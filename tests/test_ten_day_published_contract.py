from __future__ import annotations

import copy
import unittest

import server
from scripts.validate_snapshot import validate_snapshot
from tests.test_snapshot_contract import snapshot_fixture


QUALITY_GATE = {
    "minimum_independent_test_dates": 40,
    "minimum_brier_skill": 0.01,
    "minimum_auc": 0.55,
    "maximum_ece_10bin": 0.10,
    "minimum_top_decile_excess_vs_mean": 0.005,
    "minimum_top_decile_mean_net_return": 0.0,
}
READY_VALIDATION = {
    "independent_test_date_count": 40,
    "brier_score": 0.22,
    "baseline_brier_score": 0.25,
    "brier_skill": 0.12,
    "ece_10bin": 0.08,
    "auc": 0.61,
    "top_decile_mean_net_return": 0.02,
    "top_decile_excess_vs_mean": 0.01,
}


def shadow_snapshot(prediction_as_of: str | None = None) -> dict:
    snapshot = snapshot_fixture()
    snapshot["analysis_models"] = {"ten_day_return": {
        "model_id": "ten-day-technical-shadow-v1",
        "label_version": "r10-net-total-return-v1",
        "feature_schema_version": "technical-d1-v1",
        "status": "SHADOW_READY",
        "training_cutoff": "2026-08-21",
        "fit_data_cutoff": "2026-08-21",
        "validation_cutoff": "2026-08-21",
        "training_provenance": "current_universe_historical_backfill",
        "quality_gate": dict(QUALITY_GATE),
        "calibrated": False,
        "costs_ready": True,
        "tail_risk_ready": True,
        "participates_in_decision": False,
        "production_eligible": False,
        "probability": None,
        "artifact_sha256": "a" * 64,
        "validation": dict(READY_VALIDATION),
        "market_models": {
            "a_share": {
                "status": "SHADOW_READY",
                "quality_gate": dict(QUALITY_GATE),
                "validation": dict(READY_VALIDATION),
                "artifact_sha256": "c" * 64,
                "training_cutoff": "2026-08-21",
                "fit_data_cutoff": "2026-08-21",
                "validation_cutoff": "2026-08-21",
            },
            "hk": {"status": "INSUFFICIENT_DATA", "quality_gate": dict(QUALITY_GATE), "validation": {}},
            "us": {"status": "INSUFFICIENT_DATA", "quality_gate": dict(QUALITY_GATE), "validation": {}},
        },
        "limitations": ["CURRENT_UNIVERSE_BACKFILL"],
        "reason_codes": [],
        "shadow_prediction_count": 1,
        "shadow_predictions": [
            {
                "market": "a_share",
                "code": "603228",
                "model_id": "ten-day-technical-shadow-v1",
                "label_version": "r10-net-total-return-v1",
                "probability": 0.62,
                "expected_net_return": 0.03,
                "tail_risk": 0.04,
                "expected_net_utility": 0.02,
                "transaction_cost": 0.0015,
                "market_validation_status": "SHADOW_READY",
                "artifact_sha256": "c" * 64,
                "training_cutoff": "2026-08-21",
                "fit_data_cutoff": "2026-08-21",
                "participates_in_decision": False,
                "production_eligible": False,
            }
        ],
    }}
    if prediction_as_of is not None:
        snapshot["analysis_models"]["ten_day_return"]["shadow_predictions"][0][
            "prediction_as_of"
        ] = prediction_as_of
    return server.enrich_snapshot_v2(snapshot)


class TenDayPublishedContractTests(unittest.TestCase):
    def test_valid_shadow_contract_is_auditable_but_not_formal(self) -> None:
        self.assertEqual(validate_snapshot(shadow_snapshot()), [])

    def test_shadow_contract_rejects_self_authorization(self) -> None:
        snapshot = shadow_snapshot()
        snapshot["analysis_models"]["ten_day_return"]["participates_in_decision"] = True
        self.assertIn(
            "ten-day Shadow must not participate in the decision",
            validate_snapshot(snapshot),
        )

    def test_shadow_contract_rejects_bad_probability_and_model_identity(self) -> None:
        snapshot = shadow_snapshot()
        prediction = snapshot["analysis_models"]["ten_day_return"]["shadow_predictions"][0]
        prediction["probability"] = 1.2
        prediction["model_id"] = "lookalike-model"
        errors = validate_snapshot(snapshot)
        self.assertIn("ten-day Shadow prediction[0] probability must be between 0 and 1", errors)
        self.assertIn(
            "ten-day Shadow prediction[0] model_id must match ten_day_return.model_id",
            errors,
        )

    def test_shadow_ready_contract_requires_held_out_validation(self) -> None:
        snapshot = shadow_snapshot()
        snapshot["analysis_models"]["ten_day_return"].pop("validation")
        self.assertIn("ten-day Shadow held-out validation is required", validate_snapshot(snapshot))

    def test_shadow_ready_market_must_pass_the_registered_quality_gate(self) -> None:
        snapshot = shadow_snapshot()
        snapshot["analysis_models"]["ten_day_return"]["market_models"]["a_share"]["validation"][
            "brier_skill"
        ] = -0.01
        self.assertIn(
            "ten-day Shadow market_models.a_share READY gate is not met",
            validate_snapshot(snapshot),
        )

    def test_rank_eligible_shadow_requires_latest_completed_market_session(self) -> None:
        current = shadow_snapshot("2026-08-19")
        current_join = next(
            row["shadow_model"]
            for row in current["global_decision"]["evaluated_candidates"]
            if row.get("market") == "a_share" and row.get("shadow_model")
        )
        self.assertTrue(current_join["rank_eligible"])
        self.assertEqual(validate_snapshot(current), [])

        for prediction_as_of, expected_error in (
            (
                None,
                "prediction_as_of is required as an ISO date when rank_eligible=true",
            ),
            (
                "2026-08-18",
                "prediction_as_of must equal latest completed a_share session 2026-08-19",
            ),
        ):
            with self.subTest(prediction_as_of=prediction_as_of):
                snapshot = shadow_snapshot(prediction_as_of)
                joined = next(
                    row["shadow_model"]
                    for row in snapshot["global_decision"]["evaluated_candidates"]
                    if row.get("market") == "a_share" and row.get("shadow_model")
                )
                # Simulate a corrupt publication claiming eligibility.  The
                # validator must independently reject it rather than trusting
                # the server-produced boolean.
                joined["rank_eligible"] = True
                errors = validate_snapshot(snapshot)
                self.assertTrue(any(expected_error in error for error in errors), errors)

    def test_shadow_contract_rejects_provenance_or_count_tampering(self) -> None:
        snapshot = copy.deepcopy(shadow_snapshot())
        model = snapshot["analysis_models"]["ten_day_return"]
        model["training_provenance"] = "unknown"
        model["shadow_prediction_count"] = 2
        errors = validate_snapshot(snapshot)
        self.assertIn("ten-day Shadow training_provenance is invalid", errors)
        self.assertIn("ten-day Shadow prediction count is inconsistent", errors)

    def test_browser_shadow_join_must_match_the_published_prediction(self) -> None:
        snapshot = shadow_snapshot()
        joined = next(
            row["shadow_model"]
            for row in snapshot["global_decision"]["evaluated_candidates"]
            if row.get("shadow_model")
        )
        joined["probability"] = 0.11

        self.assertTrue(
            any(
                "shadow_model.probability does not match the published prediction" in error
                for error in validate_snapshot(snapshot)
            )
        )

    def test_browser_and_ledger_join_the_selected_market_artifact(self) -> None:
        snapshot = shadow_snapshot()
        model = snapshot["analysis_models"]["ten_day_return"]
        market_model = model["market_models"]["a_share"]
        market_model.update(
            {
                "artifact_sha256": "b" * 64,
                "training_cutoff": "2026-08-19",
                "fit_data_cutoff": "2026-08-19",
                "validation_cutoff": "2026-08-21",
                "last_training_signal_date": "2026-08-07",
                "last_calibration_signal_date": "2026-08-11",
            }
        )
        model["shadow_predictions"][0].update(
            {
                "artifact_sha256": "b" * 64,
                "training_cutoff": "2026-08-19",
                "fit_data_cutoff": "2026-08-19",
            }
        )

        refreshed = server.enrich_snapshot_v2(snapshot)
        joined = next(
            row["shadow_model"]
            for row in refreshed["global_decision"]["evaluated_candidates"]
            if row.get("market") == "a_share" and row.get("shadow_model")
        )

        self.assertEqual(joined["artifact_sha256"], "b" * 64)
        self.assertEqual(joined["training_cutoff"], "2026-08-19")
        self.assertNotEqual(joined["artifact_sha256"], model["artifact_sha256"])
        self.assertEqual(validate_snapshot(refreshed), [])

        joined["artifact_sha256"] = model["artifact_sha256"]
        self.assertTrue(
            any(
                "shadow_model.artifact_sha256 does not match its market model" in error
                for error in validate_snapshot(refreshed)
            )
        )

    def test_exact_shadow_model_rejects_unknown_status(self) -> None:
        snapshot = shadow_snapshot()
        snapshot["analysis_models"]["ten_day_return"]["status"] = "TYPO"
        self.assertIn("ten-day Shadow status is invalid", validate_snapshot(snapshot))

    def test_other_model_insufficient_status_is_not_mistaken_for_this_shadow_schema(self) -> None:
        snapshot = server.enrich_snapshot_v2(snapshot_fixture())
        snapshot["analysis_models"]["ten_day_return"].update(
            {"model_id": "ten-day-net-return-v0", "status": "INSUFFICIENT_DATA"}
        )
        shadow_errors = [error for error in validate_snapshot(snapshot) if error.startswith("ten-day Shadow")]
        self.assertEqual(shadow_errors, [])


if __name__ == "__main__":
    unittest.main()

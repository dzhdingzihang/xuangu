from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import model_observation_ledger as ledger


def prediction(market: str, code: str, *, probability: float, rank_eligible=None) -> dict:
    row = {
        "market": market,
        "code": code,
        "model_id": "ten-day-technical-shadow-v1",
        "label_version": "r10-net-total-return-v1",
        "feature_schema_version": "technical-d1-v1",
        "probability": probability,
        "expected_net_return": probability / 10 - 0.05,
        "expected_net_utility": probability / 10 - 0.08,
        "transaction_cost": 0.0015 if market != "hk" else 0.003,
        "tail_risk": 0.12,
        "market_validation_status": "SHADOW_REJECTED",
        "prediction_as_of": "2026-08-21",
        "artifact_sha256": ({"a_share": "a", "hk": "b", "us": "c"}[market]) * 64,
        "training_cutoff": "2026-08-08",
        "fit_data_cutoff": "2026-08-08",
        "participates_in_decision": False,
        "production_eligible": False,
    }
    if rank_eligible is not None:
        row["rank_eligible"] = rank_eligible
    return row


def snapshot(
    *,
    generated_at: str = "2026-08-21T22:49:00+08:00",
    source: str = "2026-08-22_2026-08-21_224900.json",
) -> dict:
    return {
        "snapshot_key": source,
        "generated_at": generated_at,
        "automation": {
            "trigger": "schedule",
            "scheduled_slot": "2026-08-21T22:47:00+08:00",
        },
        "global_decision": {
            "contract_version": "global-10d-v1",
            "decision_scope": "global_10d",
            "action_basis": "strict_cross_market_gate_v1",
            "action": "NO_VALID_PICK",
        },
        "analysis_models": {
            "ten_day_return": {
                "model_id": "ten-day-technical-shadow-v1",
                "label_version": "r10-net-total-return-v1",
                "feature_schema_version": "technical-d1-v1",
                "status": "SHADOW_REJECTED",
                "artifact_sha256": "d" * 64,
                "participates_in_decision": False,
                "production_eligible": False,
                "shadow_predictions": [
                    prediction("a_share", "600000", probability=0.49, rank_eligible=False),
                    prediction("hk", "0700.HK", probability=0.53),
                    prediction("us", "NVDA", probability=0.58),
                ],
            }
        },
    }


def current_observation_cohort() -> dict:
    revision = ledger.build_observation_revision(snapshot())
    return ledger._cohort_from_revisions([revision])


def rehash_revision_and_cohort(cohort: dict, revision_index: int = 0) -> None:
    revision = cohort["revisions"][revision_index]
    revision["revision_sha256"] = ledger._digest(
        {key: value for key, value in revision.items() if key != "revision_sha256"}
    )
    cohort["cohort_sha256"] = ledger._digest(
        {key: value for key, value in cohort.items() if key != "cohort_sha256"}
    )


def legacy_observation_cohort(cohort: dict) -> dict:
    """Return the exact settlement-free prediction shape written by origin/main."""

    legacy = copy.deepcopy(cohort)
    for index, revision in enumerate(legacy["revisions"]):
        for row in revision["predictions"]:
            for field in ledger.PREDICTION_SETTLEMENT_DERIVED_FIELDS:
                row.pop(field)
        rehash_revision_and_cohort(legacy, index)
    # The helper above updates the cohort hash after every revision; this final
    # pass binds all final legacy revision hashes together.
    legacy["cohort_sha256"] = ledger._digest(
        {key: value for key, value in legacy.items() if key != "cohort_sha256"}
    )
    return legacy


class ModelObservationLedgerTests(unittest.TestCase):
    def test_future_prediction_or_fit_cutoff_fails_closed(self) -> None:
        for field in ("prediction_as_of", "fit_data_cutoff"):
            payload = snapshot()
            for row in payload["analysis_models"]["ten_day_return"]["shadow_predictions"]:
                row[field] = "2026-09-01"
            with self.subTest(field=field), self.assertRaises(
                ledger.ObservationContractError
            ):
                ledger.build_observation_revision(payload)

    def test_cutoff_order_must_be_monotonic(self) -> None:
        payload = snapshot()
        for row in payload["analysis_models"]["ten_day_return"]["shadow_predictions"]:
            row["training_cutoff"] = "2026-08-10"
            row["fit_data_cutoff"] = "2026-08-09"
        with self.assertRaises(ledger.ObservationContractError):
            ledger.build_observation_revision(payload)

    def test_rejected_model_records_all_predictions_without_rank_eligibility(self) -> None:
        revision = ledger.build_observation_revision(snapshot())

        self.assertEqual(revision["track"], "MODEL_OBSERVATION")
        self.assertEqual(revision["prediction_count"], 3)
        self.assertEqual(
            revision["market_prediction_counts"],
            {"a_share": 1, "hk": 1, "us": 1},
        )
        self.assertEqual(revision["model_status"], "SHADOW_REJECTED")
        self.assertEqual([row["rank_eligible"] for row in revision["predictions"]], [False, False, False])
        self.assertTrue(all(row["track"] == ledger.TRACK for row in revision["predictions"]))
        self.assertTrue(all(row["included_in_executable_performance"] is False for row in revision["predictions"]))

    def test_every_prediction_freezes_a_ten_session_settlement_contract(self) -> None:
        revision = ledger.build_observation_revision(snapshot())

        expected = {
            "a_share": ("2026-08-24", "2026-09-04", "XSHG", "CNY", 0.0015),
            "hk": ("2026-08-24", "2026-09-04", "XHKG", "HKD", 0.003),
            "us": ("2026-08-24", "2026-09-04", "XNYS", "USD", 0.0015),
        }
        for row in revision["predictions"]:
            entry, exit_, calendar, currency, cost = expected[row["market"]]
            self.assertEqual(row["entry_trade_date"], entry)
            self.assertEqual(row["forecast_end_trade_date"], exit_)
            self.assertEqual(row["horizon_trade_sessions"], 10)
            self.assertEqual(row["entry_policy"], "next_session_open_v1")
            self.assertEqual(row["exit_policy"], "tenth_session_close_v1")
            self.assertEqual(row["calendar_id"], calendar)
            self.assertEqual(row["calendar_version"], "exchange-calendars-4.13.2")
            self.assertEqual(row["currency"], currency)
            self.assertEqual(row["transaction_cost"], cost)
            self.assertRegex(row["settlement_contract_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                row["settlement_contract_sha256"],
                ledger.settlement_contract_sha256(row),
            )

    def test_observation_ids_are_stable_across_same_slot_revisions(self) -> None:
        primary = ledger.build_observation_revision(snapshot())
        recovery_snapshot = snapshot(
            generated_at="2026-08-21T23:18:00+08:00",
            source="2026-08-22_2026-08-21_231800.json",
        )
        recovery_snapshot["analysis_models"]["ten_day_return"]["shadow_predictions"][0]["probability"] = 0.51
        recovery = ledger.build_observation_revision(recovery_snapshot)

        self.assertEqual(primary["cohort_id"], recovery["cohort_id"])
        self.assertNotEqual(primary["revision_id"], recovery["revision_id"])
        self.assertEqual(
            [row["observation_id"] for row in primary["predictions"]],
            [row["observation_id"] for row in recovery["predictions"]],
        )

    def test_2317_recovery_is_a_later_revision_of_the_2247_cohort(self) -> None:
        primary = snapshot()
        recovery = snapshot(
            generated_at="2026-08-21T23:18:00+08:00",
            source="2026-08-22_2026-08-21_231800.json",
        )
        recovery["analysis_models"]["ten_day_return"]["shadow_predictions"][2]["probability"] = 0.61

        cohorts = ledger.build_observation_cohorts(
            {primary["snapshot_key"]: primary, recovery["snapshot_key"]: recovery}
        )

        self.assertEqual(len(cohorts), 1)
        cohort = next(iter(cohorts.values()))
        self.assertEqual(cohort["revision_count"], 2)
        self.assertEqual(cohort["canonical_source_snapshot"], recovery["snapshot_key"])
        self.assertEqual(cohort["canonical_generated_at"], "2026-08-21T23:18:00+08:00")
        self.assertEqual(cohort["canonical_revision_id"], cohort["revisions"][-1]["revision_id"])

    def test_manual_and_non_daily_slots_are_not_cohorts(self) -> None:
        manual = snapshot()
        manual["automation"] = {"trigger": "workflow_dispatch", "scheduled_slot": None}
        morning = snapshot()
        morning["automation"]["scheduled_slot"] = "2026-08-21T10:17:00+08:00"

        cohorts = ledger.build_observation_cohorts(
            {"manual.json": manual, "morning.json": morning}
        )

        self.assertEqual(cohorts, {})
        with self.assertRaises(ledger.ObservationContractError):
            ledger.build_observation_cohorts({"manual.json": manual}, skip_ineligible_snapshots=False)

    def test_prediction_from_another_track_fails_closed(self) -> None:
        for foreign_track in (ledger.SHADOW_TRACK, ledger.EXECUTABLE_TRACK):
            with self.subTest(track=foreign_track):
                payload = snapshot()
                payload["analysis_models"]["ten_day_return"]["shadow_predictions"][0]["track"] = foreign_track
                with self.assertRaises(ledger.ObservationContractError):
                    ledger.build_observation_revision(payload)

    def test_duplicate_security_and_malformed_prediction_fail_closed(self) -> None:
        duplicate = snapshot()
        duplicate["analysis_models"]["ten_day_return"]["shadow_predictions"].append(
            copy.deepcopy(duplicate["analysis_models"]["ten_day_return"]["shadow_predictions"][0])
        )
        with self.assertRaises(ledger.ObservationConflictError):
            ledger.build_observation_revision(duplicate)

        malformed = snapshot()
        malformed["analysis_models"]["ten_day_return"]["shadow_predictions"][0]["probability"] = float("nan")
        with self.assertRaises(ledger.ObservationContractError):
            ledger.build_observation_revision(malformed)

    def test_same_identity_with_changed_payload_fails_closed(self) -> None:
        original = snapshot()
        changed = copy.deepcopy(original)
        changed["analysis_models"]["ten_day_return"]["shadow_predictions"][0]["probability"] = 0.77

        with self.assertRaises(ledger.ObservationConflictError):
            ledger.build_observation_cohorts(
                [(original["snapshot_key"], original), (changed["snapshot_key"], changed)]
            )

    def test_snapshot_key_makes_latest_alias_deterministic(self) -> None:
        payload = snapshot()
        immutable = ledger.build_observation_revision(payload, payload["snapshot_key"])
        latest_alias = ledger.build_observation_revision(payload, "latest.json")

        self.assertEqual(immutable, latest_alias)

    def test_complete_legacy_settlement_block_is_upgraded_deterministically(self) -> None:
        current = current_observation_cohort()
        legacy = legacy_observation_cohort(current)

        self.assertNotEqual(legacy["cohort_sha256"], current["cohort_sha256"])
        self.assertEqual(ledger.validate_observation_cohort(legacy), current)

    def test_legacy_upgrade_does_not_excuse_revision_reorder_or_duplication(self) -> None:
        primary = ledger.build_observation_revision(snapshot())
        recovery_payload = snapshot(
            generated_at="2026-08-21T23:18:00+08:00",
            source="2026-08-22_2026-08-21_231800.json",
        )
        recovery = ledger.build_observation_revision(recovery_payload)
        current = ledger._cohort_from_revisions([primary, recovery])
        legacy = legacy_observation_cohort(current)

        reordered = copy.deepcopy(legacy)
        reordered["revisions"].reverse()
        reordered["cohort_sha256"] = ledger._digest(
            {key: value for key, value in reordered.items() if key != "cohort_sha256"}
        )
        with self.assertRaisesRegex(
            ledger.ObservationConflictError,
            "revision order, count, or uniqueness",
        ):
            ledger.validate_observation_cohort(reordered)

        duplicated = copy.deepcopy(legacy)
        duplicated["revisions"].append(copy.deepcopy(duplicated["revisions"][0]))
        duplicated["cohort_sha256"] = ledger._digest(
            {key: value for key, value in duplicated.items() if key != "cohort_sha256"}
        )
        with self.assertRaisesRegex(
            ledger.ObservationConflictError,
            "revision order, count, or uniqueness",
        ):
            ledger.validate_observation_cohort(duplicated)

    def test_rehashed_outer_payload_cannot_hide_stale_prediction_digest(self) -> None:
        tampered = current_observation_cohort()
        tampered["revisions"][0]["predictions"][0]["probability"] = 0.99
        rehash_revision_and_cohort(tampered)

        with self.assertRaisesRegex(
            ledger.ObservationConflictError,
            "observation prediction digest mismatch",
        ):
            ledger.validate_observation_cohort(tampered)

    def test_prediction_fields_must_be_exactly_legacy_or_current(self) -> None:
        unknown = current_observation_cohort()
        unknown["revisions"][0]["predictions"][0]["unhashed_extension"] = True
        rehash_revision_and_cohort(unknown)
        with self.assertRaisesRegex(
            ledger.ObservationContractError,
            "prediction field set is invalid",
        ):
            ledger.validate_observation_cohort(unknown)

        partial = legacy_observation_cohort(current_observation_cohort())
        partial["revisions"][0]["predictions"][0]["entry_trade_date"] = "2026-08-24"
        rehash_revision_and_cohort(partial)
        with self.assertRaisesRegex(
            ledger.ObservationContractError,
            "settlement fields must be either wholly absent or complete",
        ):
            ledger.validate_observation_cohort(partial)

    def test_observation_identity_is_recomputed_even_when_all_hashes_are_updated(self) -> None:
        tampered = current_observation_cohort()
        row = tampered["revisions"][0]["predictions"][0]
        row["observation_id"] = "obs_" + "f" * 24
        row["prediction_sha256"] = ledger.prediction_sha256(row)
        row["settlement_contract_sha256"] = ledger.settlement_contract_sha256(row)
        rehash_revision_and_cohort(tampered)

        with self.assertRaisesRegex(
            ledger.ObservationConflictError,
            "observation_id does not match",
        ):
            ledger.validate_observation_cohort(tampered)

    def test_revision_counts_and_uniqueness_are_recomputed(self) -> None:
        bad_count = current_observation_cohort()
        bad_count["revisions"][0]["prediction_count"] += 1
        rehash_revision_and_cohort(bad_count)
        with self.assertRaisesRegex(
            ledger.ObservationConflictError,
            "prediction counts are inconsistent",
        ):
            ledger.validate_observation_cohort(bad_count)

        duplicate = current_observation_cohort()
        duplicate["revisions"][0]["predictions"].append(
            copy.deepcopy(duplicate["revisions"][0]["predictions"][0])
        )
        duplicate["revisions"][0]["prediction_count"] += 1
        duplicate["revisions"][0]["market_prediction_counts"]["a_share"] += 1
        rehash_revision_and_cohort(duplicate)
        with self.assertRaisesRegex(
            ledger.ObservationConflictError,
            "duplicate prediction identity",
        ):
            ledger.validate_observation_cohort(duplicate)

    def test_record_api_rewrites_legacy_duplicate_revision_in_current_format(self) -> None:
        current = current_observation_cohort()
        legacy = legacy_observation_cohort(current)
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / f"{current['cohort_id']}.json"
            target.write_text(json.dumps(legacy), encoding="utf-8")

            result = ledger.record_observation_revision(
                snapshot(),
                directory=pathlib.Path(directory),
            )

            self.assertFalse(result["created"])
            self.assertTrue(result["changed"])
            self.assertEqual(result["cohort"], current)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), current)

    def test_summary_is_compact_and_explicitly_isolated(self) -> None:
        cohorts = ledger.build_observation_cohorts({snapshot()["snapshot_key"]: snapshot()})
        summary = ledger.summarize_observation_cohorts(cohorts)

        self.assertEqual(summary["track"], ledger.TRACK)
        self.assertEqual(summary["status"], "OBSERVING")
        self.assertEqual(summary["cohort_count"], 1)
        self.assertEqual(summary["revision_count"], 1)
        self.assertEqual(summary["canonical_prediction_count"], 3)
        self.assertEqual(summary["market_prediction_counts"], {"a_share": 1, "hk": 1, "us": 1})
        self.assertEqual(summary["model_status_counts"], {"SHADOW_REJECTED": 1})
        self.assertFalse(summary["included_in_shadow_research"])
        self.assertFalse(summary["included_in_executable_performance"])
        self.assertEqual(summary["settlement_status"], "PENDING_MATURITY")
        self.assertFalse(summary["authorizes_production"])

    def test_record_api_atomically_creates_extends_and_deduplicates_cohort(self) -> None:
        primary = snapshot()
        recovery = snapshot(
            generated_at="2026-08-21T23:18:00+08:00",
            source="2026-08-22_2026-08-21_231800.json",
        )
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)
            first = ledger.record_observation_revision(primary, directory=target)
            duplicate = ledger.record_observation_revision(primary, directory=target)
            second = ledger.record_observation_revision(recovery, directory=target)

            self.assertTrue(first["created"])
            self.assertTrue(first["changed"])
            self.assertFalse(duplicate["created"])
            self.assertFalse(duplicate["changed"])
            self.assertFalse(second["created"])
            self.assertTrue(second["changed"])
            self.assertEqual(second["cohort"]["revision_count"], 2)
            stored = json.loads(second["path"].read_text(encoding="utf-8"))
            self.assertEqual(stored, second["cohort"])

    def test_record_api_rejects_tampered_or_foreign_track_file(self) -> None:
        payload = snapshot()
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)
            result = ledger.record_observation_revision(payload, directory=target)
            stored = json.loads(result["path"].read_text(encoding="utf-8"))
            stored["track"] = ledger.EXECUTABLE_TRACK
            result["path"].write_text(json.dumps(stored), encoding="utf-8")

            with self.assertRaises(ledger.ObservationConflictError):
                ledger.record_observation_revision(payload, directory=target)

    def test_load_api_validates_filename_and_complete_payload(self) -> None:
        payload = snapshot()
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)
            recorded = ledger.record_observation_revision(payload, directory=target)
            loaded = ledger.load_observation_cohorts(target)
            self.assertEqual(loaded, {recorded["cohort"]["cohort_id"]: recorded["cohort"]})

            tampered = json.loads(recorded["path"].read_text(encoding="utf-8"))
            tampered["prediction_count"] += 1
            recorded["path"].write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(ledger.ObservationConflictError):
                ledger.load_observation_cohorts(target)

    def test_empty_prediction_batch_is_visible_as_zero_coverage(self) -> None:
        payload = snapshot()
        payload["analysis_models"]["ten_day_return"]["status"] = "INSUFFICIENT_DATA"
        payload["analysis_models"]["ten_day_return"]["shadow_predictions"] = []

        cohorts = ledger.build_observation_cohorts({payload["snapshot_key"]: payload})
        summary = ledger.summarize_observation_cohorts(cohorts)

        self.assertEqual(summary["cohort_count"], 1)
        self.assertEqual(summary["canonical_prediction_count"], 0)
        self.assertEqual(summary["model_status_counts"], {"INSUFFICIENT_DATA": 1})


if __name__ == "__main__":
    unittest.main()

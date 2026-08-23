from __future__ import annotations

import copy
import unittest

import server
from scripts.validate_snapshot import validate_snapshot
from tests.test_snapshot_contract import dynamic_hk_us_snapshot_fixture, snapshot_fixture


def valid_no_pick_snapshot() -> dict:
    return server.enrich_snapshot_v2(snapshot_fixture())


def valid_executable_snapshot() -> dict:
    snapshot = dynamic_hk_us_snapshot_fixture()
    model = snapshot["analysis_models"]["ten_day_return"]
    model.update(
        {
            "status": "READY",
            "calibrated": True,
            "costs_ready": True,
            "tail_risk_ready": True,
            "participates_in_decision": True,
            "probability": 0.63,
        }
    )
    for market_key, section in snapshot["markets"].items():
        section["stats"]["universe_origin"] = (
            "dynamic_snapshot" if market_key == "a_share" else server.DYNAMIC_MARKET_ORIGIN
        )
        section["market_regime"] = {"state": "trend_risk_on"}
        section.setdefault("pool_health", {}).update(
            {"status": "healthy", "reason_codes": []}
        )
        section["quote_health"] = {
            **section.get("quote_health", {}),
            "status": "available",
            "quote_coverage": 1.0,
        }
    for market_state in snapshot["global_decision"]["market_states"].values():
        market_state["state"] = "READY"
        market_state["reason_codes"] = []
    snapshot["global_decision"].update(
        {
            "action": "REVIEW_EXECUTABLE_PICK",
            "probability_status": "CALIBRATED",
            "probability": 0.63,
            "calibrated": True,
            "event_pipeline_scanned": True,
            "primary": {
                "prediction_id": "pred_fixture_us_nvda",
                "market": "us",
                "code": "NVDA",
                "name": "NVIDIA",
                "status": "EXECUTABLE",
                "score_kind": "TEN_DAY_EXPECTED_NET_UTILITY",
                "model_id": model["model_id"],
                "label_version": model["label_version"],
                "calibrated": True,
                "probability": 0.63,
                "expected_net_utility": 0.024,
                "transaction_cost": 0.002,
                "tail_risk": 0.06,
                "blocker_codes": [],
            },
            "blocker_codes": [],
        }
    )
    return snapshot


def executable_builder_input() -> dict:
    snapshot = snapshot_fixture()
    snapshot["generated_at"] = "2026-08-22T09:00:00+08:00"
    snapshot = server.enrich_snapshot_v2(snapshot)
    events = []
    predictions = []
    utilities = {"a_share": 0.01, "hk": 0.02, "us": 0.04}
    for market_key, section in snapshot["markets"].items():
        section["stats"]["universe_origin"] = (
            "dynamic_snapshot" if market_key == "a_share" else server.DYNAMIC_MARKET_ORIGIN
        )
        section["market_regime"] = {"state": "trend_risk_on"}
        section["pool_health"] = {"status": "healthy", "reason_codes": []}
        section["quote_health"] = {
            **section.get("quote_health", {}),
            "status": "available",
            "quote_coverage": 1.0,
        }
        primary = section["decision"]["primary"]
        primary["execution_state"] = "CANDIDATE"
        primary["decision_gates"] = [{"id": "strict", "status": "PASS"}]
        primary["data_quality"] = {
            "score": 100,
            "inputs": [
                {"id": "quote", "required": True, "state": "fresh"},
                {"id": "kline", "required": True, "state": "fresh"},
            ],
        }
        code = primary["code"]
        events.append(
            {
                "event_id": f"official:{market_key}:{code}",
                "event_type": "announcement_or_news",
                "market": market_key,
                "symbol": code,
                "source": "Official filing",
                "source_tier": "regulatory",
                "published_at": "2026-08-21T09:00:00+08:00",
                "effective_at": "2026-08-26T09:00:00+08:00",
                "direction": "positive",
                "url": "https://example.com/official",
                "evidence_status": "verified",
                "decision_eligible": True,
                "ingestion_mode": "automatic",
            }
        )
        predictions.append(
            {
                "market": market_key,
                "code": code,
                "model_id": "ten-day-v1",
                "calibrated": True,
                "probability": 0.60,
                "expected_net_utility": utilities[market_key],
                "transaction_cost": 0.002,
                "tail_risk": 0.05,
            }
        )
    snapshot["events"] = {
        "pipeline": {
            "status": "SCANNED",
            "scanned_at": "2026-08-22T08:59:00+08:00",
            "markets": ["a_share", "hk", "us"],
        },
        "items": events,
    }
    snapshot["analysis_models"]["ten_day_return"].update(
        {
            "model_id": "ten-day-v1",
            "status": "READY",
            "calibrated": True,
            "costs_ready": True,
            "tail_risk_ready": True,
            "participates_in_decision": True,
            "predictions": predictions,
        }
    )
    return snapshot


class GlobalDecisionContractTests(unittest.TestCase):
    def test_builder_uses_expected_net_utility_instead_of_market_order(self) -> None:
        decision = server.build_global_ten_day_decision(executable_builder_input())
        self.assertEqual(decision["action"], "REVIEW_EXECUTABLE_PICK")
        self.assertEqual(decision["primary"]["market"], "us")
        self.assertEqual(decision["primary"]["expected_net_utility"], 0.04)
        self.assertRegex(decision["primary"]["prediction_id"], r"^pred_[0-9a-f]{24}$")
        self.assertEqual(decision["primary"]["label_version"], server.TEN_DAY_LABEL_VERSION)

    def test_builder_prediction_id_is_stable_for_the_same_slot(self) -> None:
        snapshot = executable_builder_input()
        snapshot["automation"] = {"scheduled_slot": "2026-08-21T08:17:00+08:00"}
        first = server.build_global_ten_day_decision(copy.deepcopy(snapshot))["primary"]["prediction_id"]
        snapshot["generated_at"] = "2026-08-22T09:03:00+08:00"
        second = server.build_global_ten_day_decision(copy.deepcopy(snapshot))["primary"]["prediction_id"]
        self.assertEqual(first, second)

    def test_research_priority_has_stable_shadow_prediction_contract(self) -> None:
        snapshot = valid_no_pick_snapshot()
        snapshot["automation"] = {"scheduled_slot": "2026-08-21T08:17:00+08:00"}
        first = server.build_global_ten_day_decision(copy.deepcopy(snapshot))["research_priority"]
        snapshot["generated_at"] = "2026-08-22T09:03:00+08:00"
        second = server.build_global_ten_day_decision(copy.deepcopy(snapshot))["research_priority"]

        self.assertEqual(first["prediction_id"], second["prediction_id"])
        self.assertEqual(first["model_id"], "ten-day-rule-shadow-v1")
        self.assertEqual(first["label_version"], "shadow-net-return-10-session-v1")
        self.assertEqual(first["score_kind"], "RULE_PRIORITY")
        self.assertEqual(first["priority_score"], first["rule_priority_score"])
        expected_priority = max(
            0.0,
            min(
                100.0,
                sum(first["priority_components"].values())
                - first["priority_risk_penalty"]
                - first["priority_market_penalty"],
            ),
        )
        self.assertEqual(first["priority_score"], round(expected_priority, 2))
        self.assertIsNone(first["probability"])
        self.assertTrue(first["entry_trade_date"])
        self.assertTrue(first["forecast_end_trade_date"])
        self.assertIn(first["calendar_id"], {"XSHG", "XHKG", "XNYS"})

    def test_builder_evaluates_complete_pool_not_only_published_legacy_rows(self) -> None:
        snapshot = snapshot_fixture()
        stronger = copy.deepcopy(snapshot["markets"]["a_share"]["decision"]["primary"])
        stronger.update({"code": "600001", "symbol": "600001", "recommendation_degree": 99, "confidence": 99})
        stronger["realtime"]["source_as_of"] = "2026-08-19T16:29:00+08:00"
        snapshot["markets"]["a_share"]["_candidate_pool"] = [
            snapshot["markets"]["a_share"]["decision"]["primary"],
            stronger,
        ]
        snapshot = server.enrich_snapshot_v2(snapshot)

        decision = snapshot["global_decision"]

        evaluated = {(row["market"], row["code"]) for row in decision["evaluated_candidates"]}
        self.assertIn(("a_share", "603228"), evaluated)
        self.assertIn(("a_share", "600001"), evaluated)
        self.assertEqual(decision["research_priority"]["code"], "600001")
        self.assertEqual(decision["action"], "NO_VALID_PICK")
        self.assertNotIn("_candidate_pool", snapshot["markets"]["a_share"])

    def test_scanned_pipeline_with_zero_events_is_a_valid_empty_result(self) -> None:
        snapshot = executable_builder_input()
        snapshot["events"] = {
            "pipeline": {
                "status": "SCANNED",
                "scanned_at": "2026-08-22T08:59:00+08:00",
                "markets": ["a_share", "hk", "us"],
            },
            "items": [],
        }

        decision = server.build_global_ten_day_decision(snapshot)

        self.assertEqual(decision["action"], "REVIEW_EXECUTABLE_PICK")
        self.assertNotIn("EXTERNAL_EVIDENCE_MISSING", decision["blocker_codes"])
        self.assertTrue(decision["event_pipeline_scanned"])
        self.assertEqual(decision["automatic_external_evidence_count"], 0)

    def test_material_negative_event_blocks_only_the_affected_candidate(self) -> None:
        snapshot = executable_builder_input()
        us = snapshot["markets"]["us"]["decision"]["primary"]
        snapshot["events"]["items"].append(
            {
                "event_id": "official:us:negative",
                "event_type": "announcement_or_news",
                "market": "us",
                "symbol": us["code"],
                "source": "SEC filing",
                "source_tier": "regulatory",
                "published_at": "2026-08-21T09:00:00+08:00",
                "effective_at": "2026-08-26T09:00:00+08:00",
                "direction": "negative",
                "materiality": "critical",
                "decision_blocking": True,
                "url": "https://example.com/material-negative",
                "evidence_status": "verified",
                "decision_eligible": True,
                "ingestion_mode": "automatic",
            }
        )

        decision = server.build_global_ten_day_decision(snapshot)

        us_row = next(row for row in decision["evaluated_candidates"] if row["market"] == "us")
        self.assertIn("MATERIAL_NEGATIVE_EVENT", us_row["blocker_codes"])
        self.assertEqual(decision["primary"]["market"], "hk")

    def test_builder_does_not_treat_ready_status_as_calibration(self) -> None:
        snapshot = executable_builder_input()
        snapshot["analysis_models"]["ten_day_return"]["calibrated"] = False
        decision = server.build_global_ten_day_decision(snapshot)
        self.assertEqual(decision["action"], "NO_VALID_PICK")
        self.assertIn("TEN_DAY_PROBABILITY_UNCALIBRATED", decision["blocker_codes"])

    def test_complete_executable_contract_is_valid(self) -> None:
        self.assertEqual(validate_snapshot(valid_executable_snapshot()), [])

    def test_ready_status_does_not_override_false_calibration(self) -> None:
        snapshot = valid_no_pick_snapshot()
        snapshot["analysis_models"]["ten_day_return"].update({"status": "READY", "calibrated": False})
        self.assertIn("ten-day READY status requires calibrated=true", validate_snapshot(snapshot))

    def test_string_false_is_not_accepted_as_a_boolean(self) -> None:
        for field in ("calibrated", "costs_ready", "tail_risk_ready", "participates_in_decision"):
            with self.subTest(field=field):
                model_snapshot = valid_no_pick_snapshot()
                model_snapshot["analysis_models"]["ten_day_return"][field] = "false"
                self.assertIn(
                    f"analysis_models.ten_day_return.{field} must be a boolean",
                    validate_snapshot(model_snapshot),
                )

        decision_snapshot = valid_no_pick_snapshot()
        decision_snapshot["global_decision"]["calibrated"] = "false"
        self.assertIn("global_decision.calibrated must be a boolean", validate_snapshot(decision_snapshot))

    def test_executable_primary_requires_complete_ten_day_metrics(self) -> None:
        expected_errors = {
            "probability": "executable primary probability must be between 0 and 1",
            "expected_net_utility": "executable primary expected_net_utility must be finite",
            "transaction_cost": "executable primary transaction_cost must be a non-negative finite number",
            "tail_risk": "executable primary tail_risk must be a non-negative finite number",
        }
        baseline = valid_executable_snapshot()
        for field, expected_error in expected_errors.items():
            with self.subTest(field=field):
                snapshot = copy.deepcopy(baseline)
                snapshot["global_decision"]["primary"].pop(field)
                self.assertIn(expected_error, validate_snapshot(snapshot))

    def test_no_valid_pick_requires_a_blocker(self) -> None:
        snapshot = valid_no_pick_snapshot()
        snapshot["global_decision"]["blocker_codes"] = []
        self.assertIn("NO_VALID_PICK must expose at least one blocker code", validate_snapshot(snapshot))

    def test_executable_primary_rejects_rule_score_and_uncalibrated_flag(self) -> None:
        rule_score_snapshot = valid_executable_snapshot()
        rule_score_snapshot["global_decision"]["primary"]["score_kind"] = "RULE_SCORE"
        self.assertIn(
            "executable primary score_kind must be a calibrated model output",
            validate_snapshot(rule_score_snapshot),
        )

        uncalibrated_snapshot = valid_executable_snapshot()
        uncalibrated_snapshot["global_decision"]["primary"]["calibrated"] = False
        self.assertIn("executable primary must be calibrated", validate_snapshot(uncalibrated_snapshot))


if __name__ == "__main__":
    unittest.main()

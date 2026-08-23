from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import server
from scripts import build_worker_assets


class BuildWorkerAssetsTests(unittest.TestCase):
    def test_shadow_outcome_is_joined_by_full_frozen_contract(self) -> None:
        pick = {
            "snapshot_key": "shadow.json",
            "automation": {},
            "global_decision": {
                "contract_version": "global-10d-v1",
                "decision_scope": "global_10d",
                "action_basis": "strict_cross_market_gate_v1",
                "action": "NO_VALID_PICK",
                "research_priority": {
                    "status": "RESEARCH_ONLY",
                    "prediction_id": "pred_0123456789abcdef01234567",
                    "model_id": "shadow-model",
                    "label_version": "shadow-label",
                    "market": "a_share",
                    "code": "600000",
                    "entry_trade_date": "2026-08-24",
                    "forecast_end_trade_date": "2026-09-04",
                    "calendar_id": "XSHG",
                    "calendar_version": "exchange-calendars-4.13.2",
                },
            }
        }
        ledger = {
            "pred_0123456789abcdef01234567": {
                "schema_version": "shadow-outcome-v1",
                "track": "SHADOW_RESEARCH",
                "status": "PENDING",
                "prediction_id": "pred_0123456789abcdef01234567",
                "model_id": "shadow-model",
                "label_version": "shadow-label",
                "market": "a_share",
                "code": "600000",
                "probability": None,
                "expected_net_utility": None,
                "tail_risk": None,
                "source_snapshot": "shadow.json",
                "entry_trade_date": "2026-08-24",
                "forecast_end_trade_date": "2026-09-04",
                "horizon_trade_sessions": 10,
                "entry_policy": "next_session_open_v1",
                "exit_policy": "tenth_session_close_v1",
                "sampling_policy": "legacy_snapshot_v1",
                "calendar_id": "XSHG",
                "calendar_version": "exchange-calendars-4.13.2",
                "transaction_cost": 0.0015,
                "secret_internal_field": "must-not-publish",
            }
        }
        outcome = build_worker_assets.matching_shadow_outcome(pick, ledger)
        self.assertEqual(outcome["status"], "PENDING")
        self.assertNotIn("secret_internal_field", outcome)
        self.assertIsNone(build_worker_assets.matching_shadow_outcome({}, ledger))

    def test_same_prediction_id_cannot_cross_join_shadow_and_executable_tracks(self) -> None:
        prediction_id = "pred_aaaaaaaaaaaaaaaaaaaaaaaa"
        pick = {
            "snapshot_key": "shared.json",
            "automation": {},
            "global_decision": {
                "contract_version": "global-10d-v1",
                "decision_scope": "global_10d",
                "action_basis": "strict_cross_market_gate_v1",
                "horizon_trade_days": 10,
                "action": "REVIEW_EXECUTABLE_PICK",
                "probability_status": "CALIBRATED",
                "probability": 0.7,
                "calibrated": True,
                "blocker_codes": [],
                "research_priority": {
                    "status": "RESEARCH_ONLY",
                    "prediction_id": prediction_id,
                    "model_id": "shadow-model",
                    "label_version": "shadow-label",
                    "market": "a_share",
                    "code": "600000",
                    "entry_trade_date": "2026-08-24",
                    "forecast_end_trade_date": "2026-09-04",
                    "calendar_id": "XSHG",
                    "calendar_version": "exchange-calendars-4.13.2",
                },
                "primary": {
                    "status": "EXECUTABLE",
                    "prediction_id": prediction_id,
                    "model_id": "formal-model",
                    "label_version": "formal-label",
                    "market": "a_share",
                    "code": "600000",
                    "score_kind": "TEN_DAY_EXPECTED_NET_UTILITY",
                    "calibrated": True,
                    "probability": 0.7,
                    "expected_net_utility": 0.04,
                    "tail_risk": 0.12,
                    "transaction_cost": 0.0015,
                    "entry_trade_date": "2026-08-24",
                    "forecast_end_trade_date": "2026-09-04",
                    "calendar_id": "XSHG",
                    "calendar_version": "exchange-calendars-4.13.2",
                },
            },
        }
        shadow = {
            prediction_id: {
                "schema_version": "shadow-outcome-v1",
                "track": "SHADOW_RESEARCH",
                "status": "PENDING",
                "prediction_id": prediction_id,
                "model_id": "shadow-model",
                "label_version": "shadow-label",
                "market": "a_share",
                "code": "600000",
                "probability": None,
                "expected_net_utility": None,
                "tail_risk": None,
                "source_snapshot": "shared.json",
                "entry_trade_date": "2026-08-24",
                "forecast_end_trade_date": "2026-09-04",
                "horizon_trade_sessions": 10,
                "entry_policy": "next_session_open_v1",
                "exit_policy": "tenth_session_close_v1",
                "sampling_policy": "legacy_snapshot_v1",
                "calendar_id": "XSHG",
                "calendar_version": "exchange-calendars-4.13.2",
                "transaction_cost": 0.0015,
            }
        }
        executable = {
            prediction_id: {
                "schema_version": "executable-outcome-v1",
                "track": "EXECUTABLE_MODEL",
                "status": "PENDING",
                "prediction_id": prediction_id,
                "model_id": "formal-model",
                "label_version": "formal-label",
                "market": "a_share",
                "code": "600000",
                "probability": 0.7,
                "expected_net_utility": 0.04,
                "tail_risk": 0.12,
                "source_snapshot": "shared.json",
                "entry_trade_date": "2026-08-24",
                "forecast_end_trade_date": "2026-09-04",
                "horizon_trade_sessions": 10,
                "entry_policy": "next_session_open_v1",
                "exit_policy": "tenth_session_close_v1",
                "sampling_policy": "all_published_executable_predictions_v1",
                "calendar_id": "XSHG",
                "calendar_version": "exchange-calendars-4.13.2",
                "transaction_cost": 0.0015,
            }
        }

        self.assertEqual(build_worker_assets.matching_shadow_outcome(pick, shadow)["track"], "SHADOW_RESEARCH")
        self.assertEqual(
            build_worker_assets.matching_executable_outcome(pick, executable)["track"],
            "EXECUTABLE_MODEL",
        )
        self.assertIsNone(build_worker_assets.matching_shadow_outcome(pick, executable))
        self.assertIsNone(build_worker_assets.matching_executable_outcome(pick, shadow))

        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "shared.json"
            source.write_text(json.dumps(pick), encoding="utf-8")
            summary = build_worker_assets.summarize_pick(source, shadow, executable)
        self.assertEqual(summary["formal_sample_status"], "PENDING")
        self.assertEqual(summary["outcome_validation"]["status"], "PENDING")
        self.assertEqual(summary["outcome_validation"]["reason"], "OUTCOME_PENDING")
        for key in (
            "probability",
            "expected_net_utility",
            "tail_risk",
            "horizon_trade_sessions",
            "entry_policy",
            "exit_policy",
            "sampling_policy",
        ):
            self.assertIn(key, summary["outcome"])

        server_summary = server.summarize_pick(
            pick,
            shadow,
            executable,
            "shared.json",
        )
        self.assertEqual(server_summary["formal_sample_status"], "PENDING")
        self.assertEqual(server_summary["outcome_validation"]["reason"], "OUTCOME_PENDING")
        for key in (
            "probability",
            "expected_net_utility",
            "tail_risk",
            "horizon_trade_sessions",
            "entry_policy",
            "exit_policy",
            "sampling_policy",
        ):
            self.assertIn(key, server_summary["outcome"])

    def test_shadow_ledger_excludes_manual_snapshots_under_current_sampling_policy(self) -> None:
        prediction_id = "pred_bbbbbbbbbbbbbbbbbbbbbbbb"
        snapshot = {
            "automation": {"trigger": "workflow_dispatch", "scheduled_slot": None},
            "global_decision": {
                "contract_version": "global-10d-v1",
                "decision_scope": "global_10d",
                "action_basis": "strict_cross_market_gate_v1",
                "action": "NO_VALID_PICK",
                "research_priority": {
                    "status": "RESEARCH_ONLY",
                    "prediction_id": prediction_id,
                    "model_id": "shadow-model",
                    "label_version": "shadow-label",
                    "market": "a_share",
                    "code": "600000",
                    "entry_trade_date": "2026-08-24",
                    "forecast_end_trade_date": "2026-09-04",
                    "calendar_id": "XSHG",
                    "calendar_version": "exchange-calendars-4.13.2",
                },
            },
        }
        outcome = {
            "track": "SHADOW_RESEARCH",
            "status": "PENDING",
            "prediction_id": prediction_id,
            "model_id": "shadow-model",
            "label_version": "shadow-label",
            "market": "a_share",
            "code": "600000",
            "entry_trade_date": "2026-08-24",
            "forecast_end_trade_date": "2026-09-04",
            "calendar_id": "XSHG",
            "calendar_version": "exchange-calendars-4.13.2",
            "source_snapshot": "manual.json",
        }
        inventory = {
            "track": "SHADOW_RESEARCH",
            "raw_count": 1,
            "read_excluded_count": 0,
            "read_conflict_count": 0,
            "records": {prediction_id: outcome},
        }
        stats = build_worker_assets.history_evaluation.ledger_statistics(
            {"manual.json": snapshot}, inventory, "SHADOW_RESEARCH"
        )
        self.assertEqual(stats["raw_count"], 1)
        self.assertEqual(stats["raw_prediction_count"], 1)
        self.assertEqual(stats["eligible_count"], 0)
        self.assertEqual(stats["prediction_count"], 0)
        self.assertEqual(stats["pending_count"], 0)
        self.assertEqual(stats["excluded_count"], 1)

    def test_embedded_formal_outcome_cannot_bypass_executable_ledger(self) -> None:
        prediction_id = "pred_cccccccccccccccccccccccc"
        pick = {
            "global_decision": {
                "contract_version": "global-10d-v1",
                "decision_scope": "global_10d",
                "action_basis": "strict_cross_market_gate_v1",
                "horizon_trade_days": 10,
                "action": "REVIEW_EXECUTABLE_PICK",
                "probability_status": "CALIBRATED",
                "probability": 0.7,
                "calibrated": True,
                "blocker_codes": [],
                "primary": {
                    "status": "EXECUTABLE",
                    "prediction_id": prediction_id,
                    "model_id": "formal-model",
                    "label_version": "formal-label",
                    "market": "a_share",
                    "code": "600000",
                    "score_kind": "TEN_DAY_EXPECTED_NET_UTILITY",
                    "calibrated": True,
                    "probability": 0.7,
                    "expected_net_utility": 0.04,
                    "tail_risk": 0.12,
                    "transaction_cost": 0.0015,
                    "entry_trade_date": "2026-08-24",
                    "forecast_end_trade_date": "2026-09-04",
                    "calendar_id": "XSHG",
                    "calendar_version": "exchange-calendars-4.13.2",
                },
            },
            "outcome": {
                "schema_version": "executable-outcome-v1",
                "track": "EXECUTABLE_MODEL",
                "status": "SETTLED",
                "prediction_id": prediction_id,
                "model_id": "formal-model",
                "label_version": "formal-label",
                "market": "a_share",
                "code": "600000",
                "entry_trade_date": "2026-08-24",
                "forecast_end_trade_date": "2026-09-04",
                "entry_at": "2026-08-24T01:30:00Z",
                "entry_price": 10.0,
                "entry_source": "fixture",
                "exit_at": "2026-09-04T07:00:00Z",
                "exit_price": 11.0,
                "exit_source": "fixture",
                "gross_total_return": 0.1,
                "net_total_return": 0.0985,
                "transaction_cost": 0.0015,
                "corporate_action_adjusted": True,
                "calendar_id": "XSHG",
                "calendar_version": "exchange-calendars-4.13.2",
                "currency": "CNY",
                "fx_rate_source": "not_applicable",
                "positive_label": True,
                "settled_at": "2026-09-04T08:00:00Z",
            },
            "shadow_outcome": {
                "track": "SHADOW_RESEARCH",
                "status": "SETTLED",
                "prediction_id": "pred_dddddddddddddddddddddddd",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "pick.json"
            target = pathlib.Path(directory) / "public.json"
            source.write_text(json.dumps(pick), encoding="utf-8")

            summary = build_worker_assets.summarize_pick(source, {}, {})
            self.assertNotIn("outcome", summary)

            build_worker_assets.write_public_pick(source, target, {}, {})
            published = json.loads(target.read_text(encoding="utf-8"))
            self.assertNotIn("outcome", published)
            self.assertNotIn("ten_day_outcome", published)
            self.assertNotIn("shadow_outcome", published)
            self.assertEqual(published["formal_sample_status"], "MISSING")
            self.assertEqual(published["outcome_validation"]["reason"], "EXECUTABLE_OUTCOME_MISSING")

    def test_read_outcome_map_rejects_filename_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "wrong.json"
            path.write_text(json.dumps({"prediction_id": "pred_right"}), encoding="utf-8")
            self.assertEqual(build_worker_assets.read_outcome_map(path.parent), {})


if __name__ == "__main__":
    unittest.main()

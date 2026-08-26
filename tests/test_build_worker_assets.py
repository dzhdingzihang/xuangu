from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import server
from scripts import build_worker_assets


class BuildWorkerAssetsTests(unittest.TestCase):
    def test_history_summary_preserves_rule_qualified_candidate_without_probability(self) -> None:
        pick = {
            "snapshot_key": "qualified.json",
            "target_date": "2026-08-25",
            "signal_date": "2026-08-25",
            "generated_at": "2026-08-25T22:47:00+08:00",
            "global_decision": {
                "contract_version": "global-10d-v1",
                "decision_scope": "global_10d",
                "action_basis": "strict_cross_market_gate_v1",
                "action": "NO_VALID_PICK",
                "primary": None,
                "blocker_codes": ["TEN_DAY_PROBABILITY_UNCALIBRATED"],
            },
            "production_decision": {
                "contract_version": "production-rule-10d-v1",
                "decision_scope": "global_10d_bounded_recall",
                "action_basis": "strict_rule_qualification_v1",
                "action": "QUALIFIED_PICK",
                "rule_model_id": "ten-day-audited-rule-ensemble-v1",
                "score_kind": "RULE_QUALIFICATION_SCORE",
                "probability_status": "NOT_APPLICABLE",
                "probability": None,
                "calibrated": False,
                "expected_net_utility": None,
                "qualified_candidate_count": 1,
                "rejected_candidate_count": 796,
                "evaluated_candidate_count": 797,
                "blocker_codes": [],
                "primary": {
                    "qualification_id": "qual_0123456789abcdef01234567",
                    "status": "QUALIFIED",
                    "market": "hk",
                    "code": "0300.HK",
                    "name": "美的集团",
                    "rule_model_id": "ten-day-audited-rule-ensemble-v1",
                    "score_kind": "RULE_QUALIFICATION_SCORE",
                    "qualification_score": 82.4,
                    "probability": None,
                    "calibrated": False,
                    "expected_net_utility": None,
                    "blocker_codes": [],
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "qualified.json"
            path.write_text(json.dumps(pick, ensure_ascii=False), encoding="utf-8")
            summary = build_worker_assets.summarize_pick(path)

        self.assertEqual(summary["production_action"], "QUALIFIED_PICK")
        self.assertEqual(summary["qualification_history_kind"], "qualified_rule_10d_v1")
        self.assertEqual(summary["qualification_id"], "qual_0123456789abcdef01234567")
        primary = summary["production_decision"]["primary"]
        self.assertEqual(primary["code"], "0300.HK")
        self.assertIsNone(primary["probability"])
        self.assertFalse(primary["calibrated"])
        qualified = summary["production_decision"]["qualified_candidates"]
        self.assertEqual([row["code"] for row in qualified], ["0300.HK"])
        self.assertFalse(summary["production_decision"]["qualified_candidates_truncated"])

    def test_history_summary_bounds_and_preserves_the_full_qualified_identity_list(self) -> None:
        rows = [
            {
                "qualification_id": f"qual_{index:024d}",
                "status": "QUALIFIED",
                "market": "us",
                "code": f"Q{index:02d}",
                "name": f"Qualified {index}",
                "qualification_score": 90 - index / 10,
                "score_kind": "RULE_QUALIFICATION_SCORE",
                "probability": None,
                "calibrated": False,
                "rule_model_id": "ten-day-audited-rule-ensemble-v3",
                "event_candidate_scanned": True,
                "verified_positive_event_ids": ["event-1"],
                "qualification_track": "event_catalyst",
                "track_evaluations": [
                    {"track": "event_catalyst", "status": "PASS", "blocker_codes": []},
                    {"track": "quality_technical", "status": "PASS", "blocker_codes": []},
                ],
                "candidate_snapshot": {"code": f"Q{index:02d}", "kline": [{"close": index}]},
            }
            for index in range(25)
        ]
        decision = {
            "contract_version": "production-rule-10d-v1",
            "decision_scope": "global_10d_bounded_recall",
            "action_basis": "dual_track_candidate_qualification_v3",
            "action": "QUALIFIED_PICK",
            "rule_model_id": "ten-day-audited-rule-ensemble-v3",
            "score_kind": "RULE_QUALIFICATION_SCORE",
            "probability": None,
            "calibrated": False,
            "qualified_candidate_count": len(rows),
            "primary": rows[0],
            "qualified_candidates": rows,
        }

        summary = build_worker_assets.summarize_production_decision(
            {
                "model_version": build_worker_assets.CURRENT_PRODUCTION_MODEL_VERSION,
                "production_decision": decision,
            }
        )

        self.assertEqual(
            len(summary["qualified_candidates"]),
            build_worker_assets.MAX_QUALIFIED_SUMMARY_CANDIDATES,
        )
        self.assertEqual(summary["qualified_candidates"][0]["code"], "Q00")
        self.assertEqual(summary["qualified_candidates"][-1]["code"], "Q19")
        self.assertEqual(summary["qualified_candidates"][0]["qualification_track"], "event_catalyst")
        self.assertEqual(summary["qualified_candidates"][0]["track_evaluations"][0]["status"], "PASS")
        self.assertTrue(summary["qualified_candidates_truncated"])
        self.assertTrue(all("candidate_snapshot" not in row for row in summary["qualified_candidates"]))

    def test_current_model_rejects_mismatched_rule_contract_from_history_and_status(self) -> None:
        decision = {
            "contract_version": "production-rule-10d-v1",
            "decision_scope": "global_10d_bounded_recall",
            "action_basis": "candidate_level_rule_qualification_v2",
            "action": "QUALIFIED_PICK",
            "rule_model_id": "ten-day-audited-rule-ensemble-v2",
            "score_kind": "RULE_QUALIFICATION_SCORE",
            "probability": None,
            "calibrated": False,
            "qualified_candidate_count": 1,
            "primary": {
                "qualification_id": "qual_0123456789abcdef01234567",
                "status": "QUALIFIED",
                "market": "us",
                "code": "AAPL",
                "rule_model_id": "ten-day-audited-rule-ensemble-v2",
                "score_kind": "RULE_QUALIFICATION_SCORE",
                "qualification_score": 80,
                "probability": None,
                "calibrated": False,
            },
        }
        mismatched = {
            "model_version": build_worker_assets.CURRENT_PRODUCTION_MODEL_VERSION,
            "target_date": "2026-08-26",
            "generated_at": "2026-08-26T22:47:00+08:00",
            "production_decision": decision,
        }
        self.assertIsNone(build_worker_assets.summarize_production_decision(mismatched))
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "mismatched.json"
            path.write_text(json.dumps(mismatched), encoding="utf-8")
            summary = build_worker_assets.summarize_pick(path)
        self.assertIsNone(summary["production_decision"])
        self.assertEqual(summary["production_action"], "NO_QUALIFIED_PICK")
        self.assertIsNone(summary["qualification_history_kind"])

        archived = {**mismatched, "model_version": "smart-selector-2026-08-26.1-candidate-rule"}
        archived_summary = build_worker_assets.summarize_production_decision(archived)
        self.assertIsNotNone(archived_summary)
        self.assertEqual(archived_summary["rule_model_id"], "ten-day-audited-rule-ensemble-v2")

        v3_decision = {
            **decision,
            "action_basis": "dual_track_candidate_qualification_v3",
            "rule_model_id": "ten-day-audited-rule-ensemble-v3",
            "action": "NO_QUALIFIED_PICK",
            "qualified_candidate_count": 0,
            "primary": None,
            "qualified_candidates": [],
        }
        current_v3 = {
            **mismatched,
            "production_decision": v3_decision,
        }
        self.assertIsNotNone(build_worker_assets.summarize_production_decision(current_v3))

        archived_with_v3 = {
            **current_v3,
            "model_version": "smart-selector-2026-08-26.1-candidate-rule",
        }
        self.assertIsNone(build_worker_assets.summarize_production_decision(archived_with_v3))
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "archived-v3.json"
            path.write_text(json.dumps(archived_with_v3), encoding="utf-8")
            summary = build_worker_assets.summarize_pick(path)
        self.assertIsNone(summary["production_decision"])
        self.assertEqual(summary["production_action"], "NO_QUALIFIED_PICK")
        self.assertIsNone(summary["qualification_history_kind"])

    def test_full_worker_snapshots_are_bounded_to_representative_decision_days(self) -> None:
        summaries = []
        for day in range(1, 36):
            date = f"2026-07-{day:02d}"
            summaries.extend(
                [
                    {
                        "target_date": date,
                        "generated_at": f"{date}T22:47:00+08:00",
                        "cache_key": f"{date}-late.json",
                        "history_kind": "global_10d_v1",
                    },
                    {
                        "target_date": date,
                        "generated_at": f"{date}T08:17:00+08:00",
                        "cache_key": f"{date}-early.json",
                        "history_kind": "global_10d_v1",
                    },
                ]
            )

        selected = build_worker_assets.select_public_snapshot_files(summaries, limit=30)

        self.assertEqual(len(selected), 30)
        self.assertIn("2026-07-35-late.json", selected)
        self.assertNotIn("2026-07-35-early.json", selected)
        self.assertNotIn("2026-07-01-late.json", selected)

    def test_technical_shadow_outcome_publishes_nested_model_probability(self) -> None:
        technical_id = "pred_abcdef0123456789abcdef01"
        rule_id = "pred_0123456789abcdef01234567"
        pick = {
            "snapshot_key": "technical.json",
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T22:47:00+08:00",
            },
            "global_decision": {
                "contract_version": "global-10d-v1",
                "decision_scope": "global_10d",
                "action_basis": "strict_cross_market_gate_v1",
                "action": "NO_VALID_PICK",
                "probability": None,
                "market_states": {
                    "a_share": {"state": "READY"},
                    "hk": {"state": "READY"},
                    "us": {"state": "READY"},
                },
                "research_priority": {
                    "status": "RESEARCH_ONLY",
                    "prediction_id": rule_id,
                    "model_id": "ten-day-rule-shadow-v1",
                    "label_version": "shadow-net-return-10-session-v1",
                    "market": "us",
                    "code": "NVDA",
                    "probability": None,
                    "entry_trade_date": "2026-08-24",
                    "forecast_end_trade_date": "2026-09-04",
                    "calendar_id": "XNYS",
                    "calendar_version": "exchange-calendars-4.13.2",
                    "shadow_model": {
                        "status": "SHADOW_ONLY",
                        "rank_eligible": True,
                        "prediction_id": technical_id,
                        "model_id": "ten-day-technical-shadow-v1",
                        "label_version": "r10-net-total-return-v1",
                        "probability": 0.62,
                        "expected_net_utility": 0.031,
                        "tail_risk": 0.084,
                        "transaction_cost": 0.0018,
                        "artifact_sha256": "a" * 64,
                        "training_cutoff": "2026-08-08",
                        "calibrated": False,
                        "participates_in_decision": False,
                        "production_eligible": False,
                    },
                },
            },
        }
        technical_outcome = {
            "schema_version": "shadow-outcome-v1",
            "track": "SHADOW_RESEARCH",
            "status": "PENDING",
            "prediction_id": technical_id,
            "model_id": "ten-day-technical-shadow-v1",
            "label_version": "r10-net-total-return-v1",
            "market": "us",
            "code": "NVDA",
            "probability": 0.62,
            "expected_net_utility": 0.031,
            "tail_risk": 0.084,
            "transaction_cost": 0.0018,
            "artifact_sha256": "a" * 64,
            "training_cutoff": "2026-08-08",
            "source_snapshot": "technical.json",
            "entry_trade_date": "2026-08-24",
            "forecast_end_trade_date": "2026-09-04",
            "horizon_trade_sessions": 10,
            "entry_policy": "next_session_open_v1",
            "exit_policy": "tenth_session_close_v1",
            "sampling_policy": "daily_last_primary_checkpoint_v1",
            "calendar_id": "XNYS",
            "calendar_version": "exchange-calendars-4.13.2",
        }
        old_rule_outcome = dict(
            technical_outcome,
            prediction_id=rule_id,
            model_id="ten-day-rule-shadow-v1",
            label_version="shadow-net-return-10-session-v1",
            probability=None,
            expected_net_utility=None,
            tail_risk=None,
            artifact_sha256=None,
            training_cutoff=None,
        )

        published = build_worker_assets.matching_shadow_outcome(
            pick,
            {technical_id: technical_outcome, rule_id: old_rule_outcome},
        )

        self.assertEqual(published["prediction_id"], technical_id)
        self.assertEqual(published["model_id"], "ten-day-technical-shadow-v1")
        self.assertEqual(published["probability"], 0.62)
        self.assertEqual(published["artifact_sha256"], "a" * 64)
        self.assertEqual(published["training_cutoff"], "2026-08-08")
        self.assertIsNone(pick["global_decision"]["research_priority"]["probability"])

    def test_shadow_outcome_is_joined_by_full_frozen_contract(self) -> None:
        pick = {
            "snapshot_key": "shadow.json",
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T22:47:00+08:00",
            },
            "global_decision": {
                "contract_version": "global-10d-v1",
                "decision_scope": "global_10d",
                "action_basis": "strict_cross_market_gate_v1",
                "action": "NO_VALID_PICK",
                "market_states": {
                    "a_share": {"state": "READY"},
                    "hk": {"state": "READY"},
                    "us": {"state": "READY"},
                },
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
                    "shadow_model": {
                        "status": "SHADOW_ONLY",
                        "rank_eligible": True,
                        "prediction_id": "pred_0123456789abcdef01234567",
                        "model_id": "shadow-model",
                        "label_version": "shadow-label",
                        "probability": 0.61,
                        "expected_net_utility": 0.02,
                        "tail_risk": 0.08,
                        "transaction_cost": 0.0015,
                        "artifact_sha256": "a" * 64,
                        "training_cutoff": "2026-08-08",
                        "calibrated": False,
                        "participates_in_decision": False,
                        "production_eligible": False,
                    },
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
                "probability": 0.61,
                "expected_net_utility": 0.02,
                "tail_risk": 0.08,
                "source_snapshot": "shadow.json",
                "entry_trade_date": "2026-08-24",
                "forecast_end_trade_date": "2026-09-04",
                "horizon_trade_sessions": 10,
                "entry_policy": "next_session_open_v1",
                "exit_policy": "tenth_session_close_v1",
                "sampling_policy": "daily_last_primary_checkpoint_v1",
                "calendar_id": "XSHG",
                "calendar_version": "exchange-calendars-4.13.2",
                "transaction_cost": 0.0015,
                "artifact_sha256": "a" * 64,
                "training_cutoff": "2026-08-08",
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
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T22:47:00+08:00",
            },
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
                "market_states": {
                    "a_share": {"state": "READY"},
                    "hk": {"state": "READY"},
                    "us": {"state": "READY"},
                },
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
                    "shadow_model": {
                        "status": "SHADOW_ONLY",
                        "rank_eligible": True,
                        "prediction_id": prediction_id,
                        "model_id": "shadow-model",
                        "label_version": "shadow-label",
                        "probability": 0.61,
                        "expected_net_utility": 0.02,
                        "tail_risk": 0.08,
                        "transaction_cost": 0.0015,
                        "artifact_sha256": "a" * 64,
                        "training_cutoff": "2026-08-08",
                        "calibrated": False,
                        "participates_in_decision": False,
                        "production_eligible": False,
                    },
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
                "probability": 0.61,
                "expected_net_utility": 0.02,
                "tail_risk": 0.08,
                "source_snapshot": "shared.json",
                "entry_trade_date": "2026-08-24",
                "forecast_end_trade_date": "2026-09-04",
                "horizon_trade_sessions": 10,
                "entry_policy": "next_session_open_v1",
                "exit_policy": "tenth_session_close_v1",
                "sampling_policy": "daily_last_primary_checkpoint_v1",
                "calendar_id": "XSHG",
                "calendar_version": "exchange-calendars-4.13.2",
                "transaction_cost": 0.0015,
                "artifact_sha256": "a" * 64,
                "training_cutoff": "2026-08-08",
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

    def test_shadow_model_history_summary_keeps_audit_evidence_not_pool_predictions(self) -> None:
        pick = {
            "analysis_models": {
                "ten_day_return": {
                    "model_id": "ten-day-technical-shadow-v1",
                    "status": "SHADOW_READY",
                    "label_version": "r10-net-total-return-v1",
                    "feature_schema_version": "technical-d1-v1",
                    "training_cutoff": "2026-08-21",
                    "training_provenance": "current_universe_historical_backfill",
                    "calibrated": False,
                    "participates_in_decision": False,
                    "production_eligible": False,
                    "shadow_prediction_count": 800,
                    "validation": {
                        "independent_test_date_count": 20,
                        "brier_score": 0.22,
                        "ece_10bin": 0.08,
                        "auc": 0.61,
                        "private_fold_rows": [1, 2, 3],
                    },
                    "market_models": {
                        "a_share": {
                            "status": "SHADOW_READY",
                            "artifact_sha256": "a" * 64,
                            "transaction_cost": 0.0015,
                            "validation": {"test_row_count": 100, "brier_score": 0.21},
                            "coefficients": [0.1] * 14,
                        }
                    },
                    "limitations": ["CURRENT_UNIVERSE_BACKFILL"],
                    "shadow_predictions": [{"code": str(index)} for index in range(800)],
                }
            }
        }

        result = build_worker_assets.summarize_analysis_models(pick)["ten_day_return"]
        self.assertEqual(result["shadow_prediction_count"], 800)
        self.assertEqual(result["validation"]["brier_score"], 0.22)
        self.assertEqual(result["market_models"]["a_share"]["validation"]["test_row_count"], 100)
        self.assertNotIn("shadow_predictions", result)
        self.assertNotIn("private_fold_rows", result["validation"])
        self.assertNotIn("coefficients", result["market_models"]["a_share"])


if __name__ == "__main__":
    unittest.main()

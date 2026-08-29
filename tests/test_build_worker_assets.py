from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

import server
from scripts import build_worker_assets


def runtime_quote_candidate(
    code: str,
    market: str,
    *,
    price: float = 10.0,
    source_as_of: str = "2026-08-26T10:00:00+08:00",
    volume_unit: str | None = None,
) -> dict:
    currency = {"a_share": "CNY", "hk": "HKD", "us": "USD"}[market]
    if volume_unit is None:
        volume_unit = "lot" if market == "a_share" else "share"
    return {
        "code": code,
        "symbol": code,
        "name": f"Candidate {code}",
        "currency": currency,
        "realtime": {
            "price": price,
            "source_as_of": source_as_of,
            "fetched_at": "2026-08-26T10:00:10+08:00",
            "volume_unit": volume_unit,
        },
        "kline": [{"date": "2026-08-25", "close": price}],
        "large_unused_payload": ["do-not-publish"] * 20,
    }


def runtime_snapshot_fixture() -> dict:
    a_share = runtime_quote_candidate("SH600000", "a_share")
    hk = runtime_quote_candidate("00700.HK", "hk", price=580)
    us = runtime_quote_candidate("BRK_B", "us", price=500)
    msft = runtime_quote_candidate("MSFT", "us", price=510)
    pfe = runtime_quote_candidate("PFE", "us", price=28)
    return {
        "schema_version": "selector-snapshot-v2",
        "selector_mode": "fixture",
        "model_version": build_worker_assets.CURRENT_PRODUCTION_MODEL_VERSION,
        "weights_version": "weights-v1",
        "universe_version": "universe-v1",
        "calendar_version": "calendar-v1",
        "snapshot_key": "2026-08-26_fixture.json",
        "generated_at": "2026-08-26T10:01:00+08:00",
        "target_date": "2026-08-26",
        "signal_date": "2026-08-25",
        "automation": {
            "trigger": "schedule",
            "scheduled_slot": "2026-08-26T10:17:00+08:00",
            "scheduled_invocation_slot": "2026-08-26T10:17:00+08:00",
            "generation_attempt": 1,
            "run_id": "fixture:1",
            "unused": "drop-me",
        },
        "markets": {
            "a_share": {
                "quote_health": {"status": "available", "requested_count": 300, "quote_count": 300},
                "decision": {"primary": None, "blocked_candidate": a_share, "watchlist": [a_share]},
            },
            "hk": {
                "quote_health": {"status": "available", "requested_count": 200, "quote_count": 200},
                "decision": {"primary": hk, "watchlist": [hk]},
            },
            "us": {
                "quote_health": {"status": "available", "requested_count": 300, "quote_count": 300},
                "decision": {"primary": None, "watchlist": [us]},
            },
        },
        "global_decision": {
            "contract_version": "global-10d-v1",
            "decision_scope": "global_10d",
            "horizon_trade_days": 10,
            "action": "NO_VALID_PICK",
            "action_basis": "strict_cross_market_gate_v1",
            "probability_status": "UNAVAILABLE",
            "probability": None,
            "calibrated": False,
            "primary": {"market": "us", "code": "MSFT", "candidate_snapshot": msft},
            "research_priority": {"market": "hk", "code": "0700.HK", "candidate_snapshot": hk},
            "market_states": {"a_share": {"state": "BLOCKED"}, "hk": {"state": "READY"}, "us": {"state": "READY"}},
            "evaluated_candidates": [{"candidate_snapshot": pfe}] * 798,
            "blocker_codes": ["TEN_DAY_PROBABILITY_UNCALIBRATED"],
        },
        "production_rule_inputs": {"contract_version": "production-rule-inputs-v2", "rows": [{}] * 798},
        "production_decision": {
            "contract_version": "production-rule-10d-v1",
            "decision_scope": "global_10d_bounded_recall",
            "horizon_trade_days": 10,
            "action": "QUALIFIED_PICK",
            "action_basis": "dual_track_candidate_qualification_v4",
            "rule_model_id": "ten-day-audited-rule-ensemble-v4",
            "score_kind": "RULE_QUALIFICATION_SCORE",
            "probability": None,
            "calibrated": False,
            "qualified_candidate_count": 1,
            "rejected_candidate_count": 797,
            "evaluated_candidate_count": 798,
            "primary": {
                "qualification_id": "qual_0123456789abcdef01234567",
                "status": "QUALIFIED",
                "market": "us",
                "code": "PFE",
                "name": "Pfizer",
                "qualification_score": 75,
                "score_kind": "RULE_QUALIFICATION_SCORE",
                "probability": None,
                "calibrated": False,
                "candidate_snapshot": pfe,
            },
            "qualified_candidates": [
                {
                    "qualification_id": "qual_0123456789abcdef01234567",
                    "status": "QUALIFIED",
                    "market": "us",
                    "code": "PFE",
                    "name": "Pfizer",
                    "qualification_score": 75,
                    "score_kind": "RULE_QUALIFICATION_SCORE",
                    "probability": None,
                    "calibrated": False,
                    "candidate_snapshot": pfe,
                }
            ],
            "evaluated_candidates": [{"candidate_snapshot": pfe}] * 798,
            "blocker_codes": [],
        },
        "events": [{"large": "drop-me"}] * 100,
    }


def bounded_live_snapshot(formal_count: int, visible_count: int = 0) -> dict:
    snapshot = runtime_snapshot_fixture()
    for section in snapshot["markets"].values():
        section["decision"] = {"primary": None, "blocked_candidate": None, "watchlist": []}
    snapshot["global_decision"]["primary"] = None
    snapshot["global_decision"]["research_priority"] = None

    qualified = []
    for index in range(formal_count):
        code = f"Q{index:03d}"
        candidate = runtime_quote_candidate(code, "us", price=10 + index / 100)
        qualified.append(
            {
                "qualification_id": f"qual_{index:024x}",
                "status": "QUALIFIED",
                "market": "us",
                "code": code,
                "name": candidate["name"],
                "qualification_score": 90 - index / 100,
                "score_kind": "RULE_QUALIFICATION_SCORE",
                "probability": None,
                "calibrated": False,
                "candidate_snapshot": candidate,
            }
        )
    decision = snapshot["production_decision"]
    decision["action"] = "QUALIFIED_PICK" if qualified else "NO_QUALIFIED_PICK"
    decision["qualified_candidate_count"] = len(qualified)
    decision["primary"] = qualified[0] if qualified else None
    decision["qualified_candidates"] = qualified
    decision["evaluated_candidates"] = copy.deepcopy(qualified)

    snapshot["markets"]["us"]["decision"]["watchlist"] = [
        runtime_quote_candidate(f"V{index:03d}", "us", price=20 + index / 100)
        for index in range(visible_count)
    ]
    return snapshot


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
                "rule_model_id": "ten-day-audited-rule-ensemble-v4",
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
            "action_basis": "dual_track_candidate_qualification_v4",
            "action": "QUALIFIED_PICK",
            "rule_model_id": "ten-day-audited-rule-ensemble-v4",
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

        v4_decision = {
            **decision,
            "action_basis": "dual_track_candidate_qualification_v4",
            "rule_model_id": "ten-day-audited-rule-ensemble-v4",
            "action": "NO_QUALIFIED_PICK",
            "qualified_candidate_count": 0,
            "primary": None,
            "qualified_candidates": [],
        }
        current_v4 = {
            **mismatched,
            "production_decision": v4_decision,
        }
        self.assertIsNotNone(build_worker_assets.summarize_production_decision(current_v4))

        archived_with_v4 = {
            **current_v4,
            "model_version": "smart-selector-2026-08-26.1-candidate-rule",
        }
        self.assertIsNone(build_worker_assets.summarize_production_decision(archived_with_v4))
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "archived-v4.json"
            path.write_text(json.dumps(archived_with_v4), encoding="utf-8")
            summary = build_worker_assets.summarize_pick(path)
        self.assertIsNone(summary["production_decision"])
        self.assertEqual(summary["production_action"], "NO_QUALIFIED_PICK")
        self.assertIsNone(summary["qualification_history_kind"])

        historical_v3 = {
            **archived_with_v4,
            "production_decision": {
                **v4_decision,
                "action_basis": "dual_track_candidate_qualification_v3",
                "rule_model_id": "ten-day-audited-rule-ensemble-v3",
            },
        }
        self.assertIsNotNone(build_worker_assets.summarize_production_decision(historical_v3))

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

    def test_historical_replay_summary_is_bounded_and_cannot_publish_authority(self) -> None:
        pick = {
            "analysis_models": {
                "historical_replay": {
                    "schema_version": "archived-shortlist-replay-summary-v1",
                    "track": "ARCHIVED_SHORTLIST_REPLAY",
                    "evidence_class": "RETROSPECTIVE",
                    "universe_scope": "ARCHIVED_SHORTLIST_ONLY",
                    "full_point_in_time_universe": False,
                    "status": "READY",
                    "cohort_count": 9,
                    "signal_date_count": 4,
                    "independent_entry_date_count": 7,
                    "shortlist_count": 27,
                    "settled_count": 18,
                    "pending_count": 9,
                    "status_counts": {"SETTLED": 18, "PENDING_MATURITY": 9},
                    "market_counts": {"a_share": 10, "hk": 8, "us": 9},
                    "metrics": {
                        "sample_count": 18,
                        "mean_net_return": 0.02,
                        "mean_net_excess_return": 0.01,
                        "positive_net_return_rate": 0.6,
                        "private_distribution": [1, 2, 3],
                    },
                    "cohorts": [{"large": "drop-me"}] * 100,
                    "participates_in_decision": True,
                    "promotion_eligible": True,
                    "authorizes_production": True,
                }
            }
        }

        result = build_worker_assets.summarize_analysis_models(pick)["historical_replay"]

        self.assertEqual(result["cohort_count"], 9)
        self.assertEqual(result["signal_date_count"], 4)
        self.assertEqual(result["independent_entry_date_count"], 7)
        self.assertEqual(result["metrics"]["sample_count"], 18)
        self.assertNotIn("private_distribution", result["metrics"])
        self.assertNotIn("cohorts", result)
        self.assertEqual(result["evidence_class"], "RETROSPECTIVE")
        self.assertEqual(result["universe_scope"], "ARCHIVED_SHORTLIST_ONLY")
        self.assertFalse(result["full_point_in_time_universe"])
        for field in (
            "included_in_live_observation_performance",
            "included_in_shadow_research",
            "included_in_executable_performance",
            "calibrated",
            "participates_in_decision",
            "production_eligible",
            "promotion_eligible",
            "authorizes_production",
        ):
            self.assertIs(result[field], False)

    def test_worker_runtime_is_a_bounded_prevalidated_summary(self) -> None:
        snapshot = runtime_snapshot_fixture()
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
        latest_summary = {
            "snapshot_key": snapshot["snapshot_key"],
            "generated_at": snapshot["generated_at"],
            "global_decision": copy.deepcopy(snapshot["global_decision"]),
            "production_decision": copy.deepcopy(snapshot["production_decision"]),
            "events": snapshot["events"],
        }

        runtime = build_worker_assets.build_worker_runtime(
            snapshot,
            latest_summary,
            source_bytes,
        )

        self.assertEqual(runtime["contract_version"], "worker-runtime-v1")
        self.assertEqual(runtime["snapshot_key"], snapshot["snapshot_key"])
        self.assertEqual(runtime["generated_at"], snapshot["generated_at"])
        self.assertEqual(runtime["automation"]["scheduled_slot"], snapshot["automation"]["scheduled_slot"])
        self.assertNotIn("unused", runtime["automation"])
        self.assertEqual(runtime["quote_health_by_market"]["hk"]["requested_count"], 200)
        self.assertEqual(runtime["global_decision"]["action"], "NO_VALID_PICK")
        self.assertEqual(runtime["global_decision"]["primary"]["code"], "MSFT")
        self.assertEqual(runtime["production_decision"]["primary"]["code"], "PFE")
        self.assertEqual(runtime["production_decision"]["qualified_candidates"][0]["code"], "PFE")
        self.assertEqual(runtime["source_snapshot"]["sha256"], hashlib.sha256(source_bytes).hexdigest())
        self.assertEqual(runtime["source_snapshot"]["byte_size"], len(source_bytes))
        encoded = json.dumps(runtime, ensure_ascii=False)
        for forbidden in (
            "candidate_snapshot",
            "evaluated_candidates",
            "production_rule_inputs",
            '"events"',
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertLess(len(encoded.encode()), len(source_bytes) // 10)

    def test_worker_ui_assets_are_identity_bound_bounded_and_split_by_tab(self) -> None:
        snapshot = runtime_snapshot_fixture()
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
        latest_summary = {
            "snapshot_key": snapshot["snapshot_key"],
            "generated_at": snapshot["generated_at"],
            "analysis_models": {"ten_day_return": {"status": "COLLECTING"}},
        }

        assets = build_worker_assets.build_worker_ui_assets(
            snapshot,
            latest_summary,
            source_bytes,
        )

        expected_identity = {
            "snapshot_key": snapshot["snapshot_key"],
            "generated_at": snapshot["generated_at"],
            "source_snapshot": {
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "byte_size": len(source_bytes),
            },
        }
        limits = {
            "ui-bootstrap.json": 192 * 1024,
            "ui-candidates.json": 768 * 1024,
            "ui-events.json": 512 * 1024,
        }
        self.assertEqual(set(assets), set(limits))
        for name, payload in assets.items():
            with self.subTest(name=name):
                for key, value in expected_identity.items():
                    self.assertEqual(payload[key], value)
                self.assertLessEqual(
                    len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()),
                    limits[name],
                )

        bootstrap = assets["ui-bootstrap.json"]
        encoded_bootstrap = json.dumps(bootstrap, ensure_ascii=False)
        for forbidden in (
            '"evaluated_candidates"',
            '"production_rule_inputs"',
            '"point_in_time_universe"',
            '"kline"',
            '"events"',
        ):
            self.assertNotIn(forbidden, encoded_bootstrap)
        self.assertEqual(bootstrap["production_decision"]["primary"]["code"], "PFE")
        self.assertEqual(bootstrap["production_decision"]["qualified_candidate_count"], 1)

        candidates = assets["ui-candidates.json"]
        self.assertEqual(candidates["contract_version"], "ui-candidates-v2")
        self.assertEqual(candidates["role_contract_version"], "candidate-role-v1")
        self.assertIn("PFE", {row["code"] for row in candidates["candidates"]})
        self.assertTrue(any(row.get("kline") for row in candidates["candidates"]))
        by_code = {row["code"]: row for row in candidates["candidates"]}
        self.assertEqual(by_code["PFE"]["decision_role"], "production_primary")
        self.assertEqual(
            by_code["PFE"]["decision_roles"],
            {"production": "PRIMARY", "legacy": "NONE", "research": "NONE"},
        )
        self.assertEqual(by_code["PFE"]["production_rank"], 1)
        self.assertEqual(by_code["0700.HK"]["decision_role"], "research_priority")
        self.assertEqual(by_code["0700.HK"]["decision_roles"]["legacy"], "PRIMARY")
        self.assertEqual(by_code["0700.HK"]["decision_roles"]["production"], "NONE")
        self.assertEqual(
            candidates["production_selection"],
            {
                "role_contract_version": "candidate-role-v1",
                "action": "QUALIFIED_PICK",
                "primary_candidate_id": by_code["PFE"]["id"],
                "qualified_candidate_ids": [by_code["PFE"]["id"]],
                "qualified_candidate_count": 1,
            },
        )
        events = assets["ui-events.json"]
        self.assertEqual(events["contract_version"], "ui-events-v2")
        self.assertEqual(len(events["events"]), len(snapshot["events"]))
        self.assertTrue(all(row["decision_bound"] is False for row in events["events"]))

    def test_worker_ui_events_keep_all_decision_evidence_and_trim_deterministically(self) -> None:
        snapshot = runtime_snapshot_fixture()
        bound_ids = ["evt-production", "evt-global-primary", "evt-global-research"]
        snapshot["production_decision"]["primary"]["verified_positive_event_ids"] = [bound_ids[0]]
        snapshot["production_decision"]["qualified_candidates"][0]["verified_positive_event_ids"] = [bound_ids[0]]
        snapshot["global_decision"]["primary"]["verified_positive_event_ids"] = [bound_ids[1]]
        snapshot["global_decision"]["research_priority"]["verified_positive_event_ids"] = [bound_ids[2]]
        snapshot["global_decision"]["automatic_external_evidence_count"] = 3

        def event(event_id: str, minute: int, *, padding: int = 0) -> dict:
            return {
                "event_id": event_id,
                "event_type": "announcement",
                "market": "us",
                "symbol": "PFE",
                "title": event_id,
                "source": "SEC",
                "url": f"https://example.test/{event_id}",
                "published_at": f"2026-08-26T08:{minute % 60:02d}:00+00:00",
                "effective_at": f"2026-08-26T09:{minute % 60:02d}:00+00:00",
                "decision_eligible": True,
                "ingestion_mode": "automatic",
                "evidence_status": "verified",
                "source_tier": "official",
                "direction": "positive",
                "padding": "x" * padding,
            }

        bound_events = [event(event_id, index) for index, event_id in enumerate(bound_ids)]
        filler = [event(f"evt-filler-{index:03d}", index, padding=6_000) for index in range(140)]
        snapshot["events"] = {
            "generated_at": snapshot["generated_at"],
            "stats": {"total": len(bound_events) + len(filler), "model_signals": 7, "automatic_external": 3},
            "items": [*reversed(filler), *reversed(bound_events)],
        }
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
        assets = build_worker_assets.build_worker_ui_assets(snapshot, {}, source_bytes)
        bootstrap = assets["ui-bootstrap.json"]
        events_payload = assets["ui-events.json"]
        published_items = events_payload["events"]["items"]
        published_ids = {item["event_id"] for item in published_items}

        self.assertEqual(bootstrap["decision_evidence"]["bound_event_ids"], sorted(bound_ids))
        self.assertEqual(
            {item["event_id"] for item in bootstrap["decision_evidence"]["items"]},
            set(bound_ids),
        )
        self.assertEqual(bootstrap["event_stats"]["total"], len(bound_events) + len(filler))
        self.assertEqual(bootstrap["event_stats"]["model_signals"], 7)
        self.assertTrue(set(bound_ids).issubset(published_ids))
        self.assertEqual(
            [item["event_id"] for item in published_items[:len(bound_ids)]],
            list(reversed(bound_ids)),
        )
        self.assertTrue(all(item["decision_bound"] is True for item in published_items[:len(bound_ids)]))
        self.assertTrue(all(item["decision_bound"] is False for item in published_items[len(bound_ids):]))
        self.assertEqual(events_payload["contract_version"], "ui-events-v2")
        self.assertEqual(
            events_payload["event_publication"]["ordering_contract_version"],
            "decision-bound-first-then-published-desc-v1",
        )
        self.assertEqual(
            events_payload["event_publication"]["decision_bound_event_ids"],
            sorted(bound_ids),
        )
        self.assertEqual(
            events_payload["event_publication"]["production_bound_event_ids"],
            [bound_ids[0]],
        )
        self.assertGreater(events_payload["event_publication"]["truncated"], 0)
        self.assertEqual(
            events_payload["event_publication"]["total"],
            events_payload["event_publication"]["published"]
            + events_payload["event_publication"]["truncated"],
        )
        self.assertLessEqual(
            len(json.dumps(events_payload, ensure_ascii=False, separators=(",", ":")).encode()),
            build_worker_assets.MAX_WORKER_UI_EVENTS_BYTES,
        )

        reordered = copy.deepcopy(snapshot)
        reordered["events"]["items"] = list(reversed(reordered["events"]["items"]))
        reordered_bytes = json.dumps(reordered, ensure_ascii=False, separators=(",", ":")).encode()
        reordered_payload = build_worker_assets.build_worker_ui_events(reordered, reordered_bytes)
        self.assertEqual(reordered_payload["events"], events_payload["events"])
        self.assertEqual(reordered_payload["event_publication"], events_payload["event_publication"])

    def test_worker_ui_assets_fail_closed_when_bound_event_is_missing(self) -> None:
        snapshot = runtime_snapshot_fixture()
        snapshot["global_decision"]["primary"]["verified_positive_event_ids"] = ["evt-missing"]
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
        with self.assertRaisesRegex(ValueError, "decision-bound event evidence is missing"):
            build_worker_assets.build_worker_ui_assets(snapshot, {}, source_bytes)

    def test_worker_ui_assets_fail_closed_when_bound_event_is_duplicated(self) -> None:
        snapshot = runtime_snapshot_fixture()
        event_id = "evt-duplicate"
        snapshot["global_decision"]["primary"]["verified_positive_event_ids"] = [event_id]
        snapshot["events"] = [
            {"event_id": event_id, "title": "first"},
            {"event_id": event_id, "title": "second"},
        ]
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
        with self.assertRaisesRegex(ValueError, "decision-bound event evidence is duplicated"):
            build_worker_assets.build_worker_ui_assets(snapshot, {}, source_bytes)

    def test_worker_live_index_collects_normalizes_and_deduplicates_visible_candidates(self) -> None:
        snapshot = runtime_snapshot_fixture()
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()

        live_index = build_worker_assets.build_worker_live_index(snapshot, source_bytes)

        self.assertEqual(live_index["contract_version"], "worker-live-index-v1")
        self.assertEqual(live_index["snapshot_key"], snapshot["snapshot_key"])
        self.assertEqual(live_index["generated_at"], snapshot["generated_at"])
        self.assertEqual(
            live_index["source_snapshot"],
            {
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "byte_size": len(source_bytes),
            },
        )
        self.assertEqual(
            live_index["contract_metadata"],
            {
                "candidate_limit": 90,
                "byte_size_limit": 512 * 1024,
                "code_normalization": "worker-facing-live-code-v1",
                "volume_units_by_market": {
                    "a_share": ["lot", "share", "shares"],
                    "hk": ["share", "shares"],
                    "us": ["share", "shares"],
                },
            },
        )
        candidates = live_index["candidates"]
        self.assertEqual(sorted(candidates), ["a_share", "hk", "us"])
        self.assertIn("600000", candidates["a_share"])
        self.assertIn("0700.HK", candidates["hk"])
        self.assertIn("BRK-B", candidates["us"])
        self.assertIn("MSFT", candidates["us"])
        self.assertIn("PFE", candidates["us"])
        self.assertEqual(live_index["candidate_count"], 5)
        self.assertEqual(live_index["market_candidate_counts"], {"a_share": 1, "hk": 1, "us": 3})
        hk = candidates["hk"]["0700.HK"]
        self.assertEqual(hk["code"], "0700.HK")
        self.assertEqual(hk["symbol"], "0700.HK")
        self.assertEqual(hk["currency"], "HKD")
        self.assertEqual(
            set(hk),
            set(build_worker_assets.LIVE_CANDIDATE_FIELDS),
        )
        self.assertNotIn("global_decision", live_index)
        self.assertNotIn("large_unused_payload", json.dumps(live_index))

    def test_worker_live_index_excludes_unsafe_quote_contracts(self) -> None:
        mutations = {
            "non_positive_price": ("price", 0),
            "naive_source_time": ("source_as_of", "2026-08-26T10:00:00"),
            "naive_fetch_time": ("fetched_at", "2026-08-26T10:00:10"),
            "wrong_volume_unit": ("volume_unit", "contracts"),
        }
        for label, (field, value) in mutations.items():
            with self.subTest(label=label):
                snapshot = runtime_snapshot_fixture()
                snapshot["markets"]["a_share"]["decision"]["blocked_candidate"]["realtime"][field] = value
                source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
                live_index = build_worker_assets.build_worker_live_index(snapshot, source_bytes)
                self.assertNotIn("600000", live_index["candidates"]["a_share"])
                self.assertEqual(live_index["excluded_candidate_count"], 1)
                self.assertEqual(live_index["excluded_candidates"][0]["identity"], "a_share:600000")
                for market, rows in live_index["candidates"].items():
                    for candidate in rows.values():
                        build_worker_assets.validate_live_candidate(candidate, market)

    def test_worker_live_code_normalization_matches_worker_facing_contract(self) -> None:
        cases = (
            ("a_share", "SH600000", "600000"),
            ("a_share", "SH.600000", "600000"),
            ("a_share", "600000.SH", "600000"),
            ("a_share", "SZ000001", "000001"),
            ("a_share", "SZ.000001", "000001"),
            ("a_share", "000001.SZ", "000001"),
            ("hk", "700.HK", "0700.HK"),
            ("hk", "00700.HK", "0700.HK"),
            ("us", "BRK_B", "BRK-B"),
            ("us", "BRK.B", "BRK-B"),
            ("us", "BRK-B", "BRK-B"),
        )
        for market, source, expected in cases:
            with self.subTest(market=market, source=source):
                self.assertEqual(build_worker_assets.normalize_live_code(source, market), expected)

    def test_worker_live_volume_units_match_worker_and_verifier_contract(self) -> None:
        expected = {
            "a_share": {"lot", "share", "shares"},
            "hk": {"share", "shares"},
            "us": {"share", "shares"},
        }
        self.assertEqual(build_worker_assets.LIVE_MARKET_VOLUME_UNITS, expected)
        for market, units in expected.items():
            code = {"a_share": "600000", "hk": "0700.HK", "us": "BRK_B"}[market]
            for unit in units:
                with self.subTest(market=market, unit=unit):
                    candidate = build_worker_assets.compact_live_candidate(
                        runtime_quote_candidate(code, market, volume_unit=unit),
                        market,
                    )
                    build_worker_assets.validate_live_candidate(candidate, market)
            with self.subTest(market=market, unit="contracts"):
                candidate = build_worker_assets.compact_live_candidate(
                    runtime_quote_candidate(code, market, volume_unit="contracts"),
                    market,
                )
                with self.assertRaisesRegex(ValueError, "volume_unit"):
                    build_worker_assets.validate_live_candidate(candidate, market)

    def test_worker_live_index_keeps_exact_candidate_boundary(self) -> None:
        snapshot = bounded_live_snapshot(90)
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()

        live_index = build_worker_assets.build_worker_live_index(snapshot, source_bytes)

        self.assertEqual(live_index["candidate_count"], 90)
        self.assertEqual(live_index["formal_qualified_candidate_count"], 90)
        self.assertEqual(len(live_index["candidates"]["us"]), 90)
        self.assertEqual(
            sorted(live_index["candidates"]["us"]),
            [f"Q{index:03d}" for index in range(90)],
        )

    def test_worker_live_index_rejects_more_than_90_formal_candidates(self) -> None:
        snapshot = bounded_live_snapshot(91)
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()

        with self.assertRaisesRegex(ValueError, "candidate limit.*91 > 90"):
            build_worker_assets.build_worker_live_index(snapshot, source_bytes)

    def test_worker_live_index_rejects_more_than_90_union_candidates(self) -> None:
        snapshot = bounded_live_snapshot(89, visible_count=2)
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()

        with self.assertRaisesRegex(ValueError, "candidate limit.*91 > 90"):
            build_worker_assets.build_worker_live_index(snapshot, source_bytes)

    def test_worker_live_index_never_silently_excludes_formal_qualified_candidate(self) -> None:
        snapshot = bounded_live_snapshot(1)
        snapshot["production_decision"]["qualified_candidates"][0]["candidate_snapshot"]["realtime"]["price"] = 0
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()

        with self.assertRaisesRegex(ValueError, "formal qualified candidate.*positive realtime price"):
            build_worker_assets.build_worker_live_index(snapshot, source_bytes)

    def test_worker_live_index_rejects_payload_over_byte_ceiling(self) -> None:
        snapshot = bounded_live_snapshot(1)
        candidate = snapshot["production_decision"]["qualified_candidates"][0]["candidate_snapshot"]
        candidate["kline"] = [
            {"date": "2026-08-25", "close": 10, "padding": "x" * 1024}
            for _ in range(600)
        ]
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()

        with self.assertRaisesRegex(ValueError, "byte-size limit"):
            build_worker_assets.build_worker_live_index(snapshot, source_bytes)

    def test_write_worker_runtime_assets_creates_both_bounded_documents(self) -> None:
        snapshot = runtime_snapshot_fixture()
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
        latest_summary = {"snapshot_key": snapshot["snapshot_key"], "generated_at": snapshot["generated_at"]}
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            build_worker_assets.write_worker_runtime_assets(
                snapshot,
                latest_summary,
                source_bytes,
                output,
            )
            runtime = json.loads((output / "runtime.json").read_text(encoding="utf-8"))
            live_index = json.loads((output / "live-index.json").read_text(encoding="utf-8"))

            ui_bootstrap = json.loads((output / "ui-bootstrap.json").read_text(encoding="utf-8"))
            ui_candidates = json.loads((output / "ui-candidates.json").read_text(encoding="utf-8"))
            ui_events = json.loads((output / "ui-events.json").read_text(encoding="utf-8"))

        self.assertEqual(runtime["snapshot_key"], snapshot["snapshot_key"])
        self.assertEqual(live_index["snapshot_key"], snapshot["snapshot_key"])
        self.assertEqual(live_index["source_snapshot"], runtime["source_snapshot"])
        self.assertEqual(ui_bootstrap["source_snapshot"], runtime["source_snapshot"])
        self.assertEqual(ui_candidates["source_snapshot"], runtime["source_snapshot"])
        self.assertEqual(ui_events["source_snapshot"], runtime["source_snapshot"])
        self.assertLess(len(json.dumps(runtime)), len(source_bytes) // 10)
        self.assertLess(len(json.dumps(live_index)), len(source_bytes) // 2)

    def test_data_manifest_splits_small_list_and_identity_bound_details(self) -> None:
        snapshot = runtime_snapshot_fixture()
        snapshot["feature_cutoff_at"] = "2026-08-26T10:00:00+08:00"
        snapshot["global_decision"]["event_coverage"] = {
            "candidate_total": 800,
            "negative_risk_scanned": 800,
            "positive_event_deep_scanned": 48,
            "by_market": {
                "a_share": {"candidate_total": 300, "negative_risk_scanned": 300},
                "hk": {"candidate_total": 200, "negative_risk_scanned": 200},
                "us": {"candidate_total": 300, "negative_risk_scanned": 300},
            },
        }
        snapshot["automation"].update(
            {
                "scheduled_slot": "2026-08-26T08:17:00+08:00",
                "scheduled_invocation_slot": "2026-08-26T10:17:00+08:00",
                "source_invocation_slot": "2026-08-26T08:17:00+08:00",
                "scheduler_delay_seconds": 7200,
                "recovery_mode": "late_cron_recovery",
                "scheduler_health": {
                    "contract_version": "scheduler-health-v1",
                    "source_invocation_slot": "2026-08-26T08:17:00+08:00",
                    "effective_checkpoint": "2026-08-26T08:17:00+08:00",
                    "effective_invocation_slot": "2026-08-26T10:17:00+08:00",
                    "scheduler_start_delay_seconds": 7200,
                    "recovery_mode": "late_cron_recovery",
                    "generation_started_at": "2026-08-26T10:17:02+08:00",
                },
            }
        )
        trade_plan = {
            "contract_version": "ten-day-trade-plan-v1",
            "status": "REVIEW_REQUIRED",
            "horizon_trade_days": 10,
            "reference_quote": {
                "price": 28.0,
                "currency": "USD",
                "source": "scheduled_snapshot",
                "source_as_of": "2026-08-26T10:00:00+08:00",
                "quote_status": "closed",
                "kind": "published_snapshot_quote",
            },
            "entry_zone": {"low": 27.72, "high": 28.14, "currency": "USD"},
            "entry_trade_date": "2026-08-26",
            "invalidation": {"price": 26.6, "currency": "USD", "source": "candidate_stop_loss"},
            "target": {"price": 30.8, "currency": "USD", "source": "candidate_take_profit_reference"},
            "position_limit": {
                "max_single_name_weight_pct": 10.0,
                "policy": "strategy_safety_cap_not_personalized",
            },
            "catalyst_expiry_date": None,
            "review_end_trade_date": "2026-09-09",
            "exit_rules": ["EXIT_IF_INVALIDATION_PRICE_BREACHED"],
            "is_personalized_advice": False,
        }
        snapshot["production_decision"]["primary"]["ten_day_trade_plan"] = copy.deepcopy(trade_plan)
        snapshot["production_decision"]["qualified_candidates"][0]["ten_day_trade_plan"] = copy.deepcopy(trade_plan)
        for row in (
            snapshot["production_decision"]["primary"],
            snapshot["production_decision"]["qualified_candidates"][0],
        ):
            row["qualification_track"] = "event_catalyst"
            row["event_candidate_scanned"] = True
            row["verified_positive_event_ids"] = ["event-1", "event-2"]
        snapshot["events"] = [
            {"event_id": "event-1"},
            {"event_id": "event-2"},
        ]
        source_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
        latest_summary = {
            "snapshot_key": snapshot["snapshot_key"],
            "generated_at": snapshot["generated_at"],
        }
        with tempfile.TemporaryDirectory() as directory:
            data_root = pathlib.Path(directory) / "data"
            picks = data_root / "picks"
            build_worker_assets.write_worker_runtime_assets(
                snapshot, latest_summary, source_bytes, picks
            )
            ui_assets = {
                name: json.loads((picks / name).read_text(encoding="utf-8"))
                for name in ("ui-bootstrap.json", "ui-candidates.json", "ui-events.json")
            }
            oversized_history_row = {
                "snapshot_key": snapshot["snapshot_key"],
                "analysis_models": {
                    "ten_day_excess_rank": {"diagnostics": "x" * 25_000},
                },
                "production_decision": {
                    "action": "QUALIFIED_PICK",
                    "qualified_candidate_count": 10,
                    "primary": {"code": "PFE", "qualification_score": 75.0},
                    "qualified_candidates": [
                        {"code": f"Q{index}", "evidence": "y" * 2_000}
                        for index in range(10)
                    ],
                },
            }
            manifest = build_worker_assets.build_data_manifest_assets(
                snapshot,
                source_bytes,
                ui_assets,
                {
                    "summaries": [oversized_history_row],
                    "history_evaluation": {},
                    "scheduler_checkpoint_ledger": (
                        build_worker_assets.scheduler_checkpoint_ledger.aggregate_receipts(
                            [],
                            evaluated_at="2026-08-26T10:30:00+08:00",
                        )
                    ),
                },
                data_root,
            )

            self.assertEqual(manifest["contract_version"], "data-manifest-v1")
            self.assertEqual(
                manifest["scheduler_health"]["source_invocation_slot"],
                "2026-08-26T08:17:00+08:00",
            )
            self.assertEqual(manifest["scheduler_health"]["scheduler_start_delay_seconds"], 7200)
            self.assertNotEqual(manifest["scheduler_health"]["scheduler_start_delay_seconds"], 0)
            self.assertEqual(manifest["scheduler_health"]["recovery_mode"], "late_cron_recovery")
            self.assertIsNone(manifest["scheduler_health"]["missed_checkpoints_24h"])
            self.assertEqual(
                manifest["scheduler_health"]["checkpoint_coverage_status"],
                "INITIALIZING_24H_LEDGER",
            )
            self.assertEqual(
                manifest["scheduler_health"]["checkpoint_evidence_contract_version"],
                "scheduler-checkpoint-ledger-v1",
            )
            self.assertFalse(manifest["scheduler_health"]["checkpoint_evidence_ready"])
            self.assertEqual(manifest["scheduler_health"]["scheduler_readiness"], "INITIALIZING")
            self.assertEqual(manifest["scheduler_health"]["publication_slo_seconds"], 2700)
            self.assertIsNone(manifest["scheduler_health"]["publication_within_slo"])
            self.assertLess(
                manifest["assets"]["summary"]["byte_size"],
                build_worker_assets.MAX_DATA_SUMMARY_BYTES,
            )
            self.assertLess(
                manifest["assets"]["candidates"]["byte_size"],
                build_worker_assets.MAX_DATA_CANDIDATE_LIST_BYTES,
            )
            candidate_list = json.loads((data_root / manifest["candidates_key"]).read_text())
            self.assertTrue(candidate_list["candidates"])
            self.assertEqual(
                candidate_list["evaluated_count"],
                snapshot["production_decision"]["evaluated_candidate_count"],
            )
            pfe_row = next(row for row in candidate_list["candidates"] if row["code"] == "PFE")
            self.assertTrue(pfe_row["qualification"]["event_candidate_scanned"])
            self.assertEqual(
                pfe_row["qualification"]["verified_positive_event_ids"],
                ["event-1", "event-2"],
            )
            history_list = json.loads((data_root / manifest["history_key"]).read_text())
            history_row = history_list["history"][0]
            self.assertNotIn("analysis_models", history_row)
            self.assertNotIn(
                "qualified_candidates", history_row["production_decision"]
            )
            self.assertEqual(history_row["production_decision"]["primary"]["code"], "PFE")
            self.assertEqual(
                history_row["production_decision"]["qualified_candidate_count"], 10
            )
            self.assertIn("analysis_models", oversized_history_row)
            self.assertIn(
                "qualified_candidates", oversized_history_row["production_decision"]
            )
            self.assertEqual(
                json.loads((data_root / manifest["summary_key"]).read_text())["feature_cutoff_at"],
                snapshot["feature_cutoff_at"],
            )
            runtime_payload = json.loads((data_root / manifest["runtime_key"]).read_text())
            self.assertEqual(
                runtime_payload["global_decision"]["event_coverage"],
                snapshot["global_decision"]["event_coverage"],
            )
            self.assertEqual(pfe_row["ten_day_trade_plan"], trade_plan)
            candidate_id = candidate_list["candidates"][0]["id"]
            detail = json.loads(
                (data_root / manifest["candidate_detail_keys"][candidate_id]).read_text()
            )
            self.assertEqual(detail["id"], candidate_id)
            self.assertEqual(detail["snapshot_key"], manifest["snapshot_key"])
            self.assertEqual(detail["source_snapshot"]["sha256"], manifest["snapshot_sha256"])


if __name__ == "__main__":
    unittest.main()

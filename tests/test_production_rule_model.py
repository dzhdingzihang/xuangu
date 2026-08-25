from __future__ import annotations

import copy
import math
import unittest

from production_rule_model import build_production_decision


def candidate(**overrides):
    row = {
        "market": "hk",
        "code": "0300.HK",
        "name": "美的集团",
        "legacy_signal": "BUY_CANDIDATE",
        "legacy_recommendation_degree": 65,
        "v2_rank": 12,
        "v2_rank_universe_size": 197,
        "rule_priority_score": 70,
        "priority_components": {"data_quality": 20.0},
        "event_candidate_scanned": True,
        "verified_positive_event_ids": ["evt-1", "evt-2"],
        "estimated_10d_range": {"low_pct": -4.1, "high_pct": 5.8},
        "entry_price": 80.0,
        "calendar_id": "XHKG",
        "calendar_version": "test-v1",
        "entry_trade_date": "2026-08-26",
        "forecast_end_trade_date": "2026-09-08",
        "blocker_codes": ["TEN_DAY_MODEL_NOT_READY", "TEN_DAY_PREDICTION_MISSING"],
        "probability": 0.99,
        "expected_net_utility": 0.12,
        "shadow_model": {"probability": 0.88},
    }
    row.update(overrides)
    return row


def snapshot(*rows):
    pool = []
    for row in rows:
        pool.append({
            "code": row["code"],
            "name": row["name"],
            "recommendation_degree": row.get("legacy_recommendation_degree"),
            "legacy_complete": "LEGACY_DEEP_SCORE_MISSING" not in row.get("blocker_codes", []),
            "data_quality": {"score": 100, "inputs": [{"required": True, "state": "fresh"}]},
            "decision_gates": [{"status": "PASS"}],
            "estimated_10d_range": row.get("estimated_10d_range"),
            "realtime": {"current_price": row.get("entry_price"), "quote_status": "LAST_CLOSE"},
        })
    return {
        "generated_at": "2026-08-25T22:13:45+08:00",
        "signal_date": "2026-08-25",
        "target_date": "2026-08-25",
        "automation": {"scheduled_slot": "2026-08-25T22:47:00+08:00"},
        "markets": {"hk": {"_candidate_pool": pool, "decision": {"action": "BUY_CANDIDATE"}}},
        "global_decision": {
            "contract_version": "global-10d-v1",
            "action": "NO_VALID_PICK",
            "evaluated_candidates": list(rows),
        },
    }


class ProductionRuleModelTests(unittest.TestCase):
    def test_emits_independent_rule_candidate_without_probability_claims(self):
        source = snapshot(candidate())
        before = copy.deepcopy(source["global_decision"])

        decision = build_production_decision(source)

        self.assertEqual(source["global_decision"], before)
        self.assertEqual(decision["contract_version"], "production-rule-10d-v1")
        self.assertEqual(decision["action"], "QUALIFIED_PICK")
        self.assertEqual(decision["score_kind"], "RULE_QUALIFICATION_SCORE")
        self.assertEqual(decision["qualified_candidate_count"], 1)
        primary = decision["primary"]
        self.assertEqual(primary["code"], "0300.HK")
        self.assertEqual(primary["probability"], None)
        self.assertEqual(primary["expected_net_utility"], None)
        self.assertFalse(primary["calibrated"])
        self.assertTrue(primary["qualification_id"].startswith("qual_"))
        self.assertTrue(primary["candidate_snapshot"]["rule_qualified"])
        self.assertEqual(primary["risk_reward"]["ratio"], 1.41)

    def test_keeps_non_model_blockers_and_real_negative_utility_blocker(self):
        row = candidate(blocker_codes=[
            "TEN_DAY_MODEL_NOT_READY",
            "TEN_DAY_PREDICTION_MISSING",
            "NON_POSITIVE_EXPECTED_NET_UTILITY",
            "MATERIAL_NEGATIVE_EVENT",
        ])

        decision = build_production_decision(snapshot(row))

        evaluated = decision["evaluated_candidates"][0]
        self.assertEqual(decision["action"], "NO_QUALIFIED_PICK")
        self.assertIn("NON_POSITIVE_EXPECTED_NET_UTILITY", evaluated["blocker_codes"])
        self.assertIn("MATERIAL_NEGATIVE_EVENT", evaluated["blocker_codes"])
        self.assertNotIn("TEN_DAY_MODEL_NOT_READY", evaluated["blocker_codes"])
        self.assertNotIn("TEN_DAY_PREDICTION_MISSING", evaluated["blocker_codes"])

    def test_market_level_legacy_action_is_diagnostic_not_a_candidate_gate(self):
        evaluated = build_production_decision(snapshot(candidate(legacy_signal="NO_TRADE")))["evaluated_candidates"][0]

        self.assertEqual(evaluated["status"], "QUALIFIED")
        self.assertEqual(evaluated["legacy_signal"], "NO_TRADE")
        self.assertNotIn("LEGACY_BUY_SIGNAL_REQUIRED", evaluated["blocker_codes"])

    def test_market_specific_thresholds_and_required_rule_gates_fail_closed(self):
        cases = {
            "hk_recommendation": (candidate(legacy_recommendation_degree=62.99), "LEGACY_RECOMMENDATION_BELOW_THRESHOLD"),
            "v2_top_twenty": (candidate(v2_rank=40), "V2_TOP_PERCENTILE_REQUIRED"),
            "event_scan": (candidate(event_candidate_scanned=False), "EVENT_CANDIDATE_NOT_SCANNED"),
            "positive_event": (candidate(verified_positive_event_ids=[]), "VERIFIED_POSITIVE_EVENT_MISSING"),
            "upside": (candidate(estimated_10d_range={"low_pct": -3.0, "high_pct": 4.99}), "TEN_DAY_UPSIDE_BELOW_THRESHOLD"),
            "downside": (candidate(estimated_10d_range={"low_pct": -8.01, "high_pct": 12.0}), "TEN_DAY_DOWNSIDE_ABOVE_LIMIT"),
            "risk_reward": (candidate(estimated_10d_range={"low_pct": -5.0, "high_pct": 5.9}), "RISK_REWARD_BELOW_THRESHOLD"),
            "range_missing": (candidate(estimated_10d_range={"low_pct": None, "high_pct": 8.0}), "TEN_DAY_RANGE_INVALID"),
        }
        for label, (row, blocker) in cases.items():
            with self.subTest(label=label):
                evaluated = build_production_decision(snapshot(row))["evaluated_candidates"][0]
                self.assertEqual(evaluated["status"], "REJECTED")
                self.assertIn(blocker, evaluated["blocker_codes"])

    def test_market_isolation_does_not_copy_global_cross_market_blockers(self):
        source = snapshot(candidate())
        source["global_decision"]["blocker_codes"] = ["MARKET_COVERAGE_INCOMPLETE"]
        source["global_decision"]["market_states"] = {
            "a_share": {"state": "READY"},
            "hk": {"state": "READY"},
            "us": {"state": "DEGRADED"},
        }

        decision = build_production_decision(source)

        self.assertEqual(decision["action"], "QUALIFIED_PICK")
        self.assertEqual(decision["primary"]["market"], "hk")

    def test_qualified_rows_rank_by_rule_score_then_stable_identity(self):
        lower = candidate(code="LOW.HK", name="Lower", legacy_recommendation_degree=64)
        higher = candidate(code="HIGH.HK", name="Higher", legacy_recommendation_degree=80)
        same_a = candidate(code="AAA.HK", name="Same A")
        same_b = candidate(code="BBB.HK", name="Same B")

        decision = build_production_decision(snapshot(lower, same_b, higher, same_a))

        self.assertEqual(decision["primary"]["code"], "HIGH.HK")
        same_codes = [item["code"] for item in decision["qualified_candidates"] if item["code"] in {"AAA.HK", "BBB.HK"}]
        self.assertEqual(same_codes, ["AAA.HK", "BBB.HK"])

    def test_non_finite_inputs_are_rejected_and_retry_id_is_stable(self):
        for value in (math.nan, math.inf, -math.inf, True, "65"):
            with self.subTest(value=value):
                row = candidate(legacy_recommendation_degree=value)
                evaluated = build_production_decision(snapshot(row))["evaluated_candidates"][0]
                self.assertIn("LEGACY_RECOMMENDATION_INVALID", evaluated["blocker_codes"])
        first = build_production_decision(snapshot(candidate()))["primary"]["qualification_id"]
        retry = snapshot(candidate())
        retry["generated_at"] = "2026-08-25T23:05:00+08:00"
        second = build_production_decision(retry)["primary"]["qualification_id"]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

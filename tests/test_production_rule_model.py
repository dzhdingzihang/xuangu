from __future__ import annotations

import copy
import json
import math
import unittest

from production_rule_model import build_production_decision, build_production_rule_inputs


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
    markets = {}
    for row in rows:
        market = row["market"]
        section = markets.setdefault(
            market,
            {"_candidate_pool": [], "decision": {"action": "BUY_CANDIDATE"}},
        )
        section["_candidate_pool"].append({
            "code": row["code"],
            "name": row["name"],
            "recommendation_degree": row.get("legacy_recommendation_degree"),
            "legacy_complete": "LEGACY_DEEP_SCORE_MISSING" not in row.get("blocker_codes", []),
            "data_quality": {
                "score": row.get("source_data_quality", 100),
                "inputs": [{"required": True, "state": "fresh"}],
            },
            "decision_gates": [{"status": "PASS"}],
            "estimated_10d_range": row.get("estimated_10d_range"),
            "realtime": {"current_price": row.get("entry_price"), "quote_status": "LAST_CLOSE"},
        })
    return {
        "generated_at": "2026-08-25T22:13:45+08:00",
        "signal_date": "2026-08-25",
        "target_date": "2026-08-25",
        "automation": {"scheduled_slot": "2026-08-25T22:47:00+08:00"},
        "markets": markets,
        "global_decision": {
            "contract_version": "global-10d-v1",
            "action": "NO_VALID_PICK",
            "evaluated_candidates": list(rows),
        },
    }


class ProductionRuleModelTests(unittest.TestCase):
    def test_frozen_minimal_inputs_rebuild_exactly_after_pool_removal_and_json_roundtrip(self):
        accepted = candidate(
            market="us",
            code="VZ",
            name="Verizon",
            legacy_recommendation_degree=75,
            v2_rank=1,
            v2_rank_universe_size=100,
            verified_positive_event_ids=[],
            estimated_10d_range={"low_pct": -4.0, "high_pct": 8.0},
            blocker_codes=["VERIFIED_POSITIVE_EVENT_MISSING"],
        )
        rejected = candidate(
            market="us",
            code="BLOCKED",
            name="Blocked",
            blocker_codes=["MATERIAL_NEGATIVE_EVENT"],
        )
        source = snapshot(accepted, rejected)

        inputs = build_production_rule_inputs(source)
        source["production_rule_inputs"] = inputs
        decision = build_production_decision(source)

        self.assertEqual(inputs["contract_version"], "production-rule-inputs-v1")
        self.assertEqual(inputs["evaluated_candidate_count"], 2)
        self.assertRegex(inputs["ledger_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            [(row["input_index"], row["market"], row["code"]) for row in inputs["rows"]],
            [(0, "us", "VZ"), (1, "us", "BLOCKED")],
        )
        self.assertIn("candidate_snapshot", inputs["rows"][0])
        self.assertNotIn("candidate_snapshot", inputs["rows"][1])
        self.assertEqual(inputs["rows"][0]["legacy_recommendation_degree"], 75)
        self.assertEqual(inputs["rows"][0]["blocker_codes"], ["VERIFIED_POSITIVE_EVENT_MISSING"])
        self.assertEqual(decision["source_rule_inputs_sha256"], inputs["ledger_sha256"])

        for section in source["markets"].values():
            section.pop("_candidate_pool", None)
        published = json.loads(json.dumps(source, ensure_ascii=False, allow_nan=False))
        self.assertEqual(build_production_decision(published), decision)

    def test_full_300_200_300_input_identity_ledger_stays_bounded(self):
        rows = []
        for index in range(300):
            rows.append(candidate(
                market="a_share",
                code=f"{600000 + index:06d}",
                name=f"A{index}",
                blocker_codes=[] if index == 0 else ["MATERIAL_NEGATIVE_EVENT"],
            ))
        for index in range(200):
            rows.append(candidate(
                market="hk",
                code=f"{index + 1:04d}.HK",
                name=f"H{index}",
                blocker_codes=["MATERIAL_NEGATIVE_EVENT"],
            ))
        for index in range(300):
            rows.append(candidate(
                market="us",
                code=f"US{index:03d}",
                name=f"U{index}",
                blocker_codes=["MATERIAL_NEGATIVE_EVENT"],
            ))
        source = snapshot(*rows)

        inputs = build_production_rule_inputs(source)

        identities = [(entry["market"], entry["code"]) for entry in inputs["rows"]]
        self.assertEqual(inputs["evaluated_candidate_count"], 800)
        self.assertEqual(len(identities), 800)
        self.assertEqual(len(set(identities)), 800)
        self.assertEqual(sum("candidate_snapshot" in entry for entry in inputs["rows"]), 1)
        self.assertLess(
            len(json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))),
            512 * 1024,
        )

    def test_emits_independent_rule_candidate_without_probability_claims(self):
        source = snapshot(candidate())
        before = copy.deepcopy(source["global_decision"])

        decision = build_production_decision(source)

        self.assertEqual(source["global_decision"], before)
        self.assertEqual(decision["contract_version"], "production-rule-10d-v1")
        self.assertEqual(decision["action_basis"], "dual_track_candidate_qualification_v3")
        self.assertEqual(decision["rule_model_id"], "ten-day-audited-rule-ensemble-v3")
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
        self.assertEqual(primary["qualification_score"], 83.39)
        self.assertEqual(primary["qualification_track"], "event_catalyst")
        self.assertEqual(
            [item["track"] for item in primary["track_evaluations"]],
            ["event_catalyst", "quality_technical"],
        )
        self.assertEqual(primary["track_evaluations"][0]["status"], "PASS")

    def test_publishes_exact_dual_track_policy(self):
        policy = build_production_decision(snapshot(candidate()))["policy"]

        self.assertEqual(
            policy["tracks"]["event_catalyst"]["market_thresholds"],
            {
                "a_share": {"minimum_legacy": 64.0, "maximum_downside": 8.0, "minimum_upside": 5.0},
                "hk": {"minimum_legacy": 63.0, "maximum_downside": 8.0, "minimum_upside": 5.0},
                "us": {"minimum_legacy": 64.0, "maximum_downside": 10.0, "minimum_upside": 6.0},
            },
        )
        quality = policy["tracks"]["quality_technical"]
        self.assertEqual(
            quality["market_thresholds"],
            {
                "a_share": {"minimum_legacy": 66.0, "maximum_downside": 6.0, "minimum_upside": 6.0},
                "hk": {"minimum_legacy": 67.0, "maximum_downside": 6.0, "minimum_upside": 6.0},
                "us": {"minimum_legacy": 68.0, "maximum_downside": 7.5, "minimum_upside": 6.5},
            },
        )
        self.assertEqual(quality["maximum_v2_rank_fraction"], 0.10)
        self.assertEqual(quality["minimum_data_quality"], 95.0)
        self.assertEqual(quality["minimum_risk_reward_ratio"], 1.50)
        self.assertEqual(quality["minimum_qualification_score"], 72.0)

    def test_quality_technical_track_can_qualify_without_positive_event(self):
        row = candidate(
            market="us",
            code="VZ",
            name="Verizon",
            legacy_recommendation_degree=71,
            v2_rank=7,
            v2_rank_universe_size=299,
            verified_positive_event_ids=[],
            estimated_10d_range={"low_pct": -4.2, "high_pct": 7.3},
            blocker_codes=["TEN_DAY_MODEL_NOT_READY", "VERIFIED_POSITIVE_EVENT_MISSING"],
        )

        decision = build_production_decision(snapshot(row))

        self.assertEqual(decision["action"], "QUALIFIED_PICK")
        primary = decision["primary"]
        self.assertEqual(primary["qualification_track"], "quality_technical")
        self.assertEqual(primary["verified_positive_event_ids"], [])
        self.assertEqual(primary["blocker_codes"], [])
        self.assertEqual(
            [(item["track"], item["status"]) for item in primary["track_evaluations"]],
            [("event_catalyst", "FAIL"), ("quality_technical", "PASS")],
        )
        self.assertIn(
            "VERIFIED_POSITIVE_EVENT_MISSING",
            primary["track_evaluations"][0]["blocker_codes"],
        )
        self.assertNotIn(
            "VERIFIED_POSITIVE_EVENT_MISSING",
            primary["track_evaluations"][1]["blocker_codes"],
        )

    def test_quality_technical_track_has_stricter_non_event_gates(self):
        cases = {
            "legacy": ({"legacy_recommendation_degree": 67.99}, "QUALITY_LEGACY_BELOW_THRESHOLD"),
            "rank": ({"v2_rank": 31}, "QUALITY_V2_TOP_DECILE_REQUIRED"),
            "quality": ({"source_data_quality": 94.99}, "QUALITY_DATA_QUALITY_BELOW_THRESHOLD"),
            "upside": ({"estimated_10d_range": {"low_pct": -4.0, "high_pct": 6.49}}, "QUALITY_TEN_DAY_UPSIDE_BELOW_THRESHOLD"),
            "downside": ({"estimated_10d_range": {"low_pct": -7.51, "high_pct": 12.0}}, "QUALITY_TEN_DAY_DOWNSIDE_ABOVE_LIMIT"),
            "ratio": ({"estimated_10d_range": {"low_pct": -5.0, "high_pct": 7.0}}, "QUALITY_RISK_REWARD_BELOW_THRESHOLD"),
            "score": ({
                "legacy_recommendation_degree": 68,
                "v2_rank": 29,
                "priority_components": {"data_quality": 19.0},
                "estimated_10d_range": {"low_pct": -4.4, "high_pct": 6.6},
            }, "QUALITY_QUALIFICATION_SCORE_BELOW_THRESHOLD"),
        }
        for label, (overrides, blocker) in cases.items():
            with self.subTest(label=label):
                values = {
                    "market": "us",
                    "code": f"{label.upper()}.US",
                    "name": label,
                    "legacy_recommendation_degree": 71,
                    "v2_rank": 7,
                    "v2_rank_universe_size": 299,
                    "verified_positive_event_ids": [],
                    "estimated_10d_range": {"low_pct": -4.2, "high_pct": 7.3},
                    "blocker_codes": ["VERIFIED_POSITIVE_EVENT_MISSING"],
                }
                values.update(overrides)
                row = candidate(**values)
                evaluated = build_production_decision(snapshot(row))["evaluated_candidates"][0]

                self.assertEqual(evaluated["status"], "REJECTED")
                quality_track = next(
                    item for item in evaluated["track_evaluations"]
                    if item["track"] == "quality_technical"
                )
                self.assertEqual(quality_track["status"], "FAIL")
                self.assertIn(blocker, quality_track["blocker_codes"])
                self.assertIn(blocker, evaluated["blocker_codes"])

    def test_quality_track_cannot_bypass_shared_safety_blockers(self):
        for blocker in (
            "POOL_COVERAGE_INCOMPLETE",
            "DATA_SOURCE_UNKNOWN",
            "MATERIAL_NEGATIVE_EVENT",
            "NON_POSITIVE_EXPECTED_NET_UTILITY",
            "EVENT_CANDIDATE_NOT_SCANNED",
        ):
            with self.subTest(blocker=blocker):
                row = candidate(
                    market="us",
                    code="SAFE.US",
                    name="Safe",
                    legacy_recommendation_degree=75,
                    v2_rank=1,
                    v2_rank_universe_size=299,
                    event_candidate_scanned=blocker != "EVENT_CANDIDATE_NOT_SCANNED",
                    verified_positive_event_ids=[],
                    estimated_10d_range={"low_pct": -4.0, "high_pct": 8.0},
                    blocker_codes=["VERIFIED_POSITIVE_EVENT_MISSING", blocker],
                )

                evaluated = build_production_decision(snapshot(row))["evaluated_candidates"][0]

                self.assertEqual(evaluated["status"], "REJECTED")
                for track in evaluated["track_evaluations"]:
                    self.assertEqual(track["status"], "FAIL")
                    self.assertIn(blocker, track["blocker_codes"])

    def test_event_catalyst_wins_when_both_tracks_pass(self):
        row = candidate(
            legacy_recommendation_degree=75,
            v2_rank=5,
            estimated_10d_range={"low_pct": -4.0, "high_pct": 8.0},
        )

        primary = build_production_decision(snapshot(row))["primary"]

        self.assertEqual(primary["qualification_track"], "event_catalyst")
        self.assertEqual(
            [item["status"] for item in primary["track_evaluations"]],
            ["PASS", "PASS"],
        )

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

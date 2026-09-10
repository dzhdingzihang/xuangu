from __future__ import annotations

import copy
import unittest

import return_opportunity as opportunity
from test_return_opportunity import CUTOFF, build, candidate


class OpportunityEntryObjectiveTests(unittest.TestCase):
    def test_audited_extended_leader_has_recomputable_wait_assessment(self):
        metrics = {"return_5d_pct": 31.163, "return_10d_pct": 41.235,
                   "distance_ma20_pct": 32.998, "daily_volatility_pct": 3.762}
        assessment = opportunity.entry_assessment(metrics)
        self.assertEqual(assessment["status"], "WAIT_FOR_PULLBACK")
        self.assertEqual(assessment["chase_risk"], "HIGH")
        self.assertEqual(assessment["penalty_points"], 24)
        self.assertFalse(assessment["execution_ready"])
        self.assertIn("TEN_DAY_RETURN_EXTENDED", assessment["reason_codes"])
        self.assertIn("MA20_DISTANCE_EXTENDED", assessment["reason_codes"])

    def test_earlier_continuation_can_outrank_already_extended_spike(self):
        result = build([candidate("SPIKE", drift=3.5, noise=3.8),
                        candidate("EARLIER", drift=0.9, noise=0.9), candidate("SLOW", drift=.2)])
        self.assertEqual(result["score_version"], "return-opportunity-score-v3")
        self.assertEqual(result["primary"]["code"], "EARLIER")
        spike = next(row for row in result["candidates"] if row["code"] == "SPIKE")
        self.assertEqual(spike["qualification_status"], "RESEARCH_ELIGIBLE")
        self.assertEqual(spike["entry_assessment"]["status"], "WAIT_FOR_PULLBACK")
        self.assertGreater(spike["evidence_score"], spike["opportunity_score"])
        self.assertEqual(result["entry_policy"]["timing"], "NEXT_SESSION_OPEN_REVIEW")
        self.assertFalse(result["entry_policy"]["automatic_execution"])
        for row in result["candidates"]:
            self.assertIsNone(row["expected_net_return"])
            self.assertIsNone(row["probability"])
            self.assertFalse(row["production_eligible"])
        self.assertEqual(opportunity.validate_return_opportunities(result), [])

    def test_volatility_itself_and_sector_names_do_not_trigger_chase_penalty(self):
        low = {"return_5d_pct": 7, "return_10d_pct": 12, "distance_ma20_pct": 8,
               "daily_volatility_pct": 1}
        high = {**low, "daily_volatility_pct": 7, "sector": "Technology"}
        self.assertEqual(opportunity.entry_assessment(low), opportunity.entry_assessment(high))
        self.assertEqual(opportunity.entry_assessment(high)["penalty_points"], 0)

    def test_entry_contract_cannot_forge_penalty_status_or_execution(self):
        original = build([candidate("SPIKE", drift=3.5, noise=3.8)])
        for mutate in (
            lambda b: b["candidates"][0]["entry_assessment"].update(penalty_points=0),
            lambda b: b["candidates"][0]["entry_assessment"].update(status="CONDITIONAL_REVIEW"),
            lambda b: b["candidates"][0]["entry_assessment"].update(execution_ready=True),
            lambda b: b["candidates"][0]["entry_assessment"].update(reason_codes=[]),
            lambda b: b["candidates"][0]["entry_assessment"].update(execution_ready=0),
            lambda b: b["candidates"][0].update(evidence_score=99),
            lambda b: b["candidates"][0]["security_classification"].update(verified=True),
            lambda b: b["entry_policy"].update(timing="BUY_NOW"),
            lambda b: b["selection_policy"].update(minimum_evidence_score=0),
        ):
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(original)
                mutate(changed)
                self.assertTrue(opportunity.validate_return_opportunities(changed))

    def test_known_leveraged_product_is_excluded_before_any_ranking(self):
        row = candidate("SKUU", drift=1.2)
        row["english_name"] = "GRANITESHARES 2X LONG SK HYNIX"
        board = build([row])
        self.assertEqual(board["eligible_count"], 0)
        excluded = board["excluded_candidates"][0]
        self.assertIn("SECURITY_TYPE_EXCLUDED", excluded["qualification_blockers"])
        self.assertEqual(excluded["security_classification"]["status"], "EXCLUDED")

    def test_unknown_security_type_remains_explicit_not_verified_common_stock(self):
        board = build([candidate("UNKNOWN")])
        row = board["primary"]
        self.assertEqual(row["security_classification"]["status"], "UNVERIFIED")
        self.assertFalse(row["security_classification"]["verified"])
        self.assertIn("SECURITY_TYPE_UNVERIFIED", row["risk_flags"])

    def test_bound_provider_etf_cannot_hide_behind_ordinary_stock_display_name(self):
        row = candidate("ETFCASE")
        row["security_type_evidence"] = [{"symbol": "ETFCASE", "source": "yahoo_chart_meta",
            "field": "instrumentType", "raw_value": "ETF", "retrieved_at": CUTOFF}]
        board = build([row])
        self.assertEqual(board["eligible_count"], 0)
        self.assertIn("SECURITY_TYPE_EXCLUDED", board["excluded_candidates"][0]["qualification_blockers"])

    def test_declared_unknown_cannot_overwrite_frozen_source_etf_evidence(self):
        board = build([candidate("ORDINARY")])
        row = board["candidates"][0]
        row["candidate_snapshot"]["security_type_evidence"] = [{"symbol": "ORDINARY", "source": "yahoo_chart_meta",
            "field": "instrumentType", "raw_value": "ETF", "retrieved_at": CUTOFF}]
        board["primary"] = copy.deepcopy(row)
        self.assertTrue(opportunity.validate_return_opportunities(board))

    def test_fresh_positive_provider_identity_is_bound_to_snapshot_cutoff(self):
        row = candidate("COMMON")
        row["security_as_of"] = "2029-01-01T00:00:00Z"
        row["security_type_evidence"] = [{"symbol": "COMMON", "source": "yahoo_chart_meta",
            "field": "instrumentType", "raw_value": "EQUITY", "retrieved_at": CUTOFF}]
        board = build([row])
        self.assertTrue(board["primary"]["security_classification"]["verified"])
        self.assertEqual(board["primary"]["security_classification"]["freshness_reference_at"], CUTOFF)
        self.assertEqual(opportunity.validate_return_opportunities(board), [])

    def test_existing_v1_v2_boards_are_not_reinterpreted_with_entry_penalty(self):
        for version in (None, "return-opportunity-score-v1", "return-opportunity-score-v2"):
            board = build([candidate("LEGACY")])
            board["score_version"] = version
            board.pop("entry_policy")
            for row in board["candidates"]:
                row["score_version"] = version
                row.pop("entry_assessment")
                row.pop("evidence_score")
            board["primary"] = copy.deepcopy(board["candidates"][0])
            self.assertEqual(opportunity.validate_return_opportunities(board), [])


if __name__ == "__main__":
    unittest.main()

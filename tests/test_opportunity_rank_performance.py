from __future__ import annotations

import copy
import unittest

import opportunity_outcome_ledger as ledger
from test_opportunity_outcome_ledger import MATURE, PUBLICATION, loader, pending, snapshot
from test_return_opportunity import CUTOFF, build, candidate
import market_calendar


def four_stock_snapshot(key="2026-08-21_2026-08-20_230000.json", version="return-opportunity-score-v2"):
    source = snapshot(key, version=version)
    board = source["return_opportunities"]
    prototype = board["candidates"][0]
    board["candidates"] = [{**copy.deepcopy(prototype), "code": code, "name": code,
                             "rank": rank, "opportunity_score": 81-rank}
                            for code, rank in zip(("AAA", "BBB", "CCC", "DDD"), (1, 2, 3, 6))]
    board.update(primary=board["candidates"][0], eligible_count=4)
    return source


def differing_returns(market, code):
    rows, source, adjusted = loader(market, code)
    ret = {"AAA": .12, "BBB": -.09, "CCC": .03, "DDD": .40, "SPY": .01}[code]
    for row in rows:
        row.update(open=100, high=max(100, 100*(1+ret))+1,
                   low=min(100, 100*(1+ret))-1, close=100*(1+ret))
    return rows, source, adjusted


class OpportunityRankPerformanceTests(unittest.TestCase):
    def test_empty_and_unmatured_board_never_claim_return_skill(self):
        for batches in ({}, {"a": pending(four_stock_snapshot())}):
            summary = ledger.evaluate_opportunity_performance(batches)
            self.assertEqual(summary["settled_count"], 0)
            self.assertFalse(summary["authorizes_production"])
            for value in summary["ranking_evaluation"]["groups"].values():
                self.assertIsNone(value["mean_net_return"])
                self.assertIsNone(value["mean_net_excess_return"])
                self.assertIsNone(value["expected_shortfall_10pct"])

    def test_original_global_top1_top3_and_board_use_absolute_net_return_first(self):
        a = ledger.settle_opportunity_batch(pending(four_stock_snapshot()), MATURE, differing_returns)
        summary = ledger.evaluate_opportunity_performance({"a": a})
        evaluation = summary["by_version"][0]["ranking_evaluation"]
        self.assertEqual(evaluation["primary_metric"], "mean_net_return")
        groups = evaluation["groups"]
        self.assertAlmostEqual(groups["top1"]["mean_net_return"], .1185)
        self.assertAlmostEqual(groups["top3"]["mean_net_return"], .0185)
        self.assertAlmostEqual(groups["board"]["mean_net_return"], .1135)
        self.assertAlmostEqual(groups["top1"]["mean_net_excess_return"], .11)
        self.assertEqual(groups["top1"]["complete_cohort_count"], 1)
        self.assertIsNone(groups["top1"]["expected_shortfall_10pct"])
        self.assertEqual(groups["top1"]["tail_sample_count"], 1)

    def test_entire_frozen_board_must_settle_even_if_top1_has_price(self):
        def partial(market, code):
            return ([], "", False) if code == "DDD" else differing_returns(market, code)
        a = ledger.settle_opportunity_batch(pending(four_stock_snapshot()), MATURE, partial)
        summary = ledger.evaluate_opportunity_performance({"a": a})
        for group in summary["ranking_evaluation"]["groups"].values():
            self.assertEqual(group["complete_cohort_count"], 0)
            self.assertEqual(group["pending_cohort_count"], 1)
            self.assertIsNone(group["mean_net_return"])

    def test_top3_requires_three_real_members(self):
        a = ledger.settle_opportunity_batch(pending(), MATURE, loader)
        groups = ledger.evaluate_opportunity_performance({"a": a})["ranking_evaluation"]["groups"]
        self.assertEqual(groups["top3"]["insufficient_member_cohort_count"], 1)
        self.assertIsNone(groups["top3"]["mean_net_return"])
        self.assertIsNotNone(groups["top1"]["mean_net_return"])

    def test_first_published_board_is_frozen_before_inspecting_winners(self):
        original = four_stock_snapshot()
        changed = four_stock_snapshot("2026-08-21_2026-08-20_230100.json")
        rows = changed["return_opportunities"]["candidates"]
        rows[0]["code"], rows[-1]["code"] = rows[-1]["code"], rows[0]["code"]
        a = ledger.settle_opportunity_batch(pending(original), MATURE, differing_returns)
        b = ledger.settle_opportunity_batch(pending(changed, publication="2026-08-21T13:29:01Z"), MATURE, differing_returns)
        groups = ledger.evaluate_opportunity_performance({"later": b, "first": a})["ranking_evaluation"]["groups"]
        self.assertEqual(groups["top1"]["duplicate_publication_count"], 1)
        self.assertEqual(groups["top1"]["complete_cohort_count"], 1)
        self.assertAlmostEqual(groups["top1"]["mean_net_return"], .1185)

    def test_versions_do_not_pool_global_top_n_performance(self):
        batches = {version: ledger.settle_opportunity_batch(pending(four_stock_snapshot(
            "2026-08-21_2026-08-20_23000" + str(index) + ".json", version)), MATURE, differing_returns)
            for index, version in enumerate(("return-opportunity-score-v1", "return-opportunity-score-v2"))}
        summary = ledger.evaluate_opportunity_performance(batches)
        self.assertEqual(summary["ranking_evaluation"]["status"], "BY_VERSION_ONLY")
        self.assertIsNone(summary["ranking_evaluation"]["groups"]["top1"]["mean_net_return"])
        for version in summary["by_version"]:
            self.assertAlmostEqual(version["ranking_evaluation"]["groups"]["top1"]["mean_net_return"], .1185)

    def test_different_publication_days_same_entry_session_are_not_extra_trades(self):
        def broad(market, code):
            dates = market_calendar.session_dates(market, "2026-08-21", "2026-09-09")
            return ([{"date": day.isoformat(), "open": 100, "high": 102, "low": 99, "close": 101}
                     for day in dates], "fixture-adjusted", True)
        a = ledger.settle_opportunity_batch(pending(four_stock_snapshot(), publication="2026-08-21T13:31:00Z"), MATURE, broad)
        b = ledger.settle_opportunity_batch(pending(four_stock_snapshot("2026-08-22_2026-08-20_230000.json"),
            publication="2026-08-22T13:31:00Z"), MATURE, broad)
        groups = ledger.evaluate_opportunity_performance({"a": a, "b": b})["ranking_evaluation"]["groups"]
        for group in groups.values():
            self.assertEqual(group["complete_cohort_count"], 1)
            self.assertEqual(group["duplicate_publication_count"], 1)
            self.assertEqual(group["non_overlapping_cohort_count"], 1)

    def test_v3_below_sixty_entry_priority_can_register_without_changing_old_rules(self):
        source = snapshot("2026-09-09_2026-09-09_202100.json")
        source.update(generated_at=CUTOFF, feature_cutoff_at=CUTOFF)
        source["return_opportunities"] = build([candidate("SPIKE", drift=3.5, noise=3.8)])
        board = source["return_opportunities"]
        self.assertLess(board["primary"]["opportunity_score"], 60)
        batch = pending(source, publication="2026-09-09T12:22:00Z")
        prediction = batch["predictions"][0]
        self.assertEqual(prediction["entry_assessment"], board["primary"]["entry_assessment"])
        self.assertEqual(prediction["evidence_score"], board["primary"]["evidence_score"])
        self.assertEqual(ledger.validate_prediction_sequence(batch["predictions"]), batch["predictions"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

import history_evaluation
import rule_outcome_ledger
from tests.test_rule_outcome_ledger import price_loader, rule_snapshot


class RuleHistoryEvaluationTests(unittest.TestCase):
    def test_partial_date_market_cell_is_excluded_and_never_ready(self) -> None:
        def partial_loader(market: str, code: str):
            if code == "000001":
                return ([], "missing-adjusted-price", True)
            return price_loader(market, code)

        batch = rule_outcome_ledger.settle_rule_snapshot(
            rule_snapshot(),
            "2026-09-10T00:00:00Z",
            partial_loader,
            benchmark_price_loader=price_loader,
        )

        result = history_evaluation.evaluate_rule_outcome_performance(
            {batch["snapshot_key"]: batch}
        )

        self.assertEqual(result["status"], "PARTIAL_DATA")
        self.assertEqual(result["settled_count"], 1)
        self.assertEqual(result["metric_eligible_settled_count"], 0)
        self.assertEqual(result["incomplete_date_market_cell_count"], 1)
        self.assertEqual(result["data_incomplete_date_market_cell_count"], 1)
        self.assertEqual(result["all_qualified"]["sample_count"], 0)

    def test_rule_track_reports_primary_all_market_and_track_without_probability_claim(self) -> None:
        batch = rule_outcome_ledger.settle_rule_snapshot(
            rule_snapshot(),
            "2026-09-10T00:00:00Z",
            price_loader,
            benchmark_price_loader=price_loader,
        )

        result = history_evaluation.evaluate_rule_outcome_performance(
            {batch["snapshot_key"]: batch}
        )

        self.assertEqual(result["prediction_count"], 2)
        self.assertEqual(result["settled_count"], 2)
        self.assertEqual(result["primary_picks"]["sample_count"], 1)
        self.assertEqual(result["all_qualified"]["sample_count"], 2)
        self.assertEqual(result["per_market"]["a_share"]["sample_count"], 2)
        self.assertEqual(
            result["per_qualification_track"]["quality_technical"]["sample_count"],
            2,
        )
        self.assertFalse(result["included_in_calibrated_probability_statistics"])
        self.assertFalse(result["authorizes_production"])

    def test_history_contract_exposes_empty_rule_track_without_fabricated_metrics(self) -> None:
        result = history_evaluation.build_history_evaluation([])
        tracking = result["rule_outcome_tracking"]
        self.assertEqual(tracking["status"], "NO_SAMPLE")
        self.assertIsNone(
            tracking["all_qualified"]["metrics"]["mean_net_return"]["value"]
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import pathlib
import unittest

import server
from tests.test_selector_v2 import fixture_candidate


def quote_fixture(
    code: str = "000001",
    *,
    pe_ttm: float | None = 5.4,
    pb: float | None = 0.55,
    total_mcap_yi: float | None = 1750,
    price: float = 11.32,
    change_pct: float = 0.8,
    amount_wan: float = 128000,
) -> dict:
    return {
        "code": code,
        "name": f"测试公司{code}",
        "price": price,
        "change_pct": change_pct,
        "amount_wan": amount_wan,
        "amount_wan_raw": amount_wan,
        "turnover_pct": 0.72,
        "vol_ratio": 0.94,
        "fundamentals": {
            "pe_ttm": pe_ttm,
            "pb": pb,
            "total_mcap_yi": total_mcap_yi,
        },
        "realtime": {"source_as_of": "2026-08-22T14:59:58+08:00"},
    }


class DualLowAnalysisTests(unittest.TestCase):
    def test_input_uses_required_units_and_preserves_missing(self) -> None:
        row = server.dual_low_input_from_quote(quote_fixture())
        self.assertEqual(row["amount"], 1_280_000_000)
        self.assertEqual(row["totalMarketCap"], 175_000_000_000)
        self.assertEqual(row["changePct"], 0.8)
        self.assertEqual(row["peRatio"], 5.4)

        missing = server.dual_low_input_from_quote(quote_fixture(pe_ttm=None))
        self.assertIsNone(missing["peRatio"])

    def test_bridge_returns_ranked_rejected_and_batch_metadata(self) -> None:
        quotes = [
            quote_fixture("000001", pe_ttm=5.4, pb=0.55, total_mcap_yi=1750),
            quote_fixture("000002", pe_ttm=10.2, pb=1.10, total_mcap_yi=900, change_pct=-1.2),
            quote_fixture("000003", pe_ttm=21.0, pb=1.50, total_mcap_yi=600),
        ]
        result = server.run_dual_low_analysis(quotes)
        self.assertEqual(result["metadata"]["model_id"], "dsa-screening-score-v1")
        self.assertEqual(result["metadata"]["input_count"], 3)
        self.assertEqual(result["metadata"]["input_profile"], "quote_valuation_core_v1")
        self.assertEqual(result["metadata"]["score_as_of"], "2026-08-22T14:59:58+08:00")
        self.assertTrue(result["metadata"]["top_ranked"])
        self.assertEqual(result["by_code"]["000001"]["status"], "ranked")
        self.assertEqual(result["by_code"]["000003"]["status"], "rejected")
        self.assertIn("value", result["by_code"]["000001"]["factor_scores"])
        self.assertTrue(result["by_code"]["000003"]["filter_reasons"])

    def test_missing_fundamental_is_rejected_as_data_missing_not_zero(self) -> None:
        result = server.run_dual_low_analysis([quote_fixture(pe_ttm=None)])
        analysis = result["by_code"]["000001"]
        self.assertEqual(analysis["status"], "rejected")
        self.assertIn("peRatio", analysis["missing_fields"])
        self.assertIn("validation.peRatio.invalid", {item["code"] for item in analysis["filter_reasons"]})
        self.assertIsNone(analysis["risk_penalty"])
        self.assertIsNone(analysis["portfolio_penalty"])

    def test_market_applicability_is_explicit(self) -> None:
        hk = server.dual_low_unavailable("hk", "MARKET_STRATEGY_NOT_CONFIGURED")
        self.assertEqual(hk["status"], "not_applicable")
        self.assertEqual(hk["reason_code"], "MARKET_STRATEGY_NOT_CONFIGURED")
        a_share = server.dual_low_unavailable("a_share", "MODEL_EXECUTION_FAILED")
        self.assertEqual(a_share["status"], "unavailable")
        self.assertIsNone(hk["final_score"])
        self.assertIsNone(hk["rank"])

    def test_batch_is_deterministic_and_score_arithmetic_is_exposed(self) -> None:
        quotes = [
            quote_fixture("000001", pe_ttm=5.4, pb=0.55, total_mcap_yi=1750),
            quote_fixture("000002", pe_ttm=10.2, pb=1.10, total_mcap_yi=900, change_pct=-1.2),
        ]
        first = server.run_dual_low_analysis(quotes)
        second = server.run_dual_low_analysis(copy.deepcopy(quotes))
        self.assertEqual(first, second)
        ranks = sorted(item["rank"] for item in first["by_code"].values())
        self.assertEqual(ranks, [1, 2])
        for analysis in first["by_code"].values():
            self.assertAlmostEqual(sum(analysis["contributions"].values()), analysis["base_score"], places=2)
            self.assertAlmostEqual(
                max(0, analysis["blended_score"] - analysis["risk_penalty"] - analysis["portfolio_penalty"]),
                analysis["final_score"],
                places=2,
            )

    def test_bridge_failure_degrades_without_raising(self) -> None:
        original = server.DUAL_LOW_BRIDGE
        try:
            server.DUAL_LOW_BRIDGE = pathlib.Path("/definitely/not/a/dual-low-bridge.mjs")
            result = server.run_dual_low_analysis([quote_fixture()])
        finally:
            server.DUAL_LOW_BRIDGE = original
        self.assertEqual(result["metadata"]["status"], "unavailable")
        self.assertEqual(result["by_code"]["000001"]["status"], "unavailable")

    def test_vendored_notice_license_target_exists(self) -> None:
        target = server.ROOT / "vendor" / "stock-scoring-kit" / "LICENSES" / "Apache-2.0-AlphaSift.txt"
        self.assertTrue(target.is_file())

    def test_overlay_does_not_change_legacy_or_v2(self) -> None:
        candidate = fixture_candidate()
        server.attach_candidate_v2(candidate, "a_share", {"risk": "normal"})
        before = copy.deepcopy(
            {
                "score": candidate["score"],
                "recommendation_degree": candidate["recommendation_degree"],
                "v2": candidate["v2"],
            }
        )
        analysis = {
            "status": "ranked",
            "model_id": "dsa-screening-score-v1",
            "final_score": 72.5,
            "rank": 2,
            "rank_universe_size": 18,
        }
        server.attach_dual_low_analysis(candidate, analysis, "a_share")
        self.assertEqual(candidate["score"], before["score"])
        self.assertEqual(candidate["recommendation_degree"], before["recommendation_degree"])
        self.assertEqual(candidate["v2"], before["v2"])
        self.assertEqual(candidate["analysis_projects"]["dual_low"]["final_score"], 72.5)
        self.assertNotIn("dual_low", candidate["v2"]["factor_groups"])


if __name__ == "__main__":
    unittest.main()

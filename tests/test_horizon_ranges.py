from __future__ import annotations

import unittest

import server
from tests.test_selector_v2 import fixture_candidate, fixture_kline


class HorizonRangeTests(unittest.TestCase):
    def test_two_and_ten_session_ranges_are_independent(self) -> None:
        rows = fixture_kline(40)
        two = server.estimate_horizon_range(rows, "a_share", 2, confidence=72, risk_count=0)
        ten = server.estimate_horizon_range(rows, "a_share", 10, confidence=72, risk_count=0)

        self.assertEqual(two["horizon_trade_days"], 2)
        self.assertEqual(ten["horizon_trade_days"], 10)
        self.assertEqual(two["method_id"], "realized-vol-drift-shadow-v1")
        self.assertFalse(two["calibrated"])
        self.assertLess(two["low_pct"], 0)
        self.assertGreater(two["high_pct"], 0)
        self.assertNotEqual((two["low_pct"], two["high_pct"]), (ten["low_pct"], ten["high_pct"]))
        self.assertGreater(ten["high_pct"] - ten["low_pct"], two["high_pct"] - two["low_pct"])

    def test_candidate_enrichment_publishes_canonical_ten_day_range(self) -> None:
        candidate = fixture_candidate()
        server.attach_candidate_v2(candidate, "a_share", {"risk": "normal"})

        self.assertEqual(candidate["estimated_2d_range"]["horizon_trade_days"], 2)
        self.assertEqual(candidate["estimated_10d_range"]["horizon_trade_days"], 10)
        self.assertEqual(candidate["estimated_2w_range"], candidate["estimated_10d_range"])
        self.assertIsNot(candidate["estimated_2w_range"], candidate["estimated_10d_range"])


if __name__ == "__main__":
    unittest.main()

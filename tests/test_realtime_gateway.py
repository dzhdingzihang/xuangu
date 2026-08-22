from __future__ import annotations

import datetime as dt
import unittest

from scripts.realtime_gateway import (
    GatewayError,
    normalize_request_symbol,
    quote_from_row,
)


class RealtimeGatewayTests(unittest.TestCase):
    def test_symbol_mapping_is_explicit_and_bounded(self) -> None:
        self.assertEqual(normalize_request_symbol("a_share:600519"), ("a_share", "600519", "SH.600519"))
        self.assertEqual(normalize_request_symbol("hk:941.hk"), ("hk", "00941.HK", "HK.00941"))
        self.assertEqual(normalize_request_symbol("us:brk-b"), ("us", "BRK-B", "US.BRK-B"))
        with self.assertRaises(GatewayError):
            normalize_request_symbol("600519")
        with self.assertRaises(GatewayError):
            normalize_request_symbol("us:../../secret")

    def test_active_fresh_quote_is_marked_realtime(self) -> None:
        fetched = dt.datetime(2026, 8, 21, 14, 0, 45, tzinfo=dt.timezone.utc)
        quote = quote_from_row(
            {
                "code": "US.NVDA",
                "last_price": 181.2,
                "prev_close_price": 180,
                "update_time": "2026-08-21 10:00:01",
                "volume": 123,
            },
            "us",
            "NVDA",
            {"market_us": "MORNING"},
            fetched,
        )
        self.assertEqual(quote["quote_status"], "REALTIME")
        self.assertEqual(quote["session"], "regular")
        self.assertTrue(quote["is_realtime"])
        self.assertAlmostEqual(quote["change_pct"], 0.6667)

    def test_closed_price_is_never_claimed_realtime(self) -> None:
        fetched = dt.datetime(2026, 8, 22, 2, 0, tzinfo=dt.timezone.utc)
        quote = quote_from_row(
            {
                "code": "SH.600519",
                "last_price": 1510.0,
                "prev_close_price": 1500.0,
                "update_time": "2026-08-21 15:00:00",
            },
            "a_share",
            "600519",
            {"market_sh": "CLOSED", "market_sz": "CLOSED"},
            fetched,
        )
        self.assertEqual(quote["quote_status"], "LAST_CLOSE")
        self.assertEqual(quote["price_kind"], "last_close")
        self.assertFalse(quote["is_realtime"])

    def test_post_market_prefers_session_price(self) -> None:
        fetched = dt.datetime(2026, 8, 21, 21, 0, 30, tzinfo=dt.timezone.utc)
        quote = quote_from_row(
            {
                "code": "US.NTNX",
                "last_price": 67.5,
                "after_price": 68.1,
                "prev_close_price": 66.0,
                "update_time": "2026-08-21 17:00:00",
            },
            "us",
            "NTNX",
            {"market_us": "AFTER_HOURS_BEGIN"},
            fetched,
        )
        self.assertEqual(quote["session"], "post")
        self.assertEqual(quote["price"], 68.1)
        self.assertEqual(quote["price_kind"], "after_hours")

    def test_ended_after_hours_is_a_last_close_not_live_session(self) -> None:
        fetched = dt.datetime(2026, 8, 22, 9, 0, tzinfo=dt.timezone.utc)
        quote = quote_from_row(
            {
                "code": "US.AAPL",
                "last_price": 310.0,
                "after_price": 309.5,
                "prev_close_price": 311.0,
                "update_time": "2026-08-21 19:59:59",
            },
            "us",
            "AAPL",
            {"market_us": "AFTER_HOURS_END"},
            fetched,
        )
        self.assertEqual(quote["session"], "closed")
        self.assertEqual(quote["quote_status"], "LAST_CLOSE")
        self.assertEqual(quote["price"], 309.5)
        self.assertEqual(quote["price_kind"], "after_hours_close")
        self.assertFalse(quote["is_stale"])


if __name__ == "__main__":
    unittest.main()

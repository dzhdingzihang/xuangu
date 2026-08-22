from __future__ import annotations

import datetime as dt
import unittest
from zoneinfo import ZoneInfo

import market_calendar


class MarketCalendarTests(unittest.TestCase):
    def test_entry_is_first_regular_open_strictly_after_decision_time(self) -> None:
        shanghai = ZoneInfo("Asia/Shanghai")
        windows = market_calendar.market_trade_windows(
            dt.datetime(2026, 8, 24, 9, 58, tzinfo=shanghai),
            horizon_sessions=10,
        )

        self.assertEqual(windows["a_share"]["entry_trade_date"], "2026-08-25")
        self.assertEqual(windows["hk"]["entry_trade_date"], "2026-08-25")
        self.assertEqual(windows["us"]["entry_trade_date"], "2026-08-24")
        self.assertGreater(
            dt.datetime.fromisoformat(windows["us"]["entry_session_open_at"]),
            dt.datetime.fromisoformat(windows["us"]["decision_time"]),
        )

    def test_weekend_and_exact_open_boundaries_have_no_lookahead(self) -> None:
        shanghai = ZoneInfo("Asia/Shanghai")
        weekend = market_calendar.market_trade_windows(dt.datetime(2026, 8, 22, 12, 0, tzinfo=shanghai))
        self.assertEqual(
            {window["entry_trade_date"] for window in weekend.values()},
            {"2026-08-24"},
        )

        exact_us_open = market_calendar.market_trade_window(
            "us",
            dt.datetime(2026, 8, 24, 21, 30, tzinfo=shanghai),
        )
        self.assertEqual(exact_us_open["entry_trade_date"], "2026-08-25")

    def test_exchange_specific_holidays_do_not_fall_back_to_weekdays(self) -> None:
        self.assertFalse(market_calendar.is_market_session("a_share", "2026-10-01"))
        self.assertEqual(market_calendar.next_session("a_share", "2026-10-01"), dt.date(2026, 10, 8))
        self.assertFalse(market_calendar.is_market_session("hk", "2026-07-01"))
        self.assertEqual(market_calendar.next_session("hk", "2026-07-01"), dt.date(2026, 7, 2))

    def test_nyse_labor_day_is_not_a_session(self) -> None:
        self.assertFalse(market_calendar.is_market_session("us", dt.date(2026, 9, 7)))
        self.assertEqual(
            market_calendar.session_on_or_after("us", dt.date(2026, 9, 7)),
            dt.date(2026, 9, 8),
        )

    def test_ten_session_window_uses_each_exchange_calendar(self) -> None:
        windows = market_calendar.market_trade_windows(dt.date(2026, 9, 7), horizon_sessions=10)

        self.assertEqual(windows["a_share"]["calendar_id"], "XSHG")
        self.assertEqual(windows["hk"]["calendar_id"], "XHKG")
        self.assertEqual(windows["us"]["calendar_id"], "XNYS")
        self.assertEqual(windows["us"]["entry_trade_date"], "2026-09-08")
        self.assertNotEqual(
            windows["us"]["entry_trade_date"],
            windows["us"]["forecast_end_trade_date"],
        )
        for market, window in windows.items():
            sessions = market_calendar.sessions_in_window(
                market,
                dt.date.fromisoformat(window["entry_trade_date"]),
                dt.date.fromisoformat(window["forecast_end_trade_date"]),
            )
            self.assertEqual(len(sessions), 10)


if __name__ == "__main__":
    unittest.main()

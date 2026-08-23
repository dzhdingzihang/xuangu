from __future__ import annotations

import datetime as dt
import json
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import server


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def yahoo_payload(*, include_adjusted: bool = True) -> dict:
    timestamp = int(
        dt.datetime(2026, 8, 20, 16, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()
    )
    indicators = {
        "quote": [
            {
                "open": [100.0],
                "high": [110.0],
                "low": [90.0],
                "close": [100.0],
                "volume": [1_000_000],
            }
        ]
    }
    if include_adjusted:
        indicators["adjclose"] = [{"adjclose": [50.0]}]
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [timestamp],
                    "meta": {"exchangeTimezoneName": "America/New_York"},
                    "indicators": indicators,
                }
            ]
        }
    }


class YahooAdjustedKlineTests(unittest.TestCase):
    def test_yahoo_daily_ohlc_uses_adjusted_close_factor(self) -> None:
        captured_url = []

        def open_fixture(request, timeout):
            captured_url.append(request.full_url)
            self.assertEqual(timeout, 6)
            return FakeResponse(yahoo_payload())

        with mock.patch.object(server.urllib.request, "urlopen", side_effect=open_fixture):
            rows = server.yahoo_chart_kline("TEST", 10)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-08-20")
        self.assertEqual(rows[0]["open"], 50.0)
        self.assertEqual(rows[0]["high"], 55.0)
        self.assertEqual(rows[0]["low"], 45.0)
        self.assertEqual(rows[0]["close"], 50.0)
        self.assertEqual(rows[0]["adjustment_factor"], 0.5)
        self.assertEqual(rows[0]["price_adjustment"], "yahoo_adjclose_factor_v1")
        self.assertIn("events=div%2Csplits", captured_url[0])

    def test_missing_adjusted_close_fails_closed_for_total_return_label(self) -> None:
        with mock.patch.object(
            server.urllib.request,
            "urlopen",
            return_value=FakeResponse(yahoo_payload(include_adjusted=False)),
        ):
            self.assertEqual(server.yahoo_chart_kline("TEST", 10), [])


if __name__ == "__main__":
    unittest.main()

import datetime as dt
import unittest
from unittest import mock

import server
from tests.test_selector_v2 import eastmoney_hk_fixture_row, eastmoney_page_response, fixture_kline


class DynamicInputRecoveryTests(unittest.TestCase):
    def test_live_quote_freshness_uses_finished_clock_after_seven_minute_retry(self):
        start = dt.datetime.fromisoformat("2026-09-10T22:00:00+08:00")
        finished = start + dt.timedelta(minutes=7)
        clock = {"now": start}
        bars = fixture_kline(40)
        bars[-1] = {**bars[-1], "date": "2026-09-10"}
        def fetch_quotes(_symbols):
            clock["now"] = finished
            return {"TEST": {"price": 10, "change_pct": 1, "session": "regular", "session_label": "盘中", "source": "Yahoo 1m includePrePost", "source_as_of": finished.isoformat(), "fetched_at": finished.isoformat()}}
        candidate = {"symbol": "TEST", "name": "Test Company", "themes": [], "lens": {}}
        with mock.patch.object(server, "now_cn", side_effect=lambda: clock["now"]), mock.patch.object(server, "yahoo_realtime_quotes", side_effect=fetch_quotes), mock.patch.object(server, "yahoo_kline_map", return_value={"TEST": bars}), mock.patch.object(server, "cached_market_kline", return_value=[]):
            live = server.score_serenity_candidates("us", [dict(candidate)])
            self.assertEqual(live["quote_health"]["realtime_count"], 1)
            clock["now"] = start
            frozen = server.score_serenity_candidates("us", [dict(candidate)], as_of=start)
            self.assertEqual(frozen["quote_health"]["realtime_count"], 0)
            self.assertEqual(live["candidates"][0]["realtime"]["source_as_of"], finished.isoformat())

    def test_discovery_budget_stops_new_network_requests_without_claiming_completeness(self):
        import itertools
        with mock.patch.object(server.time, "monotonic", side_effect=itertools.chain([0], itertools.repeat(100))), mock.patch.object(server, "market_data_get_with_retry") as network:
            _rows, coverage = server._fetch_eastmoney_dynamic_rows("us")
        network.assert_not_called()
        self.assertFalse(coverage["discovery_pagination_complete"])
        self.assertTrue(coverage["discovery_budget_exhausted"])
        self.assertEqual(coverage["discovery_budget_seconds"], 75)

    def test_live_discovery_uses_completion_clock_but_explicit_asof_stays_frozen(self):
        start = dt.datetime.fromisoformat("2026-09-10T22:00:00+08:00")
        finished = start + dt.timedelta(minutes=7)
        rows = [{"symbol": f"T{index:04}", "name": f"Company {index}", "source": "fixture", "observed_at": finished.isoformat(), "recall_routes": ["liquidity"], "recall_metrics": {"amount": 50_000_000 + index, "price": 10, "source_timestamp": int(finished.timestamp())}} for index in range(320)]
        discovery = {"discovery_pagination_complete": True, "discovery_requested_pages": 10, "discovery_completed_pages": 10, "raw_discovery_size": 320}
        with mock.patch.object(server, "now_cn", return_value=finished), mock.patch.object(server, "_us_security_directory", return_value={}), mock.patch.object(server, "_fetch_eastmoney_dynamic_rows", return_value=(rows, discovery)), mock.patch.object(server, "_fetch_sina_us_dynamic_rows", return_value=([], {})) as fallback, mock.patch.object(server, "_load_dynamic_market_cache", return_value=None), mock.patch.object(server, "_save_dynamic_market_cache"):
            _selected, live = server.load_dynamic_market_pool("us")
            self.assertEqual(live["selected_source_fresh_count"], 300)
            self.assertFalse(fallback.called)
            _selected, frozen = server.load_dynamic_market_pool("us", as_of=start)
            self.assertEqual(frozen["selected_source_fresh_count"], 0)

    def test_selector_does_not_share_pre_hk_anchor_with_later_us_calls(self):
        import inspect
        source = inspect.getsource(server.run_selector)
        self.assertNotIn("hk_us_as_of", source)
        self.assertIn('load_dynamic_market_pool("us")', source)
        self.assertIn('score_serenity_candidates("us", us_universe)', source)

    def test_observed_hk_ipo_is_removed_before_final_200_selection(self):
        anchor = "2026-09-10T21:43:59+08:00"
        rows = [{"symbol": f"{index:04}.HK", "name": f"Company {index}", "source": "eastmoney_delay_hk_market", "observed_at": anchor, "recall_routes": ["liquidity"], "recall_metrics": {"price": 10, "amount": 50_000_000 + index, "listing_date": 20000101}} for index in range(1, 211)]
        rows.append({**rows[0], "symbol": "9976.HK", "name": "江波龙", "recall_metrics": {"price": 212.6, "amount": 271406272, "listing_date": 20260908}})
        selected, coverage = server.select_dynamic_market_pool(rows, "hk")
        self.assertEqual(len(selected), 200)
        self.assertNotIn("9976.HK", [row["symbol"] for row in selected])
        self.assertEqual(coverage["admission_exclusions"][0]["reason"], "INSUFFICIENT_LISTED_HISTORY")

    def test_listing_unknown_is_not_falsely_claimed_old_or_new(self):
        eligibility = server._listing_history_eligibility({"symbol": "0001.HK", "observed_at": "2026-09-10T21:43:59+08:00", "recall_metrics": {}}, "hk")
        self.assertEqual(eligibility["status"], "UNKNOWN")

    def test_us_expands_bounded_liquidity_pages_when_two_pages_insufficient(self):
        now = dt.datetime.fromisoformat("2026-09-10T22:00:00+08:00")
        stamp = int(now.timestamp())
        calls = []
        def fetch(*args, **kwargs):
            params = kwargs["params"]
            page = int(params["pn"])
            calls.append(page)
            rows = [{"f12": f"T{number:04}", "f13": 105, "f14": f"Company {number}", "f124": stamp, "f2": 20, "f3": 1, "f5": 2_000_000, "f6": 40_000_000, "f20": 2_000_000_000} for number in range(page * 100, page * 100 + 100)]
            return eastmoney_page_response(rows)
        with mock.patch.object(server, "now_cn", return_value=now), mock.patch.object(server, "market_data_get_with_retry", side_effect=fetch):
            rows, coverage = server._fetch_eastmoney_dynamic_rows("us")
        self.assertGreaterEqual(len({row["symbol"] for row in rows}), 315)
        self.assertTrue(coverage["discovery_pagination_complete"])
        self.assertEqual(coverage["discovery_scan_scope"], "bounded_route_pages")
        self.assertFalse(coverage["discovery_full_exchange_scan"])
        self.assertGreater(max(calls), 2)

    def test_independent_hk_qfq_parser_preserves_adjustment_and_symbol(self):
        payload = {"data": {"hk00668": {"qfqday": [["2026-09-09", "126", "126.1", "129", "123", "220800"], ["2026-09-10", "126.1", "124", "127.5", "122.2", "220800"]]}}}
        rows = server._parse_tencent_hk_daily(payload, "0668.HK", 90)
        self.assertEqual(rows[-1]["date"], "2026-09-10")
        self.assertEqual(rows[-1]["price_adjustment"], "tencent_hk_qfqday")
        self.assertEqual(server._parse_tencent_hk_daily(payload, "3308.HK", 90), [])
        self.assertEqual(server._parse_tencent_hk_daily({"data": {"hk00668": {"day": payload["data"]["hk00668"]["qfqday"]}}}, "0668.HK", 90), [])

    def test_fallback_parser_rejects_invalid_or_duplicate_ohlc_dates(self):
        bad = [["2026-09-10", "100", "124", "99", "122.2", "220800"]]
        self.assertEqual(server._parse_tencent_hk_daily({"data": {"hk00668": {"qfqday": bad}}}, "0668.HK", 90), [])

    def test_sina_time_only_or_missing_clock_is_never_fabricated_from_fetch_time(self):
        item = {"symbol": "TEST", "name": "Test Company", "price": 10, "volume": 3_000_000, "mktcap": 2_000_000_000, "chg": 1, "market": "NASDAQ"}
        for value in (None, "09:43:59"):
            candidate, reason = server._dynamic_us_candidate({**item, "ticktime": value}, "liquidity", "2026-09-10T22:00:00+08:00")
            self.assertIsNone(reason)
            self.assertIsNone(candidate["recall_metrics"]["source_timestamp"])
        candidate, _ = server._dynamic_us_candidate({**item, "ticktime": "2026-09-10 09:43:59"}, "liquidity", "2026-09-10T22:00:00+08:00")
        self.assertEqual(candidate["recall_metrics"]["source_timestamp"], int(dt.datetime.fromisoformat("2026-09-10T09:43:59-04:00").timestamp()))

    def test_fresh_replacements_are_chosen_before_higher_scored_unknown_clock(self):
        now = dt.datetime.fromisoformat("2026-09-10T22:00:00+08:00")
        rows = [{"symbol": f"T{index:04}", "name": f"Company {index}", "source": "fixture", "observed_at": now.isoformat(), "recall_routes": ["liquidity"], "recall_metrics": {"amount": 50_000_000 + index, "source_timestamp": int(now.timestamp())}} for index in range(320)]
        rows.append({**rows[0], "symbol": "MISS", "recall_metrics": {"amount": 9_000_000_000}})
        selected, coverage = server._select_fresh_dynamic_pool(rows, "us", as_of=now)
        self.assertEqual(len(selected), 300)
        self.assertNotIn("MISS", [row["symbol"] for row in selected])
        self.assertEqual(coverage["discovery_stale_excluded_symbols"], ["MISS"])

    def test_complete_quote_bundle_moves_together_when_fresher_provider_is_merged(self):
        old = {"symbol": "TEST", "source": "old", "name": "Test", "recall_metrics": {"price": 10, "amount": 100, "source_timestamp": 1789052400, "listing_date": 20260901, "listing_date_source": "eastmoney_delay_market"}}
        newer = {"symbol": "TEST", "source": "new", "name": "Test", "recall_metrics": {"price": 12, "amount": 120, "source_timestamp": 1789052500}}
        merged = server._merge_dynamic_market_rows([old, newer], "us")[0]
        self.assertEqual(merged["source"], "new")
        self.assertEqual(merged["recall_metrics"]["price"], 12)
        self.assertEqual(merged["recall_metrics"]["listing_date"], 20260901)

    def test_failed_base_page_is_retried_without_refetching_successful_pages(self):
        now = dt.datetime.fromisoformat("2026-09-10T22:00:00+08:00")
        calls = {}
        def fetch(*args, **kwargs):
            params = kwargs["params"]
            key = (params["fid"], params["po"], params["pn"])
            calls[key] = calls.get(key, 0) + 1
            if key == ("f6", "1", 1) and calls[key] == 1:
                raise ValueError("transient incomplete provider payload")
            first = (int(params["pn"]) - 1) * 100 + 1
            return eastmoney_page_response([eastmoney_hk_fixture_row(number, int(now.timestamp())) for number in range(first, first + 100)])
        with mock.patch.object(server, "now_cn", return_value=now), mock.patch.object(server, "market_data_get_with_retry", side_effect=fetch):
            _rows, coverage = server._fetch_eastmoney_dynamic_rows("hk")
        self.assertTrue(coverage["discovery_pagination_complete"])
        self.assertEqual(coverage["discovery_retried_pages"], 1)
        self.assertEqual(calls[("f6", "1", 1)], 2)
        self.assertEqual(calls[("f10", "1", 1)], 1)


if __name__ == "__main__":
    unittest.main()

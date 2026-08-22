from __future__ import annotations

import copy
import datetime as dt
import re
import tempfile
import unittest
import urllib.error
from unittest import mock

import requests
import server


def fixture_kline(count: int = 40) -> list[dict]:
    start = dt.date(2026, 6, 1)
    rows = []
    price = 10.0
    for index in range(count):
        price += 0.08
        rows.append(
            {
                "date": (start + dt.timedelta(days=index)).isoformat(),
                "open": round(price - 0.04, 2),
                "high": round(price + 0.12, 2),
                "low": round(price - 0.12, 2),
                "close": round(price, 2),
                "volume": 1_000_000 + index * 10_000,
                "change_pct": 0.7,
            }
        )
    return rows


def fixture_candidate(price: float = 12.8, kline_count: int = 40) -> dict:
    return {
        "code": "603228",
        "name": "景旺电子",
        "price": price,
        "entry_price": price,
        "score": 180.78,
        "confidence": 62,
        "recommendation_degree": 62,
        "pre_score": 50.29,
        "chan_score": 46.93,
        "czsc_score": 12.0,
        "serenity_score": 18.0,
        "uzi_score": 14.0,
        "uzi_panel_score": 59.0,
        "amount_yi": 18.4,
        "turnover_pct": 6.2,
        "vol_ratio": 1.35,
        "dragon_net_wan": 2200.0,
        "theme_tags": ["PCB", "AI服务器"],
        "reason_tags": "AI算力相关PCB订单能见度提升",
        "risk_flags": [],
        "hard_risk_count": 0,
        "setup_flags": ["second_buy"],
        "chan": {
            "metrics": {
                "setup_flags": ["second_buy"],
                "distance_ma10_pct": 2.1,
                "distance_ma20_pct": 4.6,
                "pct_5d": 6.2,
                "upper_shadow_pct": 0.8,
                "close_position": 0.82,
            }
        },
        "czsc": {"metrics": {"pct_20d": 12.4}},
        "serenity": {
            "alpha_profile": {
                "dimensions": {
                    "certainty": 3.8,
                    "clarity": 3.5,
                    "purity": 3.2,
                    "elasticity": 3.0,
                    "timeframe": 3.6,
                }
            }
        },
        "realtime": {
            "session": "closed",
            "session_label": "非交易时段",
            "source": "fixture",
            "fetched_at": "2026-08-19T16:10:00+08:00",
        },
        "kline": fixture_kline(kline_count),
        "candidate_lineage": {
            "candidate_id": "a_share:603228",
            "universe_origin": "dynamic_snapshot",
            "recall_routes": [
                {
                    "route": "event",
                    "source": "ths",
                    "reason": "AI算力相关PCB订单能见度提升",
                    "published_at": None,
                    "observed_at": "2026-08-19T15:30:00+08:00",
                    "url": None,
                    "evidence_status": "partial",
                },
                {
                    "route": "liquidity",
                    "source": "eastmoney_broad",
                    "reason": "高流动性",
                    "published_at": None,
                    "observed_at": "2026-08-19T15:30:00+08:00",
                    "url": None,
                    "evidence_status": "partial",
                },
            ],
            "route_count": 2,
            "primary_route": "event",
            "first_seen_at": "2026-08-19T15:30:00+08:00",
            "last_seen_at": "2026-08-19T15:30:00+08:00",
        },
    }


def decision_ready_candidate(code: str = "603228") -> dict:
    candidate = fixture_candidate()
    candidate.update(
        {
            "code": code,
            "confidence": 88,
            "recommendation_degree": 88,
            "hard_risk_count": 0,
            "risk_flags": [],
            "amount_yi": 18.4,
            "change_pct": 1.2,
            "estimated_2w_range": {"low_pct": -2.0, "high_pct": 8.0},
            "execution_state": "CANDIDATE",
            "decision_gates": [{"id": "quote_valid", "status": "PASS"}],
        }
    )
    return candidate


def tencent_quote_payload(code: str = "600000", name: str = "浦发银行") -> bytes:
    values = [""] * 53
    values[1] = name
    values[3] = "10.25"
    values[4] = "10.00"
    values[5] = "10.01"
    values[30] = "20260821145958"
    values[32] = "2.50"
    values[33] = "10.30"
    values[34] = "9.98"
    values[36] = "100000"
    values[37] = "20000"
    values[38] = "1.20"
    values[39] = "6.80"
    values[43] = "3.20"
    values[44] = "3000"
    values[45] = "2500"
    values[46] = "0.75"
    values[47] = "11.00"
    values[48] = "9.00"
    values[49] = "1.10"
    values[52] = "7.00"
    return f'v_sh{code}="{"~".join(values)}";'.encode("gbk")


class SelectorV2Tests(unittest.TestCase):
    def test_recall_targets_and_a_share_board_classification(self) -> None:
        self.assertEqual(server.A_SHARE_RECALL_TARGET, 300)
        self.assertEqual(server.HK_RECALL_TARGET, 200)
        self.assertEqual(server.US_RECALL_TARGET, 300)
        self.assertEqual(sum(server.A_SHARE_BOARD_TARGETS.values()), 300)
        self.assertEqual(server.a_share_board("600000"), "sh_main")
        self.assertEqual(server.a_share_board("000001"), "sz_main")
        self.assertEqual(server.a_share_board("300001"), "chinext")
        self.assertEqual(server.a_share_board("688001"), "star")
        self.assertIsNone(server.a_share_board("830001"))

    def test_broad_admission_uses_board_specific_price_limit_and_name_filters(self) -> None:
        base = {
            "name": "正常公司",
            "price": 20.0,
            "amount_yi": 5.0,
            "turnover_pct": 3.0,
            "route": "liquidity",
            "relaxed": False,
        }
        self.assertFalse(server._admit_broad_a_share(code="600001", change_pct=9.0, **base))
        self.assertTrue(server._admit_broad_a_share(code="300001", change_pct=9.0, **base))
        self.assertFalse(
            server._admit_broad_a_share(
                code="300002", name="N新股", change_pct=2.0, **{key: value for key, value in base.items() if key != "name"}
            )
        )
        self.assertFalse(
            server._admit_broad_a_share(
                code="688001", name="退市样本", change_pct=2.0, **{key: value for key, value in base.items() if key != "name"}
            )
        )

    def test_diversified_a_share_pool_meets_board_targets_and_deduplicates(self) -> None:
        prefixes = {
            "sh_main": "600",
            "sz_main": "000",
            "chinext": "300",
            "star": "688",
        }
        rows = []
        for board, prefix in prefixes.items():
            for index in range(120):
                code = f"{prefix}{index:03d}"
                rows.append(
                    {
                        "code": code,
                        "source": "eastmoney_broad",
                        "recall_route": "liquidity" if index % 2 else "momentum",
                        "broad_amount_yi": float(500 - index),
                        "broad_change_pct": float(index % 8),
                        "broad_turnover_pct": 3.0,
                    }
                )
        rows.append(dict(rows[0]))

        selected, coverage = server.select_diversified_a_share_pool(rows)

        self.assertEqual(len(selected), 300)
        self.assertEqual(len({row["code"] for row in selected}), 300)
        self.assertEqual(coverage["target_count"], 300)
        self.assertEqual(coverage["selected_count"], 300)
        self.assertEqual(coverage["shortfall_count"], 0)
        self.assertEqual(coverage["board_coverage"], server.A_SHARE_BOARD_TARGETS)
        self.assertEqual(coverage["board_shortfalls"], {})
        self.assertGreater(coverage["route_coverage"]["liquidity"], 0)
        self.assertGreater(coverage["route_coverage"]["momentum"], 0)

    def test_diversified_a_share_pool_reports_shortfall_without_padding(self) -> None:
        rows = [
            {
                "code": f"600{index:03d}",
                "source": "eastmoney_broad",
                "recall_route": "liquidity",
                "broad_amount_yi": float(500 - index),
            }
            for index in range(211)
        ]

        selected, coverage = server.select_diversified_a_share_pool(rows)

        self.assertEqual(len(selected), 211)
        self.assertEqual(coverage["shortfall_count"], 89)
        self.assertEqual(coverage["board_shortfalls"]["sz_main"], 75)
        self.assertEqual(coverage["board_shortfalls"]["chinext"], 75)
        self.assertEqual(coverage["board_shortfalls"]["star"], 60)

    def test_diversified_a_share_pool_meets_mutually_exclusive_route_targets(self) -> None:
        prefixes = {
            "sh_main": "600",
            "sz_main": "000",
            "chinext": "300",
            "star": "688",
        }
        rows = []
        for board, route_targets in server.A_SHARE_BOARD_ROUTE_TARGETS.items():
            index = 0
            for route, count in route_targets.items():
                for _ in range(count):
                    rows.append(
                        {
                            "code": f"{prefixes[board]}{index:03d}",
                            "source": "fixture",
                            "recall_route": route,
                            "broad_amount_yi": float(1000 - index),
                            "broad_change_pct": 2.0 if route == "momentum" else -1.0,
                            "broad_turnover_pct": 3.0,
                        }
                    )
                    index += 1

        selected, coverage = server.select_diversified_a_share_pool(rows)

        self.assertEqual(len(selected), 300)
        self.assertEqual(coverage["board_coverage"], server.A_SHARE_BOARD_TARGETS)
        self.assertEqual(coverage["route_targets"], server.A_SHARE_ROUTE_TARGETS)
        self.assertEqual(coverage["route_counts"], server.A_SHARE_ROUTE_TARGETS)
        self.assertEqual(coverage["route_shortfalls"], {})
        self.assertEqual(coverage["backfill_count"], 0)
        self.assertEqual(sum(coverage["route_counts"].values()), 300)

    def test_route_shortfall_backfills_within_board_without_duplicates(self) -> None:
        prefixes = {"sh_main": "600", "sz_main": "000", "chinext": "300", "star": "688"}
        rows = []
        expected_event_count = 0
        missing_event_count = 0
        for board, route_targets in server.A_SHARE_BOARD_ROUTE_TARGETS.items():
            index = 0
            for route, count in route_targets.items():
                available = max(0, count - 8) if route == "event" else count
                expected_event_count += available if route == "event" else 0
                missing_event_count += count - available if route == "event" else 0
                for _ in range(available):
                    rows.append(
                        {
                            "code": f"{prefixes[board]}{index:03d}",
                            "source": "fixture",
                            "recall_route": route,
                            "broad_amount_yi": float(1000 - index),
                        }
                    )
                    index += 1
            board_missing = route_targets["event"] - max(0, route_targets["event"] - 8)
            for _ in range(board_missing):
                rows.append(
                    {
                        "code": f"{prefixes[board]}{index:03d}",
                        "source": "fixture",
                        "recall_route": "liquidity",
                        "broad_amount_yi": float(1000 - index),
                    }
                )
                index += 1

        selected, coverage = server.select_diversified_a_share_pool(rows)

        self.assertEqual(len(selected), 300)
        self.assertEqual(len({row["code"] for row in selected}), 300)
        self.assertEqual(coverage["board_coverage"], server.A_SHARE_BOARD_TARGETS)
        self.assertEqual(coverage["route_counts"]["event"], expected_event_count)
        self.assertEqual(coverage["route_shortfalls"]["event"], missing_event_count)
        self.assertEqual(coverage["backfill_count"], missing_event_count)

    def test_curated_hk_us_universes_have_exact_unique_targets(self) -> None:
        for market_key, target in (("hk", 200), ("us", 300)):
            with self.subTest(market_key=market_key):
                rows = server.market_universe(market_key)
                symbols = [row["symbol"] for row in rows]
                self.assertEqual(len(symbols), target)
                self.assertEqual(len(set(symbols)), target)
                self.assertTrue(
                    all(
                        row["candidate_lineage"]["universe_origin"] == "curated_static"
                        for row in rows
                    )
                )
                if market_key == "hk":
                    self.assertTrue(all(re.fullmatch(r"\d{4}\.HK", symbol) for symbol in symbols))
                    self.assertIn("6051.HK", symbols)
                    self.assertIn("1787.HK", symbols)
                    self.assertIn("2601.HK", symbols)
                    self.assertNotIn("0011.HK", symbols)
                    self.assertNotIn("8083.HK", symbols)
                    self.assertNotIn("8110.HK", symbols)
                    self.assertNotIn("8111.HK", symbols)
                else:
                    self.assertNotIn("SIVE.ST", symbols)
                    self.assertNotIn("SOI", symbols)
                    self.assertIn("SEI", symbols)

    def test_partial_hk_us_quote_coverage_blocks_market_recommendation(self) -> None:
        candidate = decision_ready_candidate("NVDA")
        decision = server.make_serenity_decision(
            [candidate],
            "us",
            quote_health={"status": "partial", "quote_coverage": 0.97},
        )
        self.assertEqual(decision["action"], "NO_TRADE")
        self.assertEqual(decision["data_state"], "DEGRADED")
        self.assertIn("QUOTE_COVERAGE_INSUFFICIENT", decision["blocker_codes"])

    def test_http_get_json_retries_transient_requests_error(self) -> None:
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"ok": True}
        with (
            mock.patch.object(
                server.requests,
                "get",
                side_effect=[requests.ConnectionError("temporary"), response],
            ) as get,
            mock.patch.object(server.time, "sleep"),
        ):
            result = server.http_get_json("https://example.test/api", timeout=1)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(get.call_count, 2)

    def test_tencent_quote_retries_transient_network_error(self) -> None:
        response = mock.Mock()
        response.read.return_value = tencent_quote_payload()
        with (
            mock.patch.object(
                server.urllib.request,
                "urlopen",
                side_effect=[urllib.error.URLError("temporary"), response],
            ) as urlopen,
            mock.patch.object(server.time, "sleep"),
        ):
            result = server.tencent_quote(["600000"])
        self.assertEqual(result["600000"]["name"], "浦发银行")
        self.assertEqual(urlopen.call_count, 2)

    def test_tencent_quote_stops_after_three_attempts(self) -> None:
        with (
            mock.patch.object(
                server.urllib.request,
                "urlopen",
                side_effect=urllib.error.URLError("still down"),
            ) as urlopen,
            mock.patch.object(server.time, "sleep") as sleep,
        ):
            with self.assertRaises(urllib.error.URLError):
                server.tencent_quote(["600000"])
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_tencent_quote_preserves_successful_batches(self) -> None:
        response = mock.Mock()
        response.read.return_value = tencent_quote_payload()
        failure = urllib.error.URLError("second batch down")
        with (
            mock.patch.object(
                server.urllib.request,
                "urlopen",
                side_effect=[response, failure, failure, failure],
            ),
            mock.patch.object(server.time, "sleep"),
        ):
            result = server.tencent_quote(["600000"] * 71)
        self.assertIn("600000", result)

    def test_a_share_quote_failure_returns_unavailable_health(self) -> None:
        with mock.patch.object(server, "tencent_quote", side_effect=urllib.error.URLError("down")):
            scored = server.score_candidates("2026-08-21", [{"code": "600000"}], {})
        self.assertEqual(scored["quote_health"]["status"], "unavailable")
        self.assertEqual(scored["quote_health"]["reason_codes"], ["TENCENT_QUOTE_UNAVAILABLE"])
        self.assertEqual(scored["candidates"], [])

    def test_hk_us_scoring_publishes_truthful_quote_health(self) -> None:
        universe = [
            {"symbol": "AAA", "name": "AAA", "themes": [], "lens": {}},
            {"symbol": "BBB", "name": "BBB", "themes": [], "lens": {}},
        ]
        live = {
            "AAA": {
                "price": 12.0,
                "change_pct": 1.0,
                "session": "regular",
                "session_label": "盘中",
                "source": "Yahoo 1m includePrePost",
                "source_as_of": "2026-08-21T22:00:00+08:00",
                "fetched_at": "2026-08-21T22:00:05+08:00",
            }
        }
        with (
            mock.patch.object(server, "yahoo_realtime_quotes", return_value=live),
            mock.patch.object(server, "yahoo_kline_map", return_value={"AAA": fixture_kline(40)}),
            mock.patch.object(server.time, "sleep"),
        ):
            scored = server.score_serenity_candidates("us", universe)

        self.assertEqual(scored["quote_health"]["status"], "partial")
        self.assertEqual(scored["quote_health"]["requested_count"], 2)
        self.assertEqual(scored["quote_health"]["quote_count"], 1)
        self.assertEqual(scored["quote_health"]["realtime_count"], 1)
        self.assertEqual(scored["quote_health"]["quote_coverage"], 0.5)

    def test_yahoo_quote_freshness_uses_exchange_session_and_regular_latency(self) -> None:
        as_of = dt.datetime.fromisoformat("2026-08-21T10:00:00+08:00")
        fresh = server.yahoo_quote_freshness(
            "hk", {"price": 10, "source_as_of": "2026-08-21T09:40:00+08:00"}, as_of=as_of
        )
        delayed = server.yahoo_quote_freshness(
            "hk", {"price": 10, "source_as_of": "2026-08-21T09:39:59+08:00"}, as_of=as_of
        )
        future_ok = server.yahoo_quote_freshness(
            "hk", {"price": 10, "source_as_of": "2026-08-21T10:05:00+08:00"}, as_of=as_of
        )
        future_bad = server.yahoo_quote_freshness(
            "hk", {"price": 10, "source_as_of": "2026-08-21T10:05:01+08:00"}, as_of=as_of
        )
        weekend_close = server.yahoo_quote_freshness(
            "hk",
            {"price": 10, "source_as_of": "2026-08-21T16:00:00+08:00"},
            as_of=dt.datetime.fromisoformat("2026-08-22T12:00:00+08:00"),
        )

        self.assertTrue(fresh["fresh"])
        self.assertEqual(delayed["reason"], "SOURCE_LATENCY_EXCEEDED")
        self.assertTrue(future_ok["fresh"])
        self.assertEqual(future_bad["reason"], "SOURCE_AS_OF_FUTURE")
        self.assertTrue(weekend_close["fresh"])
        self.assertEqual(weekend_close["reference_session"], "2026-08-21")

    def test_hk_realtime_count_requires_positive_fresh_source(self) -> None:
        universe = [
            {"symbol": symbol, "name": symbol, "themes": [], "lens": {}}
            for symbol in ("AAA.HK", "BBB.HK", "CCC.HK")
        ]
        live = {
            "AAA.HK": {"price": 12, "change_pct": 1, "session": "regular", "session_label": "盘中", "source_as_of": "2026-08-21T09:55:00+08:00"},
            "BBB.HK": {"price": 13, "change_pct": 1, "session": "regular", "session_label": "盘中", "source_as_of": "2026-08-20T15:55:00+08:00"},
            "CCC.HK": {"price": 0, "change_pct": 1, "session": "regular", "session_label": "盘中", "source_as_of": "2026-08-21T09:55:00+08:00"},
        }
        klines = {symbol: fixture_kline(40) for symbol in ("AAA.HK", "BBB.HK", "CCC.HK")}
        with (
            mock.patch.object(server, "now_cn", return_value=dt.datetime.fromisoformat("2026-08-21T10:00:00+08:00")),
            mock.patch.object(server, "yahoo_realtime_quotes", return_value=live),
            mock.patch.object(server, "yahoo_kline_map", return_value=klines),
        ):
            scored = server.score_serenity_candidates("hk", universe)

        health = scored["quote_health"]
        self.assertEqual(health["quote_count"], 3)
        self.assertEqual(health["realtime_count"], 1)
        self.assertEqual(health["realtime_coverage"], 0.3333)
        self.assertEqual(health["stale_realtime_symbols"], ["BBB.HK"])
        self.assertIn("YAHOO_REALTIME_STALE", health["reason_codes"])
        by_code = {row["code"]: row for row in scored["candidates"]}
        self.assertNotEqual(by_code["BBB.HK"]["entry_price"], 13)
        self.assertNotEqual(by_code["CCC.HK"]["entry_price"], 0)

    def test_a_share_deep_score_excludes_incomplete_kline(self) -> None:
        codes = ("600000", "000001", "300001")

        def quote(code: str) -> dict:
            return {
                "code": code,
                "name": code,
                "price": 10.0,
                "entry_price": 10.0,
                "current_price": 10.0,
                "last_close": 9.9,
                "open": 9.95,
                "low": 9.9,
                "change_pct": 1.0,
                "current_change_pct": 1.0,
                "amount_wan": 50_000,
                "turnover_pct": 5.0,
                "vol_ratio": 1.2,
                "float_mcap_yi": 200,
                "limit_up": 10.89,
                "limit_down": 8.91,
                "fundamentals": {},
                "realtime": {"session_label": "盘中", "source_as_of": "2026-08-21T10:00:00+08:00"},
            }

        with (
            mock.patch.object(server, "tencent_quote", return_value={code: quote(code) for code in codes}),
            mock.patch.object(server, "daily_dragon_tiger", return_value={}),
            mock.patch.object(
                server,
                "a_share_kline_map",
                return_value={codes[0]: fixture_kline(32), codes[1]: fixture_kline(31), codes[2]: []},
            ),
            mock.patch.object(server, "run_dual_low_analysis", return_value={"by_code": {}, "metadata": {}}),
            mock.patch.dict(server.os.environ, {"CHAN_MAX_KLINE_CHECKS": "3"}),
        ):
            scored = server.score_candidates(
                "2026-08-21",
                [{"code": code, "reason": "测试", "candidate_lineage": {}} for code in codes],
                {"risk": "normal"},
            )

        self.assertEqual(scored["deep_attempted_size"], 3)
        self.assertEqual(scored["deep_scored_size"], 1)
        self.assertEqual(scored["scored_size"], 1)
        self.assertEqual(scored["deep_kline_coverage"], 0.3333)
        self.assertEqual([row["code"] for row in scored["candidates"]], ["600000"])

    def test_market_context_uses_benchmark_kline_without_overstating_missing_data(self) -> None:
        with mock.patch.object(server, "yahoo_chart_kline", return_value=fixture_kline(40)):
            context = server.market_context_from_benchmark("hk")
        self.assertEqual(context["benchmark"], "^HSI")
        self.assertEqual(context["data_state"], "READY")
        self.assertTrue(context["items"])

        with mock.patch.object(server, "yahoo_chart_kline", return_value=[]):
            missing = server.market_context_from_benchmark("us")
        self.assertEqual(missing["data_state"], "DEGRADED")
        self.assertEqual(missing["risk"], "unknown")

    def test_degraded_a_share_still_builds_hk_and_us_sections(self) -> None:
        scored = {
            "candidates": [],
            "raw_pool_size": 1,
            "scored_size": 0,
            "dragon_count": 0,
            "quote_health": server.quote_health_contract(1, 0, failed=True),
            "analysis_models": {},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch.object(server, "PICKS", server.pathlib.Path(temp_dir)),
                mock.patch.object(server, "find_hot_pool", return_value=("2026-08-21", [{"code": "600000"}])),
                mock.patch.object(server, "load_broad_market_pool", return_value=[]),
                mock.patch.object(server, "cached_a_share_pool", return_value=[]),
                mock.patch.object(server, "index_quotes", return_value={"items": [], "risk": "unknown"}),
                mock.patch.object(server, "industry_heat", return_value={"top": [], "total": 0}),
                mock.patch.object(server, "score_candidates", return_value=scored),
                mock.patch.object(server, "market_universe", return_value=[]),
                mock.patch.object(server, "score_serenity_candidates", return_value={"candidates": [], "raw_pool_size": 0, "scored_size": 0}),
                mock.patch.object(
                    server,
                    "market_context_from_benchmark",
                    return_value={
                        "benchmark": "fixture",
                        "benchmarks": [],
                        "items": [],
                        "risk": "unknown",
                        "state": "unknown",
                        "data_state": "DEGRADED",
                    },
                ),
                mock.patch.object(server, "runtime_research_status", return_value={}),
                mock.patch.object(server, "serenity_source_status", return_value={}),
            ):
                snapshot = server.run_selector("2026-08-24", force=True)
        self.assertEqual(snapshot["markets"]["a_share"]["decision"]["action"], "NO_TRADE")
        self.assertEqual(snapshot["markets"]["a_share"]["pool_health"]["status"], "degraded")
        self.assertEqual(set(snapshot["markets"]), {"a_share", "hk", "us"})

    def test_zero_broad_pool_forces_degraded_no_trade(self) -> None:
        health = server.a_share_pool_health(
            [],
            event_count=57,
            cached_count=40,
            quote_count=93,
            merged_count=96,
        )
        decision = server.make_decision([decision_ready_candidate()], {}, pool_health=health)
        self.assertEqual(health["status"], "degraded")
        self.assertIn("BROAD_POOL_BELOW_MINIMUM", health["reason_codes"])
        self.assertEqual(decision["action"], "NO_TRADE")
        self.assertEqual(decision["data_state"], "DEGRADED")
        self.assertIn("POOL_COVERAGE_INSUFFICIENT", decision["blocker_codes"])

    def test_low_quote_coverage_has_stable_reason_code(self) -> None:
        health = server.a_share_pool_health(
            [{"code": str(index)} for index in range(100)],
            event_count=0,
            cached_count=0,
            quote_count=39,
            merged_count=100,
        )
        self.assertEqual(health["status"], "degraded")
        self.assertIn("QUOTE_COVERAGE_BELOW_MINIMUM", health["reason_codes"])
        self.assertEqual(health["quote_coverage"], 0.39)

    def test_a_share_deep_kline_coverage_requires_95_of_96(self) -> None:
        broad = [{"code": str(index)} for index in range(300)]
        recall = {
            "target_count": 300,
            "selected_count": 300,
            "board_coverage": dict(server.A_SHARE_BOARD_TARGETS),
            "board_shortfalls": {},
        }
        healthy = server.a_share_pool_health(
            broad,
            quote_count=300,
            deep_attempted_count=96,
            deep_completed_count=95,
            merged_count=300,
            recall_coverage=recall,
        )
        degraded = server.a_share_pool_health(
            broad,
            quote_count=300,
            deep_attempted_count=96,
            deep_completed_count=94,
            merged_count=300,
            recall_coverage=recall,
        )

        self.assertEqual(healthy["status"], "healthy")
        self.assertNotIn("A_SHARE_KLINE_COVERAGE_BELOW_MINIMUM", healthy["reason_codes"])
        self.assertEqual(degraded["status"], "degraded")
        self.assertIn("A_SHARE_KLINE_COVERAGE_BELOW_MINIMUM", degraded["reason_codes"])

    def test_objectively_blocked_candidate_cannot_be_a_share_primary(self) -> None:
        blocked = decision_ready_candidate("600001")
        blocked["execution_state"] = "BLOCKED"
        blocked["decision_gates"] = [{"id": "quote_valid", "status": "BLOCK"}]
        eligible = decision_ready_candidate("600002")
        decision = server.make_decision(
            [blocked, eligible],
            {},
            pool_health={"status": "healthy"},
        )
        self.assertEqual(decision["action"], "BUY_CANDIDATE")
        self.assertEqual(decision["primary"]["code"], "600002")
        self.assertEqual([row["code"] for row in decision["watchlist"]], ["600001"])

    def test_objectively_blocked_candidate_cannot_be_hk_or_us_primary(self) -> None:
        for market_key in ("hk", "us"):
            blocked = decision_ready_candidate("BLOCKED")
            blocked["decision_gates"] = [{"id": "kline_complete", "status": "BLOCK"}]
            eligible = decision_ready_candidate("ELIGIBLE")
            decision = server.make_serenity_decision([blocked, eligible], market_key)
            self.assertEqual(decision["action"], "BUY_CANDIDATE")
            self.assertEqual(decision["primary"]["code"], "ELIGIBLE")
            self.assertEqual([row["code"] for row in decision["watchlist"]], ["BLOCKED"])

    def test_serenity_runtime_status_does_not_publish_local_path_or_overstate_execution(self):
        status = server.serenity_skill_status()
        self.assertEqual(status["mode"], "built-in-lens")
        self.assertNotIn("path", status)

    def test_tencent_source_timestamp_is_not_replaced_by_fetch_time(self) -> None:
        self.assertEqual(
            server.parse_cn_quote_timestamp("20260819145958"),
            "2026-08-19T14:59:58+08:00",
        )
        self.assertIsNone(server.parse_cn_quote_timestamp(""))

    def test_merge_candidate_pools_preserves_all_recall_routes(self) -> None:
        rows = server.merge_candidate_pools(
            [{"code": "603228", "reason": "订单", "source": "ths"}],
            [
                {
                    "code": "603228",
                    "reason": "高流动性",
                    "source": "eastmoney_broad",
                    "recall_route": "liquidity",
                }
            ],
        )
        routes = rows[0]["candidate_lineage"]["recall_routes"]
        self.assertEqual({item["route"] for item in routes}, {"event", "liquidity"})
        self.assertEqual(rows[0]["candidate_lineage"]["route_count"], 2)

    def test_broad_pool_rows_do_not_require_positive_return_or_pb18(self) -> None:
        row = {
            "broad_change_pct": -1.2,
            "broad_amount_yi": 16.0,
            "broad_turnover_pct": 4.0,
            "pb": 35.0,
        }
        self.assertEqual(server.broad_recall_routes(row), ["liquidity", "pullback", "activity"])

    def test_cached_pool_expires_after_five_trade_weekdays(self) -> None:
        as_of = dt.date(2026, 8, 19)
        self.assertFalse(server.is_history_candidate_fresh("2026-08-12", as_of, 5))
        self.assertTrue(server.is_history_candidate_fresh("2026-08-14", as_of, 5))

    def test_v2_factor_contributions_sum_and_features_are_unique(self) -> None:
        result = server.build_v2_shadow(fixture_candidate(), "a_share", {"risk": "normal"})
        contribution = sum(item["contribution"] for item in result["factor_groups"].values())
        self.assertLess(abs(contribution - result["rule_score"]), 0.02)
        used = [
            feature["feature_id"]
            for group in result["factor_groups"].values()
            for feature in group["features"]
            if feature["used_in_score"]
        ]
        self.assertEqual(len(used), len(set(used)))
        self.assertEqual(set(result["factor_groups"]), {"event", "technical", "industry", "liquidity_flow", "quality"})

    def test_unknown_market_is_not_treated_as_normal(self) -> None:
        regime = server.classify_market_regime("hk", {}, [])
        self.assertEqual(regime["state"], "unknown")
        self.assertTrue(regime["warnings"])

    def test_invalid_quote_blocks_execution_but_keeps_legacy_fields(self) -> None:
        candidate = fixture_candidate(price=0)
        original_score = candidate["score"]
        enriched = server.attach_candidate_v2(candidate, "a_share", {"risk": "normal"})
        self.assertEqual(enriched["decision_gates"][0]["id"], "quote_valid")
        self.assertEqual(enriched["decision_gates"][0]["status"], "BLOCK")
        self.assertTrue(enriched["legacy"]["active"])
        self.assertEqual(enriched["score"], original_score)
        self.assertIn("INVALID_PRICE", {item["code"] for item in enriched["risk_items"]})

    def test_incomplete_kline_is_an_objective_block(self) -> None:
        enriched = server.attach_candidate_v2(fixture_candidate(kline_count=12), "a_share", {"risk": "normal"})
        gates = {item["id"]: item["status"] for item in enriched["decision_gates"]}
        self.assertEqual(gates["kline_complete"], "BLOCK")
        self.assertIn("KLINE_INCOMPLETE", {item["code"] for item in enriched["risk_items"]})

    def test_market_ranks_do_not_reorder_legacy_candidates(self) -> None:
        first = fixture_candidate()
        first["code"] = "603228"
        second = fixture_candidate()
        second["code"] = "002463"
        second["theme_tags"] = []
        second["setup_flags"] = []
        second["chan"]["metrics"]["setup_flags"] = []
        rows = [first, second]
        server.enrich_market_candidates(rows, "a_share", {"risk": "normal"})
        self.assertEqual([row["code"] for row in rows], ["603228", "002463"])
        self.assertEqual({row["v2"]["rank"] for row in rows}, {1, 2})

    def test_snapshot_subset_preserves_full_deep_pool_rank_denominator(self) -> None:
        full_pool = []
        for index in range(12):
            row = fixture_candidate()
            row["code"] = f"60{index:04d}"
            row["chan"]["metrics"]["pct_5d"] = float(index)
            full_pool.append(row)
        server.enrich_market_candidates(full_pool, "a_share", {"risk": "normal", "items": [{"change_pct": 0.2}]})
        subset = [full_pool[0], full_pool[5], full_pool[9]]
        before = [(row["v2"]["rank"], row["v2"]["rank_universe_size"]) for row in subset]
        server.enrich_market_candidates(subset, "a_share", {"risk": "normal", "items": [{"change_pct": 0.2}]})
        after = [(row["v2"]["rank"], row["v2"]["rank_universe_size"]) for row in subset]
        self.assertEqual(after, before)
        self.assertTrue(all(size == 12 for _, size in after))

    def test_reason_text_without_event_lineage_is_not_scored_as_event(self) -> None:
        candidate = fixture_candidate()
        candidate["candidate_lineage"]["recall_routes"] = [
            {
                "route": "liquidity",
                "source": "eastmoney_broad",
                "reason": "高流动性",
                "published_at": None,
                "observed_at": None,
                "url": None,
                "evidence_status": "partial",
            }
        ]
        result = server.build_v2_shadow(candidate, "a_share", {"risk": "normal", "items": [{"change_pct": 0.1}]})
        event_group = result["factor_groups"]["event"]
        self.assertEqual(event_group["availability"], "missing")
        self.assertFalse(event_group["features"][0]["used_in_score"])
        self.assertEqual(event_group["contribution"], 0)

    def test_quote_without_source_time_is_available_not_fresh(self) -> None:
        candidate = fixture_candidate()
        enriched = server.attach_candidate_v2(
            candidate,
            "a_share",
            {"risk": "normal", "items": [{"change_pct": 0.1}]},
        )
        quote = next(item for item in enriched["data_quality"]["inputs"] if item["id"] == "quote")
        self.assertEqual(quote["state"], "available")
        self.assertEqual(enriched["data_quality"]["status"], "partial")
        freshness = next(item for item in enriched["decision_gates"] if item["id"] == "quote_freshness")
        self.assertEqual(freshness["status"], "WARN")

    def test_explicit_stale_quote_blocks_in_all_sessions(self) -> None:
        regular = fixture_candidate()
        regular["realtime"].update({"stale": True, "session": "regular", "source_as_of": "2026-08-19T09:30:00+08:00"})
        server.attach_candidate_v2(regular, "a_share", {"risk": "normal", "items": [{"change_pct": 0.1}]})
        regular_gate = next(item for item in regular["decision_gates"] if item["id"] == "quote_freshness")
        self.assertEqual(regular_gate["status"], "BLOCK")
        self.assertIn("STALE_QUOTE", {item["code"] for item in regular["risk_items"]})

        closed = fixture_candidate()
        closed["realtime"].update({"stale": True, "session": "closed", "source_as_of": "2026-08-19T16:00:00+08:00"})
        server.attach_candidate_v2(closed, "a_share", {"risk": "normal", "items": [{"change_pct": 0.1}]})
        closed_gate = next(item for item in closed["decision_gates"] if item["id"] == "quote_freshness")
        self.assertEqual(closed_gate["status"], "BLOCK")
        self.assertIn("STALE_QUOTE", {item["code"] for item in closed["risk_items"]})

    def test_event_feed_keeps_missing_evidence_null(self) -> None:
        snapshot = {
            "generated_at": "2026-08-19T16:30:00+08:00",
            "markets": {
                "a_share": {
                    "decision": {"action": "BUY_CANDIDATE", "primary": fixture_candidate(), "watchlist": []}
                }
            },
        }
        enriched = server.enrich_snapshot_v2(snapshot)
        event = next(item for item in enriched["events"]["items"] if item["event_type"] == "announcement_or_news")
        self.assertIsNone(event["url"])
        self.assertIsNone(event["published_at"])
        self.assertEqual(event["evidence_status"], "partial")
        self.assertEqual(event["source"], "ths")

    def test_backtest_accepts_serenity_alpha_profile(self) -> None:
        lens_score, reasons, risks, alpha = server.serenity_lens_score({"lens": {}})
        self.assertIsInstance(lens_score, float)
        self.assertIsInstance(reasons, list)
        self.assertIsInstance(risks, list)
        self.assertIsInstance(alpha, dict)

    def test_enrichment_is_idempotent_for_legacy_values(self) -> None:
        candidate = fixture_candidate()
        before = copy.deepcopy({key: candidate[key] for key in ("score", "recommendation_degree", "chan_score", "uzi_panel_score")})
        server.attach_candidate_v2(candidate, "a_share", {"risk": "normal"})
        server.attach_candidate_v2(candidate, "a_share", {"risk": "normal"})
        after = {key: candidate[key] for key in before}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()

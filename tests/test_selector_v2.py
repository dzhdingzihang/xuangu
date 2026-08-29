from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
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


def eastmoney_hk_fixture_row(
    number: int,
    source_timestamp,
    *,
    amount: float = 30_000_000,
    symbol_number: int | None = None,
) -> dict:
    symbol_number = number if symbol_number is None else symbol_number
    return {
        "f2": 10,
        "f3": 1.2,
        "f5": 1_000_000,
        "f6": amount,
        "f8": 2,
        "f9": 12,
        "f10": 1.5,
        "f12": f"{symbol_number:05d}",
        "f13": 128,
        "f14": f"HK{symbol_number:04d}",
        "f20": 5_000_000_000,
        "f21": 4_000_000_000,
        "f23": 2,
        "f24": 3,
        "f25": 5,
        "f26": "20200101",
        "f62": 1_000_000,
        "f115": 12,
        "f124": source_timestamp,
    }


def eastmoney_page_response(rows: list[dict], total: int = 2914):
    response = mock.Mock()
    response.json.return_value = {"data": {"total": total, "diff": rows}}
    return response


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

    def test_legacy_curated_hk_us_universes_remain_reproducible(self) -> None:
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

    def test_dynamic_hk_us_pool_is_exact_unique_and_auditable(self) -> None:
        for market_key, target, total in (("hk", 200, 230), ("us", 300, 340)):
            with self.subTest(market_key=market_key):
                rows = []
                for index in range(total):
                    symbol = f"{index + 1:04d}.HK" if market_key == "hk" else f"U{index:03d}"
                    rows.append(
                        {
                            "symbol": symbol,
                            "name": symbol,
                            "source": "fixture_market",
                            "reason": "fixture dynamic cross-section",
                            "observed_at": "2026-08-21T16:10:00+08:00",
                            "recall_routes": ["liquidity", "momentum", "pullback", "activity", "quality"],
                            "recall_metrics": {
                                "amount": 100_000_000 + index * 1_000_000,
                                "market_cap": 2_000_000_000 + index * 10_000_000,
                                "volume": 1_000_000 + index * 1_000,
                                "change_pct": (index % 9) - 3,
                            },
                            "themes": [],
                            "lens": server._dynamic_neutral_lens(market_key),
                            "candidate_lineage": {"universe_origin": server.DYNAMIC_MARKET_ORIGIN},
                        }
                    )
                selected, coverage = server.select_dynamic_market_pool(rows, market_key)
                symbols = [row["symbol"] for row in selected]
                self.assertEqual(len(symbols), target)
                self.assertEqual(len(set(symbols)), target)
                self.assertEqual(sum(coverage["route_counts"].values()), target)
                self.assertEqual(len(coverage["recall_manifest"]), target)
                self.assertEqual(
                    {row["candidate_lineage"]["universe_origin"] for row in selected},
                    {"dynamic_market_snapshot"},
                )
                self.assertTrue(all(not row.get("themes") for row in selected))
                self.assertTrue(all(row.get("lens_confidence") is None for row in selected))

    def test_dynamic_membership_changes_when_market_cross_section_changes(self) -> None:
        def row(index: int, amount: float) -> dict:
            symbol = f"T{index:03d}"
            return {
                "symbol": symbol,
                "name": symbol,
                "source": "fixture_market",
                "reason": "fixture",
                "observed_at": "2026-08-21T16:10:00+08:00",
                "recall_routes": ["liquidity"],
                "recall_metrics": {"amount": amount, "market_cap": amount * 10, "volume": amount / 10, "change_pct": 1},
                "themes": [],
                "lens": server._dynamic_neutral_lens("us"),
                "candidate_lineage": {"universe_origin": server.DYNAMIC_MARKET_ORIGIN},
            }

        first = [row(index, 1_000_000 + index) for index in range(301)]
        second = copy.deepcopy(first)
        second[0]["recall_metrics"]["amount"] = 10_000_000_000
        first_selected, _ = server.select_dynamic_market_pool(first, "us")
        second_selected, _ = server.select_dynamic_market_pool(second, "us")
        self.assertNotEqual(
            {item["symbol"] for item in first_selected},
            {item["symbol"] for item in second_selected},
        )

    def test_dynamic_security_filters_exclude_non_common_products(self) -> None:
        observed = "2026-08-21T16:10:00+08:00"
        valid_us, _ = server._dynamic_us_candidate(
            {"symbol": "BRK_B", "name": "Berkshire Hathaway", "market": "NYSE", "price": 500, "volume": 100000, "mktcap": 1e12, "chg": 1},
            "quality",
            observed,
        )
        etf, etf_reason = server._dynamic_us_candidate(
            {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "market": "NASDAQ", "price": 500, "volume": 100000, "mktcap": 1e12, "chg": 1},
            "quality",
            observed,
        )
        fund, fund_reason = server._dynamic_hk_candidate(
            {"symbol": "02800", "name": "盈富基金", "lasttrade": 25, "volume": 2e6, "amount": 5e7, "changepercent": 1},
            "liquidity",
            observed,
        )
        crypto_etf, crypto_etf_reason = server._dynamic_us_candidate(
            {"symbol": "IBIT", "name": "iShares Bitcoin Trust ETF", "market": "NASDAQ", "price": 50, "volume": 1000000, "mktcap": 10e9, "chg": 1},
            "quality",
            observed,
        )
        closed_end_fund, closed_end_reason = server._dynamic_us_candidate(
            {"symbol": "GOF", "name": "Guggenheim Strategic Opportunities Fund", "market": "NYSE", "price": 15, "volume": 1000000, "mktcap": 2e9, "chg": 1},
            "quality",
            observed,
        )
        hk_main, _ = server._dynamic_hk_candidate(
            {"symbol": "09988", "name": "阿里巴巴-W", "lasttrade": 100, "volume": 2e6, "amount": 2e8, "changepercent": 1},
            "liquidity",
            observed,
        )
        self.assertEqual(valid_us["symbol"], "BRK-B")
        self.assertIsNone(etf)
        self.assertEqual(etf_reason, "security_type")
        self.assertIsNone(fund)
        self.assertEqual(fund_reason, "security_type")
        self.assertIsNone(crypto_etf)
        self.assertEqual(crypto_etf_reason, "security_type")
        self.assertIsNone(closed_end_fund)
        self.assertEqual(closed_end_reason, "security_type")
        self.assertEqual(hk_main["market_segment"], "main_board")

    def test_hk_intraday_liquidity_completion_scales_the_daily_amount_gate(self) -> None:
        source_time = dt.datetime.fromisoformat("2026-08-26T09:25:00+08:00")
        observed_at = "2026-08-26T09:40:00+08:00"
        base = {
            "symbol": "0700",
            "name": "腾讯控股",
            "lasttrade": 580,
            "volume": 100_000,
            "amount": 2_500_000,
            "market_cap": 5_000_000_000,
            "changepercent": 1.2,
            "ticktime": int(source_time.timestamp()),
        }

        candidate, reason = server._dynamic_hk_candidate(base, "liquidity", observed_at)

        self.assertIsNone(reason)
        self.assertIsNotNone(candidate)
        metrics = candidate["recall_metrics"]
        self.assertEqual(metrics["liquidity_policy_version"], server.HK_INTRADAY_LIQUIDITY_POLICY_VERSION)
        self.assertEqual(metrics["liquidity_admission"], "intraday_scaled")
        self.assertEqual(metrics["liquidity_amount_threshold"], 2_000_000)
        self.assertEqual(metrics["liquidity_standard_amount_threshold"], 20_000_000)
        self.assertEqual(metrics["liquidity_source_phase"], "pre")
        self.assertGreater(metrics["liquidity_gate_progress"], 0)
        self.assertEqual(metrics["liquidity_data_progress"], 0)
        self.assertIsNone(metrics["projected_full_session_amount"])
        self.assertEqual(metrics["liquidity_projection_basis"], "pre_no_linear_projection")
        self.assertIn("intraday_liquidity_completion", candidate["recall_routes"])

        regular_source, regular_source_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0705",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-26T09:35:00+08:00").timestamp()),
            },
            "liquidity",
            observed_at,
        )
        self.assertIsNone(regular_source_reason)
        self.assertEqual(regular_source["recall_metrics"]["liquidity_source_phase"], "regular")
        self.assertGreater(regular_source["recall_metrics"]["liquidity_data_progress"], 0)
        self.assertGreater(regular_source["recall_metrics"]["projected_full_session_amount"], 20_000_000)

        below_floor, below_floor_reason = server._dynamic_hk_candidate(
            {**base, "symbol": "0701", "amount": 1_999_999}, "liquidity", observed_at
        )
        small_cap, small_cap_reason = server._dynamic_hk_candidate(
            {**base, "symbol": "0702", "market_cap": 999_999_999}, "liquidity", observed_at
        )
        after_close, after_close_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0703",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-26T16:00:00+08:00").timestamp()),
            },
            "liquidity",
            "2026-08-26T16:20:00+08:00",
        )
        stale_same_session, stale_same_session_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0704",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-26T08:50:00+08:00").timestamp()),
            },
            "liquidity",
            observed_at,
        )
        prior_session, prior_session_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0705",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-25T16:00:00+08:00").timestamp()),
            },
            "liquidity",
            observed_at,
        )
        future_source, future_source_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0706",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-26T09:50:01+08:00").timestamp()),
            },
            "liquidity",
            observed_at,
        )
        stale_prior_session, stale_prior_session_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0704",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-25T09:25:00+08:00").timestamp()),
            },
            "liquidity",
            observed_at,
        )

        self.assertIsNone(below_floor)
        self.assertEqual(below_floor_reason, "liquidity")
        self.assertIsNone(small_cap)
        self.assertEqual(small_cap_reason, "liquidity")
        self.assertIsNone(after_close)
        self.assertEqual(after_close_reason, "liquidity")
        self.assertIsNone(stale_same_session)
        self.assertEqual(stale_same_session_reason, "liquidity")
        self.assertIsNone(prior_session)
        self.assertEqual(prior_session_reason, "liquidity")
        self.assertIsNone(future_source)
        self.assertEqual(future_source_reason, "liquidity")
        self.assertIsNone(stale_prior_session)
        self.assertEqual(stale_prior_session_reason, "liquidity")

    def test_hk_liquidity_clock_uses_half_day_and_strict_break_freshness_boundaries(self) -> None:
        half_day_source = dt.datetime.fromisoformat("2026-12-24T10:30:00+08:00")
        half_day, half_day_reason = server._dynamic_hk_candidate(
            {
                "symbol": "0005",
                "name": "汇丰控股",
                "lasttrade": 120,
                "volume": 100_000,
                "amount": 10_000_000,
                "market_cap": 5_000_000_000,
                "changepercent": 1,
                "ticktime": int(half_day_source.timestamp()),
            },
            "liquidity",
            "2026-12-24T10:45:00+08:00",
        )

        self.assertIsNone(half_day_reason)
        half_day_metrics = half_day["recall_metrics"]
        self.assertEqual(half_day_metrics["liquidity_session_total_minutes"], 150)
        self.assertEqual(half_day_metrics["liquidity_gate_elapsed_minutes"], 75)
        self.assertEqual(half_day_metrics["liquidity_gate_progress"], 0.5)
        self.assertEqual(half_day_metrics["liquidity_data_progress"], 0.4)
        self.assertIsNone(half_day_metrics["liquidity_session_break_start_at"])
        self.assertEqual(half_day_metrics["liquidity_amount_threshold"], 10_000_000)

        base = {
            "name": "边界测试",
            "lasttrade": 10,
            "volume": 1_000_000,
            "amount": 10_000_000,
            "market_cap": 5_000_000_000,
            "changepercent": 1,
        }
        observed_at = "2026-08-26T12:30:00+08:00"

        def candidate_at(symbol: str, source_time: str):
            timestamp = int(dt.datetime.fromisoformat(source_time).timestamp())
            return server._dynamic_hk_candidate(
                {**base, "symbol": symbol, "ticktime": timestamp}, "liquidity", observed_at
            )

        age_45, age_45_reason = candidate_at("0701", "2026-08-26T11:14:00+08:00")
        age_45_01, age_45_01_reason = candidate_at("0702", "2026-08-26T11:13:59+08:00")
        lunch_source, lunch_source_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0703",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-26T12:05:00+08:00").timestamp()),
            },
            "liquidity",
            "2026-08-26T12:47:00+08:00",
        )
        lunch_future, lunch_future_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0707",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-26T12:59:00+08:00").timestamp()),
            },
            "liquidity",
            "2026-08-26T12:01:00+08:00",
        )
        stale_open, stale_open_reason = server._dynamic_hk_candidate(
            {
                **base,
                "symbol": "0704",
                "ticktime": int(dt.datetime.fromisoformat("2026-08-26T09:30:00+08:00").timestamp()),
            },
            "liquidity",
            "2026-08-26T12:47:00+08:00",
        )

        def regular_candidate_at(symbol: str, source_time: str):
            return server._dynamic_hk_candidate(
                {
                    **base,
                    "symbol": symbol,
                    "ticktime": int(dt.datetime.fromisoformat(source_time).timestamp()),
                },
                "liquidity",
                "2026-08-26T10:00:00+08:00",
            )

        future_5, future_5_reason = regular_candidate_at("0705", "2026-08-26T10:05:00+08:00")
        future_5_01, future_5_01_reason = regular_candidate_at("0706", "2026-08-26T10:05:01+08:00")

        self.assertIsNone(age_45_reason)
        self.assertEqual(age_45["recall_metrics"]["liquidity_source_age_seconds"], 45 * 60)
        self.assertEqual(age_45["recall_metrics"]["liquidity_freshness_reference_at"], "2026-08-26T11:59:00+08:00")
        self.assertIsNone(age_45_01)
        self.assertEqual(age_45_01_reason, "liquidity")
        self.assertIsNone(lunch_source_reason)
        self.assertEqual(lunch_source["recall_metrics"]["liquidity_source_age_seconds"], 0)
        self.assertEqual(lunch_source["recall_metrics"]["liquidity_source_effective_at"], "2026-08-26T11:59:00+08:00")
        self.assertIsNone(lunch_future)
        self.assertEqual(lunch_future_reason, "liquidity")
        self.assertIsNone(stale_open)
        self.assertEqual(stale_open_reason, "liquidity")
        self.assertIsNone(future_5_reason)
        self.assertEqual(future_5["recall_metrics"]["liquidity_source_age_seconds"], -5 * 60)
        self.assertIsNone(future_5_01)
        self.assertEqual(future_5_01_reason, "liquidity")

    def test_hk_source_coverage_maps_both_lunch_clocks_to_previous_trading_minute(self) -> None:
        observed = dt.datetime.fromisoformat("2026-08-26T12:47:00+08:00")

        def row(symbol: str, source_time: str) -> dict:
            return {
                "symbol": symbol,
                "recall_metrics": {
                    "source_timestamp": int(dt.datetime.fromisoformat(source_time).timestamp())
                },
            }

        lunch = server._dynamic_source_time_coverage(
            [row("0700.HK", "2026-08-26T12:05:00+08:00")], "hk", as_of=observed
        )
        stale_open = server._dynamic_source_time_coverage(
            [row("0005.HK", "2026-08-26T09:30:00+08:00")], "hk", as_of=observed
        )
        future_lunch = server._dynamic_source_time_coverage(
            [row("0707.HK", "2026-08-26T12:59:00+08:00")],
            "hk",
            as_of=dt.datetime.fromisoformat("2026-08-26T12:01:00+08:00"),
        )

        self.assertEqual(lunch["discovery_freshness_reference_at"], "2026-08-26T11:59:00+08:00")
        self.assertEqual(lunch["discovery_source_effective_as_of"], "2026-08-26T11:59:00+08:00")
        self.assertEqual(lunch["selected_source_fresh_coverage"], 1.0)
        self.assertEqual(stale_open["selected_source_fresh_coverage"], 0.0)
        self.assertEqual(stale_open["selected_source_stale_symbols"], ["0005.HK"])
        self.assertEqual(future_lunch["selected_source_fresh_coverage"], 0.0)
        self.assertEqual(future_lunch["selected_source_stale_symbols"], ["0707.HK"])

    def test_eastmoney_hk_discovery_adaptively_fetches_more_liquidity_pages(self) -> None:
        observed = dt.datetime.fromisoformat("2026-08-26T09:40:00+08:00")
        source_timestamp = int(dt.datetime.fromisoformat("2026-08-26T09:25:00+08:00").timestamp())
        calls: list[tuple[int, str]] = []

        def market_response(*_args, **kwargs):
            params = kwargs["params"]
            page = int(params["pn"])
            field = str(params["fid"])
            calls.append((page, field))
            first = (page - 1) * 100 + 1
            rows = [
                eastmoney_hk_fixture_row(
                    number,
                    source_timestamp,
                    amount=30_000_000 if page <= 2 else 3_000_000,
                )
                for number in range(first, first + 100)
            ]
            return eastmoney_page_response(rows)

        with (
            mock.patch.object(server, "now_cn", return_value=observed),
            mock.patch.object(server, "market_data_get_with_retry", side_effect=market_response),
        ):
            rows, discovery = server._fetch_eastmoney_dynamic_rows("hk")
        selected, coverage = server.select_dynamic_market_pool(rows, "hk")

        self.assertEqual(len(selected), 200)
        self.assertGreaterEqual(coverage["eligible_discovery_size"], server.DYNAMIC_MARKET_MIN_ELIGIBLE["hk"])
        self.assertEqual(discovery["discovery_base_requested_pages"], 10)
        self.assertEqual(discovery["discovery_adaptive_requested_pages"], 1)
        self.assertEqual(discovery["discovery_adaptive_completed_pages"], 1)
        self.assertEqual(discovery["discovery_adaptive_stop_reason"], "minimum_eligible_met")
        self.assertTrue(discovery["discovery_pagination_complete"])
        self.assertGreater(discovery["adaptive_liquidity_unique_candidates"], 0)
        self.assertEqual(selected[0]["recall_metrics"]["market_cap_currency"], "HKD")
        self.assertEqual(selected[0]["recall_metrics"]["market_cap_kind"], "total")
        self.assertEqual(selected[0]["recall_metrics"]["market_cap_source_field"], "f20")
        self.assertEqual([call for call in calls if call[0] == 3], [(3, "f6")])
        self.assertFalse(any(page > 3 for page, _field in calls))

    def test_eastmoney_bad_f124_excludes_only_the_bad_row(self) -> None:
        observed = dt.datetime.fromisoformat("2026-08-26T09:40:00+08:00")
        source_timestamp = int(dt.datetime.fromisoformat("2026-08-26T09:25:00+08:00").timestamp())

        def market_response(*_args, **kwargs):
            page = int(kwargs["params"]["pn"])
            first = (page - 1) * 100 + 1
            rows = [
                eastmoney_hk_fixture_row(
                    number,
                    "bad-f124" if page == 1 and number == 1 else source_timestamp,
                    amount=30_000_000 if page <= 2 else 3_000_000,
                )
                for number in range(first, first + 100)
            ]
            return eastmoney_page_response(rows)

        with (
            mock.patch.object(server, "now_cn", return_value=observed),
            mock.patch.object(server, "market_data_get_with_retry", side_effect=market_response),
        ):
            rows, discovery = server._fetch_eastmoney_dynamic_rows("hk")
        selected, coverage = server.select_dynamic_market_pool(rows, "hk")

        self.assertEqual(len(selected), 200)
        self.assertGreaterEqual(coverage["eligible_discovery_size"], 210)
        self.assertNotIn("0001.HK", {row["symbol"] for row in rows})
        self.assertGreaterEqual(discovery["excluded_counts"]["invalid_source_timestamp"], 1)
        self.assertTrue(discovery["discovery_pagination_complete"])

    def test_hk_adaptive_pages_fail_closed_on_failure_duplicate_and_max_shortfall(self) -> None:
        observed = dt.datetime.fromisoformat("2026-08-26T09:40:00+08:00")
        source_timestamp = int(dt.datetime.fromisoformat("2026-08-26T09:25:00+08:00").timestamp())

        for scenario in ("page_failure", "duplicate_page", "max_shortfall"):
            with self.subTest(scenario=scenario):
                calls: list[int] = []

                def market_response(*_args, **kwargs):
                    page = int(kwargs["params"]["pn"])
                    calls.append(page)
                    if scenario == "page_failure" and page == 3:
                        raise requests.ConnectionError("fixture page failure")
                    first = (page - 1) * 100 + 1
                    rows = []
                    for number in range(first, first + 100):
                        symbol_number = number
                        if page >= 3:
                            if scenario == "max_shortfall":
                                symbol_number = 101 + ((number - first) % 100)
                            else:
                                symbol_number = number - 100
                        rows.append(
                            eastmoney_hk_fixture_row(
                                number,
                                source_timestamp,
                                amount=30_000_000 if page <= 2 else 3_000_000,
                                symbol_number=symbol_number,
                            )
                        )
                    return eastmoney_page_response(rows)

                with (
                    mock.patch.object(server, "now_cn", return_value=observed),
                    mock.patch.object(server, "market_data_get_with_retry", side_effect=market_response),
                ):
                    rows, discovery = server._fetch_eastmoney_dynamic_rows("hk")
                selected, coverage = server.select_dynamic_market_pool(rows, "hk")
                coverage = server._complete_dynamic_market_coverage(
                    selected, coverage, discovery, "hk", as_of=observed
                )

                self.assertFalse(server._dynamic_market_discovery_is_live_complete(coverage, "hk"))
                if scenario == "page_failure":
                    self.assertEqual(discovery["discovery_adaptive_requested_pages"], 2)
                    self.assertEqual(discovery["discovery_adaptive_completed_pages"], 1)
                    self.assertEqual(discovery["discovery_adaptive_stop_reason"], "minimum_eligible_met")
                    self.assertFalse(discovery["discovery_pagination_complete"])
                elif scenario == "duplicate_page":
                    self.assertEqual(discovery["discovery_adaptive_requested_pages"], 2)
                    self.assertFalse(discovery["discovery_page_signatures_unique"])
                    self.assertFalse(discovery["discovery_pagination_complete"])
                else:
                    self.assertEqual(
                        discovery["discovery_adaptive_requested_pages"],
                        server.HK_ADAPTIVE_LIQUIDITY_MAX_PAGE - 2,
                    )
                    self.assertEqual(discovery["discovery_adaptive_stop_reason"], "max_pages_reached")
                    self.assertEqual(coverage["eligible_discovery_size"], 200)
                    self.assertLess(coverage["eligible_discovery_size"], server.DYNAMIC_MARKET_MIN_ELIGIBLE["hk"])
                    self.assertIn(server.HK_ADAPTIVE_LIQUIDITY_MAX_PAGE, calls)

    def test_dynamic_pool_health_uses_exact_98_percent_boundary(self) -> None:
        as_of = dt.datetime.fromisoformat("2026-08-23T10:00:00+08:00")
        source_timestamp = int(dt.datetime.fromisoformat("2026-08-22T04:00:00+08:00").timestamp())
        rows = []
        for index in range(320):
            rows.append(
                {
                    "symbol": f"B{index:03d}",
                    "name": f"B{index:03d}",
                    "source": "fixture_market",
                    "reason": "fixture",
                    "observed_at": "2026-08-21T16:10:00+08:00",
                    "recall_routes": ["liquidity", "momentum", "pullback", "activity", "quality"],
                    "recall_metrics": {"amount": 1e8 + index, "market_cap": 2e9 + index, "volume": 1e6 + index, "change_pct": 1, "source_timestamp": source_timestamp},
                    "themes": [],
                    "lens": server._dynamic_neutral_lens("us"),
                    "candidate_lineage": {"universe_origin": server.DYNAMIC_MARKET_ORIGIN},
                }
            )
        selected, coverage = server.select_dynamic_market_pool(rows, "us")
        coverage.update({"raw_discovery_size": 320, "discovery_pagination_complete": True})
        coverage.update(server._dynamic_source_time_coverage(selected, "us", as_of=as_of))
        healthy = server.dynamic_market_pool_health(
            "us",
            coverage,
            {"requested_count": 300, "quote_count": 294, "realtime_count": 294},
            scored_count=294,
            as_of=as_of,
        )
        degraded = server.dynamic_market_pool_health(
            "us",
            coverage,
            {"requested_count": 300, "quote_count": 293, "realtime_count": 293},
            scored_count=293,
            as_of=as_of,
        )
        self.assertEqual(healthy["status"], "healthy")
        self.assertEqual(degraded["status"], "degraded")
        self.assertIn("DYNAMIC_SCORE_COVERAGE_BELOW_MINIMUM", degraded["reason_codes"])

    def test_dynamic_pool_without_verifiable_source_time_is_degraded(self) -> None:
        rows = [
            {
                "symbol": f"{index + 1:04d}.HK",
                "name": f"HK{index + 1:04d}",
                "source": "fixture_market",
                "reason": "fixture",
                "observed_at": "2026-08-21T16:10:00+08:00",
                "recall_routes": ["liquidity", "momentum", "pullback", "activity", "quality"],
                "recall_metrics": {
                    "amount": 100_000_000 + index,
                    "market_cap": 2_000_000_000 + index,
                    "volume": 1_000_000 + index,
                    "change_pct": 1,
                },
                "themes": [],
                "lens": server._dynamic_neutral_lens("hk"),
                "candidate_lineage": {"universe_origin": server.DYNAMIC_MARKET_ORIGIN},
            }
            for index in range(230)
        ]
        selected, coverage = server.select_dynamic_market_pool(rows, "hk")
        coverage.update({"raw_discovery_size": 230, "discovery_pagination_complete": True})
        coverage.update(server._dynamic_source_time_coverage(selected, "hk"))

        health = server.dynamic_market_pool_health(
            "hk",
            coverage,
            {"requested_count": 200, "quote_count": 200, "realtime_count": 200},
            scored_count=200,
        )

        self.assertEqual(health["status"], "degraded")
        self.assertIn("DYNAMIC_DISCOVERY_SOURCE_TIME_UNAVAILABLE", health["reason_codes"])

    def test_dynamic_source_failure_never_backfills_the_legacy_static_pool(self) -> None:
        unavailable = {
            "discovery_source": "fixture unavailable",
            "discovery_retrieved_at": "2026-08-23T10:00:00+08:00",
            "discovery_source_as_of": None,
            "discovery_reported_total": None,
            "discovery_requested_pages": 10,
            "discovery_completed_pages": 0,
            "discovery_pagination_complete": False,
            "raw_discovery_size": 0,
            "excluded_counts": {},
        }
        with (
            mock.patch.object(server, "_fetch_eastmoney_dynamic_rows", return_value=([], unavailable)),
            mock.patch.object(server, "_fetch_sina_hk_dynamic_rows", return_value=([], unavailable)),
            mock.patch.object(server, "_load_dynamic_market_cache", return_value=None),
            mock.patch.object(server, "market_universe", side_effect=AssertionError("static pool used")),
        ):
            selected, coverage = server.load_dynamic_market_pool("hk")

        self.assertEqual(selected, [])
        self.assertEqual(coverage["recall_selected_size"], 0)
        self.assertEqual(coverage["universe_origin"], server.DYNAMIC_MARKET_ORIGIN)

    def test_friday_dynamic_cache_remains_session_valid_on_monday_premarket(self) -> None:
        friday_source = dt.datetime.fromisoformat("2026-08-21T16:00:00+08:00")
        monday_premarket = dt.datetime.fromisoformat("2026-08-24T08:00:00+08:00")
        candidates = [
            {
                "symbol": f"{index + 1:04d}.HK",
                "name": f"HK{index + 1:04d}",
                "source": "fixture",
                "recall_metrics": {"source_timestamp": int(friday_source.timestamp())},
                "candidate_lineage": {"universe_origin": server.DYNAMIC_MARKET_ORIGIN},
            }
            for index in range(200)
        ]
        payload = {
            "markets": {
                "hk": {
                    "cached_at": friday_source.isoformat(),
                    "candidates": candidates,
                    "coverage": {"recall_target": 200, "recall_selected_size": 200},
                }
            }
        }
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = pathlib.Path(temporary) / "hk_us_dynamic_recall.json"
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            with (
                mock.patch.object(server, "DYNAMIC_MARKET_CACHE", cache_path),
                mock.patch.object(server, "now_cn", return_value=monday_premarket),
            ):
                loaded = server._load_dynamic_market_cache("hk")

        self.assertIsNotNone(loaded)
        cached_rows, coverage = loaded
        self.assertEqual(len(cached_rows), 200)
        self.assertEqual(coverage["universe_origin"], server.DYNAMIC_MARKET_CACHE_ORIGIN)
        self.assertEqual(coverage["selected_source_fresh_coverage"], 1.0)

    def test_dynamic_market_amount_and_cap_use_within_market_percentiles(self) -> None:
        rows = [
            {"recall_metrics": {"amount": 10, "market_cap": 100}},
            {"recall_metrics": {"amount": 20, "market_cap": 300}},
            {"recall_metrics": {"amount": 30, "market_cap": 200}},
        ]

        server.attach_dynamic_market_percentiles(rows)

        self.assertEqual([row["market_liquidity_percentile"] for row in rows], [0.0, 0.5, 1.0])
        self.assertEqual([row["market_cap_percentile"] for row in rows], [0.0, 1.0, 0.5])

    def test_dynamic_pagination_rejects_duplicate_page_signatures(self) -> None:
        self.assertFalse(
            server._dynamic_page_signatures_are_unique(
                {"liquidity": {1: ("AAA", "BBB"), 2: ("AAA", "BBB")}}
            )
        )
        self.assertTrue(
            server._dynamic_page_signatures_are_unique(
                {"liquidity": {1: ("AAA", "BBB"), 2: ("CCC", "DDD")}}
            )
        )

    def test_degraded_dynamic_pool_blocks_market_recommendation(self) -> None:
        decision = server.make_serenity_decision(
            [decision_ready_candidate("NVDA")],
            "us",
            quote_health={"status": "available", "quote_coverage": 1.0, "realtime_coverage": 1.0},
            pool_health={"status": "degraded", "reason_codes": ["DYNAMIC_RECALL_TARGET_NOT_MET"]},
        )
        self.assertEqual(decision["action"], "NO_TRADE")
        self.assertIn("POOL_COVERAGE_INSUFFICIENT", decision["blocker_codes"])

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
        current_kline = fixture_kline(40)
        current_kline[-1] = {**current_kline[-1], "date": "2026-08-21"}
        with (
            mock.patch.object(server, "yahoo_realtime_quotes", return_value=live),
            mock.patch.object(server, "yahoo_kline_map", return_value={"AAA": current_kline}),
            mock.patch.object(server, "cached_market_kline", return_value=[]),
            mock.patch.object(server.time, "sleep"),
        ):
            scored = server.score_serenity_candidates(
                "us",
                universe,
                as_of=dt.datetime.fromisoformat("2026-08-21T22:00:05+08:00"),
            )

        self.assertEqual(scored["quote_health"]["status"], "partial")
        self.assertEqual(scored["quote_health"]["requested_count"], 2)
        self.assertEqual(scored["quote_health"]["quote_count"], 1)
        self.assertEqual(scored["quote_health"]["realtime_count"], 1)
        self.assertEqual(scored["quote_health"]["quote_coverage"], 0.5)

    def test_hk_us_live_daily_kline_rejects_multi_session_stale_rows(self) -> None:
        stale_rows = fixture_kline(40)
        stale_rows[-1] = {**stale_rows[-1], "date": "2026-08-18"}
        as_of = dt.datetime.fromisoformat("2026-08-21T22:00:00+08:00")

        with (
            mock.patch.object(server, "yahoo_chart_kline", return_value=stale_rows) as fetch,
            mock.patch.object(server, "_load_hk_us_kline_cache", return_value={}),
            mock.patch.object(server, "_save_hk_us_kline_cache") as save_cache,
        ):
            result = server.yahoo_kline_map(
                ["AAA"], 90, "us", as_of=as_of
            )

        self.assertEqual(result, {})
        self.assertEqual(fetch.call_count, 3)
        save_cache.assert_called_once_with("us", {})

    def test_hk_us_stale_history_fallback_does_not_count_as_scored(self) -> None:
        stale_rows = fixture_kline(40)
        stale_rows[-1] = {**stale_rows[-1], "date": "2026-08-18"}
        as_of = dt.datetime.fromisoformat("2026-08-21T22:00:00+08:00")
        universe = [{"symbol": "AAA", "name": "AAA", "themes": [], "lens": {}}]
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
            mock.patch.object(server, "now_cn", return_value=as_of),
            mock.patch.object(server, "yahoo_realtime_quotes", return_value=live),
            mock.patch.object(server, "yahoo_kline_map", return_value={}),
            mock.patch.object(server, "cached_market_kline", return_value=stale_rows),
        ):
            scored = server.score_serenity_candidates("us", universe)

        self.assertEqual(scored["candidates"], [])
        self.assertEqual(scored["scored_size"], 0)
        self.assertEqual(scored["quote_health"]["quote_count"], 0)

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
        for rows in klines.values():
            rows[-1] = {**rows[-1], "date": "2026-08-21"}
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

    def test_a_share_full_pool_technical_score_precedes_deep_research(self) -> None:
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
                "high": 10.1,
                "low": 9.9,
                "volume": 10_000,
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

        klines = {}
        for code, marker in zip(codes, (1.0, 30.0, 20.0)):
            rows = fixture_kline(32)
            rows[-1] = {**rows[-1], "close": marker}
            klines[code] = rows

        def chan(rows: list[dict]) -> dict:
            return {"score": rows[-1]["close"], "signals": [], "warnings": [], "metrics": {}}

        with (
            mock.patch.object(server, "tencent_quote", return_value={code: quote(code) for code in codes}),
            mock.patch.object(server, "daily_dragon_tiger", return_value={}),
            mock.patch.object(server, "a_share_kline_map", return_value=klines) as kline_batch,
            mock.patch.object(server, "overlay_a_share_quote_bar", side_effect=lambda rows, _quote: rows),
            mock.patch.object(server, "chan_signal", side_effect=chan),
            mock.patch.object(
                server,
                "czsc_structure_score",
                return_value={"score": 0.0, "signals": [], "warnings": [], "metrics": {}},
            ),
            mock.patch.object(server, "run_dual_low_analysis", return_value={"by_code": {}, "metadata": {}}),
            mock.patch.dict(server.os.environ, {"CHAN_MAX_KLINE_CHECKS": "2"}),
        ):
            scored = server.score_candidates(
                "2026-08-21",
                [{"code": code, "reason": "测试", "candidate_lineage": {}} for code in codes],
                {"risk": "normal"},
            )

        self.assertEqual(kline_batch.call_args.args[0], list(codes))
        self.assertEqual(scored["base_scored_size"], 3)
        self.assertEqual(scored["technical_attempted_size"], 3)
        self.assertEqual(scored["technical_scored_size"], 3)
        self.assertEqual(scored["technical_kline_complete_size"], 3)
        self.assertEqual(scored["technical_kline_coverage"], 1.0)
        self.assertEqual(scored["deep_eligible_size"], 3)
        self.assertEqual(scored["deep_attempted_size"], 2)
        self.assertEqual(scored["deep_scored_size"], 2)
        self.assertEqual(scored["scored_size"], 2)
        self.assertEqual([row["code"] for row in scored["candidates"]], ["000001", "300001"])
        self.assertTrue(all(row["score_tier"] == "deep_legacy" for row in scored["candidates"]))
        self.assertEqual(len(scored["research_candidates"]), 3)
        by_code = {row["code"]: row for row in scored["research_candidates"]}
        self.assertEqual(by_code["600000"]["score_tier"], "technical_only")
        self.assertFalse(by_code["600000"]["legacy_complete"])
        self.assertIsNone(by_code["600000"]["recommendation_degree"])
        self.assertNotIn("uzi_score", by_code["600000"])

    def test_a_share_kline_retry_only_refetches_missing_codes(self) -> None:
        calls = {"600000": 0, "000001": 0, "300001": 0}

        def fetch(code: str, _limit: int) -> list[dict]:
            calls[code] += 1
            if code == "600000" or (code == "000001" and calls[code] >= 2):
                rows = fixture_kline(32)
                rows[-1] = {**rows[-1], "date": "2026-08-20"}
                return rows
            return []

        with (
            mock.patch.object(server, "_load_a_share_kline_cache", return_value={}),
            mock.patch.object(server, "_save_a_share_kline_cache") as save_cache,
            mock.patch.object(server, "expected_quote_session", return_value=dt.date(2026, 8, 21)),
            mock.patch.object(server, "qfq_stock_kline", side_effect=fetch),
        ):
            result = server.a_share_kline_map(list(calls))

        self.assertEqual(set(result), {"600000", "000001"})
        self.assertEqual(calls, {"600000": 1, "000001": 2, "300001": 3})
        self.assertEqual(set(save_cache.call_args.args[0]), {"600000", "000001"})

    def test_a_share_kline_rejects_multi_session_stale_provider_rows(self) -> None:
        stale_rows = fixture_kline(70)
        stale_rows[-1] = {**stale_rows[-1], "date": "2026-08-17"}
        current_rows = fixture_kline(32)
        current_rows[-1] = {**current_rows[-1], "date": "2026-08-20"}

        def fetch(code: str, _limit: int) -> list[dict]:
            return stale_rows if code == "600000" else current_rows

        with (
            mock.patch.object(server, "_load_a_share_kline_cache", return_value={}),
            mock.patch.object(server, "_save_a_share_kline_cache") as save_cache,
            mock.patch.object(server, "expected_quote_session", return_value=dt.date(2026, 8, 21)),
            mock.patch.object(server, "qfq_stock_kline", side_effect=fetch),
        ):
            result = server.a_share_kline_map(["600000", "000001"])

        self.assertEqual(set(result), {"000001"})
        self.assertEqual(set(save_cache.call_args.args[0]), {"000001"})

    def test_model_kline_chain_excludes_baidu_and_uses_explicit_adjustment_fallbacks(self) -> None:
        fallback_rows = fixture_kline(32)
        with (
            mock.patch.object(server, "baidu_stock_kline") as baidu,
            mock.patch.object(server, "eastmoney_stock_kline", return_value=[]) as eastmoney,
            mock.patch.object(server, "tencent_stock_kline", return_value=[]) as tencent,
            mock.patch.object(server, "yahoo_chart_kline", return_value=fallback_rows) as yahoo,
        ):
            rows = server.qfq_stock_kline("600000", 32)

        self.assertEqual(rows, fallback_rows)
        baidu.assert_not_called()
        eastmoney.assert_called_once_with("600000", 32)
        tencent.assert_called_once_with("600000", 32, require_qfq=True)
        yahoo.assert_called_once_with("600000.SS", 32)

    def test_model_kline_chain_stops_after_explicit_tencent_qfq(self) -> None:
        fallback_rows = fixture_kline(32)
        with (
            mock.patch.object(server, "eastmoney_stock_kline", return_value=[]),
            mock.patch.object(server, "tencent_stock_kline", return_value=fallback_rows),
            mock.patch.object(server, "yahoo_chart_kline") as yahoo,
        ):
            rows = server.qfq_stock_kline("000001", 32)

        self.assertEqual(rows, fallback_rows)
        yahoo.assert_not_called()

    def test_cached_a_share_kline_uses_current_quote_as_latest_bar(self) -> None:
        rows = fixture_kline(32)
        rows[-1] = {**rows[-1], "date": "2026-08-20", "close": 9.8}
        quote = {
            "price": 10.5,
            "open": 10.0,
            "high": 10.8,
            "low": 9.9,
            "volume": 12345,
            "amount_wan": 6789,
            "amplitude_pct": 9.0,
            "change_pct": 7.14,
            "turnover_pct": 3.2,
            "realtime": {"source_as_of": "2026-08-21T10:17:00+08:00"},
        }

        updated = server.overlay_a_share_quote_bar(rows, quote)

        self.assertEqual(updated[-1]["date"], "2026-08-21")
        self.assertEqual(updated[-1]["close"], 10.5)
        self.assertEqual(updated[-1]["volume"], 12345)

    def test_a_share_technical_score_excludes_incomplete_kline(self) -> None:
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
            mock.patch.object(server, "overlay_a_share_quote_bar", side_effect=lambda rows, _quote: rows),
            mock.patch.object(server, "run_dual_low_analysis", return_value={"by_code": {}, "metadata": {}}),
            mock.patch.dict(server.os.environ, {"CHAN_MAX_KLINE_CHECKS": "3"}),
        ):
            scored = server.score_candidates(
                "2026-08-21",
                [{"code": code, "reason": "测试", "candidate_lineage": {}} for code in codes],
                {"risk": "normal"},
            )

        self.assertEqual(scored["base_scored_size"], 3)
        self.assertEqual(scored["technical_attempted_size"], 3)
        self.assertEqual(scored["technical_scored_size"], 3)
        self.assertEqual(scored["technical_kline_complete_size"], 1)
        self.assertEqual(scored["technical_kline_coverage"], 0.3333)
        self.assertEqual(scored["deep_eligible_size"], 1)
        self.assertEqual(scored["deep_attempted_size"], 1)
        self.assertEqual(scored["deep_scored_size"], 1)
        self.assertEqual(scored["scored_size"], 1)
        self.assertEqual(scored["deep_kline_coverage"], 1.0)
        self.assertEqual([row["code"] for row in scored["candidates"]], ["600000"])

    def test_a_share_deep_pool_counts_only_trade_eligible_rows(self) -> None:
        codes = ("600000", "600001", "300001")

        def quote(code: str) -> dict:
            return {
                "code": code,
                "name": "ST测试" if code == "600001" else code,
                "price": 10.0,
                "entry_price": 10.0,
                "current_price": 10.0,
                "last_close": 9.9,
                "open": 9.95,
                "high": 10.1,
                "low": 9.9,
                "volume": 10_000,
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
            mock.patch.object(server, "a_share_kline_map", return_value={code: fixture_kline(32) for code in codes}),
            mock.patch.object(server, "overlay_a_share_quote_bar", side_effect=lambda rows, _quote: rows),
            mock.patch.object(server, "run_dual_low_analysis", return_value={"by_code": {}, "metadata": {}}),
            mock.patch.dict(server.os.environ, {"CHAN_MAX_KLINE_CHECKS": "3"}),
        ):
            scored = server.score_candidates(
                "2026-08-21",
                [{"code": code, "reason": "测试", "candidate_lineage": {}} for code in codes],
                {"risk": "normal"},
            )

        self.assertEqual(scored["base_scored_size"], 3)
        self.assertEqual(scored["technical_scored_size"], 3)
        self.assertEqual(scored["technical_kline_complete_size"], 3)
        self.assertEqual(scored["deep_eligible_size"], 2)
        self.assertEqual(scored["deep_attempted_size"], 2)
        self.assertEqual(scored["deep_scored_size"], 2)
        self.assertNotIn("600001", [row["code"] for row in scored["candidates"]])
        technical_st = next(row for row in scored["research_candidates"] if row["code"] == "600001")
        self.assertFalse(technical_st["technical_screen_eligible"])
        server.attach_candidate_v2(
            technical_st,
            "a_share",
            {"risk": "normal", "items": [{"change_pct": 0.1}]},
        )
        self.assertEqual(technical_st["execution_state"], "BLOCKED")
        self.assertIn(
            "SECURITY_NOT_DEEP_RESEARCH_ELIGIBLE",
            {item["code"] for item in technical_st["risk_items"]},
        )

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
                mock.patch.object(
                    server,
                    "load_dynamic_market_pool",
                    side_effect=lambda market, **_kwargs: (
                        [],
                        {
                            "universe_origin": server.DYNAMIC_MARKET_ORIGIN,
                            "recall_target": 200 if market == "hk" else 300,
                            "recall_selected_size": 0,
                            "recall_shortfall": 200 if market == "hk" else 300,
                            "eligible_discovery_size": 0,
                            "min_eligible_discovery_size": 210 if market == "hk" else 315,
                            "raw_discovery_size": 0,
                            "discovery_pagination_complete": False,
                            "route_counts": {},
                            "recall_manifest": [],
                            "source_counts": {},
                        },
                    ),
                ) as load_dynamic_pool,
                mock.patch.object(
                    server,
                    "score_serenity_candidates",
                    return_value={"candidates": [], "raw_pool_size": 0, "scored_size": 0},
                ) as score_dynamic_pool,
                mock.patch.object(
                    server,
                    "dynamic_market_pool_health",
                    wraps=server.dynamic_market_pool_health,
                ) as dynamic_pool_health,
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
        hk_us_anchors = [
            call.kwargs.get("as_of")
            for patched in (load_dynamic_pool, score_dynamic_pool, dynamic_pool_health)
            for call in patched.call_args_list
        ]
        self.assertEqual(len(hk_us_anchors), 6)
        self.assertTrue(all(anchor is hk_us_anchors[0] for anchor in hk_us_anchors))

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

    def test_a_share_technical_and_deep_coverage_have_separate_gates(self) -> None:
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
            technical_attempted_count=300,
            technical_completed_count=294,
            deep_eligible_count=294,
            deep_attempted_count=294,
            deep_completed_count=289,
            merged_count=300,
            recall_coverage=recall,
        )
        degraded = server.a_share_pool_health(
            broad,
            quote_count=300,
            technical_attempted_count=300,
            technical_completed_count=293,
            deep_eligible_count=293,
            deep_attempted_count=293,
            deep_completed_count=288,
            merged_count=300,
            recall_coverage=recall,
        )

        self.assertEqual(healthy["status"], "healthy")
        self.assertNotIn("A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM", healthy["reason_codes"])
        self.assertEqual(degraded["status"], "degraded")
        self.assertIn("A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM", degraded["reason_codes"])

        deep_degraded = server.a_share_pool_health(
            broad,
            quote_count=300,
            technical_attempted_count=300,
            technical_completed_count=294,
            deep_eligible_count=294,
            deep_attempted_count=294,
            deep_completed_count=288,
            merged_count=300,
            recall_coverage=recall,
        )
        self.assertIn("A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM", deep_degraded["reason_codes"])

    def test_a_share_deep_eligibility_uses_98_percent_of_complete_technical_pool(self) -> None:
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
            technical_attempted_count=300,
            technical_completed_count=297,
            deep_eligible_count=295,
            deep_attempted_count=295,
            deep_completed_count=295,
            merged_count=300,
            recall_coverage=recall,
        )
        below_minimum = server.a_share_pool_health(
            broad,
            quote_count=300,
            technical_attempted_count=300,
            technical_completed_count=297,
            deep_eligible_count=291,
            deep_attempted_count=291,
            deep_completed_count=291,
            merged_count=300,
            recall_coverage=recall,
        )

        self.assertEqual(healthy["status"], "healthy")
        self.assertEqual(healthy["deep_eligibility_target_count"], 297)
        self.assertEqual(healthy["deep_eligibility_coverage"], 0.9933)
        self.assertEqual(healthy["expected_deep_attempted_count"], 295)
        self.assertNotIn(
            "A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM",
            healthy["reason_codes"],
        )
        self.assertEqual(below_minimum["deep_eligibility_coverage"], 0.9798)
        self.assertIn(
            "A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM",
            below_minimum["reason_codes"],
        )

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

    def test_historical_replay_loader_publishes_only_a_non_authorizing_summary(self) -> None:
        fake_module = mock.Mock()
        fake_module.validate_replay_artifact.side_effect = lambda payload: payload
        fake_module.public_model_summary.return_value = {
            "schema_version": "archived-shortlist-replay-summary-v1",
            "status": "READY",
            "cohort_count": 7,
            "shortlist_count": 21,
            "settled_count": 15,
            "pending_count": 6,
            "metrics": {"sample_count": 15, "mean_net_return": 0.01},
            # The server must override any accidental authority claim.
            "participates_in_decision": True,
            "promotion_eligible": True,
            "authorizes_production": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "replay.json"
            path.write_text(json.dumps({"fixture": True}), encoding="utf-8")
            with mock.patch.object(server, "historical_replay", fake_module):
                summary = server.load_historical_replay_summary(path)

        self.assertEqual(summary["evidence_class"], "RETROSPECTIVE")
        self.assertEqual(summary["universe_scope"], "ARCHIVED_SHORTLIST_ONLY")
        self.assertFalse(summary["full_point_in_time_universe"])
        for field in (
            "included_in_live_observation_performance",
            "included_in_shadow_research",
            "included_in_executable_performance",
            "calibrated",
            "participates_in_decision",
            "production_eligible",
            "promotion_eligible",
            "authorizes_production",
        ):
            self.assertIs(summary[field], False)
        fake_module.validate_replay_artifact.assert_called_once_with({"fixture": True})

    def test_historical_replay_loader_fails_closed_for_missing_or_bad_artifact(self) -> None:
        fake_module = mock.Mock()
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with mock.patch.object(server, "historical_replay", fake_module):
                missing = server.load_historical_replay_summary(root / "missing.json")
                invalid_path = root / "invalid.json"
                invalid_path.write_text("{", encoding="utf-8")
                invalid = server.load_historical_replay_summary(invalid_path)

        self.assertEqual(missing["status"], "UNAVAILABLE")
        self.assertEqual(missing["reason_codes"], ["HISTORICAL_REPLAY_ARTIFACT_MISSING"])
        self.assertEqual(invalid["reason_codes"], ["HISTORICAL_REPLAY_ARTIFACT_UNREADABLE"])
        for summary in (missing, invalid):
            self.assertFalse(summary["participates_in_decision"])
            self.assertFalse(summary["promotion_eligible"])
            self.assertFalse(summary["authorizes_production"])


if __name__ == "__main__":
    unittest.main()

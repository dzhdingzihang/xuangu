from __future__ import annotations

import copy
import datetime as dt
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
        self.assertEqual(server.broad_recall_routes(row), ["liquidity", "pullback"])

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

    def test_explicit_stale_quote_only_blocks_in_regular_session(self) -> None:
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
        self.assertNotEqual(closed_gate["status"], "BLOCK")
        self.assertNotIn("STALE_QUOTE", {item["code"] for item in closed["risk_items"]})

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

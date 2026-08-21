from __future__ import annotations

import copy
import datetime as dt
import unittest

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


class SelectorV2Tests(unittest.TestCase):
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

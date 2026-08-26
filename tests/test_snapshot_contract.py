from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock

import production_rule_model
import server
from scripts.validate_snapshot import (
    dynamic_manifest_source_freshness,
    validate_snapshot,
    validate_snapshot_file,
)
from tests.test_selector_v2 import fixture_candidate


def snapshot_fixture() -> dict:
    markets = {}
    targets = {"a_share": 300, "hk": 200, "us": 300}
    for market_key, code in (("a_share", "603228"), ("hk", "0700.HK"), ("us", "NVDA")):
        row = fixture_candidate()
        row["code"] = code
        row["symbol"] = code
        row["market_key"] = market_key
        row.pop("candidate_lineage", None)
        row["realtime"].update(
            {
                "price": row["price"],
                "source_as_of": "2026-08-19T16:00:00+08:00",
                "volume_unit": "lot" if market_key == "a_share" else "share",
            }
        )
        stats = {
            "recall_target": targets[market_key],
            "recall_selected_size": targets[market_key],
            "recall_shortfall": 0,
            "raw_pool_size": targets[market_key],
            "universe_size": targets[market_key],
            "valid_quote_size": targets[market_key],
            "deep_scored_size": targets[market_key],
            "scored_size": targets[market_key],
            "source_counts": {"fixture": targets[market_key]},
        }
        if market_key == "a_share":
            stats.update(
                {
                    "base_scored_size": targets[market_key],
                    "technical_attempted_size": targets[market_key],
                    "technical_scored_size": targets[market_key],
                    "technical_kline_complete_size": targets[market_key],
                    "technical_kline_coverage": 1.0,
                    "deep_score_limit": 300,
                    "deep_eligible_size": targets[market_key],
                    "deep_attempted_size": 300,
                    "deep_kline_coverage": 1.0,
                    "board_targets": dict(server.A_SHARE_BOARD_TARGETS),
                    "board_counts": dict(server.A_SHARE_BOARD_TARGETS),
                    "board_shortfalls": {},
                    "route_targets": dict(server.A_SHARE_ROUTE_TARGETS),
                    "route_counts": dict(server.A_SHARE_ROUTE_TARGETS),
                    "route_shortfalls": {},
                }
            )
        markets[market_key] = {
            "key": market_key,
            "label": market_key,
            "decision": {
                "action": "BUY_CANDIDATE",
                "title": "两周推荐",
                "message": "legacy decision",
                "primary": row,
                "watchlist": [],
            },
            "stats": stats,
            "quote_health": {
                "status": "available",
                "requested_count": targets[market_key],
                "quote_count": targets[market_key],
                "quote_coverage": 1.0,
                "reason_codes": [],
                **(
                    {
                        "realtime_count": targets[market_key],
                        "stale_realtime_count": 0,
                        "realtime_coverage": 1.0,
                        "freshness_policy": "latest_exchange_session_v1",
                        "freshness_reference_session": "2026-08-19" if market_key == "hk" else "2026-08-18",
                    }
                    if market_key in {"hk", "us"}
                    else {}
                ),
            },
        }
        if market_key == "a_share":
            markets[market_key]["pool_health"] = {
                "contract_version": server.A_SHARE_POOL_HEALTH_CONTRACT_VERSION,
                "status": "healthy",
                "reason_codes": [],
                "technical_attempted_count": 300,
                "technical_completed_count": 300,
                "technical_score_coverage": 1.0,
                "min_technical_score_coverage": 0.98,
                "deep_eligible_count": 300,
                "deep_eligibility_target_count": 300,
                "deep_eligibility_coverage": 1.0,
                "min_deep_eligibility_coverage": 0.98,
                "deep_attempted_count": 300,
                "expected_deep_attempted_count": 300,
                "deep_completed_count": 300,
                "deep_score_coverage": 1.0,
                "min_deep_score_coverage": 0.98,
                "deep_score_limit": 300,
            }
    return {
        "model_version": "legacy-fixture",
        "generated_at": "2026-08-19T16:30:00+08:00",
        "snapshot_key": "2026-08-19_2026-08-19_163000.json",
        "market": {"risk": "normal", "items": []},
        "markets": markets,
    }


def current_v3_snapshot() -> dict:
    snapshot = snapshot_fixture()
    snapshot["model_version"] = server.MODEL_VERSION
    return server.enrich_snapshot_v2(snapshot)


def qualify_current_v3_row(
    snapshot: dict,
    index: int,
    *,
    code: str | None = None,
    with_positive_event: bool = True,
) -> None:
    row = snapshot["global_decision"]["evaluated_candidates"][index]
    market = row["market"]
    if code:
        row["code"] = code
    row.update(
        {
            "legacy_recommendation_degree": 80,
            "v2_rank": 1,
            "v2_rank_universe_size": 100,
            "event_candidate_scanned": True,
            "verified_positive_event_ids": ["evt-qualified"] if with_positive_event else [],
            "estimated_10d_range": {"low_pct": -4.0, "high_pct": 8.0},
            "blocker_codes": [] if with_positive_event else ["VERIFIED_POSITIVE_EVENT_MISSING"],
        }
    )
    snapshot["global_decision"]["market_states"][market].update(
        {"state": "READY", "reason_codes": []}
    )
    entry = snapshot["production_rule_inputs"]["rows"][index]
    entry.clear()
    entry.update(production_rule_model.freeze_production_rule_input_row(row, index))
    entry.update(
        {
            "market": market,
            "code": row["code"],
            "source_candidate_present": True,
            "source_data_quality_score": 100.0,
        }
    )
    candidate_snapshot = copy.deepcopy(snapshot["markets"][market]["decision"]["primary"])
    candidate_snapshot["code"] = row["code"]
    candidate_snapshot["symbol"] = row["code"]
    entry["candidate_snapshot"] = candidate_snapshot


def rebuild_current_v3(snapshot: dict) -> None:
    inputs = snapshot["production_rule_inputs"]
    inputs["ledger_sha256"] = production_rule_model.production_rule_inputs_sha256(inputs)
    snapshot["production_decision"] = production_rule_model.build_production_decision(snapshot)


def dynamic_hk_us_snapshot_fixture() -> dict:
    """Build a complete v2.5 fixture with auditable HK/US dynamic manifests."""

    snapshot = snapshot_fixture()
    snapshot["model_version"] = "smart-selector-2026-08-23.2-dynamic-hk-us"
    snapshot["universe_version"] = server.UNIVERSE_VERSION
    for market_key, primary_symbol in (("hk", "0700.HK"), ("us", "NVDA")):
        target = {"hk": server.HK_RECALL_TARGET, "us": server.US_RECALL_TARGET}[market_key]
        minimum = server.DYNAMIC_MARKET_MIN_ELIGIBLE[market_key]
        route_targets = dict(server.DYNAMIC_MARKET_ROUTE_TARGETS[market_key])
        primary_routes = [
            route
            for route, count in route_targets.items()
            for _ in range(count)
        ]
        symbols = [primary_symbol]
        if market_key == "hk":
            symbols.extend(f"{number:04d}.HK" for number in range(1, target + 1) if number != 700)
        else:
            symbols.extend(f"DYN{number:03d}" for number in range(1, target))
        symbols = symbols[:target]
        source_as_of = (
            "2026-08-19T16:00:00+08:00"
            if market_key == "hk"
            else "2026-08-19T04:00:00+08:00"
        )
        source_timestamp = int(dt.datetime.fromisoformat(source_as_of).timestamp())
        manifest = [
            {
                "symbol": symbol,
                "recall_rank": rank,
                "recall_score": round(100 - rank / 10, 4),
                "primary_route": primary_routes[rank - 1],
                "recall_routes": [primary_routes[rank - 1]],
                "source": f"eastmoney_delay_{market_key}_market",
                "observed_at": "2026-08-19T16:10:00+08:00",
                "recall_metrics": {
                    "price": 10 + rank / 100,
                    "amount": 100_000_000 + rank,
                    "amount_currency": "HKD" if market_key == "hk" else "USD",
                    "volume": 1_000_000 + rank,
                    "change_pct": 1.0,
                    "source_timestamp": source_timestamp,
                    **(
                        {
                            "liquidity_admission": "observed_amount",
                            "liquidity_policy_version": server.HK_INTRADAY_LIQUIDITY_POLICY_VERSION,
                            "liquidity_standard_amount_threshold": server.HK_STANDARD_MIN_AMOUNT_HKD,
                        }
                        if market_key == "hk"
                        else {}
                    ),
                    **(
                        {
                            "market_cap": 5_000_000_000,
                            "market_cap_currency": "HKD",
                            "market_cap_kind": "total",
                            "market_cap_source_field": "f20",
                        }
                        if market_key == "hk"
                        else {}
                    ),
                },
            }
            for rank, symbol in enumerate(symbols, 1)
        ]
        stats = snapshot["markets"][market_key]["stats"]
        stats.update(
            {
                "universe_origin": server.DYNAMIC_MARKET_ORIGIN,
                "universe_scope": "provider_bounded_common_equity_cross_section",
                "coverage_claim": "bounded_dynamic_scan",
                "recall_policy_version": server.DYNAMIC_MARKET_RECALL_POLICY_VERSION,
                "discovery_source": "Eastmoney delayed common-equity cross-section",
                "discovery_retrieved_at": "2026-08-19T16:10:00+08:00",
                "discovery_freshness_as_of": "2026-08-19T16:10:00+08:00",
                "discovery_freshness_reference_at": (
                    "2026-08-19T16:10:00+08:00"
                    if market_key == "hk"
                    else "2026-08-19T04:10:00-04:00"
                ),
                "discovery_source_as_of": source_as_of,
                "discovery_source_effective_as_of": (
                    "2026-08-19T15:59:00+08:00"
                    if market_key == "hk"
                    else source_as_of
                ),
                "discovery_expected_session": "2026-08-19" if market_key == "hk" else "2026-08-18",
                "discovery_session_phase": "post" if market_key == "hk" else "pre",
                "selected_source_time_count": target,
                "selected_source_time_coverage": 1.0,
                "selected_source_fresh_count": target,
                "selected_source_fresh_coverage": 1.0,
                "selected_source_stale_symbols": [],
                "discovery_pagination_complete": True,
                "discovery_reported_total": 2_913 if market_key == "hk" else 5_965,
                "discovery_requested_pages": 10,
                "discovery_completed_pages": 10,
                "raw_discovery_size": minimum + 100,
                "deduped_discovery_size": minimum + 25,
                "eligible_discovery_size": minimum + 25,
                "min_eligible_discovery_size": minimum,
                "route_targets": route_targets,
                "route_counts": route_targets,
                "route_hit_counts": route_targets,
                "route_shortfalls": {},
                "excluded_counts": {"security_type": 5},
                "recall_manifest": manifest,
                "raw_pool_size": target,
                "universe_size": target,
                "valid_quote_size": target,
                "deep_scored_size": target,
                "scored_size": target,
                "source_counts": {f"eastmoney_delay_{market_key}_market": target},
            }
        )
        snapshot["markets"][market_key]["pool_health"] = {
            "status": "healthy",
            "reason_codes": [],
            "warning_codes": [],
            "universe_origin": server.DYNAMIC_MARKET_ORIGIN,
            "target_count": target,
            "selected_count": target,
            "eligible_discovery_count": minimum + 25,
            "min_eligible_discovery_count": minimum,
            "raw_discovery_count": minimum + 100,
            "quote_count": target,
            "quote_coverage": 1.0,
            "realtime_count": target,
            "realtime_coverage": 1.0,
            "deep_scored_count": target,
            "deep_score_coverage": 1.0,
            "min_score_coverage": server.DYNAMIC_MARKET_MIN_SCORE_COVERAGE,
        }
        primary = snapshot["markets"][market_key]["decision"]["primary"]
        primary["candidate_lineage"] = {
            "universe_origin": server.DYNAMIC_MARKET_ORIGIN,
        }
        primary_manifest = manifest[0]
        primary["observed_at"] = primary_manifest["observed_at"]
        primary["recall_routes"] = copy.deepcopy(primary_manifest["recall_routes"])
        primary["recall_metrics"] = copy.deepcopy(primary_manifest["recall_metrics"])
    return server.enrich_snapshot_v2(snapshot)


def current_hk_intraday_snapshot_fixture() -> dict:
    """Publish one valid 09:40 XHKG scaled-liquidity row in both mirrors."""

    snapshot = dynamic_hk_us_snapshot_fixture()
    observed_at = "2026-08-19T09:40:00+08:00"
    source_timestamp = int(dt.datetime.fromisoformat("2026-08-19T09:25:00+08:00").timestamp())
    progress = round(10 / 330, 6)
    metrics = {
        "price": 10.01,
        "amount": 2_500_000,
        "amount_currency": "HKD",
        "volume": 1_000_001,
        "change_pct": 1.0,
        "market_cap": 5_000_000_000,
        "market_cap_currency": "HKD",
        "market_cap_kind": "total",
        "market_cap_source_field": "f20",
        "source_timestamp": source_timestamp,
        "liquidity_policy_version": server.HK_INTRADAY_LIQUIDITY_POLICY_VERSION,
        "liquidity_standard_amount_threshold": server.HK_STANDARD_MIN_AMOUNT_HKD,
        "liquidity_amount_threshold": server.HK_INTRADAY_MIN_AMOUNT_HKD,
        "liquidity_session_progress": progress,
        "liquidity_gate_progress": progress,
        "liquidity_data_progress": 0.0,
        "liquidity_gate_elapsed_minutes": 10.0,
        "liquidity_data_elapsed_minutes": 0.0,
        "liquidity_session_total_minutes": 330.0,
        "liquidity_reference_at": observed_at,
        "liquidity_freshness_reference_at": observed_at,
        "liquidity_source_effective_at": "2026-08-19T09:25:00+08:00",
        "liquidity_source_age_seconds": 900.0,
        "liquidity_source_age_minutes": 15.0,
        "liquidity_source_wall_age_minutes": 15.0,
        "liquidity_source_phase": "pre",
        "liquidity_gate_phase": "regular",
        "liquidity_session_open_at": "2026-08-19T09:30:00+08:00",
        "liquidity_session_break_start_at": "2026-08-19T12:00:00+08:00",
        "liquidity_session_break_end_at": "2026-08-19T13:00:00+08:00",
        "liquidity_session_close_at": "2026-08-19T16:00:00+08:00",
        "liquidity_intraday_scaling_eligible": True,
        "liquidity_admission": "intraday_scaled",
        "liquidity_projection_basis": "pre_no_linear_projection",
        "projected_full_session_amount": None,
    }
    manifest_row = snapshot["markets"]["hk"]["stats"]["recall_manifest"][0]
    candidate = snapshot["markets"]["hk"]["decision"]["primary"]
    for row in (manifest_row, candidate):
        row["observed_at"] = observed_at
        row["recall_metrics"] = copy.deepcopy(metrics)
        routes = list(row.get("recall_routes") or [])
        if "intraday_liquidity_completion" not in routes:
            routes.append("intraday_liquidity_completion")
        row["recall_routes"] = routes
    return snapshot


def install_generated_hk_intraday_row(
    snapshot: dict,
    *,
    observed_at: str,
    source_at: str,
    amount: float,
) -> dict:
    """Install generator output so validator parity can be tested at odd clocks."""

    generated, reason = server._dynamic_hk_candidate(
        {
            "symbol": "0700",
            "name": "腾讯控股",
            "lasttrade": 580,
            "volume": 1_000_000,
            "amount": amount,
            "market_cap": 5_000_000_000,
            "changepercent": 1,
            "ticktime": int(dt.datetime.fromisoformat(source_at).timestamp()),
        },
        "liquidity",
        observed_at,
    )
    if reason is not None or generated is None:
        raise AssertionError(f"HK fixture was not admitted: {reason}")
    generated["recall_metrics"].update(
        {
            "market_cap_currency": "HKD",
            "market_cap_kind": "total",
            "market_cap_source_field": "f20",
        }
    )
    manifest_row = snapshot["markets"]["hk"]["stats"]["recall_manifest"][0]
    candidate = snapshot["markets"]["hk"]["decision"]["primary"]
    for row in (manifest_row, candidate):
        row["observed_at"] = generated["observed_at"]
        row["recall_routes"] = copy.deepcopy(generated["recall_routes"])
        row["recall_metrics"] = copy.deepcopy(generated["recall_metrics"])
    return snapshot


class SnapshotContractTests(unittest.TestCase):
    def test_kline_cache_v2_retains_260_sessions_and_rejects_v1(self) -> None:
        self.assertEqual(server.MODEL_KLINE_MIN_HISTORY, 220)
        rows = [
            {
                "date": (dt.date(2025, 1, 1) + dt.timedelta(days=index)).isoformat(),
                "open": 10.0,
                "high": 10.5,
                "low": 9.5,
                "close": 10.1,
                "volume": 1000,
            }
            for index in range(280)
        ]
        with tempfile.TemporaryDirectory() as directory:
            cache_path = pathlib.Path(directory) / "a_share_daily.json"
            with mock.patch.object(server, "A_SHARE_KLINE_CACHE", cache_path):
                server._save_a_share_kline_cache({"600000": rows})
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["version"], server.A_SHARE_KLINE_CACHE_VERSION)
                self.assertEqual(
                    payload["adjustment_policy"],
                    server.A_SHARE_KLINE_ADJUSTMENT_POLICY,
                )
                self.assertEqual(len(payload["rows"]["600000"]), server.MODEL_KLINE_HISTORY_LIMIT)
                self.assertEqual(
                    len(server._load_a_share_kline_cache()["600000"]),
                    server.MODEL_KLINE_HISTORY_LIMIT,
                )

                payload["version"] = "a-share-daily-kline-v1"
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                self.assertEqual(server._load_a_share_kline_cache(), {})

                payload["version"] = server.A_SHARE_KLINE_CACHE_VERSION
                payload.pop("adjustment_policy")
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                self.assertEqual(server._load_a_share_kline_cache(), {})

                payload["adjustment_policy"] = "raw-unadjusted"
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                self.assertEqual(server._load_a_share_kline_cache(), {})

    def test_selector_shadow_builder_receives_three_caches_and_cannot_self_authorize(self) -> None:
        captured = {}

        def build(snapshot, kline_maps, generated_at):
            captured["snapshot"] = snapshot
            captured["kline_maps"] = kline_maps
            captured["generated_at"] = generated_at
            return {
                "model_id": server.TEN_DAY_SHADOW_MODEL_ID,
                "label_version": server.TEN_DAY_LABEL_VERSION,
                "feature_schema_version": server.TEN_DAY_SHADOW_FEATURE_SCHEMA,
                "status": "INSUFFICIENT_DATA",
                "calibrated": False,
                "costs_ready": True,
                "tail_risk_ready": True,
                "participates_in_decision": False,
                "production_eligible": False,
                "probability": None,
                "training_cutoff": None,
                "training_provenance": "current_universe_historical_backfill",
                "market_models": {},
                "validation": {},
                "limitations": ["fixture"],
                "artifact_sha256": "b" * 64,
                "shadow_predictions": [],
            }

        module = types.SimpleNamespace(build_snapshot_model_contract=build)
        snapshot = snapshot_fixture()
        generated_at = dt.datetime.fromisoformat(snapshot["generated_at"])
        maps = {
            "a_share": {"603228": [{"date": "2026-08-18"}]},
            "hk": {"0700.HK": [{"date": "2026-08-18"}]},
            "us": {"NVDA": [{"date": "2026-08-18"}]},
        }
        with (
            mock.patch.object(server, "ten_day_model", module),
            mock.patch.object(server, "_load_a_share_kline_cache", return_value=maps["a_share"]),
            mock.patch.object(server, "_load_hk_us_kline_cache", side_effect=lambda market: maps[market]),
        ):
            contract = server.build_ten_day_shadow_model_contract(snapshot, generated_at)

        self.assertEqual(set(captured["kline_maps"]), {"a_share", "hk", "us"})
        self.assertIs(captured["snapshot"], snapshot)
        self.assertEqual(captured["generated_at"], generated_at)
        self.assertEqual(contract["status"], "INSUFFICIENT_DATA")
        self.assertFalse(contract["calibrated"])
        self.assertFalse(contract["participates_in_decision"])
        self.assertFalse(contract["production_eligible"])
        self.assertNotIn("predictions", contract)

    def test_selector_rejects_a_shadow_contract_that_self_authorizes(self) -> None:
        module = types.SimpleNamespace(
            build_snapshot_model_contract=lambda *_: {
                "model_id": server.TEN_DAY_SHADOW_MODEL_ID,
                "label_version": server.TEN_DAY_LABEL_VERSION,
                "training_provenance": "current_universe_historical_backfill",
                "calibrated": True,
                "participates_in_decision": True,
                "production_eligible": True,
                "shadow_predictions": [],
            }
        )
        with (
            mock.patch.object(server, "ten_day_model", module),
            mock.patch.object(server, "_load_a_share_kline_cache", return_value={}),
            mock.patch.object(server, "_load_hk_us_kline_cache", return_value={}),
        ):
            contract = server.build_ten_day_shadow_model_contract(
                snapshot_fixture(),
                "2026-08-19T16:30:00+08:00",
            )

        self.assertEqual(contract["status"], "UNAVAILABLE")
        self.assertEqual(contract["reason_codes"], ["TEN_DAY_SHADOW_MODEL_INTEGRITY_ERROR"])
        self.assertFalse(contract["calibrated"])
        self.assertFalse(contract["participates_in_decision"])

    def test_dynamic_hk_us_snapshot_contract_is_auditable(self) -> None:
        enriched = dynamic_hk_us_snapshot_fixture()

        self.assertEqual(
            validate_snapshot(enriched),
            ["production_decision rule contract does not match model_version"],
        )
        for market_key, target in (("hk", 200), ("us", 300)):
            stats = enriched["markets"][market_key]["stats"]
            self.assertEqual(stats["universe_origin"], server.DYNAMIC_MARKET_ORIGIN)
            self.assertEqual(len(stats["recall_manifest"]), target)
            self.assertEqual(len({row["symbol"] for row in stats["recall_manifest"]}), target)

    def test_dynamic_hk_us_contract_rejects_manifest_and_origin_spoofing(self) -> None:
        missing_manifest_row = dynamic_hk_us_snapshot_fixture()
        missing_manifest_row["markets"]["hk"]["stats"]["recall_manifest"].pop()
        self.assertIn(
            "markets.hk.stats.recall_manifest size is invalid",
            validate_snapshot(missing_manifest_row),
        )

        unknown_origin = dynamic_hk_us_snapshot_fixture()
        unknown_origin["markets"]["us"]["stats"]["universe_origin"] = "dynamicish"
        errors = validate_snapshot(unknown_origin)
        self.assertIn("markets.us.stats.universe_origin is not a dynamic origin", errors)
        self.assertIn("global_decision.market_states.us.reason_codes are incomplete", errors)

        injected_candidate = dynamic_hk_us_snapshot_fixture()
        injected_candidate["markets"]["us"]["decision"]["primary"]["code"] = "STATIC"
        injected_candidate["markets"]["us"]["decision"]["primary"]["symbol"] = "STATIC"
        self.assertIn(
            "markets.us candidate is not present in dynamic recall_manifest",
            validate_snapshot(injected_candidate),
        )

    def test_current_hk_intraday_liquidity_is_rebuilt_from_xhkg_evidence(self) -> None:
        valid = current_hk_intraday_snapshot_fixture()
        self.assertEqual(
            validate_snapshot(valid),
            ["production_decision rule contract does not match model_version"],
        )

        attacks = {
            "currency": ("amount_currency", "USD"),
            "f20_kind": ("market_cap_kind", "float"),
            "f20_source": ("market_cap_source_field", "f21"),
            "threshold": ("liquidity_amount_threshold", 1),
            "progress": ("liquidity_session_progress", 0.9),
            "gate_progress": ("liquidity_gate_progress", 0.9),
            "data_progress": ("liquidity_data_progress", 0.5),
            "source_phase": ("liquidity_source_phase", "regular"),
            "source_effective": (
                "liquidity_source_effective_at",
                "2026-08-19T09:26:00+08:00",
            ),
            "pre_projection": ("projected_full_session_amount", 99_000_000),
            "policy": ("liquidity_policy_version", "forged-policy"),
            "floor": ("amount", 1_999_999),
            "market_cap": ("market_cap", 999_999_999),
            "prior_session": (
                "source_timestamp",
                int(dt.datetime.fromisoformat("2026-08-18T16:00:00+08:00").timestamp()),
            ),
            "stale": (
                "source_timestamp",
                int(dt.datetime.fromisoformat("2026-08-19T08:54:59+08:00").timestamp()),
            ),
            "future": (
                "source_timestamp",
                int(dt.datetime.fromisoformat("2026-08-19T09:45:01+08:00").timestamp()),
            ),
        }
        for label, (field, value) in attacks.items():
            with self.subTest(label=label):
                forged = current_hk_intraday_snapshot_fixture()
                forged["markets"]["hk"]["stats"]["recall_manifest"][0]["recall_metrics"][field] = value
                errors = validate_snapshot(forged)
                self.assertTrue(
                    any(
                        "markets.hk.stats.recall_manifest[0]" in error
                        and (
                            "deterministic XHKG policy" in error
                            or "not eligible for intraday_scaled" in error
                            or "amount_currency must be HKD" in error
                            or "market_cap_" in error
                        )
                        for error in errors
                    ),
                    errors,
                )

        pre_open = current_hk_intraday_snapshot_fixture()
        pre_open["markets"]["hk"]["stats"]["recall_manifest"][0]["observed_at"] = (
            "2026-08-19T09:00:00+08:00"
        )
        self.assertTrue(
            any(
                "markets.hk.stats.recall_manifest[0] is not eligible for intraday_scaled" in error
                for error in validate_snapshot(pre_open)
            )
        )

    def test_current_hk_liquidity_audits_candidate_and_standard_admission(self) -> None:
        candidate_attack = current_hk_intraday_snapshot_fixture()
        candidate_attack["markets"]["hk"]["decision"]["primary"]["recall_metrics"][
            "market_cap"
        ] = 999_999_999
        self.assertTrue(
            any(
                "markets.hk.candidate[0700.HK] is not eligible for intraday_scaled" in error
                for error in validate_snapshot(candidate_attack)
            )
        )

        standard_attack = dynamic_hk_us_snapshot_fixture()
        standard_attack["markets"]["hk"]["stats"]["recall_manifest"][1]["recall_metrics"][
            "liquidity_admission"
        ] = "intraday_scaled"
        self.assertIn(
            "markets.hk.stats.recall_manifest[1] standard HK amount requires observed_amount admission",
            validate_snapshot(standard_attack),
        )

        policy_attack = dynamic_hk_us_snapshot_fixture()
        policy_attack["markets"]["hk"]["stats"]["recall_manifest"][1]["recall_metrics"][
            "liquidity_policy_version"
        ] = "forged-policy"
        self.assertIn(
            "markets.hk.stats.recall_manifest[1].recall_metrics.liquidity_policy_version is invalid",
            validate_snapshot(policy_attack),
        )

    def test_current_hk_liquidity_uses_break_clock_and_half_day_xhkg_schedule(self) -> None:
        break_snapshot = install_generated_hk_intraday_row(
            dynamic_hk_us_snapshot_fixture(),
            observed_at="2026-08-26T12:30:00+08:00",
            source_at="2026-08-26T11:14:00+08:00",
            amount=10_000_000,
        )
        break_metrics = break_snapshot["markets"]["hk"]["stats"]["recall_manifest"][0][
            "recall_metrics"
        ]
        self.assertEqual(break_metrics["liquidity_freshness_reference_at"], "2026-08-26T11:59:00+08:00")
        self.assertEqual(break_metrics["liquidity_source_age_seconds"], 45 * 60)
        break_errors = validate_snapshot(break_snapshot)
        self.assertFalse(
            any(
                "markets.hk.stats.recall_manifest[0]" in error
                and ("deterministic XHKG policy" in error or "not eligible" in error)
                for error in break_errors
            ),
            break_errors,
        )

        break_stale = copy.deepcopy(break_snapshot)
        break_stale["markets"]["hk"]["stats"]["recall_manifest"][0]["recall_metrics"][
            "source_timestamp"
        ] = int(dt.datetime.fromisoformat("2026-08-26T11:13:59+08:00").timestamp())
        self.assertTrue(
            any(
                "markets.hk.stats.recall_manifest[0] is not eligible for intraday_scaled" in error
                for error in validate_snapshot(break_stale)
            )
        )

        lunch_source = install_generated_hk_intraday_row(
            dynamic_hk_us_snapshot_fixture(),
            observed_at="2026-08-26T12:47:00+08:00",
            source_at="2026-08-26T12:05:00+08:00",
            amount=10_000_000,
        )
        lunch_metrics = lunch_source["markets"]["hk"]["stats"]["recall_manifest"][0][
            "recall_metrics"
        ]
        self.assertEqual(lunch_metrics["liquidity_source_phase"], "break")
        self.assertEqual(lunch_metrics["liquidity_source_effective_at"], "2026-08-26T11:59:00+08:00")
        self.assertEqual(lunch_metrics["liquidity_source_age_seconds"], 0)
        self.assertEqual(lunch_metrics["liquidity_source_wall_age_minutes"], 42)
        lunch_errors = validate_snapshot(lunch_source)
        self.assertFalse(
            any(
                "markets.hk.stats.recall_manifest[0]" in error
                and ("deterministic XHKG policy" in error or "not eligible" in error)
                for error in lunch_errors
            ),
            lunch_errors,
        )
        lunch_stale = copy.deepcopy(lunch_source)
        lunch_stale["markets"]["hk"]["stats"]["recall_manifest"][0]["recall_metrics"][
            "source_timestamp"
        ] = int(dt.datetime.fromisoformat("2026-08-26T09:30:00+08:00").timestamp())
        self.assertTrue(
            any(
                "markets.hk.stats.recall_manifest[0] is not eligible for intraday_scaled" in error
                for error in validate_snapshot(lunch_stale)
            )
        )
        lunch_future = copy.deepcopy(lunch_source)
        lunch_future["markets"]["hk"]["stats"]["recall_manifest"][0]["recall_metrics"][
            "source_timestamp"
        ] = int(dt.datetime.fromisoformat("2026-08-26T12:59:00+08:00").timestamp())
        self.assertTrue(
            any(
                "markets.hk.stats.recall_manifest[0] is not eligible for intraday_scaled" in error
                for error in validate_snapshot(lunch_future)
            )
        )

        half_day = install_generated_hk_intraday_row(
            dynamic_hk_us_snapshot_fixture(),
            observed_at="2026-12-24T10:45:00+08:00",
            source_at="2026-12-24T10:30:00+08:00",
            amount=10_000_000,
        )
        half_day_metrics = half_day["markets"]["hk"]["stats"]["recall_manifest"][0][
            "recall_metrics"
        ]
        self.assertEqual(half_day_metrics["liquidity_session_total_minutes"], 150)
        self.assertEqual(half_day_metrics["liquidity_gate_progress"], 0.5)
        self.assertEqual(half_day_metrics["liquidity_data_progress"], 0.4)
        half_day_errors = validate_snapshot(half_day)
        self.assertFalse(
            any(
                "markets.hk.stats.recall_manifest[0]" in error
                and ("deterministic XHKG policy" in error or "not eligible" in error)
                for error in half_day_errors
            ),
            half_day_errors,
        )

    def test_hk_break_freshness_uses_effective_trading_minutes(self) -> None:
        timestamp = lambda value: int(dt.datetime.fromisoformat(value).timestamp())
        freshness = dynamic_manifest_source_freshness(
            [
                {
                    "recall_metrics": {
                        "source_timestamp": timestamp("2026-08-26T12:05:00+08:00")
                    }
                },
                {
                    "recall_metrics": {
                        "source_timestamp": timestamp("2026-08-26T09:30:00+08:00")
                    }
                },
                {
                    "recall_metrics": {
                        "source_timestamp": timestamp("2026-08-26T12:59:00+08:00")
                    }
                },
            ],
            "hk",
            "2026-08-26T12:47:00+08:00",
        )

        self.assertEqual(freshness["freshness_reference_at"], "2026-08-26T11:59:00+08:00")
        self.assertEqual(freshness["source_effective_as_of"], "2026-08-26T11:59:00+08:00")
        self.assertEqual(freshness["time_count"], 3)
        self.assertEqual(freshness["fresh_count"], 1)

    def test_archived_hk_dynamic_policy_v1_remains_compatible(self) -> None:
        archived = dynamic_hk_us_snapshot_fixture()
        archived["model_version"] = "smart-selector-2026-08-26.1-candidate-rule"
        for market_key in ("hk", "us"):
            archived["markets"][market_key]["stats"]["recall_policy_version"] = (
                "hk-us-cross-section-v1"
            )
        for row in archived["markets"]["hk"]["stats"]["recall_manifest"]:
            row["recall_metrics"].pop("liquidity_admission", None)
        archived["markets"]["hk"]["decision"]["primary"]["recall_metrics"].pop(
            "liquidity_admission", None
        )

        errors = validate_snapshot(archived)

        self.assertFalse(any("recall_policy_version is invalid" in error for error in errors), errors)
        self.assertFalse(any("HK amount requires" in error for error in errors), errors)

        unknown = copy.deepcopy(archived)
        unknown["model_version"] = "smart-selector-forged-unknown"
        unknown.pop("production_decision", None)
        unknown_errors = validate_snapshot(unknown)
        self.assertIn("markets.hk.stats.recall_policy_version is invalid", unknown_errors)

    def test_dynamic_hk_us_version_keeps_a_share_full_score_contract(self) -> None:
        enriched = dynamic_hk_us_snapshot_fixture()
        del enriched["markets"]["a_share"]["stats"]["base_scored_size"]

        errors = validate_snapshot(enriched)

        self.assertTrue(any("base_scored_size" in error for error in errors))

    def test_automation_metadata_uses_workflow_environment(self) -> None:
        with mock.patch.dict(
            server.os.environ,
            {
                "AUTOMATION_TRIGGER": "schedule",
                "SCHEDULED_SLOT": "2026-08-21T20:17:00+08:00",
                "SCHEDULED_INVOCATION_SLOT": "2026-08-21T20:47:00+08:00",
                "GENERATION_ATTEMPT": "2",
                "GITHUB_RUN_ID": "123456",
            },
            clear=False,
        ):
            snapshot = server.enrich_snapshot_v2(snapshot_fixture())
        self.assertEqual(
            snapshot["automation"],
            {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T20:17:00+08:00",
                "scheduled_invocation_slot": "2026-08-21T20:47:00+08:00",
                "generation_attempt": 2,
                "run_id": "123456:2",
            },
        )

    def test_new_scheduled_model_requires_ordered_checkpoint_and_invocation(self) -> None:
        valid = dynamic_hk_us_snapshot_fixture()
        valid["model_version"] = server.MODEL_VERSION
        valid["automation"].update(
            {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T22:47+08:00",
                "scheduled_invocation_slot": "2026-08-21T23:17+08:00",
            }
        )
        valid_errors = validate_snapshot(valid)
        self.assertFalse(any("scheduled automation" in error for error in valid_errors))
        self.assertNotIn(
            "automation.scheduled_slot does not match its invocation checkpoint",
            valid_errors,
        )

        missing = copy.deepcopy(valid)
        missing["automation"]["scheduled_invocation_slot"] = None
        self.assertIn(
            "scheduled automation.scheduled_invocation_slot must be an aware ISO datetime",
            validate_snapshot(missing),
        )

        mismatched = copy.deepcopy(valid)
        mismatched["automation"]["scheduled_slot"] = "2026-08-21T20:17+08:00"
        self.assertIn(
            "automation.scheduled_slot does not match its invocation checkpoint",
            validate_snapshot(mismatched),
        )

    def test_three_markets_keep_old_fields_and_add_v2_contract(self) -> None:
        snapshot = snapshot_fixture()
        legacy_actions = {key: section["decision"]["action"] for key, section in snapshot["markets"].items()}
        enriched = server.enrich_snapshot_v2(snapshot)
        self.assertEqual(enriched["schema_version"], server.SCHEMA_VERSION)
        self.assertEqual(enriched["selector_mode"], server.SELECTOR_MODE)
        self.assertEqual(
            enriched["analysis_models"]["ten_day_return"]["label_version"], server.TEN_DAY_LABEL_VERSION
        )
        for key in ("a_share", "hk", "us"):
            row = enriched["markets"][key]["decision"]["primary"]
            required = {
                "score",
                "recommendation_degree",
                "chan_score",
                "uzi_panel_score",
                "legacy",
                "v2",
                "data_quality",
                "decision_gates",
                "candidate_lineage",
                "analysis_projects",
            }
            self.assertTrue(required <= row.keys())
            self.assertEqual(enriched["markets"][key]["decision"]["action"], legacy_actions[key])
        self.assertEqual(enriched["analysis_models"]["dual_low"]["mode"], "shadow_overlay")
        self.assertEqual(
            enriched["markets"]["a_share"]["decision"]["primary"]["analysis_projects"]["dual_low"]["status"],
            "unavailable",
        )
        self.assertEqual(
            enriched["markets"]["hk"]["decision"]["primary"]["analysis_projects"]["dual_low"]["status"],
            "not_applicable",
        )
        self.assertEqual(
            enriched["markets"]["hk"]["decision"]["primary"]["candidate_lineage"]["universe_origin"],
            "curated_static",
        )
        self.assertEqual(
            enriched["markets"]["us"]["decision"]["primary"]["candidate_lineage"]["universe_origin"],
            "curated_static",
        )

    def test_snapshot_enrichment_does_not_change_legacy_decision(self) -> None:
        snapshot = snapshot_fixture()
        before = copy.deepcopy(snapshot["markets"])
        enriched = server.enrich_snapshot_v2(snapshot)
        for market_key in before:
            old = before[market_key]["decision"]
            new = enriched["markets"][market_key]["decision"]
            self.assertEqual(new["action"], old["action"])
            self.assertEqual(new["title"], old["title"])
            self.assertEqual(new["message"], old["message"])
            self.assertEqual(new["primary"]["score"], old["primary"]["score"])
            self.assertEqual(new["primary"]["recommendation_degree"], old["primary"]["recommendation_degree"])

    def test_enrichment_publishes_independent_production_rule_contract(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())

        self.assertEqual(server.MODEL_VERSION, "smart-selector-2026-08-26.2-dual-track-rule")
        self.assertEqual(enriched["production_decision"]["contract_version"], "production-rule-10d-v1")
        self.assertEqual(enriched["production_decision"]["action_basis"], "dual_track_candidate_qualification_v3")
        self.assertEqual(enriched["production_decision"]["rule_model_id"], "ten-day-audited-rule-ensemble-v3")
        self.assertEqual(enriched["production_decision"]["action"], "NO_QUALIFIED_PICK")
        self.assertEqual(enriched["production_decision"]["score_kind"], "RULE_QUALIFICATION_SCORE")
        self.assertIsNone(enriched["production_decision"]["probability"])
        self.assertFalse(enriched["production_decision"]["calibrated"])
        self.assertEqual(enriched["global_decision"]["action"], "NO_VALID_PICK")
        self.assertFalse(enriched["data_health"]["qualification_usable"])
        self.assertFalse(enriched["data_health"]["calibrated_decision_usable"])
        self.assertEqual(
            validate_snapshot(enriched),
            ["production_decision rule contract does not match model_version"],
        )

        enriched["production_decision"]["probability"] = 0.88
        self.assertIn("production_decision probability must be null", validate_snapshot(enriched))

    def test_current_v3_rule_input_ledger_survives_json_and_enforces_hash_identity_and_count(self) -> None:
        enriched = current_v3_snapshot()
        round_tripped = json.loads(json.dumps(enriched, ensure_ascii=False, allow_nan=False))
        production_errors = [
            error for error in validate_snapshot(round_tripped)
            if error.startswith("production")
        ]
        self.assertEqual(production_errors, [])
        self.assertFalse(any("_candidate_pool" in section for section in round_tripped["markets"].values()))
        self.assertEqual(
            production_rule_model.build_production_decision(round_tripped),
            round_tripped["production_decision"],
        )

        bad_hash = copy.deepcopy(round_tripped)
        bad_hash["production_rule_inputs"]["rows"][0]["source_data_quality_score"] = 99.0
        self.assertIn(
            "production_rule_inputs.ledger_sha256 does not match its payload",
            validate_snapshot(bad_hash),
        )

        bad_identity = copy.deepcopy(round_tripped)
        bad_identity["production_rule_inputs"]["rows"][0]["code"] = "000001"
        bad_identity["production_rule_inputs"]["ledger_sha256"] = (
            production_rule_model.production_rule_inputs_sha256(bad_identity["production_rule_inputs"])
        )
        self.assertIn(
            "production_rule_inputs.rows[0] identity does not match global evaluated candidate",
            validate_snapshot(bad_identity),
        )

        bad_count = copy.deepcopy(round_tripped)
        bad_count["production_rule_inputs"]["rows"].pop()
        bad_count["production_rule_inputs"]["ledger_sha256"] = (
            production_rule_model.production_rule_inputs_sha256(bad_count["production_rule_inputs"])
        )
        errors = validate_snapshot(bad_count)
        self.assertIn("production_rule_inputs.evaluated_candidate_count does not match rows", errors)
        self.assertIn("production_rule_inputs rows must cover every global evaluated candidate", errors)

    def test_current_v3_rejects_forged_quality_pass_shared_blocker_bypass_and_mirror_tamper(self) -> None:
        enriched = current_v3_snapshot()
        forged = copy.deepcopy(enriched)
        row = forged["production_decision"]["evaluated_candidates"][0]
        row.update(
            {
                "status": "QUALIFIED",
                "qualification_id": "qual_0123456789abcdef01234567",
                "qualification_track": "quality_technical",
                "track_evaluations": [
                    {
                        "track": "event_catalyst",
                        "status": "FAIL",
                        "blocker_codes": ["MATERIAL_NEGATIVE_EVENT"],
                    },
                    {"track": "quality_technical", "status": "PASS", "blocker_codes": []},
                ],
                "blocker_codes": [],
                "candidate_snapshot": copy.deepcopy(
                    forged["markets"]["a_share"]["decision"]["primary"]
                ),
            }
        )
        decision = forged["production_decision"]
        decision.update(
            {
                "action": "QUALIFIED_PICK",
                "primary": copy.deepcopy(row),
                "qualified_candidates": [copy.deepcopy(row)],
                "qualified_candidate_count": 1,
                "rejected_candidate_count": len(decision["evaluated_candidates"]) - 1,
                "blocker_codes": [],
            }
        )
        self.assertIn(
            "production_decision does not match deterministic current V3 rebuild",
            validate_snapshot(forged),
        )

        ledger_bypass = current_v3_snapshot()
        entry = ledger_bypass["production_rule_inputs"]["rows"][0]
        entry.update(
            {
                "legacy_recommendation_degree": 80,
                "v2_rank": 1,
                "v2_rank_universe_size": 100,
                "event_candidate_scanned": True,
                "verified_positive_event_ids": [],
                "estimated_10d_range": {"low_pct": -4.0, "high_pct": 8.0},
                "blocker_codes": ["VERIFIED_POSITIVE_EVENT_MISSING"],
                "source_data_quality_score": 100.0,
                "candidate_snapshot": copy.deepcopy(
                    ledger_bypass["markets"]["a_share"]["decision"]["primary"]
                ),
            }
        )
        rebuild_current_v3(ledger_bypass)
        self.assertIn(
            "production_rule_inputs.rows[0] rule fields do not match global evaluated candidate",
            validate_snapshot(ledger_bypass),
        )

        valid_pick = current_v3_snapshot()
        qualify_current_v3_row(valid_pick, 0)
        rebuild_current_v3(valid_pick)
        production_errors = [
            error for error in validate_snapshot(valid_pick)
            if error.startswith("production")
        ]
        self.assertEqual(production_errors, [])

        wrong_track = copy.deepcopy(valid_pick)
        for candidate in (
            wrong_track["production_decision"]["evaluated_candidates"][0],
            wrong_track["production_decision"]["qualified_candidates"][0],
            wrong_track["production_decision"]["primary"],
        ):
            self.assertEqual(
                [evaluation["status"] for evaluation in candidate["track_evaluations"]],
                ["PASS", "PASS"],
            )
            candidate["qualification_track"] = "quality_technical"
        self.assertIn(
            "production_decision does not match deterministic current V3 rebuild",
            validate_snapshot(wrong_track),
        )

        valid_pick["production_decision"]["primary"]["name"] = "未审计镜像"
        errors = validate_snapshot(valid_pick)
        self.assertIn(
            "production primary must exactly match the first qualified evaluated row",
            errors,
        )
        self.assertIn(
            "production_decision does not match deterministic current V3 rebuild",
            errors,
        )

    def test_all_production_qualified_candidates_require_complete_live_quotes(self) -> None:
        enriched = current_v3_snapshot()
        qualify_current_v3_row(enriched, 0)
        qualify_current_v3_row(enriched, 1, code="0005.HK")
        enriched["production_rule_inputs"]["rows"][1]["candidate_snapshot"].pop("realtime", None)
        rebuild_current_v3(enriched)

        self.assertIn(
            "hk:0005.HK realtime quote is required for live publication",
            validate_snapshot(enriched),
        )

    def test_new_model_requires_production_contract_but_previous_snapshot_remains_deployable(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        enriched.pop("production_decision")

        enriched["model_version"] = server.MODEL_VERSION
        self.assertIn("production_decision is required", validate_snapshot(enriched))

        enriched["model_version"] = "smart-selector-2026-08-26.1-candidate-rule"
        self.assertNotIn("production_decision is required", validate_snapshot(enriched))

        enriched["markets"]["a_share"]["stats"]["deep_score_limit"] = 96
        self.assertNotIn("markets.a_share.stats.deep_score_limit must be 96/300", validate_snapshot(enriched))

    def test_v3_qualified_rows_enforce_the_selected_track_without_requiring_events_for_quality(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        source = enriched["markets"]["a_share"]["decision"]["primary"]
        row = {
            "qualification_id": "qual_0123456789abcdef01234567",
            "status": "QUALIFIED",
            "market": "a_share",
            "code": source["code"],
            "name": source["name"],
            "rule_model_id": "ten-day-audited-rule-ensemble-v3",
            "score_kind": "RULE_QUALIFICATION_SCORE",
            "qualification_score": 82.4,
            "probability": None,
            "calibrated": False,
            "expected_net_utility": None,
            "blocker_codes": [],
            "event_candidate_scanned": True,
            "verified_positive_event_ids": [],
            "qualification_track": "quality_technical",
            "track_evaluations": [
                {
                    "track": "event_catalyst",
                    "status": "FAIL",
                    "blocker_codes": ["VERIFIED_POSITIVE_EVENT_MISSING"],
                },
                {"track": "quality_technical", "status": "PASS", "blocker_codes": []},
            ],
            "candidate_snapshot": copy.deepcopy(source),
        }
        decision = enriched["production_decision"]
        decision.update(
            {
                "action": "QUALIFIED_PICK",
                "action_basis": "dual_track_candidate_qualification_v3",
                "rule_model_id": "ten-day-audited-rule-ensemble-v3",
                "primary": copy.deepcopy(row),
                "qualified_candidates": [copy.deepcopy(row)],
                "evaluated_candidates": [copy.deepcopy(row)],
                "qualified_candidate_count": 1,
                "rejected_candidate_count": 0,
                "evaluated_candidate_count": 1,
                "blocker_codes": [],
            }
        )
        enriched["markets"]["a_share"]["market_regime"] = {"state": "normal"}
        enriched["global_decision"]["market_states"]["a_share"].update(
            {"state": "READY", "reason_codes": []}
        )

        self.assertEqual(
            validate_snapshot(enriched),
            ["production_decision rule contract does not match model_version"],
        )

        event_track = copy.deepcopy(enriched)
        for candidate in (
            event_track["production_decision"]["primary"],
            event_track["production_decision"]["qualified_candidates"][0],
            event_track["production_decision"]["evaluated_candidates"][0],
        ):
            candidate["qualification_track"] = "event_catalyst"
        self.assertIn(
            "production_decision.evaluated_candidates[0] event_catalyst requires verified positive event evidence",
            validate_snapshot(event_track),
        )

        failed_track = copy.deepcopy(enriched)
        failed_track["production_decision"]["evaluated_candidates"][0]["track_evaluations"][1]["status"] = "FAIL"
        self.assertIn(
            "production_decision.evaluated_candidates[0] selected qualification track must PASS",
            validate_snapshot(failed_track),
        )

        unscanned = copy.deepcopy(enriched)
        unscanned["production_decision"]["evaluated_candidates"][0]["event_candidate_scanned"] = False
        self.assertIn(
            "production_decision.evaluated_candidates[0] requires event candidate scan",
            validate_snapshot(unscanned),
        )

    def test_new_model_rejects_v2_pair_but_archived_v2_contract_remains_supported(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        current = copy.deepcopy(enriched)
        current["model_version"] = server.MODEL_VERSION
        current["production_decision"]["action_basis"] = "candidate_level_rule_qualification_v2"
        current["production_decision"]["rule_model_id"] = "ten-day-audited-rule-ensemble-v2"
        for row in current["production_decision"].get("evaluated_candidates", []):
            row["rule_model_id"] = "ten-day-audited-rule-ensemble-v2"
        self.assertIn("production_decision rule contract does not match model_version", validate_snapshot(current))

        archived = copy.deepcopy(current)
        archived["model_version"] = "smart-selector-2026-08-26.1-candidate-rule"
        self.assertNotIn("production_decision rule contract does not match model_version", validate_snapshot(archived))

        archived_with_v3 = current_v3_snapshot()
        archived_with_v3["model_version"] = "smart-selector-2026-08-26.1-candidate-rule"
        self.assertIn(
            "production_decision rule contract does not match model_version",
            validate_snapshot(archived_with_v3),
        )

    def test_v3_rejected_rows_require_complete_dual_track_audit(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        rejected = enriched["production_decision"]["evaluated_candidates"][0]
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertIsNone(rejected["qualification_track"])
        self.assertEqual(
            [item["track"] for item in rejected["track_evaluations"]],
            ["event_catalyst", "quality_technical"],
        )

        rejected.pop("track_evaluations")
        self.assertIn(
            "production_decision.evaluated_candidates[0].track_evaluations is invalid",
            validate_snapshot(enriched),
        )

    def test_global_ten_day_gate_is_strict_without_calibration_or_event_pipeline_scan(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        decision = enriched["global_decision"]
        self.assertEqual(decision["action"], "NO_VALID_PICK")
        self.assertEqual(decision["action_basis"], "strict_cross_market_gate_v1")
        self.assertEqual(decision["probability_status"], "UNAVAILABLE")
        self.assertIsNone(decision["probability"])
        self.assertFalse(decision["calibrated"])
        self.assertIsNone(decision["primary"])
        self.assertEqual(decision["research_priority"]["status"], "RESEARCH_ONLY")
        self.assertIn("EVENT_PIPELINE_NOT_SCANNED", decision["blocker_codes"])
        self.assertIn("TEN_DAY_PROBABILITY_UNCALIBRATED", decision["blocker_codes"])
        self.assertEqual(set(decision["market_states"]), {"a_share", "hk", "us"})
        self.assertFalse(enriched["data_health"]["decision_usable"])

    def test_snapshot_publishes_exchange_specific_trade_windows(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())

        self.assertEqual(set(enriched["next_trade_dates"]), {"a_share", "hk", "us"})
        self.assertEqual(set(enriched["forecast_end_dates"]), {"a_share", "hk", "us"})
        self.assertNotEqual(enriched["next_trade_date"], enriched["forecast_end_date"])
        self.assertEqual(enriched["next_trade_dates"]["a_share"], "2026-08-20")
        self.assertEqual(enriched["next_trade_dates"]["hk"], "2026-08-20")
        self.assertEqual(enriched["next_trade_dates"]["us"], "2026-08-19")
        for market_key in ("a_share", "hk", "us"):
            window = enriched["markets"][market_key]["trade_window"]
            self.assertEqual(window["entry_trade_date"], enriched["next_trade_dates"][market_key])
            self.assertEqual(window["forecast_end_trade_date"], enriched["forecast_end_dates"][market_key])
            self.assertEqual(window["horizon_sessions"], 10)
            self.assertGreater(
                dt.datetime.fromisoformat(window["entry_session_open_at"]),
                dt.datetime.fromisoformat(window["decision_time"]),
            )

    def test_snapshot_validator_accepts_shadow_fallback_and_rejects_decision_participation(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        self.assertEqual(
            validate_snapshot(enriched),
            ["production_decision rule contract does not match model_version"],
        )
        enriched["analysis_models"]["dual_low"]["participates_in_decision"] = True
        self.assertIn("dual-low model must not participate in the decision", validate_snapshot(enriched))

    def test_snapshot_validator_checks_published_recall_funnel_contract(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        targets = {"a_share": 300, "hk": 200, "us": 300}
        for market_key, target in targets.items():
            enriched["markets"][market_key]["stats"].update(
                {
                    "recall_target": target,
                    "recall_selected_size": target,
                    "recall_shortfall": 0,
                    "valid_quote_size": target,
                    "deep_scored_size": target,
                }
            )
        enriched["markets"]["a_share"]["stats"].update(
            {
                "board_targets": server.A_SHARE_BOARD_TARGETS,
                "board_counts": server.A_SHARE_BOARD_TARGETS,
            }
        )
        self.assertEqual(
            validate_snapshot(enriched),
            ["production_decision rule contract does not match model_version"],
        )

        enriched["markets"]["hk"]["stats"]["recall_selected_size"] = 199
        errors = validate_snapshot(enriched)
        self.assertIn("markets.hk.stats.recall_shortfall is inconsistent", errors)

    def test_expanded_universe_cannot_omit_or_falsify_recall_funnel(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        del enriched["markets"]["us"]["stats"]["recall_target"]
        enriched["markets"]["a_share"]["stats"]["board_counts"] = {
            "sh_main": 300,
            "sz_main": 0,
            "chinext": 0,
            "star": 0,
        }
        enriched["markets"]["hk"]["stats"]["raw_pool_size"] = 1
        enriched["markets"]["hk"]["stats"]["scored_size"] = 99

        errors = validate_snapshot(enriched)

        self.assertTrue(any("markets.us.stats recall funnel fields missing" in error for error in errors))
        self.assertIn("markets.a_share.stats.board_shortfalls is inconsistent", errors)
        self.assertIn("markets.hk.stats.raw_pool_size must equal selected size", errors)
        self.assertIn("markets.hk.stats.scored_size must equal deep scored size", errors)

    def test_expanded_universe_validates_deep_and_freshness_accounting(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        enriched["markets"]["a_share"]["stats"]["deep_attempted_size"] = 0
        enriched["markets"]["hk"]["quote_health"]["realtime_count"] = 199

        errors = validate_snapshot(enriched)

        self.assertIn("markets.a_share.stats.deep_scored_size exceeds attempted size", errors)
        self.assertIn("markets.a_share.stats.deep_kline_coverage is inconsistent", errors)
        self.assertIn("markets.hk.quote_health.realtime_coverage is inconsistent", errors)

    def test_a_share_full_score_stages_are_required_and_self_consistent(self) -> None:
        missing = server.enrich_snapshot_v2(snapshot_fixture())
        del missing["markets"]["a_share"]["stats"]["base_scored_size"]

        errors = validate_snapshot(missing)

        self.assertTrue(any("base_scored_size" in error for error in errors))

        inconsistent = server.enrich_snapshot_v2(snapshot_fixture())
        inconsistent["markets"]["a_share"]["stats"].update(
            {
                "base_scored_size": 299,
                "technical_attempted_size": 298,
                "technical_scored_size": 297,
                "technical_kline_complete_size": 296,
                "technical_kline_coverage": 0.1,
            }
        )

        errors = validate_snapshot(inconsistent)

        self.assertIn("markets.a_share.stats.base_scored_size must equal valid quote size", errors)
        self.assertIn("markets.a_share.stats.technical_attempted_size must equal base scored size", errors)
        self.assertIn("markets.a_share.stats.technical_kline_coverage is inconsistent", errors)

    def test_a_share_deep_attempted_uses_only_eligible_complete_kline_rows(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        stats = enriched["markets"]["a_share"]["stats"]
        stats.update(
            {
                "technical_kline_complete_size": 3,
                "technical_kline_coverage": 0.01,
                "deep_score_limit": 3,
                "deep_eligible_size": 2,
                "deep_attempted_size": 2,
                "deep_scored_size": 2,
                "deep_kline_coverage": 1.0,
                "scored_size": 2,
            }
        )

        # The production contract fixes the limit at 300, so validate the
        # eligible basis with the production limit and a two-name deep pool.
        stats["deep_score_limit"] = 300
        self.assertEqual(
            validate_snapshot(enriched),
            ["production_decision rule contract does not match model_version"],
        )

        stats["deep_attempted_size"] = 3
        errors = validate_snapshot(enriched)
        self.assertIn("markets.a_share.stats.deep_attempted_size is invalid", errors)

    def test_a_share_pool_health_audits_deep_eligibility_coverage(self) -> None:
        healthy = current_v3_snapshot()
        stats = healthy["markets"]["a_share"]["stats"]
        stats.update(
            {
                "technical_kline_complete_size": 297,
                "technical_kline_coverage": 0.99,
                "deep_eligible_size": 295,
                "deep_attempted_size": 295,
                "deep_scored_size": 295,
                "deep_kline_coverage": 1.0,
                "scored_size": 295,
            }
        )
        pool_health = healthy["markets"]["a_share"]["pool_health"]
        pool_health.update(
            {
                "status": "healthy",
                "reason_codes": [],
                "technical_completed_count": 297,
                "technical_score_coverage": 0.99,
                "deep_eligible_count": 295,
                "deep_eligibility_target_count": 297,
                "deep_eligibility_coverage": 0.9933,
                "deep_attempted_count": 295,
                "expected_deep_attempted_count": 295,
                "deep_completed_count": 295,
                "deep_score_coverage": 1.0,
            }
        )

        healthy_errors = validate_snapshot(healthy)
        self.assertFalse(
            any(error.startswith("markets.a_share.pool_health") for error in healthy_errors),
            healthy_errors,
        )

        below_minimum = copy.deepcopy(healthy)
        below_stats = below_minimum["markets"]["a_share"]["stats"]
        below_stats.update(
            {
                "deep_eligible_size": 291,
                "deep_attempted_size": 291,
                "deep_scored_size": 291,
                "scored_size": 291,
            }
        )
        below_pool = below_minimum["markets"]["a_share"]["pool_health"]
        below_pool.update(
            {
                "deep_eligible_count": 291,
                "deep_eligibility_coverage": 0.9798,
                "deep_attempted_count": 291,
                "expected_deep_attempted_count": 291,
                "deep_completed_count": 291,
            }
        )
        self.assertIn(
            "markets.a_share.pool_health deep reason is inconsistent",
            validate_snapshot(below_minimum),
        )

    def test_a_share_pool_health_accepts_legacy_unversioned_snapshot_only(self) -> None:
        legacy = current_v3_snapshot()
        legacy_pool = legacy["markets"]["a_share"]["pool_health"]
        for field in (
            "contract_version",
            "deep_eligibility_target_count",
            "deep_eligibility_coverage",
            "min_deep_eligibility_coverage",
            "expected_deep_attempted_count",
        ):
            legacy_pool.pop(field)

        legacy_errors = validate_snapshot(legacy)
        self.assertFalse(
            any(error.startswith("markets.a_share.pool_health") for error in legacy_errors),
            legacy_errors,
        )

        unknown_version = copy.deepcopy(legacy)
        unknown_version["markets"]["a_share"]["pool_health"][
            "contract_version"
        ] = "a-share-pool-health-v1"
        self.assertIn(
            "markets.a_share.pool_health.contract_version is invalid",
            validate_snapshot(unknown_version),
        )

    def test_snapshot_validator_requires_global_ten_day_contract(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        enriched["analysis_models"].pop("ten_day_return")
        enriched.pop("global_decision")
        errors = validate_snapshot(enriched)
        self.assertIn("analysis_models.ten_day_return is required", errors)
        self.assertIn("global_decision is required", errors)

    def test_snapshot_validator_rejects_invalid_trade_window_or_range_horizon(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        enriched["forecast_end_dates"]["us"] = enriched["next_trade_dates"]["us"]
        candidate = enriched["markets"]["us"]["decision"]["primary"]
        candidate["estimated_2d_range"]["horizon_trade_days"] = 10

        errors = validate_snapshot(enriched)

        self.assertIn("forecast_end_dates.us must be the 10th XNYS session", errors)
        self.assertIn("us:NVDA estimated_2d_range horizon must be 2", errors)

    def test_snapshot_validator_rejects_market_state_that_understates_sources(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        enriched["global_decision"]["market_states"]["hk"] = {
            "state": "READY",
            "reason_codes": [],
        }
        errors = validate_snapshot(enriched)
        self.assertIn("global_decision.market_states.hk understates derived DEGRADED coverage", errors)
        self.assertIn("global_decision.market_states.hk.reason_codes are incomplete", errors)

    def test_snapshot_validator_requires_realtime_price_for_published_live_candidate(self) -> None:
        for fallback_field, fallback_value in (
            ("current_price", "12.50"),
            ("entry_price", 12.5),
            ("price", 12.5),
            ("kline", [{"close": "12.50"}]),
        ):
            with self.subTest(fallback_field=fallback_field):
                enriched = server.enrich_snapshot_v2(snapshot_fixture())
                candidate = enriched["markets"]["a_share"]["decision"]["primary"]
                candidate.pop("realtime", None)
                candidate[fallback_field] = fallback_value

                errors = validate_snapshot(enriched)

                self.assertIn(
                    "a_share:603228 realtime quote is required for live publication",
                    errors,
                )

    def test_snapshot_validator_rejects_live_candidate_without_a_positive_price(self) -> None:
        for invalid in (0, -1, "12.50", True, None):
            with self.subTest(invalid=invalid):
                enriched = server.enrich_snapshot_v2(snapshot_fixture())
                candidate = enriched["markets"]["a_share"]["decision"]["primary"]
                candidate["realtime"]["price"] = invalid

                errors = validate_snapshot(enriched)

                self.assertIn(
                    "a_share:603228 realtime.price must be positive",
                    errors,
                )

    def test_snapshot_validator_checks_realtime_publication_metadata(self) -> None:
        cases = {
            "source_as_of": (
                "not-a-time",
                "a_share:603228 realtime.source_as_of must be a timezone-aware ISO datetime",
            ),
            "fetched_at": (
                "2026-08-19T16:10:00",
                "a_share:603228 realtime.fetched_at must be a timezone-aware ISO datetime",
            ),
            "volume_unit": (
                "contracts",
                "a_share:603228 realtime.volume_unit must be lot or share",
            ),
        }
        for field, (invalid_value, expected_error) in cases.items():
            with self.subTest(field=field):
                enriched = server.enrich_snapshot_v2(snapshot_fixture())
                candidate = enriched["markets"]["a_share"]["decision"]["primary"]
                candidate["realtime"][field] = invalid_value
                self.assertIn(expected_error, validate_snapshot(enriched))

    def test_snapshot_validator_rejects_old_price_only_candidate_for_latest_publication(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        candidate = enriched["markets"]["a_share"]["decision"]["primary"]
        candidate.pop("current_price", None)
        candidate.pop("entry_price", None)
        candidate.pop("realtime", None)
        candidate["price"] = "12.50"
        candidate["kline"] = []

        errors = validate_snapshot(enriched)

        self.assertIn("a_share:603228 realtime quote is required for live publication", errors)

    def test_snapshot_validator_allows_a_market_without_live_candidates(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        decision = enriched["markets"]["us"]["decision"]
        decision["primary"] = None
        decision["blocked_candidate"] = None
        decision["watchlist"] = []
        global_decision = enriched["global_decision"]
        for field in ("primary", "research_priority"):
            candidate = global_decision.get(field)
            if isinstance(candidate, dict) and candidate.get("market") == "us":
                global_decision[field] = None

        errors = validate_snapshot(enriched)

        self.assertFalse(any(error.startswith("us:") and "live candidate" in error for error in errors))

    def test_snapshot_validator_checks_unique_global_live_candidate(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        research = enriched["global_decision"]["research_priority"]
        research.update(
            {
                "market": "us",
                "code": "GLOBAL",
                "calendar_id": enriched["markets"]["us"]["trade_window"]["calendar_id"],
                "entry_trade_date": enriched["next_trade_dates"]["us"],
                "forecast_end_trade_date": enriched["forecast_end_dates"]["us"],
                "entry_price": 0,
            }
        )
        for field in ("current_price", "price", "realtime", "kline"):
            research.pop(field, None)

        errors = validate_snapshot(enriched)

        self.assertIn(
            "us:GLOBAL realtime quote is required for live publication",
            errors,
        )

    def test_research_priority_repeats_candidate_snapshot_quote_for_live_contract(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        research = enriched["global_decision"]["research_priority"]

        self.assertIsInstance(research.get("candidate_snapshot"), dict)
        self.assertEqual(research.get("realtime"), research["candidate_snapshot"].get("realtime"))
        self.assertFalse(
            any(
                error.startswith(f"{research['market']}:{research['code']} ")
                and "realtime" in error
                for error in validate_snapshot(enriched)
            )
        )

    def test_snapshot_validator_requires_safe_snapshot_key(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        for invalid in (None, "", "latest.json", "../escape.json", "nested/file.json", "bad\\file.json"):
            with self.subTest(invalid=invalid):
                enriched["snapshot_key"] = invalid
                self.assertIn(
                    "snapshot_key must be a safe immutable JSON filename",
                    validate_snapshot(enriched),
                )

    def test_snapshot_validator_requires_object_watchlist_rows(self) -> None:
        cases = (
            ({"603228": {}}, "markets.a_share.decision.watchlist must be a list"),
            ([{"code": "603228"}, "bad-row"], "markets.a_share.decision.watchlist[1] must be an object"),
        )
        for watchlist, expected in cases:
            with self.subTest(watchlist=watchlist):
                enriched = server.enrich_snapshot_v2(snapshot_fixture())
                enriched["markets"]["a_share"]["decision"]["watchlist"] = watchlist
                self.assertIn(expected, validate_snapshot(enriched))

    def test_snapshot_file_validator_requires_matching_immutable_file(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        encoded = json.dumps(enriched, ensure_ascii=False, indent=2) + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            picks = pathlib.Path(temporary)
            latest = picks / "latest.json"
            immutable = picks / enriched["snapshot_key"]
            latest.write_text(encoded, encoding="utf-8")

            missing_errors = validate_snapshot_file(latest)
            self.assertIn("immutable snapshot file is missing", missing_errors)

            immutable.write_text(encoded, encoding="utf-8")
            self.assertEqual(
                validate_snapshot_file(latest),
                ["production_decision rule contract does not match model_version"],
            )

            immutable.write_text(encoded.replace("legacy-fixture", "different-model"), encoding="utf-8")
            mismatch_errors = validate_snapshot_file(latest)
            self.assertIn("latest snapshot and immutable snapshot bytes must match", mismatch_errors)


if __name__ == "__main__":
    unittest.main()

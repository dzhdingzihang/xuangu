#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from market_calendar import CALENDAR_VERSION, calendar_id, market_trade_windows


VALID_MODEL_STATUSES = {"available", "unavailable"}
VALID_CANDIDATE_STATUSES = {"ranked", "rejected", "unavailable", "not_applicable"}
VALID_EXECUTABLE_SCORE_KINDS = {"TEN_DAY_EXPECTED_NET_UTILITY"}
STATE_SEVERITY = {"READY": 0, "DEGRADED": 1, "BLOCKED": 2}
VALID_VOLUME_UNITS = {"lot", "share"}
MARKET_RECALL_TARGETS = {"a_share": 300, "hk": 200, "us": 300}
A_SHARE_BOARD_TARGETS = {"sh_main": 90, "sz_main": 75, "chinext": 75, "star": 60}
A_SHARE_ROUTE_TARGETS = {"event": 40, "momentum": 80, "pullback": 65, "liquidity": 85, "history": 30}
EXPANDED_RECALL_UNIVERSE_VERSION = "recall-v2-2-diversified-300-200-300"


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def probability(value) -> bool:
    return finite_number(value) and 0 <= value <= 1


def strict_boolean(value) -> bool:
    return type(value) is bool


def positive_number(value) -> bool:
    """Match the Worker's strict JSON-number quote contract."""

    return finite_number(value) and value > 0


def timezone_aware_iso_datetime(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def safe_snapshot_key(value) -> bool:
    if not isinstance(value, str) or not value or value == "latest.json":
        return False
    return (
        value.endswith(".json")
        and pathlib.PurePosixPath(value).name == value
        and "/" not in value
        and "\\" not in value
    )


def normalize_live_code(market_key: str, value) -> str | None:
    """Normalize exactly the code shapes accepted by the snapshot-backed API."""

    raw = str(value or "").strip().upper()
    if market_key == "a_share":
        clean = re.sub(r"^(?:SH|SZ)\.", "", raw)
        return clean if re.fullmatch(r"\d{6}", clean) else None
    if market_key == "hk":
        match = re.fullmatch(r"(\d{1,5})\.HK", raw)
        return f"{match.group(1).zfill(4)}.HK" if match else None
    if market_key == "us":
        return raw if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", raw) else None
    return None


def live_snapshot_candidates(snapshot: dict, market_key: str) -> list[tuple[str, dict]]:
    """Return effective allow-listed candidates in Worker lookup order.

    The first row for a normalized code wins, matching `/api/live`.  This also
    prevents a compact duplicate global decision row from being required to
    repeat every field already present on the market decision candidate.
    """

    markets = snapshot.get("markets") if isinstance(snapshot.get("markets"), dict) else {}
    section = markets.get(market_key)
    if not isinstance(section, dict) and market_key == "a_share":
        section = {"decision": snapshot.get("decision") or {}}
    decision = section.get("decision") if isinstance(section, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    watchlist = decision.get("watchlist")
    rows = [
        decision.get("primary"),
        decision.get("blocked_candidate"),
        *(watchlist if isinstance(watchlist, list) else []),
    ]
    global_decision = snapshot.get("global_decision")
    if isinstance(global_decision, dict):
        for field in ("primary", "research_priority"):
            candidate = global_decision.get(field)
            if isinstance(candidate, dict) and candidate.get("market") == market_key:
                rows.append(candidate)

    result: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for candidate in rows:
        if not isinstance(candidate, dict):
            continue
        code = normalize_live_code(market_key, candidate.get("code") or candidate.get("symbol"))
        if not code or code in seen:
            continue
        seen.add(code)
        result.append((code, candidate))
    return result


def validate_live_candidate_publication(snapshot: dict) -> list[str]:
    errors: list[str] = []
    for market_key in ("a_share", "hk", "us"):
        for code, candidate in live_snapshot_candidates(snapshot, market_key):
            realtime = candidate.get("realtime")
            if not isinstance(realtime, dict):
                errors.append(f"{market_key}:{code} realtime quote is required for live publication")
                continue
            if not positive_number(realtime.get("price")):
                errors.append(f"{market_key}:{code} realtime.price must be positive")
            for field in ("source_as_of", "fetched_at"):
                if not timezone_aware_iso_datetime(realtime.get(field)):
                    errors.append(
                        f"{market_key}:{code} realtime.{field} must be a timezone-aware ISO datetime"
                    )
            if realtime.get("volume_unit") not in VALID_VOLUME_UNITS:
                errors.append(f"{market_key}:{code} realtime.volume_unit must be lot or share")
    return errors


def decision_candidates(decision: dict) -> list[dict]:
    watchlist = decision.get("watchlist")
    rows = [
        decision.get("primary"),
        decision.get("blocked_candidate"),
        *(watchlist if isinstance(watchlist, list) else []),
    ]
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or row.get("symbol") or id(row))
        if code in seen:
            continue
        seen.add(code)
        result.append(row)
    return result


def derive_market_coverage_state(section: dict) -> tuple[str, list[str]]:
    """Recompute the minimum safe market state from published source fields."""

    section = section or {}
    decision = section.get("decision") or {}
    stats = section.get("stats") or {}
    pool = section.get("pool_health") or {}
    quote_health = section.get("quote_health") or {}
    pool_state = str(pool.get("state") or pool.get("status") or pool.get("data_state") or "").upper()
    pool_codes = list(pool.get("reason_codes") or [])
    decision_codes = list(decision.get("blocker_codes") or [])
    pool_degraded = pool_state == "DEGRADED" or bool(pool_codes) or any(
        any(token in str(code) for token in ("POOL_COVERAGE", "BROAD_POOL", "QUOTE_COVERAGE"))
        for code in decision_codes
    )
    origin = str(stats.get("universe_origin") or section.get("universe_origin") or "")
    regime_payload = section.get("market_regime") or {}
    regime = regime_payload if isinstance(regime_payload, str) else regime_payload.get("state")
    quote_coverage = quote_health.get("quote_coverage")
    quote_ready = (
        str(quote_health.get("status") or "").lower() == "available"
        and finite_number(quote_coverage)
        and quote_coverage >= 0.98
        and isinstance(quote_health.get("requested_count"), int)
        and quote_health.get("requested_count") > 0
    )
    reasons: list[str] = []
    if pool_degraded:
        reasons.append("POOL_COVERAGE_INCOMPLETE")
    if origin == "curated_static":
        reasons.append("CURATED_STATIC_UNIVERSE")
    if not regime or regime == "unknown":
        reasons.append("MARKET_CONTEXT_MISSING")
    if not quote_ready:
        reasons.append("QUOTE_HEALTH_INCOMPLETE")
    return ("BLOCKED" if pool_degraded else "DEGRADED" if reasons else "READY"), reasons


def validate_snapshot(snapshot: dict) -> list[str]:
    errors: list[str] = []
    if not safe_snapshot_key(snapshot.get("snapshot_key")):
        errors.append("snapshot_key must be a safe immutable JSON filename")
    if snapshot.get("schema_version") != "selector-snapshot-v2":
        errors.append("schema_version must be selector-snapshot-v2")
    if snapshot.get("selector_mode") != "legacy_active_v2_dual_low_shadow":
        errors.append("selector_mode must expose the dual-low shadow")
    if snapshot.get("calendar_version") != CALENDAR_VERSION:
        errors.append(f"calendar_version must be {CALENDAR_VERSION}")
    window_anchor = snapshot.get("generated_at") or snapshot.get("target_date")
    next_trade_dates = snapshot.get("next_trade_dates")
    forecast_end_dates = snapshot.get("forecast_end_dates")
    expected_markets = {"a_share", "hk", "us"}
    if not isinstance(next_trade_dates, dict) or set(next_trade_dates) != expected_markets:
        errors.append("next_trade_dates must cover three markets")
        next_trade_dates = {}
    if not isinstance(forecast_end_dates, dict) or set(forecast_end_dates) != expected_markets:
        errors.append("forecast_end_dates must cover three markets")
        forecast_end_dates = {}
    expected_windows = {}
    if window_anchor:
        try:
            expected_windows = market_trade_windows(window_anchor, horizon_sessions=10)
        except (TypeError, ValueError):
            errors.append("generated_at must be an aware ISO datetime")
        for market_key in ("a_share", "hk", "us"):
            exchange_id = calendar_id(market_key)
            expected_window = expected_windows.get(market_key) or {}
            if next_trade_dates.get(market_key) != expected_window.get("entry_trade_date"):
                errors.append(f"next_trade_dates.{market_key} must be the first {exchange_id} session")
            if forecast_end_dates.get(market_key) != expected_window.get("forecast_end_trade_date"):
                errors.append(f"forecast_end_dates.{market_key} must be the 10th {exchange_id} session")
    if next_trade_dates and snapshot.get("next_trade_date") != min(next_trade_dates.values()):
        errors.append("next_trade_date must be the earliest market entry date")
    if forecast_end_dates and snapshot.get("forecast_end_date") != max(forecast_end_dates.values()):
        errors.append("forecast_end_date must be the latest market exit date")
    if snapshot.get("next_trade_date") == snapshot.get("forecast_end_date"):
        errors.append("next_trade_date and forecast_end_date must differ")
    dual_model = ((snapshot.get("analysis_models") or {}).get("dual_low") or {})
    if dual_model.get("model_id") != "dsa-screening-score-v1":
        errors.append("analysis_models.dual_low.model_id is missing")
    if dual_model.get("status") not in VALID_MODEL_STATUSES:
        errors.append("analysis_models.dual_low.status is invalid")
    if dual_model.get("participates_in_decision") is not False:
        errors.append("dual-low model must not participate in the decision")
    if dual_model.get("status") == "available":
        counts = [dual_model.get(key) for key in ("input_count", "eligible_count", "rejected_count")]
        if not all(isinstance(value, int) and value >= 0 for value in counts):
            errors.append("dual-low available counts must be non-negative integers")
        elif counts[1] + counts[2] != counts[0]:
            errors.append("dual-low available counts do not add up")
        if dual_model.get("rank_universe_size") != dual_model.get("eligible_count"):
            errors.append("dual-low rank denominator must equal eligible_count")
        for item in dual_model.get("top_ranked") or []:
            if not finite_number(item.get("final_score")) or not 0 <= item["final_score"] <= 100:
                errors.append("dual-low top-ranked score is invalid")

    ten_day_model = ((snapshot.get("analysis_models") or {}).get("ten_day_return"))
    if ten_day_model is None:
        errors.append("analysis_models.ten_day_return is required")
    else:
        if not isinstance(ten_day_model, dict):
            errors.append("analysis_models.ten_day_return must be an object")
            ten_day_model = None
        else:
            for field in ("calibrated", "costs_ready", "tail_risk_ready", "participates_in_decision"):
                if field in ten_day_model and not strict_boolean(ten_day_model.get(field)):
                    errors.append(f"analysis_models.ten_day_return.{field} must be a boolean")
            ten_day_status = str(ten_day_model.get("status") or "").upper()
            if ten_day_status in {"READY", "CALIBRATED"} and ten_day_model.get("calibrated") is not True:
                errors.append("ten-day READY status requires calibrated=true")
            ten_day_probability = ten_day_model.get("probability")
            if ten_day_model.get("calibrated") is not True and ten_day_probability is not None:
                errors.append("uncalibrated ten-day model probability must be null")
            if ten_day_probability is not None and not probability(ten_day_probability):
                errors.append("analysis_models.ten_day_return.probability must be between 0 and 1")

    markets = snapshot.get("markets") or {}
    derived_market_states: dict[str, tuple[str, list[str]]] = {}
    for market_key in ("a_share", "hk", "us"):
        if market_key not in markets:
            errors.append(f"markets.{market_key} is missing")
            continue
        section = markets[market_key] or {}
        derived_market_states[market_key] = derive_market_coverage_state(section)
        stats = section.get("stats") if isinstance(section.get("stats"), dict) else {}
        expanded_recall_contract = snapshot.get("universe_version") == EXPANDED_RECALL_UNIVERSE_VERSION
        recall_contract_present = "recall_target" in stats or "recall_selected_size" in stats
        if expanded_recall_contract:
            required_recall_fields = {
                "recall_target",
                "recall_selected_size",
                "recall_shortfall",
                "raw_pool_size",
                "universe_size",
                "valid_quote_size",
                "deep_scored_size",
                "scored_size",
                "source_counts",
            }
            missing_fields = sorted(required_recall_fields - set(stats))
            if missing_fields:
                errors.append(
                    f"markets.{market_key}.stats recall funnel fields missing: "
                    + ",".join(missing_fields)
                )
        if expanded_recall_contract or recall_contract_present:
            expected_target = MARKET_RECALL_TARGETS[market_key]
            recall_target = stats.get("recall_target")
            selected_size = stats.get("recall_selected_size")
            shortfall = stats.get("recall_shortfall")
            valid_quote_size = stats.get("valid_quote_size")
            deep_scored_size = stats.get("deep_scored_size")
            if recall_target != expected_target:
                errors.append(f"markets.{market_key}.stats.recall_target must be {expected_target}")
            if not isinstance(selected_size, int) or isinstance(selected_size, bool) or not 0 <= selected_size <= expected_target:
                errors.append(f"markets.{market_key}.stats.recall_selected_size is invalid")
            elif shortfall != expected_target - selected_size:
                errors.append(f"markets.{market_key}.stats.recall_shortfall is inconsistent")
            if (
                not isinstance(valid_quote_size, int)
                or isinstance(valid_quote_size, bool)
                or valid_quote_size < 0
                or (isinstance(selected_size, int) and valid_quote_size > selected_size)
            ):
                errors.append(f"markets.{market_key}.stats.valid_quote_size is invalid")
            if (
                not isinstance(deep_scored_size, int)
                or isinstance(deep_scored_size, bool)
                or deep_scored_size < 0
                or (isinstance(valid_quote_size, int) and deep_scored_size > valid_quote_size)
            ):
                errors.append(f"markets.{market_key}.stats.deep_scored_size is invalid")
            raw_pool_size = stats.get("raw_pool_size")
            universe_size = stats.get("universe_size")
            scored_size = stats.get("scored_size")
            if isinstance(selected_size, int) and raw_pool_size != selected_size:
                errors.append(f"markets.{market_key}.stats.raw_pool_size must equal selected size")
            if isinstance(selected_size, int) and universe_size != selected_size:
                errors.append(f"markets.{market_key}.stats.universe_size must equal selected size")
            if isinstance(deep_scored_size, int) and scored_size != deep_scored_size:
                errors.append(f"markets.{market_key}.stats.scored_size must equal deep scored size")
            quote_health = section.get("quote_health") if isinstance(section.get("quote_health"), dict) else {}
            if quote_health and quote_health.get("quote_count") != valid_quote_size:
                errors.append(f"markets.{market_key}.stats.valid_quote_size must match quote health")
            source_counts = stats.get("source_counts")
            if (
                not isinstance(source_counts, dict)
                or not source_counts
                or not all(
                    isinstance(value, int) and not isinstance(value, bool) and value >= 0
                    for value in source_counts.values()
                )
            ):
                errors.append(f"markets.{market_key}.stats.source_counts is invalid")
            if market_key == "a_share":
                board_targets = stats.get("board_targets")
                board_counts = stats.get("board_counts")
                board_shortfalls = stats.get("board_shortfalls")
                if board_targets != A_SHARE_BOARD_TARGETS:
                    errors.append("markets.a_share.stats.board_targets is invalid")
                board_counts_valid = (
                    isinstance(board_counts, dict)
                    and set(board_counts) == set(A_SHARE_BOARD_TARGETS)
                    and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in board_counts.values())
                )
                if not board_counts_valid:
                    errors.append("markets.a_share.stats.board_counts is invalid")
                elif isinstance(selected_size, int) and sum(board_counts.values()) != selected_size:
                    errors.append("markets.a_share.stats.board_counts must add up to selected size")
                if board_counts_valid:
                    expected_shortfalls = {
                        board: target - board_counts[board]
                        for board, target in A_SHARE_BOARD_TARGETS.items()
                        if board_counts[board] < target
                    }
                    if board_shortfalls != expected_shortfalls:
                        errors.append("markets.a_share.stats.board_shortfalls is inconsistent")
                route_targets = stats.get("route_targets")
                route_counts = stats.get("route_counts")
                route_shortfalls = stats.get("route_shortfalls")
                if route_targets != A_SHARE_ROUTE_TARGETS:
                    errors.append("markets.a_share.stats.route_targets is invalid")
                route_counts_valid = (
                    isinstance(route_counts, dict)
                    and set(route_counts) == set(A_SHARE_ROUTE_TARGETS)
                    and all(
                        route in A_SHARE_ROUTE_TARGETS
                        and isinstance(value, int)
                        and not isinstance(value, bool)
                        and value >= 0
                        for route, value in route_counts.items()
                    )
                )
                if not route_counts_valid:
                    errors.append("markets.a_share.stats.route_counts is invalid")
                elif isinstance(selected_size, int) and sum(route_counts.values()) != selected_size:
                    errors.append("markets.a_share.stats.route_counts must add up to selected size")
                if route_counts_valid:
                    expected_route_shortfalls = {
                        route: target - route_counts.get(route, 0)
                        for route, target in A_SHARE_ROUTE_TARGETS.items()
                        if route_counts.get(route, 0) < target
                    }
                    if route_shortfalls != expected_route_shortfalls:
                        errors.append("markets.a_share.stats.route_shortfalls is inconsistent")
        trade_window = section.get("trade_window") or {}
        if trade_window.get("calendar_id") != calendar_id(market_key):
            errors.append(f"markets.{market_key}.trade_window.calendar_id is invalid")
        if trade_window.get("calendar_version") != CALENDAR_VERSION:
            errors.append(f"markets.{market_key}.trade_window.calendar_version is invalid")
        if trade_window.get("horizon_sessions") != 10:
            errors.append(f"markets.{market_key}.trade_window.horizon_sessions must be 10")
        expected_window = expected_windows.get(market_key) or {}
        if trade_window.get("decision_time") != expected_window.get("decision_time"):
            errors.append(f"markets.{market_key}.trade_window.decision_time is invalid")
        if trade_window.get("entry_session_open_at") != expected_window.get("entry_session_open_at"):
            errors.append(f"markets.{market_key}.trade_window.entry_session_open_at is invalid")
        if trade_window.get("entry_trade_date") != next_trade_dates.get(market_key):
            errors.append(f"markets.{market_key}.trade_window entry does not match next_trade_dates")
        if trade_window.get("forecast_end_trade_date") != forecast_end_dates.get(market_key):
            errors.append(f"markets.{market_key}.trade_window end does not match forecast_end_dates")
        decision = (markets[market_key] or {}).get("decision") or {}
        watchlist = decision.get("watchlist") if isinstance(decision, dict) else None
        if not isinstance(watchlist, list):
            errors.append(f"markets.{market_key}.decision.watchlist must be a list")
        else:
            for index, row in enumerate(watchlist):
                if not isinstance(row, dict):
                    errors.append(f"markets.{market_key}.decision.watchlist[{index}] must be an object")
        for candidate in decision_candidates(decision if isinstance(decision, dict) else {}):
            code = candidate.get("code") or candidate.get("symbol")
            range_2d = candidate.get("estimated_2d_range")
            range_10d = candidate.get("estimated_10d_range")
            range_2w = candidate.get("estimated_2w_range")
            if not isinstance(range_2d, dict):
                errors.append(f"{market_key}:{code} estimated_2d_range is required")
            elif range_2d.get("horizon_trade_days") != 2:
                errors.append(f"{market_key}:{code} estimated_2d_range horizon must be 2")
            if not isinstance(range_10d, dict):
                errors.append(f"{market_key}:{code} estimated_10d_range is required")
            elif range_10d.get("horizon_trade_days") != 10:
                errors.append(f"{market_key}:{code} estimated_10d_range horizon must be 10")
            if not isinstance(range_2w, dict):
                errors.append(f"{market_key}:{code} estimated_2w_range compatibility alias is required")
            elif range_2w.get("horizon_trade_days") != 10:
                errors.append(f"{market_key}:{code} estimated_2w_range horizon must be 10")
            if isinstance(range_10d, dict) and isinstance(range_2w, dict):
                comparable_fields = ("low_pct", "high_pct", "horizon_trade_days", "method_id", "calibrated")
                if any(range_10d.get(field) != range_2w.get(field) for field in comparable_fields):
                    errors.append(f"{market_key}:{code} estimated_2w_range must alias estimated_10d_range")
            analysis = ((candidate.get("analysis_projects") or {}).get("dual_low") or {})
            status = analysis.get("status")
            if status not in VALID_CANDIDATE_STATUSES:
                errors.append(f"{market_key}:{candidate.get('code')} dual-low status is invalid")
                continue
            if analysis.get("participates_in_decision") is not False:
                errors.append(f"{market_key}:{candidate.get('code')} dual-low decision flag is invalid")
            if market_key in {"hk", "us"} and status != "not_applicable":
                errors.append(f"{market_key}:{candidate.get('code')} must be not_applicable")
            if market_key == "a_share" and status == "not_applicable":
                errors.append(f"a_share:{candidate.get('code')} cannot be not_applicable")
            if status == "ranked":
                for field in ("base_score", "final_score"):
                    value = analysis.get(field)
                    if not finite_number(value) or not 0 <= value <= 100:
                        errors.append(f"a_share:{candidate.get('code')} {field} is invalid")
                rank = analysis.get("rank")
                denominator = analysis.get("rank_universe_size")
                if not isinstance(rank, int) or not isinstance(denominator, int) or not 1 <= rank <= denominator:
                    errors.append(f"a_share:{candidate.get('code')} rank is invalid")
            elif analysis.get("final_score") is not None or analysis.get("rank") is not None:
                errors.append(f"{market_key}:{candidate.get('code')} unscored values must be null")

    global_decision = snapshot.get("global_decision")
    if global_decision is None:
        errors.append("global_decision is required")
    else:
        if not isinstance(global_decision, dict):
            errors.append("global_decision must be an object")
        else:
            if global_decision.get("contract_version") != "global-10d-v1":
                errors.append("global_decision.contract_version is invalid")
            if global_decision.get("decision_scope") != "global_10d":
                errors.append("global_decision.decision_scope is invalid")
            action = global_decision.get("action")
            if action not in {"NO_VALID_PICK", "REVIEW_EXECUTABLE_PICK"}:
                errors.append("global_decision.action is invalid")
            if global_decision.get("action_basis") != "strict_cross_market_gate_v1":
                errors.append("global_decision.action_basis is invalid")
            if not strict_boolean(global_decision.get("event_pipeline_scanned")):
                errors.append("global_decision.event_pipeline_scanned must be a boolean")
            if "calibrated" not in global_decision or not strict_boolean(global_decision.get("calibrated")):
                errors.append("global_decision.calibrated must be a boolean")
            calibrated = global_decision.get("calibrated") is True
            if not calibrated and global_decision.get("probability") is not None:
                errors.append("uncalibrated global decision probability must be null")
            if not calibrated and global_decision.get("probability_status") != "UNAVAILABLE":
                errors.append("uncalibrated global decision must be UNAVAILABLE")
            blocker_codes = global_decision.get("blocker_codes")
            if not isinstance(blocker_codes, list):
                errors.append("global_decision.blocker_codes must be a list")
                blocker_codes = []
            primary = global_decision.get("primary")
            if action == "NO_VALID_PICK":
                if primary is not None:
                    errors.append("NO_VALID_PICK must not expose a primary candidate")
                if not blocker_codes:
                    errors.append("NO_VALID_PICK must expose at least one blocker code")
            elif action == "REVIEW_EXECUTABLE_PICK":
                if not calibrated:
                    errors.append("REVIEW_EXECUTABLE_PICK requires calibrated=true")
                if global_decision.get("event_pipeline_scanned") is not True:
                    errors.append("REVIEW_EXECUTABLE_PICK requires event_pipeline_scanned=true")
                if global_decision.get("probability_status") != "CALIBRATED":
                    errors.append("REVIEW_EXECUTABLE_PICK probability_status must be CALIBRATED")
                if not probability(global_decision.get("probability")):
                    errors.append("REVIEW_EXECUTABLE_PICK probability must be between 0 and 1")
                if blocker_codes:
                    errors.append("REVIEW_EXECUTABLE_PICK must not expose blocker codes")
                if not isinstance(ten_day_model, dict):
                    errors.append("REVIEW_EXECUTABLE_PICK requires a ten-day model")
                else:
                    for field in ("calibrated", "costs_ready", "tail_risk_ready", "participates_in_decision"):
                        if ten_day_model.get(field) is not True:
                            errors.append(f"REVIEW_EXECUTABLE_PICK requires ten_day_return.{field}=true")
                if not isinstance(primary, dict):
                    errors.append("REVIEW_EXECUTABLE_PICK must expose a primary candidate")
                else:
                    if primary.get("status") != "EXECUTABLE":
                        errors.append("executable primary status must be EXECUTABLE")
                    if not isinstance(primary.get("prediction_id"), str) or not primary.get("prediction_id"):
                        errors.append("executable primary prediction_id is required")
                    if primary.get("score_kind") not in VALID_EXECUTABLE_SCORE_KINDS:
                        errors.append("executable primary score_kind must be a calibrated model output")
                    if not isinstance(primary.get("model_id"), str) or not primary.get("model_id"):
                        errors.append("executable primary model_id is required")
                    elif isinstance(ten_day_model, dict) and primary.get("model_id") != ten_day_model.get("model_id"):
                        errors.append("executable primary model_id must match ten_day_return.model_id")
                    if not isinstance(primary.get("label_version"), str) or not primary.get("label_version"):
                        errors.append("executable primary label_version is required")
                    elif isinstance(ten_day_model, dict) and primary.get("label_version") != ten_day_model.get("label_version"):
                        errors.append("executable primary label_version must match ten_day_return.label_version")
                    if primary.get("calibrated") is not True:
                        errors.append("executable primary must be calibrated")
                    if not probability(primary.get("probability")):
                        errors.append("executable primary probability must be between 0 and 1")
                    elif primary.get("probability") != global_decision.get("probability"):
                        errors.append("executable primary probability must match global_decision.probability")
                    if not finite_number(primary.get("expected_net_utility")):
                        errors.append("executable primary expected_net_utility must be finite")
                    if not finite_number(primary.get("transaction_cost")) or primary.get("transaction_cost", -1) < 0:
                        errors.append("executable primary transaction_cost must be a non-negative finite number")
                    if not finite_number(primary.get("tail_risk")) or primary.get("tail_risk", -1) < 0:
                        errors.append("executable primary tail_risk must be a non-negative finite number")
            research = global_decision.get("research_priority")
            if research is not None:
                if not isinstance(research, dict):
                    errors.append("research_priority must be an object")
                else:
                    if research.get("status") != "RESEARCH_ONLY":
                        errors.append("research_priority must be RESEARCH_ONLY")
                    if research.get("score_kind") != "RULE_PRIORITY":
                        errors.append("research_priority score_kind must be RULE_PRIORITY")
                    if not finite_number(research.get("priority_score")) or not 0 <= research["priority_score"] <= 100:
                        errors.append("research_priority priority_score must be between 0 and 100")
                    if research.get("probability") is not None:
                        errors.append("research_priority probability must be null until calibrated")
                    if research.get("calibrated") is not False:
                        errors.append("research_priority calibrated must be false")
                    if research.get("model_id") != "ten-day-rule-shadow-v1":
                        errors.append("research_priority model_id is invalid")
                    if research.get("label_version") != "shadow-net-return-10-session-v1":
                        errors.append("research_priority label_version is invalid")
                    if not isinstance(research.get("prediction_id"), str) or not research.get("prediction_id"):
                        errors.append("research_priority prediction_id is required")
                    research_market = research.get("market")
                    if research_market in expected_markets:
                        if research.get("calendar_id") != calendar_id(research_market):
                            errors.append("research_priority calendar_id is invalid")
                        if research.get("entry_trade_date") != next_trade_dates.get(research_market):
                            errors.append("research_priority entry_trade_date is invalid")
                        if research.get("forecast_end_trade_date") != forecast_end_dates.get(research_market):
                            errors.append("research_priority forecast_end_trade_date is invalid")
                    else:
                        errors.append("research_priority market is invalid")
            market_states = global_decision.get("market_states") or {}
            if not isinstance(market_states, dict) or set(market_states) != {"a_share", "hk", "us"}:
                errors.append("global_decision.market_states must cover three markets")
            for market_key, state in (market_states.items() if isinstance(market_states, dict) else []):
                if not isinstance(state, dict) or state.get("state") not in {"READY", "DEGRADED", "BLOCKED"}:
                    errors.append(f"global_decision.market_states.{market_key} is invalid")
                    continue
                published_state = state.get("state")
                derived_state, derived_reasons = derived_market_states.get(market_key, ("BLOCKED", []))
                if STATE_SEVERITY[published_state] < STATE_SEVERITY[derived_state]:
                    errors.append(
                        f"global_decision.market_states.{market_key} understates derived {derived_state} coverage"
                    )
                reason_codes = state.get("reason_codes") or []
                if not isinstance(reason_codes, list) or not set(derived_reasons).issubset(reason_codes):
                    errors.append(f"global_decision.market_states.{market_key}.reason_codes are incomplete")
                if action == "REVIEW_EXECUTABLE_PICK" and published_state != "READY":
                    errors.append(f"REVIEW_EXECUTABLE_PICK requires market_states.{market_key}=READY")
    errors.extend(validate_live_candidate_publication(snapshot))
    return errors


def validate_snapshot_file(path: pathlib.Path) -> list[str]:
    """Validate both the snapshot payload and its immutable publication pair."""

    try:
        latest_bytes = path.read_bytes()
    except OSError as exc:
        return [f"latest snapshot file is unreadable: {exc}"]
    try:
        snapshot = json.loads(latest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"latest snapshot JSON is invalid: {exc}"]
    if not isinstance(snapshot, dict):
        return ["latest snapshot JSON must be an object"]

    errors = validate_snapshot(snapshot)
    snapshot_key = snapshot.get("snapshot_key")
    if not safe_snapshot_key(snapshot_key):
        return errors
    immutable_path = path.parent / snapshot_key
    if not immutable_path.is_file():
        errors.append("immutable snapshot file is missing")
        return errors
    try:
        immutable_bytes = immutable_path.read_bytes()
    except OSError as exc:
        errors.append(f"immutable snapshot file is unreadable: {exc}")
        return errors
    if immutable_bytes != latest_bytes:
        errors.append("latest snapshot and immutable snapshot bytes must match")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/picks/latest.json")
    args = parser.parse_args()
    path = pathlib.Path(args.path)
    errors = validate_snapshot_file(path)
    if errors:
        raise SystemExit("Snapshot validation failed:\n- " + "\n- ".join(errors))
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    model = snapshot["analysis_models"]["dual_low"]
    print(
        f"Snapshot valid: {path} | dual_low={model.get('status')} "
        f"input={model.get('input_count')} eligible={model.get('eligible_count')}"
    )


if __name__ == "__main__":
    main()

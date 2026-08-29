#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import production_rule_model
from market_calendar import (
    CALENDAR_VERSION,
    calendar_id,
    expected_quote_session,
    market_trade_windows,
    quote_session_phase,
    session_close_at,
    session_open_at,
)


VALID_MODEL_STATUSES = {"available", "unavailable"}
VALID_CANDIDATE_STATUSES = {"ranked", "rejected", "unavailable", "not_applicable"}
VALID_EXECUTABLE_SCORE_KINDS = {"TEN_DAY_EXPECTED_NET_UTILITY"}
PRODUCTION_CONTRACT_VERSION = "production-rule-10d-v1"
PRODUCTION_SCORE_KIND = "RULE_QUALIFICATION_SCORE"
PRODUCTION_QUALIFICATION_TRACKS = ("event_catalyst", "quality_technical")
HISTORICAL_PRODUCTION_RULE_CONTRACTS = {
    "smart-selector-2026-08-25.1-production-rule": (
        "strict_rule_qualification_v1",
        "ten-day-audited-rule-ensemble-v1",
    ),
    "smart-selector-2026-08-26.1-candidate-rule": (
        "candidate_level_rule_qualification_v2",
        "ten-day-audited-rule-ensemble-v2",
    ),
    "smart-selector-2026-08-26.2-dual-track-rule": (
        "dual_track_candidate_qualification_v3",
        "ten-day-audited-rule-ensemble-v3",
    ),
}
PRODUCTION_RULE_ACTION_BASIS = "dual_track_candidate_qualification_v4"
PRODUCTION_RULE_MODEL_ID = "ten-day-audited-rule-ensemble-v4"
PRODUCTION_RULE_INPUTS_CONTRACT_VERSION = "production-rule-inputs-v2"
PRODUCTION_RULE_MODEL_VERSION = "smart-selector-2026-08-29.1-two-tier-rule"
CURRENT_PRODUCTION_RULE_CONTRACT = (
    PRODUCTION_RULE_ACTION_BASIS,
    PRODUCTION_RULE_MODEL_ID,
)
DUAL_TRACK_RULE_CONTRACTS = {
    HISTORICAL_PRODUCTION_RULE_CONTRACTS["smart-selector-2026-08-26.2-dual-track-rule"],
    CURRENT_PRODUCTION_RULE_CONTRACT,
}
SUPPORTED_PRODUCTION_RULE_CONTRACTS = {
    *HISTORICAL_PRODUCTION_RULE_CONTRACTS.values(),
    CURRENT_PRODUCTION_RULE_CONTRACT,
}
STATE_SEVERITY = {"READY": 0, "DEGRADED": 1, "BLOCKED": 2}
SCHEDULE_ON_TIME_MAX_SECONDS = 4 * 60 * 60
SCHEDULE_LATE_EFFECTIVE_MAX_SECONDS = 12 * 60 * 60
# The gate records delay before dependency installation and snapshot generation.
# Allow one bounded workflow hour between that audit moment and generated_at.
SCHEDULE_GENERATION_TOLERANCE_SECONDS = 60 * 60
VALID_VOLUME_UNITS = {"lot", "share"}
MARKET_RECALL_TARGETS = {"a_share": 300, "hk": 200, "us": 300}
A_SHARE_BOARD_TARGETS = {"sh_main": 90, "sz_main": 75, "chinext": 75, "star": 60}
A_SHARE_ROUTE_TARGETS = {"event": 40, "momentum": 80, "pullback": 65, "liquidity": 85, "history": 30}
EXPANDED_RECALL_UNIVERSE_VERSION = "recall-v2-4-a300-full-score"
DYNAMIC_HK_US_UNIVERSE_VERSION = "recall-v2-5-dynamic-hk-us"
FULL_A_SHARE_SCORE_UNIVERSE_VERSIONS = {
    EXPANDED_RECALL_UNIVERSE_VERSION,
    DYNAMIC_HK_US_UNIVERSE_VERSION,
}
DYNAMIC_MARKET_ORIGIN = "dynamic_market_snapshot"
DYNAMIC_MARKET_CACHE_ORIGIN = "dynamic_market_snapshot_cache"
DYNAMIC_MARKET_RECALL_POLICY_VERSION = "hk-us-cross-section-v2-hk-intraday-audited"
DYNAMIC_MARKET_LEGACY_RECALL_POLICY_VERSIONS = {"hk-us-cross-section-v1"}
DYNAMIC_MARKET_ROUTE_TARGETS = {
    "hk": {"momentum": 45, "pullback": 35, "activity": 35, "quality": 30, "liquidity": 55},
    "us": {"momentum": 70, "pullback": 50, "activity": 45, "quality": 45, "liquidity": 90},
}
DYNAMIC_MARKET_MIN_ELIGIBLE = {"hk": 210, "us": 315}
DYNAMIC_MARKET_SOURCE_TIMEZONES = {
    "hk": ZoneInfo("Asia/Hong_Kong"),
    "us": ZoneInfo("America/New_York"),
}
DYNAMIC_MARKET_REPORT_TIMEZONE = ZoneInfo("Asia/Shanghai")
DYNAMIC_DISCOVERY_MAX_GENERATION_LAG = dt.timedelta(hours=6)
DYNAMIC_DISCOVERY_MAX_REGULAR_SOURCE_AGE = dt.timedelta(minutes=45)
DYNAMIC_DISCOVERY_MAX_SOURCE_FUTURE_SKEW = dt.timedelta(minutes=5)
HK_INTRADAY_LIQUIDITY_POLICY_VERSION = "hk-intraday-scaled-amount-v1"
HK_STANDARD_MIN_AMOUNT_HKD = 20_000_000
HK_INTRADAY_MIN_AMOUNT_HKD = 2_000_000
HK_INTRADAY_MIN_MARKET_CAP_HKD = 1_000_000_000
A_SHARE_DEEP_SCORE_LIMIT = 300
A_SHARE_MIN_TECHNICAL_SCORE_COVERAGE = 0.98
A_SHARE_MIN_DEEP_SCORE_COVERAGE = 0.98
A_SHARE_POOL_HEALTH_CONTRACT_VERSION = "a-share-pool-health-v2"
YAHOO_QUOTE_FRESHNESS_POLICY = "latest_exchange_session_v1"
TEN_DAY_SHADOW_MODEL_ID = "ten-day-technical-shadow-v1"
TEN_DAY_SHADOW_LABEL_VERSION = "r10-net-total-return-v1"
TEN_DAY_SHADOW_FEATURE_SCHEMA = "technical-d1-v1"
TEN_DAY_SHADOW_PROVENANCE = "current_universe_historical_backfill"
TEN_DAY_SHADOW_STATUSES = {
    "SHADOW_READY",
    "SHADOW_REJECTED",
    "INSUFFICIENT_DATA",
    "UNAVAILABLE",
}
TEN_DAY_SHADOW_QUALITY_GATE = {
    "minimum_independent_test_dates": 40,
    "minimum_brier_skill": 0.01,
    "minimum_auc": 0.55,
    "maximum_ece_10bin": 0.10,
    "minimum_top_decile_excess_vs_mean": 0.005,
    "minimum_top_decile_mean_net_return": 0.0,
}
EVIDENCE_LOOP_MODEL_VERSIONS = {
    "smart-selector-2026-08-23.3-evidence-loop",
    "smart-selector-2026-08-25.1-production-rule",
    "smart-selector-2026-08-26.1-candidate-rule",
    "smart-selector-2026-08-26.2-dual-track-rule",
    PRODUCTION_RULE_MODEL_VERSION,
}
DYNAMIC_MARKET_MODEL_VERSIONS = {
    "smart-selector-2026-08-23.2-dynamic-hk-us",
    *EVIDENCE_LOOP_MODEL_VERSIONS,
}
PRIMARY_SCHEDULE_SLOTS = {(8, 17), (10, 17), (12, 17), (15, 17), (16, 17), (20, 17), (22, 47)}
FALLBACK_SCHEDULE_MAP = {
    (8, 47): (8, 17),
    (10, 47): (10, 17),
    (12, 47): (12, 17),
    (15, 47): (15, 17),
    (16, 47): (16, 17),
    (20, 47): (20, 17),
    (23, 17): (22, 47),
}
US_POST_CLOSE_PRIMARY_SLOTS = {(4, 17), (5, 17)}
US_POST_CLOSE_FALLBACK_MAP = {
    (4, 47): (4, 17),
    (5, 47): (5, 17),
}
ALL_PRIMARY_SCHEDULE_SLOTS = PRIMARY_SCHEDULE_SLOTS | US_POST_CLOSE_PRIMARY_SLOTS
ALL_FALLBACK_SCHEDULE_MAP = {
    **FALLBACK_SCHEDULE_MAP,
    **US_POST_CLOSE_FALLBACK_MAP,
}
TEN_DAY_RANK_MODEL_ID = "ten-day-excess-rank-shadow-v2"
TEN_DAY_RANK_LABEL_VERSION = "r10-net-excess-return-v2"
TEN_DAY_RANK_BENCHMARKS = {"a_share": "510300", "hk": "2800.HK", "us": "SPY"}
TEN_DAY_RANK_STATUSES = {"COLLECTING", "SHADOW_READY"}


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def probability(value) -> bool:
    return finite_number(value) and 0 <= value <= 1


def strict_boolean(value) -> bool:
    return type(value) is bool


def _aware_automation_moment(value) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _configured_schedule_invocation(moment: dt.datetime) -> bool:
    """Validate one invocation against the market-local weekday it represents.

    The US post-close run occurs at 04:17/04:47 China time during New York
    daylight saving and 05:17/05:47 during standard time.  A Friday US close is
    therefore a legal Saturday-morning invocation in China; validating it with
    a China Monday-Friday rule would reject the real production schedule.
    """

    local = moment.astimezone(ZoneInfo("Asia/Shanghai"))
    clock = (local.hour, local.minute)
    if clock in US_POST_CLOSE_PRIMARY_SLOTS or clock in US_POST_CLOSE_FALLBACK_MAP:
        new_york = moment.astimezone(ZoneInfo("America/New_York"))
        return new_york.weekday() < 5 and new_york.hour == 16
    return local.weekday() < 5 and (
        clock in PRIMARY_SCHEDULE_SLOTS or clock in FALLBACK_SCHEDULE_MAP
    )


def _append_schedule_automation_errors(snapshot: dict, errors: list[str]) -> None:
    if snapshot.get("model_version") != PRODUCTION_RULE_MODEL_VERSION:
        return
    automation = snapshot.get("automation")
    automation = automation if isinstance(automation, dict) else {}
    if str(automation.get("trigger") or "") != "schedule":
        return

    checkpoint = _aware_automation_moment(automation.get("scheduled_slot"))
    invocation = _aware_automation_moment(automation.get("scheduled_invocation_slot"))
    if checkpoint is None:
        errors.append("scheduled automation.scheduled_slot must be an aware ISO datetime")
    if invocation is None:
        errors.append("scheduled automation.scheduled_invocation_slot must be an aware ISO datetime")
    if checkpoint is None or invocation is None:
        return

    local_invocation = invocation.astimezone(ZoneInfo("Asia/Shanghai"))
    invocation_clock = (local_invocation.hour, local_invocation.minute)
    expected_clock = ALL_FALLBACK_SCHEDULE_MAP.get(invocation_clock, invocation_clock)
    if not _configured_schedule_invocation(invocation):
        errors.append("automation.scheduled_invocation_slot is not a configured invocation")
        return
    expected_checkpoint = local_invocation.replace(
        hour=expected_clock[0],
        minute=expected_clock[1],
        second=0,
        microsecond=0,
    )
    if checkpoint.astimezone(dt.timezone.utc) != expected_checkpoint.astimezone(dt.timezone.utc):
        errors.append("automation.scheduled_slot does not match its invocation checkpoint")

    recovery_fields_present = any(
        field in automation
        for field in (
            "source_invocation_slot",
            "scheduler_delay_seconds",
            "recovery_mode",
        )
    )
    if not recovery_fields_present:
        # Compatibility bridge for snapshots published before late-recovery
        # metadata was added. Newly generated snapshots always carry it.
        return

    recovery_mode = automation.get("recovery_mode")
    if recovery_mode not in {"on_time", "late_cron_recovery"}:
        errors.append("automation.recovery_mode is invalid")
    source_invocation = _aware_automation_moment(
        automation.get("source_invocation_slot")
    )
    scheduler_delay = automation.get("scheduler_delay_seconds")
    if recovery_mode in {"on_time", "late_cron_recovery"}:
        if source_invocation is None:
            errors.append(
                "scheduled automation.source_invocation_slot must be an aware ISO datetime"
            )
        if (
            not isinstance(scheduler_delay, int)
            or isinstance(scheduler_delay, bool)
            or scheduler_delay < 0
        ):
            errors.append(
                "automation.scheduler_delay_seconds must be a non-negative integer"
            )
    elif scheduler_delay is not None and (
        not isinstance(scheduler_delay, int)
        or isinstance(scheduler_delay, bool)
        or scheduler_delay < 0
    ):
        errors.append(
            "automation.scheduler_delay_seconds must be a non-negative integer"
        )

    generated = _aware_automation_moment(snapshot.get("generated_at"))
    if generated is not None and invocation > generated:
        errors.append("automation.scheduled_invocation_slot cannot be after generated_at")

    if source_invocation is not None:
        source_local = source_invocation.astimezone(ZoneInfo("Asia/Shanghai"))
        source_clock = (source_local.hour, source_local.minute)
        if not _configured_schedule_invocation(source_invocation):
            errors.append("automation.source_invocation_slot is not a configured invocation")
        if generated is not None and source_invocation > generated:
            errors.append("automation.source_invocation_slot cannot be in the future")
        if recovery_mode == "on_time" and source_invocation != invocation:
            errors.append(
                "on-time automation.source_invocation_slot must equal scheduled_invocation_slot"
            )
        if recovery_mode == "late_cron_recovery" and source_invocation > invocation:
            errors.append(
                "late recovery source_invocation_slot cannot follow scheduled_invocation_slot"
            )

    if (
        generated is not None
        and source_invocation is not None
        and isinstance(scheduler_delay, int)
        and not isinstance(scheduler_delay, bool)
        and scheduler_delay >= 0
    ):
        observed_source_delay = (generated - source_invocation).total_seconds()
        if abs(observed_source_delay - scheduler_delay) > SCHEDULE_GENERATION_TOLERANCE_SECONDS:
            errors.append(
                "automation.scheduler_delay_seconds is inconsistent with generated_at"
            )
        if recovery_mode == "on_time" and scheduler_delay > SCHEDULE_ON_TIME_MAX_SECONDS:
            errors.append("on-time automation exceeds the four-hour scheduler window")
        if recovery_mode == "late_cron_recovery" and scheduler_delay <= SCHEDULE_ON_TIME_MAX_SECONDS:
            errors.append("late recovery must exceed the four-hour scheduler window")

    if generated is not None and recovery_mode == "late_cron_recovery":
        effective_age = (generated - invocation).total_seconds()
        if effective_age > (
            SCHEDULE_LATE_EFFECTIVE_MAX_SECONDS + SCHEDULE_GENERATION_TOLERANCE_SECONDS
        ):
            errors.append("late recovery effective invocation exceeds the twelve-hour window")


def _append_ten_day_trade_plan_errors(plan, prefix: str, errors: list[str]) -> None:
    field = f"{prefix}.ten_day_trade_plan"
    if not isinstance(plan, dict):
        errors.append(f"{field} is required for current V4 qualified rows")
        return
    if plan.get("contract_version") != "ten-day-trade-plan-v1":
        errors.append(f"{field}.contract_version is invalid")
    if plan.get("status") != "REVIEW_REQUIRED":
        errors.append(f"{field}.status must be REVIEW_REQUIRED")
    if plan.get("horizon_trade_days") != 10:
        errors.append(f"{field}.horizon_trade_days must be 10")

    quote = plan.get("reference_quote")
    quote = quote if isinstance(quote, dict) else {}
    price = quote.get("price")
    if not finite_number(price) or price <= 0:
        errors.append(f"{field}.reference_quote.price must be positive")
    if quote.get("kind") != "published_snapshot_quote":
        errors.append(f"{field}.reference_quote.kind is invalid")
    if not isinstance(quote.get("source"), str) or not quote.get("source"):
        errors.append(f"{field}.reference_quote.source is required")
    if parse_aware_datetime(quote.get("source_as_of")) is None:
        errors.append(f"{field}.reference_quote.source_as_of is invalid")
    if not isinstance(quote.get("quote_status"), str) or not quote.get("quote_status"):
        errors.append(f"{field}.reference_quote.quote_status is required")
    currency = quote.get("currency")
    if currency not in {"CNY", "HKD", "USD"}:
        errors.append(f"{field}.reference_quote.currency is invalid")

    zone = plan.get("entry_zone")
    zone = zone if isinstance(zone, dict) else {}
    low, high = zone.get("low"), zone.get("high")
    if not finite_number(low) or not finite_number(high) or low <= 0 or high <= low:
        errors.append(f"{field}.entry_zone is invalid")
    elif finite_number(price) and not (low <= price <= high):
        errors.append(f"{field}.entry_zone must contain the reference quote")
    if zone.get("currency") != currency:
        errors.append(f"{field}.entry_zone currency is inconsistent")

    plan_sections: dict[str, dict] = {}
    for section_name in ("invalidation", "target"):
        section = plan.get(section_name)
        section = section if isinstance(section, dict) else {}
        plan_sections[section_name] = section
        section_price = section.get("price")
        if not finite_number(section_price) or section_price <= 0:
            errors.append(f"{field}.{section_name}.price must be positive")
        if section.get("currency") != currency:
            errors.append(f"{field}.{section_name} currency is inconsistent")
        if not isinstance(section.get("source"), str) or not section.get("source"):
            errors.append(f"{field}.{section_name}.source is required")
    if finite_number(price) and finite_number(plan_sections["invalidation"].get("price")):
        if plan_sections["invalidation"]["price"] >= price:
            errors.append(f"{field}.invalidation.price must be below the reference quote")
    if finite_number(price) and finite_number(plan_sections["target"].get("price")):
        if plan_sections["target"]["price"] <= price:
            errors.append(f"{field}.target.price must be above the reference quote")

    position = plan.get("position_limit")
    if not isinstance(position, dict) or position.get("max_single_name_weight_pct") != 10.0:
        errors.append(f"{field}.position_limit is invalid")
    elif position.get("policy") != "strategy_safety_cap_not_personalized":
        errors.append(f"{field}.position_limit.policy is invalid")
    if plan.get("exit_rules") != [
        "EXIT_IF_INVALIDATION_PRICE_BREACHED",
        "REVIEW_AT_TENTH_SESSION_CLOSE",
        "DO_NOT_CHASE_ABOVE_ENTRY_ZONE",
    ]:
        errors.append(f"{field}.exit_rules is invalid")
    if plan.get("is_personalized_advice") is not False:
        errors.append(f"{field}.is_personalized_advice must be false")
    for date_field in ("entry_trade_date", "review_end_trade_date"):
        try:
            dt.date.fromisoformat(str(plan.get(date_field) or ""))
        except ValueError:
            errors.append(f"{field}.{date_field} is invalid")


def _append_production_decision_errors(snapshot: dict, errors: list[str]) -> None:
    decision = snapshot.get("production_decision")
    if not isinstance(decision, dict):
        # A push deploy first adopts the last verified online snapshot. Let the
        # immediately preceding model version pass that compatibility bridge;
        # every snapshot generated by the production-rule model must publish
        # the full decision contract below.
        if snapshot.get("model_version") == PRODUCTION_RULE_MODEL_VERSION:
            errors.append("production_decision is required")
        return
    if decision.get("contract_version") != PRODUCTION_CONTRACT_VERSION:
        errors.append("production_decision.contract_version is invalid")
    if decision.get("decision_scope") != "global_10d_bounded_recall":
        errors.append("production_decision.decision_scope is invalid")
    rule_contract = (decision.get("action_basis"), decision.get("rule_model_id"))
    exact_current_v4 = bool(
        snapshot.get("model_version") == PRODUCTION_RULE_MODEL_VERSION
        and rule_contract == CURRENT_PRODUCTION_RULE_CONTRACT
    )
    if rule_contract not in SUPPORTED_PRODUCTION_RULE_CONTRACTS:
        errors.append("production_decision rule contract is invalid")
    contract_by_model = {
        **HISTORICAL_PRODUCTION_RULE_CONTRACTS,
        PRODUCTION_RULE_MODEL_VERSION: CURRENT_PRODUCTION_RULE_CONTRACT,
    }
    expected_contract = contract_by_model.get(snapshot.get("model_version"))
    expected_model = next(
        (model for model, contract in contract_by_model.items() if contract == rule_contract),
        None,
    )
    # Every rule payload is an immutable model/contract pair.  Historical
    # V1-V3 snapshots remain readable, but can never masquerade as current V4.
    if (
        (expected_contract is not None and rule_contract != expected_contract)
        or (expected_model is not None and snapshot.get("model_version") != expected_model)
    ):
        errors.append("production_decision rule contract does not match model_version")
    if decision.get("score_kind") != PRODUCTION_SCORE_KIND:
        errors.append("production_decision.score_kind is invalid")
    if decision.get("probability_status") != "NOT_APPLICABLE":
        errors.append("production_decision.probability_status must be NOT_APPLICABLE")
    if decision.get("probability") is not None:
        errors.append("production_decision probability must be null")
    if decision.get("calibrated") is not False:
        errors.append("production_decision calibrated must be false")
    if decision.get("expected_net_utility") is not None:
        errors.append("production_decision expected_net_utility must be null")

    action = decision.get("action")
    if action not in {"QUALIFIED_PICK", "NO_QUALIFIED_PICK"}:
        errors.append("production_decision.action is invalid")
    blocker_codes = decision.get("blocker_codes")
    if not isinstance(blocker_codes, list):
        errors.append("production_decision.blocker_codes must be a list")
        blocker_codes = []
    evaluated = decision.get("evaluated_candidates")
    if not isinstance(evaluated, list):
        errors.append("production_decision.evaluated_candidates must be a list")
        evaluated = []
    qualified = []
    for index, row in enumerate(evaluated):
        prefix = f"production_decision.evaluated_candidates[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if row.get("rule_model_id") != decision.get("rule_model_id"):
            errors.append(f"{prefix}.rule_model_id is invalid")
        if row.get("score_kind") != PRODUCTION_SCORE_KIND:
            errors.append(f"{prefix}.score_kind is invalid")
        score = row.get("qualification_score")
        if not finite_number(score) or not 0 <= score <= 100:
            errors.append(f"{prefix}.qualification_score is invalid")
        if row.get("probability") is not None or row.get("expected_net_utility") is not None:
            errors.append(f"{prefix} must not claim probability or expected utility")
        if row.get("calibrated") is not False:
            errors.append(f"{prefix}.calibrated must be false")
        row_blockers = row.get("blocker_codes")
        if not isinstance(row_blockers, list):
            errors.append(f"{prefix}.blocker_codes must be a list")
            row_blockers = []
        dual_track_evaluations: dict[str, dict] | None = None
        if rule_contract in DUAL_TRACK_RULE_CONTRACTS:
            raw_track_evaluations = row.get("track_evaluations")
            valid_track_evaluations = bool(
                isinstance(raw_track_evaluations, list)
                and len(raw_track_evaluations) == len(PRODUCTION_QUALIFICATION_TRACKS)
                and [item.get("track") for item in raw_track_evaluations if isinstance(item, dict)]
                == list(PRODUCTION_QUALIFICATION_TRACKS)
                and all(
                    isinstance(item, dict)
                    and item.get("status") in {"PASS", "FAIL"}
                    and isinstance(item.get("blocker_codes"), list)
                    for item in raw_track_evaluations
                )
            )
            if not valid_track_evaluations:
                errors.append(f"{prefix}.track_evaluations is invalid")
            else:
                dual_track_evaluations = {
                    item["track"]: item for item in raw_track_evaluations
                }
                for track_name in PRODUCTION_QUALIFICATION_TRACKS:
                    track_evaluation = dual_track_evaluations[track_name]
                    track_blockers = track_evaluation["blocker_codes"]
                    if track_evaluation["status"] == "PASS" and track_blockers:
                        errors.append(f"{prefix}.track_evaluations {track_name} PASS cannot expose blocker codes")
                    if track_evaluation["status"] == "FAIL" and not track_blockers:
                        errors.append(f"{prefix}.track_evaluations {track_name} FAIL requires blocker codes")
        status = row.get("status")
        if status == "QUALIFIED":
            qualified.append(row)
            if row_blockers:
                errors.append(f"{prefix} QUALIFIED row cannot expose blocker codes")
            if not isinstance(row.get("qualification_id"), str) or not re.fullmatch(r"qual_[0-9a-f]{24}", row["qualification_id"]):
                errors.append(f"{prefix}.qualification_id is invalid")
            if rule_contract in DUAL_TRACK_RULE_CONTRACTS:
                qualification_track = row.get("qualification_track")
                if qualification_track not in PRODUCTION_QUALIFICATION_TRACKS:
                    errors.append(f"{prefix}.qualification_track is invalid")
                matching_track = (
                    dual_track_evaluations.get(qualification_track)
                    if dual_track_evaluations is not None
                    else None
                )
                if not isinstance(matching_track, dict) or matching_track.get("status") != "PASS":
                    errors.append(f"{prefix} selected qualification track must PASS")
                requires_event_scan = (
                    rule_contract
                    == HISTORICAL_PRODUCTION_RULE_CONTRACTS[
                        "smart-selector-2026-08-26.2-dual-track-rule"
                    ]
                    or qualification_track == "event_catalyst"
                )
                if requires_event_scan and row.get("event_candidate_scanned") is not True:
                    errors.append(f"{prefix} requires event candidate scan")
                event_ids = row.get("verified_positive_event_ids")
                if not isinstance(event_ids, list):
                    errors.append(f"{prefix}.verified_positive_event_ids must be a list")
                    event_ids = []
                if qualification_track == "event_catalyst" and not event_ids:
                    errors.append(f"{prefix} event_catalyst requires verified positive event evidence")
                if exact_current_v4:
                    _append_ten_day_trade_plan_errors(row.get("ten_day_trade_plan"), prefix, errors)
            elif row.get("event_candidate_scanned") is not True or not row.get("verified_positive_event_ids"):
                errors.append(f"{prefix} requires verified positive event evidence")
            candidate = row.get("candidate_snapshot")
            if not isinstance(candidate, dict):
                errors.append(f"{prefix}.candidate_snapshot is required")
            elif str(candidate.get("code") or candidate.get("symbol") or "").lower() != str(row.get("code") or "").lower():
                errors.append(f"{prefix}.candidate_snapshot identity is inconsistent")
            state = (((snapshot.get("global_decision") or {}).get("market_states") or {}).get(row.get("market")) or {})
            if state.get("state") != "READY":
                errors.append(f"{prefix} requires its market state READY")
        elif status == "REJECTED":
            if not row_blockers:
                errors.append(f"{prefix} REJECTED row requires blocker codes")
            if rule_contract in DUAL_TRACK_RULE_CONTRACTS:
                if "qualification_track" not in row or row.get("qualification_track") is not None:
                    errors.append(f"{prefix} REJECTED row qualification_track must be null")
                if dual_track_evaluations is not None and any(
                    item.get("status") == "PASS" for item in dual_track_evaluations.values()
                ):
                    errors.append(f"{prefix} REJECTED row cannot contain a PASS track")
        else:
            errors.append(f"{prefix}.status is invalid")

    for field, expected in (
        ("evaluated_candidate_count", len(evaluated)),
        ("qualified_candidate_count", len(qualified)),
        ("rejected_candidate_count", len(evaluated) - len(qualified)),
    ):
        if decision.get(field) != expected:
            errors.append(f"production_decision.{field} is inconsistent")
    published_qualified = decision.get("qualified_candidates")
    if not isinstance(published_qualified, list):
        errors.append("production_decision.qualified_candidates must be a list")
    elif exact_current_v4 and published_qualified != qualified:
        errors.append("production_decision.qualified_candidates must exactly match evaluated qualified rows")
    elif [row.get("qualification_id") for row in published_qualified if isinstance(row, dict)] != [
        row.get("qualification_id") for row in qualified
    ]:
        errors.append("production_decision.qualified_candidates is inconsistent")
    primary = decision.get("primary")
    if action == "QUALIFIED_PICK":
        if blocker_codes:
            errors.append("QUALIFIED_PICK cannot expose production blocker codes")
        if not isinstance(primary, dict):
            errors.append("QUALIFIED_PICK requires a production primary")
        elif exact_current_v4 and (not qualified or primary != qualified[0]):
            errors.append("production primary must exactly match the first qualified evaluated row")
        elif not any(row.get("qualification_id") == primary.get("qualification_id") for row in qualified):
            errors.append("production primary must match one qualified evaluated row")
    elif action == "NO_QUALIFIED_PICK":
        if primary is not None:
            errors.append("NO_QUALIFIED_PICK must not expose a production primary")
        if qualified:
            errors.append("NO_QUALIFIED_PICK cannot retain qualified evaluated rows")
        if not blocker_codes:
            errors.append("NO_QUALIFIED_PICK requires at least one blocker code")

    if exact_current_v4:
        _append_current_v4_rule_input_errors(snapshot, decision, errors)


def _append_current_v4_rule_input_errors(snapshot: dict, decision: dict, errors: list[str]) -> None:
    inputs = snapshot.get("production_rule_inputs")
    if not isinstance(inputs, dict):
        errors.append("production_rule_inputs is required for current V4")
        return
    if inputs.get("contract_version") != PRODUCTION_RULE_INPUTS_CONTRACT_VERSION:
        errors.append("production_rule_inputs.contract_version is invalid")
    if inputs.get("action_basis") != PRODUCTION_RULE_ACTION_BASIS:
        errors.append("production_rule_inputs.action_basis is invalid")
    if inputs.get("rule_model_id") != PRODUCTION_RULE_MODEL_ID:
        errors.append("production_rule_inputs.rule_model_id is invalid")

    ledger_hash = inputs.get("ledger_sha256")
    computed_hash = production_rule_model.production_rule_inputs_sha256(inputs)
    if not isinstance(ledger_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", ledger_hash):
        errors.append("production_rule_inputs.ledger_sha256 is invalid")
    elif computed_hash != ledger_hash:
        errors.append("production_rule_inputs.ledger_sha256 does not match its payload")

    rows = inputs.get("rows")
    if not isinstance(rows, list):
        errors.append("production_rule_inputs.rows must be a list")
        rows = []
    global_decision = snapshot.get("global_decision")
    global_decision = global_decision if isinstance(global_decision, dict) else {}
    global_rows = global_decision.get("evaluated_candidates")
    global_rows = global_rows if isinstance(global_rows, list) else []
    if inputs.get("evaluated_candidate_count") != len(rows):
        errors.append("production_rule_inputs.evaluated_candidate_count does not match rows")
    if len(rows) != len(global_rows):
        errors.append("production_rule_inputs rows must cover every global evaluated candidate")

    identities: set[tuple[str, str]] = set()
    for index, entry in enumerate(rows):
        prefix = f"production_rule_inputs.rows[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        global_row = global_rows[index] if index < len(global_rows) and isinstance(global_rows[index], dict) else {}
        expected_market = str(global_row.get("market") or "").strip() or None
        expected_code = str(global_row.get("code") or global_row.get("symbol") or "").strip() or None
        if type(entry.get("input_index")) is not int or entry.get("input_index") != index:
            errors.append(f"{prefix}.input_index is inconsistent")
        if entry.get("market") != expected_market or entry.get("code") != expected_code:
            errors.append(f"{prefix} identity does not match global evaluated candidate")
        expected_input = production_rule_model.freeze_production_rule_input_row(global_row, index)
        actual_input = production_rule_model.freeze_production_rule_input_row(entry, index)
        if actual_input != expected_input:
            errors.append(f"{prefix} rule fields do not match global evaluated candidate")
        identity = (str(entry.get("market") or ""), str(entry.get("code") or ""))
        if identity in identities:
            errors.append(f"{prefix} identity is duplicated")
        identities.add(identity)
        if type(entry.get("source_candidate_present")) is not bool:
            errors.append(f"{prefix}.source_candidate_present must be a boolean")
        quality_score = entry.get("source_data_quality_score")
        if quality_score is not None and (not finite_number(quality_score) or not 0 <= quality_score <= 100):
            errors.append(f"{prefix}.source_data_quality_score is invalid")
        if entry.get("source_candidate_present") is False and quality_score is not None:
            errors.append(f"{prefix} absent source candidate cannot expose data quality")
        if "candidate_snapshot" in entry and not isinstance(entry.get("candidate_snapshot"), dict):
            errors.append(f"{prefix}.candidate_snapshot must be an object")

    if decision.get("source_rule_inputs_contract_version") != inputs.get("contract_version"):
        errors.append("production_decision source rule-input contract is inconsistent")
    if decision.get("source_rule_inputs_sha256") != ledger_hash:
        errors.append("production_decision source rule-input hash is inconsistent")
    if decision.get("source_rule_input_count") != len(rows):
        errors.append("production_decision source rule-input count is inconsistent")

    try:
        rebuilt = production_rule_model.build_production_decision(snapshot)
    except Exception as exc:  # pragma: no cover - defensive deployment boundary
        errors.append(f"production_decision deterministic V4 rebuild failed: {type(exc).__name__}")
        return
    rebuilt_rows = rebuilt.get("evaluated_candidates") if isinstance(rebuilt, dict) else []
    qualified_identities = {
        (str(row.get("market") or ""), str(row.get("code") or ""))
        for row in rebuilt_rows
        if isinstance(row, dict) and row.get("status") == "QUALIFIED"
    }
    for index, entry in enumerate(rows):
        if not isinstance(entry, dict):
            continue
        identity = (str(entry.get("market") or ""), str(entry.get("code") or ""))
        has_snapshot = isinstance(entry.get("candidate_snapshot"), dict)
        if identity in qualified_identities and not has_snapshot:
            errors.append(f"production_rule_inputs.rows[{index}] qualified row requires candidate_snapshot")
        if identity not in qualified_identities and "candidate_snapshot" in entry:
            errors.append(f"production_rule_inputs.rows[{index}] rejected row must not retain candidate_snapshot")
    if rebuilt != decision:
        errors.append("production_decision does not match deterministic current V4 rebuild")


def _append_evidence_loop_errors(snapshot: dict, errors: list[str]) -> None:
    if snapshot.get("model_version") not in EVIDENCE_LOOP_MODEL_VERSIONS:
        return
    automation = snapshot.get("automation") or {}
    if not isinstance(automation.get("run_id"), str) or not automation.get("run_id"):
        errors.append("evidence-loop automation.run_id is required")
    pipeline = ((snapshot.get("events") or {}).get("pipeline") or {})
    if pipeline.get("contract_version") != "official-event-pipeline-v1":
        errors.append("evidence-loop official event pipeline contract is required")
    if pipeline.get("run_id") != automation.get("run_id"):
        errors.append("event pipeline run_id must match automation.run_id")
    if pipeline.get("status") not in {"READY", "READY_EMPTY", "PARTIAL"}:
        errors.append("event pipeline status is invalid")
    scanned_symbols = pipeline.get("scanned_symbols")
    if not isinstance(scanned_symbols, dict) or set(scanned_symbols) != set(MARKET_RECALL_TARGETS):
        errors.append("event pipeline scanned_symbols must cover three markets")

    universe = snapshot.get("point_in_time_universe")
    if not isinstance(universe, dict):
        errors.append("point_in_time_universe is required")
    else:
        if universe.get("contract_version") != "point-in-time-universe-v1":
            errors.append("point_in_time_universe.contract_version is invalid")
        if universe.get("generated_at") != snapshot.get("generated_at"):
            errors.append("point_in_time_universe.generated_at must match snapshot")
        markets = universe.get("markets")
        if not isinstance(markets, dict) or set(markets) != set(MARKET_RECALL_TARGETS):
            errors.append("point_in_time_universe.markets must cover three markets")
            markets = {}
        for market, target in MARKET_RECALL_TARGETS.items():
            section = markets.get(market) or {}
            members = section.get("members")
            if section.get("target_count") != target or section.get("member_count") != target:
                errors.append(f"point_in_time_universe.{market} must contain {target} members")
            if section.get("complete") is not True or not isinstance(members, list) or len(members) != target:
                errors.append(f"point_in_time_universe.{market}.members is incomplete")
                members = members if isinstance(members, list) else []
            codes = [str(item.get("code") or "") for item in members if isinstance(item, dict)]
            if len(codes) != len(set(codes)) or any(not code for code in codes):
                errors.append(f"point_in_time_universe.{market} member identities are invalid")
            if section.get("entry_trade_date") != (snapshot.get("next_trade_dates") or {}).get(market):
                errors.append(f"point_in_time_universe.{market}.entry_trade_date is inconsistent")
            if section.get("forecast_end_trade_date") != (snapshot.get("forecast_end_dates") or {}).get(market):
                errors.append(f"point_in_time_universe.{market}.forecast_end_trade_date is inconsistent")
        identity = {key: universe.get(key) for key in ("contract_version", "generated_at", "signal_date", "markets")}
        expected_hash = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if universe.get("sha256") != expected_hash:
            errors.append("point_in_time_universe.sha256 is inconsistent")

    feature_cutoff_raw = snapshot.get("feature_cutoff_at")
    if snapshot.get("model_version") == PRODUCTION_RULE_MODEL_VERSION and feature_cutoff_raw is None:
        errors.append("feature_cutoff_at is required for current V4")
    if feature_cutoff_raw is not None:
        feature_cutoff = parse_aware_datetime(feature_cutoff_raw)
        generated_moment = parse_aware_datetime(snapshot.get("generated_at"))
        try:
            expected_windows = market_trade_windows(
                snapshot.get("generated_at") or snapshot.get("target_date"),
                horizon_sessions=10,
            )
        except (TypeError, ValueError):
            expected_windows = {}
        if feature_cutoff is None:
            errors.append("feature_cutoff_at must be a timezone-aware timestamp")
        elif generated_moment is None or feature_cutoff < generated_moment:
            errors.append("feature_cutoff_at cannot precede generated_at")
        else:
            universe_markets = ((snapshot.get("point_in_time_universe") or {}).get("markets") or {})
            for market in ("a_share", "hk", "us"):
                members = (universe_markets.get(market) or {}).get("members") or []
                for index, member in enumerate(members):
                    if not isinstance(member, dict):
                        continue
                    observed_at = parse_aware_datetime(member.get("observed_at"))
                    if observed_at is None:
                        errors.append(
                            f"point_in_time_universe.{market}.members[{index}].observed_at is invalid"
                        )
                    elif observed_at > feature_cutoff:
                        errors.append(
                            f"point_in_time_universe.{market}.members[{index}] was observed after feature_cutoff_at"
                        )
                entry_open = _exchange_calendar_datetime(
                    (expected_windows.get(market) or {}).get("entry_session_open_at")
                )
                if entry_open is not None and feature_cutoff >= entry_open:
                    errors.append(f"feature_cutoff_at must precede {market} entry-session open")

    rank_model = ((snapshot.get("analysis_models") or {}).get("ten_day_excess_rank") or {})
    if rank_model.get("model_id") != TEN_DAY_RANK_MODEL_ID:
        errors.append("analysis_models.ten_day_excess_rank.model_id is invalid")
    if rank_model.get("label_version") != TEN_DAY_RANK_LABEL_VERSION:
        errors.append("analysis_models.ten_day_excess_rank.label_version is invalid")
    if rank_model.get("feature_schema_version") != "point-in-time-technical-d1-v2":
        errors.append("analysis_models.ten_day_excess_rank feature schema is invalid")
    if rank_model.get("training_provenance") != "point_in_time_universe_ledger":
        errors.append("analysis_models.ten_day_excess_rank training provenance is invalid")
    if rank_model.get("fixed_ridge_l2") != 1.0:
        errors.append("analysis_models.ten_day_excess_rank fixed ridge policy is invalid")
    rank_status = rank_model.get("status")
    if rank_status not in TEN_DAY_RANK_STATUSES:
        errors.append("analysis_models.ten_day_excess_rank status is invalid")
    if rank_model.get("benchmark_registry") != TEN_DAY_RANK_BENCHMARKS:
        errors.append("analysis_models.ten_day_excess_rank benchmark registry is invalid")
    if rank_model.get("target") != "ten_session_net_excess_return":
        errors.append("analysis_models.ten_day_excess_rank target is invalid")
    for field in ("calibrated", "participates_in_decision", "production_eligible"):
        if rank_model.get(field) is not False:
            errors.append(f"analysis_models.ten_day_excess_rank.{field} must remain false")
    for field in ("sample_count", "signal_date_count", "fold_count"):
        if not isinstance(rank_model.get(field), int) or rank_model.get(field) < 0:
            errors.append(f"analysis_models.ten_day_excess_rank.{field} must be non-negative")
    if rank_model.get("probability") is not None:
        errors.append("analysis_models.ten_day_excess_rank probability must remain null")
    artifact_sha256 = rank_model.get("artifact_sha256")
    if not isinstance(artifact_sha256, str) or re.fullmatch(
        r"[a-f0-9]{64}", str(artifact_sha256 or "")
    ) is None:
        errors.append("analysis_models.ten_day_excess_rank artifact hash is invalid")
    else:
        artifact_contract = rank_model.get("artifact_contract_version")
        if artifact_contract not in (None, "ten-day-rank-artifact-v2"):
            errors.append("analysis_models.ten_day_excess_rank artifact contract is invalid")
        artifact_identity = {
            field: rank_model.get(field)
            for field in (
                "model_id",
                "label_version",
                "feature_schema_version",
                "training_provenance",
                "benchmark_registry",
                "fixed_ridge_l2",
                "sample_count",
                "signal_date_count",
                "fold_count",
                "validation",
            )
        }
        if artifact_contract == "ten-day-rank-artifact-v2":
            artifact_identity["artifact_contract_version"] = artifact_contract
            if rank_status == "SHADOW_READY":
                artifact_identity["out_of_fold_predictions"] = rank_model.get(
                    "out_of_fold_predictions"
                )
            artifact_identity["reason_codes"] = rank_model.get("reason_codes")
            if "collection_diagnostics" in rank_model:
                artifact_identity["collection_diagnostics"] = rank_model.get(
                    "collection_diagnostics"
                )
        elif rank_status != "COLLECTING" or "collection_diagnostics" in rank_model:
            errors.append("legacy ten-day rank artifact shape is not supported")
        try:
            expected_artifact = hashlib.sha256(
                json.dumps(
                    artifact_identity,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        except (TypeError, ValueError):
            errors.append("analysis_models.ten_day_excess_rank artifact payload is invalid")
        else:
            if artifact_sha256 != expected_artifact:
                errors.append("analysis_models.ten_day_excess_rank artifact hash is inconsistent")
    if rank_status == "COLLECTING":
        for field in ("costs_ready", "tail_risk_ready"):
            if rank_model.get(field) is not False:
                errors.append(f"analysis_models.ten_day_excess_rank.{field} must be false while collecting")
        if rank_model.get("shadow_predictions") != []:
            errors.append("analysis_models.ten_day_excess_rank cannot publish predictions while COLLECTING")
    elif rank_status == "SHADOW_READY":
        if rank_model.get("costs_ready") is not True or rank_model.get("tail_risk_ready") is not True:
            errors.append("analysis_models.ten_day_excess_rank SHADOW_READY requires cost and tail evidence")
        if not isinstance(rank_model.get("shadow_predictions"), list) or not rank_model.get("shadow_predictions"):
            errors.append("analysis_models.ten_day_excess_rank SHADOW_READY requires out-of-fold predictions")
        if rank_model.get("fold_count", 0) <= 0:
            errors.append("analysis_models.ten_day_excess_rank SHADOW_READY requires walk-forward folds")
        validation = rank_model.get("validation")
        if not isinstance(validation, dict):
            errors.append("analysis_models.ten_day_excess_rank SHADOW_READY validation is missing")
        else:
            if validation.get("actual_exit_purge") is not True:
                errors.append("analysis_models.ten_day_excess_rank must purge by actual exit")
            if validation.get("date_market_equal_weighting") is not True:
                errors.append("analysis_models.ten_day_excess_rank must use date-market weighting")
            if validation.get("final_untouched_holdout") is not True:
                errors.append("analysis_models.ten_day_excess_rank final holdout is missing")
            if not isinstance(validation.get("block_bootstrap_95pct"), dict):
                errors.append("analysis_models.ten_day_excess_rank block bootstrap is missing")
        if rank_model.get("promotion_authorized") is not False:
            errors.append("analysis_models.ten_day_excess_rank cannot self-authorize promotion")
        if rank_model.get("out_of_fold_predictions") != rank_model.get("shadow_predictions"):
            errors.append("analysis_models.ten_day_excess_rank prediction mirrors are inconsistent")

    rule_tracking = snapshot.get("rule_outcome_tracking")
    if rule_tracking is not None:
        if not isinstance(rule_tracking, dict):
            errors.append("rule_outcome_tracking must be an object")
        else:
            if rule_tracking.get("track") != "RULE_QUALIFICATION":
                errors.append("rule_outcome_tracking track is invalid")
            if rule_tracking.get("authorizes_production") is not False:
                errors.append("rule_outcome_tracking cannot authorize production")
            if rule_tracking.get("included_in_calibrated_probability_statistics") is not False:
                errors.append("rule_outcome_tracking cannot enter calibrated probability metrics")

    a_manifest = ((((snapshot.get("markets") or {}).get("a_share") or {}).get("stats") or {}).get("recall_manifest"))
    if not isinstance(a_manifest, list) or len(a_manifest) != MARKET_RECALL_TARGETS["a_share"]:
        errors.append("markets.a_share.stats.recall_manifest must contain 300 rows")
    elif len({str(item.get("symbol") or "") for item in a_manifest if isinstance(item, dict)}) != len(a_manifest):
        errors.append("markets.a_share.stats.recall_manifest symbols must be unique")


def ten_day_shadow_quality_ready(validation: dict) -> bool:
    required = (
        "independent_test_date_count",
        "brier_skill",
        "auc",
        "ece_10bin",
        "top_decile_excess_vs_mean",
        "top_decile_mean_net_return",
    )
    if not isinstance(validation, dict) or not all(finite_number(validation.get(field)) for field in required):
        return False
    return bool(
        int(validation["independent_test_date_count"])
        >= TEN_DAY_SHADOW_QUALITY_GATE["minimum_independent_test_dates"]
        and validation["brier_skill"] >= TEN_DAY_SHADOW_QUALITY_GATE["minimum_brier_skill"]
        and validation["auc"] >= TEN_DAY_SHADOW_QUALITY_GATE["minimum_auc"]
        and validation["ece_10bin"] <= TEN_DAY_SHADOW_QUALITY_GATE["maximum_ece_10bin"]
        and validation["top_decile_excess_vs_mean"]
        >= TEN_DAY_SHADOW_QUALITY_GATE["minimum_top_decile_excess_vs_mean"]
        and validation["top_decile_mean_net_return"]
        > TEN_DAY_SHADOW_QUALITY_GATE["minimum_top_decile_mean_net_return"]
    )


def _append_ten_day_shadow_errors(model: dict, errors: list[str]) -> None:
    """Validate Shadow evidence without ever treating it as production-ready."""

    status = str(model.get("status") or "").upper()
    if status not in TEN_DAY_SHADOW_STATUSES:
        errors.append("ten-day Shadow status is invalid")
    if model.get("model_id") != TEN_DAY_SHADOW_MODEL_ID:
        errors.append("ten-day Shadow model_id is invalid")
    if model.get("label_version") != TEN_DAY_SHADOW_LABEL_VERSION:
        errors.append("ten-day Shadow label_version is invalid")
    if model.get("feature_schema_version") != TEN_DAY_SHADOW_FEATURE_SCHEMA:
        errors.append("ten-day Shadow feature_schema_version is invalid")
    if model.get("training_provenance") != TEN_DAY_SHADOW_PROVENANCE:
        errors.append("ten-day Shadow training_provenance is invalid")
    if model.get("calibrated") is not False:
        errors.append("ten-day Shadow calibrated must remain false")
    if model.get("participates_in_decision") is not False:
        errors.append("ten-day Shadow must not participate in the decision")
    if model.get("production_eligible") is not False:
        errors.append("ten-day Shadow production_eligible must remain false")
    if model.get("probability") is not None:
        errors.append("ten-day Shadow top-level probability must be null")
    if status != "UNAVAILABLE" and model.get("quality_gate") != TEN_DAY_SHADOW_QUALITY_GATE:
        errors.append("ten-day Shadow quality_gate does not match the registered policy")
    if status in {"SHADOW_READY", "SHADOW_REJECTED"}:
        training_cutoff = model.get("training_cutoff")
        try:
            dt.date.fromisoformat(str(training_cutoff))
        except ValueError:
            errors.append("ten-day Shadow training_cutoff must be an ISO date")
        artifact_sha256 = model.get("artifact_sha256")
        if not isinstance(artifact_sha256, str) or re.fullmatch(r"[a-f0-9]{64}", artifact_sha256.lower()) is None:
            errors.append("ten-day Shadow artifact_sha256 is invalid")
    for list_field in ("reason_codes", "limitations"):
        values = model.get(list_field)
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            errors.append(f"ten-day Shadow {list_field} must be a string list")

    predictions = model.get("shadow_predictions")
    if not isinstance(predictions, list):
        errors.append("ten-day Shadow predictions must be a list")
        predictions = []
    prediction_count = model.get("shadow_prediction_count", model.get("prediction_count"))
    if prediction_count is not None and (
        not isinstance(prediction_count, int)
        or isinstance(prediction_count, bool)
        or prediction_count != len(predictions)
    ):
        errors.append("ten-day Shadow prediction count is inconsistent")

    seen_predictions: set[tuple[str, str]] = set()
    for index, prediction_row in enumerate(predictions):
        prefix = f"ten-day Shadow prediction[{index}]"
        if not isinstance(prediction_row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        market = prediction_row.get("market")
        code = str(prediction_row.get("code") or prediction_row.get("symbol") or "")
        if market not in MARKET_RECALL_TARGETS or not code:
            errors.append(f"{prefix} identity is invalid")
        elif (market, code) in seen_predictions:
            errors.append(f"{prefix} identity is duplicated")
        else:
            seen_predictions.add((market, code))
        if prediction_row.get("model_id", model.get("model_id")) != model.get("model_id"):
            errors.append(f"{prefix} model_id must match ten_day_return.model_id")
        if prediction_row.get("label_version", model.get("label_version")) != model.get("label_version"):
            errors.append(f"{prefix} label_version must match ten_day_return.label_version")
        probability_value = prediction_row.get("probability")
        if not probability(probability_value):
            errors.append(f"{prefix} probability must be between 0 and 1")
        for field in ("expected_net_return", "expected_net_utility"):
            if not finite_number(prediction_row.get(field)):
                errors.append(f"{prefix} {field} must be finite")
        for field in ("transaction_cost", "tail_risk"):
            value = prediction_row.get(field)
            if not finite_number(value) or value < 0:
                errors.append(f"{prefix} {field} must be a non-negative finite number")
        expected_cost = {"a_share": 0.0015, "hk": 0.0030, "us": 0.0015}.get(market)
        if expected_cost is not None and finite_number(prediction_row.get("transaction_cost")):
            if not math.isclose(
                float(prediction_row["transaction_cost"]),
                expected_cost,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                errors.append(f"{prefix} transaction_cost is inconsistent with market policy")
        expected_return = prediction_row.get("expected_net_return")
        tail_risk = prediction_row.get("tail_risk")
        utility = prediction_row.get("expected_net_utility")
        if all(finite_number(value) for value in (expected_return, tail_risk, utility)):
            expected_utility = float(expected_return) - 0.25 * float(tail_risk)
            if not math.isclose(float(utility), expected_utility, rel_tol=0.0, abs_tol=1e-6):
                errors.append(f"{prefix} expected_net_utility is inconsistent")
        if prediction_row.get("participates_in_decision") is True:
            errors.append(f"{prefix} must not participate in the decision")
        if prediction_row.get("production_eligible") is True:
            errors.append(f"{prefix} must not be production eligible")
        market_model = (
            (model.get("market_models") or {}).get(market)
            if isinstance(model.get("market_models"), dict)
            else None
        )
        if isinstance(market_model, dict):
            expected_market_status = str(market_model.get("status") or "").upper()
            if prediction_row.get("market_validation_status") != expected_market_status:
                errors.append(f"{prefix} market_validation_status must match its market model")
            for field in ("artifact_sha256", "training_cutoff", "fit_data_cutoff"):
                expected = market_model.get(field)
                if expected is not None and prediction_row.get(field) != expected:
                    errors.append(f"{prefix} {field} must match its market model")

    validation = model.get("validation")
    if status in {"SHADOW_READY", "SHADOW_REJECTED"}:
        if not isinstance(validation, dict) or not validation:
            errors.append("ten-day Shadow held-out validation is required")
        else:
            date_count = next(
                (
                    validation.get(field)
                    for field in (
                        "independent_test_date_count",
                        "independent_test_dates",
                        "test_date_count",
                        "held_out_days",
                    )
                    if field in validation
                ),
                None,
            )
            if not isinstance(date_count, int) or isinstance(date_count, bool) or date_count <= 0:
                errors.append("ten-day Shadow independent test date count is invalid")
            for field in ("brier_score", "ece_10bin"):
                if not probability(validation.get(field)):
                    errors.append(f"ten-day Shadow validation.{field} must be between 0 and 1")
            auc_value = validation.get("auc")
            if auc_value is not None and not probability(auc_value):
                errors.append("ten-day Shadow validation.auc must be between 0 and 1 or null")

    market_models = model.get("market_models")
    if not isinstance(market_models, dict):
        errors.append("ten-day Shadow market_models must be an object")
    elif any(key not in MARKET_RECALL_TARGETS for key in market_models):
        errors.append("ten-day Shadow market_models contains an invalid market")
    elif status != "UNAVAILABLE":
        if set(market_models) != set(MARKET_RECALL_TARGETS):
            errors.append("ten-day Shadow market_models must cover three markets")
        else:
            market_statuses = []
            for market, market_model in market_models.items():
                if not isinstance(market_model, dict):
                    errors.append(f"ten-day Shadow market_models.{market} must be an object")
                    continue
                market_status = str(market_model.get("status") or "").upper()
                market_statuses.append(market_status)
                if market_status not in {"SHADOW_READY", "SHADOW_REJECTED", "INSUFFICIENT_DATA"}:
                    errors.append(f"ten-day Shadow market_models.{market}.status is invalid")
                    continue
                if market_model.get("quality_gate") != TEN_DAY_SHADOW_QUALITY_GATE:
                    errors.append(f"ten-day Shadow market_models.{market}.quality_gate is invalid")
                market_validation = market_model.get("validation")
                quality_ready = ten_day_shadow_quality_ready(market_validation)
                if market_status == "SHADOW_READY" and not quality_ready:
                    errors.append(f"ten-day Shadow market_models.{market} READY gate is not met")
                if market_status == "SHADOW_REJECTED" and quality_ready:
                    errors.append(f"ten-day Shadow market_models.{market} rejection contradicts its metrics")
            expected_status = (
                "SHADOW_READY"
                if "SHADOW_READY" in market_statuses
                else "SHADOW_REJECTED"
                if "SHADOW_REJECTED" in market_statuses
                else "INSUFFICIENT_DATA"
            )
            if status != expected_status:
                errors.append("ten-day Shadow top-level status does not match market models")
    if status == "SHADOW_READY" and not predictions:
        errors.append("ten-day SHADOW_READY requires at least one prediction")


def _latest_completed_market_session(market: str, generated_at: object) -> dt.date | None:
    """Independently derive the latest regular session observable at publication."""

    if not isinstance(generated_at, str) or not generated_at:
        return None
    try:
        anchor = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if anchor.tzinfo is None or anchor.utcoffset() is None:
        return None
    try:
        quote_session = expected_quote_session(market, anchor)
        close_at = dt.datetime.fromisoformat(session_close_at(market, quote_session))
        if anchor >= close_at:
            return quote_session
        open_at = dt.datetime.fromisoformat(session_open_at(market, quote_session))
        return expected_quote_session(market, open_at - dt.timedelta(microseconds=1))
    except (KeyError, TypeError, ValueError):
        return None


def _append_ten_day_shadow_join_errors(
    model: dict,
    decision: dict,
    generated_at: object,
    errors: list[str],
) -> None:
    """Cross-check the exact Shadow values consumed by the browser and ledger."""

    predictions = model.get("shadow_predictions")
    if not isinstance(predictions, list):
        return
    prediction_index = {
        (str(row.get("market") or ""), str(row.get("code") or row.get("symbol") or "")): row
        for row in predictions
        if isinstance(row, dict)
    }
    evaluated = decision.get("evaluated_candidates")
    if not isinstance(evaluated, list):
        errors.append("global_decision.evaluated_candidates must be a list")
        return
    evaluated_index: dict[tuple[str, str], dict] = {}
    comparable_numbers = (
        "probability",
        "expected_net_return",
        "expected_net_utility",
        "transaction_cost",
        "tail_risk",
    )
    for index, row in enumerate(evaluated):
        prefix = f"global_decision.evaluated_candidates[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        identity = (str(row.get("market") or ""), str(row.get("code") or row.get("symbol") or ""))
        evaluated_index[identity] = row
        published_prediction = prediction_index.get(identity)
        nested = row.get("shadow_model")
        if published_prediction is not None and not isinstance(nested, dict):
            errors.append(f"{prefix}.shadow_model must join the published prediction")
            continue
        if not isinstance(nested, dict):
            continue
        if nested.get("status") != "SHADOW_ONLY":
            errors.append(f"{prefix}.shadow_model.status is invalid")
        if published_prediction is None:
            errors.append(f"{prefix}.shadow_model has no matching published prediction")
            continue
        for field in comparable_numbers:
            left = nested.get(field)
            right = published_prediction.get(field)
            if not (finite_number(left) and finite_number(right)):
                errors.append(f"{prefix}.shadow_model.{field} must be finite")
            elif not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-8):
                errors.append(f"{prefix}.shadow_model.{field} does not match the published prediction")
        for field, expected in (
            ("model_id", model.get("model_id")),
            ("label_version", model.get("label_version")),
            ("feature_schema_version", model.get("feature_schema_version")),
            ("training_provenance", model.get("training_provenance")),
        ):
            if nested.get(field) != expected:
                errors.append(f"{prefix}.shadow_model.{field} does not match ten_day_return")
        market_model = (model.get("market_models") or {}).get(identity[0]) or {}
        for field in (
            "artifact_sha256",
            "training_cutoff",
            "fit_data_cutoff",
            "validation_cutoff",
            "last_training_signal_date",
            "last_calibration_signal_date",
        ):
            expected = published_prediction.get(field)
            if expected is None:
                expected = market_model.get(field)
            if expected is None and field in {"artifact_sha256", "training_cutoff", "fit_data_cutoff"}:
                expected = model.get(field)
            if nested.get(field) != expected:
                errors.append(f"{prefix}.shadow_model.{field} does not match its market model")
        if not isinstance(nested.get("prediction_id"), str) or re.fullmatch(
            r"pred_[a-f0-9]{16,64}", nested.get("prediction_id") or ""
        ) is None:
            errors.append(f"{prefix}.shadow_model.prediction_id is invalid")
        for field in ("calibrated", "participates_in_decision", "production_eligible"):
            if nested.get(field) is not False:
                errors.append(f"{prefix}.shadow_model.{field} must be false")
        if not strict_boolean(nested.get("rank_eligible")):
            errors.append(f"{prefix}.shadow_model.rank_eligible must be a boolean")
        if nested.get("market_validation_status") != published_prediction.get("market_validation_status"):
            errors.append(f"{prefix}.shadow_model.market_validation_status does not match the published prediction")
        if nested.get("prediction_as_of") != published_prediction.get("prediction_as_of"):
            errors.append(f"{prefix}.shadow_model.prediction_as_of does not match the published prediction")
        if nested.get("rank_eligible") is True:
            market_model = (model.get("market_models") or {}).get(identity[0]) or {}
            if (
                str(model.get("status") or "").upper() != "SHADOW_READY"
                or str(market_model.get("status") or "").upper() != "SHADOW_READY"
                or str(nested.get("market_validation_status") or "").upper() != "SHADOW_READY"
                or not finite_number(nested.get("expected_net_utility"))
                or nested.get("expected_net_utility") <= 0
            ):
                errors.append(f"{prefix}.shadow_model.rank_eligible is inconsistent")
            prediction_as_of = nested.get("prediction_as_of")
            try:
                parsed_prediction_as_of = dt.date.fromisoformat(str(prediction_as_of))
            except ValueError:
                parsed_prediction_as_of = None
                errors.append(
                    f"{prefix}.shadow_model.prediction_as_of is required as an ISO date when rank_eligible=true"
                )
            expected_prediction_as_of = _latest_completed_market_session(identity[0], generated_at)
            if expected_prediction_as_of is None:
                errors.append(
                    f"{prefix}.shadow_model rank eligibility cannot be verified from generated_at"
                )
            elif (
                parsed_prediction_as_of is not None
                and parsed_prediction_as_of != expected_prediction_as_of
            ):
                errors.append(
                    f"{prefix}.shadow_model.prediction_as_of must equal latest completed "
                    f"{identity[0]} session {expected_prediction_as_of.isoformat()}"
                )
        if row.get("score_kind") == "RULE_PRIORITY":
            for field in ("probability", "expected_net_utility", "transaction_cost", "tail_risk"):
                if row.get(field) is not None:
                    errors.append(f"{prefix}.{field} must remain null for RULE_PRIORITY")

    research = decision.get("research_priority")
    if not isinstance(research, dict):
        return
    identity = (str(research.get("market") or ""), str(research.get("code") or research.get("symbol") or ""))
    evaluated_row = evaluated_index.get(identity)
    research_shadow = research.get("shadow_model")
    if isinstance(research_shadow, dict):
        if not isinstance(evaluated_row, dict) or research_shadow != evaluated_row.get("shadow_model"):
            errors.append("research_priority.shadow_model must match its evaluated candidate")
    candidate_snapshot = research.get("candidate_snapshot")
    if candidate_snapshot is not None:
        if not isinstance(candidate_snapshot, dict):
            errors.append("research_priority.candidate_snapshot must be an object")
        elif (
            str(candidate_snapshot.get("market_key") or "") != identity[0]
            or str(candidate_snapshot.get("code") or candidate_snapshot.get("symbol") or "") != identity[1]
        ):
            errors.append("research_priority.candidate_snapshot identity is invalid")
        elif isinstance(research_shadow, dict) and candidate_snapshot.get("shadow_model") != research_shadow:
            errors.append("research_priority.candidate_snapshot shadow_model is inconsistent")
    if research.get("research_sort_basis") == "SHADOW_EXPECTED_NET_UTILITY" and not (
        isinstance(research_shadow, dict) and research_shadow.get("rank_eligible") is True
    ):
        errors.append("research_priority Shadow sort basis requires rank-eligible evidence")


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


def parse_aware_datetime(value) -> dt.datetime | None:
    if not timezone_aware_iso_datetime(value):
        return None
    text = str(value).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    return dt.datetime.fromisoformat(text)


_XHKG_CALENDAR = xcals.get_calendar("XHKG")


def _exchange_calendar_datetime(value) -> dt.datetime | None:
    """Convert an exchange-calendars timestamp without treating NaT as time."""

    if value is None or str(value) == "NaT":
        return None
    try:
        parsed = value.to_pydatetime()
    except AttributeError:
        parsed = value
    if not isinstance(parsed, dt.datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _xhkg_exchange_clock(reference: dt.datetime) -> dict | None:
    """Return actual XHKG intervals and progress for one exchange clock.

    The schedule is read from exchange-calendars for the observed date, so a
    half-day session is not silently evaluated against a hard-coded 330-minute
    full day. Lunch is excluded from both elapsed and total trading seconds.
    """

    local_reference = reference.astimezone(DYNAMIC_MARKET_SOURCE_TIMEZONES["hk"])
    session_date = local_reference.date()
    session_label = session_date.isoformat()
    if not _XHKG_CALENDAR.is_session(session_label):
        return None
    phase = quote_session_phase("hk", reference)
    session_open = _exchange_calendar_datetime(_XHKG_CALENDAR.session_open(session_label))
    session_close = _exchange_calendar_datetime(_XHKG_CALENDAR.session_close(session_label))
    break_start = _exchange_calendar_datetime(_XHKG_CALENDAR.session_break_start(session_label))
    break_end = _exchange_calendar_datetime(_XHKG_CALENDAR.session_break_end(session_label))
    if session_open is None or session_close is None or session_close <= session_open:
        return None
    if break_start is not None and break_end is not None and session_open < break_start < break_end < session_close:
        intervals = ((session_open, break_start), (break_end, session_close))
    else:
        intervals = ((session_open, session_close),)
    total_seconds = sum((end - start).total_seconds() for start, end in intervals)
    if total_seconds <= 0:
        return None
    anchor = reference.astimezone(dt.timezone.utc)
    elapsed_seconds = sum(
        max(0.0, (min(anchor, end) - start).total_seconds())
        for start, end in intervals
        if anchor > start
    )
    progress = min(1.0, max(0.0, elapsed_seconds / total_seconds))
    freshness_reference = anchor
    if phase == "break":
        freshness_reference = _exchange_calendar_datetime(
            _XHKG_CALENDAR.previous_minute(anchor)
        )
        if freshness_reference is None:
            return None
    return {
        "session_date": session_date,
        "phase": phase,
        "session_open": session_open,
        "break_start": break_start,
        "break_end": break_end,
        "session_close": session_close,
        "total_seconds": total_seconds,
        "elapsed_seconds": elapsed_seconds,
        "progress": progress,
        "freshness_reference": freshness_reference,
    }


def _iso_in_hk(value: dt.datetime | None) -> str | None:
    return (
        value.astimezone(DYNAMIC_MARKET_SOURCE_TIMEZONES["hk"]).isoformat(timespec="seconds")
        if value is not None
        else None
    )


def _append_current_hk_liquidity_row_errors(row: dict, prefix: str, errors: list[str]) -> None:
    """Rebuild one current-policy HK liquidity admission from raw evidence."""

    metrics = row.get("recall_metrics")
    if not isinstance(metrics, dict):
        errors.append(f"{prefix}.recall_metrics is required by current HK recall policy")
        return
    if metrics.get("amount_currency") != "HKD":
        errors.append(f"{prefix}.recall_metrics.amount_currency must be HKD")
    if metrics.get("liquidity_policy_version") != HK_INTRADAY_LIQUIDITY_POLICY_VERSION:
        errors.append(f"{prefix}.recall_metrics.liquidity_policy_version is invalid")
    if metrics.get("liquidity_standard_amount_threshold") != HK_STANDARD_MIN_AMOUNT_HKD:
        errors.append(f"{prefix}.recall_metrics.liquidity_standard_amount_threshold is invalid")
    for field, expected in (
        ("market_cap_currency", "HKD"),
        ("market_cap_kind", "total"),
        ("market_cap_source_field", "f20"),
    ):
        if metrics.get(field) != expected:
            errors.append(f"{prefix}.recall_metrics.{field} must be {expected}")
    amount = metrics.get("amount")
    if not finite_number(amount) or amount < 0:
        errors.append(f"{prefix}.recall_metrics.amount is invalid")
        return
    admission = metrics.get("liquidity_admission")
    if amount >= HK_STANDARD_MIN_AMOUNT_HKD:
        if admission != "observed_amount":
            errors.append(f"{prefix} standard HK amount requires observed_amount admission")
        return

    observed_at = row.get("observed_at")
    reference = parse_aware_datetime(observed_at)
    source_timestamp = metrics.get("source_timestamp")
    source = None
    if finite_number(source_timestamp) and source_timestamp > 0:
        try:
            source = dt.datetime.fromtimestamp(source_timestamp, dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            source = None
    gate_clock = _xhkg_exchange_clock(reference) if reference is not None else None
    source_clock = _xhkg_exchange_clock(source) if source is not None else None
    expected_policy = {
        "liquidity_policy_version": HK_INTRADAY_LIQUIDITY_POLICY_VERSION,
        "liquidity_standard_amount_threshold": HK_STANDARD_MIN_AMOUNT_HKD,
        "liquidity_amount_threshold": HK_STANDARD_MIN_AMOUNT_HKD,
        "liquidity_session_progress": None,
        "liquidity_gate_progress": None,
        "liquidity_data_progress": None,
        "liquidity_gate_elapsed_minutes": None,
        "liquidity_data_elapsed_minutes": None,
        "liquidity_session_total_minutes": None,
        "liquidity_reference_at": observed_at,
        "liquidity_freshness_reference_at": None,
        "liquidity_source_effective_at": None,
        "liquidity_source_age_seconds": None,
        "liquidity_source_age_minutes": None,
        "liquidity_source_wall_age_minutes": None,
        "liquidity_source_phase": "unknown",
        "liquidity_gate_phase": "unknown",
        "liquidity_session_open_at": None,
        "liquidity_session_break_start_at": None,
        "liquidity_session_break_end_at": None,
        "liquidity_session_close_at": None,
        "liquidity_intraday_scaling_eligible": False,
    }
    if reference is not None and source is not None and gate_clock is not None:
        gate_progress = round(float(gate_clock["progress"]), 6)
        data_progress = (
            round(float(source_clock["progress"]), 6) if source_clock is not None else None
        )
        freshness_reference = gate_clock["freshness_reference"]
        source_freshness_reference = (
            source_clock["freshness_reference"]
            if source_clock is not None
            else source.astimezone(dt.timezone.utc)
        )
        age = freshness_reference - source_freshness_reference
        wall_age = reference.astimezone(dt.timezone.utc) - source.astimezone(dt.timezone.utc)
        threshold = max(
            HK_INTRADAY_MIN_AMOUNT_HKD,
            round(HK_STANDARD_MIN_AMOUNT_HKD * gate_progress),
        )
        source_local_date = source.astimezone(DYNAMIC_MARKET_SOURCE_TIMEZONES["hk"]).date()
        source_phase = str((source_clock or {}).get("phase") or "closed")
        policy_eligible = bool(
            gate_clock["phase"] in {"regular", "break"}
            and source_phase in {"pre", "regular", "break"}
            and expected_quote_session("hk", reference) == gate_clock["session_date"]
            and source_local_date == gate_clock["session_date"]
            and wall_age >= -DYNAMIC_DISCOVERY_MAX_SOURCE_FUTURE_SKEW
            and age >= -DYNAMIC_DISCOVERY_MAX_SOURCE_FUTURE_SKEW
            and age <= DYNAMIC_DISCOVERY_MAX_REGULAR_SOURCE_AGE
            and threshold < HK_STANDARD_MIN_AMOUNT_HKD
        )
        expected_policy.update(
            {
                "liquidity_amount_threshold": threshold,
                "liquidity_session_progress": gate_progress,
                "liquidity_gate_progress": gate_progress,
                "liquidity_data_progress": data_progress,
                "liquidity_gate_elapsed_minutes": round(gate_clock["elapsed_seconds"] / 60, 6),
                "liquidity_data_elapsed_minutes": (
                    round(source_clock["elapsed_seconds"] / 60, 6)
                    if source_clock is not None
                    else None
                ),
                "liquidity_session_total_minutes": round(gate_clock["total_seconds"] / 60, 6),
                "liquidity_freshness_reference_at": _iso_in_hk(freshness_reference),
                "liquidity_source_effective_at": _iso_in_hk(source_freshness_reference),
                "liquidity_source_age_seconds": round(age.total_seconds(), 6),
                "liquidity_source_age_minutes": round(age.total_seconds() / 60, 2),
                "liquidity_source_wall_age_minutes": round(wall_age.total_seconds() / 60, 2),
                "liquidity_source_phase": source_phase,
                "liquidity_gate_phase": gate_clock["phase"],
                "liquidity_session_open_at": _iso_in_hk(gate_clock["session_open"]),
                "liquidity_session_break_start_at": _iso_in_hk(gate_clock["break_start"]),
                "liquidity_session_break_end_at": _iso_in_hk(gate_clock["break_end"]),
                "liquidity_session_close_at": _iso_in_hk(gate_clock["session_close"]),
                "liquidity_intraday_scaling_eligible": policy_eligible,
            }
        )
    policy_eligible = expected_policy["liquidity_intraday_scaling_eligible"] is True
    expected_threshold = expected_policy["liquidity_amount_threshold"]
    eligible = bool(
        policy_eligible
        and amount >= HK_INTRADAY_MIN_AMOUNT_HKD
        and amount >= expected_threshold
        and finite_number(metrics.get("market_cap"))
        and metrics.get("market_cap") >= HK_INTRADAY_MIN_MARKET_CAP_HKD
    )

    data_progress = expected_policy["liquidity_data_progress"]
    source_phase = expected_policy["liquidity_source_phase"]
    projection_allowed = bool(
        policy_eligible
        and source_phase in {"regular", "break"}
        and finite_number(data_progress)
        and data_progress > 0
    )
    expected_policy["liquidity_projection_basis"] = (
        "source_trading_progress"
        if projection_allowed
        else "pre_no_linear_projection"
        if source_phase == "pre"
        else "unavailable"
    )
    expected_policy["projected_full_session_amount"] = (
        round(amount / data_progress, 2) if projection_allowed else None
    )
    for field, expected in expected_policy.items():
        if metrics.get(field) != expected:
            errors.append(f"{prefix}.recall_metrics.{field} does not match deterministic XHKG policy")
    if admission != "intraday_scaled":
        errors.append(f"{prefix} sub-standard HK amount requires intraday_scaled admission")
    if not eligible:
        errors.append(f"{prefix} is not eligible for intraday_scaled HK liquidity admission")
    routes = row.get("recall_routes")
    if not isinstance(routes, list) or "intraday_liquidity_completion" not in routes:
        errors.append(f"{prefix} intraday_scaled admission requires intraday_liquidity_completion route")


def dynamic_manifest_source_freshness(
    manifest: list[dict], market_key: str, anchor_value
) -> dict:
    anchor = parse_aware_datetime(anchor_value)
    if anchor is None:
        return {
            "time_count": 0,
            "fresh_count": 0,
            "expected_session": None,
            "freshness_reference_at": None,
            "source_effective_as_of": None,
        }
    expected_session = expected_quote_session(market_key, anchor)
    phase = quote_session_phase(market_key, anchor)
    gate_effective = anchor.astimezone(dt.timezone.utc)
    if market_key == "hk":
        gate_clock = _xhkg_exchange_clock(anchor)
        if gate_clock is not None:
            gate_effective = gate_clock["freshness_reference"]
    time_count = 0
    fresh_count = 0
    source_effective_timestamps: list[int] = []
    for row in manifest:
        if not isinstance(row, dict):
            continue
        timestamp = ((row.get("recall_metrics") or {}).get("source_timestamp"))
        if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool) or timestamp <= 0:
            continue
        time_count += 1
        try:
            source_moment = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        source_session = source_moment.astimezone(DYNAMIC_MARKET_SOURCE_TIMEZONES[market_key]).date()
        source_effective = source_moment
        source_phase_fresh = True
        if market_key == "hk":
            source_clock = _xhkg_exchange_clock(source_moment)
            if source_clock is not None:
                source_effective = source_clock["freshness_reference"]
                if phase in {"regular", "break"}:
                    source_phase_fresh = source_clock["phase"] in {"pre", "regular", "break"}
        source_effective_timestamps.append(int(source_effective.timestamp()))
        age = gate_effective - source_effective
        wall_age = anchor.astimezone(dt.timezone.utc) - source_moment
        clock_fresh = bool(
            source_phase_fresh
            and wall_age >= -DYNAMIC_DISCOVERY_MAX_SOURCE_FUTURE_SKEW
            and age >= -DYNAMIC_DISCOVERY_MAX_SOURCE_FUTURE_SKEW
        )
        if phase in {"regular", "break"}:
            clock_fresh = clock_fresh and age <= DYNAMIC_DISCOVERY_MAX_REGULAR_SOURCE_AGE
        if source_session == expected_session and clock_fresh:
            fresh_count += 1
    return {
        "time_count": time_count,
        "fresh_count": fresh_count,
        "expected_session": expected_session.isoformat(),
        "phase": phase,
        "freshness_reference_at": gate_effective.astimezone(
            DYNAMIC_MARKET_SOURCE_TIMEZONES[market_key]
        ).isoformat(timespec="seconds"),
        "source_effective_as_of": (
            dt.datetime.fromtimestamp(max(source_effective_timestamps), dt.timezone.utc)
            .astimezone(DYNAMIC_MARKET_REPORT_TIMEZONE)
            .isoformat(timespec="seconds")
            if source_effective_timestamps
            else None
        ),
    }


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
    production_decision = snapshot.get("production_decision")
    if isinstance(production_decision, dict):
        production_rows = [production_decision.get("primary")]
        qualified_candidates = production_decision.get("qualified_candidates")
        if isinstance(qualified_candidates, list):
            production_rows.extend(qualified_candidates)
        for candidate in production_rows:
            if isinstance(candidate, dict) and candidate.get("market") == market_key:
                rows.append(candidate.get("candidate_snapshot") or candidate)

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


def derive_market_coverage_state(section: dict, market_key: str | None = None) -> tuple[str, list[str]]:
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
    realtime_coverage = quote_health.get("realtime_coverage", quote_coverage)
    quote_ready = (
        str(quote_health.get("status") or "").lower() == "available"
        and finite_number(quote_coverage)
        and quote_coverage >= 0.98
        and finite_number(realtime_coverage)
        and realtime_coverage >= 0.98
        and isinstance(quote_health.get("requested_count"), int)
        and quote_health.get("requested_count") > 0
    )
    reasons: list[str] = []
    if pool_degraded:
        reasons.append("POOL_COVERAGE_INCOMPLETE")
    market_key = str(market_key or section.get("key") or "")
    expected_origin = "dynamic_snapshot" if market_key == "a_share" else DYNAMIC_MARKET_ORIGIN
    if origin in {"curated_static", "curated_fallback"}:
        reasons.append("CURATED_STATIC_UNIVERSE")
    elif origin == DYNAMIC_MARKET_CACHE_ORIGIN:
        reasons.append("DYNAMIC_DISCOVERY_CACHE_USED")
    elif origin != expected_origin:
        reasons.append("DYNAMIC_RECALL_CONTRACT_INCOMPLETE")
    if market_key in {"hk", "us"} and origin == DYNAMIC_MARKET_ORIGIN and not pool:
        pool_degraded = True
        reasons.append("DYNAMIC_RECALL_CONTRACT_INCOMPLETE")
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
            if ten_day_model.get("model_id") == TEN_DAY_SHADOW_MODEL_ID:
                _append_ten_day_shadow_errors(ten_day_model, errors)

    markets = snapshot.get("markets") or {}
    derived_market_states: dict[str, tuple[str, list[str]]] = {}
    for market_key in ("a_share", "hk", "us"):
        if market_key not in markets:
            errors.append(f"markets.{market_key} is missing")
            continue
        section = markets[market_key] or {}
        derived_market_states[market_key] = derive_market_coverage_state(section, market_key)
        stats = section.get("stats") if isinstance(section.get("stats"), dict) else {}
        expanded_recall_contract = snapshot.get("universe_version") in FULL_A_SHARE_SCORE_UNIVERSE_VERSIONS
        origin_declares_dynamic = stats.get("universe_origin") in {
            DYNAMIC_MARKET_ORIGIN,
            DYNAMIC_MARKET_CACHE_ORIGIN,
        }
        dynamic_market_contract = market_key in {"hk", "us"} and (
            snapshot.get("universe_version") == DYNAMIC_HK_US_UNIVERSE_VERSION
            or origin_declares_dynamic
        )
        if origin_declares_dynamic and snapshot.get("universe_version") != DYNAMIC_HK_US_UNIVERSE_VERSION:
            errors.append(
                f"markets.{market_key}.stats dynamic origin requires universe_version "
                f"{DYNAMIC_HK_US_UNIVERSE_VERSION}"
            )
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
                for field in ("deep_score_limit", "deep_attempted_size", "deep_kline_coverage"):
                    if field not in stats:
                        errors.append(f"markets.a_share.stats.{field} is required")
                if expanded_recall_contract:
                    for field in (
                        "base_scored_size",
                        "technical_attempted_size",
                        "technical_scored_size",
                        "technical_kline_complete_size",
                        "technical_kline_coverage",
                        "deep_eligible_size",
                    ):
                        if field not in stats:
                            errors.append(f"markets.a_share.stats.{field} is required")
                deep_score_limit = stats.get("deep_score_limit")
                deep_attempted_size = stats.get("deep_attempted_size")
                deep_kline_coverage = stats.get("deep_kline_coverage")
                deep_limit_bound = deep_score_limit if isinstance(deep_score_limit, int) and not isinstance(deep_score_limit, bool) else 0
                compatible_deep_limits = (
                    {A_SHARE_DEEP_SCORE_LIMIT}
                    if snapshot.get("model_version") == PRODUCTION_RULE_MODEL_VERSION
                    else {96, A_SHARE_DEEP_SCORE_LIMIT}
                )
                if deep_score_limit not in compatible_deep_limits:
                    expected_limits = "/".join(str(value) for value in sorted(compatible_deep_limits))
                    errors.append(f"markets.a_share.stats.deep_score_limit must be {expected_limits}")
                technical_scored_size = stats.get("technical_scored_size")
                technical_kline_complete_size = stats.get("technical_kline_complete_size")
                deep_eligible_size = stats.get("deep_eligible_size")
                expected_deep_attempted = (
                    min(deep_limit_bound, deep_eligible_size)
                    if expanded_recall_contract
                    and isinstance(deep_eligible_size, int)
                    and not isinstance(deep_eligible_size, bool)
                    else None
                )
                deep_attempted_invalid = (
                    not isinstance(deep_attempted_size, int)
                    or isinstance(deep_attempted_size, bool)
                    or deep_attempted_size < 0
                    or (
                        expected_deep_attempted is not None
                        and deep_attempted_size != expected_deep_attempted
                    )
                    or (
                        expected_deep_attempted is None
                        and isinstance(valid_quote_size, int)
                        and deep_attempted_size > min(deep_limit_bound, valid_quote_size)
                    )
                )
                if deep_attempted_invalid:
                    errors.append("markets.a_share.stats.deep_attempted_size is invalid")
                if isinstance(deep_attempted_size, int) and isinstance(deep_scored_size, int) and deep_scored_size > deep_attempted_size:
                    errors.append("markets.a_share.stats.deep_scored_size exceeds attempted size")
                expected_deep_coverage = (
                    round(deep_scored_size / deep_attempted_size, 4)
                    if isinstance(deep_attempted_size, int) and deep_attempted_size > 0 and isinstance(deep_scored_size, int)
                    else 0.0
                )
                if not finite_number(deep_kline_coverage) or deep_kline_coverage != expected_deep_coverage:
                    errors.append("markets.a_share.stats.deep_kline_coverage is inconsistent")
                if expanded_recall_contract:
                    base_scored_size = stats.get("base_scored_size")
                    technical_attempted_size = stats.get("technical_attempted_size")
                    technical_kline_coverage = stats.get("technical_kline_coverage")
                    if (
                        not isinstance(base_scored_size, int)
                        or isinstance(base_scored_size, bool)
                        or base_scored_size != valid_quote_size
                    ):
                        errors.append("markets.a_share.stats.base_scored_size must equal valid quote size")
                    if (
                        not isinstance(technical_attempted_size, int)
                        or isinstance(technical_attempted_size, bool)
                        or technical_attempted_size != base_scored_size
                    ):
                        errors.append("markets.a_share.stats.technical_attempted_size must equal base scored size")
                    if (
                        not isinstance(technical_scored_size, int)
                        or isinstance(technical_scored_size, bool)
                        or technical_scored_size != technical_attempted_size
                    ):
                        errors.append("markets.a_share.stats.technical_scored_size is invalid")
                    if (
                        not isinstance(technical_kline_complete_size, int)
                        or isinstance(technical_kline_complete_size, bool)
                        or technical_kline_complete_size < 0
                        or (
                            isinstance(technical_scored_size, int)
                            and technical_kline_complete_size > technical_scored_size
                        )
                    ):
                        errors.append("markets.a_share.stats.technical_kline_complete_size is invalid")
                    if (
                        not isinstance(deep_eligible_size, int)
                        or isinstance(deep_eligible_size, bool)
                        or deep_eligible_size < 0
                        or (
                            isinstance(technical_kline_complete_size, int)
                            and deep_eligible_size > technical_kline_complete_size
                        )
                    ):
                        errors.append("markets.a_share.stats.deep_eligible_size is invalid")
                    expected_technical_coverage = (
                        round(technical_kline_complete_size / technical_attempted_size, 4)
                        if isinstance(technical_attempted_size, int)
                        and technical_attempted_size > 0
                        and isinstance(technical_kline_complete_size, int)
                        else 0.0
                    )
                    if (
                        not finite_number(technical_kline_coverage)
                        or technical_kline_coverage != expected_technical_coverage
                    ):
                        errors.append("markets.a_share.stats.technical_kline_coverage is inconsistent")
                    if snapshot.get("model_version") == PRODUCTION_RULE_MODEL_VERSION:
                        pool_health = section.get("pool_health")
                        if not isinstance(pool_health, dict):
                            errors.append("markets.a_share.pool_health is required")
                        elif (
                            pool_health.get("contract_version")
                            == A_SHARE_POOL_HEALTH_CONTRACT_VERSION
                        ):
                            required_health_fields = {
                                "contract_version",
                                "status",
                                "reason_codes",
                                "technical_attempted_count",
                                "technical_completed_count",
                                "technical_score_coverage",
                                "min_technical_score_coverage",
                                "deep_eligible_count",
                                "deep_eligibility_target_count",
                                "deep_eligibility_coverage",
                                "min_deep_eligibility_coverage",
                                "deep_attempted_count",
                                "expected_deep_attempted_count",
                                "deep_completed_count",
                                "deep_score_coverage",
                                "min_deep_score_coverage",
                                "deep_score_limit",
                            }
                            missing_health_fields = sorted(required_health_fields - set(pool_health))
                            if missing_health_fields:
                                errors.append(
                                    "markets.a_share.pool_health fields missing: "
                                    + ",".join(missing_health_fields)
                                )

                            health_inputs_valid = all(
                                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                                for value in (
                                    deep_limit_bound,
                                    technical_attempted_size,
                                    technical_kline_complete_size,
                                    deep_eligible_size,
                                    deep_attempted_size,
                                    deep_scored_size,
                                )
                            )
                            if health_inputs_valid:
                                deep_eligibility_target = min(
                                    deep_limit_bound, technical_kline_complete_size
                                )
                                deep_eligibility_coverage = (
                                    round(deep_eligible_size / deep_eligibility_target, 4)
                                    if deep_eligibility_target
                                    else 0.0
                                )
                                expected_attempted = min(deep_limit_bound, deep_eligible_size)
                                expected_health_fields = {
                                    "contract_version": A_SHARE_POOL_HEALTH_CONTRACT_VERSION,
                                    "technical_attempted_count": technical_attempted_size,
                                    "technical_completed_count": technical_kline_complete_size,
                                    "technical_score_coverage": expected_technical_coverage,
                                    "min_technical_score_coverage": A_SHARE_MIN_TECHNICAL_SCORE_COVERAGE,
                                    "deep_eligible_count": deep_eligible_size,
                                    "deep_eligibility_target_count": deep_eligibility_target,
                                    "deep_eligibility_coverage": deep_eligibility_coverage,
                                    "min_deep_eligibility_coverage": A_SHARE_MIN_DEEP_SCORE_COVERAGE,
                                    "deep_attempted_count": deep_attempted_size,
                                    "expected_deep_attempted_count": expected_attempted,
                                    "deep_completed_count": deep_scored_size,
                                    "deep_score_coverage": expected_deep_coverage,
                                    "min_deep_score_coverage": A_SHARE_MIN_DEEP_SCORE_COVERAGE,
                                    "deep_score_limit": deep_limit_bound,
                                }
                                if any(
                                    pool_health.get(field) != expected
                                    for field, expected in expected_health_fields.items()
                                ):
                                    errors.append(
                                        "markets.a_share.pool_health score funnel is inconsistent"
                                    )

                                published_reasons = pool_health.get("reason_codes")
                                if not isinstance(published_reasons, list) or not all(
                                    isinstance(reason, str) and reason
                                    for reason in published_reasons
                                ):
                                    errors.append("markets.a_share.pool_health.reason_codes is invalid")
                                else:
                                    reason_set = set(published_reasons)
                                    technical_degraded = bool(
                                        technical_attempted_size == 0
                                        or expected_technical_coverage
                                        < A_SHARE_MIN_TECHNICAL_SCORE_COVERAGE
                                    )
                                    deep_degraded = bool(
                                        deep_eligibility_target == 0
                                        or deep_eligibility_coverage
                                        < A_SHARE_MIN_DEEP_SCORE_COVERAGE
                                        or deep_attempted_size != expected_attempted
                                        or deep_attempted_size == 0
                                        or expected_deep_coverage
                                        < A_SHARE_MIN_DEEP_SCORE_COVERAGE
                                    )
                                    if technical_degraded != (
                                        "A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM"
                                        in reason_set
                                    ):
                                        errors.append(
                                            "markets.a_share.pool_health technical reason is inconsistent"
                                        )
                                    if deep_degraded != (
                                        "A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM"
                                        in reason_set
                                    ):
                                        errors.append(
                                            "markets.a_share.pool_health deep reason is inconsistent"
                                        )
                                    expected_health_status = (
                                        "degraded" if published_reasons else "healthy"
                                    )
                                    if pool_health.get("status") != expected_health_status:
                                        errors.append(
                                            "markets.a_share.pool_health.status is inconsistent"
                                        )
                        elif pool_health.get("contract_version") is not None:
                            errors.append(
                                "markets.a_share.pool_health.contract_version is invalid"
                            )
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
            elif expanded_recall_contract:
                quote_health = section.get("quote_health") if isinstance(section.get("quote_health"), dict) else {}
                requested_count = quote_health.get("requested_count")
                realtime_count = quote_health.get("realtime_count")
                stale_count = quote_health.get("stale_realtime_count")
                realtime_coverage = quote_health.get("realtime_coverage")
                if quote_health.get("freshness_policy") != YAHOO_QUOTE_FRESHNESS_POLICY:
                    errors.append(f"markets.{market_key}.quote_health.freshness_policy is invalid")
                try:
                    expected_reference = expected_quote_session(market_key, window_anchor).isoformat()
                except (TypeError, ValueError):
                    expected_reference = None
                if quote_health.get("freshness_reference_session") != expected_reference:
                    errors.append(f"markets.{market_key}.quote_health.freshness_reference_session is invalid")
                if (
                    not isinstance(realtime_count, int)
                    or isinstance(realtime_count, bool)
                    or not isinstance(stale_count, int)
                    or isinstance(stale_count, bool)
                    or realtime_count < 0
                    or stale_count < 0
                    or not isinstance(requested_count, int)
                    or realtime_count + stale_count > requested_count
                ):
                    errors.append(f"markets.{market_key}.quote_health freshness counts are invalid")
                expected_realtime_coverage = (
                    round(realtime_count / requested_count, 4)
                    if isinstance(requested_count, int) and requested_count > 0 and isinstance(realtime_count, int)
                    else 0.0
                )
                if not finite_number(realtime_coverage) or realtime_coverage != expected_realtime_coverage:
                    errors.append(f"markets.{market_key}.quote_health.realtime_coverage is inconsistent")
            if dynamic_market_contract:
                dynamic_policy_version = stats.get("recall_policy_version")
                required_dynamic_fields = {
                    "universe_origin",
                    "universe_scope",
                    "coverage_claim",
                    "recall_policy_version",
                    "discovery_source",
                    "discovery_retrieved_at",
                    "discovery_source_as_of",
                    "discovery_pagination_complete",
                    "discovery_reported_total",
                    "discovery_freshness_as_of",
                    "discovery_expected_session",
                    "discovery_session_phase",
                    "selected_source_time_count",
                    "selected_source_time_coverage",
                    "selected_source_fresh_count",
                    "selected_source_fresh_coverage",
                    "selected_source_stale_symbols",
                    "raw_discovery_size",
                    "deduped_discovery_size",
                    "eligible_discovery_size",
                    "min_eligible_discovery_size",
                    "route_targets",
                    "route_counts",
                    "route_hit_counts",
                    "route_shortfalls",
                    "excluded_counts",
                    "recall_manifest",
                }
                if dynamic_policy_version == DYNAMIC_MARKET_RECALL_POLICY_VERSION:
                    required_dynamic_fields.update(
                        {
                            "discovery_freshness_reference_at",
                            "discovery_source_effective_as_of",
                        }
                    )
                missing_dynamic = sorted(required_dynamic_fields - set(stats))
                if missing_dynamic:
                    errors.append(
                        f"markets.{market_key}.stats dynamic recall fields missing: "
                        + ",".join(missing_dynamic)
                    )
                origin = stats.get("universe_origin")
                if origin not in {DYNAMIC_MARKET_ORIGIN, DYNAMIC_MARKET_CACHE_ORIGIN}:
                    errors.append(f"markets.{market_key}.stats.universe_origin is not a dynamic origin")
                if stats.get("universe_scope") != "provider_bounded_common_equity_cross_section":
                    errors.append(f"markets.{market_key}.stats.universe_scope is invalid")
                if stats.get("coverage_claim") != "bounded_dynamic_scan":
                    errors.append(f"markets.{market_key}.stats.coverage_claim is invalid")
                model_version = snapshot.get("model_version")
                current_policy_required = model_version == PRODUCTION_RULE_MODEL_VERSION
                if current_policy_required:
                    if dynamic_policy_version != DYNAMIC_MARKET_RECALL_POLICY_VERSION:
                        errors.append(f"markets.{market_key}.stats.recall_policy_version is invalid")
                elif model_version in DYNAMIC_MARKET_MODEL_VERSIONS and dynamic_policy_version not in {
                    DYNAMIC_MARKET_RECALL_POLICY_VERSION,
                    *DYNAMIC_MARKET_LEGACY_RECALL_POLICY_VERSIONS,
                }:
                    errors.append(f"markets.{market_key}.stats.recall_policy_version is invalid")
                elif model_version not in DYNAMIC_MARKET_MODEL_VERSIONS:
                    errors.append(f"markets.{market_key}.stats.recall_policy_version is invalid")
                audit_current_hk_liquidity = bool(
                    market_key == "hk"
                    and dynamic_policy_version == DYNAMIC_MARKET_RECALL_POLICY_VERSION
                )
                if not isinstance(stats.get("discovery_source"), str) or not stats.get("discovery_source", "").strip():
                    errors.append(f"markets.{market_key}.stats.discovery_source is invalid")
                retrieved_at = parse_aware_datetime(stats.get("discovery_retrieved_at"))
                generated_moment = parse_aware_datetime(window_anchor)
                if retrieved_at is None:
                    errors.append(f"markets.{market_key}.stats.discovery_retrieved_at is invalid")
                elif generated_moment is not None:
                    retrieval_age = generated_moment.astimezone(dt.timezone.utc) - retrieved_at.astimezone(dt.timezone.utc)
                    max_lag = (
                        dt.timedelta(days=14)
                        if stats.get("universe_origin") == DYNAMIC_MARKET_CACHE_ORIGIN
                        else DYNAMIC_DISCOVERY_MAX_GENERATION_LAG
                    )
                    if abs(retrieval_age) > max_lag:
                        errors.append(f"markets.{market_key}.stats.discovery_retrieved_at is stale or future")
                source_as_of = stats.get("discovery_source_as_of")
                if source_as_of is not None and not timezone_aware_iso_datetime(source_as_of):
                    errors.append(f"markets.{market_key}.stats.discovery_source_as_of is invalid")
                pagination_complete = stats.get("discovery_pagination_complete")
                if not strict_boolean(pagination_complete):
                    errors.append(f"markets.{market_key}.stats.discovery_pagination_complete is invalid")
                for field in ("discovery_requested_pages", "discovery_completed_pages"):
                    value = stats.get(field)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        errors.append(f"markets.{market_key}.stats.{field} is invalid")
                requested_pages = stats.get("discovery_requested_pages")
                completed_pages = stats.get("discovery_completed_pages")
                if (
                    isinstance(requested_pages, int)
                    and not isinstance(requested_pages, bool)
                    and isinstance(completed_pages, int)
                    and not isinstance(completed_pages, bool)
                    and (
                        completed_pages > requested_pages
                        or (pagination_complete is True and completed_pages != requested_pages)
                    )
                ):
                    errors.append(f"markets.{market_key}.stats discovery pagination is inconsistent")
                reported_total = stats.get("discovery_reported_total")
                if reported_total is not None and (
                    not isinstance(reported_total, int)
                    or isinstance(reported_total, bool)
                    or reported_total < 0
                ):
                    errors.append(f"markets.{market_key}.stats.discovery_reported_total is invalid")
                raw_discovery = stats.get("raw_discovery_size")
                deduped_discovery = stats.get("deduped_discovery_size")
                eligible_discovery = stats.get("eligible_discovery_size")
                minimum_discovery = stats.get("min_eligible_discovery_size")
                if minimum_discovery != DYNAMIC_MARKET_MIN_ELIGIBLE[market_key]:
                    errors.append(f"markets.{market_key}.stats.min_eligible_discovery_size is invalid")
                if (
                    not isinstance(raw_discovery, int)
                    or isinstance(raw_discovery, bool)
                    or not isinstance(deduped_discovery, int)
                    or isinstance(deduped_discovery, bool)
                    or not isinstance(eligible_discovery, int)
                    or isinstance(eligible_discovery, bool)
                    or not isinstance(selected_size, int)
                    or raw_discovery < deduped_discovery
                    or deduped_discovery < eligible_discovery
                    or eligible_discovery < selected_size
                ):
                    errors.append(f"markets.{market_key}.stats dynamic discovery counts are invalid")
                expected_routes = DYNAMIC_MARKET_ROUTE_TARGETS[market_key]
                route_targets = stats.get("route_targets")
                route_counts = stats.get("route_counts")
                route_hit_counts = stats.get("route_hit_counts")
                route_shortfalls = stats.get("route_shortfalls")
                if route_targets != expected_routes:
                    errors.append(f"markets.{market_key}.stats.route_targets is invalid")
                route_counts_valid = bool(
                    isinstance(route_counts, dict)
                    and set(route_counts) == set(expected_routes)
                    and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in route_counts.values())
                )
                if not route_counts_valid or sum(route_counts.values()) != selected_size:
                    errors.append(f"markets.{market_key}.stats.route_counts is invalid")
                if route_counts_valid:
                    expected_shortfalls = {
                        route: target - route_counts.get(route, 0)
                        for route, target in expected_routes.items()
                        if route_counts.get(route, 0) < target
                    }
                    if route_shortfalls != expected_shortfalls:
                        errors.append(f"markets.{market_key}.stats.route_shortfalls is inconsistent")
                route_hits_valid = bool(
                    isinstance(route_hit_counts, dict)
                    and set(route_hit_counts) == set(expected_routes)
                    and all(
                        isinstance(value, int)
                        and not isinstance(value, bool)
                        and value >= 0
                        and (not isinstance(selected_size, int) or value <= selected_size)
                        and (not route_counts_valid or value >= route_counts.get(route, 0))
                        for route, value in route_hit_counts.items()
                    )
                )
                if not route_hits_valid:
                    errors.append(f"markets.{market_key}.stats.route_hit_counts is invalid")
                excluded_counts = stats.get("excluded_counts")
                if not isinstance(excluded_counts, dict):
                    errors.append(f"markets.{market_key}.stats.excluded_counts is invalid")
                manifest = stats.get("recall_manifest")
                manifest_contract_valid = True
                manifest_symbol_set: set[str] = set()
                if not isinstance(manifest, list) or len(manifest) != selected_size:
                    errors.append(f"markets.{market_key}.stats.recall_manifest size is invalid")
                    manifest_contract_valid = False
                else:
                    manifest_symbols = []
                    manifest_scores = []
                    allowed_manifest_routes = set(expected_routes)
                    if audit_current_hk_liquidity:
                        allowed_manifest_routes.add("intraday_liquidity_completion")
                    for index, row in enumerate(manifest, 1):
                        if not isinstance(row, dict):
                            errors.append(f"markets.{market_key}.stats.recall_manifest[{index - 1}] is invalid")
                            manifest_contract_valid = False
                            continue
                        symbol = normalize_live_code(market_key, row.get("symbol"))
                        manifest_symbols.append(symbol)
                        manifest_scores.append(row.get("recall_score"))
                        if (
                            not symbol
                            or row.get("recall_rank") != index
                            or not finite_number(row.get("recall_score"))
                            or row.get("recall_score", -1) < 0
                            or row.get("primary_route") not in expected_routes
                            or not isinstance(row.get("recall_routes"), list)
                            or not row.get("recall_routes")
                            or row.get("primary_route") not in row.get("recall_routes", [])
                            or any(route not in allowed_manifest_routes for route in row.get("recall_routes", []))
                            or not row.get("source")
                            or not timezone_aware_iso_datetime(row.get("observed_at"))
                            or not isinstance(row.get("recall_metrics"), dict)
                        ):
                            errors.append(f"markets.{market_key}.stats.recall_manifest[{index - 1}] is invalid")
                            manifest_contract_valid = False
                        if audit_current_hk_liquidity:
                            row_error_count = len(errors)
                            _append_current_hk_liquidity_row_errors(
                                row,
                                f"markets.hk.stats.recall_manifest[{index - 1}]",
                                errors,
                            )
                            if len(errors) != row_error_count:
                                manifest_contract_valid = False
                    if None in manifest_symbols or len(set(manifest_symbols)) != len(manifest_symbols):
                        errors.append(f"markets.{market_key}.stats.recall_manifest symbols are invalid")
                        manifest_contract_valid = False
                    manifest_symbol_set = {symbol for symbol in manifest_symbols if symbol}
                    if all(finite_number(score) for score in manifest_scores) and any(
                        manifest_scores[index] > manifest_scores[index - 1]
                        for index in range(1, len(manifest_scores))
                    ):
                        errors.append(f"markets.{market_key}.stats.recall_manifest scores are not ranked")
                        manifest_contract_valid = False

                freshness_anchor = stats.get("discovery_freshness_as_of")
                parsed_freshness_anchor = parse_aware_datetime(freshness_anchor)
                if parsed_freshness_anchor is None:
                    errors.append(f"markets.{market_key}.stats.discovery_freshness_as_of is invalid")
                elif generated_moment is not None and abs(
                    generated_moment.astimezone(dt.timezone.utc)
                    - parsed_freshness_anchor.astimezone(dt.timezone.utc)
                ) > DYNAMIC_DISCOVERY_MAX_GENERATION_LAG:
                    errors.append(f"markets.{market_key}.stats.discovery_freshness_as_of is stale or future")
                if (
                    stats.get("universe_origin") == DYNAMIC_MARKET_ORIGIN
                    and retrieved_at is not None
                    and parsed_freshness_anchor is not None
                    and abs(
                        retrieved_at.astimezone(dt.timezone.utc)
                        - parsed_freshness_anchor.astimezone(dt.timezone.utc)
                    ) > dt.timedelta(hours=1)
                ):
                    errors.append(f"markets.{market_key}.stats discovery freshness anchor is inconsistent")
                freshness = dynamic_manifest_source_freshness(
                    manifest if isinstance(manifest, list) else [], market_key, freshness_anchor
                )
                if dynamic_policy_version == DYNAMIC_MARKET_RECALL_POLICY_VERSION:
                    if (
                        stats.get("discovery_freshness_reference_at")
                        != freshness.get("freshness_reference_at")
                    ):
                        errors.append(
                            f"markets.{market_key}.stats.discovery_freshness_reference_at is inconsistent"
                        )
                    if (
                        stats.get("discovery_source_effective_as_of")
                        != freshness.get("source_effective_as_of")
                    ):
                        errors.append(
                            f"markets.{market_key}.stats.discovery_source_effective_as_of is inconsistent"
                        )
                manifest_source_timestamps = [
                    (row.get("recall_metrics") or {}).get("source_timestamp")
                    for row in (manifest if isinstance(manifest, list) else [])
                    if isinstance(row, dict)
                    and isinstance((row.get("recall_metrics") or {}).get("source_timestamp"), (int, float))
                    and not isinstance((row.get("recall_metrics") or {}).get("source_timestamp"), bool)
                    and (row.get("recall_metrics") or {}).get("source_timestamp") > 0
                ]
                parsed_source_as_of = parse_aware_datetime(source_as_of)
                if manifest_source_timestamps:
                    if (
                        parsed_source_as_of is None
                        or abs(parsed_source_as_of.timestamp() - max(manifest_source_timestamps)) > 1
                    ):
                        errors.append(f"markets.{market_key}.stats.discovery_source_as_of does not match manifest")
                elif source_as_of is not None:
                    errors.append(f"markets.{market_key}.stats.discovery_source_as_of has no manifest evidence")
                source_time_count = stats.get("selected_source_time_count")
                source_fresh_count = stats.get("selected_source_fresh_count")
                expected_source_time_coverage = (
                    round(freshness["time_count"] / selected_size, 4)
                    if isinstance(selected_size, int) and selected_size > 0
                    else 0.0
                )
                expected_source_fresh_coverage = (
                    round(freshness["fresh_count"] / selected_size, 4)
                    if isinstance(selected_size, int) and selected_size > 0
                    else 0.0
                )
                if (
                    source_time_count != freshness["time_count"]
                    or source_fresh_count != freshness["fresh_count"]
                    or stats.get("selected_source_time_coverage") != expected_source_time_coverage
                    or stats.get("selected_source_fresh_coverage") != expected_source_fresh_coverage
                    or stats.get("discovery_expected_session") != freshness["expected_session"]
                    or stats.get("discovery_session_phase") != freshness.get("phase")
                ):
                    errors.append(f"markets.{market_key}.stats selected source freshness is inconsistent")
                stale_symbols = stats.get("selected_source_stale_symbols")
                if not isinstance(stale_symbols, list) or len(stale_symbols) != selected_size - freshness["fresh_count"]:
                    errors.append(f"markets.{market_key}.stats.selected_source_stale_symbols is inconsistent")
                pool_health = section.get("pool_health")
                if not isinstance(pool_health, dict):
                    errors.append(f"markets.{market_key}.pool_health is required")
                else:
                    if pool_health.get("target_count") != recall_target or pool_health.get("selected_count") != selected_size:
                        errors.append(f"markets.{market_key}.pool_health recall counts are inconsistent")
                    if pool_health.get("quote_count") != valid_quote_size or pool_health.get("deep_scored_count") != deep_scored_size:
                        errors.append(f"markets.{market_key}.pool_health score counts are inconsistent")
                    if (
                        pool_health.get("universe_origin") != origin
                        or pool_health.get("eligible_discovery_count") != eligible_discovery
                        or pool_health.get("min_eligible_discovery_count") != minimum_discovery
                        or pool_health.get("raw_discovery_count") != raw_discovery
                    ):
                        errors.append(f"markets.{market_key}.pool_health discovery counts are inconsistent")
                    expected_quote_coverage = (
                        round(valid_quote_size / selected_size, 4)
                        if isinstance(selected_size, int)
                        and selected_size > 0
                        and isinstance(valid_quote_size, int)
                        else 0.0
                    )
                    expected_score_coverage = (
                        round(deep_scored_size / selected_size, 4)
                        if isinstance(selected_size, int)
                        and selected_size > 0
                        and isinstance(deep_scored_size, int)
                        else 0.0
                    )
                    if pool_health.get("quote_coverage") != expected_quote_coverage:
                        errors.append(f"markets.{market_key}.pool_health.quote_coverage is inconsistent")
                    if pool_health.get("deep_score_coverage") != expected_score_coverage:
                        errors.append(f"markets.{market_key}.pool_health.deep_score_coverage is inconsistent")
                    quote_health = section.get("quote_health") if isinstance(section.get("quote_health"), dict) else {}
                    realtime_count_value = quote_health.get("realtime_count")
                    expected_realtime_coverage = (
                        round(realtime_count_value / selected_size, 4)
                        if isinstance(selected_size, int)
                        and selected_size > 0
                        and isinstance(realtime_count_value, int)
                        and not isinstance(realtime_count_value, bool)
                        else 0.0
                    )
                    if (
                        pool_health.get("realtime_count") != realtime_count_value
                        or pool_health.get("realtime_coverage") != expected_realtime_coverage
                    ):
                        errors.append(f"markets.{market_key}.pool_health realtime coverage is inconsistent")
                    if pool_health.get("min_score_coverage") != 0.98:
                        errors.append(f"markets.{market_key}.pool_health.min_score_coverage is invalid")

                    derived_pool_reasons = []
                    if origin == DYNAMIC_MARKET_CACHE_ORIGIN:
                        derived_pool_reasons.append("DYNAMIC_DISCOVERY_CACHE_USED")
                    elif origin != DYNAMIC_MARKET_ORIGIN:
                        derived_pool_reasons.append("DYNAMIC_RECALL_CONTRACT_INCOMPLETE")
                    if pagination_complete is not True:
                        derived_pool_reasons.append("DYNAMIC_DISCOVERY_PARTIAL")
                    if freshness["time_count"] == 0:
                        derived_pool_reasons.append("DYNAMIC_DISCOVERY_SOURCE_TIME_UNAVAILABLE")
                    elif expected_source_fresh_coverage < 0.98:
                        derived_pool_reasons.append("DYNAMIC_DISCOVERY_STALE")
                    if not isinstance(eligible_discovery, int) or eligible_discovery < DYNAMIC_MARKET_MIN_ELIGIBLE[market_key]:
                        derived_pool_reasons.append("DYNAMIC_DISCOVERY_BELOW_MINIMUM")
                    if selected_size != recall_target:
                        derived_pool_reasons.append("DYNAMIC_RECALL_TARGET_NOT_MET")
                    if not manifest_contract_valid:
                        derived_pool_reasons.append("DYNAMIC_RECALL_MANIFEST_INVALID")
                    if quote_health.get("requested_count") != selected_size or expected_quote_coverage < 0.98:
                        derived_pool_reasons.append("DYNAMIC_QUOTE_COVERAGE_BELOW_MINIMUM")
                    if expected_score_coverage < 0.98:
                        derived_pool_reasons.append("DYNAMIC_SCORE_COVERAGE_BELOW_MINIMUM")
                    if expected_realtime_coverage < 0.98:
                        derived_pool_reasons.append("DYNAMIC_REALTIME_COVERAGE_BELOW_MINIMUM")
                    published_status = str(pool_health.get("status") or "").lower()
                    published_reasons = pool_health.get("reason_codes")
                    published_reasons = set(published_reasons) if isinstance(published_reasons, list) else set()
                    if published_status not in {"healthy", "degraded"}:
                        errors.append(f"markets.{market_key}.pool_health.status is invalid")
                    expected_status = "degraded" if derived_pool_reasons else "healthy"
                    if published_status != expected_status:
                        errors.append(f"markets.{market_key}.pool_health.status understates derived health")
                    missing_pool_reasons = set(derived_pool_reasons) - published_reasons
                    if missing_pool_reasons:
                        errors.append(
                            f"markets.{market_key}.pool_health.reason_codes are incomplete: "
                            + ",".join(sorted(missing_pool_reasons))
                        )
                    if origin == DYNAMIC_MARKET_CACHE_ORIGIN and published_status != "degraded":
                        errors.append(f"markets.{market_key}.cached dynamic origin must be degraded")

                for candidate in decision_candidates((section.get("decision") or {})):
                    lineage_origin = ((candidate.get("candidate_lineage") or {}).get("universe_origin"))
                    if lineage_origin != origin:
                        errors.append(
                            f"markets.{market_key} candidate lineage origin does not match market origin"
                        )
                    candidate_code = normalize_live_code(
                        market_key, candidate.get("code") or candidate.get("symbol")
                    )
                    if candidate_code not in manifest_symbol_set:
                        errors.append(
                            f"markets.{market_key} candidate is not present in dynamic recall_manifest"
                        )
                    if audit_current_hk_liquidity:
                        _append_current_hk_liquidity_row_errors(
                            candidate,
                            f"markets.hk.candidate[{candidate_code or 'invalid'}]",
                            errors,
                        )
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
            if isinstance(ten_day_model, dict) and ten_day_model.get("model_id") == TEN_DAY_SHADOW_MODEL_ID:
                _append_ten_day_shadow_join_errors(
                    ten_day_model,
                    global_decision,
                    snapshot.get("generated_at"),
                    errors,
                )
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
    _append_schedule_automation_errors(snapshot, errors)
    _append_production_decision_errors(snapshot, errors)
    _append_evidence_loop_errors(snapshot, errors)
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

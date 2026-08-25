from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request
from collections.abc import Callable
from zoneinfo import ZoneInfo


CN_TZ = ZoneInfo("Asia/Shanghai")
SLOTS = [
    (8, 17),
    (10, 17),
    (12, 17),
    (15, 17),
    (16, 17),
    (20, 17),
    (22, 47),
]
# ``github.event.schedule`` identifies the cron invocation that GitHub meant
# to run even when the runner starts much later.  Keep that invocation moment
# separate from the primary data checkpoint: a 23:17 health fallback still
# repairs the 22:47 sample, but it is logically newer than a delayed 22:47
# primary invocation and must not be overwritten by it.
CRON_INVOCATION_SLOTS = {
    "17 0 * * 1-5": [(8, 17)],
    "17 2 * * 1-5": [(10, 17)],
    "17 4 * * 1-5": [(12, 17)],
    "17 7 * * 1-5": [(15, 17)],
    "17 8 * * 1-5": [(16, 17)],
    "17 12 * * 1-5": [(20, 17)],
    "47 14 * * 1-5": [(22, 47)],
    "47 0 * * 1-5": [(8, 47)],
    "47 2 * * 1-5": [(10, 47)],
    "47 4 * * 1-5": [(12, 47)],
    "47 7 * * 1-5": [(15, 47)],
    "47 8 * * 1-5": [(16, 47)],
    "47 12 * * 1-5": [(20, 47)],
    "17 15 * * 1-5": [(23, 17)],
}
EARLY_GRACE_SECONDS = 5 * 60
# GitHub scheduled workflows are not precise timers. They can be delayed by
# tens of minutes, and occasionally longer when GitHub Actions is busy. Treat a
# delayed start as belonging to the latest intended checkpoint instead of
# silently skipping the trading snapshot.
MAX_DELAY_SECONDS = 4 * 60 * 60
RECOVERABLE_SOURCE_REASON_CODES = {
    "BOARD_QUOTA_PARTIAL",
    "BROAD_POOL_BELOW_MINIMUM",
    "MERGED_POOL_EMPTY",
    "POOL_TARGET_NOT_MET",
    "QUOTE_COVERAGE_BELOW_MINIMUM",
    "QUOTE_INPUT_EMPTY",
    "TENCENT_QUOTE_PARTIAL",
    "TENCENT_QUOTE_UNAVAILABLE",
    "A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM",
    "A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM",
    "YAHOO_QUOTE_PARTIAL",
    "YAHOO_QUOTE_UNAVAILABLE",
    "YAHOO_REALTIME_STALE",
    "DYNAMIC_DISCOVERY_CACHE_USED",
    "DYNAMIC_DISCOVERY_PARTIAL",
    "DYNAMIC_DISCOVERY_STALE",
    "DYNAMIC_DISCOVERY_SOURCE_TIME_UNAVAILABLE",
    "DYNAMIC_DISCOVERY_BELOW_MINIMUM",
    "DYNAMIC_RECALL_TARGET_NOT_MET",
    "DYNAMIC_RECALL_MANIFEST_INVALID",
    "DYNAMIC_RECALL_CONTRACT_INCOMPLETE",
    "DYNAMIC_QUOTE_COVERAGE_BELOW_MINIMUM",
    "DYNAMIC_SCORE_COVERAGE_BELOW_MINIMUM",
    "DYNAMIC_REALTIME_COVERAGE_BELOW_MINIMUM",
}
MARKET_RECALL_TARGETS = {
    "a_share": 300,
    "hk": 200,
    "us": 300,
}
A_SHARE_BOARD_TARGETS = {
    "sh_main": 90,
    "sz_main": 75,
    "chinext": 75,
    "star": 60,
}
A_SHARE_DEEP_SCORE_LIMIT = 300
A_SHARE_MIN_TECHNICAL_SCORE_COVERAGE = 0.98
A_SHARE_MIN_DEEP_SCORE_COVERAGE = 0.98
YAHOO_QUOTE_FRESHNESS_POLICY = "latest_exchange_session_v1"
DYNAMIC_MARKET_ORIGIN = "dynamic_market_snapshot"
DYNAMIC_HK_US_UNIVERSE_VERSION = "recall-v2-5-dynamic-hk-us"
DYNAMIC_MARKET_MIN_ELIGIBLE = {"hk": 210, "us": 315}


def as_cn_time(value: dt.datetime) -> dt.datetime:
    """Normalize a timestamp to an aware Beijing timestamp."""
    if value.tzinfo is None:
        return value.replace(tzinfo=CN_TZ)
    return value.astimezone(CN_TZ)


def select_checkpoint(now: dt.datetime) -> dt.datetime | None:
    """Return the latest intended weekday checkpoint, including yesterday.

    Looking back one calendar day is deliberate: the Friday 22:47 checkpoint
    may not start until early Saturday when GitHub Actions is congested.
    """
    now = as_cn_time(now)
    candidates = [
        dt.datetime.combine(day, dt.time(hour, minute), tzinfo=CN_TZ)
        for day in (now.date(), (now - dt.timedelta(days=1)).date())
        if day.weekday() < 5
        for hour, minute in SLOTS
    ]
    eligible = [slot for slot in candidates if slot <= now]
    return max(eligible) if eligible else None


def select_cron_invocation(now: dt.datetime, cron: str | None) -> dt.datetime | None:
    """Resolve the intended cron occurrence independently of runner delay."""
    slots = CRON_INVOCATION_SLOTS.get(str(cron or "").strip())
    if not slots:
        return None
    now = as_cn_time(now)
    candidates = [
        dt.datetime.combine(day, dt.time(hour, minute), tzinfo=CN_TZ)
        for day in (now.date(), (now - dt.timedelta(days=1)).date())
        if day.weekday() < 5
        for hour, minute in slots
    ]
    eligible = [slot for slot in candidates if slot <= now]
    return max(eligible) if eligible else None


def checkpoint_for_invocation(invocation: dt.datetime) -> dt.datetime:
    """Map a fallback invocation to the primary checkpoint it recovers."""
    local = as_cn_time(invocation)
    hour_minute = (local.hour, local.minute)
    if hour_minute == (23, 17):
        return local.replace(hour=22, minute=47, second=0, microsecond=0)
    if local.minute == 47 and hour_minute != (22, 47):
        return local.replace(minute=17, second=0, microsecond=0)
    return local.replace(second=0, microsecond=0)


def checkpoint_is_within_window(now: dt.datetime, slot: dt.datetime | None) -> bool:
    if slot is None:
        return False
    delta = (as_cn_time(now) - as_cn_time(slot)).total_seconds()
    return 0 <= delta <= MAX_DELAY_SECONDS


def snapshot_covers_checkpoint(snapshot: dict, slot: dt.datetime) -> bool:
    """Whether a published/local snapshot was generated for or after a slot."""
    if not isinstance(snapshot, dict):
        return False
    generated_at = snapshot.get("generated_at")
    if not generated_at:
        return False
    try:
        generated = dt.datetime.fromisoformat(str(generated_at))
    except (TypeError, ValueError):
        return False
    return as_cn_time(generated) >= as_cn_time(slot)


def snapshot_data_source_recovery_reasons(snapshot: dict) -> list[str]:
    """Return transient source-health reasons that a fallback should retry.

    Structural research blockers such as an uncalibrated model, a curated
    universe, or missing external evidence are deliberately excluded. A
    fallback can repair a failed/partial quote or broad-pool fetch, but it
    cannot repair those product-model limitations by simply rerunning.
    """
    if not isinstance(snapshot, dict):
        return ["SNAPSHOT_NOT_AN_OBJECT"]

    reasons: list[str] = []
    markets = snapshot.get("markets")
    if not isinstance(markets, dict):
        return ["MARKETS_MISSING_OR_INVALID"]

    for market in ("a_share", "hk", "us"):
        section = markets.get(market)
        if not isinstance(section, dict):
            reasons.append(f"{market.upper()}_MARKET_MISSING_OR_INVALID")
            continue
        pool_health = section.get("pool_health")
        pool_health = pool_health if isinstance(pool_health, dict) else {}
        pool_reason_codes = pool_health.get("reason_codes")
        published_pool_codes = (
            {str(code) for code in pool_reason_codes}
            if isinstance(pool_reason_codes, list)
            else set()
        )
        reasons.extend(sorted(published_pool_codes & RECOVERABLE_SOURCE_REASON_CODES))
        if market in {"hk", "us"}:
            origin = str(((section.get("stats") or {}).get("universe_origin") or ""))
            if origin != DYNAMIC_MARKET_ORIGIN:
                reasons.append(f"{market.upper()}_DYNAMIC_ORIGIN_UNAVAILABLE")
            if not pool_health:
                reasons.append(f"{market.upper()}_POOL_HEALTH_UNKNOWN")
        quote_health = section.get("quote_health")
        if not isinstance(quote_health, dict) or not quote_health:
            reasons.append(f"{market.upper()}_QUOTE_HEALTH_UNKNOWN")
            continue
        quote_status = str(quote_health.get("status") or "").lower()
        requested_count = quote_health.get("requested_count")
        quote_coverage = quote_health.get("quote_coverage")
        reason_codes = quote_health.get("reason_codes")
        health_shape_known = (
            quote_status in {"available", "partial", "unavailable", "failed"}
            and isinstance(requested_count, (int, float))
            and not isinstance(requested_count, bool)
            and requested_count >= 0
            and isinstance(quote_coverage, (int, float))
            and not isinstance(quote_coverage, bool)
            and 0 <= quote_coverage <= 1
            and isinstance(reason_codes, list)
        )
        if not health_shape_known:
            reasons.append(f"{market.upper()}_QUOTE_HEALTH_UNKNOWN")
        if quote_status in {"unavailable", "failed"}:
            reasons.append(f"{market.upper()}_QUOTE_{quote_status.upper()}")
        elif quote_status == "partial" and (
            not isinstance(quote_coverage, (int, float)) or quote_coverage < 0.98
        ):
            reasons.append(f"{market.upper()}_QUOTE_PARTIAL")
        if (
            isinstance(requested_count, (int, float))
            and requested_count > 0
            and isinstance(quote_coverage, (int, float))
            and quote_coverage < 0.8
        ):
            reasons.append(f"{market.upper()}_QUOTE_COVERAGE_BELOW_RECOVERY_THRESHOLD")
        if market in {"hk", "us"}:
            realtime_coverage = quote_health.get("realtime_coverage")
            if (
                not isinstance(realtime_coverage, (int, float))
                or isinstance(realtime_coverage, bool)
                or realtime_coverage < 0.98
            ):
                reasons.append(f"{market.upper()}_REALTIME_COVERAGE_BELOW_MINIMUM")
            realtime_count = quote_health.get("realtime_count")
            stale_count = quote_health.get("stale_realtime_count")
            freshness_reference = quote_health.get("freshness_reference_session")
            freshness_shape_known = (
                quote_health.get("freshness_policy") == YAHOO_QUOTE_FRESHNESS_POLICY
                and isinstance(freshness_reference, str)
                and len(freshness_reference) == 10
                and isinstance(realtime_count, int)
                and not isinstance(realtime_count, bool)
                and isinstance(stale_count, int)
                and not isinstance(stale_count, bool)
                and realtime_count >= 0
                and stale_count >= 0
                and isinstance(requested_count, (int, float))
                and realtime_count + stale_count <= requested_count
                and isinstance(realtime_coverage, (int, float))
                and abs(realtime_coverage - round(realtime_count / requested_count, 4)) < 0.00005
            ) if requested_count else False
            if not freshness_shape_known:
                reasons.append(f"{market.upper()}_REALTIME_FRESHNESS_UNKNOWN")
        quote_codes = {str(code) for code in reason_codes} if isinstance(reason_codes, list) else set()
        reasons.extend(sorted(quote_codes & RECOVERABLE_SOURCE_REASON_CODES))

        stats = section.get("stats")
        stats = stats if isinstance(stats, dict) else {}
        expected_target = MARKET_RECALL_TARGETS[market]
        published_target = stats.get("recall_target")
        selected_size = stats.get("recall_selected_size")
        if not isinstance(selected_size, (int, float)) or isinstance(selected_size, bool):
            selected_size = stats.get("raw_pool_size")
        if published_target != expected_target:
            reasons.append(f"{market.upper()}_RECALL_TARGET_INVALID")
        if (
            not isinstance(selected_size, (int, float))
            or isinstance(selected_size, bool)
            or selected_size < expected_target
        ):
            reasons.append(f"{market.upper()}_POOL_TARGET_NOT_MET")
        if market in {"hk", "us"}:
            prefix = market.upper()
            quote_count = quote_health.get("quote_count")
            realtime_count = quote_health.get("realtime_count")
            deep_scored = stats.get("deep_scored_size")
            eligible_discovery = stats.get("eligible_discovery_size")
            manifest = stats.get("recall_manifest")
            manifest_symbols = [
                str(row.get("symbol") or "").strip().upper()
                for row in manifest
                if isinstance(row, dict)
            ] if isinstance(manifest, list) else []
            minimum_complete = math.ceil(expected_target * 0.98)
            pool_status = str(pool_health.get("status") or "").lower()
            contract_invalid = bool(
                snapshot.get("universe_version") != DYNAMIC_HK_US_UNIVERSE_VERSION
                or stats.get("universe_origin") != DYNAMIC_MARKET_ORIGIN
                or stats.get("discovery_pagination_complete") is not True
                or not isinstance(eligible_discovery, int)
                or isinstance(eligible_discovery, bool)
                or eligible_discovery < DYNAMIC_MARKET_MIN_ELIGIBLE[market]
                or selected_size != expected_target
                or len(manifest_symbols) != expected_target
                or len(set(manifest_symbols)) != expected_target
                or not all(manifest_symbols)
                or stats.get("selected_source_fresh_coverage", 0) < 0.98
                or stats.get("selected_source_fresh_count", 0) < minimum_complete
                or pool_status not in {"healthy", "degraded"}
            )
            if contract_invalid:
                reasons.append(f"{prefix}_DYNAMIC_CONTRACT_INVALID")
            quote_shape_invalid = bool(
                not isinstance(quote_count, int)
                or isinstance(quote_count, bool)
                or not isinstance(requested_count, int)
                or isinstance(requested_count, bool)
                or requested_count != expected_target
                or quote_count < minimum_complete
                or quote_coverage != round(quote_count / expected_target, 4)
            )
            if quote_shape_invalid:
                reasons.append(f"{prefix}_QUOTE_COVERAGE_BELOW_MINIMUM")
            realtime_shape_invalid = bool(
                not isinstance(realtime_count, int)
                or isinstance(realtime_count, bool)
                or realtime_count < minimum_complete
                or quote_health.get("realtime_coverage")
                != (
                    round(realtime_count / expected_target, 4)
                    if isinstance(realtime_count, int) and not isinstance(realtime_count, bool)
                    else -1
                )
            )
            if realtime_shape_invalid:
                reasons.append(f"{prefix}_REALTIME_COVERAGE_BELOW_MINIMUM")
            score_shape_invalid = bool(
                not isinstance(deep_scored, int)
                or isinstance(deep_scored, bool)
                or deep_scored < minimum_complete
                or stats.get("scored_size") != deep_scored
            )
            if score_shape_invalid:
                reasons.append(f"{prefix}_SCORE_COVERAGE_BELOW_MINIMUM")
            if pool_status != "healthy" or published_pool_codes:
                reasons.append(f"{prefix}_POOL_HEALTH_DEGRADED")
        if market == "a_share":
            board_counts = stats.get("board_counts")
            if (
                not isinstance(board_counts, dict)
                or set(board_counts) != set(A_SHARE_BOARD_TARGETS)
                or any(
                    not isinstance(board_counts.get(board), (int, float))
                    or isinstance(board_counts.get(board), bool)
                    or board_counts.get(board) < target
                    for board, target in A_SHARE_BOARD_TARGETS.items()
                )
            ):
                reasons.append("A_SHARE_BOARD_QUOTA_PARTIAL")
            deep_limit = stats.get("deep_score_limit")
            base_scored = stats.get("base_scored_size")
            technical_attempted = stats.get("technical_attempted_size")
            technical_scored = stats.get("technical_scored_size")
            technical_kline_complete = stats.get("technical_kline_complete_size")
            technical_coverage = stats.get("technical_kline_coverage")
            deep_eligible = stats.get("deep_eligible_size")
            deep_attempted = stats.get("deep_attempted_size")
            deep_completed = stats.get("deep_scored_size")
            deep_coverage = stats.get("deep_kline_coverage")
            valid_quote_count = quote_health.get("quote_count")
            technical_shape_known = (
                isinstance(valid_quote_count, (int, float))
                and not isinstance(valid_quote_count, bool)
                and isinstance(base_scored, int)
                and not isinstance(base_scored, bool)
                and base_scored == int(valid_quote_count)
                and isinstance(technical_attempted, int)
                and not isinstance(technical_attempted, bool)
                and technical_attempted == base_scored
                and isinstance(technical_scored, int)
                and not isinstance(technical_scored, bool)
                and technical_scored == technical_attempted
                and isinstance(technical_kline_complete, int)
                and not isinstance(technical_kline_complete, bool)
                and 0 <= technical_kline_complete <= technical_scored
                and isinstance(technical_coverage, (int, float))
                and not isinstance(technical_coverage, bool)
                and technical_coverage
                == (round(technical_kline_complete / technical_attempted, 4) if technical_attempted else 0.0)
            )
            required_technical_complete = (
                math.ceil(technical_attempted * A_SHARE_MIN_TECHNICAL_SCORE_COVERAGE)
                if isinstance(technical_attempted, int) and technical_attempted > 0
                else 1
            )
            if not technical_shape_known or technical_kline_complete < required_technical_complete:
                reasons.append("A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM")
            deep_shape_known = (
                deep_limit == A_SHARE_DEEP_SCORE_LIMIT
                and isinstance(technical_kline_complete, int)
                and not isinstance(technical_kline_complete, bool)
                and isinstance(deep_eligible, int)
                and not isinstance(deep_eligible, bool)
                and 0 <= deep_eligible <= technical_kline_complete
                and isinstance(deep_attempted, int)
                and not isinstance(deep_attempted, bool)
                and isinstance(deep_completed, int)
                and not isinstance(deep_completed, bool)
                and isinstance(deep_coverage, (int, float))
                and not isinstance(deep_coverage, bool)
                and deep_attempted == min(A_SHARE_DEEP_SCORE_LIMIT, deep_eligible)
                and 0 <= deep_completed <= deep_attempted
                and deep_coverage == (round(deep_completed / deep_attempted, 4) if deep_attempted else 0.0)
            )
            required_complete = math.ceil(deep_attempted * A_SHARE_MIN_DEEP_SCORE_COVERAGE) if isinstance(deep_attempted, int) and deep_attempted > 0 else 1
            required_eligible = min(A_SHARE_DEEP_SCORE_LIMIT, technical_kline_complete) if isinstance(technical_kline_complete, int) else 1
            if (
                not deep_shape_known
                or deep_eligible < required_eligible
                or deep_completed < required_complete
            ):
                reasons.append("A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM")
        raw_pool_size = stats.get("raw_pool_size")
        scored_size = stats.get("scored_size")
        if (
            isinstance(raw_pool_size, (int, float))
            and raw_pool_size > 0
            and isinstance(scored_size, (int, float))
            and scored_size <= 0
        ):
            reasons.append(f"{market.upper()}_SCORING_EMPTY")

    return list(dict.fromkeys(reasons))


def snapshot_is_source_healthy(snapshot: dict) -> bool:
    return not snapshot_data_source_recovery_reasons(snapshot)


def load_json_url(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "xuangu-schedule-gate/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("schedule status response must be a JSON object")
    return payload


def published_checkpoint_source(
    slot: dt.datetime,
    *,
    status_url: str | None,
    url_loader: Callable[[str], dict] = load_json_url,
) -> str | None:
    """Return live only when production proves a healthy slot is published.

    A checked-out latest file only proves that data reached the repository. It
    does not prove that the corresponding deployment succeeded, so local data
    must never suppress a scheduled recovery run.
    """
    if status_url:
        try:
            live_snapshot = url_loader(status_url)
            if snapshot_covers_checkpoint(live_snapshot, slot):
                reasons = snapshot_data_source_recovery_reasons(live_snapshot)
                if not reasons:
                    return "live"
                print(
                    "Live snapshot covers the checkpoint but needs source recovery: "
                    + ",".join(reasons)
                )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            print(f"Live checkpoint check unavailable: {exc}")
    return None


def write_output(**values: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{key}={value}" for key, value in values.items()]
    print("\n".join(lines))
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def main() -> int:
    override_now = os.environ.get("SCHEDULE_GATE_NOW")
    now = (
        as_cn_time(dt.datetime.fromisoformat(override_now))
        if override_now
        else dt.datetime.now(CN_TZ)
    )
    cron = os.environ.get("SCHEDULE_GATE_CRON") or None
    invocation_clocks = CRON_INVOCATION_SLOTS.get(str(cron or "").strip()) or SLOTS
    today_slots = (
        [
            now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            for hour, minute in invocation_clocks
        ]
        if now.weekday() < 5
        else []
    )
    future_slots = [slot for slot in today_slots if slot > now]
    if future_slots:
        next_slot = min(future_slots)
        early_delta = (next_slot - now).total_seconds()
        if early_delta <= EARLY_GRACE_SECONDS:
            wait_seconds = int(early_delta)
            if override_now:
                # Keep test/manual overrides deterministic without a real wait.
                now = next_slot
            else:
                print(
                    f"Scheduled run arrived early at {now:%Y-%m-%d %H:%M:%S}; "
                    f"waiting {wait_seconds}s for slot {next_slot:%H:%M}."
                )
                time.sleep(wait_seconds)
                now = dt.datetime.now(CN_TZ)

    cron_invocation = select_cron_invocation(now, cron)
    nearest = checkpoint_for_invocation(cron_invocation) if cron_invocation else select_checkpoint(now)
    invocation = cron_invocation or nearest
    if nearest is None:
        write_output(
            should_run="false",
            reason=f"no_eligible_checkpoint:now={now:%Y-%m-%d_%H:%M:%S}",
        )
        return 0

    delta = (now - invocation).total_seconds() if invocation else float("inf")
    if checkpoint_is_within_window(now, invocation):
        status_url = os.environ.get("SCHEDULE_GATE_STATUS_URL") or None
        published_source = published_checkpoint_source(
            nearest,
            status_url=status_url,
        )
        if published_source:
            write_output(
                should_run="false",
                reason="slot_already_published",
                slot=nearest.isoformat(timespec="minutes"),
                invocation_slot=invocation.isoformat(timespec="minutes"),
                published_source=published_source,
            )
            return 0

        write_output(
            should_run="true",
            reason=f"slot_ok:{nearest:%Y-%m-%d_%H:%M}:delta_seconds={int(delta)}",
            slot=nearest.isoformat(timespec="minutes"),
            invocation_slot=invocation.isoformat(timespec="minutes"),
        )
        return 0

    write_output(
        should_run="false",
        reason=(
            f"outside_allowed_slots:now={now:%Y-%m-%d_%H:%M:%S}:"
            f"nearest={nearest:%Y-%m-%d_%H:%M}:"
            f"invocation={invocation:%Y-%m-%d_%H:%M}:delta_seconds={int(delta)}"
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

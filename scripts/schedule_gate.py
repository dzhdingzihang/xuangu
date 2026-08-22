from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.request
from collections.abc import Callable
from zoneinfo import ZoneInfo


CN_TZ = ZoneInfo("Asia/Shanghai")
SLOTS = [
    (8, 58),
    (9, 58),
    (10, 58),
    (12, 58),
    (13, 58),
    (14, 58),
    (21, 28),
    (23, 58),
]
EARLY_GRACE_SECONDS = 5 * 60
# GitHub scheduled workflows are not precise timers. They can be delayed by
# tens of minutes, and occasionally longer when GitHub Actions is busy. Treat a
# delayed start as belonging to the latest intended checkpoint instead of
# silently skipping the trading snapshot.
MAX_DELAY_SECONDS = 4 * 60 * 60
DEFAULT_LATEST_PATH = pathlib.Path("data/picks/latest.json")
RECOVERABLE_SOURCE_REASON_CODES = {
    "BROAD_POOL_BELOW_MINIMUM",
    "MERGED_POOL_EMPTY",
    "QUOTE_COVERAGE_BELOW_MINIMUM",
    "QUOTE_INPUT_EMPTY",
    "TENCENT_QUOTE_PARTIAL",
    "TENCENT_QUOTE_UNAVAILABLE",
    "YAHOO_QUOTE_PARTIAL",
    "YAHOO_QUOTE_UNAVAILABLE",
}


def as_cn_time(value: dt.datetime) -> dt.datetime:
    """Normalize a timestamp to an aware Beijing timestamp."""
    if value.tzinfo is None:
        return value.replace(tzinfo=CN_TZ)
    return value.astimezone(CN_TZ)


def select_checkpoint(now: dt.datetime) -> dt.datetime | None:
    """Return the latest intended weekday checkpoint, including yesterday.

    Looking back one calendar day is deliberate: the Friday 23:58 checkpoint
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
    markets = snapshot.get("markets") or {}
    a_share = markets.get("a_share") or {}
    quote_health = a_share.get("quote_health") or {}
    pool_health = a_share.get("pool_health") or {}
    published_codes = {str(code) for code in list(pool_health.get("reason_codes") or [])}
    reasons.extend(sorted(published_codes & RECOVERABLE_SOURCE_REASON_CODES))

    for market in ("a_share", "hk", "us"):
        section = markets.get(market) or {}
        quote_health = section.get("quote_health") or {}
        quote_status = str(quote_health.get("status") or "").lower()
        requested_count = quote_health.get("requested_count")
        quote_coverage = quote_health.get("quote_coverage")
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
        quote_codes = {str(code) for code in list(quote_health.get("reason_codes") or [])}
        reasons.extend(sorted(quote_codes & RECOVERABLE_SOURCE_REASON_CODES))

        stats = section.get("stats") or {}
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


def load_json_path(path: pathlib.Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("local latest snapshot must be a JSON object")
    return payload


def published_checkpoint_source(
    slot: dt.datetime,
    *,
    status_url: str | None,
    latest_path: pathlib.Path | None,
    url_loader: Callable[[str], dict] = load_json_url,
    path_loader: Callable[[pathlib.Path], dict] = load_json_path,
) -> str | None:
    """Return the first source proving a slot has already been generated.

    The live endpoint is authoritative. The checked-out latest snapshot is a
    fallback for a temporary status-endpoint outage and also protects manual
    reruns before a previous archival commit is visible.
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

    if latest_path:
        try:
            local_snapshot = path_loader(latest_path)
            if snapshot_covers_checkpoint(local_snapshot, slot):
                reasons = snapshot_data_source_recovery_reasons(local_snapshot)
                if not reasons:
                    return "local"
                print(
                    "Local snapshot covers the checkpoint but needs source recovery: "
                    + ",".join(reasons)
                )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            print(f"Local checkpoint check unavailable: {exc}")
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
    today_slots = (
        [
            now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            for hour, minute in SLOTS
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

    nearest = select_checkpoint(now)
    if nearest is None:
        write_output(
            should_run="false",
            reason=f"no_eligible_checkpoint:now={now:%Y-%m-%d_%H:%M:%S}",
        )
        return 0

    delta = (now - nearest).total_seconds()
    if checkpoint_is_within_window(now, nearest):
        status_url = os.environ.get("SCHEDULE_GATE_STATUS_URL") or None
        latest_path_value = os.environ.get("SCHEDULE_GATE_LATEST_PATH", str(DEFAULT_LATEST_PATH))
        latest_path = pathlib.Path(latest_path_value) if latest_path_value else None
        published_source = published_checkpoint_source(
            nearest,
            status_url=status_url,
            latest_path=latest_path,
        )
        if published_source:
            write_output(
                should_run="false",
                reason="slot_already_published",
                slot=nearest.isoformat(timespec="minutes"),
                published_source=published_source,
            )
            return 0

        write_output(
            should_run="true",
            reason=f"slot_ok:{nearest:%Y-%m-%d_%H:%M}:delta_seconds={int(delta)}",
            slot=nearest.isoformat(timespec="minutes"),
        )
        return 0

    write_output(
        should_run="false",
        reason=(
            f"outside_allowed_slots:now={now:%Y-%m-%d_%H:%M:%S}:"
            f"nearest={nearest:%Y-%m-%d_%H:%M}:delta_seconds={int(delta)}"
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

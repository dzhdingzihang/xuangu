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
            if snapshot_covers_checkpoint(url_loader(status_url), slot):
                return "live"
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            print(f"Live checkpoint check unavailable: {exc}")

    if latest_path:
        try:
            if snapshot_covers_checkpoint(path_loader(latest_path), slot):
                return "local"
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

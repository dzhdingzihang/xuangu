from __future__ import annotations

import datetime as dt
import os
import sys
import time
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
        dt.datetime.fromisoformat(override_now).astimezone(CN_TZ)
        if override_now
        else dt.datetime.now(CN_TZ)
    )
    if now.weekday() >= 5:
        write_output(should_run="false", reason=f"not_trade_weekday:{now:%Y-%m-%d_%H:%M}")
        return 0

    today_slots = [
        now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        for hour, minute in SLOTS
    ]
    future_slots = [slot for slot in today_slots if slot > now]
    if future_slots:
        next_slot = min(future_slots)
        early_delta = (next_slot - now).total_seconds()
        if early_delta <= EARLY_GRACE_SECONDS:
            wait_seconds = int(early_delta)
            print(
                f"Scheduled run arrived early at {now:%Y-%m-%d %H:%M:%S}; "
                f"waiting {wait_seconds}s for slot {next_slot:%H:%M}."
            )
            time.sleep(wait_seconds)
            now = dt.datetime.now(CN_TZ)

    candidate_days = [now.date(), (now - dt.timedelta(days=1)).date()]
    candidates = sorted(
        dt.datetime.combine(day, dt.time(hour, minute), tzinfo=CN_TZ)
        for day in candidate_days
        for hour, minute in SLOTS
    )
    past_slots = [slot for slot in candidates if slot <= now]
    nearest = past_slots[-1]
    delta = (now - nearest).total_seconds()

    if 0 <= delta <= MAX_DELAY_SECONDS:
        write_output(
            should_run="true",
            reason=f"slot_ok:{nearest:%Y-%m-%d_%H:%M}:delta_seconds={int(delta)}",
            slot=f"{nearest:%Y-%m-%d %H:%M}",
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

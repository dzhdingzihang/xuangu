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
LATE_GRACE_SECONDS = 12 * 60


def write_output(**values: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{key}={value}" for key, value in values.items()]
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


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

    candidates = [
        now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        for hour, minute in SLOTS
    ]
    nearest = min(candidates, key=lambda slot: abs((now - slot).total_seconds()))
    delta = (now - nearest).total_seconds()

    if -EARLY_GRACE_SECONDS <= delta < 0:
        wait_seconds = int(abs(delta))
        print(f"Scheduled run arrived early at {now:%Y-%m-%d %H:%M:%S}; waiting {wait_seconds}s for slot {nearest:%H:%M}.")
        time.sleep(wait_seconds)
        now = dt.datetime.now(CN_TZ)
        delta = (now - nearest).total_seconds()

    if 0 <= delta <= LATE_GRACE_SECONDS:
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

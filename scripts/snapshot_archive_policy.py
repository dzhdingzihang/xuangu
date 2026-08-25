"""Decide which verified snapshots must be committed to immutable history."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo


CN_TZ = ZoneInfo("Asia/Shanghai")
ARCHIVE_POLICY = "daily_2247_or_qualified_or_executable_v2"


def _aware_moment(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def archive_reasons(snapshot: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    automation = snapshot.get("automation")
    automation = automation if isinstance(automation, Mapping) else {}
    checkpoint = _aware_moment(automation.get("scheduled_slot"))
    if (
        str(automation.get("trigger") or "") == "schedule"
        and checkpoint is not None
        and (checkpoint.astimezone(CN_TZ).hour, checkpoint.astimezone(CN_TZ).minute) == (22, 47)
    ):
        reasons.append("DAILY_2247_CHECKPOINT")

    production = snapshot.get("production_decision")
    production = production if isinstance(production, Mapping) else {}
    production_primary = production.get("primary")
    qualified_count = production.get("qualified_candidate_count")
    if (
        production.get("action") == "QUALIFIED_PICK"
        and isinstance(production_primary, Mapping)
        and production_primary.get("status") == "QUALIFIED"
        and isinstance(qualified_count, int)
        and not isinstance(qualified_count, bool)
        and qualified_count > 0
    ):
        reasons.append("PRODUCTION_QUALIFIED_PICK")

    global_decision = snapshot.get("global_decision")
    global_decision = global_decision if isinstance(global_decision, Mapping) else {}
    primary = global_decision.get("primary")
    if (
        global_decision.get("action") == "REVIEW_EXECUTABLE_PICK"
        and isinstance(primary, Mapping)
        and primary.get("status") == "EXECUTABLE"
    ):
        reasons.append("EXECUTABLE_PREDICTION")
    return reasons

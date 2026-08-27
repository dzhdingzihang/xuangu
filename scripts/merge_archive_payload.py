#!/usr/bin/env python3
"""Monotonically merge a verified recovery payload into an archive tree."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
from collections import Counter
from typing import Any

import model_observation_ledger
import observation_outcome_ledger


def read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def aware_moment(value: Any, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"timezone-aware {field} required") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timezone-aware {field} required")
    return parsed


def _copy_new(source: pathlib.Path, target: pathlib.Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _write_json(target: pathlib.Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _scheduled_invocation(snapshot: dict[str, Any]) -> dt.datetime | None:
    automation = snapshot.get("automation")
    if not isinstance(automation, dict) or str(automation.get("trigger") or "") != "schedule":
        return None
    value = automation.get("scheduled_invocation_slot") or automation.get("scheduled_slot")
    if value in (None, ""):
        return None
    return aware_moment(value, "automation.scheduled_invocation_slot")


def _incoming_latest_is_older(incoming: dict[str, Any], existing: dict[str, Any]) -> bool:
    """Prefer logical cron order before wall-clock generation order.

    GitHub may start a 22:47 invocation after its 23:17 recovery.  Comparing
    only ``generated_at`` would let that older logical run replace the newer
    recovery in the archive even when deployment correctly rejected it.
    """
    incoming_invocation = _scheduled_invocation(incoming)
    existing_invocation = _scheduled_invocation(existing)
    if incoming_invocation is not None and existing_invocation is not None:
        if incoming_invocation != existing_invocation:
            return incoming_invocation < existing_invocation
    incoming_time = aware_moment(incoming.get("generated_at"), "incoming generated_at")
    existing_time = aware_moment(existing.get("generated_at"), "existing generated_at")
    return incoming_time < existing_time


def _validate_observation_cohort(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return model_observation_ledger.validate_observation_cohort(payload)
    except (
        model_observation_ledger.ObservationContractError,
        model_observation_ledger.ObservationConflictError,
    ) as exc:
        raise ValueError(f"observation cohort contract conflict: {exc}") from exc


def _install_observation(source: pathlib.Path, target: pathlib.Path) -> None:
    """Validate legacy/current input and always persist the current canonical form."""

    _write_json(target, _validate_observation_cohort(read_json(source)))


def _merge_observation(source: pathlib.Path, target: pathlib.Path) -> str:
    incoming_raw = read_json(source)
    existing_raw = read_json(target)
    incoming = _validate_observation_cohort(incoming_raw)
    existing = _validate_observation_cohort(existing_raw)
    if incoming.get("cohort_id") != existing.get("cohort_id"):
        raise ValueError(f"observation identity conflict: {target}")
    existing_revisions = {
        item["revision_id"]: item for item in existing["revisions"]
    }
    incoming_revisions = {
        item["revision_id"]: item for item in incoming["revisions"]
    }
    for revision_id in set(existing_revisions) & set(incoming_revisions):
        if existing_revisions[revision_id] != incoming_revisions[revision_id]:
            raise ValueError(f"observation revision conflict: {revision_id}")
    if set(existing_revisions) > set(incoming_revisions):
        if existing_raw != existing:
            _write_json(target, existing)
        return "preserved_newer"
    if set(incoming_revisions) >= set(existing_revisions):
        if existing_raw == incoming:
            return "unchanged"
        _write_json(target, incoming)
        return "updated"
    raise ValueError(f"observation revisions diverged: {target}")


def _merge_outcome(source: pathlib.Path, target: pathlib.Path) -> str:
    incoming = read_json(source)
    existing = read_json(target)
    identity = ("track", "prediction_id", "model_id", "label_version", "market", "code")
    if any(incoming.get(key) != existing.get(key) for key in identity):
        raise ValueError(f"outcome identity conflict: {target}")
    incoming_status = str(incoming.get("status") or "").upper()
    existing_status = str(existing.get("status") or "").upper()
    if existing_status == "SETTLED" and incoming_status != "SETTLED":
        return "preserved_newer"
    if existing_status == incoming_status and incoming != existing:
        if existing_status == "SETTLED":
            raise ValueError(f"settled outcome is immutable: {target}")
        existing_time = aware_moment(
            existing.get("generated_at") or existing.get("created_at"),
            "outcome existing time",
        )
        incoming_time = aware_moment(
            incoming.get("generated_at") or incoming.get("created_at"),
            "outcome incoming time",
        )
        if existing_time > incoming_time:
            return "preserved_newer"
    _copy_new(source, target)
    return "updated" if incoming != existing else "unchanged"


def _validate_observation_batch(
    payload: dict[str, Any],
    *,
    cohort: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return observation_outcome_ledger.validate_outcome_batch(
            payload,
            cohort=cohort,
        )
    except (
        observation_outcome_ledger.ObservationOutcomeContractError,
        observation_outcome_ledger.ObservationOutcomeConflictError,
    ) as exc:
        raise ValueError(f"observation settlement contract conflict: {exc}") from exc


def _all_pending_maturity(batch: dict[str, Any]) -> bool:
    rows = batch.get("outcomes") or []
    # An empty observation cohort has no mature identity to preserve and is
    # therefore as safe to rebind as an all-PENDING_MATURITY cohort.
    return all(row.get("status") == "PENDING_MATURITY" for row in rows)


def _observation_batch_identity(batch: dict[str, Any]) -> tuple[Any, Any]:
    return batch.get("canonical_revision_id"), batch.get("cohort_sha256")


def _merge_same_canonical_observation_batches(
    incoming: dict[str, Any],
    existing: dict[str, Any],
    cohort: dict[str, Any],
) -> dict[str, Any]:
    incoming_time = aware_moment(
        incoming.get("evaluated_at"),
        "incoming observation evaluated_at",
    )
    existing_time = aware_moment(
        existing.get("evaluated_at"),
        "existing observation evaluated_at",
    )
    incoming_rows = {
        row["observation_id"]: row for row in incoming.get("outcomes") or []
    }
    existing_rows = {
        row["observation_id"]: row for row in existing.get("outcomes") or []
    }
    if set(incoming_rows) != set(existing_rows):
        raise ValueError("observation settlement coverage diverged")

    pending_rank = {"PENDING_MATURITY": 0, "PENDING_DATA": 1}
    merged_rows: list[dict[str, Any]] = []
    for observation_id in sorted(incoming_rows):
        incoming_row = incoming_rows[observation_id]
        existing_row = existing_rows[observation_id]
        if incoming_row == existing_row:
            merged_rows.append(existing_row)
            continue
        incoming_status = str(incoming_row.get("status") or "")
        existing_status = str(existing_row.get("status") or "")
        if incoming_status == existing_status == "SETTLED":
            raise ValueError(f"settled observation is immutable: {observation_id}")
        if existing_status == "SETTLED":
            merged_rows.append(existing_row)
            continue
        if incoming_status == "SETTLED":
            merged_rows.append(incoming_row)
            continue
        if incoming_status not in pending_rank or existing_status not in pending_rank:
            raise ValueError(f"unknown observation settlement state: {observation_id}")
        if pending_rank[incoming_status] > pending_rank[existing_status]:
            merged_rows.append(incoming_row)
        elif pending_rank[existing_status] > pending_rank[incoming_status]:
            merged_rows.append(existing_row)
        else:
            merged_rows.append(incoming_row if incoming_time >= existing_time else existing_row)

    counts = Counter(str(row.get("status") or "") for row in merged_rows)
    if counts and counts.get("SETTLED", 0) == len(merged_rows):
        status = "SETTLED"
    elif len(counts) == 1:
        status = next(iter(counts))
    else:
        status = "PARTIAL"
    base = dict(incoming if incoming_time >= existing_time else existing)
    base.update(
        {
            "evaluated_at": max(incoming_time, existing_time).isoformat(timespec="seconds"),
            "status": status,
            "prediction_count": len(merged_rows),
            "status_counts": dict(sorted(counts.items())),
            "outcomes": merged_rows,
        }
    )
    base["batch_sha256"] = observation_outcome_ledger._batch_digest(base)
    return _validate_observation_batch(base, cohort=cohort)


def _merge_observation_settlement(source: pathlib.Path, target: pathlib.Path) -> str:
    incoming = _validate_observation_batch(read_json(source))
    existing = _validate_observation_batch(read_json(target))
    if (
        incoming.get("track") != "MODEL_OBSERVATION"
        or existing.get("track") != "MODEL_OBSERVATION"
        or incoming.get("cohort_id") != existing.get("cohort_id")
    ):
        raise ValueError(f"observation settlement identity conflict: {target}")

    cohort_id = str(incoming.get("cohort_id") or "")
    cohort_path = target.parent.parent / "observations" / f"{cohort_id}.json"
    if not cohort_path.is_file():
        raise ValueError(f"merged observation cohort is missing: {cohort_path}")
    cohort = read_json(cohort_path)
    canonical_identity = (
        cohort.get("canonical_revision_id"),
        cohort.get("cohort_sha256"),
    )
    incoming_identity = _observation_batch_identity(incoming)
    existing_identity = _observation_batch_identity(existing)

    if incoming_identity != existing_identity:
        matching = []
        if incoming_identity == canonical_identity:
            matching.append(("incoming", incoming))
        if existing_identity == canonical_identity:
            matching.append(("existing", existing))
        if len(matching) != 1:
            raise ValueError("observation settlement has no unique merged canonical batch")
        selected_name, selected = matching[0]
        stale = existing if selected_name == "incoming" else incoming
        if not _all_pending_maturity(stale):
            raise ValueError("mature observation settlement cannot change canonical revision")
        _validate_observation_batch(selected, cohort=cohort)
        if selected_name == "existing":
            return "preserved_newer"
        _copy_new(source, target)
        return "updated"

    if incoming_identity != canonical_identity:
        raise ValueError("observation settlement canonical identity is stale")
    incoming = _validate_observation_batch(incoming, cohort=cohort)
    existing = _validate_observation_batch(existing, cohort=cohort)
    merged = _merge_same_canonical_observation_batches(incoming, existing, cohort)
    if merged == existing:
        return "unchanged"
    if merged == incoming:
        _copy_new(source, target)
    else:
        _write_json(target, merged)
    return "updated"


def _payload_merge_priority(
    path: pathlib.Path,
    payload_data: pathlib.Path,
) -> tuple[int, str]:
    relative = path.relative_to(payload_data)
    if relative.parts[:2] == ("outcomes", "observations"):
        return 0, relative.as_posix()
    if relative.parts[:2] == ("outcomes", "observation-settlements"):
        return 1, relative.as_posix()
    return 2, relative.as_posix()


def merge_payload(payload_root: pathlib.Path, archive_tree: pathlib.Path) -> dict[str, int]:
    payload_data = payload_root.resolve() / "data"
    archive_data = archive_tree.resolve() / "data"
    if not payload_data.is_dir():
        raise ValueError("payload data directory is missing")
    archive_data.mkdir(parents=True, exist_ok=True)
    counters = {"copied": 0, "updated": 0, "unchanged": 0, "preserved_newer": 0}
    incoming_latest = payload_data / "picks" / "latest.json"
    existing_latest = archive_data / "picks" / "latest.json"
    preserve_latest = False
    if incoming_latest.is_file() and existing_latest.is_file():
        incoming = read_json(incoming_latest)
        existing = read_json(existing_latest)
        incoming_time = aware_moment(incoming.get("generated_at"), "incoming generated_at")
        existing_time = aware_moment(existing.get("generated_at"), "existing generated_at")
        if _incoming_latest_is_older(incoming, existing):
            preserve_latest = True
        elif incoming_time == existing_time and incoming != existing:
            raise ValueError("same-moment latest snapshots differ")

    sources = [path for path in payload_data.rglob("*") if path.is_file()]
    for source in sorted(
        sources,
        key=lambda path: _payload_merge_priority(path, payload_data),
    ):
        relative = source.relative_to(payload_data)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe payload path: {relative}")
        target = archive_data / relative
        if relative == pathlib.Path("picks/latest.json"):
            if preserve_latest:
                counters["preserved_newer"] += 1
                continue
            if target.exists() and source.read_bytes() != target.read_bytes():
                _copy_new(source, target)
                counters["updated"] += 1
                continue
        if relative.parts[:2] == ("outcomes", "observations"):
            if not target.exists():
                _install_observation(source, target)
                counters["copied"] += 1
            else:
                counters[_merge_observation(source, target)] += 1
            continue
        if not target.exists():
            _copy_new(source, target)
            counters["copied"] += 1
            continue
        if source.read_bytes() == target.read_bytes():
            counters["unchanged"] += 1
            continue
        if relative.parts[:2] == ("outcomes", "observation-settlements"):
            result = _merge_observation_settlement(source, target)
        elif relative.parts and relative.parts[0] == "outcomes":
            result = _merge_outcome(source, target)
        elif relative.parts and relative.parts[0] == "picks" and relative.name != "latest.json":
            raise ValueError(f"immutable snapshot conflict: {relative}")
        else:
            raise ValueError(f"refusing ambiguous archive overwrite: {relative}")
        counters[result] += 1
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload_root", type=pathlib.Path)
    parser.add_argument("archive_tree", type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps(merge_payload(args.payload_root, args.archive_tree), sort_keys=True))


if __name__ == "__main__":
    main()

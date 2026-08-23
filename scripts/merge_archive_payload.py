#!/usr/bin/env python3
"""Monotonically merge a verified recovery payload into an archive tree."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
from typing import Any


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


def _merge_observation(source: pathlib.Path, target: pathlib.Path) -> str:
    incoming = read_json(source)
    existing = read_json(target)
    if incoming.get("track") != "MODEL_OBSERVATION" or existing.get("track") != "MODEL_OBSERVATION":
        raise ValueError(f"observation track conflict: {target}")
    if incoming.get("cohort_id") != existing.get("cohort_id"):
        raise ValueError(f"observation identity conflict: {target}")
    existing_revisions = {
        item.get("revision_id"): item
        for item in (existing.get("revisions") or [])
        if isinstance(item, dict)
    }
    incoming_revisions = {
        item.get("revision_id"): item
        for item in (incoming.get("revisions") or [])
        if isinstance(item, dict)
    }
    for revision_id in set(existing_revisions) & set(incoming_revisions):
        if existing_revisions[revision_id] != incoming_revisions[revision_id]:
            raise ValueError(f"observation revision conflict: {revision_id}")
    if set(existing_revisions) > set(incoming_revisions):
        return "preserved_newer"
    if set(incoming_revisions) >= set(existing_revisions):
        _copy_new(source, target)
        return "updated" if incoming != existing else "unchanged"
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
        if existing_time > incoming_time:
            preserve_latest = True
        elif existing_time == incoming_time and incoming != existing:
            raise ValueError("same-moment latest snapshots differ")

    for source in sorted(path for path in payload_data.rglob("*") if path.is_file()):
        relative = source.relative_to(payload_data)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe payload path: {relative}")
        target = archive_data / relative
        if relative == pathlib.Path("picks/latest.json") and preserve_latest:
            counters["preserved_newer"] += 1
            continue
        if not target.exists():
            _copy_new(source, target)
            counters["copied"] += 1
            continue
        if source.read_bytes() == target.read_bytes():
            counters["unchanged"] += 1
            continue
        if relative.parts[:2] == ("outcomes", "observations"):
            result = _merge_observation(source, target)
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

#!/usr/bin/env python3
"""Persist and summarize verified GitHub scheduler publication receipts.

Receipts are deliberately tiny and separate from immutable market snapshots.
The deploy workflow creates one only *after* the complete production verifier
passes, then a least-privilege writer installs that exact receipt on ``main``.
Consequently a failed or rolled-back deployment cannot become positive
scheduler evidence.

The aggregate is an operational SLO, never an exchange or GitHub SLA.  It uses
a 45-minute grace period and stays ``INITIALIZING`` until a full trailing
24-hour evidence window exists.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from collections.abc import Iterable, Mapping
from typing import Any
from zoneinfo import ZoneInfo


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_deployment import snapshot_sha256  # noqa: E402


CN_TZ = ZoneInfo("Asia/Shanghai")
NY_TZ = ZoneInfo("America/New_York")
RECEIPT_CONTRACT = "scheduler-checkpoint-receipt-v1"
LEDGER_CONTRACT = "scheduler-checkpoint-ledger-v1"
SLO_CONTRACT = "scheduler-slo-v1"
DEFAULT_DIRECTORY = ROOT / "data" / "outcomes" / "scheduler-checkpoints"
WINDOW_HOURS = 24
GRACE_MINUTES = 45
PRIMARY_CN_WEEKDAY_SLOTS = (
    (8, 17),
    (10, 17),
    (12, 17),
    (15, 17),
    (16, 17),
    (20, 17),
    (22, 47),
)
WATCHDOG_CN_WEEKDAY_SLOTS = (
    (8, 47),
    (10, 47),
    (12, 47),
    (15, 47),
    (16, 47),
    (20, 47),
    (23, 17),
)
US_POST_CLOSE_UTC_HOURS = (20, 21)
RECEIPT_FIELDS = {
    "contract_version",
    "receipt_id",
    "receipt_sha256",
    "scheduler_provider",
    "trigger",
    "source_invocation_slot",
    "effective_checkpoint",
    "effective_invocation_slot",
    "scheduler_start_delay_seconds",
    "recovery_mode",
    "snapshot_key",
    "snapshot_sha256",
    "generated_at",
    "workflow_run_id",
    "workflow_run_attempt",
    "workflow_sha",
    "publication_backend",
    "publication_status",
    "published_at",
    "verified_at",
    "verification_method",
}


class SchedulerReceiptError(ValueError):
    """Raised when scheduler evidence is malformed or conflicts."""


def _moment(value: object, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise SchedulerReceiptError(f"{field} must be a timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SchedulerReceiptError(f"{field} must be a timezone-aware ISO timestamp")
    return parsed


def _iso(value: dt.datetime) -> str:
    return value.isoformat(timespec="seconds")


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _receipt_digest(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("receipt_sha256", None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def receipt_id(workflow_run_id: str | int, workflow_run_attempt: int) -> str:
    run_id = str(workflow_run_id).strip()
    if not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise SchedulerReceiptError("workflow_run_id must be a positive integer string")
    if not isinstance(workflow_run_attempt, int) or isinstance(workflow_run_attempt, bool) or workflow_run_attempt < 1:
        raise SchedulerReceiptError("workflow_run_attempt must be a positive integer")
    return f"ghrun_{run_id}_{workflow_run_attempt}"


def receipt_filename(payload: Mapping[str, Any]) -> str:
    expected = receipt_id(payload.get("workflow_run_id", ""), payload.get("workflow_run_attempt"))
    return f"{expected}.json"


def _new_york_hour(value: dt.datetime) -> int:
    return value.astimezone(NY_TZ).hour


def _is_primary_checkpoint(value: dt.datetime) -> bool:
    local = value.astimezone(CN_TZ)
    if (
        local.second == 0
        and local.microsecond == 0
        and local.weekday() < 5
        and (local.hour, local.minute) in PRIMARY_CN_WEEKDAY_SLOTS
    ):
        return True
    utc = value.astimezone(dt.timezone.utc)
    return bool(
        utc.second == 0
        and utc.microsecond == 0
        and utc.weekday() < 5
        and utc.minute == 17
        and utc.hour in US_POST_CLOSE_UTC_HOURS
        and _new_york_hour(utc) == 16
    )


def _is_configured_invocation(value: dt.datetime) -> bool:
    local = value.astimezone(CN_TZ)
    if (
        local.second == 0
        and local.microsecond == 0
        and local.weekday() < 5
        and (local.hour, local.minute)
        in {*PRIMARY_CN_WEEKDAY_SLOTS, *WATCHDOG_CN_WEEKDAY_SLOTS}
    ):
        return True
    utc = value.astimezone(dt.timezone.utc)
    return bool(
        utc.second == 0
        and utc.microsecond == 0
        and utc.weekday() < 5
        and utc.minute in {17, 47}
        and utc.hour in US_POST_CLOSE_UTC_HOURS
        and _new_york_hour(utc) == 16
    )


def validate_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise SchedulerReceiptError("scheduler receipt must be a JSON object")
    row = dict(payload)
    if set(row) != RECEIPT_FIELDS:
        missing = sorted(RECEIPT_FIELDS - set(row))
        unknown = sorted(set(row) - RECEIPT_FIELDS)
        raise SchedulerReceiptError(f"scheduler receipt fields differ: missing={missing} unknown={unknown}")
    if row["contract_version"] != RECEIPT_CONTRACT:
        raise SchedulerReceiptError("scheduler receipt contract_version is invalid")
    expected_id = receipt_id(row["workflow_run_id"], row["workflow_run_attempt"])
    if row["receipt_id"] != expected_id:
        raise SchedulerReceiptError("scheduler receipt_id does not match workflow identity")
    if row["scheduler_provider"] != "github_actions" or row["trigger"] != "schedule":
        raise SchedulerReceiptError("scheduler receipt must represent a GitHub Actions schedule")
    if row["verification_method"] != "complete_deployment_contract_v1":
        raise SchedulerReceiptError("scheduler receipt verification_method is invalid")
    if row["publication_backend"] not in {"embedded", "r2"}:
        raise SchedulerReceiptError("scheduler receipt publication_backend is invalid")
    if row["publication_status"] != "PUBLISHED":
        raise SchedulerReceiptError("scheduler receipt publication_status is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", str(row["workflow_sha"] or "")):
        raise SchedulerReceiptError("scheduler receipt workflow_sha is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(row["snapshot_sha256"] or "")):
        raise SchedulerReceiptError("scheduler receipt snapshot_sha256 is invalid")
    snapshot_key = str(row["snapshot_key"] or "")
    if pathlib.PurePosixPath(snapshot_key).name != snapshot_key or not snapshot_key.endswith(".json"):
        raise SchedulerReceiptError("scheduler receipt snapshot_key is unsafe")
    delay = row["scheduler_start_delay_seconds"]
    if not isinstance(delay, int) or isinstance(delay, bool) or delay < 0:
        raise SchedulerReceiptError("scheduler_start_delay_seconds must be a non-negative integer")
    if row["recovery_mode"] not in {"on_time", "late_cron_recovery"}:
        raise SchedulerReceiptError("scheduler receipt recovery_mode is invalid")

    source = _moment(row["source_invocation_slot"], "source_invocation_slot")
    checkpoint = _moment(row["effective_checkpoint"], "effective_checkpoint")
    invocation = _moment(row["effective_invocation_slot"], "effective_invocation_slot")
    generated = _moment(row["generated_at"], "generated_at")
    published = _moment(row["published_at"], "published_at")
    verified = _moment(row["verified_at"], "verified_at")
    if not _is_primary_checkpoint(checkpoint):
        raise SchedulerReceiptError("effective_checkpoint is not a configured primary checkpoint")
    if not _is_configured_invocation(source):
        raise SchedulerReceiptError("source_invocation_slot is not configured")
    if not _is_configured_invocation(invocation):
        raise SchedulerReceiptError("effective_invocation_slot is not configured")
    if invocation < checkpoint:
        raise SchedulerReceiptError("effective_invocation_slot cannot precede effective_checkpoint")
    if generated < checkpoint:
        raise SchedulerReceiptError("generated_at cannot precede effective_checkpoint")
    if published < generated:
        raise SchedulerReceiptError("published_at cannot precede generated_at")
    if verified < published:
        raise SchedulerReceiptError("verified_at cannot precede published_at")
    if row["recovery_mode"] == "on_time" and source != invocation:
        raise SchedulerReceiptError("on-time source invocation must equal effective invocation")
    expected_digest = _receipt_digest(row)
    if row["receipt_sha256"] != expected_digest:
        raise SchedulerReceiptError("scheduler receipt digest is invalid")
    return row


def create_receipt(
    snapshot: Mapping[str, Any],
    *,
    workflow_run_id: str | int,
    workflow_run_attempt: int,
    workflow_sha: str,
    publication_backend: str = "embedded",
    published_at: dt.datetime | str | None = None,
    verified_at: dt.datetime | str | None = None,
) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise SchedulerReceiptError("snapshot must be a JSON object")
    automation = snapshot.get("automation")
    if not isinstance(automation, Mapping) or automation.get("trigger") != "schedule":
        raise SchedulerReceiptError("snapshot is not a scheduled automation result")
    source_health = automation.get("scheduler_health")
    source_health = source_health if isinstance(source_health, Mapping) else {}
    source = source_health.get("source_invocation_slot") or automation.get("source_invocation_slot")
    checkpoint = source_health.get("effective_checkpoint") or automation.get("scheduled_slot")
    invocation = source_health.get("effective_invocation_slot") or automation.get("scheduled_invocation_slot")
    delay = source_health.get("scheduler_start_delay_seconds", automation.get("scheduler_delay_seconds"))
    recovery = source_health.get("recovery_mode") or automation.get("recovery_mode")

    published = (
        published_at
        if isinstance(published_at, dt.datetime)
        else _moment(published_at, "published_at") if published_at is not None
        else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    )
    verified = (
        verified_at
        if isinstance(verified_at, dt.datetime)
        else _moment(verified_at, "verified_at") if verified_at is not None
        else published
    )
    run_attempt = int(workflow_run_attempt)
    row: dict[str, Any] = {
        "contract_version": RECEIPT_CONTRACT,
        "receipt_id": receipt_id(workflow_run_id, run_attempt),
        "receipt_sha256": "",
        "scheduler_provider": "github_actions",
        "trigger": "schedule",
        "source_invocation_slot": _iso(_moment(source, "source_invocation_slot")),
        "effective_checkpoint": _iso(_moment(checkpoint, "effective_checkpoint")),
        "effective_invocation_slot": _iso(_moment(invocation, "effective_invocation_slot")),
        "scheduler_start_delay_seconds": delay,
        "recovery_mode": recovery,
        "snapshot_key": snapshot.get("snapshot_key"),
        "snapshot_sha256": snapshot_sha256(dict(snapshot)),
        "generated_at": _iso(_moment(snapshot.get("generated_at"), "generated_at")),
        "workflow_run_id": str(workflow_run_id),
        "workflow_run_attempt": run_attempt,
        "workflow_sha": str(workflow_sha),
        "publication_backend": publication_backend,
        "publication_status": "PUBLISHED",
        # Publication happened no later than the successful complete verifier.
        # This is intentionally a conservative upper-bound timestamp.
        "published_at": _iso(published),
        "verified_at": _iso(verified),
        "verification_method": "complete_deployment_contract_v1",
    }
    row["receipt_sha256"] = _receipt_digest(row)
    return validate_receipt(row)


def _serialized(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def write_receipt(path: pathlib.Path, payload: Mapping[str, Any]) -> str:
    validated = validate_receipt(payload)
    expected_name = receipt_filename(validated)
    if path.name != expected_name:
        raise SchedulerReceiptError(f"receipt path must end with {expected_name}")
    encoded = _serialized(validated)
    if path.exists():
        if path.read_bytes() != encoded:
            raise SchedulerReceiptError(f"immutable scheduler receipt conflict: {path}")
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return "created"


def read_receipt(path: pathlib.Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SchedulerReceiptError(f"unable to read scheduler receipt: {path}") from exc
    validated = validate_receipt(payload)
    if path.name != receipt_filename(validated):
        raise SchedulerReceiptError(f"scheduler receipt filename does not match identity: {path.name}")
    return validated


def install_receipt(source: pathlib.Path, directory: pathlib.Path) -> tuple[pathlib.Path, str]:
    payload = read_receipt(source)
    target = directory / receipt_filename(payload)
    return target, write_receipt(target, payload)


def load_receipts(directory: pathlib.Path = DEFAULT_DIRECTORY) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    return [read_receipt(path) for path in sorted(directory.glob("*.json"))]


def expected_primary_checkpoints(
    evaluated_at: dt.datetime,
    *,
    window_hours: int = WINDOW_HOURS,
    grace_minutes: int = GRACE_MINUTES,
) -> list[dt.datetime]:
    evaluated = _moment(evaluated_at, "evaluated_at")
    window_start = evaluated - dt.timedelta(hours=window_hours)
    mature_cutoff = evaluated - dt.timedelta(minutes=grace_minutes)
    candidates: set[dt.datetime] = set()

    local_start = window_start.astimezone(CN_TZ).date() - dt.timedelta(days=1)
    local_end = mature_cutoff.astimezone(CN_TZ).date() + dt.timedelta(days=1)
    day = local_start
    while day <= local_end:
        if day.weekday() < 5:
            for hour, minute in PRIMARY_CN_WEEKDAY_SLOTS:
                candidates.add(dt.datetime.combine(day, dt.time(hour, minute), tzinfo=CN_TZ))
        day += dt.timedelta(days=1)

    utc_start = window_start.astimezone(dt.timezone.utc).date() - dt.timedelta(days=1)
    utc_end = mature_cutoff.astimezone(dt.timezone.utc).date() + dt.timedelta(days=1)
    day = utc_start
    while day <= utc_end:
        if day.weekday() < 5:
            for hour in US_POST_CLOSE_UTC_HOURS:
                instant = dt.datetime.combine(day, dt.time(hour, 17), tzinfo=dt.timezone.utc)
                if _new_york_hour(instant) == 16:
                    candidates.add(instant.astimezone(CN_TZ))
        day += dt.timedelta(days=1)

    return sorted(
        checkpoint
        for checkpoint in candidates
        if window_start <= checkpoint <= mature_cutoff
    )


def aggregate_receipts(
    receipts: Iterable[Mapping[str, Any]],
    *,
    evaluated_at: dt.datetime | str | None = None,
    window_hours: int = WINDOW_HOURS,
    grace_minutes: int = GRACE_MINUTES,
) -> dict[str, Any]:
    evaluated = (
        evaluated_at
        if isinstance(evaluated_at, dt.datetime)
        else _moment(evaluated_at, "evaluated_at") if evaluated_at is not None
        else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    )
    validated = [validate_receipt(row) for row in receipts]
    verified_moments = [_moment(row["verified_at"], "verified_at") for row in validated]
    ledger_started = min(verified_moments) if verified_moments else None
    window_start = evaluated - dt.timedelta(hours=window_hours)
    coverage_complete = bool(ledger_started is not None and ledger_started <= window_start)
    expected = expected_primary_checkpoints(
        evaluated,
        window_hours=window_hours,
        grace_minutes=grace_minutes,
    )
    by_checkpoint: dict[dt.datetime, list[dict[str, Any]]] = {}
    for row in validated:
        checkpoint = _moment(row["effective_checkpoint"], "effective_checkpoint").astimezone(CN_TZ)
        by_checkpoint.setdefault(checkpoint, []).append(row)

    rows: list[dict[str, Any]] = []
    on_time = late = missed = 0
    for checkpoint in expected:
        matching = sorted(
            by_checkpoint.get(checkpoint.astimezone(CN_TZ), []),
            key=lambda row: _moment(row["published_at"], "published_at"),
        )
        deadline = checkpoint + dt.timedelta(minutes=grace_minutes)
        if not matching:
            if coverage_complete:
                status = "MISSED"
                missed += 1
            elif ledger_started is None or checkpoint < ledger_started:
                status = "UNOBSERVED_BEFORE_LEDGER"
            else:
                status = "UNKNOWN_WINDOW_INCOMPLETE"
            rows.append(
                {
                    "checkpoint": _iso(checkpoint),
                    "deadline": _iso(deadline),
                    "status": status,
                    "receipt_id": None,
                    "published_at": None,
                    "publication_delay_seconds": None,
                }
            )
            continue
        selected = matching[0]
        published = _moment(selected["published_at"], "published_at")
        delay_seconds = max(0, int((published - checkpoint).total_seconds()))
        status = "ON_TIME" if published <= deadline else "LATE_RECOVERY"
        if status == "ON_TIME":
            on_time += 1
        else:
            late += 1
        rows.append(
            {
                "checkpoint": _iso(checkpoint),
                "deadline": _iso(deadline),
                "status": status,
                "receipt_id": selected["receipt_id"],
                "published_at": selected["published_at"],
                "publication_delay_seconds": delay_seconds,
            }
        )

    readiness = (
        "INITIALIZING"
        if not coverage_complete
        else "READY" if missed == 0 and late == 0 else "DEGRADED"
    )
    return {
        "contract_version": LEDGER_CONTRACT,
        "slo": {
            "contract_version": SLO_CONTRACT,
            "guaranteed": False,
            "public_data_source_sla": False,
            "target_publication_within_minutes": grace_minutes,
            "coverage_window_hours": window_hours,
        },
        "evaluated_at": _iso(evaluated),
        "ledger_started_at": _iso(ledger_started) if ledger_started else None,
        "coverage_complete_24h": coverage_complete,
        "checkpoint_coverage_status": (
            "COMPLETE_24H_LEDGER" if coverage_complete else "INITIALIZING_24H_LEDGER"
        ),
        "readiness": readiness,
        "expected_checkpoints_24h": len(expected),
        "published_on_time_24h": on_time,
        "late_recoveries_24h": late,
        "missed_checkpoints_24h": missed if coverage_complete else None,
        "receipt_count": len(validated),
        "evidence_lag_batches": 1,
        "evidence_lag_reason": "RECEIPT_PERSISTED_AFTER_VERIFIED_DEPLOYMENT",
        "checkpoints": rows,
    }


def _load_json_object(path: pathlib.Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SchedulerReceiptError(f"unable to read JSON object: {path}") from exc
    if not isinstance(payload, dict):
        raise SchedulerReceiptError(f"JSON object required: {path}")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create one verified scheduler receipt")
    create.add_argument("--snapshot", type=pathlib.Path, required=True)
    create.add_argument("--output", type=pathlib.Path, required=True)
    create.add_argument("--workflow-run-id", required=True)
    create.add_argument("--workflow-run-attempt", type=int, required=True)
    create.add_argument("--workflow-sha", required=True)
    create.add_argument("--publication-backend", choices=("embedded", "r2"), default="embedded")
    create.add_argument("--published-at")

    validate = commands.add_parser("validate", help="validate one immutable receipt")
    validate.add_argument("receipt", type=pathlib.Path)

    install = commands.add_parser("install", help="idempotently install one receipt")
    install.add_argument("receipt", type=pathlib.Path)
    install.add_argument("--directory", type=pathlib.Path, default=DEFAULT_DIRECTORY)

    aggregate = commands.add_parser("aggregate", help="build a trailing scheduler SLO ledger")
    aggregate.add_argument("--directory", type=pathlib.Path, default=DEFAULT_DIRECTORY)
    aggregate.add_argument("--output", type=pathlib.Path)
    aggregate.add_argument("--evaluated-at")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "create":
        snapshot = _load_json_object(args.snapshot)
        payload = create_receipt(
            snapshot,
            workflow_run_id=args.workflow_run_id,
            workflow_run_attempt=args.workflow_run_attempt,
            workflow_sha=args.workflow_sha,
            publication_backend=args.publication_backend,
            published_at=args.published_at,
        )
        status = write_receipt(args.output, payload)
        print(json.dumps({"status": status, "receipt": str(args.output), "receipt_id": payload["receipt_id"]}))
        return 0
    if args.command == "validate":
        payload = read_receipt(args.receipt)
        print(json.dumps({"valid": True, "receipt_id": payload["receipt_id"]}))
        return 0
    if args.command == "install":
        target, status = install_receipt(args.receipt, args.directory)
        print(json.dumps({"status": status, "receipt": str(target)}))
        return 0
    if args.command == "aggregate":
        payload = aggregate_receipts(
            load_receipts(args.directory),
            evaluated_at=args.evaluated_at,
        )
        encoded = _serialized(payload)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(encoded)
        else:
            sys.stdout.buffer.write(encoded)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SchedulerReceiptError as exc:
        raise SystemExit(str(exc)) from exc

"""Deterministic, settlement-free ledger for all ten-day model observations.

The observation track is deliberately independent from both the selected
``SHADOW_RESEARCH`` track and the formal ``EXECUTABLE_MODEL`` track.  A model
prediction is observable even when its quality gate is rejected, its expected
utility is negative, or it is not eligible to rank.  Nothing in this module can
promote an observation into an executable decision.

One cohort represents the scheduled Beijing 22:47 sample.  A 23:17 health
recovery inherits the same ``scheduled_slot`` and is retained as a later
revision of that cohort.  This module only freezes predictions and summaries;
network outcome settlement belongs to a separate integration layer.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any
from zoneinfo import ZoneInfo


TRACK = "MODEL_OBSERVATION"
SHADOW_TRACK = "SHADOW_RESEARCH"
EXECUTABLE_TRACK = "EXECUTABLE_MODEL"
REVISION_SCHEMA_VERSION = "model-observation-revision-v1"
COHORT_SCHEMA_VERSION = "model-observation-cohort-v1"
SUMMARY_SCHEMA_VERSION = "model-observation-summary-v1"
SAMPLING_POLICY = "daily_2247_all_shadow_predictions_v1"
CN_TZ = ZoneInfo("Asia/Shanghai")
DAILY_SLOT = (22, 47)
MAX_REVISION_DELAY = dt.timedelta(hours=4)
VALID_MARKETS = ("a_share", "hk", "us")
VALID_ARTIFACT = re.compile(r"^[a-f0-9]{64}$")
VALID_SAFE_SNAPSHOT = re.compile(r"^[A-Za-z0-9_.-]+\.json$")
VALID_OBSERVATION_ID = re.compile(r"^obs_[a-f0-9]{24}$")
VALID_COHORT_ID = re.compile(r"^obscohort_[a-f0-9]{24}$")
DEFAULT_OBSERVATION_DIRECTORY = pathlib.Path(__file__).resolve().parent / "data" / "outcomes" / "observations"


class ObservationContractError(ValueError):
    """The source snapshot does not satisfy the observation contract."""


class ObservationConflictError(RuntimeError):
    """Two records claim the same immutable identity with different payloads."""


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _aware_moment(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ObservationContractError(f"{field} must be a timezone-aware ISO timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ObservationContractError(f"{field} must be a timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ObservationContractError(f"{field} must be a timezone-aware ISO timestamp")
    return parsed


def _iso_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ObservationContractError(f"{field} must be an ISO date")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ObservationContractError(f"{field} must be an ISO date") from exc
    return parsed.isoformat()


def _digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    identity = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def _canonical_snapshot_name(snapshot: Mapping[str, Any], explicit: str | None) -> str:
    candidate = snapshot.get("snapshot_key") or explicit
    if not isinstance(candidate, str) or not VALID_SAFE_SNAPSHOT.fullmatch(candidate):
        raise ObservationContractError("source_snapshot must be a safe immutable JSON filename")
    if pathlib.PurePosixPath(candidate).name != candidate:
        raise ObservationContractError("source_snapshot must not contain a path")
    return candidate


def _scheduled_slot(snapshot: Mapping[str, Any]) -> tuple[dt.datetime, dt.datetime]:
    automation = snapshot.get("automation")
    if not isinstance(automation, Mapping) or automation.get("trigger") != "schedule":
        raise ObservationContractError("MODEL_OBSERVATION only admits scheduled snapshots")
    scheduled = _aware_moment(automation.get("scheduled_slot"), "automation.scheduled_slot")
    local_slot = scheduled.astimezone(CN_TZ)
    if (local_slot.hour, local_slot.minute) != DAILY_SLOT:
        raise ObservationContractError("MODEL_OBSERVATION only admits the Beijing 22:47 daily slot")
    generated = _aware_moment(snapshot.get("generated_at"), "generated_at")
    delay = generated.astimezone(dt.timezone.utc) - scheduled.astimezone(dt.timezone.utc)
    if delay < dt.timedelta(0) or delay > MAX_REVISION_DELAY:
        raise ObservationContractError("generated_at is outside the allowed same-slot revision window")
    return scheduled, generated


def _global_contract(snapshot: Mapping[str, Any]) -> None:
    decision = snapshot.get("global_decision")
    if not isinstance(decision, Mapping) or (
        decision.get("contract_version") != "global-10d-v1"
        or decision.get("decision_scope") != "global_10d"
        or decision.get("action_basis") != "strict_cross_market_gate_v1"
    ):
        raise ObservationContractError("global ten-day decision contract is missing")


def _prediction_record(
    prediction: Mapping[str, Any],
    *,
    scheduled_slot: str,
    source_snapshot: str,
    model: Mapping[str, Any],
) -> dict[str, Any]:
    declared_track = prediction.get("track")
    if declared_track not in (None, "", TRACK):
        raise ObservationContractError(f"prediction track {declared_track!r} cannot enter {TRACK}")

    market = prediction.get("market")
    code = prediction.get("code")
    model_id = prediction.get("model_id")
    label_version = prediction.get("label_version")
    if market not in VALID_MARKETS:
        raise ObservationContractError("prediction.market is invalid")
    if not isinstance(code, str) or not code.strip():
        raise ObservationContractError("prediction.code is missing")
    if not isinstance(model_id, str) or not model_id:
        raise ObservationContractError("prediction.model_id is missing")
    if not isinstance(label_version, str) or not label_version:
        raise ObservationContractError("prediction.label_version is missing")
    if model.get("model_id") not in (None, model_id) or model.get("label_version") not in (None, label_version):
        raise ObservationContractError("prediction model identity does not match the model card")

    artifact = prediction.get("artifact_sha256")
    if not isinstance(artifact, str) or VALID_ARTIFACT.fullmatch(artifact.lower()) is None:
        raise ObservationContractError("prediction.artifact_sha256 is invalid")
    training_cutoff = _iso_date(prediction.get("training_cutoff"), "prediction.training_cutoff")
    prediction_as_of = _iso_date(prediction.get("prediction_as_of"), "prediction.prediction_as_of")
    if training_cutoff > prediction_as_of:
        raise ObservationContractError("training_cutoff cannot be after prediction_as_of")

    probability = prediction.get("probability")
    expected_return = prediction.get("expected_net_return")
    expected_utility = prediction.get("expected_net_utility")
    transaction_cost = prediction.get("transaction_cost")
    tail_risk = prediction.get("tail_risk")
    if not _finite(probability) or not 0.0 <= float(probability) <= 1.0:
        raise ObservationContractError("prediction.probability is invalid")
    for field, value in (
        ("expected_net_return", expected_return),
        ("expected_net_utility", expected_utility),
    ):
        if not _finite(value):
            raise ObservationContractError(f"prediction.{field} is invalid")
    for field, value in (("transaction_cost", transaction_cost), ("tail_risk", tail_risk)):
        if not _finite(value) or float(value) < 0.0:
            raise ObservationContractError(f"prediction.{field} is invalid")
    if prediction.get("participates_in_decision") is not False:
        raise ObservationContractError("observed Shadow prediction must not participate in decision")
    if prediction.get("production_eligible") is not False:
        raise ObservationContractError("observed Shadow prediction must not be production eligible")

    observation_id = _stable_id(
        "obs",
        scheduled_slot,
        market,
        code.strip(),
        model_id,
        label_version,
    )
    record = {
        "schema_version": REVISION_SCHEMA_VERSION,
        "track": TRACK,
        "observation_id": observation_id,
        "source_prediction_id": prediction.get("prediction_id"),
        "source_snapshot": source_snapshot,
        "scheduled_slot": scheduled_slot,
        "market": market,
        "code": code.strip(),
        "model_id": model_id,
        "label_version": label_version,
        "feature_schema_version": prediction.get("feature_schema_version")
        or model.get("feature_schema_version"),
        "artifact_sha256": artifact.lower(),
        "training_cutoff": training_cutoff,
        "fit_data_cutoff": prediction.get("fit_data_cutoff"),
        "prediction_as_of": prediction_as_of,
        "probability": float(probability),
        "expected_net_return": float(expected_return),
        "expected_net_utility": float(expected_utility),
        "transaction_cost": float(transaction_cost),
        "tail_risk": float(tail_risk),
        "market_validation_status": prediction.get("market_validation_status"),
        "rank_eligible": prediction.get("rank_eligible") is True,
        "participates_in_decision": False,
        "production_eligible": False,
        "included_in_shadow_research": False,
        "included_in_executable_performance": False,
    }
    record["prediction_sha256"] = _digest(
        {key: value for key, value in record.items() if key not in {"source_snapshot", "prediction_sha256"}}
    )
    return record


def build_observation_revision(
    snapshot: Mapping[str, Any],
    source_name: str | None = None,
) -> dict[str, Any]:
    """Freeze all Shadow predictions from one eligible scheduled snapshot.

    ``rank_eligible`` is intentionally not an admission condition.  Invalid
    prediction shapes fail the whole revision closed so coverage cannot appear
    healthier than the actual persisted payload.
    """

    if not isinstance(snapshot, Mapping):
        raise ObservationContractError("snapshot must be an object")
    scheduled, generated = _scheduled_slot(snapshot)
    _global_contract(snapshot)
    source_snapshot = _canonical_snapshot_name(snapshot, source_name)
    model = ((snapshot.get("analysis_models") or {}).get("ten_day_return") or {})
    if not isinstance(model, Mapping):
        raise ObservationContractError("analysis_models.ten_day_return must be an object")
    predictions = model.get("shadow_predictions")
    if not isinstance(predictions, list):
        raise ObservationContractError("shadow_predictions must be a list")

    slot_iso = scheduled.astimezone(CN_TZ).isoformat(timespec="minutes")
    records: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    for raw_prediction in predictions:
        if not isinstance(raw_prediction, Mapping):
            raise ObservationContractError("every shadow prediction must be an object")
        record = _prediction_record(
            raw_prediction,
            scheduled_slot=slot_iso,
            source_snapshot=source_snapshot,
            model=model,
        )
        key = (str(record["market"]), str(record["code"]))
        if key in seen_keys or record["observation_id"] in seen_ids:
            raise ObservationConflictError(f"duplicate prediction identity in one revision: {key}")
        seen_keys.add(key)
        seen_ids.add(str(record["observation_id"]))
        records.append(record)
    records.sort(key=lambda item: (VALID_MARKETS.index(str(item["market"])), str(item["code"])))

    revision_identity = {
        "scheduled_slot": slot_iso,
        "generated_at": generated.isoformat(timespec="seconds"),
        "source_snapshot": source_snapshot,
    }
    revision_id = _stable_id("obsrev", *revision_identity.values())
    market_counts = Counter(str(item["market"]) for item in records)
    revision = {
        "schema_version": REVISION_SCHEMA_VERSION,
        "track": TRACK,
        "sampling_policy": SAMPLING_POLICY,
        "cohort_id": _stable_id("obscohort", slot_iso),
        "revision_id": revision_id,
        "scheduled_slot": slot_iso,
        "generated_at": generated.isoformat(timespec="seconds"),
        "source_snapshot": source_snapshot,
        "model_id": model.get("model_id"),
        "label_version": model.get("label_version"),
        "model_status": model.get("status"),
        "model_artifact_sha256": model.get("artifact_sha256"),
        "prediction_count": len(records),
        "market_prediction_counts": {market: market_counts.get(market, 0) for market in VALID_MARKETS},
        "predictions": records,
        "included_in_shadow_research": False,
        "included_in_executable_performance": False,
    }
    revision["revision_sha256"] = _digest(
        {key: value for key, value in revision.items() if key != "revision_sha256"}
    )
    return revision


def _iter_snapshots(
    snapshots: Mapping[str, Mapping[str, Any]] | Iterable[tuple[str, Mapping[str, Any]]],
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    return snapshots.items() if isinstance(snapshots, Mapping) else snapshots


def _cohort_from_revisions(revisions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    unique: dict[str, dict[str, Any]] = {}
    moments: dict[str, str] = {}
    cohort_id: str | None = None
    for raw_revision in revisions:
        if not isinstance(raw_revision, Mapping):
            raise ObservationContractError("observation revision must be an object")
        revision = dict(raw_revision)
        if revision.get("schema_version") != REVISION_SCHEMA_VERSION or revision.get("track") != TRACK:
            raise ObservationContractError("observation revision belongs to another schema or track")
        current_cohort_id = revision.get("cohort_id")
        revision_id = revision.get("revision_id")
        if not isinstance(current_cohort_id, str) or VALID_COHORT_ID.fullmatch(current_cohort_id) is None:
            raise ObservationContractError("observation cohort_id is invalid")
        if not isinstance(revision_id, str) or not revision_id.startswith("obsrev_"):
            raise ObservationContractError("observation revision_id is invalid")
        if cohort_id is None:
            cohort_id = current_cohort_id
        elif current_cohort_id != cohort_id:
            raise ObservationConflictError("revisions from different daily cohorts cannot be merged")
        expected_digest = _digest(
            {key: value for key, value in revision.items() if key != "revision_sha256"}
        )
        if revision.get("revision_sha256") != expected_digest:
            raise ObservationConflictError(f"revision digest mismatch: {revision_id}")
        existing = unique.get(revision_id)
        if existing is not None and existing != revision:
            raise ObservationConflictError(f"conflicting payload for revision {revision_id}")
        generated_at = str(revision.get("generated_at") or "")
        existing_moment = moments.get(generated_at)
        if existing_moment is not None and existing_moment != expected_digest:
            raise ObservationConflictError(
                f"ambiguous same-moment revisions in cohort {cohort_id}: {generated_at}"
            )
        moments[generated_at] = expected_digest
        unique[revision_id] = revision
    if not unique or cohort_id is None:
        raise ObservationContractError("observation cohort requires at least one revision")

    ordered = sorted(
        unique.values(),
        key=lambda item: (str(item["generated_at"]), str(item["revision_id"])),
    )
    canonical = ordered[-1]
    cohort = {
        "schema_version": COHORT_SCHEMA_VERSION,
        "track": TRACK,
        "sampling_policy": SAMPLING_POLICY,
        "cohort_id": cohort_id,
        "scheduled_slot": canonical["scheduled_slot"],
        "revision_count": len(ordered),
        "canonical_revision_id": canonical["revision_id"],
        "canonical_source_snapshot": canonical["source_snapshot"],
        "canonical_generated_at": canonical["generated_at"],
        "prediction_count": canonical["prediction_count"],
        "market_prediction_counts": canonical["market_prediction_counts"],
        "revisions": ordered,
        "included_in_shadow_research": False,
        "included_in_executable_performance": False,
    }
    cohort["cohort_sha256"] = _digest(
        {key: value for key, value in cohort.items() if key != "cohort_sha256"}
    )
    return cohort


def _atomic_write_json(path: pathlib.Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(rendered)
        temporary = pathlib.Path(handle.name)
    temporary.replace(path)


def record_observation_revision(
    snapshot: Mapping[str, Any],
    source_name: str | None = None,
    directory: pathlib.Path = DEFAULT_OBSERVATION_DIRECTORY,
) -> dict[str, Any]:
    """Atomically create or extend one daily observation cohort on disk."""

    revision = build_observation_revision(snapshot, source_name)
    cohort_id = str(revision["cohort_id"])
    if VALID_COHORT_ID.fullmatch(cohort_id) is None:
        raise ObservationContractError("refusing unsafe observation cohort filename")
    target = pathlib.Path(directory) / f"{cohort_id}.json"
    existing: dict[str, Any] | None = None
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ObservationConflictError(f"existing observation cohort is unreadable: {target.name}") from exc
        if not isinstance(loaded, dict):
            raise ObservationConflictError(f"existing observation cohort is not an object: {target.name}")
        existing = loaded
        if (
            existing.get("schema_version") != COHORT_SCHEMA_VERSION
            or existing.get("track") != TRACK
            or existing.get("cohort_id") != cohort_id
            or existing.get("included_in_shadow_research") is not False
            or existing.get("included_in_executable_performance") is not False
        ):
            raise ObservationConflictError(f"existing observation cohort identity conflict: {target.name}")
        stored_digest = existing.get("cohort_sha256")
        expected_digest = _digest(
            {key: value for key, value in existing.items() if key != "cohort_sha256"}
        )
        if stored_digest != expected_digest:
            raise ObservationConflictError(f"existing observation cohort digest mismatch: {target.name}")
    cohort = _cohort_from_revisions([*((existing or {}).get("revisions") or []), revision])
    changed = existing != cohort
    if changed:
        _atomic_write_json(target, cohort)
    return {
        "path": target,
        "created": existing is None,
        "changed": changed,
        "cohort": cohort,
    }


def load_observation_cohorts(
    directory: pathlib.Path = DEFAULT_OBSERVATION_DIRECTORY,
) -> dict[str, dict[str, Any]]:
    """Load and fully validate persisted observation cohorts."""

    root = pathlib.Path(directory)
    if not root.is_dir():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        if VALID_COHORT_ID.fullmatch(path.stem) is None:
            raise ObservationConflictError(f"unsafe observation cohort filename: {path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ObservationConflictError(f"observation cohort is unreadable: {path.name}") from exc
        if not isinstance(payload, dict) or payload.get("cohort_id") != path.stem:
            raise ObservationConflictError(f"observation cohort filename identity mismatch: {path.name}")
        rebuilt = _cohort_from_revisions(payload.get("revisions") or [])
        if payload != rebuilt:
            raise ObservationConflictError(f"observation cohort payload conflict: {path.name}")
        result[path.stem] = rebuilt
    return result


def build_observation_cohorts(
    snapshots: Mapping[str, Mapping[str, Any]] | Iterable[tuple[str, Mapping[str, Any]]],
    *,
    skip_ineligible_snapshots: bool = True,
) -> dict[str, dict[str, Any]]:
    """Group 22:47 samples and their inherited-slot recoveries into cohorts."""

    revisions_by_cohort: dict[str, list[dict[str, Any]]] = {}
    for source_name, snapshot in _iter_snapshots(snapshots):
        try:
            revision = build_observation_revision(snapshot, source_name)
        except ObservationContractError:
            if skip_ineligible_snapshots:
                continue
            raise
        cohort_id = str(revision["cohort_id"])
        revisions_by_cohort.setdefault(cohort_id, []).append(revision)

    cohorts: dict[str, dict[str, Any]] = {}
    for cohort_id, revisions in revisions_by_cohort.items():
        cohort = _cohort_from_revisions(revisions)
        if cohort["cohort_id"] != cohort_id:
            raise ObservationConflictError("derived cohort identity mismatch")
        cohorts[cohort_id] = cohort
    return dict(sorted(cohorts.items(), key=lambda item: str(item[1]["scheduled_slot"])))


def summarize_observation_cohorts(
    cohorts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a compact manifest-safe summary of canonical observations."""

    canonical_prediction_count = 0
    revision_count = 0
    market_counts: Counter[str] = Counter()
    model_status_counts: Counter[str] = Counter()
    for cohort_id, cohort in cohorts.items():
        if not isinstance(cohort, Mapping) or cohort.get("track") != TRACK:
            raise ObservationContractError(f"cohort {cohort_id!r} belongs to another ledger track")
        if cohort.get("included_in_shadow_research") is not False:
            raise ObservationContractError("MODEL_OBSERVATION cannot enter SHADOW_RESEARCH")
        if cohort.get("included_in_executable_performance") is not False:
            raise ObservationContractError("MODEL_OBSERVATION cannot enter executable performance")
        rebuilt = _cohort_from_revisions(cohort.get("revisions") or [])
        if dict(cohort) != rebuilt or rebuilt.get("cohort_id") != cohort_id:
            raise ObservationConflictError(f"cohort {cohort_id!r} failed immutable validation")
        canonical_prediction_count += int(cohort.get("prediction_count") or 0)
        revision_count += int(cohort.get("revision_count") or 0)
        for market, count in (cohort.get("market_prediction_counts") or {}).items():
            if market in VALID_MARKETS:
                market_counts[market] += int(count or 0)
        revisions = cohort.get("revisions") or []
        canonical_id = cohort.get("canonical_revision_id")
        canonical = next(
            (revision for revision in revisions if revision.get("revision_id") == canonical_id),
            None,
        )
        if canonical is None:
            raise ObservationContractError(f"cohort {cohort_id!r} has no canonical revision")
        model_status_counts[str(canonical.get("model_status") or "UNKNOWN")] += 1

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "track": TRACK,
        "sampling_policy": SAMPLING_POLICY,
        "status": "NO_SAMPLE" if not cohorts else "OBSERVING",
        "cohort_count": len(cohorts),
        "revision_count": revision_count,
        "canonical_prediction_count": canonical_prediction_count,
        "market_prediction_counts": {market: market_counts.get(market, 0) for market in VALID_MARKETS},
        "model_status_counts": dict(sorted(model_status_counts.items())),
        "included_in_shadow_research": False,
        "included_in_executable_performance": False,
        "settlement_status": "NOT_IMPLEMENTED",
    }


__all__ = [
    "COHORT_SCHEMA_VERSION",
    "DEFAULT_OBSERVATION_DIRECTORY",
    "EXECUTABLE_TRACK",
    "ObservationConflictError",
    "ObservationContractError",
    "REVISION_SCHEMA_VERSION",
    "SAMPLING_POLICY",
    "SHADOW_TRACK",
    "SUMMARY_SCHEMA_VERSION",
    "TRACK",
    "build_observation_cohorts",
    "build_observation_revision",
    "load_observation_cohorts",
    "record_observation_revision",
    "summarize_observation_cohorts",
]

"""Deterministic prospective ledger for all ten-day model observations.

The observation track is deliberately independent from both the selected
``SHADOW_RESEARCH`` track and the formal ``EXECUTABLE_MODEL`` track.  A model
prediction is observable even when its quality gate is rejected, its expected
utility is negative, or it is not eligible to rank.  Nothing in this module can
promote an observation into an executable decision.

One cohort represents the scheduled Beijing 22:47 sample.  A 23:17 health
recovery inherits the same ``scheduled_slot`` and is retained as a later
revision of that cohort.  This module freezes the exchange-calendar settlement
contract; network outcome settlement belongs to a separate integration layer.
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

import market_calendar


TRACK = "MODEL_OBSERVATION"
SHADOW_TRACK = "SHADOW_RESEARCH"
EXECUTABLE_TRACK = "EXECUTABLE_MODEL"
LEGACY_REVISION_SCHEMA_VERSION = "model-observation-revision-v1"
REVISION_SCHEMA_VERSION = "model-observation-revision-v2"
COHORT_SCHEMA_VERSION = "model-observation-cohort-v1"
SUMMARY_SCHEMA_VERSION = "model-observation-summary-v1"
SAMPLING_POLICY = "daily_2247_all_shadow_predictions_v1"
SOURCE_SNAPSHOT_HASH_CONTRACT = "canonical-json-sha256-v1"
CN_TZ = ZoneInfo("Asia/Shanghai")
DAILY_SLOT = (22, 47)
MAX_REVISION_DELAY = dt.timedelta(hours=4)
VALID_MARKETS = ("a_share", "hk", "us")
VALID_ARTIFACT = re.compile(r"^[a-f0-9]{64}$")
VALID_SAFE_SNAPSHOT = re.compile(r"^[A-Za-z0-9_.-]+\.json$")
VALID_OBSERVATION_ID = re.compile(r"^obs_[a-f0-9]{24}$")
VALID_COHORT_ID = re.compile(r"^obscohort_[a-f0-9]{24}$")
VALID_REVISION_ID = re.compile(r"^obsrev_[a-f0-9]{24}$")
DEFAULT_OBSERVATION_DIRECTORY = pathlib.Path(__file__).resolve().parent / "data" / "outcomes" / "observations"
CURRENCIES = {"a_share": "CNY", "hk": "HKD", "us": "USD"}
SETTLEMENT_CONTRACT_FIELDS = (
    "observation_id",
    "prediction_sha256",
    "market",
    "code",
    "model_id",
    "label_version",
    "entry_trade_date",
    "entry_session_open_at",
    "forecast_end_trade_date",
    "forecast_end_session_close_at",
    "horizon_trade_sessions",
    "entry_policy",
    "exit_policy",
    "calendar_id",
    "calendar_version",
    "currency",
    "transaction_cost",
)
PREDICTION_SHA256_FIELDS = (
    "schema_version",
    "track",
    "observation_id",
    "source_prediction_id",
    "scheduled_slot",
    "market",
    "code",
    "model_id",
    "label_version",
    "feature_schema_version",
    "artifact_sha256",
    "training_cutoff",
    "fit_data_cutoff",
    "prediction_as_of",
    "probability",
    "expected_net_return",
    "expected_net_utility",
    "transaction_cost",
    "tail_risk",
    "market_validation_status",
    "rank_eligible",
    "participates_in_decision",
    "production_eligible",
    "included_in_shadow_research",
    "included_in_executable_performance",
)
PREDICTION_SETTLEMENT_DERIVED_FIELDS = (
    "entry_trade_date",
    "entry_session_open_at",
    "forecast_end_trade_date",
    "forecast_end_session_close_at",
    "horizon_trade_sessions",
    "entry_policy",
    "exit_policy",
    "calendar_id",
    "calendar_version",
    "currency",
    "settlement_contract_sha256",
)
PREDICTION_BASE_FIELDS = frozenset(
    (*PREDICTION_SHA256_FIELDS, "source_snapshot", "prediction_sha256")
)
PREDICTION_CURRENT_FIELDS = frozenset(
    (*PREDICTION_BASE_FIELDS, *PREDICTION_SETTLEMENT_DERIVED_FIELDS)
)
LEGACY_REVISION_FIELDS = frozenset(
    {
        "schema_version",
        "track",
        "sampling_policy",
        "cohort_id",
        "revision_id",
        "scheduled_slot",
        "generated_at",
        "source_snapshot",
        "model_id",
        "label_version",
        "model_status",
        "model_artifact_sha256",
        "prediction_count",
        "market_prediction_counts",
        "predictions",
        "included_in_shadow_research",
        "included_in_executable_performance",
        "revision_sha256",
    }
)
REVISION_FIELDS = frozenset(
    {
        *LEGACY_REVISION_FIELDS,
        "source_snapshot_hash_contract",
        "source_snapshot_sha256",
        "source_snapshot_byte_size",
        "feature_cutoff_at",
    }
)
COHORT_FIELDS = frozenset(
    {
        "schema_version",
        "track",
        "sampling_policy",
        "cohort_id",
        "scheduled_slot",
        "revision_count",
        "canonical_revision_id",
        "canonical_source_snapshot",
        "canonical_generated_at",
        "prediction_count",
        "market_prediction_counts",
        "revisions",
        "included_in_shadow_research",
        "included_in_executable_performance",
        "cohort_sha256",
    }
)


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


def source_snapshot_identity(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return the deterministic content identity frozen by revision v2.

    JSON is canonicalized before hashing so formatting-only rewrites do not
    invalidate a historical feature sample, while every semantic value used by
    the point-in-time join remains bound to the revision.
    """

    if not isinstance(snapshot, Mapping):
        raise ObservationContractError("source snapshot must be an object")
    try:
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ObservationContractError("source snapshot is not canonical JSON") from exc
    return {
        "source_snapshot_hash_contract": SOURCE_SNAPSHOT_HASH_CONTRACT,
        "source_snapshot_sha256": hashlib.sha256(encoded).hexdigest(),
        "source_snapshot_byte_size": len(encoded),
    }


def _stable_id(prefix: str, *parts: Any) -> str:
    identity = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def settlement_contract_sha256(record: Mapping[str, Any]) -> str:
    """Return the immutable ten-session settlement-contract digest."""

    missing = [field for field in SETTLEMENT_CONTRACT_FIELDS if record.get(field) is None]
    if missing:
        raise ObservationContractError(
            "observation settlement contract is incomplete: " + ",".join(missing)
        )
    if record.get("horizon_trade_sessions") != 10:
        raise ObservationContractError("observation settlement horizon must be ten sessions")
    if record.get("entry_policy") != "next_session_open_v1":
        raise ObservationContractError("observation entry policy is invalid")
    if record.get("exit_policy") != "tenth_session_close_v1":
        raise ObservationContractError("observation exit policy is invalid")
    return _digest({field: record.get(field) for field in SETTLEMENT_CONTRACT_FIELDS})


def prediction_sha256(record: Mapping[str, Any]) -> str:
    """Hash the immutable model output before derived settlement fields.

    ``source_snapshot`` is deliberately excluded so ``latest.json`` and its
    immutable filename have the same prediction identity.  Settlement calendar
    fields are derived later from ``generated_at`` and have their own digest.
    An explicit allow-list prevents a newly introduced, unhashed field from
    silently becoming part of the persisted prediction contract.
    """

    missing = [field for field in PREDICTION_SHA256_FIELDS if field not in record]
    if missing:
        raise ObservationContractError(
            "observation prediction hash fields are incomplete: " + ",".join(missing)
        )
    return _digest({field: record.get(field) for field in PREDICTION_SHA256_FIELDS})


def _settlement_contract_fields(
    record: Mapping[str, Any],
    generated_at: dt.datetime | str,
) -> dict[str, Any]:
    market = str(record.get("market") or "")
    if market not in VALID_MARKETS:
        raise ObservationContractError("observation settlement market is invalid")
    window = market_calendar.market_trade_window(market, generated_at, horizon_sessions=10)
    return {
        "entry_trade_date": window["entry_trade_date"],
        "entry_session_open_at": window["entry_session_open_at"],
        "forecast_end_trade_date": window["forecast_end_trade_date"],
        "forecast_end_session_close_at": window["forecast_end_session_close_at"],
        "horizon_trade_sessions": 10,
        "entry_policy": "next_session_open_v1",
        "exit_policy": "tenth_session_close_v1",
        "calendar_id": window["calendar_id"],
        "calendar_version": window["calendar_version"],
        "currency": CURRENCIES[market],
    }


def _normalize_prediction_settlement_contract(
    raw_record: Mapping[str, Any],
    generated_at: dt.datetime | str,
) -> dict[str, Any]:
    record = dict(raw_record)
    expected = _settlement_contract_fields(record, generated_at)
    for field, value in expected.items():
        current = record.get(field)
        if current is not None and current != value:
            raise ObservationConflictError(
                f"observation settlement field conflict: {record.get('observation_id')}:{field}"
            )
        record[field] = value
    expected_digest = settlement_contract_sha256(record)
    stored_digest = record.get("settlement_contract_sha256")
    if stored_digest is not None and stored_digest != expected_digest:
        raise ObservationConflictError(
            f"observation settlement digest conflict: {record.get('observation_id')}"
        )
    record["settlement_contract_sha256"] = expected_digest
    return record


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


def _feature_cutoff(snapshot: Mapping[str, Any], generated: dt.datetime) -> str:
    raw = snapshot.get("feature_cutoff_at") or snapshot.get("generated_at")
    cutoff = _aware_moment(raw, "feature_cutoff_at")
    if cutoff.astimezone(dt.timezone.utc) < generated.astimezone(dt.timezone.utc):
        raise ObservationContractError("feature_cutoff_at cannot precede generated_at")
    return cutoff.isoformat(timespec="microseconds" if cutoff.microsecond else "seconds")


def validate_source_snapshot_binding(
    snapshot: Mapping[str, Any],
    revision: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify one parsed immutable snapshot against its frozen revision-v2 identity."""

    if not isinstance(revision, Mapping) or revision.get("schema_version") != REVISION_SCHEMA_VERSION:
        raise ObservationContractError("source snapshot binding requires revision v2")
    scheduled, generated = _scheduled_slot(snapshot)
    source_snapshot = _canonical_snapshot_name(snapshot, None)
    scheduled_iso = scheduled.astimezone(CN_TZ).isoformat(timespec="minutes")
    generated_iso = generated.isoformat(timespec="seconds")
    cutoff_iso = _feature_cutoff(snapshot, generated)
    if (
        source_snapshot != revision.get("source_snapshot")
        or scheduled_iso != revision.get("scheduled_slot")
        or generated_iso != revision.get("generated_at")
        or cutoff_iso != revision.get("feature_cutoff_at")
    ):
        raise ObservationConflictError("source snapshot critical identity mismatch")
    expected = source_snapshot_identity(snapshot)
    for field, value in expected.items():
        if revision.get(field) != value:
            raise ObservationConflictError(f"source snapshot content identity mismatch: {field}")
    return expected


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
    generated_at: dt.datetime,
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
    fit_data_cutoff = _iso_date(
        prediction.get("fit_data_cutoff"),
        "prediction.fit_data_cutoff",
    )
    prediction_as_of = _iso_date(prediction.get("prediction_as_of"), "prediction.prediction_as_of")
    decision_local_date = market_calendar.market_local_date(str(market), generated_at).isoformat()
    if not training_cutoff <= fit_data_cutoff <= prediction_as_of <= decision_local_date:
        raise ObservationContractError(
            "observation cutoffs must satisfy training_cutoff <= fit_data_cutoff "
            "<= prediction_as_of <= the market-local decision date"
        )

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
        "fit_data_cutoff": fit_data_cutoff,
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
    record["prediction_sha256"] = prediction_sha256(record)
    return _normalize_prediction_settlement_contract(record, generated_at)


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
    snapshot_identity = source_snapshot_identity(snapshot)
    feature_cutoff_at = _feature_cutoff(snapshot, generated)
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
            generated_at=generated,
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
        **snapshot_identity,
        "feature_cutoff_at": feature_cutoff_at,
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


def _normalize_persisted_prediction(
    raw_record: Mapping[str, Any],
    revision: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Validate one persisted prediction and upgrade only the legacy calendar block."""

    if not isinstance(raw_record, Mapping):
        raise ObservationContractError("observation prediction must be an object")
    record = dict(raw_record)
    fields = frozenset(record)
    derived_present = fields & frozenset(PREDICTION_SETTLEMENT_DERIVED_FIELDS)
    if not derived_present:
        expected_fields = PREDICTION_BASE_FIELDS
        legacy = True
    elif derived_present == frozenset(PREDICTION_SETTLEMENT_DERIVED_FIELDS):
        expected_fields = PREDICTION_CURRENT_FIELDS
        legacy = False
    else:
        raise ObservationContractError(
            "observation settlement fields must be either wholly absent or complete"
        )
    if fields != expected_fields:
        missing = sorted(expected_fields - fields)
        unexpected = sorted(fields - expected_fields)
        raise ObservationContractError(
            "observation prediction field set is invalid: "
            f"missing={missing} unexpected={unexpected}"
        )
    if (
        record.get("schema_version") != revision.get("schema_version")
        or record.get("schema_version") not in {
            LEGACY_REVISION_SCHEMA_VERSION,
            REVISION_SCHEMA_VERSION,
        }
        or record.get("track") != TRACK
        or record.get("participates_in_decision") is not False
        or record.get("production_eligible") is not False
        or record.get("included_in_shadow_research") is not False
        or record.get("included_in_executable_performance") is not False
        or type(record.get("rank_eligible")) is not bool
    ):
        raise ObservationContractError("observation prediction isolation contract is invalid")

    market = record.get("market")
    code = record.get("code")
    model_id = record.get("model_id")
    label_version = record.get("label_version")
    scheduled_slot = record.get("scheduled_slot")
    source_snapshot = record.get("source_snapshot")
    if (
        not isinstance(market, str)
        or market not in VALID_MARKETS
        or not isinstance(code, str)
        or not code
        or code != code.strip()
    ):
        raise ObservationContractError("observation prediction market or code is invalid")
    if (
        not isinstance(model_id, str)
        or not model_id
        or not isinstance(label_version, str)
        or not label_version
        or not isinstance(scheduled_slot, str)
        or not isinstance(source_snapshot, str)
    ):
        raise ObservationContractError("observation prediction model identity is invalid")
    source_prediction_id = record.get("source_prediction_id")
    if source_prediction_id is not None and (
        not isinstance(source_prediction_id, str) or not source_prediction_id
    ):
        raise ObservationContractError("observation source_prediction_id is invalid")
    for field in ("feature_schema_version", "market_validation_status"):
        value = record.get(field)
        if value is not None and (not isinstance(value, str) or not value):
            raise ObservationContractError(f"observation prediction {field} is invalid")
    if scheduled_slot != revision.get("scheduled_slot"):
        raise ObservationConflictError("observation prediction scheduled_slot conflict")
    if source_snapshot != revision.get("source_snapshot"):
        raise ObservationConflictError("observation prediction source_snapshot conflict")
    if (
        not VALID_SAFE_SNAPSHOT.fullmatch(source_snapshot)
        or pathlib.PurePosixPath(source_snapshot).name != source_snapshot
    ):
        raise ObservationContractError("observation prediction source_snapshot is unsafe")
    if model_id != revision.get("model_id") or label_version != revision.get("label_version"):
        raise ObservationConflictError("observation prediction model identity conflicts with revision")

    expected_observation_id = _stable_id(
        "obs",
        scheduled_slot,
        market,
        code,
        model_id,
        label_version,
    )
    if record.get("observation_id") != expected_observation_id:
        raise ObservationConflictError("observation_id does not match its immutable identity")
    expected_prediction_digest = prediction_sha256(record)
    if record.get("prediction_sha256") != expected_prediction_digest:
        raise ObservationConflictError(
            f"observation prediction digest mismatch: {record.get('observation_id')}"
        )

    artifact = record.get("artifact_sha256")
    if (
        not isinstance(artifact, str)
        or artifact != artifact.lower()
        or VALID_ARTIFACT.fullmatch(artifact) is None
    ):
        raise ObservationContractError("observation prediction artifact_sha256 is invalid")
    training_cutoff = _iso_date(record.get("training_cutoff"), "training_cutoff")
    fit_data_cutoff = _iso_date(record.get("fit_data_cutoff"), "fit_data_cutoff")
    prediction_as_of = _iso_date(record.get("prediction_as_of"), "prediction_as_of")
    if (
        record.get("training_cutoff") != training_cutoff
        or record.get("fit_data_cutoff") != fit_data_cutoff
        or record.get("prediction_as_of") != prediction_as_of
    ):
        raise ObservationContractError("observation prediction dates are not canonical ISO dates")
    generated_at = _aware_moment(revision.get("generated_at"), "revision.generated_at")
    local_decision_date = market_calendar.market_local_date(market, generated_at).isoformat()
    if not training_cutoff <= fit_data_cutoff <= prediction_as_of <= local_decision_date:
        raise ObservationContractError("observation prediction cutoffs are not monotonic")
    probability = record.get("probability")
    if not _finite(probability) or not 0.0 <= float(probability) <= 1.0:
        raise ObservationContractError("observation prediction probability is invalid")
    for field in ("expected_net_return", "expected_net_utility"):
        if not _finite(record.get(field)):
            raise ObservationContractError(f"observation prediction {field} is invalid")
    for field in ("transaction_cost", "tail_risk"):
        value = record.get(field)
        if not _finite(value) or float(value) < 0.0:
            raise ObservationContractError(f"observation prediction {field} is invalid")

    normalized = _normalize_prediction_settlement_contract(record, generated_at)
    return normalized, legacy


def _normalize_persisted_revision(
    raw_revision: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Validate a raw revision before returning its deterministic current form."""

    if not isinstance(raw_revision, Mapping):
        raise ObservationContractError("observation revision must be an object")
    revision = dict(raw_revision)
    revision_id = revision.get("revision_id")
    raw_digest = _digest(
        {key: value for key, value in revision.items() if key != "revision_sha256"}
    )
    if revision.get("revision_sha256") != raw_digest:
        raise ObservationConflictError(f"revision digest mismatch: {revision_id}")
    schema_version = revision.get("schema_version")
    expected_revision_fields = (
        REVISION_FIELDS
        if schema_version == REVISION_SCHEMA_VERSION
        else LEGACY_REVISION_FIELDS
        if schema_version == LEGACY_REVISION_SCHEMA_VERSION
        else frozenset()
    )
    fields = frozenset(revision)
    if fields != expected_revision_fields:
        raise ObservationContractError(
            "observation revision field set is invalid: "
            f"missing={sorted(expected_revision_fields - fields)} "
            f"unexpected={sorted(fields - expected_revision_fields)}"
        )
    if not expected_revision_fields or revision.get("track") != TRACK:
        raise ObservationContractError("observation revision belongs to another schema or track")
    cohort_id = revision.get("cohort_id")
    if not isinstance(cohort_id, str) or VALID_COHORT_ID.fullmatch(cohort_id) is None:
        raise ObservationContractError("observation cohort_id is invalid")
    if not isinstance(revision_id, str) or VALID_REVISION_ID.fullmatch(revision_id) is None:
        raise ObservationContractError("observation revision_id is invalid")
    for field in ("model_id", "label_version", "model_status"):
        value = revision.get(field)
        if not isinstance(value, str) or not value:
            raise ObservationContractError(f"observation revision {field} is invalid")
    if (
        revision.get("sampling_policy") != SAMPLING_POLICY
        or revision.get("included_in_shadow_research") is not False
        or revision.get("included_in_executable_performance") is not False
    ):
        raise ObservationContractError("observation revision isolation contract is invalid")

    scheduled = _aware_moment(revision.get("scheduled_slot"), "revision.scheduled_slot")
    generated = _aware_moment(revision.get("generated_at"), "revision.generated_at")
    slot_iso = scheduled.astimezone(CN_TZ).isoformat(timespec="minutes")
    generated_iso = generated.isoformat(timespec="seconds")
    delay = generated.astimezone(dt.timezone.utc) - scheduled.astimezone(dt.timezone.utc)
    if (
        revision.get("scheduled_slot") != slot_iso
        or revision.get("generated_at") != generated_iso
        or (scheduled.astimezone(CN_TZ).hour, scheduled.astimezone(CN_TZ).minute)
        != DAILY_SLOT
        or delay < dt.timedelta(0)
        or delay > MAX_REVISION_DELAY
    ):
        raise ObservationContractError("observation revision schedule contract is invalid")
    source_snapshot = str(revision.get("source_snapshot") or "")
    if (
        not VALID_SAFE_SNAPSHOT.fullmatch(source_snapshot)
        or pathlib.PurePosixPath(source_snapshot).name != source_snapshot
    ):
        raise ObservationContractError("observation revision source_snapshot is unsafe")
    feature_cutoff: dt.datetime | None = None
    if schema_version == REVISION_SCHEMA_VERSION:
        if revision.get("source_snapshot_hash_contract") != SOURCE_SNAPSHOT_HASH_CONTRACT:
            raise ObservationContractError("observation revision source snapshot hash contract is invalid")
        source_digest = revision.get("source_snapshot_sha256")
        source_size = revision.get("source_snapshot_byte_size")
        if (
            not isinstance(source_digest, str)
            or source_digest != source_digest.lower()
            or VALID_ARTIFACT.fullmatch(source_digest) is None
            or not isinstance(source_size, int)
            or isinstance(source_size, bool)
            or source_size <= 0
        ):
            raise ObservationContractError("observation revision source snapshot identity is invalid")
        feature_cutoff = _aware_moment(
            revision.get("feature_cutoff_at"),
            "revision.feature_cutoff_at",
        )
        cutoff_iso = feature_cutoff.isoformat(
            timespec="microseconds" if feature_cutoff.microsecond else "seconds"
        )
        if (
            revision.get("feature_cutoff_at") != cutoff_iso
            or feature_cutoff.astimezone(dt.timezone.utc) < generated.astimezone(dt.timezone.utc)
        ):
            raise ObservationContractError("observation revision feature cutoff is invalid")
    if cohort_id != _stable_id("obscohort", slot_iso):
        raise ObservationConflictError("observation revision cohort identity mismatch")
    if revision_id != _stable_id("obsrev", slot_iso, generated_iso, source_snapshot):
        raise ObservationConflictError("observation revision identity mismatch")

    predictions = revision.get("predictions")
    if not isinstance(predictions, list):
        raise ObservationContractError("observation revision predictions must be a list")
    normalized_predictions: list[dict[str, Any]] = []
    legacy_states: list[bool] = []
    seen_keys: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    for raw_prediction in predictions:
        prediction, prediction_legacy = _normalize_persisted_prediction(
            raw_prediction,
            revision,
        )
        identity = (str(prediction["market"]), str(prediction["code"]))
        observation_id = str(prediction["observation_id"])
        if identity in seen_keys or observation_id in seen_ids:
            raise ObservationConflictError(
                f"duplicate prediction identity in revision {revision_id}: {identity}"
            )
        seen_keys.add(identity)
        seen_ids.add(observation_id)
        normalized_predictions.append(prediction)
        legacy_states.append(prediction_legacy)
    if legacy_states and any(legacy_states) and not all(legacy_states):
        raise ObservationContractError(
            "one observation revision cannot mix legacy and current prediction fields"
        )
    legacy = bool(legacy_states and all(legacy_states))
    model_artifact = revision.get("model_artifact_sha256")
    if model_artifact is not None and (
        not isinstance(model_artifact, str)
        or model_artifact != model_artifact.lower()
        or VALID_ARTIFACT.fullmatch(model_artifact) is None
    ):
        raise ObservationContractError("observation revision model artifact is invalid")
    if normalized_predictions and model_artifact is None:
        raise ObservationContractError(
            "non-empty observation revision requires a model artifact"
        )
    if feature_cutoff is not None and any(
        feature_cutoff.astimezone(dt.timezone.utc)
        >= _aware_moment(
            prediction.get("entry_session_open_at"),
            "prediction.entry_session_open_at",
        ).astimezone(dt.timezone.utc)
        for prediction in normalized_predictions
    ):
        raise ObservationContractError(
            "observation revision feature cutoff must precede every entry-session open"
        )
    expected_order = sorted(
        normalized_predictions,
        key=lambda item: (VALID_MARKETS.index(str(item["market"])), str(item["code"])),
    )
    if normalized_predictions != expected_order:
        raise ObservationConflictError("observation revision predictions are not canonical-order")
    market_counts = Counter(str(item["market"]) for item in normalized_predictions)
    expected_market_counts = {
        market: market_counts.get(market, 0) for market in VALID_MARKETS
    }
    prediction_count = revision.get("prediction_count")
    if (
        not isinstance(prediction_count, int)
        or isinstance(prediction_count, bool)
        or prediction_count != len(normalized_predictions)
        or revision.get("market_prediction_counts") != expected_market_counts
    ):
        raise ObservationConflictError("observation revision prediction counts are inconsistent")

    revision["predictions"] = normalized_predictions
    revision["revision_sha256"] = _digest(
        {key: value for key, value in revision.items() if key != "revision_sha256"}
    )
    return revision, legacy


def _cohort_from_normalized_revisions(
    revisions: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    unique: dict[str, dict[str, Any]] = {}
    moments: dict[str, str] = {}
    cohort_id: str | None = None
    for raw_revision in revisions:
        revision = dict(raw_revision)
        current_cohort_id = revision.get("cohort_id")
        revision_id = revision.get("revision_id")
        if cohort_id is None:
            cohort_id = current_cohort_id
        elif current_cohort_id != cohort_id:
            raise ObservationConflictError("revisions from different daily cohorts cannot be merged")
        existing = unique.get(revision_id)
        if existing is not None and existing != revision:
            raise ObservationConflictError(f"conflicting payload for revision {revision_id}")
        generated_at = str(revision.get("generated_at") or "")
        existing_moment = moments.get(generated_at)
        normalized_digest = str(revision.get("revision_sha256") or "")
        if existing_moment is not None and existing_moment != normalized_digest:
            raise ObservationConflictError(
                f"ambiguous same-moment revisions in cohort {cohort_id}: {generated_at}"
            )
        moments[generated_at] = normalized_digest
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


def _cohort_from_revisions(revisions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [
        _normalize_persisted_revision(raw_revision)[0]
        for raw_revision in revisions
    ]
    return _cohort_from_normalized_revisions(normalized)


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
    stored_existing: dict[str, Any] | None = None
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ObservationConflictError(f"existing observation cohort is unreadable: {target.name}") from exc
        if not isinstance(loaded, dict):
            raise ObservationConflictError(f"existing observation cohort is not an object: {target.name}")
        stored_existing = loaded
        existing = validate_observation_cohort(loaded)
        if existing.get("cohort_id") != cohort_id:
            raise ObservationConflictError(f"existing observation cohort identity conflict: {target.name}")
    existing_revisions = list((existing or {}).get("revisions") or [])
    same_revision = next(
        (
            item
            for item in existing_revisions
            if item.get("revision_id") == revision.get("revision_id")
        ),
        None,
    )
    if (
        isinstance(same_revision, Mapping)
        and same_revision.get("schema_version") == LEGACY_REVISION_SCHEMA_VERSION
        and revision.get("schema_version") == REVISION_SCHEMA_VERSION
    ):
        # A persisted v1 revision may already have a PENDING/SETTLED outcome
        # whose cohort digest is immutable. Do not rewrite that historical
        # identity in place. It remains readable for settlement but is excluded
        # from rank training because it lacks a source-content binding.
        revisions = existing_revisions
    else:
        revisions = [*existing_revisions, revision]
    cohort = _cohort_from_revisions(revisions)
    changed = stored_existing != cohort
    if changed:
        _atomic_write_json(target, cohort)
    return {
        "path": target,
        "created": stored_existing is None,
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
        rebuilt = validate_observation_cohort(payload)
        result[path.stem] = rebuilt
    return result


def validate_observation_cohort(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a cohort and upgrade settlement-free legacy revisions in memory."""

    if not isinstance(payload, Mapping):
        raise ObservationContractError("observation cohort must be an object")
    cohort = dict(payload)
    stored_digest = cohort.get("cohort_sha256")
    expected_digest = _digest(
        {key: value for key, value in cohort.items() if key != "cohort_sha256"}
    )
    if stored_digest != expected_digest:
        raise ObservationConflictError("observation cohort digest mismatch")
    fields = frozenset(cohort)
    if fields != COHORT_FIELDS:
        raise ObservationContractError(
            "observation cohort field set is invalid: "
            f"missing={sorted(COHORT_FIELDS - fields)} "
            f"unexpected={sorted(fields - COHORT_FIELDS)}"
        )
    raw_revisions = cohort.get("revisions")
    if not isinstance(raw_revisions, list):
        raise ObservationContractError("observation cohort revisions must be a list")
    normalized_pairs = [
        _normalize_persisted_revision(raw_revision)
        for raw_revision in raw_revisions
    ]
    normalized_revisions = [revision for revision, _legacy in normalized_pairs]
    rebuilt = _cohort_from_normalized_revisions(normalized_revisions)
    if rebuilt.get("cohort_id") != cohort.get("cohort_id"):
        raise ObservationConflictError("observation cohort identity conflict")
    raw_header = {
        key: value
        for key, value in cohort.items()
        if key not in {"revisions", "cohort_sha256"}
    }
    rebuilt_header = {
        key: value
        for key, value in rebuilt.items()
        if key not in {"revisions", "cohort_sha256"}
    }
    if raw_header != rebuilt_header:
        raise ObservationConflictError("observation cohort canonical metadata conflict")
    if normalized_revisions != rebuilt["revisions"]:
        raise ObservationConflictError(
            "observation cohort revision order, count, or uniqueness is non-canonical"
        )
    has_legacy_revision = any(legacy for _revision, legacy in normalized_pairs)
    if rebuilt != cohort and not has_legacy_revision:
        raise ObservationConflictError("observation cohort payload conflict")
    return rebuilt


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
        "settlement_status": (
            "NO_SAMPLE" if canonical_prediction_count == 0 else "PENDING_MATURITY"
        ),
        "authorizes_production": False,
    }


__all__ = [
    "COHORT_SCHEMA_VERSION",
    "DEFAULT_OBSERVATION_DIRECTORY",
    "EXECUTABLE_TRACK",
    "LEGACY_REVISION_SCHEMA_VERSION",
    "ObservationConflictError",
    "ObservationContractError",
    "REVISION_SCHEMA_VERSION",
    "SAMPLING_POLICY",
    "SHADOW_TRACK",
    "SOURCE_SNAPSHOT_HASH_CONTRACT",
    "SUMMARY_SCHEMA_VERSION",
    "SETTLEMENT_CONTRACT_FIELDS",
    "PREDICTION_SETTLEMENT_DERIVED_FIELDS",
    "TRACK",
    "build_observation_cohorts",
    "build_observation_revision",
    "load_observation_cohorts",
    "record_observation_revision",
    "prediction_sha256",
    "settlement_contract_sha256",
    "source_snapshot_identity",
    "summarize_observation_cohorts",
    "validate_observation_cohort",
    "validate_source_snapshot_binding",
]

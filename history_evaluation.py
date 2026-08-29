"""Strict, deterministic evaluation for immutable selector history.

This module deliberately has no network or application-server dependencies so
the local API and the Cloudflare asset builder can share one evaluation
contract.  Shadow research outcomes and executable-model outcomes are separate
tracks and can never be substituted for each other.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import model_observation_ledger
import observation_outcome_ledger
import rule_outcome_ledger


HISTORY_EVALUATION_SCHEMA = "history-evaluation-v1"
PERFORMANCE_SCHEMA = "history-performance-v1"
SHADOW_TRACK = "SHADOW_RESEARCH"
EXECUTABLE_TRACK = "EXECUTABLE_MODEL"
SHADOW_LEDGER_SCHEMA = "shadow-outcome-v1"
EXECUTABLE_LEDGER_SCHEMA = "executable-outcome-v1"
MINIMUM_RELIABLE_SAMPLE = 20
MINIMUM_TAIL_SAMPLE = 5
MINIMUM_OBSERVATION_COHORT_DAYS = 60
CN_TZ = ZoneInfo("Asia/Shanghai")
SETTLEMENT_TOLERANCE = 1e-6
SHADOW_DAILY_SLOT = (22, 47)
VALID_LEDGER_STATUSES = {"PENDING", "SETTLED"}
SHADOW_COST_ASSUMPTIONS = {"a_share": 0.0015, "hk": 0.0030, "us": 0.0015}
VALID_PREDICTION_ID = re.compile(r"^pred_[a-f0-9]{16,64}$")
SHADOW_MODEL_IDENTITY_FIELDS = (
    "prediction_id",
    "model_id",
    "label_version",
    "probability",
    "expected_net_utility",
    "tail_risk",
    "transaction_cost",
    "artifact_sha256",
    "training_cutoff",
)
CONTRACT_IDENTITY_FIELDS = (
    "schema_version",
    "track",
    "prediction_id",
    "model_id",
    "label_version",
    "market",
    "code",
    "entry_trade_date",
    "forecast_end_trade_date",
    "calendar_id",
    "calendar_version",
    "horizon_trade_sessions",
    "entry_policy",
    "exit_policy",
    "sampling_policy",
    "probability",
    "expected_net_utility",
    "tail_risk",
    "transaction_cost",
)


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_moment(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def is_global_ten_day_decision(decision: Any) -> bool:
    return bool(
        isinstance(decision, dict)
        and decision.get("contract_version") == "global-10d-v1"
        and decision.get("decision_scope") == "global_10d"
        and decision.get("action_basis") == "strict_cross_market_gate_v1"
    )


def eligible_shadow_snapshot(snapshot: dict[str, Any]) -> bool:
    """Admit one healthy technical Shadow sample for the daily primary slot.

    The 23:17 health recovery deliberately inherits the 22:47
    ``scheduled_slot``.  It is therefore the same statistical sample, not a
    second observation.  Legacy rule rows, manual runs, degraded market
    envelopes and non-rankable model rows remain visible in history but cannot
    create an outcome-ledger contract.
    """

    automation = snapshot.get("automation")
    automation = automation if isinstance(automation, dict) else {}
    trigger = str(automation.get("trigger") or "")
    if trigger != "schedule":
        return False
    scheduled = parse_moment(automation.get("scheduled_slot"))
    if scheduled is None:
        return False
    local = scheduled.astimezone(CN_TZ)
    if (local.hour, local.minute) != SHADOW_DAILY_SLOT:
        return False

    decision = snapshot.get("global_decision")
    if not is_global_ten_day_decision(decision):
        return False
    research_priority = decision.get("research_priority")
    if not isinstance(research_priority, dict):
        return False
    nested = research_priority.get("shadow_model")
    if not isinstance(nested, dict) or nested.get("rank_eligible") is not True:
        return False

    selected_market = research_priority.get("market")
    market_states = decision.get("market_states")
    required_markets = {"a_share", "hk", "us"}
    if (
        not isinstance(selected_market, str)
        or not selected_market
        or not isinstance(market_states, dict)
        or set(market_states) != required_markets
        or selected_market not in market_states
    ):
        return False
    for state in market_states.values():
        state_name = state.get("state") if isinstance(state, dict) else state
        if str(state_name or "").upper() != "READY":
            return False
    return True


def snapshot_source_name(snapshot: dict[str, Any], explicit: str | None = None) -> str | None:
    if isinstance(explicit, str) and explicit:
        return explicit
    for key in ("snapshot_key", "cache_key"):
        value = snapshot.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def shadow_research_contract(research_priority: Any) -> dict[str, Any] | None:
    """Select the auditable Shadow identity without relabeling model output.

    Legacy rule-only snapshots have no nested ``shadow_model`` and retain their
    historical identity.  Once a nested technical model is present, however,
    it must be complete and explicitly research-only.  A malformed nested
    model fails closed instead of silently falling back to the old rule model.
    """

    if not isinstance(research_priority, dict) or research_priority.get("status") != "RESEARCH_ONLY":
        return None
    nested = research_priority.get("shadow_model")
    if nested is None:
        return dict(research_priority)
    if not isinstance(nested, dict):
        return None
    if nested.get("rank_eligible") is False:
        legacy = dict(research_priority)
        legacy.pop("shadow_model", None)
        return legacy
    if nested.get("rank_eligible") is not True:
        return None
    if (
        nested.get("status") != "SHADOW_ONLY"
        or nested.get("calibrated") is not False
        or nested.get("participates_in_decision") is not False
        or nested.get("production_eligible") is not False
    ):
        return None

    prediction_id = nested.get("prediction_id")
    model_id = nested.get("model_id")
    label_version = nested.get("label_version")
    artifact_sha256 = nested.get("artifact_sha256")
    training_cutoff = nested.get("training_cutoff")
    if (
        not isinstance(prediction_id, str)
        or not VALID_PREDICTION_ID.fullmatch(prediction_id)
        or not isinstance(model_id, str)
        or not model_id
        or not isinstance(label_version, str)
        or not label_version
        or not isinstance(artifact_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", artifact_sha256.lower()) is None
        or not isinstance(training_cutoff, str)
    ):
        return None
    try:
        dt.date.fromisoformat(training_cutoff)
    except ValueError:
        return None

    probability = nested.get("probability")
    expected_net_utility = nested.get("expected_net_utility")
    tail_risk = nested.get("tail_risk")
    transaction_cost = nested.get("transaction_cost")
    if (
        not finite_number(probability)
        or not 0.0 <= float(probability) <= 1.0
        or not finite_number(expected_net_utility)
        or not finite_number(tail_risk)
        or float(tail_risk) < 0.0
        or not finite_number(transaction_cost)
        or float(transaction_cost) < 0.0
    ):
        return None
    for key in ("market", "code"):
        if key in nested and nested.get(key) != research_priority.get(key):
            return None

    selected = dict(research_priority)
    selected.update({key: nested.get(key) for key in SHADOW_MODEL_IDENTITY_FIELDS})
    return selected


def _frozen_contract_fields(snapshot: dict[str, Any], track: str) -> dict[str, Any]:
    if track == SHADOW_TRACK:
        automation = snapshot.get("automation")
        automation = automation if isinstance(automation, dict) else {}
        sampling_policy = (
            "daily_last_primary_checkpoint_v1"
            if str(automation.get("trigger") or "") == "schedule"
            else "legacy_snapshot_v1"
        )
        schema_version = SHADOW_LEDGER_SCHEMA
    else:
        sampling_policy = "all_published_executable_predictions_v1"
        schema_version = EXECUTABLE_LEDGER_SCHEMA
    return {
        "schema_version": schema_version,
        "track": track,
        "horizon_trade_sessions": 10,
        "entry_policy": "next_session_open_v1",
        "exit_policy": "tenth_session_close_v1",
        "sampling_policy": sampling_policy,
    }


def prediction_contract(snapshot: dict[str, Any], track: str) -> dict[str, Any] | None:
    decision = snapshot.get("global_decision")
    if not is_global_ten_day_decision(decision):
        return None
    if track == SHADOW_TRACK:
        if not eligible_shadow_snapshot(snapshot):
            return None
        contract = shadow_research_contract(decision.get("research_priority"))
        if contract is None:
            return None
    elif track == EXECUTABLE_TRACK:
        if (
            decision.get("action") != "REVIEW_EXECUTABLE_PICK"
            or decision.get("probability_status") != "CALIBRATED"
            or decision.get("calibrated") is not True
            or decision.get("horizon_trade_days") != 10
            or bool(decision.get("blocker_codes"))
        ):
            return None
        contract = decision.get("primary")
        if (
            not isinstance(contract, dict)
            or contract.get("status") != "EXECUTABLE"
            or contract.get("score_kind") != "TEN_DAY_EXPECTED_NET_UTILITY"
        ):
            return None
        if contract.get("calibrated") is not True:
            return None
        probability = contract.get("probability")
        if not finite_number(probability) or not 0.0 <= probability <= 1.0:
            return None
        decision_probability = decision.get("probability")
        if (
            not finite_number(decision_probability)
            or abs(float(decision_probability) - float(probability)) > SETTLEMENT_TOLERANCE
        ):
            return None
        if not finite_number(contract.get("expected_net_utility")) or contract.get("expected_net_utility") <= 0:
            return None
        if not finite_number(contract.get("tail_risk")) or contract.get("tail_risk") < 0:
            return None
    else:
        return None

    required = (
        "prediction_id",
        "model_id",
        "label_version",
        "market",
        "code",
        "entry_trade_date",
        "forecast_end_trade_date",
        "calendar_id",
        "calendar_version",
    )
    if not all(isinstance(contract.get(key), str) and bool(contract.get(key)) for key in required):
        return None
    normalized = dict(contract)
    frozen = _frozen_contract_fields(snapshot, track)
    if any(key in contract and contract.get(key) != value for key, value in frozen.items()):
        return None
    normalized.update(frozen)
    for key in ("probability", "expected_net_utility", "tail_risk"):
        normalized.setdefault(key, None)
    if track == EXECUTABLE_TRACK:
        if not finite_number(contract.get("transaction_cost")) or contract.get("transaction_cost") < 0:
            return None
    else:
        if isinstance(contract.get("shadow_model"), dict):
            transaction_cost = contract.get("transaction_cost")
            if not finite_number(transaction_cost) or float(transaction_cost) < 0:
                return None
        else:
            transaction_cost = SHADOW_COST_ASSUMPTIONS.get(str(contract.get("market") or ""))
            if transaction_cost is None:
                return None
        normalized["transaction_cost"] = transaction_cost
    return normalized


def contract_matches_outcome(
    contract: dict[str, Any],
    outcome: dict[str, Any],
    track: str,
    source_snapshot: str | None,
) -> bool:
    if not source_snapshot or outcome.get("source_snapshot") != source_snapshot:
        return False
    if contract.get("track") != track:
        return False
    identity_fields = CONTRACT_IDENTITY_FIELDS
    if track == SHADOW_TRACK:
        identity_fields += ("artifact_sha256", "training_cutoff")
    for key in identity_fields:
        if outcome.get(key) != contract.get(key):
            return False
    return str(outcome.get("status") or "").upper() in VALID_LEDGER_STATUSES


def load_ledger_inventory(directory: pathlib.Path, track: str) -> dict[str, Any]:
    """Read one flat outcome track while retaining honest raw/exclusion counts."""

    records: dict[str, dict[str, Any]] = {}
    raw_count = 0
    excluded_count = 0
    conflict_count = 0
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            raw_count += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                excluded_count += 1
                continue
            prediction_id = payload.get("prediction_id") if isinstance(payload, dict) else None
            if not prediction_id or path.stem != str(prediction_id) or payload.get("track") != track:
                excluded_count += 1
                continue
            if str(payload.get("status") or "").upper() not in VALID_LEDGER_STATUSES:
                excluded_count += 1
                continue
            if prediction_id in records and records[prediction_id] != payload:
                records.pop(str(prediction_id), None)
                conflict_count += 1
                continue
            records[str(prediction_id)] = payload
    return {
        "track": track,
        "raw_count": raw_count,
        "read_excluded_count": excluded_count,
        "read_conflict_count": conflict_count,
        "records": records,
    }


def empty_ledger_inventory(track: str) -> dict[str, Any]:
    return {
        "track": track,
        "raw_count": 0,
        "read_excluded_count": 0,
        "read_conflict_count": 0,
        "records": {},
    }


def matching_outcome(
    snapshot: dict[str, Any],
    outcome_map: dict[str, dict[str, Any]],
    track: str,
    source_snapshot: str | None = None,
) -> dict[str, Any] | None:
    contract = prediction_contract(snapshot, track)
    if contract is None:
        return None
    source_snapshot = snapshot_source_name(snapshot, source_snapshot)
    outcome = outcome_map.get(str(contract["prediction_id"]))
    if not isinstance(outcome, dict) or not contract_matches_outcome(
        contract,
        outcome,
        track,
        source_snapshot,
    ):
        return None
    return dict(outcome)


def _contract_signature(contract: dict[str, Any]) -> tuple[Any, ...]:
    identity_fields = CONTRACT_IDENTITY_FIELDS
    if contract.get("track") == SHADOW_TRACK:
        identity_fields += ("artifact_sha256", "training_cutoff")
    return tuple(contract.get(key) for key in identity_fields)


def ledger_statistics(
    snapshots: dict[str, dict[str, Any]],
    inventory: dict[str, Any],
    track: str,
) -> dict[str, Any]:
    contracts: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for source_name, snapshot in snapshots.items():
        contract = prediction_contract(snapshot, track)
        if contract is not None:
            contracts[str(contract["prediction_id"])].append((source_name, contract))

    eligible_count = 0
    pending_count = 0
    settled_count = 0
    excluded_count = int(inventory.get("read_excluded_count") or 0)
    conflict_count = int(inventory.get("read_conflict_count") or 0)
    for prediction_id, outcome in (inventory.get("records") or {}).items():
        candidates = contracts.get(str(prediction_id)) or []
        source_snapshot = outcome.get("source_snapshot")
        if not isinstance(source_snapshot, str) or not source_snapshot:
            excluded_count += 1
            continue
        candidates = [item for item in candidates if item[0] == source_snapshot]
        if not candidates:
            excluded_count += 1
            continue
        signatures = {_contract_signature(contract) for _, contract in candidates}
        if len(signatures) != 1 or not contract_matches_outcome(
            candidates[0][1],
            outcome,
            track,
            source_snapshot,
        ):
            conflict_count += 1
            continue
        eligible_count += 1
        status = str(outcome.get("status") or "").upper()
        pending_count += status == "PENDING"
        settled_count += status == "SETTLED"

    raw_count = int(inventory.get("raw_count") or 0)
    return {
        "track": track,
        "raw_count": raw_count,
        "raw_prediction_count": raw_count,
        "eligible_count": eligible_count,
        "prediction_count": eligible_count,
        "pending_count": pending_count,
        "settled_count": settled_count,
        "excluded_count": excluded_count,
        "conflict_count": conflict_count,
        "included_in_executable_performance": track == EXECUTABLE_TRACK,
    }


def valid_formal_settlement(row: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate one formal settled row without coercing missing data to zero."""

    decision = row.get("global_decision")
    primary = decision.get("primary") if isinstance(decision, dict) else None
    outcome = row.get("outcome")
    if row.get("history_kind") != "global_10d_v1" or not is_global_ten_day_decision(decision):
        return False, "FORMAL_CONTRACT_MISSING"
    if decision.get("action") != "REVIEW_EXECUTABLE_PICK" or not isinstance(primary, dict):
        return False, "EXECUTABLE_PRIMARY_MISSING"
    if primary.get("status") != "EXECUTABLE" or primary.get("calibrated") is not True:
        return False, "PRIMARY_NOT_CALIBRATED_EXECUTABLE"
    primary_strings = (
        "prediction_id",
        "model_id",
        "label_version",
        "market",
        "code",
        "entry_trade_date",
        "forecast_end_trade_date",
        "calendar_id",
        "calendar_version",
    )
    if not all(isinstance(primary.get(key), str) and bool(primary.get(key)) for key in primary_strings):
        return False, "PRIMARY_IDENTITY_INCOMPLETE"
    probability = primary.get("probability")
    if not finite_number(probability) or not 0.0 <= probability <= 1.0:
        return False, "PRIMARY_PROBABILITY_INVALID"
    if not finite_number(primary.get("expected_net_utility")) or primary.get("expected_net_utility") <= 0:
        return False, "PRIMARY_RANK_SCORE_INVALID"
    if not finite_number(primary.get("tail_risk")) or primary.get("tail_risk") < 0:
        return False, "PRIMARY_TAIL_RISK_INVALID"
    contract = prediction_contract(row, EXECUTABLE_TRACK)
    if contract is None:
        return False, "EXECUTABLE_CONTRACT_INVALID"
    if not isinstance(outcome, dict) or outcome.get("track") != EXECUTABLE_TRACK:
        return False, "EXECUTABLE_OUTCOME_MISSING"
    if str(outcome.get("status") or "").upper() != "SETTLED":
        return False, "OUTCOME_NOT_SETTLED"
    for key in ("prediction_id", "model_id", "label_version"):
        if not primary.get(key) or outcome.get(key) != primary.get(key):
            return False, f"OUTCOME_{key.upper()}_MISMATCH"
    for key in (
        "market",
        "code",
        "entry_trade_date",
        "forecast_end_trade_date",
        "calendar_id",
        "calendar_version",
    ):
        if outcome.get(key) != primary.get(key):
            return False, f"OUTCOME_{key.upper()}_MISMATCH"
    source_snapshot = snapshot_source_name(row)
    if not source_snapshot or outcome.get("source_snapshot") != source_snapshot:
        return False, "OUTCOME_SOURCE_SNAPSHOT_MISMATCH"
    if not contract_matches_outcome(
        contract,
        outcome,
        EXECUTABLE_TRACK,
        source_snapshot,
    ):
        return False, "OUTCOME_FROZEN_CONTRACT_MISMATCH"

    number_keys = ("entry_price", "exit_price", "gross_total_return", "net_total_return", "transaction_cost")
    if not all(finite_number(outcome.get(key)) for key in number_keys):
        return False, "OUTCOME_NUMBER_INVALID"
    entry_price = float(outcome["entry_price"])
    exit_price = float(outcome["exit_price"])
    gross_return = float(outcome["gross_total_return"])
    net_return = float(outcome["net_total_return"])
    transaction_cost = float(outcome["transaction_cost"])
    # A strictly positive exit price guarantees gross return > -100%.  Net
    # return can legitimately fall just below -100% after transaction costs,
    # so its admissibility is governed by the arithmetic check below rather
    # than an additional lower bound.
    if entry_price <= 0 or exit_price <= 0 or transaction_cost < 0 or gross_return <= -1:
        return False, "OUTCOME_NUMBER_OUT_OF_RANGE"
    if finite_number(primary.get("transaction_cost")) and abs(transaction_cost - float(primary["transaction_cost"])) > SETTLEMENT_TOLERANCE:
        return False, "OUTCOME_COST_MISMATCH"
    if abs(gross_return - (exit_price / entry_price - 1.0)) > SETTLEMENT_TOLERANCE:
        return False, "OUTCOME_GROSS_ARITHMETIC_MISMATCH"
    if abs(net_return - (gross_return - transaction_cost)) > SETTLEMENT_TOLERANCE:
        return False, "OUTCOME_NET_ARITHMETIC_MISMATCH"

    required_strings = ("entry_source", "exit_source", "calendar_id", "currency", "fx_rate_source")
    if not all(isinstance(outcome.get(key), str) and bool(outcome.get(key)) for key in required_strings):
        return False, "OUTCOME_PROVENANCE_INCOMPLETE"
    if not isinstance(outcome.get("corporate_action_adjusted"), bool):
        return False, "OUTCOME_ADJUSTMENT_FLAG_INVALID"
    positive_label = outcome.get("positive_label")
    if not isinstance(positive_label, bool) or positive_label != (net_return > 0):
        return False, "OUTCOME_LABEL_INCONSISTENT"

    generated_at = parse_moment(row.get("generated_at"))
    entry_at = parse_moment(outcome.get("entry_at"))
    exit_at = parse_moment(outcome.get("exit_at"))
    settled_at = parse_moment(outcome.get("settled_at"))
    try:
        forecast_end = dt.datetime.combine(
            dt.date.fromisoformat(str(primary.get("forecast_end_trade_date") or "")),
            dt.time.min,
            tzinfo=CN_TZ,
        )
    except ValueError:
        forecast_end = None
    if not all((generated_at, entry_at, exit_at, settled_at, forecast_end)):
        return False, "OUTCOME_TIMESTAMP_INVALID"
    if entry_at < generated_at:
        return False, "ENTRY_PRECEDES_PREDICTION"
    if exit_at < forecast_end:
        return False, "EXIT_PRECEDES_FORECAST_END"
    if settled_at < exit_at:
        return False, "SETTLEMENT_PRECEDES_EXIT"
    return True, None


def formal_sample_evaluation(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return a row-level formal state; never equate SETTLED with valid."""

    decision = row.get("global_decision")
    if row.get("history_kind") != "global_10d_v1" or not is_global_ten_day_decision(decision):
        return None
    if decision.get("action") == "NO_VALID_PICK":
        return {
            "formal_sample_status": "ABSTAINED",
            "outcome_validation": {
                "status": "NOT_APPLICABLE",
                "valid": None,
                "reason": "NO_VALID_PICK",
            },
        }

    contract = prediction_contract(row, EXECUTABLE_TRACK)
    if contract is None:
        return {
            "formal_sample_status": "INVALID_CONTRACT",
            "outcome_validation": {
                "status": "INVALID",
                "valid": False,
                "reason": "EXECUTABLE_CONTRACT_INVALID",
            },
        }

    outcome = row.get("outcome")
    if not isinstance(outcome, dict):
        return {
            "formal_sample_status": "MISSING",
            "outcome_validation": {
                "status": "MISSING",
                "valid": None,
                "reason": "EXECUTABLE_OUTCOME_MISSING",
            },
        }
    source_snapshot = snapshot_source_name(row)
    if not contract_matches_outcome(
        contract,
        outcome,
        EXECUTABLE_TRACK,
        source_snapshot,
    ):
        return {
            "formal_sample_status": "OUTCOME_INVALID",
            "outcome_validation": {
                "status": "INVALID",
                "valid": False,
                "reason": "OUTCOME_IDENTITY_OR_TRACK_MISMATCH",
            },
        }

    status = str(outcome.get("status") or "").upper()
    if status == "PENDING":
        return {
            "formal_sample_status": "PENDING",
            "outcome_validation": {
                "status": "PENDING",
                "valid": None,
                "reason": "OUTCOME_PENDING",
            },
        }

    valid, reason = valid_formal_settlement(row)
    return {
        "formal_sample_status": "SETTLED_VALID" if valid else "SETTLED_INVALID",
        "outcome_validation": {
            "status": "VALID" if valid else "INVALID",
            "valid": valid,
            "reason": reason,
        },
    }


def annotate_formal_sample(row: dict[str, Any]) -> dict[str, Any]:
    evaluation = formal_sample_evaluation(row)
    if evaluation is not None:
        row.update(evaluation)
    return row


def _outcome_fingerprint(outcome: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(outcome.get(key) for key in CONTRACT_IDENTITY_FIELDS) + tuple(
        outcome.get(key)
        for key in (
            "source_snapshot",
            "entry_at",
            "entry_price",
            "exit_at",
            "exit_price",
            "gross_total_return",
            "net_total_return",
            "settled_at",
        )
    )


def select_formal_cohort(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        decision = row.get("global_decision")
        primary = decision.get("primary") if isinstance(decision, dict) else None
        if (
            row.get("history_kind") == "global_10d_v1"
            and is_global_ten_day_decision(decision)
            and decision.get("action") == "REVIEW_EXECUTABLE_PICK"
            and isinstance(primary, dict)
            and primary.get("prediction_id")
        ):
            groups[str(primary["prediction_id"])].append(row)

    accepted: list[dict[str, Any]] = []
    pending_count = 0
    invalid_count = 0
    missing_count = 0
    conflict_count = 0
    reason_counts: Counter[str] = Counter()
    for group in groups.values():
        primary_signatures = {
            _contract_signature(prediction_contract(row, EXECUTABLE_TRACK) or {}) for row in group
        }
        if len(primary_signatures) != 1:
            conflict_count += 1
            reason_counts["PRIMARY_IDENTITY_CONFLICT"] += 1
            continue
        valid_rows: list[dict[str, Any]] = []
        group_reasons: list[str] = []
        for row in group:
            valid, reason = valid_formal_settlement(row)
            if valid:
                valid_rows.append(row)
            elif reason:
                group_reasons.append(reason)
        if valid_rows:
            fingerprints = {_outcome_fingerprint(row["outcome"]) for row in valid_rows}
            if len(fingerprints) != 1:
                conflict_count += 1
                reason_counts["SETTLEMENT_CONFLICT"] += 1
                continue
            accepted.append(
                max(valid_rows, key=lambda row: str((row.get("outcome") or {}).get("settled_at") or ""))
            )
            continue
        statuses = {
            str((row.get("outcome") or {}).get("status") or "").upper()
            for row in group
            if isinstance(row.get("outcome"), dict)
        }
        if "PENDING" in statuses:
            pending_count += 1
        elif "SETTLED" in statuses:
            invalid_count += 1
            for reason in set(group_reasons or ["INVALID_SETTLEMENT"]):
                reason_counts[reason] += 1
        else:
            missing_count += 1
            reason_counts["OUTCOME_MISSING"] += 1

    accepted.sort(key=lambda row: (parse_moment((row.get("outcome") or {}).get("exit_at")), str(((row.get("global_decision") or {}).get("primary") or {}).get("prediction_id"))))
    diagnostics = {
        "executable_prediction_count": len(groups),
        "pending_settlement_count": pending_count,
        "settled_sample_count": len(accepted),
        "invalid_settlement_count": invalid_count,
        "missing_outcome_count": missing_count,
        "conflict_count": conflict_count,
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
    }
    return accepted, diagnostics


def select_latest_model_daily_cohort(
    rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Choose the latest published model, then one latest prediction per target day."""

    source_rows = list(rows)
    all_prediction_ids: set[str] = set()
    eligible: list[tuple[dt.datetime, str, dict[str, Any], dict[str, Any]]] = []
    for row in source_rows:
        decision = row.get("global_decision")
        primary = decision.get("primary") if isinstance(decision, dict) else None
        if (
            row.get("history_kind") != "global_10d_v1"
            or not is_global_ten_day_decision(decision)
            or decision.get("action") != "REVIEW_EXECUTABLE_PICK"
            or not isinstance(primary, dict)
            or not primary.get("prediction_id")
        ):
            continue
        all_prediction_ids.add(str(primary["prediction_id"]))
        contract = prediction_contract(row, EXECUTABLE_TRACK)
        generated_at = parse_moment(row.get("generated_at"))
        if contract is None or generated_at is None:
            continue
        source_key = str(row.get("snapshot_key") or row.get("cache_key") or "")
        eligible.append((generated_at, source_key, row, contract))

    empty = {
        "cohort_selection_policy": "latest_published_model_latest_target_date_run_v1",
        "cohort_model_id": None,
        "cohort_label_version": None,
        "cohort_latest_published_at": None,
        "all_executable_prediction_count": len(all_prediction_ids),
        "cohort_prediction_count": 0,
        "cohort_independent_day_count": 0,
        "cohort_same_day_excluded_count": 0,
        "cohort_missing_target_date_count": 0,
    }
    if not eligible:
        return [], empty

    latest_generated_at, _, _, latest_contract = max(eligible, key=lambda item: (item[0], item[1]))
    model_id = str(latest_contract["model_id"])
    label_version = str(latest_contract["label_version"])
    model_rows = [
        item
        for item in eligible
        if str(item[3].get("model_id")) == model_id
        and str(item[3].get("label_version")) == label_version
    ]
    cohort_prediction_ids = {str(item[3]["prediction_id"]) for item in model_rows}
    by_target_date: dict[str, tuple[dt.datetime, str, dict[str, Any], dict[str, Any]]] = {}
    missing_target_date_count = 0
    for item in model_rows:
        row = item[2]
        target_date = row.get("target_date")
        if not isinstance(target_date, str) or not target_date:
            missing_target_date_count += 1
            continue
        current = by_target_date.get(target_date)
        if current is None or (item[0], item[1]) > (current[0], current[1]):
            by_target_date[target_date] = item

    selected = [item[2] for item in by_target_date.values()]
    selected.sort(
        key=lambda row: (
            str(row.get("target_date") or ""),
            parse_moment(row.get("generated_at")),
            str(row.get("snapshot_key") or row.get("cache_key") or ""),
        )
    )
    metadata = {
        "cohort_selection_policy": empty["cohort_selection_policy"],
        "cohort_model_id": model_id,
        "cohort_label_version": label_version,
        "cohort_latest_published_at": latest_generated_at.isoformat(),
        "all_executable_prediction_count": len(all_prediction_ids),
        "cohort_prediction_count": len(cohort_prediction_ids),
        "cohort_independent_day_count": len(selected),
        "cohort_same_day_excluded_count": max(
            0,
            len(model_rows) - len(selected) - missing_target_date_count,
        ),
        "cohort_missing_target_date_count": missing_target_date_count,
    }
    return selected, metadata


def _metric(
    value: float | int | None,
    n: int,
    *,
    unit: str,
    method: str,
    minimum: int = MINIMUM_RELIABLE_SAMPLE,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    if n == 0:
        return {
            "value": None if unit != "count" else 0,
            "unit": unit,
            "n": 0,
            "status": "NO_SAMPLE",
            "min_n": minimum,
            "reason": "NO_VALID_SETTLED_SAMPLE",
            "method": method,
        }
    if unavailable_reason:
        return {
            "value": None,
            "unit": unit,
            "n": n,
            "status": "UNAVAILABLE",
            "min_n": minimum,
            "reason": unavailable_reason,
            "method": method,
        }
    return {
        "value": value,
        "unit": unit,
        "n": n,
        "status": "READY" if n >= minimum else "INSUFFICIENT_SAMPLE",
        "min_n": minimum,
        "reason": None if n >= minimum else "MINIMUM_SAMPLE_NOT_MET",
        "method": method,
    }


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[cursor]]:
            end += 1
        average_rank = (cursor + 1 + end) / 2.0
        for position in ordered[cursor:end]:
            ranks[position] = average_rank
        cursor = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    centered_left = [value - mean_left for value in left]
    centered_right = [value - mean_right for value in right]
    denominator = math.sqrt(sum(value * value for value in centered_left) * sum(value * value for value in centered_right))
    if denominator == 0:
        return None
    return sum(a * b for a, b in zip(centered_left, centered_right)) / denominator


def _observation_auc(probabilities: list[float], labels: list[float]) -> float | None:
    positives = [index for index, label in enumerate(labels) if label == 1.0]
    negatives = [index for index, label in enumerate(labels) if label == 0.0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if probabilities[positive] > probabilities[negative]:
                wins += 1.0
            elif probabilities[positive] == probabilities[negative]:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def _observation_ece(probabilities: list[float], labels: list[float]) -> float:
    total = len(probabilities)
    result = 0.0
    for bucket in range(10):
        indices = [
            index
            for index, probability in enumerate(probabilities)
            if min(9, int(probability * 10)) == bucket
        ]
        if indices:
            confidence = sum(probabilities[index] for index in indices) / len(indices)
            accuracy = sum(labels[index] for index in indices) / len(indices)
            result += len(indices) / total * abs(confidence - accuracy)
    return result


def _equal_weight_metric(
    values: list[float],
    eligible_days: int,
    *,
    cell_count: int,
    complete_day_count: int,
    unit: str,
    method: str,
    unavailable_reason: str,
) -> dict[str, Any]:
    value = round(sum(values) / len(values), 12) if values else None
    metric = _metric(
        value,
        eligible_days,
        unit=unit,
        method=method,
        minimum=MINIMUM_OBSERVATION_COHORT_DAYS,
        unavailable_reason=unavailable_reason if not values and complete_day_count else None,
    )
    if not values and complete_day_count:
        metric.update(
            {
                "status": "UNAVAILABLE",
                "reason": unavailable_reason,
            }
        )
    metric["cell_n"] = cell_count
    metric["complete_day_n"] = complete_day_count
    return metric


def evaluate_observation_performance(
    cohorts: Mapping[str, Mapping[str, Any]],
    outcome_batches: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate prospective observations without touching executable metrics.

    Every statistic is first computed within one scheduled-date/market cell and
    then averaged across cells.  This prevents a market with more recalled
    symbols from dominating the diagnostics.  The result is descriptive only:
    it is never an authorization gate and cannot promote a model.
    """

    normalized_cohorts: dict[str, dict[str, Any]] = {}
    invalid_cohort_count = 0
    for cohort_id, cohort in cohorts.items():
        try:
            normalized = model_observation_ledger.validate_observation_cohort(cohort)
            if normalized.get("cohort_id") != cohort_id:
                raise model_observation_ledger.ObservationConflictError(
                    "observation cohort key mismatch"
                )
        except (ValueError, RuntimeError):
            invalid_cohort_count += 1
            continue
        normalized_cohorts[cohort_id] = normalized

    market_counts: dict[str, Counter[str]] = {
        market: Counter() for market in model_observation_ledger.VALID_MARKETS
    }
    prediction_count = 0
    pending_maturity_count = 0
    pending_data_count = 0
    settled_count = 0
    untracked_count = 0
    invalid_outcome_count = 0
    invalid_batch_count = 0
    settled_rows: list[dict[str, Any]] = []
    expected_cell_counts: Counter[tuple[str, str]] = Counter()

    for cohort_id, cohort in normalized_cohorts.items():
        canonical_id = cohort["canonical_revision_id"]
        canonical = next(
            revision
            for revision in cohort["revisions"]
            if revision["revision_id"] == canonical_id
        )
        predictions = canonical.get("predictions") or []
        prediction_count += len(predictions)
        for prediction in predictions:
            market = str(prediction["market"])
            market_counts[market]["prediction"] += 1
            expected_cell_counts[(str(cohort["scheduled_slot"])[:10], market)] += 1
        batch = outcome_batches.get(cohort_id)
        if batch is None:
            untracked_count += len(predictions)
            continue
        try:
            validated = observation_outcome_ledger.validate_outcome_batch(
                batch,
                cohort=cohort,
            )
        except (ValueError, RuntimeError):
            invalid_batch_count += 1
            invalid_outcome_count += len(predictions)
            continue
        for row in validated["outcomes"]:
            market = str(row["market"])
            status = str(row["status"])
            market_counts[market][status] += 1
            if status == "PENDING_MATURITY":
                pending_maturity_count += 1
            elif status == "PENDING_DATA":
                pending_data_count += 1
            elif status == "SETTLED":
                settled_count += 1
                settled_rows.append(dict(row))
            else:
                invalid_outcome_count += 1

    unknown_batches = set(outcome_batches) - set(normalized_cohorts)
    invalid_batch_count += len(unknown_batches)
    invalid_outcome_count += sum(
        len((outcome_batches[cohort_id].get("outcomes") or []))
        if isinstance(outcome_batches[cohort_id], Mapping)
        else 1
        for cohort_id in unknown_batches
    )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in settled_rows:
        grouped[(str(row["scheduled_slot"])[:10], str(row["market"]))].append(row)
    settled_independent_days = len({day for day, _market in grouped})
    complete_grouped = {
        key: rows
        for key, rows in grouped.items()
        if len(rows) == expected_cell_counts.get(key, 0) and expected_cell_counts.get(key, 0) > 0
    }
    incomplete_cell_count = sum(
        1
        for key, expected in expected_cell_counts.items()
        if expected > 0 and len(grouped.get(key, [])) != expected
    )
    independent_days = len({day for day, _market in complete_grouped})

    metric_cells: dict[str, list[float]] = defaultdict(list)
    metric_days: dict[str, set[str]] = defaultdict(set)

    def add_metric(name: str, value: float, day: str) -> None:
        metric_cells[name].append(value)
        metric_days[name].add(day)

    for (day, _market), rows in complete_grouped.items():
        probabilities = [float(row["probability"]) for row in rows]
        labels = [1.0 if row["positive_label"] else 0.0 for row in rows]
        returns = [float(row["net_total_return"]) for row in rows]
        utilities = [float(row["expected_net_utility"]) for row in rows]
        count = len(rows)
        brier = sum((probability - label) ** 2 for probability, label in zip(probabilities, labels)) / count
        add_metric("brier_score", brier, day)
        prevalence = sum(labels) / count
        baseline = sum((prevalence - label) ** 2 for label in labels) / count
        if baseline > 0:
            add_metric("brier_skill", 1.0 - brier / baseline, day)
        auc = _observation_auc(probabilities, labels)
        if auc is not None:
            add_metric("auc", auc, day)
        add_metric("ece_10bin", _observation_ece(probabilities, labels), day)
        rank_ic = _pearson(_average_ranks(utilities), _average_ranks(returns))
        if rank_ic is not None:
            add_metric("daily_cross_sectional_rank_ic", rank_ic, day)
        tail_count = max(1, math.ceil(count * 0.10))
        ranked = sorted(range(count), key=utilities.__getitem__, reverse=True)
        top_return = sum(returns[index] for index in ranked[:tail_count]) / tail_count
        market_return = sum(returns) / count
        add_metric("top_decile_net_return", top_return, day)
        add_metric("top_decile_excess_return", top_return - market_return, day)
        bottom = ranked[-tail_count:]
        add_metric(
            "worst_decile_net_return",
            sum(returns[index] for index in bottom) / tail_count,
            day,
        )

    methods = {
        "brier_score": ("score", "equal-weight mean of date-market cell Brier scores", "NO_SETTLED_CELL"),
        "brier_skill": ("ratio", "equal-weight mean Brier skill versus each cell prevalence", "BINARY_LABEL_VARIATION_REQUIRED"),
        "auc": ("score", "equal-weight mean pairwise AUC across date-market cells", "BOTH_LABEL_CLASSES_REQUIRED"),
        "ece_10bin": ("score", "equal-weight mean ten-bin ECE across date-market cells", "NO_SETTLED_CELL"),
        "daily_cross_sectional_rank_ic": ("correlation", "equal-weight mean daily market-level Spearman IC of expected utility and net return", "CROSS_SECTIONAL_VARIATION_REQUIRED"),
        "top_decile_net_return": ("ratio", "equal-weight mean realized return of each cell's top expected-utility decile", "NO_SETTLED_CELL"),
        "top_decile_excess_return": ("ratio", "top expected-utility decile return minus its date-market cell mean", "NO_SETTLED_CELL"),
        "worst_decile_net_return": ("ratio", "equal-weight mean realized return of each cell's bottom expected-utility decile", "NO_SETTLED_CELL"),
    }
    metrics = {
        name: _equal_weight_metric(
            metric_cells.get(name, []),
            len(metric_days.get(name, set())),
            cell_count=len(metric_cells.get(name, [])),
            complete_day_count=independent_days,
            unit=unit,
            method=method,
            unavailable_reason=reason,
        )
        for name, (unit, method, reason) in methods.items()
    }

    market_coverage = {}
    for market in model_observation_ledger.VALID_MARKETS:
        counts = market_counts[market]
        total = counts["prediction"]
        settled = counts["SETTLED"]
        market_coverage[market] = {
            "prediction_count": total,
            "pending_maturity_count": counts["PENDING_MATURITY"],
            "pending_data_count": counts["PENDING_DATA"],
            "settled_count": settled,
            "settlement_coverage": round(settled / total, 8) if total else None,
        }

    if prediction_count == 0:
        status = "NO_SAMPLE"
    elif settled_count:
        status = "OBSERVING" if independent_days >= MINIMUM_OBSERVATION_COHORT_DAYS else "EARLY_SAMPLE"
    elif pending_data_count:
        status = "PENDING_DATA"
    elif pending_maturity_count:
        status = "PENDING_MATURITY"
    else:
        status = "UNSETTLED"
    return {
        "schema_version": "model-observation-performance-v1",
        "track": model_observation_ledger.TRACK,
        "status": status,
        "minimum_reliable_independent_cohort_days": MINIMUM_OBSERVATION_COHORT_DAYS,
        "cohort_count": len(normalized_cohorts),
        "prediction_count": prediction_count,
        "pending_maturity_count": pending_maturity_count,
        "pending_data_count": pending_data_count,
        "settled_count": settled_count,
        "untracked_count": untracked_count,
        "invalid_cohort_count": invalid_cohort_count,
        "invalid_batch_count": invalid_batch_count,
        "invalid_outcome_count": invalid_outcome_count,
        "independent_cohort_day_count": independent_days,
        "settled_independent_cohort_day_count": settled_independent_days,
        "complete_metric_cell_count": len(complete_grouped),
        "incomplete_metric_cell_count": incomplete_cell_count,
        "market_coverage": market_coverage,
        "metrics": metrics,
        "included_in_shadow_research": False,
        "included_in_executable_performance": False,
        "authorizes_production": False,
        "authorization_status": "DIAGNOSTIC_ONLY_MANUAL_REVIEW_REQUIRED",
    }


def evaluate_formal_performance(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    cohort_rows, cohort_metadata = select_latest_model_daily_cohort(rows)
    samples, diagnostics = select_formal_cohort(cohort_rows)
    diagnostics["cohort_executable_prediction_count"] = diagnostics["executable_prediction_count"]
    diagnostics["executable_prediction_count"] = cohort_metadata["all_executable_prediction_count"]
    n = len(samples)
    net_returns = [float(row["outcome"]["net_total_return"]) for row in samples]
    probabilities = [float(row["global_decision"]["primary"]["probability"]) for row in samples]
    labels = [1.0 if row["outcome"]["positive_label"] else 0.0 for row in samples]
    utilities = [float(row["global_decision"]["primary"]["expected_net_utility"]) for row in samples]

    mean_return = sum(net_returns) / n if n else None
    positive_rate = sum(labels) / n if n else None
    top_count = 0
    tail_count = 0
    if n:
        top_count = max(1, math.ceil(n * 0.10))
        top_indices = sorted(range(n), key=lambda index: probabilities[index], reverse=True)[:top_count]
        top_positive_rate = sum(labels[index] for index in top_indices) / top_count
        brier = sum((probabilities[index] - labels[index]) ** 2 for index in range(n)) / n
        ece = 0.0
        for bucket in range(10):
            indices = [index for index, probability in enumerate(probabilities) if min(9, int(probability * 10)) == bucket]
            if indices:
                confidence = sum(probabilities[index] for index in indices) / len(indices)
                accuracy = sum(labels[index] for index in indices) / len(indices)
                ece += len(indices) / n * abs(confidence - accuracy)
        tail_count = max(1, math.ceil(n * 0.10))
        expected_shortfall = sum(sorted(net_returns)[:tail_count]) / tail_count
        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0
        for net_return in net_returns:
            equity *= 1.0 + net_return
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    else:
        top_positive_rate = brier = ece = expected_shortfall = max_drawdown = None

    rank_ic = None
    rank_reason = None
    if n < 3:
        rank_reason = "RANK_IC_REQUIRES_AT_LEAST_3_SAMPLES" if n else None
    else:
        rank_ic = _pearson(_average_ranks(utilities), _average_ranks(net_returns))
        if rank_ic is None:
            rank_reason = "RANK_IC_ZERO_VARIANCE"

    metrics = {
        "mean_net_return": _metric(mean_return, n, unit="ratio", method="arithmetic mean of valid net_total_return"),
        "positive_rate": _metric(positive_rate, n, unit="ratio", method="share of valid settlements with net_total_return > 0"),
        "top_decile_positive_rate": _metric(
            top_positive_rate,
            top_count,
            unit="ratio",
            method="positive rate of the highest calibrated-probability decile among independent daily cohort samples",
            minimum=MINIMUM_TAIL_SAMPLE,
        ),
        "selection_rank_ic": _metric(
            rank_ic,
            n,
            unit="correlation",
            method="Spearman correlation across historical selected samples; not a same-day cross-sectional IC",
            unavailable_reason=rank_reason,
        ),
        "brier_score": _metric(brier, n, unit="score", method="mean squared error of calibrated P(R10 > 0)"),
        "ece_10bin": _metric(ece, n, unit="score", method="ten equal-width probability bins weighted by sample count"),
        "expected_shortfall_10pct": _metric(
            expected_shortfall,
            tail_count,
            unit="ratio",
            method="mean of the worst ceil(10%) independent daily cohort net returns",
            minimum=MINIMUM_TAIL_SAMPLE,
        ),
        "settlement_sequence_max_drawdown": _metric(
            max_drawdown,
            n,
            unit="ratio",
            method="compounded terminal returns ordered by exit_at; not a marked-to-market portfolio drawdown",
        ),
        "comparable_sample_count": _metric(n, n, unit="count", method="unique identity-consistent valid executable settlements"),
    }
    model_ids = [cohort_metadata["cohort_model_id"]] if cohort_metadata["cohort_model_id"] else []
    label_versions = [cohort_metadata["cohort_label_version"]] if cohort_metadata["cohort_label_version"] else []
    return {
        "schema_version": PERFORMANCE_SCHEMA,
        "cohort": "global-10d-v1/executable/settled",
        "sample_status": "NO_SAMPLE" if n == 0 else "READY" if n >= MINIMUM_RELIABLE_SAMPLE else "EARLY_SAMPLE",
        "minimum_reliable_sample": MINIMUM_RELIABLE_SAMPLE,
        "sample_count": n,
        "model_ids": model_ids,
        "label_versions": label_versions,
        **cohort_metadata,
        **diagnostics,
        "metrics": metrics,
    }


def _rule_metric_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    samples = [dict(row) for row in rows if row.get("status") == "SETTLED"]
    count = len(samples)
    returns = [float(row["net_total_return"]) for row in samples]
    excess = [float(row["net_excess_return"]) for row in samples]
    adverse = [float(row["maximum_adverse_excursion"]) for row in samples]
    primary = [float(row["net_total_return"]) for row in samples if row.get("is_primary") is True]
    if count:
        ordered = sorted(returns)
        middle = count // 2
        median = (
            ordered[middle]
            if count % 2
            else (ordered[middle - 1] + ordered[middle]) / 2.0
        )
        tail_count = max(1, math.ceil(count * 0.10))
        expected_shortfall = sum(ordered[:tail_count]) / tail_count
    else:
        median = expected_shortfall = None
        tail_count = 0
    metrics = {
        "mean_net_return": _metric(
            sum(returns) / count if count else None,
            count,
            unit="ratio",
            method="arithmetic mean of immutable next-open to tenth-close net returns",
        ),
        "median_net_return": _metric(
            median,
            count,
            unit="ratio",
            method="median immutable net return",
        ),
        "positive_rate": _metric(
            sum(value > 0 for value in returns) / count if count else None,
            count,
            unit="ratio",
            method="share of rule settlements with net_total_return greater than zero",
        ),
        "top1_net_return": _metric(
            sum(primary) / len(primary) if primary else None,
            len(primary),
            unit="ratio",
            method="mean realized net return of rows frozen as the published primary pick",
        ),
        "mean_net_excess_return": _metric(
            sum(excess) / count if count else None,
            count,
            unit="ratio",
            method="mean net return minus exact-window registered benchmark net return",
        ),
        "expected_shortfall_10pct": _metric(
            expected_shortfall,
            tail_count,
            unit="ratio",
            method="mean of worst ceil(10%) immutable rule net returns",
            minimum=MINIMUM_TAIL_SAMPLE,
        ),
        "mean_maximum_adverse_excursion": _metric(
            sum(adverse) / count if count else None,
            count,
            unit="ratio",
            method="mean lowest adjusted low versus entry open across each ten-session window",
        ),
        "worst_maximum_adverse_excursion": _metric(
            min(adverse) if adverse else None,
            count,
            unit="ratio",
            method="worst adjusted maximum adverse excursion among immutable rule settlements",
        ),
    }
    return {
        "sample_count": count,
        "primary_sample_count": len(primary),
        "metrics": metrics,
    }


def evaluate_rule_outcome_performance(
    batches: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Summarize rule qualifications without mixing them into probability stats."""

    values = list((batches or {}).values()) if isinstance(batches, Mapping) else list(batches or [])
    prediction_count = pending_maturity = pending_data = invalid_batch_count = 0
    raw_settled: list[dict[str, Any]] = []
    date_market_cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    snapshot_count = 0
    for raw in values:
        try:
            batch = rule_outcome_ledger.validate_rule_outcome_batch(raw)
        except (rule_outcome_ledger.RuleOutcomeContractError, rule_outcome_ledger.RuleOutcomeConflictError):
            invalid_batch_count += 1
            continue
        snapshot_count += 1
        prediction_count += int(batch["prediction_count"])
        pending_maturity += int(batch["status_counts"].get("PENDING_MATURITY", 0))
        pending_data += int(batch["status_counts"].get("PENDING_DATA", 0))
        for raw_row in batch["outcomes"]:
            row = dict(raw_row)
            date_market_cells[(str(batch["signal_date"]), str(row.get("market") or ""))].append(row)
            if row.get("status") == "SETTLED":
                raw_settled.append(row)
    settled: list[dict[str, Any]] = []
    complete_cell_count = incomplete_cell_count = data_incomplete_cell_count = 0
    for rows in date_market_cells.values():
        if rows and all(row.get("status") == "SETTLED" for row in rows):
            complete_cell_count += 1
            settled.extend(rows)
        else:
            incomplete_cell_count += 1
            if any(row.get("status") == "PENDING_DATA" for row in rows):
                data_incomplete_cell_count += 1
    primary_rows = [row for row in settled if row.get("is_primary") is True]
    per_market = {
        market: _rule_metric_summary(row for row in settled if row.get("market") == market)
        for market in rule_outcome_ledger.VALID_MARKETS
    }
    per_track = {
        track: _rule_metric_summary(
            row for row in settled if row.get("qualification_track") == track
        )
        for track in sorted(rule_outcome_ledger.VALID_TRACKS)
    }
    if not prediction_count and not invalid_batch_count:
        status = "NO_SAMPLE"
    elif invalid_batch_count:
        status = "PARTIAL_DATA" if raw_settled else "INVALID_DATA"
    elif pending_data:
        status = "PARTIAL_DATA" if raw_settled else "PENDING_DATA"
    elif settled:
        status = "READY" if len(primary_rows) >= MINIMUM_RELIABLE_SAMPLE else "EARLY_SAMPLE"
    else:
        status = "PENDING_MATURITY"
    return {
        "schema_version": "rule-outcome-performance-v1",
        "track": rule_outcome_ledger.TRACK,
        "status": status,
        "minimum_reliable_primary_sample": MINIMUM_RELIABLE_SAMPLE,
        "snapshot_count": snapshot_count,
        "prediction_count": prediction_count,
        "pending_maturity_count": pending_maturity,
        "pending_data_count": pending_data,
        "settled_count": len(raw_settled),
        "metric_eligible_settled_count": len(settled),
        "excluded_partial_cell_settled_count": len(raw_settled) - len(settled),
        "complete_date_market_cell_count": complete_cell_count,
        "incomplete_date_market_cell_count": incomplete_cell_count,
        "data_incomplete_date_market_cell_count": data_incomplete_cell_count,
        "settlement_coverage": round(len(raw_settled) / prediction_count, 6) if prediction_count else None,
        "invalid_batch_count": invalid_batch_count,
        "primary_picks": _rule_metric_summary(primary_rows),
        "all_qualified": _rule_metric_summary(settled),
        "per_market": per_market,
        "per_qualification_track": per_track,
        "included_in_calibrated_probability_statistics": False,
        "included_in_shadow_research": False,
        "included_in_executable_performance": False,
        "authorizes_production": False,
        "authorization_status": "DIAGNOSTIC_RULE_OUTCOMES_ONLY",
    }


def build_history_evaluation(
    rows: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]] | None = None,
    shadow_inventory: dict[str, Any] | None = None,
    executable_inventory: dict[str, Any] | None = None,
    rule_outcome_batches: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshots = snapshots or {}
    shadow_inventory = shadow_inventory or empty_ledger_inventory(SHADOW_TRACK)
    executable_inventory = executable_inventory or empty_ledger_inventory(EXECUTABLE_TRACK)
    return {
        "schema_version": HISTORY_EVALUATION_SCHEMA,
        "performance": evaluate_formal_performance(rows),
        "shadow_ledger": ledger_statistics(snapshots, shadow_inventory, SHADOW_TRACK),
        "executable_ledger": ledger_statistics(snapshots, executable_inventory, EXECUTABLE_TRACK),
        "rule_outcome_tracking": evaluate_rule_outcome_performance(rule_outcome_batches),
    }

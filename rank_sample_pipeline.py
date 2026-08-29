"""Point-in-time join from frozen observations to mature excess-return labels."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any

import model_observation_ledger
import observation_outcome_ledger
import ten_day_rank_model


FEATURE_NAMES = (
    "return_1d_pct",
    "return_5d_pct",
    "return_10d_pct",
    "return_20d_pct",
    "residual_momentum_20d",
    "volatility_20d",
    "opening_gap_pct",
    "adv_20d",
    "turnover_pct",
    "beta_60d",
    "pe_ttm",
    "pb",
    "data_quality_score",
    "event_age_days",
    "event_severity",
    "industry_strength",
    "technical_score",
    "liquidity_flow_score",
    "quality_score",
    "event_score",
    "rule_score",
    "legacy_recommendation",
    "market_regime_score",
)
FEATURE_SCHEMA_VERSION = ten_day_rank_model.FEATURE_SCHEMA_VERSION
PROVENANCE_SCHEMA_VERSION = "rank-sample-provenance-v1"
LABEL_SCHEMA_VERSION = "ten-session-net-excess-label-v1"
COST_VERSION = "market-round-trip-cost-v1"
CURRENCIES = {"a_share": "CNY", "hk": "HKD", "us": "USD"}
REGIME_VALUES = {"bear": -1.0, "range": 0.0, "bull": 1.0, "risk_off": -1.0, "risk_on": 1.0}
ALIASES = {
    "technical": "technical_score",
    "industry": "industry_strength",
    "liquidity_flow": "liquidity_flow_score",
    "quality": "quality_score",
    "event": "event_score",
    "legacy_recommendation_degree": "legacy_recommendation",
    "return_5d": "return_5d_pct",
    "return_10d": "return_10d_pct",
    "return_20d": "return_20d_pct",
    "gap_pct": "opening_gap_pct",
    "volatility": "volatility_20d",
    "beta": "beta_60d",
    "pe": "pe_ttm",
}


class RankSampleError(ValueError):
    """The point-in-time feature/label join is not safe for training."""


def _digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _aware(value: Any, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise RankSampleError(f"{field} must be timezone-aware") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RankSampleError(f"{field} must be timezone-aware")
    return parsed


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _label(observation: Mapping[str, Any], settlement: Mapping[str, Any]) -> ten_day_rank_model.ExcessReturnLabel:
    if settlement.get("status") != "SETTLED":
        raise RankSampleError("rank sample requires a settled outcome")
    for field in ("observation_id", "prediction_sha256", "market", "code"):
        if settlement.get(field) != observation.get(field):
            raise RankSampleError(f"settlement identity mismatch: {field}")
    if settlement.get("corporate_action_adjusted") is not True:
        raise RankSampleError("stock outcome is not corporate-action adjusted")
    raw = settlement.get("rank_label")
    if not isinstance(raw, Mapping) or raw.get("schema_version") != LABEL_SCHEMA_VERSION:
        raise RankSampleError("registered benchmark label is missing")
    market = str(observation.get("market") or "")
    if market not in ten_day_rank_model.REGISTERED_BENCHMARKS:
        raise RankSampleError("sample market is invalid")
    if observation.get("currency") != CURRENCIES[market]:
        raise RankSampleError("sample currency is inconsistent with its market")
    if raw.get("benchmark_code") != ten_day_rank_model.REGISTERED_BENCHMARKS[market]:
        raise RankSampleError("benchmark is not registered for the sample market")
    if raw.get("transaction_cost_version") != COST_VERSION:
        raise RankSampleError("rank label cost version is invalid")
    if raw.get("corporate_action_adjusted") is not True:
        raise RankSampleError("rank label is not adjusted")
    if raw.get("entry_date") != observation.get("entry_trade_date") or raw.get("exit_date") != observation.get("forecast_end_trade_date"):
        raise RankSampleError("rank label window is not aligned to the frozen prediction")
    expected_cost = ten_day_rank_model.TRANSACTION_COSTS[market]
    if _finite(observation.get("transaction_cost")) != expected_cost:
        raise RankSampleError("observation transaction cost is not versioned market cost")
    if _finite(raw.get("stock_transaction_cost")) != expected_cost or _finite(raw.get("benchmark_transaction_cost")) != expected_cost:
        raise RankSampleError("stock and benchmark costs are not aligned")
    status = str(observation.get("security_status") or "ACTIVE").upper()
    if status in {"DELISTED_BEFORE_SIGNAL", "INACTIVE_AT_SIGNAL"}:
        raise RankSampleError("security was not investable at signal time")
    if status == "DELISTED" and raw.get("delisting_treatment") != "terminal_adjusted_return_v1":
        raise RankSampleError("delisted security lacks a terminal adjusted return")
    try:
        return ten_day_rank_model.ExcessReturnLabel(
            market=market,
            benchmark_code=str(raw["benchmark_code"]),
            entry_date=str(raw["entry_date"]),
            exit_date=str(raw["exit_date"]),
            stock_entry_price=float(raw["stock_entry_price"]),
            stock_exit_price=float(raw["stock_exit_price"]),
            benchmark_entry_price=float(raw["benchmark_entry_price"]),
            benchmark_exit_price=float(raw["benchmark_exit_price"]),
            stock_transaction_cost=float(raw["stock_transaction_cost"]),
            benchmark_transaction_cost=float(raw["benchmark_transaction_cost"]),
            stock_gross_return=float(raw["stock_gross_return"]),
            stock_net_return=float(raw["stock_net_return"]),
            benchmark_gross_return=float(raw["benchmark_gross_return"]),
            benchmark_net_return=float(raw["benchmark_net_return"]),
            net_excess_return=float(raw["net_excess_return"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RankSampleError("rank label arithmetic is invalid") from exc


def _feature_records(observation: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    cutoff = _aware(
        observation.get("signal_at") or observation.get("generated_at") or observation.get("scheduled_slot"),
        "signal_at",
    )
    if observation.get("entry_session_open_at") is not None:
        entry_open = _aware(observation.get("entry_session_open_at"), "entry_session_open_at")
        if cutoff >= entry_open:
            raise RankSampleError("feature cutoff is not strictly before entry-session open")
    raw_values = observation.get("feature_values")
    if isinstance(raw_values, Mapping):
        raw_values = [
            {"name": name, **(dict(value) if isinstance(value, Mapping) else {"value": value})}
            for name, value in raw_values.items()
        ]
    if not isinstance(raw_values, list):
        raise RankSampleError("point-in-time feature values are missing")
    supplied: dict[str, dict[str, Any]] = {}
    for item in raw_values:
        if not isinstance(item, Mapping):
            raise RankSampleError("feature value must be an object")
        name = ALIASES.get(str(item.get("name") or ""), str(item.get("name") or ""))
        if name not in FEATURE_NAMES:
            continue
        if name in supplied:
            raise RankSampleError(f"duplicate point-in-time feature: {name}")
        observed_at = _aware(item.get("observed_at"), f"feature.{name}.observed_at")
        if observed_at > cutoff:
            raise RankSampleError(f"feature observed after signal time: {name}")
        source = str(item.get("source") or "")
        schema = str(item.get("schema_version") or "")
        if not source or not schema:
            raise RankSampleError(f"feature provenance is incomplete: {name}")
        missing = item.get("missing") is True or item.get("value") is None
        value = None if missing else _finite(item.get("value"))
        if not missing and value is None:
            raise RankSampleError(f"feature value is non-finite: {name}")
        identity = {
            "name": name,
            "value": value,
            "missing": missing,
            "observed_at": observed_at.isoformat(timespec="seconds"),
            "source": source,
            "schema_version": schema,
            "observation_id": observation.get("observation_id"),
            "prediction_sha256": observation.get("prediction_sha256"),
        }
        provenance = _digest(identity)
        if item.get("provenance_sha256") not in (None, provenance):
            raise RankSampleError(f"feature provenance hash mismatch: {name}")
        identity["provenance_sha256"] = provenance
        supplied[name] = identity
    records: list[dict[str, Any]] = []
    for name in FEATURE_NAMES:
        if name in supplied:
            records.append(supplied[name])
            continue
        identity = {
            "name": name,
            "value": None,
            "missing": True,
            "observed_at": cutoff.isoformat(timespec="seconds"),
            "source": "missing_at_signal",
            "schema_version": FEATURE_SCHEMA_VERSION,
            "observation_id": observation.get("observation_id"),
            "prediction_sha256": observation.get("prediction_sha256"),
        }
        identity["provenance_sha256"] = _digest(identity)
        records.append(identity)
    return tuple(records)


def build_rank_sample(
    observation: Mapping[str, Any],
    settlement: Mapping[str, Any],
) -> ten_day_rank_model.RankSample:
    """Join one immutable feature observation to its exact mature label."""

    if not isinstance(observation, Mapping) or not isinstance(settlement, Mapping):
        raise RankSampleError("rank sample inputs must be objects")
    label = _label(observation, settlement)
    records = _feature_records(observation)
    features: list[float] = []
    for record in records:
        features.extend((float(record["value"] or 0.0), 1.0 if record["missing"] else 0.0))
    signal_date = str(observation.get("prediction_as_of") or observation.get("signal_date") or "")[:10]
    provenance = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "observation_id": observation.get("observation_id"),
        "prediction_sha256": observation.get("prediction_sha256"),
        "outcome_sha256": settlement.get("outcome_sha256"),
        "feature_provenance": [record["provenance_sha256"] for record in records],
        "label": dict(settlement["rank_label"]),
    }
    regime_record = next(record for record in records if record["name"] == "market_regime_score")
    regime = str(observation.get("market_regime") or "unknown")
    if regime == "unknown" and not regime_record["missing"]:
        regime = str(regime_record["value"])
    try:
        return ten_day_rank_model.RankSample(
            market=str(observation["market"]),
            code=str(observation["code"]),
            signal_date=signal_date,
            entry_date=str(observation["entry_trade_date"]),
            exit_date=str(observation["forecast_end_trade_date"]),
            features=tuple(features),
            label=label,
            feature_records=records,
            provenance_sha256=_digest(provenance),
            market_regime=regime,
            source_observation_id=str(observation.get("observation_id") or ""),
            currency=str(observation.get("currency") or ""),
            transaction_cost_version=COST_VERSION,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RankSampleError("rank sample identity is invalid") from exc


def validate_rank_samples(
    samples: Sequence[ten_day_rank_model.RankSample],
) -> list[ten_day_rank_model.RankSample]:
    ordered = sorted(samples, key=lambda row: (row.signal_date, row.market, row.code))
    seen: set[tuple[str, str, str]] = set()
    width: int | None = None
    for sample in ordered:
        identity = (sample.signal_date, sample.market, sample.code)
        if identity in seen:
            raise RankSampleError("duplicate date-market-symbol rank sample")
        seen.add(identity)
        if width is None:
            width = len(sample.features)
        elif len(sample.features) != width:
            raise RankSampleError("rank sample feature widths differ")
        if sample.currency and sample.currency != CURRENCIES[sample.market]:
            raise RankSampleError("rank sample currency is inconsistent")
        if sample.transaction_cost_version and sample.transaction_cost_version != COST_VERSION:
            raise RankSampleError("rank sample cost version is inconsistent")
    return ordered


def _member_features(snapshot: Mapping[str, Any], prediction: Mapping[str, Any], signal_at: str) -> dict[str, Any]:
    market = str(prediction.get("market") or "")
    code = str(prediction.get("code") or "")
    section = (((snapshot.get("point_in_time_universe") or {}).get("markets") or {}).get(market) or {})
    members = section.get("members") or []
    member = next(
        (row for row in members if isinstance(row, Mapping) and str(row.get("code") or "") == code),
        None,
    )
    if not isinstance(member, Mapping):
        raise RankSampleError("source snapshot has no point-in-time universe member")
    raw = member.get("feature_snapshot")
    if not isinstance(raw, Mapping):
        raise RankSampleError("point-in-time feature snapshot is missing")
    feature_cutoff = str(snapshot.get("feature_cutoff_at") or signal_at)
    observed_at = str(member.get("observed_at") or signal_at)
    source = str(member.get("source") or "point_in_time_universe")
    feature_values: list[dict[str, Any]] = []
    flattened = dict(raw)
    for original, value in flattened.items():
        name = ALIASES.get(str(original), str(original))
        if name not in FEATURE_NAMES:
            continue
        feature_values.append(
            {
                "name": name,
                "value": value,
                "missing": value is None,
                "observed_at": observed_at,
                "source": source,
                "schema_version": str(prediction.get("feature_schema_version") or FEATURE_SCHEMA_VERSION),
            }
        )
    regime_raw = (((snapshot.get("markets") or {}).get(market) or {}).get("market_regime") or {})
    regime = regime_raw.get("state") if isinstance(regime_raw, Mapping) else regime_raw
    if isinstance(regime, str):
        feature_values.append(
            {
                "name": "market_regime_score",
                "value": REGIME_VALUES.get(regime.lower()),
                "missing": regime.lower() not in REGIME_VALUES,
                "observed_at": observed_at,
                "source": "snapshot_market_regime",
                "schema_version": FEATURE_SCHEMA_VERSION,
            }
        )
    evaluated_candidates = ((snapshot.get("global_decision") or {}).get("evaluated_candidates") or [])
    evaluated = next(
        (
            row
            for row in evaluated_candidates
            if isinstance(row, Mapping)
            and str(row.get("market") or "") == market
            and str(row.get("code") or "") == code
        ),
        None,
    )
    existing_feature_names = {str(row.get("name") or "") for row in feature_values}
    if (
        "data_quality_score" not in existing_feature_names
        and isinstance(evaluated, Mapping)
        and _finite(evaluated.get("data_quality_score")) is not None
    ):
        feature_values.append(
            {
                "name": "data_quality_score",
                "value": float(evaluated["data_quality_score"]),
                "missing": False,
                "observed_at": observed_at,
                "source": "frozen_global_candidate",
                "schema_version": FEATURE_SCHEMA_VERSION,
            }
        )
    matching_events = [
        item
        for item in ((snapshot.get("events") or {}).get("items") or [])
        if isinstance(item, Mapping)
        and str(item.get("market") or "") == market
        and str(item.get("symbol") or item.get("code") or "") == code
        and item.get("evidence_status") == "verified"
    ]
    if matching_events:
        matching_events.sort(
            key=lambda item: str(
                item.get("effective_at") or item.get("published_at") or item.get("released_at") or ""
            ),
            reverse=True,
        )
        event = matching_events[0]
        published = event.get("effective_at") or event.get("published_at") or event.get("released_at")
        event_observed = (
            event.get("ingested_at")
            or ((snapshot.get("events") or {}).get("pipeline") or {}).get("scanned_at")
            or observed_at
        )
        try:
            age_days = max(
                0.0,
                (_aware(feature_cutoff, "feature_cutoff_at") - _aware(published, "event.published_at")).total_seconds()
                / 86400.0,
            )
        except RankSampleError:
            age_days = None
        materiality = str(event.get("materiality") or "unknown").lower()
        severity = _finite(event.get("impact_score"))
        if severity is None:
            severity = {"high": 1.0, "medium": 0.6, "low": 0.25}.get(materiality)
        for name, value in (("event_age_days", age_days), ("event_severity", severity)):
            if name in existing_feature_names:
                continue
            feature_values.append(
                {
                    "name": name,
                    "value": value,
                    "missing": value is None,
                    "observed_at": event_observed,
                    "source": str(event.get("source") or "official_event_pipeline"),
                    "schema_version": FEATURE_SCHEMA_VERSION,
                }
            )
    return {
        **dict(prediction),
        # New snapshots publish the actual feature freeze time after all
        # sources have returned.  Legacy snapshots used generated_at as a run
        # start marker; those rows fail closed if a member was observed later.
        "signal_at": feature_cutoff,
        "feature_values": feature_values,
        "security_status": str(member.get("security_status") or "ACTIVE"),
        "market_regime": str(regime or "unknown"),
    }


def load_mature_rank_samples(
    observations_dir: pathlib.Path = model_observation_ledger.DEFAULT_OBSERVATION_DIRECTORY,
    outcomes_dir: pathlib.Path = observation_outcome_ledger.DEFAULT_OUTCOME_DIRECTORY,
    snapshots_dir: pathlib.Path | None = None,
    *,
    return_diagnostics: bool = False,
) -> list[ten_day_rank_model.RankSample] | tuple[list[ten_day_rank_model.RankSample], dict[str, int]]:
    """Load only complete immutable joins; no network or inferred labels."""

    snapshots_root = pathlib.Path(snapshots_dir or pathlib.Path(__file__).resolve().parent / "data" / "picks")
    cohorts = model_observation_ledger.load_observation_cohorts(pathlib.Path(observations_dir))
    batches = observation_outcome_ledger.load_outcome_batches(pathlib.Path(outcomes_dir))
    diagnostics = {
        "cohort_count": len(cohorts),
        "settled_outcome_count": 0,
        "rank_label_count": 0,
        "sample_count": 0,
        "excluded_missing_rank_label_count": 0,
        "excluded_missing_snapshot_count": 0,
        "excluded_unbound_snapshot_count": 0,
        "excluded_invalid_feature_count": 0,
        "excluded_missing_outcome_batch_count": 0,
        "excluded_invalid_revision_count": 0,
        "excluded_unsettled_outcome_count": 0,
        "excluded_pending_maturity_outcome_count": 0,
        "excluded_pending_data_outcome_count": 0,
        "excluded_other_unsettled_outcome_count": 0,
        "excluded_incomplete_market_cell_count": 0,
        "excluded_data_incomplete_market_cell_count": 0,
        "excluded_incomplete_market_cell_sample_count": 0,
    }
    samples: list[ten_day_rank_model.RankSample] = []
    for cohort_id, cohort in sorted(cohorts.items()):
        batch = batches.get(cohort_id)
        if not isinstance(batch, Mapping):
            diagnostics["excluded_missing_outcome_batch_count"] += 1
            continue
        try:
            batch = observation_outcome_ledger.validate_outcome_batch(
                batch,
                cohort=cohort,
            )
        except (
            observation_outcome_ledger.ObservationOutcomeContractError,
            observation_outcome_ledger.ObservationOutcomeConflictError,
        ) as exc:
            raise RankSampleError(
                f"observation outcome cohort binding is invalid: {cohort_id}"
            ) from exc
        revision_id = cohort.get("canonical_revision_id")
        revision = next(
            (row for row in cohort.get("revisions") or [] if row.get("revision_id") == revision_id),
            None,
        )
        if not isinstance(revision, Mapping):
            diagnostics["excluded_invalid_revision_count"] += 1
            continue
        predictions = {row["observation_id"]: row for row in revision.get("predictions") or []}
        rank_outcomes = [
            outcome
            for outcome in (batch.get("outcomes") or [])
            if outcome.get("status") == "SETTLED"
            and isinstance(outcome.get("rank_label"), Mapping)
        ]
        if revision.get("schema_version") != model_observation_ledger.REVISION_SCHEMA_VERSION:
            diagnostics["settled_outcome_count"] += sum(
                outcome.get("status") == "SETTLED"
                for outcome in (batch.get("outcomes") or [])
            )
            diagnostics["rank_label_count"] += len(rank_outcomes)
            diagnostics["excluded_unbound_snapshot_count"] += len(rank_outcomes)
            continue
        snapshot_path = snapshots_root / str(revision.get("source_snapshot") or "")
        snapshot: dict[str, Any] | None = None
        if snapshot_path.is_file():
            try:
                loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
                snapshot = loaded if isinstance(loaded, dict) else None
            except (OSError, ValueError):
                snapshot = None
        if snapshot is not None:
            try:
                model_observation_ledger.validate_source_snapshot_binding(
                    snapshot,
                    revision,
                )
            except (
                model_observation_ledger.ObservationContractError,
                model_observation_ledger.ObservationConflictError,
            ) as exc:
                raise RankSampleError(
                    f"source snapshot binding is invalid: {revision.get('source_snapshot')}"
                ) from exc
        expected_by_market: dict[str, int] = {}
        for prediction in predictions.values():
            market = str(prediction.get("market") or "")
            expected_by_market[market] = expected_by_market.get(market, 0) + 1
        cell_samples: dict[str, list[ten_day_rank_model.RankSample]] = {
            market: [] for market in expected_by_market
        }
        cell_complete = {market: True for market in expected_by_market}
        cell_data_defect = {market: False for market in expected_by_market}
        for outcome in batch.get("outcomes") or []:
            market = str(outcome.get("market") or "")
            if outcome.get("status") != "SETTLED":
                diagnostics["excluded_unsettled_outcome_count"] += 1
                status = str(outcome.get("status") or "")
                if status == "PENDING_MATURITY":
                    diagnostics["excluded_pending_maturity_outcome_count"] += 1
                elif status == "PENDING_DATA":
                    diagnostics["excluded_pending_data_outcome_count"] += 1
                    cell_data_defect[market] = True
                else:
                    diagnostics["excluded_other_unsettled_outcome_count"] += 1
                    cell_data_defect[market] = True
                cell_complete[market] = False
                continue
            diagnostics["settled_outcome_count"] += 1
            if not isinstance(outcome.get("rank_label"), Mapping):
                diagnostics["excluded_missing_rank_label_count"] += 1
                cell_complete[market] = False
                cell_data_defect[market] = True
                continue
            diagnostics["rank_label_count"] += 1
            prediction = predictions.get(outcome.get("observation_id"))
            if snapshot is None or not isinstance(prediction, Mapping):
                diagnostics["excluded_missing_snapshot_count"] += 1
                cell_complete[market] = False
                cell_data_defect[market] = True
                continue
            try:
                enriched = _member_features(snapshot, prediction, str(revision.get("generated_at") or ""))
                cell_samples[market].append(build_rank_sample(enriched, outcome))
            except RankSampleError:
                diagnostics["excluded_invalid_feature_count"] += 1
                cell_complete[market] = False
                cell_data_defect[market] = True
        for market, expected_count in expected_by_market.items():
            complete_rows = cell_samples.get(market, [])
            if cell_complete.get(market) is True and len(complete_rows) == expected_count:
                samples.extend(complete_rows)
                continue
            diagnostics["excluded_incomplete_market_cell_count"] += 1
            if cell_data_defect.get(market) is True:
                diagnostics["excluded_data_incomplete_market_cell_count"] += 1
            diagnostics["excluded_incomplete_market_cell_sample_count"] += len(complete_rows)
    samples = validate_rank_samples(samples)
    diagnostics["sample_count"] = len(samples)
    return (samples, diagnostics) if return_diagnostics else samples


__all__ = [
    "COST_VERSION", "FEATURE_NAMES", "FEATURE_SCHEMA_VERSION", "LABEL_SCHEMA_VERSION",
    "RankSampleError", "build_rank_sample", "load_mature_rank_samples", "validate_rank_samples",
]

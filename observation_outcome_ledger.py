"""Immutable, non-executable outcomes for prospective model observations.

This ledger settles every prediction in the canonical daily observation cohort.
It is deliberately isolated from both SHADOW_RESEARCH and EXECUTABLE_MODEL
performance and can never authorize a model for production use.
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
from collections.abc import Callable, Mapping
from typing import Any

import model_observation_ledger
import market_calendar
import ten_day_rank_model


TRACK = model_observation_ledger.TRACK
BATCH_SCHEMA_VERSION = "model-observation-outcome-cohort-v1"
OUTCOME_SCHEMA_VERSION = "model-observation-outcome-v1"
VALID_STATUSES = {"PENDING_MATURITY", "PENDING_DATA", "SETTLED"}
PENDING_DATA_REASONS = {
    "COMPLETE_ADJUSTED_BARS_MISSING",
    "PRICE_LOADER_CONTRACT_INVALID",
    "UNADJUSTED_PRICE_SOURCE",
    "BENCHMARK_ADJUSTED_BARS_MISSING",
}
VALID_COHORT_ID = re.compile(r"^obscohort_[a-f0-9]{24}$")
VALID_OBSERVATION_ID = re.compile(r"^obs_[a-f0-9]{24}$")
PRICE_DECIMALS = 8
RETURN_DECIMALS = 8
RANK_LABEL_SCHEMA_VERSION = "ten-session-net-excess-label-v1"
RANK_COST_VERSION = "market-round-trip-cost-v1"
DEFAULT_OUTCOME_DIRECTORY = (
    pathlib.Path(__file__).resolve().parent
    / "data"
    / "outcomes"
    / "observation-settlements"
)


class ObservationOutcomeContractError(ValueError):
    """A cohort or price payload cannot form a valid outcome contract."""


class ObservationOutcomeConflictError(RuntimeError):
    """Persisted immutable outcome identity or content conflicts."""


PriceLoader = Callable[[str, str], tuple[list[dict[str, Any]], str, bool]]


def _digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _aware_moment(value: dt.datetime | str) -> dt.datetime:
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        try:
            parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ObservationOutcomeContractError("as_of must be a timezone-aware timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ObservationOutcomeContractError("as_of must be a timezone-aware timestamp")
    return parsed


def _iso_moment(value: dt.datetime | str) -> str:
    return _aware_moment(value).isoformat(timespec="seconds")


def _finite_positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _strict_adjusted_bar_index(
    rows: list[dict[str, Any]],
    market: str,
    as_of: dt.datetime,
) -> dict[str, Mapping[str, Any]] | None:
    """Index canonical adjusted daily bars without hiding ambiguous evidence."""

    latest_legal_date = market_calendar.market_local_date(market, as_of).isoformat()
    indexed: dict[str, Mapping[str, Any]] = {}
    previous_date: str | None = None
    for item in rows:
        if not isinstance(item, Mapping):
            return None
        raw_date = item.get("date")
        if not isinstance(raw_date, str):
            return None
        try:
            parsed_date = dt.date.fromisoformat(raw_date)
        except ValueError:
            return None
        date_text = parsed_date.isoformat()
        if (
            raw_date != date_text
            or date_text > latest_legal_date
            or date_text in indexed
            or (previous_date is not None and date_text <= previous_date)
        ):
            return None
        indexed[date_text] = item
        previous_date = date_text
    return indexed


def _canonical_revision(cohort: Mapping[str, Any]) -> dict[str, Any]:
    revision_id = cohort.get("canonical_revision_id")
    revision = next(
        (
            item
            for item in (cohort.get("revisions") or [])
            if isinstance(item, Mapping) and item.get("revision_id") == revision_id
        ),
        None,
    )
    if revision is None:
        raise ObservationOutcomeContractError("observation cohort has no canonical revision")
    return dict(revision)


def _row_digest(row: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in row.items() if key != "outcome_sha256"})


def _batch_digest(batch: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in batch.items() if key != "batch_sha256"})


def _base_outcome(
    cohort: Mapping[str, Any],
    revision: Mapping[str, Any],
    prediction: Mapping[str, Any],
) -> dict[str, Any]:
    observation_id = str(prediction.get("observation_id") or "")
    if VALID_OBSERVATION_ID.fullmatch(observation_id) is None:
        raise ObservationOutcomeContractError("observation_id is invalid")
    expected_contract = model_observation_ledger.settlement_contract_sha256(prediction)
    if prediction.get("settlement_contract_sha256") != expected_contract:
        raise ObservationOutcomeConflictError(
            f"settlement contract digest mismatch: {observation_id}"
        )
    return {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "track": TRACK,
        "cohort_id": cohort["cohort_id"],
        "canonical_revision_id": cohort["canonical_revision_id"],
        "observation_id": observation_id,
        "prediction_sha256": prediction["prediction_sha256"],
        "settlement_contract_sha256": expected_contract,
        "source_snapshot": revision["source_snapshot"],
        "scheduled_slot": cohort["scheduled_slot"],
        "model_id": prediction["model_id"],
        "label_version": prediction["label_version"],
        "feature_schema_version": prediction.get("feature_schema_version"),
        "artifact_sha256": prediction["artifact_sha256"],
        "market": prediction["market"],
        "code": prediction["code"],
        "probability": prediction["probability"],
        "expected_net_return": prediction["expected_net_return"],
        "expected_net_utility": prediction["expected_net_utility"],
        "tail_risk": prediction["tail_risk"],
        "transaction_cost": prediction["transaction_cost"],
        "entry_trade_date": prediction["entry_trade_date"],
        "entry_session_open_at": prediction["entry_session_open_at"],
        "forecast_end_trade_date": prediction["forecast_end_trade_date"],
        "forecast_end_session_close_at": prediction["forecast_end_session_close_at"],
        "horizon_trade_sessions": prediction["horizon_trade_sessions"],
        "entry_policy": prediction["entry_policy"],
        "exit_policy": prediction["exit_policy"],
        "calendar_id": prediction["calendar_id"],
        "calendar_version": prediction["calendar_version"],
        "currency": prediction["currency"],
        "included_in_shadow_research": False,
        "included_in_executable_performance": False,
        "authorizes_production": False,
    }


def _pending_row(base: dict[str, Any], status: str, reason_code: str) -> dict[str, Any]:
    row = {**base, "status": status, "reason_code": reason_code}
    row["outcome_sha256"] = _row_digest(row)
    return row


def _price_evidence(
    prediction: Mapping[str, Any],
    *,
    source: str,
    entry_price: float,
    exit_price: float,
) -> dict[str, Any]:
    evidence = {
        "schema_version": "model-observation-price-evidence-v1",
        "source": source,
        "corporate_action_adjusted": True,
        "entry_bar": {
            "date": prediction["entry_trade_date"],
            "field": "open",
            "value": entry_price,
        },
        "exit_bar": {
            "date": prediction["forecast_end_trade_date"],
            "field": "close",
            "value": exit_price,
        },
    }
    evidence["evidence_sha256"] = _digest(evidence)
    return evidence


def _settled_row(
    base: dict[str, Any],
    prediction: Mapping[str, Any],
    as_of: dt.datetime,
    price_loader: PriceLoader,
    benchmark_price_loader: PriceLoader | None = None,
) -> dict[str, Any]:
    try:
        loaded = price_loader(str(prediction["market"]), str(prediction["code"]))
    except Exception:
        loaded = ([], "", False)
    if not isinstance(loaded, tuple) or len(loaded) != 3:
        return _pending_row(base, "PENDING_DATA", "PRICE_LOADER_CONTRACT_INVALID")
    rows, source, adjusted = loaded
    if not isinstance(rows, list) or not isinstance(source, str) or not adjusted:
        reason = "UNADJUSTED_PRICE_SOURCE" if rows and not adjusted else "COMPLETE_ADJUSTED_BARS_MISSING"
        return _pending_row(base, "PENDING_DATA", reason)
    by_date = _strict_adjusted_bar_index(
        rows,
        str(prediction["market"]),
        as_of,
    )
    if by_date is None:
        return _pending_row(base, "PENDING_DATA", "COMPLETE_ADJUSTED_BARS_MISSING")
    entry = _finite_positive((by_date.get(str(prediction["entry_trade_date"])) or {}).get("open"))
    exit_ = _finite_positive((by_date.get(str(prediction["forecast_end_trade_date"])) or {}).get("close"))
    if entry is None or exit_ is None or not source:
        return _pending_row(base, "PENDING_DATA", "COMPLETE_ADJUSTED_BARS_MISSING")
    published_entry = round(entry, PRICE_DECIMALS)
    published_exit = round(exit_, PRICE_DECIMALS)
    gross = round(published_exit / published_entry - 1.0, RETURN_DECIMALS)
    net = round(gross - float(prediction["transaction_cost"]), RETURN_DECIMALS)
    evidence = _price_evidence(
        prediction,
        source=source,
        entry_price=published_entry,
        exit_price=published_exit,
    )
    row = {
        **base,
        "status": "SETTLED",
        "reason_code": None,
        "entry_at": prediction["entry_session_open_at"],
        "entry_price": published_entry,
        "entry_source": source,
        "exit_at": prediction["forecast_end_session_close_at"],
        "exit_price": published_exit,
        "exit_source": source,
        "gross_total_return": gross,
        "net_total_return": net,
        "positive_label": net > 0,
        "corporate_action_adjusted": True,
        "price_evidence": evidence,
        "price_evidence_sha256": evidence["evidence_sha256"],
        "fx_rate_source": "not_required_same_currency_return",
        "settled_at": as_of.isoformat(timespec="seconds"),
    }
    if benchmark_price_loader is not None:
        market = str(prediction["market"])
        benchmark_code = ten_day_rank_model.REGISTERED_BENCHMARKS.get(market)
        expected_cost = ten_day_rank_model.TRANSACTION_COSTS.get(market)
        if benchmark_code is None or expected_cost != float(prediction["transaction_cost"]):
            return _pending_row(base, "PENDING_DATA", "BENCHMARK_ADJUSTED_BARS_MISSING")
        try:
            benchmark_loaded = benchmark_price_loader(market, benchmark_code)
        except Exception:
            benchmark_loaded = ([], "", False)
        if (
            not isinstance(benchmark_loaded, tuple)
            or len(benchmark_loaded) != 3
            or not isinstance(benchmark_loaded[0], list)
            or not isinstance(benchmark_loaded[1], str)
            or not benchmark_loaded[1]
            or benchmark_loaded[2] is not True
        ):
            return _pending_row(base, "PENDING_DATA", "BENCHMARK_ADJUSTED_BARS_MISSING")
        benchmark_rows, benchmark_source, _adjusted = benchmark_loaded
        benchmark_by_date = _strict_adjusted_bar_index(benchmark_rows, market, as_of)
        if benchmark_by_date is None:
            return _pending_row(base, "PENDING_DATA", "BENCHMARK_ADJUSTED_BARS_MISSING")
        benchmark_entry = _finite_positive(
            (benchmark_by_date.get(str(prediction["entry_trade_date"])) or {}).get("open")
        )
        benchmark_exit = _finite_positive(
            (benchmark_by_date.get(str(prediction["forecast_end_trade_date"])) or {}).get("close")
        )
        if benchmark_entry is None or benchmark_exit is None:
            return _pending_row(base, "PENDING_DATA", "BENCHMARK_ADJUSTED_BARS_MISSING")
        benchmark_entry = round(benchmark_entry, PRICE_DECIMALS)
        benchmark_exit = round(benchmark_exit, PRICE_DECIMALS)
        benchmark_gross = round(
            benchmark_exit / benchmark_entry - 1.0,
            RETURN_DECIMALS,
        )
        benchmark_net = round(benchmark_gross - expected_cost, RETURN_DECIMALS)
        rank_label = {
            "schema_version": RANK_LABEL_SCHEMA_VERSION,
            "market": market,
            "benchmark_code": benchmark_code,
            "entry_date": prediction["entry_trade_date"],
            "exit_date": prediction["forecast_end_trade_date"],
            "stock_entry_price": published_entry,
            "stock_exit_price": published_exit,
            "benchmark_entry_price": benchmark_entry,
            "benchmark_exit_price": benchmark_exit,
            "stock_transaction_cost": float(prediction["transaction_cost"]),
            "benchmark_transaction_cost": expected_cost,
            "stock_gross_return": gross,
            "stock_net_return": net,
            "benchmark_gross_return": benchmark_gross,
            "benchmark_net_return": benchmark_net,
            "net_excess_return": round(net - benchmark_net, RETURN_DECIMALS),
            "transaction_cost_version": RANK_COST_VERSION,
            "corporate_action_adjusted": True,
            "stock_price_source": source,
            "benchmark_price_source": benchmark_source,
        }
        row["rank_label"] = rank_label
        row["rank_label_sha256"] = _digest(rank_label)
    row["outcome_sha256"] = _row_digest(row)
    return row


def validate_outcome_batch(
    payload: Mapping[str, Any],
    *,
    cohort: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ObservationOutcomeContractError("observation outcome batch must be an object")
    batch = dict(payload)
    if (
        batch.get("schema_version") != BATCH_SCHEMA_VERSION
        or batch.get("track") != TRACK
        or batch.get("included_in_shadow_research") is not False
        or batch.get("included_in_executable_performance") is not False
        or batch.get("authorizes_production") is not False
    ):
        raise ObservationOutcomeConflictError("observation outcome batch isolation contract is invalid")
    cohort_id = str(batch.get("cohort_id") or "")
    if VALID_COHORT_ID.fullmatch(cohort_id) is None:
        raise ObservationOutcomeContractError("observation outcome cohort_id is invalid")
    rows = batch.get("outcomes")
    if not isinstance(rows, list):
        raise ObservationOutcomeContractError("observation outcomes must be a list")
    evaluated_at = _aware_moment(str(batch.get("evaluated_at") or ""))
    seen: set[str] = set()
    status_counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ObservationOutcomeContractError("every observation outcome must be an object")
        observation_id = str(row.get("observation_id") or "")
        if observation_id in seen or VALID_OBSERVATION_ID.fullmatch(observation_id) is None:
            raise ObservationOutcomeConflictError("observation outcome identity is invalid or duplicated")
        seen.add(observation_id)
        status = row.get("status")
        if status not in VALID_STATUSES:
            raise ObservationOutcomeContractError("observation outcome status is invalid")
        if (
            row.get("schema_version") != OUTCOME_SCHEMA_VERSION
            or row.get("track") != TRACK
            or row.get("included_in_shadow_research") is not False
            or row.get("included_in_executable_performance") is not False
            or row.get("authorizes_production") is not False
        ):
            raise ObservationOutcomeConflictError("observation outcome escaped its isolated track")
        if status == "PENDING_MATURITY" and row.get("reason_code") != "FORECAST_WINDOW_OPEN":
            raise ObservationOutcomeContractError("pending-maturity reason is invalid")
        if status == "PENDING_DATA" and row.get("reason_code") not in PENDING_DATA_REASONS:
            raise ObservationOutcomeContractError("pending-data reason is invalid")
        if status == "SETTLED" and row.get("reason_code") is not None:
            raise ObservationOutcomeContractError("settled observation reason must be empty")
        if status != "SETTLED" and any(
            key in row
            for key in (
                "entry_price",
                "exit_price",
                "gross_total_return",
                "net_total_return",
                "positive_label",
                "settled_at",
                "price_evidence",
                "price_evidence_sha256",
                "rank_label",
                "rank_label_sha256",
            )
        ):
            raise ObservationOutcomeConflictError("pending observation contains settled fields")
        maturity = _aware_moment(str(row.get("forecast_end_session_close_at") or ""))
        if status == "PENDING_MATURITY" and evaluated_at > maturity:
            raise ObservationOutcomeConflictError(
                "pending-maturity observation is already mature"
            )
        if status in {"PENDING_DATA", "SETTLED"} and evaluated_at <= maturity:
            raise ObservationOutcomeConflictError(
                "mature observation status precedes forecast maturity"
            )
        if status == "SETTLED":
            settled_at = _aware_moment(str(row.get("settled_at") or ""))
            if not maturity < settled_at <= evaluated_at:
                raise ObservationOutcomeConflictError(
                    "settlement timestamp is outside the evaluated maturity window"
                )
            rank_label = row.get("rank_label")
            if rank_label is not None:
                if not isinstance(rank_label, Mapping):
                    raise ObservationOutcomeConflictError("rank label must be an object")
                market = str(row.get("market") or "")
                expected_benchmark = ten_day_rank_model.REGISTERED_BENCHMARKS.get(market)
                expected_cost = ten_day_rank_model.TRANSACTION_COSTS.get(market)
                try:
                    stock_gross = float(rank_label.get("stock_gross_return"))
                    stock_net = float(rank_label.get("stock_net_return"))
                    benchmark_gross = float(rank_label.get("benchmark_gross_return"))
                    benchmark_net = float(rank_label.get("benchmark_net_return"))
                    net_excess = float(rank_label.get("net_excess_return"))
                    benchmark_entry = float(rank_label.get("benchmark_entry_price"))
                    benchmark_exit = float(rank_label.get("benchmark_exit_price"))
                except (TypeError, ValueError):
                    stock_gross = stock_net = benchmark_gross = benchmark_net = net_excess = math.nan
                    benchmark_entry = benchmark_exit = math.nan
                if (
                    rank_label.get("schema_version") != RANK_LABEL_SCHEMA_VERSION
                    or rank_label.get("market") != market
                    or rank_label.get("benchmark_code") != expected_benchmark
                    or rank_label.get("entry_date") != row.get("entry_trade_date")
                    or rank_label.get("exit_date") != row.get("forecast_end_trade_date")
                    or rank_label.get("transaction_cost_version") != RANK_COST_VERSION
                    or rank_label.get("corporate_action_adjusted") is not True
                    or rank_label.get("stock_transaction_cost") != expected_cost
                    or rank_label.get("benchmark_transaction_cost") != expected_cost
                    or rank_label.get("stock_entry_price") != row.get("entry_price")
                    or rank_label.get("stock_exit_price") != row.get("exit_price")
                    or not all(
                        math.isfinite(value)
                        for value in (stock_gross, stock_net, benchmark_gross, benchmark_net, net_excess)
                    )
                    or abs(stock_gross - float(row.get("gross_total_return"))) > 1e-12
                    or abs(stock_net - float(row.get("net_total_return"))) > 1e-12
                    or abs(stock_net - round(stock_gross - expected_cost, RETURN_DECIMALS)) > 1e-12
                    or benchmark_entry <= 0
                    or benchmark_exit <= 0
                    or abs(
                        benchmark_gross
                        - round(benchmark_exit / benchmark_entry - 1.0, RETURN_DECIMALS)
                    )
                    > 1e-12
                    or abs(benchmark_net - round(benchmark_gross - expected_cost, RETURN_DECIMALS)) > 1e-12
                    or abs(net_excess - round(stock_net - benchmark_net, RETURN_DECIMALS)) > 1e-12
                    or row.get("rank_label_sha256") != _digest(rank_label)
                ):
                    raise ObservationOutcomeConflictError("rank label identity or arithmetic is invalid")
        if row.get("outcome_sha256") != _row_digest(row):
            raise ObservationOutcomeConflictError(f"observation outcome digest mismatch: {observation_id}")
        status_counts[str(status)] += 1
    expected_counts = dict(sorted(status_counts.items()))
    if batch.get("status_counts") != expected_counts or batch.get("prediction_count") != len(rows):
        raise ObservationOutcomeConflictError("observation outcome summary is inconsistent")
    if status_counts and status_counts.get("SETTLED", 0) == len(rows):
        expected_status = "SETTLED"
    elif len(status_counts) == 1:
        expected_status = next(iter(status_counts))
    else:
        expected_status = "PARTIAL"
    if batch.get("status") != expected_status:
        raise ObservationOutcomeConflictError("observation outcome batch status is inconsistent")
    if batch.get("batch_sha256") != _batch_digest(batch):
        raise ObservationOutcomeConflictError("observation outcome batch digest mismatch")
    if cohort is not None:
        normalized = model_observation_ledger.validate_observation_cohort(cohort)
        if (
            cohort_id != normalized.get("cohort_id")
            or batch.get("canonical_revision_id") != normalized.get("canonical_revision_id")
            or batch.get("cohort_sha256") != normalized.get("cohort_sha256")
            or batch.get("canonical_source_snapshot")
            != normalized.get("canonical_source_snapshot")
            or batch.get("scheduled_slot") != normalized.get("scheduled_slot")
        ):
            raise ObservationOutcomeConflictError("observation outcome does not match its cohort")
        canonical = _canonical_revision(normalized)
        predictions = {row["observation_id"]: row for row in canonical["predictions"]}
        if set(predictions) != seen:
            raise ObservationOutcomeConflictError("observation outcome coverage does not match canonical predictions")
        for row in rows:
            prediction = predictions[row["observation_id"]]
            expected_base = _base_outcome(normalized, canonical, prediction)
            if any(row.get(key) != value for key, value in expected_base.items()):
                raise ObservationOutcomeConflictError("observation outcome frozen identity mismatch")
            if row.get("status") == "SETTLED":
                entry = _finite_positive(row.get("entry_price"))
                exit_ = _finite_positive(row.get("exit_price"))
                try:
                    gross = float(row.get("gross_total_return"))
                    net = float(row.get("net_total_return"))
                except (TypeError, ValueError):
                    gross = net = math.nan
                evidence = row.get("price_evidence")
                evidence_digest = (
                    _digest({key: value for key, value in evidence.items() if key != "evidence_sha256"})
                    if isinstance(evidence, Mapping)
                    else None
                )
                expected_evidence = _price_evidence(
                    prediction,
                    source=str(row.get("entry_source") or ""),
                    entry_price=entry or math.nan,
                    exit_price=exit_ or math.nan,
                )
                if (
                    entry is None
                    or exit_ is None
                    or not math.isfinite(gross)
                    or not math.isfinite(net)
                    or row.get("entry_at") != prediction.get("entry_session_open_at")
                    or row.get("exit_at") != prediction.get("forecast_end_session_close_at")
                    or not isinstance(row.get("entry_source"), str)
                    or not row.get("entry_source")
                    or not isinstance(row.get("exit_source"), str)
                    or not row.get("exit_source")
                    or row.get("entry_source") != row.get("exit_source")
                    or row.get("corporate_action_adjusted") is not True
                    or row.get("positive_label") != (net > 0)
                    or not isinstance(evidence, Mapping)
                    or evidence.get("evidence_sha256") != evidence_digest
                    or row.get("price_evidence_sha256") != evidence_digest
                    or dict(evidence) != expected_evidence
                    or abs(gross - round(exit_ / entry - 1.0, RETURN_DECIMALS)) > 1e-12
                    or abs(
                        net
                        - round(gross - float(prediction["transaction_cost"]), RETURN_DECIMALS)
                    )
                    > 1e-12
                ):
                    raise ObservationOutcomeConflictError(
                        "settled observation arithmetic or provenance is invalid"
                    )
    return batch


def _can_replace_pending_canonical(
    existing: Mapping[str, Any],
    cohort: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> bool:
    rows = existing.get("outcomes")
    if (
        existing.get("cohort_id") != cohort.get("cohort_id")
        or existing.get("scheduled_slot") != cohort.get("scheduled_slot")
        or existing.get("canonical_revision_id") == cohort.get("canonical_revision_id")
        or not isinstance(rows, list)
        or any(row.get("status") != "PENDING_MATURITY" for row in rows)
    ):
        return False
    revision_ids = {
        revision.get("revision_id")
        for revision in (cohort.get("revisions") or [])
        if isinstance(revision, Mapping)
    }
    if existing.get("canonical_revision_id") not in revision_ids:
        return False
    generated_at = _aware_moment(str(canonical.get("generated_at") or ""))
    entry_opens = [
        _aware_moment(str(prediction.get("entry_session_open_at") or ""))
        for prediction in (canonical.get("predictions") or [])
    ]
    return bool(entry_opens) and all(generated_at < entry_open for entry_open in entry_opens)


def settle_observation_cohort(
    cohort: Mapping[str, Any],
    as_of: dt.datetime | str,
    price_loader: PriceLoader,
    *,
    existing: Mapping[str, Any] | None = None,
    benchmark_price_loader: PriceLoader | None = None,
) -> dict[str, Any]:
    """Settle the canonical revision of one cohort, preserving settled rows."""

    normalized = model_observation_ledger.validate_observation_cohort(cohort)
    canonical = _canonical_revision(normalized)
    moment = _aware_moment(as_of)
    existing_batch = validate_outcome_batch(existing) if existing is not None else None
    if existing_batch is not None:
        existing_evaluated_at = _aware_moment(str(existing_batch.get("evaluated_at") or ""))
        if moment < existing_evaluated_at:
            raise ObservationOutcomeConflictError("observation settlement as_of moved backwards")
        try:
            existing_batch = validate_outcome_batch(existing_batch, cohort=normalized)
        except ObservationOutcomeConflictError:
            if not _can_replace_pending_canonical(existing_batch, normalized, canonical):
                raise
            existing_batch = None
    existing_rows = {
        row["observation_id"]: dict(row)
        for row in ((existing_batch or {}).get("outcomes") or [])
    }
    if existing_rows and all(row.get("status") == "SETTLED" for row in existing_rows.values()):
        return dict(existing_batch)

    settled_rows: list[dict[str, Any]] = []
    for prediction in canonical.get("predictions") or []:
        base = _base_outcome(normalized, canonical, prediction)
        previous = existing_rows.get(base["observation_id"])
        if previous is not None:
            if (
                previous.get("prediction_sha256") != base["prediction_sha256"]
                or previous.get("settlement_contract_sha256") != base["settlement_contract_sha256"]
            ):
                raise ObservationOutcomeConflictError(
                    f"observation outcome identity conflict: {base['observation_id']}"
                )
            if previous.get("status") == "SETTLED":
                settled_rows.append(previous)
                continue
        maturity = _aware_moment(str(prediction["forecast_end_session_close_at"]))
        if moment <= maturity:
            row = _pending_row(base, "PENDING_MATURITY", "FORECAST_WINDOW_OPEN")
        else:
            row = _settled_row(
                base,
                prediction,
                moment,
                price_loader,
                benchmark_price_loader,
            )
        settled_rows.append(row)

    settled_rows.sort(key=lambda row: str(row["observation_id"]))
    counts = Counter(str(row["status"]) for row in settled_rows)
    if counts and counts.get("SETTLED", 0) == len(settled_rows):
        status = "SETTLED"
    elif counts and len(counts) == 1:
        status = next(iter(counts))
    else:
        status = "PARTIAL"
    batch = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "track": TRACK,
        "cohort_id": normalized["cohort_id"],
        "cohort_sha256": normalized["cohort_sha256"],
        "canonical_revision_id": normalized["canonical_revision_id"],
        "canonical_source_snapshot": normalized["canonical_source_snapshot"],
        "scheduled_slot": normalized["scheduled_slot"],
        "evaluated_at": moment.isoformat(timespec="seconds"),
        "status": status,
        "prediction_count": len(settled_rows),
        "status_counts": dict(sorted(counts.items())),
        "outcomes": settled_rows,
        "included_in_shadow_research": False,
        "included_in_executable_performance": False,
        "authorizes_production": False,
    }
    batch["batch_sha256"] = _batch_digest(batch)
    validated = validate_outcome_batch(batch, cohort=normalized)
    if existing_batch is not None:
        state = {
            key: value
            for key, value in validated.items()
            if key not in {"evaluated_at", "batch_sha256"}
        }
        previous_state = {
            key: value
            for key, value in existing_batch.items()
            if key not in {"evaluated_at", "batch_sha256"}
        }
        if state == previous_state:
            return dict(existing_batch)
    return validated


def write_outcome_batch(directory: pathlib.Path, batch: Mapping[str, Any]) -> pathlib.Path:
    validated = validate_outcome_batch(batch)
    root = pathlib.Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{validated['cohort_id']}.json"
    rendered = json.dumps(
        validated,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    if target.is_file():
        current = json.loads(target.read_text(encoding="utf-8"))
        validate_outcome_batch(current)
        if current == validated:
            return target
        current_rows = {row["observation_id"]: row for row in current["outcomes"]}
        incoming_rows = {row["observation_id"]: row for row in validated["outcomes"]}
        for observation_id, row in current_rows.items():
            if row.get("status") == "SETTLED" and incoming_rows.get(observation_id) != row:
                raise ObservationOutcomeConflictError(
                    f"refusing to rewrite settled observation: {observation_id}"
                )
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=root,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(rendered)
        temporary = pathlib.Path(handle.name)
    temporary.replace(target)
    return target


def load_outcome_batches(
    directory: pathlib.Path = DEFAULT_OUTCOME_DIRECTORY,
) -> dict[str, dict[str, Any]]:
    root = pathlib.Path(directory)
    if not root.is_dir():
        return {}
    batches: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        if VALID_COHORT_ID.fullmatch(path.stem) is None:
            raise ObservationOutcomeConflictError(f"unsafe observation outcome filename: {path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ObservationOutcomeConflictError(f"unreadable observation outcome: {path.name}") from exc
        validated = validate_outcome_batch(payload)
        if validated.get("cohort_id") != path.stem:
            raise ObservationOutcomeConflictError(f"observation outcome filename mismatch: {path.name}")
        batches[path.stem] = validated
    return batches


__all__ = [
    "BATCH_SCHEMA_VERSION",
    "DEFAULT_OUTCOME_DIRECTORY",
    "OUTCOME_SCHEMA_VERSION",
    "RANK_COST_VERSION",
    "RANK_LABEL_SCHEMA_VERSION",
    "ObservationOutcomeConflictError",
    "ObservationOutcomeContractError",
    "TRACK",
    "load_outcome_batches",
    "settle_observation_cohort",
    "validate_outcome_batch",
    "write_outcome_batch",
]

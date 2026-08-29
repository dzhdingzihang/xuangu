"""Immutable outcomes for every published production-rule qualification.

This is a diagnostic rule track, not a calibrated probability track.  A
snapshot freezes every qualified row (including the primary flag), then the
ledger settles next-session open to tenth-session close using adjusted prices
and the registered investable benchmark for the same market window.
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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import market_calendar
import ten_day_rank_model


TRACK = "RULE_QUALIFICATION"
PREDICTION_SCHEMA_VERSION = "rule-prediction-v1"
OUTCOME_SCHEMA_VERSION = "rule-outcome-v1"
BATCH_SCHEMA_VERSION = "rule-outcome-batch-v1"
COST_VERSION = "market-round-trip-cost-v1"
BENCHMARK_COST_VERSION = COST_VERSION
TRANSACTION_COSTS = dict(ten_day_rank_model.TRANSACTION_COSTS)
REGISTERED_BENCHMARKS = dict(ten_day_rank_model.REGISTERED_BENCHMARKS)
CURRENCIES = {"a_share": "CNY", "hk": "HKD", "us": "USD"}
VALID_MARKETS = tuple(REGISTERED_BENCHMARKS)
VALID_TRACKS = {"event_catalyst", "quality_technical"}
VALID_STATUSES = {"PENDING_MATURITY", "PENDING_DATA", "SETTLED"}
PENDING_DATA_REASONS = {
    "ADJUSTED_PRICE_EVIDENCE_MISSING",
    "COMPLETE_ADJUSTED_WINDOW_MISSING",
}
VALID_QUALIFICATION_ID = re.compile(r"^qual_[a-f0-9]{24}$")
VALID_PREDICTION_ID = re.compile(r"^rulepred_[a-f0-9]{24}$")
VALID_SAFE_SNAPSHOT = re.compile(r"^[A-Za-z0-9_.-]+\.json$")
PRICE_DECIMALS = 8
RETURN_DECIMALS = 8
DEFAULT_OUTCOME_DIRECTORY = (
    pathlib.Path(__file__).resolve().parent / "data" / "outcomes" / "rule-settlements"
)
SETTLEMENT_FIELDS = (
    "status",
    "entry_open",
    "exit_close",
    "gross_total_return",
    "transaction_cost",
    "net_total_return",
    "benchmark_net_return",
    "net_excess_return",
    "maximum_adverse_excursion",
    "settled_at",
    "price_source",
    "outcome_sha256",
)


class RuleOutcomeContractError(ValueError):
    """A snapshot or price payload cannot form the rule-outcome contract."""


class RuleOutcomeConflictError(RuntimeError):
    """An immutable rule prediction or settled outcome was changed."""


PriceLoader = Callable[[str, str], tuple[list[dict[str, Any]], str, bool]]


@dataclass(frozen=True)
class RulePrediction:
    qualification_id: str
    snapshot_key: str
    market: str
    code: str
    signal_date: str
    entry_trade_date: str
    forecast_end_trade_date: str
    entry_price: float
    qualification_track: str
    qualification_score: float
    is_primary: bool
    rule_model_id: str


def _digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def prediction_id(row: Mapping[str, Any]) -> str:
    """Return the deterministic identity described by the public contract."""

    canonical = json.dumps(
        dict(row),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return "rulepred_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def prediction_sha256(row: Mapping[str, Any]) -> str:
    return _digest(
        {key: value for key, value in row.items() if key not in {"prediction_sha256"}}
    )


def outcome_sha256(row: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in row.items() if key != "outcome_sha256"})


def batch_sha256(batch: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in batch.items() if key != "batch_sha256"})


def _aware(value: dt.datetime | str, field: str = "timestamp") -> dt.datetime:
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        try:
            parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise RuleOutcomeContractError(f"{field} must be timezone-aware") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuleOutcomeContractError(f"{field} must be timezone-aware")
    return parsed


def _iso_date(value: Any, field: str) -> str:
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise RuleOutcomeContractError(f"{field} must be an ISO date") from exc


def _finite(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise RuleOutcomeContractError(f"{field} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuleOutcomeContractError(f"{field} must be finite") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise RuleOutcomeContractError(f"{field} must be finite")
    return number


def _snapshot_key(snapshot: Mapping[str, Any], explicit: str | None) -> str:
    value = explicit or snapshot.get("snapshot_key")
    if not isinstance(value, str) or VALID_SAFE_SNAPSHOT.fullmatch(value) is None:
        raise RuleOutcomeContractError("snapshot_key must be a safe immutable JSON filename")
    if pathlib.PurePosixPath(value).name != value or value == "latest.json":
        raise RuleOutcomeContractError("snapshot_key must name an immutable snapshot")
    return value


def _prediction_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        -float(row.get("qualification_score") or 0.0),
        str(row.get("market") or ""),
        str(row.get("code") or ""),
        str(row.get("qualification_id") or ""),
    )


def _prediction_identity_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"prediction_id", "prediction_sha256"}
    }


def validate_prediction_sequence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise RuleOutcomeContractError("rule predictions must be a list")
    normalized = [dict(row) for row in rows]
    if normalized != sorted(normalized, key=_prediction_sort_key):
        raise RuleOutcomeConflictError("rule prediction order changed")
    seen: set[str] = set()
    for row in normalized:
        identifier = str(row.get("prediction_id") or "")
        if identifier in seen or VALID_PREDICTION_ID.fullmatch(identifier) is None:
            raise RuleOutcomeConflictError("rule prediction identity is invalid or duplicated")
        seen.add(identifier)
        payload = _prediction_identity_payload(row)
        if identifier != prediction_id(payload) or row.get("prediction_sha256") != prediction_sha256(row):
            raise RuleOutcomeConflictError("rule prediction digest is invalid")
        if row.get("schema_version") != PREDICTION_SCHEMA_VERSION or row.get("track") != TRACK:
            raise RuleOutcomeConflictError("rule prediction track is invalid")
        if row.get("market") not in VALID_MARKETS:
            raise RuleOutcomeContractError("rule prediction market is invalid")
        if row.get("qualification_track") not in VALID_TRACKS:
            raise RuleOutcomeContractError("rule qualification track is invalid")
        if not isinstance(row.get("is_primary"), bool):
            raise RuleOutcomeContractError("rule primary flag must be boolean")
        _finite(row.get("entry_price"), "entry_price", positive=True)
        score = _finite(row.get("qualification_score"), "qualification_score")
        if not 0 <= score <= 100:
            raise RuleOutcomeContractError("qualification_score must be between zero and 100")
    if sum(bool(row.get("is_primary")) for row in normalized) > 1:
        raise RuleOutcomeConflictError("rule prediction sequence has multiple primary rows")
    return normalized


def build_rule_predictions(
    snapshot: Mapping[str, Any],
    source_snapshot: str | None = None,
) -> list[dict[str, Any]]:
    """Freeze the complete, ordered list of qualified production-rule rows."""

    if not isinstance(snapshot, Mapping):
        raise RuleOutcomeContractError("snapshot must be an object")
    key = _snapshot_key(snapshot, source_snapshot)
    generated = _aware(str(snapshot.get("generated_at") or ""), "generated_at")
    signal_date = _iso_date(snapshot.get("signal_date"), "signal_date")
    decision = snapshot.get("production_decision")
    if not isinstance(decision, Mapping):
        raise RuleOutcomeContractError("production_decision is missing")
    if (
        decision.get("contract_version") != "production-rule-10d-v1"
        or decision.get("horizon_trade_days") != 10
        or decision.get("score_kind") != "RULE_QUALIFICATION_SCORE"
    ):
        raise RuleOutcomeContractError("production rule identity is invalid")
    candidates = decision.get("qualified_candidates")
    if not isinstance(candidates, list):
        raise RuleOutcomeContractError("qualified_candidates must be a list")
    if decision.get("qualified_candidate_count") != len(candidates):
        raise RuleOutcomeConflictError("qualified candidate count is inconsistent")
    if bool(candidates) != (decision.get("action") == "QUALIFIED_PICK"):
        raise RuleOutcomeConflictError("production action and qualified candidates disagree")
    primary = decision.get("primary")
    primary_id = primary.get("qualification_id") if isinstance(primary, Mapping) else None
    if candidates and not primary_id:
        raise RuleOutcomeContractError("qualified candidates require a primary identity")
    rule_model_id = str(decision.get("rule_model_id") or "")
    if not rule_model_id:
        raise RuleOutcomeContractError("rule_model_id is required")

    predictions: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping) or candidate.get("status") != "QUALIFIED":
            raise RuleOutcomeContractError("every frozen rule candidate must be QUALIFIED")
        qualification_id = str(candidate.get("qualification_id") or "")
        if VALID_QUALIFICATION_ID.fullmatch(qualification_id) is None:
            raise RuleOutcomeContractError("qualification_id is invalid")
        market = str(candidate.get("market") or "")
        code = str(candidate.get("code") or "")
        if market not in VALID_MARKETS or not code:
            raise RuleOutcomeContractError("qualified market/code is invalid")
        window = market_calendar.market_trade_window(market, generated, horizon_sessions=10)
        for field in ("calendar_id", "calendar_version", "entry_trade_date", "forecast_end_trade_date"):
            if candidate.get(field) != window.get(field):
                raise RuleOutcomeContractError(f"qualified candidate {field} is inconsistent")
        core = RulePrediction(
            qualification_id=qualification_id,
            snapshot_key=key,
            market=market,
            code=code,
            signal_date=signal_date,
            entry_trade_date=window["entry_trade_date"],
            forecast_end_trade_date=window["forecast_end_trade_date"],
            entry_price=_finite(candidate.get("entry_price"), "entry_price", positive=True),
            qualification_track=str(candidate.get("qualification_track") or ""),
            qualification_score=_finite(candidate.get("qualification_score"), "qualification_score"),
            is_primary=qualification_id == primary_id,
            rule_model_id=rule_model_id,
        )
        if candidate.get("rule_model_id") != rule_model_id:
            raise RuleOutcomeContractError("candidate rule_model_id is inconsistent")
        payload = {
            "schema_version": PREDICTION_SCHEMA_VERSION,
            "track": TRACK,
            **asdict(core),
            "generated_at": generated.isoformat(timespec="seconds"),
            "entry_session_open_at": window["entry_session_open_at"],
            "forecast_end_session_close_at": window["forecast_end_session_close_at"],
            "horizon_trade_sessions": 10,
            "entry_policy": "next_session_open_v1",
            "exit_policy": "tenth_session_close_v1",
            "calendar_id": window["calendar_id"],
            "calendar_version": window["calendar_version"],
            "currency": CURRENCIES[market],
            "transaction_cost": TRANSACTION_COSTS[market],
            "transaction_cost_version": COST_VERSION,
            "benchmark_code": REGISTERED_BENCHMARKS[market],
            "benchmark_transaction_cost": TRANSACTION_COSTS[market],
            "benchmark_transaction_cost_version": BENCHMARK_COST_VERSION,
            "authorizes_production": False,
        }
        payload["prediction_id"] = prediction_id(payload)
        payload["prediction_sha256"] = prediction_sha256(payload)
        predictions.append(payload)
    return validate_prediction_sequence(predictions)


def _price_rows(
    loaded: Any,
    *,
    market: str,
    as_of: dt.datetime,
) -> tuple[dict[str, Mapping[str, Any]], str] | None:
    if not isinstance(loaded, tuple) or len(loaded) != 3:
        return None
    rows, source, adjusted = loaded
    if not isinstance(rows, list) or not isinstance(source, str) or not source or adjusted is not True:
        return None
    by_date: dict[str, Mapping[str, Any]] = {}
    previous: str | None = None
    latest_legal = market_calendar.market_local_date(market, as_of).isoformat()
    for raw in rows:
        if not isinstance(raw, Mapping):
            return None
        date_text = _iso_date(raw.get("date"), "price.date")
        if date_text > latest_legal or date_text in by_date or (previous is not None and date_text <= previous):
            return None
        by_date[date_text] = raw
        previous = date_text
    return by_date, source


def _positive_price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _pending(prediction: Mapping[str, Any], status: str, reason: str) -> dict[str, Any]:
    row = {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "track": TRACK,
        **{key: prediction[key] for key in (
            "prediction_id", "prediction_sha256", "qualification_id", "snapshot_key",
            "market", "code", "signal_date", "qualification_track", "qualification_score",
            "is_primary", "rule_model_id", "entry_trade_date", "entry_session_open_at",
            "forecast_end_trade_date", "forecast_end_session_close_at", "calendar_id",
            "calendar_version", "currency", "transaction_cost", "transaction_cost_version",
            "benchmark_code", "benchmark_transaction_cost",
            "benchmark_transaction_cost_version",
        )},
        "status": status,
        "reason_code": reason,
        "authorizes_production": False,
    }
    row["outcome_sha256"] = outcome_sha256(row)
    return row


def _settled(
    prediction: Mapping[str, Any],
    moment: dt.datetime,
    price_loader: PriceLoader,
    benchmark_price_loader: PriceLoader,
) -> dict[str, Any]:
    try:
        stock_payload = _price_rows(
            price_loader(str(prediction["market"]), str(prediction["code"])),
            market=str(prediction["market"]),
            as_of=moment,
        )
        benchmark_payload = _price_rows(
            benchmark_price_loader(
                str(prediction["market"]), str(prediction["benchmark_code"])
            ),
            market=str(prediction["market"]),
            as_of=moment,
        )
    except Exception:
        stock_payload = benchmark_payload = None
    if stock_payload is None or benchmark_payload is None:
        return _pending(prediction, "PENDING_DATA", "ADJUSTED_PRICE_EVIDENCE_MISSING")
    stock_by_date, stock_source = stock_payload
    benchmark_by_date, benchmark_source = benchmark_payload
    sessions = [
        day.isoformat()
        for day in market_calendar.session_dates(
            str(prediction["market"]),
            str(prediction["entry_trade_date"]),
            str(prediction["forecast_end_trade_date"]),
        )
    ]
    if len(sessions) != 10 or any(day not in stock_by_date for day in sessions):
        return _pending(prediction, "PENDING_DATA", "COMPLETE_ADJUSTED_WINDOW_MISSING")
    entry_day, exit_day = sessions[0], sessions[-1]
    entry = _positive_price(stock_by_date[entry_day].get("open"))
    exit_ = _positive_price(stock_by_date[exit_day].get("close"))
    lows = [_positive_price(stock_by_date[day].get("low")) for day in sessions]
    benchmark_entry = _positive_price((benchmark_by_date.get(entry_day) or {}).get("open"))
    benchmark_exit = _positive_price((benchmark_by_date.get(exit_day) or {}).get("close"))
    if None in (entry, exit_, benchmark_entry, benchmark_exit) or any(value is None for value in lows):
        return _pending(prediction, "PENDING_DATA", "COMPLETE_ADJUSTED_WINDOW_MISSING")
    entry = round(float(entry), PRICE_DECIMALS)
    exit_ = round(float(exit_), PRICE_DECIMALS)
    benchmark_entry = round(float(benchmark_entry), PRICE_DECIMALS)
    benchmark_exit = round(float(benchmark_exit), PRICE_DECIMALS)
    gross = round(exit_ / entry - 1.0, RETURN_DECIMALS)
    net = round(gross - float(prediction["transaction_cost"]), RETURN_DECIMALS)
    benchmark_gross = round(benchmark_exit / benchmark_entry - 1.0, RETURN_DECIMALS)
    benchmark_net = round(
        benchmark_gross - float(prediction["benchmark_transaction_cost"]),
        RETURN_DECIMALS,
    )
    excess = round(net - benchmark_net, RETURN_DECIMALS)
    mae = round(min(float(value) for value in lows if value is not None) / entry - 1.0, RETURN_DECIMALS)
    row = _pending(prediction, "SETTLED", "")
    row.update(
        {
            "reason_code": None,
            "entry_open": entry,
            "exit_close": exit_,
            "gross_total_return": gross,
            "net_total_return": net,
            "benchmark_entry_open": benchmark_entry,
            "benchmark_exit_close": benchmark_exit,
            "benchmark_gross_return": benchmark_gross,
            "benchmark_net_return": benchmark_net,
            "net_excess_return": excess,
            "maximum_adverse_excursion": mae,
            "settled_at": moment.isoformat(timespec="seconds"),
            "price_source": stock_source,
            "benchmark_price_source": benchmark_source,
            "corporate_action_adjusted": True,
        }
    )
    evidence = {
        "schema_version": "rule-price-evidence-v1",
        "corporate_action_adjusted": True,
        "stock_source": stock_source,
        "benchmark_source": benchmark_source,
        "entry_date": entry_day,
        "exit_date": exit_day,
        "entry_open": entry,
        "exit_close": exit_,
        "benchmark_entry_open": benchmark_entry,
        "benchmark_exit_close": benchmark_exit,
        "session_lows": [
            {"date": day, "low": round(float(stock_by_date[day]["low"]), PRICE_DECIMALS)}
            for day in sessions
        ],
    }
    evidence["evidence_sha256"] = _digest(evidence)
    row["price_evidence"] = evidence
    row["price_evidence_sha256"] = evidence["evidence_sha256"]
    row["outcome_sha256"] = outcome_sha256(row)
    return row


def validate_rule_outcome_batch(
    payload: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RuleOutcomeContractError("rule outcome batch must be an object")
    batch = dict(payload)
    if (
        batch.get("schema_version") != BATCH_SCHEMA_VERSION
        or batch.get("track") != TRACK
        or batch.get("authorizes_production") is not False
    ):
        raise RuleOutcomeConflictError("rule outcome isolation contract is invalid")
    key = str(batch.get("snapshot_key") or "")
    if VALID_SAFE_SNAPSHOT.fullmatch(key) is None or key == "latest.json":
        raise RuleOutcomeContractError("rule outcome snapshot_key is invalid")
    evaluated = _aware(str(batch.get("evaluated_at") or ""), "evaluated_at")
    predictions = validate_prediction_sequence(batch.get("predictions") or [])
    outcomes = batch.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != len(predictions):
        raise RuleOutcomeConflictError("rule outcome coverage is inconsistent")
    expected_ids = [row["prediction_id"] for row in predictions]
    if batch.get("prediction_ids") != expected_ids or batch.get("prediction_count") != len(predictions):
        raise RuleOutcomeConflictError("rule prediction summary is inconsistent")
    counts: Counter[str] = Counter()
    for prediction, raw in zip(predictions, outcomes):
        if not isinstance(raw, Mapping):
            raise RuleOutcomeContractError("rule outcome row must be an object")
        row = dict(raw)
        if row.get("prediction_id") != prediction["prediction_id"]:
            raise RuleOutcomeConflictError("rule outcome order or identity changed")
        for field in (
            "prediction_id", "prediction_sha256", "qualification_id", "snapshot_key", "market",
            "code", "signal_date", "qualification_track", "qualification_score", "is_primary",
            "rule_model_id", "entry_trade_date", "entry_session_open_at",
            "forecast_end_trade_date", "forecast_end_session_close_at", "calendar_id",
            "calendar_version", "currency", "transaction_cost", "transaction_cost_version",
            "benchmark_code", "benchmark_transaction_cost", "benchmark_transaction_cost_version",
        ):
            if row.get(field) != prediction.get(field):
                raise RuleOutcomeConflictError(f"rule outcome frozen identity changed: {field}")
        if row.get("schema_version") != OUTCOME_SCHEMA_VERSION or row.get("track") != TRACK:
            raise RuleOutcomeConflictError("rule outcome track is invalid")
        if row.get("authorizes_production") is not False:
            raise RuleOutcomeConflictError("rule outcome cannot authorize production")
        status = str(row.get("status") or "")
        if status not in VALID_STATUSES:
            raise RuleOutcomeContractError("rule outcome status is invalid")
        maturity = _aware(str(row.get("forecast_end_session_close_at") or ""), "maturity")
        if status == "PENDING_MATURITY":
            if evaluated > maturity or row.get("reason_code") != "FORECAST_WINDOW_OPEN":
                raise RuleOutcomeConflictError("pending maturity state is invalid")
        elif status == "PENDING_DATA" and row.get("reason_code") not in PENDING_DATA_REASONS:
            raise RuleOutcomeContractError("pending data reason is invalid")
        elif evaluated <= maturity:
            raise RuleOutcomeConflictError("mature rule state precedes forecast close")
        if status != "SETTLED":
            prohibited = (
                set(SETTLEMENT_FIELDS)
                | {
                    "benchmark_entry_open", "benchmark_exit_close", "benchmark_gross_return",
                    "benchmark_price_source", "corporate_action_adjusted", "price_evidence",
                    "price_evidence_sha256",
                }
            ) - {"status", "transaction_cost", "outcome_sha256"}
            if any(field in row for field in prohibited):
                raise RuleOutcomeConflictError("pending rule outcome contains settlement fields")
        else:
            if row.get("reason_code") is not None or any(field not in row for field in SETTLEMENT_FIELDS):
                raise RuleOutcomeConflictError("settled rule outcome is partial")
            values = [
                row.get(field)
                for field in (
                    "entry_open", "exit_close", "gross_total_return", "transaction_cost",
                    "net_total_return", "benchmark_net_return", "net_excess_return",
                    "maximum_adverse_excursion",
                )
            ]
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in values):
                raise RuleOutcomeConflictError("settled rule outcome contains non-finite values")
            if row.get("corporate_action_adjusted") is not True:
                raise RuleOutcomeConflictError("settled rule outcome must use adjusted prices")
            if abs(float(row["gross_total_return"]) - round(float(row["exit_close"]) / float(row["entry_open"]) - 1.0, RETURN_DECIMALS)) > 1e-12:
                raise RuleOutcomeConflictError("settled rule gross return is inconsistent")
            if abs(float(row["net_total_return"]) - round(float(row["gross_total_return"]) - float(row["transaction_cost"]), RETURN_DECIMALS)) > 1e-12:
                raise RuleOutcomeConflictError("settled rule net return is inconsistent")
            if abs(float(row["net_excess_return"]) - round(float(row["net_total_return"]) - float(row["benchmark_net_return"]), RETURN_DECIMALS)) > 1e-12:
                raise RuleOutcomeConflictError("settled rule excess return is inconsistent")
            benchmark_entry = _finite(row.get("benchmark_entry_open"), "benchmark_entry_open", positive=True)
            benchmark_exit = _finite(row.get("benchmark_exit_close"), "benchmark_exit_close", positive=True)
            benchmark_gross = round(benchmark_exit / benchmark_entry - 1.0, RETURN_DECIMALS)
            if (
                abs(float(row.get("benchmark_gross_return")) - benchmark_gross) > 1e-12
                or abs(
                    float(row["benchmark_net_return"])
                    - round(benchmark_gross - float(row["benchmark_transaction_cost"]), RETURN_DECIMALS)
                )
                > 1e-12
            ):
                raise RuleOutcomeConflictError("settled benchmark return is inconsistent")
            evidence = row.get("price_evidence")
            if not isinstance(evidence, Mapping):
                raise RuleOutcomeConflictError("settled rule price evidence is missing")
            evidence_without_hash = {
                key: value for key, value in evidence.items() if key != "evidence_sha256"
            }
            lows = evidence.get("session_lows")
            expected_sessions = [
                day.isoformat()
                for day in market_calendar.session_dates(
                    str(row["market"]),
                    str(row["entry_trade_date"]),
                    str(row["forecast_end_trade_date"]),
                )
            ]
            if (
                evidence.get("evidence_sha256") != _digest(evidence_without_hash)
                or row.get("price_evidence_sha256") != evidence.get("evidence_sha256")
                or evidence.get("corporate_action_adjusted") is not True
                or evidence.get("entry_open") != row.get("entry_open")
                or evidence.get("exit_close") != row.get("exit_close")
                or evidence.get("benchmark_entry_open") != row.get("benchmark_entry_open")
                or evidence.get("benchmark_exit_close") != row.get("benchmark_exit_close")
                or not isinstance(lows, list)
                or [item.get("date") for item in lows if isinstance(item, Mapping)] != expected_sessions
                or len(lows) != len(expected_sessions)
            ):
                raise RuleOutcomeConflictError("settled rule price evidence is inconsistent")
            low_values = [
                _finite(item.get("low"), "price_evidence.low", positive=True)
                for item in lows
                if isinstance(item, Mapping)
            ]
            if len(low_values) != len(expected_sessions) or abs(
                float(row["maximum_adverse_excursion"])
                - round(min(low_values) / float(row["entry_open"]) - 1.0, RETURN_DECIMALS)
            ) > 1e-12:
                raise RuleOutcomeConflictError("settled rule adverse excursion is inconsistent")
            settled_at = _aware(str(row.get("settled_at") or ""), "settled_at")
            if not maturity < settled_at <= evaluated:
                raise RuleOutcomeConflictError("rule settled_at is outside the legal window")
        if row.get("outcome_sha256") != outcome_sha256(row):
            raise RuleOutcomeConflictError("rule outcome digest is invalid")
        counts[status] += 1
    if batch.get("status_counts") != dict(sorted(counts.items())):
        raise RuleOutcomeConflictError("rule outcome status summary is inconsistent")
    expected_status = "EMPTY" if not outcomes else (next(iter(counts)) if len(counts) == 1 else "PARTIAL")
    if batch.get("status") != expected_status:
        raise RuleOutcomeConflictError("rule outcome batch status is inconsistent")
    if batch.get("batch_sha256") != batch_sha256(batch):
        raise RuleOutcomeConflictError("rule outcome batch digest is invalid")
    if snapshot is not None and predictions != build_rule_predictions(snapshot, key):
        raise RuleOutcomeConflictError("rule outcome batch no longer matches its source snapshot")
    return batch


def settle_rule_snapshot(
    snapshot: Mapping[str, Any],
    as_of: dt.datetime | str,
    price_loader: PriceLoader,
    *,
    benchmark_price_loader: PriceLoader | None = None,
    existing: Mapping[str, Any] | None = None,
    source_snapshot: str | None = None,
) -> dict[str, Any]:
    predictions = build_rule_predictions(snapshot, source_snapshot)
    moment = _aware(as_of, "as_of")
    previous = validate_rule_outcome_batch(existing, snapshot=snapshot) if existing is not None else None
    if previous is not None:
        if moment < _aware(str(previous["evaluated_at"]), "evaluated_at"):
            raise RuleOutcomeConflictError("rule settlement as_of moved backwards")
        if previous["predictions"] != predictions:
            raise RuleOutcomeConflictError("rule predictions changed after publication")
        if previous["outcomes"] and all(row.get("status") == "SETTLED" for row in previous["outcomes"]):
            return dict(previous)
    existing_rows = {
        row["prediction_id"]: row for row in ((previous or {}).get("outcomes") or [])
    }
    benchmark_loader = benchmark_price_loader or price_loader
    rows: list[dict[str, Any]] = []
    for prediction in predictions:
        old = existing_rows.get(prediction["prediction_id"])
        if old is not None and old.get("status") == "SETTLED":
            rows.append(dict(old))
            continue
        maturity = _aware(str(prediction["forecast_end_session_close_at"]), "maturity")
        if moment <= maturity:
            rows.append(_pending(prediction, "PENDING_MATURITY", "FORECAST_WINDOW_OPEN"))
        else:
            rows.append(_settled(prediction, moment, price_loader, benchmark_loader))
    counts = Counter(str(row["status"]) for row in rows)
    status = "EMPTY" if not rows else (next(iter(counts)) if len(counts) == 1 else "PARTIAL")
    batch = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "track": TRACK,
        "snapshot_key": predictions[0]["snapshot_key"] if predictions else _snapshot_key(snapshot, source_snapshot),
        "generated_at": _aware(str(snapshot.get("generated_at") or ""), "generated_at").isoformat(timespec="seconds"),
        "signal_date": _iso_date(snapshot.get("signal_date"), "signal_date"),
        "evaluated_at": moment.isoformat(timespec="seconds"),
        "status": status,
        "prediction_count": len(predictions),
        "prediction_ids": [row["prediction_id"] for row in predictions],
        "predictions": predictions,
        "status_counts": dict(sorted(counts.items())),
        "outcomes": rows,
        "authorizes_production": False,
    }
    batch["batch_sha256"] = batch_sha256(batch)
    validated = validate_rule_outcome_batch(batch, snapshot=snapshot)
    if previous is not None:
        comparable = {key: value for key, value in validated.items() if key not in {"evaluated_at", "batch_sha256"}}
        old_comparable = {key: value for key, value in previous.items() if key not in {"evaluated_at", "batch_sha256"}}
        if comparable == old_comparable:
            return dict(previous)
    return validated


def write_rule_outcome_batch(directory: pathlib.Path, batch: Mapping[str, Any]) -> pathlib.Path:
    validated = validate_rule_outcome_batch(batch)
    root = pathlib.Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    target = root / validated["snapshot_key"]
    if target.is_file():
        current = validate_rule_outcome_batch(json.loads(target.read_text(encoding="utf-8")))
        if current == validated:
            return target
        if current["predictions"] != validated["predictions"]:
            raise RuleOutcomeConflictError("refusing to rewrite frozen rule predictions")
        settled = {row["prediction_id"]: row for row in current["outcomes"] if row.get("status") == "SETTLED"}
        incoming = {row["prediction_id"]: row for row in validated["outcomes"]}
        if any(incoming.get(identifier) != row for identifier, row in settled.items()):
            raise RuleOutcomeConflictError("refusing to rewrite a settled rule outcome")
    rendered = json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=root, prefix=f".{target.name}.", suffix=".tmp", delete=False
    ) as handle:
        handle.write(rendered)
        temporary = pathlib.Path(handle.name)
    temporary.replace(target)
    return target


def load_rule_outcome_batches(
    directory: pathlib.Path = DEFAULT_OUTCOME_DIRECTORY,
) -> dict[str, dict[str, Any]]:
    root = pathlib.Path(directory)
    if not root.is_dir():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        if VALID_SAFE_SNAPSHOT.fullmatch(path.name) is None or path.name == "latest.json":
            raise RuleOutcomeConflictError(f"unsafe rule outcome filename: {path.name}")
        try:
            batch = validate_rule_outcome_batch(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise RuleOutcomeConflictError(f"unreadable rule outcome: {path.name}") from exc
        if batch["snapshot_key"] != path.name or path.name in result:
            raise RuleOutcomeConflictError("rule outcome filename identity mismatch")
        result[path.name] = batch
    return result


__all__ = [
    "BATCH_SCHEMA_VERSION", "BENCHMARK_COST_VERSION", "COST_VERSION",
    "DEFAULT_OUTCOME_DIRECTORY", "OUTCOME_SCHEMA_VERSION", "PREDICTION_SCHEMA_VERSION",
    "REGISTERED_BENCHMARKS", "RuleOutcomeConflictError", "RuleOutcomeContractError",
    "RulePrediction", "SETTLEMENT_FIELDS", "TRACK", "batch_sha256",
    "build_rule_predictions", "load_rule_outcome_batches", "outcome_sha256",
    "prediction_id", "prediction_sha256", "settle_rule_snapshot",
    "validate_prediction_sequence", "validate_rule_outcome_batch", "write_rule_outcome_batch",
]

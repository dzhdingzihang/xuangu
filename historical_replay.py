"""Research-only replay of shortlists that were actually archived in the repo.

This module deliberately does *not* reconstruct a historical market universe.
It only freezes ``decision.primary`` and ``decision.watchlist`` rows found in
immutable snapshot files, then settles those rows against adjusted prices from
the first exchange open after publication to the tenth session close.

The resulting evidence is retrospective, isolated from every live/prospective
model ledger, and can never authorize, promote, or participate in production.
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
from typing import Any

import market_calendar
import ten_day_rank_model


TRACK = "ARCHIVED_SHORTLIST_REPLAY"
EVIDENCE_CLASS = "RETROSPECTIVE"
UNIVERSE_SCOPE = "ARCHIVED_SHORTLIST_ONLY"
COHORT_SCHEMA_VERSION = "archived-shortlist-replay-cohort-v1"
CANDIDATE_SCHEMA_VERSION = "archived-shortlist-replay-candidate-v1"
OUTCOME_SCHEMA_VERSION = "archived-shortlist-replay-outcome-v1"
PRICE_EVIDENCE_SCHEMA_VERSION = "archived-shortlist-price-evidence-v1"
ARTIFACT_SCHEMA_VERSION = "archived-shortlist-replay-artifact-v1"
SUMMARY_SCHEMA_VERSION = "archived-shortlist-replay-summary-v1"
COST_VERSION = "market-round-trip-cost-v1"
BENCHMARK_COST_VERSION = COST_VERSION
TRANSACTION_COSTS = dict(ten_day_rank_model.TRANSACTION_COSTS)
REGISTERED_BENCHMARKS = dict(ten_day_rank_model.REGISTERED_BENCHMARKS)
CURRENCIES = {"a_share": "CNY", "hk": "HKD", "us": "USD"}
VALID_MARKETS = tuple(REGISTERED_BENCHMARKS)
VALID_STATUSES = {"PENDING_MATURITY", "PENDING_DATA", "SETTLED"}
PENDING_DATA_REASONS = {
    "ADJUSTED_PRICE_EVIDENCE_MISSING",
    "COMPLETE_ADJUSTED_WINDOW_MISSING",
}
AUTHORITY_FIELDS = (
    "full_point_in_time_universe",
    "included_in_live_observation_performance",
    "included_in_shadow_research",
    "included_in_executable_performance",
    "participates_in_decision",
    "promotion_eligible",
    "production_eligible",
    "authorizes_production",
)
LIMITATIONS = (
    "ARCHIVED_SHORTLIST_ONLY",
    "NOT_FULL_POINT_IN_TIME_UNIVERSE",
    "SURVIVORSHIP_AND_SELECTION_BIAS_POSSIBLE",
)
VALID_SAFE_SNAPSHOT = re.compile(r"^[A-Za-z0-9_.-]+\.json$")
VALID_SHA256 = re.compile(r"^[a-f0-9]{64}$")
VALID_COHORT_ID = re.compile(r"^replaycohort_[a-f0-9]{24}$")
VALID_CANDIDATE_ID = re.compile(r"^archivepick_[a-f0-9]{24}$")
VALID_OUTCOME_ID = re.compile(r"^archiveout_[a-f0-9]{24}$")
PRICE_DECIMALS = 8
RETURN_DECIMALS = 8


class HistoricalReplayContractError(ValueError):
    """An input cannot form the archived-shortlist replay contract."""


class HistoricalReplayConflictError(RuntimeError):
    """Persisted replay identity, evidence, or isolation fields conflict."""


PriceLoader = Callable[[str, str], tuple[list[dict[str, Any]], str, bool]]


def _isolation_contract() -> dict[str, bool | str]:
    return {
        "evidence_class": EVIDENCE_CLASS,
        "universe_scope": UNIVERSE_SCOPE,
        **{field: False for field in AUTHORITY_FIELDS},
    }


def _validate_isolation(record: Mapping[str, Any], label: str) -> None:
    if (
        record.get("track") != TRACK
        or record.get("evidence_class") != EVIDENCE_CLASS
        or record.get("universe_scope") != UNIVERSE_SCOPE
        or any(record.get(field) is not False for field in AUTHORITY_FIELDS)
    ):
        raise HistoricalReplayConflictError(f"{label} isolation contract is invalid")


def _digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _digest_without(record: Mapping[str, Any], *excluded: str) -> str:
    omitted = set(excluded)
    return _digest({key: value for key, value in record.items() if key not in omitted})


def _stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{_digest(parts)[:24]}"


def _aware(value: dt.datetime | str | None, field: str = "timestamp") -> dt.datetime:
    if value is None:
        parsed = dt.datetime.now(dt.timezone.utc)
    elif isinstance(value, dt.datetime):
        parsed = value
    else:
        try:
            parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HistoricalReplayContractError(
                f"{field} must be a timezone-aware timestamp"
            ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalReplayContractError(f"{field} must be a timezone-aware timestamp")
    return parsed


def _iso_date(value: Any, field: str) -> str:
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise HistoricalReplayContractError(f"{field} must be an ISO date") from exc


def _finite(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise HistoricalReplayContractError(f"{field} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalReplayContractError(f"{field} must be finite") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise HistoricalReplayContractError(f"{field} must be finite")
    return number


def _optional_finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, PRICE_DECIMALS) if math.isfinite(number) else None


def _cohort_id(
    source_snapshot: str,
    source_snapshot_sha256: str,
    market: str,
    generated_at: str,
    signal_date: str,
) -> str:
    return _stable_id(
        "replaycohort",
        source_snapshot,
        source_snapshot_sha256,
        market,
        generated_at,
        signal_date,
    )


def _candidate_id(cohort_id: str, market: str, code: str, rank: int, role: str) -> str:
    return _stable_id("archivepick", cohort_id, market, code, rank, role)


def _candidate_sha256(record: Mapping[str, Any]) -> str:
    return _digest_without(record, "candidate_sha256")


def _cohort_sha256(record: Mapping[str, Any]) -> str:
    return _digest_without(record, "cohort_sha256")


def _outcome_sha256(record: Mapping[str, Any]) -> str:
    return _digest_without(record, "outcome_sha256")


def _artifact_sha256(record: Mapping[str, Any]) -> str:
    return _digest_without(record, "artifact_sha256")


def _summary_sha256(record: Mapping[str, Any]) -> str:
    return _digest_without(record, "summary_sha256")


def _shortlist_rows(decision: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    rows: list[tuple[str, Mapping[str, Any]]] = []
    primary = decision.get("primary")
    if isinstance(primary, Mapping):
        rows.append(("PRIMARY", primary))
    watchlist = decision.get("watchlist")
    if isinstance(watchlist, list):
        rows.extend(("WATCHLIST", item) for item in watchlist if isinstance(item, Mapping))
    result: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for role, item in rows:
        code = str(item.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append((role, item))
    return result


def _snapshot_decisions(snapshot: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    markets = snapshot.get("markets")
    market_decisions: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(markets, Mapping):
        for market in VALID_MARKETS:
            payload = markets.get(market)
            decision = payload.get("decision") if isinstance(payload, Mapping) else None
            if isinstance(decision, Mapping):
                market_decisions.append((market, decision))
    if market_decisions:
        return market_decisions
    root = snapshot.get("decision")
    return [("a_share", root)] if isinstance(root, Mapping) else []


def _build_cohort(
    snapshot: Mapping[str, Any],
    *,
    source_snapshot: str,
    source_snapshot_sha256: str,
    market: str,
    decision: Mapping[str, Any],
) -> dict[str, Any] | None:
    archived = _shortlist_rows(decision)
    if not archived:
        return None
    generated = _aware(snapshot.get("generated_at"), "generated_at")
    generated_at = generated.isoformat(timespec="seconds")
    signal_date = _iso_date(snapshot.get("signal_date"), "signal_date")
    window = market_calendar.market_trade_window(market, generated, horizon_sessions=10)
    cohort_id = _cohort_id(
        source_snapshot,
        source_snapshot_sha256,
        market,
        generated_at,
        signal_date,
    )
    action = str(decision.get("action") or "UNKNOWN")
    shortlist: list[dict[str, Any]] = []
    for rank, (role, item) in enumerate(archived, start=1):
        code = str(item.get("code") or "").strip()
        candidate = {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "track": TRACK,
            **_isolation_contract(),
            "candidate_id": _candidate_id(cohort_id, market, code, rank, role),
            "cohort_id": cohort_id,
            "source_snapshot": source_snapshot,
            "source_snapshot_sha256": source_snapshot_sha256,
            "market": market,
            "code": code,
            "name": str(item.get("name") or code),
            "generated_at": generated_at,
            "signal_date": signal_date,
            "decision_action": action,
            "shortlist_rank": rank,
            "shortlist_role": role,
            "is_primary": role == "PRIMARY",
            "archived_score": _optional_finite(item.get("score")),
            "archived_confidence": _optional_finite(item.get("confidence")),
            "archived_recommendation_degree": _optional_finite(
                item.get("recommendation_degree")
            ),
            "archived_reference_price": _optional_finite(item.get("price")),
            "calendar_id": window["calendar_id"],
            "calendar_version": window["calendar_version"],
            "decision_time": window["decision_time"],
            "entry_trade_date": window["entry_trade_date"],
            "entry_session_open_at": window["entry_session_open_at"],
            "forecast_end_trade_date": window["forecast_end_trade_date"],
            "forecast_end_session_close_at": window[
                "forecast_end_session_close_at"
            ],
            "horizon_sessions": 10,
            "entry_policy": "first_exchange_open_after_snapshot_publication_v1",
            "exit_policy": "tenth_session_close_v1",
            "currency": CURRENCIES[market],
            "transaction_cost": TRANSACTION_COSTS[market],
            "transaction_cost_version": COST_VERSION,
            "benchmark_code": REGISTERED_BENCHMARKS[market],
            "benchmark_transaction_cost": TRANSACTION_COSTS[market],
            "benchmark_transaction_cost_version": BENCHMARK_COST_VERSION,
        }
        candidate["candidate_sha256"] = _candidate_sha256(candidate)
        shortlist.append(candidate)
    cohort = {
        "schema_version": COHORT_SCHEMA_VERSION,
        "track": TRACK,
        **_isolation_contract(),
        "limitations": list(LIMITATIONS),
        "cohort_id": cohort_id,
        "source_snapshot": source_snapshot,
        "source_snapshot_sha256": source_snapshot_sha256,
        "generated_at": generated_at,
        "signal_date": signal_date,
        "market": market,
        "decision_action": action,
        "calendar_id": window["calendar_id"],
        "calendar_version": window["calendar_version"],
        "decision_time": window["decision_time"],
        "entry_trade_date": window["entry_trade_date"],
        "entry_session_open_at": window["entry_session_open_at"],
        "forecast_end_trade_date": window["forecast_end_trade_date"],
        "forecast_end_session_close_at": window["forecast_end_session_close_at"],
        "horizon_sessions": 10,
        "shortlist_count": len(shortlist),
        "shortlist": shortlist,
    }
    cohort["cohort_sha256"] = _cohort_sha256(cohort)
    return validate_replay_cohort(cohort)


def discover_replay_cohorts(
    picks_dir: pathlib.Path,
    *,
    as_of: dt.datetime | str | None = None,
    max_cohorts: int | None = None,
) -> list[dict[str, Any]]:
    """Discover only shortlists physically preserved in immutable snapshots.

    ``latest.json`` aliases, malformed snapshots, empty decisions, and unknown
    markets are not evidence and are ignored.  ``as_of`` filters by the actual
    snapshot publication timestamp, never by a filename-derived date.
    """

    root = pathlib.Path(picks_dir)
    cutoff = _aware(as_of, "as_of")
    if max_cohorts is not None:
        if isinstance(max_cohorts, bool) or not isinstance(max_cohorts, int) or max_cohorts <= 0:
            raise HistoricalReplayContractError("max_cohorts must be a positive integer")
    if not root.is_dir():
        return []
    cohorts: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if path.name == "latest.json" or VALID_SAFE_SNAPSHOT.fullmatch(path.name) is None:
            continue
        try:
            raw = path.read_bytes()
            snapshot = json.loads(raw.decode("utf-8"))
            if not isinstance(snapshot, Mapping):
                continue
            generated = _aware(snapshot.get("generated_at"), "generated_at")
            if generated > cutoff:
                continue
            source_sha256 = hashlib.sha256(raw).hexdigest()
            for market, decision in _snapshot_decisions(snapshot):
                cohort = _build_cohort(
                    snapshot,
                    source_snapshot=path.name,
                    source_snapshot_sha256=source_sha256,
                    market=market,
                    decision=decision,
                )
                # A pre-entry revision is still provisional: a later archived
                # snapshot can legally supersede it before the same opening
                # bell.  Admit the replay cell only after that opening, when a
                # later generated snapshot necessarily belongs to a new cell.
                if cohort is not None and cutoff >= _aware(
                    str(cohort["entry_session_open_at"]),
                    "entry_session_open_at",
                ):
                    cohorts.append(cohort)
        except (OSError, UnicodeDecodeError, ValueError, TypeError):
            continue
    # Repeated intraday jobs that still point at the same market entry session
    # are revisions of one independent replay cell, not extra evidence.  Keep
    # the last legally archived version before that entry.  A snapshot emitted
    # after the open naturally receives the next entry session and therefore
    # remains a separate cohort.
    latest_by_entry: dict[tuple[str, str], dict[str, Any]] = {}
    for cohort in cohorts:
        key = (str(cohort["entry_trade_date"]), str(cohort["market"]))
        current = latest_by_entry.get(key)
        if current is None or (
            str(cohort["generated_at"]), str(cohort["source_snapshot"])
        ) > (str(current["generated_at"]), str(current["source_snapshot"])):
            latest_by_entry[key] = cohort
    cohorts = list(latest_by_entry.values())
    cohorts.sort(
        key=lambda row: (
            _aware(str(row["generated_at"]), "generated_at"),
            str(row["source_snapshot"]),
            VALID_MARKETS.index(str(row["market"])),
        )
    )
    if max_cohorts is not None:
        cohorts = cohorts[-max_cohorts:]
    return cohorts


def validate_replay_cohort(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise HistoricalReplayContractError("replay cohort must be an object")
    cohort = dict(payload)
    if cohort.get("schema_version") != COHORT_SCHEMA_VERSION:
        raise HistoricalReplayConflictError("replay cohort schema is invalid")
    _validate_isolation(cohort, "replay cohort")
    if cohort.get("limitations") != list(LIMITATIONS):
        raise HistoricalReplayConflictError("replay cohort limitations changed")
    source = str(cohort.get("source_snapshot") or "")
    source_hash = str(cohort.get("source_snapshot_sha256") or "")
    if (
        VALID_SAFE_SNAPSHOT.fullmatch(source) is None
        or source == "latest.json"
        or VALID_SHA256.fullmatch(source_hash) is None
    ):
        raise HistoricalReplayContractError("replay cohort source identity is invalid")
    market = str(cohort.get("market") or "")
    if market not in VALID_MARKETS:
        raise HistoricalReplayContractError("replay cohort market is invalid")
    generated = _aware(cohort.get("generated_at"), "generated_at")
    generated_at = generated.isoformat(timespec="seconds")
    signal_date = _iso_date(cohort.get("signal_date"), "signal_date")
    expected_id = _cohort_id(source, source_hash, market, generated_at, signal_date)
    if cohort.get("cohort_id") != expected_id or VALID_COHORT_ID.fullmatch(expected_id) is None:
        raise HistoricalReplayConflictError("replay cohort identity is invalid")
    window = market_calendar.market_trade_window(market, generated, horizon_sessions=10)
    window_fields = (
        "calendar_id",
        "calendar_version",
        "decision_time",
        "entry_trade_date",
        "entry_session_open_at",
        "forecast_end_trade_date",
        "forecast_end_session_close_at",
        "horizon_sessions",
    )
    if any(cohort.get(field) != window.get(field) for field in window_fields):
        raise HistoricalReplayConflictError("replay cohort trade window is invalid")
    raw_shortlist = cohort.get("shortlist")
    if not isinstance(raw_shortlist, list) or not raw_shortlist:
        raise HistoricalReplayContractError("replay cohort shortlist must be non-empty")
    shortlist: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for rank, raw_candidate in enumerate(raw_shortlist, start=1):
        if not isinstance(raw_candidate, Mapping):
            raise HistoricalReplayContractError("replay candidate must be an object")
        candidate = dict(raw_candidate)
        if candidate.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
            raise HistoricalReplayConflictError("replay candidate schema is invalid")
        _validate_isolation(candidate, "replay candidate")
        role = str(candidate.get("shortlist_role") or "")
        code = str(candidate.get("code") or "")
        if role not in {"PRIMARY", "WATCHLIST"} or not code or code in seen_codes:
            raise HistoricalReplayContractError("replay candidate shortlist identity is invalid")
        seen_codes.add(code)
        expected_candidate_id = _candidate_id(expected_id, market, code, rank, role)
        if (
            candidate.get("candidate_id") != expected_candidate_id
            or VALID_CANDIDATE_ID.fullmatch(expected_candidate_id) is None
            or candidate.get("cohort_id") != expected_id
            or candidate.get("market") != market
            or candidate.get("source_snapshot") != source
            or candidate.get("source_snapshot_sha256") != source_hash
            or candidate.get("generated_at") != generated_at
            or candidate.get("signal_date") != signal_date
            or candidate.get("decision_action") != cohort.get("decision_action")
            or candidate.get("shortlist_rank") != rank
            or candidate.get("is_primary") is not (role == "PRIMARY")
        ):
            raise HistoricalReplayConflictError("replay candidate frozen identity changed")
        for field in window_fields:
            if candidate.get(field) != window.get(field):
                raise HistoricalReplayConflictError("replay candidate trade window changed")
        if (
            candidate.get("currency") != CURRENCIES[market]
            or candidate.get("transaction_cost") != TRANSACTION_COSTS[market]
            or candidate.get("transaction_cost_version") != COST_VERSION
            or candidate.get("benchmark_code") != REGISTERED_BENCHMARKS[market]
            or candidate.get("benchmark_transaction_cost") != TRANSACTION_COSTS[market]
            or candidate.get("benchmark_transaction_cost_version") != BENCHMARK_COST_VERSION
            or candidate.get("entry_policy")
            != "first_exchange_open_after_snapshot_publication_v1"
            or candidate.get("exit_policy") != "tenth_session_close_v1"
        ):
            raise HistoricalReplayConflictError("replay candidate settlement contract changed")
        if candidate.get("candidate_sha256") != _candidate_sha256(candidate):
            raise HistoricalReplayConflictError("replay candidate digest is invalid")
        shortlist.append(candidate)
    if cohort.get("shortlist_count") != len(shortlist):
        raise HistoricalReplayConflictError("replay cohort shortlist count is inconsistent")
    if cohort.get("cohort_sha256") != _cohort_sha256(cohort):
        raise HistoricalReplayConflictError("replay cohort digest is invalid")
    return cohort


def _strict_adjusted_rows(
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
    latest_legal = market_calendar.market_local_date(market, as_of).isoformat()
    indexed: dict[str, Mapping[str, Any]] = {}
    previous: str | None = None
    for raw in rows:
        if not isinstance(raw, Mapping):
            return None
        try:
            date_text = dt.date.fromisoformat(str(raw.get("date"))).isoformat()
        except ValueError:
            return None
        if date_text > latest_legal or date_text in indexed or (
            previous is not None and date_text <= previous
        ):
            return None
        indexed[date_text] = raw
        previous = date_text
    return indexed, source


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


OUTCOME_FROZEN_FIELDS = (
    "candidate_id",
    "candidate_sha256",
    "cohort_id",
    "source_snapshot",
    "source_snapshot_sha256",
    "market",
    "code",
    "name",
    "generated_at",
    "signal_date",
    "decision_action",
    "shortlist_rank",
    "shortlist_role",
    "is_primary",
    "archived_score",
    "archived_confidence",
    "archived_recommendation_degree",
    "archived_reference_price",
    "calendar_id",
    "calendar_version",
    "decision_time",
    "entry_trade_date",
    "entry_session_open_at",
    "forecast_end_trade_date",
    "forecast_end_session_close_at",
    "horizon_sessions",
    "entry_policy",
    "exit_policy",
    "currency",
    "transaction_cost",
    "transaction_cost_version",
    "benchmark_code",
    "benchmark_transaction_cost",
    "benchmark_transaction_cost_version",
)


def _pending(candidate: Mapping[str, Any], status: str, reason: str) -> dict[str, Any]:
    row = {
        "schema_version": OUTCOME_SCHEMA_VERSION,
        "track": TRACK,
        **_isolation_contract(),
        "outcome_id": _stable_id("archiveout", candidate["candidate_id"]),
        **{field: candidate.get(field) for field in OUTCOME_FROZEN_FIELDS},
        "status": status,
        "reason_code": reason,
    }
    row["outcome_sha256"] = _outcome_sha256(row)
    return row


def _settled(
    candidate: Mapping[str, Any],
    moment: dt.datetime,
    stock_loaded: Any,
    benchmark_loaded: Any,
) -> dict[str, Any]:
    stock_payload = _strict_adjusted_rows(
        stock_loaded, market=str(candidate["market"]), as_of=moment
    )
    benchmark_payload = _strict_adjusted_rows(
        benchmark_loaded, market=str(candidate["market"]), as_of=moment
    )
    if stock_payload is None or benchmark_payload is None:
        return _pending(candidate, "PENDING_DATA", "ADJUSTED_PRICE_EVIDENCE_MISSING")
    stock_by_date, stock_source = stock_payload
    benchmark_by_date, benchmark_source = benchmark_payload
    sessions = [
        day.isoformat()
        for day in market_calendar.session_dates(
            str(candidate["market"]),
            str(candidate["entry_trade_date"]),
            str(candidate["forecast_end_trade_date"]),
        )
    ]
    if (
        len(sessions) != 10
        or any(day not in stock_by_date for day in sessions)
        or any(day not in benchmark_by_date for day in sessions)
    ):
        return _pending(candidate, "PENDING_DATA", "COMPLETE_ADJUSTED_WINDOW_MISSING")
    entry_day, exit_day = sessions[0], sessions[-1]
    entry = _positive(stock_by_date[entry_day].get("open"))
    exit_ = _positive(stock_by_date[exit_day].get("close"))
    lows = [_positive(stock_by_date[day].get("low")) for day in sessions]
    benchmark_entry = _positive(benchmark_by_date[entry_day].get("open"))
    benchmark_exit = _positive(benchmark_by_date[exit_day].get("close"))
    if None in (entry, exit_, benchmark_entry, benchmark_exit) or any(
        value is None for value in lows
    ):
        return _pending(candidate, "PENDING_DATA", "COMPLETE_ADJUSTED_WINDOW_MISSING")
    entry = round(float(entry), PRICE_DECIMALS)
    exit_ = round(float(exit_), PRICE_DECIMALS)
    benchmark_entry = round(float(benchmark_entry), PRICE_DECIMALS)
    benchmark_exit = round(float(benchmark_exit), PRICE_DECIMALS)
    gross = round(exit_ / entry - 1.0, RETURN_DECIMALS)
    net = round(gross - float(candidate["transaction_cost"]), RETURN_DECIMALS)
    benchmark_gross = round(benchmark_exit / benchmark_entry - 1.0, RETURN_DECIMALS)
    benchmark_net = round(
        benchmark_gross - float(candidate["benchmark_transaction_cost"]),
        RETURN_DECIMALS,
    )
    excess = round(net - benchmark_net, RETURN_DECIMALS)
    mae = round(min(float(value) for value in lows if value is not None) / entry - 1.0, RETURN_DECIMALS)
    row = _pending(candidate, "SETTLED", "")
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
        "schema_version": PRICE_EVIDENCE_SCHEMA_VERSION,
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
            {
                "date": day,
                "low": round(float(stock_by_date[day]["low"]), PRICE_DECIMALS),
            }
            for day in sessions
        ],
    }
    evidence["evidence_sha256"] = _digest_without(evidence, "evidence_sha256")
    row["price_evidence"] = evidence
    row["price_evidence_sha256"] = evidence["evidence_sha256"]
    row["outcome_sha256"] = _outcome_sha256(row)
    return row


def _status(counts: Counter[str], count: int) -> str:
    if count == 0:
        return "EMPTY"
    return next(iter(counts)) if len(counts) == 1 else "PARTIAL"


def _build_summary(
    cohorts: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
    evaluated_at: str,
) -> dict[str, Any]:
    status_counts = Counter(str(row["status"]) for row in outcomes)
    settled = [row for row in outcomes if row.get("status") == "SETTLED"]
    market_counts = Counter(
        str(candidate["market"])
        for cohort in cohorts
        for candidate in cohort.get("shortlist", [])
    )
    if settled:
        mean_net = round(
            sum(float(row["net_total_return"]) for row in settled) / len(settled),
            RETURN_DECIMALS,
        )
        mean_excess = round(
            sum(float(row["net_excess_return"]) for row in settled) / len(settled),
            RETURN_DECIMALS,
        )
        positive_rate = round(
            sum(float(row["net_total_return"]) > 0 for row in settled) / len(settled),
            RETURN_DECIMALS,
        )
        positive_excess_rate = round(
            sum(float(row["net_excess_return"]) > 0 for row in settled) / len(settled),
            RETURN_DECIMALS,
        )
    else:
        mean_net = mean_excess = positive_rate = positive_excess_rate = None
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "track": TRACK,
        **_isolation_contract(),
        "limitations": list(LIMITATIONS),
        "evaluated_at": evaluated_at,
        "status": _status(status_counts, len(outcomes)),
        "probability_status": "NOT_APPLICABLE",
        "calibrated": False,
        "cohort_count": len(cohorts),
        "signal_date_count": len({str(row["signal_date"]) for row in cohorts}),
        "independent_entry_date_count": len(
            {
                (str(row["market"]), str(row["entry_trade_date"]))
                for row in cohorts
            }
        ),
        "shortlist_count": len(outcomes),
        "settled_count": len(settled),
        "pending_count": len(outcomes) - len(settled),
        "status_counts": dict(sorted(status_counts.items())),
        "market_counts": dict(sorted(market_counts.items())),
        "metrics": {
            "sample_count": len(settled),
            "mean_net_return": mean_net,
            "mean_net_total_return": mean_net,
            "mean_net_excess_return": mean_excess,
            "positive_net_return_rate": positive_rate,
            "positive_net_excess_return_rate": positive_excess_rate,
        },
    }
    summary["summary_sha256"] = _summary_sha256(summary)
    return summary


def _default_price_loader(market: str, code: str):
    # Kept lazy so pure discovery/validation never imports the network-facing
    # selector module and tests can always inject deterministic evidence.
    from scripts.settle_outcomes import market_rows

    return market_rows(market, code)


def build_replay_artifact(
    cohorts: Sequence[Mapping[str, Any]],
    *,
    as_of: dt.datetime | str | None = None,
    price_loader: PriceLoader | None = None,
    benchmark_price_loader: PriceLoader | None = None,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Settle archived shortlist cohorts without entering any live ledger."""

    if isinstance(cohorts, (str, bytes)) or not isinstance(cohorts, Sequence):
        raise HistoricalReplayContractError("cohorts must be a sequence")
    normalized = [validate_replay_cohort(row) for row in cohorts]
    normalized.sort(
        key=lambda row: (
            str(row["generated_at"]),
            str(row["source_snapshot"]),
            VALID_MARKETS.index(str(row["market"])),
        )
    )
    cohort_ids = [str(row["cohort_id"]) for row in normalized]
    if len(set(cohort_ids)) != len(cohort_ids):
        raise HistoricalReplayConflictError("duplicate replay cohort identity")
    entry_cells = [
        (str(row["market"]), str(row["entry_trade_date"])) for row in normalized
    ]
    if len(set(entry_cells)) != len(entry_cells):
        raise HistoricalReplayConflictError("duplicate market entry replay cell")
    moment = _aware(as_of, "as_of")
    evaluated_at = moment.isoformat(timespec="seconds")
    previous = validate_replay_artifact(existing) if existing is not None else None
    previous_cohorts = {
        str(row["cohort_id"]): row for row in (previous or {}).get("cohorts", [])
    }
    incoming_cohorts = {str(row["cohort_id"]): row for row in normalized}
    if set(previous_cohorts) - set(incoming_cohorts):
        raise HistoricalReplayConflictError("existing replay cohorts cannot be removed")
    for identifier, old in previous_cohorts.items():
        if incoming_cohorts.get(identifier) != old:
            raise HistoricalReplayConflictError("frozen replay cohort changed")
    if previous is not None and moment < _aware(previous["evaluated_at"], "evaluated_at"):
        raise HistoricalReplayConflictError("replay as_of moved backwards")

    candidates = [candidate for cohort in normalized for candidate in cohort["shortlist"]]
    previous_rows = {
        str(row["candidate_id"]): row for row in (previous or {}).get("outcomes", [])
    }
    if set(previous_rows) - {str(row["candidate_id"]) for row in candidates}:
        raise HistoricalReplayConflictError("existing replay candidates cannot be removed")
    stock_loader = price_loader or _default_price_loader
    benchmark_loader = benchmark_price_loader or stock_loader
    stock_cache: dict[tuple[str, str], Any] = {}
    benchmark_cache: dict[tuple[str, str], Any] = {}

    def cached(loader: PriceLoader, cache: dict[tuple[str, str], Any], market: str, code: str):
        key = (market, code)
        if key not in cache:
            try:
                cache[key] = loader(market, code)
            except Exception:
                cache[key] = ([], "", False)
        return cache[key]

    outcomes: list[dict[str, Any]] = []
    for candidate in candidates:
        old = previous_rows.get(str(candidate["candidate_id"]))
        if old is not None and old.get("status") == "SETTLED":
            outcomes.append(dict(old))
            continue
        maturity = _aware(candidate["forecast_end_session_close_at"], "maturity")
        if moment <= maturity:
            outcomes.append(
                _pending(candidate, "PENDING_MATURITY", "FORECAST_WINDOW_OPEN")
            )
            continue
        market = str(candidate["market"])
        outcomes.append(
            _settled(
                candidate,
                moment,
                cached(stock_loader, stock_cache, market, str(candidate["code"])),
                cached(
                    benchmark_loader,
                    benchmark_cache,
                    market,
                    str(candidate["benchmark_code"]),
                ),
            )
        )
    counts = Counter(str(row["status"]) for row in outcomes)
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "track": TRACK,
        **_isolation_contract(),
        "limitations": list(LIMITATIONS),
        "evaluated_at": evaluated_at,
        "status": _status(counts, len(outcomes)),
        "cohort_count": len(normalized),
        "cohort_ids": cohort_ids,
        "shortlist_count": len(candidates),
        "status_counts": dict(sorted(counts.items())),
        "cohorts": normalized,
        "outcomes": outcomes,
    }
    artifact["summary"] = _build_summary(normalized, outcomes, evaluated_at)
    artifact["artifact_sha256"] = _artifact_sha256(artifact)
    validated = validate_replay_artifact(artifact)
    if (
        previous is not None
        and previous["cohorts"] == validated["cohorts"]
        and all(row.get("status") == "SETTLED" for row in previous["outcomes"])
    ):
        return dict(previous)
    return validated


def validate_replay_artifact(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise HistoricalReplayContractError("replay artifact must be an object")
    artifact = dict(payload)
    if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise HistoricalReplayConflictError("replay artifact schema is invalid")
    _validate_isolation(artifact, "replay artifact")
    if artifact.get("limitations") != list(LIMITATIONS):
        raise HistoricalReplayConflictError("replay artifact limitations changed")
    evaluated = _aware(artifact.get("evaluated_at"), "evaluated_at")
    cohorts_raw = artifact.get("cohorts")
    if not isinstance(cohorts_raw, list):
        raise HistoricalReplayContractError("replay artifact cohorts must be a list")
    cohorts = [validate_replay_cohort(row) for row in cohorts_raw]
    expected_cohort_ids = [row["cohort_id"] for row in cohorts]
    entry_cells = [
        (str(row["market"]), str(row["entry_trade_date"])) for row in cohorts
    ]
    if (
        len(set(expected_cohort_ids)) != len(expected_cohort_ids)
        or len(set(entry_cells)) != len(entry_cells)
        or artifact.get("cohort_ids") != expected_cohort_ids
        or artifact.get("cohort_count") != len(cohorts)
    ):
        raise HistoricalReplayConflictError("replay cohort summary is inconsistent")
    candidates = [candidate for cohort in cohorts for candidate in cohort["shortlist"]]
    outcomes_raw = artifact.get("outcomes")
    if not isinstance(outcomes_raw, list) or len(outcomes_raw) != len(candidates):
        raise HistoricalReplayConflictError("replay outcome coverage is inconsistent")
    counts: Counter[str] = Counter()
    outcomes: list[dict[str, Any]] = []
    settlement_only_fields = {
        "entry_open",
        "exit_close",
        "gross_total_return",
        "net_total_return",
        "benchmark_entry_open",
        "benchmark_exit_close",
        "benchmark_gross_return",
        "benchmark_net_return",
        "net_excess_return",
        "maximum_adverse_excursion",
        "settled_at",
        "price_source",
        "benchmark_price_source",
        "corporate_action_adjusted",
        "price_evidence",
        "price_evidence_sha256",
    }
    for candidate, raw in zip(candidates, outcomes_raw):
        if not isinstance(raw, Mapping):
            raise HistoricalReplayContractError("replay outcome must be an object")
        row = dict(raw)
        if row.get("schema_version") != OUTCOME_SCHEMA_VERSION:
            raise HistoricalReplayConflictError("replay outcome schema is invalid")
        _validate_isolation(row, "replay outcome")
        expected_outcome_id = _stable_id("archiveout", candidate["candidate_id"])
        if (
            row.get("outcome_id") != expected_outcome_id
            or VALID_OUTCOME_ID.fullmatch(expected_outcome_id) is None
        ):
            raise HistoricalReplayConflictError("replay outcome identity is invalid")
        for field in OUTCOME_FROZEN_FIELDS:
            if row.get(field) != candidate.get(field):
                raise HistoricalReplayConflictError(
                    f"replay outcome frozen identity changed: {field}"
                )
        status = str(row.get("status") or "")
        if status not in VALID_STATUSES:
            raise HistoricalReplayContractError("replay outcome status is invalid")
        maturity = _aware(row.get("forecast_end_session_close_at"), "maturity")
        if status == "PENDING_MATURITY":
            if evaluated > maturity or row.get("reason_code") != "FORECAST_WINDOW_OPEN":
                raise HistoricalReplayConflictError("pending replay maturity is invalid")
        elif status == "PENDING_DATA":
            if evaluated <= maturity or row.get("reason_code") not in PENDING_DATA_REASONS:
                raise HistoricalReplayConflictError("pending replay data state is invalid")
        elif evaluated <= maturity:
            raise HistoricalReplayConflictError("settled replay outcome precedes maturity")
        if status != "SETTLED":
            if any(field in row for field in settlement_only_fields):
                raise HistoricalReplayConflictError(
                    "pending replay outcome contains settlement evidence"
                )
        else:
            if row.get("reason_code") is not None or any(
                field not in row for field in settlement_only_fields
            ):
                raise HistoricalReplayConflictError("settled replay outcome is incomplete")
            numeric_fields = (
                "entry_open",
                "exit_close",
                "gross_total_return",
                "net_total_return",
                "benchmark_entry_open",
                "benchmark_exit_close",
                "benchmark_gross_return",
                "benchmark_net_return",
                "net_excess_return",
                "maximum_adverse_excursion",
            )
            if not all(
                isinstance(row.get(field), (int, float))
                and not isinstance(row.get(field), bool)
                and math.isfinite(float(row[field]))
                for field in numeric_fields
            ):
                raise HistoricalReplayConflictError("settled replay values are not finite")
            entry = _finite(row["entry_open"], "entry_open", positive=True)
            exit_ = _finite(row["exit_close"], "exit_close", positive=True)
            benchmark_entry = _finite(
                row["benchmark_entry_open"], "benchmark_entry_open", positive=True
            )
            benchmark_exit = _finite(
                row["benchmark_exit_close"], "benchmark_exit_close", positive=True
            )
            gross = round(exit_ / entry - 1.0, RETURN_DECIMALS)
            net = round(gross - float(row["transaction_cost"]), RETURN_DECIMALS)
            benchmark_gross = round(
                benchmark_exit / benchmark_entry - 1.0, RETURN_DECIMALS
            )
            benchmark_net = round(
                benchmark_gross - float(row["benchmark_transaction_cost"]),
                RETURN_DECIMALS,
            )
            excess = round(net - benchmark_net, RETURN_DECIMALS)
            if any(
                abs(float(row[field]) - expected) > 1e-12
                for field, expected in (
                    ("gross_total_return", gross),
                    ("net_total_return", net),
                    ("benchmark_gross_return", benchmark_gross),
                    ("benchmark_net_return", benchmark_net),
                    ("net_excess_return", excess),
                )
            ):
                raise HistoricalReplayConflictError("settled replay return math is invalid")
            if row.get("corporate_action_adjusted") is not True:
                raise HistoricalReplayConflictError("settled replay prices must be adjusted")
            settled_at = _aware(row.get("settled_at"), "settled_at")
            if not maturity < settled_at <= evaluated:
                raise HistoricalReplayConflictError("replay settled_at is outside legal window")
            evidence = row.get("price_evidence")
            if not isinstance(evidence, Mapping):
                raise HistoricalReplayConflictError("replay price evidence is missing")
            sessions = [
                day.isoformat()
                for day in market_calendar.session_dates(
                    str(row["market"]),
                    str(row["entry_trade_date"]),
                    str(row["forecast_end_trade_date"]),
                )
            ]
            lows = evidence.get("session_lows")
            if (
                evidence.get("schema_version") != PRICE_EVIDENCE_SCHEMA_VERSION
                or evidence.get("corporate_action_adjusted") is not True
                or evidence.get("stock_source") != row.get("price_source")
                or evidence.get("benchmark_source") != row.get("benchmark_price_source")
                or evidence.get("entry_date") != sessions[0]
                or evidence.get("exit_date") != sessions[-1]
                or evidence.get("entry_open") != row.get("entry_open")
                or evidence.get("exit_close") != row.get("exit_close")
                or evidence.get("benchmark_entry_open") != row.get("benchmark_entry_open")
                or evidence.get("benchmark_exit_close") != row.get("benchmark_exit_close")
                or not isinstance(lows, list)
                or len(lows) != len(sessions)
                or [item.get("date") for item in lows if isinstance(item, Mapping)]
                != sessions
                or evidence.get("evidence_sha256")
                != _digest_without(evidence, "evidence_sha256")
                or row.get("price_evidence_sha256") != evidence.get("evidence_sha256")
            ):
                raise HistoricalReplayConflictError("replay price evidence is inconsistent")
            low_values = [
                _finite(item.get("low"), "price_evidence.low", positive=True)
                for item in lows
                if isinstance(item, Mapping)
            ]
            if len(low_values) != len(sessions) or abs(
                float(row["maximum_adverse_excursion"])
                - round(min(low_values) / entry - 1.0, RETURN_DECIMALS)
            ) > 1e-12:
                raise HistoricalReplayConflictError("replay adverse excursion is inconsistent")
        if row.get("outcome_sha256") != _outcome_sha256(row):
            raise HistoricalReplayConflictError("replay outcome digest is invalid")
        counts[status] += 1
        outcomes.append(row)
    if (
        artifact.get("shortlist_count") != len(candidates)
        or artifact.get("status_counts") != dict(sorted(counts.items()))
        or artifact.get("status") != _status(counts, len(outcomes))
    ):
        raise HistoricalReplayConflictError("replay outcome summary is inconsistent")
    expected_summary = _build_summary(
        cohorts, outcomes, evaluated.isoformat(timespec="seconds")
    )
    if artifact.get("summary") != expected_summary:
        raise HistoricalReplayConflictError("replay public summary is inconsistent")
    if artifact.get("artifact_sha256") != _artifact_sha256(artifact):
        raise HistoricalReplayConflictError("replay artifact digest is invalid")
    return artifact


def public_model_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the validated UI-safe summary for this retrospective track."""

    return dict(validate_replay_artifact(payload)["summary"])


def summarize_replay_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible descriptive alias for :func:`public_model_summary`."""

    return public_model_summary(payload)


def write_replay_artifact(path: pathlib.Path, payload: Mapping[str, Any]) -> pathlib.Path:
    """Atomically persist an artifact without ever replacing a settled row."""

    target = pathlib.Path(path)
    incoming = validate_replay_artifact(payload)
    if target.is_file():
        try:
            current = validate_replay_artifact(
                json.loads(target.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError) as exc:
            raise HistoricalReplayConflictError("existing replay artifact is unreadable") from exc
        current_cohorts = {row["cohort_id"]: row for row in current["cohorts"]}
        incoming_cohorts = {row["cohort_id"]: row for row in incoming["cohorts"]}
        if set(current_cohorts) - set(incoming_cohorts) or any(
            incoming_cohorts.get(identifier) != row
            for identifier, row in current_cohorts.items()
        ):
            raise HistoricalReplayConflictError("refusing to rewrite a frozen replay cohort")
        incoming_rows = {row["candidate_id"]: row for row in incoming["outcomes"]}
        for row in current["outcomes"]:
            if row.get("status") == "SETTLED" and incoming_rows.get(row["candidate_id"]) != row:
                raise HistoricalReplayConflictError(
                    "refusing to rewrite an immutable settled replay row"
                )
        if current == incoming:
            return target
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        incoming, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(rendered)
        temporary = pathlib.Path(handle.name)
    temporary.replace(target)
    return target


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "CANDIDATE_SCHEMA_VERSION",
    "COHORT_SCHEMA_VERSION",
    "EVIDENCE_CLASS",
    "HistoricalReplayConflictError",
    "HistoricalReplayContractError",
    "OUTCOME_SCHEMA_VERSION",
    "SUMMARY_SCHEMA_VERSION",
    "TRACK",
    "UNIVERSE_SCOPE",
    "build_replay_artifact",
    "discover_replay_cohorts",
    "public_model_summary",
    "summarize_replay_artifact",
    "validate_replay_artifact",
    "validate_replay_cohort",
    "write_replay_artifact",
]

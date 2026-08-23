#!/usr/bin/env python3
"""Create and settle isolated ten-session outcome ledgers.

The existing shadow ledger remains deliberately separate from executable-model
performance.  Formal outcomes live in their own directory and are admitted only
from the strict, calibrated ``global_decision.primary`` contract.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from typing import Any, Callable
from zoneinfo import ZoneInfo


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import market_calendar  # noqa: E402
import history_evaluation  # noqa: E402
import model_observation_ledger  # noqa: E402
import server  # noqa: E402


PICKS = ROOT / "data" / "picks"
OUTCOMES = ROOT / "data" / "outcomes"
EXECUTABLE_OUTCOMES = OUTCOMES / "executable"
SHADOW_LEDGER_SCHEMA = "shadow-outcome-v1"
EXECUTABLE_LEDGER_SCHEMA = "executable-outcome-v1"
SHADOW_TRACK = "SHADOW_RESEARCH"
EXECUTABLE_TRACK = "EXECUTABLE_MODEL"
# Backwards-compatible aliases used by older callers and tests.
LEDGER_SCHEMA = SHADOW_LEDGER_SCHEMA
TRACK = SHADOW_TRACK
COST_ASSUMPTIONS = {"a_share": 0.0015, "hk": 0.0030, "us": 0.0015}
CURRENCIES = {"a_share": "CNY", "hk": "HKD", "us": "USD"}
PUBLISHED_PRICE_DECIMALS = 8
PUBLISHED_RETURN_DECIMALS = 8
VALID_ID = re.compile(r"^pred_[a-f0-9]{16,64}$")
CONTRACT_IDENTITY_KEYS = (
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

SHADOW_RETRY_INVARIANT_KEYS = (
    "schema_version",
    "track",
    "prediction_id",
    "model_id",
    "label_version",
    "market",
    "code",
    "signal_date",
    "sampling_policy",
    "entry_session_open_at",
    "entry_trade_date",
    "forecast_end_trade_date",
    "forecast_end_session_close_at",
    "horizon_trade_sessions",
    "entry_policy",
    "exit_policy",
    "calendar_id",
    "calendar_version",
    "currency",
    "fx_rate_source",
    "transaction_cost",
)


def contract_identity_keys(contract: dict[str, Any]) -> tuple[str, ...]:
    if contract.get("track") == SHADOW_TRACK:
        return CONTRACT_IDENTITY_KEYS + ("artifact_sha256", "training_cutoff")
    return CONTRACT_IDENTITY_KEYS


def _contract_moment(contract: dict[str, Any], key: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(contract.get(key) or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _shadow_retry_sample_matches(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    """Return whether two contracts are retries of one scheduled sample.

    Technical probability, expected utility, tail estimate, training cutoff and
    artifact are intentionally absent from the invariant envelope: those are
    allowed to improve during the same pre-entry health retry.  Slot, selected
    security and settlement identity are immutable.
    """

    if (
        left.get("track") != SHADOW_TRACK
        or right.get("track") != SHADOW_TRACK
        or left.get("sampling_policy") != "daily_last_primary_checkpoint_v1"
        or right.get("sampling_policy") != "daily_last_primary_checkpoint_v1"
        or any(left.get(key) != right.get(key) for key in SHADOW_RETRY_INVARIANT_KEYS)
    ):
        return False
    left_slot = _contract_moment(left, "scheduled_slot")
    right_slot = _contract_moment(right, "scheduled_slot")
    return left_slot is not None and right_slot is not None and left_slot == right_slot


def _contract_is_pre_entry(contract: dict[str, Any]) -> bool:
    generated_at = _contract_moment(contract, "generated_at")
    entry_at = _contract_moment(contract, "entry_session_open_at")
    return generated_at is not None and entry_at is not None and generated_at < entry_at


def _same_contract_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = contract_identity_keys(right)
    return all(left.get(key) == right.get(key) for key in keys)


def _source_preference(contract: dict[str, Any]) -> tuple[int, str]:
    """Prefer immutable snapshot names over the mutable latest.json alias."""

    source = str(contract.get("source_snapshot") or "")
    return (0 if source == "latest.json" else 1, source)


def _newest_shadow_retry_contract(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any] | None:
    """Choose the later healthy pre-entry retry, or fail closed with ``None``."""

    if (
        not _shadow_retry_sample_matches(left, right)
        or not _contract_is_pre_entry(left)
        or not _contract_is_pre_entry(right)
    ):
        return None
    left_generated = _contract_moment(left, "generated_at")
    right_generated = _contract_moment(right, "generated_at")
    if left_generated is None or right_generated is None:
        return None
    if right_generated > left_generated:
        return right
    if left_generated > right_generated:
        return left
    # Equal-generation aliases are common because latest.json duplicates the
    # immutable snapshot.  Differing technical values at the exact same moment
    # have no well-defined retry order and therefore remain a hard conflict.
    if not _same_contract_identity(left, right):
        return None
    return max((left, right), key=_source_preference)


def read_json(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def write_json_atomic(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def eligible_for_shadow_ledger(snapshot: dict[str, Any]) -> bool:
    """Apply the shared healthy technical-Shadow sampling policy.

    Health fallbacks inherit the primary checkpoint in ``scheduled_slot``, so a
    successful 23:17 recovery remains eligible for the 22:47 daily sample.
    It is a retry of that sample rather than an independent observation.
    """

    return history_evaluation.eligible_shadow_snapshot(snapshot)


def candidate_contract(snapshot: dict[str, Any], source_name: str) -> dict[str, Any] | None:
    if not eligible_for_shadow_ledger(snapshot):
        return None
    automation = snapshot.get("automation")
    automation = automation if isinstance(automation, dict) else {}
    sampling_policy = (
        "daily_last_primary_checkpoint_v1"
        if str(automation.get("trigger") or "") == "schedule"
        else "legacy_snapshot_v1"
    )
    decision = snapshot.get("global_decision") or {}
    candidate = history_evaluation.shadow_research_contract(decision.get("research_priority"))
    if candidate is None:
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
    if not all(candidate.get(key) for key in required):
        return None
    prediction_id = str(candidate["prediction_id"])
    if not VALID_ID.fullmatch(prediction_id):
        return None
    market = str(candidate["market"])
    if market not in COST_ASSUMPTIONS:
        return None
    technical_shadow = isinstance(candidate.get("shadow_model"), dict)
    transaction_cost = (
        float(candidate["transaction_cost"])
        if technical_shadow
        else COST_ASSUMPTIONS[market]
    )
    try:
        generated_at = dt.datetime.fromisoformat(
            str(snapshot.get("generated_at") or "").replace("Z", "+00:00")
        )
        entry_date = dt.date.fromisoformat(str(candidate["entry_trade_date"]))
        exit_date = dt.date.fromisoformat(str(candidate["forecast_end_trade_date"]))
    except ValueError:
        return None
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        return None
    expected_window = market_calendar.market_trade_window(market, generated_at, horizon_sessions=10)
    if (
        entry_date.isoformat() != expected_window["entry_trade_date"]
        or exit_date.isoformat() != expected_window["forecast_end_trade_date"]
        or exit_date <= entry_date
        or str(candidate["calendar_id"]) != expected_window["calendar_id"]
        or str(candidate["calendar_version"]) != expected_window["calendar_version"]
    ):
        return None
    return {
        "schema_version": SHADOW_LEDGER_SCHEMA,
        "track": SHADOW_TRACK,
        "status": "PENDING",
        "prediction_id": prediction_id,
        "model_id": candidate["model_id"],
        "label_version": candidate["label_version"],
        "market": market,
        "code": candidate["code"],
        "name": candidate.get("name"),
        "generated_at": snapshot.get("generated_at"),
        "signal_date": snapshot.get("signal_date"),
        "source_snapshot": source_name,
        "sampling_policy": sampling_policy,
        "scheduled_slot": automation.get("scheduled_slot"),
        "score_kind": candidate.get("priority_score_kind") or candidate.get("score_kind"),
        "priority_score": candidate.get("priority_score"),
        "probability": candidate.get("probability"),
        "expected_net_utility": candidate.get("expected_net_utility"),
        "tail_risk": candidate.get("tail_risk"),
        "artifact_sha256": candidate.get("artifact_sha256"),
        "training_cutoff": candidate.get("training_cutoff"),
        "entry_session_open_at": expected_window["entry_session_open_at"],
        "entry_trade_date": entry_date.isoformat(),
        "forecast_end_trade_date": exit_date.isoformat(),
        "forecast_end_session_close_at": expected_window["forecast_end_session_close_at"],
        "horizon_trade_sessions": 10,
        "entry_policy": "next_session_open_v1",
        "exit_policy": "tenth_session_close_v1",
        "calendar_id": expected_window["calendar_id"],
        "calendar_version": expected_window["calendar_version"],
        "currency": CURRENCIES[market],
        "fx_rate_source": "not_required_same_currency_return",
        "transaction_cost": transaction_cost,
        "corporate_action_adjusted": False,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def executable_candidate_contract(snapshot: dict[str, Any], source_name: str) -> dict[str, Any] | None:
    """Return a formal contract only for a complete calibrated global decision."""

    decision = snapshot.get("global_decision")
    if not isinstance(decision, dict):
        return None
    if (
        decision.get("contract_version") != "global-10d-v1"
        or decision.get("decision_scope") != "global_10d"
        or decision.get("action_basis") != "strict_cross_market_gate_v1"
        or decision.get("action") != "REVIEW_EXECUTABLE_PICK"
        or decision.get("probability_status") != "CALIBRATED"
        or decision.get("calibrated") is not True
        or decision.get("horizon_trade_days") != 10
        or bool(decision.get("blocker_codes"))
    ):
        return None

    candidate = decision.get("primary")
    if not isinstance(candidate, dict):
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
    if (
        not all(candidate.get(key) for key in required)
        or candidate.get("status") != "EXECUTABLE"
        or candidate.get("calibrated") is not True
        or candidate.get("score_kind") != "TEN_DAY_EXPECTED_NET_UTILITY"
    ):
        return None

    prediction_id = str(candidate["prediction_id"])
    market = str(candidate["market"])
    if not VALID_ID.fullmatch(prediction_id) or market not in COST_ASSUMPTIONS:
        return None
    if (
        str(candidate["calendar_id"]) != market_calendar.calendar_id(market)
        or str(candidate["calendar_version"]) != market_calendar.CALENDAR_VERSION
    ):
        return None

    probability = finite_number(candidate.get("probability"))
    decision_probability = finite_number(decision.get("probability"))
    expected_net_utility = finite_number(candidate.get("expected_net_utility"))
    transaction_cost = finite_number(candidate.get("transaction_cost"))
    tail_risk = finite_number(candidate.get("tail_risk"))
    if (
        probability is None
        or not 0 <= probability <= 1
        or decision_probability is None
        or abs(decision_probability - probability) > 1e-12
        or expected_net_utility is None
        or expected_net_utility <= 0
        or transaction_cost is None
        or transaction_cost < 0
        or tail_risk is None
        or tail_risk < 0
    ):
        return None

    try:
        generated_at = dt.datetime.fromisoformat(str(snapshot.get("generated_at") or "").replace("Z", "+00:00"))
        entry_date = dt.date.fromisoformat(str(candidate["entry_trade_date"]))
        exit_date = dt.date.fromisoformat(str(candidate["forecast_end_trade_date"]))
    except ValueError:
        return None
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        return None
    expected_window = market_calendar.market_trade_window(market, generated_at, horizon_sessions=10)
    if (
        entry_date.isoformat() != expected_window["entry_trade_date"]
        or exit_date.isoformat() != expected_window["forecast_end_trade_date"]
        or exit_date <= entry_date
    ):
        return None

    automation = snapshot.get("automation")
    automation = automation if isinstance(automation, dict) else {}
    return {
        "schema_version": EXECUTABLE_LEDGER_SCHEMA,
        "track": EXECUTABLE_TRACK,
        "status": "PENDING",
        "prediction_id": prediction_id,
        "model_id": candidate["model_id"],
        "label_version": candidate["label_version"],
        "market": market,
        "code": candidate["code"],
        "name": candidate.get("name"),
        "generated_at": snapshot["generated_at"],
        "signal_date": snapshot.get("signal_date"),
        "source_snapshot": source_name,
        "sampling_policy": "all_published_executable_predictions_v1",
        "scheduled_slot": automation.get("scheduled_slot"),
        "score_kind": candidate["score_kind"],
        "probability": probability,
        "expected_net_utility": expected_net_utility,
        "tail_risk": tail_risk,
        "entry_session_open_at": expected_window["entry_session_open_at"],
        "entry_trade_date": entry_date.isoformat(),
        "forecast_end_trade_date": exit_date.isoformat(),
        "forecast_end_session_close_at": expected_window["forecast_end_session_close_at"],
        "horizon_trade_sessions": 10,
        "entry_policy": "next_session_open_v1",
        "exit_policy": "tenth_session_close_v1",
        "calendar_id": candidate["calendar_id"],
        "calendar_version": candidate["calendar_version"],
        "currency": CURRENCIES[market],
        "fx_rate_source": "not_required_same_currency_return",
        "transaction_cost": transaction_cost,
        "corporate_action_adjusted": False,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _discover_contracts(
    picks_dir: pathlib.Path,
    builder: Callable[[dict[str, Any], str], dict[str, Any] | None],
    *,
    shadow_retry_policy: bool = False,
) -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    paths = sorted(picks_dir.glob("*.json"))
    latest_path = picks_dir / "latest.json"
    if latest_path in paths:
        paths.remove(latest_path)
        paths.append(latest_path)
    for path in paths:
        snapshot = read_json(path)
        if not snapshot:
            continue
        contract = builder(snapshot, path.name)
        if contract:
            prediction_id = str(contract["prediction_id"])
            existing = contracts.get(prediction_id)
            if existing is None:
                contracts[prediction_id] = contract
                continue
            if shadow_retry_policy:
                selected = _newest_shadow_retry_contract(existing, contract)
                if selected is None:
                    raise RuntimeError(f"outcome identity conflict: {prediction_id}")
                contracts[prediction_id] = selected
                continue
            if not _same_contract_identity(existing, contract):
                raise RuntimeError(f"outcome identity conflict: {prediction_id}")
    return contracts


def discover_contracts(picks_dir: pathlib.Path = PICKS) -> dict[str, dict[str, Any]]:
    """Discover one newest eligible technical Shadow contract per daily slot."""

    return _discover_contracts(picks_dir, candidate_contract, shadow_retry_policy=True)


def discover_executable_contracts(picks_dir: pathlib.Path = PICKS) -> dict[str, dict[str, Any]]:
    return _discover_contracts(picks_dir, executable_candidate_contract)


def market_rows(market: str, code: str) -> tuple[list[dict[str, Any]], str, bool]:
    if market == "a_share":
        # Settlement labels represent total return, so A-share entry/exit bars
        # must come from the same explicit qfq-only chain as model history.
        # ``qfq_stock_kline`` deliberately excludes providers/series whose
        # adjustment basis cannot be verified and returns no rows when neither
        # explicit qfq source is available.
        rows = server.qfq_stock_kline(str(code), 180)
        return rows, "a_share_qfq_daily", bool(rows)
    symbol = str(code).upper()
    if market == "hk":
        digits = re.sub(r"\.HK$", "", symbol).lstrip("0") or "0"
        symbol = f"{digits.zfill(4)}.HK"
    rows = yahoo_adjusted_rows(symbol, market)
    return rows, "yahoo_chart_adjusted_daily", bool(rows)


def yahoo_adjusted_rows(symbol: str, market: str, limit: int = 260) -> list[dict[str, Any]]:
    """Return split/dividend-adjusted daily open and close values."""

    target = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
    query = urllib.parse.urlencode(
        {"range": "1y", "interval": "1d", "includePrePost": "false", "events": "div,splits"}
    )
    try:
        request = urllib.request.Request(
            f"{target}?{query}",
            headers={"User-Agent": server.UA, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.load(response)
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not result:
            return []
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        adjclose = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
        opens = quote.get("open") or []
        closes = quote.get("close") or []
        timezone_name = (result.get("meta") or {}).get("exchangeTimezoneName")
        exchange_tz = ZoneInfo(timezone_name or ("America/New_York" if market == "us" else "Asia/Hong_Kong"))
    except Exception:
        return []

    rows = []
    for index, timestamp in enumerate(timestamps):
        try:
            raw_open = finite_positive(opens[index])
            raw_close = finite_positive(closes[index])
            adjusted_close = finite_positive(adjclose[index])
        except (IndexError, TypeError):
            continue
        if raw_open is None or raw_close is None or adjusted_close is None:
            continue
        factor = adjusted_close / raw_close
        rows.append(
            {
                "date": dt.datetime.fromtimestamp(float(timestamp), exchange_tz).date().isoformat(),
                "open": round(raw_open * factor, 8),
                "close": round(adjusted_close, 8),
            }
        )
    return rows[-limit:]


def finite_positive(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def settle_contract(
    contract: dict[str, Any],
    today: dt.date,
    price_loader: Callable[[str, str], tuple[list[dict[str, Any]], str, bool]] = market_rows,
) -> dict[str, Any]:
    if contract.get("status") == "SETTLED":
        return contract
    exit_date = dt.date.fromisoformat(str(contract["forecast_end_trade_date"]))
    # A close observed on the exit date may still be an intraday partial bar.
    if today <= exit_date:
        return contract
    rows, source, adjusted = price_loader(str(contract["market"]), str(contract["code"]))
    by_date = {str(row.get("date")): row for row in rows if isinstance(row, dict)}
    entry_row = by_date.get(str(contract["entry_trade_date"]))
    exit_row = by_date.get(str(contract["forecast_end_trade_date"]))
    entry_price = finite_positive((entry_row or {}).get("open"))
    exit_price = finite_positive((exit_row or {}).get("close"))
    if entry_price is None or exit_price is None:
        result = dict(contract)
        result["settlement_note"] = "WAITING_FOR_COMPLETE_DAILY_BARS"
        result["last_settlement_attempt_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        return result
    published_entry_price = round(entry_price, PUBLISHED_PRICE_DECIMALS)
    published_exit_price = round(exit_price, PUBLISHED_PRICE_DECIMALS)
    if published_entry_price <= 0 or published_exit_price <= 0:
        result = dict(contract)
        result["settlement_note"] = "PRICE_BELOW_PUBLISHED_PRECISION"
        result["last_settlement_attempt_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        return result
    cost = float(contract["transaction_cost"])
    published_gross = round(
        published_exit_price / published_entry_price - 1,
        PUBLISHED_RETURN_DECIMALS,
    )
    published_net = round(published_gross - cost, PUBLISHED_RETURN_DECIMALS)
    entry_at = market_calendar.session_open_at(
        str(contract["market"]),
        str(contract["entry_trade_date"]),
    )
    exit_at = market_calendar.session_close_at(
        str(contract["market"]),
        str(contract["forecast_end_trade_date"]),
    )
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    result = dict(contract)
    result.update(
        {
            "status": "SETTLED",
            "entry_session_open_at": entry_at,
            "entry_at": entry_at,
            "entry_price": published_entry_price,
            "entry_source": source,
            "forecast_end_session_close_at": exit_at,
            "exit_at": exit_at,
            "exit_price": published_exit_price,
            "exit_source": source,
            "gross_total_return": published_gross,
            "net_total_return": published_net,
            "positive_label": published_net > 0,
            "corporate_action_adjusted": bool(adjusted),
            "settled_at": now,
        }
    )
    result.pop("settlement_note", None)
    result.pop("last_settlement_attempt_at", None)
    return result


def _settle_contracts(
    contracts: dict[str, dict[str, Any]],
    outcomes_dir: pathlib.Path,
    today: dt.date,
) -> dict[str, int]:
    counters = {"discovered": len(contracts), "created": 0, "pending": 0, "settled": 0, "unchanged": 0}
    outcomes_dir.mkdir(parents=True, exist_ok=True)
    for prediction_id, discovered in contracts.items():
        path = outcomes_dir / f"{prediction_id}.json"
        existing = read_json(path)
        contract = discovered
        if existing:
            if discovered.get("track") == SHADOW_TRACK:
                newest = _newest_shadow_retry_contract(existing, discovered)
                if newest is None:
                    raise RuntimeError(f"outcome identity conflict: {prediction_id}")
                existing_status = str(existing.get("status") or "").upper()
                try:
                    entry_date = dt.date.fromisoformat(str(existing.get("entry_trade_date") or ""))
                except ValueError:
                    raise RuntimeError(f"outcome identity conflict: {prediction_id}") from None
                if existing_status == "SETTLED":
                    # A settled sample is immutable even if a later archive scan
                    # discovers another same-slot retry.
                    contract = existing
                elif existing_status != "PENDING":
                    raise RuntimeError(f"outcome identity conflict: {prediction_id}")
                elif newest is discovered and today < entry_date:
                    contract = discovered
                else:
                    # Once entry day begins, preserve the first frozen PENDING
                    # identity and settle that exact sample.
                    contract = existing
            else:
                if not _same_contract_identity(existing, discovered):
                    raise RuntimeError(f"outcome identity conflict: {prediction_id}")
                contract = existing
        result = settle_contract(contract, today)
        if existing == result:
            counters["unchanged"] += 1
        else:
            write_json_atomic(path, result)
            if existing is None:
                counters["created"] += 1
        counters["settled" if result.get("status") == "SETTLED" else "pending"] += 1
    return counters


def run(
    picks_dir: pathlib.Path = PICKS,
    outcomes_dir: pathlib.Path = OUTCOMES,
    today: dt.date | None = None,
    *,
    executable_outcomes_dir: pathlib.Path | None = None,
) -> dict[str, int]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    shadow = _settle_contracts(discover_contracts(picks_dir), outcomes_dir, today)
    executable_dir = executable_outcomes_dir or outcomes_dir / "executable"
    executable = _settle_contracts(discover_executable_contracts(picks_dir), executable_dir, today)
    observation_dir = outcomes_dir / "observations"
    observation = {"eligible": 0, "created": 0, "changed": 0, "unchanged": 0}
    for path in sorted(picks_dir.glob("*.json")):
        snapshot = read_json(path)
        if not snapshot:
            continue
        try:
            recorded = model_observation_ledger.record_observation_revision(
                snapshot,
                path.name,
                observation_dir,
            )
        except model_observation_ledger.ObservationContractError:
            continue
        observation["eligible"] += 1
        if recorded["created"]:
            observation["created"] += 1
        if recorded["changed"]:
            observation["changed"] += 1
        else:
            observation["unchanged"] += 1
    counters = {key: shadow[key] + executable[key] for key in shadow}
    counters.update({f"shadow_{key}": value for key, value in shadow.items()})
    counters.update({f"executable_{key}": value for key, value in executable.items()})
    counters.update({f"observation_{key}": value for key, value in observation.items()})
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description="Create/update isolated selector outcome ledgers")
    parser.add_argument("--picks-dir", type=pathlib.Path, default=PICKS)
    parser.add_argument("--outcomes-dir", type=pathlib.Path, default=OUTCOMES)
    parser.add_argument("--executable-outcomes-dir", type=pathlib.Path)
    parser.add_argument("--today", type=dt.date.fromisoformat)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.picks_dir,
                args.outcomes_dir,
                args.today,
                executable_outcomes_dir=args.executable_outcomes_dir,
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

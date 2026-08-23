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
CN_TZ = ZoneInfo("Asia/Shanghai")
DAILY_SCHEDULED_LEDGER_SLOT = (22, 47)
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
    """Keep all snapshots, but sample scheduled research once per decision day.

    Health fallbacks inherit the primary checkpoint in ``scheduled_slot``, so a
    successful 23:17 recovery remains eligible for the 22:47 daily sample.
    Manual workflow runs are operational checks, not independent research
    samples. Legacy snapshots without automation metadata keep compatibility.
    """
    automation = snapshot.get("automation")
    automation = automation if isinstance(automation, dict) else {}
    trigger = str(automation.get("trigger") or "")
    if not trigger:
        return True
    if trigger != "schedule":
        return False
    try:
        scheduled = dt.datetime.fromisoformat(str(automation.get("scheduled_slot") or ""))
    except ValueError:
        return False
    if scheduled.tzinfo is None or scheduled.utcoffset() is None:
        return False
    local = scheduled.astimezone(CN_TZ)
    return (local.hour, local.minute) == DAILY_SCHEDULED_LEDGER_SLOT


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
    candidate = decision.get("research_priority")
    if not isinstance(candidate, dict) or candidate.get("status") != "RESEARCH_ONLY":
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
        "transaction_cost": COST_ASSUMPTIONS[market],
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
            if existing and any(existing.get(key) != contract.get(key) for key in CONTRACT_IDENTITY_KEYS):
                raise RuntimeError(f"outcome identity conflict: {prediction_id}")
            contracts.setdefault(prediction_id, contract)
    return contracts


def discover_contracts(picks_dir: pathlib.Path = PICKS) -> dict[str, dict[str, Any]]:
    """Discover legacy-compatible shadow contracts."""

    return _discover_contracts(picks_dir, candidate_contract)


def discover_executable_contracts(picks_dir: pathlib.Path = PICKS) -> dict[str, dict[str, Any]]:
    return _discover_contracts(picks_dir, executable_candidate_contract)


def market_rows(market: str, code: str) -> tuple[list[dict[str, Any]], str, bool]:
    if market == "a_share":
        rows = server.eastmoney_stock_kline(str(code), 180) or server.tencent_stock_kline(str(code), 180)
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
        contract = existing or discovered
        if existing and any(existing.get(key) != discovered.get(key) for key in CONTRACT_IDENTITY_KEYS):
            raise RuntimeError(f"outcome identity conflict: {prediction_id}")
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
    counters = {key: shadow[key] + executable[key] for key in shadow}
    counters.update({f"shadow_{key}": value for key, value in shadow.items()})
    counters.update({f"executable_{key}": value for key, value in executable.items()})
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

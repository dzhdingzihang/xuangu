#!/usr/bin/env python3
"""Create and settle an honest shadow ledger for ten-session research picks.

The ledger is deliberately separate from executable-model performance.  A
RULE_PRIORITY candidate is useful research evidence, but it is not a calibrated
buy recommendation and must never inflate the production win rate.
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
LEDGER_SCHEMA = "shadow-outcome-v1"
TRACK = "SHADOW_RESEARCH"
COST_ASSUMPTIONS = {"a_share": 0.0015, "hk": 0.0030, "us": 0.0015}
CURRENCIES = {"a_share": "CNY", "hk": "HKD", "us": "USD"}
VALID_ID = re.compile(r"^pred_[a-f0-9]{16,64}$")
CN_TZ = ZoneInfo("Asia/Shanghai")
DAILY_SCHEDULED_LEDGER_SLOT = (22, 47)


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
    )
    if not all(candidate.get(key) for key in required):
        return None
    prediction_id = str(candidate["prediction_id"])
    if not VALID_ID.fullmatch(prediction_id):
        return None
    market = str(candidate["market"])
    if market not in COST_ASSUMPTIONS:
        return None
    entry_date = dt.date.fromisoformat(str(candidate["entry_trade_date"]))
    exit_date = dt.date.fromisoformat(str(candidate["forecast_end_trade_date"]))
    expected_exit = market_calendar.nth_session(market, entry_date, 10, include_current=True)
    if exit_date != expected_exit or exit_date <= entry_date:
        return None
    return {
        "schema_version": LEDGER_SCHEMA,
        "track": TRACK,
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
        "entry_trade_date": entry_date.isoformat(),
        "forecast_end_trade_date": exit_date.isoformat(),
        "horizon_trade_sessions": 10,
        "entry_policy": "next_session_open_v1",
        "exit_policy": "tenth_session_close_v1",
        "calendar_id": candidate["calendar_id"],
        "calendar_version": candidate.get("calendar_version") or "exchange-calendars-4.13.2",
        "currency": CURRENCIES[market],
        "fx_rate_source": "not_required_same_currency_return",
        "transaction_cost": COST_ASSUMPTIONS[market],
        "corporate_action_adjusted": False,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def discover_contracts(picks_dir: pathlib.Path = PICKS) -> dict[str, dict[str, Any]]:
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
        contract = candidate_contract(snapshot, path.name)
        if contract:
            contracts.setdefault(str(contract["prediction_id"]), contract)
    return contracts


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
    cost = float(contract["transaction_cost"])
    gross = exit_price / entry_price - 1
    net = gross - cost
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    result = dict(contract)
    result.update(
        {
            "status": "SETTLED",
            "entry_at": f"{contract['entry_trade_date']}T00:00:00Z",
            "entry_price": round(entry_price, 6),
            "entry_source": source,
            "exit_at": f"{contract['forecast_end_trade_date']}T23:59:59Z",
            "exit_price": round(exit_price, 6),
            "exit_source": source,
            "gross_total_return": round(gross, 8),
            "net_total_return": round(net, 8),
            "positive_label": net > 0,
            "corporate_action_adjusted": bool(adjusted),
            "settled_at": now,
        }
    )
    result.pop("settlement_note", None)
    result.pop("last_settlement_attempt_at", None)
    return result


def run(picks_dir: pathlib.Path = PICKS, outcomes_dir: pathlib.Path = OUTCOMES, today: dt.date | None = None) -> dict[str, int]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    contracts = discover_contracts(picks_dir)
    counters = {"discovered": len(contracts), "created": 0, "pending": 0, "settled": 0, "unchanged": 0}
    outcomes_dir.mkdir(parents=True, exist_ok=True)
    for prediction_id, discovered in contracts.items():
        path = outcomes_dir / f"{prediction_id}.json"
        existing = read_json(path)
        contract = existing or discovered
        if existing:
            immutable_keys = ("prediction_id", "model_id", "label_version", "market", "code", "entry_trade_date", "forecast_end_trade_date")
            if any(existing.get(key) != discovered.get(key) for key in immutable_keys):
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Create/update the selector shadow outcome ledger")
    parser.add_argument("--picks-dir", type=pathlib.Path, default=PICKS)
    parser.add_argument("--outcomes-dir", type=pathlib.Path, default=OUTCOMES)
    parser.add_argument("--today", type=dt.date.fromisoformat)
    args = parser.parse_args()
    print(json.dumps(run(args.picks_dir, args.outcomes_dir, args.today), ensure_ascii=False))


if __name__ == "__main__":
    main()

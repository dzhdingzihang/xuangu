#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import itertools
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


START = dt.date(2026, 5, 1)
END = dt.date(2026, 5, 30)


def trade_days() -> list[dt.date]:
    days = []
    current = START
    while current <= END:
        if server.is_trade_weekday(current):
            days.append(current)
        current += dt.timedelta(days=1)
    return days


def kline_for(candidate: dict, market_key: str) -> list[dict]:
    symbol = candidate["symbol"]
    return server.stock_kline(symbol, 180) if market_key == "a_share" else server.yahoo_chart_kline(symbol, 180)


def slice_until(rows: list[dict], signal_day: dt.date) -> list[dict]:
    return [row for row in rows if row.get("date", "") <= signal_day.isoformat()]


def two_day_return(rows: list[dict], signal_day: dt.date) -> float | None:
    idx = next((i for i, row in enumerate(rows) if row.get("date") == signal_day.isoformat()), None)
    if idx is None or idx + 2 >= len(rows):
        return None
    entry = rows[idx]["close"]
    exit_ = rows[idx + 2]["close"]
    return server.pct_change(exit_, entry)


def score_row(candidate: dict, market_key: str, rows: list[dict], weights: dict) -> dict | None:
    signal_rows = slice_until(rows, weights["signal_day"])
    if len(signal_rows) < 32:
        return None
    lens_score, lens_reasons, lens_risks = server.serenity_lens_score(candidate)
    chan = server.chan_signal(signal_rows)
    quote = server.quote_from_kline(signal_rows)
    metrics = chan.get("metrics") or {}
    setup_flags = metrics.get("setup_flags") or []
    hard = 0
    risks = list(lens_risks) + chan["warnings"]
    if not setup_flags:
        hard += 1
    if metrics.get("distance_ma10_pct", 0) > weights["ma10_limit"]:
        hard += 1
        risks.append("偏离 MA10 过大")
    if quote["pct_5d"] > weights["pct5_limit"]:
        hard += 1
        risks.append("5日涨幅过热")
    if quote["change_pct"] > weights["change_limit"]:
        hard += 1
        risks.append("信号日涨幅过大")
    score = lens_score * weights["lens"] + chan["score"] * weights["chan"] - hard * weights["hard_penalty"]
    confidence = server.serenity_confidence(score, len(risks), market_key)
    realized = two_day_return(rows, weights["signal_day"])
    return {
        "symbol": candidate["symbol"],
        "name": candidate["name"],
        "score": round(score, 2),
        "lens_score": lens_score,
        "chan_score": chan["score"],
        "confidence": confidence,
        "hard": hard,
        "risks": len(risks),
        "change_pct": quote["change_pct"],
        "pct_5d": quote["pct_5d"],
        "ret_2d": realized,
        "would_buy": confidence >= weights["threshold"] and hard < 2 and len(risks) < 4,
        "reasons": lens_reasons[:3] + chan["signals"][:3],
    }


def run_market(market_key: str, weights: dict, cache: dict[str, list[dict]]) -> list[dict]:
    candidates = server.SERENITY_UNIVERSES[market_key]
    rows = []
    for target in trade_days():
        signal_day = server.previous_weekday(target)
        weights = {**weights, "signal_day": signal_day}
        scored = []
        for candidate in candidates:
            item = score_row(candidate, market_key, cache[candidate["symbol"]], weights)
            if item and item["ret_2d"] is not None:
                scored.append(item)
        if not scored:
            continue
        scored.sort(key=lambda x: (x["hard"], -x["confidence"], -x["score"]))
        top = scored[0]
        rows.append({"market": market_key, "target": target.isoformat(), "signal": signal_day.isoformat(), **top})
    return rows


def summarize(rows: list[dict]) -> dict:
    buys = [row for row in rows if row["would_buy"]]
    candidate_returns = [row["ret_2d"] for row in rows if row["ret_2d"] is not None]
    trade_returns = [row["ret_2d"] for row in buys if row["ret_2d"] is not None]
    return {
        "signals": len(rows),
        "buys": len(buys),
        "candidate_hit_rate": round(sum(1 for r in candidate_returns if r > 0) / len(candidate_returns) * 100, 1) if candidate_returns else 0,
        "candidate_avg_ret": round(statistics.mean(candidate_returns), 2) if candidate_returns else 0,
        "trade_hit_rate": round(sum(1 for r in trade_returns if r > 0) / len(trade_returns) * 100, 1) if trade_returns else 0,
        "trade_avg_ret": round(statistics.mean(trade_returns), 2) if trade_returns else 0,
        "trade_median_ret": round(statistics.median(trade_returns), 2) if trade_returns else 0,
        "trade_max_draw": round(min(trade_returns), 2) if trade_returns else 0,
        "trade_best": round(max(trade_returns), 2) if trade_returns else 0,
    }


def optimize(market_key: str) -> tuple[dict, list[dict], dict]:
    candidates = server.SERENITY_UNIVERSES[market_key]
    cache = {item["symbol"]: kline_for(item, market_key) for item in candidates}
    pct5_mid = 22.0 if market_key == "us" else 16.0
    change_mid = 14.0 if market_key == "us" else 8.5
    variants = [
        {"lens": 1.0, "chan": 0.86, "hard_penalty": 9, "threshold": 64, "ma10_limit": 10.0, "pct5_limit": pct5_mid, "change_limit": change_mid},
        {"lens": 0.9, "chan": 1.1, "hard_penalty": 11, "threshold": 66, "ma10_limit": 8.0, "pct5_limit": pct5_mid - 4, "change_limit": change_mid - 2},
        {"lens": 1.25, "chan": 0.75, "hard_penalty": 8, "threshold": 62, "ma10_limit": 12.0, "pct5_limit": pct5_mid + 4, "change_limit": change_mid + 2},
        {"lens": 1.1, "chan": 1.0, "hard_penalty": 13, "threshold": 65, "ma10_limit": 8.0, "pct5_limit": pct5_mid - 2, "change_limit": change_mid - 1.5},
    ]
    best = None
    best_rows = []
    best_summary = {}
    for weights in variants:
        rows = run_market(market_key, weights, cache)
        summary = summarize(rows)
        buys = summary["buys"]
        if buys == 0:
            continue
        if summary["trade_avg_ret"] <= 0 or summary["trade_hit_rate"] < 50 or summary["trade_max_draw"] < -5:
            continue
        objective = (
            summary["trade_avg_ret"] * 2
            + summary["trade_hit_rate"] * 0.04
            + min(buys, 8) * 0.08
            + summary["trade_max_draw"] * 0.8
        )
        if best is None or objective > best[0]:
            best = (objective, weights)
            best_rows = rows
            best_summary = summary
    if best is None:
        fallback = {
            "lens": 1.0,
            "chan": 0.86,
            "hard_penalty": 9,
            "threshold": 64,
            "ma10_limit": 10.0,
            "pct5_limit": 22.0 if market_key == "us" else 16.0,
            "change_limit": 14.0 if market_key == "us" else 8.5,
        }
        rows = run_market(market_key, fallback, cache)
        return fallback, rows, summarize(rows)
    return best[1], best_rows, best_summary


def main() -> None:
    result = {}
    for market in ["a_share", "hk", "us"]:
        weights, rows, summary = optimize(market)
        result[market] = {"weights": weights, "summary": summary, "rows": rows}
        print("\n", market, json.dumps(summary, ensure_ascii=False), json.dumps(weights, ensure_ascii=False))
        for row in rows:
            mark = "BUY" if row["would_buy"] else "SKIP"
            print(row["target"], mark, row["symbol"], row["name"], row["confidence"], f"{row['ret_2d']:+.2f}%")
    out = ROOT / "data" / "backtests" / "may_2026_serenity.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwritten", out)


if __name__ == "__main__":
    main()

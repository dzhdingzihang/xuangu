#!/usr/bin/env python3
"""
Local Chan-theory A-share selector.

It intentionally prefers "no trade" over weak signals. The model is a
decision-support tool, not a guarantee of profit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.server
import json
import math
import os
import pathlib
import re
import socketserver
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import requests


ROOT = pathlib.Path(__file__).resolve().parent
STATIC = ROOT / "static"
CACHE = ROOT / "data"
PICKS = CACHE / "picks"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CN_TZ = ZoneInfo("Asia/Shanghai")
MODEL_VERSION = "chan-selector-2026-06-03.2"

for path in (CACHE, PICKS):
    path.mkdir(parents=True, exist_ok=True)


CHAN_RULES = {
    "source": "缠中说禅 PDF",
    "principles": [
        "不预测空间，只在买点出现时介入，卖点或风控出现时退出。",
        "第二类买点适合用大级别确认、次级别精确买入。",
        "第三类买点是离开中枢后的回试不破，短线更重视效率。",
        "没有趋势，没有背驰；背驰只作为转折确认，不单独追涨。",
        "风险不可消灭，只能通过系统、仓位和退出条件约束。",
    ],
    "quant_mapping": [
        "女上位: MA5 > MA10，且最好 MA10 > MA20。",
        "二买: 多头均线后第一次回踩 MA5/MA10 不破并重新收回，优先选择偏离 MA10 不大的标的。",
        "三买: 突破近 20 日箱体或中枢后，回踩不跌回箱体上沿；只突破不回踩不追。",
        "背驰: 价格创新低但 MACD 柱改善，作为二买/反转加分。",
        "卖点/风控: 涨停后大幅高开不追；跌破 MA10 或买入后两日未兑现强度时退出。",
    ],
}


THEME_KEYWORDS = [
    "先进封装",
    "存储芯片",
    "HBM",
    "CPO",
    "光模块",
    "800G",
    "1.6T",
    "AI算力",
    "算力",
    "英伟达",
    "服务器电源",
    "数据中心",
    "液冷",
    "PCB",
    "半导体",
    "机器人",
    "人形机器人",
    "低空经济",
    "商业航天",
]


def now_cn() -> dt.datetime:
    return dt.datetime.now(CN_TZ)


def is_trade_weekday(day: dt.date) -> bool:
    return day.weekday() < 5


def previous_weekday(day: dt.date) -> dt.date:
    day -= dt.timedelta(days=1)
    while not is_trade_weekday(day):
        day -= dt.timedelta(days=1)
    return day


def next_weekday(day: dt.date) -> dt.date:
    day += dt.timedelta(days=1)
    while not is_trade_weekday(day):
        day += dt.timedelta(days=1)
    return day


def default_signal_date(today: dt.date | None = None) -> dt.date:
    current = now_cn()
    today = today or current.date()
    if not is_trade_weekday(today):
        return previous_weekday(today)
    if current.time() < dt.time(15, 30):
        return previous_weekday(today)
    return today


def parse_cache_name(path: pathlib.Path) -> tuple[str, str] | None:
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json", path.name)
    if not match:
        return None
    return match.group(1), match.group(2)


def summarize_pick(pick: dict) -> dict:
    decision = pick.get("decision") or {}
    primary = decision.get("primary") or decision.get("blocked_candidate")
    summary = {
        "target_date": pick.get("target_date"),
        "signal_date": pick.get("signal_date"),
        "generated_at": pick.get("generated_at"),
        "action": decision.get("action"),
        "title": decision.get("title"),
        "message": decision.get("message"),
        "has_primary": bool(decision.get("primary")),
        "model_version": pick.get("model_version"),
    }
    if primary:
        summary.update(
            {
                "code": primary.get("code"),
                "name": primary.get("name"),
                "confidence": primary.get("confidence"),
                "estimated_2d_range": (primary.get("estimated_2d_range") or {}).get("text"),
                "score": primary.get("score"),
                "reason_tags": primary.get("reason_tags"),
            }
        )
    return summary


def history_payload(limit: int = 30) -> dict:
    rows = []
    for path in PICKS.glob("*.json"):
        parsed = parse_cache_name(path)
        if not parsed:
            continue
        try:
            pick = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        summary = summarize_pick(pick)
        summary["cache_key"] = path.name
        rows.append(summary)
    rows.sort(key=lambda item: (item.get("target_date") or "", item.get("generated_at") or ""), reverse=True)

    latest = None
    latest_path = PICKS / "latest.json"
    if latest_path.exists():
        try:
            latest_pick = json.loads(latest_path.read_text(encoding="utf-8"))
            latest = summarize_pick(latest_pick)
        except Exception:
            latest = None
    return {
        "ok": True,
        "time": now_cn().isoformat(timespec="seconds"),
        "latest": latest,
        "history": rows[:limit],
    }


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, "", "-"):
            return default
        return float(value)
    except Exception:
        return default


def market_prefix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith(("8", "4")):
        return "bj"
    return "sz"


def eastmoney_secid(code: str) -> str:
    return ("1." if code.startswith(("6", "9")) else "0.") + code


def http_get_json(url: str, params: dict | None = None, timeout: int = 14) -> dict:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def load_ths_hot(date_text: str) -> list[dict]:
    url = (
        "http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{date_text}/orderby/date/orderway/desc/charset/GBK/"
    )
    response = requests.get(url, headers={"User-Agent": UA}, timeout=12)
    response.raise_for_status()
    data = response.json()
    if data.get("errocode", 0) != 0:
        return []
    return data.get("data") or []


def find_hot_pool(signal_day: dt.date) -> tuple[str, list[dict]]:
    day = signal_day
    for _ in range(8):
        if is_trade_weekday(day):
            date_text = day.isoformat()
            try:
                rows = load_ths_hot(date_text)
                if rows:
                    return date_text, rows
            except Exception:
                pass
        day = previous_weekday(day)
    return signal_day.isoformat(), []


def load_broad_market_pool(limit: int = 260) -> list[dict]:
    rows: list[dict] = []
    page_size = 80
    pages = max(1, min(5, math.ceil(limit / page_size)))
    fields = "f2,f3,f6,f8,f12,f14,f20,f21,f23"
    for page in range(1, pages + 1):
        try:
            data = http_get_json(
                "https://push2.eastmoney.com/api/qt/clist/get",
                {
                    "pn": str(page),
                    "pz": str(page_size),
                    "po": "1",
                    "np": "1",
                    "fltt": "2",
                    "invt": "2",
                    "fid": "f6",
                    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                    "fields": fields,
                },
                timeout=12,
            )
        except Exception:
            continue
        for item in (data.get("data") or {}).get("diff", []) or []:
            code = str(item.get("f12") or "")
            name = str(item.get("f14") or "")
            if not code or "ST" in name.upper() or code.startswith(("8", "4", "9")):
                continue
            change_pct = safe_float(item.get("f3"))
            amount_yi = safe_float(item.get("f6")) / 100000000
            turnover_pct = safe_float(item.get("f8"))
            price = safe_float(item.get("f2"))
            pb = safe_float(item.get("f23"))
            if price <= 0 or amount_yi < 5:
                continue
            if change_pct < 0.8 or change_pct >= 8.8:
                continue
            if turnover_pct < 1.2 or turnover_pct > 18:
                continue
            if pb > 18:
                continue
            rows.append(
                {
                    "code": code,
                    "reason": "全市场稳健候选",
                    "source": "eastmoney_broad",
                    "broad_amount_yi": round(amount_yi, 2),
                    "broad_change_pct": change_pct,
                    "broad_turnover_pct": turnover_pct,
                }
            )
            if len(rows) >= limit:
                return rows
        time.sleep(0.1)
    return rows


def merge_candidate_pools(event_rows: list[dict], broad_rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in broad_rows + event_rows:
        code = row.get("code")
        if not code:
            continue
        if code not in merged:
            merged[code] = dict(row)
            continue
        previous_reason = merged[code].get("reason") or ""
        current_reason = row.get("reason") or ""
        if current_reason and current_reason not in previous_reason:
            merged[code]["reason"] = "、".join([part for part in [previous_reason, current_reason] if part])
        merged[code].update({key: value for key, value in row.items() if value not in ("", None)})
    return list(merged.values())


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for start in range(0, len(codes), 70):
        batch = codes[start : start + 70]
        prefixed = [market_prefix(code) + code for code in batch]
        url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=16).read().decode("gbk", "ignore")
        for line in raw.strip().split(";"):
            if not line.strip() or "=\"" not in line:
                continue
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = key[2:]
            result[code] = {
                "code": code,
                "name": vals[1],
                "price": safe_float(vals[3]),
                "last_close": safe_float(vals[4]),
                "open": safe_float(vals[5]),
                "change_pct": safe_float(vals[32]),
                "high": safe_float(vals[33]),
                "low": safe_float(vals[34]),
                "amount_wan": safe_float(vals[37]),
                "turnover_pct": safe_float(vals[38]),
                "pe_ttm": safe_float(vals[39]),
                "amplitude_pct": safe_float(vals[43]),
                "mcap_yi": safe_float(vals[44]),
                "float_mcap_yi": safe_float(vals[45]),
                "pb": safe_float(vals[46]),
                "limit_up": safe_float(vals[47]),
                "limit_down": safe_float(vals[48]),
                "vol_ratio": safe_float(vals[49]),
                "pe_static": safe_float(vals[52]),
            }
        time.sleep(0.12)
    return result


def index_quotes() -> dict:
    mapping = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
        "sh000300": "沪深300",
    }
    url = "https://qt.gtimg.cn/q=" + ",".join(mapping)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=12).read().decode("gbk", "ignore")
    except Exception:
        return {"items": [], "risk": "unknown", "risk_note": "指数接口暂不可用"}

    items = []
    for line in raw.strip().split(";"):
        if not line.strip() or "=\"" not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 33:
            continue
        items.append({"code": key, "name": vals[1], "change_pct": safe_float(vals[32])})
    negatives = sum(1 for item in items if item["change_pct"] < -0.7)
    gem = next((item for item in items if item["code"] == "sz399006"), None)
    if negatives >= 3 or (gem and gem["change_pct"] < -1.2):
        risk = "high"
        note = "主要指数偏弱，早盘不宜硬追强势股。"
    elif negatives >= 2:
        risk = "medium"
        note = "指数分歧，降低仓位或等待确认。"
    else:
        risk = "normal"
        note = "指数环境未触发系统性风险拦截。"
    return {"items": items, "risk": risk, "risk_note": note}


def daily_dragon_tiger(date_text: str) -> dict[str, dict]:
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
        "columns": "ALL",
        "filter": f"(TRADE_DATE>='{date_text}')(TRADE_DATE<='{date_text}')",
        "pageNumber": "1",
        "pageSize": "500",
        "sortColumns": "BILLBOARD_NET_AMT",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        data = http_get_json(url, params=params, timeout=18)
        rows = ((data.get("result") or {}).get("data")) or []
    except Exception:
        rows = []
    by_code: dict[str, dict] = {}
    for row in rows:
        code = row.get("SECURITY_CODE") or ""
        if not code:
            continue
        item = by_code.setdefault(
            code,
            {
                "net_buy_wan": 0.0,
                "buy_wan": 0.0,
                "sell_wan": 0.0,
                "reason": row.get("EXPLANATION", ""),
                "records": 0,
            },
        )
        item["records"] += 1
        item["net_buy_wan"] += safe_float(row.get("BILLBOARD_NET_AMT")) / 10000
        item["buy_wan"] += safe_float(row.get("BILLBOARD_BUY_AMT")) / 10000
        item["sell_wan"] += safe_float(row.get("BILLBOARD_SELL_AMT")) / 10000
    return by_code


def industry_heat() -> dict:
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    try:
        data = http_get_json(url, params=params, timeout=14)
        rows = (data.get("data") or {}).get("diff") or []
    except Exception:
        rows = []
    top = []
    for idx, item in enumerate(rows[:12], 1):
        top.append(
            {
                "rank": idx,
                "name": item.get("f14", ""),
                "change_pct": safe_float(item.get("f3")),
                "leader": item.get("f140", ""),
                "leader_change": safe_float(item.get("f136")),
                "up_count": item.get("f104", 0),
                "down_count": item.get("f105", 0),
            }
        )
    return {"top": top, "total": len(rows)}


def baidu_stock_kline(code: str, limit: int = 70) -> list[dict]:
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {
        "all": "1",
        "isIndex": "false",
        "isBk": "false",
        "isBlock": "false",
        "isFutures": "false",
        "isStock": "true",
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": code,
        "ktype": "1",
    }
    headers = {
        "User-Agent": UA,
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=12)
        response.raise_for_status()
        data = response.json()
        market = (((data.get("Result") or {}).get("newMarketData") or {}).get("marketData")) or ""
    except Exception:
        return []
    rows = []
    for line in market.split(";")[-limit:]:
        parts = line.split(",")
        if len(parts) < 18:
            continue
        rows.append(
            {
                "date": parts[1],
                "open": safe_float(parts[2]),
                "close": safe_float(parts[3]),
                "volume": safe_float(parts[4]),
                "high": safe_float(parts[5]),
                "low": safe_float(parts[6]),
                "amount": safe_float(parts[7]),
                "amplitude": 0.0,
                "change_pct": safe_float(str(parts[9]).replace("%", "")),
                "turnover": safe_float(parts[10]),
                "ma5": safe_float(parts[12]),
                "ma10": safe_float(parts[14]),
                "ma20": safe_float(parts[16]),
            }
        )
    return rows


def eastmoney_stock_kline(code: str, limit: int = 70) -> list[dict]:
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": eastmoney_secid(code),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "end": "20500101",
        "lmt": str(limit),
    }
    try:
        data = http_get_json(url, params=params, timeout=5)
        klines = ((data.get("data") or {}).get("klines")) or []
    except Exception:
        return []
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": safe_float(parts[1]),
                "close": safe_float(parts[2]),
                "high": safe_float(parts[3]),
                "low": safe_float(parts[4]),
                "volume": safe_float(parts[5]),
                "amount": safe_float(parts[6]),
                "amplitude": safe_float(parts[7]),
                "change_pct": safe_float(parts[8]),
                "turnover": safe_float(parts[10]),
            }
        )
    return rows


def stock_kline(code: str, limit: int = 70) -> list[dict]:
    rows = baidu_stock_kline(code, limit)
    if rows:
        return rows
    return eastmoney_stock_kline(code, limit)


def ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def macd_hist(closes: list[float]) -> list[float]:
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    return [(d - signal) * 2 for d, signal in zip(dif, dea)]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct_change(current: float, base: float) -> float:
    if not base:
        return 0.0
    return (current / base - 1) * 100


def chan_signal(kline: list[dict]) -> dict:
    if len(kline) < 32:
        return {
            "score": 0,
            "signals": [],
            "warnings": ["K线样本不足，缠论结构信号降权"],
            "metrics": {},
        }

    closes = [x["close"] for x in kline]
    lows = [x["low"] for x in kline]
    highs = [x["high"] for x in kline]
    vols = [x["volume"] for x in kline]
    last = kline[-1]
    ma5 = mean(closes[-5:])
    ma10 = mean(closes[-10:])
    ma20 = mean(closes[-20:])
    ma30 = mean(closes[-30:])
    hist = macd_hist(closes)
    distance_ma5 = pct_change(last["close"], ma5)
    distance_ma10 = pct_change(last["close"], ma10)
    distance_ma20 = pct_change(last["close"], ma20)
    pct_3d = pct_change(last["close"], closes[-4]) if len(closes) >= 4 else 0.0
    pct_5d = pct_change(last["close"], closes[-6]) if len(closes) >= 6 else 0.0
    pct_10d = pct_change(last["close"], closes[-11]) if len(closes) >= 11 else 0.0
    day_range = max(last["high"] - last["low"], 0.001)
    close_position = (last["close"] - last["low"]) / day_range
    upper_shadow_pct = pct_change(last["high"], last["close"])
    last_change = last.get("change_pct", 0.0)

    score = 0.0
    signals: list[str] = []
    warnings: list[str] = []
    setup_flags: list[str] = []

    if ma5 > ma10:
        score += 6
        signals.append("女上位: MA5 在 MA10 之上")
    if last["close"] > ma5 > ma10 > ma20:
        score += 8
        signals.append("多头排列: 收盘价站上 MA5/10/20")
    if last["close"] >= ma10 * 0.985:
        score += 6
        signals.append("持股线: 未有效跌破 MA10")
    else:
        warnings.append("收盘价跌破 MA10，二日持有风险偏高")
        score -= 10

    recent_pullback = min(lows[-6:-1]) <= ma10 * 1.025
    recover_ma5 = last["close"] > ma5 and last["close"] > closes[-2]
    if ma5 > ma10 and recent_pullback and recover_ma5:
        score += 22
        setup_flags.append("second_buy")
        signals.append("二买近似: 多头后回踩 MA5/MA10 并重新收回")

    box_high = max(highs[-25:-5])
    box_low = min(lows[-25:-5])
    recent_low = min(lows[-5:])
    if last["close"] > box_high * 1.01 and recent_low > box_high * 0.985:
        score += 18
        setup_flags.append("third_buy")
        signals.append("三买近似: 突破近 20 日中枢后回试不破")
    elif last["close"] >= max(highs[-21:-1]) * 0.995:
        score += 2
        warnings.append("只接近或突破 20 日高点，未出现明确回踩确认")

    if len(hist) > 28:
        prev_window = list(range(max(0, len(lows) - 28), max(0, len(lows) - 12)))
        recent_window = list(range(max(0, len(lows) - 12), len(lows)))
        if prev_window and recent_window:
            prev_low_i = min(prev_window, key=lambda i: lows[i])
            recent_low_i = min(recent_window, key=lambda i: lows[i])
            if lows[recent_low_i] <= lows[prev_low_i] * 1.01 and hist[recent_low_i] > hist[prev_low_i]:
                score += 9
                signals.append("MACD背驰改善: 低点附近绿柱力度收敛")

    if len(hist) > 8 and last["close"] >= max(highs[-21:-1]) * 0.995:
        if hist[-1] < hist[-2] < hist[-3] and hist[-1] > 0:
            score -= 12
            warnings.append("新高附近 MACD 柱缩短，谨防短线顶背驰")

    if last["volume"] > 0 and mean(vols[-6:-1]) > 0:
        vol_ratio = last["volume"] / mean(vols[-6:-1])
        if 1.05 <= vol_ratio <= 2.6:
            score += min(8, vol_ratio * 3)
            signals.append(f"量能确认: 较 5 日均量 {vol_ratio:.1f} 倍")
        elif vol_ratio > 2.6:
            warnings.append("放量偏猛，次日容易分歧")
            score -= min(18, (vol_ratio - 2.6) * 5)
    else:
        vol_ratio = 0

    if not setup_flags:
        score -= 16
        warnings.append("没有二买/三买确认，容易变成追涨交易")
    if distance_ma10 > 9:
        score -= min(26, (distance_ma10 - 9) * 2.2)
        warnings.append(f"偏离 MA10 {distance_ma10:.1f}%，追高风险上升")
    elif 0 <= distance_ma10 <= 5:
        score += 8
        signals.append("成本位置: 距 MA10 不远，二日风控更可控")
    if pct_5d > 18:
        score -= min(24, (pct_5d - 18) * 1.2)
        warnings.append(f"5 日累计涨幅 {pct_5d:.1f}%，短线兑现压力偏大")
    if last_change >= 9.5:
        score -= 14
        warnings.append("信号日接近涨停，次日追高性价比下降")
    if upper_shadow_pct > 3.5 and close_position < 0.68:
        score -= 10
        warnings.append("上影线较长，资金分歧偏大")

    return {
        "score": round(score, 2),
        "signals": signals[:6],
        "warnings": warnings[:5],
        "metrics": {
            "ma5": round(ma5, 3),
            "ma10": round(ma10, 3),
            "ma20": round(ma20, 3),
            "ma30": round(ma30, 3),
            "box_high": round(box_high, 3),
            "box_low": round(box_low, 3),
            "volume_ratio_5d": round(vol_ratio, 2),
            "distance_ma5_pct": round(distance_ma5, 2),
            "distance_ma10_pct": round(distance_ma10, 2),
            "distance_ma20_pct": round(distance_ma20, 2),
            "pct_3d": round(pct_3d, 2),
            "pct_5d": round(pct_5d, 2),
            "pct_10d": round(pct_10d, 2),
            "close_position": round(close_position, 2),
            "upper_shadow_pct": round(upper_shadow_pct, 2),
            "setup_flags": setup_flags,
            "last_kline_date": last["date"],
        },
    }


def theme_score(reason: str) -> tuple[float, list[str]]:
    hits = [kw for kw in THEME_KEYWORDS if kw in reason]
    return min(22.0, len(hits) * 4.5), hits


def preliminary_score(hot: dict, quote: dict, dragon: dict | None) -> dict:
    reason = hot.get("reason") or ""
    t_score, tags = theme_score(reason)
    amount_yi = quote["amount_wan"] / 10000
    turnover = quote["turnover_pct"]
    change_pct = quote["change_pct"]
    score = 0.0
    if 1.5 <= change_pct <= 7.5:
        score += 14 + change_pct * 1.1
    elif 7.5 < change_pct <= 11:
        score += 18 - (change_pct - 7.5) * 1.4
    elif 11 < change_pct <= 16:
        score += 8 - (change_pct - 11) * 1.8
    elif change_pct > 16:
        score -= min(22, (change_pct - 16) * 2.8)
    else:
        score += max(change_pct, -6) * 1.2
    score += min(max(math.log10(max(amount_yi, 0.2)) * 12, 0), 24)
    score += max(0, 14 - abs(turnover - 9) * 0.9)
    if 0.8 <= quote["vol_ratio"] <= 2.4:
        score += 8 - abs(quote["vol_ratio"] - 1.4) * 2
    elif quote["vol_ratio"] > 2.4:
        score -= min(16, (quote["vol_ratio"] - 2.4) * 5)
    score += t_score

    dtb_net = 0.0
    if dragon:
        dtb_net = dragon.get("net_buy_wan", 0.0)
        if dtb_net > 0:
            score += min(math.log10(dtb_net + 1) * 4.8, 18)
        else:
            score -= 8

    risk_flags = []
    if quote["limit_up"] and abs(quote["price"] - quote["limit_up"]) < 0.02:
        risk_flags.append("信号日涨停，次日追高风险")
        score -= 12
        if abs(quote["open"] - quote["limit_up"]) < 0.02 and abs(quote["low"] - quote["limit_up"]) < 0.02:
            risk_flags.append("一字涨停，次日可买性差")
            score -= 22
    if change_pct >= 18.5:
        risk_flags.append("20cm 大涨后，二日持有回撤风险高")
        score -= 12
    elif change_pct >= 9.5:
        risk_flags.append("10cm 涨停后，隔日接力不确定")
        score -= 8
    if turnover > 24:
        risk_flags.append("换手过高，分歧剧烈")
        score -= 14
    elif turnover > 18:
        risk_flags.append("换手偏高，次日易分歧")
        score -= 7
    if amount_yi < 2:
        risk_flags.append("成交额不足 2 亿")
        score -= 8
    if quote["float_mcap_yi"] > 2500 and t_score < 9:
        risk_flags.append("流通市值偏大，涨幅弹性受限")
        score -= 22
    elif quote["float_mcap_yi"] > 1300 and t_score < 9:
        risk_flags.append("流通市值偏大，涨幅弹性受限")
        score -= 12

    return {
        "pre_score": round(score, 2),
        "theme_tags": tags,
        "theme_score": round(t_score, 2),
        "dragon_net_wan": round(dtb_net, 1),
        "risk_flags": risk_flags,
    }


def candidate_confidence(score: float, risk_count: int, market_risk: str) -> int:
    confidence = 48 + (score - 60) * 0.34
    confidence -= min(risk_count * 4, 18)
    if market_risk == "medium":
        confidence -= 5
    elif market_risk == "high":
        confidence -= 12
    return int(max(38, min(72, round(confidence))))


def estimate_range(confidence: int, technical: float, theme: float, risk_count: int) -> dict:
    if confidence < 62:
        low, high = -4.0, 2.4
    else:
        low = max(-3.2, -1.8 + (confidence - 62) * 0.04 - risk_count * 0.32)
        high = 1.8 + (confidence - 62) * 0.18 + technical * 0.028 + theme * 0.045
        high = min(high, 9.0)
    return {
        "low_pct": round(low, 1),
        "high_pct": round(high, 1),
        "text": f"{low:+.1f}% ~ {high:+.1f}%",
    }


def score_candidates(signal_date: str, hot_rows: list[dict], market: dict) -> dict:
    codes = [row.get("code") for row in hot_rows if row.get("code")]
    quotes = tencent_quote(codes)
    dragon_map = daily_dragon_tiger(signal_date)

    preliminary = []
    for hot in hot_rows:
        code = hot.get("code") or ""
        quote = quotes.get(code)
        if not quote or quote["price"] <= 0:
            continue
        name = quote["name"]
        if "ST" in name.upper() or code.startswith(("8", "4", "9")):
            continue
        pre = preliminary_score(hot, quote, dragon_map.get(code))
        preliminary.append({"hot": hot, "quote": quote, **pre})

    preliminary.sort(key=lambda item: item["pre_score"], reverse=True)
    final = []
    max_kline_checks = int(os.environ.get("CHAN_MAX_KLINE_CHECKS", "60"))
    for item in preliminary[:max_kline_checks]:
        quote = item["quote"]
        code = quote["code"]
        kline = stock_kline(code)
        chan = chan_signal(kline)
        metrics = chan.get("metrics") or {}
        total = item["pre_score"] + chan["score"]
        risk_flags = list(item["risk_flags"]) + chan["warnings"]
        setup_flags = metrics.get("setup_flags") or []
        hard_risks = 0
        if not setup_flags:
            hard_risks += 1
        if metrics.get("distance_ma10_pct", 0) > 10:
            hard_risks += 1
        if quote["change_pct"] >= 9.5:
            hard_risks += 1
        if quote["turnover_pct"] > 24:
            hard_risks += 1
        if quote["vol_ratio"] > 3:
            hard_risks += 1
        if quote["turnover_pct"] > 24 and quote["change_pct"] >= 19:
            risk_flags.append("20cm 高换手，仅适合观察分歧承接")
        if hard_risks:
            total -= hard_risks * 8
        confidence = candidate_confidence(total, len(risk_flags), market.get("risk", "unknown"))
        est = estimate_range(confidence, chan["score"], item["theme_score"], len(risk_flags))
        stop_loss = max(quote["limit_down"], quote["price"] * 0.965)
        take_profit = quote["price"] * (1 + min(est["high_pct"], 10) / 100)
        reasons = []
        if item["theme_tags"]:
            reasons.append("题材命中: " + "、".join(item["theme_tags"][:5]))
        if item["dragon_net_wan"] > 0:
            reasons.append(f"龙虎榜净买入约 {item['dragon_net_wan']:.0f} 万")
        reasons.extend(chan["signals"][:4])
        reasons.append(
            f"流动性: 成交 {quote['amount_wan']/10000:.1f} 亿，换手 {quote['turnover_pct']:.1f}%"
        )
        final.append(
            {
                "code": code,
                "name": quote["name"],
                "price": quote["price"],
                "change_pct": quote["change_pct"],
                "amount_yi": round(quote["amount_wan"] / 10000, 2),
                "turnover_pct": quote["turnover_pct"],
                "vol_ratio": quote["vol_ratio"],
                "float_mcap_yi": quote["float_mcap_yi"],
                "reason_tags": item["hot"].get("reason", ""),
                "theme_tags": item["theme_tags"],
                "score": round(total, 2),
                "pre_score": item["pre_score"],
                "chan_score": chan["score"],
                "setup_flags": setup_flags,
                "hard_risk_count": hard_risks,
                "confidence": confidence,
                "estimated_2d_range": est,
                "stop_loss": round(stop_loss, 2),
                "take_profit_reference": round(take_profit, 2),
                "dragon_net_wan": item["dragon_net_wan"],
                "dragon_reason": (dragon_map.get(code) or {}).get("reason", ""),
                "reasons": reasons[:7],
                "risk_flags": risk_flags[:6],
                "chan": chan,
            }
        )

    final.sort(
        key=lambda item: (
            item.get("hard_risk_count", 0),
            -item["confidence"],
            -item["score"],
        )
    )
    return {
        "candidates": final,
        "raw_pool_size": len(hot_rows),
        "scored_size": len(final),
        "dragon_count": len(dragon_map),
    }


def make_decision(candidates: list[dict], market: dict) -> dict:
    if not candidates:
        return {
            "action": "NO_TRADE",
            "title": "今日不交易",
            "message": "没有足够强的候选池，系统选择空仓。",
            "primary": None,
            "watchlist": [],
        }
    candidates = sorted(candidates, key=lambda item: (item.get("hard_risk_count", 0), -item["confidence"], -item["score"]))
    primary = candidates[0]
    blockers = []
    if market.get("risk") == "high":
        blockers.append("指数环境触发高风险拦截")
    if primary["confidence"] < 66:
        blockers.append("预测胜率低于 66%")
    if primary.get("hard_risk_count", 0) >= 2:
        blockers.append("硬风险项过多，不适合 2 日持有")
    if len(primary["risk_flags"]) >= 3:
        blockers.append("候选股风险标签过多")
    if primary["amount_yi"] < 2.5:
        blockers.append("成交额不足，承接不够")
    if primary["change_pct"] >= 9.5:
        blockers.append("信号日已接近涨停，次日追高性价比不足")
    if primary["estimated_2d_range"]["low_pct"] <= -3.0:
        blockers.append("预估下行空间过大")

    if blockers:
        return {
            "action": "NO_TRADE",
            "title": "今日不交易",
            "message": "；".join(blockers),
            "primary": None,
            "blocked_candidate": primary,
            "watchlist": candidates[:8],
        }
    return {
        "action": "BUY_CANDIDATE",
        "title": "今日主选",
        "message": "满足二日持有的结构确认、回撤约束和风控阈值。",
        "primary": primary,
        "watchlist": candidates[1:9],
    }


def run_selector(date_text: str | None = None, force: bool = False) -> dict:
    target_day = dt.date.fromisoformat(date_text) if date_text else now_cn().date()
    signal_day = default_signal_date(target_day)
    cache_key = f"{target_day.isoformat()}_{signal_day.isoformat()}.json"
    cache_path = PICKS / cache_key
    if cache_path.exists() and not force:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("model_version") == MODEL_VERSION:
            return cached

    hot_date, event_rows = find_hot_pool(signal_day)
    broad_rows = load_broad_market_pool()
    hot_rows = merge_candidate_pools(event_rows, broad_rows)
    market = index_quotes()
    industries = industry_heat()
    scored = score_candidates(hot_date, hot_rows, market)
    decision = make_decision(scored["candidates"], market)
    next_day = next_weekday(target_day)
    result = {
        "model_version": MODEL_VERSION,
        "generated_at": now_cn().isoformat(timespec="seconds"),
        "target_date": target_day.isoformat(),
        "next_trade_date": next_day.isoformat(),
        "signal_date": hot_date,
        "holding_plan": "买入后最多持有 2 个交易日；若触发止损或 MA10 失守，提前退出。",
        "decision": decision,
        "market": market,
        "industry_heat": industries,
        "stats": {
            "hot_pool_size": scored["raw_pool_size"],
            "event_pool_size": len(event_rows),
            "broad_pool_size": len(broad_rows),
            "scored_size": scored["scored_size"],
            "dragon_count": scored["dragon_count"],
        },
        "chan_rules": CHAN_RULES,
        "accuracy_note": (
            "预测准确率是规则模型按信号强度映射的先验估计；"
            "需要每天保存结果后，用真实 2 日收益滚动校准。"
        ),
        "disclaimer": "本工具是量化决策辅助，不构成投资建议，不保证盈利。",
    }
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (PICKS / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


class AppHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean = urllib.parse.urlparse(path).path
        if clean == "/":
            return str(STATIC / "index.html")
        if clean.startswith("/static/"):
            return str(ROOT / clean.lstrip("/"))
        return str(STATIC / clean.lstrip("/"))

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/pick":
            query = urllib.parse.parse_qs(parsed.query)
            date_text = query.get("date", [None])[0]
            force = query.get("force", ["0"])[0] == "1"
            try:
                self.send_json(run_selector(date_text=date_text, force=force))
            except Exception as exc:
                self.send_json({"error": str(exc), "disclaimer": "数据源暂不可用，请稍后重试。"}, 500)
            return
        if parsed.path == "/api/history":
            query = urllib.parse.parse_qs(parsed.query)
            limit = int(query.get("limit", ["30"])[0])
            self.send_json(history_payload(limit=max(1, min(limit, 90))))
            return
        if parsed.path == "/api/latest":
            latest = PICKS / "latest.json"
            if not latest.exists():
                self.send_json({"error": "暂无历史决策缓存"}, 404)
                return
            payload = json.loads(latest.read_text(encoding="utf-8"))
            self.send_json(payload)
            return
        if parsed.path == "/api/status":
            latest = PICKS / "latest.json"
            payload = {
                "ok": True,
                "time": now_cn().isoformat(timespec="seconds"),
                "has_latest": latest.exists(),
                "latest_path": str(latest) if latest.exists() else None,
            }
            self.send_json(payload)
            return
        super().do_GET()


def scheduler_loop() -> None:
    last_run = ""
    while True:
        current = now_cn()
        key = current.strftime("%Y-%m-%d %H:%M")
        if current.weekday() < 5 and current.hour == 8 and current.minute == 30 and key != last_run:
            last_run = key
            try:
                run_selector(date_text=current.date().isoformat(), force=True)
            except Exception as exc:
                log_path = CACHE / "scheduler-error.log"
                log_path.write_text(f"{current.isoformat()} {exc}\n", encoding="utf-8")
        time.sleep(20)


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def serve(port: int, host: str) -> None:
    threading.Thread(target=scheduler_loop, daemon=True).start()
    with ReusableThreadingTCPServer((host, port), AppHandler) as httpd:
        print(f"Chan stock selector running at http://{host}:{port}")
        httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8790")))
    parser.add_argument("--once", action="store_true", help="Run selector once and print JSON.")
    parser.add_argument("--date", help="Target date, YYYY-MM-DD.")
    parser.add_argument("--force", action="store_true", help="Ignore cache.")
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run_selector(args.date, force=args.force), ensure_ascii=False, indent=2))
        return
    serve(args.port, args.host)


if __name__ == "__main__":
    main()

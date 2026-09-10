"""Deterministic ten-session return-opportunity research ranking.

This is an evidence score, not a fitted expected-return model. It deliberately
does not consume Legacy qualification, scenario upside, or shadow predictions.
All values are derived from the snapshot cut-off, so archived runs are replayable.
"""

from __future__ import annotations

import datetime as dt
import copy
import json
import math
import statistics
from collections import Counter, defaultdict
from typing import Any, Mapping

from event_pipeline import candidate_scan_coverage, event_is_auditable
from market_calendar import expected_quote_session, market_local_date, session_dates


CONTRACT_VERSION = "return-opportunities-v1"
SCORE_VERSION = "return-opportunity-score-v2"
SCORE_KIND = "RETURN_OPPORTUNITY_RULE_SCORE"
WEIGHTS = {"momentum": 0.30, "relative_strength": 0.20, "acceleration": 0.15,
           "trend_volume": 0.20, "sector_strength": 0.10, "material_event": 0.05}
MARKETS = ("a_share", "hk", "us")
CURRENCIES = {"a_share": "CNY", "hk": "HKD", "us": "USD"}
MIN_DAILY_VALUE = {"a_share": 20_000_000, "hk": 2_000_000, "us": 1_000_000}
LIMITATIONS = [
    "机会分衡量近端收益证据，尚未通过样本外收益预测验证，不代表上涨概率或预期收益。",
    "排名仅覆盖本次召回且数据合格的股票；市场相对强度使用召回池横截面，不代表全市场指数超额收益。",
    "行业强度只使用有来源和时间、未过期的行业分类；近似主题、无来源标签或同行少于3只时按中性分处理。",
    "公告扫描仅覆盖有限官方标题与申报元数据；未扫描、扫描失败及成功空结果均不代表已排除重大负面事件。",
    "历史波动情景不是预测分位数；仓位示例无法保证止损成交或最大亏损。",
    "成交成本与未来收益尚未校准，因此预期净收益和概率保持为空。",
]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _bounded(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _aware(value: Any) -> dt.datetime | None:
    try:
        result = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _code(row: Mapping) -> str:
    return str(row.get("code") or row.get("symbol") or "").upper()


def _sector(candidate: Mapping, metadata: Mapping, *, cutoff: dt.datetime | None = None) -> dict:
    # Labels only: never infer an industry from a ticker or award sector-name
    # bonuses. Generic recall roles are not industry evidence.
    sourced = []
    for row in (metadata, candidate):
        provenance = row.get("sector_metadata")
        if not isinstance(provenance, Mapping) or not str(provenance.get("name") or "").strip():
            continue
        record = dict(provenance)
        retrieved = _aware(record.get("retrieved_at"))
        future = bool(cutoff and retrieved and retrieved > cutoff)
        stale = record.get("stale") is True or record.get("status") == "STALE"
        if cutoff and retrieved and (cutoff - retrieved).total_seconds() > 7 * 86400:
            stale = True
        verified = bool(record.get("source") and retrieved and not future and not stale and record.get("status") == "FRESH")
        record.update({"name": str(record["name"]).strip(), "verified": verified,
                       "status": "KNOWN" if verified else "STALE" if stale else "UNVERIFIED",
                       "stale": stale, "evidence_type": "provider_classification"})
        if verified:
            return record
        sourced.append(record)
    if sourced:
        return sourced[0]
    for source, row in (("candidate_metadata", candidate), ("universe_metadata", metadata)):
        for key in ("industry", "sector"):
            value = row.get(key)
            if isinstance(value, Mapping):
                value = value.get("name")
            if isinstance(value, str) and value.strip() not in {"", "未知", "其他", "未分类", "Unknown"}:
                return {"name": value.strip(), "source": source, "status": "UNVERIFIED",
                        "verified": False, "evidence_type": "unsourced_classification"}
        description = str(row.get("role") or "")
        generic = any(word in description.lower() for word in ("动态", "召回", "多因子", "市场扫描", "dynamic", "recall", "momentum", "liquid"))
        if generic:
            continue
        themes = row.get("themes") or row.get("theme_tags") or []
        if isinstance(themes, str):
            themes = [themes]
        labels = [str(item).strip() for item in themes if isinstance(item, str)]
        # A declared economic theme is an approximate industry grouping, whose
        # provenance stays visible. Roles without metadata remain missing.
        for label in labels:
            if label and label not in {"高股息", "价值", "成长", "出海", "周期", "权重", "高流动性", "科技", "AI", "防御"}:
                return {"name": label, "source": source + ".themes", "status": "APPROXIMATE",
                        "verified": False, "evidence_type": "curated_theme"}
        if source == "universe_metadata" and description:
            label = description.split("/")[0].strip()
            if label:
                return {"name": label, "source": source + ".role", "status": "APPROXIMATE",
                        "verified": False, "evidence_type": "curated_role"}
    return {"name": "行业待补充", "source": None, "status": "MISSING", "verified": False, "evidence_type": None}


def _metadata_index(metadata: Any) -> dict:
    if isinstance(metadata, Mapping):
        return {str(key).upper(): value for key, value in metadata.items() if isinstance(value, Mapping)}
    return {_code(row): row for row in (metadata or []) if isinstance(row, Mapping) and _code(row)}


def _market_sections(snapshot: Mapping) -> dict:
    sections = snapshot.get("markets") or {}
    if isinstance(sections, Mapping):
        return dict(sections)
    return {row.get("key"): row for row in sections if isinstance(row, Mapping)}


def _events(snapshot: Mapping, market: str, code: str) -> tuple[list, list]:
    section = snapshot.get("events") or {}
    events = section.get("items") or section.get("events") or [] if isinstance(section, Mapping) else []
    positive, negative = [], []
    for event in events:
        if not isinstance(event, Mapping) or not event_is_auditable(event, snapshot, market, code):
            continue
        if event.get("direction") == "negative" and event.get("decision_blocking"):
            negative.append(event)
        if event.get("direction") == "positive" and event.get("decision_eligible"):
            positive.append(event)
    return positive, negative


def _event_evidence(events: list) -> tuple[float, list[str]]:
    clusters = {}
    for event in events:
        quantified = max((_number(event.get(key)) or 0 for key in (
            "impact_to_market_cap_pct", "revenue_impact_pct", "buyback_pct_of_shares")), default=0)
        verified = event.get("materiality_verified") is True
        evidence = event.get("materiality_evidence")
        verified = verified or (isinstance(evidence, Mapping) and evidence.get("verified") is True)
        if not verified and quantified < 1:
            title = str(event.get("title") or "").lower()
            # A measured catalyst is stronger evidence than a keyword. A
            # specific guidance/contract announcement may contribute a small
            # research hint, while routine share repurchase reports do not.
            explicit_catalyst = any(word in title for word in (
                "上调业绩", "业绩预增", "中标", "重大合同", "raised guidance", "raises guidance", "major contract"))
            if not explicit_catalyst:
                continue
        cluster = str(event.get("event_cluster_id") or event.get("cluster_id") or event.get("plan_id")
                      or event.get("event_type") or "material_filing")
        strength = _bounded(70 + min(quantified, 5) * 6) if verified or quantified >= 1 else 35
        clusters[cluster] = max(clusters.get(cluster, 0), strength)
    # The strongest supported catalyst contributes once. Daily disclosure
    # count, even under different document IDs, cannot create a bonus.
    return max(clusters.values(), default=0), sorted(clusters)


def _base_row(snapshot: Mapping, candidate: Mapping, market: str, metadata: Mapping,
              evaluated: Mapping, expected: dt.date | None) -> dict:
    generated = _aware(snapshot.get("feature_cutoff_at")) or _aware(snapshot.get("generated_at"))
    realtime = candidate.get("realtime") or {}
    quote_time = _aware(realtime.get("source_as_of"))
    price = _number(realtime.get("price")) or _number(realtime.get("current_price")) or _number(candidate.get("price"))
    blockers, flags = [], []
    if price is None or price <= 0:
        blockers.append("INVALID_PRICE")
    if generated is None or expected is None:
        blockers.append("SNAPSHOT_TIME_INVALID")
    if quote_time is None:
        blockers.append("QUOTE_SOURCE_TIME_MISSING")
    elif generated:
        if quote_time > generated + dt.timedelta(minutes=5):
            blockers.append("QUOTE_FROM_FUTURE")
        if expected and market_local_date(market, quote_time) < expected:
            blockers.append("STALE_QUOTE")
    if realtime.get("stale") or str(realtime.get("quote_status") or "").upper() in {"STALE", "MISSING", "UNAVAILABLE"}:
        blockers.append("STALE_QUOTE")
    if candidate.get("suspended") or str(candidate.get("trade_status") or "").lower() in {"suspended", "halted", "delisted"}:
        blockers.append("NOT_TRADABLE")
    if candidate.get("delisting") or "退市" in str(candidate.get("name") or ""):
        blockers.append("DELISTING")
    if candidate.get("technical_screen_eligible") is False:
        blockers.append("TRADABILITY_SCREEN_FAILED")
    for risk in candidate.get("risk_items") or []:
        if isinstance(risk, Mapping) and risk.get("severity") == "hard":
            blockers.append(str(risk.get("code") or "HARD_EXECUTION_RISK"))
    for gate in candidate.get("decision_gates") or []:
        if isinstance(gate, Mapping) and gate.get("status") == "BLOCK":
            blockers.append("EXECUTION_GATE_" + str(gate.get("id") or "UNKNOWN").upper())
    if candidate.get("execution_state") == "BLOCKED":
        blockers.append("CANDIDATE_EXECUTION_BLOCKED")
    if "MATERIAL_NEGATIVE_EVENT" in (evaluated.get("blocker_codes") or []):
        blockers.append("MATERIAL_NEGATIVE_EVENT")
    quality = candidate.get("data_quality") or {}
    for item in quality.get("inputs") or []:
        if isinstance(item, Mapping) and item.get("required") and item.get("state") in {"stale", "missing"}:
            blockers.append("REQUIRED_INPUT_" + str(item.get("id") or "UNKNOWN").upper())
    bars = candidate.get("kline") or []
    bars = bars[-60:] if isinstance(bars, list) else []
    valid, dates, traded_values = [], [], []
    for bar in bars:
        if not isinstance(bar, Mapping):
            blockers.append("KLINE_INVALID")
            continue
        values = [_number(bar.get(key)) for key in ("open", "high", "low", "close", "volume")]
        try:
            date = dt.date.fromisoformat(str(bar.get("date"))[:10])
        except ValueError:
            blockers.append("KLINE_DATE_INVALID")
            continue
        if any(value is None for value in values) or min(values[:4]) <= 0 or values[4] < 0:
            blockers.append("KLINE_INVALID")
            continue
        open_, high, low, close, volume = values
        if high < max(open_, close, low) or low > min(open_, close, high):
            blockers.append("KLINE_OHLC_INVALID")
            continue
        dates.append(date)
        amount = _number(bar.get("amount"))
        # Provider units are part of data provenance. A-share Tencent and
        # EastMoney bars use lots (100 shares); Yahoo adjusted bars use shares.
        # Prefer the observed monetary amount whenever available.
        unit = bar.get("volume_unit")
        adjustment = str(bar.get("price_adjustment") or "")
        if not unit:
            unit = "share" if "yahoo" in adjustment or market != "a_share" else realtime.get("volume_unit") or "lot"
        multiplier = 100 if unit == "lot" else 1
        valid.append((open_, high, low, close, volume * multiplier))
        traded_values.append(amount if amount is not None and amount > 0 else close * volume * multiplier)
    if len(valid) < 32:
        blockers.append("KLINE_INCOMPLETE")
    if dates != sorted(set(dates)):
        blockers.append("KLINE_DATES_NOT_UNIQUE_SORTED")
    if dates and expected:
        prior_sessions = session_dates(market, expected - dt.timedelta(days=12), expected)
        oldest_allowed = prior_sessions[-2] if len(prior_sessions) >= 2 else expected
        if dates[-1] < oldest_allowed:
            blockers.append("KLINE_STALE")
        if dates[-1] > expected:
            blockers.append("KLINE_FROM_FUTURE")
    positive_events, negative_events = _events(snapshot, market, _code(candidate))
    event_coverage = candidate_scan_coverage(snapshot, market, _code(candidate))
    if event_coverage["status"] == "NOT_SCANNED":
        flags.append("OFFICIAL_EVENT_NOT_SCANNED")
    elif event_coverage["status"] == "ERROR":
        flags.append("OFFICIAL_EVENT_SCAN_ERROR")
    flags.append("NEGATIVE_EVENT_COVERAGE_INCOMPLETE")
    if negative_events:
        blockers.append("MATERIAL_NEGATIVE_EVENT")
    event_score, event_clusters = _event_evidence(positive_events)
    if event_score == 35:
        flags.append("CATALYST_MATERIALITY_UNQUANTIFIED")
    result = {
        "market": market, "code": _code(candidate), "name": str(candidate.get("name") or _code(candidate)),
        "sector": _sector(candidate, metadata, cutoff=generated), "qualification_blockers": blockers, "risk_flags": flags,
        "event_coverage": event_coverage,
        "reference_quote": {"price": price, "currency": CURRENCIES[market], "source_as_of": realtime.get("source_as_of"),
                            "source": realtime.get("source"), "quote_status": realtime.get("quote_status")},
        "metrics": {"event_cluster_count": len(event_clusters)}, "event_cluster_ids": event_clusters,
        "_event_score": event_score,
    }
    if result["sector"]["status"] != "KNOWN":
        flags.append("SECTOR_METADATA_" + result["sector"]["status"])
    if len(valid) < 32:
        return result
    closes = [row[3] for row in valid]
    returns = [(b / a - 1) * 100 for a, b in zip(closes[-21:], closes[-20:])]
    if any(abs(value) > 65 for value in returns):
        blockers.append("KLINE_POSSIBLE_UNADJUSTED_JUMP")
    daily_vol = statistics.pstdev(returns)
    r5, r10, r20 = [(closes[-1] / closes[-(n + 1)] - 1) * 100 for n in (5, 10, 20)]
    ma5, ma10, ma20 = [statistics.mean(closes[-n:]) for n in (5, 10, 20)]
    distance = (closes[-1] / ma20 - 1) * 100
    vol_base = max(daily_vol, 0.75)
    normalized = 0.3 * r5 / (vol_base * math.sqrt(5)) + 0.45 * r10 / (vol_base * math.sqrt(10)) + 0.25 * r20 / (vol_base * math.sqrt(20))
    weighted_return = 0.3 * r5 + 0.45 * r10 + 0.25 * r20
    prev5 = (closes[-6] / closes[-11] - 1) * 100
    acceleration = (r5 - prev5) / (vol_base * math.sqrt(10))
    volumes = [row[4] for row in valid]
    old_volume = statistics.mean(volumes[-20:-5])
    volume_ratio = statistics.mean(volumes[-5:]) / old_volume if old_volume > 0 else None
    daily_value = statistics.median(traded_values[-20:])
    if volume_ratio is None or daily_value <= 0:
        blockers.append("VOLUME_MISSING")
    elif daily_value < MIN_DAILY_VALUE[market]:
        blockers.append("INSUFFICIENT_TRADED_VALUE")
    if r10 < 0 and r5 <= 0 or closes[-1] < ma20 and ma5 < ma10 and r5 < 0:
        blockers.append("NEGATIVE_TREND")
    if (r5 > 30 and r5 / (vol_base * math.sqrt(5)) > 4.5) or (distance > 30 and distance / (vol_base * math.sqrt(10)) > 4.0):
        blockers.append("EXTREME_CHASE")
    if daily_vol > 3:
        flags.append("HIGH_VOLATILITY_REDUCE_SIZE")
    if r5 > 15 or distance > 15:
        flags.append("EXTENDED_PRICE_REQUIRES_PATIENCE")
    if result["sector"]["status"] == "MISSING":
        flags.append("SECTOR_METADATA_MISSING")
    momentum = _bounded(50 + 30 * math.tanh(weighted_return / 10) + 15 * math.tanh(normalized / 3))
    trend = (25 if closes[-1] > ma20 else 0) + (25 if ma5 > ma10 else 0) + (25 if ma10 > ma20 else 0)
    volume_support = _bounded(50 + 35 * math.tanh(((volume_ratio or 1) - 1) / 0.5))
    trend_volume = _bounded(0.75 * (trend + (25 if r5 > 0 else 0)) + 0.25 * volume_support)
    result["metrics"].update({
        "return_5d_pct": round(r5, 3), "return_10d_pct": round(r10, 3), "return_20d_pct": round(r20, 3),
        "daily_volatility_pct": round(daily_vol, 3), "normalized_momentum": round(normalized, 3),
        "acceleration_z": round(acceleration, 3), "volume_ratio_5d_20d": round(volume_ratio, 3) if volume_ratio is not None else None,
        "distance_ma20_pct": round(distance, 3), "median_daily_traded_value": round(daily_value, 2),
        "source_window_start_date": dates[-21].isoformat(), "source_window_end_date": dates[-1].isoformat(),
        "kline_count": len(valid),
    })
    # Symmetric historical-volatility context. It is not used in ranking and
    # is deliberately not labelled q10/q90 or expected return.
    width = 1.28 * daily_vol * math.sqrt(10)
    result["scenario_range"] = {"low_pct": round(-width, 2), "high_pct": round(width, 2),
        "horizon_trade_days": 10, "calibrated": False, "method_id": "realized-volatility-context-v1",
        "source_observations": len(returns), "label": "历史波动情景"}
    risk_proxy = max(width, 3)
    result["risk_budget"] = {"illustrative_weight_pct": round(min(15, 0.5 / risk_proxy * 100), 2),
        "risk_proxy_pct": round(risk_proxy, 2), "portfolio_risk_budget_pct": 0.5,
        "method": "volatility_budget_illustration", "guaranteed_stop": False}
    result["_scores"] = {"momentum": momentum, "acceleration": _bounded(50 + 35 * math.tanh(acceleration)),
                          "trend_volume": trend_volume, "material_event": event_score}
    result["_relative_signal"] = weighted_return
    return result


def _percentile(value: float, population: list[float]) -> float:
    if len(population) < 2:
        return 50.0
    less = sum(other < value for other in population)
    equal = sum(other == value for other in population)
    return 100 * (less + (equal - 1) / 2) / (len(population) - 1)


def build_return_opportunities(snapshot: Mapping, candidate_pools: Mapping,
                               metadata_by_market: Mapping | None = None) -> dict:
    """Rank valid candidates using observable return evidence at snapshot time."""
    metadata_by_market = metadata_by_market or {}
    global_rows = (snapshot.get("global_decision") or {}).get("evaluated_candidates") or []
    evaluated = {(row.get("market"), _code(row)): row for row in global_rows if isinstance(row, Mapping)}
    all_rows, market_stats, originals = [], {}, {}
    for market in MARKETS:
        metadata = _metadata_index(metadata_by_market.get(market))
        try:
            cutoff = snapshot.get("feature_cutoff_at") if _aware(snapshot.get("feature_cutoff_at")) else snapshot.get("generated_at")
            expected = expected_quote_session(market, cutoff)
        except (TypeError, ValueError, OverflowError):
            expected = None
        pools = candidate_pools.get(market) or []
        if isinstance(pools, Mapping):
            pools = pools.get("candidates") or pools.get("_candidate_pool") or []
        # Full candidate pool is authoritative; duplicate input order cannot
        # change the ranking. For duplicate symbols prefer richer valid history.
        candidates = {}
        for candidate in pools:
            if not isinstance(candidate, Mapping) or not _code(candidate):
                continue
            code = _code(candidate)
            if code not in candidates or len(candidate.get("kline") or []) > len(candidates[code].get("kline") or []):
                candidates[code] = candidate
            elif len(candidate.get("kline") or []) == len(candidates[code].get("kline") or []):
                def duplicate_priority(item):
                    source_time = _aware((item.get("realtime") or {}).get("source_as_of"))
                    return (source_time.timestamp() if source_time else 0,
                            json.dumps(_json_safe(item), sort_keys=True, default=str))
                if duplicate_priority(candidate) > duplicate_priority(candidates[code]):
                    candidates[code] = candidate
        originals.update({(market, code): candidate for code, candidate in candidates.items()})
        rows = [_base_row(snapshot, candidate, market, metadata.get(code, {}), evaluated.get((market, code), {}), expected)
                for code, candidate in sorted(candidates.items())]
        peer_rows = [row for row in rows if "_scores" in row and not row["qualification_blockers"]]
        population = [row["_relative_signal"] for row in peer_rows]
        sectors = defaultdict(list)
        for row in peer_rows:
            if row["sector"]["status"] == "KNOWN":
                sectors[row["sector"]["name"]].append(row)
        known_count = sum(len(group) for group in sectors.values())
        coverage = 100 * known_count / len(peer_rows) if peer_rows else 0
        market_median = statistics.median(population) if population else 0
        for row in rows:
            scores = row.get("_scores")
            if scores is None:
                continue
            peers = sectors.get(row["sector"]["name"], []) if row["sector"]["status"] == "KNOWN" else []
            relative = _percentile(row["_relative_signal"], population) if not row["qualification_blockers"] else 50
            sector_strength = 50.0
            if len(peers) >= 3:
                sector_mean = statistics.median([peer["_relative_signal"] for peer in peers])
                sector_strength = _bounded(50 + 35 * math.tanh((sector_mean - market_median) / 6))
            else:
                row["risk_flags"].append("SECTOR_PEER_SAMPLE_INSUFFICIENT")
            scores.update({"relative_strength": relative, "sector_strength": sector_strength})
            row["metrics"].update({"market_relative_strength_percentile": round(relative, 2),
                "sector_relative_strength_percentile": round(_percentile(row["_relative_signal"], [p["_relative_signal"] for p in peers]), 2) if len(peers) >= 3 else None,
                "sector_peer_count": len(peers), "sector_coverage_pct": round(coverage, 2),
                "market_peer_count": len(peer_rows), "sector_strength_status": "OBSERVED" if len(peers) >= 3 else "NEUTRAL_INSUFFICIENT_COVERAGE"})
            row["components"] = {key: {"score": round(scores[key], 3), "weight": weight,
                                      "contribution": round(scores[key] * weight, 3)} for key, weight in WEIGHTS.items()}
            row["opportunity_score"] = round(sum(scores[key] * weight for key, weight in WEIGHTS.items()), 2)
            if row["opportunity_score"] < 60 or max(row["metrics"]["return_5d_pct"], row["metrics"]["return_10d_pct"]) <= 0:
                row["qualification_blockers"].append("RETURN_EVIDENCE_BELOW_THRESHOLD")
            row["reasons"] = [f"近5/10/20日收益 {row['metrics']['return_5d_pct']:+.1f}% / {row['metrics']['return_10d_pct']:+.1f}% / {row['metrics']['return_20d_pct']:+.1f}%",
                f"本市场有效召回池相对强度第 {relative:.0f} 百分位，样本 {len(peer_rows)} 只",
                f"近5日量能/此前15日 {row['metrics']['volume_ratio_5d_20d'] or 0:.2f} 倍；每日波动 {row['metrics']['daily_volatility_pct']:.2f}%"]
        all_rows.extend(rows)
        market_stats[market] = {"evaluated_count": len(rows), "data_valid_count": len(peer_rows), "sector_known_count": known_count,
                               "sector_coverage_pct": round(coverage, 2), "expected_quote_session": expected.isoformat() if expected else None,
                               "event_scanned_count": sum(row["event_coverage"]["verified"] for row in rows),
                               "event_coverage_status_counts": dict(Counter(row["event_coverage"]["status"] for row in rows))}
    eligible, excluded = [], []
    for row in all_rows:
        row["qualification_blockers"] = sorted(set(row["qualification_blockers"]))
        row["risk_flags"] = sorted(set(row["risk_flags"]))
        row.update({"score_kind": SCORE_KIND, "score_version": SCORE_VERSION, "calibrated": False, "production_eligible": False,
                    "expected_net_return": None, "probability": None})
        for key in list(row):
            if key.startswith("_"):
                row.pop(key)
        if row["qualification_blockers"]:
            row["qualification_status"] = "EXCLUDED"
            excluded.append({key: row.get(key) for key in ("market", "code", "name", "opportunity_score", "score_version", "qualification_status", "qualification_blockers", "event_coverage", "risk_flags", "sector")})
        else:
            row["qualification_status"] = "RESEARCH_ELIGIBLE"
            eligible.append(row)
    eligible.sort(key=lambda row: (-row["opportunity_score"], -row["metrics"]["return_10d_pct"], row["market"], row["code"]))
    market_ranks = Counter()
    for rank, row in enumerate(eligible, 1):
        market_ranks[row["market"]] += 1
        row.update({"rank": rank, "market_rank": market_ranks[row["market"]]})
    selected, deferred, sector_counts = [], [], Counter()
    for row in eligible:
        # The displayed subset preserves true score ranks. Unknown sectors
        # cannot be treated as one economic industry.
        sector_key = row["sector"]["name"] if row["sector"]["status"] == "KNOWN" else row["market"] + ":" + row["code"]
        if sector_counts[sector_key] >= 4:
            deferred.append(row)
            continue
        selected.append(row)
        sector_counts[sector_key] += 1
        if len(selected) == 12:
            break
    if len(selected) < 12:
        selected.extend(deferred[:12-len(selected)])
    selected.sort(key=lambda row: row["rank"])
    for row in selected:
        row["candidate_snapshot"] = copy.deepcopy(originals[(row["market"], row["code"])])
    scan_targets = {}
    for market, stats in market_stats.items():
        local = [row for row in eligible if row["market"] == market]
        scan_targets[market] = list(dict.fromkeys(
            [row["code"] for row in selected if row["market"] == market]
            + [row["code"] for row in local]
        ))[:24]
        stats.update({"eligible_count": len(local), "excluded_count": stats["evaluated_count"] - len(local),
                      "primary": local[0] if local else None})
    result = {"contract_version": CONTRACT_VERSION, "status": "RESEARCH_READY" if eligible else "NO_OPPORTUNITY",
        "generated_at": snapshot.get("generated_at"), "horizon_trade_days": 10, "score_kind": SCORE_KIND, "score_version": SCORE_VERSION,
        "calibrated": False, "production_eligible": False, "expected_net_return": None, "probability": None,
        "evaluated_count": len(all_rows), "eligible_count": len(eligible), "excluded_count": len(excluded),
        "primary": eligible[0] if eligible else None, "candidates": selected, "excluded_candidates": excluded,
        "market_summaries": market_stats, "weights": dict(WEIGHTS), "limitations": list(LIMITATIONS),
        "event_scan_targets_by_market": scan_targets,
        "selection_policy": {"score_version": SCORE_VERSION, "minimum_score": 60, "maximum_displayed": 12, "soft_sector_cap": 4,
                             "sector_evidence_policy": "fresh_sourced_classification_only",
                             "event_coverage_policy": "bounded_enrichment_with_explicit_unknown_negative_risk",
                             "ranking_basis": "observed_return_evidence", "scenario_upside_used_in_ranking": False}}
    return _json_safe(result)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def validate_return_opportunities(contract: Any) -> list[str]:
    """Validate the public research boundary, counts and selected identities."""
    errors = []
    if not isinstance(contract, Mapping):
        return ["return_opportunities must be an object"]
    prefix = "return_opportunities"
    fixed = {"contract_version": CONTRACT_VERSION, "score_kind": SCORE_KIND,
             "horizon_trade_days": 10, "calibrated": False, "production_eligible": False,
             "expected_net_return": None, "probability": None}
    for key, expected in fixed.items():
        if key not in contract or contract[key] != expected or (expected is False and contract[key] is not False):
            errors.append(f"{prefix}.{key} is invalid")
    if contract.get("score_version") not in {None, SCORE_VERSION}:
        errors.append(prefix + ".score_version is invalid")
    def check_finite(value, path):
        if isinstance(value, float) and not math.isfinite(value):
            errors.append(path + " contains non-finite number")
        elif isinstance(value, Mapping):
            for key, item in value.items():
                check_finite(item, path + "." + str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                check_finite(item, path + f"[{index}]")
    check_finite(contract, prefix)
    if contract.get("score_version") == SCORE_VERSION:
        for collection in ("candidates", "excluded_candidates"):
            for index, row in enumerate(contract.get(collection) or []):
                if not isinstance(row, Mapping):
                    continue
                path = prefix + f".{collection}[{index}]"
                coverage = row.get("event_coverage")
                if not isinstance(coverage, Mapping):
                    errors.append(path + ".event_coverage is missing")
                    continue
                status = coverage.get("status")
                if (status not in {"SUCCESS", "ERROR", "NOT_SCANNED"}
                    or coverage.get("verified") is not (status == "SUCCESS")
                    or coverage.get("negative_clearance_verified") is not False):
                    errors.append(path + ".event_coverage is invalid")
                if coverage.get("market") != row.get("market") or coverage.get("symbol") != row.get("code"):
                    errors.append(path + ".event_coverage identity mismatch")
                if status == "SUCCESS" and (coverage.get("requested") is not True or not coverage.get("run_id") or not coverage.get("source_id")):
                    errors.append(path + ".event_coverage verified evidence is missing")
                flags = row.get("risk_flags") or []
                required_flags = ["NEGATIVE_EVENT_COVERAGE_INCOMPLETE"]
                if status in {"ERROR", "NOT_SCANNED"}:
                    required_flags.append("OFFICIAL_EVENT_SCAN_ERROR" if status == "ERROR" else "OFFICIAL_EVENT_NOT_SCANNED")
                if any(flag not in flags for flag in required_flags):
                    errors.append(path + ".risk_flags omit filing uncertainty")
                if row.get("score_version") != SCORE_VERSION:
                    errors.append(path + ".score_version mismatch")
    counts = [contract.get(key) for key in ("evaluated_count", "eligible_count", "excluded_count")]
    if not all(type(count) is int and count >= 0 for count in counts) or counts[0] != counts[1] + counts[2]:
        errors.append(prefix + " counts are inconsistent")
    candidates = contract.get("candidates")
    if not isinstance(candidates, list):
        return errors + [prefix + ".candidates must be a list"]
    if len(candidates) > 12 or (isinstance(counts[1], int) and len(candidates) != min(12, counts[1])):
        errors.append(prefix + ".candidates count is inconsistent")
    seen, previous_rank = set(), 0
    previous_score = 101
    for index, row in enumerate(candidates):
        path = prefix + f".candidates[{index}]"
        if not isinstance(row, Mapping):
            errors.append(path + " must be an object")
            continue
        identity = (row.get("market"), row.get("code"))
        valid_identity = all(isinstance(part, str) and part for part in identity)
        if not valid_identity or identity[0] not in MARKETS or identity in seen:
            errors.append(path + " identity is invalid or duplicated")
        if valid_identity:
            seen.add(identity)
        for key in ("score_kind", "calibrated", "production_eligible", "expected_net_return", "probability"):
            if key not in row or row.get(key) != fixed[key] or (fixed[key] is False and row.get(key) is not False):
                errors.append(path + "." + key + " is invalid")
        if row.get("qualification_status") != "RESEARCH_ELIGIBLE" or row.get("qualification_blockers") != []:
            errors.append(path + " research qualification is invalid")
        rank, score = row.get("rank"), _number(row.get("opportunity_score"))
        if type(rank) is not int or rank <= previous_rank:
            errors.append(path + ".rank must increase")
        else:
            previous_rank = rank
        if score is None or score < 60 or score > 100 or score > previous_score:
            errors.append(path + ".opportunity_score is invalid or out of order")
        else:
            previous_score = score
        frozen = row.get("candidate_snapshot")
        if frozen is not None and (not isinstance(frozen, Mapping) or _code(frozen) != row.get("code")):
            errors.append(path + ".candidate_snapshot identity mismatch")
    primary = contract.get("primary")
    if candidates:
        if contract.get("status") != "RESEARCH_READY" or primary != candidates[0] or candidates[0].get("rank") != 1:
            errors.append(prefix + " primary/status/rank do not match first candidate")
    elif primary is not None or contract.get("status") != "NO_OPPORTUNITY":
        errors.append(prefix + " empty status/primary is invalid")
    return errors

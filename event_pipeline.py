"""Bounded, auditable official-filing collection for A/H/US candidates."""

from __future__ import annotations

import datetime as dt
import concurrent.futures
import hashlib
import html
import json
import math
import os
import re
import urllib.parse
from collections.abc import Callable, Mapping
from typing import Any
from zoneinfo import ZoneInfo

import requests


CN_TZ = ZoneInfo("Asia/Shanghai")
LOOKBACK_DAYS = 45
SOURCE_REGISTRY = {
    "a_share": {
        "source_id": "cninfo_announcements_v1",
        "hosts": ("cninfo.com.cn",),
        "source": "巨潮资讯",
    },
    "hk": {
        "source_id": "hkexnews_titles_v1",
        "hosts": ("hkexnews.hk",),
        "source": "HKEXnews",
    },
    "us": {
        "source_id": "sec_edgar_submissions_v1",
        "hosts": ("sec.gov",),
        "source": "SEC EDGAR",
    },
}
POSITIVE_TERMS = (
    "中标",
    "重大合同",
    "签订合同",
    "预增",
    "扭亏",
    "股份回购",
    "增持",
    "订单",
    "share buyback",
    "award of contract",
    "profit alert - positive",
)
NEGATIVE_TERMS = (
    "立案",
    "处罚",
    "警示函",
    "减持",
    "预亏",
    "亏损",
    "终止上市",
    "停牌",
    "清盘",
    "winding up",
    "profit warning",
)
MATERIAL_FORMS = {"8-K", "10-K", "10-Q", "20-F", "6-K", "DEF 14A", "SC 13D", "SC 13D/A"}


class EventPipelineError(RuntimeError):
    pass


def _aware(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=CN_TZ)
    return parsed.astimezone(CN_TZ)


def _moment_from_epoch_millis(value: Any) -> dt.datetime | None:
    try:
        return dt.datetime.fromtimestamp(float(value) / 1000.0, CN_TZ)
    except (TypeError, ValueError, OSError):
        return None


def _stable_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _classify(title: str) -> tuple[str, str, bool]:
    lowered = str(title or "").lower()
    if any(term.lower() in lowered for term in NEGATIVE_TERMS):
        return "negative", "material", True
    if any(term.lower() in lowered for term in POSITIVE_TERMS):
        return "positive", "high", True
    return "neutral", "unknown", False


def _response_json(response: Any) -> Any:
    if isinstance(response, (dict, list)):
        return response
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    if hasattr(response, "json"):
        return response.json()
    return json.loads(str(response))


def _response_text(response: Any) -> str:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    if hasattr(response, "text"):
        return str(response.text)
    if isinstance(response, bytes):
        return response.decode("utf-8", errors="replace")
    return str(response)


def _default_fetcher(method: str, url: str, **kwargs: Any) -> requests.Response:
    headers = {
        "User-Agent": "xuangu-event-audit/1.0 contact: xuangu.alixjd.com",
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        **(kwargs.pop("headers", {}) or {}),
    }
    return requests.request(method, url, headers=headers, timeout=12, **kwargs)


def _sec_headers() -> dict[str, str]:
    return {
        "User-Agent": os.environ.get("SEC_USER_AGENT", "Xuangu Research admin@alixjd.com"),
        "Accept-Encoding": "gzip, deflate",
    }


def _hkex_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.hkexnews.hk/",
    }


def _event(
    *,
    market: str,
    symbol: str,
    title: str,
    url: str,
    released_at: dt.datetime,
    run_id: str,
    source_document_id: str,
) -> dict[str, Any]:
    registry = SOURCE_REGISTRY[market]
    direction, materiality, eligible = _classify(title)
    released = released_at.astimezone(CN_TZ).isoformat(timespec="seconds")
    return {
        "event_id": f"evt_{_stable_id(market, symbol, source_document_id, released)}",
        "event_type": "official_filing",
        "market": market,
        "symbol": symbol,
        "title": title,
        "source": registry["source"],
        "source_id": registry["source_id"],
        "source_tier": "regulatory" if market == "us" else "exchange",
        "source_document_id": source_document_id,
        "url": url,
        "published_at": released,
        "released_at": released,
        "effective_at": released,
        "scheduled_for": None,
        "direction": direction,
        "materiality": materiality,
        "decision_blocking": direction == "negative" and eligible,
        "decision_eligible": eligible,
        "evidence_status": "verified",
        "ingestion_mode": "automatic",
        "fetch_run_id": run_id,
    }


def parse_cninfo_announcements(
    payload: Mapping[str, Any], symbol: str, run_id: str, *, now: dt.datetime
) -> list[dict[str, Any]]:
    rows = payload.get("announcements") or []
    cutoff = now.astimezone(CN_TZ) - dt.timedelta(days=LOOKBACK_DAYS)
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        released = _moment_from_epoch_millis(row.get("announcementTime"))
        title = html.unescape(re.sub(r"<[^>]+>", "", str(row.get("announcementTitle") or ""))).strip()
        adjunct = str(row.get("adjunctUrl") or "").lstrip("/")
        document_id = str(row.get("announcementId") or adjunct)
        if not released or released < cutoff or released > now or not title or not adjunct or not document_id:
            continue
        result.append(
            _event(
                market="a_share",
                symbol=symbol,
                title=title,
                url=f"https://static.cninfo.com.cn/{adjunct}",
                released_at=released,
                run_id=run_id,
                source_document_id=document_id,
            )
        )
    return result


def parse_hkex_titles(page: str, symbol: str, run_id: str, *, now: dt.datetime) -> list[dict[str, Any]]:
    cutoff = now.astimezone(CN_TZ) - dt.timedelta(days=LOOKBACK_DAYS)
    result = []
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, flags=re.I | re.S):
        href_match = re.search(r'href=["\']([^"\']+\.pdf[^"\']*)', row_html, flags=re.I)
        plain_time = re.sub(r"<[^>]+>", " ", row_html)
        time_match = re.search(
            r"(?:(20\d{2})[/-](\d{2})[/-](\d{2})|(\d{2})[/-](\d{2})[/-](20\d{2}))\s+(\d{2}:\d{2})",
            plain_time,
        )
        if not href_match or not time_match:
            continue
        headline_match = re.search(r'<div\b[^>]*class=["\'][^"\']*headline[^"\']*["\'][^>]*>(.*?)</div>', row_html, flags=re.I | re.S)
        anchor_match = re.search(r'<a\b[^>]*href=["\'][^"\']+\.pdf[^"\']*["\'][^>]*>(.*?)</a>', row_html, flags=re.I | re.S)
        title_html = (headline_match or anchor_match).group(1) if (headline_match or anchor_match) else ""
        title = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", title_html))).strip(" -")
        try:
            if time_match.group(1):
                date_text = f"{time_match.group(1)}-{time_match.group(2)}-{time_match.group(3)}"
            else:
                date_text = f"{time_match.group(6)}-{time_match.group(5)}-{time_match.group(4)}"
            released = dt.datetime.strptime(
                f"{date_text} {time_match.group(7)}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=CN_TZ)
        except ValueError:
            continue
        href = urllib.parse.urljoin("https://www1.hkexnews.hk/", html.unescape(href_match.group(1)))
        if released < cutoff or released > now or not title:
            continue
        result.append(
            _event(
                market="hk",
                symbol=symbol,
                title=title,
                url=href,
                released_at=released,
                run_id=run_id,
                source_document_id=path_document_id(href),
            )
        )
    return result


def path_document_id(url: str) -> str:
    return pathlib_name(urllib.parse.urlparse(url).path) or _stable_id(url)


def pathlib_name(path: str) -> str:
    return str(path or "").rstrip("/").rsplit("/", 1)[-1]


def parse_sec_submissions(
    payload: Mapping[str, Any], symbol: str, cik: int, run_id: str, *, now: dt.datetime
) -> list[dict[str, Any]]:
    recent = ((payload.get("filings") or {}).get("recent") or {}) if isinstance(payload, Mapping) else {}
    fields = ("accessionNumber", "filingDate", "acceptanceDateTime", "form", "primaryDocument")
    arrays = {field: recent.get(field) or [] for field in fields}
    count = min((len(value) for value in arrays.values() if isinstance(value, list)), default=0)
    cutoff = now.astimezone(CN_TZ) - dt.timedelta(days=LOOKBACK_DAYS)
    result = []
    for index in range(count):
        form = str(arrays["form"][index] or "")
        if form not in MATERIAL_FORMS:
            continue
        accepted = _aware(arrays["acceptanceDateTime"][index])
        if accepted is None:
            try:
                accepted = dt.datetime.fromisoformat(str(arrays["filingDate"][index])).replace(tzinfo=CN_TZ)
            except ValueError:
                continue
        if accepted < cutoff or accepted > now:
            continue
        accession = str(arrays["accessionNumber"][index] or "")
        primary = str(arrays["primaryDocument"][index] or "")
        if not accession or not primary:
            continue
        accession_compact = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_compact}/{primary}"
        # Filing metadata alone does not establish positive direction.  It is
        # intentionally neutral until a separately audited content parser can
        # support a directional claim.
        result.append(
            _event(
                market="us",
                symbol=symbol,
                title=f"{form} filing · {primary}",
                url=url,
                released_at=accepted,
                run_id=run_id,
                source_document_id=accession,
            )
        )
    return result


def _finite_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _bounded_score(value: Any, *, scale: float = 1.0) -> float:
    return max(0.0, min(100.0, _finite_float(value) * scale))


def _normalized_symbol(row: Mapping[str, Any], market: str) -> str:
    symbol = str(row.get("code") or row.get("symbol") or "").upper()
    if market == "hk" and symbol and not symbol.endswith(".HK"):
        symbol = f"{symbol.lstrip('0').zfill(4)}.HK"
    return symbol


def _v2_percentile(candidate: Mapping[str, Any]) -> float:
    v2 = candidate.get("v2") or {}
    if not isinstance(v2, Mapping):
        return 0.0
    if v2.get("rank_percentile") is not None:
        return _bounded_score(v2.get("rank_percentile"), scale=100.0)
    if v2.get("rank_score") is not None:
        return _bounded_score(v2.get("rank_score"))
    rank = _finite_float(v2.get("rank"))
    size = _finite_float(v2.get("rank_universe_size"))
    if rank > 0 and size > 1:
        return _bounded_score((size - rank) / (size - 1), scale=100.0)
    return 100.0 if rank == 1 and size == 1 else 0.0


def _risk_reward_score(candidate: Mapping[str, Any]) -> float:
    estimate = (
        candidate.get("estimated_10d_range")
        or candidate.get("estimated_2w_range")
        or candidate.get("estimated_2d_range")
        or {}
    )
    if not isinstance(estimate, Mapping):
        return 0.0
    upside = max(0.0, _finite_float(estimate.get("high_pct")))
    downside = abs(min(0.0, _finite_float(estimate.get("low_pct"))))
    if upside <= 0:
        return 0.0
    ratio = upside / downside if downside > 0 else 3.0
    # A 1.2x upside/downside ratio is useful but not perfect.  Cap unusually
    # optimistic ranges so this pre-scan cannot be dominated by one estimate.
    return _bounded_score(ratio, scale=40.0)


def _event_scan_priority(candidate: Mapping[str, Any], market_action: str) -> tuple[float, float, float, float, float]:
    """Rank event-scan candidates without consulting any Shadow probability."""

    legacy = candidate.get("legacy") or {}
    legacy_score = _bounded_score(
        legacy.get("recommendation_degree")
        if isinstance(legacy, Mapping) and legacy.get("recommendation_degree") is not None
        else candidate.get("recommendation_degree", candidate.get("confidence"))
    )
    v2_score = _v2_percentile(candidate)
    quality = candidate.get("data_quality") or {}
    quality_score = _bounded_score(quality.get("score") if isinstance(quality, Mapping) else None)
    reward_risk = _risk_reward_score(candidate)
    market_action_score = 100.0 if str(market_action).upper() == "BUY_CANDIDATE" else 0.0
    priority = (
        legacy_score * 0.30
        + v2_score * 0.30
        + quality_score * 0.20
        + reward_risk * 0.15
        + market_action_score * 0.05
    )
    risk_items = candidate.get("risk_items") or []
    hard_risks = sum(
        1
        for item in risk_items
        if isinstance(item, Mapping) and str(item.get("severity") or "").lower() == "hard"
    )
    blocked = str(candidate.get("execution_state") or "").upper() in {"BLOCK", "BLOCKED"} or any(
        isinstance(gate, Mapping) and str(gate.get("status") or "").upper() == "BLOCK"
        for gate in (candidate.get("decision_gates") or [])
    )
    priority -= hard_risks * 15.0 + (30.0 if blocked else 0.0)
    # The remaining fields make ties deterministic and keep a genuine Legacy
    # recommendation ahead of an equally scored technical-only row.
    legacy_complete = not (
        candidate.get("legacy_complete") is False
        or candidate.get("score_tier") == "technical_only"
        or (isinstance(legacy, Mapping) and legacy.get("complete") is False)
    )
    return (priority, float(legacy_complete), legacy_score, v2_score, quality_score)


def _candidate_symbols(snapshot: Mapping[str, Any], market: str, limit: int) -> list[str]:
    section = ((snapshot.get("markets") or {}).get(market) or {})
    decision = section.get("decision") or {}
    decision_rows = [
        decision.get("primary"),
        decision.get("blocked_candidate"),
        *(decision.get("watchlist") or []),
    ]
    production = snapshot.get("production_decision") or {}
    production_primary = production.get("primary") if isinstance(production, Mapping) else None
    if isinstance(production_primary, Mapping) and str(production_primary.get("market") or "") == market:
        decision_rows.insert(0, production_primary)
    rows = [*(section.get("_candidate_pool") or []), *decision_rows]
    candidates: dict[str, tuple[tuple[float, float, float, float, float], int, Mapping[str, Any]]] = {}
    mandatory: set[str] = set()
    market_action = str(decision.get("action") or "")
    decision_row_ids = {id(row) for row in decision_rows if isinstance(row, Mapping)}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        symbol = _normalized_symbol(row, market)
        if not symbol:
            continue
        priority = _event_scan_priority(row, market_action)
        previous = candidates.get(symbol)
        if previous is None or priority > previous[0]:
            candidates[symbol] = (priority, index, row)
        if id(row) in decision_row_ids:
            mandatory.add(symbol)

    bounded_limit = max(1, min(30, int(limit)))
    # The normal decision contract publishes at most primary + blocked + eight
    # watchlist rows.  Reserve all of them even if their ensemble score is low;
    # a malformed oversized decision can never push collection above 30.
    selection_limit = min(30, max(bounded_limit, len(mandatory)))
    ordered = sorted(
        candidates,
        key=lambda symbol: (
            *candidates[symbol][0],
            -candidates[symbol][1],
            symbol,
        ),
        reverse=True,
    )
    selected = set(list(mandatory)[:selection_limit])
    for symbol in ordered:
        if len(selected) >= selection_limit:
            break
        selected.add(symbol)
    return [symbol for symbol in ordered if symbol in selected][:selection_limit]


def _collect_a_share(symbols: list[str], run_id: str, now: dt.datetime, fetch: Callable[..., Any]) -> list[dict]:
    stock_payload = _response_json(fetch("GET", "https://static.cninfo.com.cn/new/data/szse_stock.json"))
    rows = stock_payload.get("stockList") or stock_payload.get("stock_list") or []
    mapping = {str(row.get("code") or row.get("secCode")): str(row.get("orgId") or "") for row in rows if isinstance(row, Mapping)}
    def collect_symbol(symbol: str) -> list[dict]:
        code = symbol.split(".")[0]
        org_id = mapping.get(code)
        if not org_id:
            raise EventPipelineError(f"CNINFO organization mapping missing for {code}")
        payload = _response_json(
            fetch(
                "POST",
                "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                data={
                    "stock": f"{code},{org_id}",
                    "tabName": "fulltext",
                    "pageSize": "30",
                    "pageNum": "1",
                    "column": "sse" if code.startswith("6") else "szse",
                    "category": "",
                    "seDate": "",
                    "searchkey": "",
                    "secid": "",
                    "sortName": "",
                    "sortType": "",
                    "isHLtitle": "true",
                },
                headers={"Referer": "https://www.cninfo.com.cn/"},
            )
        )
        return parse_cninfo_announcements(payload, code, run_id, now=now)
    return _parallel_collect(symbols, collect_symbol)


def _collect_hk(symbols: list[str], run_id: str, now: dt.datetime, fetch: Callable[..., Any]) -> list[dict]:
    def collect_symbol(symbol: str) -> list[dict]:
        code = symbol.replace(".HK", "").lstrip("0") or "0"
        prefix = _response_text(
            fetch(
                "GET",
                "https://www1.hkexnews.hk/search/prefix.do",
                params={"callback": "callback", "lang": "EN", "type": "A", "name": code.zfill(5), "market": "SEHK"},
                headers=_hkex_headers(),
            )
        )
        match = re.search(r'["\']?stockId["\']?\s*:\s*["\']?(\d+)', prefix)
        if not match:
            raise EventPipelineError(f"HKEX stockId mapping missing for {symbol}")
        page = _response_text(
            fetch(
                "GET",
                "https://www1.hkexnews.hk/search/titlesearch.xhtml",
                params={"lang": "en", "category": "0", "market": "SEHK", "stockId": match.group(1)},
                headers=_hkex_headers(),
            )
        )
        return parse_hkex_titles(page, symbol, run_id, now=now)
    return _parallel_collect(symbols, collect_symbol)


def _collect_us(symbols: list[str], run_id: str, now: dt.datetime, fetch: Callable[..., Any]) -> list[dict]:
    tickers = _response_json(fetch("GET", "https://www.sec.gov/files/company_tickers.json", headers=_sec_headers()))
    mapping = {
        str(row.get("ticker") or "").upper(): int(row.get("cik_str"))
        for row in (tickers.values() if isinstance(tickers, Mapping) else [])
        if isinstance(row, Mapping) and row.get("ticker") and row.get("cik_str") is not None
    }
    def collect_symbol(symbol: str) -> list[dict]:
        ticker = symbol.upper()
        cik = mapping.get(ticker)
        if cik is None:
            raise EventPipelineError(f"SEC CIK mapping missing for {ticker}")
        payload = _response_json(
            fetch("GET", f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_sec_headers())
        )
        return parse_sec_submissions(payload, ticker, cik, run_id, now=now)
    return _parallel_collect(symbols, collect_symbol)


def _parallel_collect(symbols: list[str], collector: Callable[[str], list[dict]]) -> list[dict]:
    if not symbols:
        return []
    events: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(symbols))) as executor:
        futures = {executor.submit(collector, symbol): symbol for symbol in symbols}
        for future in concurrent.futures.as_completed(futures):
            events.extend(future.result())
    return events


def collect_for_snapshot(
    snapshot: Mapping[str, Any],
    run_id: str,
    *,
    now: dt.datetime | None = None,
    fetcher: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not run_id:
        raise EventPipelineError("run_id is required")
    now = (now or dt.datetime.now(CN_TZ)).astimezone(CN_TZ)
    fetch = fetcher or _default_fetcher
    limit = max(1, min(30, int(os.environ.get("EVENT_SCAN_CANDIDATES_PER_MARKET", "16"))))
    symbols = {market: _candidate_symbols(snapshot, market, limit) for market in SOURCE_REGISTRY}
    collectors = {"a_share": _collect_a_share, "hk": _collect_hk, "us": _collect_us}
    items: list[dict] = []
    source_manifest = []
    successful_markets = []
    for market, collector in collectors.items():
        entry = {
            "market": market,
            "source_id": SOURCE_REGISTRY[market]["source_id"],
            "source": SOURCE_REGISTRY[market]["source"],
            "requested_symbol_count": len(symbols[market]),
            "scanned_symbol_count": 0,
            "official_hosts": list(SOURCE_REGISTRY[market]["hosts"]),
            "retrieved_at": now.isoformat(timespec="seconds"),
            "status": "ERROR",
            "error_code": None,
        }
        try:
            collected = collector(symbols[market], run_id, now, fetch)
            items.extend(collected)
            entry.update({"status": "SUCCESS", "event_count": len(collected), "scanned_symbol_count": len(symbols[market])})
            successful_markets.append(market)
        except Exception as exc:  # Fail closed per source while preserving the other audits.
            entry.update({"error_code": type(exc).__name__, "event_count": 0})
        source_manifest.append(entry)
    unique = {item["event_id"]: item for item in items}
    items = sorted(unique.values(), key=lambda item: str(item.get("released_at") or ""), reverse=True)
    all_success = set(successful_markets) == set(SOURCE_REGISTRY)
    status = "READY_EMPTY" if all_success and not items else "READY" if all_success else "PARTIAL"
    pipeline = {
        "contract_version": "official-event-pipeline-v1",
        "run_id": run_id,
        "status": status,
        "scanned_at": now.isoformat(timespec="seconds"),
        "markets": successful_markets,
        "markets_attempted": list(SOURCE_REGISTRY),
        "scanned_symbols": symbols,
        "source_manifest": source_manifest,
        "lookback_days": LOOKBACK_DAYS,
    }
    return {
        "generated_at": snapshot.get("generated_at"),
        "pipeline": pipeline,
        "items": items,
        "stats": {
            "automatic_external": len(items),
            "decision_eligible": sum(item.get("decision_eligible") is True for item in items),
            "positive": sum(item.get("direction") == "positive" for item in items),
            "negative": sum(item.get("direction") == "negative" for item in items),
            "neutral": sum(item.get("direction") == "neutral" for item in items),
        },
    }


def pipeline_complete(value: Mapping[str, Any]) -> bool:
    pipeline = ((value.get("events") or {}).get("pipeline") or value.get("pipeline") or value)
    if not isinstance(pipeline, Mapping):
        return False
    manifest = pipeline.get("source_manifest")
    return bool(
        pipeline.get("contract_version") == "official-event-pipeline-v1"
        and pipeline.get("status") in {"READY", "READY_EMPTY"}
        and isinstance(pipeline.get("run_id"), str)
        and pipeline.get("run_id")
        and set(pipeline.get("markets") or []) == set(SOURCE_REGISTRY)
        and isinstance(pipeline.get("scanned_symbols"), Mapping)
        and set(pipeline.get("scanned_symbols") or {}) == set(SOURCE_REGISTRY)
        and isinstance(manifest, list)
        and len(manifest) == 3
        and all(isinstance(row, Mapping) and row.get("status") == "SUCCESS" for row in manifest)
    )


def pipeline_market_complete(value: Mapping[str, Any], market: str) -> bool:
    """Return whether one market's official source completed independently.

    The strict cross-market decision still uses :func:`pipeline_complete`.
    This narrower check prevents an SEC outage from erasing an otherwise
    auditable HKEX event (and vice versa) in the market-isolated rule track.
    """

    pipeline = ((value.get("events") or {}).get("pipeline") or value.get("pipeline") or value)
    if not isinstance(pipeline, Mapping) or market not in SOURCE_REGISTRY:
        return False
    manifest = pipeline.get("source_manifest")
    scanned = pipeline.get("scanned_symbols")
    source_id = SOURCE_REGISTRY[market]["source_id"]
    return bool(
        pipeline.get("contract_version") == "official-event-pipeline-v1"
        and isinstance(pipeline.get("run_id"), str)
        and pipeline.get("run_id")
        and market in set(pipeline.get("markets") or [])
        and isinstance(scanned, Mapping)
        and isinstance(scanned.get(market), list)
        and isinstance(manifest, list)
        and any(
            isinstance(row, Mapping)
            and row.get("source_id") == source_id
            and row.get("status") == "SUCCESS"
            for row in manifest
        )
    )


def event_is_auditable(
    item: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    market: str | None = None,
    symbol: str | None = None,
) -> bool:
    pipeline = ((snapshot.get("events") or {}).get("pipeline") or {})
    event_market = str(item.get("market") or "")
    event_symbol = str(item.get("symbol") or "")
    registry = SOURCE_REGISTRY.get(event_market)
    if not registry or not pipeline_market_complete(snapshot, event_market):
        return False
    host = (urllib.parse.urlparse(str(item.get("url") or "")).hostname or "").lower()
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in registry["hosts"]):
        return False
    scanned = (pipeline.get("scanned_symbols") or {}).get(event_market) or []
    source_ok = any(
        row.get("source_id") == item.get("source_id") and row.get("status") == "SUCCESS"
        for row in (pipeline.get("source_manifest") or [])
        if isinstance(row, Mapping)
    )
    generated = _aware(snapshot.get("generated_at"))
    released = _aware(item.get("released_at") or item.get("published_at"))
    effective = _aware(item.get("effective_at"))
    if not generated or not released or not effective:
        return False
    return bool(
        item.get("fetch_run_id") == pipeline.get("run_id")
        and item.get("evidence_status") == "verified"
        and item.get("ingestion_mode") == "automatic"
        and item.get("source_document_id")
        and source_ok
        and event_symbol.lower() in {str(value).lower() for value in scanned}
        and (market is None or event_market == market)
        and (symbol is None or event_symbol.lower() == str(symbol).lower())
        and generated - dt.timedelta(days=LOOKBACK_DAYS) <= released <= generated
        and generated - dt.timedelta(days=LOOKBACK_DAYS) <= effective
    )


__all__ = [
    "EventPipelineError",
    "collect_for_snapshot",
    "event_is_auditable",
    "parse_cninfo_announcements",
    "parse_hkex_titles",
    "parse_sec_submissions",
    "pipeline_complete",
    "pipeline_market_complete",
]

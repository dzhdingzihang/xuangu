"""Bounded, cacheable public classification evidence for new cloud snapshots.

Eastmoney's ``f100`` is its own industry taxonomy for A/HK and a broader
sector taxonomy for US equities. It is not GICS or a point-in-time history.
Only explicit provider fields are used; company names and themes are never
classified. Inject ``fetcher(secids) -> raw Eastmoney JSON`` for offline tests.
This module has no OpenD, browser, credential or local service dependency.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
import concurrent.futures
import copy
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode

import requests


CACHE_VERSION = "sector-metadata-v1"
PROVIDER = "eastmoney_public_classification"
PROVIDER_URL = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
MARKETS = ("a_share", "hk", "us")
BATCH_SIZE = 100
MAX_REQUESTS = 20
MAX_WORKERS = 4
REQUEST_TIMEOUT = (3.05, 10)
FRESH_DAYS = 7
MAX_STALE_DAYS = 90
FAILURE_TTL_HOURS = 6
MAX_CACHE_RECORDS = 12000
_MISSING_LABELS = {"", "-", "--", "n/a", "na", "none", "null", "unknown", "0", "未知", "其他", "未分类"}


def _aware(value) -> dt.datetime | None:
    try:
        moment = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment.astimezone(dt.timezone.utc) if moment.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _label(value) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("name")
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.lower() in _MISSING_LABELS or len(value) > 100 or any(char in value for char in "<>\n\r"):
        return None
    return value


def parse_sector_record(record: Mapping, *, source: str, retrieved_at=None,
                        source_url: str | None = None, taxonomy: str | None = None,
                        source_field: str | None = None) -> dict | None:
    """Read explicit labels only, without deriving membership from names."""
    if not isinstance(record, Mapping):
        return None
    for field in ("industry", "sector"):
        value = _label(record.get(field))
        if value:
            return {"name": value, "source": source, "source_url": source_url,
                    "source_field": source_field or field, "taxonomy": taxonomy or source,
                    "granularity": field, "retrieved_at": retrieved_at}
    return None


def _code(value, market: str) -> str | None:
    value = str(value or "").strip().upper()
    if market == "hk":
        match = re.fullmatch(r"(\d{1,5})(?:\.HK)?", value)
        return f"{int(match[1]):04d}.HK" if match and 0 < int(match[1]) <= 99999 else None
    if market == "a_share":
        match = re.fullmatch(r"(?:SH|SZ|BJ)?(\d{6})(?:\.(?:SS|SZ|SH|BJ))?", value)
        return match[1] if match else None
    if market == "us":
        value = value.replace("_", "-").replace(".", "-")
        return value if re.fullmatch(r"[A-Z][A-Z0-9-]{0,14}", value) else None
    return None


def _index(rows, market: str) -> dict[str, dict]:
    pairs = rows.items() if isinstance(rows, Mapping) else (
        (row.get("code") or row.get("symbol"), row) for row in (rows or []) if isinstance(row, Mapping))
    result = {}
    for symbol, row in pairs:
        code = _code(symbol, market)
        if code and isinstance(row, Mapping):
            result[code] = copy.deepcopy(dict(row))
    return result


def _secids(code: str, market: str, candidate: Mapping) -> list[str]:
    if market == "a_share":
        # Beijing's 4/8/920xxx codes route through 0; only Shanghai 6/9(legacy)
        # codes use 1. New 920xxx codes must not be mistaken for Shanghai.
        venue = 1 if code.startswith("6") or (code.startswith("9") and not code.startswith("92")) else 0
        return [f"{venue}.{code}"]
    if market == "hk":
        return [f"116.{int(code.split('.')[0]):05d}"]
    metrics = candidate.get("recall_metrics") or {}
    metrics = metrics if isinstance(metrics, Mapping) else {}
    exchange = str(candidate.get("exchange") or metrics.get("exchange") or candidate.get("market_segment") or "").upper()
    venue = {"NASDAQ": 105, "NYSE": 106, "AMEX": 107, "NYSE AMERICAN": 107}.get(exchange)
    # Root canonicalizes provider class-share separators to hyphens.
    symbol = code.replace("-", "_")
    return [f"{item}.{symbol}" for item in ([venue] if venue else [105, 106, 107])]


def _fetch_batch(secids: list[str]) -> dict:
    response = requests.get(PROVIDER_URL,
                            params={"secids": ",".join(secids), "fields": "f12,f13,f100", "fltt": 2, "invt": 2},
                            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
                            timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _provider_records(payload, allowed: set[str], timestamp: str) -> dict[str, dict]:
    if not isinstance(payload, Mapping) or payload.get("rc") != 0:
        raise ValueError("invalid provider status")
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("missing provider data")
    rows = data.get("diff")
    if rows is None and data.get("total") == 0:
        rows = []
    if isinstance(rows, Mapping):
        rows = list(rows.values())
    if not isinstance(rows, list):
        raise ValueError("invalid provider rows")
    result = {}
    conflicts = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        venue = row.get("f13")
        if isinstance(venue, bool) or str(venue) not in {"0", "1", "105", "106", "107", "116"}:
            continue
        symbol = str(row.get("f12") or "").upper()
        secid = f"{venue}.{symbol}"
        if secid not in allowed:
            continue
        market = "a_share" if int(venue) in (0, 1) else "hk" if int(venue) == 116 else "us"
        code = _code(symbol, market)
        granularity = "sector" if market == "us" else "industry"
        record = parse_sector_record({granularity: row.get("f100")}, source=PROVIDER,
                                     retrieved_at=timestamp, source_field="f100",
                                     source_url=PROVIDER_URL + "?" + urlencode({"secids": secid, "fields": "f12,f13,f100"}),
                                     taxonomy="eastmoney_" + granularity)
        if not code:
            continue
        # Retain the returned identity even when its classification is absent:
        # a ticker present on two probed venues must remain ambiguous.
        record = record or {"name": None}
        record.update({"market": market, "code": code, "provider_secid": secid})
        if secid in result and result[secid] != record:
            conflicts.add(secid)
        result[secid] = record
    for secid in conflicts:
        result[secid] = {**result[secid], "name": None}
    return result


def _load_cache(path: Path) -> tuple[dict, str]:
    empty = {"version": CACHE_VERSION, "records": {}, "failures": {}}
    try:
        if path.stat().st_size > 20_000_000:
            return empty, "INVALID"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION
                or not isinstance(payload.get("records"), dict) or not isinstance(payload.get("failures"), dict)):
            return empty, "INVALID"
        return payload, "LOADED"
    except FileNotFoundError:
        return empty, "ABSENT"
    except (OSError, ValueError, UnicodeError):
        return empty, "INVALID"


def _write_cache(path: Path, cache: dict) -> str:
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as output:
            temporary = output.name
            json.dump(cache, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        return "SAVED"
    except (OSError, ValueError, TypeError):
        return "WRITE_FAILED"
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _cached_record(record, market: str, code: str, secids: list[str], now: dt.datetime) -> dict | None:
    if not isinstance(record, Mapping):
        return None
    retrieved = _aware(record.get("retrieved_at"))
    granularity = "sector" if market == "us" else "industry"
    if (record.get("source") != PROVIDER or record.get("source_field") != "f100"
            or record.get("market") != market or record.get("code") != code
            or record.get("granularity") != granularity or record.get("taxonomy") != "eastmoney_" + granularity
            or not str(record.get("source_url") or "").startswith(PROVIDER_URL + "?")
            or record.get("provider_secid") not in secids or not _label(record.get("name")) or not retrieved):
        return None
    age = (now - retrieved).total_seconds() / 86400
    if age < 0 or age > MAX_STALE_DAYS:
        return None
    return {**record, "status": "FRESH" if age <= FRESH_DAYS else "STALE",
            "stale": age > FRESH_DAYS, "age_days": round(age, 4)}


def _recent_failure(failure, now: dt.datetime) -> bool:
    stamp = _aware(failure.get("attempted_at")) if isinstance(failure, Mapping) else None
    return stamp is not None and 0 <= (now - stamp).total_seconds() < FAILURE_TTL_HOURS * 3600


def enrich_sector_metadata(metadata_by_market, candidates_by_market, *, now, cache_path,
                           fetcher: Callable[[list[str]], Mapping] | None = None) -> tuple[dict, dict]:
    """Return copied metadata plus auditable coverage; call only for new snapshots.

    Inputs accept either symbol-keyed dictionaries or lists of candidate rows.
    Fresh successes live for seven days; failures independently cool down for
    six hours. Previously verified labels remain explicitly STALE for at most
    ninety days after retrieval. All classifications are current-reference
    metadata, never evidence for rebuilding historical decisions.
    """
    anchor = _aware(now)
    if anchor is None:
        raise ValueError("now must be a timezone-aware timestamp")
    timestamp = anchor.isoformat()
    path = Path(cache_path)
    cache, read_status = _load_cache(path)
    records = cache["records"]
    failures = {key: value for key, value in cache["failures"].items() if _recent_failure(value, anchor)}
    metadata = {market: _index((metadata_by_market or {}).get(market), market) for market in MARKETS}
    candidates = {market: _index((candidates_by_market or {}).get(market), market) for market in MARKETS}
    diagnostics = {"version": CACHE_VERSION, "provider": PROVIDER, "generated_at": timestamp,
                   "status": "MISSING", "cache_read_status": read_status, "request_count": 0,
                   "request_limit": MAX_REQUESTS, "batch_size": BATCH_SIZE, "max_workers": MAX_WORKERS,
                   "fresh_ttl_days": FRESH_DAYS, "stale_fallback_max_days": MAX_STALE_DAYS,
                   "failure_ttl_hours": FAILURE_TTL_HOURS, "cache_hit_count": 0,
                   "negative_cache_hit_count": 0, "deferred_count": 0, "markets": {},
                   "limitation": "Current provider taxonomy; US fields are broad sectors. Stale and curated fallback labels are not fresh industry evidence."}
    refresh_states = {}
    batches = []
    active_batch = []
    active_size = 0
    for market in MARKETS:
        for code, candidate in candidates[market].items():
            key = f"{market}:{code}"
            row = metadata[market].setdefault(code, {})
            ids = _secids(code, market, {**row, **candidate})
            existing = _cached_record(records.get(key), market, code, ids, anchor)
            if existing and existing["status"] == "FRESH":
                diagnostics["cache_hit_count"] += 1
                refresh_states[key] = "CACHE_FRESH"
                continue
            if _recent_failure(failures.get(key), anchor):
                diagnostics["negative_cache_hit_count"] += 1
                refresh_states[key] = "FAILURE_COOLDOWN"
                continue
            if active_batch and active_size + len(ids) > BATCH_SIZE:
                batches.append(active_batch)
                active_batch, active_size = [], 0
            active_batch.append((market, code, ids))
            active_size += len(ids)
    if active_batch:
        batches.append(active_batch)
    for batch in batches[MAX_REQUESTS:]:
        for market, code, _ in batch:
            refresh_states[f"{market}:{code}"] = "DEFERRED_BUDGET"
            diagnostics["deferred_count"] += 1
    batches = batches[:MAX_REQUESTS]
    diagnostics["request_count"] = len(batches)
    fetch = fetcher or _fetch_batch
    failure_reasons = Counter()

    def run_batch(batch):
        ids = [secid for _, _, group in batch for secid in group]
        return _provider_records(fetch(ids), set(ids), timestamp)

    if batches:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(run_batch, batch): batch for batch in batches}
            for future in concurrent.futures.as_completed(futures):
                batch = futures[future]
                try:
                    found = future.result()
                    failed = False
                except Exception:
                    found, failed = {}, True
                for market, code, ids in batch:
                    key = f"{market}:{code}"
                    matches = [found[value] for value in ids if value in found
                               and found[value]["market"] == market and found[value]["code"] == code]
                    if len(matches) == 1 and _label(matches[0].get("name")) and not failed:
                        records[key] = matches[0]
                        failures.pop(key, None)
                        refresh_states[key] = "FETCHED"
                    else:
                        reason = "PROVIDER_ERROR" if failed else "AMBIGUOUS_PROVIDER_IDENTITY" if len(matches) > 1 else "NO_CLASSIFICATION"
                        failures[key] = {"attempted_at": timestamp, "reason": reason}
                        refresh_states[key] = reason
                        failure_reasons[reason] += 1
    totals = Counter()
    for market in MARKETS:
        counts = Counter()
        for code, candidate in candidates[market].items():
            key = f"{market}:{code}"
            row = metadata[market][code]
            ids = _secids(code, market, {**row, **candidate})
            evidence = _cached_record(records.get(key), market, code, ids, anchor)
            # Do not leave a former provider label in plain industry/sector fields
            # after its evidence expires or its exchange identity changes.
            prior_evidence = row.get("sector_metadata")
            if isinstance(prior_evidence, Mapping) and prior_evidence.get("source") == PROVIDER:
                row.pop("industry", None)
                row.pop("sector", None)
            if evidence:
                row[evidence["granularity"]] = evidence["name"]
                counts[evidence["status"].lower() + "_count"] += 1
            else:
                evidence = {"name": None, "source": None, "source_url": None, "retrieved_at": None,
                            "status": "MISSING", "stale": False, "age_days": None}
                counts["missing_count"] += 1
                themes = row.get("themes") or row.get("theme_tags") or []
                themes = [themes] if isinstance(themes, str) else themes if isinstance(themes, list) else []
                labels = [label for item in themes if (label := _label(item))]
                if labels:
                    evidence["fallback"] = {"status": "APPROXIMATE", "source": "reference_metadata.themes",
                                            "labels": labels, "retrieved_at": None}
                    counts["curated_fallback_count"] += 1
            evidence["refresh_status"] = refresh_states.get(key, "NOT_REQUESTED")
            if key in failures:
                evidence["last_attempt_at"] = failures[key]["attempted_at"]
                evidence["last_error"] = failures[key].get("reason")
            row["sector_metadata"] = evidence
        total = len(candidates[market])
        summary = {field: counts[field] for field in ("fresh_count", "stale_count", "missing_count", "curated_fallback_count")}
        summary.update({"candidate_count": total, "coverage_pct": round(100 * counts["fresh_count"] / total, 2) if total else 0.0,
                        "taxonomy": "eastmoney_sector" if market == "us" else "eastmoney_industry"})
        diagnostics["markets"][market] = summary
        totals.update({**counts, "candidate_count": total})
    diagnostics.update({field: totals[field] for field in ("candidate_count", "fresh_count", "stale_count", "missing_count", "curated_fallback_count")})
    total = totals["candidate_count"]
    diagnostics["coverage_pct"] = round(100 * totals["fresh_count"] / total, 2) if total else 0.0
    diagnostics["status"] = "COMPLETE" if total and totals["fresh_count"] == total else "PARTIAL" if totals["fresh_count"] or totals["stale_count"] else "MISSING"
    diagnostics["failure_reasons"] = dict(sorted(failure_reasons.items()))
    # Bound disk growth across changing universes. A provider failure never
    # replaces a good record; retention pruning is independent of refresh.
    retained = {key: value for key, value in records.items() if isinstance(value, Mapping)
                and (stamp := _aware(value.get("retrieved_at"))) is not None
                and 0 <= (anchor - stamp).total_seconds() <= 365 * 86400}
    retained = dict(sorted(retained.items(), key=lambda item: item[1]["retrieved_at"], reverse=True)[:MAX_CACHE_RECORDS])
    failures = dict(sorted(failures.items(), key=lambda item: item[1]["attempted_at"], reverse=True)[:MAX_CACHE_RECORDS])
    cache = {"version": CACHE_VERSION, "updated_at": timestamp, "records": retained, "failures": failures}
    diagnostics["cache_write_status"] = _write_cache(path, cache)
    return metadata, diagnostics

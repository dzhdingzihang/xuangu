"""Auditable security identity checks; absence of ETF evidence is not stock verification."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re

VERSION = "security-identity-v1"
DIRECTORY_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
EXCLUDED_TYPES = {"ETF", "ETN", "FUND", "MUTUALFUND", "INDEX", "WARRANT", "RIGHT", "UNIT", "PREFERRED", "LEVERAGED_PRODUCT", "TEST_ISSUE"}


def blocked_security_name(name: str, market: str) -> bool:
    text = str(name or "").strip().upper()
    if market == "hk":
        return any(token in text for token in ("ETF", "基金", "债", "权证", "牛证", "熊证", "认购", "认沽", "优先股", "两倍", "反向"))
    if any(token in text for token in ("空白支票", "交易所交易基金", "杠杆", "反向")):
        return True
    if re.search(r"\b(?:ETF|ETN|SPAC|WARRANTS?|RIGHTS?|UNITS?|PREFERRED|PFD|FUND)\b", text):
        return True
    if re.search(r"\b(?:[1234](?:\.5)?X\s+(?:LONG|SHORT|BULL|BEAR|INVERSE)|(?:LEVERAGED?|INVERSE)\s+(?:DAILY|SHARES)|DAILY\s+-?[1234]X)\b", text):
        return True
    # Sponsor identities alone are not a blanket ban on the sponsor's own equity.
    sponsors = ("ISHARES", "PROSHARES", "DIREXION", "SPDR", "VANECK", "GRAYSCALE", "GLOBAL X ", "GRANITESHARES", "LEVERAGE SHARES", "GUGGENHEIM STRATEGIC OPPORTUNITIES")
    if any(token in text for token in sponsors):
        return True
    if "WISDOMTREE" in text and not re.fullmatch(r"WISDOMTREE\s+(?:INC\.?|INCORPORATED)(?:\s*-\s*COMMON STOCK)?", text):
        return True
    trust_product = "TRUST" in text and any(token in text for token in ("BITCOIN", "ETHEREUM", "ETHER", "CRYPTO", "PHYSICAL SILVER", "PHYSICAL GOLD", "QQQ"))
    return "ACQUISITION CORP" in text or "ACQUISITION CO" in text or trust_product


def assess_security(candidate: dict, market: str) -> dict:
    symbol = str(candidate.get("symbol") or candidate.get("code") or "").upper()
    evidence = []
    reasons = []
    instrument_type = None
    fresh_provider_evidence = False
    anchor_value = candidate.get("security_as_of") or candidate.get("observed_at") or (candidate.get("realtime") or {}).get("fetched_at")
    try:
        anchor = dt.datetime.fromisoformat(str(anchor_value).replace("Z", "+00:00"))
        if anchor.tzinfo is None:
            anchor = None
    except (ValueError, TypeError):
        anchor = None
    for item in candidate.get("security_type_evidence") or []:
        if not isinstance(item, dict) or str(item.get("symbol") or "").upper() != symbol:
            continue
        source, field, raw = item.get("source"), item.get("field"), str(item.get("raw_value") or "").upper()
        if not item.get("retrieved_at"):
            continue
        try:
            retrieved = dt.datetime.fromisoformat(str(item["retrieved_at"]).replace("Z", "+00:00"))
            if retrieved.tzinfo is None:
                continue
        except (ValueError, TypeError):
            continue
        observed_type = None
        if source == "nasdaq_symbol_directory" and field == "ETF":
            if raw == "Y":
                observed_type = "ETF"
            elif raw == "N" and item.get("instrument_type") in {"COMMON_STOCK", "ADR"}:
                observed_type = item["instrument_type"]
        elif source == "nasdaq_symbol_directory" and field == "Test Issue" and raw == "Y":
            observed_type = "TEST_ISSUE"
        elif source == "yahoo_chart_meta" and field == "instrumentType":
            observed_type = {"EQUITY": "EQUITY", "ETF": "ETF", "MUTUALFUND": "MUTUALFUND", "INDEX": "INDEX"}.get(raw)
        if not observed_type:
            continue
        if item not in evidence:
            evidence.append(dict(item))
        age = (anchor - retrieved).total_seconds() if anchor else None
        fresh = age is not None and -300 <= age <= 7 * 86400
        fresh_provider_evidence = fresh_provider_evidence or fresh
        if observed_type in EXCLUDED_TYPES:
            reasons.append("PROVIDER_NON_STOCK_TYPE")
            instrument_type = observed_type
        elif fresh and instrument_type not in EXCLUDED_TYPES:
            instrument_type = observed_type
    # Unproven positive labels never certify equity. Explicit negative labels
    # still fail closed, including cached/upstream records without provenance.
    raw_type = str(candidate.get("security_type") or candidate.get("instrument_type") or "").upper()
    if raw_type in EXCLUDED_TYPES:
        reasons.append("UNVERIFIED_NON_STOCK_TYPE")
        instrument_type = raw_type
    names = [candidate.get(key) for key in ("name", "english_name", "raw_name", "source_category")]
    names.extend(item.get("security_name") for item in evidence)
    if any(blocked_security_name(name, market) for name in names if name):
        reasons.append("NON_STOCK_NAME_EVIDENCE")
        if instrument_type not in EXCLUDED_TYPES:
            instrument_type = "NON_STOCK_PRODUCT"
    excluded = bool(reasons)
    verified = fresh_provider_evidence and instrument_type is not None
    return {"contract_version": VERSION, "status": "EXCLUDED" if excluded else "PROVIDER_CLASSIFIED" if verified else "UNVERIFIED", "eligible": not excluded, "instrument_type": instrument_type, "verified": verified, "evidence": evidence, "reasons": sorted(set(reasons)), "freshness_reference_at": anchor.isoformat() if anchor else None}


def parse_nasdaq_directory(text: str, *, retrieved_at: str) -> dict[str, list[dict]]:
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    if not {"Symbol", "Security Name", "ETF", "Test Issue"}.issubset(reader.fieldnames or []):
        raise ValueError("Nasdaq directory header is invalid")
    result = {}
    for row in reader:
        symbol = str(row.get("Symbol") or "").strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
            continue
        name = str(row.get("Security Name") or "")
        upper = name.upper()
        stock_type = "ADR" if "AMERICAN DEPOSITARY" in upper else "COMMON_STOCK" if re.search(r"\b(?:COMMON STOCK|ORDINARY SHARES|COMMON SHARES)\b", upper) else None
        entries = [{"symbol": symbol, "source": "nasdaq_symbol_directory", "source_url": DIRECTORY_URL, "field": "ETF", "raw_value": row.get("ETF"), "security_name": name, "instrument_type": stock_type, "retrieved_at": retrieved_at}]
        if row.get("Test Issue") == "Y":
            entries.append({**entries[0], "field": "Test Issue", "raw_value": "Y", "instrument_type": "TEST_ISSUE"})
        if symbol in result:
            raise ValueError("Nasdaq directory contains duplicate security identities")
        result[symbol] = entries
    return result

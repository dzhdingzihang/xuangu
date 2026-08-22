#!/usr/bin/env python3
"""Authenticated Futu OpenD quote gateway for the Cloudflare Worker.

The Worker cannot connect to a local OpenD TCP port directly.  This tiny HTTP
service is intended to sit next to OpenD and be published through a Cloudflare
Tunnel.  It deliberately exposes only a bounded, read-only snapshot endpoint.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import math
import os
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from zoneinfo import ZoneInfo


CN_TZ = ZoneInfo("Asia/Shanghai")
NY_TZ = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
MAX_SYMBOLS = 50
ACTIVE_FRESH_SECONDS = 120
CACHE_SECONDS = 5
MARKET_ALIASES = {
    "a": "a_share",
    "ashare": "a_share",
    "a_share": "a_share",
    "cn": "a_share",
    "hk": "hk",
    "hongkong": "hk",
    "us": "us",
}
ACTIVE_STATE_TOKENS = (
    "MORNING",
    "AFTERNOON",
    "FUTURE_DAY_OPEN",
    "NIGHT_OPEN",
    "PRE_MARKET_BEGIN",
    "AFTER_HOURS_BEGIN",
    "OVERNIGHT_OPEN",
)


class GatewayError(ValueError):
    """Safe request error which can be returned to the caller."""


def finite_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def normalize_request_symbol(value: str) -> tuple[str, str, str]:
    """Return (market, public code, Futu code) from ``market:code``."""

    raw = str(value or "").strip()
    if ":" not in raw:
        raise GatewayError("symbol must use market:code format")
    market_raw, code_raw = raw.split(":", 1)
    market = MARKET_ALIASES.get(market_raw.strip().lower())
    if market is None:
        raise GatewayError("unsupported market")
    code = code_raw.strip().upper()

    if market == "a_share":
        code = re.sub(r"^(?:SH|SZ)[.:]?", "", code)
        if not re.fullmatch(r"\d{6}", code):
            raise GatewayError("A-share code must contain six digits")
        prefix = "SH" if code.startswith(("5", "6", "9")) else "SZ"
        return market, code, f"{prefix}.{code}"

    if market == "hk":
        code = re.sub(r"^(?:HK)[.:]?", "", code)
        code = re.sub(r"\.HK$", "", code)
        if not re.fullmatch(r"\d{1,5}", code):
            raise GatewayError("Hong Kong code must contain one to five digits")
        normalized = code.zfill(5)
        return market, f"{normalized}.HK", f"HK.{normalized}"

    code = re.sub(r"^(?:US)[.:]?", "", code)
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", code):
        raise GatewayError("US ticker is invalid")
    return market, code, f"US.{code}"


def parse_source_time(value: Any, market: str) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NY_TZ if market == "us" else CN_TZ)
    return parsed.astimezone(UTC)


def state_for_market(global_state: dict[str, Any], market: str) -> str:
    keys = {
        "a_share": ("market_sh", "market_sz"),
        "hk": ("market_hk",),
        "us": ("market_us",),
    }[market]
    values = [str(global_state.get(key) or "") for key in keys]
    return "/".join(value for value in values if value) or "UNKNOWN"


def session_for_state(state: str) -> tuple[str, str]:
    upper = state.upper()
    if "CLOSED" in upper or "_END" in upper or "REST" in upper:
        return "closed", "已收盘"
    if "OVERNIGHT" in upper or "NIGHT_OPEN" in upper:
        return "overnight", "盘夜"
    if "PRE_MARKET" in upper:
        return "pre", "盘前"
    if "AFTER_HOURS" in upper:
        return "post", "盘后"
    if any(token in upper for token in ("MORNING", "AFTERNOON", "DAY_OPEN")):
        return "regular", "盘中"
    return "closed", "已收盘"


def preferred_price(row: dict[str, Any], session: str) -> tuple[float | None, str]:
    fields = {
        "pre": ("pre_price", "pre_market"),
        "post": ("after_price", "after_hours"),
        "overnight": ("overnight_price", "overnight"),
    }
    if session in fields:
        value = finite_number(row.get(fields[session][0]))
        if value is not None and value > 0:
            return value, fields[session][1]
    return finite_number(row.get("last_price")), "last_trade" if session == "regular" else "last_close"


def public_code_from_futu(futu_code: str, market: str) -> str:
    suffix = str(futu_code or "").split(".", 1)[-1]
    return f"{suffix}.HK" if market == "hk" else suffix


def quote_from_row(
    row: dict[str, Any],
    market: str,
    public_code: str,
    global_state: dict[str, Any],
    fetched_at: dt.datetime,
) -> dict[str, Any]:
    state = state_for_market(global_state, market)
    session, session_label = session_for_state(state)
    price, price_kind = preferred_price(row, session)
    state_upper = state.upper()
    if session == "closed" and "AFTER_HOURS_END" in state_upper:
        after_price = finite_number(row.get("after_price"))
        if after_price is not None and after_price > 0:
            price, price_kind = after_price, "after_hours_close"
    elif session == "closed" and ("OVERNIGHT_END" in state_upper or "NIGHT_END" in state_upper):
        overnight_price = finite_number(row.get("overnight_price"))
        if overnight_price is not None and overnight_price > 0:
            price, price_kind = overnight_price, "overnight_close"
    source_time = parse_source_time(row.get("update_time"), market)
    latency = max(0.0, (fetched_at - source_time).total_seconds()) if source_time else None
    active = session != "closed"
    is_realtime = bool(price and active and latency is not None and latency <= ACTIVE_FRESH_SECONDS)
    quote_status = "REALTIME" if is_realtime else ("LAST_CLOSE" if session == "closed" and price else "DELAYED")
    if price is None or price <= 0:
        quote_status = "UNAVAILABLE"

    previous_close = finite_number(row.get("prev_close_price"))
    change_pct = None
    if price and previous_close and previous_close > 0:
        change_pct = round((price / previous_close - 1) * 100, 4)
    return {
        "market": market,
        "code": public_code,
        "provider_symbol": row.get("code"),
        "price": price,
        "price_kind": price_kind,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "bid": finite_number(row.get("bid_price")),
        "ask": finite_number(row.get("ask_price")),
        "volume": finite_number(row.get("volume")),
        "volume_unit": "share",
        "session": session,
        "session_label": session_label,
        "market_state": state,
        "quote_status": quote_status,
        "provider": "FUTU_OPEND",
        "source_tier": "licensed_exchange_feed",
        "source_as_of": source_time.isoformat().replace("+00:00", "Z") if source_time else None,
        "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
        "latency_seconds": round(latency, 3) if latency is not None else None,
        "is_realtime": is_realtime,
        "is_stale": quote_status in {"DELAYED", "UNAVAILABLE"},
    }


@dataclass
class CacheEntry:
    expires_at: float
    payload: dict[str, Any]


class FutuQuoteProvider:
    def __init__(self, host: str, port: int):
        try:
            from futu import OpenQuoteContext, RET_OK
        except ImportError as exc:  # pragma: no cover - production environment guard
            raise RuntimeError("futu-api is not installed") from exc
        self.ret_ok = RET_OK
        self.context = OpenQuoteContext(host=host, port=port)
        self.lock = threading.Lock()
        self.cache: dict[str, CacheEntry] = {}

    def close(self) -> None:
        self.context.close()

    def health(self) -> dict[str, Any]:
        started = time.monotonic()
        with self.lock:
            ret, state = self.context.get_global_state()
        return {
            "ok": ret == self.ret_ok,
            "opend_latency_ms": round((time.monotonic() - started) * 1000, 1),
            "market_state_available": isinstance(state, dict),
        }

    def quotes(self, requested: list[tuple[str, str, str]]) -> dict[str, Any]:
        key = ",".join(item[2] for item in requested)
        cached = self.cache.get(key)
        now_mono = time.monotonic()
        if cached and cached.expires_at > now_mono:
            result = dict(cached.payload)
            result["cache"] = "HIT"
            return result

        started = time.monotonic()
        futu_codes = [item[2] for item in requested]
        with self.lock:
            state_ret, global_state = self.context.get_global_state()
            quote_ret, frame = self.context.get_market_snapshot(futu_codes)
        if state_ret != self.ret_ok or not isinstance(global_state, dict):
            raise RuntimeError("OpenD market state is unavailable")
        if quote_ret != self.ret_ok or not hasattr(frame, "to_dict"):
            raise RuntimeError("OpenD snapshot request failed")

        by_code = {str(row.get("code")): row for row in frame.to_dict("records")}
        fetched_at = dt.datetime.now(UTC)
        quotes = []
        for market, public_code, futu_code in requested:
            row = by_code.get(futu_code)
            if row:
                quotes.append(quote_from_row(row, market, public_code, global_state, fetched_at))
            else:
                quotes.append(
                    {
                        "market": market,
                        "code": public_code,
                        "provider_symbol": futu_code,
                        "quote_status": "UNAVAILABLE",
                        "provider": "FUTU_OPEND",
                        "source_tier": "licensed_exchange_feed",
                        "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
                        "is_realtime": False,
                        "is_stale": True,
                    }
                )
        payload = {
            "ok": True,
            "provider": "FUTU_OPEND",
            "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
            "gateway_latency_ms": round((time.monotonic() - started) * 1000, 1),
            "cache": "MISS",
            "quotes": quotes,
        }
        self.cache[key] = CacheEntry(now_mono + CACHE_SECONDS, payload)
        return payload


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "XuanguQuoteGateway/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Never include query strings (which contain symbols) or auth headers.
        print(f"{self.address_string()} {fmt % args}")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self) -> bool:
        expected = self.server.gateway_token  # type: ignore[attr-defined]
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, f"Bearer {expected}")

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/health":
            try:
                health = self.server.provider.health()  # type: ignore[attr-defined]
                self.send_json(HTTPStatus.OK if health["ok"] else HTTPStatus.SERVICE_UNAVAILABLE, health)
            except Exception:
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "OPEND_UNAVAILABLE"})
            return
        if parsed.path != "/v1/quotes":
            self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "NOT_FOUND"})
            return
        if not self.authenticated():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "UNAUTHORIZED"})
            return
        raw_symbols = urllib.parse.parse_qs(parsed.query).get("symbols", [""])[0]
        values = [value.strip() for value in raw_symbols.split(",") if value.strip()]
        if not values or len(values) > MAX_SYMBOLS:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_SYMBOL_COUNT"})
            return
        try:
            requested = list(dict.fromkeys(normalize_request_symbol(value) for value in values))
            payload = self.server.provider.quotes(requested)  # type: ignore[attr-defined]
        except GatewayError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "INVALID_SYMBOL", "detail": str(exc)})
            return
        except Exception:
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "OPEND_UNAVAILABLE"})
            return
        self.send_json(HTTPStatus.OK, payload)


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Futu OpenD HTTP quote gateway")
    parser.add_argument("--host", default=os.getenv("GATEWAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("GATEWAY_PORT", "8789")))
    parser.add_argument("--opend-host", default=os.getenv("OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--opend-port", type=int, default=int(os.getenv("OPEND_PORT", "11111")))
    args = parser.parse_args()
    token = os.getenv("QUOTE_GATEWAY_TOKEN", "")
    if len(token) < 24:
        raise SystemExit("QUOTE_GATEWAY_TOKEN must contain at least 24 characters")

    provider = FutuQuoteProvider(args.opend_host, args.opend_port)
    server = ThreadingHTTPServer((args.host, args.port), GatewayHandler)
    server.gateway_token = token  # type: ignore[attr-defined]
    server.provider = provider  # type: ignore[attr-defined]
    print(
        f"quote gateway listening on http://{args.host}:{args.port} "
        f"(token fingerprint {token_fingerprint(token)})"
    )
    try:
        server.serve_forever()
    finally:
        provider.close()


if __name__ == "__main__":
    main()

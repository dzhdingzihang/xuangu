#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from zoneinfo import ZoneInfo


IDENTITY_FIELDS = (
    "generated_at",
    "snapshot_key",
    "model_version",
    "schema_version",
    "selector_mode",
)
STATUS_REQUIRED_FIELDS = IDENTITY_FIELDS
DECISION_IDENTITY_FIELDS = (
    "target_date",
    "signal_date",
    "forecast_end_date",
)
ALLOWED_GLOBAL_ACTIONS = {"NO_VALID_PICK", "REVIEW_EXECUTABLE_PICK"}
ALLOWED_PRODUCTION_ACTIONS = {"NO_QUALIFIED_PICK", "QUALIFIED_PICK"}
DEFAULT_BASE_URL = "https://xuangu.alixjd.com"
SHANGHAI_TIME_ZONE = ZoneInfo("Asia/Shanghai")
SCHEDULED_REFRESH_CHECKPOINTS = (
    (8, 17),
    (8, 47),
    (10, 17),
    (10, 47),
    (12, 17),
    (12, 47),
    (15, 17),
    (15, 47),
    (16, 17),
    (16, 47),
    (20, 17),
    (20, 47),
    (22, 47),
    (23, 17),
)
ResponsePayload = tuple[int, Mapping[str, str], bytes]
ERROR_BODY_PREVIEW_BYTES = 512
LIVE_CONTRACT_REQUEST_BUDGET = 90
WORKER_RUNTIME_CONTRACT_VERSION = "worker-runtime-v1"
WORKER_LIVE_INDEX_CONTRACT_VERSION = "worker-live-index-v1"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def fetch_response(
    url: str,
    *,
    timeout: float = 10,
    follow_redirects: bool = True,
) -> ResponsePayload:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Cache-Control": "no-cache",
            "User-Agent": "xuangu-deployment-verifier/2.0",
        },
    )
    opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def fetch_json(url: str, *, timeout: float = 10) -> dict:
    status, headers, body = fetch_response(url, timeout=timeout)
    if not 200 <= status < 300:
        details: list[str] = []
        ray = _header(headers, "cf-ray")
        if ray:
            details.append(f"cf-ray={ray}")
        preview = body[:ERROR_BODY_PREVIEW_BYTES].decode("utf-8", errors="replace")
        preview = " ".join(preview.split())
        if len(body) > ERROR_BODY_PREVIEW_BYTES:
            preview = f"{preview}…"
        if preview:
            details.append(f"body={preview!r}")
        suffix = f" ({'; '.join(details)})" if details else ""
        raise OSError(f"{url} returned HTTP {status}{suffix}")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return payload


def parse_snapshot_content(content: bytes) -> dict:
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("local latest snapshot must be a JSON object")
    return payload


def read_snapshot(path: pathlib.Path) -> dict:
    return parse_snapshot_content(path.read_bytes())


def source_snapshot_identity(content: bytes) -> tuple[str, int]:
    if not isinstance(content, bytes) or not content:
        raise ValueError("local snapshot content must be non-empty bytes")
    return hashlib.sha256(content).hexdigest(), len(content)


def _normalize_json_numbers(value):
    """Match JSON.parse/JSON.stringify numeric semantics used by the Worker."""
    if isinstance(value, dict):
        return {key: _normalize_json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def canonical_snapshot_bytes(payload: dict) -> bytes:
    if not isinstance(payload, dict):
        raise TypeError("snapshot payload must be an object")
    return json.dumps(
        _normalize_json_numbers(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def snapshot_sha256(payload: dict) -> str:
    return hashlib.sha256(canonical_snapshot_bytes(payload)).hexdigest()


def _parse_moment(value: object) -> dt.datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp is missing a timezone: {value!r}")
    return parsed


def next_scheduled_refresh(value: object) -> dt.datetime:
    """Independently calculate the next primary or health-fallback invocation."""
    current = value if isinstance(value, dt.datetime) else _parse_moment(value)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("current time must be timezone-aware")
    local = current.astimezone(SHANGHAI_TIME_ZONE)
    for day_offset in range(9):
        day = local.date() + dt.timedelta(days=day_offset)
        if day.weekday() >= 5:
            continue
        for hour, minute in SCHEDULED_REFRESH_CHECKPOINTS:
            checkpoint = dt.datetime.combine(
                day,
                dt.time(hour, minute),
                tzinfo=SHANGHAI_TIME_ZONE,
            )
            if checkpoint > local:
                return checkpoint
    raise ValueError("unable to find next scheduled refresh")


def _validate_snapshot_key(value: object) -> str:
    key = str(value or "")
    if (
        not key.endswith(".json")
        or pathlib.PurePosixPath(key).name != key
        or "/" in key
        or "\\" in key
    ):
        raise ValueError(f"unsafe snapshot_key: {key!r}")
    return key


def _atomic_write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(rendered)
        temporary = pathlib.Path(handle.name)
    temporary.replace(path)


def adopt_newer_remote_snapshot(
    local_path: pathlib.Path,
    *,
    base_url: str,
    fetcher: Callable[[str], dict] = fetch_json,
) -> dict:
    """Prevent a code push from redeploying a snapshot older than production."""
    local = read_snapshot(local_path)
    # Fetch the immutable static JSON representation, not /api/latest.  The
    # Worker API parses and re-serializes the payload in JavaScript, which
    # normalizes integral floats such as 0.0 to 0 and invalidates canonical
    # hashes produced from the original Python JSON document.
    remote = fetcher(endpoint_url(base_url, "/data/picks/latest.json"))
    for field in IDENTITY_FIELDS + DECISION_IDENTITY_FIELDS:
        if remote.get(field) in (None, ""):
            raise ValueError(f"remote.{field} is missing; refusing stale-push reconciliation")

    local_time = _parse_moment(local.get("generated_at"))
    remote_time = _parse_moment(remote.get("generated_at"))
    local_hash = snapshot_sha256(local)
    remote_hash = snapshot_sha256(remote)
    if remote_time < local_time or (remote_time == local_time and remote_hash == local_hash):
        return {
            "adopted": False,
            "snapshot_key": local.get("snapshot_key"),
            "generated_at": local.get("generated_at"),
            "sha256": local_hash,
        }

    # A same-timestamp mismatch is also treated as production-authoritative.
    # Worker build enrichment (for example a newly settled shadow outcome) is
    # allowed to add fields without changing generated_at.  Adopting it keeps
    # an ordinary code push from silently removing that newer public state.
    key = _validate_snapshot_key(remote.get("snapshot_key"))
    immutable_path = local_path.parent / key
    # Publish the immutable target first so latest.json can never point at a
    # missing timestamp file if the runner is interrupted between writes.
    _atomic_write_json(immutable_path, remote)
    _atomic_write_json(local_path, remote)
    return {
        "adopted": True,
        "snapshot_key": key,
        "generated_at": remote.get("generated_at"),
        "sha256": remote_hash,
    }


def _remote_value(payload: dict, field: str):
    if field == "snapshot_key" and field not in payload:
        return payload.get("latest_snapshot_key")
    return payload.get(field)


def deployment_mismatches(local: dict, status: dict, latest: dict) -> list[str]:
    """Compare immutable local snapshot identity with both deployed APIs."""
    errors: list[str] = []
    if not isinstance(local, dict):
        return ["local payload is not an object"]
    if not isinstance(status, dict):
        status = {}
        errors.append("status payload is not an object")
    if not isinstance(latest, dict):
        latest = {}
        errors.append("latest payload is not an object")

    for field in IDENTITY_FIELDS + DECISION_IDENTITY_FIELDS:
        expected = local.get(field)
        if expected in (None, ""):
            errors.append(f"local.{field} is missing")

    for field in STATUS_REQUIRED_FIELDS:
        expected = local.get(field)
        actual = _remote_value(status, field)
        if actual != expected:
            errors.append(f"status.{field}: expected {expected!r}, got {actual!r}")

    if status.get("ok") is not True:
        errors.append(f"status.ok: expected true, got {status.get('ok')!r}")
    if status.get("has_latest") is not True:
        errors.append(f"status.has_latest: expected true, got {status.get('has_latest')!r}")

    for field in IDENTITY_FIELDS + DECISION_IDENTITY_FIELDS:
        expected = local.get(field)
        actual = _remote_value(latest, field)
        if actual != expected:
            errors.append(f"latest.{field}: expected {expected!r}, got {actual!r}")

    try:
        local_hash = snapshot_sha256(local)
        latest_hash = snapshot_sha256(latest)
        if latest_hash != local_hash:
            errors.append(f"latest.sha256: expected {local_hash}, got {latest_hash}")
    except (TypeError, ValueError) as exc:
        errors.append(f"latest.sha256 unavailable: {exc}")

    local_global = local.get("global_decision") or {}
    remote_global = latest.get("global_decision") or {}
    expected_action = local_global.get("action")
    if expected_action not in ALLOWED_GLOBAL_ACTIONS:
        errors.append(f"local.global_decision.action is invalid: {expected_action!r}")
    if remote_global.get("action") != expected_action:
        errors.append(
            "latest.global_decision.action: "
            f"expected {expected_action!r}, got {remote_global.get('action')!r}"
        )
    for field in ("contract_version", "decision_scope", "action_basis"):
        if remote_global.get(field) != local_global.get(field):
            errors.append(
                f"latest.global_decision.{field}: expected {local_global.get(field)!r}, "
                f"got {remote_global.get(field)!r}"
            )
    local_production = local.get("production_decision")
    if isinstance(local_production, dict):
        remote_production = latest.get("production_decision") or {}
        expected_production_action = local_production.get("action")
        if expected_production_action not in ALLOWED_PRODUCTION_ACTIONS:
            errors.append(f"local.production_decision.action is invalid: {expected_production_action!r}")
        if remote_production.get("action") != expected_production_action:
            errors.append(
                "latest.production_decision.action: "
                f"expected {expected_production_action!r}, got {remote_production.get('action')!r}"
            )
        for field in ("contract_version", "decision_scope", "action_basis", "rule_model_id", "score_kind"):
            if remote_production.get(field) != local_production.get(field):
                errors.append(
                    f"latest.production_decision.{field}: expected {local_production.get(field)!r}, "
                    f"got {remote_production.get(field)!r}"
                )
        local_qualification = (local_production.get("primary") or {}).get("qualification_id")
        remote_qualification = (remote_production.get("primary") or {}).get("qualification_id")
        if remote_qualification != local_qualification:
            errors.append(
                f"latest.production_decision.primary.qualification_id: expected {local_qualification!r}, "
                f"got {remote_qualification!r}"
            )
    return errors


def status_identity_errors(local: dict, status: dict) -> list[str]:
    """Validate the lightweight status identity without downloading latest.json."""
    errors: list[str] = []
    if not isinstance(local, dict):
        return ["local payload is not an object"]
    if not isinstance(status, dict):
        status = {}
        errors.append("status payload is not an object")
    for field in IDENTITY_FIELDS + DECISION_IDENTITY_FIELDS:
        if local.get(field) in (None, ""):
            errors.append(f"local.{field} is missing")
    for field in STATUS_REQUIRED_FIELDS:
        expected = local.get(field)
        actual = _remote_value(status, field)
        if actual != expected:
            errors.append(f"status.{field}: expected {expected!r}, got {actual!r}")
    if status.get("ok") is not True:
        errors.append(f"status.ok: expected true, got {status.get('ok')!r}")
    if status.get("has_latest") is not True:
        errors.append(f"status.has_latest: expected true, got {status.get('has_latest')!r}")

    global_action = (local.get("global_decision") or {}).get("action")
    if global_action not in ALLOWED_GLOBAL_ACTIONS:
        errors.append(f"local.global_decision.action is invalid: {global_action!r}")
    production = local.get("production_decision")
    if isinstance(production, dict) and production.get("action") not in ALLOWED_PRODUCTION_ACTIONS:
        errors.append(f"local.production_decision.action is invalid: {production.get('action')!r}")
    return errors


def runtime_status_errors(
    status: dict,
    *,
    source_snapshot_sha256: str,
    source_snapshot_byte_size: int,
) -> list[str]:
    if not re.fullmatch(r"[a-f0-9]{64}", source_snapshot_sha256):
        raise ValueError("source_snapshot_sha256 must be a lowercase SHA-256 digest")
    if (
        not isinstance(source_snapshot_byte_size, int)
        or isinstance(source_snapshot_byte_size, bool)
        or source_snapshot_byte_size <= 0
    ):
        raise ValueError("source_snapshot_byte_size must be a positive integer")
    expected = {
        "runtime_contract_version": WORKER_RUNTIME_CONTRACT_VERSION,
        "source_snapshot_sha256": source_snapshot_sha256,
        "source_snapshot_byte_size": source_snapshot_byte_size,
    }
    return [
        f"status.{field}: expected {value!r}, got {status.get(field)!r}"
        for field, value in expected.items()
        if status.get(field) != value
    ]


def status_deployment_errors(
    local: dict,
    status: dict,
    *,
    source_snapshot_sha256: str,
    source_snapshot_byte_size: int,
) -> list[str]:
    errors = status_identity_errors(local, status)
    errors.extend(scheduled_snapshot_status_errors(local, status))
    errors.extend(runtime_status_errors(
        status,
        source_snapshot_sha256=source_snapshot_sha256,
        source_snapshot_byte_size=source_snapshot_byte_size,
    ))
    return errors


def scheduled_snapshot_status_errors(local: dict, status: dict) -> list[str]:
    """Require the deployed Worker to advertise the device-free snapshot mode."""
    errors: list[str] = []
    required_values = {
        "data_mode": "scheduled_snapshot",
        "quote_delivery_mode": "scheduled_snapshot",
        "device_dependency": False,
        "schedule_time_zone": "Asia/Shanghai",
        "schedule_primary_checkpoints": [
            "08:17",
            "10:17",
            "12:17",
            "15:17",
            "16:17",
            "20:17",
            "22:47",
        ],
        "schedule_fallback_checkpoints": [
            "08:47",
            "10:47",
            "12:47",
            "15:47",
            "16:47",
            "20:47",
            "23:17",
        ],
        "snapshot_as_of": local.get("generated_at"),
    }
    if isinstance(local.get("production_decision"), dict):
        required_values.update({
            "production_action": local["production_decision"].get("action"),
            "qualification_id": ((local["production_decision"].get("primary") or {}).get("qualification_id")),
            "calibrated_action": ((local.get("global_decision") or {}).get("action")),
            "prediction_id": (((local.get("global_decision") or {}).get("primary") or {}).get("prediction_id")),
        })
    for field, expected in required_values.items():
        actual = status.get(field)
        if actual != expected:
            errors.append(f"status.{field}: expected {expected!r}, got {actual!r}")

    parsed: dict[str, dt.datetime] = {}
    for field in ("time", "next_refresh"):
        try:
            parsed[field] = _parse_moment(status.get(field))
        except (TypeError, ValueError):
            errors.append(f"status.{field} is not a timezone-aware timestamp")
    if all(field in parsed for field in ("time", "next_refresh")):
        if parsed["next_refresh"].utcoffset() != dt.timedelta(hours=8):
            errors.append("status.next_refresh is not expressed in Asia/Shanghai (+08:00)")
        expected = next_scheduled_refresh(parsed["time"])
        if parsed["next_refresh"] != expected:
            errors.append(
                f"status.next_refresh: expected {expected.isoformat()}, "
                f"got {status.get('next_refresh')!r}"
            )
    return errors


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value)
    return ""


def _normalize_live_code(market: str, value: object) -> str | None:
    raw = str(value or "").strip().upper()
    if market == "a_share":
        match = re.fullmatch(r"(?:(?:SH|SZ)\.?)?(\d{6})(?:\.(?:SH|SZ))?", raw)
        return match.group(1) if match else None
    if market == "hk":
        match = re.fullmatch(r"0*(\d{1,5})(?:\.HK)?", raw)
        if not match:
            return None
        number = int(match.group(1))
        return f"{number:04d}.HK" if 1 <= number <= 9999 else None
    if market == "us":
        normalized = raw.replace("_", "-").replace(".", "-")
        return normalized if re.fullmatch(r"[A-Z][A-Z0-9-]{0,14}", normalized) else None
    return None


def _live_candidates(snapshot: dict, market: str) -> list[tuple[str, dict]]:
    markets = snapshot.get("markets") if isinstance(snapshot.get("markets"), dict) else {}
    section = markets.get(market)
    if not isinstance(section, dict) and market == "a_share":
        section = {"decision": snapshot.get("decision") or {}}
    decision = section.get("decision") if isinstance(section, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    watchlist = decision.get("watchlist")
    rows = [
        decision.get("primary"),
        decision.get("blocked_candidate"),
        *(watchlist if isinstance(watchlist, list) else []),
    ]
    global_decision = snapshot.get("global_decision")
    if isinstance(global_decision, dict):
        for field in ("primary", "research_priority"):
            candidate = global_decision.get(field)
            if isinstance(candidate, dict) and candidate.get("market") == market:
                rows.append(candidate)
    production_decision = snapshot.get("production_decision")
    if isinstance(production_decision, dict):
        qualified = production_decision.get("qualified_candidates")
        production_rows = [
            production_decision.get("primary"),
            *(qualified if isinstance(qualified, list) else []),
        ]
        for candidate in production_rows:
            if isinstance(candidate, dict) and candidate.get("market") == market:
                rows.append(candidate.get("candidate_snapshot") or candidate)

    result: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for candidate in rows:
        if not isinstance(candidate, dict):
            continue
        code = _normalize_live_code(market, candidate.get("code") or candidate.get("symbol"))
        if not code or code in seen:
            continue
        seen.add(code)
        result.append((code, candidate))
    return result


def _candidate_code(snapshot: dict, market: str) -> str | None:
    """Backward-compatible first-candidate helper for external test imports."""
    candidates = _live_candidates(snapshot, market)
    return candidates[0][0] if candidates else None


def history_contract_errors(local: dict, history_payload: dict) -> list[str]:
    errors: list[str] = []
    if history_payload.get("ok") is not True:
        errors.append("history.ok is not true")
    history = history_payload.get("history")
    meta = history_payload.get("meta")
    if not isinstance(history, list):
        return errors + ["history.history is not an array"]
    if not isinstance(meta, dict):
        errors.append("history.meta is not an object")
        meta = {}
    if meta.get("view") != "raw":
        errors.append(f"history.meta.view: expected 'raw', got {meta.get('view')!r}")
    if not isinstance(meta.get("raw_run_count"), int) or meta.get("raw_run_count", 0) < 1:
        errors.append("history.meta.raw_run_count is invalid")

    key = local.get("snapshot_key")
    row = next((item for item in history if item.get("snapshot_key") == key), None)
    if row is None:
        errors.append(f"history is missing deployed snapshot {key!r}")
        return errors
    for field in ("generated_at", "target_date", "signal_date"):
        if row.get(field) != local.get(field):
            errors.append(f"history[{key}].{field} does not match latest")
    expected_action = ((local.get("global_decision") or {}).get("action"))
    actual_action = ((row.get("global_decision") or {}).get("action"))
    if actual_action != expected_action:
        errors.append(
            f"history[{key}].global_decision.action: expected {expected_action!r}, got {actual_action!r}"
        )
    if isinstance(local.get("production_decision"), dict):
        expected_production_action = local["production_decision"].get("action")
        actual_production_action = ((row.get("production_decision") or {}).get("action"))
        if actual_production_action != expected_production_action:
            errors.append(
                f"history[{key}].production_decision.action: expected {expected_production_action!r}, "
                f"got {actual_production_action!r}"
            )
    return errors


def static_contract_errors(
    base_url: str,
    response_fetcher: Callable[[str, bool], ResponsePayload],
) -> list[str]:
    errors: list[str] = []
    root_url = endpoint_url(base_url, "/")
    status, headers, body = response_fetcher(root_url, True)
    if status != 200:
        errors.append(f"static root returned HTTP {status}")
    content_type = _header(headers, "content-type").lower()
    if "text/html" not in content_type:
        errors.append(f"static root content-type is not HTML: {content_type!r}")
    page = body.decode("utf-8", "replace")
    for marker in ('id="mainContent"', 'id="tab-history"', "/static/app.js"):
        if marker not in page:
            errors.append(f"static root is missing marker {marker!r}")

    required_headers = {
        "strict-transport-security": "max-age=",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin",
        "permissions-policy": "camera=()",
    }
    for name, expected in required_headers.items():
        actual = _header(headers, name).lower()
        if expected.lower() not in actual:
            errors.append(f"static root header {name!r} is missing {expected!r}")

    parsed = urllib.parse.urlsplit(root_url)
    if parsed.scheme == "https":
        insecure_url = urllib.parse.urlunsplit(("http", parsed.netloc, parsed.path or "/", "", ""))
        redirect_status, redirect_headers, _body = response_fetcher(insecure_url, False)
        if redirect_status not in {301, 308}:
            errors.append(f"HTTP static root did not redirect permanently: HTTP {redirect_status}")
        location = _header(redirect_headers, "location")
        if location != root_url:
            errors.append(f"HTTP static root redirect location: expected {root_url!r}, got {location!r}")
    return errors


def live_contract_errors(
    local: dict,
    *,
    base_url: str,
    fetcher: Callable[[str], dict],
    source_snapshot_sha256: str,
    source_snapshot_byte_size: int,
) -> list[str]:
    errors: list[str] = []
    expected_volume_units = {
        "a_share": {"lot", "share", "shares"},
        "hk": {"share", "shares"},
        "us": {"share", "shares"},
    }
    for market in ("a_share", "hk", "us"):
        for code, candidate in _live_candidates(local, market):
            prefix = f"live.{market}.{code}"
            quote = candidate.get("realtime")
            if not isinstance(quote, dict):
                errors.append(f"{prefix}.realtime snapshot quote is missing")
                continue
            expected_price = quote.get("price")
            if (
                not isinstance(expected_price, (int, float))
                or isinstance(expected_price, bool)
                or not math.isfinite(expected_price)
                or expected_price <= 0
            ):
                errors.append(f"{prefix}.realtime.price is not positive")
                continue
            local_quote_valid = True
            for field in ("source_as_of", "fetched_at"):
                try:
                    _parse_moment(quote.get(field))
                except (TypeError, ValueError):
                    errors.append(f"{prefix}.realtime.{field} is not a timezone-aware timestamp")
                    local_quote_valid = False
            if quote.get("volume_unit") not in expected_volume_units[market]:
                errors.append(
                    f"{prefix}.realtime.volume_unit: expected one of "
                    f"{sorted(expected_volume_units[market])!r}, got {quote.get('volume_unit')!r}"
                )
                local_quote_valid = False
            if not local_quote_valid:
                continue

            query = urllib.parse.urlencode({"market": market, "code": code})
            payload = fetcher(endpoint_url(base_url, f"/api/live?{query}"))
            if payload.get("contract_version") != "live-quote-v1":
                errors.append(f"{prefix}.contract_version is not 'live-quote-v1'")
            if payload.get("source_index_contract_version") != WORKER_LIVE_INDEX_CONTRACT_VERSION:
                errors.append(
                    f"{prefix}.source_index_contract_version is not "
                    f"{WORKER_LIVE_INDEX_CONTRACT_VERSION!r}"
                )
            if payload.get("source_snapshot_sha256") != source_snapshot_sha256:
                errors.append(
                    f"{prefix}.source_snapshot_sha256: expected {source_snapshot_sha256!r}, "
                    f"got {payload.get('source_snapshot_sha256')!r}"
                )
            if payload.get("source_snapshot_byte_size") != source_snapshot_byte_size:
                errors.append(
                    f"{prefix}.source_snapshot_byte_size: expected {source_snapshot_byte_size!r}, "
                    f"got {payload.get('source_snapshot_byte_size')!r}"
                )
            if payload.get("ok") is not True:
                errors.append(f"{prefix}.ok is not true")
            if payload.get("market") != market:
                errors.append(f"{prefix}.market: got {payload.get('market')!r}")
            if str(payload.get("code") or "").upper() != code.upper():
                errors.append(f"{prefix}.code: got {payload.get('code')!r}")
            for field in ("data_mode", "quote_mode", "provider_class"):
                if payload.get(field) != "SCHEDULED_SNAPSHOT":
                    errors.append(f"{prefix}.{field} is not 'SCHEDULED_SNAPSHOT'")
            if payload.get("snapshot_as_of") != local.get("generated_at"):
                errors.append(
                    f"{prefix}.snapshot_as_of: expected {local.get('generated_at')!r}, "
                    f"got {payload.get('snapshot_as_of')!r}"
                )
            if payload.get("snapshot_key") != local.get("snapshot_key"):
                errors.append(
                    f"{prefix}.snapshot_key: expected {local.get('snapshot_key')!r}, "
                    f"got {payload.get('snapshot_key')!r}"
                )
            price = payload.get("price")
            if (
                not isinstance(price, (int, float))
                or isinstance(price, bool)
                or not math.isfinite(price)
                or price <= 0
            ):
                errors.append(f"{prefix}.price is not positive")
            elif price != expected_price:
                errors.append(f"{prefix}.price: expected realtime.price {expected_price!r}, got {price!r}")
            for field in (
                "provider",
                "provider_class",
                "source",
                "source_as_of",
                "fetched_at",
                "volume_unit",
                "session",
                "session_label",
                "price_kind",
                "quote_status",
                "freshness",
                "rate_limit_status",
            ):
                if not isinstance(payload.get(field), str) or not payload.get(field):
                    errors.append(f"{prefix}.{field} is missing")
            for field in ("source_as_of", "fetched_at", "volume_unit"):
                if payload.get(field) != quote.get(field):
                    errors.append(
                        f"{prefix}.{field}: expected realtime.{field} {quote.get(field)!r}, "
                        f"got {payload.get(field)!r}"
                    )
            if payload.get("quote_status") not in {"DELAYED", "LAST_CLOSE"}:
                errors.append(
                    f"{prefix}.quote_status {payload.get('quote_status')!r} is invalid "
                    "for scheduled snapshot mode; REALTIME is forbidden"
                )
            for field in ("is_realtime", "is_stale", "realtime_guaranteed"):
                if type(payload.get(field)) is not bool:
                    errors.append(f"{prefix}.{field} is not a boolean")
            if payload.get("is_realtime") is not False:
                errors.append(f"{prefix}.is_realtime must be false in scheduled snapshot mode")
            if payload.get("realtime_guaranteed") is not False:
                errors.append(f"{prefix}.realtime_guaranteed must be false in scheduled snapshot mode")
            cache_ttl = payload.get("cache_ttl_seconds")
            if (
                not isinstance(cache_ttl, (int, float))
                or isinstance(cache_ttl, bool)
                or not 0 < cache_ttl <= 30
            ):
                errors.append(f"{prefix}.cache_ttl_seconds is outside (0, 30]")
            parsed_times: dict[str, dt.datetime] = {}
            for field in ("source_as_of", "fetched_at"):
                try:
                    parsed_times[field] = _parse_moment(payload.get(field))
                except (TypeError, ValueError):
                    errors.append(f"{prefix}.{field} is not a timezone-aware timestamp")
            if all(field in parsed_times for field in ("source_as_of", "fetched_at")):
                if parsed_times["source_as_of"] > parsed_times["fetched_at"] + dt.timedelta(minutes=5):
                    errors.append(f"{prefix}.source_as_of is implausibly after fetched_at")
            if not isinstance(payload.get("kline"), list):
                errors.append(f"{prefix}.kline is not an array")
    return errors


def full_deployment_errors(
    local: dict,
    *,
    base_url: str,
    json_fetcher: Callable[[str], dict],
    response_fetcher: Callable[[str, bool], ResponsePayload],
    source_snapshot_sha256: str,
    source_snapshot_byte_size: int,
) -> tuple[dict, list[str]]:
    status = json_fetcher(endpoint_url(base_url, "/api/status"))
    errors = status_deployment_errors(
        local,
        status,
        source_snapshot_sha256=source_snapshot_sha256,
        source_snapshot_byte_size=source_snapshot_byte_size,
    )
    # Never fan out to immutable/history/static/live endpoints while an edge is
    # still serving an old or internally inconsistent deployment identity.
    if errors:
        return {}, errors

    latest = json_fetcher(endpoint_url(base_url, "/api/latest"))
    errors.extend(deployment_mismatches(local, status, latest))
    if errors:
        return latest, errors

    snapshot_key = _validate_snapshot_key(local.get("snapshot_key"))
    snapshot_query = urllib.parse.urlencode({"snapshot": snapshot_key})
    immutable = json_fetcher(endpoint_url(base_url, f"/api/pick?{snapshot_query}"))
    try:
        if snapshot_sha256(immutable) != snapshot_sha256(local):
            errors.append("immutable snapshot sha256 does not match local latest")
    except (TypeError, ValueError) as exc:
        errors.append(f"immutable snapshot sha256 unavailable: {exc}")

    history = json_fetcher(endpoint_url(base_url, "/api/history?view=raw&limit=1000"))
    errors.extend(history_contract_errors(local, history))
    errors.extend(static_contract_errors(base_url, response_fetcher))
    errors.extend(live_contract_errors(
        local,
        base_url=base_url,
        fetcher=json_fetcher,
        source_snapshot_sha256=source_snapshot_sha256,
        source_snapshot_byte_size=source_snapshot_byte_size,
    ))
    return latest, errors


def poll_deployment(
    local: dict,
    *,
    base_url: str,
    attempts: int,
    delay_seconds: float,
    source_snapshot_sha256: str,
    source_snapshot_byte_size: int,
    fetcher: Callable[[str], dict] = fetch_json,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Poll the compact runtime status without repeatedly downloading latest.json."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    status_url = endpoint_url(base_url, "/api/status")
    last_errors: list[str] = []

    for attempt in range(1, attempts + 1):
        try:
            status = fetcher(status_url)
            last_errors = status_deployment_errors(
                local,
                status,
                source_snapshot_sha256=source_snapshot_sha256,
                source_snapshot_byte_size=source_snapshot_byte_size,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            last_errors = [f"request error: {exc}"]

        if not last_errors:
            return status
        if attempt < attempts:
            print(
                f"Deployment identity not visible yet (attempt {attempt}/{attempts}): "
                + "; ".join(last_errors)
            )
            sleeper(delay_seconds)

    raise RuntimeError(
        f"deployment verification failed after {attempts} attempts: "
        + "; ".join(last_errors)
    )


def poll_full_deployment(
    local: dict,
    *,
    base_url: str,
    attempts: int,
    delay_seconds: float,
    source_snapshot_sha256: str,
    source_snapshot_byte_size: int,
    json_fetcher: Callable[[str], dict],
    response_fetcher: Callable[[str, bool], ResponsePayload],
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")
    live_candidate_count = sum(
        len(_live_candidates(local, market))
        for market in ("a_share", "hk", "us")
    )
    if live_candidate_count > LIVE_CONTRACT_REQUEST_BUDGET:
        raise ValueError(
            "live contract candidate count exceeds the per-verification request budget: "
            f"{live_candidate_count} > {LIVE_CONTRACT_REQUEST_BUDGET}"
        )
    # Phase one is deliberately cheap.  Asset/route propagation can expose an
    # old version for several polls, and those polls must not trigger the live
    # contract fan-out.
    poll_deployment(
        local,
        base_url=base_url,
        attempts=attempts,
        delay_seconds=delay_seconds,
        source_snapshot_sha256=source_snapshot_sha256,
        source_snapshot_byte_size=source_snapshot_byte_size,
        fetcher=json_fetcher,
        sleeper=sleeper,
    )

    final_attempts = attempts if live_candidate_count == 0 else min(
        attempts,
        max(1, LIVE_CONTRACT_REQUEST_BUDGET // live_candidate_count),
    )

    latest: dict = {}
    last_errors: list[str] = []
    for attempt in range(1, final_attempts + 1):
        try:
            latest, last_errors = full_deployment_errors(
                local,
                base_url=base_url,
                json_fetcher=json_fetcher,
                response_fetcher=response_fetcher,
                source_snapshot_sha256=source_snapshot_sha256,
                source_snapshot_byte_size=source_snapshot_byte_size,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            last_errors = [f"request error: {exc}"]
        if not last_errors:
            return latest
        if attempt < final_attempts:
            print(
                f"Full deployment contract not ready (attempt {attempt}/{final_attempts}): "
                + "; ".join(last_errors)
            )
            sleeper(delay_seconds)
    raise RuntimeError(
        f"full deployment verification failed after {final_attempts} attempts: "
        + "; ".join(last_errors)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Guard and verify the complete Cloudflare deployment contract."
    )
    parser.add_argument("path", nargs="?", default="data/picks/latest.json")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DEPLOY_VERIFY_BASE_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--delay-seconds", type=float, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument(
        "--adopt-newer-live",
        action="store_true",
        help="On a push build, atomically adopt a newer production snapshot before deployment.",
    )
    args = parser.parse_args()

    path = pathlib.Path(args.path)
    json_fetcher = lambda url: fetch_json(url, timeout=args.timeout_seconds)
    if args.adopt_newer_live:
        result = adopt_newer_remote_snapshot(
            path,
            base_url=args.base_url,
            fetcher=json_fetcher,
        )
        print(
            "Production snapshot reconciliation: "
            f"adopted={str(result['adopted']).lower()} "
            f"snapshot_key={result['snapshot_key']} generated_at={result['generated_at']} "
            f"sha256={result['sha256']}"
        )
        return

    source_content = path.read_bytes()
    local = parse_snapshot_content(source_content)
    source_snapshot_sha256, source_snapshot_byte_size = source_snapshot_identity(source_content)
    latest = poll_full_deployment(
        local,
        base_url=args.base_url,
        attempts=args.attempts,
        delay_seconds=args.delay_seconds,
        source_snapshot_sha256=source_snapshot_sha256,
        source_snapshot_byte_size=source_snapshot_byte_size,
        json_fetcher=json_fetcher,
        response_fetcher=lambda url, follow: fetch_response(
            url,
            timeout=args.timeout_seconds,
            follow_redirects=follow,
        ),
    )
    print(
        "Deployment verified: "
        f"{args.base_url.rstrip('/')} | snapshot_key={latest.get('snapshot_key')} "
        f"generated_at={latest.get('generated_at')} sha256={snapshot_sha256(latest)}"
    )


if __name__ == "__main__":
    main()

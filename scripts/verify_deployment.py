#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time
import urllib.request
from collections.abc import Callable


IDENTITY_FIELDS = (
    "generated_at",
    "snapshot_key",
    "model_version",
    "schema_version",
    "selector_mode",
)
STATUS_REQUIRED_FIELDS = (
    "generated_at",
    "snapshot_key",
    "model_version",
    "schema_version",
    "selector_mode",
)
DEFAULT_BASE_URL = "https://xuangu.alixjd.com"


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def fetch_json(url: str, *, timeout: float = 10) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "xuangu-deployment-verifier/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return payload


def read_snapshot(path: pathlib.Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("local latest snapshot must be a JSON object")
    return payload


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

    for field in IDENTITY_FIELDS:
        expected = local.get(field)
        if expected in (None, ""):
            errors.append(f"local.{field} is missing")

    for field in STATUS_REQUIRED_FIELDS:
        expected = local.get(field)
        actual = _remote_value(status, field)
        if actual != expected:
            errors.append(f"status.{field}: expected {expected!r}, got {actual!r}")

    if status.get("has_latest") is False:
        errors.append("status.has_latest: expected deployed snapshot, got false")

    for field in IDENTITY_FIELDS:
        expected = local.get(field)
        actual = _remote_value(latest, field)
        if actual != expected:
            errors.append(f"latest.{field}: expected {expected!r}, got {actual!r}")
    return errors


def poll_deployment(
    local: dict,
    *,
    base_url: str,
    attempts: int,
    delay_seconds: float,
    fetcher: Callable[[str], dict] = fetch_json,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Poll deployed identity with injectable I/O for deterministic tests."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    status_url = endpoint_url(base_url, "/api/status")
    latest_url = endpoint_url(base_url, "/api/latest")
    last_errors: list[str] = []

    for attempt in range(1, attempts + 1):
        try:
            status = fetcher(status_url)
            latest = fetcher(latest_url)
            last_errors = deployment_mismatches(local, status, latest)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            last_errors = [f"request error: {exc}"]

        if not last_errors:
            return latest
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify that Cloudflare serves the exact locally built snapshot."
    )
    parser.add_argument("path", nargs="?", default="data/picks/latest.json")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DEPLOY_VERIFY_BASE_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--delay-seconds", type=float, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=10)
    args = parser.parse_args()

    path = pathlib.Path(args.path)
    local = read_snapshot(path)
    latest = poll_deployment(
        local,
        base_url=args.base_url,
        attempts=args.attempts,
        delay_seconds=args.delay_seconds,
        fetcher=lambda url: fetch_json(url, timeout=args.timeout_seconds),
    )
    print(
        "Deployment verified: "
        f"{args.base_url.rstrip('/')} | snapshot_key={latest.get('snapshot_key')} "
        f"generated_at={latest.get('generated_at')}"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the immutable, research-only archived-shortlist replay artifact."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import historical_replay  # noqa: E402


PICKS = ROOT / "data" / "picks"
OUTPUT = ROOT / "data" / "backtests" / "archived-shortlist-replay-v1.json"
DEFAULT_MAX_COHORTS = 2_000
MAX_COHORTS = 10_000
DEFAULT_MAX_WORKERS = 8
MAX_WORKERS = 12
PRICE_CACHE_VERSION = "historical-replay-price-cache-v1"
PriceLoader = Callable[[str, str], tuple[list[dict[str, Any]], str, bool]]


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: pathlib.Path, content: bytes) -> None:
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = pathlib.Path(handle.name)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _validated_artifact(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("historical replay artifact must be a JSON object")
    artifact = dict(payload)
    historical_replay.validate_replay_artifact(artifact)
    if artifact.get("authorizes_production") is not False:
        raise ValueError("historical replay artifact must not authorize production")
    return artifact


def _default_network_price_loader(market: str, code: str):
    # This provider chain uses public HTTPS endpoints and is the same cloud-safe
    # settlement path used by the unattended GitHub observation workflows.
    from scripts.settle_outcomes import market_rows

    return market_rows(market, code)


def _cache_file(cache_dir: pathlib.Path, market: str, code: str) -> pathlib.Path:
    identity = hashlib.sha256(f"{market}|{code}".encode("utf-8")).hexdigest()
    return cache_dir / market / f"{identity}.json"


def _cached_price_loader(
    loader: PriceLoader,
    *,
    cache_dir: pathlib.Path | None,
    cache_day: str,
) -> PriceLoader:
    @lru_cache(maxsize=None)
    def load(market: str, code: str) -> tuple[list[dict[str, Any]], str, bool]:
        target = _cache_file(cache_dir, market, code) if cache_dir is not None else None
        if target is not None and target.is_file():
            try:
                cached = json.loads(target.read_text(encoding="utf-8"))
                if (
                    isinstance(cached, Mapping)
                    and cached.get("cache_version") == PRICE_CACHE_VERSION
                    and cached.get("cache_day") == cache_day
                    and cached.get("market") == market
                    and cached.get("code") == code
                    and isinstance(cached.get("rows"), list)
                    and cached.get("rows")
                    and isinstance(cached.get("provider"), str)
                    and type(cached.get("adjusted")) is bool
                ):
                    return list(cached["rows"]), str(cached["provider"]), bool(cached["adjusted"])
            except (OSError, ValueError, TypeError):
                pass

        result: Any = ([], "", False)
        for _ in range(3):
            try:
                result = loader(market, code)
            except Exception:
                result = ([], "", False)
            if (
                isinstance(result, tuple)
                and len(result) == 3
                and isinstance(result[0], list)
                and result[0]
                and isinstance(result[1], str)
                and type(result[2]) is bool
            ):
                break
        if not isinstance(result, tuple) or len(result) != 3 or not isinstance(result[0], list):
            result = ([], "", False)
        normalized = (list(result[0]), str(result[1] or ""), bool(result[2]))
        if target is not None and normalized[0]:
            payload = {
                "cache_version": PRICE_CACHE_VERSION,
                "cache_day": cache_day,
                "market": market,
                "code": code,
                "rows": normalized[0],
                "provider": normalized[1],
                "adjusted": normalized[2],
            }
            try:
                _atomic_write(target, _canonical_bytes(payload))
            except OSError:
                # Cache persistence is an optimization. Provider evidence still
                # reaches the replay builder when GitHub cache storage is down.
                pass
        return normalized

    return load


def _aware(value: dt.datetime | str) -> dt.datetime:
    parsed = (
        value
        if isinstance(value, dt.datetime)
        else dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of and maturity timestamps must be timezone-aware")
    return parsed


def _symbols_requiring_prices(
    cohorts: Sequence[Mapping[str, Any]],
    existing: Mapping[str, Any] | None,
    moment: dt.datetime | str,
) -> list[tuple[str, str]]:
    cutoff = _aware(moment)
    settled_ids = {
        str(row.get("candidate_id") or "")
        for row in (existing or {}).get("outcomes", [])
        if isinstance(row, Mapping) and row.get("status") == "SETTLED"
    }
    symbols: set[tuple[str, str]] = set()
    for cohort in cohorts:
        shortlist = cohort.get("shortlist")
        if not isinstance(shortlist, list):
            continue
        for candidate in shortlist:
            if not isinstance(candidate, Mapping):
                continue
            if str(candidate.get("candidate_id") or "") in settled_ids:
                continue
            try:
                maturity = _aware(str(candidate.get("forecast_end_session_close_at") or ""))
            except (ValueError, TypeError):
                continue
            if cutoff <= maturity:
                continue
            market = str(candidate.get("market") or "")
            for field in ("code", "benchmark_code"):
                code = str(candidate.get(field) or "")
                if market and code:
                    symbols.add((market, code))
    return sorted(symbols)


def _prefetched_price_loader(
    loader: PriceLoader,
    cohorts: Sequence[Mapping[str, Any]],
    existing: Mapping[str, Any] | None,
    moment: dt.datetime | str,
    *,
    max_workers: int,
) -> tuple[PriceLoader, int, int]:
    worker_limit = max(1, min(MAX_WORKERS, int(max_workers)))
    symbols = _symbols_requiring_prices(cohorts, existing, moment)
    prefetched: dict[tuple[str, str], tuple[list[dict[str, Any]], str, bool]] = {}
    if symbols:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(worker_limit, len(symbols)),
        ) as executor:
            futures = {
                executor.submit(loader, market, code): (market, code)
                for market, code in symbols
            }
            for future in concurrent.futures.as_completed(futures):
                key = futures[future]
                try:
                    prefetched[key] = future.result()
                except Exception:
                    prefetched[key] = ([], "", False)

    def load(market: str, code: str) -> tuple[list[dict[str, Any]], str, bool]:
        key = (market, code)
        return prefetched[key] if key in prefetched else loader(market, code)

    return load, len(symbols), min(worker_limit, len(symbols)) if symbols else 0


def validate_file(path: pathlib.Path = OUTPUT) -> dict[str, Any]:
    target = pathlib.Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"unable to read historical replay artifact: {target}") from exc
    return _validated_artifact(payload)


def run(
    picks_dir: pathlib.Path = PICKS,
    output: pathlib.Path = OUTPUT,
    *,
    as_of: str | None = None,
    max_cohorts: int = DEFAULT_MAX_COHORTS,
    max_workers: int = DEFAULT_MAX_WORKERS,
    price_loader: PriceLoader | None = None,
    cache_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    limit = int(max_cohorts)
    if limit < 1 or limit > MAX_COHORTS:
        raise ValueError(f"max_cohorts must be between 1 and {MAX_COHORTS}")

    picks = pathlib.Path(picks_dir)
    target = pathlib.Path(output)
    moment: dt.datetime | str
    moment = as_of or dt.datetime.now(dt.timezone.utc)
    cache_day = (
        moment.astimezone(dt.timezone.utc).date().isoformat()
        if isinstance(moment, dt.datetime)
        else str(moment)[:10]
    )
    if not cache_day:
        raise ValueError("as_of must contain an ISO date")
    cohorts = historical_replay.discover_replay_cohorts(
        picks,
        as_of=moment,
        max_cohorts=limit,
    )
    if not isinstance(cohorts, list):
        raise TypeError("discover_replay_cohorts must return a list")
    existing = validate_file(target) if target.is_file() else None
    if existing is not None:
        # The discovery bound controls new work, never evidence retention.
        # Persisted cohorts are immutable and must remain in every revision.
        cohort_by_id = {
            str(row.get("cohort_id") or ""): row
            for row in existing.get("cohorts", [])
            if isinstance(row, Mapping)
        }
        frozen_entry_cells = {
            (str(row.get("market") or ""), str(row.get("entry_trade_date") or "")):
            str(row.get("cohort_id") or "")
            for row in existing.get("cohorts", [])
            if isinstance(row, Mapping)
        }
        for row in cohorts:
            if not isinstance(row, Mapping):
                raise TypeError("replay cohort must be an object")
            entry_cell = (
                str(row.get("market") or ""),
                str(row.get("entry_trade_date") or ""),
            )
            frozen_id = frozen_entry_cells.get(entry_cell)
            if frozen_id and frozen_id != str(row.get("cohort_id") or ""):
                # The first post-open admission freezes this independent cell.
                # A later repository backfill may not rewrite settled history.
                continue
            cohort_by_id[str(row.get("cohort_id") or "")] = row
        cohorts = sorted(
            cohort_by_id.values(),
            key=lambda row: (
                str(row.get("generated_at") or ""),
                str(row.get("source_snapshot") or ""),
                str(row.get("market") or ""),
            ),
        )
    cached_loader = _cached_price_loader(
        price_loader or _default_network_price_loader,
        cache_dir=pathlib.Path(cache_dir) if cache_dir is not None else None,
        cache_day=cache_day,
    )
    loader, prefetched_symbol_count, used_workers = _prefetched_price_loader(
        cached_loader,
        cohorts,
        existing,
        moment,
        max_workers=max_workers,
    )
    artifact = _validated_artifact(
        historical_replay.build_replay_artifact(
            cohorts,
            as_of=moment,
            price_loader=loader,
            benchmark_price_loader=loader,
            existing=existing,
        )
    )
    rendered = _canonical_bytes(artifact)
    existing = target.read_bytes() if target.is_file() else None
    changed = existing != rendered
    if changed:
        _atomic_write(target, rendered)

    cohort_count = artifact.get("cohort_count")
    if not isinstance(cohort_count, int) or isinstance(cohort_count, bool):
        cohort_count = len(cohorts)
    return {
        "changed": changed,
        "cohort_count": cohort_count,
        "output": str(target),
        "authorizes_production": False,
        "prefetched_symbol_count": prefetched_symbol_count,
        "worker_limit": used_workers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the GitHub-hosted archived-shortlist historical replay",
    )
    parser.add_argument("--picks-dir", type=pathlib.Path, default=PICKS)
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    parser.add_argument("--as-of")
    parser.add_argument("--max-cohorts", type=int, default=DEFAULT_MAX_COHORTS)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument(
        "--cache-dir",
        type=pathlib.Path,
        default=(
            pathlib.Path(os.environ["HISTORICAL_REPLAY_CACHE_DIR"])
            if os.environ.get("HISTORICAL_REPLAY_CACHE_DIR")
            else None
        ),
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if args.validate_only:
        artifact = validate_file(args.output)
        summary = {
            "changed": False,
            "cohort_count": artifact.get("cohort_count", 0),
            "output": str(args.output),
            "authorizes_production": False,
            "validated": True,
        }
    else:
        summary = run(
            args.picks_dir,
            args.output,
            as_of=args.as_of,
            max_cohorts=args.max_cohorts,
            max_workers=args.max_workers,
            cache_dir=args.cache_dir,
        )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()

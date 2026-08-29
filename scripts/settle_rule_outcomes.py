#!/usr/bin/env python3
"""Settle every frozen production-rule qualification in archived snapshots."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import rule_outcome_ledger  # noqa: E402


PICKS = ROOT / "data" / "picks"
OUTCOMES = rule_outcome_ledger.DEFAULT_OUTCOME_DIRECTORY
MAX_WORKERS = 12
DEFAULT_RETRIES = 2
PriceLoader = Callable[[str, str], tuple[list[dict[str, Any]], str, bool]]


def _aware(value: dt.datetime | str | None) -> dt.datetime:
    if value is None:
        parsed = dt.datetime.now(dt.timezone.utc)
    elif isinstance(value, dt.datetime):
        parsed = value
    else:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return parsed


def _default_price_loader(market: str, code: str):
    from scripts.settle_outcomes import market_rows

    return market_rows(market, code)


def _fetch(loader: PriceLoader, market: str, code: str, retries: int):
    value: Any = ([], "", False)
    for _ in range(max(1, retries + 1)):
        try:
            value = loader(market, code)
        except Exception:
            value = ([], "", False)
        if isinstance(value, tuple) and len(value) == 3 and isinstance(value[0], list) and value[0]:
            break
    return value if isinstance(value, tuple) and len(value) == 3 else ([], "", False)


def _load_snapshots(picks_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    for path in sorted(pathlib.Path(picks_dir).glob("*.json")):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(snapshot, dict):
            continue
        decision = snapshot.get("production_decision")
        if (
            not isinstance(decision, Mapping)
            or decision.get("contract_version") != "production-rule-10d-v1"
            # v2 predates qualification_track and therefore cannot be mixed
            # into per-track outcome statistics.  It remains visible as an
            # historical snapshot but is not silently relabelled.
            or decision.get("action_basis")
            not in {
                "dual_track_candidate_qualification_v3",
                "dual_track_candidate_qualification_v4",
            }
        ):
            continue
        key = snapshot.get("snapshot_key") or (path.name if path.name != "latest.json" else None)
        if not isinstance(key, str) or key == "latest.json":
            continue
        identity = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = __import__("hashlib").sha256(identity.encode("utf-8")).hexdigest()
        if key in result and digests[key] != digest:
            raise rule_outcome_ledger.RuleOutcomeConflictError(
                f"snapshot alias content conflict: {key}"
            )
        result[key] = snapshot
        digests[key] = digest
    return result


def run(
    picks_dir: pathlib.Path = PICKS,
    outcomes_dir: pathlib.Path = OUTCOMES,
    *,
    as_of: dt.datetime | str | None = None,
    price_loader: PriceLoader | None = None,
    max_workers: int = MAX_WORKERS,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, int]:
    moment = _aware(as_of)
    snapshots = _load_snapshots(pathlib.Path(picks_dir))
    existing = rule_outcome_ledger.load_rule_outcome_batches(pathlib.Path(outcomes_dir))
    unknown = set(existing) - set(snapshots)
    if unknown:
        raise rule_outcome_ledger.RuleOutcomeConflictError(
            f"rule outcome has no source snapshot: {sorted(unknown)[0]}"
        )

    prediction_sets = {
        key: rule_outcome_ledger.build_rule_predictions(snapshot, key)
        for key, snapshot in snapshots.items()
    }
    symbols: set[tuple[str, str]] = set()
    for key, predictions in prediction_sets.items():
        old = {row["prediction_id"]: row for row in (existing.get(key) or {}).get("outcomes", [])}
        for prediction in predictions:
            if (old.get(prediction["prediction_id"]) or {}).get("status") == "SETTLED":
                continue
            maturity = _aware(str(prediction["forecast_end_session_close_at"]))
            if moment > maturity:
                symbols.add((prediction["market"], prediction["code"]))
                symbols.add((prediction["market"], prediction["benchmark_code"]))

    loader = price_loader or _default_price_loader
    fetched: dict[tuple[str, str], tuple[list[dict[str, Any]], str, bool]] = {}
    worker_limit = max(1, min(MAX_WORKERS, int(max_workers)))
    if symbols:
        with ThreadPoolExecutor(max_workers=min(worker_limit, len(symbols))) as executor:
            futures = {
                executor.submit(_fetch, loader, market, code, max(0, int(retries))): (market, code)
                for market, code in sorted(symbols)
            }
            for future in as_completed(futures):
                fetched[futures[future]] = future.result()

    def cached_loader(market: str, code: str):
        return fetched.get((market, code), ([], "", False))

    counts: Counter[str] = Counter()
    prediction_count = changed = unchanged = 0
    for key, snapshot in sorted(snapshots.items()):
        batch = rule_outcome_ledger.settle_rule_snapshot(
            snapshot,
            moment,
            cached_loader,
            benchmark_price_loader=cached_loader,
            existing=existing.get(key),
            source_snapshot=key,
        )
        prediction_count += batch["prediction_count"]
        counts.update(batch["status_counts"])
        if existing.get(key) == batch:
            unchanged += 1
        else:
            rule_outcome_ledger.write_rule_outcome_batch(pathlib.Path(outcomes_dir), batch)
            changed += 1
    return {
        "snapshot_count": len(snapshots),
        "prediction_count": prediction_count,
        "pending_maturity_count": counts.get("PENDING_MATURITY", 0),
        "pending_data_count": counts.get("PENDING_DATA", 0),
        "settled_count": counts.get("SETTLED", 0),
        "fetched_symbol_count": len(fetched),
        "changed_snapshot_count": changed,
        "unchanged_snapshot_count": unchanged,
        "worker_limit": worker_limit,
        "authorizes_production": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Settle production-rule qualifications")
    parser.add_argument("--picks-dir", type=pathlib.Path, default=PICKS)
    parser.add_argument("--outcomes-dir", type=pathlib.Path, default=OUTCOMES)
    parser.add_argument("--as-of")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.picks_dir,
                args.outcomes_dir,
                as_of=args.as_of,
                max_workers=args.max_workers,
                retries=args.retries,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

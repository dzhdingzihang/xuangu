#!/usr/bin/env python3
"""Batch-settle isolated MODEL_OBSERVATION cohorts.

Only mature, unresolved symbols are fetched.  Price retrieval is bounded and
missing symbols are retried; all contract validation and persistence remains in
``observation_outcome_ledger``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from collections.abc import Callable, Mapping
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import model_observation_ledger  # noqa: E402
import observation_outcome_ledger  # noqa: E402
import ten_day_rank_model  # noqa: E402


OBSERVATIONS = model_observation_ledger.DEFAULT_OBSERVATION_DIRECTORY
OUTCOMES = observation_outcome_ledger.DEFAULT_OUTCOME_DIRECTORY
MAX_WORKERS = 12
DEFAULT_RETRIES = 2
PriceLoader = Callable[[str, str], tuple[list[dict[str, Any]], str, bool]]


def _aware_moment(value: dt.datetime | str | None) -> dt.datetime:
    if value is None:
        parsed = dt.datetime.now(dt.timezone.utc)
    elif isinstance(value, dt.datetime):
        parsed = value
    else:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware timestamp")
    return parsed


def _canonical_predictions(cohort: Mapping[str, Any]) -> list[dict[str, Any]]:
    revision_id = cohort.get("canonical_revision_id")
    for revision in cohort.get("revisions") or []:
        if isinstance(revision, Mapping) and revision.get("revision_id") == revision_id:
            return [dict(row) for row in revision.get("predictions") or []]
    raise observation_outcome_ledger.ObservationOutcomeContractError(
        "observation cohort has no canonical revision"
    )


def _default_price_loader(market: str, code: str):
    # Lazy import prevents a module cycle when scripts/settle_outcomes.py calls
    # this batch runner with its own explicit adjusted loader.
    from scripts.settle_outcomes import market_rows

    return market_rows(market, code)


def _is_missing_price_result(value: Any) -> bool:
    return not (
        isinstance(value, tuple)
        and len(value) == 3
        and isinstance(value[0], list)
        and bool(value[0])
    )


def _fetch_with_retries(
    loader: PriceLoader,
    market: str,
    code: str,
    retries: int,
) -> tuple[list[dict[str, Any]], str, bool]:
    last: Any = ([], "", False)
    for _ in range(max(1, retries + 1)):
        try:
            last = loader(market, code)
        except Exception:
            last = ([], "", False)
        if not _is_missing_price_result(last):
            break
    if not isinstance(last, tuple) or len(last) != 3:
        return [], "", False
    return last


def run(
    observations_dir: pathlib.Path = OBSERVATIONS,
    outcomes_dir: pathlib.Path = OUTCOMES,
    *,
    as_of: dt.datetime | str | None = None,
    price_loader: PriceLoader | None = None,
    max_workers: int = MAX_WORKERS,
    retries: int = DEFAULT_RETRIES,
    include_rank_labels: bool | None = None,
) -> dict[str, int]:
    """Settle every cohort once while preserving immutable settled outcomes."""

    moment = _aware_moment(as_of)
    cohorts = model_observation_ledger.load_observation_cohorts(observations_dir)
    existing_batches = observation_outcome_ledger.load_outcome_batches(outcomes_dir)
    unknown_batches = set(existing_batches) - set(cohorts)
    if unknown_batches:
        raise observation_outcome_ledger.ObservationOutcomeConflictError(
            f"observation outcomes have no source cohort: {sorted(unknown_batches)[0]}"
        )

    # Programmatic callers with a fixture loader retain the original stock-only
    # behavior unless they opt in.  The production CLI uses the default loader
    # and therefore always requires registered benchmark evidence.
    rank_labels_enabled = price_loader is None if include_rank_labels is None else bool(include_rank_labels)
    symbols: set[tuple[str, str]] = set()
    for cohort_id, cohort in cohorts.items():
        existing_rows = {
            row["observation_id"]: row
            for row in (existing_batches.get(cohort_id) or {}).get("outcomes", [])
        }
        for prediction in _canonical_predictions(cohort):
            previous = existing_rows.get(prediction["observation_id"])
            if previous is not None and previous.get("status") == "SETTLED":
                continue
            maturity = _aware_moment(prediction["forecast_end_session_close_at"])
            if moment > maturity:
                symbols.add((str(prediction["market"]), str(prediction["code"])))
                if rank_labels_enabled:
                    benchmark = ten_day_rank_model.REGISTERED_BENCHMARKS.get(
                        str(prediction["market"])
                    )
                    if benchmark:
                        symbols.add((str(prediction["market"]), benchmark))

    loader = price_loader or _default_price_loader
    worker_limit = max(1, min(MAX_WORKERS, int(max_workers)))
    fetched: dict[tuple[str, str], tuple[list[dict[str, Any]], str, bool]] = {}
    if symbols:
        with ThreadPoolExecutor(max_workers=min(worker_limit, len(symbols))) as executor:
            futures = {
                executor.submit(_fetch_with_retries, loader, market, code, max(0, int(retries))):
                (market, code)
                for market, code in sorted(symbols)
            }
            for future in as_completed(futures):
                fetched[futures[future]] = future.result()

    def cached_loader(market: str, code: str):
        return fetched.get((market, code), ([], "", False))

    changed = 0
    unchanged = 0
    status_counts: Counter[str] = Counter()
    prediction_count = 0
    for cohort_id, cohort in cohorts.items():
        previous = existing_batches.get(cohort_id)
        batch = observation_outcome_ledger.settle_observation_cohort(
            cohort,
            moment,
            cached_loader,
            existing=previous,
            benchmark_price_loader=cached_loader if rank_labels_enabled else None,
        )
        prediction_count += int(batch["prediction_count"])
        status_counts.update(batch["status_counts"])
        if previous == batch:
            unchanged += 1
        else:
            observation_outcome_ledger.write_outcome_batch(outcomes_dir, batch)
            changed += 1

    return {
        "cohort_count": len(cohorts),
        "prediction_count": prediction_count,
        "pending_maturity_count": status_counts.get("PENDING_MATURITY", 0),
        "pending_data_count": status_counts.get("PENDING_DATA", 0),
        "settled_count": status_counts.get("SETTLED", 0),
        "fetched_symbol_count": len(fetched),
        "changed_cohort_count": changed,
        "unchanged_cohort_count": unchanged,
        "worker_limit": worker_limit,
        "authorizes_production": 0,
        "rank_labels_enabled": int(rank_labels_enabled),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Settle isolated model-observation cohorts")
    parser.add_argument("--observations-dir", type=pathlib.Path, default=OBSERVATIONS)
    parser.add_argument("--outcomes-dir", type=pathlib.Path, default=OUTCOMES)
    parser.add_argument("--as-of")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.observations_dir,
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

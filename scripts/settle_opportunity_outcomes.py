#!/usr/bin/env python3
"""Settle retained opportunity records; register only a verified publication."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import opportunity_outcome_ledger as ledger
from scripts.settle_rule_outcomes import _fetch, _default_price_loader

MAX_WORKERS = 8


def run(picks_dir=None, outcomes_dir=ledger.DEFAULT_OUTCOME_DIRECTORY, *, as_of=None,
        price_loader=None, max_workers=MAX_WORKERS, retries=1,
        register_snapshot=None, published_at=None, register_only=False):
    # picks_dir is accepted for CLI compatibility; archives never generate new
    # predictions implicitly. Only the verified public payload can be registered.
    moment = ledger._aware(as_of or dt.datetime.now(dt.timezone.utc))
    root = pathlib.Path(outcomes_dir)
    existing = ledger.load_opportunity_outcome_batches(root)
    batches = dict(existing)
    if (register_snapshot is None) != (published_at is None):
        raise ValueError("--register-snapshot and --published-at are required together")
    if register_only and register_snapshot is None:
        raise ValueError("--register-only requires --register-snapshot and --published-at")
    workers = max(1, min(MAX_WORKERS, int(max_workers)))
    if register_snapshot is not None:
        snapshot = json.loads(pathlib.Path(register_snapshot).read_text(encoding="utf-8"))
        key = snapshot.get("snapshot_key")
        if ledger._aware(published_at) > moment:
            raise ValueError("published-at cannot be later than as-of")
        batches[key] = ledger.register_opportunity_snapshot(snapshot, published_at=published_at, existing=batches.get(key))
        if register_only:
            # Persist the verified publication before any historical price
            # work. The workflow can upload it immediately even when older
            # observations still need unavailable provider data.
            changed = int(batches[key] != existing.get(key))
            if changed:
                ledger.write_opportunity_outcome_batch(root, batches[key])
            return _run_summary(batches, changed, 0, workers)
    symbols = set()
    for batch in batches.values():
        for row in batch["outcomes"]:
            if row["status"] != "SETTLED" and moment > ledger._aware(row["forecast_end_session_close_at"]):
                symbols.update({(row["market"], row["code"]), (row["market"], row["benchmark_code"])})
    fetched = {}
    if symbols:
        with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as executor:
            futures = {executor.submit(_fetch, price_loader or _default_price_loader, market, code, max(0, min(3, int(retries)))): (market, code) for market, code in sorted(symbols)}
            for future in as_completed(futures):
                fetched[futures[future]] = future.result()
    changed = 0
    for key, batch in list(batches.items()):
        settled = ledger.settle_opportunity_batch(batch, moment, lambda market, code: fetched.get((market, code), ([], "", False)))
        if settled != existing.get(key):
            ledger.write_opportunity_outcome_batch(root, settled)
            changed += 1
        batches[key] = settled
    return _run_summary(batches, changed, len(fetched), workers)


def _run_summary(batches, changed, fetched_count, workers):
    summary = ledger.evaluate_opportunity_performance(batches)
    return {k: summary[k] for k in ("snapshot_count", "prediction_count", "settled_count", "pending_maturity_count", "pending_data_count")} | {"fetched_symbol_count": fetched_count, "changed_snapshot_count": changed, "unchanged_snapshot_count": len(batches) - changed, "worker_limit": workers, "authorizes_production": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--picks-dir", type=pathlib.Path)
    parser.add_argument("--outcomes-dir", type=pathlib.Path, default=ledger.DEFAULT_OUTCOME_DIRECTORY)
    parser.add_argument("--as-of")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--register-snapshot", type=pathlib.Path)
    parser.add_argument("--published-at")
    parser.add_argument("--register-only", action="store_true",
                        help="Persist a verified publication without fetching or settling historical prices")
    print(json.dumps(run(**vars(parser.parse_args())), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

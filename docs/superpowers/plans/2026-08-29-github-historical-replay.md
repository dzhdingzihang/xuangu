# GitHub Historical Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a device-independent GitHub Actions pipeline that replays immutable archived A-share, Hong Kong, and US shortlists against real adjusted trading-day outcomes and publishes an explicitly research-only audit card.

**Architecture:** A new isolated replay contract reads only immutable `data/picks/*.json` snapshots that existed before the corresponding entry session, chooses one canonical archived shortlist per signal-date/market cell, and settles exact next-session-open to tenth-session-close net and benchmark-relative returns. A dedicated GitHub Actions workflow restores the existing adjusted K-line caches, performs bounded provider fetches for missing symbols, validates and commits the replay artifact, then dispatches the normal cloud deployment workflow. The artifact can diagnose historical factor behavior but has no path to set `calibrated`, `participates_in_decision`, `production_eligible`, or `authorizes_production` to true.

**Tech Stack:** Python 3.12, `exchange-calendars`, immutable JSON contracts, `unittest`, GitHub Actions, Cloudflare Worker, vanilla JavaScript.

---

### Task 1: Freeze the archived-shortlist replay contract

**Files:**
- Create: `historical_replay.py`
- Test: `tests/test_historical_replay.py`

- [ ] **Step 1: Write failing discovery tests**

Create fixtures for a legacy top-level A-share decision and a modern three-market snapshot. Assert that discovery:

```python
cohorts, diagnostics = historical_replay.discover_replay_cohorts(picks_dir)
self.assertEqual({row["market"] for row in cohorts}, {"a_share", "hk", "us"})
self.assertTrue(all(row["generated_at"] < row["entry_session_open_at"] for row in cohorts))
self.assertTrue(all(row["authorizes_production"] is False for row in cohorts))
```

Also assert that `latest.json`, malformed timestamps, post-entry snapshots, unsafe filenames, conflicting immutable snapshot identities, and duplicate symbols fail closed or are counted as exclusions rather than silently entering the sample.

- [ ] **Step 2: Run discovery tests and confirm failure**

Run:

```bash
python -m unittest tests.test_historical_replay.HistoricalReplayDiscoveryTests -v
```

Expected: `ModuleNotFoundError: No module named 'historical_replay'`.

- [ ] **Step 3: Implement deterministic discovery**

Implement these public contracts in `historical_replay.py`:

```python
REPLAY_SCHEMA_VERSION = "archived-shortlist-replay-v1"
MODEL_ID = "archived-shortlist-factor-audit-v1"
TRACK = "ARCHIVED_SHORTLIST_REPLAY"
SOURCE_POLICY = "immutable_archived_snapshot_shortlist_v1"

def discover_replay_cohorts(
    picks_dir: pathlib.Path,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]: ...
```

Each cohort must bind `source_snapshot`, canonical JSON SHA-256, generated time, signal date, market calendar identity, exact entry/exit sessions, role (`PRIMARY` or `WATCHLIST`), archived score fields, and a stable prediction digest. Select the latest healthy archived snapshot per `(signal_date, market)` cell and never reconstruct missing candidates from current constituents.

- [ ] **Step 4: Run discovery tests**

Run:

```bash
python -m unittest tests.test_historical_replay.HistoricalReplayDiscoveryTests -v
```

Expected: all discovery tests pass.

### Task 2: Settle exact real-trading-day outcomes and factor diagnostics

**Files:**
- Modify: `historical_replay.py`
- Modify: `tests/test_historical_replay.py`

- [ ] **Step 1: Write failing settlement tests**

Use injected adjusted price loaders to cover:

```python
artifact = historical_replay.build_replay_artifact(
    cohorts,
    as_of="2026-09-30T00:00:00Z",
    price_loader=stock_loader,
    benchmark_price_loader=benchmark_loader,
)
self.assertEqual(artifact["status_counts"]["SETTLED"], 3)
self.assertEqual(artifact["horizon_trade_sessions"], 10)
self.assertFalse(artifact["participates_in_decision"])
self.assertFalse(artifact["authorizes_production"])
```

Assert exact adjusted entry open, tenth-session close, market transaction cost, benchmark-relative return, maximum adverse excursion, pending maturity, pending data, immutable settled-row preservation, signal-date/market equal weighting, and deterministic artifact SHA-256.

- [ ] **Step 2: Run settlement tests and confirm failure**

Run:

```bash
python -m unittest tests.test_historical_replay.HistoricalReplaySettlementTests -v
```

Expected: missing settlement/validation functions.

- [ ] **Step 3: Implement settlement and validation**

Add:

```python
def build_replay_artifact(
    cohorts: Sequence[Mapping[str, Any]],
    *,
    as_of: dt.datetime | str,
    price_loader: PriceLoader,
    benchmark_price_loader: PriceLoader,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]: ...

def validate_replay_artifact(payload: Mapping[str, Any]) -> dict[str, Any]: ...

def public_model_summary(payload: Mapping[str, Any]) -> dict[str, Any]: ...
```

Use registered benchmarks `510300`, `2800.HK`, and `SPY`; round published prices and returns before label calculation; reject unadjusted, unordered, duplicate-date, future-dated, or incomplete price evidence. Preserve a previously valid `SETTLED` row byte-for-byte and allow only pending rows to advance.

- [ ] **Step 4: Run the replay tests**

Run:

```bash
python -m unittest tests.test_historical_replay -v
```

Expected: all replay tests pass.

### Task 3: Add the headless cloud replay entrypoint

**Files:**
- Create: `scripts/build_historical_replay.py`
- Create: `tests/test_build_historical_replay.py`

- [ ] **Step 1: Write failing entrypoint tests**

Assert that the runner reads existing runtime caches first, fetches each missing `(market, symbol)` only once with a bounded worker pool, includes registered benchmarks, preserves an existing settled artifact, writes atomically, supports `--start-date`, `--end-date`, `--max-workers`, `--retries`, `--output`, and `--validate-only`, and never imports or calls Futu/OpenD.

- [ ] **Step 2: Run entrypoint tests and confirm failure**

Run:

```bash
python -m unittest tests.test_build_historical_replay -v
```

Expected: module is missing.

- [ ] **Step 3: Implement the cloud runner**

Load `data/runtime-cache/a_share_daily.json` only when its adjustment policy is `qfq-forward-adjusted-v1`, and load the HK/US cache only under `hk-us-daily-kline-v2`. Fall back to the existing public adjusted-price chain in `scripts.settle_outcomes.market_rows`; cap workers at 12 and retries at 2. Write `data/backtests/archived-shortlist-replay-v1.json` atomically only after full validation.

- [ ] **Step 4: Run entrypoint tests**

Run:

```bash
python -m unittest tests.test_build_historical_replay -v
```

Expected: all entrypoint tests pass.

### Task 4: Publish replay status in the selector and UI

**Files:**
- Modify: `server.py`
- Modify: `scripts/build_worker_assets.py`
- Modify: `static/app.js`
- Modify: `tests/test_selector_v2.py`
- Modify: `tests/test_build_worker_assets.py`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: Write failing publication tests**

Assert that a valid replay artifact is reduced to a bounded `analysis_models.historical_replay` model card, all authority booleans stay false, invalid artifacts produce a `UNAVAILABLE` card, Worker assets retain only summary/metrics and no row-level ledger, and the Model tab describes archived-shortlist coverage rather than full-universe point-in-time coverage.

- [ ] **Step 2: Run publication tests and confirm failure**

Run:

```bash
python -m unittest tests.test_selector_v2 tests.test_build_worker_assets tests.test_frontend_contract -v
```

Expected: historical replay publication assertions fail.

- [ ] **Step 3: Implement bounded publication**

Add a fail-closed loader in `server.py`, attach its public summary to `analysis_models`, whitelist only bounded replay summary fields in `scripts/build_worker_assets.py`, and add a Model-tab card showing settled rows, independent signal days, markets, pending data, actual entry/exit policy, artifact cutoff, and the explicit limitation `archived shortlist only; not historical full universe`.

- [ ] **Step 4: Run publication tests**

Run:

```bash
python -m unittest tests.test_selector_v2 tests.test_build_worker_assets tests.test_frontend_contract -v
node --check static/app.js
```

Expected: all tests and JavaScript syntax checks pass.

### Task 5: Automate replay and deployment entirely on GitHub

**Files:**
- Create: `.github/workflows/historical-replay.yml`
- Modify: `tests/test_workflow_reliability.py`

- [ ] **Step 1: Write failing workflow tests**

Assert that the workflow has daily schedule plus manual inputs, `permissions: {}` at workflow scope, job-scoped `contents: write` and `actions: write`, pinned checkout/setup/cache/upload actions, `timeout-minutes: 40`, a dedicated non-production concurrency group, runtime cache restore, unit tests, replay validation, staging restricted to the single replay JSON, a scoped-token push with `[skip ci]`, and explicit dispatch of `deploy-worker.yml` after a changed artifact.

- [ ] **Step 2: Run workflow tests and confirm failure**

Run:

```bash
python -m unittest tests.test_workflow_reliability.WorkflowReliabilityTests -v
```

Expected: missing workflow assertions fail.

- [ ] **Step 3: Implement the workflow**

Schedule the task after the daily observation-settlement watchdog under its own `xuangu-historical-replay` lock so delayed research cannot block production refreshes. Restore existing adjusted K-line caches, run the replay tests, build and validate the replay artifact, upload it for audit, commit only `data/backtests/archived-shortlist-replay-v1.json`, and retry a scoped-token push up to three times after fetching current `main`. The workflow may request the existing `deploy-worker.yml` through GitHub's workflow-dispatch API after a changed artifact, but it must never hold a Cloudflare secret or deploy directly. No local computer, OpenD, Render, Tunnel, or long-running device process is permitted.

- [ ] **Step 4: Run workflow tests**

Run:

```bash
python -m unittest tests.test_workflow_reliability.WorkflowReliabilityTests -v
```

Expected: all workflow reliability tests pass.

### Task 6: Document operational and statistical boundaries

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the GitHub-only replay**

Add sections covering the data lineage, schedule, manual dispatch inputs, actual 10-session label, adjustment requirements, benchmark registry, immutable settlement behavior, archived-shortlist scope, absence of full historical constituents/news revisions, separation from live cohorts, and the rule that the artifact cannot self-promote.

- [ ] **Step 2: Remove misleading legacy backtest claims**

Mark `data/backtests/may_2026_serenity.json` as legacy/non-authoritative and direct readers to `archived-shortlist-replay-v1.json` for the current cloud-generated research audit.

- [ ] **Step 3: Run documentation contract checks**

Run:

```bash
python -m unittest tests.test_frontend_contract tests.test_workflow_reliability -v
```

Expected: README and UI contract assertions pass.

### Task 7: Validate and release through GitHub Actions

**Files:**
- No additional source files.

- [ ] **Step 1: Run the full deterministic test suite locally without market data generation**

Run:

```bash
python -m unittest discover -s tests -v
node --check src/index.js
node --check static/app.js
node --check scripts/score_dual_low.mjs
```

Expected: all tests and syntax checks pass. Do not invoke the replay price fetcher locally.

- [ ] **Step 2: Commit and push implementation code**

Stage only the intended source, test, workflow, README, and this plan. Preserve existing unrelated untracked plans and `output/`.

- [ ] **Step 3: Trigger the GitHub historical replay workflow**

Use GitHub workflow dispatch against `main` with the default archived date range. The GitHub-hosted runner, not the local machine, must fetch/settle/write the replay artifact.

- [ ] **Step 4: Verify the chained deployment**

Wait for the replay workflow, CI, and explicit Cloudflare deployment workflow to complete. Verify `https://xuangu.alixjd.com/api/latest-summary` exposes the matching `analysis_models.historical_replay.artifact_sha256`, and confirm the Model tab shows the research-only replay card with no executable authority.

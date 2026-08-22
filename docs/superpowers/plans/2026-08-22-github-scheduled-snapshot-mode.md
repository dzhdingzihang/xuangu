# GitHub Scheduled Snapshot Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the A/HK/US selector entirely in GitHub Actions at two weekday decision checkpoints, publish truthful scheduled snapshots through Cloudflare, and remove any production dependency on OpenD or a continuously running personal computer.

**Architecture:** The existing Python selector remains the sole decision engine and keeps its candidate pools, Legacy/V2/dual-low factors, gates, calibration and global ranking. GitHub Actions generates and validates immutable snapshots at 08:17 and 20:17 Asia/Shanghai, with health-aware fallback invocations at 08:47 and 20:47. Cloudflare serves only published snapshot data; the browser never polls an upstream quote source or recomputes scores, and `/api/live` remains only as a snapshot-backed compatibility contract.

**Tech Stack:** Python 3.12, `requests`, `exchange-calendars`, GitHub Actions, Cloudflare Workers/Assets, vanilla JavaScript, Node.js, `unittest`.

---

## File map

- Create `docs/superpowers/plans/2026-08-22-github-scheduled-snapshot-mode.md`: implementation and verification record.
- Modify `.github/workflows/deploy-worker.yml`: two primary weekday runs and two fallback invocations.
- Modify `scripts/schedule_gate.py`: two business checkpoints with health-aware fallback behavior.
- Modify `src/index.js`: scheduled-snapshot status metadata and snapshot-only `/api/live` compatibility.
- Modify `wrangler.jsonc`: remove the production quote-gateway binding.
- Modify `static/index.html`, `static/app.js` and `static/styles.css`: expose snapshot generation/next-refresh times and remove 15-second quote polling.
- Modify `README.md`: document the selector, schedule, failure semantics and no-device architecture truthfully.
- Modify scheduling, Worker and frontend contract tests before implementation.
- Regenerate `public/` with `npm run build`; never hand-edit generated assets.

### Task 1: Lock the two-checkpoint scheduling contract

**Files:**
- Modify: `tests/test_schedule_gate.py`
- Modify: `tests/test_workflow_reliability.py`
- Modify: `scripts/schedule_gate.py`
- Modify: `.github/workflows/deploy-worker.yml`

- [x] **Step 1: Write failing scheduling tests**

Assert the exact business slots and UTC cron expressions:

```python
self.assertEqual(schedule_gate.SLOTS, [(8, 17), (20, 17)])
self.assertIn("17 0,12 * * 1-5", workflow)
self.assertIn("47 0,12 * * 1-5", workflow)
```

Add cases showing that a healthy 08:17 snapshot makes the 08:47 invocation skip, a degraded snapshot retries, an 08:17 snapshot never suppresses the 20:47 fallback, and a slot older than four hours is rejected.

- [x] **Step 2: Run focused tests and confirm failure**

Run: `python3 -m unittest tests.test_schedule_gate tests.test_workflow_reliability -v`
Expected: failures referencing the old 08:58–23:58 checkpoint set and old cron entries.

- [x] **Step 3: Implement the two-slot gate and workflow schedule**

Use only these business slots in Python:

```python
SLOTS = [(8, 17), (20, 17)]
```

Use four GitHub invocations, while keeping fallback times out of `SLOTS` so a healthy primary snapshot is not regenerated:

```yaml
- cron: "17 0,12 * * 1-5"
- cron: "47 0,12 * * 1-5"
```

Retain `cancel-in-progress: false`; each queued fallback re-evaluates snapshot health after the primary finishes.

- [x] **Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_schedule_gate tests.test_workflow_reliability -v`
Expected: all focused tests pass.

### Task 2: Make the Worker snapshot-only

**Files:**
- Modify: `tests/test_worker_freshness.py`
- Modify: `tests/test_worker_contract.py`
- Modify: `src/index.js`
- Modify: `wrangler.jsonc`

- [x] **Step 1: Write failing Worker contract tests**

Require `/api/status` to return:

```json
{
  "data_mode": "scheduled_snapshot",
  "quote_delivery_mode": "scheduled_snapshot",
  "device_dependency": false,
  "schedule_time_zone": "Asia/Shanghai",
  "schedule_primary_checkpoints": ["08:17", "20:17"],
  "schedule_fallback_checkpoints": ["08:47", "20:47"]
}
```

Require `snapshot_as_of` and a future weekday `next_refresh`. Require `/api/live` to read an allow-listed candidate from the loaded snapshot, perform zero upstream `fetch` calls, set `provider_class=SCHEDULED_SNAPSHOT`, `is_realtime=false` and retain `contract_version=live-quote-v1` for compatibility. Assert production configuration contains no `REALTIME_GATEWAY_URL`, `xuangu-quotes` or `FUTU_OPEND` reference.

- [x] **Step 2: Run focused tests and confirm failure**

Run: `python3 -m unittest tests.test_worker_freshness tests.test_worker_contract tests.test_workflow_reliability -v`
Expected: failures for old checkpoints, gateway-preference behavior and request-time quote fetches.

- [x] **Step 3: Implement status metadata and next-refresh calculation**

Set:

```javascript
const WEEKDAY_CHECKPOINTS = [[8, 17], [20, 17]];
const FALLBACK_CHECKPOINTS = [[8, 47], [20, 47]];
```

Calculate `next_refresh` in Asia/Shanghai by scanning the two primary and two health-fallback checkpoints across subsequent weekdays. Use the loaded snapshot's `generated_at` as `snapshot_as_of`.

- [x] **Step 4: Replace request-time quote fetching with snapshot lookup**

Find an allow-listed candidate in the three market decisions or `global_decision`. Publish a compatibility quote only when the candidate has a positive `realtime.price`, timezone-aware `source_as_of` and `fetched_at`, and an explicit volume unit. Missing provenance returns a structured unavailable response; it never promotes an entry price, generic price, K-line close or snapshot generation time into a quote. Return delayed/last-close semantics only; never claim `REALTIME`.

Remove gateway variables and upstream live-source functions from the production Worker, and remove `REALTIME_GATEWAY_URL` from `wrangler.jsonc`. The legacy local gateway utility may remain outside the production path.

- [x] **Step 5: Run focused tests**

Run: `python3 -m unittest tests.test_worker_freshness tests.test_worker_contract tests.test_workflow_reliability -v`
Expected: all focused tests pass, including a zero-upstream-fetch assertion.

### Task 3: Make the browser read published snapshots only

**Files:**
- Modify: `tests/test_frontend_contract.py`
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Regenerate: `public/index.html`
- Regenerate: `public/app.js`
- Regenerate: `public/styles.css`

- [x] **Step 1: Write failing frontend contract tests**

Assert that the application contains no `LIVE_POLL_INTERVAL_MS`, `pollVisibleLive`, `state.live` or `/api/live?market=` call. Require `snapshotAsOf`, `nextRefreshTime`, `snapshot_as_of` and `next_refresh`, while preserving the five-minute `/api/status` publication check and the statement that browser refresh does not recompute scores or ranking.

- [x] **Step 2: Run focused tests and confirm failure**

Run: `python3 -m unittest tests.test_frontend_contract -v`
Expected: failures for the current 15-second live overlay and missing next-refresh UI.

- [x] **Step 3: Remove the live overlay and render snapshot timing**

Read observed quotes only from immutable snapshot fields with preserved provenance; otherwise label the saved entry price as a non-market plan price:

```javascript
function candidateQuoteView(candidate) {
  const quote = candidate?.realtime;
  const observed = positive(quote?.price) && quote?.source_as_of && quote?.fetched_at;
  return observed
    ? { kind: "observed_quote", price: quote.price }
    : { kind: "plan_price", price: candidate?.entry_price ?? candidate?.price };
}
```

Delete the live map, loading state, poller, live action buttons and merge logic. Keep the five-minute status poll so an open page detects a newly published snapshot. Relabel prices and health cards as snapshot data, display both the generation time and next planned refresh, and bump static resource versions.

- [x] **Step 4: Build generated assets and run focused tests**

Run: `npm run build`

Run: `python3 -m unittest tests.test_frontend_contract tests.test_build_worker_assets -v`
Expected: all focused tests pass and generated `public/` assets match `static/`.

### Task 4: Document the production truth and operations

**Files:**
- Modify: `README.md`
- Modify: `tests/test_workflow_reliability.py`

- [x] **Step 1: Add documentation contract assertions**

Require README references to `08:17`, `20:17`, `08:47`, `20:47`, `scheduled snapshot`, `Asia/Shanghai`, no-device operation and the fact that GitHub scheduling is not a strict real-time guarantee.

- [x] **Step 2: Rewrite runtime and update-mechanism sections**

Document the immutable pipeline:

```text
public cloud sources -> GitHub Actions selector -> schema validation -> Cloudflare snapshot publication -> browser
```

Explain that candidate pools, factors, Legacy/V2/dual-low scores, gates and global ranking remain in the Python generation step. Explain that generation failure preserves the last validated snapshot instead of publishing partial data. Mark local OpenD tooling as optional legacy development support, not a production dependency.

- [x] **Step 3: Run documentation and workflow tests**

Run: `python3 -m unittest tests.test_workflow_reliability tests.test_frontend_contract -v`
Expected: all focused tests pass.

### Task 5: Full local verification

**Files:**
- Verify all changed and generated files.

- [x] **Step 1: Run syntax and snapshot validation**

Run:

```bash
node --check src/index.js
node --check static/app.js
node --check scripts/score_dual_low.mjs
node --check vendor/stock-scoring-kit/index.js
python3 scripts/validate_snapshot.py data/picks/latest.json
```

Expected: all commands exit zero.

- [x] **Step 2: Run the complete test suite and Worker dry-run**

Run:

```bash
python3 -m unittest discover -s tests -v
npm run build
npm run check
```

Expected: every test passes, assets build successfully and Wrangler validates the Worker bundle without deploying.

- [x] **Step 3: Review the diff for scope and truthfulness**

Run: `git diff --check && git status --short && git diff --stat`
Expected: no whitespace errors, only planned source/test/docs/generated changes, and no secret or local-machine path in production configuration.

### Task 6: Publish and verify production

**Files:**
- Commit and push the verified change set to `main`.

- [ ] **Step 1: Commit and push**

Run:

```bash
git add .github/workflows/deploy-worker.yml scripts/schedule_gate.py src/index.js wrangler.jsonc static public tests README.md docs/superpowers/plans/2026-08-22-github-scheduled-snapshot-mode.md
git commit -m "feat: run selector as scheduled cloud snapshots"
git push origin HEAD:main
```

Expected: push succeeds and starts the Cloudflare deployment workflow.

- [ ] **Step 2: Wait for deployment and inspect its logs**

Run: `gh run list --workflow deploy-worker.yml --limit 3` followed by `gh run watch <run-id> --exit-status`.
Expected: tests, asset build, deploy and production verification jobs all succeed.

- [ ] **Step 3: Verify the public contracts**

Check `https://xuangu.alixjd.com/`, `/api/status`, `/api/history` and an allow-listed `/api/live` compatibility request. Expected:

- root and API responses return HTTP 200;
- `/api/status` reports `scheduled_snapshot`, `device_dependency=false`, the four planned times, `snapshot_as_of` and `next_refresh`;
- `/api/live` reports `SCHEDULED_SNAPSHOT` and `is_realtime=false` without depending on OpenD;
- the history tab receives valid nonempty structured data;
- the page renders the snapshot generation and next planned refresh times.

- [ ] **Step 4: Record operating limits accurately**

Report that weekday primary and fallback schedules materially improve availability but GitHub Actions may start late or, under load, fail to run. Do not describe the twice-daily snapshot as real-time market data or as a guaranteed profit signal.

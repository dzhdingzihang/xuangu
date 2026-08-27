# Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make XuanGu fail closed on stale data, recover safely from delayed schedulers, load the decision screen from bounded assets, and turn the observation ledger into a real ten-session settlement pipeline without overstating model readiness.

**Architecture:** Keep immutable full snapshots as the audit source of truth, but derive small identity-bound Worker assets for the UI. Treat freshness as a delivery-time execution gate, never rewrite the historical production decision. Relocate late GitHub cron jobs to the latest legal checkpoint, preserve monotonic deployment ordering, and settle model observations in a separate non-executable ledger.

**Tech Stack:** Python 3.12, JavaScript ES modules, Cloudflare Workers/Wrangler, GitHub Actions, unittest, immutable JSON ledgers.

---

### Task 1: Recover delayed scheduled runs without falsifying their checkpoint

**Files:**
- Modify: `scripts/schedule_gate.py`
- Modify: `server.py`
- Modify: `scripts/validate_snapshot.py`
- Modify: `.github/workflows/deploy-worker.yml`
- Test: `tests/test_schedule_gate.py`
- Test: `tests/test_snapshot_contract.py`
- Test: `tests/test_deployment_order_guard.py`
- Test: `tests/test_workflow_reliability.py`

- [ ] **Step 1: Add failing late-recovery tests**

```python
def test_nine_hour_late_primary_recovers_latest_legal_checkpoint(self):
    output = self.run_main(
        "2026-08-27T17:52:00+08:00",
        published_source=None,
        cron="17 0 * * 1-5",
    )
    self.assertIn("should_run=true", output)
    self.assertIn("reason=late_cron_recovery", output)
    self.assertIn("slot=2026-08-27T16:17+08:00", output)
    self.assertIn("invocation_slot=2026-08-27T16:47+08:00", output)
    self.assertIn("source_invocation_slot=2026-08-27T08:17+08:00", output)

def test_late_recovery_skips_when_latest_checkpoint_is_already_healthy(self):
    output = self.run_main(
        "2026-08-27T17:52:00+08:00",
        published_source="live",
        cron="17 0 * * 1-5",
    )
    self.assertIn("should_run=false", output)
    self.assertIn("slot_already_published", output)
```

- [ ] **Step 2: Run the focused tests and confirm failure**

```bash
python3 -m unittest tests.test_schedule_gate tests.test_snapshot_contract tests.test_deployment_order_guard tests.test_workflow_reliability -v
```

Expected: the new late-recovery metadata and workflow conditions are absent.

- [ ] **Step 3: Implement a legal recovery intent**

Add a pure resolver that retains the source invocation but selects the latest configured recovery invocation at or before `now`:

```python
def resolve_schedule_intent(now: dt.datetime, cron: str | None) -> dict[str, object]:
    source_invocation = select_cron_invocation(now, cron)
    if source_invocation and checkpoint_is_within_window(now, source_invocation):
        effective_invocation = source_invocation
        mode = "on_time"
    else:
        effective_invocation = select_latest_configured_invocation(now)
        mode = "late_cron_recovery"
    return {
        "mode": mode,
        "source_invocation": source_invocation,
        "effective_invocation": effective_invocation,
        "checkpoint": checkpoint_for_invocation(effective_invocation),
    }
```

Require the recovered invocation to be one of the existing fourteen configured slots, no more than twelve hours old, and not already covered by a healthy deployed snapshot. Emit `source_invocation_slot`, `scheduler_delay_seconds`, and `recovery_mode` alongside the existing `slot` and `invocation_slot` outputs.

- [ ] **Step 4: Persist and validate recovery metadata**

Extend `automation_metadata()` with:

```python
"source_invocation_slot": os.environ.get("SCHEDULED_SOURCE_INVOCATION_SLOT") or None,
"scheduler_delay_seconds": int(os.environ["SCHEDULER_DELAY_SECONDS"])
    if os.environ.get("SCHEDULER_DELAY_SECONDS") else None,
"recovery_mode": os.environ.get("SCHEDULE_RECOVERY_MODE") or "none",
```

Validate that recovery timestamps are aware, the source invocation is not in the future, delay is non-negative, and the effective invocation/checkpoint mapping remains legal.

- [ ] **Step 5: Route scheduled-like dispatches through every safety gate**

Add `workflow_dispatch` inputs `scheduler`, `cron`, and `scheduled_at`. Compute a `scheduled_like` output when `scheduler == 'cloudflare-cron-v1'`; run `schedule_gate.py`, cache restore/save, generation, validation, deployment-order guard, archive, and rollback with the same conditions used by native schedule events. Preserve ordinary manual dispatch behavior.

- [ ] **Step 6: Run focused tests**

```bash
python3 -m unittest tests.test_schedule_gate tests.test_snapshot_contract tests.test_deployment_order_guard tests.test_workflow_reliability -v
```

Expected: all tests pass, and late jobs never claim to represent their original old checkpoint.

### Task 2: Publish a freshness-bound execution and bootstrap contract

**Files:**
- Modify: `scripts/build_worker_assets.py`
- Modify: `src/index.js`
- Modify: `wrangler.jsonc`
- Test: `tests/test_build_worker_assets.py`
- Test: `tests/test_worker_contract.py`
- Test: `tests/test_worker_freshness.py`

- [ ] **Step 1: Add failing bounded-asset and freshness tests**

```javascript
const stale = snapshotUseContract(runtime, new Date("2026-08-27T22:25:00+08:00"));
assert.equal(stale.mode, "HISTORICAL_RESEARCH_ONLY");
assert.equal(stale.current_decision_allowed, false);
assert.deepEqual(stale.blocker_codes, ["SNAPSHOT_NOT_FRESH"]);
```

Assert that `/api/latest-summary` never reads `/data/picks/latest.json`, rejects identity mismatches, preserves the published historical qualification, and exposes zero effective current candidates when freshness is not `fresh`.

- [ ] **Step 2: Run the focused tests and confirm failure**

```bash
python3 -m unittest tests.test_build_worker_assets tests.test_worker_contract tests.test_worker_freshness -v
```

- [ ] **Step 3: Build three immutable UI assets**

Generate `ui-bootstrap.json`, `ui-candidates.json`, and `ui-events.json`. Every asset must contain the same identity envelope:

```json
{
  "contract_version": "ui-bootstrap-v1",
  "snapshot_key": "...",
  "generated_at": "...",
  "source_snapshot": {"sha256": "...", "byte_size": 123}
}
```

`ui-bootstrap.json` contains decision summaries, no more than twenty qualified summaries, market-health scalars, primary evidence, and model status. It must exclude `evaluated_candidates`, `production_rule_inputs`, `point_in_time_universe`, full event lists, and K-line arrays, and remain at or below 192 KiB. Candidate and event assets must remain at or below 768 KiB and 512 KiB respectively.

- [ ] **Step 4: Add a fail-closed delivery contract**

```javascript
export function snapshotUseContract(runtime, current = new Date()) {
  const freshness = snapshotFreshness(runtime.automation?.scheduled_slot || runtime.generated_at, current);
  const allowed = freshness.freshness_state === "fresh";
  return {
    contract_version: "snapshot-use-v1",
    mode: allowed ? "CURRENT_RESEARCH" : "HISTORICAL_RESEARCH_ONLY",
    freshness_state: freshness.freshness_state,
    current_decision_allowed: allowed,
    execution_review_allowed: allowed && runtime.global_decision?.action === "REVIEW_EXECUTABLE_PICK",
    blocker_codes: allowed ? [] : ["SNAPSHOT_NOT_FRESH"],
    evaluated_at: new Date(current).toISOString(),
    snapshot_key: runtime.snapshot_key,
    source_snapshot_sha256: runtime.source_snapshot?.sha256,
    source_snapshot_byte_size: runtime.source_snapshot?.byte_size,
  };
}
```

Expose it from `/api/status`, `/api/latest-summary`, `/api/candidates`, `/api/events`, and `/api/live`. Keep `/api/latest` unchanged for audit compatibility.

- [ ] **Step 5: Add Cloudflare cron dispatch support without a public trigger route**

Add the same fourteen UTC cron expressions to `wrangler.jsonc`. Implement only a module `scheduled(controller, env)` handler that validates the cron whitelist and posts a fixed workflow dispatch payload to GitHub using `env.GITHUB_WORKFLOW_DISPATCH_TOKEN`. Missing secret or non-2xx response must throw; never log or return the token.

- [ ] **Step 6: Run focused tests and a dry build**

```bash
python3 -m unittest tests.test_build_worker_assets tests.test_worker_contract tests.test_worker_freshness -v
npm run check
```

Expected: bounded assets satisfy byte limits, all identities match, and dry deployment succeeds.

### Task 3: Make all six tabs respect stale state and load data on demand

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `static/index.html`
- Test: `tests/test_frontend_contract.py`

- [ ] **Step 1: Add failing browser-contract tests**

```javascript
const truth = productionDecisionTruth(snapshot, {
  snapshot_use: {mode: "HISTORICAL_RESEARCH_ONLY", current_decision_allowed: false},
});
assert.equal(truth.currentQualifiedCount, 0);
assert.equal(truth.historicalQualifiedCount, 1);
assert.equal(truth.currentAction, "HISTORICAL_ONLY");
```

Assert that initial load never requests `/api/latest` or `/api/history`, stale candidates use historical wording, and candidates/events/history are requested only after their tabs are opened.

- [ ] **Step 2: Run the focused test and confirm failure**

```bash
python3 -m unittest tests.test_frontend_contract -v
```

- [ ] **Step 3: Replace eager loading with snapshot-bound lazy loading**

```javascript
const TAB_DATA_REQUIREMENTS = {
  decision: [], candidates: ["candidates"], events: ["events"],
  history: ["history"], model: [], health: [],
};

async function initialize() {
  state.bootstrap = await getJson("/api/latest-summary");
  applyBootstrap(state.bootstrap);
  renderAll();
  await ensureTabData(state.tab);
}
```

Each loader captures the current `snapshot_key`; discard its response if a newer bootstrap arrives before completion. `pollStatus()` refreshes only `/api/status` and `/api/latest-summary` when identity changes.

- [ ] **Step 4: Separate published history from current usability**

`productionDecisionTruth()` must return `publishedQualifiedRows`, `historicalQualifiedCount`, `currentQualifiedRows`, `currentQualifiedCount`, and `currentAction`. `syncPreferredCandidate()` may select a historical row for inspection but must not turn it into a current candidate.

- [ ] **Step 5: Apply fail-closed language to every tab**

When not fresh:

- Decision: “历史快照曾规则合格；暂停执行，等待新快照”.
- Candidates: “历史合格·不可执行”; current qualified count is zero.
- Events: evidence remains visible but uses historical tense.
- History: unchanged because it is already historical.
- Model: published rule output is labeled historical.
- Health: `ruleUsable` requires `snapshot_use.current_decision_allowed === true`.

Add a high-contrast blocking banner and remove positive execution-colored styling from stale primary cards.

- [ ] **Step 6: Run focused tests and syntax checks**

```bash
python3 -m unittest tests.test_frontend_contract -v
node --check static/app.js
```

### Task 4: Settle all observation predictions in an isolated ten-session ledger

**Files:**
- Modify: `model_observation_ledger.py`
- Create: `observation_outcome_ledger.py`
- Create: `scripts/settle_observations.py`
- Modify: `history_evaluation.py`
- Modify: `scripts/settle_outcomes.py`
- Test: `tests/test_model_observation_ledger.py`
- Create: `tests/test_observation_outcome_ledger.py`
- Modify: `tests/test_history_evaluation_contract.py`

- [ ] **Step 1: Add failing contract, idempotency, and metric tests**

Require each canonical observation to freeze next-session open/tenth-session close dates, calendar identity, cost, currency, and `settlement_contract_sha256`. Test `PENDING_MATURITY`, `PENDING_DATA`, `SETTLED`, immutable settled rows, hash conflicts, adjusted prices, and strict separation from executable performance.

- [ ] **Step 2: Run the focused tests and confirm failure**

```bash
python3 -m unittest tests.test_model_observation_ledger tests.test_observation_outcome_ledger tests.test_history_evaluation_contract -v
```

- [ ] **Step 3: Freeze the settlement window in the observation contract**

Use `market_calendar.market_trade_window(market, generated_at, horizon_sessions=10)` and store:

```python
{
    "entry_trade_date": window["entry_trade_date"],
    "entry_session_open_at": window["entry_session_open_at"],
    "forecast_end_trade_date": window["forecast_end_trade_date"],
    "forecast_end_session_close_at": window["forecast_end_session_close_at"],
    "horizon_trade_sessions": 10,
    "entry_policy": "next_session_open_v1",
    "exit_policy": "tenth_session_close_v1",
    "calendar_id": window["calendar_id"],
    "calendar_version": window["calendar_version"],
    "currency": CURRENCIES[market],
}
```

Derive and validate `settlement_contract_sha256` from this immutable identity plus `observation_id` and `prediction_sha256`.

- [ ] **Step 4: Implement one outcome file per cohort**

Write `data/outcomes/observation-settlements/<cohort_id>.json`. Each row binds cohort, canonical revision, observation, prediction hash, settlement hash, adjusted entry/exit prices, gross/net return, positive label, sources, and outcome hash. Settled rows are immutable; missing bars remain pending and never become zero returns.

- [ ] **Step 5: Reuse adjusted price loaders with bounded concurrency**

`scripts/settle_observations.py` processes only mature unsettled cohorts, groups symbols by market, uses 12 workers, retries only missing symbols, and writes atomically after full contract validation. A/港/美 use the existing explicit qfq/adjusted chains.

- [ ] **Step 6: Publish observation-only diagnostics**

`evaluate_observation_performance()` reports maturity, pending-data, settled and invalid counts, market coverage, independent cohort days, Brier, Brier skill, AUC, ECE, daily cross-sectional Rank IC, top-decile net return/excess, and worst-decile return. Weight dates and markets equally. Keep `included_in_executable_performance=false` and never auto-authorize production.

- [ ] **Step 7: Run focused tests**

```bash
python3 -m unittest tests.test_model_observation_ledger tests.test_observation_outcome_ledger tests.test_history_evaluation_contract -v
```

Expected: the current cohort reports `PENDING_MATURITY`, not `NOT_IMPLEMENTED`; it cannot settle before 2026-09-09/10.

### Task 5: Integrate, document, deploy, and verify production

**Files:**
- Modify: `.github/workflows/deploy-worker.yml`
- Create: `.github/workflows/settle-observations.yml`
- Modify: `scripts/build_worker_assets.py`
- Modify: `scripts/verify_deployment.py`
- Modify: `README.md`
- Test: `tests/test_workflow_reliability.py`
- Test: `tests/test_snapshot_contract.py`
- Test: `tests/test_worker_contract.py`
- Test: `tests/test_frontend_contract.py`

- [ ] **Step 1: Add the isolated settlement workflow**

Run at Beijing 06:30 on weekdays and on manual dispatch. Restore caches, run `scripts/settle_observations.py`, validate ledgers, commit only changed observation settlement/evaluation assets with fetch/rebase/push retries, then let the normal 08:17 build publish the compact statistics.

- [ ] **Step 2: Extend deployment verification**

Verify `/api/latest-summary`, `/api/candidates`, `/api/events`, `/api/status`, and `/api/history`. Assert shared snapshot identity, bounded response sizes, stale current-candidate count zero, and historical qualification preservation.

- [ ] **Step 3: Update README truthfully**

Document late catch-up, the optional Cloudflare scheduler credential, fail-closed stale UX, bounded UI endpoints, observation maturity/settlement states, and the fact that production probability authorization still requires independent forward cohorts and is not forced by code deployment.

- [ ] **Step 4: Run the complete local gate**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
node --check src/index.js
node --check static/app.js
npm run build
npm run check
```

Expected: all tests pass; no full snapshot is fetched on first render; generated UI assets satisfy limits.

- [ ] **Step 5: Commit and push implementation**

```bash
git add .github README.md docs model_observation_ledger.py observation_outcome_ledger.py history_evaluation.py server.py scripts src static tests wrangler.jsonc
git commit -m "fix: make production selection fail closed and self recovering"
git push origin HEAD:main
```

- [ ] **Step 6: Trigger and monitor a manual production refresh**

```bash
gh workflow run deploy-worker.yml --repo dzhdingzihang/xuangu --ref main
gh run watch --repo dzhdingzihang/xuangu --exit-status
```

Verify the deployed commit, new snapshot identity, current freshness, candidate truth, all six tabs, console, and API response sizes. Do not call a stale rule-qualified row a current recommendation.

- [ ] **Step 7: Enable Cloudflare scheduler only with a dedicated token**

Create a fine-grained GitHub token restricted to `dzhdingzihang/xuangu` with only `Actions: write`, then store it as `GITHUB_WORKFLOW_DISPATCH_TOKEN` using Wrangler. Never reuse `QUOTE_GATEWAY_TOKEN`, `CLOUDFLARE_API_TOKEN`, or a broad local `gh` credential.

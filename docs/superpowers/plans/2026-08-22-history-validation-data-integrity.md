# History Validation Data Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the history tab report truthful daily decision history and real evaluation eligibility instead of treating intraday runs and pre-contract Legacy snapshots as global 10-day predictions.

**Architecture:** Classify every immutable snapshot at manifest-build time as either `global_10d_v1` or `legacy_snapshot`, without synthesizing a global decision for old data. The Worker and local server consolidate raw runs to one archive representative per target date, preferring a formal contract over Legacy and otherwise retaining the latest same-kind run. Evaluation is independent of that archive view: executable predictions are deduplicated by stable `prediction_id`, and only a complete, version-matched settlement contract is eligible. The frontend renders exact API metadata and fails closed when history is unavailable.

**Implementation status:** Tasks 1-4 and the local release gate are complete. Production publication and live verification remain before final handoff.

**Tech Stack:** Python 3 manifest builder and local server, Cloudflare Worker JavaScript, vanilla browser JavaScript, Python `unittest`, Node syntax/Worker contract tests.

---

### Task 1: Lock the Broken Semantics with Regression Tests

**Status:** Complete.

**Files:**
- Modify: `tests/test_worker_contract.py`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: Add a manifest regression test for Legacy and global-contract snapshots**

Create two Legacy snapshots for the same `target_date` and one explicit `global-10d-v1` snapshot. Assert the Legacy summaries remain classified as Legacy and do not receive a fabricated `global_decision`:

```python
self.assertEqual(legacy_summary["history_kind"], "legacy_snapshot")
self.assertEqual(legacy_summary["decision_scope"], "legacy_market_rules")
self.assertEqual(legacy_summary["action"], "LEGACY_ONLY")
self.assertIsNone(legacy_summary["global_decision"])
self.assertEqual(contract_summary["history_kind"], "global_10d_v1")
self.assertEqual(contract_summary["global_decision"]["contract_version"], "global-10d-v1")
```

- [ ] **Step 2: Add a Worker API test for daily consolidation and metadata**

Use a manifest containing two runs for one target date plus one contract run and assert:

```javascript
assert.equal(payload.history.length, 2);
assert.equal(payload.history[0].snapshot_key, "latest-run-for-day.json");
assert.equal(payload.meta.raw_run_count, 3);
assert.equal(payload.meta.decision_day_count, 2);
assert.equal(payload.meta.duplicate_run_count, 1);
assert.equal(payload.meta.global_contract_day_count, 1);
assert.equal(payload.meta.legacy_day_count, 1);
assert.equal(payload.meta.executable_prediction_count, 0);
assert.equal(payload.meta.settled_sample_count, 0);
```

- [ ] **Step 3: Add frontend copy/contract assertions**

Assert the frontend stores `historyPayload.meta`, displays daily decisions separately from raw runs, and never describes Legacy snapshots as global `NO_VALID_PICK` history:

```python
self.assertIn("historyMeta", self.js)
self.assertIn("原始运行", self.js)
self.assertIn("决策日", self.js)
self.assertIn("Legacy 历史日", self.js)
self.assertIn("已结算样本", self.js)
self.assertNotIn("空白代表尚未有可靠评估", self.js)
```

- [ ] **Step 4: Run focused tests and confirm they fail before implementation**

Run:

```bash
python3 -m unittest tests.test_worker_contract tests.test_frontend_contract -v
```

Expected: failures for missing classification, metadata, daily consolidation, and frontend history metadata.

### Task 2: Preserve History Semantics in the Published Manifest

**Status:** Complete.

**Files:**
- Modify: `scripts/build_worker_assets.py:155-259`
- Test: `tests/test_worker_contract.py`

- [ ] **Step 1: Add explicit contract classification**

Implement:

```python
def history_kind(global_decision: dict | None) -> str:
    if (
        isinstance(global_decision, dict)
        and global_decision.get("contract_version") == "global-10d-v1"
        and global_decision.get("decision_scope") == "global_10d"
        and global_decision.get("action_basis") == "strict_cross_market_gate_v1"
    ):
        return "global_10d_v1"
    return "legacy_snapshot"
```

- [ ] **Step 2: Stop fabricating global decisions for old snapshots**

Replace the `GLOBAL_DECISION_MISSING` fallback with explicit Legacy fields:

```python
global_decision = summarize_global_decision(pick)
kind = history_kind(global_decision)
is_global = kind == "global_10d_v1"
summary.update({
    "history_kind": kind,
    "decision_scope": "global_10d" if is_global else "legacy_market_rules",
    "action": (global_decision or {}).get("action") if is_global else "LEGACY_ONLY",
    "title": "全局十日决策" if is_global else "Legacy 规则快照",
    "message": " · ".join((global_decision or {}).get("blocker_codes") or []) if is_global else "PRE_GLOBAL_10D_CONTRACT",
    "has_primary": bool((global_decision or {}).get("primary")) if is_global else False,
    "global_decision": global_decision if is_global else None,
})
```

- [ ] **Step 3: Run the manifest regression test**

Run:

```bash
python3 -m unittest tests.test_worker_contract.WorkerAssetBuildTests -v
```

Expected: PASS.

### Task 3: Return Daily History and Truthful Evaluation Metadata

**Status:** Complete, with the final implementation strengthened to prefer formal contracts for archive representatives and use `prediction_id` for evaluation cohorts.

**Files:**
- Modify: `src/index.js:578-592`
- Modify: `server.py:898-926`
- Test: `tests/test_worker_contract.py`

- [ ] **Step 1: Add latest-run-per-target-date consolidation**

Implement equivalent helpers in JavaScript and Python. The JavaScript contract is:

```javascript
function latestDecisionDays(rows) {
  const byDate = new Map();
  for (const row of rows) {
    const key = row.target_date || row.signal_date || row.snapshot_key;
    if (!byDate.has(key)) byDate.set(key, row);
  }
  return [...byDate.values()];
}
```

Call it only after descending sort so the first row retained for a day is the latest immutable run.

- [ ] **Step 2: Compute metadata from the complete manifest, not the sliced response**

Return:

```javascript
const meta = {
  raw_run_count: rows.length,
  decision_day_count: days.length,
  duplicate_run_count: rows.length - days.length,
  global_contract_day_count: contractDays.length,
  legacy_day_count: legacyDays.length,
  executable_prediction_count: executable.length,
  no_valid_pick_day_count: contractDays.filter((row) => row.global_decision?.action === "NO_VALID_PICK").length,
  pending_settlement_count: executable.filter((row) => row.outcome?.status === "PENDING").length,
  settled_sample_count: executable.filter((row) => row.outcome?.status === "SETTLED").length,
  missing_outcome_count: executable.filter((row) => !["PENDING", "SETTLED"].includes(row.outcome?.status)).length,
};
```

- [ ] **Step 3: Keep raw runs available explicitly**

Use `view=raw` for raw run inspection; default `/api/history` returns consolidated decision days. Preserve the requested `limit` after consolidation.

- [ ] **Step 4: Mirror behavior in the local Python server**

Return the same `meta` keys and default daily consolidation from `history_payload()`. Do not infer settlement from calendar passage alone; only an immutable `outcome.status == "SETTLED"` counts as settled.

- [ ] **Step 5: Run Worker and Python tests**

Run:

```bash
python3 -m unittest tests.test_worker_contract -v
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected: all tests PASS.

### Task 4: Render Real History Coverage Instead of Placeholder Data

**Status:** Complete.

**Files:**
- Modify: `static/app.js:120-132`
- Modify: `static/app.js:1256-1348`
- Modify: `static/app.js:1544-1710`
- Test: `tests/test_frontend_contract.py`

- [ ] **Step 1: Store API history metadata**

Add `historyMeta: {}` to state and assign it for bootstrap, refresh, and polling:

```javascript
state.history = historyPayload.history || [];
state.historyMeta = historyPayload.meta || {};
```

- [ ] **Step 2: Replace the not-ready placeholder header with exact coverage**

Use `historyMeta` to show:

```javascript
const rawRuns = num(meta.raw_run_count);
const decisionDays = num(meta.decision_day_count);
const contractDays = num(meta.global_contract_day_count);
const legacyDays = num(meta.legacy_day_count);
const executable = num(meta.executable_prediction_count);
const settled = num(meta.settled_sample_count);
```

The main status must say `暂无已结算的可执行预测样本` when `settled === 0`, followed by a factual explanation such as `230 次原始运行已合并为 63 个决策日；其中 1 日属于 global-10d-v1，且为 NO_VALID_PICK，因此没有可计算收益的买入样本。`

- [ ] **Step 3: Show operational counts in metric cards**

Display decision days, raw runs, duplicate runs, global-contract days, Legacy days, executable predictions, pending settlements, and settled samples. Keep return, hit-rate, IC, Brier, ECE, drawdown, and Expected Shortfall unavailable until `settled_sample_count > 0` and an outcome aggregate exists.

- [ ] **Step 4: Correct the archive language**

Change the collapsed archive summary to `查看每日决策快照（N 个决策日）`, state that intraday duplicates were consolidated, and label rows as `global-10d-v1` or `Legacy` rather than letting a Legacy market BUY appear to be a global decision.

- [ ] **Step 5: Run frontend contract and syntax checks**

Run:

```bash
python3 -m unittest tests.test_frontend_contract -v
node --check static/app.js
```

Expected: PASS.

### Task 5: Document, Build, and Deploy

**Status:** Documentation and local build gates complete; production publication and verification pending.

**Files:**
- Modify: `README.md`
- Modify: `design-qa.md` only if visual evidence changes materially

- [ ] **Step 1: Document the history data boundary**

Explain that raw runs are immutable audit records, daily history uses the latest run per target date, pre-contract snapshots are Legacy-only, and performance requires an explicit immutable settled outcome.

- [ ] **Step 2: Run the complete release gate**

Run:

```bash
python3 scripts/validate_snapshot.py data/picks/latest.json
python3 -m unittest discover -s tests -p 'test_*.py'
node --check src/index.js
node --check static/app.js
npm run check
git diff --check
```

Expected: snapshot valid, all tests PASS, JavaScript checks PASS, Wrangler dry-run PASS, and no whitespace errors.

- [ ] **Step 3: Commit and publish**

Commit message:

```text
fix: make history validation data contract truthful
```

Update `main` without force, wait for the Cloudflare deployment workflow, and verify `/api/history` metadata plus the live history tab.

- [ ] **Step 4: Verify the production UI**

Confirm the live page shows consolidated decision-day counts, zero settled samples, no Legacy/global semantic mixing, no console errors, and no mobile horizontal overflow.

---

## Self-Review

- Spec coverage: manifest semantics, API consolidation, metadata, frontend display, tests, documentation, and deployment are all covered.
- Placeholder scan: every unavailable metric is deliberately unavailable by contract; the implementation plan contains no unresolved engineering placeholders.
- Type consistency: `history_kind`, `historyMeta`, and every `meta` key use the same spelling across builder, Worker, Python server, frontend, and tests.

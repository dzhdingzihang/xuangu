# History Evaluation V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the history tab from an archive-only view into an honest dual-track evaluation system with executable-model settlements, separate Shadow research tracking, real aggregate metrics, and explicit sample-quality states.

**Architecture:** Keep immutable pick snapshots unchanged. Store Shadow outcomes in the existing `data/outcomes/*.json` location and executable outcomes in `data/outcomes/executable/*.json`, join each track only to its matching prediction contract during the Worker asset build, and compute a versioned evaluation object from validated settled samples. Cloudflare serves the prebuilt evaluation contract; the browser only formats it and never recomputes performance from a sliced daily list.

**Tech Stack:** Python 3, vanilla JavaScript, Cloudflare Workers static assets, GitHub Actions, Python `unittest`, Node syntax checks.

---

### Task 1: Lock the Evaluation Contract with Tests

**Files:**
- Create: `history_evaluation.py`
- Modify: `tests/test_history_evaluation_contract.py`
- Modify: `tests/test_build_worker_assets.py`
- Modify: `tests/test_worker_contract.py`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: Add metric contract fixtures**

Create formal rows with valid `global-10d-v1`, `REVIEW_EXECUTABLE_PICK`, calibrated primary contracts, and matching `SETTLED` outcomes. Assert the evaluator returns metric objects shaped as:

```python
{
    "value": 0.025,
    "unit": "ratio",
    "n": 3,
    "status": "INSUFFICIENT_SAMPLE",
    "min_n": 20,
    "reason": "MINIMUM_SAMPLE_NOT_MET",
}
```

Cover mean net return, positive rate, top-decile positive rate, selection Rank IC, Brier score, ten-bin ECE, 10% expected shortfall, settlement-sequence drawdown, and comparable sample count.

- [ ] **Step 2: Add invalid sample cases**

Assert that mismatched model/label IDs, non-finite numbers, inconsistent `positive_label`, arithmetic mismatches between prices and returns, invalid probabilities, and settlements before the forecast end are excluded rather than coerced to zero.

- [ ] **Step 3: Add ledger separation cases**

Assert that Shadow and executable outcomes with the same prediction ID can coexist in separate storage tracks, that each joins only to its own contract, and that Shadow never increases executable settled counts.

- [ ] **Step 4: Run focused tests and confirm the new assertions fail**

Run:

```bash
python3 -m unittest tests.test_history_evaluation_contract tests.test_build_worker_assets tests.test_worker_contract tests.test_frontend_contract -v
```

Expected: new tests fail because the evaluation object, executable ledger join, and frontend metric renderer do not exist yet.

### Task 2: Add Shared, Strict History Evaluation

**Files:**
- Create: `history_evaluation.py`
- Modify: `server.py:1981-2114`
- Test: `tests/test_history_evaluation_contract.py`

- [ ] **Step 1: Implement strict formal-sample validation**

Expose `valid_formal_settlement(row)` and require:

```python
primary["calibrated"] is True
0.0 <= primary["probability"] <= 1.0
outcome["prediction_id"] == primary["prediction_id"]
outcome["model_id"] == primary["model_id"]
outcome["label_version"] == primary["label_version"]
abs(outcome["gross_total_return"] - (outcome["exit_price"] / outcome["entry_price"] - 1.0)) <= 1e-6
abs(outcome["net_total_return"] - (outcome["gross_total_return"] - outcome["transaction_cost"])) <= 1e-6
```

Retain the existing source, currency, calendar, adjustment, label, and timestamp checks. Return a reason code with an invalid sample so the API can report exclusions.

- [ ] **Step 2: Implement deterministic cohort selection**

First freeze the latest published `(model_id, label_version)`, then keep the latest generated executable prediction for each `target_date`. Within that daily cohort, group by immutable `prediction_id`, accept exactly one identity-consistent valid settlement per group, reject conflicting outcomes, and sort accepted samples by exit timestamp.

- [ ] **Step 3: Implement versioned metrics**

Return:

```python
{
    "schema_version": "history-performance-v1",
    "cohort": "global-10d-v1/executable/settled",
    "sample_status": "NO_SAMPLE" | "EARLY_SAMPLE" | "READY",
    "minimum_reliable_sample": 20,
    "metrics": {
        "mean_net_return": metric(...),
        "positive_rate": metric(...),
        "top_decile_positive_rate": metric(...),
        "selection_rank_ic": metric(...),
        "brier_score": metric(...),
        "ece_10bin": metric(...),
        "expected_shortfall_10pct": metric(...),
        "settlement_sequence_max_drawdown": metric(...),
        "comparable_sample_count": metric(...),
    },
}
```

Use `null`/`None` for unavailable metrics. Rank IC requires at least three samples and non-zero variance; its method text must say it is across historical selected samples, not a same-day cross-sectional IC. The drawdown method must say it is a settlement sequence, not a real portfolio.

- [ ] **Step 4: Use the shared evaluator in the local history API**

Load external outcome ledgers, join formal and Shadow tracks to immutable snapshots in memory, and add `performance` plus `shadow_ledger` to `/api/history`. Preserve the daily/raw archive semantics and all existing count fields.

- [ ] **Step 5: Run evaluator tests**

Run:

```bash
python3 -m unittest tests.test_history_evaluation_contract -v
```

Expected: PASS.

### Task 3: Create and Settle an Executable Outcome Track

**Files:**
- Modify: `scripts/settle_outcomes.py`
- Modify: `tests/test_outcome_ledger.py`
- Modify: `.github/workflows/deploy-worker.yml`

- [ ] **Step 1: Keep the two tracks in separate paths**

Continue writing Shadow contracts to `data/outcomes/pred_*.json`. Write formal contracts to `data/outcomes/executable/pred_*.json` with:

```python
{
    "schema_version": "executable-outcome-v1",
    "track": "EXECUTABLE_MODEL",
    "status": "PENDING",
    "sampling_policy": "all_published_executable_predictions_v1",
}
```

- [ ] **Step 2: Admit only complete executable predictions**

Create a formal contract only when the snapshot is a valid `global-10d-v1`, action is `REVIEW_EXECUTABLE_PICK`, primary is `EXECUTABLE` and calibrated, identity/date/calendar fields exist, probability is in `[0,1]`, cost is finite and non-negative, and the forecast end is exactly the tenth market session.

- [ ] **Step 3: Reuse the price settlement engine without mixing identities**

Both tracks use next-session open and tenth-session close. Freeze the formal prediction probability, expected net utility, cost, model ID, label version, calendar version, currency, and price-source contract. Never recompute an already settled file.

- [ ] **Step 4: Make recovery collection recursive**

Change the recovery/archive file scan from:

```python
pathlib.Path("data/outcomes").glob("*.json")
```

to:

```python
pathlib.Path("data/outcomes").rglob("*.json")
```

Rename the workflow step and comments from Shadow-only wording to dual-track outcome wording.

- [ ] **Step 5: Run ledger and workflow tests**

Run:

```bash
python3 -m unittest tests.test_outcome_ledger tests.test_workflow_reliability -v
```

Expected: PASS.

### Task 4: Publish One Evaluation Contract Through Cloudflare

**Files:**
- Modify: `scripts/build_worker_assets.py`
- Modify: `src/index.js:438-524`
- Modify: `src/index.js:727-746`
- Test: `tests/test_build_worker_assets.py`
- Test: `tests/test_worker_contract.py`

- [ ] **Step 1: Read ledgers with track-aware keys**

Read existing root outcomes as Shadow and `data/outcomes/executable` as executable. Reject filename/identity mismatches and attach:

```python
summary["shadow_outcome"] = matching_outcome(pick, "SHADOW_RESEARCH")
summary["outcome"] = matching_outcome(pick, "EXECUTABLE_MODEL")
```

Never overwrite an immutable source snapshot.

- [ ] **Step 2: Build ledger metadata from full data, not the daily slice**

Publish separate `shadow_ledger` and `executable_ledger` objects with raw, eligible, pending, settled, excluded, and conflict counts. Shadow must retain `included_in_executable_performance: false`.

- [ ] **Step 3: Build the evaluation object once**

Call the shared Python evaluator after all summaries have been enriched and store the result as `manifest.history_evaluation`.

- [ ] **Step 4: Return the prebuilt contract from the Worker**

Keep archive counts computed from all manifest summaries, but set:

```javascript
meta.performance = manifest.history_evaluation?.performance || emptyPerformance();
meta.shadow_ledger = manifest.history_evaluation?.shadow_ledger || emptyShadowLedger();
meta.executable_ledger = manifest.history_evaluation?.executable_ledger || emptyExecutableLedger();
```

Do not derive Shadow totals from the limited daily response.

- [ ] **Step 5: Run Worker build and API tests**

Run:

```bash
python3 -m unittest tests.test_build_worker_assets tests.test_worker_contract -v
node --check src/index.js
npm run build
```

Expected: PASS and generated `public/data/picks/manifest.json` contains the versioned evaluation object.

### Task 5: Render Real Metrics and Honest Sample States

**Files:**
- Modify: `static/app.js:1366-1538`
- Modify: `static/styles.css`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: Delete frontend-derived Shadow totals**

Replace `shadowLedgerStats(state.history)` with `state.historyMeta.shadow_ledger`. Show eligible samples, raw ledger count, exclusions, pending, and settled separately.

- [ ] **Step 2: Format metric contracts**

Implement one renderer that displays a number only when `value` is finite and status is `READY` or `INSUFFICIENT_SAMPLE`. For `NO_SAMPLE`, `NOT_APPLICABLE`, or `UNAVAILABLE`, display an em dash and a precise reason, except that an explicitly published zero comparable-sample count remains `0`. Use percent formatting for return/rate/drawdown metrics and decimals for Brier/ECE/Rank IC.

- [ ] **Step 3: Replace placeholder cards**

Remove `settled ? "待聚合" : "无样本"`. Bind each card to the matching backend metric and label `selection_rank_ic` as “历史已选样本 Rank IC” and drawdown as “结算序列最大回撤”. Add an “早期样本” badge until `minimum_reliable_sample` is reached.

- [ ] **Step 4: Make row status explicit**

Show formal state (`Legacy`, `主动放弃`, `可执行·待结算`, `可执行·已结算`, `结算无效`) independently from Shadow state (`Shadow·PENDING`, `Shadow·SETTLED`). Keep the detail warning that Shadow never enters executable performance.

- [ ] **Step 5: Add a Shadow research panel**

Explain that Shadow tests the research ranking only. If settled Shadow samples exist, display their own count and aggregate return separately; otherwise show the exact waiting/exclusion state.

- [ ] **Step 6: Run UI checks**

Run:

```bash
python3 -m unittest tests.test_frontend_contract -v
node --check static/app.js
```

Expected: PASS.

### Task 6: Document, Verify, Publish, and Inspect Production

**Files:**
- Modify: `README.md`
- Modify: `design-qa.md` if screenshots change materially

- [ ] **Step 1: Document the dual-track history model**

Explain immutable archives, daily consolidation, formal executable settlements, Shadow research settlements, ten-session entry/exit policies, fixed cost assumptions, and the minimum-sample warning.

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

Expected: snapshot valid, all tests pass, both JavaScript files parse, Wrangler dry-run succeeds, and no whitespace errors exist.

- [ ] **Step 3: Commit and publish without rewriting history**

Use a normal commit and push to `main`; do not force-push. Let the existing serialized GitHub Actions workflow build and deploy Cloudflare.

- [ ] **Step 4: Verify production**

Check `/api/history?limit=1000`, confirm `performance.schema_version`, verify Shadow/executable counts, confirm no unavailable metric is displayed as zero, and visually inspect the desktop and mobile history tab.

# Ten-Day Shadow Probability Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `planned` placeholder with an auditable ten-session shadow probability model that uses only completed daily bars, chronological purged splits, held-out calibration, explicit costs and tail risk, while keeping production execution fail-closed until point-in-time live evidence is sufficient.

**Architecture:** A new pure-Python `ten_day_model.py` owns features, labels, chronological splitting, ridge logistic fitting, Platt calibration, validation metrics, risk estimates and deterministic model contracts. `server.py` supplies the three market K-line caches and in-memory candidate pools before `enrich_snapshot_v2`, publishes shadow predictions separately from formal predictions, and leaves `participates_in_decision=false`. The frontend exposes shadow probability and validation evidence without relabeling it as a formal buy probability.

**Tech Stack:** Python 3.12 standard library, `exchange-calendars`, existing JSON K-line caches, vanilla JavaScript, `unittest`, GitHub Actions, Cloudflare Workers.

---

## File map

- Create `ten_day_model.py`: deterministic model implementation and contract builder; it must not import `server.py`.
- Create `tests/test_ten_day_model.py`: feature cutoffs, labels, purged splits, calibration, metrics, determinism and fail-closed coverage.
- Modify `server.py`: retain longer K-line history, attach the shadow contract before global decision construction, and copy shadow evidence into evaluated candidates without treating it as formal evidence.
- Modify `scripts/validate_snapshot.py`: validate the shadow model schema, finite probabilities, provenance and production-ineligible state.
- Modify `scripts/build_worker_assets.py`: retain a compact model-card summary and candidate shadow fields in published assets.
- Modify `static/app.js`: render model state, validation evidence and a clearly labeled shadow probability column/detail.
- Modify `README.md`: document the statistical method, current-universe backfill limitation and promotion requirements.
- Modify `.github/workflows/deploy-worker.yml`: rotate daily K-line cache keys so the longer history is fetched once and then reused.

### Task 1: Pure model primitives

**Files:**
- Create: `ten_day_model.py`
- Test: `tests/test_ten_day_model.py`

- [ ] **Step 1: Write failing feature and label tests**

```python
def test_feature_vector_ignores_future_rows(self):
    base = synthetic_rows(80)
    first = feature_vector(base, 40)
    second = feature_vector(base + synthetic_future_rows(5), 40)
    self.assertEqual(first, second)

def test_label_is_next_open_to_tenth_close_net_of_cost(self):
    rows = synthetic_rows(50)
    label = ten_session_label(rows, 20, transaction_cost=0.003)
    expected = rows[30]["close"] / rows[21]["open"] - 1.0 - 0.003
    self.assertAlmostEqual(label.net_return, expected)
    self.assertEqual(label.positive, expected > 0)
```

- [ ] **Step 2: Run tests and verify the missing module failure**

Run: `python -m unittest tests.test_ten_day_model -v`

Expected: FAIL because `ten_day_model` and its public functions do not exist.

- [ ] **Step 3: Implement immutable feature and label contracts**

```python
FEATURE_NAMES = (
    "return_1", "return_5", "return_10", "return_20",
    "ma_5_gap", "ma_10_gap", "ma_20_gap",
    "volatility_10", "volatility_20", "drawdown_20",
    "range_position_20", "volume_ratio_5_20", "atr_14",
)

@dataclass(frozen=True)
class Label:
    entry_price: float
    exit_price: float
    gross_return: float
    transaction_cost: float
    net_return: float
    positive: bool

def ten_session_label(rows, signal_index, transaction_cost):
    entry = round(float(rows[signal_index + 1]["open"]), 8)
    exit_ = round(float(rows[signal_index + 10]["close"]), 8)
    gross = exit_ / entry - 1.0
    net = gross - transaction_cost
    return Label(entry, exit_, gross, transaction_cost, net, net > 0.0)
```

`feature_vector(rows, signal_index)` must use only indices `<= signal_index`, require 21 valid completed bars, return finite floats in `FEATURE_NAMES` order, and reject zero/invalid OHLC values.

- [ ] **Step 4: Run the focused tests**

Run: `python -m unittest tests.test_ten_day_model -v`

Expected: feature and label tests PASS.

### Task 2: Date-grouped purged training and calibration

**Files:**
- Modify: `ten_day_model.py`
- Modify: `tests/test_ten_day_model.py`

- [ ] **Step 1: Add failing split and determinism tests**

```python
def test_split_keeps_dates_together_and_purges_ten_sessions(self):
    split = chronological_split(samples, calibration_days=20, test_days=20, purge_days=10)
    self.assertTrue(set(split.train_dates).isdisjoint(split.calibration_dates))
    self.assertTrue(set(split.calibration_dates).isdisjoint(split.test_dates))
    self.assertLess(max(split.train_signal_index) + 10, min(split.calibration_signal_index))
    self.assertLess(max(split.calibration_signal_index) + 10, min(split.test_signal_index))

def test_artifact_is_deterministic_for_shuffled_input(self):
    self.assertEqual(build_shadow_model(rows).artifact_sha256,
                     build_shadow_model(list(reversed(rows))).artifact_sha256)
```

- [ ] **Step 2: Implement standardization and ridge logistic fitting**

Use deterministic batch gradient descent with clipped logits, date-equal sample weights and L2 regularization. Fit means, standard deviations and coefficients only on the train fold. Constant features use standard deviation `1.0`.

```python
def sigmoid(value):
    value = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-value))

def fit_logistic(matrix, labels, weights, *, l2=0.02, steps=180, rate=0.08):
    coefficients = [0.0] * (len(matrix[0]) + 1)
    # deterministic full-batch updates; regularize feature coefficients only
    return coefficients
```

- [ ] **Step 3: Implement held-out Platt calibration**

Fit `sigmoid(a * logit(raw_probability) + b)` using only the calibration dates. The untouched test dates must never influence coefficients, scaler or calibrator.

- [ ] **Step 4: Implement validation metrics**

Publish test-only `brier_score`, `baseline_brier_score`, `brier_skill`, `ece_10bin`, `auc`, `positive_rate`, `mean_net_return`, `top_decile_mean_net_return`, `expected_shortfall_10pct`, row counts and independent date counts. Empty or single-class folds return `INSUFFICIENT_DATA`, never a fake zero.

- [ ] **Step 5: Run the model tests**

Run: `python -m unittest tests.test_ten_day_model -v`

Expected: all split, calibration, metric and determinism tests PASS.

### Task 3: Build the shadow model contract

**Files:**
- Modify: `ten_day_model.py`
- Modify: `tests/test_ten_day_model.py`

- [ ] **Step 1: Add failing contract tests**

```python
def test_backfill_model_can_never_self_authorize_production(self):
    contract = build_snapshot_model_contract(snapshot, kline_maps, generated_at)
    self.assertIn(contract["status"], {"SHADOW_READY", "SHADOW_REJECTED", "INSUFFICIENT_DATA"})
    self.assertFalse(contract["calibrated"])
    self.assertFalse(contract["participates_in_decision"])
    self.assertFalse(contract["production_eligible"])
    self.assertEqual(contract["training_provenance"], "current_universe_historical_backfill")

def test_shadow_predictions_are_bounded_and_cost_consistent(self):
    for row in contract["shadow_predictions"]:
        self.assertGreaterEqual(row["probability"], 0.0)
        self.assertLessEqual(row["probability"], 1.0)
        self.assertAlmostEqual(row["expected_net_utility"],
                               row["expected_net_return"] - 0.25 * row["tail_risk"])
```

- [ ] **Step 2: Implement per-market artifacts and predictions**

Use costs `a_share=0.0015`, `hk=0.0030`, `us=0.0015`. A market is `SHADOW_READY` only when it has enough independent train/calibration/test dates and finite held-out metrics. Overall status is `SHADOW_READY` when at least one market passes; it remains formally `calibrated=false` because the universe history is backfilled from today's membership.

- [ ] **Step 3: Freeze the model card**

The contract must include stable `model_id=ten-day-technical-shadow-v1`, `label_version=r10-net-total-return-v1`, `feature_schema_version=technical-d1-v1`, `training_cutoff`, `training_provenance`, `market_models`, `validation`, `limitations`, `artifact_sha256`, `shadow_predictions`, and formal readiness booleans.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_ten_day_model -v`

Expected: all tests PASS and JSON serialization uses `allow_nan=False`.

### Task 4: Selector and snapshot integration

**Files:**
- Modify: `server.py`
- Modify: `tests/test_global_decision_contract.py`
- Modify: `tests/test_snapshot_contract.py`

- [ ] **Step 1: Add failing integration tests**

```python
def test_shadow_model_does_not_unlock_formal_decision(self):
    snapshot = fixture_with_shadow_contract()
    decision = server.build_global_ten_day_decision(snapshot)
    self.assertEqual(decision["action"], "NO_VALID_PICK")
    self.assertIsNone(decision["primary"])
    self.assertIsNotNone(decision["research_priority"]["shadow_model"])
```

- [ ] **Step 2: Expand runtime history retention**

Set A-share and HK/US model history retention to 260 sessions, rotate cache schema to `*-daily-kline-v2`, require a healthy cache to satisfy both freshness and minimum history, and use Yahoo `range=1y`. Existing deep-score K-line payloads remain compact; only the Actions cache grows.

- [ ] **Step 3: Attach the model before enrichment**

In `run_selector`, after building `result` and before `enrich_snapshot_v2(result)`, load the three runtime cache maps and call `build_snapshot_model_contract`. Any expected sample shortage publishes `INSUFFICIENT_DATA`; integrity exceptions fail closed to an explicit `UNAVAILABLE` model card and do not affect Legacy generation.

- [ ] **Step 4: Join shadow evidence into evaluated candidates**

`build_global_ten_day_decision` must keep formal `_candidate_prediction` unchanged. Separately match `shadow_predictions` by `(market, code)`, publish a nested `shadow_model` on evaluated rows and the selected research priority, and sort eligible research rows by shadow expected net utility when available, otherwise by existing rule priority.

- [ ] **Step 5: Run selector contract tests**

Run: `python -m unittest tests.test_ten_day_model tests.test_global_decision_contract tests.test_snapshot_contract -v`

Expected: shadow output is visible, formal action remains fail-closed, and all prior strict-contract tests PASS.

### Task 5: Published contract and frontend

**Files:**
- Modify: `scripts/validate_snapshot.py`
- Modify: `scripts/build_worker_assets.py`
- Modify: `static/app.js`
- Modify: `tests/test_build_worker_assets.py`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: Add failing validation and UI contract tests**

Require rejection of non-finite/out-of-range shadow probability, a shadow model that claims `participates_in_decision=true`, missing provenance, mismatched model ids, or missing held-out validation. Assert the UI contains “影子概率” and never calls it “正式上涨概率”.

- [ ] **Step 2: Validate and summarize the model card**

Keep only audit-safe model metadata, validation metrics and prediction counts in history summaries. The latest snapshot may retain candidate shadow predictions; historical list rows need only model id/status/revision and selected research shadow evidence.

- [ ] **Step 3: Render three honest states**

- `PRODUCTION`: “10 日概率模型已参与严格门禁”.
- `SHADOW_READY`: “10 日概率模型影子运行中”; show held-out days, Brier/ECE/AUC and the current-universe backfill limitation.
- Other: “10 日概率模型数据积累中”; show exact reason codes.

Add an “影子 P10” candidate column and detail item sourced only from `shadow_model.probability`; append “不参与正式决策”. Continue to display formal executable count independently.

- [ ] **Step 4: Run published-contract tests and JS syntax checks**

Run: `python -m unittest tests.test_build_worker_assets tests.test_frontend_contract -v && node --check static/app.js`

Expected: PASS.

### Task 6: Workflow, documentation and release gate

**Files:**
- Modify: `.github/workflows/deploy-worker.yml`
- Modify: `README.md`
- Modify: `tests/test_workflow_reliability.py`

- [ ] **Step 1: Rotate cache keys**

Change A/HK/US daily cache restore/save prefixes from `*-d1-v1-` to `*-d1-v2-`, matching the longer on-disk schema. Do not add a second training invocation; model fitting occurs once inside snapshot generation after caches are populated.

- [ ] **Step 2: Document the model card and promotion policy**

Explain the 10-session label, completed-bar features, date-grouped purge, held-out Platt calibration, costs, Expected Shortfall, current-universe survivorship limitation, and why formal execution remains disabled. State that production promotion requires a point-in-time universe ledger and sufficient independent live Shadow days.

- [ ] **Step 3: Run the complete release gate**

Run:

```bash
python -m unittest discover -s tests -v
python scripts/validate_snapshot.py data/picks/latest.json
node --check src/index.js
node --check static/app.js
npm run check
git diff --check
```

Expected: all Python tests PASS, snapshot valid, both JavaScript checks PASS, Wrangler dry-run PASS and no whitespace errors.

- [ ] **Step 4: Generate one local forced snapshot with restored caches**

Run `python server.py --once --force`, validate that the model status is one of the documented shadow states, probabilities are bounded, and `global_decision.action` remains `NO_VALID_PICK` unless a separately authorized production model and complete event evidence exist.

- [ ] **Step 5: Commit, push and verify Cloudflare**

Commit code and docs, push normally to `main`, wait for the deployment workflow, then trigger one `workflow_dispatch` run to exercise cache refresh, training, snapshot generation, settlement, deployment and archive. Verify `/api/latest`, `/api/history`, desktop 1440×1000 and mobile 390×844 with zero browser console errors.

## Self-review

- Spec coverage: model math, point-in-time feature cutoff, strict labels, calibration, costs, tail risk, fail-closed integration, UI, documentation and cloud execution all have explicit tasks.
- No production bypass: the current-universe backfill contract is structurally unable to set `participates_in_decision=true`.
- Type consistency: `shadow_predictions` are separate from formal `predictions`; evaluated candidates expose one nested `shadow_model`, and formal history continues to use only `global_decision.primary`.
- Scope boundary: automatic official event ingestion and production authorization are separate follow-up subsystems; this plan exposes that blocker rather than fabricating scanned evidence.

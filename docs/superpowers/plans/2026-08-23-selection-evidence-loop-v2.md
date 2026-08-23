# Selection Evidence Loop V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable cloud-only evidence and forward-validation loop without relaxing the current executable-pick gate.

**Architecture:** Keep the existing `SHADOW_RESEARCH` and `EXECUTABLE_MODEL` tracks unchanged. Add a fail-closed official-event collector, a daily point-in-time universe and model-observation cohort, and a parallel excess-return ranker contract that remains `COLLECTING` until genuine walk-forward evidence exists. Cloudflare continues serving immutable GitHub-generated snapshots only.

**Tech Stack:** Python 3.12, `requests`, stdlib HTML/XML parsers, exchange-calendars, unittest, Cloudflare Workers, GitHub Actions.

---

### Task 1: Lock the event decision contract

**Files:**
- Create: `event_pipeline.py`
- Create: `tests/test_event_pipeline.py`
- Modify: `server.py`
- Modify: `tests/test_global_decision_contract.py`

- [ ] **Step 1: Add failing gate and time-window tests**

```python
def test_ready_empty_pipeline_never_unlocks_candidate(self):
    snapshot = executable_builder_input()
    snapshot["events"]["items"] = []
    decision = server.build_global_ten_day_decision(snapshot)
    self.assertEqual(decision["action"], "NO_VALID_PICK")
    self.assertIn("VERIFIED_POSITIVE_EVENT_MISSING", decision["blocker_codes"])

def test_recent_material_negative_event_blocks_candidate(self):
    snapshot = executable_builder_input()
    snapshot["events"]["items"].append(recent_verified_negative_fixture())
    decision = server.build_global_ten_day_decision(snapshot)
    self.assertIn("MATERIAL_NEGATIVE_EVENT", us_candidate(decision)["blocker_codes"])
```

- [ ] **Step 2: Implement a run-bound event manifest**

```python
PIPELINE_SCHEMA = "official-event-pipeline-v1"
ALLOWED_EVENT_HOSTS = {
    "cninfo": {"static.cninfo.com.cn", "www.cninfo.com.cn"},
    "hkex": {"www1.hkexnews.hk"},
    "sec": {"www.sec.gov", "data.sec.gov"},
}

def collect_event_pipeline(snapshot: dict, generated_at: str, *, fetcher=None) -> dict:
    """Return items plus source manifests; any incomplete source is DEGRADED."""
```

- [ ] **Step 3: Require candidate-specific positive evidence**

```python
if not positive_event:
    candidate_blockers.append("VERIFIED_POSITIVE_EVENT_MISSING")
if not candidate_event_scan_complete:
    candidate_blockers.append("EVENT_CANDIDATE_NOT_SCANNED")
```

- [ ] **Step 4: Separate released-event and scheduled-event time rules**

```python
def positive_event_for_candidate(item, snapshot):
    return verified(item, snapshot) and item["direction"] == "positive" and recent_or_scheduled(item, snapshot)

def material_negative_for_candidate(item, snapshot):
    return verified(item, snapshot) and item["direction"] == "negative" and recent_risk_window(item, snapshot)
```

- [ ] **Step 5: Run focused tests**

Run: `python -m unittest tests.test_event_pipeline tests.test_global_decision_contract -v`

Expected: all event and global decision tests pass; `READY_EMPTY` remains a completed scan but cannot unlock a pick.

### Task 2: Collect official A/HK/US evidence

**Files:**
- Modify: `event_pipeline.py`
- Create: `tests/fixtures/events/cninfo.json`
- Create: `tests/fixtures/events/hkex.html`
- Create: `tests/fixtures/events/sec.json`
- Modify: `tests/test_event_pipeline.py`

- [ ] **Step 1: Add fixture parsers**

```python
def fetch_cninfo_events(candidates, generated_at, session): ...
def fetch_hkex_events(candidates, generated_at, session): ...
def fetch_sec_events(candidates, generated_at, session): ...
```

- [ ] **Step 2: Normalize every record into the same evidence contract**

```python
{
    "event_id": stable_event_id,
    "pipeline_run_id": run_id,
    "source_id": "cninfo|hkex|sec",
    "source_record_id": source_record_id,
    "market": market,
    "symbol": symbol,
    "title": title,
    "published_at": published_at,
    "effective_at": effective_at,
    "direction": "positive|neutral|negative",
    "materiality": "normal|high|critical",
    "url": official_https_url,
    "content_sha256": sha256,
    "evidence_status": "verified",
    "ingestion_mode": "automatic",
}
```

- [ ] **Step 3: Fail closed on mapping, pagination, content type, host, or timestamp errors**

Run: `python -m unittest tests.test_event_pipeline -v`

Expected: official fixtures pass; fabricated hosts, future releases, stale manifests, partial scans and malformed records fail.

### Task 3: Add the point-in-time universe and parallel ranker contract

**Files:**
- Create: `ten_day_rank_model.py`
- Create: `tests/test_ten_day_rank_model.py`
- Modify: `server.py`
- Modify: `scripts/validate_snapshot.py`

- [ ] **Step 1: Freeze all recalled members, including missing-model rows**

```python
snapshot["point_in_time_universe"] = {
    "schema_version": "point-in-time-universe-v1",
    "observed_at": snapshot["generated_at"],
    "markets": {
        "a_share": freeze_recall_rows(hot_rows, 300),
        "hk": freeze_recall_rows(hk_universe, 200),
        "us": freeze_recall_rows(us_universe, 300),
    },
}
```

- [ ] **Step 2: Implement continuous excess-return model primitives**

```python
def ten_session_excess_label(stock_rows, benchmark_rows, signal_index, cost): ...
def fit_weighted_ridge(matrix, targets, weights, l2=0.1): ...
def expanding_walk_forward_splits(samples, train_days=100, test_days=20, blocks=3): ...
def ranking_validation_metrics(records): ...
```

- [ ] **Step 3: Publish v2 as collection-only**

```python
{
    "model_id": "ten-day-excess-rank-shadow-v2",
    "status": "COLLECTING",
    "training_provenance": "prospective_point_in_time_universe",
    "calibrated": False,
    "production_eligible": False,
    "participates_in_decision": False,
}
```

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_ten_day_rank_model tests.test_snapshot_contract -v`

Expected: all full membership and no-self-authorization tests pass.

### Task 4: Add a third, observation-only ledger

**Files:**
- Create: `model_observation_ledger.py`
- Create: `tests/test_model_observation_ledger.py`
- Modify: `scripts/settle_outcomes.py`
- Modify: `history_evaluation.py`
- Modify: `scripts/build_worker_assets.py`

- [ ] **Step 1: Register every valid model output at the daily 22:47 slot**

```python
def build_observation_batch(snapshot: dict) -> dict | None:
    """Record all shadow predictions without requiring rank_eligible."""

def write_observation_batch(batch: dict, root: pathlib.Path) -> pathlib.Path:
    """Write one immutable cohort file; conflicting identity fails closed."""
```

- [ ] **Step 2: Keep track denominators isolated**

```python
assert observation["included_in_executable_performance"] is False
assert observation["included_in_shadow_strategy_performance"] is False
```

- [ ] **Step 3: Publish only compact observation summaries to the Worker**

```python
manifest["history_evaluation"]["observation_ledger"] = {
    "cohort_count": cohort_count,
    "prediction_count": prediction_count,
    "pending_count": pending_count,
    "settled_count": settled_count,
    "eligible_prediction_count": eligible_count,
}
```

- [ ] **Step 4: Run ledger tests**

Run: `python -m unittest tests.test_model_observation_ledger tests.test_outcome_ledger tests.test_history_evaluation_contract -v`

Expected: rejected and negative-utility predictions are observed, while executable and Shadow denominators remain unchanged.

### Task 5: Make status and UI wording truthful

**Files:**
- Modify: `src/index.js`
- Modify: `static/app.js`
- Modify: `tests/test_worker_freshness.py`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: Separate publication freshness from source freshness**

```javascript
status.publication_state = publicationState(snapshot);
status.source_state_by_market = sourceStateByMarket(snapshot);
status.snapshot_age_minutes = ageMinutes(snapshot.generated_at);
status.schedule_delay_minutes = scheduleDelayMinutes(snapshot);
```

- [ ] **Step 2: Show the observation cohort independently in History**

```javascript
const observation = state.historyMeta.observation_ledger || {};
// Render observed / pending / settled; never call it executable performance.
```

- [ ] **Step 3: Replace realtime-like wording**

Use `计划批次已发布` and `批次行情，非实时流`; fixed costs remain documented as assumptions rather than complete account costs.

- [ ] **Step 4: Run frontend and Worker tests**

Run: `python -m unittest tests.test_worker_freshness tests.test_frontend_contract tests.test_worker_contract -v`

Expected: publication state and quote-source state are distinct and the browser never upgrades server authority.

### Task 6: Harden archive monotonicity and publish

**Files:**
- Create: `scripts/archive_snapshot_payload.py`
- Modify: `.github/workflows/deploy-worker.yml`
- Modify: `tests/test_workflow_reliability.py`
- Modify: `README.md`

- [ ] **Step 1: Prevent an older recovery payload from replacing a newer remote latest.json**

```python
if remote_generated_at > payload_generated_at:
    preserve_remote_latest()
    merge_only_missing_immutable_files_and_monotonic_ledgers()
elif remote_generated_at == payload_generated_at and remote_sha != payload_sha:
    raise ArchiveConflict("same timestamp with different snapshot digest")
```

- [ ] **Step 2: Add event and observation assets to recovery archives**

The recovery manifest must list immutable snapshot, event manifest, observation cohorts, Shadow outcomes and executable outcomes.

- [ ] **Step 3: Run the complete release gate**

Run:

```bash
python -m unittest discover -s tests -v
node --check src/index.js
node --check static/app.js
npm run build
python scripts/validate_snapshot.py data/picks/latest.json
```

Expected: every command exits 0.

- [ ] **Step 4: Generate, commit, push and verify production**

Generate one manual snapshot, deploy through the existing tested workflow, then verify `/`, `/api/status`, `/api/latest`, `/api/history`, all six tabs, immutable snapshot identity and GitHub Actions success. A `NO_VALID_PICK` result is expected until the official evidence and forward model gates genuinely pass.

# Multi-Market Refresh Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the device-free weekday snapshot schedule from two primary checkpoints to seven checkpoints aligned with A-share, Hong Kong, and US trading phases, with a 30-minute health fallback for every primary checkpoint and one independent Shadow outcome sample per day.

**Architecture:** Keep GitHub Actions as the scheduler and Cloudflare Workers as the read-only snapshot host. Define the same primary and fallback checkpoint contract in the schedule gate, Worker status/freshness code, and independent deployment verifier; tests pin the exact schedule so drift fails before deployment.

**Tech Stack:** GitHub Actions cron, Python 3.12, Cloudflare Workers JavaScript, Node.js 22, unittest.

---

### Task 1: Pin the seven-checkpoint contract in tests

**Files:**
- Modify: `tests/test_schedule_gate.py`
- Modify: `tests/test_worker_freshness.py`
- Modify: `tests/test_worker_contract.py`
- Modify: `tests/test_workflow_reliability.py`

- [ ] **Step 1: Replace the two-slot expectations with the new primary and fallback arrays**

```python
expected_primary = [
    (8, 17), (10, 17), (12, 17), (15, 17),
    (16, 17), (20, 17), (22, 47),
]
expected_fallback = [
    "08:47", "10:47", "12:47", "15:47",
    "16:47", "20:47", "23:17",
]
```

- [ ] **Step 2: Add boundary assertions for midday, Asia close, US open, fallback, Friday, and weekend transitions**

```javascript
assert.equal(
  nextScheduledRefresh(new Date("2026-08-24T22:48:00+08:00")),
  "2026-08-24T23:17:00+08:00",
);
assert.equal(
  nextScheduledRefresh(new Date("2026-08-24T23:18:00+08:00")),
  "2026-08-25T08:17:00+08:00",
);
```

- [ ] **Step 3: Run the focused tests and verify they fail against the old schedule**

Run: `python -m unittest tests.test_schedule_gate tests.test_worker_freshness tests.test_worker_contract tests.test_workflow_reliability -v`

Expected: failures showing the old `08:17 / 20:17` arrays and old cron contract.

### Task 2: Implement the schedule in every runtime contract

**Files:**
- Modify: `.github/workflows/deploy-worker.yml`
- Modify: `scripts/schedule_gate.py`
- Modify: `src/index.js`
- Modify: `scripts/verify_deployment.py`

- [ ] **Step 1: Add the seven primary checkpoints and paired fallbacks**

```python
SLOTS = [
    (8, 17), (10, 17), (12, 17), (15, 17),
    (16, 17), (20, 17), (22, 47),
]
```

```javascript
const WEEKDAY_CHECKPOINTS = [
  [8, 17], [10, 17], [12, 17], [15, 17],
  [16, 17], [20, 17], [22, 47],
];
const FALLBACK_CHECKPOINTS = [
  [8, 47], [10, 47], [12, 47], [15, 47],
  [16, 47], [20, 47], [23, 17],
];
```

- [ ] **Step 2: Configure explicit UTC cron invocations**

```yaml
- cron: "17 0,2,4,7,8,12 * * 1-5"
- cron: "47 14 * * 1-5"
- cron: "47 0,2,4,7,8,12 * * 1-5"
- cron: "17 15 * * 1-5"
```

- [ ] **Step 3: Update the independent deployment verifier to require the exact fourteen invocation times**

```python
SCHEDULED_REFRESH_CHECKPOINTS = (
    (8, 17), (8, 47), (10, 17), (10, 47),
    (12, 17), (12, 47), (15, 17), (15, 47),
    (16, 17), (16, 47), (20, 17), (20, 47),
    (22, 47), (23, 17),
)
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m unittest tests.test_schedule_gate tests.test_worker_freshness tests.test_worker_contract tests.test_workflow_reliability -v`

Expected: all focused tests pass.

### Task 3: Prevent intraday refreshes from inflating Shadow history

**Files:**
- Modify: `scripts/settle_outcomes.py`
- Modify: `scripts/build_worker_assets.py`
- Test: `tests/test_outcome_ledger.py`

- [ ] **Step 1: Prove that scheduled morning snapshots are excluded and the 22:47 checkpoint is eligible**

```python
morning["automation"] = {"trigger": "schedule", "scheduled_slot": "2026-08-21T10:17:00+08:00"}
closing["automation"] = {"trigger": "schedule", "scheduled_slot": "2026-08-21T22:47:00+08:00"}
self.assertIsNone(candidate_contract(morning, "morning.json"))
self.assertIsNotNone(candidate_contract(closing, "closing.json"))
```

- [ ] **Step 2: Gate scheduled ledger registration on the daily final primary checkpoint**

```python
DAILY_SCHEDULED_LEDGER_SLOT = (22, 47)

def eligible_for_shadow_ledger(snapshot):
    automation = snapshot.get("automation")
    automation = automation if isinstance(automation, dict) else {}
    trigger = str(automation.get("trigger") or "")
    if not trigger:
        return True
    if trigger != "schedule":
        return False
    try:
        scheduled = dt.datetime.fromisoformat(str(automation.get("scheduled_slot") or ""))
    except ValueError:
        return False
    if scheduled.tzinfo is None or scheduled.utcoffset() is None:
        return False
    scheduled = scheduled.astimezone(CN_TZ)
    return (scheduled.hour, scheduled.minute) == DAILY_SCHEDULED_LEDGER_SLOT
```

- [ ] **Step 3: Publish the sampling policy with the outcome and run ledger tests**

Run: `python -m unittest tests.test_outcome_ledger tests.test_build_worker_assets -v`

Expected: scheduled runs create at most one eligible Shadow sample per decision day while all raw pick snapshots remain archived.

### Task 4: Publish the schedule truthfully in the UI and README

**Files:**
- Modify: `static/app.js`
- Modify: `static/index.html`
- Modify: `README.md`

- [ ] **Step 1: Update frontend fallback labels to the seven primary and seven recovery checkpoints**

```javascript
const primarySchedule = (
  status.schedule_primary_checkpoints ||
  ["08:17", "10:17", "12:17", "15:17", "16:17", "20:17", "22:47"]
).join(" / ");
```

- [ ] **Step 2: Document what each primary checkpoint observes**

```text
08:17 盘前与隔夜收盘；10:17 A/H 早盘；12:17 亚洲午间；
15:17 A 股收盘；16:17 港股收盘；20:17 美股盘前；22:47 美股开盘。
```

- [ ] **Step 3: Bump the browser script cache key**

```html
<script src="/static/app.js?v=20260823-multi-checkpoints"></script>
```

- [ ] **Step 4: Run frontend and documentation contract tests**

Run: `node --check static/app.js && python -m unittest tests.test_frontend_contract tests.test_workflow_reliability -v`

Expected: JavaScript syntax succeeds and all contract tests pass.

### Task 5: Verify, publish, and prove the unattended loop

**Files:**
- Generated: `dist/`
- Generated by workflow: `data/picks/latest.json`
- Generated by workflow: `data/picks/<snapshot_key>.json`

- [ ] **Step 1: Run the full local suite and build**

Run: `python -m unittest discover -s tests -v && npm run build && git diff --check`

Expected: all tests pass, Worker assets build, and no whitespace errors appear.

- [ ] **Step 2: Commit and push the implementation to `main`**

```bash
git add .github/workflows/deploy-worker.yml scripts/schedule_gate.py src/index.js scripts/verify_deployment.py static/app.js static/index.html README.md tests docs/superpowers/plans/2026-08-23-multi-market-refresh-checkpoints.md
git commit -m "feat: add multi-market refresh checkpoints"
git push git@github.com:dzhdingzihang/xuangu.git HEAD:main
```

- [ ] **Step 3: Dispatch one full cloud refresh and wait for deploy and archive jobs**

Run: `gh workflow run deploy-worker.yml --ref main`

Expected: both `deploy` and `archive` conclude `success`.

- [ ] **Step 4: Verify the production status contract**

Run: `curl -fsS https://xuangu.alixjd.com/api/status | jq '{schedule_primary_checkpoints,schedule_fallback_checkpoints,next_refresh,device_dependency,freshness_state}'`

Expected: seven primary checkpoints, seven fallback checkpoints, `device_dependency=false`, and a non-null `next_refresh` matching the next exact invocation.

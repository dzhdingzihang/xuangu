# Cloudflare Worker Runtime Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the complete V3 snapshot without making every Worker API request parse the 9.8 MB, 800-stock document.

**Architecture:** Keep `/data/picks/latest.json` as the complete browser and audit artifact, but stream it directly for `/api/latest` and `/api/pick`. After the independent build-time validator has rebuilt the V3 decision, derive a snapshot-bound status summary for `/api/status` and a small candidate/quote index for `/api/live`; the Worker never replays the 798/800-row rule ledger inside an HTTP request.

**Tech Stack:** Python 3.12 asset builder, Cloudflare Workers JavaScript, `unittest`, Node.js contract probes, GitHub Actions, Wrangler.

---

### Task 1: Specify bounded runtime assets

**Files:**
- Modify: `tests/test_build_worker_assets.py`
- Modify: `tests/test_worker_contract.py`

- [ ] **Step 1: Write failing asset-builder tests**

Add assertions that a build creates `public/data/picks/runtime.json` and `public/data/picks/live-index.json`, that both carry the same `snapshot_key` and `generated_at` as `latest.json`, and that the live index contains only the fields consumed by `snapshotLiveContract`:

```python
runtime = json.loads((public / "data/picks/runtime.json").read_text())
live_index = json.loads((public / "data/picks/live-index.json").read_text())
self.assertEqual(runtime["contract_version"], "worker-runtime-v1")
self.assertEqual(live_index["contract_version"], "worker-live-index-v1")
self.assertEqual(runtime["snapshot_key"], snapshot["snapshot_key"])
self.assertEqual(live_index["snapshot_key"], snapshot["snapshot_key"])
self.assertNotIn("events", runtime)
self.assertNotIn("global_decision", live_index)
```

- [ ] **Step 2: Write failing Worker routing tests**

Use an `ASSETS.fetch` test double that throws if `/api/status` or `/api/live` reads `/data/picks/latest.json`; assert status reads `runtime.json`, live reads `live-index.json`, while `/api/latest` and `/api/pick?snapshot=...` return the full asset response without calling `Response.json()` inside the Worker.

- [ ] **Step 3: Run focused tests and confirm the expected failures**

Run:

```bash
/tmp/xuangu-py312.EeOtnx/bin/python -m unittest tests.test_build_worker_assets tests.test_worker_contract -v
```

Expected: new runtime/live-index assertions fail because the assets and routes do not exist yet.

### Task 2: Build deterministic decision and quote indexes

**Files:**
- Modify: `scripts/build_worker_assets.py`
- Test: `tests/test_build_worker_assets.py`

- [ ] **Step 1: Add compact candidate projection**

Implement one projection that retains exactly `code`, `symbol`, `name`, `currency`, `realtime`, and `kline`, normalizes A/HK/US codes, deduplicates candidates, and includes market primary, blocked, watchlist, global primary/research-priority, and every production-qualified candidate.

```python
LIVE_CANDIDATE_FIELDS = ("code", "symbol", "name", "currency", "realtime", "kline")

def compact_live_candidate(candidate: dict) -> dict:
    return {
        key: copy.deepcopy(candidate[key])
        for key in LIVE_CANDIDATE_FIELDS
        if key in candidate
    }
```

- [ ] **Step 2: Write the runtime decision asset**

Publish only identity fields, schedule identity, quote-health summaries, the already-validated compact `production_decision`, source snapshot SHA-256/byte size, and a prebuilt latest summary. Do not copy rule inputs, market pools, events, research rows, candidate snapshots, or global/production evaluated candidates.

- [ ] **Step 3: Write the live quote index**

Publish a market/code mapping and reject the build if a projected candidate lacks a positive snapshot quote, timezone-aware `source_as_of`/`fetched_at`, or a valid market volume unit.

- [ ] **Step 4: Run the asset-builder tests**

Run:

```bash
/tmp/xuangu-py312.EeOtnx/bin/python -m unittest tests.test_build_worker_assets -v
```

Expected: all asset-builder tests pass and both derived assets are materially smaller than the full latest snapshot.

### Task 3: Route APIs without parsing the full snapshot

**Files:**
- Modify: `src/index.js`
- Modify: `tests/test_worker_contract.py`
- Modify: `tests/test_worker_freshness.py`
- Modify: `scripts/verify_deployment.py`

- [ ] **Step 1: Add runtime and live-index readers**

Reject missing or mismatched `contract_version`, identity fields, source-snapshot binding metadata, malformed production summaries, or malformed candidate maps. Keep full V3 deterministic rebuilding in the generator, independent snapshot validator, and browser contract check rather than spending Cloudflare request CPU on all 798/800 rows.

- [ ] **Step 2: Stream full JSON endpoints**

Return the static asset body directly for `/api/latest` and `/api/pick`, preserving JSON content type and setting `Cache-Control: no-store`; never parse and re-serialize the 9.8 MB document in the Worker.

- [ ] **Step 3: Route bounded APIs**

Use `runtime.json` for `/api/status` and `/api/latest-summary`, and `live-index.json` for `/api/live`. Preserve every existing response field and error/status contract.

- [ ] **Step 4: Make deployment verification prove the optimized route**

Require successful status, full latest hash equality, immutable snapshot hash equality, and live responses for all visible candidates. Record response sizes so a regression cannot silently route status/live back through the full snapshot.

- [ ] **Step 5: Run focused and full verification**

Run:

```bash
/tmp/xuangu-py312.EeOtnx/bin/python -m unittest tests.test_build_worker_assets tests.test_worker_contract tests.test_worker_freshness tests.test_workflow_reliability -v
/tmp/xuangu-py312.EeOtnx/bin/python -m unittest discover -s tests -v
node --check src/index.js
node --check static/app.js
npm run build
npx --no-install wrangler deploy --dry-run
```

Expected: all tests and syntax checks pass; `runtime.json` and `live-index.json` are bounded; Wrangler dry-run succeeds.

### Task 4: Publish and verify V3 production

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the serving split**

Explain that the complete 800-stock snapshot remains the audit source, while Worker decision and quote endpoints consume deterministic bounded indexes generated from the same immutable snapshot.

- [ ] **Step 2: Commit and deploy**

Commit only the runtime-index implementation, tests, plan, and README; push to `main`, wait for the code deployment, then dispatch one full scheduled-snapshot workflow.

- [ ] **Step 3: Verify production identity and candidates**

Require V3 model identity, `QUALIFIED_PICK`, exact 300/200/300 recall, successful live contracts for every displayed candidate, and visually inspect Decision, Candidates, Events, Model, and History tabs.

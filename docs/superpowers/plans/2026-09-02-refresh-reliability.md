# Refresh Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make scheduled stock-selection snapshots refresh reliably without a local computer, make returning browser tabs verify freshness immediately, and remove the validation defects that recently blocked otherwise successful publications.

**Architecture:** Cloudflare Cron becomes an independent online dispatcher for the existing GitHub Actions snapshot workflow while the native GitHub schedules remain a fallback. The published snapshot remains the single source of truth. The browser keeps its five-minute poll and checkpoint timer, but also performs one debounced status check after visibility, page-cache, focus, or network recovery. Snapshot generation and deployment keep their fail-closed contracts; the broken Hong Kong provenance and manual-publication SLO paths are fixed at their sources rather than weakening validation.

**Tech Stack:** Cloudflare Workers and Cron Triggers, GitHub Actions, Python 3 and unittest, vanilla JavaScript, Node.js, Wrangler.

---

### Task 1: Lock the browser refresh behavior with failing tests

**Files:**
- Modify: `tests/test_frontend_contract.py`

- [x] Add a Node-backed contract test that calls the resume-refresh helper while the document is hidden, then visible, and proves repeated lifecycle events collapse to one `pollStatus()` call.
- [x] Assert listeners exist for `visibilitychange`, `pageshow`, `focus`, and `online`.
- [x] Add a contract test proving manual refresh reports `success` only for a new snapshot and `info` when the published snapshot identity is unchanged.
- [x] Run `python -m unittest tests.test_frontend_contract.FrontendContractTests -v` and confirm the new tests fail before implementation.

### Task 2: Refresh immediately after browser resume

**Files:**
- Modify: `static/app.js`

- [x] Add `RESUME_REFRESH_DEBOUNCE_MS = 250`, one timer, a visible-state guard, and a helper that routes all resume events into the existing concurrency-safe `pollStatus()` path.
- [x] Install lifecycle listeners only after the first bootstrap attempt has completed so initial load and `pageshow` do not race.
- [x] Return the existing `snapshotChanged` identity comparison from `applyBootstrapPayload()`.
- [x] Replace the unconditional manual-refresh success toast with a pure notice helper that distinguishes a new snapshot from an unchanged current snapshot.
- [x] Re-run the frontend contract tests and `node --check static/app.js`.

### Task 3: Remove snapshot publication validation failures

**Files:**
- Modify: `server.py`
- Modify: `scripts/validate_snapshot.py`
- Modify: `scripts/publish_data_assets.py`
- Modify: `tests/test_snapshot_contract.py`
- Modify: `tests/test_publish_data_assets.py`

- [x] Add failing coverage for Hong Kong intraday-scaled candidates that retain their market observation timestamp through international scoring.
- [x] Preserve source-specific Hong Kong market-cap provenance. EastMoney rows identify total market cap field `f20`; Sina rows identify their actual market-cap field only when positive evidence exists.
- [x] Make pool-health manifest validation and snapshot validation use the same provenance semantics.
- [x] Add a failing manual-publication test for a non-initializing invocation without a computable checkpoint delay.
- [x] Fail that non-initializing SLO closed as `false`; retain `null` only for an initializing ledger and recompute it for invocations with checkpoint timing.
- [x] Run the focused snapshot and publishing tests.

### Task 4: Enable and verify the independent Cloudflare scheduler

**Files:**
- Modify: `wrangler.jsonc`
- Modify: `tests/test_worker_contract.py`
- Modify: `tests/test_workflow_reliability.py`
- Modify: `.github/workflows/deploy-worker.yml`

- [x] Change `CLOUDFLARE_SCHEDULER_ENABLED` to `1`; retain the existing Cloudflare cron list and GitHub schedules so either provider can initiate a checkpoint.
- [x] Keep the Worker contract fail-closed: Cloudflare dispatch becomes active only when both the configuration flag and `GITHUB_WORKFLOW_DISPATCH_TOKEN` secret are present.
- [ ] Provision the minimally scoped Worker secret without exposing its value; a missing secret remains an explicit status gap and does not block GitHub fallback deployment.
- [x] Preserve `schedule_gate.py` deduplication so a delayed native GitHub schedule skips after the same checkpoint was already published by Cloudflare.

### Task 5: Verify, publish, and observe the live system

**Files:**
- Verify all modified files and generated Worker assets.

- [x] Run focused impacted suites (238 tests), `node --check static/app.js`, `node --check src/index.js`, Python compile checks, and `git diff --check`.
- [ ] Build the Worker assets using the repository build command and verify the working tree contains only intended source/generated changes.
- [ ] Commit the repair on top of the latest remote `main`, rebase if an automated data commit landed concurrently, and push to GitHub.
- [ ] Wait for the deployment workflow and verify `https://xuangu.alixjd.com/api/status` and `https://xuangu.alixjd.com/api/latest-summary` return matching snapshot identities with no-cache headers.
- [ ] Confirm `cloudflare_dispatch_enabled`, scheduler readiness, and the next active refresh values reflect the deployed independent scheduler.
- [ ] Trigger or observe one Cloudflare-originated workflow dispatch and verify it publishes or intentionally deduplicates the expected checkpoint.

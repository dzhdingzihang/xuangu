# Online refresh and opportunity evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. These sub-skills are not installed in this session; use the available collaboration tools, bounded file ownership, test-first implementation and root review instead. The user explicitly requested implementation and publication, so proceed without a separate execution-choice pause.

**Goal:** Improve unattended cloud refresh, verified sector and filing coverage, and independent forward outcome measurement for the opportunity research board.

**Architecture:** Keep GitHub Actions as the compute runner and Cloudflare as the serving/optional independent scheduling layer. Preserve existing rule and model tracks. Add separately sourced metadata and a separately versioned opportunity-outcome ledger; never regenerate historical ranks with present data or promote research scores to calibrated probabilities.

**Tech Stack:** Python 3.12, unittest, exchange_calendars, Requests, GitHub Actions, Cloudflare Workers, vanilla JavaScript, Playwright CLI.

---

## File boundaries and execution

- Root: `server.py`, `src/index.js`, `static/app.js`, `static/styles.css`, `.github/workflows/deploy-worker.yml`, `README.md`, scheduler support tests, deployment and integration.
- Sector subtask: new `sector_metadata.py`, `tests/test_sector_metadata.py`; expose explicit metadata and diagnostics, no server edits.
- Filing subtask: `event_pipeline.py`, `return_opportunity.py`, their tests. Add per-symbol verified scan state and shortlist-first targeting. Coordinate sector provenance shape with root.
- Outcome subtask: new `opportunity_outcome_ledger.py`, `scripts/settle_opportunity_outcomes.py`, their tests, and `scripts/build_worker_assets.py` integration. Root integrates the server and browser. Keep all old ledgers unchanged.

### Task 1: Sector metadata with bounded cloud requests

**Files:** Create `sector_metadata.py`, `tests/test_sector_metadata.py`; integrate at the existing `opportunity_reference_metadata`/generation boundaries in `server.py`.

- [ ] Write pure parsing/cache tests with injected data. Missing fields must remain missing, never infer technology membership from company names. Preserve per-record source and retrieval date. Repeated refreshes must reuse fresh cache entries and failed providers must not overwrite good entries.
- [ ] Implement `enrich_sector_metadata(metadata_by_market, candidates_by_market, *, now, cache_path, fetcher=None)` returning `(metadata_by_market, diagnostics)`; use verified market-data industry fields, bounded concurrency and timeouts, and explicit cache freshness. Retain curated theme evidence as an explicitly labelled fallback.
- [ ] Run `python -m unittest discover -s tests -p 'test_sector_metadata.py' -v`; expect success and no external calls from tests.
- [ ] Integrate only during new snapshot generation, before final opportunity scoring; read frozen metadata during summaries or historical views.

```python
def test_missing_industry_is_not_inferred_from_name(self):
    row = parse_sector_record({"name": "Example AI Technology"}, source="fixture")
    self.assertIsNone(row)
```

### Task 2: Honest, shortlist-prioritized official filing coverage

**Files:** Modify `event_pipeline.py`, `return_opportunity.py`; tests in `tests/test_event_pipeline.py`, `tests/test_return_opportunity.py`.

- [ ] Add failure-first tests for a successful empty scan, an unrequested symbol, a per-symbol provider error, mixed success within one market, and a top opportunity otherwise outside the old legacy shortlist.
- [ ] Publish requested/successful/failed symbols separately; `scanned_symbols` must contain successful scans only. Keep market-wide completeness strict, while retaining independently auditable per-symbol successes.
- [ ] Prefer the preliminary opportunity shortlist plus an overscan buffer; reserve bounded legacy coverage. Do not scan 800 symbols with unbounded official-source requests.
- [ ] Attach `event_coverage` and explicit risk flags to every opportunity. Unscanned/error states must never be described as verified absence of negative events. Preserve material-negative exclusion, event deduplication and zero bonus for routine buybacks.
- [ ] Run `python -m unittest discover -s tests -p 'test_event_pipeline.py' -v` and `python -m unittest discover -s tests -p 'test_return_opportunity.py' -v`; expect all tests to pass.

```python
def test_unrequested_symbol_is_not_verified(self):
    coverage = candidate_scan_coverage({"events": {"pipeline": {}}}, "us", "EXAMPLE")
    self.assertFalse(coverage["verified"])
    self.assertEqual(coverage["status"], "NOT_SCANNED")
```

### Task 3: Independent opportunity forward-outcome ledger

**Files:** Create `opportunity_outcome_ledger.py`, `scripts/settle_opportunity_outcomes.py`, `tests/test_opportunity_outcome_ledger.py`, `tests/test_settle_opportunity_outcomes.py`; modify `scripts/build_worker_assets.py`.

- [ ] Freeze only the published opportunity candidates: source snapshot, score version/weights, rank, code, market, score, decision cutoff and evidence identity. Use a separate directory `data/outcomes/opportunity-settlements`.
- [ ] Derive first exchange open strictly after the information cutoff and tenth session close with the pinned exchange calendar. Never assume fills at prices from before the ranking existed.
- [ ] Settle only after maturity with complete adjusted OHLC for security and benchmark, configured round-trip costs and explicit source. Preserve `PENDING_MATURITY`/`PENDING_DATA`; never fill missing returns with zero.
- [ ] Validate deterministic identities, immutable settled outcomes, identical repeated runs, benchmark joins, holidays and no retroactive ranking. Group reported performance by score version and independent entry sessions; distinguish row count from independent date count.
- [ ] Build a dedicated history manifest summary and recent rows with status, net return, excess return and drawdown. Initial collecting state must not imply validated skill.
- [ ] Run `python -m unittest discover -s tests -p '*opportunity*outcome*.py' -v`; expect success with injected price loaders.

```python
def test_empty_history_is_collecting_not_profitable(self):
    summary = evaluate_opportunity_performance({})
    self.assertEqual(summary["status"], "COLLECTING")
    self.assertEqual(summary["settled_count"], 0)
    self.assertIsNone(summary["mean_net_return"])
    self.assertFalse(summary["authorizes_production"])
```

### Task 4: Refresh reliability, user-visible evidence and deployment

**Files:** Modify `.github/workflows/deploy-worker.yml`, `src/index.js`, `static/app.js`, `static/styles.css`, `README.md`; add scheduler and integration tests under `tests/`.

- [ ] Add optional provisioning from the repository-scoped `XUANGU_WORKFLOW_DISPATCH_TOKEN` secret to the existing Worker dispatch binding, without logging its value or copying local broad-scope credentials. If absent, keep the working GitHub scheduler and expose the missing redundancy honestly.
- [ ] Add bounded timeout/retries for transient dispatch errors; never retry authorization failures or dispatch outside the fixed repository/workflow/cron allowlist. Verify scheduler chronology and retain publication delay measured against the real checkpoint.
- [ ] Cache sector metadata in Actions and run the new outcome CLI before bundling, validating and publishing. Archive the isolated ledger with the existing recovery path; do not merge it into old rule outcomes.
- [ ] Show industry source/coverage, filing scan state, and the independent opportunity history in the existing tabs. Preserve unknown and collecting states, and distinguish fresh catch-up from on-time publication.
- [ ] Run `python -m unittest discover -s tests -v`, `node --check src/index.js`, `node --check static/app.js`, and the asset build; expect all checks to pass.
- [ ] Publish the exact reviewed changed files against the current remote main commit with fast-forward conflict detection. Run the cloud workflow, inspect its steps, and verify live snapshot/API identities and new fields.
- [ ] Use Playwright CLI to inspect homepage, opportunity detail, history and health tabs, including mobile width; capture artifacts under `output/playwright/`. Report actual coverage, pending observations and any remaining authorization or scheduler evidence limitations.

## Acceptance limits

No local computer is required for operation. A successful release is not evidence of a full day of on-time schedules or ten trading days of profitable outcomes. Do not promise either before observations exist. No live stock trades, paid service upgrades, broad token replication, or historical-score rewriting are authorized by this implementation request.

## Implementation and verification status — 2026-09-10 08:56 Asia/Shanghai

Tasks 1–3 and the implementation portion of Task 4 are complete. Final regression: 673 tests passed, both workflow YAML files parsed, JavaScript syntax and diff checks passed, asset build and Worker dry-run passed. The deployment-tool image dependency was patched within the same minor release; `npm audit` reports zero known vulnerabilities.

Playwright checked the historical/collecting state and health tab against a local build of the actual archived snapshot: desktop and 390-pixel mobile screenshots captured; no document overflow and zero browser console errors. This was development verification only, not live deployment or a fresh market scan. Full live opportunity-detail and new-provider coverage acceptance remain pending.

Publication is blocked by GitHub authorization: the current CLI token has `repo`, `read:org`, `gist` but not `workflow`. The requested official device authorization expired without approval. No remote source or workflow was changed in this turn. Cloudflare independent dispatch additionally needs repository-only `Actions: write` fine-grained token stored as `XUANGU_WORKFLOW_DISPATCH_TOKEN`; that optional secret was absent at verification. Do not copy the broad local CLI credential.

Resume by obtaining user-approved `gh auth refresh --hostname github.com --scopes workflow`, verifying scope, reconciling remote main against source `a606615c661e189b255c4e9ef40e1f81d710a727`, and publishing only this reviewed diff. The disposable checkout has an unrelated synthetic root commit and must never be pushed as repository history. Use a proper remote-base commit or Git Data API with a fast-forward guard. Trigger the cloud refresh, verify the deployed snapshot/sector/event/ledger contracts, then publish history after the first verified opportunity receipt is archived. Never register old archived rankings retroactively.

### Authorization resumed — 2026-09-10 21:15 Asia/Shanghai

The user completed official GitHub authorization; `workflow` scope is now verified. Remote main advanced to `91051e66bf4ed0c6cafcd12154981617f07c3c55` through eleven data-only commits; none overlaps this code change. Preserve every newer data file when creating the release commit. The optional repository-scoped dispatch secret is still absent, so keep the independent Cloudflare path explicitly disabled until the user provisions it. Proceed with the existing GitHub scheduler and cloud verification.

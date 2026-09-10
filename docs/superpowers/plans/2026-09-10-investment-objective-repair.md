# Investment Objective and Market Data Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. These sub-skills are unavailable here; use bounded collaboration subtasks with independent tests and root review. The user explicitly requested complete repair, so execute without another execution-choice pause.

**Goal:** Remove non-stock contamination, recover auditable HK/US inputs, improve decision-time opportunity usefulness and forward evaluation, and harden unattended GitHub updates without inventing returns or copying broad credentials.

**Architecture:** Preserve the existing GitHub-compute / Cloudflare-serving design and old scoring tracks. Keep published rankings immutable, introduce versioned research improvements with explicit entry timing, and validate new raw data and visible summaries before deployment. A missing optional dispatch secret and immature performance evidence remain explicit limitations, never false readiness.

**Tech Stack:** Python 3.12 unittest, vanilla JavaScript, GitHub Actions, Cloudflare Workers, exchange_calendars.

---

## Scope, source and file ownership

Use `/tmp/xuangu-online-hardening.HIU4kI/repo`. Remote baseline is `d4ce431aaa90ae27489b145f4db7b50de276014d`. Its local Git history is synthetic; never push it. Publish reviewed paths on the current remote parent through the existing Git Data helper with fast-forward protection, preserving concurrent data archives.

- Market-data subproject: `server.py`, new focused security-type module if needed, HK/US provider tests. Own security identification, discovery source chronology/completeness, HK daily bars and diagnostics. Do not edit frontend/workflows/opportunity ranking.
- Opportunity subproject: `return_opportunity.py`, `opportunity_outcome_ledger.py`, related tests. Own anti-chase entry assessment, version compatibility, and Top1/Top3/net-return evaluation. Do not alter old published ranks or production authorization.
- Cloud subproject: `.github/workflows/deploy-worker.yml`, `.github/workflows/settle-observations.yml`, `scripts/schedule_gate.py`, `scripts/configure_scheduler.py`, `src/index.js`, related tests. Own bounded source recovery, truthful scheduled evidence and safe optional credential provisioning.
- Root integration: `static/app.js`, `static/styles.css`, `scripts/build_worker_assets.py`, `scripts/verify_deployment.py`, `event_pipeline.py` only if needed, `README.md`, cross-module tests, review, publication and acceptance.

## Subproject 1 — Clean stock universe and complete source evidence

- [ ] Add failing regression fixtures for the observed `SKUU / GRANITESHARES 2X LONG SK HYNIX` name, ETF/ETN/inverse/unit/warrant variants, ordinary stocks whose names contain generic fund-like substrings, missing type evidence, and security identity collisions. At minimum, the actual regression is:

```python
def test_observed_leveraged_product_is_not_an_ordinary_stock(self):
    self.assertTrue(server._blocked_dynamic_security_name(
        "GRANITESHARES 2X LONG SK HYNIX", "us"))
```

- [ ] Fix the existing `_blocked_dynamic_security_name` boundary and provider-specific type validation; attach auditable classification to newly admitted records and exclude positively identified products again before ranking. Never silently interpret an absent structured type as provider-verified common stock. Legacy compatibility must not re-admit a known ETF into current research.
- [ ] Reproduce the US discovery failures using current saved raw evidence: incomplete pagination and 48 selected rows without acceptable source timestamps. Bound and retry independent route pages, use validated fresh replacements, and distinguish an intentionally bounded scan from truncated provider pagination. Do not set `discovery_pagination_complete=true` merely because 300 selections exist.
- [ ] Reproduce HK final quote/score loss from 200 to 195. Retain the original source quote when daily-bar retrieval fails; use a bounded independent daily-bar fallback with source/date/OHLC validation, and publish exact per-symbol missing-input reasons. Stale bars must not count as complete.
- [ ] Run targeted provider and universe tests, then assert genuine output contracts with the full independent verifier. If a provider remains unavailable, retain the degraded state and record which recovery sources were exhausted.

Run: `/tmp/xuangu-profit-fix.CfP5rc/venv/bin/python -m unittest discover -s tests -p '*dynamic*' -v` plus every new focused test file. Expected: failures first on the new regressions, then all pass without live network in tests.

## Subproject 2 — Decision-time usefulness and measurable return objective

- [ ] Add regression tests based on the audited first-place row (10-day return 41.235%, MA20 deviation 32.998%, no material catalyst). Require explicit chase-risk/entry assessment, not an implied forward 41% return, and verify moderate earlier-stage continuation is not automatically ranked below an exhausted spike.
- [ ] Version the changed research scoring/entry contract while retaining support for already published v1/v2. Preserve independent original factor contributions; expected return/probability remain null until actual validated estimates exist. Explicitly state next-session open reference, delayed-snapshot limits, and conditional review rather than pretending the site can execute now.
- [ ] Add versioned forward comparison for Top1, Top3 and the displayed board using original ranks, costs and complete entry cohorts. Include net absolute return as the primary user-facing measurement and excess return as a secondary measurement. Do not pool partial cohorts or versions, and do not reinterpret historic scores with today's weights.
- [ ] Use a concrete collecting-state regression:

```python
def test_unmatured_board_does_not_claim_return_skill(self):
    summary = opportunity_outcome_ledger.evaluate_opportunity_performance({})
    self.assertEqual(summary["settled_count"], 0)
    self.assertIsNone(summary["mean_net_return"])
    self.assertFalse(summary["authorizes_production"])
```

- [ ] Run current opportunity tests and new objective/entry tests. Confirm the source snapshot identity and independent registration evidence still protect frozen rankings. No future-date simulation may appear as a production outcome.

Run: `/tmp/xuangu-profit-fix.CfP5rc/venv/bin/python -m unittest discover -s tests -p '*opportunity*' -v`. Expected: all tests pass with null immature returns and preserved old batches.

## Subproject 3 — Unattended cloud recovery

- [ ] Inspect real failed/late Actions runs and distinguish scheduler delivery delays, execution failures and unavailable source evidence. Add focused failing tests for the observed recoverable failure classes; never substitute green CI for a published snapshot receipt.
- [ ] Improve bounded recovery and deployment sequencing within the existing 40-minute job budget. Keep generation on GitHub, preserve monotonic snapshot publication and exact-version rollback, and avoid expensive repeated whole-market work after the same source failure.
- [ ] Confirm optional dedicated GitHub Actions-write credential provisioning uses stdin, refuses broad OAuth/classic PAT copying, and preserves the GitHub primary schedule if absent. Check actual repository secret names without reading secret values. Missing independent credentials are a user-configuration boundary, not a reason to claim independent scheduling enabled.
- [ ] Keep the published schedule, `next_refresh`, watchdog chronology and live readiness aligned; keep past missed/late records honest. Add tests for any changed schedule or filtering behavior.

Run: `/tmp/xuangu-profit-fix.CfP5rc/venv/bin/python -m unittest discover -s tests -p '*schedul*' -v` and `-p '*workflow*' -v`. Expected: known failures covered, bounded retry behavior, unchanged security boundaries.

## Root integration and release

- [ ] Review all three diffs and extend raw-snapshot/compact-UI projection validators for the new fields. Keep bootstrap below the existing 102,400-byte budget. Verify no known ETF can become a current market opportunity even via a legacy metadata fallback.
- [ ] Present chase risk, reference entry timing, data gaps and Top1/Top3 outcome status plainly on existing tabs. Reconcile market-wide event completeness with independently successful per-symbol scans, without converting a partial market scan into full negative-risk clearance.
- [ ] Update README with the exact scoring target, research-versus-buying boundary, all original factors retained, source recovery, clocks and remaining evidence limitations.
- [ ] Execute `/tmp/xuangu-profit-fix.CfP5rc/venv/bin/python -m unittest discover -s tests -q`, `node --check src/index.js`, `node --check static/app.js`, `git diff --check`, asset build and deployment dry-run. Preserve unrelated and generated files.
- [ ] Stage only reviewed source/tests/docs. Publish using `/tmp/xuangu-online-hardening.HIU4kI/publish_staged.py --publish --base-remote d4ce431aaa90ae27489b145f4db7b50de276014d`; if remote code overlaps, reconcile before publishing. Never force-update main.
- [ ] Trigger a GitHub cloud refresh, inspect the run, and verify the actual live instrument filtering, source timestamps, market counts, entry assessment, frozen ranking, and independent history. Publishing a compatible old snapshot is not acceptance of new data fixes.
- [ ] After registration, publish history without regenerating historical ranks; verify fresh API/visible contracts. Use a working browser to check the updated existing tabs. Report actual data gaps, missing credential and immature performance separately from implementation completion.

## Acceptance limits

The goal is a better, auditable ten-session choice, not guaranteed profit. No local OpenD, local scheduled production jobs, broad credential replication, paid data subscriptions, live trades, or retroactive synthetic winners are authorized. Require evidence for recovered markets; do not lower the 98% gates to create candidates. If full external source recovery or independent dispatch requires new access, exhaust safe alternatives and report the exact remaining requirement.

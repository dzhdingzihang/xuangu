# Production Realtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current Cloudflare research console into a truthful, production-usable A/HK/US ten-session decision service with source-timestamped intraday quotes, one global action contract, exchange calendars, a reproducible empirical baseline model, and automatic outcome settlement.

**Architecture:** Python in GitHub Actions remains the immutable decision engine. It builds a dynamic validated candidate universe, exchange-specific dates, external evidence, an empirical walk-forward ten-session distribution, and append-only outcomes. Cloudflare Worker serves immutable decision data and a bounded, cached intraday quote overlay; the browser only merges a quote when `source_as_of` is newer than the snapshot price. No score or probability is recomputed in the browser.

**Tech Stack:** Python 3.12, `requests`, `exchange-calendars==4.13.2`, Cloudflare Workers/Assets, vanilla JavaScript, GitHub Actions, `unittest`.

---

## File map

- Create `market_calendar.py`: exchange-specific session calculations for XSHG, XHKG and XNYS.
- Create `ten_day_model.py`: deterministic walk-forward empirical probability, expected return, costs and tail-risk estimates.
- Create `event_evidence.py`: normalized externally sourced evidence contract and injected-source aggregation.
- Create `scripts/settle_outcomes.py`: append-only settlement ledger writer.
- Create `data/outcomes/ledger.jsonl`: published append-only prediction outcomes.
- Modify `server.py`: dynamic pool health, model/evidence integration, one global action, correct dates and no fake 2-day range.
- Modify `scripts/validate_snapshot.py`: date, calendar, action, quote and prediction invariants.
- Modify `scripts/build_worker_assets.py`: bounded history assets and ledger-backed outcome summaries.
- Modify `src/index.js`: bounded intraday data, timestamp semantics, caching, allow-list validation, security headers and strict date behavior.
- Modify `static/app.js`: global-action wording, safe live merging, timed quote refresh, accessible chart tables and consistent health labels.
- Modify `static/index.html` and `static/styles.css`: self-contained assets, mobile legibility and accessibility refinements.
- Modify `.github/workflows/deploy-worker.yml`: settle -> generate -> validate -> deploy -> verify -> reliable archive.
- Modify `scripts/schedule_gate.py` and `scripts/verify_deployment.py`: data-health-aware fallback and content-hash verification.
- Modify `wrangler.jsonc`: route all requests through the Worker so HTTPS and security headers cover static assets.
- Modify `README.md`: production truth, sources, latency and update guarantees.

### Task 1: Exchange-specific dates and schema invariants

**Files:**
- Create: `market_calendar.py`
- Modify: `requirements.txt`
- Modify: `server.py`
- Modify: `scripts/validate_snapshot.py`
- Test: `tests/test_market_calendar.py`
- Test: `tests/test_snapshot_contract.py`

- [ ] **Step 1: Write failing exchange-calendar tests**

```python
def test_us_labor_day_is_not_a_session(self):
    self.assertFalse(is_session("us", dt.date(2026, 9, 7)))

def test_ten_sessions_are_market_specific(self):
    start = dt.date(2026, 8, 24)
    self.assertNotEqual(add_sessions("a_share", start, 10), add_sessions("us", start, 10))

def test_next_trade_date_is_target_not_forecast_end(self):
    snapshot = make_snapshot(signal_day=dt.date(2026, 8, 21))
    self.assertEqual(snapshot["next_trade_dates"]["us"], "2026-08-24")
    self.assertNotEqual(snapshot["next_trade_dates"]["us"], snapshot["forecast_end_dates"]["us"])
```

- [ ] **Step 2: Run tests and confirm the current weekday-only code fails**

Run: `python -m unittest tests.test_market_calendar tests.test_snapshot_contract -v`
Expected: failures for missing exchange-specific calendar functions and invalid `next_trade_date` semantics.

- [ ] **Step 3: Implement the calendar adapter**

```python
CALENDAR_BY_MARKET = {"a_share": "XSHG", "hk": "XHKG", "us": "XNYS"}

def sessions(market: str, start: dt.date, end: dt.date) -> list[dt.date]:
    calendar = exchange_calendars.get_calendar(CALENDAR_BY_MARKET[market])
    return [stamp.date() for stamp in calendar.sessions_in_range(start.isoformat(), end.isoformat())]

def next_session(market: str, day: dt.date) -> dt.date:
    return sessions(market, day, day + dt.timedelta(days=14))[0]

def add_sessions(market: str, day: dt.date, count: int) -> dt.date:
    rows = sessions(market, day, day + dt.timedelta(days=max(45, count * 4)))
    return rows[count]
```

Pin `exchange-calendars==4.13.2` in `requirements.txt`. Store `calendar_id`, `next_trade_dates` and `forecast_end_dates` per market; keep top-level `next_trade_date`/`forecast_end_date` only as the selected global candidate's dates or `null` when there is no executable selection.

- [ ] **Step 4: Add validator invariants**

```python
if snapshot.get("next_trade_date") == snapshot.get("forecast_end_date"):
    errors.append("next_trade_date must differ from forecast_end_date")
for market in ("a_share", "hk", "us"):
    if not is_session(market, dt.date.fromisoformat(snapshot["next_trade_dates"][market])):
        errors.append(f"next_trade_dates.{market} must be an exchange session")
```

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m unittest tests.test_market_calendar tests.test_snapshot_contract -v`
Expected: all focused tests pass.
Commit: `fix: use exchange calendars for ten-session decisions`

### Task 2: Reproducible ten-session baseline model

**Files:**
- Create: `ten_day_model.py`
- Modify: `server.py`
- Modify: `scripts/validate_snapshot.py`
- Test: `tests/test_ten_day_model.py`
- Test: `tests/test_global_decision_contract.py`

- [ ] **Step 1: Write failing walk-forward model tests**

```python
def test_prediction_is_reproducible_and_bounded(self):
    result = fit_candidate_distribution("us", deterministic_closes(140))
    self.assertEqual(result, fit_candidate_distribution("us", deterministic_closes(140)))
    self.assertGreaterEqual(result["probability"], 0)
    self.assertLessEqual(result["probability"], 1)
    self.assertGreater(result["sample_count"], 40)

def test_model_refuses_short_history(self):
    self.assertEqual(fit_candidate_distribution("hk", [10.0] * 20)["status"], "INSUFFICIENT_HISTORY")

def test_utility_includes_cost_and_tail_risk(self):
    result = fit_candidate_distribution("a_share", deterministic_closes(140))
    expected = result["expected_return"] - result["transaction_cost"] - result["tail_risk_penalty"]
    self.assertAlmostEqual(result["expected_net_utility"], expected, places=8)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.test_ten_day_model tests.test_global_decision_contract -v`
Expected: missing model module and current `planned` contract failures.

- [ ] **Step 3: Implement the empirical model**

```python
MARKET_COST = {"a_share": 0.0018, "hk": 0.0028, "us": 0.0012}

def fit_candidate_distribution(market: str, closes: list[float], horizon: int = 10) -> dict:
    returns = [(closes[index + horizon] / closes[index]) - 1 for index in range(len(closes) - horizon)]
    if len(returns) < 40:
        return {"status": "INSUFFICIENT_HISTORY", "sample_count": len(returns)}
    wins = sum(value > 0 for value in returns)
    probability = (wins + 2) / (len(returns) + 4)
    ordered = sorted(returns)
    expected_return = statistics.median(returns)
    tail_loss = max(0.0, -ordered[max(0, int(len(ordered) * 0.10) - 1)])
    transaction_cost = MARKET_COST[market]
    tail_risk_penalty = 0.35 * tail_loss
    return {
        "status": "READY",
        "model_id": "empirical-10d-walk-forward-v1",
        "label_version": "net-return-10-session-v1",
        "sample_count": len(returns),
        "probability": probability,
        "expected_return": expected_return,
        "transaction_cost": transaction_cost,
        "tail_risk": tail_loss,
        "tail_risk_penalty": tail_risk_penalty,
        "expected_net_utility": expected_return - transaction_cost - tail_risk_penalty,
        "calibrated": True,
    }
```

Use only K-lines whose date is not later than the signal date. Require at least 40 observations, positive net utility, complete data gates and sufficient external evidence. Select exactly one global candidate by highest expected net utility; all market-level Legacy actions become `RESEARCH_ONLY` display records.

- [ ] **Step 4: Validate executable predictions strictly**

Require finite probability, return, cost, tail risk, utility, `prediction_id`, `model_id`, `label_version`, exchange-specific entry/exit dates and `score_kind=TEN_DAY_EXPECTED_NET_UTILITY` before `REVIEW_EXECUTABLE_PICK` is legal.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_ten_day_model tests.test_global_decision_contract tests.test_snapshot_contract -v`
Expected: all focused tests pass.
Commit: `feat: add empirical ten-session decision baseline`

### Task 3: Automatic external evidence and dynamic validated pools

**Files:**
- Create: `event_evidence.py`
- Modify: `server.py`
- Test: `tests/test_event_evidence.py`
- Test: `tests/test_selector_v2.py`

- [ ] **Step 1: Write failing evidence and coverage tests**

```python
def test_model_signal_never_counts_as_external(self):
    self.assertFalse(decision_eligible({"event_type": "model_signal", "url": "https://example.com"}))

def test_verified_official_event_counts(self):
    event = {"event_type": "external", "source_tier": "official", "url": "https://www.sec.gov/Archives/x", "published_at": "2026-08-21T12:00:00Z", "symbol": "NTNX"}
    self.assertTrue(decision_eligible(event))

def test_two_independent_media_sources_count(self):
    self.assertTrue(evidence_sufficient([reuters_event(), cnbc_event()], "NTNX"))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.test_event_evidence tests.test_selector_v2 -v`
Expected: missing source aggregator and static-universe coverage failures.

- [ ] **Step 3: Implement normalized evidence**

```python
def evidence_sufficient(events: list[dict], symbol: str) -> bool:
    matched = [row for row in events if row.get("symbol") == symbol and row.get("url") and row.get("published_at")]
    if any(row.get("source_tier") in {"official", "regulatory", "exchange"} for row in matched):
        return True
    media_domains = {urllib.parse.urlparse(row["url"]).netloc.lower() for row in matched if row.get("source_tier") == "authoritative_media"}
    return len(media_domains) >= 2
```

Normalize existing exchange/company-IR/SEC events and retain model signals separately. Query functions accept injected HTTP fetchers so tests use fixtures. Never promote an event without a source URL, publish time, symbol and source tier.

For pools, define `seed_count`, `quote_validated_count`, `excluded_count`, `minimum_required`, `universe_origin=dynamic_quote_validated`, and quote health over the validated execution universe. A Share broad recall falls back to the successfully quoted dynamic rows rather than publishing broad pool 0 after one route fails. HK/US rerank all quote-valid seeds on every snapshot and no longer label them `curated_static`.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_event_evidence tests.test_selector_v2 tests.test_global_decision_contract -v`
Expected: all focused tests pass.
Commit: `feat: add traceable evidence and validated dynamic pools`

### Task 4: Source-timestamped intraday quote overlay

**Files:**
- Modify: `src/index.js`
- Modify: `static/app.js`
- Test: `tests/test_worker_contract.py`
- Test: `tests/test_frontend_contract.py`

- [ ] **Step 1: Write failing Worker tests**

```javascript
assert.equal(payload.granularity, "1m");
assert.equal(payload.freshness_state, "fresh");
assert.ok(Date.parse(payload.source_as_of) <= Date.parse(payload.fetched_at));
assert.equal((await worker.fetch(new Request("https://x/api/live?market=us&code=NOT_IN_POOL"), env)).status, 404);
```

Add a frontend contract assertion that live data is merged only when `Date.parse(live.source_as_of) >= Date.parse(snapshot.realtime.source_as_of)`.

- [ ] **Step 2: Run tests and verify current daily Yahoo implementation fails**

Run: `python -m unittest tests.test_worker_contract tests.test_frontend_contract -v`
Expected: failures for `range=3mo&interval=1d`, arbitrary symbols and unconditional merging.

- [ ] **Step 3: Implement bounded quote fetches**

```javascript
async function fetchWithTimeout(url, init = {}, timeoutMs = 4500) {
  return fetch(url, { ...init, signal: AbortSignal.timeout(timeoutMs) });
}

function quoteFreshness(sourceAsOf, marketState, now = Date.now()) {
  const ageSeconds = Math.max(0, Math.floor((now - Date.parse(sourceAsOf)) / 1000));
  const active = ["REGULAR", "PRE", "POST", "MORNING", "AFTERNOON"].includes(String(marketState).toUpperCase());
  return { age_seconds: ageSeconds, freshness_state: active && ageSeconds <= 180 ? "fresh" : active ? "stale" : "closed" };
}
```

Use Eastmoney/Tencent timestamps for A shares and Yahoo `range=1d&interval=1m&includePrePost=true` for HK/US. Price selection uses the latest timestamped minute bar across regular/pre/post data; `updated_at` equals `source_as_of`, while `fetched_at` records retrieval time. Cache successful live responses for 10 seconds and restrict symbols to candidates in the current immutable snapshot.

- [ ] **Step 4: Implement safe browser merging and refresh cadence**

```javascript
function shouldMergeLive(candidate, live) {
  const liveAt = Date.parse(live?.source_as_of || "");
  const snapshotAt = Date.parse(candidate?.realtime?.source_as_of || candidate?.quote_as_of || "");
  return Number.isFinite(liveAt) && (!Number.isFinite(snapshotAt) || liveAt >= snapshotAt);
}
```

Refresh the visible/selected candidates every 15 seconds only while `document.visibilityState === "visible"`. Preserve model scores, show exact source, granularity, source time, age and `fresh/delayed/closed/stale` status.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_worker_contract tests.test_frontend_contract -v`
Expected: all focused tests pass.
Commit: `fix: serve timestamped minute quotes without price rollback`

### Task 5: Global action UX, health truth and accessibility

**Files:**
- Modify: `static/app.js`
- Modify: `static/index.html`
- Modify: `static/styles.css`
- Test: `tests/test_frontend_contract.py`

- [ ] **Step 1: Write failing wording/accessibility tests**

Assert the frontend contains `RESEARCH_ONLY`, does not render market-level `BUY_CANDIDATE` as “推荐买入”, implements ArrowLeft/ArrowRight tab navigation, renders a data table adjacent to each canvas and uses mobile navigation text of at least 11px.

- [ ] **Step 2: Implement one action vocabulary**

```javascript
function actionLabel(snapshot) {
  if (snapshot.global_decision?.action === "REVIEW_EXECUTABLE_PICK") return "可执行候选，等待人工复核";
  return "当前无可执行股票";
}

function legacyLabel() {
  return "研究排序 · 不构成当前买入动作";
}
```

The top bar shows `发布正常` separately from `决策可用/决策阻断`. Candidate cards never say “推荐买入” unless they are the exact global executable primary.

- [ ] **Step 3: Add keyboard and chart alternatives**

Implement Home/End/ArrowLeft/ArrowRight on the tablist, roving `tabindex`, and visually hidden tables containing chart dates/OHLC/score values. Increase mobile nav text to 11px and keep the 44px touch target.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_frontend_contract -v`
Expected: frontend contract passes.
Commit: `fix: align the UI with the global decision contract`

### Task 6: Append-only outcome settlement

**Files:**
- Create: `scripts/settle_outcomes.py`
- Create: `data/outcomes/ledger.jsonl`
- Modify: `scripts/build_worker_assets.py`
- Modify: `src/index.js`
- Test: `tests/test_outcome_settlement.py`
- Test: `tests/test_history_evaluation_contract.py`

- [ ] **Step 1: Write failing settlement tests**

```python
def test_settlement_uses_market_calendar_and_costs(self):
    outcome = settle_prediction(prediction_fixture(), price_fixture())
    self.assertEqual(outcome["status"], "SETTLED")
    self.assertEqual(outcome["entry_source"], "daily_open")
    self.assertLess(outcome["net_total_return"], outcome["gross_total_return"])

def test_ledger_is_idempotent(self):
    self.assertEqual(append_once(ledger, outcome), True)
    self.assertEqual(append_once(ledger, outcome), False)
```

- [ ] **Step 2: Implement settlement**

Settle only `REVIEW_EXECUTABLE_PICK` predictions whose market-specific forecast end has completed. Use the next session open for entry, tenth session close for exit, adjusted daily prices, stored transaction cost, currency and calendar ID. Write one JSON line keyed by `prediction_id`; never mutate the original decision snapshot.

- [ ] **Step 3: Join ledger data during asset build**

Build history summaries with outcomes from `ledger.jsonl`. Publish only the compact manifest plus the most recent 120 full snapshots; keep older decision summaries in the manifest so storage does not grow without bound.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_outcome_settlement tests.test_history_evaluation_contract tests.test_worker_contract -v`
Expected: settlement and history metrics pass.
Commit: `feat: add append-only ten-session outcome settlement`

### Task 7: Deployment, security and rollback hardening

**Files:**
- Modify: `.github/workflows/deploy-worker.yml`
- Modify: `scripts/schedule_gate.py`
- Modify: `scripts/verify_deployment.py`
- Modify: `wrangler.jsonc`
- Modify: `src/index.js`
- Test: `tests/test_workflow_reliability.py`
- Test: `tests/test_worker_contract.py`

- [ ] **Step 1: Write failing operations tests**

Require `run_worker_first` for all routes, static security headers, HTTP 308, snapshot SHA-256 verification, no `continue-on-error`, bounded archive rebase/retry, settlement before generation and health-aware schedule fallback.

- [ ] **Step 2: Harden the workflow**

Run settlement before generation. Upload the timestamp snapshot plus ledger. Replace auto-commit with a shell loop that fetches main, rebases, commits only generated files and pushes up to three times; failure must fail the workflow. Give `contents: write` only to the archive step/job and pin third-party actions by immutable commit SHA.

- [ ] **Step 3: Protect deployment monotonicity**

`verify_deployment.py` compares `snapshot_sha256`, generated time, dates, global action, history manifest identity and static page health. Push-triggered deployment refuses to publish a snapshot older than production.

- [ ] **Step 4: Route static assets through Worker**

Set `run_worker_first` to `true` (or the Wrangler-supported all-route equivalent), add CSP and cross-origin headers, preserve local-dev behavior, and ensure HTTP requests return 308 HTTPS redirects.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_workflow_reliability tests.test_worker_contract tests.test_schedule_gate -v`
Expected: all focused tests pass.
Commit: `fix: harden Cloudflare deployment and snapshot archival`

### Task 8: Full release, production verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `design-qa.md`
- Modify: all affected tests and generated `public/` assets

- [ ] **Step 1: Reconcile the remote branch safely**

Confirm `origin/main` is an ancestor of the release branch and that the release tree contains the latest generated snapshot. Use a normal fast-forward push; do not force-push.

- [ ] **Step 2: Run the full local gate**

Run:

```bash
python -m unittest discover -s tests -v
python scripts/validate_snapshot.py data/picks/latest.json
node --check src/index.js
node --check static/app.js
npm audit --omit=dev
npm run check
```

Expected: all tests pass, validator reports valid, syntax checks pass, audit reports zero known vulnerabilities, Wrangler dry-run succeeds.

- [ ] **Step 3: Generate a fresh snapshot and ledger**

Run `python scripts/settle_outcomes.py` followed by `AUTOMATION_TRIGGER=workflow_dispatch python server.py --once --force`. Validate the new snapshot. If no candidate satisfies all model/evidence/data gates, publish `NO_VALID_PICK` plus an explicit research priority; do not fabricate an executable pick.

- [ ] **Step 4: Update documentation**

Document exact source names, quote granularity, latency states, market calendars, model formula, action semantics, settlement contract, schedule checkpoints, fallback behavior and limitations. Remove claims that Render is part of production.

- [ ] **Step 5: Commit, push and deploy**

Commit all source, tests, docs and generated current snapshot. Push to `origin/main`, monitor the Cloudflare workflow to success and record the deployed Worker version ID.

- [ ] **Step 6: Verify production**

Check `/`, all six tabs, `/api/status`, `/api/latest-summary`, daily/raw history, one live symbol per market, HTTPS redirect, security headers, quote timestamps and that repository `main` matches the production content hash. Confirm the Render service is suspended or report the exact external permission blocker.

- [ ] **Step 7: Save evidence**

Capture fresh desktop screenshots for all six tabs and a compact production verification report under `docs/release-qa/2026-08-22/`.

## Self-review

- Spec coverage: realtime quotes, candidate pools, model, dates, evidence, settlement, UI semantics, automation, security, Render and deployment are mapped to tasks.
- Placeholder scan: no implementation step relies on `TBD`, `TODO`, “similar to”, or an undefined follow-up.
- Type consistency: market keys are `a_share/hk/us`; actions are `NO_VALID_PICK/REVIEW_EXECUTABLE_PICK`; predictions use `TEN_DAY_EXPECTED_NET_UTILITY`; all date maps use ISO dates.

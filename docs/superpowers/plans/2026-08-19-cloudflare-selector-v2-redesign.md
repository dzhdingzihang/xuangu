# Cloudflare Selector V2 Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a five-tab, evidence-first A-share/HK/US stock-selection dashboard on `xuangu.alixjd.com`, preserve the current production decisions, add a truthful V2 shadow score and candidate-lineage contract, and make Cloudflare Workers the only public runtime.

**Architecture:** `server.py` remains the deterministic snapshot generator executed by scheduled GitHub Actions; it writes immutable JSON snapshots that `scripts/build_worker_assets.py` bakes into Cloudflare Worker assets. The legacy score and BUY/NO_TRADE gate stay active while a new pure-function V2 layer adds deduplicated factor groups, market regime, data quality, decision gates, source lineage, event evidence, and within-market rank. The browser is a dependency-free five-tab SPA that renders real snapshot fields, refreshes only live prices, and never pretends that a Worker request recomputes the model.

**Tech Stack:** Python 3.12 standard-library `unittest`, deterministic selector rules, vanilla HTML/CSS/JavaScript, Phosphor Icons webfont, Cloudflare Workers static assets, Wrangler 4, GitHub Actions.

---

## File map

- `server.py`: existing data acquisition and legacy scoring plus the V2 shadow-contract builder.
- `tests/test_selector_v2.py`: pure unit tests for lineage, score invariants, regimes, quality, gates, and event evidence.
- `tests/test_snapshot_contract.py`: fixture-based compatibility checks for all three markets.
- `scripts/backtest_may.py`: repair the four-value Serenity return signature and label the limitations of this research script.
- `static/index.html`: accessible five-tab application shell.
- `static/styles.css`: responsive implementation of the selected blue/white evidence-console design.
- `static/app.js`: state management, API loading, derived fallback contract, tab rendering, filters, live-quote merge, charts, and history loading.
- `src/index.js`: Cloudflare-only API behavior, honest recompute response, source timestamps, volume units, HTTPS redirect, and response security headers.
- `scripts/build_worker_assets.py`: preserve V2 fields in summaries and validate required assets.
- `.github/workflows/deploy-worker.yml`: test, generate snapshots on schedule/manual dispatch, build, and deploy only to Cloudflare.
- `README.md`: actual strategy, factor preservation, universe scope, data-source caveats, V2 rollout, API, and Cloudflare deployment.
- `render.yaml`, `runtime.txt`, `DEPLOY_RENDER.md`: remove obsolete Render deployment files.
- `design-qa.md`: visual and interaction QA evidence for all five tabs.

### Task 1: Lock the legacy/V2 contract with failing tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_selector_v2.py`
- Create: `tests/test_snapshot_contract.py`
- Modify: `server.py`

- [ ] **Step 1: Write lineage and factor invariants**

```python
def test_merge_candidate_pools_preserves_all_recall_routes():
    rows = server.merge_candidate_pools(
        [{"code": "603228", "reason": "订单", "source": "ths"}],
        [{"code": "603228", "reason": "高流动性", "source": "eastmoney_broad", "recall_route": "liquidity"}],
    )
    routes = rows[0]["candidate_lineage"]["recall_routes"]
    assert {item["route"] for item in routes} == {"event", "liquidity"}

def test_v2_factor_contributions_sum_to_rule_score():
    candidate = fixture_candidate()
    result = server.build_v2_shadow(candidate, "a_share", {"risk": "normal"})
    assert abs(sum(item["contribution"] for item in result["factor_groups"].values()) - result["rule_score"]) < 0.02
    used = [feature["feature_id"] for group in result["factor_groups"].values() for feature in group["features"] if feature["used_in_score"]]
    assert len(used) == len(set(used))
```

- [ ] **Step 2: Write regime, quality, gate, and compatibility tests**

```python
def test_unknown_market_is_not_treated_as_normal():
    regime = server.classify_market_regime("hk", {}, [])
    assert regime["state"] == "unknown"
    assert regime["warnings"]

def test_invalid_quote_blocks_execution_but_keeps_legacy_fields():
    candidate = fixture_candidate(price=0)
    enriched = server.attach_candidate_v2(candidate, "a_share", {"risk": "normal"})
    assert enriched["decision_gates"][0]["status"] == "BLOCK"
    assert enriched["legacy"]["active"] is True
    assert enriched["score"] == candidate["score"]

def test_three_markets_keep_old_fields_and_add_v2_contract():
    snapshot = load_fixture_snapshot()
    enriched = server.enrich_snapshot_v2(snapshot)
    for key in ("a_share", "hk", "us"):
        row = best_candidate(enriched["markets"][key]["decision"])
        assert {"score", "recommendation_degree", "chan_score", "uzi_panel_score", "legacy", "v2", "data_quality"} <= row.keys()
```

- [ ] **Step 3: Run the focused tests and verify the new symbols fail**

Run: `python3 -m unittest tests.test_selector_v2 tests.test_snapshot_contract -v`

Expected: failures naming the not-yet-created V2 helper functions.

- [ ] **Step 4: Add stable constants and pure helper signatures**

```python
SCHEMA_VERSION = "selector-snapshot-v2"
SELECTOR_MODE = "legacy_active_v2_shadow"
V2_WEIGHTS_VERSION = "v2-rule-prior-1"

def classify_market_regime(market_key: str, market: dict, candidates: list[dict]) -> dict:
    state = "risk_off" if market.get("risk") == "high" else "range" if market_key == "a_share" else "unknown"
    return {"state": state, "effective_weights": V2_REGIME_WEIGHTS[state], "warnings": [] if state != "unknown" else ["市场基准数据不足"]}

def build_v2_shadow(candidate: dict, market_key: str, market: dict) -> dict:
    regime = classify_market_regime(market_key, market, [candidate])
    groups = build_factor_groups(candidate, regime["effective_weights"])
    score = round(sum(group["contribution"] for group in groups.values()), 2)
    return {"mode": "shadow", "rule_score": score, "factor_groups": groups, "market_regime": regime["state"]}

def assess_data_quality(candidate: dict, market_key: str, market: dict) -> dict:
    kline_count = len(candidate.get("kline") or [])
    price_ok = safe_float(candidate.get("entry_price") or candidate.get("price")) > 0
    complete_ratio = (int(price_ok) + int(kline_count >= 32) + int(bool(market))) / 3
    return {"score": round(complete_ratio * 100), "status": "complete" if complete_ratio == 1 else "partial", "complete_ratio": round(complete_ratio, 2)}

def evaluate_decision_gates(candidate: dict, quality: dict) -> list[dict]:
    return [
        {"id": "quote_valid", "status": "PASS" if safe_float(candidate.get("entry_price") or candidate.get("price")) > 0 else "BLOCK"},
        {"id": "kline_complete", "status": "PASS" if len(candidate.get("kline") or []) >= 32 else "BLOCK"},
        {"id": "data_coverage", "status": "PASS" if quality["complete_ratio"] == 1 else "WARN"},
    ]

def attach_candidate_v2(candidate: dict, market_key: str, market: dict) -> dict:
    quality = assess_data_quality(candidate, market_key, market)
    candidate["legacy"] = legacy_score_contract(candidate)
    candidate["v2"] = build_v2_shadow(candidate, market_key, market)
    candidate["data_quality"] = quality
    candidate["decision_gates"] = evaluate_decision_gates(candidate, quality)
    return candidate

def enrich_snapshot_v2(snapshot: dict) -> dict:
    snapshot["schema_version"] = SCHEMA_VERSION
    snapshot["selector_mode"] = SELECTOR_MODE
    for market_key, section in (snapshot.get("markets") or {}).items():
        enrich_market_decision(section.get("decision") or {}, market_key, snapshot.get("market") or {})
    return snapshot
```

- [ ] **Step 5: Run the focused tests until they pass**

Run: `python3 -m unittest tests.test_selector_v2 tests.test_snapshot_contract -v`

Expected: all V2 contract tests pass without network access.

### Task 2: Upgrade A-share recall while preserving source lineage

**Files:**
- Modify: `server.py`
- Modify: `tests/test_selector_v2.py`

- [ ] **Step 1: Add tests for multi-route recall and five-session cache expiry**

```python
def test_broad_pool_rows_do_not_require_positive_return_or_pb18():
    row = normalize_broad_fixture(change_pct=-1.2, pb=35)
    assert server.broad_recall_routes(row) == ["liquidity", "pullback"]

def test_cached_pool_expires_after_five_trade_weekdays():
    assert server.is_history_candidate_fresh("2026-08-12", date(2026, 8, 19), 5) is False
    assert server.is_history_candidate_fresh("2026-08-14", date(2026, 8, 19), 5) is True
```

- [ ] **Step 2: Implement route classification and lineage merging**

```python
def broad_recall_routes(row: dict) -> list[str]:
    routes = ["liquidity"]
    change = safe_float(row.get("broad_change_pct"))
    routes.append("momentum" if change >= 0.8 else "pullback")
    return routes
```

Each merged candidate must expose `candidate_lineage.candidate_id`, `universe_origin`, `recall_routes`, `route_count`, `primary_route`, `first_seen_at`, and `last_seen_at`. Missing publication timestamps and URLs remain `None` and `evidence_status` remains `partial`.

- [ ] **Step 3: Replace PB and positive-return hard filters with execution filters**

Keep price, ST/delisting, liquidity, turnover, and daily-limit filters. Store PB as a feature, never as an admission gate. Recall up to 300 high-liquidity names and cap cache continuity at 40 candidates observed within five weekdays.

- [ ] **Step 4: Run candidate-recall tests**

Run: `python3 -m unittest tests.test_selector_v2 -v`

Expected: lineage, route, and expiry tests pass.

### Task 3: Add deduplicated V2 shadow scoring and truthful evidence

**Files:**
- Modify: `server.py`
- Modify: `tests/test_selector_v2.py`
- Modify: `tests/test_snapshot_contract.py`

- [ ] **Step 1: Preserve the legacy block exactly**

```python
candidate["legacy"] = {
    "active": True,
    "score": candidate.get("score"),
    "recommendation_degree": candidate.get("recommendation_degree") or candidate.get("confidence"),
    "components": {
        "preliminary": candidate.get("pre_score", 0),
        "chan": candidate.get("chan_score", 0),
        "czsc": candidate.get("czsc_score", 0),
        "serenity": candidate.get("serenity_score", 0),
        "uzi": candidate.get("uzi_score", 0),
        "uzi_panel": candidate.get("uzi_panel_score", 0),
    },
}
```

- [ ] **Step 2: Build five non-overlapping V2 groups**

Create `event`, `technical`, `industry`, `liquidity_flow`, and `quality` groups on a 0–100 scale. Every scoring input has one stable `feature_id` and exactly one group with `used_in_score=true`; methodology labels such as Chan, CZSC, UZI, and Serenity remain visible under `legacy` but are not summed again inside V2.

- [ ] **Step 3: Apply explainable regime priors**

```python
V2_REGIME_WEIGHTS = {
    "trend_risk_on": {"event": .20, "technical": .30, "industry": .20, "liquidity_flow": .20, "quality": .10},
    "range": {"event": .25, "technical": .20, "industry": .15, "liquidity_flow": .20, "quality": .20},
    "risk_off": {"event": .15, "technical": .15, "industry": .10, "liquidity_flow": .30, "quality": .30},
    "high_vol": {"event": .30, "technical": .15, "industry": .10, "liquidity_flow": .30, "quality": .15},
    "unknown": {"event": .20, "technical": .25, "industry": .15, "liquidity_flow": .25, "quality": .15},
}
```

- [ ] **Step 4: Add data quality, stable risk codes, and objective hard gates**

Only invalid price, incomplete K-line, explicit suspension/delisting, and known stale in-session quotes can block execution. Missing fundamentals, partial event evidence, unknown market regime, overheat, and MA distance are warnings in V2 shadow mode. Keep `source_as_of` distinct from `fetched_at`.

- [ ] **Step 5: Add within-market percentile ranks after all candidates are enriched**

Rank by V2 `rule_score`, assign `rank`, `rank_percentile`, and `rank_score`, but keep legacy candidate order and decisions active.

- [ ] **Step 6: Build a normalized event feed without fabricated sources**

Event-route records become `announcement_or_news` only when a real source record exists. Score changes and model reasons become `model_signal`. When URL, publication time, or exchange provenance is absent, use `null` plus `evidence_status: partial`.

- [ ] **Step 7: Run the full Python suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests pass and the existing fixture keeps the same legacy BUY/NO_TRADE result.

### Task 4: Repair the research backtest contract

**Files:**
- Modify: `scripts/backtest_may.py`
- Test: `tests/test_selector_v2.py`

- [ ] **Step 1: Add a signature regression test**

```python
def test_backtest_accepts_serenity_alpha_profile():
    lens_score, reasons, risks, alpha = server.serenity_lens_score({"lens": {}})
    assert isinstance(alpha, dict)
```

- [ ] **Step 2: Unpack all four values and expose the alpha metadata**

Change the backtest call to `lens_score, lens_reasons, lens_risks, alpha_profile = server.serenity_lens_score(candidate)` and include the alpha profile in each scored row.

- [ ] **Step 3: Run the regression test**

Run: `python3 -m unittest tests.test_selector_v2.SelectorV2Tests.test_backtest_accepts_serenity_alpha_profile -v`

Expected: pass.

### Task 5: Build the five-tab evidence console

**Files:**
- Replace: `static/index.html`
- Replace: `static/styles.css`
- Replace: `static/app.js`
- Create: `tests/test_frontend_contract.py`

- [ ] **Step 1: Write a static contract test**

```python
def test_five_tabs_and_accessible_panels_exist(self):
    html = Path("static/index.html").read_text()
    for tab in ("decision", "candidates", "events", "history", "model"):
        self.assertIn(f'data-tab="{tab}"', html)
        self.assertIn(f'id="panel-{tab}"', html)
```

- [ ] **Step 2: Build the shared shell**

Implement the selected reference: 190px fixed white rail, navy labels, blue active state, dense white content surface, hairline borders, square 4–8px radii, compact numerical typography, three market status rows, and a top freshness bar. Use Phosphor Icons classes for navigation and actions; do not create inline SVG or CSS-drawn icons.

- [ ] **Step 3: Implement the Decision tab**

Render a market switcher; current BUY/NO_TRADE banner; primary or blocked candidate; recommendation degree; live entry/stop/target; execution advice; V2 factor bars; legacy factor disclosure; K-line chart; risk gates; and top-five alternatives. Live quote merge updates price, K-line, and execution advice only.

- [ ] **Step 4: Implement the Candidates tab**

Render server order and V2 shadow rank side-by-side, market/risk/source filters, selected-row master/detail, source lineage, data-quality input states, hard gates, factor contributions, legacy Chan/CZSC/UZI/Serenity values, and real missing-data labels.

- [ ] **Step 5: Implement the Events tab**

Render the normalized event feed with market/type/direction/evidence filters, searchable titles, selected-event detail, model impact breakdown, affected securities, and explicit `部分证据/无原文链接` states when provenance is incomplete.

- [ ] **Step 6: Implement the History tab**

Render immutable snapshot rows, target/signal/generation time, market decisions, selected snapshot detail, recommendation-degree trend, and status labels `待验证/未接入逐笔回测` instead of invented hit rates.

- [ ] **Step 7: Implement the Model tab**

Render the actual flow `多路召回 → Legacy 评分 → V2 影子分 → 数据门控 → 决策快照`, candidate-pool boundaries, regime weights, old-factor preservation map, live-data policy, version identifiers, and Cloudflare/GitHub Actions runtime truth.

- [ ] **Step 8: Add responsive states and motion**

At widths below 900px convert the rail to a sticky horizontal tab bar, stack master/detail panels, preserve touch targets of at least 40px, and honor `prefers-reduced-motion`.

- [ ] **Step 9: Run frontend contract and syntax checks**

Run: `python3 -m unittest tests.test_frontend_contract -v && node --check static/app.js`

Expected: all tests and syntax check pass.

### Task 6: Make the Worker contract honest and Cloudflare-only

**Files:**
- Modify: `src/index.js`
- Modify: `scripts/build_worker_assets.py`
- Modify: `.github/workflows/deploy-worker.yml`
- Delete: `render.yaml`
- Delete: `runtime.txt`
- Delete: `DEPLOY_RENDER.md`

- [ ] **Step 1: Add production metadata and honest recompute behavior**

`/api/status` returns `platform: cloudflare-workers`, `snapshot_generation: github-actions`, `recompute_supported: false`, schema/model versions from the latest JSON, and its generated time. A request containing `force=1` returns HTTP 409 with a clear message to run the GitHub workflow; ordinary `/api/pick` remains backwards compatible.

- [ ] **Step 2: Split market timestamp and volume semantics**

Live responses return `source_as_of`, `fetched_at`, and `volume_unit`. A-share Eastmoney/Tencent volume uses `lot`; Yahoo volume uses `share`. The UI formatter consumes the declared unit and never divides all markets by 100.

- [ ] **Step 3: Wrap static responses with HTTPS and security headers**

Redirect HTTP to HTTPS and add HSTS, `X-Content-Type-Options`, `Referrer-Policy`, and a restrictive permissions policy without breaking the icon font or same-origin APIs.

- [ ] **Step 4: Validate build assets and summary fields**

The build script verifies the three required static files and carries `schema_version`, `selector_mode`, `weights_version`, `universe_version`, and market-regime summaries into the manifest.

- [ ] **Step 5: Update CI**

Run unit tests and `node --check` before build; install and generate snapshots only for schedule/manual runs; build and deploy every accepted run; do not install Serenity as though the skill code were executed in scoring.

- [ ] **Step 6: Remove Render files**

Delete the three Render artifacts while retaining `requirements.txt` and local `server.py`, because Python is still the GitHub Actions generator and local research server.

- [ ] **Step 7: Run the Worker dry run**

Run: `npm ci && npm run check`

Expected: Wrangler completes asset build and dry-run upload with exit code 0.

### Task 7: Rewrite strategy and operations documentation

**Files:**
- Replace: `README.md`

- [ ] **Step 1: Document the production runtime first**

State that the public site/API are Cloudflare Workers, model computation happens in scheduled GitHub Actions, immutable JSON is baked into assets, and browser refresh/live quote calls do not recompute rankings.

- [ ] **Step 2: Document candidate-pool truth**

Describe A-share dynamic event/momentum/liquidity/pullback/five-session-history routes and the curated-static HK/US universes. Do not call HK/US whole-market scans.

- [ ] **Step 3: Document old-factor preservation and V2 rollout**

Explain Legacy Active versus V2 Shadow, list the old fields that remain active, show the five V2 groups and regime weights, explain objective hard gates, and state that recommendation degree is not a calibrated probability.

- [ ] **Step 4: Document data and evidence limitations**

Separate source timestamps from fetch timestamps; name built-in CZSC/UZI/Serenity approximations accurately; disclose event URLs/timestamps may be absent; describe the current weekday-calendar limitation and backtest limitations.

- [ ] **Step 5: Document API, local validation, deployment, and rollback**

Include all public endpoints, snapshot schema examples, `python3 -m unittest discover -s tests -v`, `npm run check`, workflow dispatch, Cloudflare logs, and rollback to a previous Git commit/deployment.

### Task 8: Verify visuals and interactions against the selected design

**Files:**
- Replace: `design-qa.md`

- [ ] **Step 1: Start the local production build**

Run: `npm run build && npx wrangler dev --local --port 8787`

Expected: local Worker responds at `http://localhost:8787`.

- [ ] **Step 2: Capture all five tabs in the in-app browser**

Use the desktop viewport matching the reference, then capture Decision, Candidates, Events, History, and Model. Exercise market switching, filters, a candidate row, a history row, and a live refresh.

- [ ] **Step 3: Compare source and implementation together**

Place the attached event-screen reference and the matching implementation screenshot in one comparison input. Check rail width, column ratios, top density, typography, borders, active rows, table alignment, detail hierarchy, cropping, and responsive behavior.

- [ ] **Step 4: Fix every visible mismatch and repeat comparison**

Continue until navigation, inputs, filters, detail selection, history loading, empty states, and all five visual layouts pass.

- [ ] **Step 5: Record QA evidence**

`design-qa.md` lists the tested URL, viewport, tab and interaction matrix, accessibility checks, screenshots, known truthful data limitations, and ends with `final result: passed`.

### Task 9: Publish, regenerate V2 data, and verify production

**Files:**
- Modify: repository commit only

- [ ] **Step 1: Run the complete release gate**

Run: `python3 -m unittest discover -s tests -v && node --check static/app.js && npm run check`

Expected: all checks exit 0.

- [ ] **Step 2: Commit and update `main`**

Commit message: `feat: launch cloudflare selector v2 dashboard`

Push the exact reviewed tree to the current remote `main` without force-updating unrelated history.

- [ ] **Step 3: Trigger one manual snapshot generation**

Run the `Deploy Cloudflare Worker` workflow with `workflow_dispatch` so the new model version writes a V2 snapshot, commits it, rebuilds assets, and deploys the Worker.

- [ ] **Step 4: Verify the live API and five-tab site**

Confirm HTTPS, `/api/status`, `/api/latest`, `/api/history`, `/api/live`, schema/model version, `recompute_supported: false`, and the five tab interactions at `https://xuangu.alixjd.com/`.

- [ ] **Step 5: Report the Render boundary**

Confirm no public domain or repository deployment path depends on Render. If the separately managed Render service still exists, report its exact service URL and the remaining dashboard-only suspend/delete action; do not imply that deleting repository files stopped the external service.

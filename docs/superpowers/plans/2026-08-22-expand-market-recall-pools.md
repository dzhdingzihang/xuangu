# Expanded Three-Market Recall Pools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the production recall targets to 300 A-shares, 200 Hong Kong stocks, and 300 US stocks while preserving board/sector diversity, auditable recall lineage, and fail-closed data-health behavior.

**Architecture:** Keep candidate recall separate from deep scoring. A-shares use segmented Sina board/route queries, Eastmoney board recovery, event recall, and fresh-history fallback, followed by deterministic board quotas and fair fill to a 300-name target. Hong Kong and US retain versioned curated universes, but gain audited expansion rows, ticker normalization, stale-symbol exclusions, and exact target-size validation. Snapshot contracts expose target, achieved count, board/route/source coverage, and deficits; market recommendations remain blocked when required coverage is not achieved.

**Tech Stack:** Python 3.12, `requests`, existing selector contracts in `server.py`, `unittest`, Cloudflare Workers static deployment, GitHub Actions.

---

### Task 1: Define recall targets and deterministic diversity contracts

**Files:**
- Modify: `server.py:42-100`
- Test: `tests/test_selector_v2.py`

- [ ] **Step 1: Write failing tests for target constants, board classification, quotas, and fair fill**

```python
def test_a_share_board_classification_and_target_quota():
    assert server.a_share_board("600000") == "sh_main"
    assert server.a_share_board("000001") == "sz_main"
    assert server.a_share_board("300001") == "chinext"
    assert server.a_share_board("688001") == "star"
    assert sum(server.A_SHARE_BOARD_TARGETS.values()) == server.A_SHARE_RECALL_TARGET == 300

def test_diversified_a_share_pool_meets_board_floors_then_fair_fills():
    rows = fixture_recall_rows_by_board(120)
    selected, coverage = server.select_diversified_a_share_pool(rows, target=300)
    assert len(selected) == 300
    for board, floor in server.A_SHARE_BOARD_TARGETS.items():
        assert coverage[board] >= floor
    assert len({row["code"] for row in selected}) == 300
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `python -m unittest tests.test_selector_v2.SelectorV2Tests.test_a_share_board_classification_and_target_quota -v`

Expected: failure because the target constants and helper do not exist.

- [ ] **Step 3: Implement explicit targets and deterministic selection helpers**

```python
A_SHARE_RECALL_TARGET = 300
HK_RECALL_TARGET = 200
US_RECALL_TARGET = 300
A_SHARE_BOARD_TARGETS = {
    "sh_main": 90,
    "sz_main": 75,
    "chinext": 75,
    "star": 60,
}

def a_share_board(code: str) -> str | None:
    if code.startswith(("600", "601", "603", "605")):
        return "sh_main"
    if code.startswith(("000", "001", "002", "003")):
        return "sz_main"
    if code.startswith(("300", "301")):
        return "chinext"
    if code.startswith(("688", "689")):
        return "star"
    return None
```

`select_diversified_a_share_pool` must deduplicate by code, rank deterministically, fill each board floor, then use the remaining best candidates across all boards without exceeding the target.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_selector_v2 -v`

Expected: all selector-v2 tests pass.

### Task 2: Replace the single A-share broad query with segmented multi-route recall

**Files:**
- Modify: `server.py:1524-1635`
- Modify: `server.py:2872-2962`
- Modify: `server.py:4883-4963`
- Test: `tests/test_selector_v2.py`

- [ ] **Step 1: Write failing tests for board coverage, recall routes, and degraded-source fill**

```python
def test_segmented_broad_recall_preserves_market_and_route_lineage():
    rows = server.build_a_share_recall_pool(event_rows, broad_rows, history_rows, target=300)
    assert len(rows) == 300
    assert {server.a_share_board(row["code"]) for row in rows} == {
        "sh_main", "sz_main", "chinext", "star"
    }
    assert all((row["candidate_lineage"] or {}).get("recall_routes") for row in rows)

def test_recall_target_shortfall_is_explicit_and_never_padded_with_duplicates():
    rows, health = server.build_a_share_recall_pool([], fixture_rows(211), [], target=300)
    assert len(rows) == 211
    assert health["target_count"] == 300
    assert health["shortfall_count"] == 89
```

- [ ] **Step 2: Run the tests and confirm target/coverage failures**

Run: `python -m unittest tests.test_selector_v2 -v`

Expected: failures for missing segmented recall and health fields.

- [ ] **Step 3: Implement multi-route oversampling and fair selection**

The Sina primary loader must query each board separately and oversample several routes; Eastmoney is used only for missing-board recovery:

```python
A_SHARE_RECALL_ROUTES = (
    {"route": "liquidity", "sort": "amount", "descending": True},
    {"route": "momentum", "sort": "changepercent", "descending": True},
    {"route": "activity", "sort": "turnoverratio", "descending": True},
    {"route": "pullback", "sort": "changepercent", "descending": False},
)
```

Admission remains fail-safe: valid board, non-ST, positive price, sufficient trading amount, bounded turnover, and no near-limit-up chase. Event and fresh-history rows are merged before diversified truncation, and every retained row keeps all recall routes in `candidate_lineage`.

- [ ] **Step 4: Raise A-share deep-review capacity proportionally**

```python
max_kline_checks = int(os.environ.get("CHAN_MAX_KLINE_CHECKS", "96"))
```

The dual-low shadow analysis continues to receive the complete quoted preliminary pool. Heavy K-line scoring increases from 36 to 96 so expansion affects the final research set rather than only raw statistics.

- [ ] **Step 5: Run selector and snapshot tests**

Run: `python -m unittest tests.test_selector_v2 tests.test_snapshot_contract -v`

Expected: all tests pass.

### Task 3: Expand and validate Hong Kong and US curated universes

**Files:**
- Create: `data/universes/market_recall_expansion_v2.json`
- Modify: `server.py:42-60`
- Modify: `server.py:710-739`
- Test: `tests/test_selector_v2.py`

- [ ] **Step 1: Write failing exact-size and uniqueness tests**

```python
def test_curated_market_universe_targets_are_exact_and_unique():
    expected = {"hk": 200, "us": 300}
    for market, target in expected.items():
        rows = server.market_universe(market)
        symbols = [row["symbol"] for row in rows]
        assert len(symbols) == target
        assert len(set(symbols)) == target
        assert all(row["candidate_lineage"]["universe_origin"] == "curated_static" for row in rows)
```

- [ ] **Step 2: Run the test and confirm current 153/258 failures**

Run: `python -m unittest tests.test_selector_v2 -v`

Expected: Hong Kong reports 153 and US reports 258.

- [ ] **Step 3: Add audited expansion rows with diversification metadata**

Each JSON row must contain a current Yahoo-compatible symbol, company name, role, themes, and a `bucket` such as `large_cap_core`, `mid_cap_growth`, `value_income`, `cyclical`, `healthcare`, or `emerging_technology`. Because 90 legacy HK rows used invalid five-digit zero padding, normalize HK codes before deduplication, alias two transferred/mistyped symbols, exclude five stale listings, and add 65 expansion rows. Normalize renamed US tickers, exclude stale/non-US symbols, and add 51 net-new US rows, yielding exactly 200/300 valid unique symbols with current Yahoo daily data.

- [ ] **Step 4: Load, normalize, merge, and validate exact targets**

```python
def market_universe(market_key: str) -> list[dict]:
    rows = existing_market_rows(market_key) + expansion_rows(market_key)
    merged = merge_universe_rows(rows, market_key)
    target = {"hk": HK_RECALL_TARGET, "us": US_RECALL_TARGET}[market_key]
    if len(merged) != target:
        raise ValueError(f"{market_key} universe size {len(merged)} != target {target}")
    return merged
```

- [ ] **Step 5: Run exact-size tests**

Run: `python -m unittest tests.test_selector_v2 -v`

Expected: Hong Kong has 200 unique symbols and US has 300.

### Task 4: Publish recall coverage and enforce target-aware health gates

**Files:**
- Modify: `server.py:2437-2498`
- Modify: `server.py:4761-4797`
- Modify: `server.py:4945-5000`
- Modify: `static/app.js:220-250`
- Modify: `static/app.js:1510-1555`
- Test: `tests/test_selector_v2.py`
- Test: `tests/test_global_decision_contract.py`
- Test: `tests/test_worker_contract.py`

- [ ] **Step 1: Write failing contract tests for target, achieved, board, and route coverage**

```python
assert section["stats"]["recall_target"] == 300
assert section["stats"]["recall_achieved"] == len(pool)
assert section["stats"]["board_coverage"]["chinext"] >= 75
assert set(section["stats"]["route_coverage"]) >= {"event", "liquidity", "momentum", "pullback", "history"}
```

For HK/US, assert targets of 200/300 and publish `universe_origin=curated_static`, quoted count, deeply scored count, and shortfall.

- [ ] **Step 2: Run the contract tests and confirm missing-field failures**

Run: `python -m unittest tests.test_global_decision_contract tests.test_worker_contract -v`

Expected: failures for missing recall coverage fields.

- [ ] **Step 3: Add target-aware health contracts and UI labels**

A-share market action must be `NO_TRADE` when achieved recall is below the 300-name target, any required board misses its configured target, or quote coverage is below 80%. The strict global gate continues to require available quote status and at least 98% coverage. The UI must distinguish `召回目标`, `实际召回`, `有效行情`, and `深度评分`.

- [ ] **Step 4: Run contract and browser syntax checks**

Run: `python -m unittest tests.test_global_decision_contract tests.test_worker_contract -v && node --check static/app.js`

Expected: all tests and syntax checks pass.

### Task 5: Document, verify, publish, and validate production

**Files:**
- Modify: `README.md:24-93`
- Modify: `.github/workflows/deploy-worker.yml:75-96` only if runtime needs an explicit deep-score limit

- [ ] **Step 1: Document exact pool semantics and non-full-market caveat**

README must state: A-share target 300 with four board buckets and dynamic routes; Hong Kong target 200 and US target 300 remain curated universes; raw recall, valid quote, deep-scored, published, and executable pools are distinct; Legacy remains active while V2 and dual-low remain shadow.

- [ ] **Step 2: Run the complete validation suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

Run: `python scripts/validate_snapshot.py data/picks/latest.json && node --check src/index.js && node --check static/app.js && npm run build && git diff --check`

Expected: all checks exit successfully.

- [ ] **Step 3: Generate a forced snapshot and verify target reporting**

Run: `python server.py --once --force`

Expected: snapshot stats report targets `300/200/300`; source shortfalls remain explicit rather than being hidden or padded.

- [ ] **Step 4: Commit, push main, and monitor the deployment workflow**

```bash
git add server.py static/app.js README.md tests data/universes docs/superpowers/plans/2026-08-22-expand-market-recall-pools.md
git commit -m "feat: expand diversified market recall pools"
git push origin HEAD:main
```

Expected: GitHub Actions tests, generates/deploys the Worker, and production verification succeeds or automatically rolls back.

- [ ] **Step 5: Verify production snapshot and UI**

Run: `python scripts/verify_deployment.py data/picks/latest.json --base-url https://xuangu.alixjd.com`

Expected: deployed snapshot identity matches, all published candidates have valid strict realtime provenance, and the page displays target/actual/deep counts truthfully.

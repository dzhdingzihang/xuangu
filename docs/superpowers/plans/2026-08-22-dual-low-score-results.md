# Dual-Low Score Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the supplied `dsa-screening-score-v1` model as an A-share-only shadow analysis and present Legacy, V2, and dual-low results as distinct, understandable decision evidence.

**Architecture:** GitHub Actions keeps running `server.py` to generate immutable snapshots. A single Node bridge calls a reviewed, vendored copy of the supplied pure JavaScript scoring engine on the complete A-share quote pool before the existing 36-name deep-analysis cap; results are mapped back by stock code without changing Legacy or V2. The browser renders a three-lens score summary plus a detailed dual-low panel and never recomputes scores after a live-price refresh.

**Tech Stack:** Python 3.12, Node.js 22 ESM, vanilla HTML/CSS/JavaScript, standard-library `unittest`, Cloudflare Workers static assets, GitHub Actions.

---

## File map

- `vendor/stock-scoring-kit/index.js`: reviewed upstream scoring engine from the supplied 1.0.0 archive.
- `vendor/stock-scoring-kit/THIRD_PARTY_NOTICES.md`: source and license notice retained with the vendored engine.
- `vendor/stock-scoring-kit/LICENSE`: Apache-2.0 text shipped with the supplied package.
- `scripts/score_dual_low.mjs`: JSON stdin/stdout adapter; no network or file writes.
- `server.py`: nullable market data, model invocation, snapshot metadata, candidate mapping, and no-op market applicability.
- `tests/test_dual_low_analysis.py`: bridge, units, missing-data, market applicability, and Legacy/V2 invariants.
- `tests/test_snapshot_contract.py`: additive snapshot compatibility.
- `tests/test_frontend_contract.py`: three-lens score output and non-recomputation copy.
- `static/app.js`: score summary, dual-low status/verdict, factor detail, rejection reasons, and model explanation.
- `static/styles.css`: responsive score-lens and dual-low evidence components.
- `README.md`: model boundary, units, interpretation, rollout, and data limitations.

### Task 1: Lock the additive scoring contract

**Files:**
- Create: `tests/test_dual_low_analysis.py`
- Modify: `tests/test_snapshot_contract.py`

- [ ] **Step 1: Write tests for nullable inputs and unit conversion**

```python
def test_dual_low_input_uses_required_units_and_preserves_missing():
    quote = {
        "code": "000001", "name": "平安银行", "price": 11.32,
        "change_pct": 0.8, "amount_wan": 128000,
        "turnover_pct": 0.72, "vol_ratio": 0.94,
        "fundamentals": {"pe_ttm": 5.4, "pb": 0.55, "total_mcap_yi": 1750},
    }
    row = server.dual_low_input_from_quote(quote)
    self.assertEqual(row["amount"], 1_280_000_000)
    self.assertEqual(row["totalMarketCap"], 175_000_000_000)
    self.assertEqual(row["changePct"], 0.8)

    quote["fundamentals"]["pe_ttm"] = None
    self.assertIsNone(server.dual_low_input_from_quote(quote)["peRatio"])
```

- [ ] **Step 2: Write tests for ranked, rejected, and unsupported states**

```python
def test_dual_low_mapping_has_stable_statuses():
    result = server.dual_low_unavailable("hk", "MARKET_STRATEGY_NOT_CONFIGURED")
    self.assertEqual(result["status"], "not_applicable")
    self.assertEqual(result["reason_code"], "MARKET_STRATEGY_NOT_CONFIGURED")
```

- [ ] **Step 3: Write the non-interference regression**

```python
def test_dual_low_overlay_does_not_change_legacy_or_v2():
    candidate = fixture_candidate()
    before = copy.deepcopy({"score": candidate["score"], "confidence": candidate["confidence"]})
    server.attach_dual_low_analysis(candidate, ranked_fixture(), "a_share")
    self.assertEqual(candidate["score"], before["score"])
    self.assertEqual(candidate["confidence"], before["confidence"])
    self.assertNotIn("dual_low", candidate.get("v2", {}).get("factor_groups", {}))
```

- [ ] **Step 4: Run the focused tests and confirm they fail before implementation**

Run: `python3 -m unittest tests.test_dual_low_analysis -v`

Expected: failures for the new helper functions.

### Task 2: Vendor and invoke the supplied model safely

**Files:**
- Create: `vendor/stock-scoring-kit/index.js`
- Create: `vendor/stock-scoring-kit/THIRD_PARTY_NOTICES.md`
- Create: `vendor/stock-scoring-kit/LICENSE`
- Create: `scripts/score_dual_low.mjs`

- [ ] **Step 1: Preserve the reviewed engine and notices**

Copy the archive's `src/index.js`, `THIRD_PARTY_NOTICES.md`, and Apache license without behavior changes. Record package version 1.0.0 in the adapter output.

- [ ] **Step 2: Add the stdin/stdout bridge**

```javascript
import fs from "node:fs";
import { scoreUniverse } from "../vendor/stock-scoring-kit/index.js";

const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const stocks = Array.isArray(payload.stocks) ? payload.stocks : [];
const result = scoreUniverse(stocks, {
  maxOutput: stocks.length,
  vetoHighRisk: false,
  applyPortfolioPenalty: false,
});
process.stdout.write(JSON.stringify({ packageVersion: "1.0.0", ...result }));
```

- [ ] **Step 3: Check syntax and a deterministic fixture**

Run: `node --check vendor/stock-scoring-kit/index.js && node --check scripts/score_dual_low.mjs`

Expected: both checks exit 0.

### Task 3: Add the A-share shadow overlay to snapshots

**Files:**
- Modify: `server.py`
- Modify: `tests/test_dual_low_analysis.py`
- Modify: `tests/test_snapshot_contract.py`

- [ ] **Step 1: Add nullable parsing beside `safe_float`**

```python
def nullable_float(value) -> float | None:
    try:
        if value in (None, "", "-"):
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 2: Preserve raw fundamental availability in Tencent quotes**

Add `fundamentals.pe_ttm`, `fundamentals.pb`, and `fundamentals.total_mcap_yi` using `nullable_float`; keep existing numeric top-level fields for Legacy compatibility.

- [ ] **Step 3: Build model inputs with exact units**

```python
def dual_low_input_from_quote(quote: dict) -> dict:
    fundamentals = quote.get("fundamentals") or {}
    return {
        "code": quote.get("code"), "name": quote.get("name"),
        "isST": "ST" in str(quote.get("name") or "").upper(),
        "amount": nullable_product(quote.get("amount_wan_raw"), 10_000),
        "peRatio": fundamentals.get("pe_ttm"),
        "pbRatio": fundamentals.get("pb"),
        "totalMarketCap": nullable_product(fundamentals.get("total_mcap_yi"), 100_000_000),
        "price": nullable_float(quote.get("price")),
        "changePct": nullable_float(quote.get("change_pct")),
        "volumeRatio": nullable_float(quote.get("vol_ratio")),
        "turnoverRate": nullable_float(quote.get("turnover_pct")),
    }
```

- [ ] **Step 4: Invoke once on the complete preliminary quote pool**

Run before `preliminary[:max_kline_checks]`. Use a 20-second timeout, parse stdout, and fail open to a stable `unavailable` result when Node or the adapter fails.

- [ ] **Step 5: Map results without changing Legacy/V2**

Store results only under `candidate.analysis_projects.dual_low`. Use statuses `ranked`, `rejected`, `unavailable`, and `not_applicable`; include model ID, pool scope, rank denominator, factor scores, contributions, penalties, reasons, missing fields, and an interpretation label.

- [ ] **Step 6: Add top-level batch metadata**

```json
{
  "analysis_models": {
    "dual_low": {
      "model_id": "dsa-screening-score-v1",
      "package_version": "1.0.0",
      "mode": "shadow_overlay",
      "supported_markets": ["a_share"],
      "pool_scope": "a_share.selector_quote_pool"
    }
  }
}
```

- [ ] **Step 7: Run Python contract tests**

Run: `python3 -m unittest tests.test_dual_low_analysis tests.test_snapshot_contract tests.test_selector_v2 -v`

Expected: all tests pass and existing Legacy/V2 values remain unchanged.

### Task 4: Make the result output decision-first and comparable

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: Add score-lens helpers**

Implement `dualLowAnalysis`, `dualLowLabel`, `scoreLensCards`, and `dualLowPanel`. Labels must distinguish `双低优先`, `双低观察`, `非双低风格`, `数据不足`, and `暂不适用` without turning the score into a probability.

- [ ] **Step 2: Replace the four-number detail strip with three model lenses plus data quality**

The cards must read:

```text
实际决策：Legacy 推荐度
影子排序：V2 rule_score and rank
价值筛选：Dual-low final_score or rejection status
证据完整度：data_quality
```

- [ ] **Step 3: Add a full dual-low panel below V2 factor groups**

For ranked names, show rank/denominator, seven factor scores, base score, risk deduction, and the statement “研究优先级，不是上涨概率，不参与当前 BUY / NO_TRADE”. For rejected names, show machine-readable filter reasons translated by the supplied messages. For HK/US, show a compact not-applicable state.

- [ ] **Step 4: Add an A-share dual-low column to the candidate table**

Display `#rank · finalScore` when ranked and a short style/data status otherwise. Do not sort in the browser.

- [ ] **Step 5: Add the model card and pipeline step**

Explain that dual-low is a separate A-share batch model, its comparison pool, default hard-filter boundary, and current shadow status.

- [ ] **Step 6: Add responsive styles**

Use the existing blue/white system, no gradients. Collapse seven factor bars to one column below 760px and preserve readable rejection reasons.

- [ ] **Step 7: Run frontend contracts and syntax checks**

Run: `python3 -m unittest tests.test_frontend_contract -v && node --check static/app.js`

Expected: all checks pass.

### Task 5: Document and verify the release

**Files:**
- Modify: `README.md`
- Modify: `.github/workflows/deploy-worker.yml`

- [ ] **Step 1: Document model interpretation and boundaries**

State that Legacy stays active, V2 stays shadow, dual-low is an A-share-only independent batch ranking, rejected does not mean a bad company, and no displayed score is an upside probability.

- [ ] **Step 2: Check the vendored JavaScript in CI**

Add `node --check scripts/score_dual_low.mjs` and `node --check vendor/stock-scoring-kit/index.js` before snapshot generation.

- [ ] **Step 3: Run the complete verification set**

Run:

```bash
python3 -m unittest discover -s tests -v
node --check src/index.js
node --check static/app.js
node --check scripts/score_dual_low.mjs
node --check vendor/stock-scoring-kit/index.js
npm run build
npx wrangler deploy --dry-run
```

Expected: every command exits 0; `public/data/picks/latest.json` keeps the additive model fields.

- [ ] **Step 4: Visual QA locally**

Open the built page, verify Decision, Candidates, and Model tabs at desktop and mobile widths, and confirm old snapshots degrade to “待生成” rather than throwing.

## Self-review

- Coverage: engine, units, batch scope, nullable values, failure isolation, three result lenses, rejected states, market applicability, tests, docs, CI, and visual QA are included.
- Placeholder scan: no implementation step relies on TBD/TODO behavior.
- Type consistency: all candidate-level results use `analysis_projects.dual_low`; all batch metadata uses `analysis_models.dual_low`.


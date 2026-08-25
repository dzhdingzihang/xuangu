# Production Qualified Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 上线一条不伪造上涨概率、可以真实产出合格股票的 10 日生产规则模型，同时继续把未通过样本外检验的概率模型隔离在 Shadow 轨。

**Architecture:** 保留 `global_decision` 的严格校准概率合同，新增独立 `production_decision` 合同。生产规则模型只使用已发布快照内的 Legacy、V2、官方事件、客观交易门禁、数据质量和风险收益区间；任何一个必要条件失败都输出明确 blocker。页面优先展示 `production_decision`，但把“规则合格分”与“上涨概率”永久分开。

**Tech Stack:** Python 3.12、Cloudflare Workers、Vanilla JavaScript、GitHub Actions、`unittest`、Node syntax checks。

---

### Task 1: 新增纯函数生产规则模型

**Files:**
- Create: `production_rule_model.py`
- Create: `tests/test_production_rule_model.py`

- [ ] **Step 1: 写失败测试**

覆盖以下合同：健康市场的完整候选在 Legacy `BUY_CANDIDATE`、V2 前 20%、官方事件已扫描且至少一条正面证据、风险收益区间合格时输出 `QUALIFIED_PICK`；其他市场降级不能连带阻断；重大负面、未扫描事件、缺深研、风险收益不足分别输出稳定 blocker；规则分不能命名为概率。

```python
def test_qualified_pick_is_market_isolated_and_not_a_probability():
    decision = build_production_decision(snapshot_fixture())
    assert decision["action"] == "QUALIFIED_PICK"
    assert decision["primary"]["score_kind"] == "AUDITED_RULE_ENSEMBLE"
    assert decision["primary"]["probability"] is None
    assert decision["primary"]["calibrated"] is False
    assert decision["primary"]["market"] == "hk"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_production_rule_model -v`

Expected: FAIL，因为 `production_rule_model` 尚不存在。

- [ ] **Step 3: 实现固定合同与门槛**

```python
MODEL_ID = "ten-day-audited-rule-ensemble-v1"
CONTRACT_VERSION = "production-qualified-10d-v1"
ACTION_PICK = "QUALIFIED_PICK"
ACTION_NONE = "NO_QUALIFIED_PICK"
MARKET_POLICY = {
    "a_share": {"min_legacy": 64, "max_downside": -8.0, "min_upside": 5.0},
    "hk": {"min_legacy": 63, "max_downside": -8.0, "min_upside": 5.0},
    "us": {"min_legacy": 64, "max_downside": -10.0, "min_upside": 6.0},
}

def build_production_decision(snapshot: dict) -> dict:
    """Return one market-isolated, evidence-backed rule candidate or abstain."""
```

合格候选必须同时满足：候选所在市场 `READY`、完整 Legacy 深研、所有客观门禁 `PASS`、必需输入 fresh、无重大负面、逐股事件扫描完成、至少一条官方正向事件、市场 Legacy 动作为 `BUY_CANDIDATE`、推荐度达到分市场阈值、V2 排名进入前 20%、10 日区间下沿和上沿达到策略阈值、上行/下行比不低于 `1.20`。最终分数由 Legacy 30%、V2 30%、数据质量 15%、事件证据 15%、风险收益 10% 组成，明确标记 `score_kind=AUDITED_RULE_ENSEMBLE`、`probability=null`、`calibrated=false`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_production_rule_model -v`

Expected: PASS。

### Task 2: 接入快照并隔离概率轨

**Files:**
- Modify: `server.py`
- Modify: `tests/test_global_decision_contract.py`
- Modify: `tests/test_snapshot_contract.py`

- [ ] **Step 1: 写集成失败测试**

```python
def test_enrichment_publishes_production_decision_without_promoting_shadow():
    enriched = server.enrich_snapshot_v2(snapshot_fixture())
    assert enriched["production_decision"]["action"] == "QUALIFIED_PICK"
    assert enriched["global_decision"]["action"] == "NO_VALID_PICK"
    assert enriched["analysis_models"]["ten_day_return"]["participates_in_decision"] is False
```

- [ ] **Step 2: 接入模型**

在 `enrich_snapshot_v2()` 完成事件、候选 enrich 和 `global_decision` 后、删除 `_candidate_pool` 前调用：

```python
snapshot["production_decision"] = production_rule_model.build_production_decision(snapshot)
```

`data_health.decision_usable` 改为生产规则候选或严格概率候选任一可用；同时新增 `decision_mode`，不得把规则分写进 `global_decision.probability`。

- [ ] **Step 3: A 股完整深研覆盖 300 只**

把 `A_SHARE_DEEP_SCORE_LIMIT` 从 `96` 调整为 `300`，并同步更新池健康、调度健康门槛、README 和测试夹具。仍允许少量 K 线/交易性失败，但 98% 覆盖规则保持不变。

- [ ] **Step 4: 运行服务端合同测试**

Run: `python -m unittest tests.test_production_rule_model tests.test_global_decision_contract tests.test_snapshot_contract tests.test_selector_v2 -v`

Expected: PASS。

### Task 3: 让事件扫描命中生产候选

**Files:**
- Modify: `event_pipeline.py`
- Modify: `.github/workflows/deploy.yml`
- Modify: `tests/test_event_pipeline.py`
- Modify: `tests/test_workflow_reliability.py`

- [ ] **Step 1: 写候选预排序失败测试**

```python
def test_event_scan_prefers_ensemble_shortlist_over_raw_pool_order():
    symbols = event_pipeline._candidate_symbols(snapshot(), "hk", 16)
    assert symbols[0] == "0300.HK"
    assert len(symbols) == 16
```

- [ ] **Step 2: 实现事件预排序**

按 Legacy 推荐度、V2 绝对排名百分位、数据质量、风险收益和候选所在市场的 Legacy 动作预排序，再扫描；不使用 Shadow 概率。默认 `EVENT_SCAN_CANDIDATES_PER_MARKET=16`，仍保留最大 30 的成本上限。确保市场 primary、blocked candidate 和 watchlist 的并集不会被遗漏。

- [ ] **Step 3: 保持事件硬边界**

只有 `verified`、自动抓取、官方域名、发布时间和生效时间可验证的事件才能贡献正向证据；`model_signal`、旧主题文本和浏览器人工推断继续禁止进入生产门禁。

- [ ] **Step 4: 运行事件与工作流测试**

Run: `python -m unittest tests.test_event_pipeline tests.test_workflow_reliability -v`

Expected: PASS。

### Task 4: 前端优先展示合格候选且不伪造概率

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: 写前端合同失败测试**

断言前端识别 `production-qualified-10d-v1`，展示 `QUALIFIED_PICK`、`AUDITED_RULE_ENSEMBLE`、规则合格分和风险收益区间，并继续展示 Shadow P10 为“仅研究”。

- [ ] **Step 2: 实现 `productionDecisionTruth()`**

服务端 `production_decision` 是唯一权威来源，浏览器不得自行重排或放宽门槛。决策首页优先顺序为：严格校准概率候选、生产规则合格候选、研究优先项。规则候选卡显示“生产规则模型·待复核”，不显示百分号概率。

- [ ] **Step 3: 区分无候选原因**

页面分别显示“生产规则模型无合格候选”和“校准概率模型仍在 Shadow”，不得再把“模型未上线”误写为“市场没有好股票”。

- [ ] **Step 4: 运行 JS 检查**

Run: `node --check static/app.js && python -m unittest tests.test_frontend_contract -v`

Expected: PASS。

### Task 5: Worker、校验与历史摘要保留新合同

**Files:**
- Modify: `scripts/build_worker_assets.py`
- Modify: `src/index.js`
- Modify: `scripts/validate_snapshot.py`
- Modify: `scripts/verify_deployment.py`
- Modify: `tests/test_build_worker_assets.py`
- Modify: `tests/test_worker_contract.py`

- [ ] **Step 1: 写序列化失败测试**

```python
def test_worker_history_preserves_qualified_rule_candidate():
    summary = summarize_pick(snapshot_with_production_decision())
    assert summary["production_decision"]["action"] == "QUALIFIED_PICK"
    assert summary["production_decision"]["primary"]["probability"] is None
```

- [ ] **Step 2: 扩展快照校验**

校验 contract/version/action/model_id/score_kind、唯一 primary、分数 0..100、`probability=null`、`calibrated=false`、候选市场为 `READY`、官方事件 ID 非空、所有 qualification gates 为 PASS。`NO_QUALIFIED_PICK` 必须 primary 为空且 blocker 非空。

- [ ] **Step 3: 扩展 Worker 与部署验收**

API `/api/latest`、`/api/history` 和部署 verifier 必须保留并核对 `production_decision` 的 action、primary identity、model_id 和 prediction_id；不得把它合并进 calibrated executable ledger 或 Brier 分母。

- [ ] **Step 4: 运行合同测试**

Run: `python -m unittest tests.test_build_worker_assets tests.test_worker_contract -v && node --check src/index.js`

Expected: PASS。

### Task 6: 文档、全量验证与上线

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-25-production-qualified-selector.md`

- [ ] **Step 1: 更新 README**

清楚区分三层输出：Legacy/V2 研究信号、`production_decision` 生产规则合格候选、`global_decision` 校准概率候选；说明 A 股 300 只深研、事件扫描 16/市场、市场隔离、规则分不等于概率及历史验证边界。

- [ ] **Step 2: 全量测试**

Run: `python -m unittest discover -s tests -v`

Expected: 全部 PASS。

- [ ] **Step 3: 生成一份真实快照并验证当前候选**

Run: `AUTOMATION_TRIGGER=workflow_dispatch python server.py --once --force`

Expected: 快照通过 `scripts/validate_snapshot.py`；如果出现 `QUALIFIED_PICK`，它必须满足全部资格门禁；如果没有，必须给出逐项 blocker，不能为了出现股票改阈值。

- [ ] **Step 4: 提交、推送并触发 Cloudflare 部署**

Run: `git push origin HEAD:main`，随后触发 `Deploy Cloudflare Worker` 的 `workflow_dispatch`。

Expected: Python、JavaScript、快照校验、Cloudflare 部署和线上完整合同验证全部成功。

- [ ] **Step 5: 线上复核**

检查 `/api/status`、`/api/latest`、`/api/history`、六个 tab、候选池覆盖、事件证据、生产规则模型 action、严格概率轨状态和不可变哈希。记录部署前后时间戳与 GitHub Actions 链接。

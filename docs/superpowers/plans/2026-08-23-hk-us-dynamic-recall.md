# 港股与美股动态召回实施计划

> **For Codex:** REQUIRED SUB-SKILL: Use writing-plans to implement this plan task-by-task.

**Goal:** 将港股 200 只、美股 300 只候选池从仓库静态名单改为随每次定时任务读取市场横截面、按当日流动性与价格行为进行多路召回，再让全部入池标的进入现有 Yahoo K 线、Chan/CZSC、Serenity、UZI 深度评分。

**Architecture:** 新增 Eastmoney 港美普通股票横截面发现层，以成交额、温和动量、可控回踩、活跃度和大盘核心五条互补路径产生可审计候选；采用确定性配额、去重和公平补位得到港股 200 / 美股 300。发现失败或规模不足时不以旧静态池冒充动态结果，而由市场级 `pool_health` 阻止推荐并触发 GitHub Actions 后备刷新。静态名单仅保留旧快照兼容和代码回归用途。

**Tech Stack:** Python 3.12、Eastmoney 市场横截面、Yahoo Finance 行情/K 线、`concurrent.futures`、`unittest`、原生 JavaScript、GitHub Actions、Cloudflare Worker。

---

### Task 1: 用测试固定动态发现、筛选和配额契约

**Files:**
- Modify: `tests/test_selector_v2.py`
- Modify: `tests/test_snapshot_contract.py`
- Modify: `tests/test_schedule_gate.py`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: 写失败测试**

覆盖港美证券代码规范化、基金/权证/无成交标的过滤、五路召回、精确 200/300、确定性去重、来源链和发现不足时的降级语义。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_selector_v2 tests.test_snapshot_contract tests.test_schedule_gate tests.test_frontend_contract -v`

Expected: FAIL，因为生产代码仍使用 `curated_static`。

### Task 2: 实现港美动态横截面发现与多路召回

**Files:**
- Modify: `server.py`
- Test: `tests/test_selector_v2.py`

- [ ] **Step 1: 拉取并规范化市场横截面**

港股读取普通股票市场，美股读取 Nasdaq/NYSE/AMEX；保留正价格、正成交、Yahoo 可解析的普通股代码，排除 ETF、基金、权证、债券、优先股和异常证券。

- [ ] **Step 2: 按互补路径形成候选池**

分别按 `liquidity`、`momentum`、`pullback`、`activity`、`quality` 配额选择；每只股票保存当次成交额、涨跌幅、换手/量比、市值、观测时间和全部命中路径。

- [ ] **Step 3: 精确选出港股 200 / 美股 300**

先满足路径配额，再按综合横截面排序公平补位；不复制、不用静态名单补足。返回发现总量、合格量、选择量、路径完成量与缺口。

- [ ] **Step 4: 运行选择器测试**

Run: `python -m unittest tests.test_selector_v2 -v`

Expected: PASS。

### Task 3: 接入评分、快照健康门禁和自动补跑

**Files:**
- Modify: `server.py`
- Modify: `scripts/validate_snapshot.py`
- Modify: `scripts/schedule_gate.py`
- Modify: `.github/workflows/deploy-worker.yml`
- Modify: `tests/test_snapshot_contract.py`
- Modify: `tests/test_schedule_gate.py`

- [ ] **Step 1: 让动态池进入现有完整评分**

港股 200 和美股 300 全部进入 Yahoo 实时行情、日 K、Chan/CZSC、Serenity、UZI 与风控门控；候选来源不再参与主题先验加分。

- [ ] **Step 2: 发布动态池健康统计**

快照发布 `universe_origin=dynamic_market_snapshot`、发现来源、发现/合格/选中数量、路径配额与计数、来源时间以及 `pool_health`；任何目标不足或行情覆盖不足都必须降级且不能给出买入建议。

- [ ] **Step 3: 校验与自动恢复**

新版本快照必须满足动态来源及计数恒等式；调度门禁把发现失败、动态池不足加入可恢复原因，使后备时点自动重跑。

- [ ] **Step 4: 运行契约测试**

Run: `python -m unittest tests.test_snapshot_contract tests.test_schedule_gate -v`

Expected: PASS。

### Task 4: 更新页面口径和 README

**Files:**
- Modify: `static/app.js`
- Modify: `README.md`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: 更新候选池与健康页**

页面明确显示“动态市场池”、市场发现数量、五路召回完成度、有效行情和深度评分；继续兼容旧快照的“静态池”标签。

- [ ] **Step 2: 更新策略说明**

README 说明三市场的候选池来源、筛选边界、评分因子、更新时点、失败门禁以及动态召回不等于收益保证。

- [ ] **Step 3: 运行前端检查**

Run: `python -m unittest tests.test_frontend_contract -v && node --check static/app.js`

Expected: PASS。

### Task 5: 全量验证、推送和生产验收

**Files:**
- Verify: repository tests, generated snapshot, GitHub Actions, Cloudflare production

- [ ] **Step 1: 运行完整测试**

Run: `python -m unittest discover -s tests -v`

Expected: 全部 PASS。

- [ ] **Step 2: 生成并校验真实快照**

Run: `python server.py --once --force && python scripts/validate_snapshot.py data/picks/latest.json`

Expected: 港股 200/200、美股 300/300，来源为动态市场快照，统计自洽；数据不足时则明确降级而非伪造满池。

- [ ] **Step 3: 提交并推送**

Run: `git add server.py static/app.js scripts/validate_snapshot.py scripts/schedule_gate.py .github/workflows/deploy-worker.yml tests README.md docs/superpowers/plans/2026-08-23-hk-us-dynamic-recall.md && git commit -m "feat: add dynamic HK and US recall"`

Run: `git push git@github.com:dzhdingzihang/xuangu.git HEAD:main`

Expected: GitHub Actions 构建并发布 Cloudflare Worker。

- [ ] **Step 4: 验证线上**

检查 `https://xuangu.alixjd.com/api/latest`、`/api/status` 和页面，确认新版本、动态来源、目标计数、行情新鲜度和交互均正常。

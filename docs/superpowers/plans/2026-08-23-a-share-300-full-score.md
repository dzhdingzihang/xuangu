# A 股 300 只全量评分实施计划

> **For Codex:** REQUIRED SUB-SKILL: Use writing-plans to implement this plan task-by-task.

**Goal:** 将 A 股流水线从“300 只召回、96 只才读取 K 线并评分”改成“300 只有效行情全部基础评分和 K 线技术评分，再从中选前 96 只执行完整深度研究”，同时保留现有因子、严格披露实际完成量并在线发布。

**Architecture:** 召回和实时行情后，对全部有效行情生成 `pre_score`；一次有界并发拉取全部股票日 K，对 K 线完整的股票计算现有 `chan_score` 与 `czsc_score`，以基础分和技术分组合选择深研前 96。只有深研结果进入 Legacy 决策候选池，避免把轻量评分误当作完整推荐；快照新增基础、技术、深研三层计数，健康门禁和页面按真实完成量展示。

**Tech Stack:** Python 3、`concurrent.futures`、`unittest`、原生 JavaScript、GitHub Actions、Cloudflare Worker 静态快照。

---

### Task 1: 用测试固定六层漏斗和全量技术评分语义

**Files:**
- Modify: `tests/test_selector_v2.py`
- Modify: `tests/test_snapshot_contract.py`
- Modify: `tests/test_schedule_gate.py`
- Modify: `tests/test_frontend_contract.py`

**Step 1: Write the failing tests**

- 构造 3 只有效行情、3 份完整 K 线、深研上限 2 的测试，断言基础评分 3、技术尝试 3、技术完成 3、深研尝试/完成 2。
- 构造部分 K 线缺失测试，断言技术覆盖按全部有效行情计算，并触发稳定降级原因码。
- 快照契约要求 A 股发布 `base_scored_size`、`technical_attempted_size`、`technical_scored_size`、`technical_kline_complete_size`、`technical_kline_coverage`、`deep_eligible_size`，同时保留 `deep_*`。
- 调度健康门禁要求技术阶段覆盖率达到 98%，否则健康补跑。
- 前端契约要求显示“基础评分 / 技术评分 / 深度研究”。

**Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_selector_v2 tests.test_snapshot_contract tests.test_schedule_gate tests.test_frontend_contract`

Expected: FAIL，因为全量技术阶段字段和行为尚未实现。

### Task 2: 改造 A 股评分流水线

**Files:**
- Modify: `server.py`
- Test: `tests/test_selector_v2.py`

**Step 1: Add scoring-stage constants and bounded K-line retries**

- 新增 A 股技术评分最低覆盖率常量 98%。
- `a_share_kline_map` 首轮维持最多 12 并发，对缺失代码再以最多 4 并发重试两轮。
- 新取回或缓存的 K 线末日必须是预期交易日或紧邻的上一交易日；多日陈旧/未来数据不计入完整覆盖。

**Step 2: Score every quote-valid candidate before deep research**

- 对全部 `preliminary` 一次拉取 K 线。
- 全部候选生成组合技术排序分；完整 K 线计算现有 `chan_signal`、`czsc_structure_score`，短历史候选使用中性技术贡献并扣除不确定性，且不进入深研。
- 以组合技术排序分选择前 `A_SHARE_DEEP_SCORE_LIMIT`，再运行现有 Serenity、UZI、UZI Panel 等完整逻辑；双低继续覆盖全部有效行情，不缩窄到 96 只。
- 保持返回的 `candidates` 为完整深研池，保持决策安全边界；新增并返回基础、技术、深研各层统计。

**Step 3: Run focused selector tests**

Run: `python3 -m unittest tests.test_selector_v2`

Expected: PASS。

### Task 3: 将新统计接入健康门禁和快照契约

**Files:**
- Modify: `server.py`
- Modify: `scripts/validate_snapshot.py`
- Modify: `scripts/schedule_gate.py`
- Modify: `tests/test_snapshot_contract.py`
- Modify: `tests/test_schedule_gate.py`

**Step 1: Publish stage fields**

- A 股 `stats` 发布基础评分、技术评分和深研统计。
- `a_share_pool_health` 校验技术评分尝试覆盖全部有效行情，且完成率至少 98%。
- 新增稳定原因码 `A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM`。

**Step 2: Validate accounting invariants**

- 基础评分数等于有效行情数。
- 技术尝试数等于基础评分数，技术完成数不超过尝试数，覆盖率精确一致。
- `deep_eligible_size` 等于“技术 K 线完整且通过可交易性过滤”的数量；深研尝试数等于 `min(96, deep_eligible_size)`，深研完成数不超过尝试数。
- `scored_size` 继续等于深研完成数，明确其是决策候选数而非全量轻评分数。

**Step 3: Run contract and gate tests**

Run: `python3 -m unittest tests.test_snapshot_contract tests.test_schedule_gate`

Expected: PASS。

### Task 4: 更新页面和策略说明

**Files:**
- Modify: `static/app.js`
- Modify: `README.md`
- Modify: `tests/test_frontend_contract.py`

**Step 1: Render the six-stage funnel**

- 页面展示 `召回目标 → 实际召回 → 有效行情 → 基础评分 → 技术评分 → 深度研究`。
- 健康页显示技术评分与深研的实际完成量/尝试量，并翻译新原因码。
- 模型说明明确：300 只都进入基础和技术阶段，96 只是较重的研究预算，不是只有 96 只被评分。

**Step 2: Document retained factors and selection boundary**

- README 解释 `pre_score`、Chan/CZSC、Serenity、UZI/评审团、双低的所在阶段。
- 解释 K 线或行情缺失时按真实数量降级，不伪造 300/300。

**Step 3: Run frontend contract test**

Run: `python3 -m unittest tests.test_frontend_contract`

Expected: PASS。

### Task 5: 全量验证、提交和线上发布

**Files:**
- Verify: repository test suite and generated snapshot artifacts

**Step 1: Run full test suite**

Run: `python3 -m unittest discover -s tests`

Expected: 全部测试 PASS。

**Step 2: Generate and validate a real snapshot locally when source access permits**

Run: `python3 server.py --once --force`

Run: `python3 scripts/validate_snapshot.py data/picks/latest.json`

Expected: 快照契约通过；A 股显示基础评分接近/等于 300、技术评分实际覆盖、深研最多 96。

**Step 3: Commit and push**

Run: `git add server.py static/app.js scripts/validate_snapshot.py scripts/schedule_gate.py tests README.md docs/superpowers/plans/2026-08-23-a-share-300-full-score.md && git commit -m "feat: score full A-share recall pool"`

Run: `git push git@github.com:dzhdingzihang/xuangu.git HEAD:main`

Expected: GitHub Actions 构建和 Cloudflare 发布成功。

**Step 4: Verify production**

- 检查 `https://xuangu.alixjd.com/api/status` 与最新快照。
- 断言线上漏斗字段存在、计数自洽、页面可打开且显示六层口径。

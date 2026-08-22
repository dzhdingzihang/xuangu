# 智能选股（A 股 / 港股 / 美股）

[线上站点](https://xuangu.alixjd.com) · [Cloudflare Worker 状态](https://xuangu.alixjd.com/api/status)

这是一个面向约 10 个交易日观察周期的三市场选股研究工具。它把候选召回、价格结构、行业/主题、流动性与资金、方法论因子和风险门控合成可追溯的决策快照，并在网页中同时展示“为什么进入候选”“为什么得分”“为什么能买或被拦截”。

> 推荐度是确定性规则映射，不是经过校准的上涨概率；预估区间不是收益承诺。本项目仅用于研究辅助，不构成投资建议。

## 生产架构：只使用 Cloudflare 提供网站

公开网页和 API 均由 Cloudflare Workers 提供，不再使用 Render 作为生产运行面。

```text
GitHub Actions 定时或手动触发
  → Python 拉取行情、生成三市场候选与评分
  → 写入 data/picks/<timestamp>.json 和 latest.json
  → 构建 public 静态资产与历史 manifest
  → Wrangler 部署 Cloudflare Worker
  → xuangu.alixjd.com 提供网页、快照 API 和实时行情 API
```

这里有一个重要边界：现有 Python 选股程序不能在普通 Worker 请求里直接运行。模型计算发生在 GitHub Actions，Worker 读取发布时烘焙的不可变 JSON。网页“刷新”会重读最新快照；`/api/live` 只刷新当前股票的行情和执行提示，不会偷偷改变推荐度、V2 排名、双低排名或 BUY/NO_TRADE。

`GET /api/pick?force=1` 在生产环境会返回 `409`，明确提示使用 GitHub Actions 手动工作流，避免出现“按钮显示正在重算、实际仍是旧快照”的假动作。

## 页面结构

网站使用五个独立 Tab：

1. **决策**：A 股、港股、美股的当前结论，首选/被拦截候选、买入参考、止损/止盈、K 线、因子证据和门控。
2. **候选**：当前 API 返回候选的 Legacy 顺序、V2 结构排名、A 股双低独立榜单、来源链、数据质量、风险项和单股详情。
3. **事件**：真实事件召回和模型信号证据；没有原文 URL 或发布时间时明确标记“部分证据”，不会伪造交易所公告。
4. **历史**：按 `snapshot_key` 打开同一天的每一次不可变快照，比较当时首选和推荐度变化。没有成熟收益标签时显示“待验证”。
5. **模型说明**：候选池、旧因子、V2 分组、双低七因子、市场状态权重、数据门控、版本和运行架构。

## 当前上线方式：Legacy Active + V2 Shadow + Dual-Low Shadow

这次升级没有删掉之前的选股因子，也没有立即用新分数替换历史决策。

```text
Legacy Active
  继续决定候选顺序、推荐度和 BUY_CANDIDATE / NO_TRADE

V2 Shadow
  同步输出去重后的分组得分、市场状态、来源链、数据质量、风险码和市场内排名
  暂不改变 Legacy 决策，用真实历史样本观察 20–40 个交易日后再决定是否切换

Dual-Low Shadow（A 股）
  在同一批 A 股报价池中运行 PE/PB 双低七因子，输出通过/拒绝、横截面排名和风险扣分
  作为独立价值风格分析，不进入 Legacy、V2 或 BUY/NO_TRADE
```

每个候选仍保留这些旧字段：

- `score` / `recommendation_degree` / `confidence`
- `pre_score`
- `chan_score` / `chan`
- `czsc_score` / `czsc`
- `uzi_score` / `uzi`
- `uzi_panel_score` / `uzi_panel`
- `serenity_score` / `serenity`
- `reasons` / `risk_flags` / `hard_risk_count`
- `estimated_2w_range` / `entry_price` / `stop_loss` / `take_profit_reference`

同时新增：

- `legacy`：把当前生效的旧分数及组成集中存档。
- `v2`：影子规则分、市场内百分位、分组贡献和市场状态。
- `candidate_lineage`：候选来自哪条召回路线、何时观察到、证据是否完整。
- `data_quality`：行情、K 线、事件和市场输入的完整度。
- `decision_gates`：明确列出 PASS / WARN / BLOCK。
- `risk_items`：用稳定风险码去重，避免同一风险在多个模块重复扣分。
- `analysis_projects.dual_low`：单股双低状态、排名、七因子、扣分、过滤原因和缺失字段。
- `analysis_models.dual_low`：整批输入/合格/拒绝数量、评分时点、前五名和拒绝原因分布。

顶层兼容标识：

```json
{
  "schema_version": "selector-snapshot-v2",
  "selector_mode": "legacy_active_v2_dual_low_shadow",
  "weights_version": "v2-rule-prior-1",
  "universe_version": "recall-v2-1"
}
```

## 候选池逻辑

### A 股：动态多路召回

A 股先从全市场建立宽候选，再对有限数量做 K 线和方法论深评。候选会合并来源链，不再让后一个来源覆盖前一个来源。

- `event`：同花顺事件/异动池；缺少原文链接或准确发布时间时保留空值并标记为部分证据。
- `momentum`：流动性合格、相对强势但未触及追高区间的股票。
- `liquidity`：按成交额召回，不再要求当日必须上涨。
- `pullback`：高流动性、处于可控回调区间的股票。
- `history`：最近 5 个工作日出现过的候选，最多保留 40 只，防止一次数据源抖动让候选突然消失。

PB 不再作为能否进入候选池的硬门槛；它可以是估值研究输入，但不能把高 PB 的成长行业在召回阶段全部删掉。ST、退市风险、无有效价格、成交不足和明显不可交易状态仍会过滤或门控。

### 港股 / 美股：策展静态池 + 实时深评

当前港股和美股使用版本化的策展池，覆盖主要指数权重及 AI 芯片、光通信、HBM/存储、半导体设备、数据中心电力/液冷、neocloud、机器人、软件、量子和商业航天等方向，然后获取 Yahoo Finance K 线/行情完成深评。

它们会标记 `universe_origin: curated_static`。这不是港美“全市场动态扫描”，README 和页面都不会这样宣传。真正的全市场证券主表、退市历史和点时财务数据属于后续数据工程。

## 当前生效的 Legacy 选股策略

Legacy 仍是本次生产决策依据。

### 1. 初筛与实时可买性

- 当日涨跌幅、成交额、换手率、量比和流通市值。
- 主题/事件文字命中和龙虎榜资金线索。
- 涨停、一字板、20cm 过热、高换手、低成交额等追高风险。
- A 股腾讯实时行情；港美 Yahoo Finance 盘前/盘中/盘后或日 K 回退。

### 2. 缠论量化映射

- MA5 > MA10，最好 MA10 > MA20。
- 二买近似：多头结构后的首次回踩 MA5/MA10 未破，并重新收回。
- 三买近似：突破近 20 日箱体/中枢后回踩不回箱体。
- 价格新低但 MACD 柱改善只作为反转加分，不单独触发买入。
- 跌破 MA10、偏离 MA10 过大、买入后强度未兑现会降分或退出。

### 3. CZSC 结构因子

生产代码使用内置轻量近似规则：日线中枢突破/回踩、MA20/MA30 趋势、箱体位置和背驰风险。`czsc` 是否能被 Python import 只进入运行状态元数据；当前评分并没有调用官方 CZSC 框架的完整事件/信号引擎。

### 4. UZI 方法论因子

内置规则参考多维评分、评审团共识、游资射程、买点纪律、流动性、过热和陷阱风险。`uzi_panel` 是规则化近似评审，不是运行 `wbh604/UZI-Skill` 的完整外部程序。

### 5. Serenity 产业链因子

偏好 hyperscaler AI capex 上游瓶颈，例如 CPO/InP、HBM/存储、半导体设备、数据中心电力/液冷和受限供给；融资稀释、弱客户验证、单一催化和追高会降权。

候选池内的 `lens` 和内置函数实际参与评分。安装 `SKILL.md` 只影响运行状态标记，不会自动读取研究内容或改变分数；Serenity GitHub 查询仅用于记录 commit 等元数据，因子变化仍需代码审阅和版本发布。

### 6. Legacy 决策门槛

Legacy 总分映射到“推荐度”，再结合以下条件决定是否出推荐：

- 市场风险是否为高风险。
- 推荐度是否达到对应市场阈值。
- 硬风险数量和风险标签数量。
- A 股成交承接是否足够。
- 是否已接近涨停或明显过热。
- 两周预估区间的下沿是否过低。

通过时为 `BUY_CANDIDATE`；未通过为 `NO_TRADE`，同时保存 `blocked_candidate` 说明最接近阈值的股票为什么被拦截。

## V2 影子评分

旧模型里，同一条涨幅、量比、MA10 偏离或风险数量会在 Chan、UZI、UZI Panel、硬风险和最终推荐度中多次出现。V2 的第一目标是把原子特征唯一归组，不是堆更多名字。

五个 0–100 分组：

- `event`：事件方向、时效、证据完整度和是否已被价格反映。
- `technical`：均线结构、二买/三买、突破回踩、背驰和涨幅透支。
- `industry`：行业/主题强度及 Serenity 产业链位置。
- `liquidity_flow`：成交额、换手、量比、龙虎榜和成交可行性。
- `quality`：客户/供给确定性、财务质量和融资稀释；数据不足时标记 `missing/partial`，不会装作已经拿到财务数据。

每个用于 V2 的原子特征都有稳定 `feature_id`，且只能在一个分组里 `used_in_score: true`。Chan、CZSC、UZI、Serenity 的旧分会继续显示在 `legacy`，但不会把相同价格信息再次机械相加到 V2。

### 市场状态权重

V2 使用可解释先验权重，不使用尚未训练的机器学习模型：

| 市场状态 | 事件 | 技术 | 行业 | 流动性/资金 | 质量 |
|---|---:|---:|---:|---:|---:|
| 趋势上涨 `trend_risk_on` | 20% | 30% | 20% | 20% | 10% |
| 震荡 `range` | 25% | 20% | 15% | 20% | 20% |
| 风险下降 `risk_off` | 15% | 15% | 10% | 30% | 30% |
| 高波动 `high_vol` | 30% | 15% | 10% | 30% | 15% |
| 数据未知 `unknown` | 20% | 25% | 15% | 25% | 15% |

`unknown` 会保留警告，绝不等同于“市场正常”。

### 数据质量和风险门控

时间字段拆成：

- `source_as_of`：交易所或数据源所代表的真实行情时间；拿不到就为空。
- `fetched_at`：服务器抓取时间。

不能用抓取时间伪装成最新成交时间。V2 第一阶段只让客观执行问题进入 BLOCK：无有效价格、K 线不足、明确停牌/退市风险、明确不可成交，以及正常交易时段已知行情严重过期。数据缺少、市场状态未知、估值/财务未接入等先作为 WARN，不抢先改变 Legacy 决策。

A 股另有候选池级别的生产门控：宽基池至少 80 只，合并候选取得腾讯报价的覆盖率至少 80%。任一条件未达标时，页面仍保留已有股票和原始 Legacy / V2 / 双低分数供研究，但正式动作强制为 `NO_TRADE`，并发布稳定的 `pool_health.reason_codes`。这避免“只抓到很小一撮股票，却把其中第一名误当成全市场最优”的假精确。

## 双低七因子独立分析

模型 ID 为 `dsa-screening-score-v1`，来自随项目保留许可证和第三方声明的 `stock-scoring-kit 1.0.0`。源码以零运行时依赖形式保存在 `vendor/stock-scoring-kit/`，Python 每次快照只通过 Node bridge 批量调用一次；浏览器和 Cloudflare Worker 不重算。

### 比较池和执行边界

- 仅支持 A 股；港股、美股明确返回 `not_applicable`，不会把人民币阈值或 A 股估值口径硬套过去。
- 在 A 股合并召回且取得报价的完整 `preliminary` 池上计算，发生在最多 36 只 K 线深评截断之前。
- 页面只携带可见候选的既有结果；`rank_universe_size` 仍是完整合格批次，不用网页上的 8–9 只重新排名。
- 运行失败、Node 不可用、结果损坏或字段异常时标记 `unavailable`，Legacy 和 V2 继续生成。

默认风格过滤：成交额至少 5000 万元、PE TTM 0–15、PB 0–2、总市值 50–3000 亿元、价格 3–80 元、当日涨跌幅 -4.5%–4.5%，同时排除 ST/退市风险名称。边界只决定“是否符合双低风格”，不会把股票从主候选池删除；被拒绝不等于公司质量差。

七因子权重：

| 因子 | 权重 | 主要含义 |
|---|---:|---|
| 估值 `value` | 34% | PE/PB 同批横截面 |
| 稳定性 `stability` | 20% | 涨跌、活跃度与异常风险 |
| 流动性 `liquidity` | 14% | 成交额横截面 |
| 动量 `momentum` | 10% | 温和趋势、避免过热 |
| 活跃度 `activity` | 10% | 量比与换手适中 |
| 反转 `reversal` | 6% | 可控回调线索 |
| 规模 `size` | 6% | 总市值横截面 |

```text
base_score = Σ(七因子分 × 归一化权重)
final_score = base_score - risk_penalty - portfolio_penalty
```

首版显式关闭组合集中度扣分和外部分融合：`portfolio_penalty_enabled=false`、`externalWeight=0`。当前输入配置 `quote_valuation_core_v1` 已接入 PE、PB、总市值、成交额、价格、涨跌幅、换手率和量比；60 日涨跌、MACD、RSI、20 日波动率/回撤/ATR及日线质量尚未对整批公平接入，因此相关可选项使用模型中性回退，快照会保留覆盖率和警告。

硬过滤必需值使用 nullable 原始字段。PE/PB/总市值缺失时输出 `validation.*.invalid` 和 `missing_fields`，不会通过 `safe_float` 把缺失伪装成 0。

页面把三套结果解释为：Legacy 回答“当前怎么做”，V2 回答“结构质量如何”，双低回答“是否属于低估值风格”。它们不机械相加，任何分数都不是上涨概率。

## 排名、推荐度和未来模型

- `legacy.recommendation_degree`：当前生产规则推荐度。
- `v2.rule_score`：去重后的影子规则分。
- `v2.rank_percentile`：本次同市场已深评候选内的百分位，不是全市场百分位。
- `analysis_projects.dual_low.final_score`：同批 A 股双低研究优先分；只在 `status=ranked` 时存在。
- `analysis_projects.dual_low.rank`：双低合格池内排名；拒绝、不可用和港美不适用状态使用 `null`，不是 0 分。
- 页面只展示 API 实际返回的首选/被拦截候选和 watchlist；`scored_size` 不等于浏览器能看到的完整列表数量。

以下内容尚未上线，也不会在页面中伪造：LightGBM/LambdaRank、未来 10 日正收益概率、q10/q50/q90、Expected Alpha、Brier/ECE、Rank IC、跨市场统一概率排名。启用前至少需要点时历史、真实交易所日历、可成交入场价、费用/滑点、不可成交处理、purge/embargo 滚动样本外验证，以及 20–40 个交易日影子样本。

## 数据源和回退

- A 股事件/题材：同花顺公开事件接口。
- A 股全市场、行业热度、龙虎榜：东方财富。
- A 股实时报价与双低核心字段：腾讯财经，包括成交额、换手率、量比、PE TTM、PB 和总市值；缺失状态单独保留。
- Worker 实时接口：优先东方财富，整组失败时回退腾讯；只覆盖行情，不重算任何评分。
- A 股日 K：百度股市通 → 东方财富 → 腾讯三级回退。
- 港股/美股日 K 和实时参考：Yahoo Finance chart。
- 历史连续性：近期不可变快照中的真实候选/K 线；不会凭空生成走势。
- 公开研究仓库：只作为方法论和版本元数据，不等于执行外部框架。

外部数据是尽力获取，可能延迟、限频或口径不同。A 股成交量通常以“手”返回，Yahoo 通常以“股”返回；API 使用 `volume_unit` 明确单位，前端不会统一再除以 100。

## 快照与 API

```text
GET /api/status
GET /api/latest-summary
GET /api/latest
GET /api/history?limit=120
GET /api/pick?date=2026-08-19
GET /api/pick?snapshot=2026-08-19_2026-08-19_220629.json
GET /api/live?market=a_share&code=603228
GET /api/live?market=hk&code=1882.HK
GET /api/live?market=us&code=PWR
```

行为说明：

- 历史详情必须优先使用 `snapshot_key`；同一天可能有多次快照。
- 日期没有匹配时，`/api/pick?date=` 可能回退 latest，前端会明确提示实际展示的快照日期。
- `latest-summary` 和 `history` 是轻量摘要；候选、K 线和完整诊断在 `latest` / `pick`。
- JSON 响应 `Cache-Control: no-store`；发布资产由 Cloudflare 边缘提供。
- `/api/live` 不做服务端模型重算，也不承诺交易所直连实时性。

## 自动运行时间

GitHub Actions 的目标北京时间检查点：

```text
工作日 08:58 / 09:58 / 10:58 / 12:58 / 13:58 / 14:58 / 21:28 / 23:58
```

Workflow cron 使用 UTC：

```text
58 0,1,2,4,5,6,15 * * 1-5
28 13 * * 1-5
```

每个主检查点还有一个 30 分钟后的补跑：

```text
工作日 09:28 / 10:28 / 11:28 / 13:28 / 14:28 / 15:28 / 21:58
以及次日 00:28 补跑前一工作日 23:58 检查点
```

可靠性链路如下：

- 定时任务按 `main` 串行排队，补跑会先检查线上 `/api/status` 和仓库 `latest.json`；已发布同一检查点时自动跳过。
- 周五 23:58 即使排队到周六凌晨，4 小时窗口内仍会归入周五检查点，不再被周末判断误杀。
- 一次 Workflow 内的快照生成最多尝试 3 次，网络请求和腾讯报价也各自最多尝试 3 次有界退避。
- 先校验并部署 Cloudflare，再归档 JSON 到 Git；因此 Git 非快进冲突不会阻止已经验证的快照上线。`latest.json` 同时上传为 14 天恢复 artifact。
- 部署后轮询 `/api/status` 和 `/api/latest`，必须同时匹配 `generated_at`、`snapshot_key`、模型版本、schema 和 selector mode 才算成功。

页面每 5 分钟轮询一次状态；只有 `generated_at` 发生变化才重载最新快照与历史，并保留候选、事件和历史筛选。状态分为 `fresh / updating / stale / unknown`，对应“数据正常 / 更新中 / 数据已过期 / 状态未知”；候选池或行情降级使用独立徽章，避免把“快照按时”误解为“数据一定完整”。旧快照始终可查看，但过期后会明确标红，而不是继续显示绿色正常。

GitHub 定时任务不是精确计时器，第三方公开数据源也没有 SLA。以上机制能显著降低漏跑、瞬时网络失败和归档冲突的影响，但不能承诺 100% 准点或数据源永不故障。当前日期函数只识别周一到周五，不识别 A/H/US 各自节假日或半日市；补跑仍使用相同公开数据源，不是独立供应商灾备。因此这里称“工作日目标检查点 + 可观测补偿”，不称“交易所开盘日绝对保证”。

## 本地开发与验证

环境：Python 3.12、Node.js 22。

```bash
git clone https://github.com/dzhdingzihang/xuangu.git
cd xuangu
python3 -m pip install -r requirements.txt
npm ci
```

运行全部离线测试：

```bash
python3 -m unittest discover -s tests -v
node --check src/index.js
node --check static/app.js
node --check scripts/score_dual_low.mjs
node --check vendor/stock-scoring-kit/index.js
```

构建和 Wrangler dry-run：

```bash
npm run check
```

本地 Worker：

```bash
npm run dev
```

一次完整选股会访问外部行情并可能耗时数分钟：

```bash
python3 server.py --once --force
```

研究回测脚本：

```bash
python3 scripts/backtest_may.py
```

该脚本是固定 2026 年 5 月样本的研究工具，存在工作日代替真实交易日、信号日收盘成交、同样本挑参数和汇报结果等限制，不能作为生产胜率或 V2 上线依据。

## 部署

推送 `main` 会测试、构建并部署现有快照；定时或 `workflow_dispatch` 还会先生成新快照。

```bash
gh workflow run deploy-worker.yml --repo dzhdingzihang/xuangu --ref main
gh run list --repo dzhdingzihang/xuangu --workflow deploy-worker.yml --limit 3
```

Cloudflare Secrets：

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`（推荐显式设置，避免多账户歧义）

直接部署：

```bash
npm ci
npm run build
npx wrangler deploy
```

线上验收：

```bash
curl -fsS https://xuangu.alixjd.com/api/status
curl -fsS https://xuangu.alixjd.com/api/latest-summary
curl -fsSI https://xuangu.alixjd.com/
```

Render 配置已经从仓库移除。若 Render 控制台中以前创建的 `chan-stock-selector.onrender.com` 服务仍存在，删除仓库文件不会自动关闭那个外部服务；需要在 Render 控制台 Suspend/Delete 并关闭 Auto-Deploy。它不再是 `xuangu.alixjd.com` 的生产依赖。

## 风险提示

模型会犯错，数据源会延迟，规则分会因市场状态和样本选择产生偏差。请把页面当成一套可检查的研究证据和风险清单，而不是自动下单信号；任何真实交易都应独立核对公告、成交状态、仓位、止损和个人风险承受能力。

# 智能选股（A 股 / 港股 / 美股）

[线上站点](https://xuangu.alixjd.com) · [服务状态](https://xuangu.alixjd.com/api/status) · [源码仓库](https://github.com/dzhdingzihang/xuangu)

这是一个面向未来约两周、即 10 个交易日的三市场选股研究系统。系统扫描 A 股、港股和美股候选，结合价格、技术结构、流动性、产业链、事件证据、风险与交易可行性，给出一只跨市场“研究优先项”；只有生产门禁全部满足时，才允许升级为可执行复核候选。

本项目不会把规则分冒充上涨概率，也不会为了每天一定给出股票而绕过数据问题。当证据、市场覆盖、模型校准或交易成本口径不完整时，跨市场正式答案是 `NO_VALID_PICK`，研究优先项则以 `RESEARCH_ONLY` 单独展示。

> 本项目仅用于研究辅助，不构成投资建议。任何预估区间、分数和历史结果都不是收益承诺。

## 一眼看懂系统输出

页面同时呈现三类结论，它们的权限不同：

| 输出 | 回答的问题 | 是否可当成上涨概率 | 是否直接产生正式买入结论 |
|---|---|---:|---:|
| `Legacy` 市场级规则 | 当前旧因子体系在各市场更偏好谁 | 否 | 只产生市场级 `BUY_CANDIDATE / NO_TRADE` |
| `V2` 与双低影子分析 | 结构质量、去重评分和低估值风格如何 | 否 | 否 |
| `global_decision.research_priority` | 三市场全部候选中，谁最值得优先研究 | 否，`score_kind=RULE_PRIORITY` | 否，状态固定为 `RESEARCH_ONLY` |
| `global_decision.primary` | 哪只股票通过完整生产门禁 | 只有校准模型上线后才可解释为概率 | 是，但当前缺条件时为空 |

`RULE_PRIORITY` 是确定性规则优先级，不是“未来 10 天上涨概率”，也不能解释为“80 分等于 80% 会涨”。系统当前尚无满足生产要求的校准概率时，会明确发布 `probability_status=UNAVAILABLE`。

## 选股与评分机制

### 1. 三市场候选召回

系统先建立足够宽的召回池，再通过有效行情、全池基础评分、全池技术评分和较重的方法论深研逐层收窄。A 股页面和快照分开发布六层真实计数：`召回目标 → 实际召回 → 有效行情 → 基础评分 → 技术评分 → 深度研究`，不再把它们混为“候选数”。

- **A 股召回目标 300 只**：沪市主板 90、深市主板 75、创业板 75、科创板 60。四个板块分开过量拉取，再按板块配额和优先级去重；不会用重复代码补齐 300。
- **A 股多路召回**：事件 40、相对动量 80、可控回调 65、流动性 85、历史延续 30 是路由软目标。交易活跃度是附加命中标签；候选可同时命中多条路由。当实时宽基已满 300 时，历史候选不挤占实时席位；只在实时来源不足时按最多 5 个交易日、带衰减元数据补位。
- **A 股可交易性初筛**：排除 ST、名称含“退”、N/C 新股和无效价格；常规成交额至少 3 亿元（数据源降级补位时 1.5 亿元），换手率 0.5%–22%，涨跌幅不低于 -4.5%；主板排除≥8.8%、创业板/科创板排除≥14% 的过热追涨。PB 不是进入召回池的硬门槛。
- **A 股基础评分覆盖全部有效行情**：健康批次目标是 300/300。每只有效报价都会计算 `pre_score`，包括涨跌幅、成交额、换手率、量比、流通市值、题材和龙虎榜等；`base_scored_size` 必须严格等于 `valid_quote_size`。
- **A 股技术评分覆盖全部有效行情候选**：全部基础评分候选都会生成 `screen_score` 和 `screen_rank`。至少 32 根有效日 K 时使用现有 Chan/CZSC 技术结构；上市历史不足时仍进入评分，但技术贡献按中性值并额外扣除数据不确定性，且不能进入深研。快照同时发布 `technical_scored_size` 和 `technical_kline_complete_size`，因此“300 只都评分”和“其中多少只有完整 K 线”不会混为一谈。K 线完整安全门槛是至少 98%，即 300 只中至少 294 只；K 线末日还必须是预期交易日或紧邻的上一交易日，陈旧多日的数据不能冒充完整覆盖。
- **A 股深度研究 96 只**：`deep_eligible_size` 先统计“技术 K 线完整且通过 ST/退市/新股等可交易性过滤”的数量，再按全池 `screen_score` 取前 96 只运行 Serenity、UZI、UZI Panel/评审团、完整 Legacy、V2 和交易门禁。`deep_attempted_size=min(96, deep_eligible_size)`；深研完成数低于 95（96 的 98% 安全线）时，快照降级为 `NO_TRADE` 并触发计划补跑。兼容字段 `scored_size` 仍表示“完成深研、可进入决策的候选数”，不表示全池评分数量。
- **港股召回目标 200 只、美股 300 只**：仍是版本化策展池，但从单一 AI 主题扩展到金融、消费、医疗、工业、能源/公用事业、REIT、通信与新兴科技。港股代码统一规范为 Yahoo 可用的 4 位 `.HK`；美股会处理更名/并购代码并排除退市或非美股标的。
- **港美行情新鲜度**：`realtime_count` 同时要求正价格和可验证的 `source_as_of`。系统用 XHKG/XNYS 交易日历判断最近应覆盖的交易时段；常规盘中还要求时间延迟不超过 20 分钟。旧交易日、未来超过 5 分钟或无效价格都不会计入实时覆盖；覆盖低于 98% 时暂停该市场推荐并补跑。
- 港美快照明确标记 `universe_origin=curated_static`。这不是港美全市场动态扫描；在接入可靠的全市场证券主表、退市历史和点时财务数据前，系统不会宣传为“全市场覆盖”。

### 2. Legacy 因子继续保留

升级没有删除原有因子。Legacy 继续保存并参与各市场内部排序：

- 基础行情：价格、涨跌幅、成交额、换手率、量比和流通市值。
- 缠论近似：MA5/MA10/MA20、二买/三买近似、箱体突破回踩、MACD 改善和过度乖离。
- CZSC 轻量映射：中枢突破/回踩、MA20/MA30 趋势、箱体位置和背驰风险。
- UZI 规则映射：多维评分、评审团近似、游资射程、买点纪律、流动性和过热/陷阱风险。
- Serenity 产业链因子：AI capex 上游瓶颈、客户/供给确定性，以及稀释、单一催化和追高风险。
- 风险与交易门槛：市场风险、分数阈值、硬风险数、成交承接、涨停/过热和两周区间下沿。

完成深研的候选保留 `score`、`recommendation_degree`、`pre_score`、`screen_score`、`screen_rank`、`chan_score`、`czsc_score`、`uzi_score`、`uzi_panel_score`、`serenity_score`、`reasons`、`risk_flags`、`estimated_2w_range`、入场参考和风险价位等字段。Legacy 的市场级动作不会自动升级成跨市场可执行答案。

### 3. V2 去重影子评分

V2 的目标不是再堆一套名字，而是避免相同的涨幅、量比、均线偏离或风险被多次重复加减分。原子特征用稳定 `feature_id` 归入且只归入一个分组：

- `event`：方向、时效、证据完整度和价格反应。
- `technical`：均线、突破回踩、二买/三买、背驰与涨幅透支。
- `industry`：行业/主题强度和产业链位置。
- `liquidity_flow`：成交额、换手、量比、龙虎榜和成交可行性。
- `quality`：客户/供给确定性、财务质量和融资稀释；缺少数据时保留 `missing/partial`。

V2 根据 `trend_risk_on / range / risk_off / high_vol / unknown` 使用可解释先验权重。`v2.rule_score` 和 `v2.rank_percentile` 都是本次已深评候选内的规则结果，不是全市场百分位或校准概率。V2 当前保持 Shadow，不改变 Legacy 动作。

### 4. A 股双低七因子

`dsa-screening-score-v1` 作为独立研究项目运行在 A 股合并召回且取得报价的完整 preliminary 池上，关注估值、稳定性、流动性、动量、活跃度、反转和规模。默认风格过滤包括 PE TTM 0–15、PB 0–2、总市值 50–3000 亿元、价格 3–80 元、成交额至少 5000 万元和不过热。

双低结果只回答“是否符合这套低估值风格”；被过滤不等于公司差，分数也不与 Legacy/V2 机械相加。港股和美股明确为 `not_applicable`。

### 5. 跨市场研究优先级

全局层会评估三个市场的完整候选集合，而不是只比较三个市场各自第一名。当前不能产生校准预测时，会按可审计的规则贡献计算 `research_priority`，并输出稳定的 `prediction_id`、`model_id`、`label_version`、市场、证券和 10 交易日窗口。

研究优先项状态为：

```json
{
  "status": "RESEARCH_ONLY",
  "score_kind": "RULE_PRIORITY",
  "priority_score_kind": "auditable_rule_priority_v1"
}
```

它用于回答“今天最值得先研究哪一只”，不等于“今天应当买入哪一只”。

### 6. global 严格门禁

跨市场正式动作由 `strict_cross_market_gate_v1` 控制。以下任一类条件不满足，就输出 `NO_VALID_PICK`：

- 三市场候选覆盖、行情健康或市场状态不可比；
- 候选存在结构化 `BLOCK` 或重大负面事件；
- 自动事件管线未完成扫描，或候选缺少可用于决策的事件证据；
- 未来 10 日正收益概率没有完成样本外校准；
- 手续费、税费、点差、滑点、汇兑与尾部风险未进入统一净收益口径；
- 快照过期、关键来源不可用或其他生产合同字段不完整。

“事件扫描结果为 0 条有效事件”是合法状态，不应伪造事件；但零条有效证据也不能被当作正面催化通过门禁。重大负面证据会直接阻断对应候选。只有全部条件通过，`global_decision.action` 才能从 `NO_VALID_PICK` 升级为 `REVIEW_EXECUTABLE_PICK`。

## 事件证据管线

事件页把三类信息严格分开：

1. 自动事件证据：由管线扫描、规范化和去重，保存原文 URL、来源、发布时间、生效时间、市场和证券映射；只有 `decision_eligible=true` 的合格记录可参与门禁。
2. 人工核验待入库：可以帮助研究，但在进入自动不可变快照前不能参与买入门禁。
3. `model_signal`：模型为何关注某只股票的解释，不是外部新闻、公告或事实。

事件管线必须发布“是否已扫描、状态、有效条数和拒绝原因”，不会把无法访问原文、缺发布时间或只有模型描述的内容包装成官方证据。

## 真实交易日历与约两周窗口

交易窗口由 `exchange-calendars==4.13.2` 计算，使用：

- A 股：`XSHG`
- 港股：`XHKG`
- 美股：`XNYS`

每个市场的计划入场日是严格晚于 `generated_at` 的第一个常规开盘时点，避免盘中已经看见当日开盘后仍用该开盘价结算造成前视偏差。退出日是从入场交易日开始计数的第 10 个市场交易日收盘。周末、当地节假日和不同市场交易日差异由各自日历处理，因此同一快照的 A/H/US 入场日或结束日可能不同。

关键字段包括：

- `entry_session_open_at`
- `entry_trade_date`
- `forecast_end_trade_date`
- `horizon_sessions=10`
- `calendar_id` / `calendar_version`

这套规则已经替代“周一到周五等于交易日”的旧逻辑。

## Shadow outcome ledger（研究结果账本）

每个满足每日采样策略的稳定 `RESEARCH_ONLY` 研究优先项会写入 `data/outcomes/<prediction_id>.json`，track 固定为 `SHADOW_RESEARCH`。账本与正式可执行模型绩效完全分开：

- 工作日多时点快照全部保留，但定时绩效账本只在每日末次 `22:47` 主检查点登记一条 `PENDING`；手动运维刷新不登记绩效样本，避免把同日高度相关的盘中快照误当成多个独立样本；
- 入场采用下一交易日开盘，退出采用第 10 个交易日收盘；
- 退出日尚未完整结束时不会提前结算；
- 成熟后使用同市场日线，按市场记录成本假设，结算为 `SETTLED`；
- A 股使用前复权日线，港美使用 Yahoo adjusted close 因子调整的开盘与收盘；
- 同一 `prediction_id` 幂等更新，不修改原始决策快照。

Shadow 胜率和收益只能描述这条研究优先规则的历史，不得混入 `global_decision.primary` 的生产绩效，也不得用来声称已有校准概率。页面历史 Tab 会单独展示 Shadow 的 PENDING/SETTLED 状态；没有合法样本时显示无样本，不填造 0 胜率。

## 云端定时快照与数据源

生产站使用纯云端批次快照，不依赖 Render、Futu OpenD、个人电脑、Docker 或 Tunnel 常驻。GitHub Actions 在计划检查点获取公开数据、重算候选池和全部评分，验证通过后由 Cloudflare Worker 发布不可变快照。电脑关机不会影响下一次云端任务。

快照生成时使用的主要数据口径为：

- A 股宽基主召回来自新浪行情中心的沪主板/深主板/创业板/科创板分板块横截面，东方财富在某板块缺口时回退；报价和 K 线使用腾讯财经与东方财富的有界重试/回退链路。日 K 通过 GitHub Actions Cache 跨批次复用，缺失代码才低并发补拉；盘中技术分会用本轮腾讯实时行情覆盖缓存中的当日日线，缓存只优化请求频率，不替代行情新鲜度门禁。
- A 股龙虎榜数据来自东方财富数据中心公开接口。
- 港股和美股候选的价格与日线主要来自 Yahoo Finance chart 数据；候选边界仍是版本化策展静态池。
- 事件、公告、新闻和人工待入库证据在快照中分类标记；只有保存来源 URL、发布/生效时间并通过合同校验的自动证据才能参与严格门禁。
- XSHG / XHKG / XNYS 交易窗口由版本化 `exchange-calendars` 计算。

这些是公开 best-effort 数据源，没有交易所级 SLA。页面显示的价格、涨跌和 K 线都属于已发布快照，不是浏览器盘中实时行情。顶栏的 `snapshot_as_of` 表示快照生成时间，`next_refresh` 表示下一个计划检查点，不是数据供应商或 GitHub 的准点保证。

## 生产架构

静态页面、选股快照和 API 都在 Cloudflare Workers。Render、OpenD 和个人设备都不是生产依赖。

```text
GitHub Actions（定时 / 手动）
  → 安装 Python/Node 依赖并运行测试
  → 生成三市场不可变选股快照
  → 登记/结算 Shadow outcome ledger
  → 校验 schema 与生产合同
  → 构建 public 静态资产和历史 manifest
  → Wrangler 部署 Cloudflare Worker
  → 完整线上契约验证
  → 成功后将快照和 ledger 归档回 main

Cloudflare Worker（请求时）
  → 提供页面、快照、历史与状态 API
  → 只读 GitHub Actions 已生成并经验证的静态 assets
  → 不在请求时获取行情，也不重算选股
```

Python 选股程序不会在 Worker 或浏览器请求中重算。页面只读 `/api/latest` 与历史快照；刷新页面不改变 Legacy、V2、双低分数、全局排序或门禁结论。`GET /api/pick?force=1` 固定返回 `409 RECOMPUTE_NOT_SUPPORTED`，需要重算时应手动触发 GitHub Actions。

## 数据更新时序与可靠性

工作日北京时间（`Asia/Shanghai`）计划：

```text
主跑：08:17 / 10:17 / 12:17 / 15:17 / 16:17 / 20:17 / 22:47
健康补跑：08:47 / 10:47 / 12:47 / 15:47 / 16:47 / 20:47 / 23:17
```

七个主跑分别覆盖盘前与隔夜收盘、A/H 早盘、亚洲午间、A 股收盘、港股收盘、美股盘前和美股开盘。`22:47` 兼顾美股夏令时与冬令时，都会落在常规交易开始之后。每个主跑后 30 分钟有一次健康补跑。`schedule_gate.py` 只用线上完整 `/api/latest` 作为“已成功发布”证据：对应主跑已发布健康快照时跳过补跑；线上不可达、主跑缺失/失败，或行情/候选池处于可恢复降级时，补跑继续尝试。门禁会硬校验 A/港/美实际召回是否分别达到 `300 / 200 / 300`；任一市场差 1 只也不会把该快照当作健康主跑。同时校验港美最近交易时段覆盖至少 98%、A 股基础评分覆盖全部有效行情、技术评分至少完成 98%，以及 96 只深研中至少完成 95 只。仓库里的 `latest.json` 不能单独抑制补跑，因为它不证明 Cloudflare 已经切换成功。

一次生成与 outcome 结算各最多尝试 3 次。部署前执行单元测试、JavaScript 语法检查、snapshot schema 校验和 immutable 快照一致性检查；部署后验证线上 `generated_at`、`snapshot_as_of`、`next_refresh`、`snapshot_key`、schema、模型版本、历史和不可变快照。生成、测试或部署前校验失败时不会切换生产版。部署前还会记录当前唯一 100% 生效的 Cloudflare Worker Version 和快照摘要；若部署后完整验收失败，Workflow 会标红并自动回滚到该精确版本，再核对旧快照身份与摘要。这是自动恢复，不是零暴露发布：新版在部署后验证窗口内可能短暂在线；回滚本身若失败也会继续标红，需要人工处理。定时或手动成功生成快照后，恢复包保留 30 天，归档失败也会显式标红。

浏览器每 5 分钟读取一次 `/api/status`，只有 `generated_at` 变化才重载快照和历史。它不会轮询盘中行情，也不在前端重算评分与排序。快照 `fresh` 只表示它满足发布时效合同，不等于所有公开数据源绝对完整。

GitHub scheduled workflow 不是精确计时器，可能因平台排队延后。公开数据源也没有 SLA，因此系统提供的是“目标检查点 + 健康补跑 + 可观测降级”，不是 100% 准点保证。交易所休市、任务排队或数据源失败时，`next_refresh` 也只是下一个计划检查点（含健康补跑）。

## 故障降级

| 故障 | 系统行为 |
|---|---|
| 定时生成、测试或部署前校验失败 | 不切换线上 assets；继续提供当前版本，并让 Workflow 标红 |
| 部署后完整验收失败 | 自动回滚到部署前精确 Worker Version，核对旧快照摘要；验收窗口内新版可能短暂在线 |
| 主跑快照缺失或数据源可恢复降级 | 30 分钟后健康补跑继续尝试；已有健康快照时跳过 |
| 候选池或行情覆盖不足 | 保留研究数据，但门控正式动作并发布稳定 reason codes |
| 自动事件管线无合格证据 | 发布真实 0 条状态，不伪造事件；正式门禁不通过 |
| 模型未校准 | `probability_status=UNAVAILABLE`，只输出 `RULE_PRIORITY` 研究优先项 |
| 指定历史日期不存在 | `/api/pick?date=` 返回 `404 PICK_NOT_FOUND`，不会静默回退 latest |
| 日期格式非法 | 返回 `400 INVALID_DATE` |
| 历史 manifest 不可用 | 返回 `503 HISTORY_MANIFEST_UNAVAILABLE`，页面不显示伪 0 样本 |
| 快照过期 | 页面标记 stale，global 门禁阻止升级；旧不可变档案仍可审计 |

## API 契约

```text
GET /api/status
GET /api/latest-summary
GET /api/latest
GET /api/history?view=daily&limit=120
GET /api/history?view=raw&limit=120
GET /api/pick?date=2026-08-24
GET /api/pick?snapshot=<snapshot_key>.json
# 旧客户端兼容路由：只返回已发布快照，不获取实时行情
GET /api/live?market=a_share&code=603228
GET /api/live?market=hk&code=01882.HK
GET /api/live?market=us&code=PWR
```

契约要点：

- `/api/status` 返回快照版本、新鲜度、`snapshot_as_of`、`next_refresh`、主跑/健康补跑检查点、`data_mode=scheduled_snapshot` 和 `device_dependency=false`。
- `/api/latest` 返回完整快照；`/api/latest-summary` 返回轻量摘要。
- `/api/history` 默认 `view=daily`，按 `target_date` 合并盘中重复运行，同类保留最后一次；`view=raw` 返回不可变原始运行。绩效和 Shadow 账本另按 `prediction_id` 去重。
- `/api/pick?snapshot=` 是最精确的历史寻址方式；同一天可能有多次快照。
- `/api/pick?date=` 只返回该日期匹配项；非法日期 400、不存在 404，绝不静默返回 latest。
- `/api/live` 只是保留 URL 的 scheduled-snapshot 兼容接口，浏览器不调用它。它只返回当前已发布快照中同时保存了正价格、`source_as_of`、`fetched_at` 和成交量单位的可追溯行情；缺少这些来源字段时返回 `SNAPSHOT_QUOTE_UNAVAILABLE`，不会把计划价或 K 线收盘价冒充行情。成功响应固定发布 `data_mode=SCHEDULED_SNAPSHOT`、`provider_class=SCHEDULED_SNAPSHOT`、`is_realtime=false` 和 `realtime_guaranteed=false`；接口名中的 `live` 不代表盘中实时。
- API JSON 使用 `Cache-Control: no-store`；静态资产由 Cloudflare 边缘提供。
- `signal_date` 是信号形成日，`generated_at` 是快照生成时间；每个市场的 `entry_trade_date` 和 `forecast_end_trade_date` 由真实交易日历生成。
- `NO_VALID_PICK` 是主动放弃，不是一笔买入预测，也不能记成亏损样本。

## 页面 Tab

1. **今日答案**：展示 global 正式动作、研究优先项、市场状态、风险和 10 交易日窗口。
2. **候选池**：展示三市场候选、Legacy/V2/双低边界、来源链、快照行情质量与单股详情。
3. **事件证据**：区分自动证据、人工待入库与模型信号，并展示扫描状态。
4. **历史检验**：区分 Legacy 历史、global 合同和 `SHADOW_RESEARCH` 结果；数据异常不会降级成 0 胜率。
5. **模型逻辑**：解释候选召回、因子、去重评分、global 门禁、版本与约两周标签。
6. **数据健康**：分别监控云端调度、快照时效、市场覆盖、事件管线、数据源完整度与结论可用性。

## 本地开发

要求 Python 3.12、Node.js 22。

```bash
git clone https://github.com/dzhdingzihang/xuangu.git
cd xuangu
python3 -m pip install -r requirements.txt
npm ci

python3 -m unittest discover -s tests -v
node --check src/index.js
node --check static/app.js
npm run check
```

生成一次新快照并更新 Shadow 账本：

```bash
python3 server.py --once --force
python3 scripts/settle_outcomes.py
python3 scripts/validate_snapshot.py data/picks/latest.json
```

启动本地 Worker：

```bash
npm run dev
```

## 部署与运维

### GitHub / Cloudflare Secrets

- `CLOUDFLARE_API_TOKEN`：Worker 部署权限。
- 定时选股不需要 OpenD、Tunnel、Render 或个人设备密钥。

### 部署 Worker

推送 `main` 会测试、构建并部署仓库已有快照；`schedule` 或 `workflow_dispatch` 会先生成新快照、更新账本再部署。

```bash
gh workflow run deploy-worker.yml --repo dzhdingzihang/xuangu --ref main
gh run list --repo dzhdingzihang/xuangu --workflow deploy-worker.yml --limit 5
```

直接部署只适合运维排障，正式发布仍应以 GitHub Actions 的完整验证链为准：

```bash
npm ci
npm run build
npx wrangler deploy
```

### 线上验收

```bash
curl -fsS https://xuangu.alixjd.com/api/status
curl -fsS https://xuangu.alixjd.com/api/latest-summary
curl -fsS 'https://xuangu.alixjd.com/api/history?view=daily&limit=5'
curl -fsSI https://xuangu.alixjd.com/
```

验收 `/api/status` 时应确认 `snapshot_generation=github-actions`、`data_mode=scheduled_snapshot`、`device_dependency=false`、`snapshot_as_of` 和 `next_refresh`。如果检查 `/api/live` 兼容路由，预期 `provider_class=SCHEDULED_SNAPSHOT` 与 `is_realtime=false`，不应期待 `REALTIME`。

`xuangu.alixjd.com` 的生产页面、API 和定时更新均不依赖 Render、OpenD 或个人电脑。

## 生产边界与下一步

当前系统已经能诚实回答“今天三市场中最值得优先研究谁”，并持续记录其约两周 Shadow 结果；它尚不能诚实承诺“哪只最可能赚最多”。要把 `RESEARCH_ONLY` 升级为生产级可执行选择，至少还需要：

- 港股和美股点时全市场证券主表与退市历史；
- 统一、可审计的点时行情、财务、事件与公司行为数据；
- 跨市场费用、滑点、汇率和不可成交处理；
- purge/embargo 的滚动样本外训练与验证；
- 概率校准、Brier/ECE、Rank IC、分位收益与漂移监控；
- 足够长的 Shadow 账本样本，并通过版本化晋级门槛。

在这些条件完成前，页面会继续保留所有 Legacy 因子、V2 去重影子评分与 A 股双低七因子，给出 `RULE_PRIORITY` 研究排序，展示快照行情质量，并让十日 `global` 严格门禁阻止假精确。定时任务、规则分、研究优先项和历史 Shadow 结果均不构成收益保证。

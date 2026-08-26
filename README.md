# XuanGu · 智能选股

[![Deploy Cloudflare Worker](https://github.com/dzhdingzihang/xuangu/actions/workflows/deploy-worker.yml/badge.svg)](https://github.com/dzhdingzihang/xuangu/actions/workflows/deploy-worker.yml)

[线上站点](https://xuangu.alixjd.com) · [服务状态](https://xuangu.alixjd.com/api/status) · [最新快照](https://xuangu.alixjd.com/api/latest) · [运行记录](https://github.com/dzhdingzihang/xuangu/actions)

XuanGu 是一个面向未来约两周（10 个交易日）的 A 股、港股、美股智能选股研究系统。它将候选召回、行情校验、因子评分、深度研究、事件证据、风险门禁和历史检验放进同一条可审计流水线，目标是回答：**今天最值得优先研究哪只股票，以及当前证据是否足以支持执行。**

## 核心能力

- **三市场动态候选池**：A 股动态召回 300 只；港股、美股在每次定时或手动快照生成任务中重新读取公开市场横截面，并分别动态召回 200 / 300 只，不再使用仓库静态名单决定入池成员。
- **A 股 300 只完整深评**：全部有效行情候选先完成基础评分和技术评分；技术 K 线完整、满足交易性过滤的候选最多 300 只继续运行 Legacy、V2、双低、Chan/CZSC、Serenity、UZI 与评审团深研，不再把第 97–300 只固定挡在深度评分之外。
- **双层生产输出**：`production_decision` V3 在共享安全门禁后分别运行“事件催化”和“质量趋势”两条规则资格通道，产出 `QUALIFIED_PICK / NO_QUALIFIED_PICK`；`global_decision` 继续负责独立的严格校准概率。规则资格分不等于上涨概率，Shadow 模型也不会因为规则轨有候选而被授权。
- **纯云端自动更新**：GitHub Actions 在工作日多时点生成并校验不可变快照，Cloudflare Worker 负责发布；每日末次检查点、规则合格批次或正式可执行批次进入长期归档，不依赖 Render、OpenD 或个人电脑常开。

页面提供今日答案、候选池、事件证据、历史检验、模型逻辑和数据健康六个 Tab。所有数字均来自已发布快照；浏览器会用快照内的冻结规则输入复算资格门禁以校验合同，但只展示服务端已经发布且校验一致的结果，不会自行补选或把计划价冒充实时行情。

> 本项目仅用于研究辅助，不构成投资建议。任何预估区间、分数和历史结果都不是收益承诺。

## 一眼看懂系统输出

页面同时呈现多层结论，它们的权限不同：

| 输出 | 回答的问题 | 是否可当成上涨概率 | 是否直接产生正式买入结论 |
|---|---|---:|---:|
| `Legacy` 市场级规则 | 当前旧因子体系在各市场更偏好谁 | 否 | 只产生市场级 `BUY_CANDIDATE / NO_TRADE` |
| `V2` 与双低影子分析 | 结构质量、去重评分和低估值风格如何 | 否 | 否 |
| `global_decision.research_priority` | 三市场全部候选中，谁最值得优先研究 | 否，`score_kind=RULE_PRIORITY` | 否，状态固定为 `RESEARCH_ONLY` |
| `production_decision.primary` | 哪只股票通过事件催化或质量趋势资格通道，以及通过哪条通道 | 否，`score_kind=RULE_QUALIFICATION_SCORE` | 产生规则合格待复核项，但不声称概率 |
| `global_decision.primary` | 哪只股票通过完整生产门禁 | 只有校准模型上线后才可解释为概率 | 是，但当前缺条件时为空 |

`RULE_PRIORITY` 和 `RULE_QUALIFICATION_SCORE` 都是确定性规则分，不是“未来 10 天上涨概率”，也不能解释为“80 分等于 80% 会涨”。规则资格轨固定发布 `probability_status=NOT_APPLICABLE`、`probability=null`、`calibrated=false`；校准概率轨未达标时继续发布 `probability_status=UNAVAILABLE`。

## 选股与评分机制

### 1. 三市场候选召回

系统先建立足够宽的召回池，再通过有效行情、全池基础评分、全池技术评分和较重的方法论深研逐层收窄。A 股页面和快照分开发布六层真实计数：`召回目标 → 实际召回 → 有效行情 → 基础评分 → 技术评分 → 深度研究`，不再把它们混为“候选数”。

- **A 股召回目标 300 只**：沪市主板 90、深市主板 75、创业板 75、科创板 60。四个板块分开过量拉取，再按板块配额和优先级去重；不会用重复代码补齐 300。
- **A 股多路召回**：事件 40、相对动量 80、可控回调 65、流动性 85、历史延续 30 是路由软目标。交易活跃度是附加命中标签；候选可同时命中多条路由。当实时宽基已满 300 时，历史候选不挤占实时席位；只在实时来源不足时按最多 5 个交易日、带衰减元数据补位。
- **A 股可交易性初筛**：排除 ST、名称含“退”、N/C 新股和无效价格；常规成交额至少 3 亿元（数据源降级补位时 1.5 亿元），换手率 0.5%–22%，涨跌幅不低于 -4.5%；主板排除≥8.8%、创业板/科创板排除≥14% 的过热追涨。PB 不是进入召回池的硬门槛。
- **A 股基础评分覆盖全部有效行情**：健康批次目标是 300/300。每只有效报价都会计算 `pre_score`，包括涨跌幅、成交额、换手率、量比、流通市值、题材和龙虎榜等；`base_scored_size` 必须严格等于 `valid_quote_size`。
- **A 股技术评分覆盖全部有效行情候选**：全部基础评分候选都会生成 `screen_score` 和 `screen_rank`。至少 32 根有效日 K 时使用现有 Chan/CZSC 技术结构；上市历史不足时仍进入评分，但技术贡献按中性值并额外扣除数据不确定性，且不能进入深研。快照同时发布 `technical_scored_size` 和 `technical_kline_complete_size`，因此“300 只都评分”和“其中多少只有完整 K 线”不会混为一谈。K 线完整安全门槛是至少 98%，即 300 只中至少 294 只；K 线末日还必须是预期交易日或紧邻的上一交易日，陈旧多日的数据不能冒充完整覆盖。
- **A 股深度研究最多 300 只**：`deep_eligible_size` 先统计“技术 K 线完整且通过 ST/退市/新股等可交易性过滤”的数量，再按全池 `screen_score` 对最多 300 只运行 Serenity、UZI、UZI Panel/评审团、完整 Legacy、V2 和交易门禁。池级健康度以 `deep_eligibility_target_count=min(300, technical_kline_complete_size)` 为分母，要求可深研覆盖至少 98%；之后仍必须对所有可深研标的发起计算，即 `deep_attempted_size=min(300, deep_eligible_size)`，且完成率不得低于 98%。例如技术 K 线完整 297 只、可深研 295 只时，可深研覆盖为 99.33%，不会因 2 只客观不可交易标的而错误降级；但漏算任一只已判定可深研的标的，或任一阶段覆盖低于 98%，仍会失败关闭并触发补跑。新快照以 `contract_version=a-share-pool-health-v2` 发布这套可审计漏斗；无版本的存量快照只做部署兼容读取，新生成的 v2 字段会被独立校验器严格重算。兼容字段 `scored_size` 仍表示完成深研、可进入决策的候选数。
- **港股动态召回目标 200 只**：主板与 GEM 普通股进入公开市场横截面，以成交额、温和动量、可控回踩、活跃度和规模质量五条互补路径召回。标准流动性门槛为当日成交额 2000 万港元；盘中延迟横截面仅在源时间同交易日且足够新鲜时，按 XHKG 当日实际交易时段进度折算，同时坚守 200 万港元成交额与 10 亿港元总市值硬底。半日市使用交易所当日时间表，不按普通 330 分钟估算。基金、ETF、债券、权证、无成交、低流动性和极端涨跌标的仍会被过滤；代码统一规范为 Yahoo 可用的 4 位 `.HK`。
- **美股动态召回目标 300 只**：从 Nasdaq、NYSE、AMEX 的普通股/存托凭证横截面按美元成交额、市值、动量、回踩与活跃度召回，排除 ETF/ETN、权证、Rights、Units、优先股、明显 SPAC、非支持交易所、低价低成交和异常波动标的；类股代码统一为 Yahoo 使用的连字符格式，例如 `BRK-B`。
- **动态召回可审计**：港美快照发布 `raw_discovery_size`、`eligible_discovery_size`、路径配额与命中数、数据源与源时间，以及包含 200/300 个唯一代码、召回分、主路径和市场指标的 `recall_manifest`。港股盘中补全还发布实际门槛、观察/源数据交易进度、源年龄、入池方式、市值币种与口径及自适应分页记录；发布前校验器会用原始字段独立重算，不信任快照自报的 `intraday_scaled`。`200/300` 是入池目标，不是港美上市证券总数；准确口径是“供应商有界普通股横截面动态扫描”，不是交易所全量点时证券主表。
- **动态源故障不静态补齐**：主源为带行情源时间的东方财富延迟普通股横截面，未通过完整性或时效门禁时改用新浪公开市场榜单；主备源都未通过门禁时最多读取最近一次健康动态池缓存，并明确标为降级、暂停推荐和触发健康补跑。旧策展名单只为历史快照兼容，不参与生产补位。
- **港美行情新鲜度**：`realtime_count` 同时要求正价格和可验证的 `source_as_of`。系统用 XHKG/XNYS 交易日历判断最近应覆盖的交易时段；常规盘中还要求时间延迟不超过 20 分钟。旧交易日、未来超过 5 分钟或无效价格都不会计入实时覆盖；Yahoo 在线日 K、运行时缓存和历史快照回退也都必须停在预期交易日或紧邻上一交易日，陈旧多日的 K 线不能计入深评。任一覆盖低于 98% 时暂停该市场推荐并补跑。
- 新港美快照标记 `universe_origin=dynamic_market_snapshot`；旧快照仍保留 `curated_static`，不会被重写成动态。动态市场池解除的是“名单静态”问题，并不补齐可靠的点时证券主表、退市历史或点时财务数据，因此系统仍不会宣传为机构级“全市场完整覆盖”。

### 2. Legacy 因子继续保留

升级没有删除原有因子。Legacy 实际决策仍保留价格、涨跌、K 线结构、量比、Chan/CZSC、UZI 和风控等原有逻辑；不同市场的公开字段可用性不同：

- 基础行情：A 股 Legacy 继续使用价格、涨跌幅、成交额、换手率、量比和流通市值；港美 Legacy 深评主要使用实时价、涨跌、日 K 和量比。港美成交额/市值先用于动态召回，再以各自市场内分位进入 V2 影子评分，不把 HKD/USD 金额冒充人民币亿元直接塞入 Legacy 总分。
- 缠论近似：MA5/MA10/MA20、二买/三买近似、箱体突破回踩、MACD 改善和过度乖离。
- CZSC 轻量映射：中枢突破/回踩、MA20/MA30 趋势、箱体位置和背驰风险。
- UZI 规则映射：多维评分、评审团近似、游资射程、买点纪律、流动性和过热/陷阱风险。
- Serenity 产业链因子：A 股继续保留原有 AI capex 上游瓶颈、客户/供给确定性等研究先验；港美动态池统一使用中性 lens，避免旧静态名单因手工主题元数据获得隐性排名优势，差异主要由本轮横截面、Yahoo K 线、Chan/CZSC 与 UZI 风控产生。
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

### 6. 10 交易日生产规则资格模型

`dual_track_candidate_qualification_v3` 与 `ten-day-audited-rule-ensemble-v3` 是当前配对的生产规则合同；前端仍兼容 V1/V2 历史快照，但不会用旧合同字段推导 V3 结论。V3 复用全市场 300 / 200 / 300 个候选的审计结果，只忽略 `TEN_DAY_MODEL_NOT_READY` 与 `TEN_DAY_PREDICTION_MISSING` 两个“概率模型暂不可用”阻断。两条资格通道都要求候选市场为 `READY`、行情和候选池完整、逐股评分与事件扫描完成、无重大负面、必需输入和风险收益合同完整；任何未知阻断都失败关闭。

| 生产资格通道 | Legacy 推荐度 A / 港 / 美 | V2 市场内排名 | 正向事件 | 数据质量 | 风险收益比 | 10 日情景区间 | 额外门槛 |
|---|---:|---:|---:|---:|---:|---|---|
| `event_catalyst` 事件催化 | ≥64 / ≥63 / ≥64 | Top 20% | 至少 1 条可审计 `event_id` | 共享数据门禁 | ≥1.20 | A/港上行 ≥5%、下行 ≤8%；美股上行 ≥6%、下行 ≤10% | 无重大负面 |
| `quality_technical` 质量趋势 | ≥66 / ≥67 / ≥68 | Top 10% | 不要求；仍必须完成扫描 | ≥95 | ≥1.50 | A/港上行 ≥6%、下行 ≤6%；美股上行 ≥6.5%、下行 ≤7.5% | 资格分 ≥72 |

质量趋势通道只豁免 `VERIFIED_POSITIVE_EVENT_MISSING`：它不能绕过事件扫描，也不能绕过重大负面、数据缺口、非正净效用或未知来源阻断。该通道没有正向事件时，页面明确显示“已完成事件扫描且未发现重大负面；本通道不要求正向催化”，不会声称候选绑定了不存在的事件。Legacy 的市场级 `BUY_CANDIDATE / NO_TRADE` 仍只保留为溯源信息，不代替逐股门禁。

两条通道沿用同一资格分权重：Legacy 30%、V2 排名强度 30%、数据质量 15%、官方事件 15% 和风险收益 10%，因此分数可比较；质量趋势无正向事件时事件贡献为 0。服务端为每只候选保存两条 `track_evaluations`，并以 `qualification_track` 明确最终通过的通道。资格分只用于合格候选之间排序，**不是上涨概率、预期收益、胜率或收益承诺**。输出固定为：

```json
{
  "action": "QUALIFIED_PICK",
  "action_basis": "dual_track_candidate_qualification_v3",
  "rule_model_id": "ten-day-audited-rule-ensemble-v3",
  "score_kind": "RULE_QUALIFICATION_SCORE",
  "probability_status": "NOT_APPLICABLE",
  "probability": null,
  "calibrated": false,
  "primary": {
    "qualification_track": "quality_technical",
    "track_evaluations": [
      {"track": "event_catalyst", "status": "FAIL"},
      {"track": "quality_technical", "status": "PASS"}
    ]
  }
}
```

每次 V3 快照还发布 `production_rule_inputs` 冻结账本：它按 `global_decision.evaluated_candidates` 的原始顺序保留规则实际读取的最小字段、来源候选存在性、数据质量与合格候选快照，并绑定 SHA-256、合同版本和行数。Python 生成器、独立快照校验器和浏览器会从该账本复算；发布的 `primary`、`qualified_candidates` 或任一合格明细只要与复算结果不完全一致，就失败关闭。Cloudflare 不在每个 HTTP 请求里重放 798/800 行决策，而是只发布由已验证完整快照派生、并与 `snapshot_key`、SHA-256 及原始字节数绑定的轻量运行索引。运行索引缺失或合同不匹配时 API 直接失败关闭，不会回退解析数 MB 的完整快照。

事件扫描默认从每市场 8 只扩大到 16 只，并按 Legacy、V2、数据质量、风险收益和市场动作预排序；Shadow 概率不参与预排序。事件源按市场隔离：一个市场的官方源故障不会抹掉另一个市场已经核验的证据；但严格 `global_decision` 仍要求三市场事件管线全部完成。浏览器只展示服务端发布且复算一致的通道、资格分和证据合同，不能自行补选、切换通道或把研究项升级为 `QUALIFIED_PICK`。

### 7. 10 交易日影子概率模型

`ten-day-technical-shadow-v1` 将原来只有 `planned` 状态的 10 日模型升级为真实运行、可审计的 Shadow 研究模型。它会为具备足够日 K 历史的候选输出“影子 P10”、预期净收益、尾部风险和风险惩罚后效用，但这些字段只用于验证与排研究优先级，不会被伪装成正式买入概率。

统计口径如下：

- 标签为信号日之后第 1 个交易日开盘买入、第 10 个交易日收盘卖出的净收益；A 股和美股往返成本假设为 `0.15%`，港股为 `0.30%`。
- 特征只读取信号日已完成的日 K，包含 1/5/10/20 日收益、均线乖离、波动率、20 日回撤、区间位置、量能比和 ATR；不使用未来 K 线或当日未完成的收盘信息。
- A 股模型历史只接受明确标记的公司行为调整日 K：东方财富 `fqt=1`，失败后回退腾讯 `qfqday`，再失败才使用 Yahoo `adjclose / raw close` 因子同比调整 OHLC；百度及其他未知复权口径不会进入模型训练。港美 Yahoo 日 K 同样必须取得 `adjclose`。缺少调整价时失败关闭，避免拆股或分红把 10 日总回报标签扭曲。
- 样本按信号日整组切分为训练、校准和测试集，并按每个样本真实的退出交易日清除跨分区标签；停牌、缺失 K 线或交易日不连续时也不能让未来收益窗口穿越边界。
- 基础分类器是日期等权、L2 正则的逻辑回归；只在校准集上做 Platt 校准，Brier、ECE、AUC、平均净收益、Top 10% 收益和 10% Expected Shortfall 只由未参与拟合/校准的测试日计算。
- 所有留出指标按信号日等权，Top 10% 也先在每个交易日内选取再跨日平均，避免某一天股票特别多就支配整段结果。
- Shadow 只有在至少 40 个独立测试日、Brier Skill ≥ 1%、AUC ≥ 0.55、ECE ≤ 0.10、逐日 Top 10% 相对全体超额 ≥ 0.5 个百分点且 Top 10% 净收益为正时，才标记 `SHADOW_READY` 并允许参与研究排序；任一项不满足即为 `SHADOW_REJECTED`，概率仍保留用于审计，但排序回退到规则分。
- 每个市场分别冻结自己的 `artifact_sha256`、`training_cutoff`、`fit_data_cutoff`、`validation_cutoff`、训练来源、特征/标签版本、分区样本数和留出指标。候选与历史账本引用市场级产物身份，不再错误引用三市场聚合哈希。

当前历史 K 线是对“今天动态召回池的成员”向前回填，不是每个历史日真实可见的点时全市场成分，因此存在选样/存活偏差。契约上固定 `training_provenance=current_universe_historical_backfill`、`production_eligible=false`、`participates_in_decision=false`和顶层 `calibrated=false`；即使某批次的留出指标不错，也不能自行解锁正式买入。

要升级为生产概率模型，至少需要持续保存每个历史决策日的点时候选池和未来不可见证据，累积足够的独立在线 Shadow 决策日，预注册晋级阈值，并在另一段未参与调参的样本上同时通过概率校准、成本后收益、尾部风险和数据完整性门槛。

### 7.1 10 交易日净超额收益排序 V2

`ten-day-excess-rank-shadow-v2` 与原概率模型并行运行，不替换 Legacy 因子，也不会自行获得买入权限。它把优化目标从“十日后是否为正”改为连续的：

```text
股票下一交易日开盘至第 10 个交易日收盘的净收益
− 同一入场/退出窗口可投资宽基的净收益
```

- 注册基准固定为 A 股 `510300`、港股 `2800.HK`、美股 `SPY`；标签缺少完全相同的基准入场或退出交易日时失败关闭。
- 每个健康批次冻结全部 A/港/美 `300 / 200 / 300` 点时候选成员、来源、召回路径、当时特征和交易窗口，旧日期不会按今天的赢家回填。
- 不再将每个历史日截成 24 只；所有有效点时成员都参与训练，并以“每个信号日总权重相同”的方式防止某天候选多就支配模型。
- 使用固定 L2 Ridge 学习连续净超额收益；验证采用按真实标签退出日 purge 的 expanding walk-forward。
- 评估直接看逐日 Spearman Rank IC、Top 10% 净超额收益、Top 1 股票净收益、Top-Bottom spread、命中率和 10% Expected Shortfall。
- 当前合同固定为 `COLLECTING`，且 `calibrated=false`、`participates_in_decision=false`、`production_eligible=false`。点时历史积累和独立晋级评审完成前，它只说明研究方向，不生成正式买入。

### 8. global 严格门禁

跨市场正式动作由 `strict_cross_market_gate_v1` 控制。以下任一类条件不满足，就输出 `NO_VALID_PICK`：

- 三市场候选覆盖、行情健康或市场状态不可比；
- 候选存在结构化 `BLOCK` 或重大负面事件；
- 自动事件管线未完成扫描，或候选缺少可用于决策的事件证据；
- 未来 10 日正收益概率没有完成样本外校准；
- 手续费、税费、点差、滑点、汇兑与尾部风险未进入统一净收益口径；
- 快照过期、关键来源不可用或其他生产合同字段不完整。

“事件扫描结果为 0 条有效事件”是合法状态，不应伪造事件；但零条有效证据不能被当作正面催化通过事件催化通道或 `global_decision` 门禁。它只可能在无重大负面的前提下满足生产 V3 的质量趋势通道事件条件。重大负面证据会直接阻断对应候选。只有全部条件通过，`global_decision.action` 才能从 `NO_VALID_PICK` 升级为 `REVIEW_EXECUTABLE_PICK`。

## 事件证据管线

事件页把三类信息严格分开：

1. 自动事件证据：由管线扫描、规范化和去重，保存原文 URL、来源、发布时间、生效时间、市场和证券映射；只有 `decision_eligible=true` 的合格记录可参与门禁。
2. 人工核验待入库：可以帮助研究，但在进入自动不可变快照前不能参与买入门禁。
3. `model_signal`：模型为何关注某只股票的解释，不是外部新闻、公告或事实。

事件管线必须发布“是否已扫描、逐市场来源状态、扫描证券、有效条数和拒绝原因”，不会把无法访问原文、缺发布时间或只有模型描述的内容包装成官方证据。默认每市场预扫 16 只（硬上限 30），用于扩大真正可能进入规则资格轨的事件覆盖，而不是把新闻数量直接当成分数。

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
- `forecast_end_session_close_at`
- `horizon_sessions=10`
- `calendar_id` / `calendar_version`

这套规则已经替代“周一到周五等于交易日”的旧逻辑。

## 三轨历史账本与规则资格留痕

历史检验使用三条物理隔离的账本，原始 `data/picks/*.json` 始终保持不可变：

- 每次 `production_decision` 都随不可变快照和历史摘要保存稳定 `qualification_id`、资格分、门禁证据与 10 日交易窗口；它与正式概率样本分母隔离。规则资格轨没有校准概率，因此不会计算 Brier/ECE，也不会把早期少量候选包装成已验证胜率。

- 正式轨写入 `data/outcomes/executable/<prediction_id>.json`，`track=EXECUTABLE_MODEL`。只有完整、已校准且通过严格门禁的 `global_decision.primary` 才能登记；所有真实发布的可执行预测按稳定 `prediction_id` 去重，`NO_VALID_PICK`、Legacy 和研究优先项不会进入正式收益分母。
- 研究轨继续写入 `data/outcomes/<prediction_id>.json`，`track=SHADOW_RESEARCH`。当 Shadow 模型通过本轮研究排序资格时，账本固化技术模型的 `prediction_id`、影子概率、净效用、尾部风险、成本、市场级产物哈希和训练截止日；未通过时不把不合格概率错记为研究样本。研究账本只在每日末次 `22:47` 主检查点登记一条 `PENDING`；`23:17` 健康补跑在入场前可更新同槽记录，已结算记录永不改写，手动运维刷新不登记研究样本。
- 完整观察轨写入 `data/outcomes/observations/obscohort_<id>.json`，`track=MODEL_OBSERVATION`。每日 `22:47` 固化原概率模型的全部 `shadow_predictions`，不以 `rank_eligible`、质量门槛或净效用正负作为准入条件；`23:17` 同槽补跑作为 revision 保留。这条轨解决“被拒绝模型永远积累不到观察样本”的问题，但明确标记 `included_in_shadow_research=false` 与 `included_in_executable_performance=false`。当前只冻结预测，结果结算仍为 `NOT_IMPLEMENTED`，页面不会把它包装成胜率。

正式轨与研究轨共同遵循：

- 入场采用下一交易日开盘，退出采用第 10 个交易日收盘；
- 合同同时固化交易所日历给出的真实开盘、收盘时刻；不会用 UTC 午夜伪装成交时间；
- 退出日尚未完整结束时不会提前结算；
- 成熟后使用同市场日线，按市场记录成本假设，结算为 `SETTLED`；
- A 股使用前复权日线，港美使用 Yahoo adjusted close 因子调整的开盘与收盘；
- 价格先按 8 位发布精度固化，再据此计算 gross、net 与正收益标签，避免低价股二次舍入造成合法样本被误删；
- 同一轨内的稳定 ID 幂等更新，身份冲突会失败关闭；三条轨使用不同目录与明确隔离字段，不会串账或覆盖；
- 已经 `SETTLED` 的记录不会因为后续行情变化而重算。

页面历史 Tab 的正式指标只读取通过完整合同校验的 `EXECUTABLE_MODEL + SETTLED` 样本。统计 cohort 固定为最新发布的 `(model_id, label_version)`，同一 `target_date` 只保留生成时间最晚的一次可执行预测，因此旧模型和同日重复运行不会把可靠样本数虚高；原始账本仍完整保留供审计。页面展示平均净收益、正收益率、Top 10% 命中率、Brier、ECE、历史已选样本 Rank IC、10% Expected Shortfall 和结算序列最大回撤；总体可靠门槛为 20 个独立决策日，Top 10% 与 Expected Shortfall 另按实际尾部样本数展示，至少 5 个尾部观测才标记达标。样本不足时明确标记“早期样本”，不可用时显示空值而不是伪造 0。这里的 Rank IC 是跨历史已选样本的排序相关性，最大回撤是按结算顺序串联的终值序列，不冒充真实持仓组合。

每条正式历史记录还会发布 `formal_sample_status` 与 `outcome_validation`。只有后端确认 `SETTLED_VALID + VALID` 的记录才能显示绿色“可执行·已结算”；仅有原始 `SETTLED`、身份冲突、算术错误或时点错误都不会进入正式指标，也不会在页面被包装成成功结算。

Shadow 的 PENDING/SETTLED、排除和冲突数量独立展示。旧的手动或本地调试 ledger 若不符合当前采样合同，会保留文件但标记为排除，不计入有效研究样本。

## 云端定时快照与数据源

生产站使用纯云端批次快照，不依赖 Render、Futu OpenD、个人电脑、Docker 或 Tunnel 常驻。GitHub Actions 在计划检查点获取公开数据、重算候选池和全部评分，验证通过后由 Cloudflare Worker 发布不可变快照。电脑关机不会影响下一次云端任务。

快照生成时使用的主要数据口径为：

- A 股宽基主召回来自新浪行情中心的沪主板/深主板/创业板/科创板分板块横截面，东方财富在某板块缺口时回退；报价使用腾讯财经与东方财富的有界重试链路，模型日 K 只接受东方财富 `fqt=1`、腾讯 `qfqday` 或 Yahoo `adjclose` 三种明确调整口径。日 K 通过 GitHub Actions Cache 跨批次复用，缺失代码才低并发补拉；盘中技术分会用本轮腾讯实时行情覆盖缓存中的当日日线，缓存只优化请求频率，不替代行情新鲜度门禁。
- A 股龙虎榜数据来自东方财富数据中心公开接口。
- 港股和美股候选边界来自本轮东方财富延迟普通股横截面；源不可用时切换新浪公开市场榜单。最终 200/300 只的价格、最近交易时段与日线由 Yahoo Finance chart 二次验证，公开源缺口或时效不合格会降级，不会回填静态策展池。
- A 股公告只接受巨潮资讯、上交所或深交所官方原文；港股只接受 HKEXnews；美股只接受 SEC EDGAR。采集批次保存 run id、逐市场扫描标的、来源请求状态和原文 URL；自报 `official` 但 URL 不在官方域名白名单的记录不能进入门禁。
- 事件、公告、新闻和人工待入库证据在快照中分类标记；只有保存来源 URL、发布/生效时间、精确证券映射并通过同批次合同校验的自动证据才能作为正向催化参与严格门禁。扫描成功但零事件是 `READY_EMPTY`：它不能替代事件催化通道或 `global_decision` 所需的官方正向证据，但在无重大负面的质量趋势通道中是可审计的合法扫描结果。
- XSHG / XHKG / XNYS 交易窗口由版本化 `exchange-calendars` 计算。

这些是公开 best-effort 数据源，没有交易所级 SLA。页面显示的价格、涨跌和 K 线都属于已发布快照，不是浏览器盘中实时行情。顶栏的 `snapshot_as_of` 表示快照生成时间，`next_refresh` 表示下一个计划检查点，不是数据供应商或 GitHub 的准点保证。

## 生产架构

静态页面、选股快照和 API 都在 Cloudflare Workers。Render、OpenD 和个人设备都不是生产依赖。

```text
GitHub Actions（定时 / 手动）
  → 安装 Python/Node 依赖并运行测试
  → 生成三市场不可变选股快照
  → 分轨登记/结算正式与 Shadow outcome，并固化完整 MODEL_OBSERVATION
  → 校验 schema 与生产合同
  → 构建 public 静态资产和历史 manifest
  → Wrangler 部署 Cloudflare Worker
  → 完整线上契约验证
  → 按归档策略将每日检查点、规则合格或正式可执行快照与 ledger 写回 main

Cloudflare Worker（请求时）
  → 完整快照以静态流式响应交给页面与审计接口
  → 状态 API 只读已验证摘要，`/api/live` 只读有界候选行情索引
  → 不在请求时获取行情，也不重算选股
```

Python 选股程序不会在 Worker 或浏览器请求中重算。页面只读 `/api/latest` 与历史快照；刷新页面不改变 Legacy、V2、双低分数、全局排序或门禁结论。`GET /api/pick?force=1` 固定返回 `409 RECOMPUTE_NOT_SUPPORTED`，需要重算时应手动触发 GitHub Actions。

## 数据更新时序与可靠性

工作日北京时间（`Asia/Shanghai`）计划：

```text
主跑：08:17 / 10:17 / 12:17 / 15:17 / 16:17 / 20:17 / 22:47
健康补跑：08:47 / 10:47 / 12:47 / 15:47 / 16:47 / 20:47 / 23:17
```

七个主跑分别覆盖盘前与隔夜收盘、A/H 早盘、亚洲午间、A 股收盘、港股收盘、美股盘前和美股开盘。`22:47` 兼顾美股夏令时与冬令时，都会落在常规交易开始之后。每个主跑后 30 分钟有一次健康补跑。每个 cron 保持独立表达式，快照同时记录主检查点和实际 cron 调用点；发布前按“调用点 + 生成时间”做单调校验，因此 GitHub 排队不会再让迟到的旧任务覆盖较新补跑。`schedule_gate.py` 只用线上完整 `/api/latest` 作为“已成功发布”证据：对应主跑已发布健康快照时跳过补跑；线上不可达、主跑缺失/失败，或行情/候选池处于可恢复降级时，补跑继续尝试。门禁会硬校验 A/港/美实际召回是否分别达到 `300 / 200 / 300`；任一市场差 1 只也不会把该快照当作健康主跑。港美还必须具备本轮动态来源、完整请求页、最低发现宽度、唯一 manifest，以及行情与完整深评至少 98%；使用上次动态池缓存也会保持降级并继续补跑。同时校验 A 股基础评分覆盖全部有效行情、技术评分至少完成 98%，以及最多 300 只深研至少完成 98%（满池即至少 294 只）。仓库里的 `latest.json` 不能单独抑制补跑，因为它不证明 Cloudflare 已经切换成功。

一次生成与 outcome 结算各最多尝试 3 次。部署前执行单元测试、JavaScript 语法检查、snapshot schema 校验和 immutable 快照一致性检查；部署后先轻量轮询 `generated_at` / `snapshot_key` 直到新版本收敛，再验证完整快照摘要、历史、不可变快照、页面合同和所有可见候选行情，避免在边缘版本传播期每轮重复执行整套探针。生成、测试或部署前校验失败时不会切换生产版。部署前还会记录当前唯一 100% 生效的 Cloudflare Worker Version 和快照摘要；若部署后完整验收失败，Workflow 会标红并自动回滚到该精确版本，再核对旧快照身份与摘要。这是自动恢复，不是零暴露发布：新版在部署后验证窗口内可能短暂在线；回滚本身若失败也会继续标红，需要人工处理。

每次定时或手动生成都会上传一个保留 30 天的 GitHub Actions 恢复包。为避免约 4–5 MiB 的全量快照在 Git 和 Worker 中无限增长，长期 Git 归档保存每日 `22:47` 检查点、产生生产规则合格候选的批次，以及确实产生正式可执行候选的批次；Worker 只携带最近 30 个决策日的完整交互快照。更早的已归档决策日继续保留轻量摘要和三轨账本，因此历史统计仍可审计，但页面不会再下载其完整候选明细。归档冲突重试采用单调合并：较旧任务可以补充自己的不可变快照，但不能覆盖较新的 `latest.json`、把 `SETTLED` 降级成 `PENDING`，或丢失观察轨 revision。被发布顺序门禁拦下的倒序任务只保留 Actions 恢复包，不能借归档提交间接发布。

浏览器每 5 分钟读取一次 `/api/status`，只有 `generated_at` 变化才重载快照和历史。它不会轮询盘中行情，也不在前端重算评分与排序。快照 `fresh` 只表示它满足发布时效合同，不等于所有公开数据源绝对完整。

GitHub scheduled workflow 不是精确计时器，可能因平台排队延后。公开数据源也没有 SLA，因此系统提供的是“目标检查点 + 健康补跑 + 可观测降级”，不是 100% 准点保证。交易所休市、任务排队或数据源失败时，`next_refresh` 也只是下一个计划检查点（含健康补跑）。

## 故障降级

| 故障 | 系统行为 |
|---|---|
| 定时生成、测试或部署前校验失败 | 不切换线上 assets；继续提供当前版本，并让 Workflow 标红 |
| 部署后完整验收失败 | 自动回滚到部署前精确 Worker Version，核对旧快照摘要；验收窗口内新版可能短暂在线 |
| 主跑快照缺失或数据源可恢复降级 | 30 分钟后健康补跑继续尝试；已有健康快照时跳过 |
| 候选池或行情覆盖不足 | 保留研究数据，但门控正式动作并发布稳定 reason codes |
| 自动事件管线完成但无正向证据 | 发布真实 0 条状态，不伪造事件；事件催化与 `global_decision` 不通过，质量趋势通道仍按更严格的非事件门槛独立评估 |
| 概率模型未授权但规则门禁通过 | 页面可显示 `QUALIFIED_PICK` 与规则资格分，同时校准轨继续保持 `NO_VALID_PICK`；不显示伪概率 |
| 正式概率模型未授权 | Shadow 有效时显示“影子 P10”与留出指标，但全局仍为 `probability_status=UNAVAILABLE`，只输出研究优先项 |
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

- `/api/status` 从与完整快照同批生成的轻量运行摘要返回快照版本、新鲜度、`snapshot_as_of`、`next_refresh`、主跑/健康补跑检查点、`data_mode=scheduled_snapshot` 和 `device_dependency=false`；它不在请求内重放全部候选计算，并公开运行索引合同及源快照摘要供部署验收。
- `/api/latest` 流式返回完整快照，避免 Worker 内再次解析与序列化；`/api/latest-summary` 返回轻量摘要。
- `/api/history` 默认 `view=daily`，按 `target_date` 合并盘中重复运行，同类保留最后一次；`view=raw` 返回不可变原始运行。`meta.performance`、`meta.executable_ledger` 和 `meta.shadow_ledger` 始终基于完整账本计算，不受页面 limit 或 daily 合并影响。
- `/api/pick?snapshot=` 是最精确的历史寻址方式；同一天可能有多次快照。
- `/api/pick?date=` 只返回该日期匹配项；非法日期 400、不存在 404，绝不静默返回 latest。
- `/api/live` 只是保留 URL 的 scheduled-snapshot 兼容接口，浏览器不调用它。它从完整快照派生、最多 90 只且编码体积不超过 512 KiB 的候选行情索引中，只返回同时保存了正价格、`source_as_of`、`fetched_at` 和成交量单位的可追溯行情；全部正式合格候选必须完整保留，超过边界时构建在部署前失败，不能静默截断。缺少来源字段时返回 `SNAPSHOT_QUOTE_UNAVAILABLE`，不会把计划价或 K 线收盘价冒充行情。成功响应固定发布 `data_mode=SCHEDULED_SNAPSHOT`、`provider_class=SCHEDULED_SNAPSHOT`、`is_realtime=false` 和 `realtime_guaranteed=false`；接口名中的 `live` 不代表盘中实时。
- API JSON 使用 `Cache-Control: no-store`；静态资产由 Cloudflare 边缘提供。
- `signal_date` 是信号形成日，`generated_at` 是快照生成时间；每个市场的 `entry_trade_date` 和 `forecast_end_trade_date` 由真实交易日历生成。
- `NO_VALID_PICK` 是主动放弃，不是一笔买入预测，也不能记成亏损样本。

## 页面 Tab

1. **今日答案**：展示 global 正式动作、研究优先项、市场状态、风险和 10 交易日窗口。
2. **候选池**：展示三市场候选、Legacy/V2/双低边界、来源链、快照行情质量与单股详情。
3. **事件证据**：区分自动证据、人工待入库与模型信号，并明确规则候选属于事件催化还是质量趋势；质量趋势无正向事件时不伪造绑定关系。
4. **历史检验**：记录每次规则资格的 `qualification_track`、资格分和事件审计说明，并与 Legacy 历史、主动放弃、正式可执行预测和 `SHADOW_RESEARCH` 隔离；数据异常不会降级成 0 胜率。
5. **模型逻辑**：解释候选召回、因子、生产 V3 双通道阈值、global 门禁、版本与约两周标签。
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

生成一次新快照并更新三轨结果账本（Shadow 研究、可执行推荐、模型观察）：

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

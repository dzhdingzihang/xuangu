# XuanGu · 智能选股

[![Deploy Cloudflare Worker](https://github.com/dzhdingzihang/xuangu/actions/workflows/deploy-worker.yml/badge.svg)](https://github.com/dzhdingzihang/xuangu/actions/workflows/deploy-worker.yml)

[线上站点](https://xuangu.alixjd.com) · [服务状态](https://xuangu.alixjd.com/api/status) · [最新快照](https://xuangu.alixjd.com/api/latest) · [运行记录](https://github.com/dzhdingzihang/xuangu/actions)

XuanGu 是一个面向未来约两周（10 个交易日）的 A 股、港股、美股智能选股研究系统。它将候选召回、行情校验、因子评分、深度研究、事件证据、风险门禁和历史检验放进同一条可审计流水线，围绕**未来 10 个交易日的扣费后收益，筛选值得优先研究、能够说明依据和入场限制的股票**。当前首页仍是可解释的规则研究排序，不是已经验证能预测“未来涨最多”的模型；能正常发布候选与已经证明选股有效，是两项不同的验收。

## 核心能力

- **两周机会与入场限制一起展示**：对本轮完整评分池独立排序，保留动量、相对强弱、加速、量价、行业和事件六项证据贡献；新 `return-opportunity-score-v3` 再扣除可复算的涨幅透支分，区分“待开盘复核”“谨慎复核”和“仅观察回调”。高波动或非科技行业本身不构成扣分理由。首页先展示机会研究榜，再展示原稳健规则候选；两者都不能把过去已涨的幅度当作未来收益预测。
- **三市场动态候选池**：A 股动态召回目标 300 只；港股、美股在每次定时或手动快照生成任务中重新读取公开市场横截面，召回目标分别为 200 / 300 只，不再使用仓库静态名单决定入池成员。召回数、有效行情数和实际评分数分别披露，目标不代表每批均完整。
- **A 股 300 只完整深评**：全部有效行情候选先完成基础评分和技术评分；技术 K 线完整、满足交易性过滤的候选最多 300 只继续运行 Legacy、V2、双低、Chan/CZSC、Serenity、UZI 与评审团深研，不再把第 97–300 只固定挡在深度评分之外。
- **双层生产输出**：当前 `production_decision` V4 在共享安全门禁后分别运行“事件催化”和“质量趋势”两条规则资格通道，产出 `QUALIFIED_PICK / NO_QUALIFIED_PICK`；`global_decision` 继续负责独立的严格校准概率。V1–V3 只用于读取历史快照。规则资格分不等于上涨概率，Shadow 模型也不会因为规则轨有候选而被授权。
- **纯云端自动更新**：GitHub Actions 原生 `schedule` 和 30 分钟 watchdog 无需个人电脑。配置仓库专用令牌后，Cloudflare Cron 提供独立主触发与 30 分钟补发；没有令牌时不宣称这条备用路径已启用。并发锁和线上 `schedule_gate` 会去重，超时及短暂服务故障有界重试；授权错误不循环重试。实际准点率以 24 小时发布台账为准，不以工作流绿色状态代替。
- **机会榜独立后续验证**：线上发布核验后，冻结当时的最多 12 个研究机会、评分版本与原始排名；第 10 个交易日后分别评价原始 Top1、Top3 和整榜。以扣费后绝对收益为主、基准超额为辅，完整榜单缺任一成员行情就不报告该批 TopN 盈亏；版本、重复入场和重叠窗口分别处理。未到期、缺行情、不足尾部样本均明确展示。
- **时效失败关闭**：已发布结论与“现在能否使用”分开。快照过期时仍保留历史规则合格记录，但运行合同切换为 `HISTORICAL_RESEARCH_ONLY`、`current_decision_allowed=false`，当前可执行候选强制为 0。

页面提供今日答案、候选池、事件证据、历史检验、模型逻辑和数据健康六个 Tab。首屏只读与快照身份绑定的轻量摘要，候选、事件和历史数据在进入对应 Tab 时才按需加载。所有数字均来自已发布快照；浏览器只展示服务端已经发布且校验一致的结果，不会自行补选或把计划价冒充实时行情。

候选列表不再重复打包全部股票的完整 K 线和研究档案；每只股票的原始因子、K 线、证券类别和召回证据分别保存为带快照身份与摘要校验的详情资产。这样可以增加研究证据而不撑爆列表发布包，原始明细不会为缩减列表而删除。

> 本项目仅用于研究辅助，不构成投资建议。任何预估区间、分数和历史结果都不是收益承诺。

### 2026-09-11 V3 发布验收记录

[云端全量生成和发布 #34592430032](https://github.com/dzhdingzihang/xuangu/actions/runs/34592430032) 成功，发布后完整合同校验通过。核验快照为 `2026-09-11_2026-09-11_191132.json`，生成于北京时间 **19:11:32**，不是以后批次的保证：

- A 股召回 / 有效行情 / 技术评分 **300 / 300 / 300**，实际深研 **295**；只有通过交易性及技术门槛的候选进入深研，没有人为保留 96 只上限。
- 港股召回 / 有效行情 / 深研 **200 / 200 / 200**；美股 **300 / 300 / 300**。两者真实源时钟新鲜计数分别为 200、300，三市场池健康。
- 新机会榜 `return-opportunity-score-v3` 评估 **800**、研究入围 **207**、发布 **12**；本批稳健规则资格为 **0**，不能把研究入围数当作可以买入的数量。
- Nasdaq 证券目录本批可用，SKUU 不在美股召回池。展示机会中 5 只有供应商证券类别证据、7 只仍标记待核验；没有把缺失证据改成已确认。
- 桌面首页与移动端历史页已检查：展示证据分、透支扣分、下一开盘复核和 Top1 / Top3 / 整榜分版本对照。未成熟结果保持空值，不显示虚构收益或胜率。
- 735 项测试通过。两次真实云端构建暴露的候选档案聚合、首页重复合同体积问题均已修复，完整详情按需读取，未提高原有发布大小限制。

这证明该版本能够生成、发布并展示可核验研究结果，不证明未来两周收益最大化，也不构成持续准点 SLA。数据仍是定时快照；未配置 `XUANGU_WORKFLOW_DISPATCH_TOKEN` 时，Cloudflare 独立补触发未启用。最新时效和数量请以线上状态为准。

### 2026-09-10 发布验收记录

以下是 **v2 的历史验收记录**，保留用于追溯，不是当前代码 v3 的生产覆盖数量。新代码不会把旧快照重写成新版本；实际在用的 `score_version`、数据时间、覆盖数量和更新健康度以线上 API 与当批验收为准。

[云端生成和发布任务 #34483954602](https://github.com/dzhdingzihang/xuangu/actions/runs/34483954602) 已通过部署后合同校验。该批快照生成于北京时间 **21:43:33**，使用 `return-opportunity-score-v2`，评估 A 股 300、港股 195、美股 300 只，研究入围 198 只，展示 12 只机会。该记录是一次验收结果，不代表以后批次的数据。

- 新鲜供应商分类覆盖 **782 / 795（98.36%）**；13 只缺失分类继续明示，不根据股票名称猜行业。
- 展示的 12 只机会均已完成本轮指定官方来源扫描；全评估池为成功 89、失败 1、未扫描 705。查询成功不等于已经排除全部负面风险。
- 机会榜经线上核验后单独登记并冻结原始排名，历史摘要在下一次构建/发布时纳入这批登记；未到第 10 个交易日不生成收益率或胜率。
- GitHub 原生调度与 watchdog 已保留；Cloudflare 独立补触发仍需配置仓库专用令牌。当前发布成功不能消除之前 24 小时的迟到或遗漏记录，也不是后续准点更新的保证。
- 港美市场本批仍有数据门禁未通过；研究机会与规则合格候选、校准概率严格隔离，不通过降低安全门槛填充正式买入答案。

## 一眼看懂系统输出

页面同时呈现多层结论，它们的权限不同：

| 输出 | 回答的问题 | 是否可当成上涨概率 | 是否直接产生正式买入结论 |
|---|---|---:|---:|
| `return_opportunities` | 当前完整评分池里，哪些两周趋势机会最值得优先研究 | 否，`score_kind=RETURN_OPPORTUNITY_RULE_SCORE` | 否，固定 `production_eligible=false` |
| `Legacy` 市场级规则 | 当前旧因子体系在各市场更偏好谁 | 否 | 只产生市场级 `BUY_CANDIDATE / NO_TRADE` |
| `V2` 与双低影子分析 | 结构质量、去重评分和低估值风格如何 | 否 | 否 |
| `global_decision.research_priority` | 三市场全部候选中，谁最值得优先研究 | 否，`score_kind=RULE_PRIORITY` | 否，状态固定为 `RESEARCH_ONLY` |
| `production_decision.primary` | 哪只股票通过事件催化或质量趋势资格通道，以及通过哪条通道 | 否，`score_kind=RULE_QUALIFICATION_SCORE` | 产生规则合格待复核项，但不声称概率 |
| `global_decision.primary` | 哪只股票通过完整生产门禁 | 只有校准模型上线后才可解释为概率 | 是，但当前缺条件时为空 |

`RULE_PRIORITY` 和 `RULE_QUALIFICATION_SCORE` 都是确定性规则分，不是“未来 10 天上涨概率”，也不能解释为“80 分等于 80% 会涨”。规则资格轨固定发布 `probability_status=NOT_APPLICABLE`、`probability=null`、`calibrated=false`；校准概率轨未达标时继续发布 `probability_status=UNAVAILABLE`。

候选资源以 `candidate-role-v1` 把权限拆成三个独立命名空间，不再用一个“首选”混合不同口径：

- `decision_roles.production=PRIMARY` 是跨市场规则主候选，兼容字段为 `decision_role=production_primary`。
- `decision_roles.production=QUALIFIED` 是通过同一 V4 门禁的其他规则合格候选，兼容字段为 `decision_role=production_qualified`。
- `decision_roles.legacy=PRIMARY` 只是单个市场 Legacy 规则的首选，兼容字段为 `decision_role=legacy_market_primary`；它不等于规则主候选，也不能取得 production 或校准概率权限。`decision_roles.research=PRIORITY` 同样只表示研究排序。

同一只股票可同时拥有 production、legacy 和 research 角色；展示层的短标签只是兼容映射，服务端发布的 `decision_roles`、`production_rank` 和 `legacy_rank` 才是可审计依据。

## 选股与评分机制

### 两周收益机会研究榜与入场复核（v3）

原 V4 稳健规则更看重证据完整性和下行情景约束，容易让低波动银行股通过，而把趋势较强但波动较大的股票挡住。因此新增独立的 `return-opportunities-v1`，不篡改旧规则、不回填历史推荐，也不把未验证的 Shadow 模型升级为正式预测。

| 组成 | 权重 | 依据 |
|---|---:|---|
| 多周期动量 | 30% | 已发生的真实 5/10/20 日涨幅，同时考虑风险标准化趋势 |
| 同市场相对强弱 | 20% | 与本轮同市场评分池比较，而不是比较 A/HK/US 的绝对涨幅 |
| 动量加速 | 15% | 近期趋势相对前段是否增强 |
| 趋势和量价结构 | 20% | 均线、价格位置和成交量确认，防止只追单日脉冲 |
| 行业共振 | 10% | 有标签且有足够同行样本时，计算本轮真实表现；不足则明确中性 |
| 去重事件催化 | 5% | 核验后的材料性事件；日常回购执行披露不作为新增利好反复加分 |

上述六项贡献之和是 `evidence_score`，并未因引入入场复核而删除旧因子或重新训练权重。v3 的展示排序分为：

```text
opportunity_score = max(0, evidence_score − entry_assessment.penalty_points)
```

透支评估只读取同批公开的过去 5 日涨幅 `r5`、过去 10 日涨幅 `r10` 和距 MA20 的百分比 `d`，百分数使用数值单位（例如 20 表示 20%）：

```text
基础扣分 p = 0.5 × max(0, r5 − 12)
           + 0.35 × max(0, r10 − 20)
           + 0.5 × max(0, d − 12)
```

| 入场状态 | 判定条件（任一满足；高透支优先） | 扣分与准确含义 |
|---|---|---|
| `CONDITIONAL_REVIEW` | r5 < 12%、r10 < 20%、d < 12% | 扣 0 分；只表示未触发这组透支规则，仍须开盘复核 |
| `CAUTION` | r5 ≥ 12%、r10 ≥ 20% 或 d ≥ 12%，但未达到高透支 | 将 p 限制在 6–16 分；谨慎复核，不表示安全买点 |
| `WAIT_FOR_PULLBACK` | r5 ≥ 20%、r10 ≥ 30% 或 d ≥ 20% | 将 p 限制在 18–24 分；仅观察回调，等待新数据重新评估 |

扣分保留两位小数。比如过去 5 日 +31.163%、10 日 +41.235%、距 MA20 +32.998% 的已发生行情，会被标为高透支并扣 24 分；这些历史涨幅绝不是接下来两周的预期收益。高波动本身不增加这项扣分，材料性利好也不能自动抹去已经支付的涨幅。阈值是公开的研究先验，尚不是经过样本外优化的收益系数。

`entry_policy.timing=NEXT_SESSION_OPEN_REVIEW` 明确指向**确认发布之后下一次可交易开盘的复核**，不是当前价买入或下一开盘自动下单。必须重新核查可成交报价、证券类别、停牌/涨跌停等交易状态、跳空与点差、流动性和重大消息；`entry_assessment.execution_ready=false`、`automatic_execution=false`。历史观察使用独立账本冻结的开盘窗口与费用假设，不等于真实账户成交。

- 排名覆盖本轮完整技术/深度评分候选，不只复排旧首页的短名单。默认展示最多 12 个研究机会，并在有足够替代项时限制行业集中；不是强行填满 12 个。
- 研究资格要求原始 `evidence_score ≥ 60` 及数据/交易性门禁通过；v3 扣分后的 `opportunity_score` 可以小于 60，不代表降低旧生产规则的合格阈值。强势但已透支的股票可保留为观察对象，不能被当作直接买入答案。公开合同独立重算因子贡献、扣分和状态，不能只修改显示分数。
- 当前代码评分版本为 `return-opportunity-score-v3`，沿用 `return-opportunities-v1` 数据合同，继续读取历史 score-v1/v2，但不对其补扣分或重排。行业分类读取东方财富批量 `f100` 字段：A/HK 为供应商行业，美股为较宽的板块，不能把两者混成同一种细行业。每条分类保留来源、供应商证券身份、查询地址、采集时间与分类层级；7 天有效缓存、6 小时失败冷却，并发和请求数有上限。旧分类、主题近似或来源缺失仍可展示，但不能据此获得行业强弱加分；同行不足 3 只时同样中性。不会根据名称猜科技股，也不给“科技”固定加分。
- 每只机会都有 `event_coverage`：`SUCCESS` 仅表示本轮所列官方来源查询成功，`ERROR` 是查询失败，`NOT_SCANNED` 是未完成扫描。三者都不能直接等同于“没有负面风险”；重大负面一经核验仍排除。
- 无效或陈旧行情、K 线不足、不可交易、已核验重大负面、趋势破坏及极端追涨继续排除。风险预算只是一致化研究示例，高波动通常对应更低示例权重，不是个性化仓位建议或保证止损。
- `scenario_range` 是历史波动推导的情景范围，不按区间上界给股票排序。`expected_net_return=null`、`probability=null`、`calibrated=false` 始终保留，不能把 80 分解释为 80% 胜率或 80% 收益。
- 榜单绑定云端快照和行情来源时间；快照过期后隐藏当前榜单，等待 GitHub 云端刷新。GitHub 定时检查点是批次更新，不是交易所逐笔实时行情。
- 真正的“未来 10 日扣费后收益最大化”模型仍须积累当时可得的完整样本、走步样本外检验及成本/尾部风险验证；此研究榜不代替那项验证。

### 1. 三市场候选召回

系统先建立足够宽的召回池，再通过有效行情、全池基础评分、全池技术评分和较重的方法论深研逐层收窄。A 股页面和快照分开发布六层真实计数：`召回目标 → 实际召回 → 有效行情 → 基础评分 → 技术评分 → 深度研究`，不再把它们混为“候选数”。

- **A 股召回目标 300 只**：沪市主板 90、深市主板 75、创业板 75、科创板 60。四个板块分开过量拉取，再按板块配额和优先级去重；不会用重复代码补齐 300。
- **A 股多路召回**：事件 40、相对动量 80、可控回调 65、流动性 85、历史延续 30 是路由软目标。交易活跃度是附加命中标签；候选可同时命中多条路由。当本轮抓取宽基已满 300 时，历史候选不挤占本轮席位；只在本轮来源不足时按最多 5 个交易日、带衰减元数据补位。
- **A 股可交易性初筛**：排除 ST、名称含“退”、N/C 新股和无效价格；常规成交额至少 3 亿元（数据源降级补位时 1.5 亿元），换手率 0.5%–22%，涨跌幅不低于 -4.5%；主板排除≥8.8%、创业板/科创板排除≥14% 的过热追涨。PB 不是进入召回池的硬门槛。
- **A 股基础评分覆盖全部有效行情**：健康批次目标是 300/300。每只有效报价都会计算 `pre_score`，包括涨跌幅、成交额、换手率、量比、流通市值、题材和龙虎榜等；`base_scored_size` 必须严格等于 `valid_quote_size`。
- **A 股技术评分覆盖全部有效行情候选**：全部基础评分候选都会生成 `screen_score` 和 `screen_rank`。至少 32 根有效日 K 时使用现有 Chan/CZSC 技术结构；上市历史不足时仍进入评分，但技术贡献按中性值并额外扣除数据不确定性，且不能进入深研。快照同时发布 `technical_scored_size` 和 `technical_kline_complete_size`，因此“300 只都评分”和“其中多少只有完整 K 线”不会混为一谈。K 线完整安全门槛是至少 98%，即 300 只中至少 294 只；K 线末日还必须是预期交易日或紧邻的上一交易日，陈旧多日的数据不能冒充完整覆盖。
- **A 股深度研究最多 300 只**：`deep_eligible_size` 先统计“技术 K 线完整且通过 ST/退市/新股等可交易性过滤”的数量，再按全池 `screen_score` 对最多 300 只运行 Serenity、UZI、UZI Panel/评审团、完整 Legacy、V2 和交易门禁。池级健康度以 `deep_eligibility_target_count=min(300, technical_kline_complete_size)` 为分母，要求可深研覆盖至少 98%；之后仍必须对所有可深研标的发起计算，即 `deep_attempted_size=min(300, deep_eligible_size)`，且完成率不得低于 98%。例如技术 K 线完整 297 只、可深研 295 只时，可深研覆盖为 99.33%，不会因 2 只客观不可交易标的而错误降级；但漏算任一只已判定可深研的标的，或任一阶段覆盖低于 98%，仍会失败关闭并触发补跑。新快照以 `contract_version=a-share-pool-health-v2` 发布这套可审计漏斗；无版本的存量快照只做部署兼容读取，新生成的 v2 字段会被独立校验器严格重算。兼容字段 `scored_size` 仍表示完成深研、可进入决策的候选数。
- **港股动态召回目标 200 只**：主板与 GEM 普通股进入公开市场横截面，以成交额、温和动量、可控回踩、活跃度和规模质量五条互补路径召回。标准流动性门槛为当日成交额 2000 万港元；盘中延迟横截面仅在源时间同交易日且足够新鲜时，按 XHKG 当日实际交易时段进度折算，同时坚守 200 万港元成交额与 10 亿港元总市值硬底。半日市使用交易所当日时间表，不按普通 330 分钟估算。基金、ETF、债券、权证、无成交、低流动性和极端涨跌标的仍会被过滤；代码统一规范为 Yahoo 可用的 4 位 `.HK`。
- **美股动态召回目标 300 只**：从 Nasdaq、NYSE、AMEX 的普通股/存托凭证横截面按美元成交额、市值、动量、回踩与活跃度召回，排除 ETF/ETN、权证、Rights、Units、优先股、明显 SPAC、非支持交易所、低价低成交和异常波动标的；类股代码统一为 Yahoo 使用的连字符格式，例如 `BRK-B`。
- **证券类别不能靠“没写 ETF”确认**：`security-identity-v1` 合并 Nasdaq 证券目录的 ETF/测试标记与证券名称、Yahoo `instrumentType` 等绑定代码的来源证据，在入池、评分和最终机会校验处再次检查。已识别的 ETF/ETN、杠杆/反向产品、权证等标为 `EXCLUDED`；例如 `GRANITESHARES 2X LONG SK HYNIX` 即使中文简称不像基金也不能入选股票机会。正向类型证据必须带合法来源时间，相对观测时点超过 7 天或未来超过 5 分钟不获得 `verified`；最终机会校验以冻结的 `feature_cutoff_at` 为参考。缺失类型保持 `UNVERIFIED` 并提示复核，不冒充已核验普通股；已识别的负向产品证据不会被“未知”声明覆盖。供应商 `EQUITY` 分类也不等于完整交易所证券主表。
- **上市历史与补源分别处理**：供应商明确 `f26` 上市日期不足 32 个真实交易日的标的，在港美动态入池前排除；日期未知保留 `UNKNOWN`，后续仍必须取得足够有效日 K，不能伪造 32 根历史。缺 K 或陈旧 K 的逐股原因通过 `quote_health.input_failures/missing_input_symbols` 披露，并保留本轮取得的原始报价供诊断，不能把“有报价”算作“能深评”。
- **动态召回可审计**：港美快照发布 `raw_discovery_size`、`eligible_discovery_size`、路径配额与命中数、数据源与源时间，以及包含 200/300 个唯一代码、召回分、主路径和市场指标的 `recall_manifest`。港股盘中补全还发布实际门槛、观察/源数据交易进度、源年龄、入池方式、市值币种与口径及自适应分页记录；发布前校验器会用原始字段独立重算，不信任快照自报的 `intraday_scaled`。`200/300` 是入池目标，不是港美上市证券总数；准确口径是“供应商有界普通股横截面动态扫描”，不是交易所全量点时证券主表。
- **动态源故障不静态补齐**：主源为带行情源时间的东方财富延迟普通股横截面，未通过完整性或时效门禁时改用新浪公开市场榜单；主备源都未通过门禁时最多读取最近一次健康动态池缓存，并明确标为降级、暂停推荐和触发健康补跑。旧策展名单只为历史快照兼容，不参与生产补位。
- **美股扩池必须同时扩充新鲜来源**：东方财富五条路由各自分页，失败的基础页只单独补试一轮；新鲜有效成员不足时，有界扩展成交额页至第 8 页。发布实际请求/完成/失败页、页范围与源时间覆盖，`discovery_scan_scope=bounded_route_pages`、`discovery_full_exchange_scan=false`；不能因为凑到 300 个代码就宣布分页完整。合并来源时一并选择同一次观测的价格、涨跌、成交额和时间，不把新时间戳嫁接到旧价格；没有来源时钟的新浪记录不能伪造时钟来通过新鲜度门禁。
- **港美行情新鲜度**：`realtime_count` 同时要求正价格和可验证的 `source_as_of`。系统用 XHKG/XNYS 交易日历判断最近应覆盖的交易时段；常规盘中还要求时间延迟不超过 20 分钟。旧交易日、未来超过 5 分钟或无效价格都不会计入实时覆盖；Yahoo 在线日 K、运行时缓存和历史快照回退也都必须停在预期交易日或紧邻上一交易日，陈旧多日的 K 线不能计入深评。任一覆盖低于 98% 时暂停该市场推荐并补跑。
- 新港美快照标记 `universe_origin=dynamic_market_snapshot`；旧快照仍保留 `curated_static`，不会被重写成动态。动态市场池解除的是“名单静态”问题，并不补齐可靠的点时证券主表、退市历史或点时财务数据，因此系统仍不会宣传为机构级“全市场完整覆盖”。

### 2. Legacy 因子继续保留

升级没有删除原有因子。Legacy 实际决策仍保留价格、涨跌、K 线结构、量比、Chan/CZSC、UZI 和风控等原有逻辑；不同市场的公开字段可用性不同：

- 基础行情：A 股 Legacy 继续使用已发布快照的价格、涨跌幅、成交额、换手率、量比和流通市值；港美 Legacy 深评主要使用同批快照价、涨跌、日 K 和量比。港美成交额/市值先用于动态召回，再以各自市场内分位进入 V2 影子评分，不把 HKD/USD 金额冒充人民币亿元直接塞入 Legacy 总分。
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

`dual_track_candidate_qualification_v4` 与 `ten-day-audited-rule-ensemble-v4` 是当前配对的生产规则合同；前端仍兼容 V1–V3 历史快照，但不会用旧合同字段推导 V4 结论。V4 复用 A / 港 / 美有界召回池 300 / 200 / 300 个目标候选的审计结果，只忽略 `TEN_DAY_MODEL_NOT_READY` 与 `TEN_DAY_PREDICTION_MISSING` 两个“概率模型暂不可用”阻断。两条资格通道都要求候选市场为 `READY`、行情和候选池完整、全池逐股结构风险筛查通过、无已核验重大负面、必需输入和风险收益合同完整；任何未知安全阻断都失败关闭。网络开销较高的官方公告正向催化深扫是另一层独立 enrichment，不再错误地把未进入 Top N 深扫的优质候选挡在质量趋势通道之外。

| 生产资格通道 | Legacy 推荐度 A / 港 / 美 | V2 市场内排名 | 正向事件 | 数据质量 | 风险收益比 | 10 日情景区间 | 额外门槛 |
|---|---:|---:|---:|---:|---:|---|---|
| `event_catalyst` 事件催化 | ≥64 / ≥63 / ≥64 | Top 20% | 至少 1 条可审计 `event_id` | 共享数据门禁 | ≥1.20 | A/港上行 ≥5%、下行 ≤8%；美股上行 ≥6%、下行 ≤10% | 无重大负面 |
| `quality_technical` 质量趋势 | ≥64 / ≥67 / ≥67 | Top 10% | 不要求，也不要求入选正向事件 Top N 深扫 | ≥95 | ≥1.50 | A/港上行 ≥6%、下行 ≤6%；美股上行 ≥6.5%、下行 ≤7.5% | 资格分 ≥72；共享安全门禁必须通过 |

质量趋势通道只豁免正向事件 enrichment 的两个可用性代码：`EVENT_CANDIDATE_NOT_SCANNED` 与 `VERIFIED_POSITIVE_EVENT_MISSING`。它不能绕过候选池/行情覆盖、可交易性、必需输入、数据质量、重大负面、风险收益或任何其他未知来源阻断。页面会把“全池结构风险筛查”和“重点候选官方正向事件深扫”分开显示；未进入深扫只代表未被选入本轮正向催化 enrichment，不能被描述成“官方确认无负面”。Legacy 的市场级 `BUY_CANDIDATE / NO_TRADE` 仍只保留为溯源信息，不代替逐股门禁。

A / 港 / 美的 Legacy 分布刻度并不相同，质量通道因此使用 64 / 67 / 67 的市场边界；这组边界经过全池可达性检查，避免阈值高于某市场评分实际上限而形成“永远无候选”的死门。Top 10%、数据质量、风险收益和总资格分仍保持更严格，降低 Legacy 边界不会单独让股票通过。

两条通道沿用同一资格分权重：Legacy 30%、V2 排名强度 30%、数据质量 15%、官方事件 15% 和风险收益 10%，因此分数可比较；质量趋势无正向事件时事件贡献为 0。服务端为每只候选保存两条 `track_evaluations`，并以 `qualification_track` 明确最终通过的通道。资格分只用于合格候选之间排序，**不是上涨概率、预期收益、胜率或收益承诺**。输出固定为：

```json
{
  "action": "QUALIFIED_PICK",
  "action_basis": "dual_track_candidate_qualification_v4",
  "rule_model_id": "ten-day-audited-rule-ensemble-v4",
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

每次 V4 快照还发布 `production_rule_inputs` 冻结账本：它按 `global_decision.evaluated_candidates` 的原始顺序保留规则实际读取的最小字段、来源候选存在性、数据质量与合格候选快照，并绑定 SHA-256、合同版本和行数。Python 生成器、独立快照校验器和浏览器会从该账本复算；发布的 `primary`、`qualified_candidates` 或任一合格明细只要与复算结果不完全一致，就失败关闭。Cloudflare 不在每个 HTTP 请求里重放约 800 行决策，而是只发布由已验证完整快照派生、并与 `snapshot_key`、SHA-256 及原始字节数绑定的轻量运行索引。运行索引缺失或合同不匹配时 API 直接失败关闭，不会回退解析数 MB 的完整快照。

官方事件扫描默认每市场最多 30 只：先做初步机会排序，以将展示的前列股票及最多 24 只/市场的扩展优先序列作为重点，再保留少量原规则名额；不使用情景区间上沿或 Shadow 概率。请求名单、逐股成功和失败名单分别发布，单只证券失败不会抹掉同市场其他证券的成功证据。日常回购执行公告保留原文但默认中性；只有文档匹配、已验证的重要性证据才能按明确回购计划归并正向资格，不用披露数量冒充新增催化。快照以 `two-tier-event-coverage-v1` 明确发布两层口径：`risk_screen.scope=full_candidate_pool` 对全部候选执行结构化交易性、必需输入和已核验重大负面门禁；`positive_event_enrichment.scope=bounded_priority_sample` 才表示进入官方公告扫描的重点样本。扫描是有界官方披露/标题检索，并非对全文、媒体消息和全部历史事件的无遗漏排查。严格 `global_decision` 仍要求三市场事件管线全部完成；研究候选可在明确标示未扫描/失败风险时保留，不能因此获得正式交易资格。

每个规则合格候选还携带服务端冻结的 `ten-day-trade-plan-v2` 复核计划：快照参考价及来源时间、允许复核的参考入场区间、失效价、目标参考、最晚复核交易日和单票 10% 策略安全上限。其 `scenario_range` 必须无损绑定同一候选的 `horizon-range-v1`，核心字段包含 10 交易日上下界、`method_id=realized-vol-drift-shadow-v1`、`calibrated=false` 和源观测数；K 线日期完整时还发布真实的来源窗口起止日，日期证据缺失时省略而不猜测。核心来源字段缺失、窗口只出现单边或任一字段被篡改都会失败关闭。`horizon-range-v1`、失效价和目标价都是未校准的确定性情景，**不是概率置信区间、预期收益或胜率承诺**。计划状态固定为 `REVIEW_REQUIRED`，`is_personalized_advice=false`；这是统一执行纪律，不是实时委托或个性化仓位建议。浏览器只读取该合同，缺值显示未知，不根据当前网页时间自行推算价格。`ten-day-trade-plan-v1` 只作为历史快照兼容合同读取。

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
- 不再将每个历史日截成 24 只；所有有效点时成员都参与训练，并以“信号日—市场单元等权”的方式防止某天或某个市场的候选数量支配模型。
- 使用固定 L2 Ridge 学习连续净超额收益；验证采用按真实标签退出日 purge 的 expanding walk-forward。
- 评估直接看逐日 Spearman Rank IC、Top 10% 净超额收益、Top 1 股票净收益、Top-Bottom spread、命中率和 10% Expected Shortfall。
- 当前净超额排序 V2 为 `COLLECTING`。每个市场至少需要 100 个训练信号日、20 个最终未触碰 holdout 日，并在按真实退出日 purge 后仍满足 walk-forward 折要求；重叠窗口可能让实际所需历史更多。即使未来进入 `SHADOW_READY`，也固定 `calibrated=false`、`probability=null`、`participates_in_decision=false`、`production_eligible=false`，不会自行给当前候选授权或输出“上涨概率”。
- `sample_count` 和 `signal_date_count` 统计的是能够完成真实标签连接的**成熟样本**。`POINT_IN_TIME_LEDGER_EMPTY` 表示当前没有可用成熟训练样本，不足以据此断言原始观察账本没有登记；未成熟、缺行情与样本链不完整应查看对应诊断。没有成熟样本时不会拿新规则分伪装已训练的净收益预测。这个模型的目标是相对市场基准的净超额收益，与首页机会跟踪优先展示的绝对净收益也不是同一个指标。
- `SHADOW_READY` 只表示已生成足够的 walk-forward / final holdout 研究结果，不等于“可晋级”。`promotion_gate_passed=true` 还要求样本链完整绑定不可变的 `point_in_time_universe` 批次，且只使用完整成熟的“`signal_date × market`”单元；缺 outcome batch、无效 revision、源快照缺失/未绑定、rank label 缺失、特征无效、数据缺失结算或任一数据不完整的日期×市场单元都会让完整性门禁失败。最终未触碰 holdout 还必须同时满足 Top 1 平均净超额收益 `> 0`、逐日 Spearman IC `> 0`、验证覆盖率 `≥ 70%`，以及 Top 10% 股票净收益的 10% Expected Shortfall `≥ -15%`。即使全部通过，`promotion_authorized` 仍固定为 `false`，只能由独立人工治理流程另行授权。

每个新快照还冻结 `feature_cutoff_at`：所有特征的 `observed_at` 必须不晚于 cutoff，且 cutoff 必须早于对应市场下一交易日开盘。旧快照不会事后回填为点时训练样本；缺少合法 cutoff、成员来源或源快照摘要时，Rank 样本链失败关闭。

### 7.2 GitHub 云端历史回放

仓库额外维护 `ARCHIVED_SHORTLIST_REPLAY` 研究轨，用过去真正保存下来的决策快照复盘“当时已进入首选或观察名单的股票”。它由 `.github/workflows/historical-replay.yml` 在 GitHub-hosted runner 上运行，读取不可变 `data/picks/*.json`，按每个 `entry_trade_date × market` 选择生成时间最晚且确有短名单的合法快照，再用复权日 K 结算。这样，同一入场日盘前的多次刷新只算一次；开盘后生成、自然顺延到下一个入场日的快照仍保留为独立 cohort：

```text
快照生成并冻结候选
  → 快照发布后的第一个对应市场 regular open 入场
  → 从入场日计第 10 个真实交易日 close 退出
  → 扣市场成本
  → 减去同窗口注册宽基净收益
```

注册基准继续使用 A 股 `510300`、港股 `2800.HK`、美股 `SPY`。行情必须明确为公司行动调整序列；缺开盘、退出收盘、基准同窗口或调整口径时保持 `PENDING_DATA`，不能用相邻日期或原始未复权价格补齐。已经 `SETTLED` 的回放行保持不可变，供应商之后修订数据也不能静默重写旧结果。

这条轨道比“拿今天的股票名单向前套历史 K 线”更接近真实复盘，因为候选和因子确实来自当时保存的快照；但它仍然只覆盖**当时归档的短名单**，不是当日全市场真实 `300 / 200 / 300` 召回池，也不补写当时没有保存的退市证券、停牌状态、公告修订或财务发布时间。因此公开合同固定为：

```text
evidence_class=RETROSPECTIVE
universe_scope=ARCHIVED_SHORTLIST_ONLY
full_point_in_time_universe=false
calibrated=false
participates_in_decision=false
production_eligible=false
promotion_eligible=false
authorizes_production=false
```

它保留旧评分、置信度、推荐度、通道和排序及其真实 10 交易日结果，为后续按因子分层诊断提供可审计底表；当前页面发布的是短名单整体结果，不把它伪装成单因子因果效果。它不计入前瞻观察天数，不与 `MODEL_OBSERVATION`、`SHADOW_RESEARCH`、`EXECUTABLE_MODEL` 或规则资格收益混合，也不能因为回放指标好看就自动生成正式候选。生产晋级仍只接受未来真实冻结、等待成熟且通过独立留出与治理门槛的证据。

### 8. global 严格门禁

跨市场正式动作由 `strict_cross_market_gate_v1` 控制。以下任一类条件不满足，就输出 `NO_VALID_PICK`：

- 三市场候选覆盖、行情健康或市场状态不可比；
- 候选存在结构化 `BLOCK` 或重大负面事件；
- 自动事件管线未完成扫描，或候选缺少可用于决策的事件证据；
- 未来 10 日正收益概率没有完成样本外校准；
- 手续费、税费、点差、滑点、汇兑与尾部风险未进入统一净收益口径；
- 快照过期、关键来源不可用或其他生产合同字段不完整。

“事件扫描结果为 0 条有效事件”是合法状态，不应伪造事件；但零条有效证据不能被当作正面催化通过事件催化通道或 `global_decision` 门禁。V4 的质量趋势通道不要求进入有界正向事件 enrichment，但仍必须通过共享结构风险、数据质量、行情、可交易性和所有已知重大负面门禁。只有校准概率、成本和完整严格门禁全部通过，`global_decision.action` 才能从 `NO_VALID_PICK` 升级为 `REVIEW_EXECUTABLE_PICK`。

## 事件证据管线

事件页把三类信息严格分开：

1. 自动事件证据：由管线扫描、规范化和去重，保存原文 URL、来源、发布时间、生效时间、市场和证券映射；只有 `decision_eligible=true` 的合格记录可参与门禁。
2. 人工核验待入库：可以帮助研究，但在进入自动不可变快照前不能参与买入门禁。
3. `model_signal`：模型为何关注某只股票的解释，不是外部新闻、公告或事实。

事件管线必须发布“是否已扫描、逐市场/逐股来源状态、成功和失败证券、有效条数和拒绝原因”，不会把无法访问原文、缺发布时间或只有模型描述的内容包装成官方证据。默认每市场扫描上限 30，以初步机会榜优先；它补强重点候选的官方披露证据，而不是把新闻数量直接当成分数，也不是对已扫或未扫证券宣称“官方公告无风险”。

`event-list-v2` / `ui-events-v2` 使决策证据在首屏和分页 API 中可发现：

- 每行都有布尔值 `decision_bound`，发布元数据同时列出 `decision_bound_event_ids`、`production_bound_event_ids` 及对应计数。默认顺序是“已绑定决策的证据优先，再按发布时间倒序”，因此首页不会被更新但未绑定的事件挤掉。
- `/api/events` 支持 `scope=all|decision_bound`、`decision_bound`、`decision_eligible`、`event_id`（可重复或逗号分隔）、`market`、`symbol`、`event_type`、`direction=positive|neutral|negative` 和 `q`。所有筛选先于分页执行；非法组合返回 `400 INVALID_EVENT_FILTER`。
- 前端按 `event_id` 去重合并首屏 bootstrap 中的不可变决策证据和按需加载的事件页，不会因为首个懒加载页缺少某个 ID 就把已绑定证据清零。候选审计使用“已解析 X / Y 个绑定 `event_id`”的口径；例如“已解析 7 / 7”只表示 7 个绑定 ID 均已载入，不代表所有事件源只有 7 条或全部市场已完整扫描。

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

## 六类隔离历史证据与机会榜留痕

历史检验使用六类物理隔离的证据，原始 `data/picks/*.json` 始终保持不可变，任何一类都不能借另一类的结果扩大自己的样本分母：

- **机会榜后续表现**：`track=RETURN_OPPORTUNITY`，独立写入 `data/outcomes/opportunity-settlements`。只在完整线上契约核验成功后，冻结实际发布的 `public/data/picks/latest.json` 中的机会和来源摘要；以核验时间作为保守的“已确认可见”时点，再取严格晚于该时点及特征截止的首个交易所开盘。原始排名、分数、版本、成本、日历与基准不能被后续刷新改写。默认不把当前评分倒套历史，也不自动导入缺乏发布时点证据的旧快照。

- **规则资格结果**：每次 V4 `production_decision` 保存稳定 `qualification_id`、通道、资格分、门禁证据、严格交易复核计划和 10 日窗口。`data/outcomes/rule-settlements/<snapshot>.json` 对当批全部合格候选（含是否 primary）按“下一交易日开盘到第 10 个交易日收盘”登记并结算，同时记录市场注册基准、费用后绝对/超额收益和最大不利波动。它只评估规则，不计算 Brier/ECE，不进入校准概率样本，也不能授权生产。
- **正式可执行轨**：写入 `data/outcomes/executable/<prediction_id>.json`，`track=EXECUTABLE_MODEL`。只有完整、已校准且通过严格门禁的 `global_decision.primary` 才能登记；`NO_VALID_PICK`、Legacy、V4 规则资格和研究优先项都不会进入正式收益分母。
- **Shadow 研究轨**：继续写入 `data/outcomes/<prediction_id>.json`，`track=SHADOW_RESEARCH`。只有符合该版本研究采样合同的预测才登记影子概率、净效用、尾部风险、成本和模型产物身份；不合格概率不会被错记成研究样本。
- **完整观察轨**：写入 `data/outcomes/observations/obscohort_<id>.json`，`track=MODEL_OBSERVATION`，并在 `observation-settlements` 中独立结算。cohort/revision 冻结源快照文件名、SHA-256、字节数、生成时点和 `feature_cutoff_at`，再连接源快照里的 `point_in_time_universe` 读取当时特征；它用于诊断原概率模型及净超额排序 V2，明确 `included_in_shadow_research=false`、`included_in_executable_performance=false`、`authorizes_production=false`。
- **归档短名单回放轨**：写入 `data/backtests/archived-shortlist-replay-v1.json`，`track=ARCHIVED_SHORTLIST_REPLAY`。它只复盘历史快照当时实际保存的首选/观察名单与因子，使用真实交易所日历、调整行情、成本和注册基准生成回顾性结果；明确 `universe_scope=ARCHIVED_SHORTLIST_ONLY`，不冒充完整点时候选池，不进入任何生产晋级分母。

各类证据按各自合同结算；新增机会轨的更严格发布时点要求不会反向改写旧轨：

- 入场采用下一交易日开盘，退出采用第 10 个交易日收盘；
- 合同同时固化交易所日历给出的真实开盘、收盘时刻；不会用 UTC 午夜伪装成交时间；
- 退出日尚未完整结束时不会提前结算；
- 成熟后使用同市场日线，按市场记录成本假设，结算为 `SETTLED`；
- A 股使用前复权日线，港美使用 Yahoo adjusted close 因子调整的开盘与收盘；
- 价格先按 8 位发布精度固化，再据此计算 gross、net 与正收益标签，避免低价股二次舍入造成合法样本被误删；
- 同一轨内的稳定 ID 幂等更新，身份冲突会失败关闭；各类证据使用不同目录与明确隔离字段，不会串账或覆盖；
- 已经 `SETTLED` 的记录不会因为后续行情变化而重算。

机会轨每次刷新先结算已登记记录，发布成功后再登记本批。登记采用轻量、可独立结算的冻结记录，即使本次完整快照未进入长期 Git 归档，也不会丢失研究机会。历史发布可能比新登记滞后一批；周末也由独立结算工作流继续处理成熟窗口。`PENDING_MATURITY` 不填收益，`PENDING_DATA` 不填 0；费用后收益及超额仅在证券与基准的完整复权 OHLC 窗口都齐备时发布。统计按 `score_version_id` 分开，并报告记录数、独立入场日期和非重叠窗口数；重复刷新与重叠持有期不是独立交易。`COLLECTING/OBSERVING` 始终 `calibrated=false`、`authorizes_production=false`，不会因为出现盈利样本自动晋级。

#### 机会榜 Top1 / Top3 / 整榜对照

`opportunity_outcome_tracking.by_version[].ranking_evaluation` 使用 `opportunity-ranking-performance-v1`，回答“当时榜首、前三名、整榜分别表现如何”，不是事后挑选上涨最多的股票：

- `groups.top1/top3/board` 只读取已冻结的全局原始排名。Top3 必须真实存在原 rank 1、2、3，不能拿只有两只的榜单冒充前三名；旧版本也只按当时已登记的排名计算，不套用 v3 扣分。
- 每个评分身份、北京时间发布日先固定首次已核验发布的榜单；随后对每组真实的 `market × entry_trade_date` 窗口再次固定最早选择。两天周末发布但同一开盘入场不会变成两笔交易；后来的榜单或后来取得的成功行情不能替换最早缺数据的选择。所有原始发布记录仍保留。
- **整个原榜**全部合法结算才允许该批 Top1/Top3/整榜进入收益指标。即使榜首已取得行情，其他成员缺行情也不会先报告胜者结果。未成熟、缺行情、成员不足与重复发布分别计数。
- 先对组内证券等权，再对完整入场批次等权：`mean_net_return` 是扣费后绝对收益主指标，`mean_net_excess_return` 是同窗口基准超额副指标；同时展示正收益率、最差批次收益与不利波动。费用假设仍为 A/美往返 0.15%、港股 0.30%，不是实际券商账单或真实组合净值。
- 最差 10% 批次的平均净收益 `expected_shortfall_10pct` 只有实际尾部样本至少 5 个才发布，否则保持 `null`。`non_overlapping_cohort_count` 单列不重叠窗口数量，普通批次数不等于统计独立样本；早期观察不代表策略已经有效。
- 同时存在多个评分身份时，顶层 `ranking_evaluation.status=BY_VERSION_ONLY`、混合收益保持空；应逐版本看结果。统计版本、权重或选择政策不同的记录不能汇成一条“模型盈利曲线”，也不会解锁生产资格。

页面历史 Tab 的正式指标只读取通过完整合同校验的 `EXECUTABLE_MODEL + SETTLED` 样本。统计 cohort 固定为最新发布的 `(model_id, label_version)`，同一 `target_date` 只保留生成时间最晚的一次可执行预测，因此旧模型和同日重复运行不会把可靠样本数虚高；原始账本仍完整保留供审计。页面展示平均净收益、正收益率、Top 10% 命中率、Brier、ECE、历史已选样本 Rank IC、10% Expected Shortfall 和结算序列最大回撤；总体可靠门槛为 20 个独立决策日，Top 10% 与 Expected Shortfall 另按实际尾部样本数展示，至少 5 个尾部观测才标记达标。样本不足时明确标记“早期样本”，不可用时显示空值而不是伪造 0。这里的 Rank IC 是跨历史已选样本的排序相关性，最大回撤是按结算顺序串联的终值序列，不冒充真实持仓组合。

每条正式历史记录还会发布 `formal_sample_status` 与 `outcome_validation`。只有后端确认 `SETTLED_VALID + VALID` 的记录才能显示绿色“可执行·已结算”；仅有原始 `SETTLED`、身份冲突、算术错误或时点错误都不会进入正式指标，也不会在页面被包装成成功结算。

规则资格、Shadow 的 PENDING/SETTLED、排除和冲突数量均独立展示。旧的手动或本地调试 ledger 若不符合当前采样合同，会保留文件但标记为排除，不计入有效研究样本。

规则历史指标按“`signal_date × market`”单元聚合，只有单元内每一条资格记录都是通过合同校验的 `SETTLED` 时，该单元才能进入收益、胜率、分市场和分通道指标；不完整单元中即使已有部分 `SETTLED` 行也整体排除。只要存在无效 batch 或 `PENDING_DATA` 这类数据缺失，历史状态就绝不能是 `READY`：已有其他合法结算时显示 `PARTIAL_DATA`，尚无合法结算时显示 `PENDING_DATA / INVALID_DATA`。`PENDING_MATURITY` 只表示窗口尚未成熟，不会被当成数据缺失，但同样不会提前进入指标。

观察和规则结算都有三种逐股状态：预测窗口未结束时为 `PENDING_MATURITY`；已成熟但缺少完整复权开收盘价时为 `PENDING_DATA`；只有身份、源快照摘要、时间窗口、调整行情和收益算术全部通过合同校验才进入 `SETTLED`。独立 Workflow 每天北京时间 `06:30` 尝试结算，`12:30` 再做一次幂等 watchdog 补跑；已结算的不可变 outcome 不会被重复改写。任一轮在验证后都立即重建、部署历史数据，因此历史 Tab 不必等下一次选股任务。诊断可以计算 Brier、AUC、ECE、Rank IC 和分位收益，但只属于相应研究轨；它不进入正式收益分母，也不能自动授权生产概率模型。生产授权仍需要预注册门槛、足够的独立前瞻 cohort，以及未参与调参的留出样本；代码部署本身不会强制晋级。

## 云端定时快照与数据源

生产站使用纯云端批次快照，不依赖 Render、Futu OpenD、个人电脑、Docker 或 Tunnel 常驻。GitHub Actions 在计划检查点获取公开数据、重算候选池和全部评分，验证通过后由 Cloudflare Worker 发布不可变快照。电脑关机不会影响下一次云端任务。

快照生成时使用的主要数据口径为：

- A 股宽基主召回来自新浪行情中心的沪主板/深主板/创业板/科创板分板块横截面，东方财富在某板块缺口时回退；报价使用腾讯财经与东方财富的有界重试链路，模型日 K 只接受东方财富 `fqt=1`、腾讯 `qfqday` 或 Yahoo `adjclose` 三种明确调整口径。日 K 通过 GitHub Actions Cache 跨批次复用，缺失代码才低并发补拉；盘中技术分会用本轮抓取的腾讯报价覆盖缓存中的当日日线，缓存只优化请求频率，不替代行情新鲜度门禁。
- A 股龙虎榜数据来自东方财富数据中心公开接口。
- 港股和美股候选边界来自本轮东方财富延迟权益证券横截面，经过证券类别复核后入池；源不可用时切换新浪公开市场榜单。目标 200/300 只的价格、最近交易时段与日线由 Yahoo Finance chart 二次验证，公开源缺口或时效不合格会降级，不会回填静态策展池。
- 港股调整日 K 以 Yahoo 为主，低并发重试后，最多对剩余 24 只（4 个并发）使用独立补源：腾讯港股 `hkfqkline` 的明确 `qfqday`，再尝试东方财富 `fqt=1`。补源校验证券代码、有序且不重复的日期、正价格、完整 OHLC 与准确目标交易日；腾讯只有原始 `day` 时不冒充前复权。最后的缓存回退仍需通过原有完整性和时效门禁；补源失败保留具体缺口，不降低 98% 健康阈值，也不保证每批一定有 200 只可深评。
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
  → 分轨登记/结算正式、Shadow、MODEL_OBSERVATION 与规则资格结果
  → 校验 schema 与生产合同
  → 构建内容寻址的候选/详情/事件/历史资产与 `data-manifest-v1`
  → Wrangler 部署 Cloudflare Worker
  → 完整线上契约验证
  → 冻结已核验发布的机会榜，并独立归档轻量后续收益台账
  → 按归档策略将每日检查点、规则合格或正式可执行快照与 ledger 写回 main

Cloudflare Worker（请求时）
  → 当前从同代内嵌 manifest/资产提供服务
  → 首屏只返回身份绑定的轻量摘要
  → 候选、单股详情、事件和历史 API 按 Tab 分页懒加载
  → 完整快照只供审计、不可变历史与显式调用
  → 不在请求时获取行情，也不重算选股
```

每个数据对象都以 SHA-256 内容寻址，并由同一个 manifest 绑定 `snapshot_key`、生成时间、源快照摘要和字节数。当前生产配置使用随 Worker 发布的同代内嵌资产；仓库未启用 R2 bucket/binding，因此正常请求直接选择 embedded manifest。如果未来选中了可选 R2 manifest，但某个 R2 object 缺失，Worker 只能在内嵌 manifest 与它属于同一 generation，且请求资产的 key、SHA-256 和字节数逐项一致时回退到内嵌副本；任一身份不一致就失败关闭，绝不混用跨代资产。部署链尚未实现“R2 alias + Worker Version”联合回滚，因此 `ENABLE_R2_DATA_PUBLISH=1` 会在切换任何 alias 前主动标红，不能误开。只有联合回滚和故障演练完成后才允许启用 R2。

Python 选股程序不会在 Worker 或浏览器请求中重算。页面初始化只读 `/api/latest-summary`；打开候选、事件或历史 Tab 后才读取对应轻量 API。刷新页面不改变 Legacy、V2、双低分数、全局排序或门禁结论。`GET /api/pick?force=1` 固定返回 `409 RECOMPUTE_NOT_SUPPORTED`，需要重算时应手动触发 GitHub Actions。

## 数据更新时序与可靠性

生产默认使用 **GitHub Actions 原生 `schedule` 主调度 + GitHub watchdog 补跑**；额外配置仓库专用密钥后，Cloudflare Cron 才能加入独立检查点触发。缺少专用密钥时不宣称独立触发已接通。系统展示时区为 `Asia/Shanghai`，检查点如下：

```text
周一至周五：08:17 / 10:17 / 12:17 / 15:17 / 16:17 / 20:17 / 22:47
美股收盘后：纽约周一至周五 16:17
              = 北京周二至周六 04:17（夏令时）/ 05:17（冬令时）
```

独立触发配置成功后，Cloudflare Cron 与 GitHub 原生 `schedule` 可在同一检查点分别发起调用；Workflow 的并发锁与 `schedule_gate` 以线上完整快照去重，先完成的健康发布会让后续调用跳过。GitHub 还在每个检查点 30 分钟后运行 watchdog：北京时间 `08:47 / 10:47 / 12:47 / 15:47 / 16:47 / 20:47 / 23:17`，纽约收盘后 `16:47`（北京夏令时 `04:47`、冬令时 `05:47`）。watchdog 会先核对线上完整快照；目标检查点已健康覆盖时直接跳过，不会重复生成。

仓库已将 `CLOUDFLARE_SCHEDULER_ENABLED=1`，使 Cloudflare Cron 成为独立检查点触发器；Worker 只有在同时配置专用最小权限 `GITHUB_WORKFLOW_DISPATCH_TOKEN` 时才会实际 dispatch。版本库开关不证明生产 secret 已存在，缺少 secret 时 Cloudflare 路径会明确显示为未就绪，但不会阻止部署，也不会关闭 GitHub 原生 `schedule` 与 watchdog 降级链路。`/api/status.next_refresh` 与数据健康 Tab 应按检查点、watchdog 及纽约夏/冬令时计算，并独立展示 Cloudflare dispatch 是否真正可用。

每次实际 cron 都记录来源调用点、逻辑检查点、开始延迟、恢复模式和生成时间；对应审计字段包括 `source_invocation_slot`、`scheduled_invocation_slot` 与 `scheduler_delay_seconds`。发布前按“调用点 + 生成时间”做单调校验，迟到旧任务不能覆盖新批次。普通延迟仍在原调用点的 4 小时窗口内处理；超过窗口时进入有界 `late_cron_recovery`，有效恢复调用点最多 12 小时。`schedule_gate.py` 只用线上完整 `/api/latest` 作为“已成功发布”证据：线上不可达、目标批次缺失/失败，或行情/候选池处于可恢复降级时继续运行。门禁硬校验 A/港/美实际召回达到 `300 / 200 / 300`，并检查动态来源、行情、A 股基础/技术评分及深研覆盖；仓库里的 `latest.json` 不能单独抑制刷新，因为它不证明 Cloudflare 已经切换成功。

同一个逻辑调用点如果已经完成一次可核验的降级发布，会标记 `source_recovery_already_attempted` 并停止该调用点的重复全市场重算；这不是把降级状态改成健康。后续 watchdog 或新检查点仍有自己的恢复机会，失败的发布不能消耗成功发布证据。迟到与遗漏记录继续保留，不因补发成功而被清零。

观察/规则结算与选股生成分离：`settle-observations.yml` 每天北京时间 `06:30` 主跑，`12:30` 执行幂等 watchdog，也可手动触发。它同时更新 observation settlement 与 rule settlement，验证后提交必要 JSON，并立即构建、部署历史资产；即使没有新提交也会验证并发布当前历史口径。对每个结算发布尝试只做单轮行情请求（`--retries 0`）；未成熟预测正常保持 `PENDING_MATURITY`，行情源超时或缺数固化为 `PENDING_DATA` 等待下次运行。Workflow 整体设置 40 分钟硬超时，给安装依赖、结算、最多 3 次 Git 冲突处理、历史构建、部署和验收留出有界时间。只有合同冲突、无法读取的账本、非法结算结果或历史线上验收失败才让 Workflow 标红。

归档短名单回放由独立 `historical-replay.yml` 执行，使用单独并发锁，避免延迟的研究任务阻塞生产检查点。GitHub Actions Cache 仅用于减少重复行情请求，不是长期证据；最终合同化 JSON 才是可审计产物。产物改变时，Workflow 只提交这一个白名单文件，并通过 GitHub 自己的 workflow dispatch 请求现有 `deploy-worker.yml` 生成和发布新快照；回放任务本身不持有 Cloudflare 密钥，不调用 OpenD/Futu，也不直接改写 `latest.json`。

一次生成与 outcome 结算各最多尝试 3 次。部署前执行单元测试、JavaScript 语法检查、snapshot schema 校验和 immutable 快照一致性检查；部署后先轻量轮询 `generated_at` / `snapshot_key` 直到新版本收敛，再验证完整快照摘要、历史、不可变快照、页面合同和所有可见候选行情，避免在边缘版本传播期每轮重复执行整套探针。生成、测试或部署前校验失败时不会切换生产版。部署前还会记录当前唯一 100% 生效的 Cloudflare Worker Version 和快照摘要；若部署后完整验收失败，Workflow 会标红并自动回滚到该精确版本，再核对旧快照身份与摘要。这是自动恢复，不是零暴露发布：新版在部署后验证窗口内可能短暂在线；回滚本身若失败也会继续标红，需要人工处理。

只有“定时任务实际运行 + 新快照成功发布 + 部署后完整验收通过”才会生成 `scheduler-checkpoint-receipt-v1`。回滚或验收失败不能写成正向证据。receipt 在本次已验证部署之后由独立最小写权任务持久化，因此聚合的 `scheduler-checkpoint-ledger-v1` **从下一个构建/发布批次才能看到它**，合同明示 `evidence_lag_batches=1`；这不是当批发布丢失。

检查点账本以最近 24 小时为覆盖窗口。开始累积 receipt 后的前 24 小时必须是 `readiness=INITIALIZING`、`checkpoint_coverage_status=INITIALIZING_24H_LEDGER`、`missed_checkpoints_24h=null`，而不是假报 0 次遗漏；窗口完整后才能根据按时、迟到和遗漏 receipt 发布 `READY / DEGRADED`。“主检查点后 45 分钟内完成发布”是可观测的内部 SLO 目标，`guaranteed=false`、`public_data_source_sla=false`；它不是 GitHub、交易所或公开数据源的准时保证。

每次定时或手动生成都会上传一个保留 30 天的 GitHub Actions 恢复包。为避免数 MiB、宽池批次可接近 10 MiB 的全量快照在 Git 和 Worker 中无限增长，长期 Git 归档保存每日末次主要检查点、产生生产规则合格候选的批次，以及确实产生正式可执行候选的批次；Worker 只携带最近 30 个决策日的完整交互快照。更早日期继续保留轻量摘要和隔离账本，因此历史统计仍可审计，但页面不会再下载其完整候选明细。归档冲突重试采用单调合并：较旧任务可以补充自己的不可变快照，但不能覆盖较新的 `latest.json`、把 `SETTLED` 降级成 `PENDING`，或丢失观察 revision。

### 可用性分层

API 和页面不用一个绿色 `ok` 概括全部能力，而是分层发布：

| 层级 | 公开字段 | 准确含义 |
|---|---|---|
| 传输/合同组装 | `ok` | 当次 HTTP 请求成功，且 API 能从同一 manifest generation 组装通过身份校验的响应；不表示选股、无人值守或概率模型已就绪 |
| 当前研究决策 | `research_decision_ready` | 快照时效、三市场候选/行情覆盖和规则安全门禁足以支持当前研究或规则复核；不等于校准概率可执行 |
| 检查点证据 | `checkpoint_evidence_ready` | 已形成完整 24 小时 `scheduler-checkpoint-ledger-v1` 证据窗口；初始化期必须为 `false`/`INITIALIZING` |
| 无人值守刷新 | `unattended_refresh_ready` | 在线调度与 watchdog 配置有效，且完整检查点账本未发现超出目标的迟到或遗漏；Cloudflare dispatch 是否已接通由独立字段报告。它仍是运营 SLO，不是外部 SLA |
| 校准执行 | `calibrated_execution_ready` | 前瞻样本、校准、交易成本、尾部风险和人工治理授权全部通过，才能为 `true`；样本尚未成熟时应明确显示 `COLLECTING`，不能从规则合格分推导为可执行 |

因此 `ok=true` 与一个或多个独立 `ready=false` 同时出现是合法且必要的诚实状态；页面必须分别展示原因，不能用传输成功覆盖数据、调度或校准未就绪。

浏览器每 5 分钟读取一次 `/api/status`，并在服务端发布的 `next_refresh` 检查点主动复核；后台检查发现 `snapshot_key` 变化时重读 `/api/latest-summary`。手动“刷新已发布快照”还会核对历史摘要，即使股票快照身份没变也能更新新发布的结算结果，不会因此重算市场数据。当前未打开的候选、事件和历史 Tab 不会被顺带请求；按需接口返回更新的时效门禁时，浏览器会按服务端 `evaluated_at` 单调收紧状态，不等待下一轮定时轮询。它不会轮询盘中行情，也不在前端重算评分与排序。快照 `fresh` 只表示它满足发布时效合同，不等于所有公开数据源绝对完整。

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
| 分页参数非法 | 候选、事件和历史 API 返回 `400 INVALID_PAGINATION`，不会静默回退到第 1 页或截断到上限 |
| 指定历史日期不存在 | `/api/pick?date=` 返回 `404 PICK_NOT_FOUND`，不会静默回退 latest |
| 日期格式非法 | 返回 `400 INVALID_DATE` |
| 历史 manifest 不可用 | 返回 `503 HISTORY_MANIFEST_UNAVAILABLE`，页面不显示伪 0 样本 |
| 快照过期 | `snapshot_use.mode=HISTORICAL_RESEARCH_ONLY`、`current_decision_allowed=false`、`blocker_codes=[SNAPSHOT_NOT_FRESH]`；当前合格候选强制为 0，旧不可变档案和当时的历史合格结论仍可审计 |

## API 契约

```text
GET /api/status
GET /api/gate-status
GET /api/latest-summary
GET /api/candidates?market=us&q=NVDA&page=1&limit=25
GET /api/candidates/<candidate_id>
GET /api/events?scope=decision_bound&decision_eligible=true&event_id=evt_123&page=1&limit=25
GET /api/latest
GET /api/history?view=daily&page=1&limit=5
GET /api/history?view=raw&page=1&limit=5
GET /api/data/<content-addressed-key>
GET /api/pick?date=2026-08-24
GET /api/pick?snapshot=<snapshot_key>.json
# 旧客户端兼容路由：只返回已发布快照，不获取实时行情
GET /api/live?market=a_share&code=603228
GET /api/live?market=hk&code=01882.HK
GET /api/live?market=us&code=PWR
```

契约要点：

- `/api/status` 返回快照版本、新鲜度、`snapshot_as_of`、按 Cloudflare/GitHub 检查点与 watchdog 计算的 `next_refresh`、`active_refresh_mode`、美股收盘夏/冬令时时点、`data_mode=scheduled_snapshot` 和 `device_dependency=false`。`ok` 只表示传输与合同组装成功；`research_decision_ready`、`checkpoint_evidence_ready`、`unattended_refresh_ready` 和 `calibrated_execution_ready` 必须独立解读。快照过期时 `snapshot_use` 以 `SNAPSHOT_NOT_FRESH` 失败关闭。
- `/api/gate-status` 返回生成/发布时间、来源调用点、逻辑检查点、调度延迟、恢复模式、发布后端和检查点账本状态。有合法 ledger 但尚未满 24 小时时发布 `INITIALIZING_24H_LEDGER`；还没有可验证 ledger 时才是 `UNAVAILABLE_NO_COMPLETE_LEDGER`。两种情况都必须使 `missed_checkpoints_24h=null`，不会拿未知冒充 0 次遗漏。
- `/api/latest-summary`、`/api/candidates`、单股详情、`/api/events` 和 `/api/history` 必须来自同一个 `data-manifest-v1` generation，并具有相同 `snapshot_key`、源快照 SHA-256 和字节数；身份不一致返回 503。候选搜索/市场过滤和分页由服务端完成，`scanned_count` 始终是完整扫描数，不会被当前页条数替代。候选列表以 `candidate-list-v2` + `candidate-role-v1` 分开规则主候选、规则合格项与 Legacy 市场首选。
- `/api/events` 发布 `event-list-v2`，默认 bound-first，并在分页前完成 `scope`、`decision_bound`、`decision_eligible`、`event_id`、`market`、`symbol`、`event_type`、`direction` 和 `q` 过滤。非法事件筛选返回 `400 INVALID_EVENT_FILTER`。
- `/api/candidates`、`/api/events` 和 `/api/history` 中显式提供的 `page` / `limit` 必须是合法正整数且不超过端点上限；非整数、零、负数或越界 limit 统一返回 `400 INVALID_PAGINATION`。只有省略参数时才使用默认值。
- 候选、详情、事件、历史与首屏响应含当前时效门禁，因此固定使用 `no-store` 且不返回可导致过期 304 的 ETag。`/api/gate-status` 只在完整绑定 manifest 与调度开关时支持 ETag；`/api/data/<key>` 只提供 manifest 中登记的不可变对象，使用内容摘要 ETag 和一年 immutable cache。
- `/api/latest` 流式返回完整快照，供审计和兼容客户端使用；它不是首屏加载依赖。
- `/api/history` 默认 `view=daily`，按 `target_date` 合并盘中重复运行，同类保留最后一次；`view=raw` 返回不可变原始运行。正式、Shadow、观察和规则资格结果始终分开统计，不受页面 limit 或 daily 合并影响。
- `/api/pick?snapshot=` 是最精确的历史寻址方式；同一天可能有多次快照。
- `/api/pick?date=` 只返回该日期匹配项；非法日期 400、不存在 404，绝不静默返回 latest。
- `/api/live` 只是保留 URL 的 scheduled-snapshot 兼容接口，浏览器不调用它。它从完整快照派生、最多 90 只且编码体积不超过 512 KiB 的候选行情索引中，只返回同时保存了正价格、`source_as_of`、`fetched_at` 和成交量单位的可追溯行情；全部正式合格候选必须完整保留，超过边界时构建在部署前失败，不能静默截断。缺少来源字段时返回 `SNAPSHOT_QUOTE_UNAVAILABLE`，不会把计划价或 K 线收盘价冒充行情。成功响应固定发布 `data_mode=SCHEDULED_SNAPSHOT`、`provider_class=SCHEDULED_SNAPSHOT`、`is_realtime=false` 和 `realtime_guaranteed=false`；接口名中的 `live` 不代表盘中实时。
- 可变 API JSON 使用 `Cache-Control: no-store`；凡响应内含当前时间或 `snapshot_use` 的路由不返回 ETag。不可变内容寻址对象使用长期缓存；静态资产由 Cloudflare 边缘提供。
- `signal_date` 是信号形成日，`generated_at` 是快照生成时间；每个市场的 `entry_trade_date` 和 `forecast_end_trade_date` 由真实交易日历生成。
- `NO_VALID_PICK` 是主动放弃，不是一笔买入预测，也不能记成亏损样本。

## 页面 Tab

1. **今日答案**：展示 global 正式动作、研究优先项、市场状态、风险和 10 交易日窗口。
2. **候选池**：展示三市场候选、Legacy/V2/双低边界、来源链、快照行情质量与单股详情。
3. **事件证据**：区分自动证据、人工待入库与模型信号，并明确规则候选属于事件催化还是质量趋势；质量趋势无正向事件时不伪造绑定关系。
4. **历史检验**：记录每次规则资格的 `qualification_track`、资格分和事件审计说明，并与 Legacy 历史、主动放弃、正式可执行预测和 `SHADOW_RESEARCH` 隔离；数据异常不会降级成 0 胜率。
5. **模型逻辑**：解释候选召回、因子、生产 V4 双通道阈值、global 门禁、版本与约两周标签。
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

生成一次新快照并更新隔离结果账本：

```bash
python3 server.py --once --force
python3 scripts/settle_outcomes.py
python3 scripts/settle_rule_outcomes.py --max-workers 12 --retries 0
python3 scripts/validate_snapshot.py data/picks/latest.json
```

启动本地 Worker：

```bash
npm run dev
```

## 部署与运维

### GitHub / Cloudflare Secrets

- `CLOUDFLARE_API_TOKEN`：Worker 部署权限。
- `XUANGU_WORKFLOW_DISPATCH_TOKEN`：可选 GitHub Actions Secret。只选择 `dzhdingzihang/xuangu` 仓库、授予 `Actions: write` 的 fine-grained token；发布工作流通过标准输入写入 Worker 的 `GITHUB_WORKFLOW_DISPATCH_TOKEN`，不输出令牌、不从本机自动发现凭据，也拒绝 OAuth/经典 PAT。缺失时保留 GitHub 原生调度并明确报告独立触发未配置。令牌到期需在仓库 Secret 中替换后重新部署。
- Cloudflare 定时 `workflow_dispatch` 是可选的独立检查点触发路径，仓库配置为 `CLOUDFLARE_SCHEDULER_ENABLED=1`。这只启用代码路径，不代表生产 secret 已配置；必须为仓库 `dzhdingzihang/xuangu` 单独创建只有 `Actions: write` 的 fine-grained token，并以 Wrangler secret `GITHUB_WORKFLOW_DISPATCH_TOKEN` 保存。不得复用 `CLOUDFLARE_API_TOKEN`、任何行情密钥或本地 `gh` 的宽权限凭证。GitHub Actions 原生 `schedule` 主调度与 30 分钟 watchdog 不使用该开关或 token，因此 secret 缺失不会令部署失败，仍由 GitHub 主链路刷新；但数据健康状态必须明确报告 Cloudflare dispatch 未就绪。Worker 只接受白名单表达式，并在运行时跳过不匹配纽约 `16:17` 的 DST 变体。
- R2 当前未启用，内嵌同代资产是正式生产数据后端。现阶段不得设置 `ENABLE_R2_DATA_PUBLISH=1`；Workflow 会在 alias 切换前失败关闭并主动拒绝该配置。如果未来由 R2 manifest 供应数据，某个 R2 object 的内嵌回退也只接受同 generation 且 key / SHA-256 / 字节数一致的副本，不会把 R2 缺口静默降级为跨代数据。启用前必须补齐 alias 与 Worker Version 的原子切换、联合回滚与线上故障演练。
- 定时选股不需要 OpenD、Tunnel、Render 或个人设备密钥。
- Cloudflare 使用一个合并的定时入口，运行时过滤未配置时点及不匹配纽约盘后的夏冬令时变体，实际主检查点与 30 分钟 watchdog 不变。免费配额由整个账号共享；本项目不占满全部定时入口，也不要求升级付费套餐。

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

验收 `/api/status` 时应确认 `snapshot_generation=github-actions`、`data_mode=scheduled_snapshot`、`device_dependency=false`、`snapshot_as_of`、`active_refresh_mode`、`next_refresh`，以及 `research_decision_ready`、`checkpoint_evidence_ready`、`unattended_refresh_ready`、`calibrated_execution_ready` 四层状态。调度路径应表达为 GitHub 原生 `schedule` 主调度 + 30 分钟 watchdog；配置专用凭据后再启用 Cloudflare 独立补充触发。Cloudflare 开关/token 状态必须独立展示，不能把仅有版本库开关误报为 dispatch 已可用。同时检查 `/api/gate-status` 的 snapshot identity、发布后端、receipt 证据滞后批次和 24 小时 ledger 状态；初始窗口显示 `INITIALIZING` 是预期状态。如果检查 `/api/live` 兼容路由，预期 `provider_class=SCHEDULED_SNAPSHOT` 与 `is_realtime=false`，不应期待 `REALTIME`。

`xuangu.alixjd.com` 的生产页面、API 和定时更新均不依赖 Render、OpenD 或个人电脑。

## 生产边界与下一步

当前系统可以从三市场宽池给出 V4 规则合格待复核候选、统一 10 日交易复核计划和“最值得优先研究”的跨市场排序，并持续记录约两周结果；它尚不能诚实证明“哪只最可能赚最多”，也没有上线经前瞻样本校准的 10 日上涨概率。要把 Shadow 排名或 `RESEARCH_ONLY` 升级为生产级概率选择，至少还需要：

- 港股和美股点时全市场证券主表与退市历史；
- 统一、可审计的点时行情、财务、事件与公司行为数据；
- 跨市场费用、滑点、汇率和不可成交处理；
- purge/embargo 的滚动样本外训练与验证；
- 概率校准、Brier/ECE、Rank IC、分位收益与漂移监控；
- 足够长的 Shadow 账本样本，并通过版本化晋级门槛。

在这些条件完成前，页面会继续保留所有 Legacy 因子、V2 去重影子评分与 A 股双低七因子；V4 规则资格分只用于合格候选排序，净超额排序 V2 保持 Shadow，十日 `global` 严格门禁继续阻止假精确。定时任务、规则分、研究优先项和历史结果均不构成收益保证。

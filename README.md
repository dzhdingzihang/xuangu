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

系统先召回候选，再做较重的 K 线与方法论深评，避免只在少量手工股票中挑第一名。

- A 股使用动态多路召回：事件/异动、相对强势、流动性、可控回调、近期历史候选，并合并来源链。
- A 股会过滤或门控 ST/退市风险、无有效价格、成交不足、涨停/一字板和明显不可交易状态；PB 不再作为进入主池的硬门槛。
- 港股和美股目前使用版本化的策展静态池，覆盖主要指数权重和 AI 芯片、光通信、存储、半导体设备、数据中心电力/液冷、机器人、软件、量子、商业航天等方向，再获取行情与 K 线深评。
- 港美快照明确标记 `universe_origin=curated_static`。这不是港美全市场动态扫描；在接入可靠的全市场证券主表、退市历史和点时财务数据前，系统不会宣传为“全市场覆盖”。

### 2. Legacy 因子继续保留

升级没有删除原有因子。Legacy 继续保存并参与各市场内部排序：

- 基础行情：价格、涨跌幅、成交额、换手率、量比和流通市值。
- 缠论近似：MA5/MA10/MA20、二买/三买近似、箱体突破回踩、MACD 改善和过度乖离。
- CZSC 轻量映射：中枢突破/回踩、MA20/MA30 趋势、箱体位置和背驰风险。
- UZI 规则映射：多维评分、评审团近似、游资射程、买点纪律、流动性和过热/陷阱风险。
- Serenity 产业链因子：AI capex 上游瓶颈、客户/供给确定性，以及稀释、单一催化和追高风险。
- 风险与交易门槛：市场风险、分数阈值、硬风险数、成交承接、涨停/过热和两周区间下沿。

候选保留 `score`、`recommendation_degree`、`pre_score`、`chan_score`、`czsc_score`、`uzi_score`、`uzi_panel_score`、`serenity_score`、`reasons`、`risk_flags`、`estimated_2w_range`、入场参考和风险价位等字段。Legacy 的市场级动作不会自动升级成跨市场可执行答案。

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

每个稳定的 `RESEARCH_ONLY` 研究优先项会写入 `data/outcomes/<prediction_id>.json`，track 固定为 `SHADOW_RESEARCH`。账本与正式可执行模型绩效完全分开：

- 新研究优先项先登记为 `PENDING`；
- 入场采用下一交易日开盘，退出采用第 10 个交易日收盘；
- 退出日尚未完整结束时不会提前结算；
- 成熟后使用同市场日线，按市场记录成本假设，结算为 `SETTLED`；
- A 股使用前复权日线，港美使用 Yahoo adjusted close 因子调整的开盘与收盘；
- 同一 `prediction_id` 幂等更新，不修改原始决策快照。

Shadow 胜率和收益只能描述这条研究优先规则的历史，不得混入 `global_decision.primary` 的生产绩效，也不得用来声称已有校准概率。页面历史 Tab 会单独展示 Shadow 的 PENDING/SETTLED 状态；没有合法样本时显示无样本，不填造 0 胜率。

## 实时行情链路

网页和 API 由 Cloudflare Worker 提供，实时行情使用“授权源优先、公开源明确降级”的链路：

```text
浏览器（只轮询当前可见候选，15 秒）
  → Cloudflare Worker /api/live
    → Futu OpenD 本地只读网关（Bearer 鉴权）
      → Cloudflare Tunnel: xuangu-quotes.alixjd.com
    → 失败时回退 PUBLIC_BEST_EFFORT
       A 股：东方财富，整组失败再到腾讯
       港股/美股：Yahoo Finance 1m/chart
```

Worker 对每个 `IP + market + code` 限制为 60 秒 90 次，只允许查询当前快照中的候选代码，并使用 10 秒内存缓存；本地网关使用 5 秒缓存、单次最多 50 个 symbol，只暴露只读 `/health` 和鉴权 `/v1/quotes`。网页只在页面可见时刷新当前选中股票，并拒绝用更旧的行情时间覆盖快照中的较新值。

实时状态必须按 API 字段解释：

| `quote_status` | 含义 | `is_realtime` |
|---|---|---:|
| `REALTIME` | 授权行情源、交易时段活跃且源时间满足新鲜度阈值 | `true` |
| `DELAYED` | 有价格但源时间延迟，或公开 best-effort 盘中回退 | `false` |
| `LAST_CLOSE` | 市场已收盘，返回最近收盘/盘后结束价格 | `false` |
| `UNAVAILABLE` | 没有可用价格 | `false` |

`provider_class=LICENSED_REALTIME` 表示来自 Futu OpenD 授权链路；`provider_class=PUBLIC_BEST_EFFORT` 表示公开回退。公开回退即使价格很新，也不会伪装成 `REALTIME`，只发布 `DELAYED` 或 `LAST_CLOSE`。收盘时看到 `LAST_CLOSE` 是正常状态，不是实时链路故障。

真实盘中 `REALTIME` 依赖运行 Futu OpenD 的 Mac、OpenD 登录与行情权限、本地 LaunchAgent、Docker 和 cloudflared Tunnel 持续在线。GitHub Actions 与 Cloudflare Worker 无法替代这台行情网关；主链路中断时网站仍可用，但会明确降级到公开 best-effort。

## 生产架构

静态页面、选股快照和 API 都在 Cloudflare Workers，Render 不再是生产依赖。

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
  → 通过 Tunnel 查询 Futu OpenD 实时行情
  → 主行情链路异常时使用公开 best-effort 回退
```

Python 选股程序不会在 Worker 请求中重算。`/api/live` 只更新当前候选的价格、会话和延迟状态，不改变 Legacy/V2/双低分数、全局排序或门禁结论。`GET /api/pick?force=1` 固定返回 `409 RECOMPUTE_NOT_SUPPORTED`，需要重算时应手动运行 GitHub Actions。

## 数据更新时序与可靠性

北京时间主检查点：

```text
工作日 08:58 / 09:58 / 10:58 / 12:58 / 13:58 / 14:58 / 21:28 / 23:58
```

每个主检查点设置 30 分钟后的补跑。`schedule_gate.py` 会检查线上完整 `/api/latest` 与仓库 `latest.json`：同一检查点已经生成且数据源健康时跳过；已生成但行情或候选池处于可恢复降级时，补跑仍会重试。GitHub 排队延迟在 4 小时窗口内仍归属最近检查点，周五 23:58 延迟到周六凌晨也可继续处理。

一次生成与 outcome 结算各最多尝试 3 次。部署前执行单元测试、JavaScript 语法检查和 snapshot schema 校验；部署后必须验证线上 `generated_at`、`snapshot_key`、schema、模型版本、历史、不可变快照和三市场 live contract。成功部署的恢复包保留 30 天，归档 Git 冲突使用有界重试，归档失败会让 Workflow 标红而不会掩盖问题。

网页每 5 分钟检查一次新快照，只有 `generated_at` 变化才重载快照和历史；可见候选行情每 15 秒刷新。快照健康与实时行情健康是两套独立状态：快照 `fresh` 不代表每个行情源都完整，实时网关降级也不会删除最后一份已验证快照。

GitHub scheduled workflow 不是精确计时器，公开数据源也没有 SLA，因此系统提供的是“目标检查点 + 补跑 + 可观测降级”，不是 100% 准点保证。真实交易日历负责预测窗口与结算；GitHub cron 仍以工作日检查点启动，交易所休市时应由快照市场状态和门禁阻止不当执行。

## 故障降级

| 故障 | 系统行为 |
|---|---|
| Futu/OpenD/Tunnel 不可用 | `/api/live` 转公开 best-effort，并发布 `provider_class`、`fallback_reason` 与非实时状态 |
| 所有实时来源不可用 | 返回 `502` 和 `quote_status=UNAVAILABLE`，不复用旧价冒充实时 |
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
GET /api/live?market=a_share&code=603228
GET /api/live?market=hk&code=01882.HK
GET /api/live?market=us&code=PWR
```

契约要点：

- `/api/status` 返回快照版本、新鲜度、生成方式，以及实时网关是否配置；它不是行情本身。
- `/api/latest` 返回完整快照；`/api/latest-summary` 返回轻量摘要。
- `/api/history` 默认 `view=daily`，按 `target_date` 合并盘中重复运行，同类保留最后一次；`view=raw` 返回不可变原始运行。绩效和 Shadow 账本另按 `prediction_id` 去重。
- `/api/pick?snapshot=` 是最精确的历史寻址方式；同一天可能有多次快照。
- `/api/pick?date=` 只返回该日期匹配项；非法日期 400、不存在 404，绝不静默返回 latest。
- `/api/live` 仅支持 `a_share / hk / us` 和当前快照候选，返回 `live-quote-v1`，包含 `provider`、`provider_class`、`source_as_of`、`fetched_at`、`latency_seconds`、`session`、`quote_status`、`is_realtime`、`is_stale` 与 `volume_unit`。
- API JSON 使用 `Cache-Control: no-store`；静态资产由 Cloudflare 边缘提供。
- `signal_date` 是信号形成日，`generated_at` 是快照生成时间；每个市场的 `entry_trade_date` 和 `forecast_end_trade_date` 由真实交易日历生成。
- `NO_VALID_PICK` 是主动放弃，不是一笔买入预测，也不能记成亏损样本。

## 页面 Tab

1. **今日答案**：展示 global 正式动作、研究优先项、市场状态、风险和 10 交易日窗口。
2. **候选池**：展示三市场候选、Legacy/V2/双低边界、来源链、行情健康与单股详情。
3. **事件证据**：区分自动证据、人工待入库与模型信号，并展示扫描状态。
4. **历史检验**：区分 Legacy 历史、global 合同和 `SHADOW_RESEARCH` 结果；数据异常不会降级成 0 胜率。
5. **模型逻辑**：解释候选召回、因子、去重评分、global 门禁、版本与约两周标签。
6. **数据健康**：分别监控任务、快照、市场覆盖、事件管线、实时源与结论可用性。

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

### 本地 Futu 行情网关

网关必须和 Futu OpenD 位于同一台机器，默认读取 `127.0.0.1:11111`，自身只监听 `127.0.0.1:8789`。

```bash
python3 -m pip install -r requirements-gateway.txt
export QUOTE_GATEWAY_TOKEN='<至少 24 位随机值>'
python3 scripts/realtime_gateway.py

curl -fsS http://127.0.0.1:8789/health
```

macOS 生产运行通过 `scripts/launch_realtime_gateway.py` 从 Keychain 服务 `com.alixjd.xuangu.quote-gateway`、账户 `xuangu` 读取 token，再由 LaunchAgent 守护。不要把 bearer token 写入仓库、plist、日志或命令历史。Cloudflare Worker 中的 `QUOTE_GATEWAY_TOKEN` Secret 必须与 Keychain 值一致。

Cloudflare Tunnel 应把 `xuangu-quotes.alixjd.com` 代理到本机 `http://127.0.0.1:8789`（Docker cloudflared 场景使用 `host.docker.internal:8789`）。外网 `/health` 可用于可用性检查，`/v1/quotes` 必须携带 Bearer token。

## 部署与运维

### GitHub / Cloudflare Secrets

- `CLOUDFLARE_API_TOKEN`：Worker 部署权限。
- `CLOUDFLARE_DNS_API_TOKEN`：推荐使用只具备 `alixjd.com` DNS Edit 的独立 token；未设置时 DNS workflow 会尝试使用前者。
- `QUOTE_GATEWAY_TOKEN`：不是 GitHub Secret，而是 Cloudflare Worker Secret；通过 Wrangler 写入。

```bash
printf '%s' "$QUOTE_GATEWAY_TOKEN" | npx wrangler secret put QUOTE_GATEWAY_TOKEN
```

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

### 一次性配置实时域名 DNS

命名 Tunnel 创建完成后，运行幂等 workflow：

```bash
gh workflow run configure-realtime-dns.yml --repo dzhdingzihang/xuangu --ref main
```

它只会创建或修正预期的 `xuangu-quotes.alixjd.com` CNAME 和代理状态；如果同名位置已有无关记录，会拒绝覆盖。随后会验证公开 `/health`。该 workflow 不是日常定时任务，DNS 正常后无需重复运行。

### 线上验收

```bash
curl -fsS https://xuangu.alixjd.com/api/status
curl -fsS https://xuangu.alixjd.com/api/latest-summary
curl -fsS 'https://xuangu.alixjd.com/api/history?view=daily&limit=5'
curl -fsS https://xuangu-quotes.alixjd.com/health
curl -fsSI https://xuangu.alixjd.com/
```

对 `/api/live` 的验收应选当前快照中真实存在的候选，并同时检查 `provider_class`、`quote_status`、`source_as_of` 和 `is_realtime`，不能只看 `price`。市场收盘时预期是 `LAST_CLOSE`；交易时段只有授权链路新鲜时才预期 `REALTIME`。

Render 配置已经从仓库移除，`xuangu.alixjd.com` 不依赖 Render。如果旧 `chan-stock-selector.onrender.com` 服务仍存在，应在 Render 控制台 Suspend 并关闭 Auto-Deploy；删除仓库文件不会自动停止外部服务。

## 生产边界与下一步

当前系统已经能诚实回答“今天三市场中最值得优先研究谁”，并持续记录其约两周 Shadow 结果；它尚不能诚实承诺“哪只最可能赚最多”。要把 `RESEARCH_ONLY` 升级为生产级可执行选择，至少还需要：

- 港股和美股点时全市场证券主表与退市历史；
- 统一、可审计的点时行情、财务、事件与公司行为数据；
- 跨市场费用、滑点、汇率和不可成交处理；
- purge/embargo 的滚动样本外训练与验证；
- 概率校准、Brier/ECE、Rank IC、分位收益与漂移监控；
- 足够长的 Shadow 账本样本，并通过版本化晋级门槛。

在这些条件完成前，页面会继续保留所有旧因子、给出 `RULE_PRIORITY` 研究排序、展示实时行情质量，并让 `global` 严格门禁阻止假精确和伪实时。

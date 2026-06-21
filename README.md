# 智能选股

面向 A 股、港股、美股的两周维度智能选股网站。

线上地址：[https://xuangu.alixjd.com](https://xuangu.alixjd.com)

## 目标

- 每个开盘日 08:58、09:58、10:58、12:58、13:58、14:58、21:28、23:58 生成未来约 2 周、10 个交易日的推荐。
- 每次更新都会结合当日实时价、前 2 周真实 K 线、市场环境、UZI / CZSC / Serenity 因子重新计算。
- 每次快照独立保存，同一天推荐变化可以追溯。
- A 股、港股、美股分别给出决策；未达到阈值时明确显示“无推荐”。
- 每只候选股展示实时/盘前/盘中/盘后买入价、推荐度、两周涨幅预估、止损线、真实 K 线、推荐理由和风险拦截原因。
- 候选池会显示 `候选池 / 深度评分`：候选池是进入本轮扫描的总数，深度评分是成功拿到 K 线并完成 UZI / CZSC / Serenity 评分的数量。

## 核心逻辑

系统不是单一指标打分，而是把实时可买价格、结构、趋势、产业链、资金和风险过滤合成一个两周推荐度。

- 缠论结构：参考二买、三买、背驰、均线持股线、箱体突破等可量化形态。
- `waditu/czsc`：参考分型、笔、中枢、信号-事件-交易框架；生产环境使用内置轻量 CZSC 结构因子，避免每半小时部署时安装完整研究库导致更新变慢。
- `wbh604/UZI-Skill`：加重多维评分、投资者评审团共识、游资射程、龙虎榜、过热和杀猪盘过滤；UZI 买点纪律、流动性和陷阱风险会直接影响推荐度。
- `yan-labs/serenity-aleabitoreddit`：参考 AI capex 上游瓶颈、CPO/光通信、InP/化合物半导体、HBM/存储、neocloud、电力等产业链因子。
- Serenity Skill：额外按“需求去噪 → 财务科目映射 → 错误分类小盘 → 错误定价验证 → 验证链 → alpha 五维评分”复核产业链候选。
- 市场风控：指数环境、涨停追高、过热、流动性、下行空间、MA20 失守等会降低推荐度或直接给出无推荐。

## 候选池范围

当前不是三大市场无限制全量逐只扫描，而是“广覆盖候选池 + 深度评分”的两层结构：

- A 股：同花顺热度/事件池 + 东方财富全市场流动性/动量初筛 Top300 + 历史候选池兜底，再合并去重后进入实时行情和深度评分。
- 港股：恒指/恒科/港股通常见权重、互联网、汽车、医药、半导体、AI 应用等扩展池，当前静态候选池 47 只。
- 美股：Nasdaq/S&P 大票、半导体、AI 服务器、AI 网络、neocloud、电力、核电、量子、商业航天等扩展池，当前静态候选池 84 只。

如果外部行情源临时不可用，系统会使用最近历史快照中的真实 K 线作为兜底，避免候选池在非交易时段或接口抖动时退化为 0。

当前模型版本：`smart-selector-2026-06-04.2-uzi-live`

## 推荐输出

每个市场都会输出：

- `BUY_CANDIDATE`：两周推荐，代表通过当前阈值。
- `NO_TRADE`：无推荐，代表候选股没有达到两周买入标准。
- `recommendation_degree`：推荐度，越高代表未来两周上涨信号越强。
- `estimated_2w_range`：未来两周涨幅预估区间。
- `entry_price` / `realtime`：当前买入参考价和盘前/盘中/盘后状态。
- `uzi_panel_score` / `uzi_panel`：UZI-Skill 风格评审团近似分和多空摘要。
- `reasons`：推荐理由。
- `risk_flags` / `message`：风险标签或未推荐原因。
- `kline`：最近真实日 K OHLC 数据，用于前端 K 线图。
- `snapshot_key`：快照文件名，用于追溯当天每次更新变化。

注意：推荐度不是胜率承诺，也不是收益保证。

## 数据源

- 同花顺强势股题材归因
- 腾讯财经行情
- 东方财富全市场、龙虎榜、行业热度
- 百度股市通日 K
- Yahoo Finance 日 K（港股 / 美股）
- GitHub 公开研究仓库的方法论和产业链线索

## API

```text
GET /api/status
GET /api/latest-summary
GET /api/latest
GET /api/history?limit=120
GET /api/pick?date=2026-06-04
GET /api/pick?snapshot=2026-06-19_2026-06-19_190401.json
```

常用字段：

- `target_date`：推荐对应日期。
- `signal_date`：使用的行情信号日期。
- `forecast_end_date`：两周观察窗口结束日期。
- `forecast_horizon`：推荐观察周期。
- `markets.a_share` / `markets.hk` / `markets.us`：三市场决策。
- `history[].snapshot_key`：历史快照唯一标识。

说明：

- 首页历史记录应优先使用 `snapshot_key` 拉取指定快照，避免同一天多次更新时只看到当天最新结果。
- `latest-summary` 只返回轻量摘要，适合监控和快速状态检查；完整候选、UZI、CZSC 诊断仍在 `latest` / `pick` 中。

## 本地运行

```bash
cd "/Users/dingzihang/Documents/猪猪投资存钱罐/chan-stock-site"
python3 server.py --port 8790
```

打开：

```text
http://127.0.0.1:8790
```

生成一次快照：

```bash
python3 server.py --once --force
```

指定目标日：

```bash
python3 server.py --once --date 2026-06-04 --force
```

两周回测：

```bash
python3 scripts/backtest_may.py
```

回测窗口使用 10 个交易日，并输出两周收益、期间最大回撤和止损触发率。

构建 Cloudflare Worker 静态资源：

```bash
npm install
npm run build
```

## 自动部署

GitHub Actions 在北京时间开盘日 08:58、09:58、10:58、12:58、13:58、14:58、21:28、23:58 运行一次：

1. 安装 Python 依赖。
2. 生成新的智能选股快照。
3. 构建 Worker assets。
4. 提交 `data/picks/*.json` 历史快照。
5. 部署到 Cloudflare Workers。

对应 cron：

```text
58 0,1,2,4,5,6,15 * * 1-5
28 13 * * 1-5
```

这是 UTC 时间，对应北京时间 08:58、09:58、10:58、12:58、13:58、14:58、21:28、23:58。

## UZI-Skill

UZI-Skill 已按官方指引安装到本机：

```text
/Users/dingzihang/Documents/猪猪投资存钱罐/UZI-Skill
```

也可以单独运行个股深度分析：

```bash
cd "/Users/dingzihang/Documents/猪猪投资存钱罐/UZI-Skill"
python3 run.py 贵州茅台 --no-browser
python3 run.py AAPL --no-browser
python3 run.py 002273.SZ --depth lite --no-browser
```

## Serenity Skill

安装到 Agents skill 目录：

```bash
python3 scripts/install_serenity_skill.py
```

如果你已经有完整 Serenity skill 源目录，且目录内包含 `SKILL.md`、`LICENSE`、`references`、`assets`、`scripts`、`examples`、`agents` 等文件或目录，可以指定来源：

```bash
python3 scripts/install_serenity_skill.py --source /path/to/serenity-skill
```

安装目标：

```text
$HOME/.agents/skills/serenity-skill
```

选股系统会检测该目录，并把 Serenity 的瓶颈五维 alpha 评分纳入候选股的 `serenity.alpha_profile`、推荐理由和综合分。

## 风险提示

本项目是量化和研究辅助工具，不构成投资建议，不保证盈利。短线和两周维度受市场情绪、政策、流动性和突发消息影响很大，请结合仓位、止损和自身风险承受能力使用。

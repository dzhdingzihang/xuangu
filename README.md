# 智能选股

A 股 / 港股 / 美股的未来 2 周智能选股网站。

核心目标：

- 每个交易日 09:00 生成未来约 2 周、10 个交易日的推荐。
- 交易时段每半小时更新一次快照。
- 每次快照独立保存，历史推荐变化可追溯。
- 每个市场给出推荐股票、推荐度、两周涨幅预估和推荐理由；没有通过阈值则显示“无推荐”。

## 核心逻辑

- 缠论 PDF：二买、三买、背驰、均线持股线等可量化结构。
- `waditu/czsc`：参考分型、笔、中枢、信号-事件-交易框架，内置轻量 CZSC 结构因子；GitHub Actions 会尝试安装 `czsc` 作为可选运行时。
- `wbh604/UZI-Skill`：参考多维评分、评审团共识、游资射程、杀猪盘/过热风控，形成 UZI 风控因子。
- `yan-labs/serenity-aleabitoreddit`：AI capex 上游瓶颈、CPO/光通信、InP/化合物半导体、HBM/存储、neocloud、电力等产业链因子。

## 运行

```bash
cd "/Users/dingzihang/Documents/猪猪投资存钱罐/chan-stock-site"
python server.py --port 8790
```

打开：

```text
http://127.0.0.1:8790
```

## 命令行生成快照

```bash
python server.py --once --force
```

指定目标日：

```bash
python server.py --once --date 2026-06-04 --force
```

## 数据源

- 同花顺强势股题材归因
- 腾讯财经行情
- 东方财富全市场、龙虎榜、行业热度
- 百度股市通日 K
- Yahoo Finance 日 K（港股 / 美股）

## 自动部署

GitHub Actions 会在北京时间交易日 09:00-15:30 每半小时生成新快照、提交历史文件并部署 Cloudflare Worker。

注意：本工具是量化决策辅助，不构成投资建议，不保证盈利。

# 缠论量化选股网站

本地运行的 A 股 2 日持有选股工具。它结合缠中说禅 PDF 中可量化的买点思想、同花顺强势股题材、腾讯收盘行情、东方财富龙虎榜和日 K 技术结构。

核心原则：

- 只选 1 只主选股；如果胜率和风控不达标，输出“今日不交易”。
- 默认使用前一交易日收盘数据，适合每天早上 8:30 决策。
- 买入后最多持有 2 个交易日；跌破止损线或 MA10 失守提前退出。
- 预测准确率是模型先验估计，不是承诺收益，需要后续用真实交易结果校准。

## 运行

```bash
cd "/Users/dingzihang/Documents/猪猪投资存钱罐/chan-stock-site"
../.venv/bin/python server.py --port 8790
```

然后打开：

```text
http://127.0.0.1:8790
```

## 命令行重算

```bash
../.venv/bin/python server.py --once --force
```

指定目标日：

```bash
../.venv/bin/python server.py --once --date 2026-05-26 --force
```

## 数据源

- 同花顺强势股题材归因
- 腾讯财经行情
- 东方财富龙虎榜
- 百度股市通日 K（优先，带 MA5/10/20）
- 东方财富日 K（备用）

## 部署到 Render

本目录已经包含 Render Blueprint：

```text
render.yaml
requirements.txt
runtime.txt
```

Render 启动命令：

```bash
python server.py --host 0.0.0.0 --port $PORT
```

注意：Render Free Web Service 可能休眠，内置 08:30 定时器只有服务处于运行状态时才会准点执行。若要稳定每天 08:30 自动刷新，建议升级为常驻实例，或额外配置 Render Cron/外部定时器访问 `/api/pick?force=1`。

## 缠论量化映射

- 女上位：MA5 > MA10。
- 二买近似：多头均线后回踩 MA5/MA10 不破并重新收回。
- 三买近似：突破近 20 日中枢后回试不破。
- MACD 背驰改善：低点附近 MACD 柱力度收敛。
- 风控：不满足信号强度或风险过高时空仓。

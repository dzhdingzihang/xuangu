const els = {
  dateInput: document.getElementById("dateInput"),
  refreshBtn: document.getElementById("refreshBtn"),
  forceBtn: document.getElementById("forceBtn"),
  topUpdateTime: document.getElementById("topUpdateTime"),
  subtitle: document.getElementById("subtitle"),
  actionBadge: document.getElementById("actionBadge"),
  primaryBlock: document.getElementById("primaryBlock"),
  reasons: document.getElementById("reasons"),
  riskList: document.getElementById("riskList"),
  signalDate: document.getElementById("signalDate"),
  historyStatus: document.getElementById("historyStatus"),
  historyList: document.getElementById("historyList"),
  candidateTabs: document.getElementById("candidateTabs"),
  candidateRows: document.getElementById("candidateRows"),
  candidateDetail: document.getElementById("candidateDetail"),
  factorStrip: document.getElementById("factorStrip"),
  miniChart: document.getElementById("miniChart"),
  marketBlock: document.getElementById("marketBlock"),
  industryPanel: document.getElementById("industryPanel"),
  industryBlock: document.getElementById("industryBlock"),
  marketTabs: document.getElementById("marketTabs"),
};

const LOCAL_HISTORY_KEY = "smart-stock-history-v2";
const MARKET_ORDER = ["a_share", "hk", "us"];
const MARKET_LABELS = { a_share: "A股", hk: "港股", us: "美股" };
let activeMarket = "a_share";
let activeCandidateMarket = "a_share";
let currentData = null;
let selectedCandidateKey = "";
let selectedHistoryKey = "";
let primaryLiveToken = 0;
let candidateLiveToken = 0;

function todayText() {
  const d = new Date();
  return `${d.getFullYear()}-${`${d.getMonth() + 1}`.padStart(2, "0")}-${`${d.getDate()}`.padStart(2, "0")}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function signed(value) {
  if (typeof value !== "number") return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function pctClass(value) {
  return value >= 0 ? "red" : "green";
}

function priceText(value) {
  if (typeof value !== "number") return "--";
  return value >= 100 ? value.toFixed(2) : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function numericScore(value, max = 100) {
  if (typeof value !== "number") return null;
  return clampNumber((value / max) * 100, 0, 100);
}

function scoreDisplay(value, max = 100) {
  const normalized = numericScore(value, max);
  return normalized === null ? "--" : Math.round(normalized);
}

function stockScore(stock) {
  return Math.round(stock && (stock.recommendation_degree || stock.confidence || 0));
}

function actionSubtitle(label) {
  if (label === "推荐买入") return "把握趋势主升股";
  if (label === "谨慎买入") return "控制仓位，等回踩更稳";
  if (label === "观察") return "信号未完全确认";
  return "等待更强买点";
}

function starRating(score) {
  const full = clampNumber(Math.round((score || 0) / 20), 0, 5);
  return `<span class="stars" aria-label="${full}星">${"★".repeat(full)}${"☆".repeat(5 - full)}</span>`;
}

function industryText(stock) {
  if (!stock) return "--";
  const tags = stock.theme_tags || stock.reason_tags || [];
  if (stock.industry || stock.sector || stock.role) return stock.industry || stock.sector || stock.role;
  if (Array.isArray(tags) && tags[0]) return tags[0];
  if (typeof tags === "string" && tags.trim()) return tags.split(/[+、,，/]/).filter(Boolean)[0] || tags;
  return "--";
}

function stockChange(stock) {
  if (!stock) return 0;
  return stock.current_change_pct || stock.change_pct || stock.intraday_change_pct || 0;
}

function currentTradePrice(stock) {
  if (!stock) return null;
  const latest = ((stock.kline || []).filter((item) => Number(item.close) > 0).at(-1) || {});
  const value =
    stock.current_price ||
    stock.realtime_price ||
    (stock.realtime && stock.realtime.price) ||
    Number(latest.close) ||
    stock.entry_price ||
    stock.price;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function tradeState(stock, hasPrimary = true) {
  const entry = Number(stock && (stock.entry_price || stock.price || 0));
  const current = currentTradePrice(stock) || entry;
  const deviation = entry ? ((current - entry) / entry) * 100 : null;
  if (!stock || !hasPrimary) {
    return {
      level: "level-no",
      label: "不买",
      text: "系统没有给出可执行标的，今天先不下单。",
      deviation,
    };
  }
  const stop = Number(stock.stop_loss || 0);
  const take = Number(stock.take_profit_reference || 0);
  if (stop && current <= stop) {
    return {
      level: "level-no",
      label: "取消买入",
      text: "实时价已经碰到或跌破止损区，说明走势没有按预期走，先保护本金。",
      deviation,
    };
  }
  if (take && current >= take * 0.98) {
    return {
      level: "level-no",
      label: "不追高",
      text: "实时价已经接近止盈位，继续追买的赔率不划算。",
      deviation,
    };
  }
  if (entry && current > entry * 1.03) {
    return {
      level: "level-caution",
      label: "等回落",
      text: "实时价比建议价高出较多，买进去后更容易先承受回撤。",
      deviation,
    };
  }
  if (entry && current >= entry * 0.985 && current <= entry * 1.01) {
    return {
      level: "level-buy",
      label: "可按计划买",
      text: "实时价仍在建议买入价附近，止损距离和上涨空间比较清楚。",
      deviation,
    };
  }
  return {
    level: "level-caution",
    label: "谨慎买入",
    text: "实时价偏离建议价，适合小仓位或等待回到买入区。",
    deviation,
  };
}

function updateLiveTradeState(stock, hasPrimary = true) {
  const state = tradeState(stock, hasPrimary);
  const label = document.getElementById("liveDecisionLabel");
  const text = document.getElementById("liveDecisionText");
  const deviation = document.getElementById("liveDeviationText");
  const box = document.getElementById("liveExecutionState");
  if (box) box.className = `execution-state ${state.level}`;
  if (label) label.textContent = state.label;
  if (text) text.textContent = state.text;
  if (deviation) deviation.textContent = state.deviation === null ? "实时偏离 --" : `实时偏离 ${signed(state.deviation)}`;
}

function waitConditions(stock, section) {
  const marketNote = section && section.market_note;
  const items = [
    stock ? `价格回到建议买入价 ${priceText(stock.entry_price || stock.price)} 附近，最好不要高出 1%。` : "出现推荐度 62 分以上、止损距离清楚的候选股。",
    "风险标签减少，尤其是追高、跌破 MA10、放量过猛这类短线风险。",
    "K 线重新站稳 MA10。简单说，就是股价回到最近 10 天平均成本上方。",
    marketNote || "市场环境没有系统性风险拦截，再考虑执行。",
  ];
  return items;
}

function twoWeekPlan(stock, hasPrimary = true) {
  if (!stock || !hasPrimary) {
    return [
      ["今天", "不买，先保留现金。"],
      ["触发条件", "等价格、趋势和风险同时变好。"],
      ["未来2周", "只记录观察，不把没有胜率的机会硬做成交易。"],
    ];
  }
  return [
    ["买入区", `尽量在 ${priceText(stock.entry_price || stock.price)} 附近执行，偏离超过 3% 就等回落。`],
    ["止损线", `跌破 ${priceText(stock.stop_loss)} 退出。简单说：先承认判断错了，保护本金。`],
    ["止盈区", `接近 ${priceText(stock.take_profit_reference)} 分批止盈，避免利润坐过山车。`],
    ["持有纪律", "最多按两周观察，若跌破 MA10 或推荐度明显下降，提前复核。"],
  ];
}

function factorConclusion(label, score) {
  if (score === "--") return "缺少数据";
  const value = Number(score);
  if (label.includes("UZI")) {
    if (value >= 75) return "买点纪律和风控较好";
    if (value >= 55) return "可以观察，仓位要轻";
    return "风控不足，不宜重仓";
  }
  if (label.includes("CZSC")) {
    if (value >= 70) return "结构偏多，趋势较顺";
    if (value >= 50) return "结构未坏，但不够强";
    return "结构偏弱，先等信号";
  }
  if (label.includes("Serenity")) {
    if (value >= 70) return "产业链弹性较强";
    if (value >= 45) return "题材一般，需看资金";
    return "题材支撑不足";
  }
  if (value >= 72) return "达到可执行推荐";
  if (value >= 62) return "可谨慎参与";
  return "不满足买入阈值";
}

function candidateCompare(row) {
  const leader = row && row.__leader;
  if (!row) return "暂无排序对比。";
  if (!leader && row.__rank === 1) {
    return "当前排名第一：综合推荐度最高，说明趋势、买点、题材和风险过滤同时更占优。";
  }
  if (!leader) return "暂无排序对比。";
  const gap = stockScore(leader) - stockScore(row);
  if (gap <= 0) {
    return "当前排名第一：综合推荐度最高，说明趋势、买点、题材和风险过滤同时更占优。";
  }
  return `比第一名低 ${gap} 分。简单说：它也有亮点，但趋势强度、买点舒服程度或风险控制不如第一名。`;
}

function historyStats(history) {
  const total = history.length;
  const marketKeys = ["a_share", "hk", "us"];
  let buyCount = 0;
  let noCount = 0;
  let scoreTotal = 0;
  let scoreCount = 0;
  history.forEach((item) => {
    marketKeys.forEach((key) => {
      const summary = marketSummaryForHistory(item, key);
      if (summary.has_primary) {
        buyCount += 1;
        const score = summary.recommendation_degree || summary.confidence;
        if (typeof score === "number") {
          scoreTotal += score;
          scoreCount += 1;
        }
      } else {
        noCount += 1;
      }
    });
  });
  const avg = scoreCount ? Math.round(scoreTotal / scoreCount) : 0;
  return { total, buyCount, noCount, avg };
}

function marketWind(data) {
  const items = (data.market && data.market.items) || [];
  const risk = data.market && data.market.risk;
  const up = items.filter((item) => Number(item.change_pct) > 0).length;
  const down = items.filter((item) => Number(item.change_pct) < 0).length;
  if (risk && risk !== "normal") {
    return {
      tone: "risk",
      title: "市场风向偏弱",
      text: "市场风险拦截开启，系统会降低追高股票权重，宁愿错过也先避免大回撤。",
    };
  }
  if (up >= down) {
    return {
      tone: "good",
      title: "市场风向可交易",
      text: "指数环境没有触发系统性风险，强势题材和趋势股更容易被资金继续关注。",
    };
  }
  return {
    tone: "watch",
    title: "市场风向分歧",
    text: "下跌指数更多，推荐会更看重止损距离和当前价是否舒服，不适合盲目追高。",
  };
}

function liveCode(stock) {
  return stock && (stock.code || stock.symbol || stock.ticker || stock.name);
}

function liveMerge(stock, live) {
  if (!stock || !live || !live.ok) return stock;
  const price = typeof live.price === "number" ? live.price : live.current_price;
  return {
    ...stock,
    current_price: price || stock.current_price,
    realtime_price: price || stock.realtime_price,
    current_change_pct: typeof live.current_change_pct === "number" ? live.current_change_pct : stock.current_change_pct,
    change_pct: typeof live.change_pct === "number" ? live.change_pct : stock.change_pct,
    realtime: {
      ...(stock.realtime || {}),
      price: price || (stock.realtime && stock.realtime.price),
      change_pct: typeof live.current_change_pct === "number" ? live.current_change_pct : live.change_pct,
      session_label: live.session_label || (stock.realtime && stock.realtime.session_label),
      source: live.source || (stock.realtime && stock.realtime.source),
      updated_at: live.updated_at,
    },
    kline: Array.isArray(live.kline) && live.kline.length ? live.kline : stock.kline,
    __liveUpdatedAt: live.updated_at,
    __liveSource: live.source,
  };
}

async function fetchLiveStock(stock, market) {
  const code = liveCode(stock);
  if (!code) throw new Error("缺少股票代码");
  const response = await fetch(`/api/live?market=${encodeURIComponent(market)}&code=${encodeURIComponent(code)}`, {
    cache: "no-store",
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "实时行情暂不可用");
  return payload;
}

function sparklineSvg(stock, tone = "green") {
  const rows = ((stock && stock.kline) || []).filter((row) => Number(row.close) > 0).slice(-24);
  if (rows.length < 2) {
    return `<svg class="sparkline ${tone}" viewBox="0 0 120 44" aria-hidden="true"><path d="M4 30 C28 18, 46 26, 68 18 S100 22, 116 10"></path></svg>`;
  }
  const closes = rows.map((row) => Number(row.close));
  const max = Math.max(...closes);
  const min = Math.min(...closes);
  const span = Math.max(max - min, 0.001);
  const width = 120;
  const height = 44;
  const points = closes
    .map((close, index) => {
      const x = 4 + (index / (closes.length - 1)) * (width - 8);
      const y = 6 + ((max - close) / span) * (height - 12);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return `<svg class="sparkline ${tone}" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="${points}"></polyline></svg>`;
}

function movingAverage(values, period) {
  return values.map((_, index) => {
    if (index + 1 < period) return null;
    const slice = values.slice(index + 1 - period, index + 1);
    return slice.reduce((sum, value) => sum + value, 0) / period;
  });
}

function formatVolume(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  const lots = value / 100;
  if (lots >= 10000) return `${(lots / 10000).toFixed(2)}万手`;
  return `${Math.round(lots).toLocaleString("zh-CN")}手`;
}

function shortDate(dateText) {
  const parts = String(dateText || "").split("-");
  if (parts.length !== 3) return dateText || "--";
  return `${Number(parts[1])}-${Number(parts[2])}`;
}

function timeText(item) {
  const label = item.generated_label || item.generated_at || "";
  const match = String(label).match(/(\d{1,2}:\d{2})/);
  return match ? match[1] : item.signal_date || "--";
}

function recommendationLabel(value, hasPrimary) {
  if (!hasPrimary) return "不买";
  if (value >= 72) return "推荐买入";
  if (value >= 62) return "谨慎买入";
  return "观察";
}

function confidenceTone(value) {
  if (value >= 70) return "strong";
  if (value >= 58) return "watch";
  return "weak";
}

function actionClass(value, hasPrimary) {
  if (!hasPrimary) return "level-no";
  if (value >= 72) return "level-buy";
  if (value >= 62) return "level-caution";
  return "level-watch";
}

function candidateKey(row) {
  return `${activeCandidateMarket}:${row && (row.code || row.symbol || row.name)}`;
}

function readableReason(text) {
  const raw = String(text || "");
  const rules = [
    ["女上位", "MA5 是最近 5 天的平均成本，MA10 是最近 10 天的平均成本。MA5 在 MA10 上方，说明最近买入的人愿意用更高价格成交，短线资金比前一段更强。"],
    ["多头排列", "价格和短中期均线从上到下排得比较顺，像楼梯往上走，趋势没有明显拐头。"],
    ["持股线", "MA10 可以理解成短线持股参考线，股价还守在线上，说明短线趋势暂时没有被破坏。"],
    ["二买", "上涨后先回踩，再重新站回来，代表不是盲目追高，而是回落后又有资金接住。"],
    ["三买", "突破前面的震荡区后，回踩没有跌回去，说明突破有机会是真的。"],
    ["MACD背驰改善", "股价接近低点时，下跌力量变弱，后面更容易出现修复。"],
    ["CZSC近似", "这是把缠论结构量化后的信号，意思是当前走势结构没有明显走坏。"],
    ["Serenity因子", "这是看产业链位置，越靠近稀缺供给、AI 投入和真实订单，越容易被资金重新定价。"],
    ["Serenity Skill", "这是产业链五维复核，分数高代表确定性、弹性和催化节奏更协调。"],
    ["UZI评审团", "这是模拟多位投资者一起打分，只有趋势、买点、风险和赔率同时说得过去才加分。"],
    ["UZI风控", "这是专门看会不会买在太贵、太热、太危险的位置，分越高代表当前价位更容易控制亏损。"],
    ["题材命中", "当前股票踩中了市场正在关注的主题，容易获得更多资金关注。"],
    ["龙虎榜净买入", "龙虎榜显示有席位净买入，说明短线活跃资金有参与。"],
    ["实时买入价", "这里用的是当前能参考的买入价格，不是只看昨收，所以更贴近实际下单。"],
    ["产业链主题", "它所在方向和近期资金关注的产业链有关，题材热度能给两周走势提供推力。"],
    ["成本位置", "离常用均线不远，代表止损距离相对可控，不是追得太高。"],
  ];
  const hit = rules.find(([key]) => raw.includes(key));
  return hit ? `${raw}。简单说：${hit[1]}` : raw;
}

function readableRisk(text) {
  const raw = String(text || "");
  const rules = [
    ["偏离 MA10 过大", "股价已经离短线平均成本太远，继续追容易买在短期高点。"],
    ["5日涨幅", "最近几天已经涨了不少，先买的人可能会卖出兑现利润。"],
    ["实时涨幅过大", "今天已经被抢得太高，当前价格再买的赔率变差。"],
    ["放量过猛", "成交突然放太大，说明分歧也变大，容易冲高回落。"],
    ["跌破 MA20", "中期趋势线失守，两周持有的稳定性会下降。"],
    ["跌破 MA10", "短线持股线失守，说明最近买盘承接不够强。"],
    ["MACD 柱缩短", "上涨动能开始变弱，虽然价格高，但推动力可能跟不上。"],
    ["融资", "公司融资或稀释压力会削弱上涨质量。"],
    ["稀释", "增发或融资可能摊薄股东权益，资金会更谨慎。"],
    ["追高", "当前价位不够舒服，买进去后更容易先承受回撤。"],
    ["硬风险", "有多个风控条件没有通过，系统宁愿少赚，也先避免亏损。"],
  ];
  const hit = rules.find(([key]) => raw.includes(key));
  return hit ? `${raw}。看法：${hit[1]}` : raw;
}

function clearList(node) {
  node.replaceChildren();
}

function li(text) {
  const item = document.createElement("li");
  item.textContent = text;
  return item;
}

function marketDecisionSummary(section) {
  const decision = (section && section.decision) || {};
  const primary = decision.primary || null;
  const blocked = decision.blocked_candidate || null;
  const candidate = primary || blocked;
  const confidence = candidate ? candidate.recommendation_degree || candidate.confidence : undefined;
  const range = candidate && (candidate.estimated_2w_range || candidate.estimated_2d_range);
  return {
    action: decision.action,
    title: decision.title,
    message: decision.message,
    has_primary: Boolean(primary),
    code: primary && primary.code,
    name: primary && primary.name,
    confidence,
    recommendation_degree: confidence,
    estimated_2w_range: range && range.text,
    entry_price: primary && (primary.entry_price || primary.price),
    stop_loss: primary && primary.stop_loss,
    take_profit_reference: primary && primary.take_profit_reference,
  };
}

function summarizeClientPick(data) {
  const decision = data.decision || {};
  const primary = decision.primary || decision.blocked_candidate;
  const summary = {
    target_date: data.target_date,
    signal_date: data.signal_date,
    generated_at: data.generated_at,
    generated_label: data.generated_label,
    forecast_end_date: data.forecast_end_date,
    forecast_horizon: data.forecast_horizon,
    action: decision.action,
    title: decision.title,
    message: decision.message,
    has_primary: Boolean(decision.primary),
    local_key: data.snapshot_key || `${data.target_date}_${data.signal_date}_${data.generated_at || ""}`,
    model_version: data.model_version,
  };
  if (primary) {
    const range = primary.estimated_2w_range || primary.estimated_2d_range;
    summary.code = primary.code;
    summary.name = primary.name;
    summary.confidence = primary.recommendation_degree || primary.confidence;
    summary.recommendation_degree = primary.recommendation_degree || primary.confidence;
    summary.estimated_2w_range = range && range.text;
    summary.score = primary.score;
  }
  if (data.markets) {
    summary.markets = Object.fromEntries(
      Object.entries(data.markets).map(([key, section]) => [key, marketDecisionSummary(section)]),
    );
  }
  return summary;
}

function readLocalHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(LOCAL_HISTORY_KEY) || "{}");
    return raw && typeof raw === "object" ? raw : {};
  } catch {
    return {};
  }
}

function writeLocalHistory(history) {
  localStorage.setItem(LOCAL_HISTORY_KEY, JSON.stringify(history));
}

function storeLocalPick(data) {
  if (!data || !data.target_date || !data.signal_date) return;
  const history = readLocalHistory();
  history[data.snapshot_key || `${data.target_date}_${data.signal_date}_${data.generated_at || ""}`] = data;
  writeLocalHistory(history);
}

function localSummaries() {
  return Object.entries(readLocalHistory())
    .map(([key, value]) => ({ ...summarizeClientPick(value), local_key: key }))
    .sort((a, b) => `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`));
}

function mergeHistory(serverRows) {
  const merged = new Map();
  (serverRows || []).forEach((item) => {
    merged.set(item.cache_key || item.snapshot_key || `${item.target_date}_${item.signal_date}_${item.generated_at || ""}`, item);
  });
  localSummaries().forEach((item) => {
    const key = item.cache_key || item.snapshot_key || item.local_key || `${item.target_date}_${item.signal_date}_${item.generated_at || ""}`;
    merged.set(key, { ...item, ...(merged.get(key) || {}) });
  });
  return [...merged.values()].sort((a, b) =>
    `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`),
  );
}

function selectedMarket(data) {
  if (!data.markets) {
    return { key: "a_share", label: "A股", decision: data.decision, stats: data.stats || {}, description: "" };
  }
  return data.markets[activeMarket] || data.markets.a_share;
}

function candidateMarket(data) {
  if (!data.markets) return selectedMarket(data);
  return data.markets[activeCandidateMarket] || data.markets.a_share;
}

function renderHero(data) {
  els.subtitle.textContent = `本次决策生成于 ${data.generated_label || data.generated_at || "--"}，观察窗口至 ${data.forecast_end_date || data.next_trade_date || "--"}`;
  els.topUpdateTime.textContent = `数据更新：${data.generated_label || data.generated_at || "--"}`;
}

function renderMarketTabs(data) {
  clearList(els.marketTabs);
  const markets = data.markets || { a_share: selectedMarket(data) };
  MARKET_ORDER.filter((key) => markets[key]).forEach((key) => {
    const section = markets[key];
    const decision = section.decision || {};
    const primary = decision.primary || null;
    const candidate = primary || decision.blocked_candidate || null;
    const confidence = candidate ? stockScore(candidate) : 0;
    const range = candidate && (candidate.estimated_2w_range || candidate.estimated_2d_range);
    const label = recommendationLabel(confidence, Boolean(primary));
    const level = actionClass(confidence, Boolean(primary));
    const tone = level === "level-caution" ? "amber" : level === "level-no" ? "red" : "green";
    const stats = section.stats || {};
    const poolText = `候选池 ${stats.universe_size || stats.raw_pool_size || "--"} / 深度评分 ${stats.scored_size || "--"}`;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `market-card ${key === activeMarket ? "active" : ""} ${level}`;
    if (primary) {
      button.innerHTML = `
        <div class="market-card-head">
          <div class="market-name"><span class="market-icon">${escapeHtml((section.label || MARKET_LABELS[key]).slice(0, 1))}</span><strong>${escapeHtml(section.label || MARKET_LABELS[key])}</strong></div>
          <span class="pill ${level}">${label}</span>
        </div>
        <div class="market-card-body">
          <div class="market-main">
            <div class="market-stock-name"><b>${escapeHtml(primary.name)}</b><em>${escapeHtml(primary.code)}</em></div>
            <div class="market-score ${confidenceTone(confidence)}"><strong>${confidence}</strong><span>分</span></div>
            ${starRating(confidence)}
          </div>
          <div class="market-metrics">
            <span><small>建议买入价</small>${priceText(primary.entry_price || primary.price)}</span>
            <span><small>止盈价</small>${priceText(primary.take_profit_reference)}</span>
            <span><small>止损价</small>${priceText(primary.stop_loss)}</span>
            <span class="market-range"><small>预估收益区间</small>${escapeHtml((range && range.text) || "--")}</span>
          </div>
          ${sparklineSvg(primary, tone)}
          <div class="pool-meta">${escapeHtml(poolText)}</div>
        </div>
      `;
    } else {
      button.innerHTML = `
        <div class="market-card-head">
          <div class="market-name"><span class="market-icon">${escapeHtml((section.label || MARKET_LABELS[key]).slice(0, 1))}</span><strong>${escapeHtml(section.label || MARKET_LABELS[key])}</strong></div>
          <span class="pill level-no">不买 / 无推荐</span>
        </div>
        <div class="no-trade-copy">
          <b>不买 / 无推荐</b>
          <span>${escapeHtml(decision.message || "当前市场环境下未发现符合策略的优质标的，请继续观察，等待更佳机会")}</span>
          <small>${escapeHtml(poolText)}</small>
          ${sparklineSvg(candidate, "red")}
        </div>
      `;
    }
    button.addEventListener("click", () => {
      activeMarket = key;
      activeCandidateMarket = key;
      render(data);
    });
    els.marketTabs.append(button);
  });
}

function renderPrimary(data) {
  const section = selectedMarket(data);
  const { decision } = section;
  const primary = decision.primary;
  const blocked = decision.blocked_candidate;
  const shown = primary || blocked;
  const badgeConfidence = shown ? stockScore(shown) : 0;
  els.actionBadge.className = `status ${actionClass(badgeConfidence, Boolean(primary))}`;
  els.actionBadge.textContent = primary ? recommendationLabel(primary.recommendation_degree || primary.confidence, true) : "不买";

  if (!shown) {
    els.signalDate.textContent = `${section.label || "A股"} · 不买 / 无推荐 · 更新时间：${data.generated_label || data.generated_at || "--"}`;
    const waits = waitConditions(null, section).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const plan = twoWeekPlan(null, false).map(([title, text]) => `<span><b>${escapeHtml(title)}</b>${escapeHtml(text)}</span>`).join("");
    els.primaryBlock.innerHTML = `
      <div class="primary-stock">
        <div class="stock-title">
          <strong>不买</strong>
          <span>没有可执行标的</span>
        </div>
        <p class="decision-copy">${escapeHtml(decision.message || "等待更强买点")}</p>
        <div id="liveExecutionState" class="execution-state level-no">
          <strong id="liveDecisionLabel">不买</strong>
          <span id="liveDecisionText">没有达到两周上涨胜率要求，现金也是仓位。</span>
          <em id="liveDeviationText">实时偏离 --</em>
        </div>
        <div class="wait-box">
          <b>等待条件</b>
          <ul>${waits}</ul>
        </div>
        <div class="trade-plan">${plan}</div>
      </div>
    `;
    renderFactorStrip(null);
    renderMiniChart(null);
    return;
  }

  const confidence = stockScore(shown);
  const label = primary ? recommendationLabel(confidence, true) : "不买";
  const range = shown.estimated_2w_range || shown.estimated_2d_range || {};
  const state = tradeState(shown, Boolean(primary));
  const waits = waitConditions(shown, section).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const plan = twoWeekPlan(shown, Boolean(primary)).map(([title, text]) => `<span><b>${escapeHtml(title)}</b>${escapeHtml(text)}</span>`).join("");
  els.signalDate.textContent = `${section.label || "A股"} · ${shown.name} ${shown.code} · ${label} · 所属行业：${industryText(shown)} · 更新时间：${data.generated_label || data.generated_at || "--"}`;
  els.primaryBlock.innerHTML = `
    <div class="primary-stock">
      <div class="operation-title"><span class="operation-icon">+</span><strong>操作建议</strong></div>
      <div class="operation-lines">
        <div><span>建议买入价</span><strong>${priceText(shown.entry_price || shown.price)}</strong></div>
        <div><span>止盈价</span><strong class="red">${priceText(shown.take_profit_reference)}</strong></div>
        <div><span>止损价</span><strong class="green">${priceText(shown.stop_loss)}</strong></div>
        <div><span>预计收益区间</span><strong>${escapeHtml(range.text || "--")}</strong></div>
        <div><span>持有周期</span><strong>2周以内</strong></div>
      </div>
      <div class="operation-cta ${actionClass(confidence, Boolean(primary))}">
        <strong>${label}</strong>
        <span>${actionSubtitle(label)}</span>
      </div>
      <div id="liveExecutionState" class="execution-state ${state.level}">
        <strong id="liveDecisionLabel">${escapeHtml(state.label)}</strong>
        <span id="liveDecisionText">${escapeHtml(state.text)}</span>
        <em id="liveDeviationText">${state.deviation === null ? "实时偏离 --" : `实时偏离 ${signed(state.deviation)}`}</em>
      </div>
      ${primary ? "" : `<div class="wait-box"><b>重新考虑买入，需要满足</b><ul>${waits}</ul></div>`}
      <div class="trade-plan">${plan}</div>
      <p class="decision-copy">${escapeHtml(decision.message || "按建议价附近执行，跌破止损价必须退出。")}</p>
    </div>
  `;
  renderFactorStrip(shown);
  renderMiniChart(shown);
  refreshPrimaryLive(shown, activeMarket, Boolean(primary));
}

function klineChartSvg(stock, options = {}) {
  const kline = (stock && stock.kline) || [];
  if (!kline.length) {
    return `
      <div class="chart-empty">
        <strong>暂无真实K线</strong>
        <span>该历史快照还没有保存 OHLC 数据</span>
      </div>
    `;
  }
  const rows = kline
    .filter((row) => Number(row.high) > 0 && Number(row.low) > 0 && Number(row.close) > 0)
    .slice(-32);
  if (!rows.length) {
    return `
      <div class="chart-empty">
        <strong>暂无真实K线</strong>
        <span>行情源没有返回有效 OHLC</span>
      </div>
    `;
  }
  const width = options.width || 430;
  const height = options.height || 270;
  const top = 20;
  const bottom = 64;
  const left = 22;
  const right = 16;
  const volumeHeight = 44;
  const gap = 12;
  const chartHeight = height - top - bottom - volumeHeight - gap;
  const highs = rows.map((row) => Number(row.high));
  const lows = rows.map((row) => Number(row.low));
  const closes = rows.map((row) => Number(row.close));
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const span = Math.max(maxPrice - minPrice, 0.001);
  const step = (width - left - right) / rows.length;
  const candleWidth = Math.max(4, Math.min(9, step * 0.58));
  const y = (price) => top + ((maxPrice - price) / span) * chartHeight;
  const volumeTop = top + chartHeight + gap;
  const volumes = rows.map((row) => Number(row.volume || row.vol || 0));
  const maxVolume = Math.max(...volumes, 1);
  const maPath = (period) => {
    const ma = movingAverage(closes, period);
    const points = ma
      .map((value, index) => {
        if (value === null) return null;
        const x = left + index * step + step / 2;
        return `${x.toFixed(2)},${y(value).toFixed(2)}`;
      })
      .filter(Boolean)
      .join(" ");
    return points ? `<polyline class="ma-line ma${period}" points="${points}"></polyline>` : "";
  };
  const candles = rows
    .map((row, index) => {
      const x = left + index * step + step / 2;
      const open = Number(row.open) || Number(row.close);
      const close = Number(row.close);
      const high = Number(row.high);
      const low = Number(row.low);
      const up = close >= open;
      const colorClass = up ? "up" : "down";
      const bodyTop = Math.min(y(open), y(close));
      const bodyHeight = Math.max(Math.abs(y(open) - y(close)), 2);
      return `
        <g class="candle ${colorClass}">
          <line x1="${x.toFixed(2)}" y1="${y(high).toFixed(2)}" x2="${x.toFixed(2)}" y2="${y(low).toFixed(2)}"></line>
          <rect x="${(x - candleWidth / 2).toFixed(2)}" y="${bodyTop.toFixed(2)}" width="${candleWidth.toFixed(2)}" height="${bodyHeight.toFixed(2)}" rx="1"></rect>
        </g>
      `;
    })
    .join("");
  const volumeBars = rows
    .map((row, index) => {
      const x = left + index * step + step / 2;
      const open = Number(row.open) || Number(row.close);
      const close = Number(row.close);
      const volume = Number(row.volume || row.vol || 0);
      const barHeight = Math.max((volume / maxVolume) * volumeHeight, 1);
      const colorClass = close >= open ? "up" : "down";
      return `<rect class="volume-bar ${colorClass}" x="${(x - candleWidth / 2).toFixed(2)}" y="${(volumeTop + volumeHeight - barHeight).toFixed(2)}" width="${candleWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="1"></rect>`;
    })
    .join("");
  const labels = [
    { y: top, text: priceText(maxPrice) },
    { y: top + chartHeight / 2, text: priceText((maxPrice + minPrice) / 2) },
    { y: top + chartHeight, text: priceText(minPrice) },
  ]
    .map((item) => `<text x="2" y="${item.y + 4}" class="axis-label">${item.text}</text>`)
    .join("");
  const last = rows[rows.length - 1];
  const first = rows[0];
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(stock.name)}真实日K线">
      <g class="grid">
        <line x1="${left}" y1="${top}" x2="${width - right}" y2="${top}"></line>
        <line x1="${left}" y1="${top + chartHeight / 2}" x2="${width - right}" y2="${top + chartHeight / 2}"></line>
        <line x1="${left}" y1="${top + chartHeight}" x2="${width - right}" y2="${top + chartHeight}"></line>
        <line x1="${left}" y1="${volumeTop + volumeHeight}" x2="${width - right}" y2="${volumeTop + volumeHeight}"></line>
      </g>
      <g class="axis">${labels}</g>
      <g>${candles}</g>
      <g>${maPath(5)}${maPath(10)}${maPath(20)}${maPath(60)}</g>
      <g>${volumeBars}</g>
      <text x="${left}" y="${height - 12}" class="date-label">${shortDate(first.date)}</text>
      <text x="${width - right - 38}" y="${height - 12}" class="date-label">${shortDate(last.date)}</text>
    </svg>
  `;
}

function liveStatusText(stock) {
  if (!stock) return "";
  if (stock.__liveLoading) return "正在刷新实时行情...";
  if (stock.__liveError) return `实时刷新失败：${stock.__liveError}`;
  if (stock.__liveUpdatedAt) return `实时行情已刷新：${stock.__liveUpdatedAt.replace("T", " ").replace("+08:00", "")} · ${stock.__liveSource || "行情源"}`;
  const updated = stock.realtime && stock.realtime.updated_at;
  if (updated) return `快照行情：${String(updated).replace("T", " ").replace("+08:00", "")} · ${(stock.realtime && stock.realtime.source) || "行情源"}`;
  return "使用当前快照行情";
}

function renderMiniChart(stock) {
  if (!els.miniChart) return;
  if (!stock) {
    els.miniChart.innerHTML = `
      <div class="chart-empty">
        <strong>暂无走势</strong>
        <span>当前市场无可执行标的</span>
      </div>
    `;
    return;
  }
  const rows = (stock.kline || []).filter((row) => Number(row.close) > 0);
  const close = rows.length ? Number(rows[rows.length - 1].close) : null;
  const base = stock.current_price || stock.realtime_price || (stock.realtime && stock.realtime.price) || close || stock.entry_price || stock.price || 100;
  const change = stockChange(stock);
  const closes = rows.map((row) => Number(row.close));
  const maValue = (period) => {
    const value = movingAverage(closes, Math.min(period, closes.length)).at(-1);
    return typeof value === "number" ? priceText(value) : "--";
  };
  const latestVolume = rows.length ? Number(rows[rows.length - 1].volume || rows[rows.length - 1].vol || 0) : null;
  els.miniChart.innerHTML = `
    <div class="chart-head">
      <div>
        <strong>实时K线（日线）</strong>
        <span class="live-status ${stock.__liveError ? "error" : ""}">${escapeHtml(liveStatusText(stock))}</span>
        <span class="ma-legend"><i class="ma5">MA5: ${maValue(5)}</i><i class="ma10">MA10: ${maValue(10)}</i><i class="ma20">MA20: ${maValue(20)}</i><i class="ma60">MA60: ${maValue(60)}</i></span>
      </div>
      <div class="chart-price"><span>实时价</span><strong>${priceText(base)}</strong><b class="${pctClass(change)}">${signed(change)}</b></div>
    </div>
    ${klineChartSvg(stock)}
    <div class="volume-caption">成交量 ${formatVolume(latestVolume)}</div>
  `;
}

async function refreshPrimaryLive(stock, market, hasPrimary = true) {
  const token = ++primaryLiveToken;
  renderMiniChart({ ...stock, __liveLoading: true });
  try {
    const live = await fetchLiveStock(stock, market);
    if (token !== primaryLiveToken) return;
    const merged = liveMerge(stock, live);
    renderMiniChart(merged);
    updateLiveTradeState(merged, hasPrimary);
  } catch (error) {
    if (token !== primaryLiveToken) return;
    renderMiniChart({ ...stock, __liveError: error.message || "实时行情暂不可用" });
  }
}

function renderFactorStrip(primary) {
  clearList(els.factorStrip);
  if (!primary) return;
  const confidence = stockScore(primary);
  const factors = [
    ["UZI 评分", primary.uzi_panel_score, 60],
    ["CZSC 评分", primary.czsc_score, 35],
    ["Serenity 评分", primary.serenity_score ?? (primary.serenity && primary.serenity.score), 120],
    ["综合评分", confidence, 100],
  ];
  factors.forEach(([label, value, max]) => {
    const score = scoreDisplay(value, max);
    const chip = document.createElement("span");
    chip.className = "factor-card";
    chip.innerHTML = `
      <b>${escapeHtml(label)} <em title="满分100，系统会把原始模型分数折算到同一尺度">i</em></b>
      <strong>${score} / 100</strong>
      <i class="score-bar"><i style="width:${score === "--" ? 0 : score}%"></i></i>
      <small>${escapeHtml(factorConclusion(label, score))}</small>
    `;
    els.factorStrip.append(chip);
  });
}

function renderReasons(data) {
  clearList(els.reasons);
  clearList(els.riskList);
  const decision = selectedMarket(data).decision || {};
  const primary = decision.primary || decision.blocked_candidate;
  if (!primary) {
    els.reasons.append(li(decision.message || "没有可执行买点"));
    els.riskList.append(li("无推荐时默认不买"));
    return;
  }
  (primary.reasons || []).slice(0, 6).forEach((reason) => els.reasons.append(li(readableReason(reason))));
  if ((primary.risk_flags || []).length) {
    primary.risk_flags.slice(0, 6).forEach((flag) => els.riskList.append(li(readableRisk(flag))));
  } else {
    els.riskList.append(li("未触发硬风险"));
  }
}

function renderCandidateTabs(data) {
  clearList(els.candidateTabs);
  const markets = data.markets || { a_share: selectedMarket(data) };
  MARKET_ORDER.filter((key) => markets[key]).forEach((key) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = key === activeCandidateMarket ? "active" : "";
    button.textContent = `${MARKET_LABELS[key] || key} Top5`;
    button.addEventListener("click", () => {
      activeCandidateMarket = key;
      renderCandidateRows(data);
      renderCandidateTabs(data);
    });
    els.candidateTabs.append(button);
  });
}

function renderCandidateRows(data) {
  const section = candidateMarket(data);
  const decision = section.decision || {};
  const rows = [decision.primary, ...(decision.watchlist || [])].filter(Boolean).slice(0, 5);
  clearList(els.candidateRows);
  if (els.candidateDetail) els.candidateDetail.replaceChildren();
  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6" class="empty-cell">该市场暂无可展示候选。</td>`;
    els.candidateRows.append(tr);
    if (els.candidateDetail) {
      els.candidateDetail.innerHTML = `<div class="candidate-empty">当前市场没有候选详情。</div>`;
    }
    return;
  }
  if (!rows.some((row) => candidateKey(row) === selectedCandidateKey)) {
    selectedCandidateKey = candidateKey(rows[0]);
  }
  const leader = rows[0];
  rows.forEach((row, index) => {
    row.__rank = index + 1;
    Object.defineProperty(row, "__leader", {
      value: leader,
      enumerable: false,
      configurable: true,
    });
    const range = row.estimated_2w_range || row.estimated_2d_range || {};
    const confidence = stockScore(row);
    const reasons = (row.reasons || []).slice(0, 2).map((item) => escapeHtml(readableReason(item))).join("<br>");
    const tr = document.createElement("tr");
    tr.className = candidateKey(row) === selectedCandidateKey ? "selected-row" : "";
    tr.tabIndex = 0;
    tr.innerHTML = `
      <td>${index + 1}</td>
      <td><strong>${escapeHtml(row.name)}</strong><span class="muted">${escapeHtml(row.code)}</span></td>
      <td><strong class="${confidenceTone(confidence)}">${confidence}</strong></td>
      <td>${priceText(row.entry_price || row.price)}<br><span class="muted">止损 ${priceText(row.stop_loss)}</span></td>
      <td><span class="${pctClass((range.high_pct || 0))}">${escapeHtml(range.text || "--")}</span></td>
      <td><div class="table-note positive-note">${reasons || "暂无理由"}</div></td>
    `;
    tr.addEventListener("click", () => {
      selectedCandidateKey = candidateKey(row);
      renderCandidateRows(data);
    });
    tr.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectedCandidateKey = candidateKey(row);
        renderCandidateRows(data);
      }
    });
    els.candidateRows.append(tr);
  });
  const selected = rows.find((row) => candidateKey(row) === selectedCandidateKey) || rows[0];
  renderCandidateDetail(selected, section);
}

function renderCandidateDetail(row, section, options = {}) {
  if (!els.candidateDetail || !row) return;
  const confidence = stockScore(row);
  const candidateHasBuyCase = confidence >= 62;
  const state = tradeState(row, candidateHasBuyCase);
  const latest = ((row.kline || []).filter((item) => Number(item.close) > 0).at(-1) || {});
  const currentPrice = row.current_price || row.realtime_price || (row.realtime && row.realtime.price) || Number(latest.close) || row.entry_price || row.price;
  const change = stockChange(row);
  const reasons = (row.reasons || []).slice(0, 5).map((item) => `<li>${escapeHtml(readableReason(item))}</li>`).join("");
  const risks = (row.risk_flags || []).slice(0, 5).map((item) => `<li>${escapeHtml(readableRisk(item))}</li>`).join("");
  const liveStatus = liveStatusText(row);
  els.candidateDetail.innerHTML = `
    <div class="candidate-detail-row">
      <span class="candidate-rank">${row.__rank || 1}</span>
      <div class="candidate-name-block">
        <strong>${escapeHtml(row.name)} <em>${escapeHtml(row.code)}</em></strong>
        <span>${escapeHtml(industryText(row))}</span>
      </div>
      <div class="candidate-metric"><span>实时价</span><strong class="${pctClass(change)}">${priceText(currentPrice)}</strong><em class="${pctClass(change)}">${signed(change)}</em></div>
      <div class="candidate-metric"><span>建议买入价</span><strong>${priceText(row.entry_price || row.price)}</strong></div>
      <div class="candidate-metric"><span>止盈价</span><strong class="red">${priceText(row.take_profit_reference)}</strong></div>
      <div class="candidate-metric"><span>止损价</span><strong class="green">${priceText(row.stop_loss)}</strong></div>
      <div class="candidate-metric score"><span>综合评分</span><strong>${confidence}分</strong>${starRating(confidence)}</div>
      <button class="detail-jump" type="button">查看单股说明</button>
    </div>
    <div class="candidate-live-status ${row.__liveError ? "error" : ""}">${escapeHtml(liveStatus)}</div>
    <div class="candidate-insight-grid">
      <section class="candidate-insight">
        <b>排序解释</b>
        <span>${escapeHtml(candidateCompare(row))}</span>
      </section>
      <section class="candidate-insight ${state.level}">
        <b>当前能不能买</b>
        <span><strong>${escapeHtml(state.label)}</strong>：${escapeHtml(state.text)} ${state.deviation === null ? "" : `实时价相对建议价 ${signed(state.deviation)}。`}</span>
      </section>
    </div>
    <div class="candidate-detail-explain">
      <section class="candidate-detail-note positive-note">
        <h4>推荐理由</h4>
        <ul>${reasons || "<li>暂无足够清晰的推荐理由。</li>"}</ul>
      </section>
      <section class="candidate-detail-note risk-note">
        <h4>风险说明</h4>
        <ul>${risks || "<li>未触发硬风险，但仍需要按止损价执行。</li>"}</ul>
      </section>
    </div>
  `;
  const jump = els.candidateDetail.querySelector(".detail-jump");
  if (jump) {
    jump.addEventListener("click", () => {
      activeMarket = activeCandidateMarket;
      render(currentData);
      document.getElementById("decisionPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  if (!options.skipLive) refreshCandidateLive(row, section);
}

async function refreshCandidateLive(row, section) {
  const token = ++candidateLiveToken;
  try {
    const live = await fetchLiveStock(row, activeCandidateMarket);
    if (token !== candidateLiveToken) return;
    renderCandidateDetail(liveMerge(row, live), section, { skipLive: true });
  } catch (error) {
    if (token !== candidateLiveToken) return;
    renderCandidateDetail({ ...row, __liveError: error.message || "实时行情暂不可用" }, section, { skipLive: true });
  }
}

function marketSummaryForHistory(item, key) {
  const markets = item.markets || {};
  if (markets[key]) return markets[key];
  if (key === "a_share") return item;
  return { has_primary: false, title: "无推荐", message: "历史摘要缺少该市场" };
}

function historyMarketChip(item, key) {
  const summary = marketSummaryForHistory(item, key);
  if (!summary.has_primary) {
    return `<span class="history-market no"><b>${MARKET_LABELS[key]}</b><em>不买</em></span>`;
  }
  return `<span class="history-market buy"><b>${MARKET_LABELS[key]}</b><em>${escapeHtml(summary.name)} ${escapeHtml(summary.code)}</em></span>`;
}

function renderHistory(history, currentTarget) {
  clearList(els.historyList);
  if (!history.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "还没有历史缓存。首次计算完成后，会自动保存到这里。";
    els.historyList.append(empty);
    els.historyStatus.textContent = "0 条";
    return;
  }
  const stats = historyStats(history);
  els.historyStatus.textContent = `${stats.total} 条 · 推荐 ${stats.buyCount} · 不买 ${stats.noCount} · 均分 ${stats.avg || "--"}`;
  const grouped = new Map();
  history.forEach((item) => {
    const key = item.target_date || "未知日期";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(item);
  });
  [...grouped.entries()].forEach(([date, rows]) => {
    const group = document.createElement("section");
    group.className = "history-day";
    group.innerHTML = `<h3>${shortDate(date)} 推荐</h3>`;
    rows.forEach((item) => {
      const snapshotKey = item.cache_key || item.snapshot_key || item.local_key || `${item.target_date}_${item.signal_date}_${item.generated_at || ""}`;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `history-snapshot ${snapshotKey === selectedHistoryKey ? "active" : ""}`;
      button.innerHTML = `
        <span class="snapshot-time">${timeText(item)}</span>
        <span class="snapshot-markets">
          ${historyMarketChip(item, "a_share")}
          ${historyMarketChip(item, "hk")}
          ${historyMarketChip(item, "us")}
        </span>
      `;
      button.addEventListener("click", async () => {
        els.dateInput.value = item.target_date;
        selectedHistoryKey = snapshotKey;
        const localPick = readLocalHistory()[snapshotKey];
        if (localPick) {
          render(localPick);
          renderHistory(history, snapshotKey);
          return;
        }
        await loadSnapshot(snapshotKey, history);
      });
      group.append(button);
    });
    els.historyList.append(group);
  });
}

function renderMarket(data) {
  clearList(els.marketBlock);
  const wind = marketWind(data);
  const windCard = document.createElement("div");
  windCard.className = `market-wind ${wind.tone}`;
  windCard.innerHTML = `<strong>${escapeHtml(wind.title)}</strong><span>${escapeHtml(wind.text)}</span>`;
  els.marketBlock.append(windCard);
  const note = document.createElement("p");
  note.textContent = data.market.risk_note || "指数环境未知";
  els.marketBlock.append(note);
  (data.market.items || []).forEach((item) => {
    const row = document.createElement("div");
    row.className = "market-row";
    row.innerHTML = `<span>${escapeHtml(item.name)}</span><strong class="${pctClass(item.change_pct)}">${signed(item.change_pct)}</strong>`;
    els.marketBlock.append(row);
  });
}

function renderIndustry(data) {
  clearList(els.industryBlock);
  const top = (data.industry_heat && data.industry_heat.top) || [];
  if (!top.length) {
    if (els.industryPanel) els.industryPanel.hidden = true;
    return;
  }
  if (els.industryPanel) els.industryPanel.hidden = false;
  top.slice(0, 6).forEach((item) => {
    const row = document.createElement("div");
    row.className = "industry-row";
    row.innerHTML = `<span>${escapeHtml(item.name)}</span><strong class="${pctClass(item.change_pct)}">${signed(item.change_pct)}</strong>`;
    els.industryBlock.append(row);
  });
}

function render(data) {
  currentData = data;
  if (!data.markets || !data.markets[activeMarket]) activeMarket = "a_share";
  if (!data.markets || !data.markets[activeCandidateMarket]) activeCandidateMarket = activeMarket;
  const section = selectedMarket(data);
  renderHero(data);
  els.signalDate.textContent = `${section.label || "A股"} · ${data.generated_label || data.generated_at || ""}`;
  renderMarketTabs(data);
  renderPrimary(data);
  renderReasons(data);
  renderCandidateTabs(data);
  renderCandidateRows(data);
  renderMarket(data);
  renderIndustry(data);
}

function renderLocalHistory() {
  renderHistory(mergeHistory([]), els.dateInput.value);
}

async function loadSnapshot(snapshotKey, history = []) {
  const response = await fetch(`/api/pick?snapshot=${encodeURIComponent(snapshotKey)}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "历史快照读取失败");
  selectedHistoryKey = snapshotKey;
  render(data);
  storeLocalPick(data);
  renderHistory(history.length ? history : mergeHistory([]), snapshotKey);
  return data;
}

async function loadHistory() {
  const response = await fetch("/api/history?limit=120");
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "历史记录读取失败");
  payload.history = mergeHistory(payload.history || []);
  renderHistory(payload.history, els.dateInput.value);
  return payload;
}

async function loadLatestSnapshot() {
  const response = await fetch("/api/latest");
  const data = await response.json();
  if (!response.ok) {
    const localLatest = localSummaries()[0];
    const localPick = localLatest && readLocalHistory()[localLatest.local_key];
    if (!localPick) throw new Error(data.error || "暂无历史决策缓存");
    render(localPick);
    els.actionBadge.textContent = `${localPick.decision.title} · 本地历史`;
    return localPick;
  }
  if (data.target_date) els.dateInput.value = data.target_date;
  render(data);
  storeLocalPick(data);
  renderLocalHistory();
  return data;
}

async function load(force = false, options = {}) {
  const showBusy = options.showBusy !== false;
  if (showBusy) {
    els.actionBadge.className = "status";
    els.actionBadge.textContent = force ? "重算中" : "计算中";
  }
  const params = new URLSearchParams();
  if (els.dateInput.value) params.set("date", els.dateInput.value);
  if (force) params.set("force", "1");
  const response = await fetch(`/api/pick?${params.toString()}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "数据源暂不可用");
  render(data);
  storeLocalPick(data);
  renderLocalHistory();
  loadHistory().catch(() => {
    els.historyStatus.textContent = "已显示本地历史";
  });
}

els.dateInput.value = todayText();
els.refreshBtn.addEventListener("click", () => load(false).catch(alert));
els.forceBtn.addEventListener("click", () => load(true).catch(alert));
loadHistory()
  .then(async (payload) => {
    const latestTarget = payload.latest && payload.latest.target_date;
    if (latestTarget) els.dateInput.value = latestTarget;
    const requested = els.dateInput.value;
    const cachedRequested = (payload.history || []).some((item) => item.target_date === requested);
    if (cachedRequested) return load(false, { showBusy: false });
    if (payload.latest) {
      els.historyStatus.textContent = "先显示最近缓存，后台计算今日";
      await loadLatestSnapshot().catch(() => {});
    }
    return load(false, { showBusy: !payload.latest });
  })
  .catch(() => {
    renderLocalHistory();
    return load(false);
  })
  .catch((error) => {
    els.actionBadge.className = "status no-trade";
    els.actionBadge.textContent = "失败";
    els.primaryBlock.innerHTML = `<p class="decision-copy">${escapeHtml(error.message)}</p>`;
  });

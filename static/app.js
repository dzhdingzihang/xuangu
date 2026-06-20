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
    const confidence = candidate ? candidate.recommendation_degree || candidate.confidence : 0;
    const range = candidate && (candidate.estimated_2w_range || candidate.estimated_2d_range);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `market-card ${key === activeMarket ? "active" : ""} ${actionClass(confidence, Boolean(primary))}`;
    if (primary) {
      button.innerHTML = `
        <div class="market-card-head">
          <strong>${escapeHtml(section.label || MARKET_LABELS[key])}</strong>
          <span class="pill ${actionClass(confidence, true)}">${recommendationLabel(confidence, true)}</span>
        </div>
        <div class="market-pick">
          <b>${escapeHtml(primary.name)} ${escapeHtml(primary.code)}</b>
          <em>推荐度 ${confidence}%</em>
        </div>
        <div class="market-price-grid">
          <span><small>建议买入</small>${priceText(primary.entry_price || primary.price)}</span>
          <span><small>止盈</small>${priceText(primary.take_profit_reference)}</span>
          <span><small>止损</small>${priceText(primary.stop_loss)}</span>
        </div>
        <p>${escapeHtml((range && range.text) || "--")}</p>
      `;
    } else {
      button.innerHTML = `
        <div class="market-card-head">
          <strong>${escapeHtml(section.label || MARKET_LABELS[key])}</strong>
          <span class="pill level-no">不买 / 无推荐</span>
        </div>
        <div class="no-trade-copy">
          <b>不买 / 无推荐</b>
          <span>${escapeHtml(decision.message || "当前没有符合策略的优质标的")}</span>
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
  const { decision } = selectedMarket(data);
  const primary = decision.primary;
  const blocked = decision.blocked_candidate;
  const shown = primary || blocked;
  const badgeConfidence = shown ? shown.recommendation_degree || shown.confidence || 0 : 0;
  els.actionBadge.className = `status ${actionClass(badgeConfidence, Boolean(primary))}`;
  els.actionBadge.textContent = primary ? recommendationLabel(primary.recommendation_degree || primary.confidence, true) : "不买";

  if (!shown) {
    els.primaryBlock.innerHTML = `
      <div class="primary-stock">
        <div class="stock-title">
          <strong>不买</strong>
          <span>没有可执行标的</span>
        </div>
        <p class="decision-copy">${escapeHtml(decision.message || "等待更强买点")}</p>
      </div>
    `;
    renderFactorStrip(null);
    renderMiniChart(null);
    return;
  }

  const confidence = shown.recommendation_degree || shown.confidence || 0;
  const range = shown.estimated_2w_range || shown.estimated_2d_range || {};
  els.primaryBlock.innerHTML = `
    <div class="primary-stock">
      <div class="action-layout">
        <div>
          <span class="decision-kicker">${primary ? "当前选中市场" : "被拦截候选"}</span>
          <div class="stock-title">
            <strong>${primary ? recommendationLabel(confidence, true) : "不买"}</strong>
            <span>${escapeHtml(shown.name)} ${escapeHtml(shown.code)}</span>
          </div>
        </div>
        <div class="decision-score ${confidenceTone(confidence)}">
          <span>推荐度</span>
          <strong>${confidence}%</strong>
        </div>
      </div>
      <p class="decision-copy">${escapeHtml(decision.message || "")}</p>
      <div class="price-row">
        <div class="price-cell"><span>建议买入价</span><strong>${priceText(shown.entry_price || shown.price)}</strong></div>
        <div class="price-cell"><span>预估收益</span><strong>${escapeHtml(range.text || "--")}</strong></div>
        <div class="price-cell"><span>止盈价</span><strong class="red">${priceText(shown.take_profit_reference)}</strong></div>
        <div class="price-cell"><span>止损价</span><strong class="green">${priceText(shown.stop_loss)}</strong></div>
      </div>
    </div>
  `;
  renderFactorStrip(shown);
  renderMiniChart(shown);
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
  const width = options.width || 340;
  const height = options.height || 210;
  const top = 22;
  const bottom = 42;
  const left = 22;
  const right = 16;
  const chartHeight = height - top - bottom;
  const highs = rows.map((row) => Number(row.high));
  const lows = rows.map((row) => Number(row.low));
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const span = Math.max(maxPrice - minPrice, 0.001);
  const step = (width - left - right) / rows.length;
  const candleWidth = Math.max(4, Math.min(9, step * 0.58));
  const y = (price) => top + ((maxPrice - price) / span) * chartHeight;
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
      </g>
      <g class="axis">${labels}</g>
      <g>${candles}</g>
      <text x="${left}" y="${height - 12}" class="date-label">${shortDate(first.date)}</text>
      <text x="${width - right - 38}" y="${height - 12}" class="date-label">${shortDate(last.date)}</text>
    </svg>
  `;
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
  const base = stock.entry_price || stock.price || 100;
  const change = stock.current_change_pct || stock.change_pct || 0;
  els.miniChart.innerHTML = `
    <div class="chart-head">
      <div>
        <strong>${escapeHtml(stock.name)} ${escapeHtml(stock.code)}</strong>
        <span>实时价 ${priceText(base)} · 真实日K</span>
      </div>
      <b class="${pctClass(change)}">${signed(change)}</b>
    </div>
    ${klineChartSvg(stock)}
  `;
}

function renderFactorStrip(primary) {
  clearList(els.factorStrip);
  if (!primary) return;
  const serenityAlpha = primary.serenity && primary.serenity.alpha_profile;
  const maxScores = {
    UZI评审: 60,
    UZI风控: 30,
    CZSC: 35,
    缠论: 60,
    Serenity: 120,
  };
  const factors = [
    ["UZI评审", primary.uzi_panel_score],
    ["UZI风控", primary.uzi_score],
    ["CZSC", primary.czsc_score],
    ["缠论", primary.chan_score],
    ["Serenity", primary.serenity_score || (primary.serenity && primary.serenity.score)],
  ];
  factors.forEach(([label, value]) => {
    const chip = document.createElement("span");
    const max = maxScores[label];
    chip.innerHTML = `<b>${escapeHtml(label)}</b>${typeof value === "number" ? `${value.toFixed(1)}/${max}` : `--/${max}`}`;
    els.factorStrip.append(chip);
  });
  if (serenityAlpha && serenityAlpha.rating && typeof serenityAlpha.score === "number") {
    const chip = document.createElement("span");
    chip.innerHTML = `<b>Serenity评级</b>${escapeHtml(serenityAlpha.rating)} / ${serenityAlpha.score}/100`;
    els.factorStrip.append(chip);
  }
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
    tr.innerHTML = `<td colspan="7" class="empty-cell">该市场暂无可展示候选。</td>`;
    els.candidateRows.append(tr);
    if (els.candidateDetail) {
      els.candidateDetail.innerHTML = `<div class="candidate-empty">当前市场没有候选详情。</div>`;
    }
    return;
  }
  if (!rows.some((row) => candidateKey(row) === selectedCandidateKey)) {
    selectedCandidateKey = candidateKey(rows[0]);
  }
  rows.forEach((row, index) => {
    const range = row.estimated_2w_range || row.estimated_2d_range || {};
    const confidence = row.recommendation_degree || row.confidence || 0;
    const reasons = (row.reasons || []).slice(0, 2).map((item) => escapeHtml(readableReason(item))).join("<br>");
    const risks = (row.risk_flags || []).slice(0, 2).map((item) => escapeHtml(readableRisk(item))).join("<br>") || "无硬风险";
    const tr = document.createElement("tr");
    tr.className = candidateKey(row) === selectedCandidateKey ? "selected-row" : "";
    tr.tabIndex = 0;
    tr.innerHTML = `
      <td>${index + 1}</td>
      <td><strong>${escapeHtml(row.name)}</strong><span class="muted">${escapeHtml(row.code)}</span></td>
      <td><span class="mini-action ${actionClass(confidence, true)}">${recommendationLabel(confidence, true)}</span><strong class="${confidenceTone(confidence)}">${confidence}%</strong></td>
      <td>${priceText(row.entry_price || row.price)}<br><span class="muted">止损 ${priceText(row.stop_loss)}</span></td>
      <td><span class="${pctClass((range.high_pct || 0))}">${escapeHtml(range.text || "--")}</span></td>
      <td><div class="table-note positive-note">${reasons || "暂无理由"}</div></td>
      <td><div class="table-note risk-note">${risks}</div></td>
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

function renderCandidateDetail(row, section) {
  if (!els.candidateDetail || !row) return;
  const confidence = row.recommendation_degree || row.confidence || 0;
  const range = row.estimated_2w_range || row.estimated_2d_range || {};
  const reasons = (row.reasons || []).slice(0, 5).map((item) => `<li>${escapeHtml(readableReason(item))}</li>`).join("");
  const risks = (row.risk_flags || []).slice(0, 5).map((item) => `<li>${escapeHtml(readableRisk(item))}</li>`).join("") || "<li>未触发硬风险，但仍需要按止损执行。</li>";
  const scoreItems = [
    ["UZI评审", row.uzi_panel_score, 60],
    ["UZI风控", row.uzi_score, 30],
    ["CZSC", row.czsc_score, 35],
    ["缠论", row.chan_score, 60],
    ["Serenity", row.serenity_score || (row.serenity && row.serenity.score), 120],
  ]
    .map(([label, value, max]) => `<span><b>${escapeHtml(label)}</b>${typeof value === "number" ? value.toFixed(1) : "--"}/${max}</span>`)
    .join("");
  els.candidateDetail.innerHTML = `
    <div class="candidate-detail-head">
      <div>
        <span class="label">${escapeHtml((section && section.label) || MARKET_LABELS[activeCandidateMarket] || "")} 候选详情</span>
        <h3>${escapeHtml(row.name)} ${escapeHtml(row.code)}</h3>
      </div>
      <span class="status ${actionClass(confidence, true)}">${recommendationLabel(confidence, true)} · ${confidence}%</span>
    </div>
    <div class="candidate-detail-grid">
      <div class="candidate-trade-box">
        <div><span>建议买入价</span><strong>${priceText(row.entry_price || row.price)}</strong></div>
        <div><span>止盈参考</span><strong class="red">${priceText(row.take_profit_reference)}</strong></div>
        <div><span>止损线</span><strong class="green">${priceText(row.stop_loss)}</strong></div>
        <div><span>两周预估</span><strong>${escapeHtml(range.text || "--")}</strong></div>
      </div>
      <div class="candidate-mini-chart">${klineChartSvg(row, { width: 430, height: 210 })}</div>
    </div>
    <div class="candidate-explain-grid">
      <section class="candidate-explain positive-note">
        <h4>为什么可能涨</h4>
        <ul>${reasons || "<li>暂无足够清晰的推荐理由。</li>"}</ul>
      </section>
      <section class="candidate-explain risk-note">
        <h4>哪里可能亏</h4>
        <ul>${risks}</ul>
      </section>
    </div>
    <div class="factor-strip candidate-score-strip">${scoreItems}</div>
  `;
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
  els.historyStatus.textContent = `${history.length} 条`;
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
      const button = document.createElement("button");
      button.type = "button";
      button.className = `history-snapshot ${item.target_date === currentTarget ? "active" : ""}`;
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
        const snapshotKey = item.cache_key || item.snapshot_key || item.local_key || `${item.target_date}_${item.signal_date}_${item.generated_at || ""}`;
        const localPick = readLocalHistory()[snapshotKey];
        if (localPick) {
          render(localPick);
          renderHistory(history, item.target_date);
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
  render(data);
  storeLocalPick(data);
  renderHistory(history.length ? history : mergeHistory([]), data.target_date);
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

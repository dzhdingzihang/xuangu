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
  factorStrip: document.getElementById("factorStrip"),
  miniChart: document.getElementById("miniChart"),
  marketBlock: document.getElementById("marketBlock"),
  industryBlock: document.getElementById("industryBlock"),
  marketTabs: document.getElementById("marketTabs"),
};

const LOCAL_HISTORY_KEY = "smart-stock-history-v2";
const MARKET_ORDER = ["a_share", "hk", "us"];
const MARKET_LABELS = { a_share: "A股", hk: "港股", us: "美股" };
let activeMarket = "a_share";
let activeCandidateMarket = "a_share";
let currentData = null;

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
  if (value >= 72) return "建议买入";
  if (value >= 62) return "谨慎买入";
  return "观察";
}

function confidenceTone(value) {
  if (value >= 70) return "strong";
  if (value >= 58) return "watch";
  return "weak";
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
    button.className = `market-card ${key === activeMarket ? "active" : ""} ${primary ? "buy-card" : "no-card"}`;
    if (primary) {
      button.innerHTML = `
        <div class="market-card-head">
          <strong>${escapeHtml(section.label || MARKET_LABELS[key])}</strong>
          <span class="pill buy">${recommendationLabel(confidence, true)}</span>
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
          <span class="pill no">无推荐</span>
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
  els.actionBadge.className = `status ${primary ? "buy" : "no-trade"}`;
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
  const points = [0.24, 0.43, 0.36, 0.52, 0.47, 0.66, 0.58, 0.72, 0.63, 0.78, 0.74, 0.82];
  const path = points.map((value, index) => `${index === 0 ? "M" : "L"} ${28 + index * 25} ${152 - value * 104}`).join(" ");
  const bars = points
    .map((value, index) => {
      const h = 18 + value * 34;
      return `<rect x="${28 + index * 25}" y="${180 - h}" width="9" height="${h}" rx="2"></rect>`;
    })
    .join("");
  els.miniChart.innerHTML = `
    <div class="chart-head">
      <div>
        <strong>${escapeHtml(stock.name)} ${escapeHtml(stock.code)}</strong>
        <span>实时价 ${priceText(base)}</span>
      </div>
      <b class="${pctClass(change)}">${signed(change)}</b>
    </div>
    <svg viewBox="0 0 340 210" role="img" aria-label="走势示意图">
      <g class="grid">
        <line x1="24" y1="50" x2="318" y2="50"></line>
        <line x1="24" y1="100" x2="318" y2="100"></line>
        <line x1="24" y1="150" x2="318" y2="150"></line>
      </g>
      <g class="bars">${bars}</g>
      <path class="chart-line" d="${path}"></path>
      <circle cx="303" cy="${152 - points[points.length - 1] * 104}" r="4"></circle>
    </svg>
  `;
}

function renderFactorStrip(primary) {
  clearList(els.factorStrip);
  if (!primary) return;
  const serenityAlpha = primary.serenity && primary.serenity.alpha_profile;
  const factors = [
    ["UZI评审", primary.uzi_panel_score],
    ["UZI风控", primary.uzi_score],
    ["CZSC", primary.czsc_score],
    ["缠论", primary.chan_score],
    ["Serenity", primary.serenity_score || (primary.serenity && primary.serenity.score)],
  ];
  factors.forEach(([label, value]) => {
    const chip = document.createElement("span");
    chip.innerHTML = `<b>${escapeHtml(label)}</b>${typeof value === "number" ? value.toFixed(1) : "--"}`;
    els.factorStrip.append(chip);
  });
  if (serenityAlpha && serenityAlpha.rating && typeof serenityAlpha.score === "number") {
    const chip = document.createElement("span");
    chip.innerHTML = `<b>Serenity评级</b>${escapeHtml(serenityAlpha.rating)} / ${serenityAlpha.score}`;
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
  (primary.reasons || []).slice(0, 6).forEach((reason) => els.reasons.append(li(reason)));
  if ((primary.risk_flags || []).length) {
    primary.risk_flags.slice(0, 6).forEach((flag) => els.riskList.append(li(flag)));
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
  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="7" class="empty-cell">该市场暂无可展示候选。</td>`;
    els.candidateRows.append(tr);
    return;
  }
  rows.forEach((row, index) => {
    const range = row.estimated_2w_range || row.estimated_2d_range || {};
    const reasons = (row.reasons || []).slice(0, 2).map(escapeHtml).join("<br>");
    const risks = (row.risk_flags || []).slice(0, 2).map(escapeHtml).join("<br>") || "无硬风险";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${index + 1}</td>
      <td><strong>${escapeHtml(row.name)}</strong><span class="muted">${escapeHtml(row.code)}</span></td>
      <td><strong class="${confidenceTone(row.recommendation_degree || row.confidence)}">${row.recommendation_degree || row.confidence}%</strong></td>
      <td>${priceText(row.entry_price || row.price)}<br><span class="muted">止损 ${priceText(row.stop_loss)}</span></td>
      <td><span class="${pctClass((range.high_pct || 0))}">${escapeHtml(range.text || "--")}</span></td>
      <td><div class="table-note positive-note">${reasons || "暂无理由"}</div></td>
      <td><div class="table-note risk-note">${risks}</div></td>
    `;
    els.candidateRows.append(tr);
  });
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
    const p = document.createElement("p");
    p.textContent = "行业接口暂不可用，不参与本次硬拦截。";
    els.industryBlock.append(p);
    return;
  }
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

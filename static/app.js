const els = {
  dateInput: document.getElementById("dateInput"),
  refreshBtn: document.getElementById("refreshBtn"),
  forceBtn: document.getElementById("forceBtn"),
  subtitle: document.getElementById("subtitle"),
  actionBadge: document.getElementById("actionBadge"),
  primaryBlock: document.getElementById("primaryBlock"),
  reasons: document.getElementById("reasons"),
  signalDate: document.getElementById("signalDate"),
  confidenceMetric: document.getElementById("confidenceMetric"),
  rangeMetric: document.getElementById("rangeMetric"),
  stopMetric: document.getElementById("stopMetric"),
  poolMetric: document.getElementById("poolMetric"),
  historyStatus: document.getElementById("historyStatus"),
  historyList: document.getElementById("historyList"),
  candidateRows: document.getElementById("candidateRows"),
  chanRules: document.getElementById("chanRules"),
  marketBlock: document.getElementById("marketBlock"),
  industryBlock: document.getElementById("industryBlock"),
  marketTabs: document.getElementById("marketTabs"),
};

const LOCAL_HISTORY_KEY = "smart-stock-history-v2";
const MARKET_ORDER = ["a_share", "hk", "us"];
let activeMarket = "a_share";
let currentData = null;

function todayText() {
  const d = new Date();
  const y = d.getFullYear();
  const m = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${day}`;
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

function clearList(node) {
  node.replaceChildren();
}

function li(text) {
  const item = document.createElement("li");
  item.textContent = text;
  return item;
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
  };
  if (primary) {
    summary.code = primary.code;
    summary.name = primary.name;
    summary.confidence = primary.recommendation_degree || primary.confidence;
    summary.recommendation_degree = primary.recommendation_degree || primary.confidence;
    const range = primary.estimated_2w_range || primary.estimated_2d_range;
    summary.estimated_2w_range = range && range.text;
    summary.estimated_2d_range = range && range.text;
    summary.score = primary.score;
    summary.reason_tags = primary.reason_tags;
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

function renderLocalHistory() {
  renderHistory(mergeHistory([]), els.dateInput.value);
}

function localSummaries() {
  return Object.entries(readLocalHistory())
    .map(([key, value]) => ({ ...summarizeClientPick(value), local_key: key }))
    .sort((a, b) => `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`));
}

function mergeHistory(serverRows) {
  const merged = new Map();
  (serverRows || []).forEach((item) => {
    merged.set(item.cache_key || `${item.target_date}_${item.signal_date}_${item.generated_at || ""}`, item);
  });
  localSummaries().forEach((item) => {
    const key = item.cache_key || item.local_key || `${item.target_date}_${item.signal_date}_${item.generated_at || ""}`;
    merged.set(key, { ...item, ...(merged.get(key) || {}) });
  });
  return [...merged.values()].sort((a, b) =>
    `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`),
  );
}

function renderPrimary(data) {
  const { decision } = selectedMarket(data);
  const primary = decision.primary;
  els.actionBadge.className = `status ${decision.action === "BUY_CANDIDATE" ? "buy" : "no-trade"}`;
  els.actionBadge.textContent = decision.title;

  if (!primary) {
    const blocked = decision.blocked_candidate;
    els.primaryBlock.innerHTML = `
      <div class="primary-stock">
        <div class="stock-title">
          <strong>无推荐</strong>
          <span>等待更强信号</span>
        </div>
        <p class="decision-copy">${decision.message}</p>
        ${
          blocked
            ? `<p class="decision-copy">最高分候选是 ${blocked.code} ${blocked.name}，但没有通过未来2周推荐阈值。</p>`
            : ""
        }
      </div>
    `;
    els.confidenceMetric.textContent = blocked ? `${blocked.recommendation_degree || blocked.confidence}%` : "--";
    els.rangeMetric.textContent = blocked ? (blocked.estimated_2w_range || blocked.estimated_2d_range).text : "--";
    els.stopMetric.textContent = "--";
    return;
  }

  els.primaryBlock.innerHTML = `
    <div class="primary-stock">
      <div class="stock-title">
        <strong>${primary.name}</strong>
        <span>${primary.code}</span>
      </div>
      <p class="decision-copy">${decision.message} ${data.holding_plan}</p>
      <div class="price-row">
        <div class="price-cell"><span>${primary.realtime ? primary.realtime.session_label : "实时"}买入价</span><strong>${priceText(primary.entry_price || primary.price)}</strong></div>
        <div class="price-cell"><span>实时涨跌</span><strong class="${pctClass(primary.current_change_pct ?? primary.change_pct)}">${signed(primary.current_change_pct ?? primary.change_pct)}</strong></div>
        <div class="price-cell"><span>止损</span><strong class="green">${priceText(primary.stop_loss)}</strong></div>
        <div class="price-cell"><span>参考止盈</span><strong class="red">${priceText(primary.take_profit_reference)}</strong></div>
      </div>
    </div>
  `;
  els.confidenceMetric.textContent = `${primary.recommendation_degree || primary.confidence}%`;
  els.rangeMetric.textContent = (primary.estimated_2w_range || primary.estimated_2d_range).text;
  els.stopMetric.textContent = priceText(primary.stop_loss);
}

function renderReasons(data) {
  clearList(els.reasons);
  const decision = selectedMarket(data).decision;
  const primary = decision.primary || decision.blocked_candidate;
  if (!primary) {
    els.reasons.append(li(decision.message));
    return;
  }
  primary.reasons.forEach((reason) => els.reasons.append(li(reason)));
  primary.risk_flags.forEach((flag) => els.reasons.append(li(`风险: ${flag}`)));
}

function renderTable(data) {
  const decision = selectedMarket(data).decision || {};
  const rows = [decision.primary, ...(decision.watchlist || [])].filter(Boolean);
  clearList(els.candidateRows);
  rows.forEach((row, index) => {
    const tr = document.createElement("tr");
    const risks = row.risk_flags.length
      ? row.risk_flags.map((risk) => `<span class="risk-tag">${risk}</span>`).join("")
      : '<span class="muted">无硬风险</span>';
    tr.innerHTML = `
      <td>${index + 1}</td>
      <td><strong>${row.name}</strong><span class="muted">${row.code}</span></td>
      <td>${row.score.toFixed(1)}<br><span class="muted">UZI评审 ${(row.uzi_panel_score || 0).toFixed(1)} / 风控 ${(row.uzi_score || 0).toFixed(1)} / 缠 ${row.chan_score.toFixed(1)} / CZ ${(row.czsc_score || 0).toFixed(1)} / S ${(row.serenity_score || (row.serenity && row.serenity.score) || 0).toFixed(1)}</span></td>
      <td>${row.recommendation_degree || row.confidence}%</td>
      <td>${(row.estimated_2w_range || row.estimated_2d_range).text}</td>
      <td>${priceText(row.entry_price || row.price)}<br><span class="muted">${row.realtime ? row.realtime.session_label : "实时"} ${signed(row.current_change_pct ?? row.change_pct)} · ${row.amount_yi ? `${row.amount_yi.toFixed(1)} 亿` : "见行情"}</span></td>
      <td><div class="tagline">${row.role || row.reason_tags || "无题材标签"}</div></td>
      <td><div class="risk-tags">${risks}</div></td>
    `;
    els.candidateRows.append(tr);
  });
}

function renderRules(data) {
  clearList(els.chanRules);
  ((data.uzi_rules && data.uzi_rules.principles) || []).forEach((rule) => els.chanRules.append(li(`UZI: ${rule}`)));
  data.chan_rules.quant_mapping.forEach((rule) => els.chanRules.append(li(rule)));
  ((data.czsc_rules && data.czsc_rules.principles) || []).forEach((rule) => els.chanRules.append(li(`CZSC: ${rule}`)));
  ((data.serenity_rules && data.serenity_rules.principles) || []).forEach((rule) => els.chanRules.append(li(`Serenity: ${rule}`)));
  if (data.serenity_source) {
    const source = data.serenity_source;
    const span = source.tweet_archive_span ? `，档案 ${source.tweet_archive_span}` : "";
    els.chanRules.append(li(`Serenity源: ${source.repo} 最新提交 ${source.latest_commit || "未知"}${span}`));
  }
}

function renderMarket(data) {
  clearList(els.marketBlock);
  const note = document.createElement("p");
  note.textContent = data.market.risk_note || "指数环境未知";
  els.marketBlock.append(note);
  (data.market.items || []).forEach((item) => {
    const row = document.createElement("div");
    row.className = "market-row";
    row.innerHTML = `<span>${item.name}</span><strong class="${pctClass(item.change_pct)}">${signed(item.change_pct)}</strong>`;
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
    row.innerHTML = `<span>${item.name}</span><strong class="${pctClass(item.change_pct)}">${signed(item.change_pct)}</strong>`;
    els.industryBlock.append(row);
  });
}

function render(data) {
  currentData = data;
  if (!data.markets || !data.markets[activeMarket]) activeMarket = "a_share";
  const section = selectedMarket(data);
  els.subtitle.textContent = `${data.target_date} 推荐，基于 ${data.signal_date} 数据；观察到 ${data.forecast_end_date || data.next_trade_date}（${data.forecast_horizon || "约2周"}）`;
  els.signalDate.textContent = `${section.label || "A股"} · ${data.generated_label || data.generated_at || ""}`;
  els.poolMetric.textContent = `${section.stats.raw_pool_size}/${section.stats.scored_size}`;
  renderMarketTabs(data);
  renderPrimary(data);
  renderReasons(data);
  renderTable(data);
  renderRules(data);
  renderMarket(data);
  renderIndustry(data);
}

function selectedMarket(data) {
  if (!data.markets) {
    return { key: "a_share", label: "A股", decision: data.decision, stats: data.stats || {}, description: "" };
  }
  return data.markets[activeMarket] || data.markets.a_share;
}

function renderMarketTabs(data) {
  clearList(els.marketTabs);
  const markets = data.markets || { a_share: selectedMarket(data) };
  MARKET_ORDER.filter((key) => markets[key]).forEach((key) => {
    const section = markets[key];
    const decision = section.decision || {};
    const primary = decision.primary || decision.blocked_candidate;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `market-tab ${key === activeMarket ? "active" : ""}`;
    button.innerHTML = `
      <span class="tab-head">
        <strong>${section.label}</strong>
        <b class="${decision.action === "BUY_CANDIDATE" ? "red" : "muted"}">${decision.title || "--"}</b>
      </span>
      <span>${primary ? `${primary.name} ${primary.code}` : "无推荐"}</span>
      <small>${section.description || ""}</small>
      <span class="tab-foot">
        <em>推荐度 ${primary ? `${primary.recommendation_degree || primary.confidence}%` : "--"}</em>
        <em>${primary ? ((primary.estimated_2w_range || primary.estimated_2d_range || {}).text || "--") : "--"}</em>
      </span>
    `;
    button.addEventListener("click", () => {
      activeMarket = key;
      render(data);
    });
    els.marketTabs.append(button);
  });
}

function historyTitle(item) {
  if (!item) return "暂无历史记录";
  if (!item.has_primary) return `${item.target_date} 无推荐`;
  return `${item.target_date} ${item.name} ${item.code}`;
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
  history.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-item ${item.target_date === currentTarget ? "active" : ""}`;
    button.innerHTML = `
      <span>
        <strong>${historyTitle(item)}</strong>
        <small>${item.title || "--"} · ${item.generated_label || item.generated_at || item.signal_date || "--"} · ${item.model_version || "--"}</small>
      </span>
      <span class="history-meta">
        <b>${item.recommendation_degree || item.confidence ? `${item.recommendation_degree || item.confidence}%` : "--"}</b>
        <small>${item.estimated_2w_range || item.estimated_2d_range || item.message || "--"}</small>
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
    els.historyList.append(button);
  });
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
  els.actionBadge.textContent = `${data.decision.title} · 历史缓存`;
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
  if (!response.ok) {
    throw new Error(data.error || "数据源暂不可用");
  }
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
    if (cachedRequested) {
      return load(false, { showBusy: false });
    }
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
    els.primaryBlock.innerHTML = `<p class="decision-copy">${error.message}</p>`;
  });

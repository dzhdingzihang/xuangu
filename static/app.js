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
};

const LOCAL_HISTORY_KEY = "chan-stock-history-v1";

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
    action: decision.action,
    title: decision.title,
    message: decision.message,
    has_primary: Boolean(decision.primary),
    local_key: `${data.target_date}_${data.signal_date}`,
  };
  if (primary) {
    summary.code = primary.code;
    summary.name = primary.name;
    summary.confidence = primary.confidence;
    summary.estimated_2d_range = primary.estimated_2d_range && primary.estimated_2d_range.text;
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
  history[`${data.target_date}_${data.signal_date}`] = data;
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
    merged.set(`${item.target_date}_${item.signal_date}`, item);
  });
  localSummaries().forEach((item) => {
    const key = `${item.target_date}_${item.signal_date}`;
    merged.set(key, { ...item, ...(merged.get(key) || {}) });
  });
  return [...merged.values()].sort((a, b) =>
    `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`),
  );
}

function renderPrimary(data) {
  const { decision } = data;
  const primary = decision.primary;
  els.actionBadge.className = `status ${decision.action === "BUY_CANDIDATE" ? "buy" : "no-trade"}`;
  els.actionBadge.textContent = decision.title;

  if (!primary) {
    const blocked = decision.blocked_candidate;
    els.primaryBlock.innerHTML = `
      <div class="primary-stock">
        <div class="stock-title">
          <strong>今日不交易</strong>
          <span>空仓优先</span>
        </div>
        <p class="decision-copy">${decision.message}</p>
        ${
          blocked
            ? `<p class="decision-copy">最高分候选是 ${blocked.code} ${blocked.name}，但没有通过风控阈值。</p>`
            : ""
        }
      </div>
    `;
    els.confidenceMetric.textContent = blocked ? `${blocked.confidence}%` : "--";
    els.rangeMetric.textContent = blocked ? blocked.estimated_2d_range.text : "--";
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
        <div class="price-cell"><span>收盘价</span><strong>${primary.price.toFixed(2)}</strong></div>
        <div class="price-cell"><span>信号日涨跌</span><strong class="${pctClass(primary.change_pct)}">${signed(primary.change_pct)}</strong></div>
        <div class="price-cell"><span>止损</span><strong class="green">${primary.stop_loss.toFixed(2)}</strong></div>
        <div class="price-cell"><span>参考止盈</span><strong class="red">${primary.take_profit_reference.toFixed(2)}</strong></div>
      </div>
    </div>
  `;
  els.confidenceMetric.textContent = `${primary.confidence}%`;
  els.rangeMetric.textContent = primary.estimated_2d_range.text;
  els.stopMetric.textContent = primary.stop_loss.toFixed(2);
}

function renderReasons(data) {
  clearList(els.reasons);
  const primary = data.decision.primary || data.decision.blocked_candidate;
  if (!primary) {
    els.reasons.append(li(data.decision.message));
    return;
  }
  primary.reasons.forEach((reason) => els.reasons.append(li(reason)));
  primary.risk_flags.forEach((flag) => els.reasons.append(li(`风险: ${flag}`)));
}

function renderTable(data) {
  const rows = [data.decision.primary, ...(data.decision.watchlist || [])].filter(Boolean);
  clearList(els.candidateRows);
  rows.forEach((row, index) => {
    const tr = document.createElement("tr");
    const risks = row.risk_flags.length
      ? row.risk_flags.map((risk) => `<span class="risk-tag">${risk}</span>`).join("")
      : '<span class="muted">无硬风险</span>';
    tr.innerHTML = `
      <td>${index + 1}</td>
      <td><strong>${row.name}</strong><span class="muted">${row.code}</span></td>
      <td>${row.score.toFixed(1)}<br><span class="muted">缠 ${row.chan_score.toFixed(1)}</span></td>
      <td>${row.confidence}%</td>
      <td>${row.estimated_2d_range.text}</td>
      <td>${row.amount_yi.toFixed(1)} 亿<br><span class="muted">换手 ${row.turnover_pct.toFixed(1)}%</span></td>
      <td><div class="tagline">${row.reason_tags || "无题材标签"}</div></td>
      <td><div class="risk-tags">${risks}</div></td>
    `;
    els.candidateRows.append(tr);
  });
}

function renderRules(data) {
  clearList(els.chanRules);
  data.chan_rules.quant_mapping.forEach((rule) => els.chanRules.append(li(rule)));
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
  els.subtitle.textContent = `${data.target_date} 开盘计划，基于 ${data.signal_date} 收盘数据；持有窗口到 ${data.next_trade_date}`;
  els.signalDate.textContent = `信号日 ${data.signal_date}`;
  els.poolMetric.textContent = `${data.stats.hot_pool_size}/${data.stats.scored_size}`;
  renderPrimary(data);
  renderReasons(data);
  renderTable(data);
  renderRules(data);
  renderMarket(data);
  renderIndustry(data);
}

function historyTitle(item) {
  if (!item) return "暂无历史记录";
  if (!item.has_primary) return `${item.target_date} 空仓`;
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
        <small>${item.title || "--"} · 信号日 ${item.signal_date || "--"} · ${item.model_version || "--"}</small>
      </span>
      <span class="history-meta">
        <b>${item.confidence ? `${item.confidence}%` : "--"}</b>
        <small>${item.estimated_2d_range || item.message || "--"}</small>
      </span>
    `;
    button.addEventListener("click", async () => {
      els.dateInput.value = item.target_date;
      const localPick = readLocalHistory()[`${item.target_date}_${item.signal_date}`];
      if (localPick) {
        render(localPick);
        renderHistory(history, item.target_date);
        return;
      }
      await load(false, { showBusy: false });
    });
    els.historyList.append(button);
  });
}

async function loadHistory() {
  const response = await fetch("/api/history?limit=45");
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
    const today = els.dateInput.value;
    const cachedToday = (payload.history || []).some((item) => item.target_date === today);
    if (cachedToday) {
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

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
  candidateRows: document.getElementById("candidateRows"),
  chanRules: document.getElementById("chanRules"),
  marketBlock: document.getElementById("marketBlock"),
  industryBlock: document.getElementById("industryBlock"),
};

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
        <div class="price-cell"><span>5/25涨跌</span><strong class="${pctClass(primary.change_pct)}">${signed(primary.change_pct)}</strong></div>
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

async function load(force = false) {
  els.actionBadge.className = "status";
  els.actionBadge.textContent = "计算中";
  const params = new URLSearchParams();
  if (els.dateInput.value) params.set("date", els.dateInput.value);
  if (force) params.set("force", "1");
  const response = await fetch(`/api/pick?${params.toString()}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "数据源暂不可用");
  }
  render(data);
}

els.dateInput.value = todayText();
els.refreshBtn.addEventListener("click", () => load(false).catch(alert));
els.forceBtn.addEventListener("click", () => load(true).catch(alert));
load(false).catch((error) => {
  els.actionBadge.className = "status no-trade";
  els.actionBadge.textContent = "失败";
  els.primaryBlock.innerHTML = `<p class="decision-copy">${error.message}</p>`;
});

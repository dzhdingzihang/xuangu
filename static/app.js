const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const MARKET_ORDER = ["a_share", "hk", "us"];
const MARKET_META = {
  a_share: { label: "A股", short: "A", currency: "CNY", dot: "market-a" },
  hk: { label: "港股", short: "港", currency: "HKD", dot: "market-hk" },
  us: { label: "美股", short: "美", currency: "USD", dot: "market-us" },
};
const TAB_META = {
  decision: ["决策", "今日跨市场执行建议"],
  candidates: ["候选", "Legacy 决策、V2 影子与双低价值筛选"],
  events: ["事件", "三市场事件证据与模型信号"],
  history: ["历史", "不可变决策快照与复盘入口"],
  model: ["模型说明", "候选池、评分、门控与运行机制"],
};
const FACTOR_META = {
  event: ["事件", "ph-bell-ringing"],
  technical: ["技术结构", "ph-chart-line-up"],
  industry: ["产业链", "ph-factory"],
  liquidity_flow: ["流动性 / 资金", "ph-waves"],
  quality: ["质量 / 风险", "ph-shield-check"],
};
const DUAL_LOW_FACTOR_META = {
  value: ["估值", "PE / PB 横截面"],
  stability: ["稳定性", "涨跌、活跃度与异常风险"],
  liquidity: ["流动性", "成交额横截面"],
  momentum: ["动量", "温和趋势，不过热"],
  activity: ["活跃度", "量比与换手适中"],
  reversal: ["反转", "可控回调线索"],
  size: ["规模", "总市值横截面"],
};
const DUAL_LOW_REASON_META = {
  "filter.peRatio.max": "PE TTM 高于上限",
  "filter.peRatio.min": "PE TTM 低于下限",
  "filter.pbRatio.max": "PB 高于上限",
  "filter.pbRatio.min": "PB 低于下限",
  "filter.changePct.max": "当日涨幅过热",
  "filter.changePct.min": "当日跌幅过大",
  "filter.totalMarketCap.min": "总市值低于下限",
  "filter.totalMarketCap.max": "总市值高于上限",
  "filter.price.max": "股价高于上限",
  "filter.amount.min": "成交额低于下限",
  "validation.peRatio.invalid": "PE TTM 数据缺失",
  "validation.pbRatio.invalid": "PB 数据缺失",
  "validation.totalMarketCap.invalid": "总市值数据缺失",
};
const DUAL_LOW_RISK_META = { low: "低", medium: "中", high: "高" };
const DUAL_LOW_INPUT_META = {
  quote_valuation_core_v1: "实时行情 + PE / PB / 总市值核心字段",
};

const state = {
  tab: "decision",
  market: "a_share",
  snapshot: null,
  history: [],
  status: null,
  live: new Map(),
  liveLoading: new Set(),
  candidateKey: "",
  candidateFilters: { market: "all", risk: "all", route: "all", query: "" },
  eventKey: "",
  eventFilters: { market: "all", type: "all", direction: "all", query: "" },
  historyKey: "",
  historyMarket: "a_share",
  historyAction: "all",
  historyQuery: "",
  historySnapshot: null,
  compare: [],
};

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function num(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clamp(value, min = 0, max = 100) {
  return Math.max(min, Math.min(max, num(value)));
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "--";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

function price(value) {
  if (!Number.isFinite(Number(value))) return "--";
  const v = Number(value);
  return v >= 100 ? v.toFixed(2) : v.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function pct(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return "--";
  const v = Number(value);
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function toneFor(value) {
  if (num(value) > 0) return "positive";
  if (num(value) < 0) return "negative";
  return "muted";
}

function dateTime(value, includeDate = true) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).replace("T", " ").slice(0, includeDate ? 16 : 5);
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: includeDate ? "2-digit" : undefined,
    day: includeDate ? "2-digit" : undefined,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed).replaceAll("/", "-");
}

function safeHttpUrl(value) {
  try {
    const parsed = new URL(String(value || ""), location.origin);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : "";
  } catch {
    return "";
  }
}

function normalizedDirection(value) {
  return value === "positive" || value === "negative" ? value : "neutral";
}

function marketSection(snapshot, market = state.market) {
  if (!snapshot) return {};
  if (snapshot.markets?.[market]) return snapshot.markets[market];
  return market === "a_share" ? { decision: snapshot.decision || {}, stats: snapshot.stats || {} } : {};
}

function marketDecision(snapshot, market = state.market) {
  return marketSection(snapshot, market).decision || {};
}

function currentCandidate(decision) {
  return decision.primary || decision.blocked_candidate || (decision.watchlist || [])[0] || null;
}

function candidateId(candidate, market) {
  return `${market}:${candidate?.code || candidate?.symbol || candidate?.name || "unknown"}`;
}

function candidatesFor(snapshot, market) {
  const decision = marketDecision(snapshot, market);
  const rows = [decision.primary, decision.blocked_candidate, ...(decision.watchlist || [])].filter(Boolean);
  const seen = new Set();
  return rows.filter((row) => {
    const key = candidateId(row, market);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function candidateDecisionRole(candidate, market) {
  const decision = marketDecision(state.snapshot, market);
  const key = candidateId(candidate, market);
  if (decision.primary && candidateId(decision.primary, market) === key) return "primary";
  if (decision.blocked_candidate && candidateId(decision.blocked_candidate, market) === key) return "blocked";
  return "watchlist";
}

function decisionRoleLabel(role) {
  return ({ primary: "当前首选", blocked: "门槛未过", watchlist: "观察候选" })[role] || "观察候选";
}

function allCandidates() {
  return MARKET_ORDER.flatMap((market) => candidatesFor(state.snapshot, market).map((candidate, index) => ({
    candidate,
    market,
    legacyRank: index + 1,
    decisionRole: candidateDecisionRole(candidate, market),
  })));
}

function candidateScore(candidate) {
  const value = candidate?.recommendation_degree ?? candidate?.confidence;
  return value === null || value === undefined || value === "" ? NaN : num(value, NaN);
}

function candidatePrice(candidate) {
  const live = state.live.get(candidateId(candidate, candidate?.market_key || state.market));
  return num(live?.price || live?.current_price || candidate?.current_price || candidate?.realtime?.price || candidate?.entry_price || candidate?.price, NaN);
}

function liveMerged(candidate, market) {
  const live = state.live.get(candidateId(candidate, market));
  if (!live) return candidate;
  return {
    ...candidate,
    current_price: live.current_price ?? live.price ?? candidate.current_price,
    current_change_pct: live.current_change_pct ?? live.change_pct ?? candidate.current_change_pct,
    realtime: { ...(candidate.realtime || {}), ...live },
    kline: Array.isArray(live.kline) && live.kline.length ? live.kline : candidate.kline,
  };
}

function routeList(candidate) {
  return candidate?.candidate_lineage?.recall_routes || [];
}

function routeNames(candidate) {
  const names = routeList(candidate).map((item) => item.route).filter(Boolean);
  if (!names.length && candidate?.candidate_lineage?.universe_origin) names.push(candidate.candidate_lineage.universe_origin);
  return [...new Set(names)];
}

function riskLevel(candidate) {
  if ((candidate?.decision_gates || []).some((gate) => gate.status === "BLOCK") || candidate?.execution_state === "BLOCKED") return "blocked";
  if ((candidate?.risk_items || []).length || (candidate?.risk_flags || []).length || (candidate?.decision_gates || []).some((gate) => gate.status === "WARN")) return "warning";
  return "clear";
}

function labelForRegime(regime) {
  const stateName = typeof regime === "string" ? regime : regime?.state;
  return ({ trend_risk_on: "趋势偏多", range: "区间震荡", high_vol: "高波动", risk_off: "风险规避", unknown: "证据不足" })[stateName] || "证据不足";
}

function actionLabel(decision) {
  if (decision?.primary) return "BUY CANDIDATE";
  if (decision?.blocked_candidate) return "NO TRADE";
  return String(decision?.action || "NO SIGNAL").replaceAll("_", " ");
}

function recommendationLabel(candidate, hasPrimary = true) {
  if (!hasPrimary) return "暂不执行";
  const score = candidateScore(candidate);
  if (score >= 72) return "推荐买入";
  if (score >= 62) return "谨慎买入";
  return "观察";
}

function executionAdvice(candidate, hasPrimary) {
  if (!candidate || !hasPrimary) return { tone: "negative", label: "不买", text: "本轮门槛未通过，保留现金并等待下一份不可变快照。", deviation: null };
  if (candidate.execution_state === "BLOCKED" || (candidate.decision_gates || []).some((gate) => gate.status === "BLOCK")) {
    return { tone: "negative", label: "暂不执行", text: "候选虽通过 Legacy 排名，但 V2 客观门控发现不可执行条件；先修复行情、K线或交易状态证据。", deviation: null };
  }
  const current = candidatePrice(candidate);
  const entry = num(candidate.entry_price || candidate.price, NaN);
  const stop = num(candidate.stop_loss, NaN);
  const take = num(candidate.take_profit_reference, NaN);
  const deviation = Number.isFinite(entry) && Number.isFinite(current) ? ((current - entry) / entry) * 100 : null;
  if (Number.isFinite(stop) && current <= stop) return { tone: "negative", label: "取消买入", text: "当前价已触及止损区，走势没有按原计划兑现。", deviation };
  if (Number.isFinite(take) && current >= take * 0.98) return { tone: "warning", label: "不追高", text: "当前价已接近止盈参考，继续追买的盈亏比不足。", deviation };
  if (Number.isFinite(entry) && current > entry * 1.03) return { tone: "warning", label: "等回落", text: "当前价高于快照建议价 3% 以上，等待回到计划区。", deviation };
  if (Number.isFinite(entry) && current >= entry * 0.985 && current <= entry * 1.01) return { tone: "positive", label: "可按计划买", text: "当前价仍在建议买入区附近，止损与目标位可执行。", deviation };
  return { tone: "warning", label: "谨慎买入", text: "实时价偏离计划区，适合小仓位或等待价格回归。", deviation };
}

function icon(name) {
  return `<i class="ph ${esc(name)}" aria-hidden="true"></i>`;
}

function badge(text, tone = "") {
  return `<span class="badge ${esc(tone)}">${esc(text)}</span>`;
}

function marketBadge(market) {
  const meta = MARKET_META[market] || MARKET_META.a_share;
  return `<span class="market-dot ${meta.dot}">${meta.short}</span>`;
}

function showToast(message, type = "info") {
  const region = $("#toastRegion");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `${icon(type === "error" ? "ph-warning-circle" : type === "success" ? "ph-check-circle" : "ph-info")}<span>${esc(message)}</span>`;
  region.append(toast);
  window.setTimeout(() => toast.remove(), 3600);
}

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store", headers: { accept: "application/json" } });
  let payload;
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.error || `请求失败 ${response.status}`);
  return payload;
}

function marketSwitch(action = "market") {
  return `<div class="segmented-button" role="group" aria-label="选择市场">
    ${MARKET_ORDER.map((market) => `<button type="button" data-action="${action}" data-market="${market}" aria-pressed="${state.market === market}">${MARKET_META[market].label}</button>`).join("")}
  </div>`;
}

function renderRail() {
  const root = $("#railMarketStatus");
  if (!state.snapshot) return;
  root.innerHTML = MARKET_ORDER.map((market) => {
    const section = marketSection(state.snapshot, market);
    const decision = section.decision || {};
    const candidate = currentCandidate(decision);
    const label = decision.primary ? `${candidate?.name || "有候选"} · ${candidateScore(candidate)}` : "本轮不交易";
    return `<button class="rail-market-row" type="button" data-action="market" data-market="${market}" title="切换到${MARKET_META[market].label}">
      ${marketBadge(market)}<span><b>${MARKET_META[market].label}</b><small>${esc(label)}</small></span>
    </button>`;
  }).join("");
}

function updateTopbar() {
  const [title, subtitle] = TAB_META[state.tab];
  $("#pageTitle").textContent = title;
  $("#pageSubtitle").textContent = subtitle;
  $("#snapshotTime").textContent = dateTime(state.snapshot?.generated_at);
  const health = $("#healthBadge");
  const healthy = Boolean(state.snapshot && state.status?.ok !== false);
  health.className = `health-badge ${healthy ? "" : "is-error"}`;
  health.innerHTML = `${icon(healthy ? "ph-check" : "ph-warning")}${healthy ? "数据正常" : "数据异常"}`;
}

function switchTab(tab, writeHash = true) {
  if (!TAB_META[tab]) tab = "decision";
  state.tab = tab;
  $$(".nav-item").forEach((button) => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $$(".tab-panel").forEach((panel) => {
    const active = panel.dataset.tab === tab;
    panel.hidden = !active;
    panel.classList.toggle("is-active", active);
  });
  if (writeHash && location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  updateTopbar();
  renderActiveTab();
}

function renderKpis(items) {
  return `<div class="kpi-grid">${items.map((item) => `<article class="kpi-card">
    <div class="kpi-label">${icon(item.icon || "ph-chart-bar")}${esc(item.label)}</div>
    <div class="kpi-value ${esc(item.tone || "")}">${esc(item.value)}</div>
    <div class="kpi-meta">${item.meta === undefined ? "&nbsp;" : esc(item.meta)}</div>
  </article>`).join("")}</div>`;
}

function factorCards(candidate) {
  const groups = candidate?.v2?.factor_groups;
  if (!groups) {
    const legacy = [
      ["初筛", candidate?.pre_score, 100], ["缠论", candidate?.chan_score, 60], ["CZSC", candidate?.czsc_score, 30],
      ["Serenity", candidate?.serenity_score, 30], ["UZI", candidate?.uzi_score, 20], ["评审团", candidate?.uzi_panel_score, 100],
    ];
    return `<div class="callout">${icon("ph-clock-countdown")}<div><strong>Legacy 正在执行</strong><br>新 V2 分组将在下一次 GitHub Actions 快照生成后出现；旧因子和原决策均保留。</div></div>
      <div class="factor-grid legacy-factor-grid">${legacy.map(([name, value, max]) => `<dl class="factor-card"><dt>${esc(name)}旧评分</dt><dd>${fmt(value, 1)} / ${max}</dd><div class="progress-bar"><span style="width:${clamp(num(value) / max * 100)}%"></span></div></dl>`).join("")}</div>`;
  }
  return `<div class="factor-grid">${Object.entries(groups).map(([key, group]) => {
    const [label, iconName] = FACTOR_META[key] || [key, "ph-cube"];
    return `<dl class="factor-card"><dt>${icon(iconName)} ${esc(label)} · 权重 ${fmt(num(group.weight) * 100, 0)}%</dt><dd>${fmt(group.score, 1)} <small>贡献 ${fmt(group.contribution, 1)}</small></dd><div class="progress-bar"><span style="width:${clamp(group.score)}%"></span></div></dl>`;
  }).join("")}</div>`;
}

function dualLowAnalysis(candidate) {
  return candidate?.analysis_projects?.dual_low || null;
}

function dualLowLabel(analysis) {
  if (!analysis) return "待生成";
  if (analysis.status === "ranked") return analysis.interpretation || "双低观察";
  if (analysis.status === "rejected") return analysis.interpretation || ((analysis.missing_fields || []).length ? "数据不足" : "非双低风格");
  if (analysis.status === "not_applicable") return "暂不适用";
  return "数据不足";
}

function dualLowTone(analysis) {
  if (analysis?.status === "ranked" && num(analysis.rank_percentile) >= 0.8) return "positive";
  if (analysis?.status === "ranked") return "primary";
  if (analysis?.status === "rejected" && !(analysis.missing_fields || []).length) return "warning";
  return "muted";
}

function dualLowReasonLabel(code) {
  return DUAL_LOW_REASON_META[code] || code || "其他过滤条件";
}

function topPercent(rank, universe) {
  const position = num(rank, NaN);
  const size = num(universe, NaN);
  return Number.isFinite(position) && Number.isFinite(size) && size > 0 ? Math.max(1, Math.ceil(position / size * 100)) : null;
}

function scoreLensCards(candidate, market) {
  const dualLow = dualLowAnalysis(candidate);
  const quality = candidate?.data_quality;
  const row = allCandidates().find((item) => candidateId(item.candidate, item.market) === candidateId(candidate, market));
  const role = row?.decisionRole || candidateDecisionRole(candidate, market);
  const legacyAction = role === "primary" ? recommendationLabel(candidate, true) : role === "blocked" ? "暂不执行" : "观察候选";
  const v2Top = topPercent(candidate?.v2?.rank, candidate?.v2?.rank_universe_size);
  const dualTop = topPercent(dualLow?.rank, dualLow?.rank_universe_size);
  const gates = candidate?.decision_gates || [];
  const blocked = gates.filter((gate) => gate.status === "BLOCK").length;
  const warned = gates.filter((gate) => gate.status === "WARN").length;
  const passed = gates.filter((gate) => gate.status === "PASS").length;
  const evidenceStatus = blocked ? "BLOCK" : warned ? "WARN" : gates.length ? "PASS" : "待生成";
  const dualValue = dualLow?.status === "ranked" ? `前 ${dualTop || "--"}%` : dualLowLabel(dualLow);
  const dualMeta = dualLow?.status === "ranked"
    ? `${fmt(dualLow.final_score, 1)} 分 · #${dualLow.rank || "--"}/${dualLow.rank_universe_size || "--"}`
    : dualLow?.status === "rejected"
      ? `${(dualLow.filter_reasons || []).length} 项未通过`
      : market === "a_share" ? "等待新快照" : "首版仅支持 A 股";
  const lenses = [
    {
      key: "legacy", icon: "ph-seal-check", label: "实际决策", value: legacyAction,
      meta: `推荐度 ${fmt(candidateScore(candidate), 0)}/100 · Legacy #${row?.legacyRank || "--"}`,
      note: role === "primary" ? "当前实际首选，仍需服从门控和计划价" : role === "blocked" ? "最接近阈值，但当前不执行" : "保留观察，不代表买入信号",
      tone: role === "primary" ? "active" : role === "blocked" ? "warning" : "muted",
    },
    {
      key: "v2", icon: "ph-ranking", label: "影子排序", value: candidate?.v2?.rank ? `前 ${v2Top || "--"}%` : "待生成",
      meta: candidate?.v2?.rank ? `${fmt(candidate.v2.rule_score, 1)} 分 · #${candidate.v2.rank}/${candidate.v2.rank_universe_size || "--"}` : "去重规则分",
      note: "解释因子表现，不改变旧决策", tone: "shadow",
    },
    {
      key: "dual-low", icon: "ph-scales", label: "价值筛选", value: dualValue,
      meta: dualMeta, note: "A 股双低研究优先级，独立观察", tone: dualLowTone(dualLow),
    },
    {
      key: "quality", icon: "ph-database", label: "证据与门控", value: evidenceStatus,
      meta: quality ? `完整度 ${fmt(quality.score, 0)}% · ${passed}/${gates.length} PASS` : "旧快照 · 待生成",
      note: "缺失项不会伪装成真实零值", tone: blocked ? "negative" : warned ? "warning" : gates.length ? "positive" : "muted",
    },
  ];
  return `<div class="score-lens-grid">${lenses.map((lens) => `<article class="score-lens ${esc(lens.tone)}" data-score-lens="${esc(lens.key)}">
    <div class="score-lens-head">${icon(lens.icon)}<span>${esc(lens.label)}</span></div>
    <strong>${esc(lens.value)}</strong><small>${esc(lens.meta)}</small><p>${esc(lens.note)}</p>
  </article>`).join("")}</div>`;
}

function scoreDivergence(candidate, market) {
  const dualLow = dualLowAnalysis(candidate);
  const role = candidateDecisionRole(candidate, market);
  const v2Top = topPercent(candidate?.v2?.rank, candidate?.v2?.rank_universe_size);
  if (role === "primary" && dualLow?.status === "rejected") {
    const reason = dualLow.filter_reasons?.[0]?.message;
    return `<div class="callout warning score-divergence">${icon("ph-arrows-left-right")}<div><strong>风格分歧，不是模型冲突</strong><br>Legacy 把它列为当前首选，但双低模型认为它不属于低估值风格${reason ? `：${esc(reason)}` : ""}。实际决策仍由 Legacy 与客观门控决定。</div></div>`;
  }
  if (role === "blocked" && dualLow?.status === "ranked") {
    return `<div class="callout warning score-divergence">${icon("ph-shield-warning")}<div><strong>价值靠前，不等于现在能买</strong><br>双低研究排名较高，但 Legacy 或客观门控尚未通过；继续观察，不把价值分当交易指令。</div></div>`;
  }
  if (role === "primary" && dualLow?.status === "ranked" && v2Top !== null && v2Top <= 25) {
    return `<div class="callout score-divergence">${icon("ph-check-circle")}<div><strong>多视角一致</strong><br>Legacy 当前首选，V2 结构位于前 25%，同时进入双低研究序列；三套结果仍保持独立，不合成为上涨概率。</div></div>`;
  }
  return `<div class="callout score-divergence">${icon("ph-info")}<div><strong>如何阅读三套结果</strong><br>Legacy 回答“当前怎么做”，V2 回答“结构质量如何”，双低回答“是否属于低估值风格”。</div></div>`;
}

function dualLowPanel(candidate, market) {
  const analysis = dualLowAnalysis(candidate);
  const title = "独立分析项目 · 双低七因子";
  const disclaimer = "研究优先级，不是上涨概率，不参与当前 BUY / NO_TRADE。";
  if (!analysis) {
    return `<div class="dual-low-block"><div class="section-heading"><h3>${title}</h3><span>shadow overlay</span></div><div class="callout">${icon("ph-clock-countdown")}<div><strong>等待新快照</strong><br>当前历史快照尚未运行双低模型；Legacy 与 V2 结果仍然有效。</div></div></div>`;
  }
  if (analysis.status === "not_applicable") {
    return `<div class="dual-low-block"><div class="section-heading"><h3>${title}</h3><span>not applicable</span></div><div class="callout">${icon("ph-info")}<div><strong>港股 / 美股暂不套用 A 股阈值</strong><br>币种、估值制度和比较池口径不同，首版明确显示暂不适用。</div></div></div>`;
  }
  if (analysis.status === "unavailable") {
    return `<div class="dual-low-block"><div class="section-heading"><h3>${title}</h3><span>unavailable</span></div><div class="callout warning">${icon("ph-warning-circle")}<div><strong>本快照没有可用双低结果</strong><br>${esc(analysis.reason_code || "MODEL_EXECUTION_FAILED")}；现有选股流程不受影响。</div></div></div>`;
  }
  if (analysis.status === "rejected") {
    const reasons = analysis.filter_reasons || [];
    return `<div class="dual-low-block"><div class="section-heading"><h3>${title}</h3><span>${esc(dualLowLabel(analysis))}</span></div>
      <div class="dual-low-verdict warning"><div>${icon((analysis.missing_fields || []).length ? "ph-database" : "ph-funnel-x")}<span><small>双低结论</small><strong>${esc(dualLowLabel(analysis))}</strong></span></div><p>这不代表公司不好，只表示不符合当前低 PE / 低 PB 风格或数据口径不完整。</p></div>
      <ul class="dual-low-reasons">${reasons.map((reason) => `<li><span title="${esc(reason.code || "filter")}">${esc(dualLowReasonLabel(reason.code))}</span><div><b>${esc(reason.message || "未通过双低过滤")}</b><small>实际 ${esc(reason.actual ?? "--")} · 要求 ${esc(reason.expected || "--")}</small></div></li>`).join("") || `<li><div><b>未保存过滤明细</b></div></li>`}</ul>
      <p class="dual-low-disclaimer">${disclaimer}</p></div>`;
  }
  const factorScores = analysis.factor_scores || {};
  const contributions = analysis.contributions || {};
  const risks = analysis.risk_flags || [];
  return `<div class="dual-low-block"><div class="section-heading"><h3>${title}</h3><span>dsa-screening-score-v1</span></div>
    <div class="dual-low-verdict ${esc(dualLowTone(analysis))}"><div>${icon("ph-scales")}<span><small>${esc(dualLowLabel(analysis))}</small><strong>${fmt(analysis.final_score, 1)}</strong></span></div><p>同批合格 A 股排名 #${fmt(analysis.rank, 0)} / ${fmt(analysis.rank_universe_size, 0)}，比较池为本次 selector quote pool。</p></div>
    <div class="score-equation"><span><small>七因子基础分</small><b>${fmt(analysis.base_score, 1)}</b></span><i>−</i><span><small>风险扣分</small><b>${fmt(analysis.risk_penalty, 1)}</b></span><i>−</i><span><small>集中度扣分</small><b>${fmt(analysis.portfolio_penalty, 1)}</b></span><i>=</i><span class="result"><small>最终研究分</small><b>${fmt(analysis.final_score, 1)}</b></span></div>
    <div class="dual-factor-grid">${Object.entries(DUAL_LOW_FACTOR_META).map(([key, meta]) => `<article><header><span>${esc(meta[0])}</span><b>${fmt(factorScores[key], 1)}</b></header><div class="progress-bar"><span style="width:${clamp(factorScores[key])}%"></span></div><footer><small>${esc(meta[1])}</small><em>贡献 ${fmt(contributions[key], 1)}</em></footer></article>`).join("")}</div>
    ${risks.length ? `<ul class="dual-low-risk-list">${risks.map((risk) => `<li>${icon("ph-warning")}<span>${esc(risk.message || risk.code || "风险提示")}<small>扣分影响 ${fmt(risk.impact, 1)}</small></span></li>`).join("")}</ul>` : `<p class="muted dual-low-no-risk">当前双低模型未命中额外风险扣分。</p>`}
    <p class="dual-low-disclaimer">${disclaimer}</p></div>`;
}

function dualLowBatchOverview() {
  const model = state.snapshot?.analysis_models?.dual_low;
  if (!model) return "";
  if (model.status !== "available") {
    return `<section class="panel dual-low-overview"><header class="panel-header"><div><h3 class="panel-title">A股双低独立榜单</h3><p class="panel-subtitle">同批 PE / PB 价值筛选 · 不参与实际决策</p></div>${badge("等待新快照", "warning")}</header><div class="callout">${icon("ph-clock-countdown")}<div>当前快照尚未生成独立双低榜单；Legacy 与 V2 结果照常展示。</div></div></section>`;
  }
  const leaders = model.top_ranked || [];
  const rejections = model.rejection_breakdown || [];
  return `<section class="panel dual-low-overview"><header class="panel-header"><div><h3 class="panel-title">A股双低独立榜单</h3><p class="panel-subtitle">${esc(dateTime(model.score_as_of))} · ${esc(model.pool_scope || "同批报价池")} · 研究优先级，不是上涨概率</p></div>${badge(`${fmt(model.eligible_count, 0)} 合格 / ${fmt(model.input_count, 0)} 输入`, "positive")}</header>
    <div class="dual-low-overview-grid"><div><h4>研究优先序列 Top 5</h4><ol class="dual-low-leaderboard">${leaders.map((item) => `<li><span>${fmt(item.rank, 0)}</span><div><b>${esc(item.name || item.code)}</b><small>${esc(item.code)} · 风险 ${esc(DUAL_LOW_RISK_META[item.risk_level] || item.risk_level || "--")}</small></div><strong>${fmt(item.final_score, 1)}</strong></li>`).join("") || `<li class="empty-row">本批次没有通过双低过滤的股票。</li>`}</ol></div><div><h4>主要拒绝原因</h4><ul class="rejection-breakdown">${rejections.slice(0, 5).map((item) => `<li><span title="${esc(item.code)}">${esc(dualLowReasonLabel(item.code))}</span><b>${fmt(item.count, 0)} 只</b></li>`).join("") || `<li><span>无</span><b>0</b></li>`}</ul></div></div>
    <p class="dual-low-disclaimer">本轮输入：${esc(DUAL_LOW_INPUT_META[model.input_profile] || model.input_profile || "行情估值核心字段")}。${esc((model.warnings || [])[0] || "部分可选技术字段缺失时使用模型中性回退。")}</p></section>`;
}

function renderDecision() {
  const root = $("#decisionView");
  const section = marketSection(state.snapshot);
  const decision = section.decision || {};
  const baseCandidate = currentCandidate(decision);
  if (!baseCandidate) {
    root.innerHTML = `<div class="toolbar"><div><h2>${MARKET_META[state.market].label}决策</h2><p>${esc(decision.message || "本轮没有保存候选")}</p></div>${marketSwitch()}</div><div class="empty-state">${icon("ph-magnifying-glass")}<h3>没有可展示候选</h3><p>系统没有在当前数据证据下产生可执行候选，请查看其他市场或历史快照。</p></div>`;
    return;
  }
  const candidate = liveMerged(baseCandidate, state.market);
  const stats = section.stats || {};
  const range = candidate.estimated_2w_range || candidate.estimated_2d_range || {};
  const hasPrimary = Boolean(decision.primary);
  const advice = executionAdvice(candidate, hasPrimary);
  const objectivelyBlocked = candidate.execution_state === "BLOCKED" || (candidate.decision_gates || []).some((gate) => gate.status === "BLOCK");
  const regime = section.market_regime || candidate.v2?.regime || candidate.v2?.market_regime;
  const pool = num(stats.raw_pool_size || stats.universe_size);
  const shown = candidatesFor(state.snapshot, state.market).length;
  const gates = candidate.decision_gates || [];
  const passCount = gates.filter((gate) => gate.status === "PASS").length;
  const risks = [...(candidate.risk_items || []).map((risk) => `${risk.code}${risk.evidence ? ` · ${risk.evidence}` : ""}`), ...(candidate.risk_flags || [])];
  const live = state.live.get(candidateId(baseCandidate, state.market));
  root.innerHTML = `
    <div class="toolbar">
      <div class="toolbar-left"><div><h2>${MARKET_META[state.market].label} · ${esc(labelForRegime(regime))}</h2><p>${esc(section.description || decision.message || "根据当前快照执行")}</p></div>${badge(state.snapshot?.selector_mode?.includes("dual_low") ? "Legacy Active · V2 + 双低 Shadow" : state.snapshot?.selector_mode?.includes("v2") ? "Legacy Active · V2 Shadow" : "Legacy Active", "purple")}</div>
      <div class="toolbar-right">${marketSwitch()}<button class="icon-button" type="button" data-action="live" data-market="${state.market}" data-code="${esc(baseCandidate.code || baseCandidate.symbol)}">${icon("ph-lightning")}刷新当前行情</button></div>
    </div>
    ${renderKpis([
      { icon: "ph-binoculars", label: "候选池扫描", value: fmt(pool, 0), meta: `${esc(stats.universe_origin || (state.market === "a_share" ? "动态召回" : "精选静态池"))}` },
      { icon: "ph-funnel", label: "完成深评", value: fmt(stats.scored_size, 0), meta: `页面保留 ${shown} 只证据卡` },
      { icon: "ph-ranking", label: "推荐度", value: `${fmt(candidateScore(candidate), 0)}`, tone: hasPrimary ? "positive" : "warning", meta: `旧逻辑实际决策 · 总分 ${fmt(candidate.score, 1)}` },
      { icon: "ph-shield-check", label: "客观门控", value: gates.length ? `${passCount}/${gates.length}` : "Legacy", meta: gates.length ? `${gates.filter((g) => g.status === "BLOCK").length} 个阻断` : "V2 快照生成后启用展示" },
    ])}
    <div class="decision-grid">
      <div class="decision-main stack">
        <article class="card hero-card">
          <header class="card-header"><div><div class="eyebrow">${marketBadge(state.market)} ${esc(MARKET_META[state.market].label)} · ${esc(candidate.code || candidate.symbol)}</div><h2 class="card-title hero-title">${esc(candidate.name)}</h2><p class="card-subtitle">${esc(candidate.reason_tags || candidate.role || "综合候选")}</p></div><div class="hero-status">${badge(objectivelyBlocked && hasPrimary ? "LEGACY BUY" : actionLabel(decision), objectivelyBlocked ? "purple" : hasPrimary ? "positive" : "negative")}${badge(objectivelyBlocked ? "V2 客观阻断" : recommendationLabel(candidate, hasPrimary), objectivelyBlocked ? "negative" : advice.tone)}</div></header>
          <div class="card-body">
            <div class="price-grid price-grid-five">
              <div class="${toneFor(candidate.current_change_pct ?? candidate.change_pct)}"><small>当前参考价</small><strong>${price(candidatePrice(candidate))}</strong><span>${pct(candidate.current_change_pct ?? candidate.change_pct)}</span></div>
              <div><small>计划买入价</small><strong>${price(candidate.entry_price || candidate.price)}</strong><span>快照锁定</span></div>
              <div><small>保护止损</small><strong>${price(candidate.stop_loss)}</strong><span>${Number.isFinite(num(candidate.stop_loss, NaN)) ? pct((num(candidate.stop_loss) / num(candidate.entry_price || candidate.price) - 1) * 100) : "--"}</span></div>
              <div><small>目标参考</small><strong>${price(candidate.take_profit_reference)}</strong><span>${esc(range.text || "--")}</span></div>
              <div class="${advice.tone}"><small>当前执行状态</small><strong>${esc(advice.label)}</strong><span>${advice.deviation === null ? "实时偏离 --" : `实时偏离 ${pct(advice.deviation)}`}</span></div>
            </div>
            <div class="callout ${advice.tone === "negative" ? "negative" : advice.tone === "warning" ? "warning" : ""}">${icon(advice.tone === "positive" ? "ph-check-circle" : "ph-warning-circle")}<div><strong>${esc(advice.label)}</strong><br>${esc(advice.text)} ${live ? `行情源：${esc(live.source || "--")}；源时间：${esc(dateTime(live.source_as_of))}。` : "点击“刷新当前行情”可更新价格；评分和排序不会随之重算。"}</div></div>
          </div>
        </article>
        <article class="chart-card"><header class="chart-header"><div><h3 class="chart-title">价格结构与计划位</h3><p class="chart-subtitle">日 K · MA5 / MA10 / MA20 · 当前行情只覆盖图表和执行提示</p></div>${badge(`${(candidate.kline || []).length} 根K线`)}</header><div class="chart-shell"><canvas id="decisionChart" aria-label="${esc(candidate.name)}日K线图"></canvas></div></article>
        <article class="panel score-evidence-panel"><header class="panel-header"><div><h3 class="panel-title">评分证据拆解</h3><p class="panel-subtitle">先看实际决策，再分别核对 V2 与双低视角；三者不机械相加</p></div>${candidate.v2 ? badge(`V2 #${candidate.v2.rank || "--"} / ${candidate.v2.rank_universe_size || "--"}`, "primary") : ""}</header>${scoreLensCards(candidate, state.market)}${scoreDivergence(candidate, state.market)}<div class="detail-section"><div class="section-heading"><h3>V2 去重因子</h3><span>影子排序</span></div>${factorCards(candidate)}</div>${dualLowPanel(candidate, state.market)}</article>
      </div>
      <aside class="decision-side stack">
        <article class="panel"><header class="panel-header"><div><h3 class="panel-title">为什么是它</h3><p class="panel-subtitle">只展示快照保存的证据</p></div></header><ul class="evidence-list">${(candidate.reasons || []).slice(0, 7).map((reason) => `<li><h4>${esc(reason)}</h4></li>`).join("") || `<li><p>本快照未保存结构化理由。</p></li>`}</ul></article>
        <article class="panel"><header class="panel-header"><div><h3 class="panel-title">风险与门控</h3><p class="panel-subtitle">硬门控会阻止执行，警告只要求更谨慎</p></div></header>${gates.length ? `<ul class="gate-list">${gates.map((gate) => `<li><span class="status-pill ${gate.status === "PASS" ? "positive" : gate.status === "BLOCK" ? "negative" : "warning"}">${esc(gate.status)}</span><div><strong>${esc(gate.id)}</strong><small>${esc(gate.reason || "")}</small></div></li>`).join("")}</ul>` : `<div class="callout">${icon("ph-info")}<div>当前是旧快照，V2 客观门控尚未写入；Legacy 风控仍正常执行。</div></div>`}${risks.length ? `<ul class="evidence-list risk-list">${risks.slice(0, 6).map((risk) => `<li><p>${esc(risk)}</p></li>`).join("")}</ul>` : `<p class="muted">未保存额外风险标签。</p>`}</article>
        <article class="panel"><header class="panel-header"><div><h3 class="panel-title">同市场机会序列</h3><p class="panel-subtitle">页面不重新排序，沿用服务端快照顺序</p></div><button class="text-button" type="button" data-action="go-candidates">查看全部</button></header><div class="opportunity-list">${candidatesFor(state.snapshot, state.market).slice(0, 5).map((row, index) => `<button type="button" data-action="open-candidate" data-key="${esc(candidateId(row, state.market))}"><span class="opportunity-rank">${index + 1}</span><span><b>${esc(row.name)}</b><small>${esc(row.code || row.symbol)} · 推荐度 ${fmt(candidateScore(row), 0)}</small></span><strong>${row.v2?.rank ? `V2 #${row.v2.rank}` : pct(row.current_change_pct ?? row.change_pct)}</strong></button>`).join("")}</div></article>
      </aside>
    </div>`;
  requestAnimationFrame(() => drawCandleChart($("#decisionChart"), candidate));
  if (!state.live.has(candidateId(baseCandidate, state.market)) && !state.liveLoading.has(candidateId(baseCandidate, state.market))) loadLive(baseCandidate, state.market, false);
}

function filteredCandidates() {
  const { market, risk, route, query } = state.candidateFilters;
  const needle = query.trim().toLowerCase();
  return allCandidates().filter((row) => {
    if (market !== "all" && row.market !== market) return false;
    if (risk !== "all" && riskLevel(row.candidate) !== risk) return false;
    if (route !== "all" && !routeNames(row.candidate).includes(route)) return false;
    if (needle && !`${row.candidate.name || ""} ${row.candidate.code || row.candidate.symbol || ""} ${row.candidate.reason_tags || ""} ${(row.candidate.theme_tags || []).join(" ")}`.toLowerCase().includes(needle)) return false;
    return true;
  });
}

function selectedCandidateRow(rows) {
  let selected = rows.find((row) => candidateId(row.candidate, row.market) === state.candidateKey);
  if (!selected) selected = rows[0];
  if (selected) state.candidateKey = candidateId(selected.candidate, selected.market);
  return selected;
}

function featureEvidence(candidate) {
  const groups = candidate?.v2?.factor_groups || {};
  return Object.entries(groups).flatMap(([groupName, group]) => (group.features || []).map((feature) => ({ groupName, ...feature })));
}

function candidateDetail(row) {
  if (!row) return `<div class="empty-state">${icon("ph-cursor-click")}<h3>选择一只候选</h3><p>点击左侧候选查看来源链、三种评分视角和客观门控。</p></div>`;
  const { candidate: raw, market } = row;
  const candidate = liveMerged(raw, market);
  const lineage = candidate.candidate_lineage || {};
  const routes = lineage.recall_routes || [];
  const quality = candidate.data_quality;
  const gates = candidate.decision_gates || [];
  const riskTexts = [...(candidate.risk_items || []).map((risk) => `${risk.code}${risk.evidence ? ` · ${risk.evidence}` : ""}`), ...(candidate.risk_flags || [])];
  const features = featureEvidence(candidate);
  const checked = state.compare.includes(candidateId(raw, market));
  const dualLow = dualLowAnalysis(candidate);
  return `<article class="detail-panel candidate-detail">
    <header class="detail-header"><div><div class="eyebrow">${marketBadge(market)} ${esc(MARKET_META[market].label)} · ${esc(candidate.code || candidate.symbol)}</div><h2 class="detail-title">${esc(candidate.name)}</h2><p class="detail-subtitle">${esc(candidate.role || candidate.reason_tags || "综合候选")}</p></div><div class="detail-actions">${badge(`Legacy #${row.legacyRank}`, "primary")}${candidate.v2?.rank ? badge(`V2 #${candidate.v2.rank}/${candidate.v2.rank_universe_size}`, "purple") : ""}${dualLow?.status === "ranked" ? badge(`双低 #${dualLow.rank}/${dualLow.rank_universe_size}`, "positive") : dualLow ? badge(dualLowLabel(dualLow), dualLowTone(dualLow)) : ""}</div></header>
    ${scoreLensCards(candidate, market)}
    ${scoreDivergence(candidate, market)}
    <div class="detail-section"><div class="section-heading"><h3>来源链</h3><span>${esc(lineage.universe_origin || (market === "a_share" ? "dynamic_snapshot" : "curated_static"))}</span></div>${routes.length ? `<ul class="event-list">${routes.map((route) => `<li><h4>${esc(route.route || "legacy")} · ${esc(route.source || "来源未保存")}</h4><p>${esc(route.reason || "该路径召回")}</p><div class="event-meta"><span>${esc(route.published_at || route.observed_at || "时间未保存")}</span>${route.decay_weight !== undefined ? `<span>延续权重 ${fmt(route.decay_weight, 2)}</span>` : ""}</div></li>`).join("")}</ul>` : `<div class="callout">${icon("ph-info")}<div>旧快照没有结构化召回来源；这不会影响旧评分，但 V2 事件组不据此加分。</div></div>`}</div>
    <div class="detail-section"><div class="section-heading"><h3>V2 评分分组</h3><span>同一特征只在一组计分</span></div>${factorCards(candidate)}</div>
    <div class="detail-section">${dualLowPanel(candidate, market)}</div>
    ${features.length ? `<div class="detail-section"><div class="section-heading"><h3>特征证据</h3><span>${features.filter((f) => f.used_in_score).length}/${features.length} 参与</span></div><div class="feature-table">${features.map((feature) => `<div><span>${esc(feature.feature_id)}</span><b>${feature.used_in_score ? fmt(feature.score, 1) : "缺失"}</b><small>${esc(feature.evidence || "")}</small></div>`).join("")}</div></div>` : ""}
    <div class="detail-section"><div class="section-heading"><h3>客观门控与风险</h3><span>${esc(candidate.execution_state || "Legacy")}</span></div>${gates.length ? `<ul class="gate-list">${gates.map((gate) => `<li><span class="status-pill ${gate.status === "PASS" ? "positive" : gate.status === "BLOCK" ? "negative" : "warning"}">${esc(gate.status)}</span><div><strong>${esc(gate.id)}</strong><small>${esc(gate.reason || "")}</small></div></li>`).join("")}</ul>` : `<p class="muted">旧快照尚未保存 V2 门控。</p>`}${riskTexts.length ? `<ul class="evidence-list risk-list">${riskTexts.map((risk) => `<li><p>${esc(risk)}</p></li>`).join("")}</ul>` : `<p class="muted">未保存额外风险标签。</p>`}</div>
    <div class="detail-footer"><button class="icon-button" type="button" data-action="live" data-market="${market}" data-code="${esc(candidate.code || candidate.symbol)}">${icon("ph-lightning")}刷新行情</button><button class="icon-button ${checked ? "is-active" : ""}" type="button" data-action="compare" data-key="${esc(candidateId(raw, market))}">${icon(checked ? "ph-check" : "ph-scales")} ${checked ? "已加入对比" : "加入对比"}</button></div>
  </article>`;
}

function candidateMobileCard(row) {
  const c = liveMerged(row.candidate, row.market);
  const key = candidateId(row.candidate, row.market);
  const risk = riskLevel(c);
  const dualLow = dualLowAnalysis(c);
  const dualText = dualLow?.status === "ranked"
    ? `${fmt(dualLow.final_score, 0)} · #${dualLow.rank}/${dualLow.rank_universe_size}`
    : dualLowLabel(dualLow);
  return `<button class="candidate-mobile-card ${key === state.candidateKey ? "is-selected" : ""}" type="button" data-action="select-candidate" data-key="${esc(key)}" aria-pressed="${key === state.candidateKey}">
    <header><span>${marketBadge(row.market)}<b>${esc(c.name)}</b><small>${esc(c.code || c.symbol)}</small></span>${badge(decisionRoleLabel(row.decisionRole), row.decisionRole === "primary" ? "positive" : row.decisionRole === "blocked" ? "negative" : "")}</header>
    <div class="candidate-mobile-price"><strong>${price(candidatePrice(c))}</strong><span class="${toneFor(c.current_change_pct ?? c.change_pct)}">${pct(c.current_change_pct ?? c.change_pct)}</span></div>
    <dl><div><dt>Legacy</dt><dd>${fmt(candidateScore(c), 0)} · #${row.legacyRank}</dd></div><div><dt>V2 结构</dt><dd>${c.v2?.rank ? `${fmt(c.v2.rule_score, 0)} · #${c.v2.rank}/${c.v2.rank_universe_size}` : "--"}</dd></div><div><dt>双低价值</dt><dd>${esc(dualText)}</dd></div><div><dt>风险证据</dt><dd class="${risk === "clear" ? "positive" : risk === "blocked" ? "negative" : "warning"}">${({ clear: "PASS", warning: "WARN", blocked: "BLOCK" })[risk]}</dd></div></dl>
  </button>`;
}

function renderCandidates() {
  const root = $("#candidatesView");
  const rows = filteredCandidates();
  const selected = selectedCandidateRow(rows);
  const all = allCandidates();
  const blocked = all.filter((row) => riskLevel(row.candidate) === "blocked").length;
  const withLineage = all.filter((row) => routeNames(row.candidate).length).length;
  root.innerHTML = `
    <div class="toolbar candidates-toolbar">
      <div class="toolbar-left"><div><h2>跨市场候选池</h2><p>Legacy 决定实际顺序；V2 与双低分别回答结构质量和价值风格</p></div></div>
      <div class="toolbar-right"><label class="search-field">${icon("ph-magnifying-glass")}<input id="candidateSearch" type="search" value="${esc(state.candidateFilters.query)}" placeholder="搜索公司 / 代码 / 主题" aria-label="搜索候选"></label></div>
    </div>
    <div class="filter-strip">
      <div class="filter-group"><span>市场</span><div class="segmented-button"><button data-action="candidate-market" data-market="all" aria-pressed="${state.candidateFilters.market === "all"}">全部</button>${MARKET_ORDER.map((market) => `<button data-action="candidate-market" data-market="${market}" aria-pressed="${state.candidateFilters.market === market}">${MARKET_META[market].label}</button>`).join("")}</div></div>
      <label>风险<select id="candidateRisk"><option value="all">全部</option><option value="clear">无明确警告</option><option value="warning">有警告</option><option value="blocked">被阻断</option></select></label>
      <label>召回<select id="candidateRoute"><option value="all">全部来源</option><option value="event">事件</option><option value="momentum">动量</option><option value="liquidity">流动性</option><option value="pullback">回踩</option><option value="history">历史延续</option><option value="curated_static">精选静态池</option></select></label>
    </div>
    ${renderKpis([
      { icon: "ph-stack", label: "当前保存候选", value: fmt(all.length, 0), meta: "每市场首选 / 阻断标的 + 观察列" },
      { icon: "ph-path", label: "带来源链", value: fmt(withLineage, 0), meta: state.snapshot?.schema_version ? "V2 可追溯" : "下一快照写入" },
      { icon: "ph-prohibit", label: "客观阻断", value: fmt(blocked, 0), meta: "只统计结构化 BLOCK" },
      { icon: "ph-list-magnifying-glass", label: "筛选结果", value: fmt(rows.length, 0), meta: "表格不在前端重排" },
    ])}
    ${dualLowBatchOverview()}
    <div class="master-detail candidate-master-detail">
      <section class="panel candidate-table-panel"><header class="panel-header"><div><h3 class="panel-title">候选清单</h3><p class="panel-subtitle">推荐度不是收益概率；点击行查看证据</p></div></header>
        ${rows.length ? `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>市场</th><th>公司 / 代码</th><th class="number">现价</th><th class="number">涨跌</th><th class="number">推荐度</th><th class="number">Legacy</th><th class="number">V2</th><th class="number">双低</th><th>风险</th><th></th></tr></thead><tbody>${rows.map((row) => {
          const c = liveMerged(row.candidate, row.market);
          const key = candidateId(row.candidate, row.market);
          const risk = riskLevel(c);
          const dualLow = dualLowAnalysis(c);
          const dualLowCell = dualLow?.status === "ranked" ? `#${dualLow.rank} · ${fmt(dualLow.final_score, 0)}` : dualLowLabel(dualLow);
          return `<tr class="${key === state.candidateKey ? "is-selected" : ""}" tabindex="0" data-action="select-candidate" data-key="${esc(key)}"><td>${marketBadge(row.market)}</td><td><span class="name">${esc(c.name)}</span><br><span class="symbol">${esc(c.code || c.symbol)}</span></td><td class="number">${price(candidatePrice(c))}</td><td class="number ${toneFor(c.current_change_pct ?? c.change_pct)}">${pct(c.current_change_pct ?? c.change_pct)}</td><td class="number"><strong>${fmt(candidateScore(c), 0)}</strong></td><td class="number">#${row.legacyRank}/${candidatesFor(state.snapshot, row.market).length}</td><td class="number">${c.v2?.rank ? `#${c.v2.rank}/${c.v2.rank_universe_size || "--"}` : "--"}</td><td class="number dual-low-cell ${esc(dualLowTone(dualLow))}">${esc(dualLowCell)}</td><td><span class="status-pill ${risk === "clear" ? "positive" : risk === "blocked" ? "negative" : "warning"}">${({ clear: "清晰", warning: "警告", blocked: "阻断" })[risk]}</span></td><td><button class="row-action" type="button" data-action="select-candidate" data-key="${esc(key)}" aria-label="查看${esc(c.name)}详情">${icon("ph-caret-right")}</button></td></tr>`;
        }).join("")}</tbody></table></div>` : `<div class="empty-state">${icon("ph-funnel-x")}<h3>没有匹配候选</h3><p>调整市场、风险或召回来源筛选。</p></div>`}
        ${rows.length ? `<div class="candidate-mobile-list">${rows.map(candidateMobileCard).join("")}</div>` : ""}
      </section>
      <div>${candidateDetail(selected)}</div>
    </div>
    ${state.compare.length ? renderComparisonTray() : ""}`;
  $("#candidateRisk").value = state.candidateFilters.risk;
  $("#candidateRoute").value = state.candidateFilters.route;
}

function renderComparisonTray() {
  const rows = state.compare.map((key) => allCandidates().find((row) => candidateId(row.candidate, row.market) === key)).filter(Boolean);
  return `<div class="comparison-tray"><div><p>候选对比 ${rows.length}/3</p>${rows.map((row) => `<span class="tag primary">${esc(row.candidate.name)} · ${fmt(candidateScore(row.candidate), 0)}<button type="button" data-action="compare" data-key="${esc(candidateId(row.candidate, row.market))}" aria-label="移除${esc(row.candidate.name)}">${icon("ph-x")}</button></span>`).join("")}</div><button class="icon-button" type="button" data-action="clear-compare">清空</button></div>`;
}

function fallbackEvents() {
  return MARKET_ORDER.flatMap((market) => {
    const decision = marketDecision(state.snapshot, market);
    const candidate = currentCandidate(decision);
    if (!candidate) return [];
    return [{
      event_id: `legacy:${market}:${candidate.code || candidate.symbol}`,
      event_type: "model_signal",
      market,
      symbol: candidate.code || candidate.symbol,
      company: candidate.name,
      title: `${candidate.name} 进入本轮${MARKET_META[market].label}${decision.primary ? "可执行候选" : "观察 / 阻断"}`,
      source: "Legacy selector snapshot",
      published_at: state.snapshot?.generated_at,
      ingested_at: state.snapshot?.generated_at,
      direction: decision.primary ? "positive" : "neutral",
      impact_score: candidateScore(candidate),
      url: null,
      evidence_status: "model",
      note: "旧快照没有保存逐条公告或新闻，只能展示真实的模型入选信号。",
    }];
  });
}

function eventItems() {
  const items = state.snapshot?.events?.items;
  return Array.isArray(items) ? items : fallbackEvents();
}

function filteredEvents() {
  const { market, type, direction, query } = state.eventFilters;
  const needle = query.trim().toLowerCase();
  return eventItems().filter((event) => {
    if (market !== "all" && event.market !== market) return false;
    if (type !== "all" && event.event_type !== type) return false;
    if (direction !== "all" && normalizedDirection(event.direction) !== direction) return false;
    if (needle && !`${event.company || ""} ${event.symbol || ""} ${event.title || ""} ${event.source || ""}`.toLowerCase().includes(needle)) return false;
    return true;
  });
}

function renderEventDetail(event) {
  if (!event) return `<div class="empty-state">${icon("ph-cursor-click")}<h3>选择一条事件</h3><p>查看来源、时间、证据完整性与受影响证券。</p></div>`;
  const sourceValid = Boolean(event.source);
  const timeValid = Boolean(event.published_at || event.ingested_at);
  const eventUrl = safeHttpUrl(event.url);
  const urlValid = Boolean(eventUrl);
  const direction = normalizedDirection(event.direction);
  return `<article class="detail-panel event-detail"><header class="detail-header"><div><div class="eyebrow">${marketBadge(event.market)} ${esc(MARKET_META[event.market]?.label || event.market)} · ${esc(event.event_type)}</div><h2 class="detail-title">${esc(event.title)}</h2><p class="detail-subtitle">${esc(event.company || "行业事件")} ${event.symbol ? `· ${esc(event.symbol)}` : ""}</p></div>${badge(direction === "positive" ? "正面" : direction === "negative" ? "负面" : "中性 / 未知", direction === "positive" ? "positive" : direction === "negative" ? "negative" : "")}</header>
    <div class="event-score-strip"><div><small>影响分（规则）</small><strong>${fmt(event.impact_score, 1)}</strong></div><div><small>证据状态</small><strong>${esc(event.evidence_status || "unknown")}</strong></div><div><small>发布时间</small><strong>${esc(dateTime(event.published_at))}</strong></div></div>
    <div class="detail-section"><div class="section-heading"><h3>证据完整性</h3><span>不补写未知字段</span></div><ul class="gate-list"><li><span class="status-pill ${sourceValid ? "positive" : "warning"}">${sourceValid ? "PASS" : "WARN"}</span><div><strong>来源</strong><small>${esc(event.source || "未保存")}</small></div></li><li><span class="status-pill ${timeValid ? "positive" : "warning"}">${timeValid ? "PASS" : "WARN"}</span><div><strong>时间</strong><small>${esc(dateTime(event.published_at || event.ingested_at))}</small></div></li><li><span class="status-pill ${urlValid ? "positive" : "warning"}">${urlValid ? "PASS" : "WARN"}</span><div><strong>原文链接</strong><small>${urlValid ? "快照已保存" : "快照未保存，不生成假链接"}</small></div></li></ul></div>
    <div class="callout">${icon("ph-info")}<div><strong>如何参与选股</strong><br>${esc(event.note || (event.event_type === "model_signal" ? "这是模型入选信号，不是外部公告。" : "只有来源链明确的结构化事件才进入 V2 事件组；旧题材文本不会重复加分。"))}</div></div>
    ${eventUrl ? `<a class="primary-button" href="${esc(eventUrl)}" target="_blank" rel="noopener noreferrer">查看证据原文 ${icon("ph-arrow-square-out")}</a>` : `<button class="primary-button" type="button" disabled>没有可验证原文链接</button>`}
  </article>`;
}

function renderEvents() {
  const root = $("#eventsView");
  const all = eventItems();
  const rows = filteredEvents();
  let selected = rows.find((event) => event.event_id === state.eventKey) || rows[0];
  if (selected) state.eventKey = selected.event_id;
  const externalCount = all.filter((event) => event.event_type !== "model_signal").length;
  const missingEvidence = all.filter((event) => !event.source || !(event.published_at || event.ingested_at)).length;
  const positive = all.filter((event) => normalizedDirection(event.direction) === "positive").length;
  root.innerHTML = `
    <div class="toolbar"><div class="toolbar-left"><div><h2>事件证据流</h2><p>公告、新闻召回与模型信号分开呈现，未知来源不补写</p></div></div><div class="toolbar-right"><label class="search-field">${icon("ph-magnifying-glass")}<input id="eventSearch" type="search" value="${esc(state.eventFilters.query)}" placeholder="搜索公司 / 代码 / 事件" aria-label="搜索事件"></label></div></div>
    ${!Array.isArray(state.snapshot?.events?.items) ? `<div class="callout warning section-callout">${icon("ph-warning-circle")}<div><strong>当前仍是旧快照</strong><br>页面只展示快照中真实存在的模型信号。下一次 V2 快照会加入结构化事件来源链；不会用虚构公告填满列表。</div></div>` : ""}
    ${renderKpis([
      { icon: "ph-bell", label: "保存事件", value: fmt(all.length, 0), meta: "当前快照中的可见证据" },
      { icon: "ph-newspaper", label: "外部证据", value: fmt(externalCount, 0), meta: "不含模型信号" },
      { icon: "ph-arrow-up", label: "正向信号", value: fmt(positive, 0), meta: "方向是规则标签，不是收益预测" },
      { icon: "ph-warning", label: "证据缺项", value: fmt(missingEvidence, 0), meta: "来源或时间未保存" },
    ])}
    <div class="filter-strip"><div class="filter-group"><span>市场</span><div class="segmented-button"><button data-action="event-market" data-market="all" aria-pressed="${state.eventFilters.market === "all"}">全部</button>${MARKET_ORDER.map((market) => `<button data-action="event-market" data-market="${market}" aria-pressed="${state.eventFilters.market === market}">${MARKET_META[market].label}</button>`).join("")}</div></div><label>类型<select id="eventType"><option value="all">全部</option><option value="announcement_or_news">公告 / 新闻</option><option value="model_signal">模型信号</option></select></label><label>方向<select id="eventDirection"><option value="all">全部</option><option value="positive">正面</option><option value="neutral">中性 / 未知</option><option value="negative">负面</option></select></label></div>
    <div class="master-detail"><section class="panel"><header class="panel-header"><div><h3 class="panel-title">事件列表</h3><p class="panel-subtitle">${rows.length} 条匹配结果</p></div></header>${rows.length ? `<div class="event-master-list">${rows.map((event) => { const direction = normalizedDirection(event.direction); return `<button class="event-master-row ${event.event_id === state.eventKey ? "is-selected" : ""}" type="button" data-action="select-event" data-key="${esc(event.event_id)}"><time>${esc(dateTime(event.published_at || event.ingested_at, false))}</time>${marketBadge(event.market)}<span><b>${esc(event.company || "行业事件")}</b><strong>${esc(event.title)}</strong><small>${esc(event.source || "来源未保存")}</small></span><em class="${direction === "positive" ? "positive" : direction === "negative" ? "negative" : "muted"}">${fmt(event.impact_score, 1)}</em></button>`; }).join("")}</div>` : `<div class="empty-state">${icon("ph-funnel-x")}<h3>没有匹配事件</h3><p>调整市场、类型、方向或搜索条件。</p></div>`}</section><div>${renderEventDetail(selected)}</div></div>`;
  $("#eventType").value = state.eventFilters.type;
  $("#eventDirection").value = state.eventFilters.direction;
}

function historyMarketSummary(item, market = state.historyMarket) {
  if (item.markets?.[market]) return item.markets[market];
  if (market === "a_share") return item;
  return {};
}

function filteredHistory() {
  const needle = state.historyQuery.trim().toLowerCase();
  return state.history.filter((item) => {
    const summary = historyMarketSummary(item);
    if (state.historyAction === "buy" && !summary.has_primary) return false;
    if (state.historyAction === "no_trade" && summary.has_primary) return false;
    if (needle && !`${item.target_date || ""} ${item.generated_at || ""} ${summary.name || ""} ${summary.code || ""}`.toLowerCase().includes(needle)) return false;
    return true;
  });
}

function selectedHistoryItem(rows) {
  let selected = rows.find((item) => (item.snapshot_key || item.cache_key) === state.historyKey) || rows[0];
  if (selected) state.historyKey = selected.snapshot_key || selected.cache_key;
  return selected;
}

function historyDetail(item) {
  if (!item) return `<div class="empty-state">${icon("ph-clock-counter-clockwise")}<h3>暂无历史快照</h3><p>服务端还没有返回可复盘记录。</p></div>`;
  const summary = historyMarketSummary(item);
  const loadedSection = state.historySnapshot && (state.historySnapshot.snapshot_key === (item.snapshot_key || item.cache_key)) ? marketSection(state.historySnapshot, state.historyMarket) : null;
  const decision = loadedSection?.decision;
  const candidate = decision ? currentCandidate(decision) : null;
  return `<article class="detail-panel history-detail"><header class="detail-header"><div><div class="eyebrow">不可变快照 · ${esc(item.snapshot_key || item.cache_key || "--")}</div><h2 class="detail-title">${esc(item.target_date || item.signal_date || "--")} · ${MARKET_META[state.historyMarket].label}</h2><p class="detail-subtitle">生成于 ${esc(dateTime(item.generated_at))}</p></div>${badge(summary.has_primary ? "BUY CANDIDATE" : "NO TRADE", summary.has_primary ? "positive" : "negative")}</header>
    <div class="detail-score-grid"><div><small>标的</small><strong>${esc(summary.name || "无")}</strong><span>${esc(summary.code || "--")}</span></div><div><small>推荐度</small><strong>${fmt(summary.recommendation_degree ?? summary.confidence, 0)}</strong><span>非概率</span></div><div><small>参考价</small><strong>${price(summary.entry_price)}</strong><span>当时快照</span></div><div><small>两周区间</small><strong>${esc(summary.estimated_2w_range || summary.estimated_2d_range || "--")}</strong><span>规则估计</span></div></div>
    <div class="callout warning">${icon("ph-warning-circle")}<div><strong>结果验证状态：待验证</strong><br>当前历史接口保存的是当时决策，不含逐笔成交、复权后的统一退出价与真实滑点，因此不展示“命中率”或伪造收益。</div></div>
    ${candidate ? `<div class="detail-section"><div class="section-heading"><h3>完整快照证据</h3><span>已载入</span></div>${factorCards(candidate)}<ul class="evidence-list">${(candidate.reasons || []).slice(0, 5).map((reason) => `<li><h4>${esc(reason)}</h4></li>`).join("")}</ul></div>` : `<div class="detail-section"><button class="primary-button" type="button" data-action="load-history" data-key="${esc(item.snapshot_key || item.cache_key)}">${icon("ph-download-simple")}载入完整快照证据</button></div>`}
  </article>`;
}

function renderHistory() {
  const root = $("#historyView");
  const rows = filteredHistory();
  const selected = selectedHistoryItem(rows);
  const totalDecisions = state.history.reduce((sum, item) => sum + (historyMarketSummary(item).has_primary ? 1 : 0), 0);
  const avgScores = state.history.map((item) => num(historyMarketSummary(item).recommendation_degree ?? historyMarketSummary(item).confidence, NaN)).filter(Number.isFinite);
  const average = avgScores.length ? avgScores.reduce((a, b) => a + b, 0) / avgScores.length : NaN;
  root.innerHTML = `
    <div class="toolbar"><div class="toolbar-left"><div><h2>决策快照历史</h2><p>每次生成后锁定，复盘时不使用后来数据改写当时判断</p></div></div><div class="toolbar-right"><label class="search-field">${icon("ph-magnifying-glass")}<input id="historySearch" type="search" value="${esc(state.historyQuery)}" placeholder="搜索日期 / 公司 / 代码" aria-label="搜索历史"></label></div></div>
    <div class="filter-strip"><div class="filter-group"><span>市场</span><div class="segmented-button">${MARKET_ORDER.map((market) => `<button data-action="history-market" data-market="${market}" aria-pressed="${state.historyMarket === market}">${MARKET_META[market].label}</button>`).join("")}</div></div><label>动作<select id="historyAction"><option value="all">全部</option><option value="buy">有首选</option><option value="no_trade">不交易</option></select></label></div>
    ${renderKpis([
      { icon: "ph-archive", label: "历史快照", value: fmt(state.history.length, 0), meta: `最多读取 120 条摘要` },
      { icon: "ph-check-square", label: "有首选记录", value: fmt(totalDecisions, 0), meta: `${MARKET_META[state.historyMarket].label}筛选口径` },
      { icon: "ph-gauge", label: "平均推荐度", value: Number.isFinite(average) ? fmt(average, 1) : "--", meta: "仅历史评分均值，不是成功率" },
      { icon: "ph-calendar-check", label: "当前目标日", value: state.snapshot?.target_date || "--", meta: `最新生成 ${dateTime(state.snapshot?.generated_at)}` },
    ])}
    <div class="history-overview-grid"><article class="chart-card"><header class="chart-header"><div><h3 class="chart-title">推荐度轨迹</h3><p class="chart-subtitle">按生成时间排列；空值不补齐</p></div>${badge(MARKET_META[state.historyMarket].label, "primary")}</header><div class="chart-shell history-chart-shell"><canvas id="historyChart" aria-label="历史推荐度趋势"></canvas></div></article><article class="panel"><header class="panel-header"><div><h3 class="panel-title">复盘口径</h3><p class="panel-subtitle">事实、推断和待验证数据分开</p></div></header><ul class="evidence-list"><li><h4>事实</h4><p>快照时间、当时首选、推荐度、入场 / 止损 / 目标位。</p></li><li><h4>尚未接入</h4><p>统一复权收益、盘中是否成交、滑点、分红和不同市场交易日历。</p></li><li><h4>因此不展示</h4><p>未经校准的胜率、Alpha 与“历史命中”宣传数字。</p></li></ul></article></div>
    <div class="master-detail history-master-detail"><section class="panel"><header class="panel-header"><div><h3 class="panel-title">快照列表</h3><p class="panel-subtitle">${rows.length} 条匹配结果</p></div></header>${rows.length ? `<div class="snapshot-list">${rows.map((item) => {
      const summary = historyMarketSummary(item);
      const key = item.snapshot_key || item.cache_key;
      return `<button class="snapshot-row ${key === state.historyKey ? "is-selected" : ""}" type="button" data-action="select-history" data-key="${esc(key)}"><time>${esc(item.target_date || "--")}<small>${esc(dateTime(item.generated_at, false))}</small></time><span><b>${esc(summary.name || "本轮不交易")}</b><small>${esc(summary.code || summary.message || "无首选")}</small></span><strong class="${summary.has_primary ? "positive" : "negative"}">${summary.has_primary ? fmt(summary.recommendation_degree ?? summary.confidence, 0) : "NO"}</strong>${icon("ph-caret-right")}</button>`;
    }).join("")}</div>` : `<div class="empty-state">${icon("ph-funnel-x")}<h3>没有匹配快照</h3><p>调整市场、动作或搜索条件。</p></div>`}</section><div>${historyDetail(selected)}</div></div>`;
  $("#historyAction").value = state.historyAction;
  requestAnimationFrame(() => drawHistoryChart($("#historyChart"), rows.slice().reverse(), state.historyMarket));
}

function findV2Candidate() {
  return allCandidates().map((row) => row.candidate).find((candidate) => candidate.v2?.factor_groups) || null;
}

function modelWeightRows() {
  const candidate = findV2Candidate();
  const groups = candidate?.v2?.factor_groups;
  if (!groups) return [
    ["事件", 18], ["技术结构", 30], ["产业链", 20], ["流动性 / 资金", 20], ["质量 / 风险", 12],
  ];
  return Object.entries(groups).map(([key, value]) => [FACTOR_META[key]?.[0] || key, num(value.weight) * 100]);
}

function renderModel() {
  const root = $("#modelView");
  const status = state.status || {};
  const snapshot = state.snapshot || {};
  const weights = modelWeightRows();
  const dualModel = snapshot.analysis_models?.dual_low || {};
  root.innerHTML = `
    <div class="toolbar"><div class="toolbar-left"><div><h2>模型与运行机制</h2><p>把“从哪里找到、为什么入选、为何可执行”拆成可核查步骤</p></div>${badge(snapshot.selector_mode || "legacy_active", "purple")}</div><div class="toolbar-right"><a class="icon-button" href="https://github.com/dzhdingzihang/xuangu" target="_blank" rel="noopener noreferrer">${icon("ph-github-logo")}查看源码</a></div></div>
    ${renderKpis([
      { icon: "ph-cpu", label: "模型版本", value: snapshot.model_version || status.model_version || "--", meta: `Schema ${esc(snapshot.schema_version || "legacy")}` },
      { icon: "ph-sliders-horizontal", label: "权重版本", value: snapshot.weights_version || "待生成", meta: "规则先验，不是训练概率" },
      { icon: "ph-stack", label: "候选池版本", value: snapshot.universe_version || "legacy", meta: "A股动态 · 港美精选静态" },
      { icon: "ph-cloud", label: "公开运行面", value: status.platform || "Cloudflare Workers", meta: "生成：GitHub Actions" },
    ])}
    <section class="panel model-pipeline-panel"><header class="panel-header"><div><h3 class="panel-title">从数据到决策</h3><p class="panel-subtitle">实时行情不会偷偷改写已经发布的评分</p></div></header><ol class="pipeline-list"><li><span>01</span><div><b>多路召回候选</b><p>A股合并事件、动量、流动性、回踩与最多 5 个工作日的历史延续；港美为透明的精选静态池。</p></div></li><li><span>02</span><div><b>整批价值筛选</b><p>在 A 股同一报价池运行 PE / PB 双低七因子；先保留完整排名分母，再截取股票做深评。</p></div></li><li><span>03</span><div><b>行情与结构深评</b><p>获取日 K，计算缠论近似、CZSC 近似、UZI 风控 / 评审团与 Serenity 产业链先验。</p></div></li><li><span>04</span><div><b>Legacy 实际决策</b><p>旧总分、推荐度、排序、BUY / NO_TRADE 原样保留，保护既有逻辑连续性。</p></div></li><li><span>05</span><div><b>V2 + 双低影子</b><p>V2 去重解释结构质量；双低独立解释价值风格，两套影子分均不替换 Legacy。</p></div></li><li><span>06</span><div><b>客观门控与快照</b><p>无有效价格、K线不足、停牌退市或交易时段明确陈旧行情会阻断；结果写入不可变 JSON。</p></div></li><li><span>07</span><div><b>Cloudflare 展示</b><p>Worker 读取构建时快照；/api/live 只刷新价格、K线和执行提示，不重排股票。</p></div></li></ol></section>
    <div class="model-grid">
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">旧因子仍然保留</h3><p class="panel-subtitle">回答“之前的评分还在吗”</p></div>${badge("Active", "positive")}</header><div class="legacy-map"><div><b>初筛 pre_score</b><span>成交额、换手、量比、涨幅等</span></div><div><b>缠论近似 chan_score</b><span>均线结构、二买 / 三买、箱体回踩</span></div><div><b>CZSC 近似</b><span>中枢、趋势、箱体位置与背驰风险</span></div><div><b>UZI + 评审团</b><span>买点纪律、流动性、过热和杀猪盘门控</span></div><div><b>Serenity 先验</b><span>AI capex 上游稀缺环节与融资风险</span></div><div><b>推荐度与动作</b><span>继续决定实际排名和 BUY / NO_TRADE</span></div></div></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">V2 分组权重</h3><p class="panel-subtitle">随市场状态采用规则先验；分数只作影子观察</p></div>${badge(snapshot.weights_version || "示意基准", "purple")}</header><div class="weight-list">${weights.map(([label, value]) => `<div><span>${esc(label)}</span><div class="progress-bar"><span style="width:${clamp(value)}%"></span></div><b>${fmt(value, 0)}%</b></div>`).join("")}</div><p class="fine-print">若市场基准数据不足，状态为 unknown 并保守处理；这里不声称是机器学习概率。</p></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">双低七因子 · 独立影子</h3><p class="panel-subtitle">补充估值视角，不与 Legacy / V2 机械相加</p></div>${badge(dualModel.status === "available" ? "Shadow available" : "Shadow", dualModel.status === "available" ? "positive" : "warning")}</header><dl><dt>模型</dt><dd>${esc(dualModel.model_id || "dsa-screening-score-v1")}</dd><dt>市场</dt><dd>A股；港美暂不适用</dd><dt>比较池</dt><dd>${esc(dualModel.pool_scope || "a_share.merged_recall_quote_pool.pre_kline_v1")}</dd><dt>输入 / 合格</dt><dd>${dualModel.input_count === undefined ? "待新快照" : `${fmt(dualModel.input_count, 0)} / ${fmt(dualModel.eligible_count, 0)}`}</dd><dt>默认风格</dt><dd>PE≤15、PB≤2、不过热</dd><dt>决策权限</dt><dd>无；仅输出研究优先级</dd></dl><p class="fine-print">“被过滤”只表示不符合这套价值风格或数据不完整，不表示公司质量差。</p></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">候选池边界</h3><p class="panel-subtitle">扩大召回，但不承诺全市场无遗漏</p></div></header><dl><dt>A股</dt><dd>事件 + 动量 + 流动性 + 回踩 + 历史延续</dd><dt>港股</dt><dd>153 只左右精选静态清单，Yahoo 行情</dd><dt>美股</dt><dd>258 只左右精选静态清单，Yahoo 行情</dd><dt>历史延续</dt><dd>最多 5 个工作日、40 只、带衰减元数据</dd><dt>交易日</dt><dd>当前计划任务仅按周一至周五，不识别三地全部节假日</dd></dl></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">运行架构</h3><p class="panel-subtitle">公开站点不依赖 Render</p></div>${badge("Cloudflare only", "primary")}</header><div class="architecture-list"><div>${icon("ph-github-logo")}<span><b>GitHub Actions</b><small>定时运行 Python，生成最新快照与历史文件</small></span></div><div>${icon("ph-package")}<span><b>构建时 JSON assets</b><small>数据随 Worker 部署，不使用 KV / D1 / R2</small></span></div><div>${icon("ph-cloud")}<span><b>Cloudflare Worker</b><small>提供静态页面、历史快照 API 与实时行情代理</small></span></div><div>${icon("ph-browser")}<span><b>浏览器</b><small>渲染证据、筛选与执行提示，不在前端重算评分</small></span></div></div></article>
    </div>
    <section class="panel section-gap"><header class="panel-header"><div><h3 class="panel-title">能力状态与限制</h3><p class="panel-subtitle">不把近似规则包装成官方框架</p></div></header><div class="truth-grid"><div><span class="status-pill warning">内置近似</span><b>缠论 / CZSC</b><p>用日线均线、箱体、突破回踩和背驰风险近似，不是原生 CZSC 执行。</p></div><div><span class="status-pill warning">方法论加权</span><b>UZI</b><p>内置轻量评审和风控规则，不是外部 UZI 模型服务。</p></div><div><span class="status-pill warning">研究先验</span><b>Serenity</b><p>硬编码产业链 lens；安装 Skill 只改变元数据，不会改变分数。</p></div><div><span class="status-pill positive">真实接口</span><b>实时行情</b><p>A股优先东方财富并回退腾讯，港美 Yahoo；源时间和抓取时间分开。</p></div></div></section>`;
}

function renderActiveTab() {
  if (!state.snapshot) return;
  const view = $(`#${state.tab}View`);
  if (view) view.classList.remove("view-loading");
  ({ decision: renderDecision, candidates: renderCandidates, events: renderEvents, history: renderHistory, model: renderModel })[state.tab]?.();
}

function setupCanvas(canvas, fallbackHeight = 220) {
  if (!canvas) return null;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, rect.width || canvas.parentElement?.clientWidth || 640);
  const height = Math.max(160, rect.height || canvas.parentElement?.clientHeight || fallbackHeight);
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width, height };
}

function movingAverage(rows, period) {
  return rows.map((_, index) => {
    if (index < period - 1) return null;
    const slice = rows.slice(index - period + 1, index + 1);
    return slice.reduce((sum, row) => sum + num(row.close), 0) / period;
  });
}

function drawCandleChart(canvas, candidate) {
  const box = setupCanvas(canvas, 220);
  if (!box) return;
  const { ctx, width, height } = box;
  const rows = (candidate?.kline || []).filter((row) => num(row.high) > 0 && num(row.low) > 0 && num(row.close) > 0).slice(-42);
  ctx.clearRect(0, 0, width, height);
  if (rows.length < 2) {
    ctx.fillStyle = "#63718a"; ctx.font = "12px Inter, sans-serif"; ctx.fillText("K线数据不足", 16, 28); return;
  }
  const pad = { left: 12, right: 46, top: 18, bottom: 25 };
  const values = rows.flatMap((row) => [num(row.high), num(row.low)]);
  const stop = num(candidate.stop_loss, NaN);
  const take = num(candidate.take_profit_reference, NaN);
  if (Number.isFinite(stop)) values.push(stop);
  if (Number.isFinite(take)) values.push(take);
  const min = Math.min(...values); const max = Math.max(...values); const span = Math.max(max - min, 0.01);
  const x = (index) => pad.left + (index + 0.5) * ((width - pad.left - pad.right) / rows.length);
  const y = (value) => pad.top + ((max - value) / span) * (height - pad.top - pad.bottom);
  ctx.strokeStyle = "#e6edf6"; ctx.lineWidth = 1; ctx.font = "9px DM Mono, monospace"; ctx.fillStyle = "#8794a9";
  for (let i = 0; i <= 4; i += 1) {
    const yy = pad.top + i * ((height - pad.top - pad.bottom) / 4);
    ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(width - pad.right, yy); ctx.stroke();
    const value = max - i * (span / 4); ctx.fillText(value.toFixed(value >= 100 ? 1 : 2), width - pad.right + 6, yy + 3);
  }
  const step = (width - pad.left - pad.right) / rows.length; const bodyWidth = Math.max(2, Math.min(8, step * 0.58));
  rows.forEach((row, index) => {
    const up = num(row.close) >= num(row.open); const color = up ? "#0d8a67" : "#d04d55";
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x(index), y(num(row.high))); ctx.lineTo(x(index), y(num(row.low))); ctx.stroke();
    const top = y(Math.max(num(row.open), num(row.close))); const bottom = y(Math.min(num(row.open), num(row.close)));
    ctx.fillRect(x(index) - bodyWidth / 2, top, bodyWidth, Math.max(1.5, bottom - top));
  });
  [[5, "#2875d8"], [10, "#7355ba"], [20, "#ad6a10"]].forEach(([period, color]) => {
    const ma = movingAverage(rows, period); ctx.strokeStyle = color; ctx.lineWidth = 1.2; ctx.beginPath(); let started = false;
    ma.forEach((value, index) => { if (value === null) return; if (!started) { ctx.moveTo(x(index), y(value)); started = true; } else ctx.lineTo(x(index), y(value)); }); ctx.stroke();
  });
  [[stop, "#d04d55", "止损"], [take, "#0d8a67", "目标"]].forEach(([value, color, label]) => {
    if (!Number.isFinite(value)) return; const yy = y(value); ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = color; ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(width - pad.right, yy); ctx.stroke(); ctx.restore(); ctx.fillStyle = color; ctx.fillText(label, pad.left + 3, yy - 4);
  });
  ctx.fillStyle = "#8794a9"; ctx.fillText(rows[0].date?.slice(5) || "", pad.left, height - 7); ctx.fillText(rows.at(-1).date?.slice(5) || "", width - pad.right - 30, height - 7);
}

function drawHistoryChart(canvas, rows, market) {
  const box = setupCanvas(canvas, 180); if (!box) return;
  const { ctx, width, height } = box; ctx.clearRect(0, 0, width, height);
  const values = rows.map((item) => num(historyMarketSummary(item, market).recommendation_degree ?? historyMarketSummary(item, market).confidence, NaN));
  const points = values.map((value, index) => ({ value, index })).filter((point) => Number.isFinite(point.value));
  if (points.length < 2) { ctx.fillStyle = "#63718a"; ctx.font = "12px Inter, sans-serif"; ctx.fillText("有效历史评分不足", 16, 28); return; }
  const pad = { left: 32, right: 14, top: 16, bottom: 24 }; const min = Math.max(0, Math.min(...points.map((p) => p.value)) - 8); const max = Math.min(100, Math.max(...points.map((p) => p.value)) + 8); const span = Math.max(1, max - min);
  const x = (index) => pad.left + (index / Math.max(1, rows.length - 1)) * (width - pad.left - pad.right); const y = (value) => pad.top + ((max - value) / span) * (height - pad.top - pad.bottom);
  ctx.strokeStyle = "#e6edf6"; ctx.fillStyle = "#8794a9"; ctx.font = "9px DM Mono, monospace";
  for (let i = 0; i <= 3; i += 1) { const yy = pad.top + i * ((height - pad.top - pad.bottom) / 3); ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(width - pad.right, yy); ctx.stroke(); ctx.fillText(String(Math.round(max - i * (span / 3))), 3, yy + 3); }
  ctx.strokeStyle = "#2875d8"; ctx.lineWidth = 2; ctx.beginPath(); points.forEach((point, index) => { if (!index) ctx.moveTo(x(point.index), y(point.value)); else ctx.lineTo(x(point.index), y(point.value)); }); ctx.stroke();
  ctx.fillStyle = "#2875d8"; points.forEach((point) => { ctx.beginPath(); ctx.arc(x(point.index), y(point.value), 2.3, 0, Math.PI * 2); ctx.fill(); });
}

async function loadLive(candidate, market, notify = true) {
  if (!candidate) return;
  const key = candidateId(candidate, market);
  if (state.liveLoading.has(key)) return;
  state.liveLoading.add(key);
  try {
    const code = candidate.code || candidate.symbol;
    const payload = await getJson(`/api/live?market=${encodeURIComponent(market)}&code=${encodeURIComponent(code)}`);
    state.live.set(key, payload);
    if (notify) showToast(`${candidate.name} 当前行情已更新；评分与排序保持快照值。`, "success");
    renderActiveTab();
  } catch (error) {
    if (notify) showToast(error.message || "实时行情暂不可用", "error");
  } finally {
    state.liveLoading.delete(key);
  }
}

async function loadHistorySnapshot(key) {
  if (!key) return;
  try {
    state.historySnapshot = await getJson(`/api/pick?snapshot=${encodeURIComponent(key)}`);
    renderHistory();
    showToast("完整历史快照已载入。", "success");
  } catch (error) {
    showToast(error.message || "历史快照载入失败", "error");
  }
}

async function refreshAll() {
  const button = $("#refreshBtn");
  button.classList.add("is-loading"); button.disabled = true;
  try {
    const [status, historyPayload, snapshot] = await Promise.all([getJson("/api/status"), getJson("/api/history?limit=120"), getJson("/api/latest")]);
    state.status = status; state.history = historyPayload.history || []; state.snapshot = snapshot; state.live.clear(); state.historySnapshot = null;
    renderRail(); updateTopbar(); renderActiveTab();
    showToast("最新已发布快照已刷新。Cloudflare 页面不会在线重算选股。", "success");
  } catch (error) {
    showToast(error.message || "刷新失败", "error");
  } finally {
    button.classList.remove("is-loading"); button.disabled = false;
  }
}

function rowForKey(key) {
  return allCandidates().find((row) => candidateId(row.candidate, row.market) === key);
}

function handleClick(event) {
  const tabButton = event.target.closest(".nav-item[data-tab]");
  if (tabButton) { switchTab(tabButton.dataset.tab); return; }
  const control = event.target.closest("[data-action]");
  if (!control) return;
  const { action, market, key, code } = control.dataset;
  if (action === "market") { state.market = market; renderRail(); switchTab("decision"); return; }
  if (action === "candidate-market") { state.candidateFilters.market = market; renderCandidates(); return; }
  if (action === "select-candidate") {
    state.candidateKey = key;
    renderCandidates();
    if (window.matchMedia("(max-width: 760px)").matches) {
      requestAnimationFrame(() => $(".candidate-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
    return;
  }
  if (action === "open-candidate") { state.candidateKey = key; state.candidateFilters.market = key.split(":")[0]; switchTab("candidates"); return; }
  if (action === "go-candidates") { state.candidateFilters.market = state.market; switchTab("candidates"); return; }
  if (action === "compare") {
    if (state.compare.includes(key)) state.compare = state.compare.filter((item) => item !== key);
    else if (state.compare.length < 3) state.compare.push(key);
    else showToast("最多同时对比 3 只候选。", "error");
    renderCandidates(); return;
  }
  if (action === "clear-compare") { state.compare = []; renderCandidates(); return; }
  if (action === "event-market") { state.eventFilters.market = market; renderEvents(); return; }
  if (action === "select-event") { state.eventKey = key; renderEvents(); return; }
  if (action === "history-market") { state.historyMarket = market; state.historyKey = ""; state.historySnapshot = null; renderHistory(); return; }
  if (action === "select-history") { state.historyKey = key; state.historySnapshot = null; renderHistory(); return; }
  if (action === "load-history") { loadHistorySnapshot(key); return; }
  if (action === "live") {
    const row = allCandidates().find((item) => item.market === market && String(item.candidate.code || item.candidate.symbol) === String(code));
    if (row) loadLive(row.candidate, market); return;
  }
}

function handleChange(event) {
  if (event.target.id === "candidateRisk") { state.candidateFilters.risk = event.target.value; renderCandidates(); }
  if (event.target.id === "candidateRoute") { state.candidateFilters.route = event.target.value; renderCandidates(); }
  if (event.target.id === "eventType") { state.eventFilters.type = event.target.value; renderEvents(); }
  if (event.target.id === "eventDirection") { state.eventFilters.direction = event.target.value; renderEvents(); }
  if (event.target.id === "historyAction") { state.historyAction = event.target.value; renderHistory(); }
}

function handleInput(event) {
  if (event.isComposing || event.target.dataset.composing === "true") return;
  if (event.target.id === "candidateSearch") { state.candidateFilters.query = event.target.value; renderCandidates(); $("#candidateSearch")?.focus(); $("#candidateSearch")?.setSelectionRange(state.candidateFilters.query.length, state.candidateFilters.query.length); }
  if (event.target.id === "eventSearch") { state.eventFilters.query = event.target.value; renderEvents(); $("#eventSearch")?.focus(); $("#eventSearch")?.setSelectionRange(state.eventFilters.query.length, state.eventFilters.query.length); }
  if (event.target.id === "historySearch") { state.historyQuery = event.target.value; renderHistory(); $("#historySearch")?.focus(); $("#historySearch")?.setSelectionRange(state.historyQuery.length, state.historyQuery.length); }
}

function handleKeyboard(event) {
  const row = event.target.closest('[data-action="select-candidate"], [data-action="select-event"], [data-action="select-history"]');
  if (row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); row.click(); }
}

function updateClock() {
  $("#currentTime").textContent = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date()).replaceAll("/", "-");
}

let resizeTimer;
function handleResize() {
  clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    if (state.tab === "decision") {
      const candidate = liveMerged(currentCandidate(marketDecision(state.snapshot)), state.market);
      drawCandleChart($("#decisionChart"), candidate);
    }
    if (state.tab === "history") drawHistoryChart($("#historyChart"), filteredHistory().slice().reverse(), state.historyMarket);
  }, 100);
}

async function initialize() {
  updateClock(); window.setInterval(updateClock, 1000);
  document.addEventListener("click", handleClick);
  document.addEventListener("change", handleChange);
  document.addEventListener("input", handleInput);
  document.addEventListener("compositionstart", (event) => { if (event.target.matches?.("#candidateSearch, #eventSearch, #historySearch")) event.target.dataset.composing = "true"; });
  document.addEventListener("compositionend", (event) => { if (event.target.matches?.("#candidateSearch, #eventSearch, #historySearch")) { event.target.dataset.composing = "false"; handleInput(event); } });
  document.addEventListener("keydown", handleKeyboard);
  window.addEventListener("resize", handleResize);
  window.addEventListener("hashchange", () => switchTab(location.hash.slice(1), false));
  $("#refreshBtn").addEventListener("click", refreshAll);
  try {
    const [statusResult, historyResult, latestResult] = await Promise.allSettled([
      getJson("/api/status"), getJson("/api/history?limit=120"), getJson("/api/latest"),
    ]);
    state.status = statusResult.status === "fulfilled" ? statusResult.value : { ok: false };
    state.history = historyResult.status === "fulfilled" ? historyResult.value.history || [] : [];
    if (latestResult.status !== "fulfilled") throw latestResult.reason;
    state.snapshot = latestResult.value;
    const first = allCandidates()[0];
    if (first) state.candidateKey = candidateId(first.candidate, first.market);
    renderRail();
    switchTab(location.hash.slice(1) || "decision", false);
  } catch (error) {
    updateTopbar();
    $$(".view-loading").forEach((view) => { view.innerHTML = `<div class="empty-state">${icon("ph-warning-circle")}<h3>无法读取决策快照</h3><p>${esc(error.message || "请稍后刷新")}</p><button class="icon-button" type="button" onclick="location.reload()">重新加载</button></div>`; });
    showToast(error.message || "初始化失败", "error");
  }
}

initialize();

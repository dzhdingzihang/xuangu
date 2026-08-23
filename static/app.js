const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const MARKET_ORDER = ["a_share", "hk", "us"];
const MARKET_META = {
  a_share: { label: "A股", short: "A", currency: "CNY", dot: "market-a" },
  hk: { label: "港股", short: "港", currency: "HKD", dot: "market-hk" },
  us: { label: "美股", short: "美", currency: "USD", dot: "market-us" },
};
const TAB_META = {
  decision: ["今日答案", "未来 10 个交易日跨市场决策"],
  candidates: ["候选池", "跨市场研究优先级与完整评分证据"],
  events: ["事件证据", "公告、财报与监管文件的可追溯证据流"],
  history: ["历史检验", "10 日预测、概率校准与版本失效分析"],
  model: ["模型逻辑", "从三市场有界动态召回到可执行候选的完整链路"],
  health: ["数据健康", "覆盖率、时效性与决策可用性的分层监控"],
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
  quote_valuation_core_v1: "快照行情 + PE / PB / 总市值核心字段",
};
const POOL_HEALTH_REASON_META = {
  POOL_COVERAGE_INSUFFICIENT: "候选池或报价覆盖未达安全阈值",
  BROAD_POOL_BELOW_MINIMUM: "全市场宽基池低于最低数量",
  POOL_TARGET_NOT_MET: "实际召回未达到市场目标",
  BOARD_QUOTA_PARTIAL: "A 股板块配额未完整达标",
  CORE_BOARD_MISSING: "A 股存在整个板块未召回",
  MERGED_POOL_EMPTY: "合并候选池为空",
  QUOTE_COVERAGE_BELOW_MINIMUM: "候选报价覆盖率低于最低要求",
  A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM: "A 股全池技术评分覆盖低于 98%",
  A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM: "A 股深度研究完成率低于 98%",
  A_SHARE_KLINE_COVERAGE_BELOW_MINIMUM: "旧快照：A 股深度评分 K 线覆盖低于 98%",
  DYNAMIC_DISCOVERY_CACHE_USED: "本轮公开市场发现失败，正在使用最近一次动态池缓存",
  DYNAMIC_DISCOVERY_PARTIAL: "公开市场横截面请求存在分页缺口",
  DYNAMIC_DISCOVERY_STALE: "公开市场横截面不是最近交易时段",
  DYNAMIC_DISCOVERY_SOURCE_TIME_UNAVAILABLE: "备用榜单没有可验证的市场源时间，仅供研究",
  DYNAMIC_DISCOVERY_BELOW_MINIMUM: "动态发现宽度低于最低要求",
  DYNAMIC_RECALL_TARGET_NOT_MET: "动态入池没有达到 200/300 目标",
  DYNAMIC_RECALL_MANIFEST_INVALID: "动态召回来源清单不完整",
  DYNAMIC_RECALL_CONTRACT_INCOMPLETE: "动态召回契约不完整",
  DYNAMIC_QUOTE_COVERAGE_BELOW_MINIMUM: "动态池有效行情覆盖低于 98%",
  DYNAMIC_SCORE_COVERAGE_BELOW_MINIMUM: "动态池完整深评覆盖低于 98%",
  DYNAMIC_REALTIME_COVERAGE_BELOW_MINIMUM: "动态池最近市场时段行情覆盖低于 98%",
};
const GLOBAL_BLOCKER_META = {
  SNAPSHOT_NOT_FRESH: "快照状态不是 fresh",
  GLOBAL_DECISION_MISSING: "当前发布快照尚未包含跨市场十日契约",
  MARKET_COVERAGE_INCOMPLETE: "至少一个市场的召回、行情或市场上下文不完整",
  EXTERNAL_EVIDENCE_MISSING: "没有可进入自动决策的官方外部证据",
  TEN_DAY_PROBABILITY_UNCALIBRATED: "十日正收益概率尚未样本外校准",
  TRANSACTION_COST_MODEL_MISSING: "交易成本模型尚未就绪",
  TAIL_RISK_MODEL_MISSING: "尾部风险模型尚未就绪",
  TEN_DAY_MODEL_NOT_AUTHORIZED: "十日模型尚未获准参与正式决策",
  NO_CANDIDATE_PASSED_STRICT_GATE: "没有候选通过全部严格门禁",
  POOL_COVERAGE_INCOMPLETE: "候选池覆盖未达到跨市场比较要求",
  CURATED_STATIC_UNIVERSE: "当前市场仍使用精选静态股票池",
  DYNAMIC_DISCOVERY_CACHE_USED: "当前市场使用上次健康动态池，仅供研究",
  DYNAMIC_RECALL_CONTRACT_INCOMPLETE: "动态市场召回契约缺失或来源不明",
  MARKET_CONTEXT_MISSING: "市场状态与基准上下文缺失",
  QUOTE_HEALTH_INCOMPLETE: "行情覆盖率或源时间不完整",
};
const STATUS_POLL_INTERVAL_MS = 5 * 60 * 1000;
const HISTORY_LIMIT = 1000;
const FRESHNESS_META = {
  fresh: { label: "数据正常", icon: "ph-check-circle", className: "is-fresh" },
  updating: { label: "更新中", icon: "ph-arrows-clockwise", className: "is-updating" },
  stale: { label: "数据已过期", icon: "ph-warning-circle", className: "is-stale" },
  unknown: { label: "状态未知", icon: "ph-question", className: "is-unknown" },
};
const MANUAL_RESEARCH_EVIDENCE = [
  {
    event_id: "manual:us:NTNX:2026-08-26-results",
    event_type: "manual_external",
    market: "us",
    symbol: "NTNX",
    company: "Nutanix",
    title: "Nutanix 将于 8 月 26 日美股收盘后发布 FY2026 Q4 / 全年业绩",
    source: "Nutanix Investor Relations",
    published_at: "2026-08-06T08:00:00-07:00",
    effective_at: "2026-08-26T16:00:00-04:00",
    direction: "neutral",
    impact_score: null,
    url: "https://ir.nutanix.com/news-releases/news-release-details/nutanix-announces-date-and-conference-call-information-fiscal-6",
    evidence_status: "manual_verified_pending_ingestion",
    note: "官方原文已经人工核验，但尚未由自动事件管道入库，因此只用于研究提示，不参与自动买入门禁。",
  },
  {
    event_id: "manual:hk:0941:2026-08-25-ex-date",
    event_type: "manual_external",
    market: "hk",
    symbol: "0941.HK",
    company: "中国移动",
    title: "中国移动 8 月 25 日除净；中期股息每股人民币 2.51 元",
    source: "香港交易所权益披露表",
    published_at: "2026-08-20T18:00:00+08:00",
    effective_at: "2026-08-25T00:00:00+08:00",
    direction: "neutral",
    impact_score: null,
    url: "https://www3.hkexnews.hk/reports/doe/eent.htm",
    evidence_status: "manual_verified_pending_ingestion",
    note: "官方页面已经人工核验，但尚未由自动事件管道入库；除息会影响价格口径，不能直接解释为正面催化。",
  },
];

const state = {
  tab: "decision",
  market: "a_share",
  snapshot: null,
  history: [],
  historyMeta: {},
  historyError: "",
  status: null,
  candidateKey: "",
  candidateFilters: { market: "all", risk: "all", route: "all", query: "" },
  eventKey: "",
  eventFilters: { market: "all", type: "all", direction: "all", query: "" },
  historyKey: "",
  historyMarket: "a_share",
  historyAction: "all",
  historyQuery: "",
  historySnapshot: null,
  historySnapshotKey: "",
  historyArchiveOpen: true,
  compare: [],
  eventAuditOpen: false,
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

function ratioPct(value, digits = 1) {
  if (!Number.isFinite(Number(value))) return "--";
  return `${(Number(value) * 100).toFixed(digits)}%`;
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
    const raw = String(value || "").trim();
    if (!raw) return "";
    const parsed = new URL(raw, location.origin);
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

function poolHealthState(section, decision) {
  const health = section.pool_health || {};
  const blockerCodes = Array.isArray(decision.blocker_codes) ? decision.blocker_codes : [];
  const reasonCodes = Array.isArray(health.reason_codes) ? health.reason_codes : [];
  const healthState = String(health.state || health.status || health.data_state || "").toUpperCase();
  const poolBlocker = blockerCodes.some((code) => /POOL_COVERAGE|UNIVERSE_COVERAGE|BROAD_POOL|QUOTE_COVERAGE|DYNAMIC_/i.test(String(code)));
  const degraded = healthState === "DEGRADED" || poolBlocker || reasonCodes.length > 0;
  const stats = section.stats || {};
  const broadPoolSize = health.broad_pool_count ?? health.broad_pool_size ?? stats.broad_pool_size;
  const coverage = health.quote_coverage ?? health.coverage_ratio ?? health.coverage_pct;
  return { health, blockerCodes, reasonCodes, degraded, broadPoolSize, coverage };
}

function recallFunnel(section, marketKey = null) {
  const stats = section?.stats || {};
  const quoteHealth = section?.quote_health || {};
  const resolvedMarket = marketKey || section?.key;
  const fallbackPool = Math.max(num(stats.universe_size), num(stats.raw_pool_size));
  const expectedTarget = { a_share: 300, hk: 200, us: 300 }[resolvedMarket] || fallbackPool;
  const publishedTarget = num(stats.recall_target, NaN);
  const target = Number.isFinite(publishedTarget) && publishedTarget > 0 ? publishedTarget : expectedTarget;
  const selected = num(stats.recall_selected_size, fallbackPool);
  const validQuotes = num(stats.valid_quote_size, num(quoteHealth.quote_count));
  const deepScored = num(stats.deep_scored_size, num(stats.scored_size));
  const deepAttempted = num(stats.deep_attempted_size, deepScored);
  const fullStageFields = [
    "base_scored_size",
    "technical_attempted_size",
    "technical_scored_size",
    "technical_kline_complete_size",
    "technical_kline_coverage",
    "deep_eligible_size",
  ];
  const hasFullScoringStages = resolvedMarket === "a_share"
    && fullStageFields.every((field) => Object.prototype.hasOwnProperty.call(stats, field) && Number.isFinite(Number(stats[field])));
  const baseScored = hasFullScoringStages ? num(stats.base_scored_size) : validQuotes;
  const technicalAttempted = hasFullScoringStages ? num(stats.technical_attempted_size) : deepAttempted;
  const technicalScored = hasFullScoringStages ? num(stats.technical_scored_size) : deepScored;
  const technicalKlineComplete = hasFullScoringStages ? num(stats.technical_kline_complete_size) : deepScored;
  const deepEligible = hasFullScoringStages ? num(stats.deep_eligible_size) : deepAttempted;
  return { target, selected, validQuotes, baseScored, technicalAttempted, technicalScored, technicalKlineComplete, deepEligible, deepAttempted, deepScored, hasFullScoringStages };
}

function poolHealthAlert(section, decision) {
  const poolHealth = poolHealthState(section, decision);
  if (!poolHealth.degraded) return "";
  const textReasons = Array.isArray(poolHealth.health.reasons) ? poolHealth.health.reasons : [];
  const codedReasons = poolHealth.reasonCodes.map((code) => POOL_HEALTH_REASON_META[code] || code);
  const codedBlockers = poolHealth.blockerCodes.map((code) => POOL_HEALTH_REASON_META[code] || code);
  const reasons = [...textReasons, ...codedReasons];
  const detail = poolHealth.health.message
    || reasons[0]
    || (codedBlockers.length ? codedBlockers.join(" · ") : "全市场宽基或关键召回来源没有达到完整覆盖要求");
  const metrics = [];
  if (poolHealth.broadPoolSize !== null && poolHealth.broadPoolSize !== undefined && Number.isFinite(Number(poolHealth.broadPoolSize))) metrics.push(`宽基池 ${fmt(poolHealth.broadPoolSize, 0)} 只`);
  if (poolHealth.coverage !== null && poolHealth.coverage !== undefined && Number.isFinite(Number(poolHealth.coverage))) {
    const coveragePct = Number(poolHealth.coverage) <= 1 ? Number(poolHealth.coverage) * 100 : Number(poolHealth.coverage);
    metrics.push(`覆盖率 ${fmt(coveragePct, 0)}%`);
  }
  return `<div class="pool-health-alert" role="alert">${icon("ph-warning-octagon")}<div><strong>候选池降级 · 覆盖不足</strong><p>${esc(detail)}。当前结果可用于观察，但不能视为完整市场筛选结论。</p>${metrics.length ? `<small>${esc(metrics.join(" · "))}</small>` : ""}</div></div>`;
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
  return ({ primary: "Legacy首选", blocked: "门槛未过", watchlist: "观察候选" })[role] || "观察候选";
}

function allCandidates() {
  return MARKET_ORDER.flatMap((market) => candidatesFor(state.snapshot, market).map((candidate, index) => ({
    candidate,
    market,
    legacyRank: index + 1,
    decisionRole: candidateDecisionRole(candidate, market),
  })));
}

function automaticExternalEvents() {
  const items = state.snapshot?.events?.items;
  if (!Array.isArray(items)) return [];
  const generated = Date.parse(state.snapshot?.generated_at || "");
  const generatedDay = String(state.snapshot?.generated_at || "").slice(0, 10);
  const forecastEndDay = String(state.snapshot?.forecast_end_date || "").slice(0, 10);
  const windowStart = Date.parse(`${generatedDay}T00:00:00+08:00`);
  const windowEnd = Date.parse(`${forecastEndDay}T23:59:59.999+08:00`);
  if (![generated, windowStart, windowEnd].every(Number.isFinite)) return [];
  return items.filter((event) => {
    if (event.event_type === "model_signal" || event.event_type === "manual_external") return false;
    const published = Date.parse(event.published_at || "");
    const effective = Date.parse(event.effective_at || "");
    return event.decision_eligible === true
      && String(event.ingestion_mode || "").toLowerCase() === "automatic"
      && ["verified", "confirmed"].includes(String(event.evidence_status || "").toLowerCase())
      && ["official", "regulatory", "exchange"].includes(String(event.source_tier || "").toLowerCase())
      && String(event.direction || "").toLowerCase() === "positive"
      && !event.revoked_at
      && Boolean(event.market && event.symbol && event.source && String(event.url || "").startsWith("https://"))
      && Number.isFinite(published)
      && Number.isFinite(effective)
      && published <= generated
      && published >= generated - 45 * 24 * 60 * 60 * 1000
      && effective >= windowStart
      && effective <= windowEnd;
  });
}

function automaticExternalEvidenceCount(snapshot = state.snapshot) {
  const serverCount = snapshot?.global_decision?.automatic_external_evidence_count;
  return typeof serverCount === "number" && Number.isFinite(serverCount) && serverCount >= 0
    ? serverCount
    : automaticExternalEvents().length;
}

function manualEvidenceForSnapshot(snapshot = state.snapshot) {
  const startDate = String(snapshot?.target_date || snapshot?.generated_at || "").slice(0, 10);
  const endDate = String(snapshot?.forecast_end_date || "").slice(0, 10);
  const windowStart = Date.parse(`${startDate}T00:00:00+08:00`);
  const windowEnd = Date.parse(`${endDate}T23:59:59+08:00`);
  if (!Number.isFinite(windowStart) || !Number.isFinite(windowEnd)) return [];
  return MANUAL_RESEARCH_EVIDENCE.filter((event) => {
    const effective = Date.parse(event.effective_at || "");
    return Number.isFinite(effective) && effective >= windowStart && effective <= windowEnd;
  });
}

function tenDayModelState(snapshot = state.snapshot) {
  const model = snapshot?.analysis_models?.ten_day_return || snapshot?.forecast_10d || snapshot?.global_decision?.model_state || {};
  const status = String(model.status || model.calibration_status || "").toUpperCase();
  const calibrated = model.calibrated === true && ["READY", "CALIBRATED", "PRODUCTION"].includes(status);
  const costsReady = model.costs_ready === true || model.transaction_costs_ready === true;
  const tailReady = model.tail_risk_ready === true || model.expected_shortfall_ready === true;
  const participates = model.participates_in_decision === true;
  return { model, calibrated, costsReady, tailReady, participates, ready: calibrated && costsReady && tailReady && participates };
}

function marketCoverageState(market, snapshot = state.snapshot) {
  const section = marketSection(snapshot, market);
  const decision = section.decision || {};
  const pool = poolHealthState(section, decision);
  const stats = section.stats || {};
  const origin = String(stats.universe_origin || section.universe_origin || "").toLowerCase();
  const regime = typeof section.market_regime === "string" ? section.market_regime : section.market_regime?.state;
  const primary = decision.primary || null;
  const candidateBlocked = Boolean(primary && (primary.execution_state === "BLOCKED" || (primary.decision_gates || []).some((gate) => gate.status === "BLOCK")));
  const quoteHealth = section.quote_health || {};
  const quoteCoverage = num(quoteHealth.quote_coverage, 0);
  const realtimeCoverage = num(quoteHealth.realtime_coverage, quoteCoverage);
  const serverState = snapshot?.global_decision?.market_states?.[market];
  const reasons = [];
  if (pool.degraded) reasons.push("候选池覆盖不足");
  const expectedOrigin = market === "a_share" ? "dynamic_snapshot" : "dynamic_market_snapshot";
  if (["curated_static", "curated_fallback"].includes(origin)) reasons.push("仅静态精选池，并非动态市场召回");
  else if (origin === "dynamic_market_snapshot_cache") reasons.push("使用上次动态池缓存，本轮不执行推荐");
  else if (origin !== expectedOrigin) reasons.push("动态召回来源契约不完整");
  if (!regime || regime === "unknown") reasons.push("市场状态证据不足");
  if (quoteHealth.status !== "available" || quoteCoverage < 0.98 || realtimeCoverage < 0.98) reasons.push("行情覆盖或源时间不完整");
  if (candidateBlocked) reasons.push("候选存在客观阻断");
  const coverageReasons = reasons.filter((reason) => reason !== "候选存在客观阻断");
  const derivedState = pool.degraded ? "BLOCKED" : coverageReasons.length ? "DEGRADED" : "READY";
  const serverStateName = ["READY", "DEGRADED", "BLOCKED"].includes(serverState?.state) ? serverState.state : derivedState;
  const severity = { READY: 0, DEGRADED: 1, BLOCKED: 2 };
  const stateName = severity[serverStateName] >= severity[derivedState] ? serverStateName : derivedState;
  const serverReasons = (serverState?.reason_codes || []).map((code) => GLOBAL_BLOCKER_META[code] || code);
  return { market, section, decision, pool, stats, origin, regime, primary, candidateBlocked, quoteHealth, reasons: [...new Set([...reasons, ...serverReasons])], state: stateName };
}

function researchPriorityCandidate(snapshot = state.snapshot) {
  const serverPriority = snapshot?.global_decision?.research_priority;
  if (serverPriority && typeof serverPriority === "object") {
    const market = serverPriority.market;
    const code = String(serverPriority.code || serverPriority.symbol || "").toLowerCase();
    const candidate = candidatesFor(snapshot, market).find((row) => String(row.code || row.symbol || "").toLowerCase() === code);
    if (candidate) {
      const legacyRank = candidatesFor(snapshot, market).indexOf(candidate) + 1;
      return { market, candidate, legacyRank, coverage: marketCoverageState(market, snapshot), source: "server" };
    }
  }
  const rows = MARKET_ORDER.flatMap((market) => candidatesFor(snapshot, market).map((candidate, index) => ({
    market,
    candidate,
    legacyRank: index + 1,
    coverage: marketCoverageState(market, snapshot),
  })));
  const viable = rows.filter((row) => row.coverage.state !== "BLOCKED" && !row.coverage.candidateBlocked && row.candidate.execution_state !== "BLOCKED");
  const scored = viable.length ? viable : rows;
  return scored.sort((left, right) => {
    const evidenceScore = (row) => {
      const symbol = String(row.candidate?.code || row.candidate?.symbol || "").toLowerCase();
      return automaticExternalEvents().some((event) => event.market === row.market && String(event.symbol || "").toLowerCase() === symbol) ? 1 : 0;
    };
    const evidenceDelta = evidenceScore(right) - evidenceScore(left);
    if (evidenceDelta) return evidenceDelta;
    const leftQuality = num(left.candidate?.data_quality?.score, 0);
    const rightQuality = num(right.candidate?.data_quality?.score, 0);
    if (rightQuality !== leftQuality) return rightQuality - leftQuality;
    const leftV2 = left.candidate?.v2?.rank && left.candidate?.v2?.rank_universe_size
      ? 1 - num(left.candidate.v2.rank) / num(left.candidate.v2.rank_universe_size, 1) : 0;
    const rightV2 = right.candidate?.v2?.rank && right.candidate?.v2?.rank_universe_size
      ? 1 - num(right.candidate.v2.rank) / num(right.candidate.v2.rank_universe_size, 1) : 0;
    if (rightV2 !== leftV2) return rightV2 - leftV2;
    return num(candidateScore(right.candidate), -Infinity) - num(candidateScore(left.candidate), -Infinity);
  })[0] || null;
}

function globalDecisionTruth(snapshot = state.snapshot) {
  const serverDecision = snapshot?.global_decision;
  const modelState = tenDayModelState(snapshot);
  const markets = MARKET_ORDER.map((market) => marketCoverageState(market, snapshot));
  const autoEvidence = automaticExternalEvents();
  const autoEvidenceCount = automaticExternalEvidenceCount(snapshot);
  const freshness = state.status?.freshness_state || "unknown";
  const fresh = freshness === "fresh";
  const research = researchPriorityCandidate(snapshot);
  const serverPrimary = serverDecision?.primary;
  const finiteNumber = (value) => typeof value === "number" && Number.isFinite(value);
  const primaryMarket = String(serverPrimary?.market || "");
  const primaryCode = String(serverPrimary?.code || serverPrimary?.symbol || "").toLowerCase();
  const primaryCandidate = MARKET_ORDER.includes(primaryMarket)
    ? candidatesFor(snapshot, primaryMarket).find((candidate) => String(candidate.code || candidate.symbol || "").toLowerCase() === primaryCode)
    : null;
  const serverBlockers = Array.isArray(serverDecision?.blocker_codes) ? serverDecision.blocker_codes : [];
  const allMarketsReady = markets.length === MARKET_ORDER.length && markets.every((item) => item.state === "READY");
  const candidateHasEvidence = Boolean(primaryCandidate && autoEvidence.some((event) => {
    return event.market === primaryMarket && String(event.symbol || "").toLowerCase() === primaryCode;
  }));
  const primaryReady = Boolean(serverPrimary
    && serverPrimary.status === "EXECUTABLE"
    && serverPrimary.score_kind === "TEN_DAY_EXPECTED_NET_UTILITY"
    && serverPrimary.calibrated === true
    && finiteNumber(serverPrimary.probability)
    && serverPrimary.probability >= 0
    && serverPrimary.probability <= 1
    && finiteNumber(serverPrimary.expected_net_utility)
    && serverPrimary.expected_net_utility > 0
    && finiteNumber(serverPrimary.transaction_cost)
    && serverPrimary.transaction_cost >= 0
    && finiteNumber(serverPrimary.tail_risk)
    && serverPrimary.tail_risk >= 0
    && serverPrimary.model_id);
  const ready = Boolean(
    fresh
    && modelState.ready
    && serverDecision?.contract_version === "global-10d-v1"
    && serverDecision?.decision_scope === "global_10d"
    && serverDecision?.action === "REVIEW_EXECUTABLE_PICK"
    && serverDecision?.action_basis === "strict_cross_market_gate_v1"
    && serverDecision?.calibrated === true
    && serverDecision?.probability_status === "CALIBRATED"
    && finiteNumber(serverDecision?.probability)
    && serverDecision.probability === serverPrimary?.probability
    && serverBlockers.length === 0
    && allMarketsReady
    && autoEvidenceCount > 0
    && candidateHasEvidence
    && primaryReady
    && serverPrimary.model_id === modelState.model.model_id
  );
  const blockerCodes = [];
  if (!fresh) blockerCodes.push("SNAPSHOT_NOT_FRESH");
  if (!serverDecision) blockerCodes.push("GLOBAL_DECISION_MISSING");
  if (markets.some((item) => item.state !== "READY")) blockerCodes.push("MARKET_COVERAGE_INCOMPLETE");
  if (!autoEvidenceCount) blockerCodes.push("EXTERNAL_EVIDENCE_MISSING");
  if (!modelState.calibrated) blockerCodes.push("TEN_DAY_PROBABILITY_UNCALIBRATED");
  if (!modelState.costsReady) blockerCodes.push("TRANSACTION_COST_MODEL_MISSING");
  if (!modelState.tailReady) blockerCodes.push("TAIL_RISK_MODEL_MISSING");
  if (!modelState.participates) blockerCodes.push("TEN_DAY_MODEL_NOT_AUTHORIZED");
  if (!ready) blockerCodes.push("NO_CANDIDATE_PASSED_STRICT_GATE");
  return {
    action: ready ? "REVIEW_EXECUTABLE_PICK" : "NO_VALID_PICK",
    actionBasis: serverDecision?.action_basis || "strict_cross_market_gate_v1",
    probabilityStatus: modelState.calibrated ? "CALIBRATED" : "UNAVAILABLE",
    probability: ready ? serverPrimary.probability : null,
    calibrated: modelState.calibrated,
    executableCount: ready ? 1 : 0,
    autoEvidenceCount,
    markets,
    blockerCodes: [...new Set([...(serverDecision?.blocker_codes || []), ...blockerCodes])],
    research,
    executable: ready ? {
      market: primaryMarket,
      candidate: primaryCandidate,
      primary: serverPrimary,
      legacyRank: candidatesFor(snapshot, primaryMarket).indexOf(primaryCandidate) + 1,
    } : null,
    serverDecision,
  };
}

function candidateScore(candidate) {
  const value = candidate?.recommendation_degree ?? candidate?.confidence;
  return value === null || value === undefined || value === "" ? NaN : num(value, NaN);
}

function candidateQuoteView(candidate) {
  const quote = candidate?.realtime;
  const observedPrice = num(quote?.price, NaN);
  const sourceAsOf = typeof quote?.source_as_of === "string" ? quote.source_as_of.trim() : "";
  const fetchedAt = typeof quote?.fetched_at === "string" ? quote.fetched_at.trim() : "";
  const volumeUnit = typeof quote?.volume_unit === "string" ? quote.volume_unit : "";
  const observed = Number.isFinite(observedPrice)
    && observedPrice > 0
    && sourceAsOf
    && fetchedAt
    && ["lot", "share", "shares"].includes(volumeUnit);
  if (observed) {
    const source = quote.source || "已发布选股快照";
    const session = quote.session_label || quote.session || "时段未知";
    return {
      kind: "observed_quote",
      title: "快照行情",
      price: observedPrice,
      changePct: num(quote.change_pct ?? candidate?.current_change_pct, NaN),
      label: `${source} · ${session} · 源时间 ${dateTime(sourceAsOf)}`,
    };
  }
  const planPrice = num(candidate?.entry_price ?? candidate?.price, NaN);
  return {
    kind: "plan_price",
    title: "计划价（非行情）",
    price: planPrice,
    changePct: NaN,
    label: "行情未记录 · 源时间未记录 · 仅展示快照内计划参考价",
  };
}

function candidateChangePct(candidate) {
  return candidateQuoteView(candidate).changePct;
}

function snapshotQuoteLabel(candidate) {
  return candidateQuoteView(candidate).label;
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

function candidateRiskLevel(candidate, market) {
  const candidateLevel = riskLevel(candidate);
  const marketState = marketCoverageState(market).state;
  if (marketState === "BLOCKED" || candidateLevel === "blocked") return "blocked";
  if (marketState === "DEGRADED" || candidateLevel === "warning") return "warning";
  return "clear";
}

function labelForRegime(regime) {
  const stateName = typeof regime === "string" ? regime : regime?.state;
  return ({ trend_risk_on: "趋势偏多", range: "区间震荡", high_vol: "高波动", risk_off: "风险规避", unknown: "证据不足" })[stateName] || "证据不足";
}

function actionLabel(decision) {
  if (decision?.primary) return "LEGACY BUY_CANDIDATE";
  if (decision?.blocked_candidate) return "LEGACY NO_TRADE";
  return String(decision?.action || "NO SIGNAL").replaceAll("_", " ");
}

function recommendationLabel(candidate, hasPrimary = true) {
  if (!hasPrimary) return "Legacy 未通过";
  const score = candidateScore(candidate);
  if (score >= 72) return "Legacy 高优先";
  if (score >= 62) return "Legacy 优先观察";
  return "Legacy 观察";
}

function executionAdvice(candidate, hasPrimary) {
  if (!candidate || !hasPrimary) return { tone: "negative", label: "不买", text: "本轮门槛未通过，保留现金并等待下一份不可变快照。", deviation: null };
  if (candidate.execution_state === "BLOCKED" || (candidate.decision_gates || []).some((gate) => gate.status === "BLOCK")) {
    return { tone: "negative", label: "暂不执行", text: "候选虽通过 Legacy 排名，但 V2 客观门控发现不可执行条件；先修复行情、K线或交易状态证据。", deviation: null };
  }
  const quoteView = candidateQuoteView(candidate);
  if (quoteView.kind !== "observed_quote") {
    return { tone: "warning", label: "行情未记录", text: "本快照只保存了计划参考价，缺少可追溯行情与源时间；不计算价格偏离，不应据此执行。", deviation: null };
  }
  const current = quoteView.price;
  const entry = num(candidate.entry_price || candidate.price, NaN);
  const stop = num(candidate.stop_loss, NaN);
  const take = num(candidate.take_profit_reference, NaN);
  const deviation = Number.isFinite(entry) && Number.isFinite(current) ? ((current - entry) / entry) * 100 : null;
  if (Number.isFinite(stop) && current <= stop) return { tone: "negative", label: "取消执行", text: "当前价已触及止损区，走势没有按原计划兑现。", deviation };
  if (Number.isFinite(take) && current >= take * 0.98) return { tone: "warning", label: "不追高", text: "当前价已接近止盈参考，继续追买的盈亏比不足。", deviation };
  if (Number.isFinite(entry) && current > entry * 1.03) return { tone: "warning", label: "等回落", text: "当前价高于快照建议价 3% 以上，等待回到计划区。", deviation };
  if (Number.isFinite(entry) && current >= entry * 0.985 && current <= entry * 1.01) return { tone: "positive", label: "进入复核区", text: "当前价仍在计划区附近；是否执行必须继续服从 global 严格门禁。", deviation };
  return { tone: "warning", label: "继续观察", text: "当前价偏离计划区，等待价格回归并重新检查 global 严格门禁。", deviation };
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

async function getJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", headers: { accept: "application/json" }, ...options });
  let payload;
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.message || payload.error || `请求失败 ${response.status}`);
  return payload;
}

async function getHistoryPayload() {
  try {
    const payload = await getJson(`/api/history?limit=${HISTORY_LIMIT}`);
    state.historyError = "";
    return payload;
  } catch (error) {
    state.historyError = error.message || "历史清单读取失败";
    throw error;
  }
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
    const coverage = marketCoverageState(market);
    const label = coverage.state === "READY" ? "可评估" : coverage.state === "BLOCKED" ? "阻断" : "降级";
    return `<button class="rail-market-row" type="button" data-action="market" data-market="${market}" title="切换到${MARKET_META[market].label}">
      ${marketBadge(market)}<span><b>${MARKET_META[market].label}</b><small class="${coverage.state === "BLOCKED" ? "negative" : coverage.state === "DEGRADED" ? "warning" : "positive"}">${esc(label)}</small></span>
    </button>`;
  }).join("");
}

function updateTopbar() {
  const [title, subtitle] = TAB_META[state.tab];
  $("#pageTitle").textContent = title;
  $("#pageSubtitle").textContent = subtitle;
  const snapshotAsOf = state.status?.snapshot_as_of || state.snapshot?.generated_at;
  const nextRefresh = state.status?.next_refresh;
  $("#snapshotAsOf").textContent = dateTime(snapshotAsOf);
  $("#nextRefreshTime").textContent = dateTime(nextRefresh);
  const health = $("#healthBadge");
  const freshnessState = state.snapshot && state.status?.ok !== false
    ? state.status?.freshness_state || "unknown"
    : "unknown";
  const freshness = FRESHNESS_META[freshnessState] || FRESHNESS_META.unknown;
  health.className = `health-badge ${freshness.className}`;
  health.innerHTML = `${icon(freshness.icon)}${freshness.label}`;
  const checkpoint = state.status?.expected_checkpoint ? dateTime(state.status.expected_checkpoint) : "--";
  const lagValue = state.status?.checkpoint_lag_minutes;
  const lag = lagValue !== null && lagValue !== undefined && Number.isFinite(Number(lagValue)) ? `${fmt(lagValue, 0)} 分钟` : "--";
  health.title = `${freshness.label}；快照生成 ${dateTime(snapshotAsOf)}；下次计划检查点（含健康补跑） ${dateTime(nextRefresh)}；最近应完成检查点 ${checkpoint}；快照落后 ${lag}`;
  health.setAttribute("aria-label", health.title);

  const quality = $("#qualityBadge");
  const sections = Object.entries(state.snapshot?.markets || {});
  const poolDegraded = sections.filter(([, section]) => poolHealthState(section || {}, section?.decision || {}).degraded);
  const quoteUnavailable = sections.filter(([, section]) => section?.quote_health?.status === "unavailable");
  const otherRestricted = sections.filter(([, section]) => {
    const decision = section?.decision || {};
    return decision.data_state === "DEGRADED" && !poolHealthState(section || {}, decision).degraded;
  });
  const restricted = [...new Set([...poolDegraded, ...quoteUnavailable, ...otherRestricted].map(([market]) => market))];
  quality.hidden = restricted.length === 0;
  if (restricted.length) {
    const labels = restricted.map((market) => MARKET_META[market]?.label || market).join("、");
    const label = poolDegraded.length ? "候选池降级" : quoteUnavailable.length ? "行情不可用" : "部分市场受限";
    quality.className = "health-badge is-degraded";
    quality.innerHTML = `${icon("ph-warning-octagon")}${label}`;
    quality.title = `${labels}：${label}；快照新鲜度与数据完整度分开判断`;
    quality.setAttribute("aria-label", quality.title);
  }
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
      key: "legacy", icon: "ph-seal-check", label: "Legacy 市场信号", value: legacyAction,
      meta: `推荐度 ${fmt(candidateScore(candidate), 0)}/100 · Legacy #${row?.legacyRank || "--"}`,
      note: role === "primary" ? "市场内 Legacy 首选；只有 global 严格门禁通过才能升级为可执行复核" : role === "blocked" ? "最接近阈值，但当前不执行" : "保留观察，不代表买入信号",
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

function renderLegacyMarketDecision() {
  const root = $("#decisionView");
  const section = marketSection(state.snapshot);
  const decision = section.decision || {};
  const baseCandidate = currentCandidate(decision);
  if (!baseCandidate) {
    root.innerHTML = `<div class="toolbar"><div><h2>${MARKET_META[state.market].label}决策</h2><p>${esc(decision.message || "本轮没有保存候选")}</p></div>${marketSwitch()}</div>${poolHealthAlert(section, decision)}<div class="empty-state">${icon("ph-magnifying-glass")}<h3>没有可展示候选</h3><p>系统没有在当前数据证据下产生可执行候选，请查看其他市场或历史快照。</p></div>`;
    return;
  }
  const candidate = baseCandidate;
  const stats = section.stats || {};
  const range = candidate.estimated_2w_range || candidate.estimated_2d_range || {};
  const hasPrimary = Boolean(decision.primary);
  const advice = executionAdvice(candidate, hasPrimary);
  const quoteView = candidateQuoteView(candidate);
  const objectivelyBlocked = candidate.execution_state === "BLOCKED" || (candidate.decision_gates || []).some((gate) => gate.status === "BLOCK");
  const regime = section.market_regime || candidate.v2?.regime || candidate.v2?.market_regime;
  const funnel = recallFunnel(section, state.market);
  const shown = candidatesFor(state.snapshot, state.market).length;
  const scoringKpis = state.market === "a_share" && funnel.hasFullScoringStages
    ? [
      { icon: "ph-database", label: "有效行情 / 基础评分", value: `${fmt(funnel.validQuotes, 0)} / ${fmt(funnel.baseScored, 0)}`, meta: "全部有效行情计算 pre_score" },
      { icon: "ph-funnel", label: "技术评分 / 深度研究", value: `${fmt(funnel.technicalScored, 0)} / ${fmt(funnel.deepScored, 0)}`, meta: `K线完整 ${fmt(funnel.technicalKlineComplete, 0)} · 可深研 ${fmt(funnel.deepEligible, 0)} · 深研名额 ${fmt(funnel.deepAttempted, 0)} · 页面证据卡 ${shown}` },
    ]
    : [
      { icon: "ph-database", label: "有效行情 / 深度评分", value: `${fmt(funnel.validQuotes, 0)} / ${fmt(funnel.deepScored, 0)}`, meta: state.market === "a_share" ? "旧快照待更新；未发布全池基础/技术评分计数" : `行情有效后进入市场评分 · 页面保留 ${shown} 只证据卡` },
    ];
  const gates = candidate.decision_gates || [];
  const passCount = gates.filter((gate) => gate.status === "PASS").length;
  const risks = [...(candidate.risk_items || []).map((risk) => `${risk.code}${risk.evidence ? ` · ${risk.evidence}` : ""}`), ...(candidate.risk_flags || [])];
  const poolHealth = poolHealthState(section, decision);
  root.innerHTML = `
    <div class="toolbar">
      <div class="toolbar-left"><div><h2>${MARKET_META[state.market].label} · ${esc(labelForRegime(regime))}</h2><p>${esc(section.description || decision.message || "根据当前快照执行")}</p></div>${badge(state.snapshot?.selector_mode?.includes("dual_low") ? "Legacy Active · V2 + 双低 Shadow" : state.snapshot?.selector_mode?.includes("v2") ? "Legacy Active · V2 Shadow" : "Legacy Active", "purple")}</div>
      <div class="toolbar-right">${marketSwitch()}</div>
    </div>
    ${poolHealthAlert(section, decision)}
    ${renderKpis([
      { icon: poolHealth.degraded ? "ph-warning-octagon" : "ph-binoculars", label: "实际召回 / 目标", value: `${fmt(funnel.selected, 0)} / ${fmt(funnel.target, 0)}`, tone: poolHealth.degraded ? "warning" : "", meta: poolHealth.degraded ? "候选池降级 · 覆盖不足" : state.market === "a_share" ? "动态多路召回" : stats.universe_origin === "dynamic_market_snapshot" ? `本轮动态市场横截面 · 发现 ${fmt(stats.eligible_discovery_size, 0)}` : "版本化静态池（旧快照）" },
      ...scoringKpis,
      { icon: "ph-ranking", label: "推荐度", value: `${fmt(candidateScore(candidate), 0)}`, tone: hasPrimary ? "positive" : "warning", meta: `旧逻辑实际决策 · 总分 ${fmt(candidate.score, 1)}` },
      { icon: "ph-shield-check", label: "客观门控", value: gates.length ? `${passCount}/${gates.length}` : "Legacy", meta: gates.length ? `${gates.filter((g) => g.status === "BLOCK").length} 个阻断` : "V2 快照生成后启用展示" },
    ])}
    <div class="decision-grid">
      <div class="decision-main stack">
        <article class="card hero-card">
          <header class="card-header"><div><div class="eyebrow">${marketBadge(state.market)} ${esc(MARKET_META[state.market].label)} · ${esc(candidate.code || candidate.symbol)}</div><h2 class="card-title hero-title">${esc(candidate.name)}</h2><p class="card-subtitle">${esc(candidate.reason_tags || candidate.role || "综合候选")}</p></div><div class="hero-status">${badge(objectivelyBlocked && hasPrimary ? "LEGACY BUY" : actionLabel(decision), objectivelyBlocked ? "purple" : hasPrimary ? "positive" : "negative")}${badge(objectivelyBlocked ? "V2 客观阻断" : recommendationLabel(candidate, hasPrimary), objectivelyBlocked ? "negative" : advice.tone)}</div></header>
          <div class="card-body">
            <div class="price-grid price-grid-five">
              <div class="${toneFor(quoteView.changePct)}"><small>${esc(quoteView.title)}</small><strong>${price(quoteView.price)}</strong><span>${pct(quoteView.changePct)}</span></div>
              <div><small>计划买入价</small><strong>${price(candidate.entry_price || candidate.price)}</strong><span>快照锁定</span></div>
              <div><small>保护止损</small><strong>${price(candidate.stop_loss)}</strong><span>${Number.isFinite(num(candidate.stop_loss, NaN)) ? pct((num(candidate.stop_loss) / num(candidate.entry_price || candidate.price) - 1) * 100) : "--"}</span></div>
              <div><small>目标参考</small><strong>${price(candidate.take_profit_reference)}</strong><span>${esc(range.text || "--")}</span></div>
              <div class="${advice.tone}"><small>快照执行状态</small><strong>${esc(advice.label)}</strong><span>${advice.deviation === null ? "快照偏离 --" : `快照偏离 ${pct(advice.deviation)}`}</span></div>
            </div>
            <div class="callout ${advice.tone === "negative" ? "negative" : advice.tone === "warning" ? "warning" : ""}">${icon(advice.tone === "positive" ? "ph-check-circle" : "ph-warning-circle")}<div><strong>${esc(advice.label)}</strong><br>${esc(advice.text)} ${esc(snapshotQuoteLabel(candidate))}。页面刷新只读取 GitHub Actions 已发布快照；评分与排序不在浏览器重算。</div></div>
          </div>
        </article>
        <article class="chart-card"><header class="chart-header"><div><h3 class="chart-title">价格结构与计划位</h3><p class="chart-subtitle">快照内日 K · MA5 / MA10 / MA20 · 图表和计划位随下一份快照更新</p></div>${badge(`${(candidate.kline || []).length} 根K线`)}</header><div class="chart-shell"><canvas id="decisionChart" aria-label="${esc(candidate.name)}日K线图"></canvas></div></article>
        <article class="panel score-evidence-panel"><header class="panel-header"><div><h3 class="panel-title">评分证据拆解</h3><p class="panel-subtitle">先看实际决策，再分别核对 V2 与双低视角；三者不机械相加</p></div>${candidate.v2 ? badge(`V2 #${candidate.v2.rank || "--"} / ${candidate.v2.rank_universe_size || "--"}`, "primary") : ""}</header>${scoreLensCards(candidate, state.market)}${scoreDivergence(candidate, state.market)}<div class="detail-section"><div class="section-heading"><h3>V2 去重因子</h3><span>影子排序</span></div>${factorCards(candidate)}</div>${dualLowPanel(candidate, state.market)}</article>
      </div>
      <aside class="decision-side stack">
        <article class="panel"><header class="panel-header"><div><h3 class="panel-title">为什么是它</h3><p class="panel-subtitle">只展示快照保存的证据</p></div></header><ul class="evidence-list">${(candidate.reasons || []).slice(0, 7).map((reason) => `<li><h4>${esc(reason)}</h4></li>`).join("") || `<li><p>本快照未保存结构化理由。</p></li>`}</ul></article>
        <article class="panel"><header class="panel-header"><div><h3 class="panel-title">风险与门控</h3><p class="panel-subtitle">硬门控会阻止执行，警告只要求更谨慎</p></div></header>${gates.length ? `<ul class="gate-list">${gates.map((gate) => `<li><span class="status-pill ${gate.status === "PASS" ? "positive" : gate.status === "BLOCK" ? "negative" : "warning"}">${esc(gate.status)}</span><div><strong>${esc(gate.id)}</strong><small>${esc(gate.reason || "")}</small></div></li>`).join("")}</ul>` : `<div class="callout">${icon("ph-info")}<div>当前是旧快照，V2 客观门控尚未写入；Legacy 风控仍正常执行。</div></div>`}${risks.length ? `<ul class="evidence-list risk-list">${risks.slice(0, 6).map((risk) => `<li><p>${esc(risk)}</p></li>`).join("")}</ul>` : `<p class="muted">未保存额外风险标签。</p>`}</article>
        <article class="panel"><header class="panel-header"><div><h3 class="panel-title">同市场机会序列</h3><p class="panel-subtitle">页面不重新排序，沿用服务端快照顺序</p></div><button class="text-button" type="button" data-action="go-candidates">查看全部</button></header><div class="opportunity-list">${candidatesFor(state.snapshot, state.market).slice(0, 5).map((row, index) => `<button type="button" data-action="open-candidate" data-key="${esc(candidateId(row, state.market))}"><span class="opportunity-rank">${index + 1}</span><span><b>${esc(row.name)}</b><small>${esc(row.code || row.symbol)} · 推荐度 ${fmt(candidateScore(row), 0)}</small></span><strong>${row.v2?.rank ? `V2 #${row.v2.rank}` : pct(candidateChangePct(row))}</strong></button>`).join("")}</div></article>
      </aside>
    </div>`;
  requestAnimationFrame(() => drawCandleChart($("#decisionChart"), candidate));
}

function renderDecision() {
  const root = $("#decisionView");
  const truth = globalDecisionTruth();
  const research = truth.research;
  const executableMode = truth.action === "REVIEW_EXECUTABLE_PICK" && Boolean(truth.executable);
  const selected = executableMode ? truth.executable : research;
  const selectedMarket = selected?.market || "";
  const baseCandidate = selected?.candidate || null;
  const candidate = baseCandidate;
  const candidateQuote = candidate ? candidateQuoteView(candidate) : null;
  const selectedKey = candidate ? candidateId(candidate, selectedMarket) : "";
  const selectedEvent = candidate ? (executableMode ? automaticExternalEvents() : manualEvidenceForSnapshot()).find((event) => {
    const symbol = String(candidate.code || candidate.symbol || "").toLowerCase();
    return event.market === selectedMarket && String(event.symbol || "").toLowerCase() === symbol;
  }) : null;
  const executablePrimary = truth.executable?.primary || null;
  const targetDate = state.snapshot?.forecast_end_date || state.snapshot?.target_date || "--";
  const model = tenDayModelState();
  const freshness = state.status?.freshness_state || "unknown";
  const marketCards = truth.markets.map((item) => {
    const meta = MARKET_META[item.market];
    const primary = item.decision.primary || item.decision.blocked_candidate || null;
    const funnel = recallFunnel(item.section, item.market);
    const fullAShareStages = item.market === "a_share" && funnel.hasFullScoringStages;
    const stateTone = item.state === "READY" ? "positive" : item.state === "BLOCKED" ? "negative" : "warning";
    const stateLabel = item.state === "READY" ? "可评估" : item.state === "BLOCKED" ? "阻断" : "降级";
    const legacySignal = `LEGACY ${item.decision.primary ? "BUY_CANDIDATE" : String(item.decision.action || "NO_TRADE")}`;
    const reasons = item.reasons.length ? item.reasons.join("；") : "关键数据门禁已通过";
    return `<article class="market-decision-card ${stateTone}">
      <header><span>${marketBadge(item.market)}<b>${meta.label}</b></span><span class="status-pill ${stateTone}">${stateLabel}</span></header>
      <div class="market-decision-body"><div><small>市场级 Legacy 信号</small><strong>${esc(legacySignal)}</strong></div><div><small>${fullAShareStages ? "召回 / 目标 · 技术 / 深研" : "召回 / 目标 · 深评"}</small><strong>${fmt(funnel.selected, 0)} / ${fmt(funnel.target, 0)} · ${fullAShareStages ? `${fmt(funnel.technicalScored, 0)} / ` : ""}${fmt(funnel.deepScored, 0)}</strong></div></div>
      <p>${primary ? `${esc(primary.name || primary.code)} · 规则推荐度 ${fmt(candidateScore(primary), 0)}` : "本轮没有保存候选"}</p>
      <footer><span>${esc(reasons)}</span><button type="button" data-action="candidate-market" data-market="${item.market}">查看候选 ${icon("ph-arrow-right")}</button></footer>
    </article>`;
  }).join("");
  root.innerHTML = `
    <div class="principle-strip"><span><b>决策目标</b> 从 A 股、港股、美股中选择未来 10 个交易日净总回报最优且可执行的股票</span><small>目标日 ${esc(targetDate)}</small></div>
    <section class="answer-grid">
      <article class="answer-card ${executableMode ? "is-executable" : ""}">
        <div class="answer-kicker"><span class="status-pill ${executableMode ? "positive" : "negative"}">${executableMode ? "严格门禁已通过" : "严格门禁"}</span><span class="mono">${esc(truth.actionBasis)}</span></div>
        <h2>${truth.action === "NO_VALID_PICK" ? "今天没有满足条件的可执行股票" : "发现待复核的可执行候选"}</h2>
        <p>${truth.action === "NO_VALID_PICK" ? "这不等于三个市场没有好公司，而是当前数据还不能诚实回答“今天买哪一只，未来两周最可能赚得最多”。" : "所有全局门禁已通过，仍需在候选详情中核对入场价、止损和事件时点。"}</p>
        <div class="answer-code"><span>全局输出</span><strong>${esc(truth.action)}</strong></div>
        <ul class="answer-reasons">
          <li>${icon("ph-database")}<span><b>三市场可比性</b><small>${truth.markets.filter((item) => item.state === "READY").length} / 3 个市场可评估</small></span></li>
          <li>${icon("ph-newspaper")}<span><b>自动外部证据</b><small>${truth.autoEvidenceCount} 条进入决策门禁</small></span></li>
          <li>${icon("ph-chart-line")}<span><b>10 日概率模型</b><small>${truth.calibrated ? "已校准" : "未上线，规则分不映射为概率"}</small></span></li>
          <li>${icon("ph-scales")}<span><b>成本与尾部风险</b><small>${model.costsReady && model.tailReady ? "已纳入" : "尚未形成可验证净收益口径"}</small></span></li>
        </ul>
        <button class="secondary-button" type="button" data-action="go-health">${executableMode ? "查看数据与执行状态" : "查看阻断原因"} ${icon("ph-arrow-right")}</button>
      </article>
      <article class="research-card">
        <header><div><span class="status-pill ${executableMode ? "positive" : "primary"}">${executableMode ? "EXECUTABLE_REVIEW" : "RESEARCH_ONLY"}</span><small>${executableMode ? "严格门禁已通过，仍需人工复核交易计划" : "当前研究优先项，不是买入建议"}</small></div>${candidate ? marketBadge(selectedMarket) : ""}</header>
        ${candidate ? `<div class="research-symbol"><div><h3>${esc(candidate.name)}</h3><p>${esc(candidate.code || candidate.symbol)} · ${esc(MARKET_META[selectedMarket]?.label || selectedMarket)}</p></div><strong>${executableMode ? ratioPct(executablePrimary.probability, 1) : fmt(candidateScore(candidate), 0)}<small>${executableMode ? "10 日正收益概率" : "规则推荐度"}</small></strong></div>
          ${executableMode
            ? `<div class="research-metrics"><div><small>预期净效用</small><b>${pct(num(executablePrimary.expected_net_utility) * 100, 2)}</b></div><div><small>交易成本</small><b>${ratioPct(executablePrimary.transaction_cost, 2)}</b></div><div><small>尾部风险</small><b>${ratioPct(executablePrimary.tail_risk, 2)}</b></div></div>`
            : `<div class="research-metrics"><div><small>Legacy</small><b>#${selected.legacyRank}</b></div><div><small>V2 结构</small><b>${candidate.v2?.rank ? `#${candidate.v2.rank}/${candidate.v2.rank_universe_size || "--"}` : "--"}</b></div><div><small>上涨概率</small><b>未校准</b></div></div>`}
          <div class="research-evidence"><span>${icon("ph-calendar-dots")}<b>${executableMode ? "已准入官方证据" : "下一可核验事件"}</b></span><p>${esc(selectedEvent?.title || "自动事件证据尚未入库")}</p><small>${selectedEvent ? `${executableMode ? "自动核验入库" : "人工核验"} · ${dateTime(selectedEvent.effective_at)} · ${executableMode ? `模型 ${executablePrimary.model_id}` : "不参与自动门禁"}` : "请在事件证据页补齐官方来源"}</small></div>
          <div class="research-evidence"><span>${icon("ph-waveform")}<b>${esc(candidateQuote.title)}</b></span><p>${price(candidateQuote.price)}</p><small>${esc(candidateQuote.label)}</small></div>
          <button class="primary-button" type="button" data-action="open-candidate" data-key="${esc(selectedKey)}">${executableMode ? "复核执行计划" : "查看完整评分与风险"} ${icon("ph-arrow-right")}</button>` : `<div class="empty-state">${icon("ph-binoculars")}<h3>暂无研究优先项</h3><p>本轮快照未保留任何跨市场候选。</p></div>`}
      </article>
    </section>
    ${renderKpis([
      { icon: "ph-check-circle", label: "可执行候选", value: fmt(truth.executableCount, 0), tone: truth.executableCount ? "positive" : "negative", meta: "必须同时通过覆盖、证据、校准与成本门禁" },
      { icon: "ph-newspaper", label: "自动外部证据", value: fmt(truth.autoEvidenceCount, 0), tone: truth.autoEvidenceCount ? "positive" : "warning", meta: "model_signal 不计入外部证据" },
      { icon: "ph-chart-line-up", label: "10 日胜率", value: truth.probability === null ? "未校准" : ratioPct(truth.probability, 1), tone: truth.probability === null ? "warning" : "positive", meta: "绝不把推荐度当上涨概率" },
      { icon: "ph-clock", label: "快照状态", value: freshness.toUpperCase(), tone: freshness === "fresh" ? "positive" : "negative", meta: `生成 ${dateTime(state.snapshot?.generated_at)}` },
    ])}
    <section class="market-decision-grid">${marketCards}</section>
    <div class="decision-footnote">${icon("ph-info")}<span><b>旧因子全部保留：</b>Legacy 继续产生市场级动作，V2 与双低继续作为独立影子视角；新增的全局闸门只决定这些信号能否升级为跨市场可执行答案。</span></div>`;
}

function filteredCandidates() {
  const { market, risk, route, query } = state.candidateFilters;
  const needle = query.trim().toLowerCase();
  const rows = allCandidates().filter((row) => {
    if (market !== "all" && row.market !== market) return false;
    if (risk !== "all" && candidateRiskLevel(row.candidate, row.market) !== risk) return false;
    if (route !== "all" && !routeNames(row.candidate).includes(route)) return false;
    if (needle && !`${row.candidate.name || ""} ${row.candidate.code || row.candidate.symbol || ""} ${row.candidate.reason_tags || ""} ${(row.candidate.theme_tags || []).join(" ")}`.toLowerCase().includes(needle)) return false;
    return true;
  });
  if (market !== "all") return rows;
  return rows.sort((left, right) => {
    const evidenceLevel = (row) => {
      const symbol = String(row.candidate?.code || row.candidate?.symbol || "").toLowerCase();
      if (automaticExternalEvents().some((event) => event.market === row.market && String(event.symbol || "").toLowerCase() === symbol)) return 1;
      return 0;
    };
    const evidenceDelta = evidenceLevel(right) - evidenceLevel(left);
    if (evidenceDelta) return evidenceDelta;
    const riskDelta = ({ clear: 0, warning: 1, blocked: 2 })[candidateRiskLevel(left.candidate, left.market)] - ({ clear: 0, warning: 1, blocked: 2 })[candidateRiskLevel(right.candidate, right.market)];
    if (riskDelta) return riskDelta;
    const qualityDelta = num(right.candidate?.data_quality?.score) - num(left.candidate?.data_quality?.score);
    if (qualityDelta) return qualityDelta;
    const v2Position = (row) => row.candidate?.v2?.rank && row.candidate?.v2?.rank_universe_size ? num(row.candidate.v2.rank) / num(row.candidate.v2.rank_universe_size, 1) : 1;
    const rankDelta = v2Position(left) - v2Position(right);
    if (rankDelta) return rankDelta;
    return num(candidateScore(right.candidate), -Infinity) - num(candidateScore(left.candidate), -Infinity);
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
  const candidate = raw;
  const lineage = candidate.candidate_lineage || {};
  const routes = lineage.recall_routes || [];
  const quality = candidate.data_quality;
  const gates = candidate.decision_gates || [];
  const riskTexts = [...(candidate.risk_items || []).map((risk) => `${risk.code}${risk.evidence ? ` · ${risk.evidence}` : ""}`), ...(candidate.risk_flags || [])];
  const features = featureEvidence(candidate);
  const checked = state.compare.includes(candidateId(raw, market));
  const dualLow = dualLowAnalysis(candidate);
  const coverage = marketCoverageState(market);
  const quoteView = candidateQuoteView(candidate);
  const marketGate = coverage.state === "READY" ? "" : `<div class="callout ${coverage.state === "BLOCKED" ? "negative" : "warning"}">${icon(coverage.state === "BLOCKED" ? "ph-warning-octagon" : "ph-warning-circle")}<div><strong>市场级门禁：${coverage.state}</strong><br>${esc(coverage.reasons.join("；") || "市场覆盖尚未达到跨市场可执行标准")}。单股门控通过也不能绕过市场级阻断。</div></div>`;
  const snapshotStatus = `<div class="callout info">${icon("ph-waveform")}<div><strong>${esc(quoteView.title)}：${esc(quoteView.label)}</strong><br>快照生成 ${esc(dateTime(state.status?.snapshot_as_of || state.snapshot?.generated_at))}；下次计划检查点（含健康补跑） ${esc(dateTime(state.status?.next_refresh))}。评分与排序不在浏览器重算。</div></div>`;
  return `<article class="detail-panel candidate-detail">
    <header class="detail-header"><div><div class="eyebrow">${marketBadge(market)} ${esc(MARKET_META[market].label)} · ${esc(candidate.code || candidate.symbol)}</div><h2 class="detail-title">${esc(candidate.name)}</h2><p class="detail-subtitle">${esc(candidate.role || candidate.reason_tags || "综合候选")}</p></div><div class="detail-actions">${badge(`Legacy #${row.legacyRank}`, "primary")}${candidate.v2?.rank ? badge(`V2 #${candidate.v2.rank}/${candidate.v2.rank_universe_size}`, "purple") : ""}${dualLow?.status === "ranked" ? badge(`双低 #${dualLow.rank}/${dualLow.rank_universe_size}`, "positive") : dualLow ? badge(dualLowLabel(dualLow), dualLowTone(dualLow)) : ""}</div></header>
    ${marketGate}
    ${snapshotStatus}
    ${scoreLensCards(candidate, market)}
    ${scoreDivergence(candidate, market)}
    <div class="detail-section"><div class="section-heading"><h3>来源链</h3><span>${esc(lineage.universe_origin || (market === "a_share" ? "dynamic_snapshot" : "curated_static"))}</span></div>${routes.length ? `<ul class="event-list">${routes.map((route) => `<li><h4>${esc(route.route || "legacy")} · ${esc(route.source || "来源未保存")}</h4><p>${esc(route.reason || "该路径召回")}</p><div class="event-meta"><span>${esc(route.published_at || route.observed_at || "时间未保存")}</span>${route.decay_weight !== undefined ? `<span>延续权重 ${fmt(route.decay_weight, 2)}</span>` : ""}</div></li>`).join("")}</ul>` : `<div class="callout">${icon("ph-info")}<div>旧快照没有结构化召回来源；这不会影响旧评分，但 V2 事件组不据此加分。</div></div>`}</div>
    <div class="detail-section"><div class="section-heading"><h3>V2 评分分组</h3><span>同一特征只在一组计分</span></div>${factorCards(candidate)}</div>
    <div class="detail-section">${dualLowPanel(candidate, market)}</div>
    ${features.length ? `<div class="detail-section"><div class="section-heading"><h3>特征证据</h3><span>${features.filter((f) => f.used_in_score).length}/${features.length} 参与</span></div><div class="feature-table">${features.map((feature) => `<div><span>${esc(feature.feature_id)}</span><b>${feature.used_in_score ? fmt(feature.score, 1) : "缺失"}</b><small>${esc(feature.evidence || "")}</small></div>`).join("")}</div></div>` : ""}
    <div class="detail-section"><div class="section-heading"><h3>客观门控与风险</h3><span>${esc(coverage.state === "READY" ? candidate.execution_state || "Legacy" : `MARKET_${coverage.state}`)}</span></div>${gates.length ? `<ul class="gate-list">${gates.map((gate) => `<li><span class="status-pill ${gate.status === "PASS" ? "positive" : gate.status === "BLOCK" ? "negative" : "warning"}">${esc(gate.status)}</span><div><strong>${esc(gate.id)}</strong><small>${esc(gate.reason || "")}</small></div></li>`).join("")}</ul>` : `<p class="muted">旧快照尚未保存 V2 门控。</p>`}${riskTexts.length ? `<ul class="evidence-list risk-list">${riskTexts.map((risk) => `<li><p>${esc(risk)}</p></li>`).join("")}</ul>` : `<p class="muted">未保存额外风险标签。</p>`}</div>
    <div class="detail-footer"><button class="icon-button ${checked ? "is-active" : ""}" type="button" data-action="compare" data-key="${esc(candidateId(raw, market))}">${icon(checked ? "ph-check" : "ph-scales")} ${checked ? "已加入对比" : "加入对比"}</button></div>
  </article>`;
}

function candidateMobileCard(row) {
  const c = row.candidate;
  const quoteView = candidateQuoteView(c);
  const key = candidateId(row.candidate, row.market);
  const risk = candidateRiskLevel(c, row.market);
  const dualLow = dualLowAnalysis(c);
  const dualText = dualLow?.status === "ranked"
    ? `${fmt(dualLow.final_score, 0)} · #${dualLow.rank}/${dualLow.rank_universe_size}`
    : dualLowLabel(dualLow);
  return `<button class="candidate-mobile-card ${key === state.candidateKey ? "is-selected" : ""}" type="button" data-action="select-candidate" data-key="${esc(key)}" aria-pressed="${key === state.candidateKey}">
    <header><span>${marketBadge(row.market)}<b>${esc(c.name)}</b><small>${esc(c.code || c.symbol)}</small></span>${badge(decisionRoleLabel(row.decisionRole), row.decisionRole === "primary" ? "positive" : row.decisionRole === "blocked" ? "negative" : "")}</header>
    <div class="candidate-mobile-price"><strong title="${esc(quoteView.title)}">${price(quoteView.price)}</strong><span class="${toneFor(quoteView.changePct)}">${pct(quoteView.changePct)}</span></div>
    <dl><div><dt>Legacy</dt><dd>${fmt(candidateScore(c), 0)} · #${row.legacyRank}</dd></div><div><dt>V2 结构</dt><dd>${c.v2?.rank ? `${fmt(c.v2.rule_score, 0)} · #${c.v2.rank}/${c.v2.rank_universe_size}` : "--"}</dd></div><div><dt>双低价值</dt><dd>${esc(dualText)}</dd></div><div><dt>执行状态</dt><dd class="${risk === "clear" ? "positive" : risk === "blocked" ? "negative" : "warning"}">${({ clear: "PASS", warning: "WARN", blocked: "BLOCK" })[risk]}</dd></div></dl>
  </button>`;
}

function renderCandidates() {
  const root = $("#candidatesView");
  const truth = globalDecisionTruth();
  const rows = filteredCandidates();
  const selected = selectedCandidateRow(rows);
  const all = allCandidates();
  const blocked = all.filter((row) => candidateRiskLevel(row.candidate, row.market) === "blocked").length;
  const withLineage = all.filter((row) => routeNames(row.candidate).length).length;
  const tenDayReady = tenDayModelState().ready;
  const marketKpi = (coverage) => {
    const isA = coverage.market === "a_share";
    const funnel = recallFunnel(coverage.section, coverage.market);
    const originLabel = coverage.origin === "dynamic_market_snapshot" ? "动态" : coverage.origin === "curated_static" ? "静态" : "召回";
    const tone = coverage.state === "READY" ? "positive" : coverage.state === "BLOCKED" ? "negative" : "warning";
    const readyMeta = coverage.origin === "dynamic_market_snapshot"
      ? `本轮公开横截面重新筛选 · 发现 ${fmt(coverage.stats.eligible_discovery_size, 0)}`
      : coverage.origin === "curated_static" ? "版本化静态池（旧快照）" : "动态候选召回未就绪";
    return {
      icon: coverage.origin === "curated_static" ? "ph-path" : "ph-stack",
      label: `${MARKET_META[coverage.market].label}${isA ? "召回" : originLabel} / 目标`,
      value: `${fmt(funnel.selected, 0)} / ${fmt(funnel.target, 0)}`,
      tone,
      meta: `${coverage.state === "READY" ? readyMeta : coverage.reasons[0] || readyMeta} · 有效行情 ${fmt(funnel.validQuotes, 0)}${isA && funnel.hasFullScoringStages ? ` · 技术 ${fmt(funnel.technicalScored, 0)} · 深研 ${fmt(funnel.deepScored, 0)}` : ` · 深评 ${fmt(funnel.deepScored, 0)}${isA ? " · 旧快照待更新" : ""}`}`,
    };
  };
  root.innerHTML = `
    <div class="toolbar candidates-toolbar">
      <div class="toolbar-left"><div><h2>跨市场研究候选池</h2><p>单市场保留快照顺序；跨市场按证据、执行状态、数据质量与 V2 研究优先级排序</p></div></div>
      <div class="toolbar-right"><label class="search-field">${icon("ph-magnifying-glass")}<input id="candidateSearch" type="search" value="${esc(state.candidateFilters.query)}" placeholder="搜索公司 / 代码 / 主题" aria-label="搜索候选"></label></div>
    </div>
    <div class="callout ${tenDayReady ? "" : "warning"} section-callout">${icon(tenDayReady ? "ph-check-circle" : "ph-warning-circle")}<div><strong>${tenDayReady ? "10 日概率模型已参与严格门禁" : "10 日概率模型尚未上线"}</strong><br>下表的推荐度、V2 排名和双低得分仍是独立规则研究信号，不等于上涨概率；当前全局可执行候选为 ${truth.executableCount}。</div></div>
    <div class="filter-strip">
      <div class="filter-group"><span>市场</span><div class="segmented-button"><button data-action="candidate-market" data-market="all" aria-pressed="${state.candidateFilters.market === "all"}">全部</button>${MARKET_ORDER.map((market) => `<button data-action="candidate-market" data-market="${market}" aria-pressed="${state.candidateFilters.market === market}">${MARKET_META[market].label}</button>`).join("")}</div></div>
      <label>风险<select id="candidateRisk"><option value="all">全部</option><option value="clear">无明确警告</option><option value="warning">有警告</option><option value="blocked">被阻断</option></select></label>
      <label>召回<select id="candidateRoute"><option value="all">全部来源</option><option value="event">事件</option><option value="momentum">动量</option><option value="liquidity">流动性</option><option value="pullback">回踩</option><option value="activity">活跃度</option><option value="quality">规模质量</option><option value="history">历史延续</option><option value="curated">旧静态池</option></select></label>
    </div>
    ${renderKpis([
      { icon: "ph-check-circle", label: "可执行候选", value: fmt(truth.executableCount, 0), tone: truth.executableCount ? "positive" : "negative", meta: "全局严格门禁后的结果" },
      ...truth.markets.map((coverage, index) => {
        const item = marketKpi(coverage);
        if (index === truth.markets.length - 1) item.meta = `${item.meta} · 页面 ${all.length} 只 · 来源链 ${withLineage} 只 · BLOCK ${blocked}`;
        return item;
      }),
    ])}
    <div class="master-detail candidate-master-detail">
      <section class="panel candidate-table-panel"><header class="panel-header"><div><h3 class="panel-title">候选清单</h3><p class="panel-subtitle">推荐度不是收益概率；点击行查看证据</p></div></header>
        ${rows.length ? `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>市场</th><th>公司 / 代码</th><th class="number">行情 / 计划价</th><th class="number">快照涨跌</th><th class="number">推荐度</th><th class="number">Legacy</th><th class="number">V2</th><th class="number">双低</th><th>执行状态</th><th></th></tr></thead><tbody>${rows.map((row) => {
          const c = row.candidate;
          const quoteView = candidateQuoteView(c);
          const key = candidateId(row.candidate, row.market);
          const risk = candidateRiskLevel(c, row.market);
          const dualLow = dualLowAnalysis(c);
          const dualLowCell = dualLow?.status === "ranked" ? `#${dualLow.rank} · ${fmt(dualLow.final_score, 0)}` : dualLowLabel(dualLow);
          return `<tr class="${key === state.candidateKey ? "is-selected" : ""}" tabindex="0" data-action="select-candidate" data-key="${esc(key)}"><td>${marketBadge(row.market)}</td><td><span class="name">${esc(c.name)}</span><br><span class="symbol">${esc(c.code || c.symbol)}</span></td><td class="number" title="${esc(quoteView.title)}">${price(quoteView.price)}</td><td class="number ${toneFor(quoteView.changePct)}">${pct(quoteView.changePct)}</td><td class="number"><strong>${fmt(candidateScore(c), 0)}</strong></td><td class="number">#${row.legacyRank}/${candidatesFor(state.snapshot, row.market).length}</td><td class="number">${c.v2?.rank ? `#${c.v2.rank}/${c.v2.rank_universe_size || "--"}` : "--"}</td><td class="number dual-low-cell ${esc(dualLowTone(dualLow))}">${esc(dualLowCell)}</td><td><span class="status-pill ${risk === "clear" ? "positive" : risk === "blocked" ? "negative" : "warning"}">${({ clear: "清晰", warning: "警告", blocked: "阻断" })[risk]}</span></td><td><button class="row-action" type="button" data-action="select-candidate" data-key="${esc(key)}" aria-label="查看${esc(c.name)}详情">${icon("ph-caret-right")}</button></td></tr>`;
        }).join("")}</tbody></table></div>` : `<div class="empty-state">${icon("ph-funnel-x")}<h3>没有匹配候选</h3><p>调整市场、风险或召回来源筛选。</p></div>`}
        ${rows.length ? `<div class="candidate-mobile-list">${rows.map(candidateMobileCard).join("")}</div>` : ""}
      </section>
      <div>${candidateDetail(selected)}</div>
    </div>
    ${dualLowBatchOverview()}
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
  const automatic = Array.isArray(items) ? items : fallbackEvents();
  const ids = new Set(automatic.map((event) => event.event_id));
  return [...automatic, ...manualEvidenceForSnapshot().filter((event) => !ids.has(event.event_id))];
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

function renderLegacyEvents() {
  const root = $("#eventsView");
  const all = eventItems();
  const rows = filteredEvents();
  let selected = rows.find((event) => event.event_id === state.eventKey) || rows[0];
  if (selected) state.eventKey = selected.event_id;
  const externalCount = automaticExternalEvidenceCount();
  const modelSignalCount = all.filter((event) => event.event_type === "model_signal").length;
  const manualCount = all.filter((event) => event.event_type === "manual_external").length;
  const missingEvidence = all.filter((event) => !event.source || !(event.published_at || event.ingested_at)).length;
  root.innerHTML = `
    <div class="principle-strip"><span><b>证据原则</b> 系统推断与外部事实分开记录；只有可访问原文、来源和发布时间的证据才能进入买入决策。</span><small>核验批次 · ${esc(state.snapshot?.target_date || "--")}</small></div>
    ${renderKpis([
      { icon: "ph-newspaper", label: "官方自动证据", value: fmt(externalCount, 0), tone: externalCount ? "positive" : "negative", meta: "自动入库且可参与门禁" },
      { icon: "ph-cpu", label: "模型信号", value: fmt(modelSignalCount, 0), meta: "系统生成，不等于外部证据" },
      { icon: "ph-user-check", label: "人工核验待入库", value: fmt(manualCount, 0), tone: "warning", meta: "仅研究提示，不参与自动决策" },
      { icon: "ph-warning-octagon", label: "数据状态", value: externalCount ? "待复核" : "严重缺口", tone: externalCount ? "warning" : "negative", meta: missingEvidence ? `${missingEvidence} 条来源或时间缺失` : "事件因子不可独立支撑买入" },
    ])}
    <div class="callout warning section-callout">${icon("ph-warning-circle")}<div><strong>模型信号 ≠ 外部事件证据</strong><br>model_signal 只是系统为什么把股票放进研究池的解释；没有原文链接、官方来源和事件时点时，必须标为“非外部”，不能把它包装成公告或新闻。</div></div>
    <div class="filter-strip"><div class="filter-group"><span>市场</span><div class="segmented-button"><button data-action="event-market" data-market="all" aria-pressed="${state.eventFilters.market === "all"}">全部</button>${MARKET_ORDER.map((market) => `<button data-action="event-market" data-market="${market}" aria-pressed="${state.eventFilters.market === market}">${MARKET_META[market].label}</button>`).join("")}</div></div><label>类型<select id="eventType"><option value="all">全部</option><option value="announcement_or_news">自动公告 / 新闻</option><option value="manual_external">人工核验</option><option value="model_signal">模型信号</option></select></label><label>方向<select id="eventDirection"><option value="all">全部</option><option value="positive">正面</option><option value="neutral">中性 / 未知</option><option value="negative">负面</option></select></label><label class="search-field">${icon("ph-magnifying-glass")}<input id="eventSearch" type="search" value="${esc(state.eventFilters.query)}" placeholder="搜索公司 / 代码 / 事件" aria-label="搜索事件"></label></div>
    <div class="master-detail"><section class="panel"><header class="panel-header"><div><h3 class="panel-title">事件列表</h3><p class="panel-subtitle">${rows.length} 条匹配结果</p></div></header>${rows.length ? `<div class="event-master-list">${rows.map((event) => { const direction = normalizedDirection(event.direction); return `<button class="event-master-row ${event.event_id === state.eventKey ? "is-selected" : ""}" type="button" data-action="select-event" data-key="${esc(event.event_id)}"><time>${esc(dateTime(event.published_at || event.ingested_at, false))}</time>${marketBadge(event.market)}<span><b>${esc(event.company || "行业事件")}</b><strong>${esc(event.title)}</strong><small>${esc(event.source || "来源未保存")}</small></span><em class="${direction === "positive" ? "positive" : direction === "negative" ? "negative" : "muted"}">${fmt(event.impact_score, 1)}</em></button>`; }).join("")}</div>` : `<div class="empty-state">${icon("ph-funnel-x")}<h3>没有匹配事件</h3><p>调整市场、类型、方向或搜索条件。</p></div>`}</section><div>${renderEventDetail(selected)}</div></div>`;
  $("#eventType").value = state.eventFilters.type;
  $("#eventDirection").value = state.eventFilters.direction;
}

function renderEvents() {
  const root = $("#eventsView");
  const currentAudit = $("details.event-audit");
  if (currentAudit) state.eventAuditOpen = currentAudit.open;
  const all = eventItems();
  const rows = filteredEvents();
  const manual = all.filter((event) => event.event_type === "manual_external");
  const modelSignals = all.filter((event) => event.event_type === "model_signal");
  const automatic = automaticExternalEvents();
  const externalCount = automaticExternalEvidenceCount();
  const missingEvidence = all.filter((event) => !event.source || !(event.published_at || event.ingested_at)).length;
  let selected = rows.find((event) => event.event_id === state.eventKey)
    || rows.find((event) => automatic.some((item) => item.event_id === event.event_id))
    || rows.find((event) => event.event_type === "manual_external")
    || rows[0]
    || null;
  if (selected) state.eventKey = selected.event_id;
  const evidenceRow = (event, isAutomatic = false) => `<button class="verified-evidence-row ${event.event_id === state.eventKey ? "is-selected" : ""}" type="button" data-action="select-event" data-key="${esc(event.event_id)}"><time>${esc(dateTime(event.effective_at || event.published_at, false))}</time>${marketBadge(event.market)}<span><b>${esc(event.title)}</b><small>${esc(event.source)} · 来源可信度：高</small></span><em>官方外部证据</em><i>${isAutomatic ? "参与门禁" : "待入库"}</i></button>`;
  root.innerHTML = `
    <div class="principle-strip"><span><b>证据原则</b> 系统推断与外部事实分开记录；只有可访问原文、来源和发布时间的证据才能进入买入决策。</span><small>核验批次 · ${esc(state.snapshot?.target_date || "--")}</small></div>
    ${renderKpis([
      { icon: "ph-newspaper", label: "官方自动证据", value: fmt(externalCount, 0), tone: externalCount ? "positive" : "negative", meta: "自动入库且可参与门禁" },
      { icon: "ph-cpu", label: "模型信号", value: fmt(modelSignals.length, 0), meta: "系统生成，不等于外部证据" },
      { icon: "ph-user-check", label: "人工核验待入库", value: fmt(manual.length, 0), tone: "warning", meta: "仅研究提示，不参与自动决策" },
      { icon: "ph-warning-octagon", label: "数据状态", value: externalCount ? "待复核" : "严重缺口", tone: externalCount ? "warning" : "negative", meta: missingEvidence ? `${missingEvidence} 条来源或时间缺失` : "事件因子不可独立支撑买入" },
    ])}
    <div class="callout warning section-callout">${icon("ph-warning-circle")}<div><strong>模型信号 ≠ 外部事件证据</strong><br>model_signal 只是系统推断，不能替代公告、财报、监管文件或权威新闻；没有原文链接时，“查看证据原文”必须禁用。</div></div>
    <section class="panel evidence-feed-panel"><header class="panel-header"><div><h3 class="panel-title">已自动入库 · 参与严格门禁</h3><p class="panel-subtitle">${automatic.length} 条 · 通过来源、时点、标的与有效期校验</p></div></header><div class="verified-evidence-list">${automatic.map((event) => evidenceRow(event, true)).join("") || `<div class="empty-state compact">${icon("ph-newspaper-clipping")}<h3>暂无自动准入证据</h3><p>当前不会用模型信号或人工笔记替代。</p></div>`}</div><div class="model-signal-title"><span>已人工核验 · 待自动入库（${manual.length} 条）</span></div><div class="verified-evidence-list">${manual.map((event) => evidenceRow(event, false)).join("") || `<div class="empty-state compact"><p>暂无人工核验证据</p></div>`}</div><div class="model-signal-title"><span>系统模型信号 · 非外部证据</span></div><div class="model-signal-grid">${modelSignals.map((event) => `<article><header><span>${esc(event.title)}</span><span class="status-pill primary">非外部</span></header><p>${esc(event.source || "系统生成")} · 无可访问原文</p></article>`).join("")}</div></section>
    <section class="evidence-bottom-grid"><div>${renderEventDetail(selected)}</div><article class="panel evidence-rules"><header class="panel-header"><div><h3 class="panel-title">证据准入规则</h3><p class="panel-subtitle">任何一项缺失，都不能升级为自动买入依据</p></div></header><ol><li>可访问原文或监管文件</li><li>记录来源、发布时间与生效时间</li><li>区分事实、模型推断与人工判断</li><li>计算相关性、新颖度与已计价程度</li><li>失效或过期后自动退出决策窗口</li></ol><strong>任一关键字段缺失，事件因子只能降级为研究提示。</strong></article></section>
    <details class="event-audit" ${state.eventAuditOpen ? "open" : ""}><summary>${icon("ph-list-magnifying-glass")} 查看全部事件与模型信号（${all.length} 条）</summary><div class="history-archive-body"><div class="filter-strip"><div class="filter-group"><span>市场</span><div class="segmented-button"><button data-action="event-market" data-market="all" aria-pressed="${state.eventFilters.market === "all"}">全部</button>${MARKET_ORDER.map((market) => `<button data-action="event-market" data-market="${market}" aria-pressed="${state.eventFilters.market === market}">${MARKET_META[market].label}</button>`).join("")}</div></div><label>类型<select id="eventType"><option value="all">全部</option><option value="announcement_or_news">自动公告 / 新闻</option><option value="manual_external">人工核验</option><option value="model_signal">模型信号</option></select></label><label>方向<select id="eventDirection"><option value="all">全部</option><option value="positive">正面</option><option value="neutral">中性 / 未知</option><option value="negative">负面</option></select></label><label class="search-field">${icon("ph-magnifying-glass")}<input id="eventSearch" type="search" value="${esc(state.eventFilters.query)}" placeholder="搜索公司 / 代码 / 事件" aria-label="搜索事件"></label></div><div class="event-master-list">${rows.map((event) => { const direction = normalizedDirection(event.direction); return `<button class="event-master-row ${event.event_id === state.eventKey ? "is-selected" : ""}" type="button" data-action="select-event" data-key="${esc(event.event_id)}"><time>${esc(dateTime(event.published_at || event.ingested_at, false))}</time>${marketBadge(event.market)}<span><b>${esc(event.company || "行业事件")}</b><strong>${esc(event.title)}</strong><small>${esc(event.source || "来源未保存")}</small></span><em class="${direction === "positive" ? "positive" : direction === "negative" ? "negative" : "muted"}">${fmt(event.impact_score, 1)}</em></button>`; }).join("")}</div></div></details>`;
  const type = $("#eventType");
  const direction = $("#eventDirection");
  if (type) type.value = state.eventFilters.type;
  if (direction) direction.value = state.eventFilters.direction;
}

function historyMarketSummary(item, market = state.historyMarket) {
  if (item.markets?.[market]) return item.markets[market];
  if (market === "a_share") return item.a_share_legacy || {};
  return {};
}

function historyKind(item) {
  return item?.history_kind === "global_10d_v1" ? "global_10d_v1" : "legacy_snapshot";
}

function historyKindLabel(item) {
  return historyKind(item) === "global_10d_v1" ? "global-10d-v1" : "Legacy";
}

function historyTargetLabel(item, compact = false) {
  if (historyKind(item) === "global_10d_v1") return compact ? "计划" : "计划执行日";
  return compact ? "归档" : "Legacy 归档日";
}

function shadowOutcomeStatus(item) {
  const status = String(item?.shadow_outcome?.status || "").toUpperCase();
  return status === "PENDING" || status === "SETTLED" ? status : "";
}

function shadowOutcomeTag(item) {
  const status = shadowOutcomeStatus(item);
  if (!status) return "";
  const label = status === "PENDING" ? "Shadow·PENDING" : "Shadow·SETTLED";
  const title = "影子研究台账；不计入可执行绩效、胜率或收益";
  return `<span class="status-pill ${status === "SETTLED" ? "primary" : "warning"}" title="${title}">${label}</span>`;
}

function historyFormalStatus(item) {
  if (historyKind(item) !== "global_10d_v1") return { code: "LEGACY", label: "Legacy", tone: "muted" };
  const action = String(item?.global_decision?.action || "").toUpperCase();
  if (action === "NO_VALID_PICK") return { code: "ABSTAINED", label: "主动放弃", tone: "muted" };
  if (action !== "REVIEW_EXECUTABLE_PICK" || !item?.global_decision?.primary) {
    return { code: "INVALID", label: "结算无效", tone: "negative" };
  }
  const outcomeStatus = String(item?.outcome?.status || "").toUpperCase();
  const formalStatus = String(item?.formal_sample_status || "").toUpperCase();
  const validationStatus = String(item?.outcome_validation?.status || "").toUpperCase();
  const explicitlyInvalid = item?.outcome_valid === false
    || item?.outcome?.valid === false
    || item?.outcome_validation?.valid === false
    || item?.outcome_validation?.conflict === true
    || ["INVALID_CONTRACT", "OUTCOME_INVALID", "SETTLED_INVALID"].includes(formalStatus)
    || ["INVALID", "EXCLUDED", "CONFLICT"].includes(validationStatus);
  if (explicitlyInvalid) return { code: "INVALID", label: "结算无效", tone: "negative" };
  if (formalStatus === "SETTLED_VALID"
    && validationStatus === "VALID"
    && item?.outcome_validation?.valid === true) {
    return { code: "SETTLED", label: "可执行·已结算", tone: "positive" };
  }
  if (formalStatus === "PENDING" || validationStatus === "PENDING") {
    return { code: "PENDING", label: "可执行·待结算", tone: "warning" };
  }
  if (formalStatus === "MISSING" || validationStatus === "MISSING") {
    return { code: "MISSING", label: "可执行·缺结算", tone: "warning" };
  }
  // Legacy manifests may contain a raw ledger status without the strict
  // row-level validation contract.  Keep those visible, but never green-light
  // a settlement merely because its raw status says SETTLED.
  if (outcomeStatus === "PENDING") return { code: "PENDING", label: "可执行·待结算", tone: "warning" };
  if (outcomeStatus === "SETTLED") return { code: "UNVERIFIED", label: "已结算·待校验", tone: "warning" };
  if (!item?.outcome) return { code: "MISSING", label: "可执行·缺结算", tone: "warning" };
  return { code: "INVALID", label: "结算无效", tone: "negative" };
}

function historyFormalStatusTag(item) {
  const status = historyFormalStatus(item);
  return `<span class="status-pill ${status.tone}" title="正式可执行预测状态；与 Shadow 研究轨独立">${status.label}</span>`;
}

const HISTORY_PERFORMANCE_METRICS = [
  { key: "mean_net_return", label: "Top 1 平均净收益", note: "合法可执行样本的十日平均净总回报" },
  { key: "positive_rate", label: "十日正收益率", note: "R10 > 0 的实际比例" },
  { key: "top_decile_positive_rate", label: "Top 10% 命中率", note: "校准概率最高十分位的正收益比例" },
  { key: "selection_rank_ic", label: "历史已选样本 Rank IC", note: "跨历史已选样本的排序相关性" },
  { key: "brier_score", label: "Brier Score", note: "十日正收益概率的均方误差" },
  { key: "ece_10bin", label: "ECE（10 桶）", note: "预测概率与实际频率的校准误差" },
  { key: "expected_shortfall_10pct", label: "10% Expected Shortfall", note: "最差十分位样本的平均净收益" },
  { key: "settlement_sequence_max_drawdown", label: "结算序列最大回撤", note: "按结算顺序串联，不代表真实组合" },
  { key: "comparable_sample_count", label: "可比样本数", note: "只统计通过完整合同校验的 SETTLED outcome" },
];

const HISTORY_PERCENT_METRICS = new Set([
  "mean_net_return",
  "positive_rate",
  "top_decile_positive_rate",
  "expected_shortfall_10pct",
  "settlement_sequence_max_drawdown",
]);

function historyMetricReason(metric) {
  const reason = String(metric?.reason || "").toUpperCase();
  const publishedReason = ({
    NO_VALID_SETTLED_SAMPLE: "没有通过合同校验的已结算样本",
    MINIMUM_SAMPLE_NOT_MET: "尚未达到最低可靠样本数",
    RANK_IC_REQUIRES_AT_LEAST_3_SAMPLES: "Rank IC 至少需要 3 个历史已选样本",
    RANK_IC_ZERO_VARIANCE: "排序分或真实收益没有足够差异",
  })[reason];
  if (publishedReason) return publishedReason;
  if (metric?.reason) return String(metric.reason);
  return ({
    NO_SAMPLE: "没有合法可执行结算样本",
    NOT_APPLICABLE: "当前样本结构不适用",
    UNAVAILABLE: "服务端未发布该指标合同",
    INSUFFICIENT_SAMPLE: "样本不足，仅展示早期观察值",
    READY: "已达到该指标最低样本要求",
  })[String(metric?.status || "UNAVAILABLE").toUpperCase()] || "指标状态未知";
}

function historyMetricValue(key, metric) {
  const hasNumericValue = metric.value !== null && metric.value !== undefined && Number.isFinite(Number(metric.value));
  const isPublishedZeroSampleCount = key === "comparable_sample_count"
    && String(metric.status || "").toUpperCase() === "NO_SAMPLE"
    && hasNumericValue
    && Number(metric.value) === 0;
  if (isPublishedZeroSampleCount) return "0";
  const canDisplay = metric.status === "READY" || metric.status === "INSUFFICIENT_SAMPLE";
  if (!canDisplay || !hasNumericValue) return "—";
  const value = Number(metric.value);
  if (key === "settlement_sequence_max_drawdown") return `${value > 0 ? "−" : ""}${fmt(Math.abs(value) * 100, 2)}%`;
  if (key === "positive_rate" || key === "top_decile_positive_rate") return `${fmt(value * 100, 2)}%`;
  if (HISTORY_PERCENT_METRICS.has(key)) return `${value > 0 ? "+" : ""}${fmt(value * 100, 2)}%`;
  if (key === "comparable_sample_count" || metric.unit === "count") return fmt(value, 0);
  return fmt(value, 4);
}

function renderHistoryMetric(definition, metrics, performance) {
  const metric = metrics?.[definition.key] && typeof metrics[definition.key] === "object"
    ? metrics[definition.key]
    : { value: null, n: 0, status: "UNAVAILABLE", reason: "服务端未发布该指标合同" };
  const status = String(metric.status || "UNAVAILABLE").toUpperCase();
  const early = status === "INSUFFICIENT_SAMPLE";
  const statusLabel = ({ READY: "样本达标", INSUFFICIENT_SAMPLE: "早期样本", NO_SAMPLE: "无样本", NOT_APPLICABLE: "不适用", UNAVAILABLE: "不可用" })[status] || "状态未知";
  const sampleSize = Math.max(0, num(metric.n));
  const minimum = Math.max(0, num(metric.min_n, num(performance?.minimum_reliable_sample)));
  const sampleLabel = minimum ? `n=${fmt(sampleSize, 0)} / ${fmt(minimum, 0)}` : `n=${fmt(sampleSize, 0)}`;
  return `<article class="history-metric-card ${early ? "is-early" : ""}" data-metric-status="${esc(status)}"><header><small>${esc(definition.label)}</small><span class="status-pill ${status === "READY" ? "positive" : early ? "warning" : "muted"}">${esc(statusLabel)}</span></header><strong>${esc(historyMetricValue(definition.key, metric))}</strong><p title="${esc(metric.method || "")}">${esc(definition.note)}</p><footer><span>${esc(sampleLabel)}</span><span>${esc(historyMetricReason(metric))}</span></footer></article>`;
}

function filteredHistory() {
  const needle = state.historyQuery.trim().toLowerCase();
  return state.history.filter((item) => {
    const summary = historyMarketSummary(item);
    const hasOfficialPrimary = historyKind(item) === "global_10d_v1" && Boolean(item.global_decision?.primary);
    if (state.historyAction === "buy" && !summary.has_primary && !hasOfficialPrimary) return false;
    if (state.historyAction === "no_trade" && (summary.has_primary || hasOfficialPrimary)) return false;
    if (needle && !`${item.target_date || ""} ${item.signal_date || ""} ${item.generated_at || ""} ${historyKindLabel(item)} ${summary.name || ""} ${summary.code || ""}`.toLowerCase().includes(needle)) return false;
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
  const itemKey = item.snapshot_key || item.cache_key;
  const loadedSection = state.historySnapshot && state.historySnapshotKey === itemKey ? marketSection(state.historySnapshot, state.historyMarket) : null;
  const decision = loadedSection?.decision;
  const candidate = decision ? currentCandidate(decision) : null;
  const rangeLabel = summary.estimated_2w_range ? "两周区间" : summary.estimated_2d_range ? "两日区间" : "预测区间";
  const rangeNote = summary.estimated_2w_range ? "Legacy 两周规则估计" : summary.estimated_2d_range ? "旧版两日规则估计" : "未保存";
  const globalContract = historyKind(item) === "global_10d_v1";
  const globalPrimary = globalContract ? item.global_decision?.primary : null;
  const globalAbstained = globalContract && String(item.global_decision?.action || "").toUpperCase() === "NO_VALID_PICK";
  const headerScope = globalContract ? "跨市场动作" : MARKET_META[state.historyMarket].label;
  const headerName = globalPrimary?.name || (globalAbstained ? "本轮主动放弃" : summary.name || "本轮无 Legacy 首选");
  const shadowStatus = shadowOutcomeStatus(item);
  const shadowEvidence = shadowStatus ? `<div class="callout info">${icon("ph-flask")}<div><strong>${shadowStatus === "PENDING" ? "Shadow·PENDING" : "Shadow·SETTLED"}</strong><br>这是 research_priority 的影子研究台账，仅用于验证研究排序；不计入可执行绩效、胜率或收益。${item.shadow_outcome?.prediction_id ? ` Prediction ID：${esc(item.shadow_outcome.prediction_id)}。` : ""}</div></div>` : "";
  const officialEvidence = globalPrimary ? `<div class="detail-section"><div class="section-heading"><h3>正式十日预测</h3>${historyFormalStatusTag(item)}</div><div class="detail-score-grid"><div><small>全局首选</small><strong>${esc(globalPrimary.name || "--")}</strong><span>${esc(globalPrimary.market || "--")} · ${esc(globalPrimary.code || globalPrimary.symbol || "--")}</span></div><div><small>P(R10 &gt; 0)</small><strong>${globalPrimary.probability == null ? "--" : `${fmt(num(globalPrimary.probability) * 100, 1)}%`}</strong><span>已校准模型概率</span></div><div><small>Prediction ID</small><strong class="mono">${esc(globalPrimary.prediction_id || "--")}</strong><span>${esc(globalPrimary.model_id || "--")}</span></div><div><small>Label</small><strong>${esc(globalPrimary.label_version || "--")}</strong><span>结算必须完全匹配</span></div></div></div>` : "";
  return `<article class="detail-panel history-detail"><header class="detail-header"><div><div class="eyebrow">${historyKindLabel(item)} 档案 · ${esc(itemKey || "--")}</div><h2 class="detail-title">${esc(headerScope)} · ${esc(headerName)}</h2><p class="detail-subtitle">信号日 ${esc(item.signal_date || "--")} · ${historyTargetLabel(item)} ${esc(item.target_date || "--")} · 生成 ${esc(dateTime(item.generated_at))}</p></div><div class="history-row-statuses">${historyFormalStatusTag(item)}${shadowOutcomeTag(item)}</div></header>
    ${officialEvidence}
    ${shadowEvidence}
    <div class="detail-score-grid"><div><small>标的</small><strong>${esc(summary.name || "无")}</strong><span>${esc(summary.code || "--")}</span></div><div><small>Legacy 推荐度</small><strong>${fmt(summary.recommendation_degree ?? summary.confidence, 0)}</strong><span>规则分，非概率</span></div><div><small>参考价</small><strong>${price(summary.entry_price)}</strong><span>当时快照，不代表成交</span></div><div><small>${rangeLabel}</small><strong>${esc(summary.estimated_2w_range || summary.estimated_2d_range || "--")}</strong><span>${rangeNote}</span></div></div>
    <div class="callout warning">${icon("ph-warning-circle")}<div><strong>${globalContract ? `同日全局动作：${esc(item.global_decision?.action || "--")}；下方为独立 Legacy 市场档案` : "Legacy 规则档案，不属于 global-10d-v1 绩效样本"}</strong><br>下方 Legacy 记录只保存当时规则证据，因此不展示“命中率”或伪造收益；正式收益仅来自上方通过合同校验的外部结算账本。</div></div>
    ${candidate ? `<div class="detail-section"><div class="section-heading"><h3>完整快照证据</h3><span>已载入</span></div>${factorCards(candidate)}<ul class="evidence-list">${(candidate.reasons || []).slice(0, 5).map((reason) => `<li><h4>${esc(reason)}</h4></li>`).join("")}</ul></div>` : `<div class="detail-section"><button class="primary-button" type="button" data-action="load-history" data-key="${esc(item.snapshot_key || item.cache_key)}">${icon("ph-download-simple")}载入完整快照证据</button></div>`}
  </article>`;
}

function renderLegacyHistory() {
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

function renderShadowResearchPanel(shadowLedger) {
  const hasField = (field) => Object.prototype.hasOwnProperty.call(shadowLedger, field);
  const contractPublished = (hasField("raw_prediction_count") || hasField("raw_count"))
    && (hasField("prediction_count") || hasField("eligible_count"))
    && ["pending_count", "settled_count", "excluded_count", "included_in_executable_performance"].every(hasField);
  const rawCount = Math.max(0, num(shadowLedger.raw_prediction_count ?? shadowLedger.raw_count));
  const predictionCount = Math.max(0, num(shadowLedger.prediction_count ?? shadowLedger.eligible_count));
  const pendingCount = Math.max(0, num(shadowLedger.pending_count));
  const settledCount = Math.max(0, num(shadowLedger.settled_count));
  const excludedCount = Math.max(0, num(shadowLedger.excluded_count));
  const isolated = shadowLedger.included_in_executable_performance === false;
  const publishedReturn = shadowLedger.metrics?.mean_net_return ?? shadowLedger.mean_net_return;
  const returnMetric = publishedReturn && typeof publishedReturn === "object"
    ? publishedReturn
    : Number.isFinite(Number(publishedReturn))
      ? { value: Number(publishedReturn), n: settledCount, status: "READY" }
      : { value: null, n: settledCount, status: "UNAVAILABLE", reason: "后端未发布 Shadow 聚合收益" };
  const returnValue = historyMetricValue("mean_net_return", returnMetric);
  const countValue = (value) => contractPublished ? fmt(value, 0) : "—";
  const stateCopy = !contractPublished
    ? "Shadow 研究合同尚未发布；前端不会把缺失字段解释为 0。"
    : settledCount
    ? `已有 ${fmt(settledCount, 0)} 个 Shadow 样本完成结算；收益只描述研究排序轨。`
    : pendingCount
      ? `${fmt(pendingCount, 0)} 个 Shadow 样本正在等待第 10 个交易日结算。`
      : excludedCount
        ? `${fmt(excludedCount, 0)} 条记录未通过当前准入合同，详见后端诊断。`
        : "当前尚无可进入 Shadow 研究台账的预测。";
  const ledgerLabel = !contractPublished ? "CONTRACT UNAVAILABLE" : settledCount ? "SHADOW SETTLED" : pendingCount ? "SHADOW PENDING" : "NO SHADOW SAMPLE";
  const ledgerTone = !contractPublished ? "negative" : settledCount ? "primary" : pendingCount ? "warning" : "muted";
  return `<section class="panel shadow-evaluation-panel"><header class="panel-header"><div><h3 class="panel-title">Shadow 研究轨</h3><p class="panel-subtitle">只检验 research_priority 的研究排序；不计入可执行绩效、胜率或收益</p></div><span class="status-pill ${ledgerTone}">${ledgerLabel}</span></header><div class="shadow-ledger-grid"><div><small>原始登记</small><strong>${countValue(rawCount)}</strong><span>未按 prediction_id 去重</span></div><div><small>去重研究样本</small><strong>${countValue(predictionCount)}</strong><span>${contractPublished ? `PENDING ${fmt(pendingCount, 0)} · SETTLED ${fmt(settledCount, 0)}` : "合同未发布"}</span></div><div><small>排除记录</small><strong>${countValue(excludedCount)}</strong><span>未通过当前准入合同，详见后端诊断</span></div><div><small>Shadow 平均净收益</small><strong>${esc(returnValue)}</strong><span>${esc(historyMetricReason(returnMetric))}</span></div></div><footer>${icon("ph-flask")}<span>${esc(stateCopy)} ${isolated ? "后端合同明确标记 included_in_executable_performance=false。" : "隔离字段未发布，因此前端不会把它并入正式指标。"}</span></footer></section>`;
}

function renderHistory() {
  const root = $("#historyView");
  const currentArchive = $("details.history-archive");
  if (currentArchive) state.historyArchiveOpen = currentArchive.open;
  if (state.historyError) {
    root.innerHTML = `<div class="principle-strip"><span><b>评估原则</b> 历史数据故障不会降级显示为 0 条或 0 胜率。</span><small class="negative">HISTORY_DATA_UNAVAILABLE</small></div><div class="empty-state">${icon("ph-warning-circle")}<h3>历史数据暂不可用</h3><p>${esc(state.historyError)}</p><button class="primary-button" type="button" onclick="document.querySelector('#refreshBtn').click()">重新读取</button></div>`;
    return;
  }
  const rows = filteredHistory();
  const selected = selectedHistoryItem(rows);
  const meta = state.historyMeta || {};
  const performance = meta.performance && typeof meta.performance === "object" ? meta.performance : {};
  const metrics = performance.metrics && typeof performance.metrics === "object" ? performance.metrics : {};
  const shadowLedger = meta.shadow_ledger && typeof meta.shadow_ledger === "object" ? meta.shadow_ledger : {};
  const rawRuns = num(meta.raw_run_count, state.history.length);
  const decisionDays = num(meta.decision_day_count, state.history.length);
  const duplicateRuns = num(meta.duplicate_run_count, Math.max(0, rawRuns - decisionDays));
  const contractDays = num(meta.global_contract_day_count);
  const legacyDays = num(meta.legacy_day_count, Math.max(0, decisionDays - contractDays));
  const executable = num(meta.executable_prediction_count);
  const noValidPickDays = num(meta.no_valid_pick_day_count);
  const pending = num(meta.pending_settlement_count);
  const settled = num(meta.settled_sample_count);
  const invalidOutcome = num(meta.invalid_settlement_count);
  const missingOutcome = num(meta.missing_outcome_count);
  const returned = num(meta.returned_count, state.history.length);
  const hasMore = meta.has_more === true;
  const minimumReliableSample = Math.max(0, num(performance.minimum_reliable_sample, 20));
  const cohortIndependentDays = num(performance.cohort_independent_day_count);
  const cohortModelId = performance.cohort_model_id ? String(performance.cohort_model_id) : "";
  const cohortLabelVersion = performance.cohort_label_version ? String(performance.cohort_label_version) : "";
  const sampleStatus = String(performance.sample_status || "UNAVAILABLE").toUpperCase();
  const metricsExpandedByDefault = sampleStatus !== "NO_SAMPLE" || !window.matchMedia?.("(max-width: 760px)")?.matches;
  const comparableMetric = metrics.comparable_sample_count || {};
  const comparableSampleCount = Number.isFinite(Number(comparableMetric.value)) ? Number(comparableMetric.value) : settled;
  const performanceState = ({
    READY: { label: "READY", tone: "positive", title: "十日预测样本已达到最低可靠门槛" },
    EARLY_SAMPLE: { label: "EARLY SAMPLE", tone: "warning", title: "已有可核验样本，但仍处于早期观察期" },
    NO_SAMPLE: { label: "NO SAMPLE", tone: "negative", title: "暂无已结算的可执行预测样本" },
    UNAVAILABLE: { label: "CONTRACT UNAVAILABLE", tone: "negative", title: "历史绩效合同暂不可用" },
  })[sampleStatus] || { label: sampleStatus || "UNKNOWN", tone: "negative", title: "历史绩效状态无法识别" };
  const cohortCopy = sampleStatus === "READY"
    ? `${fmt(comparableSampleCount, 0)} 个合法样本已达到最低可靠门槛 ${fmt(minimumReliableSample, 0)}。`
    : sampleStatus === "EARLY_SAMPLE"
      ? `${fmt(comparableSampleCount, 0)} / ${fmt(minimumReliableSample, 0)} 个合法样本；指标只作早期观察，不作为稳定胜率。`
      : sampleStatus === "NO_SAMPLE"
        ? (cohortIndependentDays ? `${fmt(cohortIndependentDays, 0)} 个当前模型独立决策日中，待结算 ${fmt(pending, 0)} 个、缺结算 ${fmt(missingOutcome, 0)} 个、无效结算 ${fmt(invalidOutcome, 0)} 个。` : `${fmt(contractDays, 0)} 个正式合同决策日中，主动放弃 ${fmt(noValidPickDays, 0)} 日，因此没有买入预测可结算。`)
        : "API 尚未发布 history-performance-v1；前端不会用每日归档自行拼算收益。";
  const cohortSentence = cohortModelId && cohortLabelVersion
    ? `当前绩效 cohort 为 ${cohortModelId} / ${cohortLabelVersion}，按 target_date 仅保留最晚发布预测。`
    : "当前尚无可执行模型 cohort；不会用 Legacy 或 Shadow 记录补位。";
  const coverageSentence = `${fmt(rawRuns, 0)} 次原始运行已合并为 ${fmt(decisionDays, 0)} 个决策日；${fmt(contractDays, 0)} 日属于 global-10d-v1，${fmt(legacyDays, 0)} 日仅为 Legacy 档案。${cohortSentence}`;
  root.innerHTML = `
    <div class="principle-strip"><span><b>评估原则</b> 正式可执行绩效与 Shadow 研究轨完全分开；所有指标只读取后端发布的合法结算合同。</span><small class="${performanceState.tone}">${esc(performance.schema_version || "PERFORMANCE_CONTRACT_MISSING")}</small></div>
    <section class="evaluation-not-ready is-${esc(sampleStatus.toLowerCase())}">
      <div><span class="status-pill ${performanceState.tone}">${esc(performanceState.label)}</span>${sampleStatus === "EARLY_SAMPLE" ? `<span class="status-pill warning early-sample-badge">早期样本</span>` : ""}<h2>${esc(performanceState.title)}</h2><p>${esc(coverageSentence)}</p><strong>${esc(cohortCopy)}</strong></div>
      <aside><h3>正式样本门槛</h3><ol><li>仅限 global-10d-v1 可执行预测</li><li>按不可变 prediction_id 去重</li><li>进出场、费用、复权与日历必须完整</li><li>NO_VALID_PICK 是主动放弃，不计为亏损</li><li>Shadow 研究轨永不进入正式分母</li></ol></aside>
    </section>
    ${renderKpis([
      { icon: "ph-files", label: "原始运行", value: fmt(rawRuns, 0), meta: "全部不可变运行记录" },
      { icon: "ph-calendar-dots", label: "决策日", value: fmt(decisionDays, 0), meta: `已合并 ${fmt(duplicateRuns, 0)} 次日内重复` },
      { icon: "ph-seal-check", label: "正式合同日", value: fmt(contractDays, 0), tone: contractDays ? "primary" : "negative", meta: "global-10d-v1" },
      { icon: "ph-archive", label: "Legacy 历史日", value: fmt(legacyDays, 0), tone: "warning", meta: "仅作规则档案" },
      { icon: "ph-crosshair", label: "可执行预测", value: fmt(executable, 0), meta: `当前 cohort ${fmt(cohortIndependentDays, 0)} 个独立决策日` },
      { icon: "ph-hourglass", label: "待结算", value: fmt(pending, 0), meta: "正式预测 PENDING" },
      { icon: "ph-check-circle", label: "已结算样本", value: fmt(settled, 0), tone: settled ? "positive" : "negative", meta: "完整 outcome 合同" },
      { icon: "ph-prohibit", label: "主动放弃日", value: fmt(noValidPickDays, 0), meta: "NO_VALID_PICK 不算亏损" },
    ])}
    <div class="evaluation-tabs" aria-label="评估维度"><button class="is-active" type="button">10日表现</button><button type="button" disabled>概率校准</button><button type="button" disabled>分市场表现</button><button type="button" disabled>版本对比</button><button type="button" disabled>失效分析</button><span>真实合同指标 · 非浏览器回填 · 非模拟收益</span></div>
    <details class="history-metrics-details ${sampleStatus === "NO_SAMPLE" ? "is-no-sample" : ""}" ${metricsExpandedByDefault ? "open" : ""}><summary>${icon("ph-chart-bar")}<span>查看指标定义</span><small>${fmt(HISTORY_PERFORMANCE_METRICS.length, 0)} 项 · ${sampleStatus === "NO_SAMPLE" ? "当前无可计算样本" : performanceState.label}</small>${icon("ph-caret-down")}</summary><section class="evaluation-metric-grid">${HISTORY_PERFORMANCE_METRICS.map((definition) => renderHistoryMetric(definition, metrics, performance)).join("")}</section></details>
    ${renderShadowResearchPanel(shadowLedger)}
    <section class="panel evaluation-method"><header class="panel-header"><div><h3 class="panel-title">历史检验如何回答“今天买哪只更可能在两周内赚得最多”</h3><p class="panel-subtitle">评估既看收益排序，也看概率是否可信、风险是否可承受</p></div></header><div><article><b>01｜点时数据</b><p>当时可见的价格、财务与事件，禁止未来函数。</p></article><article><b>02｜净总回报</b><p>包含股息、扣除税费、点差、滑点与汇兑成本。</p></article><article><b>03｜概率校准</b><p>检验 P(R10&gt;0) 是否与真实频率一致。</p></article><article><b>04｜失效分析</b><p>按市场、行情状态、成本和事件类型拆解。</p></article></div></section>
    <details class="history-archive" ${state.historyArchiveOpen ? "open" : ""}><summary>${icon("ph-archive")} 查看每日决策快照（${hasMore ? `已载入 ${fmt(returned, 0)} / ` : ""}${fmt(decisionDays, 0)} 个决策日）</summary><div class="history-archive-body">
      <div class="callout info">${icon("ph-info")}<div><strong>${fmt(rawRuns, 0)} 次原始运行 → ${fmt(decisionDays, 0)} 个每日代表快照</strong><br>同一 target_date 优先展示正式 global-10d 合同，同类保留最后一次运行；绩效另限定当前模型与标签版本，并在每个 target_date 只保留最晚发布的可执行预测。</div></div>
      <div class="filter-strip"><div class="filter-group"><span>市场</span><div class="segmented-button">${MARKET_ORDER.map((market) => `<button data-action="history-market" data-market="${market}" aria-pressed="${state.historyMarket === market}">${MARKET_META[market].label}</button>`).join("")}</div></div><label>动作<select id="historyAction"><option value="all">全部</option><option value="buy">有 Legacy 首选</option><option value="no_trade">不交易</option></select></label><label class="search-field">${icon("ph-magnifying-glass")}<input id="historySearch" type="search" value="${esc(state.historyQuery)}" placeholder="搜索日期 / 公司 / 代码" aria-label="搜索历史"></label></div>
      <div class="master-detail history-master-detail"><section class="panel"><header class="panel-header"><div><h3 class="panel-title">每日档案列表</h3><p class="panel-subtitle">正式预测状态与 Shadow 研究状态独立展示</p></div></header>${rows.length ? `<div class="snapshot-list">${rows.map((item) => { const summary = historyMarketSummary(item); const official = item.global_decision?.primary; const globalAbstained = historyKind(item) === "global_10d_v1" && String(item.global_decision?.action || "").toUpperCase() === "NO_VALID_PICK"; const key = item.snapshot_key || item.cache_key; const displayName = official?.name || (globalAbstained ? "本轮主动放弃" : summary.name || "本轮无 Legacy 首选"); const displayCode = official?.code || official?.symbol || (globalAbstained ? item.global_decision?.blocker_codes?.[0] || "NO_VALID_PICK" : summary.code || summary.message || "无首选"); const displayScore = official ? `${fmt(num(official.probability) * 100, 0)}%` : summary.has_primary && !globalAbstained ? fmt(summary.recommendation_degree ?? summary.confidence, 0) : "NO"; return `<button class="snapshot-row ${key === state.historyKey ? "is-selected" : ""}" type="button" data-action="select-history" data-key="${esc(key)}"><time>${historyTargetLabel(item, true)} ${esc(item.target_date || "--")}<small>信号 ${esc(item.signal_date || "--")} · ${esc(dateTime(item.generated_at, false))}</small></time><span><b>${esc(displayName)}</b><small>${esc(historyKindLabel(item))} · ${esc(displayCode)}</small><span class="history-row-statuses">${historyFormalStatusTag(item)}${shadowOutcomeTag(item)}</span></span><strong>${displayScore}</strong>${icon("ph-caret-right")}</button>`; }).join("")}</div>` : `<div class="empty-state">${icon("ph-funnel-x")}<h3>没有匹配快照</h3></div>`}</section><div>${historyDetail(selected)}</div></div>
    </div></details>`;
  const actionSelect = $("#historyAction");
  if (actionSelect) actionSelect.value = state.historyAction;
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
  const tenDay = tenDayModelState(snapshot);
  const tenDayLive = tenDay.ready;
  const aRecall = recallFunnel(snapshot.markets?.a_share || {}, "a_share");
  const hkRecall = recallFunnel(snapshot.markets?.hk || {}, "hk");
  const usRecall = recallFunnel(snapshot.markets?.us || {}, "us");
  const aShareStageRows = aRecall.hasFullScoringStages
    ? `<dt>A股全池评分</dt><dd>基础 ${fmt(aRecall.baseScored, 0)}；技术 ${fmt(aRecall.technicalScored, 0)} / 尝试 ${fmt(aRecall.technicalAttempted, 0)}；K线完整 ${fmt(aRecall.technicalKlineComplete, 0)}，短历史候选保守降权</dd><dt>A股深度研究</dt><dd>${fmt(aRecall.deepScored, 0)} / ${fmt(aRecall.deepAttempted, 0)}；可深研 ${fmt(aRecall.deepEligible, 0)}；仅这层运行 Serenity、UZI、评审团、完整 Legacy/V2 门禁</dd>`
    : `<dt>A股评分快照</dt><dd>旧快照待更新；当前只发布深评 ${fmt(aRecall.deepScored, 0)}，不能据此声称全部召回候选已完成基础和技术评分</dd>`;
  const dynamicRecallCopy = (marketKey, recall, target) => {
    const stats = snapshot.markets?.[marketKey]?.stats || {};
    const origin = stats.universe_origin;
    const counts = `${fmt(recall.selected, 0)} / ${fmt(recall.target || target, 0)}`;
    const eligible = fmt(num(stats.eligible_discovery_size, 0), 0);
    if (origin === "dynamic_market_snapshot") {
      return `${counts}；本轮从 ${eligible} 只合格公开横截面中，按成交、活跃度、动量、回调和规模重新入池`;
    }
    if (origin === "dynamic_market_snapshot_cache") {
      return `${counts}；使用上次健康动态池缓存，本轮没有完成市场重扫，仅供研究且不放行推荐`;
    }
    if (origin === "curated_static") {
      return `${counts}；这是旧快照的版本化静态池，等待下一次定时或手动任务生成动态池`;
    }
    return `${counts}；动态市场召回尚未完成，本轮不放行推荐`;
  };
  const hkRecallCopy = dynamicRecallCopy("hk", hkRecall, 200);
  const usRecallCopy = dynamicRecallCopy("us", usRecall, 300);
  root.innerHTML = `
    <section class="objective-formula"><div><small>核心优化目标</small><strong>最终效用 ＝ 预期 10 日净总回报 − λ × 尾部风险 − μ × 交易成本 − ν × 数据不确定性</strong><p>净总回报包含股息，并扣除手续费、税费、点差、滑点与汇兑成本；缺失任一关键项时不输出可执行股票。</p></div><span>HORIZON · 10 TRADING DAYS</span></section>
    <section class="panel model-pipeline-panel"><header class="panel-header"><div><h3 class="panel-title">7 阶段决策流水线</h3><p class="panel-subtitle">任一关键门禁失败，自动回退为 NO_VALID_PICK</p></div>${badge(snapshot.selector_mode || "legacy_active", "purple")}</header><ol class="pipeline-list pipeline-seven"><li><span>01</span><div><b>三市场有界动态召回</b><p>A / 港 / 美候选覆盖与召回来源。</p></div></li><li><span>02</span><div><b>交易与数据门禁</b><p>流动性、停牌、完整性和新鲜度。</p></div></li><li><span>03</span><div><b>因子和事件特征</b><p>Legacy、V2、双低与外部证据分开。</p></div></li><li><span>04</span><div><b>分市场 10 日模型</b><p>${tenDayLive ? "预测净总回报分布；已参与门禁。" : "预测净总回报分布；当前未上线。"}</p></div></li><li><span>05</span><div><b>概率校准</b><p>${tenDayLive ? "P(R10>0) 已校准并记录模型版本。" : "P(R10>0) 样本外校准；当前未上线。"}</p></div></li><li><span>06</span><div><b>跨市场效用排名</b><p>收益、风险、成本与不确定性统一比较。</p></div></li><li class="is-gate"><span>07</span><div><b>可执行性复核</b><p>价格、仓位、事件时点与尾部风险。</p></div></li></ol></section>
    <section class="model-version-grid"><article class="panel"><header class="panel-header"><div><h3 class="panel-title">版本状态</h3><p class="panel-subtitle">实际运行、影子观察与计划能力明确分开</p></div></header><div class="version-table"><div><b>Legacy</b><span class="status-pill positive">运行中</span><small>规则评分与市场级动作</small></div><div><b>V2</b><span class="status-pill primary">影子</span><small>分组因子与市场内结构排名</small></div><div><b>10 日收益模型</b><span class="status-pill ${tenDayLive ? "positive" : "warning"}">${tenDayLive ? "运行中" : "计划"}</span><small>${tenDayLive ? esc(tenDay.model.model_id || "已校准模型") : "净收益分布与 P(R10>0)"}</small></div><div><b>数据闸门</b><span class="status-pill positive">运行中</span><small>可直接输出 NO_VALID_PICK</small></div></div></article><article class="panel"><header class="panel-header"><div><h3 class="panel-title">术语边界</h3><p class="panel-subtitle">分数、概率与动作不能混用</p></div></header><dl class="term-list"><dt>规则分</dt><dd>现有规则匹配程度，不等于上涨概率</dd><dt>正收益概率</dt><dd>经样本外校准的 P(R10&gt;0)</dd><dt>预测净收益</dt><dd>最终跨市场排序目标</dd><dt>置信度</dt><dd>数据和模型不确定性</dd><dt>研究优先</dt><dd>值得继续核验，不等于建议买入</dd></dl></article></section>
    <div class="model-grid">
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">旧因子仍然保留</h3><p class="panel-subtitle">回答“之前的评分还在吗”</p></div>${badge("Active", "positive")}</header><div class="legacy-map"><div><b>初筛 pre_score</b><span>成交额、换手、量比、涨幅等</span></div><div><b>缠论近似 chan_score</b><span>均线结构、二买 / 三买、箱体回踩</span></div><div><b>CZSC 近似</b><span>中枢、趋势、箱体位置与背驰风险</span></div><div><b>UZI + 评审团</b><span>买点纪律、流动性、过热和杀猪盘门控</span></div><div><b>Serenity 先验</b><span>AI capex 上游稀缺环节与融资风险</span></div><div><b>推荐度与动作</b><span>只决定市场内 Legacy 排名与信号；能否执行由 global 严格门禁决定</span></div></div></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">V2 分组权重</h3><p class="panel-subtitle">随市场状态采用规则先验；分数只作影子观察</p></div>${badge(snapshot.weights_version || "示意基准", "purple")}</header><div class="weight-list">${weights.map(([label, value]) => `<div><span>${esc(label)}</span><div class="progress-bar"><span style="width:${clamp(value)}%"></span></div><b>${fmt(value, 0)}%</b></div>`).join("")}</div><p class="fine-print">若市场基准数据不足，状态为 unknown 并保守处理；这里不声称是机器学习概率。</p></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">双低七因子 · 独立影子</h3><p class="panel-subtitle">补充估值视角，不与 Legacy / V2 机械相加</p></div>${badge(dualModel.status === "available" ? "Shadow available" : "Shadow", dualModel.status === "available" ? "positive" : "warning")}</header><dl><dt>模型</dt><dd>${esc(dualModel.model_id || "dsa-screening-score-v1")}</dd><dt>市场</dt><dd>A股；港美暂不适用</dd><dt>比较池</dt><dd>${esc(dualModel.pool_scope || "a_share.merged_recall_quote_pool.pre_kline_v1")}</dd><dt>输入 / 合格</dt><dd>${dualModel.input_count === undefined ? "待新快照" : `${fmt(dualModel.input_count, 0)} / ${fmt(dualModel.eligible_count, 0)}`}</dd><dt>默认风格</dt><dd>PE≤15、PB≤2、不过热</dd><dt>决策权限</dt><dd>无；仅输出研究优先级</dd></dl><p class="fine-print">“被过滤”只表示不符合这套价值风格或数据不完整，不表示公司质量差。</p></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">候选池边界</h3><p class="panel-subtitle">先扩大召回，再用行情、技术评分和深度研究逐层收窄</p></div></header><dl><dt>A股</dt><dd>${fmt(aRecall.selected, 0)} / ${fmt(aRecall.target || 300, 0)}；沪主板 90、深主板 75、创业板 75、科创板 60</dd>${aShareStageRows}<dt>A股路由</dt><dd>事件、动量、流动性、交易活跃、可控回调；历史延续只在实时宽基不足时补位</dd><dt>港股</dt><dd>${hkRecallCopy}</dd><dt>美股</dt><dd>${usRecallCopy}</dd><dt>港美动态源</dt><dd>主源必须带可验证的市场时间；无源时间的备用榜单和上次动态池只供研究，不放行推荐</dd><dt>新快照六层口径</dt><dd>公开横截面发现 → 普通股/可交易过滤 → 动态入池 → 有效行情 → 完整技术深评 → 决策候选</dd><dt>交易日</dt><dd>XSHG / XHKG / XNYS 真实交易所日历，分市场计算入场和第 10 个交易日退出</dd></dl></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">运行架构</h3><p class="panel-subtitle">公开站点不依赖 Render、OpenD 或个人电脑常开</p></div>${badge("Cloudflare only", "primary")}</header><div class="architecture-list"><div>${icon("ph-github-logo")}<span><b>GitHub Actions</b><small>定时运行 Python，生成最新快照与历史文件</small></span></div><div>${icon("ph-package")}<span><b>构建时 JSON assets</b><small>数据随 Worker 部署，不使用 KV / D1 / R2</small></span></div><div>${icon("ph-cloud")}<span><b>Cloudflare Worker</b><small>提供静态页面、快照、历史与状态 API</small></span></div><div>${icon("ph-browser")}<span><b>浏览器</b><small>渲染证据、筛选与执行提示；评分与排序不在浏览器重算</small></span></div></div></article>
    </div>
    <section class="panel section-gap"><header class="panel-header"><div><h3 class="panel-title">能力状态与限制</h3><p class="panel-subtitle">不把近似规则包装成官方框架</p></div></header><div class="truth-grid"><div><span class="status-pill warning">内置近似</span><b>缠论 / CZSC</b><p>用日线均线、箱体、突破回踩和背驰风险近似，不是原生 CZSC 执行。</p></div><div><span class="status-pill warning">方法论加权</span><b>UZI</b><p>内置轻量评审和风控规则，不是外部 UZI 模型服务。</p></div><div><span class="status-pill warning">中性先验</span><b>Serenity</b><p>港美动态池统一使用中性 lens，避免旧静态名单获得手工元数据优势；差异由行情与结构信号产生。</p></div><div><span class="status-pill primary">纯云端快照</span><b>行情交付</b><p>页面只读取 GitHub Actions 已发布批次，不宣称盘中实时；源时间与快照生成时间分开。</p></div></div></section>`;
}

function renderHealth() {
  const root = $("#healthView");
  const truth = globalDecisionTruth();
  const status = state.status || {};
  const schedulerRunning = status.ok !== false && Boolean(state.snapshot?.generated_at);
  const primarySchedule = (status.schedule_primary_checkpoints || ["08:17", "10:17", "12:17", "15:17", "16:17", "20:17", "22:47"]).join(" / ");
  const fallbackSchedule = (status.schedule_fallback_checkpoints || ["08:47", "10:47", "12:47", "15:47", "16:47", "20:47", "23:17"]).join(" / ");
  const readyMarkets = truth.markets.filter((item) => item.state === "READY").length;
  const recallTargetsMet = truth.markets.every((market) => {
    const funnel = recallFunnel(market.section, market.market);
    return funnel.target > 0 && funnel.selected >= funnel.target;
  });
  const quoteRequested = (market) => num(market?.quoteHealth?.requested_count, 0);
  const quoteCount = (market) => num(market?.quoteHealth?.quote_count, 0);
  const marketTone = (market) => market.state === "READY" ? "positive" : market.state === "BLOCKED" ? "negative" : "warning";
  const marketStateLabel = (market) => market.state === "READY" ? "可评估" : market.state === "BLOCKED" ? "阻断" : "降级";
  const marketMetrics = (market) => {
    const universeLabel = market.origin === "dynamic_market_snapshot" ? "动态市场池" : market.origin === "curated_static" ? "静态池" : "召回池";
    const funnel = recallFunnel(market.section, market.market);
    const prefix = market.market === "a_share"
      ? `宽基 ${fmt(market.pool.broadPoolSize ?? market.stats.broad_pool_size, 0)} · 召回 ${fmt(funnel.selected, 0)}/${fmt(funnel.target, 0)}`
      : `${universeLabel} ${fmt(funnel.selected, 0)}/${fmt(funnel.target, 0)} · 发现 ${fmt(market.stats.eligible_discovery_size, 0)}`;
    const freshCount = num(market.quoteHealth?.realtime_count, quoteCount(market));
    const aShareScoringMetrics = funnel.hasFullScoringStages
      ? ` · 基础 ${fmt(funnel.baseScored, 0)} · 技术 ${fmt(funnel.technicalScored, 0)}/${fmt(funnel.technicalAttempted, 0)}（K线完整 ${fmt(funnel.technicalKlineComplete, 0)}） · 可深研 ${fmt(funnel.deepEligible, 0)} · 深研 ${fmt(funnel.deepScored, 0)}/${fmt(funnel.deepAttempted, 0)}`
      : ` · 深评 ${fmt(funnel.deepScored, 0)} · 旧快照待更新`;
    return quoteRequested(market)
      ? `${prefix} · 有效行情 ${fmt(quoteCount(market), 0)}/${fmt(quoteRequested(market), 0)} · 最近时段 ${fmt(freshCount, 0)}/${fmt(quoteRequested(market), 0)}${market.market === "a_share" ? aShareScoringMetrics : ` · 深评 ${fmt(funnel.deepScored, 0)}`}`
      : `${prefix} · 行情健康未发布`;
  };
  const row = (label, tone, stateLabel, metrics, impact) => `<div class="health-table-row"><b>${esc(label)}</b><span class="status-pill ${tone}">${esc(stateLabel)}</span><code>${esc(metrics)}</code><p>${esc(impact)}</p></div>`;
  const blockers = truth.blockerCodes.map((code) => GLOBAL_BLOCKER_META[code] || code);
  const usable = truth.action === "REVIEW_EXECUTABLE_PICK";
  root.innerHTML = `
    <div class="principle-strip"><span><b>判断原则</b> 任务运行成功、行情覆盖完整、本轮有界扫描完整和决策可用是四件不同的事。</span><small class="${usable ? "positive" : "negative"}">当前：${usable ? "候选通过严格门禁，仍待人工复核" : "全局结论被严格门禁阻断"}</small></div>
    <div class="callout ${usable ? "" : "negative"} health-alert">${icon(usable ? "ph-check-circle" : "ph-warning-octagon")}<div><strong>${usable ? "跨市场候选契约完整" : "当前数据质量不足以生成跨市场买入结论"}</strong><br>${usable ? "概率、净效用、成本、尾部风险、市场覆盖和官方证据均已通过契约校验。" : esc(blockers.slice(0, 5).join("；") || "没有候选通过全部严格门禁。")}</div></div>
    ${renderKpis([
      { icon: "ph-globe", label: "可比较市场", value: `${readyMarkets} / 3`, tone: readyMarkets === 3 ? "positive" : "negative", meta: "A股、港股、美股须口径可比" },
      { icon: "ph-binoculars", label: "三市场召回目标", value: recallTargetsMet ? "300 / 200 / 300" : "未达标", tone: recallTargetsMet ? "positive" : "warning", meta: "A股 / 港股 / 美股；行情与深评另行门控" },
      { icon: "ph-newspaper", label: "外部自动证据", value: fmt(truth.autoEvidenceCount, 0), tone: truth.autoEvidenceCount ? "positive" : "negative", meta: `模型信号 ${eventItems().filter((event) => event.event_type === "model_signal").length} 条不等于证据` },
      { icon: "ph-clock-clockwise", label: "发布状态", value: schedulerRunning ? "可访问" : "需检查", tone: schedulerRunning ? "positive" : "negative", meta: `新鲜度 ${esc(status.freshness_state || "unknown")}` },
    ])}
    <section class="health-layout"><article class="panel"><header class="panel-header"><div><h3 class="panel-title">市场与数据源状态</h3><p class="panel-subtitle">健康状态直接解释为什么不能给出买入答案</p></div></header><div class="health-table"><div class="health-table-head"><span>对象</span><span>状态</span><span>关键指标</span><span>说明与决策影响</span></div>
      ${truth.markets.map((market) => row(MARKET_META[market.market].label, marketTone(market), marketStateLabel(market), marketMetrics(market), market.reasons.join("；") || "关键数据门禁已通过")).join("")}
      ${row("事件数据", truth.autoEvidenceCount ? "warning" : "negative", truth.autoEvidenceCount ? "待复核" : "严重缺口", `外部自动 ${truth.autoEvidenceCount} · 模型信号 ${eventItems().filter((event) => event.event_type === "model_signal").length}`, "事件因子不可作为自动买入依据")}
      ${row("发布任务", schedulerRunning ? "positive" : "negative", schedulerRunning ? "页面可用" : "需检查", `最近快照 ${dateTime(state.snapshot?.generated_at)}`, "页面可用和快照新鲜，不代表决策数据完整")}
    </div></article><aside class="health-side"><article class="panel"><header class="panel-header"><div><h3 class="panel-title">实际更新机制</h3><p class="panel-subtitle">纯云端批次快照，不依赖个人设备</p></div>${badge("已配置", "primary")}</header><dl><dt>主刷新</dt><dd>工作日北京时间 ${esc(primarySchedule)}</dd><dt>健康补跑</dt><dd>工作日北京时间 ${esc(fallbackSchedule)}；已有健康快照则跳过</dd><dt>快照生成</dt><dd>${esc(dateTime(status.snapshot_as_of || state.snapshot?.generated_at))}</dd><dt>下次计划检查点（含健康补跑）</dt><dd>${esc(dateTime(status.next_refresh))}</dd><dt>交易日窗口</dt><dd>XSHG / XHKG / XNYS 真实日历</dd><dt>结果跟踪</dt><dd>每日末次主快照登记 PENDING，第 10 个交易日后结算</dd></dl></article><article class="panel"><header class="panel-header"><div><h3 class="panel-title">调度正常，不代表结果可信</h3></div></header><p>任务可以完成，但如果召回池、外部证据或概率模型缺失，页面仍必须显示阻断；GitHub 调度也不承诺严格准点。</p>${badge(schedulerRunning ? "当前：发布可访问" : "当前：发布待检查", schedulerRunning ? "primary" : "negative")}</article><a class="secondary-button" href="https://github.com/dzhdingzihang/xuangu/actions" target="_blank" rel="noopener noreferrer">查看最近一次任务 ${icon("ph-arrow-square-out")}</a></aside></section>`;
}

function renderActiveTab() {
  if (!state.snapshot) return;
  const view = $(`#${state.tab}View`);
  if (view) view.classList.remove("view-loading");
  ({ decision: renderDecision, candidates: renderCandidates, events: renderEvents, history: renderHistory, model: renderModel, health: renderHealth })[state.tab]?.();
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

async function loadHistorySnapshot(key) {
  if (!key) return;
  try {
    state.historySnapshot = await getJson(`/api/pick?snapshot=${encodeURIComponent(key)}`);
    state.historySnapshotKey = key;
    renderHistory();
    showToast("完整历史快照已载入。", "success");
  } catch (error) {
    showToast(error.message || "历史快照载入失败", "error");
  }
}

async function refreshAll() {
  const requestGeneration = ++snapshotLoadGeneration;
  const button = $("#refreshBtn");
  button.classList.add("is-loading"); button.disabled = true;
  try {
    const [status, historyPayload, snapshot] = await Promise.all([getJson("/api/status"), getHistoryPayload(), getJson("/api/latest")]);
    if (requestGeneration !== snapshotLoadGeneration) return;
    if (status.generated_at && snapshot.generated_at !== status.generated_at) throw new Error("最新快照仍在边缘节点传播");
    state.status = status;
    state.history = historyPayload.history || [];
    state.historyMeta = historyPayload.meta || {};
    state.historyError = "";
    state.snapshot = snapshot;
    state.historySnapshot = null;
    state.historySnapshotKey = "";
    renderRail(); updateTopbar(); renderActiveTab();
    showToast("最新已发布快照已刷新。Cloudflare 页面不会在线重算选股。", "success");
  } catch (error) {
    renderActiveTab();
    showToast(error.message || "刷新失败", "error");
  } finally {
    button.classList.remove("is-loading"); button.disabled = false;
  }
}

let statusPollInFlight = false;
let snapshotLoadGeneration = 0;
async function pollStatus() {
  if (statusPollInFlight) return;
  statusPollInFlight = true;
  const previousGeneratedAt = state.snapshot?.generated_at || state.status?.generated_at || null;
  const previousStatusKey = JSON.stringify([
    state.status?.ok,
    state.status?.freshness_state,
    state.status?.expected_checkpoint,
    state.status?.checkpoint_lag_minutes,
  ]);
  try {
    const status = await getJson("/api/status");
    state.status = status;
    updateTopbar();
    const statusChanged = previousStatusKey !== JSON.stringify([
      status.ok,
      status.freshness_state,
      status.expected_checkpoint,
      status.checkpoint_lag_minutes,
    ]);
    if (!state.snapshot || (status.generated_at && status.generated_at !== previousGeneratedAt)) {
      const requestGeneration = ++snapshotLoadGeneration;
      const [snapshot, historyPayload] = await Promise.all([
        getJson("/api/latest"),
        getHistoryPayload(),
      ]);
      if (requestGeneration !== snapshotLoadGeneration) return;
      if (status.generated_at && snapshot.generated_at !== status.generated_at) throw new Error("新快照仍在边缘节点传播");
      state.snapshot = snapshot;
      state.history = historyPayload.history || [];
      state.historyMeta = historyPayload.meta || {};
      state.historyError = "";
      state.historySnapshot = null;
      state.historySnapshotKey = "";
      if (!state.candidateKey || !allCandidates().some((row) => candidateId(row.candidate, row.market) === state.candidateKey)) {
        const first = researchPriorityCandidate() || allCandidates()[0];
        state.candidateKey = first ? candidateId(first.candidate, first.market) : "";
      }
      renderRail();
      updateTopbar();
      renderActiveTab();
      showToast("检测到新决策快照，页面已自动更新；筛选条件保持不变。", "success");
    } else if (statusChanged) {
      renderActiveTab();
    }
  } catch (error) {
    state.status = { ...(state.status || {}), ok: false, freshness_state: "unknown" };
    updateTopbar();
    renderActiveTab();
    window.setTimeout(pollStatus, 15_000);
  } finally {
    statusPollInFlight = false;
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
  const { action, market, key } = control.dataset;
  if (action === "market") { state.market = market; state.candidateFilters.market = market; switchTab("candidates"); return; }
  if (action === "candidate-market") { state.candidateFilters.market = market; if (state.tab !== "candidates") switchTab("candidates"); else renderCandidates(); return; }
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
  if (action === "go-events") { switchTab("events"); return; }
  if (action === "go-health") { switchTab("health"); return; }
  if (action === "compare") {
    if (state.compare.includes(key)) state.compare = state.compare.filter((item) => item !== key);
    else if (state.compare.length < 3) state.compare.push(key);
    else showToast("最多同时对比 3 只候选。", "error");
    renderCandidates(); return;
  }
  if (action === "clear-compare") { state.compare = []; renderCandidates(); return; }
  if (action === "event-market") { state.eventFilters.market = market; renderEvents(); return; }
  if (action === "select-event") { state.eventKey = key; renderEvents(); return; }
  if (action === "history-market") { state.historyMarket = market; state.historyKey = ""; state.historySnapshot = null; state.historySnapshotKey = ""; renderHistory(); return; }
  if (action === "select-history") {
    state.historyKey = key;
    state.historySnapshot = null;
    state.historySnapshotKey = "";
    renderHistory();
    if (window.matchMedia?.("(max-width: 760px)")?.matches) {
      requestAnimationFrame(() => $(".history-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
    return;
  }
  if (action === "load-history") { loadHistorySnapshot(key); return; }
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
      const candidate = currentCandidate(marketDecision(state.snapshot));
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
  window.setInterval(pollStatus, STATUS_POLL_INTERVAL_MS);
  try {
    const [statusResult, historyResult, latestResult] = await Promise.allSettled([
      getJson("/api/status"), getHistoryPayload(), getJson("/api/latest"),
    ]);
    state.status = statusResult.status === "fulfilled" ? statusResult.value : { ok: false };
    state.history = historyResult.status === "fulfilled" ? historyResult.value.history || [] : [];
    state.historyMeta = historyResult.status === "fulfilled" ? historyResult.value.meta || {} : {};
    state.historyError = historyResult.status === "fulfilled" ? "" : (historyResult.reason?.message || "历史清单读取失败");
    if (latestResult.status !== "fulfilled") throw latestResult.reason;
    state.snapshot = latestResult.value;
    const first = researchPriorityCandidate() || allCandidates()[0];
    if (first) state.candidateKey = candidateId(first.candidate, first.market);
    renderRail();
    switchTab(location.hash.slice(1) || "decision", false);
    window.setTimeout(pollStatus, 1500);
  } catch (error) {
    updateTopbar();
    $$(".view-loading").forEach((view) => { view.innerHTML = `<div class="empty-state">${icon("ph-warning-circle")}<h3>无法读取决策快照</h3><p>${esc(error.message || "请稍后刷新")}</p><button class="icon-button" type="button" onclick="location.reload()">重新加载</button></div>`; });
    showToast(error.message || "初始化失败", "error");
    window.setTimeout(pollStatus, 5000);
  }
}

initialize();

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const MARKET_ORDER = ["a_share", "hk", "us"];
const CURRENT_PRODUCTION_MODEL_VERSION = "smart-selector-2026-08-29.1-two-tier-rule";
const CURRENT_PRODUCTION_RULE_CONTRACT = {
  actionBasis: "dual_track_candidate_qualification_v4",
  ruleModelId: "ten-day-audited-rule-ensemble-v4",
};
const HISTORICAL_PRODUCTION_RULE_CONTRACTS = {
  "smart-selector-2026-08-25.1-production-rule": {
    actionBasis: "strict_rule_qualification_v1",
    ruleModelId: "ten-day-audited-rule-ensemble-v1",
  },
  "smart-selector-2026-08-26.1-candidate-rule": {
    actionBasis: "candidate_level_rule_qualification_v2",
    ruleModelId: "ten-day-audited-rule-ensemble-v2",
  },
  "smart-selector-2026-08-26.2-dual-track-rule": {
    actionBasis: "dual_track_candidate_qualification_v3",
    ruleModelId: "ten-day-audited-rule-ensemble-v3",
  },
};
const RESOURCE_CONTRACT_VERSIONS = {
  candidates: new Set(["candidate-list-v2", "ui-candidates-v2", "candidate-list-v1", "ui-candidates-v1"]),
  events: new Set(["event-list-v2", "event-list-v1", "ui-events-v2", "ui-events-v1"]),
  history: new Set(["history-list-v1"]),
  candidateDetail: new Set(["candidate-detail-v2", "candidate-detail-v1"]),
  scheduler: new Set(["scheduler-health-v2", "scheduler-health-v1"]),
};
const PRODUCTION_QUALIFICATION_TRACKS = ["event_catalyst", "quality_technical"];
const PRODUCTION_EVENT_POLICY = {
  a_share: { minimumLegacy: 64, maximumDownside: 8, minimumUpside: 5 },
  hk: { minimumLegacy: 63, maximumDownside: 8, minimumUpside: 5 },
  us: { minimumLegacy: 64, maximumDownside: 10, minimumUpside: 6 },
};
const PRODUCTION_QUALITY_POLICY = {
  a_share: { minimumLegacy: 64, maximumDownside: 6, minimumUpside: 6 },
  hk: { minimumLegacy: 67, maximumDownside: 6, minimumUpside: 6 },
  us: { minimumLegacy: 67, maximumDownside: 7.5, minimumUpside: 6.5 },
};
const MARKET_META = {
  a_share: { label: "A股", short: "A", currency: "CNY", dot: "market-a" },
  hk: { label: "港股", short: "港", currency: "HKD", dot: "market-hk" },
  us: { label: "美股", short: "美", currency: "USD", dot: "market-us" },
};
const TAB_META = {
  decision: ["今日答案", "未来 10 个交易日跨市场决策"],
  candidates: ["决策短名单", "从完整扫描池收窄到可复核候选"],
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
  EVENT_PIPELINE_NOT_SCANNED: "官方公告采集没有完成三市场扫描",
  EVENT_CANDIDATE_NOT_SCANNED: "该候选未包含在本批官方公告扫描清单",
  VERIFIED_POSITIVE_EVENT_MISSING: "候选缺少可审计的官方正向事件证据",
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
// Keep the browser request inside the Worker history contract. Older rows are
// retrieved with the existing "load more" control instead of one oversized
// response.
const HISTORY_LIMIT = 5;
const LIST_PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 150;
const REQUEST_TIMEOUT_MS = 12_000;
const TAB_DATA_REQUIREMENTS = {
  decision: [],
  candidates: ["candidates"],
  events: ["events"],
  history: ["history"],
  model: [],
  health: ["scheduler"],
};
const FRESHNESS_META = {
  fresh: { label: "计划批次已发布", icon: "ph-check-circle", className: "is-fresh" },
  updating: { label: "等待计划批次", icon: "ph-arrows-clockwise", className: "is-updating" },
  stale: { label: "计划批次已过期", icon: "ph-warning-circle", className: "is-stale" },
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
  bootstrap: null,
  snapshot: null,
  candidates: [],
  candidatePayload: null,
  candidateDetails: {},
  candidateDetailStatus: {},
  candidateDetailOpen: false,
  eventsPayload: null,
  schedulerGate: null,
  tabData: {
    candidates: { status: "idle", snapshotKey: null, queryKey: "", error: "" },
    events: { status: "idle", snapshotKey: null, queryKey: "", error: "" },
    history: { status: "idle", snapshotKey: null, queryKey: "", error: "" },
    scheduler: { status: "idle", snapshotKey: null, queryKey: "", error: "" },
  },
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
  pagination: {
    candidates: { page: 1, hasMore: false, total: 0, loading: false },
    events: { page: 1, hasMore: false, total: 0, loading: false },
    history: { page: 1, hasMore: false, total: 0, loading: false },
  },
};

const requestControllers = {
  tab: null,
  detail: null,
  historyDetail: null,
};
const searchDebounceTimers = new Map();
let candidateDialogBackgroundState = [];
let tabRequestGeneration = 0;

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

function normalizeCandidateCode(market, value) {
  const raw = String(value || "").trim().toUpperCase();
  if (market === "a_share") {
    const match = raw.match(/^(?:(?:SH|SZ)\.?)?(\d{6})(?:\.(?:SH|SZ))?$/);
    return match ? match[1] : null;
  }
  if (market === "hk") {
    const match = raw.match(/^0*(\d{1,5})(?:\.HK)?$/);
    if (!match) return null;
    const number = Number(match[1]);
    return Number.isInteger(number) && number >= 1 && number <= 9999
      ? `${String(number).padStart(4, "0")}.HK`
      : null;
  }
  if (market === "us") {
    const normalized = raw.replaceAll("_", "-").replaceAll(".", "-");
    return /^[A-Z][A-Z0-9-]{0,14}$/.test(normalized) ? normalized : null;
  }
  return null;
}

function candidateIdentity(market, value) {
  const code = normalizeCandidateCode(market, value);
  return code ? `${market}:${code}` : null;
}

function candidateId(candidate, market) {
  return candidateIdentity(market, candidate?.code || candidate?.symbol)
    || `${market}:${candidate?.name || "unknown"}`;
}

function snapshotUseTruth(snapshot = state.snapshot, status = state.status) {
  const published = status?.snapshot_use || snapshot?.snapshot_use || {};
  const hasPublishedUse = Object.keys(published).length > 0;
  const identityMatches = Boolean(
    snapshot
    && status?.ok !== false
    && (!status?.snapshot_key || status.snapshot_key === snapshot.snapshot_key)
    && (!status?.generated_at || status.generated_at === snapshot.generated_at)
    && (!status?.source_snapshot_sha256
      || status.source_snapshot_sha256 === snapshot?.source_snapshot?.sha256)
    && (status?.source_snapshot_byte_size === undefined
      || status?.source_snapshot_byte_size === null
      || Number(status.source_snapshot_byte_size) === Number(snapshot?.source_snapshot?.byte_size))
    && (!published?.snapshot_key || published.snapshot_key === snapshot.snapshot_key)
  );
  // Archived/full fixtures predate snapshot_use. Production bootstrap responses
  // always publish it, so the compatibility branch cannot bypass the live gate.
  const legacyCurrent = !hasPublishedUse && (!status || status.freshness_state === "fresh");
  const currentDecisionAllowed = Boolean(identityMatches && (legacyCurrent || (
    published?.mode === "CURRENT_RESEARCH"
    && published?.current_decision_allowed === true
    && (published?.freshness_state || status?.freshness_state) === "fresh"
  )));
  const blockerCodes = [...new Set([
    ...(Array.isArray(published?.blocker_codes) ? published.blocker_codes : []),
    ...(!identityMatches ? ["SNAPSHOT_STATUS_IDENTITY_MISMATCH"] : []),
    ...(!currentDecisionAllowed ? ["SNAPSHOT_NOT_FRESH"] : []),
  ])];
  return {
    mode: currentDecisionAllowed ? "CURRENT_RESEARCH" : "HISTORICAL_RESEARCH_ONLY",
    currentDecisionAllowed,
    executionReviewAllowed: currentDecisionAllowed && (legacyCurrent || published?.execution_review_allowed === true),
    freshnessState: published?.freshness_state || status?.freshness_state || (legacyCurrent ? "fresh" : "unknown"),
    identityMatches,
    blockerCodes,
  };
}

function researchCandidateSnapshot(snapshot, market) {
  const lazy = state.candidates.find((candidate) => candidate.market === market && (
    candidate?.decision_roles?.research === "PRIORITY"
    || ["research", "research_priority"].includes(candidate.decision_role)
  ));
  if (lazy) return lazy;
  const priority = snapshot?.global_decision?.research_priority;
  const candidate = priority?.candidate_snapshot;
  if (!priority || !candidate || typeof candidate !== "object" || priority.market !== market) return null;
  const priorityIdentity = candidateIdentity(market, priority.code || priority.symbol);
  const candidateIdentityKey = candidateIdentity(market, candidate.code || candidate.symbol);
  return priorityIdentity && priorityIdentity === candidateIdentityKey ? candidate : null;
}

function productionContractValid(decision, modelVersion = null) {
  const expected = modelVersion === CURRENT_PRODUCTION_MODEL_VERSION
    ? CURRENT_PRODUCTION_RULE_CONTRACT
    : HISTORICAL_PRODUCTION_RULE_CONTRACTS[modelVersion];
  const ruleModelPairValid = Boolean(expected
    && decision?.action_basis === expected.actionBasis
    && decision?.rule_model_id === expected.ruleModelId);
  return Boolean(
    decision
    && typeof decision === "object"
    && decision.contract_version === "production-rule-10d-v1"
    && decision.decision_scope === "global_10d_bounded_recall"
    && ruleModelPairValid
    && ["QUALIFIED_PICK", "NO_QUALIFIED_PICK"].includes(String(decision.action || ""))
    && decision.score_kind === "RULE_QUALIFICATION_SCORE"
    && decision.probability === null
    && decision.calibrated === false
  );
}

function currentProductionContractValid(snapshot = state.snapshot) {
  const decision = snapshot?.production_decision;
  return Boolean(
    snapshot?.model_version === CURRENT_PRODUCTION_MODEL_VERSION
    && decision?.action_basis === CURRENT_PRODUCTION_RULE_CONTRACT.actionBasis
    && decision?.rule_model_id === CURRENT_PRODUCTION_RULE_CONTRACT.ruleModelId
    && productionContractValid(decision, snapshot?.model_version)
  );
}

function finiteRuleNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function roundRuleNumber(value, digits = 2) {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function sameRuleNumber(actual, expected, tolerance = 0.011) {
  return finiteRuleNumber(actual) && Math.abs(actual - expected) <= tolerance;
}

// Python's round() uses ties-to-even while Math.round() rounds midpoint values
// upward.  Keep the published component schema exact, but allow the contract's
// existing one-cent numeric tolerance when the browser independently audits it.
function sameRuleScoreComponents(actual, expected) {
  if (!actual || !expected || typeof actual !== "object" || typeof expected !== "object"
    || Array.isArray(actual) || Array.isArray(expected)) return false;
  const actualKeys = Object.keys(actual).sort();
  const expectedKeys = Object.keys(expected).sort();
  return actualKeys.length === expectedKeys.length
    && actualKeys.every((key, index) => (
      key === expectedKeys[index]
      && sameRuleNumber(actual[key], expected[key])
    ));
}

function sameStringList(actual, expected) {
  return Array.isArray(actual)
    && actual.length === expected.length
    && actual.every((value, index) => typeof value === "string" && value === expected[index]);
}

function stableJsonForComparison(value, ancestors = new Set()) {
  if (value === null) return "null";
  if (["string", "boolean"].includes(typeof value)) return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("non-finite JSON number");
    return JSON.stringify(value);
  }
  if (!value || typeof value !== "object") throw new TypeError("non-JSON value");
  if (ancestors.has(value)) throw new TypeError("cyclic JSON value");
  ancestors.add(value);
  let normalized;
  if (Array.isArray(value)) {
    normalized = `[${value.map((item) => stableJsonForComparison(item, ancestors)).join(",")}]`;
  } else {
    normalized = `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${stableJsonForComparison(value[key], ancestors)}`
    )).join(",")}}`;
  }
  ancestors.delete(value);
  return normalized;
}

function normalizedFullJsonEqual(left, right) {
  try {
    return stableJsonForComparison(left) === stableJsonForComparison(right);
  } catch (_error) {
    return false;
  }
}

function validCurrentTrackEvaluations(evaluations) {
  return Array.isArray(evaluations)
    && evaluations.length === PRODUCTION_QUALIFICATION_TRACKS.length
    && evaluations.every((evaluation, index) => (
      evaluation
      && typeof evaluation === "object"
      && !Array.isArray(evaluation)
      && evaluation.track === PRODUCTION_QUALIFICATION_TRACKS[index]
      && ["PASS", "FAIL"].includes(evaluation.status)
      && Array.isArray(evaluation.blocker_codes)
      && evaluation.blocker_codes.every((code) => typeof code === "string" && code)
      && (evaluation.status === "PASS"
        ? evaluation.blocker_codes.length === 0
        : evaluation.blocker_codes.length > 0)
    ));
}

function ruleText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function dedupeRuleStrings(values) {
  if (!Array.isArray(values)) return null;
  const result = [];
  const seen = new Set();
  for (const value of values) {
    const text = String(value);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
  }
  return result;
}

function frozenCurrentInputMatchesSource(source, input, index, inputContractVersion = "production-rule-inputs-v2") {
  if (!source || typeof source !== "object" || Array.isArray(source)
    || !input || typeof input !== "object" || Array.isArray(input)
    || input.input_index !== index
    || input.market !== ruleText(source.market)
    || input.code !== ruleText(source.code || source.symbol)) return false;
  const scalarFields = [
    "name", "blocker_codes", "legacy_signal", "legacy_recommendation_degree",
    "v2_rank", "v2_rank_universe_size", "event_candidate_scanned",
    "verified_positive_event_ids", "entry_price", "calendar_id", "calendar_version",
    "entry_trade_date", "forecast_end_trade_date",
  ];
  for (const field of scalarFields) {
    if (Object.hasOwn(source, field) !== Object.hasOwn(input, field)) return false;
    if (Object.hasOwn(source, field) && !normalizedFullJsonEqual(source[field], input[field])) return false;
  }
  const sourcePriority = source?.priority_components;
  const expectedPriority = sourcePriority && typeof sourcePriority === "object"
    && Object.hasOwn(sourcePriority, "data_quality")
    ? { data_quality: sourcePriority.data_quality }
    : null;
  if (Boolean(expectedPriority) !== Object.hasOwn(input, "priority_components")
    || (expectedPriority && !normalizedFullJsonEqual(input.priority_components, expectedPriority))) return false;
  const sourceRange = source?.estimated_10d_range;
  const rangeFields = inputContractVersion === "production-rule-inputs-v3"
    ? [
      "contract_version", "low_pct", "high_pct", "text",
      "horizon_trade_days", "method_id", "calibrated",
      "source_observations", "source_window_start_date", "source_window_end_date",
    ]
    : ["low_pct", "high_pct"];
  const expectedRange = sourceRange && typeof sourceRange === "object"
    ? Object.fromEntries(rangeFields
      .filter((field) => Object.hasOwn(sourceRange, field))
      .map((field) => [field, sourceRange[field]]))
    : null;
  return Boolean(expectedRange) === Object.hasOwn(input, "estimated_10d_range")
    && (!expectedRange || normalizedFullJsonEqual(input.estimated_10d_range, expectedRange));
}

function currentRuleInputContext(snapshot, decision) {
  const sources = snapshot?.global_decision?.evaluated_candidates;
  const inputs = snapshot?.production_rule_inputs;
  const inputRows = inputs?.rows;
  if (!Array.isArray(sources)
    || !inputs || typeof inputs !== "object" || Array.isArray(inputs)
    || !["production-rule-inputs-v2", "production-rule-inputs-v3"].includes(inputs.contract_version)
    || inputs.action_basis !== "dual_track_candidate_qualification_v4"
    || inputs.rule_model_id !== "ten-day-audited-rule-ensemble-v4"
    || typeof inputs.ledger_sha256 !== "string"
    || !/^[0-9a-f]{64}$/.test(inputs.ledger_sha256)
    || !Array.isArray(inputRows)
    || inputs.evaluated_candidate_count !== sources.length
    || inputRows.length !== sources.length
    || decision.source_rule_inputs_contract_version !== inputs.contract_version
    || decision.source_rule_inputs_sha256 !== inputs.ledger_sha256
    || decision.source_rule_input_count !== inputRows.length) return null;
  const byIdentity = new Map();
  for (let index = 0; index < sources.length; index += 1) {
    const source = sources[index];
    const input = inputRows[index];
    const market = ruleText(source?.market);
    const code = ruleText(source?.code || source?.symbol);
    const identity = candidateIdentity(market, code);
    if (!market || !code || !identity
      || !MARKET_ORDER.includes(market)
      || !frozenCurrentInputMatchesSource(source, input, index, inputs.contract_version)
      || typeof input.source_candidate_present !== "boolean"
      || (input.source_data_quality_score !== null
        && (!finiteRuleNumber(input.source_data_quality_score)
          || input.source_data_quality_score < 0
          || input.source_data_quality_score > 100))
      || (input.source_candidate_present === false && input.source_data_quality_score !== null)) return null;
    if (byIdentity.has(identity)) return null;
    byIdentity.set(identity, { source, input });
  }
  return { sources, inputRows, byIdentity, inputContractVersion: inputs.contract_version };
}

function expectedCurrentQualification(source, input, inputContractVersion = "production-rule-inputs-v2") {
  const market = ruleText(source?.market);
  const code = ruleText(source?.code || source?.symbol);
  const eventPolicy = PRODUCTION_EVENT_POLICY[market];
  const qualityPolicy = PRODUCTION_QUALITY_POLICY[market];
  if (!market || !code || !eventPolicy || !qualityPolicy) return null;
  const sourceBlockers = dedupeRuleStrings(source.blocker_codes);
  if (!sourceBlockers) return null;
  const ignoredModelBlockers = new Set(["TEN_DAY_MODEL_NOT_READY", "TEN_DAY_PREDICTION_MISSING"]);
  const sharedBlockers = sourceBlockers.filter((blocker) => !ignoredModelBlockers.has(blocker));
  const eventBlockers = [...sharedBlockers];
  const qualityEventWaivers = new Set(["EVENT_CANDIDATE_NOT_SCANNED", "VERIFIED_POSITIVE_EVENT_MISSING"]);
  const qualityBlockers = sharedBlockers.filter((blocker) => !qualityEventWaivers.has(blocker));
  const blockBoth = (blocker) => {
    eventBlockers.push(blocker);
    qualityBlockers.push(blocker);
  };
  if (input.source_candidate_present !== true) blockBoth("CANDIDATE_SNAPSHOT_MISSING");

  let legacy = source.legacy_recommendation_degree;
  const legacyValid = finiteRuleNumber(legacy);
  if (!legacyValid) {
    legacy = 0;
    blockBoth("LEGACY_RECOMMENDATION_INVALID");
  } else {
    legacy = Math.max(0, Math.min(100, legacy));
    if (legacy < eventPolicy.minimumLegacy) eventBlockers.push("LEGACY_RECOMMENDATION_BELOW_THRESHOLD");
    if (legacy < qualityPolicy.minimumLegacy) qualityBlockers.push("QUALITY_LEGACY_BELOW_THRESHOLD");
  }

  const rank = source.v2_rank;
  const universe = source.v2_rank_universe_size;
  const rankValid = finiteRuleNumber(rank)
    && finiteRuleNumber(universe)
    && universe >= 1
    && rank >= 1
    && rank <= universe;
  const rankFraction = rankValid ? rank / universe : null;
  const rankStrength = rankValid
    ? Math.max(0, Math.min(100, (universe - rank + 1) / universe * 100))
    : 0;
  if (!rankValid) blockBoth("V2_RANK_INVALID");
  else {
    if (rankFraction > 0.20) eventBlockers.push("V2_TOP_PERCENTILE_REQUIRED");
    if (rankFraction > 0.10) qualityBlockers.push("QUALITY_V2_TOP_DECILE_REQUIRED");
  }

  const priorityQuality = source?.priority_components?.data_quality;
  let dataQuality = finiteRuleNumber(input.source_data_quality_score)
    ? Math.max(0, Math.min(100, input.source_data_quality_score))
    : finiteRuleNumber(priorityQuality)
      ? Math.max(0, Math.min(100, priorityQuality / 20 * 100))
      : null;
  if (dataQuality === null) {
    dataQuality = 0;
    blockBoth("DATA_QUALITY_SCORE_INVALID");
  } else if (dataQuality < 95) qualityBlockers.push("QUALITY_DATA_QUALITY_BELOW_THRESHOLD");

  const eventScanned = source.event_candidate_scanned === true;
  const rawEventIds = Array.isArray(source.verified_positive_event_ids)
    ? source.verified_positive_event_ids.filter((value) => ruleText(value))
    : [];
  const eventIds = dedupeRuleStrings(rawEventIds) || [];
  if (!eventScanned) eventBlockers.push("EVENT_CANDIDATE_NOT_SCANNED");
  if (!eventIds.length) eventBlockers.push("VERIFIED_POSITIVE_EVENT_MISSING");
  const eventStrength = eventScanned && eventIds.length ? Math.min(100, 80 + 5 * eventIds.length) : 0;

  const low = source?.estimated_10d_range?.low_pct;
  const high = source?.estimated_10d_range?.high_pct;
  const rangeValid = finiteRuleNumber(low) && finiteRuleNumber(high) && low < 0 && high > 0;
  const canonicalRange = inputContractVersion === "production-rule-inputs-v3"
    ? canonicalHorizonRangeView(source?.estimated_10d_range)
    : null;
  const downside = rangeValid ? Math.abs(low) : null;
  const ratio = rangeValid ? high / downside : null;
  let riskRewardStrength = 0;
  if (!rangeValid) blockBoth("TEN_DAY_RANGE_INVALID");
  else {
    if (high < eventPolicy.minimumUpside) eventBlockers.push("TEN_DAY_UPSIDE_BELOW_THRESHOLD");
    if (downside > eventPolicy.maximumDownside) eventBlockers.push("TEN_DAY_DOWNSIDE_ABOVE_LIMIT");
    if (ratio < 1.20) eventBlockers.push("RISK_REWARD_BELOW_THRESHOLD");
    if (high < qualityPolicy.minimumUpside) qualityBlockers.push("QUALITY_TEN_DAY_UPSIDE_BELOW_THRESHOLD");
    if (downside > qualityPolicy.maximumDownside) qualityBlockers.push("QUALITY_TEN_DAY_DOWNSIDE_ABOVE_LIMIT");
    if (ratio < 1.50) qualityBlockers.push("QUALITY_RISK_REWARD_BELOW_THRESHOLD");
    riskRewardStrength = Math.max(0, Math.min(100, ratio / 2 * 100));
    if (inputContractVersion === "production-rule-inputs-v3" && !canonicalRange) {
      blockBoth("TEN_DAY_RANGE_PROVENANCE_INVALID");
    }
  }
  const components = {
    legacy_recommendation: roundRuleNumber(legacy * 0.30),
    v2_rank_strength: roundRuleNumber(rankStrength * 0.30),
    data_quality: roundRuleNumber(dataQuality * 0.15),
    verified_event_evidence: roundRuleNumber(eventStrength * 0.15),
    risk_reward_scenario: roundRuleNumber(riskRewardStrength * 0.10),
  };
  const score = roundRuleNumber(Math.max(0, Math.min(100, Object.values(components)
    .reduce((total, value) => total + value, 0))));
  if (score < 72) qualityBlockers.push("QUALITY_QUALIFICATION_SCORE_BELOW_THRESHOLD");
  const normalizedEventBlockers = dedupeRuleStrings(eventBlockers);
  const normalizedQualityBlockers = dedupeRuleStrings(qualityBlockers);
  const trackEvaluations = [
    { track: "event_catalyst", status: normalizedEventBlockers.length ? "FAIL" : "PASS", blocker_codes: normalizedEventBlockers },
    { track: "quality_technical", status: normalizedQualityBlockers.length ? "FAIL" : "PASS", blocker_codes: normalizedQualityBlockers },
  ];
  const qualificationTrack = trackEvaluations.find((evaluation) => evaluation.status === "PASS")?.track || null;
  return {
    market,
    code,
    name: ruleText(source.name),
    legacySignal: ruleText(source.legacy_signal),
    legacy: legacyValid ? roundRuleNumber(legacy) : null,
    rank: rankValid ? Math.trunc(rank) : null,
    universe: rankValid ? Math.trunc(universe) : null,
    rankFraction: rankValid ? roundRuleNumber(rankFraction, 4) : null,
    dataQuality: roundRuleNumber(dataQuality),
    eventScanned,
    eventIds,
    range: canonicalRange,
    low: rangeValid ? roundRuleNumber(low) : null,
    high: rangeValid ? roundRuleNumber(high) : null,
    downside: rangeValid ? roundRuleNumber(downside) : null,
    ratio: rangeValid ? roundRuleNumber(ratio) : null,
    components,
    score,
    trackEvaluations,
    qualificationTrack,
    blockerCodes: qualificationTrack ? [] : dedupeRuleStrings([...normalizedEventBlockers, ...normalizedQualityBlockers]),
  };
}

function sameNullableRuleNumber(actual, expected, tolerance = 0.011) {
  return expected === null ? actual === null : sameRuleNumber(actual, expected, tolerance);
}

function validCurrentEvaluatedRow(row, decision, context) {
  if (!row || typeof row !== "object" || Array.isArray(row)) return false;
  const market = ruleText(row.market);
  const code = ruleText(row.code || row.symbol);
  const identity = candidateIdentity(market, code);
  const sourceContext = identity ? context?.byIdentity.get(identity) : null;
  const expected = sourceContext
    ? expectedCurrentQualification(sourceContext.source, sourceContext.input, context?.inputContractVersion)
    : null;
  if (!expected
    || row.status !== (expected.qualificationTrack ? "QUALIFIED" : "REJECTED")
    || row.market !== expected.market
    || row.code !== expected.code
    || row.name !== expected.name
    || row.rule_model_id !== decision.rule_model_id
    || row.score_kind !== decision.score_kind
    || row.probability !== null
    || row.probability_status !== "NOT_APPLICABLE"
    || row.calibrated !== false
    || row.expected_net_utility !== null
    || row.legacy_signal !== expected.legacySignal
    || !sameNullableRuleNumber(row.legacy_recommendation_degree, expected.legacy)
    || row.v2_rank !== expected.rank
    || row.v2_rank_universe_size !== expected.universe
    || !sameNullableRuleNumber(row.v2_rank_fraction, expected.rankFraction, 0.00011)
    || !sameRuleNumber(row.data_quality_score, expected.dataQuality)
    || row.event_candidate_scanned !== expected.eventScanned
    || !normalizedFullJsonEqual(row.verified_positive_event_ids, expected.eventIds)
    || !sameRuleNumber(row.qualification_score, expected.score)
    || !sameRuleScoreComponents(row.score_components, expected.components)
    || !validCurrentTrackEvaluations(row.track_evaluations)
    || !normalizedFullJsonEqual(row.track_evaluations, expected.trackEvaluations)
    || row.qualification_track !== expected.qualificationTrack
    || !normalizedFullJsonEqual(row.blocker_codes, expected.blockerCodes)
    || row?.estimated_10d_range?.horizon_trade_days !== 10
    || (context?.inputContractVersion === "production-rule-inputs-v3"
      && expected.range && !normalizedFullJsonEqual(row.estimated_10d_range, expected.range))
    || !sameNullableRuleNumber(row?.estimated_10d_range?.low_pct, expected.low)
    || !sameNullableRuleNumber(row?.estimated_10d_range?.high_pct, expected.high)
    || !sameNullableRuleNumber(row?.risk_reward?.upside_pct, expected.high)
    || !sameNullableRuleNumber(row?.risk_reward?.downside_pct, expected.downside)
    || !sameNullableRuleNumber(row?.risk_reward?.ratio, expected.ratio)) return false;
  if (!expected.qualificationTrack) {
    return row.qualification_id === undefined && row.candidate_snapshot === undefined;
  }
  const eventBlockers = expected.trackEvaluations[0].blocker_codes;
  const boundedPositiveEventBlockers = new Set(["EVENT_CANDIDATE_NOT_SCANNED", "VERIFIED_POSITIVE_EVENT_MISSING"]);
  const qualityWaivesOnlyPositiveEnrichment = expected.qualificationTrack !== "quality_technical"
    || (eventBlockers.length > 0 && eventBlockers.every((blocker) => boundedPositiveEventBlockers.has(blocker)));
  const candidateSnapshot = row.candidate_snapshot;
  const candidateCode = normalizeCandidateCode(market, candidateSnapshot?.code || candidateSnapshot?.symbol);
  const evaluatedCode = normalizeCandidateCode(market, code);
  const planValid = context?.inputContractVersion !== "production-rule-inputs-v3"
    || validateTenDayTradePlan(row.ten_day_trade_plan, row, candidateSnapshot).valid;
  return planValid
    && qualityWaivesOnlyPositiveEnrichment
    && typeof row.qualification_id === "string"
    && /^qual_[0-9a-f]{24}$/.test(row.qualification_id)
    && normalizedFullJsonEqual(candidateSnapshot, sourceContext.input.candidate_snapshot)
    && candidateCode !== null
    && candidateCode === evaluatedCode;
}

function validCurrentQualifiedRow(row, decision, snapshot, context = null) {
  const isCurrent = decision?.action_basis === "dual_track_candidate_qualification_v4"
    && decision?.rule_model_id === "ten-day-audited-rule-ensemble-v4";
  if (!isCurrent) return true;
  const ruleContext = context || currentRuleInputContext(snapshot, decision);
  return Boolean(ruleContext && row?.status === "QUALIFIED" && validCurrentEvaluatedRow(row, decision, ruleContext));
}

function deterministicCurrentOrder(context, evaluated) {
  if (!context || !Array.isArray(context.sources) || !Array.isArray(context.inputRows)
    || !Array.isArray(evaluated) || evaluated.length !== context.sources.length) return null;
  const seen = new Set();
  const rows = evaluated.map((row) => {
    const identity = candidateIdentity(row?.market, row?.code || row?.symbol);
    const sourceContext = identity ? context.byIdentity.get(identity) : null;
    const expected = sourceContext
      ? expectedCurrentQualification(
        sourceContext.source,
        sourceContext.input,
        context.inputContractVersion,
      )
      : null;
    if (!identity || seen.has(identity) || !expected
      || row.market !== expected.market || row.code !== expected.code
      || !sameRuleNumber(row.qualification_score, expected.score)) return null;
    seen.add(identity);
    return {
      market: row.market,
      code: row.code,
      qualificationScore: row.qualification_score,
    };
  });
  if (rows.some((row) => !row) || seen.size !== context.byIdentity.size) return null;
  return rows.sort((left, right) => {
    if (left.qualificationScore !== right.qualificationScore) {
      return right.qualificationScore - left.qualificationScore;
    }
    if (left.market !== right.market) return left.market < right.market ? -1 : 1;
    if (left.code !== right.code) return left.code < right.code ? -1 : 1;
    return 0;
  });
}

function currentQualifiedTruthRows(snapshot, decision) {
  const evaluated = decision?.evaluated_candidates;
  const mirrors = decision?.qualified_candidates;
  const context = currentRuleInputContext(snapshot, decision);
  // The server sorts the already rounded, published qualification score.  Use
  // that audited value here as well; recomputing a midpoint with Math.round()
  // can differ from Python round() by 0.01 and invert adjacent equal-score rows.
  const expectedOrder = deterministicCurrentOrder(context, evaluated);
  if (!context
    || !expectedOrder
    || !Array.isArray(evaluated)
    || !Array.isArray(mirrors)
    || !Array.isArray(decision.blocker_codes)
    || decision.blocker_codes.length > 0
    || decision.evaluated_candidate_count !== context.sources.length
    || decision.evaluated_candidate_count !== evaluated.length
    || !evaluated.every((row, index) => (
      validCurrentEvaluatedRow(row, decision, context)
      && row.market === expectedOrder[index]?.market
      && row.code === expectedOrder[index]?.code
    ))) return null;
  const truthRows = evaluated.filter((row) => row.status === "QUALIFIED");
  const identities = truthRows.map((row) => row.qualification_id);
  if (!truthRows.length
    || new Set(identities).size !== identities.length
    || decision.qualified_candidate_count !== truthRows.length
    || decision.rejected_candidate_count !== evaluated.length - truthRows.length
    || mirrors.length !== truthRows.length
    || !mirrors.every((row, index) => normalizedFullJsonEqual(row, truthRows[index]))
    || !normalizedFullJsonEqual(decision.primary, truthRows[0])
    || !normalizedFullJsonEqual(decision.primary, mirrors[0])) return null;
  return truthRows;
}

function compactQualifiedTruthRows(snapshot, decision) {
  if (snapshot?.contract_version !== "ui-bootstrap-v1") return null;
  const mirrors = decision?.qualified_candidates;
  if (!Array.isArray(mirrors) || !mirrors.length || !decision?.primary) return null;
  const identities = new Set();
  for (const row of mirrors) {
    const identity = candidateIdentity(row?.market, row?.code || row?.symbol);
    const embeddedIdentity = candidateIdentity(
      row?.market,
      row?.candidate_snapshot?.code || row?.candidate_snapshot?.symbol,
    );
    if (!identity || identities.has(identity) || embeddedIdentity !== identity
      || row?.status !== "QUALIFIED"
      || typeof row?.qualification_id !== "string"
      || !/^qual_[a-f0-9]{24}$/.test(row.qualification_id)
      || !finiteRuleNumber(row?.qualification_score)) return null;
    identities.add(identity);
  }
  const primaryIdentity = candidateIdentity(decision.primary.market, decision.primary.code || decision.primary.symbol);
  const firstIdentity = candidateIdentity(mirrors[0].market, mirrors[0].code || mirrors[0].symbol);
  if (!primaryIdentity || primaryIdentity !== firstIdentity
    || decision.primary.qualification_id !== mirrors[0].qualification_id
    || !sameRuleNumber(decision.primary.qualification_score, mirrors[0].qualification_score)
    || Number(decision.qualified_candidate_count) !== mirrors.length) return null;
  return mirrors;
}

function productionQualifiedRows(snapshot = state.snapshot, market = null) {
  const decision = snapshot?.production_decision;
  if (!productionContractValid(decision, snapshot?.model_version) || decision.action !== "QUALIFIED_PICK") return [];
  const strictCurrent = decision.action_basis === "dual_track_candidate_qualification_v4"
    && decision.rule_model_id === "ten-day-audited-rule-ensemble-v4";
  const compactTruthRows = strictCurrent ? compactQualifiedTruthRows(snapshot, decision) : null;
  const currentTruthRows = strictCurrent ? (compactTruthRows || currentQualifiedTruthRows(snapshot, decision)) : null;
  if (strictCurrent && !currentTruthRows) return [];
  const rawRows = strictCurrent
    ? currentTruthRows
    : [decision.primary, ...(Array.isArray(decision.qualified_candidates) ? decision.qualified_candidates : [])];
  const rows = [];
  const seen = new Set();
  for (const primary of rawRows) {
    if (!primary || typeof primary !== "object" || primary.status !== "QUALIFIED") {
      if (strictCurrent) return [];
      continue;
    }
    const rowMarket = String(primary.market || "");
    const rowCode = normalizeCandidateCode(rowMarket, primary.code || primary.symbol);
    const embedded = primary.candidate_snapshot;
    const embeddedCode = normalizeCandidateCode(rowMarket, embedded?.code || embedded?.symbol);
    const score = primary.qualification_score;
    const valid = MARKET_ORDER.includes(rowMarket)
      && rowCode
      && typeof score === "number"
      && Number.isFinite(score)
      && primary.rule_model_id === decision.rule_model_id
      && primary.score_kind === decision.score_kind
      && (primary.probability === undefined || primary.probability === null)
      && (primary.calibrated === undefined || primary.calibrated === false)
      && (compactTruthRows ? true : validCurrentQualifiedRow(primary, decision, snapshot))
      && (!embedded || (typeof embedded === "object" && embeddedCode === rowCode));
    if (!valid) {
      if (strictCurrent) return [];
      continue;
    }
    const key = `${rowMarket}:${rowCode}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const sourceCandidate = embedded || primary;
    rows.push({
      market: rowMarket,
      code: rowCode,
      primary,
      candidate: {
        ...sourceCandidate,
        production_qualification: {
          qualification_id: primary.qualification_id || null,
          qualification_score: score,
          rule_model_id: primary.rule_model_id || decision.rule_model_id || null,
          score_kind: primary.score_kind || decision.score_kind,
          qualification_track: primary.qualification_track || null,
        },
      },
    });
  }
  const publishedCount = Number(decision.qualified_candidate_count);
  if (!Number.isInteger(publishedCount) || publishedCount <= 0 || publishedCount !== rows.length) return [];
  return market ? rows.filter((row) => row.market === market) : rows;
}

function candidatesFor(snapshot, market) {
  const lazyRows = state.candidates.filter((candidate) => candidate.market === market);
  if (state.candidatePayload) return lazyRows;
  const decision = marketDecision(snapshot, market);
  const researchCandidate = researchCandidateSnapshot(snapshot, market);
  const qualifiedRows = productionQualifiedRows(snapshot, market);
  const rows = [
    ...qualifiedRows.map((row) => row.candidate),
    decision.primary,
    decision.blocked_candidate,
    ...(decision.watchlist || []),
    researchCandidate,
  ].filter(Boolean);
  const result = [];
  const byKey = new Map();
  for (const row of rows) {
    const key = candidateId(row, market);
    if (!byKey.has(key)) {
      byKey.set(key, result.length);
      result.push(row);
      continue;
    }
    const index = byKey.get(key);
    const existing = result[index];
    if (existing?.production_qualification) result[index] = { ...row, ...existing };
  }
  return result;
}

function explicitCandidateDecisionRole(candidate, market) {
  if (candidate?.role_contract_version !== "candidate-role-v1" || !isRecord(candidate.decision_roles)) return null;
  const roles = candidate.decision_roles;
  if (!["PRIMARY", "QUALIFIED", "NONE"].includes(roles.production)
    || !["PRIMARY", "BLOCKED", "WATCHLIST", "NONE"].includes(roles.legacy)
    || !["PRIORITY", "NONE"].includes(roles.research)) return null;
  const key = candidateId(candidate, market);
  const productionRows = productionQualifiedRows(state.snapshot, market);
  const publishedQualified = productionRows.some((row) => candidateId(row.candidate, market) === key);
  const primary = state.snapshot?.production_decision?.primary;
  const publishedPrimary = publishedQualified
    && candidateId(primary?.candidate_snapshot || primary, market) === key;
  if ((roles.production === "PRIMARY" && publishedPrimary)
    || (roles.production === "QUALIFIED" && publishedQualified && !publishedPrimary)) {
    const current = currentProductionContractValid(state.snapshot) && snapshotUseTruth().currentDecisionAllowed;
    if (roles.production === "PRIMARY") return current ? "production_primary" : "historical_production_primary";
    return current ? "production_qualified" : "historical_production_qualified";
  }
  if (roles.research === "PRIORITY") return "research_priority";
  return ({
    PRIMARY: "legacy_market_primary",
    BLOCKED: "legacy_blocked",
    WATCHLIST: "legacy_watchlist",
    NONE: "legacy_watchlist",
  })[roles.legacy];
}

function isProductionCandidateRole(role) {
  return [
    "production_primary", "production_qualified",
    "historical_production_primary", "historical_production_qualified",
    "qualified", "historical_qualified",
  ].includes(role);
}

function isHistoricalProductionCandidateRole(role) {
  return ["historical_production_primary", "historical_production_qualified", "historical_qualified"].includes(role);
}

function isLegacyPrimaryRole(role) {
  return ["legacy_market_primary", "primary"].includes(role);
}

function isLegacyBlockedRole(role) {
  return ["legacy_blocked", "blocked"].includes(role);
}

function candidateDecisionRole(candidate, market) {
  const explicitRole = explicitCandidateDecisionRole(candidate, market);
  if (explicitRole) return explicitRole;
  const key = candidateId(candidate, market);
  const publishedQualified = productionQualifiedRows(state.snapshot, market)
    .some((row) => candidateId(row.candidate, market) === key);
  if (publishedQualified || candidate?.decision_role === "qualified") {
    return currentProductionContractValid(state.snapshot) && snapshotUseTruth().currentDecisionAllowed
      ? "qualified"
      : "historical_qualified";
  }
  if (["primary", "blocked", "research", "watchlist"].includes(candidate?.decision_role)) {
    return candidate.decision_role;
  }
  const decision = marketDecision(state.snapshot, market);
  if (decision.primary && candidateId(decision.primary, market) === key) return "primary";
  if (decision.blocked_candidate && candidateId(decision.blocked_candidate, market) === key) return "blocked";
  const researchCandidate = researchCandidateSnapshot(state.snapshot, market);
  if (researchCandidate && candidateId(researchCandidate, market) === key) return "research";
  return "watchlist";
}

function decisionRoleLabel(role) {
  return ({
    production_primary: "规则主候选",
    production_qualified: "规则合格",
    historical_production_primary: "历史规则主候选·不可执行",
    historical_production_qualified: "历史规则合格·不可执行",
    qualified: "规则合格",
    historical_qualified: "历史合格·不可执行",
    legacy_market_primary: "Legacy首选",
    primary: "Legacy首选",
    legacy_blocked: "Legacy门槛未过",
    blocked: "门槛未过",
    research_priority: "研究优先",
    research: "研究优先",
    legacy_watchlist: "Legacy观察",
    watchlist: "观察候选",
  })[role] || "观察候选";
}

function qualificationTrackLabel(track) {
  return ({
    event_catalyst: "事件催化合格",
    quality_technical: "质量趋势合格",
  })[track] || "规则合格";
}

function productionQualificationForCandidate(candidate, market, snapshot = state.snapshot) {
  if (candidate?.production_qualification && candidateIdentity(market, candidate.code || candidate.symbol)) {
    return candidate.production_qualification;
  }
  const key = candidateId(candidate, market);
  return productionQualifiedRows(snapshot, market)
    .find((row) => candidateId(row.candidate, market) === key)?.primary || null;
}

function allCandidates() {
  return MARKET_ORDER.flatMap((market) => candidatesFor(state.snapshot, market).map((candidate, index) => ({
    candidate,
    market,
    legacyRank: Number.isFinite(Number(candidate.legacy_rank)) ? Number(candidate.legacy_rank) : candidate.legacy_complete === false ? null : index + 1,
    decisionRole: candidateDecisionRole(candidate, market),
  })));
}

function productionDecisionTruth(snapshot = state.snapshot, status = state.status) {
  const serverDecision = snapshot?.production_decision;
  const serverAction = String(serverDecision?.action || "");
  const serverPrimary = serverDecision?.primary;
  const primaryMarket = String(serverPrimary?.market || "");
  const primaryCode = normalizeCandidateCode(primaryMarket, serverPrimary?.code || serverPrimary?.symbol);
  const qualifiedRows = productionQualifiedRows(snapshot);
  const qualifiedPrimary = qualifiedRows.find((row) => row.market === primaryMarket && row.code === primaryCode) || null;
  const qualificationScore = serverPrimary?.qualification_score;
  const finiteScore = typeof qualificationScore === "number" && Number.isFinite(qualificationScore);
  const baseContractValid = productionContractValid(serverDecision, snapshot?.model_version);
  const primaryDoesNotClaimProbability = Boolean(
    serverPrimary
    && (serverPrimary.probability === undefined || serverPrimary.probability === null)
    && (serverPrimary.calibrated === undefined || serverPrimary.calibrated === false)
  );
  const primaryValid = Boolean(
    serverPrimary
    && MARKET_ORDER.includes(primaryMarket)
    && primaryCode
    && finiteScore
    && qualifiedPrimary
    && primaryDoesNotClaimProbability
  );
  const publishedCount = Number(serverDecision?.qualified_candidate_count);
  const countValid = serverAction !== "QUALIFIED_PICK" || (
    Number.isInteger(publishedCount)
    && publishedCount > 0
    && publishedCount === qualifiedRows.length
  );
  const blockerCodes = Array.isArray(serverDecision?.blocker_codes) ? [...serverDecision.blocker_codes] : [];
  if (!serverDecision) blockerCodes.push("PRODUCTION_DECISION_MISSING");
  if (serverDecision && !baseContractValid) blockerCodes.push("PRODUCTION_DECISION_CONTRACT_INVALID");
  if (serverAction === "QUALIFIED_PICK" && !primaryValid) blockerCodes.push("PRODUCTION_PRIMARY_INVALID");
  if (serverAction === "QUALIFIED_PICK" && !countValid) blockerCodes.push("PRODUCTION_QUALIFIED_COUNT_MISMATCH");
  const publishedQualified = baseContractValid && serverAction === "QUALIFIED_PICK" && primaryValid && countValid;
  const candidate = publishedQualified ? qualifiedPrimary.candidate : null;
  const snapshotUse = snapshotUseTruth(snapshot, status);
  const currentContract = currentProductionContractValid(snapshot);
  if (baseContractValid && !currentContract) blockerCodes.push("PRODUCTION_MODEL_HISTORICAL");
  const currentQualified = publishedQualified && currentContract && snapshotUse.currentDecisionAllowed;
  const currentAction = !currentContract
    ? "HISTORICAL_ONLY"
    : snapshotUse.currentDecisionAllowed
    ? (currentQualified ? "QUALIFIED_PICK" : "NO_QUALIFIED_PICK")
    : "HISTORICAL_ONLY";
  const publishedQualifiedRows = publishedQualified ? qualifiedRows : [];
  const publishedQualifiedCandidate = publishedQualified
    ? { market: primaryMarket, candidate, primary: serverPrimary }
    : null;
  return {
    action: currentAction,
    currentAction,
    publishedAction: serverAction || "NO_QUALIFIED_PICK",
    serverAction,
    actionBasis: serverDecision?.action_basis || "production_rule_gate_v1",
    scoreKind: "RULE_QUALIFICATION_SCORE",
    probability: null,
    calibrated: false,
    qualificationScore: publishedQualified ? qualificationScore : null,
    qualifiedCount: currentQualified ? qualifiedRows.length : 0,
    qualifiedRows: currentQualified ? qualifiedRows : [],
    currentQualifiedCount: currentQualified ? qualifiedRows.length : 0,
    currentQualifiedRows: currentQualified ? qualifiedRows : [],
    historicalQualifiedCount: publishedQualifiedRows.length,
    publishedQualifiedRows,
    blockerCodes: [...new Set([...blockerCodes, ...snapshotUse.blockerCodes])],
    primary: currentQualified ? serverPrimary : null,
    publishedPrimary: publishedQualified ? serverPrimary : null,
    qualified: currentQualified ? publishedQualifiedCandidate : null,
    historicalQualified: publishedQualifiedCandidate,
    snapshotUse,
    serverDecision,
    currentContract,
  };
}

function publishedEventItems() {
  const lazy = state.eventsPayload?.events;
  const full = state.snapshot?.events;
  const evidence = decisionEvidenceItems();
  const lazyItems = Array.isArray(lazy) ? lazy : Array.isArray(lazy?.items) ? lazy.items : [];
  const fullItems = Array.isArray(full) ? full : Array.isArray(full?.items) ? full.items : [];
  const result = new Map();
  for (const item of evidence) {
    if (!item?.event_id) continue;
    result.set(item.event_id, { ...item, decision_bound: true });
  }
  for (const item of [...lazyItems, ...fullItems]) {
    if (!item?.event_id) continue;
    const bound = result.get(item.event_id);
    result.set(item.event_id, bound
      ? { ...item, ...bound, decision_bound: true }
      : { ...item, decision_bound: item.decision_bound === true });
  }
  return [...result.values()];
}

function decisionEvidenceItems(snapshot = state.snapshot) {
  const evidence = snapshot?.decision_evidence?.items;
  return Array.isArray(evidence) ? evidence : [];
}

function automaticExternalEventsFrom(items, snapshot = state.snapshot) {
  if (!Array.isArray(items)) return [];
  const generated = Date.parse(snapshot?.generated_at || "");
  const forecastEndDay = String(snapshot?.forecast_end_date || "").slice(0, 10);
  const windowStart = generated - 45 * 24 * 60 * 60 * 1000;
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

// Decision, health and candidate ordering use the bounded bootstrap evidence
// only. Visiting the Events tab must never change a published decision.
function automaticExternalEvents(snapshot = state.snapshot) {
  return automaticExternalEventsFrom(decisionEvidenceItems(snapshot), snapshot);
}

function automaticEventFeed(snapshot = state.snapshot) {
  return automaticExternalEventsFrom(publishedEventItems(), snapshot);
}

function publishedEventStats(snapshot = state.snapshot) {
  const stats = snapshot?.event_stats;
  if (stats && typeof stats === "object" && !Array.isArray(stats)) {
    return {
      total: num(stats.total, 0),
      modelSignals: num(stats.model_signals, 0),
      automaticExternal: num(stats.automatic_external, 0),
      decisionEligible: num(stats.decision_eligible, 0),
      decisionBound: num(stats.decision_bound, 0),
      pipelineStatus: stats.pipeline_status || null,
      pipelineScanned: stats.pipeline_scanned === true,
    };
  }
  const items = decisionEvidenceItems(snapshot);
  return {
    total: items.length,
    modelSignals: items.filter((event) => event.event_type === "model_signal").length,
    automaticExternal: automaticExternalEventsFrom(items, snapshot).length,
    decisionEligible: items.filter((event) => event.decision_eligible === true).length,
    decisionBound: items.length,
    pipelineStatus: snapshot?.global_decision?.event_pipeline_status || null,
    pipelineScanned: snapshot?.global_decision?.event_pipeline_scanned === true,
  };
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
  const ready = calibrated && costsReady && tailReady && participates;
  const shadowReady = status === "SHADOW_READY" && model.participates_in_decision !== true;
  const shadowRejected = status === "SHADOW_REJECTED" && model.participates_in_decision !== true;
  return { model, status, calibrated, costsReady, tailReady, participates, ready, shadowReady, shadowRejected };
}

function firstFiniteModelMetric(source, keys) {
  for (const key of keys) {
    const value = source?.[key];
    if (value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))) return Number(value);
  }
  return null;
}

function tenDayModelValidation(model) {
  const published = model?.validation || {};
  const validation = published.overall && typeof published.overall === "object" ? published.overall : published;
  return {
    heldOutDays: firstFiniteModelMetric(validation, ["independent_test_date_count", "independent_test_dates", "test_date_count", "held_out_days"]),
    brier: firstFiniteModelMetric(validation, ["brier_score"]),
    brierSkill: firstFiniteModelMetric(validation, ["brier_skill"]),
    ece: firstFiniteModelMetric(validation, ["ece_10bin"]),
    auc: firstFiniteModelMetric(validation, ["auc"]),
    topReturn: firstFiniteModelMetric(validation, ["top_decile_mean_net_return"]),
    topExcess: firstFiniteModelMetric(validation, ["top_decile_excess_vs_mean"]),
  };
}

function tenDayModelReasonCodes(model) {
  const direct = Array.isArray(model?.reason_codes) ? model.reason_codes : [];
  const validation = Array.isArray(model?.validation?.reason_codes) ? model.validation.reason_codes : [];
  return [...new Set([...direct, ...validation].map((code) => String(code)).filter(Boolean))];
}

function tenDayModelPresentation(modelState = tenDayModelState()) {
  const { model, status } = modelState;
  const reasonCodes = tenDayModelReasonCodes(model);
  if (modelState.ready) {
    return {
      title: "10 日概率模型已参与严格门禁",
      label: "PRODUCTION",
      tone: "positive",
      icon: "ph-check-circle",
      detail: "只有正式已校准概率才能参与跨市场可执行决策。",
      reasonCodes,
    };
  }
  if (status === "SHADOW_READY") {
    return {
      title: "10 日概率模型影子运行中",
      label: "SHADOW_READY",
      tone: "primary",
      icon: "ph-flask",
      detail: "影子 P10 只用于观察概率排序，不参与正式决策。",
      reasonCodes,
    };
  }
  if (status === "SHADOW_REJECTED") {
    return {
      title: "10 日概率模型留出检验未通过",
      label: "SHADOW_REJECTED",
      tone: "negative",
      icon: "ph-shield-warning",
      detail: "本轮影子 P10 仍保留用于审计，但不参与跨市场排序或正式决策；研究优先项回退到规则分。",
      reasonCodes,
    };
  }
  return {
    title: "10 日概率模型数据积累中",
    label: status || "UNAVAILABLE",
    tone: "warning",
    icon: "ph-hourglass",
    detail: "样本、留出校准或风险证据尚未达标；当前规则分不是上涨概率。",
    reasonCodes,
  };
}

function candidateShadowModel(candidate, market, snapshot = state.snapshot) {
  if (candidate?.shadow_model && typeof candidate.shadow_model === "object") return candidate.shadow_model;
  const code = String(candidate?.code || candidate?.symbol || "").toLowerCase();
  const evaluated = Array.isArray(snapshot?.global_decision?.evaluated_candidates)
    ? snapshot.global_decision.evaluated_candidates
    : [];
  const row = evaluated.find((item) => String(item?.market || "") === String(market || "")
    && String(item?.code || item?.symbol || "").toLowerCase() === code);
  return row?.shadow_model && typeof row.shadow_model === "object" ? row.shadow_model : null;
}

function shadowProbability(shadow_model) {
  if (!shadow_model || typeof shadow_model !== "object") return null;
  const probability = shadow_model.probability;
  return typeof probability === "number" && Number.isFinite(probability) && probability >= 0 && probability <= 1
    ? probability
    : null;
}

function shadowP10Label(shadow_model) {
  const probability = shadowProbability(shadow_model);
  return probability === null ? "--" : ratioPct(probability, 1);
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
      const fallbackRank = candidatesFor(snapshot, market).indexOf(candidate) + 1;
      const legacyRank = Number.isFinite(Number(candidate.legacy_rank))
        ? Number(candidate.legacy_rank)
        : candidate.legacy_complete === false ? null : fallbackRank;
      return { market, candidate, legacyRank, coverage: marketCoverageState(market, snapshot), source: "server" };
    }
    // The server selection is authoritative.  If an old/broken snapshot does
    // not publish the matching candidate_snapshot, show no priority instead of
    // quietly replacing it with a different Legacy watchlist stock.
    return null;
  }
  // New global-contract snapshots are server-authoritative even when no
  // research candidate is published.  In particular, an all-market BLOCKED
  // state must render as "no candidate", never as a browser-side fallback.
  if (snapshot?.global_decision?.contract_version === "global-10d-v1") return null;
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
  const snapshotUse = snapshotUseTruth(snapshot, state.status);
  const fresh = snapshotUse.currentDecisionAllowed;
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
  if (!fresh) blockerCodes.push(...snapshotUse.blockerCodes);
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
    snapshotUse,
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

function legacyRankLabel(row, includeUniverse = false) {
  const rank = Number(row?.legacyRank);
  if (!Number.isFinite(rank) || rank <= 0 || row?.candidate?.legacy_complete === false) return "未深评";
  if (!includeUniverse) return `#${rank}`;
  const deepSize = num(marketSection(state.snapshot, row.market)?.stats?.deep_scored_size, 0);
  return deepSize > 0 ? `#${rank}/${deepSize}` : `#${rank}`;
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

class HttpError extends Error {
  constructor(status, url, message = "") {
    super(message || `请求失败 ${status}`);
    this.name = "HttpError";
    this.status = status;
    this.url = url;
  }
}

function requestSignal(timeoutMs = REQUEST_TIMEOUT_MS, signal = null) {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    const timeout = AbortSignal.timeout(timeoutMs);
    if (!signal) return { signal: timeout, cleanup: () => {} };
    if (typeof AbortSignal.any === "function") {
      return { signal: AbortSignal.any([signal, timeout]), cleanup: () => {} };
    }
  }
  if (typeof AbortController === "undefined") return { signal, cleanup: () => {} };
  const controller = new AbortController();
  const abortReason = (message, name) => typeof DOMException === "function"
    ? new DOMException(message, name)
    : Object.assign(new Error(message), { name });
  const abortFromParent = () => controller.abort(signal?.reason || abortReason("请求已取消", "AbortError"));
  if (signal?.aborted) abortFromParent();
  else signal?.addEventListener?.("abort", abortFromParent, { once: true });
  const timer = setTimeout(() => controller.abort(abortReason("请求超时", "TimeoutError")), timeoutMs);
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      signal?.removeEventListener?.("abort", abortFromParent);
    },
  };
}

function requestAbortError(message = "请求已取消") {
  return typeof DOMException === "function"
    ? new DOMException(message, "AbortError")
    : Object.assign(new Error(message), { name: "AbortError" });
}

async function getJson(url, { timeoutMs = REQUEST_TIMEOUT_MS, signal = null, ...options } = {}) {
  const bounded = requestSignal(timeoutMs, signal);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      ...options,
      signal: bounded.signal,
      headers: { Accept: "application/json", ...(options.headers || {}) },
    });
    let payload;
    try { payload = await response.json(); } catch { payload = {}; }
    if (!response.ok) throw new HttpError(response.status, url, payload.message || payload.error);
    return payload;
  } catch (error) {
    if (error?.name === "TimeoutError") throw new Error("请求超时，请稍后重试");
    throw error;
  } finally {
    bounded.cleanup();
  }
}

async function getHistoryPayload({ signal = null, page = 1 } = {}) {
  try {
    const payload = await getJson(resourceListUrl("history", page), { signal });
    state.historyError = "";
    return payload;
  } catch (error) {
    state.historyError = error.message || "历史清单读取失败";
    throw error;
  }
}

function validSnapshotIdentity(value) {
  const source = value?.source_snapshot;
  return Boolean(
    value
    && typeof value.snapshot_key === "string"
    && value.snapshot_key.length > 0
    && typeof value.generated_at === "string"
    && Number.isFinite(Date.parse(value.generated_at))
    && source
    && typeof source === "object"
    && !Array.isArray(source)
    && typeof source.sha256 === "string"
    && /^[a-f0-9]{64}$/i.test(source.sha256)
    && Number.isInteger(source.byte_size)
    && source.byte_size > 0
  );
}

function payloadIdentityMatchesSnapshot(payload, snapshot = state.snapshot) {
  if (!validSnapshotIdentity(payload) || !validSnapshotIdentity(snapshot)) return false;
  if (payload.snapshot_key !== snapshot.snapshot_key || payload.generated_at !== snapshot.generated_at) return false;
  const payloadSource = payload.source_snapshot;
  const snapshotSource = snapshot.source_snapshot;
  return payloadSource.sha256 === snapshotSource.sha256
    && payloadSource.byte_size === snapshotSource.byte_size;
}

function snapshotUseIdentityMatchesSnapshot(snapshotUse, snapshot = state.snapshot) {
  if (!snapshotUse || !validSnapshotIdentity(snapshot)) return false;
  return snapshotUse.contract_version === "snapshot-use-v1"
    && snapshotUse.snapshot_key === snapshot.snapshot_key
    && snapshotUse.source_snapshot_sha256 === snapshot.source_snapshot?.sha256
    && snapshotUse.source_snapshot_byte_size === snapshot.source_snapshot?.byte_size
    && Number.isFinite(Date.parse(snapshotUse.evaluated_at || ""));
}

function mergeSnapshotDecisionState(payload, { mergeStatusFields = false, strict = false } = {}) {
  const incomingStatus = payload?.status && typeof payload.status === "object"
    ? payload.status
    : payload;
  const incomingUse = payload?.snapshot_use || incomingStatus?.snapshot_use;
  const incomingDecisions = payload?.effective_decisions || incomingStatus?.effective_decisions;
  if (!incomingUse || typeof incomingUse !== "object") {
    if (strict) throw new Error("按需响应缺少 snapshot_use 合同");
    if (mergeStatusFields && incomingStatus && typeof incomingStatus === "object") {
      state.status = { ...(state.status || {}), ...incomingStatus };
    }
    return true;
  }
  if (!snapshotUseIdentityMatchesSnapshot(incomingUse)) {
    if (strict) throw new Error("snapshot_use 与当前快照身份不一致");
    return false;
  }
  const incomingEvaluatedAt = Date.parse(incomingUse.evaluated_at || "");
  if (!Number.isFinite(incomingEvaluatedAt)) {
    if (strict) throw new Error("snapshot_use evaluated_at 无效");
    return false;
  }
  const currentUse = state.status?.snapshot_use;
  const sameCurrentIdentity = snapshotUseIdentityMatchesSnapshot(currentUse);
  const currentEvaluatedAt = Date.parse(currentUse?.evaluated_at || "");
  if (sameCurrentIdentity && Number.isFinite(currentEvaluatedAt) && incomingEvaluatedAt <= currentEvaluatedAt) {
    return false;
  }
  const nextStatus = mergeStatusFields
    ? { ...(state.status || {}), ...incomingStatus }
    : { ...(state.status || {}) };
  nextStatus.snapshot_use = incomingUse;
  if (incomingDecisions && typeof incomingDecisions === "object" && !Array.isArray(incomingDecisions)) {
    nextStatus.effective_decisions = incomingDecisions;
  }
  nextStatus.freshness_state = incomingUse.freshness_state || nextStatus.freshness_state;
  state.status = nextStatus;
  return true;
}

function resetLazyTabData() {
  Object.values(requestControllers).forEach((controller) => controller?.abort?.());
  requestControllers.tab = null;
  requestControllers.detail = null;
  requestControllers.historyDetail = null;
  state.candidates = [];
  state.candidatePayload = null;
  state.candidateDetails = {};
  state.candidateDetailStatus = {};
  state.candidateDetailOpen = false;
  syncCandidateDialogA11y(false);
  state.eventsPayload = null;
  state.schedulerGate = null;
  state.history = [];
  state.historyMeta = {};
  state.historyError = "";
  state.historySnapshot = null;
  state.historySnapshotKey = "";
  state.pagination = {
    candidates: { page: 1, hasMore: false, total: 0, loading: false },
    events: { page: 1, hasMore: false, total: 0, loading: false },
    history: { page: 1, hasMore: false, total: 0, loading: false },
  };
  for (const resource of Object.keys(state.tabData)) {
    state.tabData[resource] = { status: "idle", snapshotKey: null, queryKey: "", requestId: 0, error: "" };
  }
}

async function applyBootstrapPayload(payload) {
  const snapshot = payload?.latest;
  const status = payload?.status;
  if (payload?.contract_version !== "ui-bootstrap-v1"
    || !snapshot
    || snapshot.contract_version !== "ui-bootstrap-v1"
    || !validSnapshotIdentity(snapshot)) {
    throw new Error("轻量快照合同无效");
  }
  const identityStatus = status;
  const identityValid = Boolean(
    identityStatus
    && typeof identityStatus === "object"
    && !Array.isArray(identityStatus)
    && identityStatus.snapshot_key === snapshot.snapshot_key
    && identityStatus.generated_at === snapshot.generated_at
    && identityStatus.source_snapshot_sha256 === snapshot.source_snapshot.sha256
    && identityStatus.source_snapshot_byte_size === snapshot.source_snapshot.byte_size
    && snapshotUseIdentityMatchesSnapshot(payload.snapshot_use || identityStatus.snapshot_use, snapshot)
  );
  if (!identityValid) throw new Error("快照与状态身份不一致");
  const snapshotChanged = snapshot.snapshot_key !== state.snapshot?.snapshot_key
    || snapshot.generated_at !== state.snapshot?.generated_at
    || snapshot.source_snapshot?.sha256 !== state.snapshot?.source_snapshot?.sha256
    || Number(snapshot.source_snapshot?.byte_size) !== Number(state.snapshot?.source_snapshot?.byte_size);
  if (snapshotChanged) resetLazyTabData();
  state.bootstrap = payload;
  state.snapshot = snapshot;
  if (snapshotChanged || !state.status) {
    state.status = status
      ? { ...status }
      : { ok: true, generated_at: snapshot.generated_at, snapshot_key: snapshot.snapshot_key };
    delete state.status.snapshot_use;
    delete state.status.effective_decisions;
  }
  const hasSnapshotUse = Boolean(payload.snapshot_use || status?.snapshot_use);
  if (hasSnapshotUse) {
    mergeSnapshotDecisionState({
      ...(status || {}),
      snapshot_use: payload.snapshot_use || status?.snapshot_use,
      effective_decisions: payload.effective_decisions || status?.effective_decisions,
    }, { mergeStatusFields: true, strict: true });
  } else if (status) {
    state.status = { ...(state.status || {}), ...status };
  }
  syncPreferredCandidate({ revealQualified: snapshotChanged });
}

function renderTabDataState(tab) {
  const view = $(`#${tab}View`);
  if (!view) return;
  const requirements = TAB_DATA_REQUIREMENTS[tab] || [];
  const failed = requirements.map((resource) => state.tabData[resource]).find((item) => item?.status === "error");
  const loading = requirements.some((resource) => state.tabData[resource]?.status !== "ready");
  if (failed) {
    view.classList.remove("view-loading");
    view.innerHTML = `<div class="empty-state">${icon("ph-warning-circle")}<h3>该页签数据读取失败</h3><p>${esc(failed.error || "请稍后重试")}</p><button class="icon-button" type="button" data-action="retry-tab">重试</button></div>`;
    return;
  }
  if (loading) {
    view.classList.add("view-loading");
    view.innerHTML = `${icon("ph-spinner-gap")}<span>正在按需读取${esc(TAB_META[tab]?.[0] || "页签")}数据…</span>`;
  }
}

function normalizedServerQuery(value) {
  return String(value || "").trim().slice(0, 64).toLowerCase();
}

function resourceQueryKey(resource) {
  if (resource === "candidates") {
    return JSON.stringify([
      state.candidateFilters.market === "all" ? "" : state.candidateFilters.market,
      normalizedServerQuery(state.candidateFilters.query),
    ]);
  }
  if (resource === "events") {
    return JSON.stringify([
      state.eventFilters.market === "all" ? "" : state.eventFilters.market,
      state.eventFilters.type === "all" ? "" : state.eventFilters.type,
      state.eventFilters.direction === "all" ? "" : state.eventFilters.direction,
      normalizedServerQuery(state.eventFilters.query),
    ]);
  }
  if (resource === "scheduler") return "scheduler:gate-status-v2";
  return "history:daily";
}

function resourceListUrl(resource, page = 1) {
  const url = new URL(`/api/${resource}`, location.origin);
  url.searchParams.set("page", String(page));
  url.searchParams.set("limit", String(resource === "history" ? HISTORY_LIMIT : LIST_PAGE_SIZE));
  if (resource === "candidates") {
    const market = state.candidateFilters.market === "all" ? "" : state.candidateFilters.market;
    const query = normalizedServerQuery(state.candidateFilters.query);
    if (market) url.searchParams.set("market", market);
    if (query) url.searchParams.set("q", query);
  } else if (resource === "events") {
    const market = state.eventFilters.market === "all" ? "" : state.eventFilters.market;
    const eventType = state.eventFilters.type === "all" ? "" : state.eventFilters.type;
    const direction = state.eventFilters.direction === "all" ? "" : state.eventFilters.direction;
    const query = normalizedServerQuery(state.eventFilters.query);
    if (market) url.searchParams.set("market", market);
    if (eventType) url.searchParams.set("event_type", eventType);
    if (direction) url.searchParams.set("direction", direction);
    if (query) url.searchParams.set("q", query);
  }
  return `${url.pathname}${url.search}`;
}

function validPageContract(payload) {
  return Number.isInteger(payload?.page)
    && payload.page >= 1
    && Number.isInteger(payload?.limit)
    && payload.limit >= 1
    && Number.isInteger(payload?.total)
    && payload.total >= 0
    && typeof payload?.has_more === "boolean";
}

function schedulerGateIdentityMatchesSnapshot(payload, snapshot = state.snapshot) {
  return Boolean(
    payload
    && snapshot
    && typeof payload.snapshot_key === "string"
    && payload.snapshot_key === snapshot.snapshot_key
    && typeof payload.generated_at === "string"
    && payload.generated_at === snapshot.generated_at
    && Number.isFinite(Date.parse(payload.generated_at))
  );
}

function validSchedulerGatePayload(payload) {
  const optionalTimestampFields = [
    "generation_started_at", "published_at", "source_invocation_slot",
    "effective_checkpoint", "effective_invocation_slot",
  ];
  const optionalIntegerFields = [
    "scheduler_start_delay_seconds", "generation_delay_seconds",
    "publication_delay_seconds", "missed_checkpoints_24h",
  ];
  const optionalTimestampValid = (value) => value === null
    || (typeof value === "string" && Number.isFinite(Date.parse(value)));
  const optionalIntegerValid = (value) => value === null
    || (Number.isInteger(value) && value >= 0);
  const optionalTextValid = (value) => value === null
    || (typeof value === "string" && value.trim().length > 0);
  const baseValid = Boolean(
    payload?.ok === true
    && schedulerGateIdentityMatchesSnapshot(payload)
    && ["r2", "embedded"].includes(payload.publication_backend)
    && optionalTimestampFields.every((field) => (
      Object.hasOwn(payload, field) && optionalTimestampValid(payload[field])
    ))
    && optionalIntegerFields.every((field) => (
      Object.hasOwn(payload, field) && optionalIntegerValid(payload[field])
    ))
    && typeof payload.checkpoint_coverage_status === "string"
    && payload.checkpoint_coverage_status.trim().length > 0
    && optionalTextValid(payload.checkpoint_evidence_contract_version)
    && typeof payload.recovery_mode === "string"
    && payload.recovery_mode.trim().length > 0
  );
  if (!baseValid) return false;
  if (payload.contract_version === "scheduler-health-v1") {
    return Boolean(
      typeof payload.scheduler_enabled === "boolean"
      && (payload.scheduler_enabled
        ? payload.scheduler_gap === null
        : typeof payload.scheduler_gap === "string" && payload.scheduler_gap.trim().length > 0)
    );
  }
  if (payload.contract_version !== "scheduler-health-v2") return false;
  const readiness = payload.scheduler_readiness;
  const initializing = readiness === "INITIALIZING";
  const slo = payload.scheduler_slo;
  const countFields = [
    "expected_checkpoints_24h", "published_on_time_24h",
    "late_recoveries_24h", "evidence_lag_batches",
  ];
  const countsValid = countFields.every((field) => (
    Number.isInteger(payload[field]) && payload[field] >= 0
  ));
  const publicationWithinSloValid = initializing || payload.published_at === null
    ? payload.publication_within_slo === null
    : typeof payload.publication_within_slo === "boolean";
  return Boolean(
    payload.scheduler_primary_provider === "github_actions"
    && typeof payload.scheduler_primary_enabled === "boolean"
    && typeof payload.cloudflare_dispatch_enabled === "boolean"
    && ["INITIALIZING", "READY", "DEGRADED"].includes(readiness)
    && typeof payload.checkpoint_evidence_ready === "boolean"
    && typeof payload.unattended_refresh_ready === "boolean"
    && countsValid
    && payload.published_on_time_24h + payload.late_recoveries_24h
      <= payload.expected_checkpoints_24h
    && Number.isInteger(payload.publication_slo_seconds)
    && payload.publication_slo_seconds > 0
    && publicationWithinSloValid
    && isRecord(slo)
    && slo.contract_version === "scheduler-slo-v1"
    && slo.guaranteed === false
    && slo.public_data_source_sla === false
    && Number.isInteger(slo.target_publication_within_minutes)
    && slo.target_publication_within_minutes > 0
    && slo.target_publication_within_minutes * 60 === payload.publication_slo_seconds
    && (!Object.hasOwn(slo, "coverage_window_hours")
      || slo.coverage_window_hours === 24)
    && (initializing
      ? payload.checkpoint_coverage_status === "INITIALIZING_24H_LEDGER"
      : payload.checkpoint_coverage_status === "COMPLETE_24H_LEDGER")
    && payload.checkpoint_evidence_contract_version === "scheduler-checkpoint-ledger-v1"
  );
}

function effectiveCandidateRoleFromTuple(roles) {
  if (roles?.production === "PRIMARY") return "production_primary";
  if (roles?.production === "QUALIFIED") return "production_qualified";
  if (roles?.research === "PRIORITY") return "research_priority";
  return ({
    PRIMARY: "legacy_market_primary",
    BLOCKED: "legacy_blocked",
    WATCHLIST: "legacy_watchlist",
    NONE: "legacy_watchlist",
  })[roles?.legacy] || null;
}

function validCandidateRoleRow(row, selection, publishedIdentities) {
  const roles = row?.decision_roles;
  if (row?.role_contract_version !== "candidate-role-v1"
    || !isRecord(roles)
    || !["PRIMARY", "QUALIFIED", "NONE"].includes(roles.production)
    || !["PRIMARY", "BLOCKED", "WATCHLIST", "NONE"].includes(roles.legacy)
    || !["PRIORITY", "NONE"].includes(roles.research)
    || row.decision_role !== effectiveCandidateRoleFromTuple(roles)) return false;
  const qualifiedIndex = selection.qualified_candidate_ids.indexOf(row.id);
  const productionRole = roles.production;
  if (qualifiedIndex >= 0) {
    if (productionRole !== (qualifiedIndex === 0 ? "PRIMARY" : "QUALIFIED")) return false;
    if (row.production_rank !== qualifiedIndex + 1) return false;
  } else if (productionRole !== "NONE" || Object.hasOwn(row, "production_rank")) return false;
  if (productionRole !== "NONE") {
    const identity = candidateIdentity(row.market, row.code || row.symbol);
    if (!identity || (publishedIdentities && !publishedIdentities.has(identity))) return false;
  }
  return true;
}

function validCandidateRoleEnvelope(payload, rows, { complete = false } = {}) {
  const selection = payload?.production_selection;
  if (payload?.role_contract_version !== "candidate-role-v1"
    || !isRecord(selection)
    || selection.role_contract_version !== "candidate-role-v1"
    || !["QUALIFIED_PICK", "NO_QUALIFIED_PICK"].includes(selection.action)
    || !Array.isArray(selection.qualified_candidate_ids)
    || selection.qualified_candidate_ids.some((id) => typeof id !== "string" || !/^cand_[a-f0-9]{20}$/.test(id))
    || new Set(selection.qualified_candidate_ids).size !== selection.qualified_candidate_ids.length
    || !Number.isInteger(selection.qualified_candidate_count)
    || selection.qualified_candidate_count !== selection.qualified_candidate_ids.length) return false;
  const hasPick = selection.action === "QUALIFIED_PICK";
  if ((hasPick && (
    selection.qualified_candidate_ids.length === 0
    || selection.primary_candidate_id !== selection.qualified_candidate_ids[0]
  )) || (!hasPick && (
    selection.primary_candidate_id !== null
    || selection.qualified_candidate_ids.length !== 0
  ))) return false;
  const snapshotAction = state.snapshot?.production_decision?.action;
  if (["QUALIFIED_PICK", "NO_QUALIFIED_PICK"].includes(snapshotAction)
    && selection.action !== snapshotAction) return false;
  const publishedRows = productionQualifiedRows(state.snapshot);
  const publishedIdentities = snapshotAction === "QUALIFIED_PICK"
    ? new Set(publishedRows.map((row) => candidateIdentity(row.market, row.code)))
    : null;
  if (snapshotAction === "QUALIFIED_PICK"
    && publishedRows.length !== selection.qualified_candidate_count) return false;
  if (!Array.isArray(rows)) return false;
  const rowIds = rows.map((row) => row?.id);
  if (new Set(rowIds).size !== rowIds.length
    || rows.some((row) => !validCandidateRoleRow(row, selection, publishedIdentities))) return false;
  if (complete && selection.qualified_candidate_ids.some((id) => !rowIds.includes(id))) return false;
  return true;
}

function validateResourcePayload(resource, payload, { queryKey = resourceQueryKey(resource) } = {}) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("按需资产响应不是对象");
  }
  if (!RESOURCE_CONTRACT_VERSIONS[resource]?.has(payload.contract_version)) {
    throw new Error(`按需资产合同版本无效：${resource}`);
  }
  if (resource === "scheduler") {
    if (!validSchedulerGatePayload(payload)) throw new Error("调度健康合同或快照身份无效");
    return payload;
  }
  if (!payloadIdentityMatchesSnapshot(payload)) {
    throw new Error("按需资产与当前快照身份不一致");
  }
  if (resource === "candidates") {
    const paginated = ["candidate-list-v2", "candidate-list-v1"].includes(payload.contract_version);
    const roleContract = ["candidate-list-v2", "ui-candidates-v2"].includes(payload.contract_version);
    if (!Array.isArray(payload.candidates)
      || payload.candidates.some((row) => (
        !isRecord(row)
        || !MARKET_ORDER.includes(row.market)
        || !candidateIdentity(row.market, row.code || row.symbol)
        || (paginated && (typeof row.id !== "string" || !/^cand_[a-f0-9]{20}$/.test(row.id)))
      ))) throw new Error("候选列表合同无效");
    if (paginated && (!Number.isInteger(payload.scanned_count)
      || payload.scanned_count < 0
      || !validPageContract(payload))) {
      throw new Error("候选分页合同无效");
    }
    if (roleContract) {
      const complete = payload.contract_version === "ui-candidates-v2"
        || (queryKey === JSON.stringify(["", ""])
          && payload.page === 1 && payload.total === payload.candidates.length);
      if (!validCandidateRoleEnvelope(payload, payload.candidates, { complete })) {
        throw new Error("候选角色合同与正式选择不一致");
      }
    }
    if (!paginated && queryKey !== JSON.stringify(["", ""])) {
      throw new Error("旧候选合同不支持服务端筛选");
    }
  } else if (resource === "events") {
    const events = Array.isArray(payload.events) ? payload.events : payload.events?.items;
    if (!Array.isArray(events)
      || events.some((row) => !isRecord(row) || typeof row.event_id !== "string" || !row.event_id)) {
      throw new Error("事件列表合同无效");
    }
    const modern = ["event-list-v2", "event-list-v1"].includes(payload.contract_version);
    if (modern && !validPageContract(payload)) {
      throw new Error("事件分页合同无效");
    }
    if (payload.contract_version === "event-list-v2") {
      const publication = payload.event_publication;
      const bound = payload.decision_bound;
      if (payload.ordering_contract_version !== "decision-bound-first-then-published-desc-v1"
        || !isRecord(publication)
        || !Array.isArray(publication.decision_bound_event_ids)
        || publication.decision_bound_event_count !== publication.decision_bound_event_ids.length
        || events.some((row) => typeof row.decision_bound !== "boolean")
        || !isRecord(bound)
        || !Number.isInteger(bound.total)
        || bound.total !== publication.decision_bound_event_ids.length
        || !Number.isInteger(bound.matched)
        || !Number.isInteger(bound.returned)
        || typeof bound.all_matched_returned !== "boolean") {
        throw new Error("事件绑定证据合同无效");
      }
    }
    if (!modern && queryKey !== JSON.stringify(["", "", "", ""])) {
      throw new Error("旧事件合同不支持服务端筛选");
    }
  } else if (resource === "history") {
    if (!Array.isArray(payload.history) || !validPageContract({
      page: payload.page ?? payload.meta?.page,
      limit: payload.limit ?? payload.meta?.limit,
      total: payload.total ?? payload.meta?.total,
      has_more: payload.has_more ?? payload.meta?.has_more,
    })) throw new Error("历史列表合同无效");
  }
  return payload;
}

function tabRequestStillCurrent(resource, requestId, snapshotKey, queryKey) {
  const entry = state.tabData[resource];
  return entry?.requestId === requestId
    && entry.snapshotKey === snapshotKey
    && entry.queryKey === queryKey
    && state.snapshot?.snapshot_key === snapshotKey
    && resourceQueryKey(resource) === queryKey;
}

async function loadTabResource(resource, { signal = null, requestId = ++tabRequestGeneration } = {}) {
  const expectedSnapshotKey = state.snapshot?.snapshot_key;
  const expectedQueryKey = resourceQueryKey(resource);
  state.tabData[resource] = {
    status: "loading", snapshotKey: expectedSnapshotKey, queryKey: expectedQueryKey, requestId, error: "",
  };
  if (!RESOURCE_CONTRACT_VERSIONS[resource]) return;
  const payload = resource === "history"
    ? await getHistoryPayload({ signal, page: 1 })
    : resource === "scheduler"
      ? await getJson("/api/gate-status", { signal })
      : await getJson(resourceListUrl(resource, 1), { signal });
  if (!tabRequestStillCurrent(resource, requestId, expectedSnapshotKey, expectedQueryKey)) {
    throw requestAbortError("筛选或快照已变更");
  }
  validateResourcePayload(resource, payload, { queryKey: expectedQueryKey });

  if (resource !== "history" && resource !== "scheduler") {
    const decisionStateAccepted = mergeSnapshotDecisionState(payload, { strict: true });
    if (decisionStateAccepted) refreshSnapshotUsePresentation();
  }

  if (resource === "candidates") {
    state.candidatePayload = payload;
    state.candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
    state.pagination.candidates = { page: num(payload.page, 1), hasMore: payload.has_more === true, total: num(payload.total, state.candidates.length), loading: false };
    syncPreferredCandidate({ revealQualified: true });
  } else if (resource === "events") {
    state.eventsPayload = payload;
    const eventRows = Array.isArray(payload.events) ? payload.events : Array.isArray(payload.events?.items) ? payload.events.items : [];
    state.pagination.events = { page: num(payload.page, 1), hasMore: payload.has_more === true, total: num(payload.total, eventRows.length), loading: false };
  } else if (resource === "scheduler") {
    state.schedulerGate = payload;
  } else if (resource === "history") {
    const responseMeta = payload.meta && typeof payload.meta === "object" ? payload.meta : {};
    const historyEvaluation = payload.history_evaluation && typeof payload.history_evaluation === "object"
      ? payload.history_evaluation
      : {};
    state.history = payload.history || [];
    state.pagination.history = { page: num(payload.page, 1), hasMore: payload.has_more === true || responseMeta.has_more === true, total: num(payload.total, responseMeta.decision_day_count ?? state.history.length), loading: false };
    state.historyMeta = {
      ...responseMeta,
      observation_performance: responseMeta.observation_performance
        || historyEvaluation.observation_performance
        || null,
    };
    state.historyError = "";
  }
  state.tabData[resource] = {
    status: "ready", snapshotKey: expectedSnapshotKey, queryKey: expectedQueryKey, requestId, error: "",
  };
}

async function ensureTabData(tab = state.tab) {
  if (!state.snapshot) return;
  const requirements = TAB_DATA_REQUIREMENTS[tab] || [];
  const snapshotKey = state.snapshot.snapshot_key;
  const pending = requirements.filter((resource) => {
    const item = state.tabData[resource];
    return item?.status !== "ready"
      || item.snapshotKey !== snapshotKey
      || item.queryKey !== resourceQueryKey(resource);
  });
  if (!pending.length) {
    if (tab === state.tab) {
      renderActiveTab();
      if (tab === "candidates") {
        const selectedRow = rowForKey(state.candidateKey);
        if (selectedRow) void loadCandidateDetail(selectedRow);
      }
    }
    return;
  }
  requestControllers.tab?.abort?.();
  const controller = typeof AbortController === "undefined" ? null : new AbortController();
  requestControllers.tab = controller;
  const requestId = ++tabRequestGeneration;
  renderTabDataState(tab);
  try {
    await Promise.all(pending.map((resource) => loadTabResource(resource, {
      signal: controller?.signal || null,
      requestId,
    })));
    if (tab === state.tab) {
      renderActiveTab();
      if (tab === "candidates") {
        const selectedRow = rowForKey(state.candidateKey);
        if (selectedRow) void loadCandidateDetail(selectedRow);
      }
    }
  } catch (error) {
    if (error?.name === "AbortError") {
      for (const resource of pending) {
        if (state.tabData[resource]?.requestId === requestId) {
          state.tabData[resource] = {
            status: "idle", snapshotKey: null, queryKey: resourceQueryKey(resource), requestId: 0, error: "",
          };
        }
      }
      return;
    }
    for (const resource of pending) {
      if (state.tabData[resource]?.status === "loading"
        && state.tabData[resource]?.snapshotKey === snapshotKey
        && state.tabData[resource]?.requestId === requestId) {
        state.tabData[resource] = {
          status: "error", snapshotKey, queryKey: resourceQueryKey(resource), requestId, error: error.message || "数据读取失败",
        };
      }
    }
    if (tab === state.tab) renderTabDataState(tab);
  } finally {
    if (requestControllers.tab === controller) requestControllers.tab = null;
  }
}

async function loadMoreResource(resource) {
  const pageState = state.pagination[resource];
  if (!pageState?.hasMore || pageState.loading || !state.snapshot) return;
  const resourceTab = { candidates: "candidates", events: "events", history: "history" }[resource];
  const nextPage = pageState.page + 1;
  const expectedQueryKey = resourceQueryKey(resource);
  const expectedSnapshotKey = state.snapshot.snapshot_key;
  pageState.loading = true;
  if (state.tab === resourceTab) renderActiveTab();
  requestControllers.tab?.abort?.();
  const controller = typeof AbortController === "undefined" ? null : new AbortController();
  requestControllers.tab = controller;
  try {
    const payload = await getJson(resourceListUrl(resource, nextPage), { signal: controller?.signal || null });
    if (requestControllers.tab !== controller
      || state.snapshot?.snapshot_key !== expectedSnapshotKey
      || resourceQueryKey(resource) !== expectedQueryKey) throw requestAbortError("分页筛选已变更");
    validateResourcePayload(resource, payload, { queryKey: expectedQueryKey });
    if (resource === "candidates") {
      const incoming = Array.isArray(payload.candidates) ? payload.candidates : [];
      const seen = new Set(state.candidates.map((candidate) => candidate.id || candidateId(candidate, candidate.market)));
      state.candidates.push(...incoming.filter((candidate) => {
        const identity = candidate.id || candidateId(candidate, candidate.market);
        if (seen.has(identity)) return false;
        seen.add(identity);
        return true;
      }));
      state.candidatePayload = { ...(state.candidatePayload || {}), ...payload, candidates: state.candidates };
    } else if (resource === "events") {
      const existing = Array.isArray(state.eventsPayload?.events) ? state.eventsPayload.events : [];
      const incoming = Array.isArray(payload.events) ? payload.events : Array.isArray(payload.events?.items) ? payload.events.items : [];
      const seen = new Set(existing.map((event) => event.event_id));
      const merged = [...existing, ...incoming.filter((event) => {
        if (seen.has(event.event_id)) return false;
        seen.add(event.event_id);
        return true;
      })];
      state.eventsPayload = { ...(state.eventsPayload || {}), ...payload, events: merged };
    } else {
      const incoming = Array.isArray(payload.history) ? payload.history : [];
      const seen = new Set(state.history.map((item) => item.snapshot_key || item.cache_key));
      state.history.push(...incoming.filter((item) => {
        const identity = item.snapshot_key || item.cache_key;
        if (!identity || seen.has(identity)) return false;
        seen.add(identity);
        return true;
      }));
    }
    state.pagination[resource] = {
      page: num(payload.page, nextPage),
      hasMore: payload.has_more === true || (resource === "history" && payload.meta?.has_more === true),
      total: num(payload.total, state.pagination[resource].total),
      loading: false,
    };
  } catch (error) {
    if (error?.name !== "AbortError") showToast(error.message || "下一页读取失败", "error");
    pageState.loading = false;
  } finally {
    if (requestControllers.tab === controller) requestControllers.tab = null;
    if (state.tab === resourceTab) renderActiveTab();
  }
}

async function reloadPagedResource(resource, { restoreFocusId = "" } = {}) {
  if (!state.snapshot || !RESOURCE_CONTRACT_VERSIONS[resource]) return;
  requestControllers.tab?.abort?.();
  if (resource === "candidates") {
    requestControllers.detail?.abort?.();
    requestControllers.detail = null;
    state.candidateDetailOpen = false;
    syncCandidateDialogA11y(false);
  }
  const controller = typeof AbortController === "undefined" ? null : new AbortController();
  requestControllers.tab = controller;
  const requestId = ++tabRequestGeneration;
  const snapshotKey = state.snapshot.snapshot_key;
  const queryKey = resourceQueryKey(resource);
  state.pagination[resource] = { page: 1, hasMore: false, total: 0, loading: true };
  state.tabData[resource] = { status: "loading", snapshotKey, queryKey, requestId, error: "" };
  try {
    await loadTabResource(resource, { signal: controller?.signal || null, requestId });
    if (requestControllers.tab !== controller || resourceQueryKey(resource) !== queryKey) return;
    if (state.tab === resource) {
      renderActiveTab();
      if (resource === "candidates") {
        const selectedRow = rowForKey(state.candidateKey);
        if (selectedRow) void loadCandidateDetail(selectedRow);
      }
    }
  } catch (error) {
    if (error?.name === "AbortError") {
      if (state.tabData[resource]?.requestId === requestId) {
        state.tabData[resource] = { status: "idle", snapshotKey: null, queryKey, requestId: 0, error: "" };
        state.pagination[resource].loading = false;
      }
      return;
    }
    if (state.tabData[resource]?.requestId === requestId) {
      state.tabData[resource] = {
        status: "error", snapshotKey, queryKey, requestId, error: error.message || "数据读取失败",
      };
      state.pagination[resource].loading = false;
      if (state.tab === resource) renderTabDataState(resource);
    }
  } finally {
    if (requestControllers.tab === controller) requestControllers.tab = null;
    if (restoreFocusId && state.tab === resource && resourceQueryKey(resource) === queryKey) {
      window.setTimeout(() => {
        const input = $(`#${restoreFocusId}`);
        input?.focus();
        input?.setSelectionRange?.(input.value.length, input.value.length);
      }, 0);
    }
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

function updateSnapshotExecutionBanner() {
  const banner = $("#snapshotExecutionBanner");
  if (!banner || !state.snapshot) return;
  const snapshotUse = snapshotUseTruth();
  banner.hidden = snapshotUse.currentDecisionAllowed;
  if (!banner.hidden) {
    const freshness = FRESHNESS_META[snapshotUse.freshnessState]?.label || "状态未知";
    banner.innerHTML = `${icon("ph-warning-octagon")}<div><strong>${esc(freshness)}，暂停执行</strong><span>当前合格候选强制为 0；页面只保留历史发布候选供研究，等待 fresh 新快照。</span></div>`;
  }
}

function updateTopbar() {
  const [title, subtitle] = TAB_META[state.tab];
  $("#pageTitle").textContent = title;
  $("#pageSubtitle").textContent = subtitle;
  const snapshotAsOf = state.status?.snapshot_as_of || state.snapshot?.generated_at;
  const nextRefresh = validActiveRefreshStatus(state.status) ? state.status.next_active_refresh : null;
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
  health.title = `${freshness.label}；快照生成 ${dateTime(snapshotAsOf)}；下次实际自动刷新 ${dateTime(nextRefresh)}；最近应完成检查点 ${checkpoint}；快照落后 ${lag}`;
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
  updateSnapshotExecutionBanner();
}

function refreshSnapshotUsePresentation() {
  const topbarSelectors = [
    "#pageTitle", "#pageSubtitle", "#snapshotAsOf", "#nextRefreshTime",
    "#healthBadge", "#qualityBadge",
  ];
  if (topbarSelectors.every((selector) => Boolean($(selector)))) updateTopbar();
  else updateSnapshotExecutionBanner();
}

function switchTab(tab, writeHash = true) {
  if (!TAB_META[tab]) tab = "decision";
  if (state.tab !== tab) {
    requestControllers.tab?.abort?.();
    requestControllers.detail?.abort?.();
    requestControllers.historyDetail?.abort?.();
    requestControllers.tab = null;
    requestControllers.detail = null;
    requestControllers.historyDetail = null;
    state.candidateDetailOpen = false;
    syncCandidateDialogA11y(false);
  }
  state.tab = tab;
  $$(".nav-item[data-tab]").forEach((button) => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
    button.setAttribute("tabindex", active ? "0" : "-1");
  });
  $$(".tab-panel").forEach((panel) => {
    const active = panel.dataset.tab === tab;
    panel.hidden = !active;
    panel.classList.toggle("is-active", active);
  });
  if (writeHash && location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  updateTopbar();
  renderActiveTab();
  void ensureTabData(tab);
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
  const legacyAction = isLegacyPrimaryRole(role) ? recommendationLabel(candidate, true) : isLegacyBlockedRole(role) ? "暂不执行" : "观察候选";
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
      note: isLegacyPrimaryRole(role) ? "市场内 Legacy 首选；只有 global 严格门禁通过才能升级为可执行复核" : isLegacyBlockedRole(role) ? "最接近阈值，但当前不执行" : "保留观察，不代表买入信号",
      tone: isLegacyPrimaryRole(role) ? "active" : isLegacyBlockedRole(role) ? "warning" : "muted",
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
  if (isLegacyPrimaryRole(role) && dualLow?.status === "rejected") {
    const reason = dualLow.filter_reasons?.[0]?.message;
    return `<div class="callout warning score-divergence">${icon("ph-arrows-left-right")}<div><strong>风格分歧，不是模型冲突</strong><br>Legacy 把它列为当前首选，但双低模型认为它不属于低估值风格${reason ? `：${esc(reason)}` : ""}。实际决策仍由 Legacy 与客观门控决定。</div></div>`;
  }
  if (isLegacyBlockedRole(role) && dualLow?.status === "ranked") {
    return `<div class="callout warning score-divergence">${icon("ph-shield-warning")}<div><strong>价值靠前，不等于现在能买</strong><br>双低研究排名较高，但 Legacy 或客观门控尚未通过；继续观察，不把价值分当交易指令。</div></div>`;
  }
  if (isLegacyPrimaryRole(role) && dualLow?.status === "ranked" && v2Top !== null && v2Top <= 25) {
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
  const model = state.candidatePayload?.dual_low_model || state.snapshot?.analysis_models?.dual_low;
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
        <article class="chart-card"><header class="chart-header"><div><h3 class="chart-title">价格结构与计划位</h3><p class="chart-subtitle">快照内日 K · MA5 / MA10 / MA20 · 图表和计划位随下一份快照更新</p></div>${badge(`${(candidate.kline || []).length} 根K线`)}</header><div class="chart-shell"><canvas id="decisionChart" aria-label="${esc(candidate.name)}日K线图" aria-describedby="decisionChartSummary"></canvas><table id="decisionChartSummary" class="visually-hidden chart-data-summary"><caption>${esc(candidate.name)}价格计划摘要</caption><tbody><tr><th>参考入场</th><td>${price(candidate.entry_price || candidate.price)}</td></tr><tr><th>保护止损</th><td>${price(candidate.stop_loss)}</td></tr><tr><th>目标参考</th><td>${price(candidate.take_profit_reference)}</td></tr></tbody></table></div></article>
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

function renderDecisionAuditLegacy() {
  const root = $("#decisionView");
  const production = productionDecisionTruth();
  const calibratedTruth = globalDecisionTruth();
  const qualifiedMode = production.action === "QUALIFIED_PICK" && Boolean(production.qualified);
  const historicalMode = production.action === "HISTORICAL_ONLY" && Boolean(production.historicalQualified);
  const selected = production.qualified || production.historicalQualified;
  const displayPrimary = production.primary || production.publishedPrimary;
  const selectedMarket = selected?.market || "";
  const candidate = selected?.candidate || null;
  const candidateQuote = candidate ? candidateQuoteView(candidate) : null;
  const selectedKey = candidate ? candidateId(candidate, selectedMarket) : "";
  const verifiedPositiveEventIds = new Set(displayPrimary?.verified_positive_event_ids || []);
  const selectedEvent = candidate ? automaticExternalEvents().find((event) => {
    const symbol = String(candidate.code || candidate.symbol || "").toLowerCase();
    const matchesCandidate = event.market === selectedMarket && String(event.symbol || "").toLowerCase() === symbol;
    return matchesCandidate && (verifiedPositiveEventIds.size === 0 || verifiedPositiveEventIds.has(event.event_id));
  }) : null;
  const qualificationTrackName = displayPrimary
    ? qualificationTrackLabel(displayPrimary.qualification_track)
    : "规则资格";
  const qualityTrackWithoutPositiveEvent = Boolean(
    (qualifiedMode || historicalMode)
    && displayPrimary?.qualification_track === "quality_technical"
    && verifiedPositiveEventIds.size === 0
  );
  const productionEvidenceTitle = qualityTrackWithoutPositiveEvent
    ? "全池结构化风险筛查通过当前规则；不等于官方确认不存在全部负面事件；本通道不要求正向催化深扫"
    : selectedEvent?.title || "快照未保存可展示的官方事件";
  const productionEvidenceMeta = qualityTrackWithoutPositiveEvent
    ? "质量趋势通道不绑定正向事件；规则资格分仍不是上涨概率。"
    : selectedEvent
      ? `自动核验入库 · ${dateTime(selectedEvent.effective_at)} · 规则资格分不代表胜率`
      : "结论仍以服务端 production_decision 为准";
  const selectedLegacyRank = candidate ? candidatesFor(state.snapshot, selectedMarket).findIndex((row) => candidateId(row, selectedMarket) === selectedKey) + 1 : null;
  const selectedRow = candidate ? { market: selectedMarket, candidate, legacyRank: selectedLegacyRank || null } : null;
  const calibratedExecutable = calibratedTruth.action === "REVIEW_EXECUTABLE_PICK" && Boolean(calibratedTruth.executable);
  const calibratedPrimary = calibratedTruth.executable?.primary || null;
  const calibratedCandidate = calibratedTruth.executable?.candidate || null;
  const targetDate = state.snapshot?.forecast_end_date || state.snapshot?.target_date || "--";
  const model = tenDayModelState();
  const modelPresentation = tenDayModelPresentation(model);
  const freshness = state.status?.freshness_state || "unknown";
  const marketCards = calibratedTruth.markets.map((item) => {
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
    <div class="principle-strip"><span><b>决策目标</b> 从 A 股、港股、美股中选择未来 10 个交易日净总回报最优且可执行的股票</span><small>目标日 ${esc(targetDate)} · 规则资格与校准概率分轨</small></div>
    ${historicalMode ? `<div class="snapshot-execution-banner" role="alert">${icon("ph-warning-octagon")}<div><strong>快照已过期，暂停执行</strong><span>以下规则候选是历史发布结果，只供研究；等待 fresh 新快照后才会恢复当前候选。</span></div></div>` : ""}
    <section class="answer-grid">
      <article class="answer-card ${qualifiedMode ? "is-qualified" : historicalMode ? "is-historical" : ""}">
        <div class="answer-kicker"><span class="status-pill ${qualifiedMode ? "positive" : historicalMode ? "warning" : "negative"}">${qualifiedMode ? esc(qualificationTrackName) : historicalMode ? "历史规则合格·不可执行" : "规则资格门禁"}</span><span class="mono">${esc(production.actionBasis)}</span></div>
        <h2>${qualifiedMode ? `今日${esc(qualificationTrackName)}：${esc(candidate.name || candidate.code || candidate.symbol)}` : historicalMode ? `历史快照曾规则合格：${esc(candidate.name || candidate.code || candidate.symbol)}` : "今天没有通过规则资格门禁的股票"}</h2>
        <p>${qualifiedMode ? "该候选通过了服务端发布的生产规则门禁；规则资格分只用于规则排序，不是上涨概率。" : historicalMode ? "暂停执行，等待新快照；以下候选仅供历史研究。" : "页面不会用 Legacy、V2、双低或研究排序自行补选；只有服务端的 production_decision 可以生成首屏选择。"}</p>
        <div class="answer-code"><span>生产规则输出</span><strong>${esc(production.action)}</strong></div>
        <ul class="answer-reasons">
          <li>${icon("ph-seal-check")}<span><b>服务端合同</b><small>production-rule-10d-v1 · 浏览器不升级决策</small></span></li>
          <li>${icon("ph-ranking")}<span><b>规则资格分</b><small>${qualifiedMode || historicalMode ? `${fmt(production.qualificationScore, 1)} 分` : "未产生合格分"} · 非概率</small></span></li>
          <li>${icon("ph-newspaper")}<span><b>自动外部证据</b><small>${calibratedTruth.autoEvidenceCount} 条已验证证据进入全局门禁</small></span></li>
          <li>${icon("ph-chart-line")}<span><b>校准模型结论</b><small>${esc(calibratedTruth.action)} · 下方独立展示</small></span></li>
        </ul>
        <button class="secondary-button" type="button" data-action="go-health">${qualifiedMode ? "查看数据与规则门禁" : historicalMode ? "查看过期原因" : "查看阻断原因"} ${icon("ph-arrow-right")}</button>
      </article>
      <article class="research-card production-pick-card">
        <header><div><span class="status-pill ${qualifiedMode ? "positive" : historicalMode ? "warning" : "negative"}">${esc(production.action)}</span><small>${qualifiedMode ? `${esc(qualificationTrackName)}，仍需核对交易计划` : historicalMode ? "历史规则输出，仅供研究；当前不可执行" : "无规则合格候选，不展示研究排序替代品"}</small></div>${candidate ? marketBadge(selectedMarket) : ""}</header>
        ${candidate ? `<div class="research-symbol"><div><h3>${esc(candidate.name || candidate.code || candidate.symbol)}</h3><p>${esc(candidate.code || candidate.symbol)} · ${esc(MARKET_META[selectedMarket]?.label || selectedMarket)}</p></div><strong>${fmt(production.qualificationScore, 1)}<small>规则资格分（非概率）</small></strong></div>
          <div class="research-metrics"><div><small>Legacy</small><b>${esc(legacyRankLabel(selectedRow))}</b></div><div><small>V2 结构</small><b>${candidate.v2?.rank ? `#${candidate.v2.rank}/${candidate.v2.rank_universe_size || "--"}` : "--"}</b></div><div><small>概率声明</small><b>无</b><span>calibrated=false</span></div></div>
          <div class="research-evidence"><span>${icon("ph-calendar-dots")}<b>${esc(qualificationTrackName)}证据</b></span><p>${esc(productionEvidenceTitle)}</p><small>${esc(productionEvidenceMeta)}</small></div>
          <div class="research-evidence"><span>${icon("ph-waveform")}<b>${esc(candidateQuote.title)}</b></span><p>${price(candidateQuote.price)}</p><small>${esc(candidateQuote.label)}</small></div>
          <button class="primary-button" type="button" data-action="open-candidate" data-key="${esc(selectedKey)}">${historicalMode ? "查看历史评分与风险" : "查看完整评分与风险"} ${icon("ph-arrow-right")}</button>` : `<div class="empty-state">${icon("ph-shield-slash")}<h3>暂无规则合格股票</h3><p>${esc(production.blockerCodes.slice(0, 4).join("；") || "服务端明确返回 NO_QUALIFIED_PICK。")}</p></div>`}
      </article>
    </section>
    <article class="panel calibrated-track-card">
      <header class="panel-header"><div><h3 class="panel-title">全局校准模型结论</h3><p class="panel-subtitle">与规则资格选择分轨；只有通过校准合同的 global_decision 才能展示上涨概率</p></div><span class="status-pill ${calibratedExecutable ? "positive" : "negative"}">${calibratedExecutable ? "EXECUTABLE_REVIEW" : "NO_VALID_PICK"}</span></header>
      <div class="calibrated-track-body">
        <div class="calibrated-track-summary"><span>${icon(calibratedExecutable ? "ph-chart-line-up" : "ph-chart-line-down")}</span><div><small>校准轨输出</small><strong>${esc(calibratedTruth.action)}</strong><p>${calibratedExecutable ? `${esc(calibratedCandidate?.name || calibratedCandidate?.code || "待复核候选")} · 正式 P10 ${ratioPct(calibratedTruth.probability, 1)}` : `当前证据与模型条件不足以生成跨市场买入结论。${esc(modelPresentation.title)}`}</p></div></div>
        <div class="calibrated-track-metrics"><div><small>正式 P10</small><b>${calibratedTruth.probability === null ? "未校准" : ratioPct(calibratedTruth.probability, 1)}</b></div><div><small>预期净效用</small><b>${calibratedPrimary ? pct(num(calibratedPrimary.expected_net_utility) * 100, 2) : "--"}</b></div><div><small>交易成本</small><b>${calibratedPrimary ? ratioPct(calibratedPrimary.transaction_cost, 2) : "--"}</b></div><div><small>尾部风险</small><b>${calibratedPrimary ? ratioPct(calibratedPrimary.tail_risk, 2) : "--"}</b></div></div>
      </div>
      ${calibratedExecutable ? "" : `<div class="calibrated-track-blockers"><small>校准轨阻断码</small><span>${esc(calibratedTruth.blockerCodes.slice(0, 6).join(" · ") || "NO_CANDIDATE_PASSED_STRICT_GATE")}</span></div>`}
    </article>
    ${renderKpis([
      { icon: "ph-check-circle", label: "当前规则合格", value: fmt(production.currentQualifiedCount, 0), tone: production.currentQualifiedCount ? "positive" : "negative", meta: `历史发布合格 ${fmt(production.historicalQualifiedCount, 0)} 只；过期时不可执行` },
      { icon: "ph-newspaper", label: "自动外部证据", value: fmt(calibratedTruth.autoEvidenceCount, 0), tone: calibratedTruth.autoEvidenceCount ? "positive" : "warning", meta: "model_signal 不计入外部证据" },
      { icon: "ph-chart-line-up", label: "校准模型 P10", value: calibratedTruth.probability === null ? "未校准" : ratioPct(calibratedTruth.probability, 1), tone: calibratedTruth.probability === null ? "warning" : "positive", meta: model.shadowReady ? "影子 P10 另列展示，不参与正式决策" : model.shadowRejected ? "影子 P10 留出检验未通过，仅供审计" : "绝不把规则资格分当上涨概率" },
      { icon: "ph-clock", label: "快照状态", value: freshness.toUpperCase(), tone: freshness === "fresh" ? "positive" : "negative", meta: `生成 ${dateTime(state.snapshot?.generated_at)}` },
    ])}
    <section class="market-decision-grid">${marketCards}</section>
    <div class="decision-footnote">${icon("ph-info")}<span><b>双轨边界：</b>production_decision 是首屏规则资格选择，global_decision 是独立的校准模型结论。Legacy、V2、双低和影子模型仍保留研究价值，但浏览器绝不把它们自行升级为 QUALIFIED_PICK。</span></div>`;
}

const USER_DECISION_META = {
  ENTER_TRADE_REVIEW: {
    label: "进入交易复核",
    eyebrow: "当前有规则合格候选",
    tone: "positive",
    icon: "ph-clipboard-text",
  },
  RESEARCH_ONLY: {
    label: "仅继续研究",
    eyebrow: "尚未形成可执行候选",
    tone: "warning",
    icon: "ph-magnifying-glass",
  },
  NO_ACTION: {
    label: "今日不行动",
    eyebrow: "保持现金并等待下一批次",
    tone: "negative",
    icon: "ph-hand-palm",
  },
};

function userDecisionState(snapshot = state.snapshot) {
  if (!snapshotUseTruth(snapshot).currentDecisionAllowed) return "NO_ACTION";
  if (productionDecisionTruth(snapshot).action === "QUALIFIED_PICK") return "ENTER_TRADE_REVIEW";
  if (snapshot?.global_decision?.research_priority) return "RESEARCH_ONLY";
  return "NO_ACTION";
}

function firstFiniteValue(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)));
}

function firstTextValue(...values) {
  return values.find((value) => typeof value === "string" && value.trim()) || "";
}

const TRADE_PLAN_EXIT_RULE_LABELS = {
  EXIT_IF_INVALIDATION_PRICE_BREACHED: "触及失效价格即退出",
  REVIEW_AT_TENTH_SESSION_CLOSE: "第 10 个交易日收盘复核",
  DO_NOT_CHASE_ABOVE_ENTRY_ZONE: "高于入场区间不追价",
};

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function validTradeDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function horizonRangeDisplayText(low, high) {
  const signed = (value) => `${value >= 0 ? "+" : ""}${Number(value).toFixed(1)}%`;
  return `${signed(low)} ~ ${signed(high)}`;
}

function canonicalHorizonRangeView(value) {
  if (!isRecord(value)) return null;
  const low = value.low_pct;
  const high = value.high_pct;
  const observations = value.source_observations;
  if (value.contract_version !== "horizon-range-v1"
    || value.horizon_trade_days !== 10
    || value.method_id !== "realized-vol-drift-shadow-v1"
    || value.calibrated !== false
    || !finiteRuleNumber(low) || !finiteRuleNumber(high) || !(low < 0 && high > 0)
    || !Number.isInteger(observations) || observations < 0 || observations > 20
    || value.text !== horizonRangeDisplayText(low, high)) return null;
  const start = value.source_window_start_date;
  const end = value.source_window_end_date;
  if ((start === undefined || start === null) !== (end === undefined || end === null)
    || (start !== undefined && start !== null
      && (!validTradeDate(start) || !validTradeDate(end) || start > end))) return null;
  const result = {
    contract_version: "horizon-range-v1",
    low_pct: roundRuleNumber(low, 2),
    high_pct: roundRuleNumber(high, 2),
    text: horizonRangeDisplayText(low, high),
    horizon_trade_days: 10,
    method_id: "realized-vol-drift-shadow-v1",
    calibrated: false,
    source_observations: observations,
  };
  if (start !== undefined && start !== null) {
    result.source_window_start_date = start;
    result.source_window_end_date = end;
  }
  return result;
}

function validateTenDayTradePlan(published, primary = {}, candidate = {}) {
  const errors = [];
  if (!isRecord(published)) return { valid: false, errors: ["计划对象缺失"] };
  const quote = published.reference_quote;
  const entry = published.entry_zone;
  const invalidation = published.invalidation;
  const target = published.target;
  const position = published.position_limit;
  const marketCurrency = MARKET_META[primary.market]?.currency;
  const positiveNumber = (value) => finiteRuleNumber(value) && value > 0;
  const planV2 = published.contract_version === "ten-day-trade-plan-v2";
  if (!planV2 && published.contract_version !== "ten-day-trade-plan-v1") errors.push("合同版本不匹配");
  let scenarioRange = null;
  if (planV2) {
    scenarioRange = canonicalHorizonRangeView(published.scenario_range);
    const primaryRange = canonicalHorizonRangeView(primary.estimated_10d_range);
    const candidateRangeSource = candidate?.estimated_10d_range
      || candidate?.production_qualification?.estimated_10d_range;
    const candidateRange = candidateRangeSource ? canonicalHorizonRangeView(candidateRangeSource) : null;
    if (!scenarioRange || !primaryRange
      || !normalizedFullJsonEqual(scenarioRange, primaryRange)
      || (candidateRangeSource && (!candidateRange
        || !normalizedFullJsonEqual(scenarioRange, candidateRange)))) {
      errors.push("十日情景溯源不完整或上下游不一致");
    }
  }
  if (published.status !== "REVIEW_REQUIRED") errors.push("计划状态不是 REVIEW_REQUIRED");
  if (published.horizon_trade_days !== 10) errors.push("持有窗口不是 10 个交易日");
  if (!isRecord(quote)
    || !positiveNumber(quote.price)
    || !firstTextValue(quote.source)
    || !Number.isFinite(Date.parse(quote.source_as_of || ""))
    || !firstTextValue(quote.quote_status)
    || quote.kind !== "published_snapshot_quote") errors.push("参考行情合同不完整");
  const currency = quote?.currency;
  if (!marketCurrency || currency !== marketCurrency) errors.push("参考行情币种不匹配");
  if (!isRecord(entry)
    || !positiveNumber(entry.low)
    || !positiveNumber(entry.high)
    || entry.low > entry.high
    || entry.low > quote?.price
    || entry.high < quote?.price
    || entry.currency !== currency) errors.push("入场区间合同不完整");
  if (!validTradeDate(published.entry_trade_date)) errors.push("入场交易日无效");
  if (!isRecord(invalidation)
    || !positiveNumber(invalidation.price)
    || invalidation.price >= quote?.price
    || invalidation.currency !== currency
    || !firstTextValue(invalidation.source)) errors.push("失效条件合同不完整");
  if (!isRecord(target)
    || !positiveNumber(target.price)
    || target.price <= quote?.price
    || target.currency !== currency
    || !firstTextValue(target.source)) errors.push("目标价格合同不完整");
  if (!isRecord(position)
    || position.max_single_name_weight_pct !== 10
    || position.policy !== "strategy_safety_cap_not_personalized") errors.push("仓位上限合同不完整");
  if (!validTradeDate(published.review_end_trade_date)
    || (validTradeDate(published.entry_trade_date)
      && published.review_end_trade_date < published.entry_trade_date)) errors.push("复核结束日无效");
  const eventTrack = primary.qualification_track === "event_catalyst";
  const qualityTrack = primary.qualification_track === "quality_technical";
  if ((!eventTrack && !qualityTrack)
    || (eventTrack && (!validTradeDate(published.catalyst_expiry_date)
      || published.catalyst_expiry_date !== published.review_end_trade_date))
    || (qualityTrack && published.catalyst_expiry_date !== null)) errors.push("催化有效期与资格通道不匹配");
  const exitRules = published.exit_rules;
  const requiredExitRules = Object.keys(TRADE_PLAN_EXIT_RULE_LABELS);
  if (!sameStringList(exitRules, requiredExitRules)) errors.push("退出规则合同不完整");
  if (published.is_personalized_advice !== false) errors.push("个性化建议声明无效");
  return { valid: errors.length === 0, errors, scenarioRange };
}

function tenSessionTradePlan(candidate = {}, primary = {}) {
  const published = primary.ten_day_trade_plan;
  const validation = validateTenDayTradePlan(published, primary, candidate);
  const contractPublished = validation.valid;
  const entryZone = contractPublished ? published.entry_zone : {};
  const invalidation = contractPublished ? published.invalidation : {};
  const target = contractPublished ? published.target : {};
  const planV2 = contractPublished && published.contract_version === "ten-day-trade-plan-v2";
  const scenario = contractPublished
    ? planV2 ? validation.scenarioRange || {} : primary.estimated_10d_range || {}
    : {};
  const riskReward = contractPublished ? primary.risk_reward || {} : {};
  const exitRules = contractPublished ? published.exit_rules : [];
  return {
    contractPublished,
    validationErrors: validation.errors,
    status: contractPublished ? published.status : "INVALID_OR_MISSING",
    horizonTradeDays: contractPublished ? published.horizon_trade_days : null,
    currency: contractPublished ? published.reference_quote.currency : "",
    referencePrice: contractPublished ? firstFiniteValue(published.reference_quote?.price) : null,
    referenceTime: contractPublished ? firstTextValue(published.reference_quote?.source_as_of) : "",
    referenceSource: contractPublished ? firstTextValue(published.reference_quote?.source) : "",
    quoteStatus: contractPublished ? firstTextValue(published.reference_quote?.quote_status) : "",
    entryZoneLow: contractPublished ? firstFiniteValue(entryZone.low) : null,
    entryZoneHigh: contractPublished ? firstFiniteValue(entryZone.high) : null,
    entryTradeDate: contractPublished ? firstTextValue(published.entry_trade_date) : "",
    invalidationPrice: contractPublished ? firstFiniteValue(invalidation.price) : null,
    invalidationSource: contractPublished ? firstTextValue(invalidation.source) : "",
    targetPrice: contractPublished ? firstFiniteValue(target.price) : null,
    targetSource: contractPublished ? firstTextValue(target.source) : "",
    targetLowPct: contractPublished ? firstFiniteValue(scenario.low_pct) : null,
    targetHighPct: contractPublished ? firstFiniteValue(scenario.high_pct) : null,
    rangeProvenanceAvailable: planV2,
    rangeMethod: planV2 ? firstTextValue(scenario.method_id) : "",
    rangeCalibrated: planV2 ? scenario.calibrated === true : null,
    rangeObservationCount: planV2 ? scenario.source_observations : null,
    rangeWindowStart: planV2 ? firstTextValue(scenario.source_window_start_date) : "",
    rangeWindowEnd: planV2 ? firstTextValue(scenario.source_window_end_date) : "",
    riskRewardRatio: contractPublished ? firstFiniteValue(riskReward.ratio) : null,
    maximumPosition: contractPublished ? firstFiniteValue(published.position_limit?.max_single_name_weight_pct) : null,
    positionPolicy: contractPublished ? firstTextValue(published.position_limit?.policy) : "",
    catalystExpiry: contractPublished ? firstTextValue(published.catalyst_expiry_date) : "",
    forecastEndDate: contractPublished ? firstTextValue(published.review_end_trade_date) : "",
    exitRules,
    isPersonalizedAdvice: contractPublished ? published.is_personalized_advice === true : false,
  };
}

function tradePlanValue(value, currency = "") {
  return value === null || value === undefined || value === "" || !Number.isFinite(Number(value))
    ? "待发布"
    : `${price(value)}${currency ? ` ${currency}` : ""}`;
}

function tradePlanPosition(value) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "待发布";
  const numeric = Number(value);
  return `${fmt(numeric, 1)}%`;
}

function renderDecision() {
  const root = $("#decisionView");
  const snapshot = state.snapshot;
  const production = productionDecisionTruth();
  const calibratedTruth = globalDecisionTruth();
  const decisionState = userDecisionState(snapshot);
  const meta = USER_DECISION_META[decisionState];
  const selected = production.qualified || production.historicalQualified;
  const research = decisionState === "RESEARCH_ONLY" ? researchPriorityCandidate(snapshot) : null;
  const selectedMarket = decisionState === "ENTER_TRADE_REVIEW" ? selected?.market : research?.market;
  const candidate = decisionState === "ENTER_TRADE_REVIEW" ? selected?.candidate : research?.candidate;
  const primary = decisionState === "ENTER_TRADE_REVIEW" ? production.primary : null;
  const plan = tenSessionTradePlan(candidate || {}, primary || {});
  const candidateKey = candidate && selectedMarket ? candidateId(candidate, selectedMarket) : "";
  const score = decisionState === "ENTER_TRADE_REVIEW" ? production.qualificationScore : null;
  const title = decisionState === "ENTER_TRADE_REVIEW"
    ? `${candidate?.name || candidate?.code || "候选"}进入交易前复核`
    : decisionState === "RESEARCH_ONLY"
      ? `${candidate?.name || candidate?.code || "当前首选"}仅供继续研究`
      : "当前没有足够证据支持行动";
  const summary = decisionState === "ENTER_TRADE_REVIEW"
    ? "规则资格轨已经通过，但仍需逐项核对价格、失效条件、仓位和事件有效期；这不是自动下单指令。"
    : decisionState === "RESEARCH_ONLY"
      ? "它是服务端发布的研究优先项，尚未通过完整交易门禁，不应据此建立仓位。"
      : snapshotUseTruth().currentDecisionAllowed
        ? "本轮没有规则合格候选，也没有可替代的校准模型结论；继续等待下一份快照。"
        : "当前快照不是 fresh，所有历史候选均暂停执行。";
  const targetRange = Number.isFinite(Number(plan.targetPrice))
    ? `${tradePlanValue(plan.targetPrice, plan.currency)}${Number.isFinite(Number(plan.targetLowPct)) || Number.isFinite(Number(plan.targetHighPct)) ? ` · 情景 ${pct(plan.targetLowPct, 1)} – ${pct(plan.targetHighPct, 1)}` : ""}`
    : "待发布";
  const entryZone = Number.isFinite(Number(plan.entryZoneLow)) || Number.isFinite(Number(plan.entryZoneHigh))
    ? `${tradePlanValue(plan.entryZoneLow, plan.currency)} – ${tradePlanValue(plan.entryZoneHigh, plan.currency)}`
    : "待发布";
  const rangeProvenance = plan.rangeProvenanceAvailable
    ? `历史波动情景、${plan.rangeCalibrated ? "已校准" : "未校准"}、${fmt(plan.rangeObservationCount, 0)}个观测${plan.rangeWindowStart && plan.rangeWindowEnd ? `；窗口 ${plan.rangeWindowStart} 至 ${plan.rangeWindowEnd}` : ""}`
    : "旧版情景、溯源未发布";
  const scannedCount = num(production.serverDecision?.evaluated_candidate_count, state.candidatePayload?.evaluated_count);
  const publishedCount = num(state.candidatePayload?.total, state.candidates.length || production.currentQualifiedCount);
  const defaultBlockerCopy = decisionState === "NO_ACTION"
    ? "详细门禁原因已收纳到高级详情，默认视图不展示内部原因码。"
    : "资格分只是确定性门禁匹配程度，不代表上涨概率。";
  root.innerHTML = `
    <div class="principle-strip"><span><b>唯一用户结论</b> 页面先回答“今天该不该进入交易复核”，模型轨道与原因码放在高级详情</span><small>HORIZON · 10 TRADING SESSIONS</small></div>
    <section class="user-decision-card is-${esc(decisionState.toLowerCase())}" data-user-decision-state="${esc(decisionState)}">
      <div class="user-decision-icon">${icon(meta.icon)}</div>
      <div class="user-decision-copy"><span class="status-pill ${esc(meta.tone)}">${esc(meta.label)}</span><small>${esc(meta.eyebrow)}</small><h2>${esc(title)}</h2><p>${esc(summary)}</p></div>
      ${candidate ? `<div class="user-decision-symbol">${marketBadge(selectedMarket)}<span><b>${esc(candidate.name || candidate.code)}</b><small>${esc(candidate.code || candidate.symbol)} · ${esc(MARKET_META[selectedMarket]?.label || selectedMarket)}</small></span>${score === null ? "" : `<strong>${fmt(score, 1)}<small>资格分 · 非概率</small></strong>`}</div>` : ""}
    </section>
    ${decisionState === "ENTER_TRADE_REVIEW" ? `<section class="ten-session-plan" aria-labelledby="tenSessionPlanTitle">
      <header><div><span>交易前核对清单</span><h2 id="tenSessionPlanTitle">未来 10 个交易日计划</h2><p>所有价格和日期均来自当前不可变快照；合同缺失或无效时整份计划显示“待发布”，浏览器不自行推算。</p></div><span class="status-pill ${plan.contractPublished ? "positive" : "negative"}">${plan.contractPublished ? `${esc(plan.status)} · ${fmt(plan.horizonTradeDays, 0)} 日` : "计划合同无效 / 缺失"}</span></header>
      ${plan.contractPublished ? "" : `<div class="callout negative trade-plan-contract-error">${icon("ph-warning-octagon")}<div><strong>本候选不能进入价格执行核对</strong><br>${esc(plan.validationErrors.join("；") || "服务端未发布 ten-day-trade-plan-v1/v2。")}</div></div>`}
      <div class="trade-plan-grid">
        <article><small>参考价 / 时间</small><strong>${tradePlanValue(plan.referencePrice, plan.currency)}</strong><span>${esc(plan.referenceTime ? `${dateTime(plan.referenceTime)} · ${plan.referenceSource} · ${plan.quoteStatus}` : "时间、来源与行情状态待发布")}</span></article>
        <article><small>计划入场区间</small><strong>${esc(entryZone)}</strong><span>${esc(plan.entryTradeDate ? `计划入场日 ${plan.entryTradeDate}` : "入场日待发布")}</span></article>
        <article class="is-risk"><small>失效价格</small><strong>${tradePlanValue(plan.invalidationPrice, plan.currency)}</strong><span>${esc(plan.invalidationSource ? `依据 ${plan.invalidationSource}` : "失效依据待发布")}</span></article>
        <article><small>目标区间</small><strong>${esc(targetRange)}</strong><span>${esc(plan.targetSource ? `${rangeProvenance}；依据 ${plan.targetSource}；情景范围不是收益承诺` : "目标依据待发布")}</span></article>
        <article><small>风险收益比</small><strong>${Number.isFinite(Number(plan.riskRewardRatio)) ? fmt(plan.riskRewardRatio, 2) : "待发布"}</strong><span>仍需结合实际滑点</span></article>
        <article><small>建议最大仓位</small><strong>${esc(tradePlanPosition(plan.maximumPosition))}</strong><span>${esc(plan.positionPolicy === "strategy_safety_cap_not_personalized" ? "策略安全上限 · 非个性化建议" : "上限而非默认仓位")}</span></article>
        <article><small>催化有效期</small><strong>${esc(plan.catalystExpiry || (primary?.qualification_track === "quality_technical" ? "不适用" : "待发布"))}</strong><span>${primary?.qualification_track === "quality_technical" ? "质量趋势轨不依赖正向催化" : "过期后重新评估"}</span></article>
        <article><small>最迟退出日</small><strong>${esc(plan.forecastEndDate || "待发布")}</strong><span>第 10 个有效交易日</span></article>
      </div>
      <div class="trade-plan-exit-rules"><div><small>独立退出规则</small><strong>任一规则触发都要停止原计划并重新判断</strong></div>${plan.exitRules.length ? `<ul>${plan.exitRules.map((rule) => `<li><b>${esc(TRADE_PLAN_EXIT_RULE_LABELS[rule] || rule)}</b><code>${esc(rule)}</code></li>`).join("")}</ul>` : `<span>退出规则待发布</span>`}</div>
      <footer>${icon("ph-warning-circle")}<strong>规则资格分不是上涨概率，也不是收益保证。</strong><span>${plan.contractPublished && plan.isPersonalizedAdvice === false ? "该计划不是个性化投资建议；进入交易复核后仍可选择不买。" : "计划合同未通过校验，不应用于下单。"}</span></footer>
    </section>` : `<div class="no-action-guidance ${decisionState === "RESEARCH_ONLY" ? "is-research" : ""}">${icon(decisionState === "RESEARCH_ONLY" ? "ph-binoculars" : "ph-hourglass")}<div><strong>${decisionState === "RESEARCH_ONLY" ? "下一步只做研究核验" : "下一步等待新快照"}</strong><p>${esc(defaultBlockerCopy)}</p></div></div>`}
    <div class="decision-primary-actions">
      ${candidateKey ? `<button class="primary-button" type="button" data-action="open-candidate" data-key="${esc(candidateKey)}">${decisionState === "ENTER_TRADE_REVIEW" ? "核对完整评分与风险" : "查看研究证据"} ${icon("ph-arrow-right")}</button>` : ""}
      <button class="secondary-button" type="button" data-action="go-candidates">查看决策短名单</button>
      <button class="secondary-button" type="button" data-action="go-health">检查数据健康</button>
    </div>
    ${renderKpis([
      { icon: "ph-scan", label: "规则扫描", value: fmt(scannedCount, 0), meta: `短名单当前发布 ${fmt(publishedCount, 0)} 只` },
      { icon: "ph-check-circle", label: "规则合格", value: fmt(production.currentQualifiedCount, 0), tone: production.currentQualifiedCount ? "positive" : "negative", meta: "只计当前 fresh 快照" },
      { icon: "ph-calendar-dots", label: "目标退出日", value: plan.forecastEndDate || snapshot?.forecast_end_date || "--", meta: "按市场交易所日历" },
      { icon: "ph-clock", label: "快照状态", value: String(state.status?.freshness_state || "unknown").toUpperCase(), tone: snapshotUseTruth().currentDecisionAllowed ? "positive" : "negative", meta: `生成 ${dateTime(snapshot?.generated_at)}` },
    ])}
    <details class="advanced-decision-details">
      <summary>${icon("ph-sliders-horizontal")}<span>查看模型轨道与原因详情</span><small>高级研究信息</small>${icon("ph-caret-down")}</summary>
      <div class="advanced-decision-body">
        <article><span>规则资格轨</span><strong>${esc(production.action)}</strong><p>规则轨 ${esc(production.action)} · 校准轨 ${esc(calibratedTruth.action)}。资格分不是概率。</p></article>
        <article><span>全局校准轨</span><strong>${esc(calibratedTruth.action)}</strong><p>只有通过校准合同的 global_decision 才能展示上涨概率；当前正式 P10：${calibratedTruth.probability === null ? "未校准" : ratioPct(calibratedTruth.probability, 1)}。</p></article>
        <article class="advanced-blockers"><span>内部原因码</span><code>${esc([...new Set([...production.blockerCodes, ...calibratedTruth.blockerCodes])].join(" · ") || "NONE")}</code><p>原因码只用于审计，不替代上方用户结论。</p></article>
      </div>
    </details>
    <div class="decision-footnote">${icon("ph-info")}<span><b>决策边界：</b>Legacy、V2、双低和影子模型继续保留研究价值，但浏览器绝不把它们自行升级为 QUALIFIED_PICK。</span></div>`;
}

function filteredCandidates() {
  const { market, risk, route, query } = state.candidateFilters;
  const needle = query.trim().toLowerCase();
  const rows = allCandidates().filter((row) => {
    if (market !== "all" && row.market !== market) return false;
    if (risk !== "all" && candidateRiskLevel(row.candidate, row.market) !== risk) return false;
    if (route !== "all" && !routeNames(row.candidate).includes(route)) return false;
    if (needle && !`${row.candidate.name || ""} ${row.candidate.code || row.candidate.symbol || ""}`.toLowerCase().includes(needle)) return false;
    return true;
  });
  if (market !== "all") return rows;
  return rows.sort((left, right) => {
    const rolePriority = {
      production_primary: 0,
      production_qualified: 1,
      qualified: 1,
      historical_production_primary: 2,
      historical_production_qualified: 3,
      historical_qualified: 3,
      legacy_market_primary: 4,
      primary: 4,
      research_priority: 5,
      research: 5,
      legacy_watchlist: 6,
      watchlist: 6,
      legacy_blocked: 7,
      blocked: 7,
    };
    const roleDelta = (rolePriority[left.decisionRole] ?? 5) - (rolePriority[right.decisionRole] ?? 5);
    if (roleDelta) return roleDelta;
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

function syncPreferredCandidate({ revealQualified = false } = {}) {
  const production = productionDecisionTruth();
  const preferred = production.qualified || production.historicalQualified;
  if (preferred) {
    const key = candidateId(preferred.candidate, preferred.market);
    const row = allCandidates().find((item) => candidateId(item.candidate, item.market) === key);
    if (row) {
      state.candidateKey = key;
      if (revealQualified && production.qualified) state.candidateFilters = { market: "all", risk: "all", route: "all", query: "" };
      return row;
    }
  }
  const current = state.candidateKey ? rowForKey(state.candidateKey) : null;
  if (current) return current;
  const fallback = researchPriorityCandidate() || allCandidates()[0] || null;
  state.candidateKey = fallback ? candidateId(fallback.candidate, fallback.market) : "";
  return fallback;
}

function selectedCandidateRow(rows) {
  if (state.candidateKey) {
    return rows.find((row) => candidateId(row.candidate, row.market) === state.candidateKey) || null;
  }
  const selected = rows[0] || null;
  if (selected) state.candidateKey = candidateId(selected.candidate, selected.market);
  return selected;
}

function featureEvidence(candidate) {
  const groups = candidate?.v2?.factor_groups || {};
  return Object.entries(groups).flatMap(([groupName, group]) => (group.features || []).map((feature) => ({ groupName, ...feature })));
}

function candidateApiId(row) {
  return row?.candidate?.id || row?.candidate?.candidate_id || row?.candidate?.asset_id || "";
}

function candidateDetailKey(row) {
  return row ? candidateId(row.candidate, row.market) : "";
}

function detailedCandidateRow(row) {
  if (!row) return null;
  const detail = state.candidateDetails[candidateDetailKey(row)];
  if (!detail) return row;
  return {
    ...row,
    candidate: {
      ...row.candidate,
      ...detail,
      production_qualification: detail.production_qualification || row.candidate.production_qualification,
    },
  };
}

async function loadCandidateDetail(row) {
  const key = candidateDetailKey(row);
  const apiId = candidateApiId(row);
  if (!key || !apiId || state.candidateDetails[key] || state.candidateDetailStatus[key] === "loading") return;
  requestControllers.detail?.abort?.();
  const controller = typeof AbortController === "undefined" ? null : new AbortController();
  requestControllers.detail = controller;
  state.candidateDetailStatus[key] = "loading";
  if (state.tab === "candidates" && state.candidateKey === key) renderCandidates();
  try {
    const payload = await getJson(`/api/candidates/${encodeURIComponent(apiId)}`, { signal: controller?.signal || null });
    if (requestControllers.detail !== controller) throw requestAbortError("已切换候选");
    if (!RESOURCE_CONTRACT_VERSIONS.candidateDetail.has(payload?.contract_version)
      || !payloadIdentityMatchesSnapshot(payload)
      || payload.id !== apiId) throw new Error("候选详情合同或快照身份无效");
    const detail = payload.candidate;
    if (!detail || typeof detail !== "object" || Array.isArray(detail)) throw new Error("候选详情合同无效");
    if (payload.contract_version === "candidate-detail-v2"
      && (!validCandidateRoleEnvelope(payload, [detail]) || detail.id !== payload.id)) {
      throw new Error("候选详情角色合同与正式选择不一致");
    }
    mergeSnapshotDecisionState(payload, { strict: true });
    if (candidateId(detail, row.market) !== key) throw new Error("候选详情标的身份不一致");
    state.candidateDetails[key] = detail;
    state.candidateDetailStatus[key] = "ready";
  } catch (error) {
    if (error?.name === "AbortError") {
      if (state.candidateDetailStatus[key] === "loading") state.candidateDetailStatus[key] = "idle";
      return;
    }
    state.candidateDetailStatus[key] = "error";
    showToast(error.message || "候选详情读取失败", "error");
  } finally {
    if (requestControllers.detail === controller) requestControllers.detail = null;
    if (state.tab === "candidates" && state.candidateKey === key) renderCandidates();
  }
}

function candidateDetail(row) {
  if (!row) return `<div class="empty-state">${icon("ph-cursor-click")}<h3>选择一只候选</h3><p>点击左侧候选查看来源链、三种评分视角和客观门控。</p></div>`;
  const displayRow = detailedCandidateRow(row);
  const { candidate: raw, market } = displayRow;
  const candidate = raw;
  const lineage = candidate.candidate_lineage || {};
  const routes = lineage.recall_routes || [];
  const quality = candidate.data_quality;
  const gates = candidate.decision_gates || [];
  const riskTexts = [...(candidate.risk_items || []).map((risk) => `${risk.code}${risk.evidence ? ` · ${risk.evidence}` : ""}`), ...(candidate.risk_flags || [])];
  const features = featureEvidence(candidate);
  const checked = state.compare.includes(candidateId(row.candidate, market));
  const dualLow = dualLowAnalysis(candidate);
  const shadowModel = candidateShadowModel(candidate, market);
  const shadowP10 = shadowProbability(shadowModel);
  const coverage = marketCoverageState(market);
  const quoteView = candidateQuoteView(candidate);
  const marketGate = coverage.state === "READY" ? "" : `<div class="callout ${coverage.state === "BLOCKED" ? "negative" : "warning"}">${icon(coverage.state === "BLOCKED" ? "ph-warning-octagon" : "ph-warning-circle")}<div><strong>市场级门禁：${coverage.state}</strong><br>${esc(coverage.reasons.join("；") || "市场覆盖尚未达到跨市场可执行标准")}。单股门控通过也不能绕过市场级阻断。</div></div>`;
  const nextActiveRefresh = validActiveRefreshStatus(state.status) ? state.status.next_active_refresh : null;
  const snapshotStatus = `<div class="callout info">${icon("ph-waveform")}<div><strong>${esc(quoteView.title)}：${esc(quoteView.label)}</strong><br>快照生成 ${esc(dateTime(state.status?.snapshot_as_of || state.snapshot?.generated_at))}；下次实际自动刷新 ${esc(dateTime(nextActiveRefresh))}。评分与排序不在浏览器重算。</div></div>`;
  const qualification = isProductionCandidateRole(row.decisionRole)
    ? productionQualificationForCandidate(candidate, market)
    : null;
  const historicalQualification = isHistoricalProductionCandidateRole(row.decisionRole);
  const detailStatus = state.candidateDetailStatus[candidateDetailKey(row)] || (candidateApiId(row) ? "idle" : "embedded");
  const detailNotice = detailStatus === "loading"
    ? `<div class="detail-loading" role="status">${icon("ph-spinner-gap")} 正在读取完整候选详情…</div>`
    : detailStatus === "error"
      ? `<div class="callout warning">${icon("ph-warning-circle")}<div><strong>完整详情暂不可用</strong><br>当前仍展示已发布短名单摘要，不会用浏览器数据补算。</div></div>`
      : "";
  return `<article class="detail-panel candidate-detail">
    <button class="candidate-detail-back" type="button" data-action="close-candidate-detail">${icon("ph-arrow-left")} 返回决策短名单</button>
    <header class="detail-header"><div><div class="eyebrow">${marketBadge(market)} ${esc(MARKET_META[market].label)} · ${esc(candidate.code || candidate.symbol)}</div><h2 class="detail-title">${esc(candidate.name)}</h2><p class="detail-subtitle">${esc(candidate.role || candidate.reason_tags || "综合候选")}</p></div><div class="detail-actions">${qualification ? badge(`${decisionRoleLabel(row.decisionRole)} · ${qualificationTrackLabel(qualification.qualification_track)} ${fmt(qualification.qualification_score, 1)} 分`, historicalQualification ? "warning" : "positive") : badge(decisionRoleLabel(row.decisionRole), isLegacyBlockedRole(row.decisionRole) ? "warning" : "primary")}${badge(candidate.legacy_complete === false ? "Legacy 未深评" : `Legacy ${legacyRankLabel(displayRow)}`, candidate.legacy_complete === false ? "warning" : "primary")}${candidate.v2?.rank ? badge(`V2 #${candidate.v2.rank}/${candidate.v2.rank_universe_size}`, "purple") : ""}${dualLow?.status === "ranked" ? badge(`双低 #${dualLow.rank}/${dualLow.rank_universe_size}`, "positive") : dualLow ? badge(dualLowLabel(dualLow), dualLowTone(dualLow)) : ""}</div></header>
    ${detailNotice}
    ${historicalQualification ? `<div class="callout warning">${icon("ph-warning-octagon")}<div><strong>历史规则合格，不可作为当前买入信号</strong><br>快照已经过期；本页只保留评分与证据供研究，等待 fresh 快照后再判断。</div></div>` : ""}
    ${marketGate}
    ${snapshotStatus}
    <div class="shadow-p10-detail ${shadowP10 === null ? "is-unavailable" : ""}"><div><small>影子 P10</small><strong>${esc(shadowP10Label(shadowModel))}</strong></div><p>${shadowP10 === null ? "该候选尚无可用的影子概率。" : shadowModel?.rank_eligible === true ? "影子模型已通过本市场研究排序门槛，估计未来 10 个交易日净收益为正的概率。" : "该概率只保留用于审计；留出质量、时点或市场门槛未通过，不参与研究排序。"}<b>不参与正式决策</b></p><span>${esc(shadowModel?.market_validation_status || shadowModel?.model_id || "影子模型未发布")}</span></div>
    ${scoreLensCards(candidate, market)}
    ${scoreDivergence(candidate, market)}
    <div class="detail-section"><div class="section-heading"><h3>来源链</h3><span>${esc(lineage.universe_origin || (market === "a_share" ? "dynamic_snapshot" : "curated_static"))}</span></div>${routes.length ? `<ul class="event-list">${routes.map((route) => `<li><h4>${esc(route.route || "legacy")} · ${esc(route.source || "来源未保存")}</h4><p>${esc(route.reason || "该路径召回")}</p><div class="event-meta"><span>${esc(route.published_at || route.observed_at || "时间未保存")}</span>${route.decay_weight !== undefined ? `<span>延续权重 ${fmt(route.decay_weight, 2)}</span>` : ""}</div></li>`).join("")}</ul>` : `<div class="callout">${icon("ph-info")}<div>旧快照没有结构化召回来源；这不会影响旧评分，但 V2 事件组不据此加分。</div></div>`}</div>
    <div class="detail-section"><div class="section-heading"><h3>V2 评分分组</h3><span>同一特征只在一组计分</span></div>${factorCards(candidate)}</div>
    <div class="detail-section">${dualLowPanel(candidate, market)}</div>
    ${features.length ? `<div class="detail-section"><div class="section-heading"><h3>特征证据</h3><span>${features.filter((f) => f.used_in_score).length}/${features.length} 参与</span></div><div class="feature-table">${features.map((feature) => `<div><span>${esc(feature.feature_id)}</span><b>${feature.used_in_score ? fmt(feature.score, 1) : "缺失"}</b><small>${esc(feature.evidence || "")}</small></div>`).join("")}</div></div>` : ""}
    <div class="detail-section"><div class="section-heading"><h3>客观门控与风险</h3><span>${esc(coverage.state === "READY" ? candidate.execution_state || "Legacy" : `MARKET_${coverage.state}`)}</span></div>${gates.length ? `<ul class="gate-list">${gates.map((gate) => `<li><span class="status-pill ${gate.status === "PASS" ? "positive" : gate.status === "BLOCK" ? "negative" : "warning"}">${esc(gate.status)}</span><div><strong>${esc(gate.id)}</strong><small>${esc(gate.reason || "")}</small></div></li>`).join("")}</ul>` : `<p class="muted">旧快照尚未保存 V2 门控。</p>`}${riskTexts.length ? `<ul class="evidence-list risk-list">${riskTexts.map((risk) => `<li><p>${esc(risk)}</p></li>`).join("")}</ul>` : `<p class="muted">未保存额外风险标签。</p>`}</div>
    <div class="detail-footer"><button class="icon-button ${checked ? "is-active" : ""}" type="button" data-action="compare" data-key="${esc(candidateId(row.candidate, market))}">${icon(checked ? "ph-check" : "ph-scales")} ${checked ? "已加入对比" : "加入对比"}</button></div>
  </article>`;
}

function candidateMobileCard(row) {
  const c = row.candidate;
  const key = candidateId(row.candidate, row.market);
  const risk = candidateRiskLevel(c, row.market);
  const qualification = isProductionCandidateRole(row.decisionRole)
    ? productionQualificationForCandidate(c, row.market)
    : null;
  const roleLabel = decisionRoleLabel(row.decisionRole);
  const positiveRole = ["production_primary", "production_qualified", "qualified"].includes(row.decisionRole);
  const historicalRole = isHistoricalProductionCandidateRole(row.decisionRole);
  return `<button class="candidate-mobile-card ${key === state.candidateKey ? "is-selected" : ""}" type="button" data-action="select-candidate" data-key="${esc(key)}" aria-pressed="${key === state.candidateKey}">
    <header><span>${marketBadge(row.market)}<b>${esc(c.name)}</b><small>${esc(c.code || c.symbol)}</small></span>${badge(roleLabel, positiveRole ? "positive" : historicalRole ? "warning" : isLegacyBlockedRole(row.decisionRole) ? "negative" : "")}</header>
    <dl><div><dt>十日情景</dt><dd>${esc(candidateTenDayRange(c))}</dd></div><div><dt>下行风险</dt><dd class="${risk === "clear" ? "positive" : risk === "blocked" ? "negative" : "warning"}">${esc(candidateDownsideLabel(c, risk))}</dd></div><div><dt>事件覆盖</dt><dd>${esc(candidateEventGrade(c))}</dd></div></dl>
    <span class="candidate-mobile-cta">查看详情 ${icon("ph-arrow-right")}</span>
  </button>`;
}

function candidateTenDayRange(candidate) {
  const range = candidate?.estimated_10d_range || candidate?.production_qualification?.estimated_10d_range || {};
  const low = firstFiniteValue(range.low_pct);
  const high = firstFiniteValue(range.high_pct);
  return Number.isFinite(Number(low)) || Number.isFinite(Number(high))
    ? `${pct(low, 1)} – ${pct(high, 1)}`
    : "待发布";
}

function candidateDownsideLabel(candidate, risk = candidateRiskLevel(candidate)) {
  const low = firstFiniteValue(candidate?.estimated_10d_range?.low_pct);
  if (Number.isFinite(Number(low))) return `${pct(low, 1)} 情景下沿`;
  return ({ clear: "未见明确阻断", warning: "存在警告", blocked: "已阻断" })[risk] || "待核验";
}

function candidateEventGrade(candidate) {
  const riskScreen = candidate?.risk_screen || candidate?.risk_event_screen || {};
  const enrichment = candidate?.positive_event_enrichment || {};
  const qualification = candidate?.qualification || candidate?.production_qualification || {};
  const verifiedEventIds = enrichment.verified_positive_event_ids
    || candidate?.verified_positive_event_ids
    || qualification.verified_positive_event_ids
    || [];
  if (String(riskScreen.status || "").toUpperCase() === "BLOCKED") return "负面风险阻断";
  if (verifiedEventIds.length) return "正向证据已核验";
  if (String(riskScreen.status || "").toUpperCase() === "PASS") return "结构化风险筛查 PASS";
  if (qualification.status === "QUALIFIED" && qualification.qualification_track === "quality_technical") {
    return "结构化风险筛查 PASS";
  }
  return candidate?.event_candidate_scanned === true || qualification.event_candidate_scanned === true
    ? "事件已扫描"
    : "覆盖待确认";
}

function restoreCandidateDialogBackground() {
  for (const item of candidateDialogBackgroundState) {
    if (!item.element) continue;
    if ("inert" in item.element) item.element.inert = item.inert;
    if (item.hadInertAttribute) item.element.setAttribute("inert", "");
    else item.element.removeAttribute("inert");
    if (item.ariaHidden === null) item.element.removeAttribute("aria-hidden");
    else item.element.setAttribute("aria-hidden", item.ariaHidden);
  }
  candidateDialogBackgroundState = [];
  document.body?.classList?.remove("has-modal-dialog");
}

function syncCandidateDialogA11y(forceOpen = null) {
  restoreCandidateDialogBackground();
  const host = $(".candidate-detail-host");
  const mobile = window.matchMedia?.("(max-width: 760px)")?.matches === true;
  const open = forceOpen === null ? state.candidateDetailOpen && mobile : forceOpen && mobile;
  if (!host) return;
  host.setAttribute("role", open ? "dialog" : "region");
  if (open) host.setAttribute("aria-modal", "true");
  else host.removeAttribute("aria-modal");
  if (!open) return;
  const background = [
    $(".side-rail"),
    $(".topbar"),
    $("#snapshotExecutionBanner"),
    ...$$("#candidatesView > :not(.candidate-master-detail)"),
    $(".candidate-table-panel"),
  ].filter((element, index, items) => element && items.indexOf(element) === index);
  candidateDialogBackgroundState = background.map((element) => ({
    element,
    inert: Boolean(element.inert),
    hadInertAttribute: element.hasAttribute("inert"),
    ariaHidden: element.getAttribute("aria-hidden"),
  }));
  for (const element of background) {
    if ("inert" in element) element.inert = true;
    element.setAttribute("inert", "");
    element.setAttribute("aria-hidden", "true");
  }
  document.body?.classList?.add("has-modal-dialog");
}

function candidateDialogFocusables() {
  const host = $(".candidate-detail-host.is-open");
  if (!host) return [];
  return $$('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', host)
    .filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
}

function renderCandidates() {
  const root = $("#candidatesView");
  const previousHost = $(".candidate-detail-host.is-open", root);
  const previousActive = document.activeElement;
  const restoreDialogFocus = Boolean(previousHost && previousActive && previousHost.contains(previousActive));
  const restoreAction = restoreDialogFocus ? previousActive.dataset?.action || "" : "";
  const restoreKey = restoreDialogFocus ? previousActive.dataset?.key || "" : "";
  restoreCandidateDialogBackground();
  const truth = globalDecisionTruth();
  const production = productionDecisionTruth();
  const rows = filteredCandidates();
  const selected = selectedCandidateRow(rows);
  const all = allCandidates();
  const recalled = num(state.candidatePayload?.scanned_count, production.serverDecision?.evaluated_candidate_count);
  const evaluated = num(state.candidatePayload?.evaluated_count, production.serverDecision?.evaluated_candidate_count);
  const published = num(state.candidatePayload?.total, all.length);
  const blocked = all.filter((row) => candidateRiskLevel(row.candidate, row.market) === "blocked").length;
  const withLineage = all.filter((row) => routeNames(row.candidate).length).length;
  const tenDayState = tenDayModelState();
  const tenDayPresentation = tenDayModelPresentation(tenDayState);
  const historicalOnly = production.currentAction === "HISTORICAL_ONLY" && production.historicalQualifiedCount > 0;
  const candidateTrackTitle = production.qualifiedCount ? "生产规则模型已有合格候选" : historicalOnly ? "历史规则候选仅供研究" : tenDayPresentation.title;
  const candidateTrackDetail = production.qualifiedCount
    ? `规则轨已发布 ${fmt(production.qualifiedCount, 0)} 只合格候选；${tenDayPresentation.detail}`
    : historicalOnly
      ? `已发布快照曾有 ${fmt(production.historicalQualifiedCount, 0)} 只合格候选，但快照已过期，当前合格数强制为 0，暂停执行。`
      : tenDayPresentation.detail;
  const marketKpi = (coverage) => {
    const isA = coverage.market === "a_share";
    const funnel = recallFunnel(coverage.section, coverage.market);
    const originLabel = coverage.origin === "dynamic_market_snapshot" ? "动态" : coverage.origin === "curated_static" ? "静态" : "召回";
    const tone = coverage.state === "READY" ? "positive" : coverage.state === "BLOCKED" ? "negative" : "warning";
    const readyMeta = isA && coverage.origin === "dynamic_snapshot"
      ? "本轮动态多路召回"
      : coverage.origin === "dynamic_market_snapshot"
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
      <div class="toolbar-left"><div><h2>决策短名单</h2><p><strong>召回 ${fmt(recalled, 0)} · 规则评估 ${fmt(evaluated, 0)} · 展示 ${fmt(published, 0)}</strong> · 点击候选后再按需读取完整证据</p></div></div>
      <div class="toolbar-right"><label class="search-field">${icon("ph-magnifying-glass")}<input id="candidateSearch" type="search" value="${esc(state.candidateFilters.query)}" placeholder="搜索公司 / 代码" aria-label="搜索候选"></label></div>
    </div>
    <div class="callout ${production.qualifiedCount ? "info" : historicalOnly ? "warning" : ["warning", "negative"].includes(tenDayPresentation.tone) ? tenDayPresentation.tone : ""} section-callout shadow-model-callout">${icon(production.qualifiedCount ? "ph-check-circle" : historicalOnly ? "ph-warning-octagon" : tenDayPresentation.icon)}<div><strong>${esc(candidateTrackTitle)}</strong><br>${esc(candidateTrackDetail)} 两条轨道分开展示；规则资格分不是上涨概率。<span class="formal-candidate-count">当前规则合格 ${fmt(production.currentQualifiedCount, 0)} · 历史发布合格 ${fmt(production.historicalQualifiedCount, 0)} · 校准可执行 ${fmt(truth.executableCount, 0)}</span>${tenDayPresentation.reasonCodes.length ? `<small>校准轨原因码：${esc(tenDayPresentation.reasonCodes.join(" · "))}</small>` : ""}</div></div>
    <div class="filter-strip">
      <div class="filter-group"><span>市场</span><div class="segmented-button"><button data-action="candidate-market" data-market="all" aria-pressed="${state.candidateFilters.market === "all"}">全部</button>${MARKET_ORDER.map((market) => `<button data-action="candidate-market" data-market="${market}" aria-pressed="${state.candidateFilters.market === market}">${MARKET_META[market].label}</button>`).join("")}</div></div>
      <label>风险<select id="candidateRisk"><option value="all">全部</option><option value="clear">无明确警告</option><option value="warning">有警告</option><option value="blocked">被阻断</option></select></label>
      <label>召回<select id="candidateRoute"><option value="all">全部来源</option><option value="event">事件</option><option value="momentum">动量</option><option value="liquidity">流动性</option><option value="pullback">回踩</option><option value="activity">活跃度</option><option value="quality">规模质量</option><option value="history">历史延续</option><option value="curated">旧静态池</option></select></label>
    </div>
    ${renderKpis([
      { icon: "ph-check-circle", label: "当前规则合格", value: fmt(production.currentQualifiedCount, 0), tone: production.currentQualifiedCount ? "positive" : historicalOnly ? "warning" : "negative", meta: `历史发布合格 ${fmt(production.historicalQualifiedCount, 0)} 只；校准可执行 ${fmt(truth.executableCount, 0)} 只` },
      ...truth.markets.map((coverage, index) => {
        const item = marketKpi(coverage);
        if (index === truth.markets.length - 1) item.meta = `${item.meta} · 页面 ${all.length} 只 · 来源链 ${withLineage} 只 · BLOCK ${blocked}`;
        return item;
      }),
    ])}
    <div class="master-detail candidate-master-detail">
      <section class="panel candidate-table-panel"><header class="panel-header"><div><h3 class="panel-title">决策短名单</h3><p class="panel-subtitle">先看结论、十日区间、下行风险和事件覆盖；推荐度不是收益概率，评分细项放在详情</p></div><span class="shortlist-count">召回 ${fmt(recalled, 0)} · 规则评估 ${fmt(evaluated, 0)} · 发布 ${fmt(published, 0)}</span></header>
        ${rows.length ? `<div class="data-table-wrap"><table class="data-table candidate-shortlist-table"><caption class="visually-hidden">决策短名单：召回 ${fmt(recalled, 0)} 只，规则评估 ${fmt(evaluated, 0)} 只，当前发布 ${fmt(published, 0)} 只</caption><thead><tr><th>市场</th><th>公司 / 代码</th><th>统一结论</th><th>十日情景</th><th>下行风险</th><th>事件覆盖</th><th></th></tr></thead><tbody>${rows.map((row) => {
          const c = row.candidate;
          const key = candidateId(row.candidate, row.market);
          const risk = candidateRiskLevel(c, row.market);
          const currentProductionRole = ["production_primary", "production_qualified", "qualified"].includes(row.decisionRole);
          const historicalProductionRole = isHistoricalProductionCandidateRole(row.decisionRole);
          const statusTone = currentProductionRole
            ? "positive"
            : historicalProductionRole
              ? "warning"
              : isLegacyBlockedRole(row.decisionRole)
                ? "negative"
                : risk === "clear" ? "positive" : risk === "blocked" ? "negative" : "warning";
          const statusLabel = decisionRoleLabel(row.decisionRole);
          return `<tr class="${key === state.candidateKey ? "is-selected" : ""}" tabindex="0" data-action="select-candidate" data-key="${esc(key)}"><td>${marketBadge(row.market)}</td><td><span class="name">${esc(c.name)}</span><br><span class="symbol">${esc(c.code || c.symbol)}</span></td><td><span class="status-pill ${statusTone}">${statusLabel}</span></td><td>${esc(candidateTenDayRange(c))}</td><td class="${risk === "blocked" ? "negative" : risk === "warning" ? "warning" : "positive"}">${esc(candidateDownsideLabel(c, risk))}</td><td>${esc(candidateEventGrade(c))}</td><td><button class="row-action" type="button" data-action="select-candidate" data-key="${esc(key)}" aria-label="查看${esc(c.name)}详情">${icon("ph-caret-right")}</button></td></tr>`;
        }).join("")}</tbody></table></div>` : `<div class="empty-state">${icon("ph-funnel-x")}<h3>没有匹配候选</h3><p>调整市场、风险或召回来源筛选。</p></div>`}
        ${rows.length ? `<div class="candidate-mobile-list">${rows.map(candidateMobileCard).join("")}</div>` : ""}
        ${state.pagination.candidates.hasMore ? `<button class="load-more-button" type="button" data-action="load-more-candidates" ${state.pagination.candidates.loading ? "disabled" : ""}>${state.pagination.candidates.loading ? "正在读取…" : `加载更多短名单（已载入 ${fmt(all.length, 0)} / ${fmt(state.pagination.candidates.total, 0)}）`}</button>` : ""}
      </section>
      <div class="candidate-detail-host ${state.candidateDetailOpen ? "is-open" : ""}" role="${state.candidateDetailOpen ? "dialog" : "region"}" ${state.candidateDetailOpen ? 'aria-modal="true"' : ""} aria-label="候选详情">${candidateDetail(selected)}</div>
    </div>
    ${dualLowBatchOverview()}
    ${state.compare.length ? renderComparisonTray() : ""}`;
  $("#candidateRisk").value = state.candidateFilters.risk;
  $("#candidateRoute").value = state.candidateFilters.route;
  syncCandidateDialogA11y();
  if (state.candidateDetailOpen && restoreDialogFocus) {
    window.setTimeout(() => {
      const host = $(".candidate-detail-host.is-open");
      const focusTarget = (host ? $$('[data-action]', host) : []).find((element) => (
        element.dataset.action === restoreAction && (!restoreKey || element.dataset.key === restoreKey)
      )) || (host ? $(".candidate-detail-back", host) : null);
      focusTarget?.focus();
    }, 0);
  }
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
  const items = publishedEventItems();
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
    if (needle && !`${event.event_id || ""} ${event.issuer || ""} ${event.company || event.name || ""} ${event.code || event.symbol || ""} ${event.title || ""} ${event.source || ""}`.toLowerCase().includes(needle)) return false;
    return true;
  });
}

function eventTypeLabel(event) {
  const explicit = firstTextValue(event?.event_subtype, event?.category, event?.event_type);
  const title = String(event?.title || "").toLowerCase();
  if (/buyback|repurchase|回购/.test(title)) return "股份回购";
  if (/earnings|results|业绩|财报/.test(title)) return "业绩财报";
  if (/order|contract|订单|合同/.test(title)) return "订单合同";
  if (/regulat|investigation|监管|调查/.test(title)) return "监管事项";
  return explicit || "其他事件";
}

function eventAgeDays(event) {
  const published = Date.parse(event?.published_at || event?.effective_at || "");
  const generated = Date.parse(state.snapshot?.generated_at || "");
  if (!Number.isFinite(published) || !Number.isFinite(generated)) return null;
  return Math.max(0, Math.floor((generated - published) / 86_400_000));
}

function eventMaterialityLabel(event) {
  const ratio = firstFiniteValue(
    event?.amount_to_market_cap,
    event?.amount_to_revenue,
    event?.materiality_ratio,
  );
  if (Number.isFinite(Number(ratio))) return `${ratioPct(ratio, 2)} ${event?.amount_to_revenue != null ? "占营收" : "占市值"}`;
  const score = firstFiniteValue(event?.materiality_score, event?.impact_score);
  return Number.isFinite(Number(score)) ? `重要性 ${fmt(score, 1)}` : "重要性待量化";
}

function eventPriceReactionLabel(event) {
  const reaction = firstFiniteValue(event?.post_announcement_residual_move, event?.price_reaction_pct);
  if (Number.isFinite(Number(reaction))) {
    const normalized = Math.abs(Number(reaction)) <= 1 ? Number(reaction) * 100 : Number(reaction);
    return `公告后残差 ${pct(normalized, 1)}`;
  }
  if (event?.already_priced === true) return "可能已计价";
  if (event?.already_priced === false) return "尚未显示充分计价";
  return "价格反应待量化";
}

function eventExpiryLabel(event) {
  return firstTextValue(event?.expires_at, event?.expiry_at, event?.catalyst_expiry_date, event?.effective_until) || "有效期待发布";
}

function clusterEvents(events) {
  const clusters = new Map();
  for (const event of events || []) {
    const day = String(event.effective_at || event.published_at || "unknown").slice(0, 10);
    const issuer = String(event.symbol || event.company || "market").toUpperCase();
    const key = `${event.market || "unknown"}|${issuer}|${eventTypeLabel(event)}|${day}`;
    const existing = clusters.get(key);
    if (!existing) {
      clusters.set(key, {
        ...event,
        decision_bound: event.decision_bound === true,
        cluster_key: key,
        cluster_count: 1,
        cluster_event_ids: [event.event_id],
      });
      continue;
    }
    existing.cluster_count += 1;
    existing.cluster_event_ids.push(event.event_id);
    existing.decision_bound = existing.decision_bound === true || event.decision_bound === true;
    if (Date.parse(event.published_at || "") > Date.parse(existing.published_at || "")) {
      const count = existing.cluster_count;
      const ids = existing.cluster_event_ids;
      const decisionBound = existing.decision_bound;
      Object.assign(existing, event, {
        decision_bound: decisionBound,
        cluster_key: key,
        cluster_count: count,
        cluster_event_ids: ids,
      });
    }
  }
  return [...clusters.values()].sort((left, right) => Date.parse(right.published_at || "") - Date.parse(left.published_at || ""));
}

function renderEventDetail(event) {
  if (!event) return `<div class="empty-state">${icon("ph-cursor-click")}<h3>选择一条事件</h3><p>查看来源、时间、证据完整性与受影响证券。</p></div>`;
  const sourceValid = Boolean(event.source);
  const timeValid = Boolean(event.published_at || event.ingested_at);
  const eventUrl = safeHttpUrl(event.url);
  const urlValid = Boolean(eventUrl);
  const direction = normalizedDirection(event.direction);
  return `<article class="detail-panel event-detail"><header class="detail-header"><div><div class="eyebrow">${marketBadge(event.market)} ${esc(MARKET_META[event.market]?.label || event.market)} · ${esc(event.event_type)}</div><h2 class="detail-title">${esc(event.title)}</h2><p class="detail-subtitle">${esc(event.company || "行业事件")} ${event.symbol ? `· ${esc(event.symbol)}` : ""}</p></div>${badge(direction === "positive" ? "正面" : direction === "negative" ? "负面" : "中性 / 未知", direction === "positive" ? "positive" : direction === "negative" ? "negative" : "")}</header>
    <div class="event-score-strip event-fact-grid"><div><small>事件类型</small><strong>${esc(eventTypeLabel(event))}</strong></div><div><small>量化重要性</small><strong>${esc(eventMaterialityLabel(event))}</strong></div><div><small>来源时间</small><strong>${esc(dateTime(event.published_at))}</strong></div><div><small>事件年龄</small><strong>${eventAgeDays(event) === null ? "待发布" : `${fmt(eventAgeDays(event), 0)} 天`}</strong></div><div><small>价格反应</small><strong>${esc(eventPriceReactionLabel(event))}</strong></div><div><small>有效期</small><strong>${esc(eventExpiryLabel(event))}</strong></div></div>
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
    <div class="filter-strip"><div class="filter-group"><span>市场</span><div class="segmented-button"><button data-action="event-market" data-market="all" aria-pressed="${state.eventFilters.market === "all"}">全部</button>${MARKET_ORDER.map((market) => `<button data-action="event-market" data-market="${market}" aria-pressed="${state.eventFilters.market === market}">${MARKET_META[market].label}</button>`).join("")}</div></div><label>类型<select id="eventType"><option value="all">全部</option><option value="announcement_or_news">自动公告 / 新闻</option><option value="manual_external">人工核验</option><option value="model_signal">模型信号</option></select></label><label>方向<select id="eventDirection"><option value="all">全部</option><option value="positive">正面</option><option value="neutral">中性 / 未知</option><option value="negative">负面</option></select></label><label class="search-field">${icon("ph-magnifying-glass")}<input id="eventSearch" type="search" value="${esc(state.eventFilters.query)}" placeholder="搜索公司 / 代码" aria-label="搜索事件"></label></div>
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
  const production = productionDecisionTruth();
  const eventCoverage = state.snapshot?.global_decision?.event_coverage || {};
  const riskCoverage = eventCoverage.risk_screen || {};
  const positiveCoverage = eventCoverage.positive_event_enrichment || {};
  const productionRows = production.publishedQualifiedRows || [];
  const qualificationIds = new Set(productionRows.flatMap(({ primary }) => (
    primary.qualification_track === "quality_technical"
      ? []
      : primary.verified_positive_event_ids || []
  )));
  const qualificationTrackName = production.publishedPrimary
    ? qualificationTrackLabel(production.publishedPrimary.qualification_track)
    : "规则资格";
  const productionPrimaryKey = production.publishedPrimary
    ? `${production.publishedPrimary.market}:${String(production.publishedPrimary.code || production.publishedPrimary.symbol || "").toLowerCase()}`
    : "";
  const qualificationAudits = productionRows.map(({ primary }) => {
    const code = String(primary.code || primary.symbol || "");
    const rowKey = `${primary.market}:${code.toLowerCase()}`;
    const isPrimary = rowKey === productionPrimaryKey;
    const roleLabel = isPrimary ? "主候选" : "合格候选（非主候选）";
    const trackLabel = isPrimary ? qualificationTrackName : qualificationTrackLabel(primary.qualification_track);
    const eventIds = primary.verified_positive_event_ids || [];
    const identity = `Qualification ID ${primary.qualification_id || "--"}`;
    const heading = `${roleLabel} · ${trackLabel}：${primary.name || code} · 规则资格分 ${fmt(primary.qualification_score, 1)}`;
    if (primary.qualification_track === "quality_technical") {
      const observedEvents = eventIds.length
        ? `当前另有 ${eventIds.length} 条正向事件记录，但不是本通道必要条件：${eventIds.join(" · ")}`
        : "当前正向事件 ID 为 0 条";
      return `<div class="callout info section-callout production-event-audit-row">${icon("ph-seal-check")}<div><strong>${esc(heading)}</strong><br>全池结构化风险筛查通过当前规则；不等于官方确认不存在全部负面事件；本通道不要求正向催化深扫。质量趋势通道不绑定正向事件；${esc(observedEvents)}。<small>${esc(identity)} · 该摘要不改变 production.primary。</small></div></div>`;
    }
    return `<div class="callout info section-callout production-event-audit-row">${icon("ph-seal-check")}<div><strong>${esc(heading)}</strong><br>事件催化轨已绑定 ${fmt(eventIds.length, 0)} 条正向事件；event_id：${esc(eventIds.join(" · ") || "--")}。<small>${esc(identity)} · 只有这些已绑定证据参与该候选资格；规则资格分不是上涨概率。</small></div></div>`;
  }).join("");
  const automaticRaw = automaticEventFeed().sort((left, right) => (
    Number(right.decision_bound === true || qualificationIds.has(right.event_id))
    - Number(left.decision_bound === true || qualificationIds.has(left.event_id))
  ));
  const automatic = clusterEvents(automaticRaw).sort((left, right) => {
    const leftBound = left.decision_bound === true
      || (left.cluster_event_ids || []).some((id) => qualificationIds.has(id));
    const rightBound = right.decision_bound === true
      || (right.cluster_event_ids || []).some((id) => qualificationIds.has(id));
    return Number(rightBound) - Number(leftBound);
  });
  const resolvedQualificationIds = new Set(
    all.filter((event) => qualificationIds.has(event.event_id)).map((event) => event.event_id),
  );
  const externalCount = automaticExternalEvidenceCount();
  const publication = state.eventsPayload?.event_publication || {};
  const truncatedEventCount = num(publication.truncated, 0);
  const loadedEventCount = Array.isArray(state.eventsPayload?.events)
    ? state.eventsPayload.events.length
    : Array.isArray(state.eventsPayload?.events?.items) ? state.eventsPayload.events.items.length : 0;
  const filteredEventCount = num(state.eventsPayload?.total, loadedEventCount);
  const missingEvidence = all.filter((event) => !event.source || !(event.published_at || event.ingested_at)).length;
  let selected = rows.find((event) => event.event_id === state.eventKey)
    || rows.find((event) => automatic.some((item) => item.event_id === event.event_id))
    || rows.find((event) => event.event_type === "manual_external")
    || rows[0]
    || null;
  if (selected) state.eventKey = selected.event_id;
  const evidenceRow = (event, isAutomatic = false) => `<button class="verified-evidence-row ${event.event_id === state.eventKey ? "is-selected" : ""}" type="button" data-action="select-event" data-key="${esc(event.event_id)}"><time>${esc(dateTime(event.effective_at || event.published_at, false))}</time>${marketBadge(event.market)}<span><b>${esc(event.company || "行业事件")} · ${esc(event.symbol || "--")}</b><strong>${esc(eventTypeLabel(event))} · ${esc(eventMaterialityLabel(event))}${event.cluster_count > 1 ? ` · 合并 ${fmt(event.cluster_count, 0)} 条` : ""}</strong><small>${esc(event.source || "来源未保存")} · ${eventAgeDays(event) === null ? "年龄待发布" : `${fmt(eventAgeDays(event), 0)} 天`} · ${esc(eventPriceReactionLabel(event))} · 到期 ${esc(eventExpiryLabel(event))}</small></span><em>${isAutomatic ? "官方外部证据" : "人工核验"}</em><i>${isAutomatic ? "参与门禁" : "待入库"}</i></button>`;
  root.innerHTML = `
    <div class="principle-strip"><span><b>证据原则</b> 系统推断与外部事实分开记录；只有可访问原文、来源和发布时间的证据才能进入买入决策。</span><small>核验批次 · ${esc(state.snapshot?.target_date || "--")}</small></div>
    ${production.currentAction === "HISTORICAL_ONLY" ? `<div class="snapshot-execution-banner" role="alert">${icon("ph-warning-octagon")}<div><strong>快照已过期，事件只供历史研究</strong><span>历史规则候选与其绑定证据保留展示，不得触发当前执行。</span></div></div>` : ""}
    ${renderKpis([
      { icon: "ph-newspaper", label: "官方自动证据", value: fmt(externalCount, 0), tone: externalCount ? "positive" : "negative", meta: "自动入库且可参与门禁" },
      { icon: "ph-seal-check", label: "规则候选证据", value: `${fmt(resolvedQualificationIds.size, 0)} / ${fmt(qualificationIds.size, 0)}`, tone: qualificationIds.size > 0 && resolvedQualificationIds.size === qualificationIds.size ? "positive" : productionRows.length ? "warning" : "negative", meta: productionRows.length ? `${fmt(productionRows.length, 0)} 只${production.qualified ? "当前" : "历史发布"}规则合格候选 · 已解析 ${fmt(resolvedQualificationIds.size, 0)} / ${fmt(qualificationIds.size, 0)} 个绑定 event_id${production.qualified ? "" : " · 不可执行"}` : "本轮无规则合格候选" },
      { icon: "ph-cpu", label: "模型信号", value: fmt(modelSignals.length, 0), meta: "系统生成，不等于外部证据" },
      { icon: "ph-user-check", label: "人工核验待入库", value: fmt(manual.length, 0), tone: "warning", meta: "仅研究提示，不参与自动决策" },
      { icon: "ph-warning-octagon", label: "数据状态", value: externalCount ? "待复核" : "严重缺口", tone: externalCount ? "warning" : "negative", meta: missingEvidence ? `${missingEvidence} 条来源或时间缺失` : "事件因子不可独立支撑买入" },
    ])}
    ${eventCoverage.contract_version === "two-tier-event-coverage-v1" ? `<section class="two-tier-event-coverage" aria-label="事件双层覆盖口径"><article><span>全池结构化风险筛查</span><strong>${fmt(riskCoverage.evaluated_candidate_count, 0)} 只</strong><p>PASS ${fmt(riskCoverage.pass_count, 0)} · BLOCKED ${fmt(riskCoverage.blocked_count, 0)} · INCOMPLETE ${fmt(riskCoverage.incomplete_count, 0)}</p><small>覆盖标题与结构化元数据；PASS 不等于官方确认“绝无负面”。</small></article><article><span>优先样本正向事件深扫</span><strong>${fmt(positiveCoverage.scanned_candidate_count, 0)} 只</strong><p>有正向证据 ${fmt(positiveCoverage.with_positive_count, 0)} · 未命中 ${fmt(positiveCoverage.scanned_no_positive_count, 0)} · 未选深扫 ${fmt(positiveCoverage.not_selected_count, 0)}</p><small>只对有界优先样本核验正文，不代表完整扫描池都有催化。</small></article></section>` : ""}
    ${productionRows.length ? `<section class="production-event-audit-list" aria-label="全部规则合格候选通道审计">${qualificationAudits}</section>` : ""}
    ${(publication.total || loadedEventCount) ? `<div class="callout info section-callout">${icon("ph-database")}<div><strong>事件资产已按时点有界发布</strong><br>源快照 ${fmt(publication.total, 0)} 条 · 发布 ${fmt(publication.published, 0)} 条 · 当前筛选匹配 ${fmt(filteredEventCount, 0)} 条 · 已载入 ${fmt(loadedEventCount, 0)} 条${truncatedEventCount > 0 ? ` · 裁剪 ${fmt(truncatedEventCount, 0)} 条` : ""}；决策绑定证据按绑定优先发布。</div></div>` : ""}
    <div class="callout warning section-callout">${icon("ph-warning-circle")}<div><strong>模型信号 ≠ 外部事件证据</strong><br>model_signal 只是系统推断，不能替代公告、财报、监管文件或权威新闻；没有原文链接时，“查看证据原文”必须禁用。</div></div>
    <section class="panel evidence-feed-panel"><header class="panel-header"><div><h3 class="panel-title">事件聚合 · 已自动入库</h3><p class="panel-subtitle">${automaticRaw.length} 条原始证据聚合为 ${automatic.length} 组 · 按公司、事件类型与生效日期去重</p></div></header><div class="verified-evidence-list">${automatic.map((event) => evidenceRow(event, true)).join("") || `<div class="empty-state compact">${icon("ph-newspaper-clipping")}<h3>暂无自动准入证据</h3><p>当前不会用模型信号或人工笔记替代。</p></div>`}</div><div class="model-signal-title"><span>已人工核验 · 待自动入库（${manual.length} 条）</span></div><div class="verified-evidence-list">${manual.map((event) => evidenceRow(event, false)).join("") || `<div class="empty-state compact"><p>暂无人工核验证据</p></div>`}</div><div class="model-signal-title"><span>系统模型信号 · 非外部证据</span></div><div class="model-signal-grid">${modelSignals.map((event) => `<article><header><span>${esc(event.title)}</span><span class="status-pill primary">非外部</span></header><p>${esc(event.source || "系统生成")} · 无可访问原文</p></article>`).join("")}</div>${state.pagination.events.hasMore ? `<button class="load-more-button" type="button" data-action="load-more-events" ${state.pagination.events.loading ? "disabled" : ""}>${state.pagination.events.loading ? "正在读取…" : `加载更多事件（第 ${fmt(state.pagination.events.page, 0)} 页）`}</button>` : ""}</section>
    <section class="evidence-bottom-grid"><div>${renderEventDetail(selected)}</div><article class="panel evidence-rules"><header class="panel-header"><div><h3 class="panel-title">证据准入规则</h3><p class="panel-subtitle">任何一项缺失，都不能升级为自动买入依据</p></div></header><ol><li>可访问原文或监管文件</li><li>记录来源、发布时间与生效时间</li><li>区分事实、模型推断与人工判断</li><li>计算相关性、新颖度与已计价程度</li><li>失效或过期后自动退出决策窗口</li></ol><strong>任一关键字段缺失，事件因子只能降级为研究提示。</strong></article></section>
    <details class="event-audit" ${state.eventAuditOpen ? "open" : ""}><summary>${icon("ph-list-magnifying-glass")} 查看全部事件与模型信号（${all.length} 条）</summary><div class="history-archive-body"><div class="filter-strip"><div class="filter-group"><span>市场</span><div class="segmented-button"><button data-action="event-market" data-market="all" aria-pressed="${state.eventFilters.market === "all"}">全部</button>${MARKET_ORDER.map((market) => `<button data-action="event-market" data-market="${market}" aria-pressed="${state.eventFilters.market === market}">${MARKET_META[market].label}</button>`).join("")}</div></div><label>类型<select id="eventType"><option value="all">全部</option><option value="announcement_or_news">自动公告 / 新闻</option><option value="manual_external">人工核验</option><option value="model_signal">模型信号</option></select></label><label>方向<select id="eventDirection"><option value="all">全部</option><option value="positive">正面</option><option value="neutral">中性 / 未知</option><option value="negative">负面</option></select></label><label class="search-field">${icon("ph-magnifying-glass")}<input id="eventSearch" type="search" value="${esc(state.eventFilters.query)}" placeholder="搜索公司 / 代码" aria-label="搜索事件"></label></div><div class="event-master-list">${rows.map((event) => { const direction = normalizedDirection(event.direction); return `<button class="event-master-row ${event.event_id === state.eventKey ? "is-selected" : ""}" type="button" data-action="select-event" data-key="${esc(event.event_id)}"><time>${esc(dateTime(event.published_at || event.ingested_at, false))}</time>${marketBadge(event.market)}<span><b>${esc(event.company || "行业事件")}</b><strong>${esc(event.title)}</strong><small>${esc(event.source || "来源未保存")}</small></span><em class="${direction === "positive" ? "positive" : direction === "negative" ? "negative" : "muted"}">${fmt(event.impact_score, 1)}</em></button>`; }).join("")}</div></div></details>`;
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

function historyProductionStatusTag(item) {
  const decision = item?.production_decision;
  const primary = decision?.primary;
  if (decision?.action === "QUALIFIED_PICK" && primary) {
    return `<span class="status-pill positive" title="规则资格历史轨；资格分不是概率">${qualificationTrackLabel(primary.qualification_track)}·${fmt(primary.qualification_score, 1)}分</span>`;
  }
  if (decision?.action === "NO_QUALIFIED_PICK") {
    return `<span class="status-pill muted" title="该日没有候选通过生产规则门禁">规则未通过</span>`;
  }
  return "";
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
    const productionPrimary = item.production_decision?.action === "QUALIFIED_PICK" ? item.production_decision?.primary : null;
    if (state.historyAction === "buy" && !summary.has_primary && !hasOfficialPrimary && !productionPrimary) return false;
    if (state.historyAction === "no_trade" && (summary.has_primary || hasOfficialPrimary || productionPrimary)) return false;
    if (needle && !`${item.target_date || ""} ${item.signal_date || ""} ${item.generated_at || ""} ${historyKindLabel(item)} ${summary.name || ""} ${summary.code || ""} ${productionPrimary?.name || ""} ${productionPrimary?.code || ""}`.toLowerCase().includes(needle)) return false;
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
  const productionPrimary = item.production_decision?.action === "QUALIFIED_PICK" ? item.production_decision?.primary : null;
  const productionTrackName = productionPrimary
    ? qualificationTrackLabel(productionPrimary.qualification_track)
    : "规则资格";
  const productionPositiveEventIds = Array.isArray(productionPrimary?.verified_positive_event_ids)
    ? productionPrimary.verified_positive_event_ids
    : [];
  const productionEventAudit = productionPrimary?.qualification_track === "quality_technical" && productionPositiveEventIds.length === 0
    ? "全池结构化风险筛查通过当前规则；不等于官方确认不存在全部负面事件；本通道不要求正向催化深扫"
    : productionPositiveEventIds.length
      ? `已绑定 ${productionPositiveEventIds.length} 条正向事件：${productionPositiveEventIds.join(" · ")}`
      : "旧版快照未保存绑定事件明细";
  const headerScope = productionPrimary ? "生产规则资格" : globalContract ? "跨市场动作" : MARKET_META[state.historyMarket].label;
  const headerName = productionPrimary?.name || globalPrimary?.name || (globalAbstained ? "本轮主动放弃" : summary.name || "本轮无 Legacy 首选");
  const shadowStatus = shadowOutcomeStatus(item);
  const shadowEvidence = shadowStatus ? `<div class="callout info">${icon("ph-flask")}<div><strong>${shadowStatus === "PENDING" ? "Shadow·PENDING" : "Shadow·SETTLED"}</strong><br>这是 research_priority 的影子研究台账，仅用于验证研究排序；不计入可执行绩效、胜率或收益。${item.shadow_outcome?.prediction_id ? ` Prediction ID：${esc(item.shadow_outcome.prediction_id)}。` : ""}</div></div>` : "";
  const officialEvidence = globalPrimary ? `<div class="detail-section"><div class="section-heading"><h3>正式十日预测</h3>${historyFormalStatusTag(item)}</div><div class="detail-score-grid"><div><small>全局首选</small><strong>${esc(globalPrimary.name || "--")}</strong><span>${esc(globalPrimary.market || "--")} · ${esc(globalPrimary.code || globalPrimary.symbol || "--")}</span></div><div><small>P(R10 &gt; 0)</small><strong>${globalPrimary.probability == null ? "--" : `${fmt(num(globalPrimary.probability) * 100, 1)}%`}</strong><span>已校准模型概率</span></div><div><small>Prediction ID</small><strong class="mono">${esc(globalPrimary.prediction_id || "--")}</strong><span>${esc(globalPrimary.model_id || "--")}</span></div><div><small>Label</small><strong>${esc(globalPrimary.label_version || "--")}</strong><span>结算必须完全匹配</span></div></div></div>` : "";
  const productionEvidence = productionPrimary ? `<div class="detail-section"><div class="section-heading"><h3>生产规则资格记录</h3>${historyProductionStatusTag(item)}</div><div class="detail-score-grid"><div><small>规则候选</small><strong>${esc(productionPrimary.name || "--")}</strong><span>${esc(productionPrimary.market || "--")} · ${esc(productionPrimary.code || productionPrimary.symbol || "--")}</span></div><div><small>资格通道</small><strong>${esc(productionTrackName)}</strong><span>确定性规则，不是概率</span></div><div><small>规则资格分</small><strong>${fmt(productionPrimary.qualification_score, 1)} 分</strong><span>非上涨概率</span></div><div><small>Qualification ID</small><strong class="mono">${esc(productionPrimary.qualification_id || item.qualification_id || "--")}</strong><span>${esc(productionPrimary.rule_model_id || item.production_decision?.rule_model_id || "规则模型版本未保存")}</span></div><div><small>10 日风险收益</small><strong>${fmt(productionPrimary.risk_reward?.ratio, 2)}</strong><span>${fmt(productionPrimary.estimated_10d_range?.low_pct, 1)}% ~ +${fmt(productionPrimary.estimated_10d_range?.high_pct, 1)}%</span></div></div><p class="fine-print">${esc(productionEventAudit)}。该记录用于后续独立复盘；规则资格分不包装成概率，也不进入校准模型的 Brier、ECE、胜率或收益分母。</p></div>` : "";
  return `<article class="detail-panel history-detail"><header class="detail-header"><div><div class="eyebrow">${historyKindLabel(item)} 档案 · ${esc(itemKey || "--")}</div><h2 class="detail-title">${esc(headerScope)} · ${esc(headerName)}</h2><p class="detail-subtitle">信号日 ${esc(item.signal_date || "--")} · ${historyTargetLabel(item)} ${esc(item.target_date || "--")} · 生成 ${esc(dateTime(item.generated_at))}</p></div><div class="history-row-statuses">${historyProductionStatusTag(item)}${historyFormalStatusTag(item)}${shadowOutcomeTag(item)}</div></header>
    ${productionEvidence}
    ${officialEvidence}
    ${shadowEvidence}
    <div class="detail-score-grid"><div><small>标的</small><strong>${esc(summary.name || "无")}</strong><span>${esc(summary.code || "--")}</span></div><div><small>Legacy 推荐度</small><strong>${fmt(summary.recommendation_degree ?? summary.confidence, 0)}</strong><span>规则分，非概率</span></div><div><small>参考价</small><strong>${price(summary.entry_price)}</strong><span>当时快照，不代表成交</span></div><div><small>${rangeLabel}</small><strong>${esc(summary.estimated_2w_range || summary.estimated_2d_range || "--")}</strong><span>${rangeNote}</span></div></div>
    <div class="callout warning">${icon("ph-warning-circle")}<div><strong>${globalContract ? `同日全局动作：${esc(item.global_decision?.action || "--")}；下方为独立 Legacy 市场档案` : "Legacy 规则档案，不属于 global-10d-v1 绩效样本"}</strong><br>下方 Legacy 记录只保存当时规则证据，因此不展示“命中率”或伪造收益；正式收益仅来自上方通过合同校验的外部结算账本。</div></div>
    ${candidate ? `<div class="detail-section"><div class="section-heading"><h3>完整快照证据</h3><span>已载入</span></div>${factorCards(candidate)}<ul class="evidence-list">${(candidate.reasons || []).slice(0, 5).map((reason) => `<li><h4>${esc(reason)}</h4></li>`).join("")}</ul></div>` : item.full_snapshot_available === false ? `<div class="callout info">${icon("ph-archive-box")}<div><strong>历史摘要与账本仍可审计</strong><br>为控制 Worker 体积，完整交互快照仅保留最近 30 个决策日；该日的固化摘要和结果账本未被删除。</div></div>` : `<div class="detail-section"><button class="primary-button" type="button" data-action="load-history" data-key="${esc(item.snapshot_key || item.cache_key)}">${icon("ph-download-simple")}载入完整快照证据</button></div>`}
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
    <div class="history-overview-grid"><article class="chart-card"><header class="chart-header"><div><h3 class="chart-title">推荐度轨迹</h3><p class="chart-subtitle">按生成时间排列；空值不补齐</p></div>${badge(MARKET_META[state.historyMarket].label, "primary")}</header><div class="chart-shell history-chart-shell"><canvas id="historyChart" aria-label="历史推荐度趋势" aria-describedby="historyChartSummary"></canvas><table id="historyChartSummary" class="visually-hidden chart-data-summary"><caption>历史推荐度摘要</caption><tbody><tr><th>市场</th><td>${esc(MARKET_META[state.historyMarket].label)}</td></tr><tr><th>快照数</th><td>${fmt(rows.length, 0)}</td></tr><tr><th>平均推荐度</th><td>${Number.isFinite(average) ? fmt(average, 1) : "不可用"}</td></tr></tbody></table></div></article><article class="panel"><header class="panel-header"><div><h3 class="panel-title">复盘口径</h3><p class="panel-subtitle">事实、推断和待验证数据分开</p></div></header><ul class="evidence-list"><li><h4>事实</h4><p>快照时间、当时首选、推荐度、入场 / 止损 / 目标位。</p></li><li><h4>尚未接入</h4><p>统一复权收益、盘中是否成交、滑点、分红和不同市场交易日历。</p></li><li><h4>因此不展示</h4><p>未经校准的胜率、Alpha 与“历史命中”宣传数字。</p></li></ul></article></div>
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

function renderObservationLedgerPanel(observationLedger, observationPerformance) {
  const contractPublished = observationPerformance?.schema_version === "model-observation-performance-v1"
    && observationPerformance?.track === "MODEL_OBSERVATION";
  const ledgerAvailable = observationLedger?.track === "MODEL_OBSERVATION";
  const status = contractPublished
    ? String(observationPerformance.status || "UNSETTLED").toUpperCase()
    : "CONTRACT UNAVAILABLE";
  const tone = status === "OBSERVING"
    ? "primary"
    : ["EARLY_SAMPLE", "PENDING_MATURITY", "PENDING_DATA", "UNSETTLED"].includes(status)
      ? "warning"
      : status === "NO_SAMPLE" ? "muted" : "negative";
  const countValue = (field) => contractPublished ? fmt(Math.max(0, num(observationPerformance[field])), 0) : "—";
  const cohortCount = contractPublished
    ? Math.max(0, num(observationPerformance.cohort_count))
    : Math.max(0, num(observationLedger?.cohort_count));
  const predictionCount = contractPublished
    ? Math.max(0, num(observationPerformance.prediction_count))
    : Math.max(0, num(observationLedger?.canonical_prediction_count));
  const revisions = Math.max(0, num(observationLedger?.revision_count));
  const independentDays = Math.max(0, num(observationPerformance?.independent_cohort_day_count));
  const minimumDays = Math.max(0, num(observationPerformance?.minimum_reliable_independent_cohort_days));
  const untracked = Math.max(0, num(observationPerformance?.untracked_count));
  const invalidCount = ["invalid_cohort_count", "invalid_batch_count", "invalid_outcome_count"]
    .reduce((total, field) => total + Math.max(0, num(observationPerformance?.[field])), 0);
  const authorizationStatus = contractPublished
    ? String(observationPerformance.authorization_status || "DIAGNOSTIC_ONLY").toUpperCase()
    : "DIAGNOSTIC_CONTRACT_UNAVAILABLE";
  const isolated = contractPublished
    && observationPerformance.included_in_shadow_research === false
    && observationPerformance.included_in_executable_performance === false
    && observationPerformance.authorizes_production === false;
  const statusCopy = !contractPublished
    ? "服务端尚未发布模型观察绩效合同；缺失值不会被解释为 0。"
    : status === "PENDING_MATURITY"
      ? "观察结果正在等待第 10 个交易日成熟。"
      : status === "PENDING_DATA"
        ? "部分观察已到期，但行情或复权数据尚不完整。"
        : status === "EARLY_SAMPLE"
          ? `已有结算样本，但仅覆盖 ${fmt(independentDays, 0)} / ${fmt(minimumDays, 0)} 个独立 cohort 日。`
          : status === "OBSERVING"
            ? `诊断样本覆盖 ${fmt(independentDays, 0)} 个独立 cohort 日，仍只用于模型观察。`
            : status === "NO_SAMPLE"
              ? "当前没有可登记的模型观察样本。"
              : "观察记录尚未形成可用结算诊断。";
  const ledgerCopy = ledgerAvailable
    ? `台账共 ${fmt(cohortCount, 0)} 个 cohort、${fmt(predictionCount, 0)} 条预测、${fmt(revisions, 0)} 次 revisions。`
    : "观察台账合同暂不可用。";
  const diagnosticCopy = contractPublished
    ? `未跟踪 ${fmt(untracked, 0)} · 无效诊断 ${fmt(invalidCount, 0)}。`
    : "结算计数暂不可用。";
  const isolationCopy = isolated
    ? "该观察诊断不进入正式绩效，也不进入 Shadow research_priority，不授权生产执行。"
    : "隔离字段不完整，前端拒绝将该诊断并入正式绩效或解释为生产授权。";
  return `<section class="panel shadow-evaluation-panel"><header class="panel-header"><div><h3 class="panel-title">模型观察轨</h3><p class="panel-subtitle">每天 22:47 固化全部点时预测，并以独立观察合同跟踪成熟、数据缺口与结算结果</p></div><span class="status-pill ${tone}" title="${esc(authorizationStatus)}">${esc(status)}</span></header><div class="shadow-ledger-grid"><div><small>cohort / 预测</small><strong>${contractPublished ? `${fmt(cohortCount, 0)} / ${fmt(predictionCount, 0)}` : "—"}</strong><span>${esc(ledgerCopy)}</span></div><div><small>PENDING_MATURITY</small><strong>${countValue("pending_maturity_count")}</strong><span>尚未走满预测窗口</span></div><div><small>PENDING_DATA</small><strong>${countValue("pending_data_count")}</strong><span>已到期但结算证据不完整</span></div><div><small>SETTLED</small><strong>${countValue("settled_count")}</strong><span>${esc(diagnosticCopy)}</span></div></div><footer>${icon("ph-database")}<span><b>${esc(authorizationStatus)}</b> · ${esc(statusCopy)} ${esc(isolationCopy)}</span></footer></section>`;
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
  const observationLedger = meta.observation_ledger && typeof meta.observation_ledger === "object" ? meta.observation_ledger : {};
  const observationPerformance = meta.observation_performance && typeof meta.observation_performance === "object"
    ? meta.observation_performance
    : {};
  const rawRuns = num(meta.raw_run_count, state.history.length);
  const decisionDays = num(meta.decision_day_count, state.history.length);
  const duplicateRuns = num(meta.duplicate_run_count, Math.max(0, rawRuns - decisionDays));
  const contractDays = num(meta.global_contract_day_count);
  const legacyDays = num(meta.legacy_day_count, Math.max(0, decisionDays - contractDays));
  const executable = num(meta.executable_prediction_count);
  const noValidPickDays = num(meta.no_valid_pick_day_count);
  const qualifiedRuleDays = num(meta.qualified_rule_day_count);
  const noQualifiedRuleDays = num(meta.no_qualified_rule_day_count);
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
  const hasMatureMetrics = sampleStatus !== "NO_SAMPLE";
  const metricsExpandedByDefault = sampleStatus === "READY";
  const reliabilityDayThreshold = Math.max(60, num(performance.minimum_reliable_independent_days, 60));
  const observationPredictionCount = num(observationLedger.prediction_count, 0);
  const observationPendingMaturity = num(observationLedger.pending_maturity_count, observationPerformance.pending_maturity_count);
  const observationSettled = num(observationLedger.settled_count, observationPerformance.settled_count);
  const reliabilityProgress = clamp(cohortIndependentDays / Math.max(1, reliabilityDayThreshold) * 100);
  const maturityDate = firstTextValue(
    observationLedger.first_maturity_date,
    observationPerformance.first_maturity_date,
    meta.rule_outcome_tracking?.first_maturity_date,
  );
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
  const coverageSentence = `${fmt(rawRuns, 0)} 次原始运行已合并为 ${fmt(decisionDays, 0)} 个决策日；${fmt(contractDays, 0)} 日属于 global-10d-v1，${fmt(qualifiedRuleDays, 0)} 日发布规则合格候选，${fmt(legacyDays, 0)} 日仅为 Legacy 档案。${cohortSentence}`;
  const latestRuleItem = state.history.find((item) => item.production_decision?.action === "QUALIFIED_PICK" && item.production_decision?.primary);
  const latestRulePrimary = latestRuleItem?.production_decision?.primary;
  root.innerHTML = `
    <div class="principle-strip"><span><b>评估原则</b> 校准可执行绩效、规则资格历史与 Shadow 研究轨三者分开；所有绩效指标只读取后端发布的合法结算合同。</span><small class="${performanceState.tone}">${esc(performance.schema_version || "PERFORMANCE_CONTRACT_MISSING")}</small></div>
    <section class="evaluation-not-ready is-${esc(sampleStatus.toLowerCase())}">
      <div><span class="status-pill ${performanceState.tone}">${esc(performanceState.label)}</span>${sampleStatus === "EARLY_SAMPLE" ? `<span class="status-pill warning early-sample-badge">早期样本</span>` : ""}<h2>${esc(performanceState.title)}</h2><p>${esc(coverageSentence)}</p><strong>${esc(cohortCopy)}</strong></div>
      <aside><h3>正式样本门槛</h3><ol><li>仅限 global-10d-v1 可执行预测</li><li>按不可变 prediction_id 去重</li><li>进出场、费用、复权与日历必须完整</li><li>NO_VALID_PICK 是主动放弃，不计为亏损</li><li>Shadow 研究轨永不进入正式分母</li></ol></aside>
    </section>
    <section class="history-maturity-progress" aria-labelledby="historyMaturityTitle">
      <header><div><span>真实结果积累进度</span><h2 id="historyMaturityTitle">先走满 10 个交易日，再评价模型</h2></div><strong>${fmt(cohortIndependentDays, 0)} / ${fmt(reliabilityDayThreshold, 0)} 个独立样本日</strong></header>
      <div class="maturity-progress-track" role="progressbar" aria-label="距离可靠性门槛的进度" aria-valuemin="0" aria-valuemax="${fmt(reliabilityDayThreshold, 0)}" aria-valuenow="${fmt(Math.min(cohortIndependentDays, reliabilityDayThreshold), 0)}"><span style="width:${reliabilityProgress}%"></span></div>
      <div class="maturity-progress-grid"><div><small>点时预测</small><b>${fmt(observationPredictionCount, 0)}</b><span>不可变登记</span></div><div><small>等待成熟</small><b>${fmt(observationPendingMaturity, 0)}</b><span>预测窗 10 个交易日</span></div><div><small>已结算</small><b>${fmt(observationSettled, 0)}</b><span>完整价格证据</span></div><div><small>首批成熟日期</small><b>${esc(maturityDate || "等待日历合同")}</b><span>不提前填充收益</span></div><div><small>可靠性门槛</small><b>${fmt(reliabilityDayThreshold, 0)} 日</b><span>独立样本日，不是运行次数</span></div></div>
    </section>
    <div class="callout info">${icon("ph-seal-check")}<div><strong>规则资格历史轨：${fmt(qualifiedRuleDays, 0)} 个合格决策日</strong><br>${latestRulePrimary ? `最近记录为 ${esc(latestRulePrimary.name || latestRulePrimary.code)}（${esc(latestRulePrimary.code || "--")}），资格分 ${fmt(latestRulePrimary.qualification_score, 1)}；点击下方每日档案查看资格证据与 ID。` : `当前有 ${fmt(noQualifiedRuleDays, 0)} 个决策日明确记录为无规则合格候选。`} 该轨尚不计算胜率或收益，不会混入校准概率绩效。</div></div>
    ${renderKpis([
      { icon: "ph-files", label: "原始运行", value: fmt(rawRuns, 0), meta: "全部不可变运行记录" },
      { icon: "ph-calendar-dots", label: "决策日", value: fmt(decisionDays, 0), meta: `已合并 ${fmt(duplicateRuns, 0)} 次日内重复` },
      { icon: "ph-seal-check", label: "正式合同日", value: fmt(contractDays, 0), tone: contractDays ? "primary" : "negative", meta: "global-10d-v1" },
      { icon: "ph-check-fat", label: "规则合格日", value: fmt(qualifiedRuleDays, 0), tone: qualifiedRuleDays ? "positive" : "warning", meta: "production-rule-10d-v1 · 非概率" },
      { icon: "ph-archive", label: "Legacy 历史日", value: fmt(legacyDays, 0), tone: "warning", meta: "仅作规则档案" },
      { icon: "ph-crosshair", label: "可执行预测", value: fmt(executable, 0), meta: `当前 cohort ${fmt(cohortIndependentDays, 0)} 个独立决策日` },
      { icon: "ph-hourglass", label: "待结算", value: fmt(pending, 0), meta: "正式预测 PENDING" },
      { icon: "ph-check-circle", label: "已结算样本", value: fmt(settled, 0), tone: settled ? "positive" : "negative", meta: "完整 outcome 合同" },
      { icon: "ph-prohibit", label: "主动放弃日", value: fmt(noValidPickDays, 0), meta: "NO_VALID_PICK 不算亏损" },
    ])}
    <div class="evaluation-tabs" aria-label="评估维度"><button class="is-active" type="button">10日表现</button><button type="button" disabled>概率校准</button><button type="button" disabled>分市场表现</button><button type="button" disabled>版本对比</button><button type="button" disabled>失效分析</button><span>真实合同指标 · 非浏览器回填 · 非模拟收益</span></div>
    <details class="history-metrics-details ${sampleStatus === "NO_SAMPLE" ? "is-no-sample" : ""}" ${metricsExpandedByDefault ? "open" : ""}><summary>${icon("ph-chart-bar")}<span>${hasMatureMetrics ? "查看指标定义" : "指标将在样本成熟后显示"}</span><small>${fmt(HISTORY_PERFORMANCE_METRICS.length, 0)} 项 · ${hasMatureMetrics ? performanceState.label : "当前先展示积累进度"}</small>${icon("ph-caret-down")}</summary>${hasMatureMetrics ? `<section class="evaluation-metric-grid">${HISTORY_PERFORMANCE_METRICS.map((definition) => renderHistoryMetric(definition, metrics, performance)).join("")}</section>` : `<div class="maturity-metrics-placeholder">${icon("ph-hourglass")}<p>首批预测尚未走满 10 个交易日，因此不展示空指标网格，也不会把缺失值解释为 0。</p></div>`}</details>
    ${renderShadowResearchPanel(shadowLedger)}
    ${renderObservationLedgerPanel(observationLedger, observationPerformance)}
    <section class="panel evaluation-method"><header class="panel-header"><div><h3 class="panel-title">历史检验如何回答“今天买哪只更可能在两周内赚得最多”</h3><p class="panel-subtitle">评估既看收益排序，也看概率是否可信、风险是否可承受</p></div></header><div><article><b>01｜点时数据</b><p>当时可见的候选池、价格与事件，禁止未来函数。</p></article><article><b>02｜净超额收益</b><p>股票复权收益减固定市场成本，再减同期宽基净收益；个性化成本尚未接入。</p></article><article><b>03｜排名检验</b><p>逐日检验 Spearman IC、Top 10%、Top 1 和尾部损失。</p></article><article><b>04｜失效分析</b><p>按市场、行情状态、成本和事件类型拆解。</p></article></div></section>
    <details class="history-archive" ${state.historyArchiveOpen ? "open" : ""}><summary>${icon("ph-archive")} 查看每日决策快照（${hasMore ? `已载入 ${fmt(returned, 0)} / ` : ""}${fmt(decisionDays, 0)} 个决策日）</summary><div class="history-archive-body">
      <div class="callout info">${icon("ph-info")}<div><strong>${fmt(rawRuns, 0)} 次原始运行 → ${fmt(decisionDays, 0)} 个每日代表快照</strong><br>同一 target_date 优先展示正式 global-10d 合同，同类保留最后一次运行；绩效另限定当前模型与标签版本，并在每个 target_date 只保留最晚发布的可执行预测。</div></div>
      <div class="filter-strip"><div class="filter-group"><span>市场</span><div class="segmented-button">${MARKET_ORDER.map((market) => `<button data-action="history-market" data-market="${market}" aria-pressed="${state.historyMarket === market}">${MARKET_META[market].label}</button>`).join("")}</div></div><label>动作<select id="historyAction"><option value="all">全部</option><option value="buy">有首选 / 规则合格</option><option value="no_trade">不交易</option></select></label><label class="search-field">${icon("ph-magnifying-glass")}<input id="historySearch" type="search" value="${esc(state.historyQuery)}" placeholder="搜索日期 / 公司 / 代码" aria-label="搜索历史"></label></div>
      <div class="master-detail history-master-detail"><section class="panel"><header class="panel-header"><div><h3 class="panel-title">每日档案列表</h3><p class="panel-subtitle">规则资格、正式预测与 Shadow 研究状态独立展示</p></div></header>${rows.length ? `<div class="snapshot-list">${rows.map((item) => { const summary = historyMarketSummary(item); const official = item.global_decision?.primary; const productionPrimary = item.production_decision?.action === "QUALIFIED_PICK" ? item.production_decision?.primary : null; const globalAbstained = historyKind(item) === "global_10d_v1" && String(item.global_decision?.action || "").toUpperCase() === "NO_VALID_PICK"; const key = item.snapshot_key || item.cache_key; const displayName = productionPrimary?.name || official?.name || (globalAbstained ? "本轮主动放弃" : summary.name || "本轮无 Legacy 首选"); const displayCode = productionPrimary?.code || productionPrimary?.symbol || official?.code || official?.symbol || (globalAbstained ? item.global_decision?.blocker_codes?.[0] || "NO_VALID_PICK" : summary.code || summary.message || "无首选"); const displayScore = productionPrimary ? `${fmt(productionPrimary.qualification_score, 1)}分` : official ? `${fmt(num(official.probability) * 100, 0)}%` : summary.has_primary && !globalAbstained ? fmt(summary.recommendation_degree ?? summary.confidence, 0) : "NO"; return `<button class="snapshot-row ${key === state.historyKey ? "is-selected" : ""}" type="button" data-action="select-history" data-key="${esc(key)}"><time>${historyTargetLabel(item, true)} ${esc(item.target_date || "--")}<small>信号 ${esc(item.signal_date || "--")} · ${esc(dateTime(item.generated_at, false))}</small></time><span><b>${esc(displayName)}</b><small>${esc(historyKindLabel(item))} · ${esc(displayCode)}</small><span class="history-row-statuses">${historyProductionStatusTag(item)}${historyFormalStatusTag(item)}${shadowOutcomeTag(item)}</span></span><strong>${displayScore}</strong>${icon("ph-caret-right")}</button>`; }).join("")}</div>` : `<div class="empty-state">${icon("ph-funnel-x")}<h3>没有匹配快照</h3></div>`}${state.pagination.history.hasMore ? `<button class="load-more-button" type="button" data-action="load-more-history" ${state.pagination.history.loading ? "disabled" : ""}>${state.pagination.history.loading ? "正在读取…" : `加载更早档案（第 ${fmt(state.pagination.history.page, 0)} 页）`}</button>` : ""}</section><div>${historyDetail(selected)}</div></div>
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

function renderTenDayModelCard(modelState = tenDayModelState()) {
  const model = modelState.model || {};
  const presentation = tenDayModelPresentation(modelState);
  const validation = tenDayModelValidation(model);
  const provenance = String(model.training_provenance || "");
  const currentUniverseBackfill = provenance === "current_universe_historical_backfill";
  const predictionCount = firstFiniteModelMetric(model, ["shadow_prediction_count", "prediction_count"])
    ?? (Array.isArray(model.shadow_predictions) ? model.shadow_predictions.length : null);
  const marketModels = model.market_models && typeof model.market_models === "object" ? model.market_models : {};
  const marketRows = MARKET_ORDER.map((market) => {
    const marketModel = marketModels[market] || {};
    const marketValidation = tenDayModelValidation({ validation: marketModel.validation || marketModel });
    const status = String(marketModel.status || "UNAVAILABLE").toUpperCase();
    return `<div><span>${esc(MARKET_META[market].label)}</span><b>${esc(status)}</b><small>留出日 ${marketValidation.heldOutDays === null ? "--" : fmt(marketValidation.heldOutDays, 0)} · Brier Skill ${marketValidation.brierSkill === null ? "--" : ratioPct(marketValidation.brierSkill, 2)} · Top10 超额 ${marketValidation.topExcess === null ? "--" : ratioPct(marketValidation.topExcess, 2)}</small></div>`;
  }).join("");
  const limitations = Array.isArray(model.limitations) ? model.limitations.map((item) => String(item)).filter(Boolean) : [];
  const reasonCopy = presentation.reasonCodes.length
    ? `<div class="shadow-model-reasons"><small>原因码</small><code>${esc(presentation.reasonCodes.join(" · "))}</code></div>`
    : "";
  return `<section class="panel shadow-model-card" data-model-status="${esc(modelState.status || "UNAVAILABLE")}">
    <header class="panel-header"><div><h3 class="panel-title">${esc(presentation.title)}</h3><p class="panel-subtitle">影子证据与正式决策权限分开发布</p></div><span class="status-pill ${esc(presentation.tone)}">${esc(presentation.label)}</span></header>
    <div class="shadow-model-metrics"><div><small>留出独立日</small><strong>${validation.heldOutDays === null ? "--" : fmt(validation.heldOutDays, 0)}</strong><span>门槛 ≥ 40 日</span></div><div><small>Brier</small><strong>${validation.brier === null ? "--" : fmt(validation.brier, 4)}</strong><span>概率误差，越低越好</span></div><div><small>Brier Skill</small><strong>${validation.brierSkill === null ? "--" : ratioPct(validation.brierSkill, 2)}</strong><span>门槛 ≥ 1%</span></div><div><small>ECE 10-bin</small><strong>${validation.ece === null ? "--" : fmt(validation.ece, 4)}</strong><span>门槛 ≤ 0.10</span></div><div><small>AUC</small><strong>${validation.auc === null ? "--" : fmt(validation.auc, 4)}</strong><span>门槛 ≥ 0.55</span></div><div><small>Top 10% 超额</small><strong>${validation.topExcess === null ? "--" : ratioPct(validation.topExcess, 2)}</strong><span>逐日等权门槛 ≥ 0.5%</span></div><div><small>影子预测</small><strong>${predictionCount === null ? "--" : fmt(predictionCount, 0)}</strong><span>不是正式可执行数</span></div><div><small>正式决策权限</small><strong class="${modelState.ready ? "positive" : "warning"}">${modelState.ready ? "已参与" : "未参与"}</strong><span>${modelState.ready ? "严格门禁仍会二次校验" : "不参与正式决策"}</span></div></div>
    <div class="shadow-model-audit"><dl><dt>模型</dt><dd>${esc(model.model_id || "未发布")}</dd><dt>标签</dt><dd>${esc(model.label_version || "r10-net-total-return-v1")}</dd><dt>训练截止</dt><dd>${esc(model.training_cutoff || "--")}</dd><dt>训练来源</dt><dd>${esc(provenance || "未发布")}</dd></dl><div class="shadow-model-limit"><strong>${currentUniverseBackfill ? "当前成分股历史回填" : "样本边界"}</strong><p>${currentUniverseBackfill ? "历史 K 线来自当前成分股，存在幸存者偏差；因此只能发布影子 P10，不参与正式决策。" : esc(limitations[0] || presentation.detail)}</p></div></div>
    ${reasonCopy}
    <div class="shadow-model-market-grid">${marketRows}</div>
  </section>`;
}

function renderRankModelCard(model = {}) {
  const status = String(model.status || "UNAVAILABLE").toUpperCase();
  const observing = status === "COLLECTING";
  const benchmarks = model.benchmark_registry || { a_share: "510300", hk: "2800.HK", us: "SPY" };
  const reasons = Array.isArray(model.reason_codes) ? model.reason_codes : [];
  return `<section class="panel shadow-model-card"><header class="panel-header"><div><h3 class="panel-title">10 日净超额收益排序 · V2</h3><p class="panel-subtitle">直接学习“股票净收益 − 可投资宽基净收益”，目标更接近两周内赚得最多</p></div><span class="status-pill ${observing ? "primary" : "negative"}">${esc(status)}</span></header><div class="shadow-model-metrics"><div><small>点时样本</small><strong>${fmt(model.sample_count, 0)}</strong><span>不做每日期 24 只截断</span></div><div><small>独立信号日</small><strong>${fmt(model.signal_date_count, 0)}</strong><span>最低训练门槛 ${fmt(model.minimum_train_days || 100, 0)} 日</span></div><div><small>Walk-forward folds</small><strong>${fmt(model.fold_count, 0)}</strong><span>按真实标签退出日防泄漏</span></div><div><small>正式决策权限</small><strong class="warning">无</strong><span>COLLECTING 不可自授权</span></div></div><div class="shadow-model-audit"><dl><dt>模型</dt><dd>${esc(model.model_id || "ten-day-excess-rank-shadow-v2")}</dd><dt>标签</dt><dd>${esc(model.label_version || "r10-net-excess-return-v2")}</dd><dt>A股基准</dt><dd>${esc(benchmarks.a_share || "510300")}</dd><dt>港股基准</dt><dd>${esc(benchmarks.hk || "2800.HK")}</dd><dt>美股基准</dt><dd>${esc(benchmarks.us || "SPY")}</dd></dl><div class="shadow-model-limit"><strong>当前边界</strong><p>${esc(reasons.join(" · ") || "等待每天的 300 / 200 / 300 点时候选池积累并完成样本外排名检验。")}</p></div></div></section>`;
}

function renderModel() {
  const root = $("#modelView");
  const status = state.status || {};
  const snapshot = state.snapshot || {};
  const weights = modelWeightRows();
  const dualModel = snapshot.analysis_models?.dual_low || {};
  const rankModel = snapshot.analysis_models?.ten_day_excess_rank || {};
  const tenDay = tenDayModelState(snapshot);
  const tenDayLive = tenDay.ready;
  const tenDayPresentation = tenDayModelPresentation(tenDay);
  const production = productionDecisionTruth(snapshot);
  const productionPrimary = production.primary || production.publishedPrimary;
  const productionHistorical = production.currentAction === "HISTORICAL_ONLY" && Boolean(production.publishedPrimary);
  const productionTrackName = productionPrimary
    ? qualificationTrackLabel(productionPrimary.qualification_track)
    : "本轮无合格通道";
  const tenDayPipelineCopy = tenDayLive
    ? "预测净总回报分布；已参与严格门禁。"
    : tenDay.shadowReady
      ? "已发布影子 P10；不参与正式决策。"
      : tenDay.shadowRejected
        ? "已发布影子 P10，但留出质量门槛未通过，仅供审计。"
        : "样本、校准和风险证据数据积累中。";
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
    <section class="objective-formula"><div><small>核心优化目标</small><strong>排序目标 ＝ 预期 10 日股票净收益 − 同期可投资宽基净收益</strong><p>校准概率与超额收益 V2 继续积累样本；生产规则 V4 在共享安全门禁后，分别评估事件催化与质量趋势两条资格通道。</p></div><span>HORIZON · 10 TRADING DAYS</span></section>
    <section class="panel shadow-model-card production-rule-model-card">
      <header class="panel-header"><div><h3 class="panel-title">生产规则资格模型 · V4</h3><p class="panel-subtitle">双层事件口径的双通道确定性规则；与校准概率轨独立，浏览器不补选、不改阈值</p></div><span class="status-pill ${production.qualified ? "positive" : "warning"}">${esc(production.action)}</span></header>
      <div class="shadow-model-metrics">
        <div><small>${productionHistorical ? "历史规则候选" : "当前规则候选"}</small><strong>${esc(productionPrimary?.name || "无")}</strong><span>${esc(productionPrimary ? `${productionPrimary.market} · ${productionPrimary.code}${productionHistorical ? " · 不可执行" : ""}` : production.blockerCodes.join(" · ") || "未通过")}</span></div>
        <div><small>${productionHistorical ? "历史资格通道" : "当前资格通道"}</small><strong>${esc(productionTrackName)}</strong><span>${production.qualificationScore === null ? "未产生资格分" : `${fmt(production.qualificationScore, 1)} 分`} · 非概率</span></div>
        <div><small>事件催化轨</small><strong>Legacy A/H/US</strong><span>推荐度 64 / 63 / 64</span></div>
        <div><small>事件催化附加门槛</small><strong>Top 20%</strong><span>Top 20% · 正向事件 ≥1 · RR ≥1.20</span></div>
        <div><small>事件催化情景区间</small><strong>A/H 与 US</strong><span>A/H 上行≥5% 且下行≤8% · US 上行≥6% 且下行≤10%</span></div>
        <div><small>质量趋势轨</small><strong>Legacy A/H/US</strong><span>推荐度 64 / 67 / 67</span></div>
        <div><small>质量趋势附加门槛</small><strong>Top 10%</strong><span>Top 10% · 数据质量 ≥95 · RR ≥1.50 · 资格分 ≥72</span></div>
        <div><small>质量趋势 A/H 区间</small><strong>对称风控</strong><span>A/H 上行≥6% 且下行≤6%</span></div>
        <div><small>质量趋势 US 区间</small><strong>更高上行要求</strong><span>US 上行≥6.5% 且下行≤7.5%</span></div>
        <div><small>概率声明</small><strong>无</strong><span>probability=null · calibrated=false</span></div>
        <div><small>历史身份</small><strong class="mono">${esc(productionPrimary?.qualification_id || "—")}</strong><span>通道、模型版本与证据随不可变快照保存</span></div>
      </div>
      <footer>${icon("ph-shield-check")}<span>两条资格通道都要求行情、候选池、完整评分、全池结构风险筛查、必需输入和风险收益合同通过。事件催化轨额外要求入选有界官方事件深扫且存在可审计正向事件；质量趋势轨不要求入选正向事件深扫，也不声称“官方无负面”。两轨资格分都是确定性规则分，不是上涨概率、收益承诺或自动下单指令。</span></footer>
    </section>
    ${renderTenDayModelCard(tenDay)}
    ${renderRankModelCard(rankModel)}
  <section class="panel model-pipeline-panel"><header class="panel-header"><div><h3 class="panel-title">7 阶段决策流水线</h3><p class="panel-subtitle">任一关键门禁失败，自动回退为 NO_VALID_PICK</p></div>${badge(snapshot.selector_mode || "legacy_active", "purple")}</header><ol class="pipeline-list pipeline-seven"><li><span>01</span><div><b>三市场有界动态召回</b><p>A / 港 / 美候选覆盖与召回来源。</p></div></li><li><span>02</span><div><b>交易与数据门禁</b><p>流动性、停牌、完整性和新鲜度。</p></div></li><li><span>03</span><div><b>因子和事件特征</b><p>Legacy、V2、双低与外部证据分开。</p></div></li><li><span>04</span><div><b>分市场 10 日模型</b><p>${esc(tenDayPipelineCopy)}</p></div></li><li><span>05</span><div><b>概率校准</b><p>${tenDayLive ? "P(R10>0) 已校准并记录模型版本。" : tenDay.shadowReady ? "已发布留出 Brier / ECE / AUC，但当前影子运行不授权正式动作。" : tenDay.shadowRejected ? "留出 Brier Skill、AUC、ECE 或 Top 10% 超额未同时达标，概率不进入排序。" : "P(R10>0) 留出校准数据积累中。"}</p></div></li><li><span>06</span><div><b>跨市场效用排名</b><p>收益、风险、成本与不确定性统一比较。</p></div></li><li class="is-gate"><span>07</span><div><b>可执行性复核</b><p>价格、仓位、事件时点与尾部风险。</p></div></li></ol></section>
    <section class="model-version-grid"><article class="panel"><header class="panel-header"><div><h3 class="panel-title">版本状态</h3><p class="panel-subtitle">实际运行、影子观察与计划能力明确分开</p></div></header><div class="version-table"><div><b>Legacy</b><span class="status-pill positive">运行中</span><small>规则评分与市场级动作</small></div><div><b>V2 因子</b><span class="status-pill primary">影子</span><small>分组因子与市场内结构排名</small></div><div><b>生产规则 V4</b><span class="status-pill ${production.qualified ? "positive" : "warning"}">${esc(production.action)}</span><small>事件催化 / 质量趋势双通道；资格分非概率</small></div><div><b>10 日概率 V1</b><span class="status-pill ${esc(tenDayPresentation.tone)}">${esc(tenDayPresentation.label)}</span><small>${tenDayLive ? esc(tenDay.model.model_id || "已校准模型") : esc(tenDayPipelineCopy)}</small></div><div><b>超额排序 V2</b><span class="status-pill primary">${esc(String(rankModel.status || "COLLECTING").toUpperCase())}</span><small>点时候选池持续积累，不参与正式决策</small></div><div><b>数据闸门</b><span class="status-pill positive">运行中</span><small>生产资格双通道各自按合同放行或阻断</small></div></div></article><article class="panel"><header class="panel-header"><div><h3 class="panel-title">术语边界</h3><p class="panel-subtitle">分数、概率与动作不能混用</p></div></header><dl class="term-list"><dt>规则资格分</dt><dd>生产门禁匹配程度，不等于上涨概率</dd><dt>影子 P10</dt><dd>留出样本概率观察；不参与正式决策</dd><dt>净超额收益</dt><dd>股票净收益减去同期可投资宽基净收益</dd><dt>正式正收益概率</dt><dd>仅已授权校准模型的 P(R10&gt;0)</dd><dt>置信度</dt><dd>数据和模型不确定性</dd><dt>研究优先</dt><dd>值得继续核验，不等于建议买入</dd></dl></article></section>
    <div class="model-grid">
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">旧因子仍然保留</h3><p class="panel-subtitle">回答“之前的评分还在吗”</p></div>${badge("Active", "positive")}</header><div class="legacy-map"><div><b>初筛 pre_score</b><span>成交额、换手、量比、涨幅等</span></div><div><b>缠论近似 chan_score</b><span>均线结构、二买 / 三买、箱体回踩</span></div><div><b>CZSC 近似</b><span>中枢、趋势、箱体位置与背驰风险</span></div><div><b>UZI + 评审团</b><span>买点纪律、流动性、过热和杀猪盘门控</span></div><div><b>Serenity 先验</b><span>AI capex 上游稀缺环节与融资风险</span></div><div><b>推荐度与动作</b><span>市场内 Legacy 排名继续保留；production_decision 决定规则资格，global_decision 独立决定校准概率动作</span></div></div></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">V2 分组权重</h3><p class="panel-subtitle">随市场状态采用规则先验；分数只作影子观察</p></div>${badge(snapshot.weights_version || "示意基准", "purple")}</header><div class="weight-list">${weights.map(([label, value]) => `<div><span>${esc(label)}</span><div class="progress-bar"><span style="width:${clamp(value)}%"></span></div><b>${fmt(value, 0)}%</b></div>`).join("")}</div><p class="fine-print">若市场基准数据不足，状态为 unknown 并保守处理；这里不声称是机器学习概率。</p></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">双低七因子 · 独立影子</h3><p class="panel-subtitle">补充估值视角，不与 Legacy / V2 机械相加</p></div>${badge(dualModel.status === "available" ? "Shadow available" : "Shadow", dualModel.status === "available" ? "positive" : "warning")}</header><dl><dt>模型</dt><dd>${esc(dualModel.model_id || "dsa-screening-score-v1")}</dd><dt>市场</dt><dd>A股；港美暂不适用</dd><dt>比较池</dt><dd>${esc(dualModel.pool_scope || "a_share.merged_recall_quote_pool.pre_kline_v1")}</dd><dt>输入 / 合格</dt><dd>${dualModel.input_count === undefined ? "待新快照" : `${fmt(dualModel.input_count, 0)} / ${fmt(dualModel.eligible_count, 0)}`}</dd><dt>默认风格</dt><dd>PE≤15、PB≤2、不过热</dd><dt>决策权限</dt><dd>无；仅输出研究优先级</dd></dl><p class="fine-print">“被过滤”只表示不符合这套价值风格或数据不完整，不表示公司质量差。</p></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">候选池边界</h3><p class="panel-subtitle">先扩大召回，再用行情、技术评分和深度研究逐层收窄</p></div></header><dl><dt>A股</dt><dd>${fmt(aRecall.selected, 0)} / ${fmt(aRecall.target || 300, 0)}；沪主板 90、深主板 75、创业板 75、科创板 60</dd>${aShareStageRows}<dt>A股路由</dt><dd>事件、动量、流动性、交易活跃、可控回调；历史延续只在实时宽基不足时补位</dd><dt>港股</dt><dd>${hkRecallCopy}</dd><dt>美股</dt><dd>${usRecallCopy}</dd><dt>港美动态源</dt><dd>主源必须带可验证的市场时间；无源时间的备用榜单和上次动态池只供研究，不放行推荐</dd><dt>新快照六层口径</dt><dd>公开横截面发现 → 普通股/可交易过滤 → 动态入池 → 有效行情 → 完整技术深评 → 决策候选</dd><dt>交易日</dt><dd>XSHG / XHKG / XNYS 真实交易所日历，分市场计算入场和第 10 个交易日退出</dd></dl></article>
      <article class="panel"><header class="panel-header"><div><h3 class="panel-title">运行架构</h3><p class="panel-subtitle">公开站点不依赖 Render、OpenD 或个人电脑常开</p></div>${badge("Cloudflare only", "primary")}</header><div class="architecture-list"><div>${icon("ph-github-logo")}<span><b>GitHub Actions</b><small>定时运行 Python，生成最新快照与历史文件</small></span></div><div>${icon("ph-package")}<span><b>同代 JSON assets</b><small>当前 R2 未启用，内嵌同代资产生效；代码仅保留可选 R2 路径，不使用 KV / D1</small></span></div><div>${icon("ph-cloud")}<span><b>Cloudflare Worker</b><small>提供静态页面、快照、历史与状态 API</small></span></div><div>${icon("ph-browser")}<span><b>浏览器</b><small>渲染证据、筛选与执行提示；评分与排序不在浏览器重算</small></span></div></div></article>
    </div>
    <section class="panel section-gap"><header class="panel-header"><div><h3 class="panel-title">能力状态与限制</h3><p class="panel-subtitle">不把近似规则包装成官方框架</p></div></header><div class="truth-grid"><div><span class="status-pill warning">内置近似</span><b>缠论 / CZSC</b><p>用日线均线、箱体、突破回踩和背驰风险近似，不是原生 CZSC 执行。</p></div><div><span class="status-pill warning">方法论加权</span><b>UZI</b><p>内置轻量评审和风控规则，不是外部 UZI 模型服务。</p></div><div><span class="status-pill warning">中性先验</span><b>Serenity</b><p>港美动态池统一使用中性 lens，避免旧静态名单获得手工元数据优势；差异由行情与结构信号产生。</p></div><div><span class="status-pill primary">纯云端快照</span><b>行情交付</b><p>页面只读取 GitHub Actions 已发布批次，不宣称盘中实时；源时间与快照生成时间分开。</p></div></div></section>`;
}

const SCHEDULER_GAP_META = {
  GITHUB_WORKFLOW_DISPATCH_TOKEN_NOT_PROVISIONED: "Cloudflare 专用 GitHub dispatch token 未配置",
  CLOUDFLARE_SCHEDULER_DISABLED: "Cloudflare 主调度开关未开启",
  R2_OR_EMBEDDED_MANIFEST_MISSING: "调度数据 manifest 不可用",
};
const ACTIVE_REFRESH_MODES = new Set([
  "github_actions_primary_with_30m_watchdog",
]);

function scheduleCheckpointCopy(value) {
  if (!Array.isArray(value)
    || value.length === 0
    || value.some((item) => typeof item !== "string" || !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(item))) {
    return "未知（状态 API 未发布有效检查点）";
  }
  return value.join(" / ");
}

function validUsPostCloseSchedule(value) {
  return Boolean(
    value
    && typeof value === "object"
    && !Array.isArray(value)
    && value.contract_version === "us-post-close-schedule-v1"
    && value.market_time_zone === "America/New_York"
    && value.market_checkpoint === "16:17"
    && sameStringList(value.primary_beijing_variants, ["04:17 夏令时", "05:17 冬令时"])
    && sameStringList(value.watchdog_beijing_variants, ["04:47 夏令时", "05:47 冬令时"])
    && value.china_days === "周二至周六"
    && value.dst_variant_selected_at_runtime === true
  );
}

function validActiveRefreshStatus(status = state.status) {
  if (!status || typeof status !== "object" || Array.isArray(status)) return false;
  const mode = status.active_refresh_mode;
  const enabled = status.scheduler_primary_enabled;
  const readinessFields = [
    "research_decision_ready", "checkpoint_evidence_ready",
    "unattended_refresh_ready", "calibrated_execution_ready",
  ];
  return Boolean(
    status.ok === true
    && status.snapshot_key === state.snapshot?.snapshot_key
    && status.generated_at === state.snapshot?.generated_at
    && status.source_snapshot_sha256 === state.snapshot?.source_snapshot?.sha256
    && Number(status.source_snapshot_byte_size) === Number(state.snapshot?.source_snapshot?.byte_size)
    && status.scheduler_primary_provider === "github_actions"
    && enabled === true
    && typeof status.cloudflare_dispatch_enabled === "boolean"
    && status.scheduler_health_contract_version === "scheduler-health-v2"
    && ACTIVE_REFRESH_MODES.has(mode)
    && readinessFields.every((field) => typeof status[field] === "boolean")
    && typeof status.next_active_refresh === "string"
    && /\+08:00$/.test(status.next_active_refresh)
    && Number.isFinite(Date.parse(status.next_active_refresh))
    && validUsPostCloseSchedule(status.schedule_us_post_close)
  );
}

function activeRefreshStatusFieldsPresent(status = state.status) {
  return Boolean(
    status
    && typeof status === "object"
    && !Array.isArray(status)
    && [
      "scheduler_primary_provider", "scheduler_primary_enabled",
      "cloudflare_dispatch_enabled", "active_refresh_mode", "next_active_refresh",
      "schedule_us_post_close", "scheduler_health_contract_version",
      "research_decision_ready",
      "checkpoint_evidence_ready", "unattended_refresh_ready",
      "calibrated_execution_ready",
    ]
      .some((field) => Object.hasOwn(status, field))
  );
}

function readinessLayerPresentation(value, initializing = false) {
  if (initializing && value !== true) {
    return { state: "INITIALIZING", label: "证据初始化中", tone: "warning" };
  }
  if (value === true) return { state: "READY", label: "已就绪", tone: "positive" };
  if (value === false) return { state: "NOT_READY", label: "未就绪", tone: "negative" };
  return { state: "UNKNOWN", label: "未知", tone: "warning" };
}

function schedulerHealthPresentation() {
  const gate = state.schedulerGate;
  const contractReady = validSchedulerGatePayload(gate);
  const v2ContractReady = contractReady && gate.contract_version === "scheduler-health-v2";
  const legacyContractReady = contractReady && gate.contract_version === "scheduler-health-v1";
  const status = state.status || {};
  const statusFieldsPresent = activeRefreshStatusFieldsPresent(status);
  const statusReady = validActiveRefreshStatus(status);
  const contractsConsistent = Boolean(
    statusReady
    && v2ContractReady
    && status.scheduler_primary_provider === gate.scheduler_primary_provider
    && status.scheduler_primary_enabled === gate.scheduler_primary_enabled
    && status.cloudflare_dispatch_enabled === gate.cloudflare_dispatch_enabled
    && status.checkpoint_evidence_ready === gate.checkpoint_evidence_ready
    && status.unattended_refresh_ready === gate.unattended_refresh_ready
  );
  const gateOnlyFallback = !statusFieldsPresent && v2ContractReady;
  const primaryEnabled = contractsConsistent
    ? status.scheduler_primary_enabled
    : gateOnlyFallback ? gate.scheduler_primary_enabled : null;
  const primaryState = primaryEnabled === true ? "ENABLED" : primaryEnabled === false ? "DISABLED" : "UNKNOWN";
  const primaryLabel = primaryState === "ENABLED"
    ? "GitHub Actions 主调度已启用"
    : primaryState === "DISABLED" ? "GitHub Actions 主调度未启用" : "GitHub Actions 主调度状态未知";
  const primaryTone = primaryState === "ENABLED" ? "positive" : primaryState === "DISABLED" ? "negative" : "warning";
  const gapLabel = statusFieldsPresent && (!statusReady || !v2ContractReady || !contractsConsistent)
    ? "未知（状态 API 与 gate-status 合同缺失或不一致）"
    : legacyContractReady ? "旧版调度合同仅供读取，主调度状态未知"
      : !v2ContractReady ? "未知（gate-status v2 合同不可用）"
        : primaryEnabled ? "无" : "GitHub Actions 主调度未启用";
  const schedulerReadiness = v2ContractReady
    && (contractsConsistent || gateOnlyFallback)
    ? gate.scheduler_readiness : "UNKNOWN";
  const initializing = schedulerReadiness === "INITIALIZING";
  const readinessLabel = schedulerReadiness === "READY"
    ? "调度证据就绪"
    : schedulerReadiness === "DEGRADED" ? "调度证据降级"
      : initializing ? "证据初始化中" : "调度证据未知";
  const readinessTone = schedulerReadiness === "READY"
    ? "positive" : schedulerReadiness === "DEGRADED" ? "negative" : "warning";
  const cloudflareDispatchEnabled = contractsConsistent
    ? status.cloudflare_dispatch_enabled
    : gateOnlyFallback ? gate.cloudflare_dispatch_enabled : null;
  const cloudflareDispatchLabel = cloudflareDispatchEnabled === true
    ? "可选 dispatch 已启用"
    : cloudflareDispatchEnabled === false
      ? "可选 dispatch 未启用（不影响主调度）"
      : "可选 dispatch 状态未知";
  const hasBatchPublicationEvidence = Boolean(
    v2ContractReady
    && !initializing
    && typeof gate.source_invocation_slot === "string"
    && Number.isFinite(Date.parse(gate.source_invocation_slot))
    && typeof gate.published_at === "string"
    && Number.isFinite(Date.parse(gate.published_at))
  );
  const batchEvidence = initializing
    ? "证据初始化中"
    : hasBatchPublicationEvidence
    ? `源调用 ${dateTime(gate.source_invocation_slot)} · 发布 ${dateTime(gate.published_at)} · ${gate.publication_backend}`
    : "未知（未发布完整的源调用与发布时间证据）";
  const activeMode = contractsConsistent ? status.active_refresh_mode : null;
  const watchdogLabel = activeMode === "github_actions_primary_with_30m_watchdog"
    ? "30 分钟 watchdog 已配置"
    : "watchdog 状态未知";
  const watchdogDetail = activeMode
    ? `状态 API 发布 active_refresh_mode=${activeMode}`
    : hasBatchPublicationEvidence
      ? "最近批次有发布证据，但合同未标注触发来源，不归因为 GitHub watchdog"
      : "状态 API 未发布可验证的 active_refresh_mode";
  const checkpointEvidence = initializing
    ? "证据初始化中（完整 24 小时窗口形成前不按零值处理）"
    : v2ContractReady
      ? `24 小时应有 ${gate.expected_checkpoints_24h} · 按时 ${gate.published_on_time_24h} · 迟到恢复 ${gate.late_recoveries_24h} · ${Number.isInteger(gate.missed_checkpoints_24h) ? `遗漏 ${gate.missed_checkpoints_24h} · ` : ""}证据滞后 ${gate.evidence_lag_batches} 批`
      : "24 小时检查点证据不完整";
  const sloMinutes = v2ContractReady ? gate.publication_slo_seconds / 60 : null;
  const publicationSlo = initializing
    ? `${fmt(sloMinutes, 0)} 分钟发布服务目标（非保证）· 证据初始化中`
    : v2ContractReady
      ? `${fmt(sloMinutes, 0)} 分钟发布服务目标（非保证）· ${gate.publication_within_slo === true ? "最近批次在目标内" : gate.publication_within_slo === false ? "最近批次超出目标" : "最近批次证据未知"}`
      : "发布服务目标未知（不构成保证）";
  const readinessSource = contractsConsistent ? status : gateOnlyFallback ? gate : {};
  const readinessLayers = {
    research: readinessLayerPresentation(readinessSource.research_decision_ready, initializing),
    checkpoint: readinessLayerPresentation(readinessSource.checkpoint_evidence_ready, initializing),
    unattended: readinessLayerPresentation(readinessSource.unattended_refresh_ready, initializing),
    calibrated: readinessLayerPresentation(readinessSource.calibrated_execution_ready, initializing),
  };
  const usSchedule = statusReady ? status.schedule_us_post_close : null;
  return {
    contractReady, statusReady, contractsConsistent, primaryState, primaryLabel, primaryTone, gapLabel,
    activeMode, schedulerReadiness, readinessLabel, readinessTone,
    cloudflareDispatchEnabled, cloudflareDispatchLabel, publicationSlo, readinessLayers,
    hasBatchPublicationEvidence, batchEvidence, watchdogLabel, watchdogDetail,
    checkpointEvidence,
    nextActiveRefresh: contractsConsistent ? status.next_active_refresh : null,
    usPrimaryCheckpoints: usSchedule ? usSchedule.primary_beijing_variants.join(" / ") : "未知（状态 API 未发布合同）",
    usWatchdogCheckpoints: usSchedule ? usSchedule.watchdog_beijing_variants.join(" / ") : "未知（状态 API 未发布合同）",
    usScheduleDays: usSchedule ? usSchedule.china_days : "未知",
  };
}

function renderHealth() {
  const root = $("#healthView");
  const truth = globalDecisionTruth();
  const production = productionDecisionTruth();
  const status = state.status || {};
  const scheduler = schedulerHealthPresentation();
  const primarySchedule = scheduleCheckpointCopy(status.schedule_primary_checkpoints);
  const fallbackSchedule = scheduleCheckpointCopy(status.schedule_fallback_checkpoints);
  const snapshotPublished = Boolean(
    validSnapshotIdentity(state.snapshot)
    && status.ok === true
    && status.snapshot_key === state.snapshot.snapshot_key
    && status.generated_at === state.snapshot.generated_at
    && status.source_snapshot_sha256 === state.snapshot.source_snapshot.sha256
    && Number(status.source_snapshot_byte_size) === Number(state.snapshot.source_snapshot.byte_size)
  );
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
  const ruleUsable = production.action === "QUALIFIED_PICK" && Boolean(production.primary);
  const historicalOnly = production.currentAction === "HISTORICAL_ONLY";
  const publishedPrimary = production.publishedPrimary;
  const eventStats = publishedEventStats();
  root.innerHTML = `
    <div class="principle-strip"><span><b>判断原则</b> 任务运行成功、行情覆盖完整、本轮有界扫描完整和两条决策轨可用是不同的事。</span><small class="${ruleUsable || usable ? "positive" : "negative"}">当前：规则轨 ${esc(production.action)} · 校准轨 ${esc(truth.action)}</small></div>
    <div class="callout ${ruleUsable ? "info" : historicalOnly ? "warning" : usable ? "" : "negative"} health-alert">${icon(ruleUsable || usable ? "ph-check-circle" : "ph-warning-octagon")}<div><strong>${ruleUsable ? `规则资格轨已通过：${esc(production.primary.name || production.primary.code)}` : historicalOnly ? "快照已过期：当前合格候选强制为 0" : usable ? "校准跨市场候选契约完整" : "两条决策轨当前均未放行候选"}</strong><br>${ruleUsable ? `资格分 ${fmt(production.qualificationScore, 1)}（非概率）；校准轨仍为 ${esc(truth.action)}，原因：${esc(blockers.slice(0, 4).join("；") || "未发布校准候选")}。` : historicalOnly ? `历史发布合格 ${fmt(production.historicalQualifiedCount, 0)} 只，只供研究；暂停执行并等待 fresh 新快照。` : usable ? "概率、净效用、成本、尾部风险、市场覆盖和官方证据均已通过契约校验。" : esc(blockers.slice(0, 5).join("；") || production.blockerCodes.join("；") || "没有候选通过门禁。")}</div></div>
    ${renderKpis([
      { icon: "ph-seal-check", label: "当前规则合格", value: fmt(production.currentQualifiedCount, 0), tone: ruleUsable ? "positive" : historicalOnly ? "warning" : "negative", meta: `历史发布合格 ${fmt(production.historicalQualifiedCount, 0)} 只 · 非概率` },
      { icon: "ph-globe", label: "可比较市场", value: `${readyMarkets} / 3`, tone: readyMarkets === 3 ? "positive" : "negative", meta: "A股、港股、美股须口径可比" },
      { icon: "ph-binoculars", label: "三市场召回目标", value: recallTargetsMet ? "300 / 200 / 300" : "未达标", tone: recallTargetsMet ? "positive" : "warning", meta: "A股 / 港股 / 美股；行情与深评另行门控" },
      { icon: "ph-newspaper", label: "外部自动证据", value: fmt(truth.autoEvidenceCount, 0), tone: truth.autoEvidenceCount ? "positive" : "negative", meta: `模型信号 ${fmt(eventStats.modelSignals, 0)} 条不等于证据` },
      { icon: "ph-clock-clockwise", label: "GitHub Actions 主调度", value: scheduler.primaryLabel, tone: scheduler.primaryTone, meta: scheduler.readinessLabel },
    ])}
    <section class="health-layout"><article class="panel"><header class="panel-header"><div><h3 class="panel-title">市场与数据源状态</h3><p class="panel-subtitle">健康状态直接解释为什么不能给出买入答案</p></div></header><div class="health-table"><div class="health-table-head"><span>对象</span><span>状态</span><span>关键指标</span><span>说明与决策影响</span></div>
      ${truth.markets.map((market) => row(MARKET_META[market.market].label, marketTone(market), marketStateLabel(market), marketMetrics(market), market.reasons.join("；") || "关键数据门禁已通过")).join("")}
      ${row("事件数据", truth.autoEvidenceCount ? "warning" : "negative", truth.autoEvidenceCount ? "已入库" : "严重缺口", `外部自动 ${truth.autoEvidenceCount} · 发布候选绑定 ${fmt(publishedPrimary?.verified_positive_event_ids?.length, 0)} · 模型信号 ${fmt(eventStats.modelSignals, 0)}`, "官方事件可进入规则门禁，但不可单独支撑买入")}
      ${row("最近发布快照", snapshotPublished ? "positive" : "negative", snapshotPublished ? "身份一致" : "证据不足", `快照 ${dateTime(state.snapshot?.generated_at)}`, "快照可访问和新鲜度不证明主调度已启用，也不代表决策数据完整")}
    </div></article><aside class="health-side"><article class="panel"><header class="panel-header"><div><h3 class="panel-title">实际更新机制</h3><p class="panel-subtitle">纯云端批次快照，不依赖个人设备</p></div>${badge(scheduler.readinessLabel, scheduler.readinessTone)}</header><dl><dt>GitHub Actions 主调度</dt><dd>${esc(scheduler.primaryLabel)}</dd><dt>Cloudflare dispatch（可选）</dt><dd>${esc(scheduler.cloudflareDispatchLabel)}</dd><dt>调度合同</dt><dd>${esc(scheduler.gapLabel)}</dd><dt>30 分钟 watchdog</dt><dd>${esc(scheduler.watchdogLabel)}；${esc(scheduler.watchdogDetail)}</dd><dt>调度证据状态</dt><dd>${badge(scheduler.readinessLabel, scheduler.readinessTone)}</dd><dt>研究决策可用</dt><dd>${badge(scheduler.readinessLayers.research.label, scheduler.readinessLayers.research.tone)}</dd><dt>检查点证据可用</dt><dd>${badge(scheduler.readinessLayers.checkpoint.label, scheduler.readinessLayers.checkpoint.tone)}</dd><dt>无人值守刷新可用</dt><dd>${badge(scheduler.readinessLayers.unattended.label, scheduler.readinessLayers.unattended.tone)}</dd><dt>校准执行可用</dt><dd>${badge(scheduler.readinessLayers.calibrated.label, scheduler.readinessLayers.calibrated.tone)}</dd><dt>发布 SLO</dt><dd>${esc(scheduler.publicationSlo)}</dd><dt>最近批次证据</dt><dd>${esc(scheduler.batchEvidence)}</dd><dt>24 小时覆盖证据</dt><dd>${esc(scheduler.checkpointEvidence)}</dd><dt>标准主检查点（配置口径）</dt><dd>工作日北京时间 ${esc(primarySchedule)}</dd><dt>标准 watchdog（配置口径）</dt><dd>工作日北京时间 ${esc(fallbackSchedule)}；不表示已触发</dd><dt>美股盘后主检查点</dt><dd>北京时间 ${esc(scheduler.usPrimaryCheckpoints)}；${esc(scheduler.usScheduleDays)}，仅匹配纽约 16:17 的时段有效</dd><dt>美股盘后 watchdog</dt><dd>北京时间 ${esc(scheduler.usWatchdogCheckpoints)}；${esc(scheduler.usScheduleDays)}</dd><dt>快照生成</dt><dd>${esc(dateTime(status.snapshot_as_of || state.snapshot?.generated_at))}</dd><dt>下次实际自动刷新</dt><dd>${scheduler.nextActiveRefresh ? esc(dateTime(scheduler.nextActiveRefresh)) : "未知（状态 API 合同不可用）"}</dd><dt>交易日窗口</dt><dd>XSHG / XHKG / XNYS 真实日历</dd><dt>结果跟踪</dt><dd>规则资格随每日快照留档；校准可执行预测第 10 个交易日后结算</dd></dl></article><article class="panel"><header class="panel-header"><div><h3 class="panel-title">发布证据不等于主调度或决策可用</h3></div></header><p>${scheduler.activeMode ? `状态 API 已明确实际自动刷新路径为 ${esc(scheduler.activeMode)}；` : "状态 API 与 gate-status 不足时，主调度和 watchdog 必须显示未知；"}发布 SLO 只是可观测服务目标，不是 GitHub、公开数据源或市场行情的保证。最近批次发布证据也不代表决策数据完整。</p>${badge(scheduler.schedulerReadiness === "INITIALIZING" ? "证据初始化中" : scheduler.hasBatchPublicationEvidence ? "最近批次：有发布证据" : "最近批次：证据未知", scheduler.hasBatchPublicationEvidence ? "primary" : "warning")}</article><a class="secondary-button" href="https://github.com/dzhdingzihang/xuangu/actions" target="_blank" rel="noopener noreferrer">查看最近一次任务 ${icon("ph-arrow-square-out")}</a></aside></section>`;
}

function renderActiveTab() {
  if (!state.snapshot) return;
  const requirements = TAB_DATA_REQUIREMENTS[state.tab] || [];
  if (requirements.some((resource) => (
    state.tabData[resource]?.status !== "ready"
    || state.tabData[resource]?.snapshotKey !== state.snapshot.snapshot_key
    || state.tabData[resource]?.queryKey !== resourceQueryKey(resource)
  ))) {
    renderTabDataState(state.tab);
    return;
  }
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
  requestControllers.historyDetail?.abort?.();
  const controller = typeof AbortController === "undefined" ? null : new AbortController();
  requestControllers.historyDetail = controller;
  try {
    state.historySnapshot = await getJson(`/api/pick?snapshot=${encodeURIComponent(key)}`, { signal: controller?.signal || null });
    state.historySnapshotKey = key;
    renderHistory();
    showToast("完整历史快照已载入。", "success");
  } catch (error) {
    if (error?.name !== "AbortError") showToast(error.message || "历史快照载入失败", "error");
  } finally {
    if (requestControllers.historyDetail === controller) requestControllers.historyDetail = null;
  }
}

async function refreshAll() {
  const requestGeneration = ++snapshotLoadGeneration;
  const button = $("#refreshBtn");
  button.classList.add("is-loading"); button.disabled = true;
  try {
    const bootstrap = await getJson("/api/latest-summary");
    if (requestGeneration !== snapshotLoadGeneration) return;
    await applyBootstrapPayload(bootstrap);
    scheduleNextRefreshPoll();
    renderRail(); updateTopbar(); renderActiveTab();
    await ensureTabData(state.tab);
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
let nextRefreshPollTimer = null;
const CHECKPOINT_POLL_SKEW_MS = 250;
const CHECKPOINT_POLL_RETRY_MS = 15_000;

function nextRefreshPollDelay(nextRefresh, now = Date.now()) {
  const checkpoint = Date.parse(nextRefresh || "");
  if (!Number.isFinite(checkpoint) || !Number.isFinite(now)) return null;
  const remaining = checkpoint + CHECKPOINT_POLL_SKEW_MS - now;
  if (remaining <= 0) return CHECKPOINT_POLL_RETRY_MS;
  return Math.min(remaining, 2_147_000_000);
}

function scheduleNextRefreshPoll() {
  if (nextRefreshPollTimer !== null && typeof window.clearTimeout === "function") {
    window.clearTimeout(nextRefreshPollTimer);
  }
  nextRefreshPollTimer = null;
  const nextRefresh = validActiveRefreshStatus(state.status)
    ? state.status.next_active_refresh
    : activeRefreshStatusFieldsPresent(state.status) ? null : state.status?.next_refresh;
  const delay = nextRefreshPollDelay(nextRefresh);
  if (delay === null) return;
  nextRefreshPollTimer = window.setTimeout(async () => {
    nextRefreshPollTimer = null;
    await pollStatus();
    if (nextRefreshPollTimer === null) scheduleNextRefreshPoll();
  }, delay);
}

async function pollStatus() {
  if (statusPollInFlight) return;
  statusPollInFlight = true;
  const previousGeneratedAt = state.snapshot?.generated_at || state.status?.generated_at || null;
  const previousSnapshotKey = state.snapshot?.snapshot_key || null;
  const previousSourceSha = state.snapshot?.source_snapshot?.sha256 || null;
  const previousSourceByteSize = state.snapshot?.source_snapshot?.byte_size ?? null;
  const previousStatusKey = JSON.stringify([
    state.status?.ok,
    state.status?.freshness_state,
    state.status?.snapshot_use?.current_decision_allowed,
    state.status?.expected_checkpoint,
    state.status?.checkpoint_lag_minutes,
  ]);
  try {
    const status = await getJson("/api/status");
    const snapshotChanged = !state.snapshot || (status.generated_at && status.generated_at !== previousGeneratedAt)
      || (status.snapshot_key && status.snapshot_key !== previousSnapshotKey)
      || (status.source_snapshot_sha256 && status.source_snapshot_sha256 !== previousSourceSha)
      || (status.source_snapshot_byte_size !== undefined
        && status.source_snapshot_byte_size !== null
        && Number(status.source_snapshot_byte_size) !== Number(previousSourceByteSize));
    if (snapshotChanged) {
      const requestGeneration = ++snapshotLoadGeneration;
      const bootstrap = await getJson("/api/latest-summary");
      if (requestGeneration !== snapshotLoadGeneration) return;
      await applyBootstrapPayload(bootstrap);
      renderRail();
      updateTopbar();
      renderActiveTab();
      await ensureTabData(state.tab);
      showToast("检测到新决策快照，页面已自动更新；筛选条件保持不变。", "success");
    } else {
      const accepted = mergeSnapshotDecisionState(status, { mergeStatusFields: true, strict: true });
      if (accepted) {
        updateTopbar();
        const statusChanged = previousStatusKey !== JSON.stringify([
          state.status?.ok,
          state.status?.freshness_state,
          state.status?.snapshot_use?.current_decision_allowed,
          state.status?.expected_checkpoint,
          state.status?.checkpoint_lag_minutes,
        ]);
        if (statusChanged) renderActiveTab();
      }
    }
  } catch (error) {
    state.status = { ...(state.status || {}), ok: false, freshness_state: "unknown" };
    updateTopbar();
    renderActiveTab();
    window.setTimeout(pollStatus, 15_000);
  } finally {
    statusPollInFlight = false;
    scheduleNextRefreshPoll();
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
  if (action === "retry-tab") {
    for (const resource of TAB_DATA_REQUIREMENTS[state.tab] || []) {
      state.tabData[resource] = {
        status: "idle", snapshotKey: null, queryKey: resourceQueryKey(resource), requestId: 0, error: "",
      };
    }
    void ensureTabData(state.tab);
    return;
  }
  if (action === "load-more-candidates") { void loadMoreResource("candidates"); return; }
  if (action === "load-more-events") { void loadMoreResource("events"); return; }
  if (action === "load-more-history") { void loadMoreResource("history"); return; }
  if (action === "market") {
    state.market = market;
    state.candidateFilters.market = market;
    switchTab("candidates");
    return;
  }
  if (action === "candidate-market") {
    if (state.candidateFilters.market === market) return;
    state.candidateFilters.market = market;
    if (state.tab !== "candidates") switchTab("candidates");
    else void reloadPagedResource("candidates");
    return;
  }
  if (action === "select-candidate") {
    state.candidateKey = key;
    state.candidateDetailOpen = window.matchMedia("(max-width: 760px)").matches;
    renderCandidates();
    if (state.candidateDetailOpen) window.setTimeout(() => $(".candidate-detail-back")?.focus(), 0);
    const selectedRow = rowForKey(key);
    if (selectedRow) void loadCandidateDetail(selectedRow);
    return;
  }
  if (action === "close-candidate-detail") {
    state.candidateDetailOpen = false;
    requestControllers.detail?.abort?.();
    requestControllers.detail = null;
    if (state.candidateDetailStatus[state.candidateKey] === "loading") {
      state.candidateDetailStatus[state.candidateKey] = "idle";
    }
    renderCandidates();
    window.setTimeout(() => $$('[data-action="select-candidate"]').find((item) => item.dataset.key === state.candidateKey)?.focus(), 0);
    return;
  }
  if (action === "open-candidate") {
    state.candidateKey = key;
    state.candidateDetailOpen = window.matchMedia("(max-width: 760px)").matches;
    state.candidateFilters = { market: key.split(":")[0], risk: "all", route: "all", query: "" };
    switchTab("candidates");
    const selectedRow = rowForKey(key);
    if (selectedRow) void loadCandidateDetail(selectedRow);
    return;
  }
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
  if (action === "event-market") {
    if (state.eventFilters.market === market) return;
    state.eventFilters.market = market;
    if (state.tab !== "events") switchTab("events");
    else void reloadPagedResource("events");
    return;
  }
  if (action === "select-event") { state.eventKey = key; renderEvents(); return; }
  if (action === "history-market") { state.historyMarket = market; state.historyKey = ""; state.historySnapshot = null; state.historySnapshotKey = ""; renderHistory(); return; }
  if (action === "select-history") {
    requestControllers.historyDetail?.abort?.();
    requestControllers.historyDetail = null;
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
  if (event.target.id === "eventType") { state.eventFilters.type = event.target.value; void reloadPagedResource("events"); }
  if (event.target.id === "eventDirection") { state.eventFilters.direction = event.target.value; void reloadPagedResource("events"); }
  if (event.target.id === "historyAction") { state.historyAction = event.target.value; renderHistory(); }
}

function debounceSearch(key, value, commit) {
  const previous = searchDebounceTimers.get(key);
  if (previous !== undefined) window.clearTimeout(previous);
  const timer = window.setTimeout(() => {
    searchDebounceTimers.delete(key);
    commit(value);
  }, SEARCH_DEBOUNCE_MS);
  searchDebounceTimers.set(key, timer);
}

function handleInput(event) {
  if (event.isComposing || event.target.dataset.composing === "true") return;
  const value = event.target.value;
  if (event.target.id === "candidateSearch") debounceSearch("candidateSearch", value, (query) => {
    if (state.candidateFilters.query === query) return;
    state.candidateFilters.query = query;
    void reloadPagedResource("candidates", { restoreFocusId: "candidateSearch" });
  });
  if (event.target.id === "eventSearch") debounceSearch("eventSearch", value, (query) => {
    if (state.eventFilters.query === query) return;
    state.eventFilters.query = query;
    void reloadPagedResource("events", { restoreFocusId: "eventSearch" });
  });
  if (event.target.id === "historySearch") debounceSearch("historySearch", value, (query) => { state.historyQuery = query; renderHistory(); });
}

function handleKeyboard(event) {
  if (event.key === "Tab" && state.candidateDetailOpen
    && window.matchMedia?.("(max-width: 760px)")?.matches === true) {
    const host = $(".candidate-detail-host.is-open");
    const focusables = candidateDialogFocusables();
    if (host && focusables.length) {
      const first = focusables[0];
      const last = focusables.at(-1);
      if (!host.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    return;
  }
  if (event.key === "Escape" && state.candidateDetailOpen) {
    event.preventDefault();
    $("[data-action=\"close-candidate-detail\"]")?.click();
    return;
  }
  const activeTab = event.target.closest?.('[role="tab"][data-tab]');
  if (activeTab) {
    const tabs = $$('.primary-nav [role="tab"][data-tab]');
    const currentIndex = tabs.indexOf(activeTab);
    const keyTargets = {
      ArrowRight: (currentIndex + 1) % tabs.length,
      ArrowDown: (currentIndex + 1) % tabs.length,
      ArrowLeft: (currentIndex - 1 + tabs.length) % tabs.length,
      ArrowUp: (currentIndex - 1 + tabs.length) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    };
    if (Object.prototype.hasOwnProperty.call(keyTargets, event.key)) {
      event.preventDefault();
      const target = tabs[keyTargets[event.key]];
      target?.focus();
      if (target?.dataset.tab) switchTab(target.dataset.tab);
      return;
    }
  }
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
    syncCandidateDialogA11y();
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
    const bootstrap = await getJson("/api/latest-summary");
    await applyBootstrapPayload(bootstrap);
    scheduleNextRefreshPoll();
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

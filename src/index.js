const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const SECURITY_HEADERS = {
  "strict-transport-security": "max-age=31536000; includeSubDomains",
  "x-content-type-options": "nosniff",
  "referrer-policy": "strict-origin-when-cross-origin",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
};

const SHANGHAI_TIME_ZONE = "Asia/Shanghai";
const STATUS_GRACE_MINUTES = 45;
const WEEKDAY_CHECKPOINTS = [
  [8, 17],
  [10, 17],
  [12, 17],
  [15, 17],
  [16, 17],
  [20, 17],
  [22, 47],
];
const FALLBACK_CHECKPOINTS = [
  [8, 47],
  [10, 47],
  [12, 47],
  [15, 47],
  [16, 47],
  [20, 47],
  [23, 17],
];
const SCHEDULED_REFRESH_CHECKPOINTS = [...WEEKDAY_CHECKPOINTS, ...FALLBACK_CHECKPOINTS]
  .sort(([leftHour, leftMinute], [rightHour, rightMinute]) =>
    leftHour * 60 + leftMinute - (rightHour * 60 + rightMinute));
const LIVE_MARKETS = new Set(["a_share", "hk", "us"]);
const LIVE_CACHE_TTL_MS = 10_000;

function withSecurityHeaders(response) {
  const headers = new Headers(response.headers);
  Object.entries(SECURITY_HEADERS).forEach(([key, value]) => headers.set(key, value));
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function httpsRedirect(request, env) {
  if (env && env.LOCAL_DEV === "1") return null;
  const url = new URL(request.url);
  const localHost = url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "::1";
  const forwardedProto = request.headers.get("x-forwarded-proto");
  if (!localHost && (url.protocol === "http:" || forwardedProto === "http")) {
    url.protocol = "https:";
    return Response.redirect(url.toString(), 308);
  }
  return null;
}

function json(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...JSON_HEADERS, ...extraHeaders },
  });
}

function nowCN() {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: SHANGHAI_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date());
  return `${parts.replace(" ", "T")}+08:00`;
}

function shanghaiDateParts(date) {
  const values = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: SHANGHAI_TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date).filter((part) => part.type !== "literal").map((part) => [part.type, part.value]),
  );
  return {
    year: Number(values.year),
    month: Number(values.month),
    day: Number(values.day),
    hour: Number(values.hour),
    minute: Number(values.minute),
  };
}

function shiftCalendarDate(parts, days) {
  const shifted = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + days));
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
  };
}

function calendarWeekday(parts) {
  return new Date(Date.UTC(parts.year, parts.month - 1, parts.day)).getUTCDay();
}

function isBusinessDay(parts) {
  const weekday = calendarWeekday(parts);
  return weekday >= 1 && weekday <= 5;
}

function previousBusinessDay(parts) {
  let candidate = shiftCalendarDate(parts, -1);
  while (!isBusinessDay(candidate)) candidate = shiftCalendarDate(candidate, -1);
  return candidate;
}

function checkpointIso(parts, checkpoint) {
  const [hour, minute] = checkpoint;
  const pad = (value) => String(value).padStart(2, "0");
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}T${pad(hour)}:${pad(minute)}:00+08:00`;
}

export function nextScheduledRefresh(current = new Date()) {
  const now = current instanceof Date ? current : new Date(current);
  if (Number.isNaN(now.getTime())) return null;
  const local = shanghaiDateParts(now);
  const startDate = { year: local.year, month: local.month, day: local.day };
  for (let dayOffset = 0; dayOffset <= 8; dayOffset += 1) {
    const checkpointDate = shiftCalendarDate(startDate, dayOffset);
    if (!isBusinessDay(checkpointDate)) continue;
    for (const checkpoint of SCHEDULED_REFRESH_CHECKPOINTS) {
      const [hour, minute] = checkpoint;
      const epoch = Date.UTC(
        checkpointDate.year,
        checkpointDate.month - 1,
        checkpointDate.day,
        hour - 8,
        minute,
      );
      if (epoch > now.getTime()) return checkpointIso(checkpointDate, checkpoint);
    }
  }
  return null;
}

function expectedCheckpoint(current) {
  const local = shanghaiDateParts(current);
  let checkpointDate = { year: local.year, month: local.month, day: local.day };
  let checkpoint = null;
  if (isBusinessDay(checkpointDate)) {
    const currentMinute = local.hour * 60 + local.minute;
    checkpoint = [...WEEKDAY_CHECKPOINTS]
      .reverse()
      .find(([hour, minute]) => hour * 60 + minute <= currentMinute) || null;
    if (!checkpoint) checkpointDate = previousBusinessDay(checkpointDate);
  } else {
    while (!isBusinessDay(checkpointDate)) checkpointDate = shiftCalendarDate(checkpointDate, -1);
  }
  checkpoint ||= WEEKDAY_CHECKPOINTS.at(-1);
  const [hour, minute] = checkpoint;
  const epoch = Date.UTC(
    checkpointDate.year,
    checkpointDate.month - 1,
    checkpointDate.day,
    hour - 8,
    minute,
  );
  const pad = (value) => String(value).padStart(2, "0");
  return {
    epoch,
    iso: `${checkpointDate.year}-${pad(checkpointDate.month)}-${pad(checkpointDate.day)}T${pad(hour)}:${pad(minute)}:00+08:00`,
  };
}

export function snapshotFreshness(generatedAt, current = new Date()) {
  const now = current instanceof Date ? current : new Date(current);
  if (Number.isNaN(now.getTime())) {
    return {
      freshness_state: "unknown",
      expected_checkpoint: null,
      snapshot_age_minutes: null,
      checkpoint_lag_minutes: null,
    };
  }
  const expected = expectedCheckpoint(now);
  const generated = generatedAt ? new Date(generatedAt) : null;
  if (!generated || Number.isNaN(generated.getTime())) {
    return {
      freshness_state: "unknown",
      expected_checkpoint: expected.iso,
      snapshot_age_minutes: null,
      checkpoint_lag_minutes: null,
    };
  }
  const generatedEpoch = generated.getTime();
  const nowEpoch = now.getTime();
  const snapshotAge = Math.max(0, Math.floor((nowEpoch - generatedEpoch) / 60_000));
  const checkpointLag = Math.max(0, Math.floor((expected.epoch - generatedEpoch) / 60_000));
  let freshnessState = "fresh";
  if (generatedEpoch < expected.epoch) {
    freshnessState = nowEpoch <= expected.epoch + STATUS_GRACE_MINUTES * 60_000 ? "updating" : "stale";
  }
  return {
    freshness_state: freshnessState,
    expected_checkpoint: expected.iso,
    snapshot_age_minutes: snapshotAge,
    checkpoint_lag_minutes: checkpointLag,
  };
}

function normalizeLiveCode(market, value) {
  const raw = String(value || "").trim().toUpperCase();
  if (market === "a_share") {
    const clean = raw.replace(/^(?:SH|SZ)\./, "");
    return /^\d{6}$/.test(clean) ? clean : null;
  }
  if (market === "hk") {
    const match = raw.match(/^(\d{1,5})\.HK$/);
    return match ? `${match[1].padStart(4, "0")}.HK` : null;
  }
  if (market === "us") return /^[A-Z][A-Z0-9.-]{0,14}$/.test(raw) ? raw : null;
  return null;
}

function validIsoDate(value) {
  const text = String(value || "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
  const parsed = new Date(`${text}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === text;
}

function snapshotCandidateRows(snapshot, market) {
  const section = snapshot?.markets?.[market]
    || (market === "a_share" ? { decision: snapshot?.decision || {} } : {});
  const decision = section?.decision || {};
  const watchlist = Array.isArray(decision.watchlist) ? decision.watchlist : [];
  const rows = [decision.primary, decision.blocked_candidate, ...watchlist];
  for (const globalCandidate of [snapshot?.global_decision?.primary, snapshot?.global_decision?.research_priority]) {
    if (globalCandidate && globalCandidate.market === market) rows.push(globalCandidate);
  }
  return rows.filter((row) => row && typeof row === "object" && !Array.isArray(row));
}

function snapshotCandidateCodes(snapshot, market) {
  return new Set(
    snapshotCandidateRows(snapshot, market)
      .map((row) => normalizeLiveCode(market, row.code || row.symbol))
      .filter(Boolean),
  );
}

function snapshotCandidate(snapshot, market, code) {
  return snapshotCandidateRows(snapshot, market).find(
    (row) => normalizeLiveCode(market, row.code || row.symbol) === code,
  ) || null;
}

function sessionLabel(session) {
  return ({ pre: "盘前", regular: "盘中", post: "盘后", overnight: "夜盘", closed: "休市", unknown: "时段未知" })[session] || "时段未知";
}

function liveError(error, message, market, code, extra = {}) {
  return {
    contract_version: "live-quote-v1",
    ok: false,
    data_mode: "SCHEDULED_SNAPSHOT",
    quote_mode: "SCHEDULED_SNAPSHOT",
    error,
    message,
    market: market || null,
    code: code || null,
    price: null,
    current_price: null,
    change_pct: null,
    current_change_pct: null,
    volume: null,
    volume_unit: null,
    provider: null,
    provider_class: "SCHEDULED_SNAPSHOT",
    source: null,
    session: "unknown",
    session_label: sessionLabel("unknown"),
    price_kind: null,
    quote_status: "UNAVAILABLE",
    freshness: "unavailable",
    latency_seconds: null,
    is_realtime: false,
    is_stale: true,
    realtime_guaranteed: false,
    source_as_of: null,
    fetched_at: nowCN(),
    updated_at: null,
    snapshot_as_of: null,
    snapshot_generated_at: null,
    snapshot_key: null,
    next_refresh: nextScheduledRefresh(),
    rate_limit_status: "not_checked",
    cache_ttl_seconds: LIVE_CACHE_TTL_MS / 1000,
    ...extra,
  };
}

function apiAssetError() {
  return {
    ok: false,
    error: "API_ASSET_UNAVAILABLE",
    message: "已发布快照暂时无法读取，请稍后重试",
    time: nowCN(),
    data_mode: "scheduled_snapshot",
    quote_delivery_mode: "scheduled_snapshot",
    device_dependency: false,
  };
}

async function readAssetJson(env, path) {
  const response = await env.ASSETS.fetch(`https://assets.local${path}`);
  if (!response.ok) return null;
  const payload = await response.json();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`asset JSON is not an object: ${path}`);
  }
  return payload;
}

function summarizeDecision(decision) {
  const primary = decision.primary || decision.blocked_candidate;
  const summary = {
    action: decision.action,
    title: decision.title,
    message: decision.message,
    has_primary: Boolean(decision.primary),
  };
  if (primary) {
    const twoWeekRange = primary.estimated_2w_range;
    const twoDayRange = primary.estimated_2d_range;
    summary.code = primary.code;
    summary.name = primary.name;
    summary.confidence = primary.recommendation_degree || primary.confidence;
    summary.recommendation_degree = primary.recommendation_degree || primary.confidence;
    summary.estimated_2w_range = twoWeekRange && twoWeekRange.text;
    summary.estimated_2d_range = twoDayRange && twoDayRange.text;
    summary.entry_price = primary.entry_price || primary.price;
    summary.current_change_pct = primary.current_change_pct || primary.change_pct;
    summary.realtime_session = primary.realtime && primary.realtime.session_label;
    summary.risk_count = (primary.risk_flags || []).length;
    summary.hard_risk_count = primary.hard_risk_count || 0;
    summary.blocker_level = blockerLevel(decision, primary);
    summary.score = primary.score;
    summary.reason_tags = primary.reason_tags;
  }
  return summary;
}

function isGlobalTenDayDecision(decision) {
  return Boolean(
    decision
    && typeof decision === "object"
    && decision.contract_version === "global-10d-v1"
    && decision.decision_scope === "global_10d"
    && decision.action_basis === "strict_cross_market_gate_v1",
  );
}

function summarizePick(pick) {
  const legacySummary = summarizeDecision(pick.decision || {});
  const globalDecision = isGlobalTenDayDecision(pick.global_decision) ? pick.global_decision : null;
  const isGlobal = Boolean(globalDecision);
  const action = isGlobal ? globalDecision.action || "NO_VALID_PICK" : "LEGACY_ONLY";
  const summary = {
    target_date: pick.target_date,
    signal_date: pick.signal_date,
    generated_at: pick.generated_at,
    generated_label: pick.generated_label,
    snapshot_key: pick.snapshot_key,
    forecast_end_date: pick.forecast_end_date,
    forecast_horizon: pick.forecast_horizon,
    model_version: pick.model_version,
    history_kind: isGlobal ? "global_10d_v1" : "legacy_snapshot",
    decision_scope: isGlobal ? "global_10d" : "legacy_market_rules",
    action,
    title: isGlobal
      ? (action === "REVIEW_EXECUTABLE_PICK" ? "跨市场候选待复核" : "当前没有可执行跨市场候选")
      : "Legacy 规则快照",
    message: isGlobal ? (globalDecision.blocker_codes || []).join(" · ") : "PRE_GLOBAL_10D_CONTRACT",
    has_primary: isGlobal && Boolean(globalDecision.primary),
    global_decision: isGlobal ? {
      contract_version: globalDecision.contract_version,
      decision_scope: globalDecision.decision_scope,
      action: action,
      action_basis: globalDecision.action_basis,
      probability_status: globalDecision.probability_status || "UNAVAILABLE",
      probability: globalDecision.probability ?? null,
      calibrated: globalDecision.calibrated === true,
      primary: globalDecision.primary || null,
      research_priority: globalDecision.research_priority || null,
      blocker_codes: globalDecision.blocker_codes || [],
      automatic_external_evidence_count: globalDecision.automatic_external_evidence_count || 0,
    } : null,
    a_share_legacy: legacySummary,
  };
  const primary = globalDecision && globalDecision.primary;
  if (primary && typeof primary === "object") {
    summary.code = primary.code || primary.symbol;
    summary.name = primary.name;
    summary.probability = primary.probability ?? null;
    summary.expected_net_utility = primary.expected_net_utility ?? null;
    summary.transaction_cost = primary.transaction_cost ?? null;
    summary.tail_risk = primary.tail_risk ?? null;
    summary.model_id = primary.model_id || null;
  }
  if (pick.shadow_outcome && typeof pick.shadow_outcome === "object") {
    summary.shadow_outcome = pick.shadow_outcome;
  }
  // Public pick assets only retain outcomes that were joined from the isolated
  // executable ledger during the build, so this is safe to expose here.
  if (pick.outcome && typeof pick.outcome === "object") {
    summary.outcome = pick.outcome;
  }
  if (pick.formal_sample_status) summary.formal_sample_status = pick.formal_sample_status;
  if (pick.outcome_validation && typeof pick.outcome_validation === "object") {
    summary.outcome_validation = pick.outcome_validation;
  }
  if (pick.markets) {
    summary.markets = Object.fromEntries(
      Object.entries(pick.markets).map(([key, section]) => [key, summarizeDecision((section && section.decision) || {})]),
    );
  }
  return summary;
}

function historyKind(row) {
  if (row && row.history_kind === "global_10d_v1") return "global_10d_v1";
  return isGlobalTenDayDecision(row && row.global_decision) ? "global_10d_v1" : "legacy_snapshot";
}

function latestDecisionDays(rows) {
  const byDate = new Map();
  rows.forEach((row) => {
    const key = row.target_date || row.signal_date || row.snapshot_key || row.cache_key;
    const current = byDate.get(key);
    if (!current || (historyKind(current) !== "global_10d_v1" && historyKind(row) === "global_10d_v1")) {
      byDate.set(key, row);
    }
  });
  return [...byDate.values()];
}

function validSettledOutcome(row) {
  const primary = row?.global_decision?.primary;
  const outcome = row?.outcome;
  if (!primary || !outcome || String(outcome.status || "").toUpperCase() !== "SETTLED") return false;
  const generatedAt = Date.parse(row.generated_at || "");
  const entryAt = Date.parse(outcome.entry_at || "");
  const exitAt = Date.parse(outcome.exit_at || "");
  const settledAt = Date.parse(outcome.settled_at || "");
  const forecastEnd = Date.parse(`${String(row.forecast_end_date || "").slice(0, 10)}T00:00:00+08:00`);
  const netTotalReturn = outcome.net_total_return;
  const requiredNumbers = [outcome.entry_price, outcome.exit_price, outcome.gross_total_return, netTotalReturn, outcome.transaction_cost];
  const requiredStrings = [outcome.entry_source, outcome.exit_source, outcome.calendar_id, outcome.currency, outcome.fx_rate_source];
  return Boolean(
    primary.prediction_id
    && outcome.prediction_id === primary.prediction_id
    && primary.model_id
    && outcome.model_id === primary.model_id
    && primary.label_version
    && outcome.label_version === primary.label_version
    && requiredNumbers.every((value) => typeof value === "number" && Number.isFinite(value))
    && outcome.entry_price > 0
    && outcome.exit_price > 0
    && outcome.transaction_cost >= 0
    && requiredStrings.every((value) => typeof value === "string" && value.length > 0)
    && typeof outcome.corporate_action_adjusted === "boolean"
    && typeof outcome.positive_label === "boolean"
    && outcome.positive_label === (netTotalReturn > 0)
    && Number.isFinite(generatedAt)
    && Number.isFinite(entryAt)
    && entryAt >= generatedAt
    && Number.isFinite(exitAt)
    && Number.isFinite(settledAt)
    && Number.isFinite(forecastEnd)
    && exitAt >= forecastEnd
    && settledAt >= exitAt
  );
}

function emptyPerformance() {
  return {
    schema_version: null,
    cohort: null,
    sample_status: "UNAVAILABLE",
    reason: "HISTORY_PERFORMANCE_CONTRACT_UNAVAILABLE",
    minimum_reliable_sample: 20,
    sample_count: null,
    metrics: {},
  };
}

function emptyLedger(track, includedInExecutablePerformance) {
  return {
    track,
    contract_status: "UNAVAILABLE",
    reason: "HISTORY_LEDGER_CONTRACT_UNAVAILABLE",
    included_in_executable_performance: includedInExecutablePerformance,
  };
}

function historyMetadata(rows, days, view, returnedCount, evaluation = null) {
  const contractDays = days.filter((row) => historyKind(row) === "global_10d_v1");
  const legacyDays = days.filter((row) => historyKind(row) === "legacy_snapshot");
  const executableGroups = new Map();
  rows.forEach((row) => {
    const primary = row?.global_decision?.primary;
    if (
      historyKind(row) !== "global_10d_v1"
      || row?.global_decision?.action !== "REVIEW_EXECUTABLE_PICK"
      || !primary
      || typeof primary !== "object"
      || !primary.prediction_id
    ) return;
    if (!executableGroups.has(primary.prediction_id)) executableGroups.set(primary.prediction_id, []);
    executableGroups.get(primary.prediction_id).push(row);
  });
  const executable = [...executableGroups.values()];
  const outcomeStatus = (row) => String(row.outcome?.status || "").toUpperCase();
  const selectedCount = view === "raw" ? rows.length : days.length;
  const fallbackCounts = {
    executable_prediction_count: executable.length,
    pending_settlement_count: executable.filter((group) =>
      !group.some(validSettledOutcome) && group.some((row) => outcomeStatus(row) === "PENDING")).length,
    settled_sample_count: executable.filter((group) => group.some(validSettledOutcome)).length,
    invalid_settlement_count: 0,
    missing_outcome_count: executable.filter((group) =>
      !group.some(validSettledOutcome) && !group.some((row) => outcomeStatus(row) === "PENDING")).length,
  };
  const hasPrebuiltPerformance = Boolean(evaluation?.performance && typeof evaluation.performance === "object");
  const performance = hasPrebuiltPerformance ? evaluation.performance : emptyPerformance();
  const count = (key) => hasPrebuiltPerformance && Number.isInteger(performance[key]) && performance[key] >= 0
    ? performance[key]
    : fallbackCounts[key];
  return {
    view,
    raw_run_count: rows.length,
    decision_day_count: days.length,
    duplicate_run_count: Math.max(0, rows.length - days.length),
    global_contract_day_count: contractDays.length,
    legacy_day_count: legacyDays.length,
    no_valid_pick_day_count: contractDays.filter((row) => row.global_decision?.action === "NO_VALID_PICK").length,
    executable_prediction_count: count("executable_prediction_count"),
    pending_settlement_count: count("pending_settlement_count"),
    settled_sample_count: count("settled_sample_count"),
    invalid_settlement_count: count("invalid_settlement_count"),
    missing_outcome_count: count("missing_outcome_count"),
    performance,
    shadow_ledger: evaluation?.shadow_ledger && typeof evaluation.shadow_ledger === "object"
      ? evaluation.shadow_ledger
      : emptyLedger("SHADOW_RESEARCH", false),
    executable_ledger: evaluation?.executable_ledger && typeof evaluation.executable_ledger === "object"
      ? evaluation.executable_ledger
      : emptyLedger("EXECUTABLE_MODEL", true),
    returned_count: returnedCount,
    has_more: selectedCount > returnedCount,
  };
}

function blockerLevel(decision, primary) {
  if (decision.primary) return "pass";
  const message = decision.message || "";
  const hard = Number((primary && primary.hard_risk_count) || 0);
  const riskCount = ((primary && primary.risk_flags) || []).length;
  if (message.includes("指数环境触发高风险拦截") || hard >= 2 || riskCount >= 5) return "hard_block";
  if (message.includes("推荐度低于") || message.includes("预估下行空间")) return "soft_block";
  return "no_signal";
}

async function loadManifest(env) {
  const manifest = await readAssetJson(env, "/data/picks/manifest.json");
  return manifest && typeof manifest === "object" ? manifest : null;
}

async function loadPickByFile(env, file) {
  if (!file || file.includes("/") || !file.endsWith(".json")) return null;
  const pick = await readAssetJson(env, `/data/picks/${file}`);
  if (!pick) return null;
  return pick;
}

async function loadPickBySnapshot(env, snapshotKey) {
  if (!snapshotKey) return null;
  return loadPickByFile(env, snapshotKey);
}

async function latestPick(env) {
  const pick = await readAssetJson(env, "/data/picks/latest.json");
  if (!pick) return null;
  return pick;
}

async function pickForTarget(env, targetDate) {
  const manifest = await loadManifest(env);
  if (!manifest) return null;
  const summaries = Array.isArray(manifest.summaries) ? manifest.summaries : [];
  const match = summaries
    .filter((item) => item.target_date === targetDate && item.cache_key)
    .sort((a, b) => `${b.generated_at || ""}`.localeCompare(`${a.generated_at || ""}`))[0];
  if (match) return loadPickByFile(env, match.cache_key);
  return null;
}

function num(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function awareIsoTimestamp(value) {
  if (typeof value !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value.trim())) return false;
  return Number.isFinite(Date.parse(value));
}

function validSnapshotVolumeUnit(market, value) {
  if (typeof value !== "string") return false;
  const allowed = market === "a_share" ? new Set(["lot", "share", "shares"]) : new Set(["share", "shares"]);
  return allowed.has(value);
}

function strictSnapshotQuote(candidate, market) {
  const quote = candidate?.realtime;
  if (!quote || typeof quote !== "object" || Array.isArray(quote)) {
    throw new Error("published candidate has no realtime snapshot quote");
  }
  if (typeof quote.price !== "number" || !Number.isFinite(quote.price) || quote.price <= 0) {
    throw new Error("published realtime snapshot quote has no positive price");
  }
  if (!awareIsoTimestamp(quote.source_as_of)) {
    throw new Error("published realtime snapshot quote has no timezone-aware source_as_of");
  }
  if (!awareIsoTimestamp(quote.fetched_at)) {
    throw new Error("published realtime snapshot quote has no timezone-aware fetched_at");
  }
  if (!validSnapshotVolumeUnit(market, quote.volume_unit)) {
    throw new Error("published realtime snapshot quote has no valid volume_unit");
  }
  return quote;
}

function snapshotLiveContract(snapshot, market, code, current = new Date()) {
  const candidate = snapshotCandidate(snapshot, market, code);
  if (!candidate) throw new Error("candidate is not present in the published snapshot");
  const quote = strictSnapshotQuote(candidate, market);
  const quotePrice = quote.price;
  const sourceAsOf = quote.source_as_of;
  const fetchedAt = quote.fetched_at;
  const sourceEpoch = Date.parse(sourceAsOf || "");
  const nowEpoch = current instanceof Date ? current.getTime() : new Date(current).getTime();
  const latencySeconds = Number.isFinite(sourceEpoch) && Number.isFinite(nowEpoch)
    ? Math.max(0, Math.floor((nowEpoch - sourceEpoch) / 1000))
    : null;
  const session = quote.session || "unknown";
  const closed = session === "closed";
  const changePct = typeof quote.change_pct === "number" && Number.isFinite(quote.change_pct)
    ? quote.change_pct
    : null;
  const previousClose = typeof quote.previous_close === "number"
    && Number.isFinite(quote.previous_close)
    && quote.previous_close > 0
    ? quote.previous_close
    : null;
  const volume = typeof quote.volume === "number" && Number.isFinite(quote.volume) && quote.volume >= 0
    ? quote.volume
    : null;
  const snapshotState = snapshotFreshness(snapshot.generated_at, current).freshness_state;

  return {
    contract_version: "live-quote-v1",
    ok: true,
    data_mode: "SCHEDULED_SNAPSHOT",
    quote_mode: "SCHEDULED_SNAPSHOT",
    market,
    code,
    name: candidate.name || "",
    price: quotePrice,
    current_price: quotePrice,
    realtime_price: quotePrice,
    change_pct: changePct,
    current_change_pct: changePct,
    previous_close: previousClose,
    volume,
    volume_unit: quote.volume_unit,
    currency: quote.currency || candidate.currency || null,
    provider: "github_actions_snapshot",
    provider_class: "SCHEDULED_SNAPSHOT",
    source_tier: "scheduled_public_snapshot",
    primary_provider: "GITHUB_ACTIONS_SNAPSHOT",
    source: quote.source || "Published GitHub Actions snapshot",
    source_as_of: sourceAsOf,
    fetched_at: fetchedAt,
    updated_at: sourceAsOf || fetchedAt,
    session,
    session_label: quote.session_label || sessionLabel(session),
    price_kind: quote.price_kind || (closed ? "last_close" : "scheduled_snapshot"),
    quote_status: closed ? "LAST_CLOSE" : "DELAYED",
    freshness: closed ? "last_close" : "scheduled_snapshot",
    latency_seconds: latencySeconds,
    is_realtime: false,
    is_stale: quote.stale === true || snapshotState === "stale" || snapshotState === "unknown",
    realtime_guaranteed: false,
    fallback_reason: null,
    snapshot_as_of: snapshot.generated_at || null,
    snapshot_generated_at: snapshot.generated_at || null,
    snapshot_key: snapshot.snapshot_key || null,
    next_refresh: nextScheduledRefresh(current),
    cache_ttl_seconds: LIVE_CACHE_TTL_MS / 1000,
    kline: Array.isArray(candidate.kline) ? candidate.kline : [],
  };
}

async function handleApi(request, env) {
  const url = new URL(request.url);
  if (url.pathname === "/api/status") {
    const latest = await latestPick(env);
    const currentTime = nowCN();
    const current = new Date(currentTime);
    const freshness = snapshotFreshness(latest ? latest.generated_at : null, current);
    return json({
      ok: true,
      time: currentTime,
      platform: "cloudflare-workers",
      snapshot_generation: "github-actions",
      data_mode: "scheduled_snapshot",
      quote_delivery_mode: "scheduled_snapshot",
      device_dependency: false,
      schedule_time_zone: SHANGHAI_TIME_ZONE,
      schedule_primary_checkpoints: WEEKDAY_CHECKPOINTS.map(([hour, minute]) => `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`),
      schedule_fallback_checkpoints: FALLBACK_CHECKPOINTS.map(([hour, minute]) => `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`),
      recompute_supported: false,
      has_latest: Boolean(latest),
      latest_path: latest ? "/data/picks/latest.json" : null,
      schema_version: latest ? latest.schema_version || null : null,
      selector_mode: latest ? latest.selector_mode || null : null,
      model_version: latest ? latest.model_version || null : null,
      weights_version: latest ? latest.weights_version || null : null,
      universe_version: latest ? latest.universe_version || null : null,
      generated_at: latest ? latest.generated_at || null : null,
      snapshot_as_of: latest ? latest.generated_at || null : null,
      next_refresh: nextScheduledRefresh(current),
      snapshot_key: latest ? latest.snapshot_key || null : null,
      ...freshness,
    });
  }

  if (url.pathname === "/api/latest") {
    const latest = await latestPick(env);
    if (!latest) return json({ error: "暂无历史决策缓存" }, 404);
    return json(latest);
  }

  if (url.pathname === "/api/latest-summary") {
    const latest = await latestPick(env);
    if (!latest) return json({ error: "暂无历史决策缓存" }, 404);
    return json({
      ok: true,
      time: nowCN(),
      latest: summarizePick(latest),
    });
  }

  if (url.pathname === "/api/history") {
    const limit = Math.max(1, Math.min(Number(url.searchParams.get("limit") || 120), 1000));
    const view = url.searchParams.get("view") === "raw" ? "raw" : "daily";
    const manifest = await loadManifest(env);
    if (!manifest) return json({ ok: false, error: "HISTORY_MANIFEST_UNAVAILABLE" }, 503);
    const rows = Array.isArray(manifest.summaries) ? [...manifest.summaries] : [];
    rows.sort((a, b) =>
      `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`),
    );
    const days = latestDecisionDays(rows);
    const selectedRows = view === "raw" ? rows : days;
    const history = selectedRows.slice(0, limit);
    const latest = await latestPick(env);
    return json({
      ok: true,
      time: nowCN(),
      latest: latest ? summarizePick(latest) : null,
      meta: historyMetadata(rows, days, view, history.length, manifest.history_evaluation),
      history_evaluation: manifest.history_evaluation || null,
      history,
    });
  }

  if (url.pathname === "/api/pick") {
    if (url.searchParams.get("force") === "1") {
      return json(
        {
          error: "RECOMPUTE_NOT_SUPPORTED",
          message: "Cloudflare Worker 只提供不可变选股快照，不会在请求内重算模型。请运行 GitHub Actions 的 Deploy Cloudflare Worker workflow 生成新快照。",
          recompute_supported: false,
          snapshot_generation: "github-actions",
          workflow: ".github/workflows/deploy-worker.yml",
        },
        409,
      );
    }
    const snapshotKey = url.searchParams.get("snapshot");
    if (snapshotKey) {
      const snapshot = await loadPickBySnapshot(env, snapshotKey);
      if (!snapshot) return json({ error: "未找到指定历史快照" }, 404);
      return json(snapshot);
    }
    const targetDate = url.searchParams.get("date");
    if (targetDate && !validIsoDate(targetDate)) {
      return json({ error: "INVALID_DATE", message: "date 必须是有效的 YYYY-MM-DD 日期" }, 400);
    }
    const pick = targetDate ? await pickForTarget(env, targetDate) : await latestPick(env);
    if (!pick && targetDate) {
      return json({ error: "PICK_NOT_FOUND", message: `没有 ${targetDate} 的历史快照` }, 404);
    }
    if (!pick) {
      return json({ error: "暂无选股快照。请等待每日任务生成后再查看。" }, 404);
    }
    return json(pick);
  }

  if (url.pathname === "/api/live") {
    const market = String(url.searchParams.get("market") || "").trim();
    const requestedCode = url.searchParams.get("code") || "";
    if (!LIVE_MARKETS.has(market)) {
      return json(liveError("INVALID_MARKET", "market 仅支持 a_share、hk 或 us", market, requestedCode), 400);
    }
    const code = normalizeLiveCode(market, requestedCode);
    if (!code) {
      return json(liveError("INVALID_CODE", "股票代码格式不合法", market, requestedCode), 400);
    }
    let rateLimitStatus = env.LIVE_RATE_LIMITER ? "enforced" : "not_configured";
    if (env.LIVE_RATE_LIMITER) {
      try {
        const actor = request.headers.get("cf-connecting-ip") || "anonymous";
        const limited = await env.LIVE_RATE_LIMITER.limit({ key: `${actor}:${market}:${code}` });
        if (!limited || limited.success !== true) {
          return json(
            liveError("RATE_LIMITED", "行情刷新过于频繁，请稍后重试", market, code, {
              rate_limit_status: "limited",
            }),
            429,
            { "retry-after": "60" },
          );
        }
      } catch {
        rateLimitStatus = "unavailable_fail_open";
      }
    }
    let latest;
    try {
      latest = await latestPick(env);
    } catch {
      return json(
        liveError("LATEST_SNAPSHOT_UNAVAILABLE", "无法读取当前候选池", market, code, {
          rate_limit_status: rateLimitStatus,
          asset_status: "unavailable",
        }),
        503,
      );
    }
    if (!latest) {
      return json(
        liveError("LATEST_SNAPSHOT_UNAVAILABLE", "无法校验当前候选池", market, code, {
          rate_limit_status: rateLimitStatus,
          asset_status: "missing",
        }),
        503,
      );
    }
    if (!snapshotCandidateCodes(latest, market).has(code)) {
      return json(
        liveError("LIVE_CODE_NOT_IN_CURRENT_SNAPSHOT", "仅允许查询当前快照候选股", market, code, {
          rate_limit_status: rateLimitStatus,
          snapshot_as_of: latest.generated_at || null,
          snapshot_generated_at: latest.generated_at || null,
          snapshot_key: latest.snapshot_key || null,
        }),
        404,
      );
    }
    try {
      const payload = {
        ...snapshotLiveContract(latest, market, code),
        rate_limit_status: rateLimitStatus,
      };
      return json(payload);
    } catch (error) {
      const detail = String(error && error.message ? error.message : error);
      return json({
        ...liveError("SNAPSHOT_QUOTE_UNAVAILABLE", "已发布快照没有可用行情", market, code, {
          rate_limit_status: rateLimitStatus,
          snapshot_as_of: latest.generated_at || null,
          snapshot_generated_at: latest.generated_at || null,
          snapshot_key: latest.snapshot_key || null,
        }),
        detail,
      }, 502);
    }
  }

  return json({ error: "Not found" }, 404);
}

export default {
  async fetch(request, env) {
    const redirect = httpsRedirect(request, env);
    if (redirect) return withSecurityHeaders(redirect);

    const url = new URL(request.url);
    let response;
    try {
      if (url.pathname.startsWith("/api/")) {
        response = await handleApi(request, env);
      } else {
        response = await env.ASSETS.fetch(request);
      }
    } catch {
      if (url.pathname === "/api/live") {
        response = json(liveError("LATEST_SNAPSHOT_UNAVAILABLE", "无法读取当前候选池", null, null, {
          asset_status: "unavailable",
        }), 503);
      } else if (url.pathname.startsWith("/api/")) {
        response = json(apiAssetError(), 503);
      } else {
        response = new Response("Service unavailable", {
          status: 503,
          headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
        });
      }
    }
    return withSecurityHeaders(response);
  },
};

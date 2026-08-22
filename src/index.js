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
  [8, 58],
  [9, 58],
  [10, 58],
  [12, 58],
  [13, 58],
  [14, 58],
  [21, 28],
  [23, 58],
];
const LIVE_MARKETS = new Set(["a_share", "hk", "us"]);
const LIVE_CACHE_TTL_MS = 10_000;
const LIVE_FETCH_TIMEOUT_MS = 4_000;
const GATEWAY_FETCH_TIMEOUT_MS = 3_000;
const LIVE_MAX_ACTIVE_AGE_SECONDS = 120;
const liveQuoteCache = new Map();

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

function isoFromEpoch(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  const millis = parsed > 1_000_000_000_000 ? parsed : parsed * 1000;
  const date = new Date(millis);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function isoFromCnTimestamp(value) {
  const match = String(value || "").match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})/);
  if (!match) return null;
  const [, year, month, day, hour, minute, second] = match;
  return `${year}-${month}-${day}T${hour}:${minute}:${second}+08:00`;
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

function snapshotCandidateCodes(snapshot, market) {
  const section = snapshot?.markets?.[market]
    || (market === "a_share" ? { decision: snapshot?.decision || {} } : {});
  const decision = section?.decision || {};
  const rows = [decision.primary, decision.blocked_candidate, ...(decision.watchlist || [])];
  for (const globalCandidate of [snapshot?.global_decision?.primary, snapshot?.global_decision?.research_priority]) {
    if (globalCandidate && globalCandidate.market === market) rows.push(globalCandidate);
  }
  return new Set(rows.filter(Boolean).map((row) => normalizeLiveCode(market, row.code || row.symbol)).filter(Boolean));
}

async function fetchWithTimeout(input, init = {}, timeoutMs = LIVE_FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function sessionLabel(session) {
  return ({ pre: "盘前", regular: "盘中", post: "盘后", overnight: "夜盘", closed: "休市", unknown: "时段未知" })[session] || "时段未知";
}

function aShareSession(current = new Date()) {
  const parts = shanghaiDateParts(current);
  const weekday = calendarWeekday(parts);
  if (weekday === 0 || weekday === 6) return "closed";
  const minute = parts.hour * 60 + parts.minute;
  if (minute >= 9 * 60 + 15 && minute < 9 * 60 + 30) return "pre";
  if ((minute >= 9 * 60 + 30 && minute < 11 * 60 + 30) || (minute >= 13 * 60 && minute < 15 * 60)) return "regular";
  return "closed";
}

function yahooPeriod(meta, name) {
  const current = meta?.currentTradingPeriod?.[name];
  if (current && Number.isFinite(Number(current.start)) && Number.isFinite(Number(current.end))) return current;
  const periods = meta?.tradingPeriods?.[name];
  const first = Array.isArray(periods) ? (Array.isArray(periods[0]) ? periods[0][0] : periods[0]) : null;
  return first && Number.isFinite(Number(first.start)) && Number.isFinite(Number(first.end)) ? first : null;
}

function yahooSession(meta, epochSeconds = Math.floor(Date.now() / 1000)) {
  const state = String(meta?.marketState || "").toUpperCase();
  if (["PRE", "PREPRE"].includes(state)) return "pre";
  if (state === "REGULAR") return "regular";
  if (["POST", "POSTPOST"].includes(state)) return "post";
  if (state === "OVERNIGHT") return "overnight";
  for (const name of ["pre", "regular", "post"]) {
    const period = yahooPeriod(meta, name);
    if (period && epochSeconds >= Number(period.start) && epochSeconds < Number(period.end)) return name;
  }
  return "closed";
}

function yahooPriceKind(meta, epochSeconds) {
  for (const [name, label] of [["pre", "pre_market"], ["regular", "regular"], ["post", "after_hours"]]) {
    const period = yahooPeriod(meta, name);
    if (period && epochSeconds >= Number(period.start) && epochSeconds <= Number(period.end)) return label;
  }
  return "regular";
}

function quoteTiming(sourceAsOf, session) {
  const parsed = Date.parse(sourceAsOf || "");
  const latencySeconds = Number.isFinite(parsed) ? Math.max(0, Math.floor((Date.now() - parsed) / 1000)) : null;
  const active = ["pre", "regular", "post", "overnight"].includes(session);
  if (!Number.isFinite(parsed)) {
    return { quote_status: "DELAYED", freshness: "stale", latency_seconds: latencySeconds, is_realtime: false, is_stale: true };
  }
  if (!active) {
    return { quote_status: "LAST_CLOSE", freshness: "last_close", latency_seconds: latencySeconds, is_realtime: false, is_stale: false };
  }
  const fresh = latencySeconds <= LIVE_MAX_ACTIVE_AGE_SECONDS;
  return {
    quote_status: fresh ? "REALTIME" : "DELAYED",
    freshness: fresh ? "fresh" : "stale",
    latency_seconds: latencySeconds,
    is_realtime: fresh,
    is_stale: !fresh,
  };
}

function liveContract(payload) {
  const timing = quoteTiming(payload.source_as_of, payload.session);
  return {
    contract_version: "live-quote-v1",
    ok: true,
    ...payload,
    ...timing,
    session_label: payload.session_label || sessionLabel(payload.session),
    fetched_at: payload.fetched_at || nowCN(),
    updated_at: payload.source_as_of || payload.fetched_at || nowCN(),
    cache_ttl_seconds: LIVE_CACHE_TTL_MS / 1000,
  };
}

function liveError(error, message, market, code) {
  return {
    contract_version: "live-quote-v1",
    ok: false,
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
    source: null,
    session: "unknown",
    session_label: sessionLabel("unknown"),
    price_kind: null,
    quote_status: "UNAVAILABLE",
    freshness: "unavailable",
    latency_seconds: null,
    is_realtime: false,
    is_stale: true,
    source_as_of: null,
    fetched_at: nowCN(),
    updated_at: null,
    cache_ttl_seconds: LIVE_CACHE_TTL_MS / 1000,
  };
}

function bestEffortContract(payload, fallbackReason = null) {
  return {
    ...payload,
    provider_class: "PUBLIC_BEST_EFFORT",
    source_tier: "public_best_effort_1m",
    quote_status: payload.session === "closed" ? "LAST_CLOSE" : "DELAYED",
    freshness: payload.session === "closed" ? "last_close" : "best_effort",
    is_realtime: false,
    is_stale: payload.session !== "closed",
    realtime_guaranteed: false,
    primary_provider: "FUTU_OPEND",
    fallback_reason: fallbackReason,
  };
}

function futuGatewayContract(quote) {
  const price = num(quote?.price);
  if (!quote || price <= 0 || quote.quote_status === "UNAVAILABLE") {
    throw new Error("Futu gateway returned no usable quote");
  }
  return liveContract({
    market: quote.market,
    code: quote.code,
    name: quote.name || "",
    price,
    current_price: price,
    realtime_price: price,
    change_pct: num(quote.change_pct),
    current_change_pct: num(quote.change_pct),
    previous_close: num(quote.previous_close),
    bid: Number.isFinite(Number(quote.bid)) ? Number(quote.bid) : null,
    ask: Number.isFinite(Number(quote.ask)) ? Number(quote.ask) : null,
    volume: num(quote.volume),
    volume_unit: quote.volume_unit || "share",
    provider: "FUTU_OPEND",
    provider_class: "LICENSED_REALTIME",
    source_tier: quote.source_tier || "licensed_exchange_feed",
    session: quote.session || "unknown",
    session_label: quote.session_label || sessionLabel(quote.session),
    price_kind: quote.price_kind || "last_trade",
    source: "Futu OpenD licensed quote gateway",
    source_as_of: quote.source_as_of,
    fetched_at: quote.fetched_at || nowCN(),
    kline: [],
    realtime_guaranteed: quote.is_realtime === true,
    gateway_latency_ms: quote.gateway_latency_ms ?? null,
  });
}

async function futuGatewayLive(env, market, code) {
  const baseUrl = String(env?.REALTIME_GATEWAY_URL || "").replace(/\/$/, "");
  const token = String(env?.QUOTE_GATEWAY_TOKEN || "");
  if (!baseUrl || !token) throw new Error("gateway not configured");
  const target = new URL(`${baseUrl}/v1/quotes`);
  target.searchParams.set("symbols", `${market}:${code}`);
  const response = await fetchWithTimeout(target, {
    headers: { authorization: `Bearer ${token}`, accept: "application/json" },
  }, GATEWAY_FETCH_TIMEOUT_MS);
  if (!response.ok) throw new Error(`gateway ${response.status}`);
  const payload = await response.json();
  const quote = Array.isArray(payload?.quotes) ? payload.quotes[0] : null;
  const contract = futuGatewayContract({ ...quote, gateway_latency_ms: payload?.gateway_latency_ms });
  return {
    ...contract,
    quote_status: quote.quote_status || contract.quote_status,
    is_realtime: quote.is_realtime === true && contract.is_realtime,
    is_stale: quote.is_stale === true || contract.is_stale,
    realtime_guaranteed: quote.is_realtime === true && contract.is_realtime,
  };
}

async function readAssetJson(env, path) {
  const response = await env.ASSETS.fetch(`https://assets.local${path}`);
  if (!response.ok) return null;
  return response.json();
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

function historyMetadata(rows, days, view, returnedCount) {
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
  return {
    view,
    raw_run_count: rows.length,
    decision_day_count: days.length,
    duplicate_run_count: Math.max(0, rows.length - days.length),
    global_contract_day_count: contractDays.length,
    legacy_day_count: legacyDays.length,
    no_valid_pick_day_count: contractDays.filter((row) => row.global_decision?.action === "NO_VALID_PICK").length,
    executable_prediction_count: executable.length,
    pending_settlement_count: executable.filter((group) =>
      !group.some(validSettledOutcome) && group.some((row) => outcomeStatus(row) === "PENDING")).length,
    settled_sample_count: executable.filter((group) => group.some(validSettledOutcome)).length,
    missing_outcome_count: executable.filter((group) =>
      !group.some(validSettledOutcome) && !group.some((row) => outcomeStatus(row) === "PENDING")).length,
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

function eastmoneySecid(code) {
  const clean = String(code || "").replace(/\D/g, "");
  return `${clean.startsWith("6") ? "1" : "0"}.${clean}`;
}

function num(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

async function eastmoneyJson(url, params) {
  const target = new URL(url);
  Object.entries(params || {}).forEach(([key, value]) => target.searchParams.set(key, value));
  const response = await fetchWithTimeout(target, {
    headers: {
      "user-agent": "Mozilla/5.0",
      referer: "https://quote.eastmoney.com/",
    },
  });
  if (!response.ok) throw new Error(`Eastmoney ${response.status}`);
  return response.json();
}

async function aShareKline(code, limit = 70) {
  const payload = await eastmoneyJson("https://push2his.eastmoney.com/api/qt/stock/kline/get", {
    secid: eastmoneySecid(code),
    fields1: "f1,f2,f3,f4,f5,f6",
    fields2: "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    klt: "101",
    fqt: "1",
    end: "20500101",
    lmt: String(limit),
  });
  const rows = ((payload.data || {}).klines || []).map((line) => {
    const parts = String(line).split(",");
    return {
      date: parts[0],
      open: num(parts[1]),
      close: num(parts[2]),
      high: num(parts[3]),
      low: num(parts[4]),
      volume: num(parts[5]),
      amount: num(parts[6]),
      change_pct: num(parts[8]),
      turnover: num(parts[10]),
    };
  });
  return rows.filter((row) => row.date && row.close > 0);
}

function marketPrefix(code) {
  const clean = String(code || "").replace(/\D/g, "");
  return clean.startsWith("6") ? "sh" : "sz";
}

async function tencentAQuote(code) {
  const symbol = `${marketPrefix(code)}${String(code || "").replace(/\D/g, "")}`;
  const response = await fetchWithTimeout(`https://qt.gtimg.cn/q=${symbol}`, {
    headers: { "user-agent": "Mozilla/5.0", referer: "https://gu.qq.com/" },
  });
  if (!response.ok) throw new Error(`Tencent quote ${response.status}`);
  const buffer = await response.arrayBuffer();
  const text = new TextDecoder("gbk").decode(buffer);
  const body = (text.split('"')[1] || "").split("~");
  if (body.length < 53) throw new Error("Tencent quote empty");
  return {
    code: String(code || ""),
    name: body[1] || "",
    price: num(body[3]),
    previous_close: num(body[4]),
    change_pct: num(body[32]),
    high: num(body[33]),
    low: num(body[34]),
    volume: num(body[36]),
    amount: num(body[37]),
    source_as_of: isoFromCnTimestamp(body[30]),
    source: "Tencent realtime quote",
  };
}

async function tencentAKline(code, limit = 70) {
  const symbol = `${marketPrefix(code)}${String(code || "").replace(/\D/g, "")}`;
  const target = new URL("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get");
  target.searchParams.set("param", `${symbol},day,,,${limit},qfq`);
  const response = await fetchWithTimeout(target, {
    headers: { "user-agent": "Mozilla/5.0", referer: "https://gu.qq.com/" },
  });
  if (!response.ok) throw new Error(`Tencent kline ${response.status}`);
  const payload = await response.json();
  const data = ((payload.data || {})[symbol] || {});
  const rows = (data.qfqday || data.day || []).map((parts) => ({
    date: parts[0],
    open: num(parts[1]),
    close: num(parts[2]),
    high: num(parts[3]),
    low: num(parts[4]),
    volume: num(parts[5]),
  }));
  return rows.filter((row) => row.date && row.close > 0);
}

async function aShareLive(code) {
  let data = {};
  let kline = [];
  let source = "Eastmoney realtime quote";
  let sourceAsOf = null;
  try {
    const [quotePayload, rows] = await Promise.all([
      eastmoneyJson("https://push2.eastmoney.com/api/qt/stock/get", {
        secid: eastmoneySecid(code),
        fields: "f43,f44,f45,f46,f47,f48,f57,f58,f60,f86,f168,f170",
        fltt: "2",
      }),
      aShareKline(code),
    ]);
    data = quotePayload.data || {};
    kline = rows;
    sourceAsOf = isoFromEpoch(data.f86);
  } catch {
    const [quote, rows] = await Promise.all([tencentAQuote(code), tencentAKline(code)]);
    data = {
      f43: quote.price,
      f47: quote.volume,
      f57: quote.code,
      f58: quote.name,
      f60: quote.previous_close,
      f170: quote.change_pct,
    };
    kline = rows;
    source = quote.source;
    sourceAsOf = quote.source_as_of;
  }
  const latest = kline[kline.length - 1] || {};
  const price = num(data.f43) || num(latest.close);
  if (price <= 0) throw new Error("A-share quote has no valid price");
  const fetchedAt = nowCN();
  const session = aShareSession();
  return liveContract({
    market: "a_share",
    code: String(data.f57 || code),
    name: data.f58 || "",
    price,
    current_price: price,
    realtime_price: price,
    change_pct: num(data.f170) || num(latest.change_pct),
    current_change_pct: num(data.f170) || num(latest.change_pct),
    volume: num(data.f47) || num(latest.volume),
    volume_unit: "lot",
    previous_close: num(data.f60),
    provider: source === "Tencent realtime quote" ? "tencent" : "eastmoney",
    session,
    session_label: sessionLabel(session),
    price_kind: session === "pre" ? "pre_market" : session === "closed" ? "last_close" : "regular",
    source,
    source_as_of: sourceAsOf,
    fetched_at: fetchedAt,
    kline,
  });
}

async function yahooLive(symbol, market) {
  const target = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=1d&interval=1m&includePrePost=true&events=div%2Csplits`;
  const response = await fetchWithTimeout(target, { headers: { "user-agent": "Mozilla/5.0", accept: "application/json" } });
  if (!response.ok) throw new Error(`Yahoo ${response.status}`);
  const payload = await response.json();
  const result = (((payload.chart || {}).result || [])[0]) || {};
  const meta = result.meta || {};
  const quote = (((result.indicators || {}).quote || [])[0]) || {};
  const timestamps = result.timestamp || [];
  const closes = quote.close || [];
  const volumes = quote.volume || [];
  let price = 0;
  let sourceEpoch = 0;
  let latestVolume = 0;
  for (let index = closes.length - 1; index >= 0; index -= 1) {
    const close = num(closes[index]);
    const timestamp = num(timestamps[index]);
    if (close > 0 && timestamp > 0) {
      price = close;
      sourceEpoch = timestamp;
      latestVolume = num(volumes[index]);
      break;
    }
  }
  if (!price) {
    price = num(meta.regularMarketPrice);
    sourceEpoch = num(meta.regularMarketTime);
  }
  if (!price || !sourceEpoch) throw new Error("Yahoo intraday quote is empty");
  const previous = num(meta.chartPreviousClose) || num(meta.previousClose) || num(meta.regularMarketPreviousClose);
  const changePct = previous ? ((price - previous) / previous) * 100 : 0;
  const sourceAsOf = isoFromEpoch(sourceEpoch);
  const fetchedAt = nowCN();
  const session = yahooSession(meta);
  return liveContract({
    market,
    code: symbol,
    name: meta.shortName || meta.longName || "",
    price,
    current_price: price,
    realtime_price: price,
    change_pct: changePct,
    current_change_pct: changePct,
    previous_close: previous,
    volume: num(meta.regularMarketVolume) || latestVolume,
    volume_unit: "share",
    provider: "yahoo_finance",
    session,
    session_label: sessionLabel(session),
    price_kind: yahooPriceKind(meta, sourceEpoch),
    source: "Yahoo Finance 1m includePrePost",
    source_as_of: sourceAsOf,
    fetched_at: fetchedAt,
    kline: [],
  });
}

async function publicFallbackLive(market, code, reason) {
  const payload = market === "a_share"
    ? await aShareLive(code)
    : await yahooLive(code, market === "hk" ? "hk" : "us");
  return bestEffortContract(payload, reason);
}

async function liveStock(env, market, code) {
  const key = `${market}:${code}`;
  const cached = liveQuoteCache.get(key);
  if (cached && cached.expires_at > Date.now()) return cached.payload;
  if (cached) liveQuoteCache.delete(key);
  let payload;
  try {
    payload = await futuGatewayLive(env, market, code);
  } catch (error) {
    const reason = String(error?.message || "gateway unavailable").slice(0, 80);
    payload = await publicFallbackLive(market, code, reason);
  }
  liveQuoteCache.set(key, { expires_at: Date.now() + LIVE_CACHE_TTL_MS, payload });
  return payload;
}

async function handleApi(request, env) {
  const url = new URL(request.url);
  if (url.pathname === "/api/status") {
    const latest = await latestPick(env);
    const freshness = snapshotFreshness(latest ? latest.generated_at : null);
    return json({
      ok: true,
      time: nowCN(),
      platform: "cloudflare-workers",
      snapshot_generation: "github-actions",
      recompute_supported: false,
      has_latest: Boolean(latest),
      latest_path: latest ? "/data/picks/latest.json" : null,
      schema_version: latest ? latest.schema_version || null : null,
      selector_mode: latest ? latest.selector_mode || null : null,
      model_version: latest ? latest.model_version || null : null,
      weights_version: latest ? latest.weights_version || null : null,
      universe_version: latest ? latest.universe_version || null : null,
      realtime_gateway_configured: Boolean(env.REALTIME_GATEWAY_URL && env.QUOTE_GATEWAY_TOKEN),
      realtime_primary_provider: "FUTU_OPEND",
      realtime_fallback_provider_class: "PUBLIC_BEST_EFFORT",
      generated_at: latest ? latest.generated_at || null : null,
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
      meta: historyMetadata(rows, days, view, history.length),
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
    if (env.LIVE_RATE_LIMITER) {
      const actor = request.headers.get("cf-connecting-ip") || "anonymous";
      const limited = await env.LIVE_RATE_LIMITER.limit({ key: `${actor}:${market}:${code}` });
      if (!limited.success) {
        return json(
          liveError("RATE_LIMITED", "行情刷新过于频繁，请稍后重试", market, code),
          429,
          { "retry-after": "60" },
        );
      }
    }
    const latest = await latestPick(env);
    if (!latest) {
      return json(liveError("LATEST_SNAPSHOT_UNAVAILABLE", "无法校验当前候选池", market, code), 503);
    }
    if (!snapshotCandidateCodes(latest, market).has(code)) {
      return json(liveError("LIVE_CODE_NOT_IN_CURRENT_SNAPSHOT", "仅允许查询当前快照候选股", market, code), 404);
    }
    try {
      const payload = await liveStock(env, market, code);
      return json(payload);
    } catch (error) {
      const detail = String(error && error.name === "AbortError" ? "upstream timeout" : error && error.message ? error.message : error);
      return json({ ...liveError("REALTIME_UNAVAILABLE", "实时行情暂不可用", market, code), detail }, 502);
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
    if (url.pathname.startsWith("/api/")) {
      response = await handleApi(request, env);
    } else {
      response = await env.ASSETS.fetch(request);
    }
    return withSecurityHeaders(response);
  },
};

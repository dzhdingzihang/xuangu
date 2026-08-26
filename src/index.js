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
const MAX_QUALIFIED_SUMMARY_CANDIDATES = 20;
const CURRENT_PRODUCTION_MODEL_VERSION = "smart-selector-2026-08-26.2-dual-track-rule";
const PRODUCTION_RULE_V3_ACTION_BASIS = "dual_track_candidate_qualification_v3";
const PRODUCTION_RULE_V3_MODEL_ID = "ten-day-audited-rule-ensemble-v3";
const PRODUCTION_MODEL_AVAILABILITY_BLOCKERS = new Set([
  "TEN_DAY_MODEL_NOT_READY",
  "TEN_DAY_PREDICTION_MISSING",
]);
const PRODUCTION_EVENT_MARKET_POLICY = {
  a_share: { minimumLegacy: 64, maximumDownside: 8, minimumUpside: 5 },
  hk: { minimumLegacy: 63, maximumDownside: 8, minimumUpside: 5 },
  us: { minimumLegacy: 64, maximumDownside: 10, minimumUpside: 6 },
};
const PRODUCTION_QUALITY_MARKET_POLICY = {
  a_share: { minimumLegacy: 66, maximumDownside: 6, minimumUpside: 6 },
  hk: { minimumLegacy: 67, maximumDownside: 6, minimumUpside: 6 },
  us: { minimumLegacy: 68, maximumDownside: 7.5, minimumUpside: 6.5 },
};
const PRODUCTION_EVENT_MAX_RANK_FRACTION = 0.20;
const PRODUCTION_EVENT_MIN_RISK_REWARD = 1.20;
const PRODUCTION_QUALITY_MAX_RANK_FRACTION = 0.10;
const PRODUCTION_QUALITY_MIN_DATA_QUALITY = 95;
const PRODUCTION_QUALITY_MIN_RISK_REWARD = 1.50;
const PRODUCTION_QUALITY_MIN_SCORE = 72;
const PRODUCTION_RULE_INPUT_ROW_FIELDS = [
  "name", "blocker_codes", "legacy_signal", "legacy_recommendation_degree",
  "v2_rank", "v2_rank_universe_size", "event_candidate_scanned",
  "verified_positive_event_ids", "entry_price", "calendar_id", "calendar_version",
  "entry_trade_date", "forecast_end_trade_date",
];

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

function contractDeepEqual(left, right) {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left)
      && Array.isArray(right)
      && left.length === right.length
      && left.every((value, index) => contractDeepEqual(value, right[index]));
  }
  if (
    !left || !right
    || typeof left !== "object" || typeof right !== "object"
    || Array.isArray(left) || Array.isArray(right)
  ) return false;
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key, index) => (
      key === rightKeys[index]
      && contractDeepEqual(left[key], right[key])
    ));
}

function finiteRuleNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function clampRuleNumber(value, lower = 0, upper = 100) {
  return Math.max(lower, Math.min(upper, value));
}

function roundRuleNumber(value, digits = 2) {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
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

// Web Crypto is asynchronous, while the production-decision gate is a
// synchronous parser.  Keep this small SHA-256 implementation local so the
// Worker can independently reproduce Python's stable qualification id instead
// of trusting an id copied into the published decision.
function sha256RuleText(value) {
  const bytes = new TextEncoder().encode(String(value));
  const bitLength = bytes.length * 8;
  const paddedLength = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  const high = Math.floor(bitLength / 0x100000000);
  const low = bitLength >>> 0;
  view.setUint32(paddedLength - 8, high, false);
  view.setUint32(paddedLength - 4, low, false);

  const constants = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  const state = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ];
  const rotateRight = (word, bits) => (word >>> bits) | (word << (32 - bits));
  const words = new Uint32Array(64);

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + index * 4, false);
    }
    for (let index = 16; index < 64; index += 1) {
      const left = words[index - 15];
      const right = words[index - 2];
      const sigma0 = rotateRight(left, 7) ^ rotateRight(left, 18) ^ (left >>> 3);
      const sigma1 = rotateRight(right, 17) ^ rotateRight(right, 19) ^ (right >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = state;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choose = (e & f) ^ (~e & g);
      const temporary1 = (h + sum1 + choose + constants[index] + words[index]) >>> 0;
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temporary2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temporary1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temporary1 + temporary2) >>> 0;
    }
    state[0] = (state[0] + a) >>> 0;
    state[1] = (state[1] + b) >>> 0;
    state[2] = (state[2] + c) >>> 0;
    state[3] = (state[3] + d) >>> 0;
    state[4] = (state[4] + e) >>> 0;
    state[5] = (state[5] + f) >>> 0;
    state[6] = (state[6] + g) >>> 0;
    state[7] = (state[7] + h) >>> 0;
  }
  return state.map((word) => word.toString(16).padStart(8, "0")).join("");
}

function stableV3QualificationId(snapshot, market, code) {
  const automation = snapshot?.automation;
  const scheduledSlot = automation && typeof automation === "object" && !Array.isArray(automation)
    ? automation.scheduled_slot
    : null;
  const target = snapshot?.target_date || snapshot?.signal_date || "";
  const identity = [
    "production-rule-10d-v1",
    PRODUCTION_RULE_V3_MODEL_ID,
    scheduledSlot || target,
    target,
    market,
    code,
  ].map((item) => String(item || "")).join("|");
  return `qual_${sha256RuleText(identity).slice(0, 24)}`;
}

function frozenV3SourceProjection(source, index) {
  const result = {
    input_index: index,
    market: ruleText(source?.market),
    code: ruleText(source?.code || source?.symbol),
  };
  for (const field of PRODUCTION_RULE_INPUT_ROW_FIELDS) {
    if (Object.hasOwn(source, field)) result[field] = source[field];
  }
  if (source?.priority_components && typeof source.priority_components === "object"
    && !Array.isArray(source.priority_components)
    && Object.hasOwn(source.priority_components, "data_quality")) {
    result.priority_components = { data_quality: source.priority_components.data_quality };
  }
  if (source?.estimated_10d_range && typeof source.estimated_10d_range === "object"
    && !Array.isArray(source.estimated_10d_range)) {
    result.estimated_10d_range = Object.fromEntries(
      ["low_pct", "high_pct"]
        .filter((field) => Object.hasOwn(source.estimated_10d_range, field))
        .map((field) => [field, source.estimated_10d_range[field]]),
    );
  }
  return result;
}

function v3RuleInputContext(snapshot) {
  const sources = snapshot?.global_decision?.evaluated_candidates;
  const inputs = snapshot?.production_rule_inputs;
  const inputRows = inputs?.rows;
  if (
    !Array.isArray(sources)
    || !inputs || typeof inputs !== "object" || Array.isArray(inputs)
    || inputs.contract_version !== "production-rule-inputs-v1"
    || inputs.action_basis !== PRODUCTION_RULE_V3_ACTION_BASIS
    || inputs.rule_model_id !== PRODUCTION_RULE_V3_MODEL_ID
    || !Array.isArray(inputRows)
    || !Number.isInteger(inputs.evaluated_candidate_count)
    || inputs.evaluated_candidate_count !== sources.length
    || inputRows.length !== sources.length
  ) return null;
  const byIdentity = new Map();
  for (let index = 0; index < sources.length; index += 1) {
    const source = sources[index];
    const input = inputRows[index];
    if (
      !source || typeof source !== "object" || Array.isArray(source)
      || !input || typeof input !== "object" || Array.isArray(input)
      || input.input_index !== index
    ) return null;
    const market = ruleText(source.market);
    const code = ruleText(source.code || source.symbol);
    if (
      !market || !code
      || input.market !== market
      || input.code !== code
      || typeof input.source_candidate_present !== "boolean"
    ) return null;
    const frozenInput = Object.fromEntries(
      Object.entries(input).filter(([field]) => ![
        "source_candidate_present",
        "source_data_quality_score",
        "candidate_snapshot",
      ].includes(field)),
    );
    if (!contractDeepEqual(frozenInput, frozenV3SourceProjection(source, index))) return null;
    const key = `${market}:${code}`;
    if (byIdentity.has(key)) return null;
    byIdentity.set(key, { source, input });
  }
  return { sources, inputRows, byIdentity };
}

function expectedV3RuleEvaluation(snapshot, input) {
  const source = input;
  const market = ruleText(source?.market);
  const code = ruleText(source?.code || source?.symbol);
  const eventPolicy = PRODUCTION_EVENT_MARKET_POLICY[market];
  const qualityPolicy = PRODUCTION_QUALITY_MARKET_POLICY[market];
  if (!market || !code || !eventPolicy || !qualityPolicy) return null;

  const sourceBlockers = dedupeRuleStrings(source.blocker_codes);
  const sharedBlockers = sourceBlockers
    ? sourceBlockers.filter((codeValue) => !PRODUCTION_MODEL_AVAILABILITY_BLOCKERS.has(codeValue))
    : ["SOURCE_BLOCKER_CODES_INVALID"];
  const eventBlockers = [...sharedBlockers];
  const qualityBlockers = sharedBlockers.filter((codeValue) => codeValue !== "VERIFIED_POSITIVE_EVENT_MISSING");
  const blockBoth = (codeValue) => {
    eventBlockers.push(codeValue);
    qualityBlockers.push(codeValue);
  };
  if (input?.source_candidate_present !== true) blockBoth("CANDIDATE_SNAPSHOT_MISSING");

  let recommendation = source.legacy_recommendation_degree;
  if (!finiteRuleNumber(recommendation)) {
    recommendation = 0;
    blockBoth("LEGACY_RECOMMENDATION_INVALID");
  } else {
    recommendation = clampRuleNumber(recommendation);
    if (recommendation < eventPolicy.minimumLegacy) eventBlockers.push("LEGACY_RECOMMENDATION_BELOW_THRESHOLD");
    if (recommendation < qualityPolicy.minimumLegacy) qualityBlockers.push("QUALITY_LEGACY_BELOW_THRESHOLD");
  }

  const rank = source.v2_rank;
  const universe = source.v2_rank_universe_size;
  const rankValid = finiteRuleNumber(rank)
    && finiteRuleNumber(universe)
    && universe >= 1
    && rank >= 1
    && rank <= universe;
  let rankFraction = null;
  let rankStrength = 0;
  if (!rankValid) {
    blockBoth("V2_RANK_INVALID");
  } else {
    rankFraction = rank / universe;
    rankStrength = clampRuleNumber((universe - rank + 1) / universe * 100);
    if (rankFraction > PRODUCTION_EVENT_MAX_RANK_FRACTION) eventBlockers.push("V2_TOP_PERCENTILE_REQUIRED");
    if (rankFraction > PRODUCTION_QUALITY_MAX_RANK_FRACTION) qualityBlockers.push("QUALITY_V2_TOP_DECILE_REQUIRED");
  }

  const inputQuality = input.source_candidate_present === true
    ? input.source_data_quality_score
    : null;
  const priorityQuality = source?.priority_components?.data_quality;
  let dataQuality = finiteRuleNumber(inputQuality)
    ? clampRuleNumber(inputQuality)
    : finiteRuleNumber(priorityQuality)
      ? clampRuleNumber(priorityQuality / 20 * 100)
      : null;
  if (dataQuality === null) {
    dataQuality = 0;
    blockBoth("DATA_QUALITY_SCORE_INVALID");
  } else if (dataQuality < PRODUCTION_QUALITY_MIN_DATA_QUALITY) {
    qualityBlockers.push("QUALITY_DATA_QUALITY_BELOW_THRESHOLD");
  }

  const eventScanned = source.event_candidate_scanned === true;
  const eventIds = Array.isArray(source.verified_positive_event_ids)
    ? dedupeRuleStrings(source.verified_positive_event_ids.filter((value) => ruleText(value)))
    : [];
  if (!eventScanned) blockBoth("EVENT_CANDIDATE_NOT_SCANNED");
  if (!eventIds.length) eventBlockers.push("VERIFIED_POSITIVE_EVENT_MISSING");
  const eventStrength = eventScanned && eventIds.length
    ? Math.min(100, 80 + 5 * eventIds.length)
    : 0;

  const low = source?.estimated_10d_range?.low_pct;
  const high = source?.estimated_10d_range?.high_pct;
  const rangeValid = finiteRuleNumber(low) && finiteRuleNumber(high) && low < 0 && high > 0;
  let downside = null;
  let ratio = null;
  let riskRewardStrength = 0;
  if (!rangeValid) {
    blockBoth("TEN_DAY_RANGE_INVALID");
  } else {
    downside = Math.abs(low);
    ratio = high / downside;
    if (high < eventPolicy.minimumUpside) eventBlockers.push("TEN_DAY_UPSIDE_BELOW_THRESHOLD");
    if (downside > eventPolicy.maximumDownside) eventBlockers.push("TEN_DAY_DOWNSIDE_ABOVE_LIMIT");
    if (ratio < PRODUCTION_EVENT_MIN_RISK_REWARD) eventBlockers.push("RISK_REWARD_BELOW_THRESHOLD");
    if (high < qualityPolicy.minimumUpside) qualityBlockers.push("QUALITY_TEN_DAY_UPSIDE_BELOW_THRESHOLD");
    if (downside > qualityPolicy.maximumDownside) qualityBlockers.push("QUALITY_TEN_DAY_DOWNSIDE_ABOVE_LIMIT");
    if (ratio < PRODUCTION_QUALITY_MIN_RISK_REWARD) qualityBlockers.push("QUALITY_RISK_REWARD_BELOW_THRESHOLD");
    riskRewardStrength = clampRuleNumber(ratio / 2 * 100);
  }

  const components = {
    legacy_recommendation: roundRuleNumber(recommendation * 0.30),
    v2_rank_strength: roundRuleNumber(rankStrength * 0.30),
    data_quality: roundRuleNumber(dataQuality * 0.15),
    verified_event_evidence: roundRuleNumber(eventStrength * 0.15),
    risk_reward_scenario: roundRuleNumber(riskRewardStrength * 0.10),
  };
  const score = roundRuleNumber(clampRuleNumber(Object.values(components).reduce((sum, value) => sum + value, 0)));
  if (score < PRODUCTION_QUALITY_MIN_SCORE) qualityBlockers.push("QUALITY_QUALIFICATION_SCORE_BELOW_THRESHOLD");

  const normalizedEventBlockers = dedupeRuleStrings(eventBlockers);
  const normalizedQualityBlockers = dedupeRuleStrings(qualityBlockers);
  const trackEvaluations = [
    {
      track: "event_catalyst",
      status: normalizedEventBlockers.length ? "FAIL" : "PASS",
      blocker_codes: normalizedEventBlockers,
    },
    {
      track: "quality_technical",
      status: normalizedQualityBlockers.length ? "FAIL" : "PASS",
      blocker_codes: normalizedQualityBlockers,
    },
  ];
  const qualificationTrack = trackEvaluations.find((evaluation) => evaluation.status === "PASS")?.track || null;
  const qualified = qualificationTrack !== null;
  const row = {
    market,
    code,
    name: ruleText(source.name),
    status: qualified ? "QUALIFIED" : "REJECTED",
    qualification_track: qualificationTrack,
    track_evaluations: trackEvaluations,
    rule_model_id: PRODUCTION_RULE_V3_MODEL_ID,
    score_kind: "RULE_QUALIFICATION_SCORE",
    qualification_score: score,
    score_components: components,
    probability: null,
    probability_status: "NOT_APPLICABLE",
    calibrated: false,
    expected_net_utility: null,
    legacy_signal: ruleText(source.legacy_signal),
    legacy_recommendation_degree: finiteRuleNumber(source.legacy_recommendation_degree)
      ? roundRuleNumber(recommendation)
      : null,
    v2_rank: rankValid ? Math.trunc(rank) : null,
    v2_rank_universe_size: rankValid ? Math.trunc(universe) : null,
    v2_rank_fraction: rankFraction === null ? null : roundRuleNumber(rankFraction, 4),
    data_quality_score: roundRuleNumber(dataQuality),
    event_candidate_scanned: eventScanned,
    verified_positive_event_ids: eventIds,
    entry_price: finiteRuleNumber(source.entry_price) && source.entry_price > 0
      ? Number(source.entry_price)
      : null,
    calendar_id: ruleText(source.calendar_id),
    calendar_version: ruleText(source.calendar_version),
    entry_trade_date: ruleText(source.entry_trade_date),
    forecast_end_trade_date: ruleText(source.forecast_end_trade_date),
    estimated_10d_range: {
      low_pct: rangeValid ? roundRuleNumber(low) : null,
      high_pct: rangeValid ? roundRuleNumber(high) : null,
      horizon_trade_days: 10,
    },
    risk_reward: {
      upside_pct: rangeValid ? roundRuleNumber(high) : null,
      downside_pct: rangeValid ? roundRuleNumber(downside) : null,
      ratio: rangeValid ? roundRuleNumber(ratio) : null,
    },
    blocker_codes: qualified
      ? []
      : dedupeRuleStrings([...normalizedEventBlockers, ...normalizedQualityBlockers]),
  };
  if (qualified) {
    row.qualification_id = stableV3QualificationId(snapshot, market, code);
    row.candidate_snapshot = input.candidate_snapshot && typeof input.candidate_snapshot === "object"
      && !Array.isArray(input.candidate_snapshot)
      ? input.candidate_snapshot
      : null;
  }
  return row;
}

function validV3QualifiedRow(row, decision, snapshot, context = null) {
  if (productionRuleContractVersion(decision) !== 3) return true;
  if (!row || typeof row !== "object" || Array.isArray(row) || row.status !== "QUALIFIED") return false;
  const ruleContext = context || v3RuleInputContext(snapshot);
  if (!ruleContext) return false;
  const market = ruleText(row.market);
  const code = ruleText(row.code || row.symbol);
  const sourceContext = ruleContext.byIdentity.get(`${market}:${code}`);
  if (!sourceContext) return false;
  const expected = expectedV3RuleEvaluation(snapshot, sourceContext.input);
  if (!expected || expected.status !== "QUALIFIED" || !contractDeepEqual(row, expected)) return false;
  if (
    !row.candidate_snapshot || typeof row.candidate_snapshot !== "object" || Array.isArray(row.candidate_snapshot)
    || normalizeLiveCode(market, row.candidate_snapshot.code || row.candidate_snapshot.symbol)
      !== normalizeLiveCode(market, code)
  ) return false;
  try {
    strictSnapshotQuote(row.candidate_snapshot, market);
  } catch (_error) {
    return false;
  }
  return true;
}

function compareV3EvaluationRows(left, right) {
  const scoreDifference = Number(right.qualification_score || 0) - Number(left.qualification_score || 0);
  if (scoreDifference !== 0) return scoreDifference;
  const leftMarket = String(left.market || "");
  const rightMarket = String(right.market || "");
  if (leftMarket !== rightMarket) return leftMarket < rightMarket ? -1 : 1;
  const leftCode = String(left.code || "");
  const rightCode = String(right.code || "");
  if (leftCode !== rightCode) return leftCode < rightCode ? -1 : 1;
  return 0;
}

function validatedV3DecisionRows(snapshot, decision) {
  if (productionRuleContractVersion(decision) !== 3) return null;
  const evaluated = decision.evaluated_candidates;
  const published = decision.qualified_candidates;
  const context = v3RuleInputContext(snapshot);
  const inputLedger = snapshot?.production_rule_inputs;
  if (
    !context
    || typeof inputLedger?.ledger_sha256 !== "string"
    || !/^[a-f0-9]{64}$/.test(inputLedger.ledger_sha256)
    || decision.source_rule_inputs_contract_version !== inputLedger.contract_version
    || decision.source_rule_inputs_sha256 !== inputLedger.ledger_sha256
    || decision.source_rule_input_count !== context.inputRows.length
    || !Array.isArray(evaluated)
    || !Array.isArray(published)
    || !Number.isInteger(decision.evaluated_candidate_count)
    || decision.evaluated_candidate_count !== context.inputRows.length
    || !Number.isInteger(decision.qualified_candidate_count)
    || !Number.isInteger(decision.rejected_candidate_count)
    || !Array.isArray(decision.blocker_codes)
  ) return null;

  const rebuiltEvaluated = [];
  for (const input of context.inputRows) {
    const rebuilt = expectedV3RuleEvaluation(snapshot, input);
    if (!rebuilt) return null;
    rebuiltEvaluated.push(rebuilt);
  }
  rebuiltEvaluated.sort(compareV3EvaluationRows);
  const rebuiltQualified = rebuiltEvaluated.filter((row) => row.status === "QUALIFIED");
  const rebuiltPrimary = rebuiltQualified.length ? rebuiltQualified[0] : null;
  const expectedAction = rebuiltPrimary ? "QUALIFIED_PICK" : "NO_QUALIFIED_PICK";
  const expectedBlockers = rebuiltPrimary ? [] : ["NO_RULE_CANDIDATE_PASSED"];

  if (
    decision.action !== expectedAction
    || decision.evaluated_candidate_count !== rebuiltEvaluated.length
    || decision.qualified_candidate_count !== rebuiltQualified.length
    || decision.rejected_candidate_count !== rebuiltEvaluated.length - rebuiltQualified.length
    || !contractDeepEqual(decision.evaluated_candidates, rebuiltEvaluated)
    || !contractDeepEqual(decision.qualified_candidates, rebuiltQualified)
    || !contractDeepEqual(decision.primary, rebuiltPrimary)
    || !contractDeepEqual(decision.blocker_codes, expectedBlockers)
  ) return null;
  if (!rebuiltQualified.every((row) => validV3QualifiedRow(row, decision, snapshot, context))) return null;
  return { evaluated: rebuiltEvaluated, qualified: rebuiltQualified, primary: rebuiltPrimary };
}

function validatedV3QualifiedRows(snapshot, decision) {
  if (productionRuleContractVersion(decision) !== 3 || decision.action !== "QUALIFIED_PICK") return null;
  const validated = validatedV3DecisionRows(snapshot, decision);
  return validated ? validated.qualified : null;
}

function productionQualifiedCandidateRows(snapshot, market = null) {
  const decision = snapshot?.production_decision;
  if (!isProductionRuleDecision(decision, snapshot?.model_version) || decision.action !== "QUALIFIED_PICK") return [];
  if (productionRuleContractVersion(decision) === 3) {
    const qualifiedRows = validatedV3QualifiedRows(snapshot, decision);
    if (!qualifiedRows) return [];
    return qualifiedRows
      .filter((row) => !market || row.market === market)
      .map((row) => row.candidate_snapshot);
  }
  const rawRows = [decision.primary, ...(Array.isArray(decision.qualified_candidates) ? decision.qualified_candidates : [])];
  const rows = [];
  const seen = new Set();
  for (const row of rawRows) {
    if (!row || typeof row !== "object" || Array.isArray(row) || row.status !== "QUALIFIED") continue;
    const rowMarket = String(row.market || "");
    if (!LIVE_MARKETS.has(rowMarket)) continue;
    const code = normalizeLiveCode(rowMarket, row.code || row.symbol);
    if (!code) continue;
    const key = `${rowMarket}:${code}`;
    if (seen.has(key)) continue;
    const candidate = row.candidate_snapshot || row;
    if (normalizeLiveCode(rowMarket, candidate.code || candidate.symbol) !== code) continue;
    if (
      !Number.isFinite(row.qualification_score)
      || row.rule_model_id !== decision.rule_model_id
      || row.score_kind !== decision.score_kind
      || !(row.probability === undefined || row.probability === null)
      || !(row.calibrated === undefined || row.calibrated === false)
    ) continue;
    seen.add(key);
    rows.push({ market: rowMarket, candidate });
  }
  const publishedCount = Number(decision.qualified_candidate_count);
  if (!Number.isInteger(publishedCount) || publishedCount <= 0 || publishedCount !== rows.length) return [];
  return rows
    .filter((row) => !market || row.market === market)
    .map((row) => row.candidate);
}

function snapshotCandidateRows(snapshot, market) {
  const section = snapshot?.markets?.[market]
    || (market === "a_share" ? { decision: snapshot?.decision || {} } : {});
  const decision = section?.decision || {};
  const watchlist = Array.isArray(decision.watchlist) ? decision.watchlist : [];
  const rows = [decision.primary, decision.blocked_candidate, ...watchlist];
  rows.push(...productionQualifiedCandidateRows(snapshot, market));
  for (const globalCandidate of [
    snapshot?.global_decision?.primary,
    snapshot?.global_decision?.research_priority,
  ]) {
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

function productionRuleContractVersion(decision) {
  if (!decision || typeof decision !== "object" || Array.isArray(decision)) return null;
  if (decision.action_basis === "strict_rule_qualification_v1"
    && decision.rule_model_id === "ten-day-audited-rule-ensemble-v1") return 1;
  if (decision.action_basis === "candidate_level_rule_qualification_v2"
    && decision.rule_model_id === "ten-day-audited-rule-ensemble-v2") return 2;
  if (decision.action_basis === PRODUCTION_RULE_V3_ACTION_BASIS
    && decision.rule_model_id === PRODUCTION_RULE_V3_MODEL_ID) return 3;
  return null;
}

function isProductionRuleDecision(decision, modelVersion = null) {
  const contractVersion = productionRuleContractVersion(decision);
  return Boolean(
    decision
    && typeof decision === "object"
    && decision.contract_version === "production-rule-10d-v1"
    && decision.decision_scope === "global_10d_bounded_recall"
    && contractVersion !== null
    && ((modelVersion === CURRENT_PRODUCTION_MODEL_VERSION) === (contractVersion === 3))
    && ["QUALIFIED_PICK", "NO_QUALIFIED_PICK"].includes(decision.action)
    && decision.score_kind === "RULE_QUALIFICATION_SCORE"
    && decision.probability === null
    && decision.calibrated === false,
  );
}

function summarizeProductionCandidate(candidate) {
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return null;
  const fields = [
    "qualification_id", "status", "market", "code", "name", "rule_model_id",
    "score_kind", "qualification_score", "score_components", "probability_status",
    "probability", "calibrated", "expected_net_utility", "legacy_signal",
    "legacy_recommendation_degree", "v2_rank", "v2_rank_universe_size",
    "data_quality_score", "event_candidate_scanned", "verified_positive_event_ids",
    "qualification_track", "track_evaluations",
    "entry_price", "entry_trade_date", "forecast_end_trade_date", "calendar_id",
    "calendar_version", "estimated_10d_range", "risk_reward", "blocker_codes",
  ];
  return Object.fromEntries(fields.filter((field) => Object.hasOwn(candidate, field)).map((field) => [field, candidate[field]]));
}

function summarizeProductionQualifiedCandidates(decision, snapshot = null) {
  if (!isProductionRuleDecision(decision, snapshot?.model_version) || decision.action !== "QUALIFIED_PICK") return [];
  const contractVersion = productionRuleContractVersion(decision);
  const validatedRows = contractVersion === 3 ? validatedV3QualifiedRows(snapshot, decision) : null;
  if (contractVersion === 3 && !validatedRows) return [];
  const rawRows = contractVersion === 3
    ? validatedRows
    : [decision.primary, ...(Array.isArray(decision.qualified_candidates) ? decision.qualified_candidates : [])];
  const result = [];
  const seen = new Set();
  for (const row of rawRows) {
    const summary = summarizeProductionCandidate(row);
    if (!summary || summary.status !== "QUALIFIED") continue;
    const key = `${summary.market || ""}:${String(summary.code || "").toLowerCase()}`;
    if (!summary.market || !summary.code || seen.has(key)) continue;
    seen.add(key);
    result.push(summary);
    if (result.length >= MAX_QUALIFIED_SUMMARY_CANDIDATES) break;
  }
  return result;
}

function productionDecisionForSnapshot(snapshot) {
  const decision = snapshot?.production_decision;
  if (!isProductionRuleDecision(decision, snapshot?.model_version)) return null;
  if (productionRuleContractVersion(decision) !== 3) return decision;
  return validatedV3DecisionRows(snapshot, decision) ? decision : null;
}

function summarizePick(pick) {
  const legacySummary = summarizeDecision(pick.decision || {});
  const globalDecision = isGlobalTenDayDecision(pick.global_decision) ? pick.global_decision : null;
  const productionDecision = productionDecisionForSnapshot(pick);
  const qualifiedCandidates = productionDecision ? summarizeProductionQualifiedCandidates(productionDecision, pick) : [];
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
    production_action: productionDecision?.action || "NO_QUALIFIED_PICK",
    qualification_history_kind: productionDecision ? "qualified_rule_10d_v1" : null,
    production_decision: productionDecision ? {
      contract_version: productionDecision.contract_version,
      decision_scope: productionDecision.decision_scope,
      horizon_trade_days: productionDecision.horizon_trade_days,
      action: productionDecision.action,
      action_basis: productionDecision.action_basis,
      rule_model_id: productionDecision.rule_model_id,
      score_kind: productionDecision.score_kind,
      score_disclaimer: productionDecision.score_disclaimer,
      probability_status: productionDecision.probability_status,
      probability: null,
      calibrated: false,
      expected_net_utility: null,
      primary: summarizeProductionCandidate(productionDecision.primary),
      qualified_candidates: qualifiedCandidates,
      qualified_candidates_truncated: Number(productionDecision.qualified_candidate_count || 0) > qualifiedCandidates.length,
      qualified_candidate_count: productionDecision.qualified_candidate_count || 0,
      rejected_candidate_count: productionDecision.rejected_candidate_count || 0,
      evaluated_candidate_count: productionDecision.evaluated_candidate_count || 0,
      blocker_codes: productionDecision.blocker_codes || [],
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
  const qualificationPrimary = productionDecision?.primary;
  if (qualificationPrimary && typeof qualificationPrimary === "object") {
    summary.qualification_id = qualificationPrimary.qualification_id || null;
    summary.qualification_score = qualificationPrimary.qualification_score ?? null;
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
    qualified_rule_day_count: days.filter((row) => row.production_decision?.action === "QUALIFIED_PICK").length,
    no_qualified_rule_day_count: days.filter((row) => row.production_decision?.action === "NO_QUALIFIED_PICK").length,
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
    observation_ledger: evaluation?.observation_ledger && typeof evaluation.observation_ledger === "object"
      ? evaluation.observation_ledger
      : {
        track: "MODEL_OBSERVATION",
        status: "UNAVAILABLE",
        included_in_shadow_research: false,
        included_in_executable_performance: false,
        settlement_status: "NOT_IMPLEMENTED",
      },
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
    .filter((item) => item.target_date === targetDate && item.cache_key && item.full_snapshot_available !== false)
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
    const productionDecision = latest ? productionDecisionForSnapshot(latest) : null;
    const currentTime = nowCN();
    const current = new Date(currentTime);
    const freshness = snapshotFreshness(latest ? latest.generated_at : null, current);
    const sourceStateByMarket = Object.fromEntries(["a_share", "hk", "us"].map((market) => {
      const section = latest?.markets?.[market] || {};
      const health = section.quote_health || {};
      return [market, {
        status: health.status || "unknown",
        quote_coverage: Number.isFinite(Number(health.quote_coverage)) ? Number(health.quote_coverage) : null,
        source_session: health.freshness_reference_session || null,
        source_as_of: health.source_as_of || health.observed_at || null,
      }];
    }));
    return json({
      ok: true,
      time: currentTime,
      platform: "cloudflare-workers",
      snapshot_generation: "github-actions",
      data_mode: "scheduled_snapshot",
      quote_delivery_mode: "scheduled_snapshot",
      publication_state: freshness.freshness_state === "fresh" ? "BATCH_PUBLISHED" : freshness.freshness_state.toUpperCase(),
      source_state_by_market: sourceStateByMarket,
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
      production_action: productionDecision?.action || "NO_QUALIFIED_PICK",
      qualification_id: productionDecision?.primary?.qualification_id || null,
      calibrated_action: latest?.global_decision?.action || "NO_VALID_PICK",
      prediction_id: latest?.global_decision?.primary?.prediction_id || null,
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

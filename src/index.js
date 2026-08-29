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
const GITHUB_PRIMARY_UTC_SCHEDULES = [
  { minute: 17, hours: [0, 2, 4, 7, 8, 12] },
  { minute: 47, hours: [14] },
  { minute: 17, hours: [20, 21], newYorkHour: 16 },
];
const GITHUB_WATCHDOG_UTC_SCHEDULES = [
  { minute: 47, hours: [0, 2, 4, 7, 8, 12] },
  { minute: 17, hours: [15] },
  { minute: 47, hours: [20, 21], newYorkHour: 16 },
];
const LIVE_MARKETS = new Set(["a_share", "hk", "us"]);
const LIVE_CACHE_TTL_MS = 10_000;
const WORKER_RUNTIME_CONTRACT_VERSION = "worker-runtime-v1";
const WORKER_LIVE_INDEX_CONTRACT_VERSION = "worker-live-index-v1";
const WORKER_UI_BOOTSTRAP_CONTRACT_VERSION = "ui-bootstrap-v1";
const WORKER_UI_CANDIDATES_CONTRACT_VERSION = "ui-candidates-v2";
const WORKER_UI_EVENTS_CONTRACT_VERSION = "ui-events-v2";
const EVENT_LIST_CONTRACT_VERSION = "event-list-v2";
const EVENT_ORDERING_CONTRACT_VERSION = "decision-bound-first-then-published-desc-v1";
const DATA_MANIFEST_CONTRACT_VERSION = "data-manifest-v1";
const DATA_MANIFEST_KEY = "latest-manifest.json";
const EMBEDDED_DATA_MANIFEST_PATH = "/data/latest-manifest.json";
const DATA_ASSET_NAMES = new Set(["runtime", "live_index", "summary", "candidates", "events", "history"]);
const WORKER_RUNTIME_PATH = "/data/picks/runtime.json";
const WORKER_LIVE_INDEX_PATH = "/data/picks/live-index.json";
const WORKER_UI_BOOTSTRAP_PATH = "/data/picks/ui-bootstrap.json";
const WORKER_UI_CANDIDATES_PATH = "/data/picks/ui-candidates.json";
const WORKER_UI_EVENTS_PATH = "/data/picks/ui-events.json";
const WORKER_LIVE_INDEX_CANDIDATE_LIMIT = 90;
const WORKER_LIVE_INDEX_BYTE_SIZE_LIMIT = 524_288;
const MAX_QUALIFIED_SUMMARY_CANDIDATES = 20;
const GITHUB_WORKFLOW_DISPATCH_URL = "https://api.github.com/repos/dzhdingzihang/xuangu/actions/workflows/deploy-worker.yml/dispatches";
const CLOUDFLARE_SCHEDULED_CRONS = new Map([
  ["17 0,2,4,7,8,12 * * MON-FRI", { minute: 17, hours: new Set([0, 2, 4, 7, 8, 12]), weekdays: new Set([1, 2, 3, 4, 5]), githubWeekdays: "1-5" }],
  ["47 14 * * MON-FRI", { minute: 47, hours: new Set([14]), weekdays: new Set([1, 2, 3, 4, 5]), githubWeekdays: "1-5" }],
  ["17 20 * * MON-FRI", { minute: 17, hours: new Set([20]), weekdays: new Set([1, 2, 3, 4, 5]), githubWeekdays: "1-5", newYorkHour: 16 }],
  ["17 21 * * MON-FRI", { minute: 17, hours: new Set([21]), weekdays: new Set([1, 2, 3, 4, 5]), githubWeekdays: "1-5", newYorkHour: 16 }],
]);
const CURRENT_PRODUCTION_MODEL_VERSION = "smart-selector-2026-08-29.1-two-tier-rule";
const PRODUCTION_RULE_V3_ACTION_BASIS = "dual_track_candidate_qualification_v3";
const PRODUCTION_RULE_V3_MODEL_ID = "ten-day-audited-rule-ensemble-v3";
const PRODUCTION_RULE_V4_ACTION_BASIS = "dual_track_candidate_qualification_v4";
const PRODUCTION_RULE_V4_MODEL_ID = "ten-day-audited-rule-ensemble-v4";
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
  a_share: { minimumLegacy: 64, maximumDownside: 6, minimumUpside: 6 },
  hk: { minimumLegacy: 67, maximumDownside: 6, minimumUpside: 6 },
  us: { minimumLegacy: 67, maximumDownside: 7.5, minimumUpside: 6.5 },
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

function quotedEtag(digest) {
  return `"${String(digest || "")}"`;
}

function requestMatchesEtag(request, digest) {
  const value = String(request.headers.get("if-none-match") || "");
  if (!value || !digest) return false;
  const wanted = quotedEtag(digest);
  return value.split(",").map((item) => item.trim()).some((item) => item === wanted || item === "*");
}

function jsonWithEtag(request, payload, digest, cacheControl = "no-store") {
  const headers = { etag: quotedEtag(digest), "cache-control": cacheControl };
  if (requestMatchesEtag(request, digest)) return new Response(null, { status: 304, headers });
  return json(payload, 200, headers);
}

async function derivedRepresentationDigest(assetDigest, variants) {
  const normalized = Object.entries(variants || {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value ?? ""))}`)
    .join("&");
  return sha256Hex(new TextEncoder().encode(`${String(assetDigest || "")}|${normalized}`));
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
  // The repository-owned GitHub Actions schedule is the production primary.
  return nextActiveRefresh(current, true);
}

function shanghaiIsoForInstant(value) {
  const parts = shanghaiDateParts(value);
  const pad = (item) => String(item).padStart(2, "0");
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}:00+08:00`;
}

export function nextActiveRefresh(current = new Date(), primaryEnabled = false) {
  const now = current instanceof Date ? current : new Date(current);
  if (Number.isNaN(now.getTime())) return null;
  const schedules = primaryEnabled
    ? GITHUB_PRIMARY_UTC_SCHEDULES
    : GITHUB_WATCHDOG_UTC_SCHEDULES;
  const candidates = [];
  const start = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  for (let dayOffset = 0; dayOffset <= 8; dayOffset += 1) {
    const dayStart = new Date(start + dayOffset * 86_400_000);
    const weekday = dayStart.getUTCDay();
    if (weekday < 1 || weekday > 5) continue;
    for (const schedule of schedules) {
      for (const hour of schedule.hours) {
        const candidate = new Date(Date.UTC(
          dayStart.getUTCFullYear(),
          dayStart.getUTCMonth(),
          dayStart.getUTCDate(),
          hour,
          schedule.minute,
        ));
        if (candidate <= now) continue;
        if (Number.isInteger(schedule.newYorkHour) && newYorkHour(candidate) !== schedule.newYorkHour) continue;
        candidates.push(candidate);
      }
    }
  }
  if (!candidates.length) return null;
  candidates.sort((left, right) => left.getTime() - right.getTime());
  return shanghaiIsoForInstant(candidates[0]);
}

export function latestActiveCheckpoint(current = new Date(), primaryEnabled = false) {
  const now = current instanceof Date ? current : new Date(current);
  if (Number.isNaN(now.getTime())) return null;
  const schedules = primaryEnabled
    ? GITHUB_PRIMARY_UTC_SCHEDULES
    : GITHUB_WATCHDOG_UTC_SCHEDULES;
  const candidates = [];
  const start = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  for (let dayOffset = 0; dayOffset >= -8; dayOffset -= 1) {
    const dayStart = new Date(start + dayOffset * 86_400_000);
    const weekday = dayStart.getUTCDay();
    if (weekday < 1 || weekday > 5) continue;
    for (const schedule of schedules) {
      for (const hour of schedule.hours) {
        const candidate = new Date(Date.UTC(
          dayStart.getUTCFullYear(),
          dayStart.getUTCMonth(),
          dayStart.getUTCDate(),
          hour,
          schedule.minute,
        ));
        if (candidate > now) continue;
        if (Number.isInteger(schedule.newYorkHour) && newYorkHour(candidate) !== schedule.newYorkHour) continue;
        candidates.push(candidate);
      }
    }
  }
  if (!candidates.length) return null;
  candidates.sort((left, right) => right.getTime() - left.getTime());
  return {
    epoch: candidates[0].getTime(),
    iso: shanghaiIsoForInstant(candidates[0]),
  };
}

export function snapshotFreshness(generatedAt, current = new Date(), primaryEnabled = false) {
  const now = current instanceof Date ? current : new Date(current);
  if (Number.isNaN(now.getTime())) {
    return {
      freshness_state: "unknown",
      expected_checkpoint: null,
      snapshot_age_minutes: null,
      checkpoint_lag_minutes: null,
    };
  }
  const expected = latestActiveCheckpoint(now, primaryEnabled);
  if (!expected) {
    return {
      freshness_state: "unknown",
      expected_checkpoint: null,
      snapshot_age_minutes: null,
      checkpoint_lag_minutes: null,
    };
  }
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

export function roundRuleNumber(value, digits = 2) {
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

function stableV3QualificationId(snapshot, market, code, contractVersion = 4) {
  const automation = snapshot?.automation;
  const scheduledSlot = automation && typeof automation === "object" && !Array.isArray(automation)
    ? automation.scheduled_slot
    : null;
  const target = snapshot?.target_date || snapshot?.signal_date || "";
  const identity = [
    "production-rule-10d-v1",
    contractVersion === 4 ? PRODUCTION_RULE_V4_MODEL_ID : PRODUCTION_RULE_V3_MODEL_ID,
    scheduledSlot || target,
    target,
    market,
    code,
  ].map((item) => String(item || "")).join("|");
  return `qual_${sha256RuleText(identity).slice(0, 24)}`;
}

function frozenV3SourceProjection(source, index, inputContractVersion = "production-rule-inputs-v2") {
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
    const rangeFields = inputContractVersion === "production-rule-inputs-v3"
      ? [
        "contract_version", "low_pct", "high_pct", "text",
        "horizon_trade_days", "method_id", "calibrated",
        "source_observations", "source_window_start_date", "source_window_end_date",
      ]
      : ["low_pct", "high_pct"];
    result.estimated_10d_range = Object.fromEntries(
      rangeFields
        .filter((field) => Object.hasOwn(source.estimated_10d_range, field))
        .map((field) => [field, source.estimated_10d_range[field]]),
    );
  }
  return result;
}

function v3RuleInputContext(snapshot) {
  const inputs = snapshot?.production_rule_inputs;
  const inputRows = inputs?.rows;
  const sources = snapshot?.global_decision?.evaluated_candidates;
  const isV3 = inputs?.contract_version === "production-rule-inputs-v1"
    && inputs?.action_basis === PRODUCTION_RULE_V3_ACTION_BASIS
    && inputs?.rule_model_id === PRODUCTION_RULE_V3_MODEL_ID;
  const isV4 = ["production-rule-inputs-v2", "production-rule-inputs-v3"].includes(inputs?.contract_version)
    && inputs?.action_basis === PRODUCTION_RULE_V4_ACTION_BASIS
    && inputs?.rule_model_id === PRODUCTION_RULE_V4_MODEL_ID;
  if (
    !Array.isArray(sources)
    || !inputs || typeof inputs !== "object" || Array.isArray(inputs)
    || (!isV3 && !isV4)
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
    if (!contractDeepEqual(frozenInput, frozenV3SourceProjection(source, index, inputs.contract_version))) return null;
    const key = `${market}:${code}`;
    if (byIdentity.has(key)) return null;
    byIdentity.set(key, { source, input });
  }
  return {
    sources,
    inputRows,
    byIdentity,
    contractVersion: isV4 ? 4 : 3,
    inputContractVersion: inputs.contract_version,
  };
}

function horizonRangeText(low, high) {
  const signed = (value) => `${value >= 0 ? "+" : ""}${Number(value).toFixed(1)}%`;
  return `${signed(low)} ~ ${signed(high)}`;
}

function canonicalHorizonRange(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const low = value.low_pct;
  const high = value.high_pct;
  const observations = value.source_observations;
  if (
    value.contract_version !== "horizon-range-v1"
    || value.horizon_trade_days !== 10
    || value.method_id !== "realized-vol-drift-shadow-v1"
    || value.calibrated !== false
    || !finiteRuleNumber(low) || !finiteRuleNumber(high) || !(low < 0 && high > 0)
    || !Number.isInteger(observations) || observations < 0 || observations > 20
    || value.text !== horizonRangeText(low, high)
  ) return null;
  const start = value.source_window_start_date;
  const end = value.source_window_end_date;
  if ((start === undefined || start === null) !== (end === undefined || end === null)) return null;
  if (start !== undefined && start !== null && (
    !validIsoDate(start) || !validIsoDate(end) || start > end
  )) return null;
  const result = {
    contract_version: "horizon-range-v1",
    low_pct: roundRuleNumber(low, 2),
    high_pct: roundRuleNumber(high, 2),
    text: horizonRangeText(low, high),
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

function tenDayTradePlan(row, candidate, qualificationTrack, inputContractVersion = "production-rule-inputs-v2") {
  const price = row?.entry_price;
  if (!finiteRuleNumber(price) || price <= 0) return null;
  const source = candidate && typeof candidate === "object" && !Array.isArray(candidate) ? candidate : {};
  const realtime = source.realtime && typeof source.realtime === "object" && !Array.isArray(source.realtime)
    ? source.realtime : {};
  const low = row?.estimated_10d_range?.low_pct;
  const high = row?.estimated_10d_range?.high_pct;
  let stopLoss = source.stop_loss;
  let stopSource = "candidate_stop_loss";
  if (!finiteRuleNumber(stopLoss) || stopLoss <= 0) {
    stopLoss = finiteRuleNumber(low) && low < 0 ? price * (1 + low / 100) : null;
    stopSource = "ten_day_scenario_lower_bound";
  }
  let target = source.take_profit_reference;
  let targetSource = "candidate_take_profit_reference";
  if (!finiteRuleNumber(target) || target <= 0) {
    target = finiteRuleNumber(high) && high > 0 ? price * (1 + high / 100) : null;
    targetSource = "ten_day_scenario_upper_bound";
  }
  const currency = { a_share: "CNY", hk: "HKD", us: "USD" }[row.market] || null;
  const reviewEnd = ruleText(row.forecast_end_trade_date);
  const currentProvenance = inputContractVersion === "production-rule-inputs-v3";
  const plan = {
    contract_version: currentProvenance ? "ten-day-trade-plan-v2" : "ten-day-trade-plan-v1",
    status: "REVIEW_REQUIRED",
    horizon_trade_days: 10,
    reference_quote: {
      price: roundRuleNumber(price, 4),
      currency,
      source: realtime.source ?? null,
      source_as_of: realtime.source_as_of ?? null,
      quote_status: realtime.quote_status || realtime.session_label || null,
      kind: "published_snapshot_quote",
    },
    entry_zone: {
      low: roundRuleNumber(price * 0.99, 4),
      high: roundRuleNumber(price * 1.005, 4),
      currency,
    },
    entry_trade_date: ruleText(row.entry_trade_date),
    invalidation: {
      price: finiteRuleNumber(stopLoss) ? roundRuleNumber(stopLoss, 4) : null,
      currency,
      source: finiteRuleNumber(stopLoss) ? stopSource : null,
    },
    target: {
      price: finiteRuleNumber(target) ? roundRuleNumber(target, 4) : null,
      currency,
      source: finiteRuleNumber(target) ? targetSource : null,
    },
    position_limit: {
      max_single_name_weight_pct: 10,
      policy: "strategy_safety_cap_not_personalized",
    },
    catalyst_expiry_date: qualificationTrack === "event_catalyst" ? reviewEnd : null,
    review_end_trade_date: reviewEnd,
    exit_rules: [
      "EXIT_IF_INVALIDATION_PRICE_BREACHED",
      "REVIEW_AT_TENTH_SESSION_CLOSE",
      "DO_NOT_CHASE_ABOVE_ENTRY_ZONE",
    ],
    is_personalized_advice: false,
  };
  if (currentProvenance) {
    const scenarioRange = canonicalHorizonRange(row?.estimated_10d_range);
    if (!scenarioRange) return null;
    plan.scenario_range = scenarioRange;
  }
  return plan;
}

function expectedV3RuleEvaluation(
  snapshot,
  input,
  contractVersion = 4,
  inputContractVersion = "production-rule-inputs-v2",
) {
  const source = input;
  const market = ruleText(source?.market);
  const code = ruleText(source?.code || source?.symbol);
  const eventPolicy = PRODUCTION_EVENT_MARKET_POLICY[market];
  const v3QualityPolicy = {
    a_share: { minimumLegacy: 66, maximumDownside: 6, minimumUpside: 6 },
    hk: { minimumLegacy: 67, maximumDownside: 6, minimumUpside: 6 },
    us: { minimumLegacy: 68, maximumDownside: 7.5, minimumUpside: 6.5 },
  };
  const qualityPolicy = (contractVersion === 4 ? PRODUCTION_QUALITY_MARKET_POLICY : v3QualityPolicy)[market];
  if (!market || !code || !eventPolicy || !qualityPolicy) return null;

  const sourceBlockers = dedupeRuleStrings(source.blocker_codes);
  const sharedBlockers = sourceBlockers
    ? sourceBlockers.filter((codeValue) => !PRODUCTION_MODEL_AVAILABILITY_BLOCKERS.has(codeValue))
    : ["SOURCE_BLOCKER_CODES_INVALID"];
  const eventBlockers = [...sharedBlockers];
  const qualityEventWaivers = contractVersion === 4
    ? new Set(["EVENT_CANDIDATE_NOT_SCANNED", "VERIFIED_POSITIVE_EVENT_MISSING"])
    : new Set(["VERIFIED_POSITIVE_EVENT_MISSING"]);
  const qualityBlockers = sharedBlockers.filter((codeValue) => !qualityEventWaivers.has(codeValue));
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
  if (!eventScanned) {
    eventBlockers.push("EVENT_CANDIDATE_NOT_SCANNED");
    if (contractVersion === 3) qualityBlockers.push("EVENT_CANDIDATE_NOT_SCANNED");
  }
  if (!eventIds.length) eventBlockers.push("VERIFIED_POSITIVE_EVENT_MISSING");
  const eventStrength = eventScanned && eventIds.length
    ? Math.min(100, 80 + 5 * eventIds.length)
    : 0;

  const low = source?.estimated_10d_range?.low_pct;
  const high = source?.estimated_10d_range?.high_pct;
  const rangeValid = finiteRuleNumber(low) && finiteRuleNumber(high) && low < 0 && high > 0;
  const canonicalRange = inputContractVersion === "production-rule-inputs-v3"
    ? canonicalHorizonRange(source?.estimated_10d_range)
    : null;
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
    if (inputContractVersion === "production-rule-inputs-v3" && !canonicalRange) {
      blockBoth("TEN_DAY_RANGE_PROVENANCE_INVALID");
    }
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
    rule_model_id: contractVersion === 4 ? PRODUCTION_RULE_V4_MODEL_ID : PRODUCTION_RULE_V3_MODEL_ID,
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
    estimated_10d_range: canonicalRange || {
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
    row.qualification_id = stableV3QualificationId(snapshot, market, code, contractVersion);
    row.candidate_snapshot = input.candidate_snapshot && typeof input.candidate_snapshot === "object"
      && !Array.isArray(input.candidate_snapshot)
      ? input.candidate_snapshot
      : null;
    if (contractVersion === 4) {
      row.ten_day_trade_plan = tenDayTradePlan(
        row,
        row.candidate_snapshot || input.candidate_snapshot,
        qualificationTrack,
        inputContractVersion,
      );
    }
  }
  return row;
}

function validV3QualifiedRow(row, decision, snapshot, context = null) {
  const contractVersion = productionRuleContractVersion(decision);
  if (![3, 4].includes(contractVersion)) return true;
  if (!row || typeof row !== "object" || Array.isArray(row) || row.status !== "QUALIFIED") return false;
  const ruleContext = context || v3RuleInputContext(snapshot);
  if (!ruleContext) return false;
  const market = ruleText(row.market);
  const code = ruleText(row.code || row.symbol);
  const sourceContext = ruleContext.byIdentity.get(`${market}:${code}`);
  if (!sourceContext) return false;
  const expected = expectedV3RuleEvaluation(
    snapshot,
    sourceContext.input,
    contractVersion,
    ruleContext.inputContractVersion,
  );
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
  const contractVersion = productionRuleContractVersion(decision);
  if (![3, 4].includes(contractVersion)) return null;
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
    const rebuilt = expectedV3RuleEvaluation(
      snapshot,
      input,
      contractVersion,
      context.inputContractVersion,
    );
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
  if (![3, 4].includes(productionRuleContractVersion(decision)) || decision.action !== "QUALIFIED_PICK") return null;
  const validated = validatedV3DecisionRows(snapshot, decision);
  return validated ? validated.qualified : null;
}

function productionQualifiedCandidateRows(snapshot, market = null) {
  const decision = snapshot?.production_decision;
  if (!isProductionRuleDecision(decision, snapshot?.model_version) || decision.action !== "QUALIFIED_PICK") return [];
  if ([3, 4].includes(productionRuleContractVersion(decision))) {
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
  if (snapshot?.contract_version === WORKER_LIVE_INDEX_CONTRACT_VERSION) {
    const rows = snapshot?.candidates?.[market];
    if (!rows || typeof rows !== "object" || Array.isArray(rows)) return null;
    const candidate = rows[code];
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return null;
    return normalizeLiveCode(market, candidate.code || candidate.symbol) === code ? candidate : null;
  }
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

async function readOptionalAssetJson(env, path) {
  const response = await env.ASSETS.fetch(`https://assets.local${path}`);
  if (!response.ok) return null;
  const contentType = String(response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("json")) return null;
  const payload = await response.json();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`optional asset JSON is not an object: ${path}`);
  }
  return payload;
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function safeDataObjectKey(value) {
  const key = String(value || "");
  if (!key || key.startsWith("/") || key.includes("\\") || key.split("/").includes("..") || !key.endsWith(".json")) {
    return null;
  }
  return key;
}

function validDataManifest(manifest) {
  if (
    !manifest || typeof manifest !== "object" || Array.isArray(manifest)
    || manifest.contract_version !== DATA_MANIFEST_CONTRACT_VERSION
    || typeof manifest.snapshot_key !== "string"
    || manifest.snapshot_key.includes("/") || !manifest.snapshot_key.endsWith(".json")
    || typeof manifest.generated_at !== "string" || !awareIsoTimestamp(manifest.generated_at)
    || !/^[a-f0-9]{64}$/.test(String(manifest.snapshot_sha256 || ""))
    || !Number.isInteger(manifest.snapshot_byte_size) || manifest.snapshot_byte_size <= 0
    || !manifest.assets || typeof manifest.assets !== "object" || Array.isArray(manifest.assets)
  ) return false;
  for (const name of DATA_ASSET_NAMES) {
    const descriptor = manifest.assets[name];
    const key = manifest[`${name}_key`];
    if (
      !descriptor || typeof descriptor !== "object" || Array.isArray(descriptor)
      || descriptor.key !== key || !safeDataObjectKey(key)
      || !/^[a-f0-9]{64}$/.test(String(descriptor.sha256 || ""))
      || !Number.isInteger(descriptor.byte_size) || descriptor.byte_size <= 0
      || key.split("/").at(-1) !== `${descriptor.sha256}.json`
    ) return false;
  }
  const detailKeys = manifest.candidate_detail_keys || {};
  const detailMeta = manifest.assets.candidate_details || {};
  if (
    typeof detailKeys !== "object" || Array.isArray(detailKeys)
    || typeof detailMeta !== "object" || Array.isArray(detailMeta)
    || Object.keys(detailKeys).length !== Object.keys(detailMeta).length
  ) return false;
  return Object.entries(detailKeys).every(([candidateId, key]) => {
    const descriptor = detailMeta[candidateId];
    return candidateId.startsWith("cand_")
      && safeDataObjectKey(key)
      && key.startsWith("candidate-details/")
      && descriptor && typeof descriptor === "object" && !Array.isArray(descriptor)
      && /^[a-f0-9]{64}$/.test(String(descriptor.sha256 || ""))
      && Number.isInteger(descriptor.byte_size) && descriptor.byte_size > 0
      && key.split("/").at(-1) === `${descriptor.sha256}.json`;
  });
}

async function readDataObjectBytes(env, backend, key) {
  const safeKey = safeDataObjectKey(key);
  if (!safeKey) return null;
  if (backend === "r2") {
    if (!env?.DATA_ASSETS || typeof env.DATA_ASSETS.get !== "function") return null;
    const object = await env.DATA_ASSETS.get(safeKey);
    if (!object) return null;
    if (typeof object.arrayBuffer === "function") return new Uint8Array(await object.arrayBuffer());
    if (object.body && typeof object.body.arrayBuffer === "function") {
      return new Uint8Array(await object.body.arrayBuffer());
    }
    return null;
  }
  const response = await env.ASSETS.fetch(`https://assets.local/data/${safeKey}`);
  if (!response.ok) return null;
  return new Uint8Array(await response.arrayBuffer());
}

async function readDataManifest(env, backend) {
  let bytes;
  if (backend === "r2") {
    bytes = await readDataObjectBytes(env, backend, DATA_MANIFEST_KEY);
  } else {
    const response = await env.ASSETS.fetch(`https://assets.local${EMBEDDED_DATA_MANIFEST_PATH}`);
    bytes = response.ok ? new Uint8Array(await response.arrayBuffer()) : null;
  }
  if (!bytes) return null;
  try {
    const manifest = JSON.parse(new TextDecoder().decode(bytes));
    return validDataManifest(manifest) ? manifest : null;
  } catch {
    return null;
  }
}

function dataDescriptor(manifest, nameOrCandidateId) {
  if (DATA_ASSET_NAMES.has(nameOrCandidateId)) return manifest.assets[nameOrCandidateId] || null;
  const key = (manifest.candidate_detail_keys || {})[nameOrCandidateId];
  const meta = (manifest.assets.candidate_details || {})[nameOrCandidateId];
  return key && meta ? { key, ...meta } : null;
}

function payloadMatchesDataManifest(payload, manifest) {
  const source = payload?.source_snapshot;
  const digest = payload?.snapshot_sha256 || source?.sha256;
  const byteSize = payload?.snapshot_byte_size || source?.byte_size;
  return Boolean(
    payload && typeof payload === "object" && !Array.isArray(payload)
    && payload.snapshot_key === manifest.snapshot_key
    && payload.generated_at === manifest.generated_at
    && digest === manifest.snapshot_sha256
    && byteSize === manifest.snapshot_byte_size
  );
}

async function loadDataGenerationFrom(env, backend, names, frozenManifest = null) {
  const manifest = frozenManifest || await readDataManifest(env, backend);
  if (!manifest) return null;
  const assets = {};
  const raw = {};
  for (const name of names) {
    const descriptor = dataDescriptor(manifest, name);
    if (!descriptor) return null;
    const bytes = await readDataObjectBytes(env, backend, descriptor.key);
    if (!bytes || bytes.byteLength !== descriptor.byte_size || await sha256Hex(bytes) !== descriptor.sha256) return null;
    let payload;
    try {
      payload = JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      return null;
    }
    if (!payloadMatchesDataManifest(payload, manifest)) return null;
    assets[name] = payload;
    raw[name] = bytes;
  }
  return { backend, manifest, assets, raw };
}

async function loadDataGeneration(env, names) {
  let r2Manifest = null;
  try {
    r2Manifest = await readDataManifest(env, "r2");
    const r2 = r2Manifest
      ? await loadDataGenerationFrom(env, "r2", names, r2Manifest)
      : null;
    if (r2) return r2;
  } catch {
    // Continue to the identity check below.  An R2 transport failure must not
    // authorize a different embedded generation.
  }
  const embeddedManifest = await readDataManifest(env, "embedded");
  if (!embeddedManifest) return null;
  if (r2Manifest) {
    if (!sameDataGeneration(r2Manifest, embeddedManifest)) return null;
    for (const name of names) {
      const requested = dataDescriptor(r2Manifest, name);
      const fallback = dataDescriptor(embeddedManifest, name);
      if (
        !requested || !fallback
        || requested.key !== fallback.key
        || requested.sha256 !== fallback.sha256
        || requested.byte_size !== fallback.byte_size
      ) return null;
    }
  }
  return loadDataGenerationFrom(env, "embedded", names, embeddedManifest);
}

async function readApiAsset(env, path) {
  const response = await env.ASSETS.fetch(`https://assets.local${path}`);
  if (!response.ok) return null;
  const contentType = String(response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("json")) return null;
  const headers = new Headers(response.headers);
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("cache-control", "no-store");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function validRuntimeIdentity(payload, contractVersion) {
  return Boolean(
    payload
    && typeof payload === "object"
    && !Array.isArray(payload)
    && payload.contract_version === contractVersion
    && typeof payload.generated_at === "string"
    && awareIsoTimestamp(payload.generated_at)
    && typeof payload.snapshot_key === "string"
    && payload.snapshot_key.endsWith(".json")
    && !payload.snapshot_key.includes("/")
    && !payload.snapshot_key.includes("\\")
  );
}

function validSourceSnapshotBinding(payload) {
  const source = payload?.source_snapshot;
  return Boolean(
    source
    && typeof source === "object"
    && !Array.isArray(source)
    && typeof source.sha256 === "string"
    && /^[a-f0-9]{64}$/.test(source.sha256)
    && Number.isInteger(source.byte_size)
    && source.byte_size > 0
  );
}

function legacyFullSnapshotFallbackEnabled(env) {
  return String(env?.ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK || "") === "1";
}

function validLiveIndexContract(index) {
  const metadata = index?.contract_metadata;
  const candidates = index?.candidates;
  if (
    !metadata || typeof metadata !== "object" || Array.isArray(metadata)
    || metadata.candidate_limit !== WORKER_LIVE_INDEX_CANDIDATE_LIMIT
    || metadata.byte_size_limit !== WORKER_LIVE_INDEX_BYTE_SIZE_LIMIT
    || metadata.code_normalization !== "worker-facing-live-code-v1"
    || !candidates || typeof candidates !== "object" || Array.isArray(candidates)
    || !Number.isInteger(index.candidate_count)
    || index.candidate_count < 0
    || index.candidate_count > WORKER_LIVE_INDEX_CANDIDATE_LIMIT
  ) return false;
  let actualCount = 0;
  for (const market of ["a_share", "hk", "us"]) {
    const rows = candidates[market];
    if (!rows || typeof rows !== "object" || Array.isArray(rows)) return false;
    actualCount += Object.keys(rows).length;
  }
  return actualCount === index.candidate_count;
}

async function latestRuntime(env, includeGeneration = false) {
  const result = (runtime, manifest = null) => (
    includeGeneration ? { runtime, manifest } : runtime
  );
  const generation = await loadDataGeneration(env, ["runtime"]);
  const publishedRuntime = generation?.assets?.runtime || null;
  if (publishedRuntime) {
    if (
      !validRuntimeIdentity(publishedRuntime, WORKER_RUNTIME_CONTRACT_VERSION)
      || !validSourceSnapshotBinding(publishedRuntime)
    ) throw new Error("manifest-bound worker runtime identity is invalid");
    return result(publishedRuntime, generation.manifest);
  }
  if (await currentDataManifest(env)) {
    throw new Error("manifest-bound worker runtime asset is unavailable");
  }
  const runtime = await readOptionalAssetJson(env, WORKER_RUNTIME_PATH);
  if (runtime) {
    if (
      legacyFullSnapshotFallbackEnabled(env)
      && !Object.hasOwn(runtime, "contract_version")
    ) return result(await latestPick(env));
    if (
      !validRuntimeIdentity(runtime, WORKER_RUNTIME_CONTRACT_VERSION)
      || !validSourceSnapshotBinding(runtime)
    ) {
      throw new Error("worker runtime identity is invalid");
    }
    return result(runtime);
  }
  if (legacyFullSnapshotFallbackEnabled(env)) return result(await latestPick(env));
  throw new Error("worker runtime asset is unavailable");
}

async function latestLiveIndex(env) {
  const generation = await loadDataGeneration(env, ["live_index"]);
  const publishedIndex = generation?.assets?.live_index || null;
  if (publishedIndex) {
    if (
      !validRuntimeIdentity(publishedIndex, WORKER_LIVE_INDEX_CONTRACT_VERSION)
      || !validSourceSnapshotBinding(publishedIndex)
      || !validLiveIndexContract(publishedIndex)
    ) throw new Error("manifest-bound worker live index identity is invalid");
    return publishedIndex;
  }
  if (await currentDataManifest(env)) {
    throw new Error("manifest-bound worker live index asset is unavailable");
  }
  const index = await readOptionalAssetJson(env, WORKER_LIVE_INDEX_PATH);
  if (index) {
    if (
      legacyFullSnapshotFallbackEnabled(env)
      && !Object.hasOwn(index, "contract_version")
    ) return latestPick(env);
    if (
      !validRuntimeIdentity(index, WORKER_LIVE_INDEX_CONTRACT_VERSION)
      || !validSourceSnapshotBinding(index)
    ) {
      throw new Error("worker live index identity is invalid");
    }
    if (!validLiveIndexContract(index)) throw new Error("worker live index candidates are invalid");
    return index;
  }
  if (legacyFullSnapshotFallbackEnabled(env)) return latestPick(env);
  throw new Error("worker live index asset is unavailable");
}

function sameSourceSnapshot(left, right) {
  return Boolean(
    validSourceSnapshotBinding(left)
    && validSourceSnapshotBinding(right)
    && left.source_snapshot.sha256 === right.source_snapshot.sha256
    && left.source_snapshot.byte_size === right.source_snapshot.byte_size
  );
}

function sameSnapshotIdentity(runtime, asset) {
  return Boolean(
    runtime
    && asset
    && runtime.snapshot_key === asset.snapshot_key
    && runtime.generated_at === asset.generated_at
    && sameSourceSnapshot(runtime, asset)
  );
}

async function latestUiAsset(env, path, contractVersion, runtime) {
  if (await currentDataManifest(env)) {
    const error = new Error("manifest-bound worker UI asset is unavailable");
    error.code = "UI_ASSET_UNAVAILABLE";
    throw error;
  }
  const asset = await readOptionalAssetJson(env, path);
  if (!asset) {
    const error = new Error("worker UI asset is unavailable");
    error.code = "UI_ASSET_UNAVAILABLE";
    throw error;
  }
  if (!validRuntimeIdentity(asset, contractVersion) || !validSourceSnapshotBinding(asset)) {
    const error = new Error("worker UI asset contract is invalid");
    error.code = "UI_ASSET_CONTRACT_INVALID";
    throw error;
  }
  if (!sameSnapshotIdentity(runtime, asset)) {
    const error = new Error("worker UI asset identity does not match runtime");
    error.code = "UI_ASSET_IDENTITY_MISMATCH";
    throw error;
  }
  return asset;
}

export function snapshotUseContract(runtime, current = new Date(), primaryEnabled = false) {
  // Freshness is about when the published data was actually generated.  A
  // watchdog run retains the logical primary checkpoint in scheduled_slot,
  // which must not be mistaken for its real publication time.
  const freshness = snapshotFreshness(runtime?.generated_at || null, current, primaryEnabled);
  const allowed = freshness.freshness_state === "fresh";
  const evaluated = current instanceof Date ? current : new Date(current);
  return {
    contract_version: "snapshot-use-v1",
    mode: allowed ? "CURRENT_RESEARCH" : "HISTORICAL_RESEARCH_ONLY",
    freshness_state: freshness.freshness_state,
    current_decision_allowed: allowed,
    execution_review_allowed: Boolean(
      allowed && runtime?.global_decision?.action === "REVIEW_EXECUTABLE_PICK"
    ),
    blocker_codes: allowed ? [] : ["SNAPSHOT_NOT_FRESH"],
    evaluated_at: Number.isNaN(evaluated.getTime()) ? null : evaluated.toISOString(),
    snapshot_key: runtime?.snapshot_key || null,
    source_snapshot_sha256: runtime?.source_snapshot?.sha256 || null,
    source_snapshot_byte_size: Number.isInteger(runtime?.source_snapshot?.byte_size)
      ? runtime.source_snapshot.byte_size
      : null,
  };
}

function effectiveDecisions(runtime, snapshotUse) {
  const productionAction = runtime?.production_decision?.action || "NO_QUALIFIED_PICK";
  const globalAction = runtime?.global_decision?.action || "NO_VALID_PICK";
  return {
    production_action: snapshotUse.current_decision_allowed ? productionAction : "HISTORICAL_ONLY",
    global_action: snapshotUse.current_decision_allowed ? globalAction : "NO_VALID_PICK",
    current_qualified_candidate_count: snapshotUse.current_decision_allowed
      && productionAction === "QUALIFIED_PICK"
      ? Number(runtime?.production_decision?.qualified_candidate_count || 0)
      : 0,
    historical_qualified_candidate_count: productionAction === "QUALIFIED_PICK"
      ? Number(runtime?.production_decision?.qualified_candidate_count || 0)
      : 0,
  };
}

function uiAssetFailure(error) {
  const code = String(error?.code || "UI_ASSET_UNAVAILABLE");
  return json({
    ok: false,
    error: code,
    message: code === "UI_ASSET_IDENTITY_MISMATCH"
      ? "UI 数据与当前运行快照身份不一致，已停止展示当前候选"
      : "轻量页面数据暂时不可用",
  }, 503);
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
  if (decision.action_basis === PRODUCTION_RULE_V4_ACTION_BASIS
    && decision.rule_model_id === PRODUCTION_RULE_V4_MODEL_ID) return 4;
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
    && ((modelVersion === CURRENT_PRODUCTION_MODEL_VERSION) === (contractVersion === 4))
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
    "calendar_version", "estimated_10d_range", "risk_reward", "ten_day_trade_plan", "blocker_codes",
  ];
  return Object.fromEntries(fields.filter((field) => Object.hasOwn(candidate, field)).map((field) => [field, candidate[field]]));
}

function summarizeProductionQualifiedCandidates(decision, snapshot = null) {
  if (!isProductionRuleDecision(decision, snapshot?.model_version) || decision.action !== "QUALIFIED_PICK") return [];
  const contractVersion = productionRuleContractVersion(decision);
  const auditedContract = [3, 4].includes(contractVersion);
  const validatedRows = auditedContract ? validatedV3QualifiedRows(snapshot, decision) : null;
  if (auditedContract && !validatedRows) return [];
  const rawRows = auditedContract
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
  if (![3, 4].includes(productionRuleContractVersion(decision))) return decision;
  return validatedV3DecisionRows(snapshot, decision) ? decision : null;
}

function productionDecisionForRuntime(snapshot) {
  if (snapshot?.contract_version !== WORKER_RUNTIME_CONTRACT_VERSION) {
    return productionDecisionForSnapshot(snapshot);
  }
  const decision = snapshot?.production_decision;
  if (!isProductionRuleDecision(decision, snapshot?.model_version)) return null;
  const primary = decision.primary;
  if (decision.action === "NO_QUALIFIED_PICK") {
    return primary === null || primary === undefined ? decision : null;
  }
  if (
    !primary || typeof primary !== "object" || Array.isArray(primary)
    || primary.status !== "QUALIFIED"
    || typeof primary.qualification_id !== "string"
    || !/^qual_[a-f0-9]{24}$/.test(primary.qualification_id)
    || !Number.isFinite(primary.qualification_score)
  ) return null;
  return decision;
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

function emptyObservationPerformance() {
  return {
    schema_version: null,
    track: "MODEL_OBSERVATION",
    status: "UNAVAILABLE",
    reason: "OBSERVATION_PERFORMANCE_CONTRACT_UNAVAILABLE",
    included_in_shadow_research: false,
    included_in_executable_performance: false,
    authorizes_production: false,
    authorization_status: "DIAGNOSTIC_CONTRACT_UNAVAILABLE",
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
      },
    observation_performance: evaluation?.observation_performance && typeof evaluation.observation_performance === "object"
      ? evaluation.observation_performance
      : emptyObservationPerformance(),
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

async function pickFileForTarget(env, targetDate) {
  const manifest = await loadManifest(env);
  if (!manifest) return null;
  const summaries = Array.isArray(manifest.summaries) ? manifest.summaries : [];
  const match = summaries
    .filter((item) => item.target_date === targetDate && item.cache_key && item.full_snapshot_available !== false)
    .sort((a, b) => `${b.generated_at || ""}`.localeCompare(`${a.generated_at || ""}`))[0];
  const file = match?.cache_key;
  return typeof file === "string" && !file.includes("/") && file.endsWith(".json") ? file : null;
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

function snapshotLiveContract(snapshot, market, code, current = new Date(), primaryEnabled = false) {
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
  const snapshotState = snapshotFreshness(snapshot.generated_at, current, primaryEnabled).freshness_state;
  const snapshotUse = snapshotUseContract(snapshot, current, primaryEnabled);

  return {
    contract_version: "live-quote-v1",
    source_index_contract_version: snapshot.contract_version === WORKER_LIVE_INDEX_CONTRACT_VERSION
      ? snapshot.contract_version
      : null,
    source_snapshot_sha256: snapshot?.source_snapshot?.sha256 || null,
    source_snapshot_byte_size: Number.isInteger(snapshot?.source_snapshot?.byte_size)
      ? snapshot.source_snapshot.byte_size
      : null,
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
    snapshot_use: snapshotUse,
    execution_review_allowed: snapshotUse.execution_review_allowed,
    execution_blocker_codes: snapshotUse.blocker_codes,
    next_refresh: nextActiveRefresh(current, primaryEnabled),
    cache_ttl_seconds: LIVE_CACHE_TTL_MS / 1000,
    kline: Array.isArray(candidate.kline) ? candidate.kline : [],
  };
}

function schedulerPrimaryEnabled(env = {}) {
  return String(env?.GITHUB_ACTIONS_SCHEDULER_ENABLED ?? "1") !== "0";
}

function cloudflareDispatchEnabled(env = {}) {
  return String(env?.CLOUDFLARE_SCHEDULER_ENABLED || "") === "1"
    && Boolean(String(env?.GITHUB_WORKFLOW_DISPATCH_TOKEN || ""));
}

function buildStatusPayload(latest, current = new Date(), env = {}, schedulerHealth = {}) {
  const productionDecision = latest ? productionDecisionForRuntime(latest) : null;
  const currentTime = nowCN();
  const primaryEnabled = schedulerPrimaryEnabled(env);
  const optionalDispatchEnabled = cloudflareDispatchEnabled(env);
  const snapshotUse = snapshotUseContract(latest, current, primaryEnabled);
  const freshness = snapshotFreshness(
    latest?.generated_at || null,
    current,
    primaryEnabled,
  );
  const health = schedulerHealth && typeof schedulerHealth === "object" && !Array.isArray(schedulerHealth)
    ? schedulerHealth
    : {};
  const checkpointEvidenceReady = health.checkpoint_evidence_ready === true;
  const schedulerReadiness = typeof health.scheduler_readiness === "string"
    ? health.scheduler_readiness
    : "UNAVAILABLE";
  const publicationWithinSlo = typeof health.publication_within_slo === "boolean"
    ? health.publication_within_slo
    : null;
  const researchDecisionReady = Boolean(
    latest && productionDecision && snapshotUse.current_decision_allowed,
  );
  const calibratedDecision = latest?.global_decision;
  const calibratedExecutionReady = Boolean(
    snapshotUse.execution_review_allowed
    && calibratedDecision?.action === "REVIEW_EXECUTABLE_PICK"
    && calibratedDecision?.calibrated === true
    && calibratedDecision?.primary
    && typeof calibratedDecision.primary === "object",
  );
  const unattendedRefreshReady = Boolean(
    primaryEnabled
    && checkpointEvidenceReady
    && schedulerReadiness === "READY"
    && publicationWithinSlo === true,
  );
  const sourceStateByMarket = Object.fromEntries(["a_share", "hk", "us"].map((market) => {
    const section = latest?.markets?.[market] || {};
    const health = latest?.quote_health_by_market?.[market] || section.quote_health || {};
    return [market, {
      status: health.status || "unknown",
      quote_coverage: Number.isFinite(Number(health.quote_coverage)) ? Number(health.quote_coverage) : null,
      source_session: health.freshness_reference_session || null,
      source_as_of: health.source_as_of || health.observed_at || null,
    }];
  }));
  return {
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
    scheduler_primary_enabled: primaryEnabled,
    scheduler_primary_provider: "github_actions",
    cloudflare_dispatch_enabled: optionalDispatchEnabled,
    cloudflare_dispatch_optional: true,
    active_refresh_mode: primaryEnabled
      ? "github_actions_primary_with_30m_watchdog"
      : "scheduler_disabled",
    next_active_refresh: nextActiveRefresh(current, primaryEnabled),
    schedule_us_post_close: {
      contract_version: "us-post-close-schedule-v1",
      market_time_zone: "America/New_York",
      market_checkpoint: "16:17",
      primary_beijing_variants: ["04:17 夏令时", "05:17 冬令时"],
      watchdog_beijing_variants: ["04:47 夏令时", "05:47 冬令时"],
      china_days: "周二至周六",
      dst_variant_selected_at_runtime: true,
    },
    recompute_supported: false,
    readiness_contract_version: "production-readiness-v1",
    research_decision_ready: researchDecisionReady,
    checkpoint_evidence_ready: checkpointEvidenceReady,
    unattended_refresh_ready: unattendedRefreshReady,
    calibrated_execution_ready: calibratedExecutionReady,
    scheduler_readiness: schedulerReadiness,
    checkpoint_coverage_status: health.checkpoint_coverage_status || "UNAVAILABLE_NO_COMPLETE_LEDGER",
    checkpoint_evidence_contract_version: health.checkpoint_evidence_contract_version || null,
    expected_checkpoints_24h: Number.isInteger(health.expected_checkpoints_24h)
      ? health.expected_checkpoints_24h : null,
    published_on_time_24h: Number.isInteger(health.published_on_time_24h)
      ? health.published_on_time_24h : null,
    late_recoveries_24h: Number.isInteger(health.late_recoveries_24h)
      ? health.late_recoveries_24h : null,
    missed_checkpoints_24h: checkpointEvidenceReady && Number.isInteger(health.missed_checkpoints_24h)
      ? health.missed_checkpoints_24h : null,
    ledger_started_at: health.ledger_started_at || null,
    evidence_lag_batches: Number.isInteger(health.evidence_lag_batches)
      ? health.evidence_lag_batches : null,
    publication_slo_seconds: Number.isInteger(health.publication_slo_seconds)
      ? health.publication_slo_seconds : null,
    checkpoint_publication_delay_seconds: Number.isInteger(health.checkpoint_publication_delay_seconds)
      ? health.checkpoint_publication_delay_seconds : null,
    publication_within_slo: publicationWithinSlo,
    scheduler_slo: health.scheduler_slo && typeof health.scheduler_slo === "object"
      ? health.scheduler_slo : null,
    has_latest: Boolean(latest),
    latest_path: latest ? "/data/picks/latest.json" : null,
    schema_version: latest?.schema_version || null,
    selector_mode: latest?.selector_mode || null,
    model_version: latest?.model_version || null,
    weights_version: latest?.weights_version || null,
    universe_version: latest?.universe_version || null,
    generated_at: latest?.generated_at || null,
    snapshot_as_of: latest?.generated_at || null,
    next_refresh: nextActiveRefresh(current, primaryEnabled),
    snapshot_key: latest?.snapshot_key || null,
    runtime_contract_version: latest?.contract_version === WORKER_RUNTIME_CONTRACT_VERSION
      ? latest.contract_version
      : null,
    source_snapshot_sha256: latest?.source_snapshot?.sha256 || null,
    source_snapshot_byte_size: Number.isInteger(latest?.source_snapshot?.byte_size)
      ? latest.source_snapshot.byte_size
      : null,
    production_action: productionDecision?.action || "NO_QUALIFIED_PICK",
    qualification_id: productionDecision?.primary?.qualification_id || null,
    calibrated_action: latest?.global_decision?.action || latest?.calibrated_action || "NO_VALID_PICK",
    prediction_id: latest?.global_decision?.primary?.prediction_id || latest?.prediction_id || null,
    snapshot_use: snapshotUse,
    effective_decisions: effectiveDecisions(latest, snapshotUse),
    ...freshness,
  };
}

async function currentDataManifest(env) {
  try {
    const r2 = await readDataManifest(env, "r2");
    if (r2) return { backend: "r2", manifest: r2 };
  } catch {
    // Fall through to the embedded generation.
  }
  const embedded = await readDataManifest(env, "embedded");
  return embedded ? { backend: "embedded", manifest: embedded } : null;
}

function pageRequest(url, defaultLimit = 25, maximumLimit = 100) {
  const positiveInteger = (field, fallback, maximum = null) => {
    if (!url.searchParams.has(field)) return { ok: true, value: fallback };
    const raw = String(url.searchParams.get(field) || "");
    if (!/^[1-9]\d*$/.test(raw)) return { ok: false, field };
    const value = Number(raw);
    if (!Number.isSafeInteger(value) || (maximum !== null && value > maximum)) {
      return { ok: false, field };
    }
    return { ok: true, value };
  };
  const pageResult = positiveInteger("page", 1);
  if (!pageResult.ok) return pageResult;
  const limitResult = positiveInteger("limit", defaultLimit, maximumLimit);
  if (!limitResult.ok) return limitResult;
  const page = pageResult.value;
  const limit = limitResult.value;
  const offset = (page - 1) * limit;
  if (!Number.isSafeInteger(offset)) return { ok: false, field: "page" };
  return { ok: true, page, limit, offset };
}

function pageRows(rows, page) {
  const selected = rows.slice(page.offset, page.offset + page.limit);
  return {
    page: page.page,
    limit: page.limit,
    total: rows.length,
    has_more: page.offset + selected.length < rows.length,
    returned_count: selected.length,
    rows: selected,
  };
}

function parseEventBooleanFilter(searchParams, name) {
  if (!searchParams.has(name)) return { ok: true, present: false, value: null };
  const raw = String(searchParams.get(name) || "").trim().toLowerCase();
  if (["1", "true"].includes(raw)) return { ok: true, present: true, value: true };
  if (["0", "false"].includes(raw)) return { ok: true, present: true, value: false };
  return { ok: false, field: name };
}

function parseEventApiQuery(url) {
  const market = String(url.searchParams.get("market") || "").trim();
  if (market && !LIVE_MARKETS.has(market)) return { ok: false, field: "market" };
  const rawScope = String(url.searchParams.get("scope") || "all").trim().toLowerCase();
  if (!new Set(["all", "decision_bound"]).has(rawScope)) return { ok: false, field: "scope" };
  const decisionBound = parseEventBooleanFilter(url.searchParams, "decision_bound");
  const decisionEligible = parseEventBooleanFilter(url.searchParams, "decision_eligible");
  if (!decisionBound.ok) return decisionBound;
  if (!decisionEligible.ok) return decisionEligible;
  if (rawScope === "decision_bound" && decisionBound.present && decisionBound.value === false) {
    return { ok: false, field: "decision_bound" };
  }
  const eventType = String(url.searchParams.get("event_type") || "").trim().toLowerCase();
  const direction = String(url.searchParams.get("direction") || "").trim().toLowerCase();
  if (direction && !new Set(["positive", "neutral", "negative"]).has(direction)) {
    return { ok: false, field: "direction" };
  }
  const symbol = String(url.searchParams.get("symbol") || "").trim().toLowerCase();
  const q = String(url.searchParams.get("q") || url.searchParams.get("issuer") || "").trim().toLowerCase();
  if (eventType.length > 64) return { ok: false, field: "event_type" };
  if (symbol.length > 64) return { ok: false, field: "symbol" };
  if (q.length > 64) return { ok: false, field: "q" };
  const eventIds = [...new Set(url.searchParams.getAll("event_id")
    .flatMap((value) => String(value || "").split(","))
    .map((value) => value.trim())
    .filter(Boolean))];
  if (eventIds.length > 50 || eventIds.some((eventId) => eventId.length > 128)) {
    return { ok: false, field: "event_id" };
  }
  return {
    ok: true,
    market,
    scope: rawScope,
    decision_bound: decisionBound.present ? decisionBound.value : null,
    decision_eligible: decisionEligible.present ? decisionEligible.value : null,
    event_type: eventType,
    direction,
    symbol,
    q,
    event_ids: eventIds,
  };
}

function normalizedEventDirection(value) {
  const direction = String(value || "").trim().toLowerCase();
  return direction === "positive" || direction === "negative" ? direction : "neutral";
}

function eventRowsForQuery(asset, query) {
  const publication = asset?.event_publication && typeof asset.event_publication === "object"
    ? asset.event_publication
    : {};
  const boundIds = new Set(Array.isArray(publication.decision_bound_event_ids)
    ? publication.decision_bound_event_ids.map((value) => String(value))
    : []);
  const rawEvents = asset?.events;
  const sourceRows = Array.isArray(rawEvents)
    ? rawEvents
    : Array.isArray(rawEvents?.items) ? rawEvents.items : [];
  let rows = sourceRows.map((row, index) => ({
    row: {
      ...row,
      decision_bound: row?.decision_bound === true || boundIds.has(String(row?.event_id || "")),
    },
    index,
  }));
  rows.sort((left, right) => (
    Number(right.row.decision_bound) - Number(left.row.decision_bound)
    || left.index - right.index
  ));
  rows = rows.map(({ row }) => row);
  if (query.scope === "decision_bound") rows = rows.filter((row) => row.decision_bound === true);
  if (query.decision_bound !== null) {
    rows = rows.filter((row) => row.decision_bound === query.decision_bound);
  }
  if (query.market) rows = rows.filter((row) => row?.market === query.market);
  if (query.decision_eligible !== null) {
    rows = rows.filter((row) => (row?.decision_eligible === true) === query.decision_eligible);
  }
  if (query.event_ids.length) {
    const wantedIds = new Set(query.event_ids);
    rows = rows.filter((row) => wantedIds.has(String(row?.event_id || "")));
  }
  if (query.symbol) {
    rows = rows.filter((row) => [row?.symbol, row?.code]
      .some((value) => String(value || "").toLowerCase() === query.symbol));
  }
  if (query.event_type) {
    rows = rows.filter((row) => String(row?.event_type || "").toLowerCase() === query.event_type);
  }
  if (query.direction) {
    rows = rows.filter((row) => normalizedEventDirection(row?.direction) === query.direction);
  }
  if (query.q) {
    rows = rows.filter((row) => [
      row?.event_id, row?.issuer, row?.company, row?.name, row?.code,
      row?.symbol, row?.title, row?.source,
    ].some((value) => String(value || "").toLowerCase().includes(query.q)));
  }
  return { publication, boundIds, rows, sourceCount: sourceRows.length };
}

function schedulerGatePayload(manifestRecord, env) {
  const tokenPresent = Boolean(String(env?.GITHUB_WORKFLOW_DISPATCH_TOKEN || ""));
  const optionalDispatchConfigured = String(env?.CLOUDFLARE_SCHEDULER_ENABLED || "") === "1";
  const optionalDispatchEnabled = optionalDispatchConfigured && tokenPresent;
  const primaryEnabled = schedulerPrimaryEnabled(env);
  const optionalDispatchGap = optionalDispatchEnabled
    ? null
    : optionalDispatchConfigured
      ? "OPTIONAL_DISPATCH_TOKEN_NOT_PROVISIONED"
      : "OPTIONAL_DISPATCH_DISABLED";
  if (!manifestRecord) {
    return {
      ok: false,
      contract_version: "scheduler-health-v2",
      error: "DATA_MANIFEST_UNAVAILABLE",
      snapshot_key: null,
      generated_at: null,
      generation_started_at: null,
      published_at: null,
      publication_backend: null,
      source_invocation_slot: null,
      source_invocation: null,
      effective_checkpoint: null,
      effective_invocation_slot: null,
      effective_invocation: null,
      scheduler_start_delay_seconds: null,
      generation_delay_seconds: null,
      publication_delay_seconds: null,
      missed_checkpoints_24h: null,
      checkpoint_coverage_status: "UNAVAILABLE_NO_COMPLETE_LEDGER",
      checkpoint_evidence_contract_version: null,
      checkpoint_evidence_ready: false,
      scheduler_readiness: "UNAVAILABLE",
      expected_checkpoints_24h: null,
      published_on_time_24h: null,
      late_recoveries_24h: null,
      ledger_started_at: null,
      evidence_lag_batches: null,
      publication_slo_seconds: null,
      checkpoint_publication_delay_seconds: null,
      publication_within_slo: null,
      scheduler_slo: null,
      recovery_mode: null,
      scheduler_enabled: primaryEnabled,
      scheduler_primary_enabled: primaryEnabled,
      scheduler_primary_provider: "github_actions",
      cloudflare_dispatch_enabled: optionalDispatchEnabled,
      cloudflare_dispatch_optional: true,
      cloudflare_dispatch_gap: optionalDispatchGap,
      unattended_refresh_ready: false,
      scheduler_gap: primaryEnabled ? "DATA_MANIFEST_UNAVAILABLE" : "GITHUB_ACTIONS_PRIMARY_DISABLED",
    };
  }
  const { backend, manifest } = manifestRecord;
  const health = manifest.scheduler_health || {};
  const checkpointCoverageStatus = health.checkpoint_coverage_status || "UNAVAILABLE_NO_COMPLETE_LEDGER";
  const checkpointEvidenceContract = health.checkpoint_evidence_contract_version || null;
  const checkpointEvidenceReady = health.checkpoint_evidence_ready === true;
  const schedulerReadiness = typeof health.scheduler_readiness === "string"
    ? health.scheduler_readiness
    : "UNAVAILABLE";
  const publicationWithinSlo = typeof health.publication_within_slo === "boolean"
    ? health.publication_within_slo
    : null;
  const unattendedRefreshReady = Boolean(
    primaryEnabled
    && checkpointEvidenceReady
    && schedulerReadiness === "READY"
    && publicationWithinSlo === true,
  );
  return {
    ok: true,
    contract_version: "scheduler-health-v2",
    snapshot_key: manifest.snapshot_key,
    generated_at: manifest.generated_at,
    generation_started_at: health.generation_started_at || null,
    published_at: manifest.published_at || health.published_at || null,
    publication_backend: backend,
    source_invocation_slot: health.source_invocation_slot || null,
    source_invocation: health.source_invocation_slot || null,
    effective_checkpoint: health.effective_checkpoint || null,
    effective_invocation_slot: health.effective_invocation_slot || null,
    effective_invocation: health.effective_invocation_slot || null,
    scheduler_start_delay_seconds: Number.isInteger(health.scheduler_start_delay_seconds)
      ? health.scheduler_start_delay_seconds : null,
    generation_delay_seconds: Number.isInteger(health.generation_delay_seconds)
      ? health.generation_delay_seconds : null,
    publication_delay_seconds: Number.isInteger(health.publication_delay_seconds)
      ? health.publication_delay_seconds : null,
    missed_checkpoints_24h: checkpointCoverageStatus === "COMPLETE_24H_LEDGER"
      && checkpointEvidenceContract === "scheduler-checkpoint-ledger-v1"
      && Number.isInteger(health.missed_checkpoints_24h)
      ? health.missed_checkpoints_24h : null,
    checkpoint_coverage_status: checkpointCoverageStatus,
    checkpoint_evidence_contract_version: checkpointEvidenceContract,
    checkpoint_evidence_ready: checkpointEvidenceReady,
    scheduler_readiness: schedulerReadiness,
    expected_checkpoints_24h: Number.isInteger(health.expected_checkpoints_24h)
      ? health.expected_checkpoints_24h : null,
    published_on_time_24h: Number.isInteger(health.published_on_time_24h)
      ? health.published_on_time_24h : null,
    late_recoveries_24h: Number.isInteger(health.late_recoveries_24h)
      ? health.late_recoveries_24h : null,
    ledger_started_at: health.ledger_started_at || null,
    evidence_lag_batches: Number.isInteger(health.evidence_lag_batches)
      ? health.evidence_lag_batches : null,
    publication_slo_seconds: Number.isInteger(health.publication_slo_seconds)
      ? health.publication_slo_seconds : null,
    checkpoint_publication_delay_seconds: Number.isInteger(health.checkpoint_publication_delay_seconds)
      ? health.checkpoint_publication_delay_seconds : null,
    publication_within_slo: publicationWithinSlo,
    scheduler_slo: health.scheduler_slo && typeof health.scheduler_slo === "object"
      ? health.scheduler_slo : null,
    recovery_mode: health.recovery_mode || "none",
    scheduler_enabled: primaryEnabled,
    scheduler_primary_enabled: primaryEnabled,
    scheduler_primary_provider: "github_actions",
    cloudflare_dispatch_enabled: optionalDispatchEnabled,
    cloudflare_dispatch_optional: true,
    cloudflare_dispatch_gap: optionalDispatchGap,
    unattended_refresh_ready: unattendedRefreshReady,
    scheduler_gap: primaryEnabled ? null : "GITHUB_ACTIONS_PRIMARY_DISABLED",
  };
}

function dataNameForKey(manifest, key) {
  for (const name of DATA_ASSET_NAMES) {
    if (manifest?.assets?.[name]?.key === key) return name;
  }
  for (const [candidateId, candidateKey] of Object.entries(manifest?.candidate_detail_keys || {})) {
    if (candidateKey === key) return candidateId;
  }
  return null;
}

function sameDataGeneration(left, right) {
  return Boolean(
    left && right
    && left.snapshot_key === right.snapshot_key
    && left.generated_at === right.generated_at
    && left.snapshot_sha256 === right.snapshot_sha256
    && left.snapshot_byte_size === right.snapshot_byte_size
  );
}

async function immutableDataGeneration(env, record, name) {
  let generation = await loadDataGenerationFrom(env, record.backend, [name], record.manifest);
  if (generation || record.backend !== "r2") return generation;
  const embeddedManifest = await readDataManifest(env, "embedded");
  if (!sameDataGeneration(record.manifest, embeddedManifest)) return null;
  const requested = dataDescriptor(record.manifest, name);
  const fallback = dataDescriptor(embeddedManifest, name);
  if (
    !requested || !fallback
    || requested.key !== fallback.key
    || requested.sha256 !== fallback.sha256
    || requested.byte_size !== fallback.byte_size
  ) return null;
  generation = await loadDataGenerationFrom(env, "embedded", [name], embeddedManifest);
  return generation;
}

async function handleApi(request, env) {
  const url = new URL(request.url);
  if (url.pathname === "/api/gate-status") {
    const record = await currentDataManifest(env);
    const payload = schedulerGatePayload(record, env);
    const digest = await derivedRepresentationDigest(
      record?.manifest?.manifest_sha256 || record?.manifest?.snapshot_sha256 || "unavailable",
      {
        scheduler_primary_enabled: schedulerPrimaryEnabled(env),
        cloudflare_dispatch_enabled: cloudflareDispatchEnabled(env),
        publication_backend: record?.backend || "unavailable",
      },
    );
    return jsonWithEtag(request, payload, digest);
  }

  if (url.pathname.startsWith("/api/data/")) {
    const key = decodeURIComponent(url.pathname.slice("/api/data/".length));
    const record = await currentDataManifest(env);
    const name = record ? dataNameForKey(record.manifest, key) : null;
    if (!record || !name) return json({ ok: false, error: "IMMUTABLE_ASSET_NOT_FOUND" }, 404);
    const generation = await immutableDataGeneration(env, record, name);
    if (!generation) return json({ ok: false, error: "IMMUTABLE_ASSET_UNAVAILABLE" }, 503);
    const descriptor = dataDescriptor(generation.manifest, name);
    if (requestMatchesEtag(request, descriptor.sha256)) {
      return new Response(null, {
        status: 304,
        headers: {
          etag: quotedEtag(descriptor.sha256),
          "cache-control": "public, max-age=31536000, immutable",
        },
      });
    }
    return new Response(generation.raw[name], {
      status: 200,
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "public, max-age=31536000, immutable",
        etag: quotedEtag(descriptor.sha256),
      },
    });
  }

  if (url.pathname === "/api/status") {
    const { runtime: latest, manifest } = await latestRuntime(env, true);
    return json(buildStatusPayload(
      latest,
      new Date(),
      env,
      manifest?.scheduler_health || {},
    ));
  }

  if (url.pathname === "/api/latest") {
    const latest = await readApiAsset(env, "/data/picks/latest.json");
    if (!latest) return json({ error: "暂无历史决策缓存" }, 404);
    return latest;
  }

  if (url.pathname === "/api/latest-summary") {
    let runtime;
    try {
      const generation = await loadDataGeneration(env, ["runtime", "summary"]);
      if (generation) {
        runtime = generation.assets.runtime;
        const latest = generation.assets.summary;
        const current = new Date();
        const status = buildStatusPayload(
          runtime,
          current,
          env,
          generation.manifest?.scheduler_health || {},
        );
        const snapshotUse = status.snapshot_use;
        const effective = status.effective_decisions;
        return json({
          contract_version: WORKER_UI_BOOTSTRAP_CONTRACT_VERSION,
          ok: true,
          time: status.time,
          status,
          snapshot_use: snapshotUse,
          effective_decisions: effective,
          latest: { ...latest, snapshot_use: snapshotUse, effective_decisions: effective },
        });
      }
      runtime = await latestRuntime(env);
      const latest = await latestUiAsset(
        env,
        WORKER_UI_BOOTSTRAP_PATH,
        WORKER_UI_BOOTSTRAP_CONTRACT_VERSION,
        runtime,
      );
      const current = new Date();
      const status = buildStatusPayload(
        runtime,
        current,
        env,
        {},
      );
      const snapshotUse = status.snapshot_use;
      const effective = status.effective_decisions;
      return json({
        contract_version: WORKER_UI_BOOTSTRAP_CONTRACT_VERSION,
        ok: true,
        time: status.time,
        status,
        snapshot_use: snapshotUse,
        effective_decisions: effective,
        latest: { ...latest, snapshot_use: snapshotUse, effective_decisions: effective },
      });
    } catch (error) {
      if (error?.code === "UI_ASSET_UNAVAILABLE" && legacyFullSnapshotFallbackEnabled(env) && runtime) {
        return json({ ok: true, time: nowCN(), latest: summarizePick(runtime) });
      }
      if (String(error?.code || "").startsWith("UI_ASSET_")) return uiAssetFailure(error);
      throw error;
    }
  }

  const candidateDetailMatch = url.pathname.match(/^\/api\/candidates\/(cand_[a-f0-9]{20})$/);
  if (candidateDetailMatch) {
    const candidateId = candidateDetailMatch[1];
    const generation = await loadDataGeneration(env, ["runtime", candidateId]);
    if (!generation) return json({ ok: false, error: "CANDIDATE_DETAIL_NOT_FOUND" }, 404);
    const runtime = generation.assets.runtime;
    const payload = generation.assets[candidateId];
    const snapshotUse = snapshotUseContract(runtime, new Date(), schedulerPrimaryEnabled(env));
    return json({
      ...payload,
      snapshot_use: snapshotUse,
      effective_decisions: effectiveDecisions(runtime, snapshotUse),
    });
  }

  if (url.pathname === "/api/candidates") {
    const pagination = pageRequest(url, 25, 100);
    if (!pagination.ok) {
      return json({ ok: false, error: "INVALID_PAGINATION", field: pagination.field }, 400);
    }
    const market = String(url.searchParams.get("market") || "").trim();
    const query = String(url.searchParams.get("q") || "").trim().slice(0, 64).toLowerCase();
    try {
      const generation = await loadDataGeneration(env, ["runtime", "candidates"]);
      if (generation) {
        const runtime = generation.assets.runtime;
        const asset = generation.assets.candidates;
        const allRows = Array.isArray(asset.candidates) ? asset.candidates : [];
        let filtered = market ? allRows.filter((row) => row?.market === market) : allRows;
        if (query) {
          filtered = filtered.filter((row) => [row?.code, row?.name]
            .some((value) => String(value || "").toLowerCase().includes(query)));
        }
        const page = pageRows(filtered, pagination);
        const snapshotUse = snapshotUseContract(runtime, new Date(), schedulerPrimaryEnabled(env));
        return json({
          contract_version: asset.contract_version,
          ok: true,
          snapshot_key: asset.snapshot_key,
          generated_at: asset.generated_at,
          snapshot_sha256: asset.snapshot_sha256,
          source_snapshot: asset.source_snapshot,
          scanned_count: asset.scanned_count || 0,
          evaluated_count: asset.evaluated_count
            ?? runtime?.production_decision?.evaluated_candidate_count
            ?? 0,
          candidate_count: filtered.length,
          page: page.page,
          limit: page.limit,
          total: page.total,
          has_more: page.has_more,
          returned_count: page.returned_count,
          candidates: page.rows,
          role_contract_version: asset.role_contract_version,
          production_selection: asset.production_selection,
          dual_low_model: asset.dual_low_model || {},
          snapshot_use: snapshotUse,
          effective_decisions: effectiveDecisions(runtime, snapshotUse),
        });
      }
      const runtime = await latestRuntime(env);
      const asset = await latestUiAsset(
        env,
        WORKER_UI_CANDIDATES_PATH,
        WORKER_UI_CANDIDATES_CONTRACT_VERSION,
        runtime,
      );
      const snapshotUse = snapshotUseContract(runtime, new Date(), schedulerPrimaryEnabled(env));
      const allRows = Array.isArray(asset.candidates) ? asset.candidates : [];
      let filtered = market ? allRows.filter((row) => row?.market === market) : allRows;
      if (query) {
        filtered = filtered.filter((row) => [row?.code, row?.name]
          .some((value) => String(value || "").toLowerCase().includes(query)));
      }
      const page = pageRows(filtered, pagination);
      return json({
        ...asset,
        candidate_count: filtered.length,
        page: page.page,
        limit: page.limit,
        total: page.total,
        has_more: page.has_more,
        returned_count: page.returned_count,
        candidates: page.rows,
        snapshot_use: snapshotUse,
        effective_decisions: effectiveDecisions(runtime, snapshotUse),
      });
    } catch (error) {
      if (String(error?.code || "").startsWith("UI_ASSET_")) return uiAssetFailure(error);
      throw error;
    }
  }

  if (url.pathname === "/api/events") {
    const pagination = pageRequest(url, 25, 50);
    if (!pagination.ok) {
      return json({ ok: false, error: "INVALID_PAGINATION", field: pagination.field }, 400);
    }
    const query = parseEventApiQuery(url);
    if (!query.ok) {
      return json({ ok: false, error: "INVALID_EVENT_FILTER", field: query.field }, 400);
    }
    try {
      const generation = await loadDataGeneration(env, ["runtime", "events"]);
      if (generation) {
        const runtime = generation.assets.runtime;
        const asset = generation.assets.events;
        const { publication, boundIds, rows, sourceCount } = eventRowsForQuery(asset, query);
        const page = pageRows(rows, pagination);
        const snapshotUse = snapshotUseContract(runtime, new Date(), schedulerPrimaryEnabled(env));
        const matchedBoundCount = rows.filter((row) => row.decision_bound === true).length;
        const returnedBoundCount = page.rows.filter((row) => row.decision_bound === true).length;
        return json({
          contract_version: EVENT_LIST_CONTRACT_VERSION,
          ok: true,
          snapshot_key: asset.snapshot_key,
          generated_at: asset.generated_at,
          snapshot_sha256: asset.snapshot_sha256,
          source_snapshot: asset.source_snapshot,
          ordering_contract_version: EVENT_ORDERING_CONTRACT_VERSION,
          filters: {
            scope: query.scope,
            decision_bound: query.decision_bound,
            market: query.market || null,
            decision_eligible: query.decision_eligible,
            event_ids: query.event_ids,
            symbol: query.symbol || null,
            event_type: query.event_type || null,
            direction: query.direction || null,
            q: query.q || null,
          },
          source_event_count: Number(publication.total || 0),
          published_event_count: Number(publication.published || sourceCount),
          event_count: rows.length,
          page: page.page,
          limit: page.limit,
          total: page.total,
          has_more: page.has_more,
          returned_count: page.returned_count,
          events: page.rows,
          event_publication: publication,
          decision_bound: {
            total: boundIds.size,
            matched: matchedBoundCount,
            returned: returnedBoundCount,
            all_matched_returned: matchedBoundCount === returnedBoundCount,
            ids: [...boundIds].sort(),
          },
          snapshot_use: snapshotUse,
          effective_decisions: effectiveDecisions(runtime, snapshotUse),
        });
      }
      const runtime = await latestRuntime(env);
      const asset = await latestUiAsset(
        env,
        WORKER_UI_EVENTS_PATH,
        WORKER_UI_EVENTS_CONTRACT_VERSION,
        runtime,
      );
      const { publication, boundIds, rows, sourceCount } = eventRowsForQuery(asset, query);
      const page = pageRows(rows, pagination);
      const snapshotUse = snapshotUseContract(runtime, new Date(), schedulerPrimaryEnabled(env));
      const matchedBoundCount = rows.filter((row) => row.decision_bound === true).length;
      const returnedBoundCount = page.rows.filter((row) => row.decision_bound === true).length;
      return json({
        ...asset,
        contract_version: EVENT_LIST_CONTRACT_VERSION,
        ordering_contract_version: EVENT_ORDERING_CONTRACT_VERSION,
        filters: {
          scope: query.scope,
          decision_bound: query.decision_bound,
          market: query.market || null,
          decision_eligible: query.decision_eligible,
          event_ids: query.event_ids,
          symbol: query.symbol || null,
          event_type: query.event_type || null,
          direction: query.direction || null,
          q: query.q || null,
        },
        source_event_count: Number(publication.total || 0),
        published_event_count: Number(publication.published || sourceCount),
        event_count: rows.length,
        page: page.page,
        limit: page.limit,
        total: page.total,
        has_more: page.has_more,
        returned_count: page.returned_count,
        events: page.rows,
        event_publication: publication,
        decision_bound: {
          total: boundIds.size,
          matched: matchedBoundCount,
          returned: returnedBoundCount,
          all_matched_returned: matchedBoundCount === returnedBoundCount,
          ids: [...boundIds].sort(),
        },
        snapshot_use: snapshotUse,
        effective_decisions: effectiveDecisions(runtime, snapshotUse),
      });
    } catch (error) {
      if (String(error?.code || "").startsWith("UI_ASSET_")) return uiAssetFailure(error);
      throw error;
    }
  }

  if (url.pathname === "/api/history") {
    const pagination = pageRequest(url, 5, 5);
    if (!pagination.ok) {
      return json({ ok: false, error: "INVALID_PAGINATION", field: pagination.field }, 400);
    }
    const generation = await loadDataGeneration(env, ["runtime", "history"]);
    if (generation) {
      const asset = generation.assets.history;
      const view = url.searchParams.get("view") === "raw" ? "raw" : "daily";
      const rows = Array.isArray(asset.history) ? [...asset.history] : [];
      rows.sort((a, b) => `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`));
      const days = latestDecisionDays(rows);
      const selected = view === "raw" ? rows : days;
      const page = pageRows(selected, pagination);
      return json({
        contract_version: asset.contract_version,
        ok: true,
        time: nowCN(),
        snapshot_key: asset.snapshot_key,
        generated_at: asset.generated_at,
        source_snapshot: asset.source_snapshot,
        latest: generation.assets.runtime.latest_summary || null,
        page: page.page,
        limit: page.limit,
        total: page.total,
        has_more: page.has_more,
        returned_count: page.returned_count,
        meta: {
          ...historyMetadata(rows, days, view, page.returned_count, asset.history_evaluation),
          page: page.page,
          limit: page.limit,
          total: page.total,
          has_more: page.has_more,
        },
        history_evaluation: asset.history_evaluation || null,
        observation_ledger: asset.observation_ledger || null,
        observation_performance: asset.observation_performance || null,
        rule_outcome_tracking: asset.rule_outcome_tracking || null,
        history: page.rows,
      });
    }
    const view = url.searchParams.get("view") === "raw" ? "raw" : "daily";
    const manifest = await loadManifest(env);
    if (!manifest) return json({ ok: false, error: "HISTORY_MANIFEST_UNAVAILABLE" }, 503);
    const rows = Array.isArray(manifest.summaries) ? [...manifest.summaries] : [];
    rows.sort((a, b) =>
      `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`),
    );
    const days = latestDecisionDays(rows);
    const selectedRows = view === "raw" ? rows : days;
    const page = pageRows(selectedRows, pagination);
    const latest = await latestRuntime(env);
    return json({
      ok: true,
      time: nowCN(),
      latest: latest
        ? latest.contract_version === WORKER_RUNTIME_CONTRACT_VERSION
          ? latest.latest_summary || null
          : summarizePick(latest)
        : null,
      page: page.page,
      limit: page.limit,
      total: page.total,
      has_more: page.has_more,
      returned_count: page.returned_count,
      meta: {
        ...historyMetadata(rows, days, view, page.returned_count, manifest.history_evaluation),
        page: page.page,
        limit: page.limit,
        total: page.total,
        has_more: page.has_more,
      },
      history_evaluation: manifest.history_evaluation || null,
      history: page.rows,
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
      if (snapshotKey.includes("/") || snapshotKey.includes("\\") || !snapshotKey.endsWith(".json")) {
        return json({ error: "未找到指定历史快照" }, 404);
      }
      const snapshot = await readApiAsset(env, `/data/picks/${snapshotKey}`);
      if (!snapshot) return json({ error: "未找到指定历史快照" }, 404);
      return snapshot;
    }
    const targetDate = url.searchParams.get("date");
    if (targetDate && !validIsoDate(targetDate)) {
      return json({ error: "INVALID_DATE", message: "date 必须是有效的 YYYY-MM-DD 日期" }, 400);
    }
    const pickFile = targetDate ? await pickFileForTarget(env, targetDate) : "latest.json";
    if (!pickFile && targetDate) {
      return json({ error: "PICK_NOT_FOUND", message: `没有 ${targetDate} 的历史快照` }, 404);
    }
    const pick = pickFile ? await readApiAsset(env, `/data/picks/${pickFile}`) : null;
    if (!pick) {
      return json({ error: "暂无选股快照。请等待每日任务生成后再查看。" }, 404);
    }
    return pick;
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
      latest = await latestLiveIndex(env);
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
    if (!snapshotCandidate(latest, market, code)) {
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
        ...snapshotLiveContract(latest, market, code, new Date(), schedulerPrimaryEnabled(env)),
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

function scheduledCronContext(controller) {
  const cron = String(controller?.cron || "");
  const schedule = CLOUDFLARE_SCHEDULED_CRONS.get(cron);
  if (!schedule) {
    throw new Error(`scheduled cron is not whitelisted: ${cron || "missing"}`);
  }
  const scheduledTime = Number(controller?.scheduledTime);
  const scheduledAt = new Date(scheduledTime);
  if (!Number.isFinite(scheduledTime) || Number.isNaN(scheduledAt.getTime())) {
    throw new Error("scheduledTime is invalid");
  }
  const weekday = scheduledAt.getUTCDay();
  const hour = scheduledAt.getUTCHours();
  const minute = scheduledAt.getUTCMinutes();
  if (
    !schedule.weekdays.has(weekday)
    || minute !== schedule.minute
    || !schedule.hours.has(hour)
    || scheduledAt.getUTCSeconds() !== 0
    || scheduledAt.getUTCMilliseconds() !== 0
  ) {
    throw new Error(`scheduledTime does not match whitelisted cron: ${scheduledAt.toISOString()}`);
  }
  return { cron, schedule, scheduledAt, minute, hour };
}

function newYorkHour(date) {
  const value = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date).find((part) => part.type === "hour")?.value;
  return Number(value);
}

export function canonicalGithubCronForScheduled(controller) {
  const { schedule, minute, hour } = scheduledCronContext(controller);
  return `${minute} ${hour} * * ${schedule.githubWeekdays}`;
}

async function dispatchScheduledWorkflow(controller, env) {
  if (String(env?.CLOUDFLARE_SCHEDULER_ENABLED || "") !== "1") {
    return { dispatched: false, reason: "SCHEDULER_DISABLED" };
  }
  const token = String(env?.GITHUB_WORKFLOW_DISPATCH_TOKEN || "");
  if (!token) return { dispatched: false, reason: "GITHUB_WORKFLOW_DISPATCH_TOKEN_MISSING" };
  const context = scheduledCronContext(controller);
  if (
    Number.isInteger(context.schedule.newYorkHour)
    && newYorkHour(context.scheduledAt) !== context.schedule.newYorkHour
  ) {
    return { dispatched: false, reason: "INACTIVE_US_POST_CLOSE_DST_VARIANT" };
  }
  const cron = `${context.minute} ${context.hour} * * ${context.schedule.githubWeekdays}`;
  const scheduledAt = context.scheduledAt;
  const response = await fetch(GITHUB_WORKFLOW_DISPATCH_URL, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "user-agent": "xuangu-cloudflare-scheduler",
      "x-github-api-version": "2022-11-28",
    },
    body: JSON.stringify({
      ref: "main",
      inputs: {
        scheduler: "cloudflare-cron-v1",
        cron,
        scheduled_at: scheduledAt.toISOString(),
      },
    }),
  });
  if (!response.ok) {
    throw new Error(`GitHub workflow dispatch failed with status ${response.status}`);
  }
  return { dispatched: true };
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
      } else if (url.pathname === EMBEDDED_DATA_MANIFEST_PATH) {
        const assetResponse = await env.ASSETS.fetch(request);
        const headers = new Headers(assetResponse.headers);
        headers.set("cache-control", "no-store");
        response = new Response(assetResponse.body, {
          status: assetResponse.status,
          statusText: assetResponse.statusText,
          headers,
        });
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
  async scheduled(controller, env) {
    return dispatchScheduledWorkflow(controller, env);
  },
};

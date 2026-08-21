/*
 * Derived from AlphaSift revision
 * 9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf; licensed under Apache-2.0.
 * Rewritten and modified as a dependency-free JavaScript package on 2026-08-18.
 * See THIRD_PARTY_NOTICES.md and LICENSES/Apache-2.0-AlphaSift.txt.
 */

const MODEL_ID = "dsa-screening-score-v1";

const FACTOR_NAMES = Object.freeze([
  "value",
  "stability",
  "liquidity",
  "momentum",
  "activity",
  "reversal",
  "size",
]);

const DEFAULT_SCORING_PROFILE = Object.freeze({
  momentumBase: 60,
  momentumIntradaySlope: 5,
  momentumChaseStartPct: 5,
  momentumChasePenaltySlope: 10,
  momentumDownsideStartPct: -2,
  momentumDownsidePenaltySlope: 3,
  momentum60dBase: 55,
  momentum60dSlope: 0.9,
  momentum60dOverheatPct: 45,
  momentum60dOverheatPenaltySlope: 0.8,
  momentum60dBreakdownPct: -20,
  momentum60dBreakdownPenaltySlope: 0.7,
  macdBullishBonus: 6,
  macdBearishPenalty: 8,
  reversalIdealChangePct: -3,
  reversalDistancePenaltySlope: 13,
  reversalCollapseStartPct: -8,
  reversalCollapsePenaltySlope: 10,
  reversalChaseStartPct: 1,
  reversalChasePenaltySlope: 8,
  rsiOversoldBonus: 10,
  rsiOverboughtPenalty: 14,
  activityIdealVolumeRatio: 2,
  activityVolumeRatioDistanceSlope: 15,
  activityHighVolumeRatio: 5,
  activityHighVolumeRatioPenaltySlope: 8,
  activityIdealTurnoverRate: 4,
  activityTurnoverDistanceSlope: 8,
  activityHighTurnoverRate: 12,
  activityHighTurnoverPenaltySlope: 5,
  stabilityBase: 78,
  stabilityChangeAbsPenaltySlope: 3,
  stabilityHotChangePct: 7,
  stabilityHotChangePenaltySlope: 5,
  stabilityHighTurnoverRate: 10,
  stabilityHighTurnoverPenaltySlope: 2,
  stabilityHighVolumeRatio: 5,
  stabilityHighVolumeRatioPenaltySlope: 4,
  stabilityInvalidPePenalty: 18,
  stabilityHighVolatilityPct: 45,
  stabilityHighVolatilityPenaltySlope: 0.45,
  stabilityMaxDrawdownFloorPct: -12,
  stabilityDrawdownPenaltySlope: 1.2,
  stabilityHighAtrPct: 6,
  stabilityHighAtrPenaltySlope: 2,
  stabilityLowDailyQualityScore: 80,
  stabilityLowDailyQualityPenaltySlope: 0.35,
  stabilityBadDailyQualityFlagPenalty: 8,
});

const DEFAULT_RISK_PROFILE = Object.freeze({
  maxPenalty: 12,
  vetoHighRisk: false,
  chaseChangePct: 8,
  chasePoints: 4,
  breakdownChangePct: -7,
  breakdownPoints: 3.5,
  abnormalVolumeRatio: 6,
  abnormalVolumeRatioPoints: 3,
  highTurnoverRate: 15,
  highTurnoverPoints: 3,
  invalidPePoints: 3,
  highPb: 8,
  highPbPoints: 2,
  weakSignalScore: 45,
  weakSignalPoints: 2.5,
  macdBearishPoints: 2,
  rsiOverboughtPoints: 1.5,
  lowExternalConfidence: 0.35,
  lowExternalConfidencePoints: 1.5,
  externalRiskPoints: 1.2,
  externalRiskPointsCap: 4,
  deepRiskPoints: 1.5,
  deepRiskPointsCap: 4.5,
  lowDailyQualityScore: 70,
  lowDailyQualityPoints: 2,
  badDailyQualityFlagPoints: 3,
  staleDailyCachePoints: 2.5,
  fallbackDailyErrorsPoints: 1.5,
  fetchFailedDailyPoints: 6,
});

const DUAL_LOW_STRATEGY = deepFreeze({
  id: "dual_low",
  version: "1.2-js.1",
  name: "双低选股",
  description: "低 PE、低 PB 为基础，叠加稳定性、流动性与不过热的交易特征。",
  maxOutput: 5,
  hardFilters: {
    excludeST: true,
    excludeDelistingNames: true,
    amount: { min: 50_000_000 },
    peRatio: { min: 0, max: 15 },
    pbRatio: { min: 0, max: 2 },
    totalMarketCap: { min: 5_000_000_000, max: 300_000_000_000 },
    price: { min: 3, max: 80 },
    changePct: { min: -4.5, max: 4.5 },
  },
  weights: {
    value: 0.34,
    stability: 0.2,
    liquidity: 0.14,
    momentum: 0.1,
    activity: 0.1,
    reversal: 0.06,
    size: 0.06,
  },
  scoringProfile: {
    momentumChaseStartPct: 2.5,
    momentumChasePenaltySlope: 18,
    momentumDownsideStartPct: -2.5,
    activityIdealVolumeRatio: 1.2,
    activityIdealTurnoverRate: 2,
    activityHighVolumeRatio: 4,
    activityHighTurnoverRate: 8,
    stabilityHotChangePct: 4,
    stabilityHighTurnoverRate: 8,
    stabilityHighVolumeRatio: 4,
  },
  risk: {
    maxPenalty: 12,
    vetoHighRisk: false,
    chaseChangePct: 5,
    abnormalVolumeRatio: 4,
    highTurnoverRate: 8,
    lowExternalConfidence: 0.45,
  },
  portfolioPenalty: {
    enabled: true,
    freeSlotsPerBucket: 2,
    step: 3,
    maxPenalty: 9,
    buckets: {
      金融: ["券商", "证券", "银行", "保险", "金融"],
      地产链: ["地产", "房地产", "建材", "家居", "物业"],
      周期: ["钢铁", "煤炭", "有色", "化工"],
    },
  },
});

const HARD_FILTER_FIELDS = Object.freeze([
  ["amount", "成交额"],
  ["peRatio", "PE TTM"],
  ["pbRatio", "PB"],
  ["totalMarketCap", "总市值"],
  ["price", "股价"],
  ["changePct", "当日涨跌幅"],
]);

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
}

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function clamp(value, min = 0, max = 100) {
  return Math.min(Math.max(Number(value), min), max);
}

function round4(value) {
  return Math.round((Number(value) + Number.EPSILON) * 10_000) / 10_000;
}

function makeReason(stage, code, message, details = {}) {
  return { stage, code, message, ...details };
}

function cloneStock(stock) {
  const copy = { ...stock };
  for (const field of ["dailyQualityFlags", "externalRiskTags", "deepRiskTags"]) {
    if (Array.isArray(stock?.[field])) copy[field] = [...stock[field]];
  }
  return copy;
}

function normalizeStatus(value) {
  return String(value ?? "").trim().toLowerCase();
}

function isMacdBullish(value) {
  return ["bullish", "golden_cross", "zero_axis_golden_cross"].includes(normalizeStatus(value));
}

function isMacdBearish(value) {
  return ["bearish", "death_cross", "zero_axis_death_cross"].includes(normalizeStatus(value));
}

function isRsiOversold(value) {
  return ["oversold", "超卖"].includes(normalizeStatus(value));
}

function isRsiOverbought(value) {
  return ["overbought", "超买"].includes(normalizeStatus(value));
}

function resolveStrategy(strategy = DUAL_LOW_STRATEGY) {
  if (!strategy || typeof strategy !== "object") {
    throw new TypeError("strategy 必须是一个对象");
  }
  if (!String(strategy.id ?? "").trim() || !String(strategy.version ?? "").trim()) {
    throw new TypeError("strategy.id 和 strategy.version 不能为空");
  }
  const weights = strategy.weights ?? {};
  let total = 0;
  for (const factor of FACTOR_NAMES) {
    const weight = weights[factor] ?? 0;
    if (!isFiniteNumber(weight) || weight < 0) {
      throw new TypeError(`strategy.weights.${factor} 必须是非负有限数值`);
    }
    total += weight;
  }
  if (total <= 0) throw new TypeError("strategy.weights 的总和必须大于 0");
  return strategy;
}

function normalizedWeights(strategy) {
  const total = FACTOR_NAMES.reduce((sum, factor) => sum + (strategy.weights[factor] ?? 0), 0);
  return Object.fromEntries(
    FACTOR_NAMES.map((factor) => [factor, (strategy.weights[factor] ?? 0) / total]),
  );
}

function filterStock(stock, strategy = DUAL_LOW_STRATEGY) {
  const resolved = resolveStrategy(strategy);
  const reasons = [];
  if (!stock || typeof stock !== "object") {
    return [makeReason("validation", "validation.stock.invalid", "股票记录必须是对象")];
  }
  if (!String(stock.code ?? "").trim()) {
    reasons.push(makeReason("validation", "validation.code.missing", "缺少股票代码"));
  }
  if (!String(stock.name ?? "").trim()) {
    reasons.push(makeReason("validation", "validation.name.missing", "缺少股票名称"));
  }

  const filters = resolved.hardFilters ?? {};
  const name = String(stock.name ?? "");
  if (filters.excludeST && stock.isST === true) {
    reasons.push(makeReason("filter", "filter.st.excluded", "ST 股票不进入候选池"));
  }
  if ((filters.excludeST || filters.excludeDelistingNames) && /ST|退/i.test(name)) {
    reasons.push(makeReason("filter", "filter.name.risk", "名称包含 ST 或退市风险标记", {
      actual: name,
      expected: "名称不含 ST/退",
    }));
  }

  for (const [field, label] of HARD_FILTER_FIELDS) {
    const range = filters[field];
    if (!range || (!isFiniteNumber(range.min) && !isFiniteNumber(range.max))) continue;
    const value = stock[field];
    if (!isFiniteNumber(value)) {
      reasons.push(makeReason("validation", `validation.${field}.invalid`, `${label}缺失或不是有限数值`, {
        actual: value,
        expected: describeRange(range),
      }));
      continue;
    }
    if (isFiniteNumber(range.min) && value < range.min) {
      reasons.push(makeReason("filter", `filter.${field}.min`, `${label}低于策略下限`, {
        actual: value,
        expected: `>= ${range.min}`,
      }));
    }
    if (isFiniteNumber(range.max) && value > range.max) {
      reasons.push(makeReason("filter", `filter.${field}.max`, `${label}高于策略上限`, {
        actual: value,
        expected: `<= ${range.max}`,
      }));
    }
  }
  return reasons;
}

function describeRange(range) {
  if (isFiniteNumber(range.min) && isFiniteNumber(range.max)) return `${range.min}～${range.max}`;
  if (isFiniteNumber(range.min)) return `>= ${range.min}`;
  if (isFiniteNumber(range.max)) return `<= ${range.max}`;
  return "有限数值";
}

function percentileScores(rows, valueOf, { lowerIsBetter = false, fallback = 50 } = {}) {
  const valid = [];
  rows.forEach((row, index) => {
    const value = valueOf(row);
    if (isFiniteNumber(value)) valid.push({ index, value });
  });
  const result = Array(rows.length).fill(fallback);
  if (valid.length === 0) return result;
  valid.sort((left, right) => {
    const difference = lowerIsBetter
      ? right.value - left.value
      : left.value - right.value;
    return difference || left.index - right.index;
  });
  let start = 0;
  while (start < valid.length) {
    let end = start;
    while (end + 1 < valid.length && valid[end + 1].value === valid[start].value) end += 1;
    const averageRank = ((start + 1) + (end + 1)) / 2;
    const score = averageRank / valid.length * 100;
    for (let position = start; position <= end; position += 1) {
      result[valid[position].index] = score;
    }
    start = end + 1;
  }
  return result;
}

function scoringProfile(strategy) {
  return { ...DEFAULT_SCORING_PROFILE, ...(strategy.scoringProfile ?? {}) };
}

function computeFactorScores(rows, strategy) {
  const profile = scoringProfile(strategy);
  const pePercentiles = percentileScores(
    rows,
    (row) => row.peRatio > 0 && row.peRatio < 500 ? row.peRatio : undefined,
    { lowerIsBetter: true, fallback: 25 },
  );
  const pbPercentiles = percentileScores(
    rows,
    (row) => row.pbRatio > 0 && row.pbRatio < 50 ? row.pbRatio : undefined,
    { lowerIsBetter: true, fallback: 25 },
  );
  const liquidityPercentiles = percentileScores(
    rows,
    (row) => row.amount > 0 ? Math.log10(row.amount) : undefined,
    { fallback: 20 },
  );
  const sizePercentiles = percentileScores(
    rows,
    (row) => row.totalMarketCap > 0 ? Math.log10(row.totalMarketCap) : undefined,
    { fallback: 35 },
  );

  return rows.map((row, index) => {
    let value = 50 * 0.35 + pePercentiles[index] * 0.65;
    value = value * 0.55 + pbPercentiles[index] * 0.45;
    return {
      value: clamp(value),
      stability: stabilityScore(row, profile),
      liquidity: clamp(liquidityPercentiles[index]),
      momentum: momentumScore(row, profile),
      activity: activityScore(row, profile),
      reversal: reversalScore(row, profile),
      size: clamp(sizePercentiles[index]),
    };
  });
}

function momentumScore(stock, profile) {
  let score = 50;
  if (isFiniteNumber(stock.changePct)) {
    const change = stock.changePct;
    let intraday = profile.momentumBase + change * profile.momentumIntradaySlope;
    intraday -= Math.max(change - profile.momentumChaseStartPct, 0)
      * profile.momentumChasePenaltySlope;
    intraday -= Math.max(-change + profile.momentumDownsideStartPct, 0)
      * profile.momentumDownsidePenaltySlope;
    score = score * 0.35 + clamp(intraday, 5, 100) * 0.65;
  }
  if (isFiniteNumber(stock.change60d)) {
    const change = stock.change60d;
    let trend = profile.momentum60dBase + change * profile.momentum60dSlope;
    trend -= Math.max(change - profile.momentum60dOverheatPct, 0)
      * profile.momentum60dOverheatPenaltySlope;
    trend -= Math.max(-change + profile.momentum60dBreakdownPct, 0)
      * profile.momentum60dBreakdownPenaltySlope;
    score = score * 0.6 + clamp(trend, 5, 100) * 0.4;
  }
  if (isFiniteNumber(stock.signalScore)) {
    score = score * 0.7 + clamp(stock.signalScore) * 0.3;
  }
  if (isMacdBullish(stock.macdStatus)) score += profile.macdBullishBonus;
  if (isMacdBearish(stock.macdStatus)) score -= profile.macdBearishPenalty;
  return clamp(score, 5, 100);
}

function reversalScore(stock, profile) {
  if (!isFiniteNumber(stock.changePct)) return 50;
  const change = stock.changePct;
  let score = 100 - Math.abs(change - profile.reversalIdealChangePct)
    * profile.reversalDistancePenaltySlope;
  score -= Math.max(-change + profile.reversalCollapseStartPct, 0)
    * profile.reversalCollapsePenaltySlope;
  score -= Math.max(change - profile.reversalChaseStartPct, 0)
    * profile.reversalChasePenaltySlope;
  if (isRsiOversold(stock.rsiStatus)) score += profile.rsiOversoldBonus;
  if (isRsiOverbought(stock.rsiStatus)) score -= profile.rsiOverboughtPenalty;
  if (isFiniteNumber(stock.change60d)) {
    score -= Math.max(stock.change60d - 35, 0) * 0.5;
    score -= Math.max(-stock.change60d - 35, 0) * 0.8;
  }
  return clamp(score, 5, 100);
}

function activityScore(stock, profile) {
  let score = 50;
  if (isFiniteNumber(stock.volumeRatio)) {
    let volumeScore = 100 - Math.abs(stock.volumeRatio - profile.activityIdealVolumeRatio)
      * profile.activityVolumeRatioDistanceSlope;
    volumeScore -= Math.max(stock.volumeRatio - profile.activityHighVolumeRatio, 0)
      * profile.activityHighVolumeRatioPenaltySlope;
    score = score * 0.45 + clamp(volumeScore, 5, 100) * 0.55;
  }
  if (isFiniteNumber(stock.turnoverRate)) {
    let turnoverScore = 100 - Math.abs(stock.turnoverRate - profile.activityIdealTurnoverRate)
      * profile.activityTurnoverDistanceSlope;
    turnoverScore -= Math.max(stock.turnoverRate - profile.activityHighTurnoverRate, 0)
      * profile.activityHighTurnoverPenaltySlope;
    if (stock.turnoverRate <= 0) turnoverScore = 40;
    score = score * 0.55 + clamp(turnoverScore, 5, 100) * 0.45;
  }
  return clamp(score);
}

function stabilityScore(stock, profile) {
  let score = profile.stabilityBase;
  if (isFiniteNumber(stock.changePct)) {
    score -= Math.min(Math.abs(stock.changePct), 10) * profile.stabilityChangeAbsPenaltySlope;
    score -= Math.max(stock.changePct - profile.stabilityHotChangePct, 0)
      * profile.stabilityHotChangePenaltySlope;
  }
  if (isFiniteNumber(stock.turnoverRate)) {
    score -= Math.max(stock.turnoverRate - profile.stabilityHighTurnoverRate, 0)
      * profile.stabilityHighTurnoverPenaltySlope;
  }
  if (isFiniteNumber(stock.volumeRatio)) {
    score -= Math.max(stock.volumeRatio - profile.stabilityHighVolumeRatio, 0)
      * profile.stabilityHighVolumeRatioPenaltySlope;
  }
  if (isFiniteNumber(stock.peRatio) && stock.peRatio <= 0) {
    score -= profile.stabilityInvalidPePenalty;
  }
  if (isFiniteNumber(stock.signalScore)) score += (clamp(stock.signalScore) - 50) * 0.12;
  if (isFiniteNumber(stock.volatility20dPct)) {
    score -= Math.max(stock.volatility20dPct - profile.stabilityHighVolatilityPct, 0)
      * profile.stabilityHighVolatilityPenaltySlope;
  }
  if (isFiniteNumber(stock.maxDrawdown20dPct)) {
    score -= Math.max(profile.stabilityMaxDrawdownFloorPct - stock.maxDrawdown20dPct, 0)
      * profile.stabilityDrawdownPenaltySlope;
  }
  if (isFiniteNumber(stock.atr20Pct)) {
    score -= Math.max(stock.atr20Pct - profile.stabilityHighAtrPct, 0)
      * profile.stabilityHighAtrPenaltySlope;
  }
  if (isFiniteNumber(stock.dailyQualityScore)) {
    score -= Math.max(profile.stabilityLowDailyQualityScore - stock.dailyQualityScore, 0)
      * profile.stabilityLowDailyQualityPenaltySlope;
  }
  const flags = normalizedFlagSet(stock.dailyQualityFlags);
  if (["invalid_ohlc", "non_positive_price", "negative_volume", "stale_cache"]
    .some((flag) => flags.has(flag))) {
    score -= profile.stabilityBadDailyQualityFlagPenalty;
  }
  return clamp(score);
}

function riskProfile(strategy) {
  return { ...DEFAULT_RISK_PROFILE, ...(strategy.risk ?? {}) };
}

function assessRisk(stock, strategy = DUAL_LOW_STRATEGY) {
  const resolved = resolveStrategy(strategy);
  const profile = riskProfile(resolved);
  const riskFlags = [];
  let riskPoints = 0;
  const add = (code, message, points) => {
    if (!isFiniteNumber(points) || points <= 0) return;
    riskPoints += points;
    riskFlags.push(makeReason("risk", code, message, { impact: round4(points) }));
  };

  if (isFiniteNumber(stock?.changePct) && stock.changePct >= profile.chaseChangePct) {
    add("risk.single_day_chase", "单日涨幅达到追高风险阈值", profile.chasePoints);
  } else if (isFiniteNumber(stock?.changePct) && stock.changePct <= profile.breakdownChangePct) {
    add("risk.single_day_breakdown", "单日跌幅达到破位风险阈值", profile.breakdownPoints);
  }
  if (isFiniteNumber(stock?.volumeRatio) && stock.volumeRatio >= profile.abnormalVolumeRatio) {
    add("risk.abnormal_volume_ratio", "量比异常偏高", profile.abnormalVolumeRatioPoints);
  }
  if (isFiniteNumber(stock?.turnoverRate) && stock.turnoverRate >= profile.highTurnoverRate) {
    add("risk.high_turnover", "换手率异常偏高", profile.highTurnoverPoints);
  }
  if (isFiniteNumber(stock?.peRatio) && stock.peRatio <= 0) {
    add("risk.invalid_pe", "PE 非正或口径无效", profile.invalidPePoints);
  }
  if (isFiniteNumber(stock?.pbRatio) && stock.pbRatio >= profile.highPb) {
    add("risk.high_pb", "PB 达到高估值风险阈值", profile.highPbPoints);
  }
  if (isFiniteNumber(stock?.signalScore) && stock.signalScore < profile.weakSignalScore) {
    add("risk.weak_signal", "日线技术信号偏弱", profile.weakSignalPoints);
  }
  if (isMacdBearish(stock?.macdStatus)) {
    add("risk.macd_bearish", "MACD 处于空头状态", profile.macdBearishPoints);
  }
  if (isRsiOverbought(stock?.rsiStatus)) {
    add("risk.rsi_overbought", "RSI 处于过热状态", profile.rsiOverboughtPoints);
  }
  if (isFiniteNumber(stock?.externalConfidence)) {
    const confidence = stock.externalConfidence > 1
      ? stock.externalConfidence / 100
      : stock.externalConfidence;
    if (confidence < profile.lowExternalConfidence) {
      add("risk.low_external_confidence", "外部分数置信度偏低", profile.lowExternalConfidencePoints);
    }
  }

  const dailyFlags = normalizedFlagSet(stock?.dailyQualityFlags);
  if (isFiniteNumber(stock?.dailyQualityScore)
    && stock.dailyQualityScore < profile.lowDailyQualityScore) {
    add("risk.low_daily_quality", "日线数据质量偏低", profile.lowDailyQualityPoints);
  }
  if (dailyFlags.has("fetch_failed")) {
    add("risk.daily_fetch_failed", "日线数据获取失败", profile.fetchFailedDailyPoints);
  }
  if (dailyFlags.has("stale_cache")) {
    add("risk.daily_stale_cache", "日线数据来自陈旧缓存", profile.staleDailyCachePoints);
  }
  if (dailyFlags.has("fallback_errors")) {
    add("risk.daily_fallback_errors", "日线数据源发生降级错误", profile.fallbackDailyErrorsPoints);
  }
  if (["invalid_ohlc", "non_positive_price", "negative_volume"].some((flag) => dailyFlags.has(flag))) {
    add("risk.bad_daily_quality_flags", "日线数据包含严重质量标记", profile.badDailyQualityFlagPoints);
  }

  const externalTags = cleanTagList(stock?.externalRiskTags);
  if (externalTags.length) {
    const points = Math.min(externalTags.length * profile.externalRiskPoints, profile.externalRiskPointsCap);
    add("risk.external_tags", `外部风险标签：${externalTags.join("、")}`, points);
  }
  const deepTags = cleanTagList(stock?.deepRiskTags);
  if (deepTags.length) {
    const points = Math.min(deepTags.length * profile.deepRiskPoints, profile.deepRiskPointsCap);
    add("risk.deep_tags", `深度分析风险标签：${deepTags.join("、")}`, points);
  }

  const maxPenalty = Math.max(isFiniteNumber(profile.maxPenalty) ? profile.maxPenalty : 12, 0);
  const riskPenalty = Math.min(riskPoints, maxPenalty);
  const riskLevel = maxPenalty <= 0 || riskPoints < maxPenalty * 0.33
    ? "low"
    : riskPoints < maxPenalty * 0.66
      ? "medium"
      : "high";
  return {
    riskPoints: round4(riskPoints),
    riskPenalty: round4(riskPenalty),
    riskLevel,
    riskFlags,
  };
}

function normalizedFlagSet(value) {
  if (Array.isArray(value)) return new Set(value.map((item) => String(item).trim()).filter(Boolean));
  if (typeof value !== "string") return new Set();
  return new Set(value.split(/[;,，|\s]+/).map((item) => item.trim()).filter(Boolean));
}

function cleanTagList(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => String(item).trim()).filter(Boolean))];
}

function blendExternalScore(baseScore, externalScore, weights = {}) {
  if (!isFiniteNumber(baseScore) || !isFiniteNumber(externalScore)) {
    throw new TypeError("baseScore 和 externalScore 必须是有限数值");
  }
  const base = weights.base ?? 0.6;
  const external = weights.external ?? 0.4;
  if (!isFiniteNumber(base) || !isFiniteNumber(external) || base < 0 || external < 0) {
    throw new TypeError("融合权重必须是非负有限数值");
  }
  const total = base + external;
  if (total <= 0) throw new TypeError("融合权重总和必须大于 0");
  return round4(clamp(clamp(baseScore) * (base / total) + clamp(externalScore) * (external / total)));
}

function scoreUniverse(stocks, options = {}) {
  if (!Array.isArray(stocks)) throw new TypeError("stocks 必须是股票快照数组");
  const strategy = resolveStrategy(options.strategy ?? DUAL_LOW_STRATEGY);
  const rejected = [];
  const eligible = [];
  for (const input of stocks) {
    const stock = cloneStock(input ?? {});
    const filterReasons = filterStock(stock, strategy);
    if (filterReasons.length) {
      rejected.push({ ...stock, eligible: false, filterReasons });
    } else {
      eligible.push(stock);
    }
  }

  const weights = normalizedWeights(strategy);
  const factorRows = computeFactorScores(eligible, strategy);
  const externalWeight = isFiniteNumber(options.externalWeight)
    ? clamp(options.externalWeight, 0, 1)
    : 0.4;
  const vetoHighRisk = options.vetoHighRisk ?? strategy.risk?.vetoHighRisk ?? false;
  const scored = [];

  eligible.forEach((stock, index) => {
    const factorScores = Object.fromEntries(
      FACTOR_NAMES.map((factor) => [factor, round4(factorRows[index][factor])]),
    );
    const contributions = Object.fromEntries(
      FACTOR_NAMES.map((factor) => [factor, round4(factorRows[index][factor] * weights[factor])]),
    );
    const baseScore = round4(Object.values(contributions).reduce((sum, value) => sum + value, 0));
    const blendedScore = isFiniteNumber(stock.externalScore)
      ? blendExternalScore(baseScore, stock.externalScore, {
          base: 1 - externalWeight,
          external: externalWeight,
        })
      : baseScore;
    const risk = assessRisk(stock, strategy);
    const explanations = strongestFactorExplanations(factorScores, contributions);
    if (vetoHighRisk && risk.riskLevel === "high") {
      rejected.push({
        ...stock,
        eligible: false,
        filterReasons: [makeReason("risk", "risk.veto.high", "高风险候选已被策略否决")],
        ...risk,
      });
      return;
    }
    scored.push({
      ...stock,
      eligible: true,
      filterReasons: [],
      factorScores,
      contributions,
      baseScore,
      blendedScore,
      ...risk,
      portfolioPenalty: 0,
      finalScore: round4(clamp(blendedScore - risk.riskPenalty)),
      rank: 0,
      explanations,
    });
  });

  scored.sort(compareScoredStocks);
  if (options.applyPortfolioPenalty !== false && strategy.portfolioPenalty?.enabled !== false) {
    applyPortfolioPenalties(scored, strategy.portfolioPenalty ?? {});
    scored.sort(compareScoredStocks);
  }
  scored.forEach((stock, index) => { stock.rank = index + 1; });

  const requestedMax = options.maxOutput ?? strategy.maxOutput ?? scored.length;
  const maxOutput = Number.isFinite(Number(requestedMax))
    ? Math.max(0, Math.floor(Number(requestedMax)))
    : scored.length;
  return {
    modelId: MODEL_ID,
    strategy: { id: strategy.id, version: strategy.version },
    inputCount: stocks.length,
    eligibleCount: scored.length,
    rejectedCount: rejected.length,
    ranked: scored.slice(0, maxOutput),
    rejected,
  };
}

function strongestFactorExplanations(factorScores, contributions) {
  return Object.entries(contributions)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, 3)
    .map(([factor, contribution]) => `${factor}: ${factorScores[factor].toFixed(1)} × 权重贡献 ${contribution.toFixed(1)}`);
}

function compareScoredStocks(left, right) {
  return right.finalScore - left.finalScore
    || right.baseScore - left.baseScore
    || String(left.code).localeCompare(String(right.code));
}

function applyPortfolioPenalties(stocks, config) {
  const freeSlots = Math.max(1, Math.floor(Number(config.freeSlotsPerBucket ?? 2)));
  const step = Math.max(0, Number(config.step ?? 3));
  const maxPenalty = Math.max(0, Number(config.maxPenalty ?? step * 3));
  const counts = new Map();
  for (const stock of stocks) {
    const bucket = portfolioBucket(stock, config.buckets ?? {});
    if (!bucket) continue;
    const count = (counts.get(bucket) ?? 0) + 1;
    counts.set(bucket, count);
    const excess = count - freeSlots;
    if (excess <= 0) continue;
    const penalty = Math.min(step * excess, maxPenalty);
    stock.portfolioPenalty = round4(penalty);
    stock.finalScore = round4(clamp(stock.finalScore - penalty));
    stock.explanations.push(`portfolio: ${bucket} 集中度扣分 ${penalty.toFixed(1)}`);
    stock.riskFlags = [
      ...stock.riskFlags,
      makeReason("risk", `risk.portfolio.${bucket}`, `${bucket}候选集中度偏高`, { impact: penalty }),
    ];
  }
}

function portfolioBucket(stock, buckets) {
  const text = `${stock.industry ?? ""} ${stock.theme ?? ""}`.trim();
  if (!text) return "";
  for (const [bucket, keywords] of Object.entries(buckets)) {
    const list = Array.isArray(keywords) ? keywords : [keywords];
    if (list.some((keyword) => String(keyword).trim() && text.includes(String(keyword).trim()))) {
      return bucket;
    }
  }
  return String(stock.industry ?? stock.theme ?? "").trim();
}

export {
  MODEL_ID,
  DUAL_LOW_STRATEGY,
  scoreUniverse,
  filterStock,
  assessRisk,
  blendExternalScore,
};

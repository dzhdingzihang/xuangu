#!/usr/bin/env node

import fs from "node:fs";

import {
  DUAL_LOW_STRATEGY,
  MODEL_ID,
  scoreUniverse,
} from "../vendor/stock-scoring-kit/index.js";


const raw = fs.readFileSync(0, "utf8");
const payload = raw.trim() ? JSON.parse(raw) : {};
if (!Array.isArray(payload.stocks)) {
  throw new TypeError("payload.stocks must be an array");
}

const result = scoreUniverse(payload.stocks, {
  strategy: DUAL_LOW_STRATEGY,
  maxOutput: payload.stocks.length,
  externalWeight: 0,
  vetoHighRisk: false,
  applyPortfolioPenalty: false,
});

process.stdout.write(JSON.stringify({
  packageVersion: "1.0.0",
  modelId: MODEL_ID,
  portfolioPenaltyEnabled: false,
  ...result,
}));

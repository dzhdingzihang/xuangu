const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const MODEL_VERSION = "smart-selector-2026-06-04.3-serenity-skill";

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: JSON_HEADERS,
  });
}

function nowCN() {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Shanghai",
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
    const range = primary.estimated_2w_range || primary.estimated_2d_range;
    summary.code = primary.code;
    summary.name = primary.name;
    summary.confidence = primary.recommendation_degree || primary.confidence;
    summary.recommendation_degree = primary.recommendation_degree || primary.confidence;
    summary.estimated_2w_range = range && range.text;
    summary.estimated_2d_range = range && range.text;
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

function summarizePick(pick) {
  const summary = {
    target_date: pick.target_date,
    signal_date: pick.signal_date,
    generated_at: pick.generated_at,
    generated_label: pick.generated_label,
    snapshot_key: pick.snapshot_key,
    forecast_end_date: pick.forecast_end_date,
    forecast_horizon: pick.forecast_horizon,
    model_version: pick.model_version,
    ...summarizeDecision(pick.decision || {}),
  };
  if (pick.markets) {
    summary.markets = Object.fromEntries(
      Object.entries(pick.markets).map(([key, section]) => [key, summarizeDecision((section && section.decision) || {})]),
    );
  }
  return summary;
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
  return manifest && typeof manifest === "object" ? manifest : { files: [], summaries: [] };
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
  const response = await fetch(target, {
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
  const response = await fetch(`https://qt.gtimg.cn/q=${symbol}`, {
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
    source: "Tencent realtime quote",
  };
}

async function tencentAKline(code, limit = 70) {
  const symbol = `${marketPrefix(code)}${String(code || "").replace(/\D/g, "")}`;
  const target = new URL("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get");
  target.searchParams.set("param", `${symbol},day,,,${limit},qfq`);
  const response = await fetch(target, {
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
  try {
    const [quotePayload, rows] = await Promise.all([
      eastmoneyJson("https://push2.eastmoney.com/api/qt/stock/get", {
        secid: eastmoneySecid(code),
        fields: "f43,f44,f45,f46,f47,f48,f57,f58,f60,f168,f170",
        fltt: "2",
      }),
      aShareKline(code),
    ]);
    data = quotePayload.data || {};
    kline = rows;
  } catch {
    const [quote, rows] = await Promise.all([tencentAQuote(code), tencentAKline(code)]);
    data = {
      f43: quote.price,
      f47: quote.volume,
      f57: quote.code,
      f58: quote.name,
      f170: quote.change_pct,
    };
    kline = rows;
    source = quote.source;
  }
  const latest = kline[kline.length - 1] || {};
  const price = num(data.f43) || num(latest.close);
  return {
    ok: true,
    market: "a_share",
    code: String(data.f57 || code),
    name: data.f58 || "",
    price,
    current_price: price,
    realtime_price: price,
    change_pct: num(data.f170) || num(latest.change_pct),
    current_change_pct: num(data.f170) || num(latest.change_pct),
    volume: num(data.f47) || num(latest.volume),
    session_label: "实时/延时",
    source,
    updated_at: nowCN(),
    kline,
  };
}

async function yahooLive(symbol, market) {
  const target = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=3mo&interval=1d&includePrePost=true&events=div%2Csplits`;
  const response = await fetch(target, { headers: { "user-agent": "Mozilla/5.0" } });
  if (!response.ok) throw new Error(`Yahoo ${response.status}`);
  const payload = await response.json();
  const result = (((payload.chart || {}).result || [])[0]) || {};
  const meta = result.meta || {};
  const quote = (((result.indicators || {}).quote || [])[0]) || {};
  const timestamps = result.timestamp || [];
  const rows = timestamps
    .map((ts, index) => ({
      date: new Date(ts * 1000).toISOString().slice(0, 10),
      open: num((quote.open || [])[index]),
      high: num((quote.high || [])[index]),
      low: num((quote.low || [])[index]),
      close: num((quote.close || [])[index]),
      volume: num((quote.volume || [])[index]),
    }))
    .filter((row) => row.close > 0 && row.high > 0 && row.low > 0);
  const price = num(meta.regularMarketPrice) || num((rows.at(-1) || {}).close);
  const previous = num(meta.previousClose) || num(meta.regularMarketPreviousClose) || num((rows.at(-2) || {}).close) || num(meta.chartPreviousClose);
  const changePct = previous ? ((price - previous) / previous) * 100 : 0;
  return {
    ok: true,
    market,
    code: symbol,
    name: meta.shortName || meta.longName || "",
    price,
    current_price: price,
    realtime_price: price,
    change_pct: changePct,
    current_change_pct: changePct,
    volume: num(meta.regularMarketVolume) || num((rows.at(-1) || {}).volume),
    session_label: meta.marketState || "实时/延时",
    source: "Yahoo chart quote",
    updated_at: nowCN(),
    kline: rows,
  };
}

async function liveStock(market, code) {
  if (!code) return null;
  if (market === "a_share") return aShareLive(code);
  return yahooLive(code, market === "hk" ? "hk" : "us");
}

async function handleApi(request, env) {
  const url = new URL(request.url);
  if (url.pathname === "/api/status") {
    const latest = await latestPick(env);
    return json({
      ok: true,
      time: nowCN(),
      platform: "cloudflare-workers",
      has_latest: Boolean(latest),
      latest_path: latest ? "/data/picks/latest.json" : null,
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
    const limit = Math.max(1, Math.min(Number(url.searchParams.get("limit") || 120), 240));
    const manifest = await loadManifest(env);
    const rows = Array.isArray(manifest.summaries) ? [...manifest.summaries] : [];
    rows.sort((a, b) =>
      `${b.target_date || ""}${b.generated_at || ""}`.localeCompare(`${a.target_date || ""}${a.generated_at || ""}`),
    );
    const latest = await latestPick(env);
    return json({
      ok: true,
      time: nowCN(),
      latest: latest ? summarizePick(latest) : null,
      history: rows.slice(0, limit),
    });
  }

  if (url.pathname === "/api/pick") {
    const snapshotKey = url.searchParams.get("snapshot");
    if (snapshotKey) {
      const snapshot = await loadPickBySnapshot(env, snapshotKey);
      if (!snapshot) return json({ error: "未找到指定历史快照" }, 404);
      return json(snapshot);
    }
    const targetDate = url.searchParams.get("date");
    const pick = targetDate ? await pickForTarget(env, targetDate) : await latestPick(env);
    const fallback = pick || (await latestPick(env));
    if (!fallback) {
      return json({ error: "暂无选股快照。请等待每日任务生成后再查看。" }, 404);
    }
    return json(fallback);
  }

  if (url.pathname === "/api/live") {
    const market = url.searchParams.get("market") || "a_share";
    const code = url.searchParams.get("code") || "";
    try {
      const payload = await liveStock(market, code);
      if (!payload) return json({ error: "缺少股票代码" }, 400);
      return json(payload);
    } catch (error) {
      return json({ error: "实时行情暂不可用", detail: String(error && error.message ? error.message : error) }, 502);
    }
  }

  return json({ error: "Not found" }, 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) {
      return handleApi(request, env);
    }
    return env.ASSETS.fetch(request);
  },
};

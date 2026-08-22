from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import tempfile
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER_URI = (ROOT / "src" / "index.js").as_uri()
BUILD_SCRIPT = ROOT / "scripts" / "build_worker_assets.py"


def load_build_module():
    spec = importlib.util.spec_from_file_location("build_worker_assets_under_test", BUILD_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load build_worker_assets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_node(script: str) -> None:
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Node contract check failed ({completed.returncode})\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


class WorkerApiContractTests(unittest.TestCase):
    def test_worker_prefers_authenticated_futu_gateway_and_labels_public_fallback(self) -> None:
        source = (ROOT / "src" / "index.js").read_text(encoding="utf-8")
        for token in (
            "REALTIME_GATEWAY_URL",
            "QUOTE_GATEWAY_TOKEN",
            "FUTU_OPEND",
            "LICENSED_REALTIME",
            "PUBLIC_BEST_EFFORT",
            "public_best_effort_1m",
            "realtime_guaranteed",
            "LIVE_RATE_LIMITER",
            "RATE_LIMITED",
            "PICK_NOT_FOUND",
            "INVALID_DATE",
        ):
            self.assertIn(token, source)

    def test_status_force_https_and_security_contract(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)})).default;
            const latest = {{
              schema_version: "selector-snapshot-v2",
              selector_mode: "legacy_active_v2_shadow",
              model_version: "model-test-2",
              weights_version: "weights-test-2",
              universe_version: "universe-test-2",
              generated_at: "2026-08-19T22:06:29+08:00",
            }};
            const env = {{
              ASSETS: {{
                async fetch(input) {{
                  const url = new URL(typeof input === "string" ? input : input.url);
                  if (url.pathname === "/data/picks/latest.json") {{
                    return new Response(JSON.stringify(latest), {{
                      headers: {{ "content-type": "application/json" }},
                    }});
                  }}
                  return new Response("<!doctype html><title>selector</title>", {{
                    headers: {{ "content-type": "text/html" }},
                  }});
                }},
              }},
            }};

            const statusResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/status"),
              env,
            );
            assert.equal(statusResponse.status, 200);
            const status = await statusResponse.json();
            assert.equal(status.platform, "cloudflare-workers");
            assert.equal(status.snapshot_generation, "github-actions");
            assert.equal(status.recompute_supported, false);
            assert.equal(status.schema_version, latest.schema_version);
            assert.equal(status.model_version, latest.model_version);
            assert.equal(status.generated_at, latest.generated_at);
            assert.equal(statusResponse.headers.get("x-content-type-options"), "nosniff");
            assert.match(statusResponse.headers.get("strict-transport-security"), /max-age=/);
            assert.match(statusResponse.headers.get("permissions-policy"), /camera=\(\)/);

            const forceResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/pick?force=1"),
              env,
            );
            assert.equal(forceResponse.status, 409);
            const force = await forceResponse.json();
            assert.equal(force.error, "RECOMPUTE_NOT_SUPPORTED");
            assert.equal(force.recompute_supported, false);

            const redirect = await worker.fetch(
              new Request("http://xuangu.alixjd.com/api/status"),
              env,
            );
            assert.equal(redirect.status, 308);
            assert.equal(redirect.headers.get("location"), "https://xuangu.alixjd.com/api/status");

            const localResponse = await worker.fetch(
              new Request("http://xuangu.alixjd.com/api/status"),
              {{ ...env, LOCAL_DEV: "1" }},
            );
            assert.equal(localResponse.status, 200);

            const page = await worker.fetch(new Request("https://xuangu.alixjd.com/"), env);
            assert.equal(page.status, 200);
            assert.equal(page.headers.get("referrer-policy"), "strict-origin-when-cross-origin");
            """
        )

    def test_live_quotes_declare_source_time_fetch_time_and_volume_unit(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?live-contract")).default;
            const latest = {{
              markets: {{
                a_share: {{ decision: {{ watchlist: [{{ code: "603228" }}] }} }},
                hk: {{ decision: {{ watchlist: [{{ code: "0700.HK" }}] }} }},
                us: {{ decision: {{ watchlist: [{{ code: "AAPL" }}] }} }},
              }},
            }};
            const jsonResponse = (payload) => new Response(JSON.stringify(payload), {{
              status: 200,
              headers: {{ "content-type": "application/json" }},
            }});
            globalThis.fetch = async (input) => {{
              const target = input instanceof URL ? input : (typeof input === "string" ? input : input.url);
              const url = new URL(target);
              if (url.hostname === "push2.eastmoney.com") {{
                return jsonResponse({{ data: {{
                  f43: 12.34, f47: 1234, f57: "603228", f58: "测试A股",
                  f86: 1787148000, f170: 1.8,
                }} }});
              }}
              if (url.hostname === "push2his.eastmoney.com") {{
                return jsonResponse({{ data: {{ klines: [
                  "2026-08-19,12.00,12.34,12.50,11.90,1234,1500000,0,1.8,0,2.1"
                ] }} }});
              }}
              if (url.hostname === "query1.finance.yahoo.com") {{
                return jsonResponse({{ chart: {{ result: [{{
                  meta: {{
                    regularMarketPrice: 210,
                    chartPreviousClose: 205,
                    regularMarketVolume: 120000,
                    regularMarketTime: 1787148000,
                    currentTradingPeriod: {{
                      pre: {{ start: 1787112000, end: 1787131800 }},
                      regular: {{ start: 1787131800, end: 1787148000 }},
                      post: {{ start: 1787148000, end: 1787162400 }},
                    }},
                  }},
                  timestamp: [1787148000, 1787162340],
                  indicators: {{ quote: [{{
                    open: [206, 211], high: [212, 214], low: [204, 210], close: [210, 213], volume: [120000, 800],
                  }}] }},
                }}] }} }});
              }}
              throw new Error(`Unexpected URL: ${{url}}`);
            }};
            const env = {{ ASSETS: {{ fetch: async (input) => {{
              const url = new URL(typeof input === "string" ? input : input.url);
              if (url.pathname === "/data/picks/latest.json") return jsonResponse(latest);
              return new Response("missing", {{ status: 404 }});
            }} }} }};

            const aResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=a_share&code=603228"),
              env,
            );
            assert.equal(aResponse.status, 200);
            const aShare = await aResponse.json();
            assert.equal(aShare.volume, 1234);
            assert.equal(aShare.volume_unit, "lot");
            assert.equal(aShare.contract_version, "live-quote-v1");
            assert.ok(aShare.source_as_of);
            assert.match(aShare.fetched_at, /\+08:00$/);
            assert.equal(aShare.provider, "eastmoney");
            assert.ok(["REALTIME", "DELAYED", "LAST_CLOSE"].includes(aShare.quote_status));
            assert.ok(["fresh", "stale", "last_close"].includes(aShare.freshness));
            assert.equal(typeof aShare.latency_seconds, "number");
            assert.ok(aShare.session);

            const usResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              env,
            );
            assert.equal(usResponse.status, 200);
            const us = await usResponse.json();
            assert.equal(us.volume, 120000);
            assert.equal(us.volume_unit, "share");
            assert.ok(us.source_as_of);
            assert.match(us.fetched_at, /\+08:00$/);
            assert.equal(us.price, 213);
            assert.equal(us.provider, "yahoo_finance");
            assert.equal(us.price_kind, "after_hours");
            assert.match(us.source, /1m includePrePost/);

            const hkResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=hk&code=0700.HK"),
              env,
            );
            assert.equal(hkResponse.status, 200);
            const hk = await hkResponse.json();
            assert.equal(hk.market, "hk");
            assert.equal(hk.volume_unit, "share");
            assert.equal(hk.price, 213);
            assert.equal(hk.source_as_of, us.source_as_of);
            """
        )

    def test_live_api_validates_market_code_whitelist_and_uses_ten_second_cache(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?live-validation-cache")).default;
            const latest = {{
              markets: {{
                a_share: {{ decision: {{ watchlist: [{{ code: "603228" }}] }} }},
                hk: {{ decision: {{ watchlist: [{{ code: "0700.HK" }}] }} }},
                us: {{ decision: {{ watchlist: [{{ code: "AAPL" }}] }} }},
              }},
            }};
            const jsonResponse = (payload) => new Response(JSON.stringify(payload), {{
              status: 200,
              headers: {{ "content-type": "application/json" }},
            }});
            let upstreamCalls = 0;
            globalThis.fetch = async (input) => {{
              upstreamCalls += 1;
              const timestamp = Math.floor(Date.now() / 1000) - 20;
              return jsonResponse({{ chart: {{ result: [{{
                meta: {{
                  chartPreviousClose: 205,
                  regularMarketVolume: 120000,
                  marketState: "REGULAR",
                }},
                timestamp: [timestamp],
                indicators: {{ quote: [{{ close: [210], volume: [120000] }}] }},
              }}] }} }});
            }};
            const env = {{ ASSETS: {{ fetch: async (input) => {{
              const url = new URL(typeof input === "string" ? input : input.url);
              if (url.pathname === "/data/picks/latest.json") return jsonResponse(latest);
              return new Response("missing", {{ status: 404 }});
            }} }} }};

            const invalidMarket = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=crypto&code=AAPL"), env,
            );
            assert.equal(invalidMarket.status, 400);
            const invalidMarketPayload = await invalidMarket.json();
            assert.equal(invalidMarketPayload.error, "INVALID_MARKET");
            assert.equal(invalidMarketPayload.contract_version, "live-quote-v1");
            for (const field of ["provider", "session", "session_label", "latency_seconds", "quote_status", "fetched_at"]) {{
              assert.ok(Object.hasOwn(invalidMarketPayload, field), `missing unified error field: ${{field}}`);
            }}

            const invalidCode = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=../AAPL"), env,
            );
            assert.equal(invalidCode.status, 400);
            assert.equal((await invalidCode.json()).error, "INVALID_CODE");

            const outsideSnapshot = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=MSFT"), env,
            );
            assert.equal(outsideSnapshot.status, 404);
            assert.equal((await outsideSnapshot.json()).error, "LIVE_CODE_NOT_IN_CURRENT_SNAPSHOT");

            const first = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=aapl"), env,
            );
            const second = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"), env,
            );
            assert.equal(first.status, 200);
            assert.equal(second.status, 200);
            assert.equal(upstreamCalls, 1);
            const firstPayload = await first.json();
            const secondPayload = await second.json();
            assert.equal(firstPayload.code, "AAPL");
            assert.equal(secondPayload.source_as_of, firstPayload.source_as_of);
            assert.equal(firstPayload.cache_ttl_seconds, 10);
            """
        )

    def test_history_consolidates_daily_runs_and_reports_truthful_meta(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?history-contract")).default;
            const legacyOld = {{
              target_date: "2026-08-20",
              signal_date: "2026-08-19",
              generated_at: "2026-08-20T10:00:00+08:00",
              snapshot_key: "legacy-old.json",
              history_kind: "legacy_snapshot",
              decision_scope: "legacy_market_rules",
              action: "LEGACY_ONLY",
              global_decision: null,
            }};
            const legacyLatest = {{
              ...legacyOld,
              generated_at: "2026-08-20T15:00:00+08:00",
              snapshot_key: "legacy-latest.json",
            }};
            const contractNoPick = {{
              target_date: "2026-08-21",
              signal_date: "2026-08-20",
              generated_at: "2026-08-21T15:30:00+08:00",
              snapshot_key: "contract-no-pick.json",
              history_kind: "global_10d_v1",
              decision_scope: "global_10d",
              action: "NO_VALID_PICK",
              global_decision: {{
                contract_version: "global-10d-v1",
                decision_scope: "global_10d",
                action_basis: "strict_cross_market_gate_v1",
                action: "NO_VALID_PICK",
                primary: null,
              }},
            }};
            const laterLegacySameDay = {{
              ...legacyLatest,
              target_date: "2026-08-21",
              generated_at: "2026-08-21T22:00:00+08:00",
              snapshot_key: "legacy-after-contract.json",
            }};
            const manifest = {{ summaries: [legacyOld, contractNoPick, legacyLatest, laterLegacySameDay] }};
            const env = {{
              ASSETS: {{
                async fetch(input) {{
                  const url = new URL(typeof input === "string" ? input : input.url);
                  if (url.pathname === "/data/picks/manifest.json") {{
                    return new Response(JSON.stringify(manifest));
                  }}
                  if (url.pathname === "/data/picks/latest.json") {{
                    return new Response(JSON.stringify(contractNoPick));
                  }}
                  return new Response("missing", {{ status: 404 }});
                }},
              }},
            }};

            const response = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/history?limit=120"),
              env,
            );
            assert.equal(response.status, 200);
            const payload = await response.json();
            assert.equal(payload.history.length, 2);
            assert.equal(payload.history[0].snapshot_key, "contract-no-pick.json");
            assert.equal(payload.history[1].snapshot_key, "legacy-latest.json");
            assert.equal(payload.meta.view, "daily");
            assert.equal(payload.meta.raw_run_count, 4);
            assert.equal(payload.meta.decision_day_count, 2);
            assert.equal(payload.meta.duplicate_run_count, 2);
            assert.equal(payload.meta.global_contract_day_count, 1);
            assert.equal(payload.meta.legacy_day_count, 1);
            assert.equal(payload.meta.no_valid_pick_day_count, 1);
            assert.equal(payload.meta.executable_prediction_count, 0);
            assert.equal(payload.meta.settled_sample_count, 0);

            const rawResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/history?view=raw&limit=2"),
              env,
            );
            const rawPayload = await rawResponse.json();
            assert.equal(rawPayload.history.length, 2);
            assert.equal(rawPayload.meta.view, "raw");
            assert.equal(rawPayload.meta.raw_run_count, 4);
            assert.equal(rawPayload.meta.returned_count, 2);
            assert.equal(rawPayload.meta.has_more, true);

            const invalidSettlement = {{
              target_date: "2026-08-22",
              signal_date: "2026-08-21",
              generated_at: "2026-08-22T15:30:00+08:00",
              forecast_end_date: "2026-09-04",
              snapshot_key: "invalid-settlement.json",
              history_kind: "global_10d_v1",
              decision_scope: "global_10d",
              action: "REVIEW_EXECUTABLE_PICK",
              global_decision: {{
                contract_version: "global-10d-v1",
                decision_scope: "global_10d",
                action_basis: "strict_cross_market_gate_v1",
                action: "REVIEW_EXECUTABLE_PICK",
                primary: {{ prediction_id: "prediction-1", model_id: "model-1", label_version: "label-v1" }},
              }},
              outcome: {{
                status: "SETTLED",
                prediction_id: "prediction-1",
                model_id: "model-1",
                label_version: "label-v1",
                entry_at: "2026-08-22T16:00:00+08:00",
                entry_price: 100,
                entry_source: "exchange_open_v1",
                exit_at: "2026-09-04T15:00:00+08:00",
                exit_price: 108,
                exit_source: "exchange_close_v1",
                gross_total_return: 0.082,
                net_total_return: null,
                transaction_cost: 0.002,
                corporate_action_adjusted: true,
                calendar_id: "XSHG-v1",
                currency: "CNY",
                fx_rate_source: "same_currency",
                positive_label: true,
                settled_at: "2026-09-05T16:00:00+08:00",
              }},
            }};
            const laterNoPickSameDay = {{
              ...contractNoPick,
              target_date: "2026-08-22",
              generated_at: "2026-08-22T22:00:00+08:00",
              snapshot_key: "later-no-pick.json",
            }};
            manifest.summaries = [invalidSettlement, laterNoPickSameDay];
            const invalidResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/history?limit=120"),
              env,
            );
            const invalidPayload = await invalidResponse.json();
            assert.equal(invalidPayload.meta.executable_prediction_count, 1);
            assert.equal(invalidPayload.meta.settled_sample_count, 0);
            assert.equal(invalidPayload.meta.missing_outcome_count, 1);
            invalidSettlement.outcome.net_total_return = 0.08;
            invalidSettlement.outcome.exit_at = "2026-09-03T18:00:00Z";
            invalidSettlement.outcome.settled_at = "2026-09-03T19:00:00Z";
            const validResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/history?limit=120"),
              env,
            );
            const validPayload = await validResponse.json();
            assert.equal(validPayload.meta.settled_sample_count, 1);
            assert.equal(validPayload.meta.missing_outcome_count, 0);

            const unavailableResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/history?limit=120"),
              {{ ASSETS: {{ fetch: async () => new Response("missing", {{ status: 404 }}) }} }},
            );
            assert.equal(unavailableResponse.status, 503);
            assert.equal((await unavailableResponse.json()).error, "HISTORY_MANIFEST_UNAVAILABLE");
            """
        )


class WorkerAssetBuildTests(unittest.TestCase):
    def test_manifest_does_not_fabricate_global_decision_for_legacy_snapshot(self) -> None:
        module = load_build_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            legacy_path = root / "legacy.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "target_date": "2026-08-20",
                        "signal_date": "2026-08-19",
                        "generated_at": "2026-08-20T15:00:00+08:00",
                        "decision": {
                            "action": "BUY_CANDIDATE",
                            "primary": {
                                "code": "600000",
                                "name": "Legacy 标的",
                                "estimated_2d_range": {"text": "-1.0% ~ +3.0%"},
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            legacy = module.summarize_pick(legacy_path)
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy["history_kind"], "legacy_snapshot")
            self.assertEqual(legacy["decision_scope"], "legacy_market_rules")
            self.assertEqual(legacy["action"], "LEGACY_ONLY")
            self.assertEqual(legacy["title"], "Legacy 规则快照")
            self.assertEqual(legacy["message"], "PRE_GLOBAL_10D_CONTRACT")
            self.assertIsNone(legacy["global_decision"])
            self.assertFalse(legacy["has_primary"])
            self.assertIsNone(legacy["a_share_legacy"]["estimated_2w_range"])
            self.assertEqual(legacy["a_share_legacy"]["estimated_2d_range"], "-1.0% ~ +3.0%")

            contract_path = root / "contract.json"
            contract_path.write_text(
                json.dumps(
                    {
                        "target_date": "2026-08-21",
                        "signal_date": "2026-08-20",
                        "generated_at": "2026-08-21T15:30:00+08:00",
                        "global_decision": {
                            "contract_version": "global-10d-v1",
                            "decision_scope": "global_10d",
                            "action_basis": "strict_cross_market_gate_v1",
                            "action": "NO_VALID_PICK",
                            "primary": None,
                            "blocker_codes": ["NO_CANDIDATE_PASSED_STRICT_GATE"],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            contract = module.summarize_pick(contract_path)
            self.assertIsNotNone(contract)
            self.assertEqual(contract["history_kind"], "global_10d_v1")
            self.assertEqual(contract["decision_scope"], "global_10d")
            self.assertEqual(contract["action"], "NO_VALID_PICK")
            self.assertEqual(contract["global_decision"]["contract_version"], "global-10d-v1")

    def test_manifest_preserves_v2_versions_and_market_regimes(self) -> None:
        module = load_build_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            static = root / "static"
            picks = root / "data" / "picks"
            public = root / "public"
            static.mkdir(parents=True)
            picks.mkdir(parents=True)
            (static / "index.html").write_text("<!doctype html>", encoding="utf-8")
            (static / "styles.css").write_text("body{}", encoding="utf-8")
            (static / "app.js").write_text("export {};", encoding="utf-8")

            snapshot = {
                "schema_version": "selector-snapshot-v2",
                "selector_mode": "legacy_active_v2_shadow",
                "model_version": "model-test-2",
                "weights_version": "weights-test-2",
                "universe_version": "universe-test-2",
                "target_date": "2026-08-20",
                "signal_date": "2026-08-19",
                "generated_at": "2026-08-19T22:06:29+08:00",
                "snapshot_key": "2026-08-20_2026-08-19_test.json",
                "analysis_models": {
                    "dual_low": {
                        "status": "available",
                        "mode": "shadow_overlay",
                        "model_id": "dsa-screening-score-v1",
                        "package_version": "1.0.0",
                        "strategy_id": "dual_low",
                        "strategy_version": "1.2-js.1",
                        "pool_scope": "a_share.merged_recall_quote_pool.pre_kline_v1",
                        "participates_in_decision": False,
                        "supported_markets": ["a_share"],
                        "score_as_of": "2026-08-19T15:00:00+08:00",
                        "input_count": 93,
                        "eligible_count": 7,
                        "rejected_count": 86,
                        "rank_universe_size": 7,
                        "required_field_coverage": {
                            "input_count": 93,
                            "complete_count": 91,
                            "ratio": 0.9785,
                            "unbounded_debug_detail": ["must-not-reach-manifest"],
                        },
                        "top_ranked": [{"code": "600000", "final_score": 91.2}],
                        "ranked_candidates": [{"sentinel": "full-ranked-pool"}],
                        "rejected_candidates": [{"sentinel": "full-rejected-pool"}],
                    }
                },
                "research_runtime": {
                    "serenity_skill": {
                        "installed": True,
                        "mode": "skill-weighted",
                        "path": "/home/runner/.agents/skills/serenity-skill",
                    }
                },
                "decision": {"action": "NO_TRADE"},
                "markets": {
                    "a_share": {
                        "market_regime": {"state": "risk_off", "warnings": ["市场偏弱"]},
                        "decision": {"action": "NO_TRADE"},
                    },
                    "hk": {
                        "decision": {
                            "action": "BUY_CANDIDATE",
                            "primary": {"code": "0700.HK", "v2": {"market_regime": "range"}},
                        },
                    },
                    "us": {"market_regime": "trend_risk_on", "decision": {"action": "NO_TRADE"}},
                },
            }
            encoded = json.dumps(snapshot, ensure_ascii=False)
            (picks / "latest.json").write_text(encoded, encoding="utf-8")
            (picks / snapshot["snapshot_key"]).write_text(encoded, encoding="utf-8")

            module.ROOT = root
            module.PUBLIC = public
            module.STATIC = static
            module.PICKS = picks
            module.main()

            manifest = json.loads((public / "data" / "picks" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_version"], "selector-manifest-v2")
            self.assertEqual(manifest["schema_version"], snapshot["schema_version"])
            self.assertEqual(manifest["selector_mode"], snapshot["selector_mode"])
            self.assertEqual(manifest["weights_version"], snapshot["weights_version"])
            self.assertEqual(manifest["universe_version"], snapshot["universe_version"])
            self.assertEqual(manifest["market_regimes"]["a_share"]["state"], "risk_off")
            self.assertEqual(manifest["market_regimes"]["hk"]["state"], "range")
            self.assertEqual(manifest["summaries"][0]["market_regimes"]["us"]["state"], "trend_risk_on")
            dual_low = manifest["analysis_models"]["dual_low"]
            self.assertEqual(dual_low["model_id"], "dsa-screening-score-v1")
            self.assertEqual(dual_low["input_count"], 93)
            self.assertEqual(dual_low["eligible_count"], 7)
            self.assertFalse(dual_low["participates_in_decision"])
            self.assertEqual(dual_low["required_field_coverage"]["ratio"], 0.9785)
            history_dual_low = manifest["summaries"][0]["analysis_models"]["dual_low"]
            self.assertEqual(history_dual_low, dual_low)
            for pool_key in ("top_ranked", "ranked_candidates", "rejected_candidates"):
                self.assertNotIn(pool_key, dual_low)
                self.assertNotIn(pool_key, history_dual_low)
            self.assertNotIn("unbounded_debug_detail", dual_low["required_field_coverage"])
            manifest_text = json.dumps(manifest, ensure_ascii=False)
            self.assertNotIn("full-ranked-pool", manifest_text)
            self.assertNotIn("full-rejected-pool", manifest_text)
            self.assertNotIn("must-not-reach-manifest", manifest_text)
            published = json.loads((public / "data" / "picks" / "latest.json").read_text(encoding="utf-8"))
            published_serenity = published["research_runtime"]["serenity_skill"]
            self.assertNotIn("path", published_serenity)
            self.assertEqual(published_serenity["mode"], "built-in-lens")
            self.assertTrue(published_serenity["skill_metadata_detected"])

    def test_build_rejects_missing_required_static_asset(self) -> None:
        module = load_build_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            static = root / "static"
            static.mkdir()
            (static / "index.html").write_text("<!doctype html>", encoding="utf-8")
            module.STATIC = static
            with self.assertRaisesRegex(FileNotFoundError, r"missing:styles\.css"):
                module.validate_required_assets()


class CloudflareWorkflowContractTests(unittest.TestCase):
    def test_workflow_is_serial_tested_and_does_not_install_unused_skill(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-worker.yml").read_text(encoding="utf-8")
        self.assertIn("group: xuangu-production", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("timeout-minutes: 40", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("node --check src/index.js", workflow)
        self.assertIn("node --check scripts/score_dual_low.mjs", workflow)
        self.assertIn("node --check vendor/stock-scoring-kit/index.js", workflow)
        self.assertIn("python scripts/validate_snapshot.py data/picks/latest.json", workflow)
        self.assertLess(
            workflow.index("node --check scripts/score_dual_low.mjs"),
            workflow.index("python server.py --once --force"),
        )
        self.assertLess(
            workflow.index("python server.py --once --force"),
            workflow.index("python scripts/validate_snapshot.py data/picks/latest.json"),
        )
        self.assertNotIn("Install Serenity skill", workflow)

    def test_obsolete_render_blueprint_files_are_removed(self) -> None:
        for name in ("render.yaml", "runtime.txt", "DEPLOY_RENDER.md"):
            self.assertFalse((ROOT / name).exists(), name)


if __name__ == "__main__":
    unittest.main()

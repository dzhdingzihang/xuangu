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
    def test_rule_rounding_matches_python_at_half_cent_boundary(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = await import({json.dumps(WORKER_URI)} + "?rule-rounding-contract");
            assert.equal(worker.roundRuleNumber(67.15 * 0.30, 2), 20.15);
            assert.equal(worker.roundRuleNumber(1.005, 2), 1.01);
            """
        )

    def test_worker_declares_scheduled_snapshot_delivery_without_device_dependency(self) -> None:
        source = (ROOT / "src" / "index.js").read_text(encoding="utf-8")
        for token in (
            "scheduled_snapshot",
            "SCHEDULED_SNAPSHOT",
            "device_dependency",
            "realtime_guaranteed",
            "LIVE_RATE_LIMITER",
            "RATE_LIMITED",
            "PICK_NOT_FOUND",
            "INVALID_DATE",
        ):
            self.assertIn(token, source)
        for retired_token in ("REALTIME_GATEWAY_URL", "QUOTE_GATEWAY_TOKEN", "FUTU_OPEND", "LICENSED_REALTIME"):
            self.assertNotIn(retired_token, source)

    def test_status_force_https_and_security_contract(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const module = await import({json.dumps(WORKER_URI)});
            const worker = module.default;
            const latest = {{
              schema_version: "selector-snapshot-v2",
              selector_mode: "legacy_active_v2_shadow",
              model_version: "model-test-2",
              weights_version: "weights-test-2",
              universe_version: "universe-test-2",
              generated_at: "2026-08-19T22:06:29+08:00",
              production_decision: {{
                action: "QUALIFIED_PICK",
                primary: {{ qualification_id: "qual_0123456789abcdef01234567" }},
              }},
              global_decision: {{ action: "NO_VALID_PICK", primary: null }},
            }};
            const env = {{
              ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK: "1",
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
            assert.equal(status.data_mode, "scheduled_snapshot");
            assert.equal(status.quote_delivery_mode, "scheduled_snapshot");
            assert.equal(status.device_dependency, false);
            assert.equal(status.schedule_time_zone, "Asia/Shanghai");
            assert.deepEqual(status.schedule_primary_checkpoints, ["08:17", "10:17", "12:17", "15:17", "16:17", "20:17", "22:47"]);
            assert.deepEqual(status.schedule_fallback_checkpoints, ["08:47", "10:47", "12:47", "15:47", "16:47", "20:47", "23:17"]);
            assert.equal(status.scheduler_primary_enabled, true);
            assert.equal(status.scheduler_primary_provider, "github_actions");
            assert.equal(status.cloudflare_dispatch_enabled, false);
            assert.equal(status.cloudflare_dispatch_optional, true);
            assert.equal(status.active_refresh_mode, "github_actions_primary_with_30m_watchdog");
            assert.equal(status.next_active_refresh, module.nextActiveRefresh(new Date(status.time), true));
            assert.equal(status.schedule_us_post_close.contract_version, "us-post-close-schedule-v1");
            assert.deepEqual(status.schedule_us_post_close.watchdog_beijing_variants, ["04:47 夏令时", "05:47 冬令时"]);
            assert.equal(status.snapshot_as_of, latest.generated_at);
            assert.equal(status.production_action, "NO_QUALIFIED_PICK");
            assert.equal(status.qualification_id, null);
            assert.equal(status.calibrated_action, "NO_VALID_PICK");
            assert.equal(status.prediction_id, null);
            assert.equal(status.readiness_contract_version, "production-readiness-v1");
            assert.equal(status.research_decision_ready, false);
            assert.equal(status.checkpoint_evidence_ready, false);
            assert.equal(status.unattended_refresh_ready, false);
            assert.equal(status.calibrated_execution_ready, false);
            assert.equal(status.next_refresh, module.nextScheduledRefresh(new Date(status.time)));
            assert.equal(
              module.nextActiveRefresh(new Date("2026-08-31T08:00:00+08:00"), false),
              "2026-08-31T08:47:00+08:00",
            );
            assert.equal(
              module.nextActiveRefresh(new Date("2026-08-29T03:00:00+08:00"), false),
              "2026-08-29T04:47:00+08:00",
            );
            assert.equal(
              module.nextActiveRefresh(new Date("2026-08-29T03:00:00+08:00"), true),
              "2026-08-29T04:17:00+08:00",
            );
            assert.deepEqual(
              module.latestActiveCheckpoint(new Date("2026-08-29T06:00:00+08:00"), false),
              {{ epoch: Date.parse("2026-08-29T04:47:00+08:00"), iso: "2026-08-29T04:47:00+08:00" }},
            );
            assert.equal(
              module.snapshotFreshness(
                "2026-08-29T04:50:00+08:00",
                new Date("2026-08-31T08:00:00+08:00"),
                false,
              ).freshness_state,
              "fresh",
            );
            assert.equal(
              module.snapshotFreshness(
                "2026-08-28T23:17:00+08:00",
                new Date("2026-08-29T06:00:00+08:00"),
                false,
              ).freshness_state,
              "stale",
            );
            assert.equal(statusResponse.headers.get("x-content-type-options"), "nosniff");
            assert.match(statusResponse.headers.get("strict-transport-security"), /max-age=/);
            assert.match(statusResponse.headers.get("permissions-policy"), /camera=\\(\\)/);

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

    def test_runtime_indexes_keep_status_and_live_off_the_full_snapshot(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?bounded-runtime-index")).default;
            const generatedAt = "2026-08-26T11:16:53+08:00";
            const snapshotKey = "2026-08-26_2026-08-25_111653.json";
            const productionDecision = {{
              contract_version: "production-rule-10d-v1",
              decision_scope: "global_10d_bounded_recall",
              action: "QUALIFIED_PICK",
              action_basis: "dual_track_candidate_qualification_v3",
              rule_model_id: "ten-day-audited-rule-ensemble-v3",
              score_kind: "RULE_QUALIFICATION_SCORE",
              probability: null,
              calibrated: false,
              primary: {{
                status: "QUALIFIED",
                market: "us",
                code: "AAPL",
                qualification_id: "qual_0123456789abcdef01234567",
                qualification_score: 78.5,
              }},
              qualified_candidate_count: 1,
              rejected_candidate_count: 799,
              evaluated_candidate_count: 800,
              blocker_codes: [],
            }};
            const runtime = {{
              contract_version: "worker-runtime-v1",
              generated_at: generatedAt,
              snapshot_key: snapshotKey,
              source_snapshot: {{ sha256: "a".repeat(64), byte_size: 7654321 }},
              schema_version: "selector-snapshot-v2",
              selector_mode: "legacy_active_v2_dual_low_shadow",
              model_version: "smart-selector-2026-08-26.2-dual-track-rule",
              weights_version: "weights-v2",
              universe_version: "universe-v2",
              global_decision: {{ action: "NO_VALID_PICK", primary: null }},
              quote_health_by_market: {{
                a_share: {{ status: "available", quote_coverage: 1 }},
                hk: {{ status: "available", quote_coverage: 1 }},
                us: {{ status: "available", quote_coverage: 1 }},
              }},
              production_decision: productionDecision,
              latest_summary: {{ snapshot_key: snapshotKey, production_action: "QUALIFIED_PICK" }},
            }};
            const liveIndex = {{
              contract_version: "worker-live-index-v1",
              generated_at: generatedAt,
              snapshot_key: snapshotKey,
              source_snapshot: {{ sha256: "a".repeat(64), byte_size: 7654321 }},
              candidate_count: 1,
              excluded_candidate_count: 0,
              contract_metadata: {{
                candidate_limit: 90,
                byte_size_limit: 524288,
                code_normalization: "worker-facing-live-code-v1",
                volume_units_by_market: {{
                  a_share: ["lot", "share", "shares"],
                  hk: ["share", "shares"],
                  us: ["share", "shares"],
                }},
              }},
              candidates: {{
                a_share: {{}}, hk: {{}}, us: {{
                  AAPL: {{
                    code: "AAPL",
                    name: "Apple",
                    kline: [],
                    realtime: {{
                      price: 213,
                      change_pct: 1.2,
                      previous_close: 210,
                      volume: 120000,
                      volume_unit: "share",
                      session: "closed",
                      source: "Scheduled quote",
                      source_as_of: "2026-08-26T08:00:00+08:00",
                      fetched_at: generatedAt,
                    }},
                  }},
                }},
              }},
            }};
            const uiBootstrap = {{
              contract_version: "ui-bootstrap-v1",
              generated_at: generatedAt,
              snapshot_key: snapshotKey,
              source_snapshot: {{ sha256: "a".repeat(64), byte_size: 7654321 }},
              production_action: "QUALIFIED_PICK",
              production_decision: productionDecision,
              global_decision: runtime.global_decision,
              markets: {{}},
            }};
            const full = {{ generated_at: generatedAt, snapshot_key: snapshotKey, full_marker: true }};
            const calls = [];
            const jsonResponse = (payload) => new Response(JSON.stringify(payload), {{
              headers: {{ "content-type": "application/json" }},
            }});
            const streamOnlyResponse = (payload) => {{
              const response = jsonResponse(payload);
              response.json = async () => {{ throw new Error("full snapshot must be streamed"); }};
              return response;
            }};
            const env = {{ ASSETS: {{ async fetch(input) {{
              const url = new URL(typeof input === "string" ? input : input.url);
              calls.push(url.pathname);
              if (url.pathname === "/data/picks/runtime.json") return jsonResponse(runtime);
              if (url.pathname === "/data/picks/live-index.json") return jsonResponse(liveIndex);
              if (url.pathname === "/data/picks/ui-bootstrap.json") return jsonResponse(uiBootstrap);
              if (url.pathname === "/data/picks/latest.json") return streamOnlyResponse(full);
              if (url.pathname === `/data/picks/${{snapshotKey}}`) return streamOnlyResponse(full);
              return new Response("missing", {{ status: 404 }});
            }} }} }};

            calls.length = 0;
            const status = await (await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/status"), env,
            )).json();
            assert.equal(status.production_action, "QUALIFIED_PICK");
            assert.equal(status.qualification_id, "qual_0123456789abcdef01234567");
            assert.equal(status.runtime_contract_version, "worker-runtime-v1");
            assert.equal(status.source_snapshot_sha256, "a".repeat(64));
            assert.equal(status.source_snapshot_byte_size, 7654321);
            assert.deepEqual(calls, [
              "/data/latest-manifest.json", "/data/latest-manifest.json",
              "/data/picks/runtime.json",
            ]);

            calls.length = 0;
            const live = await (await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"), env,
            )).json();
            assert.equal(live.ok, true);
            assert.equal(live.price, 213);
            assert.equal(live.source_index_contract_version, "worker-live-index-v1");
            assert.equal(live.source_snapshot_sha256, "a".repeat(64));
            assert.equal(live.source_snapshot_byte_size, 7654321);
            assert.deepEqual(calls, [
              "/data/latest-manifest.json", "/data/latest-manifest.json",
              "/data/picks/live-index.json",
            ]);

            calls.length = 0;
            const latestResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/latest"), env,
            );
            assert.equal((await latestResponse.json()).full_marker, true);
            assert.equal(latestResponse.headers.get("cache-control"), "no-store");
            assert.deepEqual(calls, ["/data/picks/latest.json"]);

            calls.length = 0;
            const immutable = await worker.fetch(
              new Request(`https://xuangu.alixjd.com/api/pick?snapshot=${{snapshotKey}}`), env,
            );
            assert.equal((await immutable.json()).full_marker, true);
            assert.deepEqual(calls, [`/data/picks/${{snapshotKey}}`]);

            calls.length = 0;
            const summary = await (await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/latest-summary"), env,
            )).json();
            assert.equal(summary.latest.production_action, "QUALIFIED_PICK");
            assert.deepEqual(calls, [
              "/data/latest-manifest.json", "/data/latest-manifest.json",
              "/data/latest-manifest.json", "/data/picks/runtime.json",
              "/data/latest-manifest.json", "/data/picks/ui-bootstrap.json",
            ]);

            const failClosedCalls = [];
            const failClosedEnv = {{ ASSETS: {{ async fetch(input) {{
              const url = new URL(typeof input === "string" ? input : input.url);
              failClosedCalls.push(url.pathname);
              if (url.pathname === "/data/picks/latest.json") {{
                throw new Error("full snapshot fallback must not be attempted");
              }}
              return new Response("missing", {{ status: 404 }});
            }} }} }};
            const missingRuntime = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/status"), failClosedEnv,
            );
            assert.equal(missingRuntime.status, 503);
            assert.deepEqual(failClosedCalls, [
              "/data/latest-manifest.json", "/data/latest-manifest.json",
              "/data/picks/runtime.json",
            ]);
            failClosedCalls.length = 0;
            const missingLiveIndex = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"), failClosedEnv,
            );
            assert.equal(missingLiveIndex.status, 503);
            assert.deepEqual(failClosedCalls, [
              "/data/latest-manifest.json", "/data/latest-manifest.json",
              "/data/picks/live-index.json",
            ]);
            """
        )

    def test_ui_endpoints_are_identity_bound_and_never_read_the_full_snapshot(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?ui-assets-contract")).default;
            const generatedAt = new Date().toISOString();
            const snapshotKey = "2026-08-27_ui.json";
            const source = {{ sha256: "b".repeat(64), byte_size: 9876543 }};
            const runtime = {{
              contract_version: "worker-runtime-v1",
              generated_at: generatedAt,
              snapshot_key: snapshotKey,
              source_snapshot: source,
              production_decision: {{
                contract_version: "production-rule-10d-v1",
                decision_scope: "global_10d_bounded_recall",
                action: "QUALIFIED_PICK",
                action_basis: "dual_track_candidate_qualification_v3",
                rule_model_id: "ten-day-audited-rule-ensemble-v3",
                score_kind: "RULE_QUALIFICATION_SCORE",
                probability: null,
                calibrated: false,
                primary: {{
                  status: "QUALIFIED", market: "us", code: "VZ",
                  qualification_id: "qual_0123456789abcdef01234567",
                  qualification_score: 75,
                }},
                qualified_candidate_count: 1,
                blocker_codes: [],
              }},
              global_decision: {{ action: "NO_VALID_PICK", primary: null }},
              quote_health_by_market: {{ a_share: {{}}, hk: {{}}, us: {{}} }},
            }};
            const ui = (contractVersion, extra) => ({{
              contract_version: contractVersion,
              generated_at: generatedAt,
              snapshot_key: snapshotKey,
              source_snapshot: source,
              ...extra,
            }});
            const bootstrap = ui("ui-bootstrap-v1", {{
              production_decision: runtime.production_decision,
              global_decision: runtime.global_decision,
              markets: {{}},
            }});
            const candidateId = "cand_00000000000000000004";
            const productionSelection = {{
              role_contract_version: "candidate-role-v1",
              action: "QUALIFIED_PICK",
              primary_candidate_id: candidateId,
              qualified_candidate_ids: [candidateId],
              qualified_candidate_count: 1,
            }};
            const candidates = ui("ui-candidates-v2", {{
              role_contract_version: "candidate-role-v1",
              production_selection: productionSelection,
              candidates: [{{
                id: candidateId, market: "us", code: "VZ", name: "Verizon",
                role_contract_version: "candidate-role-v1",
                decision_roles: {{ production: "PRIMARY", legacy: "NONE", research: "NONE" }},
                decision_role: "production_primary", production_rank: 1,
              }}],
              candidate_count: 1,
            }});
            const fallbackEventId = "evt-fallback-bound";
            const events = ui("ui-events-v2", {{
              event_publication: {{
                total: 1,
                published: 1,
                truncated: 0,
                is_truncated: false,
                ordering_contract_version: "decision-bound-first-then-published-desc-v1",
                decision_bound_event_ids: [fallbackEventId],
                production_bound_event_ids: [fallbackEventId],
                decision_bound_event_count: 1,
                decision_bound_record_count: 1,
              }},
              events: {{ items: [{{
                event_id: fallbackEventId,
                market: "us",
                symbol: "VZ",
                issuer: "Verizon",
                title: "Fallback bound evidence",
                event_type: "announcement",
                direction: "positive",
                decision_eligible: true,
                decision_bound: true,
              }}] }},
            }});
            const calls = [];
            const response = (payload) => new Response(JSON.stringify(payload), {{ headers: {{ "content-type": "application/json" }} }});
            const env = {{ ASSETS: {{ async fetch(input) {{
              const path = new URL(typeof input === "string" ? input : input.url).pathname;
              calls.push(path);
              if (path === "/data/picks/runtime.json") return response(runtime);
              if (path === "/data/picks/ui-bootstrap.json") return response(bootstrap);
              if (path === "/data/picks/ui-candidates.json") return response(candidates);
              if (path === "/data/picks/ui-events.json") return response(events);
              if (path === "/data/picks/latest.json") throw new Error("full snapshot must not be read");
              return new Response("missing", {{ status: 404 }});
            }} }} }};

            const summary = await (await worker.fetch(new Request("https://xuangu.test/api/latest-summary"), env)).json();
            assert.equal(summary.contract_version, "ui-bootstrap-v1");
            assert.equal(summary.latest.snapshot_key, snapshotKey);
            assert.equal(summary.status.snapshot_key, snapshotKey);
            assert.equal(summary.snapshot_use.snapshot_key, snapshotKey);
            assert.deepEqual(calls, [
              "/data/latest-manifest.json", "/data/latest-manifest.json",
              "/data/latest-manifest.json", "/data/picks/runtime.json",
              "/data/latest-manifest.json", "/data/picks/ui-bootstrap.json",
            ]);

            calls.length = 0;
            const candidatePayload = await (await worker.fetch(new Request("https://xuangu.test/api/candidates"), env)).json();
            assert.equal(candidatePayload.contract_version, "ui-candidates-v2");
            assert.equal(candidatePayload.role_contract_version, "candidate-role-v1");
            assert.deepEqual(candidatePayload.production_selection, productionSelection);
            assert.equal(candidatePayload.snapshot_use.snapshot_key, snapshotKey);
            assert.deepEqual(calls, [
              "/data/latest-manifest.json", "/data/latest-manifest.json",
              "/data/latest-manifest.json", "/data/picks/runtime.json",
              "/data/latest-manifest.json", "/data/picks/ui-candidates.json",
            ]);

            calls.length = 0;
            const eventPayload = await (await worker.fetch(new Request("https://xuangu.test/api/events"), env)).json();
            assert.equal(eventPayload.contract_version, "event-list-v2");
            assert.equal(eventPayload.total, 1);
            assert.equal(eventPayload.returned_count, 1);
            assert.equal(eventPayload.events[0].event_id, fallbackEventId);
            assert.equal(eventPayload.published_event_count, 1);
            assert.equal(eventPayload.decision_bound.returned, 1);
            assert.deepEqual(calls, [
              "/data/latest-manifest.json", "/data/latest-manifest.json",
              "/data/latest-manifest.json", "/data/picks/runtime.json",
              "/data/latest-manifest.json", "/data/picks/ui-events.json",
            ]);

            const mismatched = {{ ...bootstrap, snapshot_key: "wrong.json" }};
            const mismatchEnv = {{ ASSETS: {{ async fetch(input) {{
              const path = new URL(typeof input === "string" ? input : input.url).pathname;
              if (path === "/data/picks/runtime.json") return response(runtime);
              if (path === "/data/picks/ui-bootstrap.json") return response(mismatched);
              return new Response("missing", {{ status: 404 }});
            }} }} }};
            const mismatchResponse = await worker.fetch(new Request("https://xuangu.test/api/latest-summary"), mismatchEnv);
            assert.equal(mismatchResponse.status, 503);
            assert.equal((await mismatchResponse.json()).error, "UI_ASSET_IDENTITY_MISMATCH");
            """
        )

    def test_manifest_apis_are_paged_cached_identity_bound_and_fall_back_as_one_generation(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            import {{ createHash }} from "node:crypto";
            const worker = (await import({json.dumps(WORKER_URI)} + "?manifest-api-contract")).default;
            const generatedAt = "2026-08-29T10:20:00+08:00";
            const snapshotKey = "2026-08-29_manifest.json";
            const source = {{ sha256: "a".repeat(64), byte_size: 123456 }};
            const identity = {{
              snapshot_key: snapshotKey,
              generated_at: generatedAt,
              snapshot_sha256: source.sha256,
              snapshot_byte_size: source.byte_size,
              source_snapshot: source,
            }};
            const runtime = {{
              contract_version: "worker-runtime-v1", ...identity,
              automation: {{ scheduled_slot: "2026-08-29T10:17:00+08:00" }},
              latest_summary: {{ snapshot_key: snapshotKey }},
              production_decision: {{ action: "NO_QUALIFIED_PICK", qualified_candidates: [] }},
              global_decision: {{ action: "NO_VALID_PICK", primary: null }},
              quote_health_by_market: {{}},
            }};
            const liveIndex = {{ contract_version: "worker-live-index-v1", ...identity }};
            const summary = {{ contract_version: "ui-bootstrap-v1", ...identity, markets: {{}} }};
            const productionSelection = {{
              role_contract_version: "candidate-role-v1",
              action: "NO_QUALIFIED_PICK",
              primary_candidate_id: null,
              qualified_candidate_ids: [],
              qualified_candidate_count: 0,
            }};
            const candidateRole = (legacy, research = "NONE") => ({{
              role_contract_version: "candidate-role-v1",
              decision_roles: {{ production: "NONE", legacy, research }},
              decision_role: research === "PRIORITY"
                ? "research_priority"
                : legacy === "PRIMARY" ? "legacy_market_primary" : "legacy_watchlist",
            }});
            const candidates = {{
              contract_version: "candidate-list-v2", ...identity,
              role_contract_version: "candidate-role-v1",
              production_selection: productionSelection,
              scanned_count: 800, evaluated_count: 799,
              candidates: [
                {{ id: "cand_00000000000000000001", market: "us", code: "AAPL", name: "Apple", ...candidateRole("PRIMARY") }},
                {{ id: "cand_00000000000000000002", market: "us", code: "AMD", name: "Advanced Micro Devices", ...candidateRole("WATCHLIST") }},
                {{ id: "cand_00000000000000000003", market: "hk", code: "0700.HK", name: "Tencent", ...candidateRole("WATCHLIST", "PRIORITY") }},
              ],
            }};
            const events = {{
              contract_version: "event-list-v2", ...identity,
              event_publication: {{
                total: 3, published: 3, truncated: 0, is_truncated: false,
                ordering_contract_version: "decision-bound-first-then-published-desc-v1",
                decision_bound_event_ids: ["evt-1"], production_bound_event_ids: ["evt-1"],
                decision_bound_event_count: 1, decision_bound_record_count: 1,
              }},
              events: [
                {{ event_id: "evt-newer", market: "us", symbol: "MSFT", issuer: "Microsoft", title: "Newer filing", event_type: "announcement", direction: "neutral", decision_eligible: false, decision_bound: false }},
                {{ event_id: "evt-1", market: "us", symbol: "AAPL", issuer: "Apple Inc", title: "Product event", event_type: "announcement", direction: "positive", decision_eligible: true, decision_bound: true }},
                {{ event_id: "evt-2", market: "hk", symbol: "0700.HK", issuer: "Tencent", title: "Results", event_type: "results", direction: "negative", decision_eligible: true, decision_bound: false }},
              ],
            }};
            const history = {{
              contract_version: "history-list-v1", ...identity,
              history: [
                {{ target_date: "2026-08-29", generated_at: generatedAt }},
                {{ target_date: "2026-08-28", generated_at: "2026-08-28T20:17:00+08:00" }},
              ],
              history_evaluation: {{}}, rule_outcome_tracking: {{ status: "TRACKING" }},
            }};
            const detail = {{
              contract_version: "candidate-detail-v2", ...identity,
              id: "cand_00000000000000000001",
              role_contract_version: "candidate-role-v1",
              production_selection: productionSelection,
              candidate: {{
                id: "cand_00000000000000000001", market: "us", code: "AAPL", name: "Apple",
                ...candidateRole("PRIMARY"), kline: [{{ close: 230 }}],
              }},
            }};
            const payloads = {{ runtime, live_index: liveIndex, summary, candidates, events, history }};
            const prefixes = {{ runtime: "runtime", live_index: "live-index", summary: "summary", candidates: "candidates", events: "events", history: "history" }};
            const objects = new Map();
            const assets = {{}};
            for (const [name, payload] of Object.entries(payloads)) {{
              const raw = new TextEncoder().encode(JSON.stringify(payload));
              const digest = createHash("sha256").update(raw).digest("hex");
              const key = `${{prefixes[name]}}/${{digest}}.json`;
              objects.set(key, raw);
              assets[name] = {{ key, sha256: digest, byte_size: raw.byteLength }};
            }}
            const detailRaw = new TextEncoder().encode(JSON.stringify(detail));
            const detailDigest = createHash("sha256").update(detailRaw).digest("hex");
            const detailKey = `candidate-details/${{detailDigest}}.json`;
            objects.set(detailKey, detailRaw);
            assets.candidate_details = {{
              cand_00000000000000000001: {{ sha256: detailDigest, byte_size: detailRaw.byteLength }},
            }};
            const manifest = {{
              contract_version: "data-manifest-v1", ...identity,
              ...Object.fromEntries(Object.entries(assets)
                .filter(([name]) => name !== "candidate_details")
                .map(([name, descriptor]) => [`${{name}}_key`, descriptor.key])),
              candidate_detail_keys: {{ cand_00000000000000000001: detailKey }},
              assets,
              published_at: "2026-08-29T02:21:00+00:00",
              manifest_sha256: "b".repeat(64),
              scheduler_health: {{
                source_invocation_slot: "2026-08-29T10:17:00+08:00",
                effective_checkpoint: "2026-08-29T10:17:00+08:00",
                effective_invocation_slot: "2026-08-29T10:17:00+08:00",
                scheduler_start_delay_seconds: 4,
                generation_delay_seconds: 180,
                publication_delay_seconds: 60,
                publication_slo_seconds: 2700,
                publication_within_slo: true,
                missed_checkpoints_24h: 0,
                checkpoint_coverage_status: "COMPLETE_24H_LEDGER",
                checkpoint_evidence_contract_version: "scheduler-checkpoint-ledger-v1",
                checkpoint_evidence_ready: true,
                scheduler_readiness: "READY",
                expected_checkpoints_24h: 8,
                published_on_time_24h: 8,
                late_recoveries_24h: 0,
                ledger_started_at: "2026-08-28T02:17:00+00:00",
                evidence_lag_batches: 1,
                scheduler_slo: {{
                  contract_version: "scheduler-slo-v1",
                  guaranteed: false,
                  public_data_source_sla: false,
                  target_publication_within_minutes: 45,
                  coverage_window_hours: 24,
                }},
                recovery_mode: "on_time",
                generation_started_at: "2026-08-29T10:17:04+08:00",
              }},
            }};
            const manifestRaw = new TextEncoder().encode(JSON.stringify(manifest));
            objects.set("latest-manifest.json", manifestRaw);
            const object = (raw) => ({{
              async arrayBuffer() {{ return raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength); }},
            }});
            const env = {{
              CLOUDFLARE_SCHEDULER_ENABLED: "1",
              DATA_ASSETS: {{ async get(key) {{ return objects.has(key) ? object(objects.get(key)) : null; }} }},
              ASSETS: {{ async fetch() {{ throw new Error("embedded fallback must not mix into valid R2 generation"); }} }},
            }};

            const listRequest = new Request("https://xuangu.test/api/candidates?page=1&limit=1&market=us&q=app");
            const listResponse = await worker.fetch(listRequest, env);
            const list = await listResponse.json();
            assert.equal(listResponse.status, 200, JSON.stringify(list));
            assert.equal(list.total, 1);
            assert.equal(list.returned_count, 1);
            assert.equal(list.scanned_count, 800);
            assert.equal(list.evaluated_count, 799);
            assert.equal(list.candidates[0].code, "AAPL");
            assert.equal(list.role_contract_version, "candidate-role-v1");
            assert.deepEqual(list.production_selection, productionSelection);
            assert.deepEqual(list.source_snapshot, source);
            assert.equal(listResponse.headers.get("etag"), null);
            const unchanged = await worker.fetch(new Request(listRequest, {{ headers: {{ "if-none-match": '"stale"' }} }}), env);
            assert.equal(unchanged.status, 200);
            assert.equal(unchanged.headers.get("cache-control"), "no-store");
            const differentQuery = await worker.fetch(new Request(
              "https://xuangu.test/api/candidates?page=1&limit=1&market=hk",
              {{ headers: {{ "if-none-match": '"stale"' }} }},
            ), env);
            assert.equal(differentQuery.status, 200);
            assert.equal(differentQuery.headers.get("etag"), null);
            assert.equal((await differentQuery.json()).candidates[0].code, "0700.HK");

            const detailResponse = await worker.fetch(
              new Request("https://xuangu.test/api/candidates/cand_00000000000000000001"), env,
            );
            const detailPayload = await detailResponse.json();
            assert.equal(detailPayload.snapshot_key, snapshotKey);
            assert.deepEqual(detailPayload.source_snapshot, source);
            assert.equal(detailPayload.candidate.code, "AAPL");
            assert.equal(detailPayload.role_contract_version, "candidate-role-v1");
            assert.deepEqual(detailPayload.production_selection, productionSelection);

            const eventResponse = await worker.fetch(
              new Request("https://xuangu.test/api/events?page=1&limit=1&market=us&issuer=APPLE"), env,
            );
            const eventPayload = await eventResponse.json();
            assert.equal(eventPayload.total, 1);
            assert.equal(eventPayload.events[0].event_id, "evt-1");
            assert.equal(eventPayload.contract_version, "event-list-v2");
            assert.equal(eventPayload.ordering_contract_version, "decision-bound-first-then-published-desc-v1");
            assert.equal(eventPayload.decision_bound.returned, 1);
            assert.deepEqual(eventPayload.source_snapshot, source);
            assert.equal(eventResponse.headers.get("etag"), null);
            const defaultEventPayload = await (await worker.fetch(new Request(
              "https://xuangu.test/api/events?page=1&limit=1",
            ), env)).json();
            assert.equal(defaultEventPayload.events[0].event_id, "evt-1", "decision-bound evidence is first by default");
            assert.equal(defaultEventPayload.decision_bound.total, 1);
            assert.equal(defaultEventPayload.decision_bound.returned, 1);
            const boundEventPayload = await (await worker.fetch(new Request(
              "https://xuangu.test/api/events?scope=decision_bound&decision_eligible=true&event_id=evt-1&symbol=AAPL&event_type=announcement&direction=positive&q=product",
            ), env)).json();
            assert.equal(boundEventPayload.total, 1);
            assert.equal(boundEventPayload.events[0].event_id, "evt-1");
            assert.equal(boundEventPayload.decision_bound.all_matched_returned, true);
            const unboundEventPayload = await (await worker.fetch(new Request(
              "https://xuangu.test/api/events?decision_bound=false",
            ), env)).json();
            assert.deepEqual(unboundEventPayload.events.map((row) => row.event_id), ["evt-newer", "evt-2"]);
            const negativeEventPayload = await (await worker.fetch(new Request(
              "https://xuangu.test/api/events?market=hk&event_type=results&direction=negative&q=tencent",
            ), env)).json();
            assert.deepEqual(negativeEventPayload.events.map((row) => row.event_id), ["evt-2"]);
            for (const invalidQuery of [
              "scope=unknown", "decision_bound=maybe", "scope=decision_bound&decision_bound=false", "decision_eligible=maybe", "direction=sideways",
            ]) {{
              const invalid = await worker.fetch(new Request(`https://xuangu.test/api/events?${{invalidQuery}}`), env);
              assert.equal(invalid.status, 400, invalidQuery);
              assert.equal((await invalid.json()).error, "INVALID_EVENT_FILTER");
            }}
            const eventVariant = await worker.fetch(new Request(
              "https://xuangu.test/api/events?page=1&limit=1&market=hk",
              {{ headers: {{ "if-none-match": '"stale"' }} }},
            ), env);
            assert.equal(eventVariant.status, 200);
            assert.equal(eventVariant.headers.get("etag"), null);

            const historyResponse = await worker.fetch(
              new Request("https://xuangu.test/api/history?page=2&limit=1"), env,
            );
            const historyPayload = await historyResponse.json();
            assert.equal(historyPayload.meta.total, 2);
            assert.equal(historyPayload.meta.page, 2);
            assert.equal(historyPayload.history.length, 1);
            assert.deepEqual(historyPayload.source_snapshot, source);
            assert.equal(historyPayload.rule_outcome_tracking.status, "TRACKING");
            assert.equal(historyResponse.headers.get("etag"), null);
            const historyVariant = await worker.fetch(new Request(
              "https://xuangu.test/api/history?page=1&limit=1",
              {{ headers: {{ "if-none-match": '"stale"' }} }},
            ), env);
            assert.equal(historyVariant.status, 200);
            assert.equal(historyVariant.headers.get("etag"), null);

            for (const [path, field] of [
              ["/api/candidates?page=0", "page"],
              ["/api/candidates?limit=101", "limit"],
              ["/api/events?page=1.5", "page"],
              ["/api/events?limit=51", "limit"],
              ["/api/history?page=-1", "page"],
              ["/api/history?limit=6", "limit"],
            ]) {{
              const invalidPagination = await worker.fetch(
                new Request(`https://xuangu.test${{path}}`), env,
              );
              assert.equal(invalidPagination.status, 400, path);
              const invalidPayload = await invalidPagination.json();
              assert.equal(invalidPayload.error, "INVALID_PAGINATION", path);
              assert.equal(invalidPayload.field, field, path);
            }}

            const gateResponse = await worker.fetch(new Request("https://xuangu.test/api/gate-status"), env);
            const gate = await gateResponse.json();
            assert.equal(gate.contract_version, "scheduler-health-v2");
            assert.equal(gate.scheduler_enabled, true);
            assert.equal(gate.scheduler_primary_enabled, true);
            assert.equal(gate.scheduler_primary_provider, "github_actions");
            assert.equal(gate.scheduler_gap, null);
            assert.equal(gate.cloudflare_dispatch_enabled, false);
            assert.equal(gate.cloudflare_dispatch_gap, "OPTIONAL_DISPATCH_TOKEN_NOT_PROVISIONED");
            assert.equal(gate.checkpoint_evidence_ready, true);
            assert.equal(gate.scheduler_readiness, "READY");
            assert.equal(gate.unattended_refresh_ready, true);
            assert.equal(gate.source_invocation_slot, "2026-08-29T10:17:00+08:00");
            assert.equal(gate.generation_delay_seconds, 180);
            assert.equal(gate.publication_delay_seconds, 60);
            assert.equal(gate.missed_checkpoints_24h, 0);
            assert.equal(gate.publication_backend, "r2");
            const sameGenerationEmbeddedEnv = {{
              CLOUDFLARE_SCHEDULER_ENABLED: "1",
              ASSETS: {{ async fetch(input) {{
                const path = new URL(typeof input === "string" ? input : input.url).pathname;
                return path === "/data/latest-manifest.json"
                  ? new Response(manifestRaw, {{ headers: {{ "content-type": "application/json" }} }})
                  : new Response("missing", {{ status: 404 }});
              }} }},
            }};
            const backendChangedGate = await worker.fetch(new Request(
              "https://xuangu.test/api/gate-status",
              {{ headers: {{ "if-none-match": gateResponse.headers.get("etag") }} }},
            ), sameGenerationEmbeddedEnv);
            assert.equal(backendChangedGate.status, 200);
            assert.equal((await backendChangedGate.json()).publication_backend, "embedded");
            const enabledGate = await worker.fetch(new Request(
              "https://xuangu.test/api/gate-status",
              {{ headers: {{ "if-none-match": gateResponse.headers.get("etag") }} }},
            ), {{ ...env, GITHUB_WORKFLOW_DISPATCH_TOKEN: "provisioned" }});
            assert.equal(enabledGate.status, 200);
            const enabledGatePayload = await enabledGate.json();
            assert.equal(enabledGatePayload.scheduler_enabled, true);
            assert.equal(enabledGatePayload.cloudflare_dispatch_enabled, true);
            assert.equal(enabledGatePayload.cloudflare_dispatch_gap, null);

            const immutableRequest = new Request(`https://xuangu.test/api/data/${{encodeURIComponent(assets.candidates.key)}}`);
            const immutable = await worker.fetch(immutableRequest, env);
            assert.equal(immutable.status, 200);
            assert.equal(immutable.headers.get("cache-control"), "public, max-age=31536000, immutable");
            const immutable304 = await worker.fetch(new Request(immutableRequest, {{
              headers: {{ "if-none-match": immutable.headers.get("etag") }},
            }}), env);
            assert.equal(immutable304.status, 304);

            let frozenAliasReads = 0;
            const frozenAliasEnv = {{
              DATA_ASSETS: {{ async get(key) {{
                if (key === "latest-manifest.json") {{
                  frozenAliasReads += 1;
                  if (frozenAliasReads > 1) throw new Error("manifest alias changed during request");
                  return object(manifestRaw);
                }}
                return objects.has(key) ? object(objects.get(key)) : null;
              }} }},
              ASSETS: {{ async fetch() {{ throw new Error("embedded fallback must not be needed"); }} }},
            }};
            const immutableFrozen = await worker.fetch(immutableRequest, frozenAliasEnv);
            assert.equal(immutableFrozen.status, 200);
            assert.equal(frozenAliasReads, 1);
            assert.equal(immutableFrozen.headers.get("etag"), immutable.headers.get("etag"));

            const embeddedFetch = async (input) => {{
              const path = new URL(typeof input === "string" ? input : input.url).pathname;
              const key = path === "/data/latest-manifest.json"
                ? "latest-manifest.json" : path.slice("/data/".length);
              const raw = objects.get(key);
              return raw ? new Response(raw, {{ headers: {{ "content-type": "application/json" }} }})
                : new Response("missing", {{ status: 404 }});
            }};
            const missingR2ObjectEnv = {{
              DATA_ASSETS: {{ async get(key) {{
                return key === "latest-manifest.json" ? object(manifestRaw) : null;
              }} }},
              ASSETS: {{ fetch: embeddedFetch }},
            }};
            const immutableFallback = await worker.fetch(immutableRequest, missingR2ObjectEnv);
            assert.equal(immutableFallback.status, 200);
            assert.equal(immutableFallback.headers.get("etag"), immutable.headers.get("etag"));

            const olderEmbeddedManifest = structuredClone(manifest);
            olderEmbeddedManifest.snapshot_key = "2026-08-28_old-embedded.json";
            olderEmbeddedManifest.generated_at = "2026-08-28T20:47:00+08:00";
            olderEmbeddedManifest.snapshot_sha256 = "c".repeat(64);
            olderEmbeddedManifest.snapshot_byte_size = 654321;
            olderEmbeddedManifest.source_snapshot = {{ sha256: "c".repeat(64), byte_size: 654321 }};
            const olderManifestRaw = new TextEncoder().encode(JSON.stringify(olderEmbeddedManifest));
            const olderIdentity = {{
              snapshot_key: olderEmbeddedManifest.snapshot_key,
              generated_at: olderEmbeddedManifest.generated_at,
              snapshot_sha256: olderEmbeddedManifest.snapshot_sha256,
              snapshot_byte_size: olderEmbeddedManifest.snapshot_byte_size,
              source_snapshot: olderEmbeddedManifest.source_snapshot,
            }};
            const olderRuntimeRaw = new TextEncoder().encode(JSON.stringify({{ ...runtime, ...olderIdentity }}));
            const olderCandidatesRaw = new TextEncoder().encode(JSON.stringify({{ ...candidates, ...olderIdentity }}));
            const mixedGenerationEnv = {{
              DATA_ASSETS: {{ async get(key) {{
                return key === "latest-manifest.json" ? object(manifestRaw) : null;
              }} }},
              ASSETS: {{ async fetch(input) {{
                const path = new URL(typeof input === "string" ? input : input.url).pathname;
                if (path === "/data/latest-manifest.json") {{
                  return new Response(olderManifestRaw, {{ headers: {{ "content-type": "application/json" }} }});
                }}
                if (path === "/data/picks/runtime.json") {{
                  return new Response(olderRuntimeRaw, {{ headers: {{ "content-type": "application/json" }} }});
                }}
                if (path === "/data/ui/candidates.json") {{
                  return new Response(olderCandidatesRaw, {{ headers: {{ "content-type": "application/json" }} }});
                }}
                return new Response("missing", {{ status: 404 }});
              }} }},
            }};
            const mixedGenerationResponse = await worker.fetch(
              new Request("https://xuangu.test/api/candidates?page=1&limit=2"),
              mixedGenerationEnv,
            );
            assert.equal(mixedGenerationResponse.status, 503);
            assert.equal((await mixedGenerationResponse.json()).error, "API_ASSET_UNAVAILABLE");

            const embeddedCalls = [];
            const fallbackEnv = {{
              DATA_ASSETS: {{ async get() {{ throw new Error("R2 unavailable"); }} }},
              ASSETS: {{ async fetch(input) {{
                const path = new URL(typeof input === "string" ? input : input.url).pathname;
                embeddedCalls.push(path);
                const key = path === "/data/latest-manifest.json"
                  ? "latest-manifest.json" : path.slice("/data/".length);
                const raw = objects.get(key);
                return raw ? new Response(raw, {{ headers: {{ "content-type": "application/json" }} }})
                  : new Response("missing", {{ status: 404 }});
              }} }},
            }};
            const fallbackList = await (await worker.fetch(
              new Request("https://xuangu.test/api/candidates?page=1&limit=2"), fallbackEnv,
            )).json();
            assert.equal(fallbackList.total, 3);
            assert.ok(embeddedCalls.every((path) => path.startsWith("/data/")));
            const manifestAlias = await worker.fetch(
              new Request("https://xuangu.test/data/latest-manifest.json"), fallbackEnv,
            );
            assert.equal(manifestAlias.status, 200);
            assert.equal(manifestAlias.headers.get("cache-control"), "no-store");
            """
        )

    def test_cloudflare_scheduled_handler_dispatches_only_whitelisted_crons(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const workerModule = await import({json.dumps(WORKER_URI)} + "?scheduled-dispatch-contract");
            const worker = workerModule.default;
            const requests = [];
            globalThis.fetch = async (input, init) => {{
              requests.push({{ input: String(input), init }});
              return new Response(null, {{ status: 204 }});
            }};
            const env = {{ CLOUDFLARE_SCHEDULER_ENABLED: "1", GITHUB_WORKFLOW_DISPATCH_TOKEN: "secret-token" }};
            const controller = {{
              cron: "17 0,2,4,7,8,12 * * MON-FRI",
              scheduledTime: Date.parse("2026-08-28T00:17:00Z"),
            }};
            await worker.scheduled(controller, env, {{ waitUntil() {{}} }});
            assert.equal(requests.length, 1);
            assert.equal(requests[0].input, "https://api.github.com/repos/dzhdingzihang/xuangu/actions/workflows/deploy-worker.yml/dispatches");
            assert.equal(requests[0].init.headers.authorization, "Bearer secret-token");
            const body = JSON.parse(requests[0].init.body);
            assert.equal(body.ref, "main");
            assert.deepEqual(body.inputs, {{
              scheduler: "cloudflare-cron-v1",
              cron: "17 0 * * 1-5",
              scheduled_at: "2026-08-28T00:17:00.000Z",
            }});
            assert.equal(workerModule.canonicalGithubCronForScheduled({{
              cron: "47 14 * * MON-FRI",
              scheduledTime: Date.parse("2026-08-28T14:47:00Z"),
            }}), "47 14 * * 1-5");
            await assert.rejects(
              worker.scheduled({{ ...controller, cron: "* * * * *" }}, env, {{ waitUntil() {{}} }}),
              /not whitelisted/,
            );
            await assert.rejects(
              worker.scheduled({{ ...controller, scheduledTime: Date.parse("2026-08-28T14:17:00Z") }}, env, {{ waitUntil() {{}} }}),
              /does not match/,
            );
            await assert.rejects(
              worker.scheduled({{ ...controller, scheduledTime: Date.parse("2026-08-29T00:17:00Z") }}, env, {{ waitUntil() {{}} }}),
              /does not match/,
            );
            await assert.rejects(
              worker.scheduled({{ ...controller, scheduledTime: Date.parse("2026-08-28T00:17:01Z") }}, env, {{ waitUntil() {{}} }}),
              /does not match/,
            );
            const missingToken = await worker.scheduled(
              controller,
              {{ CLOUDFLARE_SCHEDULER_ENABLED: "1" }},
              {{ waitUntil() {{}} }},
            );
            assert.equal(missingToken.reason, "GITHUB_WORKFLOW_DISPATCH_TOKEN_MISSING");
            await worker.scheduled(controller, {{}}, {{ waitUntil() {{}} }});
            assert.equal(requests.length, 1);
            """
        )

    def test_wrangler_uses_primary_and_dst_crons_within_free_limit(self) -> None:
        config = json.loads((ROOT / "wrangler.jsonc").read_text(encoding="utf-8"))
        crons = config["triggers"]["crons"]
        self.assertEqual(
            crons,
            [
                "17 0,2,4,7,8,12 * * MON-FRI",
                "47 14 * * MON-FRI",
                "17 20 * * MON-FRI",
                "17 21 * * MON-FRI",
            ],
        )
        self.assertLessEqual(len(crons), 5)

    def test_all_v4_rule_qualified_candidates_are_live_allowlisted_and_summarized(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            import {{ createHash }} from "node:crypto";
            const worker = (await import({json.dumps(WORKER_URI)} + "?qualified-pool-contract")).default;
            const qualificationId = (market, code) => `qual_${{createHash("sha256")
              .update(`production-rule-10d-v1|ten-day-audited-rule-ensemble-v4|||${{market}}|${{code}}`)
              .digest("hex").slice(0, 24)}}`;
            const sourceRow = (market, code, qualificationTrack) => ({{
              market,
              code,
              name: `Qualified ${{code}}`,
              blocker_codes: [
                "TEN_DAY_MODEL_NOT_READY",
                "TEN_DAY_PREDICTION_MISSING",
                ...(qualificationTrack === "quality_technical" ? ["VERIFIED_POSITIVE_EVENT_MISSING"] : []),
              ],
              legacy_recommendation_degree: 80,
              v2_rank: 5,
              v2_rank_universe_size: 100,
              priority_components: {{ data_quality: 19.6 }},
              event_candidate_scanned: true,
              verified_positive_event_ids: qualificationTrack === "event_catalyst" ? [`event:${{code}}`] : [],
              estimated_10d_range: {{ low_pct: -4, high_pct: 8 }},
            }});
            const candidate = (source, qualificationTrack, volumeUnit = "share") => {{
              const eventStrength = qualificationTrack === "event_catalyst" ? 85 : 0;
              const scoreComponents = {{
                legacy_recommendation: source.legacy_recommendation_degree * 0.30,
                v2_rank_strength: 28.8,
                data_quality: 14.7,
                verified_event_evidence: eventStrength * 0.15,
                risk_reward_scenario: 10,
              }};
              const score = Object.values(scoreComponents).reduce((sum, value) => sum + value, 0);
              return {{
              qualification_id: qualificationId(source.market, source.code),
              status: "QUALIFIED",
              market: source.market,
              code: source.code,
              name: source.name,
              rule_model_id: "ten-day-audited-rule-ensemble-v4",
              score_kind: "RULE_QUALIFICATION_SCORE",
              qualification_score: score,
              score_components: scoreComponents,
              probability_status: "NOT_APPLICABLE",
              probability: null,
              calibrated: false,
              expected_net_utility: null,
              legacy_signal: null,
              legacy_recommendation_degree: source.legacy_recommendation_degree,
              v2_rank: source.v2_rank,
              v2_rank_universe_size: source.v2_rank_universe_size,
              v2_rank_fraction: 0.05,
              data_quality_score: 98,
              estimated_10d_range: {{ low_pct: -4, high_pct: 8, horizon_trade_days: 10 }},
              risk_reward: {{ upside_pct: 8, downside_pct: 4, ratio: 2 }},
              blocker_codes: [],
              event_candidate_scanned: true,
              verified_positive_event_ids: source.verified_positive_event_ids,
              entry_price: null,
              calendar_id: null,
              calendar_version: null,
              entry_trade_date: null,
              forecast_end_trade_date: null,
              qualification_track: qualificationTrack,
              track_evaluations: [
                {{
                  track: "event_catalyst",
                  status: qualificationTrack === "event_catalyst" ? "PASS" : "FAIL",
                  blocker_codes: qualificationTrack === "event_catalyst" ? [] : ["VERIFIED_POSITIVE_EVENT_MISSING"],
                }},
                {{ track: "quality_technical", status: "PASS", blocker_codes: [] }},
              ],
              ten_day_trade_plan: null,
              candidate_snapshot: {{
                code: source.code,
                name: source.name,
                data_quality: {{ score: 98 }},
                kline: [],
                realtime: {{
                  price: 100 + score / 10,
                  change_pct: 1.2,
                  previous_close: 100,
                  volume: 120000,
                  volume_unit: volumeUnit,
                  session: "closed",
                  session_label: "休市",
                  source: "Scheduled quote",
                  source_as_of: "2026-08-25T16:00:00+08:00",
                  fetched_at: "2026-08-25T22:47:00+08:00",
                }},
              }},
              }};
            }};
            const sources = [
              sourceRow("us", "AAPL", "event_catalyst"),
              sourceRow("us", "MSFT", "quality_technical"),
              sourceRow("hk", "0700.HK", "quality_technical"),
            ];
            sources[2].legacy_recommendation_degree = 75;
            const [aapl, msft, tencent] = [
              candidate(sources[0], "event_catalyst"),
              candidate(sources[1], "quality_technical"),
              candidate(sources[2], "quality_technical"),
            ];
            const latest = {{
              model_version: "smart-selector-2026-08-29.1-two-tier-rule",
              generated_at: "2026-08-25T22:47:00+08:00",
              snapshot_key: "2026-08-25_2026-08-25_224700.json",
              markets: {{
                us: {{ decision: {{ watchlist: [] }} }},
                hk: {{ decision: {{ watchlist: [] }} }},
              }},
              global_decision: {{ evaluated_candidates: sources }},
              production_rule_inputs: {{
                contract_version: "production-rule-inputs-v2",
                action_basis: "dual_track_candidate_qualification_v4",
                rule_model_id: "ten-day-audited-rule-ensemble-v4",
                evaluated_candidate_count: 3,
                ledger_sha256: "a".repeat(64),
                rows: [aapl, msft, tencent].map((row, index) => ({{
                  ...sources[index],
                  input_index: index,
                  source_candidate_present: true,
                  source_data_quality_score: 98,
                  candidate_snapshot: structuredClone(row.candidate_snapshot),
                }})),
              }},
              production_decision: {{
                contract_version: "production-rule-10d-v1",
                decision_scope: "global_10d_bounded_recall",
                action_basis: "dual_track_candidate_qualification_v4",
                action: "QUALIFIED_PICK",
                rule_model_id: "ten-day-audited-rule-ensemble-v4",
                score_kind: "RULE_QUALIFICATION_SCORE",
                probability: null,
                calibrated: false,
                qualified_candidate_count: 3,
                evaluated_candidate_count: 3,
                rejected_candidate_count: 0,
                blocker_codes: [],
                source_rule_inputs_contract_version: "production-rule-inputs-v2",
                source_rule_inputs_sha256: "a".repeat(64),
                source_rule_input_count: 3,
                primary: structuredClone(aapl),
                qualified_candidates: structuredClone([aapl, msft, tencent]),
                evaluated_candidates: structuredClone([aapl, msft, tencent]),
              }},
            }};
            const responseFor = (payload) => new Response(JSON.stringify(payload), {{
              status: 200,
              headers: {{ "content-type": "application/json" }},
            }});
            const envFor = (payload) => ({{
              ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK: "1",
              ASSETS: {{ fetch: async (input) => {{
                const url = new URL(typeof input === "string" ? input : input.url);
                if (url.pathname === "/data/picks/latest.json") return responseFor(payload);
                return new Response("missing", {{ status: 404 }});
              }} }},
            }});

            const secondaryResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=MSFT"),
              envFor(latest),
            );
            assert.equal(secondaryResponse.status, 200);
            assert.equal((await secondaryResponse.json()).code, "MSFT");

            const crossMarketResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=hk&code=0700.HK"),
              envFor(latest),
            );
            assert.equal(crossMarketResponse.status, 200);
            assert.equal((await crossMarketResponse.json()).market, "hk");

            const unrelatedResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=TSLA"),
              envFor(latest),
            );
            assert.equal(unrelatedResponse.status, 404);
            assert.equal((await unrelatedResponse.json()).error, "LIVE_CODE_NOT_IN_CURRENT_SNAPSHOT");

            const summaryResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/latest-summary"),
              envFor(latest),
            );
            assert.equal(summaryResponse.status, 200);
            const summary = (await summaryResponse.json()).latest.production_decision;
            assert.deepEqual(summary.qualified_candidates.map((row) => row.code), ["AAPL", "MSFT", "0700.HK"]);
            assert.equal(summary.qualified_candidates_truncated, false);
            assert.equal(summary.qualified_candidates[0].qualification_track, "event_catalyst");
            assert.equal(summary.qualified_candidates[1].qualification_track, "quality_technical");
            assert.equal(summary.qualified_candidates[1].track_evaluations[1].status, "PASS");
            assert.equal(Object.hasOwn(summary.primary, "candidate_snapshot"), false);
            assert.equal(summary.qualified_candidates.every((row) => !Object.hasOwn(row, "candidate_snapshot")), true);

            const toV2 = (row) => ({{ ...row, rule_model_id: "ten-day-audited-rule-ensemble-v2" }});
            const v2Decision = {{
              ...latest.production_decision,
              action_basis: "candidate_level_rule_qualification_v2",
              rule_model_id: "ten-day-audited-rule-ensemble-v2",
              primary: toV2(aapl),
              qualified_candidates: [aapl, msft, tencent].map(toV2),
            }};
            const mismatched = {{
              ...latest,
              production_decision: v2Decision,
            }};
            const rejectedResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=MSFT"),
              envFor(mismatched),
            );
            assert.equal(rejectedResponse.status, 404);
            assert.equal((await rejectedResponse.json()).error, "LIVE_CODE_NOT_IN_CURRENT_SNAPSHOT");

            const mismatchedStatusResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/status"),
              envFor(mismatched),
            );
            const mismatchedStatus = await mismatchedStatusResponse.json();
            assert.equal(mismatchedStatus.production_action, "NO_QUALIFIED_PICK");
            assert.equal(mismatchedStatus.qualification_id, null);
            const mismatchedSummaryResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/latest-summary"),
              envFor(mismatched),
            );
            const mismatchedSummary = (await mismatchedSummaryResponse.json()).latest;
            assert.equal(mismatchedSummary.production_action, "NO_QUALIFIED_PICK");
            assert.equal(mismatchedSummary.production_decision, null);

            const archivedV2 = {{ ...mismatched, model_version: "smart-selector-2026-08-26.1-candidate-rule" }};
            const archivedResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=MSFT"),
              envFor(archivedV2),
            );
            assert.equal(archivedResponse.status, 200);

            const oldModelWithV3 = {{
              ...structuredClone(latest),
              model_version: "smart-selector-2026-08-26.1-candidate-rule",
            }};
            const oldModelWithV3Response = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              envFor(oldModelWithV3),
            );
            assert.equal(oldModelWithV3Response.status, 404);
            const oldModelWithV3Status = await (
              await worker.fetch(new Request("https://xuangu.alixjd.com/api/status"), envFor(oldModelWithV3))
            ).json();
            assert.equal(oldModelWithV3Status.production_action, "NO_QUALIFIED_PICK");

            const missingModelWithV3 = structuredClone(latest);
            delete missingModelWithV3.model_version;
            const missingModelWithV3Response = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              envFor(missingModelWithV3),
            );
            assert.equal(missingModelWithV3Response.status, 404);

            const failedQuality = structuredClone(latest);
            failedQuality.production_decision.qualified_candidates[1].track_evaluations[1].status = "FAIL";
            const failedQualityResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=MSFT"),
              envFor(failedQuality),
            );
            assert.equal(failedQualityResponse.status, 404);

            const passWithBlocker = structuredClone(latest);
            passWithBlocker.production_decision.qualified_candidates[1].track_evaluations[1].blocker_codes = ["IMPOSSIBLE_PASS_BLOCKER"];
            const passWithBlockerResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=MSFT"),
              envFor(passWithBlocker),
            );
            assert.equal(passWithBlockerResponse.status, 404);

            const eventWithoutEvidence = structuredClone(latest);
            eventWithoutEvidence.production_decision.primary.verified_positive_event_ids = [];
            eventWithoutEvidence.production_decision.qualified_candidates[0].verified_positive_event_ids = [];
            const eventWithoutEvidenceResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              envFor(eventWithoutEvidence),
            );
            assert.equal(eventWithoutEvidenceResponse.status, 404);

            const evilMirror = structuredClone(latest);
            evilMirror.production_decision.qualified_candidates[1].name = "EVIL MIRROR";
            const evilMirrorResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=MSFT"),
              envFor(evilMirror),
            );
            assert.equal(evilMirrorResponse.status, 404);

            const lowScorePrimary = structuredClone(latest);
            lowScorePrimary.production_decision.primary = structuredClone(
              lowScorePrimary.production_decision.qualified_candidates[2],
            );
            const lowScorePrimaryResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              envFor(lowScorePrimary),
            );
            assert.equal(lowScorePrimaryResponse.status, 404);

            const reorderedEvaluation = structuredClone(latest);
            [
              reorderedEvaluation.production_decision.evaluated_candidates[1],
              reorderedEvaluation.production_decision.evaluated_candidates[2],
            ] = [
              reorderedEvaluation.production_decision.evaluated_candidates[2],
              reorderedEvaluation.production_decision.evaluated_candidates[1],
            ];
            const reorderedEvaluationResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              envFor(reorderedEvaluation),
            );
            assert.equal(reorderedEvaluationResponse.status, 404);

            const highScoreFakeRejected = structuredClone(latest);
            highScoreFakeRejected.production_decision.evaluated_candidates[0].status = "REJECTED";
            const highScoreFakeRejectedResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              envFor(highScoreFakeRejected),
            );
            assert.equal(highScoreFakeRejectedResponse.status, 404);

            const fakeQualityPass = structuredClone(latest);
            fakeQualityPass.production_rule_inputs.rows[1].source_data_quality_score = 90;
            fakeQualityPass.production_rule_inputs.rows[1].candidate_snapshot.data_quality.score = 90;
            for (const row of [
              fakeQualityPass.production_decision.qualified_candidates[1],
              fakeQualityPass.production_decision.evaluated_candidates[1],
            ]) {{
              row.data_quality_score = 90;
              row.score_components.data_quality = 13.5;
              row.qualification_score = 76.3;
              row.candidate_snapshot.data_quality.score = 90;
            }}
            const fakeQualityPassResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=MSFT"),
              envFor(fakeQualityPass),
            );
            assert.equal(fakeQualityPassResponse.status, 404);

            const secondaryQuoteMissing = structuredClone(latest);
            delete secondaryQuoteMissing.production_rule_inputs.rows[1].candidate_snapshot.realtime;
            delete secondaryQuoteMissing.production_decision.qualified_candidates[1].candidate_snapshot.realtime;
            delete secondaryQuoteMissing.production_decision.evaluated_candidates[1].candidate_snapshot.realtime;
            const secondaryQuoteMissingResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              envFor(secondaryQuoteMissing),
            );
            assert.equal(secondaryQuoteMissingResponse.status, 404);
            """
        )

    def test_live_index_code_and_volume_contract_is_normalized_consistently(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?live-index-normalization")).default;
            const generatedAt = "2026-08-26T11:16:53+08:00";
            const quote = (price, volumeUnit) => ({{
              price,
              volume: 100,
              volume_unit: volumeUnit,
              session: "closed",
              source_as_of: "2026-08-26T08:00:00+08:00",
              fetched_at: generatedAt,
            }});
            const candidate = (code, price, volumeUnit) => ({{
              code, symbol: code, name: code, kline: [], realtime: quote(price, volumeUnit),
            }});
            const liveIndex = {{
              contract_version: "worker-live-index-v1",
              generated_at: generatedAt,
              snapshot_key: "2026-08-26_2026-08-25_111653.json",
              source_snapshot: {{ sha256: "b".repeat(64), byte_size: 7654321 }},
              candidate_count: 3,
              excluded_candidate_count: 0,
              contract_metadata: {{
                candidate_limit: 90,
                byte_size_limit: 524288,
                code_normalization: "worker-facing-live-code-v1",
                volume_units_by_market: {{
                  a_share: ["lot", "share", "shares"],
                  hk: ["share", "shares"],
                  us: ["share", "shares"],
                }},
              }},
              candidates: {{
                a_share: {{ "600000": candidate("600000", 12.3, "share") }},
                hk: {{ "0700.HK": candidate("0700.HK", 380.2, "shares") }},
                us: {{ "BRK-B": candidate("BRK-B", 500, "share") }},
              }},
            }};
            const env = {{ ASSETS: {{ async fetch(input) {{
              const url = new URL(typeof input === "string" ? input : input.url);
              return url.pathname === "/data/picks/live-index.json"
                ? new Response(JSON.stringify(liveIndex), {{ headers: {{ "content-type": "application/json" }} }})
                : new Response("missing", {{ status: 404 }});
            }} }} }};
            const cases = [
              ["a_share", "SH600000", "600000", "share"],
              ["a_share", "SZ.600000", "600000", "share"],
              ["a_share", "600000.SZ", "600000", "share"],
              ["hk", "700", "0700.HK", "shares"],
              ["hk", "00700.HK", "0700.HK", "shares"],
              ["us", "BRK.B", "BRK-B", "share"],
              ["us", "BRK_B", "BRK-B", "share"],
            ];
            for (const [market, inputCode, expectedCode, expectedUnit] of cases) {{
              const response = await worker.fetch(new Request(
                `https://xuangu.alixjd.com/api/live?market=${{market}}&code=${{encodeURIComponent(inputCode)}}`,
              ), env);
              assert.equal(response.status, 200, `${{market}}:${{inputCode}}`);
              const payload = await response.json();
              assert.equal(payload.code, expectedCode);
              assert.equal(payload.volume_unit, expectedUnit);
              assert.equal(payload.source_index_contract_version, "worker-live-index-v1");
            }}
            """
        )

    def test_live_quotes_are_served_only_from_the_published_snapshot(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?live-contract")).default;
            const latest = {{
              generated_at: "2026-08-22T08:20:00+08:00",
              snapshot_key: "2026-08-25_2026-08-22_082000.json",
              markets: {{
                a_share: {{ decision: {{ watchlist: [{{
                    code: "603228",
                    name: "测试A股",
                    kline: [{{ date: "2026-08-21", open: 12, close: 12.34, high: 12.5, low: 11.9 }}],
                    realtime: {{
                      price: 12.34,
                      change_pct: 1.8,
                      previous_close: 12.12,
                      volume: 1234,
                      volume_unit: "lot",
                      session: "closed",
                      session_label: "休市",
                      source: "Tencent scheduled quote",
                      source_as_of: "2026-08-21T16:14:46+08:00",
                      fetched_at: "2026-08-22T08:18:10+08:00",
                    }},
                  }}
                ] }} }},
                hk: {{ decision: {{ watchlist: [{{
                    code: "0700.HK",
                    name: "腾讯控股",
                    kline: [],
                    realtime: {{
                      price: 380.2,
                      change_pct: 0.7,
                      previous_close: 377.6,
                      volume: 880000,
                      volume_unit: "share",
                      session: "closed",
                      session_label: "非交易时段",
                      source: "Yahoo scheduled quote",
                      source_as_of: "2026-08-21T16:08:00+08:00",
                      fetched_at: "2026-08-22T08:18:20+08:00",
                    }},
                  }}
                ] }} }},
                us: {{ decision: {{ watchlist: [{{
                    code: "AAPL",
                    name: "Apple",
                    kline: [],
                    realtime: {{
                      price: 213,
                      change_pct: 3.9,
                      previous_close: 205,
                      volume: 120000,
                      volume_unit: "share",
                      session: "closed",
                      session_label: "非交易时段",
                      source: "Yahoo scheduled quote",
                      source_as_of: "2026-08-22T07:59:00+08:00",
                      fetched_at: "2026-08-22T08:18:30+08:00",
                    }},
                  }}
                ] }} }},
              }},
            }};
            const jsonResponse = (payload) => new Response(JSON.stringify(payload), {{
              status: 200,
              headers: {{ "content-type": "application/json" }},
            }});
            let upstreamCalls = 0;
            globalThis.fetch = async () => {{
              upstreamCalls += 1;
              throw new Error("Worker must not fetch a request-time quote upstream");
            }};
            const env = {{
              ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK: "1",
              ASSETS: {{ fetch: async (input) => {{
                const url = new URL(typeof input === "string" ? input : input.url);
                if (url.pathname === "/data/picks/latest.json") return jsonResponse(latest);
                return new Response("missing", {{ status: 404 }});
              }} }},
            }};

            const aResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=a_share&code=603228"),
              env,
            );
            assert.equal(aResponse.status, 200);
            const aShare = await aResponse.json();
            assert.equal(aShare.volume, 1234);
            assert.equal(aShare.volume_unit, "lot");
            assert.equal(aShare.contract_version, "live-quote-v1");
            assert.equal(aShare.provider_class, "SCHEDULED_SNAPSHOT");
            assert.equal(aShare.source_as_of, "2026-08-21T16:14:46+08:00");
            assert.equal(aShare.fetched_at, "2026-08-22T08:18:10+08:00");
            assert.equal(aShare.quote_status, "LAST_CLOSE");
            assert.notEqual(aShare.quote_status, "REALTIME");
            assert.equal(aShare.is_realtime, false);
            assert.equal(aShare.realtime_guaranteed, false);
            assert.equal(aShare.snapshot_as_of, latest.generated_at);
            assert.equal(aShare.snapshot_key, latest.snapshot_key);
            assert.equal(typeof aShare.latency_seconds, "number");
            assert.equal(aShare.session, "closed");
            assert.equal(aShare.kline.length, 1);

            const usResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              env,
            );
            assert.equal(usResponse.status, 200);
            const us = await usResponse.json();
            assert.equal(us.volume, 120000);
            assert.equal(us.volume_unit, "share");
            assert.equal(us.source_as_of, "2026-08-22T07:59:00+08:00");
            assert.equal(us.fetched_at, "2026-08-22T08:18:30+08:00");
            assert.equal(us.price, 213);
            assert.equal(us.provider_class, "SCHEDULED_SNAPSHOT");
            assert.equal(us.is_realtime, false);

            const hkResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=hk&code=0700.HK"),
              env,
            );
            assert.equal(hkResponse.status, 200);
            const hk = await hkResponse.json();
            assert.equal(hk.market, "hk");
            assert.equal(hk.volume_unit, "share");
            assert.equal(hk.price, 380.2);
            assert.equal(hk.provider_class, "SCHEDULED_SNAPSHOT");
            assert.equal(hk.is_realtime, false);
            assert.equal(upstreamCalls, 0);
            """
        )

    def test_live_api_keeps_validation_whitelist_rate_limit_and_compatibility_contract(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?live-validation-snapshot")).default;
            const latest = {{
              generated_at: "2026-08-22T08:20:00+08:00",
              snapshot_key: "2026-08-25_2026-08-22_082000.json",
              markets: {{
                a_share: {{ decision: {{ watchlist: [{{ code: "603228" }}] }} }},
                hk: {{ decision: {{ watchlist: [{{ code: "0700.HK" }}] }} }},
                us: {{ decision: {{ watchlist: [{{
                  code: "AAPL",
                  name: "Apple",
                  kline: [],
                  realtime: {{
                    price: 210,
                    change_pct: 2.4,
                    previous_close: 205,
                    volume: 120000,
                    volume_unit: "share",
                    session: "closed",
                    session_label: "非交易时段",
                    source: "Yahoo scheduled quote",
                    source_as_of: "2026-08-22T07:59:00+08:00",
                    fetched_at: "2026-08-22T08:18:30+08:00",
                  }},
                }}] }} }},
              }},
            }};
            const jsonResponse = (payload) => new Response(JSON.stringify(payload), {{
              status: 200,
              headers: {{ "content-type": "application/json" }},
            }});
            let upstreamCalls = 0;
            globalThis.fetch = async () => {{
              upstreamCalls += 1;
              throw new Error("Worker must not fetch a request-time quote upstream");
            }};
            const env = {{
              ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK: "1",
              ASSETS: {{ fetch: async (input) => {{
                const url = new URL(typeof input === "string" ? input : input.url);
                if (url.pathname === "/data/picks/latest.json") return jsonResponse(latest);
                return new Response("missing", {{ status: 404 }});
              }} }},
            }};

            const invalidMarket = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=crypto&code=AAPL"), env,
            );
            assert.equal(invalidMarket.status, 400);
            const invalidMarketPayload = await invalidMarket.json();
            assert.equal(invalidMarketPayload.error, "INVALID_MARKET");
            assert.equal(invalidMarketPayload.contract_version, "live-quote-v1");
            for (const field of ["provider", "provider_class", "data_mode", "session", "session_label", "latency_seconds", "quote_status", "fetched_at", "realtime_guaranteed"]) {{
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
            assert.equal(upstreamCalls, 0);
            const firstPayload = await first.json();
            const secondPayload = await second.json();
            assert.equal(firstPayload.code, "AAPL");
            assert.equal(secondPayload.source_as_of, firstPayload.source_as_of);
            assert.equal(firstPayload.cache_ttl_seconds, 10);
            assert.equal(firstPayload.contract_version, "live-quote-v1");
            assert.equal(firstPayload.provider_class, "SCHEDULED_SNAPSHOT");
            assert.equal(firstPayload.is_realtime, false);
            assert.equal(firstPayload.realtime_guaranteed, false);
            assert.equal(firstPayload.snapshot_as_of, latest.generated_at);
            assert.equal(firstPayload.snapshot_key, latest.snapshot_key);
            assert.notEqual(firstPayload.quote_status, "REALTIME");

            let limiterCalls = 0;
            const limitedEnv = {{
              ...env,
              LIVE_RATE_LIMITER: {{
                async limit({{ key }}) {{
                  limiterCalls += 1;
                  assert.match(key, /:us:AAPL$/);
                  return {{ success: false }};
                }},
              }},
            }};
            const limited = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL", {{
                headers: {{ "cf-connecting-ip": "203.0.113.8" }},
              }}),
              limitedEnv,
            );
            assert.equal(limited.status, 429);
            assert.equal(limited.headers.get("retry-after"), "60");
            const limitedPayload = await limited.json();
            assert.equal(limitedPayload.contract_version, "live-quote-v1");
            assert.equal(limitedPayload.error, "RATE_LIMITED");
            assert.equal(limitedPayload.quote_status, "UNAVAILABLE");
            assert.equal(limitedPayload.provider_class, "SCHEDULED_SNAPSHOT");
            assert.equal(limitedPayload.data_mode, "SCHEDULED_SNAPSHOT");
            assert.equal(limitedPayload.realtime_guaranteed, false);
            assert.equal(limiterCalls, 1);
            assert.equal(upstreamCalls, 0);
            """
        )

    def test_live_api_rejects_reference_prices_without_complete_snapshot_quote_provenance(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?strict-snapshot-provenance")).default;
            const latest = {{
              generated_at: "2026-08-22T08:20:00+08:00",
              snapshot_key: "2026-08-25_2026-08-22_082000.json",
              markets: {{ us: {{ decision: {{ watchlist: [
                {{ code: "AAPL", entry_price: 210, price: 211, kline: [{{ close: 212 }}] }},
                {{ code: "MSFT", realtime: {{ price: 500, fetched_at: "2026-08-22T08:18:30+08:00", volume_unit: "share" }} }},
                {{ code: "GOOG", realtime: {{ price: 190, source_as_of: "2026-08-22T07:59:00+08:00", fetched_at: "2026-08-22T08:18:30+08:00" }} }},
                {{ code: "AMZN", realtime: {{ price: 0, source_as_of: "2026-08-22T07:59:00+08:00", fetched_at: "2026-08-22T08:18:30+08:00", volume_unit: "share" }} }},
              ] }} }} }},
            }};
            let upstreamCalls = 0;
            globalThis.fetch = async () => {{ upstreamCalls += 1; throw new Error("unexpected upstream"); }};
            const env = {{
              ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK: "1",
              ASSETS: {{ async fetch(input) {{
                const url = new URL(typeof input === "string" ? input : input.url);
                return url.pathname === "/data/picks/latest.json"
                  ? new Response(JSON.stringify(latest), {{ headers: {{ "content-type": "application/json" }} }})
                  : new Response("missing", {{ status: 404 }});
              }} }},
            }};

            for (const code of ["AAPL", "MSFT", "GOOG", "AMZN"]) {{
              const response = await worker.fetch(
                new Request(`https://xuangu.alixjd.com/api/live?market=us&code=${{code}}`),
                env,
              );
              assert.equal(response.status, 502, code);
              const payload = await response.json();
              assert.equal(payload.contract_version, "live-quote-v1");
              assert.equal(payload.error, "SNAPSHOT_QUOTE_UNAVAILABLE");
              assert.equal(payload.data_mode, "SCHEDULED_SNAPSHOT");
              assert.equal(payload.provider_class, "SCHEDULED_SNAPSHOT");
              assert.equal(payload.is_realtime, false);
              assert.equal(payload.realtime_guaranteed, false);
              assert.equal(payload.price, null);
            }}
            assert.equal(upstreamCalls, 0);
            """
        )

    def test_live_api_fails_open_on_limiter_binding_error_and_structures_asset_failures(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const worker = (await import({json.dumps(WORKER_URI)} + "?live-failure-contracts")).default;
            const latest = {{
              generated_at: "2026-08-22T08:20:00+08:00",
              snapshot_key: "2026-08-25_2026-08-22_082000.json",
              markets: {{ us: {{ decision: {{ primary: {{
                code: "AAPL",
                realtime: {{
                  price: 210,
                  change_pct: 2.4,
                  previous_close: 205,
                  volume: 120000,
                  volume_unit: "share",
                  session: "closed",
                  source: "Yahoo scheduled quote",
                  source_as_of: "2026-08-22T07:59:00+08:00",
                  fetched_at: "2026-08-22T08:18:30+08:00",
                }},
              }} }} }} }},
            }};
            const validAssets = {{ async fetch() {{
              return new Response(JSON.stringify(latest), {{ headers: {{ "content-type": "application/json" }} }});
            }} }};
            const limiterFailure = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
              {{
                ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK: "1",
                ASSETS: validAssets,
                LIVE_RATE_LIMITER: {{ async limit() {{ throw new Error("binding unavailable"); }} }},
              }},
            );
            assert.equal(limiterFailure.status, 200);
            const limiterPayload = await limiterFailure.json();
            assert.equal(limiterPayload.ok, true);
            assert.equal(limiterPayload.rate_limit_status, "unavailable_fail_open");
            assert.equal(limiterPayload.provider_class, "SCHEDULED_SNAPSHOT");

            for (const assets of [
              {{ async fetch() {{ throw new Error("asset binding unavailable"); }} }},
              {{ async fetch() {{ return new Response("{{broken-json", {{ status: 200 }}); }} }},
              {{ async fetch() {{ return new Response("[]", {{ status: 200 }}); }} }},
            ]) {{
              const response = await worker.fetch(
                new Request("https://xuangu.alixjd.com/api/live?market=us&code=AAPL"),
                {{ ASSETS: assets }},
              );
              assert.equal(response.status, 503);
              const payload = await response.json();
              assert.equal(payload.contract_version, "live-quote-v1");
              assert.equal(payload.error, "LATEST_SNAPSHOT_UNAVAILABLE");
              assert.equal(payload.data_mode, "SCHEDULED_SNAPSHOT");
              assert.equal(payload.provider_class, "SCHEDULED_SNAPSHOT");
              assert.equal(payload.is_realtime, false);
            }}

            const statusFailure = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/status"),
              {{ ASSETS: {{ async fetch() {{ return new Response("not-json"); }} }} }},
            );
            assert.equal(statusFailure.status, 503);
            const statusPayload = await statusFailure.json();
            assert.equal(statusPayload.ok, false);
            assert.equal(statusPayload.error, "API_ASSET_UNAVAILABLE");
            assert.equal(statusPayload.data_mode, "scheduled_snapshot");
            assert.equal(statusPayload.device_dependency, false);
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
              ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK: "1",
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
              new Request("https://xuangu.alixjd.com/api/history?limit=5"),
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
            assert.equal(payload.meta.performance.sample_status, "UNAVAILABLE");
            assert.equal(payload.meta.performance.schema_version, null);
            assert.equal(payload.meta.shadow_ledger.contract_status, "UNAVAILABLE");
            assert.equal(payload.meta.shadow_ledger.raw_count, undefined);
            assert.equal(payload.meta.observation_performance.status, "UNAVAILABLE");
            assert.equal(payload.meta.observation_performance.authorizes_production, false);

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

            manifest.history_evaluation = {{
              schema_version: "history-evaluation-v1",
              performance: {{
                schema_version: "history-performance-v1",
                sample_status: "EARLY_SAMPLE",
                executable_prediction_count: 7,
                pending_settlement_count: 2,
                settled_sample_count: 3,
                invalid_settlement_count: 1,
                missing_outcome_count: 1,
                metrics: {{ mean_net_return: {{ value: 0.025, n: 3 }} }},
              }},
              shadow_ledger: {{
                track: "SHADOW_RESEARCH", raw_count: 9, eligible_count: 4,
                pending_count: 3, settled_count: 1, excluded_count: 5,
                conflict_count: 0, included_in_executable_performance: false,
              }},
              executable_ledger: {{
                track: "EXECUTABLE_MODEL", raw_count: 7, eligible_count: 5,
                pending_count: 2, settled_count: 3, excluded_count: 1,
                conflict_count: 1, included_in_executable_performance: true,
              }},
              observation_performance: {{
                schema_version: "model-observation-performance-v1",
                track: "MODEL_OBSERVATION",
                status: "PENDING_MATURITY",
                prediction_count: 31,
                pending_maturity_count: 17,
                pending_data_count: 3,
                settled_count: 11,
                included_in_shadow_research: false,
                included_in_executable_performance: false,
                authorizes_production: false,
                authorization_status: "DIAGNOSTIC_ONLY_MANUAL_REVIEW_REQUIRED",
              }},
            }};
            const evaluatedResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/history?limit=1"), env,
            );
            const evaluatedPayload = await evaluatedResponse.json();
            assert.equal(evaluatedPayload.history.length, 1);
            assert.equal(evaluatedPayload.meta.executable_prediction_count, 7);
            assert.equal(evaluatedPayload.meta.settled_sample_count, 3);
            assert.equal(evaluatedPayload.meta.performance.metrics.mean_net_return.value, 0.025);
            assert.equal(evaluatedPayload.meta.shadow_ledger.raw_count, 9);
            assert.equal(evaluatedPayload.meta.shadow_ledger.pending_count, 3);
            assert.equal(evaluatedPayload.meta.executable_ledger.settled_count, 3);
            assert.equal(evaluatedPayload.meta.observation_performance.pending_maturity_count, 17);
            assert.equal(evaluatedPayload.meta.observation_performance.pending_data_count, 3);
            assert.equal(evaluatedPayload.meta.observation_performance.settled_count, 11);
            assert.equal(evaluatedPayload.meta.observation_performance.authorizes_production, false);
            assert.deepEqual(evaluatedPayload.history_evaluation, manifest.history_evaluation);
            delete manifest.history_evaluation;

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
              new Request("https://xuangu.alixjd.com/api/history?limit=5"),
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
              new Request("https://xuangu.alixjd.com/api/history?limit=5"),
              env,
            );
            const validPayload = await validResponse.json();
            assert.equal(validPayload.meta.settled_sample_count, 1);
            assert.equal(validPayload.meta.missing_outcome_count, 0);

            const unavailableResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/history?limit=5"),
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
            self.assertEqual(manifest["history_evaluation"]["schema_version"], "history-evaluation-v1")
            self.assertEqual(manifest["history_evaluation"]["performance"]["sample_status"], "NO_SAMPLE")
            self.assertEqual(manifest["shadow_ledger"]["track"], "SHADOW_RESEARCH")
            self.assertEqual(manifest["executable_ledger"]["track"], "EXECUTABLE_MODEL")
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

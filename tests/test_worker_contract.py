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
                    previousClose: 205,
                    regularMarketVolume: 120000,
                    regularMarketTime: 1787148000,
                    marketState: "REGULAR",
                  }},
                  timestamp: [1787148000],
                  indicators: {{ quote: [{{
                    open: [206], high: [212], low: [204], close: [210], volume: [120000],
                  }}] }},
                }}] }} }});
              }}
              throw new Error(`Unexpected URL: ${{url}}`);
            }};
            const env = {{ ASSETS: {{ fetch: async () => new Response("not used") }} }};

            const aResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=a_share&code=603228"),
              env,
            );
            assert.equal(aResponse.status, 200);
            const aShare = await aResponse.json();
            assert.equal(aShare.volume, 1234);
            assert.equal(aShare.volume_unit, "lot");
            assert.ok(aShare.source_as_of);
            assert.match(aShare.fetched_at, /\+08:00$/);

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

            const hkResponse = await worker.fetch(
              new Request("https://xuangu.alixjd.com/api/live?market=hk&code=0700.HK"),
              env,
            );
            assert.equal(hkResponse.status, 200);
            const hk = await hkResponse.json();
            assert.equal(hk.market, "hk");
            assert.equal(hk.volume_unit, "share");
            """
        )


class WorkerAssetBuildTests(unittest.TestCase):
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
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertIn("timeout-minutes: 20", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("node --check src/index.js", workflow)
        self.assertNotIn("Install Serenity skill", workflow)

    def test_obsolete_render_blueprint_files_are_removed(self) -> None:
        for name in ("render.yaml", "runtime.txt", "DEPLOY_RENDER.md"):
            self.assertFalse((ROOT / name).exists(), name)


if __name__ == "__main__":
    unittest.main()

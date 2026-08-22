from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest
import urllib.parse


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-worker.yml"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_deployment.py"
WRANGLER = ROOT / "wrangler.jsonc"


def load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_deployment_under_test", VERIFY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load verify_deployment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot_fixture(*, generated_at: str = "2026-08-21T15:07:00+08:00") -> dict:
    return {
        "generated_at": generated_at,
        "snapshot_key": "2026-08-22_2026-08-21_150700.json",
        "model_version": "model-2026-08-22",
        "schema_version": "selector-snapshot-v2",
        "selector_mode": "legacy_active_v2_dual_low_shadow",
        "target_date": "2026-08-22",
        "signal_date": "2026-08-21",
        "forecast_end_date": "2026-09-04",
        "global_decision": {
            "contract_version": "global-10d-v1",
            "decision_scope": "global_10d",
            "action_basis": "strict_cross_market_gate_v1",
            "action": "NO_VALID_PICK",
        },
        "markets": {
            "a_share": {"decision": {"blocked_candidate": {"code": "603757"}}},
            "hk": {"decision": {"primary": {"code": "0941.HK"}}},
            "us": {"decision": {"primary": {"code": "NTNX"}}},
        },
    }


class WorkflowReliabilityTests(unittest.TestCase):
    def test_workflow_has_source_aware_fallbacks_and_stale_push_guard(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "28 1,2,3,5,6,7,16 * * 1-5"', workflow)
        self.assertIn('cron: "58 13 * * 1-5"', workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("SCHEDULE_GATE_STATUS_URL: https://xuangu.alixjd.com/api/latest", workflow)
        self.assertIn("--adopt-newer-live", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("python scripts/settle_outcomes.py", workflow)
        self.assertLess(
            workflow.index("Generate smart pick snapshot"),
            workflow.index("python scripts/settle_outcomes.py"),
        )
        self.assertLess(
            workflow.index("python scripts/settle_outcomes.py"),
            workflow.index("Prepare immutable snapshot recovery bundle"),
        )
        self.assertIn("AUTOMATION_TRIGGER: ${{ github.event_name }}", workflow)
        self.assertIn("SCHEDULED_SLOT: ${{ steps.schedule_gate.outputs.slot }}", workflow)
        self.assertIn('GENERATION_ATTEMPT="${attempt}" python server.py --once --force', workflow)

    def test_workflow_archives_verified_timestamp_and_optional_ledger_or_fails_red(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("recovery-manifest.json", workflow)
        self.assertIn("ledger_present", workflow)
        self.assertIn("archive ledger_present does not match ledger_files", workflow)
        self.assertIn("immutable archive snapshot sha256", workflow)
        self.assertIn('pathlib.Path("data/outcomes").glob("*.json")', workflow)
        self.assertIn('rglob(pattern)', workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("git worktree add --detach", workflow)
        self.assertIn('rebase origin/main', workflow)
        self.assertIn("Archive push attempt ${attempt}/3", workflow)
        self.assertIn("Archive failed after 3 bounded attempts", workflow)
        self.assertIn("[skip ci]", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("git-auto-commit-action", workflow)

    def test_workflow_uses_least_privilege_jobs_and_full_post_deploy_verifier(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions: {}", workflow)
        deploy_section = workflow[workflow.index("  deploy:") : workflow.index("  archive:")]
        archive_section = workflow[workflow.index("  archive:") :]
        self.assertIn("contents: read", deploy_section)
        self.assertNotIn("contents: write", deploy_section)
        self.assertIn("contents: write", archive_section)
        self.assertLess(workflow.index("npx wrangler deploy"), workflow.index("Verify complete deployed contract"))
        self.assertIn("python scripts/verify_deployment.py public/data/picks/latest.json", workflow)
        self.assertIn("--attempts 8", workflow)
        self.assertIn("--timeout-seconds 15", workflow)

    def test_all_static_requests_run_through_worker_security_contract(self) -> None:
        config = json.loads(WRANGLER.read_text(encoding="utf-8"))
        self.assertIs(config["assets"]["run_worker_first"], True)


class DeploymentVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_verify_module()

    def setUp(self) -> None:
        self.local = snapshot_fixture()
        self.status = {
            key: self.local[key]
            for key in self.module.STATUS_REQUIRED_FIELDS
        } | {"ok": True, "has_latest": True}
        self.latest = dict(self.local)

    def test_matching_status_latest_sha_date_and_global_action_pass(self) -> None:
        self.assertEqual(
            self.module.deployment_mismatches(self.local, self.status, self.latest),
            [],
        )

    def test_mismatch_reports_snapshot_key_and_sha(self) -> None:
        latest = dict(self.latest, snapshot_key="old.json")
        errors = self.module.deployment_mismatches(self.local, self.status, latest)
        self.assertTrue(any("latest.snapshot_key" in error for error in errors))
        self.assertTrue(any("latest.sha256" in error for error in errors))

    def test_polling_retries_with_injected_urls_without_network(self) -> None:
        calls: list[str] = []
        sleeps: list[float] = []
        attempt = {"number": 0}

        def fetch_json(url: str) -> dict:
            calls.append(url)
            if url.endswith("/api/status"):
                attempt["number"] += 1
                if attempt["number"] == 1:
                    return dict(self.status, generated_at="2026-08-21T14:58:00+08:00")
                return self.status
            return self.latest

        result = self.module.poll_deployment(
            self.local,
            base_url="https://selector.example.test/root/",
            attempts=2,
            delay_seconds=0.25,
            fetcher=fetch_json,
            sleeper=sleeps.append,
        )
        self.assertEqual(result["snapshot_key"], self.local["snapshot_key"])
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(
            calls,
            [
                "https://selector.example.test/root/api/status",
                "https://selector.example.test/root/api/latest",
                "https://selector.example.test/root/api/status",
                "https://selector.example.test/root/api/latest",
            ],
        )

    def test_polling_fails_after_bounded_attempts(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "deployment verification failed"):
            self.module.poll_deployment(
                self.local,
                base_url="https://selector.example.test",
                attempts=2,
                delay_seconds=0,
                fetcher=lambda _url: {},
                sleeper=lambda _seconds: None,
            )

    def test_push_guard_adopts_newer_remote_snapshot_and_immutable_file(self) -> None:
        remote = snapshot_fixture(generated_at="2026-08-21T15:08:00+08:00")
        remote["snapshot_key"] = "2026-08-22_2026-08-21_150800.json"
        with tempfile.TemporaryDirectory() as temporary:
            latest_path = pathlib.Path(temporary) / "data" / "picks" / "latest.json"
            latest_path.parent.mkdir(parents=True)
            latest_path.write_text(json.dumps(self.local), encoding="utf-8")
            result = self.module.adopt_newer_remote_snapshot(
                latest_path,
                base_url="https://selector.example.test",
                fetcher=lambda _url: remote,
            )
            self.assertTrue(result["adopted"])
            self.assertEqual(json.loads(latest_path.read_text()), remote)
            immutable = latest_path.parent / remote["snapshot_key"]
            self.assertEqual(json.loads(immutable.read_text()), remote)

    def test_push_guard_preserves_same_timestamp_public_enrichment(self) -> None:
        remote = snapshot_fixture()
        remote["shadow_outcome"] = {
            "schema_version": "shadow-outcome-v1",
            "status": "SETTLED",
        }
        with tempfile.TemporaryDirectory() as temporary:
            latest_path = pathlib.Path(temporary) / "data" / "picks" / "latest.json"
            latest_path.parent.mkdir(parents=True)
            latest_path.write_text(json.dumps(self.local), encoding="utf-8")
            result = self.module.adopt_newer_remote_snapshot(
                latest_path,
                base_url="https://selector.example.test",
                fetcher=lambda _url: remote,
            )
            self.assertTrue(result["adopted"])
            self.assertEqual(json.loads(latest_path.read_text()), remote)

    def test_full_contract_checks_immutable_history_static_https_and_live(self) -> None:
        history_row = {
            "snapshot_key": self.local["snapshot_key"],
            "generated_at": self.local["generated_at"],
            "target_date": self.local["target_date"],
            "signal_date": self.local["signal_date"],
            "global_decision": {"action": "NO_VALID_PICK"},
        }
        history = {
            "ok": True,
            "meta": {"view": "raw", "raw_run_count": 1},
            "history": [history_row],
        }
        live_payloads = {
            "a_share": ("603757", "lot"),
            "hk": ("0941.HK", "share"),
            "us": ("NTNX", "share"),
        }

        def json_fetcher(url: str) -> dict:
            parsed = urllib.parse.urlsplit(url)
            if parsed.path == "/api/status":
                return self.status
            if parsed.path in {"/api/latest", "/api/pick"}:
                return self.latest
            if parsed.path == "/api/history":
                return history
            if parsed.path == "/api/live":
                query = urllib.parse.parse_qs(parsed.query)
                market = query["market"][0]
                code, unit = live_payloads[market]
                return {
                    "contract_version": "live-quote-v1",
                    "ok": True,
                    "market": market,
                    "code": code,
                    "price": 10.0,
                    "provider": "fixture",
                    "provider_class": "PUBLIC_BEST_EFFORT",
                    "source": "fixture quote",
                    "source_as_of": "2026-08-21T15:06:00+08:00",
                    "fetched_at": "2026-08-21T15:07:01+08:00",
                    "volume_unit": unit,
                    "session": "closed",
                    "session_label": "fixture",
                    "price_kind": "last_close",
                    "quote_status": "LAST_CLOSE",
                    "freshness": "last_close",
                    "is_realtime": False,
                    "is_stale": False,
                    "realtime_guaranteed": False,
                    "cache_ttl_seconds": 10,
                    "kline": [],
                }
            raise AssertionError(url)

        html_headers = {
            "content-type": "text/html; charset=utf-8",
            "strict-transport-security": "max-age=31536000; includeSubDomains",
            "x-content-type-options": "nosniff",
            "referrer-policy": "strict-origin-when-cross-origin",
            "permissions-policy": "camera=(), microphone=()",
        }

        def response_fetcher(url: str, follow: bool):
            if url.startswith("http://"):
                self.assertFalse(follow)
                return 308, {"location": "https://selector.example.test/"}, b""
            self.assertTrue(follow)
            body = b'<main id="mainContent"><button id="tab-history"></button><script src="/static/app.js"></script>'
            return 200, html_headers, body

        latest, errors = self.module.full_deployment_errors(
            self.local,
            base_url="https://selector.example.test",
            json_fetcher=json_fetcher,
            response_fetcher=response_fetcher,
        )
        self.assertEqual(latest["snapshot_key"], self.local["snapshot_key"])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

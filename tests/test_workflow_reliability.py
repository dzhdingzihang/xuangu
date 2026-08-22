from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-worker.yml"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_deployment.py"


def load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_deployment_under_test", VERIFY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load verify_deployment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkflowReliabilityTests(unittest.TestCase):
    def test_workflow_has_fallbacks_retries_and_safe_ordering(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "28 1,2,3,5,6,7,16 * * 1-5"', workflow)
        self.assertIn('cron: "58 13 * * 1-5"', workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn("SCHEDULE_GATE_STATUS_URL:", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("AUTOMATION_TRIGGER: ${{ github.event_name }}", workflow)
        self.assertIn("SCHEDULED_SLOT: ${{ steps.schedule_gate.outputs.slot }}", workflow)
        self.assertIn('GENERATION_ATTEMPT="${attempt}" python server.py --once --force', workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("python scripts/verify_deployment.py", workflow)
        self.assertLess(
            workflow.index("npx wrangler deploy"),
            workflow.index("Commit generated snapshot"),
        )

        commit_section = workflow[workflow.index("- name: Commit generated snapshot") :]
        self.assertIn("continue-on-error: true", commit_section)
        self.assertEqual(workflow.count("continue-on-error:"), 1)


class DeploymentVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_verify_module()

    def setUp(self) -> None:
        self.local = {
            "generated_at": "2026-08-21T15:07:00+08:00",
            "snapshot_key": "2026-08-22_2026-08-21_150700.json",
            "model_version": "model-2026-08-22",
            "schema_version": "selector-snapshot-v2",
            "selector_mode": "legacy_active_v2_dual_low_shadow",
        }
        self.status = dict(self.local, ok=True)
        self.latest = dict(self.local, markets={})

    def test_matching_status_and_latest_pass_pure_validation(self) -> None:
        self.assertEqual(
            self.module.deployment_mismatches(self.local, self.status, self.latest),
            [],
        )

    def test_mismatch_reports_endpoint_and_field(self) -> None:
        latest = dict(self.latest, snapshot_key="old.json")
        errors = self.module.deployment_mismatches(self.local, self.status, latest)
        self.assertIn("latest.snapshot_key", errors[0])

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


if __name__ == "__main__":
    unittest.main()

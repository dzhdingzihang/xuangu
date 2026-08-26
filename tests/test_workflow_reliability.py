from __future__ import annotations

import importlib.util
import hashlib
import json
import pathlib
import re
import tempfile
import unittest
import urllib.parse
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-worker.yml"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_deployment.py"
WRANGLER = ROOT / "wrangler.jsonc"
README = ROOT / "README.md"


def load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_deployment_under_test", VERIFY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load verify_deployment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def realtime_fixture(*, price: float = 10.0, volume_unit: str = "share") -> dict:
    return {
        "price": price,
        "change_pct": 1.0,
        "previous_close": round(price / 1.01, 4),
        "volume": 1000,
        "volume_unit": volume_unit,
        "session": "closed",
        "source": "fixture scheduled quote",
        "source_as_of": "2026-08-21T15:06:00+08:00",
        "fetched_at": "2026-08-21T15:07:01+08:00",
    }


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
            "a_share": {
                "decision": {
                    "blocked_candidate": {
                        "code": "603757",
                        "realtime": realtime_fixture(volume_unit="lot"),
                    }
                }
            },
            "hk": {
                "decision": {
                    "primary": {"code": "0941.HK", "realtime": realtime_fixture()}
                }
            },
            "us": {
                "decision": {
                    "primary": {"code": "NTNX", "realtime": realtime_fixture()}
                }
            },
        },
    }


def source_snapshot_fixture(payload: dict) -> tuple[str, int]:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest(), len(content)


def live_payload_fixture(local: dict, market: str, code: str, quote: dict) -> dict:
    source_sha256, source_byte_size = source_snapshot_fixture(local)
    return {
        "contract_version": "live-quote-v1",
        "source_index_contract_version": "worker-live-index-v1",
        "source_snapshot_sha256": source_sha256,
        "source_snapshot_byte_size": source_byte_size,
        "ok": True,
        "data_mode": "SCHEDULED_SNAPSHOT",
        "quote_mode": "SCHEDULED_SNAPSHOT",
        "market": market,
        "code": code,
        "price": quote["price"],
        "provider": "github_actions_snapshot",
        "provider_class": "SCHEDULED_SNAPSHOT",
        "source": quote.get("source") or "fixture scheduled quote",
        "source_as_of": quote["source_as_of"],
        "fetched_at": quote["fetched_at"],
        "volume_unit": quote["volume_unit"],
        "session": quote.get("session") or "closed",
        "session_label": "fixture",
        "price_kind": "last_close",
        "quote_status": "LAST_CLOSE",
        "freshness": "last_close",
        "is_realtime": False,
        "is_stale": False,
        "realtime_guaranteed": False,
        "snapshot_as_of": local["generated_at"],
        "snapshot_key": local["snapshot_key"],
        "rate_limit_status": "enforced",
        "cache_ttl_seconds": 10,
        "kline": [],
    }


class WorkflowReliabilityTests(unittest.TestCase):
    def test_readme_describes_the_device_free_snapshot_schedule_truthfully(self) -> None:
        readme = README.read_text(encoding="utf-8")
        for token in (
            "08:17",
            "10:17",
            "12:17",
            "15:17",
            "16:17",
            "20:17",
            "22:47",
            "08:47",
            "10:47",
            "12:47",
            "15:47",
            "16:47",
            "20:47",
            "23:17",
            "Asia/Shanghai",
            "data_mode=scheduled_snapshot",
            "device_dependency=false",
            "每次定时或手动快照生成任务",
            "不依赖 Render、Futu OpenD、个人电脑",
            "不是 100% 准点保证",
        ):
            with self.subTest(token=token):
                self.assertIn(token, readme)
        self.assertNotIn("每 15 秒", readme)

    def test_workflow_has_source_aware_fallbacks_and_stale_push_guard(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(workflow.count("- cron:"), 14)
        for hour in ("0", "2", "4", "7", "8", "12"):
            self.assertIn(f'cron: "17 {hour} * * 1-5"', workflow)
            self.assertIn(f'cron: "47 {hour} * * 1-5"', workflow)
        self.assertIn('cron: "47 14 * * 1-5"', workflow)
        self.assertIn('cron: "17 15 * * 1-5"', workflow)
        self.assertNotIn('cron: "58 0,1,2,4,5,6,15 * * 1-5"', workflow)
        self.assertNotIn('cron: "28 1,2,3,5,6,7,16 * * 1-5"', workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("SCHEDULE_GATE_STATUS_URL: https://xuangu.alixjd.com/api/latest", workflow)
        self.assertIn("SCHEDULE_GATE_CRON: ${{ github.event.schedule }}", workflow)
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
        self.assertIn(
            "SCHEDULED_INVOCATION_SLOT: ${{ steps.schedule_gate.outputs.invocation_slot }}",
            workflow,
        )
        self.assertIn("python scripts/deployment_order_guard.py data/picks/latest.json", workflow)
        self.assertIn("steps.publish_guard.outputs.should_publish == 'true'", workflow)
        self.assertIn("should_publish: ${{ steps.publish_guard.outputs.should_publish }}", workflow)
        self.assertIn('EVENT_SCAN_CANDIDATES_PER_MARKET: "16"', workflow)
        self.assertIn('GENERATION_ATTEMPT="${attempt}" python server.py --once --force', workflow)
        self.assertIn('python server.py --once --force --quiet', workflow)

    def test_workflow_rotates_long_history_kline_caches_to_v2(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for prefix in ("a-share-d1-v2-", "hk-us-d1-v2-"):
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, workflow)
        for stale_prefix in ("a-share-d1-v1-", "hk-us-d1-v1-"):
            with self.subTest(stale_prefix=stale_prefix):
                self.assertNotIn(stale_prefix, workflow)

    def test_production_configuration_has_no_device_quote_gateway_dependency(self) -> None:
        production_configuration = "\n".join(
            [
                WORKFLOW.read_text(encoding="utf-8"),
                WRANGLER.read_text(encoding="utf-8"),
            ]
        ).lower()
        for forbidden in ("realtime_gateway_url", "xuangu-quotes", "futu_opend"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, production_configuration)
        self.assertFalse((WORKFLOW.parent / "configure-realtime-dns.yml").exists())

    def test_workflow_archives_verified_timestamp_and_optional_ledger_or_fails_red(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("recovery-manifest.json", workflow)
        self.assertIn("ledger_present", workflow)
        self.assertIn("archive ledger_present does not match ledger_files", workflow)
        self.assertIn("immutable archive snapshot sha256", workflow)
        self.assertIn('pathlib.Path("data/outcomes").rglob("*.json")', workflow)
        self.assertIn('rglob(pattern)', workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("Install archive validation dependencies", workflow)
        self.assertIn("git worktree add --detach", workflow)
        self.assertIn('rebase origin/main', workflow)
        self.assertIn("Archive push attempt ${attempt}/3", workflow)
        self.assertIn("Archive failed after 3 bounded attempts", workflow)
        self.assertIn("[skip ci]", workflow)
        self.assertIn("from scripts.snapshot_archive_policy import ARCHIVE_POLICY, archive_reasons", workflow)
        self.assertIn("reasons = archive_reasons(snapshot)", workflow)
        self.assertIn('"archive_reasons": reasons', workflow)
        self.assertIn("if: steps.snapshot_bundle.outcome == 'success'", workflow)
        self.assertIn("needs.deploy.outputs.should_publish != 'false'", workflow)
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

    def test_every_deploy_path_validates_immutable_bundle_before_deploy(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        validation = "python scripts/validate_snapshot.py data/picks/latest.json"
        self.assertIn(validation, workflow)
        self.assertLess(workflow.index(validation), workflow.index("npx wrangler deploy"))
        validation_step = workflow[
            workflow.rindex("- name:", 0, workflow.index(validation)) : workflow.index(validation) + len(validation)
        ]
        self.assertIn(
            "if: github.event_name != 'schedule' || steps.schedule_gate.outputs.should_run == 'true'",
            validation_step,
        )

    def test_failed_post_deploy_verification_rolls_back_exact_previous_version(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        capture = "npx --no-install wrangler deployments status --name xuangu --json"
        deploy = "npx wrangler deploy\n          --message"
        verify = "Verify complete deployed contract"
        rollback = "npx --no-install wrangler rollback"
        for token in (
            capture,
            "id: rollback_target",
            "id: deploy_worker",
            "id: verify_deployment",
            rollback,
            "steps.rollback_target.outputs.version_id",
            "steps.deploy_worker.outcome == 'success'",
            "steps.verify_deployment.outcome == 'failure'",
            "--yes",
            "rollback-target-latest.json",
            "rollback-result-deployment.json",
            "rollback did not restore the exact previous version at 100%",
            "rollback snapshot identity verification failed",
            "snapshot_sha256",
        ):
            with self.subTest(token=token):
                self.assertIn(token, workflow)
        self.assertLess(workflow.index(capture), workflow.index(deploy))
        self.assertLess(workflow.index(deploy), workflow.index(verify))
        self.assertLess(workflow.index(verify), workflow.index(rollback))
        self.assertGreaterEqual(workflow.count("python scripts/verify_deployment.py"), 2)

    def test_all_static_requests_run_through_worker_security_contract(self) -> None:
        config = json.loads(WRANGLER.read_text(encoding="utf-8"))
        self.assertIs(config["assets"]["run_worker_first"], True)


class DeploymentVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_verify_module()

    def setUp(self) -> None:
        self.local = snapshot_fixture()
        self.source_sha256, self.source_byte_size = source_snapshot_fixture(self.local)
        self.status = {
            key: self.local[key]
            for key in self.module.STATUS_REQUIRED_FIELDS
        } | {
            "ok": True,
            "has_latest": True,
            "time": "2026-08-22T10:00:00+08:00",
            "data_mode": "scheduled_snapshot",
            "quote_delivery_mode": "scheduled_snapshot",
            "device_dependency": False,
            "schedule_time_zone": "Asia/Shanghai",
            "schedule_primary_checkpoints": [
                "08:17", "10:17", "12:17", "15:17", "16:17", "20:17", "22:47",
            ],
            "schedule_fallback_checkpoints": [
                "08:47", "10:47", "12:47", "15:47", "16:47", "20:47", "23:17",
            ],
            "snapshot_as_of": self.local["generated_at"],
            "next_refresh": "2026-08-24T08:17:00+08:00",
            "runtime_contract_version": "worker-runtime-v1",
            "source_snapshot_sha256": self.source_sha256,
            "source_snapshot_byte_size": self.source_byte_size,
        }
        self.latest = dict(self.local)

    def test_live_code_normalization_matches_worker_facing_contract(self) -> None:
        cases = {
            ("a_share", "SH600000"): "600000",
            ("a_share", "SZ.600000"): "600000",
            ("a_share", "600000.SH"): "600000",
            ("hk", "700"): "0700.HK",
            ("hk", "00700.HK"): "0700.HK",
            ("us", "BRK.B"): "BRK-B",
            ("us", "BRK_B"): "BRK-B",
        }
        for (market, raw), expected in cases.items():
            with self.subTest(market=market, raw=raw):
                self.assertEqual(self.module._normalize_live_code(market, raw), expected)

    def test_matching_status_latest_sha_date_and_global_action_pass(self) -> None:
        self.assertEqual(
            self.module.deployment_mismatches(self.local, self.status, self.latest),
            [],
        )

    def test_workflow_utc_crons_match_the_verifier_checkpoint_set(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        actual: set[tuple[int, int]] = set()
        for minute, hours in re.findall(r'cron: "(\d+) ([\d,]+) \* \* 1-5"', workflow):
            for hour in hours.split(","):
                local_minutes = (int(hour) * 60 + int(minute) + 8 * 60) % (24 * 60)
                actual.add(divmod(local_minutes, 60))

        self.assertEqual(actual, set(self.module.SCHEDULED_REFRESH_CHECKPOINTS))

    def test_scheduled_snapshot_status_contract_rejects_device_or_live_mode(self) -> None:
        self.assertEqual(
            self.module.scheduled_snapshot_status_errors(self.local, self.status),
            [],
        )
        unsafe = dict(
            self.status,
            data_mode="request_time_live",
            device_dependency=True,
        )
        errors = self.module.scheduled_snapshot_status_errors(self.local, unsafe)
        self.assertTrue(any("data_mode" in error for error in errors))
        self.assertTrue(any("device_dependency" in error for error in errors))

    def test_scheduled_snapshot_status_requires_exact_next_primary_or_fallback_checkpoint(self) -> None:
        wrong = dict(
            self.status,
            next_refresh="2026-08-23T03:02:00+08:00",
        )
        errors = self.module.scheduled_snapshot_status_errors(self.local, wrong)
        self.assertTrue(any("next_refresh" in error and "expected" in error for error in errors))

        after_primary = dict(
            self.status,
            time="2026-08-24T08:18:00+08:00",
            next_refresh="2026-08-24T08:47:00+08:00",
        )
        self.assertEqual(
            self.module.scheduled_snapshot_status_errors(self.local, after_primary),
            [],
        )

        after_fallback = dict(
            self.status,
            time="2026-08-24T08:48:00+08:00",
            next_refresh="2026-08-24T10:17:00+08:00",
        )
        self.assertEqual(
            self.module.scheduled_snapshot_status_errors(self.local, after_fallback),
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
            source_snapshot_sha256=self.source_sha256,
            source_snapshot_byte_size=self.source_byte_size,
            fetcher=fetch_json,
            sleeper=sleeps.append,
        )
        self.assertEqual(result["snapshot_key"], self.local["snapshot_key"])
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(
            calls,
            [
                "https://selector.example.test/root/api/status",
                "https://selector.example.test/root/api/status",
            ],
        )

    def test_polling_fails_after_bounded_attempts(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "deployment verification failed"):
            self.module.poll_deployment(
                self.local,
                base_url="https://selector.example.test",
                attempts=2,
                delay_seconds=0,
                source_snapshot_sha256=self.source_sha256,
                source_snapshot_byte_size=self.source_byte_size,
                fetcher=lambda _url: {},
                sleeper=lambda _seconds: None,
            )

    def test_status_poll_requires_runtime_contract_and_exact_source_identity(self) -> None:
        missing = object()
        cases = (
            ("missing runtime contract", "runtime_contract_version", missing),
            ("wrong runtime contract", "runtime_contract_version", "legacy-runtime-v0"),
            ("missing source hash", "source_snapshot_sha256", missing),
            ("wrong source hash", "source_snapshot_sha256", "0" * 64),
            ("missing source byte size", "source_snapshot_byte_size", missing),
            ("wrong source byte size", "source_snapshot_byte_size", self.source_byte_size + 1),
        )
        for label, field, value in cases:
            calls: list[str] = []
            status = dict(self.status)
            if value is missing:
                status.pop(field)
            else:
                status[field] = value
            with self.subTest(label=label):
                with self.assertRaisesRegex(RuntimeError, field):
                    self.module.poll_deployment(
                        self.local,
                        base_url="https://selector.example.test",
                        attempts=1,
                        delay_seconds=0,
                        source_snapshot_sha256=self.source_sha256,
                        source_snapshot_byte_size=self.source_byte_size,
                        fetcher=lambda url: calls.append(url) or status,
                        sleeper=lambda _seconds: None,
                    )
                self.assertEqual(calls, ["https://selector.example.test/api/status"])

    def test_source_snapshot_identity_uses_exact_input_bytes(self) -> None:
        content = b'{\n  "snapshot_key": "fixture.json"\n}\n'
        self.assertEqual(
            self.module.source_snapshot_identity(content),
            (hashlib.sha256(content).hexdigest(), len(content)),
        )

    def test_full_poll_waits_for_exact_identity_before_running_live_contract(self) -> None:
        local = snapshot_fixture()
        local["production_decision"] = {
            "contract_version": "production-rule-10d-v1",
            "decision_scope": "global_10d",
            "action_basis": "dual_track_candidate_qualification_v3",
            "rule_model_id": "ten-day-audited-rule-ensemble-v3",
            "score_kind": "RULE_QUALIFICATION_SCORE",
            "action": "QUALIFIED_PICK",
            "primary": {"qualification_id": "qual_new"},
        }
        source_sha256, source_byte_size = source_snapshot_fixture(local)
        current_status = dict(
            self.status,
            production_action="QUALIFIED_PICK",
            qualification_id="qual_new",
            calibrated_action="NO_VALID_PICK",
            prediction_id=None,
            source_snapshot_sha256=source_sha256,
            source_snapshot_byte_size=source_byte_size,
        )
        old_status = dict(
            current_status,
            production_action="NO_QUALIFIED_PICK",
            qualification_id=None,
        )
        history = {
            "ok": True,
            "meta": {"view": "raw", "raw_run_count": 1},
            "history": [{
                "snapshot_key": local["snapshot_key"],
                "generated_at": local["generated_at"],
                "target_date": local["target_date"],
                "signal_date": local["signal_date"],
                "global_decision": {"action": "NO_VALID_PICK"},
                "production_decision": {"action": "QUALIFIED_PICK"},
            }],
        }
        calls: list[str] = []
        sleeps: list[float] = []
        status_reads = 0

        def json_fetcher(url: str) -> dict:
            nonlocal status_reads
            parsed = urllib.parse.urlsplit(url)
            calls.append(parsed.path)
            if parsed.path == "/api/status":
                status_reads += 1
                return old_status if status_reads <= 2 else current_status
            if parsed.path == "/api/latest":
                return local
            if parsed.path == "/api/pick":
                return local
            if parsed.path == "/api/history":
                return history
            if parsed.path == "/api/live":
                query = urllib.parse.parse_qs(parsed.query)
                market = query["market"][0]
                decision = local["markets"][market]["decision"]
                candidate = decision.get("primary") or decision.get("blocked_candidate")
                return live_payload_fixture(
                    local,
                    market,
                    candidate["code"],
                    candidate["realtime"],
                )
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
                return 308, {"location": "https://selector.example.test/"}, b""
            body = b'<main id="mainContent"><button id="tab-history"></button><script src="/static/app.js"></script>'
            return 200, html_headers, body

        result = self.module.poll_full_deployment(
            local,
            base_url="https://selector.example.test",
            attempts=4,
            delay_seconds=0.25,
            source_snapshot_sha256=source_sha256,
            source_snapshot_byte_size=source_byte_size,
            json_fetcher=json_fetcher,
            response_fetcher=response_fetcher,
            sleeper=sleeps.append,
        )

        self.assertEqual(result["snapshot_key"], local["snapshot_key"])
        self.assertEqual(sleeps, [0.25, 0.25])
        self.assertEqual(
            calls[:5],
            ["/api/status"] * 4 + ["/api/latest"],
        )
        first_live = calls.index("/api/live")
        self.assertNotIn("/api/live", calls[:first_live])

    def test_full_poll_retries_final_contract_with_a_bounded_live_budget(self) -> None:
        local = snapshot_fixture()
        local["markets"]["a_share"]["decision"]["watchlist"] = [
            {
                "code": f"{600000 + index:06d}",
                "realtime": realtime_fixture(volume_unit="lot"),
            }
            for index in range(23)
        ]
        source_sha256, source_byte_size = source_snapshot_fixture(local)
        current_status = dict(
            self.status,
            source_snapshot_sha256=source_sha256,
            source_snapshot_byte_size=source_byte_size,
        )
        full_attempts: list[int] = []

        def json_fetcher(url: str) -> dict:
            if url.endswith("/api/status"):
                return current_status
            if url.endswith("/api/latest"):
                return local
            raise AssertionError(url)

        def transient_failure(*_args, **_kwargs):
            full_attempts.append(1)
            return local, ["transient final-contract failure"]

        with mock.patch.object(self.module, "full_deployment_errors", side_effect=transient_failure):
            with self.assertRaisesRegex(RuntimeError, "full deployment verification failed"):
                self.module.poll_full_deployment(
                    local,
                    base_url="https://selector.example.test",
                    attempts=8,
                    delay_seconds=0,
                    source_snapshot_sha256=source_sha256,
                    source_snapshot_byte_size=source_byte_size,
                    json_fetcher=json_fetcher,
                    response_fetcher=lambda _url, _follow: (200, {}, b""),
                    sleeper=lambda _seconds: None,
                )

        self.assertEqual(len(full_attempts), 3)

    def test_candidate_union_over_90_fails_before_any_remote_request(self) -> None:
        local = snapshot_fixture()
        local["markets"] = {
            "a_share": {
                "decision": {
                    "watchlist": [
                        {
                            "code": f"{600000 + index:06d}",
                            "realtime": realtime_fixture(volume_unit="lot"),
                        }
                        for index in range(91)
                    ]
                }
            },
            "hk": {"decision": {"watchlist": []}},
            "us": {"decision": {"watchlist": []}},
        }
        source_sha256, source_byte_size = source_snapshot_fixture(local)
        calls: list[str] = []
        with self.assertRaisesRegex(ValueError, "91 > 90"):
            self.module.poll_full_deployment(
                local,
                base_url="https://selector.example.test",
                attempts=8,
                delay_seconds=0,
                source_snapshot_sha256=source_sha256,
                source_snapshot_byte_size=source_byte_size,
                json_fetcher=lambda url: calls.append(url) or {},
                response_fetcher=lambda _url, _follow: (200, {}, b""),
                sleeper=lambda _seconds: None,
            )
        self.assertEqual(calls, [])

    def test_fetch_json_non_2xx_reports_bounded_body_and_cf_ray(self) -> None:
        body = ("服务不可用:" + "x" * 1000 + "TAIL_MUST_NOT_LEAK").encode("utf-8")
        with mock.patch.object(
            self.module,
            "fetch_response",
            return_value=(503, {"CF-Ray": "abc123-SIN"}, body),
        ):
            with self.assertRaises(OSError) as captured:
                self.module.fetch_json("https://selector.example.test/api/status")

        message = str(captured.exception)
        self.assertIn("returned HTTP 503", message)
        self.assertIn("cf-ray=abc123-SIN", message)
        self.assertIn("服务不可用", message)
        self.assertNotIn("TAIL_MUST_NOT_LEAK", message)
        self.assertLess(len(message), 800)

    def test_push_guard_adopts_newer_remote_snapshot_and_immutable_file(self) -> None:
        remote = snapshot_fixture(generated_at="2026-08-21T15:08:00+08:00")
        remote["snapshot_key"] = "2026-08-22_2026-08-21_150800.json"
        requested_urls: list[str] = []

        def fetcher(url: str) -> dict:
            requested_urls.append(url)
            return remote

        with tempfile.TemporaryDirectory() as temporary:
            latest_path = pathlib.Path(temporary) / "data" / "picks" / "latest.json"
            latest_path.parent.mkdir(parents=True)
            latest_path.write_text(json.dumps(self.local), encoding="utf-8")
            result = self.module.adopt_newer_remote_snapshot(
                latest_path,
                base_url="https://selector.example.test",
                fetcher=fetcher,
            )
            self.assertTrue(result["adopted"])
            self.assertEqual(
                requested_urls,
                ["https://selector.example.test/data/picks/latest.json"],
            )
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

    def test_live_verifier_rejects_realtime_claim_and_snapshot_identity_mismatch(self) -> None:
        quote = self.local["markets"]["us"]["decision"]["primary"]["realtime"]

        def fetcher(url: str) -> dict:
            parsed = urllib.parse.urlsplit(url)
            market = urllib.parse.parse_qs(parsed.query)["market"][0]
            section = self.local["markets"][market]["decision"]
            candidate = section.get("primary") or section.get("blocked_candidate")
            payload = live_payload_fixture(self.local, market, candidate["code"], candidate["realtime"])
            if market == "us":
                payload["quote_status"] = "REALTIME"
                payload["snapshot_as_of"] = "2026-08-21T14:59:00+08:00"
                payload["snapshot_key"] = "old.json"
            return payload

        errors = self.module.live_contract_errors(
            self.local,
            base_url="https://selector.example.test",
            fetcher=fetcher,
            source_snapshot_sha256=self.source_sha256,
            source_snapshot_byte_size=self.source_byte_size,
        )
        self.assertTrue(any("quote_status" in error and "REALTIME" in error for error in errors))
        self.assertTrue(any("snapshot_as_of" in error for error in errors))
        self.assertTrue(any("snapshot_key" in error for error in errors))
        self.assertEqual(quote["price"], 10.0)

    def test_live_verifier_covers_all_normalized_candidates_and_allows_empty_markets(self) -> None:
        local = snapshot_fixture()
        local["markets"]["a_share"] = {"decision": {"watchlist": []}}
        hk_primary = {"code": "700.HK", "realtime": realtime_fixture(price=380.0)}
        hk_watch = {"code": "0005.HK", "realtime": realtime_fixture(price=80.0)}
        local["markets"]["hk"] = {
            "decision": {
                "primary": hk_primary,
                "watchlist": [hk_primary, hk_watch],
            }
        }
        local["markets"]["us"] = {"decision": {"watchlist": []}}
        local["global_decision"]["research_priority"] = {
            "market": "us",
            "code": "msft",
            "realtime": realtime_fixture(price=500.0),
        }
        expected = {
            ("hk", "0700.HK"): hk_primary["realtime"],
            ("hk", "0005.HK"): hk_watch["realtime"],
            ("us", "MSFT"): local["global_decision"]["research_priority"]["realtime"],
        }
        calls: list[tuple[str, str]] = []

        def fetcher(url: str) -> dict:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            key = (query["market"][0], query["code"][0])
            calls.append(key)
            return live_payload_fixture(local, key[0], key[1], expected[key])

        errors = self.module.live_contract_errors(
            local,
            base_url="https://selector.example.test",
            fetcher=fetcher,
            source_snapshot_sha256=source_snapshot_fixture(local)[0],
            source_snapshot_byte_size=source_snapshot_fixture(local)[1],
        )
        self.assertEqual(errors, [])
        self.assertEqual(calls, [("hk", "0700.HK"), ("hk", "0005.HK"), ("us", "MSFT")])

    def test_live_verifier_includes_secondary_production_qualified_candidate(self) -> None:
        local = snapshot_fixture()
        local["markets"] = {
            market: {"decision": {"watchlist": []}}
            for market in ("a_share", "hk", "us")
        }
        local["global_decision"].pop("primary", None)
        local["global_decision"].pop("research_priority", None)
        primary = {
            "market": "us",
            "code": "VZ",
            "candidate_snapshot": {
                "code": "VZ",
                "realtime": realtime_fixture(price=50.0),
            },
        }
        secondary = {
            "market": "hk",
            "code": "1919.HK",
            "candidate_snapshot": {
                "code": "1919.HK",
                "realtime": realtime_fixture(price=13.0),
            },
        }
        local["production_decision"] = {
            "action": "QUALIFIED_PICK",
            "primary": primary,
            "qualified_candidates": [primary, secondary],
        }
        source_sha256, source_byte_size = source_snapshot_fixture(local)
        expected = {
            ("hk", "1919.HK"): secondary["candidate_snapshot"]["realtime"],
            ("us", "VZ"): primary["candidate_snapshot"]["realtime"],
        }
        calls: list[tuple[str, str]] = []

        def fetcher(url: str) -> dict:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            key = (query["market"][0], query["code"][0])
            calls.append(key)
            return live_payload_fixture(local, key[0], key[1], expected[key])

        errors = self.module.live_contract_errors(
            local,
            base_url="https://selector.example.test",
            fetcher=fetcher,
            source_snapshot_sha256=source_sha256,
            source_snapshot_byte_size=source_byte_size,
        )
        self.assertEqual(errors, [])
        self.assertEqual(calls, [("hk", "1919.HK"), ("us", "VZ")])

    def test_live_verifier_requires_live_index_contract_and_source_identity(self) -> None:
        source_sha256, source_byte_size = source_snapshot_fixture(self.local)

        def fetcher(url: str) -> dict:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            market = query["market"][0]
            decision = self.local["markets"][market]["decision"]
            candidate = decision.get("primary") or decision.get("blocked_candidate")
            payload = live_payload_fixture(
                self.local,
                market,
                candidate["code"],
                candidate["realtime"],
            )
            if market == "us":
                payload["source_index_contract_version"] = "legacy-live-index-v0"
                payload["source_snapshot_sha256"] = "0" * 64
                payload["source_snapshot_byte_size"] = source_byte_size + 1
            return payload

        errors = self.module.live_contract_errors(
            self.local,
            base_url="https://selector.example.test",
            fetcher=fetcher,
            source_snapshot_sha256=source_sha256,
            source_snapshot_byte_size=source_byte_size,
        )
        self.assertTrue(any("source_index_contract_version" in error for error in errors))
        self.assertTrue(any("source_snapshot_sha256" in error for error in errors))
        self.assertTrue(any("source_snapshot_byte_size" in error for error in errors))

    def test_live_verifier_rejects_candidate_without_complete_realtime_quote(self) -> None:
        local = snapshot_fixture()
        local["markets"]["a_share"] = {"decision": {"watchlist": []}}
        local["markets"]["hk"] = {"decision": {"watchlist": []}}
        local["markets"]["us"] = {
            "decision": {"primary": {"code": "AAPL", "entry_price": 210}}
        }
        calls: list[str] = []
        errors = self.module.live_contract_errors(
            local,
            base_url="https://selector.example.test",
            fetcher=lambda url: calls.append(url) or {},
            source_snapshot_sha256=source_snapshot_fixture(local)[0],
            source_snapshot_byte_size=source_snapshot_fixture(local)[1],
        )
        self.assertTrue(any("realtime" in error for error in errors))
        self.assertEqual(calls, [])

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
        live_mode = {"provider_class": "SCHEDULED_SNAPSHOT"}

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
                decision = self.local["markets"][market]["decision"]
                candidate = decision.get("primary") or decision.get("blocked_candidate")
                payload = live_payload_fixture(
                    self.local,
                    market,
                    candidate["code"],
                    candidate["realtime"],
                )
                payload["provider_class"] = live_mode["provider_class"]
                return payload
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
            source_snapshot_sha256=self.source_sha256,
            source_snapshot_byte_size=self.source_byte_size,
        )
        self.assertEqual(latest["snapshot_key"], self.local["snapshot_key"])
        self.assertEqual(errors, [])

        live_mode["provider_class"] = "PUBLIC_BEST_EFFORT"
        _latest, mode_errors = self.module.full_deployment_errors(
            self.local,
            base_url="https://selector.example.test",
            json_fetcher=json_fetcher,
            response_fetcher=response_fetcher,
            source_snapshot_sha256=self.source_sha256,
            source_snapshot_byte_size=self.source_byte_size,
        )
        self.assertTrue(any("provider_class" in error for error in mode_errors))


if __name__ == "__main__":
    unittest.main()

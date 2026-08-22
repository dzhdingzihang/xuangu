from __future__ import annotations

import datetime as dt
import importlib.util
import io
import os
import pathlib
import unittest
from contextlib import redirect_stdout
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "schedule_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("schedule_gate_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load schedule_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScheduleGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_friday_2358_slot_survives_saturday_delay(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-22T00:21:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T23:58:00+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(now, slot))

    def test_four_hour_window_is_inclusive_and_bounded(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T23:58:00+08:00")
        at_limit = dt.datetime.fromisoformat("2026-08-22T03:58:00+08:00")
        after_limit = dt.datetime.fromisoformat("2026-08-22T03:58:01+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(at_limit, slot))
        self.assertFalse(self.module.checkpoint_is_within_window(after_limit, slot))

    def test_regular_weekday_slot_is_selected(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-21T15:26:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T14:58:00+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(now, slot))

    def test_weekend_without_recent_checkpoint_is_rejected(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-22T12:00:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T23:58:00+08:00")
        self.assertFalse(self.module.checkpoint_is_within_window(now, slot))

    def test_latest_snapshot_makes_fallback_idempotent(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T14:58:00+08:00")
        self.assertTrue(
            self.module.snapshot_covers_checkpoint(
                {"generated_at": "2026-08-21T15:07:00+08:00"},
                slot,
            )
        )
        self.assertFalse(
            self.module.snapshot_covers_checkpoint(
                {"generated_at": "2026-08-21T14:57:59+08:00"},
                slot,
            )
        )
        self.assertFalse(self.module.snapshot_covers_checkpoint({}, slot))

    def test_live_snapshot_is_checked_before_local_snapshot(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T14:58:00+08:00")
        calls: list[str] = []

        def load_url(url: str) -> dict:
            calls.append(f"url:{url}")
            return {"generated_at": "2026-08-21T15:04:00+08:00"}

        def load_path(path: pathlib.Path) -> dict:
            calls.append(f"path:{path}")
            return {"generated_at": "2026-08-21T15:05:00+08:00"}

        source = self.module.published_checkpoint_source(
            slot,
            status_url="https://example.test/api/status",
            latest_path=pathlib.Path("data/picks/latest.json"),
            url_loader=load_url,
            path_loader=load_path,
        )
        self.assertEqual(source, "live")
        self.assertEqual(calls, ["url:https://example.test/api/status"])

    def test_local_snapshot_is_used_when_live_check_fails(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T14:58:00+08:00")

        def fail_url(_url: str) -> dict:
            raise OSError("offline")

        source = self.module.published_checkpoint_source(
            slot,
            status_url="https://example.test/api/status",
            latest_path=pathlib.Path("data/picks/latest.json"),
            url_loader=fail_url,
            path_loader=lambda _path: {"generated_at": "2026-08-21T15:03:00+08:00"},
        )
        self.assertEqual(source, "local")

    def test_fallback_retries_snapshot_with_recoverable_a_share_source_failure(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T14:58:00+08:00")
        degraded = {
            "generated_at": "2026-08-21T15:03:00+08:00",
            "markets": {
                "a_share": {
                    "quote_health": {
                        "status": "unavailable",
                        "requested_count": 96,
                        "quote_count": 0,
                        "quote_coverage": 0.0,
                        "reason_codes": ["TENCENT_QUOTE_UNAVAILABLE"],
                    },
                    "pool_health": {
                        "status": "degraded",
                        "reason_codes": ["QUOTE_COVERAGE_BELOW_MINIMUM"],
                    },
                }
            },
        }
        self.assertIn(
            "TENCENT_QUOTE_UNAVAILABLE",
            self.module.snapshot_data_source_recovery_reasons(degraded),
        )
        source = self.module.published_checkpoint_source(
            slot,
            status_url="https://example.test/api/latest",
            latest_path=pathlib.Path("data/picks/latest.json"),
            url_loader=lambda _url: degraded,
            path_loader=lambda _path: degraded,
        )
        self.assertIsNone(source)

    def test_structural_model_blockers_do_not_cause_endless_fallback(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T14:58:00+08:00")
        structurally_blocked = {
            "generated_at": "2026-08-21T15:03:00+08:00",
            "data_health": {
                "blocker_codes": [
                    "TEN_DAY_PROBABILITY_UNCALIBRATED",
                    "EXTERNAL_EVIDENCE_MISSING",
                ]
            },
            "markets": {
                "a_share": {
                    "quote_health": {
                        "status": "available",
                        "requested_count": 96,
                        "quote_count": 96,
                        "quote_coverage": 1.0,
                        "reason_codes": [],
                    },
                    "pool_health": {"status": "healthy", "reason_codes": []},
                },
                "hk": {"stats": {"raw_pool_size": 153, "scored_size": 62}},
                "us": {"stats": {"raw_pool_size": 258, "scored_size": 246}},
            },
        }
        self.assertEqual(
            self.module.snapshot_data_source_recovery_reasons(structurally_blocked),
            [],
        )
        source = self.module.published_checkpoint_source(
            slot,
            status_url="https://example.test/api/latest",
            latest_path=None,
            url_loader=lambda _url: structurally_blocked,
        )
        self.assertEqual(source, "live")

    def test_hk_or_us_empty_scoring_is_recoverable(self) -> None:
        snapshot = {
            "markets": {
                "hk": {"stats": {"raw_pool_size": 153, "scored_size": 0}},
                "us": {"stats": {"raw_pool_size": 258, "scored_size": 100}},
            }
        }
        self.assertEqual(
            self.module.snapshot_data_source_recovery_reasons(snapshot),
            ["HK_SCORING_EMPTY"],
        )

    def test_hk_yahoo_source_failure_is_recoverable(self) -> None:
        snapshot = {
            "markets": {
                "hk": {
                    "quote_health": {
                        "status": "unavailable",
                        "requested_count": 153,
                        "quote_count": 0,
                        "quote_coverage": 0.0,
                        "reason_codes": ["YAHOO_QUOTE_UNAVAILABLE"],
                    },
                    "stats": {"raw_pool_size": 153, "scored_size": 0},
                }
            }
        }
        reasons = self.module.snapshot_data_source_recovery_reasons(snapshot)
        self.assertIn("HK_QUOTE_UNAVAILABLE", reasons)
        self.assertIn("YAHOO_QUOTE_UNAVAILABLE", reasons)
        self.assertIn("HK_SCORING_EMPTY", reasons)

    def test_main_emits_machine_readable_scheduled_slot(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "SCHEDULE_GATE_NOW": "2026-08-22T00:21:00+08:00",
                    "SCHEDULE_GATE_STATUS_URL": "",
                    "SCHEDULE_GATE_LATEST_PATH": "",
                },
                clear=False,
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(self.module.main(), 0)
        self.assertIn("should_run=true", output.getvalue())
        self.assertIn("slot=2026-08-21T23:58+08:00", output.getvalue())


if __name__ == "__main__":
    unittest.main()

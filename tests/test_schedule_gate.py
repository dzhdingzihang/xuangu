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


def healthy_snapshot(generated_at: str = "2026-08-21T08:25:00+08:00") -> dict:
    return {
        "generated_at": generated_at,
        "markets": {
            market: {
                "quote_health": {
                    "status": "available",
                    "requested_count": 1,
                    "quote_count": 1,
                    "quote_coverage": 1.0,
                    "reason_codes": [],
                },
                "stats": {"raw_pool_size": 1, "scored_size": 1},
            }
            for market in ("a_share", "hk", "us")
        },
    }


class ScheduleGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_business_slots_are_two_primary_checkpoints_only(self) -> None:
        self.assertEqual(self.module.SLOTS, [(8, 17), (20, 17)])

    def test_friday_2017_slot_survives_saturday_delay(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-22T00:00:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T20:17:00+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(now, slot))

    def test_four_hour_window_is_inclusive_and_bounded(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T20:17:00+08:00")
        at_limit = dt.datetime.fromisoformat("2026-08-22T00:17:00+08:00")
        after_limit = dt.datetime.fromisoformat("2026-08-22T00:17:01+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(at_limit, slot))
        self.assertFalse(self.module.checkpoint_is_within_window(after_limit, slot))

    def test_regular_weekday_slot_is_selected(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-21T20:26:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T20:17:00+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(now, slot))

    def test_weekend_without_recent_checkpoint_is_rejected(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-22T12:00:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T20:17:00+08:00")
        self.assertFalse(self.module.checkpoint_is_within_window(now, slot))

    def test_latest_snapshot_makes_fallback_idempotent(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T08:17:00+08:00")
        self.assertTrue(
            self.module.snapshot_covers_checkpoint(
                {"generated_at": "2026-08-21T08:25:00+08:00"},
                slot,
            )
        )
        self.assertFalse(
            self.module.snapshot_covers_checkpoint(
                {"generated_at": "2026-08-21T08:16:59+08:00"},
                slot,
            )
        )
        self.assertFalse(self.module.snapshot_covers_checkpoint({}, slot))

    def test_healthy_live_snapshot_suppresses_recovery(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T08:17:00+08:00")
        calls: list[str] = []

        def load_url(url: str) -> dict:
            calls.append(f"url:{url}")
            return healthy_snapshot("2026-08-21T08:24:00+08:00")

        source = self.module.published_checkpoint_source(
            slot,
            status_url="https://example.test/api/status",
            url_loader=load_url,
        )
        self.assertEqual(source, "live")
        self.assertEqual(calls, ["url:https://example.test/api/status"])

    def test_live_check_failure_never_suppresses_recovery(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T08:17:00+08:00")

        def fail_url(_url: str) -> dict:
            raise OSError("offline")

        source = self.module.published_checkpoint_source(
            slot,
            status_url="https://example.test/api/status",
            url_loader=fail_url,
        )
        self.assertIsNone(source)

    def test_stale_or_degraded_live_state_never_suppresses_recovery(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T08:17:00+08:00")
        cases = {
            "stale": healthy_snapshot("2026-08-21T08:16:59+08:00"),
            "degraded": {
                **healthy_snapshot(),
                "markets": {
                    **healthy_snapshot()["markets"],
                    "hk": {
                        "quote_health": {
                            "status": "unavailable",
                            "requested_count": 1,
                            "quote_count": 0,
                            "quote_coverage": 0.0,
                            "reason_codes": ["YAHOO_QUOTE_UNAVAILABLE"],
                        },
                        "stats": {"raw_pool_size": 1, "scored_size": 0},
                    },
                },
            },
        }
        for label, live_snapshot in cases.items():
            with self.subTest(label=label):
                source = self.module.published_checkpoint_source(
                    slot,
                    status_url="https://example.test/api/latest",
                    url_loader=lambda _url, payload=live_snapshot: payload,
                )
                self.assertIsNone(source)

    def test_missing_market_or_quote_health_is_recoverable_unknown_state(self) -> None:
        cases = {
            "markets_missing": ({"generated_at": "2026-08-21T08:25:00+08:00"}, "MARKETS_MISSING_OR_INVALID"),
            "market_missing": (
                {
                    **healthy_snapshot(),
                    "markets": {
                        key: value
                        for key, value in healthy_snapshot()["markets"].items()
                        if key != "us"
                    },
                },
                "US_MARKET_MISSING_OR_INVALID",
            ),
            "quote_health_missing": (
                {
                    **healthy_snapshot(),
                    "markets": {
                        **healthy_snapshot()["markets"],
                        "hk": {"stats": {"raw_pool_size": 1, "scored_size": 1}},
                    },
                },
                "HK_QUOTE_HEALTH_UNKNOWN",
            ),
        }
        for label, (snapshot, expected) in cases.items():
            with self.subTest(label=label):
                self.assertIn(
                    expected,
                    self.module.snapshot_data_source_recovery_reasons(snapshot),
                )

    def test_fallback_retries_snapshot_with_recoverable_a_share_source_failure(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T08:17:00+08:00")
        degraded = {
            "generated_at": "2026-08-21T08:25:00+08:00",
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
            url_loader=lambda _url: degraded,
        )
        self.assertIsNone(source)

    def test_structural_model_blockers_do_not_cause_endless_fallback(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T08:17:00+08:00")
        structurally_blocked = {
            "generated_at": "2026-08-21T08:25:00+08:00",
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
        for market in ("hk", "us"):
            structurally_blocked["markets"][market]["quote_health"] = {
                "status": "available",
                "requested_count": structurally_blocked["markets"][market]["stats"]["raw_pool_size"],
                "quote_count": structurally_blocked["markets"][market]["stats"]["raw_pool_size"],
                "quote_coverage": 1.0,
                "reason_codes": [],
            }
        self.assertEqual(
            self.module.snapshot_data_source_recovery_reasons(structurally_blocked),
            [],
        )
        source = self.module.published_checkpoint_source(
            slot,
            status_url="https://example.test/api/latest",
            url_loader=lambda _url: structurally_blocked,
        )
        self.assertEqual(source, "live")

    def test_hk_or_us_empty_scoring_is_recoverable(self) -> None:
        snapshot = {
            "markets": {
                **healthy_snapshot()["markets"],
                "hk": {
                    "quote_health": healthy_snapshot()["markets"]["hk"]["quote_health"],
                    "stats": {"raw_pool_size": 153, "scored_size": 0},
                },
                "us": {
                    "quote_health": healthy_snapshot()["markets"]["us"]["quote_health"],
                    "stats": {"raw_pool_size": 258, "scored_size": 100},
                },
            }
        }
        self.assertEqual(
            self.module.snapshot_data_source_recovery_reasons(snapshot),
            ["HK_SCORING_EMPTY"],
        )

    def test_hk_yahoo_source_failure_is_recoverable(self) -> None:
        snapshot = {
            "markets": {
                **healthy_snapshot()["markets"],
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

    def test_0847_fallback_skips_a_healthy_0817_snapshot(self) -> None:
        output = self._run_main("2026-08-21T08:47:00+08:00", published_source="live")

        self.assertIn("should_run=false", output)
        self.assertIn("reason=slot_already_published", output)
        self.assertIn("slot=2026-08-21T08:17+08:00", output)

    def test_0847_fallback_retries_a_degraded_0817_snapshot(self) -> None:
        output = self._run_main("2026-08-21T08:47:00+08:00", published_source=None)

        self.assertIn("should_run=true", output)
        self.assertIn("slot=2026-08-21T08:17+08:00", output)

    def test_2047_fallback_is_not_suppressed_by_a_healthy_morning_snapshot(self) -> None:
        output = self._run_main("2026-08-21T20:47:00+08:00", published_source=None)

        self.assertIn("should_run=true", output)
        self.assertIn("slot=2026-08-21T20:17+08:00", output)

    def _run_main(self, now: str, *, published_source: str | None) -> str:
        output = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "SCHEDULE_GATE_NOW": now,
                    "SCHEDULE_GATE_STATUS_URL": "https://example.test/api/latest",
                },
                clear=False,
            ),
            mock.patch.object(
                self.module,
                "published_checkpoint_source",
                return_value=published_source,
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(self.module.main(), 0)
        return output.getvalue()


if __name__ == "__main__":
    unittest.main()

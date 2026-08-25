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
    targets = {"a_share": 300, "hk": 200, "us": 300}
    snapshot = {
        "generated_at": generated_at,
        "universe_version": "recall-v2-5-dynamic-hk-us",
        "markets": {
            market: {
                "quote_health": {
                    "status": "available",
                    "requested_count": targets[market],
                    "quote_count": targets[market],
                    "realtime_count": targets[market],
                    "quote_coverage": 1.0,
                    "realtime_coverage": 1.0,
                    "reason_codes": [],
                },
                "stats": {
                    "raw_pool_size": targets[market],
                    "scored_size": 1,
                    "recall_target": targets[market],
                    "recall_selected_size": targets[market],
                },
            }
            for market in ("a_share", "hk", "us")
        },
    }
    snapshot["markets"]["a_share"]["stats"]["board_counts"] = {
        "sh_main": 90,
        "sz_main": 75,
        "chinext": 75,
        "star": 60,
    }
    snapshot["markets"]["a_share"]["stats"].update(
        {
            "base_scored_size": 300,
            "technical_attempted_size": 300,
            "technical_scored_size": 300,
            "technical_kline_complete_size": 300,
            "technical_kline_coverage": 1.0,
            "deep_score_limit": 300,
            "deep_eligible_size": 300,
            "deep_attempted_size": 300,
            "deep_scored_size": 300,
            "deep_kline_coverage": 1.0,
        }
    )
    for market in ("hk", "us"):
        target = targets[market]
        minimum = 210 if market == "hk" else 315
        snapshot["markets"][market]["quote_health"].update(
            {
                "stale_realtime_count": 0,
                "freshness_policy": "latest_exchange_session_v1",
                "freshness_reference_session": "2026-08-20",
            }
        )
        snapshot["markets"][market]["pool_health"] = {
            "status": "healthy",
            "reason_codes": [],
            "target_count": target,
            "selected_count": target,
        }
        snapshot["markets"][market]["stats"].update(
            {
                "universe_origin": "dynamic_market_snapshot",
                "discovery_pagination_complete": True,
                "eligible_discovery_size": minimum + 20,
                "selected_source_fresh_count": target,
                "selected_source_fresh_coverage": 1.0,
                "recall_manifest": [
                    {"symbol": f"{index + 1:04d}.HK" if market == "hk" else f"US{index + 1:03d}"}
                    for index in range(target)
                ],
                "deep_scored_size": target,
                "scored_size": target,
            }
        )
    return snapshot


class ScheduleGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_business_slots_cover_all_seven_primary_checkpoints(self) -> None:
        self.assertEqual(
            self.module.SLOTS,
            [
                (8, 17),
                (10, 17),
                (12, 17),
                (15, 17),
                (16, 17),
                (20, 17),
                (22, 47),
            ],
        )

    def test_friday_2247_slot_survives_saturday_delay(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-22T00:00:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T22:47:00+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(now, slot))

    def test_four_hour_window_is_inclusive_and_bounded(self) -> None:
        slot = dt.datetime.fromisoformat("2026-08-21T22:47:00+08:00")
        at_limit = dt.datetime.fromisoformat("2026-08-22T02:47:00+08:00")
        after_limit = dt.datetime.fromisoformat("2026-08-22T02:47:01+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(at_limit, slot))
        self.assertFalse(self.module.checkpoint_is_within_window(after_limit, slot))

    def test_regular_weekday_slot_is_selected(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-21T20:26:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T20:17:00+08:00")
        self.assertTrue(self.module.checkpoint_is_within_window(now, slot))

    def test_delayed_primary_and_fallback_keep_distinct_logical_invocations(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-26T00:00:00+08:00")
        primary = self.module.select_cron_invocation(now, "47 14 * * 1-5")
        fallback = self.module.select_cron_invocation(now, "17 15 * * 1-5")

        self.assertEqual(primary.isoformat(), "2026-08-25T22:47:00+08:00")
        self.assertEqual(fallback.isoformat(), "2026-08-25T23:17:00+08:00")
        self.assertEqual(
            self.module.checkpoint_for_invocation(fallback).isoformat(),
            "2026-08-25T22:47:00+08:00",
        )

    def test_unique_cron_keeps_a_two_hour_delayed_morning_run_at_0817(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-21T10:30:00+08:00")

        invocation = self.module.select_cron_invocation(now, "17 0 * * 1-5")

        self.assertEqual(invocation.isoformat(), "2026-08-21T08:17:00+08:00")

    def test_early_unique_fallback_waits_to_its_0847_invocation(self) -> None:
        output = self._run_main(
            "2026-08-21T08:46:00+08:00",
            published_source=None,
            cron="47 0 * * 1-5",
        )

        self.assertIn("slot=2026-08-21T08:17+08:00", output)
        self.assertIn("invocation_slot=2026-08-21T08:47+08:00", output)

    def test_weekend_without_recent_checkpoint_is_rejected(self) -> None:
        now = dt.datetime.fromisoformat("2026-08-22T12:00:00+08:00")
        slot = self.module.select_checkpoint(now)
        self.assertEqual(slot.isoformat(), "2026-08-21T22:47:00+08:00")
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
                        "stats": {
                            "raw_pool_size": 200,
                            "scored_size": 0,
                            "recall_target": 200,
                            "recall_selected_size": 200,
                        },
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
                        "hk": {
                            "stats": {
                                "raw_pool_size": 200,
                                "scored_size": 1,
                                "recall_target": 200,
                                "recall_selected_size": 200,
                            }
                        },
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
        structurally_blocked = healthy_snapshot("2026-08-21T08:25:00+08:00")
        structurally_blocked["data_health"] = {
            "blocker_codes": [
                "TEN_DAY_PROBABILITY_UNCALIBRATED",
                "EXTERNAL_EVIDENCE_MISSING",
            ]
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
        snapshot = healthy_snapshot()
        snapshot["markets"]["hk"]["stats"]["scored_size"] = 0
        snapshot["markets"]["hk"]["stats"]["deep_scored_size"] = 0

        self.assertEqual(
            set(self.module.snapshot_data_source_recovery_reasons(snapshot)),
            {"HK_SCORE_COVERAGE_BELOW_MINIMUM", "HK_SCORING_EMPTY"},
        )

    def test_hk_us_dynamic_contract_is_recomputed_instead_of_trusting_pool_label(self) -> None:
        mutations = (
            ("discovery_pagination_complete", False),
            ("eligible_discovery_size", 200),
            ("selected_source_fresh_coverage", 0.97),
            ("recall_manifest", []),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                snapshot = healthy_snapshot()
                snapshot["markets"]["hk"]["stats"][field] = value
                reasons = self.module.snapshot_data_source_recovery_reasons(snapshot)
                self.assertIn("HK_DYNAMIC_CONTRACT_INVALID", reasons)

    def test_recall_target_shortfall_forces_scheduled_recovery(self) -> None:
        snapshot = healthy_snapshot()
        shortfalls = {"a_share": 299, "hk": 199, "us": 299}
        for market, selected in shortfalls.items():
            snapshot["markets"][market]["stats"]["recall_selected_size"] = selected
            snapshot["markets"][market]["stats"]["raw_pool_size"] = selected

        reasons = self.module.snapshot_data_source_recovery_reasons(snapshot)

        self.assertIn("A_SHARE_POOL_TARGET_NOT_MET", reasons)
        self.assertIn("HK_POOL_TARGET_NOT_MET", reasons)
        self.assertIn("US_POOL_TARGET_NOT_MET", reasons)

    def test_a_share_board_quota_shortfall_forces_recovery(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["markets"]["a_share"]["stats"]["board_counts"]["star"] = 59

        reasons = self.module.snapshot_data_source_recovery_reasons(snapshot)

        self.assertIn("A_SHARE_BOARD_QUOTA_PARTIAL", reasons)

    def test_a_share_deep_kline_boundary_forces_recovery(self) -> None:
        healthy = healthy_snapshot()
        healthy["markets"]["a_share"]["stats"].update(
            {"deep_scored_size": 294, "scored_size": 294, "deep_kline_coverage": 0.98}
        )
        degraded = healthy_snapshot()
        degraded["markets"]["a_share"]["stats"].update(
            {"deep_scored_size": 293, "scored_size": 293, "deep_kline_coverage": 0.9767}
        )

        self.assertNotIn(
            "A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM",
            self.module.snapshot_data_source_recovery_reasons(healthy),
        )
        self.assertIn(
            "A_SHARE_DEEP_SCORE_COVERAGE_BELOW_MINIMUM",
            self.module.snapshot_data_source_recovery_reasons(degraded),
        )

    def test_a_share_technical_coverage_boundary_forces_recovery(self) -> None:
        healthy = healthy_snapshot()
        healthy["markets"]["a_share"]["stats"].update(
            {
                "technical_kline_complete_size": 294,
                "technical_kline_coverage": 0.98,
                "deep_eligible_size": 294,
            }
        )
        degraded = healthy_snapshot()
        degraded["markets"]["a_share"]["stats"].update(
            {
                "technical_kline_complete_size": 293,
                "technical_kline_coverage": 0.9767,
                "deep_eligible_size": 293,
            }
        )

        self.assertNotIn(
            "A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM",
            self.module.snapshot_data_source_recovery_reasons(healthy),
        )
        self.assertIn(
            "A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM",
            self.module.snapshot_data_source_recovery_reasons(degraded),
        )

    def test_hk_realtime_freshness_metadata_is_required(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["markets"]["hk"]["quote_health"].pop("freshness_policy")
        self.assertIn(
            "HK_REALTIME_FRESHNESS_UNKNOWN",
            self.module.snapshot_data_source_recovery_reasons(snapshot),
        )

    def test_hk_yahoo_source_failure_is_recoverable(self) -> None:
        snapshot = {
            "markets": {
                **healthy_snapshot()["markets"],
                "hk": {
                    "quote_health": {
                        "status": "unavailable",
                        "requested_count": 200,
                        "quote_count": 0,
                        "quote_coverage": 0.0,
                        "reason_codes": ["YAHOO_QUOTE_UNAVAILABLE"],
                    },
                    "stats": {
                        "raw_pool_size": 200,
                        "scored_size": 0,
                        "recall_target": 200,
                        "recall_selected_size": 200,
                    },
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

    def test_2317_fallback_targets_the_2247_us_open_checkpoint(self) -> None:
        output = self._run_main(
            "2026-08-21T23:17:00+08:00",
            published_source=None,
            cron="17 15 * * 1-5",
        )

        self.assertIn("should_run=true", output)
        self.assertIn("slot=2026-08-21T22:47+08:00", output)
        self.assertIn("invocation_slot=2026-08-21T23:17+08:00", output)

    def test_delayed_2247_primary_does_not_masquerade_as_2317_fallback(self) -> None:
        output = self._run_main(
            "2026-08-26T00:00:00+08:00",
            published_source=None,
            cron="47 14 * * 1-5",
        )

        self.assertIn("slot=2026-08-25T22:47+08:00", output)
        self.assertIn("invocation_slot=2026-08-25T22:47+08:00", output)
        self.assertIn("delta_seconds=4380", output)

    def test_every_health_fallback_maps_to_its_matching_primary(self) -> None:
        pairs = (
            ("08:17", "08:47"),
            ("10:17", "10:47"),
            ("12:17", "12:47"),
            ("15:17", "15:47"),
            ("16:17", "16:47"),
            ("20:17", "20:47"),
            ("22:47", "23:17"),
        )
        for primary, fallback in pairs:
            with self.subTest(primary=primary, fallback=fallback, health="healthy"):
                output = self._run_main(
                    f"2026-08-21T{fallback}:00+08:00",
                    published_source="live",
                )
                self.assertIn("should_run=false", output)
                self.assertIn(f"slot=2026-08-21T{primary}+08:00", output)
            with self.subTest(primary=primary, fallback=fallback, health="degraded"):
                output = self._run_main(
                    f"2026-08-21T{fallback}:00+08:00",
                    published_source=None,
                )
                self.assertIn("should_run=true", output)
                self.assertIn(f"slot=2026-08-21T{primary}+08:00", output)

    def _run_main(
        self,
        now: str,
        *,
        published_source: str | None,
        cron: str | None = None,
    ) -> str:
        output = io.StringIO()
        environment = {
            "SCHEDULE_GATE_NOW": now,
            "SCHEDULE_GATE_STATUS_URL": "https://example.test/api/latest",
        }
        if cron:
            environment["SCHEDULE_GATE_CRON"] = cron
        with (
            mock.patch.dict(
                os.environ,
                environment,
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

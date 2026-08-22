from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import server
from scripts.validate_snapshot import validate_snapshot, validate_snapshot_file
from tests.test_selector_v2 import fixture_candidate


def snapshot_fixture() -> dict:
    markets = {}
    targets = {"a_share": 300, "hk": 200, "us": 300}
    for market_key, code in (("a_share", "603228"), ("hk", "0700.HK"), ("us", "NVDA")):
        row = fixture_candidate()
        row["code"] = code
        row["symbol"] = code
        row["market_key"] = market_key
        row.pop("candidate_lineage", None)
        row["realtime"].update(
            {
                "price": row["price"],
                "source_as_of": "2026-08-19T16:00:00+08:00",
                "volume_unit": "lot" if market_key == "a_share" else "share",
            }
        )
        stats = {
            "recall_target": targets[market_key],
            "recall_selected_size": targets[market_key],
            "recall_shortfall": 0,
            "raw_pool_size": targets[market_key],
            "universe_size": targets[market_key],
            "valid_quote_size": 1,
            "deep_scored_size": 1,
            "scored_size": 1,
            "source_counts": {"fixture": targets[market_key]},
        }
        if market_key == "a_share":
            stats.update(
                {
                    "board_targets": dict(server.A_SHARE_BOARD_TARGETS),
                    "board_counts": dict(server.A_SHARE_BOARD_TARGETS),
                    "board_shortfalls": {},
                    "route_targets": dict(server.A_SHARE_ROUTE_TARGETS),
                    "route_counts": dict(server.A_SHARE_ROUTE_TARGETS),
                    "route_shortfalls": {},
                }
            )
        markets[market_key] = {
            "key": market_key,
            "label": market_key,
            "decision": {
                "action": "BUY_CANDIDATE",
                "title": "两周推荐",
                "message": "legacy decision",
                "primary": row,
                "watchlist": [],
            },
            "stats": stats,
        }
    return {
        "model_version": "legacy-fixture",
        "generated_at": "2026-08-19T16:30:00+08:00",
        "snapshot_key": "2026-08-19_2026-08-19_163000.json",
        "market": {"risk": "normal", "items": []},
        "markets": markets,
    }


class SnapshotContractTests(unittest.TestCase):
    def test_automation_metadata_uses_workflow_environment(self) -> None:
        with mock.patch.dict(
            server.os.environ,
            {
                "AUTOMATION_TRIGGER": "schedule",
                "SCHEDULED_SLOT": "2026-08-21T20:17:00+08:00",
                "GENERATION_ATTEMPT": "2",
            },
            clear=False,
        ):
            snapshot = server.enrich_snapshot_v2(snapshot_fixture())
        self.assertEqual(
            snapshot["automation"],
            {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T20:17:00+08:00",
                "generation_attempt": 2,
            },
        )

    def test_three_markets_keep_old_fields_and_add_v2_contract(self) -> None:
        snapshot = snapshot_fixture()
        legacy_actions = {key: section["decision"]["action"] for key, section in snapshot["markets"].items()}
        enriched = server.enrich_snapshot_v2(snapshot)
        self.assertEqual(enriched["schema_version"], server.SCHEMA_VERSION)
        self.assertEqual(enriched["selector_mode"], server.SELECTOR_MODE)
        self.assertEqual(
            enriched["analysis_models"]["ten_day_return"]["label_version"], server.TEN_DAY_LABEL_VERSION
        )
        for key in ("a_share", "hk", "us"):
            row = enriched["markets"][key]["decision"]["primary"]
            required = {
                "score",
                "recommendation_degree",
                "chan_score",
                "uzi_panel_score",
                "legacy",
                "v2",
                "data_quality",
                "decision_gates",
                "candidate_lineage",
                "analysis_projects",
            }
            self.assertTrue(required <= row.keys())
            self.assertEqual(enriched["markets"][key]["decision"]["action"], legacy_actions[key])
        self.assertEqual(enriched["analysis_models"]["dual_low"]["mode"], "shadow_overlay")
        self.assertEqual(
            enriched["markets"]["a_share"]["decision"]["primary"]["analysis_projects"]["dual_low"]["status"],
            "unavailable",
        )
        self.assertEqual(
            enriched["markets"]["hk"]["decision"]["primary"]["analysis_projects"]["dual_low"]["status"],
            "not_applicable",
        )
        self.assertEqual(
            enriched["markets"]["hk"]["decision"]["primary"]["candidate_lineage"]["universe_origin"],
            "curated_static",
        )
        self.assertEqual(
            enriched["markets"]["us"]["decision"]["primary"]["candidate_lineage"]["universe_origin"],
            "curated_static",
        )

    def test_snapshot_enrichment_does_not_change_legacy_decision(self) -> None:
        snapshot = snapshot_fixture()
        before = copy.deepcopy(snapshot["markets"])
        enriched = server.enrich_snapshot_v2(snapshot)
        for market_key in before:
            old = before[market_key]["decision"]
            new = enriched["markets"][market_key]["decision"]
            self.assertEqual(new["action"], old["action"])
            self.assertEqual(new["title"], old["title"])
            self.assertEqual(new["message"], old["message"])
            self.assertEqual(new["primary"]["score"], old["primary"]["score"])
            self.assertEqual(new["primary"]["recommendation_degree"], old["primary"]["recommendation_degree"])

    def test_global_ten_day_gate_is_strict_without_calibration_or_event_pipeline_scan(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        decision = enriched["global_decision"]
        self.assertEqual(decision["action"], "NO_VALID_PICK")
        self.assertEqual(decision["action_basis"], "strict_cross_market_gate_v1")
        self.assertEqual(decision["probability_status"], "UNAVAILABLE")
        self.assertIsNone(decision["probability"])
        self.assertFalse(decision["calibrated"])
        self.assertIsNone(decision["primary"])
        self.assertEqual(decision["research_priority"]["status"], "RESEARCH_ONLY")
        self.assertIn("EVENT_PIPELINE_NOT_SCANNED", decision["blocker_codes"])
        self.assertIn("TEN_DAY_PROBABILITY_UNCALIBRATED", decision["blocker_codes"])
        self.assertEqual(set(decision["market_states"]), {"a_share", "hk", "us"})
        self.assertFalse(enriched["data_health"]["decision_usable"])

    def test_snapshot_publishes_exchange_specific_trade_windows(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())

        self.assertEqual(set(enriched["next_trade_dates"]), {"a_share", "hk", "us"})
        self.assertEqual(set(enriched["forecast_end_dates"]), {"a_share", "hk", "us"})
        self.assertNotEqual(enriched["next_trade_date"], enriched["forecast_end_date"])
        self.assertEqual(enriched["next_trade_dates"]["a_share"], "2026-08-20")
        self.assertEqual(enriched["next_trade_dates"]["hk"], "2026-08-20")
        self.assertEqual(enriched["next_trade_dates"]["us"], "2026-08-19")
        for market_key in ("a_share", "hk", "us"):
            window = enriched["markets"][market_key]["trade_window"]
            self.assertEqual(window["entry_trade_date"], enriched["next_trade_dates"][market_key])
            self.assertEqual(window["forecast_end_trade_date"], enriched["forecast_end_dates"][market_key])
            self.assertEqual(window["horizon_sessions"], 10)
            self.assertGreater(
                dt.datetime.fromisoformat(window["entry_session_open_at"]),
                dt.datetime.fromisoformat(window["decision_time"]),
            )

    def test_snapshot_validator_accepts_shadow_fallback_and_rejects_decision_participation(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        self.assertEqual(validate_snapshot(enriched), [])
        enriched["analysis_models"]["dual_low"]["participates_in_decision"] = True
        self.assertIn("dual-low model must not participate in the decision", validate_snapshot(enriched))

    def test_snapshot_validator_checks_published_recall_funnel_contract(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        targets = {"a_share": 300, "hk": 200, "us": 300}
        for market_key, target in targets.items():
            enriched["markets"][market_key]["stats"].update(
                {
                    "recall_target": target,
                    "recall_selected_size": target,
                    "recall_shortfall": 0,
                    "valid_quote_size": target,
                    "deep_scored_size": 1,
                }
            )
        enriched["markets"]["a_share"]["stats"].update(
            {
                "board_targets": server.A_SHARE_BOARD_TARGETS,
                "board_counts": server.A_SHARE_BOARD_TARGETS,
            }
        )
        self.assertEqual(validate_snapshot(enriched), [])

        enriched["markets"]["hk"]["stats"]["recall_selected_size"] = 199
        errors = validate_snapshot(enriched)
        self.assertIn("markets.hk.stats.recall_shortfall is inconsistent", errors)

    def test_expanded_universe_cannot_omit_or_falsify_recall_funnel(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        del enriched["markets"]["us"]["stats"]["recall_target"]
        enriched["markets"]["a_share"]["stats"]["board_counts"] = {
            "sh_main": 300,
            "sz_main": 0,
            "chinext": 0,
            "star": 0,
        }
        enriched["markets"]["hk"]["stats"]["raw_pool_size"] = 1
        enriched["markets"]["hk"]["stats"]["scored_size"] = 99

        errors = validate_snapshot(enriched)

        self.assertTrue(any("markets.us.stats recall funnel fields missing" in error for error in errors))
        self.assertIn("markets.a_share.stats.board_shortfalls is inconsistent", errors)
        self.assertIn("markets.hk.stats.raw_pool_size must equal selected size", errors)
        self.assertIn("markets.hk.stats.scored_size must equal deep scored size", errors)

    def test_snapshot_validator_requires_global_ten_day_contract(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        enriched["analysis_models"].pop("ten_day_return")
        enriched.pop("global_decision")
        errors = validate_snapshot(enriched)
        self.assertIn("analysis_models.ten_day_return is required", errors)
        self.assertIn("global_decision is required", errors)

    def test_snapshot_validator_rejects_invalid_trade_window_or_range_horizon(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        enriched["forecast_end_dates"]["us"] = enriched["next_trade_dates"]["us"]
        candidate = enriched["markets"]["us"]["decision"]["primary"]
        candidate["estimated_2d_range"]["horizon_trade_days"] = 10

        errors = validate_snapshot(enriched)

        self.assertIn("forecast_end_dates.us must be the 10th XNYS session", errors)
        self.assertIn("us:NVDA estimated_2d_range horizon must be 2", errors)

    def test_snapshot_validator_rejects_market_state_that_understates_sources(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        enriched["global_decision"]["market_states"]["hk"] = {
            "state": "READY",
            "reason_codes": [],
        }
        errors = validate_snapshot(enriched)
        self.assertIn("global_decision.market_states.hk understates derived DEGRADED coverage", errors)
        self.assertIn("global_decision.market_states.hk.reason_codes are incomplete", errors)

    def test_snapshot_validator_requires_realtime_price_for_published_live_candidate(self) -> None:
        for fallback_field, fallback_value in (
            ("current_price", "12.50"),
            ("entry_price", 12.5),
            ("price", 12.5),
            ("kline", [{"close": "12.50"}]),
        ):
            with self.subTest(fallback_field=fallback_field):
                enriched = server.enrich_snapshot_v2(snapshot_fixture())
                candidate = enriched["markets"]["a_share"]["decision"]["primary"]
                candidate.pop("realtime", None)
                candidate[fallback_field] = fallback_value

                errors = validate_snapshot(enriched)

                self.assertIn(
                    "a_share:603228 realtime quote is required for live publication",
                    errors,
                )

    def test_snapshot_validator_rejects_live_candidate_without_a_positive_price(self) -> None:
        for invalid in (0, -1, "12.50", True, None):
            with self.subTest(invalid=invalid):
                enriched = server.enrich_snapshot_v2(snapshot_fixture())
                candidate = enriched["markets"]["a_share"]["decision"]["primary"]
                candidate["realtime"]["price"] = invalid

                errors = validate_snapshot(enriched)

                self.assertIn(
                    "a_share:603228 realtime.price must be positive",
                    errors,
                )

    def test_snapshot_validator_checks_realtime_publication_metadata(self) -> None:
        cases = {
            "source_as_of": (
                "not-a-time",
                "a_share:603228 realtime.source_as_of must be a timezone-aware ISO datetime",
            ),
            "fetched_at": (
                "2026-08-19T16:10:00",
                "a_share:603228 realtime.fetched_at must be a timezone-aware ISO datetime",
            ),
            "volume_unit": (
                "contracts",
                "a_share:603228 realtime.volume_unit must be lot or share",
            ),
        }
        for field, (invalid_value, expected_error) in cases.items():
            with self.subTest(field=field):
                enriched = server.enrich_snapshot_v2(snapshot_fixture())
                candidate = enriched["markets"]["a_share"]["decision"]["primary"]
                candidate["realtime"][field] = invalid_value
                self.assertIn(expected_error, validate_snapshot(enriched))

    def test_snapshot_validator_rejects_old_price_only_candidate_for_latest_publication(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        candidate = enriched["markets"]["a_share"]["decision"]["primary"]
        candidate.pop("current_price", None)
        candidate.pop("entry_price", None)
        candidate.pop("realtime", None)
        candidate["price"] = "12.50"
        candidate["kline"] = []

        errors = validate_snapshot(enriched)

        self.assertIn("a_share:603228 realtime quote is required for live publication", errors)

    def test_snapshot_validator_allows_a_market_without_live_candidates(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        decision = enriched["markets"]["us"]["decision"]
        decision["primary"] = None
        decision["blocked_candidate"] = None
        decision["watchlist"] = []
        global_decision = enriched["global_decision"]
        for field in ("primary", "research_priority"):
            candidate = global_decision.get(field)
            if isinstance(candidate, dict) and candidate.get("market") == "us":
                global_decision[field] = None

        errors = validate_snapshot(enriched)

        self.assertFalse(any(error.startswith("us:") and "live candidate" in error for error in errors))

    def test_snapshot_validator_checks_unique_global_live_candidate(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        research = enriched["global_decision"]["research_priority"]
        research.update(
            {
                "market": "us",
                "code": "GLOBAL",
                "calendar_id": enriched["markets"]["us"]["trade_window"]["calendar_id"],
                "entry_trade_date": enriched["next_trade_dates"]["us"],
                "forecast_end_trade_date": enriched["forecast_end_dates"]["us"],
                "entry_price": 0,
            }
        )
        for field in ("current_price", "price", "realtime", "kline"):
            research.pop(field, None)

        errors = validate_snapshot(enriched)

        self.assertIn(
            "us:GLOBAL realtime quote is required for live publication",
            errors,
        )

    def test_snapshot_validator_requires_safe_snapshot_key(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        for invalid in (None, "", "latest.json", "../escape.json", "nested/file.json", "bad\\file.json"):
            with self.subTest(invalid=invalid):
                enriched["snapshot_key"] = invalid
                self.assertIn(
                    "snapshot_key must be a safe immutable JSON filename",
                    validate_snapshot(enriched),
                )

    def test_snapshot_validator_requires_object_watchlist_rows(self) -> None:
        cases = (
            ({"603228": {}}, "markets.a_share.decision.watchlist must be a list"),
            ([{"code": "603228"}, "bad-row"], "markets.a_share.decision.watchlist[1] must be an object"),
        )
        for watchlist, expected in cases:
            with self.subTest(watchlist=watchlist):
                enriched = server.enrich_snapshot_v2(snapshot_fixture())
                enriched["markets"]["a_share"]["decision"]["watchlist"] = watchlist
                self.assertIn(expected, validate_snapshot(enriched))

    def test_snapshot_file_validator_requires_matching_immutable_file(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        encoded = json.dumps(enriched, ensure_ascii=False, indent=2) + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            picks = pathlib.Path(temporary)
            latest = picks / "latest.json"
            immutable = picks / enriched["snapshot_key"]
            latest.write_text(encoded, encoding="utf-8")

            missing_errors = validate_snapshot_file(latest)
            self.assertIn("immutable snapshot file is missing", missing_errors)

            immutable.write_text(encoded, encoding="utf-8")
            self.assertEqual(validate_snapshot_file(latest), [])

            immutable.write_text(encoded.replace("legacy-fixture", "different-model"), encoding="utf-8")
            mismatch_errors = validate_snapshot_file(latest)
            self.assertIn("latest snapshot and immutable snapshot bytes must match", mismatch_errors)


if __name__ == "__main__":
    unittest.main()

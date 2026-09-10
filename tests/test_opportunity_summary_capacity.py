"""Capacity fixtures only: no rescoring, provider requests or production writes."""
from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode

import event_pipeline
import opportunity_outcome_ledger
import return_opportunity
import sector_metadata
from scripts import build_worker_assets as builder
from scripts import verify_deployment


ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHIVED_SNAPSHOT = ROOT / "data/picks/2026-09-10_2026-09-09_063421.json"


def full_coverage_capacity_fixture():
    """Overlay current full metadata shapes on an old, real published board.

    Every added sector, scan and outcome is explicitly TEST_FIXTURE data. This
    does not imply that any of the archived securities have this classification.
    """
    snapshot = json.loads(ARCHIVED_SNAPSHOT.read_text(encoding="utf-8"))
    snapshot["capacity_fixture_only"] = True
    board = snapshot["return_opportunities"]
    board["score_version"] = "return-opportunity-score-v2"
    stamp = snapshot["feature_cutoff_at"]
    moment = dt.datetime.fromisoformat(stamp)
    rows = board["candidates"] + [board["primary"]] + [stats["primary"] for stats in board["market_summaries"].values() if stats.get("primary")]
    for row in rows:
        market, code = row["market"], row["code"]
        record = sector_metadata.parse_sector_record(
            {"industry": "TEST_FIXTURE_电子设备制造与专用信息技术服务"},
            source=sector_metadata.PROVIDER, retrieved_at=stamp,
            source_url=sector_metadata.PROVIDER_URL + "?" + urlencode({"secids": "TEST_FIXTURE." + code, "fields": "f12,f13,f100"}),
            source_field="f100", taxonomy="eastmoney_sector" if market == "us" else "eastmoney_industry")
        record.update(status="FRESH", stale=False, age_days=0.0, refresh_status="FETCHED", market=market, code=code, provider_secid="TEST_FIXTURE." + code)
        row["sector"] = return_opportunity._sector({}, {"sector_metadata": record}, cutoff=moment)
        coverage = event_pipeline.candidate_scan_coverage({}, market, code)
        coverage.update(status="SUCCESS", verified=True, requested=True,
                        run_id="TEST_FIXTURE_official-event-pipeline:1234567890:1",
                        retrieved_at=stamp, event_count=0, error_code=None)
        row["event_coverage"] = coverage
        row["score_version"] = board["score_version"]
        row["risk_flags"] = sorted(set(row["risk_flags"] + ["NEGATIVE_EVENT_COVERAGE_INCOMPLETE"]))
    snapshot["sector_metadata_coverage"] = {"version": "sector-metadata-v1", "provider": sector_metadata.PROVIDER,
        "status": "COMPLETE", "generated_at": stamp, "request_count": 8, "request_limit": 20,
        "cache_read_status": "TEST_FIXTURE", "fresh_ttl_days": 7, "failure_ttl_hours": 6,
        "candidate_count": 800, "fresh_count": 800, "stale_count": 0, "missing_count": 0,
        "coverage_pct": 100.0, "markets": {market: {"candidate_count": count, "fresh_count": count,
            "stale_count": 0, "missing_count": 0, "coverage_pct": 100.0,
            "taxonomy": "eastmoney_sector" if market == "us" else "eastmoney_industry"}
            for market, count in (("a_share", 300), ("hk", 200), ("us", 300))}}
    # Keep a complete measured ledger shape, marked as a fixture by its source.
    batch = opportunity_outcome_ledger.register_opportunity_snapshot(snapshot, published_at=stamp)
    tracking = opportunity_outcome_ledger.evaluate_opportunity_performance({batch["snapshot_key"]: batch})
    snapshot["opportunity_outcome_tracking"] = tracking
    return snapshot, tracking


class OpportunitySummaryCapacityTests(unittest.TestCase):
    def test_real_board_with_full_new_coverage_and_recent_rows_fits_summary_budget(self):
        with mock.patch("requests.sessions.Session.request", side_effect=AssertionError("capacity fixture cannot request providers")):
            snapshot, tracking = full_coverage_capacity_fixture()
            original_board = copy.deepcopy(snapshot["return_opportunities"])
            source = builder._stable_json_bytes(snapshot)
            latest = {"snapshot_key": snapshot["snapshot_key"], "generated_at": snapshot["generated_at"]}
            bootstrap = builder.build_worker_ui_bootstrap(snapshot, latest, source)
            self.assertLessEqual(len(builder._stable_json_bytes(bootstrap)), builder.MAX_DATA_SUMMARY_BYTES)
            with tempfile.TemporaryDirectory() as directory:
                data_root = pathlib.Path(directory) / "data"
                builder.write_worker_runtime_assets(snapshot, latest, source, data_root / "picks")
                assets = {name: json.loads((data_root / "picks" / name).read_text()) for name in ("ui-bootstrap.json", "ui-candidates.json", "ui-events.json")}
                manifest = builder.build_data_manifest_assets(snapshot, source, assets,
                    {"summaries": [], "history_evaluation": {"opportunity_outcome_tracking": tracking}, "opportunity_outcome_tracking": tracking}, data_root)
                self.assertLessEqual(manifest["assets"]["summary"]["byte_size"], builder.MAX_DATA_SUMMARY_BYTES)
                full_history = json.loads((data_root / manifest["history_key"]).read_text())
                self.assertEqual(full_history["opportunity_outcome_tracking"], tracking)
            self.assertEqual(snapshot["return_opportunities"], original_board)
            self.assertEqual(len(bootstrap["opportunity_outcome_tracking"]["recent_outcomes"]), 3)
            compact = bootstrap["return_opportunities"]
            self.assertEqual(len(compact["candidates"]), 12)
            self.assertEqual(compact["primary"], compact["candidates"][0])
            for original, row in zip(original_board["candidates"], compact["candidates"]):
                for key in ("rank", "opportunity_score", "sector", "risk_flags"):
                    self.assertEqual(row[key], original[key])
                self.assertEqual({**compact["event_scan_policy"], **row["event_coverage"]}, original["event_coverage"])

    def test_long_sector_names_and_four_score_versions_leave_capacity_headroom(self):
        snapshot, tracking = full_coverage_capacity_fixture()
        board = snapshot["return_opportunities"]
        for row in board["candidates"] + [board["primary"]] + [s["primary"] for s in board["market_summaries"].values() if s.get("primary")]:
            row["sector"]["name"] = "TEST_FIXTURE_" + "测" * (100 - len("TEST_FIXTURE_"))
        batches = {}
        for version in range(4):
            sample = copy.deepcopy(snapshot)
            sample.pop("opportunity_outcome_tracking")
            sample["snapshot_key"] = f"2026-09-10_TEST_FIXTURE_capacity_{version}.json"
            sample["return_opportunities"]["score_version"] = f"TEST_FIXTURE_return-opportunity-score-v{version}"
            batch = opportunity_outcome_ledger.register_opportunity_snapshot(sample, published_at=sample["feature_cutoff_at"])
            batches[batch["snapshot_key"]] = batch
        snapshot["opportunity_outcome_tracking"] = opportunity_outcome_ledger.evaluate_opportunity_performance(batches)
        payload = builder.build_worker_ui_bootstrap(snapshot, {}, builder._stable_json_bytes(snapshot))
        self.assertEqual(len(payload["opportunity_outcome_tracking"]["by_version"]), 4)
        self.assertEqual(len(payload["opportunity_outcome_tracking"]["recent_outcomes"]), 3)
        self.assertLess(len(builder._stable_json_bytes(payload)), builder.MAX_DATA_SUMMARY_BYTES - 2048)

    def test_compact_lineage_retains_provenance_while_details_keep_raw_metrics(self):
        snapshot, _ = full_coverage_capacity_fixture()
        candidate = snapshot["markets"]["hk"]["decision"]["blocked_candidate"]
        original = copy.deepcopy(candidate)
        compact = builder.compact_ui_candidate(candidate, "hk", detail=False)
        full = builder.compact_ui_candidate(candidate, "hk", detail=True)
        self.assertTrue(any("metrics" in route for route in original["candidate_lineage"]["recall_routes"]))
        for old, row in zip(original["candidate_lineage"]["recall_routes"], compact["candidate_lineage"]["recall_routes"]):
            self.assertEqual(row, {k: v for k, v in old.items() if k != "metrics"})
        self.assertEqual(full["candidate_lineage"], original["candidate_lineage"])
        self.assertEqual(candidate, original)

    def test_different_scan_policy_keeps_per_stock_evidence(self):
        snapshot, _ = full_coverage_capacity_fixture()
        rows = snapshot["return_opportunities"]["candidates"]
        rows[1]["event_coverage"]["lookback_days"] += 1
        rows[1]["event_coverage"]["limitations"].append("TEST_FIXTURE_different provider scope")
        compact = builder.summarize_return_opportunities(snapshot)
        self.assertNotIn("lookback_days", compact["event_scan_policy"])
        self.assertNotIn("limitations", compact["event_scan_policy"])
        for original, row in zip(rows, compact["candidates"]):
            self.assertEqual({**compact["event_scan_policy"], **row["event_coverage"]}, original["event_coverage"])

    def test_compact_projection_keeps_exact_deployment_ranking_and_evidence_checks(self):
        snapshot, _ = full_coverage_capacity_fixture()
        spec = verify_deployment.UI_ASSET_SPECS["latest-summary"]
        payload = {"ok": True, "contract_version": spec["contract_version"],
                   "latest": {"return_opportunities": builder.summarize_return_opportunities(snapshot)}, "status": {}}
        # Isolate the board comparison, leaving its real exact projector intact.
        with (
            mock.patch.dict(verify_deployment.UI_ASSET_SPECS, {"latest-summary": spec}, clear=True),
            mock.patch.object(verify_deployment, "_ui_identity_errors", return_value=[]),
            mock.patch.object(verify_deployment, "_snapshot_use_errors", return_value=[]),
        ):
            def errors(published):
                return verify_deployment.ui_api_contract_errors(snapshot, {"latest-summary": published},
                    source_snapshot_sha256="a" * 64, source_snapshot_byte_size=1)

            self.assertEqual(errors(payload), [])
            for change in ("rank", "score", "coverage", "sector_source", "shared_policy"):
                altered = copy.deepcopy(payload)
                board = altered["latest"]["return_opportunities"]
                row = board["candidates"][0]
                if change == "rank":
                    row["rank"] += 1
                elif change == "score":
                    row["opportunity_score"] += 0.01
                elif change == "coverage":
                    row["event_coverage"]["verified"] = False
                elif change == "sector_source":
                    row["sector"]["source"] = "TEST_FIXTURE_tampered"
                else:
                    board["event_scan_policy"]["limitations"] = []
                with self.subTest(change=change):
                    self.assertTrue(any("do not match the frozen research ranking" in error for error in errors(altered)))


if __name__ == "__main__":
    unittest.main()

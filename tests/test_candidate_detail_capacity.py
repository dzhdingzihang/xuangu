"""Large research dossiers must not become the paginated candidate list."""
import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scripts import build_worker_assets as builder
from tests.test_build_worker_assets import runtime_snapshot_fixture, runtime_quote_candidate


class CandidateDetailCapacityTests(unittest.TestCase):
    def test_bootstrap_qualification_does_not_repeat_recall_dossiers(self):
        snapshot = runtime_snapshot_fixture()
        for row in [snapshot["production_decision"]["primary"], *snapshot["production_decision"]["qualified_candidates"]]:
            row["candidate_snapshot"]["candidate_lineage"] = {"recall_routes": [
                {"route": "liquidity", "source": "TEST_FIXTURE", "reason": "x" * 8000}]}
        source = json.dumps(snapshot).encode()
        compact = builder.build_worker_ui_bootstrap(snapshot, {}, source)["production_decision"]
        for row in [compact["primary"], *compact["qualified_candidates"]]:
            self.assertNotIn("candidate_lineage", row["candidate_snapshot"])
            self.assertEqual(row["candidate_snapshot"]["code"], row["code"])
        full = builder.build_worker_ui_candidates(snapshot, source, for_detail_assets=True)
        self.assertTrue(next(row for row in full["candidates"] if row["code"] == "PFE")["candidate_lineage"]["recall_routes"])

    def test_many_rich_dossiers_are_loaded_individually_without_losing_evidence(self):
        snapshot = runtime_snapshot_fixture()
        rows = []
        for index in range(40):
            candidate = runtime_quote_candidate("PFE" if index == 0 else f"FIX{index:02}", "us", price=28)
            candidate["research_evidence"] = {"TEST_FIXTURE_ONLY": "x" * 25_000}
            candidate["candidate_lineage"] = {"recall_routes": [{"route": "liquidity", "source": "TEST_FIXTURE",
                "observed_at": snapshot["generated_at"], "metrics": {"TEST_FIXTURE_ONLY": "y" * 1000}}]}
            rows.append(("us", candidate))
        original = copy.deepcopy(rows)
        source = json.dumps(snapshot).encode()
        with mock.patch.object(builder, "iter_live_candidates", side_effect=lambda _snapshot: list(rows)):
            full = builder.build_worker_ui_candidates(snapshot, source, for_detail_assets=True)
            self.assertGreater(len(builder._stable_json_bytes(full)), builder.MAX_WORKER_UI_CANDIDATES_BYTES)
            compact = builder.build_worker_ui_candidates(snapshot, source)
            self.assertEqual(compact["candidate_count"], 40)
            self.assertLess(len(builder._stable_json_bytes(compact)), 200_000)
            self.assertNotIn("kline", compact["candidates"][0])
            with tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory) / "data"
                builder.write_worker_runtime_assets(snapshot, {}, source, root / "picks")
                assets = {name: json.loads((root / "picks" / name).read_text())
                          for name in ("ui-bootstrap.json", "ui-candidates.json", "ui-events.json")}
                manifest = builder.build_data_manifest_assets(snapshot, source, assets, {"summaries": []}, root)
                self.assertEqual(len(manifest["candidate_detail_keys"]), 40)
                by_id = {row["id"]: row for row in full["candidates"]}
                for identity, path in manifest["candidate_detail_keys"].items():
                    detail = json.loads((root / path).read_text())["candidate"]
                    self.assertEqual(detail, by_id[identity])
                    self.assertLess((root / path).stat().st_size, builder.MAX_DATA_CANDIDATE_DETAIL_BYTES)
        self.assertEqual(rows, original)


if __name__ == "__main__":
    unittest.main()

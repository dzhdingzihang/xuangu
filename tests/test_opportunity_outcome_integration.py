from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import opportunity_outcome_ledger as ledger
from scripts import build_worker_assets, merge_archive_payload, settle_outcomes
from tests.test_opportunity_outcome_ledger import snapshot, pending, loader, MATURE


class OpportunityOutcomeIntegrationTests(unittest.TestCase):
    def test_archive_ledger_only_validates_new_files_and_preserves_settled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            incoming, archive = root / "incoming", root / "archive"
            relative = pathlib.Path("data/outcomes/opportunity-settlements")
            early = pending()
            settled = ledger.settle_opportunity_batch(early, MATURE, loader)
            source = ledger.write_opportunity_outcome_batch(incoming / relative, early)
            self.assertEqual(merge_archive_payload.merge_payload(incoming, archive)["copied"], 1)
            ledger.write_opportunity_outcome_batch(incoming / relative, settled)
            self.assertEqual(merge_archive_payload.merge_payload(incoming, archive)["updated"], 1)
            source.write_text(json.dumps(early))
            self.assertEqual(merge_archive_payload.merge_payload(incoming, archive)["preserved_newer"], 1)
            saved = ledger.load_opportunity_outcome_batches(archive / relative)
            self.assertEqual(saved[early["snapshot_key"]], settled)
            invalid = copy.deepcopy(early)
            invalid["prediction_count"] = 99
            source.write_text(json.dumps(invalid))
            with self.assertRaises(ledger.OpportunityOutcomeConflictError):
                merge_archive_payload.merge_payload(incoming, archive)
            with self.assertRaises(ledger.OpportunityOutcomeConflictError):
                merge_archive_payload.merge_payload(incoming, root / "empty-archive")

    def test_archive_merges_complementary_partial_batches(self):
        a = ledger.settle_opportunity_batch(pending(), MATURE, lambda market, code: ([], "", False) if code == "AAA" else loader(market, code))
        b = ledger.settle_opportunity_batch(pending(), MATURE, lambda market, code: ([], "", False) if code == "BBB" else loader(market, code))
        merged = ledger.merge_opportunity_batches(a, b)
        self.assertEqual(merged["status_counts"], {"SETTLED": 2})
        self.assertEqual(ledger.merge_opportunity_batches(merged, a), merged)
        changed = ledger.settle_opportunity_batch(pending(), "2026-09-11T00:00:00Z", loader)
        with self.assertRaises(ledger.OpportunityOutcomeConflictError):
            ledger.merge_opportunity_batches(merged, changed)

    def test_worker_bootstrap_collecting_and_scan_targets_private(self):
        source = snapshot()
        source["return_opportunities"]["event_scan_targets_by_market"] = {"us": ["AAA"]}
        source["sector_metadata_coverage"] = {"us": {"covered_count": 2}}
        summary = build_worker_assets.build_worker_ui_bootstrap(source, {}, json.dumps(source).encode())
        self.assertEqual(summary["opportunity_outcome_tracking"]["schema_version"], "opportunity-performance-v1")
        self.assertEqual(summary["opportunity_outcome_tracking"]["status"], "COLLECTING")
        self.assertIsNone(summary["opportunity_outcome_tracking"]["mean_net_return"])
        self.assertEqual(summary["sector_metadata_coverage"], source["sector_metadata_coverage"])
        self.assertNotIn("event_scan_targets_by_market", summary["return_opportunities"])

    def test_yahoo_high_uses_same_adjustment_as_low_open_close(self):
        payload = {"chart": {"result": [{"timestamp": [1700000000], "meta": {"exchangeTimezoneName": "UTC"},
            "indicators": {"quote": [{"open": [100], "high": [120], "low": [90], "close": [110]}],
                "adjclose": [{"adjclose": [55]}]}}]}}
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        with mock.patch.object(settle_outcomes.urllib.request, "urlopen", return_value=response):
            rows = settle_outcomes.yahoo_adjusted_rows("AAA", "us")
        self.assertEqual({k: rows[0][k] for k in ("open", "high", "low", "close")}, {"open": 50, "high": 60, "low": 45, "close": 55})

    def test_startup_tracking_bounded_without_mutating_full_history(self):
        full = ledger.evaluate_opportunity_performance({"a": pending()})
        full["recent_outcomes"] *= 30
        full["by_version"] *= 6
        compact = build_worker_assets.compact_opportunity_tracking(full)
        self.assertEqual(len(compact["recent_outcomes"]), 3)
        self.assertEqual(len(compact["by_version"]), 4)
        self.assertTrue(compact["by_version_truncated"])
        self.assertEqual(len(full["recent_outcomes"]), 60)


if __name__ == "__main__":
    unittest.main()

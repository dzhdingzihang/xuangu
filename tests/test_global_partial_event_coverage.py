"""Per-symbol audit success must not disappear behind a partial market scan."""
import copy
import datetime as dt
import unittest
from unittest import mock

import event_pipeline
import server
from tests.test_global_decision_contract import executable_builder_input


class PartialGlobalEventCoverageTests(unittest.TestCase):
    def test_success_error_and_unselected_survive_partial_market_without_unlocking(self):
        snapshot = executable_builder_input()
        primary = snapshot["markets"]["us"]["decision"]["primary"]
        good_code = primary["code"]
        other = []
        for code in ("FAILED", "UNREQUESTED"):
            row = copy.deepcopy(primary)
            row.update(code=code, symbol=code, name=code)
            other.append(row)
        snapshot["markets"]["us"]["_candidate_pool"] = [primary, *other]

        def symbols(_snapshot, market, _limit):
            return [good_code, "FAILED"] if market == "us" else []

        def fetch(_method, url, **_kwargs):
            if url.endswith("company_tickers.json"):
                return {"0": {"ticker": good_code, "cik_str": 1},
                        "1": {"ticker": "FAILED", "cik_str": 2}}
            if "CIK0000000001" in url:
                return {"filings": {"recent": {}}}
            raise OSError("TEST_FIXTURE_source_unavailable")

        with mock.patch.object(event_pipeline, "_candidate_symbols", side_effect=symbols):
            snapshot["events"] = event_pipeline.collect_for_snapshot(
                snapshot, "TEST_FIXTURE_partial", now=dt.datetime.fromisoformat(snapshot["generated_at"]),
                fetcher=fetch)
        self.assertFalse(event_pipeline.pipeline_market_complete(snapshot, "us"))
        decision = server.build_global_ten_day_decision(snapshot)
        rows = {row["code"]: row for row in decision["evaluated_candidates"] if row["market"] == "us"}
        self.assertTrue(rows[good_code]["event_candidate_scanned"])
        self.assertTrue(rows[good_code]["risk_screen"]["official_filing_checked"])
        self.assertEqual(rows[good_code]["positive_event_enrichment"]["status"], "SCANNED_NO_POSITIVE")
        self.assertFalse(rows["FAILED"]["event_candidate_scanned"])
        self.assertEqual(rows["FAILED"]["positive_event_enrichment"]["status"], "SOURCE_UNAVAILABLE")
        self.assertEqual(rows["UNREQUESTED"]["positive_event_enrichment"]["status"], "NOT_SELECTED")
        self.assertIn("EVENT_PIPELINE_NOT_SCANNED", rows[good_code]["blocker_codes"])
        self.assertEqual(decision["action"], "NO_VALID_PICK")
        self.assertFalse(decision["event_pipeline_scanned"])
        counts = decision["event_coverage"]["positive_event_enrichment"]["by_market"]["us"]
        self.assertEqual(counts["scanned_candidate_count"], 1)
        self.assertEqual(counts["source_unavailable_count"], 1)
        self.assertEqual(counts["not_selected_count"], 1)


if __name__ == "__main__":
    unittest.main()

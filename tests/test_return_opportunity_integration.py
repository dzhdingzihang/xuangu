from __future__ import annotations

import copy
import datetime as dt
import json
import math
import unittest
from unittest import mock

import return_opportunity
import server
from market_calendar import session_dates
from scripts import build_worker_assets
from tests.test_build_worker_assets import runtime_quote_candidate, runtime_snapshot_fixture


def opportunity_candidate(code: str) -> dict:
    dates = session_dates("us", dt.date(2026, 5, 1), dt.date(2026, 8, 25))[-40:]
    bars = []
    close = 100.0
    for index, date in enumerate(dates):
        previous = close
        close *= 1.005 + math.sin(index) * 0.001
        bars.append({
            "date": date.isoformat(), "open": previous, "high": close * 1.005,
            "low": previous * 0.995, "close": close, "volume": 2_000_000,
        })
    return {
        "code": code, "symbol": code, "name": code, "entry_price": close, "price": close,
        "realtime": {"price": close, "source": "fixture",
                     "source_as_of": "2026-08-25T16:00:00-04:00",
                     "fetched_at": "2026-08-26T10:00:00+08:00", "volume_unit": "share"},
        "kline": bars, "legacy": {"recommendation_degree": 48},
        "v2": {"rank": 150, "rule_score": 50},
        "serenity": {"score": 42, "principles": ["preserve original factors"]},
    }


class ReturnOpportunityIntegrationTests(unittest.TestCase):
    def build_ranked_snapshot(self) -> tuple[dict, list[dict]]:
        snapshot = runtime_snapshot_fixture()
        snapshot["events"] = {"items": []}
        candidates = [opportunity_candidate(f"R{index:03d}") for index in range(21)]
        metadata = {candidate["code"]: {"industry": "Semiconductors" if index < 15 else "Banking"}
                    for index, candidate in enumerate(candidates)}
        snapshot["return_opportunities"] = return_opportunity.build_return_opportunities(
            snapshot, {"us": candidates}, metadata_by_market={"us": metadata},
        )
        return snapshot, candidates

    def test_top_twelve_have_details_without_obtaining_production_authority(self) -> None:
        snapshot, source_candidates = self.build_ranked_snapshot()
        source_by_code = {row["code"]: row for row in source_candidates}
        opportunity = snapshot["return_opportunities"]
        self.assertEqual(return_opportunity.validate_return_opportunities(opportunity), [])
        self.assertEqual(len(opportunity["candidates"]), 12)
        self.assertGreater(opportunity["candidates"][-1]["rank"], 12)
        before_production = copy.deepcopy(snapshot["production_decision"])
        source_bytes = json.dumps(snapshot).encode()

        detail = build_worker_assets.build_worker_ui_candidates(snapshot, source_bytes)
        live = build_worker_assets.build_worker_live_index(snapshot, source_bytes)
        by_code = {row["code"]: row for row in detail["candidates"]}
        for row in opportunity["candidates"]:
            code = row["code"]
            self.assertEqual(by_code[code]["decision_roles"]["research"], "PRIORITY")
            self.assertEqual(by_code[code]["decision_roles"]["production"], "NONE")
            self.assertEqual(by_code[code]["decision_role"], "research_priority")
            self.assertNotIn("production_rank", by_code[code])
            self.assertNotIn("production_qualification", by_code[code])
            self.assertEqual(by_code[code]["kline"], source_by_code[code]["kline"])
            self.assertEqual(by_code[code]["legacy"], source_by_code[code]["legacy"])
            self.assertEqual(by_code[code]["serenity"], source_by_code[code]["serenity"])
            self.assertIn(code, live["candidates"]["us"])
        self.assertEqual(live["formal_qualified_candidate_count"], 1)
        self.assertEqual(detail["production_selection"]["qualified_candidate_count"], 1)
        self.assertEqual(snapshot["production_decision"], before_production)

    def test_compact_bootstrap_preserves_research_boundary_and_removes_nested_kline(self) -> None:
        snapshot, _ = self.build_ranked_snapshot()
        original = copy.deepcopy(snapshot["return_opportunities"])
        source_bytes = json.dumps(snapshot).encode()
        bootstrap = build_worker_assets.build_worker_ui_bootstrap(snapshot, {}, source_bytes)
        compact = bootstrap["return_opportunities"]
        encoded = json.dumps(compact)
        self.assertNotIn('"candidate_snapshot"', encoded)
        self.assertNotIn('"kline"', encoded)
        self.assertNotIn('"excluded_candidates"', encoded)
        self.assertIs(compact["production_eligible"], False)
        self.assertIsNone(compact["probability"])
        self.assertIsNone(compact["expected_net_return"])
        self.assertEqual(compact["primary"], compact["candidates"][0])
        self.assertEqual([row["rank"] for row in compact["candidates"]],
                         [row["rank"] for row in original["candidates"]])
        self.assertEqual(bootstrap["production_decision"]["qualified_candidate_count"], 1)
        self.assertEqual(snapshot["return_opportunities"], original)

    def test_same_symbol_can_be_research_and_formal_without_inflating_count(self) -> None:
        snapshot = runtime_snapshot_fixture()
        candidate = runtime_quote_candidate("PFE", "us", price=28)
        snapshot["return_opportunities"] = {"candidates": [{
            "market": "us", "code": "PFE", "production_eligible": False,
            "candidate_snapshot": candidate,
        }]}
        details = build_worker_assets.build_worker_ui_candidates(snapshot, json.dumps(snapshot).encode())
        matching = [row for row in details["candidates"] if row["code"] == "PFE"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["decision_roles"], {"production": "PRIMARY", "legacy": "NONE", "research": "PRIORITY"})
        self.assertEqual(details["production_selection"]["qualified_candidate_count"], 1)

    def test_reference_metadata_does_not_copy_legacy_lenses_or_insert_pool_members(self) -> None:
        references = {
            "a_share": [{"symbol": "300502", "name": "Reference A", "themes": ["Optics"], "role": "Optics", "lens": {"score": 999}}],
            "hk": [{"symbol": "0700.HK", "name": "Reference HK", "themes": ["Internet"], "role": "Internet", "score": 999}],
            "us": [{"symbol": "ABSENT", "name": "Not recalled", "themes": ["Software"], "role": "Software", "lens": {"score": 999}}],
        }
        before = copy.deepcopy(references)
        with mock.patch.object(server, "market_universe", side_effect=lambda market: references[market]):
            metadata = server.opportunity_reference_metadata()
        for mapping in metadata.values():
            for row in mapping.values():
                self.assertEqual(set(row), {"name", "role", "themes", "source"})
        candidate = opportunity_candidate("REAL")
        original_candidate = copy.deepcopy(candidate)
        snapshot = runtime_snapshot_fixture()
        snapshot["events"] = {"items": []}
        model = return_opportunity.build_return_opportunities(snapshot, {"us": [candidate]}, metadata_by_market=metadata)
        self.assertEqual(model["evaluated_count"], 1)
        self.assertNotIn("ABSENT", {row["code"] for row in model["candidates"]})
        self.assertEqual(candidate, original_candidate)
        metadata["us"]["ABSENT"]["themes"].append("mutation")
        self.assertEqual(references, before)


if __name__ == "__main__":
    unittest.main()

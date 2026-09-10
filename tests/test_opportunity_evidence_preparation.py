from __future__ import annotations

import copy
import datetime as dt
from contextlib import contextmanager, ExitStack
import unittest
from unittest import mock

import server
from tests.test_build_worker_assets import runtime_quote_candidate, runtime_snapshot_fixture


MOMENT = dt.datetime(2026, 9, 10, 8, 12, tzinfo=dt.timezone.utc)
CUTOFF = MOMENT + dt.timedelta(seconds=8)
MARKETS = ("a_share", "hk", "us")


def generation_fixture():
    """Small full pools whose order and membership differ from visible picks."""
    snapshot = runtime_snapshot_fixture()
    snapshot["events"] = {"items": [], "pipeline": {"status": "NOT_SCANNED"}}
    codes = {"a_share": ["600030", "600010", "600020"],
             "hk": ["0300.HK", "0100.HK", "0200.HK"],
             "us": ["CCC", "AAA", "BBB"]}
    for market in MARKETS:
        rows = [runtime_quote_candidate(code, market) for code in codes[market]]
        snapshot["markets"][market]["_candidate_pool"] = rows
        # This copy represents a shortlist row that has lost full-pool fields.
        # Same-code deduplication must keep the complete row and its position.
        snapshot["markets"][market]["decision"] = {
            "primary": {"code": codes[market][1], "name": "shortlist copy"},
            "watchlist": [{"code": codes[market][1], "name": "another copy"}],
        }
    return snapshot, codes


def frozen_metadata(codes):
    return {
        market: {code: {"sector_metadata": {
            "name": "Fixture classification", "status": "FRESH", "stale": False,
            "source": "eastmoney_public_classification", "source_field": "f100",
            "retrieved_at": MOMENT.isoformat(),
            "taxonomy": "eastmoney_sector" if market == "us" else "eastmoney_industry",
        }} for code in symbols}
        for market, symbols in codes.items()
    }


@contextmanager
def isolate_snapshot_models(snapshot):
    """Exercise orchestration while keeping unrelated factor models bounded."""
    windows = {market: {"entry_trade_date": "2026-08-27", "forecast_end_trade_date": "2026-09-09"}
               for market in MARKETS}
    global_decision = copy.deepcopy(snapshot["global_decision"])
    global_decision["automatic_external_evidence_count"] = 0
    production = copy.deepcopy(snapshot["production_decision"])
    with ExitStack() as stack:
        for target, name, kwargs in (
            (server, "automation_metadata", {"return_value": {}}),
            (server, "market_trade_windows", {"return_value": windows}),
            (server, "enrich_market_candidates", {"side_effect": lambda rows, *args: rows}),
            (server, "classify_market_regime", {"return_value": {"state": "FIXTURE"}}),
            (server, "build_event_feed", {"return_value": copy.deepcopy(snapshot["events"])}),
            (server, "build_global_ten_day_decision", {"return_value": global_decision}),
            (server.production_rule_model, "build_production_rule_inputs", {"return_value": {"rows": []}}),
            (server.production_rule_model, "build_production_decision", {"return_value": production}),
            (server.sector_metadata, "enrich_sector_metadata", {"side_effect": AssertionError("historical/summary path fetched classifications")}),
            (server.requests.sessions.Session, "request", {"side_effect": AssertionError("unexpected live request")}),
        ):
            stack.enter_context(mock.patch.object(target, name, **kwargs))
        yield


class OpportunityEvidencePreparationTests(unittest.TestCase):
    def test_preparation_freezes_evidence_and_passes_every_market_pool_to_preliminary_builder(self):
        snapshot, codes = generation_fixture()
        original_pools = {market: copy.deepcopy(section["_candidate_pool"])
                          for market, section in snapshot["markets"].items()}
        references = {"a_share": {"REFERENCE_ONLY": {"themes": ["Curated theme"]}}}
        metadata = frozen_metadata(codes)
        diagnostics = {"status": "COMPLETE", "candidate_count": 9, "fresh_count": 9,
                       "markets": {market: {"coverage_pct": 100.0} for market in MARKETS}}
        preliminary = {"version": "preliminary-fixture", "candidates": [
            {"market": "us", "code": "CCC", "rank": 1},
        ]}

        def build(current, pools, *, metadata_by_market):
            self.assertIs(current, snapshot)
            self.assertEqual(set(pools), set(MARKETS))
            for market in MARKETS:
                self.assertEqual([row["code"] for row in pools[market]], codes[market])
                self.assertEqual(pools[market], original_pools[market])
            self.assertEqual(current["opportunity_metadata"], metadata)
            self.assertEqual(current["sector_metadata_coverage"], diagnostics)
            self.assertEqual(metadata_by_market, metadata)
            self.assertEqual(current["feature_cutoff_at"], CUTOFF.isoformat(timespec="microseconds"))
            return preliminary

        with (
            mock.patch.object(server, "opportunity_reference_metadata", return_value=references) as reference,
            mock.patch.object(server.sector_metadata, "enrich_sector_metadata", return_value=(metadata, diagnostics)) as enrich,
            mock.patch.object(server, "now_cn", return_value=CUTOFF),
            mock.patch.object(server.return_opportunity, "build_return_opportunities", side_effect=build) as builder,
            mock.patch.object(server.requests.sessions.Session, "request", side_effect=AssertionError("unexpected live request")),
        ):
            server.prepare_opportunity_evidence(snapshot, moment=MOMENT)
        reference.assert_called_once_with()
        enrich.assert_called_once()
        self.assertEqual(enrich.call_args.args[0], references)
        for market in MARKETS:
            self.assertEqual([row["code"] for row in enrich.call_args.args[1][market]], codes[market])
        self.assertEqual(enrich.call_args.kwargs["now"], MOMENT)
        self.assertEqual(enrich.call_args.kwargs["cache_path"], server.CACHE / "runtime-cache" / "sector_metadata.json")
        builder.assert_called_once()
        self.assertEqual(snapshot["return_opportunities"], preliminary)
        self.assertEqual(snapshot["opportunity_metadata"], metadata)
        self.assertEqual(snapshot["sector_metadata_coverage"], diagnostics)
        self.assertNotIn("REFERENCE_ONLY", [row["code"] for row in snapshot["markets"]["a_share"]["_candidate_pool"]])
        for market in MARKETS:
            self.assertEqual(snapshot["markets"][market]["_candidate_pool"], original_pools[market])

    def test_preparation_default_clock_separates_fetch_anchor_from_completed_evidence_cutoff(self):
        snapshot, codes = generation_fixture()
        metadata = frozen_metadata(codes)
        with (
            mock.patch.object(server, "opportunity_reference_metadata", return_value={}),
            mock.patch.object(server.sector_metadata, "enrich_sector_metadata", return_value=(metadata, {})) as enrich,
            mock.patch.object(server.return_opportunity, "build_return_opportunities", return_value={}),
            mock.patch.object(server, "now_cn", side_effect=[MOMENT, CUTOFF]),
        ):
            server.prepare_opportunity_evidence(snapshot)
        self.assertEqual(enrich.call_args.kwargs["now"], MOMENT)
        self.assertEqual(snapshot["feature_cutoff_at"], CUTOFF.isoformat(timespec="microseconds"))

    def test_final_build_uses_frozen_metadata_and_full_pools_before_compaction(self):
        snapshot, codes = generation_fixture()
        metadata = frozen_metadata(codes)
        diagnostics = {"status": "PARTIAL", "fresh_count": 8, "missing_count": 1}
        snapshot["opportunity_metadata"] = metadata
        snapshot["sector_metadata_coverage"] = diagnostics
        snapshot["return_opportunities"] = {"version": "preliminary"}
        snapshot["events"] = {"items": [], "pipeline": {"status": "SUCCESS", "scanned_symbols": {"us": ["CCC"]}}}
        frozen_before = copy.deepcopy(metadata)
        final = {"version": "final-after-official-scan", "candidates": []}

        def build(current, pools, *, metadata_by_market):
            self.assertEqual(current["events"]["pipeline"]["scanned_symbols"], {"us": ["CCC"]})
            self.assertEqual(metadata_by_market, frozen_before)
            for market in MARKETS:
                self.assertIn("_candidate_pool", current["markets"][market])
                self.assertEqual([row["code"] for row in pools[market]], codes[market])
            return final

        with (
            isolate_snapshot_models(snapshot),
            mock.patch.object(server, "opportunity_reference_metadata", side_effect=AssertionError("frozen metadata replaced")),
            mock.patch.object(server.return_opportunity, "build_return_opportunities", side_effect=build) as builder,
        ):
            result = server.enrich_snapshot_v2(snapshot)
        builder.assert_called_once()
        self.assertEqual(result["return_opportunities"], final)
        self.assertEqual(result["opportunity_metadata"], frozen_before)
        self.assertEqual(result["sector_metadata_coverage"], diagnostics)
        self.assertTrue(all("_candidate_pool" not in section for section in result["markets"].values()))

    def test_archived_snapshot_preserves_frozen_opportunities_without_network_or_reranking(self):
        snapshot = runtime_snapshot_fixture()
        snapshot["events"] = {"items": [], "pipeline": {"status": "PARTIAL"}}
        archived = {"version": "historical-score-version", "generated_at": snapshot["generated_at"],
                    "candidates": [{"market": "us", "code": "REMOVED", "rank": 1, "opportunity_score": 78.125}]}
        snapshot["return_opportunities"] = copy.deepcopy(archived)
        snapshot["opportunity_metadata"] = {"us": {"REMOVED": {"industry": "Historical classification"}}}
        snapshot["sector_metadata_coverage"] = {"status": "PARTIAL", "fresh_count": 1}
        evidence_before = copy.deepcopy(snapshot["opportunity_metadata"])
        with (
            isolate_snapshot_models(snapshot),
            mock.patch.object(server, "prepare_opportunity_evidence", side_effect=AssertionError("archive triggered preparation")),
            mock.patch.object(server, "opportunity_reference_metadata", side_effect=AssertionError("archive read current reference metadata")),
            mock.patch.object(server.return_opportunity, "build_return_opportunities", side_effect=AssertionError("archive reranked")),
        ):
            result = server.enrich_snapshot_v2(snapshot)
        self.assertEqual(result["return_opportunities"], archived)
        self.assertEqual(result["opportunity_metadata"], evidence_before)
        self.assertEqual(result["sector_metadata_coverage"], {"status": "PARTIAL", "fresh_count": 1})

    def test_legacy_archive_without_opportunity_contract_is_not_backfilled(self):
        snapshot = runtime_snapshot_fixture()
        snapshot["events"] = {"items": []}
        with (
            isolate_snapshot_models(snapshot),
            mock.patch.object(server, "opportunity_reference_metadata", side_effect=AssertionError("archive read references")),
            mock.patch.object(server.return_opportunity, "build_return_opportunities", side_effect=AssertionError("archive backfilled ranking")),
        ):
            result = server.enrich_snapshot_v2(snapshot)
        self.assertNotIn("return_opportunities", result)
        self.assertNotIn("opportunity_metadata", result)
        self.assertNotIn("sector_metadata_coverage", result)


if __name__ == "__main__":
    unittest.main()

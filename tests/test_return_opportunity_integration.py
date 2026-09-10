from __future__ import annotations

import copy
import datetime as dt
import json
import math
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import return_opportunity
import server
from market_calendar import session_dates
from scripts import build_worker_assets, verify_deployment
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
    def test_standalone_deployment_verifier_can_load_opportunity_publisher(self) -> None:
        verifier = pathlib.Path(server.__file__).parent / "scripts" / "verify_deployment.py"
        program = """
import runpy, sys
namespace = runpy.run_path(sys.argv[1])
errors = namespace['ui_api_contract_errors'](
    {'return_opportunities': {'candidates': []}},
    {'latest-summary': {'ok': True, 'latest': {}}},
    source_snapshot_sha256='a' * 64, source_snapshot_byte_size=1,
)
assert any('return_opportunities' in error for error in errors), errors
"""
        with tempfile.TemporaryDirectory() as outside_repo:
            result = subprocess.run(
                [sys.executable, "-I", "-c", program, str(verifier)],
                cwd=outside_repo, capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tencent_overlay_and_compaction_keep_bar_provenance(self) -> None:
        response = mock.Mock()
        response.json.return_value = {"data": {"sh600000": {"qfqday": [
            ["2026-08-24", "10", "10.1", "10.2", "9.9", "12000"],
        ]}}}
        with mock.patch.object(server, "requests_get_with_retry", return_value=response):
            history = server.tencent_stock_kline("600000", 32, require_qfq=True)
        original = copy.deepcopy(history)
        self.assertEqual(history[0]["volume_unit"], "lot")
        self.assertEqual(history[0]["price_adjustment"], "tencent_qfqday")
        quote = {
            "price": 10.2, "open": 10.1, "high": 10.3, "low": 10.0,
            "volume": 15000, "amount_wan": 1530,
            "realtime": {"source_as_of": "2026-08-25T14:55:00+08:00", "volume_unit": "lot"},
        }
        overlaid = server.overlay_a_share_quote_bar(history, quote)
        compact = server.compact_kline(overlaid)
        self.assertEqual(len(compact), 2)
        self.assertEqual(compact[0]["price_adjustment"], "tencent_qfqday")
        self.assertTrue(all(row["volume_unit"] == "lot" for row in compact))
        self.assertEqual(compact[-1]["amount"], 15_300_000)
        self.assertEqual(compact[-1]["volume"], 15000)
        self.assertEqual(history, original)

    def test_mixed_lots_and_shares_produce_equivalent_liquidity_and_volume_scores(self) -> None:
        share_candidate = opportunity_candidate("600000")
        share_candidate["realtime"].update({
            "source_as_of": "2026-08-26T09:45:00+08:00", "volume_unit": "lot",
        })
        for row in share_candidate["kline"]:
            row.update({"volume_unit": "share", "price_adjustment": "yahoo_adjclose_factor_v1", "amount": 42_000_000})
        mixed_candidate = copy.deepcopy(share_candidate)
        for row in mixed_candidate["kline"][-5:]:
            row["volume"] /= 100
            row.update({"volume_unit": "lot", "price_adjustment": "tencent_qfqday"})
        share_candidate["kline"] = server.compact_kline(share_candidate["kline"])
        mixed_candidate["kline"] = server.compact_kline(mixed_candidate["kline"])
        snapshot = runtime_snapshot_fixture()
        snapshot["events"] = {"items": []}
        reference = return_opportunity.build_return_opportunities(snapshot, {"a_share": [share_candidate]})
        mixed = return_opportunity.build_return_opportunities(snapshot, {"a_share": [mixed_candidate]})
        self.assertEqual(reference["eligible_count"], 1)
        self.assertEqual(mixed["eligible_count"], 1)
        left, right = reference["primary"], mixed["primary"]
        self.assertEqual(left["metrics"]["volume_ratio_5d_20d"], 1.0)
        self.assertEqual(right["metrics"]["volume_ratio_5d_20d"], 1.0)
        self.assertEqual(right["metrics"]["median_daily_traded_value"], 42_000_000)
        self.assertEqual(left["opportunity_score"], right["opportunity_score"])
        self.assertEqual(left["components"]["trend_volume"], right["components"]["trend_volume"])

    def test_deployment_verifies_exact_optional_frozen_opportunity_summary(self) -> None:
        local, _ = self.build_ranked_snapshot()
        expected = build_worker_assets.summarize_return_opportunities(local)
        spec = verify_deployment.UI_ASSET_SPECS["latest-summary"]
        payload = {
            "ok": True, "contract_version": spec["contract_version"],
            "latest": {"return_opportunities": copy.deepcopy(expected)}, "status": {},
        }
        with (
            mock.patch.dict(verify_deployment.UI_ASSET_SPECS, {"latest-summary": spec}, clear=True),
            mock.patch.object(verify_deployment, "_ui_identity_errors", return_value=[]),
            mock.patch.object(verify_deployment, "_snapshot_use_errors", return_value=[]),
        ):
            def errors(snapshot, published):
                return verify_deployment.ui_api_contract_errors(
                    snapshot, {"latest-summary": published},
                    source_snapshot_sha256="a" * 64, source_snapshot_byte_size=1,
                )

            self.assertEqual(errors(local, payload), [])
            for change in ("missing", "score_changed", "authority_changed"):
                altered = copy.deepcopy(payload)
                if change == "missing":
                    altered["latest"].pop("return_opportunities")
                elif change == "score_changed":
                    altered["latest"]["return_opportunities"]["candidates"][0]["opportunity_score"] += 0.01
                else:
                    altered["latest"]["return_opportunities"]["production_eligible"] = True
                with self.subTest(change=change):
                    self.assertTrue(any("do not match the frozen research ranking" in error for error in errors(local, altered)))
            legacy = {key: value for key, value in local.items() if key != "return_opportunities"}
            legacy_payload = copy.deepcopy(payload)
            legacy_payload["latest"].pop("return_opportunities")
            self.assertEqual(errors(legacy, legacy_payload), [])

    def build_ranked_snapshot(self) -> tuple[dict, list[dict]]:
        snapshot = runtime_snapshot_fixture()
        snapshot["events"] = {"items": []}
        candidates = [opportunity_candidate(f"R{index:03d}") for index in range(21)]
        metadata = {candidate["code"]: {"sector_metadata": {
                        "name": "Semiconductors" if index < 15 else "Banking",
                        "source": "verified-fixture-classification", "status": "FRESH",
                        "retrieved_at": "2026-08-25T16:00:00-04:00", "stale": False,
                    }}
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
        self.assertEqual(compact["primary"], {key: compact["candidates"][0][key] for key in ("market", "code", "rank", "opportunity_score")})
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

from __future__ import annotations

import copy
import unittest

import server
from scripts.validate_snapshot import validate_snapshot
from tests.test_selector_v2 import fixture_candidate


def snapshot_fixture() -> dict:
    markets = {}
    for market_key, code in (("a_share", "603228"), ("hk", "0700.HK"), ("us", "NVDA")):
        row = fixture_candidate()
        row["code"] = code
        row["symbol"] = code
        row["market_key"] = market_key
        row.pop("candidate_lineage", None)
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
            "stats": {},
        }
    return {
        "model_version": "legacy-fixture",
        "generated_at": "2026-08-19T16:30:00+08:00",
        "market": {"risk": "normal", "items": []},
        "markets": markets,
    }


class SnapshotContractTests(unittest.TestCase):
    def test_three_markets_keep_old_fields_and_add_v2_contract(self) -> None:
        snapshot = snapshot_fixture()
        legacy_actions = {key: section["decision"]["action"] for key, section in snapshot["markets"].items()}
        enriched = server.enrich_snapshot_v2(snapshot)
        self.assertEqual(enriched["schema_version"], server.SCHEMA_VERSION)
        self.assertEqual(enriched["selector_mode"], server.SELECTOR_MODE)
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

    def test_snapshot_validator_accepts_shadow_fallback_and_rejects_decision_participation(self) -> None:
        enriched = server.enrich_snapshot_v2(snapshot_fixture())
        self.assertEqual(validate_snapshot(enriched), [])
        enriched["analysis_models"]["dual_low"]["participates_in_decision"] = True
        self.assertIn("dual-low model must not participate in the decision", validate_snapshot(enriched))


if __name__ == "__main__":
    unittest.main()

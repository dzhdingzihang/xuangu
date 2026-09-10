from __future__ import annotations

import copy
import datetime as dt
import json
import math
import unittest
from unittest.mock import patch

import event_pipeline
from market_calendar import expected_quote_session, session_dates
from return_opportunity import build_return_opportunities, validate_return_opportunities


CUTOFF = "2026-09-09T20:21:00+08:00"


def candidate(code="TEST", *, market="us", drift=0.7, noise=0.9, sector=None, amount=50_000_000):
    last = expected_quote_session(market, CUTOFF)
    dates = session_dates(market, last - dt.timedelta(days=100), last)[-60:]
    price = 70.0
    bars = []
    for index, date in enumerate(dates):
        previous = price
        price *= 1 + (drift + (noise if index % 2 else -noise)) / 100
        bars.append({"date": date.isoformat(), "open": previous, "high": max(price, previous) * 1.005,
                     "low": min(price, previous) * 0.995, "close": price, "volume": 2_000_000,
                     "volume_unit": "share", "amount": amount})
    source = last.isoformat() + ("T16:00:00-04:00" if market == "us" else "T16:00:00+08:00")
    row = {"code": code, "name": code, "price": price, "kline": bars,
           "realtime": {"price": price, "source_as_of": source, "source": "test", "quote_status": "LAST_CLOSE"},
           "legacy_complete": False, "recommendation_degree": 20,
           "estimated_10d_range": {"low_pct": -25, "high_pct": 30},
           "probability": 0.99, "shadow_model": {"probability": 0.99}}
    if sector:
        row["sector"] = sector
        row["sector_metadata"] = {"name": sector, "source": "fixture_verified_provider", "retrieved_at": "2026-09-08T12:00:00Z",
                                  "status": "FRESH", "stale": False, "taxonomy": "fixture_industry", "granularity": "industry"}
    return row


def build(rows, market="us", **snapshot_fields):
    snapshot = {"generated_at": CUTOFF, "global_decision": {"evaluated_candidates": []}}
    snapshot.update(snapshot_fields)
    return build_return_opportunities(snapshot, {market: rows})


class ReturnOpportunityTests(unittest.TestCase):
    def test_stronger_returns_at_equal_risk_rank_first(self):
        result = build([candidate("SLOW", drift=0.2), candidate("FAST", drift=0.9)])
        self.assertEqual(result["primary"]["code"], "FAST")
        scores = {row["code"]: row["opportunity_score"] for row in result["candidates"] + result["excluded_candidates"]}
        self.assertGreater(scores["FAST"], scores["SLOW"])
        self.assertEqual(validate_return_opportunities(result), [])

    def test_high_volatility_is_not_rejected_by_legacy_downside_cap(self):
        result = build([candidate("ELASTIC", drift=0.8, noise=4.5)])
        self.assertEqual(result["eligible_count"], 1)
        row = result["primary"]
        self.assertLess(row["scenario_range"]["low_pct"], -7.5)
        self.assertIn("HIGH_VOLATILITY_REDUCE_SIZE", row["risk_flags"])
        self.assertLess(row["risk_budget"]["illustrative_weight_pct"], 5)
        self.assertFalse(row["risk_budget"]["guaranteed_stop"])

    def test_no_sector_name_or_shadow_prediction_bonus(self):
        a = candidate("A", sector="银行")
        b = candidate("B", sector="半导体")
        b["probability"] = 1
        b["shadow_model"]["probability"] = 1
        a["estimated_10d_range"] = {"low_pct": -3, "high_pct": 4}
        b["estimated_10d_range"] = {"low_pct": -20, "high_pct": 80}
        result = build([b, a])
        self.assertEqual([row["code"] for row in result["candidates"]], ["A", "B"])
        self.assertEqual(result["candidates"][0]["opportunity_score"], result["candidates"][1]["opportunity_score"])
        self.assertIsNone(result["probability"])
        self.assertIsNone(result["expected_net_return"])

    def test_missing_filing_scan_keeps_research_with_explicit_uncertainty(self):
        result = build([candidate("AVAILABLE"), candidate("DOWN", drift=-1)])
        row = result["primary"]
        self.assertEqual(row["qualification_status"], "RESEARCH_ELIGIBLE")
        self.assertEqual(row["event_coverage"]["status"], "NOT_SCANNED")
        self.assertFalse(row["event_coverage"]["verified"])
        self.assertFalse(row["event_coverage"]["negative_clearance_verified"])
        self.assertIn("OFFICIAL_EVENT_NOT_SCANNED", row["risk_flags"])
        self.assertIn("NEGATIVE_EVENT_COVERAGE_INCOMPLETE", row["risk_flags"])
        self.assertEqual(result["excluded_candidates"][0]["event_coverage"]["status"], "NOT_SCANNED")
        self.assertEqual(result["market_summaries"]["us"]["event_scanned_count"], 0)

    def test_shortlist_targets_preserve_displayed_rows_before_ranked_overscan(self):
        rows = [candidate(f"A{index:02}", sector="Sector A") for index in range(20)]
        rows += [candidate(f"B{index:02}", sector="Sector B") for index in range(10)]
        result = build(rows)
        selected = [row["code"] for row in result["candidates"]]
        targets = result["event_scan_targets_by_market"]["us"]
        self.assertEqual(targets[:12], selected)
        self.assertEqual(len(targets), 24)
        self.assertEqual(len(set(targets)), 24)

    def test_partial_source_keeps_negative_exclusion_and_failed_candidate_uncertainty(self):
        now = dt.datetime.fromisoformat(CUTOFF)
        rows = [candidate(code) for code in ("NEGATIVE", "FAILED", "EMPTY")]
        snapshot = {"generated_at": CUTOFF, "markets": {"us": {"_candidate_pool": rows}}}
        negative = event_pipeline._event(market="us", symbol="NEGATIVE", title="profit warning",
            url="https://www.sec.gov/Archives/edgar/data/1/warning.htm", released_at=now - dt.timedelta(hours=1),
            run_id="partial-run", source_document_id="warning-1")
        collected = {"items": [negative], "successful_symbols": ["EMPTY", "NEGATIVE"],
                     "failed_symbols": {"FAILED": "OSError"}}
        with patch.object(event_pipeline, "_collect_us", return_value=collected):
            snapshot["events"] = event_pipeline.collect_for_snapshot(snapshot, "partial-run", now=now,
                fetcher=lambda *args, **kwargs: self.fail("Unexpected network request"))
        result = build_return_opportunities(snapshot, {"us": rows})
        excluded = result["excluded_candidates"][0]
        self.assertEqual(excluded["code"], "NEGATIVE")
        self.assertIn("MATERIAL_NEGATIVE_EVENT", excluded["qualification_blockers"])
        self.assertEqual(excluded["event_coverage"]["status"], "SUCCESS")
        failed = next(row for row in result["candidates"] if row["code"] == "FAILED")
        self.assertEqual(failed["event_coverage"]["status"], "ERROR")
        self.assertIn("OFFICIAL_EVENT_SCAN_ERROR", failed["risk_flags"])
        empty = next(row for row in result["candidates"] if row["code"] == "EMPTY")
        self.assertEqual(empty["event_coverage"]["status"], "SUCCESS")
        self.assertFalse(empty["event_coverage"]["negative_clearance_verified"])
        self.assertEqual(validate_return_opportunities(result), [])

    def test_missing_and_invalid_input_fail_closed(self):
        mutations = {
            "time": lambda row: row["realtime"].pop("source_as_of"),
            "stale": lambda row: row["realtime"].update(stale=True),
            "price": lambda row: (row["realtime"].update(price=-1), row.update(price=-1)),
            "history": lambda row: row.update(kline=row["kline"][-12:]),
            "nan": lambda row: row["kline"][-1].update(close=math.nan),
            "high": lambda row: row["kline"][-1].update(high=1),
            "halt": lambda row: row.update(suspended=True),
            "liquidity": lambda row: [bar.update(amount=1) for bar in row["kline"]],
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                row = candidate()
                mutate(row)
                result = build([row])
                self.assertEqual(result["status"], "NO_OPPORTUNITY")
                self.assertEqual(result["excluded_count"], 1)
                json.dumps(result, allow_nan=False)

    def test_negative_trend_and_extreme_chase_stay_blocked(self):
        result = build([candidate("DOWN", drift=-1), candidate("CHASE", drift=6, noise=0.2)])
        blockers = {row["code"]: row["qualification_blockers"] for row in result["excluded_candidates"]}
        self.assertIn("NEGATIVE_TREND", blockers["DOWN"])
        self.assertIn("EXTREME_CHASE", blockers["CHASE"])

    def test_repeated_same_material_catalyst_does_not_inflate_score(self):
        event = {"event_id": "one", "event_cluster_id": "plan-a", "direction": "positive", "decision_eligible": True,
                 "materiality_verified": True, "buyback_pct_of_shares": 2, "title": "回购计划"}
        with patch("return_opportunity.event_is_auditable", return_value=True):
            single = build([candidate()], events={"items": [event]})
            repeated = build([candidate()], events={"items": [dict(event, event_id=str(n)) for n in range(7)]})
        self.assertEqual(single["primary"]["opportunity_score"], repeated["primary"]["opportunity_score"])
        self.assertEqual(repeated["primary"]["metrics"]["event_cluster_count"], 1)

    def test_routine_buybacks_have_no_materiality_bonus(self):
        event = {"event_id": "one", "direction": "positive", "decision_eligible": True,
                 "materiality": "high", "title": "Next Day Disclosure Return - Share Repurchase"}
        with patch("return_opportunity.event_is_auditable", return_value=True):
            result = build([candidate()], events={"items": [event] * 5})
        self.assertEqual(result["primary"]["components"]["material_event"]["score"], 0)

    def test_ties_and_sector_diversity_have_stable_true_ranks(self):
        rows = [candidate(f"A{index:02}", sector="Sector A") for index in range(10)]
        rows += [candidate(f"B{index:02}", sector="Sector B") for index in range(4)]
        rows += [candidate(f"C{index:02}", sector="Sector C") for index in range(4)]
        first, second = build(rows), build(list(reversed(rows)))
        self.assertEqual(first, second)
        self.assertEqual(len(first["candidates"]), 12)
        self.assertEqual(sum(row["sector"]["name"] == "Sector A" for row in first["candidates"]), 4)
        self.assertGreater(first["candidates"][4]["rank"], 5)
        self.assertEqual(validate_return_opportunities(first), [])

    def test_generic_dynamic_role_does_not_fake_sector(self):
        row = candidate()
        row.update(role="动态市场召回", themes=["动量"])
        result = build([row])
        self.assertEqual(result["primary"]["sector"]["status"], "MISSING")
        self.assertEqual(result["primary"]["components"]["sector_strength"]["score"], 50)

    def test_verified_sector_provenance_precedes_candidate_theme(self):
        row = candidate()
        row.update(role="AI产业链", themes=["光模块"])
        metadata = {"us": {"TEST": {"sector_metadata": {
            "name": "Technology", "source": "eastmoney_public_classification", "source_field": "f100",
            "taxonomy": "eastmoney_sector", "granularity": "sector", "retrieved_at": "2026-09-09T12:00:00Z",
            "status": "FRESH", "stale": False}}}}
        result = build_return_opportunities({"generated_at": CUTOFF}, {"us": [row]}, metadata)
        sector = result["primary"]["sector"]
        self.assertEqual(sector["name"], "Technology")
        self.assertEqual(sector["source"], "eastmoney_public_classification")
        self.assertEqual(sector["retrieved_at"], "2026-09-09T12:00:00Z")
        self.assertEqual(sector["taxonomy"], "eastmoney_sector")
        self.assertTrue(sector["verified"])

    def test_stale_future_unsourced_and_theme_labels_have_no_industry_strength(self):
        for mode in ("stale", "future", "unsourced", "theme"):
            with self.subTest(mode=mode):
                rows = [candidate(f"FAST{n}", sector="Technology", drift=0.9) for n in range(3)]
                for row in rows:
                    if mode == "stale":
                        row["sector_metadata"].update(retrieved_at="2026-08-01T12:00:00Z", status="STALE", stale=True)
                    elif mode == "future":
                        row["sector_metadata"].update(retrieved_at="2026-09-10T12:00:00Z")
                    else:
                        row.pop("sector_metadata")
                        if mode == "theme":
                            row.pop("sector")
                            row.update(themes=["半导体"])
                result = build(rows + [candidate("SLOW", drift=0.3)])
                target = next(row for row in result["candidates"] if row["code"] == "FAST0")
                self.assertEqual(target["components"]["sector_strength"]["score"], 50)
                self.assertFalse(target["sector"]["verified"])
                self.assertEqual(result["market_summaries"]["us"]["sector_known_count"], 0)
                if mode == "theme":
                    self.assertEqual(target["sector"]["status"], "APPROXIMATE")

    def test_unverified_label_cannot_borrow_fresh_peer_industry_strength(self):
        for status in ("STALE", "UNVERIFIED"):
            with self.subTest(status=status):
                rows = [candidate(f"TECH{n}", sector="Technology", drift=0.9) for n in range(3)]
                rows += [candidate(f"BANK{n}", sector="Banks", drift=0.2) for n in range(4)]
                unknown = candidate("UNKNOWN", sector="Technology", drift=0.7)
                if status == "STALE":
                    unknown["sector_metadata"].update(status="STALE", stale=True)
                else:
                    unknown.pop("sector_metadata")
                result = build(rows + [unknown])
                target = next(row for row in result["candidates"] if row["code"] == "UNKNOWN")
                self.assertEqual(target["sector"]["status"], status)
                self.assertEqual(target["components"]["sector_strength"]["score"], 50)
                self.assertEqual(target["metrics"]["sector_peer_count"], 0)
                known = next(row for row in result["candidates"] if row["code"] == "TECH0")
                self.assertGreater(known["components"]["sector_strength"]["score"], 50)

    def test_quote_price_is_not_trade_plan_entry_and_cutoff_controls_future(self):
        row = candidate()
        row["entry_price"] = 1
        row["realtime"]["source_as_of"] = "2026-09-09T20:25:00+08:00"
        result = build([row], feature_cutoff_at="2026-09-09T20:26:00+08:00")
        self.assertEqual(result["primary"]["reference_quote"]["price"], row["realtime"]["price"])

    def test_a_share_lot_volume_and_yahoo_share_volume_are_equivalent(self):
        share = candidate("000001", market="a_share")
        lot = copy.deepcopy(share)
        for bar in share["kline"]:
            bar.pop("amount")
            bar["price_adjustment"] = "yahoo_adjclose_factor_v1"
            bar.pop("volume_unit")
        for bar in lot["kline"]:
            bar.pop("amount")
            bar["volume"] /= 100
            bar["volume_unit"] = "lot"
        a, b = build([share], "a_share"), build([lot], "a_share")
        self.assertEqual(a["primary"]["metrics"]["median_daily_traded_value"], b["primary"]["metrics"]["median_daily_traded_value"])

    def test_public_contract_rejects_forged_prediction_or_identity(self):
        result = build([candidate()])
        for mutate in (
            lambda value: value.update(probability=0.99),
            lambda value: value["candidates"][0].update(production_eligible=True),
            lambda value: value["candidates"][0]["candidate_snapshot"].update(code="FORGED"),
            lambda value: value.update(eligible_count=20),
            lambda value: value["candidates"][0]["metrics"].update(return_5d_pct=math.nan),
            lambda value: value["candidates"][0].pop("event_coverage"),
            lambda value: value["candidates"][0]["event_coverage"].update(negative_clearance_verified=True),
            lambda value: value["candidates"][0]["risk_flags"].remove("OFFICIAL_EVENT_NOT_SCANNED"),
        ):
            forged = copy.deepcopy(result)
            mutate(forged)
            self.assertTrue(validate_return_opportunities(forged))


if __name__ == "__main__":
    unittest.main()

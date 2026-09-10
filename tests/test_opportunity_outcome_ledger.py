from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import market_calendar
import opportunity_outcome_ledger as ledger


PUBLICATION = "2026-08-21T13:29:00+00:00"
MATURE = "2026-09-10T00:00:00+00:00"


def snapshot(key="2026-08-21_2026-08-20_230000.json", *, version="return-opportunity-score-v1"):
    rows = [{"market": "us", "code": code, "name": code, "rank": index + 1,
        "market_rank": index + 1, "opportunity_score": 80 - index,
        "qualification_status": "RESEARCH_ELIGIBLE", "qualification_blockers": [],
        "score_kind": "RETURN_OPPORTUNITY_RULE_SCORE", "calibrated": False,
        "production_eligible": False, "metrics": {"return_10d_pct": 12 - index}}
        for index, code in enumerate(("AAA", "BBB"))]
    return {"snapshot_key": key, "generated_at": "2026-08-20T23:00:00Z",
        "feature_cutoff_at": "2026-08-21T12:00:00Z", "signal_date": "2026-08-20",
        "return_opportunities": {"contract_version": "return-opportunities-v1",
            "score_version": version, "score_kind": "RETURN_OPPORTUNITY_RULE_SCORE",
            "horizon_trade_days": 10, "calibrated": False, "production_eligible": False,
            "weights": {"momentum": 0.6, "relative_strength": 0.4},
            "selection_policy": {"maximum_displayed": 12}, "candidates": rows,
            "eligible_count": 2, "primary": rows[0], "status": "RESEARCH_READY"}}


def pending(source=None, publication=PUBLICATION):
    return ledger.register_opportunity_snapshot(source or snapshot(), published_at=publication)


def loader(market, code):
    dates = market_calendar.session_dates(market, "2026-08-21", "2026-09-03")
    base = 100 if code == "SPY" else 10
    return ([{"date": day.isoformat(), "open": base + index * .1,
        "high": base + index * .1 + .3, "low": base + index * .1 - .2,
        "close": base + index * .1 + .05} for index, day in enumerate(dates)], "fixture-adjusted", True)


class OpportunityOutcomeTests(unittest.TestCase):
    def test_only_original_published_candidates_are_frozen(self):
        source = snapshot()
        source["production_decision"] = {"qualified_candidates": [{"code": "RULE"}]}
        source["return_opportunities"]["excluded_candidates"] = [{"code": "EXCLUDED"}]
        with mock.patch("return_opportunity.build_return_opportunities", side_effect=AssertionError("must not score history")):
            batch = pending(source)
        self.assertEqual([p["code"] for p in batch["predictions"]], ["AAA", "BBB"])
        self.assertEqual([p["rank"] for p in batch["predictions"]], [1, 2])
        self.assertEqual(batch["predictions"][0]["score_identity"]["weights"], source["return_opportunities"]["weights"])

    def test_publication_cutoff_strict_next_open_and_holiday(self):
        a = pending(publication="2026-09-04T13:30:00Z")
        p = a["predictions"][0]
        self.assertEqual(p["entry_trade_date"], "2026-09-08")
        self.assertGreater(ledger._aware(p["entry_session_open_at"]), ledger._aware(p["published_at"]))
        self.assertEqual(p["forecast_end_trade_date"], "2026-09-21")
        with self.assertRaises(ledger.OpportunityOutcomeContractError):
            ledger.build_opportunity_predictions(snapshot())
        with self.assertRaises(ledger.OpportunityOutcomeContractError):
            pending(publication="2026-08-21T11:00:00Z")

    def test_repeated_publication_keeps_first_verified_anchor(self):
        a = pending()
        self.assertEqual(ledger.register_opportunity_snapshot(snapshot(), published_at="2026-08-22T00:00:00Z", existing=a), a)
        source = snapshot()
        source["opportunity_outcome_tracking"] = {"status": "COLLECTING"}
        self.assertEqual(ledger.register_opportunity_snapshot(source, published_at=MATURE, existing=a), a)
        source["return_opportunities"]["candidates"][0]["opportunity_score"] = 81
        with self.assertRaises(ledger.OpportunityOutcomeConflictError):
            ledger.register_opportunity_snapshot(source, published_at=MATURE, existing=a)

    def test_other_track_enrichment_preserves_original_publication_and_source_identity(self):
        original = pending()
        enriched = snapshot()
        enriched.update(shadow_outcome={"status": "SETTLED", "net_total_return": .1},
                        outcome={"status": "SETTLED"}, formal_sample_status="SETTLED")
        repeated = ledger.register_opportunity_snapshot(enriched, published_at=MATURE, existing=original)
        self.assertEqual(repeated, original)
        self.assertEqual(repeated["source_snapshot_sha256"], original["source_snapshot_sha256"])
        self.assertEqual(repeated["published_at"], original["published_at"])
        self.assertNotEqual(ledger._source_digest(enriched), original["source_snapshot_sha256"])

    def test_republication_rejects_every_frozen_board_policy_time_or_candidate_change(self):
        original = pending()
        mutations = {
            "score_version": lambda s: s["return_opportunities"].update(score_version="return-opportunity-score-v2"),
            "weights": lambda s: s["return_opportunities"].update(weights={"momentum": .5, "relative_strength": .5}),
            "policy": lambda s: s["return_opportunities"]["selection_policy"].update(maximum_displayed=10),
            "board_detail": lambda s: s["return_opportunities"].update(limitations=["changed policy"]),
            "candidate_evidence": lambda s: s["return_opportunities"]["candidates"][0]["metrics"].update(return_10d_pct=13),
            "candidate_code": lambda s: s["return_opportunities"]["candidates"][0].update(code="CHANGED"),
            "candidate_rank": lambda s: s["return_opportunities"]["candidates"][1].update(rank=3),
            "cutoff": lambda s: s.update(feature_cutoff_at="2026-08-21T12:01:00Z"),
            "generated": lambda s: s.update(generated_at="2026-08-20T23:01:00Z"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = snapshot()
                changed["shadow_outcome"] = {"status": "SETTLED"}
                mutate(changed)
                with self.assertRaises(ledger.OpportunityOutcomeContractError):
                    ledger.register_opportunity_snapshot(changed, published_at=MATURE, existing=original)

    def test_empty_board_keeps_score_policy_and_time_evidence_across_enrichment(self):
        empty = snapshot()
        empty["return_opportunities"].update(candidates=[], primary=None, eligible_count=0, status="NO_OPPORTUNITY")
        original = pending(empty)
        self.assertEqual(original["predictions"], [])
        self.assertEqual(original["registration_evidence"]["score_identity"]["weights"], empty["return_opportunities"]["weights"])
        enriched = copy.deepcopy(empty)
        enriched["shadow_outcome"] = {"status": "SETTLED"}
        self.assertEqual(ledger.register_opportunity_snapshot(enriched, published_at=MATURE, existing=original), original)
        for field, value in (("score_version", "another-version"), ("weights", {"momentum": 1.0}),
                             ("selection_policy", {"maximum_displayed": 10})):
            changed = copy.deepcopy(enriched)
            changed["return_opportunities"][field] = value
            with self.assertRaises(ledger.OpportunityOutcomeConflictError):
                ledger.register_opportunity_snapshot(changed, published_at=MATURE, existing=original)
        enriched["feature_cutoff_at"] = "2026-08-21T12:01:00Z"
        with self.assertRaises(ledger.OpportunityOutcomeConflictError):
            ledger.register_opportunity_snapshot(enriched, published_at=MATURE, existing=original)

    def test_legacy_batch_without_board_evidence_fails_closed_on_envelope_change(self):
        original = pending()
        original.pop("registration_evidence")
        original["batch_sha256"] = ledger.batch_sha256(original)
        self.assertEqual(ledger.register_opportunity_snapshot(snapshot(), published_at=MATURE, existing=original), original)
        enriched = snapshot()
        enriched["shadow_outcome"] = {"status": "SETTLED"}
        with self.assertRaises(ledger.OpportunityOutcomeConflictError):
            ledger.register_opportunity_snapshot(enriched, published_at=MATURE, existing=original)

    def test_market_costs_and_exchange_specific_entry_windows(self):
        for market, benchmark, cost in (("a_share", "510300", .0015), ("hk", "2800.HK", .003), ("us", "SPY", .0015)):
            source = snapshot()
            for row in source["return_opportunities"]["candidates"]:
                row["market"] = market
            p = pending(source)["predictions"][0]
            self.assertEqual(p["transaction_cost"], cost)
            self.assertEqual(p["benchmark_transaction_cost"], cost)
            self.assertEqual(p["benchmark_code"], benchmark)
            self.assertEqual(p["entry_trade_date"], "2026-08-21" if market == "us" else "2026-08-24")
            self.assertEqual(len(market_calendar.session_dates(market, p["entry_trade_date"], p["forecast_end_trade_date"])), 10)

    def test_complete_adjusted_window_benchmark_costs_and_freezing(self):
        a = ledger.settle_opportunity_batch(pending(), MATURE, loader)
        self.assertEqual(a["status_counts"], {"SETTLED": 2})
        r = a["outcomes"][0]
        self.assertAlmostEqual(r["net_total_return"], .095 - .0015)
        self.assertAlmostEqual(r["benchmark_net_return"], .0095 - .0015)
        self.assertAlmostEqual(r["net_excess_return"], .0855)
        self.assertLess(r["maximum_adverse_excursion"], 0)
        self.assertLess(r["maximum_drawdown"], 0)
        with mock.patch.object(ledger, "_settled", side_effect=AssertionError("settled outcome rewritten")):
            self.assertEqual(ledger.settle_opportunity_batch(a, "2026-09-11T00:00:00Z", loader), a)

    def test_missing_or_unadjusted_prices_are_pending_without_zero_returns(self):
        for missing in ("high", "benchmark_date", "unadjusted", "future"):
            def bad_loader(market, code):
                rows, source, adjusted = loader(market, code)
                if missing == "high":
                    rows[0].pop("high")
                if missing == "benchmark_date" and code == "SPY":
                    rows.pop(5)
                if missing == "unadjusted":
                    adjusted = False
                if missing == "future":
                    rows.append({**rows[-1], "date": "2027-01-01"})
                return rows, source, adjusted
            with self.subTest(missing=missing):
                a = ledger.settle_opportunity_batch(pending(), MATURE, bad_loader)
                self.assertEqual(a["status_counts"], {"PENDING_DATA": 2})
                self.assertNotIn("net_total_return", a["outcomes"][0])

    def test_rehash_does_not_hide_calendar_cost_or_arithmetic_tampering(self):
        a = ledger.settle_opportunity_batch(pending(), MATURE, loader)
        b = copy.deepcopy(a)
        b["outcomes"][0]["net_total_return"] = 9
        b["outcomes"][0]["outcome_sha256"] = ledger.outcome_sha256(b["outcomes"][0])
        b["batch_sha256"] = ledger.batch_sha256(b)
        with self.assertRaises(ledger.OpportunityOutcomeConflictError):
            ledger.validate_opportunity_outcome_batch(b)
        for field, value in (("entry_trade_date", "2026-08-20"), ("transaction_cost", 0)):
            rows = copy.deepcopy(a["predictions"])
            rows[0][field] = value
            rows[0]["prediction_id"] = ledger.prediction_id(rows[0])
            rows[0]["prediction_sha256"] = ledger.prediction_sha256(rows[0])
            with self.assertRaises(ledger.OpportunityOutcomeConflictError):
                ledger.validate_prediction_sequence(rows)

    def test_dedup_counts_versions_and_empty_collecting(self):
        empty = ledger.evaluate_opportunity_performance({})
        self.assertEqual(empty["status"], "COLLECTING")
        self.assertIsNone(empty["mean_net_return"])
        self.assertFalse(empty["authorizes_production"])
        a = ledger.settle_opportunity_batch(pending(), MATURE, loader)
        b = ledger.settle_opportunity_batch(pending(snapshot("2026-08-21_2026-08-20_230001.json")), MATURE, loader)
        summary = ledger.evaluate_opportunity_performance({"a": a, "b": b})
        self.assertEqual(summary["settled_count"], 4)
        self.assertEqual(summary["independent_entry_date_count"], 1)
        self.assertEqual(summary["unique_security_entry_count"], 2)
        self.assertEqual(summary["non_overlapping_entry_session_count"], 1)
        self.assertEqual(summary["duplicate_settled_observation_count"], 2)
        c = ledger.settle_opportunity_batch(pending(snapshot("2026-08-21_2026-08-20_230002.json", version="return-opportunity-score-v2")), MATURE, loader)
        mixed = ledger.evaluate_opportunity_performance({"a": a, "c": c})
        self.assertEqual(len(mixed["by_version"]), 2)
        self.assertIsNone(mixed["mean_net_return"])

    def test_writes_validate_hashes_and_never_downgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            a = pending()
            b = ledger.settle_opportunity_batch(a, MATURE, loader)
            target = ledger.write_opportunity_outcome_batch(directory, b)
            content = target.read_bytes()
            ledger.write_opportunity_outcome_batch(directory, b)
            self.assertEqual(target.read_bytes(), content)
            with self.assertRaises(ledger.OpportunityOutcomeConflictError):
                ledger.write_opportunity_outcome_batch(directory, a)
            damaged = json.loads(content)
            damaged["outcomes"][0]["status"] = "PENDING_DATA"
            target.write_text(json.dumps(damaged))
            with self.assertRaises(ledger.OpportunityOutcomeConflictError):
                ledger.load_opportunity_outcome_batches(directory)

    def test_incomplete_entry_cohort_cannot_report_winner_only_returns(self):
        def incomplete(market, code):
            return ([], "", False) if code == "BBB" else loader(market, code)
        a = ledger.settle_opportunity_batch(pending(), MATURE, incomplete)
        summary = ledger.evaluate_opportunity_performance({"a": a})
        self.assertEqual(summary["settled_count"], 1)
        self.assertEqual(summary["mature_pending_data_entry_session_count"], 1)
        self.assertEqual(summary["settled_entry_date_count"], 0)
        self.assertEqual(summary["metric_observation_count"], 0)
        self.assertIsNone(summary["mean_net_return"])
        self.assertIsNone(summary["win_rate"])
        # A successful later snapshot cannot quietly replace the earlier BBB.
        b = ledger.settle_opportunity_batch(pending(snapshot("2026-08-21_2026-08-20_230010.json"), publication="2026-08-21T13:29:01Z"), MATURE, loader)
        both = ledger.evaluate_opportunity_performance({"a": a, "b": b})
        self.assertIsNone(both["mean_net_return"])

    def test_overlapping_entry_dates_are_not_independent_ten_day_trades(self):
        def broad_loader(market, code):
            dates = market_calendar.session_dates(market, "2026-08-21", "2026-09-09")
            return ([{"date": day.isoformat(), "open": 10, "high": 12, "low": 9, "close": 11} for day in dates], "fixture", True)
        a = ledger.settle_opportunity_batch(pending(), MATURE, broad_loader)
        b = ledger.settle_opportunity_batch(pending(snapshot("2026-08-21_2026-08-20_230011.json"), publication="2026-08-21T13:31:00Z"), MATURE, broad_loader)
        summary = ledger.evaluate_opportunity_performance({"a": a, "b": b})
        self.assertEqual(summary["independent_entry_date_count"], 2)
        self.assertEqual(summary["settled_entry_session_count"], 2)
        self.assertEqual(summary["non_overlapping_entry_session_count"], 1)


if __name__ == "__main__":
    unittest.main()

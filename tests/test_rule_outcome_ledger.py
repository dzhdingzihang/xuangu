from __future__ import annotations

import copy
import datetime as dt
import pathlib
import tempfile
import unittest
from unittest import mock

import market_calendar
import rule_outcome_ledger as ledger
from scripts import settle_outcomes


def rule_snapshot() -> dict:
    generated_at = "2026-08-21T22:48:00+08:00"
    window = market_calendar.market_trade_window("a_share", generated_at, horizon_sessions=10)
    rows = []
    for index, code in enumerate(("600000", "000001")):
        rows.append(
            {
                "status": "QUALIFIED",
                "qualification_id": f"qual_{index:024x}",
                "market": "a_share",
                "code": code,
                "entry_price": 10.0 + index,
                "qualification_track": "quality_technical",
                "qualification_score": 80.0 - index,
                "rule_model_id": "ten-day-audited-rule-ensemble-v3",
                "calendar_id": window["calendar_id"],
                "calendar_version": window["calendar_version"],
                "entry_trade_date": window["entry_trade_date"],
                "forecast_end_trade_date": window["forecast_end_trade_date"],
            }
        )
    return {
        "snapshot_key": "2026-08-22_2026-08-21_224800.json",
        "generated_at": generated_at,
        "signal_date": "2026-08-21",
        "production_decision": {
            "contract_version": "production-rule-10d-v1",
            "action_basis": "dual_track_candidate_qualification_v3",
            "action": "QUALIFIED_PICK",
            "horizon_trade_days": 10,
            "rule_model_id": "ten-day-audited-rule-ensemble-v3",
            "score_kind": "RULE_QUALIFICATION_SCORE",
            "primary": copy.deepcopy(rows[0]),
            "qualified_candidates": rows,
            "qualified_candidate_count": len(rows),
        },
    }


def price_loader(market: str, code: str):
    snapshot = rule_snapshot()
    row = snapshot["production_decision"]["qualified_candidates"][0]
    dates = market_calendar.session_dates(
        market, row["entry_trade_date"], row["forecast_end_trade_date"]
    )
    base = 100.0 if code == "510300" else 10.0
    return (
        [
            {
                "date": day.isoformat(),
                "open": base + index * 0.1,
                "low": base + index * 0.1 - 0.2,
                "close": base + index * 0.1 + 0.05,
            }
            for index, day in enumerate(dates)
        ],
        "adjusted-test-source",
        True,
    )


class RuleOutcomeLedgerTests(unittest.TestCase):
    def test_yahoo_loader_applies_one_adjustment_factor_to_open_low_and_close(self) -> None:
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_700_000_000],
                        "meta": {"exchangeTimezoneName": "UTC"},
                        "indicators": {
                            "quote": [{"open": [100.0], "low": [90.0], "close": [110.0]}],
                            "adjclose": [{"adjclose": [55.0]}],
                        },
                    }
                ]
            }
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        import json

        with mock.patch.object(settle_outcomes.urllib.request, "urlopen", return_value=Response()):
            rows = settle_outcomes.yahoo_adjusted_rows("TEST", "us")

        self.assertEqual(rows[0]["open"], 50.0)
        self.assertEqual(rows[0]["low"], 45.0)
        self.assertEqual(rows[0]["close"], 55.0)

    def test_predictions_and_settlement_are_frozen_and_auditable(self) -> None:
        snapshot = rule_snapshot()
        predictions = ledger.build_rule_predictions(snapshot)
        self.assertEqual(len(predictions), 2)
        self.assertTrue(predictions[0]["is_primary"])
        self.assertRegex(predictions[0]["prediction_id"], r"^rulepred_[0-9a-f]{24}$")

        batch = ledger.settle_rule_snapshot(
            snapshot,
            "2026-09-10T00:00:00Z",
            price_loader,
            benchmark_price_loader=price_loader,
        )
        self.assertEqual(batch["status_counts"], {"SETTLED": 2})
        row = batch["outcomes"][0]
        self.assertEqual(row["status"], "SETTLED")
        self.assertEqual(row["benchmark_code"], "510300")
        self.assertAlmostEqual(
            row["net_excess_return"],
            row["net_total_return"] - row["benchmark_net_return"],
        )
        self.assertLess(row["maximum_adverse_excursion"], 0)
        self.assertEqual(row["transaction_cost_version"], ledger.COST_VERSION)

        replay = ledger.settle_rule_snapshot(
            snapshot,
            "2026-09-11T00:00:00Z",
            lambda *_: ([], "missing", False),
            benchmark_price_loader=lambda *_: ([], "missing", False),
            existing=batch,
        )
        self.assertEqual(replay, batch)

    def test_prediction_reorder_duplicate_and_calendar_tamper_fail_closed(self) -> None:
        snapshot = rule_snapshot()
        predictions = ledger.build_rule_predictions(snapshot)
        with self.assertRaises(ledger.RuleOutcomeConflictError):
            ledger.validate_prediction_sequence([predictions[1], predictions[0]])
        with self.assertRaises(ledger.RuleOutcomeConflictError):
            ledger.validate_prediction_sequence([predictions[0], predictions[0]])

        tampered = rule_snapshot()
        tampered["production_decision"]["qualified_candidates"][0]["calendar_version"] = "wrong"
        with self.assertRaises(ledger.RuleOutcomeContractError):
            ledger.build_rule_predictions(tampered)

    def test_partial_settlement_and_future_price_evidence_fail_closed(self) -> None:
        batch = ledger.settle_rule_snapshot(
            rule_snapshot(),
            "2026-09-10T00:00:00Z",
            price_loader,
            benchmark_price_loader=price_loader,
        )
        partial = copy.deepcopy(batch)
        del partial["outcomes"][0]["exit_close"]
        partial["outcomes"][0]["outcome_sha256"] = ledger.outcome_sha256(
            partial["outcomes"][0]
        )
        partial["batch_sha256"] = ledger.batch_sha256(partial)
        with self.assertRaises(ledger.RuleOutcomeConflictError):
            ledger.validate_rule_outcome_batch(partial)

        def future_loader(market: str, code: str):
            rows, source, adjusted = price_loader(market, code)
            rows.append({"date": "2027-01-01", "open": 1, "low": 1, "close": 1})
            return rows, source, adjusted

        pending = ledger.settle_rule_snapshot(
            rule_snapshot(),
            "2026-09-10T00:00:00Z",
            future_loader,
            benchmark_price_loader=price_loader,
        )
        self.assertEqual(pending["status_counts"], {"PENDING_DATA": 2})

        def missing_low_loader(market: str, code: str):
            rows, source, adjusted = price_loader(market, code)
            for row in rows:
                row.pop("low", None)
            return rows, source, adjusted

        missing_low = ledger.settle_rule_snapshot(
            rule_snapshot(),
            "2026-09-10T00:00:00Z",
            missing_low_loader,
            benchmark_price_loader=price_loader,
        )
        self.assertEqual(missing_low["status_counts"], {"PENDING_DATA": 2})
        self.assertTrue(
            all("maximum_adverse_excursion" not in row for row in missing_low["outcomes"])
        )

    def test_entry_reference_cannot_change_and_settled_rows_cannot_downgrade(self) -> None:
        snapshot = rule_snapshot()
        batch = ledger.settle_rule_snapshot(
            snapshot,
            "2026-09-10T00:00:00Z",
            price_loader,
            benchmark_price_loader=price_loader,
        )
        changed = rule_snapshot()
        changed["production_decision"]["qualified_candidates"][0]["entry_price"] += 1.0
        changed["production_decision"]["primary"]["entry_price"] += 1.0
        with self.assertRaises(ledger.RuleOutcomeConflictError):
            ledger.settle_rule_snapshot(
                changed,
                "2026-09-11T00:00:00Z",
                price_loader,
                existing=batch,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            ledger.write_rule_outcome_batch(root, batch)
            downgraded = ledger.settle_rule_snapshot(
                snapshot,
                "2026-08-25T00:00:00Z",
                price_loader,
            )
            with self.assertRaises(ledger.RuleOutcomeConflictError):
                ledger.write_rule_outcome_batch(root, downgraded)


if __name__ == "__main__":
    unittest.main()

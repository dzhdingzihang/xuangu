from __future__ import annotations

import datetime as dt
import json
import pathlib
import tempfile
import unittest

from scripts import settle_outcomes


def fixture_snapshot() -> dict:
    return {
        "generated_at": "2026-08-21T22:00:00+08:00",
        "signal_date": "2026-08-21",
        "global_decision": {
            "research_priority": {
                "status": "RESEARCH_ONLY",
                "prediction_id": "pred_0123456789abcdef01234567",
                "model_id": "ten-day-rule-shadow-v1",
                "label_version": "shadow-net-return-10-session-v1",
                "market": "us",
                "code": "NVDA",
                "name": "NVIDIA",
                "priority_score_kind": "RULE_PRIORITY",
                "priority_score": 81.2,
                "entry_trade_date": "2026-08-24",
                "forecast_end_trade_date": "2026-09-04",
                "calendar_id": "XNYS",
                "calendar_version": "exchange-calendars-4.13.2",
            }
        },
    }


class OutcomeLedgerTests(unittest.TestCase):
    def test_scheduled_shadow_ledger_samples_only_the_daily_last_primary_checkpoint(self) -> None:
        morning = fixture_snapshot() | {
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T10:17:00+08:00",
            }
        }
        closing = fixture_snapshot() | {
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T22:47:00+08:00",
            }
        }
        manual = fixture_snapshot() | {
            "automation": {
                "trigger": "workflow_dispatch",
                "scheduled_slot": None,
            }
        }

        self.assertIsNone(settle_outcomes.candidate_contract(morning, "morning.json"))
        self.assertIsNone(settle_outcomes.candidate_contract(manual, "manual.json"))
        contract = settle_outcomes.candidate_contract(closing, "closing.json")
        self.assertIsNotNone(contract)
        self.assertEqual(contract["sampling_policy"], "daily_last_primary_checkpoint_v1")
        self.assertEqual(contract["scheduled_slot"], "2026-08-21T22:47:00+08:00")

    def test_research_contract_stays_separate_and_pending(self) -> None:
        contract = settle_outcomes.candidate_contract(fixture_snapshot(), "sample.json")
        self.assertIsNotNone(contract)
        self.assertEqual(contract["track"], "SHADOW_RESEARCH")
        result = settle_outcomes.settle_contract(contract, dt.date(2026, 9, 4), lambda *_: ([], "test", False))
        self.assertEqual(result["status"], "PENDING")

    def test_complete_bars_settle_net_return_idempotently(self) -> None:
        contract = settle_outcomes.candidate_contract(fixture_snapshot(), "sample.json")
        rows = [
            {"date": "2026-08-24", "open": 100, "close": 101},
            {"date": "2026-09-04", "open": 109, "close": 110},
        ]
        settled = settle_outcomes.settle_contract(
            contract,
            dt.date(2026, 9, 5),
            lambda *_: (rows, "fixture_adjusted_daily", True),
        )
        self.assertEqual(settled["status"], "SETTLED")
        self.assertAlmostEqual(settled["gross_total_return"], 0.1)
        self.assertAlmostEqual(settled["net_total_return"], 0.0985)
        self.assertTrue(settled["positive_label"])
        self.assertEqual(
            settle_outcomes.settle_contract(settled, dt.date(2026, 9, 6), lambda *_: ([], "", False)),
            settled,
        )

    def test_run_creates_one_file_per_prediction_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            picks.mkdir()
            payload = fixture_snapshot()
            (picks / "one.json").write_text(json.dumps(payload), encoding="utf-8")
            (picks / "latest.json").write_text(json.dumps(payload), encoding="utf-8")
            first = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))
            second = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))
            self.assertEqual(first["discovered"], 1)
            self.assertEqual(len(list(outcomes.glob("*.json"))), 1)
            self.assertEqual(second["unchanged"], 1)


if __name__ == "__main__":
    unittest.main()

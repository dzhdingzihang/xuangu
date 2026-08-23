from __future__ import annotations

import datetime as dt
import copy
import json
import pathlib
import tempfile
import unittest

import history_evaluation
import market_calendar
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


def executable_fixture_snapshot(*, same_prediction_id_as_shadow: bool = False) -> dict:
    snapshot = fixture_snapshot()
    snapshot["global_decision"].update(
        {
            "contract_version": "global-10d-v1",
            "decision_scope": "global_10d",
            "action_basis": "strict_cross_market_gate_v1",
            "horizon_trade_days": 10,
            "action": "REVIEW_EXECUTABLE_PICK",
            "probability_status": "CALIBRATED",
            "probability": 0.67,
            "calibrated": True,
            "blocker_codes": [],
            "primary": {
                "status": "EXECUTABLE",
                "prediction_id": (
                    "pred_0123456789abcdef01234567"
                    if same_prediction_id_as_shadow
                    else "pred_fedcba9876543210fedcba98"
                ),
                "model_id": "ten-day-return-production-v1",
                "label_version": "net-return-10-session-v1",
                "market": "us",
                "code": "NVDA",
                "name": "NVIDIA",
                "score_kind": "TEN_DAY_EXPECTED_NET_UTILITY",
                "probability": 0.67,
                "expected_net_utility": 0.08,
                "transaction_cost": 0.0015,
                "tail_risk": 0.12,
                "calibrated": True,
                "entry_trade_date": "2026-08-24",
                "forecast_end_trade_date": "2026-09-04",
                "calendar_id": "XNYS",
                "calendar_version": "exchange-calendars-4.13.2",
            },
        }
    )
    return snapshot


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

        missing_calendar_version = fixture_snapshot()
        missing_calendar_version["global_decision"]["research_priority"].pop("calendar_version")
        self.assertIsNone(
            settle_outcomes.candidate_contract(missing_calendar_version, "missing-calendar.json")
        )

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
        self.assertEqual(settled["entry_at"], contract["entry_session_open_at"])
        self.assertEqual(settled["exit_at"], contract["forecast_end_session_close_at"])
        self.assertEqual(
            settle_outcomes.settle_contract(settled, dt.date(2026, 9, 6), lambda *_: ([], "", False)),
            settled,
        )

    def test_formal_settlement_round_trips_through_strict_evaluator(self) -> None:
        generated_at = "2025-08-21T08:17:00+08:00"
        window = market_calendar.market_trade_window("hk", generated_at, horizon_sessions=10)
        snapshot = executable_fixture_snapshot()
        snapshot["generated_at"] = generated_at
        snapshot["signal_date"] = "2025-08-21"
        snapshot["global_decision"]["primary"].update(
            {
                "market": "hk",
                "code": "00700.HK",
                "transaction_cost": 0.003,
                "entry_trade_date": window["entry_trade_date"],
                "forecast_end_trade_date": window["forecast_end_trade_date"],
                "calendar_id": window["calendar_id"],
                "calendar_version": window["calendar_version"],
            }
        )
        contract = settle_outcomes.executable_candidate_contract(snapshot, "formal.json")
        self.assertIsNotNone(contract)
        self.assertEqual(contract["entry_session_open_at"], window["entry_session_open_at"])
        self.assertEqual(
            contract["forecast_end_session_close_at"],
            window["forecast_end_session_close_at"],
        )

        raw_entry_price = 0.01234567891
        raw_exit_price = 0.01358024765
        rows = [
            {"date": window["entry_trade_date"], "open": raw_entry_price, "close": raw_entry_price},
            {"date": window["forecast_end_trade_date"], "open": raw_exit_price, "close": raw_exit_price},
        ]
        settled = settle_outcomes.settle_contract(
            contract,
            dt.date.fromisoformat(window["forecast_end_trade_date"]) + dt.timedelta(days=1),
            lambda *_: (rows, "fixture_adjusted_daily", True),
        )

        self.assertEqual(settled["entry_at"], window["entry_session_open_at"])
        self.assertEqual(settled["exit_at"], window["forecast_end_session_close_at"])
        self.assertEqual(settled["entry_price"], round(raw_entry_price, 8))
        self.assertEqual(settled["exit_price"], round(raw_exit_price, 8))
        self.assertAlmostEqual(
            settled["gross_total_return"],
            round(settled["exit_price"] / settled["entry_price"] - 1, 8),
        )
        self.assertAlmostEqual(
            settled["net_total_return"],
            round(settled["gross_total_return"] - settled["transaction_cost"], 8),
        )

        row = {
            "history_kind": "global_10d_v1",
            "target_date": window["entry_trade_date"],
            "generated_at": generated_at,
            "snapshot_key": "formal.json",
            "global_decision": snapshot["global_decision"],
            "outcome": settled,
        }
        valid, reason = history_evaluation.valid_formal_settlement(row)
        self.assertTrue(valid, reason)
        performance = history_evaluation.evaluate_formal_performance([row])
        self.assertEqual(performance["sample_count"], 1)
        self.assertEqual(performance["settled_sample_count"], 1)

    def test_positive_label_uses_the_published_net_return(self) -> None:
        contract = settle_outcomes.candidate_contract(fixture_snapshot(), "sample.json")
        rows = [
            {"date": "2026-08-24", "open": 100.0, "close": 100.0},
            {"date": "2026-09-04", "open": 100.1500004, "close": 100.1500004},
        ]
        settled = settle_outcomes.settle_contract(
            contract,
            dt.date(2026, 9, 5),
            lambda *_: (rows, "fixture_adjusted_daily", True),
        )

        self.assertEqual(settled["gross_total_return"], 0.0015)
        self.assertEqual(settled["net_total_return"], 0.0)
        self.assertFalse(settled["positive_label"])

    def test_formal_contract_requires_complete_calibrated_global_primary(self) -> None:
        contract = settle_outcomes.executable_candidate_contract(
            executable_fixture_snapshot(),
            "formal.json",
        )
        self.assertIsNotNone(contract)
        self.assertEqual(contract["schema_version"], "executable-outcome-v1")
        self.assertEqual(contract["track"], "EXECUTABLE_MODEL")
        self.assertEqual(contract["sampling_policy"], "all_published_executable_predictions_v1")
        self.assertAlmostEqual(contract["transaction_cost"], 0.0015)

        invalid_mutations = (
            lambda row: row["global_decision"].update(action="NO_VALID_PICK"),
            lambda row: row["global_decision"].update(calibrated=False),
            lambda row: row["global_decision"].update(horizon_trade_days=9),
            lambda row: row["global_decision"].update(action_basis="legacy_gate"),
            lambda row: row["global_decision"].update(probability=0.66),
            lambda row: row["global_decision"].update(blocker_codes=["MODEL_BLOCKED"]),
            lambda row: row["global_decision"]["primary"].update(status="RESEARCH_ONLY"),
            lambda row: row["global_decision"]["primary"].update(calibrated=False),
            lambda row: row["global_decision"]["primary"].update(probability=1.01),
            lambda row: row["global_decision"]["primary"].update(expected_net_utility=0),
            lambda row: row["global_decision"]["primary"].update(transaction_cost=-0.01),
            lambda row: row["global_decision"]["primary"].update(calendar_id="XHKG"),
            lambda row: row["global_decision"]["primary"].update(calendar_version="unknown"),
            lambda row: row["global_decision"]["primary"].update(entry_trade_date="2026-08-25"),
            lambda row: row["global_decision"]["primary"].update(forecast_end_trade_date="2026-09-03"),
            lambda row: row.update(generated_at="2026-08-21T22:00:00"),
        )
        for mutate in invalid_mutations:
            with self.subTest(mutate=mutate):
                snapshot = copy.deepcopy(executable_fixture_snapshot())
                mutate(snapshot)
                self.assertIsNone(settle_outcomes.executable_candidate_contract(snapshot, "invalid.json"))

    def test_formal_and_shadow_tracks_can_share_prediction_id_without_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            picks.mkdir()
            payload = executable_fixture_snapshot(same_prediction_id_as_shadow=True)
            (picks / "one.json").write_text(json.dumps(payload), encoding="utf-8")
            (picks / "latest.json").write_text(json.dumps(payload), encoding="utf-8")

            first = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))
            second = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))

            prediction_id = "pred_0123456789abcdef01234567"
            shadow = json.loads((outcomes / f"{prediction_id}.json").read_text(encoding="utf-8"))
            formal = json.loads((outcomes / "executable" / f"{prediction_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(shadow["track"], "SHADOW_RESEARCH")
            self.assertEqual(formal["track"], "EXECUTABLE_MODEL")
            self.assertEqual(first["discovered"], 2)
            self.assertEqual(first["shadow_created"], 1)
            self.assertEqual(first["executable_created"], 1)
            self.assertEqual(second["unchanged"], 2)

    def test_formal_outcome_identity_conflict_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            executable_outcomes = outcomes / "executable"
            picks.mkdir()
            executable_outcomes.mkdir(parents=True)
            payload = executable_fixture_snapshot()
            payload["global_decision"].pop("research_priority", None)
            (picks / "one.json").write_text(json.dumps(payload), encoding="utf-8")
            contract = settle_outcomes.executable_candidate_contract(payload, "one.json")
            conflicting = dict(contract, code="AMD")
            target = executable_outcomes / f"{contract['prediction_id']}.json"
            target.write_text(json.dumps(conflicting), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "outcome identity conflict"):
                settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))

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

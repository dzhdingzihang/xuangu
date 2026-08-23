from __future__ import annotations

import datetime as dt
import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

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


def technical_shadow_snapshot() -> dict:
    snapshot = fixture_snapshot()
    snapshot["generated_at"] = "2026-08-21T22:48:00+08:00"
    snapshot["automation"] = {
        "trigger": "schedule",
        "scheduled_slot": "2026-08-21T22:47:00+08:00",
    }
    snapshot["global_decision"].update(
        {
            "contract_version": "global-10d-v1",
            "decision_scope": "global_10d",
            "action_basis": "strict_cross_market_gate_v1",
            "action": "NO_VALID_PICK",
            "probability": None,
            "market_states": {
                "a_share": {"state": "READY"},
                "hk": {"state": "READY"},
                "us": {"state": "READY"},
            },
        }
    )
    snapshot["global_decision"]["research_priority"]["probability"] = None
    snapshot["global_decision"]["research_priority"]["shadow_model"] = {
        "status": "SHADOW_ONLY",
        "rank_eligible": True,
        "prediction_id": "pred_abcdef0123456789abcdef01",
        "model_id": "ten-day-technical-shadow-v1",
        "label_version": "r10-net-total-return-v1",
        "probability": 0.62,
        "expected_net_utility": 0.031,
        "tail_risk": 0.084,
        "transaction_cost": 0.0018,
        "artifact_sha256": "a" * 64,
        "training_cutoff": "2026-08-08",
        "calibrated": False,
        "participates_in_decision": False,
        "production_eligible": False,
    }
    return snapshot


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
    def test_a_share_settlement_loader_uses_only_explicit_qfq_chain(self) -> None:
        adjusted_rows = [
            {"date": "2026-08-24", "open": 10.0, "close": 10.1},
            {"date": "2026-09-04", "open": 10.9, "close": 11.0},
        ]
        with (
            mock.patch.object(
                settle_outcomes.server,
                "qfq_stock_kline",
                return_value=adjusted_rows,
            ) as qfq,
            mock.patch.object(settle_outcomes.server, "baidu_stock_kline") as baidu,
            mock.patch.object(settle_outcomes.server, "eastmoney_stock_kline") as eastmoney,
            mock.patch.object(settle_outcomes.server, "tencent_stock_kline") as tencent,
        ):
            rows, source, adjusted = settle_outcomes.market_rows("a_share", "600000")

        self.assertEqual(rows, adjusted_rows)
        self.assertEqual(source, "a_share_qfq_daily")
        self.assertTrue(adjusted)
        qfq.assert_called_once_with("600000", 180)
        baidu.assert_not_called()
        eastmoney.assert_not_called()
        tencent.assert_not_called()

    def test_a_share_settlement_loader_fails_closed_without_explicit_qfq_rows(self) -> None:
        with (
            mock.patch.object(
                settle_outcomes.server,
                "qfq_stock_kline",
                return_value=[],
            ) as qfq,
            mock.patch.object(settle_outcomes.server, "stock_kline") as legacy,
        ):
            rows, source, adjusted = settle_outcomes.market_rows("a_share", "600000")

        self.assertEqual(rows, [])
        self.assertEqual(source, "a_share_qfq_daily")
        self.assertFalse(adjusted)
        qfq.assert_called_once_with("600000", 180)
        legacy.assert_not_called()

    def test_technical_shadow_identity_and_probability_are_frozen_in_ledger(self) -> None:
        snapshot = technical_shadow_snapshot()

        contract = settle_outcomes.candidate_contract(snapshot, "technical.json")

        self.assertIsNotNone(contract)
        self.assertEqual(contract["prediction_id"], "pred_abcdef0123456789abcdef01")
        self.assertEqual(contract["model_id"], "ten-day-technical-shadow-v1")
        self.assertNotEqual(contract["model_id"], "ten-day-rule-shadow-v1")
        self.assertEqual(contract["label_version"], "r10-net-total-return-v1")
        self.assertEqual(contract["probability"], 0.62)
        self.assertEqual(contract["expected_net_utility"], 0.031)
        self.assertEqual(contract["tail_risk"], 0.084)
        self.assertEqual(contract["transaction_cost"], 0.0018)
        self.assertEqual(contract["artifact_sha256"], "a" * 64)
        self.assertEqual(contract["training_cutoff"], "2026-08-08")
        self.assertIsNone(snapshot["global_decision"]["probability"])
        self.assertIsNone(snapshot["global_decision"]["research_priority"]["probability"])

        evaluated = history_evaluation.prediction_contract(
            snapshot,
            history_evaluation.SHADOW_TRACK,
        )
        self.assertEqual(evaluated["prediction_id"], contract["prediction_id"])
        self.assertEqual(evaluated["model_id"], contract["model_id"])
        self.assertEqual(evaluated["probability"], 0.62)
        self.assertEqual(evaluated["artifact_sha256"], "a" * 64)

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            picks.mkdir()
            (picks / "technical.json").write_text(json.dumps(snapshot), encoding="utf-8")
            settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))
            ledger = json.loads(
                (outcomes / "pred_abcdef0123456789abcdef01.json").read_text(encoding="utf-8")
            )
            self.assertEqual(ledger["model_id"], "ten-day-technical-shadow-v1")
            self.assertEqual(ledger["probability"], 0.62)
            self.assertFalse((outcomes / "pred_0123456789abcdef01234567.json").exists())

    def test_malformed_nested_shadow_fails_closed_instead_of_using_rule_identity(self) -> None:
        snapshot = technical_shadow_snapshot()
        snapshot["global_decision"]["research_priority"]["shadow_model"].pop("artifact_sha256")

        self.assertIsNone(settle_outcomes.candidate_contract(snapshot, "technical.json"))
        self.assertIsNone(
            history_evaluation.prediction_contract(snapshot, history_evaluation.SHADOW_TRACK)
        )

    def test_ineligible_nested_shadow_cannot_register_rule_fallback(self) -> None:
        snapshot = technical_shadow_snapshot()
        snapshot["global_decision"]["research_priority"]["shadow_model"]["rank_eligible"] = False

        contract = settle_outcomes.candidate_contract(snapshot, "ineligible-shadow.json")

        self.assertIsNone(contract)
        self.assertIsNone(
            history_evaluation.prediction_contract(snapshot, history_evaluation.SHADOW_TRACK)
        )

    def test_scheduled_shadow_ledger_samples_only_the_daily_last_primary_checkpoint(self) -> None:
        morning = technical_shadow_snapshot()
        morning["automation"]["scheduled_slot"] = "2026-08-21T10:17:00+08:00"
        closing = technical_shadow_snapshot()
        manual = technical_shadow_snapshot()
        manual["automation"] = {"trigger": "workflow_dispatch", "scheduled_slot": None}

        self.assertIsNone(settle_outcomes.candidate_contract(morning, "morning.json"))
        self.assertIsNone(settle_outcomes.candidate_contract(manual, "manual.json"))
        contract = settle_outcomes.candidate_contract(closing, "closing.json")
        self.assertIsNotNone(contract)
        self.assertEqual(contract["sampling_policy"], "daily_last_primary_checkpoint_v1")
        self.assertEqual(contract["scheduled_slot"], "2026-08-21T22:47:00+08:00")

    def test_technical_shadow_requires_selected_and_all_published_markets_ready(self) -> None:
        selected_degraded = technical_shadow_snapshot()
        selected_degraded["global_decision"]["market_states"]["us"]["state"] = "DEGRADED"
        other_degraded = technical_shadow_snapshot()
        other_degraded["global_decision"]["market_states"]["hk"]["state"] = "DEGRADED"
        selected_missing = technical_shadow_snapshot()
        selected_missing["global_decision"]["market_states"].pop("us")
        non_selected_missing = technical_shadow_snapshot()
        non_selected_missing["global_decision"]["market_states"].pop("hk")
        unexpected_market = technical_shadow_snapshot()
        unexpected_market["global_decision"]["market_states"]["crypto"] = {
            "state": "READY"
        }

        for snapshot in (
            selected_degraded,
            other_degraded,
            selected_missing,
            non_selected_missing,
            unexpected_market,
        ):
            with self.subTest(states=snapshot["global_decision"]["market_states"]):
                self.assertIsNone(settle_outcomes.candidate_contract(snapshot, "blocked.json"))
                self.assertIsNone(
                    history_evaluation.prediction_contract(
                        snapshot,
                        history_evaluation.SHADOW_TRACK,
                    )
                )

    def test_same_slot_recovery_supersedes_pending_shadow_without_duplicate(self) -> None:
        primary = technical_shadow_snapshot()
        recovery = copy.deepcopy(primary)
        recovery["generated_at"] = "2026-08-21T23:18:00+08:00"
        recovery_shadow = recovery["global_decision"]["research_priority"]["shadow_model"]
        recovery_shadow.update(
            {
                "probability": 0.66,
                "expected_net_utility": 0.039,
                "tail_risk": 0.079,
                "artifact_sha256": "b" * 64,
                "training_cutoff": "2026-08-15",
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            picks.mkdir()
            (picks / "primary.json").write_text(json.dumps(primary), encoding="utf-8")

            first = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 21))
            prediction_id = "pred_abcdef0123456789abcdef01"
            first_ledger = json.loads(
                (outcomes / f"{prediction_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first["shadow_created"], 1)
            self.assertEqual(first_ledger["source_snapshot"], "primary.json")
            self.assertEqual(first_ledger["probability"], 0.62)

            (picks / "recovery.json").write_text(json.dumps(recovery), encoding="utf-8")
            # latest.json is an alias of the immutable recovery snapshot and
            # must not become the frozen source identity.
            (picks / "latest.json").write_text(json.dumps(recovery), encoding="utf-8")
            discovered = settle_outcomes.discover_contracts(picks)
            self.assertEqual(len(discovered), 1)
            self.assertEqual(discovered[prediction_id]["source_snapshot"], "recovery.json")

            second = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 21))
            ledger = json.loads(
                (outcomes / f"{prediction_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(second["shadow_discovered"], 1)
            self.assertEqual(second["shadow_created"], 0)
            self.assertEqual(ledger["status"], "PENDING")
            self.assertEqual(ledger["source_snapshot"], "recovery.json")
            self.assertEqual(ledger["generated_at"], recovery["generated_at"])
            self.assertEqual(ledger["probability"], 0.66)
            self.assertEqual(ledger["artifact_sha256"], "b" * 64)
            self.assertEqual(len(list(outcomes.glob("pred_*.json"))), 1)
            inventory = history_evaluation.load_ledger_inventory(
                outcomes,
                history_evaluation.SHADOW_TRACK,
            )
            stats = history_evaluation.ledger_statistics(
                {"primary.json": primary, "recovery.json": recovery},
                inventory,
                history_evaluation.SHADOW_TRACK,
            )
            self.assertEqual(stats["prediction_count"], 1)
            self.assertEqual(stats["eligible_count"], 1)
            self.assertEqual(stats["pending_count"], 1)
            self.assertEqual(stats["conflict_count"], 0)

    def test_same_slot_recovery_never_rewrites_settled_shadow(self) -> None:
        primary = technical_shadow_snapshot()
        recovery = copy.deepcopy(primary)
        recovery["generated_at"] = "2026-08-21T23:18:00+08:00"
        recovery["global_decision"]["research_priority"]["shadow_model"].update(
            {"probability": 0.66, "artifact_sha256": "b" * 64}
        )

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            picks.mkdir()
            outcomes.mkdir()
            (picks / "primary.json").write_text(json.dumps(primary), encoding="utf-8")
            old_contract = settle_outcomes.candidate_contract(primary, "primary.json")
            old_contract["status"] = "SETTLED"
            target = outcomes / f"{old_contract['prediction_id']}.json"
            target.write_text(json.dumps(old_contract), encoding="utf-8")
            (picks / "recovery.json").write_text(json.dumps(recovery), encoding="utf-8")

            settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 21))

            preserved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(preserved["status"], "SETTLED")
            self.assertEqual(preserved["source_snapshot"], "primary.json")
            self.assertEqual(preserved["probability"], 0.62)

    def test_same_prediction_id_different_shadow_security_fails_closed(self) -> None:
        primary = technical_shadow_snapshot()
        malformed = copy.deepcopy(primary)
        malformed["generated_at"] = "2026-08-21T23:18:00+08:00"
        malformed["global_decision"]["research_priority"]["code"] = "AMD"

        with tempfile.TemporaryDirectory() as directory:
            picks = pathlib.Path(directory)
            (picks / "primary.json").write_text(json.dumps(primary), encoding="utf-8")
            (picks / "malformed.json").write_text(json.dumps(malformed), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "outcome identity conflict"):
                settle_outcomes.discover_contracts(picks)

    def test_research_contract_stays_separate_and_pending(self) -> None:
        contract = settle_outcomes.candidate_contract(technical_shadow_snapshot(), "sample.json")
        self.assertIsNotNone(contract)
        self.assertEqual(contract["track"], "SHADOW_RESEARCH")
        result = settle_outcomes.settle_contract(contract, dt.date(2026, 9, 4), lambda *_: ([], "test", False))
        self.assertEqual(result["status"], "PENDING")

        missing_calendar_version = technical_shadow_snapshot()
        missing_calendar_version["global_decision"]["research_priority"].pop("calendar_version")
        self.assertIsNone(
            settle_outcomes.candidate_contract(missing_calendar_version, "missing-calendar.json")
        )

    def test_complete_bars_settle_net_return_idempotently(self) -> None:
        contract = settle_outcomes.candidate_contract(technical_shadow_snapshot(), "sample.json")
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
        self.assertAlmostEqual(settled["net_total_return"], 0.0982)
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
        contract = settle_outcomes.candidate_contract(technical_shadow_snapshot(), "sample.json")
        rows = [
            {"date": "2026-08-24", "open": 100.0, "close": 100.0},
            {"date": "2026-09-04", "open": 100.1800004, "close": 100.1800004},
        ]
        settled = settle_outcomes.settle_contract(
            contract,
            dt.date(2026, 9, 5),
            lambda *_: (rows, "fixture_adjusted_daily", True),
        )

        self.assertEqual(settled["gross_total_return"], 0.0018)
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
            payload["generated_at"] = "2026-08-21T22:48:00+08:00"
            payload["automation"] = {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-21T22:47:00+08:00",
            }
            payload["global_decision"]["market_states"] = {
                "a_share": {"state": "READY"},
                "hk": {"state": "READY"},
                "us": {"state": "READY"},
            }
            payload["global_decision"]["research_priority"]["shadow_model"] = {
                **technical_shadow_snapshot()["global_decision"]["research_priority"]["shadow_model"],
                "prediction_id": "pred_0123456789abcdef01234567",
            }
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
            payload = technical_shadow_snapshot()
            (picks / "one.json").write_text(json.dumps(payload), encoding="utf-8")
            (picks / "latest.json").write_text(json.dumps(payload), encoding="utf-8")
            first = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))
            second = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))
            self.assertEqual(first["discovered"], 1)
            self.assertEqual(len(list(outcomes.glob("*.json"))), 1)
            self.assertEqual(second["unchanged"], 1)


if __name__ == "__main__":
    unittest.main()

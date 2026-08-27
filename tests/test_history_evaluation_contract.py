from __future__ import annotations

import json
import math
import pathlib
import tempfile
import unittest
from copy import deepcopy
from unittest import mock

import history_evaluation
import model_observation_ledger
import observation_outcome_ledger
import server
from tests.test_model_observation_ledger import snapshot as observation_snapshot


def write_snapshot(directory: pathlib.Path, name: str, payload: dict) -> None:
    (directory / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def formal_row(
    prediction_id: str,
    *,
    probability: float = 0.7,
    utility: float = 0.05,
    net_return: float = 0.08,
    day: int = 1,
) -> dict:
    cost = 0.002
    gross = net_return + cost
    forecast_day = 14 + day
    source_snapshot = f"{prediction_id}.json"
    return {
        "target_date": f"2026-08-{day + 1:02d}",
        "generated_at": f"2026-08-{day:02d}T08:00:00+08:00",
        "forecast_end_date": "2099-12-31",  # Deliberately not the primary market date.
        "snapshot_key": source_snapshot,
        "history_kind": "global_10d_v1",
        "global_decision": {
            "contract_version": "global-10d-v1",
            "decision_scope": "global_10d",
            "action_basis": "strict_cross_market_gate_v1",
            "horizon_trade_days": 10,
            "action": "REVIEW_EXECUTABLE_PICK",
            "probability_status": "CALIBRATED",
            "probability": probability,
            "calibrated": True,
            "blocker_codes": [],
            "primary": {
                "status": "EXECUTABLE",
                "prediction_id": prediction_id,
                "model_id": "model-1",
                "label_version": "labels-v1",
                "market": "a_share",
                "code": f"6000{day:02d}",
                "score_kind": "TEN_DAY_EXPECTED_NET_UTILITY",
                "calibrated": True,
                "probability": probability,
                "expected_net_utility": utility,
                "tail_risk": 0.12,
                "transaction_cost": cost,
                "entry_trade_date": f"2026-08-{day + 1:02d}",
                "forecast_end_trade_date": f"2026-08-{forecast_day:02d}",
                "calendar_id": "XSHG-v1",
                "calendar_version": "exchange-calendars-test-v1",
            },
        },
        "outcome": {
            "schema_version": "executable-outcome-v1",
            "track": "EXECUTABLE_MODEL",
            "status": "SETTLED",
            "prediction_id": prediction_id,
            "model_id": "model-1",
            "label_version": "labels-v1",
            "market": "a_share",
            "code": f"6000{day:02d}",
            "probability": probability,
            "expected_net_utility": utility,
            "tail_risk": 0.12,
            "source_snapshot": source_snapshot,
            "entry_trade_date": f"2026-08-{day + 1:02d}",
            "forecast_end_trade_date": f"2026-08-{forecast_day:02d}",
            "horizon_trade_sessions": 10,
            "entry_policy": "next_session_open_v1",
            "exit_policy": "tenth_session_close_v1",
            "sampling_policy": "all_published_executable_predictions_v1",
            "entry_at": f"2026-08-{day + 1:02d}T09:30:00+08:00",
            "entry_price": 100.0,
            "entry_source": "exchange_open_v1",
            "exit_at": f"2026-08-{forecast_day:02d}T15:00:00+08:00",
            "exit_price": 100.0 * (1.0 + gross),
            "exit_source": "exchange_close_v1",
            "gross_total_return": gross,
            "net_total_return": net_return,
            "transaction_cost": cost,
            "corporate_action_adjusted": True,
            "calendar_id": "XSHG-v1",
            "calendar_version": "exchange-calendars-test-v1",
            "currency": "CNY",
            "fx_rate_source": "same_currency",
            "positive_label": net_return > 0,
            "settled_at": f"2026-08-{forecast_day:02d}T16:00:00+08:00",
        },
    }


def set_formal_version(row: dict, model_id: str, label_version: str) -> dict:
    primary = row["global_decision"]["primary"]
    outcome = row["outcome"]
    primary["model_id"] = model_id
    primary["label_version"] = label_version
    outcome["model_id"] = model_id
    outcome["label_version"] = label_version
    return row


class HistoryEvaluationContractTests(unittest.TestCase):
    def test_observation_diagnostics_are_isolated_from_executable_performance(self) -> None:
        cohorts = model_observation_ledger.build_observation_cohorts(
            {observation_snapshot()["snapshot_key"]: observation_snapshot()}
        )
        cohort = next(iter(cohorts.values()))
        batches = {
            cohort["cohort_id"]: observation_outcome_ledger.settle_observation_cohort(
                cohort,
                "2026-08-25T00:00:00Z",
                lambda *_: ([], "unused", True),
            )
        }

        diagnostics = history_evaluation.evaluate_observation_performance(cohorts, batches)
        formal = history_evaluation.evaluate_formal_performance([])

        self.assertEqual(diagnostics["track"], "MODEL_OBSERVATION")
        self.assertEqual(diagnostics["prediction_count"], 3)
        self.assertEqual(diagnostics["pending_maturity_count"], 3)
        self.assertEqual(diagnostics["settled_count"], 0)
        self.assertEqual(diagnostics["independent_cohort_day_count"], 0)
        self.assertFalse(diagnostics["included_in_executable_performance"])
        self.assertFalse(diagnostics["authorizes_production"])
        self.assertEqual(formal["executable_prediction_count"], 0)
        self.assertEqual(formal["settled_sample_count"], 0)

    def test_observation_diagnostics_report_equal_weight_market_day_metrics(self) -> None:
        snapshot = observation_snapshot()
        predictions = snapshot["analysis_models"]["ten_day_return"]["shadow_predictions"]
        second_a_share = deepcopy(predictions[0])
        second_a_share.update(
            {
                "code": "600001",
                "probability": 0.80,
                "expected_net_return": 0.08,
                "expected_net_utility": 0.05,
            }
        )
        predictions.append(second_a_share)
        cohorts = model_observation_ledger.build_observation_cohorts(
            {snapshot["snapshot_key"]: snapshot}
        )
        cohort = next(iter(cohorts.values()))
        exit_prices = {"600000": 90.0, "600001": 110.0, "0700.HK": 103.0, "NVDA": 105.0}

        def loader(market: str, code: str):
            prediction = next(
                row
                for row in cohort["revisions"][-1]["predictions"]
                if row["market"] == market and row["code"] == code
            )
            return (
                [
                    {"date": prediction["entry_trade_date"], "open": 100.0, "close": 100.0},
                    {
                        "date": prediction["forecast_end_trade_date"],
                        "open": exit_prices[code],
                        "close": exit_prices[code],
                    },
                ],
                "fixture_adjusted_daily",
                True,
            )

        batch = observation_outcome_ledger.settle_observation_cohort(
            cohort,
            "2026-09-07T00:00:00Z",
            loader,
        )
        diagnostics = history_evaluation.evaluate_observation_performance(
            cohorts,
            {cohort["cohort_id"]: batch},
        )

        self.assertEqual(diagnostics["settled_count"], 4)
        self.assertEqual(diagnostics["independent_cohort_day_count"], 1)
        self.assertEqual(diagnostics["market_coverage"]["a_share"]["settled_count"], 2)
        self.assertEqual(diagnostics["metrics"]["auc"]["value"], 1.0)
        self.assertEqual(diagnostics["metrics"]["daily_cross_sectional_rank_ic"]["value"], 1.0)
        self.assertEqual(diagnostics["metrics"]["auc"]["n"], 1)
        self.assertEqual(diagnostics["metrics"]["auc"]["cell_n"], 1)
        self.assertEqual(diagnostics["metrics"]["brier_score"]["cell_n"], 3)
        self.assertEqual(diagnostics["complete_metric_cell_count"], 3)
        self.assertEqual(diagnostics["incomplete_metric_cell_count"], 0)
        for name in (
            "brier_score",
            "brier_skill",
            "auc",
            "ece_10bin",
            "daily_cross_sectional_rank_ic",
            "top_decile_net_return",
            "top_decile_excess_return",
            "worst_decile_net_return",
        ):
            self.assertIn(name, diagnostics["metrics"])
        self.assertFalse(diagnostics["included_in_executable_performance"])
        self.assertFalse(diagnostics["authorizes_production"])

    def test_observation_metrics_exclude_incomplete_market_cells(self) -> None:
        snapshot = observation_snapshot()
        predictions = snapshot["analysis_models"]["ten_day_return"]["shadow_predictions"]
        second_a_share = deepcopy(predictions[0])
        second_a_share.update(
            {
                "code": "600001",
                "probability": 0.80,
                "expected_net_return": 0.08,
                "expected_net_utility": 0.05,
            }
        )
        predictions.append(second_a_share)
        cohorts = model_observation_ledger.build_observation_cohorts(
            {snapshot["snapshot_key"]: snapshot}
        )
        cohort = next(iter(cohorts.values()))

        def partial_loader(market: str, code: str):
            prediction = next(
                row
                for row in cohort["revisions"][-1]["predictions"]
                if row["market"] == market and row["code"] == code
            )
            if code == "600001":
                return [], "fixture_adjusted_daily", True
            return (
                [
                    {"date": prediction["entry_trade_date"], "open": 100.0, "close": 100.0},
                    {
                        "date": prediction["forecast_end_trade_date"],
                        "open": 105.0,
                        "close": 105.0,
                    },
                ],
                "fixture_adjusted_daily",
                True,
            )

        batch = observation_outcome_ledger.settle_observation_cohort(
            cohort,
            "2026-09-07T00:00:00Z",
            partial_loader,
        )
        diagnostics = history_evaluation.evaluate_observation_performance(
            cohorts,
            {cohort["cohort_id"]: batch},
        )

        self.assertEqual(diagnostics["incomplete_metric_cell_count"], 1)
        self.assertEqual(diagnostics["complete_metric_cell_count"], 2)
        self.assertEqual(diagnostics["metrics"]["brier_score"]["cell_n"], 2)
        self.assertEqual(diagnostics["metrics"]["auc"]["n"], 0)
        self.assertEqual(diagnostics["metrics"]["auc"]["status"], "UNAVAILABLE")

    def test_history_api_publishes_persisted_observation_settlement_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            picks = root / "picks"
            outcomes_root = root / "outcomes"
            picks.mkdir()
            recorded = model_observation_ledger.record_observation_revision(
                observation_snapshot(),
                directory=outcomes_root / "observations",
            )
            cohort = recorded["cohort"]

            def loader(market: str, code: str):
                prediction = next(
                    row
                    for row in cohort["revisions"][-1]["predictions"]
                    if row["market"] == market and row["code"] == code
                )
                return (
                    [
                        {"date": prediction["entry_trade_date"], "open": 100.0, "close": 100.0},
                        {
                            "date": prediction["forecast_end_trade_date"],
                            "open": 105.0,
                            "close": 105.0,
                        },
                    ],
                    "fixture_adjusted_daily",
                    True,
                )

            batch = observation_outcome_ledger.settle_observation_cohort(
                cohort,
                "2026-09-07T00:00:00Z",
                loader,
            )
            observation_outcome_ledger.write_outcome_batch(
                outcomes_root / "observation-settlements",
                batch,
            )
            with (
                mock.patch.object(server, "PICKS", picks),
                mock.patch.object(server, "OUTCOMES", outcomes_root),
                mock.patch.object(server, "EXECUTABLE_OUTCOMES", outcomes_root / "executable"),
            ):
                payload = server.history_payload(limit=30)

            performance = payload["history_evaluation"]["observation_performance"]
            self.assertEqual(performance["status"], "EARLY_SAMPLE")
            self.assertEqual(performance["settled_count"], 3)
            self.assertEqual(payload["meta"]["observation_ledger"]["settled_count"], 3)
            self.assertEqual(
                payload["meta"]["observation_ledger"]["settlement_status"],
                "EARLY_SAMPLE",
            )

    def test_history_payload_consolidates_runs_without_relabeling_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            picks = pathlib.Path(temporary)
            legacy = {
                "target_date": "2026-08-20",
                "signal_date": "2026-08-19",
                "generated_at": "2026-08-20T10:00:00+08:00",
                "decision": {
                    "action": "BUY_CANDIDATE",
                    "primary": {
                        "code": "600000",
                        "name": "旧策略标的",
                        "estimated_2d_range": {"text": "-1.0% ~ +3.0%"},
                    },
                },
            }
            write_snapshot(picks, "2026-08-20_2026-08-19_100000.json", legacy)
            legacy_latest = {**legacy, "generated_at": "2026-08-20T15:00:00+08:00"}
            write_snapshot(picks, "2026-08-20_2026-08-19_150000.json", legacy_latest)
            contract = {
                "target_date": "2026-08-21",
                "signal_date": "2026-08-20",
                "generated_at": "2026-08-21T15:30:00+08:00",
                "forecast_end_date": "2026-09-04",
                "global_decision": {
                    "contract_version": "global-10d-v1",
                    "decision_scope": "global_10d",
                    "action_basis": "strict_cross_market_gate_v1",
                    "action": "NO_VALID_PICK",
                    "primary": None,
                    "blocker_codes": ["NO_CANDIDATE_PASSED_STRICT_GATE"],
                },
            }
            write_snapshot(picks, "2026-08-21_2026-08-20_153000.json", contract)
            same_day_later_legacy = {
                **legacy,
                "target_date": "2026-08-21",
                "generated_at": "2026-08-21T22:00:00+08:00",
            }
            write_snapshot(picks, "2026-08-21_2026-08-20_220000.json", same_day_later_legacy)

            with (
                mock.patch.object(server, "PICKS", picks),
                mock.patch.object(server, "OUTCOMES", picks / "outcomes"),
                mock.patch.object(server, "EXECUTABLE_OUTCOMES", picks / "outcomes" / "executable"),
            ):
                daily = server.history_payload(limit=120)
                raw = server.history_payload(limit=120, view="raw")

            self.assertEqual(len(daily["history"]), 2)
            self.assertEqual(daily["meta"]["raw_run_count"], 4)
            self.assertEqual(daily["meta"]["decision_day_count"], 2)
            self.assertEqual(daily["meta"]["duplicate_run_count"], 2)
            self.assertEqual(daily["meta"]["global_contract_day_count"], 1)
            self.assertEqual(daily["meta"]["legacy_day_count"], 1)
            self.assertEqual(raw["meta"]["view"], "raw")
            self.assertEqual(len(raw["history"]), 4)
            self.assertEqual(
                daily["history_evaluation"]["observation_performance"]["status"],
                "NO_SAMPLE",
            )
            self.assertEqual(
                daily["meta"]["observation_ledger"]["settlement_status"],
                "NO_SAMPLE",
            )
            contract_row = next(row for row in daily["history"] if row["target_date"] == "2026-08-21")
            self.assertEqual(contract_row["history_kind"], "global_10d_v1")

            legacy_row = next(row for row in daily["history"] if row["history_kind"] == "legacy_snapshot")
            self.assertEqual(legacy_row["action"], "LEGACY_ONLY")
            self.assertIsNone(legacy_row["global_decision"])
            self.assertEqual(legacy_row["a_share_legacy"]["estimated_2d_range"], "-1.0% ~ +3.0%")
            self.assertIsNone(legacy_row["a_share_legacy"]["estimated_2w_range"])

    def test_invalid_settled_outcome_stays_out_of_settled_count(self) -> None:
        row = formal_row("p-1")
        row["outcome"]["model_id"] = "wrong-model"
        invalid = server.history_metadata([row], [row], "daily", 1)
        self.assertEqual(invalid["executable_prediction_count"], 1)
        self.assertEqual(invalid["settled_sample_count"], 0)
        self.assertEqual(invalid["invalid_settlement_count"], 1)
        self.assertEqual(invalid["missing_outcome_count"], 0)

        row["outcome"]["model_id"] = "model-1"
        valid = server.history_metadata([row], [row], "daily", 1)
        self.assertEqual(valid["settled_sample_count"], 1)
        self.assertEqual(valid["missing_outcome_count"], 0)

        for invalid_return in (None, "", "0.08", True):
            with self.subTest(net_total_return=invalid_return):
                row["outcome"]["net_total_return"] = invalid_return
                invalid = server.history_metadata([row], [row], "daily", 1)
                self.assertEqual(invalid["settled_sample_count"], 0)
                self.assertEqual(invalid["invalid_settlement_count"], 1)
                self.assertEqual(invalid["missing_outcome_count"], 0)

        row["outcome"].update(
            {
                "net_total_return": 0.08,
                "positive_label": True,
                "exit_at": "2026-08-14T18:00:00Z",
                "settled_at": "2026-08-14T19:00:00Z",
            }
        )
        timezone_aligned = server.history_metadata([row], [row], "daily", 1)
        self.assertEqual(timezone_aligned["settled_sample_count"], 1)

    def test_no_valid_pick_is_abstention_not_prediction_or_loss(self) -> None:
        row = {
            "target_date": "2026-08-21",
            "history_kind": "global_10d_v1",
            "global_decision": {"action": "NO_VALID_PICK", "primary": None},
        }
        meta = server.history_metadata([row], [row], "daily", 1)
        self.assertEqual(meta["no_valid_pick_day_count"], 1)
        self.assertEqual(meta["executable_prediction_count"], 0)
        self.assertEqual(meta["settled_sample_count"], 0)

    def test_strict_metrics_use_only_identity_consistent_formal_settlements(self) -> None:
        rows = [
            formal_row("p-1", probability=0.8, utility=0.07, net_return=0.10, day=1),
            formal_row("p-2", probability=0.4, utility=0.01, net_return=-0.05, day=2),
            formal_row("p-3", probability=0.6, utility=0.04, net_return=0.03, day=3),
        ]
        performance = history_evaluation.evaluate_formal_performance(rows)

        self.assertEqual(performance["schema_version"], "history-performance-v1")
        self.assertEqual(performance["sample_status"], "EARLY_SAMPLE")
        self.assertEqual(performance["settled_sample_count"], 3)
        metrics = performance["metrics"]
        self.assertAlmostEqual(metrics["mean_net_return"]["value"], 0.08 / 3)
        self.assertAlmostEqual(metrics["positive_rate"]["value"], 2 / 3)
        self.assertEqual(metrics["top_decile_positive_rate"]["value"], 1.0)
        self.assertAlmostEqual(metrics["selection_rank_ic"]["value"], 1.0)
        self.assertAlmostEqual(metrics["brier_score"]["value"], 0.12)
        self.assertAlmostEqual(metrics["ece_10bin"]["value"], 1 / 3)
        self.assertAlmostEqual(metrics["expected_shortfall_10pct"]["value"], -0.05)
        self.assertAlmostEqual(metrics["settlement_sequence_max_drawdown"]["value"], 0.05)
        self.assertEqual(metrics["comparable_sample_count"]["value"], 3)
        self.assertEqual(metrics["top_decile_positive_rate"]["n"], 1)
        self.assertEqual(metrics["top_decile_positive_rate"]["min_n"], 5)
        self.assertEqual(metrics["top_decile_positive_rate"]["status"], "INSUFFICIENT_SAMPLE")
        self.assertEqual(metrics["expected_shortfall_10pct"]["n"], 1)
        self.assertEqual(metrics["expected_shortfall_10pct"]["min_n"], 5)
        self.assertEqual(metrics["expected_shortfall_10pct"]["status"], "INSUFFICIENT_SAMPLE")
        for metric in metrics.values():
            self.assertIn("method", metric)
            self.assertIn("status", metric)

    def test_latest_model_and_latest_run_per_target_date_define_formal_cohort(self) -> None:
        old_first = set_formal_version(formal_row("old-1", net_return=0.50, day=1), "model-old", "labels-old")
        old_second = set_formal_version(formal_row("old-2", net_return=0.40, day=2), "model-old", "labels-old")
        new_early = set_formal_version(formal_row("new-early", net_return=-0.30, day=3), "model-new", "labels-new")
        new_late = set_formal_version(formal_row("new-late", net_return=0.20, day=3), "model-new", "labels-new")
        new_late["generated_at"] = "2026-08-03T10:00:00+08:00"
        new_last_day = set_formal_version(formal_row("new-day-2", net_return=-0.02, day=4), "model-new", "labels-new")

        performance = history_evaluation.evaluate_formal_performance(
            [old_first, old_second, new_early, new_late, new_last_day]
        )

        self.assertEqual(performance["cohort_selection_policy"], "latest_published_model_latest_target_date_run_v1")
        self.assertEqual(performance["cohort_model_id"], "model-new")
        self.assertEqual(performance["cohort_label_version"], "labels-new")
        self.assertEqual(performance["model_ids"], ["model-new"])
        self.assertEqual(performance["label_versions"], ["labels-new"])
        self.assertEqual(performance["executable_prediction_count"], 5)
        self.assertEqual(performance["cohort_prediction_count"], 3)
        self.assertEqual(performance["cohort_independent_day_count"], 2)
        self.assertEqual(performance["cohort_same_day_excluded_count"], 1)
        self.assertEqual(performance["cohort_executable_prediction_count"], 2)
        self.assertEqual(performance["settled_sample_count"], 2)
        self.assertEqual(performance["sample_count"], 2)
        self.assertAlmostEqual(performance["metrics"]["mean_net_return"]["value"], 0.09)

    def test_formal_summary_annotation_never_treats_raw_settled_as_valid(self) -> None:
        valid = history_evaluation.annotate_formal_sample(formal_row("valid"))
        self.assertEqual(valid["formal_sample_status"], "SETTLED_VALID")
        self.assertEqual(valid["outcome_validation"], {"status": "VALID", "valid": True, "reason": None})

        invalid = formal_row("invalid")
        invalid["outcome"]["exit_price"] += 1.0
        history_evaluation.annotate_formal_sample(invalid)
        self.assertEqual(invalid["formal_sample_status"], "SETTLED_INVALID")
        self.assertFalse(invalid["outcome_validation"]["valid"])
        self.assertEqual(invalid["outcome_validation"]["reason"], "OUTCOME_GROSS_ARITHMETIC_MISMATCH")

        pending = formal_row("pending")
        pending["outcome"]["status"] = "PENDING"
        history_evaluation.annotate_formal_sample(pending)
        self.assertEqual(pending["formal_sample_status"], "PENDING")
        self.assertEqual(pending["outcome_validation"]["reason"], "OUTCOME_PENDING")

        missing = formal_row("missing")
        missing.pop("outcome")
        history_evaluation.annotate_formal_sample(missing)
        self.assertEqual(missing["formal_sample_status"], "MISSING")
        self.assertEqual(missing["outcome_validation"]["reason"], "EXECUTABLE_OUTCOME_MISSING")

        abstained = formal_row("abstained")
        abstained["global_decision"].update({"action": "NO_VALID_PICK", "primary": None})
        history_evaluation.annotate_formal_sample(abstained)
        self.assertEqual(abstained["formal_sample_status"], "ABSTAINED")
        self.assertEqual(abstained["outcome_validation"]["reason"], "NO_VALID_PICK")

    def test_strict_validator_rejects_arithmetic_probability_label_and_nonfinite_values(self) -> None:
        cases = {}
        cases["probability"] = formal_row("bad-probability", probability=1.1)
        cases["arithmetic"] = formal_row("bad-arithmetic")
        cases["arithmetic"]["outcome"]["exit_price"] += 1.0
        cases["label"] = formal_row("bad-label")
        cases["label"]["outcome"]["positive_label"] = False
        cases["nonfinite"] = formal_row("bad-nonfinite")
        cases["nonfinite"]["outcome"]["net_total_return"] = math.inf
        cases["root-date"] = formal_row("primary-date-wins")
        cases["root-date"]["forecast_end_date"] = "2099-12-31"

        for name, row in cases.items():
            with self.subTest(name=name):
                valid, _ = history_evaluation.valid_formal_settlement(row)
                self.assertEqual(valid, name == "root-date")

        missing_primary_date = deepcopy(formal_row("missing-primary-date"))
        missing_primary_date["global_decision"]["primary"].pop("forecast_end_trade_date")
        valid, reason = history_evaluation.valid_formal_settlement(missing_primary_date)
        self.assertFalse(valid)
        self.assertEqual(reason, "PRIMARY_IDENTITY_INCOMPLETE")

    def test_formal_outcome_rejects_wrong_schema_and_source_snapshot(self) -> None:
        wrong_schema = formal_row("wrong-schema")
        wrong_schema["outcome"]["schema_version"] = "shadow-outcome-v1"
        valid, reason = history_evaluation.valid_formal_settlement(wrong_schema)
        self.assertFalse(valid)
        self.assertEqual(reason, "OUTCOME_FROZEN_CONTRACT_MISMATCH")

        wrong_source = formal_row("wrong-source")
        wrong_source["outcome"]["source_snapshot"] = "another-snapshot.json"
        valid, reason = history_evaluation.valid_formal_settlement(wrong_source)
        self.assertFalse(valid)
        self.assertEqual(reason, "OUTCOME_SOURCE_SNAPSHOT_MISMATCH")
        self.assertIsNone(
            history_evaluation.matching_outcome(
                wrong_source,
                {"wrong-source": wrong_source["outcome"]},
                history_evaluation.EXECUTABLE_TRACK,
            )
        )

    def test_same_prediction_id_conflicts_when_frozen_model_identity_changes(self) -> None:
        original = formal_row("identity-conflict")
        changed = deepcopy(original)
        changed["global_decision"]["primary"]["probability"] = 0.8
        changed["outcome"]["probability"] = 0.8

        accepted, diagnostics = history_evaluation.select_formal_cohort([original, changed])

        self.assertEqual(accepted, [])
        self.assertEqual(diagnostics["conflict_count"], 1)
        self.assertEqual(
            diagnostics["exclusion_reason_counts"],
            {"PRIMARY_IDENTITY_CONFLICT": 1},
        )

    def test_net_return_may_fall_below_minus_one_after_transaction_cost(self) -> None:
        row = formal_row("fee-below-minus-one", net_return=-1.001)
        self.assertGreater(row["outcome"]["gross_total_return"], -1.0)
        self.assertLess(row["outcome"]["net_total_return"], -1.0)

        valid, reason = history_evaluation.valid_formal_settlement(row)

        self.assertTrue(valid)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()

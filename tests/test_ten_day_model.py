from __future__ import annotations

import datetime as dt
import json
import math
import unittest

import ten_day_model


def synthetic_rows(count: int = 260, phase: int = 4) -> list[dict]:
    rows = []
    day = dt.date(2025, 1, 2)
    index = 0
    while len(rows) < count:
        if day.weekday() < 5:
            close = 100.0 + 0.04 * index + 8.0 * math.sin((index + phase) / 9.0) + 2.0 * math.sin(
                (index + phase) / 2.7
            )
            opening = close * (1.0 + 0.004 * math.sin((index + phase) / 3.3))
            rows.append(
                {
                    "date": day.isoformat(),
                    "open": opening,
                    "high": max(opening, close) * 1.01,
                    "low": min(opening, close) * 0.99,
                    "close": close,
                    "volume": 1_000_000 * (1.0 + 0.2 * math.sin((index + phase) / 5.0)),
                }
            )
            index += 1
        day += dt.timedelta(days=1)
    return rows


def generated_after_last_close(rows: list[dict]) -> str:
    last_day = dt.date.fromisoformat(rows[-1]["date"])
    return f"{(last_day + dt.timedelta(days=1)).isoformat()}T23:00:00+08:00"


class TenDayModelTests(unittest.TestCase):
    def test_feature_vector_ignores_future_rows(self) -> None:
        rows = synthetic_rows(80)
        first = ten_day_model.feature_vector(rows, 40)
        second = ten_day_model.feature_vector([*rows, *synthetic_rows(5)], 40)
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(ten_day_model.FEATURE_NAMES))
        self.assertTrue(all(math.isfinite(value) for value in first))

    def test_label_is_next_open_to_tenth_close_net_of_cost(self) -> None:
        rows = synthetic_rows(60)
        label = ten_day_model.ten_session_label(rows, 20, transaction_cost=0.003)
        expected = round(rows[30]["close"], 8) / round(rows[21]["open"], 8) - 1.0 - 0.003
        self.assertAlmostEqual(label.net_return, expected)
        self.assertEqual(label.positive, expected > 0)
        self.assertEqual(label.entry_date, rows[21]["date"])
        self.assertEqual(label.exit_date, rows[30]["date"])

    def test_split_keeps_dates_together_and_purges_ten_dates(self) -> None:
        rows = synthetic_rows(140)
        samples = []
        for index in range(20, 130):
            label = ten_day_model.ten_session_label(rows, index, 0.0015)
            for code in ("600000", "600001"):
                samples.append(
                    ten_day_model.Sample(
                        market="a_share",
                        code=code,
                        signal_date=rows[index]["date"],
                        signal_index=index,
                        entry_date=label.entry_date,
                        exit_date=label.exit_date,
                        features=ten_day_model.feature_vector(rows, index),
                        label=label,
                    )
                )
        split = ten_day_model.chronological_split(samples)
        self.assertTrue(set(split.train_dates).isdisjoint(split.calibration_dates))
        self.assertTrue(set(split.calibration_dates).isdisjoint(split.test_dates))
        self.assertEqual(len(split.purged_dates), 20)
        self.assertEqual({sample.signal_date for sample in split.train}, set(split.train_dates))
        self.assertEqual({sample.signal_date for sample in split.calibration}, set(split.calibration_dates))
        self.assertEqual({sample.signal_date for sample in split.test}, set(split.test_dates))

    def test_split_excludes_sparse_labels_that_cross_fold_boundaries(self) -> None:
        dates = []
        day = dt.date(2025, 1, 2)
        while len(dates) < 160:
            if day.weekday() < 5:
                dates.append(day.isoformat())
            day += dt.timedelta(days=1)

        def sample(code: str, signal_index: int, exit_index: int) -> ten_day_model.Sample:
            entry_index = min(signal_index + 1, exit_index)
            label = ten_day_model.Label(
                entry_date=dates[entry_index],
                exit_date=dates[exit_index],
                entry_price=100.0,
                exit_price=101.0,
                gross_return=0.01,
                transaction_cost=0.0015,
                net_return=0.0085,
                positive=True,
            )
            return ten_day_model.Sample(
                market="a_share",
                code=code,
                signal_date=dates[signal_index],
                signal_index=signal_index,
                entry_date=label.entry_date,
                exit_date=label.exit_date,
                features=(0.0,) * len(ten_day_model.FEATURE_NAMES),
                label=label,
            )

        samples = []
        for index in range(140):
            samples.append(sample("SAFE", index, index + 2))
        # With 30 calibration, 40 test and two 10-day purges, calibration
        # starts at index 60 and test starts at index 100.
        samples.append(sample("LEAK_TRAIN", 49, 60))
        samples.append(sample("LEAK_CALIBRATION", 89, 100))

        split = ten_day_model.chronological_split(samples)

        self.assertNotIn("LEAK_TRAIN", {row.code for row in split.train})
        self.assertNotIn("LEAK_CALIBRATION", {row.code for row in split.calibration})
        self.assertTrue(all(row.exit_date < split.calibration_dates[0] for row in split.train))
        self.assertTrue(all(row.exit_date < split.test_dates[0] for row in split.calibration))

    def test_completed_rows_excludes_current_partial_bar_before_market_close(self) -> None:
        rows = [
            {"date": "2026-08-20", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 10},
            {"date": "2026-08-21", "open": 10.5, "high": 12, "low": 10, "close": 11.5, "volume": 11},
        ]
        morning = ten_day_model.completed_rows(rows, "a_share", "2026-08-21T10:17:00+08:00")
        evening = ten_day_model.completed_rows(rows, "a_share", "2026-08-21T20:17:00+08:00")
        self.assertEqual([row["date"] for row in morning], ["2026-08-20"])
        self.assertEqual([row["date"] for row in evening], ["2026-08-20", "2026-08-21"])

    def test_snapshot_artifact_is_deterministic_for_input_order(self) -> None:
        histories = {f"A{phase}": synthetic_rows(250, phase) for phase in range(4, 8)}
        maps = {"a_share": histories, "hk": {}, "us": {}}
        reversed_maps = {"a_share": dict(reversed(list(histories.items()))), "hk": {}, "us": {}}
        generated_at = generated_after_last_close(next(iter(histories.values())))
        first = ten_day_model.build_snapshot_model_contract({}, maps, generated_at)
        second = ten_day_model.build_snapshot_model_contract({}, reversed_maps, generated_at)
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first["market_models"]["a_share"], second["market_models"]["a_share"])
        self.assertEqual(first["shadow_predictions"], second["shadow_predictions"])

    def test_backfill_model_can_never_self_authorize_production(self) -> None:
        histories = {f"A{phase}": synthetic_rows(250, phase) for phase in range(4, 10)}
        generated_at = generated_after_last_close(next(iter(histories.values())))
        contract = ten_day_model.build_snapshot_model_contract(
            {},
            {"a_share": histories, "hk": histories, "us": histories},
            generated_at,
        )
        self.assertIn(contract["status"], {"SHADOW_READY", "SHADOW_REJECTED", "INSUFFICIENT_DATA"})
        self.assertFalse(contract["calibrated"])
        self.assertFalse(contract["participates_in_decision"])
        self.assertFalse(contract["production_eligible"])
        self.assertIsNone(contract["probability"])
        self.assertEqual(contract["training_provenance"], "current_universe_historical_backfill")
        json.dumps(contract, allow_nan=False)

    def test_shadow_predictions_are_bounded_and_cost_consistent(self) -> None:
        histories = {f"A{phase}": synthetic_rows(250, phase) for phase in range(4, 10)}
        generated_at = generated_after_last_close(next(iter(histories.values())))
        contract = ten_day_model.build_snapshot_model_contract(
            {},
            {"a_share": histories, "hk": {}, "us": {}},
            generated_at,
        )
        self.assertTrue(contract["shadow_predictions"])
        self.assertEqual(contract["shadow_prediction_count"], len(contract["shadow_predictions"]))
        for row in contract["shadow_predictions"]:
            self.assertGreaterEqual(row["probability"], 0.0)
            self.assertLessEqual(row["probability"], 1.0)
            self.assertAlmostEqual(
                row["expected_net_utility"],
                row["expected_net_return"] - 0.25 * row["tail_risk"],
                places=7,
            )
            self.assertFalse(row["participates_in_decision"])
            self.assertFalse(row["production_eligible"])

    def test_validation_metrics_weight_dates_equally_and_rank_top_decile_per_date(self) -> None:
        records = [
            {
                "market": "a_share",
                "code": "ONLY",
                "signal_date": "2026-01-02",
                "probability": 0.50,
                "positive": True,
                "net_return": 1.0,
                "baseline_probability": 0.5,
            }
        ]
        for index in range(20):
            records.append(
                {
                    "market": "a_share",
                    "code": f"B{index:02d}",
                    "signal_date": "2026-01-05",
                    "probability": 0.99 - index * 0.01,
                    "positive": index < 2,
                    "net_return": 0.2 if index < 2 else 0.0,
                    "baseline_probability": 0.5,
                }
            )

        metrics = ten_day_model._validation_metrics(records, baseline_probability=0.5)

        self.assertEqual(metrics["validation_weighting"], "signal_date_equal_weight_v1")
        self.assertAlmostEqual(metrics["mean_net_return"], 0.51)
        self.assertAlmostEqual(metrics["top_decile_mean_net_return"], 0.6)
        self.assertAlmostEqual(metrics["top_decile_excess_vs_mean"], 0.09)
        self.assertEqual(metrics["independent_test_date_count"], 2)

    def test_shadow_ready_gate_requires_material_held_out_lift(self) -> None:
        passing = {
            "independent_test_date_count": 40,
            "brier_skill": 0.01,
            "auc": 0.55,
            "ece_10bin": 0.10,
            "top_decile_excess_vs_mean": 0.005,
            "top_decile_mean_net_return": 0.001,
        }
        self.assertTrue(ten_day_model._quality_gate_ready(passing))
        for field, rejected in (
            ("independent_test_date_count", 39),
            ("brier_skill", 0.0099),
            ("auc", 0.5499),
            ("ece_10bin", 0.1001),
            ("top_decile_excess_vs_mean", 0.0049),
            ("top_decile_mean_net_return", 0.0),
        ):
            with self.subTest(field=field):
                metrics = dict(passing)
                metrics[field] = rejected
                self.assertFalse(ten_day_model._quality_gate_ready(metrics))

    def test_cutoffs_use_observed_label_exit_and_predictions_freeze_market_artifact(self) -> None:
        histories = {f"A{phase}": synthetic_rows(250, phase) for phase in range(4, 10)}
        generated_at = generated_after_last_close(next(iter(histories.values())))
        samples, _ = ten_day_model._market_samples("a_share", histories, generated_at)
        split = ten_day_model.chronological_split(samples)

        contract = ten_day_model.build_snapshot_model_contract(
            {},
            {"a_share": histories, "hk": {}, "us": {}},
            generated_at,
        )
        market_model = contract["market_models"]["a_share"]
        expected_fit_cutoff = max(row.exit_date for row in (*split.train, *split.calibration))
        expected_validation_cutoff = max(row.exit_date for row in split.test)

        self.assertEqual(market_model["last_training_signal_date"], split.train_dates[-1])
        self.assertEqual(market_model["last_calibration_signal_date"], split.calibration_dates[-1])
        self.assertEqual(market_model["training_cutoff"], expected_fit_cutoff)
        self.assertEqual(market_model["fit_data_cutoff"], expected_fit_cutoff)
        self.assertEqual(market_model["validation_cutoff"], expected_validation_cutoff)
        self.assertGreater(market_model["training_cutoff"], market_model["last_calibration_signal_date"])
        for prediction in contract["shadow_predictions"]:
            self.assertEqual(prediction["artifact_sha256"], market_model["artifact_sha256"])
            self.assertEqual(prediction["training_cutoff"], market_model["training_cutoff"])
            self.assertEqual(prediction["fit_data_cutoff"], market_model["fit_data_cutoff"])

    def test_short_history_fails_closed_without_fake_metrics(self) -> None:
        rows = synthetic_rows(70)
        contract = ten_day_model.build_snapshot_model_contract(
            {},
            {"a_share": {"600000": rows}, "hk": {}, "us": {}},
            generated_after_last_close(rows),
        )
        self.assertEqual(contract["status"], "INSUFFICIENT_DATA")
        self.assertEqual(contract["validation"], {})
        self.assertEqual(contract["shadow_predictions"], [])

    def test_history_floor_fits_inside_a_260_bar_cache(self) -> None:
        short_rows = synthetic_rows(219)
        minimum_rows = synthetic_rows(220)

        short = ten_day_model.build_shadow_model(short_rows, generated_after_last_close(short_rows))
        fitted = ten_day_model.build_shadow_model(minimum_rows, generated_after_last_close(minimum_rows))

        self.assertEqual(short["status"], "INSUFFICIENT_DATA")
        self.assertIn(fitted["status"], {"SHADOW_READY", "SHADOW_REJECTED"})
        self.assertEqual(fitted["validation"]["independent_test_date_count"], 40)


if __name__ == "__main__":
    unittest.main()

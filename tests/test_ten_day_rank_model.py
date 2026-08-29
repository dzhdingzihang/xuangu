from __future__ import annotations

import datetime as dt
import json
import unittest

import ten_day_rank_model as rank_model


def price_rows(count: int, *, start: float, daily_step: float) -> list[dict]:
    day = dt.date(2025, 1, 2)
    rows = []
    while len(rows) < count:
        if day.weekday() < 5:
            index = len(rows)
            opening = start + daily_step * index
            rows.append(
                {
                    "date": day.isoformat(),
                    "open": opening,
                    "close": opening + daily_step * 0.5,
                }
            )
        day += dt.timedelta(days=1)
    return rows


def explicit_label(
    market: str,
    entry_date: str,
    exit_date: str,
    *,
    stock_net_return: float,
    benchmark_net_return: float = 0.0,
) -> rank_model.ExcessReturnLabel:
    stock_cost = rank_model.TRANSACTION_COSTS[market]
    benchmark_cost = rank_model.TRANSACTION_COSTS[market]
    return rank_model.ExcessReturnLabel(
        market=market,
        benchmark_code=rank_model.REGISTERED_BENCHMARKS[market],
        entry_date=entry_date,
        exit_date=exit_date,
        stock_entry_price=100.0,
        stock_exit_price=100.0 * (1.0 + stock_net_return + stock_cost),
        benchmark_entry_price=100.0,
        benchmark_exit_price=100.0 * (1.0 + benchmark_net_return + benchmark_cost),
        stock_transaction_cost=stock_cost,
        benchmark_transaction_cost=benchmark_cost,
        stock_gross_return=stock_net_return + stock_cost,
        stock_net_return=stock_net_return,
        benchmark_gross_return=benchmark_net_return + benchmark_cost,
        benchmark_net_return=benchmark_net_return,
        net_excess_return=stock_net_return - benchmark_net_return,
    )


def sample_for_date(
    signal_date: dt.date,
    code: str,
    feature: float,
    target: float,
    *,
    exit_offset: int = 10,
) -> rank_model.RankSample:
    entry = signal_date + dt.timedelta(days=1)
    exit_ = signal_date + dt.timedelta(days=exit_offset)
    return rank_model.RankSample(
        market="a_share",
        code=code,
        signal_date=signal_date.isoformat(),
        entry_date=entry.isoformat(),
        exit_date=exit_.isoformat(),
        features=(feature, feature * feature),
        label=explicit_label(
            "a_share",
            entry.isoformat(),
            exit_.isoformat(),
            stock_net_return=target + 0.01,
            benchmark_net_return=0.01,
        ),
    )


class TenDayRankModelTests(unittest.TestCase):
    def test_excess_label_uses_registered_benchmark_on_exact_window(self) -> None:
        stocks = price_rows(30, start=100.0, daily_step=1.0)
        benchmark = price_rows(30, start=200.0, daily_step=0.5)
        label = rank_model.ten_session_excess_label(
            stocks,
            benchmark,
            5,
            market="a_share",
        )

        expected_stock = stocks[15]["close"] / stocks[6]["open"] - 1.0 - 0.0015
        expected_benchmark = benchmark[15]["close"] / benchmark[6]["open"] - 1.0 - 0.0015
        self.assertEqual(label.benchmark_code, "510300")
        self.assertEqual(label.entry_date, stocks[6]["date"])
        self.assertEqual(label.exit_date, stocks[15]["date"])
        self.assertAlmostEqual(label.stock_net_return, expected_stock)
        self.assertAlmostEqual(label.benchmark_net_return, expected_benchmark)
        self.assertAlmostEqual(label.net_excess_return, expected_stock - expected_benchmark)

        with self.assertRaisesRegex(ValueError, "not registered"):
            rank_model.ten_session_excess_label(
                stocks,
                benchmark,
                5,
                market="a_share",
                benchmark_code="SPY",
            )

        missing_exit = [row for row in benchmark if row["date"] != stocks[15]["date"]]
        with self.assertRaisesRegex(ValueError, "missing the exact"):
            rank_model.ten_session_excess_label(stocks, missing_exit, 5, market="a_share")

    def test_all_valid_rows_are_used_without_twenty_four_symbol_cap(self) -> None:
        first = dt.date(2025, 1, 2)
        samples = [sample_for_date(first, f"A{index:03d}", float(index), index / 1000) for index in range(40)]
        samples.extend(
            sample_for_date(first + dt.timedelta(days=20), f"B{index:03d}", float(index), index / 800)
            for index in range(35)
        )

        model = rank_model.fit_date_equal_ridge(samples)

        self.assertEqual(model.sample_count, 75)
        self.assertEqual(model.signal_date_count, 2)
        self.assertEqual(model.l2, rank_model.FIXED_RIDGE_L2)

    def test_date_equal_weights_keep_all_rows_and_equalize_date_mass(self) -> None:
        first = dt.date(2025, 1, 2)
        samples = [sample_for_date(first, f"A{index}", float(index), 0.01) for index in range(40)]
        samples.append(sample_for_date(first + dt.timedelta(days=20), "ONLY", 1.0, 0.02))
        weights = rank_model.date_equal_weights(samples)

        self.assertEqual(len(weights), 41)
        self.assertAlmostEqual(sum(weights[:40]), weights[-1])
        self.assertAlmostEqual(sum(weights), 41.0)

    def test_fixed_ridge_is_deterministic_and_learns_continuous_target(self) -> None:
        first = dt.date(2025, 1, 2)
        samples = []
        for day_index in range(6):
            signal = first + dt.timedelta(days=day_index * 20)
            for symbol_index in range(30):
                feature = symbol_index / 10.0
                samples.append(sample_for_date(signal, f"S{day_index}-{symbol_index}", feature, 0.02 * feature - 0.01))

        forward = rank_model.fit_date_equal_ridge(samples)
        reverse = rank_model.fit_date_equal_ridge(list(reversed(samples)))

        self.assertEqual(forward, reverse)
        self.assertGreater(forward.predict((3.0, 9.0)), forward.predict((0.0, 0.0)))

    def test_walk_forward_purges_by_actual_exit_and_expands_without_overlap(self) -> None:
        first = dt.date(2024, 1, 2)
        samples = []
        for day_index in range(70):
            signal = first + dt.timedelta(days=day_index * 2)
            for symbol_index in range(3):
                samples.append(
                    sample_for_date(
                        signal,
                        f"S{day_index}-{symbol_index}",
                        float(symbol_index),
                        symbol_index / 100,
                        exit_offset=10 + (5 if symbol_index == 2 and day_index % 9 == 0 else 0),
                    )
                )

        folds = rank_model.expanding_walk_forward_splits(
            samples,
            min_train_days=20,
            test_block_days=10,
        )

        self.assertGreaterEqual(len(folds), 3)
        seen_test_dates: set[str] = set()
        previous_train_count = 0
        for fold in folds:
            self.assertTrue(all(row.exit_date < fold.test_dates[0] for row in fold.train))
            self.assertTrue(set(fold.test_dates).isdisjoint(seen_test_dates))
            self.assertGreaterEqual(len(fold.train_dates), previous_train_count)
            self.assertLess(fold.train_label_cutoff, fold.test_dates[0])
            seen_test_dates.update(fold.test_dates)
            previous_train_count = len(fold.train_dates)

    def test_appending_future_data_does_not_change_prior_fold_predictions(self) -> None:
        first = dt.date(2024, 1, 2)
        base = []
        future = []
        for day_index in range(65):
            signal = first + dt.timedelta(days=day_index * 2)
            target = 0.01 * ((day_index % 5) - 2)
            rows = [sample_for_date(signal, f"S{day_index}-{symbol}", float(symbol), target + symbol / 100) for symbol in range(4)]
            (base if day_index < 55 else future).extend(rows)

        before, before_folds = rank_model.walk_forward_predictions(
            base,
            min_train_days=20,
            test_block_days=10,
            max_folds=1,
        )
        after, after_folds = rank_model.walk_forward_predictions(
            [*base, *future],
            min_train_days=20,
            test_block_days=10,
            max_folds=1,
        )

        self.assertEqual(before_folds[0].train_dates, after_folds[0].train_dates)
        self.assertEqual(before_folds[0].test_dates, after_folds[0].test_dates)
        self.assertEqual(before, after)

    def test_daily_ranking_metrics_rank_within_date_then_weight_dates_equally(self) -> None:
        records = []
        for date_index, date_text in enumerate(("2026-01-05", "2026-01-06")):
            for index in range(10):
                realized = index / 100 + date_index / 1000
                records.append(
                    {
                        "market": "a_share",
                        "code": f"{date_index}-{index}",
                        "signal_date": date_text,
                        "predicted_net_excess_return": realized,
                        "net_excess_return": realized,
                        "stock_net_return": realized + 0.01,
                    }
                )

        metrics = rank_model.daily_ranking_metrics(records)

        self.assertEqual(metrics["independent_test_date_count"], 2)
        self.assertEqual(metrics["mean_daily_spearman_ic"], 1.0)
        self.assertAlmostEqual(metrics["mean_top_decile_net_excess_return"], 0.0905)
        self.assertAlmostEqual(metrics["mean_top1_stock_net_return"], 0.1005)
        self.assertEqual(metrics["top_decile_excess_hit_rate"], 1.0)
        self.assertEqual(metrics["top1_absolute_hit_rate"], 1.0)
        json.dumps(metrics, allow_nan=False)

    def test_block_bootstrap_resamples_complete_date_market_cells(self) -> None:
        records = [
            {
                "market": "a_share",
                "code": f"EARLY-{index}",
                "signal_date": "2026-01-02",
                "predicted_net_excess_return": index / 10,
                "net_excess_return": index / 10,
                "stock_net_return": index / 10,
            }
            for index in range(10)
        ]
        records.append(
            {
                "market": "a_share",
                "code": "LATE",
                "signal_date": "2026-01-03",
                "predicted_net_excess_return": -0.5,
                "net_excess_return": -0.5,
                "stock_net_return": -0.5,
            }
        )

        intervals = rank_model.block_bootstrap_confidence_intervals(
            records,
            repetitions=1,
            block_size=1,
        )

        # The fixed RNG first chooses the later one-row cell twice.  A valid
        # cell bootstrap therefore cannot leak a partial slice of the earlier
        # ten-row cell into this replicate.
        self.assertEqual(intervals["mean_top1_net_excess_return"]["lower"], -0.5)
        self.assertEqual(intervals["mean_top1_net_excess_return"]["upper"], -0.5)
        self.assertEqual(
            intervals["mean_top1_net_excess_return"]["resampling_unit"],
            "complete_date_market_cell",
        )

    def test_collecting_contract_can_never_self_authorize(self) -> None:
        signal = dt.date(2025, 1, 2)
        samples = [sample_for_date(signal, f"S{index}", float(index), index / 100) for index in range(40)]
        contract = rank_model.build_collecting_contract(
            samples,
            validation={
                "independent_test_date_count": 100,
                "mean_daily_spearman_ic": 0.50,
                "mean_top_decile_net_excess_return": 0.20,
            },
            fold_count=5,
        )

        self.assertEqual(contract["status"], "COLLECTING")
        self.assertEqual(contract["artifact_contract_version"], "ten-day-rank-artifact-v2")
        self.assertFalse(contract["calibrated"])
        self.assertFalse(contract["costs_ready"])
        self.assertFalse(contract["tail_risk_ready"])
        self.assertFalse(contract["participates_in_decision"])
        self.assertFalse(contract["production_eligible"])
        self.assertIsNone(contract["probability"])
        self.assertIsNone(contract["expected_net_excess_return"])
        self.assertEqual(contract["shadow_predictions"], [])
        self.assertEqual(contract["training_provenance"], "point_in_time_universe_ledger")
        json.dumps(contract, allow_nan=False)

    def test_invalid_ledger_reason_does_not_claim_verified_empty_history(self) -> None:
        contract = rank_model.build_collecting_contract(
            collection_diagnostics={"error_type": "ContractError", "sample_count": 0},
            additional_reason_codes=("POINT_IN_TIME_LEDGER_INVALID",),
        )
        self.assertIn("POINT_IN_TIME_LEDGER_INVALID", contract["reason_codes"])
        self.assertNotIn("POINT_IN_TIME_LEDGER_EMPTY", contract["reason_codes"])
        self.assertIn("collection_diagnostics", contract)

    def test_fit_walk_forward_uses_real_counts_final_holdout_and_never_promotes_itself(self) -> None:
        first = dt.date(2024, 1, 2)
        samples = []
        for day_index in range(75):
            signal = first + dt.timedelta(days=day_index * 2)
            for symbol in range(4):
                feature = float(symbol + day_index % 3)
                samples.append(
                    sample_for_date(
                        signal,
                        f"S{day_index}-{symbol}",
                        feature,
                        feature / 100,
                    )
                )

        contract = rank_model.fit_walk_forward(
            samples,
            min_train_days=20,
            test_block_days=10,
        )

        self.assertEqual(contract["status"], "SHADOW_READY")
        self.assertEqual(contract["sample_count"], 300)
        self.assertGreater(contract["fold_count"], 0)
        self.assertEqual(
            contract["validation"]["final_holdout"]["distinct_test_date_count"],
            10,
        )
        self.assertIn("block_bootstrap_95pct", contract["validation"])
        self.assertFalse(contract["validation"]["data_completeness_gate_passed"])
        self.assertFalse(contract["promotion_gate_passed"])
        self.assertFalse(contract["promotion_authorized"])
        self.assertFalse(contract["production_eligible"])
        self.assertFalse(contract["participates_in_decision"])
        json.dumps(contract, allow_nan=False)


if __name__ == "__main__":
    unittest.main()

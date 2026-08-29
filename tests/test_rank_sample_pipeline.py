from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import model_observation_ledger
import rank_sample_pipeline as pipeline
import observation_outcome_ledger
from tests.test_observation_outcome_ledger import complete_price_loader, observation_cohort
from tests.test_model_observation_ledger import snapshot as observation_snapshot


def observation() -> dict:
    return {
        "observation_id": "obs_0123456789abcdef01234567",
        "prediction_sha256": "a" * 64,
        "market": "a_share",
        "code": "600000",
        "scheduled_slot": "2026-08-21T22:47:00+08:00",
        "signal_at": "2026-08-21T22:48:00+08:00",
        "prediction_as_of": "2026-08-21",
        "entry_trade_date": "2026-08-24",
        "forecast_end_trade_date": "2026-09-04",
        "transaction_cost": 0.0015,
        "currency": "CNY",
        "calendar_id": "XSHG",
        "calendar_version": "exchange-calendars-4.13.2",
        "security_status": "ACTIVE",
        "feature_values": [
            {
                "name": "return_5d_pct",
                "value": 3.2,
                "missing": False,
                "observed_at": "2026-08-21T22:40:00+08:00",
                "source": "test-point-in-time",
                "schema_version": "point-in-time-technical-d1-v2",
            },
            {
                "name": "beta_60d",
                "value": None,
                "missing": True,
                "observed_at": "2026-08-21T22:40:00+08:00",
                "source": "test-point-in-time",
                "schema_version": "point-in-time-technical-d1-v2",
            },
        ],
    }


def settlement() -> dict:
    return {
        "status": "SETTLED",
        "observation_id": "obs_0123456789abcdef01234567",
        "prediction_sha256": "a" * 64,
        "market": "a_share",
        "code": "600000",
        "entry_trade_date": "2026-08-24",
        "forecast_end_trade_date": "2026-09-04",
        "corporate_action_adjusted": True,
        "rank_label": {
            "schema_version": "ten-session-net-excess-label-v1",
            "market": "a_share",
            "benchmark_code": "510300",
            "entry_date": "2026-08-24",
            "exit_date": "2026-09-04",
            "stock_entry_price": 100.0,
            "stock_exit_price": 105.0,
            "benchmark_entry_price": 200.0,
            "benchmark_exit_price": 204.0,
            "stock_transaction_cost": 0.0015,
            "benchmark_transaction_cost": 0.0015,
            "stock_gross_return": 0.05,
            "stock_net_return": 0.0485,
            "benchmark_gross_return": 0.02,
            "benchmark_net_return": 0.0185,
            "net_excess_return": 0.03,
            "transaction_cost_version": "market-round-trip-cost-v1",
            "corporate_action_adjusted": True,
        },
    }


def recorded_rank_fixture(
    root: pathlib.Path,
    *,
    extra_a_share_code: str | None = None,
    missing_stock_codes: frozenset[str] = frozenset(),
) -> tuple[dict, pathlib.Path, pathlib.Path, pathlib.Path, dict, dict]:
    source = observation_snapshot()
    source["feature_cutoff_at"] = "2026-08-21T22:50:00+08:00"
    if extra_a_share_code is not None:
        extra_prediction = copy.deepcopy(
            source["analysis_models"]["ten_day_return"]["shadow_predictions"][0]
        )
        extra_prediction["code"] = extra_a_share_code
        extra_prediction["artifact_sha256"] = "e" * 64
        source["analysis_models"]["ten_day_return"]["shadow_predictions"].append(
            extra_prediction
        )
    markets = {}
    for prediction in source["analysis_models"]["ten_day_return"]["shadow_predictions"]:
        markets.setdefault(prediction["market"], {"members": []})["members"].append(
            {
                "code": prediction["code"],
                "source": "frozen-fixture",
                "observed_at": "2026-08-21T22:49:00+08:00",
                "feature_snapshot": {
                    "technical": 70.0,
                    "return_5d_pct": 2.5,
                    "quality": 60.0,
                },
            }
        )
    source["point_in_time_universe"] = {"markets": markets}
    observations = root / "observations"
    outcomes = root / "outcomes"
    picks = root / "picks"
    picks.mkdir()
    cohort = model_observation_ledger.record_observation_revision(
        source,
        directory=observations,
    )["cohort"]

    def benchmark_loader(market: str, code: str):
        prediction = next(
            row
            for row in cohort["revisions"][-1]["predictions"]
            if row["market"] == market
        )
        return (
            [
                {"date": prediction["entry_trade_date"], "open": 200.0, "close": 201.0},
                {"date": prediction["forecast_end_trade_date"], "open": 203.0, "close": 204.0},
            ],
            "registered-benchmark-adjusted",
            True,
        )

    def stock_loader(market: str, code: str):
        if code in missing_stock_codes:
            return ([], "missing-adjusted-price", True)
        return complete_price_loader(market, code)

    batch = observation_outcome_ledger.settle_observation_cohort(
        cohort,
        "2026-09-05T00:00:00Z",
        stock_loader,
        benchmark_price_loader=benchmark_loader,
    )
    observation_outcome_ledger.write_outcome_batch(outcomes, batch)
    (picks / source["snapshot_key"]).write_text(json.dumps(source), encoding="utf-8")
    return source, observations, outcomes, picks, cohort, batch


class RankSamplePipelineTests(unittest.TestCase):
    def test_loader_reports_a_missing_outcome_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _source, observations, outcomes, picks, _cohort, _batch = recorded_rank_fixture(
                pathlib.Path(directory)
            )
            for path in outcomes.glob("*.json"):
                path.unlink()

            samples, diagnostics = pipeline.load_mature_rank_samples(
                observations,
                outcomes,
                picks,
                return_diagnostics=True,
            )

            self.assertEqual(samples, [])
            self.assertEqual(diagnostics["excluded_missing_outcome_batch_count"], 1)

    def test_loader_excludes_an_incomplete_date_market_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _source, observations, outcomes, picks, _cohort, batch = recorded_rank_fixture(
                pathlib.Path(directory),
                extra_a_share_code="600001",
                missing_stock_codes=frozenset({"600001"}),
            )
            self.assertEqual(
                [
                    (row["code"], row["status"])
                    for row in batch["outcomes"]
                    if row["market"] == "a_share"
                ],
                [("600000", "SETTLED"), ("600001", "PENDING_DATA")],
            )

            samples, diagnostics = pipeline.load_mature_rank_samples(
                observations,
                outcomes,
                picks,
                return_diagnostics=True,
            )

            self.assertEqual([row.market for row in samples], ["hk", "us"])
            self.assertEqual(diagnostics["sample_count"], 2)
            self.assertEqual(diagnostics["excluded_unsettled_outcome_count"], 1)
            self.assertEqual(diagnostics["excluded_pending_data_outcome_count"], 1)
            self.assertEqual(diagnostics["excluded_incomplete_market_cell_count"], 1)
            self.assertEqual(diagnostics["excluded_data_incomplete_market_cell_count"], 1)
            self.assertEqual(diagnostics["excluded_incomplete_market_cell_sample_count"], 1)

    def test_loader_rejects_replaced_source_snapshot_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, observations, outcomes, picks, _cohort, _batch = recorded_rank_fixture(
                pathlib.Path(directory)
            )
            replacement = copy.deepcopy(source)
            replacement["point_in_time_universe"]["markets"]["a_share"]["members"][0][
                "feature_snapshot"
            ]["technical"] = -70.0
            (picks / source["snapshot_key"]).write_text(
                json.dumps(replacement),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(pipeline.RankSampleError, "source snapshot binding"):
                pipeline.load_mature_rank_samples(observations, outcomes, picks)

    def test_loader_requires_cohort_aware_outcome_evidence_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            _source, observations, _outcomes, picks, cohort, batch = recorded_rank_fixture(root)
            tampered = copy.deepcopy(batch)
            row = tampered["outcomes"][0]
            row["exit_price"] = round(row["entry_price"] * 2.0, 8)
            row["gross_total_return"] = round(row["exit_price"] / row["entry_price"] - 1.0, 8)
            row["net_total_return"] = round(
                row["gross_total_return"] - row["transaction_cost"],
                8,
            )
            row["positive_label"] = row["net_total_return"] > 0
            label = row["rank_label"]
            label["stock_exit_price"] = row["exit_price"]
            label["stock_gross_return"] = row["gross_total_return"]
            label["stock_net_return"] = row["net_total_return"]
            label["net_excess_return"] = round(
                label["stock_net_return"] - label["benchmark_net_return"],
                8,
            )
            row["rank_label_sha256"] = observation_outcome_ledger._digest(label)
            row["outcome_sha256"] = observation_outcome_ledger._row_digest(row)
            tampered["batch_sha256"] = observation_outcome_ledger._batch_digest(tampered)
            observation_outcome_ledger.validate_outcome_batch(tampered)
            with self.assertRaises(observation_outcome_ledger.ObservationOutcomeConflictError):
                observation_outcome_ledger.validate_outcome_batch(tampered, cohort=cohort)
            tampered_outcomes = root / "tampered-outcomes"
            observation_outcome_ledger.write_outcome_batch(tampered_outcomes, tampered)

            with self.assertRaisesRegex(pipeline.RankSampleError, "cohort binding"):
                pipeline.load_mature_rank_samples(observations, tampered_outcomes, picks)

    def test_loader_joins_frozen_snapshot_features_to_mature_rank_labels(self) -> None:
        source = observation_snapshot()
        source["feature_cutoff_at"] = "2026-08-21T22:50:00+08:00"
        predictions = source["analysis_models"]["ten_day_return"]["shadow_predictions"]
        markets = {}
        for prediction in predictions:
            market = prediction["market"]
            markets.setdefault(
                market,
                {"members": []},
            )["members"].append(
                {
                    "code": prediction["code"],
                    "source": "frozen-fixture",
                    "observed_at": "2026-08-21T22:49:00+08:00",
                    "feature_snapshot": {
                        "technical": 70.0,
                        "return_5d_pct": 2.5,
                        "quality": 60.0,
                    },
                }
            )
        source["point_in_time_universe"] = {"markets": markets}
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            observations = root / "observations"
            outcomes = root / "outcomes"
            picks = root / "picks"
            picks.mkdir()
            recorded = model_observation_ledger.record_observation_revision(
                source,
                directory=observations,
            )
            cohort = recorded["cohort"]

            def benchmark_loader(market: str, code: str):
                prediction = next(
                    row
                    for row in cohort["revisions"][-1]["predictions"]
                    if row["market"] == market
                )
                return (
                    [
                        {"date": prediction["entry_trade_date"], "open": 200.0, "close": 201.0},
                        {"date": prediction["forecast_end_trade_date"], "open": 203.0, "close": 204.0},
                    ],
                    "registered-benchmark-adjusted",
                    True,
                )

            batch = observation_outcome_ledger.settle_observation_cohort(
                cohort,
                "2026-09-05T00:00:00Z",
                complete_price_loader,
                benchmark_price_loader=benchmark_loader,
            )
            observation_outcome_ledger.write_outcome_batch(outcomes, batch)
            (picks / source["snapshot_key"]).write_text(
                json.dumps(source),
                encoding="utf-8",
            )

            samples, diagnostics = pipeline.load_mature_rank_samples(
                observations,
                outcomes,
                picks,
                return_diagnostics=True,
            )

            self.assertEqual(len(samples), 3)
            self.assertEqual(diagnostics["sample_count"], 3)
            self.assertEqual(diagnostics["excluded_invalid_feature_count"], 0)
            self.assertTrue(all(sample.provenance_sha256 for sample in samples))

    def test_observation_settlement_can_freeze_registered_benchmark_label(self) -> None:
        cohort = observation_cohort()

        def benchmark_loader(market: str, code: str):
            prediction = next(
                row for row in cohort["revisions"][-1]["predictions"] if row["market"] == market
            )
            return (
                [
                    {"date": prediction["entry_trade_date"], "open": 200.0, "close": 201.0},
                    {"date": prediction["forecast_end_trade_date"], "open": 203.0, "close": 204.0},
                ],
                "registered-benchmark-adjusted",
                True,
            )

        batch = observation_outcome_ledger.settle_observation_cohort(
            cohort,
            "2026-09-05T00:00:00Z",
            complete_price_loader,
            benchmark_price_loader=benchmark_loader,
        )

        self.assertEqual(batch["status_counts"], {"SETTLED": 3})
        for row in batch["outcomes"]:
            label = row["rank_label"]
            self.assertEqual(
                label["benchmark_code"],
                pipeline.ten_day_rank_model.REGISTERED_BENCHMARKS[row["market"]],
            )
            self.assertAlmostEqual(
                label["net_excess_return"],
                label["stock_net_return"] - label["benchmark_net_return"],
            )

    def test_builds_fixed_width_sample_with_missingness_and_provenance(self) -> None:
        sample = pipeline.build_rank_sample(observation(), settlement())
        self.assertEqual(sample.label.net_excess_return, 0.03)
        self.assertEqual(len(sample.features), len(pipeline.FEATURE_NAMES) * 2)
        self.assertEqual(len(sample.feature_records), len(pipeline.FEATURE_NAMES))
        missing = {row["name"]: row["missing"] for row in sample.feature_records}
        self.assertFalse(missing["return_5d_pct"])
        self.assertTrue(missing["beta_60d"])
        self.assertRegex(sample.provenance_sha256, r"^[0-9a-f]{64}$")

    def test_rejects_features_observed_after_signal_time(self) -> None:
        row = observation()
        row["feature_values"][0]["observed_at"] = "2026-08-21T22:49:00+08:00"
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.build_rank_sample(row, settlement())

    def test_feature_cutoff_must_precede_frozen_entry_open(self) -> None:
        row = observation()
        row["entry_session_open_at"] = "2026-08-21T22:47:30+08:00"
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.build_rank_sample(row, settlement())

    def test_rejects_benchmark_cost_identity_and_adjustment_mismatch(self) -> None:
        wrong = settlement()
        wrong["rank_label"]["benchmark_code"] = "SPY"
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.build_rank_sample(observation(), wrong)

        wrong_observation = observation()
        wrong_observation["currency"] = "USD"
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.build_rank_sample(wrong_observation, settlement())

        wrong_observation = observation()
        wrong_observation["security_status"] = "DELISTED"
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.build_rank_sample(wrong_observation, settlement())

        wrong = settlement()
        wrong["rank_label"]["exit_date"] = "2026-09-05"
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.build_rank_sample(observation(), wrong)
        wrong = settlement()
        wrong["rank_label"]["transaction_cost_version"] = "unknown"
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.build_rank_sample(observation(), wrong)
        wrong = settlement()
        wrong["rank_label"]["corporate_action_adjusted"] = False
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.build_rank_sample(observation(), wrong)

    def test_duplicate_date_market_symbol_rows_fail_closed(self) -> None:
        sample = pipeline.build_rank_sample(observation(), settlement())
        with self.assertRaises(pipeline.RankSampleError):
            pipeline.validate_rank_samples([sample, copy.deepcopy(sample)])


if __name__ == "__main__":
    unittest.main()

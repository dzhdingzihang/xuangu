from __future__ import annotations

import datetime as dt
import pathlib
import tempfile
import unittest
from collections import Counter
from unittest import mock

import model_observation_ledger
import observation_outcome_ledger
from scripts import settle_observations
from scripts import settle_outcomes
from tests.test_model_observation_ledger import snapshot


class SettleObservationsTests(unittest.TestCase):
    def test_production_settlement_entrypoint_does_not_fetch_observation_prices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            picks.mkdir()
            model_observation_ledger.record_observation_revision(
                snapshot(),
                directory=outcomes / "observations",
            )
            with mock.patch.object(
                settle_observations,
                "run",
                side_effect=AssertionError("observation settlement must be delegated"),
            ) as observation_run:
                counters = settle_outcomes.run(picks, outcomes, dt.date(2026, 8, 25))

            observation_run.assert_not_called()
            self.assertEqual(counters["observation_outcome_prediction_count"], 3)
            self.assertEqual(counters["observation_outcome_fetched_symbol_count"], 0)
            self.assertEqual(counters["observation_outcome_worker_limit"], 0)

    def test_batch_retries_only_missing_symbols_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            observations = root / "observations"
            outcomes = root / "outcomes"
            recorded = model_observation_ledger.record_observation_revision(
                snapshot(),
                directory=observations,
            )
            cohort = recorded["cohort"]
            canonical = cohort["revisions"][-1]
            predictions = {
                (row["market"], row["code"]): row
                for row in canonical["predictions"]
            }
            calls: Counter[tuple[str, str]] = Counter()

            def retrying_loader(market: str, code: str):
                key = (market, code)
                calls[key] += 1
                if calls[key] == 1:
                    return [], "fixture_adjusted_daily", True
                prediction = predictions[key]
                return (
                    [
                        {"date": prediction["entry_trade_date"], "open": 100.0, "close": 101.0},
                        {
                            "date": prediction["forecast_end_trade_date"],
                            "open": 108.0,
                            "close": 110.0,
                        },
                    ],
                    "fixture_adjusted_daily",
                    True,
                )

            first = settle_observations.run(
                observations,
                outcomes,
                as_of="2026-09-07T00:00:00Z",
                price_loader=retrying_loader,
                max_workers=99,
                retries=2,
            )

            self.assertEqual(first["worker_limit"], 12)
            self.assertEqual(first["cohort_count"], 1)
            self.assertEqual(first["settled_count"], 3)
            self.assertEqual(first["pending_data_count"], 0)
            self.assertEqual(first["changed_cohort_count"], 1)
            self.assertEqual(set(calls.values()), {2})
            loaded = observation_outcome_ledger.load_outcome_batches(outcomes)
            self.assertEqual(next(iter(loaded.values()))["status_counts"], {"SETTLED": 3})

            calls.clear()
            second = settle_observations.run(
                observations,
                outcomes,
                as_of="2026-09-08T00:00:00Z",
                price_loader=retrying_loader,
            )
            self.assertEqual(calls, {})
            self.assertEqual(second["changed_cohort_count"], 0)
            self.assertEqual(second["unchanged_cohort_count"], 1)

    def test_immature_cohort_never_fetches_prices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            observations = root / "observations"
            outcomes = root / "outcomes"
            model_observation_ledger.record_observation_revision(
                snapshot(),
                directory=observations,
            )
            calls = []

            result = settle_observations.run(
                observations,
                outcomes,
                as_of="2026-08-25T00:00:00Z",
                price_loader=lambda market, code: calls.append((market, code)),
            )

            self.assertEqual(calls, [])
            self.assertEqual(result["pending_maturity_count"], 3)
            self.assertEqual(result["settled_count"], 0)

    def test_single_failed_source_round_is_persisted_as_pending_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            observations = root / "observations"
            outcomes = root / "outcomes"
            model_observation_ledger.record_observation_revision(
                snapshot(),
                directory=observations,
            )
            calls: Counter[tuple[str, str]] = Counter()

            def unavailable_loader(market: str, code: str):
                calls[(market, code)] += 1
                return [], "fixture_adjusted_daily", True

            result = settle_observations.run(
                observations,
                outcomes,
                as_of="2026-09-07T00:00:00Z",
                price_loader=unavailable_loader,
                retries=0,
            )

            self.assertEqual(set(calls.values()), {1})
            self.assertEqual(result["pending_data_count"], 3)
            self.assertEqual(result["settled_count"], 0)
            self.assertEqual(result["changed_cohort_count"], 1)
            loaded = observation_outcome_ledger.load_outcome_batches(outcomes)
            self.assertEqual(
                next(iter(loaded.values()))["status_counts"],
                {"PENDING_DATA": 3},
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest

import model_observation_ledger
import observation_outcome_ledger as outcomes
from tests.test_model_observation_ledger import snapshot


def observation_cohort() -> dict:
    return next(
        iter(
            model_observation_ledger.build_observation_cohorts(
                {snapshot()["snapshot_key"]: snapshot()}
            ).values()
        )
    )


def complete_price_loader(market: str, code: str):
    record = next(
        row
        for row in observation_cohort()["revisions"][-1]["predictions"]
        if row["market"] == market and row["code"] == code
    )
    return (
        [
            {"date": record["entry_trade_date"], "open": 100.0, "close": 101.0},
            {"date": record["forecast_end_trade_date"], "open": 108.0, "close": 110.0},
        ],
        "fixture_adjusted_daily",
        True,
    )


class ObservationOutcomeLedgerTests(unittest.TestCase):
    def assert_invalid_stock_bars_are_pending(self, loader) -> None:
        batch = outcomes.settle_observation_cohort(
            observation_cohort(),
            "2026-09-05T00:00:00Z",
            loader,
        )

        self.assertEqual(batch["status_counts"], {"PENDING_DATA": 3})
        for row in batch["outcomes"]:
            self.assertEqual(row["status"], "PENDING_DATA")
            self.assertEqual(row["reason_code"], "COMPLETE_ADJUSTED_BARS_MISSING")

    def test_duplicate_stock_bar_date_fails_closed(self) -> None:
        def duplicate_loader(market: str, code: str):
            rows, source, adjusted = complete_price_loader(market, code)
            return ([*rows, dict(rows[-1])], source, adjusted)

        self.assert_invalid_stock_bars_are_pending(duplicate_loader)

    def test_reverse_ordered_stock_bars_fail_closed(self) -> None:
        def reverse_loader(market: str, code: str):
            rows, source, adjusted = complete_price_loader(market, code)
            return (list(reversed(rows)), source, adjusted)

        self.assert_invalid_stock_bars_are_pending(reverse_loader)

    def test_future_dated_stock_bar_fails_closed(self) -> None:
        def future_loader(market: str, code: str):
            rows, source, adjusted = complete_price_loader(market, code)
            return (
                [*rows, {"date": "2026-09-06", "open": 111.0, "close": 112.0}],
                source,
                adjusted,
            )

        self.assert_invalid_stock_bars_are_pending(future_loader)

    def test_immature_rows_are_pending_without_loading_prices(self) -> None:
        calls = []
        batch = outcomes.settle_observation_cohort(
            observation_cohort(),
            "2026-08-25T00:00:00Z",
            lambda market, code: calls.append((market, code)),
        )

        self.assertEqual(calls, [])
        self.assertEqual(batch["status_counts"], {"PENDING_MATURITY": 3})
        self.assertTrue(all(row["status"] == "PENDING_MATURITY" for row in batch["outcomes"]))
        self.assertFalse(batch["included_in_executable_performance"])
        self.assertFalse(batch["authorizes_production"])

    def test_mature_missing_bars_stay_pending_data_not_zero_return(self) -> None:
        batch = outcomes.settle_observation_cohort(
            observation_cohort(),
            "2026-09-05T00:00:00Z",
            lambda *_: ([], "fixture_adjusted_daily", True),
        )

        self.assertEqual(batch["status_counts"], {"PENDING_DATA": 3})
        for row in batch["outcomes"]:
            self.assertEqual(row["status"], "PENDING_DATA")
            self.assertEqual(row["reason_code"], "COMPLETE_ADJUSTED_BARS_MISSING")
            self.assertNotIn("net_total_return", row)

    def test_complete_adjusted_bars_settle_net_return_and_bind_all_hashes(self) -> None:
        cohort = observation_cohort()
        batch = outcomes.settle_observation_cohort(
            cohort,
            "2026-09-05T00:00:00Z",
            complete_price_loader,
        )

        self.assertEqual(batch["status_counts"], {"SETTLED": 3})
        canonical = cohort["revisions"][-1]
        by_id = {row["observation_id"]: row for row in canonical["predictions"]}
        for row in batch["outcomes"]:
            source = by_id[row["observation_id"]]
            self.assertEqual(row["canonical_revision_id"], cohort["canonical_revision_id"])
            self.assertEqual(row["prediction_sha256"], source["prediction_sha256"])
            self.assertEqual(
                row["settlement_contract_sha256"],
                source["settlement_contract_sha256"],
            )
            self.assertEqual(row["entry_price"], 100.0)
            self.assertEqual(row["exit_price"], 110.0)
            self.assertEqual(row["gross_total_return"], 0.1)
            self.assertEqual(
                row["net_total_return"],
                round(0.1 - source["transaction_cost"], 8),
            )
            self.assertTrue(row["positive_label"])
            self.assertTrue(row["corporate_action_adjusted"])
            self.assertEqual(row["price_evidence"]["entry_bar"]["field"], "open")
            self.assertEqual(row["price_evidence"]["exit_bar"]["field"], "close")
            self.assertEqual(
                row["price_evidence_sha256"],
                row["price_evidence"]["evidence_sha256"],
            )
            self.assertRegex(row["outcome_sha256"], r"^[0-9a-f]{64}$")

    def test_pending_batch_can_follow_a_later_pre_entry_canonical_revision(self) -> None:
        primary = snapshot()
        first_cohort = next(
            iter(
                model_observation_ledger.build_observation_cohorts(
                    {primary["snapshot_key"]: primary}
                ).values()
            )
        )
        pending = outcomes.settle_observation_cohort(
            first_cohort,
            "2026-08-21T23:00:00+08:00",
            lambda *_: ([], "unused", True),
        )
        recovery = snapshot(
            generated_at="2026-08-21T23:18:00+08:00",
            source="2026-08-22_2026-08-21_231800.json",
        )
        recovered_cohort = next(
            iter(
                model_observation_ledger.build_observation_cohorts(
                    {
                        primary["snapshot_key"]: primary,
                        recovery["snapshot_key"]: recovery,
                    }
                ).values()
            )
        )

        rebuilt = outcomes.settle_observation_cohort(
            recovered_cohort,
            "2026-08-21T23:20:00+08:00",
            lambda *_: ([], "unused", True),
            existing=pending,
        )

        self.assertEqual(
            rebuilt["canonical_revision_id"],
            recovered_cohort["canonical_revision_id"],
        )
        self.assertEqual(rebuilt["status_counts"], {"PENDING_MATURITY": 3})

    def test_mature_or_settled_batch_cannot_follow_a_different_canonical_revision(self) -> None:
        primary = snapshot()
        first_cohort = next(
            iter(
                model_observation_ledger.build_observation_cohorts(
                    {primary["snapshot_key"]: primary}
                ).values()
            )
        )
        settled = outcomes.settle_observation_cohort(
            first_cohort,
            "2026-09-05T00:00:00Z",
            complete_price_loader,
        )
        recovery = snapshot(
            generated_at="2026-08-21T23:18:00+08:00",
            source="2026-08-22_2026-08-21_231800.json",
        )
        recovered_cohort = next(
            iter(
                model_observation_ledger.build_observation_cohorts(
                    {
                        primary["snapshot_key"]: primary,
                        recovery["snapshot_key"]: recovery,
                    }
                ).values()
            )
        )

        with self.assertRaises(outcomes.ObservationOutcomeConflictError):
            outcomes.settle_observation_cohort(
                recovered_cohort,
                "2026-09-06T00:00:00Z",
                complete_price_loader,
                existing=settled,
            )

    def test_batch_time_state_and_as_of_must_be_monotonic(self) -> None:
        cohort = observation_cohort()
        pending = outcomes.settle_observation_cohort(
            cohort,
            "2026-08-25T00:00:00Z",
            lambda *_: ([], "unused", True),
        )
        invalid = copy.deepcopy(pending)
        invalid["evaluated_at"] = "2026-09-06T00:00:00+00:00"
        invalid["batch_sha256"] = outcomes._batch_digest(invalid)
        with self.assertRaises(outcomes.ObservationOutcomeConflictError):
            outcomes.validate_outcome_batch(invalid, cohort=cohort)
        with self.assertRaises(outcomes.ObservationOutcomeConflictError):
            outcomes.settle_observation_cohort(
                cohort,
                "2026-08-24T00:00:00Z",
                lambda *_: ([], "unused", True),
                existing=pending,
            )

    def test_rehashed_price_evidence_tamper_fails_validation(self) -> None:
        cohort = observation_cohort()
        settled = outcomes.settle_observation_cohort(
            cohort,
            "2026-09-05T00:00:00Z",
            complete_price_loader,
        )
        tampered = copy.deepcopy(settled)
        evidence = tampered["outcomes"][0]["price_evidence"]
        evidence["entry_bar"]["value"] = 1.0
        tampered["outcomes"][0]["outcome_sha256"] = outcomes._row_digest(
            tampered["outcomes"][0]
        )
        tampered["batch_sha256"] = outcomes._batch_digest(tampered)
        with self.assertRaises(outcomes.ObservationOutcomeConflictError):
            outcomes.validate_outcome_batch(tampered, cohort=cohort)

    def test_settled_rows_are_immutable_and_repeat_is_byte_identical(self) -> None:
        cohort = observation_cohort()
        first = outcomes.settle_observation_cohort(
            cohort,
            "2026-09-05T00:00:00Z",
            complete_price_loader,
        )
        second = outcomes.settle_observation_cohort(
            cohort,
            "2026-09-06T00:00:00Z",
            lambda *_: ([], "later_missing_source", False),
            existing=first,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )

    def test_unchanged_pending_state_is_byte_identical_across_runs(self) -> None:
        cohort = observation_cohort()
        first = outcomes.settle_observation_cohort(
            cohort,
            "2026-08-25T00:00:00Z",
            lambda *_: ([], "unused", True),
        )
        second = outcomes.settle_observation_cohort(
            cohort,
            "2026-08-26T00:00:00Z",
            lambda *_: ([], "unused", True),
            existing=first,
        )

        self.assertEqual(second, first)

    def test_hash_or_identity_conflict_fails_closed(self) -> None:
        cohort = observation_cohort()
        settled = outcomes.settle_observation_cohort(
            cohort,
            "2026-09-05T00:00:00Z",
            complete_price_loader,
        )
        tampered = copy.deepcopy(settled)
        tampered["outcomes"][0]["net_total_return"] = 0.9

        with self.assertRaises(outcomes.ObservationOutcomeConflictError):
            outcomes.settle_observation_cohort(
                cohort,
                "2026-09-06T00:00:00Z",
                complete_price_loader,
                existing=tampered,
            )

    def test_rehashed_frozen_identity_tamper_still_fails_cohort_join(self) -> None:
        cohort = observation_cohort()
        settled = outcomes.settle_observation_cohort(
            cohort,
            "2026-09-05T00:00:00Z",
            complete_price_loader,
        )
        tampered = copy.deepcopy(settled)
        tampered["outcomes"][0]["code"] = "FOREIGN"
        tampered["outcomes"][0]["outcome_sha256"] = outcomes._row_digest(
            tampered["outcomes"][0]
        )
        tampered["batch_sha256"] = outcomes._batch_digest(tampered)

        with self.assertRaises(outcomes.ObservationOutcomeConflictError):
            outcomes.validate_outcome_batch(tampered, cohort=cohort)

    def test_atomic_file_round_trip_validates_complete_batch(self) -> None:
        batch = outcomes.settle_observation_cohort(
            observation_cohort(),
            "2026-08-25T00:00:00Z",
            lambda *_: ([], "unused", True),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = outcomes.write_outcome_batch(root, batch)
            loaded = outcomes.load_outcome_batches(root)

            self.assertEqual(loaded, {batch["cohort_id"]: batch})
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored["prediction_count"] += 1
            path.write_text(json.dumps(stored), encoding="utf-8")
            with self.assertRaises(outcomes.ObservationOutcomeConflictError):
                outcomes.load_outcome_batches(root)


if __name__ == "__main__":
    unittest.main()

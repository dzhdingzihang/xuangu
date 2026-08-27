from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

import model_observation_ledger
import observation_outcome_ledger
from scripts.merge_archive_payload import merge_payload
from tests.test_model_observation_ledger import (
    legacy_observation_cohort,
    rehash_revision_and_cohort,
    snapshot as observation_snapshot,
)


def write(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def snapshot(key: str, generated_at: str) -> dict:
    return {"snapshot_key": key, "generated_at": generated_at}


def scheduled_snapshot(
    key: str,
    generated_at: str,
    *,
    invocation: str,
) -> dict:
    return {
        **snapshot(key, generated_at),
        "automation": {
            "trigger": "schedule",
            "scheduled_slot": "2026-08-23T22:47:00+08:00",
            "scheduled_invocation_slot": invocation,
        },
    }


def observation_cohorts() -> tuple[dict, dict]:
    first_snapshot = observation_snapshot()
    first_revision = model_observation_ledger.build_observation_revision(
        first_snapshot,
        first_snapshot["snapshot_key"],
    )
    first = model_observation_ledger._cohort_from_revisions([first_revision])

    fallback_snapshot = copy.deepcopy(first_snapshot)
    fallback_snapshot["generated_at"] = "2026-08-21T23:17:00+08:00"
    fallback_snapshot["snapshot_key"] = "2026-08-22_2026-08-21_231700.json"
    fallback_snapshot["automation"]["scheduled_invocation_slot"] = (
        "2026-08-21T23:17:00+08:00"
    )
    fallback_revision = model_observation_ledger.build_observation_revision(
        fallback_snapshot,
        fallback_snapshot["snapshot_key"],
    )
    second = model_observation_ledger._cohort_from_revisions(
        [first_revision, fallback_revision]
    )
    return first, second


def observation_batch(
    cohort: dict,
    *,
    as_of: str,
    settled_codes: set[str] | None = None,
    exit_price: float = 110.0,
) -> dict:
    settled_codes = settled_codes or set()
    canonical = next(
        revision
        for revision in cohort["revisions"]
        if revision["revision_id"] == cohort["canonical_revision_id"]
    )
    predictions = {row["code"]: row for row in canonical["predictions"]}

    def loader(_market: str, code: str):
        prediction = predictions[code]
        if code not in settled_codes:
            return [], "fixture_adjusted_daily", True
        return (
            [
                {
                    "date": prediction["entry_trade_date"],
                    "open": 100.0,
                    "close": 101.0,
                },
                {
                    "date": prediction["forecast_end_trade_date"],
                    "open": 108.0,
                    "close": exit_price,
                },
            ],
            "fixture_adjusted_daily",
            True,
        )

    return observation_outcome_ledger.settle_observation_cohort(
        cohort,
        as_of,
        loader,
    )


def write_observation_pair(
    root: pathlib.Path,
    cohort: dict,
    batch: dict,
) -> None:
    cohort_id = cohort["cohort_id"]
    write(root / f"data/outcomes/observations/{cohort_id}.json", cohort)
    write(root / f"data/outcomes/observation-settlements/{cohort_id}.json", batch)


class MergeArchivePayloadTests(unittest.TestCase):
    def test_cli_imports_repository_modules_from_foreign_working_directory(self) -> None:
        script = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "merge_archive_payload.py"
        with tempfile.TemporaryDirectory() as foreign_cwd:
            completed = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=foreign_cwd,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("payload", completed.stdout)

    def test_new_legacy_observation_is_validated_and_written_current(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            current, _ = observation_cohorts()
            legacy = legacy_observation_cohort(current)
            relative = pathlib.Path(
                f"data/outcomes/observations/{current['cohort_id']}.json"
            )
            write(payload / relative, legacy)

            result = merge_payload(payload, archive)

            self.assertEqual(json.loads((archive / relative).read_text()), current)
            self.assertEqual(result["copied"], 1)

    def test_current_observation_upgrades_equivalent_two_revision_legacy_archive(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            _, current = observation_cohorts()
            legacy = legacy_observation_cohort(current)
            relative = pathlib.Path(
                f"data/outcomes/observations/{current['cohort_id']}.json"
            )
            write(payload / relative, current)
            write(archive / relative, legacy)

            result = merge_payload(payload, archive)

            self.assertEqual(json.loads((archive / relative).read_text()), current)
            self.assertEqual(result["updated"], 1)

    def test_legacy_incoming_cannot_downgrade_current_archive(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            _, current = observation_cohorts()
            legacy = legacy_observation_cohort(current)
            relative = pathlib.Path(
                f"data/outcomes/observations/{current['cohort_id']}.json"
            )
            write(payload / relative, legacy)
            write(archive / relative, current)

            result = merge_payload(payload, archive)

            self.assertEqual(json.loads((archive / relative).read_text()), current)
            self.assertEqual(result["unchanged"], 1)

    def test_same_revision_with_fully_rehashed_prediction_change_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            current, _ = observation_cohorts()
            changed = copy.deepcopy(current)
            row = changed["revisions"][0]["predictions"][0]
            row["probability"] = 0.99
            row["prediction_sha256"] = model_observation_ledger.prediction_sha256(row)
            row["settlement_contract_sha256"] = (
                model_observation_ledger.settlement_contract_sha256(row)
            )
            rehash_revision_and_cohort(changed)
            # Both files are independently valid, but the archive must not
            # accept a substantive rewrite under an existing revision_id.
            model_observation_ledger.validate_observation_cohort(changed)
            relative = pathlib.Path(
                f"data/outcomes/observations/{current['cohort_id']}.json"
            )
            write(payload / relative, changed)
            write(archive / relative, current)

            with self.assertRaisesRegex(ValueError, "observation revision conflict"):
                merge_payload(payload, archive)

    def test_newer_snapshot_replaces_archive_latest_and_keeps_immutable_file(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            old = snapshot("old.json", "2026-08-23T22:48:00+08:00")
            new = snapshot("new.json", "2026-08-24T08:20:00+08:00")
            write(payload / "data/picks/latest.json", new)
            write(payload / "data/picks/new.json", new)
            write(archive / "data/picks/latest.json", old)
            write(archive / "data/picks/old.json", old)

            result = merge_payload(payload, archive)

            self.assertEqual(json.loads((archive / "data/picks/latest.json").read_text()), new)
            self.assertEqual(json.loads((archive / "data/picks/new.json").read_text()), new)
            self.assertEqual(result["updated"], 1)
            self.assertEqual(result["copied"], 1)

    def test_older_retry_cannot_replace_newer_latest(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            old = snapshot("old.json", "2026-08-23T22:48:00+08:00")
            new = snapshot("new.json", "2026-08-23T23:18:00+08:00")
            write(payload / "data/picks/latest.json", old)
            write(payload / "data/picks/old.json", old)
            write(archive / "data/picks/latest.json", new)
            write(archive / "data/picks/new.json", new)

            result = merge_payload(payload, archive)

            self.assertEqual(json.loads((archive / "data/picks/latest.json").read_text()), new)
            self.assertTrue((archive / "data/picks/old.json").is_file())
            self.assertEqual(result["preserved_newer"], 1)

    def test_same_immutable_name_with_different_payload_fails(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            write(payload / "data/picks/latest.json", snapshot("same.json", "2026-08-23T22:48:00+08:00"))
            write(payload / "data/picks/same.json", {"value": 1})
            write(archive / "data/picks/same.json", {"value": 2})

            with self.assertRaisesRegex(ValueError, "immutable snapshot conflict"):
                merge_payload(payload, archive)

    def test_delayed_primary_is_archived_but_cannot_replace_newer_logical_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            delayed_primary = scheduled_snapshot(
                "delayed-primary.json",
                "2026-08-24T00:01:00+08:00",
                invocation="2026-08-23T22:47:00+08:00",
            )
            fallback = scheduled_snapshot(
                "fallback.json",
                "2026-08-23T23:27:00+08:00",
                invocation="2026-08-23T23:17:00+08:00",
            )
            write(payload / "data/picks/latest.json", delayed_primary)
            write(payload / "data/picks/delayed-primary.json", delayed_primary)
            write(archive / "data/picks/latest.json", fallback)
            write(archive / "data/picks/fallback.json", fallback)

            result = merge_payload(payload, archive)

            self.assertEqual(json.loads((archive / "data/picks/latest.json").read_text()), fallback)
            self.assertTrue((archive / "data/picks/delayed-primary.json").is_file())
            self.assertEqual(result["preserved_newer"], 1)

    def test_newer_logical_fallback_replaces_later_generated_primary(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            fallback = scheduled_snapshot(
                "fallback.json",
                "2026-08-23T23:27:00+08:00",
                invocation="2026-08-23T23:17:00+08:00",
            )
            delayed_primary = scheduled_snapshot(
                "delayed-primary.json",
                "2026-08-24T00:01:00+08:00",
                invocation="2026-08-23T22:47:00+08:00",
            )
            write(payload / "data/picks/latest.json", fallback)
            write(payload / "data/picks/fallback.json", fallback)
            write(archive / "data/picks/latest.json", delayed_primary)
            write(archive / "data/picks/delayed-primary.json", delayed_primary)

            result = merge_payload(payload, archive)

            self.assertEqual(json.loads((archive / "data/picks/latest.json").read_text()), fallback)
            self.assertTrue((archive / "data/picks/fallback.json").is_file())
            self.assertEqual(result["updated"], 1)

    def test_settled_outcome_is_not_downgraded_to_pending(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            identity = {
                "track": "EXECUTABLE_MODEL",
                "prediction_id": "pred_1",
                "model_id": "m",
                "label_version": "v",
                "market": "us",
                "code": "NVDA",
                "generated_at": "2026-08-23T22:48:00+08:00",
            }
            write(payload / "data/outcomes/executable/pred_1.json", {**identity, "status": "PENDING"})
            write(archive / "data/outcomes/executable/pred_1.json", {**identity, "status": "SETTLED"})

            result = merge_payload(payload, archive)

            stored = json.loads((archive / "data/outcomes/executable/pred_1.json").read_text())
            self.assertEqual(stored["status"], "SETTLED")
            self.assertEqual(result["preserved_newer"], 1)

    def test_new_canonical_replaces_old_all_pending_maturity_settlement(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            old_cohort, new_cohort = observation_cohorts()
            old_batch = observation_batch(old_cohort, as_of="2026-08-25T00:00:00Z")
            new_batch = observation_batch(new_cohort, as_of="2026-08-25T00:01:00Z")
            write_observation_pair(archive, old_cohort, old_batch)
            write_observation_pair(payload, new_cohort, new_batch)

            result = merge_payload(payload, archive)

            cohort_id = new_cohort["cohort_id"]
            stored = json.loads(
                (
                    archive
                    / f"data/outcomes/observation-settlements/{cohort_id}.json"
                ).read_text()
            )
            self.assertEqual(stored, new_batch)
            self.assertEqual(result["updated"], 2)

    def test_old_canonical_with_mature_rows_cannot_be_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            old_cohort, new_cohort = observation_cohorts()
            old_batch = observation_batch(old_cohort, as_of="2026-09-07T00:00:00Z")
            new_batch = observation_batch(new_cohort, as_of="2026-09-07T00:01:00Z")
            write_observation_pair(archive, old_cohort, old_batch)
            write_observation_pair(payload, new_cohort, new_batch)

            with self.assertRaisesRegex(
                ValueError,
                "mature observation settlement cannot change canonical revision",
            ):
                merge_payload(payload, archive)

    def test_same_canonical_partial_batches_union_settled_rows(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            cohort, _ = observation_cohorts()
            canonical = cohort["revisions"][-1]
            codes = [row["code"] for row in canonical["predictions"]]
            existing = observation_batch(
                cohort,
                as_of="2026-09-07T00:00:00Z",
                settled_codes={codes[0]},
            )
            incoming = observation_batch(
                cohort,
                as_of="2026-09-07T00:01:00Z",
                settled_codes={codes[1]},
            )
            write_observation_pair(archive, cohort, existing)
            write_observation_pair(payload, cohort, incoming)

            result = merge_payload(payload, archive)

            cohort_id = cohort["cohort_id"]
            stored = json.loads(
                (
                    archive
                    / f"data/outcomes/observation-settlements/{cohort_id}.json"
                ).read_text()
            )
            validated = observation_outcome_ledger.validate_outcome_batch(
                stored,
                cohort=cohort,
            )
            self.assertEqual(
                validated["status_counts"],
                {"PENDING_DATA": 1, "SETTLED": 2},
            )
            self.assertEqual(result["updated"], 1)

    def test_same_settled_observation_with_different_result_fails(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            payload, archive = root / "payload", root / "archive"
            cohort, _ = observation_cohorts()
            codes = {row["code"] for row in cohort["revisions"][-1]["predictions"]}
            existing = observation_batch(
                cohort,
                as_of="2026-09-07T00:00:00Z",
                settled_codes=codes,
                exit_price=110.0,
            )
            incoming = observation_batch(
                cohort,
                as_of="2026-09-07T00:01:00Z",
                settled_codes=codes,
                exit_price=111.0,
            )
            write_observation_pair(archive, cohort, existing)
            write_observation_pair(payload, cohort, incoming)

            with self.assertRaisesRegex(ValueError, "settled observation is immutable"):
                merge_payload(payload, archive)


if __name__ == "__main__":
    unittest.main()

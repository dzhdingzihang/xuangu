from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest

from scripts import scheduler_checkpoint_ledger as ledger


WORKFLOW_SHA = "a" * 40


def snapshot_for(
    checkpoint: dt.datetime,
    *,
    run_id: int,
    fallback: bool = False,
) -> dict:
    invocation = checkpoint + (dt.timedelta(minutes=30) if fallback else dt.timedelta())
    generated = invocation + dt.timedelta(minutes=5)
    return {
        "snapshot_key": f"fixture-{run_id}.json",
        "generated_at": generated.isoformat(timespec="seconds"),
        "automation": {
            "trigger": "schedule",
            "scheduled_slot": checkpoint.isoformat(timespec="seconds"),
            "scheduled_invocation_slot": invocation.isoformat(timespec="seconds"),
            "source_invocation_slot": invocation.isoformat(timespec="seconds"),
            "scheduler_delay_seconds": 0,
            "recovery_mode": "on_time",
            "scheduler_health": {
                "source_invocation_slot": invocation.isoformat(timespec="seconds"),
                "effective_checkpoint": checkpoint.isoformat(timespec="seconds"),
                "effective_invocation_slot": invocation.isoformat(timespec="seconds"),
                "scheduler_start_delay_seconds": 0,
                "recovery_mode": "on_time",
            },
        },
    }


def receipt_for(
    checkpoint: dt.datetime,
    *,
    run_id: int,
    publication_delay_minutes: int = 20,
    fallback: bool = False,
) -> dict:
    snapshot = snapshot_for(checkpoint, run_id=run_id, fallback=fallback)
    # A fallback invocation cannot be described as on-time because source and
    # effective invocation differ from the repaired logical checkpoint only in
    # the checkpoint mapping, not from each other.
    published = checkpoint + dt.timedelta(minutes=publication_delay_minutes)
    generated = dt.datetime.fromisoformat(snapshot["generated_at"])
    if published < generated:
        published = generated
    return ledger.create_receipt(
        snapshot,
        workflow_run_id=run_id,
        workflow_run_attempt=1,
        workflow_sha=WORKFLOW_SHA,
        published_at=published,
        verified_at=published,
    )


class SchedulerCheckpointLedgerTests(unittest.TestCase):
    def test_receipt_is_identity_bound_and_tampering_fails(self) -> None:
        checkpoint = dt.datetime.fromisoformat("2026-08-27T08:17:00+08:00")
        receipt = receipt_for(checkpoint, run_id=33250000001)

        self.assertEqual(receipt["contract_version"], ledger.RECEIPT_CONTRACT)
        self.assertEqual(receipt["receipt_id"], "ghrun_33250000001_1")
        self.assertEqual(receipt["verification_method"], "complete_deployment_contract_v1")
        self.assertEqual(ledger.validate_receipt(receipt), receipt)

        changed = copy.deepcopy(receipt)
        changed["snapshot_key"] = "different.json"
        with self.assertRaisesRegex(ledger.SchedulerReceiptError, "digest"):
            ledger.validate_receipt(changed)

    def test_write_and_install_are_idempotent_but_never_overwrite(self) -> None:
        checkpoint = dt.datetime.fromisoformat("2026-08-27T10:17:00+08:00")
        receipt = receipt_for(checkpoint, run_id=33250000002)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / ledger.receipt_filename(receipt)
            self.assertEqual(ledger.write_receipt(source, receipt), "created")
            self.assertEqual(ledger.write_receipt(source, receipt), "unchanged")

            installed, status = ledger.install_receipt(source, root / "installed")
            self.assertEqual(status, "created")
            self.assertEqual(ledger.install_receipt(source, root / "installed")[1], "unchanged")

            conflicting = json.loads(installed.read_text(encoding="utf-8"))
            conflicting["receipt_sha256"] = "0" * 64
            installed.write_text(json.dumps(conflicting), encoding="utf-8")
            with self.assertRaisesRegex(ledger.SchedulerReceiptError, "immutable|digest"):
                ledger.install_receipt(source, root / "installed")

    def test_fallback_receipt_repairs_the_primary_logical_checkpoint(self) -> None:
        checkpoint = dt.datetime.fromisoformat("2026-08-27T22:47:00+08:00")
        receipt = receipt_for(
            checkpoint,
            run_id=33250000003,
            publication_delay_minutes=35,
            fallback=True,
        )
        self.assertEqual(receipt["effective_checkpoint"], "2026-08-27T22:47:00+08:00")
        self.assertEqual(receipt["effective_invocation_slot"], "2026-08-27T23:17:00+08:00")

    def test_ledger_stays_initializing_before_a_full_evidence_window(self) -> None:
        evaluated = dt.datetime.fromisoformat("2026-08-27T18:00:00+08:00")
        expected = ledger.expected_primary_checkpoints(evaluated)
        receipts = [
            receipt_for(checkpoint, run_id=33251000000 + index)
            for index, checkpoint in enumerate(expected, start=1)
        ]

        result = ledger.aggregate_receipts(receipts, evaluated_at=evaluated)

        self.assertFalse(result["coverage_complete_24h"])
        self.assertEqual(result["readiness"], "INITIALIZING")
        self.assertEqual(result["checkpoint_coverage_status"], "INITIALIZING_24H_LEDGER")
        self.assertIsNone(result["missed_checkpoints_24h"])
        self.assertEqual(result["evidence_lag_batches"], 1)
        self.assertFalse(result["slo"]["guaranteed"])
        self.assertFalse(result["slo"]["public_data_source_sla"])

    def _full_window_receipts(self, evaluated: dt.datetime) -> tuple[list[dict], list[dt.datetime]]:
        expected = ledger.expected_primary_checkpoints(evaluated)
        receipts = [
            receipt_for(checkpoint, run_id=33252000000 + index)
            for index, checkpoint in enumerate(expected, start=1)
        ]
        # One older receipt establishes that the ledger existed throughout the
        # complete trailing window; it is not itself counted in that window.
        window_start = evaluated - dt.timedelta(hours=24)
        older = ledger.expected_primary_checkpoints(
            window_start,
            window_hours=48,
            grace_minutes=0,
        )
        seed_checkpoint = max(
            checkpoint
            for checkpoint in older
            if checkpoint <= window_start - dt.timedelta(minutes=45)
        )
        receipts.append(
            receipt_for(seed_checkpoint, run_id=33252999999, publication_delay_minutes=10)
        )
        return receipts, expected

    def test_complete_on_time_window_is_ready(self) -> None:
        evaluated = dt.datetime.fromisoformat("2026-08-27T18:00:00+08:00")
        receipts, expected = self._full_window_receipts(evaluated)

        result = ledger.aggregate_receipts(receipts, evaluated_at=evaluated)

        self.assertTrue(result["coverage_complete_24h"])
        self.assertEqual(result["readiness"], "READY")
        self.assertEqual(result["expected_checkpoints_24h"], len(expected))
        self.assertEqual(result["published_on_time_24h"], len(expected))
        self.assertEqual(result["late_recoveries_24h"], 0)
        self.assertEqual(result["missed_checkpoints_24h"], 0)

    def test_late_or_missing_publication_degrades_complete_window(self) -> None:
        evaluated = dt.datetime.fromisoformat("2026-08-27T18:00:00+08:00")
        receipts, expected = self._full_window_receipts(evaluated)
        missing_checkpoint = expected[0]
        receipts = [
            row
            for row in receipts
            if dt.datetime.fromisoformat(row["effective_checkpoint"]) != missing_checkpoint
        ]
        late_checkpoint = expected[1]
        for index, row in enumerate(receipts):
            if dt.datetime.fromisoformat(row["effective_checkpoint"]) == late_checkpoint:
                receipts[index] = receipt_for(
                    late_checkpoint,
                    run_id=33253000001,
                    publication_delay_minutes=60,
                )
                break

        result = ledger.aggregate_receipts(receipts, evaluated_at=evaluated)

        self.assertTrue(result["coverage_complete_24h"])
        self.assertEqual(result["readiness"], "DEGRADED")
        self.assertEqual(result["missed_checkpoints_24h"], 1)
        self.assertEqual(result["late_recoveries_24h"], 1)
        statuses = {row["checkpoint"]: row["status"] for row in result["checkpoints"]}
        self.assertEqual(statuses[missing_checkpoint.isoformat(timespec="seconds")], "MISSED")
        self.assertEqual(statuses[late_checkpoint.isoformat(timespec="seconds")], "LATE_RECOVERY")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.merge_archive_payload import merge_payload


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


class MergeArchivePayloadTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

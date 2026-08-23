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


class MergeArchivePayloadTests(unittest.TestCase):
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

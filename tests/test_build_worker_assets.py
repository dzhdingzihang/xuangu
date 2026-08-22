from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts import build_worker_assets


class BuildWorkerAssetsTests(unittest.TestCase):
    def test_shadow_outcome_is_joined_by_prediction_id_only(self) -> None:
        pick = {
            "global_decision": {
                "research_priority": {"prediction_id": "pred_0123456789abcdef01234567"}
            }
        }
        ledger = {
            "pred_0123456789abcdef01234567": {
                "track": "SHADOW_RESEARCH",
                "status": "PENDING",
                "prediction_id": "pred_0123456789abcdef01234567",
                "secret_internal_field": "must-not-publish",
            }
        }
        outcome = build_worker_assets.matching_shadow_outcome(pick, ledger)
        self.assertEqual(outcome["status"], "PENDING")
        self.assertNotIn("secret_internal_field", outcome)
        self.assertIsNone(build_worker_assets.matching_shadow_outcome({}, ledger))

    def test_read_outcome_map_rejects_filename_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "wrong.json"
            path.write_text(json.dumps({"prediction_id": "pred_right"}), encoding="utf-8")
            self.assertEqual(build_worker_assets.read_outcome_map(path.parent), {})


if __name__ == "__main__":
    unittest.main()

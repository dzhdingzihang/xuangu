from __future__ import annotations

import unittest

from scripts.snapshot_archive_policy import ARCHIVE_POLICY, archive_reasons


class SnapshotArchivePolicyTests(unittest.TestCase):
    def test_timespec_minutes_daily_checkpoint_is_archived(self) -> None:
        snapshot = {
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-25T22:47+08:00",
            }
        }

        self.assertEqual(archive_reasons(snapshot), ["DAILY_2247_CHECKPOINT"])

    def test_utc_daily_checkpoint_is_normalized_to_beijing(self) -> None:
        snapshot = {
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-25T14:47:00Z",
            }
        }

        self.assertEqual(archive_reasons(snapshot), ["DAILY_2247_CHECKPOINT"])

    def test_production_qualified_pick_is_archived_at_any_checkpoint(self) -> None:
        snapshot = {
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-25T20:17+08:00",
            },
            "production_decision": {
                "action": "QUALIFIED_PICK",
                "qualified_candidate_count": 2,
                "primary": {"status": "QUALIFIED"},
            },
        }

        self.assertEqual(archive_reasons(snapshot), ["PRODUCTION_QUALIFIED_PICK"])
        self.assertEqual(ARCHIVE_POLICY, "daily_2247_or_qualified_or_executable_v2")

    def test_unqualified_snapshot_outside_daily_checkpoint_is_not_archived(self) -> None:
        snapshot = {
            "automation": {
                "trigger": "schedule",
                "scheduled_slot": "2026-08-25T20:17+08:00",
            },
            "production_decision": {
                "action": "NO_QUALIFIED_PICK",
                "qualified_candidate_count": 0,
                "primary": None,
            },
            "global_decision": {"action": "NO_VALID_PICK", "primary": None},
        }

        self.assertEqual(archive_reasons(snapshot), [])

    def test_formal_executable_prediction_remains_archived(self) -> None:
        snapshot = {
            "global_decision": {
                "action": "REVIEW_EXECUTABLE_PICK",
                "primary": {"status": "EXECUTABLE"},
            }
        }

        self.assertEqual(archive_reasons(snapshot), ["EXECUTABLE_PREDICTION"])


if __name__ == "__main__":
    unittest.main()

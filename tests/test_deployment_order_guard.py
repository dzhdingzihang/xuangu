from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.deployment_order_guard import evaluate_path, publication_decision


def snapshot(
    key: str,
    generated_at: str,
    *,
    checkpoint: str | None,
    invocation: str | None,
    trigger: str = "schedule",
) -> dict:
    return {
        "snapshot_key": key,
        "generated_at": generated_at,
        "automation": {
            "trigger": trigger,
            "scheduled_slot": checkpoint,
            "scheduled_invocation_slot": invocation,
        },
    }


class DeploymentOrderGuardTests(unittest.TestCase):
    def test_delayed_primary_cannot_replace_newer_fallback(self) -> None:
        incoming = snapshot(
            "delayed-primary.json",
            "2026-08-26T00:01:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T22:47:00+08:00",
        )
        production = snapshot(
            "fallback.json",
            "2026-08-25T23:27:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )

        result = publication_decision(incoming, production)

        self.assertFalse(result["should_publish"])
        self.assertEqual(result["reason"], "production_logical_slot_is_newer")
        self.assertEqual(result["production_snapshot_key"], "fallback.json")

    def test_same_logical_invocation_can_publish_a_later_recovery(self) -> None:
        incoming = snapshot(
            "recovery-2.json",
            "2026-08-25T23:35:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )
        production = snapshot(
            "recovery-1.json",
            "2026-08-25T23:27:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )

        self.assertTrue(publication_decision(incoming, production)["should_publish"])

    def test_same_invocation_with_older_generation_is_blocked(self) -> None:
        incoming = snapshot(
            "older.json",
            "2026-08-25T23:20:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )
        production = snapshot(
            "newer.json",
            "2026-08-25T23:27:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )

        result = publication_decision(incoming, production)

        self.assertFalse(result["should_publish"])
        self.assertEqual(result["reason"], "production_same_slot_generation_is_newer")

    def test_same_invocation_and_moment_with_different_snapshot_fails_closed(self) -> None:
        incoming = snapshot(
            "incoming.json",
            "2026-08-25T23:27:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )
        production = snapshot(
            "production.json",
            "2026-08-25T23:27:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )

        result = publication_decision(incoming, production)

        self.assertFalse(result["should_publish"])
        self.assertEqual(result["reason"], "same_slot_same_moment_snapshot_conflict")

    def test_current_scheduled_incoming_cannot_fallback_to_checkpoint_metadata(self) -> None:
        incoming = snapshot(
            "missing-invocation.json",
            "2026-08-25T23:27:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation=None,
        )

        with self.assertRaisesRegex(ValueError, "missing its logical invocation slot"):
            publication_decision(incoming, {})

    def test_newer_primary_checkpoint_can_publish(self) -> None:
        incoming = snapshot(
            "next.json",
            "2026-08-26T08:20:00+08:00",
            checkpoint="2026-08-26T08:17:00+08:00",
            invocation="2026-08-26T08:17:00+08:00",
        )
        production = snapshot(
            "old.json",
            "2026-08-25T23:27:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )

        self.assertTrue(publication_decision(incoming, production)["should_publish"])

    def test_non_scheduled_manual_snapshot_is_not_ordered_by_cron(self) -> None:
        incoming = snapshot(
            "manual.json",
            "2026-08-26T00:02:00+08:00",
            checkpoint=None,
            invocation=None,
            trigger="workflow_dispatch",
        )
        production = snapshot(
            "scheduled.json",
            "2026-08-26T00:01:00+08:00",
            checkpoint="2026-08-25T22:47:00+08:00",
            invocation="2026-08-25T23:17:00+08:00",
        )

        self.assertEqual(
            publication_decision(incoming, production),
            {"should_publish": True, "reason": "non_scheduled_incoming"},
        )

    def test_evaluate_path_fetches_static_latest_asset(self) -> None:
        incoming = snapshot(
            "incoming.json",
            "2026-08-26T08:20:00+08:00",
            checkpoint="2026-08-26T08:17:00+08:00",
            invocation="2026-08-26T08:17:00+08:00",
        )
        requested: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "latest.json"
            path.write_text(json.dumps(incoming), encoding="utf-8")
            result = evaluate_path(
                path,
                base_url="https://selector.example.test/root/",
                fetcher=lambda url: requested.append(url) or {},
            )

        self.assertTrue(result["should_publish"])
        self.assertEqual(
            requested,
            ["https://selector.example.test/root/data/picks/latest.json"],
        )


if __name__ == "__main__":
    unittest.main()

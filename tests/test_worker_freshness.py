from __future__ import annotations

import json
import pathlib
import subprocess
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER_URI = (ROOT / "src" / "index.js").as_uri()


def run_node(script: str) -> None:
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Node freshness check failed ({completed.returncode})\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


class WorkerFreshnessTests(unittest.TestCase):
    def test_snapshot_use_contract_fails_closed_for_every_non_fresh_state(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const {{ snapshotUseContract }} = await import({json.dumps(WORKER_URI)} + "?snapshot-use-contract");
            const runtime = {{
              snapshot_key: "2026-08-27_fixture.json",
              generated_at: "2026-08-27T08:16:00+08:00",
              automation: {{ scheduled_slot: "2026-08-27T08:17:00+08:00" }},
              source_snapshot: {{ sha256: "a".repeat(64), byte_size: 12345 }},
              global_decision: {{ action: "REVIEW_EXECUTABLE_PICK" }},
            }};
            const stale = snapshotUseContract(runtime, new Date("2026-08-27T11:03:00+08:00"));
            assert.equal(stale.mode, "HISTORICAL_RESEARCH_ONLY");
            assert.equal(stale.current_decision_allowed, false);
            assert.equal(stale.execution_review_allowed, false);
            assert.deepEqual(stale.blocker_codes, ["SNAPSHOT_NOT_FRESH"]);
            assert.equal(stale.snapshot_key, runtime.snapshot_key);
            assert.equal(stale.source_snapshot_sha256, runtime.source_snapshot.sha256);
            assert.equal(stale.source_snapshot_byte_size, runtime.source_snapshot.byte_size);

            const freshRuntime = {{ ...runtime, generated_at: "2026-08-27T10:17:05+08:00", automation: {{ scheduled_slot: "2026-08-27T10:17:00+08:00" }} }};
            const fresh = snapshotUseContract(freshRuntime, new Date("2026-08-27T10:20:00+08:00"));
            assert.equal(fresh.mode, "CURRENT_RESEARCH");
            assert.equal(fresh.current_decision_allowed, true);
            assert.equal(fresh.execution_review_allowed, true);
            assert.deepEqual(fresh.blocker_codes, []);
            """
        )

    def test_active_watchdog_checkpoints_and_45_minute_grace(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const {{ snapshotFreshness }} = await import({json.dumps(WORKER_URI)} + "?freshness-weekday");

            const updating = snapshotFreshness(
              "2026-08-22T04:50:00+08:00",
              new Date("2026-08-24T09:00:00+08:00"),
            );
            assert.equal(updating.freshness_state, "updating");
            assert.equal(updating.expected_checkpoint, "2026-08-24T08:47:00+08:00");

            const stale = snapshotFreshness(
              "2026-08-22T04:50:00+08:00",
              new Date("2026-08-24T09:40:00+08:00"),
            );
            assert.equal(stale.freshness_state, "stale");
            assert.equal(stale.expected_checkpoint, "2026-08-24T08:47:00+08:00");

            const fresh = snapshotFreshness(
              "2026-08-24T08:50:00+08:00",
              new Date("2026-08-24T09:20:00+08:00"),
            );
            assert.equal(fresh.freshness_state, "fresh");
            assert.equal(fresh.expected_checkpoint, "2026-08-24T08:47:00+08:00");
            assert.equal(fresh.snapshot_age_minutes, 30);
            assert.equal(fresh.checkpoint_lag_minutes, 0);

            const usOpenUpdating = snapshotFreshness(
              "2026-08-24T20:50:00+08:00",
              new Date("2026-08-24T23:30:00+08:00"),
            );
            assert.equal(usOpenUpdating.freshness_state, "updating");
            assert.equal(usOpenUpdating.expected_checkpoint, "2026-08-24T23:17:00+08:00");
            """
        )

    def test_us_friday_post_close_becomes_saturday_beijing_checkpoint(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const {{ snapshotFreshness }} = await import({json.dumps(WORKER_URI)} + "?freshness-weekend");

            const weekend = snapshotFreshness(
              "2026-08-22T04:50:00+08:00",
              new Date("2026-08-22T12:00:00+08:00"),
            );
            assert.equal(weekend.freshness_state, "fresh");
            assert.equal(weekend.expected_checkpoint, "2026-08-22T04:47:00+08:00");
            assert.equal(weekend.snapshot_age_minutes, 430);
            assert.equal(weekend.checkpoint_lag_minutes, 0);

            const fridayGrace = snapshotFreshness(
              "2026-08-21T20:50:00+08:00",
              new Date("2026-08-21T23:30:00+08:00"),
            );
            assert.equal(fridayGrace.freshness_state, "updating");
            assert.equal(fridayGrace.expected_checkpoint, "2026-08-21T23:17:00+08:00");

            const afterGrace = snapshotFreshness(
              "2026-08-21T20:50:00+08:00",
              new Date("2026-08-22T00:03:00+08:00"),
            );
            assert.equal(afterGrace.freshness_state, "stale");
            assert.equal(afterGrace.expected_checkpoint, "2026-08-21T23:17:00+08:00");
            """
        )

    def test_next_scheduled_refresh_uses_the_current_watchdog_only_path(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const {{ nextScheduledRefresh }} = await import({json.dumps(WORKER_URI)} + "?next-refresh");

            assert.equal(
              nextScheduledRefresh(new Date("2026-08-21T20:18:00+08:00")),
              "2026-08-21T20:47:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-21T20:48:00+08:00")),
              "2026-08-21T23:17:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-21T22:48:00+08:00")),
              "2026-08-21T23:17:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-21T23:18:00+08:00")),
              "2026-08-22T04:47:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-22T12:00:00+08:00")),
              "2026-08-24T08:47:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-24T08:18:00+08:00")),
              "2026-08-24T08:47:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-24T08:48:00+08:00")),
              "2026-08-24T10:47:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-24T20:18:00+08:00")),
              "2026-08-24T20:47:00+08:00",
            );
            """
        )

    def test_all_intraday_next_refresh_and_expected_checkpoint_boundaries(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const module = await import({json.dumps(WORKER_URI)} + "?all-checkpoint-boundaries");
            const nextCases = [
              ["2026-08-24T08:18:00+08:00", "2026-08-24T08:47:00+08:00"],
              ["2026-08-24T08:48:00+08:00", "2026-08-24T10:47:00+08:00"],
              ["2026-08-24T10:18:00+08:00", "2026-08-24T10:47:00+08:00"],
              ["2026-08-24T10:48:00+08:00", "2026-08-24T12:47:00+08:00"],
              ["2026-08-24T12:18:00+08:00", "2026-08-24T12:47:00+08:00"],
              ["2026-08-24T12:48:00+08:00", "2026-08-24T15:47:00+08:00"],
              ["2026-08-24T15:18:00+08:00", "2026-08-24T15:47:00+08:00"],
              ["2026-08-24T15:48:00+08:00", "2026-08-24T16:47:00+08:00"],
              ["2026-08-24T16:18:00+08:00", "2026-08-24T16:47:00+08:00"],
              ["2026-08-24T16:48:00+08:00", "2026-08-24T20:47:00+08:00"],
              ["2026-08-24T20:18:00+08:00", "2026-08-24T20:47:00+08:00"],
              ["2026-08-24T20:48:00+08:00", "2026-08-24T23:17:00+08:00"],
              ["2026-08-24T22:48:00+08:00", "2026-08-24T23:17:00+08:00"],
              ["2026-08-24T23:18:00+08:00", "2026-08-25T04:47:00+08:00"],
            ];
            for (const [current, expected] of nextCases) {{
              assert.equal(module.nextScheduledRefresh(new Date(current)), expected, current);
            }}

            const activeCases = ["10:47", "12:47", "15:47", "16:47", "20:47", "23:17"];
            for (const checkpoint of activeCases) {{
              const [hour, minute] = checkpoint.split(":").map(Number);
              const current = new Date(Date.parse("2026-08-24T00:00:00+08:00") + (hour * 60 + minute + 13) * 60_000);
              const freshness = module.snapshotFreshness("2026-08-24T08:50:00+08:00", current);
              assert.equal(freshness.expected_checkpoint, `2026-08-24T${{checkpoint}}:00+08:00`, checkpoint);
              assert.equal(freshness.freshness_state, "updating", checkpoint);
            }}
            """
        )

    def test_missing_snapshot_is_unknown_and_status_exposes_contract(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const module = await import({json.dumps(WORKER_URI)} + "?freshness-api");
            const unknown = module.snapshotFreshness(null, new Date("2026-08-24T09:20:00+08:00"));
            assert.equal(unknown.freshness_state, "unknown");
            assert.equal(unknown.expected_checkpoint, "2026-08-24T08:47:00+08:00");
            assert.equal(unknown.snapshot_age_minutes, null);
            assert.equal(unknown.checkpoint_lag_minutes, null);

            const latest = {{
              generated_at: new Date().toISOString(),
              schema_version: "selector-snapshot-v2",
              snapshot_key: "2026-08-24_2026-08-21_090000.json",
            }};
            const env = {{
              ALLOW_LEGACY_FULL_SNAPSHOT_FALLBACK: "1",
              ASSETS: {{ async fetch(input) {{
                const url = new URL(typeof input === "string" ? input : input.url);
                return url.pathname === "/data/picks/latest.json"
                  ? new Response(JSON.stringify(latest), {{ headers: {{ "content-type": "application/json" }} }})
                  : new Response("not found", {{ status: 404 }});
              }} }},
            }};
            const response = await module.default.fetch(
              new Request("https://xuangu.alixjd.com/api/status"),
              env,
            );
            const status = await response.json();
            assert.match(status.freshness_state, /^(fresh|updating|stale|unknown)$/);
            assert.equal(typeof status.expected_checkpoint, "string");
            assert.equal(typeof status.snapshot_age_minutes, "number");
            assert.equal(typeof status.checkpoint_lag_minutes, "number");
            assert.equal(status.snapshot_key, latest.snapshot_key);
            assert.equal(status.data_mode, "scheduled_snapshot");
            assert.equal(status.quote_delivery_mode, "scheduled_snapshot");
            assert.equal(status.device_dependency, false);
            assert.equal(status.schedule_time_zone, "Asia/Shanghai");
            assert.deepEqual(status.schedule_primary_checkpoints, ["08:17", "10:17", "12:17", "15:17", "16:17", "20:17", "22:47"]);
            assert.deepEqual(status.schedule_fallback_checkpoints, ["08:47", "10:47", "12:47", "15:47", "16:47", "20:47", "23:17"]);
            assert.equal(status.snapshot_as_of, latest.generated_at);
            assert.equal(status.next_refresh, module.nextScheduledRefresh(new Date(status.time)));
            """
        )


if __name__ == "__main__":
    unittest.main()

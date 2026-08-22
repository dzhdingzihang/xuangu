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
    def test_two_weekday_checkpoints_and_45_minute_grace(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const {{ snapshotFreshness }} = await import({json.dumps(WORKER_URI)} + "?freshness-weekday");

            const updating = snapshotFreshness(
              "2026-08-21T20:18:00+08:00",
              new Date("2026-08-24T08:30:00+08:00"),
            );
            assert.equal(updating.freshness_state, "updating");
            assert.equal(updating.expected_checkpoint, "2026-08-24T08:17:00+08:00");
            assert.equal(updating.snapshot_age_minutes, 3612);
            assert.equal(updating.checkpoint_lag_minutes, 3599);

            const stale = snapshotFreshness(
              "2026-08-24T07:50:00+08:00",
              new Date("2026-08-24T09:10:00+08:00"),
            );
            assert.equal(stale.freshness_state, "stale");
            assert.equal(stale.expected_checkpoint, "2026-08-24T08:17:00+08:00");
            assert.equal(stale.snapshot_age_minutes, 80);
            assert.equal(stale.checkpoint_lag_minutes, 27);

            const fresh = snapshotFreshness(
              "2026-08-24T08:20:00+08:00",
              new Date("2026-08-24T09:20:00+08:00"),
            );
            assert.equal(fresh.freshness_state, "fresh");
            assert.equal(fresh.expected_checkpoint, "2026-08-24T08:17:00+08:00");
            assert.equal(fresh.snapshot_age_minutes, 60);
            assert.equal(fresh.checkpoint_lag_minutes, 0);

            const eveningUpdating = snapshotFreshness(
              "2026-08-24T08:20:00+08:00",
              new Date("2026-08-24T20:30:00+08:00"),
            );
            assert.equal(eveningUpdating.freshness_state, "updating");
            assert.equal(eveningUpdating.expected_checkpoint, "2026-08-24T20:17:00+08:00");
            """
        )

    def test_friday_evening_remains_expected_checkpoint_on_weekend(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const {{ snapshotFreshness }} = await import({json.dumps(WORKER_URI)} + "?freshness-weekend");

            const weekend = snapshotFreshness(
              "2026-08-21T20:18:00+08:00",
              new Date("2026-08-22T12:00:00+08:00"),
            );
            assert.equal(weekend.freshness_state, "fresh");
            assert.equal(weekend.expected_checkpoint, "2026-08-21T20:17:00+08:00");
            assert.equal(weekend.snapshot_age_minutes, 942);
            assert.equal(weekend.checkpoint_lag_minutes, 0);

            const fridayGrace = snapshotFreshness(
              "2026-08-21T08:20:00+08:00",
              new Date("2026-08-21T20:30:00+08:00"),
            );
            assert.equal(fridayGrace.freshness_state, "updating");
            assert.equal(fridayGrace.expected_checkpoint, "2026-08-21T20:17:00+08:00");

            const afterGrace = snapshotFreshness(
              "2026-08-21T08:20:00+08:00",
              new Date("2026-08-21T21:03:00+08:00"),
            );
            assert.equal(afterGrace.freshness_state, "stale");
            assert.equal(afterGrace.expected_checkpoint, "2026-08-21T20:17:00+08:00");
            """
        )

    def test_next_scheduled_refresh_includes_health_fallbacks_and_skips_weekends(self) -> None:
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
              "2026-08-24T08:17:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-22T12:00:00+08:00")),
              "2026-08-24T08:17:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-24T08:18:00+08:00")),
              "2026-08-24T08:47:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-24T08:48:00+08:00")),
              "2026-08-24T20:17:00+08:00",
            );
            assert.equal(
              nextScheduledRefresh(new Date("2026-08-24T20:18:00+08:00")),
              "2026-08-24T20:47:00+08:00",
            );
            """
        )

    def test_missing_snapshot_is_unknown_and_status_exposes_contract(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const module = await import({json.dumps(WORKER_URI)} + "?freshness-api");
            const unknown = module.snapshotFreshness(null, new Date("2026-08-24T09:20:00+08:00"));
            assert.equal(unknown.freshness_state, "unknown");
            assert.equal(unknown.expected_checkpoint, "2026-08-24T08:17:00+08:00");
            assert.equal(unknown.snapshot_age_minutes, null);
            assert.equal(unknown.checkpoint_lag_minutes, null);

            const latest = {{
              generated_at: new Date().toISOString(),
              schema_version: "selector-snapshot-v2",
              snapshot_key: "2026-08-24_2026-08-21_090000.json",
            }};
            const env = {{ ASSETS: {{ async fetch(input) {{
              const url = new URL(typeof input === "string" ? input : input.url);
              return url.pathname === "/data/picks/latest.json"
                ? new Response(JSON.stringify(latest), {{ headers: {{ "content-type": "application/json" }} }})
                : new Response("not found", {{ status: 404 }});
            }} }} }};
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
            assert.deepEqual(status.schedule_primary_checkpoints, ["08:17", "20:17"]);
            assert.deepEqual(status.schedule_fallback_checkpoints, ["08:47", "20:47"]);
            assert.equal(status.snapshot_as_of, latest.generated_at);
            assert.equal(status.next_refresh, module.nextScheduledRefresh(new Date(status.time)));
            """
        )


if __name__ == "__main__":
    unittest.main()

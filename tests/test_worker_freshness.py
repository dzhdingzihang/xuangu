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
    def test_weekday_checkpoints_and_45_minute_grace(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const {{ snapshotFreshness }} = await import({json.dumps(WORKER_URI)} + "?freshness-weekday");

            const updating = snapshotFreshness(
              "2026-08-21T23:59:00+08:00",
              new Date("2026-08-24T09:10:00+08:00"),
            );
            assert.equal(updating.freshness_state, "updating");
            assert.equal(updating.expected_checkpoint, "2026-08-24T08:58:00+08:00");
            assert.equal(updating.snapshot_age_minutes, 3431);
            assert.equal(updating.checkpoint_lag_minutes, 3419);

            const stale = snapshotFreshness(
              "2026-08-24T08:30:00+08:00",
              new Date("2026-08-24T09:50:00+08:00"),
            );
            assert.equal(stale.freshness_state, "stale");
            assert.equal(stale.expected_checkpoint, "2026-08-24T08:58:00+08:00");
            assert.equal(stale.snapshot_age_minutes, 80);
            assert.equal(stale.checkpoint_lag_minutes, 28);

            const fresh = snapshotFreshness(
              "2026-08-24T09:05:00+08:00",
              new Date("2026-08-24T09:20:00+08:00"),
            );
            assert.equal(fresh.freshness_state, "fresh");
            assert.equal(fresh.snapshot_age_minutes, 15);
            assert.equal(fresh.checkpoint_lag_minutes, 0);
            """
        )

    def test_friday_2358_remains_expected_checkpoint_on_weekend(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const {{ snapshotFreshness }} = await import({json.dumps(WORKER_URI)} + "?freshness-weekend");

            const weekend = snapshotFreshness(
              "2026-08-21T23:59:00+08:00",
              new Date("2026-08-22T12:00:00+08:00"),
            );
            assert.equal(weekend.freshness_state, "fresh");
            assert.equal(weekend.expected_checkpoint, "2026-08-21T23:58:00+08:00");
            assert.equal(weekend.snapshot_age_minutes, 721);
            assert.equal(weekend.checkpoint_lag_minutes, 0);

            const fridayGrace = snapshotFreshness(
              "2026-08-21T21:30:00+08:00",
              new Date("2026-08-21T23:59:00+08:00"),
            );
            assert.equal(fridayGrace.freshness_state, "updating");
            assert.equal(fridayGrace.expected_checkpoint, "2026-08-21T23:58:00+08:00");

            const afterGrace = snapshotFreshness(
              "2026-08-21T21:30:00+08:00",
              new Date("2026-08-22T00:44:00+08:00"),
            );
            assert.equal(afterGrace.freshness_state, "stale");
            assert.equal(afterGrace.expected_checkpoint, "2026-08-21T23:58:00+08:00");
            """
        )

    def test_missing_snapshot_is_unknown_and_status_exposes_contract(self) -> None:
        run_node(
            f"""
            import assert from "node:assert/strict";
            const module = await import({json.dumps(WORKER_URI)} + "?freshness-api");
            const unknown = module.snapshotFreshness(null, new Date("2026-08-24T09:20:00+08:00"));
            assert.equal(unknown.freshness_state, "unknown");
            assert.equal(unknown.expected_checkpoint, "2026-08-24T08:58:00+08:00");
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
            """
        )


if __name__ == "__main__":
    unittest.main()

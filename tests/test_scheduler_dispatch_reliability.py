from __future__ import annotations

import json
import pathlib
import subprocess
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER_URI = (ROOT / "src/index.js").as_uri()


class SchedulerDispatchReliabilityTests(unittest.TestCase):
    def test_transient_retry_is_bounded_and_authorization_failure_is_not_retried(self):
        script = """
        import assert from 'node:assert/strict';
        const { dispatchScheduledWorkflow } = await import(WORKER_URI);
        const controller = { cron: '17,47 0,2,4,7,8,12 * * MON-FRI',
          scheduledTime: Date.parse('2026-09-10T00:47:00Z') };
        const env = { CLOUDFLARE_SCHEDULER_ENABLED: '1', GITHUB_WORKFLOW_DISPATCH_TOKEN: 'private-value' };
        const requests = [], sleeps = [];
        const result = await dispatchScheduledWorkflow(controller, env, {
          fetcher: async (url, init) => { requests.push({url, init}); return new Response(null, {status: requests.length < 3 ? 503 : 204}); },
          sleep: async ms => sleeps.push(ms),
        });
        assert.equal(result.dispatched, true);
        assert.equal(result.attempts, 3);
        assert.deepEqual(sleeps, [1000, 2000]);
        for (const {url, init} of requests) {
          assert.equal(url, 'https://api.github.com/repos/dzhdingzihang/xuangu/actions/workflows/deploy-worker.yml/dispatches');
          assert.equal(JSON.parse(init.body).inputs.cron, '47 0 * * 1-5');
          assert.ok(init.signal);
        }
        let failures = 0;
        await assert.rejects(dispatchScheduledWorkflow(controller, env, {
          fetcher: async () => { failures++; return new Response('private response', {status: 403}); },
          sleep: async () => assert.fail('authorization errors must not retry'),
        }), error => !error.message.includes('private') && /403/.test(error.message));
        assert.equal(failures, 1);
        let networkFailures = 0;
        await assert.rejects(dispatchScheduledWorkflow(controller, env, {
          fetcher: async () => { networkFailures++; throw new Error('private network detail'); },
          sleep: async () => {},
        }), error => /3 attempts/.test(error.message) && !error.message.includes('private'));
        assert.equal(networkFailures, 3);
        """.replace("WORKER_URI", json.dumps(WORKER_URI))
        result = subprocess.run(["node", "--input-type=module", "--eval", textwrap.dedent(script)],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_configured_cloudflare_crons_cover_primary_and_watchdog_within_free_limit(self):
        config = json.loads((ROOT / "wrangler.jsonc").read_text())
        self.assertLessEqual(len(config["triggers"]["crons"]), 5)
        self.assertIn("17,47 0,2,4,7,8,12 * * MON-FRI", config["triggers"]["crons"])
        self.assertIn("17 15 * * MON-FRI", config["triggers"]["crons"])
        self.assertIn("17,47 20 * * MON-FRI", config["triggers"]["crons"])
        self.assertIn("17,47 21 * * MON-FRI", config["triggers"]["crons"])


if __name__ == "__main__":
    unittest.main()

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

    def test_configured_cloudflare_uses_one_shared_account_cron(self):
        config = json.loads((ROOT / "wrangler.jsonc").read_text())
        self.assertEqual(config["triggers"]["crons"], ["17,47 0,2,4,7,8,12,14,15,20,21 * * MON-FRI"])

    def test_single_cron_preserves_every_summer_and_winter_slot_without_extra_dispatches(self):
        script = """
        import assert from 'node:assert/strict';
        const { dispatchScheduledWorkflow, canonicalGithubCronForScheduled } = await import(WORKER_URI);
        const cron = '17,47 0,2,4,7,8,12,14,15,20,21 * * MON-FRI';
        const env = { CLOUDFLARE_SCHEDULER_ENABLED: '1', GITHUB_WORKFLOW_DISPATCH_TOKEN: 'test-token' };
        for (const [date, postCloseHour] of [['2026-09-10', 20], ['2026-12-10', 21]]) {
          const expected = [];
          for (const hour of [0, 2, 4, 7, 8, 12]) {
            for (const minute of [17, 47]) expected.push(`${minute} ${hour} * * 1-5`);
          }
          expected.push('47 14 * * 1-5', '17 15 * * 1-5',
            `17 ${postCloseHour} * * 1-5`, `47 ${postCloseHour} * * 1-5`);
          const requests = [];
          for (const hour of [0, 2, 4, 7, 8, 12, 14, 15, 20, 21]) {
            for (const minute of [17, 47]) {
              const controller = { cron, scheduledTime: Date.parse(`${date}T${String(hour).padStart(2, '0')}:${minute}:00Z`) };
              const slot = `${minute} ${hour} * * 1-5`;
              const active = expected.includes(slot);
              const before = requests.length;
              const result = await dispatchScheduledWorkflow(controller, env, {
                fetcher: async (url, init) => { requests.push(JSON.parse(init.body).inputs.cron); return new Response(null, {status: 204}); },
                sleep: async () => assert.fail('successful dispatch must not retry'),
              });
              assert.equal(result.dispatched, active, `${date} ${slot}`);
              assert.equal(requests.length - before, active ? 1 : 0, 'inactive slots must not use network');
              assert.equal(canonicalGithubCronForScheduled(controller), active ? slot : null);
              if (!active) assert.equal(result.reason, hour >= 20
                ? 'INACTIVE_US_POST_CLOSE_DST_VARIANT' : 'INACTIVE_COMBINED_CRON_SLOT');
            }
          }
          assert.deepEqual(requests, expected);
          assert.equal(requests.length, 16);
        }
        const oldAliases = [
          ['17 0,2,4,7,8,12 * * MON-FRI', '2026-09-10T00:17:00Z'],
          ['17,47 0,2,4,7,8,12 * * MON-FRI', '2026-09-10T12:47:00Z'],
          ['47 14 * * MON-FRI', '2026-09-10T14:47:00Z'],
          ['17 15 * * MON-FRI', '2026-09-10T15:17:00Z'],
          ['17,47 20 * * MON-FRI', '2026-09-10T20:47:00Z'],
          ['17,47 21 * * MON-FRI', '2026-12-10T21:47:00Z'],
          ['17 20 * * MON-FRI', '2026-09-10T20:17:00Z'],
          ['17 21 * * MON-FRI', '2026-12-10T21:17:00Z'],
        ];
        for (const [alias, time] of oldAliases) {
          const result = await dispatchScheduledWorkflow({cron: alias, scheduledTime: Date.parse(time)}, env, {
            fetcher: async () => new Response(null, {status: 204}),
          });
          assert.equal(result.dispatched, true, alias);
        }
        """.replace("WORKER_URI", json.dumps(WORKER_URI))
        result = subprocess.run(["node", "--input-type=module", "--eval", textwrap.dedent(script)],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

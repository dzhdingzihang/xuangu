import unittest

from scripts import configure_scheduler


class ConfigureSchedulerTests(unittest.TestCase):
    def test_missing_secret_is_an_explicit_optional_gap(self):
        def forbidden(*args, **kwargs):
            self.fail("missing secret must not mutate Cloudflare")
        result = configure_scheduler.configure({}, runner=forbidden)
        self.assertFalse(result["configured"])
        self.assertEqual(result["reason"], "REPOSITORY_SCOPED_SECRET_NOT_CONFIGURED")

    def test_broad_local_oauth_and_classic_tokens_are_rejected(self):
        for value in ("gho_example", "ghp_example", "not-a-token"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "fine-grained"):
                configure_scheduler.configure({"XUANGU_WORKFLOW_DISPATCH_TOKEN": value})

    def test_token_is_stdin_only_and_provider_errors_are_redacted(self):
        calls = []
        secret = "github_pat_example_scoped_to_repository"
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return type("Result", (), {"returncode": 0, "stdout": secret, "stderr": secret})()
        result = configure_scheduler.configure({"XUANGU_WORKFLOW_DISPATCH_TOKEN": secret,
                                               "CLOUDFLARE_API_TOKEN": "test-cloud-token"}, runner=runner)
        self.assertTrue(result["configured"])
        self.assertNotIn(secret, str(result))
        command, kwargs = calls[0]
        self.assertNotIn(secret, command)
        self.assertEqual(kwargs["input"], secret + "\n")
        self.assertNotIn("XUANGU_WORKFLOW_DISPATCH_TOKEN", kwargs["env"])
        self.assertEqual(kwargs["timeout"], 60)
        def failing(*args, **kwargs):
            return type("Result", (), {"returncode": 1, "stdout": secret, "stderr": secret})()
        with self.assertRaises(RuntimeError) as error:
            configure_scheduler.configure({"XUANGU_WORKFLOW_DISPATCH_TOKEN": secret}, runner=failing)
        self.assertNotIn(secret, str(error.exception))


if __name__ == "__main__":
    unittest.main()

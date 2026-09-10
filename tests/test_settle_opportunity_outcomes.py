from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import opportunity_outcome_ledger as ledger
from scripts import settle_opportunity_outcomes as cli
from tests.test_opportunity_outcome_ledger import snapshot, pending, loader, PUBLICATION, MATURE


class SettleOpportunityOutcomesTests(unittest.TestCase):
    def test_no_implicit_historical_registration_then_survives_snapshot_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks, outcomes = root / "picks", root / "outcomes"
            picks.mkdir()
            source = picks / "latest.json"
            source.write_text(json.dumps(snapshot()))
            calls = []
            def fetch(market, code):
                calls.append((market, code))
                return loader(market, code)
            empty = cli.run(picks, outcomes, as_of=PUBLICATION, price_loader=fetch)
            self.assertEqual(empty["prediction_count"], 0)
            registration = cli.run(picks, outcomes, as_of=PUBLICATION, register_snapshot=source, published_at=PUBLICATION, price_loader=fetch)
            self.assertEqual(registration["pending_maturity_count"], 2)
            self.assertEqual(calls, [])
            repeat = cli.run(picks, outcomes, as_of="2026-08-22T00:00:00Z", register_snapshot=source, published_at="2026-08-22T00:00:00Z", price_loader=fetch)
            self.assertEqual(repeat["changed_snapshot_count"], 0)
            source.unlink()
            settled = cli.run(picks, outcomes, as_of=MATURE, price_loader=fetch, max_workers=99)
            self.assertEqual(settled["settled_count"], 2)
            self.assertEqual(sorted(calls), [("us", "AAA"), ("us", "BBB"), ("us", "SPY")])
            self.assertEqual(settled["worker_limit"], cli.MAX_WORKERS)
            calls.clear()
            replay = cli.run(picks, outcomes, as_of="2026-09-11T00:00:00Z", price_loader=fetch)
            self.assertEqual(replay["changed_snapshot_count"], 0)
            self.assertEqual(calls, [])

    def test_requires_registration_pair_and_retries_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with self.assertRaises(ValueError):
                cli.run(outcomes_dir=root, register_snapshot=root / "missing.json")
            with self.assertRaisesRegex(ValueError, "register-only requires"):
                cli.run(outcomes_dir=root, register_only=True)

    def test_register_only_persists_new_publication_without_fetching_old_mature_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            outcomes = root / "outcomes"
            old = pending()
            ledger.write_opportunity_outcome_batch(outcomes, old)
            new = snapshot("2026-09-10_2026-09-10_080000.json")
            source = root / "published.json"
            source.write_text(json.dumps(new))
            def forbidden_fetch(*args):
                self.fail("register-only must never fetch historical prices")
            result = cli.run(outcomes_dir=outcomes, as_of=MATURE,
                register_snapshot=source, published_at=MATURE, register_only=True,
                price_loader=forbidden_fetch)
            self.assertEqual(result["fetched_symbol_count"], 0)
            self.assertEqual(result["changed_snapshot_count"], 1)
            saved = ledger.load_opportunity_outcome_batches(outcomes)
            self.assertEqual(saved[old["snapshot_key"]], old)
            self.assertEqual(saved[new["snapshot_key"]]["status_counts"], {"PENDING_MATURITY": 2})
            first_publication = saved[new["snapshot_key"]]["published_at"]
            repeat = cli.run(outcomes_dir=outcomes, as_of="2026-09-11T00:00:00Z",
                register_snapshot=source, published_at="2026-09-11T00:00:00Z", register_only=True,
                price_loader=forbidden_fetch)
            self.assertEqual(repeat["changed_snapshot_count"], 0)
            self.assertEqual(ledger.load_opportunity_outcome_batches(outcomes)[new["snapshot_key"]]["published_at"], first_publication)


if __name__ == "__main__":
    unittest.main()

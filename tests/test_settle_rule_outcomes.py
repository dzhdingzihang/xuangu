from __future__ import annotations

import datetime as dt
import json
import pathlib
import tempfile
import unittest

import rule_outcome_ledger
from scripts import settle_rule_outcomes
from tests.test_rule_outcome_ledger import price_loader, rule_snapshot


class SettleRuleOutcomeScriptTests(unittest.TestCase):
    def test_run_deduplicates_latest_alias_and_persists_one_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            picks.mkdir()
            snapshot = rule_snapshot()
            rendered = json.dumps(snapshot)
            (picks / snapshot["snapshot_key"]).write_text(rendered, encoding="utf-8")
            (picks / "latest.json").write_text(rendered, encoding="utf-8")

            summary = settle_rule_outcomes.run(
                picks,
                outcomes,
                as_of=dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc),
                price_loader=price_loader,
            )

            self.assertEqual(summary["snapshot_count"], 1)
            self.assertEqual(summary["prediction_count"], 2)
            self.assertEqual(summary["settled_count"], 2)
            self.assertEqual(len(rule_outcome_ledger.load_rule_outcome_batches(outcomes)), 1)

    def test_current_v4_is_settled_without_relabelling_frozen_rule_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            picks = root / "picks"
            outcomes = root / "outcomes"
            picks.mkdir()
            snapshot = rule_snapshot()
            snapshot["snapshot_key"] = "2026-08-22_2026-08-21_224801.json"
            decision = snapshot["production_decision"]
            decision["action_basis"] = "dual_track_candidate_qualification_v4"
            decision["rule_model_id"] = "ten-day-audited-rule-ensemble-v4"
            for candidate in decision["qualified_candidates"]:
                candidate["rule_model_id"] = decision["rule_model_id"]
            decision["primary"]["rule_model_id"] = decision["rule_model_id"]
            (picks / snapshot["snapshot_key"]).write_text(
                json.dumps(snapshot),
                encoding="utf-8",
            )

            summary = settle_rule_outcomes.run(
                picks,
                outcomes,
                as_of=dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc),
                price_loader=price_loader,
            )

            self.assertEqual(summary["snapshot_count"], 1)
            batch = next(iter(rule_outcome_ledger.load_rule_outcome_batches(outcomes).values()))
            self.assertEqual(
                {row["rule_model_id"] for row in batch["predictions"]},
                {"ten-day-audited-rule-ensemble-v4"},
            )


if __name__ == "__main__":
    unittest.main()

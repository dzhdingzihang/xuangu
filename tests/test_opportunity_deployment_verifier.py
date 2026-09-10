import copy
import unittest

from opportunity_outcome_ledger import evaluate_opportunity_performance
from scripts.verify_deployment import opportunity_history_contract_errors


class OpportunityDeploymentVerifierTests(unittest.TestCase):
    def test_exact_separate_history_contract_required_in_all_locations(self):
        summary = evaluate_opportunity_performance({})
        payload = {"opportunity_outcome_tracking": copy.deepcopy(summary),
                   "meta": {"opportunity_outcome_tracking": copy.deepcopy(summary)},
                   "history_evaluation": {"opportunity_outcome_tracking": copy.deepcopy(summary)}}
        self.assertEqual(opportunity_history_contract_errors(summary, payload), [])
        for location in ("root", "meta", "history_evaluation"):
            changed = copy.deepcopy(payload)
            container = changed if location == "root" else changed[location]
            container["opportunity_outcome_tracking"]["prediction_count"] = 12
            with self.subTest(location=location):
                self.assertTrue(opportunity_history_contract_errors(summary, changed))
        self.assertTrue(opportunity_history_contract_errors(summary, {}))

    def test_invalid_or_promoted_local_ledger_cannot_pass(self):
        summary = evaluate_opportunity_performance({})
        self.assertTrue(opportunity_history_contract_errors(None, {}))
        self.assertTrue(opportunity_history_contract_errors({**summary, "authorizes_production": True}, {}))


if __name__ == "__main__":
    unittest.main()

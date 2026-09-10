import pathlib
import unittest

from tests.test_frontend_contract import run_app_node

ROOT = pathlib.Path(__file__).resolve().parents[1]


class OnlineHardeningUiTests(unittest.TestCase):
    def test_event_coverage_never_implies_negative_clearance(self):
        run_app_node("""
          assert.match(opportunityEventCoverage({}).label, /尚未扫描/);
          assert.match(opportunityEventCoverage({event_coverage:{status:'SUCCESS',verified:false}}).label, /尚未扫描/);
          assert.match(opportunityEventCoverage({event_coverage:{status:'ERROR'}}).label, /失败/);
          const scanned = opportunityEventCoverage({event_coverage:{status:'SUCCESS',verified:true}});
          assert.match(scanned.detail, /不等于已排除/);
          const html = renderOpportunityEvidence({sector:{name:'<script>',source:'provider'},event_coverage:{status:'ERROR'}}, true);
          assert.ok(!html.includes('<script>'));
          assert.ok(html.includes('&lt;script&gt;'));
          for (const [status, label] of Object.entries({STALE:'分类已过期',APPROXIMATE:'主题近似',UNVERIFIED:'分类未核验'})) {
            assert.ok(renderOpportunityEvidence({sector:{name:'Technology',status}}).includes(label));
          }
        """)

    def test_opportunity_history_is_separate_and_never_turns_pending_into_zero_return(self):
        run_app_node("""
          assert.match(renderOpportunityOutcomeHistory(null), /等待登记/);
          const model = {schema_version:'opportunity-performance-v1',track:'RETURN_OPPORTUNITY',authorizes_production:false,calibrated:false,status:'COLLECTING',
            prediction_count:1,settled_count:0,pending_maturity_count:1,pending_data_count:0,
            independent_entry_date_count:1,first_maturity_date:'2026-09-23',
            by_version:[],recent_outcomes:[{name:'Example',code:'TEST',market:'us',rank:2,
              opportunity_score:80,entry_trade_date:'2026-09-10',forecast_end_trade_date:'2026-09-23',
              status:'PENDING_MATURITY',net_total_return:0,net_excess_return:0}]};
          const html = renderOpportunityOutcomeHistory(model);
          assert.match(html, /独立研究轨/);
          assert.match(html, /未到期/);
          assert.ok(!html.includes('0.00%'));
          assert.match(html, /不是独立交易样本/);
          assert.match(html, /不是账户实盘收益/);
          assert.match(renderOpportunityOutcomeHistory({...model,authorizes_production:true}), /等待登记/);
        """)

    def test_cloud_workflow_freezes_after_verification_and_archives_without_full_snapshot(self):
        source = (ROOT / ".github/workflows/deploy-worker.yml").read_text()
        self.assertLess(source.index("- name: Verify complete deployed contract"),
                        source.index("- name: Freeze verified published opportunity shortlist"))
        self.assertIn("--register-snapshot public/data/picks/latest.json", source)
        self.assertIn("--published-at", source)
        self.assertIn("has_opportunity_receipt", source)
        archive = source[source.index("  opportunity-ledger:"):source.index("  checkpoint-ledger:")]
        self.assertNotIn("should_archive", archive)
        self.assertIn("always() && needs.deploy.outputs.has_opportunity_receipt == 'true'", archive)
        self.assertIn("data/outcomes/opportunity-settlements", archive)
        self.assertIn("scripts/merge_archive_payload.py", archive)
        self.assertIn("XUANGU_WORKFLOW_DISPATCH_TOKEN", source)


if __name__ == "__main__":
    unittest.main()

import unittest

from tests.test_frontend_contract import run_app_node


class OpportunityRankComparisonUiTests(unittest.TestCase):
    def test_pending_groups_do_not_render_zero_returns(self):
        run_app_node("""
          const group = {cohort_count:2,complete_cohort_count:0,pending_cohort_count:2,
            non_overlapping_cohort_count:0,mean_net_return:0,mean_net_excess_return:0,worst_cohort_net_return:0};
          const summary = {by_version:[{score_version:'return-opportunity-score-v3',ranking_evaluation:{
            contract_version:'opportunity-ranking-performance-v1',calibrated:false,authorizes_production:false,
            groups:{top1:group,top3:group,board:group}}}]};
          const html = renderOpportunityRankComparison(summary);
          assert.match(html,/首位/); assert.match(html,/前三/); assert.match(html,/整榜/);
          assert.match(html,/十日扣费净收益/);
          assert.match(html,/非重叠窗口/);
          assert.match(html,/等待到期/);
          assert.ok(!html.includes('0.00%'));
          assert.match(html,/不是实盘组合/);
        """)

    def test_versions_are_not_pooled_and_incomplete_metrics_hidden(self):
        run_app_node("""
          const metric = (net) => ({status:'EARLY_SAMPLE',cohort_count:2,complete_cohort_count:1,
            pending_cohort_count:1,non_overlapping_cohort_count:1,mean_net_return:net,
            mean_net_excess_return:-.01,worst_cohort_net_return:net});
          const version = (name,net) => ({score_version:name,ranking_evaluation:{
            contract_version:'opportunity-ranking-performance-v1',calibrated:false,authorizes_production:false,
            groups:{top1:metric(net),top3:metric(net),board:metric(net)}}});
          const html = renderOpportunityRankComparison({by_version:[version('v3',.03),version('v2',-.02)]});
          assert.match(html,/v3/); assert.match(html,/v2/);
          assert.match(html,/3.00%/); assert.match(html,/-2.00%/);
          assert.match(html,/样本少/);
          assert.match(renderOpportunityRankComparison({by_version:[],ranking_evaluation_preview:true}),/加载/);
          assert.equal(renderOpportunityRankComparison({by_version:[{...version('unsafe',.99),ranking_evaluation:{authorizes_production:true}}]}),'');
        """)


if __name__ == "__main__":
    unittest.main()

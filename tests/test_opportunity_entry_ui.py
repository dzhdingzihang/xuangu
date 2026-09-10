import unittest

from tests.test_frontend_contract import run_app_node


class OpportunityEntryUiTests(unittest.TestCase):
    def test_compact_primary_and_sector_round_trip_without_mutation(self):
        run_app_node("""
          const row = {market:'us',code:'AAA',rank:1,opportunity_score:75,sector:{name:'Technology',source_url:'https://example.test/AAA'}};
          const source = {primary_projection:'rank-one-identity-v1',primary:{market:'us',code:'AAA',rank:1,opportunity_score:75},
            candidates:[row],sector_policy:{source:'provider',status:'KNOWN',verified:true}};
          const copy = JSON.stringify(source);
          const expanded = expandOpportunityProjection(source);
          assert.deepEqual(expanded.primary, expanded.candidates[0]);
          assert.equal(expanded.primary.sector.source,'provider');
          assert.equal(expanded.primary.sector.source_url,'https://example.test/AAA');
          assert.equal(JSON.stringify(source),copy);
          const invalid = expandOpportunityProjection({...source,primary:{...source.primary,code:'OTHER'}});
          assert.notDeepEqual(invalid.primary,invalid.candidates[0]);
          assert.match(renderOpportunityEvidence({score_version:'return-opportunity-score-v3'}),/证券类别待核验/);
          assert.match(renderOpportunityEvidence({score_version:'return-opportunity-score-v3',security_classification:{
            contract_version:'security-identity-v1',status:'PROVIDER_CLASSIFIED',eligible:true,verified:true}}),/供应商确认权益证券/);
        """)

    def test_entry_review_is_not_an_execution_signal(self):
        run_app_node("""
          assert.match(opportunityEntryView({}).label, /未评估/);
          const row = {score_version:'return-opportunity-score-v3',evidence_score:86.7,opportunity_score:62.7,
            metrics:{return_5d_pct:31.163,return_10d_pct:41.235,distance_ma20_pct:32.998},
            entry_assessment:{contract_version:'return-opportunity-entry-v1',status:'WAIT_FOR_PULLBACK',
              chase_risk:'HIGH',penalty_points:24,reason_codes:['TEN_DAY_RETURN_EXTENDED'],execution_ready:false}};
          const view = opportunityEntryView(row);
          assert.equal(view.valid, true);
          assert.match(view.label, /观察回调/);
          const html = renderOpportunityEntry(row, true);
          assert.match(html, /86.7/);
          assert.match(html, /透支 24/);
          assert.match(html, /41.2%/);
          assert.match(html, /过去/);
          assert.match(html, /不代表当前可买/);
          assert.equal(opportunityEntryView({...row,entry_assessment:{...row.entry_assessment,execution_ready:true}}).valid,false);
          assert.equal(opportunityEntryView({...row,opportunity_score:90}).valid,false);
          assert.equal(opportunityEntryView({...row,evidence_score:NaN}).valid,false);
          assert.equal(opportunityEntryView({...row,entry_assessment:{...row.entry_assessment,status:'BUY_NOW'}}).valid,false);
        """)

    def test_moderate_entry_still_requires_next_session_recheck(self):
        run_app_node("""
          const row = {score_version:'return-opportunity-score-v3',evidence_score:75,opportunity_score:75,
            metrics:{return_5d_pct:5,return_10d_pct:8,distance_ma20_pct:4},
            entry_assessment:{contract_version:'return-opportunity-entry-v1',status:'CONDITIONAL_REVIEW',
              chase_risk:'NORMAL',penalty_points:0,reason_codes:[],execution_ready:false}};
          assert.match(opportunityEntryView(row).label, /待开盘复核/);
          assert.match(renderOpportunityEntry(row), /不是买入指令/);
          const policy = renderOpportunityEntryPolicy({entry_policy:{contract_version:'return-opportunity-entry-v1',
            timing:'NEXT_SESSION_OPEN_REVIEW',automatic_execution:false,execution_ready:false}});
          assert.match(policy, /下一可交易开盘/);
          assert.match(policy, /快照价不是成交价/);
          assert.match(policy, /重大消息/);
          assert.equal(renderOpportunityEntryPolicy({entry_policy:{timing:'BUY_NOW'}}),'');
        """)


if __name__ == "__main__":
    unittest.main()

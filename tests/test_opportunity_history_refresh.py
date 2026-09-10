import unittest

from tests.test_frontend_contract import run_app_node


class OpportunityHistoryRefreshTests(unittest.TestCase):
    def test_same_snapshot_history_publication_invalidates_only_history_then_loads_full_summary(self):
        run_app_node(r"""
void (async () => {
  const identity = {
    snapshot_key: '2026-09-10_fixture.json', generated_at: '2026-09-10T00:00:00Z',
    source_snapshot: {sha256: 'a'.repeat(64), byte_size: 1000},
  };
  const before = {schema_version:'opportunity-performance-v1', track:'RETURN_OPPORTUNITY',
    authorizes_production:false, calibrated:false, status:'COLLECTING',
    prediction_count:0, settled_count:0, by_version:[], recent_outcomes:[]};
  const snapshot = {...identity, contract_version:'ui-bootstrap-v1', opportunity_outcome_tracking:before};
  const use = {contract_version:'snapshot-use-v1', snapshot_key:identity.snapshot_key,
    source_snapshot_sha256:identity.source_snapshot.sha256, source_snapshot_byte_size:1000,
    evaluated_at:'2026-09-10T01:00:00Z'};
  const status = {snapshot_key:identity.snapshot_key, generated_at:identity.generated_at,
    source_snapshot_sha256:identity.source_snapshot.sha256, source_snapshot_byte_size:1000,
    snapshot_use:use};
  state.snapshot = snapshot;
  state.status = status;
  state.tab = 'history';
  const ready = (resource, id) => ({status:'ready', snapshotKey:identity.snapshot_key,
    queryKey:resourceQueryKey(resource), requestId:id, error:''});
  const candidates = [{market:'us',code:'AAA',name:'AAA'}];
  const candidateState = ready('candidates', 7);
  const eventState = ready('events', 8);
  state.candidates = candidates;
  state.tabData.candidates = candidateState;
  state.tabData.events = eventState;
  state.tabData.history = ready('history', 9);
  const unchanged = {contract_version:'ui-bootstrap-v1', latest:snapshot, status};
  assert.equal(await applyBootstrapPayload(unchanged), false);
  assert.equal(state.tabData.history.status, 'ready');

  const row = {name:'Example', code:'AAA', market:'us', rank:1, opportunity_score:80,
    entry_trade_date:'2026-09-10', forecast_end_trade_date:'2026-09-23', status:'PENDING_MATURITY'};
  const versions = ['return-opportunity-score-v1', 'return-opportunity-score-v2'].map((version, index) => ({
    score_version:version, score_version_id:`oppscore_${index}`, prediction_count:6, settled_count:0,
    independent_entry_date_count:1, mean_net_return:null, mean_excess_return:null, win_rate:null,
  }));
  const compact = {...before, prediction_count:12, pending_maturity_count:12,
    pending_data_count:0, independent_entry_date_count:1, by_version:versions,
    recent_outcomes:[row,row,row]};
  const next = {contract_version:'ui-bootstrap-v1', latest:{...snapshot, opportunity_outcome_tracking:compact}, status};
  assert.equal(await applyBootstrapPayload(next), false, 'history updates do not invent a new decision snapshot');
  assert.equal(state.tabData.history.status, 'idle');
  assert.equal(tabRequestStillCurrent('history',9,identity.snapshot_key,'history:daily'),false);
  assert.equal(state.candidates, candidates);
  assert.equal(state.tabData.candidates, candidateState);
  assert.equal(state.tabData.events, eventState);

  const full = {...compact, recent_outcomes:Array.from({length:12}, (_, index) => ({...row,rank:index+1}))};
  let fetches = 0;
  getHistoryPayload = async () => {
    fetches += 1;
    return {contract_version:'history-list-v1', ...identity, history:[],
      page:1,limit:5,total:0,has_more:false,meta:{opportunity_outcome_tracking:before},
      opportunity_outcome_tracking:full};
  };
  await loadTabResource('history');
  assert.equal(fetches, 1);
  assert.equal(state.tabData.history.status, 'ready');
  assert.equal(state.historyMeta.opportunity_outcome_tracking.recent_outcomes.length, 12);
  const html = renderOpportunityOutcomeHistory(state.historyMeta.opportunity_outcome_tracking);
  assert.match(html, /return-opportunity-score-v1/);
  assert.match(html, /return-opportunity-score-v2/);
  assert.match(html, /最近登记的 12 条记录/);
  assert.ok(!html.includes('0.00%'));

  assert.equal(await applyBootstrapPayload(next), false);
  assert.equal(state.tabData.history.status, 'ready');
  assert.equal(state.historyMeta.opportunity_outcome_tracking.recent_outcomes.length, 12,
    'identical compact bootstrap must not overwrite the expanded history');
})();
        """)


if __name__ == '__main__':
    unittest.main()

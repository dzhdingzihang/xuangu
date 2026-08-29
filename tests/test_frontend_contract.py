from __future__ import annotations

import json
import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def run_app_node(body: str) -> None:
    app_path = ROOT / "static" / "app.js"
    harness = f"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
let source = fs.readFileSync({json.dumps(str(app_path))}, "utf8")
  .replace(/\\ninitialize\\(\\);\\s*$/, "");
const roots = new Map([
  ["#eventsView", {{ innerHTML: "" }}],
  ["#eventType", {{ value: "" }}],
  ["#eventDirection", {{ value: "" }}],
]);
const sandbox = {{
  assert,
  __roots: roots,
  console,
  document: {{
    querySelector: (selector) => roots.get(selector) || null,
    querySelectorAll: () => [],
  }},
  window: {{
    addEventListener: () => {{}},
    devicePixelRatio: 1,
    matchMedia: () => ({{ matches: false }}),
    setInterval: () => 0,
    setTimeout,
    clearTimeout,
  }},
  location: {{ hash: "", origin: "https://xuangu.test" }},
  URL,
  AbortController,
  AbortSignal,
  DOMException,
  setTimeout,
  clearTimeout,
}};
vm.createContext(sandbox);
source += "\\n" + {json.dumps(body)};
vm.runInContext(source, sandbox, {{ filename: "static/app.js" }});
"""
    completed = subprocess.run(
        ["node"],
        input=harness,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"node frontend behavior check failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

    def test_six_accessible_tabs_are_present(self) -> None:
        for tab in ("decision", "candidates", "events", "history", "model", "health"):
            self.assertIn(f'id="tab-{tab}"', self.html)
            self.assertIn(f'id="panel-{tab}"', self.html)
            self.assertIn(f'data-tab="{tab}"', self.html)
        self.assertEqual(self.html.count('role="tabpanel"'), 6)

    def test_frontend_exposes_one_user_decision_and_a_server_trade_plan(self) -> None:
        self.assertRegex(self.js, r"function userDecisionState\(")
        for state_name in ("ENTER_TRADE_REVIEW", "RESEARCH_ONLY", "NO_ACTION"):
            self.assertIn(state_name, self.js)
        self.assertIn('data-user-decision-state="${esc(decisionState)}"', self.js)
        self.assertIn("唯一用户结论", self.js)
        self.assertIn("进入交易复核", self.js)
        self.assertIn("仅继续研究", self.js)
        self.assertIn("今日不行动", self.js)
        self.assertIn('published.contract_version === "ten-day-trade-plan-v2"', self.js)
        self.assertIn('published.contract_version !== "ten-day-trade-plan-v1"', self.js)
        self.assertIn("历史波动情景、", self.js)
        self.assertIn("未校准", self.js)
        self.assertIn("个观测", self.js)
        self.assertIn("validateTenDayTradePlan", self.js)
        self.assertIn("TRADE_PLAN_EXIT_RULE_LABELS", self.js)
        for field in (
            "reference_quote?.price",
            "reference_quote?.source_as_of",
            "entry_zone",
            "invalidation.price",
            "target.price",
            "max_single_name_weight_pct",
            "catalyst_expiry_date",
            "review_end_trade_date",
            "is_personalized_advice",
        ):
            self.assertIn(field, self.js)
        self.assertIn("规则资格分不是上涨概率，也不是收益保证", self.js)
        self.assertIn("advanced-decision-details", self.js + self.css)
        self.assertNotIn("<details class=\"advanced-decision-details\" open", self.js)

    def test_trade_plan_contract_is_semantically_validated_without_browser_inference(self) -> None:
        run_app_node(
            r"""
const primary = {
  market: "us",
  qualification_track: "quality_technical",
  estimated_10d_range: { low_pct: -4, high_pct: 8 },
  risk_reward: { ratio: 2 },
};
const plan = {
  contract_version: "ten-day-trade-plan-v1",
  status: "REVIEW_REQUIRED",
  horizon_trade_days: 10,
  reference_quote: {
    price: 100, currency: "USD", source: "published_quote",
    source_as_of: "2026-08-28T16:00:00-04:00", quote_status: "LAST_CLOSE",
    kind: "published_snapshot_quote",
  },
  entry_zone: { low: 99, high: 100.5, currency: "USD" },
  entry_trade_date: "2026-08-31",
  invalidation: { price: 94, currency: "USD", source: "candidate_stop_loss" },
  target: { price: 108, currency: "USD", source: "ten_day_scenario_upper_bound" },
  position_limit: { max_single_name_weight_pct: 10, policy: "strategy_safety_cap_not_personalized" },
  catalyst_expiry_date: null,
  review_end_trade_date: "2026-09-11",
  exit_rules: [
    "EXIT_IF_INVALIDATION_PRICE_BREACHED",
    "REVIEW_AT_TENTH_SESSION_CLOSE",
    "DO_NOT_CHASE_ABOVE_ENTRY_ZONE",
  ],
  is_personalized_advice: false,
};
assert.equal(validateTenDayTradePlan(plan, primary).valid, true);
const view = tenSessionTradePlan({}, { ...primary, ten_day_trade_plan: plan });
assert.equal(view.currency, "USD");
assert.equal(view.quoteStatus, "LAST_CLOSE");
assert.equal(view.invalidationSource, "candidate_stop_loss");
assert.equal(view.targetSource, "ten_day_scenario_upper_bound");
assert.deepEqual(view.exitRules, plan.exit_rules);
for (const mutate of [
  (copy) => { copy.reference_quote.currency = "HKD"; },
  (copy) => { copy.reference_quote.quote_status = ""; },
  (copy) => { copy.invalidation.source = ""; },
  (copy) => { copy.exit_rules.reverse(); },
  (copy) => { copy.position_limit.max_single_name_weight_pct = 100; },
  (copy) => { copy.entry_trade_date = "2026-02-30"; },
]) {
  const copy = JSON.parse(JSON.stringify(plan));
  mutate(copy);
  assert.equal(validateTenDayTradePlan(copy, primary).valid, false);
}
const eventPlan = JSON.parse(JSON.stringify(plan));
eventPlan.catalyst_expiry_date = eventPlan.review_end_trade_date;
assert.equal(validateTenDayTradePlan(eventPlan, { ...primary, qualification_track: "event_catalyst" }).valid, true);
const range = {
  contract_version: "horizon-range-v1", low_pct: -4, high_pct: 8,
  text: "-4.0% ~ +8.0%", horizon_trade_days: 10,
  method_id: "realized-vol-drift-shadow-v1", calibrated: false,
  source_observations: 20,
  source_window_start_date: "2026-07-31", source_window_end_date: "2026-08-28",
};
const v2Primary = { ...primary, estimated_10d_range: range };
const v2Plan = { ...plan, contract_version: "ten-day-trade-plan-v2", scenario_range: range };
assert.equal(validateTenDayTradePlan(v2Plan, v2Primary, { estimated_10d_range: range }).valid, true);
const v2View = tenSessionTradePlan({ estimated_10d_range: range }, { ...v2Primary, ten_day_trade_plan: v2Plan });
assert.equal(v2View.rangeProvenanceAvailable, true);
assert.equal(v2View.rangeCalibrated, false);
assert.equal(v2View.rangeObservationCount, 20);
for (const mutate of [
  (copy) => { copy.scenario_range.method_id = "invented"; },
  (copy) => { copy.scenario_range.calibrated = true; },
  (copy) => { copy.scenario_range.source_observations = 21; },
  (copy) => { copy.scenario_range.text = "-4% ~ +8%"; },
  (copy) => { copy.scenario_range.high_pct = 9; },
]) {
  const copy = JSON.parse(JSON.stringify(v2Plan));
  mutate(copy);
  assert.equal(validateTenDayTradePlan(copy, v2Primary, { estimated_10d_range: range }).valid, false);
}
"""
        )

    def test_shortlist_distinguishes_recall_from_rule_evaluation_and_projects_event_evidence(self) -> None:
        self.assertIn("const recalled = num(state.candidatePayload?.scanned_count", self.js)
        self.assertIn("const evaluated = num(state.candidatePayload?.evaluated_count", self.js)
        self.assertIn("召回 ${fmt(recalled, 0)} · 规则评估 ${fmt(evaluated, 0)}", self.js)
        run_app_node(
            r"""
assert.equal(candidateEventGrade({
  qualification: {
    status: "QUALIFIED",
    qualification_track: "event_catalyst",
    event_candidate_scanned: true,
    verified_positive_event_ids: ["event-1"],
  },
}), "正向证据已核验");
assert.equal(candidateEventGrade({
  qualification: {
    status: "QUALIFIED",
    qualification_track: "quality_technical",
    event_candidate_scanned: false,
    verified_positive_event_ids: [],
  },
}), "结构化风险筛查 PASS");
assert.equal(candidateEventGrade({ event_candidate_scanned: true }), "事件已扫描");
assert.equal(candidateEventGrade({}), "覆盖待确认");
"""
        )

    def test_paged_api_filters_identity_and_abort_timeout_fallback_fail_closed(self) -> None:
        run_app_node(
            r"""
state.snapshot = {
  contract_version: "ui-bootstrap-v1",
  snapshot_key: "2026-08-29_fixture.json",
  generated_at: "2026-08-29T10:17:00+08:00",
  source_snapshot: { sha256: "a".repeat(64), byte_size: 1234 },
};
state.candidateFilters = { market: "us", risk: "all", route: "all", query: "Apple" };
const candidateUrl = resourceListUrl("candidates", 1);
assert.match(candidateUrl, /market=us/);
assert.match(candidateUrl, /q=apple/);
state.eventFilters = { market: "hk", type: "results", direction: "positive", query: "Tencent" };
const eventUrl = resourceListUrl("events", 2);
assert.match(eventUrl, /market=hk/);
assert.match(eventUrl, /event_type=results/);
assert.match(eventUrl, /direction=positive/);
assert.match(eventUrl, /q=tencent/);
assert.match(eventUrl, /page=2/);
const eventPayload = {
  contract_version: "event-list-v2",
  snapshot_key: state.snapshot.snapshot_key,
  generated_at: state.snapshot.generated_at,
  source_snapshot: { ...state.snapshot.source_snapshot },
  ordering_contract_version: "decision-bound-first-then-published-desc-v1",
  event_publication: {
    total: 1, published: 1, truncated: 0, is_truncated: false,
    ordering_contract_version: "decision-bound-first-then-published-desc-v1",
    decision_bound_event_ids: ["evt-1"], production_bound_event_ids: ["evt-1"],
    decision_bound_event_count: 1, decision_bound_record_count: 1,
  },
  decision_bound: { total: 1, matched: 1, returned: 1, all_matched_returned: true, ids: ["evt-1"] },
  page: 1, limit: 25, total: 1, has_more: false,
  events: [{ event_id: "evt-1", market: "hk", decision_bound: true }],
};
validateResourcePayload("events", eventPayload, { queryKey: resourceQueryKey("events") });
assert.throws(() => validateResourcePayload("events", {
  ...eventPayload,
  event_publication: { ...eventPayload.event_publication, decision_bound_event_count: 2 },
}, { queryKey: resourceQueryKey("events") }));
const payload = {
  contract_version: "candidate-list-v1",
  snapshot_key: state.snapshot.snapshot_key,
  generated_at: state.snapshot.generated_at,
  source_snapshot: { ...state.snapshot.source_snapshot },
  scanned_count: 800,
  page: 1, limit: 25, total: 1, has_more: false,
  candidates: [{ id: "cand_0123456789abcdef0123", market: "us", code: "AAPL", name: "Apple" }],
};
validateResourcePayload("candidates", payload, { queryKey: resourceQueryKey("candidates") });
assert.equal(payload.scanned_count, 800);
const roleSelection = {
  role_contract_version: "candidate-role-v1", action: "NO_QUALIFIED_PICK",
  primary_candidate_id: null, qualified_candidate_ids: [], qualified_candidate_count: 0,
};
const v2Payload = {
  ...payload,
  contract_version: "candidate-list-v2",
  role_contract_version: "candidate-role-v1",
  production_selection: roleSelection,
  candidates: payload.candidates.map((row) => ({
    ...row,
    role_contract_version: "candidate-role-v1",
    decision_roles: { production: "NONE", legacy: "PRIMARY", research: "NONE" },
    decision_role: "legacy_market_primary",
  })),
};
validateResourcePayload("candidates", v2Payload, { queryKey: resourceQueryKey("candidates") });
assert.throws(() => validateResourcePayload("candidates", {
  ...v2Payload,
  candidates: v2Payload.candidates.map((row) => ({
    ...row,
    decision_roles: { ...row.decision_roles, production: "PRIMARY" },
    decision_role: "production_primary",
    production_rank: 1,
  })),
}));
assert.throws(() => validateResourcePayload("candidates", {
  ...payload, source_snapshot: { ...payload.source_snapshot, byte_size: 1235 },
}));
const qualified = {
  status: "QUALIFIED", market: "us", code: "AAPL", name: "Apple",
  qualification_id: "qual_0123456789abcdef01234567", qualification_score: 80,
  rule_model_id: "ten-day-audited-rule-ensemble-v4", score_kind: "RULE_QUALIFICATION_SCORE",
  probability: null, calibrated: false,
  candidate_snapshot: { market: "us", code: "AAPL", name: "Apple" },
};
state.snapshot = {
  ...state.snapshot,
  contract_version: "ui-bootstrap-v1",
  model_version: CURRENT_PRODUCTION_MODEL_VERSION,
  production_decision: {
    contract_version: "production-rule-10d-v1", decision_scope: "global_10d_bounded_recall",
    action_basis: "dual_track_candidate_qualification_v4", action: "QUALIFIED_PICK",
    rule_model_id: "ten-day-audited-rule-ensemble-v4", score_kind: "RULE_QUALIFICATION_SCORE",
    probability: null, calibrated: false, primary: qualified,
    qualified_candidates: [qualified], qualified_candidate_count: 1,
  },
};
state.status = {
  ok: true, snapshot_key: state.snapshot.snapshot_key, generated_at: state.snapshot.generated_at,
  source_snapshot_sha256: state.snapshot.source_snapshot.sha256,
  source_snapshot_byte_size: state.snapshot.source_snapshot.byte_size,
  freshness_state: "fresh",
  snapshot_use: { mode: "CURRENT_RESEARCH", current_decision_allowed: true, execution_review_allowed: true },
};
const productionCandidate = {
  ...v2Payload.candidates[0],
  decision_roles: { production: "PRIMARY", legacy: "PRIMARY", research: "NONE" },
  decision_role: "production_primary", production_rank: 1,
};
const legacyOnlyCandidate = {
  ...productionCandidate,
  decision_roles: { production: "NONE", legacy: "PRIMARY", research: "NONE" },
  decision_role: "legacy_market_primary",
};
assert.equal(candidateDecisionRole(productionCandidate, "us"), "production_primary");
assert.equal(decisionRoleLabel("production_primary"), "规则主候选");
assert.equal(candidateDecisionRole(legacyOnlyCandidate, "us"), "legacy_market_primary");
assert.equal(decisionRoleLabel("legacy_market_primary"), "Legacy首选");
const savedAny = AbortSignal.any;
AbortSignal.any = undefined;
const parent = new AbortController();
const bounded = requestSignal(1000, parent.signal);
assert.notEqual(bounded.signal, parent.signal, "parent signal must not replace the timeout signal");
parent.abort();
assert.equal(bounded.signal.aborted, true);
bounded.cleanup();
AbortSignal.any = savedAny;
"""
        )

    def test_scheduler_health_is_contract_bound_and_never_hardcodes_success(self) -> None:
        self.assertIn(
            'scheduler: new Set(["scheduler-health-v2", "scheduler-health-v1"])',
            self.js,
        )
        self.assertIn('health: ["scheduler"]', self.js)
        self.assertIn('getJson("/api/gate-status", { signal })', self.js)
        self.assertIn("GitHub Actions 主调度", self.js)
        self.assertIn("Cloudflare dispatch（可选）", self.js)
        self.assertIn("可选 dispatch 未启用（不影响主调度）", self.js)
        self.assertIn("watchdog 状态未知", self.js)
        self.assertIn("30 分钟 watchdog 已配置", self.js)
        self.assertIn("github_actions_primary_with_30m_watchdog", self.js)
        self.assertIn("active_refresh_mode", self.js)
        self.assertIn("next_active_refresh", self.js)
        for field in (
            "scheduler_primary_provider",
            "scheduler_primary_enabled",
            "cloudflare_dispatch_enabled",
            "publication_slo_seconds",
            "publication_within_slo",
            "scheduler_readiness",
            "checkpoint_evidence_ready",
            "expected_checkpoints_24h",
            "published_on_time_24h",
            "late_recoveries_24h",
            "evidence_lag_batches",
            "scheduler_slo",
            "research_decision_ready",
            "unattended_refresh_ready",
            "calibrated_execution_ready",
        ):
            self.assertIn(field, self.js)
        self.assertIn("证据初始化中", self.js)
        self.assertIn("发布服务目标（非保证）", self.js)
        self.assertIn("us-post-close-schedule-v1", self.js)
        self.assertIn("04:17", self.js)
        self.assertIn("05:17", self.js)
        self.assertNotIn('badge("已配置"', self.js)
        self.assertNotIn('label: "Cloudflare 主调度"', self.js)
        self.assertNotIn("；>${esc(scheduler.usScheduleDays)}", self.js)
        self.assertIn("全池结构风险筛查", self.js)
        self.assertIn("当前 R2 未启用，内嵌同代资产生效", self.js)
        run_app_node(
            r"""
state.snapshot = {
  contract_version: "ui-bootstrap-v1",
  snapshot_key: "2026-08-29_fixture.json",
  generated_at: "2026-08-29T10:17:00+08:00",
  source_snapshot: { sha256: "a".repeat(64), byte_size: 1234 },
};
const gate = {
  ok: true,
  contract_version: "scheduler-health-v2",
  snapshot_key: state.snapshot.snapshot_key,
  generated_at: state.snapshot.generated_at,
  generation_started_at: "2026-08-29T10:18:00+08:00",
  published_at: null,
  publication_backend: "embedded",
  source_invocation_slot: null,
  effective_checkpoint: "2026-08-29T10:17:00+08:00",
  effective_invocation_slot: "2026-08-29T10:17:00+08:00",
  scheduler_start_delay_seconds: 60,
  generation_delay_seconds: 600,
  publication_delay_seconds: null,
  missed_checkpoints_24h: null,
  checkpoint_coverage_status: "INITIALIZING_24H_LEDGER",
  checkpoint_evidence_contract_version: "scheduler-checkpoint-ledger-v1",
  recovery_mode: "none",
  scheduler_primary_provider: "github_actions",
  scheduler_primary_enabled: true,
  cloudflare_dispatch_enabled: false,
  publication_slo_seconds: 2700,
  publication_within_slo: null,
  scheduler_readiness: "INITIALIZING",
  checkpoint_evidence_ready: false,
  unattended_refresh_ready: false,
  expected_checkpoints_24h: 0,
  published_on_time_24h: 0,
  late_recoveries_24h: 0,
  evidence_lag_batches: 1,
  scheduler_slo: {
    contract_version: "scheduler-slo-v1",
    guaranteed: false,
    public_data_source_sla: false,
    target_publication_within_minutes: 45,
    coverage_window_hours: 24,
  },
};
assert.equal(validateResourcePayload("scheduler", gate), gate);
state.schedulerGate = gate;
state.status = {
  ok: true,
  snapshot_key: state.snapshot.snapshot_key,
  generated_at: state.snapshot.generated_at,
  source_snapshot_sha256: state.snapshot.source_snapshot.sha256,
  source_snapshot_byte_size: state.snapshot.source_snapshot.byte_size,
  scheduler_primary_provider: "github_actions",
  scheduler_primary_enabled: true,
  cloudflare_dispatch_enabled: false,
  active_refresh_mode: "github_actions_primary_with_30m_watchdog",
  research_decision_ready: true,
  checkpoint_evidence_ready: false,
  unattended_refresh_ready: false,
  calibrated_execution_ready: false,
  next_active_refresh: "2026-09-01T08:47:00+08:00",
  schedule_us_post_close: {
    contract_version: "us-post-close-schedule-v1",
    market_time_zone: "America/New_York",
    market_checkpoint: "16:17",
    primary_beijing_variants: ["04:17 夏令时", "05:17 冬令时"],
    watchdog_beijing_variants: ["04:47 夏令时", "05:47 冬令时"],
    china_days: "周二至周六",
    dst_variant_selected_at_runtime: true,
  },
};
assert.equal(validActiveRefreshStatus(), true);
let view = schedulerHealthPresentation();
assert.equal(view.primaryState, "ENABLED");
assert.equal(view.primaryLabel, "GitHub Actions 主调度已启用");
assert.equal(view.cloudflareDispatchLabel, "可选 dispatch 未启用（不影响主调度）");
assert.equal(view.watchdogLabel, "30 分钟 watchdog 已配置");
assert.equal(view.nextActiveRefresh, state.status.next_active_refresh);
assert.equal(view.usPrimaryCheckpoints, "04:17 夏令时 / 05:17 冬令时");
assert.equal(view.schedulerReadiness, "INITIALIZING");
assert.equal(view.readinessLabel, "证据初始化中");
assert.equal(view.hasBatchPublicationEvidence, false);
assert.match(view.checkpointEvidence, /证据初始化中/);
assert.doesNotMatch(view.checkpointEvidence, /\b0\b/);
assert.match(view.publicationSlo, /非保证/);
assert.match(view.publicationSlo, /证据初始化中/);
assert.equal(view.readinessLayers.research.label, "已就绪");
assert.equal(view.readinessLayers.checkpoint.label, "证据初始化中");
assert.equal(view.readinessLayers.unattended.label, "证据初始化中");
assert.equal(view.readinessLayers.calibrated.label, "证据初始化中");
assert.throws(() => validateResourcePayload("scheduler", { ...gate, snapshot_key: "other.json" }));
assert.throws(() => validateResourcePayload("scheduler", { ...gate, scheduler_primary_provider: "cloudflare" }));
assert.throws(() => validateResourcePayload("scheduler", {
  ...gate, scheduler_slo: { ...gate.scheduler_slo, guaranteed: true },
}));
assert.throws(() => validateResourcePayload("scheduler", { ...gate, publication_within_slo: false }));

const readyGate = {
  ...gate,
  published_at: "2026-08-29T10:29:00+08:00",
  source_invocation_slot: "2026-08-29T10:17:00+08:00",
  publication_delay_seconds: 720,
  missed_checkpoints_24h: 0,
  checkpoint_coverage_status: "COMPLETE_24H_LEDGER",
  publication_within_slo: true,
  scheduler_readiness: "READY",
  checkpoint_evidence_ready: true,
  unattended_refresh_ready: true,
  expected_checkpoints_24h: 7,
  published_on_time_24h: 7,
};
assert.equal(validateResourcePayload("scheduler", readyGate), readyGate);
state.schedulerGate = readyGate;
state.status = {
  ...state.status,
  checkpoint_evidence_ready: true,
  unattended_refresh_ready: true,
};
view = schedulerHealthPresentation();
assert.equal(view.schedulerReadiness, "READY");
assert.equal(view.readinessLabel, "调度证据就绪");
assert.match(view.checkpointEvidence, /应有 7/);
assert.match(view.checkpointEvidence, /按时 7/);
assert.match(view.publicationSlo, /最近批次在目标内/);
assert.equal(view.readinessLayers.checkpoint.label, "已就绪");
assert.equal(view.readinessLayers.unattended.label, "已就绪");
assert.equal(view.readinessLayers.calibrated.label, "未就绪");

const degradedGate = {
  ...readyGate,
  scheduler_readiness: "DEGRADED",
  publication_within_slo: false,
  published_on_time_24h: 6,
  late_recoveries_24h: 1,
  checkpoint_evidence_ready: true,
  unattended_refresh_ready: false,
};
assert.equal(validateResourcePayload("scheduler", degradedGate), degradedGate);
state.schedulerGate = degradedGate;
state.status = { ...state.status, checkpoint_evidence_ready: true, unattended_refresh_ready: false };
view = schedulerHealthPresentation();
assert.equal(view.schedulerReadiness, "DEGRADED");
assert.equal(view.readinessLabel, "调度证据降级");
assert.equal(view.readinessLayers.checkpoint.label, "已就绪", "complete degraded evidence is still inspectable");
assert.equal(view.readinessLayers.unattended.label, "未就绪");
assert.match(view.publicationSlo, /最近批次超出目标/);

state.status = { ...state.status, cloudflare_dispatch_enabled: true };
view = schedulerHealthPresentation();
assert.equal(schedulerHealthPresentation().primaryState, "UNKNOWN");

const legacyGate = {
  ...gate,
  contract_version: "scheduler-health-v1",
  published_at: "2026-08-29T10:29:00+08:00",
  source_invocation_slot: "2026-08-29T10:17:00+08:00",
  publication_delay_seconds: 720,
  missed_checkpoints_24h: 0,
  checkpoint_coverage_status: "COMPLETE_24H_LEDGER",
  scheduler_enabled: false,
  scheduler_gap: "GITHUB_WORKFLOW_DISPATCH_TOKEN_NOT_PROVISIONED",
};
assert.equal(validateResourcePayload("scheduler", legacyGate), legacyGate);
state.schedulerGate = legacyGate;
state.status = {};
view = schedulerHealthPresentation();
assert.equal(view.primaryState, "UNKNOWN", "v1 is accepted read-only, never promoted to GitHub primary evidence");
assert.match(view.gapLabel, /旧版调度合同/);
state.schedulerGate = null;
assert.equal(schedulerHealthPresentation().primaryState, "UNKNOWN");
"""
        )

    def test_shortlist_is_list_first_and_loads_details_on_demand(self) -> None:
        self.assertIn("决策短名单", self.html + self.js)
        self.assertIn("召回 ${fmt(recalled, 0)} · 规则评估 ${fmt(evaluated, 0)} · 发布 ${fmt(published, 0)}", self.js)
        self.assertIn("candidateApiId", self.js)
        self.assertIn("/api/candidates/${encodeURIComponent(apiId)}", self.js)
        self.assertIn("candidate-detail-host", self.js + self.css)
        self.assertIn("candidate-detail-back", self.js + self.css)
        self.assertIn("返回决策短名单", self.js)
        self.assertIn("position: fixed", self.css)
        self.assertIn("max-height: calc(100vh - 112px)", self.css)

    def test_event_clustering_and_history_maturity_are_visible(self) -> None:
        self.assertRegex(self.js, r"function clusterEvents\(")
        for helper in (
            "eventMaterialityLabel",
            "eventPriceReactionLabel",
            "eventExpiryLabel",
            "eventAgeDays",
        ):
            self.assertIn(helper, self.js)
        self.assertIn("按公司、事件类型与生效日期去重", self.js)
        self.assertIn("two-tier-event-coverage-v1", self.js)
        self.assertIn("PASS 不等于官方确认", self.js)
        self.assertIn("history-maturity-progress", self.js + self.css)
        self.assertIn("先走满 10 个交易日，再评价模型", self.js)
        self.assertIn("reliabilityDayThreshold = Math.max(60", self.js)
        self.assertIn("指标将在样本成熟后显示", self.js)
        self.assertIn("不展示空指标网格", self.js)

    def test_requests_search_and_tabs_are_resilient_and_accessible(self) -> None:
        self.assertIn("class HttpError", self.js)
        self.assertIn("AbortSignal.timeout", self.js)
        self.assertIn("AbortSignal.any", self.js)
        self.assertIn("requestControllers.tab?.abort", self.js)
        self.assertIn("requestControllers.detail?.abort", self.js)
        self.assertIn("const SEARCH_DEBOUNCE_MS = 150", self.js)
        self.assertIn("debounceSearch", self.js)
        for key in ("ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"):
            self.assertIn(key, self.js)
        self.assertIn('button.setAttribute("tabindex", active ? "0" : "-1")', self.js)
        self.assertIn('tabindex="0"', self.html)
        self.assertIn('tabindex="-1"', self.html)
        self.assertIn("min-height: 44px", self.css)
        self.assertIn("font-size: 14px", self.css)
        self.assertIn("chart-data-summary", self.js + self.css)
        self.assertIn("resourceQueryKey", self.js)
        self.assertIn("resourceListUrl", self.js)
        self.assertIn('url.searchParams.set("q", query)', self.js)
        self.assertIn('url.searchParams.set("event_type", eventType)', self.js)
        self.assertIn('url.searchParams.set("direction", direction)', self.js)
        self.assertIn("reloadPagedResource", self.js)
        self.assertIn("candidateDialogFocusables", self.js)
        self.assertIn('element.setAttribute("inert", "")', self.js)
        self.assertIn('event.key === "Tab"', self.js)
        self.assertIn("body.has-modal-dialog", self.css)

    def test_frontend_uses_published_cloud_snapshot_only(self) -> None:
        self.assertIn('getJson("/api/latest-summary")', self.js)
        self.assertNotIn('getJson("/api/latest")', self.js)
        self.assertNotIn('/api/live?market=', self.js)
        self.assertNotIn("LIVE_POLL_INTERVAL_MS", self.js)
        self.assertNotIn("pollVisibleLive", self.js)
        self.assertNotIn("state.live", self.js)
        self.assertNotIn("force=1", self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertIn("评分与排序不在浏览器重算", self.js)
        self.assertIn('candidate.execution_state === "BLOCKED"', self.js)

    def test_hk_us_dynamic_cross_section_is_visible_without_full_market_overclaim(self) -> None:
        self.assertIn("dynamic_market_snapshot", self.js)
        self.assertIn("本轮公开横截面重新筛选", self.js)
        self.assertIn("本轮动态多路召回", self.js)
        self.assertIn('isA && coverage.origin === "dynamic_snapshot"', self.js)
        self.assertIn("动态市场池", self.js)
        self.assertIn("eligible_discovery_size", self.js)
        self.assertIn("三市场有界动态召回", self.js)
        self.assertIn("版本化静态池（旧快照）", self.js)
        self.assertIn("使用上次健康动态池缓存，本轮没有完成市场重扫", self.js)
        self.assertIn("这是旧快照的版本化静态池", self.js)
        self.assertIn('if (origin === "dynamic_market_snapshot")', self.js)
        self.assertIn('if (origin === "dynamic_market_snapshot_cache")', self.js)
        self.assertNotIn("只版本化策展池，每轮重新取价和排序", self.js)
        self.assertNotIn("全市场扫描完整", self.js)

    def test_cloud_snapshot_timing_is_visible(self) -> None:
        self.assertIn('id="snapshotAsOf"', self.html)
        self.assertIn('id="nextRefreshTime"', self.html)
        self.assertIn("snapshot_as_of", self.js)
        self.assertIn("next_refresh", self.js)
        self.assertIn("next_active_refresh", self.js)
        self.assertIn("下次实际自动刷新", self.html + self.js)
        self.assertIn("当前证据与模型条件不足以生成跨市场买入结论", self.js)

    def test_missing_quote_provenance_is_not_presented_as_market_data(self) -> None:
        self.assertRegex(self.js, r"function candidateQuoteView\(")
        self.assertIn("行情未记录", self.js)
        self.assertIn("计划价（非行情）", self.js)
        self.assertIn("源时间未记录", self.js)
        self.assertNotIn(
            "quote.source_as_of || state.status?.snapshot_as_of || state.snapshot?.generated_at",
            self.js,
        )

    def test_shadow_research_outcomes_are_reported_outside_executable_performance(self) -> None:
        self.assertNotRegex(self.js, r"function shadowLedgerStats\(")
        self.assertIn("meta.shadow_ledger", self.js)
        for field in (
            "prediction_count",
            "eligible_count",
            "pending_count",
            "settled_count",
            "excluded_count",
            "raw_prediction_count",
            "raw_count",
            "included_in_executable_performance",
        ):
            self.assertIn(field, self.js)
        self.assertIn("shadow_outcome", self.js)
        self.assertIn("Shadow·PENDING", self.js)
        self.assertIn("Shadow·SETTLED", self.js)
        self.assertIn("Shadow 研究轨", self.js)
        self.assertIn("后端未发布 Shadow 聚合收益", self.js)
        self.assertIn("前端不会把缺失字段解释为 0", self.js)
        self.assertIn("不计入可执行绩效、胜率或收益", self.js)

    def test_history_metrics_render_the_published_performance_contract(self) -> None:
        self.assertIn("meta.performance", self.js)
        self.assertRegex(self.js, r"function renderHistoryMetric\(")
        self.assertIn("minimum_reliable_sample", self.js)
        self.assertIn("cohort_model_id", self.js)
        self.assertIn("cohort_label_version", self.js)
        self.assertIn("cohort_independent_day_count", self.js)
        self.assertIn("按 target_date 仅保留最晚发布预测", self.js)
        self.assertIn('metric.status === "READY" || metric.status === "INSUFFICIENT_SAMPLE"', self.js)
        for key in (
            "mean_net_return",
            "positive_rate",
            "top_decile_positive_rate",
            "selection_rank_ic",
            "brier_score",
            "ece_10bin",
            "expected_shortfall_10pct",
            "settlement_sequence_max_drawdown",
            "comparable_sample_count",
        ):
            self.assertIn(key, self.js)
        self.assertIn("历史已选样本 Rank IC", self.js)
        self.assertIn("结算序列最大回撤", self.js)
        self.assertIn("早期样本", self.js)
        self.assertIn('key === "comparable_sample_count"', self.js)
        self.assertIn('String(metric.status || "").toUpperCase() === "NO_SAMPLE"', self.js)
        self.assertIn('if (isPublishedZeroSampleCount) return "0"', self.js)
        self.assertIn('if (!canDisplay || !hasNumericValue) return "—"', self.js)
        self.assertNotIn('settled ? "待聚合" : "无样本"', self.js)

    def test_history_no_sample_mobile_disclosure_and_navigation_hint(self) -> None:
        self.assertIn("history-metrics-details", self.js + self.css)
        self.assertIn("查看指标定义", self.js)
        self.assertIn('sampleStatus !== "NO_SAMPLE"', self.js)
        self.assertIn('window.matchMedia?.("(max-width: 760px)")?.matches', self.js)
        self.assertIn("横向滑动查看更多", self.css)
        self.assertIn(".history-master-detail > div { order: -1; }", self.css)
        self.assertIn('scrollIntoView({ behavior: "smooth", block: "start" })', self.js)
        self.assertIn(".history-metrics-details > summary", self.css)

    def test_shadow_exclusion_copy_does_not_guess_the_reason(self) -> None:
        self.assertIn("未通过当前准入合同，详见后端诊断", self.js)
        self.assertNotIn("因身份、时点或结算合同不完整被排除", self.js)
        self.assertNotIn("不完整或冲突合同", self.js)

    def test_history_rows_show_formal_and_shadow_tracks_independently(self) -> None:
        self.assertRegex(self.js, r"function historyFormalStatus\(")
        self.assertRegex(self.js, r"function historyFormalStatusTag\(")
        self.assertRegex(self.js, r"function historyProductionStatusTag\(")
        for label in ("Legacy", "主动放弃", "可执行·缺结算", "可执行·待结算", "可执行·已结算", "已结算·待校验", "结算无效"):
            self.assertIn(label, self.js)
        self.assertIn('formalStatus === "SETTLED_VALID"', self.js)
        self.assertIn("item?.outcome_validation?.valid === true", self.js)
        self.assertNotIn('if (outcomeStatus === "SETTLED") return { code: "SETTLED"', self.js)
        self.assertIn("history-row-statuses", self.js)
        self.assertIn("规则资格历史轨", self.js)
        self.assertIn("规则合格日", self.js)
        self.assertIn("资格分不是概率", self.js)
        self.assertIn("qualified_rule_day_count", self.js)
        self.assertIn("shadowOutcomeTag(item)", self.js)

    def test_evidence_views_and_canvas_charts_are_implemented(self) -> None:
        for renderer in ("renderDecision", "renderCandidates", "renderEvents", "renderHistory", "renderModel", "renderHealth"):
            self.assertRegex(self.js, rf"function {renderer}\(")
        self.assertIn('<canvas id="decisionChart"', self.js)
        self.assertIn('<canvas id="historyChart"', self.js)
        self.assertNotIn("<svg", self.html + self.js)
        self.assertIn('aria-label="全部规则合格候选通道审计"', self.js)
        self.assertIn("事件催化轨已绑定", self.js)
        self.assertIn("event_id：", self.js)
        self.assertIn("质量趋势通道不绑定正向事件", self.js)
        self.assertIn("规则候选证据", self.js)

    def test_copy_does_not_claim_uncalibrated_performance(self) -> None:
        self.assertIn("推荐度不是收益概率", self.js)
        self.assertIn("研究优先级，不是上涨概率", self.js)
        self.assertIn("不展示“命中率”", self.js)
        prohibited = ("保证收益", "稳赚", "预测准确率 90", "胜率 90")
        for phrase in prohibited:
            self.assertNotIn(phrase, self.html + self.js)

    def test_shadow_ten_day_probability_is_visible_but_never_promoted_to_formal(self) -> None:
        self.assertRegex(self.js, r"function candidateShadowModel\(")
        self.assertRegex(self.js, r"function tenDayModelPresentation\(")
        self.assertIn('status === "SHADOW_READY"', self.js)
        for phrase in (
            "10 日概率模型已参与严格门禁",
            "10 日概率模型影子运行中",
            "10 日概率模型留出检验未通过",
            "10 日概率模型数据积累中",
            "影子 P10",
            "不参与正式决策",
            "当前成分股历史回填",
            "校准可执行",
        ):
            self.assertIn(phrase, self.js)
        for metric in (
            "independent_test_date_count",
            "brier_score",
            "brier_skill",
            "ece_10bin",
            "auc",
            "top_decile_excess_vs_mean",
        ):
            self.assertIn(metric, self.js)
        self.assertIn("evaluated_candidates", self.js)
        self.assertIn("shadow_model.probability", self.js)
        self.assertIn("shadow-model-card", self.js + self.css)
        self.assertNotIn("正式上涨概率", self.js)

    def test_research_priority_uses_the_server_candidate_snapshot_without_silent_substitution(self) -> None:
        self.assertRegex(self.js, r"function researchCandidateSnapshot\(")
        self.assertIn("priority?.candidate_snapshot", self.js)
        self.assertIn("researchCandidate,", self.js)
        self.assertIn(
            'snapshot?.global_decision?.contract_version === "global-10d-v1"',
            self.js,
        )
        self.assertIn("return null;", self.js)
        self.assertIn("未深评", self.js)
        self.assertIn('research: "研究优先"', self.js)

    def test_event_links_and_unknown_direction_are_normalized(self) -> None:
        self.assertIn("function safeHttpUrl", self.js)
        self.assertIn('if (!raw) return ""', self.js)
        self.assertIn('parsed.protocol === "https:" || parsed.protocol === "http:"', self.js)
        self.assertIn("function normalizedDirection", self.js)

    def test_design_is_responsive_and_has_no_css_gradients(self) -> None:
        self.assertIn("@media (max-width: 760px)", self.css)
        self.assertIn("grid-template-columns: 192px", self.css)
        self.assertIsNone(re.search(r"(?:linear|radial|conic)-gradient\(", self.css))

    def test_three_score_lenses_and_dual_low_evidence_are_rendered(self) -> None:
        for helper in ("dualLowAnalysis", "dualLowLabel", "scoreLensCards", "dualLowPanel"):
            self.assertRegex(self.js, rf"function {helper}\(")
        self.assertIn("实际决策", self.js)
        self.assertIn("影子排序", self.js)
        self.assertIn("价值筛选", self.js)
        self.assertIn("独立分析项目 · 双低七因子", self.js)
        self.assertIn("A股双低独立榜单", self.js)
        self.assertIn("analysis_projects?.dual_low", self.js)
        self.assertIn("评分与排序不在浏览器重算", self.js)

    def test_freshness_polling_reloads_only_when_snapshot_changes(self) -> None:
        self.assertIn("const STATUS_POLL_INTERVAL_MS = 5 * 60 * 1000", self.js)
        self.assertRegex(self.js, r"async function pollStatus\(")
        self.assertIn('getJson("/api/status")', self.js)
        self.assertIn("snapshot_as_of", self.js)
        self.assertIn("next_refresh", self.js)
        self.assertIn("status.generated_at !== previousGeneratedAt", self.js)
        self.assertIn("!state.snapshot ||", self.js)
        self.assertIn('getJson("/api/latest-summary")', self.js)
        self.assertIn("ensureTabData", self.js)
        self.assertIn("window.setInterval(pollStatus, STATUS_POLL_INTERVAL_MS)", self.js)
        for label in ("计划批次已发布", "等待计划批次", "计划批次已过期", "状态未知"):
            self.assertIn(label, self.js)

    def test_initial_load_is_bounded_and_tabs_load_only_their_required_payloads(self) -> None:
        self.assertIn("const TAB_DATA_REQUIREMENTS", self.js)
        self.assertRegex(self.js, r"async function ensureTabData\(")
        self.assertRegex(self.js, r"async function applyBootstrapPayload\(")
        initialize = self.js[self.js.index("async function initialize()") :]
        self.assertIn('getJson("/api/latest-summary")', initialize)
        self.assertNotIn('getJson("/api/latest")', initialize)
        self.assertNotIn("getHistoryPayload()", initialize.split("initialize();", 1)[0])
        self.assertIn('resourceListUrl("history", page)', self.js)
        self.assertIn('resourceListUrl(resource, 1)', self.js)
        self.assertIn('resourceListUrl(resource, nextPage)', self.js)
        self.assertIn("tabRequestStillCurrent", self.js)
        self.assertIn("payloadIdentityMatchesSnapshot", self.js)
        self.assertIn("validateResourcePayload", self.js)

    def test_lazy_snapshot_use_merges_monotonically_and_checkpoint_poll_has_no_five_minute_gap(self) -> None:
        run_app_node(
            r"""
const snapshot = {
  contract_version: "ui-bootstrap-v1",
  snapshot_key: "2026-08-27_fixture.json",
  generated_at: "2026-08-27T08:17:00+08:00",
  source_snapshot: { sha256: "a".repeat(64), byte_size: 1234 },
};
const use = (evaluatedAt, allowed, freshness = allowed ? "fresh" : "stale") => ({
  contract_version: "snapshot-use-v1",
  snapshot_key: snapshot.snapshot_key,
  source_snapshot_sha256: snapshot.source_snapshot.sha256,
  source_snapshot_byte_size: snapshot.source_snapshot.byte_size,
  evaluated_at: evaluatedAt,
  freshness_state: freshness,
  mode: allowed ? "CURRENT_RESEARCH" : "HISTORICAL_RESEARCH_ONLY",
  current_decision_allowed: allowed,
  execution_review_allowed: allowed,
  blocker_codes: allowed ? [] : ["SNAPSHOT_NOT_FRESH"],
});
state.snapshot = snapshot;
state.status = {
  ok: true,
  snapshot_key: snapshot.snapshot_key,
  generated_at: snapshot.generated_at,
  freshness_state: "fresh",
  snapshot_use: use("2026-08-27T00:02:00Z", true),
  effective_decisions: { production_action: "QUALIFIED_PICK", global_action: "REVIEW_EXECUTABLE_PICK" },
};
const older = mergeSnapshotDecisionState({
  snapshot_use: use("2026-08-27T00:01:00Z", false),
  effective_decisions: { production_action: "HISTORICAL_ONLY", global_action: "NO_VALID_PICK" },
}, { strict: true });
assert.equal(older, false);
assert.equal(state.status.snapshot_use.current_decision_allowed, true);
assert.equal(state.status.effective_decisions.production_action, "QUALIFIED_PICK");
assert.equal(mergeSnapshotDecisionState({
  snapshot_use: use("2026-08-27T00:02:00Z", false),
  effective_decisions: { production_action: "HISTORICAL_ONLY" },
}, { strict: true }), false);
assert.equal(state.status.snapshot_use.current_decision_allowed, true);

const newer = mergeSnapshotDecisionState({
  snapshot_use: use("2026-08-27T00:03:00Z", false),
  effective_decisions: { production_action: "HISTORICAL_ONLY", global_action: "NO_VALID_PICK" },
}, { strict: true });
assert.equal(newer, true);
assert.equal(snapshotUseTruth().currentDecisionAllowed, false);
assert.equal(state.status.effective_decisions.production_action, "HISTORICAL_ONLY");
assert.equal(mergeSnapshotDecisionState({
  snapshot_use: { ...use("2026-08-27T00:04:00Z", true), snapshot_key: "other.json" },
}, { strict: false }), false);
assert.throws(() => mergeSnapshotDecisionState({
  snapshot_use: { ...use("2026-08-27T00:04:00Z", true), snapshot_key: "other.json" },
}, { strict: true }), /身份不一致/);
assert.equal(nextRefreshPollDelay("2026-08-27T00:10:00Z", Date.parse("2026-08-27T00:09:59Z")), 1250);
assert.equal(nextRefreshPollDelay("2026-08-27T00:10:00Z", Date.parse("2026-08-27T00:10:01Z")), CHECKPOINT_POLL_RETRY_MS);
"""
        )

    def test_decision_health_and_evidence_do_not_change_after_events_tab_load(self) -> None:
        run_app_node(
            r"""
const candidate = { market: "us", code: "MSFT", symbol: "MSFT", name: "Microsoft" };
const evidence = {
  event_id: "evt-global-primary", event_type: "announcement", market: "us", symbol: "MSFT",
  company: "Microsoft", title: "Official filing", source: "SEC", url: "https://example.test/filing",
  published_at: "2026-08-26T20:00:00Z", effective_at: "2026-08-27T00:00:00Z",
  decision_eligible: true, ingestion_mode: "automatic", evidence_status: "verified",
  source_tier: "official", direction: "positive",
};
const section = (market) => ({
  key: market,
  decision: market === "us" ? { primary: candidate } : {},
  pool_health: { state: "READY" },
  quote_health: { status: "available", quote_coverage: 1, realtime_coverage: 1 },
  market_regime: "trend_risk_on",
  stats: { universe_origin: market === "a_share" ? "dynamic_snapshot" : "dynamic_market_snapshot" },
});
state.snapshot = {
  contract_version: "ui-bootstrap-v1",
  snapshot_key: "2026-08-27_fixture.json",
  generated_at: "2026-08-27T08:17:00+08:00",
  target_date: "2026-08-27", forecast_end_date: "2026-09-10",
  source_snapshot: { sha256: "b".repeat(64), byte_size: 2000 },
  markets: { a_share: section("a_share"), hk: section("hk"), us: section("us") },
  analysis_models: { ten_day_return: {
    status: "READY", calibrated: true, costs_ready: true, tail_risk_ready: true,
    participates_in_decision: true, model_id: "ten-day-model",
  } },
  global_decision: {
    contract_version: "global-10d-v1", decision_scope: "global_10d",
    action: "REVIEW_EXECUTABLE_PICK", action_basis: "strict_cross_market_gate_v1",
    calibrated: true, probability_status: "CALIBRATED", probability: 0.61,
    automatic_external_evidence_count: 1, blocker_codes: [],
    market_states: { a_share: { state: "READY" }, hk: { state: "READY" }, us: { state: "READY" } },
    primary: {
      status: "EXECUTABLE", market: "us", code: "MSFT", name: "Microsoft",
      score_kind: "TEN_DAY_EXPECTED_NET_UTILITY", probability: 0.61,
      expected_net_utility: 0.02, transaction_cost: 0.001, tail_risk: 0.05,
      model_id: "ten-day-model", calibrated: true,
    },
  },
  production_decision: null,
  decision_evidence: { automatic_external_evidence_count: 1, bound_event_ids: [evidence.event_id], items: [evidence] },
  event_stats: { total: 405, model_signals: 3, automatic_external: 1, decision_eligible: 1, decision_bound: 1 },
};
state.status = {
  ok: true, freshness_state: "fresh", snapshot_key: state.snapshot.snapshot_key,
  generated_at: state.snapshot.generated_at,
  source_snapshot_sha256: state.snapshot.source_snapshot.sha256,
  source_snapshot_byte_size: state.snapshot.source_snapshot.byte_size,
  snapshot_use: {
    snapshot_key: state.snapshot.snapshot_key,
    source_snapshot_sha256: state.snapshot.source_snapshot.sha256,
    source_snapshot_byte_size: state.snapshot.source_snapshot.byte_size,
    evaluated_at: "2026-08-27T00:18:00Z", freshness_state: "fresh",
    mode: "CURRENT_RESEARCH", current_decision_allowed: true, execution_review_allowed: true,
    blocker_codes: [],
  },
};
__roots.set("#healthView", { innerHTML: "" });
const beforeTruth = globalDecisionTruth();
const beforeEvidence = automaticExternalEvents().map((item) => item.event_id);
renderHealth();
const beforeHealth = __roots.get("#healthView").innerHTML;
state.eventsPayload = {
  events: { items: [{ ...evidence, event_id: "unbound-newer", symbol: "NVDA" }] },
  event_publication: { total: 999, published: 1, truncated: 998, is_truncated: true },
};
const afterTruth = globalDecisionTruth();
const afterEvidence = automaticExternalEvents().map((item) => item.event_id);
renderHealth();
assert.equal(beforeTruth.action, "REVIEW_EXECUTABLE_PICK");
assert.equal(afterTruth.action, beforeTruth.action);
assert.equal(afterTruth.executable.primary.code, beforeTruth.executable.primary.code);
assert.deepEqual(afterEvidence, beforeEvidence);
assert.equal(publishedEventStats().modelSignals, 3);
assert.equal(__roots.get("#healthView").innerHTML, beforeHealth);
assert.deepEqual(
  automaticEventFeed().map((item) => item.event_id),
  ["evt-global-primary", "unbound-newer"],
  "bootstrap-bound evidence remains visible after lazy event loading",
);
"""
        )

    def test_stale_published_qualification_is_historical_and_never_current(self) -> None:
        run_app_node(
            r"""
const candidate = {
  market: "us", code: "VZ", symbol: "VZ", name: "Verizon",
  recommendation_degree: 72, realtime: {
    price: 50, change_pct: 0.2, source_as_of: "2026-08-26T16:00:00-04:00",
    fetched_at: "2026-08-27T08:00:00+08:00", volume_unit: "share",
  },
};
const primary = {
  qualification_id: "qual_0123456789abcdef01234567", status: "QUALIFIED",
  market: "us", code: "VZ", name: "Verizon",
  rule_model_id: "ten-day-audited-rule-ensemble-v4",
  score_kind: "RULE_QUALIFICATION_SCORE", qualification_score: 75,
  probability: null, calibrated: false, candidate_snapshot: candidate,
};
const snapshot = {
  contract_version: "ui-bootstrap-v1",
  model_version: CURRENT_PRODUCTION_MODEL_VERSION,
  snapshot_key: "2026-08-26_fixture.json",
  generated_at: "2026-08-26T22:47:00+08:00",
  target_date: "2026-08-26", forecast_end_date: "2026-09-09",
  source_snapshot: { sha256: "a".repeat(64), byte_size: 1000 },
  production_decision: {
    contract_version: "production-rule-10d-v1",
    decision_scope: "global_10d_bounded_recall",
    action: "QUALIFIED_PICK", action_basis: "dual_track_candidate_qualification_v4",
    rule_model_id: "ten-day-audited-rule-ensemble-v4",
    score_kind: "RULE_QUALIFICATION_SCORE", probability: null, calibrated: false,
    primary, qualified_candidates: [primary], qualified_candidate_count: 1,
    rejected_candidate_count: 797, evaluated_candidate_count: 798, blocker_codes: [],
  },
  global_decision: {
    contract_version: "global-10d-v1", decision_scope: "global_10d",
    action_basis: "strict_cross_market_gate_v1", action: "NO_VALID_PICK",
    primary: null, blocker_codes: [], automatic_external_evidence_count: 0,
  },
  decision_evidence: { automatic_external_evidence_count: 0, items: [] },
  markets: {
    a_share: { key: "a_share", decision: {}, pool_health: {}, quote_health: {}, stats: {} },
    hk: { key: "hk", decision: {}, pool_health: {}, quote_health: {}, stats: {} },
    us: { key: "us", decision: { primary: candidate }, pool_health: {}, quote_health: {}, stats: {} },
  },
};
const status = {
  ok: true, snapshot_key: snapshot.snapshot_key, generated_at: snapshot.generated_at,
  source_snapshot_sha256: snapshot.source_snapshot.sha256,
  source_snapshot_byte_size: snapshot.source_snapshot.byte_size,
  freshness_state: "stale",
  snapshot_use: {
    mode: "HISTORICAL_RESEARCH_ONLY", current_decision_allowed: false,
    execution_review_allowed: false, blocker_codes: ["SNAPSHOT_NOT_FRESH"],
  },
};
state.snapshot = snapshot;
state.status = status;
const truth = productionDecisionTruth(snapshot, status);
assert.equal(truth.currentQualifiedCount, 0);
assert.equal(truth.historicalQualifiedCount, 1);
assert.equal(truth.currentAction, "HISTORICAL_ONLY");
assert.equal(truth.publishedAction, "QUALIFIED_PICK");
assert.equal(candidateDecisionRole(candidate, "us"), "historical_qualified");
__roots.set("#decisionView", { innerHTML: "" });
renderDecision();
const html = __roots.get("#decisionView").innerHTML;
assert.match(html, /data-user-decision-state="NO_ACTION"/);
assert.match(html, /今日不行动/);
assert.match(html, /所有历史候选均暂停执行/);
assert.doesNotMatch(html, /今日质量趋势合格/);
assert.doesNotMatch(html, /仍需核对交易计划/);
"""
        )

    def test_decision_page_makes_degraded_pool_visible(self) -> None:
        self.assertRegex(self.js, r"function poolHealthAlert\(")
        self.assertIn("候选池降级", self.js)
        self.assertIn("覆盖不足", self.js)
        self.assertIn("decision.blocker_codes", self.js)
        self.assertIn("section.pool_health", self.js)
        self.assertIn("health.reason_codes", self.js)
        self.assertIn("health.broad_pool_count", self.js)
        self.assertIn("health.quote_coverage", self.js)
        self.assertIn("POOL_COVERAGE_INSUFFICIENT", self.js)
        self.assertIn("pool-health-alert", self.css)

    def test_recall_funnel_uses_fixed_market_targets_and_full_a_share_stages(self) -> None:
        self.assertRegex(self.js, r"function recallFunnel\(")
        self.assertIn("{ a_share: 300, hk: 200, us: 300 }", self.js)
        for label in (
            "实际召回 / 目标",
            "有效行情 / 基础评分",
            "技术评分 / 深度研究",
            "300 / 200 / 300",
        ):
            self.assertIn(label, self.js)
        self.assertIn("A_SHARE_TECHNICAL_COVERAGE_BELOW_MINIMUM", self.js)
        self.assertIn("hasFullScoringStages", self.js)
        self.assertIn("旧快照待更新；未发布全池基础/技术评分计数", self.js)
        self.assertIn('label: "有效行情 / 深度评分"', self.js)
        self.assertIn("target > 0", self.js)

    def test_freshness_and_data_quality_have_separate_badges(self) -> None:
        self.assertIn('id="healthBadge"', self.html)
        self.assertIn('id="qualityBadge"', self.html)
        self.assertIn("快照新鲜度与数据完整度分开判断", self.js)
        self.assertIn("health-badge.is-degraded", self.css)

    def test_cross_market_answer_is_dynamic_and_strict(self) -> None:
        self.assertRegex(self.js, r"function globalDecisionTruth\(")
        self.assertRegex(self.js, r"function marketCoverageState\(")
        self.assertRegex(self.js, r"function tenDayModelState\(")
        self.assertIn('"NO_VALID_PICK"', self.js)
        self.assertIn("TEN_DAY_PROBABILITY_UNCALIBRATED", self.js)
        self.assertIn("EXTERNAL_EVIDENCE_MISSING", self.js)
        self.assertIn("MARKET_COVERAGE_INCOMPLETE", self.js)
        self.assertIn('serverPrimary.score_kind === "TEN_DAY_EXPECTED_NET_UTILITY"', self.js)
        self.assertIn('serverPrimary.status === "EXECUTABLE"', self.js)
        self.assertIn('serverDecision?.contract_version === "global-10d-v1"', self.js)
        self.assertIn('serverDecision?.decision_scope === "global_10d"', self.js)
        self.assertIn('serverDecision?.action_basis === "strict_cross_market_gate_v1"', self.js)
        self.assertIn('serverDecision?.calibrated === true', self.js)
        self.assertIn("serverBlockers.length === 0", self.js)
        self.assertIn("allMarketsReady", self.js)
        self.assertIn("candidateHasEvidence", self.js)
        self.assertIn("serverPrimary.model_id === modelState.model.model_id", self.js)
        self.assertIn("severity[serverStateName] >= severity[derivedState]", self.js)
        self.assertIn("probability: ready ? serverPrimary.probability : null", self.js)
        self.assertIn("EXECUTABLE_REVIEW", self.js)
        self.assertNotIn("candidateScore(candidate) / 100", self.js)

    def test_production_rule_pick_is_primary_and_never_rendered_as_probability(self) -> None:
        self.assertRegex(self.js, r"function productionDecisionTruth\(")
        self.assertRegex(self.js, r"function productionQualifiedRows\(")
        self.assertRegex(self.js, r"function syncPreferredCandidate\(")
        self.assertIn('decision.contract_version === "production-rule-10d-v1"', self.js)
        for historical_model, action_basis, rule_model in (
            ("smart-selector-2026-08-25.1-production-rule", "strict_rule_qualification_v1", "ten-day-audited-rule-ensemble-v1"),
            ("smart-selector-2026-08-26.1-candidate-rule", "candidate_level_rule_qualification_v2", "ten-day-audited-rule-ensemble-v2"),
            ("smart-selector-2026-08-26.2-dual-track-rule", "dual_track_candidate_qualification_v3", "ten-day-audited-rule-ensemble-v3"),
        ):
            self.assertIn(historical_model, self.js)
            self.assertIn(f'actionBasis: "{action_basis}"', self.js)
            self.assertIn(f'ruleModelId: "{rule_model}"', self.js)
        self.assertIn('decision.action_basis === "dual_track_candidate_qualification_v4"', self.js)
        self.assertIn('decision.rule_model_id === "ten-day-audited-rule-ensemble-v4"', self.js)
        self.assertIn('["QUALIFIED_PICK", "NO_QUALIFIED_PICK"].includes(String(decision.action || ""))', self.js)
        self.assertIn('decision.score_kind === "RULE_QUALIFICATION_SCORE"', self.js)
        self.assertIn("decision.probability === null", self.js)
        self.assertIn("decision.calibrated === false", self.js)
        self.assertIn("serverPrimary?.qualification_score", self.js)
        self.assertIn('const currentAction = !currentContract', self.js)
        self.assertIn("const selected = production.qualified || production.historicalQualified;", self.js)
        self.assertIn("浏览器绝不把它们自行升级为 QUALIFIED_PICK", self.js)
        self.assertIn("规则资格分（非概率）", self.js)
        self.assertIn("生产规则模型已有合格候选", self.js)
        self.assertIn("当前规则合格 ${fmt(production.currentQualifiedCount, 0)}", self.js)
        self.assertIn("productionQualificationForCandidate", self.js)
        self.assertIn("decision.qualified_candidates", self.js)
        self.assertIn("qualifiedCount: currentQualified ? qualifiedRows.length : 0", self.js)
        self.assertIn("publishedCount !== rows.length", self.js)
        self.assertIn("const publishedQualified = productionQualifiedRows(state.snapshot, market)", self.js)
        self.assertIn("production_primary: 0", self.js)
        self.assertIn('production_primary: "规则主候选"', self.js)
        self.assertIn('legacy_market_primary: "Legacy首选"', self.js)
        self.assertIn("syncPreferredCandidate({ revealQualified: true })", self.js)
        self.assertIn("productionPrimary.rule_model_id || item.production_decision?.rule_model_id", self.js)
        self.assertIn("全局校准模型结论", self.js)
        self.assertIn("生产规则资格模型 · V4", self.js)
        self.assertIn("推荐度 64 / 63 / 64", self.js)
        self.assertIn("规则资格轨已通过", self.js)
        self.assertIn("规则轨 ${esc(production.action)} · 校准轨", self.js)
        self.assertIn("只有通过校准合同的 global_decision 才能展示上涨概率", self.js)
        self.assertIn("calibrated-track-card", self.css)
        self.assertNotRegex(self.js, r"ratioPct\([^\n)]*qualification_score")
        self.assertNotRegex(self.js, r"qualification_score\s*/\s*100")
        self.assertNotRegex(self.js, r"pct\([^\n)]*qualification_score")

    def test_v4_dual_track_qualification_is_named_without_inventing_event_evidence(self) -> None:
        self.assertIn('decision.action_basis === "dual_track_candidate_qualification_v4"', self.js)
        self.assertIn('decision.rule_model_id === "ten-day-audited-rule-ensemble-v4"', self.js)
        self.assertIn('["production-rule-inputs-v2", "production-rule-inputs-v3"]', self.js)
        self.assertRegex(self.js, r"function qualificationTrackLabel\(track\)")
        self.assertIn('event_catalyst: "事件催化合格"', self.js)
        self.assertIn('quality_technical: "质量趋势合格"', self.js)
        self.assertIn("qualificationTrackLabel(primary.qualification_track)", self.js)
        self.assertIn("qualificationTrackLabel(qualification.qualification_track)", self.js)
        self.assertIn("qualificationTrackLabel(displayPrimary.qualification_track)", self.js)
        self.assertIn("qualificationTrackLabel(productionPrimary.qualification_track)", self.js)
        self.assertIn("全池结构化风险筛查通过当前规则；不等于官方确认不存在全部负面事件；本通道不要求正向催化深扫", self.js)
        self.assertIn("质量趋势通道不绑定正向事件", self.js)
        self.assertIn("生产规则资格模型 · V4", self.js)
        self.assertIn("事件催化轨", self.js)
        self.assertIn("推荐度 64 / 63 / 64", self.js)
        self.assertIn("Top 20% · 正向事件 ≥1 · RR ≥1.20", self.js)
        self.assertIn("质量趋势轨", self.js)
        self.assertIn("推荐度 64 / 67 / 67", self.js)
        self.assertIn("Top 10% · 数据质量 ≥95 · RR ≥1.50 · 资格分 ≥72", self.js)
        self.assertIn("A/H 上行≥6% 且下行≤6%", self.js)
        self.assertIn("US 上行≥6.5% 且下行≤7.5%", self.js)

    def test_v4_malformed_qualified_rows_fail_closed_at_browser_runtime(self) -> None:
        run_app_node(
            r"""
const clone = (value) => JSON.parse(JSON.stringify(value));
const scoreParts = ({ legacy, rank, universe, dataQuality, eventIds, low, high }) => {
  const v2Strength = (universe - rank + 1) / universe * 100;
  const eventStrength = eventIds.length ? Math.min(100, 80 + 5 * eventIds.length) : 0;
  const riskRewardStrength = Math.min(100, high / Math.abs(low) / 2 * 100);
  const round2 = (value) => Math.round((value + Number.EPSILON) * 100) / 100;
  const components = {
    legacy_recommendation: round2(legacy * 0.30),
    v2_rank_strength: round2(v2Strength * 0.30),
    data_quality: round2(dataQuality * 0.15),
    verified_event_evidence: round2(eventStrength * 0.15),
    risk_reward_scenario: round2(riskRewardStrength * 0.10),
  };
  return { components, score: round2(Object.values(components).reduce((total, value) => total + value, 0)) };
};
const makeRow = (track = "event_catalyst") => ({
  ...(() => {
    const eventIds = track === "event_catalyst" ? ["evt:audit"] : [];
    const { components, score } = scoreParts({
      legacy: 70, rank: 1, universe: 20, dataQuality: 100, eventIds, low: -4, high: 8,
    });
    return {
      qualification_score: score,
      score_components: components,
      verified_positive_event_ids: eventIds,
    };
  })(),
  qualification_id: "qual_0123456789abcdef01234567",
  market: "us",
  code: "AUDIT",
  name: "Audit Candidate",
  status: "QUALIFIED",
  qualification_track: track,
  rule_model_id: "ten-day-audited-rule-ensemble-v4",
  score_kind: "RULE_QUALIFICATION_SCORE",
  probability: null,
  probability_status: "NOT_APPLICABLE",
  calibrated: false,
  expected_net_utility: null,
  blocker_codes: [],
  legacy_signal: "BUY_CANDIDATE",
  legacy_recommendation_degree: 70,
  v2_rank: 1,
  v2_rank_universe_size: 20,
  v2_rank_fraction: 0.05,
  data_quality_score: 100,
  event_candidate_scanned: true,
  track_evaluations: track === "event_catalyst" ? [
    { track: "event_catalyst", status: "PASS", blocker_codes: [] },
    { track: "quality_technical", status: "PASS", blocker_codes: [] },
  ] : [
    { track: "event_catalyst", status: "FAIL", blocker_codes: ["VERIFIED_POSITIVE_EVENT_MISSING"] },
    { track: "quality_technical", status: "PASS", blocker_codes: [] },
  ],
  estimated_10d_range: { low_pct: -4, high_pct: 8, horizon_trade_days: 10 },
  risk_reward: { upside_pct: 8, downside_pct: 4, ratio: 2 },
  candidate_snapshot: { market: "us", code: "AUDIT", name: "Audit Candidate" },
});
const sourceForRow = (row) => ({
  market: row.market,
  code: row.code,
  name: row.name,
  blocker_codes: row.qualification_track === "quality_technical" ? ["VERIFIED_POSITIVE_EVENT_MISSING"] : [],
  legacy_signal: row.legacy_signal,
  legacy_recommendation_degree: row.legacy_recommendation_degree,
  v2_rank: row.v2_rank,
  v2_rank_universe_size: row.v2_rank_universe_size,
  priority_components: { data_quality: row.data_quality_score / 5 },
  event_candidate_scanned: row.event_candidate_scanned,
  verified_positive_event_ids: clone(row.verified_positive_event_ids),
  estimated_10d_range: {
    low_pct: row.estimated_10d_range.low_pct,
    high_pct: row.estimated_10d_range.high_pct,
  },
});
const inputForRow = (source, row, index = 0) => ({
  input_index: index,
  market: source.market,
  code: source.code,
  name: source.name,
  blocker_codes: clone(source.blocker_codes),
  legacy_signal: source.legacy_signal,
  legacy_recommendation_degree: source.legacy_recommendation_degree,
  v2_rank: source.v2_rank,
  v2_rank_universe_size: source.v2_rank_universe_size,
  priority_components: clone(source.priority_components),
  event_candidate_scanned: source.event_candidate_scanned,
  verified_positive_event_ids: clone(source.verified_positive_event_ids),
  estimated_10d_range: clone(source.estimated_10d_range),
  source_candidate_present: true,
  source_data_quality_score: row.data_quality_score,
  candidate_snapshot: clone(row.candidate_snapshot),
});
const makeSnapshot = (row, version = 4) => {
  const historicalModelVersions = {
    1: "smart-selector-2026-08-25.1-production-rule",
    2: "smart-selector-2026-08-26.1-candidate-rule",
    3: "smart-selector-2026-08-26.2-dual-track-rule",
  };
  const ledgerHash = "a".repeat(64);
  const decision = {
    contract_version: "production-rule-10d-v1",
    decision_scope: "global_10d_bounded_recall",
    action_basis: version === 4
      ? "dual_track_candidate_qualification_v4"
      : version === 3
        ? "dual_track_candidate_qualification_v3"
      : version === 2
        ? "candidate_level_rule_qualification_v2"
        : "strict_rule_qualification_v1",
    rule_model_id: version === 4
      ? "ten-day-audited-rule-ensemble-v4"
      : version === 3
        ? "ten-day-audited-rule-ensemble-v3"
      : version === 2
        ? "ten-day-audited-rule-ensemble-v2"
        : "ten-day-audited-rule-ensemble-v1",
    action: "QUALIFIED_PICK",
    score_kind: "RULE_QUALIFICATION_SCORE",
    probability: null,
    calibrated: false,
    qualified_candidate_count: 1,
    rejected_candidate_count: 0,
    evaluated_candidate_count: 1,
    primary: clone(row),
    qualified_candidates: [clone(row)],
    evaluated_candidates: [clone(row)],
    blocker_codes: [],
  };
  const snapshot = {
    model_version: version === 4
      ? "smart-selector-2026-08-29.1-two-tier-rule"
      : historicalModelVersions[version],
    markets: { a_share: { decision: {} }, hk: { decision: {} }, us: { decision: {} } },
    production_decision: decision,
  };
  if (version === 4) {
    const source = sourceForRow(row);
    snapshot.global_decision = { evaluated_candidates: [source] };
    snapshot.production_rule_inputs = {
      contract_version: "production-rule-inputs-v2",
      action_basis: "dual_track_candidate_qualification_v4",
      rule_model_id: "ten-day-audited-rule-ensemble-v4",
      evaluated_candidate_count: 1,
      rows: [inputForRow(source, row)],
      ledger_sha256: ledgerHash,
    };
    Object.assign(decision, {
      source_rule_inputs_contract_version: "production-rule-inputs-v2",
      source_rule_inputs_sha256: ledgerHash,
      source_rule_input_count: 1,
    });
  }
  return snapshot;
};
const assertRejected = (label, mutate) => {
  const snapshot = makeSnapshot(makeRow());
  mutate(snapshot.production_decision.primary);
  mutate(snapshot.production_decision.qualified_candidates[0]);
  mutate(snapshot.production_decision.evaluated_candidates[0]);
  assert.equal(productionQualifiedRows(snapshot).length, 0, `${label}: qualified rows`);
  assert.equal(productionDecisionTruth(snapshot).action, "NO_QUALIFIED_PICK", `${label}: decision`);
};

assertRejected("unknown track", (row) => { row.qualification_track = "unknown"; });
assertRejected("track order", (row) => { row.track_evaluations.reverse(); });
assertRejected("PASS with blockers", (row) => { row.track_evaluations[0].blocker_codes = ["IMPOSSIBLE_PASS_BLOCKER"]; });
assertRejected("FAIL without blockers", (row) => {
  row.track_evaluations[1] = { track: "quality_technical", status: "FAIL", blocker_codes: [] };
});
assertRejected("selected track not PASS", (row) => {
  row.track_evaluations[0] = { track: "event_catalyst", status: "FAIL", blocker_codes: ["EVENT_GATE_FAILED"] };
  row.track_evaluations[1] = { track: "quality_technical", status: "PASS", blocker_codes: [] };
});
assertRejected("event scan missing", (row) => { row.event_candidate_scanned = false; });
assertRejected("event catalyst evidence missing", (row) => { row.verified_positive_event_ids = []; });

const mixedSnapshot = makeSnapshot(makeRow());
mixedSnapshot.production_decision.primary.event_candidate_scanned = false;
assert.equal(productionQualifiedRows(mixedSnapshot).length, 0, "a valid duplicate must not launder a malformed V4 primary");
assert.equal(productionDecisionTruth(mixedSnapshot).action, "NO_QUALIFIED_PICK");

const evilPrimary = makeSnapshot(makeRow());
evilPrimary.production_decision.primary.name = "EVIL mirror";
evilPrimary.production_decision.primary.candidate_snapshot.name = "EVIL mirror";
assert.equal(productionQualifiedRows(evilPrimary).length, 0, "same-id EVIL primary mirror must not replace evaluated truth");

const evilQualifiedMirror = makeSnapshot(makeRow());
evilQualifiedMirror.production_decision.qualified_candidates[0].score_components.data_quality = 99;
assert.equal(productionQualifiedRows(evilQualifiedMirror).length, 0, "nested EVIL qualified mirror must fail full normalized JSON equality");

const forgedQuality = makeSnapshot(makeRow("quality_technical"));
forgedQuality.global_decision.evaluated_candidates[0].legacy_recommendation_degree = 64;
forgedQuality.production_rule_inputs.rows[0].legacy_recommendation_degree = 64;
assert.equal(productionQualifiedRows(forgedQuality).length, 0, "forged quality PASS below the US Legacy 67 gate must be rejected");

const sharedBlockerBypass = makeSnapshot(makeRow("quality_technical"));
sharedBlockerBypass.global_decision.evaluated_candidates[0].blocker_codes.push("MATERIAL_NEGATIVE_EVENT");
sharedBlockerBypass.production_rule_inputs.rows[0].blocker_codes.push("MATERIAL_NEGATIVE_EVENT");
assert.equal(productionQualifiedRows(sharedBlockerBypass).length, 0, "quality track must not waive a shared safety blocker");

const qualitySnapshot = makeSnapshot(makeRow("quality_technical"));
assert.equal(productionQualifiedRows(qualitySnapshot).length, 1, "valid quality row remains accepted without positive events");
state.snapshot = qualitySnapshot;
state.status = null;
assert.equal(userDecisionState(qualitySnapshot), "ENTER_TRADE_REVIEW", "only the current V4 pair can enter review");

const qualityWithoutDeepScan = makeSnapshot(makeRow("quality_technical"));
qualityWithoutDeepScan.global_decision.evaluated_candidates[0].blocker_codes.push("EVENT_CANDIDATE_NOT_SCANNED");
qualityWithoutDeepScan.global_decision.evaluated_candidates[0].event_candidate_scanned = false;
qualityWithoutDeepScan.production_rule_inputs.rows[0].blocker_codes.push("EVENT_CANDIDATE_NOT_SCANNED");
qualityWithoutDeepScan.production_rule_inputs.rows[0].event_candidate_scanned = false;
for (const row of [
  qualityWithoutDeepScan.production_decision.primary,
  qualityWithoutDeepScan.production_decision.qualified_candidates[0],
  qualityWithoutDeepScan.production_decision.evaluated_candidates[0],
]) {
  row.event_candidate_scanned = false;
  row.track_evaluations[0].blocker_codes = ["VERIFIED_POSITIVE_EVENT_MISSING", "EVENT_CANDIDATE_NOT_SCANNED"];
}
assert.equal(
  productionQualifiedRows(qualityWithoutDeepScan).length,
  1,
  "quality track remains valid without bounded positive-event deep scan",
);

const downgradedV4 = makeSnapshot(makeRow("quality_technical"));
downgradedV4.model_version = "smart-selector-2026-08-26.2-dual-track-rule";
assert.equal(productionQualifiedRows(downgradedV4).length, 0, "V4 cannot bypass strict checks under an older model_version");

const unknownHistorical = makeSnapshot(makeRow());
unknownHistorical.model_version = "archived-production-rule-v3";
assert.equal(productionQualifiedRows(unknownHistorical).length, 0, "unknown historical versions fail closed");

const bothPassWrongSelection = makeSnapshot(makeRow());
for (const row of [
  bothPassWrongSelection.production_decision.primary,
  bothPassWrongSelection.production_decision.qualified_candidates[0],
  bothPassWrongSelection.production_decision.evaluated_candidates[0],
]) row.qualification_track = "quality_technical";
assert.equal(productionQualifiedRows(bothPassWrongSelection).length, 0, "event track must win when both tracks truly PASS");

const highRow = makeRow();
highRow.code = "HIGH";
highRow.name = "Higher Score";
highRow.qualification_id = "qual_111111111111111111111111";
highRow.candidate_snapshot.code = highRow.code;
highRow.candidate_snapshot.name = highRow.name;
const lowRow = makeRow("quality_technical");
lowRow.code = "LOW";
lowRow.name = "Lower Score";
lowRow.qualification_id = "qual_222222222222222222222222";
lowRow.candidate_snapshot.code = lowRow.code;
lowRow.candidate_snapshot.name = lowRow.name;
const highSource = sourceForRow(highRow);
const lowSource = sourceForRow(lowRow);
const forgedOrder = makeSnapshot(highRow);
forgedOrder.global_decision.evaluated_candidates = [highSource, lowSource];
forgedOrder.production_rule_inputs.rows = [
  inputForRow(highSource, highRow, 0),
  inputForRow(lowSource, lowRow, 1),
];
forgedOrder.production_rule_inputs.evaluated_candidate_count = 2;
forgedOrder.production_decision.source_rule_input_count = 2;
forgedOrder.production_decision.evaluated_candidate_count = 2;
forgedOrder.production_decision.qualified_candidate_count = 2;
forgedOrder.production_decision.rejected_candidate_count = 0;
forgedOrder.production_decision.evaluated_candidates = [clone(lowRow), clone(highRow)];
forgedOrder.production_decision.qualified_candidates = [clone(lowRow), clone(highRow)];
forgedOrder.production_decision.primary = clone(lowRow);
assert.equal(productionQualifiedRows(forgedOrder).length, 0, "a lower score cannot become primary by reordering every published mirror");
assert.equal(productionDecisionTruth(forgedOrder).action, "NO_QUALIFIED_PICK", "reordered V4 primary must fail closed");

const archivedV3Row = makeRow();
archivedV3Row.rule_model_id = "ten-day-audited-rule-ensemble-v3";
const archivedV3Snapshot = makeSnapshot(archivedV3Row, 3);
assert.equal(productionQualifiedRows(archivedV3Snapshot).length, 1, "archived V3 remains readable");
assert.equal(productionDecisionTruth(archivedV3Snapshot).action, "HISTORICAL_ONLY", "archived V3 never becomes current");
state.snapshot = archivedV3Snapshot;
state.status = null;
assert.equal(candidateDecisionRole(archivedV3Row.candidate_snapshot, "us"), "historical_qualified");
assert.equal(userDecisionState(archivedV3Snapshot), "NO_ACTION", "archived V3 is read-only");

const archivedV2Row = makeRow();
archivedV2Row.rule_model_id = "ten-day-audited-rule-ensemble-v2";
delete archivedV2Row.qualification_track;
delete archivedV2Row.track_evaluations;
delete archivedV2Row.event_candidate_scanned;
delete archivedV2Row.verified_positive_event_ids;
assert.equal(productionQualifiedRows(makeSnapshot(archivedV2Row, 2)).length, 1, "archived V2 remains compatible");
const currentVersionWithV2 = makeSnapshot(archivedV2Row, 2);
currentVersionWithV2.model_version = "smart-selector-2026-08-29.1-two-tier-rule";
assert.equal(productionQualifiedRows(currentVersionWithV2).length, 0, "current model_version cannot publish a V2 decision");

const archivedV1Row = clone(archivedV2Row);
archivedV1Row.rule_model_id = "ten-day-audited-rule-ensemble-v1";
assert.equal(productionQualifiedRows(makeSnapshot(archivedV1Row, 1)).length, 1, "archived V1 remains compatible");
"""
        )

    def test_event_tab_audits_every_v4_qualified_candidate_without_promoting_secondaries(self) -> None:
        run_app_node(
            r"""
const candidate = (market, code, name, track, score, eventIds = []) => ({
  ...(() => {
    const legacy = score;
    const round2 = (value) => Math.round((value + Number.EPSILON) * 100) / 100;
    const eventStrength = eventIds.length ? Math.min(100, 80 + 5 * eventIds.length) : 0;
    const components = {
      legacy_recommendation: round2(legacy * 0.30),
      v2_rank_strength: 30,
      data_quality: 15,
      verified_event_evidence: round2(eventStrength * 0.15),
      risk_reward_scenario: 10,
    };
    return {
      qualification_score: round2(Object.values(components).reduce((total, value) => total + value, 0)),
      score_components: components,
    };
  })(),
  qualification_id: `qual_${code.toLowerCase().replace(/[^a-f0-9]/g, "a").padEnd(24, "0").slice(0, 24)}`,
  market,
  code,
  name,
  status: "QUALIFIED",
  qualification_track: track,
  rule_model_id: "ten-day-audited-rule-ensemble-v4",
  score_kind: "RULE_QUALIFICATION_SCORE",
  probability: null,
  probability_status: "NOT_APPLICABLE",
  calibrated: false,
  expected_net_utility: null,
  blocker_codes: [],
  legacy_signal: "BUY_CANDIDATE",
  legacy_recommendation_degree: score,
  v2_rank: 1,
  v2_rank_universe_size: 20,
  v2_rank_fraction: 0.05,
  data_quality_score: 100,
  event_candidate_scanned: true,
  verified_positive_event_ids: eventIds,
  track_evaluations: [
    {
      track: "event_catalyst",
      status: track === "event_catalyst" ? "PASS" : "FAIL",
      blocker_codes: track === "event_catalyst" ? [] : ["VERIFIED_POSITIVE_EVENT_MISSING"],
    },
    { track: "quality_technical", status: "PASS", blocker_codes: [] },
  ],
  estimated_10d_range: { low_pct: -4, high_pct: 8, horizon_trade_days: 10 },
  risk_reward: { upside_pct: 8, downside_pct: 4, ratio: 2 },
  candidate_snapshot: { market, code, name },
});
const midea = candidate("hk", "0300.HK", "美的集团", "event_catalyst", 70, ["evt:midea"]);
const vz = candidate("us", "VZ", "威瑞森通讯(Verizon)", "quality_technical", 71);
const pfe = candidate("us", "PFE", "辉瑞", "quality_technical", 72);
const qualified = [midea, pfe, vz];
const sources = qualified.map((row) => ({
  market: row.market,
  code: row.code,
  name: row.name,
  blocker_codes: row.qualification_track === "quality_technical" ? ["VERIFIED_POSITIVE_EVENT_MISSING"] : [],
  legacy_signal: row.legacy_signal,
  legacy_recommendation_degree: row.legacy_recommendation_degree,
  v2_rank: row.v2_rank,
  v2_rank_universe_size: row.v2_rank_universe_size,
  priority_components: { data_quality: 20 },
  event_candidate_scanned: true,
  verified_positive_event_ids: [...row.verified_positive_event_ids],
  estimated_10d_range: { low_pct: -4, high_pct: 8 },
}));
const inputRows = sources.map((source, index) => ({
  input_index: index,
  market: source.market,
  code: source.code,
  name: source.name,
  blocker_codes: [...source.blocker_codes],
  legacy_signal: source.legacy_signal,
  legacy_recommendation_degree: source.legacy_recommendation_degree,
  v2_rank: source.v2_rank,
  v2_rank_universe_size: source.v2_rank_universe_size,
  priority_components: { ...source.priority_components },
  event_candidate_scanned: source.event_candidate_scanned,
  verified_positive_event_ids: [...source.verified_positive_event_ids],
  estimated_10d_range: { ...source.estimated_10d_range },
  source_candidate_present: true,
  source_data_quality_score: 100,
  candidate_snapshot: { ...qualified[index].candidate_snapshot },
}));
const ledgerHash = "b".repeat(64);
state.snapshot = {
  model_version: "smart-selector-2026-08-29.1-two-tier-rule",
  generated_at: "2026-08-26T08:00:00+08:00",
  target_date: "2026-08-26",
  forecast_end_date: "2026-09-08",
  markets: { a_share: { decision: {} }, hk: { decision: {} }, us: { decision: {} } },
  global_decision: { evaluated_candidates: sources },
  production_rule_inputs: {
    contract_version: "production-rule-inputs-v2",
    action_basis: "dual_track_candidate_qualification_v4",
    rule_model_id: "ten-day-audited-rule-ensemble-v4",
    evaluated_candidate_count: 3,
    rows: inputRows,
    ledger_sha256: ledgerHash,
  },
  events: { items: [{
    event_id: "evt:midea",
    event_type: "announcement",
    market: "hk",
    symbol: "0300.HK",
    company: "美的集团",
    title: "美的集团官方公告",
    source: "HKEXnews",
    url: "https://example.test/midea",
    published_at: "2026-08-25T18:00:00+08:00",
    effective_at: "2026-08-26T09:00:00+08:00",
    decision_eligible: true,
    ingestion_mode: "automatic",
    evidence_status: "verified",
    source_tier: "official",
    direction: "positive",
  }] },
  production_decision: {
    contract_version: "production-rule-10d-v1",
    decision_scope: "global_10d_bounded_recall",
    action_basis: "dual_track_candidate_qualification_v4",
    rule_model_id: "ten-day-audited-rule-ensemble-v4",
    action: "QUALIFIED_PICK",
    score_kind: "RULE_QUALIFICATION_SCORE",
    probability: null,
    calibrated: false,
    qualified_candidate_count: 3,
    primary: midea,
    qualified_candidates: qualified,
    evaluated_candidates: qualified,
    evaluated_candidate_count: 3,
    rejected_candidate_count: 0,
    source_rule_inputs_contract_version: "production-rule-inputs-v2",
    source_rule_inputs_sha256: ledgerHash,
    source_rule_input_count: 3,
    blocker_codes: [],
  },
};

const boundEvidence = state.snapshot.events.items[0];
state.snapshot.decision_evidence = {
  bound_event_ids: [boundEvidence.event_id],
  bound_event_count: 1,
  items: [boundEvidence],
};
delete state.snapshot.events;
state.eventsPayload = {
  events: [{
    ...boundEvidence,
    event_id: "evt:newer-unbound",
    symbol: "0700.HK",
    company: "腾讯",
    title: "首屏非绑定事件",
    decision_bound: false,
  }],
  total: 485,
  event_publication: {
    total: 485, published: 485, truncated: 0,
    decision_bound_event_ids: [boundEvidence.event_id],
    decision_bound_event_count: 1,
  },
};
assert.deepEqual(
  publishedEventItems().map((event) => event.event_id),
  ["evt:midea", "evt:newer-unbound"],
  "bootstrap-bound evidence must survive a lazy first page without that id",
);

renderEvents();
const html = __roots.get("#eventsView").innerHTML;
for (const text of [
  "美的集团", "威瑞森通讯(Verizon)", "辉瑞",
  "规则资格分 88.8", "规则资格分 76.3", "规则资格分 76.6",
  "事件催化合格", "质量趋势合格", "evt:midea",
  "1 / 1", "已解析 1 / 1 个绑定 event_id",
]) assert.ok(html.includes(text), `missing event audit text: ${text}`);
assert.equal((html.match(/全池结构化风险筛查通过当前规则；不等于官方确认不存在全部负面事件；本通道不要求正向催化深扫/g) || []).length, 2);
assert.equal((html.match(/合格候选（非主候选）/g) || []).length, 2);
assert.equal((html.match(/主候选 ·/g) || []).length, 1);
assert.equal(productionDecisionTruth().primary.code, "0300.HK", "secondary audit must not replace primary");
"""
        )

    def test_current_vz_pfe_snapshot_keeps_two_qualified_rows_and_vz_primary(self) -> None:
        run_app_node(
            r"""
const clone = (value) => JSON.parse(JSON.stringify(value));
const source = (code, name, legacy, rank, low, high, scanned = true, market = "us", universe = 299) => ({
  market,
  code,
  name,
  blocker_codes: [
    ...(scanned ? [] : ["EVENT_CANDIDATE_NOT_SCANNED"]),
    "VERIFIED_POSITIVE_EVENT_MISSING",
    "TEN_DAY_MODEL_NOT_READY",
    "TEN_DAY_PREDICTION_MISSING",
  ],
  legacy_signal: "BUY_CANDIDATE",
  legacy_recommendation_degree: legacy,
  v2_rank: rank,
  v2_rank_universe_size: universe,
  priority_components: { data_quality: 20 },
  event_candidate_scanned: scanned,
  verified_positive_event_ids: [],
  estimated_10d_range: { low_pct: low, high_pct: high },
});
const sources = [
  source("VZ", "威瑞森通讯(Verizon)", 71, 7, -4.2, 7.3),
  source("PFE", "辉瑞", 70, 16, -4.6, 7.9),
  source("3968.HK", "招商银行", 62, 22, -4, 5.7, true, "hk", 199),
  source("DASH", "DoorDash Inc-A", 53, 5, -6.3, 8.9, false),
  source("SHEL", "壳牌", 35, 91, -8, 7.4, false),
];
const inputs = sources.map((item, index) => ({
  input_index: index,
  market: item.market,
  code: item.code,
  name: item.name,
  blocker_codes: clone(item.blocker_codes),
  legacy_signal: item.legacy_signal,
  legacy_recommendation_degree: item.legacy_recommendation_degree,
  v2_rank: item.v2_rank,
  v2_rank_universe_size: item.v2_rank_universe_size,
  priority_components: clone(item.priority_components),
  event_candidate_scanned: item.event_candidate_scanned,
  verified_positive_event_ids: [],
  estimated_10d_range: clone(item.estimated_10d_range),
  source_candidate_present: true,
  source_data_quality_score: 100,
}));
const publishedRow = (sourceRow, input, qualificationId) => {
  const expected = expectedCurrentQualification(sourceRow, input);
  const row = {
    market: expected.market,
    code: expected.code,
    name: expected.name,
    status: expected.qualificationTrack ? "QUALIFIED" : "REJECTED",
    qualification_track: expected.qualificationTrack,
    track_evaluations: clone(expected.trackEvaluations),
    rule_model_id: "ten-day-audited-rule-ensemble-v4",
    score_kind: "RULE_QUALIFICATION_SCORE",
    qualification_score: expected.score,
    score_components: clone(expected.components),
    probability: null,
    probability_status: "NOT_APPLICABLE",
    calibrated: false,
    expected_net_utility: null,
    legacy_signal: expected.legacySignal,
    legacy_recommendation_degree: expected.legacy,
    v2_rank: expected.rank,
    v2_rank_universe_size: expected.universe,
    v2_rank_fraction: expected.rankFraction,
    data_quality_score: expected.dataQuality,
    event_candidate_scanned: expected.eventScanned,
    verified_positive_event_ids: clone(expected.eventIds),
    estimated_10d_range: { low_pct: expected.low, high_pct: expected.high, horizon_trade_days: 10 },
    risk_reward: { upside_pct: expected.high, downside_pct: expected.downside, ratio: expected.ratio },
    blocker_codes: clone(expected.blockerCodes),
  };
  if (expected.qualificationTrack) {
    row.qualification_id = qualificationId;
    row.candidate_snapshot = { market: sourceRow.market, code: sourceRow.code, name: sourceRow.name };
    input.candidate_snapshot = clone(row.candidate_snapshot);
  }
  return row;
};
const vz = publishedRow(sources[0], inputs[0], "qual_111111111111111111111111");
const pfe = publishedRow(sources[1], inputs[1], "qual_222222222222222222222222");
const cmb = publishedRow(sources[2], inputs[2]);
const dash = publishedRow(sources[3], inputs[3]);
const shell = publishedRow(sources[4], inputs[4]);
// Python round(4.625, 2) uses ties-to-even while Math.round does not.  The
// published ledger remains authoritative within the contract's 0.01 tolerance.
shell.score_components.risk_reward_scenario = 4.62;
shell.qualification_score = 51.09;
cmb.score_components.risk_reward_scenario = 7.12;
cmb.qualification_score = 67.55;
const ledgerHash = "c".repeat(64);
const decision = {
  contract_version: "production-rule-10d-v1",
  decision_scope: "global_10d_bounded_recall",
  action_basis: "dual_track_candidate_qualification_v4",
  rule_model_id: "ten-day-audited-rule-ensemble-v4",
  action: "QUALIFIED_PICK",
  score_kind: "RULE_QUALIFICATION_SCORE",
  probability: null,
  calibrated: false,
  evaluated_candidate_count: 5,
  qualified_candidate_count: 2,
  rejected_candidate_count: 3,
  primary: clone(vz),
  qualified_candidates: [clone(vz), clone(pfe)],
  evaluated_candidates: [clone(vz), clone(pfe), clone(dash), clone(cmb), clone(shell)],
  source_rule_inputs_contract_version: "production-rule-inputs-v2",
  source_rule_inputs_sha256: ledgerHash,
  source_rule_input_count: 5,
  blocker_codes: [],
};
const snapshot = {
  model_version: "smart-selector-2026-08-29.1-two-tier-rule",
  markets: { a_share: { decision: {} }, hk: { decision: {} }, us: { decision: {} } },
  global_decision: { evaluated_candidates: sources },
  production_rule_inputs: {
    contract_version: "production-rule-inputs-v2",
    action_basis: "dual_track_candidate_qualification_v4",
    rule_model_id: "ten-day-audited-rule-ensemble-v4",
    evaluated_candidate_count: 5,
    rows: inputs,
    ledger_sha256: ledgerHash,
  },
  production_decision: decision,
};

const rows = productionQualifiedRows(snapshot);
const truth = productionDecisionTruth(snapshot);
assert.deepEqual(
  deterministicCurrentOrder(currentRuleInputContext(snapshot, decision), decision.evaluated_candidates)
    .map((row) => row.code),
  ["VZ", "PFE", "DASH", "3968.HK", "SHEL"],
  "published Python-rounded scores remain the deterministic order key",
);
assert.deepEqual(rows.map((row) => row.code), ["VZ", "PFE"]);
assert.equal(truth.action, "QUALIFIED_PICK");
assert.equal(truth.qualifiedCount, 2);
assert.equal(truth.primary.code, "VZ");
assert.equal(truth.qualified.candidate.code, "VZ");
assert.deepEqual(truth.blockerCodes, []);

const forged = clone(snapshot);
forged.production_decision.primary.score_components.data_quality += 0.02;
forged.production_decision.qualified_candidates[0].score_components.data_quality += 0.02;
forged.production_decision.evaluated_candidates[0].score_components.data_quality += 0.02;
assert.equal(productionQualifiedRows(forged).length, 0, "component changes beyond one cent still fail closed");

assert.equal(normalizeCandidateCode("a_share", "SH.600000"), "600000");
assert.equal(normalizeCandidateCode("a_share", "600000.SH"), "600000");
assert.equal(normalizeCandidateCode("hk", "00700"), "0700.HK");
assert.equal(normalizeCandidateCode("hk", "0700.HK"), "0700.HK");
assert.equal(normalizeCandidateCode("us", "BRK.B"), "BRK-B");
assert.equal(normalizeCandidateCode("us", "BRK_B"), "BRK-B");
assert.equal(candidateId({ code: "BRK.B" }, "us"), candidateId({ symbol: "BRK_B" }, "us"));
"""
        )

    def test_manual_evidence_never_becomes_automatic_evidence(self) -> None:
        self.assertIn("MANUAL_RESEARCH_EVIDENCE", self.js)
        self.assertIn("manual_verified_pending_ingestion", self.js)
        self.assertIn('event.event_type === "manual_external"', self.js)
        self.assertIn("不参与自动买入门禁", self.js)
        self.assertIn('String(event.url || "").startsWith("https://")', self.js)
        self.assertIn("published >= generated - 45 * 24 * 60 * 60 * 1000", self.js)
        self.assertIn("effective >= windowStart", self.js)
        self.assertIn("effective <= windowEnd", self.js)

    def test_event_audit_remains_open_during_filtering(self) -> None:
        self.assertIn("eventAuditOpen: false", self.js)
        self.assertIn("state.eventAuditOpen = currentAudit.open", self.js)
        self.assertIn('state.eventAuditOpen ? "open" : ""', self.js)

    def test_history_is_explicitly_not_ready(self) -> None:
        self.assertIn("historyMeta", self.js)
        self.assertIn("historyError", self.js)
        self.assertIn("HISTORY_DATA_UNAVAILABLE", self.js)
        self.assertIn("getHistoryPayload", self.js)
        self.assertIn("HISTORY_LIMIT = 120", self.js)
        self.assertIn("暂无已结算的可执行预测样本", self.js)
        self.assertIn("原始运行", self.js)
        self.assertIn("决策日", self.js)
        self.assertIn("Legacy 历史日", self.js)
        self.assertIn("已结算样本", self.js)
        self.assertIn("真实合同指标 · 非浏览器回填 · 非模拟收益", self.js)
        self.assertIn("historyArchiveOpen", self.js)
        self.assertIn("state.historyArchiveOpen = currentArchive.open", self.js)
        self.assertIn("return item.a_share_legacy || {}", self.js)
        self.assertIn("state.historySnapshotKey === itemKey", self.js)
        self.assertIn("信号日", self.js)
        self.assertIn("计划执行日", self.js)
        self.assertIn("Legacy 归档日", self.js)
        self.assertIn("正式十日预测", self.js)
        self.assertIn("prediction_id", self.js)
        self.assertNotIn("空白代表尚未有可靠评估", self.js)

    def test_observation_performance_is_rendered_as_diagnostic_only(self) -> None:
        for field in (
            "observation_performance",
            "pending_maturity_count",
            "pending_data_count",
            "settled_count",
            "authorization_status",
            "included_in_executable_performance",
            "authorizes_production",
        ):
            self.assertIn(field, self.js)
        self.assertIn("不进入正式绩效", self.js)
        self.assertIn("不授权生产", self.js)
        self.assertNotIn("NOT IMPLEMENTED", self.js)
        self.assertNotIn("当前只负责积累点时预测", self.js)
        run_app_node(
            r"""
const html = renderObservationLedgerPanel(
  {
    track: "MODEL_OBSERVATION",
    status: "OBSERVING",
    cohort_count: 4,
    revision_count: 6,
    canonical_prediction_count: 31,
    market_prediction_counts: { a_share: 11, hk: 9, us: 11 },
  },
  {
    schema_version: "model-observation-performance-v1",
    track: "MODEL_OBSERVATION",
    status: "PENDING_MATURITY",
    cohort_count: 4,
    prediction_count: 31,
    pending_maturity_count: 17,
    pending_data_count: 3,
    settled_count: 11,
    independent_cohort_day_count: 2,
    minimum_reliable_independent_cohort_days: 20,
    untracked_count: 0,
    invalid_cohort_count: 0,
    invalid_batch_count: 0,
    invalid_outcome_count: 0,
    market_coverage: {},
    metrics: {},
    included_in_shadow_research: false,
    included_in_executable_performance: false,
    authorizes_production: false,
    authorization_status: "DIAGNOSTIC_ONLY_MANUAL_REVIEW_REQUIRED",
  },
);
assert.match(html, /PENDING_MATURITY/);
assert.match(html, /PENDING_DATA/);
assert.match(html, /SETTLED/);
assert.match(html, />17</);
assert.match(html, />3</);
assert.match(html, />11</);
assert.match(html, /DIAGNOSTIC_ONLY_MANUAL_REVIEW_REQUIRED/);
assert.match(html, /不进入正式绩效/);
assert.match(html, /不授权生产/);
assert.doesNotMatch(html, /NOT IMPLEMENTED/);
"""
        )

    def test_old_full_history_assets_have_an_explicit_retention_message(self) -> None:
        self.assertIn("item.full_snapshot_available === false", self.js)
        self.assertIn("完整交互快照仅保留最近 30 个决策日", self.js)


if __name__ == "__main__":
    unittest.main()

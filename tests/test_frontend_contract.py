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
  }},
  location: {{ hash: "", origin: "https://xuangu.test" }},
  URL,
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

    def test_frontend_uses_published_cloud_snapshot_only(self) -> None:
        self.assertIn('getJson("/api/latest")', self.js)
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
        self.assertIn("下次计划检查点（含健康补跑）", self.html + self.js)
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
        self.assertIn('getJson("/api/latest")', self.js)
        self.assertIn("getHistoryPayload()", self.js)
        self.assertIn("window.setInterval(pollStatus, STATUS_POLL_INTERVAL_MS)", self.js)
        for label in ("计划批次已发布", "等待计划批次", "计划批次已过期", "状态未知"):
            self.assertIn(label, self.js)

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
        self.assertIn('decision.action_basis === "strict_rule_qualification_v1"', self.js)
        self.assertIn('decision.rule_model_id === "ten-day-audited-rule-ensemble-v1"', self.js)
        self.assertIn('decision.action_basis === "candidate_level_rule_qualification_v2"', self.js)
        self.assertIn('decision.rule_model_id === "ten-day-audited-rule-ensemble-v2"', self.js)
        self.assertIn('["QUALIFIED_PICK", "NO_QUALIFIED_PICK"].includes(String(decision.action || ""))', self.js)
        self.assertIn('decision.score_kind === "RULE_QUALIFICATION_SCORE"', self.js)
        self.assertIn("decision.probability === null", self.js)
        self.assertIn("decision.calibrated === false", self.js)
        self.assertIn("serverPrimary?.qualification_score", self.js)
        self.assertIn('action: qualified ? "QUALIFIED_PICK" : "NO_QUALIFIED_PICK"', self.js)
        self.assertIn("const selected = production.qualified;", self.js)
        self.assertIn("浏览器绝不把它们自行升级为 QUALIFIED_PICK", self.js)
        self.assertIn("规则资格分（非概率）", self.js)
        self.assertIn("生产规则模型已有合格候选", self.js)
        self.assertIn("规则合格 ${fmt(production.qualifiedCount, 0)} · 校准可执行", self.js)
        self.assertIn("productionQualificationForCandidate", self.js)
        self.assertIn("decision.qualified_candidates", self.js)
        self.assertIn("qualifiedCount: qualified ? qualifiedRows.length : 0", self.js)
        self.assertIn("publishedCount !== rows.length", self.js)
        self.assertIn("productionQualifiedRows(state.snapshot, market).some", self.js)
        self.assertIn("const rolePriority = { qualified: 0", self.js)
        self.assertIn("syncPreferredCandidate({ revealQualified: true })", self.js)
        self.assertIn("productionPrimary.rule_model_id || item.production_decision?.rule_model_id", self.js)
        self.assertIn("全局校准模型结论", self.js)
        self.assertIn("生产规则资格模型 · V3", self.js)
        self.assertIn("推荐度 64 / 63 / 64", self.js)
        self.assertIn("规则资格轨已通过", self.js)
        self.assertIn("规则轨 ${esc(production.action)} · 校准轨", self.js)
        self.assertIn("只有通过校准合同的 global_decision 才能展示上涨概率", self.js)
        self.assertIn("calibrated-track-card", self.css)
        self.assertNotRegex(self.js, r"ratioPct\([^\n)]*qualification_score")
        self.assertNotRegex(self.js, r"qualification_score\s*/\s*100")
        self.assertNotRegex(self.js, r"pct\([^\n)]*qualification_score")

    def test_v3_dual_track_qualification_is_named_without_inventing_event_evidence(self) -> None:
        self.assertIn('decision.action_basis === "dual_track_candidate_qualification_v3"', self.js)
        self.assertIn('decision.rule_model_id === "ten-day-audited-rule-ensemble-v3"', self.js)
        self.assertRegex(self.js, r"function qualificationTrackLabel\(track\)")
        self.assertIn('event_catalyst: "事件催化合格"', self.js)
        self.assertIn('quality_technical: "质量趋势合格"', self.js)
        self.assertIn("qualificationTrackLabel(primary.qualification_track)", self.js)
        self.assertIn("qualificationTrackLabel(qualification.qualification_track)", self.js)
        self.assertIn("qualificationTrackLabel(production.primary.qualification_track)", self.js)
        self.assertIn("qualificationTrackLabel(productionPrimary.qualification_track)", self.js)
        self.assertIn("已完成事件扫描且未发现重大负面；本通道不要求正向催化", self.js)
        self.assertIn("质量趋势通道不绑定正向事件", self.js)
        self.assertIn("生产规则资格模型 · V3", self.js)
        self.assertIn("事件催化轨", self.js)
        self.assertIn("推荐度 64 / 63 / 64", self.js)
        self.assertIn("Top 20% · 正向事件 ≥1 · RR ≥1.20", self.js)
        self.assertIn("质量趋势轨", self.js)
        self.assertIn("推荐度 66 / 67 / 68", self.js)
        self.assertIn("Top 10% · 数据质量 ≥95 · RR ≥1.50 · 资格分 ≥72", self.js)
        self.assertIn("A/H 上行≥6% 且下行≤6%", self.js)
        self.assertIn("US 上行≥6.5% 且下行≤7.5%", self.js)

    def test_v3_malformed_qualified_rows_fail_closed_at_browser_runtime(self) -> None:
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
  rule_model_id: "ten-day-audited-rule-ensemble-v3",
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
const makeSnapshot = (row, version = 3) => {
  const ledgerHash = "a".repeat(64);
  const decision = {
    contract_version: "production-rule-10d-v1",
    decision_scope: "global_10d_bounded_recall",
    action_basis: version === 3
      ? "dual_track_candidate_qualification_v3"
      : version === 2
        ? "candidate_level_rule_qualification_v2"
        : "strict_rule_qualification_v1",
    rule_model_id: version === 3
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
    model_version: version === 3
      ? "smart-selector-2026-08-26.2-dual-track-rule"
      : `archived-production-rule-v${version}`,
    markets: { a_share: { decision: {} }, hk: { decision: {} }, us: { decision: {} } },
    production_decision: decision,
  };
  if (version === 3) {
    const source = sourceForRow(row);
    snapshot.global_decision = { evaluated_candidates: [source] };
    snapshot.production_rule_inputs = {
      contract_version: "production-rule-inputs-v1",
      action_basis: "dual_track_candidate_qualification_v3",
      rule_model_id: "ten-day-audited-rule-ensemble-v3",
      evaluated_candidate_count: 1,
      rows: [inputForRow(source, row)],
      ledger_sha256: ledgerHash,
    };
    Object.assign(decision, {
      source_rule_inputs_contract_version: "production-rule-inputs-v1",
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
assert.equal(productionQualifiedRows(mixedSnapshot).length, 0, "a valid duplicate must not launder a malformed V3 primary");
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
assert.equal(productionQualifiedRows(forgedQuality).length, 0, "forged quality PASS below the US Legacy 68 gate must be rejected");

const sharedBlockerBypass = makeSnapshot(makeRow("quality_technical"));
sharedBlockerBypass.global_decision.evaluated_candidates[0].blocker_codes.push("MATERIAL_NEGATIVE_EVENT");
sharedBlockerBypass.production_rule_inputs.rows[0].blocker_codes.push("MATERIAL_NEGATIVE_EVENT");
assert.equal(productionQualifiedRows(sharedBlockerBypass).length, 0, "quality track must not waive a shared safety blocker");

const qualitySnapshot = makeSnapshot(makeRow("quality_technical"));
assert.equal(productionQualifiedRows(qualitySnapshot).length, 1, "valid quality row remains accepted without positive events");

const downgradedV3 = makeSnapshot(makeRow("quality_technical"));
downgradedV3.model_version = "archived-production-rule-v2";
assert.equal(productionQualifiedRows(downgradedV3).length, 0, "V3 cannot bypass strict checks under an older model_version");

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
assert.equal(productionDecisionTruth(forgedOrder).action, "NO_QUALIFIED_PICK", "reordered V3 primary must fail closed");

const archivedV2Row = makeRow();
archivedV2Row.rule_model_id = "ten-day-audited-rule-ensemble-v2";
delete archivedV2Row.qualification_track;
delete archivedV2Row.track_evaluations;
delete archivedV2Row.event_candidate_scanned;
delete archivedV2Row.verified_positive_event_ids;
assert.equal(productionQualifiedRows(makeSnapshot(archivedV2Row, 2)).length, 1, "archived V2 remains compatible");
const currentVersionWithV2 = makeSnapshot(archivedV2Row, 2);
currentVersionWithV2.model_version = "smart-selector-2026-08-26.2-dual-track-rule";
assert.equal(productionQualifiedRows(currentVersionWithV2).length, 0, "current model_version cannot publish a V2 decision");

const archivedV1Row = clone(archivedV2Row);
archivedV1Row.rule_model_id = "ten-day-audited-rule-ensemble-v1";
assert.equal(productionQualifiedRows(makeSnapshot(archivedV1Row, 1)).length, 1, "archived V1 remains compatible");
"""
        )

    def test_event_tab_audits_every_v3_qualified_candidate_without_promoting_secondaries(self) -> None:
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
  rule_model_id: "ten-day-audited-rule-ensemble-v3",
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
  model_version: "smart-selector-2026-08-26.2-dual-track-rule",
  generated_at: "2026-08-26T08:00:00+08:00",
  target_date: "2026-08-26",
  forecast_end_date: "2026-09-08",
  markets: { a_share: { decision: {} }, hk: { decision: {} }, us: { decision: {} } },
  global_decision: { evaluated_candidates: sources },
  production_rule_inputs: {
    contract_version: "production-rule-inputs-v1",
    action_basis: "dual_track_candidate_qualification_v3",
    rule_model_id: "ten-day-audited-rule-ensemble-v3",
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
    action_basis: "dual_track_candidate_qualification_v3",
    rule_model_id: "ten-day-audited-rule-ensemble-v3",
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
    source_rule_inputs_contract_version: "production-rule-inputs-v1",
    source_rule_inputs_sha256: ledgerHash,
    source_rule_input_count: 3,
    blocker_codes: [],
  },
};

renderEvents();
const html = __roots.get("#eventsView").innerHTML;
for (const text of [
  "美的集团", "威瑞森通讯(Verizon)", "辉瑞",
  "规则资格分 88.8", "规则资格分 76.3", "规则资格分 76.6",
  "事件催化合格", "质量趋势合格", "evt:midea",
]) assert.ok(html.includes(text), `missing event audit text: ${text}`);
assert.equal((html.match(/已完成事件扫描且未发现重大负面；本通道不要求正向催化/g) || []).length, 2);
assert.equal((html.match(/合格候选（非主候选）/g) || []).length, 2);
assert.equal((html.match(/主候选 ·/g) || []).length, 1);
assert.equal(productionDecisionTruth().primary.code, "0300.HK", "secondary audit must not replace primary");
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
        self.assertIn("HISTORY_LIMIT = 1000", self.js)
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

    def test_old_full_history_assets_have_an_explicit_retention_message(self) -> None:
        self.assertIn("item.full_snapshot_available === false", self.js)
        self.assertIn("完整交互快照仅保留最近 30 个决策日", self.js)


if __name__ == "__main__":
    unittest.main()

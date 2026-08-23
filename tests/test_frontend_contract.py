from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


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
        for label in ("Legacy", "主动放弃", "可执行·缺结算", "可执行·待结算", "可执行·已结算", "已结算·待校验", "结算无效"):
            self.assertIn(label, self.js)
        self.assertIn('formalStatus === "SETTLED_VALID"', self.js)
        self.assertIn("item?.outcome_validation?.valid === true", self.js)
        self.assertNotIn('if (outcomeStatus === "SETTLED") return { code: "SETTLED"', self.js)
        self.assertIn("history-row-statuses", self.js)
        self.assertIn("shadowOutcomeTag(item)", self.js)

    def test_evidence_views_and_canvas_charts_are_implemented(self) -> None:
        for renderer in ("renderDecision", "renderCandidates", "renderEvents", "renderHistory", "renderModel", "renderHealth"):
            self.assertRegex(self.js, rf"function {renderer}\(")
        self.assertIn('<canvas id="decisionChart"', self.js)
        self.assertIn('<canvas id="historyChart"', self.js)
        self.assertNotIn("<svg", self.html + self.js)

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
            "正式可执行候选",
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
        self.assertIn("researchCandidate].filter(Boolean)", self.js)
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

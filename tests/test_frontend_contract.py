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

    def test_frontend_uses_published_snapshot_and_live_overlay_only(self) -> None:
        self.assertIn('getJson("/api/latest")', self.js)
        self.assertIn('/api/live?market=', self.js)
        self.assertNotIn("force=1", self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertIn("评分和排序不会随之重算", self.js)
        self.assertIn('candidate.execution_state === "BLOCKED"', self.js)

    def test_live_overlay_is_monotonic_and_visible_candidate_refreshes_every_fifteen_seconds(self) -> None:
        self.assertIn("const LIVE_POLL_INTERVAL_MS = 15 * 1000", self.js)
        self.assertRegex(self.js, r"function shouldApplyLiveQuote\(")
        self.assertIn("payload.source_as_of", self.js)
        self.assertIn("candidate?.realtime?.source_as_of", self.js)
        self.assertRegex(self.js, r"sourceEpoch\s*<\s*baselineEpoch")
        self.assertIn("if (document.hidden)", self.js)
        self.assertIn('state.tab === "decision"', self.js)
        self.assertIn('state.tab === "candidates"', self.js)
        self.assertIn("window.setInterval(pollVisibleLive, LIVE_POLL_INTERVAL_MS)", self.js)
        self.assertIn('document.addEventListener("visibilitychange"', self.js)
        for field in ("provider", "session_label", "latency_seconds", "quote_status"):
            self.assertIn(field, self.js)
        self.assertIn("实时源较旧，未覆盖快照价", self.js)

    def test_shadow_research_outcomes_are_reported_outside_executable_performance(self) -> None:
        self.assertRegex(self.js, r"function shadowLedgerStats\(")
        self.assertIn("shadow_outcome", self.js)
        self.assertIn("shadow_pending", self.js)
        self.assertIn("shadow_settled", self.js)
        self.assertIn("研究跟踪 PENDING", self.js)
        self.assertIn("研究跟踪 SETTLED", self.js)
        self.assertIn("不计入可执行绩效、胜率或收益", self.js)

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
        self.assertIn("评分和排序不会随之重算", self.js)

    def test_freshness_polling_reloads_only_when_snapshot_changes(self) -> None:
        self.assertIn("const STATUS_POLL_INTERVAL_MS = 5 * 60 * 1000", self.js)
        self.assertRegex(self.js, r"async function pollStatus\(")
        self.assertIn('getJson("/api/status")', self.js)
        self.assertIn("status.generated_at !== previousGeneratedAt", self.js)
        self.assertIn("!state.snapshot ||", self.js)
        self.assertIn('getJson("/api/latest")', self.js)
        self.assertIn("getHistoryPayload()", self.js)
        self.assertIn("window.setInterval(pollStatus, STATUS_POLL_INTERVAL_MS)", self.js)
        for label in ("数据正常", "更新中", "数据已过期", "状态未知"):
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
        self.assertIn("不展示胜率或模拟收益", self.js)
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


if __name__ == "__main__":
    unittest.main()

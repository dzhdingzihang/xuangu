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

    def test_five_accessible_tabs_are_present(self) -> None:
        for tab in ("decision", "candidates", "events", "history", "model"):
            self.assertIn(f'id="tab-{tab}"', self.html)
            self.assertIn(f'id="panel-{tab}"', self.html)
            self.assertIn(f'data-tab="{tab}"', self.html)
        self.assertEqual(self.html.count('role="tabpanel"'), 5)

    def test_frontend_uses_published_snapshot_and_live_overlay_only(self) -> None:
        self.assertIn('getJson("/api/latest")', self.js)
        self.assertIn('/api/live?market=', self.js)
        self.assertNotIn("force=1", self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertIn("评分和排序不会随之重算", self.js)
        self.assertIn('candidate.execution_state === "BLOCKED"', self.js)

    def test_evidence_views_and_canvas_charts_are_implemented(self) -> None:
        for renderer in ("renderDecision", "renderCandidates", "renderEvents", "renderHistory", "renderModel"):
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
        self.assertIn('parsed.protocol === "https:" || parsed.protocol === "http:"', self.js)
        self.assertIn("function normalizedDirection", self.js)

    def test_design_is_responsive_and_has_no_css_gradients(self) -> None:
        self.assertIn("@media (max-width: 760px)", self.css)
        self.assertIn("grid-template-columns: 190px", self.css)
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


if __name__ == "__main__":
    unittest.main()

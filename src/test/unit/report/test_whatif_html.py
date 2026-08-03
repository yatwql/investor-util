"""调仓 What-if 独立 HTML 页呈现测试。

覆盖：
  - available=True → ①对比文件 + ②汇总指标 + ③资产配置对比图 + ⑤分类对比 +
    ⑥持仓变动明细 + ⑦说明 六段齐全（未指定生效日时④时序回测隐藏）
  - 指定生效日 → ④时序回测出现：指标卡 + 2 张线图 canvas + 2 条 .chart-caption
    （C20）+ #whatif-backtest-chart-data JSON（R9 数据最小化）
  - 双环形图 canvas + 2 条 .chart-caption（C20）+ #whatif-chart-data JSON
  - 变动明细行 class 与 action-badge 渲染
  - 箭头方向类（arrow-up/down/flat）
  - available=False → 降级占位「调仓对比数据暂不可用」
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _whatif_data(**extra) -> dict:
    """构造 C19 契约 whatif_data mock（含全部变动类型）。"""
    d = {
        "available": True,
        "status": "ok",
        "base_file": "before.xlsx",
        "candidate_file": "after.xlsx",
        "base": {"total_cost": 26000.0, "total_shares": 8000.0, "holding_count": 4, "hhi": 0.5},
        "candidate": {"total_cost": 24000.0, "total_shares": 6200.0, "holding_count": 4, "hhi": 0.6},
        "summary": [
            {
                "key": "total_cost",
                "label": "总成本(元)",
                "unit": "money",
                "base": 26000.0,
                "candidate": 24000.0,
                "delta": -2000.0,
                "arrow": "↓",
            },
            {
                "key": "holding_count",
                "label": "持仓品种数",
                "unit": "count",
                "base": 4,
                "candidate": 4,
                "delta": 0,
                "arrow": "→",
            },
            {
                "key": "hhi",
                "label": "持仓集中度 HHI",
                "unit": "hhi",
                "base": 0.5,
                "candidate": 0.6,
                "delta": 0.1,
                "arrow": "↑",
            },
        ],
        "categories": [
            {
                "key": "equity",
                "label": "股票",
                "base_cost": 20000.0,
                "cand_cost": 12000.0,
                "base_weight": 76.92,
                "cand_weight": 50.0,
                "delta_pct": -26.92,
            },
            {
                "key": "fixed_income",
                "label": "固收",
                "base_cost": 6000.0,
                "cand_cost": 12000.0,
                "base_weight": 23.08,
                "cand_weight": 50.0,
                "delta_pct": 26.92,
            },
        ],
        "changes": [
            {
                "code": "511880",
                "name": "货币ETF",
                "action": "新增",
                "base_shares": 0.0,
                "cand_shares": 2000.0,
                "shares_diff": 2000.0,
                "base_cost": 0.0,
                "cand_cost": 2000.0,
                "cost_diff": 2000.0,
                "base_weight": 0.0,
                "cand_weight": 8.33,
                "weight_delta_pct": 8.33,
            },
            {
                "code": "510300",
                "name": "沪深300ETF",
                "action": "清仓",
                "base_shares": 2000.0,
                "cand_shares": 0.0,
                "shares_diff": -2000.0,
                "base_cost": 6000.0,
                "cand_cost": 0.0,
                "cost_diff": -6000.0,
                "base_weight": 23.08,
                "cand_weight": 0.0,
                "weight_delta_pct": -23.08,
            },
            {
                "code": "600900",
                "name": "长江电力",
                "action": "加仓",
                "base_shares": 1000.0,
                "cand_shares": 1200.0,
                "shares_diff": 200.0,
                "base_cost": 20000.0,
                "cand_cost": 24000.0,
                "cost_diff": 4000.0,
                "base_weight": 76.92,
                "cand_weight": 100.0,
                "weight_delta_pct": 23.08,
            },
            {
                "code": "511010",
                "name": "国债ETF",
                "action": "不变",
                "base_shares": 5000.0,
                "cand_shares": 5000.0,
                "shares_diff": 0.0,
                "base_cost": 50000.0,
                "cand_cost": 50000.0,
                "cost_diff": 0.0,
                "base_weight": 50.0,
                "cand_weight": 50.0,
                "weight_delta_pct": 0.0,
            },
        ],
        "stats": {"added": 1, "removed": 1, "increased": 1, "decreased": 0, "unchanged": 1},
        "reason": "",
    }
    d.update(extra)
    return d


class TestWhatifHtmlPage(unittest.TestCase):
    """调仓 What-if 独立 HTML 页呈现测试。"""

    def _render(self, whatif_data) -> str:
        from src.python.report.whatif_writer import render_whatif_html

        return render_whatif_html(whatif_data, "2026-08-03 12:00:00")

    def test_full_rendering_sections_without_backtest(self):
        """available=True 且未指定生效日 → ①~⑦ 六段齐全（④时序回测隐藏）。"""
        text = self._render(_whatif_data())
        for heading in ("① 对比文件", "② 汇总指标对比", "③ 资产配置对比", "⑤ 分类配置对比", "⑥ 持仓变动明细", "⑦ 说明"):
            self.assertIn(heading, text, f"缺章节 {heading}")
        self.assertNotIn("④ 时序回测", text, "未指定生效日时④时序回测不应出现")

    def test_backtest_section_rendered(self):
        """指定生效日 + 回测可用 → ④时序回测出现：指标卡 + 2 线图 + 2 caption + R9 负载。"""
        import json

        bt = {
            "available": True,
            "status": "ok",
            "reason": "",
            "effective_date": "2026-07-01",
            "metrics": [
                {
                    "key": "period_return_pct",
                    "label": "区间收益",
                    "unit": "pct",
                    "base": 1.25,
                    "candidate": 2.50,
                    "delta": 1.25,
                    "arrow": "↑",
                },
                {
                    "key": "sharpe_ratio",
                    "label": "夏普比率",
                    "unit": "ratio",
                    "base": 0.85,
                    "candidate": 1.2,
                    "delta": 0.35,
                    "arrow": "↑",
                },
            ],
            "series": {
                "labels": ["2026-07-01", "2026-07-02", "2026-07-03"],
                "base": [100.0, 101.0, 101.25],
                "candidate": [100.0, 102.0, 102.5],
                "base_drawdown": [0.0, -0.1, -0.05],
                "candidate_drawdown": [0.0, -0.2, -0.1],
            },
        }
        text = self._render(_whatif_data(backtest=bt))
        self.assertIn("④ 时序回测", text)
        self.assertIn("2026-07-01 生效", text)
        self.assertIn('id="chart_whatif_bt_nav"', text)
        self.assertIn('id="chart_whatif_bt_dd"', text)
        self.assertIn("2.50%", text, "pct 值应拼 % 号")
        self.assertEqual(text.count('class="chart-caption"'), 4, "双环图 + 2 线图各带 caption（C20）")
        # 回测图表 JSON 负载可解析且只含 series 字段（R9 数据最小化）
        m = 'id="whatif-backtest-chart-data">'
        start = text.index(m) + len(m)
        end = text.index("</script>", start)
        payload = json.loads(text[start:end])
        self.assertEqual(payload["available"], True)
        self.assertEqual(payload["effective_date"], "2026-07-01")
        self.assertEqual(
            set(payload["series"].keys()),
            {"labels", "base", "candidate", "base_drawdown", "candidate_drawdown"},
            "图表负载只应含 series 字段",
        )
        self.assertNotIn("metrics", payload, "图表负载不应含回测指标 metrics")
        self.assertNotIn("reason", payload, "图表负载不应含 reason")

    def test_backtest_unavailable_hidden(self):
        """backtest 存在但 available=False → ④时序回测隐藏。"""
        bt = {
            "available": False,
            "status": "unavailable",
            "reason": "生效日后的交易日不足 20 天",
            "effective_date": "2026-07-20",
        }
        text = self._render(_whatif_data(backtest=bt))
        self.assertNotIn("④ 时序回测", text)
        self.assertNotIn('id="chart_whatif_bt_nav"', text)

    def test_compare_files_cards(self):
        """对比文件卡 + 变动统计。"""
        text = self._render(_whatif_data())
        self.assertIn("before.xlsx", text)
        self.assertIn("after.xlsx", text)
        self.assertIn("基准（调仓前）", text)
        self.assertIn("目标（调仓后 / 假设）", text)
        self.assertIn("新增 <strong>1</strong>", text)
        self.assertIn("清仓 <strong>1</strong>", text)

    def test_summary_cards_with_arrows(self):
        """汇总指标卡 + 箭头方向类。"""
        text = self._render(_whatif_data())
        self.assertIn("总成本(元)", text)
        self.assertIn("arrow-down", text)
        self.assertIn("arrow-flat", text)
        self.assertIn("arrow-up", text)
        self.assertIn("24,000.00", text)  # 目标总成本（money 过滤器）

    def test_charts_and_captions_c20(self):
        """双环形图 canvas + 2 条 .chart-caption（C20）+ #whatif-chart-data JSON。"""
        import json

        text = self._render(_whatif_data())
        self.assertIn('id="chart_whatif_base"', text)
        self.assertIn('id="chart_whatif_candidate"', text)
        self.assertEqual(text.count('class="chart-caption"'), 2, "每张图必须有 .chart-caption（C20）")
        # 图表 JSON 数据注入可解析（Python 侧裁剪后的专用负载：只含图表消费字段）
        m = 'id="whatif-chart-data">'
        start = text.index(m) + len(m)
        end = text.index("</script>", start)
        payload = json.loads(text[start:end])
        self.assertEqual(payload["available"], True)
        self.assertEqual(len(payload["categories"]), 2)
        self.assertEqual(payload["categories"][0]["label"], "股票")
        self.assertNotIn("summary", payload, "图表负载不应含汇总指标 summary")
        self.assertNotIn("changes", payload, "图表负载不应含变动明细 changes")
        self.assertNotIn("stats", payload, "图表负载不应含变动统计 stats")
        self.assertNotIn("base", payload, "图表负载不应含基准快照 base")
        self.assertNotIn("candidate", payload, "图表负载不应含目标快照 candidate")

    def test_changes_table_with_action_rows(self):
        """变动明细：行动作行 class + action-badge。"""
        text = self._render(_whatif_data())
        self.assertIn('class="whatif-added"', text)
        self.assertIn('class="whatif-removed"', text)
        self.assertIn('class="whatif-increased"', text)
        self.assertIn('class="whatif-unchanged"', text)
        self.assertIn("action-badge badge-added", text)
        self.assertIn("货币ETF", text)
        self.assertIn("600900", text)

    def test_unavailable_placeholder(self):
        """available=False → 降级占位 + reason。"""
        data = _whatif_data(
            available=False,
            status="empty",
            summary=[],
            categories=[],
            changes=[],
            stats={},
            reason="调仓对比数据为空：基准与目标持仓均为空",
        )
        text = self._render(data)
        self.assertIn("调仓对比数据暂不可用", text)
        self.assertIn("基准与目标持仓均为空", text)
        self.assertNotIn("① 对比文件", text)

    def test_none_placeholder(self):
        """whatif_data=None → 降级占位。"""
        text = self._render(None)
        self.assertIn("调仓对比数据暂不可用", text)

    def test_theme_toggle_button_present(self):
        """暗色模式（主题切换）：浮动切换按钮存在且带 aria-label。"""
        text = self._render(_whatif_data())
        self.assertIn('class="theme-toggle-btn"', text, "whatif 页应含主题切换按钮")
        self.assertIn('aria-label="切换深色模式"', text, "切换按钮应含 aria-label")

    def test_theme_js_loaded(self):
        """暗色模式（主题切换）：whatif 页加载 theme.js。"""
        text = self._render(_whatif_data())
        self.assertIn('src="theme.js"', text, "whatif 页应加载 theme.js")

    def test_dark_theme_css_variables(self):
        """暗色模式（主题切换）：whatif 页含 :root 变量与深色覆盖块。"""
        text = self._render(_whatif_data())
        self.assertIn("--bg:", text, "whatif 页应定义页面级 --bg 变量")
        self.assertIn('[data-theme="dark"]', text, "whatif 页应含深色覆盖块")
        self.assertIn("display: none !important", text, "whatif 页打印时应隐藏主题按钮")

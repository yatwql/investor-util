"""组合演进章节 HTML 呈现测试。

覆盖：
  - available=True → 汇总提示 + ①总市值趋势 + ②HHI 趋势 + ③TOP 持仓占比变迁 + 说明
  - enable_interactive_charts=True → 3 张 Chart.js 画布 + 3 条 .chart-caption（C20）
  - 多账户 → ④账户配置流表
  - available=False（快照不足）→ 降级占位「组合演进数据不足」
  - evolution_data=None → 章节整体隐藏（html_writer 数据门控）

注意：模板在 evolution 章节内部直接调用 evolution_data.get()，
生产路径由 html_writer 保证 evolution_data 非 None 时才渲染该章节，
因此 None 场景测试通过「章节不可见」验证（而非渲染占位）。
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

from src.test.unit.report.test_html_report_structure import (
    _REPORT_SECTION_DEFAULT,
    _build_minimal_render_data,
    _render_template,
)

_EVO_SECTION = {"key": "portfolio_evolution", "name": "组合演进", "number": 19}


def _order_with_evolution() -> list[dict]:
    """默认清单追加 portfolio_evolution 章节。"""
    return [dict(sec) for sec in _REPORT_SECTION_DEFAULT] + [dict(_EVO_SECTION)]


def _render_evolution(evolution_data, interactive: bool = False) -> "BeautifulSoup":
    """渲染 portfolio_evolution 可见、其余隐藏的模板。"""
    order = _order_with_evolution()
    numbers = {sec["key"]: sec["number"] for sec in order}
    sv_dict = {sec["key"]: (sec["key"] == "portfolio_evolution") for sec in order}
    data = _build_minimal_render_data(order, numbers, sv_dict)
    data["evolution_data"] = evolution_data
    if interactive:
        data["enable_interactive_charts"] = True
    return _render_template(data)


def _evolution_data(**extra) -> dict:
    """构造 C19 契约 evolution_data mock（3 观察日，双账户，TOP3）。"""
    d = {
        "available": True,
        "snapshot_count": 5,
        "min_snapshots": 3,
        "periods": ["07-01", "07-02", "07-03"],
        "total_value": [100000.0, 110000.0, 120000.0],
        "total_cost": [90000.0, 90000.0, 90000.0],
        "total_pnl": [10000.0, 20000.0, 30000.0],
        "holding_counts": [2, 2, 3],
        "account_flows": {"账户A": [60.0, 50.0, 70.0], "账户B": [40.0, 50.0, 30.0]},
        "hhi": [0.52, 0.58, 0.38],
        "top_holdings": [
            {"code": "a", "name": "资产A", "weights": [60.0, 70.0, 50.0], "present_count": 3},
            {"code": "b", "name": "资产B", "weights": [40.0, 30.0, 30.0], "present_count": 3},
            {"code": "c", "name": "资产C", "weights": [0.0, 0.0, 20.0], "present_count": 1},
        ],
        "reason": "",
    }
    d.update(extra)
    return d


class TestHtmlEvolutionSection(unittest.TestCase):
    """组合演进章节 HTML 呈现测试。"""

    def _section(self, evolution_data, interactive: bool = False):
        return _render_evolution(evolution_data, interactive=interactive).find(id="sec-portfolio_evolution")

    def test_full_rendering_when_available(self):
        """available=True → 汇总提示 + ①总市值 + ②HHI + ③TOP 变迁 + 说明。"""
        section = self._section(_evolution_data())
        text = section.get_text()
        self.assertIn("组合演进", text)
        self.assertIn("已聚合", text)
        self.assertIn("5", text)  # snapshot_count
        self.assertIn("3", text)  # 有效观察日
        self.assertIn("① 总市值与总盈亏趋势", text)
        self.assertIn("② 持仓集中度（HHI）趋势", text)
        self.assertIn("③ TOP 持仓占比变迁", text)
        self.assertIn("资产A", text)
        self.assertIn("资产C", text)
        self.assertIn("0.5200", text)  # HHI 首期
        self.assertIn("100,000.00", text)  # 首期总市值（money 过滤器）
        # 说明区
        self.assertIn("权重口径", text)
        self.assertIn("快照格式限制", text)

    def test_interactive_charts_and_captions(self):
        """enable_interactive_charts=True → 3 张画布 + 3 条图下说明（C20）。"""
        section = self._section(_evolution_data(), interactive=True)
        self.assertEqual(len(section.select("canvas")), 3)
        for cid in ("chart_evolution_total", "chart_evolution_hhi", "chart_evolution_top"):
            self.assertIsNotNone(section.find(id=cid), f"缺画布 {cid}")
        captions = section.select(".chart-caption")
        self.assertEqual(len(captions), 3, "每张图表必须有 .chart-caption（C20）")
        joined = " ".join(c.get_text() for c in captions)
        self.assertIn("总市值与总盈亏", joined)
        self.assertIn("HHI", joined)
        self.assertIn("TOP 持仓占比", joined)
        # 图表 JSON 数据注入
        self.assertIsNotNone(section.find(id="evolution-chart-data"))

    def test_top_chart_only_when_multiple_top_holdings(self):
        """TOP 变迁图仅在 top_holdings > 1 时渲染（单品种无需变迁图）。"""
        data = _evolution_data()
        data["top_holdings"] = [{"code": "a", "name": "资产A", "weights": [100.0, 100.0, 100.0], "present_count": 3}]
        section = self._section(data, interactive=True)
        self.assertIsNone(section.find(id="chart_evolution_top"), "单品种不应渲染 TOP 变迁图")

    def test_account_flows_rendered_when_multi_account(self):
        """多账户 → ④账户配置流表。"""
        section = self._section(_evolution_data())
        text = section.get_text()
        self.assertIn("④ 账户配置流", text)
        self.assertIn("账户A", text)
        self.assertIn("账户B", text)

    def test_account_flows_hidden_when_single_account(self):
        """单账户 → 不渲染账户配置流表。"""
        data = _evolution_data()
        data["account_flows"] = {"全部": [100.0, 100.0, 100.0]}
        section = self._section(data)
        self.assertNotIn("账户配置流", section.get_text())

    def test_unavailable_placeholder(self):
        """available=False（快照不足）→ 降级占位 + reason。"""
        data = _evolution_data(
            available=False,
            snapshot_count=2,
            periods=[],
            total_value=[],
            total_cost=[],
            total_pnl=[],
            holding_counts=[],
            hhi=[],
            top_holdings=[],
            reason="组合演进快照不足：有效期数 2 < 下限 3，趋势数据待积累",
        )
        section = self._section(data)
        text = section.get_text()
        self.assertIn("组合演进数据不足", text)
        self.assertIn("组合演进快照不足", text)
        self.assertIn("3", text)  # min_snapshots 提示
        self.assertNotIn("① 总市值与总盈亏趋势", text)

    def test_none_section_hidden(self):
        """evolution_data=None → 章节整体不渲染（html_writer 数据门控）。

        与 correlation 章节一致：生产路径由 html_writer 在 evolution_data 为
        None 时将 portfolio_evolution 置为不可见，此处用全隐藏 sv_dict 模拟。
        """
        order = _order_with_evolution()
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: False for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["evolution_data"] = None
        soup = _render_template(data)
        self.assertIsNone(soup.find(id="sec-portfolio_evolution"))

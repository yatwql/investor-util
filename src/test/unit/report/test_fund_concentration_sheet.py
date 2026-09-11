"""持仓集中度监控页签 Excel 呈现测试。

覆盖（fund_concentration_sheet.write_concentration_sheet）：
  - 表头含「报告期」列，逐行呈现本期持仓所依据的报告期
  - 报告期陈旧 → 期次后缀「（陈旧）」
  - 报告期未推进 → 环比列「无对比意义」（而非报 0）、标识列「⎯ 报告期未推进」
  - 报告期推进 → 照常呈现环比箭头与预警标识

集中度是静态快照的比例值：报告期未推进时本次与上期读的是同一份报告，
环比恒为 0，报 0 会被读成"持仓结构没变化"，故须据实标注。
"""

from __future__ import annotations

import unittest
from typing import Any

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _item(**extra: Any) -> dict:
    """构造 compute_concentration() 的单行结果。"""
    base: dict[str, Any] = {
        "name": "易方达中小盘混合",
        "code": "110011",
        "report_period": "2026-06-30",
        "report_stale": False,
        "top3_pct": 24.5,
        "top5_pct": 35.5,
        "top10_pct": 35.5,
        "prev_top10_pct": None,
        "change_pct": None,
        "alert_level": "正常",
        "is_first_check": False,
        "period_unchanged": False,
    }
    base.update(extra)
    return base


class TestConcentrationSheet(unittest.TestCase):
    """write_concentration_sheet：报告期与环比语义的呈现。"""

    def _write(self, data: list[dict]) -> "object":
        from openpyxl import Workbook

        from src.python.report.fund_concentration_sheet import write_concentration_sheet

        wb = Workbook()
        ws = wb.active
        write_concentration_sheet(ws, data)
        return ws

    def _rows(self, ws) -> list[list[str]]:
        return [[str(c.value) if c.value is not None else "" for c in row] for row in ws.iter_rows()]

    def _flat(self, ws) -> list[str]:
        return [v for row in self._rows(ws) for v in row]

    def test_header_includes_report_period(self):
        """表头含「报告期」列（否则读者无从判断占比是哪一期的持仓）。"""
        ws = self._write([_item()])
        header = self._rows(ws)[1]
        self.assertIn("报告期", header)
        self.assertLess(header.index("基金代码"), header.index("报告期"))
        self.assertLess(header.index("报告期"), header.index("前3占比%"))

    def test_report_period_rendered(self):
        """报告期逐行呈现，与数据同列。"""
        ws = self._write([_item(report_period="2025-12-31")])
        header = self._rows(ws)[1]
        data_row = next(r for r in self._rows(ws) if r and r[0] == "易方达中小盘混合")
        self.assertEqual(data_row[header.index("报告期")], "2025-12-31")

    def test_stale_report_period_suffixed(self):
        """报告期陈旧 → 期次后缀「（陈旧）」，一眼可辨。"""
        ws = self._write([_item(report_period="2020-03-31", report_stale=True)])
        flat = self._flat(ws)
        self.assertTrue(any("2020-03-31（陈旧）" in v for v in flat), f"应标注陈旧，实际: {flat}")

    def test_period_unchanged_no_comparison_meaning(self):
        """报告期未推进 → 环比「无对比意义」、标识「报告期未推进」（不报 0 冒充无变化）。"""
        ws = self._write([_item(period_unchanged=True, prev_top10_pct=35.5, change_pct=None)])
        flat = self._flat(ws)
        self.assertIn("无对比意义", flat)
        self.assertTrue(any("报告期未推进" in v for v in flat), f"标识列应说明原因，实际: {flat}")
        self.assertFalse(any("基线已记录" in v for v in flat), "报告期未推进不应显示为基线已记录")
        self.assertFalse(any("→ 0.00%" in v or "+0.00%" in v for v in flat), "不应把环比呈现为 0")

    def test_advanced_period_renders_change(self):
        """报告期推进 → 照常呈现环比箭头与预警标识（闸门不可误伤正常对比）。"""
        ws = self._write([_item(report_period="2026-06-30", prev_top10_pct=30.0, change_pct=5.5, alert_level="正常")])
        flat = self._flat(ws)
        self.assertTrue(any("↑ +5.50%" in v for v in flat), f"应呈现环比，实际: {flat}")
        self.assertFalse(any("无对比意义" in v for v in flat), "报告期已推进不应标为无对比意义")
        self.assertTrue(any("✅ 正常" in v for v in flat))

    def test_first_check_keeps_baseline_label(self):
        """首检 → 环比「基线已记录」，不受报告期语义影响。"""
        ws = self._write([_item(is_first_check=True, prev_top10_pct=None, change_pct=None)])
        flat = self._flat(ws)
        self.assertIn("基线已记录", flat)
        self.assertFalse(any("无对比意义" in v for v in flat))

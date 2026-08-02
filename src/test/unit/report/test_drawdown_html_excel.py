"""回撤明细在 HTML/Excel 报告中的呈现测试。

HTML：
  - drawdown_available=True 时渲染「回撤明细」事件表 + 当前回撤状态卡
  - 有效交易日不足（drawdown_available=False）显示数据不足提示
  - history_data 缺失显示数据不可用占位
  - 未恢复事件的恢复耗时显示占位符

Excel：
  - _write_drawdown_analysis_sheet 指标矩阵下方追加回撤明细表
  - drawdown_events 为空时写占位行
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


def _render_drawdown(history_data) -> "BeautifulSoup":
    """渲染 drawdown_analysis 可见、其余隐藏的模板。"""
    order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
    numbers = {sec["key"]: sec["number"] for sec in order}
    sv_dict = {sec["key"]: (sec["key"] == "drawdown_analysis") for sec in order}
    data = _build_minimal_render_data(order, numbers, sv_dict)
    data["history_data"] = history_data
    data["drawdown_min_span"] = 60  # html_writer 在生产路径中注入，测试直接渲染模板需自行提供
    return _render_template(data)


def _history(events: list[dict] | None, available: bool = True, **extra) -> dict:
    """构造带 drawdown 字段的 history_data mock。"""
    h = {
        "status": "ok",
        "bars": [{"date": f"2026-01-{d:02d}", "total_value": 100.0, "drawdown_pct": 0.0}
                 for d in range(1, 61)],
        "total_return_pct": 10.0,
        "total_return": 1000.0,
        "data_start": "2026-01-01",
        "data_end": "2026-03-01",
        "max_drawdown_pct": -0.05,
        "max_drawdown": -500.0,
        "drawdown_start": "2026-01-10",
        "drawdown_end": "2026-01-20",
        "annualized_volatility": 0.18,
        "drawdown_available": available,
        "drawdown_events": events if events is not None else [],
        "warnings": None,
        "failed_holdings": None,
        "successful_holdings": None,
    }
    h.update(extra)
    return h


# ── HTML 呈现 ────────────────────────────────────────────────


class TestHtmlDrawdownSection(unittest.TestCase):
    """回撤章节 HTML 呈现测试。"""

    def _section(self, history_data):
        soup = _render_drawdown(history_data)
        return soup.find(id="sec-drawdown_analysis")

    def test_events_table_rendered_when_available(self):
        """drawdown_available=True → 渲染回撤明细事件表。"""
        events = [
            {"peak_date": "2026-01-10", "trough_date": "2026-01-20",
             "recovery_date": "2026-02-01", "drawdown_pct": 12.5,
             "duration_days": 10, "recovery_days": 12, "recovered": True},
        ]
        section = self._section(_history(events))
        self.assertIn("回撤明细", section.get_text())
        rows = section.select("table tbody tr")
        self.assertEqual(len(rows), 1)
        cells = [c.get_text(strip=True) for c in rows[0].select("td")]
        self.assertIn("2026-01-10", cells)   # 起峰日
        self.assertIn("2026-01-20", cells)   # 最深日
        self.assertIn("2026-02-01", cells)   # 恢复日
        self.assertIn("12.50%", cells)       # 最大回撤（两位小数 + %）
        self.assertIn("10 天", cells)        # 持续天数
        self.assertIn("12 天", cells)        # 恢复耗时
        self.assertIn("✅ 已恢复", cells)

    def test_unrecovered_event_placeholder(self):
        """未恢复事件 → 恢复日/恢复耗时显示占位符。"""
        events = [
            {"peak_date": "2026-01-10", "trough_date": "2026-01-20",
             "recovery_date": "", "drawdown_pct": 8.0,
             "duration_days": 10, "recovery_days": None, "recovered": False},
        ]
        section = self._section(_history(events))
        rows = section.select("table tbody tr")
        self.assertEqual(len(rows), 1)
        cells = [c.get_text(strip=True) for c in rows[0].select("td")]
        self.assertIn("—", cells)            # 恢复日占位
        self.assertIn("⏳ 未恢复", cells)

    def test_current_drawdown_status_card(self):
        """「当前回撤状态」卡渲染最近一次事件状态。"""
        events = [
            {"peak_date": "2026-01-10", "trough_date": "2026-01-20",
             "recovery_date": "", "drawdown_pct": 8.0,
             "duration_days": 10, "recovery_days": None, "recovered": False},
        ]
        section = self._section(_history(events))
        self.assertIn("当前回撤状态", section.get_text())
        self.assertIn("回撤中", section.get_text())

    def test_no_events_shows_no_significant(self):
        """drawdown_available=True 但无事件 → 状态卡显示无显著回撤，无事件表。"""
        section = self._section(_history([]))
        self.assertIn("无显著回撤", section.get_text())
        self.assertIsNone(section.select_one("table tbody tr"))

    def test_insufficient_data_message(self):
        """drawdown_available=False（有效交易日不足）→ 显示数据不足提示。"""
        history = _history([], available=False)
        history["bars"] = [{"date": "2026-01-01", "total_value": 100.0, "drawdown_pct": 0.0}]
        section = self._section(history)
        self.assertIn("历史回撤数据不足", section.get_text())
        self.assertIn("60", section.get_text())  # drawdown_min_span

    def test_history_none_placeholder(self):
        """history_data=None → 显示数据不可用占位。"""
        section = self._section(None)
        self.assertIn("回撤分析数据暂不可用", section.get_text())

    def test_unavailable_status_placeholder(self):
        """status=unavailable → 显示数据不可用占位（而非回撤明细）。"""
        section = self._section(_history([], available=True, status="unavailable", bars=[]))
        self.assertIn("回撤分析数据暂不可用", section.get_text())
        self.assertNotIn("回撤明细", section.get_text())


# ── Excel 呈现 ───────────────────────────────────────────────


class TestExcelDrawdownSheet(unittest.TestCase):
    """回撤分析页签 Excel 呈现测试。"""

    def _write(self, history_data) -> "object":
        from openpyxl import Workbook

        from src.python.report.excel_generator import _write_drawdown_analysis_sheet

        wb = Workbook()
        ws = wb.active
        _write_drawdown_analysis_sheet(ws, history_data)
        return ws

    def _all_text(self, ws) -> list[list[str]]:
        return [[str(c.value) if c.value is not None else "" for c in row]
                for row in ws.iter_rows()]

    def test_metrics_matrix_then_events_table(self):
        """指标矩阵下方追加回撤明细表。"""
        events = [
            {"peak_date": "2026-01-10", "trough_date": "2026-01-20",
             "recovery_date": "2026-02-01", "drawdown_pct": 12.5,
             "duration_days": 10, "recovery_days": 12, "recovered": True},
        ]
        history = _history(events)
        ws = self._write(history)
        rows = self._all_text(ws)
        titles = [r[0] for r in rows]
        self.assertIn("历史回撤分析", titles)
        self.assertIn("回撤明细", titles)
        # 回撤明细位于指标汇总之后
        self.assertLess(titles.index("历史回撤分析"), titles.index("回撤明细"))
        # 事件行数据完整
        flat = [v for row in rows for v in row]
        self.assertIn("2026-01-10", flat)
        self.assertIn("2026-02-01", flat)
        self.assertIn("已恢复", flat)
        self.assertIn("0.125", flat)  # 12.5% / 100 存储为小数（FMT_PERCENT 显示 12.50%）

    def test_empty_events_placeholder_row(self):
        """drawdown_events 为空 → 写占位行。"""
        ws = self._write(_history([]))
        flat = [v for row in self._all_text(ws) for v in row]
        self.assertTrue(any("未检测到显著回撤事件" in v for v in flat),
                        "空事件应写入占位行")

    def test_history_none_placeholder(self):
        """history_data=None → 整页占位。"""
        ws = self._write(None)
        flat = [v for row in self._all_text(ws) for v in row]
        self.assertTrue(any("历史回撤分析数据暂不可用" in v for v in flat),
                        "history_data=None 应写入整页占位")

    def test_unrecovered_event_row(self):
        """未恢复事件 → 恢复日空、状态未恢复。"""
        events = [
            {"peak_date": "2026-01-10", "trough_date": "2026-01-20",
             "recovery_date": "", "drawdown_pct": 8.0,
             "duration_days": 10, "recovery_days": None, "recovered": False},
        ]
        ws = self._write(_history(events))
        flat = [v for row in self._all_text(ws) for v in row]
        self.assertIn("未恢复", flat)
        self.assertIn("--", flat)  # recovery_days 占位

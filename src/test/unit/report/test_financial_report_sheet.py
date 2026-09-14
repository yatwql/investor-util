"""持仓个股财报摘要页签 Excel 呈现测试。

覆盖：
  - available=True → 标题 + 表头 + 逐行摘要 + 来源/原文 + 说明
  - available=False → 占位原因 + 失败清单
  - digest_data=None → 整页占位
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _digest_data(**extra) -> dict:
    d = {
        "available": True,
        "reason": "",
        "entry_count": 1,
        "rows": [
            {
                "code": "600519",
                "name": "贵州茅台",
                "symbol": "600519.SS",
                "report_period": "2025-12-31",
                "doc_type": "年报",
                "title": "2025 年年度报告",
                "announcement_date": "2026-04-01",
                "summary": "管理层讨论与分析：营收同比增长……",
                "source": "巨潮资讯网 (cninfo)",
                "adjunct_url": "http://example.com/1",
            }
        ],
        "failures": [],
    }
    d.update(extra)
    return d


class TestExcelFinancialReportSheet(unittest.TestCase):
    def _write(self, digest_data):
        from openpyxl import Workbook

        from src.python.report.financial_report_sheet import write_financial_report_sheet

        wb = Workbook()
        ws = wb.active
        write_financial_report_sheet(ws, digest_data)
        return ws

    def _flat(self, ws) -> list[str]:
        return [str(c.value) if c.value is not None else "" for row in ws.iter_rows() for c in row]

    def test_available_writes_rows_and_notes(self):
        ws = self._write(_digest_data())
        flat = self._flat(ws)
        self.assertTrue(any("持仓个股财报摘要" in v for v in flat))
        for expected in ("贵州茅台", "600519", "2025-12-31", "年报", "2026-04-01", "巨潮资讯网", "原文"):
            self.assertTrue(any(expected in v for v in flat), f"缺少 {expected}: {flat}")

    def test_unavailable_writes_reason_and_failures(self):
        ws = self._write(
            _digest_data(
                available=False,
                reason="未配置 DataSinking API key",
                failures=[{"code": "600519", "name": "贵州茅台", "reason": "未取到财报"}],
            )
        )
        flat = self._flat(ws)
        self.assertTrue(any("未配置 DataSinking API key" in v for v in flat))
        self.assertTrue(any("未取到财报" in v for v in flat))

    def test_none_writes_placeholder(self):
        ws = self._write(None)
        flat = self._flat(ws)
        self.assertTrue(any("暂无可用财报数据" in v for v in flat))

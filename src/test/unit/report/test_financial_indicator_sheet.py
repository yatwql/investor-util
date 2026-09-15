"""财务指标页签 Excel 呈现测试。

覆盖：available=True → 标题 + 表头 + 数值格式（亿元/百分数/倍数）+ 失败清单；
available=False → 占位原因；None → 整页占位；缺失值写「—」而非 0。

运行：
  pytest src/test/unit/report/test_financial_indicator_sheet.py -v
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _indicator_data(**extra) -> dict:
    d = {
        "available": True,
        "reason": "",
        "entry_count": 1,
        "rows": [
            {
                "code": "600900",
                "name": "长江电力",
                "report_period": "2025-12-31",
                "doc_type": "annual",
                "doc_type_label": "年报",
                "source_api": "akshare_financial",
                "source": "akshare 财务指标",
                "revenue": 86_241_940_222.20,
                "net_profit": 34_502_809_176.39,
                "revenue_yoy": 0.0207,
                "net_profit_yoy": 0.0617,
                "gross_margin": 0.35,
                "roe": 0.159,
                "debt_ratio": 0.5827,
                "operating_cash_flow": 60_562_925_570.41,
                "eps": 1.4101,
                "bvps": 9.05,
                "pe": 20.21,
                "pb": 3.15,
                "quality_grade": "优",
                "quality_score": 2.75,
                "trend": "增长",
                "series": [],
                "period_count": 2,
            }
        ],
        "failures": [],
    }
    d.update(extra)
    return d


class TestExcelFinancialIndicatorSheet(unittest.TestCase):
    def _write(self, indicator_data):
        from openpyxl import Workbook

        from src.python.report.financial_indicator_sheet import write_financial_indicator_sheet

        wb = Workbook()
        ws = wb.active
        write_financial_indicator_sheet(ws, indicator_data)
        return ws

    def _flat(self, ws) -> list[str]:
        return [str(c.value) if c.value is not None else "" for row in ws.iter_rows() for c in row]

    def test_available_writes_header_and_formatted_values(self):
        ws = self._write(_indicator_data())
        flat = self._flat(ws)
        self.assertTrue(any("财务指标" in v for v in flat))
        for expected in ("长江电力", "600900", "2025-12-31", "年报", "862.42", "345.03", "605.63"):
            self.assertTrue(any(expected in v for v in flat), f"缺少 {expected}: {flat}")
        # 比率换算为百分数；倍数保留两位
        self.assertTrue(any("6.17%" in v for v in flat), flat)
        self.assertTrue(any("15.90%" in v for v in flat), flat)
        self.assertTrue(any("20.21" in v for v in flat), flat)
        self.assertTrue(any("优" in v for v in flat), flat)

    def test_missing_values_render_dash_not_zero(self):
        row = dict(_indicator_data()["rows"][0])
        row.update({"gross_margin": None, "pe": None, "quality_grade": "", "trend": ""})
        ws = self._write(_indicator_data(rows=[row]))
        flat = self._flat(ws)
        self.assertIn("—", flat, "缺失值应写「—」而非 0")

    def test_unavailable_writes_reason_and_failures(self):
        ws = self._write(
            _indicator_data(
                available=False,
                reason="未取到财务指标数据（数据源不可用或标的不在覆盖范围）",
                rows=[],
                entry_count=0,
                failures=[{"code": "600900", "name": "长江电力", "reason": "无指标数据"}],
            )
        )
        flat = self._flat(ws)
        self.assertTrue(any("数据源不可用" in v for v in flat))
        self.assertTrue(any("无指标数据" in v for v in flat))

    def test_none_writes_placeholder(self):
        ws = self._write(None)
        flat = self._flat(ws)
        self.assertTrue(any("暂无可用财务指标数据" in v for v in flat))

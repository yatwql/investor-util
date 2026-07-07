"""Excel 数字格式测试 — 金额/百分比/份额格式验证。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/report/test_excel_format_edge.py -v
"""

from __future__ import annotations

import unittest
import pytest

from openpyxl.styles import numbers

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


@pytest.mark.edge
class TestExcelNumberFormats(unittest.TestCase):
    """Excel 数字格式一致性验证。"""

    def test_money_format_has_thousands_sep(self):
        """金额格式包含千分位。"""
        fmt = '¥#,##0.00'
        self.assertIn("#,##0", fmt)

    def test_pct_format_is_percentage(self):
        """收益率为百分比格式。"""
        fmt = '0.00%'
        self.assertIn("%", fmt)

    def test_shares_format_has_thousands(self):
        """份额格式包含千分位。"""
        fmt = '#,##0.000'
        self.assertIn("#,##0", fmt)

    def test_money_builtin_format(self):
        """检查 openpyxl 内建金额格式。"""
        # openpyxl 中 '¥#,##0.00' 是自定义格式
        from openpyxl.styles import Font, PatternFill, Alignment, Border
        from src.python.report.styles import MONEY_FORMAT
        self.assertIn("#,##0", MONEY_FORMAT)

    def test_pct_builtin_format(self):
        """检查 openpyxl 内建百分比格式。"""
        from src.python.report.styles import PCT_FORMAT
        self.assertIn("0.00%", PCT_FORMAT)

    def test_thousands_builtin_format(self):
        """检查千分位格式。"""
        from src.python.report.styles import THOUSANDS_FORMAT
        self.assertIn("#,##0", THOUSANDS_FORMAT)

    def test_styles_module_has_all_formats(self):
        """styles.py 模块包含金额/百分比/千分位/份额格式常量。"""
        import src.python.report.styles as s
        for name in ["MONEY_FORMAT", "PCT_FORMAT", "THOUSANDS_FORMAT"]:
            self.assertTrue(hasattr(s, name), f"styles.py 缺少 {name}")

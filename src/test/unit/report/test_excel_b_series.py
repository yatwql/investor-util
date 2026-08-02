"""B 系列（基金深度分析）Excel 章节辅助函数单元测试。"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestExcelBSeries:
    """B 系列（基金深度分析）基础函数测试。"""

    def test_process_b_module_signature(self):
        """_process_b_module 可调用并返回 (list, dict) 元组。"""
        from src.python.report.excel_b_series import _process_b_module

        class _MockHolding:
            def __init__(self, code: str = "000001"):
                self.code = code
                self.name = code
                self.account = "主账户"

        class _MockProgress:
            def info(self, msg): pass

        holdings = [_MockHolding("600519")]
        result = _process_b_module(holdings, lambda h: h, _MockProgress())
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_write_b_series_disabled(self):
        """enable_fund_deep_analysis=False → 不写入任何内容（返回 None）。"""
        from src.python.report.excel_b_series import write_b_series_sheets

        result = write_b_series_sheets(
            sheets={},
            holdings=[],
            enable_fund_deep_analysis=False,
            data={},
            modules={},
            prog=type("_P", (), {"info": lambda s, m: None, "ok": lambda s, m: None, "add_error": lambda s, m: None})(),
        )
        assert result is None

"""penetration_sheet 边缘场景 — 降级占位与异常输入。

覆盖：穿透计算模块键缺失时的空 dict 占位传入（写入函数须优雅降级为
「暂无穿透数据」而非在键访问处抛 KeyError 导致整表写入失败）。
"""

from __future__ import annotations

import pytest
from openpyxl import Workbook

from src.python.report import penetration_sheet as ps

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


class TestPenetrationSheetEdge:
    """write_penetration_sheet 的空数据/占位输入降级行为。"""

    def test_empty_penetration_data_writes_placeholder_not_keyerror(self, caplog):
        """降级占位空 dict 传入 → 写「暂无穿透数据」，不抛 KeyError。"""
        import logging

        wb = Workbook()
        ws = wb.active

        with caplog.at_level(logging.WARNING):
            ps.write_penetration_sheet(ws, [], [], penetration_data={})

        text = "\n".join(str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None)
        assert "暂无穿透数据" in text

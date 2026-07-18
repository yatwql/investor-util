"""基金风格分析 Excel 写入模块 — 报告页签 16。

输出列：
  基金名称 | 基金代码 | 当前风格 | 上期风格 |
  漂移等级 | 漂移评分 | 备注
"""

from __future__ import annotations

import logging
from typing import Any

from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from src.python.registry import get_report_section_number, get_report_sheet_name
from src.python.report.data_status import STATUS_MESSAGES
from src.python.report.excel_writer import (
    _write_placeholder,
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.python.report.styles import NORMAL_FONT

logger = logging.getLogger("invest")

_NCOLS = 8
_HEADERS = [
    "基金名称",
    "基金代码",
    "当前风格",
    "上期风格",
    "漂移等级",
    "漂移评分",
    "备注",
    "标识",
]

_DRIFT_FONTS: dict[str, Font] = {
    "严重": Font(color="CC0000"),
    "中度": Font(color="FF8C00"),
    "轻度": Font(color="DAA520"),
}


def _drift_font(level: str) -> Font:
    return _DRIFT_FONTS.get(level, NORMAL_FONT)


def _remark(is_estimated: bool, is_first: bool) -> str:
    """生成备注列文本。"""
    if is_first:
        return "基准确立中"
    parts = []
    if is_estimated:
        parts.append("估算风格")
    return "；".join(parts) if parts else ""


def write_style_sheet(
    ws: Worksheet,
    style_data: list[dict[str, Any]],
) -> None:
    """写入基金风格分析页签。

    Args:
        ws: openpyxl Worksheet 对象
        style_data: analyze_style_for_all_funds 的结果中的 results 列表
    """
    _name = get_report_sheet_name("fund_style")
    write_title_row(ws, 1, f"{get_report_section_number('fund_style')}. {_name}", ncols=_NCOLS)
    write_header_row(ws, 2, _HEADERS)

    if not style_data:
        _write_placeholder(ws, STATUS_MESSAGES["style_unavailable"], row=4, max_cols=_NCOLS)
        freeze_header(ws, row=2)
        auto_width(ws)
        logger.info("基金风格分析：无数据，写入占位")
        return

    for i, item in enumerate(style_data, start=3):
        drift_level = item.get("drift_level", "")
        row_font = _drift_font(drift_level)
        is_first = item.get("is_first_check", False)

        row_data = [
            item.get("name", ""),
            item.get("code", ""),
            item.get("current_style", "--"),
            item.get("prev_style", "--"),
            drift_level,
            item.get("drift_score", "--") if item.get("drift_score") is not None else "--",
            _remark(item.get("is_estimated", False), is_first),
            "📋 基线" if is_first else "✅",
        ]
        write_data_row(ws, i, row_data)
        for col in range(1, _NCOLS + 1):
            ws.cell(row=i, column=col).font = row_font

    freeze_header(ws, row=2)
    auto_width(ws)
    logger.info("基金风格分析页签写入完成: %d 条", len(style_data))

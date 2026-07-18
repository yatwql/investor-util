"""基金经理变更监控 Excel 写入模块 — 报告页签 13。

输出列：
  基金名称 | 基金代码 | 当前基金经理 | 任职天数 | 1月内变更 | 3月内变更 | 6月内变更 | 预警级别
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
    "当前基金经理",
    "任职天数",
    "1月内变更",
    "3月内变更",
    "6月内变更",
    "预警级别",
]

# ── 预警级别字体 ─────────────────────────────────────────────

_ALERT_FONTS: dict[str, Font] = {
    "紧急": Font(color="CC0000"),  # 红色
    "关注": Font(color="FF8C00"),  # 暗橙色
    "首检": Font(color="808080"),  # 灰色
}


def _alert_font(level: str) -> Font:
    """根据预警级别返回行字体。"""
    return _ALERT_FONTS.get(level, NORMAL_FONT)


def _change_label(changed: bool, is_first: bool) -> str:
    """生成变更状态标签。"""
    if is_first:
        return "—"
    return "🔴 是" if changed else "✅ 否"


def write_fund_manager_sheet(
    ws: Worksheet,
    manager_data: list[dict[str, Any]],
) -> None:
    """写入基金经理变更监控页签。

    Args:
        ws: openpyxl Worksheet 对象
        manager_data: detect_manager_changes() 的返回结果
    """
    _name = get_report_sheet_name("fund_manager")
    write_title_row(ws, 1, f"{get_report_section_number('fund_manager')}. {_name}", ncols=_NCOLS)
    write_header_row(ws, 2, _HEADERS)

    if not manager_data:
        _write_placeholder(ws, STATUS_MESSAGES["manager_unavailable"], row=4, max_cols=_NCOLS)
        freeze_header(ws, row=2)
        auto_width(ws)
        logger.info("基金经理变更监控：无数据，写入占位")
        return

    for i, item in enumerate(manager_data, start=3):
        is_first = item.get("is_first_check", False)
        alert = item.get("alert_level", "正常")
        row_font = _alert_font(alert)

        row_data = [
            item.get("name", ""),
            item.get("code", ""),
            item.get("current_manager", "--"),
            str(item.get("tenure_days", 0)),
            _change_label(item.get("changed_1m", False), is_first),
            _change_label(item.get("changed_3m", False), is_first),
            _change_label(item.get("changed_6m", False), is_first),
            alert,
        ]
        write_data_row(ws, i, row_data)
        # 对整行应用颜色字体
        for col in range(1, _NCOLS + 1):
            ws.cell(row=i, column=col).font = row_font

    freeze_header(ws, row=2)
    auto_width(ws)
    logger.info("基金经理变更监控页签写入完成: %d 条", len(manager_data))

"""持仓集中度监控 Excel 写入模块 — 报告页签 15。

输出列：
  基金名称 | 基金代码 | 前3占比 | 前5占比 | 前10占比
  | 上期前10占比 | 环比变化 | 预警级别

着色规则：
  🔴 紧急 → 整行红色字体
  ⚠️ 关注 → 整行橙色字体
  ✅ 正常 → 默认字体
  首检 → 灰色字体
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

_NCOLS = 10
_HEADERS = [
    "基金名称",
    "基金代码",
    "基金类型",
    "前3占比%",
    "前5占比%",
    "前10占比%",
    "上期前10占比%",
    "环比变化",
    "预警级别",
    "标识",
]

# ── 预警字体 ────────────────────────────────────────────────

_ALERT_FONTS: dict[str, Font] = {
    "紧急": Font(color="CC0000"),
    "关注": Font(color="FF8C00"),
    "正常": Font(color="008000"),
}


def _alert_font(level: str) -> Font:
    return _ALERT_FONTS.get(level, NORMAL_FONT)


def _change_label(change_pct: float | None) -> str:
    """生成环比变化标签。"""
    if change_pct is None:
        return "基线已记录"
    sign = "+" if change_pct >= 0 else ""
    arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else "→"
    return f"{arrow} {sign}{change_pct:.2f}%"


def _flag_label(is_first: bool, alert_level: str) -> str:
    """生成标识列文本。"""
    if is_first:
        return "📋 基线已记录"
    if alert_level == "紧急":
        return "🔴 紧急"
    if alert_level == "关注":
        return "⚠️ 关注"
    return "✅ 正常"


def write_concentration_sheet(
    ws: Worksheet,
    concentration_data: list[dict[str, Any]],
) -> None:
    """写入持仓集中度监控页签。

    Args:
        ws: openpyxl Worksheet 对象
        concentration_data: compute_concentration() 的返回结果
    """
    _name = get_report_sheet_name("fund_concentration")
    write_title_row(ws, 1, f"{get_report_section_number('fund_concentration')}. {_name}", ncols=_NCOLS)
    write_header_row(ws, 2, _HEADERS)

    if not concentration_data:
        _write_placeholder(ws, STATUS_MESSAGES["concentration_unavailable"], row=4, max_cols=_NCOLS)
        freeze_header(ws, row=2)
        auto_width(ws)
        logger.info("持仓集中度监控：无数据，写入占位")
        return

    for i, item in enumerate(concentration_data, start=3):
        is_first = item.get("is_first_check", False)
        alert = item.get("alert_level", "正常")
        row_font = _alert_font(alert)
        change_pct = item.get("change_pct")

        row_data = [
            item.get("name", ""),
            item.get("code", ""),
            "",  # 基金类型（暂无细分类别）
            item.get("top3_pct", 0),
            item.get("top5_pct", 0),
            item.get("top10_pct", 0),
            item.get("prev_top10_pct", "--") if item.get("prev_top10_pct") is not None else "—",
            _change_label(change_pct),
            alert,
            _flag_label(is_first, alert),
        ]
        write_data_row(ws, i, row_data)
        # 对整行应用颜色字体
        for col in range(1, _NCOLS + 1):
            ws.cell(row=i, column=col).font = row_font

    freeze_header(ws, row=2)
    auto_width(ws)
    logger.info("持仓集中度监控页签写入完成: %d 条", len(concentration_data))

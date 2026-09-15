"""财务指标 Excel 页签 — 每只 A 股一行基本面指标。

数据来自 ``financial_indicator_data`` 契约（akshare 主源 / DataSinking 解析支路，
`功能开关 `financial_indicator`` 开关，默认关）。

金额列以「亿元」呈现（便于横向比较），比率列以百分数呈现；缺失值写「—」而非 0。
不可用时写占位文本（``available=False``，§1.4.5 数据降级治理）。
"""

from __future__ import annotations

import logging
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from src.python.core.registry import get_report_sheet_name
from src.python.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)

logger = logging.getLogger("invest")

_COLUMNS = [
    "名称",
    "代码",
    "报告期",
    "文种",
    "营收(亿)",
    "归母净利(亿)",
    "营收同比",
    "净利同比",
    "毛利率",
    "ROE",
    "负债率",
    "经营现金流(亿)",
    "每股收益",
    "每股净资产",
    "PE",
    "PB",
    "质量档",
    "年度趋势",
    "来源",
]

_DASH = "—"


def _yi(value: Any) -> str:
    """金额（元）→ 亿元字符串；缺失写「—」。"""
    if not isinstance(value, (int, float)):
        return _DASH
    return f"{value / 1e8:,.2f}"


def _pct(value: Any) -> str:
    """小数比例 → 百分数字符串（保留 2 位）；缺失写「—」。"""
    if not isinstance(value, (int, float)):
        return _DASH
    return f"{value * 100:.2f}%"


def _plain(value: Any, digits: int = 2) -> str:
    if not isinstance(value, (int, float)):
        return _DASH
    return f"{value:.{digits}f}"


def write_financial_indicator_sheet(ws: Worksheet, indicator_data: dict[str, Any] | None) -> None:
    """写入财务指标页签。

    Args:
        ws: openpyxl Worksheet 对象
        indicator_data: ``financial_indicator_data`` 契约 dict；
            None 或 ``available=False`` 时写占位文本。
    """
    name = get_report_sheet_name("financial_indicator")
    ncols = len(_COLUMNS)
    write_title_row(ws, 1, name, ncols=ncols)

    if not indicator_data or not indicator_data.get("available"):
        reason = (indicator_data or {}).get("reason") or "暂无可用财务指标数据"
        row = write_data_row(ws, 3, [reason] + [""] * (ncols - 1))
        for _f in (indicator_data or {}).get("failures", []) or []:
            row = write_data_row(
                ws,
                row,
                [f"{_f.get('name') or _f.get('code')}（{_f.get('code')}）：{_f.get('reason')}"] + [""] * (ncols - 1),
            )
        freeze_header(ws, row=2)
        auto_width(ws, min_width=10, max_width=40)
        logger.info("[financial_indicator] 财务指标页签写占位：%s", reason)
        return

    header = write_header_row(ws, 3, _COLUMNS)
    row = header
    for r in indicator_data.get("rows", []):
        row = write_data_row(
            ws,
            row,
            [
                r.get("name") or "",
                r.get("code") or "",
                r.get("report_period") or "",
                r.get("doc_type_label") or r.get("doc_type") or "",
                _yi(r.get("revenue")),
                _yi(r.get("net_profit")),
                _pct(r.get("revenue_yoy")),
                _pct(r.get("net_profit_yoy")),
                _pct(r.get("gross_margin")),
                _pct(r.get("roe")),
                _pct(r.get("debt_ratio")),
                _yi(r.get("operating_cash_flow")),
                _plain(r.get("eps"), 4),
                _plain(r.get("bvps")),
                _plain(r.get("pe")),
                _plain(r.get("pb")),
                r.get("quality_grade") or _DASH,
                r.get("trend") or _DASH,
                r.get("source") or "",
            ],
        )

    for _f in indicator_data.get("failures", []) or []:
        row = write_data_row(
            ws,
            row,
            [f"{_f.get('name') or _f.get('code')}（{_f.get('code')}）：{_f.get('reason')}"] + [""] * (ncols - 1),
        )

    freeze_header(ws, row=3)
    auto_width(ws, min_width=10, max_width=40)
    logger.info("[financial_indicator] 财务指标页签已写入 %d 行", len(indicator_data.get("rows", [])))

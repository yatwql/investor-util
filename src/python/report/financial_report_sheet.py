"""持仓个股财报摘要 Excel 页签 — 每只 A 股一行财报章节摘要。

数据来自 ``financial_report_digest_data`` 契约（DataSinking 全文本财报，
`功能开关 `financial_report_digest`` 开关，默认关）。

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

_COLUMNS = ["名称", "代码", "报告期", "文种", "标题", "披露日", "摘要", "来源", "原文链接"]


def write_financial_report_sheet(ws: Worksheet, digest_data: dict[str, Any] | None) -> None:
    """写入持仓个股财报摘要页签。

    Args:
        ws: openpyxl Worksheet 对象
        digest_data: ``financial_report_digest_data`` 契约 dict；
            None 或 ``available=False`` 时写占位文本。
    """
    name = get_report_sheet_name("financial_report_digest")
    ncols = len(_COLUMNS)
    write_title_row(ws, 1, name, ncols=ncols)

    if not digest_data or not digest_data.get("available"):
        reason = (digest_data or {}).get("reason") or "暂无可用财报数据"
        row = write_data_row(ws, 3, [reason] + [""] * (ncols - 1))
        for _f in (digest_data or {}).get("failures", []) or []:
            row = write_data_row(
                ws,
                row,
                [f"{_f.get('name') or _f.get('code')}（{_f.get('code')}）：{_f.get('reason')}"] + [""] * (ncols - 1),
            )
        freeze_header(ws, row=2)
        auto_width(ws, min_width=10, max_width=40)
        logger.info("持仓个股财报摘要：无可用数据，写入占位")
        return

    rows = digest_data.get("rows", []) or []
    row = write_header_row(ws, 2, _COLUMNS)
    for item in rows:
        row = write_data_row(
            ws,
            row,
            [
                item.get("name", ""),
                item.get("code", ""),
                item.get("report_period", ""),
                item.get("doc_type", ""),
                item.get("title", ""),
                item.get("announcement_date", ""),
                item.get("summary", ""),
                item.get("source", ""),
                item.get("adjunct_url", ""),
            ],
        )

    failures = digest_data.get("failures", []) or []
    if failures:
        row += 1
        row = write_title_row(ws, row, "未取到财报的标的", ncols=ncols)
        for item in failures:
            row = write_data_row(
                ws,
                row,
                [f"{item.get('name') or item.get('code')}（{item.get('code')}）：{item.get('reason')}"]
                + [""] * (ncols - 1),
            )

    row += 1
    row = write_title_row(ws, row, "说明", ncols=ncols)
    for note in (
        "数据来源：DataSinking 全文本财报（请保留披露平台归属）；仅覆盖 A 股（沪深京）",
        "摘要为报告章节正文截断，完整内容见原文链接；具体取用章节与截断长度见 config.json 的 datasink 段",
    ):
        row = write_data_row(ws, row, [note] + [""] * (ncols - 1))

    freeze_header(ws, row=2)
    auto_width(ws, min_width=10, max_width=48)
    logger.info("持仓个股财报摘要页签写入完成: %d 只标的（失败 %d）", len(rows), len(failures))

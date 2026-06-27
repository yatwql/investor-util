"""LLM 内容输出模块 — 报告第 7、8 页。

由调用方预生成 LLM 内容后传入本模块写入 Excel 页签。
"""

from __future__ import annotations

import logging
import re

from openpyxl.worksheet.worksheet import Worksheet

from src.report.excel_writer import (
    auto_width,
    freeze_header,
    write_title_row,
)

logger = logging.getLogger("invest")

# ── 内容区合并单元格的范围 ───────────────────────────────────
_CONTENT_MERGE_END_ROW = 50
_CONTENT_NCOLS = 2


def _strip_html(text: str) -> str:
    """移除文本中的 HTML 标签，保留纯文本内容。"""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _write_content_sheet(
    ws: Worksheet,
    title: str,
    content: str | None,
) -> None:
    """写入一个 LLM 内容页签。

    结构：
      - 第 1 行：标题（合并 A1:B1，居中标题样式）
      - 第 2 行起：写入内容到合并的 A2:B{_CONTENT_MERGE_END_ROW} 单元格

    Args:
        ws: 目标工作表
        title: 页签标题行文本
        content: LLM 返回的 HTML 文本（已剥离标签），为 None 时写入占位符
    """
    ws.title = title

    # 标题行
    row = write_title_row(ws, 1, title, _CONTENT_NCOLS)

    # 内容区：合并 A{row}:B{_CONTENT_MERGE_END_ROW}
    merge_end_row = max(row + 1, _CONTENT_MERGE_END_ROW)
    ws.merge_cells(
        start_row=row,
        start_column=1,
        end_row=merge_end_row,
        end_column=_CONTENT_NCOLS,
    )

    if content:
        text = _strip_html(content)
        ws.cell(row=row, column=1, value=text)
    else:
        placeholder = (
            "本节内容待生成 — 请配置 LLM API Key（data/config/llm.json）"
        )
        ws.cell(row=row, column=1, value=placeholder)

    # 设列宽，冻结标题行
    auto_width(ws, min_width=20, max_width=100)
    freeze_header(ws, 1)


def write_llm_sheets(
    wb: Any,
    llm_content: tuple[str | None, str | None],
) -> tuple[str, str]:
    """写入 LLM 内容页签（模块 7 & 8）。

    调用方必须预先生成 llm_content，本函数仅负责写入 Excel。

    Args:
        wb: 工作簿
        llm_content: (macro_html, expert_html) 预生成内容，各可能为 None

    Returns:
        (macro_text, expert_text) 纯文本二元组，供 TUI 展示
    """
    ws7 = wb.create_sheet()
    ws7.title = "全球政经局势"
    ws8 = wb.create_sheet()
    ws8.title = "智囊团深度复盘"

    content7, content8 = llm_content

    _write_content_sheet(ws7, "全球政经局势", content7)
    _write_content_sheet(ws8, "智囊团深度复盘", content8)

    logger.info("LLM 内容页签写入完成")

    # 返回纯文本内容，供 TUI 展示
    return _strip_html(content7) if content7 else "", _strip_html(content8) if content8 else ""

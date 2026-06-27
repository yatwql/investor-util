"""LLM 内容输出模块 — 报告第 7、8 页。

调用 LLM 客户端生成"全球政经局势分析"和"智囊团深度复盘"文本，
写入 Excel 页签的合并单元格中。LLM 不可用时写入占位提示。

模块 7（全球政经局势）：
  调用 generate_global_macro()，传入指数行情 + 持仓概览。

模块 8（智囊团深度复盘）：
  调用 generate_expert_review()，传入持仓盈亏 + 穿透 TOP10 资产。
"""

from __future__ import annotations

import logging
import re
from typing import Any, List

from openpyxl.worksheet.worksheet import Worksheet

from src.fetcher import fetch_indices, fetch_us_indices
from src.llm_client import generate_all_llm
from src.models import Holding
from src.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_title_row,
)
from src.report.market_value import DetailRow
from src.report.penetration import compute_penetration_top10

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
    holdings: List[Holding],
    details: List[DetailRow],
    output_dir: str,
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    categories: dict,
    penetration_data: dict | None = None,
    force_llm: bool = False,
    llm_content: tuple[str | None, str | None] | None = None,
    a_indices: list[dict] | None = None,
    us_indices: list[dict] | None = None,
) -> tuple[str, str]:
    """写入 LLM 内容页签（模块 7 & 8）。

    创建两个页签：
      - "全球政经局势"：调用 LLM 生成全球宏观经济分析
      - "智囊团深度复盘"：调用 LLM 生成持仓复盘与优化建议

    Args:
        llm_content: 可选预生成内容 (macro_html, expert_html)，
            传入时跳过内部 LLM 调用直接使用此内容。
        a_indices: 可选预获取的 A 股指数，传入时跳过内部指数行情获取。
        us_indices: 可选预获取的美股指数，传入时跳过内部指数行情获取。

    Returns:
        (macro_text, expert_text) 纯文本二元组，供 TUI 展示
    """
    ws7 = wb.create_sheet()
    ws7.title = "全球政经局势"
    ws8 = wb.create_sheet()
    ws8.title = "智囊团深度复盘"

    # ── 模块 7 & 8：LLM 生成 ────────────────────────────
    if llm_content is not None:
        # 使用外部传入的预生成内容（避免重复调用 LLM）
        content7, content8 = llm_content
    else:
        try:
            # 获取指数行情（优先复用外部传入数据）
            if a_indices is not None and us_indices is not None:
                a_indices_local = a_indices
                us_indices_local = us_indices
            else:
                a_idx_dict = fetch_indices()
                us_idx_dict = fetch_us_indices()
                a_indices_local = list(a_idx_dict.values())
                us_indices_local = list(us_idx_dict.values())

            # 获取穿透 TOP10 资产数据
            if penetration_data is not None:
                penetrated_assets = penetration_data.get("top10")
            else:
                penetrated = compute_penetration_top10(holdings, details)
                penetrated_assets = penetrated.get("top10")

            # 构建持仓明细（供 LLM 引用具体品种，防止虚构代码）
            holdings_details = [
                {
                    "name": d.name,
                    "code": d.code,
                    "market_value": d.market_value,
                    "cost": d.cost,
                    "profit": d.profit,
                    "profit_rate": d.profit_rate,
                    "change_pct": (
                        (d.price - d.yesterday_close) / d.yesterday_close * 100
                        if d.yesterday_close and abs(d.yesterday_close) > 1e-10
                        else 0.0
                    ),
                }
                for d in details
            ]

            # 调用 LLM
            content7, content8 = generate_all_llm(
                a_indices=a_indices_local,
                us_indices=us_indices_local,
                total_mv=total_mv,
                total_cost=total_cost,
                total_profit=total_profit,
                total_today_profit=total_today_profit,
                holdings_count=len(holdings),
                categories=categories,
                penetrated_assets=penetrated_assets,
                holdings_details=holdings_details,
                force=force_llm,
            )
        except Exception:
            logger.warning("LLM 内容生成失败", exc_info=True)
            content7 = content8 = None

    _write_content_sheet(ws7, "全球政经局势", content7)
    _write_content_sheet(ws8, "智囊团深度复盘", content8)

    logger.info("LLM 内容页签写入完成")

    # 返回纯文本内容，供 TUI 展示
    return _strip_html(content7) if content7 else "", _strip_html(content8) if content8 else ""

"""财经新闻热点与持仓关联分析模块 — 报告增补页签。

从新浪财经获取最新新闻，与持仓名称/代码进行关键词匹配，
按关联度排序输出 TOP 100，在 Excel 中以单独页签呈现。

输出列：
  序号 | 新闻标题 | 摘要 | 来源 | 发布时间 | 关联关键词
"""

from __future__ import annotations

import logging
from typing import Any, List

from openpyxl.worksheet.worksheet import Worksheet

from src.models import Holding
from src.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)

logger = logging.getLogger("invest")

_NCOLS = 6
_HEADERS = [
    "序号", "新闻标题", "摘要", "来源", "发布时间", "关联关键词",
]


def build_news_data(holdings: List[Holding], top_n: int = 100) -> List[dict[str, Any]]:
    """获取新闻数据并与持仓关联。

    调用 sina_news 模块获取最新财经新闻，
    与持仓名称/代码进行关键词匹配，
    按关联度排序返回 TOP N。

    Args:
        holdings: 持仓列表
        top_n: 最多返回的关联新闻条数

    Returns:
        [{title, intro, url, ctime, media_name, matched_keywords}, ...]
        获取失败返回 []
    """
    from src.providers.sina_news import build_holding_keywords, fetch_and_correlate

    keywords = build_holding_keywords(holdings)
    logger.info("新闻关联关键词: %s", keywords)

    news_items = fetch_and_correlate(keywords, top_n=top_n)
    if news_items:
        logger.info("新闻关联完成: 获取 %d 条, 匹配 %d 条",
                    len(news_items), sum(1 for n in news_items if n.get("matched_keywords")))
    else:
        logger.warning("新闻获取失败")

    return news_items


def write_news_sheet(ws: Worksheet, news_data: List[dict[str, Any]]) -> None:
    """写入财经新闻热点与持仓关联分析页签。

    这是 Excel 的增补页签（仅在 N 选项时生成）。

    Args:
        ws: 目标工作表
        news_data: build_news_data() 返回的数据
    """
    ws.title = "财经新闻热点"

    row = write_title_row(ws, 1, "财经新闻热点与持仓关联分析", _NCOLS)
    row = write_header_row(ws, row, _HEADERS)

    if not news_data:
        write_data_row(ws, row, ["暂无关联新闻"])
        logger.info("新闻关联分析：无数据")
        freeze_header(ws, 2)
        auto_width(ws)
        return

    for idx, item in enumerate(news_data, 1):
        # Format matched keywords as comma-separated string
        keywords_str = ", ".join(item.get("matched_keywords", []))

        vals = [
            idx,
            item.get("title", ""),
            item.get("intro", ""),
            item.get("media_name", ""),
            item.get("ctime", ""),
            keywords_str,
        ]
        write_data_row(ws, row, vals)
        row += 1

    # Add note
    row += 1
    write_data_row(ws, row, [
        f"共获取 {len(news_data)} 条关联新闻，关键词匹配基于持仓名称和代码"
    ])

    freeze_header(ws, 2)
    auto_width(ws)
    logger.info("新闻关联分析页签写入完成，共 %d 条", len(news_data))

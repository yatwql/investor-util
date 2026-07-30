"""新闻页签写入模块。

职责：财经新闻页签获取/写入。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.python.core.logger import setup_logger
from src.python.core.registry import get_llm_module_name
from src.python.report.progress import ProgressReporter

logger = setup_logger()


def write_news_sheet(
    sheets: dict[str, Any],
    holdings: list,
    pen_result: dict,
    include_news: bool,
    news_data: list | None,
    news_llm_meta: dict | None,
    news_top_count: int,
    prog: ProgressReporter,
) -> None:
    """写入新闻页签。"""
    if not include_news:
        return
    penetrated_assets = pen_result.get("top10", []) if pen_result else []

    write_news_sheet: Callable[..., Any] | None
    try:
        from src.python.report.news_correlation import write_news_sheet
    except ImportError:
        write_news_sheet = None
        prog.add_error(f"{get_llm_module_name('news_correlation')}模块缺失 (news_correlation)")

    if news_data is not None:
        logger.info("复用预取的新闻数据，共 %d 条", len(news_data))
        _meta = news_llm_meta or {}
        prog.ok(f"复用预取新闻数据（{len(news_data)} 条）")
    else:
        prog.info("正在获取财经新闻（含穿透资产关键词）...")
        build_news_data: Callable[..., Any] | None
        try:
            from src.python.report.news_correlation import build_news_data
        except ImportError:
            build_news_data = None
        if build_news_data is not None:
            try:
                news_data, _meta = build_news_data(holdings, top_n=news_top_count, penetrated_assets=penetrated_assets)
            except Exception:
                prog.add_error("新闻数据获取失败（详情请查看日志）")
                news_data, _meta = [], {}
        else:
            prog.add_error(f"{get_llm_module_name('news_correlation')}数据模块缺失")
            news_data, _meta = [], {}

    prog.call_sheet(
        get_llm_module_name("news_correlation"), write_news_sheet, sheets["news_correlation"], news_data, llm_meta=_meta
    )

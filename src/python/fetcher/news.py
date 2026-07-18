"""新闻数据获取封装层 — 提供统一的新闻获取接口。

职责：
  封装 ``providers/news_aggregator`` 和 ``providers/news_keywords`` 的
  底层实现，为报告层提供整洁的获取接口。报告模块应从此模块而非直接导入
  ``providers.news_*``，遵循 report/ → fetcher/ → providers/ 的
  架构分层约束。

当前封装函数：
  - aggregate_news — 多源新闻获取聚合
  - build_holding_keywords — 持仓关键词构建
  - get_last_source_status — 各新闻源状态查询
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.python.models import Holding
from src.python.providers.news_aggregator import (
    aggregate_news as _aggregate_news,
)
from src.python.providers.news_aggregator import (
    get_last_source_status as _get_last_source_status,
)
from src.python.providers.news_keywords import build_holding_keywords as _build_holding_keywords

__all__ = [
    "aggregate_news",
    "build_holding_keywords",
    "get_last_source_status",
]


def aggregate_news(
    keywords: list[str],
    top_n: int = 100,
    sources: list[str] | None = None,
    per_source: int = 100,
    progress_callback: Callable[[str, int, str], None] | None = None,
    lightweight_keywords: set[str] | None = None,
) -> list[dict[str, Any]]:
    """从多个新闻源获取新闻，去重后按关键词关联度排序。

    委托给 ``providers.news_aggregator.aggregate_news``。

    Args:
        keywords: 关键词列表
        top_n: 最多返回的关联新闻条数
        sources: 要使用的新闻源名称列表，默认使用全部启用的源
        per_source: 每个源获取的原始新闻条数
        progress_callback: 可选进度回调
        lightweight_keywords: 轻量级关键词集合

    Returns:
        关联新闻列表
    """
    return _aggregate_news(
        keywords=keywords,
        top_n=top_n,
        sources=sources,
        per_source=per_source,
        progress_callback=progress_callback,
        lightweight_keywords=lightweight_keywords,
    )


def build_holding_keywords(
    holdings: list[Holding],
    penetrated_assets: list[dict] | None = None,
    max_keywords: int = 50,
) -> list[str]:
    """从持仓和穿透 TOP10 资产提取关键词。

    委托给 ``providers.news_keywords.build_holding_keywords``。

    Args:
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产列表
        max_keywords: 最多返回的关键词数量

    Returns:
        关键词列表
    """
    return _build_holding_keywords(holdings, penetrated_assets=penetrated_assets, max_keywords=max_keywords)


def get_last_source_status() -> dict[str, dict]:
    """返回上次 aggregate_news() 调用的各源状态字典。

    委托给 ``providers.news_aggregator.get_last_source_status``。

    Returns:
        {source_key: {"label": str, "success": bool, "count": int, "error": str | None}}
    """
    return _get_last_source_status()

"""东方财富新闻 API — 通过 JSON 推送接口获取财经新闻列表。

从东方财富 push-api 获取最新新闻列表（JSON），
每条包含标题、摘要、链接、时间、来源等信息。

数据来源：https://push-api-html.eastmoney.com/app/news/list
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("invest")

_TIMEOUT = 15.0
_API_URL = "https://push-api-html.eastmoney.com/app/news/list"

_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.eastmoney.com",
}


def _parse_news_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """解析单条新闻 JSON 条目为统一格式。

    Args:
        item: API 返回的新闻条目字典

    Returns:
        结构化新闻字典，解析失败返回 None
    """
    title = (item.get("title") or "").strip()
    if not title:
        return None

    return {
        "title": title,
        "intro": (item.get("content") or "").strip(),
        "url": (item.get("articleUrl") or "").strip(),
        "ctime": (item.get("showTime") or "").strip(),
        "media_name": (item.get("source") or "东方财富").strip(),
    }


def fetch_news(num: int = 50) -> list[dict[str, Any]]:
    """从东方财富 JSON 推送接口获取财经新闻列表。

    Args:
        num: 需要获取的新闻条数（pageSize）

    Returns:
        结构化新闻列表（可能少于 num 条），获取失败返回空列表
    """
    params = {
        "type": "web",
        "pageIndex": 1,
        "pageSize": num,
    }

    try:
        with httpx.Client(timeout=_TIMEOUT, verify=False) as client:
            resp = client.get(_API_URL, headers=_HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning("东方财富新闻 API 请求失败: %s", e)
        return []
    except ValueError as e:
        logger.warning("东方财富新闻 API 返回非 JSON 数据: %s", e)
        return []

    items: list[dict[str, Any]] = []
    raw_list = (data.get("data") or {}).get("list") or []
    for raw_item in raw_list:
        parsed = _parse_news_item(raw_item)
        if parsed is not None:
            items.append(parsed)

    logger.info("东方财富新闻获取成功: %d 条", len(items))
    return items

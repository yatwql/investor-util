"""东方财富新闻 API — 通过快讯接口获取财经新闻列表。

从 np-weblist 快讯接口获取最新新闻列表（JSON），
每条包含标题、摘要、链接、时间等信息。

数据来源：https://np-weblist.eastmoney.com/comm/web/getFastNewsList
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_TIMEOUT = 15.0
_API_URL = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"

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

    # 文章链接由 code 拼接：https://finance.eastmoney.com/a/{code}.html
    code = (item.get("code") or "").strip()
    url = f"https://finance.eastmoney.com/a/{code}.html" if code else ""

    return {
        "title": title,
        "intro": (item.get("summary") or "").strip(),
        "url": url,
        "ctime": (item.get("showTime") or "").strip(),
        "media_name": "东方财富",
    }


def fetch_news(num: int = 50) -> list[dict[str, Any]]:
    """从东方财富快讯接口获取财经新闻列表。

    Args:
        num: 需要获取的新闻条数（pageSize）

    Returns:
        结构化新闻列表（可能少于 num 条），获取失败返回空列表
    """
    params = {
        "client": "web",
        "biz": "web_724",
        "fastColumn": "102",
        "sortEnd": "",
        "pageSize": str(num),
        "req_trace": str(int(time.time() * 1000)),
    }

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(_API_URL, headers=_HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning("东方财富新闻 API 请求失败: %s", e)
        return []
    except ValueError as e:
        logger.warning("东方财富新闻 API 返回非 JSON 数据: %s", e)
        return []

    # 新接口响应结构：{code: 0|1, message: "...", data: {fastNewsList: [...]}}
    # code 值不稳定（有时 0 有时 1），以 data.fastNewsList 存在为准
    raw_list = (data.get("data") or {}).get("fastNewsList")
    if not raw_list:
        logger.warning("东方财富新闻 API 返回空列表: code=%s, message=%s",
                       data.get("code"), data.get("message"))
        return []

    items: list[dict[str, Any]] = []
    for raw_item in raw_list:
        parsed = _parse_news_item(raw_item)
        if parsed is not None:
            items.append(parsed)

    logger.info("东方财富新闻获取成功: %d 条", len(items))
    return items

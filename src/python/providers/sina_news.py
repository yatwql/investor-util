"""新浪财经新闻 API — 获取财经新闻并与持仓关键词关联。

Endpoint: https://feed.mix.sina.com.cn/api/roll/get
支持多个新闻分类（财经要闻、国内财经、国际财经），
通过标题/简介关键词匹配实现与持仓的自动关联。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.python.http_client import make_http_client
from src.python.providers._utils import ts_to_str

logger = logging.getLogger("invest")

_BASE_URL = "https://feed.mix.sina.com.cn/api/roll/get"
_TIMEOUT = 15.0

# 新闻分类
_LID_MAP: dict[str, str] = {
    "2516": "财经要闻",
    "2509": "国内财经",
    "2510": "国际财经",
}

_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn",
}


def _parse_news_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """解析单条新闻项，提取结构化字段。

    Args:
        item: 原始 API 返回的新闻 dict

    Returns:
        结构化新闻 dict，包含 title, intro, url, ctime, media_name
        无效数据返回 None
    """
    title = (item.get("title") or "").strip()
    url = (item.get("url") or "").strip()
    if not title or not url:
        return None

    raw_ctime = item.get("ctime")
    try:
        ctime_str = ts_to_str(int(float(raw_ctime))) if raw_ctime is not None else ""
    except (TypeError, ValueError):
        ctime_str = ""

    return {
        "title": title,
        "intro": (item.get("intro") or "").strip(),
        "url": url,
        "ctime": ctime_str,
        "media_name": (item.get("media_name") or "").strip(),
    }


def fetch_news(lid: str = "2516", num: int = 30, page: int = 1) -> list[dict[str, Any]]:
    """从新浪财经获取新闻列表。

    Args:
        lid: 分类 ID (2516=财经要闻, 2509=国内财经, 2510=国际财经)
        num: 每页条数
        page: 页码

    Returns:
        结构化新闻列表，每项包含 title, intro, url, ctime, media_name
        获取失败时返回空列表
    """
    params: dict[str, Any] = {
        "pageid": "153",
        "lid": lid,
        "k": "",
        "num": num,
        "page": page,
    }

    category = _LID_MAP.get(lid, lid)
    logger.debug("Sina 新闻请求: %s (分类=%s, num=%d, page=%d)", lid, category, num, page)

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(_BASE_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.warning("Sina 新闻 API 超时 (lid=%s)", lid)
        return []
    except httpx.RequestError as e:
        logger.warning("Sina 新闻 API 请求失败: %s", e)
        return []
    except ValueError as e:
        logger.warning("Sina 新闻 API 响应 JSON 解析失败: %s", e)
        return []

    # 提取 result.data 列表
    result = data.get("result")
    if not isinstance(result, dict):
        logger.warning("Sina 新闻 API 响应缺少 result 字段")
        return []

    raw_items = result.get("data")
    if not isinstance(raw_items, list):
        logger.debug("Sina 新闻 API: data 为空或非列表 (lid=%s)", lid)
        return []

    parsed: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        parsed_item = _parse_news_item(item)
        if parsed_item:
            parsed.append(parsed_item)

    logger.info("Sina 新闻获取成功: 分类=%s, 获取 %d 条", category, len(parsed))
    return parsed

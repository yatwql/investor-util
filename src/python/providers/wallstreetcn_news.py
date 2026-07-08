"""华尔街见闻新闻 API — 获取财经新闻并与持仓关键词关联。

Endpoint: https://api-one.wallstcn.com/apiv1/content/lives
提供全球财经直播流（global-channel），包含宏观经济、股市、商品等实时资讯。
无鉴权要求，返回结构化 JSON 数据。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_BASE_URL = "https://api-one.wallstcn.com/apiv1/content/lives"
_TIMEOUT = 15.0

_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://wallstreetcn.com/live/global",
}


def _ts_to_str(ts: int) -> str:
    """将 Unix 时间戳（秒）转换为格式化的日期字符串。

    WallStreetCN API 返回的时间戳为 UTC 时区，转换为北京时间（UTC+8）。

    Args:
        ts: Unix 时间戳（秒）

    Returns:
        "YYYY-MM-DD HH:MM" 格式的字符串
    """
    try:
        bj_tz = timezone(timedelta(hours=8))
        dt = datetime.fromtimestamp(ts, tz=bj_tz)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return ""


def _parse_news_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """解析单条新闻项，提取结构化字段。

    WallStreetCN API 返回的直播流数据格式：
      - title: 标题
      - content_text: 正文内容（可能包含 HTML 标签）
      - display_time: Unix 时间戳（秒）
      - uri: 详情页路径

    Args:
        item: 原始 API 返回的新闻 dict

    Returns:
        结构化新闻 dict，包含 title, intro, url, ctime, media_name
        无效数据返回 None
    """
    title = (item.get("title") or "").strip()
    if not title:
        # 有些直播流条目可能没有标题，用内容前 40 字替代
        content_text = (item.get("content_text") or "").strip()
        if content_text:
            title = content_text[:40] + ("…" if len(content_text) > 40 else "")
        else:
            return None

    content_text = (item.get("content_text") or "").strip()
    # 去除 HTML 标签（如有）
    import re
    intro = re.sub(r"<[^>]+>", "", content_text).strip()
    # 限制摘要长度
    if len(intro) > 300:
        intro = intro[:300] + "…"

    raw_ctime = item.get("display_time")
    try:
        ctime_str = _ts_to_str(int(raw_ctime))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        ctime_str = ""

    # uri 可能是相对路径 "/live/xxxxx"，拼接完整 URL
    uri = (item.get("uri") or "").strip()
    url = f"https://wallstreetcn.com{uri}" if uri and not uri.startswith("http") else uri or ""

    return {
        "title": title,
        "intro": intro,
        "url": url,
        "ctime": ctime_str,
        "media_name": "华尔街见闻",
    }


def fetch_news(num: int = 50) -> list[dict[str, Any]]:
    """从华尔街见闻获取全球财经直播流新闻。

    Args:
        num: 获取条数（最大 100）

    Returns:
        结构化新闻列表，每项包含 title, intro, url, ctime, media_name
        获取失败时返回空列表
    """
    params: dict[str, Any] = {
        "channel": "global-channel",
        "limit": min(num, 100),  # API 限制最大 100
    }

    logger.debug("WallStreetCN 新闻请求: limit=%d", params["limit"])

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(_BASE_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.warning("WallStreetCN 新闻 API 超时")
        return []
    except httpx.RequestError as e:
        logger.warning("WallStreetCN 新闻 API 请求失败: %s", e)
        return []
    except ValueError as e:
        logger.warning("WallStreetCN 新闻 API 响应 JSON 解析失败: %s", e)
        return []

    # 提取 data.items 列表
    raw_items = data.get("data", {}).get("items")
    if not isinstance(raw_items, list):
        logger.debug("WallStreetCN 新闻 API: items 为空或非列表")
        return []

    parsed: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        parsed_item = _parse_news_item(item)
        if parsed_item:
            parsed.append(parsed_item)

    logger.info("WallStreetCN 新闻获取成功: 获取 %d 条", len(parsed))
    return parsed

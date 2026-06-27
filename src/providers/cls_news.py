"""财联社财经新闻 API — 获取财经新闻。

Endpoint: https://www.cls.cn/v1/roll/get_roll_list
财联社提供 7×24 小时实时财经快讯，
与新浪财经/东方财富互为补充源。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger("invest")

_BASE_URL = "https://www.cls.cn/v1/roll/get_roll_list"
_TIMEOUT = 15.0

_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.cls.cn",
}


def _ts_to_str(ts: int) -> str:
    """将 Unix 时间戳（秒）转换为格式化的日期字符串。

    CLS API 返回的时间戳为北京时间（UTC+8）。

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
    """解析单条新闻项。

    Args:
        item: 原始 API 返回的新闻 dict

    Returns:
        结构化新闻 dict（title, intro, url, ctime, media_name），无效返回 None
    """
    title = (item.get("title") or "").strip()
    url = (item.get("shareurl") or item.get("url") or "").strip()
    if not title or not url:
        return None

    # 时间戳处理
    raw_ctime = item.get("ctime")
    if raw_ctime:
        try:
            ctime_str = _ts_to_str(int(raw_ctime))
        except (TypeError, ValueError):
            ctime_str = ""
    else:
        ctime_str = ""

    return {
        "title": title,
        "intro": (item.get("brief") or item.get("intro") or "").strip(),
        "url": url,
        "ctime": ctime_str,
        "media_name": "财联社",
    }


def fetch_news(num: int = 50) -> list[dict[str, Any]]:
    """从财联社获取新闻列表。

    Args:
        num: 获取条数

    Returns:
        结构化新闻列表，每项包含 title, intro, url, ctime, media_name
        获取失败时返回空列表
    """
    params: dict[str, Any] = {
        "app": "CailianpressWeb",
        "os": "web",
        "sv": "8.4.0",
        "rn": num,
        "type": "all",
    }

    logger.debug("财联社新闻请求: num=%d", num)

    try:
        with httpx.Client(timeout=_TIMEOUT, verify=False) as client:
            resp = client.get(_BASE_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.warning("财联社新闻 API 超时")
        return []
    except httpx.RequestError as e:
        logger.warning("财联社新闻 API 请求失败: %s", e)
        return []
    except ValueError as e:
        logger.warning("财联社新闻 API 响应 JSON 解析失败: %s", e)
        return []

    # 提取 data.roll_data
    outer_data = data.get("data")
    if not isinstance(outer_data, dict):
        errno = data.get("errno", "")
        if errno == "10012":
            logger.warning("财联社新闻 API 需要签名鉴权（errno=10012），当前不可用")
        else:
            logger.warning("财联社新闻 API 响应缺少 data 字段 (errno=%s)", errno)
        return []

    raw_items = outer_data.get("roll_data")
    if not isinstance(raw_items, list):
        logger.debug("财联社新闻 API: roll_data 为空或非列表")
        return []

    parsed: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        parsed_item = _parse_news_item(item)
        if parsed_item:
            parsed.append(parsed_item)

    logger.info("财联社新闻获取成功: %d 条", len(parsed))
    return parsed

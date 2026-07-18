"""akshare 财经新闻聚合 — 通过 akshare 间接获取多源财经新闻。

akshare 是一个开源 Python 财经数据接口库，底层封装了东方财富、财新、
新浪等多家数据源。本模块通过 akshare 获取以下新闻渠道：

  1. 财新网要闻（stock_news_main_cx）— 财经前瞻/要闻
  2. CCTV 新闻（news_cctv）        — 央视财经新闻

无需鉴权，akshare 自动处理底层数据源适配。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("invest")

_TIMEOUT = 30.0

# 央视新闻每天条数较少，仅作为补充
_MAX_CCTV = 17


def _fetch_from_caixin(num: int = 100) -> list[dict[str, Any]]:
    """从财新网获取要闻（通过 akshare 封装）。

    使用 ak.stock_news_main_cx() 获取财新网要闻列表。

    Args:
        num: 获取条数上限（财新 API 返回最多 100 条）

    Returns:
        结构化新闻列表，每项包含 title, intro, url, ctime, media_name
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 模块未安装，跳过财新新闻")
        return []

    try:
        df = ak.stock_news_main_cx()
    except Exception as e:
        logger.warning("财新新闻 (akshare) 获取失败: %s", e)
        return []

    if df is None or df.empty:
        logger.debug("财新新闻: 结果为空")
        return []

    bj_tz = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj_tz)
    today_str = now_bj.strftime("%Y-%m-%d")

    parsed: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for _, row in df.iterrows():
        tag = str(row.get("tag") or "").strip()
        summary = str(row.get("summary") or "").strip()
        url = str(row.get("url") or "").strip()

        if not summary and not url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # 用 tag + summary 前 40 字作为标题
        title_parts = [tag] if tag else []
        title_text = summary[:40] + ("…" if len(summary) > 40 else "")
        title_parts.append(title_text)
        title = "：".join(title_parts) if len(title_parts) > 1 else title_text

        # 摘要
        intro = summary if len(summary) <= 300 else summary[:300] + "…"

        # 财新 API 不返回发布时间，用当前日期
        ctime = f"{today_str} 00:00"

        parsed.append(
            {
                "title": title,
                "intro": intro,
                "url": url,
                "ctime": ctime,
                "media_name": "财新网",
            }
        )

        if len(parsed) >= num:
            break

    logger.info("财新新闻 (akshare): 获取 %d 条", len(parsed))
    return parsed


def _fetch_cctv_news(date_str: str | None = None) -> list[dict[str, Any]]:
    """从央视网获取财经新闻（通过 akshare 封装）。

    使用 ak.news_cctv() 获取央视新闻。

    Args:
        date_str: 日期字符串 YYYYMMDD，默认使用当天

    Returns:
        结构化新闻列表
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 模块未安装，跳过 CCTV 新闻")
        return []

    if not date_str:
        bj_tz = timezone(timedelta(hours=8))
        date_str = datetime.now(bj_tz).strftime("%Y%m%d")

    try:
        df = ak.news_cctv(date=date_str)
    except Exception as e:
        logger.warning("CCTV 新闻 (akshare) 获取失败: %s", e)
        return []

    if df is None or df.empty:
        logger.debug("CCTV 新闻: 结果为空")
        return []

    bj_tz = timezone(timedelta(hours=8))
    parsed: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for _, row in df.iterrows():
        title = str(row.get("title") or "").strip()
        content = str(row.get("content") or "").strip()

        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        intro = content if len(content) <= 300 else content[:300] + "…"

        # CCTV 不返回具体时间，用当前日期
        now_bj = datetime.now(bj_tz)
        ctime = now_bj.strftime("%Y-%m-%d %H:%M")

        parsed.append(
            {
                "title": title,
                "intro": intro,
                "url": "",
                "ctime": ctime,
                "media_name": "央视新闻",
            }
        )

    logger.info("CCTV 新闻 (akshare): 获取 %d 条", len(parsed))
    return parsed


def fetch_news(num: int = 100) -> list[dict[str, Any]]:
    """通过 akshare 从多个渠道获取财经新闻。

    聚合财新网 + CCTV 新闻，去重合并后返回。

    Args:
        num: 期望获取的新闻条数

    Returns:
        结构化新闻列表
    """
    all_items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # 1) 财新网（主要渠道）
    caixin_items = _fetch_from_caixin(num)
    for item in caixin_items:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_items.append(item)

    # 2) CCTV 新闻（补充渠道）
    cctv_items = _fetch_cctv_news()
    for item in cctv_items:
        title = item.get("title", "")
        if title and title not in seen_urls:
            seen_urls.add(title)
            all_items.append(item)

    logger.info("akshare 新闻汇总: 财新 %d 条 + CCTV %d 条 = %d 条", len(caixin_items), len(cctv_items), len(all_items))

    # 按 ctime 降序排列
    all_items.sort(key=lambda x: x.get("ctime", ""), reverse=True)

    return all_items[:num]

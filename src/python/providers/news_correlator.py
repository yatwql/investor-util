"""新闻关联匹配模块。

将新闻与关键词匹配，按匹配数排序输出 TOP N 条。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("invest")


def correlate_news_with_holdings(
    news_list: list[dict[str, Any]],
    keywords: list[str],
    top_n: int = 100,
    lightweight_keywords: set[str] | None = None,
) -> list[dict[str, Any]]:
    """将新闻与关键词关联，按匹配数排序。

    对每条新闻的 title + intro 进行关键词匹配。
    匹配到的关键词越多，关联度越高。

    行业/概念等轻量级关键词（lightweight_keywords）需要至少 2 个
    匹配才视为关联，避免单条泛匹配导致假阳性。

    Args:
        news_list: 新闻列表
        keywords: 关键词列表
        top_n: 最多返回的关联新闻条数
        lightweight_keywords: 轻量级关键词集合，匹配此类关键词
            需要至少 2 个命中才计为关联

    Returns:
        同 news_list，增加 matched_keywords 字段，按匹配数降序，最多 top_n 条
    """
    if not news_list or not keywords:
        return news_list

    kw_lower = [kw.lower() for kw in keywords]

    scored: list[tuple[dict[str, Any], int, list[str]]] = []
    for news in news_list:
        text = f"{news.get('title', '')} {news.get('intro', '')}".lower()
        matched: list[str] = []
        for i, kw in enumerate(kw_lower):
            if kw and kw in text:
                matched.append(keywords[i])
        if not matched:
            continue
        # 轻量级关键词阈值：如果全部命中都是行业/概念关键词且不足 2 个，跳过
        if lightweight_keywords:
            light_count = sum(1 for kw in matched if kw in lightweight_keywords)
            if light_count == len(matched) and light_count < 2:
                continue
        if matched:
            scored.append((news, len(matched), matched))

    scored.sort(key=lambda x: x[1], reverse=True)

    result: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for news, _count, matched in scored:
        url = news.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        enriched = dict(news)
        enriched["matched_keywords"] = matched
        result.append(enriched)
        if len(result) >= top_n:
            break

    logger.info(
        "新闻关联: 输入 %d 条, 关联 %d 条, 关键词 %d 个",
        len(news_list), len(result), len(keywords),
    )
    return result

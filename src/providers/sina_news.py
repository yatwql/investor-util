"""新浪财经新闻 API — 获取财经新闻并与持仓关键词关联。

Endpoint: https://feed.mix.sina.com.cn/api/roll/get
支持多个新闻分类（财经要闻、国内财经、国际财经），
通过标题/简介关键词匹配实现与持仓的自动关联。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

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


def _ts_to_str(ts: int) -> str:
    """将 Unix 时间戳（秒）转换为格式化的日期字符串。

    API 返回的时间戳为北京时间（UTC+8）。

    Args:
        ts: Unix 时间戳（秒）

    Returns:
        "YYYY-MM-DD HH:MM" 格式的字符串
    """
    try:
        # Sina API 时间戳为北京时间 (UTC+8)
        bj_tz = timezone(timedelta(hours=8))
        dt = datetime.fromtimestamp(ts, tz=bj_tz)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return ""


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
        ctime_str = _ts_to_str(int(raw_ctime))
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
        with httpx.Client(timeout=_TIMEOUT, verify=False) as client:
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


def correlate_news_with_holdings(
    news_list: list[dict[str, Any]], keywords: list[str], top_n: int = 100
) -> list[dict[str, Any]]:
    """将新闻与持仓关键词关联，按匹配数排序。

    对每条新闻的 title + intro 进行关键词匹配。
    匹配到的关键词越多，关联度越高。

    Args:
        news_list: 新闻列表
        keywords: 持仓关键词列表（名称关键词 + 代码）
        top_n: 最多返回的关联新闻条数

    Returns:
        同 news_list，但每项增加 matched_keywords 字段
        按匹配关键词数降序排列，最多返回 top_n 条
    """
    if not news_list or not keywords:
        return news_list

    # 构建关键词变体：对代码类关键词，添加无前缀变体
    keyword_variants: dict[str, list[str]] = {}
    for kw in keywords:
        variants = [kw]
        # 对于纯数字代码（如 "600900"），也尝试无前缀匹配
        if kw.isdigit() and len(kw) == 6:
            # 去掉交易所前缀后三位市场标识后的纯数字
            pass  # 原代码已足够匹配
        keyword_variants[kw] = variants

    kw_lower = [kw.lower() for kw in keywords]

    scored: list[tuple[dict[str, Any], int, list[str]]] = []
    for news in news_list:
        text = f"{news.get('title', '')} {news.get('intro', '')}".lower()
        matched: list[str] = []
        for i, kw in enumerate(kw_lower):
            if kw and kw in text:
                matched.append(keywords[i])
        if matched:
            scored.append((news, len(matched), matched))

    # 按匹配数降序排列
    scored.sort(key=lambda x: x[1], reverse=True)

    # 构造结果
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
        "新闻关联完成: 输入 %d 条, 关联 %d 条, 关键词 %d 个, top_n=%d",
        len(news_list),
        len(result),
        len(keywords),
        top_n,
    )
    return result


def fetch_and_correlate(
    keywords: list[str], max_news: int = 300, top_n: int = 100
) -> list[dict[str, Any]]:
    """便捷函数：获取新闻并关联持仓。

    从多个分类获取新闻，去重后按匹配度排序。

    Args:
        keywords: 持仓关键词列表
        max_news: 获取的新闻总数上限
        top_n: 最多返回的关联新闻条数

    Returns:
        关联后的新闻列表，每项含 matched_keywords 字段
        按匹配关键词数降序排列，最多返回 top_n 条
    """
    # 确保有足够的原始新闻供关联筛选（至少 top_n * 3 条）
    max_news = max(max_news, top_n * 3)

    # 每次请求从各分类均分条数
    lids = list(_LID_MAP.keys())
    per_category = max(1, max_news // len(lids))

    all_news: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for lid in lids:
        items = fetch_news(lid=lid, num=per_category, page=1)
        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_news.append(item)

    if not all_news:
        logger.info("所有分类均未获取到新闻")
        return []

    logger.info("新闻去重汇总: 总计 %d 条", len(all_news))

    # 按时间排序（如果有 ctime 字段，越新越靠前）
    def _sort_key(item: dict[str, Any]) -> str:
        return item.get("ctime", "")

    all_news.sort(key=_sort_key, reverse=True)

    # 关联关键词
    correlated = correlate_news_with_holdings(all_news, keywords, top_n=top_n)

    return correlated


def build_holding_keywords(holdings: list[Any]) -> list[str]:
    """从持仓列表提取关键词。

    Args:
        holdings: List[Holding] — 持仓列表，每个有 name 和 code 字段

    Returns:
        关键词列表（用于新闻匹配），最多 30 个，按长度降序排列
    """
    keywords: set[str] = set()

    # 常见需要过滤的基金/ETF 后缀
    _suffixes = [
        "ETF",
        "联接",
        "A",
        "C",
        "(QDII)",
        "基金",
        "混合",
        "指数",
        "开放",
        "式",
        "发起",
        "LOF",
    ]

    for h in holdings:
        name = h.name.strip()
        code = h.code.strip()

        # 添加代码
        if code:
            keywords.add(code)

        # 清理名称中的常见后缀
        clean = name
        for suffix in _suffixes:
            clean = clean.replace(suffix, "")

        # 提取有意义的 2 字以上中文词
        terms = re.findall(r"[一-鿿]{2,}", clean)
        for t in terms:
            keywords.add(t)

        # 对于 ETF 类名称，尝试提取核心部分（如 "电池ETF" → "电池"）
        if "ETF" in name:
            core = name.replace("ETF", "").strip()
            core_terms = re.findall(r"[一-鿿]{2,}", core)
            for t in core_terms:
                keywords.add(t)

        # 对于联接基金，提取更细粒度的关键词
        if "联接" in name:
            # 提取基金公司 + 指数名部分
            parts = re.findall(r"[一-鿿]{2,}", name)
            if len(parts) >= 2:
                # 例如 "华安纳斯达克100ETF联接" → ["华安纳斯达克", "纳斯达克100"]
                keywords.add(parts[0] if len(parts[0]) >= 2 else "")
                for i in range(1, min(3, len(parts))):
                    if len(parts[i]) >= 2:
                        keywords.add(parts[i])

    # 过滤空字符串
    keywords.discard("")

    # 按长度降序排列（长关键词更精确，优先匹配），最多 30 个
    sorted_kw = sorted(keywords, key=lambda x: (-len(x), x))

    logger.debug("持仓关键词提取: %d 个", len(sorted_kw[:30]))
    return sorted_kw[:30]

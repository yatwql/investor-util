"""统一财经新闻聚合器 — 多源获取 + 去重 + 关键词关联。

聚合三大财经新闻源：
  1. 新浪财经   — 财经要闻/国内/国际
  2. 东方财富   — 股市/财经综合
  3. 财联社     — 7×24 实时快讯

支持从持仓和穿透 TOP10 资产提取关键词，
多源去重合并后按关键词关联度排序。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, List, Optional

from src.models import Holding

logger = logging.getLogger("invest")

# ── 新闻来源注册 ──────────────────────────────────────────────

_SOURCE_CONFIG: dict[str, dict[str, Any]] = {
    "sina": {
        "label": "新浪财经",
        "enabled": True,
    },
    "eastmoney": {
        "label": "东方财富",
        "enabled": True,
    },
    "cls": {
        "label": "财联社",
        "enabled": False,  # API 已要求签名鉴权（errno=10012），匿名请求不可用
    },
}


def get_enabled_sources() -> list[str]:
    """返回当前启用的新闻来源名称列表。"""
    return [name for name, cfg in _SOURCE_CONFIG.items() if cfg.get("enabled", True)]


# ── 关键词提取（含穿透资产） ──────────────────────────────────


def build_holding_keywords(
    holdings: List[Holding],
    penetrated_assets: Optional[List[dict]] = None,
    max_keywords: int = 50,
) -> list[str]:
    """从持仓和穿透 TOP10 资产提取关键词。

    对于每只持仓，提取代码和有意义的中文名称片段；
    对于穿透资产，同样提取代码和名称。

    Args:
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产列表，每个含 name 和 codes 字段
        max_keywords: 最多返回的关键词数量

    Returns:
        关键词列表，按长度降序排列（长关键词优先匹配）
    """
    keywords: set[str] = set()

    # 常见需要过滤的基金/ETF 后缀
    _suffixes = [
        "ETF", "联接", "A", "C", "(QDII)", "基金", "混合",
        "指数", "开放", "式", "发起", "LOF",
    ]

    # ── 1) 从持仓提取 ──
    for h in holdings:
        name = h.name.strip()
        code = h.code.strip()

        if code:
            keywords.add(code)

        clean = name
        for suffix in _suffixes:
            clean = clean.replace(suffix, "")

        terms = re.findall(r"[一-鿿]{2,}", clean)
        for t in terms:
            keywords.add(t)

        if "ETF" in name:
            core = name.replace("ETF", "").strip()
            core_terms = re.findall(r"[一-鿿]{2,}", core)
            for t in core_terms:
                keywords.add(t)

        if "联接" in name:
            parts = re.findall(r"[一-鿿]{2,}", name)
            if len(parts) >= 2:
                keywords.add(parts[0] if len(parts[0]) >= 2 else "")
                for i in range(1, min(3, len(parts))):
                    if len(parts[i]) >= 2:
                        keywords.add(parts[i])

    # ── 2) 从穿透 TOP10 资产提取 ──
    if penetrated_assets:
        for asset in penetrated_assets:
            asset_name = (asset.get("name") or "").strip()
            asset_codes = asset.get("codes") or []

            # 添加穿透资产代码
            for ac in asset_codes:
                if ac.strip():
                    keywords.add(ac.strip())

            # 添加穿透资产名称中的中文关键词
            if asset_name:
                # 对英文名（如 AAPL 美股权重股）直接添加
                if re.match(r"^[A-Za-z0-9\s.&]+$", asset_name):
                    keywords.add(asset_name)
                else:
                    # 中文名提取 2 字以上词
                    clean_name = asset_name
                    for suffix in _suffixes:
                        clean_name = clean_name.replace(suffix, "")
                    terms = re.findall(r"[一-鿿]{2,}", clean_name)
                    for t in terms:
                        keywords.add(t)

    # 过滤空字符串
    keywords.discard("")

    # 按长度降序排列（长关键词更精确，优先匹配），最多 max_keywords 个
    sorted_kw = sorted(keywords, key=lambda x: (-len(x), x))

    logger.debug(
        "关键词提取: %d 个 (持仓 %d + 穿透 %d)",
        len(sorted_kw[:max_keywords]),
        len(holdings),
        len(penetrated_assets) if penetrated_assets else 0,
    )
    return sorted_kw[:max_keywords]


# ── 新闻关联匹配 ──────────────────────────────────────────────


def correlate_news_with_holdings(
    news_list: list[dict[str, Any]],
    keywords: list[str],
    top_n: int = 100,
) -> list[dict[str, Any]]:
    """将新闻与关键词关联，按匹配数排序。

    对每条新闻的 title + intro 进行关键词匹配。
    匹配到的关键词越多，关联度越高。

    Args:
        news_list: 新闻列表
        keywords: 关键词列表
        top_n: 最多返回的关联新闻条数

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
        if matched:
            scored.append((news, len(matched), matched))

    # 按匹配数降序
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


# ── 多源获取 ──────────────────────────────────────────────────


def _fetch_from_sina(num: int) -> list[dict[str, Any]]:
    """从新浪财经获取新闻，均匀覆盖多个分类。"""
    try:
        from src.providers.sina_news import fetch_news as sina_fetch
    except ImportError:
        logger.warning("新浪财经模块不可用")
        return []

    lids = ["2516", "2509", "2510"]  # 财经要闻, 国内财经, 国际财经
    per_category = max(1, num // len(lids))

    all_items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for lid in lids:
        items = sina_fetch(lid=lid, num=per_category, page=1)
        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_items.append(item)

    logger.info("新浪财经: 获取 %d 条 (去重后)", len(all_items))
    return all_items


def _fetch_from_eastmoney(num: int) -> list[dict[str, Any]]:
    """从东方财富获取新闻。"""
    try:
        from src.providers.eastmoney_news import fetch_news as em_fetch
    except ImportError:
        logger.warning("东方财富模块不可用")
        return []

    items = em_fetch(num=num)
    logger.info("东方财富: 获取 %d 条", len(items))
    return items


def _fetch_from_cls(num: int) -> list[dict[str, Any]]:
    """从财联社获取新闻。"""
    try:
        from src.providers.cls_news import fetch_news as cls_fetch
    except ImportError:
        logger.warning("财联社模块不可用")
        return []

    items = cls_fetch(num=num)
    logger.info("财联社: 获取 %d 条", len(items))
    return items


_FETCH_MAP: dict[str, Callable] = {
    "sina": _fetch_from_sina,
    "eastmoney": _fetch_from_eastmoney,
    "cls": _fetch_from_cls,
}


def aggregate_news(
    keywords: list[str],
    top_n: int = 100,
    sources: Optional[list[str]] = None,
    per_source: int = 100,
) -> list[dict[str, Any]]:
    """从多个新闻源获取新闻，去重后按关键词关联度排序。

    流程：
      1. 从各源获取原始新闻（并行）
      2. 按 URL 去重合并
      3. 按发布时间排序（越新越靠前）
      4. 与关键词关联匹配
      5. 按匹配度降序返回 TOP N

    Args:
        keywords: 关键词列表（由 build_holding_keywords 生成）
        top_n: 最多返回的关联新闻条数
        sources: 要使用的新闻源名称列表，默认使用全部启用的源
        per_source: 每个源获取的原始新闻条数

    Returns:
        关联后的新闻列表，每项含 matched_keywords 字段
    """
    if sources is None:
        sources = get_enabled_sources()

    # 新闻缓存：同一关键词 + 同一分钟内复用，避免重复 HTTP
    import hashlib
    import json
    _cache_key = "news_" + hashlib.md5(
        json.dumps([keywords, top_n, sources, per_source], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:12]
    from src.cache import get as _nget, set as _nset, get_ttl as _get_news_ttl
    _cached = _nget(_cache_key, _get_news_ttl("news"))
    if _cached is not None:
        logger.info("新闻缓存命中，跳过 3 源获取")
        return _cached

    # 1) 从各源获取（并行）
    all_raw: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    src_results: dict[str, tuple[int, str]] = {}  # 源名 → (条数, 状态标签)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_to_src: dict[Any, str] = {}
        for src in sources:
            fetch_fn = _FETCH_MAP.get(src)
            if not fetch_fn:
                src_results[src] = (0, "未知源")
                continue
            fut = executor.submit(fetch_fn, per_source)
            fut_to_src[fut] = src

        for future in as_completed(fut_to_src):
            src = fut_to_src[future]
            label = _SOURCE_CONFIG.get(src, {}).get("label", src)
            try:
                items = future.result()
                count = 0
                for item in items:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_raw.append(item)
                        item["_source"] = label
                        count += 1
                src_results[src] = (count, "OK")
            except Exception as e:
                src_results[src] = (0, f"失败({e})")

    # 输出各源状态汇总
    status_parts = [f"{_SOURCE_CONFIG.get(s,{}).get('label',s)} {n}条" if st == "OK"
                    else f"{_SOURCE_CONFIG.get(s,{}).get('label',s)} {st}"
                    for s, (n, st) in src_results.items()]
    logger.info("新闻源状态: %s", " | ".join(status_parts))

    if not all_raw:
        logger.info("所有新闻源均未获取到数据")
        return []

    logger.info("新闻汇总: 去重后共 %d 条 (来自 %d 个源)", len(all_raw), len(sources))

    # 2) 按时间排序
    def _sort_key(item: dict[str, Any]) -> str:
        return item.get("ctime", "")

    all_raw.sort(key=_sort_key, reverse=True)

    # 3) 与关键词关联
    correlated = correlate_news_with_holdings(all_raw, keywords, top_n=top_n)

    # 4) 在结果中标注来源（若无 matched_keywords 则补空列表）
    for item in correlated:
        if "matched_keywords" not in item:
            item["matched_keywords"] = []

    _result = correlated[:top_n]
    _nset(_cache_key, _result)
    return _result

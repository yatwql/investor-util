"""统一财经新闻聚合器 — 多源获取 + 去重 + 关键词关联。

聚合四大财经新闻源，多源去重合并后按关键词关联度排序。
"""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

from src.python.providers.news_sources import (
    _FETCH_MAP,
    _FALLBACK_ENABLED,
    _SOURCE_LABELS,
)
from src.python.providers.news_correlator import correlate_news_with_holdings

logger = logging.getLogger("invest")


def get_enabled_sources() -> list[str]:
    """返回当前启用的新闻来源名称列表。

    启停状态从 config.json 的 news_sources 字段读取，
    未配置时使用 _FALLBACK_ENABLED 后备值。
    """
    from src.python.config import get_config
    config = get_config()
    enabled_map: dict[str, bool] = config.get("news_sources") or {}
    return [
        name for name in _SOURCE_LABELS
        if enabled_map.get(name, _FALLBACK_ENABLED.get(name, True))
    ]


def aggregate_news(
    keywords: list[str],
    top_n: int = 100,
    sources: Optional[list[str]] = None,
    per_source: int = 100,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> list[dict[str, Any]]:
    """从多个新闻源获取新闻，去重后按关键词关联度排序。

    流程：
      1. 从各源获取原始新闻（并行）
      2. 按 URL 去重合并
      3. 按发布时间排序
      4. 与关键词关联匹配
      5. 按匹配度降序返回 TOP N

    Args:
        keywords: 关键词列表
        top_n: 最多返回的关联新闻条数
        sources: 要使用的新闻源名称列表，默认使用全部启用的源
        per_source: 每个源获取的原始新闻条数
        progress_callback: 可选进度回调，签名为 (source_label, count, status)
            每次源获取完成后调用。status 为 "OK" 或 "失败原因"

    Returns:
        关联后的新闻列表，每项含 matched_keywords 字段
    """
    if sources is None:
        sources = get_enabled_sources()

    # 新闻缓存：同一关键词 + 同一分钟内复用，避免重复 HTTP
    _cache_key = "news_" + hashlib.md5(
        json.dumps([keywords, top_n, sources, per_source], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:12]
    from src.python.cache import get as _nget, set as _nset, get_ttl as _get_news_ttl
    _cached = _nget(_cache_key, _get_news_ttl("news"))
    if _cached is not None:
        logger.info("新闻缓存命中，跳过 %d 个源获取", len(sources))
        return _cached

    # 1) 从各源获取（并行）
    all_raw: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    src_results: dict[str, tuple[int, str]] = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
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
            label = _SOURCE_LABELS.get(src, src)
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
                if progress_callback:
                    progress_callback(label, count, "OK")
            except Exception as e:
                err_msg = f"失败({e})"
                src_results[src] = (0, err_msg)
                if progress_callback:
                    progress_callback(label, 0, err_msg)

    # 输出各源状态汇总
    status_parts = [f"{_SOURCE_LABELS.get(s, s)} {n}条" if st == "OK"
                    else f"{_SOURCE_LABELS.get(s, s)} {st}"
                    for s, (n, st) in src_results.items()]
    logger.info("新闻源状态: %s", " | ".join(status_parts))

    if not all_raw:
        logger.warning("所有新闻源均获取失败，请检查网络连接")
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

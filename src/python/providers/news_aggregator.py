"""统一财经新闻聚合器 — 多源获取 + 去重 + 关键词关联。

聚合四大财经新闻源，多源去重合并后按关键词关联度排序。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.python.providers.news_correlator import correlate_news_with_holdings
from src.python.providers.news_sources import (
    _FETCH_MAP,
    _SOURCE_LABELS,
)

logger = logging.getLogger("invest")


def get_enabled_sources() -> list[str]:
    """返回当前启用的新闻来源名称列表。

    启停状态从 config.json 的 news_sources 字段读取。
    """
    from src.python.config import get_config
    config = get_config()
    enabled_map: dict[str, bool] = config.get("news_sources") or {}
    return [
        name for name in _SOURCE_LABELS
        if enabled_map.get(name, False)
    ]


def _compute_cache_key(
    keywords: list[str], top_n: int, sources: list[str], per_source: int,
) -> str:
    """计算新闻缓存键。"""
    raw = json.dumps([keywords, top_n, sources, per_source], sort_keys=True, ensure_ascii=False)
    return "news_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _check_news_cache(cache_key: str, sources: list[str]) -> list[dict] | None:
    """检查新闻缓存，命中则直接返回缓存结果。"""
    from src.python.cache import get as _nget
    from src.python.cache import get_ttl as _get_news_ttl
    cached = _nget(cache_key, _get_news_ttl("news"))
    if cached is not None:
        logger.info("新闻缓存命中，跳过 %d 个源获取", len(sources))
    return cached


def _save_news_cache(cache_key: str, result: list[dict]) -> None:
    """保存新闻结果到缓存。"""
    from src.python.cache import set as _nset
    _nset(cache_key, result)


# ── 上次获取的各源状态（用于 D-7b 空态占位） ──────────────────

_last_src_results: dict[str, tuple[int, str]] = {}


def get_last_source_status() -> dict[str, dict]:
    """返回上次 aggregate_news() 调用的各源状态字典。

    Returns:
        {source_key: {"label": str, "success": bool, "count": int, "error": str | None}}
        source_key 是内部键名（如 "sina"、"eastmoney"），label 是中文标签。
    """
    result: dict[str, dict] = {}
    for src, (count, status) in _last_src_results.items():
        label = _SOURCE_LABELS.get(src, src)
        result[src] = {
            "label": label,
            "success": status == "OK",
            "count": count,
            "error": None if status == "OK" else status,
        }
    return result


def _fetch_from_all_sources(
    sources: list[str], per_source: int,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, str]]]:
    """从多个新闻源并行获取，去重合并。返回 (all_raw, src_results)。"""
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

    return all_raw, src_results


def _log_source_status(src_results: dict[str, tuple[int, str]]) -> None:
    """输出各新闻源状态汇总日志。"""
    status_parts = []
    for s, (n, st) in src_results.items():
        label = _SOURCE_LABELS.get(s, s)
        if st == "OK":
            status_parts.append(f"{label} {n}条")
        else:
            status_parts.append(f"{label} {st}")
    logger.info("新闻源状态: %s", " | ".join(status_parts))


def _finalize_news_results(
    all_raw: list[dict[str, Any]], keywords: list[str], top_n: int,
) -> list[dict[str, Any]]:
    """排序、关联关键词、确保 matched_keywords 字段、截取 TOP N。"""
    if not all_raw:
        return []

    # 按时间排序
    all_raw.sort(key=lambda item: item.get("ctime", ""), reverse=True)

    # 与关键词关联
    correlated = correlate_news_with_holdings(all_raw, keywords, top_n=top_n)

    # 确保 matched_keywords 字段
    for item in correlated:
        if "matched_keywords" not in item:
            item["matched_keywords"] = []

    return correlated[:top_n]


def aggregate_news(
    keywords: list[str],
    top_n: int = 100,
    sources: list[str] | None = None,
    per_source: int = 100,
    progress_callback: Callable[[str, int, str], None] | None = None,
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
    global _last_src_results

    if sources is None:
        sources = get_enabled_sources()

    cache_key = _compute_cache_key(keywords, top_n, sources, per_source)
    cached = _check_news_cache(cache_key, sources)
    if cached is not None:
        _last_src_results = {s: (0, "cache") for s in sources}
        return cached

    all_raw, src_results = _fetch_from_all_sources(sources, per_source, progress_callback)
    _last_src_results = src_results

    if not all_raw:
        logger.warning("所有新闻源均获取失败，请检查网络连接")
        return []

    logger.info("新闻汇总: 去重后共 %d 条 (来自 %d 个源)", len(all_raw), len(sources))

    result = _finalize_news_results(all_raw, keywords, top_n)
    _save_news_cache(cache_key, result)
    return result

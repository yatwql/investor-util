"""缓存引擎 — 命中率统计 + 目录统计子模块。

职责：缓存命中/未命中计数、命中率查询、目录级统计（文件数/大小/前缀分组）。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from ._paths import _CACHE_DIR

logger = logging.getLogger("invest")

# ── 缓存命中率统计（线程安全） ───────────────────────────────
_cache_stats_lock = threading.Lock()
_cache_hits: int = 0
_cache_misses: int = 0


def _record_cache_hit() -> None:
    """记录一次缓存命中（线程安全）。"""
    global _cache_hits
    with _cache_stats_lock:
        _cache_hits += 1


def _record_cache_miss() -> None:
    """记录一次缓存未命中（线程安全）。"""
    global _cache_misses
    with _cache_stats_lock:
        _cache_misses += 1


def get_cache_hit_rate() -> dict[str, int | float]:
    """返回缓存命中率统计。

    Returns:
        {hits, misses, total, rate}
        rate 为 0.0~1.0 的浮点数，无可观测数据时返回 0.0
    """
    with _cache_stats_lock:
        hits = _cache_hits
        misses = _cache_misses
    total = hits + misses
    rate = round(hits / total, 4) if total > 0 else 0.0
    return {"hits": hits, "misses": misses, "total": total, "rate": rate}


def reset_cache_stats() -> None:
    """重置缓存命中率计数器。"""
    global _cache_hits, _cache_misses
    with _cache_stats_lock:
        _cache_hits = 0
        _cache_misses = 0


def get_cache_stats() -> dict:
    """统计缓存目录：文件总数、总大小、按前缀分组数量、最大文件 TOP 10。

    同时统计 .json 和 .json.gz 文件。

    Returns:
        {total_files, total_size_bytes, by_prefix: {prefix: count},
         top_by_size: [(key, size_bytes), ...]}
    """
    stats: dict[str, Any] = {
        "total_files": 0,
        "total_size_bytes": 0,
        "by_prefix": {},
        "top_by_size": [],
    }
    if not os.path.isdir(_CACHE_DIR):
        return stats
    _sized_items: list[tuple[str, int]] = []
    for fname in os.listdir(_CACHE_DIR):
        if fname.endswith(".json.gz"):
            stem = fname[:-8]  # 去掉 .json.gz
        elif fname.endswith(".json"):
            stem = fname[:-5]  # 去掉 .json
        else:
            continue
        fpath = os.path.join(_CACHE_DIR, fname)
        try:
            size = os.path.getsize(fpath)
            stats["total_files"] += 1
            stats["total_size_bytes"] += size
            prefix = stem.split("_", 1)[0] if "_" in stem else "other"
            stats["by_prefix"][prefix] = stats["by_prefix"].get(prefix, 0) + 1
            _sized_items.append((stem, size))
        except OSError:
            pass
    _sized_items.sort(key=lambda x: -x[1])
    stats["top_by_size"] = _sized_items[:10]
    return stats

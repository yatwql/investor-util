"""缓存引擎 — 组管理子模块。

职责：按前缀/组批量清除缓存。
"""

from __future__ import annotations

import logging
import os

from src.python.registry import get_registry

from ._paths import _CACHE_DIR, _GZIP_SUFFIX, _cache_path
from ._store import _cache_lock, clear

logger = logging.getLogger("invest")


def clear_by_prefix(key_prefix: str) -> int:
    """清除所有键名以指定前缀开头的缓存文件（同时处理 .json 和 .json.gz）。

    Args:
        key_prefix: 缓存键名前缀，如 ``"fund_perf_"``

    Returns:
        已清除的文件数量
    """
    with _cache_lock:
        count = 0
        if not os.path.isdir(_CACHE_DIR):
            return 0
        for fname in os.listdir(_CACHE_DIR):
            # 识别 .json 和 .json.gz
            if fname.endswith(".json.gz"):
                fkey = fname[:-8]  # 去掉 .json.gz
            elif fname.endswith(".json"):
                fkey = fname[:-5]  # 去掉 .json
            else:
                continue
            if fkey.startswith(key_prefix):
                try:
                    os.remove(os.path.join(_CACHE_DIR, fname))
                    count += 1
                    logger.debug("缓存已清除: %s", fkey)
                except OSError as e:
                    logger.warning("缓存清除失败 %s: %s", fkey, e)
    return count


def clear_by_group(group_name: str) -> dict[str, int]:
    """清除指定缓存组的所有缓存文件。

    从 registry 自动推导该组包含的所有模块的缓存前缀和精确键名，
    逐一调用 clear_by_prefix / clear。

    Args:
        group_name: 缓存组名，对应 DataModuleDef.cache_groups 中的值

    Returns:
        {模块名: 清除的文件数} 字典，方便日志/UI 展示
    """
    result: dict[str, int] = {}
    for m in get_registry():
        if group_name not in m.cache_groups:
            continue
        total = 0
        for prefix in m.cache_prefixes:
            total += clear_by_prefix(prefix)
        for exact_key in m.exact_cache_keys:
            path = _cache_path(exact_key)
            gz_path = path + _GZIP_SUFFIX
            file_exists = os.path.exists(path) or os.path.exists(gz_path)
            clear(exact_key)
            if file_exists:
                total += 1
        if total > 0:
            result[m.name] = total
    return result

"""缓存引擎 — 过期清理子模块。

职责：过期缓存扫描、清理、预览。
"""

from __future__ import annotations

import logging
import os
import time

from src.python.core.registry import get_exact_type_map, get_prefix_type_map

from ._io import _read_cache_data
from ._paths import _CACHE_DIR
from ._store import _cache_lock
from ._ttl import get_ttl

logger = logging.getLogger("invest")


def _process_cache_file(
    fname: str,
    dry_run: bool,
    prefix_type_map: dict[str, str],
    exact_map: dict[str, str],
) -> int:
    """处理单个缓存文件：判断类型、检查过期、删除。returns 是否删除（0/1）。"""
    if fname.endswith(".json.gz"):
        fkey = fname[:-8]
    elif fname.endswith(".json"):
        fkey = fname[:-5]
    else:
        return 0
    fpath = os.path.join(_CACHE_DIR, fname)

    data_type = "default"
    if fkey in exact_map:
        data_type = exact_map[fkey]
    else:
        for pfx, dtype in prefix_type_map.items():
            if fkey.startswith(pfx):
                data_type = dtype
                break

    ttl = get_ttl(data_type)
    payload = _read_cache_data(fpath, fkey, dry_run=dry_run)
    if payload is None:
        return 1  # 损坏也算清理

    now = time.time()
    age = now - payload.get("_ts", 0)
    if age <= ttl:
        return 0

    if not dry_run:
        try:
            os.remove(fpath)
        except OSError:
            return 0
    logger.info("缓存清理: %s %s (age=%.1fh > ttl=%.1fh)", "预览" if dry_run else "删除", fname, age / 3600, ttl / 3600)
    return 1


def cleanup_expired(dry_run: bool = False) -> int:
    """扫描缓存目录，删除已过期的缓存文件。

    每个缓存文件内含 _ts 时间戳，读取后与当前时间比对，
    根据文件名的类型前缀查表确定 TTL，过期则删除。
    同时处理 .json 和 .json.gz 文件。

    Args:
        dry_run: True 时仅打印不删除；False 时实际删除

    Returns:
        已删除（或待删除）的文件数
    """
    with _cache_lock:
        prefix_type_map: dict[str, str] = get_prefix_type_map()
        exact_map: dict[str, str] = get_exact_type_map()

        if not os.path.isdir(_CACHE_DIR):
            logger.info("缓存目录不存在，跳过清理")
            return 0

        removed = 0
        for fname in sorted(os.listdir(_CACHE_DIR)):
            removed += _process_cache_file(fname, dry_run, prefix_type_map, exact_map)

        logger.info("缓存清理%s: 共 %d 个文件", "预览" if dry_run else "完成", removed)
        return removed


_SENSITIVE_PREFIXES: tuple[str, ...] = (
    "holding_",
    "penetration_",
    "fund_hold_",
    "fund_manager_",
)


def clean_sensitive(older_than_days: int = 90, dry_run: bool = False) -> int:
    """清理超过指定天数的敏感缓存文件。

    敏感缓存包括可能包含持仓明细的数据：
      - holding_* (持仓数据)
      - penetration_* (穿透数据)
      - fund_hold_* (基金持仓)
      - fund_manager_* (基金经理 — 可能含持仓)

    Args:
        older_than_days: 超过此天数的缓存将被清理
        dry_run: True 时仅打印不删除

    Returns:
        已删除（或待删除）的文件数
    """
    with _cache_lock:
        if not os.path.isdir(_CACHE_DIR):
            logger.info("缓存目录不存在，跳过敏感缓存清理")
            return 0

        older_than_secs = older_than_days * 86400
        now = time.time()
        removed = 0

        for fname in sorted(os.listdir(_CACHE_DIR)):
            if not any(fname.startswith(pfx) for pfx in _SENSITIVE_PREFIXES):
                continue

            if fname.endswith(".json.gz"):
                fkey = fname[:-8]
            elif fname.endswith(".json"):
                fkey = fname[:-5]
            else:
                continue

            fpath = os.path.join(_CACHE_DIR, fname)
            payload = _read_cache_data(fpath, fkey, dry_run=dry_run)
            if payload is None:
                # 损坏文件已在 _read_cache_data 中处理（dry_run=False 时删除）
                removed += 1
                continue

            ts = payload.get("_ts", 0)
            age = now - ts
            if age <= older_than_secs:
                continue

            if not dry_run:
                try:
                    os.remove(fpath)
                except OSError:
                    continue
            logger.info(
                "敏感缓存清理: %s %s (age=%.1fd > %dd)",
                "预览" if dry_run else "删除",
                fname,
                age / 86400,
                older_than_days,
            )
            removed += 1

        logger.info("敏感缓存清理%s: 共 %d 个文件", "预览" if dry_run else "完成", removed)
        return removed

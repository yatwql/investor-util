"""缓存引擎 — 核心存取子模块。

职责：缓存读取（get）、写入（set）、删除（clear）三个核心公开 API。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import time
from typing import Any

from ._io import _read_cache_data, _write_atomic
from ._paths import _GZIP_THRESHOLD, _GZIP_SUFFIX, _cache_path
from ._stats import _record_cache_hit, _record_cache_miss

logger = logging.getLogger("invest")

_cache_lock = threading.Lock()


def get(key: str, max_age_seconds: float) -> Any | None:
    """读取缓存，过期或不存在时返回 None。

    Args:
        key: 缓存键名（对应文件名，不含扩展名）
        max_age_seconds: 最大有效期（秒）

    Returns:
        缓存的数据（反序列化后的 Python 对象），过期/不存在返回 None
    """
    path = _cache_path(key)
    gz_path = path + _GZIP_SUFFIX

    # 优先读取 .json.gz，不存在则回退到 .json
    for fpath in (gz_path, path):
        data = _read_cache_data(fpath, key)
        if data is None:
            continue

        timestamp = data.get("_ts", 0)
        age = time.time() - timestamp
        if age > max_age_seconds:
            logger.debug("缓存 %s 已过期 (%.1fs > %.1fs)", key, age, max_age_seconds)
            _record_cache_miss()
            return None

        logger.debug("缓存命中: %s (age=%.1fs, max=%.1fs)", key, age, max_age_seconds)
        _record_cache_hit()
        return data.get("_data")

    _record_cache_miss()
    return None


def set(key: str, data: Any) -> None:
    """写入缓存。使用临时文件 + 原子替换保证线程安全。

    Args:
        key: 缓存键名
        data: 任意可 JSON 序列化的数据
    """
    path = _cache_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    payload = {"_ts": time.time(), "_data": data}
    try:
        json_str = json.dumps(payload, ensure_ascii=False, indent=2)
        raw_bytes = json_str.encode("utf-8")
        use_gzip = len(raw_bytes) > _GZIP_THRESHOLD
        final_path = path + _GZIP_SUFFIX if use_gzip else path
    except (TypeError, ValueError, OverflowError):
        logger.warning("缓存序列化失败 %s: 数据无法 JSON 序列化", key)
        return

    # 先写临时文件，再 os.replace 原子替换，防止并发读取时读到不完整的 JSON
    try:
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    except OSError:
        # tempfile.mkstemp 失败（如磁盘满、权限不足），直接返回
        logger.warning("缓存写入失败 %s: 无法创建临时文件", key)
        return

    try:
        _write_atomic(fd, tmp_path, final_path, path, json_str, raw_bytes, use_gzip)
        logger.debug("缓存已写入: %s", key)
    except FileNotFoundError:
        # 目录可能在 makedirs 后被外部删除，重试一次
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd2, tmp_path2 = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            try:
                _write_atomic(fd2, tmp_path2, final_path, path, json_str, raw_bytes, use_gzip)
                logger.debug("缓存已写入(重试成功): %s", key)
            except OSError as e2:
                logger.warning("缓存写入失败(重试后) %s: %s", key, e2)
                with contextlib.suppress(OSError):
                    os.remove(tmp_path2)
        except OSError as e2:
            logger.warning("缓存写入失败(重试后) %s: %s", key, e2)
    except OSError as e:
        logger.warning("缓存写入失败 %s: %s", key, e)
        with contextlib.suppress(OSError):
            os.remove(tmp_path)


def clear(key: str) -> None:
    """删除指定缓存文件（同时处理 .json 和 .json.gz）。"""
    with _cache_lock:
        path = _cache_path(key)
        gz_path = path + _GZIP_SUFFIX
        for p in (path, gz_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
                    logger.debug("缓存已清除: %s", key)
            except OSError as e:  # noqa: PERF203
                logger.warning("缓存清除失败 %s: %s", key, e)

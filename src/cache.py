"""通用 JSON 文件缓存。

每个缓存项对应 `data/cache/{key}.json` 一个文件。
支持按秒级过期时间自动失效，写入时自动创建目录。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

_CACHE_DIR = "data/cache"

logger = logging.getLogger("invest")


def _cache_path(key: str) -> str:
    """返回缓存文件完整路径。"""
    # 防止目录穿越
    safe_name = key.replace("/", "_").replace("\\", "_").replace("..", "_")
    return os.path.join(_CACHE_DIR, f"{safe_name}.json")


def get(key: str, max_age_seconds: float) -> Any | None:
    """读取缓存，过期或不存在时返回 None。

    Args:
        key: 缓存键名（对应文件名，不含扩展名）
        max_age_seconds: 最大有效期（秒）

    Returns:
        缓存的数据（反序列化后的 Python 对象），过期/不存在返回 None
    """
    path = _cache_path(key)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("缓存文件 %s 损坏，跳过: %s", key, e)
        return None

    timestamp = data.get("_ts", 0)
    age = time.time() - timestamp
    if age > max_age_seconds:
        logger.debug("缓存 %s 已过期 (%.1fs > %.1fs)", key, age, max_age_seconds)
        return None

    logger.debug("缓存命中: %s (age=%.1fs, max=%.1fs)", key, age, max_age_seconds)
    return data.get("_data")


def set(key: str, data: Any) -> None:
    """写入缓存。

    Args:
        key: 缓存键名
        data: 任意可 JSON 序列化的数据
    """
    path = _cache_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    payload = {"_ts": time.time(), "_data": data}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.debug("缓存已写入: %s", key)
    except (IOError, OSError) as e:
        logger.warning("缓存写入失败 %s: %s", key, e)


def exists(key: str) -> bool:
    """检查缓存文件是否存在（不校验过期）。"""
    return os.path.exists(_cache_path(key))


def clear(key: str) -> None:
    """删除指定缓存文件。"""
    path = _cache_path(key)
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.debug("缓存已清除: %s", key)
    except OSError as e:
        logger.warning("缓存清除失败 %s: %s", key, e)


def clear_by_prefix(key_prefix: str) -> int:
    """清除所有键名以指定前缀开头的缓存文件。

    Args:
        key_prefix: 缓存键名前缀，如 ``"fund_perf_"``

    Returns:
        已清除的文件数量
    """
    count = 0
    if not os.path.isdir(_CACHE_DIR):
        return 0
    for fname in os.listdir(_CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        fkey = fname[:-5]  # 去掉 .json 后缀
        if fkey.startswith(key_prefix):
            try:
                os.remove(os.path.join(_CACHE_DIR, fname))
                count += 1
                logger.debug("缓存已清除: %s", fkey)
            except OSError as e:
                logger.warning("缓存清除失败 %s: %s", fkey, e)
    return count


# ── 预定义缓存频率常量（秒，用作代码内默认值） ──────────

CACHE_DAILY = 86400         # 每日（24h）
CACHE_WEEKLY = 604800       # 每周（7d）
CACHE_MONTHLY = 2592000     # 每月（30d）
CACHE_HOLDINGS = 0          # 持仓更新时（不过期，由外部触发刷新）


# ── 从 config.json 读取缓存 TTL ──────────────────────────

_CACHE_TTL_DEFAULTS: dict[str, float] = {
    "price": CACHE_DAILY,
    "index": CACHE_DAILY,
    "rank": CACHE_DAILY,
    "hold": CACHE_WEEKLY,
    "news": CACHE_DAILY,
    "benchmark": CACHE_MONTHLY,
}


def get_ttl(data_type: str) -> float:
    """获取指定数据类型的缓存过期时间（秒）。

    优先读取 data/config/config.json 中的 cache_ttl.<data_type>，
    未配置时返回预定义默认值。

    Args:
        data_type: 数据类型键名，如 "price"、"rank"、"hold"

    Returns:
        过期时间（秒）
    """
    try:
        from src.config import get_config
        config = get_config()
        ttl_config = config.get("cache_ttl") or {}
        if data_type in ttl_config:
            val = float(ttl_config[data_type])
            if val > 0:
                return val
    except Exception:
        pass
    return _CACHE_TTL_DEFAULTS.get(data_type, CACHE_DAILY)
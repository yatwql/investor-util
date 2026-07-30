"""会话缓存管理 — 域命名空间化会话级内存缓存，含 LRU 淘汰。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

# ── 常量 ────────────────────────────────────────────────

_SESSION_CACHE_MAX_ENTRIES = 2000
"""每 domain 最多缓存条目数，超限时淘汰最旧条目。"""

# ── Sentinel ─────────────────────────────────────────────

NOT_FOUND: object = object()
"""会话缓存未命中的返回值 sentinel，区分『缓存存了 None』和『没查过』。"""


# ── 数据类型 ────────────────────────────────────────────


@dataclass
class SessionCacheEntry:
    """会话缓存条目。"""

    value: Any
    fetched_at: float
    source: str


# ── 缓存封装类 ──────────────────────────────────────────


class SessionCache:
    """域命名空间化的会话级内存缓存，线程安全，支持 LRU 淘汰。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, dict[str, SessionCacheEntry]] = {}

    # ── 读写接口 ──────────────────────────────────────

    def get(self, domain: str, code: str) -> Any:
        """从会话缓存读取，未命中时返回 NOT_FOUND sentinel。

        NOTE: 调用方应通过 `is get(...) is NOT_FOUND` 区分
        『未缓存』和『缓存值为 None』。
        """
        with self._lock:
            entry = self._data.get(domain, {}).get(code)
            if entry is None:
                return NOT_FOUND
            return entry.value

    def set(
        self,
        domain: str,
        code: str,
        value: Any,
        source: str = "api",
    ) -> None:
        """写入会话缓存（支持 value=None）。"""
        with self._lock:
            if domain not in self._data:
                self._data[domain] = {}
            dc = self._data[domain]
            if len(dc) >= _SESSION_CACHE_MAX_ENTRIES:
                self._evict_one(dc)
            dc[code] = SessionCacheEntry(
                value=value,
                fetched_at=time.time(),
                source=source,
            )

    def contains(self, domain: str, code: str) -> bool:
        """检查某 key 是否在会话缓存中（无视值是否为 None）。"""
        with self._lock:
            return code in self._data.get(domain, {})

    def clear(self, domain: str | None = None) -> None:
        """清空会话缓存。domain=None 时清空全部。"""
        with self._lock:
            if domain is not None:
                self._data.pop(domain, None)
            else:
                self._data.clear()

    # ── 内部淘汰 ───────────────────────────────────────

    @staticmethod
    def _evict_one(dc: dict[str, SessionCacheEntry]) -> None:
        """O(1) 淘汰最旧条目（不排序，直接弹出第一个）。"""
        try:
            dc.pop(next(iter(dc)))
        except (StopIteration, KeyError):
            pass

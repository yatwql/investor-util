"""熔断状态持久化。"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
import threading

logger = logging.getLogger("invest")

_CIRCUIT_BREAKER_STATE_FILE = "circuit_breaker.json"
"""熔断状态持久化文件名（存储在 data/state 目录下）。"""
_CIRCUIT_BREAKER_TTL = 86400  # 24h
"""熔断状态持久化记录的超时 TTL（秒），超过此时间的条目在加载时自动清理。"""
_PROVIDER_COOLDOWN_SECS = 300
"""熔断后默认冷却秒数。"""
_BACKOFF_LEVELS = (60, 300, 900, 3600)
"""指数退避级别（秒）。"""


def _get_breaker_state_path() -> str:
    """返回熔断状态持久化文件路径。"""
    from src.python.cache._paths import _CACHE_DIR

    return os.path.join(os.path.dirname(_CACHE_DIR), "state", _CIRCUIT_BREAKER_STATE_FILE)


def save_state(providers: dict, lock: threading.RLock) -> None:
    """持久化当前熔断状态到 JSON 文件（原子写入）。

    Args:
        providers: 以 provider_name 为 key 的 ProviderState dict
        lock: 保护 providers 的锁
    """
    path = _get_breaker_state_path()
    now = time.time()
    state: dict[str, dict] = {}
    with lock:
        for name, ps in providers.items():
            if ps.is_skipped or ps.consecutive_failures > 0:
                state[name] = {
                    "consecutive_failures": ps.consecutive_failures,
                    "is_skipped": ps.is_skipped,
                    "last_failure_time": ps.last_failure_time,
                    "last_failure_context": ps.last_failure_context,
                    "backoff_level": ps.backoff_level,
                    "cooldown_secs": ps.cooldown_secs,
                    "_saved_at": now,
                }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
            raise
    except OSError as e:
        logger.warning("[registry] 熔断状态持久化失败: %s", e)


def load_state(providers: dict, lock: threading.RLock) -> None:
    """从 JSON 文件加载熔断状态，超过 TTL 的条目自动清理。

    Args:
        providers: 以 provider_name 为 key 的 ProviderState dict
        lock: 保护 providers 的锁
    """
    path = _get_breaker_state_path()
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.debug("[registry] 熔断状态文件损坏，跳过加载")
        return

    now = time.time()
    loaded = 0
    expired = 0
    with lock:
        for name, ps_data in data.items():
            saved_at = ps_data.get("_saved_at", 0)
            if now - saved_at > _CIRCUIT_BREAKER_TTL:
                expired += 1
                continue
            state = providers.get(name)
            if state is None:
                continue
            state.consecutive_failures = ps_data.get("consecutive_failures", 0)
            state.is_skipped = ps_data.get("is_skipped", False)
            state.last_failure_time = ps_data.get("last_failure_time", 0)
            state.last_failure_context = ps_data.get("last_failure_context", "")
            state.backoff_level = ps_data.get("backoff_level", 0)
            state.cooldown_secs = ps_data.get("cooldown_secs", _PROVIDER_COOLDOWN_SECS)
            loaded += 1
    if loaded:
        logger.info("[registry] 已加载 %d 个 Provider 熔断状态（%d 条已过期）", loaded, expired)

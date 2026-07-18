"""LLM 熔断器模块 — 防止对故障 endpoint 持续无效请求。"""

from __future__ import annotations

import logging
import threading as _threading
import time

logger = logging.getLogger("invest")

__all__ = [
    "_CIRCUIT_BREAKER_THRESHOLD", "_CIRCUIT_BREAKER_RECOVERY",
    "_circuit_failures", "_circuit_open_until", "_circuit_lock",
    "_cb_endpoint", "_cb_record_failure", "_cb_record_success", "_cb_is_open",
    "get_circuit_status",
]

_CIRCUIT_BREAKER_THRESHOLD = 3   # 连续失败 N 次后开启熔断
_CIRCUIT_BREAKER_RECOVERY = 60  # 冷却时间（秒）

_circuit_failures: dict[str, int] = {}        # endpoint → 连续失败次数
_circuit_open_until: dict[str, float] = {}     # endpoint → 冷却到期时间
_circuit_lock = _threading.Lock()


def _cb_endpoint(url: str) -> str:
    """从 URL 提取域名作为熔断器 key。"""
    try:
        return url.split("/")[2] if url else "unknown"
    except (IndexError, TypeError, AttributeError):
        return "unknown"


def _cb_record_failure(url: str) -> None:
    """记录一次失败，达到阈值时开启熔断。"""
    ep = _cb_endpoint(url)
    with _circuit_lock:
        _circuit_failures[ep] = _circuit_failures.get(ep, 0) + 1
        if _circuit_failures[ep] >= _CIRCUIT_BREAKER_THRESHOLD:
            expiry = time.time() + _CIRCUIT_BREAKER_RECOVERY
            _circuit_open_until[ep] = expiry
            logger.warning("熔断器已开启: %s (连续失败 %d 次, 冷却 %.0fs)",
                          ep, _circuit_failures[ep], _CIRCUIT_BREAKER_RECOVERY)


def _cb_record_success(url: str) -> None:
    """成功时重置熔断状态。"""
    ep = _cb_endpoint(url)
    with _circuit_lock:
        _circuit_failures.pop(ep, None)
        _circuit_open_until.pop(ep, None)


def _cb_is_open(url: str) -> bool:
    """检查熔断是否开启。若冷却期已过则自动转为半开（返回 False）。"""
    ep = _cb_endpoint(url)
    with _circuit_lock:
        if ep not in _circuit_open_until:
            return False
        if time.time() >= _circuit_open_until[ep]:
            del _circuit_open_until[ep]  # 冷却结束 → 半开，允许一次试探
            return False
        return True


def get_circuit_status(endpoint: str) -> str:
    """查询指定端点的熔断状态，返回中文状态描述。

    Args:
        endpoint: API endpoint URL（如 "https://api.anthropic.com/v1/messages"）

    Returns:
        "正常" — 熔断器未开启或已冷却
        "熔断中" — 熔断器开启，正在冷却
    """
    if _cb_is_open(endpoint):
        return "熔断中"
    return "正常"

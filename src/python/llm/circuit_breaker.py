"""LLM 熔断器模块 — 防止对故障 endpoint 持续无效请求。"""

from __future__ import annotations

import logging
import threading as _threading
import time
from typing import Any

logger = logging.getLogger("invest")

__all__ = [
    "_CIRCUIT_BREAKER_THRESHOLD",
    "_CIRCUIT_BREAKER_RECOVERY",
    "_circuit_failures",
    "_circuit_open_until",
    "_circuit_lock",
    "_cb_endpoint",
    "_cb_record_failure",
    "_cb_record_success",
    "_cb_is_open",
    "get_circuit_status",
]

_CIRCUIT_BREAKER_THRESHOLD = 3  # 连续失败 N 次后开启熔断
_CIRCUIT_BREAKER_RECOVERY = 60  # 冷却时间（秒）

_circuit_failures: dict[str, int] = {}  # endpoint → 连续失败次数
_circuit_open_until: dict[str, float] = {}  # endpoint → 冷却到期时间
_circuit_lock = _threading.Lock()


def _cb_endpoint(url: str) -> str:
    """从 URL 提取域名作为熔断器 key。"""
    try:
        return url.split("/")[2] if url else "unknown"
    except (IndexError, TypeError, AttributeError):
        return "unknown"


def _cb_record_failure(url: str, cooldown: float | None = None, force: bool = False) -> None:
    """记录一次失败，达到阈值时开启熔断。

    Args:
        cooldown: 覆盖默认冷却秒数（不传用 ``_CIRCUIT_BREAKER_RECOVERY``）。
        force: 跳过连续失败阈值立即开启熔断——供「限速终态失败」（重试耗尽仍 429）
            使用：该信号明确表示端点限速/配额，继续按常规节奏试错只会反复无效
            先试并加剧风控画像，须立即进入长冷却。
    """
    ep = _cb_endpoint(url)
    cd = float(cooldown) if cooldown is not None else float(_CIRCUIT_BREAKER_RECOVERY)
    with _circuit_lock:
        _circuit_failures[ep] = _circuit_failures.get(ep, 0) + 1
        if force or _circuit_failures[ep] >= _CIRCUIT_BREAKER_THRESHOLD:
            expiry = time.time() + cd
            _circuit_open_until[ep] = expiry
            logger.warning("熔断器已开启: %s (连续失败 %d 次, 冷却 %.0fs)", ep, _circuit_failures[ep], cd)


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


def circuit_status_snapshot() -> dict[str, dict[str, Any]]:
    """端点熔断状态快照（core 网关经注册钩子取用，core 不反向 import 上层）。"""
    now = time.time()
    status: dict[str, dict[str, Any]] = {}
    all_endpoints = set(list(_circuit_failures.keys()) + list(_circuit_open_until.keys()))
    for ep in all_endpoints:
        cooldown_remaining = 0.0
        if ep in _circuit_open_until:
            cooldown_remaining = max(0.0, _circuit_open_until[ep] - now)
            _cb = cooldown_remaining > 0
        else:
            _cb = False
        status[ep] = {
            "circuit_broken": _cb,
            "consecutive_failures": _circuit_failures.get(ep, 0),
            "threshold": _CIRCUIT_BREAKER_THRESHOLD,
            "cooldown_remaining": round(cooldown_remaining, 1),
            "recovery_secs": _CIRCUIT_BREAKER_RECOVERY,
        }
    return status


def _register_to_core_gateway() -> None:
    """把 LLM 熔断快照与展示判定注册进 core 网关（模块导入时执行一次）。"""
    from src.python.core.circuit_breaker import register_breaker_status, register_circuit_text

    register_breaker_status("llm", circuit_status_snapshot)
    # 晚绑定回调：经模块全局解析 get_circuit_status，展示层只拿到 core 侧的
    # 注册面，不反向 import 本模块；也便于用例替换判定函数。
    register_circuit_text(lambda endpoint: get_circuit_status(endpoint))


_register_to_core_gateway()

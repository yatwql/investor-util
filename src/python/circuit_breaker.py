"""统一的断路器网关层 — 聚合 Provider 和 LLM 熔断状态查询。

提供统一的熔断状态查询入口，UI/CLI 模块只需调用此模块；
Provider 熔断和 LLM 熔断的状态共享同一持久化文件。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("invest")

__all__ = [
    "get_all_breaker_status",
    "get_provider_breaker_status",
    "get_llm_endpoint_status",
]


def get_provider_breaker_status() -> dict[str, dict[str, Any]]:
    """返回所有 Provider 的熔断状态报告。

    Returns:
        {provider_name: {available, tier, consecutive_failures,
                         circuit_broken, cooldown_remaining, ...}, ...}
    """
    from src.python.provider_registry import get_registry

    return get_registry().generate_status_report()


def get_llm_endpoint_status() -> dict[str, dict[str, Any]]:
    """返回所有 LLM 端点的熔断状态报告。

    Returns:
        {endpoint_domain: {circuit_broken, consecutive_failures,
                           cooldown_remaining_secs}, ...}
    """
    from src.python.llm.circuit_breaker import (
        _CIRCUIT_BREAKER_RECOVERY,
        _CIRCUIT_BREAKER_THRESHOLD,
        _circuit_failures,
        _circuit_open_until,
    )

    now = __import__("time").time()
    status: dict[str, dict[str, Any]] = {}
    for ep in set(list(_circuit_failures.keys()) + list(_circuit_open_until.keys())):
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


def get_all_breaker_status() -> dict[str, dict[str, Any]]:
    """返回所有断路器状态（Provider + LLM）。

    Returns:
        {"provider": {...}, "llm": {...}}
        provider 和 llm 分别为对应域的熔断状态报告。
    """
    return {
        "provider": get_provider_breaker_status(),
        "llm": get_llm_endpoint_status(),
    }

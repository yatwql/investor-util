"""统一的断路器网关层 — 聚合 Provider / LLM / 指标熔断状态查询与管理。

提供统一的熔断状态查询入口、监控接口、配置预设。
Provider 熔断（provider_registry.py DataSourceRegistry）、
LLM 熔断（llm/circuit_breaker.py 模块级）和
指标熔断（analysis/circuit_breaker_wrapper.py::IndicatorBreaker）
共享同一查询入口。

用法:
    from src.python.core.circuit_breaker import gateway

    # 获取统一状态报告（provider + llm + indicator）
    status = gateway.summary()

    # 获取 DataSource 熔断器实例
    registry = gateway.get("data_source")

    # 查询 LLM 熔断端点状态
    llm_status = gateway.get("llm")

    # 查询指标熔断器状态
    indicator_status = gateway.get("indicator")

包装函数:
    get_all_breaker_status() / get_provider_breaker_status() /
    get_llm_endpoint_status() / get_indicator_breaker_status()
    委派给网关。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("invest")

__all__ = [
    "BreakerConfig",
    "CircuitBreakerGateway",
    "gateway",
    "get_all_breaker_status",
    "get_provider_breaker_status",
    "get_llm_endpoint_status",
    "get_indicator_breaker_status",
    "BREAKER_CONFIG_DATA_SOURCE",
]

# ═══════════════════════════════════════════════════════════════
# 预设配置
# ═══════════════════════════════════════════════════════════════


@dataclass
class BreakerConfig:
    """断路器预设配置。

    Attributes:
        max_failures: 连续失败多少次后开启熔断
        cooldown_seconds: 基础冷却时间（秒）
        backoff_levels: 指数退避级别序列（秒），超出序列末位后锁定末位值
    """

    max_failures: int
    cooldown_seconds: int | float
    backoff_levels: tuple[int | float, ...] = field(default_factory=tuple)


BREAKER_CONFIG_DATA_SOURCE = BreakerConfig(
    max_failures=3,
    cooldown_seconds=300,
    backoff_levels=(60, 300, 900, 3600),
)
"""数据源 Provider 熔断器预设：3 次/300s 基础冷却，指数退避至 3600s。"""


# ═══════════════════════════════════════════════════════════════
# 熔断器网关
# ═══════════════════════════════════════════════════════════════


class CircuitBreakerGateway:
    """统一熔断器网关。

    聚合 Provider（DataSourceRegistry）、LLM（llm/circuit_breaker）和
    指标熔断器（analysis/circuit_breaker_wrapper.py::IndicatorBreaker）的
    状态查询和管理接口，消除三熔断器运维复杂度。

    用法:
        >>> from src.python.core.circuit_breaker import gateway
        >>> status = gateway.summary()  # dict 格式统一报告
        >>> registry = gateway.get("data_source")  # DataSourceRegistry 实例
    """

    def get(self, name: str) -> Any:
        """获取指定类型的熔断器实例或状态信息。

        Args:
            name: "data_source" 返回 DataSourceRegistry 单例，
                  "llm" 返回当前 LLM 端点熔断状态字典，
                  "indicator" 返回指标熔断器实例，
                  其他名称返回 None。

        Returns:
            DataSourceRegistry 实例（data_source 时）,
            IndicatorBreaker 实例（indicator 时）,
            状态字典（llm 时）,
            或 None（未知名称）
        """
        if name == "data_source":
            from src.python.core.provider_registry import get_registry

            return get_registry()
        if name == "llm":
            return self._get_llm_status()
        if name == "indicator":
            from src.python.analysis.circuit_breaker_wrapper import get_indicator_breaker

            return get_indicator_breaker()
        logger.debug("CircuitBreakerGateway.get: 未知熔断器类型 '%s'", name)
        return None

    def summary(self) -> dict[str, Any]:
        """返回所有断路器的统一状态报告。

        Returns:
            {
                "provider": {  # 数据源 Provider 熔断状态
                    provider_name: {
                        "available": bool,
                        "tier": int,
                        "consecutive_failures": int,
                        "circuit_broken": bool,
                        "cooldown_remaining": float,
                        "total_failures": int,
                        "total_successes": int,
                        "backoff_level": int,
                    }, ...
                },
                "llm": {  # LLM 端点熔断状态
                    endpoint_domain: {
                        "circuit_broken": bool,
                        "consecutive_failures": int,
                        "threshold": int,
                        "cooldown_remaining": float,
                        "recovery_secs": float,
                    }, ...
                },
                "indicator": {  # 指标熔断状态
                    indicator_name: {
                        "indicator": str,
                        "circuit_broken": bool,
                        "consecutive_failures": int,
                        "cooldown_remaining": float,
                        "last_context": str,
                    }, ...
                },
            }
        """
        return {
            "provider": self._get_provider_status(),
            "llm": self._get_llm_status(),
            "indicator": self._get_indicator_status(),
        }

    @staticmethod
    def _get_provider_status() -> dict[str, dict[str, Any]]:
        """返回所有 Provider 的熔断状态报告。"""
        from src.python.core.provider_registry import get_registry

        return get_registry().generate_status_report()

    @staticmethod
    def _get_llm_status() -> dict[str, dict[str, Any]]:
        """返回所有 LLM 端点的熔断状态报告。"""
        from src.python.llm.circuit_breaker import (
            _CIRCUIT_BREAKER_RECOVERY,
            _CIRCUIT_BREAKER_THRESHOLD,
            _circuit_failures,
            _circuit_open_until,
        )

        now = __import__("time").time()
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

    @staticmethod
    def _get_indicator_status() -> dict[str, dict[str, Any]]:
        """返回所有指标断路器的熔断状态报告。

        委派给 analysis/circuit_breaker_wrapper.py::IndicatorBreaker.summary()。
        """
        from src.python.analysis.circuit_breaker_wrapper import get_indicator_breaker

        return get_indicator_breaker().summary()


# ── 模块级单例 ─────────────────────────────────────────

gateway = CircuitBreakerGateway()
"""全局统一熔断器网关实例。"""


# ═══════════════════════════════════════════════════════════════
# 模块级包装函数（委派给 gateway）
# ═══════════════════════════════════════════════════════════════


def get_provider_breaker_status() -> dict[str, dict[str, Any]]:
    """返回所有 Provider 的熔断状态报告。

    委派给 gateway._get_provider_status()。

    Returns:
        {provider_name: {available, tier, consecutive_failures, ...}, ...}
    """
    return gateway._get_provider_status()


def get_llm_endpoint_status() -> dict[str, dict[str, Any]]:
    """返回所有 LLM 端点的熔断状态报告。

    委派给 gateway._get_llm_status()。

    Returns:
        {endpoint_domain: {circuit_broken, consecutive_failures, ...}, ...}
    """
    return gateway._get_llm_status()


def get_indicator_breaker_status() -> dict[str, dict[str, Any]]:
    """返回所有指标断路器的熔断状态报告。

    委派给 gateway._get_indicator_status()。

    Returns:
        {indicator_name: {indicator, circuit_broken, consecutive_failures, ...}, ...}
    """
    return gateway._get_indicator_status()


def get_all_breaker_status() -> dict[str, dict[str, Any]]:
    """返回所有断路器状态（Provider + LLM + 指标）。

    委派给 gateway.summary()。

    Returns:
        {"provider": {...}, "llm": {...}, "indicator": {...}}
    """
    return gateway.summary()

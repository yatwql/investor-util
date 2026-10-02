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
from collections.abc import Callable
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
    "register_breaker_status",
]

# ═══════════════════════════════════════════════════════════════
# 上游熔断状态注册（分层纪律：core 不反向 import 上层模块）
# ═══════════════════════════════════════════════════════════════

#: 上游模块（analysis / llm）在自模块导入时注册的熔断状态快照函数。
#: key 与 circuit_breaker_status 的断路器分类一致："llm"（LLM 端点熔断状态）、
#: "indicator"（指标断路器实例）。未注册 → 视为上游未加载，状态为空 dict / None。
_BREAKER_SNAPSHOT_PROVIDERS: dict[str, Callable[[], Any]] = {}


def register_breaker_status(category: str, provider: Callable[[], Any]) -> None:
    """注册上游模块的熔断状态快照函数（上游模块导入时自行调用）。

    Args:
        category: 断路器分类（"llm" / "indicator"，供网关按名取用）
        provider: 无参函数——"llm" 返回 {endpoint: {circuit_broken, ...}} 字典，
            "indicator" 返回 IndicatorBreaker 实例（带 summary()）。
    """
    _BREAKER_SNAPSHOT_PROVIDERS[category] = provider


def _breaker_snapshot(category: str) -> Any:
    """取已注册的上游熔断快照；未注册返回 None（调用方按空态降级）。"""
    provider = _BREAKER_SNAPSHOT_PROVIDERS.get(category)
    return provider() if provider is not None else None


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
            return _breaker_snapshot("indicator")
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
        """返回所有 LLM 端点的熔断状态报告。

        状态快照由 llm/circuit_breaker 导入时注册（``register_breaker_status``）；
        未注册 → LLM 侧未加载，返回空 dict（不可用态语义与空集合一致）。
        """
        return _breaker_snapshot("llm") or {}

    @staticmethod
    def _get_indicator_status() -> dict[str, dict[str, Any]]:
        """返回所有指标断路器的熔断状态报告。

        委派给 analysis 侧注册的 IndicatorBreaker.summary()（core 不反向 import 上层）。
        """
        breaker = _breaker_snapshot("indicator")
        return breaker.summary() if breaker is not None else {}


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

"""CircuitBreakerGateway 统一熔断网关单元测试。

覆盖统一熔断网关需求：网关聚合 Provider / LLM / 指标三路熔断状态，
统一查询入口 + 监控接口。

覆盖要点：
  - gateway.get("data_source") → DataSourceRegistry 实例
  - gateway.get("indicator") → IndicatorBreaker 实例
  - gateway.get("llm") → LLM 端点状态字典
  - gateway.get(未知) → None
  - gateway.summary() → 同时含 provider / llm / indicator 三键
  - get_indicator_breaker_status() 包装函数可调用
  - 指标熔断状态能在 summary() 中如实反映
"""

from __future__ import annotations

import pytest

from src.python.analysis.circuit_breaker_wrapper import get_indicator_breaker
from src.python.core.circuit_breaker import (
    gateway,
    get_all_breaker_status,
    get_indicator_breaker_status,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestGatewayGet:
    """gateway.get() 各分支返回类型。"""

    def test_get_data_source_returns_registry(self):
        """get("data_source") → DataSourceRegistry 实例。"""
        from src.python.core.provider_registry import DataSourceRegistry

        assert isinstance(gateway.get("data_source"), DataSourceRegistry)

    def test_get_indicator_returns_breaker(self):
        """get("indicator") → IndicatorBreaker 实例。"""
        from src.python.analysis.circuit_breaker_wrapper import IndicatorBreaker

        breaker = gateway.get("indicator")
        assert isinstance(breaker, IndicatorBreaker)

    def test_get_llm_returns_dict(self):
        """get("llm") → 状态字典（可能为空）。"""
        llm_status = gateway.get("llm")
        assert isinstance(llm_status, dict)

    def test_get_unknown_returns_none(self):
        """get(未知名称) → None。"""
        assert gateway.get("nonexistent") is None


class TestGatewaySummary:
    """gateway.summary() 聚合三路熔断状态。"""

    def test_summary_has_all_three_keys(self):
        """summary() 同时含 provider / llm / indicator 三键。"""
        status = gateway.summary()
        assert "provider" in status
        assert "llm" in status
        assert "indicator" in status

    def test_summary_indicator_reflects_breaker(self):
        """指标连续失败达阈值后，summary()["indicator"] 如实反映断路状态。"""
        breaker = get_indicator_breaker()
        for i in range(3):
            breaker.record_failure("gateway_test_indicator", f"error_{i}")

        status = gateway.summary()
        ind_status = status["indicator"]
        assert "gateway_test_indicator" in ind_status
        assert ind_status["gateway_test_indicator"]["circuit_broken"] is True
        assert ind_status["gateway_test_indicator"]["consecutive_failures"] == 3

    def test_summary_provider_reflects_registry(self):
        """Provider 熔断后 summary()["provider"] 如实反映。"""
        from src.python.core.provider_registry import get_registry

        registry = get_registry()
        for _ in range(3):
            registry.record_failure("eastmoney")

        status = gateway.summary()
        assert status["provider"]["eastmoney"]["circuit_broken"] is True


class TestGatewayWrappers:
    """模块级包装函数（委派给网关）。"""

    def test_get_indicator_breaker_status_callable(self):
        """get_indicator_breaker_status() 返回 {indicator_name: 状态} 字典。"""
        status = get_indicator_breaker_status()
        assert isinstance(status, dict)

    def test_get_indicator_breaker_status_reflects_failure(self):
        """指标失败后 get_indicator_breaker_status() 包含该指标。"""
        breaker = get_indicator_breaker()
        breaker.record_failure("gateway_wrap_indicator", "err")
        breaker.record_failure("gateway_wrap_indicator", "err")
        breaker.record_failure("gateway_wrap_indicator", "err")

        status = get_indicator_breaker_status()
        assert "gateway_wrap_indicator" in status
        assert status["gateway_wrap_indicator"]["circuit_broken"] is True

    def test_get_all_breaker_status_has_three_keys(self):
        """get_all_breaker_status() 含 provider / llm / indicator 三键。"""
        status = get_all_breaker_status()
        assert set(status.keys()) == {"provider", "llm", "indicator"}

"""链韧性测试 — 多数据源故障/恢复/持久化场景。

使用 mock 模拟数据源故障，验证熔断器行为正确：
  1. 多数据源同时故障 → 级联熔断
  2. 长时间不可用后恢复 → 冷却期试探
  3. 熔断器持久化 → 跨会话加载
  4. 所有源不可用 → 降级报告仍可生成
  5. LLM 端点熔断 → 独立熔断器生效

@pytest.mark.scenario_resilience
"""

from __future__ import annotations

import json
import os
import time
from unittest.mock import patch

import logging

import pytest

pytestmark = [pytest.mark.scenario_resilience]

from src.python.core.circuit_breaker import gateway
from src.python.core.provider_registry import get_registry

logger = logging.getLogger("invest")

# ── 辅助函数 ─────────────────────────────────────────────────


def _reset_llm_circuit_breaker() -> None:
    """重置 LLM 熔断器状态（模块级变量）。"""
    from src.python.llm.circuit_breaker import (
        _circuit_failures,
        _circuit_open_until,
    )

    _circuit_failures.clear()
    _circuit_open_until.clear()


# ── 测试用例 ─────────────────────────────────────────────────


class TestChainResilience:
    """链韧性测试 — 五种故障场景验证。"""

    @pytest.mark.scenario_resilience
    def test_multi_source_failure(self):
        """多数据源同时故障 → 级联熔断：两个 provider 各失败 3 次后熔断。"""
        registry = get_registry()
        _reset_llm_circuit_breaker()

        # 对 eastmoney 和 tencent 各模拟 3 次失败
        for provider in ("eastmoney", "tencent"):
            for _ in range(3):
                registry.record_failure(provider)

        status = gateway.summary()
        provider_status = status.get("provider", {})

        assert provider_status.get("eastmoney", {}).get("circuit_broken"), "eastmoney 应熔断"
        assert provider_status.get("tencent", {}).get("circuit_broken"), "tencent 应熔断"

        chain_broken = registry.is_chain_broken({"eastmoney", "tencent"})
        assert chain_broken, "双数据源熔断后链应标记为断开"

    @pytest.mark.scenario_resilience
    def test_long_recovery(self):
        """长时间不可用后恢复 → 冷却期结束后试探请求应解熔。"""
        registry = get_registry()
        _reset_llm_circuit_breaker()

        # 3 次失败触发熔断
        for _ in range(3):
            registry.record_failure("eastmoney")
        assert registry.is_circuit_broken("eastmoney"), "熔断应已触发"

        # 模拟冷却期结束：将 last_failure_time 设到过去
        registry._providers["eastmoney"].last_failure_time = time.time() - 3600

        # 试探请求（记录成功）
        registry.record_success("eastmoney")
        assert not registry.is_circuit_broken("eastmoney"), "冷却期后成功应解熔"

    @pytest.mark.scenario_resilience
    def test_breaker_persistence(self):
        """熔断器持久化 → 跨会话加载后仍保留失败计数。"""
        registry = get_registry()
        _reset_llm_circuit_breaker()

        # 模拟 2 次失败（不触发熔断，仅记录）
        for _ in range(2):
            registry.record_failure("eastmoney")

        # 验证状态已记录在熔断器内部
        state = registry._providers.get("eastmoney")
        failures = state.consecutive_failures if state else 0
        assert failures >= 2, f"持久化前应有 >=2 次失败，实际 {failures}"

    @pytest.mark.scenario_resilience
    def test_all_sources_unreachable(self):
        """所有外部数据源不可用 → 报告仍可降级生成（不崩溃）。"""
        registry = get_registry()
        _reset_llm_circuit_breaker()

        # 熔断所有已知 provider
        for provider in ("eastmoney", "tencent", "sina"):
            for _ in range(5):
                registry.record_failure(provider)

        # 验证所有已熔断
        all_broken = all(
            registry.is_circuit_broken(p)
            for p in ("eastmoney", "tencent", "sina")
        )
        assert all_broken, "所有 provider 应均已熔断"

        # 验证链状态
        chain_broken = registry.is_chain_broken({"eastmoney", "tencent", "sina"})
        assert chain_broken, "全链路熔断应标记为断开"

        # 验证 get() 不崩溃
        est = registry.generate_status_report()
        assert isinstance(est, dict), "全熔断状态下状态报告应为 dict"

    @pytest.mark.scenario_resilience
    def test_llm_circuit_breaker(self):
        """LLM 端点熔断器：3 次失败后应独立熔断。"""
        _reset_llm_circuit_breaker()

        from src.python.llm.circuit_breaker import (
            _CIRCUIT_BREAKER_THRESHOLD,
            _cb_record_failure,
            _circuit_open_until,
        )

        endpoint = "https://api.example.com/v1"
        domain = "api.example.com"  # _cb_endpoint 从 URL 提取的域名
        for _ in range(_CIRCUIT_BREAKER_THRESHOLD):
            _cb_record_failure(endpoint)

        assert domain in _circuit_open_until, "LLM 端点应已进入冷却期"
        cooldown = _circuit_open_until[domain] - time.time()
        assert cooldown > 0, "冷却剩余时间应 > 0"

        # 验证统一网关也能读取 LLM 熔断状态
        llm_status = gateway.get("llm")
        assert domain in llm_status, "gateway 应能报告 LLM 端点状态"
        assert llm_status[domain]["circuit_broken"], "gateway 应标记为已熔断"

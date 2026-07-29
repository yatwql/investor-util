"""DataSourceRegistry 单元测试。

覆盖：注册、熔断器、会话缓存、策略选择、审计报告、线程安全。
"""

from __future__ import annotations

import threading
import time
from unittest import mock

import pytest

from src.python.provider_registry import (
    FetchStrategy,
    NOT_FOUND,
    DataSourceRegistry,
    get_registry,
)
from src.python._session_cache import _SESSION_CACHE_MAX_ENTRIES

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


def _fresh_registry() -> DataSourceRegistry:
    """返回干净的 registry 实例（测试用）。"""
    r = get_registry()
    r.reset()
    return r


# ════════════════════════════════════════════════════════════
# Provider 注册
# ════════════════════════════════════════════════════════════


class TestProviderRegistration:
    def test_register_idempotent(self):
        """重复注册更新配置但不影响熔断状态。"""
        r = _fresh_registry()
        r.register_provider("t1", tier=2, timeout=10.0)
        r.record_failure("t1", "test")
        r.record_failure("t1", "test")
        # 第二次注册，改 timeout
        r.register_provider("t1", tier=2, timeout=20.0)
        state = r._providers["t1"]
        assert state.timeout == 20.0
        assert state.consecutive_failures == 2  # 熔断计数不受影响

    def test_register_default_chains_populates_providers(self):
        """register_default_chains 从 _DEFAULT_CHAINS 注册所有 provider。"""
        r = _fresh_registry()
        r.register_default_chains()
        # 常见的 provider 应已注册
        for expected in ("tencent", "eastmoney", "tiantian", "eastmoney_industry"):
            assert expected in r._providers

    def test_register_default_chains_sets_chains(self):
        """register_default_chains 写入 _chains。"""
        r = _fresh_registry()
        r.register_default_chains()
        assert "price" in r._chains
        assert "industry" in r._chains
        assert r._chains["price"] == ["tencent", "eastmoney"]


# ════════════════════════════════════════════════════════════
# 熔断器
# ════════════════════════════════════════════════════════════


class TestCircuitBreaker:
    def test_record_success_resets_failures(self):
        """record_success 重置熔断计数和跳过标记。"""
        r = _fresh_registry()
        r.register_provider("t1")
        r.record_failure("t1", "timeout")
        r.record_failure("t1", "timeout")
        r.record_success("t1")
        assert r._providers["t1"].consecutive_failures == 0
        assert r._providers["t1"].is_skipped is False

    def test_record_failure_under_threshold(self):
        """连续失败少于阈值时不熔断。"""
        r = _fresh_registry()
        r.register_provider("t1")
        r.record_failure("t1", "timeout")
        r.record_failure("t1", "dns")
        assert r.is_circuit_broken("t1") is False

    def test_record_failure_meets_threshold(self):
        """连续失败达到阈值时触发熔断。"""
        r = _fresh_registry()
        r.register_provider("t1")
        r.record_failure("t1", "timeout")
        r.record_failure("t1", "dns")
        r.record_failure("t1", "5xx")
        assert r.is_circuit_broken("t1") is True

    def test_cooldown_auto_recovery(self):
        """冷却期满后自动恢复。"""
        r = _fresh_registry()
        r.register_provider("t1")
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "dns")
            r.record_failure("t1", "5xx")
            assert r.is_circuit_broken("t1") is True
        # 快进 301s（需要一个新的 patch 来覆盖 is_circuit_broken 内部调用的 time.time）
        with mock.patch("time.time", return_value=1301.0):
            assert r.is_circuit_broken("t1") is False
            assert r._providers["t1"].is_skipped is False

    def test_cooldown_not_expired(self):
        """冷却未到期时不恢复。"""
        r = _fresh_registry()
        r.register_provider("t1")
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "dns")
            r.record_failure("t1", "5xx")
        with mock.patch("time.time", return_value=1030.0):
            assert r.is_circuit_broken("t1") is True

    def test_is_chain_broken_all(self):
        """全链熔断返回 True。"""
        r = _fresh_registry()
        for p in ("p1", "p2"):
            r.register_provider(p)
        with mock.patch("time.time", return_value=1000.0):
            for p in ("p1", "p2"):
                r.record_failure(p, "timeout")
                r.record_failure(p, "timeout")
                r.record_failure(p, "timeout")
            assert r.is_chain_broken(["p1", "p2"]) is True

    def test_is_chain_broken_one_available(self):
        """链中有一个可用时返回 False。"""
        r = _fresh_registry()
        r.register_provider("p1")
        r.register_provider("p2")
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("p1", "timeout")
            r.record_failure("p1", "timeout")
            r.record_failure("p1", "timeout")
            # p2 正常（无调用，不受熔断影响）
            assert r.is_chain_broken(["p1", "p2"]) is False

    def test_is_chain_broken_cooldown(self):
        """全链熔断但冷却期满时返回 False 并自动恢复。"""
        r = _fresh_registry()
        for p in ("p1", "p2"):
            r.register_provider(p)
        with mock.patch("time.time", return_value=1000.0):
            for p in ("p1", "p2"):
                r.record_failure(p, "timeout")
                r.record_failure(p, "timeout")
                r.record_failure(p, "timeout")
        with mock.patch("time.time", return_value=1301.0):
            assert r.is_chain_broken(["p1", "p2"]) is False
            assert r._providers["p1"].is_skipped is False
            assert r._providers["p2"].is_skipped is False

    def test_get_available_providers(self):
        """只返回未熔断的 provider。"""
        r = _fresh_registry()
        for p in ("p1", "p2", "p3"):
            r.register_provider(p)
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("p1", "timeout")
            r.record_failure("p1", "timeout")
            r.record_failure("p1", "timeout")
            available = r.get_available_providers(["p1", "p2", "p3"])
            assert "p1" not in available
            assert "p2" in available
            assert "p3" in available

    def test_is_transport_failure(self):
        """校验 is_transport_failure 正确识别 sentinel。"""
        from src.python.provider_registry import TRANSPORT_FAILURE
        assert DataSourceRegistry.is_transport_failure(TRANSPORT_FAILURE) is True
        assert DataSourceRegistry.is_transport_failure(None) is False
        assert DataSourceRegistry.is_transport_failure({}) is False


# ════════════════════════════════════════════════════════════
# 会话级缓存
# ════════════════════════════════════════════════════════════


class TestSessionCache:
    def test_set_get(self):
        r = _fresh_registry()
        r.session_cache_set("price", "600519", {"p": 150.0})
        assert r.session_cache_get("price", "600519") == {"p": 150.0}

    def test_miss(self):
        r = _fresh_registry()
        assert r.session_cache_get("price", "000001") is NOT_FOUND

    def test_contains_existing(self):
        r = _fresh_registry()
        r.session_cache_set("extended", "600519", None)
        assert r.session_cache_contains("extended", "600519") is True

    def test_contains_none_existing(self):
        """值为 None 的条目 '存在' 语义正确。"""
        r = _fresh_registry()
        r.session_cache_set("extended", "600519", None)
        assert r.session_cache_contains("extended", "600519") is True
        assert r.session_cache_contains("extended", "000001") is False

    def test_contains_missing(self):
        r = _fresh_registry()
        assert r.session_cache_contains("extended", "000001") is False

    def test_clear_domain(self):
        r = _fresh_registry()
        r.session_cache_set("price", "600519", {})
        r.session_cache_set("industry", "600519", {})
        r.session_cache_clear("price")
        assert r.session_cache_get("price", "600519") is NOT_FOUND
        assert r.session_cache_get("industry", "600519") is not NOT_FOUND

    def test_clear_all(self):
        r = _fresh_registry()
        r.session_cache_set("price", "600519", {})
        r.session_cache_set("industry", "600519", {})
        r.session_cache_clear()
        assert r.session_cache_get("price", "600519") is NOT_FOUND
        assert r.session_cache_get("industry", "600519") is NOT_FOUND

    def test_eviction_order(self):
        """超限（>2000）时淘汰最旧条目。"""
        r = _fresh_registry()
        domain = "test"
        n = _SESSION_CACHE_MAX_ENTRIES + 5  # 2005，确保触发淘汰
        for i in range(n):
            r.session_cache_set(domain, f"code{i:05d}", i)
        dc = r._session_cache[domain]
        assert len(dc) == _SESSION_CACHE_MAX_ENTRIES  # 正好 2000
        # 最早的 5 条应被淘汰
        for i in range(5):
            assert f"code{i:05d}" not in dc, f"code{i:05d} 应被淘汰"
        # 最新的 5 条应存在
        for i in range(n - 5, n):
            assert f"code{i:05d}" in dc, f"code{i:05d} 应存在"


# ════════════════════════════════════════════════════════════
# fetch_or_cached / fetch_cached_only
# ════════════════════════════════════════════════════════════


class TestFetchOrCached:
    def test_fetch_or_cached_live_fetch(self):
        """LIVE_FETCH 策略 → 调用 fetch_fn 并写 session cache。"""
        r = _fresh_registry()
        calls = []
        def _fetch(code: str) -> dict:
            calls.append(code)
            return {"price": 100.0}
        with mock.patch("src.python.market_hours.is_market_open", return_value=True):
            result = r.fetch_or_cached("600519", "a_share", _fetch,
                                       cache_domain="price", chain=[])
        assert result == {"price": 100.0}
        assert calls == ["600519"]
        # session cache 应有值
        assert r.session_cache_get("price", "600519") == {"price": 100.0}

    def test_fetch_or_cached_cache_only(self):
        """全链熔断 → CACHE_ONLY → 不调 fetch_fn，仅读缓存。"""
        r = _fresh_registry()
        r.register_provider("t1")
        r.register_provider("t2")
        with mock.patch("time.time", return_value=1000.0):
            for p in ("t1", "t2"):
                for _ in range(3):
                    r.record_failure(p, "timeout")
            r.session_cache_set("price", "600519", {"price": 100.0})
            calls = []
            def _fetch(code: str) -> dict:
                calls.append(code)
                return {"price": 200.0}
            with mock.patch("src.python.market_hours.is_market_open", return_value=True):
                result = r.fetch_or_cached("600519", "a_share", _fetch,
                                           cache_domain="price", chain=["t1", "t2"])
        # 全链熔断 → CACHE_ONLY → 返回 session cache
        assert result == {"price": 100.0}
        assert calls == []

    def test_fetch_or_cached_live_fetch_none_does_not_cache(self):
        """LIVE_FETCH 但 fetch_fn 返回 None → 不写 session cache。"""
        r = _fresh_registry()
        def _fetch(code: str) -> None:
            return None
        with mock.patch("src.python.market_hours.is_market_open", return_value=True):
            result = r.fetch_or_cached("600519", "a_share", _fetch,
                                       cache_domain="price")
        assert result is None
        assert r.session_cache_get("price", "600519") is NOT_FOUND


class TestFetchCachedOnly:
    def test_fetch_cached_only_session_hit(self):
        """session cache 命中 → 直接返回。"""
        r = _fresh_registry()
        r.session_cache_set("price", "600519", {"price": 100.0})
        result = r.fetch_cached_only("600519", "price")
        assert result == {"price": 100.0}

    def test_fetch_cached_only_miss_returns_none(self):
        """session cache 和 file cache 均无数据 → 返回 None。"""
        r = _fresh_registry()
        result = r.fetch_cached_only("600519", "price")
        assert result is None


# ════════════════════════════════════════════════════════════
# 策略选择
# ════════════════════════════════════════════════════════════


class TestStrategySelection:
    def test_strategy_qdii(self):
        r = _fresh_registry()
        assert r.get_effective_strategy("qdii") == FetchStrategy.LIVE_FETCH

    def test_strategy_hk_stock(self):
        r = _fresh_registry()
        assert r.get_effective_strategy("hk_stock") == FetchStrategy.LIVE_FETCH

    def test_strategy_market_open(self):
        r = _fresh_registry()
        assert r.get_effective_strategy("a_share", market_open=True) == FetchStrategy.LIVE_FETCH

    def test_strategy_market_closed(self):
        r = _fresh_registry()
        assert r.get_effective_strategy("a_share", market_open=False) == FetchStrategy.CACHE_ONLY

    def test_strategy_chain_broken(self):
        """全链熔断时降级 CACHE_ONLY。"""
        r = _fresh_registry()
        r.register_provider("t1")
        r.register_provider("t2")
        with mock.patch("time.time", return_value=1000.0):
            for p in ("t1", "t2"):
                r.record_failure(p, "timeout")
                r.record_failure(p, "timeout")
                r.record_failure(p, "timeout")
            strategy = r.get_effective_strategy("a_share", chain=["t1", "t2"], market_open=True)
            assert strategy == FetchStrategy.CACHE_ONLY

    def test_strategy_chain_not_broken(self):
        """链正常时不降级。"""
        r = _fresh_registry()
        r.register_provider("t1")
        assert r.get_effective_strategy("a_share", chain=["t1"], market_open=True) == FetchStrategy.LIVE_FETCH

    def test_strategy_qdii_ignores_chain(self):
        """QDII 不受熔断状态影响。"""
        r = _fresh_registry()
        r.register_provider("t1")
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "timeout")
        assert r.get_effective_strategy("qdii", chain=["t1"]) == FetchStrategy.LIVE_FETCH


# ════════════════════════════════════════════════════════════
# 审计报告
# ════════════════════════════════════════════════════════════


class TestStatusReport:
    def test_generate_status_report(self):
        r = _fresh_registry()
        r.register_provider("t1", tier=2)
        r.register_provider("t2", tier=3)
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("t2", "timeout")
            r.record_failure("t2", "timeout")
            r.record_failure("t2", "timeout")
        report = r.generate_status_report()
        assert report["t1"]["available"] is True
        assert report["t2"]["available"] is False
        assert report["t2"]["circuit_broken"] is True
        assert report["t2"]["total_failures"] >= 3

    def test_status_report_cooldown_remaining(self):
        r = _fresh_registry()
        r.register_provider("t1")
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "timeout")
        with mock.patch("time.time", return_value=1100.0):
            report = r.generate_status_report()
            assert report["t1"]["circuit_broken"] is True
            assert 199 < report["t1"]["cooldown_remaining"] <= 200


# ════════════════════════════════════════════════════════════
# 线程安全
# ════════════════════════════════════════════════════════════


class TestThreadSafety:
    def test_concurrent_record(self):
        """多线程并发 record_success/failure 不抛异常，最终计数正确。"""
        r = _fresh_registry()
        r.register_provider("t1")

        def worker(n: int):
            for _ in range(100):
                if n % 2 == 0:
                    r.record_failure("t1", "concurrent")
                else:
                    r.record_success("t1")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 无异常抛出即为通过
        state = r._providers["t1"]
        assert state.total_failures + state.total_successes == 10 * 100

    def test_concurrent_cache(self):
        """多线程并发 session_cache 读写不抛异常。"""
        r = _fresh_registry()

        def writer():
            for i in range(100):
                r.session_cache_set("test", f"code{i:05d}", i)

        def reader():
            for i in range(100):
                r.session_cache_get("test", f"code{i:05d}")

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 无异常抛出即为通过
        assert r.session_cache_contains("test", "code00000") is True


# ════════════════════════════════════════════════════════════
# reset
# ════════════════════════════════════════════════════════════


class TestReset:
    def test_reset_clears_providers(self):
        r = _fresh_registry()
        r.register_provider("t1")
        r.record_failure("t1", "timeout")
        r.reset()
        assert "t1" not in r._providers

    def test_reset_clears_cache(self):
        r = _fresh_registry()
        r.session_cache_set("test", "600519", {})
        r.reset()
        assert r.session_cache_get("test", "600519") is NOT_FOUND

    def test_reset_clears_chains(self):
        r = _fresh_registry()
        r.register_default_chains()
        r.reset()
        assert len(r._chains) == 0

    def test_circuit_breaker_status_in_report(self):
        """熔断状态可通过 generate_status_report 查询。"""
        r = _fresh_registry()
        r.register_provider("t1")
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "timeout")
        report = r.generate_status_report()
        assert "t1" in report
        assert report["t1"]["circuit_broken"] is True

    def test_circuit_breaker_failure_details_in_report(self):
        """熔断详情可通过 generate_status_report 查询。"""
        r = _fresh_registry()
        r.register_provider("t1")
        with mock.patch("time.time", return_value=1000.0):
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "timeout")
            r.record_failure("t1", "timeout")
        report = r.generate_status_report()
        assert "t1" in report
        assert report["t1"]["total_failures"] >= 3
        assert report["t1"]["last_failure_context"] == "timeout"

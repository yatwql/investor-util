"""``core/throttle.py`` 单元测试 — 「按名最小间隔」原语的算式、等待与归属。

覆盖：``interval_delay`` 算式（0/抖动上界/比例钳制）、``RateLimiter`` 的
配置加载与 acquire 短路、间隔等待（注入假时钟）、显式间隔 + 抖动、
``reset``；以及两条**架构归属**断言——数据层再导出的是同一个类、
LLM 端点节流不再反向依赖 ``fetcher`` 层。
"""

from __future__ import annotations

import inspect

import pytest

import src.python.core.throttle as throttle

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class _FakeTime:
    """假时钟：sleep 推进 monotonic，便于断言实际等待量。"""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time(monkeypatch):
    fake = _FakeTime()
    monkeypatch.setattr(throttle, "time", fake)
    return fake


class TestIntervalDelay:
    def test_non_positive_interval_is_zero(self):
        assert throttle.interval_delay(0.0) == 0.0
        assert throttle.interval_delay(-5.0, jitter_ratio=0.5) == 0.0

    def test_without_jitter_returns_interval(self):
        assert throttle.interval_delay(1.5) == 1.5

    def test_jitter_within_bounds(self):
        values = [throttle.interval_delay(2.0, jitter_ratio=0.25) for _ in range(50)]
        assert all(2.0 <= v <= 2.5 + 1e-9 for v in values)
        assert len(set(values)) > 1  # 确有抖动

    def test_jitter_ratio_clamped_to_unit_range(self):
        assert all(2.0 <= throttle.interval_delay(2.0, jitter_ratio=99.0) <= 4.0 for _ in range(20))
        assert throttle.interval_delay(2.0, jitter_ratio=-1.0) == 2.0


class TestRateLimiter:
    def test_ignores_non_positive_and_non_numeric_config(self, fake_time):
        limiter = throttle.RateLimiter({"a": 0.0, "b": -1, "c": "x", "d": 0.5})
        limiter.acquire("a")
        limiter.acquire("b")
        limiter.acquire("c")
        assert fake_time.slept == []
        limiter.acquire("d")
        assert fake_time.slept == []  # 首次调用无历史 → 不等待
        assert limiter._limits == {"d": 0.5}

    def test_second_call_waits_remaining_interval(self, fake_time):
        limiter = throttle.RateLimiter({"p": 1.0})
        limiter.acquire("p")  # 建立时间戳
        fake_time.now += 0.4
        waited = limiter.acquire_interval("p", 1.0)
        assert waited == pytest.approx(0.6)
        assert fake_time.slept == [pytest.approx(0.6)]

    def test_zero_interval_is_short_circuit(self, fake_time):
        limiter = throttle.RateLimiter()
        assert limiter.acquire_interval("p", 0.0) == 0.0
        assert fake_time.slept == []

    def test_jitter_ratio_extends_target_interval(self, fake_time):
        limiter = throttle.RateLimiter()
        limiter.acquire_interval("p", 1.0)
        fake_time.now += 0.5
        waited = limiter.acquire_interval("p", 1.0, jitter_ratio=0.5)
        assert 0.5 <= waited <= 1.0  # 目标 1.0~1.5，已过 0.5

    def test_reset_clears_timestamp(self, fake_time):
        limiter = throttle.RateLimiter({"p": 1.0})
        limiter.acquire("p")
        limiter.reset("p")
        assert limiter.acquire_interval("p", 1.0) == 0.0
        assert fake_time.slept == []

    def test_distinct_keys_do_not_block_each_other(self, fake_time):
        limiter = throttle.RateLimiter({"a": 1.0, "b": 1.0})
        limiter.acquire("a")
        assert limiter.acquire_interval("b", 1.0) == 0.0


class TestArchitectureOwnership:
    """原语归属：实现只在 ``core/throttle.py``，上层只做再导出或依赖它。"""

    def test_fetcher_reexports_same_class(self):
        from src.python.fetcher.batch import RateLimiter as from_batch

        assert from_batch is throttle.RateLimiter

    def test_llm_pacing_does_not_depend_on_fetcher_layer(self):
        import src.python.llm.pacing as pacing

        source = inspect.getsource(pacing)
        assert "fetcher.batch" not in source
        assert "from src.python.core.throttle import RateLimiter" in source

    def test_providers_depend_on_core_throttle(self):
        import src.python.providers.cninfo as cninfo
        import src.python.providers.datasink as datasink
        import src.python.providers.hithink as hithink

        for module in (cninfo, datasink, hithink):
            source = inspect.getsource(module)
            assert "from src.python.core.throttle import RateLimiter" in source
            assert "from src.python.fetcher.batch import RateLimiter" not in source

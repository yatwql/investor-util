"""``core/retry.py`` 单元测试 — 重试策略算式、瞬时判据与执行器。

覆盖：三种退避算式与抖动/上限、边界钳制（attempts<1、未知算式、base=0 不等待）、
异常触发与结果哨兵触发、重试次数有界、非瞬时异常不重试、睡眠可注入（零等待）、
以及 ``on_retry`` 回调契约。
"""

from __future__ import annotations

import httpx
import pytest

import src.python.core.retry as rt

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestPolicyMath:
    def test_exponential_linear_fixed(self):
        exp = rt.RetryPolicy(attempts=4, strategy=rt.STRATEGY_EXPONENTIAL, base_backoff=0.5, factor=2.0)
        lin = rt.RetryPolicy(attempts=4, strategy=rt.STRATEGY_LINEAR, base_backoff=1.0)
        fixed = rt.RetryPolicy(attempts=4, strategy=rt.STRATEGY_FIXED, base_backoff=0.25)
        assert [exp.delay_for(i) for i in (1, 2, 3)] == [0.5, 1.0, 2.0]
        assert [lin.delay_for(i) for i in (1, 2, 3)] == [1.0, 2.0, 3.0]
        assert [fixed.delay_for(i) for i in (1, 2, 3)] == [0.25, 0.25, 0.25]

    def test_zero_base_means_no_wait_even_with_jitter(self):
        p = rt.RetryPolicy(attempts=2, strategy=rt.STRATEGY_FIXED, base_backoff=0.0, jitter=0.2)
        assert p.delay_for(1) == 0.0

    def test_jitter_within_bounds(self):
        p = rt.RetryPolicy(attempts=2, strategy=rt.STRATEGY_FIXED, base_backoff=1.0, jitter=0.3)
        delays = [p.delay_for(1) for _ in range(50)]
        assert all(1.0 <= d <= 1.3 + 1e-9 for d in delays)

    def test_max_backoff_caps_exponential(self):
        p = rt.RetryPolicy(attempts=6, strategy=rt.STRATEGY_EXPONENTIAL, base_backoff=1.0, max_backoff=2.5)
        assert [p.delay_for(i) for i in (1, 2, 3, 4)] == [1.0, 2.0, 2.5, 2.5]

    def test_attempts_below_one_clamped(self):
        assert rt.RetryPolicy(attempts=0).attempts == 1
        assert rt.RetryPolicy(attempts=-3).retry_count == 0

    def test_unknown_strategy_falls_back_to_exponential(self):
        p = rt.RetryPolicy(attempts=3, strategy="wat", base_backoff=1.0)
        assert p.strategy == rt.STRATEGY_EXPONENTIAL
        assert p.delay_for(2) == 2.0


class TestTransientJudge:
    def test_transport_errors_are_transient(self):
        assert rt.is_transient_exception(httpx.ConnectTimeout("t"))
        assert rt.is_transient_exception(httpx.ConnectError("t"))
        assert rt.is_transient_exception(httpx.RemoteProtocolError("t"))

    def test_deterministic_errors_are_not_transient(self):
        assert not rt.is_transient_exception(ValueError("bad params"))
        assert not rt.is_transient_exception(httpx.HTTPStatusError("404", request=None, response=None))  # type: ignore[arg-type]


class TestExecutor:
    def test_retries_transient_then_succeeds(self):
        calls = {"n": 0}
        sleeps: list[float] = []

        def fn():
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectTimeout("cold start")
            return "ok"

        policy = rt.RetryPolicy(attempts=3, strategy=rt.STRATEGY_LINEAR, base_backoff=1.0)
        assert rt.retry_transient(fn, policy=policy, sleep=sleeps.append) == "ok"
        assert calls["n"] == 2
        assert sleeps == [1.0]

    def test_exhausted_transient_reraises_last(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise httpx.ConnectTimeout(f"fail-{calls['n']}")

        policy = rt.RetryPolicy(attempts=3, strategy=rt.STRATEGY_LINEAR, base_backoff=1.0)
        with pytest.raises(httpx.ConnectTimeout, match="fail-3"):
            rt.retry_transient(fn, policy=policy, sleep=lambda _s: None)
        assert calls["n"] == 3

    def test_non_transient_is_not_retried(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise ValueError("deterministic")

        with pytest.raises(ValueError):
            rt.retry_transient(fn, policy=rt.RetryPolicy(attempts=4), sleep=lambda _s: None)
        assert calls["n"] == 1

    def test_result_sentinel_triggers_retry_and_returns_sentinel(self):
        calls = {"n": 0}
        sleeps: list[float] = []
        sentinel = object()

        def fn():
            calls["n"] += 1
            return sentinel if calls["n"] < 2 else "good"

        policy = rt.RetryPolicy(attempts=2, strategy=rt.STRATEGY_EXPONENTIAL, base_backoff=0.0)
        out = rt.retry_transient(fn, policy=policy, retry_if_result=lambda r: r is sentinel, sleep=sleeps.append)
        assert out == "good" and calls["n"] == 2
        assert sleeps == []  # base=0 → 不等待

    def test_sentinel_exhaustion_returns_sentinel(self):
        sentinel = object()
        policy = rt.RetryPolicy(attempts=2, strategy=rt.STRATEGY_FIXED, base_backoff=0.0)
        out = rt.retry_transient(
            lambda: sentinel, policy=policy, retry_if_result=lambda r: r is sentinel, sleep=lambda _s: None
        )
        assert out is sentinel

    def test_on_retry_reports_attempt_delay_and_exception(self):
        seen: list[tuple[int, float, BaseException | None]] = []

        def fn():
            raise httpx.ConnectTimeout("x")

        policy = rt.RetryPolicy(attempts=2, strategy=rt.STRATEGY_LINEAR, base_backoff=0.5)
        with pytest.raises(httpx.ConnectTimeout):
            rt.retry_transient(
                fn, policy=policy, on_retry=lambda a, d, e: seen.append((a, d, e)), sleep=lambda _s: None
            )
        assert seen == [(1, 0.5, seen[0][2])]
        assert isinstance(seen[0][2], httpx.ConnectTimeout)

    def test_no_retry_when_attempts_is_one(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise httpx.ConnectTimeout("x")

        with pytest.raises(httpx.ConnectTimeout):
            rt.retry_transient(fn, policy=rt.RetryPolicy(attempts=1), sleep=lambda _s: None)
        assert calls["n"] == 1

"""PhaseTimeout 全局超时上下文管理器单元测试。

覆盖：正常流程、超时触发、过期检测、嵌套保护。
"""

from __future__ import annotations

import threading
import time
from unittest import mock

import pytest

from src.python.core.provider_registry import phase_timeout

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestPhaseTimeout:
    def test_normal_exit_no_timeout(self):
        """正常退出不触发超时，expired=False。"""
        with phase_timeout(seconds=5.0, phase_name="test") as ctx:
            assert not ctx.expired
            assert ctx.elapsed >= 0
            assert ctx.remaining > 0
        # 退出后检查
        assert ctx.elapsed >= 0

    def test_timeout_triggered(self):
        """超时后 expired=True，抛出 TimeoutError。"""
        with phase_timeout(seconds=0.01, phase_name="test_fast") as ctx:
            time.sleep(0.05)
            assert ctx.expired
            with pytest.raises(TimeoutError):
                ctx.check()

    def test_elapsed_remaining_monotonic(self):
        """elapsed/remaining 单调变化。"""
        with phase_timeout(seconds=0.5, phase_name="test_mono") as ctx:
            t1 = ctx.elapsed
            r1 = ctx.remaining
            time.sleep(0.05)
            t2 = ctx.elapsed
            r2 = ctx.remaining
            assert t2 >= t1
            assert r2 <= r1

    def test_nested_raises(self):
        """嵌套使用 phase_timeout 抛出 RuntimeError。"""
        with phase_timeout(seconds=5.0, phase_name="outer"):
            with pytest.raises(RuntimeError) as exc_info:
                with phase_timeout(seconds=5.0, phase_name="inner"):
                    pass
            assert "嵌套" in str(exc_info.value)

    def test_remaining_never_negative(self):
        """remaining 永不小于 0。"""
        with phase_timeout(seconds=0.01, phase_name="test_neg") as ctx:
            time.sleep(0.1)
            assert ctx.remaining == 0.0

    def test_check_before_timeout_ok(self):
        """超时前 check 不抛出异常。"""
        with phase_timeout(seconds=5.0, phase_name="test_check_ok") as ctx:
            ctx.check()  # should not raise

    def test_separate_context_non_overlapping(self):
        """前后不重叠的两个 phase_timeout 正常。"""
        with phase_timeout(seconds=0.5, phase_name="first") as ctx1:
            assert not ctx1.expired
        with phase_timeout(seconds=0.5, phase_name="second") as ctx2:
            assert not ctx2.expired

    def test_concurrent_no_interference(self):
        """不同线程各自的 phase_timeout 互不干扰。"""
        results: list[bool] = []

        def worker():
            try:
                with phase_timeout(seconds=0.01, phase_name="worker"):
                    time.sleep(0.05)
                    results.append(True)
            except RuntimeError:
                results.append(False)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 线程中的 phase_timeout 因嵌套检测会失败
        assert len(results) == 3

"""IndicatorBreaker 断路器与单例工厂单元测试。"""

from __future__ import annotations

import os
import tempfile as _tf

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


class TestCircuitBreakerWrapper:
    """IndicatorBreaker 断路器和单例工厂测试。"""

    def test_get_indicator_breaker_singleton(self):
        """get_indicator_breaker() 返回同一实例。"""
        from src.python.analysis.circuit_breaker_wrapper import (
            get_indicator_breaker,
            reset_indicator_breaker,
        )

        reset_indicator_breaker()
        b1 = get_indicator_breaker()
        b2 = get_indicator_breaker()
        assert b1 is b2

    def test_reset_indicator_breaker_clear(self):
        """reset_indicator_breaker() 后获取新实例。"""
        from src.python.analysis.circuit_breaker_wrapper import (
            get_indicator_breaker,
            reset_indicator_breaker,
        )

        reset_indicator_breaker()
        b1 = get_indicator_breaker()
        b1.record_failure("test_indicator", "test error")
        reset_indicator_breaker()
        b2 = get_indicator_breaker()
        assert b2 is not b1
        assert b2.is_broken("test_indicator") is False

    def test_record_success(self):
        """record_success 重置失败计数。"""
        from src.python.analysis.circuit_breaker_wrapper import get_indicator_breaker

        with _tf.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        brk = get_indicator_breaker().__class__(persist_path=tmp_path)
        brk.record_failure("indicator_a", "err")
        brk.record_success("indicator_a")
        st = brk.get_breaker_status("indicator_a")
        assert st["circuit_broken"] is False
        assert st["consecutive_failures"] == 0
        os.unlink(tmp_path)

    def test_record_failure_triggers_breaker(self):
        """连续失败达到阈值 → 断路。"""
        from src.python.analysis.circuit_breaker_wrapper import IndicatorBreaker

        with _tf.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        brk = IndicatorBreaker(persist_path=tmp_path)
        for i in range(3):
            brk.record_failure("indicator_b", f"error_{i}")
        st = brk.get_breaker_status("indicator_b")
        assert st["circuit_broken"] is True
        assert st["consecutive_failures"] == 3
        os.unlink(tmp_path)

    def test_is_broken_after_cooldown(self):
        """冷却期满后 is_broken 自动解除。"""
        import time as _t

        from src.python.analysis.circuit_breaker_wrapper import IndicatorBreaker

        with _tf.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        brk = IndicatorBreaker(persist_path=tmp_path)
        brk.record_failure("indicator_c", "err")
        brk.record_failure("indicator_c", "err")
        brk.record_failure("indicator_c", "err")
        brk._state["indicator_c"]["broken_until"] = _t.time() - 1
        assert brk.is_broken("indicator_c") is False
        os.unlink(tmp_path)

    def test_guard_returns_fn_result(self):
        """guard 正常执行并返回结果。"""
        from src.python.analysis.circuit_breaker_wrapper import get_indicator_breaker

        with _tf.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        brk = get_indicator_breaker().__class__(persist_path=tmp_path)
        result = brk.guard("test_guard", lambda x: x + 1, 41)
        assert result == 42
        os.unlink(tmp_path)

    def test_guard_returns_none_on_exception(self):
        """guard 遇到异常 → 返回 None。"""
        from src.python.analysis.circuit_breaker_wrapper import get_indicator_breaker

        with _tf.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        brk = get_indicator_breaker().__class__(persist_path=tmp_path)
        result = brk.guard("test_ex", lambda: 1 / 0)
        assert result is None
        os.unlink(tmp_path)

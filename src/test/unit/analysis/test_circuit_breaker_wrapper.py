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


class TestMetricsBreakerPersistencePath:
    """指标熔断器持久化路径（data/state/ 迁移）。"""

    def test_default_path_under_state_dir(self):
        """默认持久化路径应位于 data/state/ 而非 data/cache/。"""
        from src.python.analysis import circuit_breaker_wrapper as _cbw

        path = _cbw._METRICS_BREAKER_FILE
        # 跨平台路径规范化：Windows 分隔符为 \，统一转 / 再匹配（源码/conftest 均用 os.path/pathlib 构造）
        path_posix = path.replace(os.sep, "/")
        assert "data/state/metrics_breaker.json" in path_posix, (
            f"默认路径应指向 data/state/metrics_breaker.json，实际 {path}"
        )
        assert "data/cache" not in path_posix, f"不应再指向 data/cache，实际 {path}"


class TestMetricsFeatureFlagLinkage:
    """量化指标总开关（``metrics_enabled``）↔ 断路器联动。

    原 7 个逐项 ``metrics_*`` 开关合并为单开关后，联动口径收敛到一处；本类覆盖
    此前无任何用例的联动语义（关闭期不计失败 / 关闭时自动解熔 / 开回时清残留），
    以及「无对应开关的指标不受约束」的边界。
    """

    @staticmethod
    def _make_breaker(tmp_path):
        from src.python.analysis.circuit_breaker_wrapper import IndicatorBreaker

        return IndicatorBreaker(persist_path=str(tmp_path / "breaker.json"))

    @staticmethod
    def _set_flag(monkeypatch, value: bool) -> None:
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "metrics_enabled", value)

    def test_flag_off_does_not_count_failures(self, tmp_path, monkeypatch):
        """总开关关闭 → 全部联动指标不计失败（多次失败也不断路）。"""
        from src.python.analysis.circuit_breaker_wrapper import (
            _DEFAULT_MAX_FAILURES,
            _METRIC_INDICATOR_NAMES,
        )

        brk = self._make_breaker(tmp_path)
        self._set_flag(monkeypatch, False)
        for name in _METRIC_INDICATOR_NAMES:
            for _ in range(_DEFAULT_MAX_FAILURES + 2):
                brk.record_failure(name, "err")

        assert brk.summary() == {}, "关闭期失败被计数了（应不计并保持无断路状态）"

    def test_flag_on_counts_failures_to_break(self, tmp_path, monkeypatch):
        """总开关开启 → 连续失败达到阈值即断路（联动不吞计数）。"""
        from src.python.analysis.circuit_breaker_wrapper import _DEFAULT_MAX_FAILURES

        brk = self._make_breaker(tmp_path)
        self._set_flag(monkeypatch, True)
        for _ in range(_DEFAULT_MAX_FAILURES):
            brk.record_failure("sharpe_ratio", "err")

        assert brk.is_broken("sharpe_ratio") is True

    def test_unmapped_indicator_not_gated_by_flag(self, tmp_path, monkeypatch):
        """无对应开关的指标不受总开关约束 → 关闭开关仍照常计数断路。"""
        from src.python.analysis.circuit_breaker_wrapper import _DEFAULT_MAX_FAILURES

        brk = self._make_breaker(tmp_path)
        self._set_flag(monkeypatch, False)
        for _ in range(_DEFAULT_MAX_FAILURES):
            brk.record_failure("custom_indicator", "err")

        assert brk.is_broken("custom_indicator") is True

    def test_guard_skips_compute_when_flag_off(self, tmp_path, monkeypatch):
        """总开关关闭 → guard 返回 None 且不执行计算；映射外指标照常执行。"""
        brk = self._make_breaker(tmp_path)
        self._set_flag(monkeypatch, False)
        calls: list[int] = []

        assert brk.guard("sharpe_ratio", lambda: calls.append(1) or 1) is None
        assert calls == [], "开关关闭时不得执行指标计算"

        assert brk.guard("custom_indicator", lambda: calls.append(1) or 1) == 1
        assert calls == [1]

    def test_flag_off_clears_broken_state(self, tmp_path, monkeypatch):
        """已断路后关闭总开关 → 下一次 guard 自动解除断路（不计为失败）。"""
        from src.python.analysis.circuit_breaker_wrapper import _DEFAULT_MAX_FAILURES

        brk = self._make_breaker(tmp_path)
        self._set_flag(monkeypatch, True)
        for _ in range(_DEFAULT_MAX_FAILURES):
            brk.record_failure("sharpe_ratio", "err")
        assert brk.is_broken("sharpe_ratio") is True

        self._set_flag(monkeypatch, False)
        assert brk.guard("sharpe_ratio", lambda: 1) is None

        self._set_flag(monkeypatch, True)
        assert brk.is_broken("sharpe_ratio") is False, "开关关闭期应自动解熔"

    def test_flag_cycle_clears_residual_failure_count(self, tmp_path, monkeypatch):
        """开 → 关 → 开一个周期后，关闭前的残留失败计数清零（不跨周期累计）。

        缺陷场景：``_ff_was_off`` 标记只读不写，开关「开回时重置断路器」的契约
        从未生效——关闭前的计数跨周期累计，可能在开关刚打开时就误触发断路。
        """
        brk = self._make_breaker(tmp_path)
        self._set_flag(monkeypatch, True)
        brk.record_failure("calmar_ratio", "err")
        brk.record_failure("calmar_ratio", "err")  # 未达阈值，残留计数
        assert brk.is_broken("calmar_ratio") is False

        self._set_flag(monkeypatch, False)
        brk.guard("calmar_ratio", lambda: 1)  # 关闭期打标
        self._set_flag(monkeypatch, True)
        brk.guard("calmar_ratio", lambda: 1)  # 开回 → 清残留

        brk.record_failure("calmar_ratio", "err")
        brk.record_failure("calmar_ratio", "err")  # 残留若未清零：2+2 ≥ 阈值 → 断路
        assert brk.is_broken("calmar_ratio") is False

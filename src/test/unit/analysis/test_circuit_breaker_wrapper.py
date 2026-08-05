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
        assert "data/state/metrics_breaker.json" in path_posix, f"默认路径应指向 data/state/metrics_breaker.json，实际 {path}"
        assert "data/cache" not in path_posix, f"不应再指向 data/cache，实际 {path}"

    def test_legacy_file_migrated_on_load(self, monkeypatch, tmp_path):
        """旧路径 data/cache/metrics_breaker.json 存在 → 加载时自动改写至新的持久化位置并删除旧文件。"""
        import json as _json

        from src.python.analysis.circuit_breaker_wrapper import IndicatorBreaker

        import time as _t

        legacy_path = str(tmp_path / "data/cache/metrics_breaker.json")
        new_path = str(tmp_path / "data/state/metrics_breaker.json")
        os.makedirs(os.path.dirname(legacy_path), exist_ok=True)
        with open(legacy_path, "w", encoding="utf-8") as f:
            _json.dump({"old_indicator": {"consecutive_failures": 2, "_saved_at": _t.time()}}, f)

        monkeypatch.setattr(
            "src.python.analysis.circuit_breaker_wrapper._LEGACY_METRICS_BREAKER_FILE",
            legacy_path,
        )
        brk = IndicatorBreaker(persist_path=new_path)

        # 状态已从旧文件加载
        assert brk._state.get("old_indicator", {}).get("consecutive_failures") == 2
        # 新路径文件已写入，旧文件已删除
        assert os.path.exists(new_path)
        assert not os.path.exists(legacy_path)

    def test_legacy_migration_skipped_when_new_exists(self, monkeypatch, tmp_path):
        """新路径已存在 → 不执行迁移，保留新文件内容。"""
        import json as _json

        from src.python.analysis.circuit_breaker_wrapper import IndicatorBreaker

        import time as _t

        legacy_path = str(tmp_path / "data/cache/metrics_breaker.json")
        new_path = str(tmp_path / "data/state/metrics_breaker.json")
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        with open(new_path, "w", encoding="utf-8") as f:
            _json.dump({"new_indicator": {"consecutive_failures": 1, "_saved_at": _t.time()}}, f)
        # 旧文件也存在，但新路径优先
        os.makedirs(os.path.dirname(legacy_path), exist_ok=True)
        with open(legacy_path, "w", encoding="utf-8") as f:
            _json.dump({"old_indicator": {"consecutive_failures": 9, "_saved_at": _t.time()}}, f)

        monkeypatch.setattr(
            "src.python.analysis.circuit_breaker_wrapper._LEGACY_METRICS_BREAKER_FILE",
            legacy_path,
        )
        brk = IndicatorBreaker(persist_path=new_path)

        assert "new_indicator" in brk._state
        assert "old_indicator" not in brk._state
        # 旧文件保留（迁移未执行，因为新文件已存在）
        assert os.path.exists(legacy_path)

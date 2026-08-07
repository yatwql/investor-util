"""WebProgressReporter 单元测试（progress.py）。

覆盖：事件按 run 隔离 / seq 单调递增 / level 正确 / add_error 同步 /
call_sheet 成功与失败路径。
"""

from __future__ import annotations

import pytest

from src.python.web.progress import WebProgressReporter
from src.python.web.runs import RunState

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


def _make_state(run_id: str = "run-test") -> RunState:
    return RunState(run_id, {"report_type": "basic"})


class TestEventBuffering:
    """事件缓冲行为。"""

    def test_events_isolated_by_run(self):
        """事件按 run 隔离：两个 RunState 互不串扰。"""
        s1 = _make_state("run-1")
        s2 = _make_state("run-2")
        WebProgressReporter(s1).info("第一条")
        WebProgressReporter(s2).ok("另一条")

        assert [e["message"] for e in s1.events_after(0)] == ["第一条"]
        assert [e["message"] for e in s2.events_after(0)] == ["另一条"]

    def test_seq_monotonic(self):
        """seq 单调递增（非时间戳，测试确定性）。"""
        reporter = WebProgressReporter(_make_state())
        seqs = [reporter.info(f"消息{i}") for i in range(5)]
        assert seqs == [1, 2, 3, 4, 5]

    def test_level_mapping(self):
        """info/ok/warn/error 各 level 写入正确。"""
        state = _make_state()
        reporter = WebProgressReporter(state)
        reporter.info("i")
        reporter.ok("o")
        reporter.warn("w")
        reporter.error("e")

        events = state.events_after(0)
        assert [e["level"] for e in events] == ["info", "ok", "warn", "error"]

    def test_incremental_after(self):
        """events_after(N) 仅返回序号 > N 的增量事件（轮询增量通道）。"""
        state = _make_state()
        reporter = WebProgressReporter(state)
        reporter.info("1")
        reporter.info("2")
        reporter.info("3")

        after_two = state.events_after(2)
        assert len(after_two) == 1
        assert after_two[0]["message"] == "3"
        assert after_two[0]["seq"] == 3

    def test_event_cap_rolls_oldest(self):
        """事件缓冲上限 _EVENT_LIMIT：超出滚动丢弃最旧。"""
        state = _make_state()
        reporter = WebProgressReporter(state)
        for i in range(600):
            reporter.info(f"e{i}")
        events = state.events_after(0)
        # 保留最近 500 条
        assert len(events) == 500
        assert events[0]["message"] == "e100"  # 丢弃 e0..e99

    def test_add_error_syncs_state(self):
        """add_error：事件缓冲 + run 错误列表 + get_errors 三处同步。"""
        state = _make_state()
        reporter = WebProgressReporter(state)
        reporter.add_error("某模块失败")

        assert state.errors == ["某模块失败"]
        assert reporter.get_errors() == ["某模块失败"]
        assert state.events_after(0)[-1]["level"] == "error"


class TestCallSheet:
    """call_sheet 安全调用语义（对齐 TuiProgressReporter）。"""

    def test_call_sheet_success(self):
        """成功：先 info「正在生成X...」再 ok「X生成完成」。"""
        state = _make_state()
        reporter = WebProgressReporter(state)
        called = []

        def fake_fn():
            called.append(True)
            return None

        ok = reporter.call_sheet("行情页", fake_fn)
        assert ok is True
        assert called == [True]
        messages = [e["message"] for e in state.events_after(0)]
        assert messages[0] == "正在生成行情页..."
        assert messages[-1] == "行情页生成完成"

    def test_call_sheet_failure_adds_error(self):
        """失败：add_error 记录错误，返回 False，不抛异常。"""
        state = _make_state()
        reporter = WebProgressReporter(state)

        def boom():
            raise RuntimeError("写盘失败")

        ok = reporter.call_sheet("明细页", boom)
        assert ok is False
        assert state.errors == ["明细页生成失败（详情请查看日志）"]

    def test_call_sheet_none_module(self):
        """fn 为 None（模块缺失）：add_error 并返回 False。"""
        state = _make_state()
        reporter = WebProgressReporter(state)
        ok = reporter.call_sheet("穿透页", None)
        assert ok is False
        assert "穿透页模块缺失" in state.errors[0]

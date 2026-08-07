"""RunManager 单元测试（runs.py）。

覆盖：submit→running→done 状态机 / exit_code 映射 / executor 异常兜底 /
并发提交各自隔离（单 worker 串行）/ 队列容量上限 / run 保留上限 /
单例重置（_auto_reset_run_manager 语义）。
"""

from __future__ import annotations

import time

import pytest

from src.python.web.runs import (
    _QUEUE_LIMIT,
    _RUN_KEEP,
    RunManager,
    get_run_manager,
    reset_run_manager,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


def _wait_done(manager: RunManager, run_id: str, timeout: float = 3.0):
    """轮询等待 run 进入终态（done/failed），返回 RunState。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = manager.get(run_id)
        if state is not None and state.status in ("done", "failed"):
            return state
        time.sleep(0.005)
    raise AssertionError(f"run {run_id} 未在 {timeout}s 内完成（status={manager.get(run_id).status}）")


def _make_executor(code: int):
    """返回固定退出码的 fake executor。"""

    def _exec(state, params):
        state.push_event("info", f"执行 {state.run_id}")
        return code

    return _exec


class TestStateMachine:
    """submit → running → done 状态机与退出码。"""

    def test_submit_to_done(self):
        """submit 返回 run_id，worker 执行后 done，exit_code 正确映射。"""
        m = RunManager(executor=_make_executor(0))
        run_id = m.submit({"report_type": "basic"})
        assert run_id

        state = _wait_done(m, run_id)
        assert state.status == "done"
        assert state.exit_code == 0
        assert state.started_at is not None
        assert state.finished_at is not None
        assert state.started_at <= state.finished_at

    def test_exit_code_mapping(self):
        """exit_code 0/1/2 透传（对应 ReportResult 成功/部分失败/严重）。"""
        for code in (0, 1, 2):
            m = RunManager(executor=_make_executor(code))
            run_id = m.submit({"report_type": "basic"})
            state = _wait_done(m, run_id)
            assert state.status == "done"
            assert state.exit_code == code

    def test_executor_exception_marks_failed(self):
        """executor 抛异常：run 置 failed + 错误记录，服务不崩溃。"""

        def boom(_state, _params):
            raise RuntimeError("boom")

        m = RunManager(executor=boom)
        run_id = m.submit({"report_type": "basic"})
        state = _wait_done(m, run_id)
        assert state.status == "failed"
        assert state.errors == ["任务执行异常（详情请查看日志）"]

    def test_events_reach_run_state(self):
        """executor 推送的事件可通过 run 状态增量读取。"""
        m = RunManager(executor=_make_executor(0))
        run_id = m.submit({"report_type": "basic"})
        state = _wait_done(m, run_id)
        events = state.events_after(0)
        assert len(events) == 1
        assert events[0]["message"] == f"执行 {run_id}"


class TestConcurrency:
    """单 worker 串行队列与隔离。"""

    def test_concurrent_submits_isolated(self):
        """连续两次 submit：run_id 不同，串行执行各自完成。"""
        m = RunManager(executor=_make_executor(0))
        id_a = m.submit({"report_type": "both"})
        id_b = m.submit({"report_type": "full"})
        assert id_a != id_b

        state_a = _wait_done(m, id_a)
        state_b = _wait_done(m, id_b)
        assert state_a.status == "done"
        assert state_b.status == "done"
        # 参数各自隔离
        assert state_a.params["report_type"] == "both"
        assert state_b.params["report_type"] == "full"

    def test_queue_full_rejects(self):
        """队列容量上限 _QUEUE_LIMIT：超出提交返回 None（调用方转 429）。"""
        slow_executor_calls = {"active": 0, "max_active": 0}

        def slow_exec(_state, _params):
            slow_executor_calls["active"] += 1
            slow_executor_calls["max_active"] = max(slow_executor_calls["max_active"], slow_executor_calls["active"])
            time.sleep(0.15)
            slow_executor_calls["active"] -= 1
            return 0

        m = RunManager(executor=slow_exec)
        run_ids = [m.submit({"report_type": "basic"}) for _ in range(_QUEUE_LIMIT)]
        assert all(run_ids)  # 前 _QUEUE_LIMIT 个都入队成功

        overflow = m.submit({"report_type": "basic"})
        assert overflow is None  # 队列已满

        for rid in run_ids:
            assert _wait_done(m, rid).status == "done"
        # 单 worker：任何时刻最多 1 个活跃执行
        assert slow_executor_calls["max_active"] == 1


class TestRetention:
    """run 记录保留上限。"""

    def test_retention_trim_oldest(self, monkeypatch):
        """超出 _RUN_KEEP：清理最旧已完成 run。

        放大 _QUEUE_LIMIT 避免队列容量先于保留上限触发（submit 返回 None）。
        trim 在 submit 时对已完成 run 即时清理，故已提交的早期 run 可能已被
        淘汰（get 返回 None 属正常）——等待队列清空后仅校验保留上限。
        """
        import src.python.web.runs as runs_mod

        monkeypatch.setattr(runs_mod, "_QUEUE_LIMIT", _RUN_KEEP + 10)
        m = RunManager(executor=_make_executor(0))
        run_ids = [m.submit({"report_type": "basic"}) for _ in range(_RUN_KEEP + 5)]
        assert all(run_ids)  # 队列放大后全部入队成功

        # 等待所有已提交 run 执行完毕（提交瞬间即 trim，早期 run 可能已淘汰）
        deadline = time.time() + 5.0
        while time.time() < deadline:
            remaining = [r for r in m.list_runs(limit=1000) if r.status in ("queued", "running")]
            if not remaining:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("worker 队列未在 5s 内清空")

        assert len(m.list_runs(limit=1000)) <= _RUN_KEEP
        # 保留上限内应保留最新 run（淘汰最旧）
        states = m.list_runs(limit=1000)
        assert states[0].run_id in run_ids


class TestSingletonReset:
    """模块级单例与 autouse 重置语义。"""

    def test_singleton_recreated_after_reset(self):
        """reset_run_manager() 后 get_run_manager() 返回全新空实例。"""
        m1 = get_run_manager()
        m1.submit({"report_type": "basic"})
        reset_run_manager()
        m2 = get_run_manager()
        assert m2 is not m1
        assert len(m2.list_runs()) == 0

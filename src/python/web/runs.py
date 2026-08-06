"""Web 运行任务管理 — 单 worker 串行队列 + run 状态/事件注册表。

管线本身同步阻塞（无内建队列/asyncio），Web 层用 RunManager 维护
**单 worker 串行队列**：同一时刻仅执行一个生成任务，后续任务排队等待
（消除并发产物覆盖竞态）。每个 run 在出队执行时取一次 ``get_config()``
快照，run 期间不受外部配置修改影响。

数据边界（架构约束「渲染期数据不可写模块级全局」符合性）：
  本模块的 run 注册表属**运行态任务管理**（与 ``get_tracker()`` 同类），
  报告渲染数据仍经 ProgressReporter / template context 传递，不落入
  run 注册表。

生命周期（MVP 权衡）：
  - run 状态/事件为**内存态**，服务重启即丢（进行中 run）；历史记录页
    数据源 = ``core.perf.load_history()``（管线自动落盘的 perf 快照）。
  - 队列容量上限 ``_QUEUE_LIMIT``（含运行中），超出提交返回 None（429）。
  - run 记录（含事件）保留最近 ``_RUN_KEEP`` 个，超出清理最旧。
  - 事件缓冲每 run 上限 ``_EVENT_LIMIT`` 条（滚动丢弃最旧）。
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import deque
from typing import Callable

logger = logging.getLogger("invest")

# 队列容量（含运行中）上限，超出提交返回 None（前端收到 429）
_QUEUE_LIMIT = 3
# run 记录（含事件）保留上限，超出清理最旧（防服务长跑内存膨胀）
_RUN_KEEP = 20
# 事件缓冲每 run 上限（滚动丢弃最旧，防内存膨胀）
_EVENT_LIMIT = 500


class RunState:
    """单个 run 的运行时状态（内存态，不持久化）。

    Attributes:
        run_id: 唯一标识（secrets.token_urlsafe 生成，不可预测）
        params: 出队时使用的参数快照（file_id/report_type/fetch_history/force_llm）
        status: queued / running / done / failed
        exit_code: 管线 ReportResult.exit_code（0/1/2），None=未完成
        errors: 非致命错误列表（对应管线 reporter.get_errors()）
        output_dir: 出队时配置快照的 output_dir（产物定位基准，run 期间不变）
        _events: deque[(seq, level, msg, phase)]，seq 单调递增
    """

    def __init__(self, run_id: str, params: dict) -> None:
        self.run_id = run_id
        self.params = dict(params)
        self.status = "queued"
        self.exit_code: int | None = None
        self.errors: list[str] = []
        self.output_dir: str | None = None
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self._events: deque[tuple[int, str, str, str]] = deque()
        self._seq = 0

    def push_event(self, level: str, msg: str, phase: str = "") -> int:
        """追加一条进度事件，返回该事件序号（seq 单调递增）。

        超出 ``_EVENT_LIMIT`` 时滚动丢弃最旧事件。
        """
        self._seq += 1
        seq = self._seq
        self._events.append((seq, level, msg, phase))
        if len(self._events) > _EVENT_LIMIT:
            self._events.popleft()
        return seq

    def events_after(self, after: int) -> list[dict]:
        """返回序号 > ``after`` 的增量事件列表（轮询增量通道）。

        Args:
            after: 前端最后已读序号（0 = 全量）
        """
        return [
            {"seq": s, "level": level, "message": msg, "phase": phase}
            for s, level, msg, phase in self._events
            if s > after
        ]

    def snapshot(self) -> dict:
        """返回 run 状态快照（不含事件，供 /api/runs/{id}）。"""
        return {
            "run_id": self.run_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "errors": list(self.errors),
            "params": dict(self.params),
            "output_dir": self.output_dir,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class RunManager:
    """单 worker 串行任务队列。

    ``executor`` 为任务执行体 ``(run_state, params) -> exit_code``，由
    app 工厂注入（默认绑定 ``handlers._run_generation``）；worker 线程
    出队逐个执行，异常兜底为 run failed 状态 + 日志（不崩溃服务）。
    """

    def __init__(self, executor: Callable | None = None) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, RunState] = {}
        self._queue: deque[str] = deque()
        self._worker: threading.Thread | None = None
        self._executor = executor

    # ── executor 注入 ──
    @property
    def executor(self) -> Callable | None:
        return self._executor

    @executor.setter
    def executor(self, fn: Callable | None) -> None:
        self._executor = fn

    # ── 队列操作 ──
    def submit(self, params: dict) -> str | None:
        """提交一个生成任务到队列。

        Args:
            params: 任务参数（file_id/report_type/fetch_history/force_llm）

        Returns:
            run_id（成功）；队列已满返回 None（调用方返回 429）
        """
        run_id = secrets.token_urlsafe(8)
        state = RunState(run_id, params)
        with self._lock:
            active = sum(1 for r in self._runs.values() if r.status in ("queued", "running"))
            if active >= _QUEUE_LIMIT:
                return None
            self._runs[run_id] = state
            self._queue.append(run_id)
            self._trim_runs()
        self._ensure_worker()
        return run_id

    def get(self, run_id: str) -> RunState | None:
        """按 run_id 获取 run 状态；不存在返回 None。"""
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, limit: int = 10) -> list[RunState]:
        """返回最近 run 列表（按创建时间倒序）。"""
        with self._lock:
            runs = list(self._runs.values())
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit]

    def _dequeue(self) -> str | None:
        """出队下一个 run_id；队列为空返回 None（worker 退出）。"""
        with self._lock:
            while self._queue:
                run_id = self._queue.popleft()
                if run_id in self._runs:
                    return run_id
            return None

    def _ensure_worker(self) -> None:
        """确保有 worker 线程存活（单 worker；前序 worker 退出后重启）。"""
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            worker = threading.Thread(target=self._work_loop, name="web_run", daemon=True)
            worker.start()
            self._worker = worker

    def _work_loop(self) -> None:
        """worker 主循环：串行出队执行，队列为空即退出。"""
        while True:
            run_id = self._dequeue()
            if run_id is None:
                return
            state = self._runs.get(run_id)
            if state is None:
                continue
            state.status = "running"
            state.started_at = time.time()
            try:
                if self._executor is None:
                    raise RuntimeError("任务执行器未注入（executor 为空）")
                state.exit_code = self._executor(state, state.params)
                state.status = "done"
            except Exception:
                logger.exception("[web-run] run %s 执行异常", run_id)
                state.status = "failed"
                if "任务执行异常（详情请查看日志）" not in state.errors:
                    state.errors.append("任务执行异常（详情请查看日志）")
            finally:
                state.finished_at = time.time()
                # run 完成时同步触发保留上限清理（submit 时多数 run 未完成，
                # 仅靠 submit 时 trim 会漏掉后来完成的 run）
                with self._lock:
                    self._trim_runs()

    def _trim_runs(self) -> None:
        """run 记录超出 _RUN_KEEP 时清理最旧的已完成 run。"""
        if len(self._runs) <= _RUN_KEEP:
            return
        done = [r for r in self._runs.values() if r.status in ("done", "failed")]
        done.sort(key=lambda r: r.finished_at or 0)
        for r in done[: len(self._runs) - _RUN_KEEP]:
            self._runs.pop(r.run_id, None)

    def reset(self) -> None:
        """清空注册表与队列（测试隔离用）。"""
        with self._lock:
            self._runs.clear()
            self._queue.clear()
            self._worker = None


# ── 模块级单例（对齐 provider_registry / data_status 的 get_* 模式）──

_manager: RunManager | None = None
_manager_lock = threading.Lock()


def get_run_manager() -> RunManager:
    """返回全局单例 RunManager（惰性创建）。"""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = RunManager()
    return _manager


def reset_run_manager() -> None:
    """销毁全局单例，下次 get_run_manager() 重建（测试隔离 autouse 使用）。"""
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.reset()
        _manager = None

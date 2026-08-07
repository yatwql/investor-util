"""Web 进度报告器 — 把管线进度事件写入 run 状态缓冲（内存）。

与 ``report.progress.ProgressReporter`` 接口同构（管线零改动，只注入
reporter 子类）。Web 层把 info/ok/warn/error 事件追加到 RunState 的
事件缓冲，供 ``/api/runs/{id}/events`` 轮询读取。

事件 ``seq`` 用**单调递增整数**（非时间戳），保证测试确定性。
"""

from __future__ import annotations

import logging

from src.python.report.progress import ProgressReporter
from src.python.web.runs import RunState

logger = logging.getLogger("invest")


class WebProgressReporter(ProgressReporter):
    """Web 进度报告器 — 事件写入 RunState 缓冲 + 同步 logger。

    与 TuiProgressReporter 同构：管线只调 info/ok/warn/error/add_error，
    Web 层把事件写入 run 注册表，前端轮询增量读取。不 print
    （日志统一约束）。
    """

    def __init__(self, state: RunState) -> None:
        super().__init__()
        self._state = state

    def _emit(self, level: str, msg: str) -> int:
        return self._state.push_event(level, msg)

    def info(self, msg: str) -> int:
        return self._emit("info", msg)

    def ok(self, msg: str) -> int:
        return self._emit("ok", msg)

    def warn(self, msg: str) -> int:
        return self._emit("warn", msg)

    def error(self, msg: str) -> int:
        return self._emit("error", msg)

    def add_error(self, msg: str) -> None:
        """记录非致命错误：同步进事件缓冲 + run 错误列表 + logger。"""
        self._errors.append(msg)
        self._state.push_event("error", msg)
        self._state.errors.append(msg)
        logger.warning("[web-run %s] 生成异常: %s", self._state.run_id, msg)

    def call_sheet(self, label: str, fn, *args, **kwargs) -> bool:
        """安全调用单页写入函数，事件体现「正在生成X.../X生成完成」。

        对齐 TuiProgressReporter.call_sheet 语义（info 开始 / ok 完成 /
        error 失败），使前端进度事件可观察页签粒度。
        """
        if fn is None:
            self.add_error(f"{label}模块缺失，跳过")
            return False
        self.info(f"正在生成{label}...")
        try:
            with self.timer(label):
                fn(*args, **kwargs)
        except Exception:
            self.add_error(f"{label}生成失败（详情请查看日志）")
            logger.exception("%s写入异常", label)
            return False
        self.ok(f"{label}生成完成")
        return True

    def print_timing_summary(self) -> None:
        """Web 无终端输出；耗时已由 Timer 记录到实例记录，忽略。"""

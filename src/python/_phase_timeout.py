"""阶段超时上下文管理器。"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager

logger = logging.getLogger("invest")


class _PhaseTimeoutState:
    """phase_timeout 的可变状态容器，避免模块级 global 变量。

    通过包装为对象属性访问而非 module-level global 关键字，
    满足 C14 约束。提供 reset() 方法供测试隔离使用。
    """

    def __init__(self) -> None:
        self.timer: threading.Timer | None = None
        self.expired = False
        self.lock = threading.Lock()
        self.name: str = ""

    def reset(self) -> None:
        """仅供测试：清空超时状态。"""
        self.timer = None
        self.expired = False
        self.name = ""


_phase_timeout = _PhaseTimeoutState()


class _PhaseTimeoutContext:
    """超时上下文，供调用方检查超时状态。"""

    def __init__(self, start: float, total: float):
        self._start = start
        self._total = total

    @property
    def expired(self) -> bool:
        with _phase_timeout.lock:
            return _phase_timeout.expired

    @property
    def elapsed(self) -> float:
        return time.time() - self._start

    @property
    def remaining(self) -> float:
        return max(0.0, self._total - self.elapsed)

    def check(self) -> None:
        """检查超时，超时时抛出 TimeoutError。"""
        if self.expired:
            raise TimeoutError(f"数据获取阶段超时（{self._total:.0f}s）")


@contextmanager
def phase_timeout(seconds: float, phase_name: str = "data_fetch"):
    """数据获取阶段全局超时上下文管理器。

    超时后已获取的数据保留，未完成的以占位处理。
    超时不影晌正在运行的 HTTP 线程（Python 无法 kill 线程），但结果被丢弃。

    不支持嵌套——检测到嵌套时抛出 RuntimeError。

    Args:
        seconds: 超时秒数
        phase_name: 阶段名称（日志用）

    Yields:
        _PhaseTimeoutContext 实例，供调用方检查过期/剩余时间
    """
    if _phase_timeout.timer is not None:
        raise RuntimeError(
            f"phase_timeout 不支持嵌套：已有 '{_phase_timeout.name}' 在运行，不能开启 '{phase_name}'"
        )

    start = time.time()
    _phase_timeout.expired = False
    _phase_timeout.name = phase_name

    def _expire():
        with _phase_timeout.lock:
            _phase_timeout.expired = True
        logger.warning(
            "[phase_timeout] %s 超时（%.0fs），继续使用已获取数据",
            phase_name,
            seconds,
        )

    timer = threading.Timer(seconds, _expire)
    timer.daemon = True
    timer.start()
    _phase_timeout.timer = timer

    try:
        yield _PhaseTimeoutContext(start, seconds)
    finally:
        timer.cancel()
        with _phase_timeout.lock:
            _phase_timeout.expired = False
        _phase_timeout.timer = None
        _phase_timeout.name = ""

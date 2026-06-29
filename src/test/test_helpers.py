"""测试辅助工具。

集中存放测试中可复用的 mock/helper，避免各测试文件重复定义。
"""
from __future__ import annotations

from concurrent.futures import Future


class SynchronousExecutor:
    """同步执行器 — ThreadPoolExecutor 的测试替身。

    用当前线程同步执行 submit 的任务，返回已完成的 Future。
    避免 mock-heavy 测试中 ThreadPoolExecutor 的线程创建开销。
    """

    def __init__(self, max_workers: int = 1) -> None:
        self._max_workers = max_workers

    def submit(self, fn, /, *args, **kwargs) -> Future:
        fut: Future = Future()
        try:
            result = fn(*args, **kwargs)
            fut.set_result(result)
        except BaseException as e:
            fut.set_exception(e)
        return fut

    def __enter__(self) -> SynchronousExecutor:
        return self

    def __exit__(self, *args) -> None:
        pass

    def shutdown(self, wait: bool = True) -> None:
        pass

"""测试辅助工具。

集中存放测试中可复用的 mock/helper，避免各测试文件重复定义。
"""

from __future__ import annotations

from concurrent.futures import Future
from datetime import date

_QUARTER_END_MMDD = ("03-31", "06-30", "09-30", "12-31")


def recent_holdings_period(today: date | None = None) -> str:
    """返回相对当天「新鲜」的持仓报告期（最近一个完整季末，YYYY-MM-DD）。

    用于 mock 基金持仓数据的 ``date`` 字段。写死绝对日期会让这类测试随时间
    推移被报告期时效闸门判为陈旧而失败——相对当天生成则恒定落在新鲜区间。
    """
    day = today or date.today()
    quarter = (day.month - 1) // 3
    if quarter == 0:
        return f"{day.year - 1}-12-31"
    return f"{day.year}-{_QUARTER_END_MMDD[quarter - 1]}"


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

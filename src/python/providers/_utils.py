"""提供商模块共享工具函数。

包含跨多个新闻/数据 API 提供商模块共用的辅助函数。
"""

from __future__ import annotations

import logging

from src.python.core.constants import BEIJING_TZ
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from typing import Any, Callable

from src.python.core.num_utils import safe_num

logger = logging.getLogger("invest")


def run_with_timeout(fn: Callable[[], Any], timeout: float = 15.0, retries: int = 1) -> Any:
    """在线程中执行函数，超时或异常时重试，全部失败返回 None。

    供 akshare 等**同步且无超时参数**的第三方取数函数使用：在独立线程中执行
    并设上限，避免单个调用挂死整条报告链路。

    Args:
        fn: 要执行的函数（无参，调用方用闭包传入参数）
        timeout: 每次调用的超时秒数
        retries: 失败后的重试次数（默认 1 次）

    Returns:
        函数返回值；每次均超时/异常时返回 None
    """
    for attempt in range(1 + retries):
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(fn)
            try:
                return fut.result(timeout=timeout)
            except TimeoutError:
                logger.warning("akshare 调用超时 (%.1fs, 第 %d/%d 次)", timeout, attempt + 1, 1 + retries)
                fut.cancel()
                if attempt < retries:
                    import time as _time

                    _time.sleep(1)
                continue
            except Exception as e:
                logger.warning("akshare 调用异常 (第 %d/%d 次): %s", attempt + 1, 1 + retries, e)
                fut.cancel()
                if attempt < retries:
                    import time as _time

                    _time.sleep(1)
                continue
        finally:
            pool.shutdown(wait=False)
    return None


def ts_to_str(ts: int) -> str:
    """将 Unix 时间戳（秒）转换为北京时间的格式化日期字符串。

    Args:
        ts: Unix 时间戳（秒）

    Returns:
        "YYYY-MM-DD HH:MM" 格式的字符串，转换失败返回 ""
    """
    try:
        bj_tz = BEIJING_TZ
        dt = datetime.fromtimestamp(ts, tz=bj_tz)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return ""


def safe_float(s: Any) -> float:
    """安全地将输入转换为浮点数。

    转换失败返回 0.0。NaN/±inf 一并归一为 0.0——它们不抛异常、能一路
    穿透到市值/收益聚合链污染聚合结果，故必须在此显式拦下，而非依赖
    后续调用方逐处判空。

    Args:
        s: 输入值

    Returns:
        有限的 float，转换失败返回 0.0
    """
    result = safe_num(s, default=0.0)
    return float(result)  # type: ignore[arg-type]

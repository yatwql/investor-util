"""提供商模块共享工具函数。

包含跨多个新闻/数据 API 提供商模块共用的辅助函数。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def ts_to_str(ts: int) -> str:
    """将 Unix 时间戳（秒）转换为北京时间的格式化日期字符串。

    Args:
        ts: Unix 时间戳（秒）

    Returns:
        "YYYY-MM-DD HH:MM" 格式的字符串，转换失败返回 ""
    """
    try:
        bj_tz = timezone(timedelta(hours=8))
        dt = datetime.fromtimestamp(ts, tz=bj_tz)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return ""


def safe_float(s: Any) -> float:
    """安全地将输入转换为浮点数。

    Args:
        s: 输入值

    Returns:
        浮点数，转换失败返回 0.0
    """
    try:
        return float(s) if s is not None else 0.0
    except (ValueError, TypeError):
        return 0.0

"""回撤历史分位预警 — 滚动窗口和全历史窗口的百分比排行预警。

滚动 1 年（252 日）窗口每品种近 252 日滚动最大回撤 + 当前分位数，
扩展到全历史窗口（1 年 / 3 年 / 全历史），多时间尺度预警。

消费 portfolio_history 已计算的 bars 数据（每日期含 drawdown_pct），
不依赖原始 K 线，纯数学计算。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("invest")

__all__ = [
    "compute_drawdown_warning",
    "rolling_max_drawdown",
    "current_drawdown_percentile",
]

_WINDOWS: dict[str, int] = {
    "短期（1年）": 252,
    "中期（3年）": 756,
}

_DRAW_WARNING_THRESHOLD = 0.80
"""当当前回撤超过历史 80% 分位时触发预警。"""

_DRAW_CRITICAL_THRESHOLD = 0.95
"""当当前回撤超过历史 95% 分位时触发严重预警。"""


def rolling_max_drawdown(drawdown_pct_series: list[float], window: int) -> list[float]:
    """计算滚动窗口内的最大回撤。

    Args:
        drawdown_pct_series: 每日回撤百分比序列（负值，如 -0.05 = -5%）
        window: 滚动窗口大小（日）

    Returns:
        每个日期对应的近 window 日最大回撤（最负值，如 -0.15 = -15%）。
        长度与输入一致，前 window-1 个值填充为 None。
    """
    if not drawdown_pct_series:
        return []

    result: list[float] = []
    for i in range(len(drawdown_pct_series)):
        start = max(0, i - window + 1)
        segment = drawdown_pct_series[start : i + 1]
        if not segment:
            result.append(0.0)
        else:
            # 回撤是负值，max_drawdown 取最负值（最小值）
            result.append(min(segment))
    return result


def current_drawdown_percentile(
    drawdown_pct_series: list[float],
    current_drawdown: float | None = None,
) -> dict[str, float]:
    """计算当前回撤在历史中的分位位置。

    Args:
        drawdown_pct_series: 每日回撤百分比序列
        current_drawdown: 当前回撤值，None 时使用序列最后一个值

    Returns:
        {
            "current_drawdown": float,     # 当前回撤值
            "min_drawdown": float,         # 历史最大回撤（最负值）
            "percentile_50": float,        # 50% 分位
            "percentile_80": float,        # 80% 分位（预警线）
            "percentile_95": float,        # 95% 分位（严重预警线）
            "current_percentile": float,   # 当前回撤在历史中的分位（0~1）
            "below_warning": bool,         # 是否低于预警线
            "below_critical": bool,        # 是否低于严重预警线
        }
    """
    if not drawdown_pct_series:
        return {
            "current_drawdown": 0.0,
            "min_drawdown": 0.0,
            "percentile_50": 0.0,
            "percentile_80": 0.0,
            "percentile_95": 0.0,
            "current_percentile": 0.0,
            "below_warning": False,
            "below_critical": False,
        }

    sorted_dd = sorted(drawdown_pct_series)
    n = len(sorted_dd)
    current = current_drawdown if current_drawdown is not None else drawdown_pct_series[-1]

    def percentile_value(p: float) -> float:
        idx = int(n * p)
        idx = max(0, min(n - 1, idx))
        return sorted_dd[idx]

    # 计算当前值在历史中的分位（低于当前值的比例）
    count_below = sum(1 for v in drawdown_pct_series if v <= current)
    current_pct = count_below / n if n > 0 else 0.0

    p50 = percentile_value(0.50)
    p80 = percentile_value(0.80)
    p95 = percentile_value(0.95)

    return {
        "current_drawdown": round(current, 4),
        "min_drawdown": round(sorted_dd[0], 4),
        "percentile_50": round(p50, 4),
        "percentile_80": round(p80, 4),
        "percentile_95": round(p95, 4),
        "current_percentile": round(current_pct, 4),
        "below_warning": current_pct >= _DRAW_WARNING_THRESHOLD,
        "below_critical": current_pct >= _DRAW_CRITICAL_THRESHOLD,
    }


def compute_drawdown_warning(
    bars: list[dict[str, Any]],
    name: str = "组合",
) -> dict[str, Any]:
    """计算组合的完整回撤预警分析。

    覆盖滚动 1 年 + 多窗口全历史。
    每品种预警结果可调用品种级函数。

    Args:
        bars: 组合/品种的历史走势数据，每项含 "date"、"drawdown_pct" 键
        name: 组合/品种名称（用于结果标记）

    Returns:
        {
            "name": str,
            "current_drawdown": float,
            "max_drawdown": float,
            "windows": {                   # 滚动窗口分析
                "短期（1年）": { rolling_dd, current_percentile, below_warning, ... },
                "中期（3年）": { ... },
            },
            "all_time": {                  # 全历史分析
                "current_percentile": float,
                "below_warning": bool,
                "below_critical": bool,
            },
            "alert_level": str,            # "normal" / "warning" / "critical"
        }
    """
    drawdown_series = [
        b.get("drawdown_pct", 0) or 0
        for b in bars
    ]
    if not drawdown_series:
        return {
            "name": name,
            "current_drawdown": 0.0,
            "max_drawdown": 0.0,
            "windows": {},
            "all_time": {},
            "alert_level": "normal",
        }

    current_dd = drawdown_series[-1]

    # 各滚动窗口分析
    windows_result: dict[str, Any] = {}
    for win_label, win_days in _WINDOWS.items():
        rolling = rolling_max_drawdown(drawdown_series, win_days)
        current_rolling = rolling[-1] if rolling else 0.0
        percentile = current_drawdown_percentile(drawdown_series, current_rolling)
        windows_result[win_label] = {
            "window_days": win_days,
            "rolling_max_drawdown": round(current_rolling, 4),
            **percentile,
        }

    # 全历史分析
    all_time = current_drawdown_percentile(drawdown_series, current_dd)

    # 综合预警等级
    any_warning = any(w.get("below_warning", False) for w in windows_result.values())
    any_critical = any(w.get("below_critical", False) for w in windows_result.values())
    if any_critical or all_time.get("below_critical", False):
        alert_level = "critical"
    elif any_warning or all_time.get("below_warning", False):
        alert_level = "warning"
    else:
        alert_level = "normal"

    return {
        "name": name,
        "current_drawdown": round(current_dd, 4),
        "max_drawdown": round(min(drawdown_series), 4) if drawdown_series else 0.0,
        "windows": windows_result,
        "all_time": all_time,
        "alert_level": alert_level,
    }

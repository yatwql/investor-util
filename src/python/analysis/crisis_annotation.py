"""危机区间标注 — 纯计算层（C19 契约数据源）。

职责：基于组合净值时间线（history_data.bars），对预设历史危机区间
（2015 股灾 / 2018 贸易摩擦 / 2020 疫情 / 2022 调整）做区间标注：

- 区间是否落在报告数据窗口内（in_range）
- 区间内最大回撤（interval_drawdown_pct，正数百分比）
- 区间最深日（trough_date）与恢复耗时（recovery_days）

设计要点：
- 危机日期为**静态历史事实表**（不随持仓变化），不拉长 history.lookback_days——
  仅在既有 bars 数据窗口内做重叠裁剪，无任何新增网络请求。
- 纯标准库，无数据获取、无 report/llm 依赖（analysis 层隔离约束）。
- 契约结构见 technical.md 附录 H「危机区间标注契约（crisis_annotation_data）」。

用法：
  >>> from src.python.analysis.crisis_annotation import build_crisis_annotation
  >>> contract = build_crisis_annotation(history_data)
  >>> contract["intervals"][0]["name"]
  '2015 股灾'
"""

from __future__ import annotations

from datetime import date
from typing import Any

# ── 静态危机区间表（历史事实，不随持仓变化） ─────────────────
# 每项：{name, start, end, desc}，日期为 ISO 格式（YYYY-MM-DD）。
CRISIS_INTERVALS: list[dict[str, str]] = [
    {
        "name": "2015 股灾",
        "start": "2015-06-12",
        "end": "2015-09-30",
        "desc": "杠杆牛破裂，上证指数自 5178 点快速回落，连续千股跌停",
    },
    {
        "name": "2018 贸易摩擦",
        "start": "2018-06-19",
        "end": "2019-01-04",
        "desc": "中美贸易摩擦升级，市场风险偏好收缩，上证指数跌破 2500 点",
    },
    {
        "name": "2020 疫情冲击",
        "start": "2020-02-03",
        "end": "2020-03-23",
        "desc": "新冠疫情全球扩散引发流动性危机，全球市场同步重挫",
    },
    {
        "name": "2022 市场调整",
        "start": "2022-01-04",
        "end": "2022-04-27",
        "desc": "美联储激进加息叠加俄乌冲突，成长股大幅回调",
    },
]


def build_crisis_annotation(history_data: dict | None) -> dict[str, Any]:
    """构建危机区间标注契约（C19 `crisis_annotation_data`）。

    Args:
        history_data: 组合历史走势契约 dict（含 bars / data_start / data_end）。
            为 None、status=unavailable 或 bars 为空时返回 available=False 占位。

    Returns:
        契约 dict：
        {
            "available": bool,   # 数据可用（history_data 有可用 bars）
            "intervals": [
                {
                    "name": str,               # 危机名称
                    "start": str,              # 区间起点（ISO 日期）
                    "end": str,                # 区间终点（ISO 日期）
                    "desc": str,               # 危机背景说明
                    "in_range": bool,          # 是否与报告数据窗口重叠
                    "interval_drawdown_pct": float | None,  # 区间最大回撤（正数 %）
                    "trough_date": str | None, # 区间内最深日
                    "recovery_days": int | None,  # 最深日→恢复耗时（天），未恢复为 None
                    "recovered": bool | None,  # 数据窗口内是否已恢复
                },
                ...
            ],
        }
    """
    if not history_data or history_data.get("status") == "unavailable":
        return _unavailable()
    bars = history_data.get("bars") or []
    if not bars:
        return _unavailable()

    data_start = history_data.get("data_start") or bars[0].get("date", "")
    data_end = history_data.get("data_end") or bars[-1].get("date", "")
    window = _parse_window(data_start, data_end)

    intervals: list[dict[str, Any]] = []
    for raw in CRISIS_INTERVALS:
        entry: dict[str, Any] = {
            "name": raw["name"],
            "start": raw["start"],
            "end": raw["end"],
            "desc": raw.get("desc", ""),
            "in_range": False,
            "interval_drawdown_pct": None,
            "trough_date": None,
            "recovery_days": None,
            "recovered": None,
        }
        overlap = _overlap_interval(raw, window)
        if overlap is not None:
            stats = _compute_interval_stats(bars, overlap)
            entry.update(stats)
            entry["in_range"] = True
        intervals.append(entry)

    return {"available": True, "intervals": intervals}


# ── 内部实现 ─────────────────────────────────────────────


def _unavailable() -> dict[str, Any]:
    """数据不可用占位（status=unavailable / 无 bars）。"""
    return {
        "available": False,
        "intervals": [
            {
                "name": raw["name"],
                "start": raw["start"],
                "end": raw["end"],
                "desc": raw.get("desc", ""),
                "in_range": False,
                "interval_drawdown_pct": None,
                "trough_date": None,
                "recovery_days": None,
                "recovered": None,
            }
            for raw in CRISIS_INTERVALS
        ],
    }


def _parse_window(data_start: str, data_end: str) -> tuple[date, date] | None:
    """解析报告数据窗口为 (start, end) date 对；格式异常返回 None。"""
    try:
        return date.fromisoformat(data_start), date.fromisoformat(data_end)
    except (TypeError, ValueError):
        return None


def _overlap_interval(
    raw: dict[str, str],
    window: tuple[date, date] | None,
) -> tuple[date, date] | None:
    """计算危机区间与报告数据窗口的重叠区间。

    Returns:
        (overlap_start, overlap_end) 或 None（区间不重叠 / 日期格式异常）。
    """
    if window is None:
        return None
    w_start, w_end = window
    try:
        i_start = date.fromisoformat(raw["start"])
        i_end = date.fromisoformat(raw["end"])
    except (TypeError, ValueError):
        return None
    overlap_start = max(i_start, w_start)
    overlap_end = min(i_end, w_end)
    if overlap_start > overlap_end:
        return None
    return overlap_start, overlap_end


def _compute_interval_stats(
    bars: list[dict],
    overlap: tuple[date, date],
) -> dict[str, Any]:
    """在重叠区间内计算区间回撤 + 恢复耗时。

    Args:
        bars: [{"date": "YYYY-MM-DD", "total_value": float, ...}, ...] 升序。
        overlap: (start, end) 重叠区间 date 对。

    Returns:
        {interval_drawdown_pct, trough_date, recovery_days, recovered}
    """
    o_start, o_end = overlap
    window_bars: list[dict] = []
    for bar in bars:
        d_str = str(bar.get("date") or "")
        try:
            d = date.fromisoformat(d_str)
        except (TypeError, ValueError):
            continue
        if o_start <= d <= o_end:
            window_bars.append(bar)

    # 无重叠内 bar → 区间统计置空
    if not window_bars:
        return {
            "interval_drawdown_pct": None,
            "trough_date": None,
            "recovery_days": None,
            "recovered": None,
        }

    # 1) 区间最大回撤：窗口内 running peak 的最大 (peak - value)/peak
    running_peak = 0.0
    peak_at_trough = 0.0
    max_dd = 0.0
    trough_date: str | None = None
    for bar in window_bars:
        tv = float(bar.get("total_value") or 0.0)
        d = str(bar.get("date") or "")
        if tv <= 0:
            continue
        if tv > running_peak:
            running_peak = tv
        if running_peak > 0:
            dd = (running_peak - tv) / running_peak
            if dd > max_dd:
                max_dd = dd
                trough_date = d
                peak_at_trough = running_peak

    # 2) 恢复耗时：从最深日向后扫描，首个 total_value >= 峰值 的日期
    recovery_date: str | None = None
    if trough_date is not None and peak_at_trough > 0:
        scanning = False
        for bar in bars:
            d_str = str(bar.get("date") or "")
            if d_str == trough_date:
                scanning = True
                continue
            if scanning:
                tv = float(bar.get("total_value") or 0.0)
                if tv >= peak_at_trough:
                    recovery_date = d_str
                    break

    if recovery_date is None:
        return {
            "interval_drawdown_pct": round(max_dd * 100, 2),
            "trough_date": trough_date,
            "recovery_days": None,
            "recovered": False,
        }

    try:
        recovery_days = (date.fromisoformat(recovery_date) - date.fromisoformat(str(trough_date))).days
    except (TypeError, ValueError):
        recovery_days = None
    return {
        "interval_drawdown_pct": round(max_dd * 100, 2),
        "trough_date": trough_date,
        "recovery_days": recovery_days,
        "recovered": True,
    }

"""回撤事件提取 — 纯计算层。

职责：从组合净值时间线（bars）扫描独立回撤事件（水下区间），输出：
  - drawdown_events：{peak_date, trough_date, recovery_date, drawdown_pct,
                       duration_days, recovery_days, recovered}
  - recovery_times：{start_date, end_date, days}（trough → recovery 恢复耗时）

- 无数据获取、无报告依赖，纯标准库（C8：日志走 logging，不用 print）。
- 算法：跟踪 running peak；跌破前峰进入回撤（水下），回升至前峰恢复；
  连续未恢复区间合并为一个事件（一次水下，一个事件）。
- 过滤：drawdown 深度 < min_depth_pct 的事件剔除；超出 max_events 只保留最深的。
- MIN_SPAN=60：历史 span < 60 交易日判数据不足（§1.4.5，由调用方标记）。
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger("invest")

# 有效历史下限（交易日）：低于此 span 判数据不足（§1.4.5）
MIN_SPAN: int = 60


def _to_date(s: str) -> date:
    """ISO 日期字符串 → date 对象（格式异常时抛 ValueError，由调用方降级）。"""
    return date.fromisoformat(s)


def extract_drawdown_events(
    bars: list[dict],
    min_depth_pct: float = 5.0,
    max_events: int = 5,
) -> list[dict]:
    """从组合时间线提取独立回撤事件。

    Args:
        bars: [{"date": "YYYY-MM-DD", "total_value": float, ...}, ...] 按日期升序。
            仅使用 date/total_value 字段。
        min_depth_pct: 最小回撤深度（百分比），低于此深度的事件被剔除。
        max_events: 最多返回的事件数（超出按深度优先保留）。

    Returns:
        list[dict]，按起峰日升序排列：
        {peak_date, trough_date, recovery_date, drawdown_pct,
         duration_days, recovery_days, recovered}
        - drawdown_pct：最大深度（正数，百分比，两位小数）
        - duration_days：起峰日→最深日 日历天数（下跌持续）
        - recovery_days：最深日→恢复日 日历天数（未恢复时为 None）
        - recovered：数据期内是否回到前峰（False 表示仍处于水下）
    """
    if not bars:
        return []

    events: list[dict] = []
    running_peak = 0.0
    peak_date = ""
    underwater: dict | None = None  # 进行中的水下事件
    trough_value = 0.0

    for bar in bars:
        tv = float(bar.get("total_value") or 0.0)
        d = str(bar.get("date") or "")
        if tv <= 0:
            continue

        if tv > running_peak:
            # 创新高：若处于水下，则此日为该事件恢复日
            if underwater is not None:
                underwater["recovery_date"] = d
                underwater["recovered"] = True
                _finalize_event(underwater)
                events.append(underwater)
                underwater = None
            running_peak = tv
            peak_date = d
        else:
            # 低于前峰：进入或延续水下
            if underwater is None:
                underwater = {
                    "peak_date": peak_date or d,
                    "trough_date": d,
                    "recovery_date": "",
                    "drawdown_pct": 0.0,
                    "recovered": False,
                }
                trough_value = tv
            else:
                if tv < trough_value:
                    trough_value = tv
                    underwater["trough_date"] = d
            if running_peak > 0:
                dd_pct = (running_peak - tv) / running_peak * 100.0
                if dd_pct > underwater["drawdown_pct"]:
                    underwater["drawdown_pct"] = dd_pct

    # 数据末尾仍处于水下 → 未恢复事件
    if underwater is not None:
        _finalize_event(underwater)
        events.append(underwater)

    # 深度过滤 + 截断（保留最深的 max_events 个）→ 按起峰日升序
    deep_events = [e for e in events if e["drawdown_pct"] >= min_depth_pct]
    deep_events.sort(key=lambda e: e["drawdown_pct"], reverse=True)
    deep_events = deep_events[:max_events]
    deep_events.sort(key=lambda e: e["peak_date"])
    return deep_events


def _finalize_event(event: dict) -> None:
    """补全事件派生字段（duration_days / recovery_days）。"""
    try:
        peak = _to_date(event["peak_date"])
        trough = _to_date(event["trough_date"])
        event["duration_days"] = (trough - peak).days
    except (ValueError, TypeError):
        event["duration_days"] = 0
    if event.get("recovered") and event.get("recovery_date"):
        try:
            event["recovery_days"] = (_to_date(event["recovery_date"]) - trough).days
        except (ValueError, TypeError):
            event["recovery_days"] = None
    else:
        event["recovery_days"] = None
    event["drawdown_pct"] = round(event["drawdown_pct"], 2)


def compute_recovery_times(events: list[dict]) -> list[dict]:
    """计算已恢复事件的恢复耗时明细（trough → recovery）。

    Args:
        events: extract_drawdown_events 输出。

    Returns:
        list[dict]：{start_date, end_date, days}，仅含 recovered=True 的事件，
        按 start_date 升序。
    """
    out: list[dict] = []
    for e in events:
        if not e.get("recovered"):
            continue
        start = e.get("trough_date", "")
        end = e.get("recovery_date", "")
        days = e.get("recovery_days")
        out.append({"start_date": start, "end_date": end, "days": days})
    out.sort(key=lambda r: (r["start_date"] or ""))
    return out

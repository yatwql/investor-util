"""月度收益日历 — 组合日频序列的按月收益聚合（纯计算，无 I/O）。

口径（caliber，双口径并排预留）：

  - ``as-if``（当前实现）：假设当前持仓份额在过去 N 天不变（与组合历史走势
    同源语义），月度收益 = 月末总市值 / 上月末总市值 − 1；
  - ``realized``（预留）：按成交回放的实际持仓逐月计算——待完整交易回放数据
    （24~36 个月成交流水）就绪后接入；渲染层按 ``caliber`` 并排展示两组。

窗口与边界：

  - 默认取最近 ``DEFAULT_WINDOW_MONTHS`` 个月；首窗月仍以上窗真实月末为基线
    （截窗不改变收益口径）；
  - 最早月无上月基线时以其首根 bar 为基线，``baseline="inception"``；
  - 样本 < 2 个不同日期（单日无收益语义）→ ``available=False``；
  - ``|收益| < FLAT_EPSILON_PCT``（百分点）计为平月，展示四舍五入为 0.00%。
"""

from __future__ import annotations

from typing import Any

CALIBER_AS_IF = "as-if"
#: 预留口径：成交回放数据就绪后接入（结构与标签先行，渲染按 caliber 并排）
CALIBER_REALIZED = "realized"

CALIBER_LABELS: dict[str, str] = {
    CALIBER_AS_IF: "as-if（当前持仓份额回溯）",
    CALIBER_REALIZED: "实际成交回放",
}

DEFAULT_WINDOW_MONTHS = 24
#: 月收益绝对值小于此（百分点）计为平月（display 两位小数恰为 0.00）
FLAT_EPSILON_PCT = 0.005


def _unavailable(caliber: str, window_months: int) -> dict[str, Any]:
    """不可用形态（样本不足/输入为空），键集与可用形态一致。"""
    return {
        "available": False,
        "caliber": caliber,
        "caliber_label": CALIBER_LABELS.get(caliber, caliber),
        "window_months": window_months,
        "months_total": 0,
        "years": [],
        "stats": None,
    }


def aggregate_monthly_returns(
    bars: list[dict[str, Any]],
    *,
    window_months: int = DEFAULT_WINDOW_MONTHS,
    caliber: str = CALIBER_AS_IF,
) -> dict[str, Any]:
    """按月聚合日频 bars 为月度收益日历数据契约（见模块 docstring）。

    Args:
        bars: 升序日频序列 ``[{date: "YYYY-MM-DD", total_value: float}, ...]``。
        window_months: 保留最近 N 个月（≤0 表示不截窗）。
        caliber: 口径标识（``CALIBER_*``）。

    Returns:
        ``{"available": bool, "caliber", "caliber_label", "window_months",
        "months_total", "years": [{"year", "cells": [{"month", "key",
        "return_pct", "baseline"} × 12]}], "stats"}``；
        ``return_pct`` 为百分数（2.15 = +2.15%，HTML ``change`` 滤镜直读，
        Excel 端写入时 ÷100 配 FMT_PERCENT）；不可用时 ``years=[]``、``stats=None``。
    """
    month_end: dict[tuple[int, int], tuple[str, float]] = {}
    first_value: float | None = None
    sample_dates = 0
    for bar in bars or []:
        date = str(bar.get("date") or "")[:10]
        try:
            value = float(bar.get("total_value"))
        except (TypeError, ValueError):
            continue
        if len(date) != 10 or date[4] != "-" or date[7] != "-" or value <= 0:
            continue
        sample_dates += 1
        ym = (int(date[:4]), int(date[5:7]))
        month_end[ym] = (date, value)  # 升序输入，后写即月末
        if first_value is None:
            first_value = value
    if sample_dates < 2 or not month_end or first_value is None:
        return _unavailable(caliber, window_months)

    ordered = sorted(month_end)
    window = ordered[-window_months:] if window_months and window_months > 0 else ordered
    position = {ym: i for i, ym in enumerate(ordered)}

    entries: list[tuple[tuple[int, int], float | None, str]] = []
    for ym in window:
        _date, value = month_end[ym]
        idx = position[ym]
        if idx == 0:
            base_value, baseline = first_value, "inception"
        else:
            base_value, baseline = month_end[ordered[idx - 1]][1], "prev_month"
        ret = (value / base_value - 1.0) * 100.0 if base_value > 0 else None
        entries.append((ym, ret, baseline))

    years: list[dict[str, Any]] = []
    for year in sorted({ym[0] for ym in window}):
        by_month = {ym[1]: (ret, baseline) for ym, ret, baseline in entries if ym[0] == year}
        cells = []
        for month in range(1, 13):
            ret, baseline = by_month.get(month, (None, None))
            cells.append(
                {
                    "month": month,
                    "key": f"{year:04d}-{month:02d}",
                    "return_pct": round(ret, 4) if ret is not None else None,
                    "baseline": baseline,
                }
            )
        years.append({"year": year, "cells": cells})

    valued = [(ym, ret) for ym, ret, _ in entries if ret is not None]
    if not valued:
        return _unavailable(caliber, window_months)
    up = [(ym, v) for ym, v in valued if v > FLAT_EPSILON_PCT]
    down = [(ym, v) for ym, v in valued if v < -FLAT_EPSILON_PCT]
    flat = len(valued) - len(up) - len(down)
    best_ym, best = max(valued, key=lambda kv: kv[1])
    worst_ym, worst = min(valued, key=lambda kv: kv[1])

    # 最长连亏（按月序，平月打断连续）
    streak = 0
    best_streak = 0
    streak_end: str | None = None
    best_streak_end: str | None = None
    for ym, ret, _ in entries:
        if ret is not None and ret < -FLAT_EPSILON_PCT:
            streak += 1
            streak_end = f"{ym[0]:04d}-{ym[1]:02d}"
            if streak > best_streak:
                best_streak, best_streak_end = streak, streak_end
        else:
            streak = 0
            streak_end = None

    def _cell(ym: tuple[int, int], value: float) -> dict[str, Any]:
        return {"key": f"{ym[0]:04d}-{ym[1]:02d}", "return_pct": round(value, 4)}

    return {
        "available": True,
        "caliber": caliber,
        "caliber_label": CALIBER_LABELS.get(caliber, caliber),
        "window_months": window_months,
        "months_total": len(valued),
        "years": years,
        "stats": {
            "up": len(up),
            "down": len(down),
            "flat": flat,
            "best": _cell(best_ym, best),
            "worst": _cell(worst_ym, worst),
            "max_down_streak": {"end_key": best_streak_end, "length": best_streak},
        },
    }

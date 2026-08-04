"""尾部风险统计 — 纯计算层。

职责：从组合净值时间线（bars）计算尾部风险指标，输出：
  - var95 / var99：历史模拟法 VaR（单日损失幅度，正数百分比）
  - max_single_day_drop：最大单日跌幅（正数百分比）及发生日期
  - consecutive_down_days：最长连续下跌天数及区间
  - recovery_days_after_drop：最大单日跌幅后收复跌幅所需交易日

- 无数据获取、无报告依赖，纯标准库（日志走 logging，不用 print）。
- 复用历史日收益序列（与 report/portfolio_history._compute_daily_returns 同口径：
  日收益 = (curr - prev) / prev，小数单位，如 0.01 = 1%），不额外拉长 lookback。
- 样本不足（< MIN_SAMPLE 个日收益）判数据不足（§1.4.5），available=False，
  各指标置 None，由调用方写占位符。
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("invest")

# 有效日收益样本下限：低于此数判数据不足（§1.4.5 数据降级）
MIN_SAMPLE: int = 20


def compute_tail_risk(bars: list[dict] | None) -> dict:
    """计算组合尾部风险指标。

    Args:
        bars: [{"date": "YYYY-MM-DD", "total_value": float, ...}, ...] 按日期升序。
            仅使用 date/total_value 字段。None/空列表返回 available=False 占位。

    Returns:
        tail_risk_data 契约 dict：
        {
          "available": bool,                  # 样本是否充足（>= MIN_SAMPLE）
          "sample_size": int,                 # 参与计算的日收益样本数
          "var95": float | None,              # VaR(95) 单日损失幅度（正数%）
          "var99": float | None,              # VaR(99) 单日损失幅度（正数%）
          "max_single_day_drop": float | None,        # 最大单日跌幅（正数%）
          "max_single_day_drop_date": str | None,     # 最大单日跌幅发生日期
          "consecutive_down_days": int | None,        # 最长连续下跌天数
          "consecutive_down_start": str | None,       # 连续下跌区间起点日期
          "consecutive_down_end": str | None,         # 连续下跌区间终点日期
          "recovery_days_after_drop": int | None,     # 最大跌幅后恢复所需交易日（未恢复 None）
          "recovery_state": str | None,   # "recovered" | "unrecovered" | "none"
          "warnings": list[str],
        }
    """
    if not bars:
        logger.warning("尾部风险：无历史 bars，返回数据不足占位")
        return _unavailable(0)

    returns = _compute_daily_returns(bars)
    sample_size = len(returns)
    if sample_size < MIN_SAMPLE:
        logger.warning(
            "尾部风险：日收益样本 %d < 下限 %d，数据不足",
            sample_size,
            MIN_SAMPLE,
        )
        return _unavailable(sample_size)

    var95 = _compute_var(returns, 0.95)
    var99 = _compute_var(returns, 0.99)
    max_drop, max_drop_idx = _max_single_day_drop(returns)
    down_days, down_start_idx, down_end_idx = _max_consecutive_down(returns)
    recovery_days, recovery_state = _recovery_after_drop(bars, max_drop_idx)

    max_drop_date = _bar_date_at(bars, max_drop_idx + 1)
    down_start_date = _bar_date_at(bars, down_start_idx + 1) if down_days > 0 else None
    down_end_date = _bar_date_at(bars, down_end_idx + 1) if down_days > 0 else None

    return {
        "available": True,
        "sample_size": sample_size,
        "var95": round(var95, 2),
        "var99": round(var99, 2),
        "max_single_day_drop": round(max_drop, 2),
        "max_single_day_drop_date": max_drop_date,
        "consecutive_down_days": down_days,
        "consecutive_down_start": down_start_date,
        "consecutive_down_end": down_end_date,
        "recovery_days_after_drop": recovery_days,
        "recovery_state": recovery_state,
        "warnings": [],
    }


def _unavailable(sample_size: int) -> dict:
    """样本不足占位（§1.4.5 数据降级）。"""
    return {
        "available": False,
        "sample_size": sample_size,
        "var95": None,
        "var99": None,
        "max_single_day_drop": None,
        "max_single_day_drop_date": None,
        "consecutive_down_days": None,
        "consecutive_down_start": None,
        "consecutive_down_end": None,
        "recovery_days_after_drop": None,
        "recovery_state": None,
        "warnings": ["日收益样本不足，尾部风险指标不可用"],
    }


def _compute_daily_returns(bars: list[dict]) -> list[float]:
    """bars → 日收益率序列（小数，0.01 = 1%）。

    与 report/portfolio_history._compute_daily_returns 同口径：prev 市值 > 0 才计入，
    序号 i 对应 bars[i+1]（即收益在 bars[i+1]["date"] 实现）。
    """
    returns: list[float] = []
    for i in range(1, len(bars)):
        prev = float(bars[i - 1].get("total_value") or 0.0)
        curr = float(bars[i].get("total_value") or 0.0)
        # 首尾任一 ≤0（缺失/占位/清仓）都不构成有效收益，跳过（避免伪 -100% 单日）
        if prev > 0 and curr > 0:
            returns.append((curr - prev) / prev)
    return returns


def _compute_var(returns: list[float], level: float) -> float:
    """历史模拟法 VaR：单日损失幅度（正数百分比，0 表示该分位无损失）。

    Args:
        returns: 日收益率序列（小数）。
        level: 置信度（0.95 / 0.99）。

    实现：日收益升序排序，取 (1-level) 分位损失。样本全为正收益时该分位
    收益 ≥ 0，返回 0（无损失）。
    """
    sorted_returns = sorted(returns)
    n = len(sorted_returns)
    k = int(math.ceil((1.0 - level) * n)) - 1
    k = max(0, min(k, n - 1))
    var_loss = -sorted_returns[k] * 100.0
    return max(0.0, var_loss)


def _max_single_day_drop(returns: list[float]) -> tuple[float, int]:
    """最大单日跌幅（正数百分比）及其在收益序列中的索引（取第一个最深日）。

    全为正收益/持平（无下跌日）→ (0.0, -1)，调用方据此判恢复状态 none。
    """
    if not returns:
        return 0.0, -1
    min_return = min(returns)
    if min_return >= 0:
        return 0.0, -1
    idx = returns.index(min_return)
    return -min_return * 100.0, idx


def _max_consecutive_down(returns: list[float]) -> tuple[int, int, int]:
    """最长连续下跌天数及其区间索引（start/end，区间内收益均 < 0）。"""
    best = 0
    best_start = -1
    best_end = -1
    cur = 0
    cur_start = -1
    for i, r in enumerate(returns):
        if r < 0:
            if cur == 0:
                cur_start = i
            cur += 1
            if cur > best:
                best = cur
                best_start = cur_start
                best_end = i
        else:
            cur = 0
    return best, best_start, best_end


def _recovery_after_drop(bars: list[dict], drop_idx: int) -> tuple[int | None, str]:
    """最大单日跌幅后的恢复天数（交易日）。

    Args:
        bars: 组合时间线（含 date/total_value）。
        drop_idx: 日收益序列中最大单日跌幅的索引（对应 bars[drop_idx+1]）。

    Returns:
        (recovery_days, recovery_state)：
        - drop_idx < 0（无下跌日）→ (None, "none")
        - 数据期内收复前日水平 → (j - (drop_idx+1), "recovered")
        - 数据期末未收复 → (None, "unrecovered")
    """
    if drop_idx < 0 or drop_idx + 1 >= len(bars):
        return None, "none"
    pre_drop_value = float(bars[drop_idx].get("total_value") or 0.0)
    if pre_drop_value <= 0:
        return None, "unrecovered"
    for j in range(drop_idx + 2, len(bars)):
        if float(bars[j].get("total_value") or 0.0) >= pre_drop_value:
            return j - (drop_idx + 1), "recovered"
    return None, "unrecovered"


def _bar_date_at(bars: list[dict], index: int) -> str | None:
    """取 bars[index]["date"]（越界返回 None）。"""
    if 0 <= index < len(bars):
        return str(bars[index].get("date") or "")
    return None

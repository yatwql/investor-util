"""调仓 What-if 指定生效日时序回测 — 纯计算模块。

对基准（调仓前）与目标（调仓后）两份持仓，在指定**调仓生效日**之后
的行情窗口内，各自用 as-if 市值（份额 × 每日价格）归一化到 100 基点，
对比区间收益 / 年化收益 / 年化波动率 / 夏普 / 最大回撤。

设计边界：
  - **纯计算**：本模块不联网、不 import report/ 任何模块（analysis 层单向依赖纪律）。
    行情获取与 PortfolioHistoryCalculator 编排在 report/whatif_operations.py 完成，
    本模块仅消费其输出的 bars 列表并计算指标。
  - **opt-in**：仅当指定生效日时才启用时序回测；未指定时主 whatif 维持纯截面比较。
  - **降级**：数据不足 / 无可对齐锚点 / 生效日无效 → available=False，不阻塞主报告。
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from src.python.analysis.metrics import (
    _MIN_SAMPLE_DAYS,
    annualized_return,
    max_drawdown_pct,
    sharpe_ratio,
)
from src.python.analysis.whatif import _arrow

# ── 常量 ────────────────────────────────────────────────

_MIN_BACKTEST_DAYS = 30
"""回测最少请求天数（chain 层历史窗口下限）。"""

_MAX_BACKTEST_DAYS = 365
"""回测最多请求天数（股票/ETF K 线 provider 上限）。"""

_BACKTEST_WARMUP_BARS = 20
"""生效日→今日的自然日折算交易日后的热身缓冲 bar 数。"""

_VAR_EPS = 1e-15
"""方差下界：低于此值视为零波动（与 metrics 模块一致）。"""


# ── days 计算 ──────────────────────────────────────────


def compute_backtest_days(effective_date: str, today: date | None = None) -> int | None:
    """按生效日折算回测行情请求天数。

    自然日 → 交易日（×5/7）折算，加热身缓冲后钳位到 [30, 365]。

    Args:
        effective_date: 调仓生效日（YYYY-MM-DD）
        today: 基准日（测试注入），缺省取当天

    Returns:
        请求天数；格式无效或生效日不早于 today 时返回 None
    """
    try:
        eff = datetime.strptime(effective_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    today = today or date.today()
    if eff >= today:
        return None
    natural = (today - eff).days
    trading = max(1, round(natural * 5 / 7))
    return min(max(trading + _BACKTEST_WARMUP_BARS, _MIN_BACKTEST_DAYS), _MAX_BACKTEST_DAYS)


# ── 序列对齐 ──────────────────────────────────────────


def _locf(dates: list[str], value_map: dict[str, float]) -> list[float | None]:
    """按日期顺序前值填充（Last Observation Carried Forward）。

    某侧在某日无实际值时沿用上一次已知值，避免净值滞后导致曲线断档。

    Args:
        dates: 升序日期列表
        value_map: {date: total_value}

    Returns:
        与 dates 等长的值列表（首值前无已知值时可能为 None）
    """
    vals: list[float | None] = []
    last: float | None = None
    for d in dates:
        if d in value_map:
            last = value_map[d]
        vals.append(last)
    return vals


def _align_series(
    base_bars: list[dict[str, Any]],
    cand_bars: list[dict[str, Any]],
    effective_date: str,
) -> tuple[list[str], list[float], list[float]] | None:
    """对齐两侧 bars 到统一日期轴，丢弃锚点前的日期。

    Args:
        base_bars: 基准 bars（[{date, total_value, ...}]，仅含生效日后）
        cand_bars: 目标 bars（同上）
        effective_date: 调仓生效日（YYYY-MM-DD）

    Returns:
        (labels, base_vals, cand_vals) — 锚点（双方首个都有正值的日期）起的
        对齐序列；无可对齐锚点时返回 None。
    """
    b_map = {b["date"]: b["total_value"] for b in base_bars if b["date"] >= effective_date}
    c_map = {b["date"]: b["total_value"] for b in cand_bars if b["date"] >= effective_date}
    dates = sorted(set(b_map) | set(c_map))
    if not dates:
        return None
    b_vals = _locf(dates, b_map)
    c_vals = _locf(dates, c_map)
    anchor = next(
        (
            i
            for i in range(len(dates))
            if b_vals[i] is not None and c_vals[i] is not None and b_vals[i] > 0 and c_vals[i] > 0
        ),
        None,
    )
    if anchor is None:
        return None
    return dates[anchor:], b_vals[anchor:], c_vals[anchor:]  # type: ignore[return-value]


# ── 序列变换 ──────────────────────────────────────────


def _normalize(vals: list[float], anchor_val: float) -> list[float]:
    """归一化到 100 基点（anchor_val 已由 _align_series 保证 > 0）。"""
    return [round(v / anchor_val * 100, 4) for v in vals]


def _returns_from_values(norm: list[float]) -> list[float]:
    """归一化值序列 → 相邻日收益率序列（小数）。"""
    returns: list[float] = []
    for i in range(1, len(norm)):
        prev = norm[i - 1]
        curr = norm[i]
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _drawdown_series(norm: list[float]) -> list[float]:
    """归一化值序列 → 回撤百分比序列（负值，如 -1.25 表示 -1.25%）。"""
    peak = 0.0
    series: list[float] = []
    for v in norm:
        if v > peak:
            peak = v
        dd = ((v - peak) / peak * 100) if peak > 0 else 0.0
        series.append(round(dd, 4))
    return series


# ── 指标构建 ──────────────────────────────────────────


def _period_return(norm: list[float]) -> float | None:
    """区间收益（%）：末值 / 首值 - 1。"""
    if not norm or norm[0] <= 0:
        return None
    return round((norm[-1] / norm[0] - 1) * 100, 2)


def _annual_return_pct(ret: list[float]) -> float | None:
    """年化收益（%）。"""
    v = annualized_return(ret)
    return round(v * 100, 2) if v is not None else None


def _vol_pct(ret: list[float]) -> float | None:
    """年化波动率（%）：std(ddof=1) × √252。"""
    if len(ret) < 2:
        return None
    mean = sum(ret) / len(ret)
    variance = sum((r - mean) ** 2 for r in ret) / (len(ret) - 1)
    if variance < _VAR_EPS:
        return 0.0
    return round(math.sqrt(variance) * math.sqrt(252) * 100, 2)


def _neg_dd(v: float | None) -> float | None:
    """最大回撤正数幅度 → 负百分比（与 portfolio_history 惯例一致）。"""
    return -round(v * 100, 2) if v is not None else None


def _build_metrics(
    b_ret: list[float],
    c_ret: list[float],
    b_norm: list[float],
    c_norm: list[float],
) -> list[dict[str, Any]]:
    """构建 5 行指标对比（区间收益/年化收益/年化波动率/夏普/最大回撤）。"""
    rows: list[dict[str, Any]] = [
        {
            "key": "period_return_pct",
            "label": "区间收益",
            "unit": "pct",
            "base": _period_return(b_norm),
            "candidate": _period_return(c_norm),
        },
        {
            "key": "annualized_return_pct",
            "label": "年化收益",
            "unit": "pct",
            "base": _annual_return_pct(b_ret),
            "candidate": _annual_return_pct(c_ret),
        },
        {
            "key": "annualized_volatility_pct",
            "label": "年化波动率",
            "unit": "pct",
            "base": _vol_pct(b_ret),
            "candidate": _vol_pct(c_ret),
        },
        {
            "key": "sharpe_ratio",
            "label": "夏普比率",
            "unit": "ratio",
            "base": sharpe_ratio(b_ret),
            "candidate": sharpe_ratio(c_ret),
        },
        {
            "key": "max_drawdown_pct",
            "label": "最大回撤",
            "unit": "pct",
            "base": _neg_dd(max_drawdown_pct(b_ret)),
            "candidate": _neg_dd(max_drawdown_pct(c_ret)),
        },
    ]
    for r in rows:
        b, c = r["base"], r["candidate"]
        if b is not None or c is not None:
            r["delta"] = round((c or 0.0) - (b or 0.0), 2)
        else:
            r["delta"] = None
        r["arrow"] = _arrow(r["delta"] or 0.0)
    return rows


# ── 对外入口 ──────────────────────────────────────────


def compute_backtest_metrics(
    base_bars: list[dict[str, Any]],
    cand_bars: list[dict[str, Any]],
    effective_date: str,
    base_status: str = "ok",
    cand_status: str = "ok",
) -> dict[str, Any]:
    """计算生效日后时序回测指标（纯计算，消费两侧 bars）。

    Args:
        base_bars: 基准组合综合走势 bars（[{date, total_value, ...}]）
        cand_bars: 目标组合综合走势 bars（同上）
        effective_date: 调仓生效日（YYYY-MM-DD）
        base_status: 基准侧 status（"ok"/"degraded"/"unavailable"）
        cand_status: 目标侧 status（同上）

    Returns:
        backtest 契约 dict：
          - available / status("ok"/"degraded"/"unavailable") / reason / effective_date
          - metrics: [{key, label, unit, base, candidate, delta, arrow}]（5 行）
          - series: {labels, base, candidate, base_drawdown, candidate_drawdown}
            净值归一化到 100，回撤为负百分比。
    """
    if not base_bars and not cand_bars:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "两侧持仓均无历史数据",
            "effective_date": effective_date,
        }

    aligned = _align_series(base_bars, cand_bars, effective_date)
    if aligned is None:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "生效日后无可对齐的行情数据",
            "effective_date": effective_date,
        }

    labels, b_vals, c_vals = aligned
    if len(labels) - 1 < _MIN_SAMPLE_DAYS:
        return {
            "available": False,
            "status": "unavailable",
            "reason": f"生效日后的交易日不足 {_MIN_SAMPLE_DAYS} 天（当前 {len(labels) - 1} 天）",
            "effective_date": effective_date,
        }

    b_norm = _normalize(b_vals, b_vals[0])
    c_norm = _normalize(c_vals, c_vals[0])
    b_ret = _returns_from_values(b_norm)
    c_ret = _returns_from_values(c_norm)

    status = "degraded" if (base_status == "degraded" or cand_status == "degraded") else "ok"
    reason = "部分持仓无历史数据，回测基于可用品种" if status == "degraded" else ""

    return {
        "available": True,
        "status": status,
        "reason": reason,
        "effective_date": effective_date,
        "metrics": _build_metrics(b_ret, c_ret, b_norm, c_norm),
        "series": {
            "labels": labels,
            "base": b_norm,
            "candidate": c_norm,
            "base_drawdown": _drawdown_series(b_norm),
            "candidate_drawdown": _drawdown_series(c_norm),
        },
    }

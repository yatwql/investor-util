"""基准指数历史走势获取与归一化。

职责：
  1. 接收 benchmark_indices 配置 {代码: 名称}
  2. 使用 fetch_index_history 并行获取所有指数的历史日线
  3. 返回原始数据字典（fetch_benchmarks）
  4. 归一化到 100 基点，与组合走势对齐（normalize_benchmarks）

数据获取走 fetch_index_history → history_index chain → Provider，不绕过。
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.python.fetcher.index import fetch_index_history

logger = logging.getLogger("invest")


def normalize_benchmarks(
    portfolio_bars: list[dict[str, Any]],
    raw_benchmarks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """归一化基准指数到 100 基点，并与组合走势对齐。

    LOCF 合并 → 起算日对齐 → 归一化至 100。

    Args:
        portfolio_bars: 组合合并走势（已截断），每项含 {"date": str, ...}
        raw_benchmarks: fetch_benchmarks 的原始输出，
                        {code: {"name": str, "bars": [{date, close, ...}, ...]}}

    Returns:
        [{
            "code": str,          # 指数代码
            "name": str,          # 指数名称
            "bars": [             # 归一化走势，与 portfolio_dates 一一对应
                {"date": str, "value": float},
                ...
            ],
            "total_return_pct": float,    # 区间累计收益率（%）
            "max_drawdown_pct": float,    # 区间最大回撤（%）
            "annualized_volatility": float,  # 区间年化波动率（%）
            "data_start": str,            # 指数起效起始日
            "data_end": str,              # 指数结束日
            "status": str,                # "ok" | "degraded"
        }, ...]
        输入为空或全部归一化失败时返回 []。
    """
    if not portfolio_bars or not raw_benchmarks:
        return []

    portfolio_dates = [b["date"] for b in portfolio_bars]
    if not portfolio_dates:
        return []

    results: list[dict[str, Any]] = []

    for code, bm in raw_benchmarks.items():
        name = bm.get("name", code)
        raw_bars = bm.get("bars", [])
        if not raw_bars:
            continue

        # 构建 date→close 映射，过滤无效数据
        date_to_close: dict[str, float] = {}
        for bar in raw_bars:
            bar_date = bar.get("date")
            if bar_date is None:
                continue
            close = bar.get("close")
            if close is not None and isinstance(close, (int, float)) and close > 0:
                date_to_close[bar_date] = float(close)

        sorted_bar_dates = sorted(date_to_close.keys())
        if not sorted_bar_dates:
            continue

        # 检查数据是否有重叠
        if sorted_bar_dates[0] > portfolio_dates[-1]:
            logger.warning(
                "[normalize] %s(%s) 数据起始日 %s 晚于组合结束日 %s，跳过",
                name,
                code,
                sorted_bar_dates[0],
                portfolio_dates[-1],
            )
            continue
        if sorted_bar_dates[-1] < portfolio_dates[0]:
            logger.warning(
                "[normalize] %s(%s) 数据结束日 %s 早于组合起算日 %s，跳过",
                name,
                code,
                sorted_bar_dates[-1],
                portfolio_dates[0],
            )
            continue

        # 确定对齐起算日 = max(组合起算日, 指数首条数据日)
        align_start = portfolio_dates[0]
        if sorted_bar_dates[0] > align_start:
            align_start = sorted_bar_dates[0]

        # 找到起算日处的最新 close（起算日当天或之前最近一条）
        close_at_start: float | None = None
        for d in sorted_bar_dates:
            if d <= align_start:
                close_at_start = date_to_close[d]
            else:
                break

        if close_at_start is None or close_at_start <= 0:
            logger.warning("[normalize] %s(%s) 起算日 %s 无可用 close", name, code, align_start)
            continue

        # LOCF 填充 + 归一化
        normalized: list[dict[str, Any]] = []
        last_close = close_at_start
        bar_idx = 0

        for pd in portfolio_dates:
            if pd < align_start:
                continue

            # LOCF：将 <= pd 的最新 bar close 前值填充
            while bar_idx < len(sorted_bar_dates) and sorted_bar_dates[bar_idx] <= pd:
                last_close = date_to_close[sorted_bar_dates[bar_idx]]
                bar_idx += 1

            value = round(last_close / close_at_start * 100, 2)
            normalized.append({"date": pd, "value": value})

        if not normalized:
            continue

        logger.info("[normalize] %s(%s) 归一化完成, %d 条数据", name, code, len(normalized))

        # 计算区间累计收益率 = (归一化终值 / 100 - 1) * 100 = 终值 - 100
        total_return_pct = round(normalized[-1]["value"] - 100, 2)

        # 计算最大回撤
        values = [b["value"] for b in normalized]
        peak = values[0]
        max_dd_pct = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd_pct = (peak - v) / peak * 100
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        # 计算年化波动率（%）：日收益率标准差 × sqrt(252) × 100（与组合走势同一口径）
        daily_ret = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values)) if values[i - 1] > 0]
        if len(daily_ret) >= 2:
            _mean = sum(daily_ret) / len(daily_ret)
            _var = sum((r - _mean) ** 2 for r in daily_ret) / (len(daily_ret) - 1)
            annualized_vol_pct = math.sqrt(_var) * math.sqrt(252) * 100
        else:
            annualized_vol_pct = 0.0

        results.append(
            {
                "code": code,
                "name": name,
                "bars": normalized,
                "total_return_pct": total_return_pct,
                "max_drawdown_pct": round(-max_dd_pct, 2),
                "annualized_volatility": round(annualized_vol_pct, 2),
                "data_start": normalized[0]["date"],
                "data_end": normalized[-1]["date"],
                "status": "ok",
            }
        )

    return results


def fetch_benchmarks(
    benchmark_indices: dict[str, str],
    days: int = 365,
) -> dict[str, dict[str, Any]]:
    """并行获取多个基准指数的历史日线数据。

    Args:
        benchmark_indices: {代码: 名称} 映射，如 {"sh000300": "沪深300"}
        days: 获取天数（默认 365，透传给 fetch_index_history）

    Returns:
        {code: {"name": str, "bars": [{date, close, open, high, low, volume}, ...]}}
        获取失败或配置为空时返回空字典。
    """
    if not benchmark_indices:
        logger.debug("[benchmark] benchmark_indices 为空，跳过")
        return {}

    results: dict[str, dict[str, Any]] = {}
    codes = list(benchmark_indices.keys())

    _max_workers = min(4, len(codes)) if len(codes) > 1 else 1
    with ThreadPoolExecutor(max_workers=_max_workers) as pool:
        futures = {pool.submit(fetch_index_history, code, days): code for code in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            name = benchmark_indices[code]
            try:
                bars = fut.result()
            except Exception:
                logger.warning("[benchmark] %s(%s) 获取异常", name, code, exc_info=True)
                bars = None

            if not bars:
                logger.warning("[benchmark] %s(%s) 无可用的历史数据", name, code)
                continue

            results[code] = {
                "name": name,
                "bars": bars,
            }
            logger.info("[benchmark] %s(%s) 获取完成, %d 条日线", name, code, len(bars))

    if not results:
        logger.warning("[benchmark] 所有基准指数均获取失败")

    return results

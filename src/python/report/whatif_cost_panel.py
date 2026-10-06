"""调仓 What-if 交易成本对比面板（whatif_cost_panel）— 开关 ``whatif_trade_cost`` 消费点。

装配 ``whatif_data["cost"]`` 契约（开关开启时由 ``run_whatif_simulation`` 追加键，
开关关闭 → 键缺席 → whatif 双端输出逐字节不变）：

  - **trade_cost**：``analysis.trade_cost_model`` 成本估算本体——逐腿费率/费用、
    申购/赎回合计、未知与未建模计数、口径标注（notes）
  - **impact**：成本前/后收益差——仅回测可用**且费率全知**（``fees_complete``）时；
    口径 = 生效日 t0 一次性扣费，成本后曲线 = 成本前曲线 ×（1 − 费用/目标成本），
    收益统一相对 100 基点基线度量（费率未知不出成本后数字，不留伪精度）
  - **benchmark**：业绩基准三线之第三线——仅回测可用时；映射经
    ``analysis.benchmark_index_resolver``（配置覆盖 → 持仓基准文本 → 宽基默认），
    行情经 ``fetch_index_history`` 既有链路（多源降级），按回测标签 LOCF 对齐并
    归一化到 100 基点；取不到 → status=unavailable（只出成本后对比，不阻塞）
  - **chart**：图表数据（labels / 基准持仓 / 目标·成本后 / 业绩基准），与 impact 同源

I/O 全部经**懒加载 + 可注入**（测试零出网、断言确定性）；单代码/单环节失败只降级
本环节（returns 缺席/None），不抛出、不阻断 whatif 主产物。依赖方向：report →
analysis（纯函数）与 fetcher（备数），analysis 不反向依赖 report（架构纪律）。
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any, Callable

logger = logging.getLogger("invest")


def _is_unmodeled(name: str, code: str) -> bool:
    """场内/直接持有品种判定（不建模申赎费，显式标注而非冒充 0）。

    股票（含 00 区间重叠的名称判别）、场内基金/ETF/LOF、指数代码 → 不建模；
    其余按场外基金建模（申赎费可得）。判定一律经 ``core.code_utils``，禁自建前缀表。
    """
    from src.python.core.code_utils import (
        is_a_share_stock,
        is_exchange_fund_code,
        is_index_code,
    )

    return is_a_share_stock(name, code) or is_exchange_fund_code(code) or is_index_code(code)


def _load_snapshots() -> list[Any]:
    """本机持仓快照历史（批次重放输入）；加载失败 → 空列表（卖出腿费率判未知）。"""
    try:
        from src.python.report.history_snapshot import load_all

        return load_all()
    except Exception:  # noqa: BLE001 — 快照缺失/损坏不得阻断面板（仅兜 Exception）
        logger.warning("[交易成本] 持仓快照加载失败，卖出腿按持有期未知降级", exc_info=True)
        return []


def _align_benchmark_values(labels: list[Any], bars: list[dict[str, Any]] | None) -> list[float | None] | None:
    """指数日线 → 按回测标签对齐（LOCF 前向填充）并归一化到 100 基点。

    标签早于指数首个可用日的前段保持 None（图上留缺口，不外推）；
    无任何交集 / 锚点非正 → None（调用方按取不到处理）。
    """
    if not labels or not bars:
        return None
    by_date: dict[str, float] = {}
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        text = str(bar.get("date") or "")[:10]
        close = bar.get("close")
        if text and isinstance(close, (int, float)) and not isinstance(close, bool) and math.isfinite(close):
            by_date[text] = float(close)  # 输入按日升序，同日后者覆盖
    if not by_date:
        return None

    values: list[float | None] = []
    last: float | None = None
    for label in labels:
        key = str(label)[:10]
        if key in by_date:
            last = by_date[key]
        values.append(round(last, 4) if last is not None else None)

    anchor = next((v for v in values if v is not None), None)
    if anchor is None or anchor <= 0:
        return None
    return [None if v is None else round(v / anchor * 100.0, 4) for v in values]


def build_whatif_cost_panel(
    whatif_data: dict[str, Any] | None,
    effective_date: str | None = None,
    *,
    snapshots: list[Any] | None = None,
    count_trading_days: Callable[[str, str], int | None] | None = None,
    fee_index: dict[str, Any] | None = None,
    benchmark_override: str | None = None,
    comparison_indices: dict[str, str] | None = None,
    benchmark_text_getter: Callable[[str], Any] | None = None,
    index_history_getter: Callable[[str, int], Any] | None = None,
) -> dict[str, Any]:
    """装配 whatif 成本面板契约（开关 ``whatif_trade_cost`` 开启时调用）。

    Args:
        whatif_data: whatif 主数据契约（消费 ``changes``/``backtest``/``candidate``）
        effective_date: 调仓生效日（None/空 → 无回测语境，持有期截止日取当日）
        snapshots: 持仓快照序列（注入；None → 现场加载，失败按空降级）
        count_trading_days: 交易日计数注入（None → ``count_trading_days_elapsed``）
        fee_index: 费率索引注入（None → ``fetch_fee_index`` 现场取，失败按空降级）
        benchmark_override: 基准覆盖值（None → 读 ``config.whatif_benchmark_index``）
        comparison_indices: 宽基指数池（None → 读 ``config.comparison_indices``）
        benchmark_text_getter: 基准文本查询注入（None → ``fetch_fund_benchmark``）
        index_history_getter: 指数行情注入（None → ``fetch_index_history``）

    Returns:
        ``{"available", "trade_cost", "impact", "benchmark", "chart", "reason"}``——
        ``available`` 随成本本体（无变动腿 → False + reason）；impact/benchmark/chart
        按前置条件可缺席（None），键位恒在便于渲染层统一判空。
    """
    changes = (whatif_data or {}).get("changes") or []

    # ── 品种划分：场内/股票不建模；场外基金才进费率装配 ──
    unmodeled_codes: set[str] = set()
    fund_codes: list[str] = []
    for c in changes:
        code = str(c.get("code") or "").strip()
        if not code or c.get("action") == "不变":
            continue
        if _is_unmodeled(str(c.get("name") or ""), code):
            unmodeled_codes.add(code)
        elif code not in fund_codes:
            fund_codes.append(code)

    # ── 成本本体（批次重放 + 费率索引 + 交易日计数，全部可注入）──
    if snapshots is None:
        snapshots = _load_snapshots()
    from src.python.analysis.trade_cost_model import rebuild_position_lots

    lots_by_code = rebuild_position_lots(snapshots)

    if count_trading_days is None:
        from src.python.core.trading_calendar import count_trading_days_elapsed

        count_trading_days = count_trading_days_elapsed
    if fee_index is None and fund_codes:
        try:
            from src.python.fetcher.fund_fee import fetch_fee_index

            fee_index = fetch_fee_index(fund_codes)
        except Exception:  # noqa: BLE001 — 费率取数失败按未知降级，不阻断（BaseException 不吞）
            logger.warning("[交易成本] 费率索引装配失败，按费率未知降级", exc_info=True)
            fee_index = {}
    if fee_index is None:
        fee_index = {}

    hold_end = effective_date or date.today().isoformat()
    from src.python.analysis.trade_cost_model import compute_trade_costs

    trade_cost = compute_trade_costs(
        changes,
        fee_index=fee_index,
        lots_by_code=lots_by_code,
        count_trading_days=count_trading_days,
        effective_date=effective_date or "",
        holding_end_date=hold_end,
        unmodeled_codes=unmodeled_codes,
    )

    panel: dict[str, Any] = {
        "available": bool(trade_cost.get("available")),
        "trade_cost": trade_cost,
        "impact": None,
        "benchmark": None,
        "chart": None,
        "reason": trade_cost.get("reason", ""),
    }
    if not panel["available"]:
        return panel

    # ── 回测语境：impact / benchmark / chart 三者共享回测标签 ──
    bt = (whatif_data or {}).get("backtest")
    series = (bt or {}).get("series") or {}
    labels = series.get("labels") or []
    if not (bt and bt.get("available") and labels):
        return panel  # 无回测 → 只出成本块（成本前/后差与三线皆依赖回测标签）

    base_vals = series.get("base") or []
    cand_vals = series.get("candidate") or []

    # ── 成本前/后收益差（t0 一次性扣费；费率全知才出数字）──
    cand_t0_value = float(((whatif_data or {}).get("candidate") or {}).get("total_cost") or 0.0)
    fee_total = float(trade_cost.get("total_cost") or 0.0)
    ratio: float | None = None
    candidate_after: list[float] | None = None
    if trade_cost.get("fees_complete") and cand_t0_value > 0 and cand_vals:
        ratio = fee_total / cand_t0_value
        if 0 <= ratio < 1:
            ratio = round(ratio, 6)
            candidate_after = [round(v * (1.0 - ratio), 4) for v in cand_vals]
            return_before = round(cand_vals[-1] - 100.0, 2)  # 序列以 100 基点起
            return_after = round(candidate_after[-1] - 100.0, 2)
            panel["impact"] = {
                "fee_total": round(fee_total, 2),
                "cand_t0_value": round(cand_t0_value, 2),
                "t0_ratio": ratio,
                "return_before_pct": return_before,
                "return_after_pct": return_after,
                "delta_pct_points": round(return_after - return_before, 2),
            }
        else:
            ratio = None

    # ── 业绩基准三线（映射 + 行情，逐环节降级）──
    panel["benchmark"] = _resolve_benchmark(
        changes=changes,
        effective_date=effective_date,
        labels=labels,
        benchmark_override=benchmark_override,
        comparison_indices=comparison_indices,
        benchmark_text_getter=benchmark_text_getter,
        index_history_getter=index_history_getter,
    )

    panel["chart"] = {
        "labels": labels,
        "base": base_vals,
        "candidate_after": candidate_after,
        "candidate_before": cand_vals,
        "benchmark": (panel["benchmark"] or {}).get("values"),
    }
    return panel


def _resolve_benchmark(
    *,
    changes: list[dict[str, Any]],
    effective_date: str | None,
    labels: list[Any],
    benchmark_override: str | None,
    comparison_indices: dict[str, str] | None,
    benchmark_text_getter: Callable[[str], Any] | None,
    index_history_getter: Callable[[str, int], Any] | None,
) -> dict[str, Any] | None:
    """基准指数解析与行情对齐（逐环节降级；返回 None = 本环节缺席）。"""
    from src.python.analysis.benchmark_index_resolver import resolve_benchmark_index

    try:
        if comparison_indices is None or benchmark_text_getter is None or benchmark_override is None:
            from src.python.config import get_config

            config = get_config()
            if comparison_indices is None:
                comparison_indices = config.get("comparison_indices") or {}
            if benchmark_override is None:
                benchmark_override = config.get("whatif_benchmark_index") or ""
        if benchmark_text_getter is None:
            from src.python.fetcher.fund import fetch_fund_benchmark

            benchmark_text_getter = fetch_fund_benchmark
        if index_history_getter is None:
            from src.python.fetcher.index import fetch_index_history

            index_history_getter = fetch_index_history

        holdings = [
            {"code": str(c.get("code") or ""), "name": str(c.get("name") or ""), "cost": c.get("cand_cost") or 0.0}
            for c in changes
            if str(c.get("code") or "") and (c.get("cand_cost") or 0) > 0
        ]
        resolved = resolve_benchmark_index(
            holdings,
            override=benchmark_override,
            comparison_indices=comparison_indices,
            benchmark_text_getter=benchmark_text_getter,
        )
    except Exception:  # noqa: BLE001 — 映射/配置异常 → 三线缺席（不阻断成本块）
        logger.warning("[交易成本] 基准指数映射失败，三线缺席", exc_info=True)
        return None

    from src.python.analysis.whatif_backtest import compute_backtest_days

    days = compute_backtest_days(effective_date) or max(120, len(labels) * 2)
    try:
        bars = index_history_getter(resolved["code"], days)
    except Exception:  # noqa: BLE001 — 行情取数失败 → status=unavailable（只出成本后对比）
        logger.warning("[交易成本] 基准指数行情获取失败: %s", resolved["code"], exc_info=True)
        bars = None
    values = _align_benchmark_values(labels, bars if isinstance(bars, list) else None)
    return {
        **resolved,
        "status": "ok" if values else "unavailable",
        "values": values,
    }


__all__ = ["build_whatif_cost_panel"]

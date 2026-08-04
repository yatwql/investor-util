"""行动建议单一数据源 — 19 章「行动建议」的计算层（C14/C19 单源计算）。

决策闭环的核心产出（再平衡信号 + 交易纪律 + 调仓建议 + 收益归因）均为
纯算法功能，与 LLM 无关。本模块是 19 章「行动建议」与 13 章「行动摘要」
共享的唯一计算入口——计算结果经 orchestrator 组装进 pipeline_data
（C19 契约 `action_data`），17/12 两处渲染均从模板 context 取，
不写模块级全局变量（C14 合规，单源计算两处呈现）。

C19 契约 `action_data`：
  {
    "available": bool,           # 持仓明细可用
    "rebalance_signals": list,   # 再平衡信号（单品超限，复用 simple_rebalance）
    "discipline_signals": list,  # 交易纪律触发（止盈/止损/回撤）
    "rebalance_advice": list,    # 调仓建议清单（可行化层：份额取整/费用估算/现金缓冲）
    "attribution": dict | None,  # 收益归因（TOP5 贡献占比，正负分列 + 合计摘要）
    "summary": str,              # 行动摘要一句话
  }

架构约束：
  ⚠️ 禁止导入 report/ 包下的任何模块。
  仅消费调用方传入的数据（holdings_details + total_mv），
  保持与报告层的完全解耦。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.analysis.rebalance_advisor import build_rebalance_advice
from src.python.analysis.return_attribution import build_return_attribution
from src.python.analysis.simple_rebalance import compute_simple_rebalance_signals
from src.python.analysis.trade_discipline import compute_discipline_signals

logger = logging.getLogger("invest")

__all__ = ["build_action_data"]


def _build_summary(
    rebalance_signals: list[dict[str, Any]],
    discipline_signals: list[dict[str, Any]],
    rebalance_advice: list[dict[str, Any]],
    attribution: dict | None,
) -> str:
    """构建行动摘要一句话（按子块产出逐项拼接）。

    Args:
        rebalance_signals: 再平衡信号列表
        discipline_signals: 交易纪律触发列表
        rebalance_advice: 调仓建议清单
        attribution: 收益归因 dict 或 None

    Returns:
        摘要文本，如「再平衡建议 2 条」；全部为空时返回「当前无行动建议」。
    """
    parts: list[str] = []
    if rebalance_signals:
        parts.append(f"再平衡建议 {len(rebalance_signals)} 条")
    if discipline_signals:
        parts.append(f"纪律触发 {len(discipline_signals)} 条")
    if rebalance_advice:
        parts.append(f"调仓建议 {len(rebalance_advice)} 条")
    if attribution and attribution.get("available"):
        parts.append("收益归因已生成")
    if not parts:
        return "当前无行动建议"
    return "；".join(parts)


def build_action_data(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
    discipline_config: dict[str, Any] | None = None,
    portfolio_peak_mv: float | None = None,
) -> dict[str, Any]:
    """构建行动建议单一数据源（C19 契约 `action_data`）。

    Args:
        holdings_details: 持仓明细列表（含 market_value/name/code/profit/profit_rate 等）
        total_mv: 持仓总市值
        discipline_config: 交易纪律配置段（None 时由纪律引擎读取全局配置）
        portfolio_peak_mv: 组合历史峰值市值（None 时纪律引擎跳过回撤纪律）

    Returns:
        C19 契约 dict（结构见模块 docstring）。available 表示持仓明细可用；
        再平衡/纪律/调仓建议/收益归因子块均已填充；Σ|profit|=0 时归因返回 None
        （渲染层写「待生成」占位）。
    """
    available = bool(holdings_details)
    rebalance_signals: list[dict[str, Any]] = []
    discipline_signals: list[dict[str, Any]] = []
    rebalance_advice: list[dict[str, Any]] = []
    attribution: dict[str, Any] | None = None
    if available and total_mv > 0:
        rebalance_signals = compute_simple_rebalance_signals(holdings_details, total_mv)
        discipline_signals = compute_discipline_signals(
            holdings_details,
            total_mv,
            discipline_config=discipline_config,
            portfolio_peak_mv=portfolio_peak_mv,
        )
        # 调仓建议可行化清单：把再平衡/纪律触发信号转成可执行订单
        # （份额取整一手、费用估算、现金缓冲防负值、优先级排序）
        rebalance_advice = build_rebalance_advice(
            rebalance_signals,
            discipline_signals,
            holdings_details,
            total_mv,
        )
        # 收益归因（贡献占比）：TOP5 盈利/亏损来源，正负分列 + 合计摘要
        attribution = build_return_attribution(holdings_details)

    summary = _build_summary(rebalance_signals, discipline_signals, rebalance_advice, attribution)
    return {
        "available": available,
        "rebalance_signals": rebalance_signals,
        "discipline_signals": discipline_signals,
        "rebalance_advice": rebalance_advice,
        "attribution": attribution,
        "summary": summary,
    }

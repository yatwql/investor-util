"""极简再平衡信号计算模块（硬编码阈值）。

架构约束：
  ⚠️ 禁止导入 report/ 包下的任何模块。
  仅消费调用方传入的数据（holdings_details + total_mv），
  保持与报告层的完全解耦。

阈值与规则：
  - 单品种 weight = market_value / total_value
  - 硬编码阈值 15%（0.15），超出触发建议
  - 超过 3 个品种同时触发时聚合为一条汇总建议
  - 按偏离幅度排序，最多返回 3 条（或 1 条汇总）

返回格式：
  [
    {"code": str, "name": str, "weight": float,
     "threshold": float, "action": str},
    ...
  ]
  汇总模式：
  [{"summary": True, "count": int,
    "message": "集中度较高，N 个品种超过 15% 警戒线..."}]
"""

from __future__ import annotations

from typing import Any

__all__ = ["compute_rebalance_signals"]

_THRESHOLD = 0.15  # 单品种权重上限（硬编码）
_MAX_DETAILED = 3  # 逐条显示上限


def compute_rebalance_signals(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
) -> list[dict[str, Any]]:
    """计算再平衡信号。

    Args:
        holdings_details: 持仓明细列表（含 market_value / name / code）
        total_mv: 持仓总市值

    Returns:
        再平衡信号列表（结构见模块文档）
    """
    if not holdings_details or total_mv <= 0:
        return []

    signals: list[dict[str, Any]] = []
    for h in holdings_details:
        mv = h.get("market_value", 0) or 0
        weight = mv / total_mv
        if weight > _THRESHOLD:
            signals.append(
                {
                    "code": h.get("code", ""),
                    "name": h.get("name", ""),
                    "weight": round(weight, 4),
                    "threshold": _THRESHOLD,
                    "action": "建议部分止盈至10-15%区间",
                }
            )

    if not signals:
        return []

    # 去重聚合：超过 _MAX_DETAILED 个触发时汇总
    if len(signals) > _MAX_DETAILED:
        return [
            {
                "summary": True,
                "count": len(signals),
                "message": (
                    f"您的组合集中度较高，有 {len(signals)} 个品种超过 "
                    f"{_THRESHOLD * 100:.0f}% 警戒线，建议整体考虑适度分散"
                ),
            }
        ]

    # 按权重降序
    signals.sort(key=lambda x: -x["weight"])
    return signals[:_MAX_DETAILED]

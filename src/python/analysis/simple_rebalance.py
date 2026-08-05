"""极简再平衡信号计算模块（配置化阈值 + 静默期）。

架构约束：
  ⚠️ 禁止导入 report/ 包下的任何模块。
  仅消费调用方传入的数据（holdings_details + total_mv），
  保持与报告层的完全解耦。

阈值与规则：
  - 单品种 weight = market_value / total_value
  - 超限阈值默认 15%（0.15），可从 config 的 ``rebalance.threshold`` 覆盖
  - 超过 3 个品种同时触发时聚合为一条汇总建议
  - 按偏离幅度排序，最多返回 3 条（或 1 条汇总）
  - 静默期（config ``rebalance.silence_days``，默认 30 天）：同一品种触发后
    N 天内不重复告警，复用 ``_silence.py`` 持久化机制；``silence_days=0`` 关闭

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

from src.python.core.constants import PROJECT_ROOT
import os

__all__ = ["compute_simple_rebalance_signals"]

_THRESHOLD = 0.15  # 单品种权重上限（默认值，可被 config 覆盖）
_MAX_DETAILED = 3  # 逐条显示上限

# 静默期持久化路径（与 rebalance.py 完整引擎共用；可通过参数注入测试路径）
_SILENCE_FILE = os.path.join(PROJECT_ROOT, "data/state/rebalance_silence.json")


def _resolve_threshold(threshold: float | None) -> float:
    """解析超限阈值：显式参数优先，否则读 config rebalance.threshold。"""
    if threshold is not None:
        return threshold
    from src.python.config import get_config

    return get_config().get("rebalance", {}).get("threshold", _THRESHOLD)


def _resolve_silence_days(silence_days: int | None) -> int:
    """解析静默期天数：显式参数优先，否则读 config rebalance.silence_days。"""
    if silence_days is not None:
        return silence_days
    from src.python.config import get_config

    return get_config().get("rebalance", {}).get("silence_days", 0)


def compute_simple_rebalance_signals(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
    threshold: float | None = None,
    silence_days: int | None = None,
    silence_file: str | None = None,
) -> list[dict[str, Any]]:
    """计算再平衡信号（配置化阈值 + 静默期过滤）。

    Args:
        holdings_details: 持仓明细列表（含 market_value / name / code）
        total_mv: 持仓总市值
        threshold: 单品种权重超限阈值（小数）。None 时读 config rebalance.threshold
        silence_days: 静默期天数。None 时读 config rebalance.silence_days；
                      0 表示关闭静默期
        silence_file: 静默期持久化路径。None 时使用模块默认路径

    Returns:
        再平衡信号列表（结构见模块文档）
    """
    if not holdings_details or total_mv <= 0:
        return []

    limit = _resolve_threshold(threshold)

    signals: list[dict[str, Any]] = []
    for h in holdings_details:
        mv = h.get("market_value", 0) or 0
        weight = mv / total_mv
        if weight > limit:
            signals.append(
                {
                    "code": h.get("code", ""),
                    "name": h.get("name", ""),
                    "weight": round(weight, 4),
                    "threshold": limit,
                    "action": f"建议部分止盈至{limit * 50:.0f}-{limit * 100:.0f}%区间",
                }
            )

    if not signals:
        return []

    # 去重聚合：超过 _MAX_DETAILED 个触发时汇总
    if len(signals) > _MAX_DETAILED:
        result: list[dict[str, Any]] = [
            {
                "summary": True,
                "count": len(signals),
                "message": (
                    f"您的组合集中度较高，有 {len(signals)} 个品种超过 {limit * 100:.0f}% 警戒线，建议整体考虑适度分散"
                ),
            }
        ]
    else:
        # 按权重降序
        signals.sort(key=lambda x: -x["weight"])
        result = signals[:_MAX_DETAILED]

    # 静默期过滤 + 更新（复用 _silence.py 机制，仅单品信号参与）
    days = _resolve_silence_days(silence_days)
    if days > 0:
        from src.python.analysis._silence import (
            _filter_silenced_signals,
            _update_silence_state,
        )

        path = silence_file or _SILENCE_FILE
        result = _filter_silenced_signals(result, days, path)
        _update_silence_state(result, path)

    return result

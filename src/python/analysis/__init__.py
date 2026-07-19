"""分析计算模块 — 与 report/ 无依赖的业务计算层。

所有分析计算逻辑收敛于此包，严格禁止导入 report/ 下的任何模块。
仅消费调用方传入的数据（holdings_details / total_mv 等），
保持与报告层的完全解耦。

已实现：
  - simple_rebalance: 极简再平衡信号计算
正在迁移：
  - 证券代码/分类判定 → 全部收敛至 code_utils.py（已完成）
  - 币种判定 → 待迁移
"""

from __future__ import annotations

from src.python.analysis.simple_rebalance import compute_rebalance_signals  # noqa: F401

__all__ = [
    "compute_rebalance_signals",
]

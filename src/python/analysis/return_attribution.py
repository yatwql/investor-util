"""收益归因计算与 20 章适配层 — 品种收益贡献占比（TOP 5，正负分列 + 合计摘要）。

决策闭环的纯算法能力：组合收益按品种贡献排序——TOP 5 盈利/亏损来源
（贡献占比 pp，非收益率，两者不可混用），正负分列 + 正负合计摘要。
纯本地计算（零新增外部依赖），由 `llm/prompts_core._build_profit_attribution_block`
（14 章 LLM 提示词段落）与 20 章行动建议归因子块（表格）两处复用，避免重复实现
（归因计算唯一实现，段落/表格均为同一数据的两处格式化呈现）。

C19 契约 `action_data["attribution"]`（`build_return_attribution` 输出）：
  {
    "available": bool,           # 有持仓且 Σ|profit|>0
    "盈利来源": list[dict],       # TOP5 盈利品种（name/code/profit/contribution_pp）
    "亏损来源": list[dict],       # TOP5 亏损品种（name/code/profit/contribution_pp）
    "summary": str,              # 正负合计摘要（净额合计，报告层可见）
  }
  contribution_pp 为全精度浮点（贡献占比 pp，正数盈利 / 负数亏损），由渲染层
  格式化展示（如 +47.6pp）；profit 为原始盈亏金额（元）。

架构约束：
  ⚠️ 禁止导入 report/ 包下的任何模块；纯计算层，仅消费调用方传入的
  holdings_details（含 name/code/profit），与报告层完全解耦。
  依赖方向：`llm/prompts_core` 惰性 import 本模块（llm → analysis 单向依赖，
  与 `_build_rebalance_block` 复用 simple_rebalance 同构）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("invest")

__all__ = ["compute_return_attribution", "build_return_attribution"]

# TOP 5 品种贡献排序（与 `_build_profit_attribution_block` 提示词口径一致）
_TOP_N = 5


def compute_return_attribution(
    holdings_details: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """收益归因纯计算（共享唯一实现，供提示词段落与 20 章表格两处复用）。

    Args:
        holdings_details: 持仓明细列表（含 name/code/profit，profit 可缺省按 0）。

    Returns:
        None 当无持仓或 Σ|profit|==0（无盈亏可归因）；
        dict：{available, 盈利来源, 亏损来源, pos_total, neg_total, total_abs}——
        盈利/亏损来源为 TOP5 内各自分列（按 |profit| 降序），每项含
        name/code/profit/contribution_pp（全精度浮点，正数盈利 / 负数亏损）；
        pos_total/neg_total 为全部持仓（非仅 TOP5）的正负盈亏合计。
    """
    if not holdings_details:
        return None
    profits = [(h.get("name", ""), h.get("code", ""), h.get("profit", 0) or 0) for h in holdings_details]
    total_abs = sum(abs(p) for _, _, p in profits)
    if total_abs == 0:
        return None

    top5 = sorted(profits, key=lambda x: abs(x[2]), reverse=True)[:_TOP_N]
    pos = [(n, c, p) for n, c, p in top5 if p > 0]
    neg = [(n, c, p) for n, c, p in top5 if p < 0]

    def _item(name: str, code: str, profit: float) -> dict[str, Any]:
        return {
            "name": name,
            "code": code,
            "profit": profit,
            "contribution_pp": profit / total_abs * 100,
        }

    return {
        "available": True,
        "盈利来源": [_item(n, c, p) for n, c, p in pos],
        "亏损来源": [_item(n, c, p) for n, c, p in neg],
        "pos_total": sum(p for _, _, p in profits if p > 0),
        "neg_total": sum(p for _, _, p in profits if p < 0),
        "total_abs": total_abs,
    }


def build_return_attribution(
    holdings_details: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """20 章行动建议收益归因子块（渲染适配层，C19 `attribution` 契约）。

    复用 `compute_return_attribution` 计算结果，适配为报告层可读的表格数据——
    盈利来源 / 亏损来源分列、净额合计（summary）在报告层可见（渲染适配层为新代码，
    非纯复用：把共享计算塑形为 20 章表格契约，contribution_pp 全精度浮点、profit
    原始盈亏金额，由渲染层格式化展示）。

    Args:
        holdings_details: 持仓明细列表（同 `compute_return_attribution`）。

    Returns:
        None 当无可归因数据（无持仓 / Σ|profit|==0，渲染层写「待生成」占位）；
        dict：{available, 盈利来源, 亏损来源, summary}（结构见模块 docstring）。
    """
    data = compute_return_attribution(holdings_details)
    if not data:
        return None
    pos_total = data["pos_total"]
    neg_total = data["neg_total"]
    net = pos_total + neg_total
    if pos_total > 0 and neg_total < 0:
        summary = f"盈利品种合计 +{pos_total:,.2f}，亏损品种合计 {neg_total:,.2f}（净{net:+,.2f}）"
    elif pos_total > 0:
        summary = f"全部品种盈利，合计 +{pos_total:,.2f}"
    elif neg_total < 0:
        summary = f"全部品种亏损，合计 {neg_total:,.2f}"
    else:
        summary = ""
    return {
        "available": True,
        "盈利来源": data["盈利来源"],
        "亏损来源": data["亏损来源"],
        "summary": summary,
    }

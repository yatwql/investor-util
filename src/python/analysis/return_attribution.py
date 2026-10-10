"""收益归因计算与行动建议章适配层 — 品种收益贡献占比（TOP 5，正负分列 + 合计摘要）。

决策闭环的纯算法能力：组合收益按品种贡献排序——TOP 5 盈利/亏损来源
（贡献占比 pp，非收益率，两者不可混用），正负分列 + 正负合计摘要。
纯本地计算（零新增外部依赖），由 `llm/prompts_core._build_profit_attribution_block`
（智囊团深度复盘 LLM 提示词段落）与行动建议归因子块（表格）两处复用，避免重复实现
（归因计算唯一实现，段落/表格均为同一数据的两处格式化呈现）。

呈现为「大类 → 品种」两级：大类层按 `code_utils.classify_holding_tier` 单源分类
聚合为权益/固收/现金（未知二元组兑底「其他」），品种层为 TOP5——两层共用同一
分母 Σ|profit|，Σ大类贡献 ≡ Σ品种贡献（结构关系由单测锁定）。

数据契约 `action_data["attribution"]`（`build_return_attribution` 输出）：
  {
    "available": bool,           # 有持仓且 Σ|profit|>0
    "盈利来源": list[dict],       # TOP5 盈利品种（name/code/profit/contribution_pp）
    "亏损来源": list[dict],       # TOP5 亏损品种（name/code/profit/contribution_pp）
    "大类贡献": list[dict],       # 资产类分解（asset_class/profit/contribution_pp，|profit| 降序）
    "summary": str,              # 正负合计摘要（净额合计，报告层可见）
    "note": str,                 # 口径说明句（渲染层脚注单源文案，HTML/Excel 同句）
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

from src.python.core.code_utils import classify_holding_tier

logger = logging.getLogger("invest")

__all__ = ["compute_return_attribution", "build_return_attribution"]

# TOP 5 品种贡献排序（与 `_build_profit_attribution_block` 提示词口径一致）
_TOP_N = 5

# 大类映射：单源分类二元组 → 资产类（权益/固收/现金）；未知二元组兑底「其他」
# （键集覆盖 classify_holding_tier 全部可产出二元组，由单测锁定）
_ASSET_CLASS_BY_TIER = {
    ("股票", "A股"): "权益",
    ("基金", "QDII"): "权益",
    ("基金", "被动"): "权益",
    ("基金", "主动"): "权益",
    ("基金", "指数"): "权益",
    ("基金", "混合"): "权益",
    ("债券", "纯债"): "固收",
    ("现金", "货币"): "现金",
}

#: 渲染层脚注口径句（HTML/Excel 单源消费，勿在渲染层复制字面量）
ATTRIBUTION_NOTE = "口径：贡献占比 = 盈亏金额 ÷ Σ|盈亏|（持仓成本口径，非严格区间收益归因）"


def _asset_class_for_tier(tier: tuple[str, str]) -> str:
    """(资产属性, 投资分类) → 资产类（未知二元组兑底「其他」）。"""
    return _ASSET_CLASS_BY_TIER.get(tier, "其他")


def compute_return_attribution(
    holdings_details: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """收益归因纯计算（共享唯一实现，供提示词段落与行动建议表格两处复用）。

    Args:
        holdings_details: 持仓明细列表（含 name/code/profit/account，profit 可缺省按 0，
            account 缺省按空串——大类分解的场外渠道判定需要账户名）。

    Returns:
        None 当无持仓或 Σ|profit|==0（无盈亏可归因）；
        dict：{available, 盈利来源, 亏损来源, 大类贡献, pos_total, neg_total, total_abs}——
        盈利/亏损来源为 TOP5 内各自分列（按 |profit| 降序），每项含
        name/code/profit/contribution_pp（全精度浮点，正数盈利 / 负数亏损）；
        大类贡献为资产类分解（asset_class/profit/contribution_pp，|profit| 降序，
        与品种层共用 total_abs 分母）；pos_total/neg_total 为全部持仓（非仅 TOP5）
        的正负盈亏合计。
    """
    if not holdings_details:
        return None
    profits = [
        (h.get("name", ""), h.get("code", ""), h.get("profit", 0) or 0, h.get("account", "")) for h in holdings_details
    ]
    total_abs = sum(abs(p) for _, _, p, _ in profits)
    if total_abs == 0:
        return None

    top5 = sorted(profits, key=lambda x: abs(x[2]), reverse=True)[:_TOP_N]
    pos = [(n, c, p) for n, c, p, _ in top5 if p > 0]
    neg = [(n, c, p) for n, c, p, _ in top5 if p < 0]

    def _item(name: str, code: str, profit: float) -> dict[str, Any]:
        return {
            "name": name,
            "code": code,
            "profit": profit,
            "contribution_pp": profit / total_abs * 100,
        }

    # 大类层：单源分类聚合（Σ大类 ≡ Σ品种，同一 total_abs 分母）
    class_sums: dict[str, float] = {}
    for n, c, p, a in profits:
        asset_class = _asset_class_for_tier(classify_holding_tier(n, c, a))
        class_sums[asset_class] = class_sums.get(asset_class, 0.0) + p
    asset_breakdown = [
        {"asset_class": ac, "profit": v, "contribution_pp": v / total_abs * 100}
        for ac, v in sorted(class_sums.items(), key=lambda kv: abs(kv[1]), reverse=True)
    ]

    return {
        "available": True,
        "盈利来源": [_item(n, c, p) for n, c, p in pos],
        "亏损来源": [_item(n, c, p) for n, c, p in neg],
        "大类贡献": asset_breakdown,
        "pos_total": sum(p for _, _, p, _ in profits if p > 0),
        "neg_total": sum(p for _, _, p, _ in profits if p < 0),
        "total_abs": total_abs,
    }


def build_return_attribution(
    holdings_details: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """行动建议收益归因子块（渲染适配层，`attribution` 契约）。

    复用 `compute_return_attribution` 计算结果，适配为报告层可读的表格数据——
    盈利来源 / 亏损来源分列、净额合计（summary）在报告层可见（渲染适配层为新代码，
    非纯复用：把共享计算塑形为行动建议表格契约，contribution_pp 全精度浮点、profit
    原始盈亏金额，由渲染层格式化展示）。

    Args:
        holdings_details: 持仓明细列表（同 `compute_return_attribution`）。

    Returns:
        None 当无可归因数据（无持仓 / Σ|profit|==0，渲染层写「待生成」占位）；
        dict：{available, 盈利来源, 亏损来源, 大类贡献, summary, note}
        （结构见模块 docstring）。
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
        "大类贡献": data["大类贡献"],
        "summary": summary,
        "note": ATTRIBUTION_NOTE,
    }

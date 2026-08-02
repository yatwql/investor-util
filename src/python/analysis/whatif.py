"""调仓 What-if 模拟 — 双持仓对比计算。

对两份持仓（基准 base / 目标 candidate）做**成本口径**截面比较，
输出 C19 契约 `whatif_data`，供 Excel 调仓模拟报告与 HTML 双栏对比页消费。

设计边界（对应 plan-advanced-analysis.md §2 风险）：
  - **成本口径**：candidate 持仓没有市场历史，无法取实时市值/净值，
    所有指标（权重/集中度）均基于 成本 = 份额 × 每份成本 计算，纯结构层、
    零网络请求（"只能做截面比较"）。
  - **不可回测**：What-if 的量化指标（夏普/波动率等）没有真实交易数据，
    本模块不产出任何回测类结论。

变动类型（复用 schemas/history.py `_DiffAction` 语义）：
  新增 / 清仓 / 加仓 / 减仓 / 不变
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.analysis.rebalance import (
    _CATEGORY_LABELS,
    _CATEGORY_ORDER,
    classify_holding,
)
from src.python.core.models import Holding

logger = logging.getLogger("invest")

# 份额比较容差：|Δ份额| < 该值视为「不变」
_EPS = 1e-3


def _arrow(delta: float) -> str:
    """指标变化箭头：↑ 增加 / ↓ 减少 / → 不变。"""
    if delta > _EPS:
        return "↑"
    if delta < -_EPS:
        return "↓"
    return "→"


def _merge_holdings(holdings: list[Holding]) -> dict[str, dict[str, Any]]:
    """按 code 合并多账户持仓 → {code: {name, shares, cost, weight}}。

    同一 code 出现在多个账户时份额累加、成本累加；名称取第一个非空。

    Args:
        holdings: 持仓列表（可能含多账户）

    Returns:
        {code: {"name": str, "shares": float, "cost": float, "weight": float}}
        总成本为 0 时 weight 统一为 0。
    """
    merged: dict[str, dict[str, Any]] = {}
    total_cost = sum((h.shares or 0.0) * (h.cost_price or 0.0) for h in holdings)

    for h in holdings:
        code = (h.code or "").strip()
        if not code:
            continue
        shares = h.shares or 0.0
        cost_price = h.cost_price or 0.0
        cost = shares * cost_price
        entry = merged.get(code)
        if entry is None:
            merged[code] = {
                "name": (h.name or code).strip() or code,
                "shares": shares,
                "cost": cost,
            }
        else:
            entry["shares"] += shares
            entry["cost"] += cost
            if not entry.get("name") and h.name:
                entry["name"] = h.name.strip()

    for entry in merged.values():
        entry["weight"] = round(entry["cost"] / total_cost, 6) if total_cost > 0 else 0.0

    return merged


def _compute_hhi(holdings_index: dict[str, dict[str, Any]]) -> float:
    """成本口径 HHI = Σ(权重²)。"""
    return round(sum(e["weight"] ** 2 for e in holdings_index.values()), 6)


def _category_stats(
    holdings_index: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """按资产大类汇总成本与权重占比。

    Returns:
        {category_key: {"cost": float, "weight_pct": float}}，仅含非空大类。
    """
    total_cost = sum(e["cost"] for e in holdings_index.values())
    buckets: dict[str, dict[str, float]] = {}
    for code, entry in holdings_index.items():
        cat = classify_holding(entry["name"], code)
        b = buckets.setdefault(cat, {"cost": 0.0, "weight_pct": 0.0})
        b["cost"] += entry["cost"]
    for b in buckets.values():
        b["weight_pct"] = round(b["cost"] / total_cost * 100, 2) if total_cost > 0 else 0.0
    return buckets


def build_whatif_data(
    base: list[Holding],
    candidate: list[Holding],
    base_file: str = "",
    candidate_file: str = "",
) -> dict[str, Any]:
    """构建调仓 What-if 对比 C19 契约 dict。

    Args:
        base:      基准持仓（调仓前）
        candidate: 目标持仓（调仓后/假设）
        base_file: 基准文件显示名（用于报告展示）
        candidate_file: 目标文件显示名

    Returns:
        whatif_data 契约 dict：
          - available / status / reason: 数据可用性（两侧均为空 → 降级；
            单侧为空视为合法的「全部清仓/全部新增」对比，仍可计算）
          - base_file / candidate_file: 展示名
          - base / candidate: 各侧 {total_cost, total_shares, holding_count, hhi}
          - summary: [{key, label, unit, base, candidate, delta, arrow}]（成本/份额/品种数/HHI）
          - categories: [{key, label, base_cost, cand_cost, base_weight, cand_weight, delta_pct}]
            按 _CATEGORY_ORDER 排序，仅含任一侧非空的大类
          - changes: [{code, name, action, base_shares, cand_shares, shares_diff,
                        base_cost, cand_cost, cost_diff, base_weight, cand_weight,
                        weight_delta_pct}] 按 新增→清仓→加仓→减仓→不变 排序
          - stats: {added, removed, increased, decreased, unchanged}
    """
    base_idx = _merge_holdings(base)
    cand_idx = _merge_holdings(candidate)

    if not base_idx and not cand_idx:
        return {
            "available": False,
            "status": "empty",
            "base_file": base_file,
            "candidate_file": candidate_file,
            "reason": "调仓对比数据为空：基准与目标持仓均为空",
        }

    # ── 各侧汇总 ──
    base_total_cost = sum(e["cost"] for e in base_idx.values())
    cand_total_cost = sum(e["cost"] for e in cand_idx.values())
    base_metrics = {
        "total_cost": round(base_total_cost, 2),
        "total_shares": round(sum(e["shares"] for e in base_idx.values()), 2),
        "holding_count": len(base_idx),
        "hhi": _compute_hhi(base_idx),
    }
    cand_metrics = {
        "total_cost": round(cand_total_cost, 2),
        "total_shares": round(sum(e["shares"] for e in cand_idx.values()), 2),
        "holding_count": len(cand_idx),
        "hhi": _compute_hhi(cand_idx),
    }

    # ── 汇总对比行（渲染层直接消费）──
    summary = [
        {
            "key": "total_cost",
            "label": "总成本(元)",
            "unit": "money",
            "base": base_metrics["total_cost"],
            "candidate": cand_metrics["total_cost"],
            "delta": round(cand_metrics["total_cost"] - base_metrics["total_cost"], 2),
            "arrow": _arrow(cand_metrics["total_cost"] - base_metrics["total_cost"]),
        },
        {
            "key": "total_shares",
            "label": "总份额",
            "unit": "shares",
            "base": base_metrics["total_shares"],
            "candidate": cand_metrics["total_shares"],
            "delta": round(cand_metrics["total_shares"] - base_metrics["total_shares"], 2),
            "arrow": _arrow(cand_metrics["total_shares"] - base_metrics["total_shares"]),
        },
        {
            "key": "holding_count",
            "label": "持仓品种数",
            "unit": "count",
            "base": base_metrics["holding_count"],
            "candidate": cand_metrics["holding_count"],
            "delta": cand_metrics["holding_count"] - base_metrics["holding_count"],
            "arrow": _arrow(cand_metrics["holding_count"] - base_metrics["holding_count"]),
        },
        {
            "key": "hhi",
            "label": "持仓集中度 HHI",
            "unit": "hhi",
            "base": base_metrics["hhi"],
            "candidate": cand_metrics["hhi"],
            "delta": round(cand_metrics["hhi"] - base_metrics["hhi"], 6),
            "arrow": _arrow(cand_metrics["hhi"] - base_metrics["hhi"]),
        },
    ]

    # ── 分类配置对比（成本口径权重 %）──
    base_cats = _category_stats(base_idx)
    cand_cats = _category_stats(cand_idx)
    categories: list[dict[str, Any]] = []
    for key in _CATEGORY_ORDER:
        if key not in base_cats and key not in cand_cats:
            continue
        b = base_cats.get(key, {"cost": 0.0, "weight_pct": 0.0})
        c = cand_cats.get(key, {"cost": 0.0, "weight_pct": 0.0})
        categories.append(
            {
                "key": key,
                "label": _CATEGORY_LABELS.get(key, key),
                "base_cost": round(b["cost"], 2),
                "cand_cost": round(c["cost"], 2),
                "base_weight": b["weight_pct"],
                "cand_weight": c["weight_pct"],
                "delta_pct": round(c["weight_pct"] - b["weight_pct"], 2),
            }
        )

    # ── 持仓变动明细 ──
    all_codes = set(base_idx) | set(cand_idx)
    changes: list[dict[str, Any]] = []
    _action_rank = {"新增": 0, "清仓": 1, "加仓": 2, "减仓": 3, "不变": 4}

    for code in all_codes:
        b = base_idx.get(code)
        c = cand_idx.get(code)
        if b is None:
            action = "新增"
            name = c["name"]
        elif c is None:
            action = "清仓"
            name = b["name"]
        else:
            name = c["name"] or b["name"]
            shares_diff = c["shares"] - b["shares"]
            if abs(shares_diff) < _EPS:
                action = "不变"
            elif shares_diff > 0:
                action = "加仓"
            else:
                action = "减仓"

        changes.append(
            {
                "code": code,
                "name": name,
                "action": action,
                "base_shares": round(b["shares"], 2) if b else 0.0,
                "cand_shares": round(c["shares"], 2) if c else 0.0,
                "shares_diff": round((c["shares"] - b["shares"]) if b and c else 0.0, 2),
                "base_cost": round(b["cost"], 2) if b else 0.0,
                "cand_cost": round(c["cost"], 2) if c else 0.0,
                "cost_diff": round((c["cost"] - b["cost"]) if b and c else 0.0, 2),
                "base_weight": round(b["weight"] * 100, 2) if b else 0.0,
                "cand_weight": round(c["weight"] * 100, 2) if c else 0.0,
                "weight_delta_pct": round(((c["weight"] - b["weight"]) * 100) if b and c else 0.0, 2),
            }
        )
    changes.sort(key=lambda r: (_action_rank[r["action"]], r["name"]))

    stats = {a: 0 for a in ("added", "removed", "increased", "decreased", "unchanged")}
    _action_to_stat = {
        "新增": "added",
        "清仓": "removed",
        "加仓": "increased",
        "减仓": "decreased",
        "不变": "unchanged",
    }
    for r in changes:
        stats[_action_to_stat[r["action"]]] += 1

    return {
        "available": True,
        "status": "ok",
        "base_file": base_file,
        "candidate_file": candidate_file,
        "base": base_metrics,
        "candidate": cand_metrics,
        "summary": summary,
        "categories": categories,
        "changes": changes,
        "stats": stats,
        "reason": "",
    }

"""快照差异摘要 — 组合演进章顶部「自上次快照变化摘要」。

对比去重后的最近两次快照，输出数据契约 `snapshot_diff_data`：
  - 新增/移除品种（复用 `fetcher/history_diff.HistoryDiff` 引擎，action=新增/清仓）
  - 集中度 HHI 变化（本期 - 上期；市值口径优先，市值为 0 回退成本口径，
    与 `analysis/portfolio_evolution` 的权重口径一致）
  - 超警戒线品种（当前权重 > 15% 警戒线，与 `analysis/simple_rebalance` 阈值一致）

设计边界（快照不含以下字段，无法派生，不虚构）：
  - 相关性矩阵差异（快照无相关性数据）
  - 行业/穿透结构差异（快照无行业/穿透字段）

数据不足（去重后有效快照 < 2 期，无上次快照可对比）时返回 available=False
的降级 dict，由展示层写入占位文本（§1.4.5 数据降级治理）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.analysis.portfolio_evolution import (
    _compute_hhi,
    _dedup_by_date,
    _format_period_label,
    _holding_weight,
)
from src.python.analysis.simple_rebalance import _THRESHOLD

logger = logging.getLogger("invest")

# 警戒线：单品种权重超过此值判「超限项」（复用 simple_rebalance 的 15% 阈值）
_DEFAULT_THRESHOLD_PCT = _THRESHOLD * 100
# 有效期数下限：去重后不足 2 期无法对比（无上次快照）
_DEFAULT_MIN_SNAPSHOTS = 2


def build_snapshot_diff(
    threshold_pct: float = _DEFAULT_THRESHOLD_PCT,
    min_snapshots: int = _DEFAULT_MIN_SNAPSHOTS,
) -> dict[str, Any]:
    """构建快照差异摘要数据契约 dict。

    从快照目录加载全部快照 → 按日期去重 → 取最近两次对比。

    Args:
        threshold_pct: 超警戒线阈值（%），默认 15.0（与 simple_rebalance 一致）
        min_snapshots: 有效期数下限（默认 2），不足时返回 available=False

    Returns:
        snapshot_diff_data 契约 dict：
          - available: 数据是否充足（去重后有效快照 >= min_snapshots）
          - snapshot_count: 原始快照文件数
          - previous_date / current_date: 上期/最新期展示标签（MM-DD）
          - added / removed: 本期新增/移除品种 [{code, name}]
          - hhi_previous / hhi_current / hhi_change: 集中度 HHI 及变化（本期-上期）
          - over_limit: 当前超警戒线品种 [{code, name, weight_pct, threshold_pct}]
          - summary: 变化摘要文本（渲染层直接展示）
          - reason: available=False 时的降级原因
    """
    from src.python.report.history_snapshot import load_all

    raw = load_all()
    snapshots = _dedup_by_date(raw)

    if len(snapshots) < min_snapshots:
        logger.warning("快照差异：有效快照 %d < 下限 %d，无上次快照可对比", len(snapshots), min_snapshots)
        return _unavailable(len(raw), min_snapshots)

    prev_sd, curr_sd = snapshots[-2], snapshots[-1]

    # 新增/移除品种（复用 HistoryDiff 引擎，action=新增/清仓）
    from src.python.fetcher.history_diff import HistoryDiff

    diff = HistoryDiff.compute(curr_sd, prev_sd)
    added = [{"code": d.code, "name": d.name} for d in diff.added]
    removed = [{"code": d.code, "name": d.name} for d in diff.removed]

    # 集中度 HHI（市值口径优先，市值为 0 回退成本口径；与演进模块同口径）
    hhi_prev = _snapshot_hhi(prev_sd)
    hhi_curr = _snapshot_hhi(curr_sd)
    hhi_change = round(hhi_curr - hhi_prev, 6) if (hhi_prev is not None and hhi_curr is not None) else None

    # 超警戒线品种（当前快照权重 > threshold_pct）
    over_limit = _over_limit_items(curr_sd, threshold_pct)

    summary = _build_summary(added, removed, hhi_prev, hhi_curr, over_limit, threshold_pct)

    return {
        "available": True,
        "snapshot_count": len(raw),
        "previous_date": _format_period_label(prev_sd.timestamp or ""),
        "current_date": _format_period_label(curr_sd.timestamp or ""),
        "added": added,
        "removed": removed,
        "hhi_previous": hhi_prev,
        "hhi_current": hhi_curr,
        "hhi_change": hhi_change,
        "over_limit": over_limit,
        "summary": summary,
        "reason": "",
    }


def _unavailable(snapshot_count: int, min_snapshots: int) -> dict[str, Any]:
    """有效快照不足占位（§1.4.5 数据降级）。"""
    return {
        "available": False,
        "snapshot_count": snapshot_count,
        "previous_date": None,
        "current_date": None,
        "added": [],
        "removed": [],
        "hhi_previous": None,
        "hhi_current": None,
        "hhi_change": None,
        "over_limit": [],
        "summary": "",
        "reason": f"快照差异不足：有效快照 < {min_snapshots} 期，无上次快照可对比，变化摘要待积累",
    }


def _snapshot_hhi(sd: Any) -> float | None:
    """计算单个快照的 HHI 集中度（全部账户持仓聚合）。

    市值为 0（旧快照）时回退成本口径；无任何有效权重时返回 None（该期不参与对比）。

    Returns:
        HHI 值（0~1）或 None（无有效权重）
    """
    all_holdings = [h for acc in sd.accounts for h in (getattr(acc, "holdings", ()) or ())]
    weights = [_holding_weight(h, sd.total_value or 0.0, sd.total_cost or 0.0) for h in all_holdings]
    if weights and any(w > 0 for w in weights):
        return _compute_hhi(weights)
    return None


def _over_limit_items(sd: Any, threshold_pct: float) -> list[dict[str, Any]]:
    """当前快照中权重超过警戒线的品种列表（按权重降序）。

    Args:
        sd: 最新快照 SnapshotData
        threshold_pct: 警戒线阈值（%）

    Returns:
        [{code, name, weight_pct, threshold_pct}]，超限品种为空时返回空列表
    """
    out: list[dict[str, Any]] = []
    total_mv = sd.total_value or 0.0
    total_cost = sd.total_cost or 0.0
    for acc in sd.accounts:
        for h in getattr(acc, "holdings", ()) or ():
            weight_pct = round(_holding_weight(h, total_mv, total_cost) * 100, 2)
            if weight_pct > threshold_pct:
                out.append(
                    {
                        "code": h.code,
                        "name": h.name,
                        "weight_pct": weight_pct,
                        "threshold_pct": threshold_pct,
                    }
                )
    out.sort(key=lambda x: -x["weight_pct"])
    return out


def _build_summary(
    added: list[dict[str, Any]],
    removed: list[dict[str, Any]],
    hhi_prev: float | None,
    hhi_curr: float | None,
    over_limit: list[dict[str, Any]],
    threshold_pct: float,
) -> str:
    """汇总变化点成一段可读摘要文本。"""
    parts: list[str] = []
    if added:
        parts.append(f"新增 {len(added)} 个品种：{'、'.join(d['name'] or d['code'] for d in added)}")
    if removed:
        parts.append(f"移除 {len(removed)} 个品种：{'、'.join(d['name'] or d['code'] for d in removed)}")

    if over_limit:
        names = "、".join(f"{o['name'] or o['code']}（{o['weight_pct']}%）" for o in over_limit)
        parts.append(f"超 {threshold_pct:.0f}% 警戒线品种 {len(over_limit)} 个：{names}")

    if hhi_prev is not None and hhi_curr is not None:
        delta = hhi_curr - hhi_prev
        if delta > 1e-6:
            direction = "更集中"
        elif delta < -1e-6:
            direction = "更分散"
        else:
            direction = "持平"
        parts.append(f"集中度 HHI {hhi_prev:.4f} → {hhi_curr:.4f}（{direction}）")

    # 无新增/移除/超限项，且 HHI 不可比时（如全部权重无效）→ 明确"无变化"
    if not parts:
        parts.append("与上次快照相比持仓结构无变化")
    return "；".join(parts) + "。"

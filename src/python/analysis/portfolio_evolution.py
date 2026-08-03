"""组合演进分析 — 多快照趋势聚合。

聚合 `data/history/snapshots/` 下已持久化的多期持仓快照，输出组合
演进趋势数据（C19 契约 `evolution_data`），供 HTML「组合演进」章节
与 Excel 页签消费。

可派生指标（快照字段内计算，无新数据源依赖）：
  - 总市值趋势：各快照 top-level `total_value`（另含总成本/总盈亏/持仓数）
  - 账户配置流：各账户市值占比（快照含 accounts 结构，未来多账户时自动生效）
  - 集中度 HHI 趋势：Σ(持仓权重²)，权重优先用市值，市值为 0 时回退成本口径
  - TOP 持仓占比变迁：各期持仓市值（或成本）权重前 N 名的变化

设计边界（快照不含以下字段，无法派生，不虚构）：
  - 行业配置流（快照无行业归属字段）
  - 穿透 TOP10 变迁（快照无穿透数据）
  - 量化指标趋势（快照无夏普/波动率等指标）

数据不足（去重后有效期数 < min_snapshots）时返回 `available=False`
的降级 dict，由展示层写入占位文本（§1.4.5 数据降级治理）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("invest")

# 有效期数下限：快照去重后不足该值视为数据不足（占位展示）
_DEFAULT_MIN_SNAPSHOTS = 3
# TOP 持仓变迁展示数量上限
_DEFAULT_TOP_N = 10


def _holding_weight(h: Any, total_mv: float, total_cost: float) -> float:
    """计算单个持仓的权重。

    优先用市值口径（total_mv > 0 时），否则回退成本口径（total_cost > 0 时），
    两者皆不可用时返回 0（该期不参与集中度/TOP 变迁计算）。

    Args:
        h: SnapshotHolding（含 market_value / cost_total 字段）
        total_mv: 该快照总市值
        total_cost: 该快照总成本

    Returns:
        权重（0~1 浮点数）
    """
    mv = getattr(h, "market_value", 0.0) or 0.0
    cost = getattr(h, "cost_total", 0.0) or 0.0
    if total_mv > 0 and mv > 0:
        return mv / total_mv
    if total_cost > 0 and cost > 0:
        return cost / total_cost
    return 0.0


def _compute_hhi(weights: list[float]) -> float:
    """计算 HHI 集中度 = Σ(权重²)。

    Args:
        weights: 该期全部持仓权重列表

    Returns:
        HHI 值（0~1），无有效权重时返回 0.0
    """
    return round(sum(w * w for w in weights), 6)


def _dedup_by_date(snapshots: list[Any]) -> list[Any]:
    """按日期去重：同一自然日保留当天最后一个快照（时间戳最新）。

    真实运行中一天内可能多次生成报告，按日聚合使趋势线更有意义。

    Args:
        snapshots: 按时间戳升序的 SnapshotData 列表

    Returns:
        按日期去重后的列表（每日取最后一个，保持升序）
    """
    by_date: dict[str, Any] = {}
    for sd in snapshots:
        date_key = (sd.timestamp or "")[:8]  # YYYYMMDD
        if not date_key:
            continue
        by_date[date_key] = sd  # 升序遍历，后者覆盖前者 → 保留当天最后
    return [by_date[k] for k in sorted(by_date)]


def _format_period_label(ts: str) -> str:
    """将快照时间戳格式化为展示标签（MM-DD）。

    Args:
        ts: 快照时间戳（YYYYMMDDTHHMMSS）

    Returns:
        展示标签；时间戳异常时原样返回
    """
    if len(ts) >= 10:
        return f"{ts[4:6]}-{ts[6:8]}"
    return ts


def build_evolution_data(
    min_snapshots: int = _DEFAULT_MIN_SNAPSHOTS,
    top_n: int = _DEFAULT_TOP_N,
) -> dict[str, Any]:
    """构建组合演进 C19 契约 dict。

    从快照目录加载全部快照 → 按日期去重 → 派生各趋势序列。

    Args:
        min_snapshots: 有效期数下限（默认 3），不足时返回 available=False
        top_n: TOP 持仓变迁展示数量上限（默认 10）

    Returns:
        evolution_data 契约 dict：
          - available: 数据是否充足
          - snapshot_count: 原始快照文件数
          - periods: 去重后各期展示标签（MM-DD）
          - total_value / total_cost / total_pnl / holding_counts: 各期趋势
          - account_flows: {账户名: [占比% 序列]}，市值口径
          - hhi: HHI 集中度序列（None 表示该期无有效权重）
          - top_holdings: [{code, name, weights:[各期占比%], present_count}] 按末期权重降序
          - reason: available=False 时的降级原因
    """
    from src.python.report.history_snapshot import load_all

    raw = load_all()
    snapshots = _dedup_by_date(raw)
    count = len(snapshots)

    if count < min_snapshots:
        return {
            "available": False,
            "snapshot_count": len(raw),
            "min_snapshots": min_snapshots,
            "periods": [],
            "total_value": [],
            "total_cost": [],
            "total_pnl": [],
            "holding_counts": [],
            "account_flows": {},
            "hhi": [],
            "top_holdings": [],
            "reason": f"组合演进快照不足：有效期数 {count} < 下限 {min_snapshots}，趋势数据待积累",
        }

    periods: list[str] = []
    total_value: list[float] = []
    total_cost: list[float] = []
    total_pnl: list[float] = []
    holding_counts: list[int] = []
    hhi: list[float | None] = []
    account_flows: dict[str, list[float]] = {}

    # 全部持仓（跨期）→ {code: (name, [各期权重%])}
    holding_series: dict[str, tuple[str, list[float]]] = {}

    for idx, sd in enumerate(snapshots):
        periods.append(_format_period_label(sd.timestamp or ""))
        total_value.append(round(sd.total_value or 0.0, 2))
        total_cost.append(round(sd.total_cost or 0.0, 2))
        total_pnl.append(round(sd.total_pnl or 0.0, 2))

        # 汇总全部账户持仓
        all_holdings: list[Any] = []
        per_account: list[tuple[str, list[Any]]] = []
        account_value: list[float] = []
        for acc in sd.accounts:
            hs = list(getattr(acc, "holdings", ()) or ())
            all_holdings.extend(hs)
            per_account.append((getattr(acc, "account_name", ""), hs))
            account_value.append(sum(getattr(h, "market_value", 0.0) or 0.0 for h in hs))

        holding_counts.append(len(all_holdings))

        # 账户配置流（市值口径占比 %）
        _acct_total = sum(account_value)
        if _acct_total > 0:
            for (name, _hs), av in zip(per_account, account_value):
                account_flows.setdefault(name or "全部", []).append(round(av / _acct_total * 100, 2))
        else:
            # 市值为 0（旧快照）时用成本口径
            _acct_cost_total = sum(sum(getattr(h, "cost_total", 0.0) or 0.0 for h in hs) for _n, hs in per_account)
            if _acct_cost_total > 0:
                for (name, hs), _av in zip(per_account, account_value):
                    _cv = sum(getattr(h, "cost_total", 0.0) or 0.0 for h in hs)
                    account_flows.setdefault(name or "全部", []).append(round(_cv / _acct_cost_total * 100, 2))

        # 集中度 HHI + TOP 持仓权重
        _tot_mv = sd.total_value or 0.0
        _tot_cost = sd.total_cost or 0.0
        weights = [_holding_weight(h, _tot_mv, _tot_cost) for h in all_holdings]
        if weights and any(w > 0 for w in weights):
            hhi.append(_compute_hhi(weights))
        else:
            hhi.append(None)

        for h in all_holdings:
            code = getattr(h, "code", "")
            if not code:
                continue
            w = _holding_weight(h, _tot_mv, _tot_cost)
            # 按期索引写入权重；未持有的期已预填 0%（跨期缺失 → 0）
            if code not in holding_series:
                holding_series[code] = (getattr(h, "name", "") or code, [0.0] * count)
            holding_series[code][1][idx] = round(w * 100, 2)

    # TOP 持仓变迁：按末期权重降序取前 N
    top_holdings: list[dict[str, Any]] = []
    _ordered = sorted(
        holding_series.items(),
        key=lambda kv: kv[1][1][-1] if kv[1][1] else 0.0,
        reverse=True,
    )
    for code, (name, series) in _ordered[:top_n]:
        top_holdings.append(
            {
                "code": code,
                "name": name,
                "weights": series,
                "present_count": sum(1 for w in series if w > 0),
            }
        )

    return {
        "available": True,
        "snapshot_count": len(raw),
        "min_snapshots": min_snapshots,
        "periods": periods,
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "holding_counts": holding_counts,
        "account_flows": account_flows,
        "hhi": hhi,
        "top_holdings": top_holdings,
        "reason": "",
    }

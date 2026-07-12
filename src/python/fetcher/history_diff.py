"""F1 差异计算引擎：HistoryDiff.compute(new, old) → DiffSummary。

比较新旧两份 SnapshotData，识别组合级 Δ 值和持仓级变动。

差异类型：
  组合级 — 总市值 Δ、总盈亏 Δ、总盈亏率 Δ
  持仓级 — 新增/清仓/加仓/减仓/不变
  基准日 — days_since_last_report（距上次报告天数）

用例覆盖（验收标准 —— 7 用例）：
  1. 首次运行（无旧快照）→ is_first_check=True
  2. 无变化 → 全空 diff
  3. 新增持仓
  4. 清仓持仓
  5. 加仓
  6. 减仓
  7. 基准日对齐
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.python.schemas.history import (
    AccountSnapshot,
    DiffSummary,
    HoldingDiff,
    SnapshotData,
    SnapshotHolding,
)

logger = logging.getLogger("invest")

# ── 公开 API ────────────────────────────────────────────────


class HistoryDiff:
    """差异计算引擎。仅含类方法，无状态。"""

    @classmethod
    def compute(cls, new: SnapshotData, old: SnapshotData | None) -> DiffSummary:
        """计算新旧快照之间的差异。

        Args:
            new: 本次报告的快照数据
            old: 上次报告的快照数据（None = 首次运行）

        Returns:
            DiffSummary 差异摘要。
            首次运行（old=None）时 is_first_check=True，其余字段为默认值。
        """
        if old is None:
            return DiffSummary(is_first_check=True)

        # 1) 组合级 Δ
        total_value_diff = new.total_value - old.total_value
        total_value_diff_pct = (
            (total_value_diff / old.total_value * 100)
            if old.total_value != 0
            else 0.0
        )
        total_pnl_diff = new.total_pnl - old.total_pnl

        # 2) 基准日对齐
        days_since_last = cls._compute_days_since(new.timestamp, old.timestamp)

        # 3) 持仓级 Δ（按 code 合并索引）
        new_holdings = cls._index_holdings(new)
        old_holdings = cls._index_holdings(old)

        all_codes = set(new_holdings.keys()) | set(old_holdings.keys())

        added: list[HoldingDiff] = []
        removed: list[HoldingDiff] = []
        increased: list[HoldingDiff] = []
        decreased: list[HoldingDiff] = []

        for code in sorted(all_codes):
            new_h = new_holdings.get(code)
            old_h = old_holdings.get(code)

            if new_h and not old_h:
                added.append(HoldingDiff(
                    code=code,
                    name=new_h.name,
                    action="新增",
                    shares_diff=new_h.shares,
                    value_diff=new_h.market_value,
                    pnl_diff=new_h.total_pnl,
                ))
            elif old_h and not new_h:
                removed.append(HoldingDiff(
                    code=code,
                    name=old_h.name,
                    action="清仓",
                    shares_diff=-old_h.shares,
                    value_diff=-old_h.market_value,
                    pnl_diff=-old_h.total_pnl,
                ))
            elif new_h and old_h:
                shares_diff = new_h.shares - old_h.shares
                value_diff = new_h.market_value - old_h.market_value
                pnl_diff = new_h.total_pnl - old_h.total_pnl
                pnl_rate_diff = 0.0
                if old_h.cost_total > 0 and new_h.cost_total > 0:
                    old_rate = old_h.total_pnl / old_h.cost_total * 100
                    new_rate = new_h.total_pnl / new_h.cost_total * 100
                    pnl_rate_diff = round(new_rate - old_rate, 2)

                if abs(shares_diff) < 0.001:
                    action = "不变"
                elif shares_diff > 0:
                    action = "加仓"
                else:
                    action = "减仓"

                diff = HoldingDiff(
                    code=code,
                    name=new_h.name,
                    action=action,
                    shares_diff=round(shares_diff, 4),
                    value_diff=round(value_diff, 2),
                    pnl_diff=round(pnl_diff, 2),
                    pnl_rate_diff=pnl_rate_diff,
                )
                if action == "加仓":
                    increased.append(diff)
                elif action == "减仓":
                    decreased.append(diff)

        return DiffSummary(
            total_value_diff=round(total_value_diff, 2),
            total_value_diff_pct=round(total_value_diff_pct, 4),
            total_pnl_diff=round(total_pnl_diff, 2),
            days_since_last_report=days_since_last,
            added=tuple(added),
            removed=tuple(removed),
            increased=tuple(increased),
            decreased=tuple(decreased),
            is_first_check=False,
        )

    # ── 辅助方法 ─────────────────────────────────────────

    @staticmethod
    def _index_holdings(sd: SnapshotData) -> dict[str, SnapshotHolding]:
        """将快照中所有账户的持仓按 code 合并索引。

        同一 code 出现在多个账户时，份额/市值/盈亏累加。
        """
        merged: dict[str, SnapshotHolding] = {}
        for account in sd.accounts:
            for h in account.holdings:
                if h.code in merged:
                    existing = merged[h.code]
                    merged[h.code] = SnapshotHolding(
                        code=h.code,
                        name=h.name or existing.name,
                        shares=existing.shares + h.shares,
                        cost_price=(
                            (existing.cost_price * existing.shares + h.cost_price * h.shares)
                            / (existing.shares + h.shares)
                            if (existing.shares + h.shares) > 0
                            else 0.0
                        ),
                        market_value=existing.market_value + h.market_value,
                        daily_pnl=existing.daily_pnl + h.daily_pnl,
                        total_pnl=existing.total_pnl + h.total_pnl,
                        cost_total=existing.cost_total + h.cost_total,
                    )
                else:
                    merged[h.code] = h
        return merged

    @staticmethod
    def _compute_days_since(new_ts: str, old_ts: str) -> int:
        """计算新旧快照之间的天数。

        支持 ISO 格式时间戳（如 "2026-07-12T14:30:00"）和
        紧凑格式（如 "20260712T143000"）。
        解析失败时返回 0。

        Returns:
            int 天数（向下取整），至少 1
        """
        ts1 = _parse_timestamp(new_ts)
        ts2 = _parse_timestamp(old_ts)
        if ts1 is None or ts2 is None:
            return 0
        delta = (ts1 - ts2).days
        return max(1, delta)


def _parse_timestamp(ts: str) -> datetime | None:
    """尝试解析多种时间戳格式。"""
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%dT%H%M%S",
        "%Y-%m-%d",
        "%Y%m%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None

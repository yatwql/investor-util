"""快照差异摘要模块边缘场景测试 — 异常/极端值。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。

覆盖：
  - 快照目录为空（0 份）→ available=False
  - 空持仓快照 → 不崩溃，摘要报告"无变化"
  - 全部权重为 0（市值/成本均不可用）→ 无除零错误
  - 阈值边界：threshold_pct=0 → 所有权重 > 0 的品种判超限
  - 损坏快照文件自动跳过
  - 多账户超限项跨账户聚合
"""

from __future__ import annotations

import json
import os

import pytest

from src.python.analysis.snapshot_diff import build_snapshot_diff
from src.python.core.constants import HISTORY_SNAPSHOT_DIR
from src.python.report.history_snapshot import save
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


def _holding(code: str, name: str, mv: float, cost: float) -> SnapshotHolding:
    return SnapshotHolding(
        code=code,
        name=name,
        shares=0.0,
        cost_price=0.0,
        market_value=mv,
        daily_pnl=0.0,
        total_pnl=0.0,
        cost_total=cost,
    )


def _save(ts: str, holdings: list[SnapshotHolding], account: str = "全部") -> None:
    sd = SnapshotData(
        accounts=(AccountSnapshot(account_name=account, holdings=tuple(holdings)),),
        total_value=sum(h.market_value for h in holdings),
        total_cost=sum(h.cost_total for h in holdings),
        total_pnl=sum(h.total_pnl for h in holdings),
        timestamp=ts,
    )
    save(sd)


def _save_multi_account(ts: str, accounts: list[tuple[str, list[SnapshotHolding]]]) -> None:
    sd = SnapshotData(
        accounts=tuple(AccountSnapshot(account_name=n, holdings=tuple(hs)) for n, hs in accounts),
        total_value=sum(h.market_value for _n, hs in accounts for h in hs),
        total_cost=sum(h.cost_total for _n, hs in accounts for h in hs),
        total_pnl=0.0,
        timestamp=ts,
    )
    save(sd)


# ── 空目录 / 空持仓 ───────────────────────────────────────


def test_no_snapshots_returns_unavailable():
    """快照目录无任何文件 → available=False，不崩溃。"""
    data = build_snapshot_diff()
    assert data["available"] is False
    assert data["snapshot_count"] == 0
    assert data["reason"]


def test_empty_holdings_snapshot_no_crash():
    """两期均为空持仓 → 不崩溃，摘要报告"无变化"。"""
    _save("20260701T090000", [])
    _save("20260702T090000", [])
    data = build_snapshot_diff()
    assert data["available"] is True
    assert data["hhi_previous"] is None
    assert data["hhi_change"] is None
    assert data["over_limit"] == []
    assert "无变化" in data["summary"]


# ── 权重不可用（防除零） ───────────────────────────────────


def test_totals_zero_no_division_error():
    """市值/成本均为 0 → 权重全 0，不抛除零错误。"""
    _save("20260701T090000", [_holding("A", "A基金", 0, 0), _holding("B", "B基金", 0, 0)])
    _save("20260702T090000", [_holding("A", "A基金", 0, 0), _holding("B", "B基金", 0, 0)])
    data = build_snapshot_diff()
    assert data["available"] is True
    assert data["hhi_previous"] is None
    assert data["hhi_current"] is None
    assert data["over_limit"] == []
    assert "无变化" in data["summary"]


# ── 阈值边界 ──────────────────────────────────────────────


def test_zero_threshold_flags_all_holdings():
    """threshold_pct=0 → 所有权重 > 0 的品种均判超限。"""
    _save("20260701T090000", [_holding("A", "A基金", 7000, 1000), _holding("B", "B基金", 3000, 1000)])
    _save("20260702T090000", [_holding("A", "A基金", 7000, 1000), _holding("B", "B基金", 3000, 1000)])
    data = build_snapshot_diff(threshold_pct=0.0)
    assert {o["code"] for o in data["over_limit"]} == {"A", "B"}
    assert data["over_limit"][0]["threshold_pct"] == 0.0


# ── 损坏文件容错 ──────────────────────────────────────────


def test_corrupt_snapshot_file_skipped():
    """目录含损坏 JSON 文件 → 自动跳过，仅统计有效快照。"""
    os.makedirs(HISTORY_SNAPSHOT_DIR, exist_ok=True)
    with open(os.path.join(HISTORY_SNAPSHOT_DIR, "snapshot_corrupt.json"), "w", encoding="utf-8") as f:
        f.write("{ not valid json ")
    _save("20260701T090000", [_holding("A", "A基金", 5000, 4000)])
    data = build_snapshot_diff()
    # 损坏文件被跳过 → 仅 1 份有效快照，无上次可对比
    assert data["available"] is False
    assert data["snapshot_count"] == 1
    assert "快照差异不足" in data["reason"]


# ── 多账户聚合 ────────────────────────────────────────────


def test_multi_account_over_limit_aggregation():
    """跨账户超限品种聚合进同一列表，按权重降序。"""
    _save_multi_account(
        "20260701T090000",
        [("账户A", [_holding("A", "A基金", 5000, 4000), _holding("B", "B基金", 5000, 4000)])],
    )
    _save_multi_account(
        "20260702T090000",
        [
            ("账户A", [_holding("A", "A基金", 1800, 1000)]),
            ("账户B", [_holding("B", "B基金", 8200, 1000)]),
        ],
    )
    data = build_snapshot_diff()
    over = data["over_limit"]
    assert [o["code"] for o in over] == ["B", "A"]
    assert over[0]["weight_pct"] == 82.0

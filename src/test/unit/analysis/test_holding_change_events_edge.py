"""持仓变动事件抽取边缘场景测试 — 异常/极端值。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。

覆盖：
  - 有效快照 < 2 期（0 期 / 1 期）→ available=False 占位不抛异常
  - min_periods=0 且空输入 → 契约字段齐全、窗口为 None
  - 份额字段 NaN（非有限值）→ 事件标「不可判定」、份额字段置 None、
    不被差异引擎误判方向（NaN 在比较运算中恒为 False，缺防会静默归入减仓）
  - 全部持仓份额非法但市值无变化 → 不出事件（无可判定事实）
  - 空时间戳快照被按日去重剔除（不产生空 date_key 期）
  - 无事件但期数达标 → available=True、events 为空列表（非降级）
"""

from __future__ import annotations

import pytest

from src.python.analysis.holding_change_events import extract_change_events
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


def _snap(ts: str, holdings: list[SnapshotHolding]) -> SnapshotData:
    return SnapshotData(
        accounts=(AccountSnapshot(account_name="全部", holdings=tuple(holdings)),),
        total_value=0.0,
        total_cost=0.0,
        total_pnl=0.0,
        timestamp=ts,
    )


def _h(code: str, shares: float, price: float) -> SnapshotHolding:
    return SnapshotHolding(
        code=code,
        name=f"{code}基金",
        shares=shares,
        cost_price=price,
        market_value=shares * price,  # shares=NaN 时自然得 NaN（非有限 → 不可判定）
        daily_pnl=0.0,
        total_pnl=0.0,
        cost_total=0.0,
    )


def test_zero_snapshots_unavailable_placeholder():
    """0 期 → available=False 占位，不抛异常。"""
    data = extract_change_events([])
    assert data["available"] is False
    assert data["events"] == []
    assert "快照不足" in data["reason"]
    assert data["window_start"] is None
    assert data["window_end"] is None


def test_single_snapshot_unavailable_placeholder():
    """1 期（无上次快照可差分）→ available=False 占位。"""
    data = extract_change_events([_snap("20260105T090000", [_h("A", 1000, 10)])])
    assert data["available"] is False
    assert data["period_count"] == 1
    assert data["event_count"] == 0


def test_min_periods_zero_empty_input_contract_complete():
    """min_periods=0 且空输入 → available=True 但窗口字段为 None（不 IndexError）。"""
    data = extract_change_events([], min_periods=0)
    assert data["available"] is True
    assert data["period_count"] == 0
    assert data["window_start"] is None
    assert data["window_end"] is None
    assert data["events"] == []


def test_non_finite_shares_marked_indeterminate_not_direction():
    """份额 NaN + 市值变化 → 「不可判定」事件（shares_diff=None），不误判为减仓。"""
    seq = [
        _snap("20260105T090000", [_h("A", 1000, 10)]),
        _snap(
            "20260106T090000",
            [SnapshotHolding(code="A", name="A基金", shares=float("nan"), cost_price=10.0, market_value=12000.0)],
        ),
    ]
    data = extract_change_events(seq)
    assert data["available"] is True
    assert data["event_count"] == 1
    assert data["indeterminate_count"] == 1
    event = data["events"][0]
    assert event["action"] == "不可判定"
    assert event["indeterminate"] is True
    assert event["shares_diff"] is None
    assert event["shares_after"] is None
    assert event["shares_before"] == 1000.0
    assert event["value_diff"] == 2000.0


def test_non_finite_shares_without_value_change_emits_no_event():
    """份额非法且市值两侧均不可知 → 无可判定事实，不出事件。"""
    seq = [
        _snap(
            "20260105T090000",
            [SnapshotHolding(code="A", name="A基金", shares=float("nan"), cost_price=0.0, market_value=float("nan"))],
        ),
        _snap(
            "20260106T090000",
            [SnapshotHolding(code="A", name="A基金", shares=float("nan"), cost_price=0.0, market_value=float("nan"))],
        ),
    ]
    data = extract_change_events(seq)
    assert data["available"] is True
    assert data["events"] == []
    assert data["indeterminate_count"] == 0


def test_empty_timestamp_snapshots_excluded_by_dedup():
    """时间戳为空的快照无 date_key，按日去重剔除（期数不计入、不参与差分）。"""
    seq = [
        _snap("", [_h("A", 1000, 10)]),
        _snap("20260105T090000", [_h("A", 1000, 10)]),
        _snap("20260106T090000", [_h("A", 800, 10)]),
    ]
    data = extract_change_events(seq)
    assert data["period_count"] == 2
    assert "" not in data["period_timestamps"]
    assert data["event_count"] == 1


def test_periods_ok_but_no_changes_returns_empty_events_not_degraded():
    """期数达标但全程无变动 → available=True、events=[]（空事件非降级）。"""
    seq = [
        _snap("20260105T090000", [_h("A", 1000, 10)]),
        _snap("20260106T090000", [_h("A", 1000, 10)]),
        _snap("20260107T090000", [_h("A", 1000, 10)]),
    ]
    data = extract_change_events(seq)
    assert data["available"] is True
    assert data["period_count"] == 3
    assert data["events"] == []
    assert data["reason"] == ""

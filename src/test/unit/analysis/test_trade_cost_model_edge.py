"""调仓交易成本模型边缘/降级用例（@pytest.mark.edge 独立文件）。

覆盖：空输入/无效时间戳/NaN 与倒挂金额/坏表/计数器异常返回/固定费档缺
source/持有期截止缺失等降级路径——一律不抛、不猜、降级留 None。
"""

from __future__ import annotations

import math

import pytest

from src.python.analysis.fee_schedule_model import (
    SRC_UNKNOWN,
    parse_purchase_fee_schedule,
    parse_redemption_fee_schedule,
    purchase_fee,
    select_redemption_tier,
)
from src.python.analysis.trade_cost_model import compute_trade_costs, rebuild_position_lots
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


def _h(code: str, shares, price: float = 10.0) -> SnapshotHolding:
    return SnapshotHolding(
        code=code,
        name=f"{code}基金",
        shares=shares,
        cost_price=price,
        market_value=(shares or 0.0) * price,
        daily_pnl=0.0,
        total_pnl=0.0,
        cost_total=(shares or 0.0) * price,
    )


def _snap(ts: str, holdings: list[SnapshotHolding]) -> SnapshotData:
    return SnapshotData(
        accounts=(AccountSnapshot(account_name="全部", holdings=tuple(holdings)),),
        total_value=0.0,
        total_cost=0.0,
        total_pnl=0.0,
        timestamp=ts,
    )


def _rows() -> list[list[str]]:
    return [
        ["小于7天", "1.50%"],
        ["大于等于7天，小于30天", "0.75%"],
        ["大于等于30天，小于365天", "0.50%"],
        ["大于等于365天，小于730天", "0.25%"],
        ["大于等于730天", "0.00%"],
    ]


def _change(code: str, action: str, base: tuple, cand: tuple) -> dict:
    return {
        "code": code,
        "name": code,
        "action": action,
        "base_shares": base[0],
        "base_cost": base[1],
        "cand_shares": cand[0],
        "cand_cost": cand[1],
    }


def test_rebuild_invalid_timestamps_skipped():
    """时间戳无效 → 该期跳过 → 无批次（不抛、不猜日期）。"""
    snap = _snap("bad-ts", [_h("A", 1000.0)])
    assert rebuild_position_lots([snap]) == {}
    assert rebuild_position_lots([_snap("", [_h("A", 1000.0)])]) == {}


def test_rebuild_iso_timestamp_supported():
    """ISO 形态时间戳（YYYY-MM-DD…）亦可解析出日期批次。"""
    lots = rebuild_position_lots([_snap("2026-01-05T09:00:00", [_h("A", 1000.0)])])
    assert lots["A"] == [{"start_date": "2026-01-05", "shares": 1000.0}]


def test_empty_changes_contract():
    """无变动输入 → 空契约（字段全量、reason 非空）。"""
    res = compute_trade_costs([])
    assert res["available"] is False and res["reason"]
    assert res["legs"] == [] and res["total_cost"] == 0.0
    assert res["unknown_legs"] == 0 and res["unmodeled_legs"] == 0
    assert res["notes"] == []


def test_nan_amount_yields_unknown_fee():
    """NaN 成本 → 金额非有限 → 档位无命中 → 费率未知（不抛、不冒充 0）。"""
    res = compute_trade_costs(
        [_change("N", "新增", (0.0, 0.0), (100.0, float("nan")))],
        fee_index={
            "N": {"purchase": parse_purchase_fee_schedule([["小于10万元", "1.00%"], ["大于等于10万元", "0.00%"]])}
        },
        effective_date="2026-10-05",
    )
    assert res["legs"][0]["fee"] is None
    assert res["legs"][0]["rate_source"] == SRC_UNKNOWN
    assert res["fees_complete"] is False


def test_negative_cost_increase_clamped_to_zero():
    """加仓但成本减量为负（数据倒挂）→ 金额钳 0、fee=0 已知、不抛。"""
    s = parse_purchase_fee_schedule([["小于10万元", "1.00%"], ["大于等于10万元", "0.00%"]])
    res = compute_trade_costs(
        [_change("N", "加仓", (100.0, 5000.0), (200.0, 3000.0))],
        fee_index={"N": {"purchase": s}},
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["amount"] == 0.0 and leg["fee"] == 0.0
    assert res["fees_complete"] is True


def test_counter_returning_none_yields_unknown():
    """交易日计数返回 None（日历加载失败）→ 卖出腿费率未知。"""
    res = compute_trade_costs(
        [_change("A", "清仓", (100.0, 1000.0), (0.0, 0.0))],
        fee_index={"A": {"redemption": parse_redemption_fee_schedule(_rows())}},
        lots_by_code={"A": [{"start_date": "2026-06-01", "shares": 100.0}]},
        count_trading_days=lambda _s, _e: None,
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["fee"] is None and leg["holding_days"] is None
    assert leg["rate_source"] == SRC_UNKNOWN
    assert any("费率来源缺失" in note for note in res["notes"])


def test_counter_negative_days_yields_unknown():
    """计数为负（起止倒挂）→ 档位无命中 → 未知。"""
    res = compute_trade_costs(
        [_change("A", "清仓", (100.0, 1000.0), (0.0, 0.0))],
        fee_index={"A": {"redemption": parse_redemption_fee_schedule(_rows())}},
        lots_by_code={"A": [{"start_date": "2026-06-01", "shares": 100.0}]},
        count_trading_days=lambda _s, _e: -5,
        effective_date="2026-10-05",
    )
    assert res["legs"][0]["fee"] is None
    assert res["fees_complete"] is False


def test_malformed_schedule_mapping_is_unknown():
    """费率表缺 tiers 键（坏数据注入）→ 选档无命中 → 未知，不抛。"""
    assert select_redemption_tier({"tiers": "oops"}, 10) is None
    assert select_redemption_tier(None, 10) is None
    assert select_redemption_tier(parse_redemption_fee_schedule(_rows()), None) is None
    res = compute_trade_costs(
        [_change("A", "清仓", (100.0, 1000.0), (0.0, 0.0))],
        fee_index={"A": {"redemption": {"tiers": "oops"}}},
        lots_by_code={"A": [{"start_date": "2026-06-01", "shares": 100.0}]},
        count_trading_days=lambda _s, _e: 10,
        effective_date="2026-10-05",
    )
    assert res["legs"][0]["fee"] is None


def test_missing_hold_end_note_when_no_effective_date():
    """无生效日也无截止日 → 卖出腿未知 + 「未指定生效日」标注。"""
    res = compute_trade_costs(
        [_change("A", "清仓", (100.0, 1000.0), (0.0, 0.0))],
        fee_index={"A": {"redemption": parse_redemption_fee_schedule(_rows())}},
        lots_by_code={"A": [{"start_date": "2026-06-01", "shares": 100.0}]},
        count_trading_days=lambda _s, _e: 10,
    )
    joined = " ".join(res["notes"])
    assert res["legs"][0]["fee"] is None
    assert "未指定生效日" in joined
    assert "未指定生效日且无持有期截止日" in joined


def test_broken_fee_rows_all_reject():
    """全类坏行（列不足/区间倒置/非费率/缺口）→ 解析一律 None。"""
    assert parse_redemption_fee_schedule([]) is None
    assert parse_redemption_fee_schedule([["小于7天"]]) is None
    assert parse_redemption_fee_schedule([["小于7天", "免"]]) is None
    assert parse_redemption_fee_schedule([["大于等于30天，小于7天", "1.5%"], ["大于等于30天", "0.0%"]]) is None
    assert parse_redemption_fee_schedule([["小于7天", "1.5%"], ["大于等于30天", "0.5%"]]) is None
    assert parse_purchase_fee_schedule([]) is None
    assert parse_purchase_fee_schedule([["x"]]) is None
    assert parse_purchase_fee_schedule([["大于等于500万元，小于100万元", "1.0%"], ["大于等于1000万元", "0.0%"]]) is None


def test_purchase_flat_fee_with_nbsp_entity():
    """单元格含 &nbsp; 实体 → 空白归一后仍取到每笔固定费。"""
    s = parse_purchase_fee_schedule([["小于1000万元", "1.00%"], ["大于等于1000万元", "每笔&nbsp;1000&nbsp;元"]])
    assert s is not None
    assert purchase_fee(20_000_000.0, s) == (1000.0, s["tiers"][1])
    assert purchase_fee(1_000_000.0, s) == (10_000.0, s["tiers"][0])  # 1000万×1%


def test_nan_shares_snapshot_does_not_crash():
    """快照 shares=NaN → 非有限 → 沿用上期份额，批次不被误消耗。"""
    snaps = [
        _snap("20260105T090000", [_h("A", 1000.0)]),
        _snap("20260112T090000", [_h("A", float("nan"))]),
    ]
    lots = rebuild_position_lots(snaps)
    assert lots["A"] == [{"start_date": "2026-01-05", "shares": 1000.0}]


def test_unmodeled_only_changes_still_available():
    """全部腿为场内未建模 → available=True、费用 0、未知 0（未建模≠未知）。"""
    res = compute_trade_costs(
        [_change("600900", "清仓", (1000.0, 8000.0), (0.0, 0.0))],
        effective_date="2026-10-05",
        unmodeled_codes={"600900"},
    )
    assert res["available"] is True
    assert res["total_cost"] == 0.0 and res["unknown_legs"] == 0
    assert res["unmodeled_legs"] == 1 and res["fees_complete"] is True
    assert not any(math.isnan(v) for v in (res["purchase_total"], res["redemption_total"], res["total_cost"]))

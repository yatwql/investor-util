"""调仓交易成本模型（trade_cost_model）纯计算测试 — 口径与手算对照。

覆盖（对应验收条目）：
  - 赎回费档位解析（来源实测标签全形态）与边界选取（临界两侧 / 恰好整档 /
    零费率 / 超长持有），手算容差 0
  - FIFO 逐批消耗：最老先耗、两批加权费率与加权持有期手算、批次不足判未知
  - 申购费金额分档：首档/次档边界、优惠费率取值、每笔固定费、单档近似
  - 批次重放：期初批 / 期中新增 / 加仓新批 / 减仓 FIFO 扣减 / 清仓消失再现 /
    同日去重 / 份额字段无效沿用 / 多账户合并
  - 成本聚合契约：腿划分、入账日 = 生效日、未知与未建模计数、notes 标注
"""

from __future__ import annotations

import pytest

from src.python.analysis.fee_schedule_model import (
    SRC_F10,
    SRC_TABLE_SINGLE,
    SRC_UNKNOWN,
    TRADING_DAYS_PER_YEAR,
    build_single_purchase_schedule,
    parse_fee_percent,
    parse_purchase_fee_schedule,
    parse_redemption_fee_schedule,
    purchase_fee,
    select_purchase_tier,
    select_redemption_tier,
)
from src.python.analysis.trade_cost_model import (
    SIDE_BUY,
    SIDE_SELL,
    SIDE_UNMODELED,
    compute_trade_costs,
    rebuild_position_lots,
)
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


# ── 共享 fixture ─────────────────────────────────────────


def _redemption_rows() -> list[list[str]]:
    """来源实测五档（002943 形态）：1.5% / 0.75% / 0.5% / 0.25% / 0。"""
    return [
        ["小于7天", "1.50%"],
        ["大于等于7天，小于30天", "0.75%"],
        ["大于等于30天，小于365天", "0.50%"],
        ["大于等于365天，小于730天", "0.25%"],
        ["大于等于730天", "0.00%"],
    ]


def _redemption_schedule() -> dict:
    s = parse_redemption_fee_schedule(_redemption_rows())
    assert s is not None
    return s


def _purchase_schedule() -> dict:
    s = parse_purchase_fee_schedule(
        [
            ["小于100万元", "1.50%  |  0.15%"],
            ["大于等于100万元，小于500万元", "1.20%  |  0.12%"],
            ["大于等于500万元", "每笔1000元"],
        ]
    )
    assert s is not None
    return s


def _counter(days: float) -> callable:
    """固定返回 ``days`` 的交易日计数注入（手算可预期）。"""
    return lambda _start, _end: int(days)


def _changes(code: str, action: str, base: tuple[float, float], cand: tuple[float, float]) -> dict:
    """构造单条 What-if 变动（(份额, 成本)）。"""
    base_shares, base_cost = base
    cand_shares, cand_cost = cand
    return {
        "code": code,
        "name": f"{code}基金",
        "action": action,
        "base_shares": base_shares,
        "cand_shares": cand_shares,
        "base_cost": base_cost,
        "cand_cost": cand_cost,
    }


# ── 费率百分比与标签解析 ─────────────────────────────────


def test_parse_fee_percent_forms():
    """「1.50%」→ 0.015；「0.00%」→ 已知 0；---/空/非百分比 → None。"""
    assert parse_fee_percent("1.50%") == 0.015
    assert parse_fee_percent(" 0.15% ") == 0.0015
    assert parse_fee_percent("0.00%") == 0.0
    assert parse_fee_percent("---") is None
    assert parse_fee_percent("") is None
    assert parse_fee_percent("每笔1000元") is None


def test_redemption_label_forms_parse():
    """来源实测标签全形态 → 交易日边界（年标签 ×250）。"""
    rows = [
        ["小于7天", "1.50%"],
        ["小于等于6天", "1.50%"],
        ["大于等于7天，小于30天", "0.75%"],
        ["大于等于30天，小于等于364天", "0.50%"],
        ["大于等于7天", "0.00%"],
    ]
    # 逐行单档覆盖（首档从 0 起、全轴开区间由末档保证）
    s1 = parse_redemption_fee_schedule([rows[0], ["大于等于7天", "0.00%"]])
    assert select_redemption_tier(s1, 6)["rate"] == 0.015
    assert select_redemption_tier(s1, 7)["rate"] == 0.0

    s2 = parse_redemption_fee_schedule([["小于7天", "1.50%"], rows[2], ["大于等于30天", "0.10%"]])
    assert select_redemption_tier(s2, 7)["rate"] == 0.0075
    assert select_redemption_tier(s2, 29)["rate"] == 0.0075
    assert select_redemption_tier(s2, 30)["rate"] == 0.001

    # 「小于等于6天」≡ <7；「小于等于364天」≡ ≤364
    s3 = parse_redemption_fee_schedule([rows[1], ["大于等于7天", "0.00%"]])
    assert select_redemption_tier(s3, 6)["rate"] == 0.015
    assert select_redemption_tier(s3, 7)["rate"] == 0.0
    s4 = parse_redemption_fee_schedule([["小于30天", "0.50%"], rows[3], ["大于等于365天", "0.10%"]])
    assert select_redemption_tier(s4, 364)["rate"] == 0.005
    assert select_redemption_tier(s4, 365)["rate"] == 0.001


def test_redemption_year_label_boundary():
    """「N年」标签按 250 交易日/年折算为档位边界。"""
    s = parse_redemption_fee_schedule(
        [
            ["小于7天", "1.50%"],
            ["大于等于7天，小于1年", "0.50%"],
            ["大于等于1年，小于2年", "0.25%"],
            ["大于等于2年", "0.00%"],
        ]
    )
    assert s is not None
    assert TRADING_DAYS_PER_YEAR == 250
    assert select_redemption_tier(s, 249)["rate"] == 0.005
    assert select_redemption_tier(s, 250)["rate"] == 0.0025
    assert select_redemption_tier(s, 499)["rate"] == 0.0025
    assert select_redemption_tier(s, 500)["rate"] == 0.0


def test_redemption_parse_rejects_broken_rows():
    """缺口/起始不从 0/列不足/非百分比/区间倒置 → None（费率未知，不猜）。"""
    gap = parse_redemption_fee_schedule([["小于7天", "1.50%"], ["大于等于30天", "0.50%"]])
    assert gap is None
    not_from_zero = parse_redemption_fee_schedule([["大于等于30天", "0.50%"], ["大于等于365天", "0.25%"]])
    assert not_from_zero is None
    assert parse_redemption_fee_schedule([["小于7天"]]) is None
    assert parse_redemption_fee_schedule([["小于7天", "面议"]]) is None
    inverted = parse_redemption_fee_schedule([["大于等于30天，小于7天", "1.50%"], ["大于等于30天", "0.00%"]])
    assert inverted is None
    assert parse_redemption_fee_schedule([]) is None


def test_purchase_parse_discount_and_flat():
    """申购表：优惠费率优先取值、每笔固定费档、单值单元格取原值。"""
    s = _purchase_schedule()
    assert s["tiers"][0]["rate"] == 0.0015  # 取「|」后的优惠费率，非原费率 1.5%
    assert s["tiers"][0]["min_amount"] is None and s["tiers"][0]["max_amount"] == 1_000_000.0
    assert s["tiers"][1]["min_amount"] == 1_000_000.0 and s["tiers"][1]["max_amount"] == 5_000_000.0
    assert s["tiers"][1]["rate"] == 0.0012
    assert s["tiers"][2]["flat_fee"] == 1000.0 and s["tiers"][2]["max_amount"] is None

    single = parse_purchase_fee_schedule([["小于10万元", "0.15%"], ["大于等于10万元", "0.00%"]])
    assert single is not None and single["tiers"][0]["rate"] == 0.0015

    broken = parse_purchase_fee_schedule([["大于等于500万元，小于100万元", "1.0%"], ["大于等于1000万元", "0.00%"]])
    assert broken is None
    assert parse_purchase_fee_schedule([]) is None


# ── 申购费金额分档手算 ───────────────────────────────────


def test_purchase_fee_tier_boundaries_handcalc():
    """金额分档手算（容差 0）：次档边界、首档边界、每笔固定费。"""
    s = _purchase_schedule()
    # 首档 <100 万：999,900 × 0.15% = 1,499.85
    assert purchase_fee(999_900.0, s) == (1499.85, s["tiers"][0])
    # 次档边界恰好 100 万：1,000,000 × 0.12% = 1,200.00
    assert purchase_fee(1_000_000.0, s) == (1200.0, s["tiers"][1])
    # 次档中部：2,000,000 × 0.12% = 2,400.00
    assert purchase_fee(2_000_000.0, s) == (2400.0, s["tiers"][1])
    # 末档每笔固定费
    assert purchase_fee(6_000_000.0, s) == (1000.0, s["tiers"][2])


def test_purchase_fee_single_rate_schedule():
    """全量表单档费率（无分档）：按该档线性计费。"""
    s = build_single_purchase_schedule(0.0015)
    assert s is not None and s["source"] == SRC_TABLE_SINGLE
    # 50,000 × 0.15% = 75.00
    assert purchase_fee(50_000.0, s) == (75.0, s["tiers"][0])
    assert purchase_fee(0.0, s) == (0.0, s["tiers"][0])
    assert build_single_purchase_schedule(float("nan")) is None
    assert build_single_purchase_schedule(-0.1) is None


def test_select_purchase_tier_rejects_non_finite():
    """NaN 金额恒无命中（不落入任何档位，不出伪费率）。"""
    s = _purchase_schedule()
    assert select_purchase_tier(s, float("nan")) is None
    assert select_purchase_tier(None, 100.0) is None


# ── 赎回费 FIFO 手算（≥8 例） ─────────────────────────────


def test_fifo_single_lot_partial_sell_handcalc():
    """例① 单批次部分卖出：400 份 @ 80 交易日 → [30,365) 0.5%；4000×0.5%=20.00。"""
    lots = {"510300": [{"start_date": "2026-06-01", "shares": 1000.0}]}
    fee_index = {"510300": {"redemption": _redemption_schedule()}}
    res = compute_trade_costs(
        [_changes("510300", "减仓", (1000.0, 10000.0), (600.0, 6000.0))],
        fee_index=fee_index,
        lots_by_code=lots,
        count_trading_days=_counter(80),
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["side"] == SIDE_SELL
    assert leg["shares"] == 400.0 and leg["amount"] == 4000.0
    assert leg["rate"] == 0.005
    assert leg["fee"] == 20.0
    assert leg["holding_days"] == 80.0
    assert leg["rate_source"] == SRC_F10
    assert leg["booked_date"] == "2026-10-05"
    assert res["redemption_total"] == 20.0 and res["total_cost"] == 20.0
    assert res["fees_complete"] is True


def test_fifo_single_lot_full_sell_handcalc():
    """例② 单批次全额卖出：10000×0.5%=50.00。"""
    lots = {"511010": [{"start_date": "2026-06-01", "shares": 1000.0}]}
    res = compute_trade_costs(
        [_changes("511010", "清仓", (1000.0, 10000.0), (0.0, 0.0))],
        fee_index={"511010": {"redemption": _redemption_schedule()}},
        lots_by_code=lots,
        count_trading_days=_counter(80),
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["amount"] == 10000.0 and leg["fee"] == 50.0
    assert leg["rate"] == 0.005


def test_fifo_boundary_both_sides_handcalc():
    """例③ 持有期临界两侧：6 交易日 → 1.5%；7 交易日 → 0.75%。"""
    sched = _redemption_schedule()
    fee_index = {"X": {"redemption": sched}}
    for days, expect_rate, expect_fee in ((6, 0.015, 30.0), (7, 0.0075, 15.0)):
        res = compute_trade_costs(
            [_changes("X", "清仓", (1000.0, 2000.0), (0.0, 0.0))],
            fee_index=fee_index,
            lots_by_code={"X": [{"start_date": "2026-09-01", "shares": 1000.0}]},
            count_trading_days=_counter(days),
            effective_date="2026-10-05",
        )
        leg = res["legs"][0]
        assert leg["holding_days"] == float(days)
        assert leg["rate"] == expect_rate
        assert leg["fee"] == expect_fee  # 2000 × rate


def test_fifo_exact_tier_edge_handcalc():
    """例④ 恰好整档：364 交易日 → 0.5%；365 交易日 → 0.25%。"""
    for days, expect_rate in ((364, 0.005), (365, 0.0025)):
        res = compute_trade_costs(
            [_changes("X", "清仓", (1000.0, 10000.0), (0.0, 0.0))],
            fee_index={"X": {"redemption": _redemption_schedule()}},
            lots_by_code={"X": [{"start_date": "2026-01-05", "shares": 1000.0}]},
            count_trading_days=_counter(days),
            effective_date="2026-10-05",
        )
        assert res["legs"][0]["rate"] == expect_rate
        assert res["legs"][0]["fee"] == 10000.0 * expect_rate


def test_fifo_two_lots_weighted_handcalc():
    """例⑤ 两批加权：卖出 500 消耗旧 400@100d(0.5%)+新 100@5d(1.5%)。

    加权费率 = (400×0.005 + 100×0.015) / 500 = 0.007
    加权持有期 = (400×100 + 100×5) / 500 = 81.0
    费用 = 5000 × 0.007 = 35.00
    """
    lots = {
        "A": [
            {"start_date": "2026-01-05", "shares": 400.0},
            {"start_date": "2026-09-01", "shares": 600.0},
        ]
    }
    days_map = {"2026-01-05": 100, "2026-09-01": 5}
    res = compute_trade_costs(
        [_changes("A", "减仓", (1000.0, 8000.0), (500.0, 3000.0))],
        fee_index={"A": {"redemption": _redemption_schedule()}},
        lots_by_code=lots,
        count_trading_days=lambda s, _e: days_map[s],
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["amount"] == 5000.0
    assert leg["rate"] == 0.007
    assert leg["fee"] == 35.0
    assert leg["holding_days"] == 81.0


def test_fifo_oldest_consumed_first_handcalc():
    """例⑥ 消耗顺序 = 最老先耗：卖 300 只碰最老批（0.25%），非新批（1.5%）。"""
    lots = {
        "B": [
            {"start_date": "2026-01-05", "shares": 300.0},  # 400d → [365,730) 0.25%
            {"start_date": "2026-09-01", "shares": 300.0},  # 5d → 1.5%
        ]
    }
    days_map = {"2026-01-05": 400, "2026-09-01": 5}
    res = compute_trade_costs(
        [_changes("B", "减仓", (600.0, 6000.0), (300.0, 3000.0))],
        fee_index={"B": {"redemption": _redemption_schedule()}},
        lots_by_code=lots,
        count_trading_days=lambda s, _e: days_map[s],
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["rate"] == 0.0025
    assert leg["fee"] == 3000.0 * 0.0025  # 7.50
    assert leg["holding_days"] == 400.0


def test_fifo_zero_fee_schedule_handcalc():
    """例⑦ 零费率表（来源明确 0）→ fee=0 且已知（非未知）。"""
    s = parse_redemption_fee_schedule([["---", "0.00%"]])
    assert s is not None and s["tiers"][0]["rate"] == 0.0
    res = compute_trade_costs(
        [_changes("C", "清仓", (100.0, 1000.0), (0.0, 0.0))],
        fee_index={"C": {"redemption": s}},
        lots_by_code={"C": [{"start_date": "2026-09-01", "shares": 100.0}]},
        count_trading_days=_counter(10),
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["fee"] == 0.0 and leg["rate"] == 0.0
    assert leg["rate_source"] == SRC_F10
    assert res["fees_complete"] is True
    assert res["unknown_legs"] == 0


def test_fifo_very_long_hold_handcalc():
    """例⑧ 超长持有：800 交易日 → 末档 0%，fee=0 已知。"""
    res = compute_trade_costs(
        [_changes("D", "清仓", (100.0, 5000.0), (0.0, 0.0))],
        fee_index={"D": {"redemption": _redemption_schedule()}},
        lots_by_code={"D": [{"start_date": "2026-01-05", "shares": 100.0}]},
        count_trading_days=_counter(800),
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["holding_days"] == 800.0
    assert leg["rate"] == 0.0 and leg["fee"] == 0.0


def test_fifo_insufficient_lots_is_unknown():
    """批次不足覆盖卖出份额 → 费率未知（不猜），fees_complete=False。"""
    res = compute_trade_costs(
        [_changes("E", "清仓", (1200.0, 12000.0), (0.0, 0.0))],
        fee_index={"E": {"redemption": _redemption_schedule()}},
        lots_by_code={"E": [{"start_date": "2026-06-01", "shares": 1000.0}]},
        count_trading_days=_counter(80),
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["fee"] is None and leg["rate"] is None
    assert leg["rate_source"] == SRC_UNKNOWN
    assert res["unknown_legs"] == 1 and res["fees_complete"] is False
    assert res["redemption_total"] == 0.0


def test_fifo_missing_pieces_are_unknown():
    """缺批次 / 缺交易日计数 / 缺截止日 / 缺费率表 → 卖出腿一律未知。"""
    change = [_changes("F", "清仓", (100.0, 1000.0), (0.0, 0.0))]
    fee_index = {"F": {"redemption": _redemption_schedule()}}
    lots = {"F": [{"start_date": "2026-06-01", "shares": 100.0}]}
    cases = [
        {
            "fee_index": fee_index,
            "lots_by_code": {},
            "count_trading_days": _counter(80),
            "effective_date": "2026-10-05",
        },
        {"fee_index": fee_index, "lots_by_code": lots, "count_trading_days": None, "effective_date": "2026-10-05"},
        {
            "fee_index": fee_index,
            "lots_by_code": lots,
            "count_trading_days": _counter(80),
            "effective_date": "",
            "holding_end_date": "",
        },
        {"fee_index": {}, "lots_by_code": lots, "count_trading_days": _counter(80), "effective_date": "2026-10-05"},
    ]
    for kwargs in cases:
        res = compute_trade_costs(change, **kwargs)
        assert res["legs"][0]["fee"] is None
        assert res["legs"][0]["rate_source"] == SRC_UNKNOWN
        assert res["fees_complete"] is False


# ── 批次重放 ─────────────────────────────────────────────


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


def test_rebuild_opening_lot_and_increase():
    """期初批 = 首见日；份额增加 → 追加新批（本期日期）。"""
    snaps = [
        _snap("20260105T090000", [_h("A", 1000.0)]),
        _snap("20260112T090000", [_h("A", 1400.0)]),
    ]
    lots = rebuild_position_lots(snaps)
    assert lots["A"] == [
        {"start_date": "2026-01-05", "shares": 1000.0},
        {"start_date": "2026-01-12", "shares": 400.0},
    ]


def test_rebuild_decrease_consumes_oldest_fifo():
    """份额减少自最老批扣减；余量批保留。"""
    snaps = [
        _snap("20260105T090000", [_h("A", 1000.0)]),
        _snap("20260112T090000", [_h("A", 1400.0)]),
        _snap("20260120T090000", [_h("A", 1200.0)]),  # 减 200 → 耗最老批
    ]
    lots = rebuild_position_lots(snaps)
    assert lots["A"] == [
        {"start_date": "2026-01-05", "shares": 800.0},
        {"start_date": "2026-01-12", "shares": 400.0},
    ]


def test_rebuild_exit_then_reappear_is_new_lot():
    """清仓后再现 → 全新批次（不沿用旧批）。"""
    snaps = [
        _snap("20260105T090000", [_h("A", 1000.0)]),
        _snap("20260112T090000", []),  # 缺席 = 清仓
        _snap("20260120T090000", [_h("A", 500.0)]),
    ]
    lots = rebuild_position_lots(snaps)
    assert lots["A"] == [{"start_date": "2026-01-20", "shares": 500.0}]


def test_rebuild_same_day_dedup_keeps_last():
    """同日两份快照按日去重（保留最后一份），不产生虚假加仓批。"""
    snaps = [
        _snap("20260105T090000", [_h("A", 1000.0)]),
        _snap("20260105T150000", [_h("A", 1000.0)]),
        _snap("20260106T090000", [_h("A", 1000.0)]),
    ]
    lots = rebuild_position_lots(snaps)
    assert lots["A"] == [{"start_date": "2026-01-05", "shares": 1000.0}]


def test_rebuild_invalid_shares_carried_forward():
    """份额字段无效（None）→ 沿用上期批次，不判清仓。"""
    snaps = [
        _snap("20260105T090000", [_h("A", 1000.0)]),
        _snap("20260112T090000", [_h("A", None)]),
        _snap("20260120T090000", [_h("A", 1000.0)]),
    ]
    lots = rebuild_position_lots(snaps)
    assert lots["A"] == [{"start_date": "2026-01-05", "shares": 1000.0}]


def test_rebuild_multi_account_merged():
    """同 code 跨账户份额合并为同一批次（期初批 = 合计）。"""
    snap = SnapshotData(
        accounts=(
            AccountSnapshot(account_name="甲", holdings=(_h("A", 600.0),)),
            AccountSnapshot(account_name="乙", holdings=(_h("A", 400.0),)),
        ),
        total_value=0.0,
        total_cost=0.0,
        total_pnl=0.0,
        timestamp="20260105T090000",
    )
    lots = rebuild_position_lots([snap])
    assert lots["A"] == [{"start_date": "2026-01-05", "shares": 1000.0}]


def test_rebuild_empty_input():
    """空输入 → 空 dict（零批次，卖出腿将判未知）。"""
    assert rebuild_position_lots([]) == {}


# ── 成本聚合契约 ─────────────────────────────────────────


def test_buy_legs_amount_and_booked_date():
    """买入腿（新增/加仓）：金额 = 成本增量、入账日 = 生效日、单档来源标注。"""
    fee_index = {
        "N1": {"purchase": build_single_purchase_schedule(0.0015)},
        "N2": {"purchase": _purchase_schedule()},
    }
    res = compute_trade_costs(
        [
            _changes("N1", "新增", (0.0, 0.0), (1000.0, 50000.0)),
            _changes("N2", "加仓", (100.0, 10000.0), (300.0, 30000.0)),
        ],
        fee_index=fee_index,
        effective_date="2026-10-05",
    )
    assert res["available"] is True and res["leg_count"] == 2
    leg1, leg2 = res["legs"]
    assert leg1["side"] == SIDE_BUY and leg1["action"] == "新增"
    assert leg1["amount"] == 50000.0 and leg1["fee"] == 75.0  # 50000×0.15%
    assert leg1["rate_source"] == SRC_TABLE_SINGLE
    assert leg1["booked_date"] == "2026-10-05" and leg1["holding_days"] is None
    assert leg2["side"] == SIDE_BUY and leg2["amount"] == 20000.0
    assert leg2["fee"] == 30.0  # 20000×0.15%（首档优惠）
    assert leg2["rate_source"] == SRC_F10
    assert res["purchase_total"] == 105.0 and res["total_cost"] == 105.0
    assert res["unknown_legs"] == 0 and res["fees_complete"] is True


def test_unmodeled_stock_leg_not_counted_as_unknown():
    """场内品种腿：side=unmodeled、fee None、不计入未知、带未建模标注。"""
    res = compute_trade_costs(
        [
            _changes("601398", "清仓", (5000.0, 30000.0), (0.0, 0.0)),
            _changes("N1", "新增", (0.0, 0.0), (100.0, 10000.0)),
        ],
        fee_index={"N1": {"purchase": build_single_purchase_schedule(0.0015)}},
        effective_date="2026-10-05",
        unmodeled_codes={"601398"},
    )
    stock_leg = next(leg for leg in res["legs"] if leg["code"] == "601398")
    assert stock_leg["side"] == SIDE_UNMODELED
    assert stock_leg["fee"] is None and stock_leg["rate_source"] == "unmodeled"
    assert res["unmodeled_legs"] == 1 and res["unknown_legs"] == 0
    assert res["fees_complete"] is True
    assert any("未建模" in note and "印花税" in note for note in res["notes"])


def test_unknown_fee_source_leg_blocks_completeness():
    """基金腿无费率来源 → 未知计数 + fees_complete=False + 标注缺失。"""
    res = compute_trade_costs(
        [_changes("MISSING", "新增", (0.0, 0.0), (100.0, 10000.0))],
        fee_index={},
        effective_date="2026-10-05",
    )
    leg = res["legs"][0]
    assert leg["fee"] is None and leg["rate_source"] == SRC_UNKNOWN
    assert res["unknown_legs"] == 1 and res["fees_complete"] is False
    assert res["purchase_total"] == 0.0
    assert any("费率来源缺失" in note for note in res["notes"])


def test_all_unchanged_has_no_cost():
    """全部「不变」→ available=False 空契约（字段全量在场）。"""
    res = compute_trade_costs([_changes("U", "不变", (100.0, 1000.0), (100.0, 1000.0))])
    assert res["available"] is False
    assert res["legs"] == [] and res["leg_count"] == 0
    assert res["total_cost"] == 0.0 and res["fees_complete"] is True
    assert "无调仓变动" in res["reason"]


def test_notes_contract_lines():
    """口径标注：入账日/成本口径/交易日与保守/下界估计随内容出现。"""
    res = compute_trade_costs(
        [_changes("A", "清仓", (100.0, 1000.0), (0.0, 0.0))],
        fee_index={"A": {"redemption": _redemption_schedule()}},
        lots_by_code={"A": [{"start_date": "2026-06-01", "shares": 100.0}]},
        count_trading_days=_counter(80),
        effective_date="2026-10-05",
    )
    joined = " ".join(res["notes"])
    assert "入账日 = 调仓生效日（2026-10-05）" in joined
    assert "成本价口径" in joined
    assert "先进先出" in joined and "交易日" in joined and "偏保守" in joined
    assert "下界估计" in joined  # 使用了批次 → 下界标注
    assert "费率来源缺失" not in joined and "未建模" not in joined


def test_notes_single_rate_purchase_wording():
    """买单腿全部来自单档来源 → 「单档/首档近似」措辞（非「分档」）。"""
    res = compute_trade_costs(
        [_changes("N1", "新增", (0.0, 0.0), (100.0, 50000.0))],
        fee_index={"N1": {"purchase": build_single_purchase_schedule(0.0015)}},
        effective_date="2026-10-05",
    )
    joined = " ".join(res["notes"])
    assert "单档优惠费率" in joined and "按首档近似" in joined


def test_mixed_legs_totals_sum():
    """买卖混合：合计 = 申购 + 赎回；每腿字段全量在场。"""
    fee_index = {
        "BUY1": {"purchase": build_single_purchase_schedule(0.0015)},
        "SELL1": {"redemption": _redemption_schedule()},
    }
    res = compute_trade_costs(
        [
            _changes("BUY1", "新增", (0.0, 0.0), (100.0, 20000.0)),
            _changes("SELL1", "清仓", (300.0, 6000.0), (0.0, 0.0)),
        ],
        fee_index=fee_index,
        lots_by_code={"SELL1": [{"start_date": "2026-06-01", "shares": 300.0}]},
        count_trading_days=_counter(80),
        effective_date="2026-10-05",
    )
    assert res["purchase_total"] == 30.0  # 20000×0.15%
    assert res["redemption_total"] == 30.0  # 6000×0.5%
    assert res["total_cost"] == 60.0
    expected_keys = {
        "code",
        "name",
        "action",
        "side",
        "shares",
        "amount",
        "rate",
        "fee",
        "flat_fee",
        "rate_source",
        "booked_date",
        "holding_days",
    }
    for leg in res["legs"]:
        assert set(leg.keys()) == expected_keys


def test_config_source_stamped_on_leg():
    """费率表 source=config（配置兜底）→ 腿上如实标注来源。"""
    s = parse_redemption_fee_schedule(_redemption_rows(), source="config")
    res = compute_trade_costs(
        [_changes("A", "清仓", (100.0, 1000.0), (0.0, 0.0))],
        fee_index={"A": {"redemption": s}},
        lots_by_code={"A": [{"start_date": "2026-06-01", "shares": 100.0}]},
        count_trading_days=_counter(80),
        effective_date="2026-10-05",
    )
    assert res["legs"][0]["rate_source"] == "config"

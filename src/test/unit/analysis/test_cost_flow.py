"""成本流水分析单元测试 — XIRR 资金加权收益 + 成本分档 + 分红累计。

测试目标（验收口径）：
  - `solve_xirr`：已知年化案例（一次性投入 / 月定投 / 亏损 / 短周期）误差 <0.1%；
    空输入 / 长度不一致 / 日期非法 / 全部同一天返回 None；不同初始猜测收敛一致
  - `build_xirr_cashflows`：买入负 / 卖出正 / 分红正 / 期末市值正、按日期升序；
    无流水返回 None；分红份额未知回退当前持仓；费用计入
  - `build_cost_lots`：单笔买入 / 多笔买入 FIFO / 卖出扣减 / 无买入不可用
  - `compute_cost_tiers`：相对市价低/高/未分档划分、组合级合计与追高占比
  - `compute_dividend_totals`：按代码汇总、无持仓份额回退跳过
  - `build_fund_flow_data`：C19 契约形状（available 与子数据联动）

运行：
  python -m pytest src/test/unit/analysis/test_cost_flow.py -v
"""

from __future__ import annotations

import datetime as _dt

import pytest

from src.python.analysis.cost_flow import (
    build_cost_lots,
    build_fund_flow_data,
    build_xirr_cashflows,
    compute_cost_tiers,
    compute_dividend_totals,
    solve_xirr,
)
from src.python.core.models import DividendRecord, Holding, TradeRecord

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


def _trade(code, date, action, shares, price, fee=0.0):
    """构造交易流水记录。"""
    return TradeRecord(date=date, code=code, action=action, shares=shares, price=price, fee=fee)


def _div(code, date, amount, shares=0.0):
    """构造分红流水记录。"""
    return DividendRecord(date=date, code=code, amount=amount, shares=shares)


def _holding(code, name, shares, cost_price):
    """构造当前持仓记录。"""
    return Holding(account="账户A", name=name, code=code, shares=shares, cost_price=cost_price)


# ─────────────────────────────────────────────────────────────
#  solve_xirr — 已知案例精度
# ─────────────────────────────────────────────────────────────


def test_xirr_lump_sum_known_annual():
    """一次性投入 1000，一年后 1100 -> 年化 ≈10%（误差 <0.1%）。"""
    amounts = [-1000.0, 1100.0]
    dates = [_dt.date(2025, 1, 1), _dt.date(2026, 1, 1)]
    rate = solve_xirr(amounts, dates)
    assert rate is not None
    assert abs(rate - 0.10) < 0.001


def test_xirr_monthly_dca_known_annual():
    """月定投 1000×12，期末值按 10% 年化构造 -> XIRR≈10%（误差 <0.1%）。"""
    amounts = [-1000.0] * 12
    dates = [_dt.date(2025, 1, 1) + _dt.timedelta(days=30 * i) for i in range(12)]
    # 期末市值 = Σ 每笔投入按剩余 365-30i 天以 10% 年化复利
    final = sum(1000.0 * (1.10) ** ((365.0 - 30.0 * i) / 365.0) for i in range(12))
    amounts.append(final)
    dates.append(_dt.date(2025, 1, 1) + _dt.timedelta(days=365))
    rate = solve_xirr(amounts, dates)
    assert rate is not None
    assert abs(rate - 0.10) < 0.001


def test_xirr_loss_case():
    """一次性投入 1000，一年后 900 -> 年化 ≈ -10%。"""
    amounts = [-1000.0, 900.0]
    dates = [_dt.date(2025, 1, 1), _dt.date(2026, 1, 1)]
    rate = solve_xirr(amounts, dates)
    assert rate is not None
    assert abs(rate - (-0.10)) < 0.001


def test_xirr_short_period_annualized():
    """半年 1050（本金 1000，182 天）-> 年化 ≈ (1.05)^(365/182)-1。"""
    amounts = [-1000.0, 1050.0]
    dates = [_dt.date(2025, 1, 1), _dt.date(2025, 7, 2)]
    expected = 1.05 ** (365.0 / 182.0) - 1.0
    rate = solve_xirr(amounts, dates)
    assert rate is not None
    assert abs(rate - expected) < 0.001


def test_xirr_guess_independent():
    """不同初始猜测收敛到同一年化收益（数值稳定性）。"""
    amounts = [-1000.0, 1100.0]
    dates = [_dt.date(2025, 1, 1), _dt.date(2026, 1, 1)]
    r1 = solve_xirr(amounts, dates, guess=-0.2)
    r2 = solve_xirr(amounts, dates, guess=0.5)
    r3 = solve_xirr(amounts, dates, guess=1.5)
    assert r1 is not None and r2 is not None and r3 is not None
    assert abs(r1 - r2) < 1e-6
    assert abs(r2 - r3) < 1e-6


# ─────────────────────────────────────────────────────────────
#  solve_xirr — 边界
# ─────────────────────────────────────────────────────────────


def test_xirr_empty_inputs_none():
    """空输入 -> None。"""
    assert solve_xirr([], []) is None
    assert solve_xirr([-1000.0], []) is None


def test_xirr_mismatched_lengths_none():
    """金额与日期长度不一致 -> None。"""
    assert solve_xirr([-1000.0, 1100.0], [_dt.date(2025, 1, 1)]) is None


def test_xirr_invalid_date_none():
    """日期非法 -> None。"""
    assert solve_xirr([-1000.0, 1100.0], ["不是日期", _dt.date(2026, 1, 1)]) is None


def test_xirr_all_same_date_none():
    """全部现金流同一天（时点权重恒 0，NPV 与收益无关）-> None。"""
    amounts = [-1000.0, 1100.0]
    dates = [_dt.date(2025, 1, 1), _dt.date(2025, 1, 1)]
    assert solve_xirr(amounts, dates) is None


# ─────────────────────────────────────────────────────────────
#  build_xirr_cashflows
# ─────────────────────────────────────────────────────────────


def test_cashflows_shape_and_sign():
    """买入负 / 卖出正 / 分红正 / 期末市值正，按日期升序。"""
    tx = [
        _trade("600900", "2025-01-05", "buy", 200, 25.0, fee=5.0),
        _trade("600519", "2025-06-10", "sell", 10, 2100.0, fee=10.0),
    ]
    divs = [_div("600900", "2025-06-01", 0.35, shares=200.0)]
    holdings = [
        _holding("600900", "长江电力", 200, 25.05),
        _holding("600519", "贵州茅台", 0, 0.0),
    ]
    prices = {"600900": 28.0, "600519": 2200.0}
    flows = build_xirr_cashflows(tx, divs, holdings, prices, end_date=_dt.date(2025, 12, 31))
    assert flows is not None
    # 买入：-(200×25 + 5) = -5005
    assert flows[0][0] == _dt.date(2025, 1, 5)
    assert flows[0][1] == pytest.approx(-5005.0)
    # 分红：0.35×200 = 70
    assert (_dt.date(2025, 6, 1), 70.0) in flows
    # 卖出：+(10×2100 - 10) = 20990
    assert (_dt.date(2025, 6, 10), 20990.0) in flows
    # 期末市值：200×28 + 0×2200 = 5600
    assert flows[-1][0] == _dt.date(2025, 12, 31)
    assert flows[-1][1] == pytest.approx(5600.0)
    dates = [d for d, _ in flows]
    assert dates == sorted(dates)


def test_cashflows_no_flows_none():
    """无交易无分红 -> None。"""
    holdings = [_holding("600900", "长江电力", 200, 25.0)]
    flows = build_xirr_cashflows([], [], holdings, {"600900": 28.0})
    assert flows is None


def test_cashflows_dividend_shares_fallback():
    """分红登记日份额未知 -> 回退当前持仓份额。"""
    tx = [_trade("600900", "2025-01-05", "buy", 200, 25.0)]
    divs = [_div("600900", "2025-06-01", 0.35)]  # shares=0 -> 回退
    holdings = [_holding("600900", "长江电力", 200, 25.0)]
    flows = build_xirr_cashflows(tx, divs, holdings, {"600900": 28.0})
    assert flows is not None
    assert (_dt.date(2025, 6, 1), pytest.approx(70.0)) in flows


def test_cashflows_fee_included():
    """买入费用计入现金流幅值（-（价格×份额 + 费用））。"""
    tx = [_trade("600900", "2025-01-05", "buy", 200, 25.0, fee=12.0)]
    flows = build_xirr_cashflows(tx, [], [], {"600900": 28.0})
    assert flows is not None
    assert flows[0][1] == pytest.approx(-(25.0 * 200 + 12.0))


# ─────────────────────────────────────────────────────────────
#  build_cost_lots
# ─────────────────────────────────────────────────────────────


def test_cost_lots_single_buy():
    """单笔买入 -> 单批次，成本价含费用摊薄。"""
    tx = [_trade("600900", "2025-01-05", "buy", 200, 25.0, fee=5.0)]
    data = build_cost_lots(tx)
    assert data["available"] is True
    lots = data["lots"]["600900"]
    assert len(lots) == 1
    assert lots[0]["shares"] == pytest.approx(200.0)
    assert lots[0]["cost_price"] == pytest.approx(25.0 + 5.0 / 200.0)


def test_cost_lots_fifo_sell_consumes():
    """多笔买入 + 卖出 FIFO 扣减（先买先卖）。"""
    tx = [
        _trade("600900", "2025-01-05", "buy", 100, 20.0),
        _trade("600900", "2025-02-05", "buy", 100, 30.0),
        _trade("600900", "2025-03-05", "sell", 150, price=28.0),
    ]
    data = build_cost_lots(tx)
    assert data["available"] is True
    lots = data["lots"]["600900"]
    # 卖出 150 扣减第一批 100 + 第二批 50
    assert len(lots) == 1
    assert lots[0]["shares"] == pytest.approx(50.0)
    assert lots[0]["cost_price"] == pytest.approx(30.0)


def test_cost_lots_sell_all_empty_unavailable():
    """卖出清空全部批次 -> available=False。"""
    tx = [
        _trade("600900", "2025-01-05", "buy", 100, 20.0),
        _trade("600900", "2025-03-05", "sell", 100, price=28.0),
    ]
    data = build_cost_lots(tx)
    assert data["available"] is False


def test_cost_lots_no_buy_unavailable():
    """无买入流水 -> available=False。"""
    tx = [_trade("600900", "2025-03-05", "sell", 100, price=28.0)]
    assert build_cost_lots(tx)["available"] is False
    assert build_cost_lots([])["available"] is False


# ─────────────────────────────────────────────────────────────
#  compute_cost_tiers
# ─────────────────────────────────────────────────────────────


def test_cost_tiers_low_high_split():
    """相对市价低/高成本档划分与组合合计、追高占比。"""
    tx = [
        _trade("600900", "2025-01-05", "buy", 100, 20.0),  # 低成本
        _trade("600900", "2025-02-05", "buy", 100, 40.0),  # 高成本
    ]
    holdings = [_holding("600900", "长江电力", 200, 30.0)]
    data = compute_cost_tiers(tx, holdings, {"600900": 30.0})
    assert data["available"] is True
    low = data["totals"]["low"]
    high = data["totals"]["high"]
    assert low["shares"] == pytest.approx(100.0)
    assert high["shares"] == pytest.approx(100.0)
    assert low["market_value"] == pytest.approx(100.0 * 30.0)
    assert high["market_value"] == pytest.approx(100.0 * 30.0)
    assert data["high_cost_ratio"] == pytest.approx(0.5)


def test_cost_tiers_no_price_unpriced():
    """无市价品种 -> 归入「未分档」，不计入追高占比。"""
    tx = [_trade("600900", "2025-01-05", "buy", 100, 20.0)]
    holdings = [_holding("600900", "长江电力", 100, 20.0)]
    data = compute_cost_tiers(tx, holdings, {})
    assert data["available"] is True
    assert data["totals"]["unpriced"]["shares"] == pytest.approx(100.0)
    assert data["totals"]["low"]["shares"] == pytest.approx(0.0)
    assert data["high_cost_ratio"] == pytest.approx(0.0)


def test_cost_tiers_unavailable_without_lots():
    """无可分档批次 -> available=False。"""
    data = compute_cost_tiers([], [_holding("600900", "长江电力", 100, 20.0)], {"600900": 30.0})
    assert data["available"] is False


# ─────────────────────────────────────────────────────────────
#  compute_dividend_totals
# ─────────────────────────────────────────────────────────────


def test_dividend_totals_per_code_and_total():
    """分红按代码汇总，含登记日份额与回退份额。"""
    divs = [
        _div("600900", "2025-06-01", 0.35, shares=200.0),
        _div("600900", "2025-12-01", 0.35),  # shares=0 -> 回退当前持仓
        _div("600519", "2025-06-01", 2.5, shares=10.0),
    ]
    holdings = [_holding("600900", "长江电力", 200, 25.0)]
    data = compute_dividend_totals(divs, holdings)
    assert data["available"] is True
    assert data["per_code"]["600900"] == pytest.approx(70.0 + 70.0)
    assert data["per_code"]["600519"] == pytest.approx(25.0)
    assert data["total"] == pytest.approx(165.0)


def test_dividend_totals_unavailable_empty():
    """无分红或无持仓份额可回退 -> available=False。"""
    assert compute_dividend_totals([], [])["available"] is False
    divs = [_div("600900", "2025-06-01", 0.35)]  # 无当前持仓可回退
    assert compute_dividend_totals(divs, [])["available"] is False


# ─────────────────────────────────────────────────────────────
#  build_fund_flow_data（C19 契约）
# ─────────────────────────────────────────────────────────────


def test_fund_flow_data_contract_shape():
    """契约形状：xirr / cost_tiers / dividends 联动 available。"""
    tx = [
        _trade("600900", "2025-01-05", "buy", 200, 25.0),
        _trade("600900", "2025-02-05", "buy", 100, 30.0),
    ]
    divs = [_div("600900", "2025-06-01", 0.35, shares=200.0)]
    holdings = [_holding("600900", "长江电力", 300, 26.67)]
    data = build_fund_flow_data(tx, divs, holdings, {"600900": 28.0}, end_date=_dt.date(2025, 12, 31))
    assert data["available"] is True
    assert data["xirr"] is not None
    assert "rate" in data["xirr"] and "end_date" in data["xirr"]
    assert data["cost_tiers"]["available"] is True
    assert data["dividends"]["available"] is True
    assert set(data.keys()) == {"available", "xirr", "cost_tiers", "dividends"}


def test_fund_flow_data_unavailable_without_flows():
    """无流水且无分红 -> available=False，各子数据为空占位。"""
    holdings = [_holding("600900", "长江电力", 200, 25.0)]
    data = build_fund_flow_data([], [], holdings, {"600900": 28.0})
    assert data["available"] is False
    assert data["xirr"] is None
    assert data["cost_tiers"]["available"] is False
    assert data["dividends"]["available"] is False

"""调仓建议可行化层单元测试（份额取整 / 费用估算 / 现金缓冲 / 优先级）。

覆盖：
  - 份额取整：A 股取整一手 100 股、场内基金/ETF 取整 100 份、场外基金取整整数份
  - 操作生成：止损清仓 / 止盈部分了结 / 再平衡超限卖出减仓
  - 费用估算：佣金（含最低佣金）/ 印花税（仅 A 股）/ 赎回费（仅场外基金），固定 fixture 精度
  - 现金缓冲：逐条累计现金、现金负值订单剔除（现金负值防护）
  - 优先级：止损 > 部分止盈 > 卖出减仓；同品种去重保留优先级最高
  - 守卫：空信号 / 组合级信号跳过 / 缺价格 / 信号指向不存在品种

运行：
  python -m pytest src/test/unit/analysis/test_rebalance_advisor.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.rebalance_advisor import build_rebalance_advice, estimate_fee


pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

# 固定费率 fixture（含小数佣金，断言误差 <0.01 元）
_FEE_FIXTURE = {
    "commission_rate": 0.00025,  # 万 2.5
    "min_commission": 5.0,  # 最低佣金 5 元
    "stamp_duty_rate": 0.0005,  # 印花税 0.05%
    "redemption_rate": 0.005,  # 场外赎回费 0.5%
}


# ── 辅助构造 ──────────────────────────────────────────────


def _holding(name: str, code: str, shares: float, price: float) -> dict:
    """构造 holdings_details 单行（市值 = 份额 × 价格）。"""
    return {
        "name": name,
        "code": code,
        "shares": shares,
        "price": price,
        "market_value": round(shares * price, 2),
        "cost": 0.0,
        "profit": 0.0,
        "profit_rate": 0.0,
        "change_pct": 0.0,
        "nav_date": "2026-08-04",
        "source_api": "test",
    }


def _discipline(code: str, name: str, action: str) -> dict:
    """构造交易纪律触发信号（结构同 trade_discipline 输出）。"""
    return {
        "code": code,
        "name": name,
        "rule": "止损线 -15%",
        "value": "-18.0%",
        "triggered": True,
        "distance_pct": 3.0,
        "action": action,
    }


def _rebalance(code: str, name: str, weight: float = 0.3, threshold: float = 0.15) -> dict:
    """构造再平衡信号（结构同 simple_rebalance 输出）。"""
    return {
        "code": code,
        "name": name,
        "weight": weight,
        "threshold": threshold,
        "action": "建议部分止盈至10-15%区间",
    }


# ── 份额取整（一手） ──────────────────────────────────────


class TestLotRounding:
    """份额取整：A 股 / 场内基金取整一手 100，场外基金取整整数份。"""

    def test_a_share_rounded_down_to_100_lot(self):
        """A 股 1350 份卖出 1/3 → 450 → 取整一手 100 → 400。"""
        holdings = [_holding("浦发银行", "600000", 1350, 10.0)]
        signals = [_discipline("600000", "浦发银行", "止盈")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=13500.0, fee_table=_FEE_FIXTURE)
        assert len(advice) == 1
        assert advice[0]["shares"] == 400
        assert advice[0]["amount"] == 4000.0

    def test_exchange_fund_rounded_down_to_100_lot(self):
        """场内 ETF 1050 份卖出 1/3 → 350 → 取整 100 份 → 300。"""
        holdings = [_holding("沪深300ETF", "510300", 1050, 4.0)]
        signals = [_discipline("510300", "沪深300ETF", "止盈")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=4200.0, fee_table=_FEE_FIXTURE)
        assert len(advice) == 1
        assert advice[0]["shares"] == 300

    def test_otc_fund_rounded_to_integer_shares(self):
        """场外基金 1234.5 份止损清仓 → 取整整数份 → 1234。"""
        holdings = [_holding("华夏混合", "000001", 1234.5, 1.2)]
        signals = [_discipline("000001", "华夏混合", "止损/减仓")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=1481.4, fee_table=_FEE_FIXTURE)
        assert len(advice) == 1
        assert advice[0]["shares"] == 1234

    def test_otc_bond_fund_bare_bond_keyword_integer_shares(self):
        """名称含"债券"（无细分词）的 00 前缀场外基金 → 取整整数份（回归：000311 债券A）。"""
        holdings = [_holding("景顺长城景颐双利债券A", "000311", 1234.5, 1.2)]
        signals = [_discipline("000311", "景顺长城景颐双利债券A", "止损/减仓")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=1481.4, fee_table=_FEE_FIXTURE)
        assert len(advice) == 1
        assert advice[0]["shares"] == 1234

    def test_hk_stock_rounded_to_integer_shares(self):
        """港股（非 A 股/场内基金/场外基金）按整数份取整，不做一手 100 取整。"""
        holdings = [_holding("腾讯控股", "00700", 500.5, 400.0)]
        signals = [_discipline("00700", "腾讯控股", "止损/减仓")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=200200.0, fee_table=_FEE_FIXTURE)
        assert len(advice) == 1
        assert advice[0]["shares"] == 500


# ── 操作生成 ──────────────────────────────────────────────


class TestOperation:
    """操作生成：止损清仓 / 止盈部分了结 / 再平衡超限卖出减仓。"""

    def test_stop_loss_sells_entire_position(self):
        """止损 → 清仓：500 份全部卖出，金额 = 500 × 10。"""
        holdings = [_holding("浦发银行", "600000", 500, 10.0)]
        signals = [_discipline("600000", "浦发银行", "止损/减仓")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=5000.0, fee_table=_FEE_FIXTURE)
        assert len(advice) == 1
        assert advice[0]["operation"] == "止损"
        assert advice[0]["shares"] == 500
        assert advice[0]["amount"] == 5000.0

    def test_take_profit_sells_one_third(self):
        """止盈 → 部分了结 1/3：600 份 → 200 份。"""
        holdings = [_holding("贵州茅台", "600519", 600, 100.0)]
        signals = [_discipline("600519", "贵州茅台", "部分止盈")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=60000.0, fee_table=_FEE_FIXTURE)
        assert len(advice) == 1
        assert advice[0]["operation"] == "部分止盈"
        assert advice[0]["shares"] == 200

    def test_rebalance_overweight_sells_to_threshold(self):
        """再平衡超限（占比 30% > 15%）→ 卖出超出警戒线部分至阈值市值。"""
        holdings = [_holding("某持仓", "600001", 300, 10.0)]  # 市值 3000 = 总市值 10000 的 30%
        signals = [_rebalance("600001", "某持仓", weight=0.3, threshold=0.15)]
        advice = build_rebalance_advice(signals, [], holdings, total_mv=10000.0, fee_table=_FEE_FIXTURE)
        assert len(advice) == 1
        assert advice[0]["operation"] == "卖出减仓"
        # 超出部分 = 3000 - 0.15×10000 = 1500 → 150 份 → 取整一手 100
        assert advice[0]["shares"] == 100
        assert advice[0]["amount"] == 1000.0


# ── 费用估算 ──────────────────────────────────────────────


class TestFeeEstimation:
    """费用估算：佣金最低线 / 印花税（仅 A 股）/ 赎回费（仅场外基金）。"""

    def test_fee_precision_with_fixed_fixture(self):
        """固定费率 fixture 下费用与解析解误差 <0.01 元（自动化断言）。"""
        # A 股卖出 10000 元：佣金 max(2.5,5)=5 + 印花税 5.0 = 10.0
        assert estimate_fee("卖出减仓", 10000.0, "600000", "浦发银行", _FEE_FIXTURE) == pytest.approx(10.0, abs=0.005)
        # 场内 ETF 卖出 10000 元：仅佣金 5.0（无印花税）
        assert estimate_fee("卖出减仓", 10000.0, "510300", "沪深300ETF", _FEE_FIXTURE) == pytest.approx(5.0, abs=0.005)
        # 场外基金卖出 10000 元：佣金 5.0 + 赎回费 50.0 = 55.0
        assert estimate_fee("卖出减仓", 10000.0, "000001", "华夏混合", _FEE_FIXTURE) == pytest.approx(55.0, abs=0.005)

    def test_commission_minimum_applied(self):
        """小额卖出佣金按最低 5 元计：300 元 A 股 → 5 + 0.15 = 5.15。"""
        assert estimate_fee("卖出减仓", 300.0, "600000", "浦发银行", _FEE_FIXTURE) == pytest.approx(5.15, abs=0.005)

    def test_stamp_duty_only_on_a_share(self):
        """印花税仅 A 股卖出计收：同金额 A 股比场内 ETF 多出印花税部分。"""
        a_share = estimate_fee("卖出减仓", 10000.0, "600000", "浦发银行", _FEE_FIXTURE)
        etf = estimate_fee("卖出减仓", 10000.0, "510300", "沪深300ETF", _FEE_FIXTURE)
        assert a_share - etf == pytest.approx(5.0, abs=0.005)  # 印花税 10000×0.0005

    def test_redemption_fee_only_on_otc_fund(self):
        """赎回费仅场外基金卖出计收：场外基金比场内基金多出赎回费。"""
        otc = estimate_fee("卖出减仓", 10000.0, "000001", "华夏混合", _FEE_FIXTURE)
        etf = estimate_fee("卖出减仓", 10000.0, "510300", "沪深300ETF", _FEE_FIXTURE)
        assert otc - etf == pytest.approx(50.0, abs=0.005)  # 赎回费 10000×0.005

    def test_bond_fund_redemption_not_stamp_duty(self):
        """00 前缀债券型基金（名称含"债券"无细分词）计收赎回费而非印花税（回归：000311）。"""
        assert estimate_fee("卖出减仓", 10000.0, "000311", "景顺长城景颐双利债券A", _FEE_FIXTURE) == pytest.approx(
            55.0, abs=0.005
        )  # 佣金 5 + 赎回费 50

    def test_none_name_does_not_crash(self):
        """名称缺失（None）不抛异常：00 前缀按 A 股处理计收印花税（防御性降级）。"""
        assert estimate_fee("止损", 10000.0, "000311", None, _FEE_FIXTURE) == pytest.approx(10.0, abs=0.005)

    def test_unknown_operation_raises_value_error(self):
        """未知操作（如买入）拒绝估算，避免静默按卖出口径计费。"""
        with pytest.raises(ValueError):
            estimate_fee("买入", 10000.0, "600000", "浦发银行", _FEE_FIXTURE)


# ── 现金缓冲 ──────────────────────────────────────────────


class TestCashBuffer:
    """现金缓冲：逐条累计现金余额、现金负值订单剔除（现金负值防护）。"""

    def test_cash_after_accumulates_never_negative(self):
        """多条卖出按执行顺序累计现金，任一条调仓后现金 ≥0。"""
        holdings = [
            _holding("浦发银行", "600000", 200, 10.0),  # 止损卖出 2000，费 6.0
            _holding("沪深300ETF", "510300", 300, 4.0),  # 止损卖出 1200，费 5.0
        ]
        signals = [
            _discipline("600000", "浦发银行", "止损/减仓"),
            _discipline("510300", "沪深300ETF", "止损/减仓"),
        ]
        advice = build_rebalance_advice(
            [], signals, holdings, total_mv=3200.0, fee_table=_FEE_FIXTURE, available_cash=1000.0
        )
        assert len(advice) == 2
        # 同优先级（止损）按卖出量降序执行：先卖 510300（1200 元），再卖 600000（2000 元）
        assert advice[0]["code"] == "510300"
        assert advice[0]["cash_after"] == pytest.approx(1000.0 + 1200.0 - 5.0, abs=0.005)
        assert advice[1]["code"] == "600000"
        assert advice[1]["cash_after"] == pytest.approx(2195.0 + 2000.0 - 6.0, abs=0.005)
        for item in advice:
            assert item["cash_after"] >= 0

    def test_order_skipped_when_cash_goes_negative(self):
        """现金负值防护：卖出净额不足以覆盖费用（费用 > 卖出金额）→ 剔除该订单。"""
        # 退市边缘 A 股 1 手 = 100 股 × 0.01 元 = 1 元，佣金最低 5 元 → 净额 -4 元
        holdings = [_holding("退市边缘", "600000", 100, 0.01)]
        signals = [_discipline("600000", "退市边缘", "止损/减仓")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=1.0, fee_table=_FEE_FIXTURE)
        assert advice == []

    def test_initial_cash_preserved_in_cash_after(self):
        """无信号时初始现金不被消费，返回空清单。"""
        holdings = [_holding("浦发银行", "600000", 200, 10.0)]
        advice = build_rebalance_advice([], [], holdings, total_mv=2000.0, fee_table=_FEE_FIXTURE, available_cash=500.0)
        assert advice == []


# ── 优先级与去重 ──────────────────────────────────────────


class TestPriorityAndDedupe:
    """优先级排序与同品种去重。"""

    def test_priority_order_stop_loss_first(self):
        """止损 > 部分止盈 > 卖出减仓：清单按该顺序输出。"""
        holdings = [
            _holding("甲", "600000", 500, 10.0),  # 止损
            _holding("乙", "600001", 600, 10.0),  # 止盈
            _holding("丙", "600002", 300, 10.0),  # 再平衡超限（市值 3000 = 30%）
        ]
        rebalance_signals = [_rebalance("600002", "丙", weight=0.3, threshold=0.15)]
        discipline_signals = [
            _discipline("600000", "甲", "止损/减仓"),
            _discipline("600001", "乙", "部分止盈"),
        ]
        advice = build_rebalance_advice(
            rebalance_signals, discipline_signals, holdings, total_mv=10000.0, fee_table=_FEE_FIXTURE
        )
        assert [a["operation"] for a in advice] == ["止损", "部分止盈", "卖出减仓"]

    def test_dedupe_same_code_prefers_discipline(self):
        """同一品种同时触发再平衡与止损 → 只保留优先级最高的止损一条。"""
        holdings = [_holding("某持仓", "600001", 300, 10.0)]
        rebalance_signals = [_rebalance("600001", "某持仓", weight=0.3, threshold=0.15)]
        discipline_signals = [_discipline("600001", "某持仓", "止损/减仓")]
        advice = build_rebalance_advice(
            rebalance_signals, discipline_signals, holdings, total_mv=10000.0, fee_table=_FEE_FIXTURE
        )
        assert len(advice) == 1
        assert advice[0]["operation"] == "止损"


# ── 多品种与守卫 ──────────────────────────────────────────


class TestMultiAndGuards:
    """多品种混合输出与数据守卫。"""

    def test_mixed_positions_full_item_shape(self):
        """多品种混合触发 → 每条含 code/name/operation/shares/amount/fee/cash_after。"""
        holdings = [
            _holding("甲", "600000", 200, 10.0),
            _holding("乙", "510300", 300, 4.0),
            _holding("丙", "000001", 500.5, 2.0),
        ]
        signals = [
            _discipline("600000", "甲", "止损/减仓"),
            _discipline("510300", "乙", "部分止盈"),
            _discipline("000001", "丙", "部分止盈"),
        ]
        advice = build_rebalance_advice([], signals, holdings, total_mv=4000.0, fee_table=_FEE_FIXTURE)
        assert len(advice) == 3
        for item in advice:
            assert {"code", "name", "operation", "shares", "amount", "fee", "cash_after"} <= set(item)

    def test_empty_signals_returns_empty(self):
        """无任何信号 → 空清单。"""
        holdings = [_holding("浦发银行", "600000", 200, 10.0)]
        assert build_rebalance_advice([], [], holdings, total_mv=2000.0) == []
        assert build_rebalance_advice(None, None, holdings, total_mv=2000.0) == []

    def test_empty_holdings_returns_empty(self):
        """空持仓 → 空清单。"""
        assert build_rebalance_advice([], [], None, total_mv=0.0) == []

    def test_portfolio_level_signal_skipped(self):
        """组合级信号（code 为空，如回撤）无可对应单品 → 跳过。"""
        holdings = [_holding("浦发银行", "600000", 200, 10.0)]
        signals = [
            {
                "code": "",
                "name": "组合",
                "rule": "回撤线 -10%",
                "value": "-12.0%",
                "triggered": True,
                "distance_pct": 2.0,
                "action": "减仓控回撤",
            }
        ]
        advice = build_rebalance_advice([], signals, holdings, total_mv=2000.0, fee_table=_FEE_FIXTURE)
        assert advice == []

    def test_missing_price_guard(self):
        """缺价格（price=0）的品种不生成建议（避免除零）。"""
        holdings = [_holding("浦发银行", "600000", 200, 0.0)]
        signals = [_discipline("600000", "浦发银行", "止损/减仓")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=2000.0, fee_table=_FEE_FIXTURE)
        assert advice == []

    def test_signal_for_unknown_holding_skipped(self):
        """信号指向持仓中不存在的品种 → 跳过。"""
        holdings = [_holding("浦发银行", "600000", 200, 10.0)]
        signals = [_discipline("999999", "不存在", "止损/减仓")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=2000.0, fee_table=_FEE_FIXTURE)
        assert advice == []

    def test_a_share_below_lot_rounded_to_zero_skipped(self):
        """A 股不足一手的卖出请求（如 50 份）取整为 0 → 不生成建议。"""
        holdings = [_holding("浦发银行", "600000", 50, 10.0)]
        signals = [_discipline("600000", "浦发银行", "止损/减仓")]
        advice = build_rebalance_advice([], signals, holdings, total_mv=500.0, fee_table=_FEE_FIXTURE)
        assert advice == []

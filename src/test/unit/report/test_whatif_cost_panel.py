"""What-if 交易成本对比面板（whatif_cost_panel）单元测试 — 装配契约与手算对照。

覆盖（对应验收条目）：
  - 全量装配：费率注入 + 快照批次 + 计数注入 → 成本本体 / impact 手算 / 基准对齐
  - 费率未知 → 无成本后数字（impact/candidate_after 缺席），成本块照常
  - 无回测 → 仅成本块（impact/benchmark/chart 全缺席）
  - 未建模品种（股票/场内）显式标注；费率取数只喂场外基金代码
  - 三线图数据与 impact 同源（labels/base/candidate_after/benchmark）

所有 I/O 注入（snapshots / 计数 / 费率 / 基准文本 / 指数行情），零出网零落盘。

运行：
  cd <项目根目录>
  pytest src/test/unit/report/test_whatif_cost_panel.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.fee_schedule_model import (
    SRC_F10,
    build_single_purchase_schedule,
    parse_redemption_fee_schedule,
)
from src.python.analysis.trade_cost_model import SIDE_BUY, SIDE_SELL
from src.python.report.whatif_cost_panel import build_whatif_cost_panel
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_BENCH_POOL = {"sh000300": "沪深300", "sh000905": "中证500"}


# ── 共享 fixture ─────────────────────────────────────────


def _redemption_rows() -> list[list[str]]:
    """来源实测五档（002943 形态）：60 交易日落 [30,365) 档 → 0.50%。"""
    return [
        ["小于7天", "1.50%"],
        ["大于等于7天，小于30天", "0.75%"],
        ["大于等于30天，小于365天", "0.50%"],
        ["大于等于365天，小于730天", "0.25%"],
        ["大于等于730天", "0.00%"],
    ]


def _h(code: str, shares: float) -> SnapshotHolding:
    return SnapshotHolding(code=code, name=code, shares=shares, cost_price=1.0, market_value=shares)


def _snapshots() -> list[SnapshotData]:
    """096001 期初批 2026-07-01（2000 份）→ 卖出腿持有期可判。"""
    return [
        SnapshotData(
            accounts=(AccountSnapshot(account_name="全部", holdings=(_h("096001", 2000.0),)),),
            total_value=0.0,
            total_cost=0.0,
            total_pnl=0.0,
            timestamp="20260701T090000",
        )
    ]


def _changes() -> list[dict]:
    """新增 002943（10000 元买入）+ 清仓 096001（20000 元卖出）。"""
    return [
        {
            "code": "002943",
            "name": "广发多因子灵活配置混合",
            "action": "新增",
            "base_shares": 0.0,
            "cand_shares": 500.0,
            "shares_diff": 500.0,
            "base_cost": 0.0,
            "cand_cost": 10000.0,
            "cost_diff": 10000.0,
            "base_weight": 0.0,
            "cand_weight": 10.0,
            "weight_delta_pct": 10.0,
        },
        {
            "code": "096001",
            "name": "某债券基金",
            "action": "清仓",
            "base_shares": 2000.0,
            "cand_shares": 0.0,
            "shares_diff": -2000.0,
            "base_cost": 20000.0,
            "cand_cost": 0.0,
            "cost_diff": -20000.0,
            "base_weight": 20.0,
            "cand_weight": 0.0,
            "weight_delta_pct": -20.0,
        },
    ]


def _whatif(*, with_backtest: bool = True) -> dict:
    data: dict = {
        "available": True,
        "changes": _changes(),
        "candidate": {"total_cost": 99000.0, "total_shares": 500.0, "holding_count": 2, "hhi": 0.5},
        "stats": {"added": 1, "removed": 1, "increased": 0, "decreased": 0, "unchanged": 0},
    }
    if with_backtest:
        data["backtest"] = {
            "available": True,
            "effective_date": "2026-10-01",
            "series": {
                "labels": ["2026-10-01", "2026-10-06"],
                "base": [100.0, 101.0],
                "candidate": [100.0, 105.0],
                "base_drawdown": [0.0, 0.0],
                "candidate_drawdown": [0.0, 0.0],
            },
        }
    return data


def _fee_index() -> dict:
    return {
        "002943": {"purchase": build_single_purchase_schedule(0.0015, source="f10_tier")},
        "096001": {"redemption": parse_redemption_fee_schedule(_redemption_rows())},
    }


def _index_bars() -> list[dict]:
    return [{"date": "2026-10-01", "close": 3000.0}, {"date": "2026-10-06", "close": 3300.0}]


def _build(data: dict | None = None, **overrides):
    """默认注入确定性 I/O；overrides 逐项覆盖。"""
    kwargs: dict = {
        "effective_date": "2026-10-01",
        "snapshots": _snapshots(),
        "count_trading_days": lambda start, end: 60,
        "fee_index": _fee_index(),
        "comparison_indices": _BENCH_POOL,
        "benchmark_text_getter": lambda code: "沪深300指数收益率×90%",
        "index_history_getter": lambda code, days: _index_bars(),
    }
    kwargs.update(overrides)
    return build_whatif_cost_panel(data if data is not None else _whatif(), **kwargs)


class TestCostPanelAssembly:
    """全量装配：成本本体 + impact 手算 + 基准三线 + 图表同源。"""

    def test_trade_cost_totals_and_legs(self) -> None:
        """买入 15 元 + 卖出 100 元（60 交易日落 [30,365) 档 0.50%）= 115 元。"""
        panel = _build()
        tc = panel["trade_cost"]
        assert panel["available"] is True
        assert tc["purchase_total"] == 15.0
        assert tc["redemption_total"] == 100.0
        assert tc["total_cost"] == 115.0
        assert tc["unknown_legs"] == 0 and tc["unmodeled_legs"] == 0
        assert tc["fees_complete"] is True
        buy = next(leg for leg in tc["legs"] if leg["side"] == SIDE_BUY)
        sell = next(leg for leg in tc["legs"] if leg["side"] == SIDE_SELL)
        assert buy["fee"] == 15.0 and buy["rate"] == 0.0015 and buy["rate_source"] == SRC_F10
        assert buy["booked_date"] == "2026-10-01" and buy["holding_days"] is None
        assert sell["fee"] == 100.0 and sell["rate"] == 0.005
        assert sell["holding_days"] == 60.0

    def test_impact_handcalc(self) -> None:
        """t0 一次性扣费：115/99000 → 成本后收益与收益差手算对照。"""
        panel = _build()
        impact = panel["impact"]
        assert impact is not None
        ratio = round(115.0 / 99000.0, 6)
        assert impact["fee_total"] == 115.0
        assert impact["cand_t0_value"] == 99000.0
        assert impact["t0_ratio"] == ratio
        assert impact["return_before_pct"] == 5.0
        expected_after = round(round(105.0 * (1.0 - ratio), 4) - 100.0, 2)
        assert impact["return_after_pct"] == expected_after
        assert impact["delta_pct_points"] == round(expected_after - 5.0, 2)
        assert impact["delta_pct_points"] < 0  # 成本只会压低收益

    def test_benchmark_resolved_and_aligned(self) -> None:
        """持仓文本匹配 sh000300；指数行情按标签 LOCF 对齐并归一化 100 基点。"""
        panel = _build()
        bench = panel["benchmark"]
        assert bench is not None
        assert bench["code"] == "sh000300" and bench["source"] == "holdings"
        assert bench["status"] == "ok"
        assert bench["values"] == [100.0, 110.0]  # 3000 → 3300

    def test_chart_shares_series_with_impact(self) -> None:
        """三线图数据与 impact 同源：成本后曲线 = 成本前 ×（1 − ratio）。"""
        panel = _build()
        chart = panel["chart"]
        impact = panel["impact"]
        assert chart is not None and impact is not None
        assert chart["labels"] == ["2026-10-01", "2026-10-06"]
        assert chart["base"] == [100.0, 101.0]
        assert chart["candidate_before"] == [100.0, 105.0]
        factor = 1.0 - impact["t0_ratio"]
        assert chart["candidate_after"] == [round(v * factor, 4) for v in (100.0, 105.0)]
        assert chart["benchmark"] == [100.0, 110.0]


class TestCostPanelGating:
    """前置条件门控：费率未知 / 无回测 / 未建模的契约行为。"""

    def test_unknown_fees_block_post_cost_numbers(self) -> None:
        """费率全未知 → 无 impact、无成本后曲线，但成本块与基准三线照常。"""
        panel = _build(fee_index={})
        tc = panel["trade_cost"]
        assert tc["fees_complete"] is False
        assert tc["unknown_legs"] == 2
        assert tc["total_cost"] == 0.0
        assert panel["impact"] is None
        assert panel["chart"]["candidate_after"] is None
        assert panel["chart"]["candidate_before"] == [100.0, 105.0]
        assert panel["benchmark"] is not None and panel["benchmark"]["status"] == "ok"

    def test_without_backtest_cost_block_only(self) -> None:
        """无回测 → impact/benchmark/chart 全缺席，成本本体照常（截面模式）。"""
        panel = _build(data=_whatif(with_backtest=False))
        assert panel["available"] is True
        assert panel["trade_cost"]["total_cost"] == 115.0
        assert panel["impact"] is None
        assert panel["benchmark"] is None
        assert panel["chart"] is None

    def test_stock_leg_marked_unmodeled(self) -> None:
        """股票腿显式标注未建模（不冒充 0 费率），基金腿照常建模。"""
        data = _whatif(with_backtest=False)
        data["changes"] = data["changes"] + [
            {
                "code": "600900",
                "name": "长江电力",
                "action": "减仓",
                "base_shares": 1000.0,
                "cand_shares": 400.0,
                "shares_diff": -600.0,
                "base_cost": 30000.0,
                "cand_cost": 12000.0,
                "cost_diff": -18000.0,
                "base_weight": 30.0,
                "cand_weight": 12.0,
                "weight_delta_pct": -18.0,
            }
        ]
        panel = _build(data=data)
        tc = panel["trade_cost"]
        stock_leg = next(leg for leg in tc["legs"] if leg["code"] == "600900")
        assert stock_leg["side"] == "unmodeled"
        assert stock_leg["rate"] is None and stock_leg["fee"] is None
        assert stock_leg["rate_source"] == "unmodeled"
        assert tc["unmodeled_legs"] == 1
        fund_leg = next(leg for leg in tc["legs"] if leg["code"] == "002943")
        assert fund_leg["side"] == SIDE_BUY and fund_leg["fee"] == 15.0

    def test_fee_fetch_receives_only_otc_fund_codes(self, monkeypatch) -> None:
        """费率装配只喂场外基金代码（股票/场内不进在线取数）。"""
        seen: dict = {}

        def _fake_fetch(codes):
            seen["codes"] = list(codes)
            return _fee_index()

        monkeypatch.setattr("src.python.fetcher.fund_fee.fetch_fee_index", _fake_fetch)
        data = _whatif(with_backtest=False)
        data["changes"] = data["changes"] + [
            {
                "code": "601398",
                "name": "工商银行",
                "action": "加仓",
                "base_shares": 1000.0,
                "cand_shares": 1500.0,
                "shares_diff": 500.0,
                "base_cost": 5000.0,
                "cand_cost": 7500.0,
                "cost_diff": 2500.0,
                "base_weight": 5.0,
                "cand_weight": 7.0,
                "weight_delta_pct": 2.0,
            }
        ]
        panel = _build(data=data, fee_index=None)
        assert seen["codes"] == ["002943", "096001"]
        assert panel["trade_cost"]["unmodeled_legs"] == 1


class TestCostFlipRegression:
    """先决门槛③（方向性翻转）固化回归：成本计入后结论翻转 ≥1 例。

    翻转机制（fixture 全固定、零实时数据）：换手约 30%（卖出 30000 @0.50%
    持有 60 交易日 + 买入 30000 @0.15%）= 195 元 ≈ 19.7bp；成本前目标持仓
    小幅领先基准（100.55 vs 100.40，+0.15pp），t0 扣费后
    （100.55×0.99803 = 100.3519）落后基准 → 「调 vs 不调」结论方向翻转。
    数值与合理性说明见设计文档先决门槛判定记录。
    """

    _BUY_AMOUNT = 30000.0
    _SELL_AMOUNT = 30000.0

    @classmethod
    def _flip_changes(cls) -> list[dict]:
        return [
            {
                "code": "002943",
                "name": "广发多因子灵活配置混合",
                "action": "新增",
                "base_shares": 0.0,
                "cand_shares": 1500.0,
                "shares_diff": 1500.0,
                "base_cost": 0.0,
                "cand_cost": cls._BUY_AMOUNT,
                "cost_diff": cls._BUY_AMOUNT,
                "base_weight": 0.0,
                "cand_weight": 30.0,
                "weight_delta_pct": 30.0,
            },
            {
                "code": "096001",
                "name": "某债券基金",
                "action": "清仓",
                "base_shares": 3000.0,
                "cand_shares": 0.0,
                "shares_diff": -3000.0,
                "base_cost": cls._SELL_AMOUNT,
                "cand_cost": 0.0,
                "cost_diff": -cls._SELL_AMOUNT,
                "base_weight": 30.0,
                "cand_weight": 0.0,
                "weight_delta_pct": -30.0,
            },
        ]

    @classmethod
    def _flip_panel(cls) -> dict:
        data = _whatif()
        data["changes"] = cls._flip_changes()
        data["candidate"]["total_cost"] = 99000.0
        data["backtest"]["series"]["base"] = [100.0, 100.4]  # 基准 +0.40%
        data["backtest"]["series"]["candidate"] = [100.0, 100.55]  # 目标 +0.55%（领先 0.15pp）
        data["backtest"]["series"]["base_drawdown"] = [0.0, 0.0]
        data["backtest"]["series"]["candidate_drawdown"] = [0.0, 0.0]
        snaps = [
            SnapshotData(
                accounts=(AccountSnapshot(account_name="全部", holdings=(_h("096001", 3000.0),)),),
                total_value=0.0,
                total_cost=0.0,
                total_pnl=0.0,
                timestamp="20260701T090000",
            )
        ]
        return _build(data=data, snapshots=snaps)

    def test_cost_flips_close_call_conclusion(self) -> None:
        """成本前目标领先 → 成本后目标落后：方向性翻转成立且幅度与成本量级一致。"""
        panel = self._flip_panel()
        impact = panel["impact"]
        chart = panel["chart"]
        assert impact is not None
        assert panel["trade_cost"]["total_cost"] == 195.0  # 45（买 0.15%）+ 150（卖 0.50%/60 日）
        assert chart["candidate_before"][-1] > chart["base"][-1], "成本前目标领先基准"
        assert chart["candidate_after"][-1] < chart["base"][-1], "成本后目标落后基准 → 方向性翻转"
        assert impact["t0_ratio"] < 0.01, "成本占比约 19.7bp（<1%），翻转量级合理"
        assert impact["delta_pct_points"] < 0

    def test_cost_flip_hand_arithmetic(self) -> None:
        """翻转算术手算对照：195/99000 扣减后期末值 100.3519 < 基准 100.40。"""
        panel = self._flip_panel()
        impact = panel["impact"]
        chart = panel["chart"]
        assert impact["t0_ratio"] == round(195.0 / 99000.0, 6)
        after_end = round(100.55 * (1.0 - impact["t0_ratio"]), 4)
        assert chart["candidate_after"][-1] == after_end
        assert after_end == 100.3519
        assert after_end < 100.4 < 100.55  # 成本前领先、成本后落后
        assert impact["delta_pct_points"] == round(round(after_end - 100.0, 2) - 0.55, 2)

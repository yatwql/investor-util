"""``analysis/financial_statement_derive.py`` 单元测试。

覆盖：三表 → 标准指标字段的口径与算术（营收/归母净利/毛利率/负债率/ROE/经营现金流/EPS）、
同比（上年同期对齐）、文种推断、降序与限流、缺表即空、脏值兜底、报告期回退。

运行：
  pytest src/test/unit/analysis/test_financial_statement_derive.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.financial_statement_derive import derive_indicator_records

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

#: 长江电力 2026 半年报 / 2026 一季报 / 2025 半年报（实测值，亿元级真实量纲）
_MS_2026Q2 = 1782748800000  # 2026-06-30
_MS_2026Q1 = 1774972800000  # 2026-03-31
_MS_2025Q2 = 1751212800000  # 2025-06-30


def _fy(period_ms: int) -> tuple[str, str]:
    """时间戳 → (fiscal_year, fiscal_period)，贴近上游真实响应的字段组合。"""
    from src.python.core.num_utils import ms_to_date_str

    date = ms_to_date_str(period_ms)  # 北京自然日
    year, month = int(date.split("-")[0]), int(date.split("-")[1])
    # 披露窗口起点也归到所属财季：Q1=3/4 月、Q2=6/7 月、Q3=9/10 月、Q4=12/1 月
    if month in (3, 4):
        return str(year), "Q1"
    if month in (6, 7):
        return str(year), "Q2"
    if month in (9, 10):
        return str(year), "Q3"
    return (str(year) if month == 12 else str(year - 1)), "Q4"


def _income(period_ms: int, revenue: float, net_profit: float, cost: float, eps: float) -> dict:
    year, fp = _fy(period_ms)
    return {
        "fiscal_year": year,
        "fiscal_period": fp,
        "period_end_ms": period_ms,
        "operating_income": revenue,
        "parent_holder_net_profit": net_profit,
        "operating_costs": cost,
        "basic_eps": eps,
    }


def _balance(period_ms: int, assets: float, debt: float, equity: float) -> dict:
    year, fp = _fy(period_ms)
    return {
        "fiscal_year": year,
        "fiscal_period": fp,
        "period_end_ms": period_ms,
        "assets_total": assets,
        "total_debt": debt,
        "holder_equity_total": equity,
    }


def _cashflow(period_ms: int, ocf: float) -> dict:
    year, fp = _fy(period_ms)
    return {"fiscal_year": year, "fiscal_period": fp, "period_end_ms": period_ms, "act_cash_flow_net": ocf}


class TestDerivation:
    """口径与算术：与主源 akshare 同报告期实测对齐（营收/净利/毛利率/负债率/现金流/EPS 完全一致）。"""

    def _records(self, **kw):
        args = {
            "income": {
                "item": [
                    _income(_MS_2026Q2, 37_929_268_927.18, 14_755_694_774.53, 15_971_160_694.54, 0.6031),
                    _income(_MS_2025Q2, 36_697_614_066.72, 13_056_000_000.0, 16_101_982_065.34, 0.5669),
                ]
            },
            "balance": {"item": [_balance(_MS_2026Q2, 600_000_000_000.0, 356_190_000_000.0, 228_000_000_000.0)]},
            "cashflow": {"item": [_cashflow(_MS_2026Q2, 24_128_313_774.37)]},
        }
        args.update(kw)
        return derive_indicator_records(code="600900", symbol="600900.SH", **args)

    def test_maps_amounts_and_derives_ratios(self):
        row = self._records()[0]
        assert row["report_period"] == "2026-06-30"
        assert row["doc_type"] == "semiannual"
        assert row["revenue"] == pytest.approx(37_929_268_927.18)
        assert row["net_profit"] == pytest.approx(14_755_694_774.53)
        assert row["gross_margin"] == pytest.approx(0.578923, abs=1e-5)
        assert row["debt_ratio"] == pytest.approx(0.59365, abs=1e-4)
        assert row["roe"] == pytest.approx(14_755_694_774.53 / 228_000_000_000.0)
        assert row["operating_cash_flow"] == pytest.approx(24_128_313_774.37)
        assert row["eps"] == pytest.approx(0.6031)
        assert row["source_api"] == "hithink"
        assert row["source"] == "同花顺金融数据"

    def test_revenue_yoy_against_same_quarter_prior_year(self):
        row = self._records()[0]
        assert row["revenue_yoy"] == pytest.approx((37_929_268_927.18 - 36_697_614_066.72) / 36_697_614_066.72)
        assert row["net_profit_yoy"] == pytest.approx((14_755_694_774.53 - 13_056_000_000.0) / 13_056_000_000.0)

    def test_yoy_none_without_prior_year(self):
        """上年同期缺失 → 同比 None（宁缺勿错，不臆造）。"""
        income = {"item": [_income(_MS_2026Q2, 100.0, 10.0, 60.0, 0.1)]}
        row = self._records(income=income)[0]
        assert row["revenue_yoy"] is None and row["net_profit_yoy"] is None

    def test_yoy_none_when_prior_base_is_zero(self):
        income = {
            "item": [
                _income(_MS_2026Q2, 100.0, 10.0, 60.0, 0.1),
                _income(_MS_2025Q2, 0.0, 0.0, 50.0, 0.0),
            ]
        }
        row = self._records(income=income)[0]
        assert row["revenue_yoy"] is None and row["net_profit_yoy"] is None

    def test_period_normalized_to_quarter_end_not_disclosure_start(self):
        """上游季度条目的时间戳是披露窗口起点（2026Q1 = 04-01）→ 必须归一到季末 03-31。

        否则同报告期与主源 akshare（标准季末）对不上，同比对齐与趋势比较都会错位。
        """
        income = {
            "item": [
                {
                    "fiscal_year": "2026",
                    "fiscal_period": "Q1",
                    "period_end_ms": 1774972800000,
                    "operating_income": 100.0,
                    "parent_holder_net_profit": 10.0,
                }
            ]
        }
        balance = {
            "item": [
                {
                    "fiscal_year": "2026",
                    "fiscal_period": "Q1",
                    "period_end_ms": 1774972800000,
                    "assets_total": 1000.0,
                    "total_debt": 500.0,
                    "holder_equity_total": 400.0,
                }
            ]
        }
        cashflow = {
            "item": [
                {
                    "fiscal_year": "2026",
                    "fiscal_period": "Q1",
                    "period_end_ms": 1774972800000,
                    "act_cash_flow_net": 30.0,
                }
            ]
        }
        row = self._records(income=income, balance=balance, cashflow=cashflow)[0]
        assert row["report_period"] == "2026-03-31"
        assert row["doc_type"] == "q1"

    @pytest.mark.parametrize(
        ("ms", "doc_type"),
        [(_MS_2026Q1, "q1"), (_MS_2026Q2, "semiannual"), (1759132800000, "q3"), (1767110400000, "annual")],
    )
    def test_doc_type_inferred_from_month(self, ms, doc_type):
        income = {"item": [_income(ms, 100.0, 10.0, 60.0, 0.1)]}
        balance = {"item": [_balance(ms, 1000.0, 500.0, 400.0)]}
        cashflow = {"item": [_cashflow(ms, 30.0)]}
        row = self._records(income=income, balance=balance, cashflow=cashflow)[0]
        assert row["doc_type"] == doc_type

    def test_bvps_always_none(self):
        """官方报表不给总股本 → 该源恒不产每股净资产（PB 不可用，已在模块文档串说明）。"""
        assert self._records()[0]["bvps"] is None


class TestRobustness:
    def _records(self, **kw):
        args = {
            "income": {"item": [_income(_MS_2026Q2, 100.0, 10.0, 60.0, 0.1)]},
            "balance": {"item": [_balance(_MS_2026Q2, 1000.0, 500.0, 400.0)]},
            "cashflow": {"item": [_cashflow(_MS_2026Q2, 30.0)]},
        }
        args.update(kw)
        return derive_indicator_records(code="600900", symbol="600900.SH", **args)

    @pytest.mark.parametrize("missing", ["income", "balance", "cashflow"])
    def test_any_missing_table_yields_empty(self, missing):
        """任一张表缺失 → 空列表（不产半份数据，由链路继续降级）。"""
        assert self._records(**{missing: {"item": []}}) == []
        assert self._records(**{missing: None}) == []

    def test_dirty_values_become_none_without_raising(self):
        income = {
            "item": [
                {
                    "period_end_ms": _MS_2026Q2,
                    "operating_income": "bad",
                    "parent_holder_net_profit": None,
                    "net_profit": "1e999",
                    "operating_costs": "50",
                    "basic_eps": "x",
                }
            ]
        }
        row = self._records(income=income)[0]
        assert row["revenue"] is None
        assert row["net_profit"] is None  # 归母缺失且合并净利非有限 → None
        assert row["gross_margin"] is None
        assert row["eps"] is None

    def test_period_fallback_and_skip(self):
        """报告期缺失：回退 period/publish_date_ms；仍不可得则跳过该期。"""
        income = {
            "item": [
                {"period": "2026-06-30", "operating_income": 100.0, "parent_holder_net_profit": 10.0},
                {"operating_income": 200.0, "parent_holder_net_profit": 20.0},  # 无任何报告期 → 跳过
            ]
        }
        balance = {
            "item": [
                {"period": "2026-06-30", "assets_total": 1000.0, "total_debt": 500.0, "holder_equity_total": 400.0}
            ]
        }
        cashflow = {"item": [{"period": "2026-06-30", "act_cash_flow_net": 30.0}]}
        records = self._records(income=income, balance=balance, cashflow=cashflow)
        assert [r["report_period"] for r in records] == ["2026-06-30"]

    def test_sorted_desc_and_limited(self):
        ms = {2026: _MS_2026Q2, 2025: _MS_2025Q2, 2024: 1719705600000}
        income = {
            "item": [_income(ms[y], 100.0 * i, 10.0 * i, 60.0, 0.1 * i) for i, y in enumerate((2024, 2025, 2026), 1)]
        }
        records = self._records(income=income, limit=2)
        assert [r["report_period"] for r in records] == ["2026-06-30", "2025-06-30"]

    def test_unexpected_structures_are_tolerated(self):
        assert derive_indicator_records("nope", [], {}, code="600900", symbol="600900.SH") == []

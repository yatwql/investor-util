"""analysis/financial_indicator.py（财务指标派生）单元测试。

覆盖：质量分档（四维均值 + 缺维跳过）、年度趋势（相邻年报、期数不足不给结论）、
当前 PE/PB（亏损/净资产非正/缺价留空）、趋势点截取。

运行：
  pytest src/test/unit/analysis/test_financial_indicator.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.financial_indicator import (
    annual_records,
    current_valuation,
    quality_grade,
    trend_label,
    trend_points,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

_GOOD = {
    "roe": 0.20,
    "gross_margin": 0.55,
    "debt_ratio": 0.25,
    "operating_cash_flow": 120.0,
    "net_profit": 100.0,
}

_WEAK = {
    "roe": 0.01,
    "gross_margin": 0.05,
    "debt_ratio": 0.95,
    "operating_cash_flow": 10.0,
    "net_profit": 100.0,
}


class TestQualityGrade:
    def test_all_dimensions_good_is_top_grade(self):
        grade, score = quality_grade(_GOOD)
        assert grade == "优"
        assert score == 3.0

    def test_all_dimensions_weak_is_bottom_grade(self):
        grade, score = quality_grade(_WEAK)
        assert grade == "弱"
        assert score is not None and score < 1.0

    def test_missing_dimensions_are_skipped_not_zeroed(self):
        """缺维度按「不参与」而非 0 分——否则缺数据会被误判为差。"""
        grade, score = quality_grade({"roe": 0.20})
        assert grade == "优"
        assert score == 3.0

    def test_empty_record_gives_no_grade(self):
        assert quality_grade(None) == ("", None)
        assert quality_grade({}) == ("", None)

    def test_cash_quality_requires_positive_profit(self):
        """净利 ≤ 0 时现金流覆盖无意义 → 该维度不参与。"""
        profitless = {"roe": 0.20, "operating_cash_flow": 1000.0, "net_profit": -5.0}
        assert quality_grade(profitless) == ("优", 3.0)


class TestAnnualRecordsAndTrend:
    def _series(self, *periods):
        return [
            {
                "report_period": p,
                "doc_type": "annual" if p.endswith("-12-31") else "q3",
                "revenue": v,
                "net_profit": v / 10,
            }
            for p, v in periods
        ]

    def test_annual_records_filters_and_sorts_within_annual(self):
        series = self._series(("2024-12-31", 100.0), ("2025-09-30", 999.0), ("2025-12-31", 130.0))
        annual = annual_records(series)
        assert [r["report_period"] for r in annual] == ["2025-12-31", "2024-12-31"]

    def test_growth_when_revenue_and_profit_both_up(self):
        assert trend_label(self._series(("2025-12-31", 130.0), ("2024-12-31", 100.0))) == "增长"

    def test_decline_when_both_down(self):
        assert trend_label(self._series(("2025-12-31", 70.0), ("2024-12-31", 100.0))) == "下滑"

    def test_flat_within_three_percent(self):
        assert trend_label(self._series(("2025-12-31", 101.0), ("2024-12-31", 100.0))) == "持平"

    def test_mixed_is_volatile(self):
        series = [
            {"report_period": "2025-12-31", "revenue": 130.0, "net_profit": 5.0},
            {"report_period": "2024-12-31", "revenue": 100.0, "net_profit": 10.0},
        ]
        assert trend_label(series) == "波动"

    def test_insufficient_annual_periods_gives_no_label(self):
        assert trend_label(self._series(("2025-12-31", 130.0))) == ""

    def test_quarterly_only_series_gives_no_label(self):
        """只有季报时不给年度趋势（避免把累计值当年度值比较）。"""
        series = [
            {"report_period": "2025-09-30", "revenue": 90.0},
            {"report_period": "2024-09-30", "revenue": 80.0},
        ]
        assert trend_label(series) == ""


class TestCurrentValuation:
    def test_pe_and_pb_from_price(self):
        pe, pb = current_valuation({"eps": 2.0, "bvps": 10.0}, 40.0)
        assert pe == pytest.approx(20.0)
        assert pb == pytest.approx(4.0)

    def test_loss_has_no_pe_but_keeps_pb(self):
        pe, pb = current_valuation({"eps": -1.0, "bvps": 10.0}, 40.0)
        assert pe is None
        assert pb == pytest.approx(4.0)

    def test_non_positive_bvps_has_no_pb(self):
        pe, pb = current_valuation({"eps": 2.0, "bvps": 0.0}, 40.0)
        assert pe == pytest.approx(20.0)
        assert pb is None

    def test_official_ttm_mrq_wins_over_self_calc(self):
        """官方 TTM/MRQ 优先：自算（现价 ÷ 报告期 EPS）在半年报上会明显虚高。

        实测长江电力：自算 46.4（28.0 ÷ 0.6031）vs 官方 pe_ttm 19.19 —— 混用会误导估值判断。
        """
        pe, pb = current_valuation({"eps": 0.6031, "bvps": 8.83, "pe_ttm": 19.188161, "pb_mrq": 3.21403}, 28.0)
        assert pe == pytest.approx(19.19)
        assert pb == pytest.approx(3.21)

    def test_partial_official_falls_back_per_field(self):
        """只给一个官方值时，另一项仍按自算兜底（逐字段而非全有全无）。"""
        pe, pb = current_valuation({"eps": 2.0, "bvps": 10.0, "pe_ttm": 12.5}, 40.0)
        assert pe == pytest.approx(12.5)
        assert pb == pytest.approx(4.0)

    def test_official_values_without_price_still_reported(self):
        """官方口径不依赖现价 → 无价时仍可给出 PE/PB。"""
        assert current_valuation({"pe_ttm": 19.188161, "pb_mrq": 3.21403}, None) == (19.19, 3.21)

    def test_dirty_official_values_are_ignored(self):
        pe, pb = current_valuation({"eps": 2.0, "bvps": 10.0, "pe_ttm": "bad", "pb_mrq": float("nan")}, 40.0)
        assert pe == pytest.approx(20.0) and pb == pytest.approx(4.0)

    def test_missing_price_or_record_is_empty(self):
        assert current_valuation({"eps": 2.0}, None) == (None, None)
        assert current_valuation(None, 40.0) == (None, None)


class TestTrendPoints:
    def test_limit_and_field_mapping(self):
        series = [
            {"report_period": f"2025-1{i}-31", "revenue": i, "net_profit": i / 2, "roe": 0.1} for i in range(1, 7)
        ]
        points = trend_points(series, limit=3)
        assert len(points) == 3
        assert set(points[0]) == {"report_period", "doc_type", "revenue", "net_profit", "roe"}
        assert points[0]["revenue"] == 1

    def test_empty_series(self):
        assert trend_points(None) == []
        assert trend_points([]) == []

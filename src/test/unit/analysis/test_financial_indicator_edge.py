"""analysis/financial_indicator.py 边缘场景测试。

覆盖：分档阈值边界、脏数值（NaN/±inf）不计分、零基数/缺字段趋势、
非正现价、档位区间边界。

运行：
  pytest src/test/unit/analysis/test_financial_indicator_edge.py -v
"""

from __future__ import annotations


import pytest

from src.python.analysis.financial_indicator import (
    current_valuation,
    quality_grade,
    trend_label,
    trend_points,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


class TestThresholdBoundaries:
    @pytest.mark.parametrize(
        ("roe", "expected"),
        [(0.15, 3.0), (0.1499, 2.0), (0.08, 2.0), (0.0799, 1.0), (0.03, 1.0), (0.0299, 0.0)],
    )
    def test_roe_threshold_ladder(self, roe, expected):
        """ROE 单维度阈值阶梯（含边界值本身归高档）。"""
        assert quality_grade({"roe": roe}) == (
            ("优" if expected >= 2.5 else "良" if expected >= 1.75 else "中" if expected >= 1 else "弱"),
            expected,
        )

    @pytest.mark.parametrize(
        ("debt", "expected"),
        [(0.40, 3.0), (0.4001, 2.0), (0.60, 2.0), (0.6001, 1.0), (0.80, 1.0), (0.8001, 0.0)],
    )
    def test_debt_ratio_is_lower_better(self, debt, expected):
        _, score = quality_grade({"debt_ratio": debt})
        assert score == expected

    def test_cash_quality_threshold_ladder(self):
        base = {"net_profit": 100.0}
        assert quality_grade({**base, "operating_cash_flow": 100.0})[1] == 3.0  # 覆盖 1.0 → 优
        assert quality_grade({**base, "operating_cash_flow": 50.0})[1] == 1.0  # 覆盖 0.5 → 中
        assert quality_grade({**base, "operating_cash_flow": 1.0})[1] == 0.0  # 覆盖 0.01 → 弱

    def test_grade_ladder_from_score(self):
        """均值分档边界：2.5/1.75/1.0。"""
        assert quality_grade({"roe": 0.20, "gross_margin": 0.55})[0] == "优"
        assert quality_grade({"roe": 0.10, "gross_margin": 0.30})[0] == "良"
        assert quality_grade({"roe": 0.05, "gross_margin": 0.15})[0] == "中"


class TestDirtyValues:
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "n/a", None, object()])
    def test_dirty_values_are_not_scored(self, bad):
        """脏值既不参与计分也不当 0 分（缺维度即跳过）。"""
        assert quality_grade({"roe": bad}) == ("", None)
        assert quality_grade({"roe": bad, "gross_margin": 0.55})[0] in ("优", "良")

    def test_dirty_values_do_not_break_pe_pb(self):
        pe, pb = current_valuation({"eps": float("nan"), "bvps": 10.0}, 40.0)
        assert pe is None
        assert pb == pytest.approx(4.0)

    def test_non_positive_or_dirty_price_is_rejected(self):
        record = {"eps": 2.0, "bvps": 10.0}
        for price in (0.0, -5.0, float("nan"), float("inf"), None, "abc"):
            assert current_valuation(record, price) == (None, None)


class TestTrendEdges:
    def test_zero_previous_value_skips_that_metric(self):
        """上年为 0 的指标不参与（避免除零），其余指标可照常给结论。"""
        series = [
            {"report_period": "2025-12-31", "revenue": 100.0, "net_profit": 10.0},
            {"report_period": "2024-12-31", "revenue": 0.0, "net_profit": 10.0},
        ]
        assert trend_label(series) == "持平"

    def test_all_metrics_zero_base_gives_no_label(self):
        series = [
            {"report_period": "2025-12-31", "revenue": 100.0, "net_profit": 10.0},
            {"report_period": "2024-12-31", "revenue": 0.0, "net_profit": 0.0},
        ]
        assert trend_label(series) == ""

    def test_missing_fields_give_no_label(self):
        series = [
            {"report_period": "2025-12-31"},
            {"report_period": "2024-12-31"},
        ]
        assert trend_label(series) == ""

    def test_only_dirty_values_give_no_label(self):
        series = [
            {"report_period": "2025-12-31", "revenue": float("nan"), "net_profit": float("inf")},
            {"report_period": "2024-12-31", "revenue": 100.0, "net_profit": 10.0},
        ]
        assert trend_label(series) == ""

    def test_single_annual_with_dirty_period_sorting(self):
        """报告期缺失/异常的记录不参与年度比较。"""
        series = [
            {"report_period": "", "revenue": 1.0, "net_profit": 1.0},
            {"report_period": "2025-12-31", "revenue": 130.0, "net_profit": 13.0},
        ]
        assert trend_label(series) == ""

    def test_trend_points_tolerates_dirty_fields(self):
        points = trend_points([{"report_period": "2025-12-31", "revenue": float("inf"), "net_profit": None}])
        assert points[0]["revenue"] is None
        assert points[0]["net_profit"] is None
        assert points[0]["roe"] is None

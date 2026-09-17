"""估值分位边界场景测试（edge，必须放 *_edge.py）。

覆盖：恒平序列 / 当前价越界 / 空序列 / NaN 输入；真实估值分位（TTM）的
脏值基本面 / 非正价格 / 生效日边界 / 不可解析日期。
"""

from __future__ import annotations

import pytest

from src.python.analysis.valuation_percentile import (
    build_fundamental_points,
    build_valuation_series,
    compute_real_valuation,
    price_percentile,
    value_percentile,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


class TestPricePercentileEdge:
    def test_all_identical_closes(self):
        """恒平序列：全部等于当前价 → 分位 100%。"""
        closes = [5.0] * 100
        assert price_percentile(closes) == 100.0

    def test_current_below_all(self):
        """当前价低于全部历史 → 分位 ~0%（不含任何样本）。"""
        closes = [float(i) for i in range(1, 101)]
        pct = price_percentile(closes, current=0.5)
        assert pct is not None
        assert pct == 0.0

    def test_current_above_all(self):
        """当前价高于全部历史 → 分位 100%。"""
        closes = [float(i) for i in range(1, 101)]
        assert price_percentile(closes, current=999.0) == 100.0

    def test_zero_length(self):
        assert price_percentile([]) is None

    def test_nan_current(self):
        """NaN 当前价 → 返回 None（不硬算）。"""
        closes = [float(i) for i in range(1, 101)]
        assert price_percentile(closes, current=float("nan")) is None

    def test_inf_current(self):
        """无穷当前价 → 返回 None（不硬算）。"""
        closes = [float(i) for i in range(1, 101)]
        assert price_percentile(closes, current=float("inf")) is None


def _flat_bars(days: int, close: float = 20.0) -> list[dict]:
    """构造 2025-05 起的逐日收盘价（晚于年报生效日 2025-04-30）。"""
    import datetime

    base = datetime.date(2025, 5, 1)
    return [{"date": (base + datetime.timedelta(days=i)).isoformat(), "close": close} for i in range(days)]


def _year(eps=2.0, bvps=10.0) -> list[dict]:
    return [{"report_period": "2024-12-31", "doc_type": "annual", "eps": eps, "bvps": bvps}]


class TestRealValuationEdge:
    def test_dirty_fundamentals_are_ignored(self):
        """NaN/±inf 的 EPS/BVPS 视为缺失（不参与序列，也不当 0）。"""
        recs = [{"report_period": "2024-12-31", "eps": float("nan"), "bvps": float("inf")}]
        points = build_fundamental_points(recs)
        assert points[0].ttm_eps is None
        assert points[0].bvps is None
        assert build_valuation_series(_flat_bars(120), points) == ([], [])

    def test_non_positive_or_unparsable_price_bars_skipped(self):
        recs = _year()
        points = build_fundamental_points(recs)
        bars = [
            {"date": "2025-05-06", "close": 0.0},
            {"date": "2025-05-07", "close": -3.0},
            {"date": "2025-05-08", "close": float("nan")},
            {"date": "bad-date", "close": 20.0},
            {"date": "2025-05-09", "close": 20.0},
        ]
        pe, pb = build_valuation_series(bars, points)
        assert pe == [pytest.approx(10.0)]
        assert pb == [pytest.approx(2.0)]

    def test_deadline_boundary_is_inclusive(self):
        """生效日当天即计入（含边界）。"""
        points = build_fundamental_points(_year())
        bars = [{"date": "2025-04-29", "close": 20.0}, {"date": "2025-04-30", "close": 20.0}]
        pe, _ = build_valuation_series(bars, points)
        assert len(pe) == 1

    def test_zero_or_negative_current_value_has_no_percentile(self):
        values = [1.0] * 100
        assert value_percentile(values, 0.0) is None
        assert value_percentile(values, -5.0) is None
        assert value_percentile(values, float("inf")) is None

    def test_empty_values_have_no_percentile(self):
        assert value_percentile([], 1.0) is None

    def test_no_overlap_between_bars_and_fundamentals(self):
        """价格区间早于任何生效日 → 序列为空（no_overlap）。"""
        recs = _year()
        bars = [{"date": "2025-01-03", "close": 20.0}]
        out = compute_real_valuation(bars, recs)
        assert out["available"] is False
        assert out["reason"] in ("no_overlap", "insufficient_samples")

    def test_current_price_falls_back_to_last_close(self):
        out = compute_real_valuation(_flat_bars(120, close=20.0), _year())
        assert out["available"] is True
        assert out["pe_ttm"] == pytest.approx(2.0)
        assert out["pb"] == pytest.approx(10.0)

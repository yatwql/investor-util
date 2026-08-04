"""估值分位边界场景测试（edge，必须放 *_edge.py）。

覆盖：恒平序列 / 当前价越界 / 阈值边界 / 空序列 / NaN 输入。
"""

from __future__ import annotations

import pytest

from src.python.analysis.valuation_percentile import (
    price_percentile,
    tier_from_percentile,
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

    def test_tier_boundary_30(self):
        assert tier_from_percentile(30.0) == "合理"

    def test_tier_boundary_70(self):
        assert tier_from_percentile(70.0) == "合理"

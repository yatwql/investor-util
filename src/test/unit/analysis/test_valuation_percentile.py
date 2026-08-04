"""估值分位纯计算层单元测试（价格分位代理层）。

覆盖：收盘价提取 / 价格分位解析解 / 三档刻度映射 / 数据不足 / 显式局限标注。
"""

from __future__ import annotations

import pytest

from src.python.analysis.valuation_percentile import (
    DISCLAIMER,
    MIN_SAMPLES,
    compute_price_percentile,
    extract_closes,
    price_percentile,
    tier_from_percentile,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


class TestExtractCloses:
    def test_close_key_preferred(self):
        """股票 K 线优先取 close 字段。"""
        bars = [
            {"date": "2024-01-01", "close": 10.0, "nav": 11.0},
            {"date": "2024-01-02", "close": 10.5, "nav": 11.2},
        ]
        assert extract_closes(bars) == [10.0, 10.5]

    def test_nav_fallback_for_fund(self):
        """场外基金净值 bars 无 close 时回退 nav。"""
        bars = [{"date": "2024-01-01", "nav": 1.2}, {"date": "2024-01-02", "nav": 1.3}]
        assert extract_closes(bars) == [1.2, 1.3]

    def test_filters_none_and_nan(self):
        """过滤 None/NaN/非数值字段。"""
        bars = [
            {"date": "2024-01-01", "close": 10.0},
            {"date": "2024-01-02", "close": None},
            {"date": "2024-01-03", "close": float("nan")},
            {"date": "2024-01-04", "close": 11.0},
        ]
        assert extract_closes(bars) == [10.0, 11.0]

    def test_empty_bars(self):
        assert extract_closes([]) == []


class TestPricePercentile:
    def test_analytic_series_midpoint(self):
        """固定 fixture：严格递增 750 日序列，第 375 个值分位恰为 50.0%。"""
        closes = [float(i) for i in range(1, 751)]
        pct = price_percentile(closes, current=375.0)
        assert pct is not None
        assert abs(pct - 50.0) < 0.5  # 解析解误差 < 0.5%

    def test_analytic_series_quarter(self):
        """递增 400 日序列，第 100 个值分位 = 100/400 = 25.0%。"""
        closes = [float(i) for i in range(1, 401)]
        pct = price_percentile(closes, current=100.0)
        assert pct is not None
        assert abs(pct - 25.0) < 0.5

    def test_current_last_by_default(self):
        """current 缺省时取序列末值 → 分位 100%。"""
        closes = [1.0, 2.0, 3.0, 4.0, 5.0] * 20  # 100 个样本
        assert price_percentile(closes) == 100.0

    def test_insufficient_samples_returns_none(self):
        """样本不足（< MIN_SAMPLES）返回 None。"""
        assert price_percentile([1.0, 2.0]) is None

    def test_min_samples_threshold(self):
        """恰好达到 MIN_SAMPLES 可计算。"""
        closes = [float(i) for i in range(MIN_SAMPLES)]
        assert price_percentile(closes) is not None

    def test_low_end(self):
        """最低价 → 分位 ~1%（含自身）。"""
        closes = [float(i) for i in range(1, 101)]
        assert abs(price_percentile(closes, current=1.0) - 1.0) < 0.5

    def test_high_end(self):
        """最高价 → 分位 100%。"""
        closes = [float(i) for i in range(1, 101)]
        assert price_percentile(closes, current=100.0) == 100.0


class TestTierFromPercentile:
    def test_low(self):
        assert tier_from_percentile(10.0) == "低估"

    def test_fair(self):
        assert tier_from_percentile(50.0) == "合理"

    def test_high(self):
        assert tier_from_percentile(85.0) == "高估"

    def test_low_boundary_below(self):
        assert tier_from_percentile(29.99) == "低估"

    def test_high_boundary_above(self):
        assert tier_from_percentile(70.01) == "高估"

    def test_boundary_30_is_fair(self):
        assert tier_from_percentile(30.0) == "合理"

    def test_boundary_70_is_fair(self):
        assert tier_from_percentile(70.0) == "合理"


class TestComputePricePercentile:
    def test_available_with_tier(self):
        """正常返回：分位 + 三档刻度 + 样本数。"""
        bars = [{"date": f"d{i}", "close": float(i)} for i in range(1, 101)]
        result = compute_price_percentile(bars)
        assert result["available"] is True
        assert result["price_percentile"] == 100.0
        assert result["tier"] == "高估"
        assert result["sample_count"] == 100
        assert result["reason"] is None

    def test_insufficient(self):
        """样本不足 → available=False + 原因。"""
        result = compute_price_percentile([{"date": "d1", "close": 1.0}])
        assert result["available"] is False
        assert result["reason"] == "insufficient_samples"

    def test_no_bars(self):
        """空序列 → available=False + 原因。"""
        result = compute_price_percentile([])
        assert result["available"] is False
        assert result["reason"] == "no_bars"


class TestDisclaimer:
    def test_proxy_disclaimer_present(self):
        """显式局限标注必须出现（合规断言）。"""
        assert "价格分位代理" in DISCLAIMER
        assert "非真实历史估值分位" in DISCLAIMER

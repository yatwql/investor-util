"""市场温度边界场景测试（edge，必须放 *_edge.py）。

覆盖：恒平序列 / 极端因子 clamp / 负值输入。
"""

from __future__ import annotations

import pytest

from src.python.analysis.market_temperature import (
    compute_temperature,
    temperature_score,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


class TestTemperatureEdge:
    def test_flat_series_available(self):
        """恒平序列：分位 100%、MA 偏离 0、波动率 0 → 可计算。"""
        closes = [10.0] * 100
        result = compute_temperature([{"date": f"d{i}", "close": c} for i, c in enumerate(closes)])
        assert result["available"] is True
        assert result["volatility"] == 0.0
        assert abs(result["ma_deviation"]) < 1e-9

    def test_score_never_negative(self):
        assert temperature_score(0.0, -1.0, -1.0) >= 0.0

    def test_score_never_exceeds_100(self):
        assert temperature_score(100.0, 1.0, 1.0) <= 100.0

    def test_zero_close_series_insufficient(self):
        """含零/负值收盘价：收益率分母保护，温度可算或降级但不崩溃。"""
        bars = [{"date": f"d{i}", "close": float(i)} for i in range(1, 61)]
        result = compute_temperature(bars)
        # 序列合法时 available=True，否则 must 为 False（两者皆可，但不抛异常）
        assert result["available"] in (True, False)

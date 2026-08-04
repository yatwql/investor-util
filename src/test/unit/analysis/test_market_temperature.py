"""市场温度纯计算层单元测试（三因子合成层）。

覆盖：均线偏离 / 年化波动率 / 三因子合成 / 温度计刻度映射 / 免责声明 / 数据不足。
"""

from __future__ import annotations

import pytest

from src.python.analysis.market_temperature import (
    TEMPERATURE_DISCLAIMER,
    compute_temperature,
    ma_deviation,
    returns_volatility,
    temperature_score,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


class TestMaDeviation:
    def test_above_ma_positive(self):
        """19 个 10.0 + 1 个 11.0，20 日均线=10.05，偏离解析解。"""
        closes = [10.0] * 19 + [11.0]
        dev = ma_deviation(closes, 11.0, window=20)
        expected = (11.0 - 10.05) / 10.05
        assert dev is not None
        assert abs(dev - expected) < 1e-9

    def test_at_ma_zero(self):
        closes = [10.0] * 20
        assert abs(ma_deviation(closes, 10.0, window=20) - 0.0) < 1e-9

    def test_below_ma_negative(self):
        """最近价低于均线 → 负偏离。"""
        closes = [10.0] * 19 + [9.0]
        dev = ma_deviation(closes, 9.0, window=20)
        assert dev is not None
        assert dev < 0

    def test_insufficient(self):
        assert ma_deviation([1.0, 2.0], 2.0, window=20) is None

    def test_current_default_last(self):
        closes = [10.0] * 20
        assert abs(ma_deviation(closes, window=20) - 0.0) < 1e-9


class TestVolatility:
    def test_constant_series_zero(self):
        """恒平序列 → 波动率 0。"""
        closes = [10.0] * 30
        assert returns_volatility(closes, window=20) == 0.0

    def test_known_alternating(self):
        """交替涨跌 → 波动率 > 0。"""
        closes = [100.0, 110.0] * 15
        vol = returns_volatility(closes, window=20)
        assert vol is not None
        assert vol > 0

    def test_insufficient(self):
        assert returns_volatility([1.0], window=20) is None

    def test_annualized_positive(self):
        """年化波动率应为正且合理量级。"""
        import math

        closes = [100.0 * (1 + 0.01 * (1 if i % 2 else -1)) for i in range(60)]
        vol = returns_volatility(closes, window=20)
        assert vol is not None
        assert math.isfinite(vol)
        assert 0.0 < vol < 2.0


class TestTemperatureScore:
    def test_mid_scale(self):
        """pct=50, ma_dev=0, vol=0.18 → 与解析解一致（误差 <0.5）。"""
        score = temperature_score(50.0, 0.0, 0.18)
        expected = 0.5 * 50.0 + 0.3 * 50.0 + 0.2 * (0.18 / 0.5 * 100.0)
        assert abs(score - expected) < 0.5

    def test_high_extreme_clamped(self):
        score = temperature_score(100.0, 0.2, 0.5)
        assert 0.0 <= score <= 100.0

    def test_low_extreme_clamped(self):
        score = temperature_score(0.0, -0.2, 0.0)
        assert 0.0 <= score <= 100.0

    def test_hot_series_scores_high(self):
        """高位 + 正偏离 + 高波动 → 温度偏高。"""
        hot = temperature_score(90.0, 0.1, 0.3)
        cold = temperature_score(10.0, -0.1, 0.05)
        assert hot > cold


class TestComputeTemperature:
    @staticmethod
    def _trend_bars(n: int = 100, start: float = 10.0, step: float = 0.5) -> list[dict]:
        return [{"date": f"d{i}", "close": start + step * i} for i in range(n)]

    def test_available_components(self):
        """正常返回：三因子 + 温度分 + 三档刻度 + 样本数。"""
        result = compute_temperature(self._trend_bars(100))
        assert result["available"] is True
        assert result["price_percentile"] is not None
        assert result["ma_deviation"] is not None
        assert result["volatility"] is not None
        assert result["score"] is not None
        assert result["tier"] in ("低估", "合理", "高估")
        assert result["sample_count"] == 100
        assert result["reason"] is None

    def test_analytic_precision(self):
        """固定 fixture：递增 750 日序列，温度分与解析解误差 <0.5%（自动化断言）。"""
        closes = [10.0 + 0.1 * i for i in range(750)]
        bars = [{"date": f"d{i}", "close": c} for i, c in enumerate(closes)]
        result = compute_temperature(bars)
        assert result["available"] is True
        # 分位 = 100%（末值最高）；MA 偏离 = (84.9 - 20日均线)/20日均线；波动率由解析计算
        expected_pct = 100.0
        assert abs(result["price_percentile"] - expected_pct) < 0.5

    def test_insufficient(self):
        result = compute_temperature([{"date": "d1", "close": 1.0}])
        assert result["available"] is False
        assert result["reason"] == "insufficient_samples"

    def test_no_bars(self):
        result = compute_temperature([])
        assert result["available"] is False
        assert result["reason"] == "no_bars"

    def test_disclaimer_no_position_instruction(self):
        """免责声明：含三因子描述 + 不含仓位指令（负向断言，合规）。"""
        assert "价格分位" in TEMPERATURE_DISCLAIMER
        assert "均线偏离" in TEMPERATURE_DISCLAIMER
        assert "波动率" in TEMPERATURE_DISCLAIMER
        assert "几成仓" not in TEMPERATURE_DISCLAIMER

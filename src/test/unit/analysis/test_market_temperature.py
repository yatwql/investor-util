"""市场温度纯计算层单元测试（三因子合成层）。

覆盖：均线偏离 / 年化波动率 / 三因子合成 / 温度计刻度映射 / 免责声明 / 数据不足。
"""

from __future__ import annotations

import pytest

from src.python.analysis.market_temperature import (
    TEMPERATURE_DISCLAIMER,
    build_erp_series,
    compute_temperature,
    ma_deviation,
    returns_volatility,
    temperature_score,
    unavailable_temperature,
    valuation_percentile,
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
        """pct=50, ma_dev=0, vol=0.18 → 与解析解一致（误差 <0.5；vol 分量反向）。"""
        score = temperature_score(50.0, 0.0, 0.18)
        expected = 0.5 * 50.0 + 0.3 * 50.0 + 0.2 * ((1.0 - 0.18 / 0.5) * 100.0)
        assert abs(score - expected) < 0.5

    def test_high_extreme_clamped(self):
        score = temperature_score(100.0, 0.2, 0.5)
        assert 0.0 <= score <= 100.0

    def test_low_extreme_clamped(self):
        score = temperature_score(0.0, -0.2, 0.0)
        assert 0.0 <= score <= 100.0

    def test_hot_series_scores_high(self):
        """高位 + 正偏离主导 → 温度偏高（波动率反向后不改变主导结论）。"""
        hot = temperature_score(90.0, 0.1, 0.3)
        cold = temperature_score(10.0, -0.1, 0.05)
        assert hot > cold

    def test_volatility_direction_reversed(self):
        """波动率分量反向：其余因子相同，波动越高温度越低（恐慌降温口径回归锁定）。"""
        calm = temperature_score(50.0, 0.0, 0.05)
        panicked = temperature_score(50.0, 0.0, 0.45)
        assert panicked < calm

        # 同向旧口径陷阱回归：高波动不得再抬高温度（曾把低估区推高 +20 分）
        assert temperature_score(20.0, -0.1, 0.5) < temperature_score(20.0, -0.1, 0.0)


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


class TestBuildErpSeries:
    """build_erp_series：PE 月频 × rf 日频按日期 asof 对齐（不得序号错位配对）。"""

    def test_asof_alignment(self):
        """每个 PE 日期取 ≤ 该日最近 rf；晚于所有 PE 点的 rf 不参与。"""
        pe_rows = [
            {"date": "2026-01-31", "pe": 10.0},
            {"date": "2026-02-28", "pe": 20.0},
        ]
        rf_rows = [
            {"date": "2025-12-31", "rate": 0.02},
            {"date": "2026-02-10", "rate": 0.03},
            {"date": "2026-03-15", "rate": 0.04},
        ]
        # 解析解：1/10−0.02=0.08；2 月点取 2/10 的 0.03 → 1/20−0.03=0.02（非 3 月的 0.04）
        assert build_erp_series(pe_rows, rf_rows) == pytest.approx([0.08, 0.02])

    def test_pe_before_first_rf_skipped(self):
        """首个 rf 之前的历史 PE 点无 rf 可用 → 跳过（不误配）。"""
        pe_rows = [
            {"date": "2020-01-31", "pe": 10.0},
            {"date": "2026-01-31", "pe": 12.0},
        ]
        rf_rows = [{"date": "2025-12-31", "rate": 0.02}]
        assert build_erp_series(pe_rows, rf_rows) == pytest.approx([1 / 12 - 0.02])

    def test_empty_inputs(self):
        assert build_erp_series([], [{"date": "d", "rate": 0.02}]) == []
        assert build_erp_series([{"date": "d", "pe": 10.0}], []) == []

    def test_invalid_rf_skipped(self):
        """None/越界 rf（非小数）不参与，取下一个合法值。"""
        rf_rows = [
            {"date": "2025-01-01", "rate": None},
            {"date": "2025-06-01", "rate": 1.5},
            {"date": "2025-12-01", "rate": 0.02},
        ]
        pe_rows = [{"date": "2026-01-31", "pe": 10.0}]
        assert build_erp_series(pe_rows, rf_rows) == pytest.approx([0.08])


class TestValuationPercentile:
    """valuation_percentile：PE/PB/ERP 各自历史分位等权平均。"""

    @staticmethod
    def _ascending(n: int = 60, base: float = 1.0) -> list[float]:
        return [base + i for i in range(n)]

    def test_equal_weight_available_components(self):
        """PE 升序（末值最高 → 100）+ PB 降序（末值最低）→ 等权平均。"""
        pe = self._ascending()
        pb = list(reversed(self._ascending()))
        result = valuation_percentile(pe, pb, None)
        assert result is not None
        assert result["components"]["pe"] == pytest.approx(100.0)
        assert result["components"]["erp"] is None
        expected = (100.0 + result["components"]["pb"]) / 2
        assert result["percentile"] == pytest.approx(round(expected, 2))

    def test_single_component_fallback(self):
        """仅 PE 可用 → 分位即 PE 分位（分母只算可用项）。"""
        pe = self._ascending()
        result = valuation_percentile(pe, None, None)
        assert result["percentile"] == pytest.approx(result["components"]["pe"])

    def test_all_insufficient_returns_none(self):
        assert valuation_percentile([1.0, 2.0], None, None) is None
        assert valuation_percentile(None, None, None) is None

    def test_non_positive_pe_excluded(self):
        """非正 PE（亏损期）全部剔除 → 该项缺席 → 整体 None。"""
        assert valuation_percentile([-1.0] * 70, None, None) is None


class TestComputeTemperatureValuationPath:
    """compute_temperature 第一因子：估值分位优先，缺席回落点位分位。"""

    @staticmethod
    def _bars(n: int = 100) -> list[dict]:
        return [{"date": f"d{i}", "close": 10.0 + 0.1 * i} for i in range(n)]

    @staticmethod
    def _ascending(n: int = 60) -> list[float]:
        return [1.0 + i for i in range(n)]

    def test_valuation_first_factor(self):
        result = compute_temperature(
            self._bars(),
            pe_series=self._ascending(),
            pb_series=self._ascending(),
            erp_values=self._ascending(),
        )
        assert result["available"] is True
        assert result["first_factor"] == "valuation"
        assert result["valuation_percentile"] == pytest.approx(100.0)
        assert result["price_percentile"] is not None  # 仍保留（展示/回落双轨）
        assert result["valuation_components"]["pe"] == pytest.approx(100.0)
        # 估值分位 100 主导第一因子 → 分数应等于以估值分位合成的解析解
        expected = temperature_score(100.0, result["ma_deviation"], result["volatility"])
        assert result["score"] == pytest.approx(expected, abs=0.5)

    def test_price_proxy_when_valuation_absent(self):
        """估值序列不可得 → 回落点位分位，分数与旧口径一致（=改造前行为）。"""
        result = compute_temperature(self._bars())
        assert result["first_factor"] == "price_proxy"
        assert result["valuation_percentile"] is None
        assert result["valuation_components"] is None
        expected = temperature_score(result["price_percentile"], result["ma_deviation"], result["volatility"])
        assert result["score"] == pytest.approx(expected, abs=0.05)

    def test_partial_valuation_still_prefers_valuation(self):
        """仅 PE 可用 → 仍走估值路径（分母只算可用项）。"""
        result = compute_temperature(self._bars(), pe_series=self._ascending())
        assert result["first_factor"] == "valuation"
        assert result["valuation_components"]["pb"] is None
        assert result["valuation_components"]["erp"] is None

    def test_unavailable_contract_keys(self):
        """不可用契约同步新增键（估值键为 None，消费方免判存在性）。"""
        data = unavailable_temperature("insufficient")
        assert data["available"] is False
        assert data["valuation_percentile"] is None
        assert data["valuation_components"] is None
        assert data["first_factor"] is None

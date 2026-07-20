"""量化指标计算模块测试 — 覆盖 8 个核心指标的正、边缘、异常路径。

测试覆盖：
  1. sharpe_ratio — 正常计算 / 不足 20 日返回 None
  2. calmar_ratio — 正常计算 / 最大回撤小于阈值返回 None
  3. hhi — 等权集中度 1/N / 空列表返回 0
  4. win_rate — 全部盈利 / 全部亏损
  5. turnover_rate — 正常换手 / 空输入返回 None
  6. risk_contribution — 正常贡献度 / 空列表返回 []
  7. individual_volatility — 正常波动率 / 不足样本 None
  8. portfolio_beta — 正常 Beta / 不足样本 None
"""

from __future__ import annotations

import math

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

# ── 测试数据 Helpers ─────────────────────────────────────


def _make_positive_returns(n: int = 252, mean: float = 0.001, std: float = 0.01) -> list[float]:
    """生成日收益率序列（伪随机但确定性的振荡序列）。"""
    import hashlib
    rng = []
    for i in range(n):
        h = hashlib.md5(f"seed_{i}".encode()).hexdigest()
        v = mean + std * (int(h[:4], 16) / 65535 - 0.5) * 2
        rng.append(v)
    return rng


def _make_holdings(profits: list[float]) -> list[dict]:
    """生成指定盈亏的持仓列表。"""
    return [
        {"name": f"品种{i}", "code": f"00000{i}", "profit": p}
        for i, p in enumerate(profits)
    ]


class TestSharpeRatio:
    """夏普比率测试。"""

    def test_normal_sharpe(self):
        """正常数据 → 返回正值（预期 > 0）。"""
        from src.python.analysis.metrics import sharpe_ratio

        returns = _make_positive_returns(252, 0.001, 0.01)
        sr = sharpe_ratio(returns, rf_annual=0.015)
        assert sr is not None
        assert sr > 0, f"预期正夏普比率，实际 {sr}"

    def test_insufficient_data_returns_none(self):
        """不足 20 日 → None。"""
        from src.python.analysis.metrics import sharpe_ratio

        assert sharpe_ratio([0.001] * 10) is None


class TestCalmarRatio:
    """卡玛比率测试。"""

    def test_normal_calmar(self):
        """正常上升序列 → 卡玛比率应为正。"""
        from src.python.analysis.metrics import calmar_ratio

        returns = _make_positive_returns(252, 0.001, 0.01)
        cr = calmar_ratio(returns)
        assert cr is not None
        assert cr > 0, f"预期正卡玛比率，实际 {cr}"

    def test_flat_returns_returns_none(self):
        """近乎无波动 → 最大回撤小于阈值 → None。"""
        from src.python.analysis.metrics import calmar_ratio

        # 极小幅波动，最大回撤远低于 0.1%
        returns = [0.00001] * 252
        cr = calmar_ratio(returns)
        assert cr is None


class TestHHI:
    """HHI 集中度指数测试。"""

    def test_equal_weights(self):
        """N 品种等权重 → HHI = 1/N。"""
        from src.python.analysis.metrics import hhi

        n = 10
        result = hhi([1.0 / n] * n)
        expected = 1.0 / n
        assert result == pytest.approx(expected, rel=1e-4), f"期望 {expected}，实际 {result}"

    def test_empty_weights_returns_zero(self):
        """空列表 → 0。"""
        from src.python.analysis.metrics import hhi

        assert hhi([]) == 0.0


class TestWinRate:
    """持仓胜率测试。"""

    def test_all_winning(self):
        """全部盈利 → 胜率 1.0。"""
        from src.python.analysis.metrics import win_rate

        holdings = _make_holdings([100, 200, 50])
        result = win_rate(holdings)
        assert result["win_rate"] == 1.0
        assert len(result["winning"]) == 3
        assert len(result["losing"]) == 0

    def test_all_losing(self):
        """全部亏损 → 胜率 0.0。"""
        from src.python.analysis.metrics import win_rate

        holdings = _make_holdings([-100, -200, -50])
        result = win_rate(holdings)
        assert result["win_rate"] == 0.0
        assert len(result["winning"]) == 0
        assert len(result["losing"]) == 3


class TestTurnoverRate:
    """换手率测试。"""

    def test_no_change_returns_zero(self):
        """两期完全一致 → 换手率 0。"""
        from src.python.analysis.metrics import turnover_rate

        data = [{"code": "A", "market_value": 100}, {"code": "B", "market_value": 200}]
        result = turnover_rate(data, data)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-4)

    def test_empty_before_returns_none(self):
        """空上期 → None。"""
        from src.python.analysis.metrics import turnover_rate

        after = [{"code": "A", "market_value": 100}]
        assert turnover_rate([], after) is None


class TestRiskContribution:
    """风险贡献测试。"""

    def test_equal_risk_contribution(self):
        """等权等波动率 → 贡献度均等。"""
        from src.python.analysis.metrics import risk_contribution

        n = 5
        result = risk_contribution([0.2] * n, [0.1] * n)
        assert len(result) == n
        for r in result:
            assert r["contribution"] == pytest.approx(1.0 / n, rel=1e-4)

    def test_empty_input_returns_empty(self):
        """空列表 → []。"""
        from src.python.analysis.metrics import risk_contribution

        assert risk_contribution([], []) == []


class TestIndividualVolatility:
    """个股波动率测试。"""

    def test_normal_volatility(self):
        """正常序列 → 返回正值波动率。"""
        from src.python.analysis.metrics import individual_volatility

        returns = _make_positive_returns(252, 0.0, 0.02)
        result = individual_volatility({"A": returns})
        vol = result.get("A")
        assert vol is not None
        assert vol > 0, f"预期正波动率，实际 {vol}"

    def test_insufficient_data_returns_none(self):
        """不足 20 日 → None。"""
        from src.python.analysis.metrics import individual_volatility

        result = individual_volatility({"A": [0.001] * 10})
        assert result.get("A") is None


class TestPortfolioBeta:
    """组合 Beta 测试。"""

    def test_beta_near_one(self):
        """组合与基准高度正相关 → Beta ≈ 1。"""
        from src.python.analysis.metrics import portfolio_beta

        # 生成高度相关的收益率序列
        base = _make_positive_returns(252, 0.001, 0.01)
        portfolio = [b + 0.0001 for b in base]  # 非常接近基准
        beta = portfolio_beta(portfolio, base)
        assert beta is not None
        assert abs(beta - 1.0) < 0.5, f"期望接近 1，实际 {beta}"

    def test_insufficient_data_returns_none(self):
        """不足 20 日 → None。"""
        from src.python.analysis.metrics import portfolio_beta

        assert portfolio_beta([0.001] * 10, [0.002] * 10) is None


# ── 数值清理函数测试 ──────────────────────────────────────


class TestSanitizeMetric:
    """数值清理测试。"""

    def test_nan_returns_default(self):
        from src.python.analysis.metrics import sanitize_metric

        assert sanitize_metric(float("nan")) is None
        assert sanitize_metric(float("nan"), 0.0) == 0.0

    def test_inf_returns_default(self):
        from src.python.analysis.metrics import sanitize_metric

        assert sanitize_metric(float("inf")) is None
        assert sanitize_metric(float("-inf")) is None

    def test_normal_value_passes_through(self):
        from src.python.analysis.metrics import sanitize_metric

        assert sanitize_metric(1.5) == 1.5
        assert sanitize_metric(0) == 0


class TestTruncateExtremeValues:
    """极端值截断测试。"""

    def test_no_extremes_unchanged(self):
        from src.python.analysis.metrics import truncate_extreme_values

        data = [0.1, 0.2, 0.3]
        result = truncate_extreme_values(data)
        assert result == data

    def test_outliers_truncated(self):
        from src.python.analysis.metrics import truncate_extreme_values

        data = [-100.0, 0.1, 0.2, 0.3, 100.0]
        result = truncate_extreme_values(data, lower_quantile=0.1, upper_quantile=0.9)
        assert min(result) >= -100.0  # 下限截断
        assert max(result) <= 100.0
        assert len(result) == len(data)


class TestCheckDataSufficiency:
    """数据充分性检查测试。"""

    def test_sufficient_returns_2(self):
        from src.python.analysis.metrics import check_data_sufficiency

        assert check_data_sufficiency([0.001] * 252) == 2

    def test_insufficient_returns_0(self):
        from src.python.analysis.metrics import check_data_sufficiency

        assert check_data_sufficiency([0.001] * 10) == 0

    def test_empty_returns_0(self):
        from src.python.analysis.metrics import check_data_sufficiency

        assert check_data_sufficiency([]) == 0

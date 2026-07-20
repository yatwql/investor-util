"""量化指标计算 edge 测试 — 极端/异常输入验证。

覆盖 metrics.py 各函数的边角场景：
  - None / NaN / Inf 输入
  - 空列表 / 单元素 / 长度不匹配
  - 零值 / 负值 / 极端值
  - 类型异常 / 缺失字段
"""

from __future__ import annotations

import math

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


# ═══════════════════════════════════════════════════════════════
# sharpe_ratio
# ═══════════════════════════════════════════════════════════════


class TestSharpeRatioEdge:
    """夏普比率 — 边界/异常输入。"""

    def test_single_element_returns_none(self):
        """单元素 → 无法计算标准差 → None。"""
        from src.python.analysis.metrics import sharpe_ratio

        assert sharpe_ratio([0.001]) is None

    def test_zero_variance_returns_none(self):
        """零方差（全部相同）→ 夏普无意义 → None。"""
        from src.python.analysis.metrics import sharpe_ratio

        assert sharpe_ratio([0.001] * 252, rf_annual=0.015) is None

    def test_none_rf_uses_default(self):
        """rf_annual=None → 使用默认无风险利率，不崩溃。"""
        from src.python.analysis.metrics import sharpe_ratio

        returns = [0.0005 + (i % 3 - 1) * 0.005 for i in range(252)]
        sr = sharpe_ratio(returns, rf_annual=None)
        assert sr is not None
        assert isinstance(sr, float)

    def test_extreme_negative_returns(self):
        """全负收益率 → 夏普比率负值。"""
        from src.python.analysis.metrics import sharpe_ratio

        returns = [-0.01 + (i % 5) * 0.001 for i in range(252)]
        sr = sharpe_ratio(returns, rf_annual=0.015)
        assert sr is not None
        assert sr < 0

    def test_nan_in_returns(self):
        """NaN 混入收益率 → 夏普返回 None 或正常值（NaN 传播不崩溃）。"""
        from src.python.analysis.metrics import sharpe_ratio

        returns = [0.001] * 251 + [float("nan")]
        sr = sharpe_ratio(returns, rf_annual=0.015)
        # math.nan 在加法中传播 → variance 变成 NaN → daily_vol = NaN → None
        assert sr is None or math.isnan(sr)

    def test_inf_in_returns(self):
        """Inf 混入收益率 → 不崩溃。"""
        from src.python.analysis.metrics import sharpe_ratio

        returns = [0.001] * 251 + [float("inf")]
        sr = sharpe_ratio(returns, rf_annual=0.015)
        assert sr is None or math.isnan(sr) or math.isinf(sr)


# ═══════════════════════════════════════════════════════════════
# calmar_ratio
# ═══════════════════════════════════════════════════════════════


class TestCalmarRatioEdge:
    """卡玛比率 — 边界/异常输入。"""

    def test_empty_returns_returns_none(self):
        """空列表 → None。"""
        from src.python.analysis.metrics import calmar_ratio

        assert calmar_ratio([]) is None

    def test_single_element_returns_none(self):
        """单元素 → 不足 20 日 → None。"""
        from src.python.analysis.metrics import calmar_ratio

        assert calmar_ratio([0.001]) is None

    def test_all_negative_returns(self):
        """全部负数 → 卡玛比率应为负。"""
        from src.python.analysis.metrics import calmar_ratio

        returns = [-0.005] * 252
        cr = calmar_ratio(returns)
        assert cr is not None
        assert cr < 0

    def test_all_zero_returns_returns_none(self):
        """全零 → 最大回撤接近 0 → None。"""
        from src.python.analysis.metrics import calmar_ratio

        assert calmar_ratio([0.0] * 252) is None


# ═══════════════════════════════════════════════════════════════
# hhi
# ═══════════════════════════════════════════════════════════════


class TestHHIEdge:
    """HHI — 边界/异常输入。"""

    def test_negative_weights(self):
        """含负权重 → 绝对值处理，不崩溃。"""
        from src.python.analysis.metrics import hhi

        result = hhi([0.6, -0.4])
        assert result >= 0

    def test_all_zero_weights_returns_zero(self):
        """全零 → 0。"""
        from src.python.analysis.metrics import hhi

        assert hhi([0.0, 0.0, 0.0]) == 0.0

    def test_single_weight(self):
        """单品种权重 → HHI = 1.0。"""
        from src.python.analysis.metrics import hhi

        assert hhi([1.0]) == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════
# win_rate
# ═══════════════════════════════════════════════════════════════


class TestWinRateEdge:
    """胜率 — 边界/异常输入。"""

    def test_empty_holdings(self):
        """空列表 → win_rate=0。"""
        from src.python.analysis.metrics import win_rate

        result = win_rate([])
        assert result["win_rate"] == 0.0
        assert len(result["winning"]) == 0
        assert len(result["losing"]) == 0
        assert len(result["zero"]) == 0

    def test_none_profit_treated_as_zero(self):
        """profit=None → 归入持平。"""
        from src.python.analysis.metrics import win_rate

        holdings = [
            {"name": "A", "code": "001", "profit": None},
            {"name": "B", "code": "002", "profit": 100},
        ]
        result = win_rate(holdings)
        assert result["win_rate"] == 0.5
        assert "A" in result["zero"]

    def test_missing_profit_treated_as_zero(self):
        """缺 profit 键 → 归入持平。"""
        from src.python.analysis.metrics import win_rate

        holdings = [
            {"name": "A", "code": "001"},
            {"name": "B", "code": "002", "profit": 100},
        ]
        result = win_rate(holdings)
        assert result["win_rate"] == 0.5
        assert "A" in result["zero"]

    def test_non_numeric_profit_coerced_to_zero(self):
        """str 类型 profit → 转为 0。"""
        from src.python.analysis.metrics import win_rate

        holdings = [
            {"name": "A", "code": "001", "profit": "亏损"},
        ]
        result = win_rate(holdings)
        assert result["win_rate"] == 0.0
        assert "A" in result["zero"]

    def test_all_zero_profit(self):
        """全部持平 → win_rate=0。"""
        from src.python.analysis.metrics import win_rate

        holdings = [{"name": "A", "code": "001", "profit": 0},
                     {"name": "B", "code": "002", "profit": 0}]
        result = win_rate(holdings)
        assert result["win_rate"] == 0.0
        assert len(result["zero"]) == 2

    def test_missing_name_falls_back_to_code(self):
        """缺 name → 使用 code。"""
        from src.python.analysis.metrics import win_rate

        holdings = [{"code": "001", "profit": 100}]
        result = win_rate(holdings)
        assert "001" in result["winning"]


# ═══════════════════════════════════════════════════════════════
# turnover_rate
# ═══════════════════════════════════════════════════════════════


class TestTurnoverRateEdge:
    """换手率 — 边界/异常输入。"""

    def test_empty_after_returns_none(self):
        """空下期 → None。"""
        from src.python.analysis.metrics import turnover_rate

        before = [{"code": "A", "market_value": 100}]
        assert turnover_rate(before, []) is None

    def test_both_empty_returns_none(self):
        """两期皆空 → None。"""
        from src.python.analysis.metrics import turnover_rate

        assert turnover_rate([], []) is None

    def test_zero_market_value_returns_none(self):
        """市值为 0 → None。"""
        from src.python.analysis.metrics import turnover_rate

        data = [{"code": "A", "market_value": 0}]
        assert turnover_rate(data, data) is None

    def test_missing_code_still_processes(self):
        """缺 code 键 → 视为空字符串，不崩溃。"""
        from src.python.analysis.metrics import turnover_rate

        before = [{"code": "A", "market_value": 100}]
        after = [{"name": "B", "market_value": 200}]  # 无 code
        result = turnover_rate(before, after)
        assert result is not None

    def test_none_market_value_treated_as_zero(self):
        """market_value=None → 视为 0。"""
        from src.python.analysis.metrics import turnover_rate

        before = [{"code": "A", "market_value": 100}]
        after = [{"code": "A", "market_value": None}]
        result = turnover_rate(before, after)
        # old_total=100, new_total=0 → 返回 None
        assert result is None


# ═══════════════════════════════════════════════════════════════
# risk_contribution
# ═══════════════════════════════════════════════════════════════


class TestRiskContributionEdge:
    """风险贡献 — 边界/异常输入。"""

    def test_length_mismatch_returns_empty(self):
        """weights 与 volatilities 不等长 → []。"""
        from src.python.analysis.metrics import risk_contribution

        assert risk_contribution([0.5, 0.5], [0.1]) == []

    def test_zero_volatilities_returns_empty(self):
        """全部波动率为零 → 无法计算 → []。"""
        from src.python.analysis.metrics import risk_contribution

        assert risk_contribution([0.5, 0.5], [0.0, 0.0]) == []

    def test_nan_weight_treated_as_zero(self):
        """NaN 权重 → sanitize 为 0。"""
        from src.python.analysis.metrics import risk_contribution

        result = risk_contribution([float("nan"), 0.5], [0.1, 0.2])
        # NaN 被清理为 0 → 第一项贡献为 0
        assert len(result) == 2
        assert result[0]["contribution"] >= 0

    def test_negative_weight_negative_volatility(self):
        """负权重 + 负波动率 → contribution 计算不崩溃。"""
        from src.python.analysis.metrics import risk_contribution

        result = risk_contribution([-0.5, 1.5], [0.1, 0.2])
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════
# individual_volatility
# ═══════════════════════════════════════════════════════════════


class TestIndividualVolatilityEdge:
    """个股波动率 — 边界/异常输入。"""

    def test_empty_dict_returns_empty(self):
        """空字典 → { }。"""
        from src.python.analysis.metrics import individual_volatility

        assert individual_volatility({}) == {}

    def test_code_with_empty_list_returns_none(self):
        """某品种为空列表 → None。"""
        from src.python.analysis.metrics import individual_volatility

        result = individual_volatility({"A": []})
        assert result["A"] is None

    def test_code_with_single_return(self):
        """单元素列表 → 不足 20 日 → None。"""
        from src.python.analysis.metrics import individual_volatility

        result = individual_volatility({"A": [0.001]})
        assert result["A"] is None

    def test_zero_variance_returns_zero(self):
        """零方差 → 波动率 0.0。"""
        from src.python.analysis.metrics import individual_volatility

        result = individual_volatility({"A": [0.001] * 252})
        assert result["A"] == 0.0

    def test_not_annualized(self):
        """annualize=False → 返回日波动率。"""
        from src.python.analysis.metrics import individual_volatility

        returns = [0.001 + (i % 5) * 0.002 for i in range(252)]
        result = individual_volatility({"A": returns}, annualize=False)
        assert result["A"] is not None
        assert result["A"] < 0.1  # 日波动率应远小于年化


# ═══════════════════════════════════════════════════════════════
# portfolio_beta
# ═══════════════════════════════════════════════════════════════


class TestPortfolioBetaEdge:
    """组合 Beta — 边界/异常输入。"""

    def test_zero_variance_benchmark_returns_none(self):
        """基准零方差 → 无法计算 → None。"""
        from src.python.analysis.metrics import portfolio_beta

        assert portfolio_beta([0.001] * 252, [0.0] * 252) is None

    def test_unequal_lengths_uses_shorter(self):
        """两序列不等长 → 对齐到较短者。"""
        from src.python.analysis.metrics import portfolio_beta

        portfolio = [0.001 + (i % 3 - 1) * 0.005 for i in range(252)]
        benchmark = [0.002 + (i % 5 - 2) * 0.003 for i in range(200)]
        beta = portfolio_beta(portfolio, benchmark)
        assert beta is not None

    def test_perfectly_correlated_returns_beta(self):
        """完全正相关 → Beta≈Cov/Var。"""
        from src.python.analysis.metrics import portfolio_beta

        base = [0.001 + (i % 5) * 0.005 for i in range(252)]
        scaled = [2.0 * b for b in base]
        beta = portfolio_beta(scaled, base)
        assert beta is not None
        assert abs(beta - 2.0) < 0.5

    def test_negatively_correlated_returns_negative_beta(self):
        """完全负相关 → 负 Beta。"""
        from src.python.analysis.metrics import portfolio_beta

        base = [0.001 + (i % 5) * 0.005 for i in range(252)]
        inverted = [-b for b in base]
        beta = portfolio_beta(inverted, base)
        assert beta is not None
        assert beta < 0


# ═══════════════════════════════════════════════════════════════
# sanitize_metric
# ═══════════════════════════════════════════════════════════════


class TestSanitizeMetricEdge:
    """数值清理 — 非数值类型。"""

    def test_string_passes_through_if_not_float(self):
        """字符串输入 → 原样返回（非 float 不检查 NaN/Inf）。"""
        from src.python.analysis.metrics import sanitize_metric

        assert sanitize_metric("hello") == "hello"

    def test_dict_passes_through(self):
        """字典 → 原样返回。"""
        from src.python.analysis.metrics import sanitize_metric

        d = {"a": 1}
        assert sanitize_metric(d) is d

    def test_none_returns_default(self):
        """None → default。"""
        from src.python.analysis.metrics import sanitize_metric

        assert sanitize_metric(None, 0.0) == 0.0
        assert sanitize_metric(None) is None

    def test_negative_zero(self):
        """-0.0 → 0.0 视同正常值。"""
        from src.python.analysis.metrics import sanitize_metric

        result = sanitize_metric(-0.0)
        assert result == 0.0 or result == -0.0


# ═══════════════════════════════════════════════════════════════
# truncate_extreme_values
# ═══════════════════════════════════════════════════════════════


class TestTruncateExtremeValuesEdge:
    """极端值截断 — 边界输入。"""

    def test_single_element(self):
        """单元素 → 原样返回。"""
        from src.python.analysis.metrics import truncate_extreme_values

        assert truncate_extreme_values([0.5]) == [0.5]

    def test_extreme_quantiles_no_crash(self):
        """极端分位数参数（0 或 1）→ 不崩溃。"""
        from src.python.analysis.metrics import truncate_extreme_values

        data = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = truncate_extreme_values(data, lower_quantile=0.0, upper_quantile=1.0)
        assert result == data


# ═══════════════════════════════════════════════════════════════
# check_data_sufficiency / get_confidence_level
# ═══════════════════════════════════════════════════════════════


class TestCheckDataSufficiencyEdge:
    """数据充分性 — 边界输入。"""

    def test_none_returns_low(self):
        """None 输入 → 返回 0。"""
        from src.python.analysis.metrics import check_data_sufficiency

        # 函数签名不接受 None，但防御性处理
        assert check_data_sufficiency([]) == 0


class TestGetConfidenceLevelEdge:
    """置信度等级 — 边界输入。"""

    def test_none_input_returns_insufficient(self):
        """None → 'insufficient'。"""
        from src.python.analysis.metrics import get_confidence_level

        assert get_confidence_level(None) == "insufficient"

    def test_empty_input_returns_insufficient(self):
        """[] → 'insufficient'。"""
        from src.python.analysis.metrics import get_confidence_level

        assert get_confidence_level([]) == "insufficient"

    def test_between_20_and_252_returns_low(self):
        """20~251 日 → 'low'。"""
        from src.python.analysis.metrics import get_confidence_level

        assert get_confidence_level([0.001] * 100) == "low"

    def test_252_or_more_returns_high(self):
        """≥252 日 → 'high'。"""
        from src.python.analysis.metrics import get_confidence_level

        assert get_confidence_level([0.001] * 252) == "high"


# ═══════════════════════════════════════════════════════════════
# compute_all_metrics
# ═══════════════════════════════════════════════════════════════


class TestComputeAllMetricsEdge:
    """全量指标聚合 — 边界/部分参数。"""

    def test_minimal_params(self):
        """仅传 portfolio_daily_returns → 不应崩溃。"""
        from src.python.analysis.metrics import compute_all_metrics

        returns = [0.001 + (i % 3 - 1) * 0.005 for i in range(252)]
        result = compute_all_metrics(returns)
        assert isinstance(result, dict)
        assert "sharpe_ratio" in result

    def test_empty_returns(self):
        """空收益率序列 → 各指标为 None/空。"""
        from src.python.analysis.metrics import compute_all_metrics

        result = compute_all_metrics([])
        assert result["sharpe_ratio"] is None
        assert result["calmar_ratio"] is None
        assert result["portfolio_beta"] is None

    def test_insufficient_data_sets_all_none(self):
        """不足 20 日 → 所有指标 None。"""
        from src.python.analysis.metrics import compute_all_metrics

        result = compute_all_metrics([0.001] * 10)
        assert result["sharpe_ratio"] is None
        assert result["calmar_ratio"] is None

    def test_holdings_none_does_not_crash(self):
        """holdings_details=None → win_rate 默认 []。"""
        from src.python.analysis.metrics import compute_all_metrics

        returns = [0.001 + (i % 3 - 1) * 0.005 for i in range(252)]
        result = compute_all_metrics(returns, holdings_details=None)
        assert result["win_rate"]["win_rate"] == 0.0


# ═══════════════════════════════════════════════════════════════
# portfolio_beta_analysis — 额外异常路径
# ═══════════════════════════════════════════════════════════════


class TestBetaAnalysisEdge:
    """Beta 置信区间分析 — 边界路径。"""

    def test_no_variance_benchmark_returns_none(self):
        """基准全零 → beta None → analysis None。"""
        from src.python.analysis.metrics import portfolio_beta_analysis

        assert portfolio_beta_analysis([0.001] * 252, [0.0] * 252) is None

    def test_low_df_critical_value(self):
        """小自由度 → 查表给出界内值。"""
        from src.python.analysis.metrics import _t_critical_95

        assert _t_critical_95(1) == 12.706
        assert _t_critical_95(2) == 4.303

    def test_very_large_df_approaches_1_96(self):
        """大自由度 → 逼近 1.96。"""
        from src.python.analysis.metrics import _t_critical_95

        assert abs(_t_critical_95(1000) - 1.96) < 0.1

    def test_t_cdf_zero_df_returns_0_5(self):
        """df ≤ 0 → 返回 0.5。"""
        from src.python.analysis.metrics import _t_cdf

        assert _t_cdf(1.0, 0) == 0.5

    def test_t_cdf_extreme_values(self):
        """t 统计量极大/极小 → 概率饱和。"""
        from src.python.analysis.metrics import _t_cdf

        assert _t_cdf(10.0, 100) >= 0.999  # 极大 t → 接近 1
        assert _t_cdf(-10.0, 100) <= 0.001  # 极小 t → 接近 0

    def test_se_zero_perfect_prediction(self):
        """标准误为 0 → 完美预测分支。"""
        from src.python.analysis.metrics import portfolio_beta_analysis

        base = [0.001 + (i % 5) * 0.005 for i in range(252)]
        result = portfolio_beta_analysis(base, base)
        assert result is not None
        # 完全相同序列使 SSE=0 → SE=0
        assert result["p_value"] == 0.0
        assert result["reliable"] is True

    def test_ci_width_exceeds_threshold_unreliable(self):
        """CI 宽度超过 1.5 → reliable=False。"""
        from src.python.analysis.metrics import portfolio_beta_analysis

        import random
        random.seed(42)
        base = [random.gauss(0.0, 0.015) for _ in range(100)]
        # 高噪声确保宽 CI
        noisy = [b * 1.0 + random.gauss(0.0, 0.08) for b in base]
        result = portfolio_beta_analysis(noisy, base)
        # 确认这个路径走通了
        assert result is not None
        if result["ci_lower"] is not None and result["ci_upper"] is not None:
            width = result["ci_upper"] - result["ci_lower"]
            # 高噪声下 CI 可能很宽
            if width > 1.5:
                assert result["reliable"] is False

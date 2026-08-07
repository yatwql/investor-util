"""情景分析模块单元测试。

覆盖：
  - 正常 Beta 输入 → 六情景正确计算
  - CI 传播方向正确（市场上涨/下跌时 CI 反转）
  - Beta 为 None → 所有情景显示 "--"
  - 金额计算正确
  - 行业集中度情景
  - 汇率情景
  - 夏普比率置信区间传播
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


class TestScenarioAnalysis:
    """情景分析（Beta 推导）测试。"""

    def test_six_scenarios_returned(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=1_000_000, beta=1.0)
        assert len(result["scenarios"]) == 6

    def test_market_changes_correct(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=1_000_000, beta=1.0)
        expected = [-0.30, -0.20, -0.10, 0.10, 0.20, 0.30]
        for s, exp in zip(result["scenarios"], expected):
            assert s["market_change"] == exp

    def test_beta_one_expected_pct(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=1_000_000, beta=1.0)
        for s in result["scenarios"]:
            assert s["expected_change_pct"] == s["market_change"]

    def test_beta_one_two_expected_pct(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=1_000_000, beta=1.2)
        for s in result["scenarios"]:
            assert s["expected_change_pct"] == round(1.2 * s["market_change"], 4)

    def test_amount_calculation(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=500_000, beta=1.0)
        for s in result["scenarios"]:
            expected_amt = round(500_000 * s["expected_change_pct"], 2)
            assert s["expected_change_amt"] == expected_amt

    def test_ci_propagation_down_market(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(
            portfolio_value=1_000_000, beta=1.2,
            beta_ci_lower=1.0, beta_ci_upper=1.4,
        )
        down = [s for s in result["scenarios"] if s["market_change"] == -0.20][0]
        assert down["expected_change_pct"] == -0.24
        assert down["ci_lower_pct"] == -0.28
        assert down["ci_upper_pct"] == -0.20

    def test_ci_propagation_up_market(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(
            portfolio_value=1_000_000, beta=1.2,
            beta_ci_lower=1.0, beta_ci_upper=1.4,
        )
        up = [s for s in result["scenarios"] if s["market_change"] == 0.20][0]
        assert up["expected_change_pct"] == 0.24
        assert up["ci_lower_pct"] == 0.20
        assert up["ci_upper_pct"] == 0.28

    def test_no_beta_returns_has_data_false(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=1_000_000)
        assert result["has_data"] is False
        assert result["beta"] is None
        for s in result["scenarios"]:
            assert s["expected_change_pct"] is None

    def test_zero_market_change_not_present(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=1_000_000, beta=1.0)
        changes = [s["market_change"] for s in result["scenarios"]]
        assert 0.0 not in changes

    def test_ci_propagation_with_no_ci(self):
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=1_000_000, beta=1.0)
        for s in result["scenarios"]:
            assert s["ci_lower_pct"] is None

    def test_expected_change_symmetry(self):
        """上涨和下跌情景对称。"""
        from src.python.analysis.scenario import scenario_analysis
        result = scenario_analysis(portfolio_value=1_000_000, beta=1.0)
        up10 = [s for s in result["scenarios"] if s["market_change"] == 0.10][0]
        down10 = [s for s in result["scenarios"] if s["market_change"] == -0.10][0]
        assert up10["expected_change_pct"] == -down10["expected_change_pct"]


class TestIndustryConcentration:
    """行业集中度情景分析测试。"""

    def test_high_concentration_impact(self):
        from src.python.analysis.scenario import industry_concentration_analysis
        result = industry_concentration_analysis(0.60, 1_000_000, "白酒")
        assert result["has_data"] is True
        assert result["concentration_risk"] == "high"
        assert result["impact_pct"] == round(0.60 * -0.15, 4)

    def test_medium_concentration(self):
        from src.python.analysis.scenario import industry_concentration_analysis
        result = industry_concentration_analysis(0.35, 1_000_000)
        assert result["concentration_risk"] == "medium"

    def test_low_concentration(self):
        from src.python.analysis.scenario import industry_concentration_analysis
        result = industry_concentration_analysis(0.15, 1_000_000)
        assert result["concentration_risk"] == "low"

    def test_no_data_returns_warning(self):
        from src.python.analysis.scenario import industry_concentration_analysis
        result = industry_concentration_analysis(None, 1_000_000)
        assert result["has_data"] is False
        assert result["warning"] is not None

    def test_impact_amount(self):
        from src.python.analysis.scenario import industry_concentration_analysis
        result = industry_concentration_analysis(0.50, 500_000, "科技")
        expected_amt = round(500_000 * 0.50 * -0.15, 2)
        assert result["impact_amt"] == expected_amt


class TestFxScenario:
    """汇率情景分析测试。"""

    def test_two_scenarios_returned(self):
        from src.python.analysis.scenario import fx_scenario_analysis
        result = fx_scenario_analysis(0.20, 1_000_000)
        assert len(result["scenarios"]) == 2

    def test_appreciation_negative_impact(self):
        """人民币升值 → 外币资产缩水。"""
        from src.python.analysis.scenario import fx_scenario_analysis
        result = fx_scenario_analysis(0.20, 1_000_000)
        appreciation = [s for s in result["scenarios"] if s["fx_change"] < 0][0]
        assert appreciation["label"] == "人民币升值"
        assert appreciation["impact_pct"] < 0

    def test_depreciation_positive_impact(self):
        """人民币贬值 → 外币资产增值。"""
        from src.python.analysis.scenario import fx_scenario_analysis
        result = fx_scenario_analysis(0.20, 1_000_000)
        depreciation = [s for s in result["scenarios"] if s["fx_change"] > 0][0]
        assert depreciation["label"] == "人民币贬值"
        assert depreciation["impact_pct"] > 0

    def test_no_data(self):
        from src.python.analysis.scenario import fx_scenario_analysis
        result = fx_scenario_analysis(None, 1_000_000)
        assert result["has_data"] is False
        assert result["warning"] is not None

    def test_low_exposure_warning(self):
        from src.python.analysis.scenario import fx_scenario_analysis
        result = fx_scenario_analysis(0.03, 1_000_000)
        assert result["warning"] is not None

    def test_impact_amount(self):
        from src.python.analysis.scenario import fx_scenario_analysis
        result = fx_scenario_analysis(0.10, 500_000)
        dep = [s for s in result["scenarios"] if s["fx_change"] > 0][0]
        assert dep["impact_amt"] == round(500_000 * 0.10 * 0.05, 2)


class TestSharpeCI:
    """夏普比率置信区间传播测试。"""

    def test_normal_sharpe_returns_ci(self):
        from src.python.analysis.scenario import sharpe_ci_propagation
        result = sharpe_ci_propagation(0.80, 3.0)
        assert result["has_data"] is True
        assert result["ci_lower"] < result["sharpe_ratio"]
        assert result["ci_upper"] > result["sharpe_ratio"]

    def test_high_sharpe_wider_ci(self):
        """夏普比率越高，CI 越宽（Lo 近似）。"""
        from src.python.analysis.scenario import sharpe_ci_propagation
        r1 = sharpe_ci_propagation(0.50, 3.0)
        r2 = sharpe_ci_propagation(2.00, 3.0)
        assert r2["ci_width"] > r1["ci_width"]

    def test_more_data_narrower_ci(self):
        """更多观测数据 → CI 更窄。"""
        from src.python.analysis.scenario import sharpe_ci_propagation
        r1 = sharpe_ci_propagation(0.80, 1.0, n_observations=63)
        r2 = sharpe_ci_propagation(0.80, 3.0, n_observations=756)
        assert r2["ci_width"] < r1["ci_width"]

    def test_none_sharpe_returns_no_data(self):
        from src.python.analysis.scenario import sharpe_ci_propagation
        result = sharpe_ci_propagation(None, 3.0)
        assert result["has_data"] is False

    def test_short_history_warning(self):
        from src.python.analysis.scenario import sharpe_ci_propagation
        result = sharpe_ci_propagation(0.50, 0.5)
        assert result["warning"] is not None

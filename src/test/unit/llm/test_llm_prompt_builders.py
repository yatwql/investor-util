"""LLM 提示词构建模块单元测试 — 各提示词构建函数与格式化工具。

运行：
  pytest src/test/unit/llm/test_llm_prompt_builders.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


@pytest.mark.unit_llm
class TestBuildHealthCheckPrompt(unittest.TestCase):
    """_build_health_check_prompt 提示词构建。"""

    def test_contains_scoring_dimensions(self):
        """包含四个评分维度描述。"""
        from src.python.llm.prompts import _build_health_check_prompt
        result = _build_health_check_prompt(
            total_mv=100_000, total_cost=80_000, total_profit=20_000,
            total_today_profit=1_000, holdings_count=5, categories={},
        )
        self.assertIn("风险分散度", result)
        self.assertIn("流动性", result)
        self.assertIn("收益合理性", result)
        self.assertIn("成本结构", result)


@pytest.mark.unit_llm
class TestBuildPenetrationDeepPrompt(unittest.TestCase):
    """_build_penetration_deep_prompt 提示词构建。"""

    def test_contains_penetration_sections(self):
        """包含穿透分析各维度。"""
        from src.python.llm.prompts import _build_penetration_deep_prompt
        result = _build_penetration_deep_prompt(
            total_mv=100_000, total_cost=80_000, total_profit=20_000,
            holdings_count=5, categories={},
        )
        self.assertIn("行业集中度", result)
        self.assertIn("品种集中度", result)

    def test_with_penetrated_assets(self):
        """穿透 TOP10 明细嵌入。"""
        from src.python.llm.prompts import _build_penetration_deep_prompt
        assets = [
            {"name": "贵州茅台", "codes": ["600519"], "mv": 50_000, "ratio": 25.0, "sector": "白酒"},
        ]
        result = _build_penetration_deep_prompt(
            total_mv=200_000, total_cost=180_000, total_profit=20_000,
            holdings_count=5, categories={}, penetrated_assets=assets,
        )
        self.assertIn("贵州茅台", result)
        self.assertIn("25.0%", result)

    def test_calc_country_exposure_included(self):
        """国别/币种分布嵌入（含交易所前缀代码分类为 A 股）。"""
        from src.python.llm.prompts import _build_penetration_deep_prompt
        details = [
            {"code": "sh600900", "market_value": 50_000, "source_api": "tencent", "name": "长江电力"},
        ]
        result = _build_penetration_deep_prompt(
            total_mv=50_000, total_cost=40_000, total_profit=10_000,
            holdings_count=1, categories={}, holdings_details=details,
        )
        self.assertIn("A股", result)


@pytest.mark.unit_llm
class TestFormatHoldingsBlock(unittest.TestCase):
    """_format_holdings_block 持仓明细块格式化。"""

    def test_empty_returns_empty(self):
        """空列表返回空字符串。"""
        from src.python.llm.prompts import _format_holdings_block
        self.assertEqual(_format_holdings_block(None), "")
        self.assertEqual(_format_holdings_block([]), "")

    def test_limits_output(self):
        """超过 limit 行时截断。"""
        from src.python.llm.prompts import _format_holdings_block
        details = [
            {"code": f"600{i:03d}", "market_value": 10_000, "profit": 1_000,
             "profit_rate": 10.0, "source_api": "tencent", "name": f"测试{i}",
             "change_pct": 0.0}
            for i in range(50)
        ]
        result = _format_holdings_block(details, limit=5)
        self.assertGreaterEqual(result.count("\n"), 4)  # 5 items → 4 newlines
        self.assertLessEqual(result.count("\n"), 10)


@pytest.mark.unit_llm
class TestFormatPenetrationBlock(unittest.TestCase):
    """_format_penetration_block 穿透块格式化。"""

    def test_empty_returns_empty(self):
        """空列表返回空字符串。"""
        from src.python.llm.prompts import _format_penetration_block
        self.assertEqual(_format_penetration_block(None), "")
        self.assertEqual(_format_penetration_block([]), "")

    def test_returns_string_with_assets(self):
        """格式化穿透资产文本。"""
        from src.python.llm.prompts import _format_penetration_block
        assets = [
            {"name": "腾讯控股", "codes": ["00700"], "mv": 50_000, "sector": "互联网"},
        ]
        result = _format_penetration_block(assets)
        self.assertIn("穿透", result)
        self.assertIn("腾讯控股", result)


@pytest.mark.unit_llm
class TestCalcCountryExposure(unittest.TestCase):
    """_calc_country_exposure 国别/币种分布计算。"""

    def test_empty_returns_empty_list(self):
        from src.python.llm.prompts import _calc_country_exposure
        self.assertEqual(_calc_country_exposure(None), [])
        self.assertEqual(_calc_country_exposure([]), [])

    def test_a_share_code_mapped(self):
        """A 股代码（sh/sz 前缀）归属正确。"""
        from src.python.llm.prompts import _calc_country_exposure
        details = [{"code": "sh600900", "market_value": 50_000}]
        result = _calc_country_exposure(details)
        combined = " ".join(result)
        self.assertIn("A股", combined)

    def test_no_prefix_code_is_cny_by_default(self):
        """无交易所前缀代码默认按 CNY 归属为 A 股。"""
        from src.python.llm.prompts import _calc_country_exposure
        details = [{"code": "900900", "market_value": 50_000}]
        result = _calc_country_exposure(details)
        combined = " ".join(result)
        self.assertIn("A股", combined)


@pytest.mark.unit_llm
class TestBuildCompetitiveContextBlock(unittest.TestCase):
    """_build_competitive_context_block 竞争语境段落构建。"""

    def _no_data(self) -> str:
        from src.python.llm.prompts import _build_competitive_context_block
        return _build_competitive_context_block(None, 0, 0)

    def test_no_data_returns_fallback(self):
        """无数据时返回兜底文本。"""
        result = self._no_data()
        self.assertEqual(result, "暂无足够历史数据进行竞争语境对比")

    def test_with_index_data_shows_today_compare(self):
        """指数数据正确显示今日对比段落。"""
        from src.python.llm.prompts import _build_competitive_context_block
        a_indices = {
            "sh000300": {"name": "沪深300", "change_pct": 0.5},
            "sh000905": {"name": "中证500", "change_pct": 1.2},
        }
        result = _build_competitive_context_block(a_indices, 1_000_000, 10_000)
        self.assertIn("【今日对比】", result)
        self.assertIn("沪深300", result)
        self.assertIn("中证500", result)
        self.assertIn("相对沪深300", result)

    def test_with_history_data_shows_interval_compare(self):
        """历史数据包含区间对比。"""
        from src.python.llm.prompts import _build_competitive_context_block
        history_data = {
            "portfolio_returns": [0.01, 0.02, 0.05],
            "benchmark_returns": [0.005, 0.01, 0.03],
        }
        result = _build_competitive_context_block(
            {"sh000300": {"change_pct": 0.5}}, 1_000_000, 10_000,
            history_data=history_data,
        )
        self.assertIn("【区间对比】", result)

    def test_with_metrics_shows_indicator_compare(self):
        """量化指标正确嵌入指标对比段落。"""
        from src.python.llm.prompts import _build_competitive_context_block
        metrics = {
            "sharpe_ratio": 0.85,
            "annualized_volatility": 0.1234,
            "max_drawdown": -0.15,
            "calmar_ratio": 1.2,
        }
        result = _build_competitive_context_block(
            {"sh000300": {"change_pct": 0.5}}, 1_000_000, 10_000,
            metrics=metrics,
        )
        self.assertIn("【指标对比】", result)
        self.assertIn("夏普 0.85", result)
        self.assertIn("年化波动率 12.3%", result)
        self.assertIn("最大回撤 -15.0%", result)
        self.assertIn("卡玛 1.20", result)

    def test_metrics_partial_keys_shows_available_only(self):
        """指标字典部分键时仅显示存在的指标。"""
        from src.python.llm.prompts import _build_competitive_context_block
        metrics = {
            "sharpe_ratio": 0.85,
            "annualized_volatility": 0.12,
        }
        result = _build_competitive_context_block(
            {"sh000300": {"change_pct": 0.5}}, 1_000_000, 10_000,
            metrics=metrics,
        )
        self.assertIn("【指标对比】", result)
        self.assertIn("夏普 0.85", result)
        self.assertIn("年化波动率", result)
        self.assertNotIn("最大回撤", result)
        self.assertNotIn("卡玛", result)

    def test_metrics_with_none_values_ignored(self):
        """指标值为 None 时跳过。"""
        from src.python.llm.prompts import _build_competitive_context_block
        metrics = {
            "sharpe_ratio": None,
            "annualized_volatility": 0.12,
            "max_drawdown": None,
            "calmar_ratio": None,
        }
        result = _build_competitive_context_block(
            {"sh000300": {"change_pct": 0.5}}, 1_000_000, 10_000,
            metrics=metrics,
        )
        self.assertIn("【指标对比】", result)
        self.assertIn("年化波动率", result)
        self.assertNotIn("夏普", result)
        self.assertNotIn("最大回撤", result)
        self.assertNotIn("卡玛", result)

    def test_metrics_empty_dict_no_indicator_section(self):
        """空指标字典时无指标对比段落。"""
        from src.python.llm.prompts import _build_competitive_context_block
        result = _build_competitive_context_block(
            {"sh000300": {"change_pct": 0.5}}, 1_000_000, 10_000,
            metrics={},
        )
        self.assertNotIn("【指标对比】", result)
        self.assertIn("【今日对比】", result)

    def test_custom_comparison_indices(self):
        """自定义对比指数池生效。"""
        from src.python.llm.prompts import _build_competitive_context_block
        a_indices = {
            "sh000300": {"name": "沪深300", "change_pct": 0.5},
            "sh000012": {"name": "中证全债", "change_pct": 0.05},
        }
        result = _build_competitive_context_block(
            a_indices, 1_000_000, 10_000,
            comparison_indices={"sh000012": "中证全债"},
        )
        self.assertIn("中证全债", result)
        self.assertNotIn("中证500", result)

    def test_footnote_appended_when_comparison_present(self):
        """有对比数据时脚注自动追加。"""
        from src.python.llm.prompts import _build_competitive_context_block
        result = _build_competitive_context_block(
            {"sh000300": {"name": "沪深300", "change_pct": 0.5}},
            1_000_000, 10_000,
        )
        self.assertIn("口径说明", result)
        self.assertIn("费后净收益", result)
        self.assertIn("价格指数", result)
        self.assertIn("现金管理品种", result)
        self.assertIn("非静态组合", result)

    def test_footnote_not_appended_when_no_data(self):
        """无对比数据时无脚注。"""
        from src.python.llm.prompts import _build_competitive_context_block
        result = _build_competitive_context_block(None, 0, 0)
        self.assertEqual(result, "暂无足够历史数据进行竞争语境对比")
        self.assertNotIn("口径说明", result)

    def test_survivor_bias_note_appended_when_comparison_present(self):
        """有对比数据时幸存者偏差提示自动追加。"""
        from src.python.llm.prompts import _build_competitive_context_block
        result = _build_competitive_context_block(
            {"sh000300": {"name": "沪深300", "change_pct": 0.5}},
            1_000_000, 10_000,
        )
        self.assertIn("幸存者偏差", result)
        self.assertIn("成分股", result)

    def test_survivor_bias_note_not_appended_when_no_data(self):
        """无对比数据时无幸存者偏差提示。"""
        from src.python.llm.prompts import _build_competitive_context_block
        result = _build_competitive_context_block(None, 0, 0)
        self.assertNotIn("幸存者偏差", result)


@pytest.mark.unit_llm
class TestBuildExpertReviewPromptSkipScenarios(unittest.TestCase):
    """_build_expert_review_prompt skip_scenarios 参数验证。"""

    def test_skip_scenarios_removes_scenario_block(self):
        """skip_scenarios=True 时不应包含情景分析指令。"""
        from src.python.llm.prompts import _build_expert_review_prompt
        result = _build_expert_review_prompt(
            total_mv=100_000, total_cost=80_000, total_profit=20_000,
            total_today_profit=1_000, holdings_count=5, categories={},
            skip_scenarios=True,
        )
        self.assertNotIn("### 情景分析", result)
        self.assertNotIn("上涨情景", result)
        self.assertNotIn("下跌情景", result)

    def test_default_scenarios_present(self):
        """skip_scenarios=False（默认）时应包含情景分析指令。"""
        from src.python.llm.prompts import _build_expert_review_prompt
        result = _build_expert_review_prompt(
            total_mv=100_000, total_cost=80_000, total_profit=20_000,
            total_today_profit=1_000, holdings_count=5, categories={},
        )
        self.assertIn("### 情景分析", result)
        self.assertIn("上涨情景", result)
        self.assertIn("下跌情景", result)

    def test_skip_scenarios_keeps_other_content(self):
        """skip_scenarios=True 不影响其他内容块。"""
        from src.python.llm.prompts import _build_expert_review_prompt
        details = [
            {"code": "600900", "market_value": 50_000, "profit": 5_000,
             "profit_rate": 10.0, "source_api": "tencent", "name": "长江电力",
             "change_pct": 0.5},
        ]
        result = _build_expert_review_prompt(
            total_mv=100_000, total_cost=80_000, total_profit=20_000,
            total_today_profit=1_000, holdings_count=5, categories={},
            holdings_details=details,
            skip_scenarios=True,
        )
        self.assertIn("持仓明细", result)
        self.assertIn("600900", result)
        self.assertNotIn("### 情景分析", result)


@pytest.mark.unit_llm
class TestBuildPromptAppendix(unittest.TestCase):
    """_build_prompt_appendix 统一注入防御。"""

    def _make_holding(self, code: str, name: str, mv: float, rate: float | None = None) -> dict:
        return {
            "code": code,
            "name": name,
            "market_value": mv,
            "profit_rate": rate,
            "profit": mv * (rate or 0) / 100 if rate else 0,
        }

    def test_empty_holdings_returns_empty(self):
        """空持仓返回空字符串。"""
        from src.python.llm.prompts_tables import _build_prompt_appendix
        self.assertEqual(_build_prompt_appendix(None, 0, 0, 0), "")
        self.assertEqual(_build_prompt_appendix([], 100_000, 80_000, 20_000), "")

    def test_single_holding_contains_all_blocks(self):
        """单个品种包含 TOP3 + 数据速查表 + 代码白名单。"""
        from src.python.llm.prompts_tables import _build_prompt_appendix
        holdings = [self._make_holding("011506", "建信高端装备", 60_000, 8.5)]
        result = _build_prompt_appendix(holdings, 60_000, 55_000, 5_000)
        self.assertIn("TOP3", result)
        self.assertIn("数据", result)
        self.assertIn("白名单", result)
        self.assertIn("011506", result)
        self.assertIn("建信高端装备", result)

    def test_multiple_holdings_correct_ranking(self):
        """多品种时 TOP3 按市值降序排列，#1 是市值最高者。"""
        from src.python.llm.prompts_tables import _build_prompt_appendix
        holdings = [
            self._make_holding("011506", "建信高端装备", 60_000, 8.5),
            self._make_holding("601939", "建设银行", 30_000, 2.0),
            self._make_holding("561910", "电池ETF", 10_000, -1.5),
        ]
        result = _build_prompt_appendix(holdings, 100_000, 90_000, 10_000)
        # #1 应为建信高端装备（市值最高）
        self.assertIn("1. 建信高端装备", result)
        # 白名单应包含所有三个代码
        self.assertIn("011506", result)
        self.assertIn("601939", result)
        self.assertIn("561910", result)
        # 数据速查表应有各品种收益率
        self.assertIn("+8.50%", result)

    def test_zero_mv_returns_partial_content(self):
        """total_mv=0 时返回空字符串（避免除零）。"""
        from src.python.llm.prompts_tables import _build_prompt_appendix
        holdings = [self._make_holding("011506", "建信高端装备", 0, 0)]
        result = _build_prompt_appendix(holdings, 0, 0, 0)
        self.assertEqual(result, "")

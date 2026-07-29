"""LLM 提示词模块单元测试 — FAIL_REASON 常量、格式化工具、Prompt 构建函数。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/llm/test_prompts.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


@pytest.mark.unit_llm
class TestFailReasonConstants(unittest.TestCase):
    """_build_global_macro_prompt 提示词构建。"""

    def test_returns_string(self):
        """空数据时返回合理提示词。"""
        from src.python.llm.prompts import _build_global_macro_prompt
        result = _build_global_macro_prompt({}, {}, 0, 0, 0, {})
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 20)
        self.assertIn("总市值", result)

    def test_with_index_data(self):
        """指数数据正确嵌入。"""
        from src.python.llm.prompts import _build_global_macro_prompt
        a_indices = {
            "000001": {"name": "上证指数", "price": 3200, "change_pct": 0.5},
        }
        us_indices = {
            "dji": {"name": "道琼斯", "price": 40000, "change_pct": -0.2},
        }
        result = _build_global_macro_prompt(a_indices, us_indices, 1_000_000, 50_000, 0, {})
        self.assertIn("上证指数", result)
        self.assertIn("道琼斯", result)
        self.assertIn("1,000,000", result)

    def test_with_sector_flow(self):
        """行业资金流向数据嵌入。"""
        from src.python.llm.prompts import _build_global_macro_prompt
        sector_flow = [
            {"name": "电力", "change_pct": 1.5, "main_net_inflow": 500_000_000, "main_net_inflow_pct": 0.12},
        ]
        result = _build_global_macro_prompt({}, {}, 500_000, 10_000, 0, {}, sector_flow)
        self.assertIn("行业资金流向", result)
        self.assertIn("电力", result)

    def test_with_categories(self):
        """品种分类信息嵌入。"""
        from src.python.llm.prompts import _build_global_macro_prompt
        categories = {"股票": 3, "基金": 2}
        result = _build_global_macro_prompt({}, {}, 0, 0, 0, categories)
        self.assertIn("股票3只", result)
        self.assertIn("基金2只", result)


@pytest.mark.unit_llm
class TestBuildExpertReviewPrompt(unittest.TestCase):
    """_build_expert_review_prompt 提示词构建。"""

    def test_returns_string_with_overview(self):
        """包含持仓概况和明细。"""
        from src.python.llm.prompts import _build_expert_review_prompt
        result = _build_expert_review_prompt(
            total_mv=100_000, total_cost=80_000, total_profit=20_000,
            total_today_profit=1_000, holdings_count=5, categories={},
        )
        self.assertIn("持仓概况", result)
        self.assertIn("100,000", result)
        self.assertIn("5只", result)

    def test_with_holdings_details(self):
        """持仓明细嵌入。"""
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
        )
        self.assertIn("持仓明细", result)
        self.assertIn("600900", result)

    def test_with_penetrated_assets(self):
        """穿透数据嵌入。"""
        from src.python.llm.prompts import _build_expert_review_prompt
        assets = [
            {"name": "腾讯控股", "codes": ["00700"], "mv": 30_000, "sector": "互联网"},
        ]
        result = _build_expert_review_prompt(
            total_mv=100_000, total_cost=80_000, total_profit=20_000,
            total_today_profit=1_000, holdings_count=5, categories={},
            penetrated_assets=assets,
        )
        self.assertIn("穿透", result)


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
class TestBuildHoldingsSummary(unittest.TestCase):
    """_build_holdings_summary 持仓摘要构建。"""

    def test_returns_text_with_holdings(self):
        """从持仓列表生成摘要文本。"""
        from src.python.llm.prompts import _build_holdings_summary
        from src.python.models import Holding
        holdings = [
            Holding("证券", "长江电力", "600900", 100, 15.0),
            Holding("基金", "易方达中小盘", "110011", 500, 2.0),
        ]
        result = _build_holdings_summary(holdings)
        self.assertIn("长江电力", result)
        self.assertIn("600900", result)
        self.assertIn("110011", result)

    def test_with_industry_data(self):
        """行业概念标签嵌入。"""
        from src.python.llm.prompts import _build_holdings_summary
        from src.python.models import Holding
        holdings = [Holding("证券", "长江电力", "600900", 100, 15.0)]
        industry_data = {
            "600900": {"industry": "电力", "concepts": ["水电", "清洁能源"]},
        }
        result = _build_holdings_summary(holdings, industry_data=industry_data)
        self.assertIn("电力", result)
        self.assertIn("水电", result)

    def test_with_penetrated_assets(self):
        """穿透资产条目嵌入。"""
        from src.python.llm.prompts import _build_holdings_summary
        result = _build_holdings_summary([], penetrated_assets=[
            {"name": "腾讯控股", "codes": ["00700"]},
        ])
        self.assertIn("[穿透]", result)
        self.assertIn("腾讯控股", result)


@pytest.mark.unit_llm
class TestBuildNewsCorrelationSummary(unittest.TestCase):
    """_build_news_correlation_summary 新闻摘要构建。"""

    def test_returns_string(self):
        """从新闻列表生成摘要。"""
        from src.python.llm.prompts import _build_news_correlation_summary
        news = [
            {"title": "A股大涨", "intro": "今日A股大幅上涨", "matched_keywords": ["A股"]},
        ]
        result = _build_news_correlation_summary(news)
        self.assertIn("A股大涨", result)
        self.assertIn("今日A股大幅上涨", result)

    def test_empty_news(self):
        """空列表返回空字符串。"""
        from src.python.llm.prompts import _build_news_correlation_summary
        self.assertEqual(_build_news_correlation_summary([]), "")

    def test_truncates_long_titles(self):
        """长标题截断。"""
        from src.python.llm.prompts import _build_news_correlation_summary
        long_title = "长" * 200
        news = [{"title": long_title, "intro": "简介", "matched_keywords": []}]
        result = _build_news_correlation_summary(news)
        self.assertTrue(len(result) < 500)


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

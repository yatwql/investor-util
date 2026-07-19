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
    """FAIL_REASON_* 常量定义正确性。"""

    def test_constants_are_strings(self):
        """所有 FAIL_REASON 常量应为非空字符串。"""
        from src.python.llm.prompts import (
            FAIL_REASON_API_ERROR,
            FAIL_REASON_CIRCUIT_OPEN,
            FAIL_REASON_DISABLED,
            FAIL_REASON_NETWORK_ERROR,
            FAIL_REASON_NOT_CONFIGURED,
            FAIL_REASON_TIMEOUT,
        )
        for name, val in [
            ("FAIL_REASON_NOT_CONFIGURED", FAIL_REASON_NOT_CONFIGURED),
            ("FAIL_REASON_API_ERROR", FAIL_REASON_API_ERROR),
            ("FAIL_REASON_NETWORK_ERROR", FAIL_REASON_NETWORK_ERROR),
            ("FAIL_REASON_TIMEOUT", FAIL_REASON_TIMEOUT),
            ("FAIL_REASON_CIRCUIT_OPEN", FAIL_REASON_CIRCUIT_OPEN),
            ("FAIL_REASON_DISABLED", FAIL_REASON_DISABLED),
        ]:
            with self.subTest(name=name):
                self.assertIsInstance(val, str)
                self.assertTrue(len(val) > 0)

    def test_constants_are_unique(self):
        """所有 FAIL_REASON 常量值互不相同。"""
        from src.python.llm.prompts import (
            FAIL_REASON_API_ERROR,
            FAIL_REASON_CIRCUIT_OPEN,
            FAIL_REASON_DISABLED,
            FAIL_REASON_NETWORK_ERROR,
            FAIL_REASON_NOT_CONFIGURED,
            FAIL_REASON_TIMEOUT,
        )
        values = {
            FAIL_REASON_NOT_CONFIGURED,
            FAIL_REASON_API_ERROR,
            FAIL_REASON_NETWORK_ERROR,
            FAIL_REASON_TIMEOUT,
            FAIL_REASON_CIRCUIT_OPEN,
            FAIL_REASON_DISABLED,
        }
        self.assertEqual(len(values), 6)


@pytest.mark.unit_llm
class TestModuleFailureDict(unittest.TestCase):
    """LLM_MODULE_FAILURE 字典操作。"""

    def setUp(self):
        from src.python.llm.prompts import LLM_MODULE_FAILURE
        self._orig = dict(LLM_MODULE_FAILURE)
        LLM_MODULE_FAILURE.clear()

    def tearDown(self):
        from src.python.llm.prompts import LLM_MODULE_FAILURE
        LLM_MODULE_FAILURE.clear()
        LLM_MODULE_FAILURE.update(self._orig)

    def test_set_and_get(self):
        """设置模块失败原因后能正确读取。"""
        from src.python.llm.prompts import (
            FAIL_REASON_DISABLED,
            LLM_MODULE_FAILURE,
        )
        LLM_MODULE_FAILURE["global_macro"] = FAIL_REASON_DISABLED
        self.assertEqual(LLM_MODULE_FAILURE.get("global_macro"), FAIL_REASON_DISABLED)

    def test_clear_key(self):
        """清除指定模块的失败原因后返回 None。"""
        from src.python.llm.prompts import (
            FAIL_REASON_API_ERROR,
            LLM_MODULE_FAILURE,
        )
        LLM_MODULE_FAILURE["expert_review"] = FAIL_REASON_API_ERROR
        LLM_MODULE_FAILURE.pop("expert_review", None)
        self.assertIsNone(LLM_MODULE_FAILURE.get("expert_review"))

    def test_unknown_key_returns_none(self):
        """未记录的模块键返回 None。"""
        from src.python.llm.prompts import LLM_MODULE_FAILURE
        self.assertIsNone(LLM_MODULE_FAILURE.get("nonexistent_module"))

    def test_direct_import_from_prompts(self):
        """从 prompts 模块直接导入可访问 LLM_MODULE_FAILURE。"""
        from src.python.llm.prompts import LLM_MODULE_FAILURE
        self.assertIsInstance(LLM_MODULE_FAILURE, dict)


@pytest.mark.unit_llm
class TestFmtWan(unittest.TestCase):
    """_fmt_wan 中文单位格式化。"""

    def test_zero(self):
        from src.python.llm.prompts import _fmt_wan
        self.assertEqual(_fmt_wan(0), "0")

    def test_under_wan(self):
        from src.python.llm.prompts import _fmt_wan
        self.assertEqual(_fmt_wan(500), "500")
        self.assertEqual(_fmt_wan(9999), "9,999")

    def test_wan(self):
        from src.python.llm.prompts import _fmt_wan
        self.assertEqual(_fmt_wan(15_000), "1.5万")
        self.assertEqual(_fmt_wan(12_345_678), "1234.6万")

    def test_yi(self):
        from src.python.llm.prompts import _fmt_wan
        self.assertEqual(_fmt_wan(150_000_000), "1.50亿")
        self.assertEqual(_fmt_wan(2_000_000_000), "20.00亿")


@pytest.mark.unit_llm
class TestFmtHoldingLine(unittest.TestCase):
    """_fmt_holding_line 持仓明细行格式化。"""

    def test_basic_tencent(self):
        """腾讯 source_api → 含今日涨跌幅。"""
        from src.python.llm.prompts import _fmt_holding_line
        h = {
            "code": "600900", "market_value": 50_000, "profit": 5_000,
            "profit_rate": 10.0, "nav_date": "2026-07-07", "source_api": "tencent",
            "name": "长江电力", "change_pct": 0.5,
        }
        result = _fmt_holding_line(h)
        self.assertIn("600900", result)
        self.assertIn("市值5.0万", result)
        self.assertIn("盈亏5,000", result)
        self.assertIn("今+0.50%", result)

    def test_eastmoney_with_nav_date(self):
        """非 Tencent source_api + nav_date → 含净值日期标注。"""
        from src.python.llm.prompts import _fmt_holding_line
        h = {
            "code": "110011", "market_value": 30_000, "profit": -1_000,
            "profit_rate": -3.3, "nav_date": "2026-07-06", "source_api": "eastmoney",
            "name": "易方达中小盘", "change_pct": 0,
        }
        result = _fmt_holding_line(h)
        self.assertIn("净值:2026-07-06", result)

    def test_show_cost(self):
        """show_cost=True 时显示成本。"""
        from src.python.llm.prompts import _fmt_holding_line
        h = {
            "code": "600519", "market_value": 200_000, "cost": 150_000, "profit": 50_000,
            "profit_rate": 33.33, "nav_date": "", "source_api": "tencent",
            "name": "贵州茅台", "change_pct": 1.0,
        }
        result = _fmt_holding_line(h, show_cost=True)
        self.assertIn("成本", result)
        self.assertIn("市值", result)

    def test_compact_mode(self):
        """compact=True 省略今日涨跌幅。"""
        from src.python.llm.prompts import _fmt_holding_line
        h = {
            "code": "600900", "market_value": 50_000, "profit": 5_000,
            "profit_rate": 10.0, "nav_date": "", "source_api": "tencent",
            "name": "长江电力", "change_pct": 0.5,
        }
        compact = _fmt_holding_line(h, compact=True)
        full = _fmt_holding_line(h, compact=False)
        self.assertNotIn("今", compact)
        self.assertIn("今", full)

    def test_qdii_extended_suffix(self):
        """QDII 基金含 (QDII滞后1日) 后缀。"""
        from src.python.llm.prompts import _fmt_holding_line
        h = {
            "code": "164906", "market_value": 10_000, "profit": 500,
            "profit_rate": 5.0, "nav_date": "2026-07-06", "source_api": "eastmoney",
            "name": "交银中证海外中国互联网指数(QDII)", "change_pct": 0,
        }
        result = _fmt_holding_line(h)
        self.assertIn("QDII滞后1日", result)

    def test_negative_profit(self):
        """亏损时显示负值。"""
        from src.python.llm.prompts import _fmt_holding_line
        h = {
            "code": "600010", "market_value": 10_000, "profit": -2_000,
            "profit_rate": -16.67, "nav_date": "", "source_api": "tencent",
            "name": "测试", "change_pct": -0.5,
        }
        result = _fmt_holding_line(h)
        self.assertIn("-2,000", result)
        self.assertIn("-16.67%", result)


@pytest.mark.unit_llm
class TestSystemPrompts(unittest.TestCase):
    """系统提示词常量为非空字符串。"""

    def test_system_global_macro(self):
        from src.python.llm.prompts import _SYSTEM_GLOBAL_MACRO
        self.assertIsInstance(_SYSTEM_GLOBAL_MACRO, str)
        self.assertTrue(len(_SYSTEM_GLOBAL_MACRO) > 50)

    def test_system_expert_review(self):
        from src.python.llm.prompts import _SYSTEM_EXPERT_REVIEW
        self.assertIsInstance(_SYSTEM_EXPERT_REVIEW, str)
        self.assertIn("Phase 1", _SYSTEM_EXPERT_REVIEW)

    def test_system_expert_review_competitive_context_constraint(self):
        """专家复盘 prompt 包含竞争语境约束。"""
        from src.python.llm.prompts import _SYSTEM_EXPERT_REVIEW
        self.assertIn("竞争语境约束", _SYSTEM_EXPERT_REVIEW)
        self.assertIn("不得使用", _SYSTEM_EXPERT_REVIEW)
        self.assertIn("口径差异", _SYSTEM_EXPERT_REVIEW)

    def test_system_health_check(self):
        from src.python.llm.prompts import _SYSTEM_HEALTH_CHECK
        self.assertIsInstance(_SYSTEM_HEALTH_CHECK, str)
        self.assertIn("风险分散度", _SYSTEM_HEALTH_CHECK)

    def test_system_penetration_deep(self):
        from src.python.llm.prompts import _SYSTEM_PENETRATION_DEEP
        self.assertIsInstance(_SYSTEM_PENETRATION_DEEP, str)
        self.assertIn("行业集中度", _SYSTEM_PENETRATION_DEEP)

    def test_system_news_correlation(self):
        from src.python.llm.prompts import _SYSTEM_NEWS_CORRELATION
        self.assertIsInstance(_SYSTEM_NEWS_CORRELATION, str)
        self.assertIn("关联度", _SYSTEM_NEWS_CORRELATION)


@pytest.mark.unit_llm
class TestBuildGlobalMacroPrompt(unittest.TestCase):
    """_build_global_macro_prompt 提示词构建。"""

    def test_returns_string(self):
        """空数据时返回合理提示词。"""
        from src.python.llm.prompts import _build_global_macro_prompt
        result = _build_global_macro_prompt({}, {}, 0, 0, {})
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
        result = _build_global_macro_prompt(a_indices, us_indices, 1_000_000, 50_000, {})
        self.assertIn("上证指数", result)
        self.assertIn("道琼斯", result)
        self.assertIn("1,000,000", result)

    def test_with_sector_flow(self):
        """行业资金流向数据嵌入。"""
        from src.python.llm.prompts import _build_global_macro_prompt
        sector_flow = [
            {"name": "电力", "change_pct": 1.5, "main_net_inflow": 500_000_000, "main_net_inflow_pct": 0.12},
        ]
        result = _build_global_macro_prompt({}, {}, 500_000, 10_000, {}, sector_flow)
        self.assertIn("行业资金流向", result)
        self.assertIn("电力", result)

    def test_with_categories(self):
        """品种分类信息嵌入。"""
        from src.python.llm.prompts import _build_global_macro_prompt
        categories = {"股票": 3, "基金": 2}
        result = _build_global_macro_prompt({}, {}, 0, 0, categories)
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

    def test_no_prefix_code_is_other(self):
        """无交易所前缀且非 A 股数字特征的代码归属为其他。"""
        from src.python.llm.prompts import _calc_country_exposure
        details = [{"code": "900900", "market_value": 50_000}]
        result = _calc_country_exposure(details)
        combined = " ".join(result)
        self.assertIn("其他", combined)


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

"""LLM 提示词构建模块单元测试。

测试目标：
  - _build_global_macro_prompt — 北京时间注入 + 紧凑格式
  - _build_expert_review_prompt — 北京时间注入 + 穿透数据拼接
  - _build_holdings_summary — 持仓摘要格式和内容
  - _build_news_correlation_summary — 新闻摘要格式和内容

运行：
  pytest src/test/unit/llm/test_llm_prompts.py -v
"""

from __future__ import annotations

import unittest
from collections import namedtuple

import pytest

from src.python.llm.prompts import (
    _SYSTEM_EXPERT_REVIEW,
    _build_expert_review_prompt,
    _build_global_macro_prompt,
    _build_holdings_summary,
    _build_news_correlation_summary,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


# ═══════════════════════════════════════════════════════════
#  _build_global_macro_prompt
# ═══════════════════════════════════════════════════════════


class TestBuildGlobalMacroPrompt(unittest.TestCase):
    """测试全球政经局势用户提示词。"""

    def test_has_timestamp(self) -> None:
        r = _build_global_macro_prompt({}, {}, 100.0, 10.0, 0, {"股票": 3})
        self.assertIn("北京时间", r)
        self.assertIn("当前时间", r)

    def test_compact_format(self) -> None:
        a_idx = {"sh000001": {"name": "上证指数", "price": 3120, "change_pct": 1.2}}
        r = _build_global_macro_prompt(a_idx, {}, 100000, 5000, 0, {"股票": 3, "基金": 2})
        self.assertIn("上证指数", r)
        self.assertIn("3120", r)
        self.assertIn("+1.20%", r)
        self.assertIn("股票3只", r)
        self.assertIn("基金2只", r)

    def test_single_line_indices(self) -> None:
        """指数应为紧凑单行格式。"""
        a_idx = {"sh000001": {"name": "上证", "price": 3000, "change_pct": -0.5}}
        r = _build_global_macro_prompt(a_idx, {}, 0, 0, 0, {})
        self.assertIn("上证3000(-0.50%)", r)

    def test_no_categories(self) -> None:
        r = _build_global_macro_prompt({}, {}, 0, 0, 0, {})
        self.assertIn("当前时间", r)
        # 不应该有 AssertionError

    def test_with_sector_flow(self) -> None:
        """传入行业资金流向时，prompt 应包含资金流向数据。"""
        sector_flow = [
            {"name": "半导体", "change_pct": 2.5, "main_net_inflow": 1500000000, "main_net_inflow_pct": 3.2},
            {"name": "银行", "change_pct": -0.8, "main_net_inflow": -500000000, "main_net_inflow_pct": -1.1},
        ]
        r = _build_global_macro_prompt({}, {}, 100000, 5000, 0, {"股票": 3}, sector_flow=sector_flow)
        self.assertIn("行业资金流向", r)
        self.assertIn("半导体", r)
        self.assertIn("+2.50%", r)
        self.assertIn("银行", r)
        self.assertIn("-0.80%", r)
        self.assertIn("主力净流入", r)

    def test_sector_flow_none(self) -> None:
        """sector_flow=None 时不应包含资金流向内容。"""
        r = _build_global_macro_prompt({}, {}, 0, 0, 0, {})
        self.assertNotIn("行业资金流向", r)

    def test_us_index_and_thousand_separator(self) -> None:
        """美股指数嵌入 + 市值千分位格式化。"""
        a_indices = {
            "000001": {"name": "上证指数", "price": 3200, "change_pct": 0.5},
        }
        us_indices = {
            "dji": {"name": "道琼斯", "price": 40000, "change_pct": -0.2},
        }
        r = _build_global_macro_prompt(a_indices, us_indices, 1_000_000, 50_000, 0, {})
        self.assertIn("上证指数", r)
        self.assertIn("道琼斯", r)
        self.assertIn("1,000,000", r)

    def test_empty_data_contains_market_value_label(self) -> None:
        """空数据时仍包含总市值标签。"""
        r = _build_global_macro_prompt({}, {}, 0, 0, 0, {})
        self.assertIn("总市值", r)


# ═══════════════════════════════════════════════════════════
#  _build_expert_review_prompt
# ═══════════════════════════════════════════════════════════


class TestBuildReviewPrompt(unittest.TestCase):
    """测试智囊团深度复盘用户提示词。"""

    def test_has_timestamp(self) -> None:
        r = _build_expert_review_prompt(100, 80, 20, 5, 5, {"股票": 3})
        self.assertIn("北京时间", r)
        self.assertIn("当前时间", r)

    def test_with_penetration(self) -> None:
        pen = [
            {"name": "茅台", "codes": ["600519"], "mv": 50000, "sector": "消费"},
            {"name": "宁德", "codes": ["300750"], "mv": 30000, "sector": "新能源"},
        ]
        r = _build_expert_review_prompt(100000, 80000, 20000, 1000, 3, {"基金": 2}, pen)
        self.assertIn("茅台", r)
        self.assertIn("穿透", r)

    def test_without_penetration(self) -> None:
        r = _build_expert_review_prompt(100, 80, 20, 5, 5, {"股票": 3})
        self.assertNotIn("穿透", r)

    def test_compact_format(self) -> None:
        r = _build_expert_review_prompt(100000, 80000, 20000, 1000, 3, {"股票": 2, "基金": 1})
        self.assertIn("股票2只", r)
        self.assertIn("基金1只", r)

    def test_nav_date_label(self) -> None:
        """tencent→今涨跌幅，场外→净值日期。"""
        details = [
            {"code": "600900", "market_value": 100000, "cost": 80000,
             "profit": 20000, "profit_rate": 25.0, "change_pct": 1.2,
             "nav_date": "", "source_api": "tencent"},
            {"code": "110011", "market_value": 50000, "cost": 40000,
             "profit": 10000, "profit_rate": 25.0, "change_pct": -0.5,
             "nav_date": "2026-06-26", "source_api": "eastmoney"},
        ]
        r = _build_expert_review_prompt(150000, 120000, 30000, 1500, 2, {},
                                 holdings_details=details)
        # compact 模式省略今日涨跌幅，保留净值日期
        self.assertNotIn("今+1.20%", r)
        self.assertIn("净值:2026-06-26", r)

    def test_nav_date_empty_fallback(self) -> None:
        """compact 模式下场内品种无今日涨跌幅（减少 token）。"""
        details = [
            {"code": "600900", "market_value": 100000, "cost": 80000,
             "profit": 20000, "profit_rate": 25.0, "change_pct": 1.2},
        ]
        r = _build_expert_review_prompt(100000, 80000, 20000, 1200, 1, {},
                                 holdings_details=details)
        self.assertNotIn("今+1.20%", r)

    def test_qdii_label(self) -> None:
        """compact 模式下 QDII 品种标注 (QDII滞后1日)，省略今日涨跌幅。"""
        details = [
            {"code": "000041", "name": "华夏全球QDII混合", "market_value": 30000, "cost": 25000,
             "profit": 5000, "profit_rate": 20.0, "change_pct": 0.3,
             "nav_date": "2026-06-26", "source_api": "eastmoney"},
            {"code": "513100", "name": "纳指ETF(QDII)", "market_value": 20000, "cost": 18000,
             "profit": 2000, "profit_rate": 11.1, "change_pct": 1.5,
             "nav_date": "", "source_api": "tencent"},
        ]
        r = _build_expert_review_prompt(50000, 43000, 7000, 200, 2, {},
                                 holdings_details=details)
        self.assertIn("净值:2026-06-26(QDII滞后1日)", r)
        # compact 模式省略今日涨跌幅
        self.assertNotIn("今+1.50%", r)
        self.assertIn("(QDII滞后1日)", r)

    def test_system_expert_constraint_updated(self) -> None:
        """_SYSTEM_EXPERT_REVIEW 包含净值约束和 QDII 说明。"""
        self.assertIn("净值", _SYSTEM_EXPERT_REVIEW)
        self.assertIn("QDII", _SYSTEM_EXPERT_REVIEW)
        self.assertIn("滞后", _SYSTEM_EXPERT_REVIEW)

    def test_overview_and_detail_blocks(self) -> None:
        """持仓概况 + 千分位市值 + 持仓明细。"""
        r = _build_expert_review_prompt(100_000, 80_000, 20_000, 1_000, 5, {})
        self.assertIn("持仓概况", r)
        self.assertIn("100,000", r)
        self.assertIn("5只", r)
        details = [
            {"code": "600900", "market_value": 50_000, "profit": 5_000,
             "profit_rate": 10.0, "source_api": "tencent", "name": "长江电力",
             "change_pct": 0.5},
        ]
        r2 = _build_expert_review_prompt(100_000, 80_000, 20_000, 1_000, 5, {},
                                 holdings_details=details)
        self.assertIn("持仓明细", r2)
        self.assertIn("600900", r2)


# ═══════════════════════════════════════════════════════════
#  _build_holdings_summary — 持仓摘要生成
# ═══════════════════════════════════════════════════════════


class TestBuildHoldingsSummary(unittest.TestCase):
    """测试 _build_holdings_summary 的格式和内容。"""

    def setUp(self) -> None:
        Holding = namedtuple("Holding", ["name", "code"])
        self.holdings = [
            Holding(name="长江电力", code="600900"),
            Holding(name="贵州茅台", code="600519"),
        ]
        self.penetrated = [
            {"name": "宁德时代", "codes": ["300750"]},
        ]

    def test_basic(self) -> None:
        result = _build_holdings_summary(self.holdings)
        self.assertIn("长江电力", result)
        self.assertIn("600900", result)
        self.assertIn("600519", result)

    def test_with_penetration(self) -> None:
        result = _build_holdings_summary(self.holdings, self.penetrated)
        self.assertIn("[穿透]", result)

    def test_with_industry_data(self) -> None:
        """industry_data 中包含行业和概念 → 显示到摘要中。"""
        industry_data = {
            "600900": {"industry": "电力", "concepts": ["核电", "水电"]},
            # 生产链路经 fetcher 网关已剥离申万层级后缀（白酒Ⅱ → 白酒）
            "600519": {"industry": "白酒", "concepts": ["白酒", "超级品牌"]},
        }
        result = _build_holdings_summary(self.holdings, industry_data=industry_data)
        self.assertIn("电力", result)
        self.assertIn("白酒", result)
        self.assertIn("核电", result)

    def test_empty(self) -> None:
        result = _build_holdings_summary([], None)
        self.assertEqual(result, "")

    def test_limit_20(self) -> None:
        """超过 20 只持仓时截断。"""
        H = namedtuple("Holding", ["name", "code"])
        many = [H(name=f"股票{i}", code=f"{i:06d}") for i in range(30)]
        result = _build_holdings_summary(many)
        lines = [l for l in result.split("\n") if l.strip()]
        # 最多 20 行持仓
        holding_lines = [l for l in lines if "[穿透]" not in l]
        self.assertLessEqual(len(holding_lines), 20)


# ═══════════════════════════════════════════════════════════
#  _build_news_correlation_summary — 新闻摘要生成（LLM 关联分析用）
# ═══════════════════════════════════════════════════════════


class TestBuildNewsSummary(unittest.TestCase):
    """测试 _build_news_correlation_summary 的格式和内容。"""

    def test_basic(self) -> None:
        news = [
            {"title": "能源改革新方案", "intro": "国家能源局发布电力改革方案...",
             "matched_keywords": ["长江电力"]},
        ]
        result = _build_news_correlation_summary(news)
        self.assertIn("能源改革", result)
        self.assertIn("长江电力", result)

    def test_empty(self) -> None:
        self.assertEqual(_build_news_correlation_summary([]), "")

    def test_limit_30(self) -> None:
        """超过 30 条时截断。"""
        many = [{"title": f"新闻{i}", "matched_keywords": []} for i in range(50)]
        result = _build_news_correlation_summary(many)
        # 最多 30 条
        count = result.count("标题:")
        self.assertLessEqual(count, 30)

    def test_long_title_truncated(self) -> None:
        """超长标题截断，避免摘要过长。"""
        long_title = "长" * 200
        news = [{"title": long_title, "intro": "简介", "matched_keywords": []}]
        result = _build_news_correlation_summary(news)
        self.assertTrue(len(result) < 500)

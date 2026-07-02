"""新闻关键词提取模块单元测试。

测试目标：
  - build_holding_keywords — 持仓/穿透关键词提取逻辑

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_news_keywords -v
"""

from __future__ import annotations

import unittest

from src.python.models import Holding
from src.python.providers.news_keywords import build_holding_keywords
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_news]




class TestBuildHoldingKeywords(unittest.TestCase):
    """build_holding_keywords 测试。"""

    def test_empty_holdings(self) -> None:
        """空持仓 → 空列表。"""
        self.assertEqual(build_holding_keywords([]), [])

    def test_code_extracted(self) -> None:
        """股票代码被提取为核心关键词。"""
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertIn("600900", keywords)

    def test_name_extracted(self) -> None:
        """持仓中文名称被提取。"""
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertIn("长江电力", keywords)

    def test_etf_name_clean(self) -> None:
        """ETF 名称去掉后缀后仍能提取核心词。"""
        holdings = [
            Holding(account="证券", name="沪深300ETF", code="510300",
                    shares=100, cost_price=4.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertIn("沪深", keywords)

    def test_fund_clean(self) -> None:
        """基金名称去掉后缀后提取核心词。"""
        holdings = [
            Holding(account="基金", name="易方达蓝筹精选混合", code="005827",
                    shares=1000, cost_price=2.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertIn("易方达蓝筹精选", keywords)

    def test_lianjie_handling(self) -> None:
        """联接基金 → 拆分提取母基金名称。"""
        holdings = [
            Holding(account="基金", name="天弘沪深300ETF联接A", code="000961",
                    shares=1000, cost_price=1.5),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertIn("天弘沪深", keywords)

    def test_qdii_suffix_stripped(self) -> None:
        """QDII 后缀被剥离。"""
        holdings = [
            Holding(account="基金", name="华夏恒生ETF联接(QDII)A", code="000071",
                    shares=1000, cost_price=1.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertIn("华夏恒生", keywords)

    def test_penetrated_assets_added(self) -> None:
        """穿透资产名称和代码被加入关键词。"""
        holdings = [Holding(account="证券", name="贵州茅台", code="600519",
                            shares=100, cost_price=200.0)]
        penetrated = [
            {"name": "贵州茅台", "codes": ["600519"]},
            {"name": "宁德时代", "codes": ["300750"]},
        ]
        keywords = build_holding_keywords(holdings, penetrated_assets=penetrated)
        self.assertIn("300750", keywords)
        self.assertIn("宁德时代", keywords)

    def test_english_asset_name_added(self) -> None:
        """纯英文穿透资产名直接添加。"""
        holdings = [Holding(account="证券", name="标普500", code="SPY",
                            shares=100, cost_price=400.0)]
        penetrated = [{"name": "AAPL", "codes": ["AAPL"]}]
        keywords = build_holding_keywords(holdings, penetrated_assets=penetrated)
        self.assertIn("AAPL", keywords)

    def test_max_keywords_limit(self) -> None:
        """max_keywords 限制返回数量。"""
        holdings = [
            Holding(account="证券", name=f"股票{i:04d}", code=f"600{i:04d}",
                    shares=100, cost_price=10.0)
            for i in range(20)
        ]
        keywords = build_holding_keywords(holdings, max_keywords=10)
        self.assertLessEqual(len(keywords), 10)

    def test_duplicates_removed(self) -> None:
        """同一关键词不重复出现。"""
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
            Holding(account="证券", name="长江电力", code="600900",
                    shares=200, cost_price=12.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertEqual(keywords.count("600900"), 1)

    def test_short_terms_filtered(self) -> None:
        """小于 2 字的词（如助词/量词）不被提取。"""
        holdings = [
            Holding(account="证券", name="A股", code="000001",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings)
        # "A股" 中的 "A" 是英文，"股" 是中文单字，均不被提取
        self.assertNotIn("A", keywords)

    def test_empty_code_skipped(self) -> None:
        """代码为空时跳过。"""
        holdings = [
            Holding(account="证券", name="现金", code="",
                    shares=100, cost_price=1.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertEqual(keywords, ["现金"])

    def test_sort_by_length_desc(self) -> None:
        """关键词按长度降序排列（长关键词优先匹配）。"""
        holdings = [
            Holding(account="证券", name="易方达蓝筹精选混合", code="005827",
                    shares=100, cost_price=2.0),
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings)
        # 长词应在短词前面
        idx_long = keywords.index("易方达蓝筹精选")
        idx_short = keywords.index("长江电力")
        self.assertLess(idx_long, idx_short)

    def test_empty_name_with_code(self) -> None:
        """名称为空但代码存在 → 只提取代码。"""
        holdings = [
            Holding(account="证券", name="", code="600900",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertEqual(keywords, ["600900"])

    def test_empty_name_and_empty_code(self) -> None:
        """名称和代码均为空 → 返回空列表。"""
        holdings = [
            Holding(account="证券", name="", code="",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertEqual(keywords, [])

    def test_name_special_chars(self) -> None:
        """名称含括号 → 正确提取中文关键词，括号不干扰。"""
        holdings = [
            Holding(account="证券", name="药明康德(港股)", code="02359",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertIn("药明康德", keywords)
        self.assertIn("02359", keywords)

    def test_name_with_dash(self) -> None:
        """名称含破折号 → 正确提取中文关键词。"""
        holdings = [
            Holding(account="证券", name="ST-华英", code="002321",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertIn("华英", keywords)
        self.assertIn("002321", keywords)

    def test_name_only_ascii(self) -> None:
        """名称只有 ASCII 字符 → 只提取代码。"""
        holdings = [
            Holding(account="美股", name="Apple Inc.", code="AAPL",
                    shares=100, cost_price=150.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertEqual(keywords, ["AAPL"])

    def test_penetrated_assets_empty_list(self) -> None:
        """penetrated_assets=[] 与默认行为一致。"""
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
        ]
        keywords_with = build_holding_keywords(holdings, penetrated_assets=[])
        keywords_without = build_holding_keywords(holdings)
        self.assertEqual(keywords_with, keywords_without)

    def test_penetrated_assets_none(self) -> None:
        """penetrated_assets=None 不崩溃。"""
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings, penetrated_assets=None)
        self.assertIsInstance(keywords, list)
        self.assertIn("600900", keywords)

    def test_penetrated_assets_empty_name_and_empty_codes(self) -> None:
        """穿透资产名称和代码均为空 → 不影响已有关键词。"""
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
        ]
        penetrated = [{"name": "", "codes": [""]}]
        keywords = build_holding_keywords(holdings, penetrated_assets=penetrated)
        self.assertIn("600900", keywords)
        self.assertIn("长江电力", keywords)

    def test_penetrated_assets_name_without_codes(self) -> None:
        """穿透资产有名称无代码。"""
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
        ]
        penetrated = [{"name": "宁德时代", "codes": []}]
        keywords = build_holding_keywords(holdings, penetrated_assets=penetrated)
        self.assertIn("宁德时代", keywords)

    def test_lianjie_with_single_part(self) -> None:
        """联接基金但提取不到两个中文片段 → 不额外添加。"""
        holdings = [
            Holding(account="基金", name="联接A", code="000000",
                    shares=100, cost_price=1.0),
        ]
        keywords = build_holding_keywords(holdings)
        self.assertEqual(keywords, ["000000"])

    def test_max_keywords_zero(self) -> None:
        """max_keywords=0 返回空列表。"""
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                    shares=100, cost_price=10.0),
        ]
        keywords = build_holding_keywords(holdings, max_keywords=0)
        self.assertEqual(keywords, [])


if __name__ == "__main__":
    unittest.main()

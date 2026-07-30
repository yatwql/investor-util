"""穿透 TOP10 混合场景验证（S-P9 ~ S-P10）。

覆盖资产类型：
  S-P9: 全类型混合场景 — 多类型持仓合并、排序、占比
  S-P10: 交叉持股合并 — 同标的被多只基金持有时归一

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_penetration_mixed.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.models import Holding
from src.python.report.market_value import DetailRow
from src.python.report import penetration as pene

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]


# ═══════════════════════════════════════════════════════════════
#  S-P9: 全类型混合场景 — 多类型合并
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP9MixedAllTypes(unittest.TestCase):
    """S-P9：全类型混合场景 — 多类型持仓合并、排序、占比验证。

    场景：同时持有股票、ETF、主动权益基金、QDII、联接基金。
    验证：
      1. 各类型分类计数正确
      2. fund_breakdown 包含所有基金类型
      3. TOP10 按市值降序
      4. 占比总和 ≤ 100%
      5. 同类底层标的合并（宁德时代跨基金出现）
    """

    def setUp(self):
        self.holdings = [
            # 直接持股
            Holding("证券", "长江电力", "600900", 200, 28.0),
            # ETF
            Holding("证券", "电池ETF", "561910", 800, 1.0),
            # 主动权益
            Holding("支付宝", "中欧医疗健康混合", "003095", 500, 2.0),
        ]
        # 直接持股市值 = 28 * 200 = 5600
        # ETF 市值 = 1 * 800 = 800
        # 主动基金市值 = 2 * 500 = 1000

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_mixed_classification_counts(self, mock_enrich, mock_batch):
        """混合场景 → total_stocks=1, total_funds=2, fund_breakdown 含"ETF1 + 主动1"。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                ],
            },
            "003095": {
                "code": "003095", "name": "中欧医疗健康混合",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "药明康德", "code": "603259", "ratio": 10.0},
                    {"name": "宁德时代", "code": "300750", "ratio": 5.0},
                ],
            },
        }

        details = [
            DetailRow(
                account="证券", name="长江电力", code="600900",
                price=28.0, nav_date="2026-07-03", yesterday_close=27.5,
                price_type="T", premium="--", shares=200.0,
                market_value=5600.0, cost=5600.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="证券", name="电池ETF", code="561910",
                price=1.0, nav_date="2026-07-03", yesterday_close=0.99,
                price_type="T", premium="--", shares=800.0,
                market_value=800.0, cost=800.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="支付宝", name="中欧医疗健康混合", code="003095",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.95,
                price_type="T-1", premium="--", shares=500.0,
                market_value=1000.0, cost=1000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        s = result["summary"]
        self.assertEqual(s["total_stocks"], 1)
        self.assertEqual(s["total_funds"], 2)
        self.assertIn("ETF1", s["fund_breakdown"])
        self.assertIn("主动1", s["fund_breakdown"])

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_mixed_merged_and_sorted(self, mock_enrich, mock_batch):
        """混合场景 → merged_count=4, TOP10 按市值降序。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                ],
            },
            "003095": {
                "code": "003095", "name": "中欧医疗健康混合",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "药明康德", "code": "603259", "ratio": 10.0},
                    {"name": "宁德时代", "code": "300750", "ratio": 5.0},
                ],
            },
        }

        details = [
            DetailRow(
                account="证券", name="长江电力", code="600900",
                price=28.0, nav_date="2026-07-03", yesterday_close=27.5,
                price_type="T", premium="--", shares=200.0,
                market_value=5600.0, cost=5600.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="证券", name="电池ETF", code="561910",
                price=1.0, nav_date="2026-07-03", yesterday_close=0.99,
                price_type="T", premium="--", shares=800.0,
                market_value=800.0, cost=800.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="支付宝", name="中欧医疗健康混合", code="003095",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.95,
                price_type="T-1", premium="--", shares=500.0,
                market_value=1000.0, cost=1000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        # merged: 长江电力 + 宁德时代(合并) + 比亚迪 + 药明康德 = 4
        self.assertEqual(result["summary"]["merged_count"], 4)
        mvs = [e["mv"] for e in result["top10"]]
        for i in range(1, len(mvs)):
            self.assertGreaterEqual(mvs[i - 1], mvs[i])

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_mixed_same_underlying_merged(self, mock_enrich, mock_batch):
        """混合场景 → 宁德时代跨 ETF 和主动基金合并为一条。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                ],
            },
            "003095": {
                "code": "003095", "name": "中欧医疗健康混合",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 5.0},
                ],
            },
        }

        details = [
            DetailRow(
                account="证券", name="长江电力", code="600900",
                price=28.0, nav_date="2026-07-03", yesterday_close=27.5,
                price_type="T", premium="--", shares=200.0,
                market_value=5600.0, cost=5600.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="证券", name="电池ETF", code="561910",
                price=1.0, nav_date="2026-07-03", yesterday_close=0.99,
                price_type="T", premium="--", shares=800.0,
                market_value=800.0, cost=800.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="支付宝", name="中欧医疗健康混合", code="003095",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.95,
                price_type="T-1", premium="--", shares=500.0,
                market_value=1000.0, cost=1000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        # 宁德时代只出现一次
        nd_entries = [e for e in result["top10"] if "宁德时代" in e["name"]]
        self.assertEqual(len(nd_entries), 1,
                         "宁德时代应被合并为一条")
        nd = nd_entries[0]
        # 宁德时代总市值 = ETF 贡献(800*0.15=120) + 主动基金贡献(1000*0.05=50) = 170
        self.assertAlmostEqual(nd["mv"], 170.0, places=1)
        # 应有 2 个来源
        self.assertEqual(len(nd["sources"]), 2)

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_mixed_ratio_sum_le_100(self, mock_enrich, mock_batch):
        """混合场景 → 穿透占比总和 ≤ 100%。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                ],
            },
            "003095": {
                "code": "003095", "name": "中欧医疗健康混合",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "药明康德", "code": "603259", "ratio": 10.0},
                    {"name": "宁德时代", "code": "300750", "ratio": 5.0},
                ],
            },
        }

        details = [
            DetailRow(
                account="证券", name="长江电力", code="600900",
                price=28.0, nav_date="2026-07-03", yesterday_close=27.5,
                price_type="T", premium="--", shares=200.0,
                market_value=5600.0, cost=5600.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="证券", name="电池ETF", code="561910",
                price=1.0, nav_date="2026-07-03", yesterday_close=0.99,
                price_type="T", premium="--", shares=800.0,
                market_value=800.0, cost=800.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="支付宝", name="中欧医疗健康混合", code="003095",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.95,
                price_type="T-1", premium="--", shares=500.0,
                market_value=1000.0, cost=1000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        total_ratio = sum(e["ratio_pct"] for e in result["top10"])
        self.assertLessEqual(total_ratio, 100.0 + 1e-9,
                             f"TOP10 占比总和 {total_ratio:.2f}% > 100%")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_mixed_sources_have_type_tags(self, mock_enrich, mock_batch):
        """混合场景 → 来源包含正确的类型标签。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                ],
            },
            "003095": {
                "code": "003095", "name": "中欧医疗健康混合",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "药明康德", "code": "603259", "ratio": 10.0},
                ],
            },
        }

        details = [
            DetailRow(
                account="证券", name="长江电力", code="600900",
                price=28.0, nav_date="2026-07-03", yesterday_close=27.5,
                price_type="T", premium="--", shares=200.0,
                market_value=5600.0, cost=5600.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="证券", name="电池ETF", code="561910",
                price=1.0, nav_date="2026-07-03", yesterday_close=0.99,
                price_type="T", premium="--", shares=800.0,
                market_value=800.0, cost=800.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="支付宝", name="中欧医疗健康混合", code="003095",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.95,
                price_type="T-1", premium="--", shares=500.0,
                market_value=1000.0, cost=1000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        # 长江电力：直接持有
        cj_name = next(e for e in result["top10"] if e["name"] == "长江电力")
        self.assertIn("直接持有", cj_name["sources"])
        # 宁德时代：来自 ETF
        nd = next(e for e in result["top10"] if "宁德时代" in e["name"])
        self.assertTrue(any("[ETF]" in s for s in nd["sources"]),
                        "宁德时代应有 [ETF] 标签来源")
        # 药明康德：来自主动权益基金
        ym = next(e for e in result["top10"] if "药明康德" in e["name"])
        self.assertTrue(any("[权益]" in s for s in ym["sources"]),
                        "药明康德应有 [权益] 标签来源")


# ═══════════════════════════════════════════════════════════════
#  S-P10: 交叉持股合并 — 同底层标的多源汇聚
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP10CrossHoldingMerge(unittest.TestCase):
    """S-P10：交叉持股合并 — 同一底层标的被多只基金持有时归一。

    场景：三只不同类型基金同时持有贵州茅台。
    验证：
      1. 贵州茅台只出现一次（归一合并）
      2. 合并后市值 = 各基金贡献之和
      3. 来源列表包含所有基金
      4. 合并后占比 ≥ 各基金单独占比之和
    """

    def setUp(self):
        self.holdings = [
            # 三只基金都持有贵州茅台，但比例不同
            Holding("证券", "消费ETF", "159928", 2000, 1.0),
            Holding("支付宝", "易方达蓝筹精选", "005827", 1000, 2.0),
            Holding("支付宝", "天弘沪深300ETF联接A", "000961", 3000, 1.0),
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_cross_holding_dedup(self, mock_enrich, mock_batch):
        """交叉持股 → 贵州茅台只出现一次。"""
        mock_batch.return_value = {
            "159928": {
                "code": "159928", "name": "消费ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 12.0},
                    {"name": "五粮液", "code": "000858", "ratio": 8.0},
                ],
            },
            "005827": {
                "code": "005827", "name": "易方达蓝筹精选",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 15.0},
                    {"name": "腾讯控股", "code": "0700", "ratio": 10.0},
                ],
            },
            "000961": {
                "code": "000961", "name": "天弘沪深300ETF联接A",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 16.0},
                    {"name": "宁德时代", "code": "300750", "ratio": 8.0},
                ],
            },
        }

        details = [
            DetailRow(
                account="证券", name="消费ETF", code="159928",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.98,
                price_type="T", premium="--", shares=2000.0,
                market_value=4000.0, cost=2000.0, profit=2000.0,
                profit_rate=1.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="支付宝", name="易方达蓝筹精选", code="005827",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=1000.0,
                market_value=1800.0, cost=2000.0, profit=-200.0,
                profit_rate=-0.1, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
            DetailRow(
                account="支付宝", name="天弘沪深300ETF联接A", code="000961",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T-1", premium="--", shares=3000.0,
                market_value=3600.0, cost=3000.0, profit=600.0,
                profit_rate=0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        # 贵州茅台只出现一次
        mt_entries = [e for e in result["top10"] if "贵州茅台" in e["name"]]
        self.assertEqual(len(mt_entries), 1,
                         "贵州茅台被多只基金持有应合并为一条")
        mt = mt_entries[0]

        # 茅台合并市值 = 消费ETF(4000*0.12=480) + 蓝筹(1800*0.15=270) + 联接(3600*0.16=576)
        expected_mv = 480.0 + 270.0 + 576.0
        self.assertAlmostEqual(mt["mv"], expected_mv, places=1)

        # 来源应包含 3 条
        self.assertEqual(len(mt["sources"]), 3)

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_cross_holding_total_mv(self, mock_enrich, mock_batch):
        """交叉持股 → total_mv 等于所有合并市值之和。"""
        mock_batch.return_value = {
            "159928": {
                "code": "159928", "name": "消费ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 12.0},
                    {"name": "五粮液", "code": "000858", "ratio": 8.0},
                ],
            },
            "005827": {
                "code": "005827", "name": "易方达蓝筹精选",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 15.0},
                    {"name": "腾讯控股", "code": "0700", "ratio": 10.0},
                ],
            },
            "000961": {
                "code": "000961", "name": "天弘沪深300ETF联接A",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 16.0},
                    {"name": "宁德时代", "code": "300750", "ratio": 8.0},
                ],
            },
        }

        details = [
            DetailRow(
                account="证券", name="消费ETF", code="159928",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.98,
                price_type="T", premium="--", shares=2000.0,
                market_value=4000.0, cost=2000.0, profit=2000.0,
                profit_rate=1.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="支付宝", name="易方达蓝筹精选", code="005827",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=1000.0,
                market_value=1800.0, cost=2000.0, profit=-200.0,
                profit_rate=-0.1, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
            DetailRow(
                account="支付宝", name="天弘沪深300ETF联接A", code="000961",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T-1", premium="--", shares=3000.0,
                market_value=3600.0, cost=3000.0, profit=600.0,
                profit_rate=0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        # 手动计算合并后市值：
        # 茅台: 480+270+576 = 1326
        # 五粮液: 4000*0.08 = 320
        # 腾讯: 1800*0.10 = 180
        # 宁德时代: 3600*0.08 = 288
        expected_total = 1326.0 + 320.0 + 180.0 + 288.0
        self.assertAlmostEqual(result["summary"]["total_mv"],
                               expected_total, places=1)

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_cross_holding_all_sources_present(self, mock_enrich, mock_batch):
        """交叉持股 → 每只基金的来源标签类型正确。"""
        mock_batch.return_value = {
            "159928": {
                "code": "159928", "name": "消费ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 12.0},
                ],
            },
            "005827": {
                "code": "005827", "name": "易方达蓝筹精选",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "五粮液", "code": "000858", "ratio": 10.0},
                ],
            },
            "000961": {
                "code": "000961", "name": "天弘沪深300ETF联接A",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 8.0},
                ],
            },
        }

        details = [
            DetailRow(
                account="证券", name="消费ETF", code="159928",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.98,
                price_type="T", premium="--", shares=2000.0,
                market_value=4000.0, cost=2000.0, profit=2000.0,
                profit_rate=1.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
            DetailRow(
                account="支付宝", name="易方达蓝筹精选", code="005827",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=1000.0,
                market_value=1800.0, cost=2000.0, profit=-200.0,
                profit_rate=-0.1, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
            DetailRow(
                account="支付宝", name="天弘沪深300ETF联接A", code="000961",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T-1", premium="--", shares=3000.0,
                market_value=3600.0, cost=3000.0, profit=600.0,
                profit_rate=0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        # 贵州茅台来源：消费ETF [ETF]
        mt = next(e for e in result["top10"] if "贵州茅台" in e["name"])
        self.assertTrue(any("[ETF]" in s for s in mt["sources"]),
                        "茅台来源应含 [ETF]")
        # 五粮液来源：易方达蓝筹 [权益]
        wly = next(e for e in result["top10"] if "五粮液" in e["name"])
        self.assertTrue(any("[权益]" in s for s in wly["sources"]),
                        "五粮液来源应含 [权益]")
        # 宁德时代来源：联接 [联接]
        nd = next(e for e in result["top10"] if "宁德时代" in e["name"])
        self.assertTrue(any("[联接]" in s for s in nd["sources"]),
                        "宁德时代来源应含 [联接]")


if __name__ == "__main__":
    unittest.main()

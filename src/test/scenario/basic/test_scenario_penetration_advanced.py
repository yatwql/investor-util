"""穿透 TOP10 高级场景验证（S-P5, S-P7, S-P8）。

覆盖资产类型：
  S-P5: QDII 基金穿透 — 美股持仓穿透与板块映射
  S-P7: 基于国外指数的 QDII 基金 — QDII 指数基金穿透
  S-P8: 国内指数联接基金 — 联接基金穿透验证

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_penetration_advanced.py -v
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
#  S-P5: QDII 基金穿透 — 美股持仓
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP5QDII(unittest.TestCase):
    """S-P5：QDII 基金穿透 — 美股持仓穿透与板块映射。

    场景：持有纳指 QDII 基金，穿透为美股科技股。
    验证：
      1. 分类为 QDII
      2. 来源标签含"[QDII]"
      3. 美股板块映射正确（科技）
      4. fund_breakdown 含 "QDII"
    """

    def setUp(self):
        self.holdings = [
            Holding("证券", "华夏纳斯达克100ETF(QDII)", "513300", 1000, 1.5),
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_qdii_source_tag(self, mock_enrich, mock_batch):
        """QDII → 来源包含"[QDII]"标签。"""
        mock_batch.return_value = {
            "513300": {
                "code": "513300", "name": "华夏纳斯达克100ETF(QDII)",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "苹果", "code": "AAPL", "ratio": 12.0},
                    {"name": "微软", "code": "MSFT", "ratio": 10.0},
                    {"name": "英伟达", "code": "NVDA", "ratio": 8.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="证券", name="华夏纳斯达克100ETF(QDII)", code="513300",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T", premium="0.5%", shares=1000.0,
                market_value=1200.0, cost=1500.0, profit=-300.0,
                profit_rate=-0.2, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            tag_found = any("[QDII]" in s for s in entry["sources"])
            self.assertTrue(tag_found, f"{entry['name']} 来源缺少 [QDII] 标签")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_qdii_sector_tech(self, mock_enrich, mock_batch):
        """QDII → 美股板块映射为"科技"。"""
        mock_batch.return_value = {
            "513300": {
                "code": "513300", "name": "华夏纳斯达克100ETF(QDII)",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "苹果", "code": "AAPL", "ratio": 12.0},
                    {"name": "微软", "code": "MSFT", "ratio": 10.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="证券", name="华夏纳斯达克100ETF(QDII)", code="513300",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T", premium="0.5%", shares=1000.0,
                market_value=1200.0, cost=1500.0, profit=-300.0,
                profit_rate=-0.2, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            self.assertEqual(entry["sector"], "科技",
                             f"{entry['name']} 板块应映射为科技")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_qdii_breakdown(self, mock_enrich, mock_batch):
        """QDII → fund_breakdown 含"QDII"。"""
        mock_batch.return_value = {
            "513300": {
                "code": "513300", "name": "华夏纳斯达克100ETF(QDII)",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "苹果", "code": "AAPL", "ratio": 12.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="证券", name="华夏纳斯达克100ETF(QDII)", code="513300",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T", premium="0.5%", shares=1000.0,
                market_value=1200.0, cost=1500.0, profit=-300.0,
                profit_rate=-0.2, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        self.assertIn("QDII", result["summary"]["fund_breakdown"])

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_qdii_mv_calculation(self, mock_enrich, mock_batch):
        """QDII → 穿透市值 = 基金市值 × 比例。"""
        mock_batch.return_value = {
            "513300": {
                "code": "513300", "name": "华夏纳斯达克100ETF(QDII)",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "苹果", "code": "AAPL", "ratio": 12.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="证券", name="华夏纳斯达克100ETF(QDII)", code="513300",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T", premium="0.5%", shares=1000.0,
                market_value=1200.0, cost=1500.0, profit=-300.0,
                profit_rate=-0.2, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        apple = next(e for e in result["top10"] if e["name"] == "苹果")
        self.assertAlmostEqual(apple["mv"], 144.0, places=1)


# ═══════════════════════════════════════════════════════════════
#  S-P7: 基于国外指数的 QDII 基金
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP7QDIIIndexFund(unittest.TestCase):
    """S-P7：基于国外指数的 QDII 基金穿透。

    场景：场外 QDII 指数基金（如标普500 QDII），穿透为美股成分股。
    验证：
      1. 分类为 QDII（名称含 QDII 关键词）
      2. 来源标签含"[QDII]"
      3. 穿透结果含市场指数相关成分股
    """

    def setUp(self):
        self.holdings = [
            Holding("支付宝", "易方达标普500指数(QDII)", "161125", 2000, 1.0),
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_qdii_index_source_tag(self, mock_enrich, mock_batch):
        """QDII 指数基金 → 来源含"[QDII]"，fund_breakdown 含"QDII"。"""
        mock_batch.return_value = {
            "161125": {
                "code": "161125", "name": "易方达标普500指数(QDII)",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "苹果", "code": "AAPL", "ratio": 7.5},
                    {"name": "微软", "code": "MSFT", "ratio": 6.8},
                    {"name": "英伟达", "code": "NVDA", "ratio": 5.2},
                    {"name": "亚马逊", "code": "AMZN", "ratio": 4.0},
                    {"name": "谷歌", "code": "GOOGL", "ratio": 3.5},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="易方达标普500指数(QDII)", code="161125",
                price=1.5, nav_date="2026-07-03", yesterday_close=1.48,
                price_type="T-1", premium="--", shares=2000.0,
                market_value=3000.0, cost=2000.0, profit=1000.0,
                profit_rate=0.5, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            tag_found = any("[QDII]" in s for s in entry["sources"])
            self.assertTrue(tag_found, f"{entry['name']} 来源缺少 [QDII] 标签")
        self.assertIn("QDII", result["summary"]["fund_breakdown"])

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_qdii_index_sorted_by_mv(self, mock_enrich, mock_batch):
        """QDII 指数基金 → TOP10 按市值降序排列。"""
        mock_batch.return_value = {
            "161125": {
                "code": "161125", "name": "易方达标普500指数(QDII)",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "苹果", "code": "AAPL", "ratio": 7.5},
                    {"name": "微软", "code": "MSFT", "ratio": 6.8},
                    {"name": "英伟达", "code": "NVDA", "ratio": 5.2},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="易方达标普500指数(QDII)", code="161125",
                price=1.5, nav_date="2026-07-03", yesterday_close=1.48,
                price_type="T-1", premium="--", shares=2000.0,
                market_value=3000.0, cost=2000.0, profit=1000.0,
                profit_rate=0.5, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        mvs = [e["mv"] for e in result["top10"]]
        for i in range(1, len(mvs)):
            self.assertGreaterEqual(mvs[i - 1], mvs[i])

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_qdii_index_5_stocks(self, mock_enrich, mock_batch):
        """QDII 指数基金 → 5 只成分股全部进入 TOP10。"""
        mock_batch.return_value = {
            "161125": {
                "code": "161125", "name": "易方达标普500指数(QDII)",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "苹果", "code": "AAPL", "ratio": 7.5},
                    {"name": "微软", "code": "MSFT", "ratio": 6.8},
                    {"name": "英伟达", "code": "NVDA", "ratio": 5.2},
                    {"name": "亚马逊", "code": "AMZN", "ratio": 4.0},
                    {"name": "谷歌", "code": "GOOGL", "ratio": 3.5},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="易方达标普500指数(QDII)", code="161125",
                price=1.5, nav_date="2026-07-03", yesterday_close=1.48,
                price_type="T-1", premium="--", shares=2000.0,
                market_value=3000.0, cost=2000.0, profit=1000.0,
                profit_rate=0.5, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        self.assertEqual(len(result["top10"]), 5)
        expected = {"苹果", "微软", "英伟达", "亚马逊", "谷歌"}
        actual = {e["name"] for e in result["top10"]}
        self.assertEqual(actual, expected)


# ═══════════════════════════════════════════════════════════════
#  S-P8: 国内指数联接基金
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP8IndexLink(unittest.TestCase):
    """S-P8：国内指数联接基金穿透。

    场景：持有沪深300 ETF 联接基金，穿透为指数前 10 大成分股。
    验证：
      1. 分类为 INDEX_LINK
      2. 来源标签含"[联接]"
      3. fund_breakdown 含"联接"
      4. 穿透市值计算正确
    """

    def setUp(self):
        self.holdings = [
            Holding("支付宝", "天弘沪深300ETF联接A", "000961", 5000, 1.0),
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_index_link_source_tag(self, mock_enrich, mock_batch):
        """联接基金 → 来源包含"[联接]"标签。"""
        mock_batch.return_value = {
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
                account="支付宝", name="天弘沪深300ETF联接A", code="000961",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T-1", premium="--", shares=5000.0,
                market_value=6000.0, cost=5000.0, profit=1000.0,
                profit_rate=0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            tag_found = any("[联接]" in s for s in entry["sources"])
            self.assertTrue(tag_found, f"{entry['name']} 来源缺少 [联接] 标签")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_index_link_breakdown(self, mock_enrich, mock_batch):
        """联接基金 → fund_breakdown 含"联接"、merged_count 正确。"""
        mock_batch.return_value = {
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
                account="支付宝", name="天弘沪深300ETF联接A", code="000961",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T-1", premium="--", shares=5000.0,
                market_value=6000.0, cost=5000.0, profit=1000.0,
                profit_rate=0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        self.assertIn("联接", result["summary"]["fund_breakdown"])
        self.assertEqual(result["summary"]["merged_count"], 2)

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_index_link_many_constituents(self, mock_enrich, mock_batch):
        """联接基金 → 超过 10 只成分股时只取 TOP10。"""
        mock_batch.return_value = {
            "000961": {
                "code": "000961", "name": "天弘沪深300ETF联接A",
                "date": "2026-03-31",
                "holdings": [
                    {"name": f"股票{i:02d}", "code": f"600{i:04d}", "ratio": 3.0}
                    for i in range(1, 16)
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="天弘沪深300ETF联接A", code="000961",
                price=1.2, nav_date="2026-07-03", yesterday_close=1.18,
                price_type="T-1", premium="--", shares=5000.0,
                market_value=6000.0, cost=5000.0, profit=1000.0,
                profit_rate=0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        # 15 只成分股全部等比例 → merged_count = 15
        self.assertEqual(result["summary"]["merged_count"], 15)
        # TOP10 只取前 10
        self.assertEqual(len(result["top10"]), 10)


if __name__ == "__main__":
    unittest.main()

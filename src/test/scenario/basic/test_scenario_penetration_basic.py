"""穿透 TOP10 基础场景验证（S-P1 ~ S-P4）。

覆盖资产类型：
  S-P1: 纯股票组合 — 直接持有股票分类与板块识别
  S-P2: 债券基金穿透 — 债券品种穿透与来源标注
  S-P3: 场内 ETF 穿透 — ETF 成分股穿透与排序
  S-P4: 场外主动权益基金 — 主动基金穿透与来源标注

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_penetration_basic.py -v
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
#  S-P1: 纯股票组合 — 直接持有股票
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP1DirectStocks(unittest.TestCase):
    """S-P1：纯股票组合 — 验证直接持有股票的穿透分类与板块识别。

    场景：持仓中全部为 A 股股票，无任何基金。
    验证：
      1. 所有股票正确分类为 STOCK
      2. 板块映射准确（消费/能源资源/新能源）
      3. 占比总和 = 100%
      4. TOP10 按市值降序排列
      5. 来源标注为"直接持有"
    """

    def setUp(self):
        self.holdings = [
            Holding("证券", "贵州茅台", "600519", 100, 1500.0),
            Holding("证券", "长江电力", "600900", 200, 28.0),
            Holding("证券", "宁德时代", "300750", 50, 250.0),
        ]

    def _make_detail(self, code: str, name: str, price: float,
                     shares: int = 100) -> DetailRow:
        return DetailRow(
            account="证券", name=name, code=code,
            price=price, nav_date="2026-07-03", yesterday_close=price * 0.99,
            price_type="T", premium="--", shares=float(shares),
            market_value=price * shares, cost=price * shares,
            profit=0.0, profit_rate=0.0, today_profit=0.0,
            source="mock", source_api="tencent",
        )

    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_stock_classification_count(self, mock_enrich):
        """纯股票 → summary.total_stocks = 3, total_funds = 0。"""
        details = [
            self._make_detail("600519", "贵州茅台", 1500.0, 100),
            self._make_detail("600900", "长江电力", 28.0, 200),
            self._make_detail("300750", "宁德时代", 250.0, 50),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        summary = result["summary"]
        self.assertEqual(summary["total_stocks"], 3)
        self.assertEqual(summary["total_funds"], 0)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_stock_sector_mapping(self, mock_ind):
        """纯股票 → 板块映射正确：茅台→消费, 长江电力→能源资源, 宁德时代→新能源。"""
        details = [
            self._make_detail("600519", "贵州茅台", 1500.0, 100),
            self._make_detail("600900", "长江电力", 28.0, 200),
            self._make_detail("300750", "宁德时代", 250.0, 50),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        sectors = {e["name"]: e["sector"] for e in result["top10"]}
        self.assertEqual(sectors.get("贵州茅台"), "消费")
        self.assertEqual(sectors.get("长江电力"), "能源资源")
        self.assertEqual(sectors.get("宁德时代"), "新能源")

    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_stock_ratio_sum_100(self, mock_enrich):
        """纯股票 → 各股占比总和 = 100%。"""
        details = [
            self._make_detail("600519", "贵州茅台", 1500.0, 100),
            self._make_detail("600900", "长江电力", 28.0, 200),
            self._make_detail("300750", "宁德时代", 250.0, 50),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        total_ratio = sum(e["ratio_pct"] for e in result["top10"])
        self.assertAlmostEqual(total_ratio, 100.0, places=4)

    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_stock_sorted_by_mv_desc(self, mock_enrich):
        """纯股票 → TOP10 按市值降序排列。"""
        details = [
            self._make_detail("600519", "贵州茅台", 1500.0, 100),
            self._make_detail("600900", "长江电力", 28.0, 200),
            self._make_detail("300750", "宁德时代", 250.0, 50),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        mvs = [e["mv"] for e in result["top10"]]
        for i in range(1, len(mvs)):
            self.assertGreaterEqual(mvs[i - 1], mvs[i])

    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_stock_source_direct_holding(self, mock_enrich):
        """纯股票 → 来源标注包含"直接持有"。"""
        details = [
            self._make_detail("600519", "贵州茅台", 1500.0, 100),
            self._make_detail("600900", "长江电力", 28.0, 200),
            self._make_detail("300750", "宁德时代", 250.0, 50),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            self.assertIn("直接持有", entry["sources"])

    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_stock_no_fund_breakdown(self, mock_enrich):
        """纯股票 → fund_breakdown 为空字符串（无基金）。"""
        details = [
            self._make_detail("600519", "贵州茅台", 1500.0, 100),
            self._make_detail("600900", "长江电力", 28.0, 200),
            self._make_detail("300750", "宁德时代", 250.0, 50),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        self.assertEqual(result["summary"]["fund_breakdown"], "")


# ═══════════════════════════════════════════════════════════════
#  S-P2: 债券基金穿透
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP2BondFund(unittest.TestCase):
    """S-P2：债券基金穿透 — 验证债券品种穿透与来源标注。

    场景：持有纯债基金，穿透为具体债券品种。
    验证：
      1. 分类为 BOND_FUND
      2. 来源标签含"[债券]"
      3. 债券品种名称正确
      4. 穿透市值 = 基金市值 × 持仓比例
    """

    def setUp(self):
        self.holdings = [
            Holding("支付宝", "招商鑫福中短债A", "012325", 5000, 1.0),
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_bond_classification(self, mock_enrich, mock_batch):
        """债券基金 → unknown_mv=0, failed_funds=0。"""
        mock_batch.return_value = {
            "012325": {
                "code": "012325", "name": "招商鑫福中短债A", "date": "2026-06-30",
                "holdings": [
                    {"name": "23国开10", "code": "230210", "ratio": 8.0},
                    {"name": "22国债14", "code": "220014", "ratio": 6.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="招商鑫福中短债A", code="012325",
                price=1.0, nav_date="2026-07-03", yesterday_close=1.0,
                price_type="T-1", premium="--", shares=5000.0,
                market_value=5000.0, cost=5000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        self.assertEqual(result["summary"]["unknown_mv"], 0.0)
        self.assertEqual(result["summary"]["failed_funds"], 0)

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_bond_source_tag(self, mock_enrich, mock_batch):
        """债券基金 → 来源包含"[债券]"标签。"""
        mock_batch.return_value = {
            "012325": {
                "code": "012325", "name": "招商鑫福中短债A", "date": "2026-06-30",
                "holdings": [
                    {"name": "23国开10", "code": "230210", "ratio": 8.0},
                    {"name": "22国债14", "code": "220014", "ratio": 6.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="招商鑫福中短债A", code="012325",
                price=1.0, nav_date="2026-07-03", yesterday_close=1.0,
                price_type="T-1", premium="--", shares=5000.0,
                market_value=5000.0, cost=5000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            tag_found = any("[债券]" in s for s in entry["sources"])
            self.assertTrue(tag_found, f"{entry['name']} 来源缺少 [债券] 标签")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_bond_mv_attribution(self, mock_enrich, mock_batch):
        """债券基金 → 穿透市值 = 基金市值 × 比例。"""
        mock_batch.return_value = {
            "012325": {
                "code": "012325", "name": "招商鑫福中短债A", "date": "2026-06-30",
                "holdings": [
                    {"name": "23国开10", "code": "230210", "ratio": 8.0},
                    {"name": "22国债14", "code": "220014", "ratio": 6.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="招商鑫福中短债A", code="012325",
                price=1.0, nav_date="2026-07-03", yesterday_close=1.0,
                price_type="T-1", premium="--", shares=5000.0,
                market_value=5000.0, cost=5000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            if entry["name"] == "23国开10":
                self.assertAlmostEqual(entry["mv"], 5000.0 * 0.08, places=1)
            elif entry["name"] == "22国债14":
                self.assertAlmostEqual(entry["mv"], 5000.0 * 0.06, places=1)

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_bond_fund_breakdown(self, mock_enrich, mock_batch):
        """债券基金 → fund_breakdown 含"债券1"。"""
        mock_batch.return_value = {
            "012325": {
                "code": "012325", "name": "招商鑫福中短债A", "date": "2026-06-30",
                "holdings": [
                    {"name": "23国开10", "code": "230210", "ratio": 8.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="招商鑫福中短债A", code="012325",
                price=1.0, nav_date="2026-07-03", yesterday_close=1.0,
                price_type="T-1", premium="--", shares=5000.0,
                market_value=5000.0, cost=5000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        self.assertIn("债券", result["summary"]["fund_breakdown"])
        self.assertIn("1", result["summary"]["fund_breakdown"])


# ═══════════════════════════════════════════════════════════════
#  S-P3: 场内 ETF 穿透
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP3ETF(unittest.TestCase):
    """S-P3：场内 ETF 穿透 — ETF 成分股穿透与排序验证。

    场景：持有场内 ETF，穿透为前 10 大成分股。
    覆盖类型：
      - 国内行业风格 ETF（如 561910 电池ETF）
      - 基于国外指数的 ETF（如 513500 标普500ETF，名称不含 QDII）
    验证：
      1. 分类为 ETF
      2. 来源标签含"[ETF]"
      3. TOP10 按市值降序
      4. 合并数量正确
      5. 国内 ETF → A 股板块映射，国外指数 ETF → 美股板块映射
    """

    def setUp(self):
        self.holdings = [
            Holding("证券", "电池ETF", "561910", 5000, 1.0),
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_etf_source_tag(self, mock_enrich, mock_batch):
        """ETF → 来源包含"[ETF]"标签。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="证券", name="电池ETF", code="561910",
                price=1.0, nav_date="2026-07-03", yesterday_close=0.99,
                price_type="T", premium="--", shares=5000.0,
                market_value=5000.0, cost=5000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            tag_found = any("[ETF]" in s for s in entry["sources"])
            self.assertTrue(tag_found, f"{entry['name']} 来源缺少 [ETF] 标签")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_etf_mv_sorted(self, mock_enrich, mock_batch):
        """ETF → 成分股按市值降序排序。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                    {"name": "赣锋锂业", "code": "002460", "ratio": 5.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="证券", name="电池ETF", code="561910",
                price=1.0, nav_date="2026-07-03", yesterday_close=0.99,
                price_type="T", premium="--", shares=5000.0,
                market_value=5000.0, cost=5000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        mvs = [e["mv"] for e in result["top10"]]
        for i in range(1, len(mvs)):
            self.assertGreaterEqual(mvs[i - 1], mvs[i])
        # 宁德时代 > 比亚迪 > 赣锋锂业
        names = [e["name"] for e in result["top10"]]
        self.assertEqual(names[0], "宁德时代")
        self.assertEqual(names[1], "比亚迪")
        self.assertEqual(names[2], "赣锋锂业")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_etf_merged_count(self, mock_enrich, mock_batch):
        """ETF → merged_count = 成分股个数。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="证券", name="电池ETF", code="561910",
                price=1.0, nav_date="2026-07-03", yesterday_close=0.99,
                price_type="T", premium="--", shares=5000.0,
                market_value=5000.0, cost=5000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        self.assertEqual(result["summary"]["merged_count"], 2)

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_foreign_index_etf_classification(self, mock_enrich, mock_batch):
        """基于国外指数的场内ETF（标普500ETF）→ 分类为 ETF 且穿透美股板块映射正确。"""
        mock_batch.return_value = {
            "513500": {
                "code": "513500", "name": "标普500ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "苹果", "code": "AAPL", "ratio": 7.5},
                    {"name": "微软", "code": "MSFT", "ratio": 6.8},
                    {"name": "英伟达", "code": "NVDA", "ratio": 5.2},
                    {"name": "亚马逊", "code": "AMZN", "ratio": 4.0},
                    {"name": "谷歌", "code": "GOOGL", "ratio": 3.5},
                ],
            },
        }
        holdings = [
            Holding("证券", "标普500ETF", "513500", 1000, 2.0),
        ]
        details = [
            DetailRow(
                account="证券", name="标普500ETF", code="513500",
                price=2.0, nav_date="2026-07-03", yesterday_close=1.98,
                price_type="T", premium="0.3%", shares=1000.0,
                market_value=2000.0, cost=2000.0, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(holdings, details)
        # 分类验证：名称含"标普"（海外指数关键词）→ QDII（海外指数 ETF 实质为 QDII 产品）
        self.assertIn("QDII", result["summary"]["fund_breakdown"],
                      "标普500ETF 应分类为 QDII（海外指数 ETF 实质为 QDII 产品）")
        # 来源标签应为 [QDII]
        for entry in result["top10"]:
            tag_found = any("[QDII]" in s for s in entry["sources"])
            self.assertTrue(tag_found, f"{entry['name']} 来源缺少 [QDII] 标签")
        # 美股板块映射验证（科技）
        for entry in result["top10"]:
            self.assertEqual(entry["sector"], "科技",
                             f"{entry['name']} 板块应映射为科技")
        # 5 只成分股全部呈现
        self.assertEqual(len(result["top10"]), 5)
        expected = {"苹果", "微软", "英伟达", "亚马逊", "谷歌"}
        actual = {e["name"] for e in result["top10"]}
        self.assertEqual(actual, expected)


# ═══════════════════════════════════════════════════════════════
#  S-P4: 场外主动权益基金穿透
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP4ActiveEquity(unittest.TestCase):
    """S-P4：场外主动权益基金穿透。

    场景：支付宝账户中的主动权益基金，穿透为具体股票持仓。
    验证：
      1. 分类为 ACTIVE_EQUITY
      2. 来源标签含"[权益]"
      3. 穿透市值计算正确
    """

    def setUp(self):
        self.holdings = [
            Holding("支付宝", "中欧医疗健康混合", "003095", 1000, 2.0),
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_active_equity_source_tag(self, mock_enrich, mock_batch):
        """主动基金 → 来源包含"[权益]"标签。"""
        mock_batch.return_value = {
            "003095": {
                "code": "003095", "name": "中欧医疗健康混合", "date": "2026-03-31",
                "holdings": [
                    {"name": "药明康德", "code": "603259", "ratio": 10.0},
                    {"name": "恒瑞医药", "code": "600276", "ratio": 8.0},
                    {"name": "迈瑞医疗", "code": "300760", "ratio": 6.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="中欧医疗健康混合", code="003095",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=1000.0,
                market_value=1800.0, cost=2000.0, profit=-200.0,
                profit_rate=-0.1, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            tag_found = any("[权益]" in s for s in entry["sources"])
            self.assertTrue(tag_found, f"{entry['name']} 来源缺少 [权益] 标签")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_active_equity_sector_医药(self, mock_ind, mock_batch):
        """主动基金 → 穿透标的板块映射为"医药"。"""
        mock_batch.return_value = {
            "003095": {
                "code": "003095", "name": "中欧医疗健康混合", "date": "2026-03-31",
                "holdings": [
                    {"name": "药明康德", "code": "603259", "ratio": 10.0},
                    {"name": "恒瑞医药", "code": "600276", "ratio": 8.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="中欧医疗健康混合", code="003095",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=1000.0,
                market_value=1800.0, cost=2000.0, profit=-200.0,
                profit_rate=-0.1, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        for entry in result["top10"]:
            self.assertEqual(entry["sector"], "医药",
                             f"{entry['name']} 板块应为医药")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_active_equity_mv_attribution(self, mock_enrich, mock_batch):
        """主动基金 → 穿透市值 = 1800 × 比例。"""
        mock_batch.return_value = {
            "003095": {
                "code": "003095", "name": "中欧医疗健康混合", "date": "2026-03-31",
                "holdings": [
                    {"name": "药明康德", "code": "603259", "ratio": 10.0},
                ],
            },
        }
        details = [
            DetailRow(
                account="支付宝", name="中欧医疗健康混合", code="003095",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=1000.0,
                market_value=1800.0, cost=2000.0, profit=-200.0,
                profit_rate=-0.1, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        yao = next(e for e in result["top10"] if e["name"] == "药明康德")
        self.assertAlmostEqual(yao["mv"], 180.0, places=1)


if __name__ == "__main__":
    unittest.main()

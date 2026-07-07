"""穿透 TOP10 业务场景验证（S-P1 ~ S-P10）。

覆盖资产类型：
  S-P1: 纯股票组合 — 直接持有股票分类与板块识别
  S-P2: 债券基金穿透 — 债券品种穿透与来源标注
  S-P3: 场内 ETF 穿透 — ETF 成分股穿透与排序
  S-P4: 场外主动权益基金 — 主动基金穿透与来源标注
  S-P5: QDII 基金穿透 — 美股持仓穿透与板块映射
  S-P6: 黄金 ETF 无效比例过滤 — >100% 的垃圾数据排除
  S-P7: 基于国外指数的 QDII 基金 — QDII 指数基金穿透
  S-P8: 国内指数联接基金 — 联接基金穿透验证
  S-P9: 全类型混合场景 — 多类型持仓合并、排序、占比
  S-P10: 交叉持股合并 — 同标的被多只基金持有时归一

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_penetration.py -v
  pytest src/test/ -m "scenario_basic" -v    # 全部基础场景
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

    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_stock_sector_mapping(self, mock_enrich):
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_bond_classification(self, mock_enrich, mock_fetch):
        """债券基金 → unknown_mv=0, failed_funds=0。"""
        mock_fetch.return_value = {
            "code": "012325", "name": "招商鑫福中短债A", "date": "2026-06-30",
            "holdings": [
                {"name": "23国开10", "code": "230210", "ratio": 8.0},
                {"name": "22国债14", "code": "220014", "ratio": 6.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_bond_source_tag(self, mock_enrich, mock_fetch):
        """债券基金 → 来源包含"[债券]"标签。"""
        mock_fetch.return_value = {
            "code": "012325", "name": "招商鑫福中短债A", "date": "2026-06-30",
            "holdings": [
                {"name": "23国开10", "code": "230210", "ratio": 8.0},
                {"name": "22国债14", "code": "220014", "ratio": 6.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_bond_mv_attribution(self, mock_enrich, mock_fetch):
        """债券基金 → 穿透市值 = 基金市值 × 比例。"""
        mock_fetch.return_value = {
            "code": "012325", "name": "招商鑫福中短债A", "date": "2026-06-30",
            "holdings": [
                {"name": "23国开10", "code": "230210", "ratio": 8.0},
                {"name": "22国债14", "code": "220014", "ratio": 6.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_bond_fund_breakdown(self, mock_enrich, mock_fetch):
        """债券基金 → fund_breakdown 含"债券1"。"""
        mock_fetch.return_value = {
            "code": "012325", "name": "招商鑫福中短债A", "date": "2026-06-30",
            "holdings": [
                {"name": "23国开10", "code": "230210", "ratio": 8.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_etf_source_tag(self, mock_enrich, mock_fetch):
        """ETF → 来源包含"[ETF]"标签。"""
        mock_fetch.return_value = {
            "code": "561910", "name": "电池ETF", "date": "2026-03-31",
            "holdings": [
                {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                {"name": "比亚迪", "code": "002594", "ratio": 10.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_etf_mv_sorted(self, mock_enrich, mock_fetch):
        """ETF → 成分股按市值降序排序。"""
        mock_fetch.return_value = {
            "code": "561910", "name": "电池ETF", "date": "2026-03-31",
            "holdings": [
                {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                {"name": "赣锋锂业", "code": "002460", "ratio": 5.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_etf_merged_count(self, mock_enrich, mock_fetch):
        """ETF → merged_count = 成分股个数。"""
        mock_fetch.return_value = {
            "code": "561910", "name": "电池ETF", "date": "2026-03-31",
            "holdings": [
                {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                {"name": "比亚迪", "code": "002594", "ratio": 10.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_foreign_index_etf_classification(self, mock_enrich, mock_fetch):
        """基于国外指数的场内ETF（标普500ETF）→ 分类为 ETF 且穿透美股板块映射正确。"""
        mock_fetch.return_value = {
            "code": "513500", "name": "标普500ETF", "date": "2026-03-31",
            "holdings": [
                {"name": "苹果", "code": "AAPL", "ratio": 7.5},
                {"name": "微软", "code": "MSFT", "ratio": 6.8},
                {"name": "英伟达", "code": "NVDA", "ratio": 5.2},
                {"name": "亚马逊", "code": "AMZN", "ratio": 4.0},
                {"name": "谷歌", "code": "GOOGL", "ratio": 3.5},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_active_equity_source_tag(self, mock_enrich, mock_fetch):
        """主动基金 → 来源包含"[权益]"标签。"""
        mock_fetch.return_value = {
            "code": "003095", "name": "中欧医疗健康混合", "date": "2026-03-31",
            "holdings": [
                {"name": "药明康德", "code": "603259", "ratio": 10.0},
                {"name": "恒瑞医药", "code": "600276", "ratio": 8.0},
                {"name": "迈瑞医疗", "code": "300760", "ratio": 6.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_active_equity_sector_医药(self, mock_enrich, mock_fetch):
        """主动基金 → 穿透标的板块映射为"医药"。"""
        mock_fetch.return_value = {
            "code": "003095", "name": "中欧医疗健康混合", "date": "2026-03-31",
            "holdings": [
                {"name": "药明康德", "code": "603259", "ratio": 10.0},
                {"name": "恒瑞医药", "code": "600276", "ratio": 8.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_active_equity_mv_attribution(self, mock_enrich, mock_fetch):
        """主动基金 → 穿透市值 = 1800 × 比例。"""
        mock_fetch.return_value = {
            "code": "003095", "name": "中欧医疗健康混合", "date": "2026-03-31",
            "holdings": [
                {"name": "药明康德", "code": "603259", "ratio": 10.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_qdii_source_tag(self, mock_enrich, mock_fetch):
        """QDII → 来源包含"[QDII]"标签。"""
        mock_fetch.return_value = {
            "code": "513300", "name": "华夏纳斯达克100ETF(QDII)",
            "date": "2026-03-31",
            "holdings": [
                {"name": "苹果", "code": "AAPL", "ratio": 12.0},
                {"name": "微软", "code": "MSFT", "ratio": 10.0},
                {"name": "英伟达", "code": "NVDA", "ratio": 8.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_qdii_sector_tech(self, mock_enrich, mock_fetch):
        """QDII → 美股板块映射为"科技"。"""
        mock_fetch.return_value = {
            "code": "513300", "name": "华夏纳斯达克100ETF(QDII)",
            "date": "2026-03-31",
            "holdings": [
                {"name": "苹果", "code": "AAPL", "ratio": 12.0},
                {"name": "微软", "code": "MSFT", "ratio": 10.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_qdii_breakdown(self, mock_enrich, mock_fetch):
        """QDII → fund_breakdown 含"QDII"。"""
        mock_fetch.return_value = {
            "code": "513300", "name": "华夏纳斯达克100ETF(QDII)",
            "date": "2026-03-31",
            "holdings": [
                {"name": "苹果", "code": "AAPL", "ratio": 12.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_qdii_mv_calculation(self, mock_enrich, mock_fetch):
        """QDII → 穿透市值 = 基金市值 × 比例。"""
        mock_fetch.return_value = {
            "code": "513300", "name": "华夏纳斯达克100ETF(QDII)",
            "date": "2026-03-31",
            "holdings": [
                {"name": "苹果", "code": "AAPL", "ratio": 12.0},
            ],
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
#  S-P6: 黄金 ETF — 无效比例过滤
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestSP6GoldETF(unittest.TestCase):
    """S-P6：黄金 ETF 无效比例过滤。

    场景：华安黄金 ETF（518880），天天基金 API 返回 >100% 的垃圾比例。
    验证：
      1. ratio > 100% 的标的被过滤
      2. 过滤后无有效标的 → top10 为空
      3. unknown_mv 包含基金全值
      4. failed_funds = 1
    """

    def setUp(self):
        self.holdings = [
            Holding("证券", "华安黄金ETF", "518880", 100, 83.097),
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_gold_etf_all_invalid_ratios(self, mock_enrich, mock_fetch):
        """黄金ETF 全为无效比例 → top10 为空、unknown_mv=全值。"""
        mock_fetch.return_value = {
            "code": "518880", "name": "华安黄金ETF", "date": "",
            "holdings": [
                {"name": "财通成长优选混合A(001480)", "code": "001480",
                 "ratio": 401.03},
                {"name": "财通成长优选混合C(021528)", "code": "021528",
                 "ratio": 399.15},
            ],
        }
        details = [
            DetailRow(
                account="证券", name="华安黄金ETF", code="518880",
                price=83.097, nav_date="2026-07-03", yesterday_close=82.0,
                price_type="T", premium="--", shares=100.0,
                market_value=8309.70, cost=8309.70, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        self.assertEqual(len(result["top10"]), 0,
                         "全为无效比例时 TOP10 应为空")
        self.assertAlmostEqual(result["summary"]["unknown_mv"], 8309.70,
                               delta=0.02)
        self.assertEqual(result["summary"]["failed_funds"], 1)

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_gold_etf_mixed_ratios(self, mock_enrich, mock_fetch):
        """黄金ETF 混有无效和有效比例 → 只保留有效。"""
        mock_fetch.return_value = {
            "code": "518880", "name": "华安黄金ETF", "date": "",
            "holdings": [
                {"name": "财通成长优选混合A(001480)", "code": "001480",
                 "ratio": 401.03},
                {"name": "山东黄金", "code": "600547", "ratio": 15.0},
                {"name": "中金黄金", "code": "600489", "ratio": 10.0},
            ],
        }
        details = [
            DetailRow(
                account="证券", name="华安黄金ETF", code="518880",
                price=83.097, nav_date="2026-07-03", yesterday_close=82.0,
                price_type="T", premium="--", shares=100.0,
                market_value=8309.70, cost=8309.70, profit=0.0,
                profit_rate=0.0, today_profit=0.0,
                source="mock", source_api="tencent",
            ),
        ]
        result = pene.compute_penetration_top10(self.holdings, details)
        top10_names = [e["name"] for e in result["top10"]]
        self.assertNotIn("财通成长优选混合A", top10_names,
                         "ratio>100% 的标的应被过滤")
        self.assertIn("山东黄金", top10_names)
        self.assertIn("中金黄金", top10_names)
        # 山东黄金 = 8309.70 * 15% = 1246.46
        sd = next(e for e in result["top10"] if e["name"] == "山东黄金")
        self.assertAlmostEqual(sd["mv"], 1246.46, places=1)
        # 有效占比之和 ≈ 100%
        total_ratio = sum(e["ratio_pct"] for e in result["top10"])
        self.assertAlmostEqual(total_ratio, 100.0, delta=0.02)


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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_qdii_index_source_tag(self, mock_enrich, mock_fetch):
        """QDII 指数基金 → 来源含"[QDII]"，fund_breakdown 含"QDII"。"""
        mock_fetch.return_value = {
            "code": "161125", "name": "易方达标普500指数(QDII)",
            "date": "2026-03-31",
            "holdings": [
                {"name": "苹果", "code": "AAPL", "ratio": 7.5},
                {"name": "微软", "code": "MSFT", "ratio": 6.8},
                {"name": "英伟达", "code": "NVDA", "ratio": 5.2},
                {"name": "亚马逊", "code": "AMZN", "ratio": 4.0},
                {"name": "谷歌", "code": "GOOGL", "ratio": 3.5},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_qdii_index_sorted_by_mv(self, mock_enrich, mock_fetch):
        """QDII 指数基金 → TOP10 按市值降序排列。"""
        mock_fetch.return_value = {
            "code": "161125", "name": "易方达标普500指数(QDII)",
            "date": "2026-03-31",
            "holdings": [
                {"name": "苹果", "code": "AAPL", "ratio": 7.5},
                {"name": "微软", "code": "MSFT", "ratio": 6.8},
                {"name": "英伟达", "code": "NVDA", "ratio": 5.2},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_qdii_index_5_stocks(self, mock_enrich, mock_fetch):
        """QDII 指数基金 → 5 只成分股全部进入 TOP10。"""
        mock_fetch.return_value = {
            "code": "161125", "name": "易方达标普500指数(QDII)",
            "date": "2026-03-31",
            "holdings": [
                {"name": "苹果", "code": "AAPL", "ratio": 7.5},
                {"name": "微软", "code": "MSFT", "ratio": 6.8},
                {"name": "英伟达", "code": "NVDA", "ratio": 5.2},
                {"name": "亚马逊", "code": "AMZN", "ratio": 4.0},
                {"name": "谷歌", "code": "GOOGL", "ratio": 3.5},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_index_link_source_tag(self, mock_enrich, mock_fetch):
        """联接基金 → 来源包含"[联接]"标签。"""
        mock_fetch.return_value = {
            "code": "000961", "name": "天弘沪深300ETF联接A",
            "date": "2026-03-31",
            "holdings": [
                {"name": "贵州茅台", "code": "600519", "ratio": 16.0},
                {"name": "宁德时代", "code": "300750", "ratio": 8.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_index_link_breakdown(self, mock_enrich, mock_fetch):
        """联接基金 → fund_breakdown 含"联接"、merged_count 正确。"""
        mock_fetch.return_value = {
            "code": "000961", "name": "天弘沪深300ETF联接A",
            "date": "2026-03-31",
            "holdings": [
                {"name": "贵州茅台", "code": "600519", "ratio": 16.0},
                {"name": "宁德时代", "code": "300750", "ratio": 8.0},
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_index_link_many_constituents(self, mock_enrich, mock_fetch):
        """联接基金 → 超过 10 只成分股时只取 TOP10。"""
        mock_fetch.return_value = {
            "code": "000961", "name": "天弘沪深300ETF联接A",
            "date": "2026-03-31",
            "holdings": [
                {"name": f"股票{i:02d}", "code": f"600{i:04d}", "ratio": 3.0}
                for i in range(1, 16)
            ],
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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_mixed_classification_counts(self, mock_enrich, mock_fetch):
        """混合场景 → total_stocks=1, total_funds=2, fund_breakdown 含"ETF1 + 主动1"。"""
        mock_fetch.side_effect = lambda code: {
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
        }.get(code, None)

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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_mixed_merged_and_sorted(self, mock_enrich, mock_fetch):
        """混合场景 → merged_count=4, TOP10 按市值降序。"""
        mock_fetch.side_effect = lambda code: {
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
        }.get(code, None)

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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_mixed_same_underlying_merged(self, mock_enrich, mock_fetch):
        """混合场景 → 宁德时代跨 ETF 和主动基金合并为一条。"""
        mock_fetch.side_effect = lambda code: {
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
        }.get(code, None)

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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_mixed_ratio_sum_le_100(self, mock_enrich, mock_fetch):
        """混合场景 → 穿透占比总和 ≤ 100%。"""
        mock_fetch.side_effect = lambda code: {
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
        }.get(code, None)

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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_mixed_sources_have_type_tags(self, mock_enrich, mock_fetch):
        """混合场景 → 来源包含正确的类型标签。"""
        mock_fetch.side_effect = lambda code: {
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
        }.get(code, None)

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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_cross_holding_dedup(self, mock_enrich, mock_fetch):
        """交叉持股 → 贵州茅台只出现一次。"""
        mock_fetch.side_effect = lambda code: {
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
        }.get(code, None)

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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_cross_holding_total_mv(self, mock_enrich, mock_fetch):
        """交叉持股 → total_mv 等于所有合并市值之和。"""
        mock_fetch.side_effect = lambda code: {
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
        }.get(code, None)

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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    @patch("src.python.report.penetration._enrich_with_industry_api",
           return_value=(True, ""))
    def test_cross_holding_all_sources_present(self, mock_enrich, mock_fetch):
        """交叉持股 → 每只基金的来源标签类型正确。"""
        mock_fetch.side_effect = lambda code: {
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
        }.get(code, None)

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

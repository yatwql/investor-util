"""穿透 TOP10 边缘场景验证（S-P6）。

覆盖资产类型：
  S-P6: 黄金 ETF 无效比例过滤 — >100% 的垃圾数据排除

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_penetration_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.core.models import Holding
from src.python.report.market_value import DetailRow
from src.python.report import penetration as pene

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic, pytest.mark.edge]


# ═══════════════════════════════════════════════════════════════
#  S-P6: 黄金 ETF — 无效比例过滤
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
@pytest.mark.edge
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

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_gold_etf_all_invalid_ratios(self, mock_enrich, mock_batch):
        """黄金ETF 全为无效比例 → top10 为空、unknown_mv=全值。"""
        mock_batch.return_value = {
            "518880": {
                "code": "518880", "name": "华安黄金ETF", "date": "",
                "holdings": [
                    {"name": "财通成长优选混合A(001480)", "code": "001480",
                     "ratio": 401.03},
                    {"name": "财通成长优选混合C(021528)", "code": "021528",
                     "ratio": 399.15},
                ],
            },
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

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    @patch("src.python.fetcher.industry.batch_fetch_industry_data",
           return_value={})
    def test_gold_etf_mixed_ratios(self, mock_enrich, mock_batch):
        """黄金ETF 混有无效和有效比例 → 只保留有效。"""
        mock_batch.return_value = {
            "518880": {
                "code": "518880", "name": "华安黄金ETF", "date": "",
                "holdings": [
                    {"name": "财通成长优选混合A(001480)", "code": "001480",
                     "ratio": 401.03},
                    {"name": "山东黄金", "code": "600547", "ratio": 15.0},
                    {"name": "中金黄金", "code": "600489", "ratio": 10.0},
                ],
            },
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


if __name__ == "__main__":
    unittest.main()

"""QDII 多时区净值日期一致性边缘测试 。

测试目标：
  - QDII 基金在不同时区场景下的净值日期判定
  - 美股 QDII（美东时区，T-2 典型延迟）vs 港股 QDII（北京时间，T-1 典型延迟）
  - 当前实现使用统一 T-2 延迟假设，需验证边界行为
  - price_update_status 对 QDII 的 T/T-1 认可逻辑

运行：
  pytest src/test/unit/report/test_qdii_timezone_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


class TestQdiiNavDateConsistency(unittest.TestCase):
    """多时区 QDII 净值日期一致性验证。"""

    def _make_us_qdii_detail(self, nav_date: str, trading_day: str) -> dict:
        """构造美股 QDII DetailRow（通过 market_value._compute_detail_row）。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0)
        mkt = {
            "price": 2.1, "yesterday_close": 2.0,
            "price_date": nav_date, "source": "天天基金",
            "source_api": "eastmoney",
            "nav_date": nav_date,
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value=trading_day):
            return _compute_detail_row(h, mkt)

    def _make_hk_qdii_detail(self, nav_date: str, trading_day: str) -> dict:
        """构造港股 QDII DetailRow。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券账户", "华宝港股通恒生中国(QDII)", "501023", 100, 1.5)
        mkt = {
            "price": 1.6, "yesterday_close": 1.55,
            "price_date": nav_date, "source": "天天基金",
            "source_api": "eastmoney",
            "nav_date": nav_date,
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value=trading_day):
            return _compute_detail_row(h, mkt)

    def test_us_qdii_nav_date_t1(self):
        """美股 QDII 净值日期 = T-1 → price_update_status 认可已更新。"""
        from src.python.report.market_value import price_update_status
        detail = self._make_us_qdii_detail(nav_date="2026-06-30",
                                            trading_day="2026-07-01")
        updated, total, all_updated = price_update_status([detail], "2026-07-01")
        self.assertEqual(updated, 1, "美股 QDII T-1 应视为已更新")
        self.assertTrue(all_updated)

    def test_us_qdii_nav_date_t2(self):
        """美股 QDII 净值日期 = T-2 → price_update_status 应标记为未更新。"""
        from src.python.report.market_value import price_update_status
        detail = self._make_us_qdii_detail(nav_date="2026-06-28",
                                            trading_day="2026-07-01")
        updated, total, all_updated = price_update_status([detail], "2026-07-01")
        self.assertEqual(updated, 0, "美股 QDII T-2 应视为未更新")

    def test_hk_qdii_nav_date_t1(self):
        """港股 QDII 净值日期 = T-1 → price_update_status 认可已更新。"""
        from src.python.report.market_value import price_update_status
        detail = self._make_hk_qdii_detail(nav_date="2026-06-30",
                                            trading_day="2026-07-01")
        updated, total, all_updated = price_update_status([detail], "2026-07-01")
        self.assertEqual(updated, 1, "港股 QDII T-1 应视为已更新")

    def test_qdii_today_profit_t(self):
        """QDII 净值日期 = T → today_profit > 0。"""
        detail = self._make_us_qdii_detail(nav_date="2026-07-01",
                                            trading_day="2026-07-01")
        self.assertGreater(detail.today_profit, 0)

    def test_qdii_today_profit_t1_is_zero(self):
        """QDII 净值日期 = T-1 → today_profit = 0（当前限制）。"""
        detail = self._make_us_qdii_detail(nav_date="2026-06-30",
                                            trading_day="2026-07-01")
        self.assertEqual(detail.today_profit, 0.0)

    def test_mixed_qdii_types_updated_status(self):
        """混合美股+港股 QDII → 各自正确判定更新状态。"""
        from src.python.report.market_value import price_update_status
        us_detail = self._make_us_qdii_detail(nav_date="2026-06-30",
                                               trading_day="2026-07-01")
        hk_detail = self._make_hk_qdii_detail(nav_date="2026-07-01",
                                               trading_day="2026-07-01")
        updated, total, all_updated = price_update_status([us_detail, hk_detail], "2026-07-01")
        self.assertEqual(updated, 2, "两个 QDII 都应视为已更新")
        self.assertEqual(total, 2)
        self.assertTrue(all_updated)

    @patch("src.python.report.market_value.get_last_trading_day",
           return_value="2026-07-01")
    def test_classify_holdings_qdii_detection(self, mock_td):
        """classify_holdings 正确识别各类型 QDII 名称变体。"""
        from src.python.report.market_value import classify_holdings

        holdings = [
            Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0),
            Holding("支付宝", "易方达中证海外联接人民币(QDII)", "006327", 100, 1.5),
            Holding("支付宝", "广发全球精选股票(QDII)", "000906", 100, 1.8),
        ]
        result = classify_holdings(holdings)
        self.assertIn("QDII", result)
        self.assertEqual(len(result["QDII"]), 3)


if __name__ == "__main__":
    unittest.main()

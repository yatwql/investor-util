"""scenario_extreme: 极限场景测试（S0c + S10）。

测试目标：
  S0c: 超多持仓（200+ 条）— 极限持仓量下批量计算不崩溃
  S10: 极端值（极大/极小持仓份额）— 数值溢出处理

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/resilience/test_scenario_extreme.py -v
  pytest src/test/ -m "scenario_extreme" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from src.python.models import Holding


# ═══════════════════════════════════════════════════════════════
#  S0c: 超多持仓（200+ 条）
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_extreme
class TestS0cLargeHoldings(unittest.TestCase):
    """S0c: 超多持仓（200+ 条）— 极限持仓量下的正确性。"""

    def setUp(self):
        # 阻止网络调用
        self._price_patcher = patch(
            "src.python.report.market_value.fetch_market_data")
        self._mock_price = self._price_patcher.start()
        self._mock_price.return_value = {
            "price": 10.0, "yesterday_close": 9.8,
            "price_date": "2026-07-03", "source": "腾讯财经",
            "source_api": "tencent",
        }

    def tearDown(self):
        self._price_patcher.stop()

    def _make_holding(self, account: str, name: str, code: str,
                       shares: float, cost_price: float) -> Holding:
        return Holding(
            account=account, name=name, code=code,
            shares=shares, cost_price=cost_price,
        )

    def test_200_holdings_generate_details(self):
        """200+ 持仓 → _generate_details 不崩溃。"""
        from src.python.report.market_value import _generate_details

        holdings = [
            self._make_holding("证券", f"批量股票{i:03d}", f"600{i:04d}",
                               100, 10.0)
            for i in range(201)
        ]

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            details = _generate_details(holdings, "2026-07-03")

        self.assertEqual(len(details), 201)
        # 验证所有持仓都有市值
        for d in details:
            self.assertGreater(d.market_value, 0)
            self.assertEqual(d.source_api, "tencent")

    def test_200_holdings_market_value_sum(self):
        """200+ 持仓 → 总市值 = 每条市值之和（不遗漏/不重复）。"""
        from src.python.report.market_value import _compute_detail_row

        holdings = [
            self._make_holding("证券", f"批量{i:03d}", f"600{i:04d}",
                               100, 10.0)
            for i in range(201)
        ]

        total_mv = 0.0
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            for h in holdings:
                mkt = {
                    "price": 10.0, "yesterday_close": 9.8,
                    "price_date": "2026-07-03", "source_api": "tencent",
                    "name": h.name, "code": h.code,
                }
                row = _compute_detail_row(h, mkt)
                total_mv += row.market_value

        # 每条市值 = 10.0 * 100 = 1000，201 条 = 201000
        self.assertAlmostEqual(total_mv, 201000.0)

    def test_200_holdings_all_account_subtotals(self):
        """200+ 持仓按账户分组 → 小计之和 = 总计。"""
        from src.python.report.market_value import _compute_detail_row

        holdings = []
        # 证券账户 100 条
        holdings.extend([
            self._make_holding("证券", f"ZQ{i:03d}", f"600{i:04d}",
                               100, 10.0)
            for i in range(100)
        ])
        # 支付宝 60 条
        holdings.extend([
            self._make_holding("支付宝", f"ZFB{i:03d}", f"000{i:04d}",
                               200, 5.0)
            for i in range(60)
        ])
        # 微信 41 条
        holdings.extend([
            self._make_holding("微信", f"WX{i:03d}", f"300{i:04d}",
                               50, 20.0)
            for i in range(41)
        ])

        self.assertEqual(len(holdings), 201)

        subtotals: dict[str, float] = {}
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            for h in holdings:
                mkt = {
                    "price": 10.0, "yesterday_close": 9.8,
                    "price_date": "2026-07-03", "source_api": "tencent",
                    "name": h.name, "code": h.code,
                }
                row = _compute_detail_row(h, mkt)
                subtotals[row.account] = subtotals.get(row.account, 0) + row.market_value

        total = sum(subtotals.values())
        all_held_total = sum(
            10.0 * h.shares for h in holdings
        )
        self.assertAlmostEqual(total, all_held_total)
        self.assertEqual(len(subtotals), 3)


# ═══════════════════════════════════════════════════════════════
#  S10: 极端值（极大/极小持仓份额）
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_extreme
class TestScenarioExtreme(unittest.TestCase):
    """S10: 极端值 — 极大/极小持仓份额。"""

    def test_extremely_large_shares(self):
        """极大份额 → 数值计算正确（不溢出）。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "长江电力", "600900", 10_000_000_000, 28.0)
        mkt = {
            "price": 28.5, "yesterday_close": 28.0,
            "price_date": "2026-07-03",
            "source": "腾讯财经", "source_api": "tencent",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            detail = _compute_detail_row(h, mkt)

        # 市值 = 28.5 * 10^10
        expected_mv = 28.5 * 10_000_000_000
        self.assertEqual(detail.market_value, round(expected_mv, 2))
        self.assertGreater(detail.profit, 0)

    def test_extremely_small_shares(self):
        """极小份额（1 股）→ 小数精度正确。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "长江电力", "600900", 1, 28.0)
        mkt = {
            "price": 28.55, "yesterday_close": 28.0,
            "price_date": "2026-07-03",
            "source": "腾讯财经", "source_api": "tencent",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            detail = _compute_detail_row(h, mkt)

        # 市值 = 28.55 * 1
        expected_mv = round(28.55 * 1, 2)
        self.assertEqual(detail.market_value, expected_mv)
        # today_profit = (28.55 - 28.0) * 1
        expected_today = round((28.55 - 28.0) * 1, 2)
        self.assertEqual(detail.today_profit, expected_today)

    def test_fractional_shares(self):
        """小数份额（0.001 股）→ 不崩溃。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "极小仓位", "600000", 0.001, 1000.0)
        mkt = {
            "price": 1050.0, "yesterday_close": 1000.0,
            "price_date": "2026-07-03",
            "source": "腾讯财经", "source_api": "tencent",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            detail = _compute_detail_row(h, mkt)

        # 不应崩溃
        self.assertAlmostEqual(detail.cost, 1000.0 * 0.001)
        self.assertAlmostEqual(detail.market_value, 1050.0 * 0.001)

    def test_high_precision_nav_price(self):
        """高精度净值价格（多位小数）→ 舍入正确。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("支付宝", "易方达蓝筹", "005827", 1000, 2.1234567)
        mkt = {
            "price": 2.2345678, "yesterday_close": 2.1000001,
            "price_date": "2026-07-03",
            "source": "天天基金", "source_api": "eastmoney",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            detail = _compute_detail_row(h, mkt)

        # 计算应有 round 保护
        expected_mv = round(2.2345678 * 1000, 2)
        expected_cost = round(2.1234567 * 1000, 2)
        self.assertEqual(detail.market_value, expected_mv)
        self.assertEqual(detail.cost, expected_cost)

    def test_extreme_combined(self):
        """多种极端值组合 → 不崩溃。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "极端组合", "600000", 0, 0.0)
        mkt = {
            "price": 0.0, "yesterday_close": 0.0,
            "price_date": "",
            "source": "--", "source_api": "",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            detail = _compute_detail_row(h, mkt)

        # 零份额 + 零成本 → 全零
        self.assertEqual(detail.shares, 0)
        self.assertEqual(detail.cost, 0.0)
        self.assertEqual(detail.market_value, 0.0)
        self.assertEqual(detail.profit, 0.0)
        self.assertEqual(detail.today_profit, 0.0)
        self.assertIsNone(detail.profit_rate)


if __name__ == "__main__":
    unittest.main()

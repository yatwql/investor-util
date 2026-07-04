"""Z2 — 操作行为场景（S29-S33）。

测试目标：
  验证个人投资者日常操作行为后的报告正确性：

  S29: 分红送转除权 — 送转后份额跳变和成本摊薄计算
  S30: 定投成本摊薄 — 多次不同价格买入的加权平均成本
  S31: 部分调仓卖出 — 卖出后剩余持仓成本和盈亏
  S32: 跨账户转仓 — 同代码跨账户不重复计算
  S33: 新股中签待上市 — 未上市 IPO 以发行价估值

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_operational_behavior.py -v
  pytest src/test/ -m "scenario_basic" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from src.python.models import Holding

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]


# ═══════════════════════════════════════════════════════════════
#  S29: 分红送转除权
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS29DividendSplit(unittest.TestCase):
    """S29: 分红送转除权 — 送转后份额跳变和成本摊薄计算。

    10 送 10 后持仓份额翻倍，每份成本减半，总成本不变。
    除权后交易所在除权除息日调整开盘参考价。
    """

    def test_split_doubles_shares_cost_unchanged(self):
        """10送10后 shares 翻倍、cost_price 减半 → 总成本不变。"""
        from src.python.report.market_value import _compute_detail_row

        # 除权前：100 股 × 10.0 = 1000
        # 除权后：200 股 × 5.0  = 1000（总成本不变）
        h = Holding("证券", "长江电力", "600900", shares=200, cost_price=5.0)
        mkt = {
            "price": 6.0, "yesterday_close": 5.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "长江电力", "code": "600900",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.shares, 200.0)
        self.assertEqual(row.cost, 1000.0)          # 200 × 5.0 = 1000
        self.assertEqual(row.market_value, 1200.0)  # 200 × 6.0 = 1200
        self.assertEqual(row.profit, 200.0)          # 1200 - 1000

    def test_split_profit_rate_after_ex_rights(self):
        """除权除息后股价调整 → 收益率基于除权成本正确计算。"""
        from src.python.report.market_value import _compute_detail_row

        # 除权前成本 10 元/股，10 送 10 后成本摊薄为 5 元/股
        # 除权参考价 = (前收盘 - 股息) / (1 + 送转比例)
        # 除权后股价 7 元
        h = Holding("证券", "长江电力", "600900", shares=200, cost_price=5.0)
        mkt = {
            "price": 7.0, "yesterday_close": 5.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "长江电力", "code": "600900",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.market_value, 1400.0)  # 200 × 7.0
        self.assertEqual(row.cost, 1000.0)           # 200 × 5.0
        self.assertEqual(row.profit, 400.0)          # 1400 - 1000
        # profit_rate = profit / cost
        self.assertIsNotNone(row.profit_rate)
        self.assertAlmostEqual(row.profit_rate, 0.4)  # 400 / 1000

    def test_split_zero_cost_songgu(self):
        """纯送股（零成本获得）→ cost_price=0，profit_rate=None。"""
        from src.python.report.market_value import _compute_detail_row

        # 送股获得 100 股，成本为 0
        h = Holding("证券", "某股票", "600111", shares=100, cost_price=0.0)
        mkt = {
            "price": 15.0, "yesterday_close": 14.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "某股票", "code": "600111",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.cost, 0.0)
        self.assertEqual(row.market_value, 1500.0)  # 100 × 15.0
        self.assertEqual(row.profit, 1500.0)         # 1500 - 0
        self.assertIsNone(row.profit_rate)            # 零成本不触发除零


# ═══════════════════════════════════════════════════════════════
#  S30: 定投成本摊薄
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS30DcaCostAveraging(unittest.TestCase):
    """S30: 定投成本摊薄 — 多批次不同价格买入的加权平均成本。"""

    def test_dca_two_batches(self):
        """两批不同价买入 → 加权平均成本正确，总成本 = shares × wavg_price。"""
        from src.python.report.market_value import _compute_detail_row

        # 第 1 批：100 股 × 10.0 = 1000
        # 第 2 批：100 股 × 12.0 = 1200
        # 加权平均成本 = (1000 + 1200) / 200 = 11.0
        h = Holding("证券", "沪深300ETF", "510300", shares=200, cost_price=11.0)
        mkt = {
            "price": 13.0, "yesterday_close": 12.8,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "沪深300ETF", "code": "510300",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.shares, 200.0)
        self.assertEqual(row.cost, 2200.0)          # 200 × 11.0
        self.assertEqual(row.market_value, 2600.0)  # 200 × 13.0
        self.assertEqual(row.profit, 400.0)          # 2600 - 2200

    def test_dca_three_batches_uneven(self):
        """三批不等额买入 → 加权平均成本正确。"""
        from src.python.report.market_value import _compute_detail_row

        # 第 1 批：200 股 × 8.0  = 1600
        # 第 2 批：100 股 × 10.0 = 1000
        # 第 3 批：50 股  × 12.0 = 600
        # 加权平均 = (1600 + 1000 + 600) / 350 = 9.142857...
        # cost_price 取 round 后传入
        total_shares = 350
        total_cost = 200 * 8.0 + 100 * 10.0 + 50 * 12.0  # 3200
        wavg = round(total_cost / total_shares, 2)  # 9.14

        h = Holding("证券", "中证500ETF", "510500",
                    shares=total_shares, cost_price=wavg)
        mkt = {
            "price": 11.0, "yesterday_close": 10.8,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "中证500ETF", "code": "510500",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertAlmostEqual(row.cost, total_cost, delta=1.0)  # 允许舍入误差
        self.assertAlmostEqual(row.market_value, 3850.0)          # 350 × 11.0

    def test_dca_loss_position(self):
        """定投后市价低于加权平均成本 → 亏损。"""
        from src.python.report.market_value import _compute_detail_row

        # 加权平均成本 11.0，市价 9.0 → 亏损
        h = Holding("证券", "科创50ETF", "588000", shares=200, cost_price=11.0)
        mkt = {
            "price": 9.0, "yesterday_close": 9.2,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "科创50ETF", "code": "588000",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.cost, 2200.0)          # 200 × 11.0
        self.assertEqual(row.market_value, 1800.0)  # 200 × 9.0
        self.assertEqual(row.profit, -400.0)         # 1800 - 2200
        self.assertIsNotNone(row.profit_rate)
        self.assertAlmostEqual(row.profit_rate, -0.1818, places=3)


# ═══════════════════════════════════════════════════════════════
#  S31: 部分调仓卖出
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS31PartialSell(unittest.TestCase):
    """S31: 部分调仓卖出 — 卖出后剩余持仓成本和盈亏。"""

    def test_partial_sell_half(self):
        """卖出 50% 后剩余 shares 正确，cost_price 不变（加权平均）。"""
        from src.python.report.market_value import _compute_detail_row

        # 原 200 股 × 10.0，卖出 100 股
        # 剩余：100 股 × 10.0（加权平均成本不变）
        h = Holding("证券", "贵州茅台", "600519", shares=100, cost_price=10.0)
        mkt = {
            "price": 12.0, "yesterday_close": 11.8,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "贵州茅台", "code": "600519",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.shares, 100.0)
        self.assertEqual(row.cost, 1000.0)          # 100 × 10.0
        self.assertEqual(row.market_value, 1200.0)  # 100 × 12.0
        self.assertEqual(row.profit, 200.0)          # 1200 - 1000

    def test_partial_sell_most(self):
        """卖出大部分（90%）→ 剩余少量份额成本正确。"""
        from src.python.report.market_value import _compute_detail_row

        # 原 1000 股 × 5.0，卖出 900 股
        # 剩余：100 股 × 5.0
        h = Holding("证券", "工商银行", "601398", shares=100, cost_price=5.0)
        mkt = {
            "price": 5.5, "yesterday_close": 5.4,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "工商银行", "code": "601398",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.shares, 100.0)
        self.assertEqual(row.cost, 500.0)           # 100 × 5.0
        self.assertEqual(row.market_value, 550.0)   # 100 × 5.5
        self.assertEqual(row.profit, 50.0)           # 550 - 500

    def test_partial_sell_all_cleared(self):
        """全部卖出 → shares=0，残值归零。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "工商银行", "601398", shares=0, cost_price=0.0)
        mkt = {
            "price": 5.5, "yesterday_close": 5.4,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "工商银行", "code": "601398",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.shares, 0.0)
        self.assertEqual(row.cost, 0.0)
        self.assertEqual(row.market_value, 0.0)
        self.assertEqual(row.profit, 0.0)


# ═══════════════════════════════════════════════════════════════
#  S32: 跨账户转仓
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS32CrossAccount(unittest.TestCase):
    """S32: 跨账户转仓 — 同代码跨账户不重复计算。"""

    def test_same_stock_two_accounts_two_rows(self):
        """同代码两个账户 → 各自生成 DetailRow，不冲突。"""
        from src.python.report.market_value import _compute_detail_row

        # 证券账户：100 股长江电力
        h1 = Holding("证券账户", "长江电力", "600900", shares=100, cost_price=10.0)
        # 信用账户：50 股长江电力（转仓后）
        h2 = Holding("信用账户", "长江电力", "600900", shares=50, cost_price=10.0)

        mkt = {
            "price": 25.0, "yesterday_close": 24.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "长江电力", "code": "600900",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row1 = _compute_detail_row(h1, mkt)
                row2 = _compute_detail_row(h2, mkt)

        # 两条独立明细
        self.assertEqual(row1.account, "证券账户")
        self.assertEqual(row2.account, "信用账户")
        self.assertEqual(row1.code, "600900")
        self.assertEqual(row2.code, "600900")
        self.assertEqual(row1.shares, 100.0)
        self.assertEqual(row2.shares, 50.0)
        # 市值分别计算，不再合并
        self.assertEqual(row1.market_value, 2500.0)  # 100 × 25
        self.assertEqual(row2.market_value, 1250.0)  # 50 × 25
        # 合计（分类汇总应由 summary 模块处理合并）
        total_mv = row1.market_value + row2.market_value
        self.assertEqual(total_mv, 3750.0)

    def test_same_stock_same_category(self):
        """同代码两账户 → 分类一致。"""
        from src.python.report.category import _categorize_holding

        h1 = Holding("证券账户", "长江电力", "600900", shares=100, cost_price=10.0)
        h2 = Holding("信用账户", "长江电力", "600900", shares=50, cost_price=10.0)

        prop1, sub1 = _categorize_holding(h1)
        prop2, sub2 = _categorize_holding(h2)

        self.assertEqual(prop1, prop2)
        self.assertEqual(sub1, sub2)
        self.assertEqual(prop1, "股票")
        self.assertEqual(sub1, "A股")

    def test_different_stocks_different_accounts(self):
        """不同代码各账户独立 → 分类各自正确。"""
        from src.python.report.market_value import _compute_detail_row

        h1 = Holding("证券账户", "长江电力", "600900", shares=100, cost_price=10.0)
        h2 = Holding("信用账户", "贵州茅台", "600519", shares=50, cost_price=200.0)

        mkt1 = {
            "price": 25.0, "yesterday_close": 24.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "长江电力", "code": "600900",
        }
        mkt2 = {
            "price": 1800.0, "yesterday_close": 1780.0,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "贵州茅台", "code": "600519",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row1 = _compute_detail_row(h1, mkt1)
                row2 = _compute_detail_row(h2, mkt2)

        self.assertEqual(row1.code, "600900")
        self.assertEqual(row2.code, "600519")
        self.assertEqual(row1.market_value, 2500.0)
        self.assertEqual(row2.market_value, 90000.0)
        self.assertNotEqual(row1.account, row2.account)


# ═══════════════════════════════════════════════════════════════
#  S33: 新股中签待上市
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS33IpoPendingListing(unittest.TestCase):
    """S33: 新股中签待上市 — 未上市 IPO 以发行价估值。"""

    def test_ipo_no_market_data(self):
        """新股无行情 → cost 基于发行价，market_value=0，不崩溃。"""
        from src.python.report.market_value import _compute_detail_row

        # 中签 500 股，发行价 22.5
        h = Holding("证券", "某新股", "789001", shares=500, cost_price=22.5)
        row = _compute_detail_row(h, None)

        self.assertEqual(row.shares, 500.0)
        self.assertEqual(row.cost, 11250.0)         # 500 × 22.5
        self.assertEqual(row.market_value, 0.0)      # 无行情
        self.assertEqual(row.price, 0.0)
        self.assertEqual(row.price_type, "--")
        self.assertEqual(row.profit, 0.0)            # 无行情时 profit 硬编码为 0（不显示伪亏损）

    def test_ipo_with_market_data_after_listing(self):
        """新股上市后有行情 → 正常按市价计算。"""
        from src.python.report.market_value import _compute_detail_row

        # 上市首日，发行价 22.5，开盘价 30.0
        h = Holding("证券", "某新股", "789001", shares=500, cost_price=22.5)
        mkt = {
            "price": 30.0, "yesterday_close": 22.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "某新股", "code": "789001",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)

        self.assertEqual(row.shares, 500.0)
        self.assertEqual(row.cost, 11250.0)          # 500 × 22.5
        self.assertEqual(row.market_value, 15000.0)  # 500 × 30.0
        self.assertEqual(row.profit, 3750.0)          # 15000 - 11250

    def test_ipo_multiple_allocations(self):
        """多只新股中签 → 各自计算不干扰。"""
        from src.python.report.market_value import _compute_detail_row

        h1 = Holding("证券", "新股A", "789001", shares=500, cost_price=22.5)
        h2 = Holding("证券", "新股B", "789002", shares=1000, cost_price=10.0)

        # 新股A 有行情（已上市），新股B 无行情（未上市）
        mkt1 = {
            "price": 30.0, "yesterday_close": 22.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "新股A", "code": "789001",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row1 = _compute_detail_row(h1, mkt1)
                row2 = _compute_detail_row(h2, None)

        # 新股A：正常计算
        self.assertEqual(row1.cost, 11250.0)
        self.assertEqual(row1.market_value, 15000.0)
        # 新股B：无行情降级
        self.assertEqual(row2.shares, 1000.0)
        self.assertEqual(row2.cost, 10000.0)
        self.assertEqual(row2.market_value, 0.0)
        self.assertEqual(row2.price_type, "--")


if __name__ == "__main__":
    unittest.main()

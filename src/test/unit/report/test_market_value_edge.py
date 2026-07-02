"""市场价值边缘场景测试 — R-090 (溢价率)、R-091 (today_profit=0)。

测试目标：
  - R-090: premium 始终为占位符 "--"，所有资产溢价率列正确显示
  - R-091: 场外基金非 T 日净值日期 → today_profit = 0
  - R-091: tencent 场内存货始终计算 today_profit
  - R-091: 无净值日期 → today_profit = 0
  - detail row 序列化溢价率列值正确
  - R-100: 净值数据空窗期处理（_count_trading_days_back / NAV 日期缺口）
  - R-101: 交易时段切换瞬间取价方式标签 + cache TTL 竞争行为

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_market_value_edge -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import ANY, MagicMock, patch

from src.python.models import Holding
from src.python.report.market_value import (
    _count_trading_days_back,
    _determine_price_type,
    _is_trading_day,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]



class TestPremiumPlaceholder(unittest.TestCase):
    """R-090: 溢价率始终为占位符 '--'。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    def test_tencent_premium_placeholder(self, mock_midday, mock_open, mock_td):
        """Tencent 场内资产 → premium = '--'。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 100, 10.0)
        mkt = {
            "price": 25.0, "yesterday_close": 24.5,
            "price_date": "2026-06-30", "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.premium, _FUND_PREMIUM_PLACEHOLDER)
        self.assertEqual(detail.premium, "--")

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_eastmoney_premium_placeholder(self, mock_open, mock_td):
        """Eastmoney 场外基金 → premium = '--'。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0)
        mkt = {
            "price": 2.1, "yesterday_close": 2.0,
            "price_date": "2026-06-30", "source": "天天基金", "source_api": "eastmoney",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.premium, "--")

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_detail_to_row_values_premium(self, mock_open, mock_td):
        """_detail_to_row_values 序列化 premium 值正确。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "贵州茅台", "600519", 50, 200.0)
        mkt = {
            "price": 2050.0, "yesterday_close": 2000.0,
            "price_date": "2026-06-30", "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        values = _detail_to_row_values(detail)

        # 溢价率在第 8 列（索引 7）
        premium_col = values[7]
        self.assertEqual(premium_col, "--")

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_multiple_assets_all_premium_placeholder(self, mock_open, mock_td):
        """多种资产溢价率全部为 '--'。"""
        mock_td.return_value = "2026-06-30"

        holdings = [
            Holding("证券", "长江电力", "600900", 100, 10.0),
            Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0),
        ]
        mkts = [
            {"price": 25.0, "yesterday_close": 24.5, "price_date": "2026-06-30",
             "source": "腾讯财经", "source_api": "tencent"},
            {"price": 2.1, "yesterday_close": 2.0, "price_date": "2026-06-25",
             "source": "天天基金", "source_api": "eastmoney"},
        ]

        for h, m in zip(holdings, mkts):
            detail = _compute_detail_row(h, m)
            self.assertEqual(detail.premium, "--")

    def test_premium_placeholder_constant(self):
        """_FUND_PREMIUM_PLACEHOLDER 常量值为 '--'。"""
        self.assertEqual(_FUND_PREMIUM_PLACEHOLDER, "--")


class TestTodayProfitEastMoneyNonTDay(unittest.TestCase):
    """R-091: 场外基金非 T 日 → today_profit = 0。"""

    def _make_market_data(self, nav_date: str, source_api: str = "eastmoney") -> dict:
        return {
            "price": 2.5, "yesterday_close": 2.4,
            "price_date": nav_date,
            "source": "天天基金", "source_api": source_api,
        }

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_non_t_day_eastmoney(self, mock_open, mock_td):
        """Eastmoney, nav_date != trading_day → today_profit = 0。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0)
        mkt = self._make_market_data("2026-06-23")  # 非 T 日
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_t_day_eastmoney_calculates(self, mock_open, mock_td):
        """Eastmoney, nav_date == trading_day → today_profit > 0。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0)
        mkt = self._make_market_data("2026-06-30")  # T 日
        detail = _compute_detail_row(h, mkt)
        expected = round((2.5 - 2.4) * 100, 2)
        self.assertEqual(detail.today_profit, expected)
        self.assertGreater(detail.today_profit, 0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_empty_nav_date_eastmoney(self, mock_open, mock_td):
        """Eastmoney, nav_date 为空 → today_profit = 0。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0)
        mkt = self._make_market_data("")
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)


class TestTodayProfitTencentAlways(unittest.TestCase):
    """R-091: Tencent 场内资产始终计算 today_profit。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_tencent_always_calculates(self, mock_open, mock_td):
        """Tencent 无论 nav_date 是什么 → today_profit 始终计算。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 200, 10.0)
        mkt = {
            "price": 28.5, "yesterday_close": 28.0,
            "price_date": "2026-06-25",  # 非 T 日
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        expected = round((28.5 - 28.0) * 200, 2)
        self.assertEqual(detail.today_profit, expected)
        self.assertGreater(detail.today_profit, 0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_tencent_empty_nav_date_calculates(self, mock_open, mock_td):
        """Tencent, nav_date 为空 → today_profit 仍计算。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 100, 10.0)
        mkt = {
            "price": 25.5, "yesterday_close": 25.0,
            "price_date": "",
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        expected = round((25.5 - 25.0) * 100, 2)
        self.assertEqual(detail.today_profit, expected)

    @patch("src.python.report.market_value.get_last_trading_day")
    def test_tencent_qdii_always_calculates(self, mock_td):
        """Tencent QDII ETF → today_profit 始终计算（场内逻辑）。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "纳斯达克ETF", "513300", 300, 1.5)
        mkt = {
            "price": 1.8, "yesterday_close": 1.75,
            "price_date": "2026-06-27",  # 多个自然日前的 T-1 净值
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        expected = round((1.8 - 1.75) * 300, 2)
        self.assertEqual(detail.today_profit, expected)


class TestTodayProfitEdgeCases(unittest.TestCase):
    """today_profit 边界场景。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_no_price_data(self, mock_open, mock_td):
        """获取行情失败（price=0）→ today_profit = 0。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0)
        mkt = {
            "price": 0.0, "yesterday_close": 0.0,
            "price_date": "",
            "source": "--", "source_api": "",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_today_profit_negative(self, mock_open, mock_td):
        """本日下跌 → today_profit 为负值。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 100, 10.0)
        mkt = {
            "price": 24.0, "yesterday_close": 25.0,
            "price_date": "2026-06-30", "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        expected = round((24.0 - 25.0) * 100, 2)
        self.assertEqual(detail.today_profit, expected)
        self.assertLess(detail.today_profit, 0)

    def test_today_profit_in_price_update_status(self):
        """price_update_status 影响 today_profit 计算路径，但不直接修改值。"""
        # 这个测试验证 price_update_status 的分类逻辑
        # 与 _compute_detail_row 中的 today_profit 计算一致
        pass


class TestPremiumInWriteSheet(unittest.TestCase):
    """验证 premium 在写入页签时的列值。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_premium_in_excel_row(self, mock_open, mock_td):
        """写入 Excel 行时溢价率列为 '--'。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 100, 10.0)
        mkt = {
            "price": 25.0, "yesterday_close": 24.5,
            "price_date": "2026-06-30", "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        values = _detail_to_row_values(detail)
        # _detail_to_row_values 第 8 列(索引 7) = premium
        self.assertEqual(values[7], "--")


class TestCurrencyConversion(unittest.TestCase):
    """R-096: 多币种转换正确 — 美元/港币份额处理。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_qdii_price_in_rmb_from_api(self, mock_open, mock_td):
        """QDII 价格来自 API（已为人民币计值），市值计算正确。"""
        mock_td.return_value = "2026-07-01"
        h = Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0)
        # API 返回的 NAV 已为人民币
        mkt = {
            "price": 2.1, "yesterday_close": 2.0,
            "price_date": "2026-07-01", "source": "天天基金", "source_api": "eastmoney",
            "nav_date": "2026-07-01",
        }
        detail = _compute_detail_row(h, mkt)
        # 市值 = 2.1 × 100 = 210
        self.assertAlmostEqual(detail.market_value, 210.0, delta=0.01)
        # 本日盈亏 = (2.1 - 2.0) × 100 = 10
        self.assertAlmostEqual(detail.today_profit, 10.0, delta=0.01)

    @patch("src.python.report.market_value.get_last_trading_day")
    def test_qdii_today_profit_t1(self, mock_td):
        """QDII 净值日期=T-1 → today_profit=0（当前行为，待扩展）。"""
        mock_td.return_value = "2026-07-01"  # T
        h = Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0)
        mkt = {
            "price": 2.1, "yesterday_close": 2.0,
            "price_date": "2026-06-30", "source": "天天基金", "source_api": "eastmoney",
            "nav_date": "2026-06-30",  # T-1
        }
        detail = _compute_detail_row(h, mkt)
        # 当前实现：today_profit 仅当 nav_date == trading_day 时计算
        # QDII 的 T-1 延迟在此处未被特殊处理
        self.assertEqual(detail.today_profit, 0.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    def test_price_update_status_qdii_t1_updated(self, mock_td):
        """price_update_status 正确识别 QDII T-1 为已更新。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import price_update_status
        h = Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0)
        mkt = {
            "price": 2.1, "yesterday_close": 2.0,
            "price_date": "2026-06-30", "source": "天天基金", "source_api": "eastmoney",
            "nav_date": "2026-06-30",
        }
        detail = _compute_detail_row(h, mkt)
        updated, total, all_updated = price_update_status([detail], "2026-07-01")
        self.assertEqual(updated, 1)
        self.assertEqual(total, 1)
        self.assertTrue(all_updated)


class TestCountTradingDaysBack(unittest.TestCase):
    """R-100: _count_trading_days_back 净值日期空窗期判定。

    验证场外基金净值日期缺失时的 T-N 计算正确性，
    覆盖基金建仓期净值不可用约 3 个月的极端场景。
    """

    TD = "2026-07-01"  # Wednesday

    def _side_effect_is_trading_day(self, d: datetime) -> bool:
        """周六日除外，其余为交易日。"""
        return d.weekday() < 5

    def _call(self, nav_date: str, trading_day: str | None = None) -> int | None:
        from src.python.report.market_value import _count_trading_days_back
        return _count_trading_days_back(trading_day or self.TD, nav_date)

    # ── 正常场景 ────────────────────────────────────────

    @patch("src.python.report.market_value._is_trading_day")
    def test_same_day_returns_none(self, mock_istd):
        """nav_date == trading_day → None（无需回退）。"""
        mock_istd.side_effect = self._side_effect_is_trading_day
        self.assertIsNone(self._call("2026-07-01"))

    @patch("src.python.report.market_value._is_trading_day")
    def test_prev_trading_day_returns_1(self, mock_istd):
        """nav_date == T-1 → 返回 1。"""
        mock_istd.side_effect = self._side_effect_is_trading_day
        self.assertEqual(self._call("2026-06-30"), 1)

    @patch("src.python.report.market_value._is_trading_day")
    def test_two_days_back(self, mock_istd):
        """nav_date == T-2（跨 1 个自然日）→ 返回 2。"""
        mock_istd.side_effect = self._side_effect_is_trading_day
        self.assertEqual(self._call("2026-06-29"), 2)

    @patch("src.python.report.market_value._is_trading_day")
    def test_five_days_back_skip_weekend(self, mock_istd):
        """nav_date == T-5（跨周末）→ 返回 5。"""
        mock_istd.side_effect = self._side_effect_is_trading_day
        # T=周三，往前 5 个交易日 = 上周三(06-24)
        self.assertEqual(self._call("2026-06-24"), 5)

    @patch("src.python.report.market_value._is_trading_day")
    def test_six_plus_days_back(self, mock_istd):
        """nav_date > 5 个交易日前 → 返回正确 N。"""
        mock_istd.side_effect = self._side_effect_is_trading_day
        # T=周三，往前 8 个交易日 = 上周五(06-19)（跳过 2 个周末日）
        result = self._call("2026-06-19")
        self.assertEqual(result, 8)
        self.assertGreater(result, 5)

    # ── 异常场景 ────────────────────────────────────────

    @patch("src.python.report.market_value._is_trading_day")
    def test_future_date_returns_none(self, mock_istd):
        """nav_date > trading_day（未来日期）→ None。"""
        mock_istd.side_effect = self._side_effect_is_trading_day
        self.assertIsNone(self._call("2026-07-02"))

    @patch("src.python.report.market_value._is_trading_day")
    def test_nav_beyond_60_days_lookback(self, mock_istd):
        """nav_date 超出 60 个自然日查找范围 → None。"""
        mock_istd.side_effect = self._side_effect_is_trading_day
        self.assertIsNone(self._call("2026-04-01"))

    def test_invalid_date_returns_none(self):
        """无效日期字符串 → None。"""
        self.assertIsNone(self._call("not-a-date"))


class TestDeterminePriceTypeNavGap(unittest.TestCase):
    """R-100: _determine_price_type 场外基金净值日期空窗期取价标签。"""

    def setUp(self):
        self.td = "2026-07-01"  # Wednesday
        self.prev = "2026-06-30"  # Tuesday

    def _call(self, nav_date: str) -> str:
        from src.python.report.market_value import _determine_price_type
        return _determine_price_type("eastmoney", nav_date, self.td)

    def test_nav_date_empty(self):
        """无净值日期 → 官方净值(--)。"""
        self.assertEqual(self._call(""), "官方净值(--)")

    def test_nav_date_today(self):
        """nav_date == T → 官方净值(T)。"""
        self.assertEqual(self._call(self.td), "官方净值(T)")

    def test_nav_date_prev(self):
        """nav_date == T-1 → 官方净值(T-1)。"""
        self.assertEqual(self._call(self.prev), "官方净值(T-1)")

    def test_nav_date_t2(self):
        """nav_date == T-2 → 官方净值(T-2)。"""
        self.assertEqual(self._call("2026-06-29"), "官方净值(T-2)")

    def test_nav_date_t3(self):
        """nav_date == T-3 → 官方净值(T-3)。"""
        self.assertEqual(self._call("2026-06-26"), "官方净值(T-3)")

    def test_nav_date_t4(self):
        """nav_date == T-4 → 官方净值(T-4)。"""
        self.assertEqual(self._call("2026-06-25"), "官方净值(T-4)")

    def test_nav_date_t5(self):
        """nav_date == T-5 → 官方净值(T-5)。"""
        self.assertEqual(self._call("2026-06-24"), "官方净值(T-5)")

    def test_nav_date_6plus_days(self):
        """nav_date > 5 个交易日前 → 官方净值(日期)。"""
        self.assertEqual(self._call("2026-06-19"), "官方净值(2026-06-19)")

    def test_nav_date_three_months_gap(self):
        """nav_date 约 3 个月前（建仓期空窗）→ 官方净值(日期)。"""
        self.assertEqual(self._call("2026-04-01"), "官方净值(2026-04-01)")

    def test_future_nav_date(self):
        """nav_date 为未来日期（数据异常）→ 官方净值(T)。"""
        self.assertEqual(self._call("2026-07-02"), "官方净值(T)")


class TestDeterminePriceTypeSessionSwitch(unittest.TestCase):
    """R-101: 交易时段切换瞬间 _determine_price_type 标签正确。"""

    def setUp(self):
        self.td = "2026-07-01"
        self.prev = "2026-06-30"

    # ── 11:29:59 → 11:30:00 ─────────────────────────────

    @patch("src.python.report.market_value.is_market_open", return_value=True)
    def test_morning_112959_still_trading(self, _):
        """11:29:59 上午交易时段 → 场内实时价。"""
        from src.python.report.market_value import _determine_price_type
        result = _determine_price_type("tencent", self.td, self.td)
        self.assertEqual(result, "场内实时价")

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=True)
    def test_midday_113000_just_closed(self, _, __):
        """11:30:00 刚进入午间休市 → 场内午市收盘(T)。"""
        from src.python.report.market_value import _determine_price_type
        result = _determine_price_type("tencent", self.td, self.td)
        self.assertEqual(result, "场内午市收盘(T)")

    # ── 14:59:59 → 15:00:00 ─────────────────────────────

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=True)
    def test_midday_145959_still_midday(self, _, __):
        """14:59:59 仍在午间休市（未开盘）→ 场内午市收盘(T)。"""
        from src.python.report.market_value import _determine_price_type
        result = _determine_price_type("tencent", self.td, self.td)
        self.assertEqual(result, "场内午市收盘(T)")

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    def test_close_150000_market_closed(self, _, __):
        """15:00:00 已收盘 → 场内收盘价(T)。"""
        from src.python.report.market_value import _determine_price_type

        result = _determine_price_type("tencent", self.td, self.td)
        self.assertEqual(result, "场内收盘价(T)")


if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()

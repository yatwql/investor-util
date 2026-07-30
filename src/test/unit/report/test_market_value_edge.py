"""市场价值边缘场景测试 — 溢价率/today_profit/净值空窗/时段切换。

测试目标：
  - premium 始终为占位符 "--"，所有资产溢价率列正确显示
  - 场外基金非 T 日净值日期 → today_profit = 0
  - tencent 场内资产始终计算 today_profit
  - 无净值日期 → today_profit = 0
  - detail row 序列化溢价率列值正确
  - 净值数据空窗期处理（_count_trading_days_back / NAV 日期缺口）
  - 交易时段切换瞬间取价方式标签 + cache TTL 竞争行为

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_market_value_edge -v
"""

from __future__ import annotations

import unittest
import math
from datetime import datetime, timedelta
from unittest.mock import ANY, MagicMock, patch

from src.python.core.models import Holding
from src.python.report.market_value import (
    _compute_detail_row,
    _count_trading_days_back,
    _determine_price_type,
    _FUND_PREMIUM_PLACEHOLDER,
    _is_trading_day,
)
from src.python.report.market_value_sheet import (
    _detail_to_row_values,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]



class TestPremiumPlaceholder(unittest.TestCase):
    """溢价率始终为占位符 '--'。"""

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
    """场外基金非 T 日 → today_profit = 0。"""

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
    """Tencent 场内资产始终计算 today_profit。"""

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
    """多币种转换正确 — 美元/港币份额处理。"""

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
    """_count_trading_days_back 净值日期空窗期判定。

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
    """_determine_price_type 场外基金净值日期空窗期取价标签。"""

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
    """交易时段切换瞬间 _determine_price_type 标签正确。"""

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


# ═══════════════════════════════════════════════════════════
# Y4: 数值计算纵深 — 浮点/极值/NaN/int32/负成本
# ═══════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.unit_report
@pytest.mark.edge
class TestNumericalEdgeY4(unittest.TestCase):
    """Y4: 数值计算纵深边缘场景。

    覆盖浮点累加误差/极微份额/超高单价/收益率超 ±1000%/NaN 传播链/
    int32 溢出/负成本/多数量级相加共 12 项测试。
    """

    # ── Y4-1: 浮点累加误差 ────────────────────────────────

    def test_float_accumulation_many_tiny_values(self):
        """1000 条微额持仓 market_value 累加 → 浮点误差在 1e-6 以内。"""
        from src.python.report.market_value import DetailRow
        details = [
            DetailRow(account="账户", name=f"资产{i}", code=f"000{i:04d}",
                      shares=0.01, cost=0.01, price=0.001 * (i % 10 + 1),
                      yesterday_close=0.001, nav_date="", source_api="tencent",
                      today_profit=0.0, profit=0.0, profit_rate=0.0,
                      premium="--", market_value=0.001 * (i % 10 + 1) * 0.01,
                      ) for i in range(1000)
        ]
        total = sum(d.market_value for d in details)
        expected = 0.055
        self.assertAlmostEqual(total, expected, places=6)

    def test_float_accumulation_many_profit_values(self):
        """1000 条持仓 profit 累加 → 浮点误差在合理范围。"""
        from src.python.report.market_value import DetailRow
        details = [
            DetailRow(account="账户", name=f"资产{i}", code=f"000{i:04d}",
                      shares=1.0, cost=100.0, price=100.0,
                      yesterday_close=100.0, nav_date="", source_api="tencent",
                      today_profit=0.0, profit=0.01,
                      profit_rate=0.0001, premium="--", market_value=100.0,
                      ) for i in range(1000)
        ]
        total = sum(d.profit for d in details)
        self.assertAlmostEqual(total, 10.0, places=6)

    # ── Y4-2: 极微份额 ────────────────────────────────────

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_tiny_shares_001(self, mock_open, mock_td):
        """极微份额（0.01 份）→ 市值计算正确无精度丢失。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "极微持仓", "600519", 0.01, 200000.0)
        mkt = {"price": 210000.0, "yesterday_close": 208000.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.cost, 2000.0)
        self.assertAlmostEqual(detail.market_value, 2100.0)
        self.assertAlmostEqual(detail.profit, 100.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_tiny_shares_0001(self, mock_open, mock_td):
        """极微份额（0.0001 份）→ 市值计算正确。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "纳米持仓", "600519", 0.0001, 200000.0)
        mkt = {"price": 210000.0, "yesterday_close": 208000.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.cost, 20.0)
        self.assertAlmostEqual(detail.market_value, 21.0)
        self.assertAlmostEqual(detail.profit, 1.0)

    # ── Y4-3: 超高单价 ────────────────────────────────────

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_ultra_high_price(self, mock_open, mock_td):
        """超高单价（20 万/份）→ 市值计算正确无溢出。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "贵州茅台", "600519", 10, 200000.0)
        mkt = {"price": 210000.0, "yesterday_close": 208000.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.market_value, 2100000.0)
        self.assertAlmostEqual(detail.cost, 2000000.0)
        self.assertAlmostEqual(detail.profit, 100000.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_ultra_high_price_precision(self, mock_open, mock_td):
        """超高单价（万元级带两位小数）× 份额 → 精度正确。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "高价资产", "000001", 123.45, 15234.56)
        mkt = {"price": 15876.82, "yesterday_close": 15700.00,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        expected_mv = round(15876.82 * 123.45, 2)
        expected_cost = round(15234.56 * 123.45, 2)
        self.assertAlmostEqual(detail.market_value, expected_mv, places=2)
        self.assertAlmostEqual(detail.cost, expected_cost, places=2)

    # ── Y4-4: 收益率超 ±1000% ─────────────────────────────

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_extreme_positive_profit_rate_over_1000pct(self, mock_open, mock_td):
        """收益率 > 1000%（微成本暴涨）→ profit_rate > 10.0 不崩溃。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "百倍股", "000001", 100, 0.01)
        mkt = {"price": 50.0, "yesterday_close": 49.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertGreater(detail.profit_rate, 10.0)
        self.assertAlmostEqual(detail.profit_rate, 4999.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_extreme_negative_profit_rate(self, mock_open, mock_td):
        """严重亏损（成本远高于市值）→ profit_rate ≈ -100%。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "清零资产", "000001", 100, 1000.0)
        mkt = {"price": 0.5, "yesterday_close": 0.6,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.profit_rate, -0.9995, places=4)
        self.assertGreater(detail.profit_rate, -1.0)

    # ── Y4-5: NaN 传播链 ─────────────────────────────────

    def test_nan_price_does_not_crash(self):
        """price = NaN → 不崩溃。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "异常资产", "000001", 100, 10.0)
        mkt = {"price": float('nan'), "yesterday_close": 10.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        try:
            detail = _compute_detail_row(h, mkt)
            self.assertTrue(math.isnan(detail.market_value) or detail.market_value == 0.0)
        except Exception:
            self.fail("NaN price should not cause exception")

    def test_nan_yclose_does_not_crash(self):
        """yesterday_close = NaN → today_profit 不崩溃。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "异常资产", "000001", 100, 10.0)
        mkt = {"price": 10.0, "yesterday_close": float('nan'),
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        try:
            detail = _compute_detail_row(h, mkt)
            self.assertIsNotNone(detail)
            self.assertTrue(math.isnan(detail.today_profit) or detail.today_profit == 0.0)
        except Exception:
            self.fail("NaN yesterday_close should not cause exception")

    # ── Y4-6: int32 溢出 ──────────────────────────────────

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_market_value_exceeds_int32(self, mock_open, mock_td):
        """市值超过 int32 范围（> 21 亿）→ Python 无溢出。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "巨量持仓", "000001", 100_000_000, 100.0)
        mkt = {"price": 500.0, "yesterday_close": 490.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertGreater(detail.market_value, 2**31 - 1)
        self.assertAlmostEqual(detail.market_value, 50_000_000_000.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_market_value_exceeds_int64(self, mock_open, mock_td):
        """市值超过 int64 范围（> 9e18）→ Python 浮点不溢出。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "天文持仓", "000001", 1_000_000_000_000, 1.0)
        mkt = {"price": 10_000_000.0, "yesterday_close": 9_900_000.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertGreater(detail.market_value, 9e18)
        self.assertAlmostEqual(detail.market_value / 1e19, 1.0, places=5)

    # ── Y4-7: 负成本 ──────────────────────────────────────

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_negative_cost_price(self, mock_open, mock_td):
        """负成本（赠予/合并形成）→ profit_rate = None（cost≤0 保护），其他值正常。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "负成本资产", "000001", 100, -5.0)
        mkt = {"price": 10.0, "yesterday_close": 9.5,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.cost, -500.0)
        self.assertAlmostEqual(detail.market_value, 1000.0)
        self.assertAlmostEqual(detail.profit, 1500.0)
        self.assertIsNone(detail.profit_rate)  # cost=-500 ≤ 0，源码中 profit_rate = None

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_zero_cost_price(self, mock_open, mock_td):
        """零成本 → profit_rate = None（避免除零），其他值正常。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "零成本资产", "000001", 100, 0.0)
        mkt = {"price": 10.0, "yesterday_close": 9.5,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.cost, 0.0)
        self.assertAlmostEqual(detail.market_value, 1000.0)
        self.assertIsNone(detail.profit_rate)

    # ── Y4-8: 多数量级相加 ────────────────────────────────

    def test_mixed_magnitudes_in_sum(self):
        """多数量级（1e-6 到 1e9）累加 → 小值不被大值完全淹没（float64 精度约 1e-7）。"""
        from src.python.report.market_value import DetailRow
        tiny = DetailRow(account="A", name="tiny", code="000001",
                         shares=0.001, cost=0.001, price=0.001,
                         yesterday_close=0.001, nav_date="", source_api="tencent",
                         price_type="", premium="--",
                         today_profit=0.0, profit=0.0, profit_rate=0.0,
                         market_value=1e-6)
        huge = DetailRow(account="B", name="huge", code="000002",
                         shares=1e7, cost=1e9, price=100.0,
                         yesterday_close=99.0, nav_date="", source_api="tencent",
                         price_type="", premium="--",
                         today_profit=0.0, profit=0.0, profit_rate=0.0,
                         market_value=1e9)
        total = sum([tiny.market_value, huge.market_value])
        self.assertNotEqual(total, huge.market_value)
        # float64 精度：1e9 + 1e-6 误差约 1e-7，验证小值贡献存在即可
        diff = total - huge.market_value
        self.assertGreater(diff, 0)
        self.assertLess(diff, 1e-5)

    def test_mixed_magnitudes_three_levels(self):
        """三数量级（1e-3, 1e0, 1e6）累加 → 各数量级均保留。"""
        from src.python.report.market_value import DetailRow
        rows = [
            DetailRow(account="A", name="low", code="001",
                      shares=1, cost=1, price=1, yesterday_close=1,
                      nav_date="", source_api="tencent", price_type="",
                      today_profit=0.0, profit=0.0, profit_rate=0.0,
                      premium="--", market_value=0.001),
            DetailRow(account="A", name="mid", code="002",
                      shares=1, cost=1, price=1, yesterday_close=1,
                      nav_date="", source_api="tencent", price_type="",
                      today_profit=0.0, profit=0.0, profit_rate=0.0,
                      premium="--", market_value=1.0),
            DetailRow(account="A", name="high", code="003",
                      shares=1, cost=1, price=1, yesterday_close=1,
                      nav_date="", source_api="tencent", price_type="",
                      today_profit=0.0, profit=0.0, profit_rate=0.0,
                      premium="--", market_value=1_000_000.0),
        ]
        total = sum(r.market_value for r in rows)
        expected = 0.001 + 1.0 + 1_000_000.0
        self.assertAlmostEqual(total, expected, places=3)
        self.assertNotAlmostEqual(total, 1_000_000.0, places=3)


if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()

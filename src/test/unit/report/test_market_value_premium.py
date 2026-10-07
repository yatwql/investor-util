"""市值核算模块单元测试 — 溢价率与今日盈亏分支。

测试目标：
  - determine_price_type — 行情类型判定
  - generate_details — 明细生成与占位符填充
  - 溢价率计算/写入、今日盈亏（东财非 T 日、腾讯恒定、边界值）
  - 外币计价品种市值（不做汇率折算）

运行：
  pytest src/test/unit/report/test_market_value_premium.py -v
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch


from src.python.core.models import Holding
from src.python.report import market_value as mv
import pytest

# ── 市值明细计算与行情更新状态辅助导入 ────────────
from src.python.report.market_value import (
    _FUND_PREMIUM_PLACEHOLDER,
    _compute_detail_row,
    price_update_status,
)
from src.python.report.holdings_detail_sheet import (
    _detail_to_row_values,
)

from .test_market_value import (
    _mock_is_trading_day,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ═══════════════════════════════════════════════════════════
#  _determine_price_type
# ═══════════════════════════════════════════════════════════


class TestDeterminePriceType(unittest.TestCase):
    """测试 _determine_price_type 取价方式标签生成。

    需要 mock is_market_open 和 get_prev_trading_day。
    """

    def setUp(self):
        self.td = "2026-06-26"  # Friday
        self.prev = "2026-06-25"  # Thursday
        # _count_trading_days_back → _is_trading_day → akshare 交易日历（真实网络）。
        # 用例 mock 了 is_market_open/get_prev_trading_day，但漏 _is_trading_day。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_td.start()
        self.addCleanup(self._patch_td.stop)

    # ── Tencent ───────────────────────────────────────────

    @patch("src.python.report.market_value.is_market_open", return_value=True)
    def test_tencent_intraday(self, _):
        """tencent + 交易时段 → 场内实时价。"""
        result = mv._determine_price_type("tencent", self.td, self.td)
        self.assertEqual(result, "场内实时价")

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    def test_tencent_closed_no_nav_date(self, _, __):
        """tencent + 已收市 + 无净值日期 → 场内收盘价(--)。"""
        with patch("src.python.report.market_value.get_prev_trading_day", return_value=self.prev):
            result = mv._determine_price_type("tencent", "", self.td)
            self.assertEqual(result, "场内收盘价(--)")

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    def test_tencent_closed_nav_today(self, _, __):
        """tencent + 已收市 + nav_date == T → 场内收盘价(T)。"""
        result = mv._determine_price_type("tencent", self.td, self.td)
        self.assertEqual(result, "场内收盘价(T)")

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    def test_tencent_closed_nav_prev(self, _, __):
        """tencent + 已收市 + nav_date == T-1 → 场内收盘价(T-1)。"""
        with patch("src.python.report.market_value.get_prev_trading_day", return_value=self.prev):
            result = mv._determine_price_type("tencent", self.prev, self.td)
            self.assertEqual(result, "场内收盘价(T-1)")

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    def test_tencent_closed_nav_other(self, _, __):
        """tencent + 已收市 + nav_date 为其他日期 → 场内收盘价(date)。"""
        result = mv._determine_price_type("tencent", "2026-06-20", self.td)
        self.assertEqual(result, "场内收盘价(2026-06-20)")

    # ── 午间休市 ──────────────────────────────────────────

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=True)
    def test_tencent_midday_nav_today(self, _, __):
        """tencent + 午间休市 + nav_date == T → 场内午市收盘(T)。"""
        result = mv._determine_price_type("tencent", self.td, self.td)
        self.assertEqual(result, "场内午市收盘(T)")

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=True)
    def test_tencent_midday_nav_prev(self, _, __):
        """tencent + 午间休市 + nav_date == T-1 → 仍为场内收盘价(T-1)。"""
        with patch("src.python.report.market_value.get_prev_trading_day", return_value=self.prev):
            result = mv._determine_price_type("tencent", self.prev, self.td)
            self.assertEqual(result, "场内收盘价(T-1)")

    # ── EastMoney（场外）──────────────────────────────────

    def test_eastmoney_no_nav_date(self):
        """eastmoney + 空 nav_date → 官方净值(--)。"""
        result = mv._determine_price_type("eastmoney", "", self.td)
        self.assertEqual(result, "官方净值(--)")

    def test_eastmoney_nav_today(self):
        """eastmoney + nav_date == T → 官方净值(T)。"""
        result = mv._determine_price_type("eastmoney", self.td, self.td)
        self.assertEqual(result, "官方净值(T)")

    def test_eastmoney_nav_prev(self):
        """eastmoney + nav_date == T-1 → 官方净值(T-1)。"""
        with patch("src.python.report.market_value.get_prev_trading_day", return_value=self.prev):
            result = mv._determine_price_type("eastmoney", self.prev, self.td)
            self.assertEqual(result, "官方净值(T-1)")

    def test_eastmoney_nav_2_days_ago(self):
        """eastmoney + nav_date 2 天前 → 官方净值(T-2)。"""
        result = mv._determine_price_type("eastmoney", "2026-06-24", self.td)
        self.assertEqual(result, "官方净值(T-2)")

    def test_eastmoney_nav_5_days_ago(self):
        """eastmoney + nav_date 5 个交易日前 → 官方净值(T-5)。"""
        result = mv._determine_price_type("eastmoney", "2026-06-18", self.td)
        self.assertEqual(result, "官方净值(T-5)")

    def test_eastmoney_nav_6_days_ago(self):
        """eastmoney + nav_date 6 个交易日前 → 官方净值(date)。"""
        result = mv._determine_price_type("eastmoney", "2026-06-17", self.td)
        self.assertEqual(result, "官方净值(2026-06-17)")

    def test_eastmoney_nav_invalid_format(self):
        """eastmoney + 无效日期格式 → 官方净值(原字符串)（ValueError 分支）。"""
        result = mv._determine_price_type("eastmoney", "invalid-date", self.td)
        self.assertEqual(result, "官方净值(invalid-date)")

    def test_eastmoney_nav_future(self):
        """eastmoney + 未来日期（days_diff < 0）→ 官方净值(T)。"""
        result = mv._determine_price_type("eastmoney", "2026-06-30", self.td)
        self.assertEqual(result, "官方净值(T)")


# ═══════════════════════════════════════════════════════════
#  _generate_details
# ═══════════════════════════════════════════════════════════


class TestGenerateDetails(unittest.TestCase):
    """测试 _generate_details 明细行生成（mock API 调用）。"""

    def setUp(self):
        self.tencent_mock_data = {
            "name": "电池ETF",
            "code": "561910",
            "price": 10.5,
            "yesterday_close": 10.0,
            "price_date": "2026-06-26",
            "source_api": "tencent",
            "source": "腾讯财经",
        }
        # _generate_details → _determine_price_type → _count_trading_days_back
        # → _is_trading_day → akshare 交易日历（真实网络）。用例已 mock
        # get_last_trading_day/is_market_open 等，但漏 _is_trading_day，统一隔离。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_td.start()
        self.addCleanup(self._patch_td.stop)
        self.eastmoney_mock_data = {
            "name": "中欧医疗健康混合",
            "code": "003095",
            "price": 1.5,
            "yesterday_close": 1.48,
            "price_date": "2026-06-26",
            "source_api": "eastmoney",
            "source": "东方财富",
        }

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open")
    @patch("src.python.report.market_value.is_midday_break")
    def test_tencent_asset(self, mock_midday, mock_open, mock_ltd, mock_fetch):
        """Tencent 场内资产：各字段正确赋值，today_profit 按公式计算。"""
        mock_midday.return_value = False
        mock_open.return_value = False
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = self.tencent_mock_data

        h = Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0)
        details = mv._generate_details([h], "2026-06-26")
        self.assertEqual(len(details), 1)

        d = details[0]
        self.assertEqual(d.account, "证券账户")
        self.assertEqual(d.name, "电池ETF")
        self.assertEqual(d.code, "561910")
        self.assertEqual(d.price, 10.5)
        self.assertEqual(d.nav_date, "2026-06-26")
        self.assertEqual(d.yesterday_close, 10.0)
        self.assertEqual(d.source_api, "tencent")
        self.assertEqual(d.source, "腾讯财经")
        # tencent + 已收市 + nav_date==T → "场内收盘价(T)"
        self.assertEqual(d.price_type, "场内收盘价(T)")
        self.assertEqual(d.premium, "--")
        self.assertEqual(d.shares, 1000.0)
        self.assertEqual(d.market_value, 10500.0)  # 10.5 * 1000
        self.assertEqual(d.cost, 1000.0)  # 1.0 * 1000
        self.assertEqual(d.profit, 9500.0)  # 10500 - 1000
        self.assertAlmostEqual(d.profit_rate, 9.5)  # 9500 / 1000
        # today_profit = (10.5 - 10.0) * 1000
        self.assertEqual(d.today_profit, 500.0)

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open")
    def test_eastmoney_asset(self, mock_open, mock_ltd, mock_fetch):
        """EastMoney 场外资产：字段正确赋值。"""
        mock_open.return_value = False
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = self.eastmoney_mock_data

        h = Holding("支付宝", "中欧医疗健康混合", "003095", 500.0, 2.0)
        details = mv._generate_details([h], "2026-06-26")
        self.assertEqual(len(details), 1)

        d = details[0]
        self.assertEqual(d.account, "支付宝")
        self.assertEqual(d.source_api, "eastmoney")
        # eastmoney + nav_date==T → "官方净值(T)"
        self.assertEqual(d.price_type, "官方净值(T)")
        self.assertEqual(d.cost, 1000.0)  # 2.0 * 500
        self.assertEqual(d.market_value, 750.0)  # 1.5 * 500
        self.assertEqual(d.profit, -250.0)  # 750 - 1000
        # nav_date == T → today_profit = (1.5 - 1.48) * 500
        self.assertEqual(d.today_profit, 10.0)

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    def test_eastmoney_stale_nav(self, mock_ltd, mock_fetch):
        """East Money + nav_date 过期 → today_profit 为 0。"""
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = {
            "name": "中欧医疗健康混合",
            "code": "003095",
            "price": 1.5,
            "yesterday_close": 1.48,
            "price_date": "2026-06-20",  # 6 天前，过期数据
            "source_api": "eastmoney",
            "source": "东方财富",
        }

        h = Holding("支付宝", "中欧医疗健康混合", "003095", 100.0, 1.0)
        details = mv._generate_details([h], "2026-06-26")
        self.assertEqual(details[0].today_profit, 0.0)
        # price_type 也是 T-6 对应的格式
        self.assertEqual(details[0].price_type, "官方净值(2026-06-20)")

    @patch("src.python.report.market_value.fetch_market_data")
    def test_fetch_returns_none(self, mock_fetch):
        """API 返回 None → 默认值填充，日志告警。"""
        mock_fetch.return_value = None

        h = Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0)
        details = mv._generate_details([h], "2026-06-26")
        self.assertEqual(len(details), 1)

        d = details[0]
        self.assertEqual(d.price, 0.0)
        self.assertEqual(d.yesterday_close, 0.0)
        self.assertEqual(d.nav_date, "")
        self.assertEqual(d.source, "无数据")
        self.assertEqual(d.source_api, "")
        self.assertEqual(d.price_type, "暂无行情")
        self.assertEqual(d.today_profit, 0.0)

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open")
    def test_multiple_holdings(self, mock_open, mock_ltd, mock_fetch):
        """多个持仓 → 返回多条明细。"""
        mock_open.return_value = False
        mock_ltd.return_value = "2026-06-26"

        def side_effect(code, name=""):
            if code == "561910":
                return self.tencent_mock_data
            elif code == "003095":
                return self.eastmoney_mock_data
            return None

        mock_fetch.side_effect = side_effect

        holdings = [
            Holding("证券账户", "电池ETF", "561910", 100.0, 1.0),
            Holding("支付宝", "中欧医疗健康混合", "003095", 200.0, 1.0),
        ]
        details = mv._generate_details(holdings, "2026-06-26")
        self.assertEqual(len(details), 2)
        self.assertEqual(details[0].source_api, "tencent")
        self.assertEqual(details[1].source_api, "eastmoney")

    @patch("src.python.report.market_value.fetch_market_data")
    def test_empty_holdings(self, mock_fetch):
        """空持仓列表 → 返回空列表。"""
        details = mv._generate_details([], "2026-06-26")
        self.assertEqual(details, [])

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open")
    def test_today_str_none(self, mock_open, mock_ltd, mock_fetch):
        """today_str 为空（默认取当天）→ 不报错。"""
        mock_open.return_value = False
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = self.tencent_mock_data

        h = Holding("证券账户", "电池ETF", "561910", 100.0, 1.0)
        # 传入空字符串，函数内部回退到 datetime.now()
        with patch("src.python.report.market_value.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 26, 15, 30, 0)
            details = mv._generate_details([h], "")
        self.assertEqual(len(details), 1)

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open")
    def test_account_strip(self, mock_open, mock_ltd, mock_fetch):
        """账户名前后空格被清理。"""
        mock_open.return_value = False
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = self.tencent_mock_data

        h = Holding("  证券账户  ", "电池ETF", "561910", 100.0, 1.0)
        details = mv._generate_details([h], "2026-06-26")
        self.assertEqual(details[0].account, "证券账户")

    # ── 场外基金本日盈亏 ────────────
    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    def test_eastmoney_nav_t_minus_1_today_profit_zero(self, mock_ltd, mock_fetch):
        """场外基金净值日期为 T-1（今日净值未出）→ 本日盈亏为 0。"""
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = {
            "name": "中欧医疗健康混合",
            "code": "003095",
            "price": 1.5,
            "yesterday_close": 1.48,
            "price_date": "2026-06-25",  # T-1（周四）
            "source_api": "eastmoney",
            "source": "东方财富",
        }
        h = Holding("支付宝", "中欧医疗健康混合", "003095", 500.0, 2.0)
        details = mv._generate_details([h], "2026-06-26")
        self.assertEqual(details[0].today_profit, 0.0)
        # price_type 仍应为 T-1
        self.assertEqual(details[0].price_type, "官方净值(T-1)")

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    def test_eastmoney_nav_t_minus_2_price_type(self, mock_ltd, mock_fetch):
        """场外基金净值日期为 T-2（如 6/25 → T=6/29 周一）→ 显示官方净值(T-2)。"""
        mock_ltd.return_value = "2026-06-29"
        mock_fetch.return_value = {
            "name": "016055",
            "code": "016055",
            "price": 1.2,
            "yesterday_close": 1.18,
            "price_date": "2026-06-25",  # T-2（周四）
            "source_api": "eastmoney",
            "source": "东方财富",
        }
        h = Holding("基金账户", "016055", "016055", 1000.0, 1.0)
        details = mv._generate_details([h], "2026-06-29")
        self.assertEqual(details[0].price_type, "官方净值(T-2)")
        # 今日净值未出 → 本日盈亏为 0
        self.assertEqual(details[0].today_profit, 0.0)

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    def test_eastmoney_nav_today_today_profit_computed(self, mock_ltd, mock_fetch):
        """场外基金净值日期等于交易日（T）→ 本日盈亏正常计算。"""
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = {
            "name": "中欧医疗健康混合",
            "code": "003095",
            "price": 1.5,
            "yesterday_close": 1.48,
            "price_date": "2026-06-26",  # T（周五）
            "source_api": "eastmoney",
            "source": "东方财富",
        }
        h = Holding("支付宝", "中欧医疗健康混合", "003095", 500.0, 2.0)
        details = mv._generate_details([h], "2026-06-26")
        self.assertEqual(details[0].today_profit, 10.0)
        self.assertEqual(details[0].price_type, "官方净值(T)")


# ═══════════════════════════════════════════════════════════════
#  溢价率计算验证


# ═══════════════════════════════════════════════════════════════
#  溢价率计算验证
# ═══════════════════════════════════════════════════════════════


class TestPremiumRate(unittest.TestCase):
    """验证溢价率字段的处理。

    当前实现：溢价率使用占位符 "--"（简化处理，不考虑实时溢价）。
    测试确保：
      - 占位符正确填充
      - 不出现报错
      - 溢价率列始终为字符串类型
    """

    def setUp(self) -> None:
        # _compute_detail_row → _determine_price_type → _is_trading_day（akshare
        # 网络）+ is_market_open/is_midday_break（东方财富 push2 HTTP）。统一隔离。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_open = patch("src.python.report.market_value.is_market_open", return_value=False)
        self._patch_midday = patch("src.python.report.market_value.is_midday_break", return_value=False)
        self._patch_td.start()
        self._patch_open.start()
        self._patch_midday.start()
        self.addCleanup(self._patch_td.stop)
        self.addCleanup(self._patch_open.stop)
        self.addCleanup(self._patch_midday.stop)

    def test_premium_placeholder_in_detail_row(self):
        """不在交易时段或不是 tencent 源 → premium=--。"""
        from src.python.report.market_value import (
            _compute_detail_row,
            _FUND_PREMIUM_PLACEHOLDER,
        )
        from src.python.core.models import Holding

        h = Holding(account="证券", name="华夏纳斯达克100ETF(QDII)", code="513300", shares=100, cost_price=1.5)
        mkt = {
            "price": 1.6,
            "yesterday_close": 1.55,
            "price_date": "2026-06-26",
            "source": "腾讯财经",
            "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.premium, _FUND_PREMIUM_PLACEHOLDER)

    def test_premium_type_is_string(self):
        """溢价率字段始终为字符串类型。"""
        from src.python.report.market_value import (
            _compute_detail_row,
        )
        from src.python.core.models import Holding

        h = Holding(account="证券", name="沪深300ETF", code="510300", shares=100, cost_price=4.0)
        mkt = {
            "price": 4.2,
            "yesterday_close": 4.1,
            "price_date": "",
            "source": "东方财富",
            "source_api": "eastmoney",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertIsInstance(detail.premium, str)

    def test_premium_in_row_values(self):
        """detail_to_row_values 中溢价率列索引正确。"""
        from src.python.report.market_value import DetailRow
        from src.python.report.holdings_detail_sheet import (
            _detail_to_row_values,
        )

        d = DetailRow(
            account="证券",
            name="测试",
            code="600000",
            premium="--",
        )
        values = _detail_to_row_values(d)
        # 溢价率是第 8 列（0-indexed）
        self.assertEqual(values[7], "--")

    def test_premium_not_none(self):
        """溢价率不应为 None（避免 Excel 单元格显示空白）。"""
        from src.python.report.market_value import (
            _compute_detail_row,
        )
        from src.python.core.models import Holding

        h = Holding(account="证券", name="普通股票", code="600000", shares=100, cost_price=10.0)
        mkt = {
            "price": 11.0,
            "yesterday_close": 10.5,
            "price_date": "2026-06-26",
            "source": "腾讯财经",
            "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertIsNotNone(detail.premium)
        self.assertNotEqual(detail.premium, "")


# ═══════════════════════════════════════════════════════════════
#  场外基金非 T 日 today_profit=0 验证
# ═══════════════════════════════════════════════════════════════


class TestTodayProfitOffMarket(unittest.TestCase):
    """验证场外基金在非 T 日（nav_date ≠ trading_day）时 today_profit=0。"""

    def setUp(self):
        # 固定交易日为 "2026-06-26"
        self._ld_patcher = unittest.mock.patch(
            "src.python.report.market_value.get_last_trading_day",
            return_value="2026-06-26",
        )
        self._ld_patcher.start()
        # _compute_detail_row → _determine_price_type → _is_trading_day → akshare 交易日历。
        self._td_patcher = unittest.mock.patch(
            "src.python.core.trading_calendar._is_trading_day",
            side_effect=_mock_is_trading_day,
        )
        self._td_patcher.start()

    def tearDown(self):
        self._td_patcher.stop()
        self._ld_patcher.stop()

    def test_off_market_nav_not_t_day(self):
        """场外基金 nav_date != trading_day → today_profit=0。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.core.models import Holding

        h = Holding(account="支付宝", name="易方达蓝筹精选", code="005827", shares=1000, cost_price=2.0)
        mkt = {
            "price": 2.1,
            "yesterday_close": 2.05,
            "price_date": "2026-06-24",  # ≠ 2026-06-26（非 T 日）
            "source": "天天基金",
            "source_api": "tiantian",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)

    def test_on_market_nav_is_t_day(self):
        """场外基金 nav_date == trading_day → today_profit 正常计算。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.core.models import Holding

        h = Holding(account="支付宝", name="易方达蓝筹精选", code="005827", shares=1000, cost_price=2.0)
        mkt = {
            "price": 2.1,
            "yesterday_close": 2.05,
            "price_date": "2026-06-26",  # == trading_day
            "source": "天天基金",
            "source_api": "tiantian",
        }
        detail = _compute_detail_row(h, mkt)
        # today_profit = (2.1 - 2.05) * 1000 = 50.0
        self.assertAlmostEqual(detail.today_profit, 50.0)

    def test_tencent_source_ignores_nav_date(self):
        """腾讯源（场内实时）即使无 nav_date 也计算 today_profit。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.core.models import Holding

        h = Holding(account="证券", name="长江电力", code="600900", shares=100, cost_price=20.0)
        mkt = {
            "price": 21.0,
            "yesterday_close": 20.5,
            "price_date": "",  # 腾讯源无净值日期
            "source": "腾讯财经",
            "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        # tencent 源始终用 price - yclose 计算 today_profit
        self.assertAlmostEqual(detail.today_profit, 50.0)

    def test_no_nav_date_non_tencent(self):
        """非腾讯源且无 nav_date → today_profit=0。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.core.models import Holding

        h = Holding(account="支付宝", name="某基金", code="000001", shares=100, cost_price=1.0)
        mkt = {
            "price": 1.1,
            "yesterday_close": 1.05,
            "price_date": "",
            "source": "天天基金",
            "source_api": "tiantian",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)


# ═══════════════════════════════════════════════════════════════
#  以下为市值明细非 edge 场景测试
# ═══════════════════════════════════════════════════════════════


class TestPremiumPlaceholder(unittest.TestCase):
    """溢价率始终为占位符 '--'。"""

    def setUp(self) -> None:
        # _compute_detail_row → _determine_price_type → _is_trading_day → akshare 交易日历。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_td.start()
        self.addCleanup(self._patch_td.stop)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    def test_tencent_premium_placeholder(self, mock_midday, mock_open, mock_td):
        """Tencent 场内资产 → premium = '--'。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 100, 10.0)
        mkt = {
            "price": 25.0,
            "yesterday_close": 24.5,
            "price_date": "2026-06-30",
            "source": "腾讯财经",
            "source_api": "tencent",
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
            "price": 2.1,
            "yesterday_close": 2.0,
            "price_date": "2026-06-30",
            "source": "天天基金",
            "source_api": "eastmoney",
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
            "price": 2050.0,
            "yesterday_close": 2000.0,
            "price_date": "2026-06-30",
            "source": "腾讯财经",
            "source_api": "tencent",
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
            {
                "price": 25.0,
                "yesterday_close": 24.5,
                "price_date": "2026-06-30",
                "source": "腾讯财经",
                "source_api": "tencent",
            },
            {
                "price": 2.1,
                "yesterday_close": 2.0,
                "price_date": "2026-06-25",
                "source": "天天基金",
                "source_api": "eastmoney",
            },
        ]

        for h, m in zip(holdings, mkts):
            detail = _compute_detail_row(h, m)
            self.assertEqual(detail.premium, "--")

    def test_premium_placeholder_constant(self):
        """_FUND_PREMIUM_PLACEHOLDER 常量值为 '--'。"""
        self.assertEqual(_FUND_PREMIUM_PLACEHOLDER, "--")


class TestTodayProfitEastMoneyNonTDay(unittest.TestCase):
    """场外基金非 T 日 → today_profit = 0。"""

    def setUp(self) -> None:
        # _compute_detail_row → _determine_price_type → _is_trading_day → akshare 交易日历。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_td.start()
        self.addCleanup(self._patch_td.stop)

    def _make_market_data(self, nav_date: str, source_api: str = "eastmoney") -> dict:
        return {
            "price": 2.5,
            "yesterday_close": 2.4,
            "price_date": nav_date,
            "source": "天天基金",
            "source_api": source_api,
        }

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_non_t_day_eastmoney(self, mock_open, mock_td):
        """Eastmoney, nav_date != trading_day → today_profit = 0。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0)
        mkt = self._make_market_data("2026-06-23")
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_t_day_eastmoney_calculates(self, mock_open, mock_td):
        """Eastmoney, nav_date == trading_day → today_profit > 0。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0)
        mkt = self._make_market_data("2026-06-30")
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

    def setUp(self) -> None:
        # _compute_detail_row → _determine_price_type → _is_trading_day（akshare 网络）
        # + is_market_open/is_midday_break（东方财富 push2 HTTP）。统一隔离。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_open = patch("src.python.report.market_value.is_market_open", return_value=False)
        self._patch_midday = patch("src.python.report.market_value.is_midday_break", return_value=False)
        self._patch_td.start()
        self._patch_open.start()
        self._patch_midday.start()
        self.addCleanup(self._patch_td.stop)
        self.addCleanup(self._patch_open.stop)
        self.addCleanup(self._patch_midday.stop)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_tencent_always_calculates(self, mock_open, mock_td):
        """Tencent 无论 nav_date 是什么 → today_profit 始终计算。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 200, 10.0)
        mkt = {
            "price": 28.5,
            "yesterday_close": 28.0,
            "price_date": "2026-06-25",
            "source": "腾讯财经",
            "source_api": "tencent",
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
            "price": 25.5,
            "yesterday_close": 25.0,
            "price_date": "",
            "source": "腾讯财经",
            "source_api": "tencent",
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
            "price": 1.8,
            "yesterday_close": 1.75,
            "price_date": "2026-06-27",
            "source": "腾讯财经",
            "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        expected = round((1.8 - 1.75) * 300, 2)
        self.assertEqual(detail.today_profit, expected)


class TestTodayProfitEdgeCases(unittest.TestCase):
    """today_profit 边界场景。"""

    def setUp(self) -> None:
        # _compute_detail_row → _determine_price_type → _is_trading_day → akshare 交易日历。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_td.start()
        self.addCleanup(self._patch_td.stop)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_no_price_data(self, mock_open, mock_td):
        """获取行情失败（price=0）→ today_profit = 0。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("支付宝", "易方达蓝筹", "005827", 100, 2.0)
        mkt = {
            "price": 0.0,
            "yesterday_close": 0.0,
            "price_date": "",
            "source": "--",
            "source_api": "",
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
            "price": 24.0,
            "yesterday_close": 25.0,
            "price_date": "2026-06-30",
            "source": "腾讯财经",
            "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        expected = round((24.0 - 25.0) * 100, 2)
        self.assertEqual(detail.today_profit, expected)
        self.assertLess(detail.today_profit, 0)


class TestPremiumInWriteSheet(unittest.TestCase):
    """验证 premium 在写入页签时的列值。"""

    def setUp(self) -> None:
        # _compute_detail_row → _determine_price_type → _is_trading_day → akshare 交易日历。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_td.start()
        self.addCleanup(self._patch_td.stop)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_premium_in_excel_row(self, mock_open, mock_td):
        """写入 Excel 行时溢价率列为 '--'。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 100, 10.0)
        mkt = {
            "price": 25.0,
            "yesterday_close": 24.5,
            "price_date": "2026-06-30",
            "source": "腾讯财经",
            "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        values = _detail_to_row_values(detail)
        self.assertEqual(values[7], "--")


class TestForeignDenominatedMarketValue(unittest.TestCase):
    """非人民币计价品种市值核算 — QDII/港股通份额按价格 × 份额直接计市值（不做汇率折算）。"""

    def setUp(self) -> None:
        # _compute_detail_row → _determine_price_type → _count_trading_days_back
        # → _is_trading_day → akshare 交易日历（真实网络）。这些用例已 mock
        # get_last_trading_day/is_market_open，但漏 _is_trading_day，补上以
        # 隔离 akshare 网络调用。
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_td.start()
        self.addCleanup(self._patch_td.stop)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_qdii_price_in_rmb_from_api(self, mock_open, mock_td):
        """QDII 价格来自 API（已为人民币计值），市值计算正确。"""
        mock_td.return_value = "2026-07-01"
        h = Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0)
        mkt = {
            "price": 2.1,
            "yesterday_close": 2.0,
            "price_date": "2026-07-01",
            "source": "天天基金",
            "source_api": "eastmoney",
            "nav_date": "2026-07-01",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.market_value, 210.0, delta=0.01)
        self.assertAlmostEqual(detail.today_profit, 10.0, delta=0.01)

    @patch("src.python.report.market_value.get_last_trading_day")
    def test_qdii_today_profit_t1(self, mock_td):
        """QDII 净值日期=T-1 → today_profit=0（当前行为，待扩展）。"""
        mock_td.return_value = "2026-07-01"
        h = Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0)
        mkt = {
            "price": 2.1,
            "yesterday_close": 2.0,
            "price_date": "2026-06-30",
            "source": "天天基金",
            "source_api": "eastmoney",
            "nav_date": "2026-06-30",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    def test_price_update_status_qdii_t1_updated(self, mock_td):
        """price_update_status 正确识别 QDII T-1 为已更新。"""
        mock_td.return_value = "2026-07-01"
        h = Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0)
        mkt = {
            "price": 2.1,
            "yesterday_close": 2.0,
            "price_date": "2026-06-30",
            "source": "天天基金",
            "source_api": "eastmoney",
            "nav_date": "2026-06-30",
        }
        detail = _compute_detail_row(h, mkt)
        updated, total, all_updated = price_update_status([detail], "2026-07-01")
        self.assertEqual(updated, 1)
        self.assertEqual(total, 1)
        self.assertTrue(all_updated)


if __name__ == "__main__":
    unittest.main()

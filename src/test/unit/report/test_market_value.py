"""市值核算模块单元测试。

测试目标：
  - is_qdii_by_name / is_etf_by_name — 基金类型识别（委派 code_utils）
  - _date_within_days   — 日期范围判断
  - classify_holdings   — 持仓分类逻辑
  - price_update_status — 价格更新状态检测
  - is_market_open      — A 股交易时段判断
  - get_last_trading_day / get_prev_trading_day — 交易日计算
  - _determine_price_type — 取价方式标签生成
  - _generate_details   — 明细行生成（mock API）
  - 溢价率/场外基金 today_profit 等业务场景

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_market_value -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, call, patch

from openpyxl import Workbook

from src.python.core.models import Holding
from src.python.report import market_value as mv
from src.python.report.styles import BLUE_FONT
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ── 市值明细计算与行情更新状态辅助导入 ────────────
from src.python.report.market_value import (
    _FUND_PREMIUM_PLACEHOLDER,
    _compute_detail_row,
    price_update_status,
)
from src.python.report.market_value_sheet import (
    _detail_to_row_values,
)



# ═══════════════════════════════════════════════════════════
#  is_qdii_by_name（委派 code_utils）
# ═══════════════════════════════════════════════════════════


class TestIsQdii(unittest.TestCase):
    """测试 is_qdii_by_name 名称含 QDII 判断。"""

    def test_qdii_in_name(self):
        """名称含 QDII → True。"""
        from src.python.core.code_utils import is_qdii_by_name
        self.assertTrue(is_qdii_by_name("华夏纳斯达克100ETF(QDII)"))

    def test_qdii_lowercase(self):
        """名称含小写 qdii → True（大小写不敏感）。"""
        from src.python.core.code_utils import is_qdii_by_name
        self.assertTrue(is_qdii_by_name("华夏纳斯达克100ETF(qdii)"))

    def test_qdii_mixed_case(self):
        """名称含混合大小写 QdIi → True。"""
        from src.python.core.code_utils import is_qdii_by_name
        self.assertTrue(is_qdii_by_name("测试(QdIi)"))

    def test_non_qdii(self):
        """不含 QDII → False。"""
        from src.python.core.code_utils import is_qdii_by_name
        self.assertFalse(is_qdii_by_name("电池ETF"))

    def test_empty_string(self):
        """空字符串 → False。"""
        from src.python.core.code_utils import is_qdii_by_name
        self.assertFalse(is_qdii_by_name(""))

    def test_no_market_value_keyword(self):
        """含有其他相似关键词但不含 QDII → False。"""
        from src.python.core.code_utils import is_qdii_by_name
        self.assertFalse(is_qdii_by_name("QD股票基金"))

    def test_non_etf(self):
        """不含 ETF → False（通过 _etf_by_name 委派 code_utils）。"""
        from src.python.core.code_utils import is_etf_by_name
        self.assertFalse(is_etf_by_name("长江电力"))

    def test_empty_string(self):
        """空字符串 → False。"""
        from src.python.core.code_utils import is_etf_by_name
        self.assertFalse(is_etf_by_name(""))


# ═══════════════════════════════════════════════════════════
#  classify_holdings
# ═══════════════════════════════════════════════════════════


class TestClassifyHoldings(unittest.TestCase):
    """测试 classify_holdings 按类型分类持仓。"""

    def _h(self, name: str, code: str = "", account: str = "证券账户") -> Holding:
        return Holding(
            account=account, name=name, code=code,
            shares=1.0, cost_price=1.0,
        )

    # ── QDII ─────────────────────────────────────────────

    def test_qdii_in_name(self):
        """名称含 QDII → QDII。"""
        h = self._h("华夏纳斯达克100ETF(QDII)", "513300")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["QDII"]), 1)
        self.assertEqual(result["QDII"][0], h)

    def test_qdii_lowercase(self):
        """名称含小写 qdii → QDII（大小写不敏感）。"""
        h = self._h("易方达标普500(Qdii)", "161125")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["QDII"]), 1)

    # ── 场外渠道 ─────────────────────────────────────────

    def test_fund_account(self):
        """基金账户 → 国内场外。"""
        h = self._h("某混合基金", "002943", "基金账户")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["国内场外"]), 1)

    def test_alipay_account(self):
        """支付宝账户 → 国内场外。"""
        h = self._h("中欧医疗健康混合", "003095", "支付宝")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["国内场外"]), 1)

    def test_wechat_account(self):
        """微信账户 → 国内场外。"""
        h = self._h("易方达蓝筹精选", "005827", "微信理财")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["国内场外"]), 1)

    def test_bank_account(self):
        """银行账户 → 国内场外。"""
        h = self._h("某稳健增长", "001234", "银行")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["国内场外"]), 1)

    # ── 场内 ETF ─────────────────────────────────────────

    def test_etf_in_name(self):
        """名称含 ETF → 场内ETF。"""
        h = self._h("电池ETF", "561910")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["场内ETF"]), 1)

    def test_code_starts_with_5(self):
        """代码 5 开头 → 场内ETF。"""
        h = self._h("黄金ETF", "518880")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["场内ETF"]), 1)

    def test_code_starts_with_1(self):
        """代码 1 开头 → 场内ETF。"""
        h = self._h("某转债", "110059")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["场内ETF"]), 1)

    # ── 场内股票 ─────────────────────────────────────────

    def test_stock_code_6(self):
        """代码 6 开头 → 场内股票。"""
        h = self._h("长江电力", "600900")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["场内股票"]), 1)

    def test_stock_code_0(self):
        """代码 0 开头 → 场内股票。"""
        h = self._h("平安银行", "000001")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["场内股票"]), 1)

    def test_stock_code_3(self):
        """代码 3 开头 → 场内股票。"""
        h = self._h("宁德时代", "300750")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["场内股票"]), 1)

    # ── 兜底 ─────────────────────────────────────────────

    def test_other_code_falls_back(self):
        """其余（非 A 股/ETF 前缀）→ 国内场外。"""
        h = self._h("某基金", "400000")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["国内场外"]), 1)

    # ── 优先级：QDII > 场外渠道 > ETF > 股票 > 兜底 ────

    def test_qdii_priority_over_fund_account(self):
        """QDII 优先级高于场外渠道。"""
        h = self._h("标普500ETF(QDII)", "161125", "支付宝")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["QDII"]), 1)

    def test_account_priority_over_code(self):
        """场外渠道账户优先级高于代码匹配。"""
        h = self._h("某基金", "600900", "支付宝")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["国内场外"]), 1)

    def test_qdii_priority_over_etf(self):
        """QDII 优先级高于 ETF 名称匹配。"""
        h = self._h("恒生ETF(QDII)", "159920")
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["QDII"]), 1)

    # ── 边缘情况 ─────────────────────────────────────────

    def test_empty_holdings(self):
        """空列表 → 所有分类为空。"""
        result = mv.classify_holdings([])
        for cat in result.values():
            self.assertEqual(len(cat), 0)

    def test_whitespace_stripped(self):
        """持仓名称/代码/账户的空格被清理。"""
        h = Holding(account="  证券账户  ", name="  电池ETF  ", code="  561910  ",
                    shares=1.0, cost_price=1.0)
        result = mv.classify_holdings([h])
        self.assertEqual(len(result["场内ETF"]), 1)

    def test_mixed_holdings(self):
        """多种类型混合分类正确。"""
        holdings = [
            self._h("电池ETF", "561910"),
            self._h("长江电力", "600900"),
            self._h("华夏纳斯达克100ETF(QDII)", "513300"),
            self._h("中欧医疗健康混合", "003095", "支付宝"),
        ]
        result = mv.classify_holdings(holdings)
        self.assertEqual(len(result["QDII"]), 1)
        self.assertEqual(len(result["场内ETF"]), 1)
        self.assertEqual(len(result["场内股票"]), 1)
        self.assertEqual(len(result["国内场外"]), 1)


# ═══════════════════════════════════════════════════════════
#  price_update_status
# ═══════════════════════════════════════════════════════════


class TestPriceUpdateStatus(unittest.TestCase):
    """测试 price_update_status 价格更新状态检测。"""

    def _row(self, source_api: str, nav_date: str, name: str = "") -> mv.DetailRow:
        return mv.DetailRow(
            source_api=source_api, nav_date=nav_date, name=name,
        )

    # ── Tencent（场内）────────────────────────────────────

    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_tencent_updated(self, mock_open, mock_midday):
        """tencent + nav_date == trading_day + 已收市 → 已更新。"""
        d = self._row("tencent", "2026-06-26")
        updated, total, all_ok = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 1)
        self.assertEqual(total, 1)
        self.assertTrue(all_ok)

    def test_tencent_not_updated(self):
        """tencent + nav_date != trading_day → 未更新。"""
        d = self._row("tencent", "2026-06-25")
        updated, total, all_ok = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 0)
        self.assertEqual(total, 1)
        self.assertFalse(all_ok)

    def test_tencent_empty_nav_date(self):
        """tencent + 空 nav_date → 未更新。"""
        d = self._row("tencent", "")
        updated, _, _ = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 0)

    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    @patch("src.python.report.market_value.is_market_open", return_value=True)
    def test_tencent_during_market_hours_not_updated(self, mock_open, mock_midday):
        """tencent + nav_date == trading_day + 交易时段 → 未更新（只有实时价，无收市价）。"""
        d = self._row("tencent", "2026-06-26")
        updated, total, all_ok = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 0)
        self.assertEqual(total, 1)
        self.assertFalse(all_ok)

    # ── EastMoney + QDII ────────────────────────────────

    def test_eastmoney_qdii_equal_trading_day(self):
        """eastmoney + QDII + nav_date == trading_day(T) → 已更新。"""
        d = self._row("eastmoney", "2026-06-26", name="标普500(QDII)")
        updated, _, _ = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 1)

    def test_eastmoney_qdii_equal_prev_trading_day(self):
        """eastmoney + QDII + nav_date == prev_trading_day(T-1) → 已更新。"""
        d = self._row("eastmoney", "2026-06-25", name="标普500(QDII)")
        updated, _, _ = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 1)

    def test_eastmoney_qdii_old_date(self):
        """eastmoney + QDII + nav_date 早于 T-1 → 未更新。"""
        d = self._row("eastmoney", "2026-06-24", name="标普500(QDII)")
        updated, _, _ = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 0)

    def test_eastmoney_qdii_empty_nav_date(self):
        """eastmoney + QDII + 空 nav_date → 未更新。"""
        d = self._row("eastmoney", "", name="标普500(QDII)")
        updated, _, _ = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 0)

    # ── EastMoney + 非 QDII（国内场外）────────────────────

    def test_eastmoney_domestic_equal_trading_day(self):
        """eastmoney + 非 QDII + nav_date == trading_day → 已更新。"""
        d = self._row("eastmoney", "2026-06-26", name="中欧医疗健康混合")
        updated, _, _ = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 1)

    def test_eastmoney_domestic_equal_prev_trading_day(self):
        """eastmoney + 非 QDII + nav_date == prev_trading_day(T-1) → 不计入（仅 T 算已更新）。"""
        # 周三交易日，周二为前一日
        d = self._row("eastmoney", "2026-06-23", name="中欧医疗健康混合")
        updated, _, _ = mv.price_update_status([d], "2026-06-24")
        self.assertEqual(updated, 0)

    def test_eastmoney_domestic_neither(self):
        """eastmoney + 非 QDII + nav_date 不是 T 也不是 T-1 → 未更新。"""
        d = self._row("eastmoney", "2026-06-22", name="中欧医疗健康混合")
        updated, _, _ = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 0)

    # ── 混合场景 ───────────────────────────────────────────

    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_mixed_status(self, mock_open, mock_midday):
        """部分更新 → all_ok 为 False。"""
        details = [
            self._row("tencent", "2026-06-26"),        # 已更新（已收市）
            self._row("tencent", "2026-06-25"),          # 未更新
            self._row("eastmoney", "2026-06-26", name="某基金"),  # 已更新
        ]
        updated, total, all_ok = mv.price_update_status(details, "2026-06-26")
        self.assertEqual(updated, 2)
        self.assertEqual(total, 3)
        self.assertFalse(all_ok)

    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_all_updated(self, mock_open, mock_midday):
        """全部已更新 → all_ok 为 True。"""
        details = [
            self._row("tencent", "2026-06-26"),
            self._row("eastmoney", "2026-06-26", name="某基金"),
        ]
        _, _, all_ok = mv.price_update_status(details, "2026-06-26")
        self.assertTrue(all_ok)

    def test_all_not_updated(self):
        """全部未更新 → all_ok 为 False。"""
        details = [
            self._row("tencent", "2026-06-25"),
            self._row("tencent", "2026-06-24"),
        ]
        _, _, all_ok = mv.price_update_status(details, "2026-06-26")
        self.assertFalse(all_ok)

    def test_empty_list(self):
        """空列表 → (0, 0, True)。"""
        updated, total, all_ok = mv.price_update_status([], "2026-06-26")
        self.assertEqual(updated, 0)
        self.assertEqual(total, 0)
        self.assertTrue(all_ok)

    def test_unknown_source_api_ignored(self):
        """未知 source_api → 不计入已更新。"""
        d = self._row("unknown_api", "2026-06-26")
        updated, total, _ = mv.price_update_status([d], "2026-06-26")
        self.assertEqual(updated, 0)
        self.assertEqual(total, 1)


# ═══════════════════════════════════════════════════════════
#  is_market_open
# ═══════════════════════════════════════════════════════════


class TestIsMarketOpen(unittest.TestCase):
    """测试 is_market_open A 股交易时段判断（mock datetime.now）。"""

    @patch("src.python.core.market_hours.datetime")
    def test_weekend_saturday(self, mock_dt):
        """周六 → False。"""
        mock_dt.now.return_value = datetime(2026, 6, 27, 10, 0, 0)  # Saturday
        self.assertFalse(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_weekend_sunday(self, mock_dt):
        """周日 → False。"""
        mock_dt.now.return_value = datetime(2026, 6, 28, 10, 0, 0)  # Sunday
        self.assertFalse(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_before_open(self, mock_dt):
        """周一 9:00（开盘前）→ False。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 9, 0, 0)  # Mon
        self.assertFalse(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_morning_session(self, mock_dt):
        """周一 10:00（上午交易时段）→ True。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 10, 0, 0)
        self.assertTrue(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_morning_open_boundary(self, mock_dt):
        """周一 9:30（开盘边界）→ True。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 9, 30, 0)
        self.assertTrue(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_morning_close_boundary(self, mock_dt):
        """周一 11:30（午休边界）→ True。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 11, 30, 0)
        self.assertTrue(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_lunch_break(self, mock_dt):
        """周一 12:00（午休）→ False。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 12, 0, 0)
        self.assertFalse(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_afternoon_session(self, mock_dt):
        """周一 14:00（下午交易时段）→ True。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 14, 0, 0)
        self.assertTrue(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_afternoon_open_boundary(self, mock_dt):
        """周一 13:00（下午开盘边界）→ True。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 13, 0, 0)
        self.assertTrue(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_afternoon_close_boundary(self, mock_dt):
        """周一 15:00（收盘边界）→ True。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 15, 0, 0)
        self.assertTrue(mv.is_market_open())

    @patch("src.python.core.market_hours.datetime")
    def test_after_close(self, mock_dt):
        """周一 15:30（收盘后）→ False。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 15, 30, 0)
        self.assertFalse(mv.is_market_open())


# ═══════════════════════════════════════════════════════════
#  get_last_trading_day
# ═══════════════════════════════════════════════════════════


def _mock_calendar() -> set[str]:
    """模拟交易日历：周一到周五，排除 2026-06-19（端午节）。"""
    return {
        "2026-06-18", "2026-06-22", "2026-06-23", "2026-06-24",
        "2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30",
    }


class TestGetLastTradingDay(unittest.TestCase):
    """测试 get_last_trading_day 最近交易日计算（mock datetime.now + 交易日历）。"""

    def _mock_td(self, d):
        return d.strftime("%Y-%m-%d") in _mock_calendar()

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_saturday(self, mock_dt, mock_td):
        """周六 → 上周五。"""
        mock_dt.now.return_value = datetime(2026, 6, 27, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_sunday(self, mock_dt, mock_td):
        """周日 → 上周五。"""
        mock_dt.now.return_value = datetime(2026, 6, 28, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_monday_after_open(self, mock_dt, mock_td):
        """周一 10:00（已开盘）→ 当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 29, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-29")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_monday_before_open(self, mock_dt, mock_td):
        """周一 02:35（盘前）→ 上周五。"""
        mock_dt.now.return_value = datetime(2026, 6, 29, 2, 35, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_monday_early_morning(self, mock_dt, mock_td):
        """周一 9:00（盘前）→ 上周五。"""
        mock_dt.now.return_value = datetime(2026, 6, 29, 9, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_monday_at_open(self, mock_dt, mock_td):
        """周一 9:30（开盘）→ 当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 29, 9, 30, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-29")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_wednesday(self, mock_dt, mock_td):
        """周三 10:00 → 当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 24, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-24")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_wednesday_before_open(self, mock_dt, mock_td):
        """周三 7:00（盘前）→ 周二。"""
        mock_dt.now.return_value = datetime(2026, 6, 24, 7, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-23")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_friday_after_open(self, mock_dt, mock_td):
        """周五 10:00 → 当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 26, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_friday_before_open(self, mock_dt, mock_td):
        """周五 7:00（盘前）→ 周四。"""
        mock_dt.now.return_value = datetime(2026, 6, 26, 7, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-25")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_holiday_monday_after_open(self, mock_dt, mock_td):
        """端午节后周一 10:00 → 当天为交易日，返回当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-22")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_holiday_friday_before_open(self, mock_dt, mock_td):
        """端午节 06-19 盘前 → 退回 06-18。"""
        mock_dt.now.return_value = datetime(2026, 6, 19, 7, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-18")

    @patch("src.python.report.market_value._is_trading_day")
    @patch("src.python.report.market_value.datetime")
    def test_holiday_friday_after_open(self, mock_dt, mock_td):
        """端午节 06-19 10:00（非交易日）→ 退回最近交易日 06-18。"""
        mock_dt.now.return_value = datetime(2026, 6, 19, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-18")


# ═══════════════════════════════════════════════════════════
#  get_prev_trading_day
# ═══════════════════════════════════════════════════════════


class TestGetPrevTradingDay(unittest.TestCase):
    """测试 get_prev_trading_day 前一交易日计算（mock 交易日历）。"""

    @patch("src.python.report.market_value._is_trading_day")
    def test_monday_to_pre_holiday(self, mock_td):
        """端午节后周一 → 跳过假期 → 上周四 06-18。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-22"), "2026-06-18")

    @patch("src.python.report.market_value._is_trading_day")
    def test_tuesday_to_monday(self, mock_td):
        """周二 → 周一。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-23"), "2026-06-22")

    @patch("src.python.report.market_value._is_trading_day")
    def test_wednesday_to_tuesday(self, mock_td):
        """周三 → 周二。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-24"), "2026-06-23")

    @patch("src.python.report.market_value._is_trading_day")
    def test_thursday_to_wednesday(self, mock_td):
        """周四 → 周三。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-25"), "2026-06-24")

    @patch("src.python.report.market_value._is_trading_day")
    def test_friday_to_thursday(self, mock_td):
        """周五 → 周四。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-26"), "2026-06-25")

    @patch("src.python.report.market_value._is_trading_day")
    def test_saturday_to_friday(self, mock_td):
        """周六 → 周五。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-27"), "2026-06-26")

    @patch("src.python.report.market_value._is_trading_day")
    def test_sunday_to_friday(self, mock_td):
        """周日 → 周五。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-28"), "2026-06-26")

    @patch("src.python.report.market_value._is_trading_day")
    def test_empty_string_calls_get_last_trading_day(self, mock_td):
        """空字符串 → 调用 get_last_trading_day。"""
        mock_td.return_value = True  # 模拟所有日期都是交易日
        with patch("src.python.report.market_value.get_last_trading_day") as mock_ltd:
            mock_ltd.return_value = "2026-06-26"
            result = mv.get_prev_trading_day("")
            self.assertEqual(result, "2026-06-25")
            mock_ltd.assert_called_once()

    @patch("src.python.report.market_value._is_trading_day")
    def test_invalid_date(self, mock_td):
        """无效日期字符串 → 返回空字符串。"""
        mock_td.return_value = True
        self.assertEqual(mv.get_prev_trading_day("not-a-date"), "")

    @patch("src.python.report.market_value._is_trading_day")
    def test_none_date(self, mock_td):
        """None 作为日期 → falsy 判断触发，回退到 get_last_trading_day（不会进入异常分支）。"""
        mock_td.return_value = True
        with patch("src.python.report.market_value.get_last_trading_day") as mock_ltd:
            mock_ltd.return_value = "2026-06-26"
            result = mv.get_prev_trading_day(None)
            self.assertEqual(result, "2026-06-25")


# ═══════════════════════════════════════════════════════════
#  _determine_price_type
# ═══════════════════════════════════════════════════════════


class TestDeterminePriceType(unittest.TestCase):
    """测试 _determine_price_type 取价方式标签生成。

    需要 mock is_market_open 和 get_prev_trading_day。
    """

    def setUp(self):
        self.td = "2026-06-26"   # Friday
        self.prev = "2026-06-25"  # Thursday

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
        with patch("src.python.report.market_value.get_prev_trading_day",
                   return_value=self.prev):
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
        with patch("src.python.report.market_value.get_prev_trading_day",
                   return_value=self.prev):
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
        with patch("src.python.report.market_value.get_prev_trading_day",
                   return_value=self.prev):
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
        with patch("src.python.report.market_value.get_prev_trading_day",
                   return_value=self.prev):
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
            "name": "电池ETF", "code": "561910",
            "price": 10.5, "yesterday_close": 10.0,
            "price_date": "2026-06-26",
            "source_api": "tencent", "source": "腾讯财经",
        }
        self.eastmoney_mock_data = {
            "name": "中欧医疗健康混合", "code": "003095",
            "price": 1.5, "yesterday_close": 1.48,
            "price_date": "2026-06-26",
            "source_api": "eastmoney", "source": "东方财富",
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
        self.assertEqual(d.market_value, 10500.0)       # 10.5 * 1000
        self.assertEqual(d.cost, 1000.0)                 # 1.0 * 1000
        self.assertEqual(d.profit, 9500.0)               # 10500 - 1000
        self.assertAlmostEqual(d.profit_rate, 9.5)       # 9500 / 1000
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
        self.assertEqual(d.cost, 1000.0)                 # 2.0 * 500
        self.assertEqual(d.market_value, 750.0)           # 1.5 * 500
        self.assertEqual(d.profit, -250.0)                # 750 - 1000
        # nav_date == T → today_profit = (1.5 - 1.48) * 500
        self.assertEqual(d.today_profit, 10.0)

    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    def test_eastmoney_stale_nav(self, mock_ltd, mock_fetch):
        """East Money + nav_date 过期 → today_profit 为 0。"""
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = {
            "name": "中欧医疗健康混合", "code": "003095",
            "price": 1.5, "yesterday_close": 1.48,
            "price_date": "2026-06-20",          # 6 天前，过期数据
            "source_api": "eastmoney", "source": "东方财富",
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

    # ── 回归测试：场外基金本日盈亏（issue #1）────────────
    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.report.market_value.get_last_trading_day")
    def test_eastmoney_nav_t_minus_1_today_profit_zero(self, mock_ltd, mock_fetch):
        """场外基金净值日期为 T-1（今日净值未出）→ 本日盈亏为 0。"""
        mock_ltd.return_value = "2026-06-26"
        mock_fetch.return_value = {
            "name": "中欧医疗健康混合", "code": "003095",
            "price": 1.5, "yesterday_close": 1.48,
            "price_date": "2026-06-25",          # T-1（周四）
            "source_api": "eastmoney", "source": "东方财富",
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
            "name": "016055", "code": "016055",
            "price": 1.2, "yesterday_close": 1.18,
            "price_date": "2026-06-25",          # T-2（周四）
            "source_api": "eastmoney", "source": "东方财富",
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
            "name": "中欧医疗健康混合", "code": "003095",
            "price": 1.5, "yesterday_close": 1.48,
            "price_date": "2026-06-26",          # T（周五）
            "source_api": "eastmoney", "source": "东方财富",
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

    def test_premium_placeholder_in_detail_row(self):
        """不在交易时段或不是 tencent 源 → premium=--。"""
        from src.python.report.market_value import (
            _compute_detail_row, _FUND_PREMIUM_PLACEHOLDER,
        )
        from src.python.core.models import Holding

        h = Holding(account="证券", name="华夏纳斯达克100ETF(QDII)",
                     code="513300", shares=100, cost_price=1.5)
        mkt = {
            "price": 1.6, "yesterday_close": 1.55,
            "price_date": "2026-06-26",
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.premium, _FUND_PREMIUM_PLACEHOLDER)

    def test_premium_type_is_string(self):
        """溢价率字段始终为字符串类型。"""
        from src.python.report.market_value import (
            _compute_detail_row, _FUND_PREMIUM_PLACEHOLDER,
        )
        from src.python.core.models import Holding

        h = Holding(account="证券", name="沪深300ETF",
                     code="510300", shares=100, cost_price=4.0)
        mkt = {
            "price": 4.2, "yesterday_close": 4.1,
            "price_date": "", "source": "东方财富", "source_api": "eastmoney",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertIsInstance(detail.premium, str)

    def test_premium_in_row_values(self):
        """detail_to_row_values 中溢价率列索引正确。"""
        from src.python.report.market_value import DetailRow
        from src.python.report.market_value_sheet import (
            _detail_to_row_values,
        )

        d = DetailRow(
            account="证券", name="测试", code="600000",
            premium="--",
        )
        values = _detail_to_row_values(d)
        # 溢价率是第 8 列（0-indexed）
        self.assertEqual(values[7], "--")

    def test_premium_not_none(self):
        """溢价率不应为 None（避免 Excel 单元格显示空白）。"""
        from src.python.report.market_value import (
            _compute_detail_row, _FUND_PREMIUM_PLACEHOLDER,
        )
        from src.python.core.models import Holding

        h = Holding(account="证券", name="普通股票",
                     code="600000", shares=100, cost_price=10.0)
        mkt = {
            "price": 11.0, "yesterday_close": 10.5,
            "price_date": "2026-06-26",
            "source": "腾讯财经", "source_api": "tencent",
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

    def tearDown(self):
        self._ld_patcher.stop()

    def test_off_market_nav_not_t_day(self):
        """场外基金 nav_date != trading_day → today_profit=0。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.core.models import Holding

        h = Holding(account="支付宝", name="易方达蓝筹精选",
                     code="005827", shares=1000, cost_price=2.0)
        mkt = {
            "price": 2.1, "yesterday_close": 2.05,
            "price_date": "2026-06-24",  # ≠ 2026-06-26（非 T 日）
            "source": "天天基金", "source_api": "tiantian",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)

    def test_on_market_nav_is_t_day(self):
        """场外基金 nav_date == trading_day → today_profit 正常计算。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.core.models import Holding

        h = Holding(account="支付宝", name="易方达蓝筹精选",
                     code="005827", shares=1000, cost_price=2.0)
        mkt = {
            "price": 2.1, "yesterday_close": 2.05,
            "price_date": "2026-06-26",  # == trading_day
            "source": "天天基金", "source_api": "tiantian",
        }
        detail = _compute_detail_row(h, mkt)
        # today_profit = (2.1 - 2.05) * 1000 = 50.0
        self.assertAlmostEqual(detail.today_profit, 50.0)

    def test_tencent_source_ignores_nav_date(self):
        """腾讯源（场内实时）即使无 nav_date 也计算 today_profit。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.core.models import Holding

        h = Holding(account="证券", name="长江电力",
                     code="600900", shares=100, cost_price=20.0)
        mkt = {
            "price": 21.0, "yesterday_close": 20.5,
            "price_date": "",  # 腾讯源无净值日期
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        # tencent 源始终用 price - yclose 计算 today_profit
        self.assertAlmostEqual(detail.today_profit, 50.0)

    def test_no_nav_date_non_tencent(self):
        """非腾讯源且无 nav_date → today_profit=0。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.core.models import Holding


        h = Holding(account="支付宝", name="某基金",
                     code="000001", shares=100, cost_price=1.0)
        mkt = {
            "price": 1.1, "yesterday_close": 1.05,
            "price_date": "",
            "source": "天天基金", "source_api": "tiantian",
        }
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)


# ═══════════════════════════════════════════════════════════════
#  以下为市值明细非 edge 场景测试
# ═══════════════════════════════════════════════════════════════


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

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_tencent_always_calculates(self, mock_open, mock_td):
        """Tencent 无论 nav_date 是什么 → today_profit 始终计算。"""
        mock_td.return_value = "2026-06-30"
        h = Holding("证券", "长江电力", "600900", 200, 10.0)
        mkt = {
            "price": 28.5, "yesterday_close": 28.0,
            "price_date": "2026-06-25",
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
            "price_date": "2026-06-27",
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
        """"""
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
        self.assertEqual(values[7], "--")


class TestCurrencyConversion(unittest.TestCase):
    """多币种转换正确 — 美元/港币份额处理。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_qdii_price_in_rmb_from_api(self, mock_open, mock_td):
        """QDII 价格来自 API（已为人民币计值），市值计算正确。"""
        mock_td.return_value = "2026-07-01"
        h = Holding("支付宝", "华夏纳斯达克100ETF(QDII)", "513300", 100, 2.0)
        mkt = {
            "price": 2.1, "yesterday_close": 2.0,
            "price_date": "2026-07-01", "source": "天天基金", "source_api": "eastmoney",
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
            "price": 2.1, "yesterday_close": 2.0,
            "price_date": "2026-06-30", "source": "天天基金", "source_api": "eastmoney",
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
            "price": 2.1, "yesterday_close": 2.0,
            "price_date": "2026-06-30", "source": "天天基金", "source_api": "eastmoney",
            "nav_date": "2026-06-30",
        }
        detail = _compute_detail_row(h, mkt)
        updated, total, all_updated = price_update_status([detail], "2026-07-01")
        self.assertEqual(updated, 1)
        self.assertEqual(total, 1)
        self.assertTrue(all_updated)


if __name__ == "__main__":
    unittest.main()

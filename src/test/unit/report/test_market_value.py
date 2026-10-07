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
  pytest src/test/unit/report/test_market_value.py -v

兄弟分片：test_market_value_premium.py（溢价率与今日盈亏分支）。
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch


from src.python.core import trading_calendar
from src.python.core.models import Holding
from src.python.report import market_value as mv
import pytest

# ── 市值明细计算与行情更新状态辅助导入 ────────────

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ═══════════════════════════════════════════════════════════
#  get_last_trading_day
# ═══════════════════════════════════════════════════════════


def _mock_calendar() -> set[str]:
    """模拟交易日历：周一到周五，排除 2026-06-19（端午节）。"""
    return {
        "2026-06-18",
        "2026-06-22",
        "2026-06-23",
        "2026-06-24",
        "2026-06-25",
        "2026-06-26",
        "2026-06-29",
        "2026-06-30",
    }


def _mock_is_trading_day(date) -> bool:
    """mock _is_trading_day：用 _mock_calendar 迷你日历判定，保留节假日语义。

    原实现会经 _get_trading_calendar() → akshare(V8) 真实网络。此辅助函数
    用固定迷你日历替代，使 T-N 计数（_count_trading_days_back）行为与原
    真实 akshare 日历一致（含 2026-06-19 端午排除），同时零网络依赖。
    """
    return date.strftime("%Y-%m-%d") in _mock_calendar()


# ═══════════════════════════════════════════════════════════
#  交易日历并发串行化（回归：并发初始化 V8 崩溃）
# ═══════════════════════════════════════════════════════════


class _FakeSeries:
    """极简 pandas.Series 替代：仅支撑 dropna().astype(str).tolist() 链式调用。"""

    def __init__(self, values):
        self._values = values

    def dropna(self):
        return self

    def astype(self, _dtype):
        return self

    def tolist(self):
        return list(self._values)


class _FakeCalendarDf:
    """极简 DataFrame 替代：仅支撑 df["trade_date"] 取值。"""

    def __init__(self, trade_dates):
        self._trade_dates = trade_dates

    def __getitem__(self, key):
        if key == "trade_date":
            return _FakeSeries(self._trade_dates)
        raise KeyError(key)


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

    def test_etf_empty_string(self):
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
            account=account,
            name=name,
            code=code,
            shares=1.0,
            cost_price=1.0,
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
        h = Holding(account="  证券账户  ", name="  电池ETF  ", code="  561910  ", shares=1.0, cost_price=1.0)
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
    """测试 price_update_status 价格更新状态检测。

    注意：类级 setUp 统一 mock 市场状态与交易日历，避免真实网络请求。
    price_update_status 内部会调用 is_market_open/is_midday_break（东方财富
    push2 API，真实 HTTP）与 get_prev_trading_day→_is_trading_day（akshare
    交易日历，V8 解密 + 真实 HTTP）。这些外部依赖与"价格更新状态判断"断言无关，
    必须在测试中隔离，否则每个用例耗时 2~6s 且依赖网络。
    方法级 @patch 与 setUp 的 patch 叠加时，方法级 mock 优先（后进入栈）。
    """

    def setUp(self) -> None:
        self._patch_open = patch("src.python.report.market_value.is_market_open", return_value=False)
        self._patch_midday = patch("src.python.report.market_value.is_midday_break", return_value=False)
        self._patch_td = patch("src.python.core.trading_calendar._is_trading_day", side_effect=_mock_is_trading_day)
        self._patch_open.start()
        self._patch_midday.start()
        self._patch_td.start()
        self.addCleanup(self._patch_open.stop)
        self.addCleanup(self._patch_midday.stop)
        self.addCleanup(self._patch_td.stop)

    def _row(self, source_api: str, nav_date: str, name: str = "") -> mv.DetailRow:
        return mv.DetailRow(
            source_api=source_api,
            nav_date=nav_date,
            name=name,
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
            self._row("tencent", "2026-06-26"),  # 已更新（已收市）
            self._row("tencent", "2026-06-25"),  # 未更新
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


class TestGetLastTradingDay(unittest.TestCase):
    """测试 get_last_trading_day 最近交易日计算（mock datetime.now + 交易日历）。"""

    def _mock_td(self, d):
        return d.strftime("%Y-%m-%d") in _mock_calendar()

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_saturday(self, mock_dt, mock_td):
        """周六 → 上周五。"""
        mock_dt.now.return_value = datetime(2026, 6, 27, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_sunday(self, mock_dt, mock_td):
        """周日 → 上周五。"""
        mock_dt.now.return_value = datetime(2026, 6, 28, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_monday_after_open(self, mock_dt, mock_td):
        """周一 10:00（已开盘）→ 当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 29, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-29")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_monday_before_open(self, mock_dt, mock_td):
        """周一 02:35（盘前）→ 上周五。"""
        mock_dt.now.return_value = datetime(2026, 6, 29, 2, 35, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_monday_early_morning(self, mock_dt, mock_td):
        """周一 9:00（盘前）→ 上周五。"""
        mock_dt.now.return_value = datetime(2026, 6, 29, 9, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_monday_at_open(self, mock_dt, mock_td):
        """周一 9:30（开盘）→ 当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 29, 9, 30, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-29")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_wednesday(self, mock_dt, mock_td):
        """周三 10:00 → 当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 24, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-24")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_wednesday_before_open(self, mock_dt, mock_td):
        """周三 7:00（盘前）→ 周二。"""
        mock_dt.now.return_value = datetime(2026, 6, 24, 7, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-23")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_friday_after_open(self, mock_dt, mock_td):
        """周五 10:00 → 当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 26, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-26")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_friday_before_open(self, mock_dt, mock_td):
        """周五 7:00（盘前）→ 周四。"""
        mock_dt.now.return_value = datetime(2026, 6, 26, 7, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-25")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_holiday_monday_after_open(self, mock_dt, mock_td):
        """端午节后周一 10:00 → 当天为交易日，返回当天。"""
        mock_dt.now.return_value = datetime(2026, 6, 22, 10, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-22")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
    def test_holiday_friday_before_open(self, mock_dt, mock_td):
        """端午节 06-19 盘前 → 退回 06-18。"""
        mock_dt.now.return_value = datetime(2026, 6, 19, 7, 0, 0)
        mock_td.side_effect = self._mock_td
        self.assertEqual(mv.get_last_trading_day(), "2026-06-18")

    @patch("src.python.core.trading_calendar._is_trading_day")
    @patch("src.python.core.trading_calendar.datetime")
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

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_monday_to_pre_holiday(self, mock_td):
        """端午节后周一 → 跳过假期 → 上周四 06-18。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-22"), "2026-06-18")

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_tuesday_to_monday(self, mock_td):
        """周二 → 周一。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-23"), "2026-06-22")

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_wednesday_to_tuesday(self, mock_td):
        """周三 → 周二。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-24"), "2026-06-23")

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_thursday_to_wednesday(self, mock_td):
        """周四 → 周三。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-25"), "2026-06-24")

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_friday_to_thursday(self, mock_td):
        """周五 → 周四。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-26"), "2026-06-25")

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_saturday_to_friday(self, mock_td):
        """周六 → 周五。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-27"), "2026-06-26")

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_sunday_to_friday(self, mock_td):
        """周日 → 周五。"""
        mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in _mock_calendar()
        self.assertEqual(mv.get_prev_trading_day("2026-06-28"), "2026-06-26")

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_empty_string_calls_get_last_trading_day(self, mock_td):
        """空字符串 → 调用 get_last_trading_day。"""
        mock_td.return_value = True  # 模拟所有日期都是交易日
        with patch("src.python.core.trading_calendar.get_last_trading_day") as mock_ltd:
            mock_ltd.return_value = "2026-06-26"
            result = mv.get_prev_trading_day("")
            self.assertEqual(result, "2026-06-25")
            mock_ltd.assert_called_once()

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_invalid_date(self, mock_td):
        """无效日期字符串 → 返回空字符串。"""
        mock_td.return_value = True
        self.assertEqual(mv.get_prev_trading_day("not-a-date"), "")

    @patch("src.python.core.trading_calendar._is_trading_day")
    def test_none_date(self, mock_td):
        """None 作为日期 → falsy 判断触发，回退到 get_last_trading_day（不会进入异常分支）。"""
        mock_td.return_value = True
        with patch("src.python.core.trading_calendar.get_last_trading_day") as mock_ltd:
            mock_ltd.return_value = "2026-06-26"
            result = mv.get_prev_trading_day(None)
            self.assertEqual(result, "2026-06-25")


class TestTradingCalendarConcurrency(unittest.TestCase):
    """回归测试：并发调用交易日历会串行化 akshare(V8) 调用。

    缺陷场景：菜单 2「更新行情类缓存」的并行价格抓取（ThreadPoolExecutor
    4 workers）中，每个价格的新鲜度校验都会调用 get_last_trading_day() →
    _get_trading_calendar()。akshare 的 tool_trade_date_hist_sina() 内部用
    py_mini_racer(V8) 解密，多线程并发首次初始化会触发
    [FATAL:partition_address_space.cc(243)] Check failed:
    !IsConfigurablePoolInitialized() 直接 abort 进程（try/except 无法捕获）。

    修复：_get_trading_calendar() 缓存未命中分支用模块级锁串行化。
    本测试直接验证该串行化不变量：并发调用下 akshare 回调最大并发深度为 1。
    """

    def test_concurrent_calls_serialize_akshare(self):
        import sys
        import threading
        import types

        from src.python.cache import clear as cache_clear

        # 缓存隔离：确保所有线程都走到 akshare 未命中分支
        cache_clear(trading_calendar._TRADING_CALENDAR_CACHE_KEY)

        # ── 注入 fake akshare：统计 tool_trade_date_hist_sina 回调并发深度 ──
        depth = {"active": 0, "max_active": 0}
        counter_lock = threading.Lock()

        def fake_tool_trade_date_hist_sina():
            with counter_lock:
                depth["active"] += 1
                depth["max_active"] = max(depth["max_active"], depth["active"])
            # 锁外持有，构造并发窗口：无串行化时多线程能观察到 max_active > 1
            try:
                return _FakeCalendarDf(["2026-08-03", "2026-08-04", "2026-08-05"])
            finally:
                with counter_lock:
                    depth["active"] -= 1

        fake_akshare = types.ModuleType("akshare")
        fake_akshare.tool_trade_date_hist_sina = fake_tool_trade_date_hist_sina

        results: list = []
        errors: list = []

        def worker():
            try:
                results.append(trading_calendar._get_trading_calendar())
            except Exception as exc:
                errors.append(exc)

        with patch.dict(sys.modules, {"akshare": fake_akshare}):
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 4)
        expected = {"2026-08-03", "2026-08-04", "2026-08-05"}
        for r in results:
            self.assertEqual(r, expected)
        # 核心断言：akshare(V8) 回调被串行化，最大并发深度为 1
        self.assertEqual(depth["max_active"], 1)


if __name__ == "__main__":
    unittest.main()

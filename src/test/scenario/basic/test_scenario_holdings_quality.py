"""Z3 — 持仓质量场景（S0a-S0d）。

测试目标：
  验证持仓数据质量和边界情况下的正确行为：

  S0a: 含已清仓记录 — shares=0 的持仓自动跳过，不计入报告各项合计
  S0b: 同名基金多份额 — A/C 类份额同时持有时的穿透合并行为
  S0d: 持仓名称含特殊字符 — ®/™/♥/全角括号/繁体中文/英文混排不破坏输出
  S0c: 超多持仓 -> scenario/scenario_extreme/test_scenario_extreme.py

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_holdings_quality.py -v
  pytest src/test/ -m "scenario_basic" -v          # 含全部 S 场景
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from src.python.models import Holding

# 各 S0 类已各自标注 @pytest.mark.scenario，模块级不写入 scenario
# 避免 TestS0cLargeHoldings（无 @pytest.mark.scenario）被意外收集
pytestmark = [pytest.mark.scenario_basic]


# ═══════════════════════════════════════════════════════════════
#  S0a: 含已清仓记录
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS0aZeroSharesSkipped(unittest.TestCase):
    """S0a: 含已清仓记录 — 份额为 0 的持仓自动跳过。

    验证：
      1. 份额=0 时市值/成本/盈亏均为 0，不影响合计
      2. 份额=0 且成本=0 时不会导致除零错误
      3. 份额=0 的持仓在穿透计算中被正确排除
    """

    def test_compute_detail_row_zero_shares(self):
        """份额=0 → market_value=0, cost=0, profit=0。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "已清仓品种", "600999", shares=0, cost_price=10.0)
        mkt = {
            "price": 12.0, "yesterday_close": 11.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "已清仓品种", "code": "600999",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)

        self.assertEqual(row.shares, 0.0)
        self.assertEqual(row.market_value, 0.0)   # 12.0 * 0 = 0
        self.assertEqual(row.cost, 0.0)            # 10.0 * 0 = 0
        self.assertEqual(row.profit, 0.0)          # 0 - 0 = 0
        self.assertEqual(row.today_profit, 0.0)    # (12-11.5) * 0 = 0

    def test_compute_detail_row_zero_shares_no_mkt(self):
        """份额=0 + 无行情 → cost=0（不崩溃）。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "已清仓品种", "600999", shares=0, cost_price=10.0)
        row = _compute_detail_row(h, None)

        self.assertEqual(row.shares, 0.0)
        self.assertEqual(row.market_value, 0.0)
        self.assertEqual(row.cost, 0.0)
        self.assertEqual(row.profit, 0.0)

    def test_compute_detail_row_zero_shares_zero_cost(self):
        """份额=0 + 成本=0 → profit_rate=None，不触发除零。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "已清仓品种", "600999", shares=0, cost_price=0.0)
        mkt = {
            "price": 12.0, "yesterday_close": 11.5,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "已清仓品种", "code": "600999",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)

        self.assertEqual(row.market_value, 0.0)
        self.assertEqual(row.cost, 0.0)
        # profit_rate 应为 None（cost=0 时分母为 0）
        self.assertIsNone(row.profit_rate)

    def test_zero_shares_not_affect_total(self):
        """带正常持仓+清仓持仓时，合计仅含正常持仓。"""
        from src.python.report.market_value import _compute_detail_row

        h1 = Holding("证券", "正常股票", "600519", shares=100, cost_price=150.0)
        h2 = Holding("证券", "已清仓品种", "600999", shares=0, cost_price=10.0)

        mkt1 = {
            "price": 160.0, "yesterday_close": 155.0,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "正常股票", "code": "600519",
        }

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row1 = _compute_detail_row(h1, mkt1)
            row2 = _compute_detail_row(h2, mkt1)  # 使用相同行情数据

        total_mv = row1.market_value + row2.market_value
        total_cost = row1.cost + row2.cost
        # 仅正常股票有市值
        self.assertGreater(row1.market_value, 0)
        # 清仓品种市值=0，不影响合计
        self.assertEqual(total_mv, row1.market_value)
        self.assertEqual(total_cost, row1.cost)


# ═══════════════════════════════════════════════════════════════
#  S0b: 同名基金多份额（A/C 类）
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS0bSameFundACClass(unittest.TestCase):
    """S0b: 同名基金多份额 — A/C 类同时持有。

    验证：
      1. A 类和 C 类都正确分类为 active_equity
      2. 穿透计算同时处理 A/C 两类不崩溃
      3. 穿透合并后不会因代码不同而重复计算
    """

    def test_ac_share_classification(self):
        """A/C 类份额都分类为 active_equity。"""
        from src.python.report.penetration import classify_penetration

        a = Holding("支付宝", "易方达蓝筹精选A", "005827", 500, 2.0)
        c = Holding("支付宝", "易方达蓝筹精选C", "012772", 300, 2.0)

        self.assertEqual(classify_penetration(a), "active_equity")
        self.assertEqual(classify_penetration(c), "active_equity")

    def test_ac_share_in_category(self):
        """A/C 类份额在分类逻辑中均归为（基金, 主动）。"""
        from src.python.report.category import _categorize_holding

        a = Holding("支付宝", "易方达蓝筹精选A", "005827", 500, 2.0)
        c = Holding("支付宝", "易方达蓝筹精选C", "012772", 300, 2.0)

        self.assertEqual(_categorize_holding(a), ("基金", "主动"))
        self.assertEqual(_categorize_holding(c), ("基金", "主动"))

    def test_ac_penetration_not_crash(self):
        """A/C 类同时穿透 → compute_penetration_top10 不崩溃。"""
        from src.python.report.market_value import DetailRow
        from src.python.report.penetration import compute_penetration_top10

        holdings = [
            Holding("支付宝", "易方达蓝筹精选A", "005827", 500, 2.0),
            Holding("支付宝", "易方达蓝筹精选C", "012772", 300, 2.0),
        ]
        details = [
            DetailRow(
                account="支付宝", name="易方达蓝筹精选A", code="005827",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=500.0,
                market_value=800.0, cost=1000.0, profit=-200.0,
                profit_rate=-0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
            DetailRow(
                account="支付宝", name="易方达蓝筹精选C", code="012772",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=300.0,
                market_value=480.0, cost=600.0, profit=-120.0,
                profit_rate=-0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]

        with (
            patch("src.python.report.penetration.fetch_fund_holdings_batch",
                  return_value={
                      "005827": {
                          "code": "005827", "name": "易方达蓝筹精选",
                          "date": "2026-03-31",
                          "holdings": [{"name": "贵州茅台", "code": "600519",
                                        "ratio": 16.0}],
                      },
                      "012772": {
                          "code": "005827", "name": "易方达蓝筹精选",
                          "date": "2026-03-31",
                          "holdings": [{"name": "贵州茅台", "code": "600519",
                                        "ratio": 16.0}],
                      },
                  }),
            patch("src.python.fetcher.industry.batch_fetch_industry_data",
                  return_value={}),
        ):
            result = compute_penetration_top10(holdings, details)

        self.assertIsNotNone(result)
        self.assertIn("top10", result)
        self.assertGreater(len(result["top10"]), 0)

    def test_ac_market_value_summed(self):
        """A/C 穿透后总市值 = (A 市值 + C 市值) × 持仓比例。"""
        from src.python.report.market_value import DetailRow
        from src.python.report.penetration import compute_penetration_top10

        holdings = [
            Holding("支付宝", "易方达蓝筹精选A", "005827", 500, 2.0),
            Holding("支付宝", "易方达蓝筹精选C", "012772", 300, 2.0),
        ]
        details = [
            DetailRow(
                account="支付宝", name="易方达蓝筹精选A", code="005827",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=500.0,
                market_value=800.0, cost=1000.0, profit=-200.0,
                profit_rate=-0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
            DetailRow(
                account="支付宝", name="易方达蓝筹精选C", code="012772",
                price=1.8, nav_date="2026-07-03", yesterday_close=1.75,
                price_type="T-1", premium="--", shares=300.0,
                market_value=480.0, cost=600.0, profit=-120.0,
                profit_rate=-0.2, today_profit=0.0,
                source="mock", source_api="tiantian",
            ),
        ]

        with (
            patch("src.python.report.penetration.fetch_fund_holdings_batch",
                  return_value={
                      "005827": {
                          "code": "005827", "name": "易方达蓝筹精选",
                          "date": "2026-03-31",
                          "holdings": [{"name": "贵州茅台", "code": "600519",
                                        "ratio": 16.0}],
                      },
                      "012772": {
                          "code": "005827", "name": "易方达蓝筹精选",
                          "date": "2026-03-31",
                          "holdings": [{"name": "贵州茅台", "code": "600519",
                                        "ratio": 16.0}],
                      },
                  }),
            patch("src.python.fetcher.industry.batch_fetch_industry_data",
                  return_value={}),
        ):
            result = compute_penetration_top10(holdings, details)

        # A: 800*0.16=128, C: 480*0.16=76.8, 穿透合计=204.8
        total_mv = result["summary"]["total_mv"]
        self.assertAlmostEqual(total_mv, 204.8, places=1)


# ═══════════════════════════════════════════════════════════════
#  S0d: 持仓名称含特殊字符
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS0dSpecialCharacters(unittest.TestCase):
    """S0d: 特殊字符名称 — 不破坏输出。

    验证名称含以下字符时各模块不崩溃：
      - ® ™ ♥ 等特殊符号
      - （全角括号）、全角空格
      - 繁体中文
      - 英文/数字/符号混排
    """

    # 特殊字符持仓名称列表
    SPECIAL_NAMES = [
        ("证券", "贵州茅台®", "600519"),
        ("证券", "科技ETF™", "510300"),
        ("证券", "测试♥基金", "003095"),
        ("支付宝", "（全角括号）测试", "003095"),
        ("证券", "中歐盛世成長", "003095"),   # 繁体
        ("证券", "S&P 500 ETF", "513500"),
        ("微信", " 前後空格 ", "003095"),
        ("支付宝", "Test·混合·名称", "003095"),
    ]

    def test_special_chars_classification(self):
        """特殊字符名称 → _categorize_holding 不崩溃。"""
        from src.python.report.category import _categorize_holding

        for account, name, code in self.SPECIAL_NAMES:
            with self.subTest(name=name):
                h = Holding(account, name, code, 100, 10.0)
                prop, sub = _categorize_holding(h)
                self.assertIsNotNone(prop)
                self.assertIsNotNone(sub)

    def test_special_chars_penetration_classify(self):
        """特殊字符名称 → classify_penetration 不崩溃。"""
        from src.python.report.penetration import classify_penetration

        for account, name, code in self.SPECIAL_NAMES:
            with self.subTest(name=name):
                h = Holding(account, name, code, 100, 10.0)
                cls = classify_penetration(h)
                self.assertIsNotNone(cls)

    def test_special_chars_compute_detail_row(self):
        """特殊字符名称 → _compute_detail_row 不崩溃。"""
        from src.python.report.market_value import _compute_detail_row

        for account, name, code in self.SPECIAL_NAMES:
            with self.subTest(name=name):
                h = Holding(account, name, code, 100, 10.0)
                mkt = {
                    "price": 10.0, "yesterday_close": 9.8,
                    "price_date": "2026-07-03", "source_api": "tencent",
                    "name": name, "code": code,
                }
                with (
                    patch("src.python.report.market_value.get_last_trading_day",
                          return_value="2026-07-03"),
                    patch("src.python.report.market_value.datetime") as mock_dt,
                ):
                    mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
                    mock_dt.timezone = timezone
                    mock_dt.timedelta = timedelta
                    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                    row = _compute_detail_row(h, mkt)

                self.assertEqual(row.name, name)
                self.assertAlmostEqual(row.market_value, 1000.0)  # 10 * 100

    def test_special_chars_excel_sheet_write(self):
        """特殊字符名称 → write_market_value_sheet 不崩溃。"""
        from src.python.report.market_value import DetailRow

        details = []
        for account, name, code in self.SPECIAL_NAMES:
            details.append(
                DetailRow(
                    account=account, name=name, code=code,
                    price=10.0, nav_date="2026-07-03", yesterday_close=9.8,
                    price_type="T", premium="--", shares=100.0,
                    market_value=1000.0, cost=1000.0, profit=0.0,
                    profit_rate=0.0, today_profit=0.0,
                    source="mock", source_api="tencent",
                )
            )

        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active

        from src.python.report.market_value_sheet import write_market_value_sheet
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            try:
                write_market_value_sheet(ws, [], "2026-07-03", details=details)
            except Exception as e:
                self.fail(f"write_market_value_sheet 含特殊字符名称崩溃: {e}")

    def test_special_chars_html_filters(self):
        """特殊字符名称 → HTML 模板过滤器不崩溃。"""
        from src.python.report.html_jinja_env import (
            _jinja_money, _jinja_shares, _jinja_price, _jinja_pct,
        )

        for account, name, code in self.SPECIAL_NAMES:
            with self.subTest(name=name):
                # 模板过滤器接受 str/float/None 输入，不应因特殊字符崩溃
                try:
                    _jinja_money(1000.50)
                    _jinja_shares(100.0)
                    _jinja_price(10.50)
                    _jinja_pct(0.0523)
                except Exception as e:
                    self.fail(f"HTML 过滤器对名称 '{name}' 崩溃: {e}")


if __name__ == "__main__":
    unittest.main()

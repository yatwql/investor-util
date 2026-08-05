"""模块间接口契约验证 — reader → market_value → penetration 类型链。

验证各模块输入/输出的数据类型契约，不依赖真实 API。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.integration, pytest.mark.integration_contract]


@pytest.mark.integration
@pytest.mark.integration_contract
class TestModuleContractChain(unittest.TestCase):
    """模块间接口契约验证 — reader 输出 → market_value → penetration 类型链。

    构造完整类型链，断言各环节输入/输出类型正确，不依赖真实 API。
    """

    def test_holding_dataclass_fields(self):
        """Holding dataclass 字段类型契约。"""
        h = Holding("证券", "贵州茅台", "600519", 100, 150.0)
        self.assertIsInstance(h.account, str)
        self.assertIsInstance(h.name, str)
        self.assertIsInstance(h.code, str)
        self.assertIsInstance(h.shares, (int, float))
        self.assertIsInstance(h.cost_price, (int, float))

    def test_holding_to_detail_row_contract(self):
        """Holding + MarketData → DetailRow 的类型转换契约。

        _compute_detail_row 接受 Holding + dict，返回 DetailRow，
        字段类型符合预期。
        """
        from src.python.report.market_value import _compute_detail_row, DetailRow

        h = Holding("证券", "贵州茅台", "600519", 100, 150.0)
        mkt = {
            "price": 160.5, "yesterday_close": 158.0,
            "price_date": "2026-07-03", "source_api": "tencent",
            "source": "腾讯行情", "name": "贵州茅台", "code": "600519",
        }

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 30)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)

        # DetailRow 类型契约
        self.assertIsInstance(row, DetailRow)
        self.assertIsInstance(row.account, str)
        self.assertIsInstance(row.name, str)
        self.assertIsInstance(row.code, str)
        self.assertIsInstance(row.price, (int, float))
        self.assertIsInstance(row.nav_date, str)
        self.assertIsInstance(row.yesterday_close, (int, float))
        self.assertIsInstance(row.price_type, str)
        self.assertIsInstance(row.shares, (int, float))
        self.assertIsInstance(row.market_value, (int, float))
        self.assertIsInstance(row.cost, (int, float))
        self.assertIsInstance(row.profit, (int, float))
        self.assertIsInstance(row.profit_rate, (int, float, type(None)))
        self.assertIsInstance(row.source, str)
        self.assertIsInstance(row.source_api, str)

        # 数值合理性
        self.assertAlmostEqual(row.price, 160.5)
        self.assertAlmostEqual(row.market_value, 16050.0)  # 160.5 * 100
        self.assertAlmostEqual(row.cost, 15000.0)  # 150.0 * 100
        self.assertAlmostEqual(row.profit, 1050.0)  # 16050 - 15000

    def test_detail_row_to_penetration_contract(self):
        """list[DetailRow] → compute_penetration_top10 类型链。

        接受 list[Holding] + list[DetailRow]，返回结构化 dict。
        """
        from src.python.report.market_value import DetailRow
        from src.python.report.penetration import compute_penetration_top10

        holdings = [
            Holding("证券", "茅台", "600519", 100, 150.0),
            Holding("证券", "沪深300ETF", "510300", 1000, 4.0),
        ]
        details = [
            DetailRow("证券", "茅台", "600519", 160.0, "2026-07-03",
                      158.0, "tencent", "--", 100, 16000.0, 15000.0, 1000.0,
                      0.0667, 200.0, "腾讯行情", "tencent"),
            DetailRow("证券", "沪深300ETF", "510300", 4.2, "2026-07-03",
                      4.1, "tencent", "--", 1000, 4200.0, 4000.0, 200.0,
                      0.05, 100.0, "腾讯行情", "tencent"),
        ]

        with (
            patch("src.python.fetcher.industry.batch_fetch_industry_data",
                  return_value={}),
        ):
            result = compute_penetration_top10(holdings, details)

        # 顶层字段类型契约
        self.assertIsInstance(result, dict)
        self.assertIn("update_time", result)
        self.assertIn("summary", result)
        self.assertIn("top10", result)
        self.assertIsInstance(result["summary"], dict)
        self.assertIsInstance(result["top10"], list)

        # summary 字段契约
        summary = result["summary"]
        self.assertIn("top10_coverage_pct", summary)
        self.assertIn("unknown_mv", summary)
        self.assertIn("total_mv", summary)

        # top10 条目字段契约
        for item in result["top10"]:
            self.assertIn("rank", item)
            self.assertIn("name", item)
            self.assertIn("codes", item)
            self.assertIn("mv", item)
            self.assertIn("ratio_pct", item)
            self.assertIsInstance(item["rank"], int)
            self.assertIsInstance(item["name"], str)
            self.assertIsInstance(item["codes"], list)
            self.assertIsInstance(item["mv"], (int, float))
            self.assertIsInstance(item["ratio_pct"], (int, float))

    def test_classify_holdings_type_contract(self):
        """classify_holdings 输入/输出类型契约。"""
        from src.python.report.market_value import classify_holdings

        holdings = [
            Holding("证券", "茅台", "600519", 100, 150.0),
            Holding("支付宝", "易方达蓝筹", "005827", 500, 2.0),
        ]
        categories = classify_holdings(holdings)

        self.assertIsInstance(categories, dict)
        expected_keys = {"场内股票", "场内ETF", "国内场外", "QDII"}
        self.assertSetEqual(set(categories.keys()), expected_keys)
        for key, items in categories.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(items, list)
            for item in items:
                self.assertIsInstance(item, Holding)

    def test_classify_penetration_types(self):
        """classify_penetration 返回值为预定义常量之一。"""
        from src.python.report.penetration import classify_penetration, \
            STOCK, ETF, QDII, BOND_FUND, INDEX_LINK, ACTIVE_EQUITY, IGNORE

        valid_types = {STOCK, ETF, QDII, BOND_FUND, INDEX_LINK, ACTIVE_EQUITY, IGNORE}
        test_cases = [
            (Holding("证券", "贵州茅台", "600519", 100, 150.0), STOCK),
            (Holding("证券", "沪深300ETF", "510300", 1000, 4.0), ETF),
            (Holding("证券", "易方达QDII", "003095", 100, 1.5), QDII),
            (Holding("证券", "招商纯债", "003095", 1000, 1.0), BOND_FUND),
            (Holding("支付宝", "沪深300ETF联接", "003095", 500, 1.5), INDEX_LINK),
            (Holding("支付宝", "易方达蓝筹精选", "005827", 500, 2.0), ACTIVE_EQUITY),
            (Holding("证券", "XX转债", "123456", 100, 100.0), IGNORE),
        ]
        for h, expected in test_cases:
            with self.subTest(name=h.name):
                result = classify_penetration(h)
                self.assertIn(result, valid_types)
                self.assertEqual(result, expected)

    def test_compute_detail_row_none_mkt_fallback(self):
        """行情为 None 时 _compute_detail_row 返回降级 DetailRow。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "茅台", "600519", 100, 150.0)
        row = _compute_detail_row(h, None)
        self.assertEqual(row.price, 0.0)
        self.assertEqual(row.market_value, 0.0)
        self.assertAlmostEqual(row.cost, 15000.0)  # cost_price * shares
        self.assertEqual(row.profit, 0.0)
        self.assertEqual(row.nav_date, "")
        self.assertEqual(row.source_api, "")

    def test_price_update_status_type_contract(self):
        """price_update_status 返回三元组类型契约。"""
        from src.python.report.market_value import price_update_status, DetailRow

        details = [
            DetailRow("证券", "茅台", "600519", 160.0, "2026-07-03",
                      158.0, "tencent", "--", 100, 16000.0, 15000.0, 1000.0,
                      0.0667, 200.0, "腾讯行情", "tencent"),
        ]
        with (
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-07-02"),
        ):
            updated, total, all_updated = price_update_status(details, "2026-07-03")

        self.assertIsInstance(updated, int)
        self.assertIsInstance(total, int)
        self.assertIsInstance(all_updated, bool)

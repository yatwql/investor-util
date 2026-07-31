"""Y2: 数据质量纵深边缘场景测试。

覆盖停牌无交易/新基金空持仓/穿透数据重复/多层嵌套 FOF/ETF 超多持仓/
负价格净值/极低流动性/债券违约/同基金多层份额/跨市场停牌时差共 15 项测试。

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/report/test_data_quality_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.core.models import Holding
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


def _make_holding(name: str, code: str, shares: float = 100,
                  cost_price: float = 10.0, account: str = "证券") -> Holding:
    return Holding(account=account, name=name, code=code,
                   shares=shares, cost_price=cost_price)


def _make_merged_item(name: str, mv: float,
                      codes: list[str] | None = None,
                      funds: list[str] | None = None,
                      sector: str = "制造业",
                      concepts: list[str] | None = None) -> dict:
    return {
        "name": name,
        "mv": mv,
        "codes": codes or [],
        "funds": funds or ["直接持股"],
        "sector": sector,
        "concepts": concepts or [],
    }


def _make_detail_row(code: str, market_value: float = 1000.0,
                     name: str = "持仓") -> "DetailRow":
    from src.python.report.market_value import DetailRow
    return DetailRow(account="证券", name=name, code=code,
                     price=10.0, nav_date="2026-07-01",
                     yesterday_close=9.9, price_type="场内收盘价(T)",
                     premium="--", shares=100, market_value=market_value,
                     cost=1000.0, profit=0.0, profit_rate=0.0,
                     today_profit=0.0, source="腾讯财经", source_api="tencent")


# ═══════════════════════════════════════════════════════════
# Y2-1: 停牌无交易
# ═══════════════════════════════════════════════════════════

class TestSuspendedStockY2(unittest.TestCase):
    """停牌股票：行情无更新，today_profit = 0。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_suspended_stock_price_unchanged(self, mock_open, mock_td):
        """停牌股票（price == yesterday_close）→ today_profit = 0。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "停牌股票", "600519", 100, 200.0)
        mkt = {"price": 200.0, "yesterday_close": 200.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_suspended_stock_zero_price(self, mock_open, mock_td):
        """停牌股票（price=0）→ 市值为 0，today_profit=0。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "长期停牌", "000001", 100, 10.0)
        mkt = {"price": 0.0, "yesterday_close": 0.0,
               "price_date": "2026-06-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.market_value, 0.0)
        self.assertEqual(detail.today_profit, 0.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_suspended_stock_stale_price_type(self, mock_open, mock_td):
        """停牌股票 → price_type 为场内收盘价(T-1) 或更早。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import (
            _compute_detail_row, _determine_price_type,
        )
        h = Holding("证券", "停牌股票", "600900", 100, 10.0)
        mkt = {"price": 10.0, "yesterday_close": 10.0,
               "price_date": "2026-06-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        # 价格日期为 T-N，取价方式应为 "场内收盘价(YYYY-MM-DD)"
        price_type = _determine_price_type("tencent", "2026-06-01", "2026-07-01")
        self.assertIn("2026-06-01", price_type)


# ═══════════════════════════════════════════════════════════
# Y2-2: 新基金空持仓
# ═══════════════════════════════════════════════════════════

class TestNewFundEmptyHoldingsY2(unittest.TestCase):
    """新成立基金尚无持仓数据 → 穿透不崩溃。"""

    @patch("src.python.report.penetration.fetch_fund_holdings_batch", return_value={"019999": None})
    def test_empty_holdings_moves_to_unknown(self, mock_batch):
        """空持仓基金 → 归入 unknown_mv，不崩溃。"""
        from src.python.report.penetration import _merge_fund_layer

        funds = [_make_holding("新发基金", "019999", 100, 1.0, account="支付宝")]
        detail_map = {"019999": 100.0}
        merged, unknown_mv, failed_count, failed_details = _merge_fund_layer(funds, detail_map)

        self.assertEqual(failed_count, 1)
        self.assertGreater(unknown_mv, 0)
        self.assertEqual(len(failed_details), 1)
        self.assertEqual(failed_details[0]["code"], "019999")

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_empty_holdings_mixed_with_normal(self, mock_batch):
        """空持仓基金+正常基金混合 → 正常基金穿透仍正确。"""
        from src.python.report.penetration import _merge_fund_layer

        _data = {
            "005827": {"holdings": [
                {"name": "贵州茅台", "code": "600519", "ratio": 50.0},
            ]},
        }
        mock_batch.side_effect = lambda codes: {code: _data.get(code) for code in codes}

        detail_map = {
            "005827": 1000.0,
            "019999": 100.0,
        }
        funds = [
            _make_holding("易方达蓝筹", "005827", 100, 10.0, account="支付宝"),
            _make_holding("新发基金", "019999", 100, 1.0, account="支付宝"),
        ]
        merged, unknown_mv, failed_count, _ = _merge_fund_layer(funds, detail_map)

        # 正常基金穿透：贵州茅台 1000*50%=500
        self.assertIn("贵州茅台", merged)
        self.assertAlmostEqual(merged["贵州茅台"]["mv"], 500.0)
        self.assertEqual(failed_count, 1)
        self.assertGreater(unknown_mv, 0.0)


# ═══════════════════════════════════════════════════════════
# Y2-3: 穿透数据重复
# ═══════════════════════════════════════════════════════════

class TestPenetrationDataDeduplicationY2(unittest.TestCase):
    """穿透数据重复条目处理。"""

    def test_same_code_in_fund_and_direct(self):
        """同一股票既直接持有又被基金持有 → 合并市值。"""
        from src.python.report.penetration import (
            _build_penetration_result,
        )

        merged = {
            "宁德时代": _make_merged_item("宁德时代", 30000,
                                      funds=["直接持股", "沪深300ETF"]),
        }
        classified = {"qdii": [], "etf": [], "index_link": [],
                      "bond_fund": [], "active_equity": []}
        result = _build_penetration_result(
            merged=merged, classified=classified, funds=[],
            direct_stocks=[], unknown_mv=0.0, failed_count=0,
            failed_fund_details=[],
        )
        self.assertEqual(len(result["top10"]), 1)
        self.assertEqual(result["top10"][0]["name"], "宁德时代")
        self.assertEqual(result["top10"][0]["mv"], 30000)

    def test_same_code_multiple_funds_deduped(self):
        """同一资产被多只基金持有 → 合并为 1 条。"""
        from src.python.report.penetration import (
            _build_penetration_result,
        )

        merged = {
            "贵州茅台": _make_merged_item("贵州茅台", 50000,
                                      codes=["600519"],
                                      funds=["易方达蓝筹", "沪深300ETF"]),
        }
        classified = {"qdii": [], "etf": [], "index_link": [],
                      "bond_fund": [], "active_equity": []}
        result = _build_penetration_result(
            merged=merged, classified=classified, funds=[],
            direct_stocks=[], unknown_mv=0.0, failed_count=0,
            failed_fund_details=[],
        )
        self.assertEqual(len(result["top10"]), 1)
        self.assertIn("易方达蓝筹", result["top10"][0].get("sources", []))
        self.assertIn("沪深300ETF", result["top10"][0].get("sources", []))


# ═══════════════════════════════════════════════════════════
# Y2-4: 多层嵌套 FOF
# ═══════════════════════════════════════════════════════════

class TestNestedFOFY2(unittest.TestCase):
    """FOF 持有 FOF → 仅处理第一层，不递归崩溃。"""

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_fof_holding_fof_no_crash(self, mock_batch, mock_ind):
        """FOF 持有另一只基金 → 穿透不崩溃，第一层正常。"""
        from src.python.report.penetration import compute_penetration_top10

        _data = {
            "FOF001": {"holdings": [
                {"name": "子基金 A", "code": "SUB001", "ratio": 60.0},
                {"name": "中国平安", "code": "601318", "ratio": 40.0},
            ]},
            "SUB001": {"holdings": [
                {"name": "贵州茅台", "code": "600519", "ratio": 80.0},
                {"name": "腾讯控股", "code": "SUB002", "ratio": 20.0},
            ]},
        }
        mock_batch.side_effect = lambda codes: {code: _data.get(code) for code in codes}

        funds = [
            _make_holding("FOF母基金", "FOF001", 1000, 2.0, account="支付宝"),
        ]
        details = [_make_detail_row("FOF001", 2000.0, "FOF母基金")]
        result = compute_penetration_top10(funds, details)

        # 第一层正常穿透：子基金A 60% + 中国平安 40%
        top10_names = [item["name"] for item in result["top10"]]
        self.assertIn("子基金 A", top10_names)
        self.assertIn("中国平安", top10_names)


# ═══════════════════════════════════════════════════════════
# Y2-5: ETF 超多持仓
# ═══════════════════════════════════════════════════════════

class TestETFSuperManyHoldingsY2(unittest.TestCase):
    """ETF 持仓 200+ 只 → 穿透不崩溃，TOP10 正确。"""

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_etf_200_holdings_no_crash(self, mock_batch, mock_ind):
        """ETF 含 200 只持仓 → compute_penetration_top10 不崩溃。"""
        from src.python.report.penetration import compute_penetration_top10

        holdings_200 = [
            {"name": f"持仓{i:04d}", "code": f"{600000+i}", "ratio": 0.5}
            for i in range(200)
        ]
        mock_batch.return_value = {"510300": {"holdings": holdings_200}}

        etf = _make_holding("沪深300ETF", "510300", 1000, 4.0, account="证券")
        details = [_make_detail_row("510300", 4000.0, "沪深300ETF")]

        result = compute_penetration_top10([etf], details)

        # TOP10 最多取 10 条
        self.assertLessEqual(len(result["top10"]), 10)
        # merged_count 反映合并后数量
        self.assertGreaterEqual(result["summary"]["merged_count"], 200)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_etf_200_holdings_ratio_sum(self, mock_batch, mock_ind):
        """ETF 200 只持仓 ratio_pct 之和 ≈ 100%。"""
        from src.python.report.penetration import compute_penetration_top10

        holdings_200 = [
            {"name": f"持仓{i:04d}", "code": f"{600000+i}", "ratio": 0.5}
            for i in range(200)
        ]
        mock_batch.return_value = {"510300": {"holdings": holdings_200}}

        etf = _make_holding("宽基ETF", "510300", 1000, 4.0)
        details = [_make_detail_row("510300", 4000.0, "宽基ETF")]
        result = compute_penetration_top10([etf], details)
        total_ratio = sum(item["ratio_pct"] for item in result["top10"])
        # 每只持仓占 0.5%，TOP10 共 5%
        self.assertAlmostEqual(total_ratio, 5.0, delta=0.02)


# ═══════════════════════════════════════════════════════════
# Y2-6: 负价格净值
# ═══════════════════════════════════════════════════════════

class TestNegativePriceNavY2(unittest.TestCase):
    """负价格/净值场景。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_negative_price_market_value(self, mock_open, mock_td):
        """负价格 → 市值 = 负值，计算不崩溃。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "异常资产", "000001", 100, 10.0)
        mkt = {"price": -5.0, "yesterday_close": 10.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.market_value, -500.0)
        self.assertAlmostEqual(detail.today_profit, -1500.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_negative_yclose(self, mock_open, mock_td):
        """昨日收盘为负 → today_profit 计算不崩溃。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "资产", "000001", 100, 10.0)
        mkt = {"price": 5.0, "yesterday_close": -5.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        expected_today = round((5.0 - (-5.0)) * 100, 2)
        self.assertEqual(detail.today_profit, expected_today)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_negative_nav_penetration(self, mock_batch, mock_ind):
        """基金净值为负 → 穿透不崩溃。"""
        from src.python.report.penetration import compute_penetration_top10

        mock_batch.return_value = {"005827": {"holdings": [
            {"name": "贵州茅台", "code": "600519", "ratio": 100.0},
        ]}}
        h = _make_holding("亏损基金", "005827", 100, 10.0)
        details = [_make_detail_row("005827", -500.0, "亏损基金")]
        result = compute_penetration_top10([h], details)
        self.assertEqual(len(result["top10"]), 1)
        # 穿透市值基于基金市值计算，为负值
        self.assertLess(result["top10"][0]["mv"], 0)


# ═══════════════════════════════════════════════════════════
# Y2-7: 极低流动性
# ═══════════════════════════════════════════════════════════

class TestLowLiquidityY2(unittest.TestCase):
    """极低流动性资产。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_zero_volume_price_no_change(self, mock_open, mock_td):
        """极低流动性（price==yclose，无波动）→ today_profit=0。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "僵尸股", "000001", 1000, 10.0)
        mkt = {"price": 10.0, "yesterday_close": 10.0,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertEqual(detail.today_profit, 0.0)
        self.assertEqual(detail.profit, 0.0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_sub_cent_price_change(self, mock_open, mock_td):
        """价格变动不足 1 分钱 → 小数精度正确。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "毫厘波动", "000001", 10000, 1.0)
        mkt = {"price": 1.0001, "yesterday_close": 1.0000,
               "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        detail = _compute_detail_row(h, mkt)
        self.assertAlmostEqual(detail.today_profit, 1.0, places=2)


# ═══════════════════════════════════════════════════════════
# Y2-8: 债券违约
# ═══════════════════════════════════════════════════════════

class TestBondDefaultY2(unittest.TestCase):
    """债券违约场景。"""

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_bond_fund_with_defaulted_bond(self, mock_batch, mock_ind):
        """债券基金含违约债券（价格暴跌）→ 穿透不崩溃。"""
        from src.python.report.penetration import compute_penetration_top10

        mock_batch.return_value = {"008888": {"holdings": [
            {"name": "17华置债", "code": "123456", "ratio": 30.0},
            {"name": "国债1901", "code": "019611", "ratio": 70.0},
        ]}}
        bond_fund = _make_holding("XX纯债", "008888", 1000, 1.0, account="支付宝")
        # 违约债券导致基金净值暴跌
        details = [_make_detail_row("008888", 500.0, "XX纯债")]
        result = compute_penetration_top10([bond_fund], details)

        defaulted_items = [i for i in result["top10"] if "17华置" in i["name"]]
        if defaulted_items:
            item = defaulted_items[0]
            # 违约债券市值 = 基金市值500 * 30% = 150
            self.assertAlmostEqual(item["mv"], 150.0, delta=0.01)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_bond_fund_zero_nav(self, mock_batch, mock_ind):
        """债券违约后净值为 0 → 穿透不崩溃。"""
        from src.python.report.penetration import compute_penetration_top10

        mock_batch.return_value = {"008888": {"holdings": [
            {"name": "违约债", "code": "123456", "ratio": 100.0},
        ]}}
        h = _make_holding("XX纯债", "008888", 1000, 1.0, account="支付宝")
        details = [_make_detail_row("008888", 0.0, "XX纯债")]
        result = compute_penetration_top10([h], details)
        # 净值为 0 → 穿透市值也为 0
        if result["top10"]:
            self.assertEqual(result["top10"][0]["mv"], 0.0)


# ═══════════════════════════════════════════════════════════
# Y2-9: 同基金多层份额
# ═══════════════════════════════════════════════════════════

class TestSameFundMultiShareY2(unittest.TestCase):
    """同一基金多份额（A/C 类）分类正确。"""

    def test_a_c_share_classification(self):
        """同一基金 A 类和 C 类 → 分类为 ACTIVE_EQUITY。"""
        from src.python.report.penetration import classify_penetration
        a = _make_holding("易方达蓝筹精选A", "005827", 100, 2.0, account="支付宝")
        c = _make_holding("易方达蓝筹精选C", "005828", 100, 2.0, account="支付宝")
        for h in (a, c):
            cat = classify_penetration(h)
            self.assertEqual(cat, "active_equity")

    def test_etf_a_c_share_all_etf(self):
        """ETF A/C 类 → 均归为 ETF。"""
        from src.python.report.penetration import classify_penetration
        a = _make_holding("科创50ETF A", "588000", 100, 1.0, account="证券")
        c = _make_holding("科创50ETF C", "588001", 100, 1.0, account="证券")
        for h in (a, c):
            cat = classify_penetration(h)
            self.assertEqual(cat, "etf")

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch", return_value={"004231": None, "004232": None})
    def test_a_c_merged_in_penetration(self, mock_batch, mock_ind):
        """A/C 类份额 → 在穿透中不被额外处理，不崩溃。"""
        from src.python.report.penetration import compute_penetration_top10

        funds = [
            _make_holding("中欧医疗A", "004231", 500, 2.0, account="支付宝"),
            _make_holding("中欧医疗C", "004232", 300, 2.0, account="支付宝"),
        ]
        details = [
            _make_detail_row("004231", 1000.0, "中欧医疗A"),
            _make_detail_row("004232", 600.0, "中欧医疗C"),
        ]
        result = compute_penetration_top10(funds, details)
        self.assertIsNotNone(result)
        # 两个基金都无持仓数据 → failed_count=2
        self.assertEqual(result["summary"]["failed_funds"], 2)


# ═══════════════════════════════════════════════════════════
# Y2-10: 跨市场停牌时差
# ═══════════════════════════════════════════════════════════

class TestCrossMarketSuspensionY2(unittest.TestCase):
    """港股通/A 股跨市场停牌时差。"""

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_a_share_suspended_h_trade_normal(self, mock_open, mock_td):
        """A 股停牌但港股交易 → 各自处理，不互扰。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row

        # A 股停牌
        a = Holding("证券", "中国平安", "601318", 100, 50.0)
        a_mkt = {"price": 50.0, "yesterday_close": 50.0,
                 "price_date": "2026-06-15", "source": "腾讯财经", "source_api": "tencent"}
        # 港股正常交易
        h = Holding("证券", "中国平安", "02318", 200, 60.0)
        h_mkt = {"price": 62.0, "yesterday_close": 61.0,
                 "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}

        a_detail = _compute_detail_row(a, a_mkt)
        h_detail = _compute_detail_row(h, h_mkt)

        # A 停牌 → today_profit=0
        self.assertEqual(a_detail.today_profit, 0.0)
        # 港股正常 → today_profit>0
        self.assertGreater(h_detail.today_profit, 0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_hk_suspended_a_trade_normal(self, mock_open, mock_td):
        """港股停牌但 A 股交易 → 各自处理，不互扰。"""
        mock_td.return_value = "2026-07-01"
        from src.python.report.market_value import _compute_detail_row

        # 港股停牌
        h = Holding("证券", "腾讯控股", "00700", 100, 300.0)
        h_mkt = {"price": 300.0, "yesterday_close": 300.0,
                 "price_date": "2026-06-20", "source": "腾讯财经", "source_api": "tencent"}
        # A 股正常交易
        a = Holding("证券", "贵州茅台", "600519", 50, 200.0)
        a_mkt = {"price": 2100.0, "yesterday_close": 2080.0,
                 "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}

        h_detail = _compute_detail_row(h, h_mkt)
        a_detail = _compute_detail_row(a, a_mkt)

        # 港股停牌 → today_profit=0
        self.assertEqual(h_detail.today_profit, 0.0)
        # A 股正常 → today_profit>0
        self.assertGreater(a_detail.today_profit, 0)


if __name__ == "__main__":
    unittest.main()

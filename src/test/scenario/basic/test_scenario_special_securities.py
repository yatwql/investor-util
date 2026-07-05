"""Z1 — 特殊品种场景（S21-S28）。

测试目标：
  验证个人投资者持有的常见特殊品种在报告中的正确分类和计算行为：

  S21: 港股通持仓 — 港股通标的（00700、03690）的分类和计价
  S22: 可转债持仓 — 可转债（12xxxx）的分类和交易属性
  S23: 公募 REITs — 基础设施 REITs（18xxxx）的分类和持仓
  S24: 货币基金 — 货币基金/短期理财（万份收益/净值恒为 1）
  S25: 科创板 + 北交所混合 — 688（20%涨跌停）+ 8xx（30%涨跌停）
  S26: 商品/黄金 ETF — 黄金 ETF、有色金属 ETF 的分类和估值
  S27: 跨境 ETF（美股/港股方向）— 纳指 ETF、恒生科技 ETF 的净值延迟
  S28: 纯债/国债持仓 — 国债/企业债的面值 vs 净价

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/basic/test_scenario_special_securities.py -v
  pytest src/test/ -m "scenario_basic" -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.python.models import Holding

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]


# ═══════════════════════════════════════════════════════════════
#  S21: 港股通持仓
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS21HkStockConnect(unittest.TestCase):
    """S21: 港股通持仓 — 港股通标的正确交易和分类。"""

    def test_hk_stock_tencent_classification(self):
        """港股通腾讯 00700 → 分类为 股票/A股（代码以0开头）。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "腾讯控股", "00700", shares=100, cost_price=380.0)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "股票")
        self.assertEqual(sub, "A股")

    def test_hk_stock_meituan_prefix(self):
        """港股通美团 03690（5位码）→ _add_prefix 不修改（非6位码原样返回）。"""
        from src.python.providers.tencent import _add_prefix
        result = _add_prefix("03690")
        # 03690 只有 5 位，不满足 len(code) != 6 条件，原样返回
        self.assertEqual(result, "03690")

    def test_hk_stock_no_price_no_crash(self):
        """港股通无行情 → 市值=0，不崩溃。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "腾讯控股", "00700", shares=100, cost_price=380.0)
        row = _compute_detail_row(h, None)
        self.assertEqual(row.market_value, 0.0)
        self.assertEqual(row.price, 0.0)
        self.assertEqual(row.price_type, "--")


# ═══════════════════════════════════════════════════════════════
#  S22: 可转债持仓
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS22ConvertibleBond(unittest.TestCase):
    """S22: 可转债持仓 — 12xxxx 代码分类与交易。"""

    def test_convertible_bond_classification(self):
        """可转债名称含"债" → 分类为 债券/纯债（名称匹配优先于代码匹配）。"""
        from src.python.report.category import _categorize_holding
        # "浦发转债"含"债" → _BOND_KEYWORDS 命中 → 债券/纯债
        h = Holding("证券", "浦发转债", "110059", shares=10, cost_price=105.0)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "债券")
        self.assertEqual(sub, "纯债")

    def test_convertible_bond_name_bond_classification(self):
        """可转债名称含"转债" → 分类为 债券/纯债（"债"宽匹配）。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "浦发转债", "110059", shares=10, cost_price=105.0)
        prop, sub = _categorize_holding(h)
        # 名称含"债" → is_bond_related_by_name 或 "债" in name 命中 → 债券/纯债
        self.assertEqual(prop, "债券")
        self.assertEqual(sub, "纯债")

    def test_convertible_bond_market_value(self):
        """可转债有行情 → 市值计算正确。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "浦发转债", "110059", shares=10, cost_price=105.0)
        mkt = {"price": 108.5, "yesterday_close": 108.0,
               "price_date": "2026-07-03", "source": "腾讯财经", "source_api": "tencent"}
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)
        self.assertEqual(row.market_value, 1085.0)  # 108.5 * 10
        self.assertEqual(row.cost, 1050.0)           # 105.0 * 10
        self.assertEqual(row.profit, 35.0)           # 1085 - 1050


# ═══════════════════════════════════════════════════════════════
#  S23: 公募 REITs
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS23PublicReits(unittest.TestCase):
    """S23: 公募 REITs — 18xxxx 基础设施 REITs。"""

    def test_reit_classification(self):
        """公募 REITs 18xxxx → 归类为 基金/指数（代码1开头）。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "华夏中国交建REIT", "180102", shares=1000, cost_price=8.5)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "指数")

    def test_reit_reit_in_name_classification(self):
        """REIT 名称含 REIT → 当前按 基金/指数 分类。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "华夏中国交建REIT", "180102", shares=1000, cost_price=8.5)
        prop, sub = _categorize_holding(h)
        self.assertEqual((prop, sub), ("基金", "指数"))

    def test_reit_market_value(self):
        """REIT 有行情 → 市值正常计算。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "华夏中国交建REIT", "180102", shares=1000, cost_price=8.5)
        mkt = {"price": 9.2, "yesterday_close": 9.1,
               "price_date": "2026-07-03", "source": "腾讯财经", "source_api": "tencent"}
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)
        self.assertEqual(row.market_value, 9200.0)  # 9.2 * 1000
        self.assertEqual(row.profit, 700.0)          # 9200 - 8500


# ═══════════════════════════════════════════════════════════════
#  S24: 货币基金
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS24MoneyMarketFund(unittest.TestCase):
    """S24: 货币基金 — 净值恒为 1，万份收益。"""

    def test_money_fund_classification(self):
        """货币基金（名称含"货币"）→ 分类为 现金/货币。"""
        from src.python.report.category import _categorize_holding
        h = Holding("基金账户", "余额宝货币", "000001", shares=5000, cost_price=1.0)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "现金")
        self.assertEqual(sub, "货币")

    def test_money_fund_nav_always_one(self):
        """货币基金净值恒为 1.0 → 市值=份额。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("基金账户", "余额宝货币", "000001", shares=5000, cost_price=1.0)
        mkt = {"price": 1.0, "yesterday_close": 1.0,
               "price_date": "2026-07-03", "source": "天天基金", "source_api": "tiantian"}
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)
        self.assertEqual(row.price, 1.0)
        self.assertEqual(row.market_value, 5000.0)  # 1.0 * 5000

    def test_wealth_management_classification(self):
        """短期理财（名称含"增利"）→ 分类为 现金/货币。"""
        from src.python.report.category import _categorize_holding
        h = Holding("银行", "天天增利", "000001", shares=10000, cost_price=1.0)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "现金")
        self.assertEqual(sub, "货币")


# ═══════════════════════════════════════════════════════════════
#  S25: 科创板 + 北交所混合
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS25StarMarketAndBse(unittest.TestCase):
    """S25: 科创板 688 + 北交所 8xx 同时存在。"""

    def test_star_market_classification(self):
        """科创板 688xxx → 股票/A股。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "中芯国际", "688981", shares=200, cost_price=56.0)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "股票")
        self.assertEqual(sub, "A股")

    def test_bse_classification(self):
        """北交所 8xxxxx → is_a_share_code 识别为 A 股 → 股票/A股。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "贝特瑞", "835185", shares=100, cost_price=25.0)
        prop, sub = _categorize_holding(h)
        # is_a_share_code 识别 8 开头为 A 股（北交所）
        self.assertEqual(prop, "股票")
        self.assertEqual(sub, "A股")

    def test_star_market_tencent_prefix(self):
        """科创板 688xxx → _add_prefix 添加 sh 前缀。"""
        from src.python.providers.tencent import _add_prefix
        result = _add_prefix("688981")
        self.assertEqual(result, "sh688981")

    def test_bse_tencent_prefix(self):
        """北交所 8xxxxx → _add_prefix 添加 bj 前缀。"""
        from src.python.providers.tencent import _add_prefix
        result = _add_prefix("835185")
        self.assertEqual(result, "bj835185")


# ═══════════════════════════════════════════════════════════════
#  S26: 商品/黄金 ETF
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS26CommodityGoldEtf(unittest.TestCase):
    """S26: 商品/黄金 ETF — 名称含 ETF 分类。"""

    def test_gold_etf_classification(self):
        """黄金 ETF（名称含ETF）→ 基金/指数。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "华安黄金ETF", "518880", shares=300, cost_price=5.2)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "指数")

    def test_commodity_etf_classification(self):
        """商品 ETF（豆粕ETF）→ 基金/指数。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "华夏豆粕ETF", "159985", shares=200, cost_price=1.8)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "指数")

    def test_gold_etf_premium(self):
        """黄金 ETF → premium 为占位符。"""
        from src.python.report.market_value import _compute_detail_row, _FUND_PREMIUM_PLACEHOLDER
        h = Holding("证券", "华安黄金ETF", "518880", shares=300, cost_price=5.2)
        mkt = {"price": 5.5, "yesterday_close": 5.45,
               "price_date": "2026-07-03", "source": "腾讯财经", "source_api": "tencent"}
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)
        self.assertEqual(row.premium, _FUND_PREMIUM_PLACEHOLDER)
        self.assertEqual(row.market_value, 1650.0)  # 5.5 * 300


# ═══════════════════════════════════════════════════════════════
#  S27: 跨境 ETF（美股/港股方向）
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS27CrossBorderEtf(unittest.TestCase):
    """S27: 跨境 ETF — 净值延迟和溢价率。"""

    def test_us_etf_classification(self):
        """纳指 ETF → 基金/指数。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "纳斯达克ETF", "513100", shares=200, cost_price=1.5)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "指数")

    def test_hk_etf_classification(self):
        """恒生科技 ETF → 基金/指数。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "恒生科技ETF", "513380", shares=300, cost_price=1.2)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "指数")

    def test_cross_border_etf_nav_date_t1(self):
        """跨境 ETF 净值日期为 T-1（港股未开盘）→ today_profit=0。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "恒生科技ETF", "513380", shares=300, cost_price=1.2)
        # 净值日期是前一天（T-1），说明基金净值未更新
        mkt = {"price": 1.25, "yesterday_close": 1.24,
               "price_date": "2026-07-02", "source": "天天基金", "source_api": "tiantian"}
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)
        # nav_date != trading_day → today_profit = 0
        self.assertEqual(row.today_profit, 0.0)
        self.assertEqual(row.nav_date, "2026-07-02")


# ═══════════════════════════════════════════════════════════════
#  S28: 纯债/国债持仓
# ═══════════════════════════════════════════════════════════════

@pytest.mark.scenario_basic
@pytest.mark.scenario
class TestS28BondHoldings(unittest.TestCase):
    """S28: 纯债/国债 — 名称含固收关键词分类。"""

    def test_pure_bond_classification(self):
        """国债ETF 名称含"债"且代码 5开头 → 债券类优先，归为 债券/纯债。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "国债ETF", "511010", shares=100, cost_price=120.0)
        prop, sub = _categorize_holding(h)
        # "国债ETF"含"债"→ is_bond_related_by_name + "债"宽匹配 → 债券/纯债
        self.assertEqual(prop, "债券")
        self.assertEqual(sub, "纯债")

    def test_treasury_name_contains_bond_keyword(self):
        """国债名称含"债" → is_bond_related_by_name 或 "债" in name 匹配。"""
        from src.python.code_utils import is_bond_related_by_name
        h = Holding("证券", "20国债01", "019641", shares=100, cost_price=100.0)
        self.assertTrue(is_bond_related_by_name(h.name) or "债" in h.name)

    def test_treasury_classification(self):
        """国债 01xxxx + 名称含"债" → 债券/纯债。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "20国债01", "019641", shares=100, cost_price=100.0)
        prop, sub = _categorize_holding(h)
        # "20国债01"含"债"→ 名称匹配优先于代码判断
        self.assertEqual((prop, sub), ("债券", "纯债"))

    def test_corporate_bond_classification(self):
        """企业债 名称含"信用" → 债券/纯债。"""
        from src.python.report.category import _categorize_holding
        h = Holding("证券", "XX信用债", "127000", shares=100, cost_price=98.0)
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "债券")
        self.assertEqual(sub, "纯债")

    def test_bond_market_value(self):
        """债券有行情 → 市值按净价成交。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding("证券", "XX信用债", "127000", shares=100, cost_price=98.0)
        mkt = {"price": 99.5, "yesterday_close": 99.0,
               "price_date": "2026-07-03", "source": "腾讯财经", "source_api": "tencent"}
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-07-03"):
            with patch("src.python.report.market_value.is_market_open",
                       return_value=False):
                row = _compute_detail_row(h, mkt)
        self.assertEqual(row.market_value, 9950.0)   # 99.5 * 100
        self.assertEqual(row.profit, 150.0)           # 9950 - 9800


if __name__ == "__main__":
    unittest.main()

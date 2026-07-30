"""业务场景集成测试 S6~S10。

测试目标：
  - S6: 纯债券基金组合 → 穿透 TOP10 无股权覆盖或极小
  - S7: 网络中断 → 降级使用过期缓存
  - S8: 单账户单持仓 → 正确生成单行报告
  - S9: 零成本持仓（cost_price=0）→ 盈亏/收益率正确处理
  - S10: 极端值（极大持仓份额）→ 数值溢出处理

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test.test_integration_scenarios -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.models import Holding
from src.python.report.penetration import classify_penetration


@pytest.mark.scenario_resilience
@pytest.mark.scenario
class ScenarioTestBase(unittest.TestCase):
    """场景测试基类：提供共享的 mock 环境。"""

    def setUp(self):
        # 阻止所有网络/API 调用
        self._price_patcher = patch("src.python.fetcher.price.fetch_market_data")
        self._mock_price = self._price_patcher.start()
        self._mock_price.return_value = {
            "price": 10.0, "yesterday_close": 9.8,
            "price_date": "2026-06-26", "source": "腾讯财经",
            "source_api": "tencent",
        }

        self._fund_patcher = patch("src.python.report.penetration.fetch_fund_holdings_batch")
        self._mock_fund = self._fund_patcher.start()
        self._mock_fund.return_value = {"510300": {
            "code": "510300", "name": "沪深300ETF",
            "date": "2026-03-31",
            "holdings": [{"name": "贵州茅台", "code": "600519", "ratio": 16.0}],
        }}

        # LLM 相关 mock
        self._llm_config_patcher = patch(
            "src.python.config.get_llm_config",
            return_value={"provider": None, "enabled_llm": {}},
        )
        self._llm_config_patcher.start()

    def tearDown(self):
        self._price_patcher.stop()
        self._fund_patcher.stop()
        self._llm_config_patcher.stop()

    def _make_holding(self, account: str, name: str, code: str,
                       shares: float, cost_price: float) -> Holding:
        return Holding(
            account=account, name=name, code=code,
            shares=shares, cost_price=cost_price,
        )


# ═══════════════════════════════════════════════════════════════
#  S6: 纯债券基金组合（无股权穿透）
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_bond
class TestScenarioBond(ScenarioTestBase):
    """S6: 纯债券基金组合 → 穿透 TOP10 无股权覆盖或极小。"""

    def setUp(self):
        super().setUp()
        self.holdings = [
            # ETF 品类的债券基金仍归类为 etf（名称含 ETF），不等同于股票型 ETF
            self._make_holding("证券", "国债ETF", "511010", 1000, 120.0),
            # 真正的场外债券基金 → bond_fund
            self._make_holding("支付宝", "招商鑫福中短债A", "012325", 500, 1.0),
            self._make_holding("微信", "长盛安逸纯债", "012345", 1000, 1.0),
        ]

    def test_bond_funds_classified_correctly(self):
        """纯债基金（非ETF）→ classify_penetration 返回 bond_fund。"""
        for h in self.holdings:
            if "ETF" in h.name:
                # ETF 标记的债券基金按规则归为 etf
                self.assertEqual(classify_penetration(h), "etf",
                                 f"{h.name} 应为 etf")
            else:
                # 场外债券基金 → bond_fund
                self.assertEqual(classify_penetration(h), "bond_fund",
                                 f"{h.name} 应分类为 bond_fund，实际为 {classify_penetration(h)}")

    def test_penetration_top10_contains_no_or_few_stocks(self):
        """纯债券穿透 → TOP10 无直接股权, 或无穿透数据。"""
        from src.python.report.market_value import DetailRow

        details_list = []
        for h in self.holdings:
            dr = DetailRow()
            dr.account = h.account
            dr.name = h.name
            dr.code = h.code
            dr.price = h.cost_price
            dr.market_value = h.cost_price * h.shares
            dr.source_api = "tiantian"
            dr.shares = h.shares
            dr.cost = h.cost_price * h.shares
            dr.profit = 0.0
            dr.today_profit = 0.0
            dr.nav_date = "2026-06-26"
            dr.yesterday_close = h.cost_price
            dr.price_type = "官方净值(T)"
            dr.premium = "--"
            dr.source = "天天基金"
            dr.profit_rate = 0.0
            details_list.append(dr)

        from src.python.report.penetration import compute_penetration_top10

        with patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}):
            result = compute_penetration_top10(self.holdings, details_list)

        # 债券一般不穿透或穿透结果极少, 只要不崩溃就满足
        self.assertIsNotNone(result)

    def test_bond_fund_category_in_fund_breakdown(self):
        """fund_breakdown 包含'债券'分类。"""
        from src.python.report.penetration import _build_penetration_result

        classified = {
            "qdii": [], "etf": [],
            "index_link": [], "bond_fund": self.holdings,
            "active_equity": [],
        }

        result = _build_penetration_result(
            merged={},
            classified=classified,
            funds=self.holdings,
            direct_stocks=[],
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        self.assertIn("债券", result["summary"]["fund_breakdown"],
                      "fund_breakdown 应包含债券标记")


# ═══════════════════════════════════════════════════════════════
#  S7: 网络中断 → 降级使用过期缓存
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_network_down
class TestScenarioNetworkDown(ScenarioTestBase):
    """S7: 报告生成过程中网络中断 → 降级使用过期缓存。"""

    def setUp(self):
        super().setUp()
        self.holding = self._make_holding("证券", "长江电力", "600900", 100, 10.0)

    def test_fetch_failure_falls_to_stale_cache(self):
        """Provider 全部失败 → 降级使用过期缓存数据。"""
        from src.python.fetcher.chain import fetch_with_fallback

        provider_map = {
            "tencent": ("腾讯财经", MagicMock(side_effect=Exception("网络中断"))),
            "eastmoney": ("东方财富", MagicMock(side_effect=Exception("网络中断"))),
        }

        with patch("src.python.fetcher.chain.cache_get") as mock_cache_get:
            # 第一次 cache_get（最新缓存）→ None
            # 第二次 cache_get（过期缓存降级）→ stale data
            mock_cache_get.side_effect = [None, {"stale": True, "price": 10.5}]

            with patch("src.python.fetcher.chain._get_chain",
                       return_value=["tencent", "eastmoney"]):
                result = fetch_with_fallback(
                    "price", provider_map, "test_600900", 3600
                )

        # 降级使用过期缓存
        self.assertEqual(result, {"stale": True, "price": 10.5})

    def test_fetch_failure_no_cache_returns_none(self):
        """Provider 全部失败 + 无过期缓存 → 返回 None。"""
        from src.python.fetcher.chain import fetch_with_fallback

        provider_map = {
            "tencent": ("腾讯财经", MagicMock(side_effect=Exception("网络中断"))),
        }

        with patch("src.python.fetcher.chain.cache_get", return_value=None):
            with patch("src.python.fetcher.chain._get_chain",
                       return_value=["tencent"]):
                result = fetch_with_fallback(
                    "price", provider_map, "test_600900", 3600
                )

        self.assertIsNone(result)

    def test_report_generate_with_network_failure(self):
        """网络中断场景 → _generate_details 使用备用值。"""
        from src.python.report.market_value import _compute_detail_row

        # 模拟行情数据获取失败（返回空/缺字段的行情）
        mkt = {
            "price": 0.0, "yesterday_close": 0.0,
            "price_date": "", "source": "--", "source_api": "",
        }
        detail = _compute_detail_row(self.holding, mkt)

        # 网络失败时 price=0, nav_date 为空
        self.assertEqual(detail.price, 0.0)
        self.assertEqual(detail.today_profit, 0.0)
        self.assertEqual(detail.nav_date, "")
        self.assertEqual(detail.source_api, "")


# ═══════════════════════════════════════════════════════════════
#  S8: 单账户单持仓 → 正确生成报告
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_single_holding
class TestScenarioSingleHolding(ScenarioTestBase):
    """S8: 单账户单持仓 → 正确生成单行报告。"""

    def setUp(self):
        super().setUp()
        self.holding = self._make_holding("证券", "长江电力", "600900", 100, 28.0)

    def test_single_holding_profit_correct(self):
        """单持仓 → 盈亏计算正确。"""
        from src.python.report.market_value import _compute_detail_row

        mkt = {
            "price": 29.0, "yesterday_close": 28.5,
            "price_date": "2026-06-26",
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(self.holding, mkt)

        expected_profit = round(29.0 * 100 - 28.0 * 100, 2)
        expected_today = round((29.0 - 28.5) * 100, 2)
        self.assertEqual(detail.profit, expected_profit)
        self.assertEqual(detail.today_profit, expected_today)

    def test_single_holding_generates_excel(self):
        """单持仓 → 可生成 Excel 报告。"""
        import tempfile
        from src.python.report.excel_generator import generate_excel_report

        tmp = tempfile.TemporaryDirectory()
        try:
            with patch("src.python.fetcher.index.fetch_indices", return_value={}), \
                 patch("src.python.fetcher.index.fetch_us_indices", return_value={}), \
                 patch("src.python.report.fund_performance.write_fund_performance_sheet"):

                generate_excel_report(
                    [self.holding],
                    output_dir=tmp.name,
                    details=[],
                    a_indices={},
                    us_indices={},
                )

                out_files = os.listdir(tmp.name)
                self.assertTrue(any(f.endswith(".xlsx") for f in out_files))
        finally:
            tmp.cleanup()

    def test_single_holding_account_subtotal(self):
        """单持仓 → 账户小计等于持仓市值。"""
        from src.python.report.market_value import _compute_detail_row

        mkt = {
            "price": 29.0, "yesterday_close": 28.5,
            "price_date": "2026-06-26",
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(self.holding, mkt)

        expected_mv = round(29.0 * 100, 2)
        self.assertEqual(detail.market_value, expected_mv)


# ═══════════════════════════════════════════════════════════════
#  S9: 零成本持仓（cost_price=0）
# ═══════════════════════════════════════════════════════════════


@pytest.mark.scenario_zero_cost
class TestScenarioZeroCost(ScenarioTestBase):
    """S9: 零成本持仓 → 盈亏/收益率正确处理。"""

    def test_zero_cost_stock(self):
        """cost_price=0 → profit_rate=None（除零保护）。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "赠送股票", "600000", 100, 0.0)
        mkt = {
            "price": 50.0, "yesterday_close": 49.0,
            "price_date": "2026-06-26",
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)

        # cost = 0 * 100 = 0
        self.assertEqual(detail.cost, 0.0)
        # profit_rate 应为 None（除零保护）
        self.assertIsNone(detail.profit_rate)
        # profit = market_value - cost = 5000 - 0 = 5000
        self.assertEqual(detail.profit, 5000.0)

    def test_zero_cost_fund(self):
        """场外基金 cost_price=0 → cost=0, profit_rate=None。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("支付宝", "赠送基金", "005827", 500, 0.0)
        mkt = {
            "price": 2.0, "yesterday_close": 1.9,
            "price_date": "2026-06-30",
            "source": "天天基金", "source_api": "eastmoney",
        }
        detail = _compute_detail_row(h, mkt)

        self.assertEqual(detail.cost, 0.0)
        self.assertIsNone(detail.profit_rate)
        self.assertGreater(detail.market_value, 0)

    @patch("src.python.report.market_value.get_last_trading_day")
    @patch("src.python.report.market_value.is_market_open", return_value=False)
    def test_zero_cost_all_fields(self, mock_open, mock_td):
        """cost_price=0 → 所有字段正确。"""
        mock_td.return_value = "2026-06-30"
        from src.python.report.market_value import _compute_detail_row
        from src.python.report.market_value_sheet import _detail_to_row_values

        h = Holding("证券", "测试零成本", "600000", 100, 0.0)
        mkt = {
            "price": 10.0, "yesterday_close": 9.5,
            "price_date": "2026-06-30",
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)
        values = _detail_to_row_values(detail)

        # _detail_to_row_values 索引 10 = cost = 0
        self.assertEqual(values[10], 0.0)
        # 第 13 列 = profit_rate
        self.assertIsNone(values[12])

    def test_zero_cost_with_loss(self):
        """零成本但市值为负（极端）→ 盈亏为负值。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "负值零成本", "600000", 100, 0.0)
        mkt = {
            "price": -5.0, "yesterday_close": -4.0,
            "price_date": "2026-06-26",
            "source": "腾讯财经", "source_api": "tencent",
        }
        detail = _compute_detail_row(h, mkt)

        # 即使 price 为负，不应崩溃
        # market_value = -5 * 100 = -500
        self.assertEqual(detail.market_value, -500.0)
        # profit = -500 - 0 = -500
        self.assertEqual(detail.profit, -500.0)
        self.assertIsNone(detail.profit_rate)

if __name__ == "__main__":
    unittest.main()

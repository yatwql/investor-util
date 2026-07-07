"""HTML 报告数据构建器边缘/异常测试 — 降级与容错。

测试目标：
  - _calc_yield_text：零/负价格、类型异常等边界
  - _coverage_text：研报数为 0 边界
  - _load_profit_forecast：API 失败降级
  - _build_category_data：分红数据 API 异常降级

运行：
  pytest src/test/unit/report/test_html_builders_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.models import Holding
from src.python.report.market_value import DetailRow

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


class TestCalcYieldTextEdge(unittest.TestCase):
    """_calc_yield_text 边界/异常情况。"""

    def setUp(self):
        from src.python.report.category import calc_yield_text
        self.fn = calc_yield_text

    def test_price_zero(self):
        """最新价为 0 → "--"。"""
        d = MagicMock(spec=DetailRow)
        d.price = 0.0
        result = self.fn("600900", d, {"600900": {"avg_dividend": 0.85}})
        self.assertEqual(result, "--")

    def test_price_negative(self):
        """最新价为负 → "--"。"""
        d = MagicMock(spec=DetailRow)
        d.price = -1.0
        result = self.fn("600900", d, {"600900": {"avg_dividend": 0.85}})
        self.assertEqual(result, "--")

    def test_detail_none(self):
        """detail 对象为 None → price=0 → "--"。"""
        result = self.fn("600900", None, {"600900": {"avg_dividend": 0.85}})
        self.assertEqual(result, "--")

    def test_division_by_zero_safe(self):
        """price=0 不会触发除零错误。"""
        d = MagicMock(spec=DetailRow)
        d.price = 0.0
        result = self.fn("600900", d, {"600900": {"avg_dividend": 0.85}})
        self.assertEqual(result, "--")

    def test_info_value_error_handled(self):
        """avg_dividend 为非数值类型 → try/except 兜底返回 "--"。"""
        d = MagicMock(spec=DetailRow)
        d.price = 50.0
        result = self.fn("600900", d, {"600900": {"avg_dividend": "invalid"}})
        self.assertEqual(result, "--")


class TestCoverageTextEdge(unittest.TestCase):
    """_coverage_text 边界情况。"""

    def setUp(self):
        from src.python.report.html_builders import _coverage_text
        self.fn = _coverage_text

    def test_reports_is_zero(self):
        """研报数为 0 → "--"。"""
        result = self.fn("000001", {"000001": {"reports": 0, "eps_2026e": 1.23}})
        self.assertEqual(result, "--")


class TestLoadProfitForecast(unittest.TestCase):
    """_load_profit_forecast 容错测试。"""

    def test_success_returns_dict(self):
        """正常加载 → 返回字典。"""
        from src.python.report.html_builders import _load_profit_forecast
        with patch("src.python.providers.akshare_extras.get_profit_forecast",
                   return_value={"000001": {"reports": 5}}):
            result = _load_profit_forecast()
        self.assertEqual(result, {"000001": {"reports": 5}})

    def test_api_failure_returns_empty(self):
        """API 失败 → 返回空字典。"""
        from src.python.report.html_builders import _load_profit_forecast
        with patch("src.python.providers.akshare_extras.get_profit_forecast",
                   side_effect=Exception("API 失败")):
            result = _load_profit_forecast()
        self.assertEqual(result, {})


class TestBuildCategoryDataDividendDegradation(unittest.TestCase):
    """_build_category_data 分红 API 异常降级。"""

    def setUp(self):
        self.holdings = [
            Holding("证券账户", "长江电力", "600900", 100, 50.0),
            Holding("证券账户", "工商银行", "601398", 200, 6.0),
        ]
        self.detail_map = {}
        for h in self.holdings:
            d = MagicMock(spec=DetailRow)
            d.market_value = h.shares * 55.0 if h.code == "600900" else h.shares * 6.5
            d.cost = h.shares * h.cost_price
            d.profit = d.market_value - d.cost
            d.profit_rate = d.profit / d.cost if d.cost > 0 else 0.0
            d.today_profit = 0.0
            d.price = 55.0 if h.code == "600900" else 6.5
            d.name = h.name
            d.code = h.code
            self.detail_map[h.code] = d

    def test_dividend_api_failure_yields_dash(self):
        """get_dividend_data 抛异常 → 所有 yield_text 为 "--"。"""
        from src.python.report.html_builders import _build_category_data

        with patch("src.python.providers.akshare_extras.get_dividend_data",
                   side_effect=Exception("API 失败")):
            result, dividend_success = _build_category_data(self.holdings, list(self.detail_map.values()))
            self.assertFalse(dividend_success)

        for group in result:
            for item in group["items"]:
                self.assertEqual(item.get("yield_text"), "--",
                                 f"{item['name']} 的 yield_text 应为 --")


if __name__ == "__main__":
    unittest.main()

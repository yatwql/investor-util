"""HTML 报告数据构建器单元测试 — 正常路径。

测试目标：
  - _calc_yield_text：正常/缺失数据下的文本计算
  - _coverage_text：正常格式化和缺失数据
  - _build_category_data：标准分红数据加载和正常路径

运行：
  pytest src/test/unit/report/test_html_builders.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.models import Holding
from src.python.report.market_value import DetailRow

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestCalcYieldText(unittest.TestCase):
    """_calc_yield_text 基础功能测试。"""

    def setUp(self):
        from src.python.report.category import calc_yield_text
        self.fn = calc_yield_text
        self.d = MagicMock(spec=DetailRow)
        self.d.price = 50.0
        self.d.cost = 0.0
        self.d.market_value = 5000.0
        self.d.profit = 0.0
        self.d.profit_rate = 0.0
        self.d.today_profit = 0.0

    def test_normal_calculation(self):
        """正常数据 → 正确的股息率百分比。"""
        dividend_data = {"600900": {"avg_dividend": 0.85}}
        result = self.fn("600900", self.d, dividend_data)
        self.assertEqual(result, "1.70%")  # 0.85 / 50.0 * 100

    def test_code_not_in_dividend_data(self):
        """代码不在分红数据中 → "--"。"""
        result = self.fn("600900", self.d, {})
        self.assertEqual(result, "--")

    def test_avg_dividend_none(self):
        """avg_dividend 为 None → "--"。"""
        dividend_data = {"600900": {"avg_dividend": None}}
        result = self.fn("600900", self.d, dividend_data)
        self.assertEqual(result, "--")

    def test_avg_dividend_missing_key(self):
        """avg_dividend key 缺失 → "--"。"""
        dividend_data = {"600900": {}}
        result = self.fn("600900", self.d, dividend_data)
        self.assertEqual(result, "--")


class TestCoverageText(unittest.TestCase):
    """_coverage_text 基础格式化测试。"""

    def setUp(self):
        from src.python.report.html_builders import _coverage_text
        self.fn = _coverage_text

    def test_reports_and_eps(self):
        """有研报数 + EPS → 格式化文本。"""
        result = self.fn("000001", {"000001": {"reports": 5, "eps_2025e": 1.23}})
        self.assertEqual(result, "5家研报 EPS¥1.23")

    def test_reports_only(self):
        """仅研报数 → 显示研报家数。"""
        result = self.fn("000001", {"000001": {"reports": 3}})
        self.assertEqual(result, "3家研报")

    def test_eps_is_none_with_reports(self):
        """EPS 为 None 但有研报数 → 显示研报家数。"""
        result = self.fn("000001", {"000001": {"reports": 2, "eps_2025e": None}})
        self.assertEqual(result, "2家研报")

    def test_no_data(self):
        """代码在字典中但无有用字段 → "--"。"""
        result = self.fn("000001", {"000001": {}})
        self.assertEqual(result, "--")

    def test_code_not_in_dict(self):
        """代码不在盈利预测字典中 → "--"。"""
        result = self.fn("999999", {"000001": {"reports": 5}})
        self.assertEqual(result, "--")

    def test_empty_dict(self):
        """盈利预测为空字典 → "--"。"""
        result = self.fn("000001", {})
        self.assertEqual(result, "--")


class TestBuildCategoryDataDividend(unittest.TestCase):
    """_build_category_data 分红数据加载正常路径。"""

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

    def test_dividend_api_success(self):
        """get_dividend_data 正常 → yield_text 正确计算。"""
        from src.python.report.html_builders import _build_category_data

        with patch("src.python.providers.akshare_extras.get_dividend_data",
                   return_value={"600900": {"avg_dividend": 0.85},
                                 "601398": {"avg_dividend": 0.30}}):
            result = _build_category_data(self.holdings, list(self.detail_map.values()))

        for group in result:
            for item in group["items"]:
                code = item["code"]
                yield_text = item.get("yield_text", "--")
                if code == "600900":
                    self.assertEqual(yield_text, "1.55%")
                elif code == "601398":
                    self.assertEqual(yield_text, "4.62%")

    def test_dividend_data_empty(self):
        """无 A 股持仓 → 不调用 get_dividend_data，yield_text = "--"。"""
        from src.python.report.html_builders import _build_category_data

        non_a_holdings = [
            Holding("证券账户", "腾讯控股", "00700", 100, 300.0),
        ]
        d = MagicMock(spec=DetailRow)
        d.market_value = 31000.0
        d.cost = 30000.0
        d.profit = 1000.0
        d.profit_rate = 0.0333
        d.today_profit = 0.0
        d.price = 310.0
        d.name = "腾讯控股"
        d.code = "00700"

        with patch("src.python.providers.akshare_extras.get_dividend_data") as mock_dd:
            result = _build_category_data(non_a_holdings, [d])
            mock_dd.assert_not_called()

        for group in result:
            for item in group["items"]:
                self.assertEqual(item.get("yield_text"), "--")


if __name__ == "__main__":
    unittest.main()

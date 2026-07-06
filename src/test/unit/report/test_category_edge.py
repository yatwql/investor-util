"""持仓分类模块边缘/异常测试 — calc_yield_text 容错。

测试目标：
  - calc_yield_text：零价格、None 对象、类型异常时的降级

运行：
  pytest src/test/unit/report/test_category_edge.py -v
"""

from __future__ import annotations

import unittest

import pytest

from src.python.report import category as cat

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


class TestYieldTextEdge(unittest.TestCase):
    """calc_yield_text 边界/异常情况。"""

    def setUp(self):
        self.d = cat.DetailRow()
        self.d.name = "长江电力"
        self.d.code = "600900"
        self.d.price = 50.0
        self.d.market_value = 5000.0
        self.d.cost = 4500.0
        self.d.profit = 500.0
        self.d.profit_rate = 0.10
        self.d.today_profit = 10.0

    def test_price_zero(self):
        """最新价为 0 → "--"。"""
        d = cat.DetailRow()
        d.price = 0.0
        result = cat.calc_yield_text("000001", d, {"000001": {"avg_dividend": 0.50}})
        self.assertEqual(result, "--")

    def test_detail_none(self):
        """detail 为 None → "--"。"""
        result = cat.calc_yield_text("600900", None, {"600900": {"avg_dividend": 0.85}})
        self.assertEqual(result, "--")

    def test_type_error_handled(self):
        """非法类型 → try/except 兜底返回 "--"。"""
        result = cat.calc_yield_text("600900", self.d, {"600900": {"avg_dividend": "invalid"}})
        self.assertEqual(result, "--")


if __name__ == "__main__":
    unittest.main()

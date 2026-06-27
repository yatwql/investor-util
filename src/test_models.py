"""DataModel Holding 单元测试。

测试目标：
  - Holding dataclass 字段正确性与默认值
  - 各种类型的参数绑定

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_models -v
"""

from __future__ import annotations

import unittest

from src.models import Holding


class TestHolding(unittest.TestCase):
    """Holding dataclass 的基础字段测试。"""

    def test_create_minimal(self):
        """最简构造，所有字段必填。"""
        h = Holding(account="证券账户", name="长江电力",
                     code="600900", shares=800, cost_price=17.65)
        self.assertEqual(h.account, "证券账户")
        self.assertEqual(h.name, "长江电力")
        self.assertEqual(h.code, "600900")
        self.assertEqual(h.shares, 800)
        self.assertEqual(h.cost_price, 17.65)

    def test_create_zero_shares(self):
        """允许 0 份额（外部校验处理）。"""
        h = Holding(account="测试", name="测试", code="000000",
                     shares=0.0, cost_price=10.0)
        self.assertEqual(h.shares, 0.0)

    def test_create_negative_cost(self):
        """允许负成本（外部校验处理）。"""
        h = Holding(account="测试", name="测试", code="000000",
                     shares=100, cost_price=-5.0)
        self.assertEqual(h.cost_price, -5.0)

    def test_create_string_shares(self):
        """字符串份额保持原始值（dataclass 不自动转换）。"""
        h = Holding(account="测试", name="测试", code="000000",
                     shares="800", cost_price=10.0)
        self.assertEqual(h.shares, "800")

    def test_repr(self):
        """repr 输出含关键字段。"""
        h = Holding(account="证券账户", name="长江电力",
                     code="600900", shares=800, cost_price=17.65)
        r = repr(h)
        self.assertIn("长江电力", r)
        self.assertIn("600900", r)

    def test_eq_different(self):
        """不同持仓对象不等。"""
        h1 = Holding(account="A", name="股票1", code="000001",
                      shares=100, cost_price=10.0)
        h2 = Holding(account="B", name="股票2", code="000002",
                      shares=200, cost_price=20.0)
        self.assertNotEqual(h1, h2)

    def test_eq_same_values(self):
        """相同字段值的对象相等（dataclass 默认行为）。"""
        h1 = Holding(account="A", name="X", code="000001",
                      shares=100, cost_price=10.0)
        h2 = Holding(account="A", name="X", code="000001",
                      shares=100, cost_price=10.0)
        self.assertEqual(h1, h2)

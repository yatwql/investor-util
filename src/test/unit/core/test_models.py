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

from src.python.models import Holding
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_core]




class TestHolding(unittest.TestCase):
    """Holding dataclass 的基础字段测试。"""

    @pytest.mark.smoke
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

    @pytest.mark.smoke
    def test_repr(self):
        """repr 输出含关键字段。"""
        h = Holding(account="证券账户", name="长江电力",
                     code="600900", shares=800, cost_price=17.65)
        r = repr(h)
        self.assertIn("长江电力", r)
        self.assertIn("600900", r)

    @pytest.mark.smoke
    def test_eq_different(self):
        """不同持仓对象不等。"""
        h1 = Holding(account="A", name="股票1", code="000001",
                      shares=100, cost_price=10.0)
        h2 = Holding(account="B", name="股票2", code="000002",
                      shares=200, cost_price=20.0)
        self.assertNotEqual(h1, h2)

    @pytest.mark.smoke
    def test_eq_same_values(self):
        """相同字段值的对象相等（dataclass 默认行为）。"""
        h1 = Holding(account="A", name="X", code="000001",
                      shares=100, cost_price=10.0)
        h2 = Holding(account="A", name="X", code="000001",
                      shares=100, cost_price=10.0)
        self.assertEqual(h1, h2)


class TestHoldingEdgeCases(unittest.TestCase):
    """Holding 边缘情况测试。"""

    def test_negative_shares(self) -> None:
        """负份额（dataclass 不校验）。"""
        h = Holding(account="证券", name="股票", code="000001",
                     shares=-100.0, cost_price=10.0)
        self.assertEqual(h.shares, -100.0)

    def test_empty_code(self) -> None:
        """代码为空字符串。"""
        h = Holding(account="证券", name="现金", code="",
                     shares=100, cost_price=1.0)
        self.assertEqual(h.code, "")

    def test_empty_account(self) -> None:
        """账户名为空字符串。"""
        h = Holding(account="", name="股票", code="000001",
                     shares=100, cost_price=10.0)
        self.assertEqual(h.account, "")

    def test_empty_name(self) -> None:
        """名称为空字符串。"""
        h = Holding(account="证券", name="", code="000001",
                     shares=100, cost_price=10.0)
        self.assertEqual(h.name, "")

    def test_code_with_special_chars(self) -> None:
        """代码含特殊字符（如港股代码）。"""
        h = Holding(account="港股", name="腾讯控股", code="00700.HK",
                     shares=1000, cost_price=300.0)
        self.assertEqual(h.code, "00700.HK")

    def test_shares_as_float(self) -> None:
        """份额为浮点数。"""
        h = Holding(account="证券", name="股票", code="000001",
                     shares=100.5, cost_price=10.0)
        self.assertIsInstance(h.shares, float)

    def test_repr_contains_all_fields(self) -> None:
        """repr 包含所有字段。"""
        h = Holding(account="证券", name="长江电力", code="600900",
                     shares=800, cost_price=17.65)
        r = repr(h)
        self.assertIn("Holding", r)
        self.assertIn("account=", r)
        self.assertIn("name=", r)
        self.assertIn("code=", r)
        self.assertIn("shares=", r)
        self.assertIn("cost_price=", r)


class TestHoldingComparison(unittest.TestCase):
    """Holding 比较行为测试。"""

    def test_eq_ignores_type_mismatch(self) -> None:
        """不同类型的对象不相等。"""
        h = Holding(account="A", name="X", code="000001",
                     shares=100, cost_price=10.0)
        self.assertNotEqual(h, "not a holding")

    def test_eq_shares_type_coercion(self) -> None:
        """100 == 100.0（Dataclass 默认行为）。"""
        h1 = Holding(account="A", name="X", code="000001",
                      shares=100, cost_price=10.0)
        h2 = Holding(account="A", name="X", code="000001",
                      shares=100.0, cost_price=10.0)
        self.assertEqual(h1, h2)

    def test_hash_raises_type_error(self) -> None:
        """非 frozen dataclass 不可 hash。"""
        h = Holding(account="A", name="X", code="000001",
                     shares=100, cost_price=10.0)
        with self.assertRaises(TypeError):
            hash(h)


class TestHoldingLargeDataset(unittest.TestCase):
    """大量 Holding 对象构造测试。"""

    def test_create_many_holdings(self) -> None:
        """快速构造 10000 个 Holding 不报错。"""
        holdings = [
            Holding(account=f"账户{i%5}", name=f"股票{i}", code=f"{i:06d}",
                    shares=float(i), cost_price=float(i % 100))
            for i in range(10000)
        ]
        self.assertEqual(len(holdings), 10000)
        self.assertEqual(holdings[0].account, "账户0")
        self.assertEqual(holdings[-1].code, "009999")

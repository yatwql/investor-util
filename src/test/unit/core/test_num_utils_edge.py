"""数值归一原语边缘用例（core/num_utils.py）。

极端值、特殊浮点、外来数值标量。
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from src.python.core.num_utils import finite_or, is_finite_number, safe_num, strict_num


@pytest.mark.unit
@pytest.mark.unit_core
@pytest.mark.edge
class TestExtremeValues:
    """极端数值。"""

    def test_negative_zero_is_finite(self):
        result = safe_num(-0.0)
        assert result == 0.0
        assert math.copysign(1.0, result) == -1.0

    def test_max_float_is_finite(self):
        assert safe_num(1.7976931348623157e308) == 1.7976931348623157e308

    def test_overflow_string_becomes_inf_and_is_rejected(self):
        """``float("1e999")`` 溢出为 inf —— 必须在转换后拦下。"""
        assert safe_num("1e999") is None

    def test_huge_decimal_would_overflow_to_inf_but_is_gated_by_type(self):
        """超大 Decimal 转 float 得 inf（不抛异常）——类型门在转换前已拦下。"""
        assert math.isinf(float(Decimal("1e9999")))
        assert safe_num(Decimal("1e9999")) is None

    def test_infinity_keyword_variants(self):
        assert safe_num("Infinity") is None
        assert safe_num("INF") is None


@pytest.mark.unit
@pytest.mark.unit_core
@pytest.mark.edge
class TestForeignScalars:
    """非内置数值标量。"""

    def test_decimal_is_rejected(self):
        """Decimal 不是 int/float —— 严格口径拒绝；宽容口径也拒绝（避免隐式精度损失）。"""
        assert strict_num(Decimal("1.5")) is None
        assert safe_num(Decimal("1.5")) is None

    def test_numeric_string_with_whitespace_and_signs(self):
        assert safe_num("  +2.5  ") == 2.5
        assert safe_num("+0") == 0.0

    def test_comma_separated_string_rejected(self):
        """千分位串不是合法 float —— 返回 default 而非静默截断。"""
        assert safe_num("1,234", default=0.0) == 0.0

    def test_bytes_rejected(self):
        assert safe_num(b"1.5") is None


@pytest.mark.unit
@pytest.mark.unit_core
@pytest.mark.edge
class TestFiniteOrExtremes:
    """``finite_or`` 极端输入。"""

    def test_nan_chain_never_returns_nan(self):
        """连续归一仍不产 NaN —— 全链路不变量的最小断言。"""
        value = float("nan")
        for _ in range(5):
            value = finite_or(value)
        assert value == 0.0

    def test_zero_fallback_preserves_negative_values(self):
        """负值是真数值，不应被 ``> 0`` 式写法误杀。"""
        assert finite_or(-5.0) == -5.0

    def test_predicate_on_boundary(self):
        assert is_finite_number(5e-324) is True  # 最小正次正规数
        assert is_finite_number(float("nan")) is False

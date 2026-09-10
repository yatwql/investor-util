"""数值归一原语测试（core/num_utils.py）。

覆盖重点：
- ``safe_num`` 全脏值矩阵
- ``finite_or`` 相对裸 ``or 0.0`` 的正确性（缺陷回归核心）
- ``strict_num`` 与 ``signal_ledger._safe_number`` 的口径一致性
"""

from __future__ import annotations

import math

import pytest

from src.python.core.num_utils import (
    finite_or,
    is_finite_number,
    safe_num,
    strict_num,
)


@pytest.mark.unit
@pytest.mark.unit_core
class TestSafeNum:
    """宽容归一：数值字符串解析 + 有限性检查。"""

    def test_keeps_finite_numbers(self):
        assert safe_num(3) == 3
        assert safe_num(3.5) == 3.5
        assert safe_num(0) == 0
        assert safe_num(-12.25) == -12.25

    def test_int_stays_int(self):
        """整数不转 float —— 份额/ID 不应被改写类型。"""
        assert isinstance(safe_num(7), int)

    def test_parses_numeric_strings(self):
        assert safe_num("12.5") == 12.5
        assert safe_num(" 8 ") == 8
        assert safe_num("-1.5") == -1.5

    def test_returns_default_for_placeholders(self):
        assert safe_num("--", default=0.0) == 0.0
        assert safe_num("", default=0.0) == 0.0
        assert safe_num("N/A") is None
        assert safe_num("abc", default=-1.0) == -1.0

    def test_returns_default_for_none(self):
        assert safe_num(None) is None
        assert safe_num(None, default=0.0) == 0.0

    def test_rejects_nan_and_inf(self):
        assert safe_num(float("nan")) is None
        assert safe_num(float("inf")) is None
        assert safe_num(float("-inf")) is None
        assert safe_num(float("nan"), default=0.0) == 0.0

    def test_rejects_infinite_strings(self):
        """``float("inf")`` 与 ``float("nan")`` 都是合法转换，必须在转换后拦下。"""
        assert safe_num("inf") is None
        assert safe_num("nan") is None
        assert safe_num("-infinity") is None

    def test_rejects_bool(self):
        """bool 是 int 子类，必须显式排除，否则 True 静默变 1。"""
        assert safe_num(True) is None
        assert safe_num(False) is None
        assert safe_num(True, default=0.0) == 0.0

    def test_rejects_non_numeric_types(self):
        assert safe_num([1]) is None
        assert safe_num({"a": 1}) is None
        assert safe_num(object()) is None


@pytest.mark.unit
@pytest.mark.unit_core
class TestStrictNum:
    """严格归一：不接受字符串。"""

    def test_keeps_finite_numbers(self):
        assert strict_num(3) == 3
        assert strict_num(3.5) == 3.5

    def test_rejects_numeric_strings(self):
        """与 ``safe_num`` 的关键差异：字符串一律非数值。"""
        assert strict_num("12.5") is None
        assert strict_num("12.5", default=0.0) == 0.0

    def test_rejects_bool_nan_inf(self):
        assert strict_num(True) is None
        assert strict_num(float("nan")) is None
        assert strict_num(float("inf")) is None


@pytest.mark.unit
@pytest.mark.unit_core
class TestFiniteOr:
    """``finite_or`` 是 ``or 0.0`` 惯用法的缺陷修复点。"""

    def test_nan_falls_back(self):
        """核心缺陷回归：``float('nan') or 0.0`` 返回 NaN，``finite_or`` 返回 0.0。"""
        assert math.isnan(float("nan") or 0.0)  # 裸 ``or`` 拦不住
        assert finite_or(float("nan")) == 0.0

    def test_inf_falls_back(self):
        assert finite_or(float("inf")) == 0.0
        assert finite_or(float("-inf")) == 0.0

    def test_keeps_finite_values(self):
        assert finite_or(2.5) == 2.5
        assert finite_or(0) == 0.0
        assert finite_or("3.5") == 3.5

    def test_always_returns_float(self):
        assert isinstance(finite_or(3), float)

    def test_custom_fallback(self):
        assert finite_or(None, fallback=-1.0) == -1.0
        assert finite_or(float("nan"), fallback=99.0) == 99.0


@pytest.mark.unit
@pytest.mark.unit_core
class TestIsFiniteNumber:
    """谓词：真数值且有限。"""

    def test_accepts_finite_numbers(self):
        assert is_finite_number(0)
        assert is_finite_number(-1.5)
        assert is_finite_number(1e308)

    def test_rejects_dirty_values(self):
        assert not is_finite_number(None)
        assert not is_finite_number(True)
        assert not is_finite_number("1")
        assert not is_finite_number(float("nan"))
        assert not is_finite_number(float("inf"))

    def test_zero_is_finite(self):
        """避免调用方误写 ``if value``（0 是合法数值却为假）。"""
        assert is_finite_number(0) is True


"""数值归一回归测试 —— provider 解析器不得泄漏 NaN/±inf。

缺陷背景：``float("nan")`` / ``float("inf")`` 不抛异常，原先各 provider 的
``try: float(x) except`` 兜底对它们完全无效，脏值会一路穿透到市值、收益序列
与绘图数据。本文件锁定「provider 解析器的输出一定是有限值」这一不变量。
"""

from __future__ import annotations

import math

import pytest

from src.python.providers import _utils, akshare_extras, eastmoney_industry, sina_kline, tencent

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


@pytest.mark.unit
@pytest.mark.unit_providers
class TestSharedSafeFloat:
    """providers/_utils.safe_float —— 命中面最广的一个（基金净值/排名链路）。"""

    def test_nan_becomes_zero(self):
        """核心缺陷：NaN 净值曾原样流向 fetcher/price.py → market_value。"""
        result = _utils.safe_float(float("nan"))
        assert result == 0.0
        assert math.isfinite(result)

    def test_inf_becomes_zero(self):
        assert _utils.safe_float(float("inf")) == 0.0
        assert _utils.safe_float(float("-inf")) == 0.0

    def test_nan_string_becomes_zero(self):
        assert _utils.safe_float("nan") == 0.0

    def test_legitimate_values_unchanged(self):
        """合法输入行为逐字不变（不变量）。"""
        assert _utils.safe_float(3) == 3.0
        assert _utils.safe_float("12.5") == 12.5
        assert _utils.safe_float(-1.5) == -1.5
        assert _utils.safe_float(None) == 0.0
        assert _utils.safe_float("abc") == 0.0

    def test_always_returns_float(self):
        assert isinstance(_utils.safe_float(3), float)


@pytest.mark.unit
@pytest.mark.unit_providers
class TestTencentParsers:
    """腾讯行情解析器。"""

    def test_parse_float_positive_inf_no_longer_leaks(self):
        """``inf > 0`` 为真，仅凭正负号判断会让 +inf 直入 price 字段。"""
        assert tencent._parse_float(float("inf")) == 0.0
        assert tencent._parse_float("inf") == 0.0

    def test_parse_float_keeps_positive_values(self):
        assert tencent._parse_float("12.5") == 12.5

    def test_parse_float_clamps_negative(self):
        """负数钳制为 0.0 属既有口径，保持不变。"""
        assert tencent._parse_float(-3.0) == 0.0

    def test_parse_float_field_rejects_non_finite(self):
        assert tencent._parse_float_field(float("nan")) == 0.0
        assert tencent._parse_float_field(float("-inf")) == 0.0

    def test_parse_float_field_keeps_legitimate(self):
        assert tencent._parse_float_field("7.25") == 7.25
        assert tencent._parse_float_field("") == 0.0


@pytest.mark.unit
@pytest.mark.unit_providers
class TestSinaKlineParser:
    """新浪 K 线解析器 —— 脏值会进入 analysis/ 全部收益序列指标。"""

    def test_non_finite_rejected(self):
        assert sina_kline._parse_sina_kline_float(float("nan")) == 0.0
        assert sina_kline._parse_sina_kline_float(float("inf")) == 0.0
        assert sina_kline._parse_sina_kline_float(float("-inf")) == 0.0

    def test_legitimate_values_unchanged(self):
        assert sina_kline._parse_sina_kline_float("10.5") == 10.5
        assert sina_kline._parse_sina_kline_float(None) == 0.0
        assert sina_kline._parse_sina_kline_float("bad") == 0.0

    def test_nan_string_rejected(self):
        assert sina_kline._parse_sina_kline_float("nan") == 0.0


@pytest.mark.unit
@pytest.mark.unit_providers
class TestEastmoneyIndustryParser:
    """东方财富行业扩展估值字段。"""

    def test_non_finite_rejected(self):
        assert eastmoney_industry._extract_number({"f9": float("nan")}, "f9") is None
        assert eastmoney_industry._extract_number({"f9": float("inf")}, "f9") is None

    def test_legitimate_values_unchanged(self):
        assert eastmoney_industry._extract_number({"f9": 12.5}, "f9") == 12.5
        assert eastmoney_industry._extract_number({"f9": "12.5"}, "f9") == 12.5
        assert eastmoney_industry._extract_number({"f9": "-"}, "f9") is None
        assert eastmoney_industry._extract_number({}, "f9") is None

    def test_bool_rejected(self):
        """bool 是 int 子类，接口字段出现布尔值属脏数据，须拒绝。"""
        assert eastmoney_industry._extract_number({"f9": True}, "f9") is None


@pytest.mark.unit
@pytest.mark.unit_providers
class TestAkshareExtrasParser:
    """akshare 扩展数据解析器。"""

    def test_inf_rejected(self):
        """归一须同时拦下 NaN 与 ±inf，只拦 NaN 会让无穷值漏出。"""
        assert akshare_extras._safe_float(float("inf")) is None
        assert akshare_extras._safe_float(float("-inf")) is None
        assert akshare_extras._safe_float(float("nan")) is None

    def test_legitimate_values_unchanged(self):
        assert akshare_extras._safe_float("1.5") == 1.5
        assert akshare_extras._safe_float(None) is None
        assert akshare_extras._safe_float("abc") is None

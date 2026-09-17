"""数据源适配契约边界测试（@edge）。

覆盖正常路径之外的输入形态：非映射原始响应、空响应、全 None 字段、
上游多出未知键、别名冲突、非字符串名称等——归一后必须仍是标准字段集
且不抛异常（脏响应不得炸链路）。

按仓库纪律：edge 场景必须置于 ``*_edge.py`` 文件。
"""

from __future__ import annotations

import unittest
from typing import Any, ClassVar

import pytest

from src.python.fetcher import source_adapter as sa
from src.python.schemas.datasource_fields import DOMAIN_QUOTE, QuoteFields

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher, pytest.mark.edge]

_STANDARD = set(QuoteFields.__dataclass_fields__)


def _quote_adapter(source_id: str) -> sa.SourceAdapter:
    return sa.get_adapters(DOMAIN_QUOTE)[source_id]


class TestRawShapeEdge(unittest.TestCase):
    """原始响应形态异常。"""

    def test_non_mapping_raw_returns_none(self):
        """上游返回非映射（列表/字符串/数字/None）→ 判为无数据，不抛异常。"""
        adapter = _quote_adapter("tencent")
        for raw in ([], "异常响应", 42, None, object()):
            self.assertIsNone(adapter.transform_record(raw, "腾讯财经"))

    def test_empty_mapping_yields_standard_shape(self):
        """空响应 → 仍输出完整标准字段（缺省值），下游无需判 KeyError。"""
        out = _quote_adapter("tencent").transform_record({}, "腾讯财经")
        self.assertEqual(set(out), _STANDARD)
        self.assertEqual(out["name"], "")
        self.assertEqual(out["price"], 0.0)
        self.assertEqual(out["market_cap"], 0.0)  # 腾讯源缺市值时按 0.0 处理

    def test_all_none_fields_do_not_raise(self):
        """全部字段为 None → 归一为类型缺省值。"""
        raw = dict.fromkeys(_STANDARD, None)
        out = _quote_adapter("tencent").transform_record(raw, "腾讯财经")
        self.assertEqual(set(out), _STANDARD)
        self.assertEqual(out["name"], "")
        self.assertEqual(out["price"], 0.0)

    def test_unknown_upstream_keys_are_dropped(self):
        """上游多出未知键 → 不进标准记录（防上游字段泄入下游契约）。"""
        raw = {"name": "x", "code": "600519", "price": 1.0, "上游新增字段": "值", "另一个": 2}
        out = _quote_adapter("tencent").transform_record(raw, "腾讯财经")
        self.assertEqual(set(out), _STANDARD)


class TestValueEdge(unittest.TestCase):
    """字段取值异常。"""

    def test_non_finite_numeric_values_fall_back(self):
        """NaN / ±inf 数值 → 归一到该源声明的缺省值，不污染下游。

        「不可用」与「未提供」同待遇：都回落 ``defaults``，未声明则该源按字段
        类型注解取缺省。腾讯声明的市值缺省为 0.0（源不提供时按 0 处理），
        故不可用值同样得 0.0；而必填的 price 未声明缺省，按类型取 0.0。
        """
        adapter = _quote_adapter("tencent")
        for value in (float("nan"), float("inf"), float("-inf")):
            out = adapter.transform_record({"price": value, "market_cap": value}, "腾讯财经")
            self.assertEqual(out["price"], 0.0)
            self.assertEqual(out["market_cap"], 0.0)

    def test_unusable_value_uses_source_declared_default(self):
        """同一不可用取值，不同源的声明缺省不同 → 结果各自服从本源语义。

        新浪源声明「不提供市值」→ 缺省 None；腾讯源声明「不提供按 0 计」→ 0.0。
        """
        for value in (float("nan"), "不可解析"):
            sina = _quote_adapter("sina").transform_record({"market_cap": value}, "新浪财经")
            tencent = _quote_adapter("tencent").transform_record({"market_cap": value}, "腾讯财经")
            self.assertIsNone(sina["market_cap"])
            self.assertEqual(tencent["market_cap"], 0.0)

    def test_legitimate_zero_is_not_overridden_by_default(self):
        """合法的 0.0 不被声明的缺省值覆盖（只有不可用值才回落）。"""
        out = _quote_adapter("tencent").transform_record({"market_cap": 0.0, "price": 0.0}, "腾讯财经")
        self.assertEqual(out["market_cap"], 0.0)
        self.assertEqual(out["price"], 0.0)

    def test_numeric_strings_and_whitespace(self):
        """数值字符串按数值归一；空白串归缺省值。"""
        adapter = _quote_adapter("tencent")
        out = adapter.transform_record({"price": "1700.5", "yesterday_close": "  "}, "腾讯财经")
        self.assertEqual(out["price"], 1700.5)
        self.assertEqual(out["yesterday_close"], 0.0)

    def test_str_field_accepts_non_str_by_stringification(self):
        """文本字段收到数字 → 字符串化，保证类型契约不破。"""
        out = _quote_adapter("tencent").transform_record({"name": 600519, "code": 519}, "腾讯财经")
        self.assertEqual(out["name"], "600519")
        self.assertEqual(out["code"], "519")

    def test_identity_fields_always_from_adapter(self):
        """源身份字段不因上游缺失而变空。"""
        out = _quote_adapter("sina").transform_record({}, "新浪财经")
        self.assertEqual(out["source"], "新浪财经")
        self.assertEqual(out["source_api"], "sina")


class TestAliasConflictEdge(unittest.TestCase):
    """别名声明异常。"""

    def test_multiple_aliases_to_same_field_first_wins(self):
        """同一标准字段有多个上游别名 → 取先声明者（确定性，不受 dict 顺序漂移影响）。"""

        class _Adapter(sa.SourceAdapter):
            domain: ClassVar[str] = DOMAIN_QUOTE
            source_id: ClassVar[str] = "alias_conflict"
            display_name: ClassVar[str] = "别名冲突源"
            aliases: ClassVar[dict[str, str]] = {"nav": "price", "净值": "price"}

            def extract_data(self, query: dict[str, Any]) -> Any:
                return None

        out = _Adapter().transform_record({"nav": 1.0, "净值": 99.0}, "别名冲突源")
        self.assertEqual(out["price"], 1.0)

    def test_alias_of_standard_named_upstream_key(self):
        """上游键名恰好等于另一个标准字段名 → 按 alias 声明的目标字段落位。"""

        class _Adapter(sa.SourceAdapter):
            domain: ClassVar[str] = DOMAIN_QUOTE
            source_id: ClassVar[str] = "collide"
            display_name: ClassVar[str] = "键名撞车源"
            aliases: ClassVar[dict[str, str]] = {"name": "code"}

            def extract_data(self, query: dict[str, Any]) -> Any:
                return None

        out = _Adapter().transform_record({"name": "上游把代码放在 name 里"}, "键名撞车源")
        self.assertEqual(out["code"], "上游把代码放在 name 里")
        self.assertEqual(set(out), _STANDARD)

    def test_defaults_key_not_in_standard_fields_is_reported(self):
        """defaults 声明了非标准字段 → 自检报告。"""

        class _Adapter(sa.SourceAdapter):
            domain: ClassVar[str] = DOMAIN_QUOTE
            source_id: ClassVar[str] = "bad_default"
            display_name: ClassVar[str] = "错默认值源"
            defaults: ClassVar[dict[str, Any]] = {"不存在的字段": 1}

            def extract_data(self, query: dict[str, Any]) -> Any:
                return None

        problems = _Adapter().self_test()
        self.assertTrue(any("defaults" in p for p in problems), problems)

    def test_missing_identity_declarations_reported(self):
        """缺 source_id/display_name/domain 声明 → 自检逐项报告且不抛异常。"""

        class _Bare(sa.SourceAdapter):
            def extract_data(self, query: dict[str, Any]) -> Any:
                return None

        problems = _Bare().self_test()
        self.assertTrue(any("source_id" in p for p in problems), problems)
        self.assertTrue(any("display_name" in p for p in problems), problems)
        self.assertTrue(any("domain" in p for p in problems), problems)

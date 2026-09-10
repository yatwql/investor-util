"""数据源适配契约单元测试。

测试目标：
  - 注册表：域登记、未知域空映射、自检报告
  - 三段式：参数转译 / 抓取 / 映射到标准字段的串接
  - 声明式归一：alias 改名、源身份字段强制覆盖、类型驱动的缺省取值
  - 自检：坏 alias、未登记域、transform_data 抛异常均被检出且不中断调用方

不发起任何网络请求（抓取一律用桩）。
"""

from __future__ import annotations

import unittest
from typing import Any, ClassVar

import pytest

from src.python.fetcher import source_adapter as sa
from src.python.schemas.datasource_fields import DOMAIN_QUOTE, QuoteFields

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]


class _StubAdapter(sa.SourceAdapter):
    """最小可用适配器：抓取返回构造好的原始响应（不碰网络）。"""

    domain: ClassVar[str] = DOMAIN_QUOTE
    source_id: ClassVar[str] = "stub"
    display_name: ClassVar[str] = "桩数据源"

    def __init__(self, payload: Any = None) -> None:
        self.payload = payload
        self.queries: list[dict[str, Any]] = []

    def extract_data(self, query: dict[str, Any]) -> Any:
        self.queries.append(query)
        return self.payload


class TestAdapterRegistry(unittest.TestCase):
    """注册表与自检报告。"""

    def test_quote_domain_adapters_registered(self):
        """行情域已登记腾讯/新浪/东方财富三个适配器。"""
        adapters = sa.get_adapters(DOMAIN_QUOTE)
        self.assertEqual(sorted(adapters), ["eastmoney", "sina", "tencent"])
        self.assertEqual(adapters["tencent"].display_name, "腾讯财经")

    def test_unknown_domain_returns_empty(self):
        """未知数据域返回空映射而非抛异常。"""
        self.assertEqual(sa.get_adapters("不存在的域"), {})
        provider_map, transform_map = sa.adapter_chain_slots("不存在的域")
        self.assertEqual((provider_map, transform_map), ({}, {}))

    def test_chain_slots_shape(self):
        """链路两槽结构与 fetch_with_fallback 的两入参一致。"""
        provider_map, transform_map = sa.adapter_chain_slots(DOMAIN_QUOTE)
        label, fetch_fn = provider_map["eastmoney"]
        self.assertEqual(label, "东方财富")
        self.assertTrue(callable(fetch_fn))
        self.assertTrue(callable(transform_map["eastmoney"]))

    def test_survey_reports_all_passed(self):
        """已登记适配器全部通过契约自检。"""
        reports = sa.survey_adapters()
        self.assertEqual(len(reports), 3)
        self.assertTrue(all(r["ok"] for r in reports), [r for r in reports if not r["ok"]])
        self.assertEqual({r["domain"] for r in reports}, {DOMAIN_QUOTE})

    def test_survey_detects_alias_to_unknown_field(self):
        """alias 指向非标准字段 → 自检检出（防改名写错后静默丢字段）。"""

        class _BadAliasAdapter(_StubAdapter):
            aliases: ClassVar[dict[str, str]] = {"nav": "净值"}

        sa.register_adapter(_BadAliasAdapter({"nav": 1.0}))
        reports = {r["source_id"]: r for r in sa.survey_adapters()}
        self.assertFalse(reports["stub"]["ok"])
        self.assertIn("不是标准字段", reports["stub"]["message"])

    def test_survey_detects_missing_standard_field(self):
        """transform_data 输出缺标准字段 → 自检检出。"""

        class _LossyAdapter(_StubAdapter):
            def transform_data(self, raw: Any, source: str = "") -> dict[str, Any] | None:
                return {"name": "只有名称"}

        sa.register_adapter(_LossyAdapter())
        reports = {r["source_id"]: r for r in sa.survey_adapters()}
        self.assertFalse(reports["stub"]["ok"])
        self.assertIn("缺标准字段", reports["stub"]["message"])

    def test_survey_detects_unregistered_domain(self):
        """域未登记 → 自检检出而非抛 KeyError。"""

        class _UnknownDomainAdapter(_StubAdapter):
            domain: ClassVar[str] = "尚未登记的域"

        sa.register_adapter(_UnknownDomainAdapter())
        reports = {r["source_id"]: r for r in sa.survey_adapters()}
        self.assertFalse(reports["stub"]["ok"])
        self.assertIn("未在 DOMAIN_RECORDS 登记", reports["stub"]["message"])

    def test_survey_survives_raising_adapter(self):
        """适配器 transform_data 抛异常 → 转为失败报告，不向上抛。"""

        class _RaisingAdapter(_StubAdapter):
            def transform_data(self, raw: Any, source: str = "") -> dict[str, Any] | None:
                raise RuntimeError("自检必须吞掉此异常")

        sa.register_adapter(_RaisingAdapter())
        reports = {r["source_id"]: r for r in sa.survey_adapters()}
        self.assertFalse(reports["stub"]["ok"])
        self.assertIn("RuntimeError", reports["stub"]["message"])

    def test_register_ignores_adapter_without_identity(self):
        """缺 domain/source_id 的适配器不进入注册表。"""

        class _NoIdentityAdapter(_StubAdapter):
            source_id: ClassVar[str] = ""

        sa.register_adapter(_NoIdentityAdapter())
        self.assertNotIn("", sa.get_adapters(DOMAIN_QUOTE))


class TestThreePhaseContract(unittest.TestCase):
    """三段式契约行为。"""

    def test_transform_query_default_is_identity(self):
        """默认参数转译不改写入参（返回新 dict）。"""
        adapter = _StubAdapter()
        params = {"code": "600519"}
        query = adapter.transform_query(params)
        self.assertEqual(query, params)
        self.assertIsNot(query, params)

    def test_fetch_raw_passes_translated_query(self):
        """抓取槽 = 参数转译 → 抓取，抓取函数收到转译后的 query。"""

        class _QueryAdapter(_StubAdapter):
            def transform_query(self, params):
                return {**params, "extra": "注入"}

        adapter = _QueryAdapter({"name": "x"})
        adapter.fetch_raw(code="600519")
        self.assertEqual(adapter.queries, [{"code": "600519", "extra": "注入"}])

    def test_transform_record_returns_exact_standard_field_set(self):
        """映射输出恰好是标准字段集（不多不少）。"""
        adapter = _StubAdapter()
        out = adapter.transform_record({"name": "贵州茅台", "未知字段": 1}, "桩数据源")
        self.assertEqual(set(out), set(QuoteFields.__dataclass_fields__))
        self.assertNotIn("未知字段", out)


class TestDeclarativeNormalization(unittest.TestCase):
    """声明式 alias 归一与类型驱动的缺省取值。"""

    def setUp(self):
        self.adapter = sa.get_adapters(DOMAIN_QUOTE)["eastmoney"]

    def test_alias_renames_upstream_fields(self):
        """净值源的 nav/yesterday_nav/nav_date 归一到 price/yesterday_close/price_date。"""
        raw = {
            "name": "易方达消费行业",
            "code": "110022",
            "nav": 3.4567,
            "yesterday_nav": 3.4100,
            "nav_date": "2026-09-09",
            "source": "天天基金",
        }
        out = self.adapter.transform_record(raw, "东方财富")
        self.assertEqual(out["price"], 3.4567)
        self.assertEqual(out["yesterday_close"], 3.41)
        self.assertEqual(out["price_date"], "2026-09-09")

    def test_identity_fields_ignore_upstream_self_report(self):
        """源身份字段由适配器强制提供——上游自报的来源不覆盖链路标签。

        东方财富回落到天天基金时原始响应自报 source="天天基金"，若直接透传会让
        报告显示「来源：天天基金」而实际生效链路是东方财富。
        """
        raw = {"name": "x", "code": "110022", "nav": 1.0, "source": "天天基金"}
        out = self.adapter.transform_record(raw, "东方财富")
        self.assertEqual(out["source"], "东方财富")
        self.assertEqual(out["source_api"], "eastmoney")

    def test_invalid_nav_yields_no_data(self):
        """净值缺失或 <= 0 视为无数据，交由链路尝试下一个源。"""
        self.assertIsNone(self.adapter.transform_record({"nav": 0.0}, "东方财富"))
        self.assertIsNone(self.adapter.transform_record({"name": "x"}, "东方财富"))
        self.assertIsNone(self.adapter.transform_record(None, "东方财富"))

    def test_numeric_coercion_rejects_non_finite(self):
        """NaN / ±inf / 脏字符串经数值归一转缺省值，不进下游。"""
        raw = {"name": "x", "code": "600519", "price": float("nan"), "yesterday_close": "abc"}
        out = sa.get_adapters(DOMAIN_QUOTE)["tencent"].transform_record(raw, "腾讯财经")
        self.assertEqual(out["price"], 0.0)
        self.assertEqual(out["yesterday_close"], 0.0)

    def test_none_valued_optional_fields_stay_none(self):
        """新浪源不提供市值/市盈率，归一为 None（下游使用前需判 None）。"""
        raw = {"name": "x", "code": "600519", "price": 1.0}
        out = sa.get_adapters(DOMAIN_QUOTE)["sina"].transform_record(raw, "新浪财经")
        self.assertIsNone(out["market_cap"])
        self.assertIsNone(out["pe"])

    def test_numeric_optional_field_keeps_upstream_value(self):
        """源提供了可选数值字段时按上游值归一。"""
        raw = {"name": "x", "code": "600519", "price": 1.0, "market_cap": 12345.6, "pe": "9.8"}
        out = sa.get_adapters(DOMAIN_QUOTE)["tencent"].transform_record(raw, "腾讯财经")
        self.assertEqual(out["market_cap"], 12345.6)
        self.assertEqual(out["pe"], 9.8)

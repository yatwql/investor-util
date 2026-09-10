"""行情域适配契约等价性回归测试 —— 试点验收标准。

适配器路径必须与既有手写转换函数**等价**，否则实验开关一开就会静默改变
报告数值。逐源锁定的等价性：

- 腾讯/新浪：与既有转换函数输出**逐键逐值相等**；
- 东方财富：既有转换函数不含 ``market_cap``/``pe`` 两个键，适配器统一补
  ``None``（标准字段集恒为全字段）。这是本试点**唯一**的有意差异，下游消费方
  一律用 ``.get()`` 读取，取值语义不变——由 ``test_eastmoney_...`` 显式断言，
  防止差异扩大成「悄悄多跑一个源出来」。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.config.features import set_feature_enabled
from src.python.fetcher import price as price_module
from src.python.fetcher.quote_adapters import (
    EastMoneyQuoteAdapter,
    SinaQuoteAdapter,
    TencentQuoteAdapter,
)
from src.python.providers import eastmoney, tencent

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

# 真实响应形状的行情原始数据（腾讯含市值/市盈率与量价扩展字段，新浪不含市值）
_TENCENT_RAW = {
    "name": "贵州茅台",
    "code": "600519",
    "price": 1700.5,
    "yesterday_close": 1690.0,
    "price_date": "2026-09-10",
    "open": 1695.0,
    "high": 1712.0,
    "low": 1688.0,
    "volume": 32100.0,
    "turnover": 5.46e9,
    "market_cap": 21360.0,
    "pe": 31.2,
    "source": "腾讯财经",
}

_SINA_RAW = {
    "name": "贵州茅台",
    "code": "600519",
    "price": 1701.0,
    "yesterday_close": 1690.0,
    "price_date": "2026-09-10",
    "open": 1695.0,
    "high": 1712.0,
    "low": 1688.0,
    "volume": 32100.0,
    "turnover": 5.46e9,
    "source": "新浪财经",
}

_EASTMONEY_RAW = {
    "name": "易方达消费行业",
    "code": "110022",
    "nav": 3.4567,
    "acc_nav": 5.0123,
    "nav_date": "2026-09-09",
    "yesterday_nav": 3.41,
    "source": "东方财富",
}


class TestTransformParity(unittest.TestCase):
    """转换槽与既有手写转换函数逐源等价。"""

    def test_tencent_parity(self):
        self.assertEqual(
            TencentQuoteAdapter().transform_record(_TENCENT_RAW, "腾讯财经"),
            price_module._price_transform_tencent(_TENCENT_RAW, "腾讯财经"),
        )

    def test_sina_parity(self):
        self.assertEqual(
            SinaQuoteAdapter().transform_record(_SINA_RAW, "新浪财经"),
            price_module._price_transform_sina(_SINA_RAW, "新浪财经"),
        )

    def test_eastmoney_parity_except_uniform_optional_fields(self):
        """东财源差异仅限 market_cap/pe 两个 None 键（标准字段集恒为全字段）。"""
        out = EastMoneyQuoteAdapter().transform_record(_EASTMONEY_RAW, "东方财富")
        legacy = price_module._price_transform_eastmoney(_EASTMONEY_RAW, "东方财富")
        self.assertEqual(
            {k: v for k, v in out.items() if k not in ("market_cap", "pe")},
            legacy,
        )
        self.assertEqual(out["market_cap"], None)
        self.assertEqual(out["pe"], None)
        self.assertEqual(set(out) - set(legacy), {"market_cap", "pe"})

    def test_eastmoney_invalid_nav_parity(self):
        """净值无效时两者同样判为无数据。"""
        for raw in ({"nav": 0.0, "code": "110022"}, {"name": "空净值", "code": "110022"}):
            self.assertIsNone(EastMoneyQuoteAdapter().transform_record(raw, "东方财富"))
            self.assertIsNone(price_module._price_transform_eastmoney(raw, "东方财富"))


class TestChainSlotSelection(unittest.TestCase):
    """开关决定链路取哪套映射（结构断言，不依赖数值）。"""

    def test_flag_off_uses_legacy_mappings_verbatim(self):
        """开关关闭时返回既有映射对象本身（行为逐字节不变的结构保证）。"""
        set_feature_enabled("datasource_adapter", False)
        providers, transforms = price_module._price_chain_slots()
        self.assertIs(providers, price_module._PRICE_PROVIDERS)
        self.assertIs(transforms, price_module._PRICE_TRANSFORMS)

    def test_flag_on_uses_adapters(self):
        """开关开启时改用适配器映射（源集合不变）。"""
        set_feature_enabled("datasource_adapter", True)
        providers, transforms = price_module._price_chain_slots()
        self.assertEqual(set(providers), {"tencent", "sina", "eastmoney"})
        self.assertEqual(set(transforms), {"tencent", "sina", "eastmoney"})
        self.assertEqual(providers["tencent"][0], "腾讯财经")


class TestEndToEndParity(unittest.TestCase):
    """端到端：开关开/关下 fetch 结果一致（走完整链路 + 缓存 + 校验）。"""

    def _run(self, code: str, data_type: str, cache_key: str) -> dict:
        from src.python.cache import clear as cache_clear

        cache_clear(cache_key)
        return price_module._fetch_price_with_cache_refresh(data_type, code, cache_key, "")

    def test_tencent_path_identical(self):
        """腾讯链路：开关开/关结果完全相等。"""

        def _fake_fetch(code: str) -> dict:
            return dict(_TENCENT_RAW)

        with (
            patch.dict(price_module._PRICE_PROVIDERS, {"tencent": ("腾讯财经", _fake_fetch)}, clear=True),
            patch.object(tencent, "fetch_price", _fake_fetch),
        ):
            set_feature_enabled("datasource_adapter", False)
            legacy = self._run("600519", "price", "price_600519")
            set_feature_enabled("datasource_adapter", True)
            adapted = self._run("600519", "price", "price_600519")

        self.assertEqual(legacy, adapted)
        self.assertEqual(legacy["price"], 1700.5)
        self.assertEqual(legacy["source_api"], "tencent")

    def test_eastmoney_path_differs_only_by_optional_fields(self):
        """东方财富链路：差异恰好是 market_cap/pe 两个 None 键。"""

        def _fake_nav(code: str) -> dict:
            return dict(_EASTMONEY_RAW)

        with (
            patch.dict(price_module._PRICE_PROVIDERS, {"eastmoney": ("东方财富", _fake_nav)}, clear=True),
            patch.object(eastmoney, "fetch_nav", _fake_nav),
        ):
            set_feature_enabled("datasource_adapter", False)
            legacy = self._run("110022", "price", "price_110022")
            set_feature_enabled("datasource_adapter", True)
            adapted = self._run("110022", "price", "price_110022")

        self.assertEqual(
            {k: v for k, v in adapted.items() if k not in ("market_cap", "pe")},
            legacy,
        )
        self.assertEqual(set(adapted) - set(legacy), {"market_cap", "pe"})
        self.assertEqual(adapted["price"], 3.4567)

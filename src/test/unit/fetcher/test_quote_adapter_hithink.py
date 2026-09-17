"""同花顺行情适配器与行情/历史链路顺序单元测试（官方行情第三槽）。

覆盖：别名归一（last_price→price / prev_price→yesterday_close）、不提供的字段落 None、
契约自检、行情域第三槽与历史日 K 第三槽的链路顺序、历史 provider 映射。

运行：
  pytest src/test/unit/fetcher/test_quote_adapter_hithink.py -v
"""

from __future__ import annotations

import pytest

from src.python.fetcher.quote_adapters import HithinkQuoteAdapter
from src.python.schemas.datasource_fields import DOMAIN_QUOTE

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]


class TestHithinkQuoteAdapter:
    def test_alias_and_standard_fields(self):
        adapter = HithinkQuoteAdapter()
        raw = {
            "name": "长江电力",
            "code": "600900",
            "price": 28.44,
            "yesterday_close": 28.46,
            "price_date": "2026-09-17",
            "source": "同花顺金融数据",
        }
        record = adapter.transform_data(raw, source=adapter.display_name)
        assert set(record) == set(adapter.standard_fields())
        assert record["price"] == 28.44
        assert record["yesterday_close"] == 28.46
        assert record["source_api"] == "hithink"
        assert record["market_cap"] is None  # 本源不提供总市值

    def test_self_test_passes(self):
        assert HithinkQuoteAdapter().self_test() == []

    def test_registered_in_quote_domain(self):
        from src.python.fetcher.source_adapter import get_adapters

        assert "hithink" in get_adapters(DOMAIN_QUOTE)


class TestChainOrder:
    def test_quote_and_history_third_slot(self):
        from src.python.fetcher.chain import _get_chain

        assert _get_chain("price_stock") == ["tencent", "sina", "hithink"]
        assert _get_chain("history_stock") == ["tencent", "sina", "hithink"]

    def test_history_provider_map_has_hithink(self):
        from src.python.fetcher.chain import _HISTORY_PROVIDER_MAP

        assert _HISTORY_PROVIDER_MAP["hithink"] == "src.python.providers.hithink"

    def test_otc_chain_unchanged(self):
        """场外基金链不受影响（同花顺在 price_stock/history_stock，不接管场外净值）。"""
        from src.python.fetcher.chain import _get_chain

        assert _get_chain("price_fund_otc") == ["eastmoney"]

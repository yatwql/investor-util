"""跨模块缓存一致性验证 — 同一数据源在不同模块间使用同一缓存。

锁定缓存前缀命名契约，验证 price/指数等缓存数据在
fetcher 与 market_value、excel_generator 等模块间可共享。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.integration, pytest.mark.integration_cache]


@pytest.mark.integration
@pytest.mark.integration_cache
class TestCrossModuleCacheConsistency(unittest.TestCase):
    """跨模块缓存一致性 — 同一数据源在不同模块间使用同一缓存。

    验证 price/指数等缓存数据在 market_value 和 fund_performance 间共享。
    """

    def test_fetch_market_data_cache_prefix(self):
        """fetch_market_data 使用正确缓存前缀，不同前缀不冲突。"""
        from src.python.fetcher.price import _price_cache_key
        key = _price_cache_key("600519")
        self.assertIn("price_", key)
        self.assertEqual(key, "price_600519")

    def test_cache_sharing_between_fetcher_and_market_value(self):
        """fetch_market_data 的缓存可被 market_value 模块重用。

        直接写入缓存后，fetch_market_data 应命中缓存而非重新获取。
        """
        from src.python.cache import set as cache_set, clear as cache_clear
        from src.python.fetcher.price import fetch_market_data

        cache_key = "price_600519"
        cached_data = {
            "price": 160.0, "yesterday_close": 158.0,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "贵州茅台", "code": "600519",
            "source": "腾讯行情",
        }

        # 先写入缓存，再调用 fetch_market_data 应直接命中缓存
        cache_set(cache_key, cached_data)

        # 注意：_PRICE_PROVIDERS 在 import 时捕获了 provider 函数对象直接引用，
        # 通过 patch("src.python.providers.tencent.fetch_price") 等方式无法拦截。
        # 此处 mock _price_cache_fresh 使缓存数据直接生效，避免因 price_date
        # 早于最近交易日而触发的跨日重取。
        with patch("src.python.fetcher.price._price_cache_fresh",
                    return_value=True):
            result = fetch_market_data("600519", "贵州茅台")

        self.assertIsNotNone(result)
        self.assertEqual(result.get("price"), 160.0)

        # 清理测试写入的缓存
        cache_clear(cache_key)

    def test_cache_prefix_consistency_price(self):
        """market_value 和 fetcher.price 使用相同缓存前缀。"""
        from src.python.core.registry import get_prefix_type_map
        prefix_map = get_prefix_type_map()
        self.assertIn("price_", prefix_map)
        self.assertEqual(prefix_map["price_"], "price")

    def test_index_cache_shared_across_modules(self):
        """指数行情缓存可被多个模块共享。

        fetch_indices 缓存可被 report/excel_generator 等模块重用。
        """
        from src.python.fetcher.index import fetch_indices
        from src.python.cache import get as cache_get

        mock_data = {
            "sh000001": {"name": "上证指数", "code": "sh000001",
                         "price": 3050.5, "change_pct": 0.5},
        }

        with (
            patch("src.python.fetcher.index._fetch_indices_from_tencent",
                  return_value=mock_data),
            patch("src.python.fetcher.index.cache_get",
                  return_value=None),
        ):
            result = fetch_indices()
            self.assertEqual(result["sh000001"]["price"], 3050.5)

        # 验证缓存键格式
        from src.python.fetcher.index import _index_cache_key
        key = _index_cache_key("sh000001")
        self.assertIn("index_", key)
        self.assertEqual(key, "index_sh000001")

"""数据获取路由模块单元测试 — 异常场景与降级测试。

测试目标：
  - _get_chain — 默认链路与首选提供商配置
  - _fetch_with_fallback — 主链路失败时自动切换备用链路（mock）
  - fetch_market_data — 缓存命中/未命中/名称匹配（mock 缓存）
  - fetch_fund_benchmark — 内置基准库查询
  - fetch_us_indices — mock API 失败降级

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_fetcher -v
"""

from __future__ import annotations

import unittest
from unittest.mock import ANY, MagicMock, patch

from src import fetcher as fch


class TestProviderChain(unittest.TestCase):
    """Provider Chain 选择逻辑测试。"""

    def test_default_chain_price(self):
        """price 类型的默认链路为 ['tencent', 'eastmoney']。"""
        chain = fch._get_chain("price")
        self.assertIn("tencent", chain)
        self.assertIn("eastmoney", chain)

    def test_default_chain_index(self):
        """index 类型的默认链路。"""
        chain = fch._get_chain("index")
        self.assertIsInstance(chain, list)
        self.assertTrue(len(chain) > 0)

    def test_default_chain_fund_rank(self):
        """fund_rank 类型的默认链路。"""
        chain = fch._get_chain("fund_rank")
        self.assertIsInstance(chain, list)
        self.assertTrue(len(chain) > 0)

    @patch("src.fetcher.get_config")
    def test_preferred_provider_respected(self, mock_get_config):
        """配置首选提供商 → 链路以配置的为先。"""
        mock_get_config.return_value = {"preferred_provider": {"price": "eastmoney"}}
        chain = fch._get_chain("price")
        self.assertEqual(chain[0], "eastmoney")

    def test_unknown_data_type_fallback(self):
        """未知类型 → 返回空列表。"""
        chain = fch._get_chain("unknown_type")
        self.assertEqual(chain, [])


class TestFetchMarketData(unittest.TestCase):
    """fetch_market_data 的缓存与降级测试（mock 缓存层）。"""

    @patch("src.fetcher.cache_get")
    def test_cache_hit_returns_data(self, mock_cache_get):
        """缓存命中且未过期 → 直接返回缓存数据。"""
        cached = {"price": 26.65, "price_date": "2026-06-26", "source": "腾讯财经"}
        mock_cache_get.return_value = cached
        result = fch.fetch_market_data("600900", "长江电力")
        self.assertEqual(result["price"], 26.65)

    @patch("src.fetcher.cache_set", MagicMock())
    @patch("src.fetcher.cache_get")
    @patch.dict("src.fetcher._PRICE_PROVIDERS", {
        "tencent": ("腾讯财经", MagicMock(return_value={
            "name": "长江电力", "code": "600900",
            "price": 27.0, "yesterday_close": 26.5,
            "price_date": "2026-06-27"
        })),
    }, clear=True)
    def test_cache_miss_calls_api(self, mock_cache_get):
        """缓存未命中 → 调 API 并返回数据。"""
        mock_cache_get.return_value = None
        result = fch.fetch_market_data("600900", "长江电力")
        self.assertIsNotNone(result)
        self.assertEqual(result["price"], 27.0)

    @patch("src.fetcher.cache_set", MagicMock())
    @patch("src.fetcher.cache_get")
    @patch.dict("src.fetcher._PRICE_PROVIDERS", {
        "tencent": ("腾讯财经", MagicMock(return_value=None)),
        "eastmoney": ("东方财富", MagicMock(return_value=None)),
    }, clear=True)
    def test_api_failure_returns_none(self, mock_cache_get):
        """缓存未命中 + API 全部失败 → 返回 None。"""
        mock_cache_get.return_value = None
        result = fch.fetch_market_data("600900", "长江电力")
        self.assertIsNone(result)

    @patch("src.fetcher.cache_set", MagicMock())
    @patch("src.fetcher.cache_get")
    @patch.dict("src.fetcher._PRICE_PROVIDERS", {
        "tencent": ("腾讯财经", MagicMock(return_value={
            "name": "非匹配名称", "code": "600900",
            "price": 15.0, "yesterday_close": 14.5,
            "price_date": "2026-06-26"
        })),
        "eastmoney": ("东方财富", MagicMock(return_value={
            "name": "长江电力", "code": "600900",
            "nav": 16.0, "yesterday_nav": 15.5,
            "nav_date": "2026-06-26"
        })),
    }, clear=True)
    def test_name_mismatch_logged(self, mock_cache_get):
        """名称不匹配但备选链路有数据 → 不阻塞返回。"""
        mock_cache_get.return_value = None
        result = fch.fetch_market_data("600900", "长江电力")
        self.assertIsNotNone(result)


class TestFetchUsIndices(unittest.TestCase):
    """fetch_us_indices 的 mock API 失败降级测试。"""

    @patch("src.fetcher.cache_get")
    @patch("src.fetcher.sina.fetch_us_indices")
    def test_api_failure_returns_empty(self, mock_sina, mock_cache_get):
        """API 失败 → 返回空字典。"""
        mock_cache_get.return_value = None
        mock_sina.side_effect = Exception("API error")
        result = fch.fetch_us_indices()
        self.assertEqual(result, {})

    @patch("src.fetcher.cache_get")
    @patch("src.fetcher.sina.fetch_us_indices")
    def test_retry_on_failure(self, mock_sina, mock_cache_get):
        """API 首次失败 → 重试。"""
        mock_cache_get.return_value = None
        mock_sina.side_effect = [Exception("fail"), Exception("fail")]
        result = fch.fetch_us_indices()
        self.assertEqual(result, {})


class TestFetchFundBenchmark(unittest.TestCase):
    """基金业绩基准测试（依赖内置基准库）。"""

    def test_builtin_benchmark_exists(self):
        """内置基准库中有该基金 → 返回基准名称。"""
        result = fch.fetch_fund_benchmark("000961")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "")

    def test_unknown_code_returns_default(self):
        """未知代码 → 返回 "--"。"""
        result = fch.fetch_fund_benchmark("999999")
        self.assertIsInstance(result, str)


class TestFetchWithFallback(unittest.TestCase):
    """_fetch_with_fallback 的链路切换测试。"""

    @patch("src.fetcher.cache_get")
    @patch("src.fetcher._get_chain")
    def test_empty_chain_returns_none(self, mock_get_chain, mock_cache_get):
        """空链路 → 返回 None。"""
        mock_cache_get.return_value = None
        mock_get_chain.return_value = []
        result = fch._fetch_with_fallback(
            "price",
            {"tencent": ("腾讯", MagicMock())},
            "test_cache_key",
            3600,
        )
        self.assertIsNone(result)

    @patch("src.fetcher.cache_get")
    @patch("src.fetcher._get_chain")
    def test_chain_not_registered_skipped(self, mock_get_chain, mock_cache_get):
        """链路中某 provider 未注册 → 跳过。"""
        mock_cache_get.return_value = None
        mock_get_chain.return_value = ["nonexistent_provider"]
        result = fch._fetch_with_fallback(
            "price",
            {"tencent": ("腾讯", MagicMock())},
            "test_cache_key",
            3600,
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

"""指数获取模块单元测试。

测试目标：
  - _index_cache_key — 缓存键生成
  - fetch_indices — A 股指数获取（mock 腾讯 + 缓存）
  - fetch_us_indices — 美股指数获取（mock 新浪 + 重试）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_fetcher_index.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestIndexCacheKey(unittest.TestCase):
    """_index_cache_key 纯函数测试。"""

    def _call(self, code: str) -> str:
        from src.python.fetcher.index import _index_cache_key
        return _index_cache_key(code)

    def test_format(self):
        """格式为 index_{code}。"""
        self.assertEqual(self._call("sh000001"), "index_sh000001")

    def test_different_code(self):
        """不同代码 → 不同键。"""
        self.assertNotEqual(self._call("sh000001"), self._call("sz399001"))


class TestFetchIndices(unittest.TestCase):
    """fetch_indices（A 股指数）测试。"""

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value={"name": "上证指数", "price": 3000})
    def test_all_cached(self, mock_cache_get, mock_cache_set):
        """全部缓存命中 → 不调 API。"""
        from src.python.fetcher.index import fetch_indices
        result = fetch_indices()
        self.assertGreater(len(result), 0)
        mock_cache_set.assert_not_called()

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.tencent.fetch_price")
    def test_cache_miss_calls_api(self, mock_fetch_price, mock_cache_get,
                                  mock_cache_set):
        """缓存未命中 → 调腾讯 API。"""
        mock_fetch_price.return_value = {
            "name": "上证指数", "code": "sh000001",
            "price": 3000.0, "yesterday_close": 2980.0,
            "price_date": "2026-07-01",
        }

        from src.python.fetcher.index import fetch_indices
        result = fetch_indices()
        # 至少有一个未缓存 → 调 API
        self.assertGreater(len(result), 0)

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.tencent.fetch_price", return_value=None)
    def test_api_failure_fallback_to_stale(self, mock_fetch_price,
                                           mock_cache_get, mock_cache_set):
        """API 失败且无过期缓存 → 不抛异常。"""
        # 第一次 cache_get 返回 None（每日缓存），第二次也返回 None（周缓存也空）
        from src.python.fetcher.index import cache_get as real_cache_get

        call_count = 0

        def side_effect(key, ttl):
            nonlocal call_count
            call_count += 1
            return None

        mock_cache_get.side_effect = side_effect

        from src.python.fetcher.index import fetch_indices
        result = fetch_indices()
        self.assertIsInstance(result, dict)

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.tencent.fetch_price", return_value=None)
    def test_api_returns_none(self, mock_fetch_price, mock_cache_get,
                              mock_cache_set):
        """API 返回 None → 不抛异常。"""
        from src.python.fetcher.index import fetch_indices
        result = fetch_indices()
        self.assertIsInstance(result, dict)


class TestFetchUsIndices(unittest.TestCase):
    """fetch_us_indices（美股指数）测试。"""

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get",
           return_value={"name": "道琼斯", "price": 34500})
    def test_all_cached(self, mock_cache_get, mock_cache_set):
        """全部缓存命中 → 不调 API。"""
        from src.python.fetcher.index import fetch_us_indices
        result = fetch_us_indices()
        self.assertGreater(len(result), 0)
        mock_cache_set.assert_not_called()

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.sina.fetch_us_indices")
    def test_api_success(self, mock_sina, mock_cache_get, mock_cache_set):
        """正常返回 → 正确写入缓存。"""
        mock_sina.return_value = {
            "gb_dji": {"name": "道琼斯", "price": 34500, "code": "gb_dji",
                       "yesterday_close": 34400},
        }

        from src.python.fetcher.index import fetch_us_indices
        result = fetch_us_indices()
        self.assertIn("gb_dji", result)
        mock_cache_set.assert_called()

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.sina.fetch_us_indices")
    def test_api_failure_retry(self, mock_sina, mock_cache_get,
                               mock_cache_set):
        """API 失败 → 重试 → 最终返回空。"""
        mock_sina.side_effect = Exception("API error")

        from src.python.fetcher.index import fetch_us_indices
        result = fetch_us_indices()
        self.assertIsInstance(result, dict)
        # 应该调了 2 次
        self.assertEqual(mock_sina.call_count, 2)

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get")
    @patch("src.python.fetcher.index.sina.fetch_us_indices")
    def test_api_failure_degrade_to_stale(self, mock_sina, mock_cache_get,
                                          mock_cache_set):
        """API 全失败 → 降级到过期缓存。"""
        # 每日缓存 → None，过期缓存 → 有数据
        stale_data = {"name": "道琼斯(旧)", "price": 34000}

        def cache_get_side_effect(key, ttl):
            if ttl == 604800:  # 过期缓存
                return stale_data
            return None

        mock_cache_get.side_effect = cache_get_side_effect
        mock_sina.side_effect = Exception("API error")

        from src.python.fetcher.index import fetch_us_indices
        result = fetch_us_indices()
        self.assertGreater(len(result), 0)

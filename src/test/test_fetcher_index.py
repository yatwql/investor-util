"""指数获取模块单元测试。

测试目标：
  - _index_cache_key — 缓存键生成
  - fetch_indices — A 股指数获取（腾讯主链路 + 新浪备用链路 + 缓存降级）
  - fetch_us_indices — 美股指数获取（新浪主链路 + 腾讯备用链路 + 缓存降级）

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
    def test_tencent_success(self, mock_fetch_price, mock_cache_get,
                              mock_cache_set):
        """腾讯主链路成功 → 不调新浪备用。"""
        mock_fetch_price.return_value = {
            "name": "上证指数", "code": "sh000001",
            "price": 3000.0, "yesterday_close": 2980.0,
            "price_date": "2026-07-01",
        }

        from src.python.fetcher.index import fetch_indices
        result = fetch_indices()
        self.assertGreater(len(result), 0)

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.tencent.fetch_price", return_value=None)
    @patch("src.python.fetcher.index.sina.fetch_a_indices")
    def test_tencent_fail_sina_fallback(self, mock_sina, mock_fetch_price,
                                         mock_cache_get, mock_cache_set):
        """腾讯失败 → 新浪备用链路成功。"""
        mock_sina.return_value = {
            "s_sh000001": {"name": "上证指数", "price": 2990.0,
                           "yesterday_close": 2970.0, "price_date": "2026-07-01",
                           "change": 20.0, "change_pct": 0.67},
        }

        from src.python.fetcher.index import fetch_indices
        result = fetch_indices()
        self.assertGreater(len(result), 0)
        mock_sina.assert_called_once()

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.tencent.fetch_price", return_value=None)
    @patch("src.python.fetcher.index.sina.fetch_a_indices", return_value={})
    def test_both_fail_no_stale(self, mock_sina, mock_fetch_price,
                                mock_cache_get, mock_cache_set):
        """腾讯+新浪都失败且无过期缓存 → 不抛异常。"""
        # 第一次 get（每日TTL）→ None，第二次 get（周缓存）→ None
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
    @patch("src.python.fetcher.index.sina.fetch_a_indices", return_value={})
    def test_both_fail_degrade_to_stale(self, mock_sina, mock_fetch_price,
                                        mock_cache_get, mock_cache_set):
        """腾讯+新浪都失败 → 降级到过期缓存。"""
        stale_data = {"name": "上证指数(旧)", "price": 2950}

        from src.python.fetcher.index import cache_get as real_cache_get

        call_count = 0

        def side_effect(key, ttl):
            nonlocal call_count
            call_count += 1
            if call_count >= 6:  # 第 6 次调用是过期缓存读取（CACHE_WEEKLY）
                return stale_data
            return None

        mock_cache_get.side_effect = side_effect

        from src.python.fetcher.index import fetch_indices
        result = fetch_indices()
        self.assertGreater(len(result), 0)


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
    def test_sina_success(self, mock_sina, mock_cache_get, mock_cache_set):
        """新浪主链路成功 → 不调腾讯备用。"""
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
    def test_sina_failure_retry_then_tencent(self, mock_sina, mock_cache_get,
                                              mock_cache_set):
        """新浪失败 2 次 → 腾讯备用链路。"""
        mock_sina.side_effect = Exception("API error")

        from src.python.fetcher.index import fetch_us_indices
        with patch("src.python.fetcher.index.tencent.fetch_index_price") as mock_tencent:
            mock_tencent.return_value = {
                "name": "道琼斯", "price": 34400,
                "yesterday_close": 34300, "price_date": "2026-07-01",
            }
            result = fetch_us_indices()
            self.assertIn("gb_dji", result)
            # Sina 调了 2 次（重试），Tencent 调了
            self.assertEqual(mock_sina.call_count, 2)
            mock_tencent.assert_called()

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.sina.fetch_us_indices")
    def test_both_fail_retry_count(self, mock_sina, mock_cache_get,
                                   mock_cache_set):
        """新浪+腾讯都失败 → 调用计数正确。"""
        mock_sina.side_effect = Exception("API error")

        from src.python.fetcher.index import fetch_us_indices
        with patch("src.python.fetcher.index.tencent.fetch_index_price",
                   return_value=None) as mock_tencent:
            result = fetch_us_indices()
            self.assertIsInstance(result, dict)
            self.assertEqual(mock_sina.call_count, 2)

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get")
    @patch("src.python.fetcher.index.sina.fetch_us_indices")
    def test_sina_fail_tencent_fail_degrade_to_stale(self, mock_sina,
                                                      mock_cache_get,
                                                      mock_cache_set):
        """新浪+腾讯都失败 → 降级到过期缓存。"""
        stale_data = {"name": "道琼斯(旧)", "price": 34000}

        def cache_get_side_effect(key, ttl):
            if ttl == 604800:  # 过期缓存
                return stale_data
            return None

        mock_cache_get.side_effect = cache_get_side_effect
        mock_sina.side_effect = Exception("API error")

        from src.python.fetcher.index import fetch_us_indices
        with patch("src.python.fetcher.index.tencent.fetch_index_price",
                   return_value=None) as mock_tencent:
            result = fetch_us_indices()
            self.assertGreater(len(result), 0)

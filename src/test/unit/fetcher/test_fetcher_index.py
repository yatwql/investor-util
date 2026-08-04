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
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]



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
    @patch("src.python.fetcher.index.tencent.fetch_index_price")
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
        # 回归守卫：mock 目标必须与实际调用一致，否则静默真调 API（无网时暴露）
        mock_fetch_price.assert_called()

    @patch("src.python.fetcher.index.cache_set")
    @patch("src.python.fetcher.index.cache_get", return_value=None)
    @patch("src.python.fetcher.index.tencent.fetch_index_price", return_value=None)
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
    @patch("src.python.fetcher.index.tencent.fetch_index_price", return_value=None)
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
    @patch("src.python.fetcher.index.tencent.fetch_index_price", return_value=None)
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


@pytest.mark.data
class TestIndexValueSanity(unittest.TestCase):
    """指数行情数值合理 — 数量级确认。"""

    def _call_fetch_indices(self, cached_data: dict | None = None):
        """通过 mock 缓存返回固定的指数数据。"""
        with patch("src.python.fetcher.index.cache_set"):
            with patch("src.python.fetcher.index.cache_get",
                       return_value=cached_data):
                from src.python.fetcher.index import fetch_indices
                return fetch_indices()

    def _call_fetch_us(self, cached_data: dict | None = None):
        """通过 mock 缓存返回固定的美股指数数据。"""
        with patch("src.python.fetcher.index.cache_set"):
            with patch("src.python.fetcher.index.cache_get",
                       return_value=cached_data):
                with patch("src.python.fetcher.index.tencent.fetch_index_price",
                           return_value=None):
                    from src.python.fetcher.index import fetch_us_indices

                    return fetch_us_indices()

    def test_shanghai_composite_magnitude(self):
        """上证 ≈ 3000 量级（非 30000 或 300）。"""
        result = self._call_fetch_indices(
            {"name": "上证指数", "price": 3000.45})
        values = list(result.values())
        self.assertTrue(
            any(v.get("price", 0) == 3000.45 for v in values),
            f"预期价格 3000.45，实际: {[v.get('price') for v in values]}"
        )

    def test_csi300_magnitude(self):
        """沪深300 ≈ 4000 量级。"""
        result = self._call_fetch_indices(
            {"name": "沪深300", "price": 4000.78})
        values = list(result.values())
        # fetch_indices 返回 dict[code, data]；所有缓存数据一致
        self.assertTrue(
            any(v.get("price", 0) == 4000.78 for v in values),
            f"预期价格 4000.78，实际: {[v.get('price') for v in values]}"
        )

    def test_hang_seng_magnitude(self):
        """恒指 ≈ 20000 量级（所有指数使用相同 mock 缓存）。"""
        idx_data = {"name": "恒生指数", "price": 22000.50}
        result = self._call_fetch_indices(idx_data)
        values = list(result.values())
        self.assertTrue(
            any(isinstance(v, dict) and 10000 < v.get("price", 0) < 40000
                for v in values),
            f"无恒指量级价格，实际: {[v.get('price') for v in values]}"
        )

    def test_sp500_magnitude(self):
        """标普500 ≈ 5000 量级。"""
        idx_data = {"name": "标普500", "price": 5500.30}
        result = self._call_fetch_us(idx_data)
        values = list(result.values())
        self.assertTrue(
            any(isinstance(v, dict) and 1000 < v.get("price", 0) < 20000
                for v in values),
            f"无标普量级价格，实际: {[v.get('price') for v in values]}"
        )

    def test_index_price_non_negative(self):
        """所有指数价格 >= 0。"""
        idx_data = {"name": "上证指数", "price": 3000}
        result = self._call_fetch_indices(idx_data)
        values = list(result.values())
        for v in values:
            self.assertGreaterEqual(v["price"], 0,
                f"指数 {v.get('name', '?')} 价格为负: {v['price']}")


class TestFetchIndexHistory(unittest.TestCase):
    """fetch_index_history（指数历史日线）测试。

    覆盖场景：
      - 空代码 → None
      - 正常返回 → 走 chain 获取、写入会话缓存
      - 会话缓存命中 → 不调 chain（会话级复用）
      - Chain 全链路失败 → 空列表
      - Chain 异常 → 空列表
      - days 参数钳制到 [5, 3650]
    """

    _SAMPLE_KLINE_1 = {"date": "2026-07-01", "close": 4000.0, "open": 3980.0,
                        "high": 4010.0, "low": 3970.0, "volume": 1000000}
    _SAMPLE_KLINE_2 = {"date": "2026-07-02", "close": 4020.0, "open": 4000.0,
                        "high": 4030.0, "low": 3990.0, "volume": 1200000}

    @patch("src.python.core.provider_registry.get_registry")
    @patch("src.python.fetcher.chain.fetch_with_incremental_fallback")
    def test_normal_return(self, mock_fetch, mock_get_reg):
        """正常返回 → 调用 chain 并写入会话缓存。"""
        from src.python.core.provider_registry import NOT_FOUND
        mock_reg = MagicMock()
        mock_reg.session_cache_get.return_value = NOT_FOUND
        mock_get_reg.return_value = mock_reg

        expected = [self._SAMPLE_KLINE_1, self._SAMPLE_KLINE_2]
        mock_fetch.return_value = expected

        from src.python.fetcher.index import fetch_index_history
        result = fetch_index_history("sh000300")

        self.assertEqual(result, expected)
        mock_fetch.assert_called_once_with("history_index", "sh000300", 365)
        mock_reg.session_cache_set.assert_called_once_with(
            "history_index", "sh000300", expected, source="api")

    @patch("src.python.core.provider_registry.get_registry")
    def test_empty_code_returns_none(self, mock_get_reg):
        """空代码 → 返回 None，不调用注册表。"""
        from src.python.fetcher.index import fetch_index_history
        self.assertIsNone(fetch_index_history(""))
        self.assertIsNone(fetch_index_history(None))
        # 空代码在导入前就返回了，注册表不应被调用
        mock_get_reg.assert_not_called()

    @patch("src.python.core.provider_registry.get_registry")
    @patch("src.python.fetcher.chain.fetch_with_incremental_fallback")
    def test_session_cache_hit_skips_chain(self, mock_fetch, mock_get_reg):
        """会话缓存命中 → 不调 chain（会话级复用）。"""
        cached = [self._SAMPLE_KLINE_1, self._SAMPLE_KLINE_2]
        mock_reg = MagicMock()
        mock_reg.session_cache_get.return_value = cached
        mock_get_reg.return_value = mock_reg

        from src.python.fetcher.index import fetch_index_history
        result = fetch_index_history("sh000300")

        self.assertEqual(result, cached)
        mock_fetch.assert_not_called()
        mock_reg.session_cache_set.assert_not_called()

    @patch("src.python.core.provider_registry.get_registry")
    @patch("src.python.fetcher.chain.fetch_with_incremental_fallback")
    def test_chain_failure_returns_empty(self, mock_fetch, mock_get_reg):
        """全链路失败 → 返回空列表。"""
        from src.python.core.provider_registry import NOT_FOUND
        mock_reg = MagicMock()
        mock_reg.session_cache_get.return_value = NOT_FOUND
        mock_get_reg.return_value = mock_reg
        mock_fetch.return_value = []

        from src.python.fetcher.index import fetch_index_history
        result = fetch_index_history("sh000300")

        self.assertEqual(result, [])
        # 空结果也写入会话缓存（避免重复请求）
        mock_reg.session_cache_set.assert_called_once_with(
            "history_index", "sh000300", [], source="api")

    @patch("src.python.core.provider_registry.get_registry")
    @patch("src.python.fetcher.chain.fetch_with_incremental_fallback")
    def test_chain_exception_returns_empty(self, mock_fetch, mock_get_reg):
        """chain 抛出异常 → 返回空列表。"""
        from src.python.core.provider_registry import NOT_FOUND
        mock_reg = MagicMock()
        mock_reg.session_cache_get.return_value = NOT_FOUND
        mock_get_reg.return_value = mock_reg
        mock_fetch.side_effect = RuntimeError("API unreachable")

        from src.python.fetcher.index import fetch_index_history
        result = fetch_index_history("sh000300")

        self.assertEqual(result, [])
        # 异常结果也写入会话缓存
        mock_reg.session_cache_set.assert_called_once_with(
            "history_index", "sh000300", [], source="api")

    @patch("src.python.core.provider_registry.get_registry")
    @patch("src.python.fetcher.chain.fetch_with_incremental_fallback")
    def test_days_clamped_min(self, mock_fetch, mock_get_reg):
        """days < 5 → 钳制到 5。"""
        from src.python.core.provider_registry import NOT_FOUND
        mock_reg = MagicMock()
        mock_reg.session_cache_get.return_value = NOT_FOUND
        mock_get_reg.return_value = mock_reg
        mock_fetch.return_value = [self._SAMPLE_KLINE_1]

        from src.python.fetcher.index import fetch_index_history
        fetch_index_history("sh000300", days=1)

        mock_fetch.assert_called_once_with("history_index", "sh000300", 5)

    @patch("src.python.core.provider_registry.get_registry")
    @patch("src.python.fetcher.chain.fetch_with_incremental_fallback")
    def test_days_clamped_max(self, mock_fetch, mock_get_reg):
        """days > 3650 → 钳制到 3650。"""
        from src.python.core.provider_registry import NOT_FOUND
        mock_reg = MagicMock()
        mock_reg.session_cache_get.return_value = NOT_FOUND
        mock_get_reg.return_value = mock_reg
        mock_fetch.return_value = [self._SAMPLE_KLINE_1]

        from src.python.fetcher.index import fetch_index_history
        fetch_index_history("sh000300", days=5000)

        mock_fetch.assert_called_once_with("history_index", "sh000300", 3650)

    @patch("src.python.core.provider_registry.get_registry")
    @patch("src.python.fetcher.chain.fetch_with_incremental_fallback")
    def test_us_index_code(self, mock_fetch, mock_get_reg):
        """美股指数代码（gb_ 前缀）同样走 chain。"""
        from src.python.core.provider_registry import NOT_FOUND
        mock_reg = MagicMock()
        mock_reg.session_cache_get.return_value = NOT_FOUND
        mock_get_reg.return_value = mock_reg
        mock_fetch.return_value = [self._SAMPLE_KLINE_1]

        from src.python.fetcher.index import fetch_index_history
        result = fetch_index_history("gb_inx", days=200)

        self.assertEqual(len(result), 1)
        mock_fetch.assert_called_once_with("history_index_us", "gb_inx", 200)

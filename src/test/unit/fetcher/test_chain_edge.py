"""Provider Chain HTTP 错误回退 edge 专项测试。

从 test_chain.py 提取的 edge 场景：
  - HTTP 超时 → 回退
  - HTTP 429 限流 → 回退
  - HTTP 503 不可用 → 回退
  - 全部 Provider 各抛不同 HTTP 错误 → 降级到过期缓存

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/fetcher/test_chain_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher, pytest.mark.edge]


class TestFetchWithFallbackEdge(unittest.TestCase):
    """Provider Chain HTTP 特定错误回退 edge 场景。"""

    def setUp(self):
        self.provider_fn_map = {
            "p1": ("Provider1", None),
            "p2": ("Provider2", None),
        }

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_http_timeout_triggers_fallback(self, mock_chain, mock_set, mock_get):
        """Provider 超时 → 回退到下一链路。"""
        from src.python.fetcher.chain import _fetch_with_fallback
        import httpx
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(side_effect=httpx.TimeoutException("Connection timed out"))
        fn2 = MagicMock(return_value={"data": "fallback_ok"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "fallback_ok"})
        fn1.assert_called_once()
        fn2.assert_called_once()

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_http_429_triggers_fallback(self, mock_chain, mock_set, mock_get):
        """HTTP 429 限流 → 回退到下一链路。"""
        from src.python.fetcher.chain import _fetch_with_fallback
        import httpx
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        req = httpx.Request("GET", "https://api.test.com")
        resp = httpx.Response(429, request=req)
        fn1 = MagicMock(side_effect=httpx.HTTPStatusError("Too Many", request=req, response=resp))
        fn2 = MagicMock(return_value={"data": "fallback_429"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "fallback_429"})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_http_503_triggers_fallback(self, mock_chain, mock_set, mock_get):
        """HTTP 503 服务不可用 → 回退到下一链路。"""
        from src.python.fetcher.chain import _fetch_with_fallback
        import httpx
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        req = httpx.Request("GET", "https://api.test.com")
        resp = httpx.Response(503, request=req)
        fn1 = MagicMock(side_effect=httpx.HTTPStatusError("Unavailable", request=req, response=resp))
        fn2 = MagicMock(return_value={"data": "fallback_503"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "fallback_503"})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_all_providers_http_errors_fall_to_stale(self, mock_chain, mock_set, mock_get):
        """全部 Provider 各抛不同 HTTP 错误 → 降级到过期缓存。"""
        from src.python.fetcher.chain import _fetch_with_fallback
        import httpx
        mock_chain.return_value = ["p1", "p2"]
        # 第一次 cache_get（新鲜缓存）→ None；第二次（过期降级）→ stale
        mock_get.side_effect = [None, {"stale": True, "price": 99.0}]
        req = httpx.Request("GET", "https://api.test.com")
        fn1 = MagicMock(side_effect=httpx.HTTPStatusError("429", request=req,
                          response=httpx.Response(429, request=req)))
        fn2 = MagicMock(side_effect=httpx.TimeoutException("timeout"))
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"stale": True, "price": 99.0})


if __name__ == "__main__":
    unittest.main()

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
from src.python.fetcher.chain import reset_provider_skip

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher, pytest.mark.edge]


class TestFetchWithFallbackEdge(unittest.TestCase):
    """Provider Chain HTTP 特定错误回退 edge 场景。"""

    def setUp(self):
        reset_provider_skip()  # 清除前序测试的熔断状态
        self.provider_fn_map = {
            "p1": ("Provider1", None),
            "p2": ("Provider2", None),
        }

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_http_timeout_triggers_fallback(self, mock_chain, mock_set, mock_get):
        """Provider 超时 → 回退到下一链路。"""
        from src.python.fetcher.chain import _fetch_with_fallback, reset_provider_skip
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
        from src.python.fetcher.chain import _fetch_with_fallback, reset_provider_skip
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
        from src.python.fetcher.chain import _fetch_with_fallback, reset_provider_skip
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
        from src.python.fetcher.chain import _fetch_with_fallback, reset_provider_skip
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


@pytest.mark.edge
class TestCircuitBreakerCooldownProbe(unittest.TestCase):
    """熔断冷却期满后的试探恢复行为。

    熔断触发后 _PROVIDER_COOLDOWN_SECS（300s）内跳过该 provider，
    期满后放行一次试探请求：成功则恢复，失败则重新计时。
    """

    def setUp(self):
        reset_provider_skip()
        self.provider_map = {
            "p1": ("P1", MagicMock()),
            "p2": ("P2", MagicMock(return_value={"data": "fallback"})),
        }

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_cooldown_expired_allows_probe_success(self, mock_chain, mock_set, mock_get):
        """冷却期满 → 试探请求 → 成功 → 恢复。"""
        from src.python.fetcher.chain import (
            _PROVIDER_COOLDOWN_SECS,
            _PROVIDER_SKIP,
            _PROVIDER_SKIP_TIME,
            _fetch_with_fallback,
        )
        import time
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None

        # 将 p1 置于熔断状态且冷却已过期
        _PROVIDER_SKIP.add("p1")
        _PROVIDER_SKIP_TIME["p1"] = time.time() - _PROVIDER_COOLDOWN_SECS - 1
        p1_fn = MagicMock(return_value={"data": "probe_ok"})
        self.provider_map["p1"] = ("P1", p1_fn)

        result = _fetch_with_fallback("price", self.provider_map, "k1", 3600)

        self.assertEqual(result, {"data": "probe_ok"})
        p1_fn.assert_called_once()  # 试探请求被放行
        self.assertNotIn("p1", _PROVIDER_SKIP)  # 熔断已清除

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_cooldown_expired_probe_fails(self, mock_chain, mock_set, mock_get):
        """冷却期满 → 试探请求 → 失败 → 计数器重置为 1，后续连续失败才重新熔断。"""
        from src.python.fetcher.chain import (
            _PROVIDER_COOLDOWN_SECS,
            _PROVIDER_SKIP,
            _PROVIDER_SKIP_TIME,
            _fetch_with_fallback,
        )
        import time
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None

        # 将 p1 置于熔断状态且冷却已过期
        _PROVIDER_SKIP.add("p1")
        _PROVIDER_SKIP_TIME["p1"] = time.time() - _PROVIDER_COOLDOWN_SECS - 1
        p1_fn = MagicMock(return_value=None)  # 试探仍然失败
        self.provider_map["p1"] = ("P1", p1_fn)

        # 第1次：探头失败 → p2 兜底 → p1 计数器 = 1，尚未重新熔断
        result = _fetch_with_fallback("price", self.provider_map, "k2a", 3600)
        self.assertEqual(result, {"data": "fallback"})
        p1_fn.assert_called_once()
        self.assertNotIn("p1", _PROVIDER_SKIP)  # 未重新熔断

        # 第2次：p1 计数器 = 2，仍不熔断
        p1_fn.reset_mock()
        result = _fetch_with_fallback("price", self.provider_map, "k2b", 3600)
        self.assertEqual(result, {"data": "fallback"})
        self.assertNotIn("p1", _PROVIDER_SKIP)

        # 第3次：p1 计数器 = 3，重新熔断
        p1_fn.reset_mock()
        result = _fetch_with_fallback("price", self.provider_map, "k2c", 3600)
        self.assertEqual(result, {"data": "fallback"})
        self.assertIn("p1", _PROVIDER_SKIP)  # 重新熔断

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_cooldown_not_expired_still_skipped(self, mock_chain, mock_set, mock_get):
        """冷却期内 → 仍跳过，不放行。"""
        from src.python.fetcher.chain import (
            _PROVIDER_SKIP,
            _PROVIDER_SKIP_TIME,
            _fetch_with_fallback,
        )
        import time
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None

        # p1 刚刚被熔断（冷却未过期）
        _PROVIDER_SKIP.add("p1")
        _PROVIDER_SKIP_TIME["p1"] = time.time()
        p1_fn = MagicMock(return_value={"data": "should_not_call"})
        self.provider_map["p1"] = ("P1", p1_fn)

        result = _fetch_with_fallback("price", self.provider_map, "k3", 3600)

        self.assertEqual(result, {"data": "fallback"})
        p1_fn.assert_not_called()  # 未放行

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_no_skip_time_fallback_to_probe(self, mock_chain, mock_set, mock_get):
        """熔断但无时间戳（兼容旧状态）→ 视为冷却已过期，放行试探。"""
        from src.python.fetcher.chain import (
            _PROVIDER_SKIP,
            _fetch_with_fallback,
        )
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None

        # p1 在跳过集合中但 SKIP_TIME 无记录
        _PROVIDER_SKIP.add("p1")
        p1_fn = MagicMock(return_value={"data": "probe_ok"})
        self.provider_map["p1"] = ("P1", p1_fn)

        result = _fetch_with_fallback("price", self.provider_map, "k4", 3600)

        # _skip_time=0 → time.time()-0>=300 → 视为冷却已过期，放行试探
        self.assertEqual(result, {"data": "probe_ok"})
        p1_fn.assert_called_once()
        self.assertNotIn("p1", _PROVIDER_SKIP)  # 试探成功，熔断清除


if __name__ == "__main__":
    unittest.main()

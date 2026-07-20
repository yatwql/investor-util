"""Provider Chain HTTP 错误回退 edge 专项测试。

edge 场景：
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
        from src.python.fetcher.chain import fetch_with_fallback, reset_provider_skip
        import httpx
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(side_effect=httpx.TimeoutException("Connection timed out"))
        fn2 = MagicMock(return_value={"data": "fallback_ok"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "fallback_ok"})
        fn1.assert_called_once()
        fn2.assert_called_once()

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_http_429_triggers_fallback(self, mock_chain, mock_set, mock_get):
        """HTTP 429 限流 → 回退到下一链路。"""
        from src.python.fetcher.chain import fetch_with_fallback, reset_provider_skip
        import httpx
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        req = httpx.Request("GET", "https://api.test.com")
        resp = httpx.Response(429, request=req)
        fn1 = MagicMock(side_effect=httpx.HTTPStatusError("Too Many", request=req, response=resp))
        fn2 = MagicMock(return_value={"data": "fallback_429"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "fallback_429"})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_http_503_triggers_fallback(self, mock_chain, mock_set, mock_get):
        """HTTP 503 服务不可用 → 回退到下一链路。"""
        from src.python.fetcher.chain import fetch_with_fallback, reset_provider_skip
        import httpx
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        req = httpx.Request("GET", "https://api.test.com")
        resp = httpx.Response(503, request=req)
        fn1 = MagicMock(side_effect=httpx.HTTPStatusError("Unavailable", request=req, response=resp))
        fn2 = MagicMock(return_value={"data": "fallback_503"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "fallback_503"})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_all_providers_http_errors_fall_to_stale(self, mock_chain, mock_set, mock_get):
        """全部 Provider 各抛不同 HTTP 错误 → 降级到过期缓存。"""
        from src.python.fetcher.chain import fetch_with_fallback, reset_provider_skip
        import httpx
        mock_chain.return_value = ["p1", "p2"]
        # 第一次 cache_get（新鲜缓存）→ None；第二次（过期降级）→ stale
        mock_get.side_effect = [None, {"stale": True, "price": 99.0}]
        req = httpx.Request("GET", "https://api.test.com")
        fn1 = MagicMock(side_effect=httpx.HTTPStatusError("429", request=req,
                          response=httpx.Response(429, request=req)))
        fn2 = MagicMock(side_effect=httpx.TimeoutException("timeout"))
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"stale": True, "price": 99.0})


@pytest.mark.edge
class TestCircuitBreakerCooldownProbe(unittest.TestCase):
    """熔断冷却期满后的试探恢复行为（委托 DataSourceRegistry）。

    熔断逻辑集中在 provider_registry.py，此测试验证 chain.py 的 fetch_with_fallback
    通过 registry 正确响应冷却期状态。
    """

    def setUp(self):
        reset_provider_skip()
        self.provider_map = {
            "p1": ("P1", MagicMock()),
            "p2": ("P2", MagicMock(return_value={"data": "fallback"})),
        }

    def _break_provider(self, name: str, at_time: float):
        """在指定时间点模拟 provider 连续 3 次传输级失败。"""
        from src.python.provider_registry import get_registry
        with patch("src.python.provider_registry.time.time", return_value=at_time):
            reg = get_registry()
            reg.register_provider(name, 2)
            reg.record_failure(name, "test")
            reg.record_failure(name, "test")
            reg.record_failure(name, "test")

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_cooldown_expired_allows_probe_success(self, mock_chain, mock_set, mock_get):
        """冷却期满 → 试探请求 → 成功 → 恢复。"""
        # p1 在 700.0 触发熔断，当前 1001.0（已过 300s 冷却）
        self._break_provider("p1", 700.0)
        self._break_provider("p2", 1000.0)
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        p1_fn = MagicMock(return_value={"data": "probe_ok"})
        self.provider_map["p1"] = ("P1", p1_fn)

        with patch("src.python.provider_registry.time.time", return_value=1001.0):
            from src.python.fetcher.chain import fetch_with_fallback
            result = fetch_with_fallback("price", self.provider_map, "k1", 3600)

        self.assertEqual(result, {"data": "probe_ok"})
        p1_fn.assert_called_once()  # 试探请求被放行
        from src.python.provider_registry import get_registry
        self.assertFalse(get_registry().is_circuit_broken("p1"))  # 熔断已清除

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_cooldown_expired_probe_fails(self, mock_chain, mock_set, mock_get):
        """冷却期满 → 试探请求 → 失败 → 计数器重置为 1，后续连续失败才重新熔断。"""
        # p1 在 700.0 触发熔断，当前 1001.0（冷却已过期）
        self._break_provider("p1", 700.0)
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        p1_fn = MagicMock(side_effect=RuntimeError("transport error"))
        self.provider_map["p1"] = ("P1", p1_fn)

        with patch("src.python.provider_registry.time.time", return_value=1001.0):
            from src.python.fetcher.chain import fetch_with_fallback

            # 第1次：探头失败 → p2 兜底 → p1 计数器 = 1，尚未重新熔断
            result = fetch_with_fallback("price", self.provider_map, "k2a", 3600)
            self.assertEqual(result, {"data": "fallback"})
            p1_fn.assert_called_once()
            from src.python.provider_registry import get_registry
            self.assertFalse(get_registry().is_circuit_broken("p1"))  # 未重新熔断

            # 第2次：p1 计数器 = 2，仍不熔断
            p1_fn.reset_mock()
            result = fetch_with_fallback("price", self.provider_map, "k2b", 3600)
            self.assertEqual(result, {"data": "fallback"})
            self.assertFalse(get_registry().is_circuit_broken("p1"))

            # 第3次：p1 计数器 = 3，重新熔断
            p1_fn.reset_mock()
            result = fetch_with_fallback("price", self.provider_map, "k2c", 3600)
            self.assertEqual(result, {"data": "fallback"})
            self.assertTrue(get_registry().is_circuit_broken("p1"))  # 重新熔断

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_cooldown_not_expired_still_skipped(self, mock_chain, mock_set, mock_get):
        """冷却期内 → 仍跳过，不放行。"""
        # p1 在 900.0 触发熔断，当前 950.0（仅过 50s，冷却期未满）
        self._break_provider("p1", 900.0)
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        p1_fn = MagicMock(return_value={"data": "should_not_call"})
        self.provider_map["p1"] = ("P1", p1_fn)

        with patch("src.python.provider_registry.time.time", return_value=950.0):
            from src.python.fetcher.chain import fetch_with_fallback
            result = fetch_with_fallback("price", self.provider_map, "k3", 3600)

        self.assertEqual(result, {"data": "fallback"})
        p1_fn.assert_not_called()  # 未放行

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_no_skip_time_fallback_to_probe(self, mock_chain, mock_set, mock_get):
        """registry 中无 last_failure_time（初始状态）→ is_circuit_broken 返回 False 直接放行。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        # p1 从未被熔断（不在 registry 中），registry.is_circuit_broken 返回 False
        p1_fn = MagicMock(return_value={"data": "probe_ok"})
        self.provider_map["p1"] = ("P1", p1_fn)

        from src.python.fetcher.chain import fetch_with_fallback
        result = fetch_with_fallback("price", self.provider_map, "k4", 3600)

        self.assertEqual(result, {"data": "probe_ok"})
        p1_fn.assert_called_once()


if __name__ == "__main__":
    unittest.main()

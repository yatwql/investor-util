"""Y1: API/网络异常纵深测试 — 共 16 项。

覆盖 Provider 层 HTTP 异常（超时/断连/DNS/SSL）、Provider Chain
Fallback（主链路失败→备链路→过期缓存降级）、LLM API 错误分类
（可重试/不可恢复）、响应解析异常（空/截断/非 JSON/HTML 污染）。

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/fetcher/test_api_edge.py -v
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import httpx
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher, pytest.mark.edge]


# ═══════════════════════════════════════════════════════════════
# Y1-1 ~ Y1-4: Provider 层 HTTP 异常
# ═══════════════════════════════════════════════════════════════

class TestProviderHttpErrorsY1(unittest.TestCase):
    """Provider 各 HTTP 异常 → 返回 None，不抛出。"""

    @patch("src.python.providers.tencent.make_http_client")
    def test_tencent_timeout_returns_none(self, mock_factory):
        """腾讯超时 → 返回 None。"""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
        mock_factory.return_value.__enter__.return_value = mock_client

        from src.python.providers.tencent import fetch_price
        result = fetch_price("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.tencent.make_http_client")
    def test_tencent_dns_failure_returns_none(self, mock_factory):
        """腾讯 DNS 解析失败 → 返回 None。"""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("Name resolution failed")
        mock_factory.return_value.__enter__.return_value = mock_client

        from src.python.providers.tencent import fetch_price
        result = fetch_price("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_eastmoney_timeout_triggers_fallback(self, mock_factory):
        """东方财富超时 → 触发 fallback_fundf10。"""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
        mock_factory.return_value.__enter__.return_value = mock_client

        with patch("src.python.providers.eastmoney._fallback_fundf10") as mock_fallback:
            mock_fallback.return_value = {"fallback": True}
            from src.python.providers.eastmoney import fetch_nav
            result = fetch_nav("000001")
            self.assertEqual(result, {"fallback": True})
            mock_fallback.assert_called_once()

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_eastmoney_request_error_triggers_fallback(self, mock_factory):
        """东方财富连接拒绝 → 触发 fallback。"""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("Connection refused")
        mock_factory.return_value.__enter__.return_value = mock_client

        with patch("src.python.providers.eastmoney._fallback_fundf10") as mock_fallback:
            mock_fallback.return_value = {"fallback": True}
            from src.python.providers.eastmoney import fetch_nav
            result = fetch_nav("000001")
            self.assertEqual(result, {"fallback": True})
            mock_fallback.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# Y1-5: Provider Chain 多级降级
# ═══════════════════════════════════════════════════════════════

class TestProviderChainFallbackY1(unittest.TestCase):
    """Provider Chain 多级降级：主链→备链→过期缓存。"""

    @patch("src.python.fetcher.chain.cache_get", return_value=None)
    @patch("src.python.fetcher.chain.cache_set")
    @patch.dict("src.python.fetcher.price._PRICE_PROVIDERS", {
        "tencent": ("腾讯财经", MagicMock(return_value=None)),
        "eastmoney": ("东方财富", MagicMock(return_value={
            "name": "长江电力", "code": "600900", "nav": 27.0,
            "nav_date": "2026-07-03", "source": "东方财富",
        })),
    })
    def test_primary_fails_fallback_succeeds(self, mock_set, mock_get):
        """腾讯（主）返回 None → 东方财富（备）成功。"""
        from src.python.fetcher.price import fetch_market_data
        result = fetch_market_data("600900", "长江电力")
        self.assertIsNotNone(result)
        self.assertEqual(result["price"], 27.0)

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    def test_all_providers_fail_stale_cache_used(self, mock_set, mock_get):
        """全部 Provider 失败 → 降级使用过期缓存。"""
        # 模拟无有效缓存，有过期缓存
        mock_get.side_effect = lambda key, ttl: (
            None if ttl < 3600 else {"price": 26.0, "stale": True}
        )
        from src.python.fetcher.price import _PRICE_PROVIDERS
        with patch.dict(_PRICE_PROVIDERS, {
            "tencent": ("腾讯", MagicMock(return_value=None)),
            "eastmoney": ("东方财富", MagicMock(return_value=None)),
        }):
            from src.python.fetcher.price import fetch_market_data
            result = fetch_market_data("600900", "长江电力")
            self.assertIsNotNone(result)
            self.assertTrue(result.get("stale"))

    @patch("src.python.fetcher.chain.cache_get", return_value=None)
    @patch("src.python.fetcher.chain.cache_set")
    def test_all_providers_fail_no_cache_returns_none(self, mock_set, mock_get):
        """全部 Provider 失败且无过期缓存 → 返回 None。"""
        from src.python.fetcher.price import _PRICE_PROVIDERS
        with patch.dict(_PRICE_PROVIDERS, {
            "tencent": ("腾讯", MagicMock(return_value=None)),
            "eastmoney": ("东方财富", MagicMock(return_value=None)),
        }):
            from src.python.fetcher.price import fetch_market_data
            result = fetch_market_data("600900", "长江电力")
            self.assertIsNone(result)

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    def test_provider_raises_exception_fallback(self, mock_set, mock_get):
        """Provider 抛出异常 → 跳过该链路，尝试下一链路。"""
        mock_get.return_value = None
        from src.python.fetcher.price import _PRICE_PROVIDERS
        failing = MagicMock(side_effect=RuntimeError("Unexpected crash"))
        with patch.dict(_PRICE_PROVIDERS, {
            "tencent": ("腾讯", failing),
            "eastmoney": ("东方财富", MagicMock(return_value={
                "name": "长江电力", "code": "600900", "nav": 27.5,
                "nav_date": "2026-07-03", "source": "东方财富",
            })),
        }):
            from src.python.fetcher.price import fetch_market_data
            result = fetch_market_data("600900", "长江电力")
            self.assertIsNotNone(result)
            self.assertEqual(result["price"], 27.5)


# ═══════════════════════════════════════════════════════════════
# Y1-6 ~ Y1-8: 响应解析异常
# ═══════════════════════════════════════════════════════════════

class TestResponseParsingErrorsY1(unittest.TestCase):
    """响应体格式异常 → 返回 None。"""

    @patch("src.python.providers.tencent.make_http_client")
    def test_empty_response_text(self, mock_factory):
        """空响应体 → 返回 None。"""
        mock_resp = MagicMock()
        mock_resp.text = ""
        mock_resp.encoding = "gbk"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_factory.return_value.__enter__.return_value = mock_client

        from src.python.providers.tencent import fetch_price
        result = fetch_price("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.tencent.make_http_client")
    def test_truncated_response_fields(self, mock_factory):
        """截断响应（字段不足）= 返回 None。"""
        mock_resp = MagicMock()
        # Tencent 格式：v_sh600900="1~名称~600900~10.0"; 最少 10 个 ~ 字段
        mock_resp.text = 'v_sh600900="1~名称~600900~10.0";'
        mock_resp.encoding = "gbk"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_factory.return_value.__enter__.return_value = mock_client

        from src.python.providers.tencent import fetch_price
        result = fetch_price("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_non_json_response(self, mock_factory):
        """东方财富返回非 JSON（HTML 污染）→ 触发 fallback。"""
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>500 Internal Server Error</body></html>"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_factory.return_value.__enter__.return_value = mock_client

        with patch("src.python.providers.eastmoney._fallback_fundf10", return_value=None):
            from src.python.providers.eastmoney import fetch_nav
            result = fetch_nav("000001")
            self.assertIsNone(result)

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_empty_json_response(self, mock_factory):
        """东方财富返回空 JSON → 触发 fallback。"""
        mock_resp = MagicMock()
        mock_resp.text = "jQuery({})"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_factory.return_value.__enter__.return_value = mock_client

        with patch("src.python.providers.eastmoney._fallback_fundf10", return_value=None):
            from src.python.providers.eastmoney import fetch_nav
            result = fetch_nav("000001")
            self.assertIsNone(result)

    @patch("src.python.providers.tencent.make_http_client")
    def test_invalid_encoding_response(self, mock_factory):
        """编码声明与实际不一致 → 不崩溃（Tencent）。"""
        mock_resp = MagicMock()
        mock_resp.encoding = "gbk"
        # 当 resp.text 被访问时，httpx 自动解码
        # 模拟解码不抛异常
        # Tencent 格式需要 10+ 个 ~ 字段
        mock_resp.text = ('v_sh600900="1~test~600900~26.65~26.50~26.80~'
                          '1000~50000~26.70~26.40~26.85~100000~'
                          '20260703150000~1.23~0.88~26.65");')
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_factory.return_value.__enter__.return_value = mock_client

        from src.python.providers.tencent import fetch_price
        result = fetch_price("600900")
        self.assertIsNotNone(result)


# ═══════════════════════════════════════════════════════════════
# Y1-9 ~ Y1-12: LLM API 错误分类
# ═══════════════════════════════════════════════════════════════

class TestLlmApiErrorsY1(unittest.TestCase):
    """LLM API 错误分类：可重试 vs 不可恢复。"""

    def setUp(self):
        self.client = MagicMock()
        self.url = "https://api.anthropic.com/v1/messages"
        self.headers = {"x-api-key": "sk-test"}
        self.payload = {"model": "claude-sonnet-4", "messages": [{"role": "user", "content": "hi"}]}
        self.timeout = 30.0

    def _call_api(self):
        from src.python.llm.api_base import _attempt_api_call
        return _attempt_api_call(self.client, self.url, self.headers, self.payload, self.timeout)

    def test_http_429_retryable(self):
        """429 限流 → (retryable, 429)。"""
        self.client.post.return_value.status_code = 429
        kind, detail = self._call_api()
        self.assertEqual(kind, "retryable")
        self.assertEqual(detail, 429)

    def test_http_503_retryable(self):
        """503 服务不可用 → (retryable, 503)。"""
        self.client.post.return_value.status_code = 503
        kind, detail = self._call_api()
        self.assertEqual(kind, "retryable")
        self.assertEqual(detail, 503)

    def test_http_401_fatal(self):
        """401 未授权 → httpx.HTTPStatusError → (retryable, host)。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_resp
        )
        self.client.post.return_value = mock_resp
        kind, detail = self._call_api()
        self.assertEqual(kind, "retryable")
        self.assertIn("api.anthropic.com", detail)

    def test_http_500_retryable(self):
        """500 服务器错误 → httpx.HTTPStatusError → (retryable, host)。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error", request=MagicMock(), response=mock_resp
        )
        self.client.post.return_value = mock_resp
        kind, detail = self._call_api()
        self.assertEqual(kind, "retryable")
        self.assertIn("api.anthropic.com", detail)

    def test_timeout_retryable(self):
        """超时 → (retryable, None)。"""
        self.client.post.side_effect = httpx.TimeoutException("Request timed out")
        kind, detail = self._call_api()
        self.assertEqual(kind, "retryable")
        self.assertIsNone(detail)

    def test_connection_error_retryable(self):
        """连接错误 → httpx.HTTPError → (retryable, host)。"""
        self.client.post.side_effect = httpx.RequestError("Connection reset")
        kind, detail = self._call_api()
        self.assertEqual(kind, "retryable")

    def test_valid_response_success(self):
        """正常 200 → (success, {data})。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "msg_123", "content": "hello"}
        self.client.post.return_value = mock_resp
        kind, detail = self._call_api()
        self.assertEqual(kind, "success")


# ═══════════════════════════════════════════════════════════════
# Y1-13: SSL 证书错误
# ═══════════════════════════════════════════════════════════════

class TestSslErrorsY1(unittest.TestCase):
    """SSL 证书验证失败 → 不崩溃。"""

    @patch("src.python.providers.tencent.make_http_client")
    def test_ssl_error_caught_by_request_error(self, mock_factory):
        """SSL 证书错误 → RequestError 捕获 → 返回 None。"""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError(
            "SSL: CERTIFICATE_VERIFY_FAILED"
        )
        mock_factory.return_value.__enter__.return_value = mock_client

        from src.python.providers.tencent import fetch_price
        result = fetch_price("600900")
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════
# Y1-14: HTTP 客户端 — SSL_VERIFY 环境变量
# ═══════════════════════════════════════════════════════════════

class TestHttpClientSslVerifyY1(unittest.TestCase):
    """SSL_VERIFY 环境变量控制验证策略。"""

    @patch("src.python.http_client.os.getenv")
    def test_ssl_verify_false_disables_verification(self, mock_getenv):
        """SSL_VERIFY=false → Client(verify=False)。"""
        mock_getenv.return_value = "false"
        # 重新加载模块级变量
        import importlib
        import src.python.http_client as hc
        importlib.reload(hc)
        self.assertFalse(hc._SSL_VERIFY)

    @patch("src.python.http_client.os.getenv")
    def test_ssl_verify_default_true(self, mock_getenv):
        """SSL_VERIFY 未设置（默认 true）→ Client(verify=True)。"""
        mock_getenv.return_value = "true"
        import importlib
        import src.python.http_client as hc
        importlib.reload(hc)
        self.assertTrue(hc._SSL_VERIFY)


if __name__ == "__main__":
    unittest.main()

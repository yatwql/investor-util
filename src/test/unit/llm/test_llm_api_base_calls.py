"""api_base._attempt_api_call 调用分类单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import httpx
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


class TestAttemptApiCall(unittest.TestCase):
    """_attempt_api_call 的返回分类：可重试 vs 不可恢复。"""

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

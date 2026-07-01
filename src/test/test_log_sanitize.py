"""日志脱敏验证测试。

测试目标：
  - 验证 API Key 等敏感信息不在 app.log 中明文出现
  - 验证 _sanitize_endpoint 正确脱敏 URL
  - 验证日志中不包含完整的 api_key 值

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_log_sanitize -v
"""

from __future__ import annotations

import io
import logging
import unittest
from unittest.mock import MagicMock, patch

from src.python.llm.api import _sanitize_endpoint


class TestSanitizeEndpoint(unittest.TestCase):
    """_sanitize_endpoint 脱敏辅助函数测试。"""

    def test_normal_url_returns_host(self):
        """https://api.anthropic.com/v1/messages → api.anthropic.com。"""
        self.assertEqual(
            _sanitize_endpoint("https://api.anthropic.com/v1/messages"),
            "api.anthropic.com"
        )

    def test_empty_url(self):
        """空字符串 → unknown。"""
        self.assertEqual(_sanitize_endpoint(""), "unknown")

    def test_invalid_url(self):
        """非 URL 字符串 → unknown。"""
        self.assertEqual(_sanitize_endpoint("not-a-url"), "unknown")

    def test_none_value(self):
        """None → unknown。"""
        self.assertEqual(_sanitize_endpoint(None), "unknown")

    def test_url_with_port(self):
        """含端口号的 URL → 端口保留。"""
        self.assertEqual(
            _sanitize_endpoint("https://api.test.com:8080/v1/chat"),
            "api.test.com:8080"
        )

    def test_http_url(self):
        """http URL → 域名部分。"""
        self.assertEqual(
            _sanitize_endpoint("http://localhost:11434/v1"),
            "localhost:11434"
        )


class TestApiKeyNotInLog(unittest.TestCase):
    """验证 api_key 不直接出现在日志中。"""

    def setUp(self):
        self.log_capture = io.StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        self.handler.setLevel(logging.DEBUG)
        self.orig_handlers = list(logging.getLogger("invest").handlers)
        logging.getLogger("invest").handlers.clear()
        logging.getLogger("invest").addHandler(self.handler)
        logging.getLogger("invest").setLevel(logging.DEBUG)

    def tearDown(self):
        logging.getLogger("invest").handlers.clear()
        for h in self.orig_handlers:
            logging.getLogger("invest").addHandler(h)

    def test_api_key_not_logged_in_call_llm(self):
        """_call_llm 的日志不包含 api_key 明文。"""
        from src.python.llm.api import _call_llm

        secret_key = "sk-test-secret-key-12345"
        config = {"provider": "claude", "api_key": secret_key}

        with patch("src.python.llm.api._call_single_provider") as mock_call:
            mock_call.return_value = (None, None)
            _call_llm("sys", "user", config)

        log_text = self.log_capture.getvalue()
        # api_key 明文不应出现在日志中
        self.assertNotIn(secret_key, log_text,
                         "API Key 明文不应出现在日志中")

    def test_api_key_not_logged_on_failure(self):
        """API 调用失败日志不包含 api_key。"""
        from src.python.llm.api import _call_llm_with_retry as _retry

        secret_key = "sk-another-secret-99999"
        with patch("src.python.llm.api._attempt_api_call") as mock_attempt:
            mock_attempt.return_value = ("retryable", 429)
            _retry(
                label="Claude",
                client=MagicMock(),
                url="https://api.test.com/v1",
                headers={"x-api-key": secret_key},
                payload={}, timeout=30, max_retries=1,
                max_tokens=1000, config_field="max_tokens",
                extract_fn=lambda d: "", check_truncation_fn=lambda d, mt: False,
                provider="claude",
            )

        log_text = self.log_capture.getvalue()
        self.assertNotIn(secret_key, log_text,
                         "日志不应包含 API Key")

    def test_header_api_key_not_in_log(self):
        """HTTP 请求头的 API Key 不写入日志。"""
        from src.python.llm.api import _call_claude

        secret_key = "sk-header-key-88888"
        with patch("src.python.llm.api._call_llm_with_retry") as mock_retry:
            mock_retry.return_value = ("result", {"input_tokens": 10})
            _call_claude(
                system="sys", user="user", api_key=secret_key,
                model="claude-sonnet-4", endpoint="",
                max_tokens=100, timeout=30,
            )

        log_text = self.log_capture.getvalue()
        self.assertNotIn(secret_key, log_text,
                         "请求头中的 API Key 不应出现在日志中")


class TestSanitizeEndpointInLogs(unittest.TestCase):
    """验证日志中使用脱敏后的 endpoint（只含域名）。"""

    def setUp(self):
        self.log_capture = io.StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        self.handler.setLevel(logging.DEBUG)
        self.orig_handlers = list(logging.getLogger("invest").handlers)
        logging.getLogger("invest").handlers.clear()
        logging.getLogger("invest").addHandler(self.handler)
        logging.getLogger("invest").setLevel(logging.DEBUG)

    def tearDown(self):
        logging.getLogger("invest").handlers.clear()
        for h in self.orig_handlers:
            logging.getLogger("invest").addHandler(h)

    def test_circuit_breaker_logs_sanitized_endpoint(self):
        """熔断器日志使用域名而非完整 URL。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _CIRCUIT_BREAKER_THRESHOLD,
        )

        # 需要连续失败 _CIRCUIT_BREAKER_THRESHOLD(3) 次才触发日志
        for _ in range(_CIRCUIT_BREAKER_THRESHOLD):
            _cb_record_failure("https://api.secret-endpoint.com/v1/chat")
        log_text = self.log_capture.getvalue()
        self.assertIn("api.secret-endpoint.com", log_text)
        self.assertNotIn("/v1/chat", log_text)

    def test_config_api_key_not_in_log(self):
        """config 模块不将 api_key 写入日志。"""
        import logging
        cfg_logger = logging.getLogger("invest")
        cfg_logger.handlers.clear()
        cfg_logger.addHandler(self.handler)
        cfg_logger.setLevel(logging.DEBUG)

        from src.python.config import get_llm_config
        import tempfile, json, os

        # 创建临时 llm_key.json 含 api_key
        tmp = tempfile.TemporaryDirectory()
        key_path = os.path.join(tmp.name, "llm_key.json")
        secret = "sk-config-secret-666"
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump({"provider": "claude", "api_key": secret}, f)

        with patch("src.python.config.get_llm_key_path", return_value=key_path):
            with patch("src.python.config.get_llm_settings_path",
                       return_value=os.path.join(tmp.name, "llm_settings.json")):
                with patch("src.python.config.os.path.exists") as mock_exists:
                    mock_exists.return_value = True
                    get_llm_config()

        log_text = self.log_capture.getvalue()
        self.assertNotIn(secret, log_text,
                         "API Key 不应出现在 config 模块的日志中")
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

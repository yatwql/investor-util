"""测试：LLM API 基础模块 — api_base.py

覆盖 api_base.py 的基础设施函数（常量 + 检测 + 内容提取 + 重试骨架 + 失败追踪）。
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import httpx
import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
]


class TestExtractContent(unittest.TestCase):
    """_extract_content — 从 API 响应中提取文本内容。"""

    def test_normal_content_list(self) -> None:
        """正常 content 列表 → 返回拼接文本。"""
        from src.python.llm.api_base import _extract_content

        data = {"content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": "World"}]}
        result = _extract_content(data)
        self.assertEqual(result, "Hello\nWorld")

    def test_content_is_string(self) -> None:
        """content 为字符串 → 直接返回。"""
        from src.python.llm.api_base import _extract_content

        data = {"content": "plain string response"}
        result = _extract_content(data)
        self.assertEqual(result, "plain string response")

    def test_thinking_block_ignored(self) -> None:
        """content 含 thinking/redacted_thinking block → 忽略 non-text block。"""
        from src.python.llm.api_base import _extract_content

        data = {
            "content": [
                {"type": "thinking", "thinking": "internal thoughts"},
                {"type": "text", "text": "final answer"},
            ]
        }
        result = _extract_content(data)
        self.assertEqual(result, "final answer")

    def test_empty_content_list(self) -> None:
        """content 为空列表 → 返回空字符串。"""
        from src.python.llm.api_base import _extract_content

        data = {"content": []}
        result = _extract_content(data)
        self.assertEqual(result, "")

    def test_error_in_response(self) -> None:
        """data 含 error → 返回 None。"""
        from src.python.llm.api_base import _extract_content

        data = {"error": {"type": "authentication_error", "message": "invalid api key"}}
        result = _extract_content(data)
        self.assertIsNone(result)

    def test_data_is_none(self) -> None:
        """data 为 None → 返回 None。"""
        from src.python.llm.api_base import _extract_content

        result = _extract_content(None)
        self.assertIsNone(result)

    def test_only_thinking_blocks(self) -> None:
        """仅有 thinking block 无 text → 返回空字符串。"""
        from src.python.llm.api_base import _extract_content

        data = {"content": [{"type": "thinking", "thinking": "thinking..."}, {"type": "redacted_thinking", "data": "..."}]}
        result = _extract_content(data)
        self.assertEqual(result, "")


class TestCheckClaudeTruncation(unittest.TestCase):
    """_check_claude_truncation — Claude 截断检测。"""

    def test_max_tokens_truncated(self) -> None:
        """stop_reason='max_tokens' → True。"""
        from src.python.llm.api_base import _check_claude_truncation

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR"):
            result = _check_claude_truncation(data, 1000, "TestLabel")
        self.assertTrue(result)

    def test_end_turn_not_truncated(self) -> None:
        """stop_reason='end_turn' → False。"""
        from src.python.llm.api_base import _check_claude_truncation

        data = {"stop_reason": "end_turn"}
        result = _check_claude_truncation(data, 1000, "TestLabel")
        self.assertFalse(result)

    def test_empty_data_no_truncation(self) -> None:
        """异常 data 格式 → False。"""
        from src.python.llm.api_base import _check_claude_truncation

        result = _check_claude_truncation({}, 1000, "TestLabel")
        self.assertFalse(result)

    def test_missing_stop_reason(self) -> None:
        """data 无 stop_reason → False。"""
        from src.python.llm.api_base import _check_claude_truncation

        data = {"usage": {"output_tokens": 100}}
        result = _check_claude_truncation(data, 1000, "TestLabel")
        self.assertFalse(result)


class TestCheckOpenaiTruncation(unittest.TestCase):
    """_check_openai_truncation — OpenAI 截断检测。"""

    def test_length_finish_reason(self) -> None:
        """finish_reason='length' → True。"""
        from src.python.llm.api_base import _check_openai_truncation

        data = {"choices": [{"finish_reason": "length"}], "usage": {"completion_tokens": 500}}
        with self.assertLogs("invest", level="ERROR"):
            result = _check_openai_truncation(data, 1000, "OpenAI")
        self.assertTrue(result)

    def test_stop_finish_reason(self) -> None:
        """finish_reason='stop' → False。"""
        from src.python.llm.api_base import _check_openai_truncation

        data = {"choices": [{"finish_reason": "stop"}]}
        result = _check_openai_truncation(data, 1000, "OpenAI")
        self.assertFalse(result)

    def test_malformed_choices(self) -> None:
        """choices 索引异常 → False。"""
        from src.python.llm.api_base import _check_openai_truncation

        result = _check_openai_truncation({"choices": []}, 1000, "OpenAI")
        self.assertFalse(result)

    def test_missing_choices(self) -> None:
        """data 无 choices → False。"""
        from src.python.llm.api_base import _check_openai_truncation

        result = _check_openai_truncation({}, 1000, "OpenAI")
        self.assertFalse(result)


class TestSupportsExtendedThinking(unittest.TestCase):
    """_supports_extended_thinking — Thinking 兼容性检查。"""

    def test_supported_model(self) -> None:
        """支持的前缀 → True。"""
        from src.python.llm.api_base import _supports_extended_thinking

        self.assertTrue(_supports_extended_thinking("claude-sonnet-4-20250514"))
        self.assertTrue(_supports_extended_thinking("claude-opus-4-20250514"))
        self.assertTrue(_supports_extended_thinking("deepseek-v4-1234"))
        self.assertTrue(_supports_extended_thinking("deepseek-chat"))

    def test_unsupported_model(self) -> None:
        """不支持的前缀 → False。"""
        from src.python.llm.api_base import _supports_extended_thinking

        self.assertFalse(_supports_extended_thinking("claude-sonnet-3-5"))
        self.assertFalse(_supports_extended_thinking("gpt-4o"))

    def test_empty_string(self) -> None:
        """空字符串 → False。"""
        from src.python.llm.api_base import _supports_extended_thinking

        self.assertFalse(_supports_extended_thinking(""))


class TestIsEffortModel(unittest.TestCase):
    """_is_effort_model — effort 模型判断。"""

    def test_deepseek_models(self) -> None:
        """DeepSeek 前缀 → True。"""
        from src.python.llm.api_base import _is_effort_model

        self.assertTrue(_is_effort_model("deepseek-v4-20250301"))
        self.assertTrue(_is_effort_model("deepseek-chat"))

    def test_claude_models(self) -> None:
        """Claude 前缀 → False。"""
        from src.python.llm.api_base import _is_effort_model

        self.assertFalse(_is_effort_model("claude-sonnet-4-20250514"))
        self.assertFalse(_is_effort_model("claude-opus-4"))


class TestSanitizeEndpoint(unittest.TestCase):
    """_sanitize_endpoint — URL 域名提取。"""

    def test_normal_url(self) -> None:
        """标准 URL → 返回域名。"""
        from src.python.llm.api_base import _sanitize_endpoint

        self.assertEqual(_sanitize_endpoint("https://api.anthropic.com/v1/messages"), "api.anthropic.com")

    def test_url_with_port(self) -> None:
        """带端口的 URL → 返回 域名:端口。"""
        from src.python.llm.api_base import _sanitize_endpoint

        self.assertEqual(_sanitize_endpoint("https://localhost:8080/api"), "localhost:8080")

    def test_empty_endpoint(self) -> None:
        """空字符串 → 'unknown'。"""
        from src.python.llm.api_base import _sanitize_endpoint

        self.assertEqual(_sanitize_endpoint(""), "unknown")

    def test_invalid_url(self) -> None:
        """非 URL 格式 → 'unknown'。"""
        from src.python.llm.api_base import _sanitize_endpoint

        self.assertEqual(_sanitize_endpoint("not-a-url"), "unknown")


class TestGetRetryMax(unittest.TestCase):
    """_get_retry_max — 重试次数获取。"""

    def test_normal_config(self) -> None:
        """正常配置 → 返回配置值。"""
        from src.python.llm.api_base import _get_retry_max

        self.assertEqual(_get_retry_max({"max_retries": 3}), 3)

    def test_missing_key(self) -> None:
        """缺失 key → 兜底 2。"""
        from src.python.llm.api_base import _get_retry_max

        self.assertEqual(_get_retry_max({}), 2)

    def test_invalid_value(self) -> None:
        """非法值 → 兜底 2。"""
        from src.python.llm.api_base import _get_retry_max

        self.assertEqual(_get_retry_max({"max_retries": "abc"}), 2)

    def test_zero_retries(self) -> None:
        """max_retries=0 → 0。"""
        from src.python.llm.api_base import _get_retry_max

        self.assertEqual(_get_retry_max({"max_retries": 0}), 0)

    def test_negative_value(self) -> None:
        """负数 → 返回 0（不重试）。"""
        from src.python.llm.api_base import _get_retry_max

        self.assertEqual(_get_retry_max({"max_retries": -1}), 0)


class TestAttemptApiCall(unittest.TestCase):
    """_attempt_api_call — 单次 HTTP 调用。"""

    def setUp(self) -> None:
        from src.python.llm.api_base import _attempt_api_call
        self._attempt_api_call = _attempt_api_call

    def test_success(self) -> None:
        """200 OK → ('success', data)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": "hello"}
        mock_client.post.return_value = mock_response

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "success")
        self.assertEqual(info, {"content": "hello"})

    def test_rate_limit_429(self) -> None:
        """429 → ('retryable', 429)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "retryable")
        self.assertEqual(info, 429)

    def test_service_unavailable_503(self) -> None:
        """503 → ('retryable', 503)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_client.post.return_value = mock_response

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "retryable")
        self.assertEqual(info, 503)

    def test_timeout_exception(self) -> None:
        """httpx.TimeoutException → ('retryable', None)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.TimeoutException("timeout")

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "retryable")
        self.assertIsNone(info)

    def test_http_error(self) -> None:
        """httpx.HTTPError → ('retryable', host)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.HTTPError("connection error")

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com/path", {}, {}, 30.0)
        self.assertEqual(kind, "retryable")
        self.assertEqual(info, "api.test.com")

    def test_json_decode_error(self) -> None:
        """JSON 解析失败 → ('fatal', errmsg)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.post.return_value = mock_response

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "fatal")
        self.assertIsInstance(info, str)


class TestIsRetryAvailable(unittest.TestCase):
    """_is_retry_available — 重试可用性判断。"""

    def test_attempt_available(self) -> None:
        """attempt < max_retries → True。"""
        from src.python.llm.api_base import _is_retry_available

        result = _is_retry_available("Test", 0, 2, "超时", "https://api.test.com")
        self.assertTrue(result)

    def test_attempt_exhausted(self) -> None:
        """attempt >= max_retries → False。"""
        from src.python.llm.api_base import _is_retry_available

        result = _is_retry_available("Test", 2, 2, "超时", "https://api.test.com")
        self.assertFalse(result)


class TestCallLlmWithRetry(unittest.TestCase):
    """call_llm_with_retry — 通用重试骨架。"""

    def setUp(self) -> None:
        # 清理失败状态
        from src.python.llm.api_base import clear_last_llm_failure
        clear_last_llm_failure()

    @patch("src.python.llm.api_base._cb_is_open", return_value=False)
    @patch("src.python.llm.api_base._cb_record_success")
    @patch("src.python.llm.api_base._log_token_usage")  # avoid formatting magic mock
    def test_success_first_try(self, mock_log_usage, mock_record_success, mock_cb_open) -> None:
        """首次成功 → (content, usage)。"""
        from src.python.llm.api_base import call_llm_with_retry

        mock_client = MagicMock()

        result, usage = call_llm_with_retry(
            "Test", mock_client, "https://api.test.com", {}, {},
            30.0, 2, 1000, "max_tokens",
            extract_fn=lambda d: (d or {}).get("content"),
            check_truncation_fn=lambda d, mt: False,
            provider="claude", model_name="test-model",
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(usage)

    @patch("src.python.llm.api_base._cb_is_open", return_value=False)
    @patch("src.python.llm.api_base._cb_record_failure")
    def test_circuit_breaker_open(self, mock_record_failure, mock_cb_open) -> None:
        """熔断打开 → (None, None)。"""
        mock_cb_open.return_value = True  # override: circuit breaker open
        from src.python.llm.api_base import call_llm_with_retry

        mock_client = MagicMock()

        result, usage = call_llm_with_retry(
            "Test", mock_client, "https://api.test.com", {}, {},
            30.0, 2, 1000, "max_tokens",
            extract_fn=lambda d: "content",
            check_truncation_fn=lambda d, mt: False,
            provider="claude",
        )
        self.assertIsNone(result)
        self.assertIsNone(usage)

    @patch("src.python.llm.api_base._cb_is_open", return_value=False)
    @patch("src.python.llm.api_base._attempt_api_call")
    @patch("src.python.llm.api_base._cb_record_success")
    def test_retry_then_succeed(self, mock_record_success, mock_attempt, mock_cb_open) -> None:
        """失败重试后成功 → (content, usage)。"""
        from src.python.llm.api_base import call_llm_with_retry
        from src.python.llm.api_base import _is_retry_available

        # 第一次 retryable, 第二次 success
        mock_attempt.side_effect = [
            ("retryable", 429),
            ("success", {"content": "hello", "usage": {"input_tokens": 10, "output_tokens": 20}}),
        ]

        # Need a client for the call but attempt is patched, so client isn't actually used
        mock_client = MagicMock()

        with patch("src.python.llm.api_base._is_retry_available", return_value=True):
            result, usage = call_llm_with_retry(
                "Test", mock_client, "https://api.test.com", {}, {},
                30.0, 2, 1000, "max_tokens",
                extract_fn=lambda d: d.get("content"),
                check_truncation_fn=lambda d, mt: False,
                provider="claude", model_name="test-model",
            )
        self.assertEqual(result, "hello")
        self.assertEqual(usage["input_tokens"], 10)

    @patch("src.python.llm.api_base._cb_is_open", return_value=False)
    @patch("src.python.llm.api_base._attempt_api_call")
    def test_all_retries_exhausted(self, mock_attempt, mock_cb_open) -> None:
        """全部重试耗尽 → (None, None)。"""
        from src.python.llm.api_base import call_llm_with_retry

        # Always retryable
        mock_attempt.return_value = ("retryable", 429)

        mock_client = MagicMock()

        # Make sure max_retries is 0 so only 1 attempt
        from src.python.llm.api_base import _is_retry_available
        with patch("src.python.llm.api_base._is_retry_available", return_value=False):
            result, usage = call_llm_with_retry(
                "Test", mock_client, "https://api.test.com", {}, {},
                30.0, 0, 1000, "max_tokens",
                extract_fn=lambda d: None,
                check_truncation_fn=lambda d, mt: False,
                provider="claude",
            )
        self.assertIsNone(result)
        self.assertIsNone(usage)

    @patch("src.python.llm.api_base._cb_is_open", return_value=False)
    @patch("src.python.llm.api_base._attempt_api_call")
    def test_response_parse_error(self, mock_attempt, mock_cb_open) -> None:
        """响应解析失败 → (None, None)。"""
        from src.python.llm.api_base import call_llm_with_retry

        mock_attempt.return_value = ("fatal", "parse error")

        mock_client = MagicMock()
        result, usage = call_llm_with_retry(
            "Test", mock_client, "https://api.test.com", {}, {},
            30.0, 2, 1000, "max_tokens",
            extract_fn=lambda d: None,
            check_truncation_fn=lambda d, mt: False,
            provider="claude",
        )
        self.assertIsNone(result)
        self.assertIsNone(usage)


class TestLastLlmFailureReason(unittest.TestCase):
    """_last_llm_failure_reason — 失败追踪。"""

    def setUp(self) -> None:
        from src.python.llm.api_base import clear_last_llm_failure
        clear_last_llm_failure()

    def test_normal_state_is_none(self) -> None:
        """初始状态为 None。"""
        from src.python.llm.api_base import _get_last_llm_failure

        self.assertIsNone(_get_last_llm_failure())

    def test_clear_resets_to_none(self) -> None:
        """清除后为 None。"""
        from src.python.llm.api_base import clear_last_llm_failure, _get_last_llm_failure

        clear_last_llm_failure()
        self.assertIsNone(_get_last_llm_failure())

    def test_get_set_roundtrip(self) -> None:
        """设置后读取正确（通过模块命名空间）。"""
        import src.python.llm.api_base
        from src.python.llm.api_base import (
            clear_last_llm_failure,
            _get_last_llm_failure,
        )

        src.python.llm.api_base._last_llm_failure_reason = "test_reason"
        self.assertEqual(_get_last_llm_failure(), "test_reason")
        clear_last_llm_failure()
        self.assertIsNone(_get_last_llm_failure())


class TestCacheLineModelTpl(unittest.TestCase):
    """_cache_line_model_tpl — 缓存行模板。"""

    def test_model_name_in_html(self) -> None:
        """模型名嵌入 HTML。"""
        from src.python.llm.api_base import _cache_line_model_tpl

        html = _cache_line_model_tpl("claude-sonnet-4")
        self.assertIn("claude-sonnet-4", html)
        self.assertIn("LLM缓存", html)


class TestExtractModelFromCached(unittest.TestCase):
    """_extract_model_from_cached — 从缓存 HTML 提取模型名。"""

    def test_model_line_found(self) -> None:
        """含模型名行 → 提取成功。"""
        from src.python.llm.api_base import _extract_model_from_cached

        html = '<p>模型：claude-sonnet-4 | 本次使用LLM缓存</p>'
        model = _extract_model_from_cached(html)
        self.assertEqual(model, "claude-sonnet-4")

    def test_model_line_not_found(self) -> None:
        """无模型名 → 空字符串。"""
        from src.python.llm.api_base import _extract_model_from_cached

        html = "<p>纯文本内容</p>"
        model = _extract_model_from_cached(html)
        self.assertEqual(model, "")


class TestTruncationWarning(unittest.TestCase):
    """_truncation_warning — 截断警告。"""

    def test_warning_contains_marker(self) -> None:
        """警告含截断标记。"""
        from src.python.llm.api_base import TRUNCATION_MARKER, _truncation_warning

        warning = _truncation_warning("max_tokens")
        self.assertIn(TRUNCATION_MARKER, warning)
        self.assertIn("max_tokens", warning)


class TestLogTokenUsage(unittest.TestCase):
    """_log_token_usage — Token 用量日志。"""

    def test_claude_usage_logged(self) -> None:
        """Claude 格式用量 → 打印日志。"""
        from src.python.llm.api_base import _log_token_usage

        usage = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 10}
        # Should not raise
        _log_token_usage("claude", usage, "test_label", model_name="test-model")

    def test_openai_usage_logged(self) -> None:
        """OpenAI 格式用量 → 打印日志。"""
        from src.python.llm.api_base import _log_token_usage

        usage = {"prompt_tokens": 200, "completion_tokens": 100}
        _log_token_usage("openai", usage, "test_label", model_name="test-model")

    def test_none_usage_ignored(self) -> None:
        """usage 为 None → 跳过。"""
        from src.python.llm.api_base import _log_token_usage

        _log_token_usage("claude", None, "test_label")  # Should not raise

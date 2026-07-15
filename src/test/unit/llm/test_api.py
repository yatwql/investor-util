"""LLM API 调用模块单元测试 — 重试骨架、Provider 路由、回退、安抚重试。

测试目标：
  - call_llm_with_retry — 熔断/429/503/超时/网络错误/截断/内容过滤
  - _call_llm — 主/回退链式调度 + 空内容安抚重试
  - call_single_provider — claude/openai/unknown 路由
  - 辅助函数：_get_retry_max/_sanitize_endpoint/_extract_model_from_cached/_truncation_warning

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_api.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import httpx

from src.python.llm.api_base import (
    TRUNCATION_MARKER,
    call_llm_with_retry,
    _extract_model_from_cached,
    _get_retry_max,
    _sanitize_endpoint,
    _truncation_warning,
)
from src.python.llm.api import (
    call_llm,
    call_single_provider,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]



# ═══════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════


def _make_mock_response(status_code: int = 200, json_data: dict | None = None,
                        usage: dict | None = None) -> MagicMock:
    """创建模拟 httpx.Response。

    Args:
        status_code: HTTP 状态码
        json_data: JSON 响应体
        usage: 自动注入 usage 字段到 json_data
    """
    if json_data is None:
        json_data = {"content": [{"type": "text", "text": "回复"}]}
    if usage is not None:
        json_data["usage"] = usage

    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data

    # HTTPError 状态码 → raise_for_status() 抛异常
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None

    return resp


def _default_extract(data: dict) -> str:
    return data.get("content", [{}])[0].get("text", "")


def _no_truncation(data: dict, mt: int) -> bool:
    return False


# ═══════════════════════════════════════════════════════════
#  _get_retry_max
# ═══════════════════════════════════════════════════════════


class TestGetRetryMax(unittest.TestCase):
    """_get_retry_max 边界测试。"""

    def test_default(self) -> None:
        self.assertEqual(_get_retry_max({}), 2)

    def test_custom_value(self) -> None:
        self.assertEqual(_get_retry_max({"max_retries": 5}), 5)

    def test_zero(self) -> None:
        self.assertEqual(_get_retry_max({"max_retries": 0}), 0)

    def test_negative_clamp_to_zero(self) -> None:
        self.assertEqual(_get_retry_max({"max_retries": -1}), 0)

    def test_none_config(self) -> None:
        self.assertEqual(_get_retry_max({"max_retries": None}), 2)

    def test_string_value(self) -> None:
        self.assertEqual(_get_retry_max({"max_retries": "abc"}), 2)


# ═══════════════════════════════════════════════════════════
#  _sanitize_endpoint
# ═══════════════════════════════════════════════════════════


class TestSanitizeEndpoint(unittest.TestCase):
    """_sanitize_endpoint 边界测试。"""

    def test_normal_url(self) -> None:
        self.assertEqual(
            _sanitize_endpoint("https://api.anthropic.com/v1/messages"),
            "api.anthropic.com",
        )

    def test_empty(self) -> None:
        self.assertEqual(_sanitize_endpoint(""), "unknown")

    def test_none(self) -> None:
        self.assertEqual(_sanitize_endpoint(None), "unknown")

    def test_no_slashes(self) -> None:
        self.assertEqual(_sanitize_endpoint("invalid"), "unknown")

    def test_http_local(self) -> None:
        self.assertEqual(_sanitize_endpoint("http://localhost:8080/chat"), "localhost:8080")


# ═══════════════════════════════════════════════════════════
#  _truncation_warning / _extract_model_from_cached
# ═══════════════════════════════════════════════════════════


class TestTruncationWarning(unittest.TestCase):
    """_truncation_warning 格式化。"""

    def test_default_field(self) -> None:
        result = _truncation_warning("max_tokens")
        self.assertIn(TRUNCATION_MARKER, result)
        self.assertIn("max_tokens", result)

    def test_custom_field(self) -> None:
        result = _truncation_warning("max_tokens_expert_review")
        self.assertIn("max_tokens_expert_review", result)


class TestExtractModelFromCached(unittest.TestCase):
    """_extract_model_from_cached 正则提取。"""

    def test_extract_model(self) -> None:
        html = '<p style="color:#888;font-size:12px">模型：claude-sonnet-4-6 | Token 用量</p>'
        self.assertEqual(_extract_model_from_cached(html), "claude-sonnet-4-6")

    def test_chinese_colon_with_pipe(self) -> None:
        """中文冒号 + | 分隔的 model line。"""
        html = '<p style="color:#888;font-size:12px">模型：deepseek-v4-flash | Token 用量</p>'
        self.assertEqual(_extract_model_from_cached(html), "deepseek-v4-flash")

    def test_no_model(self) -> None:
        self.assertEqual(_extract_model_from_cached("<p>内容</p>"), "")

    def test_empty(self) -> None:
        self.assertEqual(_extract_model_from_cached(""), "")


# ═══════════════════════════════════════════════════════════
#  call_llm_with_retry — 熔断器
# ═══════════════════════════════════════════════════════════


class TestCallLlmWithRetryCircuitBreaker(unittest.TestCase):
    """熔断器开启 → 跳过。"""

    def test_circuit_open_skips(self) -> None:
        with patch("src.python.llm.api_base._cb_is_open", return_value=True):
            result, usage = call_llm_with_retry(
                "Test", MagicMock(), "https://api.test.com/v1",
                {}, {"model": "test"}, 60, 2, 1000, "max_tokens",
                _default_extract, _no_truncation, "claude", "test-model",
            )
        self.assertIsNone(result)
        self.assertIsNone(usage)


# ═══════════════════════════════════════════════════════════
#  call_llm_with_retry — HTTP 错误码重试
# ═══════════════════════════════════════════════════════════


class TestCallLlmWithRetryHttpErrors(unittest.TestCase):
    """HTTP 错误码重试 + 最终失败。"""

    def setUp(self) -> None:
        self.client = MagicMock(spec=httpx.Client)
        self.base_kw = dict(
            label="Test", client=self.client, url="https://api.test.com/v1",
            headers={}, payload={"model": "test"}, timeout=60, max_retries=2,
            max_tokens=1000, config_field="max_tokens",
            extract_fn=_default_extract, check_truncation_fn=_no_truncation,
            provider="claude", model_name="test-model",
        )
        self.cb_patcher = patch("src.python.llm.api_base._cb_is_open", return_value=False)
        self.cb_patcher.start()

    def tearDown(self) -> None:
        self.cb_patcher.stop()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("src.python.llm.api_base._log_token_usage")
    @patch("src.python.llm.api_base.track_session_usage")
    def test_success_first_try(self, mock_track: MagicMock, mock_log: MagicMock,
                                mock_success: MagicMock) -> None:
        """首次调用成功。"""
        usage = {"input_tokens": 10, "output_tokens": 5}
        self.client.post.return_value = _make_mock_response(
            200, {"content": [{"type": "text", "text": "OK"}]}, usage=usage,
        )
        result, u = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(u["input_tokens"], 10)
        mock_success.assert_called_once()
        mock_log.assert_called_once()
        mock_track.assert_called_once()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_429_then_success(self, mock_sleep: MagicMock, mock_success: MagicMock) -> None:
        """429 → 重试 → 成功。"""
        succeed = _make_mock_response(200, {"content": [{"type": "text", "text": "OK"}]})
        self.client.post.side_effect = [_make_mock_response(429), succeed]
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(self.client.post.call_count, 2)
        mock_success.assert_called_once()

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_429_all_fail(self, mock_sleep: MagicMock, mock_failure: MagicMock) -> None:
        """429 全部重试失败 → (None, None)。"""
        self.client.post.return_value = _make_mock_response(429)
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 3)
        mock_failure.assert_called_once()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_503_then_success(self, mock_sleep: MagicMock, mock_success: MagicMock) -> None:
        """503 → 重试 → 成功。"""
        succeed = _make_mock_response(200, {"content": [{"type": "text", "text": "OK"}]})
        self.client.post.side_effect = [_make_mock_response(503), succeed]
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(self.client.post.call_count, 2)

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_timeout_then_success(self, mock_sleep: MagicMock, mock_success: MagicMock) -> None:
        """超时 → 重试 → 成功。"""
        succeed = _make_mock_response(200, {"content": [{"type": "text", "text": "OK"}]})
        self.client.post.side_effect = [httpx.TimeoutException("timeout"), succeed]
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(self.client.post.call_count, 2)

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_timeout_all_fail(self, mock_sleep: MagicMock, mock_failure: MagicMock) -> None:
        """超时全部重试失败 → (None, None)。"""
        self.client.post.side_effect = httpx.TimeoutException("timeout")
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 3)
        mock_failure.assert_called_once()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_request_error_then_success(self, mock_sleep: MagicMock, mock_success: MagicMock) -> None:
        """网络错误 → 重试 → 成功。"""
        succeed = _make_mock_response(200, {"content": [{"type": "text", "text": "OK"}]})
        self.client.post.side_effect = [httpx.RequestError("reset"), succeed]
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(self.client.post.call_count, 2)

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_request_error_all_fail(self, mock_sleep: MagicMock, mock_failure: MagicMock) -> None:
        """网络错误全部重试失败 → (None, None)。"""
        self.client.post.side_effect = httpx.RequestError("reset")
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 3)
        mock_failure.assert_called_once()


# ═══════════════════════════════════════════════════════════
#  call_llm_with_retry — 响应解析错误
# ═══════════════════════════════════════════════════════════


class TestCallLlmWithRetryResponseErrors(unittest.TestCase):
    """响应解析错误 — 不重试，立即失败。"""

    def setUp(self) -> None:
        self.client = MagicMock(spec=httpx.Client)
        self.base_kw = dict(
            label="Test", client=self.client, url="https://api.test.com/v1",
            headers={}, payload={}, timeout=60, max_retries=2,
            max_tokens=1000, config_field="max_tokens",
            extract_fn=_default_extract, check_truncation_fn=_no_truncation,
            provider="claude", model_name="",
        )
        self.cb_patcher = patch("src.python.llm.api_base._cb_is_open", return_value=False)
        self.cb_patcher.start()

    def tearDown(self) -> None:
        self.cb_patcher.stop()

    @patch("src.python.llm.api_base._cb_record_failure")
    def test_json_decode_error(self, mock_failure: MagicMock) -> None:
        """JSON 解析失败 → 立即失败，不重试。"""
        resp = _make_mock_response(200, json_data={"content": [{"type": "text", "text": ""}]})
        resp.json.side_effect = ValueError("Invalid JSON")
        self.client.post.return_value = resp
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 1)

    @patch("src.python.llm.api_base._cb_record_failure")
    def test_extract_returns_none(self, mock_failure: MagicMock) -> None:
        """extract_fn 返回 None → 立即失败。"""
        def _none_extract(data):
            return None
        resp = _make_mock_response(200, json_data={"wrong": "format"})
        self.client.post.return_value = resp
        result, usage = call_llm_with_retry(**{**self.base_kw, "extract_fn": _none_extract})
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 1)


# ═══════════════════════════════════════════════════════════
#  call_llm_with_retry — 内容过滤 / 截断
# ═══════════════════════════════════════════════════════════


class TestCallLlmWithRetryContentFilter(unittest.TestCase):
    """空内容（内容过滤）处理。"""

    def setUp(self) -> None:
        self.client = MagicMock(spec=httpx.Client)
        self.cb_patcher = patch("src.python.llm.api_base._cb_is_open", return_value=False)
        self.cb_patcher.start()

    def tearDown(self) -> None:
        self.cb_patcher.stop()

    def test_empty_content_returns_with_usage(self) -> None:
        """空内容 → 返回 ("", usage) 供安抚重试。"""
        usage = {"input_tokens": 10, "output_tokens": 5}
        data = {"content": [{"type": "text", "text": ""}], "usage": usage}
        resp = _make_mock_response(200, json_data=data)
        self.client.post.return_value = resp

        result, u = call_llm_with_retry(
            "Test", self.client, "https://api.test.com/v1",
            {}, {}, 60, 2, 1000, "max_tokens",
            _default_extract, _no_truncation, "claude", "",
        )
        self.assertEqual(result, "")
        self.assertEqual(u["input_tokens"], 10)


class TestCallLlmWithRetryTruncation(unittest.TestCase):
    """截断检测 + 警告追加。"""

    def setUp(self) -> None:
        self.client = MagicMock(spec=httpx.Client)
        self.cb_patcher = patch("src.python.llm.api_base._cb_is_open", return_value=False)
        self.cb_patcher.start()

    def tearDown(self) -> None:
        self.cb_patcher.stop()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("src.python.llm.api_base._log_token_usage")
    @patch("src.python.llm.api_base.track_session_usage")
    def test_truncation_appends_warning(self, mock_track: MagicMock,
                                         mock_log: MagicMock, mock_success: MagicMock) -> None:
        """截断 → 内容追加截断警告。"""
        def _truncated(data, mt):
            return True
        data = {"content": [{"type": "text", "text": "部分内容"}],
                "usage": {"input_tokens": 10, "output_tokens": 800}}
        resp = _make_mock_response(200, json_data=data)
        self.client.post.return_value = resp

        result, usage = call_llm_with_retry(
            "Test", self.client, "https://api.test.com/v1",
            {}, {}, 60, 2, 800, "max_tokens_expert_review",
            _default_extract, _truncated, "claude", "",
        )
        self.assertIn("max_tokens_expert_review", result)
        self.assertIn(TRUNCATION_MARKER, result)
        self.assertIn("部分内容", result)


# ═══════════════════════════════════════════════════════════
#  call_single_provider — Provider 路由
# ═══════════════════════════════════════════════════════════


class TestCallSingleProvider(unittest.TestCase):
    """测试 provider 分发。"""

    @patch("src.python.llm.api.call_claude")
    def test_claude_routing(self, mock_claude: MagicMock) -> None:
        mock_claude.return_value = ("claude result", {"input_tokens": 10})
        result, usage = call_single_provider(
            "claude", "system", "user", "sk-key", "claude-sonnet-4-6",
            "https://api.anthropic.com/v1/messages", 800, 60, 2, None,
            "max_tokens", None, None,
        )
        self.assertEqual(result, "claude result")
        mock_claude.assert_called_once()

    @patch("src.python.llm.api.call_openai")
    def test_openai_routing(self, mock_openai: MagicMock) -> None:
        mock_openai.return_value = ("openai result", {"prompt_tokens": 20})
        result, usage = call_single_provider(
            "openai", "system", "user", "sk-key", "gpt-4o",
            "https://api.openai.com/v1/chat/completions", 800, 60, 2, None,
            "max_tokens", None, None,
        )
        self.assertEqual(result, "openai result")
        mock_openai.assert_called_once()

    def test_unknown_provider(self) -> None:
        result, usage = call_single_provider(
            "unknown", "", "", "", "", "", 0, 0, 0, None, "", None, None,
        )
        self.assertIsNone(result)
        self.assertIsNone(usage)


# ═══════════════════════════════════════════════════════════
#  _call_llm — 主调度 + 安抚重试 + 回退
# ═══════════════════════════════════════════════════════════


class TestCallLlm(unittest.TestCase):
    """_call_llm 主/回退链式调度。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_provider_success(self, mock_single: MagicMock) -> None:
        """主 provider 成功 → 返回结果。"""
        mock_single.return_value = ("成功结果", {"input_tokens": 100})
        result, usage = call_llm("system", "user", {"provider": "claude", "api_key": "sk-x"})
        self.assertEqual(result, "成功结果")
        self.assertEqual(usage["input_tokens"], 100)
        mock_single.assert_called_once()

    @patch("src.python.llm.api.call_single_provider")
    def test_provider_returns_none(self, mock_single: MagicMock) -> None:
        """主 provider 失败 → 无回退 → (None, None)。"""
        mock_single.return_value = (None, None)
        result, usage = call_llm("system", "user", {"provider": "claude", "api_key": "sk-x"})
        self.assertIsNone(result)
        self.assertIsNone(usage)

    @patch("src.python.llm.api.call_single_provider")
    def test_content_filter_recovery_success(self, mock_single: MagicMock) -> None:
        """空内容 → 安抚重试成功。"""
        mock_single.side_effect = [
            ("", {"input_tokens": 10}),
            ("安抚后结果", {"input_tokens": 20}),
        ]
        result, usage = call_llm("system", "user", {"provider": "claude", "api_key": "sk-x"})
        self.assertEqual(result, "安抚后结果")
        self.assertEqual(mock_single.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_content_filter_recovery_still_empty(self, mock_single: MagicMock) -> None:
        """安抚重试仍为空 → 无回退 → (None, None)。"""
        mock_single.side_effect = [
            ("", {"input_tokens": 10}),
            ("", {"input_tokens": 20}),
        ]
        result, usage = call_llm("system", "user", {"provider": "claude", "api_key": "sk-x"})
        self.assertIsNone(result)
        self.assertEqual(mock_single.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_fallback_success(self, mock_single: MagicMock) -> None:
        """主 provider 失败 → 回退成功。"""
        mock_single.side_effect = [
            (None, None),
            ("回退结果", {"prompt_tokens": 50}),
        ]
        config = {
            "provider": "claude", "api_key": "sk-claude",
            "fallback_provider": "openai", "fallback_api_key": "sk-openai",
            "fallback_endpoint": "https://api.openai.com/v1",
            "fallback_model": "gpt-4o",
        }
        result, usage = call_llm("system", "user", config)
        self.assertEqual(result, "回退结果")
        self.assertEqual(mock_single.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_both_fail(self, mock_single: MagicMock) -> None:
        """主 + 回退都失败 → (None, None)。"""
        mock_single.return_value = (None, None)
        config = {
            "provider": "claude", "api_key": "sk-claude",
            "fallback_provider": "openai", "fallback_api_key": "sk-openai",
        }
        result, usage = call_llm("system", "user", config)
        self.assertIsNone(result)
        self.assertEqual(mock_single.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_fallback_same_as_primary_not_used(self, mock_single: MagicMock) -> None:
        """fallback_provider == provider → 不尝试回退。"""
        mock_single.return_value = (None, None)
        config = {
            "provider": "claude", "api_key": "sk-claude",
            "fallback_provider": "claude",
        }
        result, usage = call_llm("system", "user", config)
        self.assertIsNone(result)
        mock_single.assert_called_once()

    @patch("src.python.llm.api.call_single_provider")
    def test_content_filter_then_fallback(self, mock_single: MagicMock) -> None:
        """安抚重试仍空 + 有回退 → 尝试回退。"""
        mock_single.side_effect = [
            ("", {"input_tokens": 10}),
            ("", {"input_tokens": 20}),
            ("回退结果", {"prompt_tokens": 30}),
        ]
        config = {
            "provider": "claude", "api_key": "sk-claude",
            "fallback_provider": "openai", "fallback_api_key": "sk-openai",
        }
        result, usage = call_llm("system", "user", config)
        self.assertEqual(result, "回退结果")
        self.assertEqual(mock_single.call_count, 3)



if __name__ == "__main__":
    unittest.main()

"""边缘测试：LLM API 基础模块 — api_base.py

覆盖 api_base.py 的边缘场景（熔断器、空内容响应、截断追加等）。
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
    pytest.mark.edge,
]


class TestCheckCircuitBreakerEdge(unittest.TestCase):
    """_check_circuit_breaker — 熔断器状态检查边缘场景。"""

    def test_circuit_open_returns_true(self) -> None:
        """熔断打开 → True。"""
        from src.python.llm.api_base import _check_circuit_breaker

        with patch("src.python.llm.api_base._cb_is_open", return_value=True):
            result = _check_circuit_breaker("https://api.test.com", "Test")
        self.assertTrue(result)

    def test_circuit_closed_returns_false(self) -> None:
        """熔断关闭 → False。"""
        from src.python.llm.api_base import _check_circuit_breaker

        with patch("src.python.llm.api_base._cb_is_open", return_value=False):
            result = _check_circuit_breaker("https://api.test.com", "Test")
        self.assertFalse(result)


class TestProcessSuccessResponseEdge(unittest.TestCase):
    """_process_success_response — 成功响应处理边缘场景。"""

    def test_empty_content_returns_with_usage(self) -> None:
        """空内容 → ("", usage)。"""
        from src.python.llm.api_base import _process_success_response

        data = {"usage": {"input_tokens": 10}}
        content, usage = _process_success_response(
            data,
            extract_fn=lambda d: "",
            check_truncation_fn=lambda d, mt: False,
            max_tokens=1000,
            config_field="max_tokens",
            provider="claude",
            model_name="test",
            label="Test",
            url="https://api.test.com",
        )
        self.assertEqual(content, "")
        self.assertEqual(usage, {"input_tokens": 10})

    def test_extract_returns_none(self) -> None:
        """提取返回 None → (None, None)。"""
        from src.python.llm.api_base import _process_success_response

        data = {"content": "test"}
        with patch("src.python.llm.api_base._cb_record_failure"):
            content, usage = _process_success_response(
                data,
                extract_fn=lambda d: None,
                check_truncation_fn=lambda d, mt: False,
                max_tokens=1000,
                config_field="max_tokens",
                provider="claude",
                model_name="test",
                label="Test",
                url="https://api.test.com",
            )
        self.assertIsNone(content)
        self.assertIsNone(usage)

    def test_truncation_appends_warning(self) -> None:
        """截断检测 → 内容后追加警告。"""
        from src.python.llm.api_base import (
            TRUNCATION_MARKER,
            _process_success_response,
        )

        data = {"content": "partial output", "usage": {"input_tokens": 10, "output_tokens": 5}}
        content, usage = _process_success_response(
            data,
            extract_fn=lambda d: d.get("content"),
            check_truncation_fn=lambda d, mt: True,
            max_tokens=100,
            config_field="max_tokens",
            provider="claude",
            model_name="test",
            label="Test",
            url="https://api.test.com",
        )
        self.assertIn(TRUNCATION_MARKER, content)
        self.assertIsNotNone(usage)

    def test_usage_missing_does_not_crash(self) -> None:
        """usage 缺失 → 不报错。"""
        from src.python.llm.api_base import _process_success_response

        data = {"content": "no usage data"}
        try:
            content, usage = _process_success_response(
                data,
                extract_fn=lambda d: d.get("content"),
                check_truncation_fn=lambda d, mt: False,
                max_tokens=100,
                config_field="max_tokens",
                provider="claude",
                model_name="test",
                label="Test",
                url="https://api.test.com",
            )
            self.assertEqual(content, "no usage data")
            self.assertIsNone(usage)
        except Exception as e:
            self.fail(f"usage 缺失引发异常: {e}")


class TestExtractContentEdge(unittest.TestCase):
    """_extract_content — 仅 thinking block 无 text 的边缘场景（回归测试）。

    回归缺陷：DeepSeek V4 强制推理模型在思考部分耗尽 max_tokens 预算时
    响应只有 thinking block、无 text block，原实现误判为"内容被过滤"并返回空串，
    触发无效安抚重试。修复后返回 None 走 provider 切换。
    """

    def test_thinking_only_max_tokens_returns_none(self) -> None:
        """仅 thinking + stop_reason=max_tokens → None，记录预算耗尽日志（非"内容被过滤"）。"""
        from src.python.llm.api_base import _extract_content

        data = {
            "content": [{"type": "thinking", "thinking": "internal thoughts..."}],
            "stop_reason": "max_tokens",
            "usage": {"output_tokens": 4096},
        }
        with self.assertLogs("invest", level="WARNING") as cm:
            result = _extract_content(data)
        self.assertIsNone(result)
        log_text = "\n".join(cm.output)
        self.assertIn("max_tokens", log_text, "应记录预算耗尽根因日志")
        self.assertNotIn("内容过滤", log_text, "不得误报为内容被过滤")

    def test_thinking_only_end_turn_returns_none(self) -> None:
        """仅 thinking + stop_reason=end_turn → None（内容为空，可能被过滤）。"""
        from src.python.llm.api_base import _extract_content

        data = {
            "content": [{"type": "thinking", "thinking": "internal thoughts..."}],
            "stop_reason": "end_turn",
        }
        with self.assertLogs("invest", level="WARNING") as cm:
            result = _extract_content(data)
        self.assertIsNone(result)
        self.assertIn("空内容", "\n".join(cm.output))

    def test_thinking_plus_text_returns_text(self) -> None:
        """thinking + text 并存 → 正常返回 text（不回归）。"""
        from src.python.llm.api_base import _extract_content

        data = {
            "content": [
                {"type": "thinking", "thinking": "internal thoughts..."},
                {"type": "text", "text": "final answer"},
            ],
            "stop_reason": "end_turn",
        }
        result = _extract_content(data)
        self.assertEqual(result, "final answer")


class TestCallLlmWithRetryEdge(unittest.TestCase):
    """call_llm_with_retry — 边缘场景。"""

    @patch("src.python.llm.api_base._cb_is_open", return_value=False)
    @patch("src.python.llm.api_base._attempt_api_call")
    @patch("src.python.llm.api_base._cb_record_success")
    def test_empty_content_filter_recovery(self, mock_record_success, mock_attempt, mock_cb_open) -> None:
        """内容过滤空返回 → 带空标记。"""
        from src.python.llm.api_base import call_llm_with_retry

        mock_attempt.return_value = (
            "success",
            {"content": "", "usage": {"input_tokens": 5, "output_tokens": 0}},
        )

        mock_client = MagicMock()
        result, usage = call_llm_with_retry(
            "Test",
            mock_client,
            "https://api.test.com",
            {},
            {},
            30.0,
            2,
            1000,
            "max_tokens",
            extract_fn=lambda d: d.get("content"),
            check_truncation_fn=lambda d, mt: False,
            provider="claude",
        )
        self.assertEqual(result, "")
        self.assertIsNotNone(usage)

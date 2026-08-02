"""LLM API 调用模块单元测试。

测试目标：
  - call_llm — provider 路由
  - call_claude — Extended Thinking 降级
  - Provider 回退链路
  - content_filter 空返回安抚重试

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test.unit.llm.test_llm_api -v
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.llm.api import (
    call_claude,
    call_llm,
)
from src.python.llm.api_base import (
    _extract_content,
    _get_last_thinking_exhausted,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


# ═══════════════════════════════════════════════════════════
#  call_llm provider routing
# ═══════════════════════════════════════════════════════════


class TestCallLlmProvider(unittest.TestCase):
    """测试 call_llm 的 provider 路由。"""

    def test_unsupported_provider(self) -> None:
        config = {"provider": "unknown", "api_key": "test"}
        content, usage, _ = call_llm("system", "user", config)
        self.assertIsNone(content)
        self.assertIsNone(usage)

    @patch("src.python.llm.api.call_claude")
    def test_claude_routing(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("claude result", {"input_tokens": 10, "output_tokens": 50})
        config = {"provider": "claude", "api_key": "sk-xxx"}
        content, usage, _ = call_llm("system", "user", config)
        self.assertEqual(content, "claude result")
        self.assertEqual(usage, {"input_tokens": 10, "output_tokens": 50})
        mock_call.assert_called_once()

    @patch("src.python.llm.api.call_openai")
    def test_openai_routing(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("openai result", {"prompt_tokens": 20, "completion_tokens": 80})
        config = {"provider": "openai", "api_key": "sk-xxx"}
        content, usage, _ = call_llm("system", "user", config)
        self.assertEqual(content, "openai result")
        self.assertEqual(usage, {"prompt_tokens": 20, "completion_tokens": 80})
        mock_call.assert_called_once()


# ═══════════════════════════════════════════════════════════
#  call_claude Extended Thinking 降级
# ═══════════════════════════════════════════════════════════


class TestCallClaudeThinkingDegradation(unittest.TestCase):
    """测试 call_claude 中 Extended Thinking 的降级行为。

    通过 mock call_llm_with_retry 捕获 payload，验证 thinking 注入逻辑。
    """

    def setUp(self) -> None:
        self.base_kw = dict(
            system="system",
            user="user",
            api_key="sk-test",
            endpoint="",
            max_tokens=800,
            http_client=MagicMock(),
        )
        self.llm_config = {
            "thinking_enabled_global_macro": True,
            "thinking_budget_global_macro": 4000,
        }

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    def test_thinking_injected_for_supported_model(self, mock_retry: MagicMock) -> None:
        """Sonnet-4 支持 Extended Thinking，应注入 thinking 参数。"""
        call_claude(
            **self.base_kw,
            model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro",
            llm_config=self.llm_config,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertIn("thinking", _payload)
        self.assertEqual(_payload["thinking"]["type"], "enabled")
        # temperature 应在 thinking 开启时被移除
        self.assertNotIn("temperature", _payload)

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    def test_thinking_skipped_for_unsupported_model(self, mock_retry: MagicMock) -> None:
        """Sonnet-3.5 不支持 Extended Thinking，应降级跳过。"""
        call_claude(
            **self.base_kw,
            model="claude-sonnet-3-5-20241022",
            config_field="max_tokens_global_macro",
            llm_config=self.llm_config,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    def test_thinking_skipped_when_disabled(self, mock_retry: MagicMock) -> None:
        """thinking_enabled=False 时不应注入 thinking 参数。"""
        cfg = {"thinking_enabled_global_macro": False}
        call_claude(
            **self.base_kw,
            model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro",
            llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    def test_thinking_skipped_when_no_llm_config(self, mock_retry: MagicMock) -> None:
        """llm_config=None 时不报错、不注入。"""
        call_claude(
            **self.base_kw,
            model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro",
            llm_config=None,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    def test_budget_auto_padding(self, mock_retry: MagicMock) -> None:
        """budget 小于 max_tokens + 1024 时自动补足到 max_tokens + 4096。"""
        cfg = {"thinking_enabled_global_macro": True, "thinking_budget_global_macro": 100}
        call_claude(
            **self.base_kw,
            model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro",
            llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        # max_tokens=800 → auto_pad=800+4096=4896
        self.assertEqual(_payload["thinking"]["budget_tokens"], 4896)

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    def test_deepseek_uses_effort_not_budget(self, mock_retry: MagicMock) -> None:
        """DeepSeek 使用 effort 而非 budget_tokens 控制思考深度。"""
        cfg = {
            "thinking_enabled_global_macro": True,
            "reasoning_effort_global_macro": "high",
        }
        call_claude(
            **self.base_kw,
            model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro",
            llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertEqual(_payload["thinking"]["type"], "enabled")
        self.assertIn("output_config", _payload)
        self.assertEqual(_payload["output_config"]["effort"], "high")
        # DeepSeek 不发送 budget_tokens
        self.assertNotIn("budget_tokens", _payload["thinking"])
        # temperature 应被移除
        self.assertNotIn("temperature", _payload)

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    def test_deepseek_effort_default_high(self, mock_retry: MagicMock) -> None:
        """DeepSeek 未配置 reasoning_effort 时默认 high。"""
        cfg = {"thinking_enabled_global_macro": True}
        call_claude(
            **self.base_kw,
            model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro",
            llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertEqual(_payload["output_config"]["effort"], "high")

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    def test_deepseek_effort_max(self, mock_retry: MagicMock) -> None:
        """DeepSeek reasoning_effort 可以设为 max。"""
        cfg = {
            "thinking_enabled_global_macro": True,
            "reasoning_effort_global_macro": "max",
        }
        call_claude(
            **self.base_kw,
            model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro",
            llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertEqual(_payload["output_config"]["effort"], "max")

    # ═══════════════════════════════════════════════════════════
    #  思考耗尽安全网：thinking 耗尽 max_tokens 预算无正文时，
    #  自动关闭 thinking 同 provider 重试一次，保证有正文产出。
    # ═══════════════════════════════════════════════════════════

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    @patch("src.python.llm._api_claude._get_last_thinking_exhausted")
    @patch("src.python.llm._api_claude.clear_last_thinking_exhausted")
    def test_thinking_exhausted_retries_without_thinking(
        self, mock_clear: MagicMock, mock_get: MagicMock, mock_retry: MagicMock
    ) -> None:
        """思考耗尽（无正文）→ 关闭 thinking 重试一次，temperature 恢复，返回第二次结果。"""
        mock_get.side_effect = [True, False]
        mock_retry.side_effect = [(None, None), ("recovered", {"output_tokens": 5})]
        cfg = {"thinking_enabled_global_macro": True}
        result, usage = call_claude(
            **self.base_kw,
            model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro",
            llm_config=cfg,
            temperature=0.3,
        )
        self.assertEqual(result, "recovered")
        self.assertEqual(mock_retry.call_count, 2)
        first_payload = mock_retry.call_args_list[0][1]["payload"]
        second_payload = mock_retry.call_args_list[1][1]["payload"]
        self.assertIn("thinking", first_payload)
        self.assertNotIn("thinking", second_payload)
        # thinking 关闭后恢复 temperature
        self.assertEqual(second_payload.get("temperature"), 0.3)
        mock_clear.assert_called_once()

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    @patch("src.python.llm._api_claude._get_last_thinking_exhausted")
    @patch("src.python.llm._api_claude.clear_last_thinking_exhausted")
    def test_thinking_exhausted_flag_false_no_retry(
        self, mock_clear: MagicMock, mock_get: MagicMock, mock_retry: MagicMock
    ) -> None:
        """flag False（非思考耗尽空内容）→ 不重试，行为与现状一致。"""
        mock_get.return_value = False
        mock_retry.return_value = (None, None)
        cfg = {"thinking_enabled_global_macro": True}
        result, usage = call_claude(
            **self.base_kw,
            model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro",
            llm_config=cfg,
        )
        self.assertIsNone(result)
        self.assertEqual(mock_retry.call_count, 1)
        mock_clear.assert_not_called()

    @patch("src.python.llm._api_claude.call_llm_with_retry")
    @patch("src.python.llm._api_claude._get_last_thinking_exhausted")
    @patch("src.python.llm._api_claude.clear_last_thinking_exhausted")
    def test_no_thinking_enabled_no_retry(
        self, mock_clear: MagicMock, mock_get: MagicMock, mock_retry: MagicMock
    ) -> None:
        """未注入 thinking → 即使 flag True 也不重试（短路由，不误触）。"""
        mock_get.return_value = True
        mock_retry.return_value = (None, None)
        cfg = {"thinking_enabled_global_macro": False}
        result, usage = call_claude(
            **self.base_kw,
            model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro",
            llm_config=cfg,
        )
        self.assertIsNone(result)
        self.assertEqual(mock_retry.call_count, 1)
        mock_clear.assert_not_called()

    def test_thinking_exhausted_flag_thread_local_isolation(self) -> None:
        """并发线程 _extract_content 不清除本线程思考耗尽标志（thread-local 隔离）。

        LLM 生成在 ThreadPoolExecutor(llm_max_concurrency=3) 下并发执行（多个模块
        并行）。思考耗尽标志存储于线程局部存储：其他线程 _extract_content 开头的
        无条件复位不会清除本线程已置位的标志，call_claude"关闭 thinking 重试"安全网
        可靠触发，provider 不会因并发线程的提取而误标 api_error。
        """
        exhausted_data = {
            "content": [{"type": "thinking", "thinking": "思考内容"}],  # 仅 thinking block
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 10, "output_tokens": 20000},
        }
        normal_data = {
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 10},
        }
        # 主线程提取思考耗尽响应 → 置位本线程标志
        self.assertIsNone(_extract_content(exhausted_data))
        self.assertTrue(_get_last_thinking_exhausted())

        # 并发线程提取普通响应（旧全局实现会复位共享标志 → 本断言回归失败）
        def _worker() -> None:
            _extract_content(normal_data)

        t = threading.Thread(target=_worker)
        t.start()
        t.join()
        self.assertTrue(_get_last_thinking_exhausted(), "并发线程不应清除本线程思考耗尽标志")

        # 本线程内后续提取仍正常复位（thread-local 保留原语义）
        _extract_content(normal_data)
        self.assertFalse(_get_last_thinking_exhausted())


# ═══════════════════════════════════════════════════════════════
#  Provider 回退链路测试
# ═══════════════════════════════════════════════════════════════


class TestProviderFallback(unittest.TestCase):
    """测试 call_llm 在主 provider 失败时回退到 fallback provider。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_main_provider_success_no_fallback(self, mock_call):
        """主 provider 成功 → 不调用 fallback。"""
        mock_call.return_value = ("main result", {"input_tokens": 100})
        config = {
            "provider": "claude",
            "api_key": "sk-main",
            "fallback_provider": "openai",
            "fallback_api_key": "sk-fb",
        }
        content, usage, _ = call_llm("sys", "user", config)
        self.assertEqual(content, "main result")
        self.assertEqual(mock_call.call_count, 1)

    @patch("src.python.llm.api.call_single_provider")
    def test_main_failure_fallback_used(self, mock_call):
        """主 provider 返回 None → fallback 被调用。"""
        mock_call.side_effect = [
            (None, None),  # 主 provider 失败
            ("fb result", {"prompt_tokens": 50}),  # fallback 成功
        ]
        config = {
            "provider": "claude",
            "api_key": "sk-main",
            "fallback_provider": "openai",
            "fallback_api_key": "sk-fb",
            "fallback_endpoint": "https://api.openai.com/v1",
            "fallback_model": "gpt-4o",
        }
        content, usage, _ = call_llm("sys", "user", config)
        self.assertEqual(content, "fb result")
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_main_and_fallback_both_fail(self, mock_call):
        """主 + fallback 均失败 → (None, None)。"""
        mock_call.return_value = (None, None)
        config = {
            "provider": "claude",
            "api_key": "sk-main",
            "fallback_provider": "openai",
            "fallback_api_key": "sk-fb",
        }
        content, usage, _ = call_llm("sys", "user", config)
        self.assertIsNone(content)
        self.assertIsNone(usage)
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_no_fallback_configured(self, mock_call):
        """未配置 fallback → 不尝试 fallback。"""
        mock_call.return_value = (None, None)
        config = {"provider": "claude", "api_key": "sk-main"}
        content, usage, _ = call_llm("sys", "user", config)
        self.assertIsNone(content)
        self.assertEqual(mock_call.call_count, 1)

    @patch("src.python.llm.api.call_single_provider")
    def test_fallback_same_as_main_no_loop(self, mock_call):
        """fallback_provider == provider → 不重复调用。"""
        mock_call.return_value = (None, None)
        config = {
            "provider": "claude",
            "api_key": "sk-main",
            "fallback_provider": "claude",
            "fallback_api_key": "sk-fb",
        }
        content, usage, _ = call_llm("sys", "user", config)
        self.assertIsNone(content)
        self.assertEqual(mock_call.call_count, 1)


# ═══════════════════════════════════════════════════════════════
#  LLM content_filter 空返回安抚重试测试
# ═══════════════════════════════════════════════════════════════


class TestContentFilterRecovery(unittest.TestCase):
    """测试 call_llm 在 API 返回空内容时的安抚重试机制。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_empty_content_triggers_retry(self, mock_call):
        """API 返回空字符串 → 追加安抚指令重试一次。"""
        mock_call.side_effect = [
            ("", {"input_tokens": 100}),  # 第一次：空内容
            ("retry result", {"input_tokens": 200}),  # 第二次：安抚后成功
        ]
        config = {"provider": "claude", "api_key": "sk-test"}
        content, usage, _ = call_llm("system prompt", "user content", config)
        # 应返回安抚重试后的结果
        self.assertEqual(content, "retry result")
        self.assertEqual(mock_call.call_count, 2)

        # 验证第二次调用 system_prompt 包含安抚指令
        from src.python.llm.api import _CONTENT_FILTER_RECOVERY

        second_call_system = mock_call.call_args_list[1][0][1]  # system_prompt arg
        self.assertIn("注意：请确保你的回答包含实质性的分析内容", second_call_system)

    @patch("src.python.llm.api.call_single_provider")
    def test_empty_content_then_still_empty(self, mock_call):
        """安抚重试后仍为空 → 尝试 fallback provider。"""
        mock_call.side_effect = [
            ("", {"input_tokens": 10}),  # 主 provider 空
            ("", {"input_tokens": 20}),  # 安抚重试仍空
            ("fb ok", {"prompt_tokens": 5}),  # fallback 成功
        ]
        config = {
            "provider": "claude",
            "api_key": "sk-main",
            "fallback_provider": "openai",
            "fallback_api_key": "sk-fb",
        }
        content, usage, _ = call_llm("sys", "user", config)
        self.assertEqual(content, "fb ok")
        self.assertEqual(mock_call.call_count, 3)

    @patch("src.python.llm.api.call_single_provider")
    def test_empty_content_no_fallback_returns_none(self, mock_call):
        """安抚重试仍空且无 fallback → (None, None)。"""
        mock_call.return_value = ("", {"input_tokens": 10})
        config = {"provider": "claude", "api_key": "sk-test"}
        content, usage, _ = call_llm("sys", "user", config)
        self.assertIsNone(content)
        # 被调用 2 次（原始 + 安抚重试）
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_normal_content_no_retry(self, mock_call):
        """正常返回内容 → 不触发安抚重试。"""
        mock_call.return_value = ("正常内容", {"input_tokens": 100})
        config = {"provider": "claude", "api_key": "sk-test"}
        content, usage, _ = call_llm("sys", "user", config)
        self.assertEqual(content, "正常内容")
        self.assertEqual(mock_call.call_count, 1)

    @patch("src.python.llm.api.call_single_provider")
    def test_none_from_provider_triggers_fallback_not_retry(self, mock_call):
        """provider 返回 None（格式异常）→ 不触发安抚重试，直接走 fallback。"""
        mock_call.side_effect = [
            (None, None),  # 主 provider 格式异常
            ("fb result", None),  # fallback 成功
        ]
        config = {
            "provider": "claude",
            "api_key": "sk-main",
            "fallback_provider": "openai",
            "fallback_api_key": "sk-fb",
        }
        content, usage, _ = call_llm("sys", "user", config)
        self.assertEqual(content, "fb result")
        # 只调用了 2 次（主 + fallback），没有安抚重试
        self.assertEqual(mock_call.call_count, 2)

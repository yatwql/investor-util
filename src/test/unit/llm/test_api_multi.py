"""LLM Multi-Provider — 异常链处理 + 安抚重试。

覆盖 R7 场景：
  1. 空内容安抚重试后成功
  2. 空内容安抚耗尽 → 回退下一 provider
  3. 安抚+回退组合验证 provider_name
  4. 熔断异常兼容（call_single_provider 抛异常 → 跳下一 provider）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/llm/test_api_multi.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


class TestChainEmptyContentRetry(unittest.TestCase):
    """空内容安抚重试在当前 provider 内完成，不跨 provider。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_retry_succeeds_within_same_provider(self, mock_call: MagicMock) -> None:
        """首次返回空 → 安抚重试成功 → 返回重试结果。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            ("", {"input_tokens": 100}),           # 首次空内容
            ("retry success", {"input_tokens": 200}),  # 安抚后成功
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        content, usage, provider_name = call_llm("sys", "user", config)

        self.assertEqual(content, "retry success")
        self.assertEqual(usage, {"input_tokens": 200})
        self.assertEqual(provider_name, "p1")  # 还是在 p1 内完成
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_retry_includes_calming_prompt(self, mock_call: MagicMock) -> None:
        """安抚重试的 system prompt 包含安抚指令。"""
        from src.python.llm.api import call_llm
        from src.python.llm.api import _CONTENT_FILTER_RECOVERY

        mock_call.side_effect = [
            ("", {}),                          # 首次空
            ("ok", {}),                        # 安抚后成功
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
            ],
        }
        call_llm("original prompt", "user", config)

        # 第二次调用的 system_prompt 应包含安抚指令
        calmed = mock_call.call_args_list[1][1]["system_prompt"]
        self.assertIn(_CONTENT_FILTER_RECOVERY, calmed)


class TestChainRetryExhaustedFallback(unittest.TestCase):
    """空内容安抚耗尽 → 正确回退下一 provider。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_retry_exhausted_falls_back(self, mock_call: MagicMock) -> None:
        """p1 空 → 安抚仍空 → p2 成功。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            ("", {"input_tokens": 10}),     # p1 原始空
            ("", {"input_tokens": 20}),     # p1 安抚仍空
            ("fb ok", {"prompt_tokens": 5}),   # p2 成功
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        content, usage, provider_name = call_llm("sys", "user", config)

        self.assertEqual(content, "fb ok")
        self.assertEqual(provider_name, "p2")  # 来自 p2
        self.assertEqual(mock_call.call_count, 3)

    @patch("src.python.llm.api.call_single_provider")
    def test_all_providers_empty_fails(self, mock_call: MagicMock) -> None:
        """全部 provider 空内容 → (None, None, None)。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            ("", {}), ("", {}),   # p1 原始 + 安抚
            ("", {}), ("", {}),   # p2 原始 + 安抚
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        content, usage, provider_name = call_llm("sys", "user", config)

        self.assertIsNone(content)
        self.assertIsNone(usage)
        self.assertIsNone(provider_name)
        self.assertEqual(mock_call.call_count, 4)


class TestChainExceptionSafety(unittest.TestCase):
    """chain 循环异常安全：单个 provider 抛异常不中断整个 chain。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_exception_skips_to_next_provider(self, mock_call: MagicMock) -> None:
        """p1 抛异常 → 捕获后尝试 p2 → p2 成功。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            RuntimeError("p1 网络超时"),
            ("p2 ok", {"input_tokens": 50}),
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        content, usage, provider_name = call_llm("sys", "user", config)

        self.assertEqual(content, "p2 ok")
        self.assertEqual(provider_name, "p2")
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_all_providers_exception_fails(self, mock_call: MagicMock) -> None:
        """全部 provider 抛异常 → (None, None, None)。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            RuntimeError("p1 timeout"),
            RuntimeError("p2 timeout"),
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        content, usage, provider_name = call_llm("sys", "user", config)

        self.assertIsNone(content)
        self.assertIsNone(usage)
        self.assertIsNone(provider_name)
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api.call_single_provider")
    def test_exception_during_empty_retry_skips(self, mock_call: MagicMock) -> None:
        """p1 空 → 安抚重试抛异常 → p2 接手。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            ("", {"input_tokens": 10}),     # p1 原始空
            RuntimeError("安抚重试异常"),   # p1 安抚抛异常
            ("p2 rescue", {"prompt_tokens": 5}),  # p2 成功
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        content, usage, provider_name = call_llm("sys", "user", config)

        self.assertEqual(content, "p2 rescue")
        self.assertEqual(provider_name, "p2")
        self.assertEqual(mock_call.call_count, 3)


class TestChainProviderName(unittest.TestCase):
    """验证不同场景下 provider_name 返回值正确性。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_first_provider_success_name(self, mock_call: MagicMock) -> None:
        """首个 provider 成功 → provider_name 为 p1。"""
        from src.python.llm.api import call_llm

        mock_call.return_value = ("result", {"input_tokens": 10})

        config = {
            "_provider_list": [
                {"name": "my-claude", "provider": "claude", "api_key": "sk-p1"},
                {"name": "my-openai", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        _, _, provider_name = call_llm("sys", "user", config)
        self.assertEqual(provider_name, "my-claude")

    @patch("src.python.llm.api.call_single_provider")
    def test_fallback_provider_success_name(self, mock_call: MagicMock) -> None:
        """p1 失败 → p2 成功 → provider_name 为 p2。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            (None, None),
            ("from fallback", {"prompt_tokens": 10}),
        ]

        config = {
            "_provider_list": [
                {"name": "primary", "provider": "claude", "api_key": "sk-p1"},
                {"name": "secondary", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        _, _, provider_name = call_llm("sys", "user", config)
        self.assertEqual(provider_name, "secondary")


class TestChainFailureTracking(unittest.TestCase):
    """失败追踪 — provider name 记录 + 所有尝试记录。"""

    def _pop_failure(self, key: str) -> None:
        """清理 LLM_MODULE_FAILURE 避免测试间污染。"""
        from src.python.llm.prompts import LLM_MODULE_FAILURE
        LLM_MODULE_FAILURE.pop(key, None)

    @patch("src.python.llm.api.call_single_provider")
    def test_failure_has_provider_name(self, mock_call: MagicMock) -> None:
        """失败原因含 provider name。"""
        from src.python.llm.api import call_llm
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        self._pop_failure("global_macro")
        mock_call.return_value = (None, None)  # 全部失败

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        call_llm("sys", "user", config, config_field="max_tokens_global_macro")

        result = LLM_MODULE_FAILURE.get("global_macro")
        self.assertIsInstance(result, dict)
        assert isinstance(result, dict)  # for type narrowing
        attempted = result.get("attempted", [])
        self.assertEqual(len(attempted), 2)
        # 每条记录应以 "provider_name: " 开头
        for entry in attempted:
            self.assertIn(": ", entry, f"失败原因应包含 provider name: {entry}")
        # p1 先尝试
        self.assertIn("p1: ", attempted[0])

    @patch("src.python.llm.api.call_single_provider")
    def test_chain_all_fail_records_all(self, mock_call: MagicMock) -> None:
        """全部失败时记录所有尝试。"""
        from src.python.llm.api import call_llm
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        self._pop_failure("expert_review")
        mock_call.side_effect = [
            (None, None),           # p1 api_error
            RuntimeError("crash"),  # p2 异常
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
        }
        call_llm("sys", "user", config, config_field="max_tokens_expert_review")

        result = LLM_MODULE_FAILURE.get("expert_review")
        self.assertIsInstance(result, dict)
        assert isinstance(result, dict)
        attempted = result.get("attempted", [])
        self.assertEqual(len(attempted), 2)
        self.assertIn("p1: ", attempted[0])
        self.assertIn("p2: EXCEPTION", attempted[1])

    @patch("src.python.llm.api.call_single_provider")
    def test_success_clears_failure(self, mock_call: MagicMock) -> None:
        """成功时 final_status 应为 success。"""
        from src.python.llm.api import call_llm
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        self._pop_failure("health_check")
        mock_call.return_value = ("ok", {"input_tokens": 10})

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
            ],
        }
        call_llm("sys", "user", config, config_field="max_tokens_health_check")

        result = LLM_MODULE_FAILURE.get("health_check")
        self.assertIsInstance(result, dict)
        assert isinstance(result, dict)
        self.assertEqual(result.get("final_status"), "success")
        self.assertIn("p1: SUCCESS", result.get("attempted", []))


class TestModulePreferredRouting(unittest.TestCase):
    """R10 — 每模块 Provider 路由端到端验证。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_module_preferred_full_chain(self, mock_call: MagicMock) -> None:
        """preferred 配置 → resolve_provider_chain → 偏好 provider 排首位。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            ("preferred result", {}),  # 偏好 provider 先被调用
            ("should not happen", {}),
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
                {"name": "p3", "provider": "gemini", "api_key": "sk-p3"},
            ],
            "_preferred_providers": {
                "global_macro": "p2",  # p2 应在第一个尝试
            },
            "_strategy": "priority",
        }
        content, usage, provider_name = call_llm(
            "sys", "user", config, config_field="max_tokens_global_macro",
        )

        self.assertEqual(content, "preferred result")
        self.assertEqual(provider_name, "p2")  # p2 排首位
        self.assertEqual(mock_call.call_count, 1)  # 只调了一次

    @patch("src.python.llm.api.call_single_provider")
    def test_different_modules_different_preferences(self, mock_call: MagicMock) -> None:
        """不同模块的 preferred 独立生效。"""
        from src.python.llm.api import call_llm

        config = {
            "_provider_list": [
                {"name": "claude-main", "provider": "claude", "api_key": "sk-c"},
                {"name": "openai-fallback", "provider": "openai", "api_key": "sk-o"},
                {"name": "gemini-backup", "provider": "gemini", "api_key": "sk-g"},
            ],
            "_preferred_providers": {
                "global_macro": "gemini-backup",
                "expert_review": "openai-fallback",
            },
            "_strategy": "priority",
        }

        # 模块 A：global_macro → 偏好 gemini
        mock_call.side_effect = [
            ("gemini macro", {}),  # gemini-backup 先
            ("should not happen", {}),
        ]
        _, _, pn1 = call_llm("sys", "user", config, config_field="max_tokens_global_macro")
        self.assertEqual(pn1, "gemini-backup")

        # 模块 B：expert_review → 偏好 openai
        mock_call.side_effect = [
            ("openai expert", {}),  # openai-fallback 先
            ("should not happen", {}),
        ]
        _, _, pn2 = call_llm("sys", "user", config, config_field="max_tokens_expert_review")
        self.assertEqual(pn2, "openai-fallback")


if __name__ == "__main__":
    unittest.main()

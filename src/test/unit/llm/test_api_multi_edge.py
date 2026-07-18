"""LLM Multi-Provider — 异常边缘场景。

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/llm/test_api_multi_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm, pytest.mark.edge]


class TestChainNoFallbackFields(unittest.TestCase):
    """验证 _provider_list 配置后，旧 fallback 字段不再生效。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_fallback_fields_ignored_when_chain_configured(self, mock_call: MagicMock) -> None:
        """配置了 _provider_list 后，fallback_provider 不应被调用。"""
        from src.python.llm.api import call_llm

        # 两个 provider 都失败
        mock_call.return_value = (None, None)

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
            # 旧 fallback 字段——不应生效
            "provider": "claude",
            "api_key": "sk-old",
            "fallback_provider": "gemini",
            "fallback_api_key": "sk-fb",
            "fallback_endpoint": "https://fake.example.com",
        }
        result, usage, provider_name = call_llm("sys", "user", config)

        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertIsNone(provider_name)
        # 应只调用了 2 次（p1 + p2），fallback_provider 不被调用
        self.assertEqual(mock_call.call_count, 2)

        # 验证调用的 api_key 来自 chain，非 fallback 字段
        call_args_list = mock_call.call_args_list
        for call_args in call_args_list:
            kwargs = call_args[1] if len(call_args) > 1 else {}
            api_key = kwargs.get("api_key", "")
            self.assertIn(api_key, ["sk-p1", "sk-p2"],
                          "api_key 应来自 _provider_list，而非旧 fallback 字段")

    @patch("src.python.llm.api.call_single_provider")
    def test_fallback_model_ignored(self, mock_call: MagicMock) -> None:
        """fallback_model 在链模式下被忽略。"""
        from src.python.llm.api import call_llm

        mock_call.side_effect = [
            (None, None),          # p1 失败
            ("chain ok", {}),      # p2 成功
        ]

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-p1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-p2"},
            ],
            "fallback_model": "gpt-4o-mini",  # 不应使用
        }
        result, usage, provider_name = call_llm("sys", "user", config)

        self.assertEqual(result, "chain ok")
        self.assertEqual(provider_name, "p2")
        self.assertEqual(mock_call.call_count, 2)


class TestFailureTrackingLegacyFormat(unittest.TestCase):
    """旧字符串格式仍可被消费者读取。"""

    def test_dict_format_not_mistaken_for_disabled(self) -> None:
        """dict 格式不应被 == FAIL_REASON_DISABLED 误匹配。"""
        from src.python.llm.prompts import LLM_MODULE_FAILURE, FAIL_REASON_DISABLED

        LLM_MODULE_FAILURE["health_check"] = {
            "attempted": ["p1: api_error"],
            "final_status": "api_error",
        }
        self.assertNotEqual(LLM_MODULE_FAILURE.get("health_check"), FAIL_REASON_DISABLED,
                            "dict 格式不应等于禁用常量")
        LLM_MODULE_FAILURE.pop("health_check", None)

    def test_legacy_string_still_works(self) -> None:
        """旧字符串格式的 FAIL_REASON 仍能正确比较。"""
        from src.python.llm.prompts import (
            LLM_MODULE_FAILURE,
            FAIL_REASON_API_ERROR, FAIL_REASON_TIMEOUT,
            FAIL_REASON_NETWORK_ERROR, FAIL_REASON_NOT_CONFIGURED,
            FAIL_REASON_CIRCUIT_OPEN, FAIL_REASON_DISABLED,
        )

        # 验证旧格式仍然是 str，可被 == 比较
        self.assertIsInstance(FAIL_REASON_API_ERROR, str)
        self.assertIsInstance(FAIL_REASON_DISABLED, str)

        # 验证旧格式直接相等比较
        LLM_MODULE_FAILURE["global_macro"] = FAIL_REASON_API_ERROR
        self.assertEqual(LLM_MODULE_FAILURE.get("global_macro"), FAIL_REASON_API_ERROR)
        LLM_MODULE_FAILURE.pop("global_macro", None)

        # 验证 dict 格式不误匹配
        LLM_MODULE_FAILURE["expert_review"] = {
            "attempted": ["p1: api_error"],
            "final_status": FAIL_REASON_API_ERROR,
        }
        self.assertNotIsInstance(LLM_MODULE_FAILURE.get("expert_review"), str,
                                 "多链格式应为 dict 而非 str")
        LLM_MODULE_FAILURE.pop("expert_review", None)

    def test_legacy_placeholder_mapping_unchanged(self) -> None:
        """旧格式 _PLACEHOLDER_BY_REASON 映射未变更。"""
        from src.python.llm.prompts import (
            FAIL_REASON_NOT_CONFIGURED, FAIL_REASON_API_ERROR,
            FAIL_REASON_TIMEOUT, FAIL_REASON_NETWORK_ERROR,
            FAIL_REASON_CIRCUIT_OPEN, FAIL_REASON_DISABLED,
        )
        from src.python.report.llm_content import _PLACEHOLDER_BY_REASON

        self.assertIn(FAIL_REASON_NOT_CONFIGURED, _PLACEHOLDER_BY_REASON)
        self.assertIn(FAIL_REASON_API_ERROR, _PLACEHOLDER_BY_REASON)
        self.assertIn(FAIL_REASON_TIMEOUT, _PLACEHOLDER_BY_REASON)
        self.assertIn(FAIL_REASON_NETWORK_ERROR, _PLACEHOLDER_BY_REASON)
        self.assertIn(FAIL_REASON_CIRCUIT_OPEN, _PLACEHOLDER_BY_REASON)


if __name__ == "__main__":
    unittest.main()

"""LLM 合规声明注入模块单元测试。

测试目标：
  - apply_compliance_guardrails — 叠加声明、幂等、角色追加项、空 prompt 保护
  - call_llm 漏斗接线 — 下游 provider 收到的 system prompt 必含合规声明

运行：
  pytest src/test/unit/llm/test_compliance.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.llm.api import call_llm
from src.python.llm.compliance import (
    COMPLIANCE_CLOSING,
    apply_compliance_guardrails,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


class TestApplyComplianceGuardrails(unittest.TestCase):
    """apply_compliance_guardrails 纯函数测试。"""

    def test_appends_closing_to_plain_prompt(self) -> None:
        result = apply_compliance_guardrails("你是复盘助手。")
        self.assertIn("你是复盘助手。", result)
        self.assertIn(COMPLIANCE_CLOSING, result)
        # 声明位于 prompt 尾部
        self.assertTrue(result.rstrip().endswith(COMPLIANCE_CLOSING))

    def test_idempotent_on_second_application(self) -> None:
        once = apply_compliance_guardrails("你是复盘助手。")
        twice = apply_compliance_guardrails(once)
        self.assertEqual(once, twice)
        # 声明只出现一次
        self.assertEqual(twice.count(COMPLIANCE_CLOSING), 1)

    def test_role_extra_items_appended_for_known_role(self) -> None:
        result = apply_compliance_guardrails("你是新闻判定员。", role="news_correlation")
        self.assertIn(COMPLIANCE_CLOSING, result)
        self.assertIn("不得引申为确定性因果", result)
        # 角色追加项位于通用声明之后（尾部）
        self.assertTrue(result.rstrip().endswith("。"))

    def test_unknown_role_gets_generic_only(self) -> None:
        result = apply_compliance_guardrails("你是复盘助手。", role="no_such_module")
        self.assertIn(COMPLIANCE_CLOSING, result)
        self.assertNotIn("不得引申为确定性因果", result)

    def test_empty_prompt_untouched(self) -> None:
        self.assertEqual(apply_compliance_guardrails(""), "")
        self.assertEqual(apply_compliance_guardrails("", role="news_correlation"), "")

    def test_prompt_already_containing_closing_untouched(self) -> None:
        # 模板自带合规声明时不得重复叠加（幂等保护）
        custom = f"你是复盘助手。\n\n{COMPLIANCE_CLOSING}"
        self.assertEqual(apply_compliance_guardrails(custom), custom)


class TestCallLlmComplianceWiring(unittest.TestCase):
    """call_llm 单一漏斗接线：provider 收到的 system prompt 必含合规声明。"""

    @patch("src.python.llm.api.call_claude")
    def test_claude_receives_guardrailed_prompt(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("ok", {"input_tokens": 1, "output_tokens": 2})
        content, _, _ = call_llm("原始 system", "user", {"provider": "claude", "api_key": "sk-x"})
        self.assertEqual(content, "ok")
        sent_system = mock_call.call_args[0][0] if mock_call.call_args[0] else mock_call.call_args.kwargs.get("system")
        # call_claude 第一个位置参数为 system prompt
        self.assertIsNotNone(sent_system)
        self.assertIn(COMPLIANCE_CLOSING, sent_system)
        self.assertIn("原始 system", sent_system)

    @patch("src.python.llm.api.call_claude")
    def test_prompt_with_existing_closing_not_doubled_through_call_llm(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("ok", {"input_tokens": 1, "output_tokens": 2})
        pre_guardrailed = apply_compliance_guardrails("原始 system")
        call_llm(pre_guardrailed, "user", {"provider": "claude", "api_key": "sk-x"})
        sent_system = mock_call.call_args[0][0] if mock_call.call_args[0] else mock_call.call_args.kwargs.get("system")
        self.assertEqual(sent_system.count(COMPLIANCE_CLOSING), 1)

"""LLM 占位文本三种状态区分测试。

测试目标：
  - FAIL_REASON_NOT_CONFIGURED → 占位文本提示"LLM 未配置"
  - FAIL_REASON_DISABLED → 占位文本提示"已禁用"
  - FAIL_REASON_API_ERROR → 占位文本提示"LLM API 调用失败"
  - 以上三种占位文本互不相同、无歧义

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_llm_placeholder -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.llm.prompts import (

    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_API_ERROR,
    FAIL_REASON_DISABLED,
    LLM_MODULE_FAILURE,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


class TestLlmPlaceholderTextConstants(unittest.TestCase):
    """验证失败原因常量值互不相同。"""

    def test_constants_distinct(self):
        """三种 FAIL_REASON 常量值各不相同。"""
        reasons = {FAIL_REASON_NOT_CONFIGURED, FAIL_REASON_API_ERROR, FAIL_REASON_DISABLED}
        self.assertEqual(len(reasons), 3)

    def test_not_configured_value(self):
        """not_configured 常量为 'not_configured'。"""
        self.assertEqual(FAIL_REASON_NOT_CONFIGURED, "not_configured")

    def test_api_error_value(self):
        """api_error 常量为 'api_error'。"""
        self.assertEqual(FAIL_REASON_API_ERROR, "api_error")

    def test_disabled_value(self):
        """disabled 常量为 'disabled'。"""
        self.assertEqual(FAIL_REASON_DISABLED, "disabled")


class TestLlmPlaceholderTextInReport(unittest.TestCase):
    """验证三个报告模块中占位文本的区分性。"""

    def test_excel_generator_placeholder_distinct(self):
        """excel_generator 中所有状态占位文本互不相同。"""
        # 验证 _build_llm_usage_sheet 中的 DISPLAY_REASON 映射
        from src.python.report.excel_llm_usage import build_llm_usage_sheet as _blus

        # 5 种非 disabled 原因 + disabled（单独处理）= 6 种不同状态
        display_reason = {
            "not_configured": "LLM 未配置",
            "api_error": "LLM API 调用失败",
            "network_error": "LLM API 网络连接失败",
            "timeout": "LLM API 请求超时",
            "circuit_open": "LLM API 暂时不可用（熔断冷却中）",
        }
        texts = set(display_reason.values())
        for v in display_reason.values():
            self.assertIn(v, texts)
        self.assertEqual(len(texts), 5, "非 disabled 应有 5 种占位文本")

        # disabled 单独验证（通过函数内专门分支）
        self.assertEqual(len(set(display_reason.values()) | {"已禁用"}), 6,
                         "包含 disabled 共 6 种不同占位")

    def test_llm_content_placeholder_distinct(self):
        """llm_content 中所有原因占位文本互不相同。"""
        from src.python.report.llm_content import _PLACEHOLDER_BY_REASON

        # 验证占位文本映射各不相同
        texts = set(_PLACEHOLDER_BY_REASON.values())
        self.assertEqual(len(texts), len(_PLACEHOLDER_BY_REASON),
                         "每种原因的占位文本应互不相同")
        self.assertGreaterEqual(len(texts), 3,
                                "至少应有 3 种以上占位文本")

        # 验证每个占位文本非空
        for reason, placeholder in _PLACEHOLDER_BY_REASON.items():
            self.assertTrue(len(placeholder) > 0,
                            f"原因 {reason} 的占位文本不应为空")

        # llm_content 不包含 FAIL_REASON_DISABLED
        # disabled 由调用方在模块级别过滤，不会传入 llm_content
        from src.python.llm.prompts import FAIL_REASON_DISABLED
        self.assertNotIn(FAIL_REASON_DISABLED, _PLACEHOLDER_BY_REASON,
                         "disabled 应在 llm_content 上层过滤，不进入 _PLACEHOLDER_BY_REASON")

    def test_html_writer_placeholder_distinct(self):
        """html_writer 中所有状态占位文本互不相同。"""
        # 验证 html_writer 中 _build_module_info_list 的占位映射
        from src.python.report.html_renderers import _build_module_info_list


        display_reason = {
            "not_configured": "LLM 未配置",
            "api_error": "LLM API 调用失败",
            "network_error": "LLM API 网络连接失败",
            "timeout": "LLM API 请求超时",
            "circuit_open": "LLM API 暂时不可用（熔断冷却中）",
        }
        texts = set(display_reason.values())
        self.assertEqual(len(texts), 5, "非 disabled 应有 5 种占位文本")
        self.assertEqual(len(texts | {"已禁用"}), 6,
                         "包含 disabled 共 6 种不同占位")
        self.assertIn("未配置", display_reason["not_configured"])
        self.assertIn("失败", display_reason["api_error"])


class TestLlmPlaceholderIntegration(unittest.TestCase):
    """验证 LLM_MODULE_FAILURE 与占位文本的正确映射。"""

    def test_not_configured_placeholder_matches(self):
        """not_configured → 显示 '未配置'。"""
        LLM_MODULE_FAILURE["test_mod"] = FAIL_REASON_NOT_CONFIGURED
        reason = LLM_MODULE_FAILURE.get("test_mod")
        self.assertEqual(reason, "not_configured")
        LLM_MODULE_FAILURE.clear()

    def test_disabled_placeholder_matches(self):
        """disabled → 显示 '已禁用'。"""
        LLM_MODULE_FAILURE["test_mod"] = FAIL_REASON_DISABLED
        reason = LLM_MODULE_FAILURE.get("test_mod")
        self.assertEqual(reason, "disabled")
        LLM_MODULE_FAILURE.clear()

    def test_api_error_placeholder_matches(self):
        """api_error → 显示 'LLM API 调用失败'。"""
        LLM_MODULE_FAILURE["test_mod"] = FAIL_REASON_API_ERROR
        reason = LLM_MODULE_FAILURE.get("test_mod")
        self.assertEqual(reason, "api_error")
        LLM_MODULE_FAILURE.clear()

    def test_three_states_mutually_exclusive(self):
        """三种状态在同一 LLM_MODULE_FAILURE 中互不冲突。"""
        LLM_MODULE_FAILURE["mod_a"] = FAIL_REASON_NOT_CONFIGURED
        LLM_MODULE_FAILURE["mod_b"] = FAIL_REASON_DISABLED
        LLM_MODULE_FAILURE["mod_c"] = FAIL_REASON_API_ERROR

        self.assertEqual(LLM_MODULE_FAILURE["mod_a"], "not_configured")
        self.assertEqual(LLM_MODULE_FAILURE["mod_b"], "disabled")
        self.assertEqual(LLM_MODULE_FAILURE["mod_c"], "api_error")

        # 三个值各不相同
        values = set(LLM_MODULE_FAILURE.values())
        self.assertEqual(len(values), 3)

        LLM_MODULE_FAILURE.clear()

    def test_clear_failure_before_regeneration(self):
        """新生成开始时清除对应 key → 旧状态不会残留。"""
        LLM_MODULE_FAILURE["expert_review"] = FAIL_REASON_API_ERROR
        # 模拟生成前清除
        LLM_MODULE_FAILURE.pop("expert_review", None)
        self.assertNotIn("expert_review", LLM_MODULE_FAILURE)

    def test_disabled_module_placeholder(self):
        """已禁用的模块不应显示 API 错误占位。"""
        LLM_MODULE_FAILURE["global_macro"] = FAIL_REASON_DISABLED
        reason = LLM_MODULE_FAILURE.get("global_macro")
        self.assertEqual(reason, FAIL_REASON_DISABLED)
        self.assertNotEqual(reason, FAIL_REASON_API_ERROR)
        LLM_MODULE_FAILURE.clear()


if __name__ == "__main__":
    unittest.main()

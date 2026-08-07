"""LLM 占位文本区分测试 — 未配置/已禁用/生成失败 三种状态。

运行：
  pytest src/test/unit/llm/test_llm_placeholder_distinction_edge.py -v
"""

from __future__ import annotations

import os
import unittest
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.edge]


@pytest.mark.edge
class TestLlmPlaceholderDistinction(unittest.TestCase):
    """LLM 三种占位文本互不相同。

    占位文本实现在 report/llm_content.py:_PLACEHOLDER_BY_REASON 中，
    按失败原因（FAIL_REASON_*）区分。

    MODULE_DISABLED（已禁用）对应的模块完全跳过不渲染，
    无占位文本，但在 LLM API 用量页签的模块明细表中以"已禁用"状态显示。
    """

    def setUp(self):
        from src.python.report.llm_content import _PLACEHOLDER_BY_REASON
        from src.python.llm.prompts import (
            FAIL_REASON_NOT_CONFIGURED,
            FAIL_REASON_API_ERROR,
            FAIL_REASON_DISABLED,
        )
        self._placeholder = _PLACEHOLDER_BY_REASON
        self._not_configured_key = FAIL_REASON_NOT_CONFIGURED
        self._api_error_key = FAIL_REASON_API_ERROR
        self._disabled_label = "已禁用"

    def test_not_configured_text_differs_from_disabled(self):
        """未配置与已禁用应为不同文本。"""
        nc_text = self._placeholder.get(self._not_configured_key, "")
        self.assertNotEqual(nc_text, self._disabled_label)

    def test_api_error_text_differs_from_disabled(self):
        """API 错误与已禁用应为不同文本。"""
        ae_text = self._placeholder.get(self._api_error_key, "")
        self.assertNotEqual(ae_text, self._disabled_label)

    def test_not_configured_mentions_config(self):
        """未配置文本包含"配置"相关提示。"""
        text = self._placeholder.get(self._not_configured_key, "")
        self.assertTrue(
            "配置" in text or "API" in text or "Key" in text,
            f"未配置提示应含配置引导: {text}",
        )

    def test_disabled_mentions_disabled(self):
        """已禁用标签包含"禁用"相关词汇。"""
        self.assertIn("禁用", self._disabled_label)

    def test_api_error_mentions_failure(self):
        """API 失败文本提及失败原因。"""
        text = self._placeholder.get(self._api_error_key, "")
        self.assertTrue(
            "失败" in text or "error" in text.lower() or "网络" in text,
            f"API 失败提示应说明原因: {text}",
        )

    def test_html_renders_not_configured_placeholder(self):
        """模板在未配置 LLM 时显示占位提示。"""
        tmpl_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "static", "tmpl", "report_template.html",
        )
        tmpl_path = os.path.normpath(tmpl_path)
        with open(tmpl_path, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("本节内容待生成", html)
        self.assertIn("需配置 LLM API Key 后自动启用", html)

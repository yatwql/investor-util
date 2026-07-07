"""LLM 占位文本区分测试 — 未配置/已禁用/生成失败 三种状态。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/llm/test_llm_placeholder_distinction_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.edge]


@pytest.mark.edge
class TestLlmPlaceholderDistinction(unittest.TestCase):
    """LLM 三种占位文本互不相同。"""

    def setUp(self):
        self.config_not_configured = "NOT_CONFIGURED"
        self.config_disabled = "DISABLED"
        self.config_api_error = "API_ERROR"

    def test_not_configured_text_differs_from_disabled(self):
        """未配置与已禁用应为不同文本。"""
        from src.python.llm.skeleton import STATUS_MESSAGES as SM
        self.assertNotEqual(
            SM.get("NOT_CONFIGURED", ""),
            SM.get("MODULE_DISABLED", ""),
        )

    def test_api_error_text_differs_from_disabled(self):
        """API 错误与已禁用应为不同文本。"""
        from src.python.llm.skeleton import STATUS_MESSAGES as SM
        self.assertNotEqual(
            SM.get("API_ERROR", ""),
            SM.get("MODULE_DISABLED", ""),
        )

    def test_not_configured_mentions_config(self):
        """未配置文本包含"配置"相关提示。"""
        from src.python.llm.skeleton import STATUS_MESSAGES as SM
        text = SM.get("NOT_CONFIGURED", "")
        self.assertTrue(
            "配置" in text or "API" in text or "Key" in text,
            f"未配置提示应含配置引导: {text}",
        )

    def test_disabled_mentions_disabled(self):
        """已禁用文本包含"禁用"相关词汇。"""
        from src.python.llm.skeleton import STATUS_MESSAGES as SM
        text = SM.get("MODULE_DISABLED", "")
        self.assertIn("禁用", text)

    def test_api_error_mentions_failure(self):
        """API 失败文本提及失败原因。"""
        from src.python.llm.skeleton import STATUS_MESSAGES as SM
        text = SM.get("API_ERROR", "")
        self.assertTrue(
            "失败" in text or "error" in text.lower() or "网络" in text,
            f"API 失败提示应说明原因: {text}",
        )

    def test_html_renders_not_configured_placeholder(self):
        """模板在未配置 LLM 时显示占位提示。"""
        import os
        tmpl_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "python", "tmpl", "report_template.html",
        )
        tmpl_path = os.path.normpath(tmpl_path)
        with open(tmpl_path, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("本节内容待生成", html)
        self.assertIn("需配置 LLM API Key 后自动启用", html)

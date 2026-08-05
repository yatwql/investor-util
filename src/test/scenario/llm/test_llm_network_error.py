"""LLM 场景测试 — 断网下 LLM 模块渲染降级。

网络断开时所有 LLM 模块降级为 NETWORK_ERROR 状态，
HTML 端 _render_llm_module_info 输出 failed 状态文本，不阻塞报告生成。
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack

import pytest
from unittest.mock import patch

from src.python.llm import FAIL_REASON_NETWORK_ERROR

pytestmark = [pytest.mark.llm, pytest.mark.scenario_llm, pytest.mark.scenario]


class TestNetworkErrorHtmlRender(unittest.TestCase):
    """断网场景下 HTML 端 LLM 模块渲染降级。"""

    def test_network_error_placeholder_text(self):
        """_render_llm_module_info：断网 → failed 状态文本正确。"""
        from src.python.report.html_renderers import _render_llm_module_info

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts.LLM_MODULE_FAILURE", {
                "global_macro": FAIL_REASON_NETWORK_ERROR,
                "expert_review": FAIL_REASON_NETWORK_ERROR,
                "health_check": FAIL_REASON_NETWORK_ERROR,
                "penetration_deep": FAIL_REASON_NETWORK_ERROR,
                "news_correlation": FAIL_REASON_NETWORK_ERROR,
            }))
            stack.enter_context(
                patch("src.python.llm.get_session_usage",
                      return_value={"has_usage": False, "per_module": {}}))
            stack.enter_context(
                patch("src.python.llm.format_session_usage",
                      return_value={"has_usage": False}))

            llm_module_info, _, _, _ = _render_llm_module_info(True)

        by_key = {m["key"]: m for m in llm_module_info}
        for key in ("global_macro", "expert_review", "health_check",
                    "penetration_deep", "news_correlation"):
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], "failed")
                self.assertIn("网络连接失败", by_key[key]["status_label"])

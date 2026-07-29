"""LLM 场景 S16：断网下 LLM 生成。

S16：网络断开 → 所有模块降级为 NETWORK_ERROR。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/llm/test_s16_network_error.py -v
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack

import pytest
from unittest.mock import patch

from src.python.llm import FAIL_REASON_NETWORK_ERROR


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS16NetworkDown(unittest.TestCase):
    """S16：网络断开 → 所有模块降级为 NETWORK_ERROR。

    预期：所有 LLM 模块占位文本"LLM API 网络连接失败"，
    不阻塞报告生成，日志记录 NETWORK_ERROR。
    """

    def test_all_network_error(self):
        """_build_module_info_list：全部 NETWORK_ERROR。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "global_macro": FAIL_REASON_NETWORK_ERROR,
            "expert_review": FAIL_REASON_NETWORK_ERROR,
            "health_check": FAIL_REASON_NETWORK_ERROR,
            "penetration_deep": FAIL_REASON_NETWORK_ERROR,
            "news_correlation": FAIL_REASON_NETWORK_ERROR,
        }

        result = build_llm_module_info(failure, {})
        by_key = {m["key"]: m for m in result}

        for key in failure:
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], "failed")
                self.assertEqual(
                    by_key[key]["status_label"],
                    "LLM API 网络连接失败",
                )

    def test_network_error_placeholder_text(self):
        """_render_llm_module_info：断网 -> failed 状态文本正确。"""
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

    def test_s16_console_output_format(self):
        """S16 场景下验证 TUI 摘要输出格式中失败模块数正确。"""
        # 验证 _build_module_info_list 返回 5 个失败模块
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "global_macro": FAIL_REASON_NETWORK_ERROR,
            "expert_review": FAIL_REASON_NETWORK_ERROR,
            "health_check": FAIL_REASON_NETWORK_ERROR,
            "penetration_deep": FAIL_REASON_NETWORK_ERROR,
            "news_correlation": FAIL_REASON_NETWORK_ERROR,
        }
        result = build_llm_module_info(failure, {})

        failed_count = sum(1 for m in result if m["status"] == "failed")
        self.assertEqual(failed_count, 5, "断网时所有 5 个模块应标记为 failed")

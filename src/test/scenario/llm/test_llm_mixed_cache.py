"""LLM 场景 S11：混合缓存+真实调用。

S11：4 模块混合状态 — 2 缓存 + 1 成功 + 1 失败。

运行：
  python -m pytest src/test/scenario/llm/test_llm_mixed_cache.py
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack

import pytest
from unittest.mock import MagicMock, patch

from src.python.llm import FAIL_REASON_API_ERROR, FAIL_REASON_DISABLED


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS11MixedCacheAndRealCall(unittest.TestCase):
    """S11：4 模块混合状态 — 2 缓存 + 1 成功 + 1 失败。

    预期：HTML 表各模块状态正确（蓝"缓存"、绿"成功"、红"LLM API 调用失败"）；
    Excel 明细行颜色/费用/Thinking 正确；Summary 页模块列表正确。
    """

    def test_build_module_info_mixed_states(self):
        """_build_module_info_list：混合状态正确分发。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "penetration_deep": FAIL_REASON_API_ERROR,
        }
        per_module = {
            "global_macro": {
                "model": "deepseek-v4-flash", "cached": True,
                "input_tokens": 0, "output_tokens": 0, "cache_hit_tokens": 500,
                "cost": 0.0, "thinking": False, "endpoint": "",
            },
            "expert_review": {
                "model": "claude-sonnet-4", "cached": False,
                "input_tokens": 2000, "output_tokens": 1000,
                "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
                "endpoint": "",
            },
        }

        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}

        # 2 缓存
        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["global_macro"]["status_label"], "缓存")
        self.assertEqual(by_key["global_macro"]["cache_hit_tokens"], 500)
        self.assertTrue(by_key["global_macro"]["cached"])

        # 1 成功（含 Thinking）
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["expert_review"]["status_label"], "成功")
        self.assertEqual(by_key["expert_review"]["input_tokens"], 2000)
        self.assertEqual(by_key["expert_review"]["output_tokens"], 1000)
        self.assertEqual(by_key["expert_review"]["total_tokens"], 3000)
        self.assertTrue(by_key["expert_review"]["thinking"])

        # 1 失败
        self.assertEqual(by_key["penetration_deep"]["status"], "failed")
        self.assertEqual(by_key["penetration_deep"]["status_label"], "LLM API 调用失败")

        # health_check 和 news_correlation 无数据 → unknown
        self.assertEqual(by_key["health_check"]["status"], "unknown")
        self.assertEqual(by_key["news_correlation"]["status"], "unknown")

    def test_mixed_states_count(self):
        """_build_module_info_list：返回 5 个模块条目。"""
        from src.python.report.llm_module_info import build_llm_module_info
        result = build_llm_module_info({}, {})
        self.assertEqual(len(result), 5)
        keys = [m["key"] for m in result]
        self.assertIn("news_correlation", keys)

    def test_render_llm_mixed_integration(self):
        """_render_llm_module_info + 混合状态：状态正确分发。"""
        from src.python.report.html_renderers import _render_llm_module_info

        session_usage = {
            "has_usage": True, "call_count": 1, "per_module": {
                "global_macro": {
                    "model": "ds", "cached": True,
                    "input_tokens": 0, "output_tokens": 0, "cache_hit_tokens": 300,
                    "cost": 0.0, "thinking": False, "endpoint": "",
                },
                "expert_review": {
                    "model": "claude", "cached": False,
                    "input_tokens": 1500, "output_tokens": 800,
                    "cache_hit_tokens": 0, "cost": 0.005, "thinking": True,
                    "endpoint": "",
                },
            },
        }
        module_failure = {
            "health_check": FAIL_REASON_DISABLED,
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts.LLM_MODULE_FAILURE",
                                      module_failure))
            stack.enter_context(
                patch("src.python.llm.get_session_usage", return_value=session_usage))
            stack.enter_context(
                patch("src.python.llm.format_session_usage", return_value=session_usage))

            llm_module_info, llm_endpoint, module_disabled, llm_session_usage = \
                _render_llm_module_info(True)

        by_key = {m["key"]: m for m in llm_module_info}
        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["health_check"]["status"], "disabled")
        self.assertEqual(by_key["penetration_deep"]["status"], "unknown")
        self.assertEqual(by_key["news_correlation"]["status"], "unknown")

        # module_disabled dict
        self.assertTrue(module_disabled["health_check"])
        self.assertFalse(module_disabled["global_macro"])
        self.assertFalse(module_disabled["expert_review"])
        self.assertFalse(module_disabled["penetration_deep"])

        # llm_session_usage 应有值
        self.assertIsNotNone(llm_session_usage)
        self.assertTrue(llm_session_usage["has_usage"])

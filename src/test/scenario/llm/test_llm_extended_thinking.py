"""LLM 场景 S13：Extended Thinking 混合。

S13：2 模块有 Thinking + 2 模块无 Thinking。

运行：
  python -m pytest src/test/scenario/llm/test_llm_extended_thinking.py
"""

from __future__ import annotations

import unittest

import pytest


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS13ThinkingMixed(unittest.TestCase):
    """S13：2 模块有 Thinking + 2 模块无 Thinking。

    预期：Thinking 列 ✓ 仅出现在启用的模块行，
    Excel/HTML/Summary 三种输出一致。
    """

    def test_thinking_mixed(self):
        """_build_module_info_list：Thinking 标记正确。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "global_macro": {
                "model": "ds", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": True,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 200, "output_tokens": 100,
                "cache_hit_tokens": 0, "cost": 0.002, "thinking": True,
                "endpoint": "",
            },
            "health_check": {
                "model": "gpt4", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 300, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "penetration_deep": {
                "model": "ds", "cached": False,
                "input_tokens": 300, "output_tokens": 150,
                "cache_hit_tokens": 0, "cost": 0.003, "thinking": False,
                "endpoint": "",
            },
        }

        result = build_llm_module_info({}, per_module)
        by_key = {m["key"]: m for m in result}

        # global_macro + Thinking
        self.assertTrue(by_key["global_macro"]["thinking"])
        # expert_review + Thinking
        self.assertTrue(by_key["expert_review"]["thinking"])
        # health_check 缓存 → thinking=False（缓存不考虑 thinking）
        self.assertFalse(by_key["health_check"]["thinking"])
        # penetration_deep → thinking=False
        self.assertFalse(by_key["penetration_deep"]["thinking"])

        # news_correlation 无 per_module → 默认 no thinking
        self.assertFalse(by_key["news_correlation"]["thinking"])

    def test_thinking_true_count(self):
        """Thinking=True 恰好 2 个（global_macro + expert_review）。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "global_macro": {
                "model": "ds", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": True,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 200, "output_tokens": 100,
                "cache_hit_tokens": 0, "cost": 0.002, "thinking": True,
                "endpoint": "",
            },
        }

        result = build_llm_module_info({}, per_module)
        thinking_count = sum(1 for m in result if m["thinking"])
        self.assertEqual(thinking_count, 2)

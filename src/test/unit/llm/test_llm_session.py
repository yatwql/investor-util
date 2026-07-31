"""LLM Session 会话统计模块单元测试。

测试目标：
  - track_session_usage / format_session_usage / record_per_module

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test.unit.llm.test_llm_session -v
"""

from __future__ import annotations

import unittest

import pytest

from src.python.llm import (
    format_session_usage,
    get_session_usage,
)
from src.python.llm.session import (
    record_per_module,
    reset_session_usage,
    _session_usage,
    track_session_usage,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


# ═══════════════════════════════════════════════════════════
#  Session — track_session_usage / format_session_usage / record_per_module
# ═══════════════════════════════════════════════════════════


class TestSession(unittest.TestCase):
    """测试 LLM 会话统计模块。"""

    def setUp(self) -> None:
        reset_session_usage()

    def test_reset_clears_all(self) -> None:
        """reset_session_usage 应清零所有累计。"""
        track_session_usage("claude", {"input_tokens": 100, "output_tokens": 50}, "claude-sonnet-4-6")
        reset_session_usage()
        usage = get_session_usage()
        self.assertEqual(usage["input_tokens"], 0)
        self.assertEqual(usage["output_tokens"], 0)
        self.assertEqual(usage["call_count"], 0)

    def test_track_claude_usage(self) -> None:
        """Claude 格式的用量应正确累计。"""
        track_session_usage("claude", {"input_tokens": 200, "output_tokens": 100,
                                        "cache_read_input_tokens": 50}, "claude-sonnet-4-6")
        usage = get_session_usage()
        self.assertEqual(usage["input_tokens"], 200)
        self.assertEqual(usage["output_tokens"], 100)
        self.assertEqual(usage["cache_hit_tokens"], 50)
        self.assertEqual(usage["call_count"], 1)
        self.assertEqual(usage["model"], "claude-sonnet-4-6")

    def test_track_openai_usage(self) -> None:
        """OpenAI 格式的用量应正确累计。"""
        track_session_usage("openai", {"prompt_tokens": 150, "completion_tokens": 75}, "gpt-4o")
        usage = get_session_usage()
        self.assertEqual(usage["input_tokens"], 150)
        self.assertEqual(usage["output_tokens"], 75)

    def test_track_none_usage_no_op(self) -> None:
        """None 用量不应改变累计值。"""
        track_session_usage("claude", None)
        usage = get_session_usage()
        self.assertEqual(usage["call_count"], 0)

    def test_get_session_usage_returns_copy(self) -> None:
        """get_session_usage 应返回副本而非引用。"""
        usage = get_session_usage()
        usage["input_tokens"] = 999
        self.assertEqual(_session_usage["input_tokens"], 0)

    def test_track_multiple_calls_accumulate(self) -> None:
        """多次调用应正确累加。"""
        for _ in range(5):
            track_session_usage("claude", {"input_tokens": 100, "output_tokens": 50})
        usage = get_session_usage()
        self.assertEqual(usage["input_tokens"], 500)
        self.assertEqual(usage["output_tokens"], 250)
        self.assertEqual(usage["call_count"], 5)

    def testrecord_per_module(self) -> None:
        """record_per_module 应记录模块级用量。"""
        record_per_module("global_macro", "deepseek-v4-flash", inp=100, out=50)
        record_per_module("expert_review", "deepseek-v4-flash", inp=200, out=100)
        usage = get_session_usage()
        self.assertIn("global_macro", usage["per_module"])
        self.assertIn("expert_review", usage["per_module"])
        self.assertEqual(usage["per_module"]["global_macro"]["input_tokens"], 100)
        self.assertEqual(usage["per_module"]["expert_review"]["output_tokens"], 100)

    def testrecord_per_module_accumulate(self) -> None:
        """同一模块多次记录应累加 token。"""
        record_per_module("global_macro", "deepseek-v4-flash", inp=100, out=50)
        record_per_module("global_macro", "deepseek-v4-flash", inp=50, out=25)
        self.assertEqual(_session_usage["per_module"]["global_macro"]["input_tokens"], 150)

    def test_format_session_usage_no_data(self) -> None:
        """无数据时应返回 has_usage=False。"""
        result = format_session_usage(None)
        self.assertFalse(result["has_usage"])
        result = format_session_usage({})
        self.assertFalse(result["has_usage"])

    def test_format_session_usage_with_data(self) -> None:
        """有数据时应正确格式化。"""
        track_session_usage("claude", {"input_tokens": 1000, "output_tokens": 500}, "deepseek-v4-flash")
        raw = get_session_usage()
        result = format_session_usage(raw)
        self.assertTrue(result["has_usage"])
        self.assertEqual(result["call_count"], 1)
        self.assertEqual(result["total_tokens"], 1500)
        self.assertIn("cost_display", result)

    def testtrack_session_usage_models_dedup(self) -> None:
        """多次使用同一模型应去重。"""
        track_session_usage("claude", {"input_tokens": 100, "output_tokens": 50}, "deepseek-v4-flash")
        track_session_usage("claude", {"input_tokens": 200, "output_tokens": 100}, "deepseek-v4-flash")
        self.assertEqual(len(_session_usage["models"]), 1)

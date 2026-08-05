"""LLM 会话统计模块单元测试。

测试目标：
  - reset_session_usage — 重置所有累计量
  - get_session_usage — 返回副本不泄漏内部引用
  - format_session_usage — 格式化正确
  - track_session_usage — 跨 provider 的 Token 累计
  - record_per_module — 模块级用量记录

运行：
  pytest src/test/unit/llm/test_llm_session_usage.py -v
"""

from __future__ import annotations

import unittest

from src.python.llm.session import (

    _session_usage,
    _session_lock,
    get_session_usage,
    reset_session_usage,
    format_session_usage,
    track_session_usage,
    record_per_module,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]



def _reset_safe():
    """线程安全重置（测试用）。"""
    with _session_lock:
        _session_usage["input_tokens"] = 0
        _session_usage["output_tokens"] = 0
        _session_usage["cache_hit_tokens"] = 0
        _session_usage["total_cost"] = 0.0
        _session_usage["call_count"] = 0
        _session_usage["per_module"] = {}
        _session_usage["models"] = []


class TestResetSessionUsage(unittest.TestCase):
    """重置会话累计用量。"""

    def setUp(self):
        _reset_safe()
        # 先塞一些数据
        with _session_lock:
            _session_usage["input_tokens"] = 100
            _session_usage["output_tokens"] = 50
            _session_usage["call_count"] = 2
            _session_usage["models"] = ["claude-sonnet-4-6"]

    def test_reset_zeros_input_tokens(self):
        """reset 后 input_tokens 归零。"""
        reset_session_usage()
        self.assertEqual(_session_usage["input_tokens"], 0)

    def test_reset_zeros_output_tokens(self):
        """reset 后 output_tokens 归零。"""
        reset_session_usage()
        self.assertEqual(_session_usage["output_tokens"], 0)

    def test_reset_zeros_call_count(self):
        """reset 后 call_count 归零。"""
        reset_session_usage()
        self.assertEqual(_session_usage["call_count"], 0)

    def test_reset_clears_models(self):
        """reset 后 models 清空。"""
        reset_session_usage()
        self.assertEqual(_session_usage["models"], [])

    def test_reset_clears_per_module(self):
        """reset 后 per_module 清空。"""
        with _session_lock:
            _session_usage["per_module"] = {"test": {"model": "x"}}
        reset_session_usage()
        self.assertEqual(_session_usage["per_module"], {})

    def test_reset_total_cost(self):
        """reset 后 total_cost 归零。"""
        with _session_lock:
            _session_usage["total_cost"] = 1.23
        reset_session_usage()
        self.assertEqual(_session_usage["total_cost"], 0.0)


class TestGetSessionUsage(unittest.TestCase):
    """获取会话累计用量副本。"""

    def setUp(self):
        _reset_safe()

    def test_get_returns_copy(self):
        """get 返回 dict 而非内部引用。"""
        usage = get_session_usage()
        usage["input_tokens"] = 999
        self.assertNotEqual(_session_usage["input_tokens"], 999)

    def test_get_returns_current_values(self):
        """get 正确反映当前累计值。"""
        with _session_lock:
            _session_usage["call_count"] = 5
        usage = get_session_usage()
        self.assertEqual(usage["call_count"], 5)

    def test_get_has_all_keys(self):
        """get 返回的 dict 包含所有必要键。"""
        usage = get_session_usage()
        for key in ("input_tokens", "output_tokens", "cache_hit_tokens",
                     "total_cost", "call_count", "per_module", "models"):
            self.assertIn(key, usage)


class TestFormatSessionUsage(unittest.TestCase):
    """格式化会话用量。"""

    def setUp(self):
        _reset_safe()

    def test_none_returns_no_usage(self):
        """传入 None → has_usage=False。"""
        result = format_session_usage(None)
        self.assertFalse(result["has_usage"])

    def test_empty_returns_no_usage(self):
        """空 dict → has_usage=False。"""
        result = format_session_usage({})
        self.assertFalse(result["has_usage"])

    def test_zero_calls_no_per_module_returns_no_usage(self):
        """call_count=0 且无 per_module → has_usage=False。"""
        result = format_session_usage({"call_count": 0})
        self.assertFalse(result["has_usage"])

    def test_zero_calls_with_per_module_shows_usage(self):
        """call_count=0 但有 per_module → has_usage=True（全缓存场景）。"""
        result = format_session_usage({
            "call_count": 0,
            "per_module": {"global_macro": {"model": "x"}},
        })
        self.assertTrue(result["has_usage"])

    def test_with_calls_returns_has_usage_true(self):
        """有调用次数 → has_usage=True。"""
        result = format_session_usage({"call_count": 3})
        self.assertTrue(result["has_usage"])

    def test_total_tokens_is_sum(self):
        """total_tokens = input + output。"""
        result = format_session_usage({
            "call_count": 1,
            "input_tokens": 100,
            "output_tokens": 50,
        })
        self.assertEqual(result["total_tokens"], 150)

    def test_cache_hit_tokens_preserved(self):
        """cache_hit_tokens 原样传入。"""
        result = format_session_usage({
            "call_count": 1,
            "cache_hit_tokens": 200,
        })
        self.assertEqual(result["cache_hit_tokens"], 200)

    def test_cost_display_format(self):
        """cost_display 包含货币符号。"""
        result = format_session_usage({
            "call_count": 1,
            "total_cost": 0.0456,
            "currency": "CNY",
        })
        self.assertIn("¥", result["cost_display"])
        self.assertIn("0.0456", result["cost_display"])

    def test_model_display_single(self):
        """单模型时 model_display 等于 model。"""
        result = format_session_usage({
            "call_count": 1,
            "model": "claude-sonnet-4-6",
        })
        self.assertEqual(result["model_display"], "claude-sonnet-4-6")

    def test_model_display_multiple_joined(self):
        """多模型时 model_display 用 / 连接。"""
        result = format_session_usage({
            "call_count": 2,
            "models": ["claude-sonnet-4-6", "deepseek-v4-flash"],
        })
        self.assertIn("/", result["model_display"])


class TestTrackSessionUsage(unittest.TestCase):
    """单次 LLM 用量累计。"""

    def setUp(self):
        _reset_safe()

    def test_none_usage_ignored(self):
        """usage 为 None → 不做任何累加。"""
        track_session_usage("claude", None)
        self.assertEqual(_session_usage["call_count"], 0)

    def test_claude_provider_tokens(self):
        """claude provider 使用 input_tokens / output_tokens。"""
        track_session_usage("claude", {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_input_tokens": 5,
        })
        self.assertEqual(_session_usage["input_tokens"], 10)
        self.assertEqual(_session_usage["output_tokens"], 20)
        self.assertEqual(_session_usage["cache_hit_tokens"], 5)
        self.assertEqual(_session_usage["call_count"], 1)

    def test_openai_provider_tokens(self):
        """openai provider 使用 prompt_tokens / completion_tokens。"""
        track_session_usage("openai", {
            "prompt_tokens": 30,
            "completion_tokens": 40,
        })
        self.assertEqual(_session_usage["input_tokens"], 30)
        self.assertEqual(_session_usage["output_tokens"], 40)
        self.assertEqual(_session_usage["cache_hit_tokens"], 0)

    def test_call_count_increments(self):
        """多次调用累加 call_count。"""
        for _ in range(3):
            track_session_usage("claude", {"input_tokens": 1, "output_tokens": 1})
        self.assertEqual(_session_usage["call_count"], 3)

    def test_model_name_tracked(self):
        """传入 model_name 累计到 models 列表。"""
        track_session_usage("claude", {"input_tokens": 1, "output_tokens": 1},
                             model_name="claude-sonnet-4-6")
        self.assertIn("claude-sonnet-4-6", _session_usage["models"])

    def test_model_name_dedup(self):
        """相同 model_name 不重复添加。"""
        for _ in range(2):
            track_session_usage("claude", {"input_tokens": 1, "output_tokens": 1},
                                 model_name="claude-sonnet-4-6")
        self.assertEqual(len(_session_usage["models"]), 1)


class TestRecordPerModule(unittest.TestCase):
    """模块级用量记录。"""

    def setUp(self):
        _reset_safe()

    def test_record_creates_entry(self):
        """首次记录创建模块条目。"""
        record_per_module("global_macro", "claude-sonnet-4-6",
                           inp=100, out=50, cost=0.01)
        pm = _session_usage["per_module"]
        self.assertIn("global_macro", pm)
        entry = pm["global_macro"]
        self.assertEqual(entry["input_tokens"], 100)
        self.assertEqual(entry["output_tokens"], 50)
        self.assertEqual(entry["cost"], 0.01)

    def test_record_accumulates(self):
        """多次记录同一模块累加 Token 和费用。"""
        record_per_module("global_macro", "claude-sonnet-4-6",
                           inp=100, out=50, cost=0.01)
        record_per_module("global_macro", "claude-sonnet-4-6",
                           inp=200, out=30, cost=0.02)
        entry = _session_usage["per_module"]["global_macro"]
        self.assertEqual(entry["input_tokens"], 300)
        self.assertEqual(entry["output_tokens"], 80)
        self.assertEqual(entry["cost"], 0.03)

    def test_cached_flag_persists(self):
        """cached=True 后保持 True。"""
        record_per_module("test_mod", "m", inp=1, out=1, cached=True)
        self.assertTrue(_session_usage["per_module"]["test_mod"]["cached"])

    def test_thinking_flag_persists(self):
        """thinking=True 后保持 True。"""
        record_per_module("test_mod", "m", inp=1, out=1, thinking=True)
        self.assertTrue(_session_usage["per_module"]["test_mod"]["thinking"])

    def test_endpoint_recorded(self):
        """endpoint 被记录。"""
        record_per_module("test_mod", "m", inp=1, out=1, endpoint="https://api.test")
        self.assertEqual(
            _session_usage["per_module"]["test_mod"]["endpoint"],
            "https://api.test",
        )

    def test_cache_hit_tokens_accumulated(self):
        """cache_hit_tokens 累加。"""
        record_per_module("test_mod", "m", inp=1, out=1, cache_hit_tokens=50)
        record_per_module("test_mod", "m", inp=1, out=1, cache_hit_tokens=30)
        self.assertEqual(
            _session_usage["per_module"]["test_mod"]["cache_hit_tokens"], 80)

    def test_multiple_modules_independent(self):
        """多个模块独立累计。"""
        record_per_module("mod_a", "m1", inp=100, out=10)
        record_per_module("mod_b", "m2", inp=200, out=20)
        self.assertEqual(_session_usage["per_module"]["mod_a"]["input_tokens"], 100)
        self.assertEqual(_session_usage["per_module"]["mod_b"]["input_tokens"], 200)

    def test_model_added_to_models_list(self):
        """传入 model_name 自动添加到全局 models 列表。"""
        record_per_module("mod", "claude-opus-4-8", inp=1, out=1)
        self.assertIn("claude-opus-4-8", _session_usage["models"])

    def test_model_dedup_in_models_list(self):
        """相同模型不重复添加到 models。"""
        record_per_module("mod_a", "claude-sonnet-4-6", inp=1, out=1)
        record_per_module("mod_b", "claude-sonnet-4-6", inp=1, out=1)
        self.assertEqual(len(_session_usage["models"]), 1)


if __name__ == "__main__":
    unittest.main()

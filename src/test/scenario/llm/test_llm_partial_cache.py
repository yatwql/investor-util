"""LLM 场景 S17：部分缓存超期 + 全缓存。

S17：部分模块缓存超期（过期模块重新调用，未过期命中缓存）。
S17a：全部模块缓存命中，无 API 调用。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/llm/test_llm_partial_cache.py
"""

from __future__ import annotations

import unittest

import pytest


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS17PartialCacheExpiry(unittest.TestCase):
    """S17：部分模块缓存超期。

    预期：过期模块重新调用 API（显示 Token 和费用），
    未过期模块显示"缓存"状态，费用为 0。
    """

    def test_partial_cache_hit(self):
        """_build_module_info_list：部分缓存 + 部分成功。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 1000, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 3000, "output_tokens": 1500,
                "cache_hit_tokens": 0, "cost": 0.015, "thinking": True,
                "endpoint": "",
            },
        }

        result = build_llm_module_info({}, per_module)
        by_key = {m["key"]: m for m in result}

        # 缓存
        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["global_macro"]["cost"], 0.0)
        self.assertEqual(by_key["global_macro"]["cache_hit_tokens"], 1000)
        self.assertTrue(by_key["global_macro"]["cached"])

        # 成功（重新调用）
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["expert_review"]["input_tokens"], 3000)
        self.assertEqual(by_key["expert_review"]["output_tokens"], 1500)
        self.assertEqual(by_key["expert_review"]["total_tokens"], 4500)
        self.assertEqual(by_key["expert_review"]["cost"], 0.015)
        self.assertFalse(by_key["expert_review"]["cached"])

        # 无 per_module → unknown
        self.assertEqual(by_key["health_check"]["status"], "unknown")
        self.assertEqual(by_key["penetration_deep"]["status"], "unknown")

    def test_session_usage_correctly_reports_mixed_cache(self):
        """阶段性验证：format_session_usage 在混合场景下正确反映 call_count。"""
        from src.python.llm import get_session_usage, format_session_usage
        from src.python.llm.session import reset_session_usage
        from src.python.llm.session import track_session_usage, record_per_module

        reset_session_usage()

        # 模拟 S17: 2 模块缓存 + 1 模块成功（过期重新调用）
        record_per_module("global_macro", "ds", inp=0, out=0, cached=True,
                           cache_hit_tokens=1000)
        record_per_module("health_check", "gpt4", inp=0, out=0, cached=True,
                           cache_hit_tokens=500)
        track_session_usage("claude",
                             {"input_tokens": 2000, "output_tokens": 1000},
                             "claude-sonnet-4")
        record_per_module("expert_review", "claude-sonnet-4",
                           inp=2000, out=1000, cached=False)

        raw = get_session_usage()
        formatted = format_session_usage(raw)

        self.assertTrue(formatted["has_usage"])
        # 只有 1 次真实 API 调用，2 次缓存
        self.assertEqual(formatted["call_count"], 1)
        # 总 token = 真实调用 token（缓存模块 token=0）
        self.assertEqual(formatted["total_tokens"], 3000)

        per_module = raw["per_module"]
        self.assertTrue(per_module["global_macro"]["cached"])
        self.assertTrue(per_module["health_check"]["cached"])
        self.assertFalse(per_module["expert_review"]["cached"])

        reset_session_usage()


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS17aFullCache(unittest.TestCase):
    """S17：全部模块缓存命中，无 API 调用。

    预期：module_info 全部 cached，无失败/成功条目。
    """

    def test_all_cache_hit(self):
        """_build_module_info_list：全部缓存命中。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 300, "cost": 0.0, "thinking": True,
                "endpoint": "",
            },
            "health_check": {
                "model": "gpt4", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 200, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "penetration_deep": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 400, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "news_correlation": {
                "model": "claude", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 600, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
        }

        result = build_llm_module_info({}, per_module)
        by_key = {m["key"]: m for m in result}

        for key in per_module:
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], "cached")
                self.assertTrue(by_key[key]["cached"])
                self.assertEqual(by_key[key]["cost"], 0.0)

"""LLM 场景 S15：禁用+缓存混合（禁用优先）。

S15：1 禁用 + 1 缓存 + 1 成功 → 禁用优先原则。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/llm/test_s15_disabled_cache.py -v
"""

from __future__ import annotations

import unittest

import pytest

from src.python.llm import FAIL_REASON_DISABLED


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS15DisabledPriority(unittest.TestCase):
    """S15：1 禁用 + 1 缓存 + 1 成功 → 禁用优先原则。

    预期：禁用模块显示"已禁用"（灰色），即使该模块有缓存或 per_module 数据。
    """

    def test_disabled_overrides_per_module(self):
        """FAIL_REASON_DISABLED 优先于 per_module 数据。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "health_check": FAIL_REASON_DISABLED,
        }
        # health_check 在 per_module 中也有数据，但应被禁用覆盖
        per_module = {
            "health_check": {
                "model": "ds", "cached": False,
                "input_tokens": 500, "output_tokens": 300,
                "cache_hit_tokens": 0, "cost": 0.002, "thinking": False,
                "endpoint": "",
            },
        }

        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}

        # 禁用优先 → 显示 disabled
        self.assertEqual(by_key["health_check"]["status"], "disabled")
        self.assertEqual(by_key["health_check"]["status_label"], "已禁用")
        # 禁用时 model 应为空（不显示原始模型）
        self.assertEqual(by_key["health_check"]["model"], "")
        # 禁用时费用为 0
        self.assertEqual(by_key["health_check"]["cost"], 0.0)
        # 禁用时 cached=False
        self.assertFalse(by_key["health_check"]["cached"])

    def test_disabled_overrides_cached(self):
        """禁用优先于缓存状态。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "health_check": FAIL_REASON_DISABLED,
        }
        per_module = {
            "health_check": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
        }

        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["health_check"]["status"], "disabled")
        self.assertEqual(by_key["health_check"]["status_label"], "已禁用")
        # 禁用时不应显示缓存标记
        self.assertFalse(by_key["health_check"]["cached"])

    def test_disabled_alone_no_per_module(self):
        """仅禁用无 per_module → 正确显示 disabled。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {"global_macro": FAIL_REASON_DISABLED}
        result = build_llm_module_info(failure, {})
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["status"], "disabled")
        self.assertEqual(by_key["global_macro"]["status_label"], "已禁用")

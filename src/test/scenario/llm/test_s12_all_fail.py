"""LLM 场景 S12：全部失败（5 种原因）。

S12：5 种失败原因全量覆盖。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/llm/test_s12_all_fail.py -v
"""

from __future__ import annotations

import unittest

import pytest

from src.python.llm import (
    FAIL_REASON_API_ERROR,
    FAIL_REASON_CIRCUIT_OPEN,
    FAIL_REASON_DISABLED,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_TIMEOUT,
)


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS12AllFailures(unittest.TestCase):
    """S12：5 种失败原因全量覆盖。

    预期：各模块分别显示 NOT_CONFIGURED / API_ERROR / NETWORK_ERROR /
    TIMEOUT / CIRCUIT_OPEN，颜色均为灰色/红色。
    """

    def test_all_five_failure_reasons(self):
        """_build_module_info_list：5 种失败原因正确映射。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "global_macro": FAIL_REASON_NOT_CONFIGURED,
            "expert_review": FAIL_REASON_API_ERROR,
            "health_check": FAIL_REASON_NETWORK_ERROR,
            "penetration_deep": FAIL_REASON_TIMEOUT,
            "news_correlation": FAIL_REASON_CIRCUIT_OPEN,
        }

        result = build_llm_module_info(failure, {})
        by_key = {m["key"]: m for m in result}

        expected = {
            "global_macro": ("failed", "LLM 未配置"),
            "expert_review": ("failed", "LLM API 调用失败"),
            "health_check": ("failed", "LLM API 网络连接失败"),
            "penetration_deep": ("failed", "LLM API 请求超时"),
            "news_correlation": ("failed", "LLM API 暂时不可用（熔断冷却中）"),
        }

        for key, (exp_status, exp_label) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], exp_status,
                                 f"{key} 状态应为 {exp_status}")
                self.assertEqual(by_key[key]["status_label"], exp_label,
                                 f"{key} 标签应为 {exp_label}")
                self.assertEqual(by_key[key]["model"], "")
                self.assertEqual(by_key[key]["cost"], 0.0)

    def test_all_failed_no_per_module(self):
        """全部失败 + 无 per_module → 全部 failed，无成功/缓存覆盖。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "global_macro": FAIL_REASON_API_ERROR,
            "expert_review": FAIL_REASON_API_ERROR,
            "health_check": FAIL_REASON_API_ERROR,
            "penetration_deep": FAIL_REASON_TIMEOUT,
            "news_correlation": FAIL_REASON_CIRCUIT_OPEN,
        }
        # 即使 per_module 有数据，failure 优先覆盖
        per_module = {
            "global_macro": {
                "model": "test", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": False,
                "endpoint": "",
            },
        }

        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}

        # 即使 global_macro 在 per_module 中有数据，failure 优先
        self.assertEqual(by_key["global_macro"]["status"], "failed")
        self.assertEqual(by_key["global_macro"]["status_label"], "LLM API 调用失败")
        # 失败时 model 应为空
        self.assertEqual(by_key["global_macro"]["model"], "")

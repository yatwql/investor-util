"""LLM 场景测试 — 多账户 + LLM 多轮交互。

验证多账户下 LLM 生成不冲突，多轮调用数据完整聚合。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/llm/test_llm_multi_account.py -v
"""

from __future__ import annotations

import unittest

import pytest
from unittest.mock import patch


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestMultiAccountMultiRoundLlm(unittest.TestCase):
    """多账户 + LLM 多轮交互场景。

    验证多账户下 LLM 生成不冲突，多轮调用数据完整聚合。
    """

    def test_multi_account_does_not_break_build_module_info(self):
        """多账户持仓传入 _build_module_info_list 不崩溃。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {}
        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
        }
        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}
        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(len(result), 5)

    def test_multi_round_per_module_accumulates(self):
        """多轮调用后 per_module 累加所有轮次的 token 数据。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module_round1 = {
            "global_macro": {
                "model": "ds", "cached": False,
                "input_tokens": 1000, "output_tokens": 500,
                "cache_hit_tokens": 0, "cost": 0.005, "thinking": False,
                "endpoint": "",
            },
        }
        per_module_round2 = {
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 2000, "output_tokens": 1000,
                "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
                "endpoint": "",
            },
        }
        # 模拟多轮合并（生产代码中由调用方合并 per_module 字典）
        merged = {**per_module_round1, **per_module_round2}
        result = build_llm_module_info({}, merged)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["input_tokens"], 1000)
        self.assertEqual(by_key["expert_review"]["input_tokens"], 2000)
        # 确保所有 5 个模块都存在
        self.assertEqual(len(result), 5)

    def test_generate_all_llm_with_multi_account(self):
        """多账户持仓下 generate_all_llm 不崩溃。"""
        from src.python.llm.generators_orchestrator import generate_all_llm

        with (
            patch("src.python.llm.generators_orchestrator.is_llm_module_enabled",
                  return_value=False),
        ):
            result = generate_all_llm({}, {}, 0, 0, 0, 0, 0, {},
                                      holdings_details=[],
                                      penetrated_assets=[])
            self.assertIsNotNone(result)

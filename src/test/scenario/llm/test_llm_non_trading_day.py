"""LLM 场景测试 — 非交易日 LLM 行为。

验证非交易日生成含 LLM 的报告时，LLM 模块不受市场状态影响。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/llm/test_llm_non_trading_day.py -v
"""

from __future__ import annotations

import unittest

import pytest
from unittest.mock import patch

from src.python.llm import FAIL_REASON_NETWORK_ERROR


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestNonTradingDayWithLlm(unittest.TestCase):
    """非交易日生成含 LLM 的报告。

    LLM 模块状态不受市场状态影响，非交易日下应正常显示。
    """

    def test_llm_module_info_independent_of_market_state(self):
        """_build_module_info_list 不依赖市场状态，非交易日照常调用。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {"penetration_deep": FAIL_REASON_NETWORK_ERROR}
        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 2000, "output_tokens": 1000,
                "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
                "endpoint": "",
            },
        }
        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["penetration_deep"]["status_label"], "LLM API 网络连接失败")
        self.assertEqual(by_key["health_check"]["status"], "unknown")
        self.assertEqual(by_key["news_correlation"]["status"], "unknown")

    def test_non_trading_day_no_llm_crash(self):
        """非交易日下 generate_all_llm 不应崩溃。"""
        from src.python.llm.generators_orchestrator import generate_all_llm

        with (
            patch("src.python.llm.generators_orchestrator.is_llm_module_enabled",
                  return_value=False),
        ):
            result = generate_all_llm({}, {}, 0, 0, 0, 0, 0, {},
                                      holdings_details=[],
                                      penetrated_assets=[])
            self.assertIsNotNone(result)

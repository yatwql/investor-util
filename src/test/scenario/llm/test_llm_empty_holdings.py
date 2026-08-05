"""LLM 场景测试 — 空持仓下 LLM 降级。

验证空持仓时所有 LLM 模块应正常跳过/占位，不崩溃。

运行：
  python -m pytest src/test/scenario/llm/test_llm_empty_holdings.py -v
"""

from __future__ import annotations

import unittest

import pytest
from unittest.mock import MagicMock, patch

from src.test.helpers import SynchronousExecutor


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestEmptyHoldingsWithLlm(unittest.TestCase):
    """空持仓下 LLM 生成的降级行为。

    预期：无持仓时所有 LLM 模块应正常跳过/占位，不崩溃；
    holdings_count=0 时 generate_all_llm 不抛出异常。
    """

    @classmethod
    def setUpClass(cls):
        cls._cfg_patcher = patch("src.python.llm.generators_orchestrator.get_llm_config",
                                  return_value={"enabled_llm": {
                                      "global_macro": True,
                                      "expert_review": True,
                                      "health_check": True,
                                      "penetration_deep": True,
                                  }})
        cls._cfg_patcher.start()
        cls._exec_patcher = patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators_orchestrator.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
        cls._cfg_patcher.stop()

    @patch("src.python.llm.generators_orchestrator.generate_penetration_deep_analysis")
    @patch("src.python.llm.generators_orchestrator.generate_health_check")
    @patch("src.python.llm.generators_orchestrator.generate_global_macro")
    @patch("src.python.llm.generators_orchestrator.generate_expert_review")
    def test_empty_holdings_no_crash(
        self, mock_expert, mock_macro, mock_health, mock_penetration,
    ):
        """holdings_count=0 + categories={} → 不会崩溃。"""
        from src.python.llm import generate_all_llm

        mock_macro.return_value = ("<p>空持仓</p>", False)
        mock_expert.return_value = ("<p>空复盘</p>", False)
        mock_health.return_value = ("<p>空体检</p>", False)
        mock_penetration.return_value = ("<p>空穿透</p>", False)

        try:
            result = generate_all_llm(
                {}, {}, 0, 0, 0, 0, 0, {},
                holdings_details=[], penetrated_assets=[],
            )
        except Exception as e:
            self.fail(f"generate_all_llm 在空持仓下不应崩溃: {e}")

        # 依次取各模块输出，不依赖是否含辩论模式末位元素
        macro = result[0]
        expert = result[1]
        health = result[2]
        pen = result[3]
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)

    @patch("src.python.llm.generators._build_global_macro_prompt")
    def test_global_macro_zero_values(self, mock_prompt):
        """generate_global_macro 在 categories={} 时不应崩溃。"""
        from src.python.llm.generators import generate_global_macro

        mock_prompt.return_value = "空持仓 prompt"
        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.return_value = ("<p>宏观</p>", False)
            try:
                result, cached = generate_global_macro({}, {}, 0, 0, 0, {},
                                                        force=True)
            except Exception as e:
                self.fail(f"空持仓下 generate_global_macro 不应崩溃: {e}")
            self.assertEqual(result, "<p>宏观</p>")

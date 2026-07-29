"""辩论模式条件推理单元测试 — Mode 2 情景分析注入。

测试 _build_expert_review_prompt() 在 enable_conditional 参数下的行为：
  - 多情景注入
  - 空情景/禁用的对比
  - 单情景

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/llm/test_debate_conditional.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


def _make_minimal_holdings() -> list[dict]:
    """构造最小持仓明细（满足 _format_holdings_block 字段要求）。"""
    return [
        {
            "code": "600900",
            "market_value": 50_000,
            "profit": 5_000,
            "profit_rate": 10.0,
            "source_api": "tencent",
            "name": "长江电力",
            "change_pct": 0.5,
        },
    ]


def _mock_llm_config_with_scenarios(scenarios: list[dict]) -> dict:
    """构造带指定 scenarios 的 mock LLM 配置。"""
    return {
        "debate": {
            "conditional": {
                "scenarios": scenarios,
            },
        },
    }


@pytest.mark.unit_llm
class TestDebateConditionalMode2(unittest.TestCase):
    """_build_expert_review_prompt enable_conditional 条件推理情景注入。"""

    # ── test 1: Mode 2 启用 + 3 情景 ──────────────────────────

    @patch("src.python.config._core.get_llm_config")
    def test_mode2_enabled_3_scenarios(self, mock_get_llm_config):
        """Mode 2 启用 + 3 情景 → prompt 末尾出现 3 段情景指令，含 '+20%'。"""
        mock_get_llm_config.return_value = _mock_llm_config_with_scenarios([
            {"name": "上涨", "change": 0.20, "desc": "如果未来市场上涨 20%"},
            {"name": "下跌", "change": -0.20, "desc": "如果未来市场下跌 20%"},
            {"name": "震荡", "change": 0.05, "desc": "如果未来市场窄幅震荡±5%"},
        ])
        from src.python.llm.prompts import _build_expert_review_prompt

        result = _build_expert_review_prompt(
            total_mv=100_000,
            total_cost=80_000,
            total_profit=20_000,
            total_today_profit=1_000,
            holdings_count=5,
            categories={},
            holdings_details=_make_minimal_holdings(),
            enable_conditional=True,
        )

        self.assertIn("### 情景分析", result)
        self.assertIn("上涨", result)
        self.assertIn("下跌", result)
        self.assertIn("震荡", result)
        self.assertIn("20%", result)
        # 恰好有 3 个情景条目
        self.assertEqual(result.count("📈"), 3)

    # ── test 2: Mode 2 禁用 ──────────────────────────────────

    def test_mode2_disabled(self):
        """Mode 2 禁用 → prompt 末尾与 MVP-06 一致，无情景段落。"""
        from src.python.llm.prompts import _build_expert_review_prompt

        result = _build_expert_review_prompt(
            total_mv=100_000,
            total_cost=80_000,
            total_profit=20_000,
            total_today_profit=1_000,
            holdings_count=5,
            categories={},
            holdings_details=_make_minimal_holdings(),
        )

        self.assertNotIn("### 情景分析", result)
        # MVP-06 末尾段落为"给出优化建议和风险预警。"后无追加内容
        self.assertTrue(result.strip().endswith("风险预警。"))

    # ── test 3: 单情景 ───────────────────────────────────────

    @patch("src.python.config._core.get_llm_config")
    def test_mode2_enabled_1_scenario(self, mock_get_llm_config):
        """1 情景 → prompt 末尾仅 1 段情景指令。"""
        mock_get_llm_config.return_value = _mock_llm_config_with_scenarios([
            {"name": "上涨", "change": 0.20, "desc": "如果未来市场上涨 20%"},
        ])
        from src.python.llm.prompts import _build_expert_review_prompt

        result = _build_expert_review_prompt(
            total_mv=100_000,
            total_cost=80_000,
            total_profit=20_000,
            total_today_profit=1_000,
            holdings_count=5,
            categories={},
            holdings_details=_make_minimal_holdings(),
            enable_conditional=True,
        )

        self.assertIn("### 情景分析", result)
        self.assertEqual(result.count("📈"), 1)

    # ── test 4: scenarios=[] ─────────────────────────────────

    @patch("src.python.config._core.get_llm_config")
    def test_mode2_enabled_empty_scenarios(self, mock_get_llm_config):
        """scenarios=[] → prompt 末尾段落与 Mode 2 关闭一致，无情景段。"""
        mock_get_llm_config.return_value = _mock_llm_config_with_scenarios([])
        from src.python.llm.prompts import _build_expert_review_prompt

        result = _build_expert_review_prompt(
            total_mv=100_000,
            total_cost=80_000,
            total_profit=20_000,
            total_today_profit=1_000,
            holdings_count=5,
            categories={},
            holdings_details=_make_minimal_holdings(),
            enable_conditional=True,
        )

        self.assertNotIn("### 情景分析", result)
        self.assertTrue(result.strip().endswith("风险预警。"))


if __name__ == "__main__":
    unittest.main()

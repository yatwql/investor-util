"""辩论模式 Token 预算守卫测试 — 。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/llm/test_debate_token_budget.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]

_MIN_HOLDINGS = [
    {"name": "测试A", "code": "000001", "market_value": 100000, "cost": 80000,
     "profit": 20000, "profit_rate": 0.25, "change_pct": 1.5, "nav_date": "2026-07-20", "source_api": "mock"},
]

_LONG_TEXT = "分析" * 2000  # 4000 chars — 配合显式低预算（100×1.0=100 chars）超 1× 阈值
_SHORT_TEXT = "分析结果"  # 4 chars


def _mock_long_result() -> tuple[str, bool]:
    return (_LONG_TEXT, False)


def _mock_short_result() -> tuple[str, bool]:
    return (_SHORT_TEXT, False)


@pytest.mark.unit_llm
class TestDebateTokenBudgetExceeded(unittest.TestCase):
    """Token 预算超限 → 跳过 synthesis，返回 pro+con 拼接。"""

    @patch("src.python.config._llm_settings.get_llm_config")
    @patch("src.python.llm.generators.generate_llm_module")
    def test_budget_exceeded_skips_synthesis(self, mock_gen, mock_config):
        """低预算下 pro+con 后跳过 synthesis。"""
        # 配置极低预算
        mock_config.return_value = {
            "debate": {
                "max_total_tokens_per_report": 100,
                "per_call_timeout_override": 30,
                "procon": {
                    "per_call_max_tokens": 8192,
                    "synthesis_temperature": 0.5,
                },
            },
        }
        # 模拟 pro 和 con 返回长文本（超过预算）
        mock_gen.side_effect = [
            _mock_short_result(),  # pro: 4 chars
            _mock_long_result(),  # con: 4000 chars → 总和 4004 > 100(100×1.0=100)
        ]

        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000, 80000, 20000, 1000, 1,
            {"股票": 1}, [],
            holdings_details=_MIN_HOLDINGS,
        )

        # 应该跳过 synthesis，返回 pro+con+None
        self.assertIsNotNone(result[0])
        self.assertIsNotNone(result[1])
        self.assertIsNone(result[2])  # synthesis 为 None


@pytest.mark.unit_llm
class TestDebateTokenBudgetNormal(unittest.TestCase):
    """Token 未超限 → 正常执行。"""

    @patch("src.python.config._llm_settings.get_llm_config")
    @patch("src.python.llm.generators.generate_llm_module")
    def test_budget_ok_full_execution(self, mock_gen, mock_config):
        """正常预算下三段全部执行。"""
        mock_config.return_value = {
            "debate": {
                "max_total_tokens_per_report": 16000,
                "per_call_timeout_override": 90,
                "procon": {
                    "per_call_max_tokens": 8192,
                    "synthesis_temperature": 0.5,
                },
            },
        }
        mock_gen.side_effect = [
            _mock_short_result(),  # pro
            _mock_short_result(),  # con
            _mock_short_result(),  # synthesis
        ]

        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000, 80000, 20000, 1000, 1,
            {"股票": 1}, [],
            holdings_details=_MIN_HOLDINGS,
        )

        self.assertIsNotNone(result[0])
        self.assertIsNotNone(result[1])
        self.assertIsNotNone(result[2])


@pytest.mark.unit_llm
class TestDebateTokenBudget2xFallback(unittest.TestCase):
    """超过 2× 预算 → 跳过所有 debate，回退普通模式。"""

    @patch("src.python.config._llm_settings.get_llm_config")
    @patch("src.python.llm.generators.generate_llm_module")
    def test_budget_2x_skips_all(self, mock_gen, mock_config):
        """超 2× 预算 → 返回 (None, None, None)。"""
        mock_config.return_value = {
            "debate": {
                "max_total_tokens_per_report": 100,
                "per_call_timeout_override": 30,
                "procon": {
                    "per_call_max_tokens": 8192,
                    "synthesis_temperature": 0.5,
                },
            },
        }
        # 2× 预算 = 100×1.0×2 = 200 chars，单个 long（300）超过 2× 阈值
        _very_long = "分" * 300
        mock_gen.side_effect = [
            (_very_long, False),  # pro: 200 chars > 130
        ]

        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000, 80000, 20000, 1000, 1,
            {"股票": 1}, [],
            holdings_details=_MIN_HOLDINGS,
        )

        # pro 已经超过 2× 预算 → 全部跳过
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertIsNone(result[2])

"""辩论模式集中度问答单元测试 — Mode 3 Q&A 块构建。

测试 _build_qa_concentration_block() 集中度问答引导段落构建：
  - 单品种集中（>20%）
  - 全部低集中（<5%）
  - 前 3 品种合计集中（>60%）
  - 行业集中（>40%）
  - 要求回答引导（量化评估/基准对比/调仓建议）
  - 纯计算无 LLM 调用

运行：
  pytest src/test/unit/llm/test_debate_qa.py -v
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


def _call_qa_block(
    holdings: list[dict] | None,
    total_mv: float,
    threshold: float = 0.20,
    industry_concentration: dict[str, float] | None = None,
) -> str:
    """辅助调用 _build_qa_concentration_block。"""
    from src.python.llm.prompts import _build_qa_concentration_block

    return _build_qa_concentration_block(
        holdings,
        total_mv,
        threshold=threshold,
        industry_concentration=industry_concentration,
    )


@pytest.mark.unit_llm
class TestDebateQaConcentration(unittest.TestCase):
    """_build_qa_concentration_block 集中度反问段落构建。"""

    # ── test 1: 单品种 25% > 20% ─────────────────────────────

    def test_single_holding_25pct(self):
        """单品种 25%（>20% 阈值）→ QA 块提及该品种和占比。"""
        holdings = [
            {"mv": 250_000, "name": "贵州茅台", "code": "600519"},
            {"mv": 750_000, "name": "长江电力", "code": "600900"},
        ]
        result = _call_qa_block(holdings, 1_000_000)

        self.assertIn("贵州茅台", result)
        self.assertIn("25.0%", result)
        self.assertIn("20% 警戒线", result)

    # ── test 2: 全部 <5% ─────────────────────────────────────

    def test_all_below_5pct(self):
        """全部品种占比 <5% → 无 QA 块（空字符串）。"""
        holdings = [
            {"mv": 10_000, "name": "A", "code": "A"},
            {"mv": 15_000, "name": "B", "code": "B"},
            {"mv": 20_000, "name": "C", "code": "C"},
        ]
        result = _call_qa_block(holdings, 500_000)

        self.assertEqual(result, "")

    # ── test 3: 前 3 品种合计 65% > 60% ──────────────────────

    def test_top3_total_65pct(self):
        """前 3 品种合计 82%（>60%）→ 含"前 3 大品种合计"段落。"""
        holdings = [
            {"mv": 250_000, "name": "A", "code": "A"},
            {"mv": 220_000, "name": "B", "code": "B"},
            {"mv": 180_000, "name": "C", "code": "C"},
            {"mv": 350_000, "name": "D", "code": "D"},
        ]
        result = _call_qa_block(holdings, 1_000_000)
        # Top 3 by mv: D(350K) + A(250K) + B(220K) = 820K → 82.0%

        self.assertIn("前 3 大品种合计", result)
        self.assertIn("82.0%", result)

    # ── test 4: 行业集中度 45% > 40% ─────────────────────────

    def test_industry_concentration_45pct(self):
        """行业集中度 45%（>40%）→ QA 块含该行业名和占比。"""
        holdings = [
            {"mv": 500_000, "name": "贵州茅台", "code": "600519"},
        ]
        industry_conc = {"白酒": 0.45}
        result = _call_qa_block(
            holdings,
            1_000_000,
            industry_concentration=industry_conc,
        )

        self.assertIn("白酒", result)
        self.assertIn("45.0%", result)
        self.assertIn("40% 行业集中度预警线", result)

    # ── test 5: 要求回答引导 ──

    def test_requires_answer_instead_of_disclaimer(self):
        """QA 块要求回答（量化评估/基准对比/调仓建议），不再含"无需回答"免责声明。"""
        holdings = [
            {"mv": 250_000, "name": "贵州茅台", "code": "600519"},
            {"mv": 750_000, "name": "长江电力", "code": "600900"},
        ]
        result = _call_qa_block(holdings, 1_000_000)

        self.assertIn("### 集中度问答", result)
        self.assertIn("量化评估", result)
        self.assertIn("调仓建议", result)
        self.assertNotIn("无需在本次报告中回答", result)

    # ── test 6: 纯计算无 LLM ─────────────────────────────────

    def test_pure_mock_no_llm(self):
        """纯计算函数，无 LLM 调用，仅验证返回值类型。"""
        holdings = [
            {"mv": 250_000, "name": "贵州茅台", "code": "600519"},
            {"mv": 750_000, "name": "长江电力", "code": "600900"},
        ]
        result = _call_qa_block(holdings, 1_000_000)

        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        self.assertIn("贵州茅台", result)

    # ── 边界：空/None 输入 ───────────────────────────────────

    def test_none_holdings_returns_empty(self):
        """holdings_details=None → 返回空字符串。"""
        result = _call_qa_block(None, 1_000_000)
        self.assertEqual(result, "")

    def test_empty_holdings_returns_empty(self):
        """holdings_details=[] → 返回空字符串。"""
        result = _call_qa_block([], 1_000_000)
        self.assertEqual(result, "")

    def test_zero_total_mv_returns_empty(self):
        """total_mv <= 0 → 返回空字符串。"""
        holdings = [{"mv": 100_000, "name": "A"}]
        result = _call_qa_block(holdings, 0)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()

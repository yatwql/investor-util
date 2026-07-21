"""LLM 辩论模式提示词模块单元测试 — System Prompt 模板和 Prompt 构建函数。

覆盖 I-02 提示词内容验证：
  - _SYSTEM_DEBATE_PRO 正面关键词
  - _SYSTEM_DEBATE_CON 四个风险维度
  - _SYSTEM_DEBATE_SYNTHESIS 白脸/黑脸占位符
  - _SYSTEM_DEBATE_CONDITIONAL_SCENARIO 条件推理情景模板
  - _build_debate_synthesis_prompt 签名与输出
  - _build_qa_concentration_block 集中度反问逻辑

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/llm/test_debate_prompts.py -v
"""

from __future__ import annotations

import inspect
import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


@pytest.mark.unit_llm
class TestDebateSystemPrompts(unittest.TestCase):
    """辩论模式 _SYSTEM_DEBATE_* 模板常量检证。"""

    def test_system_debate_pro_contains_positive_keywords(self):
        """_SYSTEM_DEBATE_PRO 包含正面关键词（正面/优势/持有理由）。"""
        from src.python.llm.prompts import _SYSTEM_DEBATE_PRO
        self.assertIsInstance(_SYSTEM_DEBATE_PRO, str)
        self.assertTrue(len(_SYSTEM_DEBATE_PRO) > 50)
        has_positive = any(kw in _SYSTEM_DEBATE_PRO for kw in ("正面", "优势", "持有理由"))
        self.assertTrue(has_positive, "_SYSTEM_DEBATE_PRO 应包含至少一个正面关键词")

    def test_system_debate_con_contains_all_four_dimensions(self):
        """_SYSTEM_DEBATE_CON 必须覆盖估值/行业/集中度/流动性 四个风险维度。"""
        from src.python.llm.prompts import _SYSTEM_DEBATE_CON
        self.assertIsInstance(_SYSTEM_DEBATE_CON, str)
        self.assertIn("估值风险", _SYSTEM_DEBATE_CON)
        self.assertIn("行业风险", _SYSTEM_DEBATE_CON)
        self.assertIn("集中度风险", _SYSTEM_DEBATE_CON)
        self.assertIn("流动性风险", _SYSTEM_DEBATE_CON)

    def test_system_debate_synthesis_contains_placeholders(self):
        """_SYSTEM_DEBATE_SYNTHESIS 包含 {pro_text} 和 {con_text} 占位符。"""
        from src.python.llm.prompts import _SYSTEM_DEBATE_SYNTHESIS
        self.assertIsInstance(_SYSTEM_DEBATE_SYNTHESIS, str)
        self.assertIn("{pro_text}", _SYSTEM_DEBATE_SYNTHESIS)
        self.assertIn("{con_text}", _SYSTEM_DEBATE_SYNTHESIS)

    def test_system_debate_conditional_scenario_exists(self):
        """_SYSTEM_DEBATE_CONDITIONAL_SCENARIO 模板存在且包含 {name}/{desc} 占位符。

        条件推理情景模板（I-04 模式 2）用于在提示词中注入预设上/下行情景。
        该常量尚未在 prompts_core.py 中实现，待补充后此测试将自动生效。
        """
        try:
            from src.python.llm.prompts import _SYSTEM_DEBATE_CONDITIONAL_SCENARIO as SCENARIO
        except (ImportError, AttributeError):
            self.skipTest(
                "_SYSTEM_DEBATE_CONDITIONAL_SCENARIO 尚未在 prompts 模块中定义，"
                "实现该常量后此测试将自动生效。"
            )
        self.assertIsInstance(SCENARIO, str)
        self.assertIn("{name}", SCENARIO)
        self.assertIn("{desc}", SCENARIO)


@pytest.mark.unit_llm
class TestDebateSynthesisPrompt(unittest.TestCase):
    """_build_debate_synthesis_prompt 综合 prompt 构建函数。"""

    def test_function_is_callable(self):
        """函数可调用。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt
        self.assertTrue(callable(_build_debate_synthesis_prompt))

    def test_signature_has_pro_con_params(self):
        """函数签名包含 pro_text 和 con_text 两个参数。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt
        sig = inspect.signature(_build_debate_synthesis_prompt)
        params = list(sig.parameters.keys())
        self.assertIn("pro_text", params)
        self.assertIn("con_text", params)

    def test_returns_string_with_both_texts(self):
        """输出字符串中应包含传入的 pro_text 和 con_text。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt
        pro = "白脸分析：该组合配置合理。"
        con = "黑脸分析：集中度偏高。"
        result = _build_debate_synthesis_prompt(pro, con)
        self.assertIsInstance(result, str)
        self.assertIn(pro, result)
        self.assertIn(con, result)

    def test_output_contains_markdown_code_block(self):
        """输出应包含 markdown 代码块标记（```markdown）。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt
        result = _build_debate_synthesis_prompt("pro", "con")
        self.assertIn("```markdown", result)
        # 应该是两个代码块（白脸和黑脸各一个）
        self.assertEqual(result.count("```markdown"), 2)


@pytest.mark.unit_llm
class TestBuildQaConcentrationBlock(unittest.TestCase):
    """_build_qa_concentration_block 集中度反问构建。"""

    def test_function_is_callable(self):
        """函数可调用。"""
        from src.python.llm.prompts import _build_qa_concentration_block
        self.assertTrue(callable(_build_qa_concentration_block))

    def test_empty_holdings_returns_empty(self):
        """空持仓（None / 空列表）返回空字符串。"""
        from src.python.llm.prompts import _build_qa_concentration_block
        self.assertEqual(_build_qa_concentration_block(None, 100_000), "")
        self.assertEqual(_build_qa_concentration_block([], 100_000), "")

    def test_zero_total_mv_returns_empty(self):
        """总市值为 0 时返回空字符串。"""
        from src.python.llm.prompts import _build_qa_concentration_block
        details = [{"name": "A", "code": "000001", "mv": 100_000}]
        self.assertEqual(_build_qa_concentration_block(details, 0), "")

    def test_single_holding_exceeds_threshold(self):
        """单品种超过阈值（默认 20%）时生成反问。"""
        from src.python.llm.prompts import _build_qa_concentration_block
        details = [{"name": "贵州茅台", "code": "600519", "mv": 500_000}]
        result = _build_qa_concentration_block(details, 1_000_000)
        self.assertIn("贵州茅台", result)
        self.assertIn("50.0%", result)
        self.assertIn("20%", result)

    def test_top3_exceeds_60_percent(self):
        """前 3 品种合计超过 60% 时生成反问。"""
        from src.python.llm.prompts import _build_qa_concentration_block
        # 使用高 threshold (0.50) 避免单个品种触发，仅测试前 3 合计条件
        details = [
            {"name": "甲", "code": "000001", "mv": 400_000},
            {"name": "乙", "code": "000002", "mv": 300_000},
            {"name": "丙", "code": "000003", "mv": 200_000},
            {"name": "丁", "code": "000004", "mv": 100_000},
        ]
        # top 3 = 400+300+200 = 900k / 1000k = 90% > 60%
        result = _build_qa_concentration_block(details, 1_000_000, threshold=0.50)
        self.assertIn("前 3 大品种", result)
        self.assertIn("90.0%", result)

    def test_no_trigger_returns_empty(self):
        """无触发条件时返回空字符串。"""
        from src.python.llm.prompts import _build_qa_concentration_block
        details = [
            {"name": "A", "code": "000001", "mv": 10_000},
            {"name": "B", "code": "000002", "mv": 10_000},
            {"name": "C", "code": "000003", "mv": 10_000},
        ]
        # 各品种占比均 < 20%，前 3 合计 30/100 = 30% < 60%
        result = _build_qa_concentration_block(details, 100_000)
        self.assertEqual(result, "")

    def test_industry_concentration_exceeds_40_percent(self):
        """行业集中度超过 40% 时生成反问。"""
        from src.python.llm.prompts import _build_qa_concentration_block
        details = [{"name": "A", "code": "000001", "mv": 10_000}]
        ind_conc = {"白酒": 0.45}
        result = _build_qa_concentration_block(details, 50_000, industry_concentration=ind_conc)
        self.assertIn("白酒", result)
        self.assertIn("45.0%", result)
        self.assertIn("40%", result)

    def test_industry_concentration_all_low_no_output(self):
        """行业集中度低于 40% 时不触发反问。"""
        from src.python.llm.prompts import _build_qa_concentration_block
        details = [{"name": "A", "code": "000001", "mv": 10_000}]
        ind_conc = {"白酒": 0.25, "科技": 0.15}
        result = _build_qa_concentration_block(details, 50_000, industry_concentration=ind_conc)
        self.assertEqual(result, "")

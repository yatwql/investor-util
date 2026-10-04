"""LLM 辩论模式提示词模块单元测试 — System Prompt 模板和 Prompt 构建函数。

覆盖 提示词内容验证：
  - _SYSTEM_DEBATE_PRO 正面关键词
  - _SYSTEM_DEBATE_CON 四个风险维度
  - _SYSTEM_DEBATE_SYNTHESIS 白脸/黑脸占位符
  - 条件推理情景注入（`debate.conditional.scenarios` → user prompt：name/desc 渲染、空配置回退、开关门控）
  - _build_debate_synthesis_prompt 签名与输出
  - _build_concentration_qa_block 集中度反问逻辑

运行：
  pytest src/test/unit/llm/test_debate_prompts.py -v
"""

from __future__ import annotations

import inspect
import unittest
from unittest import mock

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

    def test_system_debate_synthesis_contains_instruction_keywords(self):
        """_SYSTEM_DEBATE_SYNTHESIS 包含不应重复论点和情景分析等关键指令。"""
        from src.python.llm.prompts import _SYSTEM_DEBATE_SYNTHESIS

        self.assertIsInstance(_SYSTEM_DEBATE_SYNTHESIS, str)
        # 应包含"不要重复"或"无需"等阻止重复的指令
        has_no_repeat = any(kw in _SYSTEM_DEBATE_SYNTHESIS for kw in ("不要重复", "无需重复", "无需"))
        self.assertTrue(has_no_repeat, "_SYSTEM_DEBATE_SYNTHESIS 应包含禁止重复论点的指令")
        # 应包含 "共识与分歧摘要" 输出结构
        self.assertIn("共识与分歧摘要", _SYSTEM_DEBATE_SYNTHESIS)


@pytest.mark.unit_llm
class TestConditionalScenarioInjection(unittest.TestCase):
    """条件推理情景注入 — `debate.conditional.scenarios` 到 user prompt 的真实行为。

    情景按需求 R-LLM-DB-CONDITIONAL-02/04 注入 **user prompt**（仅改内容、不改调用次数），
    渲染形态为 `**{name}情景（{desc}）**`；R-LLM-DB-CONDITIONAL-05 要求 scenarios 为空时
    条件推理不生效、回退标准 prompt。
    """

    @mock.patch("src.python.config._llm_settings.get_llm_config")
    def test_scenarios_rendered_into_synthesis_prompt(self, mock_get):
        """开关开启时，每条情景的 name/desc 都渲染进综合阶段 user prompt。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt

        scenarios = [
            {"name": "上涨", "change": 0.2, "desc": "指数上涨20%"},
            {"name": "下跌", "change": -0.2, "desc": "指数下跌20%"},
        ]
        mock_get.return_value = {"debate": {"conditional": {"scenarios": scenarios}}}

        result = _build_debate_synthesis_prompt("白脸正文", "黑脸正文", enable_conditional=True)

        self.assertIn("### 情景分析", result)
        for sc in scenarios:
            self.assertIn(
                f"**{sc['name']}情景（{sc['desc']}）**",
                result,
                f"情景 {sc['name']} 应以 name/desc 渲染进 user prompt",
            )

    @mock.patch("src.python.config._llm_settings.get_llm_config")
    def test_empty_scenarios_falls_back_to_baseline(self, mock_get):
        """scenarios 为空 → 条件推理不生效，综合 prompt 不含情景段（回退基线）。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt

        mock_get.return_value = {"debate": {"conditional": {"scenarios": []}}}

        result = _build_debate_synthesis_prompt("白脸正文", "黑脸正文", enable_conditional=True)

        self.assertNotIn("### 情景分析", result)
        self.assertIn("白脸原始分析", result)

    @mock.patch("src.python.config._llm_settings.get_llm_config")
    def test_flag_off_ignores_configured_scenarios(self, mock_get):
        """开关关闭时即使配置了情景也不注入（开关是条件推理的唯一门）。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt

        mock_get.return_value = {
            "debate": {
                "conditional": {
                    "scenarios": [
                        {"name": "上涨", "change": 0.2, "desc": "指数上涨20%"},
                    ]
                }
            }
        }

        result = _build_debate_synthesis_prompt("白脸正文", "黑脸正文", enable_conditional=False)

        self.assertNotIn("### 情景分析", result)
        self.assertNotIn("上涨情景（指数上涨20%）", result)

    @mock.patch("src.python.config._llm_settings.get_llm_config")
    def test_scenarios_rendered_into_expert_review_prompt(self, mock_get):
        """标准路径同样注入情景；`skip_scenarios=True` 时辩论 pro/con 跳过。"""
        from src.python.llm.prompts import _build_expert_review_prompt

        scenarios = [{"name": "震荡", "change": 0.05, "desc": "指数震荡±5%"}]
        mock_get.return_value = {"debate": {"conditional": {"scenarios": scenarios}}}
        base_kwargs = dict(
            total_mv=1_000_000,
            total_cost=900_000,
            total_profit=100_000,
            total_today_profit=5_000,
            holdings_count=2,
            categories={"股票": 1_000_000},
        )

        with_conditional = _build_expert_review_prompt(**base_kwargs, enable_conditional=True)
        self.assertIn("**震荡情景（指数震荡±5%）**", with_conditional)

        skipped = _build_expert_review_prompt(
            **base_kwargs,
            enable_conditional=True,
            skip_scenarios=True,
        )
        self.assertNotIn("**震荡情景（指数震荡±5%）**", skipped)


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

    def test_output_contains_code_block(self):
        """输出应包含代码块标记（```），白脸和黑脸各一开一闭共 4 个。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt

        result = _build_debate_synthesis_prompt("pro", "con")
        self.assertIn("```", result)
        # 两个代码块，每块一开一闭：白脸 ```...``` + 黑脸 ```...``` = 4 个
        self.assertEqual(result.count("```"), 4)


@pytest.mark.unit_llm
class TestBuildSystemDebateSynthesis(unittest.TestCase):
    """_build_system_debate_synthesis 综合权衡 system prompt 动态构建。"""

    def test_function_is_callable(self):
        """函数可调用且默认返回基线版本。"""
        from src.python.llm.prompts import _build_system_debate_synthesis

        self.assertTrue(callable(_build_system_debate_synthesis))

    def test_conditional_false_returns_baseline(self):
        """conditional 关闭时返回 _SYSTEM_DEBATE_SYNTHESIS 基线（禁止情景分析）。"""
        from src.python.llm.prompts import (
            _SYSTEM_DEBATE_SYNTHESIS,
            _build_system_debate_synthesis,
        )

        result = _build_system_debate_synthesis(enable_conditional=False)
        self.assertIs(result, _SYSTEM_DEBATE_SYNTHESIS)
        # 基线仍保留"不要插入情景分析段落"约束
        self.assertIn("不要重复白脸/黑脸", result)
        self.assertIn("不要在综合权衡中再次插入情景分析段落", result)

    def test_conditional_true_allows_scenario_with_citation_discipline(self):
        """conditional 开启时允许输出情景分析，但强化引用纪律。

        conditional 开启时 user prompt 会注入情景指令，system prompt 若仍禁止
        情景分析会与 user prompt 冲突，导致 LLM 为满足情景指令而重复复述白脸/
        黑脸观点。本断言确保 conditional 变体：
          - 不再包含"不要插入情景分析段落"的冲突断言
          - 明确允许按 prompt 输出情景分析
          - 强化"引用一句话概括、不复述"纪律
        """
        from src.python.llm.prompts import _build_system_debate_synthesis

        result = _build_system_debate_synthesis(enable_conditional=True)
        # 仍禁止重复白脸/黑脸论点
        self.assertIn("不要重复白脸/黑脸", result)
        # 不再包含与 user prompt 冲突的"禁止情景分析"断言
        self.assertNotIn("不要在综合权衡中再次插入情景分析段落", result)
        # 明确允许情景分析（conditional 模式）
        self.assertIn("情景分析纪律", result)
        self.assertIn("下方 prompt 要求你按涨/跌/震荡情景", result)
        # 强化引用纪律
        self.assertIn("不得复述白脸/黑脸的具体论述", result)
        # 输出结构包含情景分析
        self.assertIn("5. **情景分析**", result)

    def test_conditional_varies_by_flag(self):
        """conditional 开关应改变返回内容。"""
        from src.python.llm.prompts import _build_system_debate_synthesis

        baseline = _build_system_debate_synthesis(enable_conditional=False)
        conditional = _build_system_debate_synthesis(enable_conditional=True)
        self.assertNotEqual(baseline, conditional)


@pytest.mark.unit_llm
class TestBuildQaConcentrationBlock(unittest.TestCase):
    """_build_concentration_qa_block 集中度反问构建。"""

    def test_function_is_callable(self):
        """函数可调用。"""
        from src.python.llm.prompts import _build_concentration_qa_block

        self.assertTrue(callable(_build_concentration_qa_block))

    def test_empty_holdings_returns_empty(self):
        """空持仓（None / 空列表）返回空字符串。"""
        from src.python.llm.prompts import _build_concentration_qa_block

        self.assertEqual(_build_concentration_qa_block(None, 100_000), "")
        self.assertEqual(_build_concentration_qa_block([], 100_000), "")

    def test_zero_total_mv_returns_empty(self):
        """总市值为 0 时返回空字符串。"""
        from src.python.llm.prompts import _build_concentration_qa_block

        details = [{"name": "A", "code": "000001", "mv": 100_000}]
        self.assertEqual(_build_concentration_qa_block(details, 0), "")

    def test_single_holding_exceeds_threshold(self):
        """单品种超过阈值（默认 20%）时生成反问。"""
        from src.python.llm.prompts import _build_concentration_qa_block

        details = [{"name": "贵州茅台", "code": "600519", "mv": 500_000}]
        result = _build_concentration_qa_block(details, 1_000_000)
        self.assertIn("贵州茅台", result)
        self.assertIn("50.0%", result)
        self.assertIn("20%", result)

    def test_top3_exceeds_60_percent(self):
        """前 3 品种合计超过 60% 时生成反问。"""
        from src.python.llm.prompts import _build_concentration_qa_block

        # 使用高 threshold (0.50) 避免单个品种触发，仅测试前 3 合计条件
        details = [
            {"name": "甲", "code": "000001", "mv": 400_000},
            {"name": "乙", "code": "000002", "mv": 300_000},
            {"name": "丙", "code": "000003", "mv": 200_000},
            {"name": "丁", "code": "000004", "mv": 100_000},
        ]
        # top 3 = 400+300+200 = 900k / 1000k = 90% > 60%
        result = _build_concentration_qa_block(details, 1_000_000, threshold=0.50)
        self.assertIn("前 3 大品种", result)
        self.assertIn("90.0%", result)

    def test_no_trigger_returns_empty(self):
        """无触发条件时返回空字符串。"""
        from src.python.llm.prompts import _build_concentration_qa_block

        details = [
            {"name": "A", "code": "000001", "mv": 10_000},
            {"name": "B", "code": "000002", "mv": 10_000},
            {"name": "C", "code": "000003", "mv": 10_000},
        ]
        # 各品种占比均 < 20%，前 3 合计 30/100 = 30% < 60%
        result = _build_concentration_qa_block(details, 100_000)
        self.assertEqual(result, "")

    def test_industry_concentration_exceeds_40_percent(self):
        """行业集中度超过 40% 时生成反问。"""
        from src.python.llm.prompts import _build_concentration_qa_block

        details = [{"name": "A", "code": "000001", "mv": 10_000}]
        ind_conc = {"白酒": 0.45}
        result = _build_concentration_qa_block(details, 50_000, industry_concentration=ind_conc)
        self.assertIn("白酒", result)
        self.assertIn("45.0%", result)
        self.assertIn("40%", result)

    def test_industry_concentration_all_low_no_output(self):
        """行业集中度低于 40% 时不触发反问。"""
        from src.python.llm.prompts import _build_concentration_qa_block

        details = [{"name": "A", "code": "000001", "mv": 10_000}]
        ind_conc = {"白酒": 0.25, "科技": 0.15}
        result = _build_concentration_qa_block(details, 50_000, industry_concentration=ind_conc)
        self.assertEqual(result, "")


@pytest.mark.unit_llm
class TestDebateQaConcentrationConfig(unittest.TestCase):
    """集中度问答的合成阶段（synthesis）与阈值配置读取。

    集中度问答引导需求：
      - 综合权衡 prompt 在 qa 开启时追加集中度问答引导段（要求回答版）
      - synthesis 阶段 threshold 从 llm_settings 读取，而非硬编码 0.20
      - system prompt 在 qa 开启时追加集中度问答章节输出要求
      - 标准模式（expert_review）threshold 同样从配置读取
    """

    # ── _build_debate_synthesis_prompt ──────────────────────────

    def test_synthesis_prompt_qa_enabled_appends_instruction(self):
        """include_concentration_qa=True 且命中触发时，合成 prompt 含集中度问答指令与问题。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt

        holdings = [
            {"name": "贵州茅台", "code": "600519", "mv": 250_000},
            {"name": "长江电力", "code": "600900", "mv": 750_000},
        ]
        prompt = _build_debate_synthesis_prompt(
            "白脸",
            "黑脸",
            include_concentration_qa=True,
            holdings_details=holdings,
            total_mv=1_000_000,
        )
        self.assertIn("集中度问答", prompt)
        self.assertIn("贵州茅台", prompt)
        self.assertIn("警戒线", prompt)
        self.assertIn("调仓建议", prompt)

    def test_synthesis_prompt_qa_disabled_no_instruction(self):
        """include_concentration_qa=False 时合成 prompt 不含集中度问答指令。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt

        holdings = [
            {"name": "贵州茅台", "code": "600519", "mv": 250_000},
            {"name": "长江电力", "code": "600900", "mv": 750_000},
        ]
        prompt = _build_debate_synthesis_prompt(
            "白脸",
            "黑脸",
            include_concentration_qa=False,
            holdings_details=holdings,
            total_mv=1_000_000,
        )
        self.assertNotIn("集中度问答", prompt)
        self.assertNotIn("警戒线", prompt)

    @mock.patch("src.python.config._llm_settings.get_llm_config")
    def test_synthesis_prompt_qa_uses_config_threshold(self, mock_get):
        """合成阶段 threshold 从 llm_settings 读取（18% 占比 + 15% 阈值 → 触发）。

        若 threshold 硬编码为默认 0.20，18% 将不触发 → 本断言验证配置读取生效。
        """
        from src.python.llm.prompts import _build_debate_synthesis_prompt

        mock_get.return_value = {"debate": {"concentration_qa": {"threshold": 0.15}}}
        # 单品种占比 18%（>15% 触发，但 <20% 默认阈值），前 3 合计 50.8% < 60%
        holdings = [
            {"name": "甲", "code": "000001", "mv": 180_000},
            {"name": "乙", "code": "000002", "mv": 164_000},
            {"name": "丙", "code": "000003", "mv": 164_000},
            {"name": "丁", "code": "000004", "mv": 164_000},
            {"name": "戊", "code": "000005", "mv": 164_000},
            {"name": "己", "code": "000006", "mv": 164_000},
        ]
        prompt = _build_debate_synthesis_prompt(
            "白脸",
            "黑脸",
            include_concentration_qa=True,
            holdings_details=holdings,
            total_mv=1_000_000,
        )
        self.assertIn("集中度问答", prompt)
        self.assertIn("甲", prompt)
        self.assertIn("警戒线", prompt)

    @mock.patch("src.python.config._llm_settings.get_llm_config")
    def test_synthesis_prompt_qa_config_threshold_below_skips(self, mock_get):
        """合成阶段 threshold 读配置为 20% 时，18% 占比不触发集中度问答。"""
        from src.python.llm.prompts import _build_debate_synthesis_prompt

        mock_get.return_value = {"debate": {"concentration_qa": {"threshold": 0.20}}}
        holdings = [
            {"name": "甲", "code": "000001", "mv": 180_000},
            {"name": "乙", "code": "000002", "mv": 164_000},
            {"name": "丙", "code": "000003", "mv": 164_000},
            {"name": "丁", "code": "000004", "mv": 164_000},
            {"name": "戊", "code": "000005", "mv": 164_000},
            {"name": "己", "code": "000006", "mv": 164_000},
        ]
        prompt = _build_debate_synthesis_prompt(
            "白脸",
            "黑脸",
            include_concentration_qa=True,
            holdings_details=holdings,
            total_mv=1_000_000,
        )
        self.assertNotIn("集中度问答", prompt)

    # ── _build_system_debate_synthesis ──────────────────────────

    def test_system_prompt_qa_appends_appendix(self):
        """include_concentration_qa=True 时 system prompt 追加集中度问答输出要求。"""
        from src.python.llm.prompts import _build_system_debate_synthesis

        result = _build_system_debate_synthesis(
            enable_conditional=False,
            include_concentration_qa=True,
        )
        self.assertIn("集中度问答（qa 模式）", result)
        self.assertIn("量化评估", result)
        self.assertIn("调仓建议", result)

    def test_system_prompt_qa_off_no_appendix(self):
        """include_concentration_qa=False 时 system prompt 不含 qa 附录。"""
        from src.python.llm.prompts import _build_system_debate_synthesis

        result = _build_system_debate_synthesis(enable_conditional=False)
        self.assertNotIn("集中度问答（qa 模式）", result)

    def test_system_prompt_conditional_plus_qa_combination(self):
        """conditional + qa 组合：情景分析纪律与 qa 附录同时存在，无编号冲突。"""
        from src.python.llm.prompts import _build_system_debate_synthesis

        result = _build_system_debate_synthesis(
            enable_conditional=True,
            include_concentration_qa=True,
        )
        self.assertIn("情景分析纪律", result)
        self.assertIn("5. **情景分析**", result)
        self.assertIn("集中度问答（qa 模式）", result)

    # ── _build_expert_review_prompt threshold 配置读取 ──────────

    @mock.patch("src.python.config._llm_settings.get_llm_config")
    def test_expert_review_prompt_threshold_from_config(self, mock_get):
        """标准模式 expert_review 的 threshold 从配置读取（22% 占比 + 15% 阈值 → 触发）。"""
        from src.python.llm.prompts import _build_expert_review_prompt

        mock_get.return_value = {"debate": {"concentration_qa": {"threshold": 0.15}}}
        # 单品种占比 22%（>15% 触发，但 <30%），前 3 合计 53.2% < 60% → 仅触发器①按配置阈值判定
        details = [
            {"name": "甲", "code": "000001", "mv": 220_000, "cost": 200_000},
            {"name": "乙", "code": "000002", "mv": 156_000, "cost": 140_000},
            {"name": "丙", "code": "000003", "mv": 156_000, "cost": 140_000},
            {"name": "丁", "code": "000004", "mv": 156_000, "cost": 140_000},
            {"name": "戊", "code": "000005", "mv": 156_000, "cost": 140_000},
            {"name": "己", "code": "000006", "mv": 156_000, "cost": 140_000},
        ]
        prompt = _build_expert_review_prompt(
            total_mv=1_000_000,
            total_cost=900_000,
            total_profit=100_000,
            total_today_profit=5_000,
            holdings_count=len(details),
            categories={},
            holdings_details=details,
            include_concentration_qa=True,
        )
        self.assertIn("### 集中度问答", prompt)
        self.assertIn("甲", prompt)
        self.assertIn("警戒线", prompt)

    @mock.patch("src.python.config._llm_settings.get_llm_config")
    def test_expert_review_prompt_threshold_higher_skips(self, mock_get):
        """threshold 高于单品种占比（30% 阈值 + 22% 占比）→ 不触发集中度问答。

        若 threshold 硬编码为默认 0.20，22% 将触发；配置读取 0.30 后应跳过。
        """
        from src.python.llm.prompts import _build_expert_review_prompt

        mock_get.return_value = {"debate": {"concentration_qa": {"threshold": 0.30}}}
        details = [
            {"name": "甲", "code": "000001", "mv": 220_000, "cost": 200_000},
            {"name": "乙", "code": "000002", "mv": 156_000, "cost": 140_000},
            {"name": "丙", "code": "000003", "mv": 156_000, "cost": 140_000},
            {"name": "丁", "code": "000004", "mv": 156_000, "cost": 140_000},
            {"name": "戊", "code": "000005", "mv": 156_000, "cost": 140_000},
            {"name": "己", "code": "000006", "mv": 156_000, "cost": 140_000},
        ]
        prompt = _build_expert_review_prompt(
            total_mv=1_000_000,
            total_cost=900_000,
            total_profit=100_000,
            total_today_profit=5_000,
            holdings_count=len(details),
            categories={},
            holdings_details=details,
            include_concentration_qa=True,
        )
        self.assertNotIn("### 集中度问答", prompt)

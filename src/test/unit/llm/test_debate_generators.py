"""LLM 辩论模式生成模块单元测试 — generate_debate_procon 流程与幻觉过滤。

覆盖 I-03 辩论模式生成逻辑：
  - generate_debate_procon 正常/异常流程（pro → con → synthesis 三步）
  - system_prompt/user_prompt 覆盖参数正确传递
  - _filter_hallucinated_codes 虚构代码过滤行为

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/llm/test_debate_generators.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


@pytest.mark.unit_llm
class TestDebateProconFlow(unittest.TestCase):
    """generate_debate_procon 三步生成流程控制测试。

    通过 mock generate_llm_module（模块级导入）控制各步返回值，
    验证函数在不同 LLM 返回下的分支走向。

    注意：base_kwargs 包含 holdings_details（含真实代码），确保
    _filter_hallucinated_codes 不会将 mock 文本中的代码误判为虚构。
    """

    def setUp(self):
        """通用最小参数集 — 满足函数签名但不触发真实 LLM 调用。"""
        self.base_kwargs = dict(
            total_mv=1_000_000,
            total_cost=800_000,
            total_profit=200_000,
            total_today_profit=10_000,
            holdings_count=5,
            categories={"基金": 3, "股票": 2},
            holdings_details=[
                {"code": "600519", "name": "贵州茅台", "market_value": 500_000},
            ],
            llm_config={},
            force=True,
        )

    # ── 测试：system_prompt / user_prompt 覆盖参数 ────────────

    def test_system_prompt_overrides_passed(self):
        """三步调用分别传递正确的 _SYSTEM_DEBATE_PRO/CON/SYNTHESIS。

        验证 generate_llm_module 的 system_prompt 关键字参数
        在 pro/con/synthesis 各阶段使用正确的模板常量。
        """
        from src.python.llm.prompts import (
            _SYSTEM_DEBATE_CON,
            _SYSTEM_DEBATE_PRO,
            _SYSTEM_DEBATE_SYNTHESIS,
        )
        from src.python.llm.generators import generate_debate_procon

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.side_effect = [
                ("600519 贵州茅台适合长期持有，行业地位稳固。", False),
                ("600519 估值已偏高，需注意回调风险。", False),
                ("综合双方意见，建议持有但设止盈。", False),
            ]
            generate_debate_procon(**self.base_kwargs)

            self.assertEqual(mock_gen.call_count, 3)
            self.assertEqual(mock_gen.call_args_list[0].kwargs["system_prompt"], _SYSTEM_DEBATE_PRO)
            self.assertEqual(mock_gen.call_args_list[1].kwargs["system_prompt"], _SYSTEM_DEBATE_CON)
            self.assertEqual(mock_gen.call_args_list[2].kwargs["system_prompt"], _SYSTEM_DEBATE_SYNTHESIS)

    def test_user_prompt_is_not_empty(self):
        """user_prompt 参数在每个阶段均为非空字符串。"""
        from src.python.llm.generators import generate_debate_procon

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.side_effect = [
                ("600519 表现良好。", False),
                ("600519 需警惕。", False),
                ("综合建议。", False),
            ]
            generate_debate_procon(**self.base_kwargs)

            for i in range(3):
                up = mock_gen.call_args_list[i].kwargs.get("user_prompt", "")
                self.assertIsInstance(up, str)
                self.assertTrue(len(up) > 0, f"第 {i + 1} 步 user_prompt 不应为空")

    def test_correct_module_key_and_force(self):
        """生成函数传递正确的 module_key='expert_review' 和 force=True。"""
        from src.python.llm.generators import generate_debate_procon

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.side_effect = [
                ("600519 表现良好。", False),
                ("600519 需警惕。", False),
                ("综合建议。", False),
            ]
            generate_debate_procon(**self.base_kwargs)

            for i, call in enumerate(mock_gen.call_args_list):
                args, _ = call
                self.assertEqual(args[1], "expert_review", f"第 {i + 1} 步 module_key 错误")

    # ── 测试：正常流程 ──────────────────────────────────────

    def test_normal_flow_returns_pro_con_synthesis(self):
        """正常三步全部成功 → 返回 (pro, con, synthesis) 三元组。"""
        from src.python.llm.generators import generate_debate_procon

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.side_effect = [
                ("600519 适合长期持有。", False),
                ("600519 集中度偏高。", False),
                ("综合建议：保持配置。", False),
            ]
            pro, con, syn = generate_debate_procon(**self.base_kwargs)

            self.assertEqual(pro, "600519 适合长期持有。")
            self.assertEqual(con, "600519 集中度偏高。")
            self.assertEqual(syn, "综合建议：保持配置。")
            self.assertEqual(mock_gen.call_count, 3)

    # ── 测试：合成步骤失败 ──────────────────────────────────

    def test_synthesis_failure_returns_pro_con_none(self):
        """综合失败（synthesis 返回 None）→ 返回 (pro, con, None)。"""
        from src.python.llm.generators import generate_debate_procon

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.side_effect = [
                ("600519 适合长期持有。", False),
                ("600519 需注意集中度风险。", False),
                (None, False),  # synthesis 失败
            ]
            pro, con, syn = generate_debate_procon(**self.base_kwargs)

            self.assertEqual(pro, "600519 适合长期持有。")
            self.assertEqual(con, "600519 需注意集中度风险。")
            self.assertIsNone(syn)

    # ── 测试：pro 步骤失败 ──────────────────────────────────

    def test_pro_failure_returns_none_tuple(self):
        """白脸失败（pro 返回 None）→ 返回 (None, None, None)。"""
        from src.python.llm.generators import generate_debate_procon

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.return_value = (None, False)  # pro 失败
            pro, con, syn = generate_debate_procon(**self.base_kwargs)

            self.assertIsNone(pro)
            self.assertIsNone(con)
            self.assertIsNone(syn)
            # pro 失败后应短路，不调用 con/synthesis
            self.assertEqual(mock_gen.call_count, 1)

    # ── 测试：con 步骤失败 ──────────────────────────────────

    def test_con_failure_returns_none_tuple(self):
        """黑脸失败（con 返回 None）→ 返回 (None, None, None)。"""
        from src.python.llm.generators import generate_debate_procon

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.side_effect = [
                ("600519 适合长期持有。", False),
                (None, False),  # con 失败
            ]
            pro, con, syn = generate_debate_procon(**self.base_kwargs)

            self.assertIsNone(pro)
            self.assertIsNone(con)
            self.assertIsNone(syn)
            # con 失败后应短路，不调用 synthesis
            self.assertEqual(mock_gen.call_count, 2)

    # ── 测试：pro 返回空字符串 ──────────────────────────────

    def test_pro_empty_string_returns_none_tuple(self):
        """白脸返回空字符串 → 返回 (None, None, None)。"""
        from src.python.llm.generators import generate_debate_procon

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.return_value = ("", False)  # pro 返回空字符串
            pro, con, syn = generate_debate_procon(**self.base_kwargs)

            self.assertIsNone(pro)
            self.assertIsNone(con)
            self.assertIsNone(syn)

    # ── 测试：Token 预算超限跳过 synthesis ──────────────────

    def test_token_budget_exceeded_skips_synthesis(self):
        """pro + con 超 token 预算时不调用 synthesis，返回 (pro, con, None)。"""
        from src.python.llm.generators import generate_debate_procon

        # 较长文本触发 token 预算上限（threshold ≈ 10400 chars, 2x ≈ 20800 chars）
        long_pro = "600519 " + "好" * 6000
        long_con = "600519 " + "差" * 6000

        with patch("src.python.llm.generators.generate_llm_module") as mock_gen:
            mock_gen.side_effect = [
                (long_pro, False),
                (long_con, False),
            ]
            pro, con, syn = generate_debate_procon(**self.base_kwargs)

            self.assertIsNotNone(pro)
            self.assertIsNotNone(con)
            self.assertIsNone(syn)
            # 超预算后 synthesis 不调用
            self.assertEqual(mock_gen.call_count, 2)


@pytest.mark.unit_llm
class TestFilterHallucinatedCodes(unittest.TestCase):
    """_filter_hallucinated_codes 虚构代码过滤。

    覆盖规则：
      - 6 位纯数字代码（如 600519）默认视为合法，不过滤
      - 含字母的非注册代码（如 X1234）视为虚构，整行移除
      - 空文本 / 无代码文本不做处理
      - 多行文本中仅含虚构代码的行被移除
    """

    def _call(self, text: str, valid: set[str] | None = None):
        from src.python.llm.generators import _filter_hallucinated_codes

        return _filter_hallucinated_codes(text, valid or set())

    def test_removes_hallucinated_codes(self):
        """含字母的虚构代码（不在 valid 中）被移除。"""
        text = "600519 贵州茅台表现良好。\nX1234 是虚构品种，要注意。"
        result = self._call(text, {"600519", "600900"})
        self.assertIn("600519", result)
        self.assertNotIn("X1234", result)

    def test_keeps_valid_codes_unchanged(self):
        """有效代码（在 valid_codes 中）保留。"""
        text = "600519 贵州茅台"
        result = self._call(text, {"600519", "600900"})
        self.assertEqual(result, text)

    def test_empty_text_returns_unchanged(self):
        """空文本直接原样返回。"""
        self.assertEqual(self._call(""), "")
        self.assertEqual(self._call(None), None)

    def test_no_invalid_codes_returns_unchanged(self):
        """无虚构代码时文本原样返回。"""
        text = "组合表现良好，无异常品种。"
        result = self._call(text)
        self.assertEqual(result, text)

    def test_mixed_valid_and_hallucinated(self):
        """混合文本中仅有效代码行保留。"""
        text = "600519 贵州茅台，建议持有。\nX1234 虚构品种，需警惕。\n600900 长江电力，表现稳健。"
        result = self._call(text, {"600519", "600900"})
        self.assertIn("600519", result)
        self.assertIn("600900", result)
        self.assertNotIn("X1234", result)

    def test_6digit_digit_only_not_filtered(self):
        """6 位纯数字代码即使不在 valid 中也不过滤（可能为合法股票代码）。"""
        text = "999999 是未知代码但纯数字。"
        result = self._call(text, {"600519"})
        self.assertIn("999999", result)

    def test_all_lines_removed_returns_empty(self):
        """所有行均含虚构代码 → 返回空字符串。"""
        text = "HK1234 虚构港股。\nUS567 虚构美股。"
        result = self._call(text, {"600519"})
        self.assertEqual(result, "")

    def test_logs_warning_on_hallucination(self):
        """检测到虚构代码时记录警告（验证 logger 调用）。"""
        with patch("src.python.llm.generators.logger.warning") as mock_warn:
            self._call("X1234 虚构品种。", {"600519"})
            mock_warn.assert_called_once()
            args, _ = mock_warn.call_args
            self.assertIn("虚构", args[0])

    def test_sentence_level_removal_same_line(self):
        """同一行内按句末标点切分，仅删除含虚构代码的句子（不整行删除）。

        回归缺陷：过滤按整行删除，单行多句文本会因一个虚构 token 丢失整行。
        """
        text = "600519 表现良好。X1234 虚构品种需警惕。600900 稳健。"
        result = self._call(text, {"600519", "600900"})
        self.assertIn("600519", result)
        self.assertIn("600900", result)
        self.assertIn("表现良好", result)
        self.assertIn("稳健", result)
        self.assertNotIn("X1234", result)
        self.assertNotIn("需警惕", result)


@pytest.mark.unit_llm
class TestFilterHallucinatedCodesEnglishWords(unittest.TestCase):
    """常见英文词汇不会被误判为虚构代码（正则误杀修复）。

    修复后必须同时满足：
      1. HTML/CSS 标签、金融术语、英文高频词不被误杀
      2. 真正的虚构代码（格式类似代码的字母组合）仍被过滤
    """

    def _call(self, text: str, valid: set[str] | None = None):
        from src.python.llm.generators import _filter_hallucinated_codes

        return _filter_hallucinated_codes(text, valid or set())

    def test_english_words_not_filtered(self):
        """HTML/CSS 标签和英文高频词不被误杀。"""
        text = (
            "当前指数处于 strong 趋势，板块风格 style 为成长，注意 flash 下跌风险，font size 12px color red 标注警示。"
        )
        result = self._call(text, {"600519"})
        self.assertIn("strong", result)
        self.assertIn("style", result)
        self.assertIn("flash", result)
        self.assertIn("font", result)
        self.assertIn("size", result)
        self.assertIn("color", result)
        self.assertIn("12px", result)

    def test_qdii_and_token_not_filtered(self):
        """QDII / Token / 100ETF 等行业术语不被误杀。"""
        text = "QDII 额度紧张，Token 资产波动大，100ETF 净流入"
        result = self._call(text, {"600519"})
        self.assertIn("QDII", result)
        self.assertIn("Token", result)
        self.assertIn("100ETF", result)

    def test_mixed_case_safe_words_not_filtered(self):
        """大小写混合的英文词汇同样豁免（大写 COLOR / Style / TOKEN）。"""
        text = "大写 COLOR 标注危险，Style 标签说明，TOKEN 代币概念"
        result = self._call(text, {"600519"})
        self.assertIn("COLOR", result)
        self.assertIn("Style", result)
        self.assertIn("TOKEN", result)

    def test_lowercase_code_never_filtered(self):
        """全小写字母串绝不视为虚构代码（实盘无全小写代码）。"""
        text = "lowercase 测试 abcdef ghijkl mnopqr"
        result = self._call(text, {"600519"})
        self.assertEqual(result, text)

    def test_real_hallucinations_still_caught(self):
        """真正的虚构代码仍被过滤。"""
        text = "建议关注600519\n虚构代码X1234需警惕\n虚构港股HK5678"
        result = self._call(text, {"600519"})
        self.assertIn("600519", result)
        self.assertNotIn("X1234", result)
        self.assertNotIn("HK5678", result)

    def test_mixed_safe_and_hallucinated(self):
        """安全英文词与真正虚构代码共存时，仅虚构代码行被移除。"""
        text = "市场风格 style 偏向成长\n虚构代码X1234需警惕\n注意 strong 趋势信号"
        result = self._call(text, {"600519"})
        self.assertIn("style", result)
        self.assertIn("strong", result)
        self.assertNotIn("X1234", result)

    def test_mixed_english_and_chinese_scenario(self):
        """混合英文词与持仓代码的长文本 → 不被全量清空。"""
        text = (
            "【市场风格分析】当前市场风格偏向大盘成长 style，"
            "需注意 flash 下跌风险，QDII 额度阶段性收紧。\n"
            "【持仓建议】建议关注600519贵州茅台、00700腾讯控股。\n"
            "虚构品种ZZZZZ需警惕集中度风险。"
        )
        result = self._call(text, {"600519", "00700"})
        self.assertIn("style", result)
        self.assertIn("flash", result)
        self.assertIn("QDII", result)
        self.assertIn("600519", result)
        self.assertIn("00700", result)
        self.assertNotIn("ZZZZZ", result)
        self.assertGreater(len(result), 0, "误杀导致全空，修复后应有内容")

    def test_top_rank_suffix_not_filtered(self):
        """TOP2/TOP3 排名表述（提示词附录 TOP3 块的回声）不被误判为虚构代码。"""
        text = "TOP2 持仓占比偏高，TOP3 现金流稳健，组合整体风险可控。"
        result = self._call(text, {"600519"})
        self.assertIn("TOP2", result)
        self.assertIn("TOP3", result)
        self.assertEqual(result, text)

    def test_smart_term_not_filtered(self):
        """Smart（Smart Beta / Smart Money）等金融术语不被误判为虚构代码。"""
        text = "Smart Beta 策略占比提升，Smart Money 资金流入明显。"
        result = self._call(text, {"600519"})
        self.assertIn("Smart", result)
        self.assertEqual(result, text)

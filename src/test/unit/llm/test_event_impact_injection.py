"""事件窗分歧例块注入链路单元测试（四模块统一附录通道）。

覆盖：
  - 提取层：generate_all_llm 从事件窗契约提取 prompt_block 并分发四模块，
    提取一次同一实例、契约缺席回退空串、提取助手三态；
  - 传输层：四模块 generate_* → generate_llm_module → skeleton 统一附录 →
    最终 user prompt 含块；块缺席 → 不含（关态逐字节回退面）；
  - 辩论 inputs 携带块、指纹条件并入（块空 = 与不带该段逐字节一致）；
  - 统一附录构造器条件拼接（空串输出与不含该段时逐字节一致）。

运行：
  pytest src/test/unit/llm/test_event_impact_injection.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.llm import generate_all_llm
from src.test.helpers import SynchronousExecutor

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]

_BLOCK = (
    "【事件窗量化对照·分歧例（文本判定 vs 事件窗方向）】\n"
    "分歧例（1 条，与报告事件表同源）：\n"
    "  2026-09-22（交易日 2026-09-22） 300750 关键词 宁德时代 文本=利好 方向=下 收益 -2.02% 超额 +1.99%｜示例新闻"
)
_ENABLED = {
    "enabled_llm": {
        "global_macro": True,
        "expert_review": True,
        "health_check": True,
        "penetration_deep": True,
    }
}
_CONTRACT = {"available": True, "prompt_block": _BLOCK}


# ═══════════════════════════════════════════════════════════════
#  提取层：契约 → 四模块形参（提取一次，同一实例）
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm._llm_dispatch.generate_penetration_deep_analysis")
@patch("src.python.llm._llm_dispatch.generate_health_check")
@patch("src.python.llm._llm_dispatch.generate_global_macro")
@patch("src.python.llm._llm_dispatch.generate_expert_review")
class TestExtractFromPipelineData(unittest.TestCase):
    """提取层：契约字段 prompt_block → 四模块形参。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._cfg_patcher = patch("src.python.llm.generators_orchestrator.get_llm_config", return_value=dict(_ENABLED))
        cls._cfg_patcher.start()
        cls._exec_patcher = patch("src.python.llm._llm_dispatch.ThreadPoolExecutor", new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm._llm_dispatch.httpx.Client", new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
        cls._cfg_patcher.stop()

    @staticmethod
    def _stubs(mock_expert, mock_macro, mock_health, mock_penetration):
        mock_macro.return_value = ("<p>m</p>", False)
        mock_expert.return_value = ("<p>e</p>", False)
        mock_health.return_value = ("<p>h</p>", False)
        mock_penetration.return_value = ("<p>p</p>", False)

    def test_block_passed_to_all_four_generators(self, mock_expert, mock_macro, mock_health, mock_penetration):
        """契约字段存在 → 四个生成函数收到同一实例（提取一次，非各处再拼）。"""
        self._stubs(mock_expert, mock_macro, mock_health, mock_penetration)
        pipeline_data = {"event_impact_data": dict(_CONTRACT)}

        generate_all_llm([], [], 0, 0, 0, 0, 0, {}, pipeline_data=pipeline_data)

        for name, mock_fn in [
            ("global_macro", mock_macro),
            ("expert_review", mock_expert),
            ("health_check", mock_health),
            ("penetration_deep", mock_penetration),
        ]:
            kwargs = mock_fn.call_args.kwargs
            assert kwargs.get("event_impact_block") == _BLOCK, f"{name}: 未收到分歧例块实例"

    def test_absent_contract_passes_empty_string(self, mock_expert, mock_macro, mock_health, mock_penetration):
        """契约缺席（feature 关闭/无分歧例）→ ""（提示词与缓存键双不变）。"""
        self._stubs(mock_expert, mock_macro, mock_health, mock_penetration)

        generate_all_llm([], [], 0, 0, 0, 0, 0, {}, pipeline_data={})

        for name, mock_fn in [
            ("global_macro", mock_macro),
            ("expert_review", mock_expert),
            ("health_check", mock_health),
            ("penetration_deep", mock_penetration),
        ]:
            assert mock_fn.call_args.kwargs.get("event_impact_block") == "", f"{name}: 未回退空串"

    def test_extract_helper_three_states(self, mock_expert, mock_macro, mock_health, mock_penetration):
        """提取助手三态：None 管线 / 契约缺席 / 契约在场。"""
        self._stubs(mock_expert, mock_macro, mock_health, mock_penetration)
        from src.python.llm import extract_event_impact_block

        assert extract_event_impact_block(None) == ""
        assert extract_event_impact_block({}) == ""
        assert extract_event_impact_block({"event_impact_data": dict(_CONTRACT)}) == _BLOCK


# ═══════════════════════════════════════════════════════════════
#  传输层：四模块最终 user prompt 含块（LLM 调用 mock 捕获）
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.generate_llm_content", return_value=("<p>内容</p>", False))
@patch("src.python.llm.skeleton.get_llm_config", return_value=dict(_ENABLED))
class TestPromptEndToEndContainsBlock(unittest.TestCase):
    """四模块 generate_* 真实走完 prompt 组装，最终 prompt 含块。"""

    @staticmethod
    def _call_kwargs(module_key: str) -> dict:
        holdings = [
            {
                "code": "011506",
                "name": "建信高端装备",
                "market_value": 60_000.0,
                "profit_rate": 8.5,
                "profit": 5_100.0,
            }
        ]
        common = dict(total_mv=60_000.0, total_cost=55_000.0, total_profit=5_000.0, holdings_details=holdings)
        if module_key == "global_macro":
            return dict(common, a_indices={}, us_indices={}, categories={})
        return dict(common, total_today_profit=500.0, holdings_count=1, categories={}, penetrated_assets=None)

    @staticmethod
    def _prompt_texts(mock_content) -> list[str]:
        call = mock_content.call_args
        return [a for a in call.args if isinstance(a, str)] + [v for v in call.kwargs.values() if isinstance(v, str)]

    def test_four_modules_receive_block(self, mock_cfg, mock_content):
        """四个模块送入模型的 prompt 均含块。"""
        from src.python.llm import generators

        fns = {
            "global_macro": generators.generate_global_macro,
            "expert_review": generators.generate_expert_review,
            "health_check": generators.generate_health_check,
            "penetration_deep": generators.generate_penetration_deep_analysis,
        }
        for module_key, fn in fns.items():
            mock_content.reset_mock()
            fn(**self._call_kwargs(module_key), event_impact_block=_BLOCK)
            texts = self._prompt_texts(mock_content)
            assert any("【事件窗量化对照·分歧例" in s for s in texts), f"{module_key}: 最终 prompt 不含块"

    def test_four_modules_absent_block_unchanged(self, mock_cfg, mock_content):
        """块缺席 → 最终 prompt 不含块（关态逐字节回退面）。"""
        from src.python.llm import generators

        fns = {
            "global_macro": generators.generate_global_macro,
            "expert_review": generators.generate_expert_review,
            "health_check": generators.generate_health_check,
            "penetration_deep": generators.generate_penetration_deep_analysis,
        }
        for module_key, fn in fns.items():
            mock_content.reset_mock()
            fn(**self._call_kwargs(module_key))
            texts = self._prompt_texts(mock_content)
            assert not any("【事件窗量化对照·分歧例" in s for s in texts), f"{module_key}: 缺席时 prompt 意外含块"


# ═══════════════════════════════════════════════════════════════
#  辩论 inputs + 指纹条件并入
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.generate_llm_content", return_value=("<p>观点</p>", False))
@patch("src.python.llm.skeleton.get_llm_config", return_value=dict(_ENABLED))
class TestDebateCarriesBlock(unittest.TestCase):
    """辩论三个章节的 prompt 与指纹 inputs 的分歧例块注入。"""

    @patch("src.python.llm.generators.generate_llm_module", return_value=("<p>x</p>", True))
    @patch("src.python.llm.generators.debate_procon_fingerprint", return_value="fp")
    def test_debate_inputs_carry_block(self, mock_fp, mock_module, mock_cfg, mock_content):
        """辩论指纹 inputs 携带块（与 purchase/holding 块平行同构）。"""
        from src.python.llm.generators import generate_debate_procon

        generate_debate_procon(0.0, 0.0, 0.0, 0.0, 0, {}, event_impact_block=_BLOCK)
        inputs = mock_fp.call_args.args[0]
        assert inputs.event_impact_block == _BLOCK

    @patch("src.python.llm.generators.generate_llm_module", return_value=("<p>x</p>", True))
    @patch("src.python.llm.generators.debate_procon_fingerprint", return_value="fp")
    def test_debate_inputs_empty_block_by_default(self, mock_fp, mock_module, mock_cfg, mock_content):
        """缺省 → inputs.event_impact_block == ""（回退原键形态）。"""
        from src.python.llm.generators import generate_debate_procon

        generate_debate_procon(0.0, 0.0, 0.0, 0.0, 0, {})
        inputs = mock_fp.call_args.args[0]
        assert inputs.event_impact_block == ""


class TestFingerprintConditionalJoin(unittest.TestCase):
    """指纹条件并入：块空 = 与不带该段逐字节一致；块非空 = 键改变。"""

    @staticmethod
    def _inputs(**kw):
        from src.python.llm.module_fingerprint import ModuleFingerprintInputs

        return ModuleFingerprintInputs(total_mv=100.0, total_profit=10.0, **kw)

    def test_standard_modules_conditional(self):
        from src.python.llm.module_fingerprint import (
            expert_review_fingerprint,
            global_macro_fingerprint,
            health_check_fingerprint,
            penetration_deep_fingerprint,
        )

        for fn in (global_macro_fingerprint, expert_review_fingerprint, health_check_fingerprint):
            base = fn(self._inputs())
            assert fn(self._inputs(event_impact_block="")) == base, f"{fn.__name__}: 空块改变了键"
            assert fn(self._inputs(event_impact_block=_BLOCK)) != base, f"{fn.__name__}: 非空块未进键"
        base = penetration_deep_fingerprint(self._inputs())
        assert penetration_deep_fingerprint(self._inputs(event_impact_block="")) == base
        assert penetration_deep_fingerprint(self._inputs(event_impact_block=_BLOCK)) != base

    def test_self_review_conditional(self):
        from src.python.llm.module_fingerprint import self_review_fingerprint

        base = self_review_fingerprint({"a": "<p>x</p>"})
        assert self_review_fingerprint({"a": "<p>x</p>"}, event_impact_block="") == base
        assert self_review_fingerprint({"a": "<p>x</p>"}, event_impact_block=_BLOCK) != base


# ═══════════════════════════════════════════════════════════════
#  统一附录构造器：条件拼接与逐字节回退
# ═══════════════════════════════════════════════════════════════


class TestPromptAppendixConditional:
    """_build_prompt_appendix 对分歧例块条件拼接（关态逐字节回退）。"""

    def test_block_appended_when_non_empty(self):
        from src.python.llm.prompts_tables import _build_prompt_appendix

        appendix = _build_prompt_appendix(None, 0.0, 0.0, 0.0, event_impact_block=_BLOCK)
        assert _BLOCK in appendix

    def test_empty_block_byte_identical_to_omitted(self):
        from src.python.llm.prompts_tables import _build_prompt_appendix

        without = _build_prompt_appendix(None, 0.0, 0.0, 0.0)
        with_empty = _build_prompt_appendix(None, 0.0, 0.0, 0.0, event_impact_block="")
        assert with_empty == without, "空块必须与不含该段时逐字节一致"

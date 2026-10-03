"""申购限购约束块注入链路单元测试。

覆盖：
  - generate_all_llm 从 pipeline_data 提取 constraint_block 并分发四模块（提取层）
  - 四模块 generate_* → generate_llm_module → skeleton 统一附录 → 最终 user prompt
    含块（传输层，LLM 调用 mock 捕获）
  - 块缺席（契约降级）→ 提示词与键回退原样（降级矩阵）

运行：
  pytest src/test/unit/llm/test_purchase_constraint_injection.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.llm import generate_all_llm
from src.test.helpers import SynchronousExecutor

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]

_BLOCK = (
    "【申购限购约束】（天天基金渠道口径，数据抓取于 2026-10-01）\n- 110022 示例安心债券 限大额：单账户单日限购 100 元"
)
_ENABLED = {
    "enabled_llm": {
        "global_macro": True,
        "expert_review": True,
        "health_check": True,
        "penetration_deep": True,
    }
}


# ═══════════════════════════════════════════════════════════════
#  提取层：generate_all_llm 单次提取同一实例交预检侧与写侧
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm.generators_orchestrator.generate_penetration_deep_analysis")
@patch("src.python.llm.generators_orchestrator.generate_health_check")
@patch("src.python.llm.generators_orchestrator.generate_global_macro")
@patch("src.python.llm.generators_orchestrator.generate_expert_review")
class TestExtractFromPipelineData(unittest.TestCase):
    """提取层：契约字段 → 四模块形参。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._cfg_patcher = patch("src.python.llm.generators_orchestrator.get_llm_config", return_value=dict(_ENABLED))
        cls._cfg_patcher.start()
        cls._exec_patcher = patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor", new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators_orchestrator.httpx.Client", new=MagicMock())
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

    def test_constraint_block_passed_to_all_four_generators(
        self, mock_expert, mock_macro, mock_health, mock_penetration
    ):
        """契约字段存在 → 四个生成函数收到同一实例（提取一次，非各处再拼）。"""
        self._stubs(mock_expert, mock_macro, mock_health, mock_penetration)
        pipeline_data = {"purchase_status_data": {"constraint_block": _BLOCK}}

        generate_all_llm([], [], 0, 0, 0, 0, 0, {}, pipeline_data=pipeline_data)

        for name, mock_fn in [
            ("global_macro", mock_macro),
            ("expert_review", mock_expert),
            ("health_check", mock_health),
            ("penetration_deep", mock_penetration),
        ]:
            kwargs = mock_fn.call_args.kwargs
            assert kwargs.get("purchase_constraint_block") == _BLOCK, f"{name}: 未收到约束块实例"

    def test_absent_contract_passes_empty_string(self, mock_expert, mock_macro, mock_health, mock_penetration):
        """契约缺席（降级/未产出）→ ""（提示词与缓存键双不变）。"""
        self._stubs(mock_expert, mock_macro, mock_health, mock_penetration)

        generate_all_llm([], [], 0, 0, 0, 0, 0, {}, pipeline_data={})

        for name, mock_fn in [
            ("global_macro", mock_macro),
            ("expert_review", mock_expert),
            ("health_check", mock_health),
            ("penetration_deep", mock_penetration),
        ]:
            assert mock_fn.call_args.kwargs.get("purchase_constraint_block") == "", f"{name}: 未回退空串"


# ═══════════════════════════════════════════════════════════════
#  传输层：四模块最终 user prompt 含块（LLM 调用 mock 捕获）
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.generate_llm_content", return_value=("<p>内容</p>", False))
@patch("src.python.llm.skeleton.get_llm_config", return_value=dict(_ENABLED))
class TestPromptEndToEndContainsBlock(unittest.TestCase):
    """四模块 generate_* 真实走完 prompt 组装，最终 user_prompt 含块。"""

    def _call_kwargs(self, module_key: str) -> dict:
        """各模块的最小合法实参（附录数据足以渲染三防御 + 块）。"""
        holdings = [
            {
                "code": "011506",
                "name": "建信高端装备",
                "market_value": 60_000.0,
                "profit_rate": 8.5,
                "profit": 5_100.0,
            }
        ]
        common = dict(
            total_mv=60_000.0,
            total_cost=55_000.0,
            total_profit=5_000.0,
            holdings_details=holdings,
        )
        if module_key == "global_macro":
            return dict(common, a_indices={}, us_indices={}, categories={})
        if module_key == "expert_review":
            return dict(
                common,
                total_today_profit=500.0,
                holdings_count=1,
                categories={},
                penetrated_assets=None,
            )
        if module_key == "health_check":
            return dict(
                common,
                total_today_profit=500.0,
                holdings_count=1,
                categories={},
                penetrated_assets=None,
            )
        return dict(
            common,
            total_today_profit=500.0,
            holdings_count=1,
            categories={},
            penetrated_assets=None,
        )

    @staticmethod
    def _prompt_texts(mock_content) -> list[str]:
        """collect generate_llm_content 实参中的全部字符串（system+user 均在内）。"""
        call = mock_content.call_args
        return [a for a in call.args if isinstance(a, str)] + [v for v in call.kwargs.values() if isinstance(v, str)]

    def test_four_modules_receive_block(self, mock_cfg, mock_content):
        """四个模块送入模型的 prompt 均含块（mock 捕获 generate_llm_content 实参）。"""
        from src.python.llm import generators

        fns = {
            "global_macro": generators.generate_global_macro,
            "expert_review": generators.generate_expert_review,
            "health_check": generators.generate_health_check,
            "penetration_deep": generators.generate_penetration_deep_analysis,
        }
        for module_key, fn in fns.items():
            mock_content.reset_mock()
            fn(**self._call_kwargs(module_key), purchase_constraint_block=_BLOCK)
            texts = self._prompt_texts(mock_content)
            assert any("【申购限购约束】" in s for s in texts), f"{module_key}: 最终 prompt 不含约束块"
            assert any("110022" in s for s in texts), f"{module_key}: 约束明细未随块进入 prompt"

    def test_four_modules_absent_block_unchanged(self, mock_cfg, mock_content):
        """块缺席 → 最终 prompt 不含块（与接线前提示词逐字节一致的回退面）。"""
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
            assert not any("【申购限购约束】" in s for s in texts), f"{module_key}: 缺席时 prompt 意外含块"


# ═══════════════════════════════════════════════════════════════
#  辩论面：pro / con / synthesis 三章 + inputs 指纹
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.generate_llm_content", return_value=("<p>观点</p>", False))
@patch("src.python.llm.skeleton.get_llm_config", return_value=dict(_ENABLED))
class TestDebateProConSynContainBlock(unittest.TestCase):
    """辩论三章 prompt 与指纹的约束块注入。"""

    def test_debate_three_prompts_contain_block(self, mock_cfg, mock_content):
        """pro/con/synthesis 三次模型调用的 prompt 均含块。"""
        from src.python.llm.generators import generate_debate_procon

        holdings = [
            {
                "code": "011506",
                "name": "建信高端装备",
                "market_value": 60_000.0,
                "profit_rate": 8.5,
                "profit": 5_100.0,
            }
        ]
        pro, con, syn = generate_debate_procon(
            60_000.0,
            55_000.0,
            5_000.0,
            500.0,
            1,
            {},
            holdings_details=holdings,
            purchase_constraint_block=_BLOCK,
        )
        assert pro and con and syn, "辩论三段应产出（mock 下）"
        assert mock_content.call_count >= 3, "pro/con/synthesis 至少三次模型调用"
        for idx, call in enumerate(mock_content.call_args_list):
            texts = [a for a in call.args if isinstance(a, str)] + [
                v for v in call.kwargs.values() if isinstance(v, str)
            ]
            assert any("【申购限购约束】" in s for s in texts), f"第 {idx} 次辩论调用 prompt 不含块"

    @patch("src.python.llm.generators.generate_llm_module", return_value=("<p>x</p>", True))
    @patch("src.python.llm.generators.debate_procon_fingerprint", return_value="fp")
    def test_debate_inputs_carry_block(self, mock_fp, mock_module, mock_cfg, mock_content):
        """辩论指纹 inputs 携带块（进提示词必进指纹，同实例交预检/写两侧语义）。"""
        from src.python.llm.generators import generate_debate_procon

        generate_debate_procon(0.0, 0.0, 0.0, 0.0, 0, {}, purchase_constraint_block=_BLOCK)

        inputs = mock_fp.call_args.args[0]
        assert inputs.purchase_block == _BLOCK

    @patch("src.python.llm.generators.generate_llm_module", return_value=("<p>x</p>", True))
    @patch("src.python.llm.generators.debate_procon_fingerprint", return_value="fp")
    def test_debate_inputs_empty_block_by_default(self, mock_fp, mock_module, mock_cfg, mock_content):
        """缺省 → inputs.purchase_block == ""（回退原键形态）。"""
        from src.python.llm.generators import generate_debate_procon

        generate_debate_procon(0.0, 0.0, 0.0, 0.0, 0, {})
        inputs = mock_fp.call_args.args[0]
        assert inputs.purchase_block == ""


# ═══════════════════════════════════════════════════════════════
#  生成后自检面
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.generate_llm_content", return_value=("<p>自检</p>", False))
@patch("src.python.llm.skeleton.get_llm_config", return_value=dict(_ENABLED))
class TestSelfReviewContainsBlock(unittest.TestCase):
    """生成后自检 prompt 与指纹的约束块注入。"""

    _OUTPUTS = {
        "global_macro": "<p>宏观</p>",
        "expert_review": "<p>策略</p>",
        "health_check": "<p>体检</p>",
        "penetration_deep": "<p>穿透</p>",
    }

    def test_self_review_prompt_contains_block(self, mock_cfg, mock_content):
        """自检 prompt（经统一附录）含块。"""
        from src.python.llm.generators import generate_self_review

        holdings = [
            {
                "code": "011506",
                "name": "建信高端装备",
                "market_value": 60_000.0,
                "profit_rate": 8.5,
                "profit": 5_100.0,
            }
        ]
        generate_self_review(dict(self._OUTPUTS), holdings, None, purchase_constraint_block=_BLOCK)
        texts = [a for a in mock_content.call_args.args if isinstance(a, str)] + [
            v for v in mock_content.call_args.kwargs.values() if isinstance(v, str)
        ]
        assert any("【申购限购约束】" in s for s in texts), "自检 prompt 不含块"

    def test_self_review_fingerprint_three_states(self, mock_cfg, mock_content):
        """自检指纹三态：空块 ≡ 不带段原形态；非空换键；内容变再换键。"""
        from src.python.llm.module_fingerprint import self_review_fingerprint

        holdings = [{"code": "011506", "name": "建信高端装备", "market_value": 60_000.0}]
        baseline = self_review_fingerprint(dict(self._OUTPUTS), holdings, None)
        empty = self_review_fingerprint(dict(self._OUTPUTS), holdings, None, purchase_block="")
        with_block = self_review_fingerprint(dict(self._OUTPUTS), holdings, None, purchase_block=_BLOCK)
        changed = self_review_fingerprint(
            dict(self._OUTPUTS), holdings, None, purchase_block=_BLOCK.replace("100", "200")
        )
        assert empty == baseline, "空块必须与不带段的原形态逐字节一致"
        assert with_block != baseline, "块未进自检指纹"
        assert with_block != changed, "块内容变化未换键"


# ═══════════════════════════════════════════════════════════════
#  新闻面：批量提示词 + 指纹条件并入 + 6 函数透传
# ═══════════════════════════════════════════════════════════════


class TestNewsChainContainsBlock(unittest.TestCase):
    """新闻关联链：块进批量提示词/指纹，且逐级透传。"""

    def test_batch_prompt_contains_block_and_constructive_proof(self):
        """批量提示词：非空块 == 无块形态 + 分隔符 + 块（构造性拼接证明）。"""
        from src.python.llm.generators_news import _build_news_hooks

        top_news = [{"title": "示例新闻", "matched_keywords": ["建信"]}]
        _, _, prompt_fn_with, _ = _build_news_hooks(top_news, [], None, None, {}, _BLOCK)
        _, _, prompt_fn_without, _ = _build_news_hooks(top_news, [], None, None, {})
        prompt_with = prompt_fn_with(top_news, "fp")
        prompt_without = prompt_fn_without(top_news, "fp")
        self.assertEqual(prompt_with, prompt_without + "\n\n" + _BLOCK)

    def test_batch_preparer_fp_conditionally_joins_block(self):
        """指纹条件并入：块非空换键且逐值等于三参重算；块空沿用两参原形态。"""
        from src.python.llm.fingerprint import compute_fingerprint
        from src.python.llm.generators_news import _build_news_hooks

        top_news = [{"title": "示例新闻", "matched_keywords": []}]
        preparer_with, *_ = _build_news_hooks(top_news, [], None, None, {}, _BLOCK)
        preparer_without, *_ = _build_news_hooks(top_news, [], None, None, {})

        _, fp_with = preparer_with()
        _, fp_without = preparer_without()
        assert fp_with == compute_fingerprint([], None, _BLOCK), "未按三参重算"
        assert fp_without == compute_fingerprint([], None), "空块必须沿用两参原形态"
        assert fp_with != fp_without, "块未进新闻缓存指纹"

    def test_submit_news_future_passes_block_positionally(self):
        """_submit_news_future → build_news_data 第 4 位置实参收到块。"""
        from src.python.report._llm_news import _submit_news_future

        pool = MagicMock()
        _submit_news_future(pool, [], {"news_top_count": 10, "penetrated_assets": None}, True, _BLOCK)
        assert pool.submit.call_args.args[4] == _BLOCK

    def test_run_safe_passes_block_keyword(self):
        """run_news_correlation_safe → enhance_news_correlation 收到块。"""
        with (
            patch(
                "src.python.llm._llm_news_correlation.get_llm_config",
                return_value={"enabled_llm": {"news_correlation": True}},
            ),
            patch("src.python.llm.generators_news.enhance_news_correlation") as mock_enhance,
        ):
            mock_enhance.return_value = ([], False, {})
            from src.python.llm._llm_news_correlation import run_news_correlation_safe

            run_news_correlation_safe(
                [{"title": "t", "matched_keywords": []}],
                [],
                purchase_constraint_block=_BLOCK,
            )
            assert mock_enhance.call_args.kwargs.get("purchase_constraint_block") == _BLOCK

    def test_enhance_passes_block_to_hooks(self):
        """enhance_news_correlation → _build_news_hooks 第 6 实参收到块。"""
        with patch("src.python.llm.generators_news._build_news_hooks") as mock_hooks:
            mock_hooks.return_value = (lambda: ([], "fp"), lambda *_: "k", lambda *_: "p", "m")
            from src.python.llm.generators_news import enhance_news_correlation

            enhance_news_correlation(
                [{"title": "t", "matched_keywords": []}],
                [],
                llm_config={"model": "m", "enabled_llm": {"news_correlation": True}},
                purchase_constraint_block=_BLOCK,
            )
            assert mock_hooks.call_args.args[5] == _BLOCK

    def test_fetch_extracts_block_from_pipeline_data(self):
        """_fetch_llm_and_news 从同一契约字段提取并交新闻线程任务。"""
        with patch("src.python.report._llm_news._submit_news_future") as mock_submit:
            mock_fut = MagicMock()
            mock_fut.result.return_value = ([], {}, False)
            mock_submit.return_value = mock_fut
            from src.python.report._llm_news import _fetch_llm_and_news

            _fetch_llm_and_news(
                [],
                {"news_top_count": 10, "penetrated_assets": None},
                None,
                False,
                {"purchase_status_data": {"constraint_block": _BLOCK}},
                True,
                False,
                MagicMock(),
            )
            assert mock_submit.call_args.args[4] == _BLOCK

    def test_chain_entry_signatures_carry_block_param(self):
        """build_news_data / _apply_llm_enhancement 签名携带块形参（透传中段）。"""
        import inspect

        from src.python.report.news_correlation import _apply_llm_enhancement, build_news_data

        for fn in (build_news_data, _apply_llm_enhancement):
            assert "purchase_constraint_block" in inspect.signature(fn).parameters, fn.__name__


# ═══════════════════════════════════════════════════════════════
#  降级成对：辩论 / 自检 缺席面（与完备面一一成对）
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.generate_llm_content", return_value=("<p>观点</p>", False))
@patch("src.python.llm.skeleton.get_llm_config", return_value=dict(_ENABLED))
class TestAbsentBlockFallbackPair(unittest.TestCase):
    """降级成对断言：缺席时辩论/自检 prompt 不含块（与完备面一一对应）。"""

    def test_debate_prompts_absent_block(self, mock_cfg, mock_content):
        """缺省 → 辩论三章 prompt 均不含块。"""
        from src.python.llm.generators import generate_debate_procon

        generate_debate_procon(60_000.0, 55_000.0, 5_000.0, 500.0, 1, {})
        assert mock_content.call_count >= 3
        for call in mock_content.call_args_list:
            texts = [a for a in call.args if isinstance(a, str)] + [
                v for v in call.kwargs.values() if isinstance(v, str)
            ]
            assert not any("【申购限购约束】" in s for s in texts), "缺席时辩论 prompt 意外含块"

    def test_self_review_prompt_absent_block(self, mock_cfg, mock_content):
        """缺省 → 自检 prompt 不含块。"""
        from src.python.llm.generators import generate_self_review

        generate_self_review(
            {"global_macro": "<p>宏观</p>", "expert_review": "<p>策略</p>"},
            [{"code": "011506", "name": "建信高端装备", "market_value": 60_000.0}],
            None,
        )
        texts = [a for a in mock_content.call_args.args if isinstance(a, str)] + [
            v for v in mock_content.call_args.kwargs.values() if isinstance(v, str)
        ]
        assert not any("【申购限购约束】" in s for s in texts), "缺席时自检 prompt 意外含块"

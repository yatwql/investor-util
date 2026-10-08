"""持仓变动复盘提示词注入链路 + 章内归因编排单元测试（双轨：四模块统一附录 + 章内归因块）。

覆盖：
  - 轨 1（四模块统一附录）：generate_all_llm 从契约提取 prompt_block 并分发四模块、
    最终 user prompt 含块、块缺席逐字节回退、辩论 inputs 携带、指纹条件并入；
  - 轨 2（章内归因块）：run_holding_change_review 各准入门 + 成功写回契约
    `llm_review` + 失败登记 + 窗口信号块过滤。

运行：
  pytest src/test/unit/llm/test_holding_change_injection.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.python.llm import generate_all_llm
from src.test.helpers import SynchronousExecutor

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]

_BLOCK = "【持仓变动复盘·变动事件清单（区间净额推断，非逐笔）】\n复盘窗口 08-06 → 10-05：28 个观察期"
_ENABLED = {
    "enabled_llm": {
        "global_macro": True,
        "expert_review": True,
        "health_check": True,
        "penetration_deep": True,
        "holding_change": True,
    }
}
_CONTRACT = {"available": True, "prompt_block": _BLOCK, "llm_review": None}


# ═══════════════════════════════════════════════════════════════
#  轨 1 提取层：契约 → 四模块形参（提取一次，同一实例）
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
        pipeline_data = {"holding_change_data": dict(_CONTRACT)}

        with patch("src.python.llm.holding_change_review.run_holding_change_review") as mock_run:
            generate_all_llm([], [], 0, 0, 0, 0, 0, {}, pipeline_data=pipeline_data)

        for name, mock_fn in [
            ("global_macro", mock_macro),
            ("expert_review", mock_expert),
            ("health_check", mock_health),
            ("penetration_deep", mock_penetration),
        ]:
            kwargs = mock_fn.call_args.kwargs
            assert kwargs.get("holding_change_block") == _BLOCK, f"{name}: 未收到提示词块实例"
        # 归因入口同样以该管线数据被编排层串行调用
        assert mock_run.call_count == 1
        assert mock_run.call_args.args[0] is pipeline_data

    def test_absent_contract_passes_empty_string(self, mock_expert, mock_macro, mock_health, mock_penetration):
        """契约缺席（feature 关闭/准入未过）→ ""（提示词与缓存键双不变）。"""
        self._stubs(mock_expert, mock_macro, mock_health, mock_penetration)

        generate_all_llm([], [], 0, 0, 0, 0, 0, {}, pipeline_data={})

        for name, mock_fn in [
            ("global_macro", mock_macro),
            ("expert_review", mock_expert),
            ("health_check", mock_health),
            ("penetration_deep", mock_penetration),
        ]:
            assert mock_fn.call_args.kwargs.get("holding_change_block") == "", f"{name}: 未回退空串"

    def test_extract_helper_three_states(self, mock_expert, mock_macro, mock_health, mock_penetration):
        """提取助手三态：None 管线 / 契约缺席 / 契约在场。"""
        self._stubs(mock_expert, mock_macro, mock_health, mock_penetration)
        from src.python.llm import extract_holding_change_block

        assert extract_holding_change_block(None) == ""
        assert extract_holding_change_block({}) == ""
        assert extract_holding_change_block({"holding_change_data": dict(_CONTRACT)}) == _BLOCK


# ═══════════════════════════════════════════════════════════════
#  轨 1 传输层：四模块最终 user prompt 含块（LLM 调用 mock 捕获）
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
            fn(**self._call_kwargs(module_key), holding_change_block=_BLOCK)
            texts = self._prompt_texts(mock_content)
            assert any("【持仓变动复盘·变动事件清单" in s for s in texts), f"{module_key}: 最终 prompt 不含块"

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
            assert not any("【持仓变动复盘·变动事件清单" in s for s in texts), f"{module_key}: 缺席时 prompt 意外含块"


# ═══════════════════════════════════════════════════════════════
#  轨 1 辩论面 + 指纹条件并入
# ═══════════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.generate_llm_content", return_value=("<p>观点</p>", False))
@patch("src.python.llm.skeleton.get_llm_config", return_value=dict(_ENABLED))
class TestDebateCarriesBlock(unittest.TestCase):
    """辩论三章 prompt 与指纹 inputs 的提示词块注入。"""

    @patch("src.python.llm.generators.generate_llm_module", return_value=("<p>x</p>", True))
    @patch("src.python.llm.generators.debate_procon_fingerprint", return_value="fp")
    def test_debate_inputs_carry_block(self, mock_fp, mock_module, mock_cfg, mock_content):
        """辩论指纹 inputs 携带块（进提示词必进指纹；与 purchase_block 平行同构）。"""
        from src.python.llm.generators import generate_debate_procon

        generate_debate_procon(0.0, 0.0, 0.0, 0.0, 0, {}, holding_change_block=_BLOCK)
        inputs = mock_fp.call_args.args[0]
        assert inputs.holding_change_block == _BLOCK

    @patch("src.python.llm.generators.generate_llm_module", return_value=("<p>x</p>", True))
    @patch("src.python.llm.generators.debate_procon_fingerprint", return_value="fp")
    def test_debate_inputs_empty_block_by_default(self, mock_fp, mock_module, mock_cfg, mock_content):
        """缺省 → inputs.holding_change_block == ""（回退原键形态）。"""
        from src.python.llm.generators import generate_debate_procon

        generate_debate_procon(0.0, 0.0, 0.0, 0.0, 0, {})
        inputs = mock_fp.call_args.args[0]
        assert inputs.holding_change_block == ""


class TestFingerprintConditionalJoin(unittest.TestCase):
    """指纹条件并入：块空 = 与不带该段逐字节一致；块非空 = 键改变。"""

    @staticmethod
    def _inputs(**kw):
        from src.python.llm.module_fingerprint import ModuleFingerprintInputs

        return ModuleFingerprintInputs(total_mv=100.0, total_profit=10.0, **kw)

    def test_standard_four_modules_conditional(self):
        from src.python.llm.module_fingerprint import (
            expert_review_fingerprint,
            global_macro_fingerprint,
            health_check_fingerprint,
            penetration_deep_fingerprint,
        )

        for fn in (global_macro_fingerprint, expert_review_fingerprint, health_check_fingerprint):
            base = fn(self._inputs())
            assert fn(self._inputs(holding_change_block="")) == base, f"{fn.__name__}: 空块改变了键"
            assert fn(self._inputs(holding_change_block=_BLOCK)) != base, f"{fn.__name__}: 非空块未进键"
        base = penetration_deep_fingerprint(self._inputs())
        assert penetration_deep_fingerprint(self._inputs(holding_change_block="")) == base
        assert penetration_deep_fingerprint(self._inputs(holding_change_block=_BLOCK)) != base

    def test_self_review_conditional(self):
        from src.python.llm.module_fingerprint import self_review_fingerprint

        base = self_review_fingerprint({"a": "<p>x</p>"})
        assert self_review_fingerprint({"a": "<p>x</p>"}, holding_change_block="") == base
        assert self_review_fingerprint({"a": "<p>x</p>"}, holding_change_block=_BLOCK) != base

    def test_holding_change_review_content_addressed(self):
        from src.python.llm.module_fingerprint import holding_change_review_fingerprint

        a = holding_change_review_fingerprint(_BLOCK)
        b = holding_change_review_fingerprint(_BLOCK + "变更")
        assert holding_change_review_fingerprint(_BLOCK) == a, "同内容应同键"
        assert b != a, "事实块变化必须改键"
        assert holding_change_review_fingerprint(_BLOCK, signal_block="S") != a, "信号块必须进键"
        assert holding_change_review_fingerprint(_BLOCK, purchase_block="P") != a, "附录约束块必须进键"


# ═══════════════════════════════════════════════════════════════
#  轨 2：章内归因编排入口
# ═══════════════════════════════════════════════════════════════


class TestRunHoldingChangeReview(unittest.TestCase):
    """run_holding_change_review 准入门 + 成功写回 + 失败登记。"""

    def test_contract_absent_is_zero_behavior(self):
        """契约缺席（feature 关闭）→ 零行为：不调用生成、不写载体。"""
        from src.python.llm.holding_change_review import run_holding_change_review

        with patch("src.python.llm.generators.generate_holding_change_review") as mock_gen:
            assert run_holding_change_review({}, dict(_ENABLED)) is False
            assert run_holding_change_review(None, dict(_ENABLED)) is False
        assert mock_gen.call_count == 0

    def test_module_switch_disabled_skips(self):
        """enabled_llm.holding_change = false → 跳过（TUI/配置层可独立关闭归因）。"""
        from src.python.llm.holding_change_review import run_holding_change_review

        cfg = {"enabled_llm": {"holding_change": False}}
        with patch("src.python.llm.generators.generate_holding_change_review") as mock_gen:
            assert run_holding_change_review({"holding_change_data": dict(_CONTRACT)}, cfg) is False
        assert mock_gen.call_count == 0

    def test_empty_context_block_registers_skip(self):
        """契约在场但事实块为空 → 登记失败原因并跳过。"""
        from src.python.llm.holding_change_review import run_holding_change_review
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        contract = {"available": True, "prompt_block": "", "llm_review": None}
        try:
            with patch("src.python.llm.generators.generate_holding_change_review") as mock_gen:
                assert run_holding_change_review({"holding_change_data": contract}, dict(_ENABLED)) is False
            assert mock_gen.call_count == 0
            assert LLM_MODULE_FAILURE.get("holding_change"), "空事实块应登记失败原因"
        finally:
            LLM_MODULE_FAILURE.pop("holding_change", None)

    def test_success_writes_review_field(self):
        """生成成功 → 写回契约 llm_review（章内渲染就地读取）。"""
        from src.python.llm.holding_change_review import run_holding_change_review

        contract = {"available": True, "prompt_block": _BLOCK, "llm_review": None}
        with patch(
            "src.python.llm.generators.generate_holding_change_review",
            return_value=("## 持仓变动归因\n- 结构变更", False),
        ) as mock_gen:
            ok = run_holding_change_review({"holding_change_data": contract}, dict(_ENABLED), holdings_details=[])
        assert ok is True
        assert contract["llm_review"] == "## 持仓变动归因\n- 结构变更"
        # 事实块以同一实例进生成（进提示词与指纹同源）
        assert mock_gen.call_args.args[0] == _BLOCK

    def test_failure_keeps_none_and_registers(self):
        """生成失败 → llm_review 保持 None（归因块隐藏）+ 登记原因，不外抛。"""
        from src.python.llm.holding_change_review import run_holding_change_review
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        contract = {"available": True, "prompt_block": _BLOCK, "llm_review": None}
        try:
            with patch("src.python.llm.generators.generate_holding_change_review", return_value=(None, False)):
                ok = run_holding_change_review({"holding_change_data": contract}, dict(_ENABLED))
            assert ok is False
            assert contract["llm_review"] is None
            assert LLM_MODULE_FAILURE.get("holding_change")
        finally:
            LLM_MODULE_FAILURE.pop("holding_change", None)

    def test_exception_never_propagates(self):
        """生成抛异常 → 守护吞掉（与 seam 同契约：异常不外抛）。"""
        from src.python.llm.holding_change_review import run_holding_change_review

        contract = {"available": True, "prompt_block": _BLOCK, "llm_review": None}
        with patch("src.python.llm.generators.generate_holding_change_review", side_effect=RuntimeError("boom")):
            assert run_holding_change_review({"holding_change_data": contract}, dict(_ENABLED)) is False
        assert contract["llm_review"] is None

    def test_signal_window_block_filters_by_window(self):
        """窗口信号块：只含窗口内 report_date；窗口外/非 dict 记录剔除；无命中 → \"\"。"""
        from src.python.llm.holding_change_review import _build_signal_window_block

        contract = {"window_start": "20260806T092637", "window_end": "20261005T081511"}
        signals = [
            {
                "report_date": "2026-09-15",
                "subject": "510300",
                "signal_type": "valuation",
                "rating": "低估",
                "direction": 1,
            },
            {
                "report_date": "2026-07-01",
                "subject": "510300",
                "signal_type": "valuation",
                "rating": "高估",
                "direction": -1,
            },
            "not-a-dict",
        ]
        with (
            patch("src.python.core.signal_ledger.is_active", return_value=True),
            patch("src.python.core.signal_ledger.load_signals", return_value=signals),
        ):
            block = _build_signal_window_block(contract)
            assert "2026-09-15" in block
            assert "低估" in block
            assert "2026-07-01" not in block, "窗口外信号不得进块"

        with (
            patch("src.python.core.signal_ledger.is_active", return_value=True),
            patch("src.python.core.signal_ledger.load_signals", return_value=[]),
        ):
            assert _build_signal_window_block(contract) == ""

    def test_signal_block_inactive_returns_empty(self):
        """信号功能关闭 → \"\"（附录零贡献，不进提示词亦不进指纹）。"""
        from src.python.llm.holding_change_review import _build_signal_window_block

        with patch("src.python.core.signal_ledger.is_active", return_value=False):
            assert _build_signal_window_block({"window_start": "20260806", "window_end": "20261005"}) == ""


# ═══════════════════════════════════════════════════════════════
#  注册表 / 配置对齐
# ═══════════════════════════════════════════════════════════════


class TestRegistryAlignment(unittest.TestCase):
    """模块登记与 llm_settings 默认键对齐（复用既有机制的必要条件）。"""

    def test_registry_entry_exists(self):
        from src.python.core.registry import get_llm_module_name, get_known_llm_settings_keys

        assert get_llm_module_name("holding_change") == "持仓变动复盘归因"
        keys = get_known_llm_settings_keys()
        assert "system_prompt_holding_change" in keys
        assert "max_tokens_holding_change" in keys

    def test_settings_defaults_aligned(self):
        from src.python.config._llm_settings_defaults import _DEFAULT_LLM_SETTINGS
        from src.python.core.registry import get_known_llm_settings_keys

        assert _DEFAULT_LLM_SETTINGS["enabled_llm"].get("holding_change") is True, "归因默认开（章本体由 feature 控制）"
        known = get_known_llm_settings_keys()
        for key in _DEFAULT_LLM_SETTINGS:
            if key.endswith("_holding_change"):
                assert key in known, f"{key} 未在注册表登记为合法键"
                break
        else:
            pytest.fail("默认设置缺少 *_holding_change 键组")

    def test_not_in_dispatch_module_fns(self):
        """刻意不进 _build_module_fns（串行后置，无独立并行调度语义）。"""
        from src.python.llm import _llm_dispatch

        fns = _llm_dispatch._build_module_fns({}, {}, 0.0, 0.0, 0.0, 0.0, 0, {}, None, None, None, False)
        assert "holding_change" not in fns, "归因模块应由编排层串行调用，不得进线程池调度"


# ═══════════════════════════════════════════════════════════════
#  轨 2 提示词内容：系统提示框架 + user prompt 组装
# ═══════════════════════════════════════════════════════════════


class TestHoldingChangePrompts(unittest.TestCase):
    """系统提示与 user prompt 的关键结构（账户结构变更框架 + 事实/信号块组装）。"""

    def test_system_prompt_has_structure_change_framework(self):
        from src.python.llm.prompts import _SYSTEM_HOLDING_CHANGE_REVIEW

        assert "账户/数据结构变更" in _SYSTEM_HOLDING_CHANGE_REVIEW
        assert "区间净额推断" in _SYSTEM_HOLDING_CHANGE_REVIEW
        assert "投资建议" in _SYSTEM_HOLDING_CHANGE_REVIEW, "必须显式禁止投资建议"

    def test_user_prompt_assembles_context_and_signal(self):
        from src.python.llm.prompts import _build_holding_change_review_prompt

        text = _build_holding_change_review_prompt(_BLOCK, "SIG-BLOCK")
        assert _BLOCK in text
        assert "SIG-BLOCK" in text

        text_no_signal = _build_holding_change_review_prompt(_BLOCK)
        assert _BLOCK in text_no_signal
        assert "SIG-BLOCK" not in text_no_signal


# ═══════════════════════════════════════════════════════════════
#  串行后置入口 http_client 缺省 → 漏斗兜底客户端（端到端）
# ═══════════════════════════════════════════════════════════════


class TestRunHoldingChangeReviewFallbackClient(unittest.TestCase):
    """编排层串行调用不注入 http_client 时，归因仍须真实到达 provider 层。

    回归背景：``run_holding_change_review`` → ``generate_holding_change_review``
    全链不传 ``http_client``，None 直达 provider 层 ``assert client is not
    None`` 秒败，且异常被链路吞掉 → 返回 False、归因内容静默丢失。
    """

    def test_end_to_end_builds_and_closes_client(self):
        """全链跑通：返回 True 且 provider 层收到一次性真实客户端（用后关闭）。"""
        from src.python.llm.holding_change_review import run_holding_change_review

        contract = {"available": True, "prompt_block": _BLOCK, "llm_review": None}
        cfg = dict(_ENABLED)
        cfg.update({"provider": "claude", "api_key": "sk-test"})
        with (
            patch("src.python.core.signal_ledger.is_active", return_value=False),
            patch(
                "src.python.llm._api_claude.call_llm_with_retry",
                return_value=("## 持仓变动归因\n\n- 结构变更", {"input_tokens": 10, "output_tokens": 5}),
            ) as mock_retry,
        ):
            ok = run_holding_change_review({"holding_change_data": contract}, cfg, force=True, holdings_details=[])

        assert ok is True, "归因调用失败会静默返回 False，此处必须证明全链跑通"
        assert contract["llm_review"] and "结构变更" in contract["llm_review"]
        client = mock_retry.call_args.kwargs["client"]
        assert isinstance(client, httpx.Client), "兜底必须是真实客户端而非 None"
        assert client.is_closed, "一次性兜底客户端应在调用结束后关闭"

    def test_end_to_end_registers_failure_when_provider_rejects(self):
        """provider 层拒绝（模拟断言失败语义）→ 返回 False + 登记原因，不外抛。"""
        from src.python.llm.holding_change_review import run_holding_change_review
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        contract = {"available": True, "prompt_block": _BLOCK, "llm_review": None}
        cfg = dict(_ENABLED)
        cfg.update({"provider": "claude", "api_key": "sk-test"})
        try:
            with (
                patch("src.python.core.signal_ledger.is_active", return_value=False),
                patch("src.python.llm._api_claude.call_llm_with_retry", return_value=(None, None)),
            ):
                ok = run_holding_change_review({"holding_change_data": contract}, cfg, force=True, holdings_details=[])
            assert ok is False
            assert contract["llm_review"] is None
            assert LLM_MODULE_FAILURE.get("holding_change"), "失败须登记可观测原因"
        finally:
            LLM_MODULE_FAILURE.pop("holding_change", None)

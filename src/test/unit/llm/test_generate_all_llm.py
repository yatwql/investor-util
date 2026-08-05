"""LLM 生成编排入口单元测试。

测试目标：
  - generate_all_llm — force 参数透传
  - generate_* 函数传递 llm_config 参数
  - generate_all_llm 缓存预检

运行：
  pytest src/test/unit/llm/test_generate_all_llm.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.llm import (
    generate_all_llm,
)
from src.python.llm.generators import (
    generate_expert_review,
    generate_global_macro,
    generate_health_check,
    generate_penetration_deep_analysis,
)
from src.test.helpers import SynchronousExecutor

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


# ═══════════════════════════════════════════════════════════
#  generate_all_llm force passthrough
# ═══════════════════════════════════════════════════════════


@patch("src.python.llm.generators_orchestrator.generate_penetration_deep_analysis")
@patch("src.python.llm.generators_orchestrator.generate_health_check")
@patch("src.python.llm.generators_orchestrator.generate_global_macro")
@patch("src.python.llm.generators_orchestrator.generate_expert_review")
class TestGenerateAllLlm(unittest.TestCase):
    """测试并行生成函数。"""

    @classmethod
    def setUpClass(cls) -> None:
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
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
        cls._cfg_patcher.stop()

    def test_force_passthrough(self, mock_expert: MagicMock, mock_macro: MagicMock, mock_health: MagicMock, mock_penetration: MagicMock) -> None:
        mock_macro.return_value = ("<p>宏</p>", False)
        mock_expert.return_value = ("<p>策略</p>", False)
        mock_health.return_value = ("<p>体检</p>", False)
        mock_penetration.return_value = ("<p>穿透</p>", False)

        macro, expert, health, penetration, mc, ec, hc, pc, *_ = generate_all_llm([], [], 0, 0, 0, 0, 0, {}, force=True)

        self.assertEqual(macro, "<p>宏</p>")
        self.assertEqual(expert, "<p>策略</p>")
        self.assertEqual(health, "<p>体检</p>")
        self.assertEqual(penetration, "<p>穿透</p>")
        self.assertFalse(mc)
        self.assertFalse(ec)
        self.assertFalse(hc)
        self.assertFalse(pc)
        # 验证 force=True 被透传
        _, kwargs_m = mock_macro.call_args
        _, kwargs_e = mock_expert.call_args
        self.assertTrue(kwargs_m.get("force"))
        self.assertTrue(kwargs_e.get("force"))

    def test_force_false_default(self, mock_expert: MagicMock, mock_macro: MagicMock, mock_health: MagicMock, mock_penetration: MagicMock) -> None:
        mock_macro.return_value = ("<p>m</p>", False)
        mock_expert.return_value = ("<p>e</p>", False)
        mock_health.return_value = ("<p>h</p>", False)
        mock_penetration.return_value = ("<p>p</p>", False)

        macro, expert, health, penetration, mc, ec, hc, pc, *_ = generate_all_llm([], [], 0, 0, 0, 0, 0, {})

        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(penetration)
        self.assertFalse(mc)
        self.assertFalse(ec)
        self.assertFalse(hc)
        self.assertFalse(pc)
        _, kwargs_m = mock_macro.call_args
        self.assertFalse(kwargs_m.get("force"))

    def test_extra_valid_codes_passed_for_penetration_aware_modules(
        self, mock_expert: MagicMock, mock_macro: MagicMock, mock_health: MagicMock, mock_penetration: MagicMock
    ) -> None:
        """智囊团/持仓体检/穿透深度校验时传入穿透代码为额外有效代码，全球政经不传。

        三个模块的提示词均含【穿透 TOP10】数据（_format_penetration_block），
        LLM 会引用穿透股票代码（如宁德时代 300750、阳光电源 300274）。它们非直接
        持仓但属组合穿透范围，品种存在性校验须视为有效，否则误报"不在当前持仓中"。
        全球政经提示词不含穿透数据，保持严格校验（extra_valid_codes=None）。
        """
        mock_macro.return_value = ("<p>全球宏观分析</p>", False)
        mock_expert.return_value = ("<p>智囊团提及穿透品种 300750、300274。</p>", False)
        mock_health.return_value = ("<p>体检涉及穿透代码 300750。</p>", False)
        mock_penetration.return_value = ("<p>穿透深度聚焦 300750。</p>", False)

        _labels = {
            "global_macro": "全球政经局势",
            "expert_review": "智囊团深度复盘",
            "health_check": "持仓体检报告",
            "penetration_deep": "穿透深度分析",
        }
        fc_calls: list[tuple[str, object]] = []

        def _fake_fact_check(html, holdings, module_label="", extra_valid_codes=None, **kwargs):
            fc_calls.append((module_label, extra_valid_codes))
            return html, ""

        _penetrated = [
            {"name": "宁德时代", "codes": ["300750"], "mv": 100.0, "ratio": 10.0, "sector": "电力设备"},
            {"name": "阳光电源", "codes": ["300274"], "mv": 80.0, "ratio": 8.0, "sector": "电力设备"},
        ]
        with patch("src.python.llm.generators_orchestrator.run_fact_check", side_effect=_fake_fact_check), \
             patch("src.python.llm.generators_orchestrator.get_llm_module_names", return_value=_labels):
            generate_all_llm(
                {}, {}, 100000, 50000, 50000, 100, 10, {"股票": 10},
                penetrated_assets=_penetrated,
                holdings_details=[{"code": "600519", "name": "贵州茅台", "market_value": 50000, "cost": 40000}],
                force=True,
            )

        self.assertEqual(len(fc_calls), 4)
        by_label = dict(fc_calls)
        self.assertEqual(by_label["智囊团深度复盘"], {"300750", "300274"})
        self.assertEqual(by_label["持仓体检报告"], {"300750", "300274"})
        self.assertEqual(by_label["穿透深度分析"], {"300750", "300274"})
        self.assertIsNone(by_label["全球政经局势"])


# ═══════════════════════════════════════════════════════════
#  generate_* 传递 llm_config 参数
# ═══════════════════════════════════════════════════════════


class TestGenerateFunctionsAcceptLlmConfig(unittest.TestCase):
    """测试 generate_* 函数传递 llm_config 参数。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._exec_patcher = patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators_orchestrator.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
    """测试 generate_* 函数接受外部 llm_config 参数。"""

    @patch("src.python.llm.skeleton.generate_llm_content")
    def test_global_macro_uses_passed_config(
        self, mock_gen: MagicMock,
    ) -> None:
        """传入 llm_config → 被 _generate_llm_content 接收。"""
        from src.python.llm.generators import generate_global_macro
        mock_gen.return_value = ("<p>结果</p>", False)
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_global_macro": False}
        result, cached = generate_global_macro(
            a_indices={}, us_indices={}, total_mv=0, total_profit=0, total_cost=0,
            categories={}, llm_config=llm_config,
        )
        self.assertEqual(result, "<p>结果</p>")
        # 验证传递给 _generate_llm_content 的第一个参数是传入的 llm_config
        self.assertIs(mock_gen.call_args[0][0], llm_config)

    @patch("src.python.llm.skeleton.generate_llm_content")
    def test_expert_review_uses_passed_config(
        self, mock_gen: MagicMock,
    ) -> None:
        """gen_expert_review 传递 llm_config 到 _generate_llm_content。"""
        from src.python.llm.generators import generate_expert_review
        mock_gen.return_value = ("<p>复盘</p>", False)
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_expert_review": False}
        result, cached = generate_expert_review(
            total_mv=0, total_cost=0, total_profit=0, total_today_profit=0,
            holdings_count=1, categories={}, llm_config=llm_config,
        )
        self.assertEqual(result, "<p>复盘</p>")
        self.assertIs(mock_gen.call_args[0][0], llm_config)

    @patch("src.python.llm.skeleton.generate_llm_content")
    def test_health_check_uses_passed_config(
        self, mock_gen: MagicMock,
    ) -> None:
        """gen_health_check 传递 llm_config 到 _generate_llm_content。"""
        from src.python.llm.generators import generate_health_check
        mock_gen.return_value = ("<p>体检</p>", False)
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_health_check": False}
        result, cached = generate_health_check(
            total_mv=0, total_cost=0, total_profit=0, total_today_profit=0,
            holdings_count=1, categories={}, llm_config=llm_config,
        )
        self.assertEqual(result, "<p>体检</p>")
        self.assertIs(mock_gen.call_args[0][0], llm_config)

    @patch("src.python.llm.skeleton.generate_llm_content")
    def test_penetration_uses_passed_config(
        self, mock_gen: MagicMock,
    ) -> None:
        """gen_penetration_deep_analysis 传递 llm_config。"""
        from src.python.llm.generators import generate_penetration_deep_analysis
        mock_gen.return_value = ("<p>穿透</p>", False)
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_penetration_deep": False}
        result, cached = generate_penetration_deep_analysis(
            total_mv=0, total_cost=0, total_profit=0, total_today_profit=0,
            holdings_count=1, categories={}, llm_config=llm_config,
        )
        self.assertEqual(result, "<p>穿透</p>")
        self.assertIs(mock_gen.call_args[0][0], llm_config)


# ═══════════════════════════════════════════════════════════
#  generate_all_llm 缓存预检
# ═══════════════════════════════════════════════════════════


@patch("src.python.llm.generators_orchestrator.generate_penetration_deep_analysis")
@patch("src.python.llm.generators_orchestrator.generate_health_check")
@patch("src.python.llm.generators_orchestrator.generate_global_macro")
@patch("src.python.llm.generators_orchestrator.generate_expert_review")
class TestGenerateAllLlmCachePrecheck(unittest.TestCase):
    """测试 generate_all_llm 缓存预检行为。"""

    @classmethod
    def setUpClass(cls) -> None:
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
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
        cls._cfg_patcher.stop()

    CACHED_CONTENT = '<p>缓存内容</p><p style="color:#888;font-size:12px">本次使用LLM缓存</p>'

    @patch("src.python.llm.generators_orchestrator.cache_get")
    def test_all_cached_no_threads(
        self, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """全部缓存命中 → 不调用 generate_* 函数。"""
        mock_cache_get.return_value = self.CACHED_CONTENT
        macro, expert, health, pen, mc, ec, hc, pc, *_ = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
        )
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)
        self.assertTrue(mc)
        self.assertTrue(ec)
        self.assertTrue(hc)
        self.assertTrue(pc)
        mock_macro.assert_not_called()
        mock_expert.assert_not_called()
        mock_health.assert_not_called()
        mock_penetration.assert_not_called()

    @patch("src.python.llm.generators_orchestrator.cache_get")
    def test_none_cached_all_threads(
        self, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """全部未缓存 → 调用全部 generate_* 函数。"""
        mock_cache_get.return_value = None
        mock_macro.return_value = ("<p>宏</p>", False)
        mock_expert.return_value = ("<p>策略</p>", False)
        mock_health.return_value = ("<p>体检</p>", False)
        mock_penetration.return_value = ("<p>穿透</p>", False)

        macro, expert, health, pen, mc, ec, hc, pc, *_ = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
        )
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)
        mock_macro.assert_called_once()
        mock_expert.assert_called_once()
        mock_health.assert_called_once()
        mock_penetration.assert_called_once()

    @patch("src.python.llm.generators_orchestrator.cache_get")
    def test_force_skips_cache(
        self, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """force=True → 跳过缓存预检，全部线程生成。"""
        mock_cache_get.return_value = self.CACHED_CONTENT
        mock_macro.return_value = ("<p>宏</p>", False)
        mock_expert.return_value = ("<p>策略</p>", False)
        mock_health.return_value = ("<p>体检</p>", False)
        mock_penetration.return_value = ("<p>穿透</p>", False)

        macro, expert, health, pen, mc, ec, hc, pc, *_ = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
            force=True,
        )
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)
        # force=True 时 force_flag=True → can_cache_* 全为 False → 不走缓存
        mock_macro.assert_called_once()
        mock_expert.assert_called_once()
        mock_health.assert_called_once()
        mock_penetration.assert_called_once()

    @patch("src.python.llm.generators_orchestrator.cache_get")
    def test_partial_cache_some_threads(
        self, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """部分缓存命中 → 仅未命中的模块提交线程。"""
        # 模拟 macro 和 expert 命中缓存，health 和 penetration 未命中
        def _side_effect(key, ttl=None):
            if "global_macro" in key or "expert_review" in key:
                return self.CACHED_CONTENT
            return None
        mock_cache_get.side_effect = _side_effect
        mock_health.return_value = ("<p>体检</p>", False)
        mock_penetration.return_value = ("<p>穿透</p>", False)

        macro, expert, health, pen, mc, ec, hc, pc, *_ = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
        )
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)
        self.assertTrue(mc)
        self.assertTrue(ec)
        self.assertFalse(hc)
        self.assertFalse(pc)
        mock_macro.assert_not_called()
        mock_expert.assert_not_called()
        mock_health.assert_called_once()
        mock_penetration.assert_called_once()

    @patch("src.python.llm.generators_orchestrator.cache_get")
    @patch("src.python.llm.api_base.record_per_module")
    def test_cache_hit_records_per_module(
        self, mock_record: MagicMock, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """全部缓存命中 → 为每个模块记录 per_module 用量（cached=True）。"""
        mock_cache_get.return_value = self.CACHED_CONTENT

        macro, expert, health, pen, mc, ec, hc, pc, *_ = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
        )

        self.assertEqual(mock_record.call_count, 4)
        expected_keys = {"global_macro", "expert_review", "health_check", "penetration_deep"}
        actual_keys = {call[0][0] for call in mock_record.call_args_list}
        self.assertEqual(actual_keys, expected_keys)
        # 每个调用必须带 cached=True
        for call in mock_record.call_args_list:
            kwargs = call[1] if len(call) > 1 else {}
            cached = kwargs.get("cached") if "cached" in kwargs else (call[0][2] if len(call[0]) > 2 else False)
            self.assertTrue(cached, f"模块 {call[0][0]} 的 cached 不是 True")

    @patch("src.python.llm.api_base.record_per_module")
    def test_partial_cache_records_per_module(
        self, mock_record: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """部分缓存命中 → 仅缓存命中模块记录 per_module。"""
        # 模拟 precheck 缓存：需要 mock cache_get 但该函数在 @patch 顺序中未直接传入
        # 直接调用 _precheck_one_cache 验证，而非 generate_all_llm
        from src.python.llm.generators_orchestrator import _precheck_one_cache

        cache_info = {"key": "llm_global_macro_fp", "ttl": 3600,
                       "can_cache": True, "thinking_key": "thinking_enabled_global_macro"}
        llm_config = {"model": "test-model", "endpoint": "https://test.endpoint"}

        with patch("src.python.llm.generators_orchestrator.cache_get", return_value=self.CACHED_CONTENT):
            result, from_cache = _precheck_one_cache(cache_info, llm_config, "global_macro")

        self.assertIsNotNone(result)
        self.assertTrue(from_cache)
        # 当缓存内容不含模型名时，使用 llm_config["model"] 作为模型名
        mock_record.assert_called_once_with(
            "global_macro", "test-model", cached=True,
            thinking=False, endpoint="https://test.endpoint",
        )

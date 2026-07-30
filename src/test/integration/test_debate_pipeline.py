"""辩论模式集成测试 — 完整管线验证。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/integration/test_debate_pipeline.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration]

# 预检结果：所有模块"无需缓存，需要工作线程生成"
_NONE_CACHED = {
    "global_macro": {"result": None, "cached": False},
    "expert_review": {"result": None, "cached": False},
    "health_check": {"result": None, "cached": False},
    "penetration_deep": {"result": None, "cached": False},
}

# 模拟 _dispatch_llm_workers 返回：所有模块成功
_DISPATCH_OK = {
    "global_macro": {"result": "全球宏观", "cached": False},
    "expert_review": {"result": "专家分析", "cached": False},
    "health_check": {"result": "持仓体检", "cached": False},
    "penetration_deep": {"result": "穿透分析", "cached": False},
}


def _make_dispatch_mock(debate_info: dict | None = None):
    """创建 _dispatch_llm_workers 的 mock，按需填充 debate_info 容器。"""
    def _side_effect(needs, llm_config, force, *args, **kwargs):
        container = kwargs.get("_debate_info_container")
        if container is not None and debate_info is not None:
            container[0] = debate_info
        return dict(_DISPATCH_OK)
    return _side_effect


class TestDebatePipelineBackwardCompat(unittest.TestCase):
    """所有 Flag 关闭时输出 8 元组（不含 debate_info）。"""

    @patch("src.python.llm.generators_orchestrator.get_llm_config")
    @patch("src.python.config.features.is_feature_enabled")
    @patch("src.python.llm.generators_orchestrator._precheck_all_modules")
    def test_all_flags_off_returns_8tuple(
        self,
        mock_precheck,
        mock_feature,
        mock_config,
    ):
        """所有 Feature Flag 为 False → 返回 8 元组。"""
        mock_config.return_value = {"cache_enabled_expert_review": True,
                                    "enabled_llm": {"global_macro": True,
                                                    "expert_review": True,
                                                    "health_check": True,
                                                    "penetration_deep": True}}
        mock_precheck.return_value = _NONE_CACHED
        mock_feature.return_value = False  # 所有 flag 关

        from src.python.llm.generators_orchestrator import generate_all_llm

        result = generate_all_llm(
            a_indices={},
            us_indices={},
            total_mv=100000,
            total_cost=80000,
            total_profit=20000,
            total_today_profit=1000,
            holdings_count=1,
            categories={"股票": 1},
        )

        # Flag 全关时返回 8 元组
        self.assertEqual(len(result), 8)


class TestDebatePipelineProconEnabled(unittest.TestCase):
    """正反辩论启用时 debate_info 正确返回。"""

    @patch("src.python.llm.generators_orchestrator.get_llm_config")
    @patch("src.python.config.features.is_feature_enabled")
    @patch("src.python.llm.generators_orchestrator._precheck_all_modules")
    def test_procon_enabled_returns_debate_info(
        self,
        mock_precheck,
        mock_feature,
        mock_config,
    ):
        """正反辩论启用 → 返回 9 元组，含 debate_info。"""
        mock_config.return_value = {"cache_enabled_expert_review": True,
                                    "enabled_llm": {"global_macro": True,
                                                    "expert_review": True,
                                                    "health_check": True,
                                                    "penetration_deep": True}}
        mock_precheck.return_value = _NONE_CACHED

        # 正反辩论启用状态 + 用 side_effect 模拟 dispatch 填充 debate_info 容器
        mock_feature.side_effect = lambda name: name == "llm_debate_procon"

        _debate_info = {"pro_text": "白脸观点", "con_text": "黑脸观点", "mode_label": "\U0001f9ea 辩论模式"}

        with patch("src.python.llm.generators_orchestrator._dispatch_llm_workers") as mock_dispatch:
            mock_dispatch.side_effect = _make_dispatch_mock(debate_info=_debate_info)

            from src.python.llm.generators_orchestrator import generate_all_llm

            result = generate_all_llm(
                a_indices={},
                us_indices={},
                total_mv=100000,
                total_cost=80000,
                total_profit=20000,
                total_today_profit=1000,
                holdings_count=1,
                categories={"股票": 1},
            )

        # 正反辩论启用 → 9 元组
        self.assertEqual(len(result), 9)
        debate_info = result[8]
        self.assertIsNotNone(debate_info)
        if debate_info:
            self.assertIn("pro_text", debate_info)
            self.assertIn("con_text", debate_info)
            self.assertIn("mode_label", debate_info)


class TestDebatePipelineSynthesisFallback(unittest.TestCase):
    """正反辩论启用 + debate 全部失败 → 降级普通模式。"""

    @patch("src.python.llm.generators_orchestrator.get_llm_config")
    @patch("src.python.config.features.is_feature_enabled")
    @patch("src.python.llm.generators_orchestrator._precheck_all_modules")
    def test_synthesis_none_fallback(
        self,
        mock_precheck,
        mock_feature,
        mock_config,
    ):
        """debate 全部失败 → 降级普通 expert_review。"""
        mock_config.return_value = {"cache_enabled_expert_review": True,
                                    "enabled_llm": {"global_macro": True,
                                                    "expert_review": True,
                                                    "health_check": True,
                                                    "penetration_deep": True}}
        mock_precheck.return_value = _NONE_CACHED
        mock_feature.return_value = True  # debate flag 开

        with patch("src.python.llm.generators_orchestrator._dispatch_llm_workers") as mock_dispatch:
            # 模拟 dispatch：不填充 debate_info（debate 全部失败）
            mock_dispatch.side_effect = _make_dispatch_mock(debate_info=None)

            from src.python.llm.generators_orchestrator import generate_all_llm

            result = generate_all_llm(
                a_indices={},
                us_indices={},
                total_mv=100000,
                total_cost=80000,
                total_profit=20000,
                total_today_profit=1000,
                holdings_count=1,
                categories={"股票": 1},
            )

            # 应返回 8 或 9 元组
            self.assertGreaterEqual(len(result), 8)

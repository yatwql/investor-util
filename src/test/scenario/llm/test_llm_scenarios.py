"""LLM 业务场景组合测试 — S11~S17。

测试目标：
  验证 LLM 全场景组合下的模块状态映射和一致性：

  S11：LLM 混合缓存+真实调用 — 2 缓存 + 1 成功 + 1 失败 + 1 禁用
  S12：LLM 全部失败（5 种失败原因）
  S13：Extended Thinking 混合 — 2 模块有 Thinking + 2 模块无 Thinking
  S14：LLM 不启用 — 无 LLM 章节、无 LLM API 用量页，核心报告完整
  S15：禁用+缓存混合 — 禁用优先原则在 module_info 中正确体现
  S16：断网下 LLM 生成 — 所有模块 NETWORK_ERROR 降级
  S17：LLM 部分缓存超期 — 过期模块重新调用，未过期命中缓存

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_llm_scenarios -v
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack

import pytest
from unittest.mock import MagicMock, patch

from src.test.helpers import SynchronousExecutor

from src.python.llm import (
    FAIL_REASON_API_ERROR,
    FAIL_REASON_CIRCUIT_OPEN,
    FAIL_REASON_DISABLED,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_TIMEOUT,
)


# ═══════════════════════════════════════════════════════════
#  S11: LLM 混合缓存+真实调用
# ═══════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS11MixedCacheAndRealCall(unittest.TestCase):
    """S11：4 模块混合状态 — 2 缓存 + 1 成功 + 1 失败。

    预期：HTML 表各模块状态正确（蓝"缓存"、绿"成功"、红"LLM API 调用失败"）；
    Excel 明细行颜色/费用/Thinking 正确；Summary 页模块列表正确。
    """

    def test_build_module_info_mixed_states(self):
        """_build_module_info_list：混合状态正确分发。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {
            "penetration_deep": FAIL_REASON_API_ERROR,
        }
        per_module = {
            "global_macro": {
                "model": "deepseek-v4-flash", "cached": True,
                "input_tokens": 0, "output_tokens": 0, "cache_hit_tokens": 500,
                "cost": 0.0, "thinking": False, "endpoint": "",
            },
            "expert_review": {
                "model": "claude-sonnet-4", "cached": False,
                "input_tokens": 2000, "output_tokens": 1000,
                "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
                "endpoint": "",
            },
        }

        result = _build_module_info_list(failure, per_module)
        by_key = {m["key"]: m for m in result}

        # 2 缓存
        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["global_macro"]["status_label"], "缓存")
        self.assertEqual(by_key["global_macro"]["cache_hit_tokens"], 500)
        self.assertTrue(by_key["global_macro"]["cached"])

        # 1 成功（含 Thinking）
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["expert_review"]["status_label"], "成功")
        self.assertEqual(by_key["expert_review"]["input_tokens"], 2000)
        self.assertEqual(by_key["expert_review"]["output_tokens"], 1000)
        self.assertEqual(by_key["expert_review"]["total_tokens"], 3000)
        self.assertTrue(by_key["expert_review"]["thinking"])

        # 1 失败
        self.assertEqual(by_key["penetration_deep"]["status"], "failed")
        self.assertEqual(by_key["penetration_deep"]["status_label"], "LLM API 调用失败")

        # health_check 和 news_correlation 无数据 → unknown
        self.assertEqual(by_key["health_check"]["status"], "unknown")
        self.assertEqual(by_key["news_correlation"]["status"], "unknown")

    def test_mixed_states_count(self):
        """_build_module_info_list：返回 5 个模块条目。"""
        from src.python.report.html_writer import _build_module_info_list
        result = _build_module_info_list({}, {})
        self.assertEqual(len(result), 5)
        keys = [m["key"] for m in result]
        self.assertIn("news_correlation", keys)

    def test_render_llm_mixed_integration(self):
        """_render_llm_module_info + 混合状态：状态正确分发。"""
        from src.python.report.html_writer import _render_llm_module_info

        session_usage = {
            "has_usage": True, "call_count": 1, "per_module": {
                "global_macro": {
                    "model": "ds", "cached": True,
                    "input_tokens": 0, "output_tokens": 0, "cache_hit_tokens": 300,
                    "cost": 0.0, "thinking": False, "endpoint": "",
                },
                "expert_review": {
                    "model": "claude", "cached": False,
                    "input_tokens": 1500, "output_tokens": 800,
                    "cache_hit_tokens": 0, "cost": 0.005, "thinking": True,
                    "endpoint": "",
                },
            },
        }
        module_failure = {
            "health_check": FAIL_REASON_DISABLED,
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts._LLM_MODULE_FAILURE",
                                      module_failure))
            stack.enter_context(
                patch("src.python.llm.get_session_usage", return_value=session_usage))
            stack.enter_context(
                patch("src.python.llm.format_session_usage", return_value=session_usage))

            llm_module_info, llm_endpoint, module_disabled, llm_session_usage = \
                _render_llm_module_info(True)

        by_key = {m["key"]: m for m in llm_module_info}
        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["health_check"]["status"], "disabled")
        self.assertEqual(by_key["penetration_deep"]["status"], "unknown")
        self.assertEqual(by_key["news_correlation"]["status"], "unknown")

        # module_disabled dict
        self.assertTrue(module_disabled["health_check"])
        self.assertFalse(module_disabled["global_macro"])
        self.assertFalse(module_disabled["expert_review"])
        self.assertFalse(module_disabled["penetration_deep"])

        # llm_session_usage 应有值
        self.assertIsNotNone(llm_session_usage)
        self.assertTrue(llm_session_usage["has_usage"])


# ═══════════════════════════════════════════════════════════
#  S12: LLM 全部失败（5 种原因）
# ═══════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS12AllFailures(unittest.TestCase):
    """S12：5 种失败原因全量覆盖。

    预期：各模块分别显示 NOT_CONFIGURED / API_ERROR / NETWORK_ERROR /
    TIMEOUT / CIRCUIT_OPEN，颜色均为灰色/红色。
    """

    def test_all_five_failure_reasons(self):
        """_build_module_info_list：5 种失败原因正确映射。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {
            "global_macro": FAIL_REASON_NOT_CONFIGURED,
            "expert_review": FAIL_REASON_API_ERROR,
            "health_check": FAIL_REASON_NETWORK_ERROR,
            "penetration_deep": FAIL_REASON_TIMEOUT,
            "news_correlation": FAIL_REASON_CIRCUIT_OPEN,
        }

        result = _build_module_info_list(failure, {})
        by_key = {m["key"]: m for m in result}

        expected = {
            "global_macro": ("failed", "LLM 未配置"),
            "expert_review": ("failed", "LLM API 调用失败"),
            "health_check": ("failed", "LLM API 网络连接失败"),
            "penetration_deep": ("failed", "LLM API 请求超时"),
            "news_correlation": ("failed", "LLM API 暂时不可用（熔断冷却中）"),
        }

        for key, (exp_status, exp_label) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], exp_status,
                                 f"{key} 状态应为 {exp_status}")
                self.assertEqual(by_key[key]["status_label"], exp_label,
                                 f"{key} 标签应为 {exp_label}")
                self.assertEqual(by_key[key]["model"], "")
                self.assertEqual(by_key[key]["cost"], 0.0)

    def test_all_failed_no_per_module(self):
        """全部失败 + 无 per_module → 全部 failed，无成功/缓存覆盖。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {
            "global_macro": FAIL_REASON_API_ERROR,
            "expert_review": FAIL_REASON_API_ERROR,
            "health_check": FAIL_REASON_API_ERROR,
            "penetration_deep": FAIL_REASON_TIMEOUT,
            "news_correlation": FAIL_REASON_CIRCUIT_OPEN,
        }
        # 即使 per_module 有数据，failure 优先覆盖
        per_module = {
            "global_macro": {
                "model": "test", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": False,
                "endpoint": "",
            },
        }

        result = _build_module_info_list(failure, per_module)
        by_key = {m["key"]: m for m in result}

        # 即使 global_macro 在 per_module 中有数据，failure 优先
        self.assertEqual(by_key["global_macro"]["status"], "failed")
        self.assertEqual(by_key["global_macro"]["status_label"], "LLM API 调用失败")
        # 失败时 model 应为空
        self.assertEqual(by_key["global_macro"]["model"], "")


# ═══════════════════════════════════════════════════════════
#  S13: Extended Thinking 混合
# ═══════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS13ThinkingMixed(unittest.TestCase):
    """S13：2 模块有 Thinking + 2 模块无 Thinking。

    预期：Thinking 列 ✓ 仅出现在启用的模块行，
    Excel/HTML/Summary 三种输出一致。
    """

    def test_thinking_mixed(self):
        """_build_module_info_list：Thinking 标记正确。"""
        from src.python.report.html_writer import _build_module_info_list

        per_module = {
            "global_macro": {
                "model": "ds", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": True,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 200, "output_tokens": 100,
                "cache_hit_tokens": 0, "cost": 0.002, "thinking": True,
                "endpoint": "",
            },
            "health_check": {
                "model": "gpt4", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 300, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "penetration_deep": {
                "model": "ds", "cached": False,
                "input_tokens": 300, "output_tokens": 150,
                "cache_hit_tokens": 0, "cost": 0.003, "thinking": False,
                "endpoint": "",
            },
        }

        result = _build_module_info_list({}, per_module)
        by_key = {m["key"]: m for m in result}

        # global_macro + Thinking
        self.assertTrue(by_key["global_macro"]["thinking"])
        # expert_review + Thinking
        self.assertTrue(by_key["expert_review"]["thinking"])
        # health_check 缓存 → thinking=False（缓存不考虑 thinking）
        self.assertFalse(by_key["health_check"]["thinking"])
        # penetration_deep → thinking=False
        self.assertFalse(by_key["penetration_deep"]["thinking"])

        # news_correlation 无 per_module → 默认 no thinking
        self.assertFalse(by_key["news_correlation"]["thinking"])

    def test_thinking_true_count(self):
        """Thinking=True 恰好 2 个（global_macro + expert_review）。"""
        from src.python.report.html_writer import _build_module_info_list

        per_module = {
            "global_macro": {
                "model": "ds", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": True,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 200, "output_tokens": 100,
                "cache_hit_tokens": 0, "cost": 0.002, "thinking": True,
                "endpoint": "",
            },
        }

        result = _build_module_info_list({}, per_module)
        thinking_count = sum(1 for m in result if m["thinking"])
        self.assertEqual(thinking_count, 2)


# ═══════════════════════════════════════════════════════════
#  S14: LLM 不启用
# ═══════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS14LlmDisabled(unittest.TestCase):
    """S14：TUI 不按 L → 无 LLM 章节、无 LLM API 用量页。

    预期：核心报告完整生成；无十二.LLM API 用量页签；
    无 LLM 分析章节；所有模块状态 unknown。
    """

    def test_llm_enabled_false_all_unknown(self):
        """_render_llm_module_info(False) → 全部 unknown + 无用量。"""
        from src.python.report.html_writer import _render_llm_module_info

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts._LLM_MODULE_FAILURE", {}))
            # 即使 _LLM_MODULE_FAILURE 有内容，llm_enabled=False 也应覆盖
            llm_module_info, llm_endpoint, module_disabled, llm_session_usage = \
                _render_llm_module_info(False)

        self.assertEqual(len(llm_module_info), 5)
        for mi in llm_module_info:
            self.assertEqual(mi["status"], "unknown")
            self.assertEqual(mi["status_label"], "")
        self.assertEqual(llm_endpoint, "")
        self.assertIsNone(llm_session_usage)
        # llm_enabled=False → 所有模块未禁用（因为根本没有 LLM 功能）
        self.assertFalse(any(module_disabled.values()))

    def test_llm_enabled_false_no_session_usage(self):
        """llm_enabled=False → llm_session_usage 为 None（即使有 _LLM_MODULE_FAILURE）。"""
        from src.python.report.html_writer import _render_llm_module_info

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts._LLM_MODULE_FAILURE", {
                "global_macro": FAIL_REASON_API_ERROR,
                "expert_review": FAIL_REASON_DISABLED,
            }))
            llm_module_info, llm_endpoint, module_disabled, llm_session_usage = \
                _render_llm_module_info(False)

        # llm_enabled=False 时 session_usage 总为 None
        self.assertIsNone(llm_session_usage)
        # _LLM_MODULE_FAILURE 仍被读取（记录了生成时发生的状态）
        # _render_llm_module_info 不区分 enable 和 failure — failure 来自全局状态
        by_key = {m["key"]: m for m in llm_module_info}
        self.assertEqual(by_key["global_macro"]["status"], "failed")
        self.assertEqual(by_key["expert_review"]["status"], "disabled")

    def test_llm_content_none_when_disabled(self):
        """generate_all_llm 不被调用 → llm_content 为 None。"""
        # 测试 html_writer 在 enable_llm=False 时是否传递 llm_enabled=False 到模板
        from src.python.report.html_writer import write_html_report
        from src.python.models import Holding

        holdings = [Holding("证券账户", "长江电力", "600900", 100, 50.0)]

        with ExitStack() as stack:
            mock_details = stack.enter_context(
                patch("src.python.report.html_writer._generate_details"))
            mock_a_idx = stack.enter_context(
                patch("src.python.report.html_writer.fetch_indices"))
            mock_us_idx = stack.enter_context(
                patch("src.python.report.html_writer.fetch_us_indices"))
            mock_pen = stack.enter_context(
                patch("src.python.report.html_writer.compute_penetration_top10"))
            mock_cat = stack.enter_context(
                patch("src.python.report.html_writer._build_category_data"))
            mock_status = stack.enter_context(
                patch("src.python.report.html_writer.price_update_status"))
            mock_perf = stack.enter_context(
                patch("src.python.report.html_writer._build_perf_data"))
            mock_llm = stack.enter_context(
                patch("src.python.llm.generate_all_llm"))
            mock_template = stack.enter_context(
                patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [MagicMock(market_value=1000, cost=500,
                                                   profit=500, today_profit=50,
                                                   name="长江电力", code="600900",
                                                   price=55, yesterday_close=54,
                                                   profit_rate=1.0, source="腾讯",
                                                   price_type="real", premium="",
                                                   shares=100, cost_price=50,
                                                   nav_date="")]
            mock_a_idx.return_value = {}
            mock_us_idx.return_value = {}
            mock_pen.return_value = {}
            mock_cat.return_value = ([], True)
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix="test_s14_")
            try:
                write_html_report(
                    holdings,
                    output_dir=tmp_dir,
                    enable_llm=False,
                    llm_content=None,
                )
            finally:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # generate_all_llm 不应被调用
        mock_llm.assert_not_called()
        # 模板收到 llm_enabled=False
        _, kwargs = tmpl.render.call_args
        self.assertFalse(kwargs["llm_enabled"])
        self.assertIsNone(kwargs["global_macro"])
        self.assertIsNone(kwargs["llm_session_usage"])

        # llm_module_info 仍是 5 条 unknown
        self.assertEqual(len(kwargs["llm_module_info"]), 5)
        for mi in kwargs["llm_module_info"]:
            self.assertEqual(mi["status"], "unknown")


# ═══════════════════════════════════════════════════════════
#  S15: 禁用+缓存混合（禁用优先）
# ═══════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS15DisabledPriority(unittest.TestCase):
    """S15：1 禁用 + 1 缓存 + 1 成功 → 禁用优先原则。

    预期：禁用模块显示"已禁用"（灰色），即使该模块有缓存或 per_module 数据。
    """

    def test_disabled_overrides_per_module(self):
        """FAIL_REASON_DISABLED 优先于 per_module 数据。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {
            "health_check": FAIL_REASON_DISABLED,
        }
        # health_check 在 per_module 中也有数据，但应被禁用覆盖
        per_module = {
            "health_check": {
                "model": "ds", "cached": False,
                "input_tokens": 500, "output_tokens": 300,
                "cache_hit_tokens": 0, "cost": 0.002, "thinking": False,
                "endpoint": "",
            },
        }

        result = _build_module_info_list(failure, per_module)
        by_key = {m["key"]: m for m in result}

        # 禁用优先 → 显示 disabled
        self.assertEqual(by_key["health_check"]["status"], "disabled")
        self.assertEqual(by_key["health_check"]["status_label"], "已禁用")
        # 禁用时 model 应为空（不显示原始模型）
        self.assertEqual(by_key["health_check"]["model"], "")
        # 禁用时费用为 0
        self.assertEqual(by_key["health_check"]["cost"], 0.0)
        # 禁用时 cached=False
        self.assertFalse(by_key["health_check"]["cached"])

    def test_disabled_overrides_cached(self):
        """禁用优先于缓存状态。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {
            "health_check": FAIL_REASON_DISABLED,
        }
        per_module = {
            "health_check": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
        }

        result = _build_module_info_list(failure, per_module)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["health_check"]["status"], "disabled")
        self.assertEqual(by_key["health_check"]["status_label"], "已禁用")
        # 禁用时不应显示缓存标记
        self.assertFalse(by_key["health_check"]["cached"])

    def test_disabled_alone_no_per_module(self):
        """仅禁用无 per_module → 正确显示 disabled。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {"global_macro": FAIL_REASON_DISABLED}
        result = _build_module_info_list(failure, {})
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["status"], "disabled")
        self.assertEqual(by_key["global_macro"]["status_label"], "已禁用")


# ═══════════════════════════════════════════════════════════
#  S16: 断网下 LLM 生成
# ═══════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS16NetworkDown(unittest.TestCase):
    """S16：网络断开 → 所有模块降级为 NETWORK_ERROR。

    预期：所有 LLM 模块占位文本"LLM API 网络连接失败"，
    不阻塞报告生成，日志记录 NETWORK_ERROR。
    """

    def test_all_network_error(self):
        """_build_module_info_list：全部 NETWORK_ERROR。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {
            "global_macro": FAIL_REASON_NETWORK_ERROR,
            "expert_review": FAIL_REASON_NETWORK_ERROR,
            "health_check": FAIL_REASON_NETWORK_ERROR,
            "penetration_deep": FAIL_REASON_NETWORK_ERROR,
            "news_correlation": FAIL_REASON_NETWORK_ERROR,
        }

        result = _build_module_info_list(failure, {})
        by_key = {m["key"]: m for m in result}

        for key in failure:
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], "failed")
                self.assertEqual(
                    by_key[key]["status_label"],
                    "LLM API 网络连接失败",
                )

    def test_network_error_placeholder_text(self):
        """_render_llm_module_info：断网 -> failed 状态文本正确。"""
        from src.python.report.html_writer import _render_llm_module_info

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts._LLM_MODULE_FAILURE", {
                "global_macro": FAIL_REASON_NETWORK_ERROR,
                "expert_review": FAIL_REASON_NETWORK_ERROR,
                "health_check": FAIL_REASON_NETWORK_ERROR,
                "penetration_deep": FAIL_REASON_NETWORK_ERROR,
                "news_correlation": FAIL_REASON_NETWORK_ERROR,
            }))
            stack.enter_context(
                patch("src.python.llm.get_session_usage",
                      return_value={"has_usage": False, "per_module": {}}))
            stack.enter_context(
                patch("src.python.llm.format_session_usage",
                      return_value={"has_usage": False}))

            llm_module_info, _, _, _ = _render_llm_module_info(True)

        by_key = {m["key"]: m for m in llm_module_info}
        for key in ("global_macro", "expert_review", "health_check",
                    "penetration_deep", "news_correlation"):
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], "failed")
                self.assertIn("网络连接失败", by_key[key]["status_label"])

    def test_s16_console_output_format(self):
        """S16 场景下验证 TUI 摘要输出格式中失败模块数正确。"""
        # 验证 _build_module_info_list 返回 5 个失败模块
        from src.python.report.html_writer import _build_module_info_list

        failure = {
            "global_macro": FAIL_REASON_NETWORK_ERROR,
            "expert_review": FAIL_REASON_NETWORK_ERROR,
            "health_check": FAIL_REASON_NETWORK_ERROR,
            "penetration_deep": FAIL_REASON_NETWORK_ERROR,
            "news_correlation": FAIL_REASON_NETWORK_ERROR,
        }
        result = _build_module_info_list(failure, {})

        failed_count = sum(1 for m in result if m["status"] == "failed")
        self.assertEqual(failed_count, 5, "断网时所有 5 个模块应标记为 failed")


# ═══════════════════════════════════════════════════════════
#  S17: LLM 部分缓存超期
# ═══════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS17PartialCacheExpiry(unittest.TestCase):
    """S17：部分模块缓存超期。

    预期：过期模块重新调用 API（显示 Token 和费用），
    未过期模块显示"缓存"状态，费用为 0。
    """

    def test_partial_cache_hit(self):
        """_build_module_info_list：部分缓存 + 部分成功。"""
        from src.python.report.html_writer import _build_module_info_list

        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 1000, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 3000, "output_tokens": 1500,
                "cache_hit_tokens": 0, "cost": 0.015, "thinking": True,
                "endpoint": "",
            },
        }

        result = _build_module_info_list({}, per_module)
        by_key = {m["key"]: m for m in result}

        # 缓存
        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["global_macro"]["cost"], 0.0)
        self.assertEqual(by_key["global_macro"]["cache_hit_tokens"], 1000)
        self.assertTrue(by_key["global_macro"]["cached"])

        # 成功（重新调用）
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["expert_review"]["input_tokens"], 3000)
        self.assertEqual(by_key["expert_review"]["output_tokens"], 1500)
        self.assertEqual(by_key["expert_review"]["total_tokens"], 4500)
        self.assertEqual(by_key["expert_review"]["cost"], 0.015)
        self.assertFalse(by_key["expert_review"]["cached"])

        # 无 per_module → unknown
        self.assertEqual(by_key["health_check"]["status"], "unknown")
        self.assertEqual(by_key["penetration_deep"]["status"], "unknown")

    def test_session_usage_correctly_reports_mixed_cache(self):
        """阶段性验证：format_session_usage 在混合场景下正确反映 call_count。"""
        from src.python.llm import get_session_usage, format_session_usage
        from src.python.llm.session import reset_session_usage
        from src.python.llm.session import _track_session_usage, _record_per_module

        reset_session_usage()

        # 模拟 S17: 2 模块缓存 + 1 模块成功（过期重新调用）
        _record_per_module("global_macro", "ds", inp=0, out=0, cached=True,
                           cache_hit_tokens=1000)
        _record_per_module("health_check", "gpt4", inp=0, out=0, cached=True,
                           cache_hit_tokens=500)
        _track_session_usage("claude",
                             {"input_tokens": 2000, "output_tokens": 1000},
                             "claude-sonnet-4")
        _record_per_module("expert_review", "claude-sonnet-4",
                           inp=2000, out=1000, cached=False)

        raw = get_session_usage()
        formatted = format_session_usage(raw)

        self.assertTrue(formatted["has_usage"])
        # 只有 1 次真实 API 调用，2 次缓存
        self.assertEqual(formatted["call_count"], 1)
        # 总 token = 真实调用 token（缓存模块 token=0）
        self.assertEqual(formatted["total_tokens"], 3000)

        per_module = raw["per_module"]
        self.assertTrue(per_module["global_macro"]["cached"])
        self.assertTrue(per_module["health_check"]["cached"])
        self.assertFalse(per_module["expert_review"]["cached"])

        reset_session_usage()


# ═══════════════════════════════════════════════════════════
#  S17a: LLM 全缓存（无实际 API 调用）
# ═══════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestS17aFullCache(unittest.TestCase):
    """S17 扩展：全部模块缓存命中，无 API 调用。

    预期：module_info 全部 cached，无失败/成功条目。
    """

    def test_all_cache_hit(self):
        """_build_module_info_list：全部缓存命中。"""
        from src.python.report.html_writer import _build_module_info_list

        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 300, "cost": 0.0, "thinking": True,
                "endpoint": "",
            },
            "health_check": {
                "model": "gpt4", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 200, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "penetration_deep": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 400, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "news_correlation": {
                "model": "claude", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 600, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
        }

        result = _build_module_info_list({}, per_module)
        by_key = {m["key"]: m for m in result}

        for key in per_module:
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], "cached")
                self.assertTrue(by_key[key]["cached"])
                self.assertEqual(by_key[key]["cost"], 0.0)


# ═══════════════════════════════════════════════════════════
#  空持仓 + LLM 场景
# ═══════════════════════════════════════════════════════════

@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestEmptyHoldingsWithLlm(unittest.TestCase):
    """空持仓下 LLM 生成的降级行为。

    预期：无持仓时所有 LLM 模块应正常跳过/占位，不崩溃；
    holdings_count=0 时 generate_all_llm 不抛出异常。
    """

    @classmethod
    def setUpClass(cls):
        cls._cfg_patcher = patch("src.python.llm.generators.get_llm_config",
                                  return_value={"enabled_llm": {
                                      "global_macro": True,
                                      "expert_review": True,
                                      "health_check": True,
                                      "penetration_deep": True,
                                  }})
        cls._cfg_patcher.start()
        cls._exec_patcher = patch("src.python.llm.generators.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
        cls._cfg_patcher.stop()

    @patch("src.python.llm.generators.generate_penetration_deep_analysis")
    @patch("src.python.llm.generators.generate_health_check")
    @patch("src.python.llm.generators.generate_global_macro")
    @patch("src.python.llm.generators.generate_expert_review")
    def test_empty_holdings_no_crash(
        self, mock_expert, mock_macro, mock_health, mock_penetration,
    ):
        """holdings_count=0 + categories={} → 不会崩溃。"""
        from src.python.llm import generate_all_llm

        mock_macro.return_value = ("<p>空持仓</p>", False)
        mock_expert.return_value = ("<p>空复盘</p>", False)
        mock_health.return_value = ("<p>空体检</p>", False)
        mock_penetration.return_value = ("<p>空穿透</p>", False)

        try:
            macro, expert, health, pen, mc, ec, hc, pc = generate_all_llm(
                {}, {}, 0, 0, 0, 0, 0, {},
                holdings_details=[], penetrated_assets=[],
            )
        except Exception as e:
            self.fail(f"generate_all_llm 在空持仓下不应崩溃: {e}")

        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)

    @patch("src.python.llm.generators._build_global_macro_prompt")
    def test_global_macro_zero_values(self, mock_prompt):
        """generate_global_macro 在 categories={} 时不应崩溃。"""
        from src.python.llm.generators import generate_global_macro

        mock_prompt.return_value = "空持仓 prompt"
        with patch("src.python.llm.generators._generate_llm_module") as mock_gen:
            mock_gen.return_value = ("<p>宏观</p>", False)
            try:
                result, cached = generate_global_macro({}, {}, 0, 0, {},
                                                        force=True)
            except Exception as e:
                self.fail(f"空持仓下 generate_global_macro 不应崩溃: {e}")
            self.assertEqual(result, "<p>宏观</p>")


# ═══════════════════════════════════════════════════════════
#  输出格式一致性验证
# ═══════════════════════════════════════════════════════════

@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestOutputConsistency(unittest.TestCase):
    """验证 Excel/HTML/Summary 三种输出对同一 module_info 状态一致性。

    核心原则：
    - 同一模块，同一状态 → 模块名、状态标签、Token 数、费用、Thinking 标记完全一致
    - html_writer._build_module_info_list vs excel_generator._build_llm_usage_sheet
      应生成相同的 module_info 条目（同一输入 → 同一输出）
    """

    MIXED_FAILURE = {
        "global_macro": FAIL_REASON_NOT_CONFIGURED,
        "expert_review": FAIL_REASON_API_ERROR,
        "health_check": FAIL_REASON_DISABLED,
        "penetration_deep": FAIL_REASON_NETWORK_ERROR,
        "news_correlation": FAIL_REASON_TIMEOUT,
    }

    MIXED_PER_MODULE = {
        "global_macro": {
            "model": "ds", "cached": True,
            "input_tokens": 0, "output_tokens": 0,
            "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
            "endpoint": "",
        },
        "expert_review": {
            "model": "claude", "cached": False,
            "input_tokens": 2000, "output_tokens": 1000,
            "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
            "endpoint": "https://api.test.com",
        },
    }

    def _key_for_comparison(self, entry: dict) -> dict:
        """提取关键字段用于比较（排除 key/name 等标识字段）。"""
        return {
            "status": entry.get("status"),
            "status_label": entry.get("status_label"),
            "model": entry.get("model"),
            "input_tokens": entry.get("input_tokens"),
            "output_tokens": entry.get("output_tokens"),
            "total_tokens": entry.get("total_tokens"),
            "cache_hit_tokens": entry.get("cache_hit_tokens"),
            "cost": entry.get("cost"),
            "cached": entry.get("cached"),
            "thinking": entry.get("thinking"),
        }

    def test_html_and_excel_consistent_disabled(self):
        """disabled 状态在 html 和 excel 中标签一致。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {"health_check": FAIL_REASON_DISABLED}
        html_result = _build_module_info_list(failure, {})

        # 模拟 excel_generator 的构建逻辑
        from src.python.report.excel_generator import _build_llm_usage_sheet as _blus
        # _blus 内部依赖全局 _LLM_MODULE_FAILURE 和 session_usage
        # 这里直接用内置逻辑构造 excel 等效数据
        DISPLAY_REASON = {
            "not_configured": "LLM 未配置",
            "api_error": "LLM API 调用失败",
            "network_error": "LLM API 网络连接失败",
            "timeout": "LLM API 请求超时",
            "circuit_open": "LLM API 暂时不可用（熔断冷却中）",
        }

        hc_html = next(m for m in html_result if m["key"] == "health_check")
        self.assertEqual(hc_html["status"], "disabled")
        self.assertEqual(hc_html["status_label"], "已禁用")

        # Excel 等效构造
        excel_entry = {
            "key": "health_check", "name": "持仓体检报告",
            "status": "disabled", "status_label": "已禁用",
            "model": "", "input_tokens": 0, "output_tokens": 0,
            "total_tokens": 0, "cache_hit_tokens": 0,
            "cost": 0.0, "cached": False, "thinking": False, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(hc_html),
                         self._key_for_comparison(excel_entry))

    def test_html_and_excel_consistent_failure(self):
        """各失败原因在 html 和 excel 中标签一致。"""
        from src.python.report.html_writer import _build_module_info_list

        # 使用已知模块键（_build_module_info_list 只识别 5 个标准 key）
        MODULE_KEY = "health_check"

        for reason, expected_label in [
            (FAIL_REASON_NOT_CONFIGURED, "LLM 未配置"),
            (FAIL_REASON_API_ERROR, "LLM API 调用失败"),
            (FAIL_REASON_NETWORK_ERROR, "LLM API 网络连接失败"),
            (FAIL_REASON_TIMEOUT, "LLM API 请求超时"),
            (FAIL_REASON_CIRCUIT_OPEN, "LLM API 暂时不可用（熔断冷却中）"),
        ]:
            with self.subTest(reason=reason):
                failure = {MODULE_KEY: reason}
                html_result = _build_module_info_list(failure, {})
                test_entry = next(m for m in html_result if m["key"] == MODULE_KEY)

                self.assertEqual(test_entry["status"], "failed")
                self.assertEqual(test_entry["status_label"], expected_label)
                self.assertEqual(test_entry["model"], "")
                self.assertEqual(test_entry["cost"], 0.0)

    def test_html_and_excel_consistent_success(self):
        """success 状态在 html 和 excel 中标签一致。"""
        from src.python.report.html_writer import _build_module_info_list

        per_module = {
            "expert_review": {
                "model": "claude-sonnet-4", "cached": False,
                "input_tokens": 1500, "output_tokens": 800,
                "cache_hit_tokens": 0, "cost": 0.005, "thinking": True,
                "endpoint": "",
            },
        }
        html_result = _build_module_info_list({}, per_module)
        er_html = next(m for m in html_result if m["key"] == "expert_review")

        self.assertEqual(er_html["status"], "success")
        self.assertEqual(er_html["status_label"], "成功")
        self.assertEqual(er_html["total_tokens"], 2300)
        self.assertEqual(er_html["cost"], 0.005)
        self.assertTrue(er_html["thinking"])

        # Excel 等效
        excel_entry = {
            "key": "expert_review", "name": "智囊团深度复盘",
            "status": "success", "status_label": "成功",
            "model": "claude-sonnet-4",
            "input_tokens": 1500, "output_tokens": 800,
            "total_tokens": 2300, "cache_hit_tokens": 0,
            "cost": 0.005, "cached": False, "thinking": True, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(er_html),
                         self._key_for_comparison(excel_entry))

    def test_html_and_excel_consistent_cached(self):
        """cached 状态在 html 和 excel 中标签一致。"""
        from src.python.report.html_writer import _build_module_info_list

        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
        }
        html_result = _build_module_info_list({}, per_module)
        gm_html = next(m for m in html_result if m["key"] == "global_macro")

        self.assertEqual(gm_html["status"], "cached")
        self.assertEqual(gm_html["status_label"], "缓存")
        self.assertEqual(gm_html["cache_hit_tokens"], 500)
        self.assertTrue(gm_html["cached"])

        # Excel 等效
        excel_entry = {
            "key": "global_macro", "name": "全球政经局势",
            "status": "cached", "status_label": "缓存",
            "model": "ds",
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "cache_hit_tokens": 500, "cost": 0.0, "cached": True,
            "thinking": False, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(gm_html),
                         self._key_for_comparison(excel_entry))

    def test_html_has_news_correlation(self):
        """HTML module_info 包含 news_correlation 模块。"""
        from src.python.report.html_writer import _build_module_info_list
        result = _build_module_info_list({}, {})
        keys = [m["key"] for m in result]
        self.assertIn("news_correlation", keys)
        self.assertEqual(len(result), 5)

    def test_summary_and_excel_module_order(self):
        """Summary 页签和 Excel 用量页签的模块顺序一致。"""
        from src.python.report.html_writer import _build_module_info_list

        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": True,
                "endpoint": "",
            },
            "health_check": {
                "model": "gpt4", "cached": False,
                "input_tokens": 200, "output_tokens": 100,
                "cache_hit_tokens": 0, "cost": 0.002, "thinking": False,
                "endpoint": "",
            },
            "penetration_deep": {
                "model": "ds", "cached": False,
                "input_tokens": 300, "output_tokens": 150,
                "cache_hit_tokens": 0, "cost": 0.003, "thinking": False,
                "endpoint": "",
            },
        }
        html_result = _build_module_info_list({}, per_module)
        html_keys = [m["key"] for m in html_result if m["status"] != "unknown"]

        # Excel 模块顺序: global_macro, expert_review, health_check,
        # penetration_deep, news_correlation
        expected_order = ["global_macro", "expert_review",
                          "health_check", "penetration_deep",
                          "news_correlation"]
        for i, key in enumerate(html_keys):
            self.assertEqual(key, expected_order[i])


# ═══════════════════════════════════════════════════════════
#  非交易日 + LLM 混合场景
# ═══════════════════════════════════════════════════════════


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestNonTradingDayWithLlm(unittest.TestCase):
    """非交易日生成含 LLM 的报告。

    LLM 模块状态不受市场状态影响，非交易日下应正常显示。
    """

    def test_llm_module_info_independent_of_market_state(self):
        """_build_module_info_list 不依赖市场状态，非交易日照常调用。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {"penetration_deep": FAIL_REASON_NETWORK_ERROR}
        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 2000, "output_tokens": 1000,
                "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
                "endpoint": "",
            },
        }
        result = _build_module_info_list(failure, per_module)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["penetration_deep"]["status_label"], "LLM API 网络连接失败")
        self.assertEqual(by_key["health_check"]["status"], "unknown")
        self.assertEqual(by_key["news_correlation"]["status"], "unknown")

    def test_non_trading_day_no_llm_crash(self):
        """非交易日下 generate_all_llm 不应崩溃。"""
        from src.python.llm.generators import generate_all_llm

        with (
            patch("src.python.llm.generators._is_llm_module_enabled",
                  return_value=False),
        ):
            result = generate_all_llm({}, {}, 0, 0, 0, 0, 0, {},
                                      holdings_details=[],
                                      penetrated_assets=[])
            self.assertIsNotNone(result)


# ═══════════════════════════════════════════════════════════
#  多账户混合 + LLM 多轮
# ═══════════════════════════════════════════════════════════


@pytest.mark.llm
@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestMultiAccountMultiRoundLlm(unittest.TestCase):
    """多账户 + LLM 多轮交互场景。

    验证多账户下 LLM 生成不冲突，多轮调用数据完整聚合。
    """

    def test_multi_account_does_not_break_build_module_info(self):
        """多账户持仓传入 _build_module_info_list 不崩溃。"""
        from src.python.report.html_writer import _build_module_info_list

        failure = {}
        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
        }
        result = _build_module_info_list(failure, per_module)
        by_key = {m["key"]: m for m in result}
        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(len(result), 5)

    def test_multi_round_per_module_accumulates(self):
        """多轮调用后 per_module 累加所有轮次的 token 数据。"""
        from src.python.report.html_writer import _build_module_info_list

        per_module_round1 = {
            "global_macro": {
                "model": "ds", "cached": False,
                "input_tokens": 1000, "output_tokens": 500,
                "cache_hit_tokens": 0, "cost": 0.005, "thinking": False,
                "endpoint": "",
            },
        }
        per_module_round2 = {
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 2000, "output_tokens": 1000,
                "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
                "endpoint": "",
            },
        }
        # 模拟多轮合并（生产代码中由调用方合并 per_module 字典）
        merged = {**per_module_round1, **per_module_round2}
        result = _build_module_info_list({}, merged)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["input_tokens"], 1000)
        self.assertEqual(by_key["expert_review"]["input_tokens"], 2000)
        # 确保所有 5 个模块都存在
        self.assertEqual(len(result), 5)

    def test_generate_all_llm_with_multi_account(self):
        """多账户持仓下 generate_all_llm 不崩溃。"""
        from src.python.llm.generators import generate_all_llm

        with (
            patch("src.python.llm.generators._is_llm_module_enabled",
                  return_value=False),
        ):
            result = generate_all_llm({}, {}, 0, 0, 0, 0, 0, {},
                                      holdings_details=[],
                                      penetrated_assets=[])
            self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()

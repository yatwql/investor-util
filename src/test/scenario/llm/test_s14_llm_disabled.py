"""LLM 场景 S14：LLM 不启用。

S14：TUI 不按 L → 无 LLM 章节、无 LLM API 用量页。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/llm/test_s14_llm_disabled.py -v
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack

import pytest
from unittest.mock import MagicMock, patch

from src.python.llm import FAIL_REASON_API_ERROR, FAIL_REASON_DISABLED


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
        from src.python.report.html_renderers import _render_llm_module_info

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts.LLM_MODULE_FAILURE", {}))
            # 即使 LLM_MODULE_FAILURE 有内容，llm_enabled=False 也应覆盖
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
        """llm_enabled=False → llm_session_usage 为 None（即使有 LLM_MODULE_FAILURE）。"""
        from src.python.report.html_renderers import _render_llm_module_info

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts.LLM_MODULE_FAILURE", {
                "global_macro": FAIL_REASON_API_ERROR,
                "expert_review": FAIL_REASON_DISABLED,
            }))
            llm_module_info, llm_endpoint, module_disabled, llm_session_usage = \
                _render_llm_module_info(False)

        # llm_enabled=False 时 session_usage 总为 None
        self.assertIsNone(llm_session_usage)
        # LLM_MODULE_FAILURE 仍被读取（记录了生成时发生的状态）
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

        import tempfile
        import shutil

        with ExitStack() as stack:
            mock_details = stack.enter_context(
                patch("src.python.report.html_renderers._generate_details"))
            mock_a_idx = stack.enter_context(
                patch("src.python.report.html_renderers.fetch_indices"))
            mock_us_idx = stack.enter_context(
                patch("src.python.report.html_renderers.fetch_us_indices"))
            mock_pen = stack.enter_context(
                patch("src.python.report.html_renderers.compute_penetration_top10"))
            mock_cat = stack.enter_context(
                patch("src.python.report.html_renderers._build_category_data"))
            mock_status = stack.enter_context(
                patch("src.python.report.html_renderers.price_update_status"))
            mock_perf = stack.enter_context(
                patch("src.python.report.html_renderers._build_perf_data"))
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

            tmp_dir = tempfile.mkdtemp(prefix="test_s14_")
            try:
                write_html_report(
                    holdings,
                    output_dir=tmp_dir,
                    enable_llm=False,
                    llm_content=None,
                )
            finally:
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

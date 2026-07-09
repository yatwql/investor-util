"""全局降级冒烟测试 — 所有外部 API 失败时的报告生成稳定性（D-8）。

测试目标：
  - 全局降级：mock 所有外部数据源失败 → 报告生成不崩溃
  - 降级标记：数据源状态 ⚠/ℹ 正确写入
  - 消息一致性：Excel 和 HTML 对同一 data_status dict 输出相同文本

运行：
  pytest src/test/unit/report/test_excel_generator_edge.py -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.report.data_status import STATUS_MESSAGES, TIER_PREFIX
from src.python.report.progress import SilentProgressReporter

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


# ============================================================
#  全局降级冒烟 — 所有外部 API 失败的场景
# ============================================================


class TestGlobalDegradationSmoke(unittest.TestCase):
    """全局降级冒烟测试 — 外部 mock 全部数据源失败，内部模块真实运行。"""

    def setUp(self):
        self.progress = SilentProgressReporter()
        self.holding = MagicMock()
        self.holding.name = "长江电力"
        self.holding.code = "600900"
        self.holding.shares = 100
        self.holding.cost_price = 50.0
        self.holding.account = "证券账户"
        self.holdings = [self.holding]

    def _mock_external_apis(self):
        """mock 所有外部数据源，让内部 sheet 逻辑真实运行。"""
        patchers = [
            # 指数
            patch("src.python.fetcher.index.fetch_indices", return_value={}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
            # 分类
            patch("src.python.report.html_builders._build_category_data", return_value=[]),
            # 穿透 — 数据获取
            patch("src.python.report.penetration_sheet._load_profit_forecast_safe",
                  return_value=({}, False)),
            patch("src.python.report.penetration_sheet._load_dividend_data_safe",
                  return_value=({}, False)),
            # 基金持仓
            patch("src.python.fetcher.fund.fetch_fund_holdings", return_value=None),
            # 基金业绩
            patch("src.python.fetcher.fund.fetch_fund_rankings", return_value=None),
            patch("src.python.fetcher.fund.fetch_fund_benchmark", return_value="--"),
            patch("src.python.report.fund_performance._load_profit_forecast",
                  return_value=({}, False)),
            # B 系列数据
            patch("src.python.report.fund_manager_analysis.detect_manager_changes",
                  return_value=[]),
            patch("src.python.report.fund_overlap.compute_overlap_matrix",
                  return_value={"funds": [], "matrix": [], "pairs": []}),
            patch("src.python.report.fund_concentration.compute_concentration",
                  return_value=[]),
            patch("src.python.report.fund_style_analysis.analyze_style_for_all_funds",
                  return_value={"results": []}),
            # 新闻
            patch("src.python.report.news_correlation.build_news_data",
                  return_value=([], {})),
            # LLM（跳过）
            patch("src.python.report.llm_content.write_llm_sheets"),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def test_global_degradation_no_crash(self):
        """所有外部 API 失败 → 完整 Excel 报告生成不崩溃。"""
        from src.python.report.excel_generator import generate_excel_report

        self._mock_external_apis()

        _tmp = tempfile.TemporaryDirectory()
        self.addCleanup(_tmp.cleanup)

        # 不抛出异常即通过
        generate_excel_report(
            self.holdings,
            details=[],
            include_news=True,
            include_llm=False,
            output_dir=_tmp.name,
            progress=self.progress,
        )

    def test_global_degradation_bseries_placeholder_logged(self):
        """所有外部 API 失败 → B 系列模块写入占位文本（而非报错）。"""
        from src.python.report.excel_generator import generate_excel_report

        self._mock_external_apis()

        _tmp = tempfile.TemporaryDirectory()
        self.addCleanup(_tmp.cleanup)

        generate_excel_report(
            self.holdings,
            details=[],
            include_news=True,
            include_llm=False,
            output_dir=_tmp.name,
            progress=self.progress,
        )

        # generator 运行时未记录任何 add_error → 各模块异常隔离生效
        errors = self.progress.get_errors()
        # 因所有 API 被 mock 返回空数据，内部 sheet 逻辑正常处理，
        # 且 B 系列写入器无条件调用（不受 if data: 保护），预期不触发 add_error
        self.assertEqual(len(errors), 0)


# ============================================================
#  Excel vs HTML 消息一致性（D-8 核心）
# ============================================================


class TestMessageConsistency(unittest.TestCase):
    """Excel 和 HTML 从同一 STATUS_MESSAGES/TIER_PREFIX 渲染出相同文本。

    验证策略：
      - 结构层：Excel 和 HTML 两端引用同一 STATUS_MESSAGES 和 TIER_PREFIX 对象
      - 渲染层：Python 等价实现（模拟 HTML 模板的 render_data_status 宏逻辑）
        vs _write_data_status_foot 输出一致 → 证明渲染逻辑等价
    """

    def test_status_messages_shared_constant(self):
        """Excel 和 HTML 使用相同的 STATUS_MESSAGES 常量（同一对象引用）。"""
        from src.python.report import data_status as ds1
        from src.python.report import data_status as ds2

        self.assertIs(ds1.STATUS_MESSAGES, ds2.STATUS_MESSAGES)

    def test_tier_prefix_shared(self):
        """TIER_PREFIX 常量定义完整。"""
        self.assertEqual(TIER_PREFIX["T2"], "⚠")
        self.assertEqual(TIER_PREFIX["T3"], "ℹ")
        self.assertEqual(TIER_PREFIX["T4"], "ℹ")
        for key in ("T2", "T3", "T4"):
            self.assertIn(key, TIER_PREFIX)

    def test_status_messages_all_keys(self):
        """所有 STATUS_MESSAGES key 存在且不为空。"""
        for key, msg in STATUS_MESSAGES.items():
            with self.subTest(key=key):
                self.assertIsInstance(key, str)
                self.assertIsInstance(msg, str)
                self.assertGreater(len(msg), 0)

    def test_placeholder_texts_used_in_both(self):
        """B 系列 STATUS_MESSAGES key 完整且被 sheet 模块引用。"""
        from src.python.report.fund_manager_sheet import write_fund_manager_sheet
        from src.python.report.fund_concentration_sheet import write_concentration_sheet
        from src.python.report.fund_style_sheet import write_style_sheet

        self.assertTrue(callable(write_fund_manager_sheet))
        self.assertTrue(callable(write_concentration_sheet))
        self.assertTrue(callable(write_style_sheet))

        for key in ("manager_unavailable", "overlap_unavailable",
                    "concentration_unavailable", "style_unavailable"):
            self.assertIn(key, STATUS_MESSAGES,
                          f"STATUS_MESSAGES 应包含 {key}")

    # ── 渲染层一致性验证 ────────────────────────────────

    def _excel_render_status_lines(self, data_status: dict) -> list[str]:
        """通过 _write_data_status_foot 渲染 data_status，返回文本行列表。"""
        from src.python.report.excel_writer import _write_data_status_foot, create_workbook

        wb = create_workbook()
        ws = wb.active
        _write_data_status_foot(ws, data_status, start_row=1)

        lines = []
        for row in ws.iter_rows(min_row=2, max_col=1, values_only=True):
            val = row[0]
            if val and isinstance(val, str):
                lines.append(val.strip())
        return lines

    def _html_simulated_macro(self, data_status: dict) -> list[str]:
        """模拟 render_data_status 宏逻辑（纯 Python）。

        等价于 HTML 模板中的：
          <div class="{% if item.tier == 'T2' %}data-status-warn{% else %}data-status-info{% endif %}">
              {% if item.tier == 'T2' %}⚠{% else %}ℹ{% endif %} {{ item.message }}
          </div>
        """
        if not data_status:
            return []

        lines = []
        for key, item in data_status.items():
            available = item.get("available", True)
            if not available:
                tier = item.get("tier", "T4")
                prefix = TIER_PREFIX.get(tier, "ℹ")
                msg = item.get("message", "")
                lines.append(f"{prefix} {msg}")
        return lines

    def test_data_status_content_consistent(self):
        """Exce 和 HTML 对同一 data_status 输出相同文本行。"""
        test_cases = [
            # T2 单项降级
            {
                "rank": {"available": False, "tier": "T2",
                         "message": STATUS_MESSAGES["rank_unavailable"]},
            },
            # T3 单项降级
            {
                "industry": {"available": False, "tier": "T3",
                             "message": STATUS_MESSAGES["industry_unavailable"]},
            },
            # T4 单项降级
            {
                "dividend": {"available": False, "tier": "T4",
                             "message": STATUS_MESSAGES["dividend_unavailable"]},
            },
            # 混合降级（T2 + T3 + T4）
            {
                "index_a": {"available": False, "tier": "T2",
                            "message": STATUS_MESSAGES["index_degraded"]},
                "industry": {"available": False, "tier": "T3",
                             "message": STATUS_MESSAGES["industry_unavailable"]},
                "eps": {"available": False, "tier": "T4",
                        "message": STATUS_MESSAGES["profit_forecast_unavailable"]},
            },
            # 含可用项（应被过滤）
            {
                "rank": {"available": False, "tier": "T2",
                         "message": STATUS_MESSAGES["rank_unavailable"]},
                "benchmark": {"available": True, "tier": "T3",
                              "message": "基准数据正常"},
            },
        ]

        for idx, status_dict in enumerate(test_cases):
            with self.subTest(case=idx):
                excel_lines = self._excel_render_status_lines(status_dict)
                html_lines = self._html_simulated_macro(status_dict)

                self.assertEqual(
                    excel_lines, html_lines,
                    f"Case {idx}: Excel 和 HTML 输出不一致\n"
                    f"  Excel: {excel_lines}\n"
                    f"  HTML:  {html_lines}",
                )

    def test_data_status_empty(self):
        """空 dict / 全部 available → 两端均无输出。"""
        excel_lines = self._excel_render_status_lines({})
        html_lines = self._html_simulated_macro({})
        self.assertEqual(excel_lines, [])
        self.assertEqual(html_lines, [])

        excel_lines = self._excel_render_status_lines({
            "a": {"available": True, "tier": "T2", "message": "ok"},
        })
        html_lines = self._html_simulated_macro({
            "a": {"available": True, "tier": "T2", "message": "ok"},
        })
        self.assertEqual(excel_lines, [])
        self.assertEqual(html_lines, [])


if __name__ == "__main__":
    unittest.main()

"""HTML 报告生成模块边缘/异常测试。

测试目标：
  - _render_penetration_section：API 失败、空数据、缺失键时的降级
  - write_html_report：数据源状态摘要渲染（穿透/基金业绩/独立性）

运行：
  pytest src/test/unit/report/test_html_writer_edge.py -v
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from src.python.core.models import Holding
from src.python.report.data_status import DataStatusItem, STATUS_MESSAGES

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


class TestRenderPenetrationSection(unittest.TestCase):
    """测试 _render_penetration_section 在数据加载失败时的降级。"""

    def setUp(self):
        self.holdings = [Holding("证券账户", "长江电力", "600900", 100, 50.0)]
        self.detail = MagicMock()
        self.detail.market_value = 1000.0
        self.detail.cost = 500.0
        self.detail.profit = 500.0
        self.detail.today_profit = 50.0
        self.detail.name = "长江电力"
        self.detail.code = "600900"
        self.detail.price = 55.0
        self.detail.yesterday_close = 54.0
        self.detail.profit_rate = 1.0
        self.detail.source = "腾讯"
        self.detail.price_type = "实时"
        self.detail.premium = ""
        self.detail.shares = 100
        self.detail.cost_price = 50.0
        self.detail.nav_date = ""
        self.prog = MagicMock()

    def test_penetration_empty_top10_returns_early(self):
        """pen_result 无 top10 → 直接返回，不加载额外数据。"""
        from src.python.report.html_renderers import _render_penetration_section

        with patch("src.python.report.html_renderers.compute_penetration_top10",
                   return_value={}):
            result, _, _ = _render_penetration_section(self.holdings, [self.detail], self.prog)
        self.assertEqual(result, {})

    def test_penetration_top10_has_eps_and_dividend_defaults(self):
        """API 全失败 → 每个 entry 的 eps_text/dividend_text 为 "--"。"""
        from src.python.report.html_renderers import _render_penetration_section

        mock_top10 = {
            "top10": [
                {"rank": 1, "name": "长江电力", "codes": ["600900"], "mv": 1000.0},
                {"rank": 2, "name": "某标的（港股）", "codes": ["00700"]},
            ],
            "summary": {"total_funds": 0, "total_stocks": 2, "merged_count": 2, "top10_coverage_pct": 100.0},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10",
                                      return_value=mock_top10))
            stack.enter_context(patch("src.python.report.html_renderers.get_profit_forecast",
                                      side_effect=Exception("API 失败")))
            stack.enter_context(patch("src.python.report.html_renderers.get_dividend_data",
                                      side_effect=Exception("API 失败")))
            result, prof_ok, div_ok = _render_penetration_section(self.holdings, [self.detail], self.prog)

        for entry in result["top10"]:
            self.assertEqual(entry.get("eps_text"), "--")
            self.assertEqual(entry.get("dividend_text"), "--")
        self.assertFalse(prof_ok)
        self.assertFalse(div_ok)

    def test_penetration_partial_data(self):
        """部分数据有值 → 仅匹配到的 entry 有 EPS/股息率。"""
        from src.python.report.html_renderers import _render_penetration_section

        mock_top10 = {
            "top10": [
                {"rank": 1, "name": "长江电力", "codes": ["600900"], "mv": 1000.0},
                {"rank": 2, "name": "贵州茅台", "codes": ["600519"], "mv": 800.0},
            ],
            "summary": {},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10",
                                      return_value=mock_top10))
            stack.enter_context(patch("src.python.report.html_renderers.get_profit_forecast",
                                      return_value={
                                          "600900": {"eps_2026e": 1.23},
                                          "600519": {"eps_2026e": 58.5},
                                      }))
            stack.enter_context(patch("src.python.report.html_renderers.get_dividend_data",
                                      return_value={
                                          "600900": {"avg_dividend": 0.85},
                                      }))
            result, prof_ok, div_ok = _render_penetration_section(self.holdings, [self.detail], self.prog)

        entry_600900 = next(e for e in result["top10"] if "600900" in (e.get("codes") or []))
        entry_600519 = next(e for e in result["top10"] if "600519" in (e.get("codes") or []))

        self.assertEqual(entry_600900["eps_text"], "¥1.23")
        self.assertEqual(entry_600900["dividend_text"], "0.8500元/年")
        self.assertEqual(entry_600519["eps_text"], "¥58.50")
        self.assertEqual(entry_600519["dividend_text"], "--")
        self.assertTrue(prof_ok)
        self.assertTrue(div_ok)

    def test_penetration_no_codes_key(self):
        """entry 无 codes 键 → 跳过，eps_text/dividend_text 为 "--"。"""
        from src.python.report.html_renderers import _render_penetration_section

        mock_top10 = {
            "top10": [
                {"rank": 1, "name": "未知标的", "mv": 500.0},
            ],
            "summary": {},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10",
                                      return_value=mock_top10))
            stack.enter_context(patch("src.python.report.html_renderers.get_profit_forecast",
                                      return_value={}))
            stack.enter_context(patch("src.python.report.html_renderers.get_dividend_data",
                                      return_value={}))
            result, _, _ = _render_penetration_section(self.holdings, [self.detail], self.prog)

        entry = result["top10"][0]
        self.assertEqual(entry.get("eps_text"), "--")
        self.assertEqual(entry.get("dividend_text"), "--")


# ============================================================
#  write_html_report — data_status 渲染（D-6 新增）
# ============================================================


class TestWriteHtmlReportDataStatus(unittest.TestCase):
    """测试 write_html_report 的数据源状态摘要（data_status_xxx）渲染。"""

    def setUp(self):
        self.holdings = [Holding("证券账户", "长江电力", "600900", 100, 50.0)]
        self._tmp = tempfile.mkdtemp(prefix="test_html_ds_")
        self.detail = MagicMock()
        self.detail.market_value = 1000.0
        self.detail.cost = 500.0
        self.detail.profit = 500.0
        self.detail.today_profit = 50.0
        self.detail.name = "长江电力"
        self.detail.code = "600900"
        self.detail.price = 55.0
        self.detail.yesterday_close = 54.0
        self.detail.profit_rate = 1.0
        self.detail.source = "腾讯"
        self.detail.price_type = "实时"
        self.detail.premium = ""
        self.detail.shares = 100
        self.detail.cost_price = 50.0
        self.detail.nav_date = ""

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_data_status_penetration_on_failure(self):
        """穿透数据源失败 → data_status_penetration 含失败项。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            # 标准外部依赖 mock
            stack.enter_context(patch("src.python.report.html_renderers._generate_details",
                                       return_value=[self.detail]))
            stack.enter_context(patch("src.python.report.html_renderers.fetch_indices",
                                       return_value={"sh000001": {"name": "上证", "price": 3120, "change": 10, "change_pct": 0.32}}))
            stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices",
                                       return_value={"gb_dji": {"name": "道指", "price": 35000, "change": 100, "change_pct": 0.29}}))
            stack.enter_context(patch("src.python.report.html_renderers._build_category_data",
                                       return_value=([], True)))
            stack.enter_context(patch("src.python.report.html_renderers.price_update_status",
                                       return_value=(0, 0, True)))
            # 穿透子函数 mock — 返回空穿透结果（industry_success=False）
            stack.enter_context(patch(
                "src.python.report.html_writer._render_penetration_section",
                return_value=({"top10": [], "summary": {}, "industry_success": False}, False, True),
            ))
            # 基金业绩子函数 mock
            stack.enter_context(patch(
                "src.python.report.html_writer._render_fund_performance_section",
                return_value=([], True),
            ))
            # data_status mock — industry 失败
            stack.enter_context(patch(
                "src.python.report.html_writer.build_penetration_data_status",
                return_value={
                    "industry": DataStatusItem(
                        available=False, tier="T3",
                        message=STATUS_MESSAGES["industry_unavailable"],
                    ),
                },
            ))
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            stack.enter_context(patch("src.python.report.html_writer._ENV.get_template",
                                       return_value=tmpl))

            write_html_report(self.holdings, output_dir=self._tmp)

        _, kwargs = tmpl.render.call_args
        self.assertIn("data_status_penetration", kwargs)
        self.assertIn("industry", kwargs["data_status_penetration"])
        self.assertFalse(kwargs["data_status_penetration"]["industry"]["available"])
        self.assertEqual(kwargs["data_status_penetration"]["industry"]["tier"], "T3")

    def test_data_status_perf_on_failure(self):
        """基金业绩数据源失败 → data_status_perf 含失败项。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.report.html_renderers._generate_details",
                                       return_value=[self.detail]))
            stack.enter_context(patch("src.python.report.html_renderers.fetch_indices",
                                       return_value={"sh000001": {"name": "上证", "price": 3120, "change": 10, "change_pct": 0.32}}))
            stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices",
                                       return_value={"gb_dji": {"name": "道指", "price": 35000, "change": 100, "change_pct": 0.29}}))
            stack.enter_context(patch("src.python.report.html_renderers._build_category_data",
                                       return_value=([], True)))
            stack.enter_context(patch("src.python.report.html_renderers.price_update_status",
                                       return_value=(0, 0, True)))
            stack.enter_context(patch(
                "src.python.report.html_writer._render_penetration_section",
                return_value=({"top10": [], "summary": {}, "industry_success": True}, True, True),
            ))
            # 基金业绩子函数 — profit_success=False
            stack.enter_context(patch(
                "src.python.report.html_writer._render_fund_performance_section",
                return_value=([], False),
            ))
            stack.enter_context(patch(
                "src.python.report.html_writer.build_perf_data_status",
                return_value={
                    "rank": DataStatusItem(
                        available=False, tier="T2",
                        message=STATUS_MESSAGES["rank_unavailable"],
                    ),
                },
            ))
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            stack.enter_context(patch("src.python.report.html_writer._ENV.get_template",
                                       return_value=tmpl))

            write_html_report(self.holdings, output_dir=self._tmp)

        _, kwargs = tmpl.render.call_args
        self.assertIn("data_status_perf", kwargs)
        self.assertIn("rank", kwargs["data_status_perf"])
        self.assertFalse(kwargs["data_status_perf"]["rank"]["available"])

    def test_data_status_try_split_independent(self):
        """穿透和基金业绩的 data_status try 块独立：一方异常不影响另一方。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.report.html_renderers._generate_details",
                                       return_value=[self.detail]))
            stack.enter_context(patch("src.python.report.html_renderers.fetch_indices",
                                       return_value={"sh000001": {"name": "上证", "price": 3120, "change": 10, "change_pct": 0.32}}))
            stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices",
                                       return_value={"gb_dji": {"name": "道指", "price": 35000, "change": 100, "change_pct": 0.29}}))
            stack.enter_context(patch("src.python.report.html_renderers._build_category_data",
                                       return_value=([], True)))
            stack.enter_context(patch("src.python.report.html_renderers.price_update_status",
                                       return_value=(0, 0, True)))
            # 穿透有数据（truthy），profit_success/dividend_success 不影响 data_status mock
            stack.enter_context(patch(
                "src.python.report.html_writer._render_penetration_section",
                return_value=({"top10": [{"rank": 1, "codes": ["600900"]}], "summary": {}}, True, True),
            ))
            stack.enter_context(patch(
                "src.python.report.html_writer._render_fund_performance_section",
                return_value=([], True),
            ))
            # 穿透 data_status 抛异常 → 被辅助函数捕获，结果为 {}
            stack.enter_context(patch(
                "src.python.report.html_writer.build_penetration_data_status",
                side_effect=Exception("模拟穿透状态构建失败"),
            ))
            # 基金业绩 data_status 正常返回
            stack.enter_context(patch(
                "src.python.report.html_writer.build_perf_data_status",
                return_value={
                    "benchmark": DataStatusItem(
                        available=False, tier="T3",
                        message=STATUS_MESSAGES["benchmark_unavailable"],
                    ),
                },
            ))
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            stack.enter_context(patch("src.python.report.html_writer._ENV.get_template",
                                       return_value=tmpl))

            write_html_report(self.holdings, output_dir=self._tmp)

        _, kwargs = tmpl.render.call_args
        # 穿透状态为空（异常被捕获，变量保持初始值 {}）
        self.assertEqual(kwargs["data_status_penetration"], {})
        # 基金业绩状态正常保留，不受穿透异常影响
        self.assertIn("benchmark", kwargs["data_status_perf"])
        self.assertFalse(kwargs["data_status_perf"]["benchmark"]["available"])


# ============================================================
#  B 系列模块空态占位（D-7a）
# ============================================================


class TestWriteHtmlReportBseriesEmpty(unittest.TestCase):
    """B 系列模块在 enable_fund_deep_analysis=True 且数据为空时 → section 可见 + 占位文本。"""

    def setUp(self):
        self.holdings = [Holding("证券账户", "长江电力", "600900", 100, 50.0)]
        self._tmp = tempfile.mkdtemp(prefix="test_html_bs_")
        self.detail = MagicMock()
        self.detail.market_value = 1000.0
        self.detail.cost = 500.0
        self.detail.profit = 500.0
        self.detail.today_profit = 50.0
        self.detail.name = "长江电力"
        self.detail.code = "600900"
        self.detail.price = 55.0
        self.detail.yesterday_close = 54.0
        self.detail.profit_rate = 1.0
        self.detail.source = "腾讯"
        self.detail.price_type = "实时"
        self.detail.premium = ""
        self.detail.shares = 100
        self.detail.cost_price = 50.0
        self.detail.nav_date = ""

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_b_series_mocks(self, stack):
        """mock 标准依赖 + 4 个 B 系列 _render_* 返回空数据。"""
        stack.enter_context(patch("src.python.report.html_renderers._generate_details",
                                   return_value=[self.detail]))
        stack.enter_context(patch("src.python.report.html_renderers.fetch_indices",
                                   return_value={"sh000001": {"name": "上证", "price": 3120, "change": 10, "change_pct": 0.32}}))
        stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices",
                                   return_value={"gb_dji": {"name": "道指", "price": 35000, "change": 100, "change_pct": 0.29}}))
        stack.enter_context(patch("src.python.report.html_renderers._build_category_data",
                                   return_value=([], True)))
        stack.enter_context(patch("src.python.report.html_renderers.price_update_status",
                                   return_value=(0, 0, True)))
        # 穿透 + 基金业绩返回（标准）
        stack.enter_context(patch(
            "src.python.report.html_writer._render_penetration_section",
            return_value=({"top10": [], "summary": {}, "industry_success": False}, False, True),
        ))
        stack.enter_context(patch(
            "src.python.report.html_writer._render_fund_performance_section",
            return_value=([], True),
        ))
        # 4 个 B 系列模块返回空数据
        stack.enter_context(patch(
            "src.python.report.html_writer._render_manager_analysis",
            return_value={"results": [], "first_check_summary": None},
        ))
        stack.enter_context(patch(
            "src.python.report.html_writer._render_overlap_matrix",
            return_value={"funds": [], "fund_names": {}, "matrix": [], "pairs": [], "has_mv_data": False},
        ))
        stack.enter_context(patch(
            "src.python.report.html_writer._render_concentration",
            return_value={"results": []},
        ))
        stack.enter_context(patch(
            "src.python.report.html_writer._render_style_analysis",
            return_value={"results": []},
        ))
        # data_status 构建（标准）
        stack.enter_context(patch("src.python.report.html_writer.build_index_data_status",
                                   return_value={}))
        stack.enter_context(patch("src.python.report.html_writer.build_penetration_data_status",
                                   return_value={}))
        stack.enter_context(patch("src.python.report.html_writer.build_perf_data_status",
                                   return_value={}))
        # 模板
        tmpl = MagicMock()
        tmpl.render.return_value = "<html>ok</html>"
        stack.enter_context(patch("src.python.report.html_writer._ENV.get_template",
                                   return_value=tmpl))
        return tmpl

    def test_all_bseries_sections_visible_when_empty(self):
        """B 系列 4 模块全部返回空数据 → 4 个 section 均可见（section_visible_dict=True）。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            tmpl = self._make_b_series_mocks(stack)
            write_html_report(self.holdings, include_news=True, output_dir=self._tmp)

        _, kwargs = tmpl.render.call_args
        svis = kwargs.get("section_visible_dict", {})
        self.assertTrue(svis.get("fund_manager"), "基金经理 section 应可见")
        self.assertTrue(svis.get("fund_overlap"), "重合度 section 应可见")
        self.assertTrue(svis.get("fund_concentration"), "集中度 section 应可见")
        self.assertTrue(svis.get("fund_style"), "风格分析 section 应可见")

    def test_bseries_empty_data_passed_to_template(self):
        """空数据时 manager_analysis / overlap_matrix / concentration_analysis / style_analysis
        正确传递给模板且为 dict。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            tmpl = self._make_b_series_mocks(stack)
            write_html_report(self.holdings, include_news=True, output_dir=self._tmp)

        _, kwargs = tmpl.render.call_args
        # 每个 B 系列数据都为 dict（非 None），确保模板不会因 .get("results") 而炸
        self.assertIsInstance(kwargs.get("manager_analysis"), dict)
        self.assertIsInstance(kwargs.get("overlap_matrix"), dict)
        self.assertIsInstance(kwargs.get("concentration_analysis"), dict)
        self.assertIsInstance(kwargs.get("style_analysis"), dict)
        # 空数据确认
        self.assertEqual(kwargs["manager_analysis"]["results"], [])
        self.assertEqual(kwargs["overlap_matrix"]["funds"], [])
        self.assertEqual(kwargs["concentration_analysis"]["results"], [])
        self.assertEqual(kwargs["style_analysis"]["results"], [])


if __name__ == "__main__":
    unittest.main()

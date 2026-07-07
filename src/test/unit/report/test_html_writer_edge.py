"""HTML 报告生成模块边缘/异常测试 — 穿透数据降级。

测试目标：
  - _render_penetration_section：API 失败、空数据、缺失键时的降级

运行：
  pytest src/test/unit/report/test_html_writer_edge.py -v
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from src.python.models import Holding

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
        from src.python.report.html_writer import _render_penetration_section

        with patch("src.python.report.html_writer.compute_penetration_top10",
                   return_value={}):
            result, _, _ = _render_penetration_section(self.holdings, [self.detail], self.prog)
        self.assertEqual(result, {})

    def test_penetration_top10_has_eps_and_dividend_defaults(self):
        """API 全失败 → 每个 entry 的 eps_text/dividend_text 为 "--"。"""
        from src.python.report.html_writer import _render_penetration_section

        mock_top10 = {
            "top10": [
                {"rank": 1, "name": "长江电力", "codes": ["600900"], "mv": 1000.0},
                {"rank": 2, "name": "某标的（港股）", "codes": ["00700"]},
            ],
            "summary": {"total_funds": 0, "total_stocks": 2, "merged_count": 2, "top10_coverage_pct": 100.0},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.report.html_writer.compute_penetration_top10",
                                      return_value=mock_top10))
            stack.enter_context(patch("src.python.providers.akshare_extras.get_profit_forecast",
                                      side_effect=Exception("API 失败")))
            stack.enter_context(patch("src.python.providers.akshare_extras.get_dividend_data",
                                      side_effect=Exception("API 失败")))
            result, prof_ok, div_ok = _render_penetration_section(self.holdings, [self.detail], self.prog)

        for entry in result["top10"]:
            self.assertEqual(entry.get("eps_text"), "--")
            self.assertEqual(entry.get("dividend_text"), "--")
        self.assertFalse(prof_ok)
        self.assertFalse(div_ok)

    def test_penetration_partial_data(self):
        """部分数据有值 → 仅匹配到的 entry 有 EPS/股息率。"""
        from src.python.report.html_writer import _render_penetration_section

        mock_top10 = {
            "top10": [
                {"rank": 1, "name": "长江电力", "codes": ["600900"], "mv": 1000.0},
                {"rank": 2, "name": "贵州茅台", "codes": ["600519"], "mv": 800.0},
            ],
            "summary": {},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.report.html_writer.compute_penetration_top10",
                                      return_value=mock_top10))
            stack.enter_context(patch("src.python.providers.akshare_extras.get_profit_forecast",
                                      return_value={
                                          "600900": {"eps_2025e": 1.23},
                                          "600519": {"eps_2025e": 58.5},
                                      }))
            stack.enter_context(patch("src.python.providers.akshare_extras.get_dividend_data",
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
        from src.python.report.html_writer import _render_penetration_section

        mock_top10 = {
            "top10": [
                {"rank": 1, "name": "未知标的", "mv": 500.0},
            ],
            "summary": {},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.report.html_writer.compute_penetration_top10",
                                      return_value=mock_top10))
            stack.enter_context(patch("src.python.providers.akshare_extras.get_profit_forecast",
                                      return_value={}))
            stack.enter_context(patch("src.python.providers.akshare_extras.get_dividend_data",
                                      return_value={}))
            result, _, _ = _render_penetration_section(self.holdings, [self.detail], self.prog)

        entry = result["top10"][0]
        self.assertEqual(entry.get("eps_text"), "--")
        self.assertEqual(entry.get("dividend_text"), "--")


if __name__ == "__main__":
    unittest.main()

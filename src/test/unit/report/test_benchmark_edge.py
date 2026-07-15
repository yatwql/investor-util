"""基准指数获取与归一化 — 边缘/异常场景测试。

测试目标：
  - normalize_benchmarks 的极端/边界条件
    - 全部 close = 0
    - align_start 处 close = 0
    - 指数数据早于组合（无重叠前段）
    - 指数数据晚于组合（无重叠后段）
    - 单一 bar
    - 指数仅一天数据
"""

from __future__ import annotations

import unittest

import pytest

from src.python.report.benchmark import normalize_benchmarks

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]

_PORTFOLIO_BARS = [
    {"date": "2026-01-05", "total_value": 1000000},
    {"date": "2026-01-06", "total_value": 1010000},
    {"date": "2026-01-07", "total_value": 1020000},
    {"date": "2026-01-08", "total_value": 1015000},
    {"date": "2026-01-09", "total_value": 1030000},
]


class TestNormalizeBenchmarksEdge(unittest.TestCase):
    """normalize_benchmarks 边界条件。"""

    maxDiff = None

    def _raw(self, bars, name="沪深300", code="sh000300") -> dict:
        return {code: {"name": name, "bars": bars}}

    def test_all_closes_zero(self):
        """所有 close = 0 → 跳过，返回 []。"""
        bars = [
            {"date": "2026-01-05", "close": 0},
            {"date": "2026-01-06", "close": 0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        self.assertEqual(result, [])

    def test_close_zero_at_align_start(self):
        """align_start 附近 close = 0 被过滤 → 起算日自动前移到首个有效日。"""
        bars = [
            {"date": "2026-01-05", "close": 0},     # 无效，被过滤
            {"date": "2026-01-06", "close": 100.0},
            {"date": "2026-01-07", "close": 102.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # align_start = max(1/5, 1/6) = 1/6, close_at_start = 100
        self.assertEqual(bm["data_start"], "2026-01-06")
        expected = [100.0, 102.0, 102.0, 102.0]  # 1/6:100, 1/7:102, 1/8 LOCF:102, 1/9 LOCF:102
        self.assertEqual([b["value"] for b in bm["bars"]], expected)

    def test_no_overlap_benchmark_ends_before_portfolio(self):
        """指数在组合起算前已结束 → 跳过。"""
        bars = [
            {"date": "2025-12-30", "close": 100.0},
            {"date": "2025-12-31", "close": 101.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        # 指数最后一条 = 2025-12-31 < 组合起算日 2026-01-05
        self.assertEqual(result, [])

    def test_no_overlap_benchmark_starts_after_portfolio(self):
        """指数在组合结束后才起始 → 跳过。"""
        bars = [
            {"date": "2026-01-12", "close": 100.0},
            {"date": "2026-01-13", "close": 101.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        # 指数首条 = 2026-01-12 > 组合结束日 2026-01-09
        self.assertEqual(result, [])

    def test_single_bar_benchmark(self):
        """指数只有一条有效数据 → 正常归一化（flat line at 100）。"""
        bars = [
            {"date": "2026-01-05", "close": 2000.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # 所有日期对齐 2000/2000*100 = 100
        expected = [100.0] * 5
        self.assertEqual([b["value"] for b in bm["bars"]], expected)
        self.assertEqual(bm["total_return_pct"], 0.0)
        self.assertEqual(bm["max_drawdown_pct"], 0.0)

    def test_benchmark_one_day_after_portfolio_start(self):
        """指数仅一条数据且日期 > 组合首日 → 对齐到该日期。"""
        bars = [
            {"date": "2026-01-07", "close": 500.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # align_start = max(1/5, 1/7) = 1/7
        self.assertEqual(bm["data_start"], "2026-01-07")
        self.assertEqual(len(bm["bars"]), 3)  # 1/7, 1/8, 1/9
        self.assertEqual(bm["bars"][0]["value"], 100.0)
        self.assertEqual(bm["bars"][1]["value"], 100.0)  # LOCF
        self.assertEqual(bm["bars"][2]["value"], 100.0)  # LOCF
        self.assertEqual(bm["total_return_pct"], 0.0)

    def test_partial_close_zero_at_middle(self):
        """中间有 close=0，前后有正常数据 → 0 条被过滤，剩余 LOCF。"""
        bars = [
            {"date": "2026-01-05", "close": 100.0},
            {"date": "2026-01-06", "close": 0},        # 过滤
            {"date": "2026-01-07", "close": 105.0},
            {"date": "2026-01-08", "close": 103.0},
        ]
        # portfolio 只有 1/5~1/8
        portfolio = _PORTFOLIO_BARS[:4]
        result = normalize_benchmarks(portfolio, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # 有效: 1/5=100, 1/7=105, 1/8=103
        # align_start = 1/5, close_at_start=100
        # 1/5: 100, 1/6: LOCF→100, 1/7: 105, 1/8: 103
        self.assertEqual([b["value"] for b in bm["bars"]],
                         [100.0, 100.0, 105.0, 103.0])

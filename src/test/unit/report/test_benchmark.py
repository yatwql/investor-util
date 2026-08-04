"""基准指数获取模块单元测试。

测试目标：
  - fetch_benchmarks — 并行获取指数历史日线
    - 正常返回
    - 空配置
    - 部分指数失败（其他成功）
    - 全部失败
    - 走 fetch_index_history
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.report.benchmark import fetch_benchmarks, normalize_benchmarks

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_SAMPLE_BARS = [
    {"date": "2026-07-01", "close": 4000.0, "open": 3980.0,
     "high": 4010.0, "low": 3970.0, "volume": 1000000},
    {"date": "2026-07-02", "close": 4020.0, "open": 4000.0,
     "high": 4030.0, "low": 3990.0, "volume": 1200000},
]


class TestFetchBenchmarks(unittest.TestCase):
    """fetch_benchmarks 单元测试。"""

    @patch("src.python.report.benchmark.fetch_index_history")
    def test_normal_return(self, mock_fetch):
        """正常返回 → 每只指数都有 name + bars。"""
        mock_fetch.return_value = _SAMPLE_BARS

        indices = {"sh000300": "沪深300", "gb_inx": "标普500"}
        result = fetch_benchmarks(indices, days=365)

        self.assertIn("sh000300", result)
        self.assertIn("gb_inx", result)
        self.assertEqual(result["sh000300"]["name"], "沪深300")
        self.assertEqual(result["sh000300"]["bars"], _SAMPLE_BARS)
        self.assertEqual(result["gb_inx"]["bars"], _SAMPLE_BARS)
        # 每个指数都调用了 fetch_index_history
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("src.python.report.benchmark.fetch_index_history")
    def test_empty_indices(self, mock_fetch):
        """空字典 → 直接返回空字典，不调用 fetch_index_history。"""
        result = fetch_benchmarks({}, days=365)
        self.assertEqual(result, {})
        mock_fetch.assert_not_called()

    @patch("src.python.report.benchmark.fetch_index_history")
    def test_partial_failure(self, mock_fetch):
        """部分指数失败 → 返回成功获取的。"""
        def _side_effect(code, days):
            if code == "sh000300":
                return _SAMPLE_BARS
            return None  # gb_inx 获取失败

        mock_fetch.side_effect = _side_effect

        indices = {"sh000300": "沪深300", "gb_inx": "标普500"}
        result = fetch_benchmarks(indices, days=365)

        self.assertIn("sh000300", result)
        self.assertNotIn("gb_inx", result)
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("src.python.report.benchmark.fetch_index_history")
    def test_all_fail(self, mock_fetch):
        """全部失败 → 返回空字典。"""
        mock_fetch.return_value = None

        indices = {"sh000300": "沪深300", "gb_inx": "标普500"}
        result = fetch_benchmarks(indices, days=365)

        self.assertEqual(result, {})

    @patch("src.python.report.benchmark.fetch_index_history")
    def test_single_index(self, mock_fetch):
        """只有一个指数 → 也能正确获取。"""
        mock_fetch.return_value = _SAMPLE_BARS

        indices = {"sh000300": "沪深300"}
        result = fetch_benchmarks(indices, days=200)

        self.assertIn("sh000300", result)
        self.assertEqual(len(result["sh000300"]["bars"]), 2)
        mock_fetch.assert_called_once_with("sh000300", 200)

    @patch("src.python.report.benchmark.fetch_index_history")
    def test_exception_handling(self, mock_fetch):
        """fetch_index_history 抛出异常 → 跳过该指数，不影响其他。"""
        def _side_effect(code, days):
            if code == "sh000300":
                raise RuntimeError("API error")
            return _SAMPLE_BARS

        mock_fetch.side_effect = _side_effect

        indices = {"sh000300": "沪深300", "gb_inx": "标普500"}
        result = fetch_benchmarks(indices, days=365)

        self.assertNotIn("sh000300", result)
        self.assertIn("gb_inx", result)


# ═══════════════════════════════════════════════════════════════
#  normalize_benchmarks 单元测试
# ═══════════════════════════════════════════════════════════════


_PORTFOLIO_BARS = [
    {"date": "2026-01-05", "total_value": 1000000},
    {"date": "2026-01-06", "total_value": 1010000},
    {"date": "2026-01-07", "total_value": 1020000},
    {"date": "2026-01-08", "total_value": 1015000},
    {"date": "2026-01-09", "total_value": 1030000},
]

_BM_BARS_SAME = [  # 5 天均有数据
    {"date": "2026-01-05", "close": 100.0},
    {"date": "2026-01-06", "close": 101.0},
    {"date": "2026-01-07", "close": 102.0},
    {"date": "2026-01-08", "close": 101.0},
    {"date": "2026-01-09", "close": 103.0},
]


class TestNormalizeBenchmarks(unittest.TestCase):
    """normalize_benchmarks 单元测试。"""

    maxDiff = None

    def _raw(self, bars, name="沪深300", code="sh000300") -> dict:
        return {code: {"name": name, "bars": bars}}

    def test_same_start_date(self):
        """组合与指数起算日相同 → 从第一天归一化。"""
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(_BM_BARS_SAME))
        self.assertEqual(len(result), 1)
        bm = result[0]
        self.assertEqual(bm["code"], "sh000300")
        self.assertEqual(bm["name"], "沪深300")
        # normalized values: 100/100*100=100, 101/100*100=101, ...
        expected_values = [100.0, 101.0, 102.0, 101.0, 103.0]
        self.assertEqual([b["value"] for b in bm["bars"]], expected_values)
        self.assertEqual(bm["total_return_pct"], 3.0)  # 103 - 100
        # max drawdown: peak=102 at 1/7, drop to 101 at 1/8 → (102-101)/102*100=0.98
        self.assertAlmostEqual(bm["max_drawdown_pct"], -0.98, places=2)
        self.assertEqual(bm["data_start"], "2026-01-05")
        self.assertEqual(bm["data_end"], "2026-01-09")
        self.assertEqual(bm["status"], "ok")

    def test_benchmark_starts_after_portfolio(self):
        """指数数据起始日晚于组合 → 对齐起算日为指数首日。"""
        bars = [
            {"date": "2026-01-07", "close": 100.0},
            {"date": "2026-01-08", "close": 101.0},
            {"date": "2026-01-09", "close": 102.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # 对齐起算日 = max(1/5, 1/7) = 1/7
        self.assertEqual(bm["data_start"], "2026-01-07")
        expected = [100.0, 101.0, 102.0]
        self.assertEqual([b["value"] for b in bm["bars"]], expected)
        self.assertEqual(bm["total_return_pct"], 2.0)

    def test_benchmark_starts_before_portfolio(self):
        """指数数据起始日早于组合 → 对齐起算日为组合首日。"""
        bars = [
            {"date": "2026-01-01", "close": 50.0},
            {"date": "2026-01-02", "close": 52.0},
            {"date": "2026-01-05", "close": 100.0},
            {"date": "2026-01-06", "close": 101.0},
            {"date": "2026-01-07", "close": 102.0},
            {"date": "2026-01-08", "close": 101.0},
            {"date": "2026-01-09", "close": 103.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # 对齐起算日 = max(1/5, 1/1) = 1/5
        self.assertEqual(bm["data_start"], "2026-01-05")
        # close_at_start = 100 (on 1/5)
        expected = [100.0, 101.0, 102.0, 101.0, 103.0]
        self.assertEqual([b["value"] for b in bm["bars"]], expected)

    def test_locf_gap_fill(self):
        """指数数据有缺失日 → LOCF 前值填充。"""
        bars = [  # 仅 1/5, 1/7, 1/9 有数据
            {"date": "2026-01-05", "close": 100.0},
            {"date": "2026-01-07", "close": 102.0},
            {"date": "2026-01-09", "close": 103.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # LOCF:
        #   1/5: 100.0, 1/6: LOCF→100.0, 1/7: 102.0, 1/8: LOCF→102.0, 1/9: 103.0
        expected = [100.0, 100.0, 102.0, 102.0, 103.0]
        self.assertEqual([b["value"] for b in bm["bars"]], expected)

    def test_locf_with_gap_after_align_start(self):
        """对齐起算日之后指数有缺失 → LOCF 正确填充。"""
        portfolio_bars = [
            {"date": "2026-01-05", "total_value": 1000},
            {"date": "2026-01-06", "total_value": 1010},
            {"date": "2026-01-07", "total_value": 1020},
        ]
        bars = [  # 仅 1/5 和 1/7 有数据
            {"date": "2026-01-05", "close": 100.0},
            {"date": "2026-01-07", "close": 105.0},
        ]
        result = normalize_benchmarks(portfolio_bars, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # 1/5: 100, 1/6: LOCF→100, 1/7: 105
        self.assertEqual([b["value"] for b in bm["bars"]], [100.0, 100.0, 105.0])

    def test_multiple_benchmarks(self):
        """多个基准指数 → 每只独立归一化。"""
        bm1 = _BM_BARS_SAME
        bm2 = [
            {"date": "2026-01-05", "close": 1000.0},
            {"date": "2026-01-06", "close": 1010.0},
            {"date": "2026-01-07", "close": 1020.0},
            {"date": "2026-01-08", "close": 1030.0},
            {"date": "2026-01-09", "close": 1040.0},
        ]
        raw = {
            "sh000300": {"name": "沪深300", "bars": bm1},
            "gb_inx": {"name": "标普500", "bars": bm2},
        }
        result = normalize_benchmarks(_PORTFOLIO_BARS, raw)
        self.assertEqual(len(result), 2)
        # 沪深300: normalized as before
        bm1_result = [r for r in result if r["code"] == "sh000300"][0]
        self.assertEqual([b["value"] for b in bm1_result["bars"]],
                         [100.0, 101.0, 102.0, 101.0, 103.0])
        # 标普500: 1000→100, 1010→101, ...
        bm2_result = [r for r in result if r["code"] == "gb_inx"][0]
        self.assertEqual([b["value"] for b in bm2_result["bars"]],
                         [100.0, 101.0, 102.0, 103.0, 104.0])
        self.assertEqual(bm2_result["total_return_pct"], 4.0)

    def test_empty_portfolio_bars(self):
        """空组合走势 → 返回 []。"""
        result = normalize_benchmarks([], self._raw(_BM_BARS_SAME))
        self.assertEqual(result, [])

        result = normalize_benchmarks(None, self._raw(_BM_BARS_SAME))  # type: ignore
        self.assertEqual(result, [])

    def test_empty_raw_benchmarks(self):
        """空基准配置 → 返回 []。"""
        result = normalize_benchmarks(_PORTFOLIO_BARS, {})
        self.assertEqual(result, [])

        result = normalize_benchmarks(_PORTFOLIO_BARS, None)  # type: ignore
        self.assertEqual(result, [])

    def test_benchmark_empty_bars(self):
        """基准有代码但 bars 为空 → 跳过该基准。"""
        raw = {"sh000300": {"name": "沪深300", "bars": []}}
        result = normalize_benchmarks(_PORTFOLIO_BARS, raw)
        self.assertEqual(result, [])

    def test_nan_close_filtered(self):
        """含有 NaN/0/None close 的 bars 被过滤，剩余正常数据参与归一化。"""
        bars = [
            {"date": "2026-01-05", "close": 100.0},
            {"date": "2026-01-06", "close": 0},        # 无效
            {"date": "2026-01-07", "close": None},      # 无效
            {"date": "2026-01-08", "close": 101.0},
            {"date": "2026-01-09", "close": 102.0},
        ]
        result = normalize_benchmarks(_PORTFOLIO_BARS, self._raw(bars))
        self.assertEqual(len(result), 1)
        bm = result[0]
        # 有效 day-to-close: 1/5→100, 1/8→101, 1/9→102
        # align_start = max(1/5, 1/5) = 1/5, close_at_start = 100
        # LOCF:
        #   1/5: 100, 1/6: LOCF→100, 1/7: LOCF→100, 1/8: 101, 1/9: 102
        expected = [100.0, 100.0, 100.0, 101.0, 102.0]
        self.assertEqual([b["value"] for b in bm["bars"]], expected)

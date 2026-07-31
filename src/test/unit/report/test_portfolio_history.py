"""组合历史走势计算器单元测试。

测试目标：
  - calculate_for_holding — 代码类型路由与 00 代码降级
  - _get_stock_history / _get_fund_history — 内部路由
  - _compute_annualized_volatility — 波动率计算
  - _validate_bars — 数据质量校验
  - get_combined_timeseries — 综合走势合并
  - _is_bond_fund — 债券基金名称识别
"""

from __future__ import annotations

import unittest
from unittest.mock import patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestCalculateForHolding(unittest.TestCase):
    """calculate_for_holding 路由与降级逻辑测试。"""

    def _make_calculator(self, session_cache: dict | None = None) -> object:
        from src.python.report.portfolio_history import PortfolioHistoryCalculator
        return PortfolioHistoryCalculator(session_cache or {})

    # ── 正常路由 ──────────────────────────────────────────

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_a_share_code_routes_to_stock(self, mock_fetch):
        """6 开头 A 股 → _get_stock_history。"""
        fake_bars = [{"date": "2026-07-01", "close": 26.65}]
        mock_fetch.return_value = fake_bars

        calc = self._make_calculator()
        result = calc.calculate_for_holding("600900", "长江电力", 800)
        self.assertIsNotNone(result)
        mock_fetch.assert_called_once_with("history_stock", "600900")

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_zero_prefix_code_routes_to_stock(self, mock_fetch):
        """0 开头代码且非 OTC 基金 → _get_stock_history。"""
        fake_bars = [{"date": "2026-07-01", "close": 12.50}]
        mock_fetch.return_value = fake_bars

        calc = self._make_calculator()
        result = calc.calculate_for_holding("000001", "平安银行", 500)
        self.assertIsNotNone(result)
        mock_fetch.assert_called_once_with("history_stock", "000001")

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_five_prefix_etf_routes_to_stock(self, mock_fetch):
        """5 开头 ETF → _get_stock_history。"""
        fake_bars = [{"date": "2026-07-01", "close": 1.234}]
        mock_fetch.return_value = fake_bars

        calc = self._make_calculator()
        result = calc.calculate_for_holding("511880", "银华日利", 100)
        self.assertIsNotNone(result)
        mock_fetch.assert_called_once_with("history_stock", "511880")

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_six_digit_code_routes_to_fund(self, mock_fetch):
        """6 位纯数字非 A 股/ETF → _get_fund_history。"""
        fake_bars = [{"date": "2026-07-01", "nav": 1.5}]
        mock_fetch.return_value = fake_bars

        calc = self._make_calculator()
        result = calc.calculate_for_holding("011506", "某基金", 1000)
        self.assertIsNotNone(result)
        mock_fetch.assert_called_once_with("history_fund_otc", "011506")

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_bond_fund_routes_to_fund(self, mock_fetch):
        """债券基金名称 → _get_fund_history。"""
        fake_bars = [{"date": "2026-07-01", "nav": 1.02}]
        mock_fetch.return_value = fake_bars

        calc = self._make_calculator()
        result = calc.calculate_for_holding("012325", "招商鑫福中短债A", 5000)
        self.assertIsNotNone(result)
        mock_fetch.assert_called_once_with("history_fund_otc", "012325")

    def test_hk_stock_returns_none(self):
        """港股通代码 → None。"""
        calc = self._make_calculator()
        result = calc.calculate_for_holding("00700", "腾讯控股", 100)
        self.assertIsNone(result)

    def test_unknown_type_returns_none(self):
        """未知类型代码 → None。"""
        calc = self._make_calculator()
        result = calc.calculate_for_holding("ABCDE", "未知资产", 100)
        self.assertIsNone(result)

    # ── 00 代码降级 ────────────────────────────────────────

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_code_fallback_to_fund(self, mock_fetch):
        """00 代码 K 线全空 → 降级至基金净值。"""
        mock_fetch.side_effect = [
            None,                     # history_stock → 失败
            [{"date": "2026-07-01", "nav": 1.2345}],  # history_fund_otc → 成功
        ]

        calc = self._make_calculator()
        result = calc.calculate_for_holding("002943", "广发多因子", 1000)
        self.assertIsNotNone(result)
        self.assertEqual(mock_fetch.call_count, 2)
        # 第 1 次调用必须是 history_stock
        self.assertEqual(mock_fetch.call_args_list[0][0][0], "history_stock")
        # 第 2 次调用必须是 history_fund_otc（降级）
        self.assertEqual(mock_fetch.call_args_list[1][0][0], "history_fund_otc")

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_kline_success_no_fallback(self, mock_fetch):
        """00 代码但 K 线成功 → 不降级。"""
        mock_fetch.return_value = [{"date": "2026-07-01", "close": 12.50}]

        calc = self._make_calculator()
        result = calc.calculate_for_holding("000001", "平安银行", 500)
        self.assertIsNotNone(result)
        mock_fetch.assert_called_once_with("history_stock", "000001")

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_code_fallback_all_fail(self, mock_fetch):
        """00 代码 K 线 + 基金净值均失败 → None。"""
        mock_fetch.side_effect = [None, None]

        calc = self._make_calculator()
        result = calc.calculate_for_holding("002943", "广发多因子", 1000)
        self.assertIsNone(result)
        self.assertEqual(mock_fetch.call_count, 2)

    # ── Session Cache ────────────────────────────────────

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_session_cache_stock(self, mock_fetch):
        """_get_stock_history 复用会话缓存。"""
        calc = self._make_calculator({
            "history_stock_600900": [{"date": "2026-07-01", "close": 26.65}],
        })
        result = calc.calculate_for_holding("600900", "长江电力", 800)
        self.assertIsNotNone(result)
        self.assertEqual(result[0]["close"], 26.65)
        mock_fetch.assert_not_called()

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_session_cache_fund(self, mock_fetch):
        """_get_fund_history 复用会话缓存（00 代码触发降级路径）。"""
        mock_fetch.return_value = None  # stock 路径也 mock 掉
        calc = self._make_calculator({
            "history_fund_otc_002943": [{"date": "2026-07-01", "nav": 1.2345}],
        })
        result = calc.calculate_for_holding("002943", "广发多因子", 1000)
        self.assertIsNotNone(result)
        self.assertEqual(result[0]["close"], 1.2345)

    # ── as-if 市值计算 ─────────────────────────────────

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_as_if_market_value(self, mock_fetch):
        """as-if 市值 = close × shares。"""
        mock_fetch.return_value = [
            {"date": "2026-07-01", "close": 10.0},
            {"date": "2026-07-02", "close": 11.0},
        ]

        calc = self._make_calculator()
        result = calc.calculate_for_holding("600900", "长江电力", 800)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["value"], 8000.0)   # 10.0 × 800
        self.assertEqual(result[1]["value"], 8800.0)   # 11.0 × 800

    @patch("src.python.report.portfolio_history.fetch_with_incremental_fallback")
    def test_as_if_skips_zero_close(self, mock_fetch):
        """close <= 0 的 bar 跳过。"""
        mock_fetch.return_value = [
            {"date": "2026-07-01", "close": 0.0},
            {"date": "2026-07-02", "close": 10.0},
        ]

        calc = self._make_calculator()
        result = calc.calculate_for_holding("600900", "长江电力", 800)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["value"], 8000.0)


class TestGetCombinedTimeseries(unittest.TestCase):
    """get_combined_timeseries 综合走势测试。"""

    def _make_calculator(self):
        from src.python.report.portfolio_history import PortfolioHistoryCalculator
        return PortfolioHistoryCalculator({})

    def _bars(self, close_values: list[float], shares: float = 1,
              start: str = "2026-07-01") -> list[dict]:
        """生成 calculate_for_holding 的返回格式（含 value）。"""
        return [{"date": f"2026-07-{1 + i:02d}", "close": v, "value": round(v * shares, 2)}
                for i, v in enumerate(close_values)]

    @patch("src.python.report.portfolio_history.PortfolioHistoryCalculator.calculate_for_holding")
    def test_all_success_status_ok(self, mock_calc):
        """全部成功 → status=ok。"""
        mock_calc.side_effect = [
            self._bars([10, 11, 12]),      # 持仓 1
            self._bars([20, 21, 22]),      # 持仓 2
        ]
        calc = self._make_calculator()
        result = calc.get_combined_timeseries([
            ("600900", "长江电力", 100),
            ("002943", "广发多因子", 200),
        ], days=3)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["bars"]), 3)

    @patch("src.python.report.portfolio_history.PortfolioHistoryCalculator.calculate_for_holding")
    def test_partial_fail_status_degraded(self, mock_calc):
        """部分失败 → status=degraded。"""
        mock_calc.side_effect = [
            self._bars([10, 11, 12]),      # 成功
            None,                           # 失败
        ]
        calc = self._make_calculator()
        result = calc.get_combined_timeseries([
            ("600900", "长江电力", 100),
            ("002943", "广发多因子", 200),
        ], days=3)
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(any("部分持仓" in w for w in result["warnings"]))

    @patch("src.python.report.portfolio_history.PortfolioHistoryCalculator.calculate_for_holding")
    def test_all_fail_status_unavailable(self, mock_calc):
        """全部失败 → status=unavailable。"""
        mock_calc.side_effect = [None, None]
        calc = self._make_calculator()
        result = calc.get_combined_timeseries([
            ("600900", "长江电力", 100),
            ("002943", "广发多因子", 200),
        ])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(len(result["bars"]), 0)

    # ── Benchmark integration ──────────────────────────────

    @patch("src.python.report.portfolio_history.normalize_benchmarks")
    @patch("src.python.report.portfolio_history.fetch_benchmarks")
    @patch("src.python.report.portfolio_history.PortfolioHistoryCalculator.calculate_for_holding")
    def test_benchmark_indices_provided_calls_fetch(self, mock_calc, mock_fetch, mock_norm):
        """传入 benchmark_indices → 调用 fetch_benchmarks + normalize_benchmarks。"""
        from src.python.report.portfolio_history import PortfolioHistoryCalculator
        mock_calc.side_effect = [self._bars([10, 11, 12])]
        mock_fetch.return_value = {"sh000300": {"name": "沪深300", "bars": []}}
        mock_norm.return_value = [{"code": "sh000300", "name": "沪深300", "bars": [],
                                    "total_return_pct": 2.0, "max_drawdown_pct": -1.0,
                                    "data_start": "", "data_end": "", "status": "ok"}]

        calc = PortfolioHistoryCalculator(
            {},
            benchmark_indices={"sh000300": "沪深300"},
        )
        result = calc.get_combined_timeseries([("600900", "长江电力", 100)], days=30)
        mock_fetch.assert_called_once_with({"sh000300": "沪深300"}, days=30)
        mock_norm.assert_called_once()
        self.assertIn("benchmarks", result)
        self.assertEqual(len(result["benchmarks"]), 1)
        self.assertEqual(result["benchmarks"][0]["code"], "sh000300")

    @patch("src.python.report.portfolio_history.normalize_benchmarks")
    @patch("src.python.report.portfolio_history.fetch_benchmarks")
    @patch("src.python.report.portfolio_history.PortfolioHistoryCalculator.calculate_for_holding")
    def test_benchmark_indices_empty_skips_fetch(self, mock_calc, mock_fetch, mock_norm):
        """benchmark_indices 为空字典 → 不调用 fetch_benchmarks。"""
        from src.python.report.portfolio_history import PortfolioHistoryCalculator
        mock_calc.side_effect = [self._bars([10, 11, 12])]

        calc = PortfolioHistoryCalculator(
            {},
            benchmark_indices={},
        )
        result = calc.get_combined_timeseries([("600900", "长江电力", 100)], days=30)
        mock_fetch.assert_not_called()
        mock_norm.assert_not_called()
        self.assertEqual(result["benchmarks"], [])

    @patch("src.python.report.portfolio_history.normalize_benchmarks")
    @patch("src.python.report.portfolio_history.fetch_benchmarks")
    @patch("src.python.report.portfolio_history.PortfolioHistoryCalculator.calculate_for_holding")
    def test_benchmark_fetch_exception_handled(self, mock_calc, mock_fetch, mock_norm):
        """fetch_benchmarks 抛出异常 → 不阻塞，返回空列表。"""
        from src.python.report.portfolio_history import PortfolioHistoryCalculator
        mock_calc.side_effect = [self._bars([10, 11, 12])]
        mock_fetch.side_effect = RuntimeError("网络错误")

        calc = PortfolioHistoryCalculator(
            {},
            benchmark_indices={"sh000300": "沪深300"},
        )
        result = calc.get_combined_timeseries([("600900", "长江电力", 100)], days=30)
        mock_fetch.assert_called_once()
        mock_norm.assert_not_called()
        self.assertEqual(result["benchmarks"], [])
        self.assertEqual(result["status"], "ok")  # 基准异常不影响组合走势


class TestComputeAnnualizedVolatility(unittest.TestCase):
    """年化波动率计算测试。"""

    def _call(self, daily_returns: list[float]) -> float:
        from src.python.report.portfolio_history import PortfolioHistoryCalculator
        return PortfolioHistoryCalculator._compute_annualized_volatility(daily_returns)

    def test_annualized_volatility_normal_returns_positive(self):
        """正常收益率序列 → 正波动率。"""
        result = self._call([0.01, -0.005, 0.02, -0.01, 0.015])
        self.assertGreater(result, 0)

    def test_annualized_volatility_single_return_zero(self):
        """单元素 → 0。"""
        self.assertEqual(self._call([0.01]), 0.0)

    def test_annualized_volatility_empty_list_zero(self):
        """空列表 → 0。"""
        self.assertEqual(self._call([]), 0.0)

    def test_annualized_volatility_identical_returns_zero(self):
        """全部相同（无波动）→ 0。"""
        self.assertEqual(self._call([0.01, 0.01, 0.01]), 0.0)


class TestValidateBars(unittest.TestCase):
    """走势数据质量校验测试。"""

    def _call(self, bars: list[dict]) -> list[str]:
        from src.python.report.portfolio_history import _validate_bars
        return _validate_bars(bars)

    def test_clean_bars_no_warnings(self):
        """正常数据 → 无警告。"""
        warnings = self._call([
            {"date": "2026-07-01", "close": 10.0},
            {"date": "2026-07-02", "close": 11.0},
        ])
        self.assertEqual(warnings, [])

    def test_zero_close_warning(self):
        """收盘价为 0 → 警告。"""
        warnings = self._call([
            {"date": "2026-07-01", "close": 0.0},
        ])
        self.assertTrue(any("收盘价为 0" in w for w in warnings))

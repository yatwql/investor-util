"""TUI 缓存管理命令处理器单元测试。

运行：
  pytest src/test/unit/handlers/test_handlers_cache.py -v
"""

from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


@pytest.mark.unit_core
class TestRefreshProfitForecastCache(unittest.TestCase):
    """_refresh_profit_forecast_cache 缓存刷新（operations 版）。"""

    def _call(self):
        from src.python.cache.operations import _refresh_profit_forecast_cache
        return _refresh_profit_forecast_cache()

    @patch("src.python.fetcher.akshare.get_profit_forecast")
    def test_success(self, mock_get):
        """成功获取 → 返回 (profit_forecast, 覆盖数)。"""
        mock_get.return_value = {"600900": {}, "600519": {}}
        name, count = self._call()
        self.assertEqual(name, "profit_forecast")
        self.assertEqual(count, 2)

    @patch("src.python.fetcher.akshare.get_profit_forecast")
    def test_empty_result(self, mock_get):
        """空结果 → 返回 0。"""
        mock_get.return_value = {}
        name, count = self._call()
        self.assertEqual(count, 0)

    @patch("src.python.fetcher.akshare.get_profit_forecast")
    def test_none_result(self, mock_get):
        """None 结果 → 返回 0。"""
        mock_get.return_value = None
        name, count = self._call()
        self.assertEqual(count, 0)


@pytest.mark.unit_core
class TestRefreshSectorFlowCache(unittest.TestCase):
    """_refresh_sector_flow_cache 缓存刷新（operations 版）。"""

    def _call(self):
        from src.python.cache.operations import _refresh_sector_flow_cache
        return _refresh_sector_flow_cache()

    @patch("src.python.fetcher.akshare.get_sector_fund_flow")
    def test_success(self, mock_get):
        """成功获取 → 返回 (sector_flow, 行业数)。"""
        mock_get.return_value = [{"name": "电力"}, {"name": "银行"}]
        name, count = self._call()
        self.assertEqual(name, "sector_flow")
        self.assertEqual(count, 2)

    @patch("src.python.fetcher.akshare.get_sector_fund_flow")
    def test_empty_result(self, mock_get):
        """空列表 → 返回 0。"""
        mock_get.return_value = []
        name, count = self._call()
        self.assertEqual(count, 0)

    @patch("src.python.fetcher.akshare.get_sector_fund_flow")
    def test_none_result(self, mock_get):
        """None 结果 → 返回 0。"""
        mock_get.return_value = None
        name, count = self._call()
        self.assertEqual(count, 0)


@pytest.mark.unit_core
class TestPrintCacheRefreshReport(unittest.TestCase):
    """_print_cache_refresh_report 输出格式（CacheUpdateResult 版）。"""

    def setUp(self):
        self._stdout = io.StringIO()
        from src.python.cache.operations import CacheUpdateResult
        self.CacheUpdateResult = CacheUpdateResult

    def _make_result(self, **kwargs):
        return self.CacheUpdateResult(**kwargs)

    def _call(self, result):
        from src.python.tui.handlers_cache import _print_cache_refresh_report
        with patch("sys.stdout", self._stdout):
            _print_cache_refresh_report(result)
        return self._stdout.getvalue()

    def test_all_ok(self):
        """全部成功时显示 [OK]。"""
        result = self._make_result(
            total_funds=2, perf_ok=2, hold_ok=2, bm_ok=2,
            pf_ok=10, sf_ok=5,
        )
        output = self._call(result)
        self.assertIn("全部成功", output)
        self.assertIn("[OK]", output)

    def test_partial_failure(self):
        """部分失败时显示 [!]。"""
        result = self._make_result(
            total_funds=2, perf_ok=1, hold_ok=2, bm_ok=0,
            pf_ok=0, sf_ok=0,
        )
        output = self._call(result)
        self.assertIn("[!]", output)
        self.assertIn("1 只失败", output)
        self.assertIn("2 只未找到", output)

    def test_no_funds(self):
        """无基金时的输出。"""
        result = self._make_result(
            total_funds=0, perf_ok=0, hold_ok=0, bm_ok=0,
            pf_ok=10, sf_ok=5,
        )
        output = self._call(result)
        self.assertIn("profit_forecast", output)
        self.assertIn("sector_flow", output)

    def test_sector_flow_fail_hint(self):
        """资金流向获取失败时的提示。"""
        result = self._make_result(
            total_funds=1, perf_ok=1, hold_ok=1, bm_ok=1,
            pf_ok=0, sf_ok=0,
        )
        from src.python.tui.handlers_cache import _print_cache_refresh_report
        with patch("sys.stdout", self._stdout):
            _print_cache_refresh_report(result)
        output = self._stdout.getvalue()
        self.assertIn("获取失败", output)

    def test_empty_funds_with_pf_only(self):
        """无基金仅盈利预测成功。"""
        result = self._make_result(
            total_funds=0, perf_ok=0, hold_ok=0, bm_ok=0,
            pf_ok=5, sf_ok=0,
        )
        output = self._call(result)
        self.assertIn("5 只股票", output)


@pytest.mark.unit_core
class TestCmdCleanupCache(unittest.TestCase):
    """_cmd_cleanup_cache 清理命令（委托 operations）。"""

    def test_cleanup_removed_some(self):
        """清理到过期文件（verify delegation + TuiProgressReporter output）。"""
        from src.python.tui.handlers_cache import _cmd_cleanup_cache
        with (
            patch("src.python.cache.operations.cleanup_cache", return_value=5),
            patch("src.python.tui.handlers_cache.press_any_key"),
            patch("src.python.report.progress.TuiProgressReporter.ok"),
            patch("src.python.report.progress.TuiProgressReporter.info"),
            patch("sys.stdout", io.StringIO()),
        ):
            _cmd_cleanup_cache()

    def test_cleanup_nothing(self):
        """无过期文件（verify delegation + TuiProgressReporter output）。"""
        from src.python.tui.handlers_cache import _cmd_cleanup_cache
        with (
            patch("src.python.cache.operations.cleanup_cache", return_value=0),
            patch("src.python.tui.handlers_cache.press_any_key"),
        ):
            _cmd_cleanup_cache()


@pytest.mark.unit_core
class TestRefreshIndustryCache(unittest.TestCase):
    """_refresh_industry_cache 行业分类刷新（operations 版）。"""

    def _call(self, holdings):
        from src.python.cache.operations import _refresh_industry_cache
        return _refresh_industry_cache(holdings)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data")
    def test_with_valid_codes(self, mock_fetch):
        """有效代码返回正确计数。"""
        mock_fetch.return_value = {"600900": {}, "600519": {}}
        from src.python.core.models import Holding
        holdings = [
            Holding("证券", "长江电力", "600900", 100, 15.0),
            Holding("证券", "贵州茅台", "600519", 10, 2000.0),
        ]
        count = self._call(holdings)
        self.assertEqual(count, 2)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data")
    def test_empty_holdings(self, mock_fetch):
        """空持仓列表返回 0 且不调用 API。"""
        count = self._call([])
        self.assertEqual(count, 0)
        mock_fetch.assert_not_called()

    @patch("src.python.fetcher.industry.batch_fetch_industry_data")
    def test_empty_result(self, mock_fetch):
        """API 返回空字典。"""
        mock_fetch.return_value = {}
        from src.python.core.models import Holding
        holdings = [Holding("证券", "测试", "000001", 100, 10.0)]
        count = self._call(holdings)
        self.assertEqual(count, 0)


@pytest.mark.unit_core
class TestRefreshDividendCache(unittest.TestCase):
    """_refresh_dividend_cache 分红刷新（operations 版）。"""

    def _call(self, holdings):
        from src.python.cache.operations import _refresh_dividend_cache
        return _refresh_dividend_cache(holdings)

    @patch("src.python.fetcher.akshare.get_dividend_data")
    def test_with_valid_codes(self, mock_get):
        """有效代码返回正确计数。"""
        mock_get.return_value = {"600900": {}, "600519": {}}
        from src.python.core.models import Holding
        holdings = [
            Holding("证券", "长江电力", "600900", 100, 15.0),
            Holding("证券", "贵州茅台", "600519", 10, 2000.0),
        ]
        count = self._call(holdings)
        self.assertEqual(count, 2)

    @patch("src.python.fetcher.akshare.get_dividend_data")
    def test_empty_holdings(self, mock_get):
        """空持仓列表返回 0 且不调用 API。"""
        count = self._call([])
        self.assertEqual(count, 0)
        mock_get.assert_not_called()


@pytest.mark.unit_core
class TestRefreshOneFundCache(unittest.TestCase):
    """_refresh_one_fund_cache 单基金缓存刷新（operations 版）。"""

    def _make_fund(self, code="000001", name="测试基金"):
        f = MagicMock()
        f.code = code
        f.name = name
        return f

    @patch("src.python.fetcher.fund.fetch_fund_benchmark")
    @patch("src.python.fetcher.fund.fetch_fund_holdings")
    @patch("src.python.fetcher.fund.fetch_fund_rankings")
    def test_all_ok(self, mock_rank, mock_hold, mock_bm):
        """全部数据获取成功。"""
        from src.python.cache.operations import _refresh_one_fund_cache

        mock_rank.return_value = {"rank": 1}
        mock_hold.return_value = {"holdings": [{"name": "茅台", "code": "600519"}]}
        mock_bm.return_value = "沪深300"

        result = _refresh_one_fund_cache(self._make_fund())
        self.assertEqual(result[0], "fund")
        self.assertEqual(result[1], "000001")
        self.assertIs(result[3], True)  # perf_ok
        self.assertIs(result[4], True)  # hold_ok
        self.assertIs(result[6], True)  # bm_ok

    @patch("src.python.fetcher.fund.fetch_fund_benchmark", return_value="--")
    @patch("src.python.fetcher.fund.fetch_fund_holdings", return_value=None)
    @patch("src.python.fetcher.fund.fetch_fund_rankings", return_value=None)
    def test_all_fail(self, mock_rank, mock_hold, mock_bm):
        """全部数据获取失败。"""
        from src.python.cache.operations import _refresh_one_fund_cache

        result = _refresh_one_fund_cache(self._make_fund())
        self.assertIs(result[3], False)  # perf_ok
        self.assertIs(result[4], False)  # hold_ok
        self.assertIs(result[6], False)  # bm_ok

    @patch("src.python.fetcher.fund.fetch_fund_benchmark", return_value="--")
    @patch("src.python.fetcher.fund.fetch_fund_holdings", return_value=None)
    @patch("src.python.fetcher.fund.fetch_fund_rankings", side_effect=Exception("API err"))
    def test_rankings_raises(self, mock_rank, mock_hold, mock_bm):
        """排名 API 抛出异常时向上传播（函数未捕获该异常）。"""
        from src.python.cache.operations import _refresh_one_fund_cache

        with self.assertRaisesRegex(Exception, "API err"):
            _refresh_one_fund_cache(self._make_fund())

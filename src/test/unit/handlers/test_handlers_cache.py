"""TUI 缓存管理命令处理器单元测试。

测试 _refresh_profit_forecast_cache、_refresh_sector_flow_cache、
_print_cache_refresh_report 等可独立测试的函数。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/handlers/test_handlers_cache.py -v
"""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


@pytest.mark.unit_core
class TestRefreshProfitForecastCache(unittest.TestCase):
    """_refresh_profit_forecast_cache 缓存刷新。"""

    def _call(self):
        from src.python.handlers_cache import _refresh_profit_forecast_cache
        return _refresh_profit_forecast_cache()

    @patch("src.python.providers.akshare_extras._memo_clear")
    @patch("src.python.providers.akshare_extras.get_profit_forecast")
    def test_success(self, mock_get, mock_memo):
        """成功获取 → 返回 (profit_forecast, 覆盖数)。"""
        mock_get.return_value = {"600900": {}, "600519": {}}
        name, count = self._call()
        self.assertEqual(name, "profit_forecast")
        self.assertEqual(count, 2)
        mock_memo.assert_called_once()

    @patch("src.python.providers.akshare_extras._memo_clear")
    @patch("src.python.providers.akshare_extras.get_profit_forecast")
    def test_empty_result(self, mock_get, mock_memo):
        """空结果 → 返回 0。"""
        mock_get.return_value = {}
        name, count = self._call()
        self.assertEqual(count, 0)

    @patch("src.python.providers.akshare_extras._memo_clear")
    @patch("src.python.providers.akshare_extras.get_profit_forecast")
    def test_none_result(self, mock_get, mock_memo):
        """None 结果 → 返回 0。"""
        mock_get.return_value = None
        name, count = self._call()
        self.assertEqual(count, 0)


@pytest.mark.unit_core
class TestRefreshSectorFlowCache(unittest.TestCase):
    """_refresh_sector_flow_cache 缓存刷新。"""

    def _call(self):
        from src.python.handlers_cache import _refresh_sector_flow_cache
        return _refresh_sector_flow_cache()

    @patch("src.python.providers.akshare_extras.get_sector_fund_flow")
    def test_success(self, mock_get):
        """成功获取 → 返回 (sector_flow, 行业数)。"""
        mock_get.return_value = [{"name": "电力"}, {"name": "银行"}]
        name, count = self._call()
        self.assertEqual(name, "sector_flow")
        self.assertEqual(count, 2)

    @patch("src.python.providers.akshare_extras.get_sector_fund_flow")
    def test_empty_result(self, mock_get):
        """空列表 → 返回 0。"""
        mock_get.return_value = []
        name, count = self._call()
        self.assertEqual(count, 0)

    @patch("src.python.providers.akshare_extras.get_sector_fund_flow")
    def test_none_result(self, mock_get):
        """None 结果 → 返回 0。"""
        mock_get.return_value = None
        name, count = self._call()
        self.assertEqual(count, 0)


@pytest.mark.unit_core
class TestPrintCacheRefreshReport(unittest.TestCase):
    """_print_cache_refresh_report 输出格式。"""

    def setUp(self):
        self._stdout = io.StringIO()

    def _call(self, **kwargs):
        from src.python.handlers_cache import _print_cache_refresh_report
        with patch("sys.stdout", self._stdout):
            _print_cache_refresh_report(**kwargs)
        return self._stdout.getvalue()

    def test_all_ok(self):
        """全部成功时显示 [OK]。"""
        output = self._call(
            funds=["基金A", "基金B"], perf_ok=2, hold_ok=2, bm_ok=2,
            pf_ok=10, sf_ok=5,
        )
        self.assertIn("全部成功", output)
        self.assertIn("[OK]", output)

    def test_partial_failure(self):
        """部分失败时显示 [!]。"""
        output = self._call(
            funds=["基金A", "基金B"], perf_ok=1, hold_ok=2, bm_ok=0,
            pf_ok=0, sf_ok=0,
        )
        self.assertIn("[!]", output)
        self.assertIn("1 只失败", output)
        self.assertIn("2 只未找到", output)

    def test_no_funds(self):
        """无基金时的输出。"""
        output = self._call(
            funds=[], perf_ok=0, hold_ok=0, bm_ok=0,
            pf_ok=10, sf_ok=5,
        )
        self.assertIn("profit_forecast", output)
        self.assertIn("sector_flow", output)

    def test_sector_flow_fail_hint(self):
        """资金流向获取失败时的提示。"""
        from src.python.handlers_cache import _print_cache_refresh_report
        with patch("sys.stdout", self._stdout):
            _print_cache_refresh_report(
                funds=["基金A"], perf_ok=1, hold_ok=1, bm_ok=1,
                pf_ok=0, sf_ok=0,
            )
        output = self._stdout.getvalue()
        self.assertIn("获取失败", output)

    def test_empty_funds_with_pf_only(self):
        """无基金仅盈利预测成功。"""
        output = self._call(
            funds=[], perf_ok=0, hold_ok=0, bm_ok=0,
            pf_ok=5, sf_ok=0,
        )
        self.assertIn("5 只股票", output)


@pytest.mark.unit_core
class TestCmdCleanupCache(unittest.TestCase):
    """_cmd_cleanup_cache 清理命令。"""

    def test_cleanup_removed_some(self):
        """清理到过期文件。"""
        from src.python.handlers_cache import _cmd_cleanup_cache
        with (
            patch("src.python.cache.cleanup_expired", return_value=5),
            patch("src.python.cache.get_cache_dir", return_value="data/cache"),
            patch("src.python.handlers_cache.press_any_key"),
            patch("sys.stdout", io.StringIO()) as stdout,
        ):
            _cmd_cleanup_cache()
        output = stdout.getvalue()
        self.assertIn("已删除", output)

    def test_cleanup_nothing(self):
        """无过期文件。"""
        from src.python.handlers_cache import _cmd_cleanup_cache
        with (
            patch("src.python.cache.cleanup_expired", return_value=0),
            patch("src.python.cache.get_cache_dir", return_value="data/cache"),
            patch("src.python.handlers_cache.press_any_key"),
            patch("sys.stdout", io.StringIO()) as stdout,
        ):
            _cmd_cleanup_cache()
        output = stdout.getvalue()
        self.assertIn("无需清理", output)


@pytest.mark.unit_core
class TestRefreshIndustryCache(unittest.TestCase):
    """_refresh_industry_cache 行业分类刷新。"""

    def _call(self, holdings):
        from src.python.handlers_cache import _refresh_industry_cache
        return _refresh_industry_cache(holdings)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data")
    def test_with_valid_codes(self, mock_fetch):
        """有效代码返回正确计数。"""
        mock_fetch.return_value = {"600900": {}, "600519": {}}
        from src.python.models import Holding
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
        from src.python.models import Holding
        holdings = [Holding("证券", "测试", "000001", 100, 10.0)]
        count = self._call(holdings)
        self.assertEqual(count, 0)


@pytest.mark.unit_core
class TestRefreshDividendCache(unittest.TestCase):
    """_refresh_dividend_cache 分红刷新。"""

    def _call(self, holdings):
        from src.python.handlers_cache import _refresh_dividend_cache
        return _refresh_dividend_cache(holdings)

    @patch("src.python.providers.akshare_extras.get_dividend_data")
    def test_with_valid_codes(self, mock_get):
        """有效代码返回正确计数。"""
        mock_get.return_value = {"600900": {}, "600519": {}}
        from src.python.models import Holding
        holdings = [
            Holding("证券", "长江电力", "600900", 100, 15.0),
            Holding("证券", "贵州茅台", "600519", 10, 2000.0),
        ]
        count = self._call(holdings)
        self.assertEqual(count, 2)

    @patch("src.python.providers.akshare_extras.get_dividend_data")
    def test_empty_holdings(self, mock_get):
        """空持仓列表返回 0 且不调用 API。"""
        count = self._call([])
        self.assertEqual(count, 0)
        mock_get.assert_not_called()

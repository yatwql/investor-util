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
            total_funds=2,
            perf_ok=2,
            hold_ok=2,
            bm_ok=2,
            pf_ok=10,
            sf_ok=5,
        )
        output = self._call(result)
        self.assertIn("全部成功", output)
        self.assertIn("[OK]", output)

    def test_partial_failure(self):
        """部分失败时显示 [!]。"""
        result = self._make_result(
            total_funds=2,
            perf_ok=1,
            hold_ok=2,
            bm_ok=0,
            pf_ok=0,
            sf_ok=0,
        )
        output = self._call(result)
        self.assertIn("[!]", output)
        self.assertIn("1 只失败", output)
        self.assertIn("2 只未找到", output)

    def test_no_funds(self):
        """无基金时的输出。"""
        result = self._make_result(
            total_funds=0,
            perf_ok=0,
            hold_ok=0,
            bm_ok=0,
            pf_ok=10,
            sf_ok=5,
        )
        output = self._call(result)
        self.assertIn("profit_forecast", output)
        self.assertIn("sector_flow", output)

    def test_sector_flow_fail_hint(self):
        """资金流向获取失败时的提示。"""
        result = self._make_result(
            total_funds=1,
            perf_ok=1,
            hold_ok=1,
            bm_ok=1,
            pf_ok=0,
            sf_ok=0,
        )
        from src.python.tui.handlers_cache import _print_cache_refresh_report

        with patch("sys.stdout", self._stdout):
            _print_cache_refresh_report(result)
        output = self._stdout.getvalue()
        self.assertIn("获取失败", output)

    def test_empty_funds_with_pf_only(self):
        """无基金仅盈利预测成功。"""
        result = self._make_result(
            total_funds=0,
            perf_ok=0,
            hold_ok=0,
            bm_ok=0,
            pf_ok=5,
            sf_ok=0,
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


@pytest.mark.unit_core
class TestRefreshNewsCache(unittest.TestCase):
    """_refresh_news_cache 新闻缓存刷新（operations 版）。"""

    def _call(self, holdings):
        from src.python.cache.operations import _refresh_news_cache

        return _refresh_news_cache(holdings)

    @patch("src.python.cache.operations._get_news_top_count")
    @patch("src.python.report.news_correlation._expand_industry_keywords")
    @patch("src.python.fetcher.news.build_holding_keywords")
    @patch("src.python.fetcher.news.aggregate_news")
    def test_success(self, mock_agg, mock_build, mock_expand, mock_top):
        """有持仓且有关键词 → 复用报告管线并返回关联条数。"""
        from src.python.core.models import Holding

        holdings = [Holding("证券", "长江电力", "600900", 100, 15.0)]
        mock_top.return_value = 300
        mock_build.return_value = ["长江电力"]
        mock_expand.return_value = (["长江电力", "电力行业"], {}, {"电力行业"})
        mock_agg.return_value = [{"title": "a"}, {"title": "b"}, {"title": "c"}]

        count = self._call(holdings)
        self.assertEqual(count, 3)
        mock_build.assert_called_once_with(holdings, penetrated_assets=None)
        mock_expand.assert_called_once_with(holdings, None, ["长江电力"])
        mock_agg.assert_called_once_with(
            ["长江电力", "电力行业"],
            top_n=300,
            per_source=600,
            lightweight_keywords={"电力行业"},
        )

    @patch("src.python.fetcher.news.build_holding_keywords", return_value=[])
    @patch("src.python.fetcher.news.aggregate_news")
    def test_empty_keywords(self, mock_agg, mock_build):
        """关键词为空 → 返回 0 且不调用聚合。"""
        from src.python.core.models import Holding

        holdings = [Holding("证券", "长江电力", "600900", 100, 15.0)]
        self.assertEqual(self._call(holdings), 0)
        mock_agg.assert_not_called()

    def test_no_holdings(self):
        """无持仓 → 返回 0 且不调用任何 API。"""
        with (
            patch("src.python.fetcher.news.build_holding_keywords") as mock_build,
            patch("src.python.fetcher.news.aggregate_news") as mock_agg,
        ):
            self.assertEqual(self._call([]), 0)
        mock_build.assert_not_called()
        mock_agg.assert_not_called()

    @patch("src.python.cache.operations._get_news_top_count")
    @patch("src.python.report.news_correlation._expand_industry_keywords")
    @patch("src.python.fetcher.news.build_holding_keywords")
    @patch("src.python.fetcher.news.aggregate_news")
    def test_empty_news_result(self, mock_agg, mock_build, mock_expand, mock_top):
        """聚合返回空列表 → 返回 0。"""
        from src.python.core.models import Holding

        holdings = [Holding("证券", "长江电力", "600900", 100, 15.0)]
        mock_top.return_value = 300
        mock_build.return_value = ["长江电力"]
        mock_expand.return_value = (["长江电力"], {}, set())
        mock_agg.return_value = []
        self.assertEqual(self._call(holdings), 0)


@pytest.mark.unit_core
class TestRefreshFundManagerCache(unittest.TestCase):
    """_refresh_fund_manager_cache 基金经理缓存刷新（operations 版）。"""

    def _make_fund(self, code="000001", name="测试基金"):
        f = MagicMock()
        f.code = code
        f.name = name
        return f

    def _call(self, funds):
        from src.python.cache.operations import _refresh_fund_manager_cache

        return _refresh_fund_manager_cache(funds)

    @patch("src.python.fetcher.fund_manager.fetch_fund_manager")
    def test_all_success(self, mock_fetch):
        """全部基金成功获取 → 返回基金数。"""
        mock_fetch.return_value = {"manager": "张三"}
        funds = [self._make_fund("000001"), self._make_fund("000002")]
        self.assertEqual(self._call(funds), 2)

    @patch("src.python.fetcher.fund_manager.fetch_fund_manager")
    def test_partial_fail(self, mock_fetch):
        """部分失败（None/异常）→ 只计数成功。"""
        mock_fetch.side_effect = [{"manager": "张三"}, None, Exception("err")]
        funds = [self._make_fund("000001"), self._make_fund("000002"), self._make_fund("000003")]
        self.assertEqual(self._call(funds), 1)

    def test_empty(self):
        """空列表 → 0。"""
        self.assertEqual(self._call([]), 0)


@pytest.mark.unit_core
class TestRefreshExtendedCache(unittest.TestCase):
    """_refresh_extended_cache 风格扩展数据预取（operations 版）。"""

    def _make_holding(self, code, name="测试"):
        from src.python.core.models import Holding

        return Holding("证券", name, code, 100, 10.0)

    def _call(self, holdings):
        from src.python.cache.operations import _refresh_extended_cache

        return _refresh_extended_cache(holdings)

    @patch("src.python.report.fund_style_classify._prefetch_extended_data")
    def test_a_share_codes(self, mock_prefetch):
        """A 股代码 → 调用预取并返回去重代码数。"""
        holdings = [self._make_holding("600900", "长江电力"), self._make_holding("000001", "平安银行")]
        self.assertEqual(self._call(holdings), 2)
        mock_prefetch.assert_called_once()

    @patch("src.python.report.fund_style_classify._prefetch_extended_data")
    def test_dedup(self, mock_prefetch):
        """同一代码出现两次 → 去重后返回 1。"""
        holdings = [self._make_holding("600900"), self._make_holding("600900")]
        self.assertEqual(self._call(holdings), 1)

    @patch("src.python.report.fund_style_classify._prefetch_extended_data")
    def test_no_a_share(self, mock_prefetch):
        """无 A 股（基金/港股）→ 返回 0 且不调用预取。"""
        holdings = [self._make_holding("161725"), self._make_holding("00700")]
        self.assertEqual(self._call(holdings), 0)
        mock_prefetch.assert_not_called()

    def test_empty(self):
        """空持仓 → 0。"""
        self.assertEqual(self._call([]), 0)


@pytest.mark.unit_core
class TestRefreshExtendedCaches(unittest.TestCase):
    """_refresh_extended_caches 扩展缓存并行编排。"""

    def _make_reporter(self):
        return MagicMock()

    def _make_result(self):
        from src.python.cache.operations import CacheUpdateResult

        return CacheUpdateResult()

    @patch("src.python.cache.operations._refresh_extended_cache", return_value=2)
    @patch("src.python.cache.operations._refresh_fund_manager_cache", return_value=1)
    @patch("src.python.cache.operations._refresh_news_cache", return_value=3)
    def test_all_refreshed(self, mock_news, mock_mgr, mock_ext):
        """有持仓且有基金 → 新闻/基金经理/风格扩展全部执行并写入结果。"""
        from src.python.cache.operations import _refresh_extended_caches

        result = self._make_result()
        _refresh_extended_caches(["h1"], ["f1"], result, self._make_reporter())
        self.assertEqual(result.news_ok, 3)
        self.assertEqual(result.manager_ok, 1)
        self.assertEqual(result.ext_ok, 2)
        mock_news.assert_called_once_with(["h1"])
        mock_mgr.assert_called_once_with(["f1"])
        mock_ext.assert_called_once_with(["h1"])

    @patch("src.python.cache.operations._refresh_extended_cache", return_value=2)
    @patch("src.python.cache.operations._refresh_fund_manager_cache", return_value=1)
    @patch("src.python.cache.operations._refresh_news_cache", return_value=3)
    def test_no_funds_skips_manager(self, mock_news, mock_mgr, mock_ext):
        """无基金 → 跳过基金经理刷新，其余照常执行。"""
        from src.python.cache.operations import _refresh_extended_caches

        result = self._make_result()
        _refresh_extended_caches(["h1"], [], result, self._make_reporter())
        self.assertEqual(result.manager_ok, 0)
        self.assertEqual(result.news_ok, 3)
        self.assertEqual(result.ext_ok, 2)
        mock_mgr.assert_not_called()

    @patch("src.python.cache.operations._refresh_extended_cache", side_effect=Exception("boom"))
    @patch("src.python.cache.operations._refresh_fund_manager_cache", return_value=1)
    @patch("src.python.cache.operations._refresh_news_cache", return_value=3)
    def test_exception_recorded(self, mock_news, mock_mgr, mock_ext):
        """单个任务异常 → 记录 errors，其余任务正常写入。"""
        from src.python.cache.operations import _refresh_extended_caches

        result = self._make_result()
        _refresh_extended_caches(["h1"], ["f1"], result, self._make_reporter())
        self.assertEqual(result.news_ok, 3)
        self.assertEqual(result.manager_ok, 1)
        self.assertEqual(result.ext_ok, 0)
        self.assertTrue(result.errors)


@pytest.mark.unit_core
class TestUpdateBasicCacheExtended(unittest.TestCase):
    """update_basic_cache 接线（扩展缓存接入两分支）。"""

    def _make_reporter(self):
        return MagicMock()

    def _make_holding(self, code, name="测试"):
        from src.python.core.models import Holding

        return Holding("证券", name, code, 100, 10.0)

    @patch("src.python.cache.operations._refresh_extended_caches")
    @patch("src.python.cache.operations._refresh_common_caches", return_value=(1, 1, 1, 1))
    @patch("src.python.report.fund_performance.is_fund", return_value=False)
    @patch("src.python.cache.clear_by_group")
    def test_no_funds_path(self, mock_clear, mock_is_fund, mock_common, mock_ext):
        """无基金分支：刷新公共缓存 + 扩展缓存，写入 holdings_count。"""
        from src.python.cache.operations import update_basic_cache

        holdings = [self._make_holding("600900"), self._make_holding("000001")]
        result = update_basic_cache(holdings, self._make_reporter())
        self.assertEqual(result.holdings_count, 2)
        self.assertEqual(result.total_funds, 0)
        self.assertEqual(result.pf_ok, 1)
        self.assertEqual(result.sf_ok, 1)
        self.assertEqual(result.ind_ok, 1)
        self.assertEqual(result.div_ok, 1)
        mock_ext.assert_called_once()
        args = mock_ext.call_args.args
        self.assertEqual(args[0], holdings)
        self.assertEqual(args[1], [])
        self.assertIs(args[2], result)

    @patch("src.python.cache.operations._refresh_extended_caches")
    @patch("src.python.cache.operations._refresh_dividend_cache", return_value=2)
    @patch("src.python.cache.operations._refresh_industry_cache", return_value=3)
    @patch("src.python.cache.operations._refresh_sector_flow_cache", return_value=("sector_flow", 4))
    @patch("src.python.cache.operations._refresh_profit_forecast_cache", return_value=("profit_forecast", 5))
    @patch(
        "src.python.cache.operations._refresh_one_fund_cache",
        return_value=("fund", "000001", "测试基金", True, True, 2, True),
    )
    @patch("src.python.report.fund_performance.is_fund", return_value=True)
    @patch("src.python.cache.clear_by_group")
    def test_funds_path(self, mock_clear, mock_is_fund, mock_fund, mock_pf, mock_sf, mock_ind, mock_div, mock_ext):
        """有基金分支：基金+公共缓存+行业/分红并行提交，随后刷新扩展缓存。"""
        from src.python.cache.operations import update_basic_cache

        holdings = [self._make_holding("161725", "测试基金")]
        result = update_basic_cache(holdings, self._make_reporter())
        self.assertEqual(result.total_funds, 1)
        self.assertEqual(result.perf_ok, 1)
        self.assertEqual(result.hold_ok, 1)
        self.assertEqual(result.bm_ok, 1)
        self.assertEqual(result.pf_ok, 5)
        self.assertEqual(result.sf_ok, 4)
        self.assertEqual(result.ind_ok, 3)
        self.assertEqual(result.div_ok, 2)
        mock_ext.assert_called_once()
        args = mock_ext.call_args.args
        self.assertEqual(args[0], holdings)
        self.assertEqual(args[1], holdings)  # funds = 全部持仓（is_fund 恒 True）
        self.assertIs(args[2], result)


@pytest.mark.unit_core
class TestPrintCacheRefreshReportExtended(unittest.TestCase):
    """_print_cache_refresh_report 扩展缓存三行输出。"""

    def setUp(self):
        self._stdout = io.StringIO()
        from src.python.cache.operations import CacheUpdateResult

        self.CacheUpdateResult = CacheUpdateResult

    def _call(self, result):
        from src.python.tui.handlers_cache import _print_cache_refresh_report

        with patch("sys.stdout", self._stdout):
            _print_cache_refresh_report(result)
        return self._stdout.getvalue()

    def test_extended_ok(self):
        """新闻/基金经理/风格扩展全部成功 → 三行 [OK]。"""
        result = self.CacheUpdateResult(
            total_funds=1,
            perf_ok=1,
            hold_ok=1,
            bm_ok=1,
            pf_ok=0,
            sf_ok=0,
            holdings_count=2,
            news_ok=10,
            manager_ok=1,
            ext_ok=3,
        )
        output = self._call(result)
        self.assertIn("news_{md5}.json", output)
        self.assertIn("fund_manager_{code}.json", output)
        self.assertIn("风格扩展", output)
        self.assertIn("10 条", output)
        self.assertIn("1/1 只基金", output)
        self.assertIn("3 只证券", output)

    def test_extended_fail_gated(self):
        """有持仓/有基金但全部失败 → 显示 [!]。"""
        result = self.CacheUpdateResult(
            total_funds=1,
            perf_ok=1,
            hold_ok=1,
            bm_ok=1,
            pf_ok=0,
            sf_ok=0,
            holdings_count=2,
            news_ok=0,
            manager_ok=0,
            ext_ok=0,
        )
        output = self._call(result)
        self.assertIn("新闻获取失败", output)
        self.assertIn("基金经理获取失败", output)
        self.assertIn("风格扩展", output)

    def test_empty_holdings_no_fail_lines(self):
        """无持仓无基金 → 不输出扩展缓存失败行。"""
        result = self.CacheUpdateResult(
            total_funds=0,
            perf_ok=0,
            hold_ok=0,
            bm_ok=0,
            pf_ok=0,
            sf_ok=0,
            holdings_count=0,
            news_ok=0,
            manager_ok=0,
            ext_ok=0,
        )
        output = self._call(result)
        self.assertNotIn("新闻获取失败", output)
        self.assertNotIn("基金经理获取失败", output)

"""fetcher/fund.py 单元测试。

测试目标：
  - _get_full_benchmark_table 内置库合并
  - _get_benchmark_lock 锁管理
  - _fetch_benchmark_from_api HTML 解析/异常
  - fetch_fund_benchmark 三层策略

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test.test_fund -v
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

from src.python.fetcher.fund import (

    _BUILTIN_BENCHMARKS,
    _get_benchmark_lock,
    _get_full_benchmark_table,
    fetch_fund_benchmark,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]


class TestGetFullBenchmarkTable(unittest.TestCase):
    """_get_full_benchmark_table：内置库 + config 合并"""

    def test_returns_builtin_benchmarks(self):
        """无 config 覆盖时返回内置库副本。"""
        with patch("src.python.fetcher.fund.get_config", return_value={}):
            table = _get_full_benchmark_table()
        self.assertEqual(table, _BUILTIN_BENCHMARKS)
        # 确保是副本，修改不影响原字典
        table.clear()
        self.assertTrue(_BUILTIN_BENCHMARKS)  # 原字典不受影响

    def test_merges_user_overrides(self):
        """config.json 的 user_fund_benchmarks 覆盖内置库。"""
        overrides = {"561910": "自定义基准", "999999": "新基金基准"}
        with patch("src.python.fetcher.fund.get_config",
                   return_value={"user_fund_benchmarks": overrides}):
            table = _get_full_benchmark_table()
        self.assertEqual(table["561910"], "自定义基准")  # 覆盖
        self.assertEqual(table["999999"], "新基金基准")  # 新增
        self.assertEqual(table["159941"], "汇率调整后的纳斯达克100指数收益率")  # 未覆盖保留

    def test_handles_none_user_benchmarks(self):
        """user_fund_benchmarks 为 None 时不崩溃（由 or {} 兜底）。"""
        with patch("src.python.fetcher.fund.get_config",
                   return_value={"user_fund_benchmarks": None}):
            table = _get_full_benchmark_table()
        self.assertEqual(table, _BUILTIN_BENCHMARKS)

    def test_handles_config_exception(self):
        """get_config 抛出异常时回退到内置库。"""
        with patch("src.python.fetcher.fund.get_config", side_effect=KeyError("test")):
            table = _get_full_benchmark_table()
        self.assertEqual(table, _BUILTIN_BENCHMARKS)


class TestGetBenchmarkLock(unittest.TestCase):
    """_get_benchmark_lock：per-code 锁管理"""

    def tearDown(self):
        _benchmark_locks = {}  # 清理全局状态
        import src.python.fetcher.fund as _fm
        _fm._benchmark_locks.clear()

    def test_creates_lock_on_first_access(self):
        """首次访问创建新锁。"""
        lock = _get_benchmark_lock("123456")
        # 跨 Python 版本兼容检查：type(threading.Lock()) 而非 threading.Lock（3.10 平台差异）
        self.assertIsInstance(lock, type(threading.Lock()))

    def test_reuses_existing_lock(self):
        """同一 code 返回同一锁对象。"""
        lock1 = _get_benchmark_lock("123456")
        lock2 = _get_benchmark_lock("123456")
        self.assertIs(lock1, lock2)

    def test_different_codes_get_different_locks(self):
        """不同 code 返回不同锁对象。"""
        lock1 = _get_benchmark_lock("111111")
        lock2 = _get_benchmark_lock("222222")
        self.assertIsNot(lock1, lock2)


class TestFetchBenchmarkFromApi(unittest.TestCase):
    """_fetch_benchmark_from_api：HTML 解析"""

    def _make_html(self, body: str) -> str:
        return f"<!DOCTYPE html><html><head></head><body>{body}</body></html>"

    @patch("src.python.fetcher.fund.make_http_client")
    def test_finds_benchmark_in_html(self, mock_factory):
        """从 HTML 中正确提取业绩比较基准。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client

        resp = MagicMock()
        resp.text = self._make_html('业绩比较基准：沪深300指数收益率×80%+中证全债×20%')
        mock_client.get.return_value = resp

        from src.python.fetcher.fund import _fetch_benchmark_from_api
        result = _fetch_benchmark_from_api("000000")
        self.assertIsNotNone(result)
        self.assertIn("沪深300", result)
        self.assertIn("中证全债", result)

    @patch("src.python.fetcher.fund.make_http_client")
    def test_finds_benchmark_with_colon_variant(self, mock_factory):
        """处理中文冒号「：」的业绩比较基准。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client

        resp = MagicMock()
        resp.text = self._make_html('业绩比较基准:沪深300指数收益率')
        mock_client.get.return_value = resp

        from src.python.fetcher.fund import _fetch_benchmark_from_api
        result = _fetch_benchmark_from_api("000000")
        self.assertEqual(result, "沪深300指数收益率")

    @patch("src.python.fetcher.fund.make_http_client")
    def test_finds_benchmark_in_script(self, mock_factory):
        """从 script 标签中提取基准"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client

        resp = MagicMock()
        resp.text = self._make_html(
            '<script>var data = {benchmark: "中证500指数"}; var 基准: 沪深300指数</script>'
        )
        mock_client.get.return_value = resp

        from src.python.fetcher.fund import _fetch_benchmark_from_api
        result = _fetch_benchmark_from_api("000000")
        self.assertIsNotNone(result)

    @patch("src.python.fetcher.fund.make_http_client")
    def test_returns_none_on_no_match(self, mock_factory):
        """无匹配文本时返回 None。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client

        resp = MagicMock()
        resp.text = self._make_html("<p>没有基准信息</p>")
        mock_client.get.return_value = resp

        from src.python.fetcher.fund import _fetch_benchmark_from_api
        result = _fetch_benchmark_from_api("000000")
        self.assertIsNone(result)

    @patch("src.python.fetcher.fund.make_http_client")
    def test_handles_http_error(self, mock_factory):
        """HTTP 请求异常时返回 None。"""
        import httpx as _httpx_loc
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client

        mock_client.get.side_effect = _httpx_loc.RequestError("timeout")

        from src.python.fetcher.fund import _fetch_benchmark_from_api
        result = _fetch_benchmark_from_api("000000")
        self.assertIsNone(result)

    @patch("src.python.fetcher.fund.make_http_client")
    def test_tries_multiple_urls(self, mock_factory):
        """第一个 URL 失败时尝试第二个 URL。"""
        import httpx as _httpx_loc
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client

        # 第一个 URL 超时，第二个返回有效
        resp = MagicMock()
        resp.text = self._make_html('业绩比较基准：中证全债指数')
        mock_client.get.side_effect = [
            _httpx_loc.RequestError("timeout"),
            resp,
        ]

        from src.python.fetcher.fund import _fetch_benchmark_from_api
        result = _fetch_benchmark_from_api("000000")
        self.assertEqual(result, "中证全债指数")


class TestFetchFundBenchmark(unittest.TestCase):
    """fetch_fund_benchmark：三层策略集成"""

    def tearDown(self):
        import src.python.fetcher.fund as _fm
        _fm._benchmark_locks.clear()

    @patch("src.python.fetcher.fund.cache_get")
    def test_returns_from_cache(self, mock_cache_get):
        """缓存命中时直接返回。"""
        mock_cache_get.return_value = {"000000": "缓存基准"}
        result = fetch_fund_benchmark("000000")
        self.assertEqual(result, "缓存基准")

    @patch("src.python.fetcher.fund.cache_get")
    def test_returns_dash_for_missing_code_in_cache(self, mock_cache_get):
        """缓存命中但 code 不在表中时返回 '--'。"""
        mock_cache_get.return_value = {"111111": "某基准"}
        result = fetch_fund_benchmark("000000")
        self.assertEqual(result, "--")

    @patch("src.python.fetcher.fund.cache_get")
    @patch("src.python.fetcher.fund.cache_set")
    @patch("src.python.fetcher.fund._fetch_benchmark_from_api")
    def test_uses_api_result_when_cache_misses(
        self, mock_api, mock_set, mock_get,
    ):
        """缓存未命中且 API 成功时，基准来自 API 并写入缓存表。"""
        mock_get.return_value = None
        mock_get.return_value = None  # 双重检查锁
        mock_api.return_value = "沪深300"

        result = fetch_fund_benchmark("000000")
        self.assertEqual(result, "沪深300")
        mock_set.assert_called_once()
        table = mock_set.call_args[0][1]
        self.assertIn("000000", table)

    @patch("src.python.fetcher.fund.cache_get")
    @patch("src.python.fetcher.fund.cache_set")
    @patch("src.python.fetcher.fund._fetch_benchmark_from_api")
    def test_falls_back_to_builtin_when_api_fails(
        self, mock_api, mock_set, mock_get,
    ):
        """API 失败时使用内置知识库。"""
        mock_get.return_value = None
        mock_api.return_value = None  # API 失败

        result = fetch_fund_benchmark("561910")  # 内置库有
        self.assertEqual(result, "中证电池主题指数收益率")

    @patch("src.python.fetcher.fund.cache_get")
    @patch("src.python.fetcher.fund.cache_set")
    @patch("src.python.fetcher.fund._fetch_benchmark_from_api")
    def test_returns_dash_when_all_layers_fail(
        self, mock_api, mock_set, mock_get,
    ):
        """全部三层失败时返回 '--'。"""
        mock_get.return_value = None
        mock_api.return_value = None  # API 失败

        result = fetch_fund_benchmark("000000")  # 内置库也没有
        self.assertEqual(result, "--")

    @patch("src.python.fetcher.fund.cache_get")
    @patch("src.python.fetcher.fund.cache_set")
    @patch("src.python.fetcher.fund._fetch_benchmark_from_api")
    def test_double_check_locking(self, mock_api, mock_set, mock_get):
        """双重检查锁：只有第一个进入的线程调 API，第二个线程复用结果。"""
        # 用 Event 控制：API 调用前 cache_get 返回 None，调用后返回有效数据
        api_called = threading.Event()

        def _side(*args, **kwargs):
            # 第 1 次调用（任意线程首次检查）：返回 None → 进入锁
            if not api_called.is_set():
                return None
            # API 已调用后：返回有效数据（模拟缓存生效）
            return {"000000": "沪深300"}

        mock_get.side_effect = _side
        mock_api.side_effect = lambda code: (
            api_called.set() or "沪深300"
        )

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(fetch_fund_benchmark, "000000")
            f2 = ex.submit(fetch_fund_benchmark, "000000")
            r1 = f1.result()
            r2 = f2.result()

        self.assertEqual(r1, "沪深300")
        self.assertEqual(r2, "沪深300")
        # API 仅调用一次（锁+双重检查确保）
        self.assertEqual(mock_api.call_count, 1)


if __name__ == "__main__":
    unittest.main()


# ═══════════════════════════════════════════════════════════
#  批量接口测试
# ═══════════════════════════════════════════════════════════


class TestFetchFundRankingsBatch(unittest.TestCase):
    """fetch_fund_rankings_batch 批量并行获取。"""

    def test_empty_list_returns_empty_dict(self):
        """空列表 → 空 dict。"""
        from src.python.fetcher.fund import fetch_fund_rankings_batch

        result = fetch_fund_rankings_batch([])
        self.assertEqual(result, {})

    @patch("src.python.fetcher.batch.BatchDispatcher")
    def test_single_fund(self, mock_dispatcher_cls):
        """单基金返回正确映射。"""
        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = [
            type("R", (), {"success": True, "result": {"rank": 1}})(),
        ]
        mock_dispatcher_cls.return_value = mock_disp

        from src.python.fetcher.fund import fetch_fund_rankings_batch

        result = fetch_fund_rankings_batch(["000001"])
        self.assertIn("000001", result)
        self.assertEqual(result["000001"]["rank"], 1)

    @patch("src.python.fetcher.batch.BatchDispatcher")
    def test_partial_failures(self, mock_dispatcher_cls):
        """部分失败 → 缺失项为 None。"""
        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = [
            type("R", (), {"success": True, "result": {"rank": 1}})(),
            type("R", (), {"success": False, "result": None, "error": "err"})(),
            type("R", (), {"success": True, "result": {"rank": 3}})(),
        ]
        mock_dispatcher_cls.return_value = mock_disp

        from src.python.fetcher.fund import fetch_fund_rankings_batch

        result = fetch_fund_rankings_batch(["000001", "000002", "000003"])
        self.assertIsNotNone(result["000001"])
        self.assertIsNone(result["000002"])
        self.assertIsNotNone(result["000003"])

    @patch("src.python.fetcher.batch.BatchDispatcher")
    def test_uses_cache_check(self, mock_dispatcher_cls):
        """使用 execute_with_cache_check（非 execute）。"""
        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = []
        mock_dispatcher_cls.return_value = mock_disp

        from src.python.fetcher.fund import fetch_fund_rankings_batch

        fetch_fund_rankings_batch(["000001"])
        mock_disp.execute_with_cache_check.assert_called_once()

    def test_external_dispatcher_no_shutdown(self):
        """传入外部 dispatcher 时不 shutdown。"""
        from unittest.mock import MagicMock

        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = [
            type("R", (), {"success": True, "result": {"rank": 1}})(),
        ]

        from src.python.fetcher.fund import fetch_fund_rankings_batch

        result = fetch_fund_rankings_batch(["000001"], dispatcher=mock_disp)
        self.assertIn("000001", result)
        mock_disp.shutdown.assert_not_called()


class TestFetchFundHoldingsBatch(unittest.TestCase):
    """fetch_fund_holdings_batch 批量并行获取。"""

    def test_empty_list_returns_empty_dict(self):
        """空列表 → 空 dict。"""
        from src.python.fetcher.fund import fetch_fund_holdings_batch

        result = fetch_fund_holdings_batch([])
        self.assertEqual(result, {})

    @patch("src.python.fetcher.batch.BatchDispatcher")
    def test_uses_cache_check_method(self, mock_dispatcher_cls):
        """使用 execute_with_cache_check（缓存优先）。"""
        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = [
            type("R", (), {"success": True, "result": {"holdings": []}})(),
        ]
        mock_dispatcher_cls.return_value = mock_disp

        from src.python.fetcher.fund import fetch_fund_holdings_batch

        result = fetch_fund_holdings_batch(["000001"])
        self.assertEqual(len(result), 1)

    @patch("src.python.fetcher.batch.BatchDispatcher")
    def test_partial_failures(self, mock_dispatcher_cls):
        """部分失败 → 缺失项为 None。"""
        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = [
            type("R", (), {"success": True, "result": {"holdings": []}})(),
            type("R", (), {"success": False, "result": None, "error": "err"})(),
        ]
        mock_dispatcher_cls.return_value = mock_disp

        from src.python.fetcher.fund import fetch_fund_holdings_batch

        result = fetch_fund_holdings_batch(["000001", "000002"])
        self.assertIsNotNone(result["000001"])
        self.assertIsNone(result["000002"])

    def test_calls_fetch_fund_holdings_cached_internally(self):
        """内部使用 fetch_fund_holdings_cached（含 session_cache）。"""
        from src.python.fetcher.fund import fetch_fund_holdings_batch, fetch_fund_holdings_cached

        # Verify the batch function uses the cached variant
        from functools import partial
        import inspect

        # Check that the source references fetch_fund_holdings_cached
        src = inspect.getsource(fetch_fund_holdings_batch)
        self.assertIn("fetch_fund_holdings_cached", src)

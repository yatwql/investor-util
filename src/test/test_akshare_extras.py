"""akshare 扩展数据源单元测试。

测试目标：
  - get_profit_forecast — 缓存降级逻辑 + 异常安全
  - get_sector_fund_flow — 同
  - get_dividend_data — 指纹 + 缓存 + 分红计算 + 降级
  - _calc_dividend_summary — 分红 DataFrame 解析逻辑
  - _compute_dividend_fingerprint — 指纹稳定性

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_akshare_extras -v
"""

from __future__ import annotations

import json
import hashlib
import threading
import unittest
from unittest.mock import MagicMock, patch

from src.python.providers import akshare_extras as ae


class TestComputeDividendFingerprint(unittest.TestCase):
    """测试分红指纹计算。"""

    def test_empty_list(self) -> None:
        self.assertEqual(ae._compute_dividend_fingerprint([]), "empty")

    def test_single_code(self) -> None:
        fp = ae._compute_dividend_fingerprint(["600519"])
        self.assertEqual(len(fp), 12)

    def test_sorted_stable(self) -> None:
        fp1 = ae._compute_dividend_fingerprint(["600519", "000858"])
        fp2 = ae._compute_dividend_fingerprint(["000858", "600519"])
        self.assertEqual(fp1, fp2, "指纹应忽略代码顺序")

    def test_different_codes_different_fp(self) -> None:
        fp1 = ae._compute_dividend_fingerprint(["600519"])
        fp2 = ae._compute_dividend_fingerprint(["000858"])
        self.assertNotEqual(fp1, fp2, "不同代码应生成不同指纹")


class TestCalcDividendSummary(unittest.TestCase):
    """测试分红数据汇总计算。"""

    @staticmethod
    def _make_df(rows: list[dict]) -> MagicMock:
        """模拟 akshare 返回的 DataFrame。"""
        df = MagicMock()
        df.empty = False
        df.columns = ["股票代码", "股票简称", "除权除息日", "每股股利(税前)(元)", "每股股利(税后)(元)"]
        df.__iter__.return_value = iter(df.columns)
        df.__len__.return_value = len(rows)

        def _iterrows():
            for r in rows:
                yield (0, r)
        df.iterrows = _iterrows
        return df

    def test_normal_data(self) -> None:
        rows = [
            {"股票代码": "600519", "股票简称": "贵州茅台", "除权除息日": "2025-06-19",
             "每股股利(税前)(元)": 21.875, "每股股利(税后)(元)": 17.5},
            {"股票代码": "600519", "股票简称": "贵州茅台", "除权除息日": "2024-06-19",
             "每股股利(税前)(元)": 19.0, "每股股利(税后)(元)": 15.2},
            {"股票代码": "600519", "股票简称": "贵州茅台", "除权除息日": "2023-06-20",
             "每股股利(税前)(元)": 17.5, "每股股利(税后)(元)": 14.0},
        ]
        df = self._make_df(rows)
        result = ae._calc_dividend_summary(df)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["avg_dividend"], (21.875 + 19.0 + 17.5) / 3, places=4)
        self.assertEqual(result["years"], 3)
        self.assertEqual(result["record_count"], 3)

    def test_single_year(self) -> None:
        rows = [
            {"股票代码": "600519", "股票简称": "贵州茅台", "除权除息日": "2025-06-19",
             "每股股利(税前)(元)": 21.875, "每股股利(税后)(元)": 17.5},
        ]
        df = self._make_df(rows)
        result = ae._calc_dividend_summary(df)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["avg_dividend"], 21.875, places=4)
        self.assertEqual(result["years"], 1)

    def test_multiple_dividends_same_year(self) -> None:
        """同一年多次分红，应累加后按年计算。"""
        rows = [
            {"股票代码": "600036", "股票简称": "招商银行", "除权除息日": "2025-07-11",
             "每股股利(税前)(元)": 1.2, "每股股利(税后)(元)": 0.96},
            {"股票代码": "600036", "股票简称": "招商银行", "除权除息日": "2025-01-15",
             "每股股利(税前)(元)": 0.5, "每股股利(税后)(元)": 0.4},
            {"股票代码": "600036", "股票简称": "招商银行", "除权除息日": "2024-07-12",
             "每股股利(税前)(元)": 1.1, "每股股利(税后)(元)": 0.88},
        ]
        df = self._make_df(rows)
        result = ae._calc_dividend_summary(df)
        self.assertIsNotNone(result)
        # 2025: 1.2 + 0.5 = 1.7, 2024: 1.1 → avg = (1.7 + 1.1) / 2 = 1.4
        self.assertAlmostEqual(result["avg_dividend"], 1.4, places=4)
        self.assertEqual(result["years"], 2)

    def test_no_dividend_column(self) -> None:
        """无每股股利列 → None。"""
        df = MagicMock()
        df.empty = False
        df.columns = ["股票代码"]
        df.iterrows.return_value = iter([])
        result = ae._calc_dividend_summary(df)
        self.assertIsNone(result)

    def test_empty_df(self) -> None:
        df = MagicMock()
        df.empty = True
        self.assertIsNone(ae._calc_dividend_summary(df))

    def test_none_df(self) -> None:
        self.assertIsNone(ae._calc_dividend_summary(None))


class TestGetDividendData(unittest.TestCase):
    """测试 get_dividend_data 缓存/降级/数据流。"""

    def setUp(self):
        ae._memo_clear()

    @patch("src.python.providers.akshare_extras.cache_get", return_value=None)
    @patch("src.python.providers.akshare_extras.cache_set")
    @patch("src.python.providers.akshare_extras._compute_dividend_fingerprint", return_value="testfp")
    @patch("src.python.providers.akshare_extras.as_completed")
    @patch("src.python.providers.akshare_extras.ThreadPoolExecutor")
    def test_success_path(
        self, mock_pool: MagicMock, mock_completed: MagicMock,
        mock_fp: MagicMock, mock_set: MagicMock, mock_get: MagicMock,
    ) -> None:
        """正常路径：获取分红数据。"""
        # 模拟 ThreadPoolExecutor
        ctx = MagicMock()
        ctx.__enter__.return_value = ctx
        mock_pool.return_value = ctx

        # 模拟 future 结果
        future = MagicMock()
        future.result.return_value = ("600519", {
            "avg_dividend": 19.4583, "years": 3, "record_count": 3, "name": "贵州茅台",
        })
        ctx.submit.return_value = future
        mock_completed.return_value = [future]

        result = ae.get_dividend_data(["600519", "000858"])
        self.assertIn("600519", result)
        self.assertAlmostEqual(result["600519"]["avg_dividend"], 19.4583, places=4)
        mock_set.assert_called_once()

    @patch("src.python.providers.akshare_extras.cache_get")
    def test_cache_hit(self, mock_get: MagicMock) -> None:
        """缓存命中时直接返回。"""
        cached = {"600519": {"avg_dividend": 19.46, "years": 3, "record_count": 3}}
        mock_get.return_value = cached
        result = ae.get_dividend_data(["600519"])
        self.assertEqual(result, cached)

    def test_no_a_stock_codes(self) -> None:
        """无 A 股代码应返回空 dict。"""
        result = ae.get_dividend_data(["518880", "159915"])
        self.assertEqual(result, {})

    @patch("src.python.providers.akshare_extras.cache_get", return_value=None)
    @patch("src.python.providers.akshare_extras.cache_set")
    def test_empty_codes(self, mock_set: MagicMock, mock_get: MagicMock) -> None:
        """空代码列表应返回空 dict。"""
        result = ae.get_dividend_data([])
        self.assertEqual(result, {})
        mock_set.assert_not_called()

    @patch("src.python.providers.akshare_extras.cache_get", return_value=None)
    @patch("src.python.providers.akshare_extras.cache_set")
    @patch("src.python.providers.akshare_extras.as_completed")
    @patch("src.python.providers.akshare_extras.ThreadPoolExecutor")
    def test_dividend_memo_second_call(
        self, mock_pool: MagicMock, mock_completed: MagicMock,
        mock_set: MagicMock, mock_get: MagicMock,
    ) -> None:
        """相同代码列表第二次调用应命中 memo，不重复 fetch。"""
        ctx = MagicMock()
        ctx.__enter__.return_value = ctx
        mock_pool.return_value = ctx
        future = MagicMock()
        future.result.return_value = ("600519", {
            "avg_dividend": 19.4583, "years": 3, "record_count": 3, "name": "贵州茅台",
        })
        ctx.submit.return_value = future
        mock_completed.return_value = [future]

        # 第一次调用 — 走 fetch
        result1 = ae.get_dividend_data(["600519"])
        self.assertIn("600519", result1)
        self.assertEqual(mock_pool.call_count, 1)

        # 重置 mock，准备验证第二次不再调用
        mock_pool.reset_mock()
        mock_get.reset_mock()

        # 第二次调用 — 应命中 memo
        result2 = ae.get_dividend_data(["600519"])
        self.assertEqual(result2, result1)
        mock_pool.assert_not_called()


class TestCacheKey(unittest.TestCase):
    """测试缓存键生成。"""

    def test_with_fingerprint(self) -> None:
        key = ae._cache_key("dividend_", "abc123def456")
        self.assertEqual(key, "dividend_abc123def456")

    def test_without_fingerprint(self) -> None:
        key = ae._cache_key("dividend_", "")
        self.assertEqual(key, "dividend_nofp")


class TestMemoCache(unittest.TestCase):
    """测试进程级内存 TTL 缓存层。"""

    def setUp(self):
        ae._memo_clear()

    def test_set_get(self) -> None:
        ae._memo_set("profit_forecast", {"000001": {"name": "平安银行"}})
        val = ae._memo_get("profit_forecast")
        self.assertEqual(val, {"000001": {"name": "平安银行"}})

    def test_miss_on_different_key(self) -> None:
        ae._memo_set("key_a", "value_a")
        val = ae._memo_get("key_b")
        self.assertIsNone(val)

    def test_ttl_expiry(self) -> None:
        """直接操纵时间戳模拟 TTL 过期。"""
        now = ae._time.time()
        ae._memo_set("dividend:abc", "dividend_data")
        # 修改时间戳为 700 秒前（dividend TTL 600s，肯定过期）
        ae._MEMO_CACHE["dividend:abc"] = ("dividend_data", now - 700)
        val = ae._memo_get("dividend:abc")
        self.assertIsNone(val)

    def test_ttl_within_boundary(self) -> None:
        """在 TTL 内应正常返回。"""
        now = ae._time.time()
        ae._memo_set("dividend:abc", "dividend_data")
        # 修改时间戳为 500 秒前（dividend TTL 600s，未过期）
        ae._MEMO_CACHE["dividend:abc"] = ("dividend_data", now - 500)
        val = ae._memo_get("dividend:abc")
        self.assertEqual(val, "dividend_data")

    def test_thread_safety(self) -> None:
        """并发读写不应崩溃。"""
        errors: list[Exception] = []

        def _worker(n: int) -> None:
            try:
                for _ in range(100):
                    ae._memo_set(f"k{n}", n)
                    ae._memo_get(f"k{n}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

"""缓存清理与统计单元测试 — _cleanup / _stats / _groups 子模块。

测试目标：
  - cleanup_expired — 过期清理、损坏清理、dry_run
  - get_cache_stats — 文件计数/大小/前缀分组
  - clear_by_group — 按组清除缓存
  - get_cache_age — 缓存文件年龄查询

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/core/test_cache_cleanup.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

# ═══════════════════════════════════════════════════════════
#  基类：统一的临时目录 + 补丁
# ═══════════════════════════════════════════════════════════


class CacheTestBase(unittest.TestCase):
    """所有缓存测试的基类。在 setUp 中创建临时目录并替换 _CACHE_DIR。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache_dir = self._tmpdir.name
        self._patcher_paths = patch("src.python.cache._paths._CACHE_DIR", self.cache_dir)
        self._patcher_stats = patch("src.python.cache._stats._CACHE_DIR", self.cache_dir)
        self._patcher_cleanup = patch("src.python.cache._cleanup._CACHE_DIR", self.cache_dir)
        self._patcher_groups = patch("src.python.cache._groups._CACHE_DIR", self.cache_dir)
        self._patcher_paths.start()
        self._patcher_stats.start()
        self._patcher_cleanup.start()
        self._patcher_groups.start()

    def tearDown(self):
        self._patcher_groups.stop()
        self._patcher_cleanup.stop()
        self._patcher_stats.stop()
        self._patcher_paths.stop()
        self._tmpdir.cleanup()

    def _write_cache(self, key: str, data: object, ts: float) -> str:
        """向缓存目录写入指定内容的 JSON 文件，返回完整路径。"""
        safe = key.replace("/", "_").replace("\\", "_").replace("..", "_")
        path = os.path.join(self.cache_dir, f"{safe}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_ts": ts, "_data": data}, f, ensure_ascii=False)
        return path

    def _write_gz_cache(self, key: str, data: object, ts: float) -> str:
        """向缓存目录写入 gzip 压缩的 JSON 文件，返回完整路径。"""
        import gzip

        safe = key.replace("/", "_").replace("\\", "_").replace("..", "_")
        path = os.path.join(self.cache_dir, f"{safe}.json.gz")
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump({"_ts": ts, "_data": data}, f, ensure_ascii=False)
        return path


# ═══════════════════════════════════════════════════════════
#  get_cache_stats 测试
# ═══════════════════════════════════════════════════════════


class TestCacheGetStats(CacheTestBase):
    """测试 get_cache_stats 的统计功能。"""

    def test_empty_dir(self):
        """空目录 → 全零统计。"""
        from src.python.cache import get_cache_stats

        stats = get_cache_stats()
        self.assertEqual(stats["total_files"], 0)
        self.assertEqual(stats["total_size_bytes"], 0)
        self.assertEqual(stats["by_prefix"], {})

    def test_missing_dir(self):
        """目录不存在 → 全零统计。"""
        import shutil

        shutil.rmtree(self.cache_dir)
        from src.python.cache import get_cache_stats

        stats = get_cache_stats()
        self.assertEqual(stats["total_files"], 0)

    def test_files_counted(self):
        """多个缓存文件 → 正确计数。"""
        self._write_cache("price_a", 1, 100.0)
        self._write_cache("price_b", 2, 100.0)
        self._write_cache("index_c", 3, 100.0)

        from src.python.cache import get_cache_stats

        stats = get_cache_stats()
        self.assertEqual(stats["total_files"], 3)

    def test_files_size_summed(self):
        """文件大小累加正确。"""
        self._write_cache("small", "x", 100.0)
        path = os.path.join(self.cache_dir, "big.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_ts": 100.0, "_data": "x" * 1000}, f)

        from src.python.cache import get_cache_stats

        stats = get_cache_stats()
        self.assertGreater(stats["total_size_bytes"], 0)

    def test_prefix_grouping(self):
        """文件名前缀分组正确。"""
        self._write_cache("price_a", 1, 100.0)
        self._write_cache("price_b", 2, 100.0)
        self._write_cache("index_a", 3, 100.0)
        self._write_cache("other", 4, 100.0)

        from src.python.cache import get_cache_stats

        stats = get_cache_stats()
        self.assertEqual(stats["by_prefix"]["price"], 2)
        self.assertEqual(stats["by_prefix"]["index"], 1)
        self.assertIn("other", stats["by_prefix"])

    def test_non_json_ignored(self):
        """非 .json 文件不被计入统计。"""
        self._write_cache("mykey", 1, 100.0)
        path = os.path.join(self.cache_dir, "readme.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not cache")

        from src.python.cache import get_cache_stats

        stats = get_cache_stats()
        self.assertEqual(stats["total_files"], 1)

    def test_no_underscore_goes_to_other(self):
        """文件名不含下划线 → 归入 other 分组。"""
        self._write_cache("abc", 1, 100.0)

        from src.python.cache import get_cache_stats

        stats = get_cache_stats()
        self.assertEqual(stats["by_prefix"].get("other"), 1)


# ═══════════════════════════════════════════════════════════
#  cleanup_expired 测试
# ═══════════════════════════════════════════════════════════


class TestCleanupExpired(CacheTestBase):
    """测试 cleanup_expired 的全部分支。"""

    def _set_time_and_write(self, key: str, data: object, ts: float):
        """写入缓存并返回路径。"""
        return self._write_cache(key, data, ts)

    def _read_ts_file(self, key: str) -> float:
        path = os.path.join(self.cache_dir, f"{key}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("_ts", 0)

    @patch("src.python.cache._cleanup.time.time")
    def test_empty_dir_returns_zero(self, mock_time):
        """空目录 → 返回 0。"""
        mock_time.return_value = 1000.0
        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 0)

    @patch("src.python.cache._cleanup.time.time")
    def test_missing_dir_returns_zero(self, mock_time):
        """目录不存在 → 返回 0。"""
        import shutil

        shutil.rmtree(self.cache_dir)
        mock_time.return_value = 1000.0
        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 0)

    @patch("src.python.cache._cleanup.time.time")
    @patch("src.python.cache._cleanup.get_ttl")
    def test_expired_files_deleted(self, mock_ttl, mock_time):
        """过期的缓存文件被删除。"""
        mock_time.return_value = 10000.0
        mock_ttl.return_value = 100.0

        self._set_time_and_write("price_old", 1, ts=9500.0)
        self._set_time_and_write("price_fresh", 2, ts=9950.0)

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 1)

        old_path = os.path.join(self.cache_dir, "price_old.json")
        fresh_path = os.path.join(self.cache_dir, "price_fresh.json")
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(fresh_path))

    @patch("src.python.cache._cleanup.time.time")
    @patch("src.python.cache._cleanup.get_ttl")
    def test_dry_run_does_not_delete(self, mock_ttl, mock_time):
        """dry_run=True 时文件不被删除，但计数正确。"""
        mock_time.return_value = 10000.0
        mock_ttl.return_value = 100.0

        self._set_time_and_write("price_old", 1, ts=9500.0)
        self._set_time_and_write("price_keep", 2, ts=9950.0)

        from src.python.cache import cleanup_expired

        count = cleanup_expired(dry_run=True)
        self.assertEqual(count, 1)
        old_path = os.path.join(self.cache_dir, "price_old.json")
        self.assertTrue(os.path.exists(old_path))

    @patch("src.python.cache._cleanup.time.time")
    def test_corrupted_file_deleted_in_cleanup(self, mock_time):
        """损坏的文件在 cleanup 中被删除。"""
        mock_time.return_value = 1000.0
        path = os.path.join(self.cache_dir, "broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{{broken")

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 1)
        self.assertFalse(os.path.exists(path))

    @patch("src.python.cache._cleanup.time.time")
    def test_corrupted_file_dry_run(self, mock_time):
        """损坏的文件在 dry_run 时只计数不删除。"""
        mock_time.return_value = 1000.0
        path = os.path.join(self.cache_dir, "broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{{broken")

        from src.python.cache import cleanup_expired

        count = cleanup_expired(dry_run=True)
        self.assertEqual(count, 1)
        self.assertTrue(os.path.exists(path))

    @patch("src.python.cache._cleanup.time.time")
    @patch("src.python.cache._cleanup.get_ttl")
    def test_non_json_ignored(self, mock_ttl, mock_time):
        """非 .json 文件被忽略。"""
        mock_time.return_value = 1000.0
        mock_ttl.return_value = 100.0

        path = os.path.join(self.cache_dir, "notes.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not cache")

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 0)
        self.assertTrue(os.path.exists(path))

    @patch("src.python.cache._cleanup.time.time")
    @patch("src.python.cache._cleanup.get_ttl")
    def test_multiple_prefixes_use_different_ttl(self, mock_ttl, mock_time):
        """不同前缀使用对应 TTL 判断过期。"""
        mock_time.return_value = 10000.0

        def ttl_side_effect(dtype: str) -> float:
            mapping = {"price": 100.0, "news": 500.0}
            return mapping.get(dtype, 300.0)

        mock_ttl.side_effect = ttl_side_effect

        self._set_time_and_write("price_old", 1, ts=9800.0)
        self._set_time_and_write("news_old", 2, ts=9800.0)

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 1)
        self.assertFalse(os.path.exists(os.path.join(self.cache_dir, "price_old.json")))
        self.assertTrue(os.path.exists(os.path.join(self.cache_dir, "news_old.json")))

    @patch("src.python.cache._cleanup.time.time")
    @patch("src.python.cache._cleanup.get_ttl")
    def test_cleanup_os_error_removal_skipped(self, mock_ttl, mock_time):
        """删除文件时 OSError 被吞掉。"""
        mock_time.return_value = 10000.0
        mock_ttl.return_value = 1.0

        self._set_time_and_write("price_x", 1, ts=100.0)

        from src.python.cache import cleanup_expired as real_clean

        with patch("src.python.cache._cleanup.os.remove") as mock_remove:
            mock_remove.side_effect = OSError("permission denied")
            count = real_clean()
            self.assertEqual(count, 0)

    @patch("src.python.cache._cleanup.time.time")
    def test_unknown_prefix_uses_default_ttl(self, mock_time):
        """未知前缀的缓存文件按默认 TTL 判断过期。"""
        mock_time.return_value = 10000.0
        self._set_time_and_write("unknown_xyz", 1, ts=9500.0)

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 0)

    @patch("src.python.cache._cleanup.time.time")
    def test_trading_calendar_not_cleaned_early(self, mock_time):
        """交易日历注册了 exact key → 使用 calendar TTL。"""
        mock_time.return_value = 10000.0
        self._set_time_and_write("trading_calendar", ["2026-01-01"], ts=8000.0)

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 0)
        path = os.path.join(self.cache_dir, "trading_calendar.json")
        self.assertTrue(os.path.exists(path))

    @patch("src.python.cache._cleanup.time.time")
    @patch("src.python.cache._cleanup.get_ttl")
    def test_sorted_file_processing(self, mock_ttl, mock_time):
        """文件按名称排序处理，不报错。"""
        mock_time.return_value = 10000.0
        mock_ttl.return_value = 1.0

        self._set_time_and_write("a_file", 1, ts=100.0)
        self._set_time_and_write("b_file", 2, ts=100.0)
        self._set_time_and_write("c_file", 3, ts=100.0)

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 3)


# ═══════════════════════════════════════════════════════════
#  clear_by_group 测试
# ═══════════════════════════════════════════════════════════


class TestClearByGroup(CacheTestBase):
    """测试 clear_by_group 函数。"""

    def test_clear_refresh_group_deletes_matching(self):
        """refresh 组清除基金/新闻/行业/分红/盈利预测缓存，保留 preload 组。"""
        self._write_cache("fund_perf_000001", {"d": 1}, ts=1000.0)
        self._write_cache("news_abc", {"d": 2}, ts=1000.0)
        self._write_cache("industry_600000", {"d": 3}, ts=1000.0)
        self._write_cache("dividend_600000", {"d": 4}, ts=1000.0)
        self._write_cache("price_600000", {"d": 5}, ts=1000.0)

        from src.python.cache import clear_by_group

        result = clear_by_group("refresh")

        for key in ("fund_perf_000001", "news_abc", "industry_600000", "dividend_600000"):
            self.assertFalse(os.path.exists(os.path.join(self.cache_dir, f"{key}.json")))
        self.assertTrue(os.path.exists(os.path.join(self.cache_dir, "price_600000.json")))
        self.assertIn("基金业绩排名", result)

    def test_clear_preload_group(self):
        """preload 组清除价格/指数/LLM 缓存，保留 refresh 组。"""
        self._write_cache("price_000001", {"d": 1}, ts=1000.0)
        self._write_cache("index_sh000001", {"d": 2}, ts=1000.0)
        self._write_cache("llm_global_macro_abc", {"d": 3}, ts=1000.0)
        self._write_cache("news_abc", {"d": 4}, ts=1000.0)

        from src.python.cache import clear_by_group

        result = clear_by_group("preload")

        for key in ("price_000001", "index_sh000001", "llm_global_macro_abc"):
            self.assertFalse(os.path.exists(os.path.join(self.cache_dir, f"{key}.json")))
        self.assertTrue(os.path.exists(os.path.join(self.cache_dir, "news_abc.json")))
        self.assertIn("股票价格", result)

    def test_clear_refresh_clears_exact_keys(self):
        """refresh 组也清除 fund_benchmarks 精确键名。"""
        self._write_cache("fund_benchmarks", {"d": 1}, ts=1000.0)
        from src.python.cache import clear_by_group

        result = clear_by_group("refresh")
        self.assertFalse(os.path.exists(os.path.join(self.cache_dir, "fund_benchmarks.json")))
        self.assertIn("基金业绩基准", result)

    def test_clear_unknown_group(self):
        """未知组名返回空字典。"""
        from src.python.cache import clear_by_group

        self.assertEqual(clear_by_group("nonexistent"), {})

    def test_clear_group_empty_dir(self):
        """空目录不报错。"""
        from src.python.cache import clear_by_group

        self.assertEqual(clear_by_group("refresh"), {})


# ═══════════════════════════════════════════════════════════
#  get_cache_age 测试
# ═══════════════════════════════════════════════════════════


class TestGetCacheAge(CacheTestBase):
    """测试 get_cache_age() 函数。"""

    @patch("src.python.cache._ttl.time.time")
    def test_get_cache_age_fresh(self, mock_time):
        """缓存刚写入 → 年龄 ≈0。"""
        from src.python.cache import set, get_cache_age

        mock_time.return_value = 1000.0
        set("age_test", "data")

        age = get_cache_age("age_test")
        self.assertIsNotNone(age)
        self.assertAlmostEqual(age, 0, delta=0.1)

    @patch("src.python.cache._ttl.time.time")
    def test_get_cache_age_aged(self, mock_time):
        """写入后快进 → 年龄 = 时间差。"""
        from src.python.cache import set, get_cache_age

        mock_time.return_value = 1000.0
        set("age_test2", "data")

        mock_time.return_value = 2000.0
        age = get_cache_age("age_test2")
        self.assertIsNotNone(age)
        self.assertAlmostEqual(age, 1000.0, delta=0.1)

    def test_get_cache_age_missing(self):
        """缓存不存在 → 返回 None。"""
        from src.python.cache import get_cache_age

        self.assertIsNone(get_cache_age("nonexistent_key"))

    def test_get_cache_age_gz(self):
        """gzip 压缩的缓存也正确返回年龄。"""
        ts_now = 10000.0
        self._write_gz_cache("gz_age", "some_data", ts=ts_now)
        from src.python.cache import get_cache_age

        age = get_cache_age("gz_age")
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 0)

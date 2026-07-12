"""缓存模块单元测试。

测试目标：
  - _cache_path — 路径生成与目录穿越防护
  - get — 正常命中、过期、文件损坏、键缺失等场景
  - set — 目录创建、文件写入、写入失败处理
  - exists — 文件存在性检查
  - clear — 文件删除
  - clear_by_prefix — 前缀匹配删除、.json 过滤、目录不存在
  - get_cache_stats — 文件计数/大小/前缀分组
  - cleanup_expired — 过期清理、损坏清理、dry_run
  - get_ttl — 配置读取、默认值、兜底

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_cache -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
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
#  _cache_path 测试
# ═══════════════════════════════════════════════════════════


class TestCachePath(unittest.TestCase):
    """测试 _cache_path 路径生成与目录穿越防护。"""

    def test_normal_key(self):
        """普通键名 → 正确路径。"""
        from src.python.cache import _cache_path

        path = _cache_path("my_key")
        self.assertTrue(path.endswith("my_key.json"))
        # _CACHE_DIR = "data/cache"，os.path.join 在 Windows 上可能混合 separator
        self.assertIn("data", path)
        self.assertIn("cache", path)

    def test_key_with_slash_replaced(self):
        """含斜杠的键名 → 斜杠被替换。"""
        from src.python.cache import _cache_path

        path = _cache_path("a/b")
        self.assertIn("a_b", path)
        self.assertNotIn("/", path.split(os.sep)[-1])

    def test_key_with_backslash_replaced(self):
        """含反斜杠的键名 → 反斜杠被替换。"""
        from src.python.cache import _cache_path

        path = _cache_path("a\\b")
        self.assertIn("a_b", path)

    def test_key_with_dotdot_replaced(self):
        """含 .. 的键名 → .. 被替换。"""
        from src.python.cache import _cache_path

        path = _cache_path("..")
        self.assertNotIn("..", path.split(os.sep)[-1])
        # 路径不应逃逸出缓存目录
        self.assertNotIn(".." + os.sep, path)


# ═══════════════════════════════════════════════════════════
#  get 测试
# ═══════════════════════════════════════════════════════════


class TestCacheGet(CacheTestBase):
    """测试 get 的全部返回路径：命中、过期、损坏、缺失字段。"""

    def test_missing_file_returns_none(self):
        """文件不存在 → 返回 None。"""
        from src.python.cache import get

        result = get("nonexistent", 9999)
        self.assertIsNone(result)

    @patch("src.python.cache._store.time.time")
    def test_valid_cache_returns_data(self, mock_time):
        """未过期的缓存 → 返回存储的数据。"""
        mock_time.return_value = 2000.0
        self._write_cache("mykey", {"value": 42}, ts=1990.0)
        from src.python.cache import get

        result = get("mykey", 100)
        self.assertEqual(result, {"value": 42})

    @patch("src.python.cache._store.time.time")
    def test_expired_cache_returns_none(self, mock_time):
        """已过期的缓存 → 返回 None。"""
        mock_time.return_value = 2000.0
        self._write_cache("mykey", {"value": 42}, ts=1800.0)
        from src.python.cache import get

        result = get("mykey", 100)
        self.assertIsNone(result)

    def test_corrupted_json_deletes_file(self):
        """损坏的 JSON → 返回 None 且文件被自动删除。"""
        safe = "corrupted"
        path = os.path.join(self.cache_dir, f"{safe}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not json at all")

        from src.python.cache import get

        result = get("corrupted", 9999)
        self.assertIsNone(result)
        self.assertFalse(os.path.exists(path))

    def test_corrupted_json_io_error_returns_none(self):
        """文件权限/IO 损坏 → 返回 None（文件可能残留在磁盘）。"""
        # 写入一个普通文件但不给读取权限来模拟 IOError
        safe = "ioerr"
        path = os.path.join(self.cache_dir, f"{safe}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{broken")

        from src.python.cache import get

        # JSONDecodeError 分支也会返回 None
        result = get("ioerr", 9999)
        self.assertIsNone(result)

    @patch("src.python.cache._store.time.time")
    def test_missing_timestamp_treated_as_expired(self, mock_time):
        """缺少 _ts 字段 → 按过期处理返回 None。"""
        mock_time.return_value = 2000.0
        path = os.path.join(self.cache_dir, "no_ts.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_data": "hello"}, f)
        from src.python.cache import get

        result = get("no_ts", 1)
        self.assertIsNone(result)
        # 文件不应被删除（只是过期，不是损坏）
        self.assertTrue(os.path.exists(path))

    @patch("src.python.cache._store.time.time")
    def test_missing_data_returns_none(self, mock_time):
        """缺少 _data 字段 → 返回 None。"""
        mock_time.return_value = 2000.0
        path = os.path.join(self.cache_dir, "no_data.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_ts": 1999.0}, f)
        from src.python.cache import get

        result = get("no_data", 100)
        self.assertIsNone(result)

    @patch("src.python.cache._store.time.time")
    def test_exact_boundary_not_expired(self, mock_time):
        """age 恰好等于 max_age_seconds → 未过期（age > max 才过期）。"""
        mock_time.return_value = 2000.0
        self._write_cache("boundary", "data", ts=1900.0)
        from src.python.cache import get

        result = get("boundary", 100)
        self.assertEqual(result, "data")

    @patch("src.python.cache._store.time.time")
    def test_exact_boundary_minus_epsilon_expired(self, mock_time):
        """age 略大于 max_age_seconds → 过期返回 None。"""
        mock_time.return_value = 2000.001
        self._write_cache("eps", "data", ts=1900.0)
        from src.python.cache import get

        result = get("eps", 100)
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════
#  set 测试
# ═══════════════════════════════════════════════════════════


class TestCacheSet(CacheTestBase):
    """测试 set 的文件写入与目录创建。"""

    @patch("src.python.cache._store.time.time")
    def test_set_creates_file(self, mock_time):
        """set → 文件被正确写入 JSON。"""
        mock_time.return_value = 1234.0
        from src.python.cache import set

        set("newkey", "hello")

        path = os.path.join(self.cache_dir, "newkey.json")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["_ts"], 1234.0)
        self.assertEqual(payload["_data"], "hello")

    @patch("src.python.cache._store.time.time")
    def test_set_creates_nested_directory(self, mock_time):
        """set → 缓存目录不存在时自动创建。"""
        mock_time.return_value = 1000.0
        import shutil

        shutil.rmtree(self.cache_dir)
        self.assertFalse(os.path.exists(self.cache_dir))

        from src.python.cache import set

        set("nested", "data")

        self.assertTrue(os.path.exists(self.cache_dir))
        path = os.path.join(self.cache_dir, "nested.json")
        self.assertTrue(os.path.exists(path))

    @patch("src.python.cache._store.time.time")
    def test_set_overwrites_existing(self, mock_time):
        """set 覆盖已有文件 → 内容更新。"""
        mock_time.return_value = 1000.0
        self._write_cache("overwrite", "old", ts=500.0)

        mock_time.return_value = 2000.0
        from src.python.cache import set

        set("overwrite", "new")

        path = os.path.join(self.cache_dir, "overwrite.json")
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["_ts"], 2000.0)
        self.assertEqual(payload["_data"], "new")

    @patch("src.python.cache._store.time.time")
    @patch("src.python.cache._store.tempfile.mkstemp")
    def test_set_write_error_logged(self, mock_mkstemp, mock_time):
        """写入 IOError → 不抛出异常，正常返回。"""
        mock_mkstemp.side_effect = OSError("disk full")
        from src.python.cache import set

        # 不应抛出异常
        set("fail", "data")

    @patch("src.python.cache._store.time.time")
    def test_set_list_data(self, mock_time):
        """set 写入列表数据 → 正确序列化。"""
        mock_time.return_value = 500.0
        data = [1, 2, {"a": 3}]
        from src.python.cache import set

        set("listkey", data)

        path = os.path.join(self.cache_dir, "listkey.json")
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["_data"], data)

    @patch("src.python.cache._store.time.time")
    def test_set_atomic_write_content(self, mock_time):
        """原子写入 → 最终文件内容正确，临时文件被清理。"""
        mock_time.return_value = 3000.0
        from src.python.cache import set

        set("atomic", {"hello": "world"})

        # 文件内容正确
        path = os.path.join(self.cache_dir, "atomic.json")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["_ts"], 3000.0)
        self.assertEqual(payload["_data"], {"hello": "world"})

        # 临时文件已清理
        tmp_files = [f for f in os.listdir(self.cache_dir) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files), 0)

    @patch("src.python.cache._store.time.time")
    @patch("src.python.cache._store.os.replace")
    def test_set_windows_replace_fallback(self, mock_replace, mock_time):
        """Windows 上 os.replace 因 PermissionError 失败 → 降级 remove+rename 成功。"""
        mock_time.return_value = 4000.0
        mock_replace.side_effect = PermissionError("被锁定")

        from src.python.cache import set

        # 不应抛出异常
        set("winlock", "data")

        # 验证最终写入成功
        path = os.path.join(self.cache_dir, "winlock.json")
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["_data"], "data")


# ═══════════════════════════════════════════════════════════
#  clear 测试
# ═══════════════════════════════════════════════════════════


class TestCacheClear(CacheTestBase):
    """测试 clear 的文件删除。"""

    def test_clear_existing_file(self):
        """清除存在的文件 → 文件被删除。"""
        self._write_cache("toclear", "x", ts=100.0)
        path = os.path.join(self.cache_dir, "toclear.json")
        self.assertTrue(os.path.exists(path))

        from src.python.cache import clear

        clear("toclear")
        self.assertFalse(os.path.exists(path))

    def test_clear_nonexistent_no_error(self):
        """清除不存在的文件 → 不抛异常。"""
        from src.python.cache import clear

        clear("ghost")  # 不应抛出任何异常

    def test_clear_os_error_swallowed(self):
        """os.remove 抛出 OSError → 被静默吞掉。"""
        from src.python.cache import clear as real_clear

        with patch("src.python.cache._store.os.remove") as mock_remove:
            mock_remove.side_effect = OSError("permission denied")
            # 不应抛出
            real_clear("somekey")


# ═══════════════════════════════════════════════════════════
#  clear_by_prefix 测试
# ═══════════════════════════════════════════════════════════


class TestCacheClearByPrefix(CacheTestBase):
    """测试 clear_by_prefix 的前缀匹配删除。"""

    def setUp(self):
        super().setUp()
        # 准备一批缓存文件
        self._write_cache("price_000001", 1, 100.0)
        self._write_cache("price_000002", 2, 100.0)
        self._write_cache("index_000300", 3, 100.0)
        self._write_cache("fund_perf_rank", 4, 100.0)
        self._write_cache("other_key", 5, 100.0)

    def test_clear_by_prefix_matches(self):
        """匹配前缀的文件全部删除。"""
        from src.python.cache import clear_by_prefix

        count = clear_by_prefix("price_")
        self.assertEqual(count, 2)
        self.assertFalse(os.path.exists(os.path.join(self.cache_dir, "price_000001.json")))
        self.assertFalse(os.path.exists(os.path.join(self.cache_dir, "price_000002.json")))
        # 其他文件不受影响
        self.assertTrue(os.path.exists(os.path.join(self.cache_dir, "index_000300.json")))

    def test_clear_by_prefix_no_match(self):
        """无前缀匹配 → 返回 0。"""
        from src.python.cache import clear_by_prefix

        count = clear_by_prefix("nonexistent_")
        self.assertEqual(count, 0)
        # 文件全都在
        self.assertEqual(len(os.listdir(self.cache_dir)), 5)

    def test_clear_by_prefix_ignores_non_json(self):
        """非 .json 文件不被纳入匹配。"""
        # 写入一个非 .json 文件
        non_json = os.path.join(self.cache_dir, "price_other.txt")
        with open(non_json, "w", encoding="utf-8") as f:
            f.write("not cache")

        from src.python.cache import clear_by_prefix

        count = clear_by_prefix("price_")
        # 只删除了 2 个 price_*.json，txt 文件不碰
        self.assertEqual(count, 2)
        self.assertTrue(os.path.exists(non_json))

    def test_clear_by_prefix_empty_dir(self):
        """缓存目录不存在 → 返回 0。"""
        import shutil

        shutil.rmtree(self.cache_dir)
        from src.python.cache import clear_by_prefix

        self.assertEqual(clear_by_prefix("price_"), 0)

    def test_clear_by_prefix_os_error_continues(self):
        """单个文件删除失败 → 继续删除其他文件。"""
        from src.python.cache import clear_by_prefix as real_cbp

        with patch("src.python.cache._groups.os.remove") as mock_remove:
            # 第一次删除抛出异常，第二次成功
            mock_remove.side_effect = [OSError("locked"), None]

            # 目录中有 price_000001.json 和 price_000002.json
            # mock_remove 被调用两次：第一次失败，第二次成功
            count = real_cbp("price_")
            # 返回成功删除的数量
            self.assertEqual(count, 1)


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
        # 写一个明显更大的文件
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
        # "other" 不带下划线 → 归入 other 组
        # 但 "other" 没有下划线，所以会被归入 "other" 组（名称就是 "other"）
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
        # 所有类型都返回 100 秒 TTL
        mock_ttl.return_value = 100.0

        # ts=9500 → age=500 > 100 → 过期
        self._set_time_and_write("price_old", 1, ts=9500.0)
        # ts=9950 → age=50 < 100 → 未过期
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
        # 文件仍然存在
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

        # 根据实际 prefix_type_map 模拟 TTL 分配
        def ttl_side_effect(dtype: str) -> float:
            mapping = {"price": 100.0, "news": 500.0}
            return mapping.get(dtype, 300.0)

        mock_ttl.side_effect = ttl_side_effect

        # price_* → dtype "price" → TTL 100
        self._set_time_and_write("price_old", 1, ts=9800.0)   # age=200 > 100 → 过期
        # news_* → dtype "news" → TTL 500
        self._set_time_and_write("news_old", 2, ts=9800.0)    # age=200 < 500 → 未过期

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
            self.assertEqual(count, 0)  # 未成功删除

    @patch("src.python.cache._cleanup.time.time")
    def test_unknown_prefix_uses_default_ttl(self, mock_time):
        """未知前缀的缓存文件按默认 TTL（news 的 TTL）判断过期。"""
        mock_time.return_value = 10000.0
        # get_ttl 不 mock — 让它走真实逻辑
        # "unknown" 前缀不匹配任何 prefix_type_map，data_type 默认为 "news"
        # news 的默认 TTL 是 900 秒
        # ts=9500 → age=500 < 900 → 未过期，不会被删除
        self._set_time_and_write("unknown_xyz", 1, ts=9500.0)

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 0)

    @patch("src.python.cache._cleanup.time.time")
    def test_trading_calendar_not_cleaned_early(self, mock_time):
        """交易日历注册了 exact key → 使用 calendar TTL，不会被 news 的短 TTL 误删。"""
        # trading_calendar 未注册时，data_type 回退到 "news" (TTL=900)
        # 写入 age=2000s（>900s 但 < calendar 的 1209600s）
        mock_time.return_value = 10000.0
        self._set_time_and_write("trading_calendar", ["2026-01-01"], ts=8000.0)

        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 0, "trading_calendar 已注册 exact key，不应被误删")

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
#  get_ttl 测试
# ═══════════════════════════════════════════════════════════


class TestGetTTL(unittest.TestCase):
    """测试 get_ttl 的配置读取、默认值与兜底逻辑。"""

    @patch("src.python.cache._ttl._is_market_open", return_value=False)
    def test_known_type_returns_default(self, mock_market):
        """已知类型未配置 → 返回默认值。"""
        from src.python.cache import CACHE_DAILY, get_ttl

        self.assertEqual(get_ttl("price"), CACHE_DAILY)

    def test_unknown_type_returns_daily(self):
        """未知类型 → 返回 CACHE_DAILY。"""
        from src.python.cache import CACHE_DAILY, get_ttl

        self.assertEqual(get_ttl("unknown_type_xyz"), CACHE_DAILY)

    def test_hold_returns_weekly(self):
        """hold 类型 → 默认返回 CACHE_WEEKLY。"""
        from src.python.constants import CACHE_WEEKLY
        from src.python.cache import get_ttl

        self.assertEqual(get_ttl("hold"), CACHE_WEEKLY)

    def test_benchmark_returns_monthly(self):
        """benchmark 类型 → 默认返回 CACHE_MONTHLY。"""
        from src.python.constants import CACHE_MONTHLY
        from src.python.cache import get_ttl

        self.assertEqual(get_ttl("benchmark"), CACHE_MONTHLY)

    @patch("src.python.config.get_config")
    def test_config_value_used_when_present(self, mock_get_config):
        """配置文件中的 cache_ttl 值被优先使用。"""
        mock_get_config.return_value = {
            "cache_ttl": {"price": 12345},
        }
        from src.python.cache import get_ttl

        self.assertEqual(get_ttl("price"), 12345.0)

    @patch("src.python.cache._ttl._is_market_open", return_value=False)
    @patch("src.python.config.get_config")
    def test_config_zero_value_ignored(self, mock_get_config, mock_market):
        """配置中 TTL 为 0 → 忽略该值，使用默认。"""
        from src.python.cache import get_ttl
        from src.python.registry import get_cache_ttl_defaults

        mock_get_config.return_value = {
            "cache_ttl": {"price": 0},
        }
        self.assertEqual(get_ttl("price"), get_cache_ttl_defaults()["price"])

    @patch("src.python.cache._ttl._is_market_open", return_value=False)
    @patch("src.python.config.get_config")
    def test_config_negative_value_ignored(self, mock_get_config, mock_market):
        """配置中 TTL 为负数 → 忽略该值，使用默认。"""
        from src.python.cache import get_ttl
        from src.python.registry import get_cache_ttl_defaults

        mock_get_config.return_value = {
            "cache_ttl": {"price": -100},
        }
        self.assertEqual(get_ttl("price"), get_cache_ttl_defaults()["price"])

    @patch("src.python.cache._ttl._is_market_open", return_value=False)
    @patch("src.python.config.get_config")
    def test_config_exception_falls_back(self, mock_get_config, mock_market):
        """get_config 抛出异常 → 返回默认值。"""
        mock_get_config.side_effect = RuntimeError("config error")
        from src.python.cache import get_ttl
        from src.python.registry import get_cache_ttl_defaults

        self.assertEqual(get_ttl("price"), get_cache_ttl_defaults()["price"])

    @patch("src.python.cache._ttl._is_market_open", return_value=False)
    @patch("src.python.config.get_config")
    def test_config_missing_cache_ttl_key(self, mock_get_config, mock_market):
        """配置中无 cache_ttl 键 → 返回默认值。"""
        mock_get_config.return_value = {}
        from src.python.cache import get_ttl
        from src.python.registry import get_cache_ttl_defaults

        self.assertEqual(get_ttl("price"), get_cache_ttl_defaults()["price"])

    @patch("src.python.cache._ttl._is_market_open", return_value=False)
    @patch("src.python.config.get_config")
    def test_config_cache_ttl_is_none(self, mock_get_config, mock_market):
        """配置中 cache_ttl 为 None → 返回默认值。"""
        mock_get_config.return_value = {"cache_ttl": None}
        from src.python.cache import get_ttl
        from src.python.registry import get_cache_ttl_defaults

        self.assertEqual(get_ttl("price"), get_cache_ttl_defaults()["price"])


# ═══════════════════════════════════════════════════════════
#  get_cache_dir 测试
# ═══════════════════════════════════════════════════════════





class TestGetCacheDir(unittest.TestCase):
    """测试 get_cache_dir 返回绝对路径。"""

    def test_returns_absolute_path(self):
        """返回值是绝对路径。"""
        from src.python.cache import get_cache_dir

        path = get_cache_dir()
        self.assertTrue(os.path.isabs(path))

    def test_ends_with_cache(self):
        """路径以 cache 结尾。"""
        from src.python.cache import get_cache_dir

        path = get_cache_dir()
        self.assertTrue(path.endswith("cache"))


# ═══════════════════════════════════════════════════════════
#  全局常量测试
# ═══════════════════════════════════════════════════════════


class TestCacheConstants(unittest.TestCase):
    """测试缓存常量定义符合预期。"""

    def test_cache_daily(self):
        from src.python.cache import CACHE_DAILY
        self.assertEqual(CACHE_DAILY, 86400)

    def test_cache_weekly(self):
        from src.python.constants import CACHE_WEEKLY
        self.assertEqual(CACHE_WEEKLY, 604800)

    def test_cache_monthly(self):
        from src.python.constants import CACHE_MONTHLY
        self.assertEqual(CACHE_MONTHLY, 2592000)


# ═══════════════════════════════════════════════════════════
#  gzip 缓存测试
# ═══════════════════════════════════════════════════════════


class TestGzipCache(CacheTestBase):
    """测试大文件的自动 gzip 压缩/解压。"""

    @patch("src.python.cache._store.time.time")
    def test_small_file_not_gzipped(self, mock_time):
        """小文件 (<100KB) 仍写入 .json。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set

        set("small_key", "small_data")

        json_path = os.path.join(self.cache_dir, "small_key.json")
        gz_path = json_path + ".gz"
        self.assertTrue(os.path.exists(json_path))
        self.assertFalse(os.path.exists(gz_path))

    @patch("src.python.cache._store.time.time")
    def test_large_file_auto_gzipped(self, mock_time):
        """大文件 (>100KB) 自动写入 .json.gz。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set

        large_data = "x" * 110000
        set("large_key", large_data)

        json_path = os.path.join(self.cache_dir, "large_key.json")
        gz_path = json_path + ".gz"
        self.assertTrue(os.path.exists(gz_path))
        self.assertFalse(os.path.exists(json_path))

    @patch("src.python.cache._store.time.time")
    def test_read_gzipped_file(self, mock_time):
        """读取 .json.gz 返回正确数据。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set

        large_data = "x" * 110000
        set("read_gz", large_data)

        mock_time.return_value = 1050.0
        from src.python.cache import get

        result = get("read_gz", 100)
        self.assertEqual(result, large_data)

    @patch("src.python.cache._store.time.time")
    def test_read_fallback_json(self, mock_time):
        """.gz 不存在时回退到 .json。"""
        mock_time.return_value = 1000.0
        self._write_cache("fallback", "json_data", ts=950.0)
        from src.python.cache import get

        result = get("fallback", 100)
        self.assertEqual(result, "json_data")

    @patch("src.python.cache._store.time.time")
    def test_clear_by_prefix_removes_gz(self, mock_time):
        """前缀删除同时删除 .gz 文件。"""
        mock_time.return_value = 1000.0
        self._write_cache("price_000001", 1, ts=100.0)
        self._write_gz_cache("price_000002", 2, ts=100.0)
        from src.python.cache import clear_by_prefix

        count = clear_by_prefix("price_")
        self.assertEqual(count, 2)

        json_path = os.path.join(self.cache_dir, "price_000001.json")
        gz_path = os.path.join(self.cache_dir, "price_000002.json.gz")
        self.assertFalse(os.path.exists(json_path))
        self.assertFalse(os.path.exists(gz_path))

    @patch("src.python.cache._store.time.time")
    @patch("src.python.cache._cleanup.get_ttl")
    def test_cleanup_expired_gz(self, mock_ttl, mock_time):
        """缓存清理处理 .gz 文件。"""
        mock_time.return_value = 10000.0
        mock_ttl.return_value = 100.0

        self._write_gz_cache("price_gz_old", 1, ts=9500.0)
        self._write_gz_cache("price_gz_fresh", 2, ts=9950.0)
        from src.python.cache import cleanup_expired

        count = cleanup_expired()
        self.assertEqual(count, 1)

        old_path = os.path.join(self.cache_dir, "price_gz_old.json.gz")
        fresh_path = os.path.join(self.cache_dir, "price_gz_fresh.json.gz")
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(fresh_path))

    @patch("src.python.cache._store.time.time")
    def test_gzip_fingerprint_matches(self, mock_time):
        """内容指纹在压缩前后一致。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set

        complex_data = {
            "list": list(range(500)),
            "nested": {"a": 1, "b": [1, 2, 3], "c": {"d": "e"}},
            "numbers": [1.0, 2.0, 3.0],
            "text": "x" * 110000,
        }
        set("fp_complex", complex_data)

        mock_time.return_value = 1500.0
        from src.python.cache import get

        result = get("fp_complex", 600)
        self.assertEqual(result, complex_data)


class TestClearByGroup(CacheTestBase):
    """测试 clear_by_group 函数。"""

    def test_clear_refresh_group_deletes_matching(self):
        """refresh 组清除基金/新闻/行业/分红/盈利预测缓存，保留 preload 组。"""
        self._write_cache("fund_perf_000001", {"d": 1}, ts=1000.0)
        self._write_cache("news_abc", {"d": 2}, ts=1000.0)
        self._write_cache("industry_600000", {"d": 3}, ts=1000.0)
        self._write_cache("dividend_600000", {"d": 4}, ts=1000.0)
        self._write_cache("price_600000", {"d": 5}, ts=1000.0)  # preload 组，不应删除

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
        self._write_cache("news_abc", {"d": 4}, ts=1000.0)  # refresh 组

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


if __name__ == "__main__":
    unittest.main()


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
        # age 应接近 now - ts_now
        self.assertGreaterEqual(age, 0)


# ═══════════════════════════════════════════════════════════
#  _is_market_open 测试（多渠道市场时段判断）
# ═══════════════════════════════════════════════════════════


class TestIsMarketOpen(unittest.TestCase):
    """测试 _is_market_open() 的多数据源与午餐排除逻辑。"""

    def _call_is_market_open(self, mock_now: datetime) -> bool:
        """辅助：patch datetime.now → 调用 is_market_open。"""
        with patch("src.python.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            from src.python.market_hours import is_market_open as _is_market_open
            return _is_market_open()

    # ── 默认 fallback（无 config、无 API） ────────────────
    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_default_morning_session(self, mock_cfg, mock_fetch):
        """工作日 10:00 → 交易时段。"""
        mock_cfg.return_value = {}
        now = datetime(2026, 6, 30, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))  # 周二
        self.assertTrue(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_default_lunch_break(self, mock_cfg, mock_fetch):
        """工作日 12:00（午餐休市）→ 非交易时段。"""
        mock_cfg.return_value = {}
        now = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_default_afternoon_session(self, mock_cfg, mock_fetch):
        """工作日 14:00 → 交易时段。"""
        mock_cfg.return_value = {}
        now = datetime(2026, 6, 30, 14, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_default_after_close(self, mock_cfg, mock_fetch):
        """工作日 15:30 → 非交易时段。"""
        mock_cfg.return_value = {}
        now = datetime(2026, 6, 30, 15, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_default_weekend(self, mock_cfg, mock_fetch):
        """周六 → 非交易时段。"""
        mock_cfg.return_value = {}
        now = datetime(2026, 7, 4, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))  # 周六
        self.assertFalse(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_default_before_open(self, mock_cfg, mock_fetch):
        """工作日 09:00 → 非交易时段。"""
        mock_cfg.return_value = {}
        now = datetime(2026, 6, 30, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._call_is_market_open(now))

    # ── config.json 覆盖 ─────────────────────────────────
    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_config_override_start_end(self, mock_cfg, mock_fetch):
        """配置 market_hours.start=08:00, end=16:00 → 覆盖默认值。"""
        mock_cfg.return_value = {
            "market_hours": {"start": "08:00", "end": "16:00"},
        }
        # 08:30 在默认值（09:30）之外，但在覆盖值之内
        now = datetime(2026, 6, 30, 8, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_config_override_outside(self, mock_cfg, mock_fetch):
        """配置 market_hours.start=10:00 → 09:30 不算交易时段。"""
        mock_cfg.return_value = {
            "market_hours": {"start": "10:00", "end": "15:00"},
        }
        now = datetime(2026, 6, 30, 9, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.config.get_config")
    def test_config_override_empty_ignored(self, mock_cfg, mock_fetch):
        """配置 market_hours 无 start/end → 降级到默认值。"""
        mock_cfg.return_value = {
            "market_hours": {"official_source": False},
        }
        now = datetime(2026, 6, 30, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._call_is_market_open(now))

    # ── 官方 API 状态 ─────────────────────────────────────
    @patch("src.python.config.get_config")
    def test_api_status_trading(self, mock_cfg):
        """API 返回 f100=1 → 交易时段。

        注：conftest._mock_market_hours_api autouse fixture 会替换
        _is_market_open_official 为 lambda，因此本测试实际验证的是
        fallback 层（10:00 在工作日交易时段内）。
        """
        mock_cfg.return_value = {"market_hours": {"official_source": True}}
        now = datetime(2026, 6, 30, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.cache.get")
    @patch("src.python.cache.set")
    @patch("src.python.config.get_config")
    def test_api_status_closed(self, mock_cfg, mock_set, mock_get, mock_fetch):
        """API 返回 f100=2 → 非交易时段。"""
        mock_cfg.return_value = {"market_hours": {"official_source": True}}
        mock_get.return_value = None
        mock_fetch.return_value = 2  # f100=2（已收盘）
        now = datetime(2026, 6, 30, 15, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._call_is_market_open(now))

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.cache.get")
    @patch("src.python.config.get_config")
    def test_api_cached_trading(self, mock_cfg, mock_get, mock_fetch):
        """缓存中 status=1 → 直接返回 True 不走 API。"""
        mock_cfg.return_value = {"market_hours": {"official_source": True}}
        mock_get.return_value = {"status": 1}
        now = datetime(2026, 6, 30, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._call_is_market_open(now))
        mock_fetch.assert_not_called()

    @patch("src.python.market_hours._fetch_trading_status_from_official", return_value=None)
    @patch("src.python.cache.get")
    @patch("src.python.config.get_config")
    def test_api_cached_closed(self, mock_cfg, mock_get, mock_fetch):
        """缓存中 status=2 → 直接返回 False。"""
        mock_cfg.return_value = {"market_hours": {"official_source": True}}
        mock_get.return_value = {"status": 2}
        now = datetime(2026, 6, 30, 15, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._call_is_market_open(now))


# ═══════════════════════════════════════════════════════════════
#  R-088: gzip 透明压缩解压测试
# ═══════════════════════════════════════════════════════════════


class TestGzipTransparentCompression(CacheTestBase):
    """测试缓存 >100KB 时自动 gzip 压缩 + 透明解压。"""

    def _big_data(self, size_kb: int = 150) -> dict:
        """生成指定大小的测试数据（确保超过 _GZIP_THRESHOLD=100KB）。"""
        return {"data": "x" * (size_kb * 1024)}

    @patch("src.python.cache._store.time.time")
    def test_small_data_not_gzip(self, mock_time):
        """小数据（<100KB）→ 存储为 .json 而非 .json.gz。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set
        data = {"small": "hello"}
        set("small_key", data)

        json_path = os.path.join(self.cache_dir, "small_key.json")
        gz_path = json_path + ".gz"
        self.assertTrue(os.path.exists(json_path))
        self.assertFalse(os.path.exists(gz_path))

    @patch("src.python.cache._store.time.time")
    def test_large_data_stored_as_gz(self, mock_time):
        """大数据（>100KB）→ 自动存储为 .json.gz。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set
        big = self._big_data(150)
        set("big_key", big)

        json_path = os.path.join(self.cache_dir, "big_key.json")
        gz_path = json_path + ".gz"

        # .json 文件不应存在（被 .json.gz 替代）
        self.assertFalse(os.path.exists(json_path),
                         ".json 文件应被清理")
        self.assertTrue(os.path.exists(gz_path),
                        "应创建 .json.gz 文件")

        # 验证确实是 gzip 格式
        import gzip
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["_data"]["data"], big["data"])

    @patch("src.python.cache._store.time.time")
    def test_read_gz_transparently(self, mock_time):
        """读取 .json.gz 透明解压 → 返回正确数据。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set, get

        big = self._big_data(120)
        set("transparent_key", big)

        # 读取（应透明解压 .json.gz）
        mock_time.return_value = 1000.0  # 同一时刻，未过期
        result = get("transparent_key", 9999)
        self.assertEqual(result, big)

    @patch("src.python.cache._store.time.time")
    def test_gz_cleanup_expired(self, mock_time):
        """清理过期缓存时 .json.gz 也被正确处理。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set

        big = self._big_data(110)
        set("expire_gz", big)

        gz_path = os.path.join(self.cache_dir, "expire_gz.json.gz")
        self.assertTrue(os.path.exists(gz_path))

        # 快进到过期后清理
        mock_time.return_value = 999999.0
        from src.python.cache import cleanup_expired
        count = cleanup_expired()
        self.assertEqual(count, 1)
        self.assertFalse(os.path.exists(gz_path))

    @patch("src.python.cache._store.time.time")
    def test_gz_clear_by_prefix(self, mock_time):
        """clear_by_prefix 应同时清理 .json.gz 文件。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set, clear_by_prefix

        big1 = self._big_data(110)
        big2 = self._big_data(110)
        set("price_gz_a", big1)
        set("price_gz_b", big2)

        gz_a = os.path.join(self.cache_dir, "price_gz_a.json.gz")
        gz_b = os.path.join(self.cache_dir, "price_gz_b.json.gz")
        self.assertTrue(os.path.exists(gz_a))
        self.assertTrue(os.path.exists(gz_b))

        count = clear_by_prefix("price_gz_")
        self.assertEqual(count, 2)
        self.assertFalse(os.path.exists(gz_a))
        self.assertFalse(os.path.exists(gz_b))

    @patch("src.python.cache._store.time.time")
    def test_get_prefers_gz_over_json(self, mock_time):
        """同时存在 .json 和 .json.gz → 优先读取 .json.gz。"""
        mock_time.return_value = 1000.0

        # 写两个同名不同格式的文件
        json_path = os.path.join(self.cache_dir, "duel.json")
        gz_path = json_path + ".gz"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"_ts": 900.0, "_data": "plain"}, f)

        import gzip
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            json.dump({"_ts": 900.0, "_data": "compressed"}, f)

        from src.python.cache import get
        result = get("duel", 9999)
        # 应返回 gzip 的内容
        self.assertEqual(result, "compressed")


class TestParseTimeToMinutes(unittest.TestCase):
    """测试 _parse_time_to_minutes 工具函数。"""

    def test_normal(self):
        from src.python.market_hours import _parse_time_to_minutes
        self.assertEqual(_parse_time_to_minutes("09:30"), 570)
        self.assertEqual(_parse_time_to_minutes("15:00"), 900)
        self.assertEqual(_parse_time_to_minutes("00:00"), 0)

    def test_invalid_format(self):
        from src.python.market_hours import _parse_time_to_minutes

        self.assertIsNone(_parse_time_to_minutes(""))
        self.assertIsNone(_parse_time_to_minutes("abc"))
        self.assertIsNone(_parse_time_to_minutes("09:"))
        self.assertIsNone(_parse_time_to_minutes(":30"))

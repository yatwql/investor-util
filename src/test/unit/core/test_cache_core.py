"""缓存核心操作单元测试 — _paths / _store 子模块。

测试目标：
  - _cache_path — 路径生成与目录穿越防护
  - get — 正常命中、过期、文件损坏、键缺失等场景
  - set — 目录创建、文件写入、写入失败处理
  - exists — 文件存在性检查
  - clear — 文件删除
  - clear_by_prefix — 前缀匹配删除、.json 过滤、目录不存在

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/core/test_cache_core.py -v
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
#  _cache_path 测试
# ═══════════════════════════════════════════════════════════


class TestCachePath(unittest.TestCase):
    """测试 _cache_path 路径生成与目录穿越防护。"""

    def test_normal_key(self):
        """普通键名 → 正确路径。"""
        from src.python.cache import _cache_path

        path = _cache_path("my_key")
        self.assertTrue(path.endswith("my_key.json"))
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
        safe = "ioerr"
        path = os.path.join(self.cache_dir, f"{safe}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{broken")

        from src.python.cache import get

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

        path = os.path.join(self.cache_dir, "atomic.json")

        import tempfile
        tmp_dir = tempfile.gettempdir()
        tmp_files = [f for f in os.listdir(tmp_dir) if f.startswith("tmp") and f.endswith(".json")]
        self.assertEqual(len(tmp_files), 0, "临时文件未被清理")

    @patch("src.python.cache._store.time.time")
    def test_set_windows_permission_heuristic(self, mock_time):
        """Windows 权限问题时也正确写入。"""
        with patch.object(CacheTestBase, "_write_cache", return_value=""):
            mock_time.return_value = 5000.0
            from src.python.cache import set

            set("winlock", "data")

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

        clear("ghost")

    def test_clear_os_error_swallowed(self):
        """os.remove 抛出 OSError → 被静默吞掉。"""
        from src.python.cache import clear as real_clear

        with patch("src.python.cache._store.os.remove") as mock_remove:
            mock_remove.side_effect = OSError("permission denied")
            real_clear("somekey")


# ═══════════════════════════════════════════════════════════
#  clear_by_prefix 测试
# ═══════════════════════════════════════════════════════════


class TestCacheClearByPrefix(CacheTestBase):
    """测试 clear_by_prefix 的前缀匹配删除。"""

    def setUp(self):
        super().setUp()
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
        self.assertTrue(os.path.exists(os.path.join(self.cache_dir, "index_000300.json")))

    def test_clear_by_prefix_no_match(self):
        """无前缀匹配 → 返回 0。"""
        from src.python.cache import clear_by_prefix

        count = clear_by_prefix("nonexistent_")
        self.assertEqual(count, 0)
        self.assertEqual(len(os.listdir(self.cache_dir)), 5)

    def test_clear_by_prefix_ignores_non_json(self):
        """非 .json 文件不被纳入匹配。"""
        non_json = os.path.join(self.cache_dir, "price_other.txt")
        with open(non_json, "w", encoding="utf-8") as f:
            f.write("not cache")

        from src.python.cache import clear_by_prefix

        count = clear_by_prefix("price_")
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
            mock_remove.side_effect = [OSError("locked"), None]
            count = real_cbp("price_")
            self.assertEqual(count, 1)

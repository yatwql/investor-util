"""缓存格式单元测试 — gzip 压缩/透明解压。

测试目标：
  - 小文件 (<100KB) 存储为 .json
  - 大文件 (>100KB) 自动 gzip 压缩为 .json.gz
  - 透明解压读取 .json.gz
  - gzip 与清理/前缀删除的交互

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/core/test_cache_format.py -v
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


# ═══════════════════════════════════════════════════════════════
#  gzip 透明压缩解压测试
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

        self.assertFalse(os.path.exists(json_path), ".json 文件应被清理")
        self.assertTrue(os.path.exists(gz_path), "应创建 .json.gz 文件")

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

        mock_time.return_value = 1000.0
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

        json_path = os.path.join(self.cache_dir, "duel.json")
        gz_path = json_path + ".gz"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"_ts": 900.0, "_data": "plain"}, f)

        import gzip

        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            json.dump({"_ts": 900.0, "_data": "compressed"}, f)

        from src.python.cache import get

        result = get("duel", 9999)
        self.assertEqual(result, "compressed")

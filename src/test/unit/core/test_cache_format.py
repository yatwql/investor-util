"""缓存格式单元测试 — gzip 压缩/透明解压。

覆盖面：
  - 阈值两侧（<100KB 存 .json / >100KB 存 .json.gz）与 gz 内铭文解析；
  - 透明解压读取、.json 兜底回退、.gz 优先；
  - 清理与按前缀删除对 .gz 文件的处理；
  - 压缩前后内容指纹一致性。
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


# ═══════════════════════════════════════════════════════════════
#  基类：统一的临时目录 + 补丁
# ═══════════════════════════════════════════════════════════════


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
        self.addCleanup(self._patcher_paths.stop)
        self.addCleanup(self._patcher_stats.stop)
        self.addCleanup(self._patcher_cleanup.stop)
        self.addCleanup(self._patcher_groups.stop)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_cache(self, key, data, ts=1000.0):
        """向缓存目录写入指定内容的 JSON 文件，返回完整路径。"""
        from src.python.cache import _cache_path

        path = _cache_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_ts": ts, "_data": data}, f, ensure_ascii=False)
        return path


# ═══════════════════════════════════════════════════════════════
#  gzip 压缩/透明解压与生命周期处理
# ═══════════════════════════════════════════════════════════════


class TestGzipTransparentCompression(CacheTestBase):
    """测试缓存 >100KB 时自动 gzip 压缩 + 透明解压。"""

    def _big_data(self, size_kb: int = 150) -> dict:
        """生成指定大小的测试数据（确保超过 gzip 阈值）。"""
        return {"data": "x" * (size_kb * 1024)}

    @patch("src.python.cache._store.time.time")
    def test_small_data_not_gzip(self, mock_time):
        """小数据（<100KB）→ 存储为 .json 而非 .json.gz。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set, _cache_path

        data = {"small": "hello"}
        set("small_key", data)

        json_path = _cache_path("small_key")
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

        from src.python.cache import _cache_path

        json_path = _cache_path("big_key")
        gz_path = json_path + ".gz"

        self.assertFalse(os.path.exists(json_path), ".json 文件应被清理")
        self.assertTrue(os.path.exists(gz_path), "应创建 .json.gz 文件")

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

        from src.python.cache import _cache_path

        gz_path = _cache_path("expire_gz") + ".gz"
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

        from src.python.cache import _cache_path

        gz_a = _cache_path("price_gz_a") + ".gz"
        gz_b = _cache_path("price_gz_b") + ".gz"
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
        from src.python.cache import _cache_path, get

        json_path = _cache_path("duel")
        gz_path = json_path + ".gz"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"_ts": 900.0, "_data": "plain"}, f)

        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            json.dump({"_ts": 900.0, "_data": "compressed"}, f)

        result = get("duel", 9999)
        self.assertEqual(result, "compressed")


# ═══════════════════════════════════════════════════════════════
#  缓存读取兜底与内容指纹一致性
# ═══════════════════════════════════════════════════════════════


class TestCacheFallbackAndFingerprint(CacheTestBase):
    """.json 兜底路径与压缩对内容指纹的透明性。"""

    @patch("src.python.cache._store.time.time")
    def test_read_fallback_json(self, mock_time):
        """.gz 不存在时回退到 .json。"""
        mock_time.return_value = 1000.0
        self._write_cache("fallback", "json_data", ts=950.0)
        from src.python.cache import get

        result = get("fallback", 100)
        self.assertEqual(result, "json_data")

    @patch("src.python.cache._store.time.time")
    def test_gzip_fingerprint_matches(self, mock_time):
        """内容指纹在压缩前后一致（含嵌套结构与高精度浮点）。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set, get

        complex_data = {
            "list": list(range(500)),
            "nested": {"a": 1, "b": [1, 2, 3], "c": {"d": "e"}},
            "numbers": [1.0, 2.0, 3.0],
            "text": "x" * 110000,
        }
        set("fp_complex", complex_data)

        mock_time.return_value = 1500.0
        result = get("fp_complex", 600)
        self.assertEqual(result, complex_data)


if __name__ == "__main__":
    unittest.main()

"""缓存文件 IO（序列化/反序列化/原子写入）单元测试。"""

from __future__ import annotations

import gzip
import json
import os
import tempfile

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestCacheIo:
    """缓存文件 IO 测试。"""

    def test_read_cache_data_not_exists(self):
        """文件不存在 → 返回 None。"""
        from src.python.cache._io import _read_cache_data

        result = _read_cache_data("/tmp/nonexistent_cache_file.json", "test_key")
        assert result is None

    def test_read_cache_data_corrupt_then_delete(self, tmp_path):
        """文件损坏 → 自动删除并返回 None。"""
        from src.python.cache._io import _read_cache_data

        corrupt_file = os.path.join(tmp_path, "corrupt.json")
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write("这不是 JSON{")
        result = _read_cache_data(corrupt_file, "corrupt_key")
        assert result is None
        assert not os.path.exists(corrupt_file)

    def test_read_cache_data_dry_keep_corrupt(self, tmp_path):
        """dry_run=True → 不删除损坏文件。"""
        from src.python.cache._io import _read_cache_data

        corrupt_file = os.path.join(tmp_path, "corrupt_dry.json")
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write("{invalid json")
        result = _read_cache_data(corrupt_file, "corrupt_dry", dry_run=True)
        assert result is None
        assert os.path.exists(corrupt_file)

    def test_write_atomic_json(self, tmp_path):
        """写入纯 JSON → 文件内容正确。"""
        from src.python.cache._io import _write_atomic

        final_path = os.path.join(tmp_path, "test.json")
        fd, tmp_file = tempfile.mkstemp(dir=tmp_path, suffix=".json.tmp")
        data = {"key": "value", "num": 42}
        json_str = json.dumps(data, ensure_ascii=False)
        raw_bytes = json_str.encode("utf-8")

        _write_atomic(fd, tmp_file, final_path, final_path, json_str, raw_bytes, use_gzip=False)

        assert os.path.exists(final_path)
        with open(final_path, encoding="utf-8") as f:
            assert json.load(f) == data

    def test_write_atomic_gzip(self, tmp_path):
        """写入 gzip 压缩 JSON → 可正常解压读取。"""
        from src.python.cache._io import _write_atomic

        final_path = os.path.join(tmp_path, "test.json.gz")
        fd, tmp_file = tempfile.mkstemp(dir=tmp_path, suffix=".json.gz.tmp")
        data = {"key": "gzip_test"}
        json_str = json.dumps(data, ensure_ascii=False)
        raw_bytes = json_str.encode("utf-8")

        # path 参数是原始缓存路径（用于清理另一格式文件），不应等于 final_path
        plain_path = os.path.join(tmp_path, "test.json")
        _write_atomic(fd, tmp_file, final_path, plain_path, json_str, raw_bytes, use_gzip=True)

        assert os.path.exists(final_path)
        with open(final_path, "rb") as f:
            decompressed = gzip.decompress(f.read()).decode("utf-8")
            assert json.loads(decompressed) == data

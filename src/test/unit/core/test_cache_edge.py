"""缓存 edge 场景专项测试。

edge 场景：
  - TestGetTTLMarketHourAware: 市场交易时段感知的 TTL 计算
  - TestGzipCacheEdge: gzip 压缩边界（100KB 阈值）+ 损坏文件恢复

运行：
  pytest src/test/unit/core/test_cache_edge.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


# ── 测试基类 ─────────────────────────────────


class _CacheTestBase:
    """测试辅助方法。"""

    def setUp(self):
        self.cache_dir = tempfile.TemporaryDirectory()
        self._p_paths = patch("src.python.cache._paths._CACHE_DIR", self.cache_dir.name)
        self._p_cleanup = patch("src.python.cache._cleanup._CACHE_DIR", self.cache_dir.name)
        self._p_groups = patch("src.python.cache._groups._CACHE_DIR", self.cache_dir.name)
        self._p_paths.start()
        self._p_cleanup.start()
        self._p_groups.start()

    def tearDown(self):
        if hasattr(self, "_p_groups"):
            self._p_groups.stop()
        if hasattr(self, "_p_cleanup"):
            self._p_cleanup.stop()
        self._p_paths.stop()
        self.cache_dir.cleanup()

    def _write_cache(self, key, data, ts=None):
        """写入一个 .json 缓存文件（可选带时间戳）。"""
        from src.python.cache import _cache_path

        path = _cache_path(key)
        payload = {"data": data}
        if ts is not None:
            payload["timestamp"] = ts
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def _write_gz_cache(self, key, data, ts=None):
        """写入一个 .json.gz 缓存文件（可选带时间戳）。"""
        import gzip

        from src.python.cache import _cache_path

        path = _cache_path(key) + ".gz"
        payload = {"data": data}
        if ts is not None:
            payload["timestamp"] = ts
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(payload, f)


# ── 交易时段 TTL 边界 ──────────────────────────────────────────────


@pytest.mark.edge
class TestGetTTLMarketHourAware(unittest.TestCase, _CacheTestBase):
    """get_ttl 在收盘/午休等特殊时段的行为。"""

    def setUp(self):
        _CacheTestBase.setUp(self)

    def tearDown(self):
        _CacheTestBase.tearDown(self)

    def test_market_open_uses_short_ttl(self):
        """交易时段 + market_hour_aware 声明过 → 用短的刷新间隔 TTL。"""
        with (
            patch("src.python.cache._ttl._is_market_open", return_value=True),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {"market_hour_aware": ["price"], "market_hour_ttl": 120}
            from src.python.cache import get_ttl

            self.assertEqual(get_ttl("price"), 120)

    def test_market_open_clamps_min_30(self):
        """刷新 TTL 最小值限制为 30 秒。"""
        with (
            patch("src.python.cache._ttl._is_market_open", return_value=True),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
                "market_hour_ttl": 5,
            }
            from src.python.cache import get_ttl

            result = get_ttl("price")
            self.assertGreaterEqual(result, 30)

    def test_market_open_clamps_max_86400(self):
        """刷新 TTL 最大值限制为 86400 秒。"""
        with (
            patch("src.python.cache._ttl._is_market_open", return_value=True),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
                "market_hour_ttl": 999999,
            }
            from src.python.cache import get_ttl

            result = get_ttl("price")
            self.assertLessEqual(result, 86400)

    def test_non_aware_type_uses_static(self):
        """未声明为市场感知的类型 → 即使开盘也用静态 TTL（短 TTL 不生效）。"""
        with (
            patch("src.python.cache._ttl._is_market_open", return_value=True),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
                "market_hour_ttl": 120,
                "cache_ttl": {"news": 900},
            }
            from src.python.cache import get_ttl

            self.assertEqual(get_ttl("news"), 900)

    def test_market_closed_uses_static_ttl(self):
        """非交易时段 → 即使属感知类型也用静态 cache_ttl。"""
        with (
            patch("src.python.cache._ttl._is_market_open", return_value=False),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
                "market_hour_ttl": 120,
                "cache_ttl": {"price": 43200},
            }
            from src.python.cache import get_ttl

            self.assertEqual(get_ttl("price"), 43200)

    def test_market_closed_no_config_uses_default(self):
        """非交易时段且无 cache_ttl 配置 → 回退注册表内置默认 TTL。"""
        from src.python.core.registry import get_cache_ttl_defaults

        with (
            patch("src.python.cache._ttl._is_market_open", return_value=False),
            patch("src.python.config.get_config", return_value={}),
        ):
            from src.python.cache import get_ttl

            self.assertEqual(get_ttl("price"), float(get_cache_ttl_defaults()["price"]))

    def test_market_hour_ttl_missing_fallback_to_30(self):
        """market_hour_ttl 配置缺失 → 默认 30 秒。"""
        with (
            patch("src.python.cache._ttl._is_market_open", return_value=True),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
            }
            from src.python.cache import get_ttl

            result = get_ttl("price")
            self.assertEqual(result, 30)

    def test_invalid_market_hour_ttl_fallback_to_30(self):
        """market_hour_ttl 配置值非法 → 使用 30 秒默认值。"""
        with (
            patch("src.python.cache._ttl._is_market_open", return_value=True),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
                "market_hour_ttl": "not_a_number",
            }
            from src.python.cache import get_ttl

            result = get_ttl("price")
            self.assertEqual(result, 30)

    def test_closed_hours_use_static_ttl(self):
        """非交易时段（午间休市 / 下午收盘后）→ 均走静态 TTL 分支。

        两种情况在 `get_ttl` 里由同一分支决定（只看 `_is_market_open`），
        故用一条用例覆盖，不拆成两条同义用例。
        """
        with (
            patch("src.python.cache._ttl._is_market_open", return_value=False),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
                "market_hour_ttl": 120,
                "cache_ttl": {"price": 86400},
            }
            from src.python.cache import get_ttl

            with self.subTest(scenario="午间休市"):
                self.assertEqual(get_ttl("price"), 86400)
            with self.subTest(scenario="下午收盘后"):
                self.assertEqual(get_ttl("price"), 86400)


# ── Gzip 边界场景 ──────────────────────────────────────────────────


class TestGzipCacheEdge(unittest.TestCase, _CacheTestBase):
    """gzip 压缩边界与损坏恢复。"""

    def setUp(self):
        _CacheTestBase.setUp(self)

    def tearDown(self):
        _CacheTestBase.tearDown(self)

    @patch("src.python.cache._store.time.time")
    def test_exact_100kb_boundary_not_gzip(self, mock_time):
        """恰 100KB（未超阈值）→ 不 gzip。"""
        mock_time.return_value = 1000.0
        from src.python.cache import set

        # 恰好 100*1024 字节（阈值是 > 不是 >=）
        boundary_data = "x" * (100 * 1024 - 50)  # 留余量给 JSON 序列化开销
        set("boundary_key", boundary_data)

        from src.python.cache import _cache_path

        json_path = _cache_path("boundary_key")
        gz_path = json_path + ".gz"
        self.assertTrue(os.path.exists(json_path), "≤100KB 数据应仍为 .json")
        self.assertFalse(os.path.exists(gz_path))

    @patch("src.python.cache._store.time.time")
    def test_gz_corrupted_file_deleted_on_read(self, mock_time):
        """损坏的 .json.gz → 删除并返回 None。"""
        mock_time.return_value = 1000.0
        # 创建一个损坏的 .json.gz 文件
        from src.python.cache import _cache_path

        gz_path = _cache_path("corrupted_gz") + ".gz"
        with open(gz_path, "wb") as f:
            f.write(b"this is not valid gzip data")

        from src.python.cache import get

        result = get("corrupted_gz", 3600)

        self.assertIsNone(result)
        # 损坏文件应被删除
        self.assertFalse(os.path.exists(gz_path))


# ── BOM 缓存文件 ──────────────────────────────────────────────


@pytest.mark.edge
class TestBomCacheFile(unittest.TestCase):
    """UTF-8 BOM 头的缓存文件可读性测试。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_bom_cache_file_readable(self):
        """含 UTF-8 BOM 头的 .json 缓存文件 → _read_cache_data() 正常解析。"""
        from src.python.cache import _read_cache_data

        # 用 utf-8-sig 写入产生 BOM
        fpath = os.path.join(self.tmp.name, "bom_test.json")
        payload = '{"_ts": 1000.0, "_data": {"price": 10.5}}'
        with open(fpath, "w", encoding="utf-8-sig") as f:
            f.write(payload)

        result = _read_cache_data(fpath, "bom_test")
        self.assertIsNotNone(result)
        self.assertEqual(result["_data"]["price"], 10.5)


if __name__ == "__main__":
    unittest.main()

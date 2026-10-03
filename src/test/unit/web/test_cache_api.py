"""Web 缓存管理接口测试（GET /api/cache + POST /api/cache/cleanup）。

覆盖：统计面结构与排序（只读，dry_run 扫描）、前缀降序透传、命中率子面、
清理计数透传（cleanup_expired 以 dry_run=False 调用）、同源校验拒绝。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.python.config import _config_defaults
from src.python.config._core import invalidate_config_cache
from src.python.web.app import create_app
from src.python.web.runs import RunManager

pytestmark = [pytest.mark.unit, pytest.mark.unit_web, pytest.mark.usefixtures("offline_external_sources")]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
    invalidate_config_cache()
    app = create_app(RunManager(executor=lambda state, params: 0))
    app.config["TESTING"] = True
    return app.test_client()


class TestCacheStats:
    """GET /api/cache：统计结构（真实只读扫描）+ 打点透传（mock）。"""

    def test_stats_shape(self, app_client):
        resp = app_client.get("/api/cache")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        # 响应契约：字段集合固定（新增字段须同步前端与本断言）
        assert set(data.keys()) == {
            "total_files",
            "total_size_bytes",
            "by_prefix",
            "top_by_size",
            "hit_rate",
            "expired_count",
        }
        assert isinstance(data["total_files"], int)
        assert isinstance(data["total_size_bytes"], int)
        assert isinstance(data["by_prefix"], list)
        assert isinstance(data["top_by_size"], list)
        assert isinstance(data["expired_count"], int)
        assert data["total_files"] >= 0
        assert data["expired_count"] >= 0
        hit = data["hit_rate"]
        assert set(hit.keys()) == {"hits", "misses", "total", "rate"}

    def test_stats_pass_through_sorted_desc(self, app_client, monkeypatch):
        """前缀按文件数降序；打点原样透传（结构关系断言，不写死条数）。"""
        monkeypatch.setattr(
            "src.python.cache.get_cache_stats",
            lambda: {
                "total_files": 5,
                "total_size_bytes": 1234,
                "by_prefix": {"fund_": 2, "quote_": 3},
                "top_by_size": [("a", 1)] * 7,
            },
        )
        monkeypatch.setattr(
            "src.python.cache.get_cache_hit_rate",
            lambda: {"hits": 8, "misses": 2, "total": 10, "rate": 0.8},
        )
        monkeypatch.setattr("src.python.cache.cleanup_expired", lambda dry_run=False: 4)
        resp = app_client.get("/api/cache")
        data = resp.get_json()["data"]
        assert [p[0] for p in data["by_prefix"]] == ["quote_", "fund_"]  # 数组保序降序
        assert [p[1] for p in data["by_prefix"]] == [3, 2]
        assert data["hit_rate"]["rate"] == 0.8
        assert data["expired_count"] == 4
        assert len(data["top_by_size"]) <= 5  # 前端只展示前几大，防卡片过长

    def test_stats_dry_run_cleanup_not_deleting(self, app_client, monkeypatch):
        """统计面的过期数必须以 dry_run=True 取（GET 是只读接口）。"""
        cleanup_mock = MagicMock(return_value=0)
        monkeypatch.setattr("src.python.cache.cleanup_expired", cleanup_mock)
        resp = app_client.get("/api/cache")
        assert resp.status_code == 200
        cleanup_mock.assert_called_once_with(dry_run=True)


class TestCacheCleanup:
    """POST /api/cache/cleanup：同源守卫 + dry_run=False 清理 + 计数透传。"""

    def test_cleanup_pass_through(self, app_client, monkeypatch):
        cleanup_mock = MagicMock(return_value=3)
        monkeypatch.setattr("src.python.cache.cleanup_expired", cleanup_mock)
        resp = app_client.post("/api/cache/cleanup")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["removed"] == 3
        cleanup_mock.assert_called_once_with(dry_run=False)

    def test_cleanup_zero_removed_ok(self, app_client, monkeypatch):
        monkeypatch.setattr("src.python.cache.cleanup_expired", MagicMock(return_value=0))
        resp = app_client.post("/api/cache/cleanup")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["removed"] == 0

    def test_cleanup_cross_origin_403(self, app_client, monkeypatch):
        cleanup_mock = MagicMock(return_value=0)
        monkeypatch.setattr("src.python.cache.cleanup_expired", cleanup_mock)
        resp = app_client.post(
            "/api/cache/cleanup",
            headers={"Origin": "http://evil.example"},
        )
        assert resp.status_code == 403
        assert resp.get_json()["error_code"] == "BAD_PARAM"
        cleanup_mock.assert_not_called()

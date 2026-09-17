"""Web `/api/health` 凭据跳过态透传测试（常规开关 `datasource_credential_ready`，默认开启）。

`/api/health` 直接透传 `run_health_checks` 的结构，故凭据跳过项新增的
``skipped`` 标记须原样到达前端（凭据页/健康页据此区分「源故障」与「未配置」）。

运行：
  pytest src/test/unit/web/test_health_credential.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.config import _config_defaults
from src.python.config._core import invalidate_config_cache
from src.python.web.app import create_app
from src.python.web.handlers import _health_cache
from src.python.web.runs import RunManager

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """最小 Flask test_client：输出目录隔离到 tmp_path，执行器为空实现。"""
    monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
    invalidate_config_cache()
    app = create_app(RunManager(executor=lambda state, params: 0))
    app.config["TESTING"] = True
    return app.test_client()


class TestHealthCredentialPassthrough:
    """跳过项结构透传到前端，健康接口自身不因凭据缺失而失败。"""

    def test_skipped_item_reaches_response(self, app_client):
        _health_cache["ts"] = 0.0
        _health_cache["data"] = None
        payload = [
            {"name": "免费源", "label": "免费源", "ok": True, "latency_ms": 3.0, "message": "3ms 正常"},
            {
                "name": "需凭据源",
                "label": "需凭据源",
                "ok": False,
                "skipped": True,
                "latency_ms": 0.0,
                "message": "缺少凭据（数据源：示例财经）——请设置环境变量 X_KEY",
            },
        ]
        with patch("src.python.core.check_sources.run_health_checks", return_value=payload):
            resp = app_client.get("/api/health?fresh=1")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        by_name = {r["name"]: r for r in data}
        assert by_name["需凭据源"]["skipped"] is True
        assert "X_KEY" in by_name["需凭据源"]["message"]
        assert "skipped" not in by_name["免费源"]

    def test_no_skipped_key_when_gate_off(self, app_client):
        """开关关闭 → 结构里不出现 skipped（既有消费方断言不受影响）。"""
        _health_cache["ts"] = 0.0
        _health_cache["data"] = None
        payload = [{"name": "免费源", "label": "免费源", "ok": True, "latency_ms": 3.0, "message": "3ms 正常"}]
        with patch("src.python.core.check_sources.run_health_checks", return_value=payload):
            resp = app_client.get("/api/health?fresh=1")

        assert resp.status_code == 200
        assert all("skipped" not in r for r in resp.get_json()["data"])

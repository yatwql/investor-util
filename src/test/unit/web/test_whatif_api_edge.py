"""调仓 What-if 模拟接口边缘场景测试（对应 test_whatif_api.py 的边界分支）。

覆盖：互斥锁忙碌 429、各字段类型错误 400、生效日空串/前后空白的容错语义。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.python.config import _config_defaults
from src.python.config._core import invalidate_config_cache
from src.python.report.whatif_operations import WhatifRunResult
from src.python.web.app import create_app
from src.python.web.runs import RunManager
import src.python.web.handlers as web_handlers
import src.python.web.upload as upload

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_web,
    pytest.mark.edge,
    pytest.mark.usefixtures("offline_external_sources"),
]

_HOLDINGS = [{"名称": "测试基金", "代码": "000001", "份额": 1000.0, "成本": 1.0}]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Flask test_client：output_dir 重定向到 tmp_path。"""
    monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
    invalidate_config_cache()
    app = create_app(RunManager(executor=lambda state, params: 0))
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def cand_file_id(tmp_path):
    path = tmp_path / "调仓后.xlsx"
    path.write_bytes(b"placeholder")
    file_id = "whatif-edge-cand"
    upload._register(file_id, str(path))
    yield file_id
    upload.discard_file(file_id)


def _mock_ok(monkeypatch):
    monkeypatch.setattr("src.python.core.reader.read_holdings", lambda path: list(_HOLDINGS))
    run_mock = MagicMock(return_value=WhatifRunResult(ok=True, excel="调仓模拟.xlsx", html="调仓模拟.html"))
    monkeypatch.setattr("src.python.report.whatif_operations.run_whatif_simulation", run_mock)
    return run_mock


class TestWhatifEdge:
    """互斥忙碌 / 字段类型 / 生效日容错。"""

    def test_busy_lock_429(self, app_client, cand_file_id, monkeypatch):
        """模拟执行互斥：锁被占用时快速失败 429，不排队阻塞请求线程。"""
        _mock_ok(monkeypatch)
        assert web_handlers._whatif_lock.acquire(blocking=False)
        try:
            resp = app_client.post("/api/whatif", json={"candidate_file_id": cand_file_id})
        finally:
            web_handlers._whatif_lock.release()
        assert resp.status_code == 429
        assert resp.get_json()["error_code"] == "WHATIF_BUSY"

    @pytest.mark.parametrize(
        "payload",
        [
            {"candidate_file_id": 123},
            {"candidate_file_id": "x", "base_file_id": 456},
            {"candidate_file_id": "x", "use_existing": "yes"},
            {"candidate_file_id": "x", "effective_date": 123},
        ],
    )
    def test_field_type_invalid_400(self, app_client, payload):
        resp = app_client.post("/api/whatif", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_empty_effective_date_treated_as_absent(self, app_client, cand_file_id, monkeypatch):
        """空串生效日按「未提供」处理（前端清理输入的兜底），不报 400。"""
        run_mock = _mock_ok(monkeypatch)
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": cand_file_id, "effective_date": ""},
        )
        assert resp.status_code == 200
        assert run_mock.call_args.kwargs["effective_date"] is None

    def test_effective_date_whitespace_stripped(self, app_client, cand_file_id, monkeypatch):
        run_mock = _mock_ok(monkeypatch)
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": cand_file_id, "effective_date": "  2026-07-01  "},
        )
        assert resp.status_code == 200
        assert run_mock.call_args.kwargs["effective_date"] == "2026-07-01"

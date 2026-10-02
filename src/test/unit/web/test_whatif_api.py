"""Web 调仓 What-if 模拟接口测试（POST /api/whatif，Flask test_client）。

覆盖：成功链路（存量基准 / 上传基准 / 生效日透传）、参数枚举校验、
同源校验、file_id 过期、持仓读空、业务不可用、执行异常的错误信封映射。
业务链（read_holdings / run_whatif_simulation）全部 mock，不落真实产物。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.python.config import _config_defaults
from src.python.config._core import invalidate_config_cache
from src.python.report.whatif_operations import WhatifRunResult
from src.python.web.app import create_app
from src.python.web.runs import RunManager
import src.python.web.upload as upload

pytestmark = [pytest.mark.unit, pytest.mark.unit_web, pytest.mark.usefixtures("offline_external_sources")]

_HOLDINGS = [{"名称": "测试基金", "代码": "000001", "份额": 1000.0, "成本": 1.0}]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Flask test_client：output_dir 重定向到 tmp_path（产物路径断言用）。"""
    monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
    invalidate_config_cache()
    app = create_app(RunManager(executor=lambda state, params: 0))
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def cand_file_id(tmp_path):
    """注册一个目标持仓临时文件（不经真实上传，直接进 file_id 注册表）。"""
    path = tmp_path / "调仓后.xlsx"
    path.write_bytes(b"placeholder")
    file_id = "whatif-cand-1"
    upload._register(file_id, str(path))
    yield file_id
    upload.discard_file(file_id)


@pytest.fixture
def base_file_id(tmp_path):
    """注册一个基准持仓临时文件。"""
    path = tmp_path / "调仓前.xlsx"
    path.write_bytes(b"placeholder")
    file_id = "whatif-base-1"
    upload._register(file_id, str(path))
    yield file_id
    upload.discard_file(file_id)


def _mock_pipeline(monkeypatch, excel="调仓模拟.xlsx", html="调仓模拟.html", ok=True, reason=""):
    """mock 读取 + 业务链，返回 run_whatif_simulation 的 MagicMock。"""
    read_calls: list[str] = []

    def _read(path):
        read_calls.append(path)
        return list(_HOLDINGS)

    run_mock = MagicMock(
        return_value=WhatifRunResult(ok=ok, reason=reason, excel=excel, html=html)
        if ok
        else WhatifRunResult(ok=False, reason=reason)
    )
    monkeypatch.setattr("src.python.core.reader.read_holdings", _read)
    monkeypatch.setattr("src.python.report.whatif_operations.run_whatif_simulation", run_mock)
    return run_mock, read_calls


class TestWhatifSuccess:
    """成功链路：存量基准 / 上传基准 / 生效日透传 / 产物 basename。"""

    def test_existing_base_success(self, app_client, cand_file_id, monkeypatch, tmp_path):
        run_mock, read_calls = _mock_pipeline(monkeypatch)
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": cand_file_id, "use_existing": True},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["excel"] == "调仓模拟.xlsx"
        assert data["html"] == "调仓模拟.html"
        assert data["base_count"] == len(_HOLDINGS)
        assert data["candidate_count"] == len(_HOLDINGS)
        # 基准走配置默认持仓路径（前缀），目标走上传临时文件
        assert read_calls[0].endswith("个人投资持仓信息.xlsx")
        assert read_calls[1].endswith("调仓后.xlsx")
        # 业务链参数：output_dir 来自隔离配置，生效日缺省 None
        kwargs = run_mock.call_args.kwargs
        assert kwargs["output_dir"] == str(tmp_path)
        assert kwargs["effective_date"] is None
        assert kwargs["reporter"] is None

    def test_uploaded_base_success(self, app_client, cand_file_id, base_file_id, monkeypatch, tmp_path):
        run_mock, read_calls = _mock_pipeline(monkeypatch)
        resp = app_client.post(
            "/api/whatif",
            json={
                "candidate_file_id": cand_file_id,
                "base_file_id": base_file_id,
                "use_existing": False,
            },
        )
        assert resp.status_code == 200
        assert read_calls[0].endswith("调仓前.xlsx")
        assert read_calls[1].endswith("调仓后.xlsx")

    def test_effective_date_passed_through(self, app_client, cand_file_id, monkeypatch, tmp_path):
        run_mock, _ = _mock_pipeline(monkeypatch)
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": cand_file_id, "effective_date": "2026-07-01"},
        )
        assert resp.status_code == 200
        assert run_mock.call_args.kwargs["effective_date"] == "2026-07-01"

    def test_result_paths_normalized_to_basename(self, app_client, cand_file_id, monkeypatch, tmp_path):
        """产物路径为绝对路径时也归一化为 basename（/api/reports 按名取件）。"""
        _mock_pipeline(
            monkeypatch,
            excel=str(tmp_path / "调仓模拟.xlsx"),
            html=str(tmp_path / "调仓模拟.html"),
        )
        resp = app_client.post("/api/whatif", json={"candidate_file_id": cand_file_id})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["excel"] == "调仓模拟.xlsx"
        assert data["html"] == "调仓模拟.html"


class TestWhatifValidation:
    """参数/枚举/同源校验 → 400/403 错误信封。"""

    def test_missing_candidate_400(self, app_client):
        resp = app_client.post("/api/whatif", json={"use_existing": True})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["ok"] is False
        assert body["error_code"] == "BAD_PARAM"

    def test_empty_payload_400(self, app_client):
        resp = app_client.post("/api/whatif", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    @pytest.mark.parametrize(
        "effective_date",
        ["2026-7-1", "20260701", "abc", "2026-13-01"],
    )
    def test_invalid_effective_date_400(self, app_client, cand_file_id, effective_date):
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": cand_file_id, "effective_date": effective_date},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_use_existing_false_without_base_400(self, app_client, cand_file_id):
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": cand_file_id, "use_existing": False},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_cross_origin_403(self, app_client, cand_file_id):
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": cand_file_id},
            headers={"Origin": "http://evil.example"},
        )
        assert resp.status_code == 403
        assert resp.get_json()["error_code"] == "BAD_PARAM"


class TestWhatifErrors:
    """过期/读空/业务不可用/执行异常 → 404/422/500 错误信封。"""

    def test_unknown_file_id_404(self, app_client):
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": "no-such-file-id"},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error_code"] == "FILE_EXPIRED"

    def test_expired_base_file_id_404(self, app_client, cand_file_id):
        resp = app_client.post(
            "/api/whatif",
            json={"candidate_file_id": cand_file_id, "base_file_id": "no-such-base"},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error_code"] == "FILE_EXPIRED"

    def test_empty_candidate_holdings_422(self, app_client, cand_file_id, monkeypatch):
        monkeypatch.setattr("src.python.core.reader.read_holdings", lambda path: [])
        resp = app_client.post("/api/whatif", json={"candidate_file_id": cand_file_id})
        assert resp.status_code == 422
        assert resp.get_json()["error_code"] == "WHATIF_UNAVAILABLE"

    def test_result_not_ok_422(self, app_client, cand_file_id, monkeypatch):
        monkeypatch.setattr("src.python.core.reader.read_holdings", lambda path: list(_HOLDINGS))
        monkeypatch.setattr(
            "src.python.report.whatif_operations.run_whatif_simulation",
            MagicMock(return_value=WhatifRunResult(ok=False, reason="两侧均为空")),
        )
        resp = app_client.post("/api/whatif", json={"candidate_file_id": cand_file_id})
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["error_code"] == "WHATIF_UNAVAILABLE"
        assert "两侧均为空" in body["error"]

    def test_run_exception_500(self, app_client, cand_file_id, monkeypatch):
        monkeypatch.setattr("src.python.core.reader.read_holdings", lambda path: list(_HOLDINGS))
        monkeypatch.setattr(
            "src.python.report.whatif_operations.run_whatif_simulation",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        resp = app_client.post("/api/whatif", json={"candidate_file_id": cand_file_id})
        assert resp.status_code == 500
        assert resp.get_json()["error_code"] == "WHATIF_FAILED"

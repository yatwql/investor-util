"""Web 路由 handler 测试（handlers.py，Flask test_client）。

覆盖：上传→生成→轮询→产物 URL 全链路（管线 mock）/ _run_generation 退出码
映射（generate_report mock）/ 错误信封格式 / 参数枚举校验 / file_id 过期 /
路径穿越与扩展名白名单拒绝。
"""

from __future__ import annotations

import os
import time
from io import BytesIO
from unittest.mock import patch
from urllib.parse import quote

import pytest
from openpyxl import Workbook

import src.python.web.upload as upload
from src.python.config import _config_defaults
from src.python.config._core import invalidate_config_cache
from src.python.report.orchestrator import ReportResult
from src.python.web.app import create_app
from src.python.web.handlers import _run_generation
from src.python.web.runs import RunManager, RunState

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


def _make_holdings_xlsx() -> bytes:
    """构造标准四列最小持仓 xlsx 字节流。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "账户一"
    ws.append(["名称", "代码", "持仓份额", "每份成本"])
    ws.append(["测试基金", "000001", 1000, 1.0])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fake_executor(tmp_path):
    """全链路用 fake executor：记录 output_dir + 推送事件 + 成功返回。"""

    def _exec(state, params):
        state.output_dir = str(tmp_path)
        state.push_event("info", "正在获取行情数据...")
        state.push_event("ok", "报告生成完成")
        return 0

    return _exec


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """构造 Flask test_client：config output_dir 重定向到 tmp_path + fake executor。"""
    monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
    invalidate_config_cache()

    rm = RunManager(executor=_fake_executor(tmp_path))
    app = create_app(rm)
    app.config["TESTING"] = True
    return app.test_client()


class TestFullChain:
    """上传→生成→轮询→产物 URL 全链路（管线 mock）。"""

    def test_upload_then_run_then_poll_then_artifact(self, app_client, tmp_path):
        client = app_client

        # 1. 上传
        resp = client.post("/api/upload", data={"file": (BytesIO(_make_holdings_xlsx()), "持仓.xlsx")})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        file_id = body["data"]["file_id"]
        assert body["data"]["count"] == 1

        # 2. 生成
        resp = client.post(
            "/api/runs",
            json={"file_id": file_id, "report_type": "basic", "fetch_history": None, "force_llm": False},
        )
        assert resp.status_code == 202
        run_id = resp.get_json()["data"]["run_id"]

        # 3. 轮询至完成（fake executor 立即完成）
        for _ in range(200):
            detail = client.get(f"/api/runs/{run_id}").get_json()["data"]
            if detail["status"] in ("done", "failed"):
                break
            time.sleep(0.01)
        assert detail["status"] == "done"
        assert detail["exit_code"] == 0

        # 事件增量轮询
        events_resp = client.get(f"/api/runs/{run_id}/events?after=0")
        events = events_resp.get_json()["data"]["events"]
        assert len(events) == 2

        # 4. 产物 URL（basic → 仅 Excel）
        artifacts = detail["artifacts"]
        assert [a["kind"] for a in artifacts] == ["xlsx"]

        # 往 tmp_path 写一个产物文件供 send_from_directory
        with open(os.path.join(str(tmp_path), "个人投资分析报告.xlsx"), "wb") as f:
            f.write(_make_holdings_xlsx())
        url = "/api/reports/" + quote("个人投资分析报告.xlsx")
        artifact_resp = client.get(url)
        assert artifact_resp.status_code == 200
        assert artifact_resp.data[:2] == b"PK"

    def test_both_type_artifacts(self, app_client, tmp_path):
        client = app_client
        resp = client.post("/api/upload", data={"file": (BytesIO(_make_holdings_xlsx()), "持仓.xlsx")})
        file_id = resp.get_json()["data"]["file_id"]

        resp = client.post("/api/runs", json={"file_id": file_id, "report_type": "both"})
        run_id = resp.get_json()["data"]["run_id"]
        detail = None
        for _ in range(200):
            detail = client.get(f"/api/runs/{run_id}").get_json()["data"]
            if detail["status"] in ("done", "failed"):
                break
            time.sleep(0.01)
        assert detail["status"] == "done"
        assert [a["kind"] for a in detail["artifacts"]] == ["html", "xlsx"]


class TestErrorEnvelope:
    """统一错误信封：{ok:false, error_code, error:中文}。"""

    def test_missing_file_id(self, app_client):
        resp = app_client.post("/api/runs", json={"report_type": "basic"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["ok"] is False
        assert body["error_code"] == "BAD_PARAM"
        assert body["error"]  # 中文文案

    def test_invalid_report_type(self, app_client):
        resp = app_client.post("/api/runs", json={"file_id": "x", "report_type": "weird"})
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_invalid_fetch_history_type(self, app_client):
        resp = app_client.post("/api/runs", json={"file_id": "x", "fetch_history": "yes"})
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_expired_file_id(self, app_client):
        resp = app_client.post("/api/runs", json={"file_id": "nonexistent"})
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["error_code"] == "FILE_EXPIRED"

    def test_unknown_run_404(self, app_client):
        resp = app_client.get("/api/runs/no-such-run")
        assert resp.status_code == 404
        assert resp.get_json()["error_code"] == "NOT_FOUND"

    def test_queue_full_429(self, tmp_path, monkeypatch):
        monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
        invalidate_config_cache()

        slow_calls = {"active": 0}

        def slow_exec(_state, _params):
            slow_calls["active"] += 1
            time.sleep(0.2)
            slow_calls["active"] -= 1
            return 0

        rm = RunManager(executor=slow_exec)
        app = create_app(rm)
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.post("/api/upload", data={"file": (BytesIO(_make_holdings_xlsx()), "持仓.xlsx")})
        file_id = resp.get_json()["data"]["file_id"]

        import src.python.web.runs as runs_mod

        # 塞满队列（容量 = _QUEUE_LIMIT）
        for _ in range(runs_mod._QUEUE_LIMIT):
            client.post("/api/runs", json={"file_id": file_id, "report_type": "basic"})
        overflow = client.post("/api/runs", json={"file_id": file_id, "report_type": "basic"})
        assert overflow.status_code == 429
        assert overflow.get_json()["error_code"] == "RUN_QUEUE_FULL"

    def test_upload_rejects_bad_file(self, app_client):
        resp = app_client.post(
            "/api/upload",
            data={"file": (BytesIO(b"NOTAZIP" + b"\x00" * 32), "伪装.xlsx")},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["ok"] is False
        assert body["error_code"] == "UPLOAD_BAD_FILE"
        assert body["error"]


class TestServeReportSecurity:
    """预览/下载防路径穿越与扩展名白名单（§6.2）。"""

    def test_extension_whitelist_rejects_py(self, app_client):
        resp = app_client.get("/api/reports/evil.py")
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_path_traversal_rejected(self, app_client):
        """.. 穿越：send_from_directory 内置净化拒绝（非 200 + JSON 信封）。"""
        resp = app_client.get("/api/reports/../data/config/config.json")
        # 400（扩展名/净化）或 404（NotFound）均可 —— 关键是不可泄露文件内容
        assert resp.status_code in (400, 404)
        body = resp.get_json()
        assert body["ok"] is False


class TestRunGeneration:
    """_run_generation 执行体（generate_report mock，真实上传预检 + 清理）。"""

    @patch("src.python.report.orchestrator.generate_report")
    def test_maps_exit_code_and_cleans_upload(self, mock_gen, monkeypatch):
        # 真实上传（预检通过）
        result = upload.save_upload(BytesIO(_make_holdings_xlsx()), "持仓.xlsx")
        file_id = result["file_id"]
        params = {"file_id": file_id, "report_type": "basic"}

        mock_gen.return_value = ReportResult(report_generated=True, excel_ok=True)
        state = RunState("r1", params)
        code = _run_generation(state, params)

        assert code == 0
        mock_gen.assert_called_once()
        # 产物 output_dir 取配置快照
        assert state.output_dir == _config_defaults._DEFAULT_CONFIG["output_dir"]
        # 上传临时文件立即清理
        assert upload.resolve_file(file_id) is None

    @patch("src.python.report.orchestrator.generate_report")
    def test_generate_report_error_mapping(self, mock_gen, monkeypatch):
        result = upload.save_upload(BytesIO(_make_holdings_xlsx()), "持仓.xlsx")
        file_id = result["file_id"]
        params = {"file_id": file_id, "report_type": "basic"}

        # 部分失败（errors 非空）→ exit_code 1
        mock_gen.return_value = ReportResult(report_generated=True, excel_ok=True, errors=["某模块失败"])
        state = RunState("r2", params)
        code = _run_generation(state, params)
        assert code == 1
        assert state.errors == ["某模块失败"]

    def test_missing_file_returns_severe(self):
        """file_id 已失效：返回严重退出码 + 错误提示。"""
        state = RunState("r3", {"file_id": "gone", "report_type": "basic"})
        code = _run_generation(state, {"file_id": "gone", "report_type": "basic"})
        assert code == 2
        assert state.errors == ["上传文件已过期，请重新上传"]

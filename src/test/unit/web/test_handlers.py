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
from src.python.web.handlers import _build_artifacts, _build_system_info, _health_cache, _run_generation
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


class TestIndexConfigBackfill:
    """索引页按 get_config() 回填表单默认（历史走势/强制 LLM 复选框）。"""

    def test_index_renders_form_and_status_sections(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # 生成区新增控件
        assert 'id="history-fetch"' in html
        assert 'id="force-llm"' in html
        # 状态区：健康 + 历史
        assert 'id="health-list"' in html
        assert 'id="history-list"' in html

    def test_history_checkbox_follows_config_default(self, app_client):
        """默认 fetch_mode=auto → 历史走势复选框勾选 + 配置说明。"""
        resp = app_client.get("/")
        html = resp.data.decode("utf-8")
        assert 'name="fetch_history" checked' in html
        assert "跟随配置开启" in html

    def test_history_checkbox_off_when_config_fetch_mode_off(self, tmp_path, monkeypatch):
        """配置 history.fetch_mode=off → 复选框不勾选。"""
        monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
        monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG["history"], "fetch_mode", "off")
        invalidate_config_cache()
        rm = RunManager(executor=_fake_executor(tmp_path))
        app = create_app(rm)
        app.config["TESTING"] = True
        html = app.test_client().get("/").data.decode("utf-8")
        assert 'name="fetch_history"' in html  # 控件存在
        assert 'name="fetch_history" checked' not in html  # 未勾选
        assert "当前配置关闭" in html


class TestHealthEndpoint:
    """/api/health 缓存 + fresh 强制重测。"""

    def test_cached_and_fresh(self, app_client):
        _health_cache["ts"] = 0.0
        _health_cache["data"] = None
        calls = {"n": 0}

        def fake_health(max_timeout=15.0):
            calls["n"] += 1
            return [{"name": "x", "label": "测试源", "ok": True, "latency_ms": 1.0, "message": "ok"}]

        with patch("src.python.core.check_sources.run_health_checks", side_effect=fake_health):
            r1 = app_client.get("/api/health")
            assert r1.status_code == 200
            assert r1.get_json()["data"][0]["ok"] is True
            # 60s 缓存内：不触发真实探测
            app_client.get("/api/health")
            assert calls["n"] == 1
            # fresh=1 强制重测
            app_client.get("/api/health?fresh=1")
            assert calls["n"] == 2


class TestArtifactsExitCode:
    """产物清单按 exit_code/状态裁剪（错误处理完善）。"""

    def test_severe_no_artifacts(self):
        state = RunState("r", {"report_type": "both"})
        state.output_dir = "/tmp"
        state.exit_code = 2
        assert _build_artifacts(state.params, state) == []

    def test_failed_no_artifacts(self):
        state = RunState("r", {"report_type": "both"})
        state.output_dir = "/tmp"
        state.status = "failed"
        assert _build_artifacts(state.params, state) == []

    def test_partial_keeps_artifacts(self):
        """exit_code 1（部分失败）：产物仍可用。"""
        state = RunState("r", {"report_type": "both"})
        state.output_dir = "/tmp"
        state.exit_code = 1
        assert [a["kind"] for a in _build_artifacts(state.params, state)] == ["html", "xlsx"]

    def test_success_basic_only_xlsx(self):
        state = RunState("r", {"report_type": "basic"})
        state.output_dir = "/tmp"
        state.exit_code = 0
        assert [a["kind"] for a in _build_artifacts(state.params, state)] == ["xlsx"]


class TestCreateRunBoolParams:
    """阶段 2 表单显式提交布尔参数（历史走势/强制 LLM）。"""

    def test_fetch_history_bool_accepted(self, app_client):
        resp = app_client.post("/api/upload", data={"file": (BytesIO(_make_holdings_xlsx()), "持仓.xlsx")})
        file_id = resp.get_json()["data"]["file_id"]
        for value in (True, False):
            resp = app_client.post(
                "/api/runs", json={"file_id": file_id, "report_type": "basic", "fetch_history": value}
            )
            assert resp.status_code == 202, resp.get_json()

    def test_force_llm_bool_accepted(self, app_client):
        resp = app_client.post("/api/upload", data={"file": (BytesIO(_make_holdings_xlsx()), "持仓.xlsx")})
        file_id = resp.get_json()["data"]["file_id"]
        resp = app_client.post("/api/runs", json={"file_id": file_id, "report_type": "basic", "force_llm": True})
        assert resp.status_code == 202, resp.get_json()


class TestSystemInfo:
    """状态区系统信息组装（_build_system_info：版本 / IP / 持仓摘要 / LLM 状态，对齐 TUI）。

    覆盖：默认未配置 / 持仓摘要字段（含文件就绪判定）/ flat 单 provider /
    credentials_ref 多链 / 读配置异常兜底 / 索引页渲染（未配置时显示「未配置」）。
    """

    @staticmethod
    def _patch_llm(monkeypatch, config=None, module_names=None, circuit="正常"):
        monkeypatch.setattr("src.python.config.get_llm_config", lambda: config)
        monkeypatch.setattr(
            "src.python.core.registry.get_llm_module_names",
            lambda: module_names or {},
        )
        monkeypatch.setattr("src.python.llm.circuit_breaker.get_circuit_status", lambda ep: circuit)
        monkeypatch.setattr("src.python.core.logger._get_machine_ip", lambda: "192.168.1.100")
        return config

    @staticmethod
    def _patch_config(monkeypatch, config=None, privacy_shown=False):
        """替换配置摘要数据源：get_config / 本地状态标志 / 机器 IP。"""
        monkeypatch.setattr("src.python.config.get_config", lambda: config or {})
        monkeypatch.setattr("src.python.config._local_state.get_flag", lambda key: privacy_shown)
        monkeypatch.setattr("src.python.core.logger._get_machine_ip", lambda: "192.168.1.100")
        return config

    def test_default_no_llm_config(self, monkeypatch):
        """未配置（get_llm_config 返回 None）：configured=False，版本/IP 正常。"""
        self._patch_llm(monkeypatch, config=None)
        info = _build_system_info()
        assert info["app_version"]
        assert info["machine_ip"] == "192.168.1.100"
        assert info["llm"] == {"configured": False}

    def test_config_summary_defaults(self, monkeypatch):
        """配置为空 dict：持仓目录/文件未设置、输出默认 reports、新闻 300、状态未就绪、匿名化关闭。"""
        self._patch_llm(monkeypatch, config=None)
        self._patch_config(monkeypatch, config={})
        info = _build_system_info()
        assert info["holdings_dir"] == "未设置"
        assert info["holdings_filename"] == "未设置"
        assert info["output_dir"] == "reports"
        assert info["news_top_count"] == 300
        assert info["holdings_ready"] is False
        assert info["anonymization"] == "关闭"
        assert info["privacy_shown"] is False

    def test_config_summary_fields_and_ready(self, monkeypatch, tmp_path):
        """持仓文件就绪：目录/文件名/输出/新闻/匿名化/隐私齐全，状态为就绪。"""
        holdings_file = tmp_path / "持仓.xlsx"
        holdings_file.touch()
        self._patch_llm(monkeypatch, config=None)
        self._patch_config(
            monkeypatch,
            config={
                "holdings_dir": str(tmp_path),
                "holdings_filename": "持仓.xlsx",
                "output_dir": str(tmp_path / "reports"),
                "news_top_count": 200,
                "features": {"anonymization": {"mode": "full_anonymous"}},
            },
            privacy_shown=True,
        )
        info = _build_system_info()
        assert info["holdings_dir"] == str(tmp_path)
        assert info["holdings_filename"] == "持仓.xlsx"
        assert info["output_dir"] == str(tmp_path / "reports")
        assert info["news_top_count"] == 200
        assert info["holdings_ready"] is True
        assert info["anonymization"] == "完全匿名"
        assert info["privacy_shown"] is True

    def test_config_summary_file_missing(self, monkeypatch, tmp_path):
        """持仓文件不存在：holdings_ready=False（状态「未找到」）。"""
        self._patch_llm(monkeypatch, config=None)
        self._patch_config(
            monkeypatch,
            config={"holdings_dir": str(tmp_path), "holdings_filename": "不存在的.xlsx"},
        )
        info = _build_system_info()
        assert info["holdings_ready"] is False

    def test_get_config_raises_falls_back_defaults(self, monkeypatch):
        """get_config 抛异常 → 摘要按默认值兜底，不阻断页面渲染。"""
        self._patch_llm(monkeypatch, config=None)
        self._patch_config(monkeypatch, config=None)

        def _boom():
            raise RuntimeError("config read failed")

        monkeypatch.setattr("src.python.config.get_config", _boom)
        info = _build_system_info()
        assert info["holdings_dir"] == "未设置"
        assert info["news_top_count"] == 300
        assert info["holdings_ready"] is False
        assert info["llm"] == {"configured": False}

    def test_default_llm_key_missing(self, monkeypatch):
        """flat 模式但缺 api_key/provider：按未配置兜底。"""
        self._patch_llm(monkeypatch, config={"model": "claude-sonnet-4-6"})
        info = _build_system_info()
        assert info["llm"] == {"configured": False}

    def test_flat_mode_details(self, monkeypatch):
        """flat 单 provider：provider/model/endpoint（简化主机名）/熔断/模型路由。"""
        self._patch_llm(
            monkeypatch,
            config={
                "api_key": "sk-test",
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "endpoint": "https://api.anthropic.com/v1/messages",
            },
            module_names={
                "global_macro": "全球政经局势",
                "expert_review": "智囊团深度复盘",
                "debate_pro": "正反辩论",
                "debate_con": "正反辩论反方",
                "debate_synthesis": "辩论总结",
            },
        )
        info = _build_system_info()
        llm = info["llm"]
        assert llm["configured"] is True
        assert llm["mode"] == "flat"
        assert llm["provider"] == "claude"
        assert llm["model"] == "claude-sonnet-4-6"
        assert llm["endpoint_display"] == "api.anthropic.com"
        assert llm["circuit"] == "正常"
        # 模型路由：隐藏后缀（辩论三模块）不展示；未配置的模块级 model 回退到全局 model
        assert "全球政经局势=claude-sonnet-4-6" in llm["route"]
        assert "智囊团深度复盘=claude-sonnet-4-6" in llm["route"]
        assert not any("正反辩论" in r for r in llm["route"])

    def test_flat_mode_module_model_override(self, monkeypatch):
        """模块级 model_{sfx} 覆盖全局 model（路由展示各模块实际模型）。"""
        self._patch_llm(
            monkeypatch,
            config={
                "api_key": "sk-test",
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "endpoint": "默认",
                "model_expert_review": "claude-opus-4-8",
            },
            module_names={"global_macro": "全球政经局势", "expert_review": "智囊团深度复盘"},
        )
        info = _build_system_info()
        llm = info["llm"]
        # endpoint == "默认" → 熔断状态不查询（"—"）
        assert llm["endpoint_display"] == "默认"
        assert llm["circuit"] == "—"
        assert "全球政经局势=claude-sonnet-4-6" in llm["route"]
        assert "智囊团深度复盘=claude-opus-4-8" in llm["route"]

    def test_multi_chain_mode(self, monkeypatch):
        """credentials_ref 多链：策略 / provider 清单（含凭据引用解析）/ 模块偏好。"""
        self._patch_llm(
            monkeypatch,
            config={
                "_strategy": "priority",
                "_provider_list": [
                    {
                        "name": "主链",
                        "provider": "claude",
                        "model": "claude-sonnet-4-6",
                        "endpoint": "https://api.anthropic.com/v1/messages",
                        "priority": 1,
                    },
                    {"name": "备链", "provider": "openai", "credentials_ref": "ref-openai", "priority": 2},
                ],
                "_llm_credentials": {
                    "ref-openai": {"model": "gpt-4o", "endpoint": "https://api.openai.com/v1"},
                },
                "_preferred_providers": {"global_macro": "主链", "expert_review": "备链"},
            },
            module_names={"global_macro": "全球政经局势", "expert_review": "智囊团深度复盘"},
        )
        info = _build_system_info()
        llm = info["llm"]
        assert llm["configured"] is True
        assert llm["mode"] == "multi"
        assert llm["strategy"] == "优先级排序"
        assert len(llm["providers"]) == 2
        # 主链：直接来自 provider_list
        assert llm["providers"][0]["name"] == "主链"
        assert llm["providers"][0]["backend"] == "claude"
        assert llm["providers"][0]["endpoint_display"] == "api.anthropic.com"
        assert llm["providers"][0]["priority"] == "1"
        # 备链：model/endpoint 从 credentials_ref 解析
        assert llm["providers"][1]["name"] == "备链"
        assert llm["providers"][1]["model"] == "gpt-4o"
        assert llm["providers"][1]["endpoint_display"] == "api.openai.com"
        assert llm["providers"][1]["priority"] == "2"
        assert llm["providers"][1]["circuit"] == "正常"
        # 模块偏好：模块语义名 → provider 名
        assert llm["preferred"] == ["全球政经局势 → 主链", "智囊团深度复盘 → 备链"]

    def test_get_llm_config_raises_falls_back_unconfigured(self, monkeypatch):
        """读取 LLM 配置抛异常 → 按未配置兜底，不阻断页面渲染。"""
        self._patch_llm(monkeypatch, config=None)

        def _boom():
            raise RuntimeError("config read failed")

        monkeypatch.setattr("src.python.config.get_llm_config", _boom)
        info = _build_system_info()
        assert info["llm"] == {"configured": False}
        assert info["machine_ip"] == "192.168.1.100"

    def test_index_renders_system_info_unconfigured(self, app_client):
        """索引页未配置时：版本/IP 渲染 + LLM 显示「未配置」+ 不显示详情区。"""
        resp = app_client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="system-version"' in html
        assert 'id="system-ip"' in html
        assert 'id="system-llm"' in html
        assert "未配置" in html
        assert 'id="system-llm-detail"' not in html

    def test_index_renders_config_summary(self, app_client, tmp_path, monkeypatch):
        """索引页渲染持仓摘要：目录/文件/输出/新闻上限/状态（就绪）/匿名化/隐私。"""
        holdings_file = tmp_path / "持仓.xlsx"
        holdings_file.touch()
        self._patch_config(
            monkeypatch,
            config={
                "holdings_dir": str(tmp_path),
                "holdings_filename": "持仓.xlsx",
                "output_dir": str(tmp_path / "reports"),
                "news_top_count": 150,
                "features": {"anonymization": {"mode": "code_display"}},
            },
            privacy_shown=False,
        )
        resp = app_client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="system-holdings-dir"' in html and str(tmp_path) in html
        assert 'id="system-holdings-file"' in html and "持仓.xlsx" in html
        assert 'id="system-output-dir"' in html
        assert 'id="system-news-top"' in html and "150 条" in html
        assert 'id="system-anonymization"' in html and "代码显示" in html
        assert 'id="system-privacy"' in html and "待首次报告生成时显示" in html
        # 文件就绪 → 绿色状态文案
        assert '<span class="system-status-ok">文件就绪</span>' in html

    def test_index_renders_config_summary_file_missing(self, app_client, tmp_path, monkeypatch):
        """持仓文件不存在 → 状态显示「文件未找到」（红色）。"""
        self._patch_config(
            monkeypatch,
            config={"holdings_dir": str(tmp_path), "holdings_filename": "缺失.xlsx"},
            privacy_shown=True,
        )
        resp = app_client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert '<span class="system-status-err">文件未找到</span>' in html
        assert 'id="system-privacy"' in html and "已显示" in html

#!/usr/bin/env python3
"""Web 模式 HTTP 冒烟脚本 — 上传→生成→进度→产物全链路（Flask test_client）。

沉淀自 Web 模式验收的临时 HTTP 冒烟脚本（原脚本为一次性脚本，未入库）。
本脚本以 Flask test_client 在进程内走 HTTP 链路（不占真实端口、不发真实
网络），覆盖 9 项断言：

  1. 页面渲染      GET /                    → 200 + HTML 含 main.js 引用与关键元素
  2. 健康检查      GET /api/health          → 200 + ok 信封（探测源 mock）
  3. 上传校验      POST /api/upload         → 合法 xlsx → 200 + file_id + count==1；
                                               伪装坏文件 → 400 UPLOAD_BAD_FILE
  4. 生成 202      POST /api/runs           → 202 + run_id
  5. 进度事件      GET /api/runs/{id}/events → 事件非空 + status 可达 done
  6. 完成态        GET /api/runs/{id}       → status done + exit_code 0 + artifacts
  7. 产物下载      GET /api/reports/{名}     → 200 + xlsx 文件头（PK）
  8. 历史记录      GET /api/runs/history    → 200 + ok + records 列表（mock）
  9. 产物目录隔离  run 的 output_dir 落在临时目录，非项目真实 reports/

隔离（对齐测试隔离纪律）：
  - 管线 mock：注入 fake executor（写产物 + 推送事件 + 返回 0）
  - 配置重定向：output_dir → 临时目录
  - 上传目录重定向：upload._UPLOAD_DIR → 临时目录
  - 健康/历史 mock：run_health_checks / load_history 返回罐头数据
  - 服务进程内（test_client），不建真实 socket

用法：
  .venv/bin/python scripts/smoke-web.py          # 全量 9 项
  .venv/bin/python scripts/smoke-web.py --quiet  # 仅打印失败项

退出码：0 全部通过；2 存在失败项。
"""

from __future__ import annotations

import io
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 产物固定文件名（与 handlers._LATEST_XLSX 一致）
_LATEST_XLSX = "个人投资分析报告.xlsx"

# 检查结果统一信封：{name, ok, detail}
_RESULT_NAME = "name"
_RESULT_OK = "ok"
_RESULT_DETAIL = "detail"


def _make_holdings_xlsx() -> bytes:
    """构造标准四列最小持仓 xlsx 字节流（复用测试夹具模式）。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "账户一"
    ws.append(["名称", "代码", "持仓份额", "每份成本"])
    ws.append(["测试基金", "000001", 1000, 1.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fake_health(max_timeout: float = 15.0):
    """罐头健康探测结果（避免真实网络）。"""
    return [{"name": "mock_source", "label": "测试行情源", "ok": True, "latency_ms": 1.0, "message": "ok"}]


def _fake_history():
    """罐头历史记录（避免读真实 perf 历史文件）。"""
    return [{"run_id": "smoke-1", "report_type": "basic", "exit_code": 0, "duration_s": 0.5}]


def _fake_executor(output_dir: str):
    """全链路 fake executor：写产物到 output_dir + 推送事件 + 成功返回。"""

    def _exec(state, params):
        state.output_dir = str(output_dir)
        state.push_event("info", "正在获取行情数据...")
        state.push_event("ok", "报告生成完成")
        artifact = Path(output_dir) / _LATEST_XLSX
        artifact.write_bytes(_make_holdings_xlsx())
        return 0

    return _exec


def _build_client(tmp_root: Path):
    """构造隔离的 Flask test_client：配置/上传目录重定向 + fake executor。"""
    from src.python.config import _config_defaults
    from src.python.config._core import invalidate_config_cache
    from src.python.web.app import create_app
    from src.python.web.runs import RunManager

    output_dir = tmp_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 配置 output_dir 重定向（run 出队时读取的配置快照取这里）
    _config_defaults._DEFAULT_CONFIG["output_dir"] = str(output_dir)
    invalidate_config_cache()

    rm = RunManager(executor=_fake_executor(str(output_dir)))
    app = create_app(rm)
    app.config["TESTING"] = True
    return app.test_client(), output_dir


def _check_page_render(client, results):
    resp = client.get("/")
    html = resp.data.decode("utf-8")
    ok = resp.status_code == 200
    ok = ok and "/static/main.js" in html
    ok = ok and all(k in html for k in ('id="generate-form"', 'id="progress-section"', 'id="result-section"'))
    results.append(
        {
            _RESULT_NAME: "页面渲染",
            _RESULT_OK: ok,
            _RESULT_DETAIL: f"GET / -> {resp.status_code}",
        }
    )


def _check_health(client, results):
    with patch("src.python.core.check_sources.run_health_checks", side_effect=_fake_health):
        resp = client.get("/api/health")
    body = resp.get_json() or {}
    ok = resp.status_code == 200 and body.get("ok") is True and body.get("data")
    results.append({_RESULT_NAME: "健康检查", _RESULT_OK: ok, _RESULT_DETAIL: f"GET /api/health -> {resp.status_code}"})


def _check_upload(client, results) -> str | None:
    from src.python.web.upload import _file_registry

    xlsx = _make_holdings_xlsx()
    resp = client.post("/api/upload", data={"file": (io.BytesIO(xlsx), "持仓.xlsx")})
    body = resp.get_json() or {}
    file_id = (body.get("data") or {}).get("file_id")
    ok = resp.status_code == 200 and body.get("ok") is True
    ok = ok and bool(file_id) and (body.get("data") or {}).get("count") == 1

    # 伪装坏文件 → 400 UPLOAD_BAD_FILE
    resp_bad = client.post("/api/upload", data={"file": (io.BytesIO(b"NOTAZIP" + b"\x00" * 32), "伪装.xlsx")})
    bad_body = resp_bad.get_json() or {}
    ok = ok and resp_bad.status_code == 400 and bad_body.get("error_code") == "UPLOAD_BAD_FILE"

    results.append(
        {
            _RESULT_NAME: "上传校验",
            _RESULT_OK: ok,
            _RESULT_DETAIL: f"合法 xlsx -> {resp.status_code}, 坏文件 -> {resp_bad.status_code}",
        }
    )
    return file_id if ok else None


def _check_run_and_poll(client, results, file_id: str) -> str | None:
    import json

    resp = client.post(
        "/api/runs",
        data=json.dumps({"file_id": file_id, "report_type": "basic"}),
        content_type="application/json",
    )
    body = resp.get_json() or {}
    run_id = (body.get("data") or {}).get("run_id")
    ok = resp.status_code == 202 and body.get("ok") is True and bool(run_id)
    results.append({_RESULT_NAME: "生成 202", _RESULT_OK: ok, _RESULT_DETAIL: f"POST /api/runs -> {resp.status_code}"})
    return run_id if ok else None


def _check_progress_events(client, results, run_id: str):
    # fake executor 立即完成，轮询至终态
    status = None
    for _ in range(100):
        detail = client.get(f"/api/runs/{run_id}").get_json().get("data") or {}
        status = detail.get("status")
        if status in ("done", "failed"):
            break
        time.sleep(0.01)

    ev_resp = client.get(f"/api/runs/{run_id}/events?after=0")
    ev_body = ev_resp.get_json() or {}
    events = (ev_body.get("data") or {}).get("events") or []
    ok = status == "done" and ev_resp.status_code == 200 and len(events) >= 2
    results.append(
        {
            _RESULT_NAME: "进度事件",
            _RESULT_OK: ok,
            _RESULT_DETAIL: f"status={status}, events={len(events)}",
        }
    )


def _check_final_state(client, results, run_id: str):
    resp = client.get(f"/api/runs/{run_id}")
    body = resp.get_json() or {}
    detail = body.get("data") or {}
    artifacts = detail.get("artifacts") or []
    ok = detail.get("status") == "done"
    ok = ok and detail.get("exit_code") == 0
    ok = ok and any(a.get("kind") == "xlsx" for a in artifacts)
    results.append(
        {
            _RESULT_NAME: "完成态",
            _RESULT_OK: ok,
            _RESULT_DETAIL: f"status={detail.get('status')}, exit_code={detail.get('exit_code')}",
        }
    )


def _check_report_download(client, results):
    from urllib.parse import quote

    resp = client.get("/api/reports/" + quote(_LATEST_XLSX))
    ok = resp.status_code == 200 and resp.data[:2] == b"PK"
    results.append(
        {_RESULT_NAME: "产物下载", _RESULT_OK: ok, _RESULT_DETAIL: f"GET /api/reports/... -> {resp.status_code}"}
    )


def _check_history(client, results):
    with patch("src.python.core.perf.load_history", side_effect=_fake_history):
        resp = client.get("/api/runs/history")
    body = resp.get_json() or {}
    ok = resp.status_code == 200 and body.get("ok") is True and isinstance(body.get("data"), list)
    results.append(
        {
            _RESULT_NAME: "历史记录",
            _RESULT_OK: ok,
            _RESULT_DETAIL: f"GET /api/runs/history -> {resp.status_code}",
        }
    )


def _check_output_dir_isolated(client, results, run_id: str, output_dir: Path):
    detail = (client.get(f"/api/runs/{run_id}").get_json() or {}).get("data") or {}
    run_out = detail.get("output_dir") or ""
    real_reports = (_REPO_ROOT / "reports").resolve()
    ok = bool(run_out) and Path(run_out).resolve() != real_reports
    ok = ok and Path(run_out) == output_dir
    results.append(
        {
            _RESULT_NAME: "产物目录隔离",
            _RESULT_OK: ok,
            _RESULT_DETAIL: f"output_dir={run_out}",
        }
    )


def run_smoke() -> list[dict]:
    """执行全部 9 项冒烟检查，返回 [{name, ok, detail}]。"""
    from src.python.web import upload

    # 保存并重定向上传目录 / 文件注册表（finally 还原，防污染其他调用方）
    saved_upload_dir = upload._UPLOAD_DIR
    saved_registry = upload._file_registry

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="smoke-web-") as tmp:
        tmp_root = Path(tmp)
        try:
            upload._UPLOAD_DIR = str(tmp_root / "uploads")
            upload._file_registry = {}

            client, output_dir = _build_client(tmp_root)

            _check_page_render(client, results)
            _check_health(client, results)
            file_id = _check_upload(client, results)
            run_id = None
            if file_id:
                run_id = _check_run_and_poll(client, results, file_id)
            if run_id:
                _check_progress_events(client, results, run_id)
                _check_final_state(client, results, run_id)
                _check_output_dir_isolated(client, results, run_id, output_dir)
            _check_report_download(client, results)
            _check_history(client, results)
        finally:
            upload._UPLOAD_DIR = saved_upload_dir
            upload._file_registry = saved_registry
    return results


def main() -> int:
    quiet = "--quiet" in sys.argv
    results = run_smoke()
    failed = [r for r in results if not r[_RESULT_OK]]
    for r in results:
        if quiet and r[_RESULT_OK]:
            continue
        tag = "[OK]" if r[_RESULT_OK] else "[ERR]"
        print(f"  {tag} {r[_RESULT_NAME]} — {r[_RESULT_DETAIL]}")
    print(f"  Web 冒烟结果：{len(results) - len(failed)}/{len(results)} 通过")
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

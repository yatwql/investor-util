#!/usr/bin/env python3
"""Web 模式 HTTP 冒烟脚本 — 上传→生成→进度→产物全链路（Flask test_client）。

沉淀自 Web 模式验收的临时 HTTP 冒烟脚本（原脚本为一次性脚本，未入库）。
本脚本以 Flask test_client 在进程内走 HTTP 链路（不占真实端口、不发真实
网络），覆盖 11 项断言：

  1. 页面渲染      GET /                    → 200 + HTML 含 main.js 引用与关键元素；
                                               引用的全部 /static/* 资产可访问（200，防 404 漂移）
  2. 健康检查      GET /api/health          → 200 + ok 信封（探测源 mock）
  3. 上传校验      POST /api/upload         → 合法 xlsx → 200 + file_id + count==1；
                                               伪装坏文件 → 400 UPLOAD_BAD_FILE
  4. 生成 202      POST /api/runs           → 202 + run_id
  5. 进度事件      GET /api/runs/{id}/events → 事件非空 + status 可达 done
  6. 完成态        GET /api/runs/{id}       → status done + exit_code 0 + artifacts
  7. 产物下载      GET /api/reports/{名}     → 200 + xlsx 文件头（PK）
  8. 历史记录      GET /api/runs/history    → 200 + ok + records 列表（mock）
  9. 产物目录隔离  run 的 output_dir 落在临时目录，非项目真实 reports/
 10. 正式-用存量   POST /api/runs            → 无 file_id 提交 202 + run_id；
                                              带 file_id / 非法 mode → 400 BAD_PARAM
 11. 配置编辑      GET /api/config/edit      → 200 + 7 组可编辑面；
                                              合法保存 enable_news → 200；
                                              非法键 → 400 BAD_PARAM

隔离（对齐测试隔离纪律）：
  - 管线 mock：注入 fake executor（写产物 + 推送事件 + 返回 0）
  - 配置重定向：output_dir → 临时目录；config.json → 临时目录（写配置不污染真实配置）
  - 上传目录重定向：upload._UPLOAD_DIR → 临时目录
  - 健康/历史 mock：run_health_checks / load_history 返回罐头数据
  - 服务进程内（test_client），不建真实 socket

用法：
  .venv/bin/python scripts/smoke-web.py          # 全量 11 项
  .venv/bin/python scripts/smoke-web.py --quiet  # 仅打印失败项

退出码：0 全部通过；2 存在失败项。
"""

from __future__ import annotations

import io
import re
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
    # 正式-用存量冒烟需要正式持仓文件：holdings_dir 一并重定向并落一份合法文件
    holdings_dir = tmp_root / "holdings"
    holdings_dir.mkdir(parents=True, exist_ok=True)
    _config_defaults._DEFAULT_CONFIG["holdings_dir"] = str(holdings_dir)
    _config_defaults._DEFAULT_CONFIG["holdings_filename"] = "测试持仓.xlsx"
    (holdings_dir / "测试持仓.xlsx").write_bytes(_make_holdings_xlsx())
    # 配置编辑冒烟需写 config.json：重定向到临时目录（防污染真实 data/config/）
    config_dir = tmp_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    _config_defaults._CONFIG_FILE = str(config_dir / "config.json")
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
    # 输入模式控件：生成用途单选 / 输入来源单选 / 正式展开区 / 覆盖确认勾选 / 警示条
    ok = ok and 'name="input_mode"' in html and 'value="trial"' in html and 'value="formal"' in html
    ok = ok and 'name="use_existing"' in html and 'value="existing"' in html
    ok = ok and 'id="formal-options"' in html and 'id="confirm-overwrite"' in html and 'id="formal-warning"' in html
    # 静态资产可解析：index.html 引用的每个 /static/* 资源都必须返回 200。
    # 盲区——此前仅查引用串存在（"/static/main.js" in html）不查资源可访问，
    # static_url_path 推导漂移致全部资产 404 时整页 JS/CSS 失效、冒烟仍误报通过。
    assets = re.findall(r'(?:src|href)="(/static/[^"?#]+)', html)
    missing = [a for a in assets if client.get(a).status_code != 200]
    ok = ok and bool(assets) and not missing
    detail = f"GET / -> {resp.status_code}, 静态资产 {len(assets)} 个"
    if missing:
        detail += f"，404: {missing}"
    results.append({_RESULT_NAME: "页面渲染", _RESULT_OK: ok, _RESULT_DETAIL: detail})


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


def _check_formal_use_existing(client, results) -> None:
    """正式-用存量冒烟：无 file_id 提交 → 202；携带 file_id / 非法 mode → 400。

    后端组合校验（handlers._handle_create_run）：formal+use_existing 禁止携带
    file_id；mode 仅允许 trial/formal。正式持仓文件已在 _build_client 落盘。
    """
    import json

    # ① 用存量：无 file_id 放行 → 202 + run_id
    resp_ok = client.post(
        "/api/runs",
        data=json.dumps({"mode": "formal", "use_existing": True, "report_type": "basic"}),
        content_type="application/json",
    )
    body_ok = resp_ok.get_json() or {}
    run_id = (body_ok.get("data") or {}).get("run_id")
    ok = resp_ok.status_code == 202 and body_ok.get("ok") is True and bool(run_id)

    # ② 用存量 + 携带 file_id → 400 BAD_PARAM
    resp_bad_id = client.post(
        "/api/runs",
        data=json.dumps({"mode": "formal", "use_existing": True, "file_id": "fake", "report_type": "basic"}),
        content_type="application/json",
    )
    bad_id_body = resp_bad_id.get_json() or {}
    ok = ok and resp_bad_id.status_code == 400 and bad_id_body.get("error_code") == "BAD_PARAM"

    # ③ 非法 mode → 400 BAD_PARAM
    resp_bad_mode = client.post(
        "/api/runs",
        data=json.dumps({"mode": "bogus", "report_type": "basic"}),
        content_type="application/json",
    )
    bad_mode_body = resp_bad_mode.get_json() or {}
    ok = ok and resp_bad_mode.status_code == 400 and bad_mode_body.get("error_code") == "BAD_PARAM"

    results.append(
        {
            _RESULT_NAME: "正式-用存量",
            _RESULT_OK: ok,
            _RESULT_DETAIL: (
                f"无 file_id -> {resp_ok.status_code}, "
                f"带 file_id -> {resp_bad_id.status_code}, "
                f"非法 mode -> {resp_bad_mode.status_code}"
            ),
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


def _check_config_edit(client, results) -> None:
    """配置编辑冒烟：GET 面板全量面 → 合法保存 200 → 非法键 400。

    配置编辑会写共享 config.json，_build_client 已将其重定向到临时目录，
    本检查不会污染真实 data/config/。
    """

    # ① GET 面板：7 组全量可编辑面
    resp_get = client.get("/api/config/edit")
    body_get = resp_get.get_json() or {}
    data = body_get.get("data") or {}
    ok = resp_get.status_code == 200 and body_get.get("ok") is True
    ok = ok and set(data) >= {
        "paths",
        "sections",
        "submodules",
        "anonymization",
        "comparison_indices",
        "comparison_indices_defaults",
        "llm",
    }

    # ② 合法保存：enable_news → 200 + key/value 回显
    resp_save = client.post("/api/config/edit", json={"key": "enable_news", "value": False})
    body_save = resp_save.get_json() or {}
    ok = ok and resp_save.status_code == 200 and body_save.get("ok") is True
    ok = ok and (body_save.get("data") or {}).get("key") == "enable_news"
    ok = ok and (body_save.get("data") or {}).get("value") is False

    # ③ 非法键 → 400 BAD_PARAM
    resp_bad = client.post("/api/config/edit", json={"key": "no_such_key", "value": True})
    bad_body = resp_bad.get_json() or {}
    ok = ok and resp_bad.status_code == 400 and bad_body.get("error_code") == "BAD_PARAM"

    results.append(
        {
            _RESULT_NAME: "配置编辑",
            _RESULT_OK: ok,
            _RESULT_DETAIL: (
                f"GET -> {resp_get.status_code}, "
                f"保存 enable_news -> {resp_save.status_code}, "
                f"非法键 -> {resp_bad.status_code}"
            ),
        }
    )


def run_smoke() -> list[dict]:
    """执行全部 11 项冒烟检查，返回 [{name, ok, detail}]。"""
    from src.python.config import _config_defaults
    from src.python.config._core import invalidate_config_cache
    from src.python.web import upload

    # 保存并重定向上传目录 / 文件注册表 / config.json 路径 / _DEFAULT_CONFIG 覆盖
    # （finally 统一还原，防残留污染其他调用方/后续测试——_DEFAULT_CONFIG 若残留，
    # 后续 config 测试会读到非默认配置，产生顺序依赖失败）
    saved_upload_dir = upload._UPLOAD_DIR
    saved_registry = upload._file_registry
    saved_config_file = _config_defaults._CONFIG_FILE
    saved_defaults = dict(_config_defaults._DEFAULT_CONFIG)

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
            _check_formal_use_existing(client, results)
            _check_config_edit(client, results)
        finally:
            upload._UPLOAD_DIR = saved_upload_dir
            upload._file_registry = saved_registry
            _config_defaults._CONFIG_FILE = saved_config_file
            _config_defaults._DEFAULT_CONFIG.clear()
            _config_defaults._DEFAULT_CONFIG.update(saved_defaults)
            invalidate_config_cache()
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

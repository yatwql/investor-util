"""Web 路由 handler — 页面/上传/生成/轮询/预览/下载/历史/健康。

生成 handler（``_run_generation``）复刻 ``cli.py:_handle_report`` 模板：
读持仓（含流水页签）→ 建 reporter → ``generate_report`` → 映射 exit_code。
Worker 线程经 RunManager 执行，产物定位基于出队时配置快照的 output_dir。

响应统一信封：成功 ``{"ok": true, "data": ...}``；
错误 ``{"ok": false, "error_code": str|null, "error": 中文文案}``
（error_code 为机器可判定短标识，前端按 code 分支动作，不靠解析中文）。
"""

from __future__ import annotations

import logging
import os
import time
from urllib.parse import urlparse

from flask import request, send_from_directory

logger = logging.getLogger("invest")

# ── 退出码（对齐 cli.py）──────────────────────────────
_EXIT_SUCCESS = 0
_EXIT_PARTIAL = 1
_EXIT_SEVERE = 2

# 产物固定文件名（与 report/html_save.py / excel_writer.py 最新版固定名一致）
_LATEST_HTML = "个人投资分析报告.html"
_LATEST_XLSX = "个人投资分析报告.xlsx"

# 预览/下载扩展名白名单（.lower() 归一化后校验，防 .HTML/.XLSX 绕过）
_ALLOWED_REPORT_EXT = {"html", "js", "map", "css", "png", "svg", "json", "xlsx"}

# 短缓存（健康 60s / 历史 5s）——防频繁轮询重复读文件/重复真实探测
_health_cache: dict = {"ts": 0.0, "data": None}
_history_cache: dict = {"ts": 0.0, "data": None}


# ── 响应信封辅助 ─────────────────────────────────────


def _ok(data):
    return {"ok": True, "data": data}


def _err(error_code, message):
    return {"ok": False, "error_code": error_code, "error": message}


# ── worker 执行体（RunManager.executor 注入点）────────────────


def _run_generation(state, params: dict) -> int:
    """单个 run 的执行体：读持仓 → 建 reporter → generate_report → 映射退出码。

    在 worker 线程执行。每个 run 启动时取一次 ``get_config()`` 快照
    （run 期间不受外部配置修改影响）；产物 output_dir 基于该快照
    保存到 run 记录（产物 URL/下载基于 run 记录而非实时配置）。
    上传临时文件在 finally 中立即删除（§6.1 清理）。
    """
    from src.python.config import get_config
    from src.python.core.reader import read_holdings_with_flows
    from src.python.report.orchestrator import generate_report

    from src.python.web.progress import WebProgressReporter
    from src.python.web.upload import discard_file, resolve_file

    file_id = params.get("file_id")
    path = resolve_file(file_id) if file_id else None
    if path is None:
        state.errors.append("上传文件已过期，请重新上传")
        return _EXIT_SEVERE

    try:
        parsed = read_holdings_with_flows(path)
        holdings = parsed.holdings
        if not holdings:
            state.errors.append("持仓文件为空或格式异常")
            return _EXIT_SEVERE

        # 每个 run 启动取一次配置快照（run 期间不受外部配置修改影响）
        config = get_config()
        reporter = WebProgressReporter(state)
        result = generate_report(
            holdings=holdings,
            config=config,
            reporter=reporter,
            report_type=params.get("report_type", "basic"),
            # None → generate_report 回退到配置层 history.fetch_mode 解析
            fetch_history=params.get("fetch_history"),
            force_llm=bool(params.get("force_llm")),
            output_dir=None,
            transactions=parsed.transactions,
            dividends=parsed.dividends,
        )
        state.output_dir = config.get("output_dir", "reports")
        state.errors = list(result.errors)
        return result.exit_code
    except Exception:
        logger.exception("[web-run] run %s 生成异常", state.run_id)
        state.errors.append("生成任务执行异常（详情请查看日志）")
        return _EXIT_SEVERE
    finally:
        discard_file(file_id)


def _build_artifacts(params: dict, state) -> list[dict]:
    """按 report_type 计算产物清单（路径相对 output_dir，供前端渲染按钮）。

    basic → 仅 Excel；both/full → HTML + Excel（对齐 CLI --type 语义）。
    """
    report_type = params.get("report_type", "basic")
    if not state.output_dir:
        return []
    artifacts = []
    if report_type in ("both", "full"):
        artifacts.append({"kind": "html", "name": "HTML 报告", "path": _LATEST_HTML})
    artifacts.append({"kind": "xlsx", "name": "Excel 报告", "path": _LATEST_XLSX})
    return artifacts


# ── 同源校验（轻量，副作用操作用）────────────────────


def _is_same_origin() -> bool:
    """轻量同源校验：Sec-Fetch-Site / Origin 与请求 host 一致性。

    test_client / 无这些头的合法客户端默认放行；跨站请求（伪造提交）拒绝。
    """
    sec_fetch = request.headers.get("Sec-Fetch-Site")
    if sec_fetch and sec_fetch not in ("same-origin", "same-site", "none"):
        return False
    origin = request.headers.get("Origin")
    if origin:
        host = request.host
        try:
            netloc = urlparse(origin).netloc
            if netloc and netloc != host:
                return False
        except ValueError:
            return False
    return True


# ── 路由 handler ─────────────────────────────────────


def _handle_index():
    from flask import render_template

    from src.python.core.constants import APP_VERSION

    # 静态资源带版本查询串 ?v={APP_VERSION}（防浏览器缓存旧 JS/CSS 导致功能异常）
    return render_template("index.html", app_version=APP_VERSION)


def _handle_upload():
    from src.python.web.upload import UploadError, save_upload

    file = request.files.get("file")
    if file is None or not file.filename:
        return _err("UPLOAD_BAD_FILE", "未选择文件"), 400
    try:
        data = save_upload(file.stream, file.filename)
    except UploadError as e:
        return _err(e.error_code, e.message), 400
    return _ok(data)


def _handle_create_run(run_manager):
    from src.python.web.upload import resolve_file

    payload = request.get_json(silent=True) or {}
    file_id = payload.get("file_id")
    report_type = payload.get("report_type", "basic")
    fetch_history = payload.get("fetch_history")
    force_llm = payload.get("force_llm", False)

    # 枚举校验（BAD_PARAM）
    if not isinstance(file_id, str) or not file_id:
        return _err("BAD_PARAM", "缺少 file_id"), 400
    if report_type not in ("basic", "both", "full"):
        return _err("BAD_PARAM", "报告格式不合法（basic/both/full）"), 400
    if fetch_history is not None and not isinstance(fetch_history, bool):
        return _err("BAD_PARAM", "历史走势参数不合法"), 400
    if not isinstance(force_llm, bool):
        return _err("BAD_PARAM", "强制 LLM 参数不合法"), 400
    # file_id 存在且未过期（TTL 清理后引用 → FILE_EXPIRED）
    if resolve_file(file_id) is None:
        return _err("FILE_EXPIRED", "上传文件已过期，请重新上传"), 404
    # 副作用操作轻量同源校验
    if not _is_same_origin():
        return _err("BAD_PARAM", "同源校验失败，拒绝提交"), 403

    run_id = run_manager.submit(
        {
            "file_id": file_id,
            "report_type": report_type,
            "fetch_history": fetch_history,
            "force_llm": force_llm,
        }
    )
    if run_id is None:
        return _err("RUN_QUEUE_FULL", "已有任务在跑，排队或稍后再试"), 429
    return _ok({"run_id": run_id}), 202


def _handle_list_runs(run_manager):
    states = run_manager.list_runs(limit=10)
    return _ok([s.snapshot() for s in states])


def _handle_run_detail(run_manager, run_id):
    state = run_manager.get(run_id)
    if state is None:
        return _err("NOT_FOUND", "任务不存在"), 404
    data = state.snapshot()
    if state.status in ("done", "failed"):
        data["artifacts"] = _build_artifacts(state.params, state)
    return _ok(data)


def _handle_run_events(run_manager, run_id):
    state = run_manager.get(run_id)
    if state is None:
        return _err("NOT_FOUND", "任务不存在"), 404
    raw = request.args.get("after", "0")
    try:
        after = max(0, int(raw))
    except (TypeError, ValueError):
        after = 0
    events = state.events_after(after)
    last_seq = events[-1]["seq"] if events else after
    return _ok({"events": events, "status": state.status, "last_seq": last_seq})


def _handle_run_history():
    from src.python.core.perf import load_history

    now = time.time()
    if _history_cache["data"] is not None and now - _history_cache["ts"] < 5:
        return _ok(_history_cache["data"])
    records = load_history()
    _history_cache["ts"] = now
    _history_cache["data"] = records
    return _ok(records)


def _handle_serve_report(filename: str):
    """预览/下载产物（route ``<path:filename>`` → 参数名 filename）。

    扩展名白名单先拦（防 .HTML/.XLSX 大小写绕过）；``send_from_directory``
    内置 ``..`` 净化（§6.2 防路径穿越）。
    """
    from src.python.config import get_config

    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    if ext not in _ALLOWED_REPORT_EXT:
        return _err("BAD_PARAM", "不支持的文件类型"), 400
    config = get_config()
    output_dir = config.get("output_dir", "reports")
    return send_from_directory(output_dir, filename)


def _handle_health():
    from src.python.core.check_sources import run_health_checks

    now = time.time()
    if _health_cache["data"] is not None and now - _health_cache["ts"] < 60:
        return _ok(_health_cache["data"])
    results = run_health_checks(max_timeout=8.0)
    _health_cache["ts"] = now
    _health_cache["data"] = results
    return _ok(results)


# ── 路由注册 ─────────────────────────────────────────


def create_handlers(app, run_manager) -> None:
    """注册全部 HTTP 路由。

    注意：``/api/runs/history`` 必须先于 ``/api/runs/<run_id>`` 注册
    （run_id 为 token 字符串，否则 history 会被当作 run_id 捕获）。
    """
    app.add_url_rule("/", "index", _handle_index)

    app.add_url_rule("/api/upload", "upload", _handle_upload, methods=["POST"])

    app.add_url_rule("/api/runs", "create_run", lambda: _handle_create_run(run_manager), methods=["POST"])
    app.add_url_rule("/api/runs", "list_runs", lambda: _handle_list_runs(run_manager), methods=["GET"])
    # 静态历史路由必须先注册
    app.add_url_rule("/api/runs/history", "run_history", _handle_run_history, methods=["GET"])
    app.add_url_rule(
        "/api/runs/<run_id>", "run_detail", lambda run_id: _handle_run_detail(run_manager, run_id), methods=["GET"]
    )
    app.add_url_rule(
        "/api/runs/<run_id>/events",
        "run_events",
        lambda run_id: _handle_run_events(run_manager, run_id),
        methods=["GET"],
    )

    app.add_url_rule("/api/reports/<path:filename>", "serve_report", _handle_serve_report, methods=["GET"])
    app.add_url_rule("/api/health", "health", _handle_health, methods=["GET"])

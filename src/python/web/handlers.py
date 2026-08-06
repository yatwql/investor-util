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
    严重失败（exit_code 2）或执行失败（failed）时无可用产物，返回空。
    """
    report_type = params.get("report_type", "basic")
    if not state.output_dir:
        return []
    # 严重失败/执行失败：报告未生成，产物按钮无意义（点击只会 404）
    if state.status == "failed" or state.exit_code == _EXIT_SEVERE:
        return []
    artifacts = []
    if report_type in ("both", "full"):
        artifacts.append({"kind": "html", "name": "HTML 报告", "path": _LATEST_HTML})
    artifacts.append({"kind": "xlsx", "name": "Excel 报告", "path": _LATEST_XLSX})
    return artifacts


# ── 系统信息组装（版本 / 机器 IP / LLM 状态，对齐 TUI 状态面板）────────


def _simplify_endpoint(endpoint: str) -> str:
    """简化 endpoint 显示（取 URL 主机名），非 URL 原样返回。

    对齐 TUI ``tui_menu._show_llm_config_status`` 的 endpoint 展示
    （``endpoint.split('/')[2]`` 取主机名），避免页面显示过长 URL。
    """
    if not endpoint or endpoint == "默认":
        return endpoint or "默认"
    if "//" in endpoint:
        parts = endpoint.split("/")
        if len(parts) > 2:
            return parts[2]
    return endpoint


# 状态面板隐藏的 LLM 模块后缀（对齐 tui_menu.LLM_MENU_HIDDEN_KEYS：辩论三模块
# 在注册表保留供缓存 TTL 依赖，但不在状态面板展示，避免误导为可开关模块）。
_LLM_STATUS_HIDDEN_SUFFIXES: frozenset[str] = frozenset({"debate_pro", "debate_con", "debate_synthesis"})


def _build_system_info() -> dict:
    """组装页面状态信息：程序版本号 / 机器 IP / LLM 配置状态。

    复现 TUI 状态面板（``tui_menu._show_llm_config_status`` /
    ``_show_multi_chain_status``）的信息面：
    - flat 单 provider：provider / model / endpoint（简化主机名）/ 熔断 / 模型路由；
    - credentials_ref 多链：策略 / 各 provider（名称/后端/模型/优先级/熔断）/ 模块偏好；
    - 未配置：configured=False（页面按未配置展示）。

    LLM 配置读取失败按未配置兜底，不阻断页面渲染。

    Returns:
        dict，含 app_version / machine_ip / llm（结构化状态）
    """
    from src.python.config import get_llm_config
    from src.python.core.constants import APP_VERSION
    from src.python.core.logger import _get_machine_ip
    from src.python.core.registry import get_llm_module_names
    from src.python.llm.circuit_breaker import get_circuit_status

    info = {
        "app_version": APP_VERSION,
        "machine_ip": _get_machine_ip(),
        "llm": {"configured": False},
    }
    try:
        llm_config = get_llm_config()
    except Exception:
        logger.warning("读取 LLM 配置失败，页面按未配置展示", exc_info=True)
        llm_config = None
    if llm_config is None:
        return info

    provider_list = llm_config.get("_provider_list") or []

    # ── credentials_ref 多链模式 ──
    if provider_list and not llm_config.get("api_key"):
        strategy_labels = {
            "priority": "优先级排序",
            "weighted": "加权随机",
            "cost_first": "价格最低优先",
            "fallback_only": "仅 Fallback",
        }
        strategy_raw = llm_config.get("_strategy", "priority")
        all_creds = llm_config.get("_llm_credentials", {}) or {}
        providers = []
        for entry in provider_list:
            name = entry.get("name", "?")
            backend = entry.get("provider", "?")
            model = entry.get("model", "")
            endpoint = entry.get("endpoint") or ""
            creds_ref = entry.get("credentials_ref")
            if creds_ref and (not model or not endpoint):
                ref_creds = all_creds.get(creds_ref, {})
                if isinstance(ref_creds, dict):
                    if not model:
                        model = ref_creds.get("model", "")
                    if not endpoint:
                        endpoint = ref_creds.get("endpoint", "") or ""
            raw_priority = entry.get("priority")
            providers.append(
                {
                    "name": name,
                    "backend": backend,
                    "model": model or "默认",
                    "endpoint": endpoint,
                    "endpoint_display": _simplify_endpoint(endpoint),
                    "priority": str(raw_priority) if raw_priority is not None else "99（默认）",
                    "circuit": get_circuit_status(endpoint) if endpoint else "—",
                }
            )
        preferred = []
        for mk, pname in (llm_config.get("_preferred_providers", {}) or {}).items():
            preferred.append(f"{get_llm_module_names().get(mk, mk)} → {pname}")
        info["llm"] = {
            "configured": True,
            "mode": "multi",
            "strategy": strategy_labels.get(strategy_raw, strategy_raw),
            "providers": providers,
            "preferred": preferred,
        }
        return info

    # ── 传统 flat 模式：单 provider ──
    if not llm_config.get("api_key") or not llm_config.get("provider"):
        return info

    provider = llm_config["provider"]
    model = llm_config.get("model") or "默认"
    endpoint = llm_config.get("endpoint") or "默认"
    circuit = get_circuit_status(endpoint) if endpoint and endpoint != "默认" else "—"
    route = []
    for sfx, name in get_llm_module_names().items():
        if sfx in _LLM_STATUS_HIDDEN_SUFFIXES:
            continue
        route.append(f"{name}={llm_config.get(f'model_{sfx}') or model}")
    info["llm"] = {
        "configured": True,
        "mode": "flat",
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "endpoint_display": _simplify_endpoint(endpoint),
        "circuit": circuit,
        "route": route,
    }
    return info


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

    from src.python.config import get_config
    from src.python.core.constants import APP_VERSION

    # 表单默认参数在页面加载时取一次 get_config()（页面刷新即重取，
    # 避免页面参数与 run 出队时配置快照时刻不一致）。
    # 历史走势默认跟随配置 fetch_mode（off→关闭；auto/prompt→开启）。
    config = get_config()
    fetch_mode = (config.get("history", {}) or {}).get("fetch_mode") or "auto"
    history_checked = bool(config.get("enable_history", True)) and fetch_mode != "off"
    # 表单说明文案（模板里嵌在复选框 label 括号中，不再重复「历史走势」前缀）
    config_note = "跟随配置开启" if history_checked else "当前配置关闭"
    # 静态资源带版本查询串 ?v={APP_VERSION}（防浏览器缓存旧 JS/CSS 导致功能异常）
    # 状态区系统信息（版本 / 机器 IP / LLM 状态）随页面渲染，对齐 TUI 状态面板
    return render_template(
        "index.html",
        app_version=APP_VERSION,
        history_checked=history_checked,
        config_note=config_note,
        system_info=_build_system_info(),
    )


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

    # 默认走 60s 缓存（防轮询/频繁刷页触发真实探测）；?fresh=1 强制重测
    # （健康页「重新检测」按钮用，用户主动动作不计入缓存污染）
    fresh = request.args.get("fresh") == "1"
    now = time.time()
    if not fresh and _health_cache["data"] is not None and now - _health_cache["ts"] < 60:
        return _ok(_health_cache["data"])
    # 整体预算必须低于前端 /api/health 的 15s abort（留余量）。
    # 12s 覆盖正常网络下的全量检查（实测 ~10s），仅切断真正挂起的检查项，
    # 未完成项由 run_health_checks 标记"超时"返回，避免整接口超时被前端判失败。
    results = run_health_checks(max_timeout=12.0)
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

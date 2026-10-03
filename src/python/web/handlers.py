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
import threading
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

# 短缓存（健康 60s / 历史 5s）——防频繁轮询重复读文件/重复真实探测。
# 并发边界（rf-528）：server 为 threaded=True，两 dict 的读写由同一把锁保护——
# 锁只保护「读缓存/写缓存」两段，真实计算在锁外；两请求同时 miss 时可能重
# 复计算一次（本地单人 Web 的低风险余量，不引入检查时间内串行化代价）。
_health_cache: dict = {"ts": 0.0, "data": None}
_history_cache: dict = {"ts": 0.0, "data": None}
_render_cache_lock = threading.Lock()


# ── 响应信封辅助 ─────────────────────────────────────


def _ok(data):
    return {"ok": True, "data": data}


def _err(error_code, message):
    return {"ok": False, "error_code": error_code, "error": message}


# ── worker 执行体（RunManager.executor 注入点）────────────────


def _web_input_mode_snapshot_domain(mode: str) -> str | None:
    """生成用途（web 输入模式）→ 快照隔离域：试算→web 试算域 / 正式→共享主目录。

    模式与快照隔离域映射的唯一事实来源（语义名即代码名），避免散落多处。
    试算（trial）：快照隔离到 ``web/`` 域，不污染共享时间线；
    正式（formal）：快照写共享主目录（返回 None = 默认共享域）。
    """
    return "web" if mode == "trial" else None


def _run_generation(state, params: dict) -> int:
    """单个 run 的执行体：读持仓 → 建 reporter → generate_report → 映射退出码。

    在 worker 线程执行。每个 run 启动时取一次 ``get_config()`` 快照
    （run 期间不受外部配置修改影响）；产物 output_dir 基于该快照
    保存到 run 记录（产物 URL/下载基于 run 记录而非实时配置）。
    上传临时文件在 finally 中立即删除（§6.1 清理）。

    输入模式分派（试算隔离 vs 正式共享）：
      - 试算（trial，默认）：读上传临时文件，快照写 ``web/`` 隔离域
        （``snapshot_namespace="web"``），不落正式持仓、不写共享快照。
      - 正式（formal）+ 上传：先 ``promote_upload_to_holdings`` 提升临时文件
        为正式持仓（备份旧文件为 .bak），读正式文件，快照写共享主目录。
      - 正式（formal）+ 用存量（use_existing）：直接读正式持仓文件
        （路径仅从 ``get_config()`` 派生，无目录穿越向量），快照写共享主目录。
    正式模式的提升发生在 run 出队后、生成前——报告后续失败（LLM/网络）
    不影响已提交的正式文件（正式模式语义，UI/文档已说明）。
    """
    from src.python.config import get_config
    from src.python.core.reader import read_holdings_with_flows
    from src.python.report.orchestrator import generate_report

    from src.python.web.holdings_update import promote_upload_to_holdings
    from src.python.web.progress import WebProgressReporter
    from src.python.web.upload import discard_file, resolve_file

    mode = params.get("mode", "trial")
    use_existing = bool(params.get("use_existing", False))
    file_id = params.get("file_id")

    try:
        # 每个 run 启动取一次配置快照（run 期间不受外部配置修改影响）
        config = get_config()
        # 输入模式 → 快照隔离域（试算→web/ 正式→共享主目录），单一来源
        snapshot_namespace = _web_input_mode_snapshot_domain(mode)

        # ── 按模式解析持仓来源与快照隔离域 ──
        if mode == "formal":
            holdings_dir = config.get("holdings_dir") or ""
            holdings_name = config.get("holdings_filename") or ""
            formal_path = os.path.join(holdings_dir, holdings_name) if holdings_dir and holdings_name else None
            if use_existing:
                # 正式 + 用存量：直接读正式文件（路径仅从配置派生）
                if formal_path is None or not os.path.isfile(formal_path):
                    shown = formal_path or "（未配置 holdings_dir/holdings_filename）"
                    state.errors.append(f"正式持仓文件不存在：{shown}。请先在正式模式上传覆盖，或改用临时试算")
                    return _EXIT_SEVERE
                holdings_path = formal_path
            else:
                # 正式 + 上传：出队后先提升为正式文件（备份旧文件），再读正式路径
                path = resolve_file(file_id) if file_id else None
                if path is None:
                    state.errors.append("上传文件已过期，请重新上传")
                    return _EXIT_SEVERE
                if formal_path is None:
                    state.errors.append("未配置正式持仓文件路径（holdings_dir/holdings_filename）")
                    return _EXIT_SEVERE
                promote_upload_to_holdings(path, formal_path)
                holdings_path = formal_path
        else:
            # 试算（默认）：读上传临时文件，快照隔离到 web/ 域
            path = resolve_file(file_id) if file_id else None
            if path is None:
                state.errors.append("上传文件已过期，请重新上传")
                return _EXIT_SEVERE
            holdings_path = path

        parsed = read_holdings_with_flows(holdings_path)
        holdings = parsed.holdings
        if not holdings:
            state.errors.append("持仓文件为空或格式异常")
            return _EXIT_SEVERE

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
            snapshot_namespace=snapshot_namespace,
        )
        from src.python.config import get_default

        state.output_dir = config.get("output_dir") or get_default("output_dir")
        state.errors = list(result.errors)
        return result.exit_code
    except Exception:
        logger.exception("[web-run] run %s 生成异常", state.run_id)
        state.errors.append("生成任务执行异常（详情请查看日志）")
        return _EXIT_SEVERE
    finally:
        # 试算 / 正式-上传携带 file_id → 清理上传临时文件（正式文件本体保留；
        # promote 为 copy，临时文件生命周期不变，仍由这里统一清理）
        if file_id:
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


def _build_system_info() -> dict:
    """组装页面状态信息——委托共享层 core.system_info.build_system_info。

    共享单源：版本/机器IP/持仓输出摘要/匿名化/隐私提示/自检开关/LLM（含多链
    provider 链路）状态；TUI ``tui_menu`` 展示同一组原语，渠道层只做传输封装。
    """
    from src.python.core.system_info import build_system_info

    return build_system_info()


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
    from src.python.core.constants import APP_NAME, APP_VERSION

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
        app_name=APP_NAME,
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
    mode = payload.get("mode", "trial")
    use_existing = payload.get("use_existing", False)

    # 枚举校验（BAD_PARAM）
    if report_type not in ("basic", "both", "full"):
        return _err("BAD_PARAM", "报告格式不合法（basic/both/full）"), 400
    if fetch_history is not None and not isinstance(fetch_history, bool):
        return _err("BAD_PARAM", "历史走势参数不合法"), 400
    if not isinstance(force_llm, bool):
        return _err("BAD_PARAM", "强制 LLM 参数不合法"), 400
    if mode not in ("trial", "formal"):
        return _err("BAD_PARAM", "生成用途不合法（trial/formal）"), 400
    if not isinstance(use_existing, bool):
        return _err("BAD_PARAM", "输入来源参数不合法"), 400

    # 模式 × 输入来源组合校验：
    #   - 正式 + 用存量：无需上传（不携带 file_id），读正式持仓文件
    #   - 其余（试算 / 正式 + 上传）：必须有合法未过期 file_id
    if mode == "formal" and use_existing:
        if isinstance(file_id, str) and file_id:
            return _err("BAD_PARAM", "正式-用存量模式下无需上传文件（请勿携带 file_id）"), 400
    else:
        if not isinstance(file_id, str) or not file_id:
            return _err("BAD_PARAM", "缺少 file_id"), 400
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
            "mode": mode,
            "use_existing": use_existing,
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
    with _render_cache_lock:
        if _history_cache["data"] is not None and now - _history_cache["ts"] < 5:
            return _ok(_history_cache["data"])
    records = load_history()
    with _render_cache_lock:
        _history_cache["ts"] = now
        _history_cache["data"] = records
    return _ok(records)


# ── 调仓 What-if 模拟（同步执行，独立产物）────────────────

# 同一时刻仅允许一个模拟（threaded 服务器下防止双写同名「调仓模拟.*」产物）
_whatif_lock = threading.Lock()


def _handle_whatif():
    """调仓 What-if 模拟（POST /api/whatif，副作用，同源守卫）。

    payload：
      - candidate_file_id（必填）：目标持仓（调仓后/假设）上传 file_id
      - base_file_id（可选）：基准持仓上传 file_id；缺省走 use_existing
      - use_existing（默认 True）：无 base_file_id 时用配置默认持仓文件
      - effective_date（可选 YYYY-MM-DD）：指定后追加时序回测（opt-in 联网）

    全程同步执行（本地计算，与 CLI/TUI 同链 run_whatif_simulation），
    成功返回产物 basename，前端经 /api/reports/<filename> 预览下载。
    """
    from src.python.config import get_config
    from src.python.core.reader import read_holdings
    from src.python.report.whatif_operations import run_whatif_simulation
    from src.python.web.upload import resolve_file

    payload = request.get_json(silent=True) or {}
    candidate_file_id = payload.get("candidate_file_id")
    base_file_id = payload.get("base_file_id")
    use_existing = payload.get("use_existing", True)
    effective_date = payload.get("effective_date")

    # ── 参数校验（BAD_PARAM）──
    if not isinstance(candidate_file_id, str) or not candidate_file_id:
        return _err("BAD_PARAM", "缺少目标持仓 file_id"), 400
    if base_file_id is not None and (not isinstance(base_file_id, str) or not base_file_id):
        return _err("BAD_PARAM", "基准持仓 file_id 不合法"), 400
    if not isinstance(use_existing, bool):
        return _err("BAD_PARAM", "输入来源参数不合法"), 400
    if effective_date is not None and not isinstance(effective_date, str):
        return _err("BAD_PARAM", "生效日格式不合法"), 400
    # 格式校验/归一化委托共享层 normalize_effective_date（与 CLI/TUI 同一规则）
    from src.python.report.whatif_operations import normalize_effective_date

    try:
        effective_date = normalize_effective_date(effective_date)
    except ValueError as e:
        return _err("BAD_PARAM", str(e)), 400
    # 副作用操作轻量同源校验
    if not _is_same_origin():
        return _err("BAD_PARAM", "同源校验失败，拒绝提交"), 403

    # ── 文件来源解析（上传过期 → FILE_EXPIRED 404）──
    candidate_path = resolve_file(candidate_file_id)
    if candidate_path is None:
        return _err("FILE_EXPIRED", "目标持仓文件已过期，请重新上传"), 404

    if base_file_id:
        base_path = resolve_file(base_file_id)
        if base_path is None:
            return _err("FILE_EXPIRED", "基准持仓文件已过期，请重新上传"), 404
    elif use_existing:
        from src.python.config import resolve_holdings_path

        base_path = resolve_holdings_path()
    else:
        return _err("BAD_PARAM", "缺少基准持仓来源"), 400

    # ── 读取两侧持仓（空/读失败 → 422，对齐 CLI 退出码语义）──
    base_holdings = read_holdings(base_path)
    cand_holdings = read_holdings(candidate_path)
    if not base_holdings:
        return _err("WHATIF_UNAVAILABLE", f"基准持仓读取失败或为空: {os.path.basename(base_path)}"), 422
    if not cand_holdings:
        return _err("WHATIF_UNAVAILABLE", f"目标持仓读取失败或为空: {os.path.basename(candidate_path)}"), 422

    # ── 互斥执行（忙碌 → 429）──
    if not _whatif_lock.acquire(blocking=False):
        return _err("WHATIF_BUSY", "已有调仓模拟在执行，请稍后再试"), 429
    try:
        from src.python.config import get_default

        output_dir = get_config().get("output_dir") or get_default("output_dir")
        result = run_whatif_simulation(
            base_holdings,
            cand_holdings,
            base_file=base_path,
            candidate_file=candidate_path,
            output_dir=output_dir,
            reporter=None,
            effective_date=effective_date,
        )
    except Exception:
        logger.exception("调仓 What-if 模拟执行异常")
        return _err("WHATIF_FAILED", "调仓模拟执行异常，请查看日志"), 500
    finally:
        _whatif_lock.release()

    if not result.ok:
        return _err("WHATIF_UNAVAILABLE", f"调仓对比数据不可用: {result.reason}"), 422
    return _ok(
        {
            "excel": os.path.basename(result.excel),
            "html": os.path.basename(result.html),
            "base_count": len(base_holdings),
            "candidate_count": len(cand_holdings),
        }
    )


# ── 缓存管理（统计 + 清理过期）──────────────────────────


def _handle_cache_stats():
    """缓存统计（GET /api/cache，只读）：总量/前缀分布/命中率/过期预估。

    结构化载荷由 ``cache.operations.get_cache_stats_payload`` 单源组装（保序
    数组、top 截断、命中率与过期预估），Web 侧只做传输封装。
    """
    from src.python.cache.operations import get_cache_stats_payload

    return _ok(get_cache_stats_payload())


def _handle_cache_cleanup():
    """清理过期缓存（POST /api/cache/cleanup，副作用，同源守卫）。

    与 TUI `[3]` 同链（cache.cleanup_expired），仅删 TTL 已过期文件；
    有效缓存不受影响，下次读取按需重建。
    """
    from src.python.cache import cleanup_expired

    if not _is_same_origin():
        return _err("BAD_PARAM", "同源校验失败，拒绝提交"), 403
    removed = cleanup_expired(dry_run=False)
    return _ok({"removed": removed})


def _handle_config_edit():
    """配置编辑：GET 返回可编辑面，POST 应用单次编辑（副作用，同源守卫）。

    POST 校验失败（未知键/类型/枚举/action 非法）→ 400 BAD_PARAM；
    写共享配置异常 → 500 CONFIG_WRITE_FAILED（详情记日志，前端不泄露内部细节）。
    """
    from src.python.web.config_edit import ConfigEditError, apply_config_edit, get_config_edit_surface

    if request.method == "POST":
        if not _is_same_origin():
            return _err("BAD_PARAM", "同源校验失败，拒绝提交"), 403
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return _err("BAD_PARAM", "请求体格式不合法"), 400
        try:
            data = apply_config_edit(payload)
        except ConfigEditError as e:
            return _err("BAD_PARAM", str(e)), 400
        except Exception:
            logger.exception("[config-edit] 配置写入失败")
            return _err("CONFIG_WRITE_FAILED", "配置写入失败（详情请查看日志）"), 500
        return _ok(data)
    return _ok(get_config_edit_surface())


def _handle_serve_report(filename: str):
    """预览/下载产物（route ``<path:filename>`` → 参数名 filename）。

    扩展名白名单先拦（防 .HTML/.XLSX 大小写绕过）；``send_from_directory``
    内置 ``..`` 净化（§6.2 防路径穿越）。
    """
    from src.python.config import get_default, get_config

    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    if ext not in _ALLOWED_REPORT_EXT:
        return _err("BAD_PARAM", "不支持的文件类型"), 400
    config = get_config()
    output_dir = config.get("output_dir") or get_default("output_dir")
    return send_from_directory(output_dir, filename)


def _handle_health():
    from src.python.core.check_sources import run_health_checks

    # 默认走 60s 缓存（防轮询/频繁刷页触发真实探测）；?fresh=1 强制重测
    # （健康页「重新检测」按钮用，用户主动动作不计入缓存污染）
    fresh = request.args.get("fresh") == "1"
    now = time.time()
    if not fresh:
        with _render_cache_lock:
            if _health_cache["data"] is not None and now - _health_cache["ts"] < 60:
                return _ok(_health_cache["data"])
    # 整体预算必须低于前端 /api/health 的 15s abort（留余量）。
    # 12s 覆盖正常网络下的全量检查（实测 ~10s），仅切断真正挂起的检查项，
    # 未完成项由 run_health_checks 标记"超时"返回，避免整接口超时被前端判失败。
    results = run_health_checks(max_timeout=12.0)
    with _render_cache_lock:
        _health_cache["ts"] = now
        _health_cache["data"] = results
    return _ok(results)


def _handle_doctor():
    """GET /api/doctor — 系统自检（doctor_check 开关门控，默认开启）。

    查询参数：
      network — ``0`` 跳过数据源联网检查（默认 1，含网络检查）

    与 /api/health 的分工：health 只探测数据源；doctor 还覆盖环境/配置/目录，
    故不与其共享缓存（doctor 的本地项是廉价的，网络项复用 health 的 60s 缓存
    并不成立——两者预算不同）。

    Returns:
        {results: [...], ok_count: int, bad_count: int}
        每项含 group / label / ok / message / hint。
    """
    from src.python.core.doctor import run_doctor_checks, summarize_doctor_results

    include_network = request.args.get("network", "1") != "0"
    _MAX_TIMEOUT_CEILING = 15.0
    try:
        timeout = min(float(request.args.get("timeout", 12.0)), _MAX_TIMEOUT_CEILING)
    except (TypeError, ValueError):
        timeout = 12.0

    # 整体预算低于前端 abort 阈值（留余量），未完成项由 run_health_checks 标"超时"
    results = run_doctor_checks(include_network=include_network, max_timeout=max(timeout, 1.0))
    ok_count, bad_count = summarize_doctor_results(results)
    return _ok({"results": results, "ok_count": ok_count, "bad_count": bad_count})


def _handle_logs():
    """GET /api/logs — 结构化日志查看（日志可视化）。

    查询参数：
      level  — 最小级别阈值（DEBUG/INFO/WARNING/ERROR/CRITICAL，非法值 → 400）
      lines  — 尾部读取物理行数（默认 5000，clamp [1,5000]，防大日志卡顿）
      since/until — 时间前缀过滤（透传核心层）
    所有解析/过滤/尾部读取逻辑委托核心层 read_log()，本 handler 仅做
    参数校验与 JSON 渲染。
    """
    from src.python.core.log_reader import LOG_LEVELS, read_log

    level = request.args.get("level")
    if level is not None and level not in LOG_LEVELS:
        return _err("BAD_PARAM", f"无效日志级别: {level}"), 400

    raw_lines = request.args.get("lines", "5000")
    try:
        lines = int(raw_lines)
    except (TypeError, ValueError):
        return _err("BAD_PARAM", f"无效 lines 参数: {raw_lines}"), 400
    lines = max(1, min(lines, 5000))

    since = request.args.get("since")
    until = request.args.get("until")

    try:
        entries = read_log(limit=lines, level=level, since=since, until=until)
    except (ValueError, OSError):
        logger.exception("[logs] 读取运行日志失败")
        return _err("LOG_READ_FAILED", "读取运行日志失败（详情请查看日志）"), 500

    return _ok([e.to_dict() for e in entries])


def _handle_health_history():
    """GET /api/health/history — 数据源健康历史摘要（最近 10 次）。

    与 /api/health（实时探测）解耦：本接口只读历史快照文件（零网络探测），
    聚合逻辑委托核心层 summarize_health_history()。
    """
    from src.python.core.perf import summarize_health_history

    try:
        summaries = summarize_health_history(limit=10)
    except OSError:
        logger.exception("[health] 读取健康历史失败")
        return _err("HEALTH_HISTORY_READ_FAILED", "读取健康历史失败（详情请查看日志）"), 500

    return _ok(summaries)


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
    app.add_url_rule("/api/whatif", "whatif", _handle_whatif, methods=["POST"])
    app.add_url_rule("/api/cache", "cache_stats", _handle_cache_stats, methods=["GET"])
    app.add_url_rule("/api/cache/cleanup", "cache_cleanup", _handle_cache_cleanup, methods=["POST"])
    app.add_url_rule("/api/health", "health", _handle_health, methods=["GET"])
    app.add_url_rule("/api/health/history", "health_history", _handle_health_history, methods=["GET"])
    app.add_url_rule("/api/doctor", "doctor", _handle_doctor, methods=["GET"])
    app.add_url_rule("/api/logs", "logs", _handle_logs, methods=["GET"])

    app.add_url_rule("/api/config/edit", "config_edit", _handle_config_edit, methods=["GET", "POST"])

"""Web 应用工厂 — create_app() 可测试应用。

职责：
  - 支持注入 run_manager（默认全局单例，测试传内存 fake 免 patch 全局）
  - 路由注册（委托 handlers.create_handlers）
  - 统一 JSON 错误处理：500 → {"ok": false, "error": "服务器内部错误"}
    （记录 error 日志，不泄绝对路径）；413 → 中文上传超限提示；
    404 → 中文接口不存在提示。
  - before_request 生成 request_id 注入日志（请求可关联到 run，错误定位）；
    after_request 记一行访问日志（method/path/status/耗时，**不记录**上传
    文件名、持仓内容、绝对路径全文——日志隐私边界）。
  - 关闭 werkzeug 默认访问日志（统一走 invest logger，禁止双通道）。
"""

from __future__ import annotations

import logging
import os
import time
from uuid import uuid4

from flask import Flask, g, request

from src.python.core.constants import PROJECT_ROOT
from src.python.web.handlers import _err, _run_generation, create_handlers
from src.python.web.upload import _MAX_BYTES

logger = logging.getLogger("invest")

# Web UI 前端目录：Jinja 模板 + 静态资产统一归 src/static/web/（与报告模板同属前端资源）
_WEB_FRONTEND_DIR = os.path.join(PROJECT_ROOT, "src", "static", "web")


def create_app(run_manager=None) -> Flask:
    """创建 Flask 应用。

    Args:
        run_manager: RunManager 实例；为 None 时用全局单例（默认）。
            测试可传入内存 fake 以避免 patch 全局。
    """
    from src.python.web.runs import get_run_manager

    if run_manager is None:
        run_manager = get_run_manager()
    # 执行器未注入时绑定 Web 生成执行体（测试传 fake executor 则不动）
    if run_manager.executor is None:
        run_manager.executor = _run_generation

    app = Flask(
        __name__,
        template_folder=_WEB_FRONTEND_DIR,
        static_folder=_WEB_FRONTEND_DIR,
        # 静态路由固定 /static/*：不显式指定时 Flask 按 static_folder 的 basename
        # 推导 static_url_path（src/static/web/ → /web/*），会导致 index.html 的
        # /static/main.js、/static/style.css 全部 404，前端 JS/CSS 完全失效。
        static_url_path="/static",
    )
    app.config["MAX_CONTENT_LENGTH"] = _MAX_BYTES
    # 中文 JSON 不转义（对齐仓库中文文案惯例）
    app.json.ensure_ascii = False

    # werkzeug 自带访问日志纳入 invest logger 统一通道：调低级别避免双通道噪音
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    create_handlers(app, run_manager)

    @app.before_request
    def _attach_request_id():
        g.request_id = uuid4().hex[:8]

    @app.after_request
    def _log_access(response):
        # 隐私边界：仅记录 method/path/状态/耗时，不记录请求体/文件名/持仓内容
        duration_ms = 0.0
        try:
            duration_ms = (time.perf_counter() - g.get("_start_ts", time.perf_counter())) * 1000
        except Exception:
            pass
        logger.info(
            "[web %s] %s %s -> %s (%dms)",
            getattr(g, "request_id", "-"),
            request.method,
            request.path,
            response.status_code,
            round(duration_ms, 1),
        )
        return response

    @app.before_request
    def _mark_start_ts():
        g._start_ts = time.perf_counter()

    # ── 统一 JSON 错误处理 ──
    @app.errorhandler(413)
    def _too_large(_e):
        logger.warning("[web %s] 上传超过 10MB 上限", getattr(g, "request_id", "-"))
        return _err("UPLOAD_TOO_LARGE", "文件超过 10MB 上限"), 413

    @app.errorhandler(404)
    def _not_found(_e):
        return _err("NOT_FOUND", "接口不存在"), 404

    @app.errorhandler(500)
    def _server_error(e):
        # 记录详细 error 日志（含堆栈），但响应不回显绝对路径/内部细节
        logger.exception("[web %s] 服务器内部错误: %s", getattr(g, "request_id", "-"), e)
        return _err("SERVER_ERROR", "服务器内部错误"), 500

    return app

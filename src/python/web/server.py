#!/usr/bin/env python3
"""Web 服务主入口 — sys.path 注入 + main() + 端口检测 + app.run。

启动方式：
  python -m src.python.web             # 模块入口（对齐 cli/tui）
  python src/python/web/server.py      # 直接执行（launch.sh web）

参数：
  --host 默认本机回环    监听地址（默认仅本机；局域网访问显式传全零监听地址）
  --port 8000        监听端口
  --config PATH      备用配置文件路径（默认 data/config/config.json）

端口占用检测：占用则报错并提示换端口，避免服务静默失败/多实例混用产物。
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys

# 确保项目根目录在 sys.path 中（支持直接执行 python src/python/web/server.py）
_src_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_src_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logger = logging.getLogger("invest")


def _port_in_use(host: str, port: int) -> bool:
    """检测端口是否已被占用（bind 探测，立即释放）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return False
        except OSError:
            return True


def main() -> int:
    """Web 服务主入口。"""
    from src.python.core.logger import log_app_boundary, setup_logger

    parser = argparse.ArgumentParser(
        prog="investor-util-web",
        description="个人投资分析报告生成工具 — 轻量 Web 模式",
        epilog="示例: python -m src.python.web --host 127.0.0.1 --port 8000",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1；局域网访问显式用 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--config", metavar="PATH", help="备用配置文件路径（默认: data/config/config.json）")
    args = parser.parse_args()

    setup_logger()
    log_app_boundary("启动", "Web模式")

    from src.python.config import init_config

    init_config(config_path=args.config)

    # 端口占用检测：占用则报错并提示换端口，避免多实例混用产物
    if _port_in_use(args.host, args.port):
        logger.error("端口 %s:%d 已被占用，请换端口（--port）后重试", args.host, args.port)
        return 2

    from src.python.web.app import create_app
    from src.python.web.runs import get_run_manager
    from src.python.web.upload import cleanup_all

    run_manager = get_run_manager()
    app = create_app(run_manager)

    # 启动时清理全部残留上传文件（§6.1：残留由启动清理兜底）
    cleanup_all()

    if args.host in ("0.0.0.0", "::"):
        logger.warning("Web 服务监听 %s —— 局域网可访问，请仅限可信网络（无内建认证）", args.host)
    logger.info("Web 服务已启动: http://127.0.0.1:%d （Ctrl+C 退出）", args.port)
    # 生成线程 daemon=True：Ctrl+C 时进程可正常退出（进行中任务丢弃）
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    from src.python.core.logger import log_app_boundary

    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log_app_boundary("关闭", "Web模式")
        sys.exit(130)
    except Exception:
        logger.exception("Web 未处理异常")
        log_app_boundary("关闭", "Web模式")
        sys.exit(2)

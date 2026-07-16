#!/usr/bin/env python3
"""CLI 命令行模式 — argparse 主入口。

支持 report 和 cache 子命令，共享 P1 已提取的业务编排层。
"""
from __future__ import annotations

import argparse
import os
import sys

# 确保项目根目录在 sys.path 中，并切换工作目录
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
os.chdir(_project_root)

from src.python.constants import APP_VERSION


# ── 退出码 ───────────────────────────────────────────────

_EXIT_SUCCESS = 0
_EXIT_PARTIAL = 1
_EXIT_SEVERE = 2


# ── argparse 解析器 ─────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """构建 argparse 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="investor-util",
        description="个人投资分析报告生成工具 — 命令行模式",
        epilog="示例: python -m src.python.cli report --type full --history auto",
    )

    # 全局参数
    parser.add_argument("--config", metavar="PATH",
                        help="备用配置文件路径（默认: data/config/config.json）")
    parser.add_argument("--output", metavar="DIR",
                        help="报告输出目录（覆盖 config.json 的 output_dir）")
    parser.add_argument("--verbose", action="store_true",
                        help="将进度消息同步到 stderr（默认仅写入 logs/app.log）")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s v{APP_VERSION}")

    sub = parser.add_subparsers(dest="command", required=True)

    # ── report 子命令 ──
    report_p = sub.add_parser("report", help="生成投资分析报告")
    report_p.add_argument(
        "--type", choices=["basic", "both", "full"], default="basic",
        help="报告类型: basic=仅Excel(≈1min, 默认), both=HTML+Excel(不含LLM,≈2min), "
             "full=全量含LLM(≈5min, 定时任务按需开启)",
    )
    report_p.add_argument(
        "--history", choices=["auto", "off"], default="off",
        help="获取组合历史走势数据: auto=获取, off=跳过（默认; 仅 --type both/full 时有效）",
    )
    report_p.add_argument("--force-llm", action="store_true",
                          help="强制重新生成 LLM 内容（跳过缓存）")
    report_p.add_argument("--warm", action="store_true",
                          help="预热新资产缓存（冷启动时使用）")

    # ── cache 子命令 ──
    cache_p = sub.add_parser("cache", help="缓存管理")
    cache_action = cache_p.add_mutually_exclusive_group(required=True)
    cache_action.add_argument("--update", choices=["basic", "position", "all"],
                              help="更新缓存: basic=基础类, position=持仓类, all=全部")
    cache_action.add_argument("--clean", action="store_true",
                              help="清理过期缓存文件")
    cache_action.add_argument("--stats", action="store_true",
                              help="查看缓存文件统计/状态")
    cache_p.epilog = (
        "示例:\n"
        "  cache --update all             更新全部缓存\n"
        "  cache --update basic           仅更新基础类缓存\n"
        "  cache --clean                  清理过期缓存\n"
        "  cache --stats                  查看缓存统计"
    )

    return parser


# ── 子命令处理器（C1 占位，后续轮次逐步实现）───────────


def _handle_report(args: argparse.Namespace, config: dict) -> int:
    """处理 report 子命令。"""
    print(f"[..] report 子命令 — 占位处理（--type={args.type}, "
          f"--history={args.history}, --force-llm={args.force_llm}, "
          f"--warm={args.warm}, --output={args.output})")
    return _EXIT_SUCCESS


def _handle_cache(args: argparse.Namespace, config: dict) -> int:
    """处理 cache 子命令。"""
    if args.clean:
        print("[..] cache --clean 占位处理")
        return _EXIT_SUCCESS
    if args.stats:
        print("[..] cache --stats 占位处理")
        return _EXIT_SUCCESS
    if args.update:
        print(f"[..] cache --update {args.update} 占位处理")
        return _EXIT_SUCCESS
    return _EXIT_SEVERE


# ── 主入口 ───────────────────────────────────────────────


def main() -> int:
    """CLI 主入口。

    Returns:
        int 退出码（0=成功, 1=部分失败, 2=严重错误）
    """
    from src.python.logger import setup_logger, log_app_boundary
    setup_logger()
    log_app_boundary("启动", "CLI模式")

    parser = _build_parser()
    args = parser.parse_args()

    from src.python.config import init_config, get_config
    init_config(config_path=args.config)
    config = get_config()

    if args.command == "report":
        return _handle_report(args, config)
    elif args.command == "cache":
        return _handle_cache(args, config)
    return _EXIT_SEVERE


if __name__ == "__main__":
    from src.python.logger import log_app_boundary
    try:
        sys.exit(main())
    except SystemExit:
        # 正常退出路径
        log_app_boundary("关闭", "CLI模式")
        raise
    except KeyboardInterrupt:
        import logging
        logging.getLogger("invest").info("CLI 操作被用户中断")
        log_app_boundary("关闭", "CLI模式")
        sys.exit(130)
    except Exception:
        import logging
        logging.getLogger("invest").exception("CLI 未处理异常")
        log_app_boundary("关闭", "CLI模式")
        sys.exit(2)

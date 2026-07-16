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


# ── 子命令处理器 ───────────────────────────────────────


def _cli_read_holdings(config: dict) -> list | None:
    """CLI 模式读取持仓——跳过文件选择交互，通过 config 配置定位文件。

    Args:
        config: 配置字典（需含 holdings_dir 和 holdings_filename）

    Returns:
        持仓列表，文件不存在或格式异常时返回 None
    """
    import logging
    logger = logging.getLogger("invest")

    holdings_dir = config.get("holdings_dir", "data/holdings")
    holdings_filename = config.get("holdings_filename", "个人投资持仓信息.xlsx")
    filepath = os.path.join(holdings_dir, holdings_filename)

    if not os.path.exists(filepath):
        logger.error(
            "持仓文件不存在（路径: %s）—— 请检查 config.json 中 "
            "holdings_dir + holdings_filename 配置", filepath,
        )
        return None

    from src.python.reader import list_xlsx_files, read_holdings

    # 如果 holdings_filename 实际是一个目录，自动选第一个 xlsx 文件
    if os.path.isdir(filepath):
        xlsx_files = list_xlsx_files(filepath)
        if not xlsx_files:
            logger.error("持仓目录 %s 中找不到 .xlsx 文件", filepath)
            return None
        if len(xlsx_files) > 1:
            logger.warning("持仓目录 %s 中有多个 .xlsx 文件，自动选择第一个: %s",
                           filepath, xlsx_files[0])
        filepath = xlsx_files[0]

    holdings = read_holdings(filepath)
    if not holdings:
        logger.error(
            "持仓文件为空或格式异常: %s —— "
            "请确保持仓文件包含「名称, 代码, 持仓份额, 每份成本」四列", filepath,
        )
        return None

    logger.info("成功读取持仓文件: %s（共 %d 条记录）", filepath, len(holdings))
    return holdings


def _handle_report(args: argparse.Namespace, config: dict) -> int:
    """处理 report 子命令——委托 orchestrator 共享层。

    支持 --type basic/both/full，通过 generate_report() 统一路由。
    """
    from src.python.report.cli_progress import CliProgressReporter
    from src.python.report.orchestrator import generate_report

    holdings = _cli_read_holdings(config)
    if holdings is None:
        return _EXIT_SEVERE

    reporter = CliProgressReporter(verbose=args.verbose)

    result = generate_report(
        holdings=holdings,
        config=config,
        reporter=reporter,
        report_type=args.type,
        history_mode=args.history,
        force_llm=args.force_llm,
        output_dir=args.output,
        warm_cache=args.warm,
    )

    reporter.print_timing_summary()
    return result.exit_code


def _handle_cache(args: argparse.Namespace, config: dict) -> int:
    """处理 cache 子命令——委托 operations 共享层。

    各缓存操作通过 CliProgressReporter 输出进度，退出码由 operations 结果决定。
    """
    from src.python.cache.operations import (
        cleanup_cache,
        get_cache_stats,
        update_basic_cache,
        update_position_cache,
    )
    from src.python.report.cli_progress import CliProgressReporter

    reporter = CliProgressReporter(verbose=args.verbose)

    if args.clean:
        cleanup_cache(reporter)
        return _EXIT_SUCCESS

    if args.stats:
        get_cache_stats(reporter)
        return _EXIT_SUCCESS

    if args.update:
        return _handle_cache_update(args.update, config, reporter)

    return _EXIT_SEVERE


def _handle_cache_update(update_type: str, config: dict, reporter) -> int:
    """处理 cache --update 子分支。

    --update basic / position / all 均先读取持仓，然后委托 operations。
    --update all 采用最大努力模式：basic 失败后仍继续执行 position，
    最终退出码取两者最大值。
    """
    from src.python.cache.operations import (
        update_basic_cache,
        update_position_cache,
    )

    holdings = _cli_read_holdings(config)
    if holdings is None:
        return _EXIT_SEVERE

    if update_type == "basic":
        result = update_basic_cache(holdings, reporter)
        return result.exit_code

    if update_type == "position":
        result = update_position_cache(holdings, reporter)
        return result.exit_code

    if update_type == "all":
        # 最大努力模式：basic 失败后仍继续执行 position
        basic_result = update_basic_cache(holdings, reporter)
        pos_result = update_position_cache(holdings, reporter)
        return max(basic_result.exit_code, pos_result.exit_code)

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

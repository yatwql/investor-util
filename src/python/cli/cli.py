#!/usr/bin/env python3
"""CLI 命令行模式 — argparse 主入口。

支持 report 和 cache 子命令，共享业务编排层。
"""

from __future__ import annotations

import argparse
import os
import sys

# 确保项目根目录在 sys.path 中（支持直接执行 python src/python/cli/cli.py）
_src_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_src_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.python.core.constants import APP_NAME, APP_VERSION

# ── 退出码 ───────────────────────────────────────────────

_EXIT_SUCCESS = 0
_EXIT_PARTIAL = 1
_EXIT_SEVERE = 2


# ── argparse 解析器 ─────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """构建 argparse 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="investor-util",
        description=f"{APP_NAME} — 命令行模式",
        epilog="示例: python -m src.python.cli report --type full --history auto",
    )

    # 全局参数
    parser.add_argument("--config", metavar="PATH", help="备用配置文件路径（默认: data/config/config.json）")
    parser.add_argument("--output", metavar="DIR", help="报告输出目录（覆盖 config.json 的 output_dir）")
    parser.add_argument("--verbose", action="store_true", help="将进度消息同步到 stderr（默认仅写入 logs/app.log）")
    parser.add_argument("--non-interactive", action="store_true", help="跳过首次运行交互式引导（定时任务/脚本使用）")
    parser.add_argument("--version", action="version", version=f"%(prog)s v{APP_VERSION}")

    sub = parser.add_subparsers(dest="command", required=True)

    # ── report 子命令 ──
    report_p = sub.add_parser("report", help="生成投资分析报告")
    report_p.add_argument(
        "--type",
        choices=["basic", "both", "full"],
        default="basic",
        help="报告类型: basic=仅Excel(≈1min, 默认), both=HTML+Excel(不含LLM,≈2min), "
        "full=全量含LLM(≈5min, 定时任务按需开启)",
    )
    report_p.add_argument(
        "--history",
        choices=["auto", "off"],
        default=None,
        help="获取组合历史走势数据: auto=获取, off=跳过（未指定时按配置 history.fetch_mode，默认 auto；"
        "仅 --type both/full 时有效）",
    )
    report_p.add_argument("--force-llm", action="store_true", help="强制重新生成 LLM 内容（跳过缓存）")

    # ── cache 子命令 ──
    cache_p = sub.add_parser("cache", help="缓存管理")
    cache_action = cache_p.add_mutually_exclusive_group(required=True)
    cache_action.add_argument(
        "--update", choices=["basic", "position", "all"], help="更新缓存: basic=基础类, position=持仓类, all=全部"
    )
    cache_action.add_argument("--clean", action="store_true", help="清理过期缓存文件")
    cache_action.add_argument("--stats", action="store_true", help="查看缓存文件统计/状态")
    cache_p.epilog = (
        "示例:\n"
        "  cache --update all             更新全部缓存\n"
        "  cache --update basic           仅更新基础类缓存\n"
        "  cache --clean                  清理过期缓存\n"
        "  cache --stats                  查看缓存统计"
    )

    # ── whatif 子命令 ──
    whatif_p = sub.add_parser("whatif", help="调仓 What-if 模拟：对比两份持仓生成 diff 报告")
    whatif_p.add_argument("--candidate", metavar="PATH", required=True, help="目标持仓文件（调仓后/假设，必填）")
    whatif_p.add_argument("--base", metavar="PATH", help="基准持仓文件（调仓前）；缺省用 config 配置的持仓文件")
    whatif_p.add_argument(
        "--effective-date",
        metavar="YYYY-MM-DD",
        help="调仓生效日（可选）：指定后 opt-in 联网取生效日后行情，追加时序回测页（区间/年化收益、波动率、夏普、最大回撤）",
    )
    whatif_p.epilog = (
        "示例:\n"
        "  whatif --candidate 调仓后.xlsx              对比当前持仓 vs 目标持仓（成本口径截面比较）\n"
        "  whatif --base 调仓前.xlsx --candidate 调仓后.xlsx   显式指定两份持仓\n"
        "  whatif --candidate 调仓后.xlsx --effective-date 2026-07-01   指定生效日，追加时序回测\n"
        "输出: 调仓模拟.xlsx / .html（最新版固定名，历史归档至日期子目录；默认零网络请求，指定生效日时联网取历史做假设推演，不构成收益承诺）"
    )

    # ── check-sources 子命令 ──
    check_p = sub.add_parser("check-sources", help="数据源健康检查（无需 config）")
    check_p.epilog = "示例:\n  check-sources    测试各数据源联通性"

    # ── view-logs 子命令 ──
    logs_p = sub.add_parser("view-logs", help="查看结构化运行日志（无需 config）")
    logs_p.add_argument(
        "--level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="最小级别阈值（ERROR 含 ERROR+CRITICAL；默认全部）",
    )
    logs_p.add_argument(
        "--lines",
        type=int,
        default=5000,
        help="读取日志末尾物理行数上限（默认 5000，防止大日志卡顿）",
    )
    logs_p.add_argument("--since", metavar="YYYY-MM-DD[ HH:MM:SS]", help="起始时间前缀过滤")
    logs_p.add_argument("--until", metavar="YYYY-MM-DD[ HH:MM:SS]", help="结束时间前缀过滤（含边界）")
    logs_p.epilog = (
        "示例:\n"
        "  view-logs                     查看最近日志\n"
        "  view-logs --level ERROR      只看 ERROR+CRITICAL\n"
        "  view-logs --since 2026-08-16 只看指定日期之后\n"
        "  view-logs --lines 200        只读末尾 200 行"
    )

    return parser


# ── 子命令处理器 ───────────────────────────────────────


def _show_llm_config_status_cli() -> None:
    """CLI 模式显示 LLM 配置状态（含多链详细信息）。"""
    import logging

    logger = logging.getLogger("invest")

    from src.python.config import get_llm_config
    from src.python.llm.circuit_breaker import get_circuit_status
    from src.python.core.registry import get_llm_module_names

    llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM: 未配置（配置 data/config/llm_key.json 或 llm_providers.json 后重启生效）")
        return

    provider_list = llm_config.get("_provider_list") or []

    logger.info("─" * 40)
    logger.info("LLM Provider 状态")

    # ── 多链模式 ──
    if provider_list and not llm_config.get("api_key"):
        strategy_raw = llm_config.get("_strategy", "priority")
        strategy_labels = {
            "priority": "优先级排序",
            "weighted": "加权随机",
            "cost_first": "价格最低优先",
            "fallback_only": "仅 Fallback",
        }
        strategy_label = strategy_labels.get(strategy_raw, strategy_raw)
        logger.info("状态: 已配置 | 策略: %s | 多链服务: %d provider", strategy_label, len(provider_list))

        for i, entry in enumerate(provider_list, 1):
            name = entry.get("name", "?")
            backend = entry.get("provider", "?")

            model = entry.get("model", "")
            endpoint = entry.get("endpoint") or ""
            creds_ref = entry.get("credentials_ref")
            if creds_ref and (not model or not endpoint):
                all_creds = llm_config.get("_llm_credentials", {})
                ref_creds = all_creds.get(creds_ref, {})
                if isinstance(ref_creds, dict):
                    if not model:
                        model = ref_creds.get("model", "")
                    if not endpoint:
                        endpoint = ref_creds.get("endpoint", "") or ""

            model_display = model or "默认"
            raw_priority = entry.get("priority")
            priority_display = str(raw_priority) if raw_priority is not None else "99（默认）"
            cb_status = get_circuit_status(endpoint) if endpoint else "—"

            logger.info("  [%d] %s (%s)", i, name, backend)
            logger.info("      模型: %s    优先级: %s    熔断: %s", model_display, priority_display, cb_status)

        preferred = llm_config.get("_preferred_providers", {})
        if preferred:
            parts = []
            for mk, pname in preferred.items():
                display_name = get_llm_module_names().get(mk, mk)
                parts.append(f"{display_name} → {pname}")
            logger.info("  ▶ 模块偏好: %s", " / ".join(parts))

    # ── 传统 flat 模式 ──
    elif llm_config.get("api_key") and llm_config.get("provider"):
        provider = llm_config["provider"]
        model = llm_config.get("model") or "默认"
        endpoint = llm_config.get("endpoint") or "默认"
        ep_display = (
            endpoint.split("/")[2] if endpoint and endpoint != "默认" and len(endpoint.split("/")) > 2 else endpoint
        )
        cb_status = get_circuit_status(endpoint) if endpoint and endpoint != "默认" else "—"
        logger.info(
            "状态: 已配置 | provider=%s | model=%s | endpoint=%s | 熔断: %s", provider, model, ep_display, cb_status
        )
    else:
        logger.info("状态: 未配置（配置 data/config/llm_key.json 或 llm_providers.json）")

    logger.info("─" * 40)


def _cli_resolve_holdings_file(config: dict) -> str | None:
    """CLI 模式定位持仓文件路径——跳过文件选择交互，通过 config 配置定位。

    Args:
        config: 配置字典（需含 holdings_dir 和 holdings_filename）

    Returns:
        持仓文件路径；文件不存在或目录内无 xlsx 时返回 None
    """
    import logging

    logger = logging.getLogger("invest")

    holdings_dir = config.get("holdings_dir", "data/holdings")
    holdings_filename = config.get("holdings_filename", "个人投资持仓信息.xlsx")
    filepath = os.path.join(holdings_dir, holdings_filename)

    if not os.path.exists(filepath):
        logger.error(
            "持仓文件不存在（路径: %s）—— 请检查 config.json 中 holdings_dir + holdings_filename 配置",
            filepath,
        )
        return None

    from src.python.core.reader import list_xlsx_files

    # 如果 holdings_filename 实际是一个目录，自动选第一个 xlsx 文件
    if os.path.isdir(filepath):
        xlsx_files = list_xlsx_files(filepath)
        if not xlsx_files:
            logger.error("持仓目录 %s 中找不到 .xlsx 文件", filepath)
            return None
        if len(xlsx_files) > 1:
            logger.warning("持仓目录 %s 中有多个 .xlsx 文件，自动选择第一个: %s", filepath, xlsx_files[0])
        filepath = xlsx_files[0]

    return filepath


def _cli_read_holdings(config: dict) -> list | None:
    """CLI 模式读取持仓（主表）——跳过文件选择交互，通过 config 配置定位文件。

    Args:
        config: 配置字典（需含 holdings_dir 和 holdings_filename）

    Returns:
        持仓列表，文件不存在或格式异常时返回 None
    """
    import logging

    logger = logging.getLogger("invest")

    filepath = _cli_resolve_holdings_file(config)
    if filepath is None:
        return None

    from src.python.core.reader import read_holdings

    holdings = read_holdings(filepath)
    if not holdings:
        logger.error(
            "持仓文件为空或格式异常: %s —— 请确保持仓文件包含「名称, 代码, 持仓份额, 每份成本」四列",
            filepath,
        )
        return None

    logger.info("成功读取持仓文件: %s（共 %d 条记录）", filepath, len(holdings))
    return holdings


def _cli_read_holdings_with_flows(config: dict) -> "tuple[list, list, list] | None":
    """CLI 模式读取持仓完整数据（主表 + 可选交易/分红流水页签）。

    Args:
        config: 配置字典（需含 holdings_dir 和 holdings_filename）

    Returns:
        (holdings, transactions, dividends) 三元组；文件不存在或格式异常时返回 None。
        无流水页签时 transactions/dividends 为空列表。
    """
    import logging

    logger = logging.getLogger("invest")

    filepath = _cli_resolve_holdings_file(config)
    if filepath is None:
        return None

    from src.python.core.reader import read_holdings_with_flows

    parsed = read_holdings_with_flows(filepath)
    if not parsed.holdings:
        logger.error(
            "持仓文件为空或格式异常: %s —— 请确保持仓文件包含「名称, 代码, 持仓份额, 每份成本」四列",
            filepath,
        )
        return None

    logger.info(
        "成功读取持仓文件: %s（共 %d 条记录，交易流水 %d 条，分红流水 %d 条）",
        filepath,
        len(parsed.holdings),
        len(parsed.transactions),
        len(parsed.dividends),
    )
    return parsed.holdings, parsed.transactions, parsed.dividends


def _handle_report(args: argparse.Namespace, config: dict) -> int:
    """处理 report 子命令——委托 orchestrator 共享层。

    支持 --type basic/both/full，通过 generate_report() 统一路由。
    """
    from src.python.report.cli_progress import CliProgressReporter
    from src.python.report.orchestrator import generate_report

    parsed = _cli_read_holdings_with_flows(config)
    if parsed is None:
        return _EXIT_SEVERE
    holdings, transactions, dividends = parsed

    reporter = CliProgressReporter(verbose=args.verbose)

    result = generate_report(
        holdings=holdings,
        config=config,
        reporter=reporter,
        report_type=args.type,
        # None（未显式传 --history）→ generate_report 回退到配置层 history.fetch_mode 解析
        fetch_history=args.history,
        force_llm=args.force_llm,
        output_dir=args.output,
        transactions=transactions,
        dividends=dividends,
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
    )
    from src.python.report.cli_progress import CliProgressReporter

    reporter = CliProgressReporter(verbose=args.verbose)

    if args.clean:
        cleanup_cache(reporter)
        return _EXIT_SUCCESS

    if args.stats:
        get_cache_stats(reporter)
        _show_llm_config_status_cli()
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


def _handle_whatif(args: argparse.Namespace, config: dict) -> int:
    """处理 whatif 子命令——调仓 What-if 模拟。

    对比基准（--base，缺省为 config 持仓文件）与目标（--candidate）两份持仓，
    生成调仓 diff 报告（Excel + HTML）。全程本地计算，零网络请求。
    业务链（build→校验→输出）委托共享层 run_whatif_simulation，
    本函数仅保留文件来源解析与退出码映射。
    """
    from src.python.core.reader import read_holdings
    from src.python.report.cli_progress import CliProgressReporter
    from src.python.report.whatif_operations import run_whatif_simulation

    reporter = CliProgressReporter(verbose=args.verbose)

    # ── 基准持仓（--base 或 config 默认）──
    base_file = args.base
    if base_file:
        base_holdings = read_holdings(base_file)
    else:
        base_file = os.path.join(
            config.get("holdings_dir", "data/holdings"),
            config.get("holdings_filename", "个人投资持仓信息.xlsx"),
        )
        base_holdings = _cli_read_holdings(config)
    if not base_holdings:
        reporter.error(f"基准持仓读取失败或为空: {base_file}")
        return _EXIT_SEVERE

    # ── 目标持仓（--candidate，必填）──
    cand_file = args.candidate
    cand_holdings = read_holdings(cand_file)
    if not cand_holdings:
        reporter.error(f"目标持仓读取失败或为空: {cand_file}")
        return _EXIT_SEVERE

    output_dir = args.output or config.get("output_dir", "reports")
    result = run_whatif_simulation(
        base_holdings,
        cand_holdings,
        base_file=base_file,
        candidate_file=cand_file,
        output_dir=output_dir,
        reporter=reporter,
        effective_date=args.effective_date,
    )
    if not result.ok:
        reporter.error(f"调仓对比数据不可用: {result.reason}")
        return _EXIT_SEVERE

    reporter.print_timing_summary()
    return _EXIT_SUCCESS


def _handle_check_sources() -> int:
    """处理 check-sources 子命令——数据源健康检查。

    Returns:
        int 退出码（0=全部正常, 1=有告警, 2=有失败）
    """
    from src.python.core.check_sources import run_check_sources

    run_check_sources()
    return 2  # unreachable, run_check_sources calls sys.exit


def _handle_view_logs(args: argparse.Namespace) -> int:
    """处理 view-logs 子命令——读取结构化运行日志。

    纯命令输出（print），无需 config——配置损坏时仍可查看日志诊断。
    级别/时间过滤与尾部读取逻辑全部委托核心层 read_log()。
    """
    import logging

    from src.python.core.log_reader import read_log

    lines = max(1, args.lines)
    try:
        entries = read_log(limit=lines, level=args.level, since=args.since, until=args.until)
    except (ValueError, OSError):
        logging.getLogger("invest").exception("读取运行日志失败")
        print("[ERR] 读取运行日志失败（详见日志）", file=sys.stderr)
        return _EXIT_SEVERE

    if not entries:
        print("无匹配日志条目")
        return _EXIT_SUCCESS

    level_label = args.level or "全部"
    print(f"=== 运行日志（尾部 {lines} 行，级别: {level_label}）===")
    for entry in entries:
        print(f"{entry.time} [{entry.level}] {entry.message}")
        # 多行 body（traceback 等续行）缩进显示
        for body_line in entry.body.splitlines()[1:]:
            print(f"    {body_line}")
    return _EXIT_SUCCESS


# ── 主入口 ───────────────────────────────────────────────


def main() -> int:
    """CLI 主入口。

    Returns:
        int 退出码（0=成功, 1=部分失败, 2=严重错误）
    """
    from src.python.core.logger import log_app_boundary, setup_logger

    setup_logger()
    log_app_boundary("启动", "CLI模式")

    parser = _build_parser()
    args = parser.parse_args()

    from src.python.config import get_config, init_config

    if args.command == "check-sources":
        return _handle_check_sources()

    # view-logs 无需 config：配置损坏时仍可查看日志诊断
    if args.command == "view-logs":
        return _handle_view_logs(args)

    init_config(config_path=args.config)
    config = get_config()

    # 首次运行引导（非交互/CI/脚本环境自动跳过，不阻塞命令执行）
    try:
        from src.python.startup_wizard import show_startup_wizard_if_needed

        show_startup_wizard_if_needed(non_interactive=args.non_interactive)
    except Exception:
        import logging

        logging.getLogger("invest").debug("首次运行引导显示失败（非关键）", exc_info=True)

    if args.command == "report":
        return _handle_report(args, config)
    elif args.command == "cache":
        return _handle_cache(args, config)
    elif args.command == "whatif":
        return _handle_whatif(args, config)
    return _EXIT_SEVERE


if __name__ == "__main__":
    from src.python.core.logger import log_app_boundary

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

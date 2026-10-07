"""CLI 子命令处理器 —— 各子命令实现、持仓读入辅助与退出码契约。

退出码 ``_EXIT_*`` 在本模块定义（处理器是退出码的生产者），由 ``cli.py``
门面 re-export 给 ``src.python.cli`` 包与外部调用方；``cli.py`` 的 ``main()``
按 ``args.command`` 分派到本模块的 ``_handle_*``。
"""

from __future__ import annotations

import argparse
import os
import sys

# ── 退出码 ───────────────────────────────────────────────

_EXIT_SUCCESS = 0
_EXIT_PARTIAL = 1
_EXIT_SEVERE = 2


# ── 子命令处理器 ───────────────────────────────────────


def _show_llm_config_status_cli() -> None:
    """CLI 模式显示 LLM 配置状态（消费 system_info.llm_status 单源，仅做日志渲染）。"""
    import logging

    logger = logging.getLogger("invest")

    from src.python.core.system_info import llm_status

    llm = llm_status()

    logger.info("─" * 40)
    logger.info("LLM Provider 状态")
    if not llm.get("configured"):
        logger.info("状态: 未配置（配置 data/config/llm_key.json 或 llm_providers.json）")
    elif llm.get("mode") == "multi":
        logger.info("状态: 已配置 | 策略: %s | 多链服务: %d provider", llm["strategy"], len(llm["providers"]))
        for i, p in enumerate(llm["providers"], 1):
            logger.info("  [%d] %s (%s)", i, p["name"], p["backend"])
            logger.info("      模型: %s    优先级: %s    熔断: %s", p["model"], p["priority"], p["circuit"])
        if llm.get("preferred"):
            logger.info("  ▶ 模块偏好: %s", " / ".join(llm["preferred"]))
    else:
        logger.info(
            "状态: 已配置 | provider=%s | model=%s | endpoint=%s | 熔断: %s",
            llm["provider"],
            llm["model"],
            llm["endpoint_display"],
            llm["circuit"],
        )
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

    from src.python.config import resolve_holdings_path

    filepath = resolve_holdings_path(config)

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

    from src.python.core.reader import read_holdings, require_holdings

    holdings = read_holdings(filepath)
    try:
        require_holdings(holdings, filepath)
    except ValueError as e:
        logger.error("%s", e)
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

    from src.python.core.reader import read_holdings_with_flows, require_holdings

    parsed = read_holdings_with_flows(filepath)
    try:
        require_holdings(parsed.holdings, filepath)
    except ValueError as e:
        logger.error("%s", e)
        return None

    logger.info(
        "成功读取持仓文件: %s（共 %d 条记录，交易流水 %d 条，分红流水 %d 条）",
        filepath,
        len(parsed.holdings),
        len(parsed.transactions),
        len(parsed.dividends),
    )
    return parsed.holdings, parsed.transactions, parsed.dividends


def _resolve_source_overrides(args: argparse.Namespace) -> tuple[str | None, tuple[str, ...]]:
    """解析 ``--prefer-source`` / ``--exclude-source``（未知源名即报错退出）。

    取值域由 ``fetcher.chain.known_provider_names()`` 派生（不另写清单）；未知源名
    报错而非静默忽略——否则用户会误以为已生效。multi 首选项取第一个（与
    ``config.preferred_provider`` 的单一首选语义一致）。

    Returns:
        ``(preferred, exclude_tuple)``；未传参时为 ``(None, ())``。

    Raises:
        SystemExit: 传入未知源名时退出（退出码为用法错误）。
    """
    from src.python.fetcher.chain import known_provider_names

    preferred_list = list(getattr(args, "prefer_source", None) or [])
    exclude_list = list(getattr(args, "exclude_source", None) or [])
    if not preferred_list and not exclude_list:
        return None, ()

    known = known_provider_names()
    unknown = [n for n in [*preferred_list, *exclude_list] if n not in known]
    if unknown:
        raise SystemExit(
            "[ERR] 未知数据源: "
            + "、".join(unknown)
            + "\n可用数据源: "
            + "、".join(sorted(known))
            + "\n提示: 源名与 config.json 的 preferred_provider / datasource 路由同名"
        )
    return preferred_list[0], tuple(exclude_list)


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

    # 调用级源覆盖（仅本次运行，不写配置）：排障/评测用（如「只用腾讯源复现」）
    from src.python.fetcher.chain import chain_overrides

    preferred_source, exclude_sources = _resolve_source_overrides(args)

    with chain_overrides(preferred=preferred_source, exclude=exclude_sources):
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
    # 运行收尾资源摘要：LLM 成本 + 缓存命中率（无 LLM 调用/缓存读写时各自静默）
    reporter.print_llm_cost_summary()
    reporter.print_cache_hit_summary()
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
        update_all_cache,
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
        # 最大努力模式（下沉共享层：basic 失败仍继续 position，退出码取两者最大值）
        return update_all_cache(holdings, reporter)

    return _EXIT_SEVERE


def _handle_whatif(args: argparse.Namespace, config: dict) -> int:
    """处理 whatif 子命令——调仓 What-if 模拟。

    对比基准（--base，缺省为 config 持仓文件）与目标（--candidate）两份持仓，
    生成调仓 diff 报告（Excel + HTML）。全程本地计算，零网络请求。
    业务链（build→校验→输出）委托共享层 run_whatif_simulation，
    本函数仅保留文件来源解析与退出码映射。
    """
    from src.python.config import get_default, resolve_holdings_path
    from src.python.core.reader import read_holdings
    from src.python.report.cli_progress import CliProgressReporter
    from src.python.report.whatif_operations import run_whatif_simulation

    reporter = CliProgressReporter(verbose=args.verbose)

    # ── 基准持仓（--base 或 config 默认）──
    base_file = args.base
    if base_file:
        base_holdings = read_holdings(base_file)
    else:
        base_file = resolve_holdings_path(config)
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

    output_dir = args.output or (config.get("output_dir") or get_default("output_dir"))
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


def _use_ansi_color() -> bool:
    """终端是否支持 ANSI 着色（无 TTY / 设了 NO_COLOR / 非 UTF-8 编码时降级）。"""
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return bool(sys.stdout.encoding and sys.stdout.encoding.upper() in ("UTF-8", "UTF8"))


def _handle_doctor(args: argparse.Namespace) -> int:
    """处理 doctor 子命令——系统自检。

    纯只读诊断，不需要 config 初始化：配置损坏正是自检要定位的场景之一。

    Returns:
        int 退出码（_EXIT_SUCCESS=全部通过, _EXIT_PARTIAL=有失败项）。
        自检失败不是命令本身失败——命令跑完了并给出了结论，故用 PARTIAL 而非 SEVERE。
    """
    from src.python.core.doctor import (
        format_doctor_report,
        run_doctor_checks,
        summarize_doctor_results,
    )

    results = run_doctor_checks(include_network=not args.offline, max_timeout=args.timeout)
    print(format_doctor_report(results, use_color=_use_ansi_color()))

    _ok_count, bad_count = summarize_doctor_results(results)
    return _EXIT_PARTIAL if bad_count else _EXIT_SUCCESS


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


def _handle_cassettes(args: argparse.Namespace) -> int:
    """处理 cassettes 子命令——数据源记录-回放维护（只读、离线）。

    纯只读维护命令，与 ``doctor`` 同例：无需 config、不受任何实验开关约束。
    本命令不发起网络请求——``--verify`` 的回放传输在 socket 之前拦截。

    Returns:
        int 退出码（_EXIT_SUCCESS=正常, _EXIT_SEVERE=有录制的解析路径失败）。
    """
    from src.python.core.cassette import CASSETTE_DIR, list_cassettes, verify_cassettes

    entries = list_cassettes()
    if not entries:
        print(f"未找到已录制的数据源响应（目录: {CASSETTE_DIR}）")
        return _EXIT_SUCCESS

    if not args.verify:
        print(f"已录制数据源响应 {len(entries)} 份（{CASSETTE_DIR}）:")
        for entry in entries:
            if "error" in entry:
                print(f"  [ERR] {entry['name']} — {entry['error']}")
                continue
            print(
                f"  {entry['name']}  来源={entry['source'] or '-'}  录制于={entry['recorded_at'] or '-'}"
                f"  交互={entry['interactions']}  大小={entry['size_bytes'] / 1024:.1f} KB"
            )
        return _EXIT_SUCCESS

    from src.python.fetcher.cassette_checks import CASSETTE_CHECKS

    verdicts = verify_cassettes(CASSETTE_CHECKS)
    print(f"离线回放校验 {len(verdicts)} 份数据源响应（不联网，交给当前解析器）：")
    failures = 0
    for verdict in verdicts:
        status = verdict["status"]
        if status == "ok":
            print(f"  [OK] {verdict['name']}（{verdict.get('interactions', 0)} 条交互）")
        elif status == "skipped":
            print(f"  [!] {verdict['name']} — 跳过：{verdict['detail']}")
        else:
            failures += 1
            print(f"  [ERR] {verdict['name']} — {verdict['detail']}")

    if failures:
        print(f"[ERR] {failures} 份录制的解析路径失败（上游格式可能已变，需重新录制）")
        return _EXIT_SEVERE
    print("[OK] 全部录制的解析路径正常")
    return _EXIT_SUCCESS

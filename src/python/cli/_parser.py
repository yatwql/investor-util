"""CLI argparse 解析器构建 —— 全局参数、子命令定义与 type 回调校验。

仅负责「参数如何定义与解析」；解析结果的执行（子命令处理器）在
``_handlers.py``，主流程编排在 ``cli.py`` 门面。
"""

from __future__ import annotations

import argparse

from src.python.core.constants import APP_NAME, APP_VERSION

# ── argparse 解析器 ─────────────────────────────────────


def _experiment_name(value: str) -> tuple[str, ...]:
    """argparse type 回调 —— 校验并归一化 ``--experiment`` 取值。

    取值清单取自 features 注册表的实验组（与 TUI 菜单 S / Web 配置面板同源），
    支持开关名、显示名与 ``all``。命中多个（``all``）时返回全部开关名，调用方
    平铺后统一启用。

    名称解析本身容忍空白项（见 resolve_experiment_flags），但命令行取值
    为空串时属用户笔误，此处按非法取值报错，不静默忽略。
    """
    from src.python.config.features import describe_experiment_flags, resolve_experiment_flags

    flags, unknown = resolve_experiment_flags([value])
    if unknown or not flags:
        raise argparse.ArgumentTypeError(f"未知实验功能 '{value}'；可选: {describe_experiment_flags()}、all")
    return tuple(sorted(flags))


def _feature_override(value: str) -> tuple[str, bool]:
    """argparse type 回调 —— 校验 ``--feature NAME=VALUE`` 取值。

    与 ``--experiment`` 的区别见各自 help：本参数作用于**全部**功能开关（含常规
    组）且**双向**（可关）。取值域与合法性在解析期即校验——错误的开关名或取值
    当场报错并列出可选项，不留给运行时静默失效。
    """
    from src.python.config.features import parse_switch_override

    try:
        return parse_switch_override(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _effective_date_arg(value: str) -> str:
    """argparse 类型钩子：生效日归一化校验（委托共享层，与 Web/TUI 同一规则）。"""
    from src.python.report.whatif_operations import normalize_effective_date

    try:
        return normalize_effective_date(value) or ""
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


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
    parser.add_argument(
        "--experiment",
        metavar="NAME",
        action="append",
        type=_experiment_name,
        help="启用实验性功能，仅本次运行生效（不写入 features.json）。可重复指定；"
        "NAME 取开关名或显示名，all=全部启用。等价于 --feature 的实验组只开简写。",
    )
    parser.add_argument(
        "--feature",
        metavar="NAME=VALUE",
        action="append",
        type=_feature_override,
        help="覆写任意功能开关（含常规开关），仅本次运行生效（不写入 features.json）。可重复指定；"
        "NAME 取开关名，VALUE ∈ on/off/true/false/1/0（大小写不敏感）。"
        "与 --experiment 的区别：本参数是全开关双向覆写，后者只开实验组。",
    )
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
    report_p.add_argument(
        "--prefer-source",
        action="append",
        default=None,
        metavar="NAME",
        help="本次运行优先使用的数据源（可重复；不写配置，仅排到链首，不绕过熔断）",
    )
    report_p.add_argument(
        "--exclude-source",
        action="append",
        default=None,
        metavar="NAME",
        help="本次运行排除的数据源（可重复；用于排障复现，不写配置）",
    )

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
        type=_effective_date_arg,
        help="调仓生效日（可选）：指定后 opt-in 联网取生效日后行情，追加时序回测页（区间/年化收益、波动率、夏普、最大回撤）",
    )
    whatif_p.epilog = (
        "示例:\n"
        "  whatif --candidate 调仓后.xlsx              对比当前持仓 vs 目标持仓（成本口径截面比较）\n"
        "  whatif --base 调仓前.xlsx --candidate 调仓后.xlsx   显式指定两份持仓\n"
        "  whatif --candidate 调仓后.xlsx --effective-date 2026-07-01   指定生效日，追加时序回测\n"
        "输出: 调仓模拟.xlsx / .html（最新版固定名，历史归档至日期子目录；默认零网络请求，指定生效日时联网取历史做假设推演，不构成收益承诺）"
    )

    # ── cassettes 子命令（只读维护，无需 config）──
    cassettes_p = sub.add_parser(
        "cassettes",
        help="数据源记录-回放：列出已录制响应 / 离线校验能否被当前解析器解析（无需 config）",
    )
    cassettes_p.add_argument(
        "--verify",
        action="store_true",
        help="逐条离线回放并交给当前解析器解析（不联网）；有解析失败则退出码 2",
    )
    cassettes_p.epilog = (
        "示例:\n"
        "  cassettes           列出已录制 cassette（来源/录制时间/交互数）\n"
        "  cassettes --verify  离线校验每份录制的解析路径\n"
        "\n"
        "刷新录制需联网且为显式动作：\n"
        "  python scripts/test-runner.py --mode live --record-cassettes"
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

    # ── doctor 子命令（只读诊断，不依赖 config 初始化）──
    doctor_p = sub.add_parser("doctor", help="系统自检：环境/配置/目录/数据源一键体检（无需 config）")
    doctor_p.add_argument(
        "--offline",
        action="store_true",
        help="跳过数据源网络检查（仅查本地环境/配置/目录，瞬时返回）",
    )
    doctor_p.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="网络检查整体耗时预算秒数（默认 8，防止慢速数据源拖住自检）",
    )
    doctor_p.epilog = (
        "示例:\n"
        "  doctor              完整自检（含数据源联通性）\n"
        "  doctor --offline    仅本地自检，不联网\n"
        "  doctor --timeout 15 放宽网络检查耗时预算"
    )

    return parser

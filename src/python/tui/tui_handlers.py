"""TUI 命令处理器模块 — 实用工具 + 菜单调度。

对应关系：报告生成 → handlers_report.py，缓存管理 → handlers_cache.py，
配置管理 → handlers_config.py。本文件保留：
  - 菜单执行调度（execute_item）
  - 通用辅助函数（_print_*、_check_*、prepare_holdings、select_holdings_file 等）
  - 持仓变更检测与缓存预热（委托 cache.operations.warm_new_asset_caches）
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime

from src.python.llm.pricing import CURRENCY_SYMBOLS
from src.python.core.logger import setup_logger
from src.python.core.reader import get_xlsx_info, list_xlsx_files, read_holdings_with_flows
from src.python.report.progress import TuiProgressReporter
from src.python.tui.tui_menu import MENU_ITEMS, get_config_cache, press_any_key, refresh_config

logger = setup_logger()

_busy: bool = False  # 防连续按键保护
_busy_lock = threading.Lock()  # _busy 标志位锁保护


# ── LLM 用量 / 耗时 / 错误提示 ──────────────────────────────


def print_llm_session_usage(usage: dict | None = None) -> None:
    """输出会话累计 LLM 用量（TUI 终端一行）。"""
    if usage is None:
        try:
            from src.python.llm import get_session_usage

            usage = get_session_usage()
        except (ImportError, TypeError, AttributeError):
            logger.debug("获取 LLM 会话用量失败（非关键）")
            return
    if not usage or usage.get("call_count", 0) == 0:
        return
    calls = usage["call_count"]
    total_tok = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    cost = usage.get("total_cost", 0.0)
    symbol = CURRENCY_SYMBOLS.get(usage.get("currency", "CNY"), "¥")
    print(f"  [OK] 本会话 LLM 累计：{calls} 次调用，{total_tok:,} tokens，费用 {symbol}{cost:.4f}")


def print_timing_summary() -> None:
    """输出本次运行时各模块耗时排行（委托至 TuiProgressReporter）。"""
    from src.python.report.progress import timing_records

    reporter = TuiProgressReporter()
    reporter._timing_records.extend(timing_records)
    reporter.print_timing_summary()
    timing_records.clear()


def print_error_with_hint(e: Exception, prefix: str = "操作失败") -> None:
    """输出带友好提示的错误信息。"""
    msg = str(e)
    is_network = any(
        kw in msg.lower()
        for kw in (
            "connect",
            "timeout",
            "dns",
            "resolve",
            "network",
            "connection",
            "read timed out",
            "eof",
            "reset",
        )
    )
    if is_network:
        print(f"  [ERR] {prefix}: 网络连接异常，请检查网络后重试")
        print(f"        详情: {msg}")
    elif isinstance(e, PermissionError):
        print(f"  [ERR] {prefix}: 文件读取/写入权限不足")
        print("        请检查文件或目录的权限设置")
    elif isinstance(e, FileNotFoundError):
        print(f"  [ERR] {prefix}: 文件未找到，请检查路径是否正确")
        print(f"        详情: {msg}")
    elif isinstance(e, json.JSONDecodeError):
        print(f"  [ERR] {prefix}: 配置文件格式错误（JSON 语法错误）")
        print("        请检查配置文件是否为有效 JSON 格式")
    elif isinstance(e, (KeyError, ValueError, AttributeError, TypeError)):
        logger.warning("%s: %s", prefix, msg, exc_info=True)
        print(f"  [ERR] {prefix}: 数据处理异常，详情请查看日志文件 logs/app.log")
    elif isinstance(e, ImportError):
        logger.warning("%s: %s", prefix, msg, exc_info=True)
        print(f"  [ERR] {prefix}: 模块加载失败，请检查依赖是否完整安装")
        print("        pip install -r requirements.txt")
    else:
        logger.warning("%s: %s", prefix, msg, exc_info=True)
        print(f"  [ERR] {prefix}: 操作异常，详情请查看日志文件 logs/app.log")


# ── 持仓准备 / 收尾 ────────────────────────────────────────


def prepare_holdings() -> "tuple[list, list, list] | None":
    """选择持仓文件并读取持仓记录（含可选交易/分红流水页签）。失败时返回 None。

    Returns:
        (holdings, transactions, dividends) 三元组；无流水页签时流水列表为空。
    """
    refresh_config()
    filepath = select_holdings_file()
    if not filepath:
        return None
    try:
        print("  [..] 正在读取持仓数据...")
        parsed = read_holdings_with_flows(filepath)
        holdings = parsed.holdings
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            press_any_key()
            return None
        print(f"  [OK] 成功读取 {len(holdings)} 条持仓记录")
        if parsed.transactions or parsed.dividends:
            print(f"     含交易流水 {len(parsed.transactions)} 条，分红流水 {len(parsed.dividends)} 条")
        from src.python.cache.operations import warm_new_asset_caches

        warm_new_asset_caches(holdings, TuiProgressReporter())
        return holdings, parsed.transactions, parsed.dividends
    except Exception as e:
        print_error_with_hint(e, "读取持仓失败")
        press_any_key()
        return None


def finish_report(reporter: TuiProgressReporter) -> None:
    """报告生成收尾：错误摘要 → 耗时排行 → 按任意键。"""
    reporter.print_error_summary()
    reporter.print_timing_summary()
    press_any_key()


# ── 文件选择 ──────────────────────────────────────────────


def select_holdings_file() -> str | None:
    """让用户选择持仓文件，返回绝对路径；未找到时返回 None。"""
    from src.python.config import get_default, resolve_holdings_path

    refresh_config()
    config = get_config_cache() or {}
    specific_path = resolve_holdings_path(config)
    if os.path.exists(specific_path):
        return os.path.abspath(specific_path)
    dir_path = config.get("holdings_dir") or get_default("holdings_dir")
    files = list_xlsx_files(dir_path)
    if not files:
        print(f"  [ERR] 目录 '{dir_path}' 下未找到 xlsx 文件")
        print("     请先配置正确的持仓目录（菜单选项 C）")
        return None
    if len(files) == 1:
        print(f"  使用唯一找到的文件: {os.path.basename(files[0])}")
        return files[0]
    print("  找到多个持仓文件，请选择:")
    print(f"  {'':8s}{'文件名':40s}{'大小':>10s}{'修改日期':>22s}{'账户数':>8s}")
    print(f"  {'':-^8s}{'':-^40s}{'':->10s}{'':->22s}{'':->8s}")
    for i, f in enumerate(files, 1):
        basename = os.path.basename(f)
        name_disp = basename if len(basename) <= 38 else basename[:35] + "..."
        size = os.path.getsize(f)
        size_str = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
        mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
        info = get_xlsx_info(f)
        acct_str = f"{info.get('accounts', '?')}" if "error" not in info else "err"
        print(f"  [{i}]  {name_disp:38s} {size_str:>10s} {mtime:>22s} {acct_str:>8s}")
    try:
        choice = input("  请输入编号: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            return files[idx]
        print("  [ERR] 无效编号")
    except (ValueError, EOFError, KeyboardInterrupt):
        print()
        print("  [ERR] 无效输入")
    return None


# ── 菜单执行调度 ────────────────────────────────────────────


def execute_item(sel: int) -> None:
    """执行第 sel 项菜单的回调或退出。"""
    global _busy
    _, _label, callback, is_exit = MENU_ITEMS[sel]
    if is_exit:
        from src.python.tui.tui_menu import exit_app

        exit_app()
    if callback is not None:
        with _busy_lock:
            if _busy:
                return
            _busy = True
        try:
            callback()
        except KeyboardInterrupt:
            print()
            print("  操作已取消")
            press_any_key()
        except Exception as e:
            logger.exception("菜单项执行异常")
            print_error_with_hint(e, "操作执行异常")
            press_any_key()
        finally:
            with _busy_lock:
                _busy = False

"""TUI 命令处理器模块（精简版）— 实用工具 + 菜单调度。

按职责拆分后，报告生成 → handlers_report.py，缓存管理 → handlers_cache.py，
配置管理 → handlers_config.py。本文件保留：
  - 菜单执行调度（_execute_item）
  - 通用辅助函数（_print_*、_check_*、_prepare_holdings、_select_holdings_file 等）
  - 持仓变更检测与缓存预热（_check_and_warm_for_new_assets）
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from src.python.tui_menu import MENU_ITEMS, _press_any_key, _refresh_config, get_config_cache
from src.python.logger import setup_logger
from src.python.reader import get_xlsx_info, list_xlsx_files, read_holdings
from src.python.llm.pricing import _CURRENCY_SYMBOLS
from src.python.report.progress import TuiProgressReporter

logger = setup_logger()

_busy: bool = False  # 防连续按键保护


# ── LLM 用量 / 耗时 / 错误提示 ──────────────────────────────


def _print_llm_session_usage(usage: dict | None = None) -> None:
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
    symbol = _CURRENCY_SYMBOLS.get(usage.get("currency", "CNY"), "¥")
    print(f"  [OK] 本会话 LLM 累计：{calls} 次调用，{total_tok:,} tokens，费用 {symbol}{cost:.4f}")


def _print_timing_summary() -> None:
    """输出本次运行时各模块耗时排行（委托至 TuiProgressReporter）。"""
    TuiProgressReporter().print_timing_summary()


def _print_error_with_hint(e: Exception, prefix: str = "操作失败") -> None:
    """输出带友好提示的错误信息。"""
    msg = str(e)
    is_network = any(kw in msg.lower() for kw in (
        "connect", "timeout", "dns", "resolve", "network",
        "connection", "read timed out", "eof", "reset",
    ))
    if is_network:
        print(f"  [ERR] {prefix}: 网络连接异常，请检查网络后重试")
        print(f"        详情: {msg}")
    elif isinstance(e, PermissionError):
        print(f"  [ERR] {prefix}: 文件读取/写入权限不足")
        print(f"        请检查文件或目录的权限设置")
    elif isinstance(e, FileNotFoundError):
        print(f"  [ERR] {prefix}: 文件未找到，请检查路径是否正确")
        print(f"        详情: {msg}")
    elif isinstance(e, json.JSONDecodeError):
        print(f"  [ERR] {prefix}: 配置文件格式错误（JSON 语法错误）")
        print(f"        请检查配置文件是否为有效 JSON 格式")
    elif isinstance(e, (KeyError, ValueError, AttributeError, TypeError)):
        logger.warning("%s: %s", prefix, msg, exc_info=True)
        print(f"  [ERR] {prefix}: 数据处理异常，详情请查看日志文件 logs/app.log")
    elif isinstance(e, ImportError):
        logger.warning("%s: %s", prefix, msg, exc_info=True)
        print(f"  [ERR] {prefix}: 模块加载失败，请检查依赖是否完整安装")
        print(f"        pip install -r requirements.txt")
    else:
        logger.warning("%s: %s", prefix, msg, exc_info=True)
        print(f"  [ERR] {prefix}: 操作异常，详情请查看日志文件 logs/app.log")


def _check_network_available(details: list) -> bool:
    """检查行情数据是否全部不可用（网络完全中断）。"""
    if not details:
        return False
    all_unavailable = all(
        getattr(d, 'price', 0) is None or getattr(d, 'price', 0) == 0
        for d in details
    )
    if all_unavailable:
        print("  [!!] 网络连接异常：所有行情数据均获取失败")
        print("     请检查网络连接后重试（部分报告内容可能为空）")
        return False
    return True


# ── 持仓准备 / 收尾 ────────────────────────────────────────


def _prepare_holdings() -> list | None:
    """选择持仓文件并读取持仓记录。失败时返回 None。"""
    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return None
    try:
        print("  [..] 正在读取持仓数据...")
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return None
        print(f"  [OK] 成功读取 {len(holdings)} 条持仓记录")
        _check_and_warm_for_new_assets(holdings)
        return holdings
    except Exception as e:
        _print_error_with_hint(e, "读取持仓失败")
        _press_any_key()
        return None


def _finish_report(reporter: TuiProgressReporter) -> None:
    """报告生成收尾：错误摘要 → 耗时排行 → 按任意键。"""
    reporter.print_error_summary()
    reporter.print_timing_summary()
    _press_any_key()


def _check_and_warm_for_new_assets(holdings: list) -> None:
    """检测持仓是否变化，若有新增资产则主动预热其缓存数据。"""
    try:
        from src.python.cache import check_and_refresh_caches
        from src.python.fetcher.industry import batch_fetch_industry_data
        from src.python.fetcher.fund import fetch_fund_holdings, fetch_fund_rankings
        from src.python.fetcher.price import fetch_market_data
        from src.python.report.fund_performance import _is_fund

        new_codes = check_and_refresh_caches(holdings)
        if not new_codes:
            return

        code_map = {h.code: h for h in holdings}
        print(f"  [..] 检测到 {len(new_codes)} 个新增资产，正在预热缓存...")

        for code in new_codes:
            h = code_map.get(code)
            name = h.name if h else code
            print(f"  [..]   新增 {name} ({code}) — 获取行情...", end="")
            result = fetch_market_data(code, name)
            if result and result.get("price", 0) > 0:
                print(f" {result['price']:.4f}")
            else:
                print(" 失败")
            if h and _is_fund(h):
                print(f"  [..]   新增基金 {name} ({code}) — 获取业绩排名...", end="")
                perf = fetch_fund_rankings(code)
                print(" OK" if perf else " 失败")
                print(f"  [..]   新增基金 {name} ({code}) — 获取持仓明细...", end="")
                holds = fetch_fund_holdings(code)
                if holds and holds.get("holdings"):
                    print(f" {len(holds['holdings'])} 条")
                else:
                    print(" 无数据")
            print(f"  [..]   新增 {name} ({code}) — 获取行业分类...", end="")
            _ind_map = batch_fetch_industry_data([code])
            if _ind_map and code in _ind_map:
                _idata = _ind_map[code]
                ind_name = _idata.get("industry") or "未知"
                conc_count = len(_idata.get("concepts", []))
                print(f" {ind_name} ({conc_count} 个概念)")
            else:
                print(" 无数据")
        print(f"  [OK] 新增资产缓存预热完成")
    except Exception:
        logger.warning("新资产预热过程异常，跳过（不影响后续生成）")


# ── 文件选择 ──────────────────────────────────────────────


def _select_holdings_file() -> str | None:
    """让用户选择持仓文件，返回绝对路径；未找到时返回 None。"""
    _refresh_config()
    config = get_config_cache() or {}
    specific_path = os.path.join(config.get("holdings_dir", ""), config.get("holdings_filename", ""))
    if os.path.exists(specific_path):
        return os.path.abspath(specific_path)
    dir_path = config.get("holdings_dir", "")
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


def _execute_item(sel: int) -> None:
    """执行第 sel 项菜单的回调或退出。"""
    global _busy
    _, _label, callback, is_exit = MENU_ITEMS[sel]
    if is_exit:
        from src.python.tui_menu import _exit_app
        _exit_app()
    if callback is not None:
        if _busy:
            return
        _busy = True
        try:
            callback()
        except KeyboardInterrupt:
            print()
            print("  操作已取消")
            _press_any_key()
        except Exception as e:
            logger.exception("菜单项执行异常")
            _print_error_with_hint(e, "操作执行异常")
            _press_any_key()
        finally:
            _busy = False

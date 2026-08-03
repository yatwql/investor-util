#!/usr/bin/env python3
"""投资分析系统 — TUI 主入口。"""

from __future__ import annotations

import atexit
import os
import sys
from collections.abc import Callable

# 确保项目根目录在 sys.path 中（支持直接执行 python src/python/tui/tui.py）
_src_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_src_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.python.config import init_config
from src.python.llm.pricing import CURRENCY_SYMBOLS
from src.python.core.logger import log_app_boundary, setup_logger
from src.python.tui.tui_keys import KEY_CTRL_C, KEY_DOWN, KEY_ENTER, KEY_UP, get_key
from src.python.tui.tui_handlers import execute_item
from src.python.tui.tui_menu import (
    MENU_ITEMS,
    exit_app,
    index_by_key,
    print_header,
    render_menu,
    show_config,
)

logger = setup_logger()
log_app_boundary("启动", "TUI模式")
atexit.register(log_app_boundary, "关闭", "TUI模式")


def _print_session_usage_on_exit() -> None:
    """程序退出时打印 LLM 会话累计用量。"""
    try:
        from src.python.llm import get_session_usage

        usage = get_session_usage()
        if usage.get("call_count", 0) > 0:
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cache_hit = usage.get("cache_hit_tokens", 0)
            total_tok = inp + out
            calls = usage.get("call_count", 0)
            cost = usage.get("total_cost", 0.0)
            currency = usage.get("currency", "CNY")
            symbol = CURRENCY_SYMBOLS.get(currency, "¥")
            model = usage.get("model", "")
            print("\n── LLM 会话统计 ──")
            print(f"  模型: {model}")
            per_module = usage.get("per_module", {})
            if per_module:
                from src.python.core.registry import get_llm_module_names

                _MODULE_DISPLAY = get_llm_module_names()
                for key, display_name in _MODULE_DISPLAY.items():
                    if key in per_module:
                        pm = per_module[key]
                        _m = pm.get("model", "-")
                        _tag = " (缓存)" if pm.get("cached") else ""
                        print(f"    {display_name}: {_m}{_tag}")
            print(f"  调用次数: {calls}")
            print(f"  输入 tokens: {inp:,}")
            print(f"  输出 tokens: {out:,}")
            if cache_hit:
                print(f"  缓存命中: {cache_hit:,}")
            print(f"  总 tokens: {total_tok:,}")
            print(f"  累计费用: {symbol}{cost:.4f}")
            print("──────────────────")
    except (KeyError, TypeError, AttributeError):
        logger.warning("打印 LLM 会话统计时出错", exc_info=True)
        pass


def _bind_callbacks() -> None:
    """运行时将函数引用填入 MENU_ITEMS。"""
    from src.python.tui.handlers_cache import (
        _cmd_cleanup_cache,
        _cmd_show_cache_stats,
        _cmd_update_basic_cache,
        _cmd_update_position_cache,
    )
    from src.python.tui.handlers_config import (
        _cmd_config_anonymization_mode,
        _cmd_config_comparison_indices,
        _cmd_config_dir,
        _cmd_config_filename,
        _cmd_config_llm_modules,
        _cmd_config_output_dir,
        _cmd_config_report_boards,
        _cmd_refresh_config,
    )
    from src.python.tui.handlers_report import (
        _cmd_generate_both,
        _cmd_generate_excel,
        _cmd_generate_full,
    )
    from src.python.tui.handlers_whatif import _cmd_whatif

    callbacks: dict[str, Callable] = {
        "E": _cmd_generate_excel,
        "B": _cmd_generate_both,
        "L": _cmd_generate_full,
        "W": _cmd_whatif,
        "C": _cmd_config_dir,
        "F": _cmd_config_filename,
        "O": _cmd_config_output_dir,
        "1": _cmd_update_basic_cache,
        "2": _cmd_update_position_cache,
        "3": _cmd_cleanup_cache,
        "4": _cmd_show_cache_stats,
        "I": _cmd_config_comparison_indices,
        "A": _cmd_config_anonymization_mode,
        "P": _cmd_config_report_boards,
        "S": _cmd_config_llm_modules,
        "R": _cmd_refresh_config,
    }
    for i, (key, _label, _cb, is_exit) in enumerate(MENU_ITEMS):
        MENU_ITEMS[i] = (key, _label, callbacks.get(key), is_exit)


def main() -> None:
    """TUI 主循环。支持方向键导航 + Enter 确认 + 字母快捷键 + Ctrl+C。"""
    init_config()
    _bind_callbacks()
    atexit.register(_print_session_usage_on_exit)

    # 启动时自动清理过期缓存（静默后台执行，仅日志记录）
    try:
        from src.python.cache import cleanup_expired

        removed = cleanup_expired(dry_run=False)
        if removed > 0:
            logger.info("启动时自动清理了 %d 个过期缓存文件", removed)
    except OSError as e:
        logger.warning("启动时缓存清理失败: %s", e)

    # 首次运行隐私提示
    try:
        from src.python.report.privacy_notice import show_privacy_notice_if_needed

        show_privacy_notice_if_needed()
    except Exception:
        logger.debug("隐私提示显示失败（非关键）", exc_info=True)

    # 首次运行引导（检测缺失资源并交互式提示）
    try:
        from src.python.startup_wizard import show_startup_wizard_if_needed

        show_startup_wizard_if_needed()
    except Exception:
        logger.debug("首次运行引导显示失败（非关键）", exc_info=True)

    # 读取缺省菜单选项（config.json → default_menu_key），仅支持 E/H/B/L/W/C/F/O/1/2/3/4/S/R/X
    from src.python.config import get_config

    _default_key = get_config().get("default_menu_key", "L").upper()
    _idx = index_by_key(_default_key)
    sel: int = _idx if _idx is not None else 0

    while True:
        print_header()
        show_config()
        render_menu(sel)

        key = get_key()

        if key == KEY_UP:
            sel = (sel - 1) % len(MENU_ITEMS)
        elif key == KEY_DOWN:
            sel = (sel + 1) % len(MENU_ITEMS)
        elif key == KEY_ENTER:
            execute_item(sel)
        elif key == KEY_CTRL_C:
            exit_app()
        elif len(key) == 1 and ("A" <= key <= "Z" or "a" <= key <= "z" or "0" <= key <= "9"):
            idx = index_by_key(key.upper())
            if idx is not None:
                sel = idx
                execute_item(idx)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("  感谢使用，再见！")
        sys.exit(0)

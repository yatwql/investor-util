#!/usr/bin/env python3
"""投资分析系统 — TUI 主入口。"""

from __future__ import annotations

import os
import sys

# 确保项目根目录在 sys.path 中，并切换工作目录
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
os.chdir(_project_root)

from src.python.logger import setup_logger
from src.python.config import init_config
from src.python.reader import read_holdings
from src.python.tui import KEY_CTRL_C, KEY_DOWN, KEY_ENTER, KEY_UP, get_key

from src.python.tui_menu import (
    MENU_ITEMS,
    _exit_app,
    _index_by_key,
    _print_header,
    _render_menu,
    _show_config,
    _refresh_config,
)
from src.python.tui_handlers import _execute_item

logger = setup_logger()


def _bind_callbacks() -> None:
    """运行时将函数引用填入 MENU_ITEMS。"""
    from src.python.tui_handlers import (
        _cmd_generate_excel,
        _cmd_generate_excel_with_news,
        _cmd_generate_html,
        _cmd_generate_both,
        _cmd_generate_full,
        _cmd_config_dir,
        _cmd_config_filename,
        _cmd_config_output_dir,
        _cmd_update_basic_cache,
        _cmd_update_position_cache,
        _cmd_cleanup_cache,
        _cmd_show_cache_stats,
    )
    callbacks: dict[str, callable] = {
        "E": _cmd_generate_excel,
        "N": _cmd_generate_excel_with_news,
        "H": _cmd_generate_html,
        "B": _cmd_generate_both,
        "L": _cmd_generate_full,
        "C": _cmd_config_dir,
        "F": _cmd_config_filename,
        "R": _cmd_config_output_dir,
        "1": _cmd_update_basic_cache,
        "2": _cmd_update_position_cache,
        "3": _cmd_cleanup_cache,
        "4": _cmd_show_cache_stats,
    }
    for i, (key, _label, _cb, is_exit) in enumerate(MENU_ITEMS):
        MENU_ITEMS[i] = (key, _label, callbacks.get(key), is_exit)


def main() -> None:
    """TUI 主循环。支持方向键导航 + Enter 确认 + 字母快捷键 + Ctrl+C。"""
    init_config()
    _bind_callbacks()

    # 启动时自动清理过期缓存（静默后台执行，仅日志记录）
    try:
        from src.python.cache import cleanup_expired
        removed = cleanup_expired(dry_run=False)
        if removed > 0:
            logger.info("启动时自动清理了 %d 个过期缓存文件", removed)
    except Exception:
        pass

    _print_header()
    sel: int = 0

    while True:
        _show_config()
        _render_menu(sel)

        key = get_key()

        if key == KEY_UP:
            sel = (sel - 1) % len(MENU_ITEMS)
        elif key == KEY_DOWN:
            sel = (sel + 1) % len(MENU_ITEMS)
        elif key == KEY_ENTER:
            _execute_item(sel)
        elif key == KEY_CTRL_C:
            _exit_app()
        elif len(key) == 1 and ("A" <= key <= "Z" or "a" <= key <= "z" or "0" <= key <= "9"):
            idx = _index_by_key(key.upper())
            if idx is not None:
                sel = idx
                _execute_item(idx)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("  感谢使用，再见！")
        sys.exit(0)

"""TUI 配置管理命令处理器。

按职责从 tui_handlers.py 拆分而来，负责所有配置管理相关的命令函数。
"""
from __future__ import annotations

import json
import os
import sys

from src.python.config import set_config
from src.python.logger import setup_logger
from src.python.reader import list_xlsx_files
from src.python.tui_menu import _press_any_key, _refresh_config, get_config_cache

logger = setup_logger()


def _read_llm_settings() -> tuple[dict, str] | None:
    """读取 llm_settings.json 配置（支持 JSON 注释）。

    Returns:
        (settings_dict, path) 成功时；失败时返回 None（已输出错误提示）
    """
    from src.python.config import _strip_json_comments
    path = "data/config/llm_settings.json"
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = f.read()
        settings = json.loads(_strip_json_comments(raw))
        return settings, path
    except (FileNotFoundError, json.JSONDecodeError):
        print("  [ERR] 无法读取 llm_settings.json")
        _press_any_key()
        return None


def _write_llm_settings(settings: dict, path: str) -> None:
    """写入 llm_settings.json 并刷新 LLM 配置缓存。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    from src.python.config import get_llm_config
    get_llm_config()


def _cmd_config_dir() -> None:
    """配置持仓目录。"""
    _refresh_config()
    config = get_config_cache() or {}
    current = config.get("holdings_dir", "")
    print(f"  当前目录: {current}")
    print("  请输入新目录路径（留空则不修改）:")
    try:
        new_dir = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if new_dir:
        set_config("holdings_dir", new_dir)
        _refresh_config()
        print(f"  [OK] 目录已更新为: {new_dir}")
    else:
        print("  未修改")


def _cmd_config_filename() -> None:
    """配置持仓文件名。"""
    _refresh_config()
    config = get_config_cache() or {}
    current = config.get("holdings_filename", "")
    files = list_xlsx_files(config.get("holdings_dir", ""))
    if files:
        print("  当前目录中的 xlsx 文件:")
        for i, f in enumerate(files, 1):
            print(f"    [{i}] {os.path.basename(f)}")
        print()
    print(f"  当前文件名: {current}")
    print("  请输入文件名（留空则不修改）:")
    try:
        new_name = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if new_name:
        set_config("holdings_filename", new_name)
        _refresh_config()
        print(f"  [OK] 文件名已更新为: {new_name}")
    else:
        print("  未修改")


def _cmd_config_output_dir() -> None:
    """配置报告输出目录。"""
    _refresh_config()
    config = get_config_cache() or {}
    current = config.get("output_dir", "reports")
    print(f"  当前输出目录: {current}")
    print("  请输入新的报告输出目录路径（留空则不修改）:")
    try:
        new_dir = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if new_dir:
        set_config("output_dir", new_dir)
        _refresh_config()
        print(f"  [OK] 输出目录已更新为: {new_dir}")
    else:
        print("  未修改")


def _cmd_config_llm_modules() -> None:
    """配置各 LLM 报告的启用/停用（编辑 llm_settings.json 的 enabled_llm）。"""
    from src.python.registry import get_llm_module_names

    result = _read_llm_settings()
    if result is None:
        return
    settings, settings_path = result

    enabled_map = settings.get("enabled_llm", {})
    module_names = get_llm_module_names()

    while True:
        print()
        print("  ┌── 配置支持LLM的报告分析章节 ──────────────┐")
        items = []
        for i, (sfx, name) in enumerate(module_names.items(), 1):
            status = enabled_map.get(sfx, True)
            if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
                _GREEN = _RED = _RESET = ""
            else:
                _GREEN, _RED, _RESET = "\033[92m", "\033[91m", "\033[0m"
            status_str = f"{_GREEN}开启{_RESET}" if status else f"{_RED}关闭{_RESET}"
            items.append((i, sfx, name, status))
            print(f"  │ {i}. {name:<14s} [{status_str}]{' ' * 4}│")
        print(f"  │ 0. 返回主菜单{' ' * 27}│")
        print(f"  └{'─' * 42}┘")
        print()
        try:
            choice = input("  输入编号切换 (0-5): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            break

        try:
            idx = int(choice)
            matched = [it for it in items if it[0] == idx]
            if matched:
                _, sfx, name, curr = matched[0]
                enabled_map[sfx] = not curr
                settings["enabled_llm"] = enabled_map
                _write_llm_settings(settings, settings_path)
                print(f"  [OK] {name} 已{'开启' if not curr else '关闭'}")
            else:
                print("  [!] 无效编号")
        except (ValueError, TypeError):
            print("  [!] 请输入有效编号")

    _press_any_key()


def _cmd_refresh_config() -> None:
    """重新加载所有配置（config.json + llm_settings.json + llm_key.json）。"""
    # 破坏内部缓存强制重新读取
    import src.python.config as _cfg_mod
    from src.python.config import get_config, get_llm_config
    from src.python.llm.pricing import _reload_pricing
    _cfg_mod._config_cache = None
    _cfg_mod._config_mtime = 0
    _cfg_mod._llm_config_cache = None
    _cfg_mod._llm_config_mtime = 0

    config = get_config()
    llm_config = get_llm_config()
    _reload_pricing()

    # 刷新 tui_menu 配置缓存
    _refresh_config()

    if config:
        print("  [OK] config.json 已重新加载")
    if llm_config:
        print("  [OK] llm_settings.json + llm_key.json 已重新加载")
    else:
        print("  [!] LLM 未配置（llm_key.json 缺失或无效）")
    _press_any_key()

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
from src.python.tui_menu import GREEN, RED, YELLOW, RESET, press_any_key, refresh_config, get_config_cache

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
        print(f"  {RED}[ERR]{RESET} 无法读取 llm_settings.json")
        press_any_key()
        return None


def _write_llm_settings(settings: dict, path: str) -> None:
    """写入 llm_settings.json 并刷新 LLM 配置缓存，保留文件中的注释。

    仅更新 settings 中发生变化的字段对应的文本区块，注释和其他字段原样保留。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        raw = ""

    if raw.strip():
        from src.python.config import _strip_json_comments
        current = json.loads(_strip_json_comments(raw))
        updated_raw = _update_json_raw_text(raw, current, settings)
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated_raw)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

    from src.python.config import get_llm_config
    get_llm_config()


def _update_json_raw_text(raw: str, current: dict, new: dict) -> str:
    """在原始 JSON 文本中做精确的字段级替换，保留注释和空白。

    对 dict 类型值使用 brace 平衡算法 + 自适应缩进替换，
    对简单值（str/int/bool/None）使用正则替换。

    Args:
        raw: 原始 JSON 文本（含注释）
        current: 当前解析后的值
        new: 要写入的新值

    Returns:
        经字段级替换后的新文本
    """
    import re

    result = raw
    for key, new_val in new.items():
        old_val = current.get(key)
        if old_val == new_val:
            continue

        if isinstance(old_val, dict):
            result = _replace_dict_block(result, key, new_val)
        else:
            old_json = json.dumps(old_val, ensure_ascii=False, indent=2) if old_val is not None else "null"
            new_json = json.dumps(new_val, ensure_ascii=False, indent=2) if new_val is not None else "null"
            result = re.sub(
                re.escape(f'"{key}":') + r'\s*' + re.escape(old_json),
                f'"{key}": {new_json}',
                result,
                count=1,
            )
    return result


def _replace_dict_block(text: str, key: str, new_val: dict) -> str:
    """在 JSON 文本中找到指定 key 的 dict 值区块，自适应缩进替换。

    使用 brace 平衡算法确保正确匹配嵌套大括号，自动检测周围缩进层级，
    使替换后的 JSON 与文件缩进风格一致。
    """
    import re
    import json as _json

    match = re.search(re.escape(f'"{key}":') + r'\s*\{', text)
    if not match:
        return text

    # 检测 key 所在的当前行缩进
    line_start = text.rfind("\n", 0, match.start()) + 1
    base_indent = match.start() - line_start  # ""{key}"" 前的空格数

    # 序列化新值，使用 4 空格内缩
    INNER_INDENT = 4
    lines = _json.dumps(new_val, ensure_ascii=False, indent=INNER_INDENT).split("\n")

    # 第一行是 "{"，续行加 base_indent 前缀，末行 "}" 也加 base_indent
    block_lines = [lines[0]]
    for line in lines[1:]:
        stripped = line.lstrip()
        leading = len(line) - len(stripped)
        if leading == 0:
            block_lines.append(" " * base_indent + stripped)
        else:
            block_lines.append(" " * base_indent + line)
    block_text = "\n".join(block_lines)

    # 从 opening brace 开始逐字符查找 matching closing brace
    brace_start = match.end() - 1  # '{' 的位置
    depth = 0
    pos = brace_start
    while pos < len(text):
        ch = text[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[:match.start()] + f'"{key}": {block_text}' + text[pos + 1:]
        pos += 1
    return text  # brace 不平衡，放弃替换


def _cmd_config_dir() -> None:
    """配置持仓目录。"""
    refresh_config()
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
        refresh_config()
        print(f"  {GREEN}[OK]{RESET} 目录已更新为: {new_dir}")
    else:
        print("  未修改")


def _cmd_config_filename() -> None:
    """配置持仓文件名。"""
    refresh_config()
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
        refresh_config()
        print(f"  {GREEN}[OK]{RESET} 文件名已更新为: {new_name}")
    else:
        print("  未修改")


def _cmd_config_output_dir() -> None:
    """配置报告输出目录。"""
    refresh_config()
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
        refresh_config()
        print(f"  {GREEN}[OK]{RESET} 输出目录已更新为: {new_dir}")
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
            status_str = f"{GREEN}开启{RESET}" if status else f"{RED}关闭{RESET}"
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
                print(f"  {GREEN}[OK]{RESET} {name} 已{'开启' if not curr else '关闭'}")
            else:
                print(f"  {YELLOW}[!]{RESET} 无效编号")
        except (ValueError, TypeError):
            print(f"  {YELLOW}[!]{RESET} 请输入有效编号")

    press_any_key()


def _cmd_config_report_boards() -> None:
    """配置报告板块可见性（B 系列 / 新闻与预警 / 历史走势）。"""
    from src.python.config import (
        is_enable_b_series, is_enable_news, is_enable_history,
        set_config, get_config,
    )

    while True:
        config = get_config()
        b_series = is_enable_b_series(config)
        news     = is_enable_news(config)
        history  = is_enable_history(config)

        print()
        print("  ┌── 配置报告板块可见性 ────────────────────┐")
        b_status = f"{GREEN}启用{RESET}" if b_series else f"{RED}禁用{RESET}"
        n_status = f"{GREEN}启用{RESET}" if news else f"{RED}禁用{RESET}"
        h_status = f"{GREEN}启用{RESET}" if history else f"{RED}禁用{RESET}"
        print(f"  │ 1. B 系列基金深度分析（#6~9）  [{b_status}]{' ' * 8}│")
        print(f"  │ 2. 新闻与预警（#10~11）        [{n_status}]{' ' * 8}│")
        print(f"  │ 3. 组合历史走势+回撤（#16~17）  [{h_status}]{' ' * 8}│")
        print(f"  │                                   │")
        print(f"  │ 4. LLM 板块（#12~15,#18） — 请在菜单 S 配置 │")
        print(f"  │ 0. 返回主菜单{' ' * 27}│")
        print(f"  └{'─' * 42}┘")
        print()
        try:
            choice = input("  输入编号切换 (0-4): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            break

        if choice == "1":
            set_config("enable_b_series", not b_series)
            print(f"  {GREEN}[OK]{RESET} B 系列已{'禁用' if b_series else '启用'}")
        elif choice == "2":
            set_config("enable_news", not news)
            print(f"  {GREEN}[OK]{RESET} 新闻与预警已{'禁用' if news else '启用'}")
        elif choice == "3":
            set_config("enable_history", not history)
            print(f"  {GREEN}[OK]{RESET} 组合历史走势已{'禁用' if history else '启用'}")
        elif choice == "4":
            print(f"  {YELLOW}[!]{RESET} LLM 板块配置请使用菜单 [S]")
        else:
            print(f"  {YELLOW}[!]{RESET} 无效编号")

    refresh_config()
    press_any_key()


def _cmdrefresh_config() -> None:
    """重新加载所有配置（config.json + llm_settings.json + llm_key.json）。"""
    # 破坏内部缓存强制重新读取
    import src.python.config as _cfg_mod
    from src.python.config import get_config, get_llm_config
    from src.python.llm.pricing import reload_pricing
    _cfg_mod._config_cache = None
    _cfg_mod._config_mtime = 0
    _cfg_mod._llm_config_cache = None
    _cfg_mod._llm_config_mtime = 0

    config = get_config()
    llm_config = get_llm_config()
    reload_pricing()

    # 刷新 tui_menu 配置缓存
    refresh_config()

    if config:
        print(f"  {GREEN}[OK]{RESET} config.json 已重新加载")
    if llm_config:
        print(f"  {GREEN}[OK]{RESET} llm_settings.json + llm_key.json 已重新加载")
    else:
        print(f"  {YELLOW}[!]{RESET} LLM 未配置（llm_key.json 缺失或无效）")
    press_any_key()

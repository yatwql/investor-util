"""TUI 配置管理命令处理器。

所有配置管理相关的 TUI 命令处理函数（菜单 C/F/O/P/S/R/A/I）。
"""

from __future__ import annotations

import json
import os

from src.python.config import set_config
from src.python.constants import PROJECT_ROOT
from src.python.logger import setup_logger
from src.python.reader import list_xlsx_files
from src.python.tui_menu import GREEN, RED, RESET, YELLOW, get_config_cache, press_any_key, refresh_config

logger = setup_logger()


def _read_llm_settings() -> tuple[dict, str] | None:
    """读取 llm_settings.json 配置（支持 JSON 注释）。

    Returns:
        (settings_dict, path) 成功时；失败时返回 None（已输出错误提示）
    """
    from src.python.config import _strip_json_comments, get_config

    config_path = get_config().get(
        "llm_settings_file",
        os.path.join(PROJECT_ROOT, "data/config/llm_settings.json"),
    )
    try:
        with open(config_path, encoding="utf-8-sig") as f:
            raw = f.read()
        settings = json.loads(_strip_json_comments(raw))
        return settings, config_path
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"  {RED}[ERR]{RESET} 无法读取 llm_settings.json")
        press_any_key()
        return None


def _write_llm_settings(settings: dict, path: str) -> None:
    """写入 llm_settings.json 并刷新 LLM 配置缓存，保留文件中的注释。

    仅更新 settings 中发生变化的字段对应的文本区块，注释和其他字段原样保留。
    """
    try:
        with open(path, encoding="utf-8") as f:
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
                re.escape(f'"{key}":') + r"\s*" + re.escape(old_json),
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
    import json as _json
    import re

    match = re.search(re.escape(f'"{key}":') + r"\s*\{", text)
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
                return text[: match.start()] + f'"{key}": {block_text}' + text[pos + 1 :]
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
    """配置各 LLM 报告的启用/停用（llm_settings.json + features.json 辩论开关）。

    标准 LLM 模块（1-5）通过 enabled_llm 控制，存储在 llm_settings.json。
    辩论模式增强（6-8）通过 Feature Flag 控制，存储在 features.json。
    """
    from src.python.features import is_feature_enabled, save_feature_overrides, set_feature_enabled
    from src.python.registry import get_llm_module_names

    result = _read_llm_settings()
    if result is None:
        return
    settings, settings_path = result

    enabled_map = settings.get("enabled_llm", {})
    module_names = get_llm_module_names()

    # 辩论模式开关定义：(flag_key, 显示名, 说明)
    DEBATE_FLAGS: list[tuple[str, str, str]] = [
        ("llm_debate_procon", "辩论-M1 正反辩论", "三段式(白脸→黑脸→综合)"),
        ("llm_debate_conditional", "辩论-M2 条件推理", "情景化分析(涨/跌/震荡)"),
        ("llm_debate_qa_concentration", "辩论-M3 集中度问答", "集中度风险问答"),
    ]

    while True:
        print()
        print("  ┌── 配置支持LLM的报告分析章节 ──────────────┐")
        items: list[tuple[int, str, str, bool, str]] = []

        # ① 标准 LLM 模块（1-5）
        for i, (sfx, name) in enumerate(module_names.items(), 1):
            status = enabled_map.get(sfx, True)
            status_str = f"{GREEN}开启{RESET}" if status else f"{RED}关闭{RESET}"
            items.append((i, sfx, name, status, "llm"))
            print(f"  │ {i}. {name:<14s} [{status_str}]{' ' * 4}│")

        # 分隔线 + 实验功能标记
        print(f"  │{'─' * 42}│")
        print(f"  │ ⚗ 实验性功能（默认关闭）{' ' * 22}│")

        # ② 辩论模式开关（6-8）
        for j, (flag, label, _desc) in enumerate(DEBATE_FLAGS, len(module_names) + 1):
            status = is_feature_enabled(flag)
            status_str = f"{GREEN}开启{RESET}" if status else f"{RED}关闭{RESET}"
            items.append((j, flag, label, status, "debate"))
            print(f"  │ {j}. ⚗{label:<14s} [{status_str}]{' ' * 3}│")

        print(f"  │ 0. 返回主菜单{' ' * 27}│")
        print(f"  └{'─' * 42}┘")
        print("  ⚗ 实验性辩论模式默认关闭，开启后智囊团深度复盘输出含辩论内容")
        print("     ⚠ 当前为实验阶段，输出质量可能不稳定")
        print()
        try:
            total = len(items)
            choice = input(f"  输入编号切换 (0-{total}): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            break

        try:
            idx = int(choice)
            matched = [it for it in items if it[0] == idx]
            if matched:
                _, key, name, curr, kind = matched[0]
                new_val = not curr
                if kind == "llm":
                    enabled_map[key] = new_val
                    settings["enabled_llm"] = enabled_map
                    _write_llm_settings(settings, settings_path)
                else:
                    set_feature_enabled(key, new_val)
                    save_feature_overrides({key: new_val})
                print(f"  {GREEN}[OK]{RESET} {name} 已{'开启' if new_val else '关闭'}")
                # 刷新配置缓存
                refresh_config()
            else:
                print(f"  {YELLOW}[!]{RESET} 无效编号")
        except (ValueError, TypeError):
            print(f"  {YELLOW}[!]{RESET} 请输入有效编号")

    press_any_key()


def _cmd_config_comparison_indices() -> None:
    """管理对比指数池（竞争语境中使用的多指数对比）。"""
    from src.python.config._config_defaults import _DEFAULT_CONFIG

    while True:
        refresh_config()
        config = get_config_cache() or {}
        indices = config.get("comparison_indices", _DEFAULT_CONFIG.get("comparison_indices", {}))
        print()
        print("  ┌── 管理对比指数池 ──────────────────────┐")
        print("  │ 自定义基准指数，用于报告中组合 vs 多指数对比  │")
        print(f"  │ 当前指数 ({len(indices)} 个):{' ' * 21}│")
        if indices:
            for i, (code, name) in enumerate(indices.items(), 1):
                label = f"{code} ({name})"
                padding = " " * max(1, 35 - len(label))
                print(f"  │   {i}. {label}{padding}│")
        else:
            print("  │   空池（仅显示沪深300） {' ' * 20}│")
        print(f"  │{'─' * 42}│")
        print("  │ A. 添加指数 {' ' * 30}│")
        print("  │ D. 删除指数 {' ' * 30}│")
        print("  │ R. 重置为默认预设{' ' * 27}│")
        print("  │ 0. 返回主菜单{' ' * 27}│")
        print(f"  └{'─' * 42}┘")
        print()
        try:
            choice = input("  请选择 (A/D/R/0): ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            break
        elif choice == "A":
            _add_comparison_index(config, indices)
        elif choice == "D":
            _remove_comparison_index(config, indices)
        elif choice == "R":
            default_pool = _DEFAULT_CONFIG.get("comparison_indices", {})
            set_config("comparison_indices", dict(default_pool))
            print(f"  {GREEN}[OK]{RESET} 对比指数池已重置为默认预设")
        elif choice in ("A", "D", "R"):
            continue
        else:
            print(f"  {YELLOW}[!]{RESET} 无效选择，请重试")

    press_any_key()


def _add_comparison_index(config: dict, indices: dict[str, str]) -> None:
    """添加指数到对比池。"""
    print("  请输入指数代码（如 sh000905）:")
    try:
        code = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not code:
        print(f"  {YELLOW}[!]{RESET} 代码不能为空")
        return
    if code in indices:
        print(f"  {YELLOW}[!]{RESET} 指数 {code} 已在对比池中")
        return
    print("  请输入指数名称（如 中证500）:")
    try:
        name = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not name:
        print(f"  {YELLOW}[!]{RESET} 名称不能为空")
        return
    new_indices = dict(indices)
    new_indices[code] = name
    set_config("comparison_indices", new_indices)
    print(f"  {GREEN}[OK]{RESET} 已添加 {code} ({name})")


def _remove_comparison_index(config: dict, indices: dict[str, str]) -> None:
    """从对比池中删除指数。"""
    if not indices:
        print(f"  {YELLOW}[!]{RESET} 对比池为空，无指数可删除")
        return
    items = list(indices.items())
    print("  选择要删除的指数编号:")
    for i, (code, name) in enumerate(items, 1):
        print(f"    [{i}] {code} ({name})")
    print("    [0] 取消")
    try:
        choice = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    try:
        idx = int(choice)
    except (ValueError, TypeError):
        print(f"  {YELLOW}[!]{RESET} 无效编号")
        return
    if idx == 0:
        return
    if 1 <= idx <= len(items):
        code, name = items[idx - 1]
        new_indices = dict(indices)
        del new_indices[code]
        set_config("comparison_indices", new_indices)
        print(f"  {GREEN}[OK]{RESET} 已删除 {code} ({name})")
    else:
        print(f"  {YELLOW}[!]{RESET} 编号超出范围")


def _cmd_config_report_boards() -> None:
    """配置报告可选章节（基金分析 / 市场新闻 / 历史走势）。"""
    from src.python.config import (
        get_config,
        is_enable_b_series,
        is_enable_history,
        is_enable_news,
        set_config,
    )

    while True:
        config = get_config()
        b_series = is_enable_b_series(config)
        news = is_enable_news(config)
        history = is_enable_history(config)

        print()
        print("  ┌── 配置报告可选章节 ────────────────────┐")
        b_status = f"{GREEN}启用{RESET}" if b_series else f"{RED}禁用{RESET}"
        n_status = f"{GREEN}启用{RESET}" if news else f"{RED}禁用{RESET}"
        h_status = f"{GREEN}启用{RESET}" if history else f"{RED}禁用{RESET}"
        print(f"  │ 1. 基金深度分析（#6~9）         [{b_status}]{' ' * 8}│")
        print(f"  │ 2. 市场新闻（#10）              [{n_status}]{' ' * 8}│")
        print(f"  │ 3. 组合历史走势+回撤（#16~17）  [{h_status}]{' ' * 8}│")
        print("  │                                   │")
        print("  │ 4. LLM 分析章节（全球政经/智囊团/体检/穿透等） — 请在菜单 S 配置 │")
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
            print(f"  {GREEN}[OK]{RESET} 基金深度分析已{'禁用' if b_series else '启用'}")
        elif choice == "2":
            set_config("enable_news", not news)
            print(f"  {GREEN}[OK]{RESET} 市场新闻已{'禁用' if news else '启用'}")
        elif choice == "3":
            set_config("enable_history", not history)
            print(f"  {GREEN}[OK]{RESET} 组合历史走势已{'禁用' if history else '启用'}")
        elif choice == "4":
            print(f"  {YELLOW}[!]{RESET} LLM 分析章节配置请使用菜单 [S]")
        else:
            print(f"  {YELLOW}[!]{RESET} 无效编号")

    refresh_config()
    press_any_key()


def _cmd_refresh_config() -> None:
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
        print(f"  {YELLOW}[!]{RESET} LLM 未配置（llm_key.json 或 llm_providers.json 缺失或无效）")
    press_any_key()


def _cmd_config_anonymization_mode() -> None:
    """配置持仓匿名化（关闭/代码显示/完全匿名/汇总）。"""
    from src.python.anonymizer import (
        ANONYMIZATION_MODE_DESCRIPTIONS,
        get_anonymization_mode,
        set_anonymization_mode,
    )

    # 定义显示顺序
    _ORDERED_KEYS = ["off", "code_display", "full_anonymous", "summary"]

    while True:
        current = get_anonymization_mode()
        print()
        print(f"  ┌── 配置持仓匿名化 {'─' * 36}┐")
        print(f"  │ 当前模式: {current}{' ' * (32 - len(current))}│")
        print(f"  │{'─' * 48}│")
        for idx, mode_key in enumerate(_ORDERED_KEYS, 1):
            desc = ANONYMIZATION_MODE_DESCRIPTIONS.get(mode_key, mode_key)
            marker = "►" if mode_key == current else " "
            print(f"  │ {marker} {idx}. {desc}{' ' * max(1, 42 - len(desc))}│")
        print(f"  │{'─' * 48}│")
        print("  │ 0. 返回主菜单                              │")
        print(f"  └{'─' * 48}┘")
        print()
        try:
            choice = input("  请选择 (0-4): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            break

        try:
            idx = int(choice)
            if 1 <= idx <= len(_ORDERED_KEYS):
                new_mode = _ORDERED_KEYS[idx - 1]
                if new_mode == current:
                    print(f"  {YELLOW}[!]{RESET} 已是当前模式")
                else:
                    set_anonymization_mode(new_mode)
                    print(f"  {GREEN}[OK]{RESET} 持仓匿名化已切换为: {new_mode}")
            else:
                print(f"  {YELLOW}[!]{RESET} 无效编号")
        except (ValueError, TypeError):
            print(f"  {YELLOW}[!]{RESET} 请输入有效编号")

    press_any_key()

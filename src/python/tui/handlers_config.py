"""TUI 配置管理命令处理器。

所有配置管理相关的 TUI 命令处理函数（菜单 C/F/O/P/S/R/A/I）。
"""

from __future__ import annotations

import json
import os

from src.python.config import set_config
from src.python.core.constants import PROJECT_ROOT
from src.python.core.logger import setup_logger
from src.python.core.reader import list_xlsx_files
from src.python.tui.tui_menu import (
    GREEN,
    RED,
    RESET,
    YELLOW,
    filter_menu_llm_modules,
    get_config_cache,
    press_any_key,
    refresh_config,
)
from src.python.tui.text_layout import display_width, pad_right, render_panel

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

    委托 config 层共享写入原语 write_llm_settings（自本函数抽取），行为一致。
    """
    from src.python.config._llm_settings import write_llm_settings

    write_llm_settings(settings, path)


def _edit_single_config(key: str, label: str, default: str = "", *, pre_hook=None) -> None:
    """通用单配置项编辑命令。

    封装 刷新 → 显示当前值 → 输入新值 → 保存 的重复模式。

    Args:
        key: config.json 中的键名
        label: 显示用名称
        default: 默认值
        pre_hook: 可选前置回调（如显示文件列表），无参回调
    """
    refresh_config()
    config = get_config_cache() or {}
    current = config.get(key, default)
    if pre_hook:
        pre_hook()
    print(f"  当前{label}: {current}")
    print(f"  请输入新{label}（留空则不修改）:")
    try:
        new_val = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if new_val:
        set_config(key, new_val)
        refresh_config()
        print(f"  {GREEN}[OK]{RESET} {label}已更新为: {new_val}")
    else:
        print("  未修改")


def _list_xlsx_preview() -> None:
    """列出当前 holdings_dir 中的 xlsx 文件（供 _cmd_config_filename 使用）。"""
    config = get_config_cache() or {}
    files = list_xlsx_files(config.get("holdings_dir", ""))
    if files:
        print("  当前目录中的 xlsx 文件:")
        for i, f in enumerate(files, 1):
            print(f"    [{i}] {os.path.basename(f)}")
        print()


def _cmd_config_dir() -> None:
    """配置持仓目录。"""
    _edit_single_config("holdings_dir", "目录")


def _cmd_config_filename() -> None:
    """配置持仓文件名。"""
    _edit_single_config("holdings_filename", "文件名", pre_hook=_list_xlsx_preview)


def _cmd_config_output_dir() -> None:
    """配置报告输出目录。"""
    _edit_single_config("output_dir", "报告输出目录", default="reports")


def _cmd_config_llm_modules() -> None:
    """配置各 LLM 报告的启用/停用，以及全部功能开关（llm_settings.json + features.json）。

    标准 LLM 模块通过 enabled_llm 控制，存储在 llm_settings.json。
    功能开关（辩论模式增强、决策跨期反思闭环、量化指标、交互图表、系统自检、
    数据源适配契约等）通过 Feature Flag 控制，存储在 features.json；两块的分组、
    显示名与顺序均取自 ``features.feature_switch_registry``，新增开关自动上屏，
    渠道层不另写清单。
    辩论白脸/黑脸/综合（debate_pro/con/synthesis）保留在注册表
    （缓存 TTL/前缀清理仍依赖），菜单层隐藏，不在此面板展示。
    """
    from src.python.config.features import (
        GROUP_EXPERIMENTAL,
        GROUP_LABELS,
        GROUP_REPORT,
        GROUP_STANDARD,
        is_feature_enabled,
        save_feature_overrides,
        set_feature_enabled,
        switches_in_group,
    )
    from src.python.core.registry import get_llm_module_names

    result = _read_llm_settings()
    if result is None:
        return
    settings, settings_path = result

    enabled_map = settings.get("enabled_llm", {})
    # 菜单层隐藏辩论三模块（注册表保留：缓存 TTL/前缀清理仍依赖）
    # 实际辩论开关由下方实验性 Feature Flag（正反辩论等）控制
    module_names = filter_menu_llm_modules(get_llm_module_names())

    # 功能开关分块：(分组标题, [(flag_key, 显示名), ...])，顺序即注册表顺序
    switch_blocks = [
        (GROUP_LABELS[group], [(flag, d.label) for flag, d in switches_in_group(group)])
        for group in (GROUP_EXPERIMENTAL, GROUP_STANDARD, GROUP_REPORT)
    ]
    # 行首 ⚗ 标记仅给实验组（常规组靠分组标题区分，无需逐行标记）
    experiment_flags = {flag for flag, _d in switches_in_group(GROUP_EXPERIMENTAL)}

    # 名称列宽：取清单内最长显示名，使各行状态方括号纵向对齐（超宽名不截断）
    name_column = max(
        map(
            display_width,
            [
                *module_names.values(),
                *(label for _title, block in switch_blocks for _flag, label in block),
            ],
        )
    )

    while True:
        rows: list[str | None] = []
        items: list[tuple[int, str, str, bool, str]] = []

        # ① 标准 LLM 模块（1-5）
        for i, (sfx, name) in enumerate(module_names.items(), 1):
            status = enabled_map.get(sfx, True)
            status_str = f"{GREEN}开启{RESET}" if status else f"{RED}关闭{RESET}"
            items.append((i, sfx, name, status, "llm"))
            rows.append(f"{i}. {pad_right(name, name_column)} [{status_str}]")

        # ② 功能开关：编号紧随标准模块之后，实验块在前、常规块在其后，逐块顺序派发
        # 编号由分组与块内顺序派生、非硬编码：某项转正即离开实验块，落进常规块中
        # 它在注册表声明处的顺序位置
        next_serial = len(module_names) + 1
        for title, block in switch_blocks:
            rows.append(None)
            rows.append(title)
            for j, (flag, label) in enumerate(block, next_serial):
                status = is_feature_enabled(flag)
                status_str = f"{GREEN}开启{RESET}" if status else f"{RED}关闭{RESET}"
                marker = "⚗" if flag in experiment_flags else ""
                items.append((j, flag, label, status, "feature"))
                rows.append(f"{j}. {marker}{pad_right(label, name_column)} [{status_str}]")
            next_serial += len(block)

        rows.append("0. 返回主菜单")
        print()
        print("\n".join(render_panel("配置 LLM 报告章节与功能开关", rows)))
        print("  ⚗ 实验性功能默认关闭，开启后按各自说明增强报告输出")
        print("     ⚠ 当前为实验阶段，输出质量可能不稳定")
        print("  常规开关默认开启，关闭即按各自说明收回对应能力（详见 how-to-config 手册）")
        print("  报告章节与增强默认多数关闭，开启即新增对应章节/列（依赖见各条说明）")
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
        rows: list[str | None] = ["自定义基准指数，用于报告中组合 vs 多指数对比", f"当前指数 ({len(indices)} 个):"]
        if indices:
            for i, (code, name) in enumerate(indices.items(), 1):
                rows.append(f"  {i}. {code} ({name})")
        else:
            rows.append("  空池（仅显示沪深300）")
        rows += [None, "A. 添加指数", "D. 删除指数", "R. 重置为默认预设", "0. 返回主菜单"]
        print()
        print("\n".join(render_panel("管理对比指数池", rows)))
        print()
        try:
            choice = input("  请选择 (A/D/R/0): ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            break
        elif choice == "A":
            _add_comparison_index(indices)
        elif choice == "D":
            _remove_comparison_index(indices)
        elif choice == "R":
            default_pool = _DEFAULT_CONFIG.get("comparison_indices", {})
            set_config("comparison_indices", dict(default_pool))
            print(f"  {GREEN}[OK]{RESET} 对比指数池已重置为默认预设")
        elif choice in ("A", "D", "R"):
            continue
        else:
            print(f"  {YELLOW}[!]{RESET} 无效选择，请重试")

    press_any_key()


def _add_comparison_index(indices: dict[str, str]) -> None:
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


def _remove_comparison_index(indices: dict[str, str]) -> None:
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
    """配置基础报告章节（基金深度分析 / 市场新闻 / 组合历史走势+回撤 / 组合演进 / 行动建议）。

    报告章节与增强子模块（数据质量/估值分位/市场温度/财报摘要/财务指标等）已在
    功能开关注册表的「报告章节与增强」组，统一在菜单 [S] 配置（本面板不再另设入口）。
    """
    from src.python.config import (
        get_config,
        is_enable_action,
        is_enable_fund_deep_analysis,
        is_enable_history,
        is_enable_news,
        is_enable_portfolio_evolution,
        set_config,
    )

    while True:
        config = get_config()
        fund_deep_analysis = is_enable_fund_deep_analysis(config)
        news = is_enable_news(config)
        history = is_enable_history(config)
        portfolio_evolution = is_enable_portfolio_evolution(config)
        action = is_enable_action(config)

        fund_status = f"{GREEN}启用{RESET}" if fund_deep_analysis else f"{RED}禁用{RESET}"
        n_status = f"{GREEN}启用{RESET}" if news else f"{RED}禁用{RESET}"
        h_status = f"{GREEN}启用{RESET}" if history else f"{RED}禁用{RESET}"
        e_status = f"{GREEN}启用{RESET}" if portfolio_evolution else f"{RED}禁用{RESET}"
        a_status = f"{GREEN}启用{RESET}" if action else f"{RED}禁用{RESET}"
        # 编号后的章节名补齐到同一列，使状态方括号纵向对齐
        section_column = max(
            map(display_width, ["基金深度分析", "市场新闻", "组合历史走势+回撤", "组合演进", "行动建议"])
        )
        rows = [
            f"1. {pad_right('基金深度分析', section_column)} [{fund_status}]",
            f"2. {pad_right('市场新闻', section_column)} [{n_status}]",
            f"3. {pad_right('组合历史走势+回撤', section_column)} [{h_status}]",
            f"4. {pad_right('组合演进', section_column)} [{e_status}]",
            f"5. {pad_right('行动建议', section_column)} [{a_status}]",
            "",
            "6. 报告增强子模块 / LLM 分析章节 — 请在菜单 S 配置",
            "0. 返回主菜单",
        ]
        print()
        print("\n".join(render_panel("配置报告可选章节", rows)))
        print()
        try:
            choice = input("  输入编号切换 (0-6): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            break

        if choice == "1":
            set_config("enable_fund_deep_analysis", not fund_deep_analysis)
            print(f"  {GREEN}[OK]{RESET} 基金深度分析已{'禁用' if fund_deep_analysis else '启用'}")
        elif choice == "2":
            set_config("enable_news", not news)
            print(f"  {GREEN}[OK]{RESET} 市场新闻已{'禁用' if news else '启用'}")
        elif choice == "3":
            set_config("enable_history", not history)
            print(f"  {GREEN}[OK]{RESET} 组合历史走势+回撤已{'禁用' if history else '启用'}")
        elif choice == "4":
            set_config("enable_portfolio_evolution", not portfolio_evolution)
            print(f"  {GREEN}[OK]{RESET} 组合演进已{'禁用' if portfolio_evolution else '启用'}")
        elif choice == "5":
            set_config("enable_action", not action)
            print(f"  {GREEN}[OK]{RESET} 行动建议已{'禁用' if action else '启用'}")
        elif choice == "6":
            print(f"  {YELLOW}[!]{RESET} 报告增强子模块与 LLM 分析章节请使用菜单 [S] 配置")
        else:
            print(f"  {YELLOW}[!]{RESET} 无效编号")

    refresh_config()
    press_any_key()


def _cmd_refresh_config() -> None:
    """重新加载所有配置（config.json + llm_settings.json + llm_key.json）。"""
    from src.python.config import get_config, get_llm_config
    from src.python.config._core import invalidate_config_cache
    from src.python.config._llm_settings import invalidate_llm_config_cache
    from src.python.llm.pricing import reload_pricing

    invalidate_config_cache()
    invalidate_llm_config_cache()

    config = get_config()
    llm_config = get_llm_config()
    reload_pricing()

    # 刷新 BatchDispatcher 限速器配置（batch_rate_limit 即时生效）
    from src.python.fetcher.batch import get_rate_limiter

    get_rate_limiter.cache_clear()

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
    from src.python.config.anonymizer import (
        ANONYMIZATION_MODE_DESCRIPTIONS,
        get_anonymization_mode,
        set_anonymization_mode,
    )

    # 定义显示顺序
    _ORDERED_KEYS = ["off", "code_display", "full_anonymous", "summary"]

    # 说明列宽：取最长模式说明，使选中标记、编号与说明各占固定列
    desc_column = max(map(display_width, ANONYMIZATION_MODE_DESCRIPTIONS.values()))

    while True:
        current = get_anonymization_mode()
        rows: list[str | None] = [f"当前模式: {current}", None]
        for idx, mode_key in enumerate(_ORDERED_KEYS, 1):
            desc = ANONYMIZATION_MODE_DESCRIPTIONS.get(mode_key, mode_key)
            marker = "►" if mode_key == current else " "
            rows.append(f"{marker} {idx}. {pad_right(desc, desc_column)}")
        rows += [None, "0. 返回主菜单"]
        print()
        print("\n".join(render_panel("配置持仓匿名化", rows)))
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

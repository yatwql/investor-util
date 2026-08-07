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
    """配置各 LLM 报告的启用/停用（llm_settings.json + features.json 辩论开关）。

    标准 LLM 模块（1-5）通过 enabled_llm 控制，存储在 llm_settings.json。
    辩论模式增强（6-8）通过 Feature Flag 控制，存储在 features.json。
    辩论白脸/黑脸/综合（debate_pro/con/synthesis）保留在注册表
    （缓存 TTL/前缀清理仍依赖），菜单层隐藏，不在此面板展示。
    """
    from src.python.config.features import is_feature_enabled, save_feature_overrides, set_feature_enabled
    from src.python.core.registry import get_llm_module_names

    result = _read_llm_settings()
    if result is None:
        return
    settings, settings_path = result

    enabled_map = settings.get("enabled_llm", {})
    # 菜单层隐藏辩论三模块（注册表保留：缓存 TTL/前缀清理仍依赖）
    # 实际辩论开关由下方实验性 Feature Flag（正反辩论等）控制
    module_names = filter_menu_llm_modules(get_llm_module_names())

    # 辩论模式开关定义：(flag_key, 显示名, 说明)
    DEBATE_FLAGS: list[tuple[str, str, str]] = [
        ("llm_debate_procon", "辩论-正反辩论", "三段式(白脸→黑脸→综合)"),
        ("llm_debate_conditional", "辩论-条件推理", "情景化分析(涨/跌/震荡)"),
        ("llm_debate_qa_concentration", "辩论-集中度问答", "集中度风险问答"),
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
    """配置报告可选章节（基金深度分析 / 市场新闻 / 组合历史走势+回撤 / 组合演进 / 行动建议 / 报告增强子模块）。"""
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

        print()
        print("  ┌── 配置报告可选章节 ────────────────────┐")
        fund_status = f"{GREEN}启用{RESET}" if fund_deep_analysis else f"{RED}禁用{RESET}"
        n_status = f"{GREEN}启用{RESET}" if news else f"{RED}禁用{RESET}"
        h_status = f"{GREEN}启用{RESET}" if history else f"{RED}禁用{RESET}"
        e_status = f"{GREEN}启用{RESET}" if portfolio_evolution else f"{RED}禁用{RESET}"
        a_status = f"{GREEN}启用{RESET}" if action else f"{RED}禁用{RESET}"
        print(f"  │ 1. 基金深度分析      [{fund_status}]{' ' * 8}│")
        print(f"  │ 2. 市场新闻          [{n_status}]{' ' * 8}│")
        print(f"  │ 3. 组合历史走势+回撤  [{h_status}]{' ' * 8}│")
        print(f"  │ 4. 组合演进          [{e_status}]{' ' * 8}│")
        print(f"  │ 5. 行动建议          [{a_status}]{' ' * 8}│")
        print("  │                                   │")
        print("  │ 6. 报告增强子模块（数据质量/行业Beta/候选比较/成本流水/估值分位/市场温度）│")
        print("  │ 7. LLM 分析章节（全球政经/智囊团/体检/穿透等） — 请在菜单 S 配置 │")
        print(f"  │ 0. 返回主菜单{' ' * 27}│")
        print(f"  └{'─' * 42}┘")
        print()
        try:
            choice = input("  输入编号切换 (0-7): ").strip()
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
            _cmd_config_report_submodules()
        elif choice == "7":
            print(f"  {YELLOW}[!]{RESET} LLM 分析章节配置请使用菜单 [S]")
        else:
            print(f"  {YELLOW}[!]{RESET} 无效编号")

    refresh_config()
    press_any_key()


def _cmd_config_report_submodules() -> None:
    """配置报告增强子模块（数据质量仪表盘 / 行业Beta子表 / 候选基金比较 / 成本流水 / 估值分位 / 市场温度）。

    6 项增强子模块独立启停，实时保存到 config.json 的 `report_submodules`（数据质量仪表盘默认开，其余默认关）。
    开启后对应章节按需增强区块（数据源可用性矩阵 / 风格与因子分析 / 基金业绩分析 /
    资产穿透TOP10 / 投资分析汇总），不改变既有章节输出。
    """
    from src.python.config import (
        get_config,
        is_enable_candidate_compare,
        is_enable_cost_lots,
        is_enable_data_quality,
        is_enable_industry_beta,
        is_enable_market_temperature,
        is_enable_valuation_percentile,
        set_config,
    )

    # 子模块定义：(配置键, 显示名, 说明)
    SUBMODULES: list[tuple[str, str, str]] = [
        ("data_quality", "数据质量仪表盘", "数据源可用性矩阵增强（覆盖/时效/降级状态）"),
        ("industry_beta", "行业Beta子表", "风格与因子分析：行业暴露 + 回归敏感性"),
        ("candidate_compare", "候选基金比较子表", "基金业绩分析：候选基金横向比较"),
        ("cost_lots", "成本流水", "成本分档 + XIRR + 分红累计"),
        ("valuation_percentile", "估值分位", "资产穿透TOP10 估值分位列"),
        ("market_temperature", "市场温度", "投资分析汇总 市场温度刻度行"),
    ]
    accessors = {
        "data_quality": is_enable_data_quality,
        "industry_beta": is_enable_industry_beta,
        "candidate_compare": is_enable_candidate_compare,
        "cost_lots": is_enable_cost_lots,
        "valuation_percentile": is_enable_valuation_percentile,
        "market_temperature": is_enable_market_temperature,
    }

    while True:
        config = get_config()
        print()
        print("  ┌── 配置报告增强子模块 ───────────────────┐")
        items: list[tuple[int, str, bool]] = []
        for i, (key, label, _desc) in enumerate(SUBMODULES, 1):
            status = accessors[key](config)
            status_str = f"{GREEN}开启{RESET}" if status else f"{RED}关闭{RESET}"
            items.append((i, key, status))
            print(f"  │ {i}. {label:<14s} [{status_str}]{' ' * 4}│")
        print(f"  │ 0. 返回上一级{' ' * 25}│")
        print(f"  └{'─' * 42}┘")
        print()
        try:
            choice = input("  输入编号切换 (0-6): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "0":
            break

        try:
            idx = int(choice)
            matched = [it for it in items if it[0] == idx]
            if not matched:
                print(f"  {YELLOW}[!]{RESET} 无效编号")
                continue
            _, key, curr = matched[0]
            submodules = dict(config.get("report_submodules") or {})
            submodules[key] = not curr
            set_config("report_submodules", submodules)
            label = next(lb for k, lb, _ in SUBMODULES if k == key)
            print(f"  {GREEN}[OK]{RESET} {label} 已{'开启' if not curr else '关闭'}")
            refresh_config()
        except (ValueError, TypeError):
            print(f"  {YELLOW}[!]{RESET} 请输入有效编号")

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

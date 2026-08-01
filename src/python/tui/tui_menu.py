"""TUI 菜单定义与渲染模块。

职责：
  - MenuItem 类型定义
  - MENU_ITEMS 菜单列表
  - 菜单渲染（render_menu、print_header、print_sep）
  - 配置显示（show_config、_show_llm_config_status）
  - 快捷键查找（index_by_key）
  - 通用 UI 辅助（exit_app、press_any_key、refresh_config）
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from src.python.core.ansi_colors import GREEN, RED, RESET, YELLOW
from src.python.config import get_config, get_llm_config

# 每个菜单项：(快捷键, 显示标签, 回调函数, 是否退出项)
MenuItem = tuple[str, str, Callable[[], None] | None, bool]

MENU_ITEMS: list[MenuItem] = [
    ("E", "生成基础版Excel分析报告", None, False),
    ("B", "生成标准报告(Excel+HTML) [按章节配置]", None, False),
    ("L", "生成完整报告(Excel+HTML) [含LLM，按章节配置]", None, False),
    ("C", "配置持仓信息目录", None, False),
    ("F", "配置持仓信息文件名", None, False),
    ("O", "配置报告输出目录", None, False),
    ("1", "更新基础类缓存（含基金业绩/持仓/经理/基准等）", None, False),
    ("2", "更新行情类缓存（含价格/指数等）", None, False),
    ("3", "清理过期缓存文件", None, False),
    ("4", "查看缓存/状态统计", None, False),
    ("P", "配置报告可选章节（基金分析/市场新闻/历史走势）", None, False),
    ("I", "管理对比指数池（自定义基准指数）", None, False),
    ("A", "配置持仓匿名化（代码/名称脱敏）", None, False),
    ("S", "配置LLM分析章节", None, False),
    ("R", "刷新配置", None, False),
    ("X", "退出", None, True),
]

_config_cache: dict | None = None


def refresh_config() -> dict:
    """刷新并返回配置缓存。"""
    global _config_cache
    _config_cache = get_config()
    return _config_cache


def get_config_cache() -> dict | None:
    """返回当前配置缓存（只读访问）。"""
    return _config_cache


# ── LLM 菜单隐藏模块 ──────────────────────────────────────
# 旧设计遗留的辩论三模块（debate_pro/con/synthesis）在注册表中保留
# （缓存 TTL/前缀清理仍依赖），但不在菜单/状态面板展示，避免误导为可开关模块。
# 实际辩论开关由 features.json 的实验性 Flag（正反辩论/条件推理/集中度问答）控制。
LLM_MENU_HIDDEN_KEYS: frozenset[str] = frozenset({"debate_pro", "debate_con", "debate_synthesis"})


def filter_menu_llm_modules(module_names: dict[str, str]) -> dict[str, str]:
    """菜单层过滤：剔除隐藏的 LLM 模块（注册表条目保留）。"""
    return {k: v for k, v in module_names.items() if k not in LLM_MENU_HIDDEN_KEYS}


# ── 界面输出 ──────────────────────────────────────────────


def print_sep(char: str = "=", width: int = 56) -> None:
    print(char * width)


def print_header() -> None:
    """打印程序标题头（每次主循环迭代时重绘）。"""
    from src.python.core.constants import APP_VERSION

    print_sep()
    print(f"        个人投资分析报告生成小助手  v{APP_VERSION}")
    print_sep()

    # 首次运行引导：检测是否缺少关键资源
    config = _config_cache if _config_cache is not None else refresh_config()
    holdings = os.path.join(config.get("holdings_dir", ""), config.get("holdings_filename", ""))
    _first_run_hints = []
    if not os.path.exists(holdings):
        _first_run_hints.append("• 请先通过菜单 [C]/[F] 配置持仓文件路径，或放置文件到默认目录")
    llm_conf = get_llm_config()
    if llm_conf is None or not (llm_conf.get("api_key") or llm_conf.get("_provider_list")):
        _first_run_hints.append(
            "• 如需 LLM 分析，请配置 data/config/llm_key.json 或 llm_providers.json（菜单 [S] 查看状态）"
        )
    if _first_run_hints:
        print("  📋 首次使用指引：")
        for hint in _first_run_hints:
            print(f"    {hint}")
        print()


def render_menu(sel: int) -> None:
    """打印带选择指示器的菜单。"""
    print()
    for i, (key, label, _cb, is_exit) in enumerate(MENU_ITEMS):
        prefix = "  >" if i == sel else "   "
        print(f"{prefix} [{key}] {label}")
    print()
    print("  方向键移动 | Enter 确认 | 字母/数字键直达 | Ctrl+C 退出")
    print()


def show_config() -> None:
    """显示当前配置及 LLM 配置状态。"""
    config = _config_cache if _config_cache is not None else refresh_config()
    holdings_path = os.path.join(config.get("holdings_dir", ""), config.get("holdings_filename", ""))
    print(f"  持仓目录: {config.get('holdings_dir', '未设置')}")
    print(f"  持仓文件: {config.get('holdings_filename', '未设置')}")
    print(f"  输出目录: {config.get('output_dir', 'reports')}")
    print(f"  新闻抓取上限: {config.get('news_top_count', '100')} 条")
    if os.path.exists(holdings_path):
        print("  状态: [OK] 文件就绪")
    else:
        print("  状态: [!!] 文件未找到")
    _show_privacy_and_security_status()
    _show_llm_config_status()
    print()


def _show_privacy_and_security_status() -> None:
    """显示隐私提示和匿名化安全状态。"""
    from src.python.config import get_config as _get_cfg

    _cfg = _get_cfg()
    _anon_mode = _cfg.get("features", {}).get("anonymization", {}).get("mode", "off")
    _anon_labels = {"off": "关闭", "code_display": "代码显示", "full_anonymous": "完全匿名", "summary": "汇总"}
    _anon_display = _anon_labels.get(_anon_mode, _anon_mode)

    # 检查隐私提示是否已显示过
    _privacy_shown = _cfg.get("_privacy_notice_shown", False)
    _privacy_icon = f"{GREEN}✓{RESET}" if _privacy_shown else f"{YELLOW}待首次报告生成时显示{RESET}"

    print(f"  持仓匿名化: {_anon_display}")
    print(f"  隐私声明: {_privacy_icon}")
    print()


def _show_llm_config_status() -> None:
    """显示 LLM 配置状态（绿色已配置 / 红色未配置），含多链详细信息。"""
    from src.python.llm.circuit_breaker import get_circuit_status
    from src.python.core.registry import get_llm_module_names

    llm_config = get_llm_config()
    if llm_config is None:
        print(f"  LLM: {RED}未配置{RESET}（配置 data/config/llm_key.json 或 llm_providers.json 后重启生效）")
        return

    provider_list = llm_config.get("_provider_list") or []

    # ── credentials_ref 多链模式 ──
    if provider_list and not llm_config.get("api_key"):
        _show_multi_chain_status(llm_config, provider_list)
        return

    # ── 传统 flat 模式：单 provider ──
    if not llm_config.get("api_key") or not llm_config.get("provider"):
        print(f"  LLM: {RED}未配置{RESET}（配置 data/config/llm_key.json 或 llm_providers.json 后重启生效）")
        return

    provider = llm_config["provider"]
    model = llm_config.get("model") or "默认"
    endpoint = llm_config.get("endpoint") or "默认"
    ep_display = (
        endpoint.split("/")[2] if endpoint and endpoint != "默认" and len(endpoint.split("/")) > 2 else endpoint
    )

    # 单 provider 熔断状态
    cb_status = get_circuit_status(endpoint) if endpoint and endpoint != "默认" else "—"
    cb_display = f" |  熔断: {cb_status}" if cb_status != "—" else ""

    print(f"  LLM: {GREEN}已配置{RESET}  provider={provider}  model={model}  endpoint={ep_display}{cb_display}")
    _route_parts = []
    for _sfx, _name in filter_menu_llm_modules(get_llm_module_names()).items():
        _mv = llm_config.get(f"model_{_sfx}") or model
        _route_parts.append(f"{_name}={_mv}")
    print(f"         模型路由: {' / '.join(_route_parts)}")


def _show_multi_chain_status(llm_config: dict, provider_list: list[dict]) -> None:
    """显示多 Provider 链式服务的详细信息。

    展示策略、各 Provider 的后端/模型/优先级/熔断状态。
    单独提取为函数以保持 _show_llm_config_status 清晰。
    """
    from src.python.llm.circuit_breaker import get_circuit_status
    from src.python.core.registry import get_llm_module_names

    strategy_raw = llm_config.get("_strategy", "priority")
    strategy_labels = {
        "priority": "优先级排序",
        "weighted": "加权随机",
        "cost_first": "价格最低优先",
        "fallback_only": "仅 Fallback",
    }
    strategy_label = strategy_labels.get(strategy_raw, strategy_raw)

    print(f"  LLM: {GREEN}已配置{RESET}")
    print(f"  策略: {strategy_label}  |  多链服务 ({len(provider_list)} provider)")

    # 每个 provider 一行列表显示（含后端类型、模型、优先级、熔断状态）
    for i, entry in enumerate(provider_list, 1):
        name = entry.get("name", "?")
        backend = entry.get("provider", "?")

        # 解析模型和 endpoint（优先 entry 内联，再查 _llm_credentials）
        model = entry.get("model", "")
        endpoint = entry.get("endpoint") or ""
        creds_ref = entry.get("credentials_ref")
        if creds_ref and (not model or not endpoint):
            all_creds = llm_config.get("_llm_credentials", {})
            ref_creds = all_creds.get(creds_ref, {})
            if isinstance(ref_creds, dict):
                if not model:
                    model = ref_creds.get("model", "")
                if not endpoint:
                    endpoint = ref_creds.get("endpoint", "") or ""

        model_display = model or "默认"

        # 优先级显示
        raw_priority = entry.get("priority")
        priority_display = str(raw_priority) if raw_priority is not None else "50（默认）"

        # 熔断状态
        cb_status = get_circuit_status(endpoint) if endpoint else "—"
        cb_icon = f"{GREEN}✓{RESET}" if cb_status == "正常" else f"{RED}⚠{RESET}"

        print(f"    [{i}] {name}  ({backend})")
        print(f"         模型: {model_display}")
        print(f"         优先级: {priority_display}    熔断: {cb_icon} {cb_status}")

    # 模块级 provider 偏好（如有）
    preferred = llm_config.get("_preferred_providers", {})
    if preferred:
        parts = []
        for mk, pname in preferred.items():
            display_name = get_llm_module_names().get(mk, mk)
            parts.append(f"{display_name} → {pname}")
        print(f"    ▶ 模块偏好: {' / '.join(parts)}")


# ── 快捷键查找 ──────────────────────────────────────────────


def index_by_key(key: str) -> int | None:
    """返回快捷键对应的菜单索引，未找到则返回 None。"""
    for i, (k, _label, _cb, _is_exit) in enumerate(MENU_ITEMS):
        if k == key:
            return i
    return None


# ── 通用 UI 辅助 ──────────────────────────────────────────────


def press_any_key() -> None:
    """等待用户按任意键继续。支持 Ctrl+C 退出。"""
    from src.python.tui.tui_keys import KEY_CTRL_C, get_key

    print("  按任意键返回菜单...")
    k = get_key()
    if k == KEY_CTRL_C:
        exit_app()


def exit_app() -> None:
    """打印退出信息并终止程序。"""
    print()
    print("  感谢使用，再见！")
    sys.exit(0)

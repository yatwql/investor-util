"""TUI 菜单定义与渲染模块。

职责：
  - MenuItem 类型定义
  - MENU_ITEMS 菜单列表
  - 菜单渲染（_render_menu、_print_header、_print_sep）
  - 配置显示（_show_config、_show_llm_config_status）
  - 快捷键查找（_index_by_key）
  - 通用 UI 辅助（_exit_app、_press_any_key、_refresh_config）
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

try:
    import colorama  # type: ignore[import-untyped]
    colorama.init()  # 包装 stdout，ANSI → Win32 API，不依赖终端原生 ANSI 支持
except ImportError:
    pass  # 无 colorama 时 Windows 控制台可能无法正确显示颜色，但功能不受影响

# ANSI 颜色：非 TTY 或设置了 NO_COLOR 环境变量时禁用颜色输出
if "NO_COLOR" in os.environ or not sys.stdout.isatty():
    _GREEN = _RED = _YELLOW = _RESET = ""
else:
    _GREEN = "\033[92m"
    _RED = "\033[91m"
    _YELLOW = "\033[93m"
    _RESET = "\033[0m"

from src.python.config import get_config, get_llm_config

# 每个菜单项：(快捷键, 显示标签, 回调函数, 是否退出项)
MenuItem = tuple[str, str, Callable[[], None] | None, bool]

MENU_ITEMS: list[MenuItem] = [
    ("E", "生成基础版Excel分析报告", None, False),
    ("H", "生成基础版HTML分析报告", None, False),
    ("B", "生成全系列包含新闻的报告(Excel+HTML) [含基金深度分析]", None, False),
    ("L", "生成全系列完整版报告(Excel+HTML) [含基金深度分析]", None, False),
    ("C", "配置持仓信息目录", None, False),
    ("F", "配置持仓信息文件名", None, False),
    ("O", "配置报告输出目录", None, False),
    ("1", "更新基础类缓存（含基金业绩/持仓/经理/基准等）", None, False),
    ("2", "更新持仓类缓存", None, False),
    ("3", "清理过期缓存文件", None, False),
    ("4", "查看缓存统计信息", None, False),
    ("S", "配置支持LLM的报告分析章节", None, False),
    ("R", "刷新配置", None, False),
    ("X", "退出", None, True),
]

_config_cache: dict | None = None


def _refresh_config() -> dict:
    """刷新并返回配置缓存。"""
    global _config_cache
    _config_cache = get_config()
    return _config_cache


def get_config_cache() -> dict | None:
    """返回当前配置缓存（只读访问）。"""
    return _config_cache


# ── 界面输出 ──────────────────────────────────────────────


def _print_sep(char: str = "=", width: int = 56) -> None:
    print(char * width)


def _print_header() -> None:
    """打印程序标题头（仅启动时一次）。"""
    from src.python.constants import APP_VERSION
    _print_sep()
    print(f"        个人投资分析报告生成小助手  v{APP_VERSION}")
    _print_sep()

    # 首次运行引导：检测是否缺少关键资源
    config = _config_cache if _config_cache is not None else _refresh_config()
    holdings = os.path.join(config.get("holdings_dir", ""), config.get("holdings_filename", ""))
    _first_run_hints = []
    if not os.path.exists(holdings):
        _first_run_hints.append("• 请先通过菜单 [C]/[F] 配置持仓文件路径，或放置文件到默认目录")
    llm_conf = get_llm_config()
    if llm_conf is None or not llm_conf.get("api_key"):
        _first_run_hints.append("• 如需 LLM 分析，请配置 data/config/llm_key.json（菜单 [S] 查看状态）")
    if _first_run_hints:
        print("  📋 首次使用指引：")
        for hint in _first_run_hints:
            print(f"    {hint}")
        print()


def _render_menu(sel: int) -> None:
    """打印带选择指示器的菜单。"""
    print()
    for i, (key, label, _cb, is_exit) in enumerate(MENU_ITEMS):
        prefix = "  >" if i == sel else "   "
        print(f"{prefix} [{key}] {label}")
    print()
    print("  方向键移动 | Enter 确认 | 字母/数字键直达 | Ctrl+C 退出")
    print()


def _show_config() -> None:
    """显示当前配置及 LLM 配置状态。"""
    config = _config_cache if _config_cache is not None else _refresh_config()
    holdings_path = os.path.join(config.get("holdings_dir", ""), config.get("holdings_filename", ""))
    print(f"  持仓目录: {config.get('holdings_dir', '未设置')}")
    print(f"  持仓文件: {config.get('holdings_filename', '未设置')}")
    print(f"  输出目录: {config.get('output_dir', 'reports')}")
    print(f"  新闻 TOP: {config.get('news_top_count', '100')} 条")
    if os.path.exists(holdings_path):
        print("  状态: [OK] 文件就绪")
    else:
        print("  状态: [!!] 文件未找到")
    _show_llm_config_status()
    print()


def _show_llm_config_status() -> None:
    """显示 LLM 配置状态（绿色已配置 / 红色未配置）。"""
    llm_config = get_llm_config()
    if llm_config and llm_config.get("api_key") and llm_config.get("provider"):
        provider = llm_config["provider"]
        model = llm_config.get("model") or "默认"
        endpoint = llm_config.get("endpoint") or "默认"
        ep_display = endpoint.split("/")[2] if endpoint and endpoint != "默认" and len(endpoint.split("/")) > 2 else endpoint
        print(f"  LLM: {_GREEN}已配置{_RESET}  provider={provider}  model={model}  endpoint={ep_display}")
        from src.python.registry import get_llm_module_names
        _route_parts = []
        for _sfx, _name in get_llm_module_names().items():
            _mv = llm_config.get(f"model_{_sfx}") or model
            _route_parts.append(f"{_name}={_mv}")
        print(f"         模型路由: {' / '.join(_route_parts)}")
    else:
        print(f"  LLM: {_RED}未配置{_RESET}（配置 data/config/llm_key.json 后重启生效）")


# ── 快捷键查找 ──────────────────────────────────────────────


def _index_by_key(key: str) -> int | None:
    """返回快捷键对应的菜单索引，未找到则返回 None。"""
    for i, (k, _label, _cb, _is_exit) in enumerate(MENU_ITEMS):
        if k == key:
            return i
    return None


# ── 通用 UI 辅助 ──────────────────────────────────────────────


def _press_any_key() -> None:
    """等待用户按任意键继续。支持 Ctrl+C 退出。"""
    from src.python.tui import KEY_CTRL_C, get_key
    print("  按任意键返回菜单...")
    k = get_key()
    if k == KEY_CTRL_C:
        _exit_app()


def _exit_app() -> None:
    """打印退出信息并终止程序。"""
    print()
    print("  感谢使用，再见！")
    sys.exit(0)

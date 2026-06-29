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

import colorama
import os
import sys
from typing import Any, Callable, Optional

colorama.just_fix_windows_console()

from src.python.config import get_config, get_llm_config

# 每个菜单项：(快捷键, 显示标签, 回调函数, 是否退出项)
MenuItem = tuple[str, str, Optional[Callable[[], None]], bool]

MENU_ITEMS: list[MenuItem] = [
    ("E", "生成基础版Excel分析报告", None, False),
    ("N", "生成包含新闻的Excel分析报告", None, False),
    ("H", "生成基础版HTML分析报告", None, False),
    ("B", "生成全系列包含新闻的报告(Excel+HTML)", None, False),
    ("L", "生成全系列完整版报告(Excel+HTML)", None, False),
    ("C", "配置持仓信息目录", None, False),
    ("F", "配置持仓信息文件名", None, False),
    ("R", "配置报告输出目录", None, False),
    ("1", "更新基础类缓存", None, False),
    ("2", "更新持仓类缓存", None, False),
    ("3", "清理过期缓存文件", None, False),
    ("4", "查看缓存统计信息", None, False),
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
    _print_sep()
    print("        个人投资分析报告生成小助手")
    _print_sep()


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
    holdings_path = os.path.join(config["holdings_dir"], config["holdings_filename"])
    print(f"  持仓目录: {config['holdings_dir']}")
    print(f"  持仓文件: {config['holdings_filename']}")
    print(f"  输出目录: {config.get('output_dir', 'reports')}")
    print(f"  新闻 TOP: {config.get('news_top_count', '100')} 条")
    if os.path.exists(holdings_path):
        print(f"  状态: [OK] 文件就绪")
    else:
        print(f"  状态: [!!] 文件未找到")
    _show_llm_config_status()
    print()


def _show_llm_config_status() -> None:
    """显示 LLM 配置状态（绿色已配置 / 红色未配置）。"""
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"

    llm_config = get_llm_config()
    if llm_config and llm_config.get("api_key") and llm_config.get("provider"):
        provider = llm_config["provider"]
        model = llm_config.get("model") or "默认"
        endpoint = llm_config.get("endpoint") or "默认"
        ep_display = endpoint.split("/")[2] if endpoint and endpoint != "默认" else endpoint
        print(f"  LLM: {GREEN}已配置{RESET}  provider={provider}  model={model}  endpoint={ep_display}")
        model_global_macro = llm_config.get("model_global_macro") or model
        model_expert_review = llm_config.get("model_expert_review") or model
        model_news_correlation = llm_config.get("model_news_correlation") or model
        model_health_check = llm_config.get("model_health_check") or model
        model_penetration_deep = llm_config.get("model_penetration_deep") or model
        print(f"         模型路由: 全球政经局势={model_global_macro} / 智囊团深度复盘={model_expert_review} / 财经新闻热点与持仓关联分析={model_news_correlation} / 持仓体检报告={model_health_check} / 穿透深度分析={model_penetration_deep}")
    else:
        print(f"  LLM: {RED}未配置{RESET}（配置 data/config/llm_key.json 后重启生效）")


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

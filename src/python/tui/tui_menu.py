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
from src.python.core.registry import LLM_HIDDEN_KEYS
from src.python.config import get_config

# 每个菜单项：(快捷键, 显示标签, 回调函数, 是否退出项)
MenuItem = tuple[str, str, Callable[[], None] | None, bool]

MENU_ITEMS: list[MenuItem] = [
    ("E", "生成基础版Excel分析报告", None, False),
    ("B", "生成标准报告(Excel+HTML) [按章节配置]", None, False),
    ("L", "生成完整报告(Excel+HTML) [含LLM，按章节配置]", None, False),
    ("W", "调仓 What-if 模拟（对比两份持仓，独立报告）", None, False),
    ("D", "配置目录信息（持仓目录/文件名/输出目录）", None, False),
    ("1", "更新基础类缓存（含基金业绩/持仓/经理/基准等）", None, False),
    ("2", "更新行情类缓存（含价格/指数等）", None, False),
    ("3", "清理过期缓存文件", None, False),
    ("4", "查看缓存/状态统计", None, False),
    ("P", "配置基础报告章节组（基金深度分析/市场新闻/组合历史走势+回撤/组合演进/行动建议）", None, False),
    ("I", "管理对比指数池（自定义基准指数）", None, False),
    ("A", "配置持仓匿名化（代码/名称脱敏）", None, False),
    ("S", "配置功能开关（LLM 分析章节 + 实验性/常规/报告章节与增强开关）", None, False),
    ("R", "刷新配置", None, False),
    ("V", "查看最近运行日志（可按级别筛选）", None, False),
    ("H", "查看数据源健康历史（近期检查记录）", None, False),
    ("T", "系统自检（环境/配置/目录/数据源一键体检）", None, False),
    ("X", "退出", None, True),
]

# 受功能开关约束的菜单项：{快捷键: 开关名}。
# 开关关闭时该菜单项整体不出现（在 _apply_feature_gates 中裁剪），
# 避免用户点进去只得到一句「功能未启用」。
FEATURE_GATED_ITEMS: dict[str, str] = {"T": "doctor_check"}


def _apply_feature_gates() -> None:
    """按功能开关就地裁剪 MENU_ITEMS（切片赋值保持列表对象不变，调用方视图同步）。"""
    from src.python.config.features import is_feature_enabled

    disabled = {
        key
        for key, flag in FEATURE_GATED_ITEMS.items()
        if key in {item[0] for item in MENU_ITEMS} and not is_feature_enabled(flag)
    }
    if disabled:
        MENU_ITEMS[:] = [item for item in MENU_ITEMS if item[0] not in disabled]


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
# 辩论三模块（debate_pro/con/synthesis）在注册表中保留
# （缓存 TTL/前缀清理仍依赖），但不在菜单/状态面板展示，避免误导为可开关模块。
# 实际辩论开关由 features.json 控制（正反辩论为实验 Flag；条件推理为常规开关；集中度问答为流程内建段）。
LLM_MENU_HIDDEN_KEYS: frozenset[str] = LLM_HIDDEN_KEYS


def filter_menu_llm_modules(module_names: dict[str, str]) -> dict[str, str]:
    """菜单层过滤：剔除隐藏的 LLM 模块（注册表条目保留）。"""
    return {k: v for k, v in module_names.items() if k not in LLM_MENU_HIDDEN_KEYS}


# ── 界面输出 ──────────────────────────────────────────────


def print_sep(char: str = "=", width: int = 56) -> None:
    print(char * width)


def print_header() -> None:
    """打印程序标题头（每次主循环迭代时重绘）。"""
    from src.python.core.constants import APP_NAME, APP_VERSION

    print_sep()
    print(f"        {APP_NAME}  v{APP_VERSION}")
    print_sep()

    # 首次运行引导：检测是否缺少关键资源
    config = _config_cache if _config_cache is not None else refresh_config()
    holdings = os.path.join(config.get("holdings_dir", ""), config.get("holdings_filename", ""))
    _first_run_hints = []
    if not os.path.exists(holdings):
        _first_run_hints.append("• 请先通过菜单 [D] 配置持仓目录/文件名，或放置文件到默认目录")
    from src.python.core.system_info import llm_status

    if not llm_status()["configured"]:
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
    from src.python.config import get_default, resolve_holdings_path

    config = _config_cache if _config_cache is not None else refresh_config()
    holdings_path = resolve_holdings_path(config)
    print(f"  持仓目录: {config.get('holdings_dir', '未设置')}")
    print(f"  持仓文件: {config.get('holdings_filename', '未设置')}")
    print(f"  输出目录: {config.get('output_dir') or get_default('output_dir')}")
    print(f"  新闻抓取上限: {config.get('news_top_count', '300')} 条")
    if os.path.exists(holdings_path):
        print("  状态: [OK] 文件就绪")
    else:
        print("  状态: [!!] 文件未找到")
    _show_privacy_and_security_status()
    _show_llm_config_status()
    print()


def _show_privacy_and_security_status() -> None:
    """显示隐私提示和匿名化安全状态。"""
    from src.python.config.anonymizer import get_anonymization_mode
    from src.python.core.system_info import anon_mode_label

    _anon_mode = get_anonymization_mode()
    _anon_display = anon_mode_label(_anon_mode)

    # 检查隐私提示是否已显示过（机器本地状态）
    from src.python.config import get_local_flag

    _privacy_shown = get_local_flag("_privacy_notice_shown")
    _privacy_icon = f"{GREEN}✓{RESET}" if _privacy_shown else f"{YELLOW}待首次报告生成时显示{RESET}"

    print(f"  持仓匿名化: {_anon_display}")
    print(f"  隐私声明: {_privacy_icon}")
    print()


def _show_llm_config_status() -> None:
    """显示 LLM 配置状态（绿色已配置 / 红色未配置）。

    数据来自 ``core.system_info.llm_status`` 单源（三渠道共用判定树），
    本函数只做终端渲染，不自行组装状态。
    """
    from src.python.core.system_info import llm_status

    llm = llm_status()
    if not llm.get("configured"):
        print(f"  LLM: {RED}未配置{RESET}（配置 data/config/llm_key.json 或 llm_providers.json 后重启生效）")
        return
    if llm.get("mode") == "multi":
        _show_multi_chain_status(llm)
        return
    cb_display = f" |  熔断: {llm['circuit']}" if llm["circuit"] != "—" else ""
    print(
        f"  LLM: {GREEN}已配置{RESET}  provider={llm['provider']}  model={llm['model']}"
        f"  endpoint={llm['endpoint_display']}{cb_display}"
    )
    print(f"         模型路由: {' / '.join(llm['route'])}")


def _show_multi_chain_status(llm: dict) -> None:
    """显示多 Provider 链式服务的详细信息（消费 llm_status 单源结果）。

    展示策略、各 Provider 的后端/模型/优先级/熔断状态与模块偏好；
    单独提取为函数以保持 _show_llm_config_status 清晰。
    """
    print(f"  LLM: {GREEN}已配置{RESET}")
    print(f"  策略: {llm['strategy']}  |  多链服务 ({len(llm['providers'])} provider)")
    for i, p in enumerate(llm["providers"], 1):
        cb_status = p["circuit"]
        cb_icon = f"{GREEN}✓{RESET}" if cb_status == "正常" else f"{RED}⚠{RESET}"
        print(f"    [{i}] {p['name']}  ({p['backend']})")
        print(f"         模型: {p['model']}")
        print(f"         优先级: {p['priority']}    熔断: {cb_icon} {cb_status}")
    if llm.get("preferred"):
        print(f"    ▶ 模块偏好: {' / '.join(llm['preferred'])}")

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

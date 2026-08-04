"""首次运行引导模块 — 检测缺失资源并交互式引导。

镜像 `report/privacy_notice.py` 范式：配置标记键 + 首次运行检测 + 显示。

职责：
  - is_first_run() — 是否为首次运行（引导未显示过）
  - mark_wizard_shown() — 标记引导已显示，避免重复提示
  - _detect_startup_state(config) — 检测持仓 / LLM 凭据 / 降级状态
  - show_startup_wizard_if_needed(non_interactive=False) — 交互式引导

架构约束：
  - 写入 llm_key.json 使用 `config._core._atomic_write` 原子写入
  - 运行时诊断走 logging；交互式引导 print 属日志豁免（提示类输出）
  - 持仓目录使用配置层已绝对化的 holdings_dir，不依赖 CWD
  - 凭据写入 llm_key.json（合法凭据位置），不写入 llm_providers.json
"""

from __future__ import annotations

import json
import logging
import os
import sys

from src.python.config._local_state import get_flag, set_flag

logger = logging.getLogger("invest")

# 首次运行标记键（存于 data/state/local_state.json，机器本地状态）
_FIRST_RUN_KEY = "_startup_wizard_shown"

# 引导边框宽度（仿隐私提示边框）
_BORDER_WIDTH = 58


# ── 首次运行标记 ─────────────────────────────────────────────


def is_first_run() -> bool:
    """检查是否为首次运行（引导未显示过）。

    Returns:
        True 表示首次运行
    """
    try:
        return not get_flag(_FIRST_RUN_KEY)
    except Exception:
        return True


def mark_wizard_shown() -> None:
    """标记引导已显示，避免重复提示。"""
    try:
        if not get_flag(_FIRST_RUN_KEY):
            set_flag(_FIRST_RUN_KEY, True)
            logger.info("[startup-wizard] 首次运行引导已标记为已读")
    except Exception:
        logger.debug("[startup-wizard] 标记引导失败（非关键）", exc_info=True)


# ── 状态检测 ─────────────────────────────────────────────────


def _detect_startup_state(config: dict) -> dict:
    """检测首次运行状态。

    Returns:
        dict: {holdings_ok, llm_key_ok, llm_degraded}
          - holdings_ok: holdings_dir 下存在 .xlsx 持仓文件
          - llm_key_ok: llm_key.json 存在 或 llm_providers.json 有 providers（链模式）
          - llm_degraded: LLM 分析章节启用但无凭据 → 报告 LLM 页签将显示占位
    """
    holdings_ok = bool(_list_holding_files(config))
    llm_key_ok = _llm_key_present()
    llm_degraded = (not llm_key_ok) and _llm_expected(config)
    return {
        "holdings_ok": holdings_ok,
        "llm_key_ok": llm_key_ok,
        "llm_degraded": llm_degraded,
    }


def _list_holding_files(config: dict) -> list[str]:
    """列出持仓目录下的 xlsx 文件（holdings_dir 由配置层绝对化）。"""
    from src.python.core.reader import list_xlsx_files

    return list_xlsx_files(config.get("holdings_dir", "") or "")


def _llm_key_present() -> bool:
    """LLM 凭据是否就绪：llm_key.json 存在，或 llm_providers.json 链模式有 provider。"""
    from src.python.config._llm_providers import _get_llm_key_path, _load_llm_providers

    if os.path.exists(_get_llm_key_path()):
        return True
    raw = _load_llm_providers()
    return bool(raw and raw.get("providers"))


def _llm_expected(config: dict) -> bool:
    """LLM 分析章节是否启用（启用但无凭据 → 报告占位，§1.4.5 降级）。"""
    from src.python.config import is_enable_llm

    return is_enable_llm(config)


def _is_non_interactive(force: bool = False) -> bool:
    """检测是否应跳过交互：显式 --non-interactive / CI / 非 TTY。"""
    if force:
        return True
    if os.environ.get("CI") or os.environ.get("NON_INTERACTIVE"):
        return True
    try:
        return not sys.stdin.isatty()
    except Exception:
        return True


def _write_llm_key_flat(
    api_key: str,
    provider: str = "claude",
    model: str = "",
    endpoint: str = "",
) -> None:
    """原子写入 flat llm_key.json（单凭据格式，读取时自动升级为 _default）。

    Args:
        api_key: API 密钥
        provider: provider 类型（claude/openai 等）
        model: 模型名（可选）
        endpoint: 自定义端点（可选，DeepSeek Anthropic 兼容端点）
    """
    from src.python.config._core import _atomic_write
    from src.python.config._llm_providers import _get_llm_key_path

    key_path = _get_llm_key_path()
    # 原子写要求父目录存在（同 set_config 的 _core.os.makedirs 范式）
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    data: dict = {"provider": provider, "api_key": api_key}
    if model:
        data["model"] = model
    if endpoint:
        data["endpoint"] = endpoint
    _atomic_write(key_path, json.dumps(data, ensure_ascii=False, indent=2))
    logger.info("[startup-wizard] 已写入 llm_key.json（provider=%s）", provider)


# ── 交互式引导 ───────────────────────────────────────────────


def _print_banner(title: str) -> None:
    """打印边框引导横幅。"""
    print()
    print("  ╔" + "═" * (_BORDER_WIDTH - 2) + "╗")
    print(f"  ║ {title}")
    print("  ╠" + "═" * (_BORDER_WIDTH - 2) + "╣")


def _print_line(text: str) -> None:
    """打印带左边框的一行提示。"""
    print(f"  ║ {text}")


def _print_footer() -> None:
    print("  ╚" + "═" * (_BORDER_WIDTH - 2) + "╝")
    print()


def _prompt_enter_key() -> bool:
    """询问用户是否现在输入 LLM Key。

    Returns:
        True 表示用户选择现在输入
    """
    try:
        ans = input("  现在配置 LLM Key？[y/N] ").strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _handle_key_input() -> None:
    """读取 API Key 并原子写入 flat llm_key.json。"""
    try:
        api_key = input("  请输入 API Key（回车跳过）: ").strip()
        if not api_key:
            _print_line("已跳过 Key 输入，可在菜单「LLM 配置」中补充。")
            return
        _write_llm_key_flat(api_key)
        _print_line("✓ 已保存 llm_key.json，下次生成报告生效。")
    except (EOFError, KeyboardInterrupt):
        _print_line("已取消 Key 输入。")


def show_startup_wizard_if_needed(non_interactive: bool = False) -> bool:
    """首次运行时显示交互式引导。已显示过或非交互环境则静默。

    Args:
        non_interactive: 显式跳过交互（CLI --non-interactive / 定时任务）

    Returns:
        True 表示本次显示了引导
    """
    if not is_first_run():
        return False
    if _is_non_interactive(force=non_interactive):
        logger.info("[startup-wizard] 非交互环境，跳过首次运行引导")
        return False

    from src.python.config import get_config

    config = get_config()
    state = _detect_startup_state(config)

    _print_banner("首次运行引导 / First-Run Guide")
    _print_line("config.json 已由 init_config 自动创建，无需处理。")

    if not state["holdings_ok"]:
        _print_line("【持仓文件】data/holdings/ 下暂无 .xlsx 持仓文件。")
        _print_line("  请放置持仓 Excel（每个 worksheet = 一个账户），格式见")
        _print_line("  README.md → how-to-start.md → 持仓格式章节。")
    else:
        _print_line("【持仓文件】✓ 已检测到持仓文件。")

    if not state["llm_key_ok"]:
        _print_line("【LLM 配置】未检测到 llm_key.json 凭据。")
        if state["llm_degraded"]:
            _print_line("  LLM 分析章节（智囊团/持仓体检等）将显示占位内容。")
        if _prompt_enter_key():
            _handle_key_input()
    else:
        _print_line("【LLM 配置】✓ 已检测到 LLM 凭据。")

    if state["holdings_ok"] and state["llm_key_ok"]:
        _print_line("一切就绪，开始生成报告！")

    _print_footer()
    mark_wizard_shown()
    return True

"""TUI 报告生成命令处理器。

仅保留 TUI 专属交互外壳，业务编排逻辑全部委托 orchestrator。
"""

from __future__ import annotations

from src.python.core.logger import setup_logger
from src.python.report import orchestrator
from src.python.report.progress import TuiProgressReporter
from src.python.tui.tui_handlers import (
    finish_report,
    prepare_holdings,
    print_error_with_hint,
    print_llm_session_usage,
)
from src.python.tui.tui_menu import get_config_cache

logger = setup_logger()


def _prompt_history(reporter: TuiProgressReporter) -> str:
    """TUI 专属：询问用户是否获取历史走势数据。"""
    from src.python.config import is_enable_history

    config = get_config_cache() or {}
    if not is_enable_history(config):
        return "off"
    _history_cfg_mode = config.get("history", {}).get("analysis", "auto")
    if _history_cfg_mode == "prompt":
        try:
            _resp = input("  [..] 是否获取组合历史走势数据（as-if 模拟）？(y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            _resp = "n"
        return "auto" if _resp == "y" else "off"
    return _history_cfg_mode


def _prompt_force_llm(reporter: TuiProgressReporter) -> bool:
    """TUI 专属：询问用户是否强制刷新 LLM 缓存。"""
    try:
        _resp = input("  [..] 是否强制重新生成 LLM 内容（跳过缓存）？(y/N): ").strip().lower()
        _force = _resp == "y"
    except (EOFError, KeyboardInterrupt):
        _force = False
    if _force:
        reporter.ok("将跳过 LLM 缓存强制重新生成")
    return _force


def _run_generate(
    report_type: str,
    *,
    history_mode: str | None = None,
    force_llm: bool | None = None,
) -> TuiProgressReporter | None:
    """通用报告生成命令骨架。

    Args:
        report_type: 报告类型（"basic" / "both" / "full"）
        history_mode: 历史走势模式，None 表示不传入（使用 orchestrator 默认）
        force_llm: 是否强制刷新 LLM 缓存，None 表示不传入

    Returns:
        TuiProgressReporter 实例（成功时）或 None（持仓未就绪时）
    """
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    holdings = prepare_holdings()
    if not holdings:
        return None
    kwargs: dict = {
        "holdings": holdings,
        "config": config,
        "reporter": reporter,
        "report_type": report_type,
    }
    if history_mode is not None:
        kwargs["history_mode"] = history_mode
    if force_llm is not None:
        kwargs["force_llm"] = force_llm
    try:
        orchestrator.generate_report(**kwargs)
    except Exception as e:
        logger.exception("生成 %s 报告失败", report_type)
        print_error_with_hint(e, "生成失败")
    finish_report(reporter)
    return reporter


def _cmd_generate_excel() -> None:
    """生成 Excel 分析报告（必选内容）。"""
    _run_generate("basic")


def _cmd_generate_both() -> None:
    """生成全系列包含新闻的报告（Excel+HTML，不含 LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    _run_generate("both", history_mode=_prompt_history(reporter))


def _cmd_generate_full() -> None:
    """生成包含所有内容的全系列报告（Excel + HTML + 新闻 + LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    _run_generate("full", history_mode=_prompt_history(reporter), force_llm=_prompt_force_llm(reporter))
    print_llm_session_usage()

"""TUI 报告生成命令处理器。

仅保留 TUI 专属交互外壳，业务编排逻辑全部委托 orchestrator。
"""

from __future__ import annotations

from src.python.logger import setup_logger
from src.python.report import orchestrator
from src.python.report.progress import TuiProgressReporter
from src.python.tui_handlers import (
    finish_report,
    prepare_holdings,
    print_error_with_hint,
    print_llm_session_usage,
)
from src.python.tui_menu import get_config_cache

logger = setup_logger()


def _prompt_history(reporter: TuiProgressReporter) -> str:
    """TUI 专属：询问用户是否获取历史走势数据。"""
    from src.python.config import is_enable_history

    config = get_config_cache() or {}
    if not is_enable_history(config):
        return "off"
    _history_cfg_mode = config.get("history", {}).get("analysis", "off")
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


def _cmd_generate_excel() -> None:
    """生成 Excel 分析报告（必选内容）。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    holdings = prepare_holdings()
    if not holdings:
        return
    try:
        orchestrator.generate_report(
            holdings=holdings,
            config=config,
            reporter=reporter,
            report_type="basic",
        )
    except Exception as e:
        logger.exception("生成 Excel 报告失败")
        print_error_with_hint(e, "生成失败")
    finish_report(reporter)


def _cmd_generate_both() -> None:
    """生成全系列包含新闻的报告（Excel+HTML，不含 LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    holdings = prepare_holdings()
    if not holdings:
        return
    try:
        orchestrator.generate_report(
            holdings=holdings,
            config=config,
            reporter=reporter,
            report_type="both",
            history_mode=_prompt_history(reporter),
        )
    except Exception as e:
        logger.exception("生成全系列报告失败")
        print_error_with_hint(e, "生成失败")
    finish_report(reporter)


def _cmd_generate_full() -> None:
    """生成包含所有内容的全系列报告（Excel + HTML + 新闻 + LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    holdings = prepare_holdings()
    if not holdings:
        return
    try:
        orchestrator.generate_report(
            holdings=holdings,
            config=config,
            reporter=reporter,
            report_type="full",
            history_mode=_prompt_history(reporter),
            force_llm=_prompt_force_llm(reporter),
        )
        print_llm_session_usage()
    except Exception as e:
        logger.exception("生成全系列报告失败")
        print_error_with_hint(e, "生成失败")
    finish_report(reporter)

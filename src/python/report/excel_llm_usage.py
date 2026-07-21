"""LLM 分析章节 + API 用量页签写入模块。

职责：LLM 分析章节编排 + LLM API 用量构建/写入。
"""

from __future__ import annotations

from typing import Any

from src.python.logger import setup_logger
from src.python.report.llm_module_info import build_llm_module_info
from src.python.report.progress import ProgressReporter, Timer

logger = setup_logger()


def write_llm_section_and_usage(
    sheets: dict[str, Any],
    include_llm: bool,
    llm_content: tuple[str | None, str | None, str | None, str | None] | None,
    prog: ProgressReporter,
    section_order: list[dict] | None = None,
    debate_mode_label: str | None = None,
) -> None:
    """写入 LLM 分析章节页签和 LLM API 用量页签。

    Args:
        debate_mode_label: 辩论模式标签，非 None 时在 expert_review 页签和用量页展示实验模式标识
    """
    if not include_llm:
        return

    with Timer("LLM 分析章节"):
        prog.info("正在生成 LLM 分析章节...")
        try:
            from src.python.report.llm_content import write_llm_sheets

            write_llm_sheets(
                sheets,
                llm_content=llm_content or (None, None, None, None),
                section_order=section_order,
                debate_mode_label=debate_mode_label,
            )
            logger.info("LLM 分析章节已生成")
            prog.ok("LLM 分析章节生成完成")
        except ImportError:
            logger.warning("LLM 分析章节模块 (src.python.report.llm_content) 未就绪，跳过")
            prog.add_error("LLM 分析章节模块未就绪，跳过")
        except Exception:
            logger.exception("生成 LLM 分析章节失败")
            prog.add_error("LLM 分析章节生成失败（详情请查看日志）")

    build_llm_usage_sheet(sheets, prog, debate_mode_label=debate_mode_label)


def build_llm_usage_sheet(
    sheets: dict[str, Any],
    _prog: ProgressReporter,
    debate_mode_label: str | None = None,
) -> None:
    """构建并写入 LLM API 用量页签。

    Args:
        debate_mode_label: 辩论模式标签，非 None 时在模块状态列和汇总区显示实验模式标识
    """
    try:
        from src.python.llm import (
            format_session_usage,
            get_session_usage,
        )
        from src.python.llm.prompts import LLM_MODULE_FAILURE
        from src.python.report.summary import write_llm_usage_sheet
    except (ImportError, AttributeError) as e:
        logger.debug("LLM 用量页签模块未就绪（非关键）: %s", e)
        return

    raw_session = get_session_usage()
    formatted = format_session_usage(raw_session)
    if not formatted:
        return

    per_module = raw_session.get("per_module", {}) or {}
    if not per_module:
        logger.debug("LLM 会话数据中 per_module 为空，尝试从 formatted 获取")
        per_module = formatted.get("per_module", {}) or {}
    all_failure = dict(LLM_MODULE_FAILURE)

    # 辩论模式启用时，标记 expert_review 为实验模式
    _debate_modules: set[str] | None = None
    if debate_mode_label:
        _debate_modules = {"expert_review"}

    excel_module_info = build_llm_module_info(
        all_failure, per_module, skip_unknown=True, debate_enabled_modules=_debate_modules
    )

    if not excel_module_info:
        return

    ws = sheets.get("llm_usage")
    if ws is None:
        logger.debug("llm_usage 页签未被创建，跳过 API 用量写入")
        return
    glb_endpoint = next((mi["endpoint"] for mi in excel_module_info if mi.get("endpoint")), "")
    try:
        write_llm_usage_sheet(ws, formatted, excel_module_info, llm_endpoint=glb_endpoint)
    except Exception as e:
        logger.debug("创建 LLM API 用量页签失败（非关键）: %s", e)

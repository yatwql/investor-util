"""LLM 分析章节 + API 用量页签写入模块。

职责：LLM 分析章节编排 + LLM API 用量构建/写入。
提取自 excel_generator.py 的 _write_llm_section_and_usage + _build_llm_usage_sheet。
"""

from __future__ import annotations

from typing import Any

from src.python.logger import setup_logger
from src.python.report.progress import ProgressReporter, _Timer

logger = setup_logger()


def write_llm_section_and_usage(
    sheets: dict[str, Any], include_llm: bool, llm_content: tuple[str | None, str | None, str | None, str | None] | None,
    prog: ProgressReporter, section_order: list[dict] | None = None,
) -> None:
    """写入 LLM 分析章节页签和 LLM API 用量页签。"""
    if not include_llm:
        return

    with _Timer("LLM 分析章节"):
        prog.info("正在生成 LLM 分析章节...")
        try:
            from src.python.report.llm_content import write_llm_sheets
            write_llm_sheets(sheets, llm_content=llm_content or (None, None, None, None), section_order=section_order)
            logger.info("LLM 分析章节已生成")
            prog.ok("LLM 分析章节生成完成")
        except ImportError:
            logger.warning("LLM 分析章节模块 (src.python.report.llm_content) 未就绪，跳过")
            prog.add_error("LLM 分析章节模块未就绪，跳过")
        except Exception:
            logger.exception("生成 LLM 分析章节失败")
            prog.add_error("LLM 分析章节生成失败（详情请查看日志）")

    build_llm_usage_sheet(sheets, prog)


def build_llm_usage_sheet(sheets: dict[str, Any], _prog: ProgressReporter) -> None:
    """构建并写入 LLM API 用量页签。"""
    try:
        from src.python.llm import (
            FAIL_REASON_DISABLED,
            format_session_usage,
            get_session_usage,
        )
        from src.python.llm.prompts import _LLM_MODULE_FAILURE
        from src.python.registry import get_llm_module_names
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
    all_failure = dict(_LLM_MODULE_FAILURE)
    names_map = get_llm_module_names()

    MODULE_KEYS = ["global_macro", "expert_review", "health_check", "penetration_deep", "news_correlation"]
    DISPLAY_REASON = {
        "not_configured": "LLM 未配置",
        "api_error": "LLM API 调用失败",
        "network_error": "LLM API 网络连接失败",
        "timeout": "LLM API 请求超时",
        "circuit_open": "LLM API 暂时不可用（熔断冷却中）",
    }

    excel_module_info: list[dict] = []
    for mk in MODULE_KEYS:
        entry: dict = {"key": mk, "name": names_map.get(mk, mk)}
        reason = all_failure.get(mk)
        pm = per_module.get(mk)
        if reason == FAIL_REASON_DISABLED:
            entry.update({"status": "disabled", "status_label": "已禁用",
                          "model": "", "input_tokens": 0, "output_tokens": 0,
                          "total_tokens": 0, "cache_hit_tokens": 0,
                          "cost": 0.0, "cached": False, "thinking": False, "endpoint": ""})
        elif reason:
            reason_text = DISPLAY_REASON.get(str(reason).lower(), str(reason))
            entry.update({"status": "failed", "status_label": reason_text,
                          "model": "", "input_tokens": 0, "output_tokens": 0,
                          "total_tokens": 0, "cache_hit_tokens": 0,
                          "cost": 0.0, "cached": False, "thinking": False, "endpoint": ""})
        elif pm:
            inp = pm.get("input_tokens", 0)
            out = pm.get("output_tokens", 0)
            entry.update({
                "status": "cached" if pm.get("cached") else "success",
                "status_label": "缓存" if pm.get("cached") else "成功",
                "model": pm.get("model", ""),
                "input_tokens": inp, "output_tokens": out,
                "total_tokens": inp + out,
                "cache_hit_tokens": pm.get("cache_hit_tokens", 0),
                "cost": pm.get("cost", 0.0),
                "cached": pm.get("cached", False),
                "thinking": pm.get("thinking", False),
                "endpoint": pm.get("endpoint", ""),
            })
        else:
            continue
        if entry.get("status_label"):
            excel_module_info.append(entry)

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

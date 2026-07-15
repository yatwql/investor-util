"""LLM 模块信息构建 — 共享模块，消除 html_renderers 与 excel_llm_usage 中的重复代码。

提供 :func:`build_llm_module_info` 统一构建模块状态/Token用量/费用信息，
供 HTML 和 Excel 两端共用。
"""

from __future__ import annotations

from typing import Any

from src.python.registry import get_llm_module_names

try:
    from src.python.llm import (
        FAIL_REASON_API_ERROR,
        FAIL_REASON_CIRCUIT_OPEN,
        FAIL_REASON_DISABLED,
        FAIL_REASON_NETWORK_ERROR,
        FAIL_REASON_NOT_CONFIGURED,
        FAIL_REASON_TIMEOUT,
    )
except ImportError:
    FAIL_REASON_DISABLED = FAIL_REASON_NOT_CONFIGURED = "disabled"
    FAIL_REASON_API_ERROR = FAIL_REASON_NETWORK_ERROR = FAIL_REASON_TIMEOUT = FAIL_REASON_CIRCUIT_OPEN = "error"

_MODULE_KEYS = ["global_macro", "expert_review", "health_check", "penetration_deep", "news_correlation"]

_DISPLAY_REASON: dict[str, str] = {
    FAIL_REASON_NOT_CONFIGURED: "LLM 未配置",
    FAIL_REASON_API_ERROR: "LLM API 调用失败",
    FAIL_REASON_NETWORK_ERROR: "LLM API 网络连接失败",
    FAIL_REASON_TIMEOUT: "LLM API 请求超时",
    FAIL_REASON_CIRCUIT_OPEN: "LLM API 暂时不可用（熔断冷却中）",
}


def build_llm_module_info(llm_failure: dict, per_module: dict, skip_unknown: bool = False) -> list[dict[str, Any]]:
    """构建 LLM 模块信息列表（状态、Token 用量、费用等）。

    Args:
        llm_failure: LLM 模块失败原因字典（LLM_MODULE_FAILURE）
        per_module: 每个模块的用量统计
        skip_unknown: 是否跳过状态为 unknown 的模块

    Returns:
        模块信息列表，每项含 key/name/status/status_label/model/tokens/cost 等字段
    """
    names = get_llm_module_names()
    result: list[dict[str, Any]] = []
    for mk in _MODULE_KEYS:
        entry: dict[str, Any] = {"key": mk, "name": names.get(mk, mk)}
        reason = llm_failure.get(mk)
        pm = per_module.get(mk)
        if reason == FAIL_REASON_DISABLED:
            entry.update(
                status="disabled", status_label="已禁用",
                model="", input_tokens=0, output_tokens=0, total_tokens=0,
                cache_hit_tokens=0, cost=0.0, cached=False, thinking=False, endpoint="",
            )
        elif reason:
            entry.update(
                status="failed",
                status_label=_DISPLAY_REASON.get(reason, str(reason)),
                model="", input_tokens=0, output_tokens=0, total_tokens=0,
                cache_hit_tokens=0, cost=0.0, cached=False, thinking=False, endpoint="",
            )
        elif pm:
            inp = pm.get("input_tokens", 0)
            out = pm.get("output_tokens", 0)
            entry.update(
                status="cached" if pm.get("cached") else "success",
                status_label="缓存" if pm.get("cached") else "成功",
                model=pm.get("model", ""), input_tokens=inp, output_tokens=out,
                total_tokens=inp + out, cache_hit_tokens=pm.get("cache_hit_tokens", 0),
                cost=pm.get("cost", 0.0), cached=pm.get("cached", False),
                thinking=pm.get("thinking", False), endpoint=pm.get("endpoint", ""),
            )
        elif skip_unknown:
            continue
        else:
            entry.update(
                status="unknown", status_label="",
                model="", input_tokens=0, output_tokens=0, total_tokens=0,
                cache_hit_tokens=0, cost=0.0, cached=False, thinking=False, endpoint="",
            )
        result.append(entry)
    return result

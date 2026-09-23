"""LLM 模块信息构建 — 共享模块，消除 html_renderers 与 excel_llm_usage 中的重复代码。

提供 :func:`build_llm_module_info` 统一构建模块状态/Token用量/费用信息，
供 HTML 和 Excel 两端共用。
"""

from __future__ import annotations

from typing import Any

from src.python.core.registry import get_llm_module_names

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


def get_llm_module_failure_reason(module_failure: dict, module_key: str) -> str | None:
    """从 LLM_MODULE_FAILURE 中提取模块失败原因，支持字符串和多链 dict 两种格式。

    字符串：value 为 FAIL_REASON_*，直接返回。
    多链 dict：value 为 ``{"attempted": [...], "final_status": "success"|FAIL_REASON_*}``，
    提取 final_status，success 转换为 None（表示成功）。

    Returns:
        FAIL_REASON_* 字符串，或 None（模块未失败/成功/键不存在）
    """
    reason = module_failure.get(module_key)
    if isinstance(reason, dict):
        final_status = reason.get("final_status", "")
        return None if final_status == "success" else final_status
    return reason


def _endpoint_priority_map(llm_config: dict | None) -> dict[str, float]:
    """从 llm_config 的 provider 链构建 endpoint → priority 映射。

    endpoint 解析复用 `llm/api.py::resolve_provider_endpoint`（唯一解析入口），
    不在报告层重写 credentials_ref → endpoint 的遍历规则。
    """
    mapping: dict[str, float] = {}
    if not llm_config:
        return mapping
    from src.python.llm.api import resolve_provider_endpoint

    for provider in llm_config.get("_provider_list") or []:
        endpoint = resolve_provider_endpoint(provider, llm_config)
        if endpoint and endpoint not in mapping:
            mapping[endpoint] = float(provider.get("priority", 999))
    return mapping


def build_llm_endpoint_display(module_info: list[dict[str, Any]], llm_config: dict | None = None) -> str:
    """构建 Endpoint 汇总展示（HTML / Excel 两端共用）。

    - 无端点 → ""
    - 单一端点 → 原样返回
    - 多端点（主备混用）→ 按 provider 链 priority 升序排列，主在前并标注，
      形如 ``"https://主端点（主） / https://备端点（备）"``；
      任一端点无法映射到链路时保持模块出现顺序、不标注（避免误标主备）

    llm_config 为 None 时惰性加载全局 LLM 配置；加载失败降级为无标注拼接。
    """
    seen: list[str] = []
    for mi in module_info:
        ep = mi.get("endpoint")
        if ep and ep not in seen:
            seen.append(ep)
    if not seen:
        return ""
    if len(seen) == 1:
        return seen[0]
    if llm_config is None:
        try:
            from src.python.config import get_llm_config

            llm_config = get_llm_config()
        except Exception:  # 配置不可用时降级为无标注拼接
            llm_config = {}
    pmap = _endpoint_priority_map(llm_config)
    if not pmap or any(ep not in pmap for ep in seen):
        return " / ".join(seen)
    ordered = sorted(seen, key=lambda ep: pmap[ep])
    return " / ".join(f"{ep}（{'主' if i == 0 else '备'}）" for i, ep in enumerate(ordered))


def build_llm_module_info(
    llm_failure: dict,
    per_module: dict,
    skip_unknown: bool = False,
    debate_enabled_modules: set[str] | None = None,
) -> list[dict[str, Any]]:
    """构建 LLM 模块信息列表（状态、Token 用量、费用等）。

    Args:
        llm_failure: LLM 模块失败原因字典（LLM_MODULE_FAILURE）
        per_module: 每个模块的用量统计
        skip_unknown: 是否跳过状态为 unknown 的模块
        debate_enabled_modules: 启用辩论模式的模块 key 集合，命中时 status_label 覆盖为实验模式标签

    Returns:
        模块信息列表，每项含 key/name/status/status_label/model/tokens/cost 等字段
    """
    names = get_llm_module_names()
    result: list[dict[str, Any]] = []
    for mk in _MODULE_KEYS:
        entry: dict[str, Any] = {"key": mk, "name": names.get(mk, mk)}
        reason = get_llm_module_failure_reason(llm_failure, mk)
        pm = per_module.get(mk)

        # 辩论模式标签映射（模块级覆盖）
        _DEBATE_LABELS: dict[str, str] = {
            "llm_debate_procon": "🧪 辩论模式",
        }

        if reason == FAIL_REASON_DISABLED:
            entry.update(
                status="disabled",
                status_label="已禁用",
                model="",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cache_hit_tokens=0,
                cost=0.0,
                cached=False,
                thinking=False,
                endpoint="",
            )
        elif reason:
            entry.update(
                status="failed",
                status_label=_DISPLAY_REASON.get(reason, str(reason)),
                model="",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cache_hit_tokens=0,
                cost=0.0,
                cached=False,
                thinking=False,
                endpoint="",
            )
        elif pm:
            inp = pm.get("input_tokens", 0)
            out = pm.get("output_tokens", 0)
            # 辩论模式覆盖状态标签
            _label_override = None
            if debate_enabled_modules and mk in debate_enabled_modules:
                for _flag, _lbl in _DEBATE_LABELS.items():
                    if _flag in debate_enabled_modules:
                        _label_override = _lbl
                        break
            entry.update(
                status="cached" if pm.get("cached") else "success",
                status_label=_label_override or ("缓存" if pm.get("cached") else "成功"),
                model=pm.get("model", ""),
                input_tokens=inp,
                output_tokens=out,
                total_tokens=inp + out,
                cache_hit_tokens=pm.get("cache_hit_tokens", 0),
                cost=pm.get("cost", 0.0),
                cached=pm.get("cached", False),
                thinking=pm.get("thinking", False),
                endpoint=pm.get("endpoint", ""),
            )
        elif skip_unknown:
            continue
        else:
            entry.update(
                status="unknown",
                status_label="",
                model="",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cache_hit_tokens=0,
                cost=0.0,
                cached=False,
                thinking=False,
                endpoint="",
            )
        result.append(entry)
    return result

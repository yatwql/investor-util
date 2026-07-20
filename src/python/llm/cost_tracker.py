"""LLM 成本追踪与预算模块 — Token 预算管理、耗时追踪、摘要格式化。

封装会话级的 Token 预算检查逻辑和成本摘要输出，
与 session.py（用量累计）互补，专注于**预算约束**和**展示格式化**。

使用方式:
    from src.python.llm.cost_tracker import (
        reset_budget, check_input_budget, get_cost_summary,
    )

    # 每份报告开始时重置
    reset_budget(input_budget=8000)

    # 调用 call_llm() 前检查
    if not check_input_budget(module_key, estimated_input_tokens):
        logger.warning("LLM Token 预算告警...")

    # 报告末尾输出成本摘要
    summary = get_cost_summary()
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.llm.pricing import CURRENCY_SYMBOLS, estimate_cost
from src.python.llm.session import format_session_usage, get_session_usage

logger = logging.getLogger("invest")

# ── 默认预算 ──────────────────────────────────────────────────

DEFAULT_INPUT_BUDGET = 8000  # tokens：每份报告默认输入 Token 预算上限
"""每份报告的输入 Token 预算上限（默认 8K）。

超出时仅告警不截断，为后续模型分层（便宜模型做结构性内容）提供基线数据。
"""

# ── 内部状态 ──────────────────────────────────────────────────

_input_budget: int = DEFAULT_INPUT_BUDGET
"""当前报告周期的输入 Token 预算。"""

_budget_warned: bool = False
"""是否已告警过（避免同一报告周期重复告警）。"""


# ═══════════════════════════════════════════════════════════════
#  预算管理
# ═══════════════════════════════════════════════════════════════


def set_input_budget(budget: int) -> None:
    """设置当前报告周期的输入 Token 预算上限。

    Args:
        budget: 输入 Token 预算数（例如 8000）。
    """
    global _input_budget, _budget_warned
    _input_budget = max(budget, 1000)  # 最低 1K，防止设为 0 导致总是告警
    _budget_warned = False


def reset_budget(input_budget: int | None = None) -> None:
    """重置预算状态（新报告周期开始时调用）。

    Args:
        input_budget: 新的输入 Token 预算，不传则使用默认值 DEFAULT_INPUT_BUDGET。
    """
    global _budget_warned
    _budget_warned = False
    if input_budget is not None:
        set_input_budget(input_budget)


def check_input_budget(module_name: str, input_tokens: int, warn_once: bool = True) -> bool:
    """检查累计输入 Token 是否超出预算。

    在每次 call_llm() 调用之前调用，传入该次调用的预估输入 Token 数。
    超出预算时记录告警但**不阻止调用**（告警不截断原则）。

    Args:
        module_name: 模块名称（日志标识）。
        input_tokens: 本次调用的输入 Token 数（可使用 prompt 字符数 * 系数估算，
                      或传递 0 仅基于已有累计做纯检查）。
        warn_once: 同一报告周期是否只告警一次（默认 True）。

    Returns:
        True = 未超出预算（或已告警过不再重复），False = 超出预算且首次告警。
    """
    global _budget_warned
    usage = get_session_usage()
    cumulative = usage.get("input_tokens", 0)
    total_if_added = cumulative + input_tokens

    if total_if_added > _input_budget and not _budget_warned:
        pct = (total_if_added / _input_budget) * 100
        logger.warning(
            "LLM Token 预算告警: %s 模块预计累计输入 %d tokens, "
            "超出预算 %d tokens 的 %.0f%%。"
            "（当前累计: %d, 本次预估: %d）"
            "报告继续进行，不会被截断。",
            module_name,
            total_if_added,
            _input_budget,
            pct,
            cumulative,
            input_tokens,
        )
        if warn_once:
            _budget_warned = True
        return False

    return True


def get_budget_status() -> dict[str, Any]:
    """获取预算状态字典（供展示/调试用）。

    Returns:
        {"budget": int, "used": int, "remaining": int, "warned": bool}
    """
    usage = get_session_usage()
    used = usage.get("input_tokens", 0)
    return {
        "budget": _input_budget,
        "used": used,
        "remaining": max(0, _input_budget - used),
        "warned": _budget_warned,
    }


# ═══════════════════════════════════════════════════════════════
#  成本摘要
# ═══════════════════════════════════════════════════════════════


def _format_duration(seconds: float) -> str:
    """将秒格式化为易读字符串。

    Args:
        seconds: 持续秒数。

    Returns:
        如 "3.2s"、"1m 12s"、"0.5s"。
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


def get_cost_summary(for_report: bool = True) -> str:
    """生成格式化的成本摘要文本。

    Args:
        for_report: True = 报告末尾紧凑格式（纯文本），
                    False = 详细调试格式（含按模块明细）。

    Returns:
        格式化字符串。无调用记录时返回空字符串。
    """
    raw = get_session_usage()
    formatted = format_session_usage(raw)
    if not formatted.get("has_usage"):
        return ""

    parts: list[str] = []

    if for_report:
        # 紧凑格式（报告末尾）
        inp = formatted.get("input_tokens", 0)
        out = formatted.get("output_tokens", 0)
        cache_hit = formatted.get("cache_hit_tokens", 0)
        cost_display = formatted.get("cost_display", "¥0.0000")
        model = formatted.get("model_display", "未指定")

        parts.append(f"LLM Token 用量: 输入 {inp:,} / 输出 {out:,} = {inp + out:,} tokens")
        if cache_hit:
            parts.append(f"缓存命中: {cache_hit:,} tokens")
        parts.append(f"估算费用: {cost_display}")
        parts.append(f"模型: {model}")

        # 预算状态
        budget_info = get_budget_status()
        if budget_info["budget"] > 0:
            pct = (budget_info["used"] / budget_info["budget"]) * 100
            st = "⚠ 已超预算" if budget_info["warned"] else "预算内"
            parts.append(f"输入 Token 预算: {budget_info['used']:,}/{budget_info['budget']:,} ({pct:.0f}%, {st})")
    else:
        # 详细格式（-v verbose 模式）
        inp = formatted.get("input_tokens", 0)
        out = formatted.get("output_tokens", 0)
        cost_display = formatted.get("cost_display", "¥0.0000")
        model = formatted.get("model_display", "未指定")

        parts.append(f"LLM Token 成本追踪")
        parts.append(f"{'=' * 40}")
        parts.append(f"模型: {model}")
        parts.append(f"调用次数: {formatted.get('call_count', 0)}")
        parts.append(f"输入 Token: {inp:,}")
        parts.append(f"输出 Token: {out:,}")
        parts.append(f"总 Token: {inp + out:,}")

        ch = formatted.get("cache_hit_tokens", 0)
        if ch:
            parts.append(f"缓存命中: {ch:,}")
        parts.append(f"估算费用: {cost_display}")

        # 按模块明细
        per_module = raw.get("per_module", {})
        if per_module:
            parts.append("")
            parts.append("按模块明细:")
            for mod_key, mod_data in sorted(per_module.items()):
                mi = mod_data.get("input_tokens", 0)
                mo = mod_data.get("output_tokens", 0)
                mc = mod_data.get("cost", 0.0)
                mm = mod_data.get("model", "")
                md = mod_data.get("duration", 0.0)
                mcached = " [缓存]" if mod_data.get("cached") else ""
                dur_str = _format_duration(md) if md > 0 else ""
                parts.append(
                    f"  {mod_key}: 输入{mi:,}/输出{mo:,} 费用¥{mc:.4f}"
                    f"{' 耗时' + dur_str if dur_str else ''}{mcached} ({mm})"
                )

        budget_info = get_budget_status()
        if budget_info["budget"] > 0:
            st = "⚠ 已超预算" if budget_info["warned"] else "预算内"
            parts.append("")
            parts.append(f"输入 Token 预算: {budget_info['used']:,}/{budget_info['budget']:,} ({st})")

        parts.append(f"{'=' * 40}")

    return "\n".join(parts)


__all__ = [
    "DEFAULT_INPUT_BUDGET",
    "set_input_budget",
    "reset_budget",
    "check_input_budget",
    "get_budget_status",
    "get_cost_summary",
]

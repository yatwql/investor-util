"""LLM 会话统计模块 — Token 用量累计、模块级用量记录。"""

from __future__ import annotations

import logging
from typing import Any

from src.python.llm.pricing import _PRICING_CURRENCY, _estimate_cost

logger = logging.getLogger("invest")

__all__ = [
    "_session_usage",
    "reset_session_usage", "get_session_usage", "format_session_usage",
    "_track_session_usage", "_record_per_module",
]

# ── 会话级 Token 用量累计跟踪 ──

_session_usage: dict[str, Any] = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_hit_tokens": 0,
    "total_cost": 0.0,
    "currency": "CNY",
    "model": "未指定",
    "models": [],
    "call_count": 0,
    "per_module": {},
}
"""会话期间所有 LLM 调用的累计 Token 用量和费用。
per_module: {module_key: {"model": str, "input_tokens": int, "output_tokens": int}}
生成报告后可在 TUI/汇总页展示。"""


def reset_session_usage() -> None:
    """重置会话累计用量（新会话开始时调用）。"""
    _session_usage["input_tokens"] = 0
    _session_usage["output_tokens"] = 0
    _session_usage["cache_hit_tokens"] = 0
    _session_usage["total_cost"] = 0.0
    _session_usage["call_count"] = 0
    _session_usage["per_module"] = {}
    _session_usage["models"] = []


def get_session_usage() -> dict[str, Any]:
    """返回会话累计用量字典的副本（供 TUI/报告展示）。"""
    return dict(_session_usage)


def format_session_usage(raw: dict[str, Any] | None) -> dict[str, Any]:
    """将 get_session_usage() 的原始 dict 格式化为报告展示用的 dict。

    输出字段：
      has_usage    — bool，是否有实际调用
      call_count   — 调用次数
      model        — 模型名
      input_tokens — 输入 token 数
      output_tokens
      total_tokens — 输入+输出合计数
      cache_hit_tokens
      cost         — 费用数值（float）
      currency     — 货币类型（CNY/USD）
      cost_display — 格式化费用字符串（如 "¥0.0456"）
    """
    if not raw or not raw.get("call_count", 0):
        return {"has_usage": False}
    inp = raw.get("input_tokens", 0)
    out = raw.get("output_tokens", 0)
    cache_hit = raw.get("cache_hit_tokens", 0)
    cost = raw.get("total_cost", 0.0)
    currency = raw.get("currency", "CNY")
    symbol = {"CNY": "¥", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency, "¥")
    models = raw.get("models", [])
    model_display = " / ".join(models) if models else raw.get("model", "未指定")
    return {
        "has_usage": True,
        "call_count": raw.get("call_count", 0),
        "model": raw.get("model", "未指定"),
        "models": models,
        "model_display": model_display,
        "per_module": raw.get("per_module", {}),
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "cache_hit_tokens": cache_hit,
        "cost": cost,
        "currency": currency,
        "cost_display": f"{symbol}{cost:.4f}",
    }


def _track_session_usage(provider: str, usage: dict | None,
                         model_name: str = "") -> None:
    """将一次 LLM 调用的用量累计到会话统计。"""
    global _session_usage
    if not usage:
        return
    if provider == "claude":
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cache_hit = usage.get("cache_read_input_tokens", 0)
    else:
        inp = usage.get("prompt_tokens", 0)
        out = usage.get("completion_tokens", 0)
        cache_hit = 0
    _session_usage["input_tokens"] += inp
    _session_usage["output_tokens"] += out
    _session_usage["cache_hit_tokens"] += cache_hit
    _session_usage["call_count"] += 1
    if model_name:
        _session_usage["model"] = model_name
        # 累加所有使用过的模型名称（去重），供 HTML 报告展示
        if model_name not in _session_usage["models"]:
            _session_usage["models"].append(model_name)

    # 累计费用
    _cost_str = _estimate_cost(model_name, inp, out,
                               cache_hit_input_tokens=cache_hit)
    if _cost_str != "-":
        # 解析费用数值
        try:
            cost_val = float(_cost_str.lstrip("$¥€£"))
            _session_usage["total_cost"] += cost_val
        except (ValueError, AttributeError):
            pass
    _session_usage["currency"] = _PRICING_CURRENCY


def _record_per_module(module_key: str, model_name: str,
                       inp: int = 0, out: int = 0,
                       cached: bool = False) -> None:
    """按模块记录本次 LLM 调用的模型和 Token 用量，用于 TUI 退出统计展示。"""
    pm = _session_usage.setdefault("per_module", {})
    if module_key not in pm:
        pm[module_key] = {"model": model_name, "input_tokens": 0, "output_tokens": 0}
    elif cached and not pm[module_key].get("model"):
        pm[module_key]["model"] = model_name
    pm[module_key]["input_tokens"] += inp
    pm[module_key]["output_tokens"] += out
    if model_name:
        pm[module_key]["model"] = model_name
        # 缓存命中时也记录模型名称，确保全缓存场景下 models 列表有值
        if model_name not in _session_usage["models"]:
            _session_usage["models"].append(model_name)

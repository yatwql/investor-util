"""LLM 定价模块 — 模型费用估算与定价配置管理。"""

from __future__ import annotations

import logging

from src.python.constants import MODEL_PRICING

logger = logging.getLogger("invest")

__all__ = [
    "_PRICING_MERGED", "_PRICING_CURRENCY", "_CURRENCY_SYMBOLS",
    "_reload_pricing", "_estimate_cost",
]

# ── 运行时合并定价表：硬编码 + llm_settings.json 覆盖
_PRICING_MERGED: dict[str, dict[str, float]] = dict(MODEL_PRICING)

# 定价货币标识，默认 CNY；可通过 llm_settings.json → pricing.currency 覆盖
_PRICING_CURRENCY: str = "CNY"

# 货币符号映射
_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "CNY": "¥",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
}


def _reload_pricing() -> None:
    """从 llm_settings.json 重新加载定价配置。

    - "currency" 字段（可选，默认 "CNY"）设定货币类型，影响费用显示的符号。
    - 其余字段按模型名合并到 _PRICING_MERGED（文件配置优先级高于内置默认）。
      文件中的 input_cache_hit 为可选字段，缺失时继承内置默认值（如内置也无则等于 input）。
    """
    global _PRICING_CURRENCY
    try:
        from src.python.config import get_llm_config
        cfg = get_llm_config()
        if cfg and "pricing" in cfg:
            file_pricing = cfg["pricing"]
            if isinstance(file_pricing, dict):
                # 提取货币标识
                if "currency" in file_pricing:
                    _PRICING_CURRENCY = str(file_pricing["currency"]).upper().strip()
                # 合并模型定价（跳过 currency 等非模型字段）
                for model, prices in file_pricing.items():
                    if model == "currency":
                        continue
                    if isinstance(prices, dict) and "input" in prices and "output" in prices:
                        entry: dict[str, float] = {
                            "input": float(prices["input"]),
                            "output": float(prices["output"]),
                        }
                        if "input_cache_hit" in prices:
                            entry["input_cache_hit"] = float(prices["input_cache_hit"])
                        else:
                            # 文件未指定缓存命中价时，继承内置默认或等于 input
                            existing = _PRICING_MERGED.get(model, {})
                            entry["input_cache_hit"] = float(
                                existing.get("input_cache_hit", float(prices["input"]))
                            )
                        _PRICING_MERGED[model] = entry
                    elif isinstance(prices, dict):
                        # 部分字段缺失时保持已有值
                        existing = _PRICING_MERGED.get(model, {"input": 0, "output": 0, "input_cache_hit": 0})
                        if "input" in prices:
                            existing["input"] = float(prices["input"])
                        if "output" in prices:
                            existing["output"] = float(prices["output"])
                        if "input_cache_hit" in prices:
                            existing["input_cache_hit"] = float(prices["input_cache_hit"])
                        _PRICING_MERGED[model] = existing
    except Exception:
        logger.debug("加载定价配置失败，使用默认定价", exc_info=True)


# 模块加载时自动合并一次
_reload_pricing()


def _estimate_cost(model: str, input_tokens: int, output_tokens: int,
                   cache_hit_input_tokens: int = 0) -> str:
    """估算 LLM API 调用的费用。

    基于已知模型定价（每百万 token 价格）。
    未知模型返回 "-"。
    货币符号由 _PRICING_CURRENCY 决定（自 llm_settings.json → pricing.currency）。
    若存在缓存命中 token，按 input_cache_hit 费率计算（通常为 input 的 10%）。

    Args:
        model: 模型名称
        input_tokens: 总输入 token 数（含缓存命中+缓存未命中）
        output_tokens: 输出 token 数
        cache_hit_input_tokens: 其中属于缓存命中的 token 数（默认 0）

    Returns:
        格式化费用字符串，如 "$0.008"、"¥0.06" 或 "-"
    """
    if not input_tokens and not output_tokens:
        return "-"
    model_lower = model.lower().strip()
    pricing = _PRICING_MERGED.get(model_lower)
    if not pricing:
        for known, price in _PRICING_MERGED.items():
            if model_lower.startswith(known):
                pricing = price
                break
    if not pricing:
        return "-"
    cache_miss = input_tokens - cache_hit_input_tokens
    cost = (cache_miss / 1_000_000 * pricing["input"] +
            output_tokens / 1_000_000 * pricing["output"])
    if cache_hit_input_tokens > 0:
        cache_rate = pricing.get("input_cache_hit", pricing["input"])
        cost += cache_hit_input_tokens / 1_000_000 * cache_rate
    symbol = _CURRENCY_SYMBOLS.get(_PRICING_CURRENCY, "$")
    if cost < 0.01:
        return f"{symbol}{cost:.4f}"
    return f"{symbol}{cost:.3f}"

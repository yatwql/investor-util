"""fact_checker 子包 — 语境检测函数。

判断百分比数值 / 品种代码所处的语义语境（回撤、变化率、贡献度、仓位、
假设、建议等），供检查器决定是否跳过或如何比较。词表见 _constants.py。
"""

from __future__ import annotations

from src.python.llm.fact_checker._constants import (
    _CHANGE_RATE_KEYWORDS,
    _CONTRIBUTION_KEYWORDS,
    _DRAWDOWN_KEYWORDS,
    _HYPOTHETICAL_KEYWORDS,
    _POSITION_WEIGHT_KEYWORDS,
    _PROFIT_KEYWORDS,
    _SUGGESTION_KEYWORDS,
)


def _is_drawdown_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在回撤语境中（如"历史最大回撤...19.0%"）。

    全句检查回撤关键词——回撤关键词可能距离百分值几百字（如包含大段正文）。
    但若 match 前 15 字符内有收益关键词（"收益""盈利""累计"等）
    则以收益为主，不判定为回撤语境。15 字 ≈ 5-7 个中文词，
    足以捕获"累计收益率"等紧邻修饰，又不会跨分句读到其他数值的修饰词。
    """
    if not any(kw in sentence for kw in _DRAWDOWN_KEYWORDS):
        return False
    # match 前 15 字符内有收益关键词 → 以收益为主
    _profit_nearby = sentence[max(0, match_start - 15) : match_start]
    if any(kw in _profit_nearby for kw in _PROFIT_KEYWORDS):
        return False
    return True


def _is_change_rate_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在环比/同比变化率语境中。

    环比变化率（如"总市值变化-96.02%"）是相对上期/上年的变化比例，
    与收益率（相对成本）维度不同，不可直接比较，否则会被误修正为
    某个个股/组合的收益率。用 match 前 20 字符内的变化率关键词判定
    （变化率数值通常紧邻"环比/变化"等词），而非全句判断——避免同句
    首部的真实收益率被连带跳过。
    """
    if not any(kw in sentence for kw in _CHANGE_RATE_KEYWORDS):
        return False
    nearby = sentence[max(0, match_start - 20) : match_start + 5]
    return any(kw in nearby for kw in _CHANGE_RATE_KEYWORDS)


def _is_contribution_sentence(sentence: str) -> bool:
    """判断是否为收益归因句，其数值为贡献度占比而非收益率。"""
    return any(kw in sentence for kw in _CONTRIBUTION_KEYWORDS)


def _is_position_weight_context(sentence: str) -> bool:
    """判断是否为仓位/占比语境，数值为权重而非收益率。"""
    return any(kw in sentence for kw in _POSITION_WEIGHT_KEYWORDS)


def _is_hypothetical_context(sentence: str) -> bool:
    """判断是否为假设/情景语境，数值为假设而非实际收益率。"""
    return any(kw in sentence for kw in _HYPOTHETICAL_KEYWORDS)


def _is_suggestion_context(code: str, full_text: str) -> bool:
    """判断代码在全文上下文中是否属于建议/推荐语境而非声称持有。

    通过检查代码前后约 60 字符的上下文窗口是否含建议关键词来判定。
    用于将建议提及从"品种不存在"告警中降级为非幻觉。
    """
    idx = full_text.find(code)
    if idx == -1:
        return False
    start = max(0, idx - 60)
    end = min(len(full_text), idx + 60)
    context = full_text[start:end]
    return any(kw in context for kw in _SUGGESTION_KEYWORDS)

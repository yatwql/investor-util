"""fact_checker 子包 — 基础工具函数。

HTML 剥离、句子拆分、上下文摘要、持仓映射与组合数值计算。
"""

from __future__ import annotations

import re


def _strip_html(html: str) -> str:
    """去除 HTML 标签，返回纯文本。"""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_sentences(text: str) -> list[str]:
    """按中英文句号、感叹号、问号、换行拆分句子。"""
    sentences = re.split(r"[。！？\n!?]", text)
    return [s.strip() for s in sentences if s.strip()]


def _sentence_snippet(sentence: str, max_len: int = 50) -> str:
    """截取句子前 max_len 字作为上下文摘要。"""
    s = sentence.replace(" ", "").strip()
    return s[:max_len] + "…" if len(s) > max_len else s


def _extract_holding_map(holdings_details: list[dict] | None) -> dict[str, str]:
    """从持仓明细构建 {code: name} 映射。"""
    result: dict[str, str] = {}
    for d in holdings_details or []:
        code = d.get("code", "") or ""
        name = d.get("name", "") or ""
        if code:
            result[code] = name
    return result


def _calc_portfolio_values(holdings_details: list[dict] | None) -> dict[str, float]:
    """计算组合核心数值。

    Returns:
        {"total_mv": float, "total_cost": float, "total_profit": float, "total_profit_rate": float}
    """
    total_mv = sum(d.get("market_value", 0) or 0 for d in holdings_details or [])
    total_cost = sum(d.get("cost", 0) or 0 for d in holdings_details or [])
    total_profit = total_mv - total_cost
    total_profit_rate = 0.0
    if total_cost and abs(total_cost) > 1e-10:
        total_profit_rate = (total_profit / total_cost) * 100
    return {
        "total_mv": total_mv,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_profit_rate": total_profit_rate,
    }


def _build_stock_rate_map(holdings_details: list[dict] | None) -> dict[str, float]:
    """构建 {code: profit_rate} 映射用于个股级校验。

    每个品种的盈亏比例来自持仓明细中的 profit_rate 字段，
    用于在 LLM 提及个股收益时进行精准比对，而非一律回退到组合总收益。
    """
    result: dict[str, float] = {}
    for d in holdings_details or []:
        code = d.get("code", "") or ""
        rate = d.get("profit_rate")
        if code and rate is not None:
            result[code] = float(rate)
    return result

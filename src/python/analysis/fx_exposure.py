"""汇率敞口分析模块 — 货币分类与外汇风险敞口判断。

基于上市地和名称关键词，将持仓按交易币种分类（CNY / HKD / USD），
汇总各币种占比（市值加权），供 LLM 注入外汇风险判断。

使用方式:
    >>> from src.python.analysis.fx_exposure import fx_exposure
    >>> result = fx_exposure(holdings_details)
    >>> result["summary"]
    '人民币 70.0%、港币 20.0%、美元 10.0%'
"""

from __future__ import annotations

from typing import Any

from src.python.code_utils import get_currency_by_code

# ── 币种常量 ──────────────────────────────────────────────────

CURRENCY_CNY = "CNY"
CURRENCY_HKD = "HKD"
CURRENCY_USD = "USD"
CURRENCY_OTHER = "其他"

_CURRENCY_LABELS: dict[str, str] = {
    CURRENCY_CNY: "人民币",
    CURRENCY_HKD: "港币",
    CURRENCY_USD: "美元",
    CURRENCY_OTHER: "其他币种",
}

# 港股通换汇说明（附加在 HKD 段落，提醒用户实际换汇成本隐含）
_HKD_DISCLAIMER = "（港股通品种为港币计价，实际换汇成本隐含在汇率中）"


def fx_exposure(holdings_details: list[dict[str, Any]] | None) -> dict[str, Any]:
    """计算持仓的币种敞口分布（市值加权）。

    Args:
        holdings_details: 持仓明细列表，每项至少含 name / code / market_value 字段。
            可为 None 或空列表，此时返回空结果。

    Returns:
        包含以下键的字典:
            - "exposures": list[dict] — 每币种一行，含 currency, label, total_mv, pct
            - "summary": str — 格式化摘要文本，如 "人民币 70.0%、港币 20.0%、美元 10.0%"
            - "has_foreign": bool — 是否含非人民币资产
            - "hkd_suffix": str — 港股说明（如有港股则显示，否则为空字符串）
            - "total_mv": float — 总市值（用于百分比计算基数）
    """
    if not holdings_details:
        return {"exposures": [], "summary": "", "has_foreign": False, "hkd_suffix": "", "total_mv": 0.0}

    # 按币种汇总市值
    currency_mv: dict[str, float] = {}
    total_mv = 0.0
    has_hkd = False

    for h in holdings_details:
        name = h.get("name", "")
        code = h.get("code", "")
        mv = h.get("market_value", 0) or 0

        if mv <= 0:
            continue

        currency = get_currency_by_code(name, code)
        currency_mv[currency] = currency_mv.get(currency, 0) + mv
        total_mv += mv
        if currency == CURRENCY_HKD:
            has_hkd = True

    if total_mv <= 0:
        return {"exposures": [], "summary": "", "has_foreign": False, "hkd_suffix": "", "total_mv": 0.0}

    # 构建输出
    exposures = []
    for currency in (CURRENCY_CNY, CURRENCY_HKD, CURRENCY_USD):
        mv = currency_mv.get(currency, 0)
        pct = (mv / total_mv) * 100 if total_mv > 0 else 0.0
        if mv > 0:
            exposures.append(
                {
                    "currency": currency,
                    "label": _CURRENCY_LABELS.get(currency, currency),
                    "total_mv": round(mv, 2),
                    "pct": round(pct, 1),
                }
            )

    # 处理其他币种（按货币代码排序展示）
    other_mv = sum(mv for c, mv in currency_mv.items() if c not in (CURRENCY_CNY, CURRENCY_HKD, CURRENCY_USD))
    if other_mv > 0:
        other_pct = (other_mv / total_mv) * 100
        exposures.append(
            {
                "currency": CURRENCY_OTHER,
                "label": _CURRENCY_OTHER,
                "total_mv": round(other_mv, 2),
                "pct": round(other_pct, 1),
            }
        )

    # 摘要文本
    summary_parts = [f"{e['label']} {e['pct']:.1f}%" for e in exposures]
    summary = "、".join(summary_parts)

    has_foreign = any(e["currency"] != CURRENCY_CNY for e in exposures)
    hkd_suffix = _HKD_DISCLAIMER if has_hkd else ""

    return {
        "exposures": exposures,
        "summary": summary,
        "has_foreign": has_foreign,
        "hkd_suffix": hkd_suffix,
        "total_mv": round(total_mv, 2),
    }

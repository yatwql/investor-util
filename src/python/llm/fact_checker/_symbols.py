"""fact_checker 子包 — 检查器 2：品种存在性。

校验 LLM 输出的品种代码是否确实存在于持仓中。
"""

from __future__ import annotations

from src.python.llm.fact_checker._constants import _INDEX_CODES, _SUGGESTION_KEYWORDS
from src.python.llm.fact_checker._context import _is_suggestion_context
from src.python.llm.fact_checker._patterns import _CODE_PATTERN
from src.python.llm.fact_checker._utils import _extract_holding_map


def check_symbol_existence(
    text: str,
    holdings_details: list[dict] | None,
    extra_valid_codes: set[str] | None = None,
    suggestion_keywords: tuple[str, ...] | None = _SUGGESTION_KEYWORDS,
) -> tuple[list[str], int, int, list[str]]:
    """检查 LLM 输出的品种代码是否确实存在于持仓中。

    跳过常见指数代码（如沪深300:000300），仅校验疑似持仓代码。
    支持传入 extra_valid_codes 扩展有效代码集（如穿透分析的股票代码）。

    返回 4 元组，第 4 项是建议语境提及的列表（不计入幻觉率）。
    建议提及是指 LLM 在建议/推荐语境中引用非持仓代码（如"建议关注511010"），
    而非声称持有该品种。

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。
        extra_valid_codes: 额外有效代码集合（如穿透 TOP10 中的股票代码）。
        suggestion_keywords: 建议语境关键词元组，设为 None 可关闭此检测。

    Returns:
        (issues, total_checked, passed_count, suggestion_issues)
        — suggestion_issues 是 issues 的子集，已从 issues 中移除，
          不计入幻觉率。
    """
    issues: list[str] = []
    suggestions: list[str] = []
    if not text or not holdings_details:
        return issues, 0, 0, suggestions

    valid_codes = _extract_holding_map(holdings_details)
    codes_found = set(_CODE_PATTERN.findall(text))

    total_checked = len(codes_found)
    passed = 0

    # 合并额外有效代码
    extra_codes = extra_valid_codes or set()
    all_valid = set(valid_codes.keys()) | _INDEX_CODES | extra_codes

    for code in codes_found:
        if code in all_valid:
            passed += 1
        else:
            # 判断是否建议语境（如"建议关注511010"）
            if suggestion_keywords is not None and _is_suggestion_context(code, text):
                suggestions.append(f"品种代码 {code} 不在当前持仓中（建议提及）")
            else:
                issues.append(f"品种代码 {code} 不在当前持仓中")

    return issues, total_checked, passed, suggestions

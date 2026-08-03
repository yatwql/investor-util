"""fact_checker 子包 — 检查器 3：排名正确性。

校验 LLM "最大持仓"/"第一重仓"等声称与实际排名一致。
"""

from __future__ import annotations

from src.python.llm.fact_checker._patterns import _CODE_PATTERN, _RANK_MAX_PATTERN
from src.python.llm.fact_checker._utils import _split_sentences


def check_ranking_correctness(
    text: str,
    holdings_details: list[dict] | None,
    is_penetration_module: bool = False,
) -> tuple[list[str], int, int]:
    """检查 LLM 的持仓排名声称是否与实际排名一致。

    检测 "最大持仓"、"第一重仓"、"前三大" 等排名声称，
    验证所提及的品种代码确实处于对应排名位置。

    穿透分析模块（is_penetration_module=True）时跳过排名校验，
    因为穿透分析使用不同的排名维度（穿透权重而非直接持仓）。

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。
        is_penetration_module: 是否为穿透分析模块。

    Returns:
        (issues, total_checked, passed_count)
    """
    issues: list[str] = []
    if not text or not holdings_details:
        return issues, 0, 0

    # 穿透分析模块跳过排名校验（排名维度不同）
    if is_penetration_module:
        return issues, 0, 0

    # 按市值降序排列
    sorted_holdings = sorted(
        [d for d in holdings_details if (d.get("market_value", 0) or 0) > 0],
        key=lambda d: d.get("market_value", 0) or 0,
        reverse=True,
    )
    if not sorted_holdings:
        return issues, 0, 0

    # {code: rank_index} 映射
    rank_map: dict[str, int] = {}
    for i, d in enumerate(sorted_holdings):
        code = d.get("code", "")
        if code:
            rank_map[code] = i

    total_checked = 0
    passed = 0

    for sentence in _split_sentences(text):
        if not _RANK_MAX_PATTERN.search(sentence):
            continue

        codes_in_sentence = _CODE_PATTERN.findall(sentence)
        if not codes_in_sentence:
            continue

        total_checked += 1
        mentioned_code = codes_in_sentence[0]
        rank = rank_map.get(mentioned_code)

        if rank is None:
            issues.append(f"品种 {mentioned_code} 无法在持仓市值排名中找到")
            continue

        # 检查 "最大/最重/第一" 声称
        if rank != 0:
            actual_top = sorted_holdings[0]
            actual_name = actual_top.get("name", "") or ""
            actual_code = actual_top.get("code", "") or ""
            issues.append(f"声称 {mentioned_code} 为最大持仓，但实际最大持仓为 {actual_code}（{actual_name}）")
        else:
            passed += 1

    return issues, total_checked, passed

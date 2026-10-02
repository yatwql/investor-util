"""事实校验（独立检查器精准分类，幻理率统计输入）。"""

from __future__ import annotations

from typing import Any

import logging

logger = logging.getLogger("hallucination_sampler")

# ── 事实校验（使用独立检查器，精准分类） ────────────────────────


def _run_fact_check(
    llm_output: str,
    holdings_details: list[dict],
    module_label: str,
    extra_valid_codes: set[str] | None = None,
    is_penetration_module: bool = False,
) -> dict[str, Any]:
    """对 LLM 输出执行全量事实校验（使用独立检查器）。

    直接调用 fact_checker 的三个独立检查器，精确统计。

    Returns:
        {"issues": {...}, "total_checks": int, "hallucination_rate": float, ...}
    """
    from src.python.llm.fact_checker._runner import (
        check_numerical_consistency,
        check_ranking_correctness,
        check_symbol_existence,
    )
    from src.python.llm.fact_checker._utils import _strip_html as _fc_strip_html

    text = _fc_strip_html(llm_output)

    # 检查器 1：数值一致性
    num_issues, num_checked, num_passed, num_corrections = check_numerical_consistency(text, holdings_details)

    # 检查器 2：品种存在性（建议语境已在内部处理）
    sym_issues, sym_checked, sym_passed, sym_suggestions = check_symbol_existence(
        text,
        holdings_details,
        extra_valid_codes,
    )

    # 检查器 3：排名正确性
    rank_issues, rank_checked, rank_passed = check_ranking_correctness(
        text,
        holdings_details,
        is_penetration_module,
    )

    total_checks = num_checked + sym_checked + rank_checked
    total_issues = len(num_issues) + len(sym_issues) + len(rank_issues)
    hallucination_rate = total_issues / total_checks if total_checks > 0 else 0.0

    return {
        "issues": {
            "numerical": num_issues,
            "symbol": sym_issues,
            "rank": rank_issues,
            "symbol_suggestion": sym_suggestions,
        },
        "numerical_corrections": num_corrections,
        "total_checks": total_checks,
        "num_checked": num_checked,
        "sym_checked": sym_checked,
        "rank_checked": rank_checked,
        "sym_suggestion_count": len(sym_suggestions),
        "hallucination_rate": hallucination_rate,
    }

"""fact_checker 子包 — run_fact_check 统一入口。

依次执行数值一致性、品种存在性、排名正确性三项检查，
当 auto_correct=True 时自动修正错误数值。
"""

from __future__ import annotations

import logging

from src.python.llm.fact_checker._constants import _DEFAULT_TOLERANCE_PCT
from src.python.llm.fact_checker._corrections import apply_numerical_corrections
from src.python.llm.fact_checker._numerical import check_numerical_consistency
from src.python.llm.fact_checker._ranking import check_ranking_correctness
from src.python.llm.fact_checker._symbols import check_symbol_existence
from src.python.llm.fact_checker._utils import _sentence_snippet, _strip_html

logger = logging.getLogger("invest")


def run_fact_check(
    html_content: str,
    holdings_details: list[dict] | None,
    module_label: str = "",
    extra_valid_codes: set[str] | None = None,
    is_penetration_module: bool = False,
    auto_correct: bool = True,
    tolerance_pct: float | None = None,
    tolerance_overrides: dict[str, float] | None = None,
    history_data: dict | None = None,
    skip_ranking_check: bool = False,
) -> tuple[str, str]:
    """对 LLM 生成的 HTML 内容执行全量事实校验与自动修正。

    依次执行数值一致性、品种存在性、排名正确性三项检查，
    当 auto_correct=True 时自动修正错误数值。
    返回 (修正后的 HTML, 校验摘要 HTML)。

    v2 新增参数：
        extra_valid_codes: 额外有效代码集合（穿透分析用）。
        is_penetration_module: 是否为穿透分析模块（排名使用穿透排序而非直接持仓）。

    v3 新增参数：
        auto_correct: 是否自动修正错误的数值（默认 True）。
        tolerance_pct: 数值偏差容差（百分点），覆盖模块级配置。
        tolerance_overrides: 模块名→容差映射，如 {"expert_review": 2.0}。

    v4 新增参数：
        history_data: 组合历史走势数据字典，用于提取最大回撤等指标。

    v5 新增参数：
        skip_ranking_check: 是否跳过排名正确性校验（默认 False）。
            缓存命中的 LLM 内容基于生成时的数据快照，用当前市值校验其排名
            声称会因价格变动产生"排名翻转"误报 → 由调用方传 True。
            数值/品种校验仍执行。

    Args:
        html_content: LLM 生成的 HTML 内容。
        holdings_details: 持仓明细数据（用于品种存在性和排名校验）。
        module_label: 模块中文名，用于摘要标签（如"全球政经局势"）。
        extra_valid_codes: 额外有效代码集合（穿透分析用）。
        is_penetration_module: 是否为穿透分析模块。
        auto_correct: 是否自动修正错误的数值。
        tolerance_pct: 数值偏差容差（百分点），默认 None 使用 _DEFAULT_TOLERANCE_PCT。
        tolerance_overrides: 按模块覆盖容差。
        history_data: 组合历史走势数据字典（含 max_drawdown_pct）。
        skip_ranking_check: 是否跳过排名正确性校验。

    Returns:
        (corrected_html, summary_html)
        — corrected_html 是 auto_correct 后的内容（未修正时与原内容相同）。
        — summary_html 为 HTML 摘要片段，空字符串表示无内容或无需检查。
    """
    if not html_content:
        return html_content, ""

    # 确定容差（模块级覆盖优先）
    effective_tolerance = _DEFAULT_TOLERANCE_PCT
    if tolerance_pct is not None:
        effective_tolerance = tolerance_pct
    elif tolerance_overrides and module_label:
        key = module_label.replace(" ", "_")
        effective_tolerance = tolerance_overrides.get(key, _DEFAULT_TOLERANCE_PCT)

    # 从 history_data 提取最大回撤
    _max_dd = None
    if history_data and history_data.get("max_drawdown_pct"):
        _max_dd = float(history_data["max_drawdown_pct"])

    text = _strip_html(html_content)
    all_issues: list[str] = []
    total_checks = 0
    total_passed = 0
    all_corrections: list[tuple[str, str, str]] = []

    # 检查 1：数值一致性（含回撤语境检测）
    num_issues, num_checked, num_passed, corrections = check_numerical_consistency(
        text,
        holdings_details,
        tolerance_pct=effective_tolerance,
        max_drawdown_pct=_max_dd,
    )
    all_issues.extend(num_issues)
    total_checks += num_checked
    total_passed += num_passed
    all_corrections.extend(corrections)

    # 检查 2：品种存在性（支持穿透分析的额外有效代码）
    sym_issues, sym_checked, sym_passed, sym_suggestions = check_symbol_existence(
        text,
        holdings_details,
        extra_valid_codes,
    )
    all_issues.extend(sym_issues)
    total_checks += sym_checked
    total_passed += sym_passed

    # 检查 3：排名正确性（穿透分析模块使用穿透排名基线）
    # skip_ranking_check=True（缓存命中场景）时跳过排名校验：
    # 缓存内容基于生成时的价格快照，当前市值可能已发生排名翻转 → 误报。
    if skip_ranking_check:
        rank_issues, rank_checked, rank_passed = [], 0, 0
    else:
        rank_issues, rank_checked, rank_passed = check_ranking_correctness(
            text, holdings_details, is_penetration_module
        )
    all_issues.extend(rank_issues)
    total_checks += rank_checked
    total_passed += rank_passed

    # ── 自动修正 ──
    corrected_html = html_content
    correction_lines = ""
    if auto_correct and all_corrections:
        corrected_html = apply_numerical_corrections(html_content, all_corrections)
        # 修正明细：日志记录 + HTML 摘要灰色行（供用户直接查看具体修正了什么）。
        # 4 元组 correction 带语义 reason（如"601939实际收益率187.1%"），
        # 展示"修正的是哪个数字、其语义"，而非仅截断句段。
        _parts = []
        for cx in all_corrections:
            w, c, s = cx[0], cx[1], cx[2]
            reason = cx[3] if len(cx) >= 4 and cx[3] else _sentence_snippet(s)
            _parts.append(f"{w}%→{c}%（{reason}）")
        _corr_detail = "; ".join(_parts)
        logger.info(
            "[%s] 事实校验自动修正 %d 处数值: %s",
            module_label or "LLM",
            len(all_corrections),
            _corr_detail,
        )
        correction_lines = f'\n<span style="color:#888;font-size:11px">已修正明细: {_corr_detail}</span>'

    if total_checks == 0:
        return corrected_html, ""

    tag = f"[{module_label}] " if module_label else ""

    # 构建建议提及行（灰色，不计入告警）
    suggestion_lines = ""
    if sym_suggestions:
        sug_detail = "; ".join(sym_suggestions)
        suggestion_lines = (
            f'\n<span style="color:#999;font-size:11px">ℹ {tag}建议提及（不计入校验）: {sug_detail}</span>'
        )

    if not all_issues:
        # 全部通过 — 绿色摘要（含建议提及则灰色追加）
        summary = f"{tag}✓ 事实校验通过：{total_passed}/{total_checks} 项检查全部通过"
        result = f'<p style="color:#4a4;font-size:12px">{summary}</p>'
        if suggestion_lines:
            result += suggestion_lines
        return corrected_html, result + correction_lines

    # 存在不一致 — 黄色告警摘要（若已修正则标注修正条数，已修正项不重复列出）
    corrected_values = {c[0] for c in all_corrections} if auto_correct else set()
    detail_lines: list[str] = []
    for issue in all_issues:
        # 跳过已自动修正的数值的告警（用户在内容中已看不到该值，列出徒增困惑）
        if any(cv in issue for cv in corrected_values):
            continue
        detail_lines.append(f"⚠ {tag}{issue}")
    auto_msg = f"（自动修正 {len(all_corrections)} 处数值）" if auto_correct and all_corrections else ""
    if detail_lines:
        summary = f"{tag}事实校验：{total_passed}/{total_checks} 项通过，{len(detail_lines)} 项提示{auto_msg}\n"
        summary += "\n".join(detail_lines)
    else:
        summary = f"{tag}✓ 事实校验通过：{total_passed}/{total_checks} 项检查全部通过{auto_msg}"
    return corrected_html, f'<p style="color:#a40;font-size:12px">{summary}</p>{suggestion_lines}{correction_lines}'

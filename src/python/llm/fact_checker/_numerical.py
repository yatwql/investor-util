"""fact_checker 子包 — 检查器 1：数值一致性（带语境感知）。

校验 LLM 引用的收益/回报率百分比与实际数据匹配。
"""

from __future__ import annotations

import re

from src.python.llm.fact_checker._constants import (
    _DEFAULT_TOLERANCE_PCT,
    _EXPOSURE_KEYWORDS,
    _INDEX_CODES,
    _POSITION_WEIGHT_KEYWORDS,
    _PROFIT_KEYWORDS,
    _PROPORTION_KEYWORDS,
    _REBALANCE_TARGET_KEYWORDS,
)
from src.python.llm.fact_checker._context import (
    _is_contribution_sentence,
    _is_change_rate_context,
    _is_drawdown_context,
    _is_hypothetical_context,
    _is_position_weight_context,
)
from src.python.llm.fact_checker._patterns import _CODE_PATTERN, _PERCENT_PATTERN
from src.python.llm.fact_checker._utils import (
    _build_stock_rate_map,
    _calc_portfolio_values,
    _extract_holding_map,
    _sentence_snippet,
    _split_sentences,
)


def _evaluate_percent_value(
    value: float,
    value_str: str,
    sentence: str,
    stock_rates_abs: dict[str, float],
    holding_codes: set[str],
    profit_rate: float,
    profit_sign: str,
    tolerance_pct: float = _DEFAULT_TOLERANCE_PCT,
    drawdown_pct: float | None = None,
    is_drawdown: bool = False,
    is_change_rate: bool = False,
) -> tuple[str | None, tuple[str, str, str] | None]:
    """评估单个百分比数值。

    Args:
        value: 数值浮点。
        value_str: 数值原始文本（用于修正替换）。
        sentence: 所在句子。
        stock_rates_abs: {code: abs_profit_rate} 映射。
        holding_codes: 持仓代码集合。
        profit_rate: 组合总收益率（绝对值）。
        profit_sign: "盈利" / "亏损"。
        tolerance_pct: 容差（百分点）。
        drawdown_pct: 实际最大回撤百分比（可选），is_drawdown=True 时使用。
        is_drawdown: 是否为回撤语境数值。
        is_change_rate: 是否为环比/同比变化率语境数值（相对上期，非收益率）。

    Returns:
        (issue_str_or_None, correction_or_None)
        correction = (wrong_value_str, correct_value_str, context_sentence)
    """
    # 环比/同比变化率语境 → 数值为相对上期的变化比例而非收益率，不可比较
    if is_change_rate:
        return None, None

    # 品种计数/比例语境
    if any(kw in sentence for kw in _PROPORTION_KEYWORDS):
        return None, None

    # 回撤语境 → 与实际最大回撤比较
    if is_drawdown:
        if drawdown_pct is None or drawdown_pct < 0.01:
            return None, None  # 无回撤数据，无法校验，跳过
        diff = abs(value - drawdown_pct)
        if diff <= tolerance_pct:
            return None, None
        correct_str = f"{drawdown_pct:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"回撤相关数值 {value}% 与实际最大回撤 {correct_str}% 偏差超过容差（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence)

    # 无收益关键词或收益率太小 → 无法校验
    is_profit_context = any(kw in sentence for kw in _PROFIT_KEYWORDS)
    if not is_profit_context or profit_rate < 0.01:
        return None, None

    # 构建参考收益率列表：个股收益率 + 组合总收益率
    ref_rates: dict[str, float] = dict(stock_rates_abs)
    ref_rates["_portfolio"] = profit_rate

    closest_ref = min(ref_rates, key=lambda k: abs(value - ref_rates[k]))
    closest_diff = abs(value - ref_rates[closest_ref])

    # 策略 1：最接近的参考值在容差内
    if closest_diff <= tolerance_pct:
        return None, None

    # 策略 2：句中代码全部为指数代码
    codes_in_sentence = _CODE_PATTERN.findall(sentence)
    index_codes_in_sentence = [c for c in codes_in_sentence if c in _INDEX_CODES]
    holding_codes_in_sentence = [c for c in codes_in_sentence if c in holding_codes]
    if not holding_codes_in_sentence and index_codes_in_sentence:
        return None, None

    # 策略 3：贡献/归因类关键词
    if _is_contribution_sentence(sentence):
        return None, None

    # 策略 4：金融基准类关键词
    if any(kw in sentence for kw in ("国债", "利率", "通胀", "GDP", "CPI", "PMI")):
        return None, None

    # 策略 5：仓位/占比语境
    if _is_position_weight_context(sentence):
        return None, None

    # 策略 6：假设/情景语境
    if _is_hypothetical_context(sentence):
        return None, None

    # 策略 7：调仓目标语境
    if any(kw in sentence for kw in _REBALANCE_TARGET_KEYWORDS):
        return None, None

    # 策略 8：币种/敞口语境
    if any(kw in sentence for kw in _EXPOSURE_KEYWORDS):
        return None, None

    # 全部策略均未通过 → 标记为不一致
    if len(holding_codes_in_sentence) > 1:
        best_code = min(holding_codes_in_sentence, key=lambda c: abs(value - stock_rates_abs.get(c, 999)))
    elif holding_codes_in_sentence:
        best_code = holding_codes_in_sentence[0]
    else:
        best_code = None

    if best_code:
        stock_rate = stock_rates_abs.get(best_code, 0)
        correct_str = f"{stock_rate:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"收益相关数值 {value}% 与 {best_code} 的实际收益率 {correct_str}%（{profit_sign}）偏差超过容差（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence)
    elif closest_ref != "_portfolio":
        stock_rate = stock_rates_abs.get(closest_ref, 0)
        correct_str = f"{stock_rate:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"收益相关数值 {value}% 与 {closest_ref} 的实际收益率 {correct_str}%（{profit_sign}）偏差超过容差（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence)
    else:
        correct_str = f"{profit_rate:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"收益相关数值 {value}% 与实际累计收益率 {correct_str}%（{profit_sign}）偏差超过容差（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence)


def check_numerical_consistency(
    text: str,
    holdings_details: list[dict] | None,
    tolerance_pct: float = _DEFAULT_TOLERANCE_PCT,
    max_drawdown_pct: float | None = None,
) -> tuple[list[str], int, int, list[tuple[str, str, str]]]:
    """检查 LLM 输出中的百分比数值与实际组合/个股数据是否一致。

    v2 改进：
    - 按句子粒度分析，准确识别收益归因段落并跳过
    - 优先匹配句中持仓代码对应的个股收益率
    - 未识别到个股时回退到组合总收益率
    - 指数基准代码数值自动跳过
    - 贡献度/归因段落数值跳过（不可直接比较）

    v3 改进：
    - 返回修正信息列表，供 auto_correct 消费
    - 容差可配置

    v4 改进：
    - 回撤语境检测：将"最大回撤"等数值与实际最大回撤比较而非与收益率比较

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。
        tolerance_pct: 数值偏差容差（百分点），默认 1.0。
        max_drawdown_pct: 实际组合最大回撤百分比（可选）。

    Returns:
        (issues, total_checked, passed_count, corrections)
        corrections: [(wrong_value_str, correct_value_str, context_sentence), ...]
    """
    issues: list[str] = []
    corrections: list[tuple[str, str, str]] = []
    if not text:
        return issues, 0, 0, corrections

    values = _calc_portfolio_values(holdings_details)
    profit_rate = abs(values["total_profit_rate"])
    profit_sign = "盈利" if values["total_profit"] >= 0 else "亏损"

    # 构建个股收益率映射
    stock_rates = _build_stock_rate_map(holdings_details)
    stock_rates_abs = {code: abs(r) for code, r in stock_rates.items()}
    holding_codes = set(_extract_holding_map(holdings_details).keys())

    total_checked = 0
    passed = 0
    seen_values: set[str] = set()

    for sentence in _split_sentences(text):
        # 跳过收益归因段落（贡献度占比不可与收益率直接比较）
        if _is_contribution_sentence(sentence):
            continue

        for match in re.finditer(_PERCENT_PATTERN, sentence):
            value_str = match.group(1)
            if value_str in seen_values:
                continue
            seen_values.add(value_str)
            value = float(value_str)

            total_checked += 1

            # 回撤语境检测
            is_dd = _is_drawdown_context(sentence, match.start()) if max_drawdown_pct is not None else False
            # 环比/同比变化率语境检测
            is_change_rate = _is_change_rate_context(sentence, match.start())

            issue, correction = _evaluate_percent_value(
                value,
                value_str,
                sentence,
                stock_rates_abs,
                holding_codes,
                profit_rate,
                profit_sign,
                tolerance_pct=tolerance_pct,
                drawdown_pct=max_drawdown_pct,
                is_drawdown=is_dd,
                is_change_rate=is_change_rate,
            )
            if issue is None:
                passed += 1
            else:
                issues.append(issue)
                if correction:
                    corrections.append(correction)

    return issues, total_checked, passed, corrections

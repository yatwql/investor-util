"""fact_checker 子包 — 检查器 1：数值一致性（带语境感知）。

校验 LLM 引用的收益/回报率百分比与实际数据匹配。
"""

from __future__ import annotations

import re

from src.python.llm.fact_checker._constants import (
    _DEFAULT_TOLERANCE_PCT,
    _EXPOSURE_KEYWORDS,
    _INDEX_CODES,
    _PROFIT_KEYWORDS,
    _PROPORTION_KEYWORDS,
    _REBALANCE_TARGET_KEYWORDS,
)
from src.python.llm.fact_checker._context import (
    _is_benchmark_relative_context,
    _is_contribution_sentence,
    _is_change_rate_context,
    _is_daily_change_context,
    _is_drawdown_context,
    _is_hypothetical_context,
    _is_portfolio_daily_change_context,
    _is_portfolio_level_context,
    _is_position_weight_context,
    _is_trim_target_context,
    _is_weight_context,
    _is_win_rate_context,
)
from src.python.llm.fact_checker._patterns import _CODE_PATTERN, _PERCENT_PATTERN
from src.python.llm.fact_checker._utils import (
    _build_stock_change_map,
    _build_stock_rate_map,
    _calc_portfolio_values,
    _extract_holding_map,
    _locate_subject_code,
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
    is_daily_change: bool = False,
    stock_changes: dict[str, float] | None = None,
    name_to_code: dict[str, str] | None = None,
    anchor: int = 0,
    stock_rates: dict[str, float] | None = None,
    profit_rate_signed: float | None = None,
    is_win_rate: bool = False,
    is_weight: bool = False,
    is_benchmark_relative: bool = False,
    is_trim_target: bool = False,
) -> tuple[str | None, tuple[str, str, str, str] | None]:
    """评估单个百分比数值。

    Args:
        value: 数值浮点。
        value_str: 数值原始文本（用于修正替换）。
        sentence: 所在句子。
        stock_rates_abs: {code: abs_profit_rate} 映射（最近邻比较用）。
        holding_codes: 持仓代码集合。
        profit_rate: 组合总收益率（绝对值）。
        profit_sign: "盈利" / "亏损"。
        tolerance_pct: 容差（百分点）。
        drawdown_pct: 实际最大回撤百分比（可选），is_drawdown=True 时使用。
        is_drawdown: 是否为回撤语境数值。
        is_change_rate: 是否为环比/同比变化率语境数值（相对上期，非收益率）。
        is_daily_change: 是否为单日/当日涨跌语境数值（相对昨收，非收益率）。
        stock_changes: {code: change_pct} 单日涨跌映射（单日涨跌语境校验用）。
        name_to_code: {name: code} 名称映射（句中以名称指代持仓时定位用）。
        anchor: 百分比数值在句子中的位置（match.start()），用于定位主体。
        stock_rates: {code: profit_rate} 带符号映射（修正输出用，保留盈亏方向）。
        profit_rate_signed: 组合总收益率带符号（修正输出用）。
        is_win_rate: 是否为胜率语境（盈利品种占比，非收益率）。
        is_weight: 是否为评分权重语境（维度权数，非收益率）。
        is_benchmark_relative: 是否为相对基准跑输/跑赢语境（指数差，非收益率）。
        is_trim_target: 是否为止盈/减仓目标比例语境（调仓目标，非收益率）。

    Returns:
        (issue_str_or_None, correction_or_None)
        correction = (wrong_value_str, correct_value_str, context_sentence, reason)
        reason 为修正语义（如"601939实际收益率187.1%"），供修正明细展示。
    """
    # 环比/同比变化率、胜率、评分权重、相对基准跑输/跑赢、止盈/减仓目标比例
    # → 数值均非收益率，不可比较。均用近邻窗口检测（数值紧邻对应语境词），
    # 避免同句其他真实收益率被连带跳过。
    if is_change_rate or is_win_rate or is_weight or is_benchmark_relative or is_trim_target:
        return None, None

    # 单日/当日涨跌语境 → 数值为单日行情涨跌而非收益率。
    # 句中含持仓主体（代码/名称）时按该品种 change_pct 校验（维度匹配），
    # 无主体（如"科创50单日重挫4.43%"的指数/大盘）→ 跳过，不误修正为个股收益率。
    if is_daily_change:
        subject = _locate_subject_code(sentence, holding_codes, name_to_code, anchor)
        change = stock_changes.get(subject) if subject and stock_changes else None
        if change is None:
            return None, None  # 无持仓主体或无单日涨跌数据 → 无法校验，跳过
        if abs(value - abs(change)) <= tolerance_pct:
            return None, None
        correct_str = f"{change:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"单日涨跌数值 {value}% 与 {subject} 实际单日涨跌 {correct_str}%（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence, f"{subject}单日涨跌{correct_str}%")

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
        return issue, (value_str, correct_str, sentence, f"回撤实际{correct_str}%")

    # 无收益关键词或收益率太小 → 无法校验
    is_profit_context = any(kw in sentence for kw in _PROFIT_KEYWORDS)
    if not is_profit_context or profit_rate < 0.01:
        return None, None

    # 构建参考收益率列表：个股收益率 + 组合总收益率
    ref_rates: dict[str, float] = dict(stock_rates_abs)
    ref_rates["_portfolio"] = profit_rate

    # 组合级收益语境（"组合累计收益约10.0%"）→ 数值归到组合总收益率而非某个个股。
    # 必须在主体定位前判定：同句含多个持仓代码时（如"组合累计收益10%，招商银行上涨8%，
    # 贵州茅台上涨15%"），组合收益数值若走个股路由会被误归到数值最近的个股。
    if _is_portfolio_level_context(sentence, anchor):
        if abs(value - profit_rate) <= tolerance_pct:
            return None, None
        signed = profit_rate_signed if profit_rate_signed is not None else profit_rate
        correct_str = f"{signed:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"收益相关数值 {value}% 与实际累计收益率 {correct_str}%（{profit_sign}）偏差超过容差（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence, f"组合实际收益率{correct_str}%")

    # 组合单日/当日表现语境（"今日组合 +0.21%"）→ 数值为组合当日收益，非个股收益率，
    # 且无组合当日收益基准数据可校验 → 跳过。必须在此判定：否则回退全局最近邻会把
    # 当日收益（如 0.21%）误修正为数值最接近的品种收益率（如 561910 的 -2.3%）。
    if _is_portfolio_daily_change_context(sentence, anchor):
        return None, None

    # 定位句中明确持仓主体：统一按 _locate_subject_code「紧邻优先 + 代码/全名最近兜底」
    # 归因（含代码、全名、简称、描述性尾名四来源），而非全局最近邻。同句含多个名称
    # 主体时（如"040046 收益率 +130.61%、建设银行收益率 +181.37%"）各数值各自就近
    # 归因，建设银行主体的 181.37% 归 601939，不被句内代码 040046 钉扎。句中无名称/
    # 代码主体时回退全局最近邻（兜底语义）。
    codes_in_sentence = _CODE_PATTERN.findall(sentence)
    index_codes_in_sentence = [c for c in codes_in_sentence if c in _INDEX_CODES]
    holding_codes_in_sentence = [c for c in codes_in_sentence if c in holding_codes]

    name_code = _locate_subject_code(sentence, holding_codes, name_to_code, anchor)
    if name_code is not None and name_code in stock_rates_abs:
        best_code = name_code
    elif len(holding_codes_in_sentence) > 1:
        # 句中主体无收益率数据但多代码：按收益率最近者归因（历史语义，防仅按位置
        # 就近把数值错配到同句其他品种）。
        best_code = min(holding_codes_in_sentence, key=lambda c: abs(value - stock_rates_abs.get(c, 999)))
    elif holding_codes_in_sentence:
        best_code = holding_codes_in_sentence[0]
    else:
        # 句中无代码但以名称指代持仓（如"建设银行收益率+1.87%"）→ 名称定位到代码，
        # 否则该收益声称无法归因到具体品种，会误修正到数值最接近的无关品种。
        # 仅当该品种确有收益率数据（在 stock_rates_abs 中）时采用，否则回退组合收益率。
        best_code = None

    closest_ref = min(ref_rates, key=lambda k: abs(value - ref_rates[k]))

    # 策略 1：句中有明确持仓主体 → 按该主体实际收益率校验（容差内通过）；
    # 主体无收益率数据（ref 为 None）或无主体 → 回退全局最近邻（历史语义）。
    if best_code is not None:
        ref = stock_rates_abs.get(best_code)
        if ref is not None and abs(value - ref) <= tolerance_pct:
            return None, None
        if ref is None and abs(value - ref_rates[closest_ref]) <= tolerance_pct:
            return None, None
    elif abs(value - ref_rates[closest_ref]) <= tolerance_pct:
        return None, None

    # 策略 2：句中代码全部为指数代码
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

    # 全部策略均未通过 → 标记为不一致（best_code 已在策略 1 前解析）

    # 修正输出用带符号收益率（stock_rates / profit_rate_signed），保留盈亏方向：
    # 亏损品种（如 518880 实际 -8.86%）修正时必须输出 -8.9%，不得写成 +8.9%。
    # 最近邻比较仍用绝对值（_PERCENT_PATTERN 不捕获负号，value 恒为正，幅度匹配）。
    if best_code:
        stock_rate = (stock_rates or stock_rates_abs).get(best_code, 0)
        correct_str = f"{stock_rate:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"收益相关数值 {value}% 与 {best_code} 的实际收益率 {correct_str}%（{profit_sign}）偏差超过容差（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence, f"{best_code}实际收益率{correct_str}%")
    elif closest_ref != "_portfolio":
        stock_rate = (stock_rates or stock_rates_abs).get(closest_ref, 0)
        correct_str = f"{stock_rate:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"收益相关数值 {value}% 与 {closest_ref} 的实际收益率 {correct_str}%（{profit_sign}）偏差超过容差（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence, f"{closest_ref}实际收益率{correct_str}%")
    else:
        signed = profit_rate_signed if profit_rate_signed is not None else profit_rate
        correct_str = f"{signed:.1f}"
        _ctx = _sentence_snippet(sentence)
        issue = f"收益相关数值 {value}% 与实际累计收益率 {correct_str}%（{profit_sign}）偏差超过容差（句段：{_ctx}）"
        return issue, (value_str, correct_str, sentence, f"组合实际收益率{correct_str}%")


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

    # 单日涨跌映射 {code: change_pct} 与名称→代码映射（单日涨跌语境校验用）
    stock_changes = _build_stock_change_map(holdings_details)
    name_to_code = {name: code for code, name in _extract_holding_map(holdings_details).items()}

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
            # 单日/当日涨跌语境检测
            is_daily_change = _is_daily_change_context(sentence, match.start())

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
                is_daily_change=is_daily_change,
                stock_changes=stock_changes,
                name_to_code=name_to_code,
                anchor=match.start(),
                # 带符号收益率（修正输出保留盈亏方向）
                stock_rates=stock_rates,
                profit_rate_signed=values["total_profit_rate"],
                # 非收益率语境（胜率/评分权重/相对基准跑输跑赢/止盈减仓目标比例）
                is_win_rate=_is_win_rate_context(sentence, match.start()),
                is_weight=_is_weight_context(sentence, match.start()),
                is_benchmark_relative=_is_benchmark_relative_context(sentence, match.start()),
                is_trim_target=_is_trim_target_context(sentence, match.start()),
            )
            if issue is None:
                passed += 1
            else:
                issues.append(issue)
                if correction:
                    corrections.append(correction)

    return issues, total_checked, passed, corrections

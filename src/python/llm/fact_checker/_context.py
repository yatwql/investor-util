"""fact_checker 子包 — 语境检测函数。

判断百分比数值 / 品种代码所处的语义语境（回撤、变化率、贡献度、仓位、
假设、建议等），供检查器决定是否跳过或如何比较。词表见 _constants.py。
"""

from __future__ import annotations

import re

from src.python.llm.fact_checker._constants import (
    _BENCHMARK_RELATIVE_KEYWORDS,
    _CHANGE_RATE_KEYWORDS,
    _CONDITION_TRIGGER_KEYWORDS,
    _CONTRIBUTION_KEYWORDS,
    _DAILY_MOVE_KEYWORDS,
    _DAILY_TIME_KEYWORDS,
    _DRAWDOWN_KEYWORDS,
    _HYPOTHETICAL_KEYWORDS,
    _PORTFOLIO_KEYWORDS,
    _POSITION_WEIGHT_KEYWORDS,
    _PROFIT_KEYWORDS,
    _SUGGESTION_KEYWORDS,
    _TRIM_TARGET_KEYWORDS,
    _WARNING_THRESHOLD_KEYWORDS,
    _WEIGHT_KEYWORDS,
    _WIN_RATE_KEYWORDS,
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


def _is_daily_change_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在单日/当日涨跌语境中（如"今日下跌-3.41%""单日重挫4.43%"）。

    单日涨跌幅度是相对昨收的单日行情变化，与收益率（相对成本）维度不同，
    不可直接与收益率比较。检测 match 前 18 字符窗口内是否同时出现时间词
    （今日/昨日/单日等）与涨跌动作词（下跌/重挫/收涨等）。

    与 _PROFIT_KEYWORDS（含"上涨/下跌"）冲突时单日涨跌优先：LLM 写
    "今日下跌-3.41%"时"下跌"会使句子被判为收益语境，但该数值是单日涨跌
    而非收益率。仅时间词（如"今日组合累计收益率为30.3%"）不足以判定——
    需同时有涨跌动作词。
    """
    nearby = sentence[max(0, match_start - 18) : match_start + 5]
    has_time = any(kw in nearby for kw in _DAILY_TIME_KEYWORDS)
    has_move = any(kw in nearby for kw in _DAILY_MOVE_KEYWORDS)
    return has_time and has_move


def _is_win_rate_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在胜率语境中（如"持仓胜率80%"）。

    胜率是盈利品种占比，非收益率；但句子常含"盈利"等收益关键词触发收益语境。
    用 match 前 15 字符内的"胜率"判定，而非全句——避免同句首部的真实收益率被连带跳过。
    """
    nearby = sentence[max(0, match_start - 15) : match_start + 5]
    return any(kw in nearby for kw in _WIN_RATE_KEYWORDS)


def _is_weight_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在评分权重语境中（如"风险分散度权重20%"）。

    评分权重是维度权数，非收益率。用 match 前 15 字符内的"权重"判定，
    不纳入"占比/仓位/集中度"（那些由 _is_position_weight_context 全句兜底）。
    """
    nearby = sentence[max(0, match_start - 15) : match_start + 5]
    return any(kw in nearby for kw in _WEIGHT_KEYWORDS)


def _is_benchmark_relative_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在相对基准跑输/跑赢语境中（如"跑输沪深300达1.10%"）。

    相对指数的表现差是百分点而非收益率，直接与持仓收益率比较会误修正。
    用 match 前 20 字符内的"跑输/跑赢/落后于/领先于"判定。
    """
    nearby = sentence[max(0, match_start - 20) : match_start + 10]
    return any(kw in nearby for kw in _BENCHMARK_RELATIVE_KEYWORDS)


def _is_trim_target_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否为止盈/减仓等调仓目标比例（如"建议止盈约30%"）。

    调仓建议中的止盈/减仓/止损比例是相对当前持仓的目标调仓比例，
    与收益率（相对成本）维度不同，直接与收益率比较会被误修正为
    某品种收益率。用 match 前 15 字符内是否出现调仓动作词判定——
    目标比例数值通常紧邻"止盈/减仓"等词（如"止盈约30%"、"-40%"），
    避免同句首部的真实收益率被连带跳过。

    额外识别条件阈值触发式（"收益率超过200%后可考虑部分止盈"）：数值前有
    "超过/达到/突破"等触发词、数值后有止盈/减仓等调仓动作词时，数值是
    条件触发的止盈目标阈值，非对当前收益率的陈述。双条件联合判定，避免
    把"收益率+X%，建议止盈"的真实收益率误判为阈值（该处数值前无触发词）。
    """
    nearby = sentence[max(0, match_start - 15) : match_start + 5]
    if any(kw in nearby for kw in _TRIM_TARGET_KEYWORDS):
        return True
    # 风险警戒阈值（"已接近回调20%的警戒区域"）：警戒词修饰风控阈值而非收益率，
    # 数值与"警戒"间可能间隔数词，用更宽窗口检测。警戒词不修饰真实收益率描述，
    # 宽窗口安全，不会跳过合法收益率校验。
    _wide = sentence[max(0, match_start - 25) : match_start + 8]
    if any(kw in _wide for kw in _WARNING_THRESHOLD_KEYWORDS):
        return True
    # 条件阈值触发式（"超过X%后可考虑部分止盈"）——"止盈"等动作词位于数值
    # 之后较远处（超出 [-15,+5] 邻近窗口），需触发词+后置动作词双条件联合：
    # 仅有触发词而无动作词（如"收益率超过200%，风险很大"）仍按收益率校验。
    _cond = sentence[max(0, match_start - 12) : match_start]
    if any(kw in _cond for kw in _CONDITION_TRIGGER_KEYWORDS):
        _after = sentence[match_start : match_start + 25]
        if any(kw in _after for kw in _TRIM_TARGET_KEYWORDS):
            return True
    return False


def _is_portfolio_level_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在组合级收益语境中（如"组合累计收益约10.0%"）。

    组合级收益数值应归到组合总收益率而非某个个股。用 match 前 15 字符内
    是否出现组合级关键词判定（"组合累计""总收益""整体收益"等），避免同句
    含多个持仓代码时组合收益数值被误路由到数值最近的个股。
    """
    nearby = sentence[max(0, match_start - 15) : match_start]
    return any(kw in nearby for kw in _PORTFOLIO_KEYWORDS)


def _is_portfolio_daily_change_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在组合单日/当日表现语境中（如"今日组合 +0.21%"）。

    组合当日收益（本日涨跌）与收益率（相对成本）维度不同，且系统不提供组合
    当日收益基准数据 → 无法校验，跳过，避免回退全局最近邻把当日收益误修正为
    某个品种收益率。判定：match 前 18 字符内有时间词（今日/本日等），且数值
    紧邻"组合"标记（"今日组合 +0.21%"、"组合+0.21%"）。与组合级累计收益语境
    （_is_portfolio_level_context，校验组合总收益率）互补：组合累计收益
    （"今日组合累计收益30%"）由组合级语境先行校验，本检测仅兜底"组合+时间词"
    但不含累计/总收益关键词的当日表现句。
    """
    if not any(kw in sentence[max(0, match_start - 18) : match_start + 5] for kw in _DAILY_TIME_KEYWORDS):
        return False
    nearby = sentence[max(0, match_start - 8) : match_start]
    return re.search(r"组合\s*[+-]?\s*$", nearby) is not None


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

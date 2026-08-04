"""fact_checker 子包 — 语境检测函数。

判断百分比数值 / 品种代码所处的语义语境（回撤、变化率、贡献度、仓位、
假设、建议等），供检查器决定是否跳过或如何比较。词表见 _constants.py。
"""

from __future__ import annotations

from src.python.llm.fact_checker._constants import (
    _BENCHMARK_RELATIVE_KEYWORDS,
    _CHANGE_RATE_KEYWORDS,
    _CONTRIBUTION_KEYWORDS,
    _DAILY_MOVE_KEYWORDS,
    _DAILY_TIME_KEYWORDS,
    _DRAWDOWN_KEYWORDS,
    _HYPOTHETICAL_KEYWORDS,
    _PORTFOLIO_KEYWORDS,
    _POSITION_WEIGHT_KEYWORDS,
    _PROFIT_KEYWORDS,
    _SUGGESTION_KEYWORDS,
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


def _is_portfolio_level_context(sentence: str, match_start: int) -> bool:
    """判断百分比数值是否在组合级收益语境中（如"组合累计收益约10.0%"）。

    组合级收益数值应归到组合总收益率而非某个个股。用 match 前 15 字符内
    是否出现组合级关键词判定（"组合累计""总收益""整体收益"等），避免同句
    含多个持仓代码时组合收益数值被误路由到数值最近的个股。
    """
    nearby = sentence[max(0, match_start - 15) : match_start]
    return any(kw in nearby for kw in _PORTFOLIO_KEYWORDS)


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

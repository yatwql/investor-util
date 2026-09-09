"""fact_checker 子包 — 自动修正（数值 + 品种代码笔误）。

对 LLM 生成的 HTML 中错误百分比数值执行自动替换，
并对唯一可辨的品种代码笔误（如 561910→161910）做带权重佐证的自动纠正。
"""

from __future__ import annotations

import re

from src.python.llm.fact_checker._constants import (
    _DEFAULT_TOLERANCE_PCT,
    _INDEX_CODES,
    _POSITION_WEIGHT_KEYWORDS,
)
from src.python.llm.fact_checker._context import _is_suggestion_context
from src.python.llm.fact_checker._patterns import _CODE_PATTERN, _PERCENT_PATTERN
from src.python.llm.fact_checker._utils import (
    _build_stock_weight_map,
    _edit_distance_le_one,
    _extract_holding_map,
    _sentence_snippet,
    _strip_html,
)


def apply_numerical_corrections(
    html: str,
    corrections: list[tuple[str, str, str]],
) -> str:
    """对 HTML 内容中的错误百分比数值执行自动替换。

    使用 sentence 上下文确认匹配位置，避免误替换 HTML 属性中的数值。
    按 wrong_value 长度降序替换（避免 "3.7" 先于 "3.79" 被替换）。

    Args:
        html: 原始 HTML 内容。
        corrections: [(wrong_value_str, correct_value_str, context_sentence, reason), ...]。

    Returns:
        修正后的 HTML 内容。
    """
    if not corrections:
        return html

    # 按 wrong_value 降序排列，避免部分匹配问题
    sorted_cx = sorted(corrections, key=lambda c: -len(c[0]))
    stripped = _strip_html(html)

    result = html
    for cx in sorted_cx:
        wrong_val, correct_val, sentence = cx[0], cx[1], cx[2]
        if sentence not in stripped:
            continue

        # 在 HTML 文本中查找 wrong_val%（带可选空格）
        # lookbehind 确保不会替换数字的一部分
        pattern = re.compile(r"(?<!\d)" + re.escape(wrong_val) + r"\s*%")
        # count=1：check 阶段按数值全局去重，每个 wrong_val 在 corrections 中唯一，
        # 只替换判定处一次，避免误伤 HTML 中同值异义的其他出现处
        # （如"止盈约30%"与"收益率30%"并存时只修被判为错误的收益率处）。
        result = pattern.sub(correct_val + "%", result, count=1)

    return result


# 代码笔误权重佐证——笔误代码后紧跟"规模达/占比 X%"这类权重声称，
# 其数值与真实持仓候选的组合权重吻合才自动纠正。仅用于后置本地窗口判定
# （错码 token 结束后 ~_CODE_WEIGHT_SCAN_WINDOW 字符内），不扩张数值检查器
# 的 _POSITION_WEIGHT_KEYWORDS 全句语义。补充 _POSITION_WEIGHT_KEYWORDS
# 未覆盖的"规模达/规模"表述（实盘笔误场景 "161910规模达10.2%"）。
_WEIGHT_CLAIM_KEYWORDS: frozenset[str] = _POSITION_WEIGHT_KEYWORDS | frozenset({"规模达", "规模", "权重达"})

# 错码 token 后扫描权重声称的最大窗口（字符）：约等于一个中文数量短语的宽度
# （"规模达10.2%…"或"占比约 10.2%"），过大易跨到下一个无关百分比。
_CODE_WEIGHT_SCAN_WINDOW = 24


def detect_code_corrections(
    text: str,
    holdings_details: list[dict] | None,
    extra_valid_codes: set[str] | None = None,
) -> list[tuple[str, str, str, str]]:
    """检测可自动纠正的品种代码笔误。

    数值检查器只能修数值、品种检查器只能告警——LLM 若把持仓代码易位一位数字
    （如 561910→161910，实盘穿透深度模块复现），既有的"品种不在持仓"告警虽能
    精确标出，却只能等用户手工核错。本函数在品种存在性告警的基础上补一条
    确定性纠正通道，仅当以下三个条件**全部**满足才判定为笔误并给出纠正：

      - 非合法有效代码：bad 不属于 直接持仓、穿透 extra_valid_codes、常见指数
        三者的并集（建议语境下引用的非持仓代码不纠正——"建议关注511010"是合法推荐）；
      - 唯一近邻：恰好一个直接持仓代码 good 与 bad 编辑距离 ≤1
        （extra/指数不作候选——避免把合法外部代码错当指数/穿透代码误伤）；
      - 权重佐证：bad 结束后 ~24 字符内出现权重声称词（"占比/规模达"等），
        且其后唯一百分比数值与 weight_map[good] 在默认容差（1.0pt）内吻合——
        错码旁边跟着真实持仓的权重比例，是"本意是该持仓"的最强信号。

    Args:
        text: 去 HTML 标签后的纯文本（修正判定统一用与数值检查一致的剥离文本）。
        holdings_details: 持仓明细列表（须含 market_value 以便算权重佐证）。
        extra_valid_codes: 穿透分析等额外有效代码集合（仅作排除，不作纠正候选）。

    Returns:
        [(bad_code, good_code, context_sentence, reason), ...]。
        返回的 code 元组为 4 元组，与数值 correction（wrong, correct, sentence,
        reason）形状一致，便于 runner 统一并入"已修正明细"。
    """
    corrections: list[tuple[str, str, str, str]] = []
    if not text or not holdings_details:
        return corrections

    name_to_code = _extract_holding_map(holdings_details)
    holding_codes = set(name_to_code.keys())
    if not holding_codes:
        return corrections
    weight_map = _build_stock_weight_map(holdings_details)
    extra_codes = extra_valid_codes or set()
    all_valid = holding_codes | _INDEX_CODES | extra_codes

    for cm in _CODE_PATTERN.finditer(text):
        bad = cm.group(0)
        if bad in all_valid:
            continue
        if _is_suggestion_context(bad, text):
            continue
        # 唯一近邻：仅直接持仓代码作为纠正候选（排除 extra/指数），
        # 命中>1 视为歧义 → 保持告警，不自动纠正。
        near = [c for c in holding_codes if _edit_distance_le_one(bad, c)]
        if len(near) != 1:
            continue
        good = near[0]
        weight = weight_map.get(good)
        if weight is None:
            continue

        # 条件三（权重佐证）：扫描错码 token 后窗口内的权重声称词与百分比数值。
        after = text[cm.end() : cm.end() + _CODE_WEIGHT_SCAN_WINDOW]
        if not any(kw in after for kw in _WEIGHT_CLAIM_KEYWORDS):
            continue
        pcts = [float(m.group(1)) for m in _PERCENT_PATTERN.finditer(after)]
        if len(pcts) != 1:
            continue
        if abs(pcts[0] - weight) > _DEFAULT_TOLERANCE_PCT:
            continue

        reason = f"{good}（{name_to_code[good]}）实际权重{weight:.1f}%，与笔误代码的权重声称吻合"
        corrections.append((bad, good, text, reason))
    return corrections


def apply_code_corrections(
    html: str,
    code_corrections: list[tuple[str, str, str, str]],
) -> str:
    """对 HTML 内容中的品种代码笔误执行自动替换。

    与 apply_numerical_corrections 同构：用 context_sentence 确认匹配位置，
    避免误改 HTML 属性/其它同码片段。差异——不做 count=1：一个 6 位错码
    是单一所指，须全文替换（错码是笔误，不存在"同值异义"，残留即隐藏缺陷）。

    Args:
        html: 原始 HTML 内容。
        code_corrections: [(bad_code, good_code, context_sentence, reason), ...]。

    Returns:
        纠正后的 HTML 内容。
    """
    if not code_corrections:
        return html

    # 守卫仅确认错码仍存在于当前内容，而非整句匹配：代码纠正被 runner 在数值
    # 纠正之后应用，此时句内被数值修正过的百分比已变更——整句 stripped 匹配会
    # 因兄弟数值修正而误判跳过。6 位错码是单一所指且全文替换（无需 count=1
    # 定位单处），故以"错码仍在"作前置即可；数值修正只动 % 前数字、绝不触碰
    # 6 位代码本身，此守卫不会因数值修正误跳。
    stripped = _strip_html(html)
    result = html
    for bad, good, _sentence, _reason in code_corrections:
        if bad not in stripped:
            continue
        pattern = re.compile(r"(?<!\d)" + re.escape(bad) + r"(?!\d)")
        result = pattern.sub(good, result)
    return result

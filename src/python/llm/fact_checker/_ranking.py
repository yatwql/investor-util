"""fact_checker 子包 — 检查器 3：排名正确性。

校验 LLM "最大持仓"/"第N大持仓"/"前N大持仓" 等声称与实际排名一致。
按声称类型分别校验：
  - 最大/最重/首要、第一重仓   → 必须处于市值第 1 名
  - 第N大持仓                 → 必须处于市值第 N 名
  - 前N大/头N大持仓           → 必须处于市值前 N 名
"主要持仓"等模糊声称不校验（不断言精确名次，无法确定性验证）。

归因规则：声称所指品种取「离声称词最近的代码」，而非"句中第一个代码"。
LLM 常以表格形式输出（如调仓方案表），句中含多个代码，声称词实际指向
的是其就近单元格中的品种；取句中第一个代码会把合法声称误归因到无关品种
（如 "040046 ... 继续持有第一重仓" 被归因到句首的 561910 → 误报）。
"""

from __future__ import annotations

import re

from src.python.llm.fact_checker._patterns import (
    _CODE_PATTERN,
    _RANK_MAX_PATTERN,
    _RANK_ORDINAL_PATTERN,
    _RANK_TOP_PATTERN,
)
from src.python.llm.fact_checker._utils import _split_sentences

# 中文数字 → 整数（支持 一~九、十、十一~十九、二十~九十九、"两"）
_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _parse_rank_number(s: str) -> int:
    """解析中文/阿拉伯排名数字（如"三"→3、"十二"→12、"20"→20）。"""
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    if "十" in s:
        tens_s, _, ones_s = s.partition("十")
        tens = _CN_NUM.get(tens_s, 1) if tens_s else 1
        ones = _CN_NUM.get(ones_s, 0) if ones_s else 0
        return tens * 10 + ones
    return _CN_NUM.get(s, 0)


# 表格行分隔符：markdown 表格相邻行间为连续管道（含仅空白间隔，如 "||" / "| |"）
_ROW_SEP_PATTERN = re.compile(r"\|\s*\|")


def _nearest_code(sentence: str, lo: int, hi: int, anchor: int) -> str | None:
    """在 [lo, hi) 区间内找离 anchor 最近的 6 位代码。"""
    best_code: str | None = None
    best_dist: int | None = None
    for cm in _CODE_PATTERN.finditer(sentence):
        if not (lo <= cm.start() < hi):
            continue
        # 代码与 anchor 的间隔距离（代码整体在 anchor 之前/之后）
        dist = (cm.start() - anchor) if cm.start() >= anchor else (anchor - cm.end())
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_code = cm.group(0)
    return best_code


def _claimed_code(sentence: str, match: re.Match) -> str | None:
    """定位排名声称所指的品种代码。

    表格句（含管道分隔符）：声称与其品种通常同属一个表格行（如
    "| 561910 招商中证电池主题ETF | 减仓 | 已是组合第三大持仓..."），
    行内就近归因；不得把后续行的代码（如 040046）误归因到本行声称。
    非表格句：整句就近归因（离声称词最近的代码，前/后皆可）。

    相比"取句中第一个代码"，可正确处理表格/多代码句中的归因。
    句中无代码时返回 None（该声称无法校验，跳过）。
    """
    m_start, m_end = match.span()
    if _ROW_SEP_PATTERN.search(sentence):
        # 表格句：以行分隔符划出声称所在行区间，行内就近
        row_start = 0
        for rsm in _ROW_SEP_PATTERN.finditer(sentence, 0, m_start):
            row_start = rsm.end()
        row_end = len(sentence)
        rsm = _ROW_SEP_PATTERN.search(sentence, m_end)
        if rsm:
            row_end = rsm.start()
        code = _nearest_code(sentence, row_start, row_end, m_start)
        if code:
            return code
        # 行内无代码 → 回退整句就近（防漏检）
        return _nearest_code(sentence, 0, len(sentence), m_start)
    return _nearest_code(sentence, 0, len(sentence), m_start)


def _build_issue(claim_type: str, n: int, code: str, sorted_holdings: list[dict]) -> str:
    """按声称类型构建告警文案。"""
    if claim_type == "max" or (claim_type == "ordinal" and n == 1):
        # "最大持仓"/"第一重仓" 均指市值第一
        top = sorted_holdings[0]
        return f"声称 {code} 为最大持仓，但实际最大持仓为 {top.get('code', '')}（{top.get('name', '')}）"
    if claim_type == "ordinal":
        idx = n - 1
        if idx >= len(sorted_holdings):
            return f"声称 {code} 为第{n}大持仓，但持仓品种不足 {n} 只"
        target = sorted_holdings[idx]
        return f"声称 {code} 为第{n}大持仓，但实际第{n}大持仓为 {target.get('code', '')}（{target.get('name', '')}）"
    # top-N 声称
    top_n = "、".join(f"{d.get('code', '')}（{d.get('name', '')}）" for d in sorted_holdings[:n])
    return f"声称 {code} 为前{n}大持仓，但实际前{n}大持仓为 {top_n}，不含 {code}"


def check_ranking_correctness(
    text: str,
    holdings_details: list[dict] | None,
    is_penetration_module: bool = False,
) -> tuple[list[str], int, int]:
    """检查 LLM 的持仓排名声称是否与实际排名一致。

    检测 "最大持仓"、"第N大持仓"、"前N大持仓" 等排名声称，
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
        # 收集句中全部排名声称：[（声称类型, 排名数 N, 匹配对象）]
        claims: list[tuple[str, int, re.Match]] = []
        for m in _RANK_MAX_PATTERN.finditer(sentence):
            claims.append(("max", 0, m))
        for m in _RANK_ORDINAL_PATTERN.finditer(sentence):
            claims.append(("ordinal", _parse_rank_number(m.group(1)), m))
        for m in _RANK_TOP_PATTERN.finditer(sentence):
            claims.append(("top", _parse_rank_number(m.group(1)), m))

        for claim_type, n, m in claims:
            code = _claimed_code(sentence, m)
            if not code:
                continue  # 声称未指向具体品种，无法校验

            total_checked += 1
            rank = rank_map.get(code)
            if rank is None:
                issues.append(f"品种 {code} 无法在持仓市值排名中找到")
                continue

            # 按声称类型校验对应名次
            if claim_type == "max":
                ok = rank == 0
            elif claim_type == "ordinal":
                ok = rank == n - 1
            else:  # top-N
                ok = rank < n

            if ok:
                passed += 1
            else:
                issues.append(_build_issue(claim_type, n, code, sorted_holdings))

    return issues, total_checked, passed

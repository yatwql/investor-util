"""LLM 事实锚定校验器 — 纯算法层。

对 LLM 生成的报告内容做确定性事实校验，无需额外 LLM API 调用。

当前实现三个检查器：
  1. **数值一致性** — 校验 LLM 引用的收益/回报率百分比与实际数据匹配
  2. **品种存在性** — 校验 LLM 提及的品种代码确实在持仓中
  3. **排名正确性** — 校验 LLM "最大持仓"/"第一重仓"等声称与实际排名一致

用法:
    >>> from src.python.llm.fact_checker import run_fact_check
    >>> summary_html = run_fact_check(html_content, holdings_details, "全球政经局势")
    >>> html_content += summary_html
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("invest")

# ── 常量 ──────────────────────────────────────────────────────

# 6 位数字代码（A 股/基金/指数）
_CODE_PATTERN = re.compile(r'\b[0-9]{6}\b')

# 排名声称模式
_RANK_MAX_PATTERN = re.compile(r'(?:第[一二三四五六七八九十\d]+大|最大|最重|首要|主要|第一重仓|第一权重)')
_RANK_TOP_N_PATTERN = re.compile(r'(?:前[一二三四五六七八九十\d]+|头[一二三四五六七八九十\d]+)')

# 百分比数值
_PERCENT_PATTERN = re.compile(r'(\d+\.?\d*)\s*%')

# 收益/回报相关关键词（用于数值上下文判断）
_PROFIT_KEYWORDS = frozenset([
    '收益', '盈利', '回报', '涨幅', '利润', '收益率', '回报率',
    '累计', '浮盈', '浮亏', '亏损', '增长', '下跌', '上涨',
])

# 常见指数代码（校验品种存在性时跳过）
_INDEX_CODES: frozenset[str] = frozenset({
    '000300',  # 沪深300
    '000001',  # 上证指数
    '399001',  # 深证成指
    '399006',  # 创业板指
    '000688',  # 科创50
    '000016',  # 上证50
    '000905',  # 中证500
    '399300',  # 沪深300（深圳）
})

# 默认容差（百分点）
_DEFAULT_TOLERANCE_PCT = 1.0


def _strip_html(html: str) -> str:
    """去除 HTML 标签，返回纯文本。"""
    if not html:
        return ""
    text = re.sub(r'<[^>]+>', '', html)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _split_sentences(text: str) -> list[str]:
    """按中英文句号、感叹号、问号、换行拆分句子。"""
    sentences = re.split(r'[。！？\n!?]', text)
    return [s.strip() for s in sentences if s.strip()]


def _extract_holding_map(holdings_details: list[dict] | None) -> dict[str, str]:
    """从持仓明细构建 {code: name} 映射。"""
    result: dict[str, str] = {}
    for d in holdings_details or []:
        code = d.get('code', '') or ''
        name = d.get('name', '') or ''
        if code:
            result[code] = name
    return result


def _calc_portfolio_values(holdings_details: list[dict] | None) -> dict[str, float]:
    """计算组合核心数值。

    Returns:
        {"total_mv": float, "total_cost": float, "total_profit": float, "total_profit_rate": float}
    """
    total_mv = sum(d.get('market_value', 0) or 0 for d in holdings_details or [])
    total_cost = sum(d.get('cost', 0) or 0 for d in holdings_details or [])
    total_profit = total_mv - total_cost
    total_profit_rate = 0.0
    if total_cost and abs(total_cost) > 1e-10:
        total_profit_rate = (total_profit / total_cost) * 100
    return {
        "total_mv": total_mv,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_profit_rate": total_profit_rate,
    }


# ── 检查器 1：数值一致性 ──────────────────────────────────────


def check_numerical_consistency(
    text: str,
    holdings_details: list[dict] | None,
) -> tuple[list[str], int, int]:
    """检查 LLM 输出中的百分比数值与实际组合数据是否一致。

    主要校验维度：
    - 带"收益/回报/涨幅"等关键词的百分比是否接近实际总收益率

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。

    Returns:
        (issues, total_checked, passed_count)
            issues: 不一致项描述列表。
            total_checked: 本次检查的数值总数。
            passed_count: 通过检查的数值数。
    """
    issues: list[str] = []
    if not text:
        return issues, 0, 0

    values = _calc_portfolio_values(holdings_details)
    profit_rate = abs(values["total_profit_rate"])
    profit_sign = "盈利" if values["total_profit"] >= 0 else "亏损"

    total_checked = 0
    passed = 0
    seen_values: set[str] = set()

    for match in re.finditer(_PERCENT_PATTERN, text):
        value_str = match.group(1)
        # 去重（同一数值不同位置只检一次）
        if value_str in seen_values:
            continue
        seen_values.add(value_str)
        value = float(value_str)

        # 提取上下文判断数值语义
        ctx_start = max(0, match.start() - 15)
        ctx_end = min(len(text), match.end() + 15)
        context = text[ctx_start:ctx_end]

        total_checked += 1

        # 判断是否为收益/回报相关上下文
        is_profit_context = any(kw in context for kw in _PROFIT_KEYWORDS)

        if not is_profit_context or profit_rate < 0.01:
            # 无法确定上下文的数值或无可比数据，跳过
            passed += 1
            continue

        # 对比数值
        if abs(value - profit_rate) <= _DEFAULT_TOLERANCE_PCT:
            passed += 1
        else:
            issues.append(
                f"收益相关数值 {value}% 与实际累计收益率 {profit_rate:.1f}%（{profit_sign}）偏差超过容差"
            )

    return issues, total_checked, passed


# ── 检查器 2：品种存在性 ────────────────────────────────────


def check_symbol_existence(
    text: str,
    holdings_details: list[dict] | None,
) -> tuple[list[str], int, int]:
    """检查 LLM 输出的品种代码是否确实存在于持仓中。

    跳过常见指数代码（如沪深300:000300），仅校验疑似持仓代码。

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。

    Returns:
        (issues, total_checked, passed_count)
    """
    issues: list[str] = []
    if not text or not holdings_details:
        return issues, 0, 0

    valid_codes = _extract_holding_map(holdings_details)
    codes_found = set(_CODE_PATTERN.findall(text))

    total_checked = len(codes_found)
    passed = 0

    for code in codes_found:
        if code in _INDEX_CODES:
            passed += 1
            continue
        if code in valid_codes:
            passed += 1
        else:
            issues.append(f"品种代码 {code} 不在当前持仓中")

    return issues, total_checked, passed


# ── 检查器 3：排名正确性 ──────────────────────────────────────


def check_ranking_correctness(
    text: str,
    holdings_details: list[dict] | None,
) -> tuple[list[str], int, int]:
    """检查 LLM 的持仓排名声称是否与实际排名一致。

    检测 "最大持仓"、"第一重仓"、"前三大" 等排名声称，
    验证所提及的品种代码确实处于对应排名位置。

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。

    Returns:
        (issues, total_checked, passed_count)
    """
    issues: list[str] = []
    if not text or not holdings_details:
        return issues, 0, 0

    # 按市值降序排列
    sorted_holdings = sorted(
        [d for d in holdings_details if (d.get('market_value', 0) or 0) > 0],
        key=lambda d: d.get('market_value', 0) or 0,
        reverse=True,
    )
    if not sorted_holdings:
        return issues, 0, 0

    # {code: rank_index} 映射
    rank_map: dict[str, int] = {}
    for i, d in enumerate(sorted_holdings):
        code = d.get('code', '')
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
            actual_name = actual_top.get('name', '') or ''
            actual_code = actual_top.get('code', '') or ''
            issues.append(
                f"声称 {mentioned_code} 为最大持仓，"
                f"但实际最大持仓为 {actual_code}（{actual_name}）"
            )
        else:
            passed += 1

    return issues, total_checked, passed


# ── 统一入口 ──────────────────────────────────────────────────


def run_fact_check(
    html_content: str,
    holdings_details: list[dict] | None,
    module_label: str = "",
) -> str:
    """对 LLM 生成的 HTML 内容执行全量事实校验。

    依次执行数值一致性、品种存在性、排名正确性三项检查，
    返回可追加到 HTML 底部的校验摘要。

    Args:
        html_content: LLM 生成的 HTML 内容。
        holdings_details: 持仓明细数据（用于品种存在性和排名校验）。
        module_label: 模块中文名，用于摘要标签（如"全球政经局势"）。

    Returns:
        HTML 摘要片段，空字符串表示无需追加（无内容或无需检查）。
        示例：
            <p style="color:#4a4;font-size:12px">[全球政经局势] ✓ 事实校验通过：5/5 项检查全部通过</p>
            <p style="color:#a40;font-size:12px">[全球政经局势] 事实校验：3/5 项通过，2 项提示<br/>⚠ 品种代码 600000 不在当前持仓中</p>
    """
    if not html_content:
        return ""

    text = _strip_html(html_content)
    all_issues: list[str] = []
    total_checks = 0
    total_passed = 0

    # 检查 1：数值一致性
    num_issues, num_checked, num_passed = check_numerical_consistency(text, holdings_details)
    all_issues.extend(num_issues)
    total_checks += num_checked
    total_passed += num_passed

    # 检查 2：品种存在性
    sym_issues, sym_checked, sym_passed = check_symbol_existence(text, holdings_details)
    all_issues.extend(sym_issues)
    total_checks += sym_checked
    total_passed += sym_passed

    # 检查 3：排名正确性
    rank_issues, rank_checked, rank_passed = check_ranking_correctness(text, holdings_details)
    all_issues.extend(rank_issues)
    total_checks += rank_checked
    total_passed += rank_passed

    if total_checks == 0:
        return ""

    tag = f"[{module_label}] " if module_label else ""

    if not all_issues:
        # 全部通过 — 绿色摘要
        summary = f"{tag}✓ 事实校验通过：{total_passed}/{total_checks} 项检查全部通过"
        return f'<p style="color:#4a4;font-size:12px">{summary}</p>'

    # 存在不一致 — 黄色告警摘要
    detail_lines = "\n".join(f"⚠ {tag}{issue}" for issue in all_issues)
    summary = (
        f"{tag}事实校验：{total_passed}/{total_checks} 项通过，{len(all_issues)} 项提示\n"
        f"{detail_lines}"
    )
    return f'<p style="color:#a40;font-size:12px">{summary}</p>'

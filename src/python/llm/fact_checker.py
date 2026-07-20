"""LLM 事实锚定校验器 — 纯算法层。

对 LLM 生成的报告内容做确定性事实校验，无需额外 LLM API 调用。

当前实现三个检查器：
  1. **数值一致性** — 校验 LLM 引用的收益/回报率百分比与实际数据匹配
  2. **品种存在性** — 校验 LLM 提及的品种代码确实在持仓中
  3. **排名正确性** — 校验 LLM "最大持仓"/"第一重仓"等声称与实际排名一致

改进要点（v2）：
  - 数值校验按句子粒度分析，优先匹配个股收益率再回退到组合总收益
  - 收益归因段落（贡献度占比）自动跳过，不与收益率直接比较
  - 指数基准类（沪深300/上证等）数值自动跳过
  - 品种存在性支持传入穿透资产额外有效代码集
  - 排名校验支持模块上下文区分（穿透分析使用穿透排名）

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

# 收益归因段落特征词（数值为贡献度占比，不可与收益率直接比较）
_CONTRIBUTION_KEYWORDS = frozenset([
    '盈利来源', '亏损来源', '收益归因',
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


# ── 辅助函数（v2 感知增强）─────────────────────────────────────


def _build_stock_rate_map(holdings_details: list[dict] | None) -> dict[str, float]:
    """构建 {code: profit_rate} 映射用于个股级校验。

    每个品种的盈亏比例来自持仓明细中的 profit_rate 字段，
    用于在 LLM 提及个股收益时进行精准比对，而非一律回退到组合总收益。
    """
    result: dict[str, float] = {}
    for d in holdings_details or []:
        code = d.get('code', '') or ''
        rate = d.get('profit_rate')
        if code and rate is not None:
            result[code] = float(rate)
    return result


def _is_contribution_sentence(sentence: str) -> bool:
    """判断是否为收益归因句，其数值为贡献度占比而非收益率。"""
    return any(kw in sentence for kw in _CONTRIBUTION_KEYWORDS)


# ── 检查器 1：数值一致性（v2 — 感知增强）───────────────────────


def check_numerical_consistency(
    text: str,
    holdings_details: list[dict] | None,
) -> tuple[list[str], int, int]:
    """检查 LLM 输出中的百分比数值与实际组合/个股数据是否一致。

    v2 改进：
    - 按句子粒度分析，准确识别收益归因段落并跳过
    - 优先匹配句中持仓代码对应的个股收益率
    - 未识别到个股时回退到组合总收益率
    - 指数基准代码数值自动跳过
    - 贡献度/归因段落数值跳过（不可直接比较）

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。

    Returns:
        (issues, total_checked, passed_count)
    """
    issues: list[str] = []
    if not text:
        return issues, 0, 0

    values = _calc_portfolio_values(holdings_details)
    profit_rate = abs(values["total_profit_rate"])
    profit_sign = "盈利" if values["total_profit"] >= 0 else "亏损"

    # 构建个股收益率映射
    stock_rates = _build_stock_rate_map(holdings_details)
    # 持仓代码集合（用于判断句中代码是否为持仓品种）
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

            # 数值上下文必须有收益相关关键词才进入校验
            is_profit_context = any(kw in sentence for kw in _PROFIT_KEYWORDS)
            if not is_profit_context or profit_rate < 0.01:
                passed += 1
                continue

            total_checked += 1

            # 构建参考收益率列表：个股收益率 + 组合总收益率
            # 对每个数值，找最接近的参考值进行匹配
            stock_rates_abs = {code: abs(r) for code, r in stock_rates.items()}
            ref_rates: dict[str, float] = dict(stock_rates_abs)
            ref_rates["_portfolio"] = profit_rate

            # 找最接近的参考值
            closest_ref = min(ref_rates, key=lambda k: abs(value - ref_rates[k]))
            closest_diff = abs(value - ref_rates[closest_ref])

            # 策略 1：最接近的参考值在容差内 → 通过
            if closest_diff <= _DEFAULT_TOLERANCE_PCT:
                passed += 1
                continue

            # 策略 2：句中代码全部为指数代码 → 跳过（基准数值不来自持仓）
            codes_in_sentence = _CODE_PATTERN.findall(sentence)
            index_codes_in_sentence = [c for c in codes_in_sentence if c in _INDEX_CODES]
            holding_codes_in_sentence = [c for c in codes_in_sentence if c in holding_codes]
            if not holding_codes_in_sentence and index_codes_in_sentence:
                passed += 1
                continue

            # 策略 3：句中含贡献类关键词 → 跳过不可验证
            if any(kw in sentence for kw in ('贡献', '贡献度', '归因', '主要来源')):
                passed += 1
                continue

            # 策略 4：句中含金融基准类关键词（利率/通胀/国债等外部指标）→ 跳过
            if any(kw in sentence for kw in ('国债', '利率', '通胀', 'GDP', 'CPI', 'PMI')):
                passed += 1
                continue

            # 全部策略均未通过 → 标记为不一致
            # 优先使用句中持仓代码生成消息（更准确），否则使用最近参考值
            if holding_codes_in_sentence:
                code = holding_codes_in_sentence[0]
                stock_rate = stock_rates_abs.get(code, 0)
                issues.append(
                    f"收益相关数值 {value}% 与 {code} 的实际收益率 {stock_rate:.1f}%（{profit_sign}）偏差超过容差"
                )
            elif closest_ref != "_portfolio":
                stock_rate = stock_rates_abs.get(closest_ref, 0)
                issues.append(
                    f"收益相关数值 {value}% 与 {closest_ref} 的实际收益率 {stock_rate:.1f}%（{profit_sign}）偏差超过容差"
                )
            else:
                issues.append(
                    f"收益相关数值 {value}% 与实际累计收益率 {profit_rate:.1f}%（{profit_sign}）偏差超过容差"
                )

    return issues, total_checked, passed


# ── 检查器 2：品种存在性 ────────────────────────────────────


def check_symbol_existence(
    text: str,
    holdings_details: list[dict] | None,
    extra_valid_codes: set[str] | None = None,
) -> tuple[list[str], int, int]:
    """检查 LLM 输出的品种代码是否确实存在于持仓中。

    跳过常见指数代码（如沪深300:000300），仅校验疑似持仓代码。
    支持传入 extra_valid_codes 扩展有效代码集（如穿透分析的股票代码）。

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。
        extra_valid_codes: 额外有效代码集合（如穿透 TOP10 中的股票代码）。

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

    # 合并额外有效代码
    extra_codes = extra_valid_codes or set()
    all_valid = set(valid_codes.keys()) | _INDEX_CODES | extra_codes

    for code in codes_found:
        if code in all_valid:
            passed += 1
        else:
            issues.append(f"品种代码 {code} 不在当前持仓中")

    return issues, total_checked, passed


# ── 检查器 3：排名正确性 ──────────────────────────────────────


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
    extra_valid_codes: set[str] | None = None,
    is_penetration_module: bool = False,
) -> str:
    """对 LLM 生成的 HTML 内容执行全量事实校验。

    依次执行数值一致性、品种存在性、排名正确性三项检查，
    返回可追加到 HTML 底部的校验摘要。

    v2 新增参数：
        extra_valid_codes: 额外有效代码集合（穿透分析用）。
        is_penetration_module: 是否为穿透分析模块（排名使用穿透排序而非直接持仓）。

    Args:
        html_content: LLM 生成的 HTML 内容。
        holdings_details: 持仓明细数据（用于品种存在性和排名校验）。
        module_label: 模块中文名，用于摘要标签（如"全球政经局势"）。
        extra_valid_codes: 额外有效代码集合（穿透分析用）。
        is_penetration_module: 是否为穿透分析模块。

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

    # 检查 2：品种存在性（支持穿透分析的额外有效代码）
    sym_issues, sym_checked, sym_passed = check_symbol_existence(text, holdings_details, extra_valid_codes)
    all_issues.extend(sym_issues)
    total_checks += sym_checked
    total_passed += sym_passed

    # 检查 3：排名正确性（穿透分析模块使用穿透排名基线）
    rank_issues, rank_checked, rank_passed = check_ranking_correctness(text, holdings_details, is_penetration_module)
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

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
# 使用 re.ASCII 确保 \b 在中文和非 ASCII 字符旁也正常匹配边界
_CODE_PATTERN = re.compile(r"\b[0-9]{6}\b", re.ASCII)

# 排名声称模式 — "最大持仓"/"第一大重仓"/"前三大持仓" 等持仓排名声称。
# 要求排名词与持仓名词紧邻（允许中间一个"的"），避免将
# "最大单项亏损品种"/"主要利润贡献"/"最大亏损来源"/"最大特点" 等
# 非持仓排名语境误判为排名声称。
# "第X大/前X大/头X大" 的"大"可省略（如"第一重仓"），但须与持仓名词紧邻。
_RANK_MAX_PATTERN = re.compile(
    r"(?:第[一二三四五六七八九十\d]+大?|最大|最重|首要|主要|"
    r"前[一二三四五六七八九十\d]+大?|头[一二三四五六七八九十\d]+大?)"
    r"(?:的)?(?:持仓|重仓|仓位|持股|权重)"
)
_RANK_TOP_N_PATTERN = re.compile(r"(?:前[一二三四五六七八九十\d]+|头[一二三四五六七八九十\d]+)")

# 百分比数值
_PERCENT_PATTERN = re.compile(r"(\d+\.?\d*)\s*%")

# 收益/回报相关关键词（用于数值上下文判断）
_PROFIT_KEYWORDS = frozenset(
    [
        "收益",
        "盈利",
        "回报",
        "涨幅",
        "利润",
        "收益率",
        "回报率",
        "累计",
        "浮盈",
        "浮亏",
        "亏损",
        "增长",
        "下跌",
        "上涨",
    ]
)

# 收益归因段落特征词（数值为贡献度占比，不可与收益率直接比较）
_CONTRIBUTION_KEYWORDS = frozenset(
    [
        "盈利来源",
        "亏损来源",
        "收益归因",
        "贡献占比",
        "盈利贡献",
        "贡献度",
        "归因于",
    ]
)

# 仓位/占比上下文——数值为权重而非收益率
_POSITION_WEIGHT_KEYWORDS = frozenset(
    [
        "占比",
        "仓位",
        "集中度",
    ]
)

# 品种计数/比例上下文——数值为品种计数比例而非收益率（如"80%的品种处于盈利"）
_PROPORTION_KEYWORDS: tuple[str, ...] = (
    "的品种",
    "的持仓",
    "的标的",
    "的资产",
)

# 回撤上下文——数值为回撤幅度而非个股/组合收益率
_DRAWDOWN_KEYWORDS = frozenset(
    [
        "回撤",
        "最大回撤",
        "回撤率",
        "回撤幅度",
        "回落",
        "自高点",
        "从高点",
        "历史最大",
    ]
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


def _sentence_snippet(sentence: str, max_len: int = 50) -> str:
    """截取句子前 max_len 字作为上下文摘要。"""
    s = sentence.replace(" ", "").strip()
    return s[:max_len] + "…" if len(s) > max_len else s


# 调仓目标上下文——数值为目标而非实际收益率
_REBALANCE_TARGET_KEYWORDS = frozenset(
    [
        "降至",
        "升至",
        "调至",
        "减仓至",
        "加仓至",
    ]
)

# 假设/情景上下文——数值为假设场景而非实际收益率
_HYPOTHETICAL_KEYWORDS = frozenset(
    [
        "如果",
        "假设",
        "若",
        "情景",
        "假如",
    ]
)

# 币种/敞口上下文
_EXPOSURE_KEYWORDS = frozenset(
    [
        "币种",
        "敞口",
        "人民币",
        "美元",
        "港币",
        "港元",
    ]
)

# 建议语境关键词 — 品种代码属于投资建议而非声称持有
# 注意：避免"关注"（会匹配"值得关注"）、"参考"（会匹配"参考品种"）等宽泛词
_SUGGESTION_KEYWORDS: tuple[str, ...] = (
    "建议",
    "可考虑",
    "推荐",
    "买入",
    "可以考虑",
    "适合",
    "可买入",
    "建议关注",
    "可关注",
    "值得配置",
)

# 常见指数代码（校验品种存在性时跳过）
_INDEX_CODES: frozenset[str] = frozenset(
    {
        "000300",  # 沪深300
        "000001",  # 上证指数
        "399001",  # 深证成指
        "399006",  # 创业板指
        "000688",  # 科创50
        "000016",  # 上证50
        "000905",  # 中证500
        "399300",  # 沪深300（深圳）
    }
)

# 默认容差（百分点）
_DEFAULT_TOLERANCE_PCT = 1.0


def _strip_html(html: str) -> str:
    """去除 HTML 标签，返回纯文本。"""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_sentences(text: str) -> list[str]:
    """按中英文句号、感叹号、问号、换行拆分句子。"""
    sentences = re.split(r"[。！？\n!?]", text)
    return [s.strip() for s in sentences if s.strip()]


def _extract_holding_map(holdings_details: list[dict] | None) -> dict[str, str]:
    """从持仓明细构建 {code: name} 映射。"""
    result: dict[str, str] = {}
    for d in holdings_details or []:
        code = d.get("code", "") or ""
        name = d.get("name", "") or ""
        if code:
            result[code] = name
    return result


def _calc_portfolio_values(holdings_details: list[dict] | None) -> dict[str, float]:
    """计算组合核心数值。

    Returns:
        {"total_mv": float, "total_cost": float, "total_profit": float, "total_profit_rate": float}
    """
    total_mv = sum(d.get("market_value", 0) or 0 for d in holdings_details or [])
    total_cost = sum(d.get("cost", 0) or 0 for d in holdings_details or [])
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
        code = d.get("code", "") or ""
        rate = d.get("profit_rate")
        if code and rate is not None:
            result[code] = float(rate)
    return result


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


# ── 检查器 1：数值一致性（v3 — 带语境感知）───────────────────────


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

    Returns:
        (issue_str_or_None, correction_or_None)
        correction = (wrong_value_str, correct_value_str, context_sentence)
    """
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
            )
            if issue is None:
                passed += 1
            else:
                issues.append(issue)
                if correction:
                    corrections.append(correction)

    return issues, total_checked, passed, corrections


# ── 检查器 2：品种存在性 ────────────────────────────────────


def check_symbol_existence(
    text: str,
    holdings_details: list[dict] | None,
    extra_valid_codes: set[str] | None = None,
    suggestion_keywords: tuple[str, ...] | None = _SUGGESTION_KEYWORDS,
) -> tuple[list[str], int, int, list[str]]:
    """检查 LLM 输出的品种代码是否确实存在于持仓中。

    跳过常见指数代码（如沪深300:000300），仅校验疑似持仓代码。
    支持传入 extra_valid_codes 扩展有效代码集（如穿透分析的股票代码）。

    返回 4 元组，第 4 项是建议语境提及的列表（不计入幻觉率）。
    建议提及是指 LLM 在建议/推荐语境中引用非持仓代码（如"建议关注511010"），
    而非声称持有该品种。

    Args:
        text: 去 HTML 标签后的纯文本。
        holdings_details: 持仓明细列表。
        extra_valid_codes: 额外有效代码集合（如穿透 TOP10 中的股票代码）。
        suggestion_keywords: 建议语境关键词元组，设为 None 可关闭此检测。

    Returns:
        (issues, total_checked, passed_count, suggestion_issues)
        — suggestion_issues 是 issues 的子集，已从 issues 中移除，
          不计入幻觉率。
    """
    issues: list[str] = []
    suggestions: list[str] = []
    if not text or not holdings_details:
        return issues, 0, 0, suggestions

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
            # 判断是否建议语境（如"建议关注511010"）
            if suggestion_keywords is not None and _is_suggestion_context(code, text):
                suggestions.append(f"品种代码 {code} 不在当前持仓中（建议提及）")
            else:
                issues.append(f"品种代码 {code} 不在当前持仓中")

    return issues, total_checked, passed, suggestions


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
            actual_name = actual_top.get("name", "") or ""
            actual_code = actual_top.get("code", "") or ""
            issues.append(f"声称 {mentioned_code} 为最大持仓，但实际最大持仓为 {actual_code}（{actual_name}）")
        else:
            passed += 1

    return issues, total_checked, passed


# ── 数值自动修正 ──────────────────────────────────────────────


def apply_numerical_corrections(
    html: str,
    corrections: list[tuple[str, str, str]],
) -> str:
    """对 HTML 内容中的错误百分比数值执行自动替换。

    使用 sentence 上下文确认匹配位置，避免误替换 HTML 属性中的数值。
    按 wrong_value 长度降序替换（避免 "3.7" 先于 "3.79" 被替换）。

    Args:
        html: 原始 HTML 内容。
        corrections: [(wrong_value_str, correct_value_str, context_sentence), ...]。

    Returns:
        修正后的 HTML 内容。
    """
    if not corrections:
        return html

    # 按 wrong_value 降序排列，避免部分匹配问题
    sorted_cx = sorted(corrections, key=lambda c: -len(c[0]))
    stripped = _strip_html(html)

    result = html
    for wrong_val, correct_val, sentence in sorted_cx:
        if sentence not in stripped:
            continue

        # 在 HTML 文本中查找 wrong_val%（带可选空格）
        # lookbehind 确保不会替换数字的一部分
        pattern = re.compile(r"(?<!\d)" + re.escape(wrong_val) + r"\s*%")
        result = pattern.sub(correct_val + "%", result)

    return result


# ── 统一入口 ──────────────────────────────────────────────────


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
        rank_issues, rank_checked, rank_passed = check_ranking_correctness(text, holdings_details, is_penetration_module)
    all_issues.extend(rank_issues)
    total_checks += rank_checked
    total_passed += rank_passed

    # ── 自动修正 ──
    corrected_html = html_content
    if auto_correct and all_corrections:
        corrected_html = apply_numerical_corrections(html_content, all_corrections)

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
        return corrected_html, result

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
    return corrected_html, f'<p style="color:#a40;font-size:12px">{summary}</p>{suggestion_lines}'

"""LLM 输出虚构代码过滤模块。

提取自 ``llm/generators.py``，用于辩论模式等场景中过滤 LLM 生成的
虚构品种代码（A 股 6 位数字代码/港股美股字母数字代码）。

同时保留已知安全的英文词汇（白名单），避免误伤正常金融术语和 HTML/CSS 标签。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("invest")

# ── 已知安全英文词白名单 ──────────────────────────────

# 不应被当作虚构股票代码（大小写不敏感）
# 出现场景：LLM 在分析报告中插入 HTML/CSS 标签、金融术语、英文词汇
_HALLU_SAFE_WORDS: set[str] = {
    # 已报告误杀（HTML/CSS 标签、英文词汇）
    "style",
    "flash",
    "strong",
    "font",
    "size",
    "color",
    "token",
    "qdii",
    "12px",
    "100etf",
    # HTML/CSS 常见属性
    "width",
    "height",
    "align",
    "border",
    "margin",
    "padding",
    "inline",
    "solid",
    "dashed",
    "dotted",
    "double",
    "groove",
    "ridge",
    "inset",
    "outset",
    "hidden",
    "visible",
    "scroll",
    # 金融/经济分析高频词汇
    "value",
    "price",
    "yield",
    "total",
    "index",
    "month",
    "year",
    "daily",
    "weekly",
    "growth",
    "level",
    "range",
    "trend",
    "large",
    "small",
    "short",
    "long",
    "cover",
    "limit",
    "order",
    "trade",
    "share",
    "stock",
    "bond",
    "fund",
    "cash",
    "risk",
    "rate",
    "asset",
    "debt",
    "equity",
    "fixed",
    "float",
    "clear",
    "cycle",
    "light",
    "dark",
    "block",
    "track",
    "focus",
    "upper",
    "lower",
    "major",
    "minor",
    "prime",
    "core",
    "delta",
    "gamma",
    "theta",
    "alpha",
    "beta",
    "sigma",
    "rally",
    "crash",
    "bulls",
    "bears",
    "spike",
    "split",
    # 报告写作常见词
    "title",
    "table",
    "label",
    "point",
    "issue",
    "topic",
    "chart",
    "graph",
    "phase",
    "stage",
    "state",
    "event",
    "cause",
    "effect",
    "basis",
    "shift",
    "swing",
}


def _is_safe_word(code: str) -> bool:
    """判断一个由正则捕获的字母数字组合是否为安全英文词汇而非虚构代码。

    两条规则满足其一即安全：
      1. **全小写字母**：实盘交易所代码不会全小写，低风险豁免。
      2. **白名单命中**：大小写不敏感匹配 ``_HALLU_SAFE_WORDS``。

    Args:
        code: 正则捕获的 4-6 位字母数字串。

    Returns:
        该词为安全英文词汇时返回 True，否则返回 False。
    """
    # 全小写字母 → 绝非实盘代码
    if code.islower():
        return True
    # 大小写不敏感匹配白名单
    return code.lower() in _HALLU_SAFE_WORDS


def _filter_hallucinated_codes(
    text: str,
    valid_codes: set[str],
) -> str:
    """从 LLM 输出中过滤虚构代码。

    正则提取所有 6 位数字代码（A 股）及字母数字代码（港股/美股），
    与 valid_codes 交叉校验，移除虚构代码及其所在整句。

    Args:
        text: LLM 原始输出文本。
        valid_codes: 合法持仓代码集合。

    Returns:
        过滤后的文本（无虚构代码的句子），如全部移除则返回空字符串。
    """
    if not text:
        return text

    # 使用左边界(^|[^A-Za-z0-9])和右边界([^A-Za-z0-9]|$)替代\b
    # 避免中文环境下\b失效（Python re 视中文字符为\w）
    found_codes = set(re.findall(r"(?:^|[^A-Za-z0-9])([A-Za-z0-9]{4,6})(?=[^A-Za-z0-9]|$)", text))
    invalid = {c for c in found_codes if c not in valid_codes and not c.isdigit() and not _is_safe_word(c)}

    if not invalid:
        return text

    logger.warning("[debate-hallu] 检测到 %d 个虚构品种代码: %s", len(invalid), invalid)
    lines = text.split("\n")
    filtered = []
    removed_count = 0
    for line in lines:
        line_codes = set(re.findall(r"(?:^|[^A-Za-z0-9])([A-Za-z0-9]{4,6})(?=[^A-Za-z0-9]|$)", line))
        if line_codes & invalid:
            removed_count += 1
            continue
        filtered.append(line)

    logger.info(
        "[debate-hallu] 过滤前 %d 字符，过滤后 %d 字符，移除了 %d 个虚构品种所在行",
        len(text),
        len("\n".join(filtered)),
        removed_count,
    )
    return "\n".join(filtered)

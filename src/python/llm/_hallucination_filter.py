"""LLM 输出虚构代码过滤模块。

用于辩论模式等场景中过滤 LLM 生成的
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
    "smart",
    "money",
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

    满足任一规则即安全：
      1. **全小写字母**：实盘交易所代码不会全小写，低风险豁免。
      2. **TOP 排名表述**：``TOP\\d+``（如 TOP2/TOP3）——提示词附录
         ``【持仓TOP3】`` 块的回声表述，绝非实盘代码形态。
      3. **白名单命中**：大小写不敏感匹配 ``_HALLU_SAFE_WORDS``。

    Args:
        code: 正则捕获的 4-6 位字母数字串。

    Returns:
        该词为安全英文词汇时返回 True，否则返回 False。
    """
    # 全小写字母 → 绝非实盘代码
    if code.islower():
        return True
    # TOP 后跟数字 → 排名表述（如 TOP2/TOP3），非代码形态
    if re.fullmatch(r"TOP\d+", code, re.IGNORECASE):
        return True
    # 大小写不敏感匹配白名单
    return code.lower() in _HALLU_SAFE_WORDS


_CODE_PATTERN = r"(?:^|[^A-Za-z0-9])([A-Za-z0-9]{4,6})(?=[^A-Za-z0-9]|$)"
"""虚构代码提取正则（与过滤逻辑共用）。

使用左边界(^|[^A-Za-z0-9])和右边界([^A-Za-z0-9]|$)替代\\b，
避免中文环境下\\b失效（Python re 视中文字符为\\w）。
"""

_INLINE_SENTENCE_RE = re.compile(r"(?<=[。！？；])")
"""行内句末标点正则（。！？；），用于行内按句段切分。

过滤按"句段"而非"行"为单位删除——markdown_to_html 输出的 HTML
为无换行的单行拼接字符串，仅按行删除会把整段内容误删。
先按行切分（保留多行结构），行内再按句末标点切分（单行可精确删除）。
"""


def _filter_hallucinated_codes(
    text: str,
    valid_codes: set[str],
) -> str:
    """从 LLM 输出中过滤虚构代码。

    正则提取所有 6 位数字代码（A 股）及字母数字代码（港股/美股），
    与 valid_codes 交叉校验，按句段（换行/句末标点切分）移除含虚构
    代码的句段，保留其余内容。

    设计考量：
      - 应在 LLM 原始 Markdown 文本上调用（带换行，句段粒度自然）；
        骨架层 ``raw_filter_fn`` 钩子在 markdown_to_html 之前注入。
      - 即便误用于 HTML 单行字符串，句段级删除也不会再整段丢失。

    Args:
        text: LLM 原始输出文本。
        valid_codes: 合法持仓代码集合。

    Returns:
        过滤后的文本（无虚构代码的句段），如全部移除则返回空字符串。
    """
    if not text:
        return text

    found_codes = set(re.findall(_CODE_PATTERN, text))
    invalid = {c for c in found_codes if c not in valid_codes and not c.isdigit() and not _is_safe_word(c)}

    if not invalid:
        return text

    logger.warning("[debate-hallu] 检测到 %d 个虚构品种代码: %s", len(invalid), invalid)
    filtered_lines = []
    removed_count = 0
    for line in text.split("\n"):
        kept = []
        for segment in _INLINE_SENTENCE_RE.split(line):
            segment_codes = set(re.findall(_CODE_PATTERN, segment))
            if segment_codes & invalid:
                removed_count += 1
                continue
            kept.append(segment)
        if any(s.strip() for s in kept):
            # 行内仍有非空句段 → 保留过滤后的行（行内部分删除）
            filtered_lines.append("".join(kept))
        elif not line.strip():
            # 原空行（段落分隔）→ 无虚构代码，原样保留
            filtered_lines.append(line)
        # 否则：整行句段全部被移除 → 丢弃该行（连带其换行）

    result = "\n".join(filtered_lines)
    logger.info(
        "[debate-hallu] 过滤前 %d 字符，过滤后 %d 字符，移除了 %d 个虚构品种所在句段",
        len(text),
        len(result),
        removed_count,
    )
    return result

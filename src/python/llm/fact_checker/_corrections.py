"""fact_checker 子包 — 数值自动修正。

对 LLM 生成的 HTML 中错误百分比数值执行自动替换。
"""

from __future__ import annotations

import re

from src.python.llm.fact_checker._utils import _strip_html


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

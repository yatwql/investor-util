"""JSON 注释剥离 — 用于 llm_settings.json / llm_key.json。"""
from __future__ import annotations


def _strip_json_comments(text: str) -> str:
    """剥离 JSON 中的 ``//`` 单行注释和 ``/* */`` 多行注释。

    正确处理字符串中的转义引号，不会将字符串内的 ``//`` / ``/*`` 误伤。

    Args:
        text: 可能包含注释的 JSON 文本

    Returns:
        不含注释的纯 JSON 文本
    """
    # 逐个字符扫描，仅在字符串外识别注释
    result: list[str] = []
    i = 0
    length = len(text)
    in_string = False
    in_single_line_comment = False
    in_multi_line_comment = False

    while i < length:
        ch = text[i]

        # ── 字符串内：只处理转义引号 ────────────────────────
        if in_string:
            result.append(ch)
            if ch == '\\':
                i += 1
                if i < length:
                    result.append(text[i])
            elif ch == '"':
                in_string = False
            i += 1
            continue

        # ── 多行注释内 ──────────────────────────────────────
        if in_multi_line_comment:
            if ch == '*' and i + 1 < length and text[i + 1] == '/':
                i += 2  # 跳过 */
                in_multi_line_comment = False
            else:
                i += 1
            continue

        # ── 单行注释内 ──────────────────────────────────────
        if in_single_line_comment:
            if ch == '\n':
                in_single_line_comment = False
                result.append(ch)
            i += 1
            continue

        # ── 注释起始检测（仅在字符串外） ─────────────────────
        if ch == '/' and i + 1 < length:
            nxt = text[i + 1]
            if nxt == '/':
                in_single_line_comment = True
                i += 2
                continue
            if nxt == '*':
                in_multi_line_comment = True
                i += 2
                continue

        # ── 字符串起始 ────────────────────────────────────
        if ch == '"':
            in_string = True

        result.append(ch)
        i += 1

    return "".join(result)

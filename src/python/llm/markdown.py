"""LLM Markdown → HTML 转换模块。"""

from __future__ import annotations

import re

__all__ = ["_markdown_to_html"]


def _markdown_to_html(text: str) -> str:
    """将 Markdown 文本转换为基础 HTML，供 HTML 报告模板渲染。

    支持：标题（## / ###）、粗体、斜体、行内代码、
    无序列表（-）、有序列表（1.）、水平分割线（---）、段落。

    Args:
        text: 含 Markdown 标记的纯文本

    Returns:
        HTML 片段，不含 <html>/<body> 包裹
    """
    if not text:
        return ""

    # 预处理：统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    parts: list[str] = []
    in_ul = False
    in_ol = False

    def _close_list() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        if in_ol:
            parts.append("</ol>")
            in_ol = False

    def _inline(text: str) -> str:
        """处理行内 Markdown 标记。"""
        # 粗体 **text**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # 斜体 *text*（避免误伤粗体已处理过的）
        text = re.sub(r"(?<!\*)\*(?![*])(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        # 行内代码 `code`
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            _close_list()
            continue

        # 标题（必须行首）
        h_match = re.match(r"^#{2,3}\s+(.+)$", line)
        if h_match:
            _close_list()
            level = min(6, line.split(" ")[0].count("#"))
            tag = f"h{level}"  # ## → h2, ### → h3
            parts.append(f"<{tag}>{_inline(h_match.group(1))}</{tag}>")
            continue

        # 水平分割线
        if re.match(r"^-{3,}$|^_{3,}$|^\*{3,}$", line):
            _close_list()
            parts.append("<hr>")
            continue

        # 无序列表
        ul_match = re.match(r"^[-*+]\s+(.+)$", line)
        if ul_match:
            if not in_ul:
                _close_list()
                parts.append("<ul>")
                in_ul = True
            elif in_ol:
                _close_list()
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{_inline(ul_match.group(1))}</li>")
            continue

        # 有序列表
        ol_match = re.match(r"^\d+[.)]\s+(.+)$", line)
        if ol_match:
            if not in_ol:
                _close_list()
                parts.append("<ol>")
                in_ol = True
            elif in_ul:
                _close_list()
                parts.append("<ol>")
                in_ol = True
            parts.append(f"<li>{_inline(ol_match.group(1))}</li>")
            continue

        # 普通段落
        _close_list()
        parts.append(f"<p>{_inline(line)}</p>")

    _close_list()
    return "".join(parts)

"""LLM Markdown → HTML 转换模块。"""

from __future__ import annotations

import re

__all__ = ["markdown_to_html"]


def _md_close_list(
    parts: list[str],
    in_ul: bool | None = None,
    in_ol: bool | None = None,
) -> tuple[bool, bool]:
    """关闭当前打开的列表标签，返回 (in_ul, in_ol)。"""
    if in_ul:
        parts.append("</ul>")
        in_ul = False
    if in_ol:
        parts.append("</ol>")
        in_ol = False
    return bool(in_ul), bool(in_ol)


def _md_inline(text: str) -> str:
    """处理行内 Markdown 标记：粗体、斜体、行内代码。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?![*])(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def markdown_to_html(text: str) -> str:
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

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            in_ul, in_ol = _md_close_list(parts, in_ul, in_ol)
            continue

        # 标题（必须行首）
        h_match = re.match(r"^#{2,3}\s+(.+)$", line)
        if h_match:
            in_ul, in_ol = _md_close_list(parts, in_ul, in_ol)
            level = min(6, line.split(" ")[0].count("#"))
            tag = f"h{level}"  # ## → h2, ### → h3
            parts.append(f"<{tag}>{_md_inline(h_match.group(1))}</{tag}>")
            continue

        # 水平分割线
        if re.match(r"^-{3,}$|^_{3,}$|^\*{3,}$", line):
            in_ul, in_ol = _md_close_list(parts, in_ul, in_ol)
            parts.append("<hr>")
            continue

        # 无序列表
        ul_match = re.match(r"^[-*+]\s+(.+)$", line)
        if ul_match:
            if not in_ul or in_ol:
                in_ul, in_ol = _md_close_list(parts, in_ul, in_ol)
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{_md_inline(ul_match.group(1))}</li>")
            continue

        # 有序列表
        ol_match = re.match(r"^\d+[.)]\s+(.+)$", line)
        if ol_match:
            if not in_ol or in_ul:
                in_ul, in_ol = _md_close_list(parts, in_ul, in_ol)
                parts.append("<ol>")
                in_ol = True
            parts.append(f"<li>{_md_inline(ol_match.group(1))}</li>")
            continue

        # 普通段落
        in_ul, in_ol = _md_close_list(parts, in_ul, in_ol)
        parts.append(f"<p>{_md_inline(line)}</p>")

    in_ul, in_ol = _md_close_list(parts, in_ul, in_ol)
    return "".join(parts)

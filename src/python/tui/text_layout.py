"""终端文本宽度与盒线面板排版助手。

中文/全角字符在等宽终端占 2 列，而 `len()` 按码点计数只算 1——面板行若用
`' ' * N` 手写补白，含中文的行就会比含英文的行短，盒线右边框参差不齐；行与行
之间还各自写着不同的补白数（上下边框、分隔线、内容行三者口径不一），同一面板
的右边框因此对不到同一列。本模块按东亚宽度计算显示列数，并由 `render_panel`
按整块面板的最长行统一定宽，调用方不必预估列宽，也不会因某行超宽而撑破右边框。

ANSI 颜色序列不占显示列：`GREEN`/`RESET` 等常量在非 TTY 下为空串，但着色开启
时若不先剥离，会把转义字符按可见字符多算，故 `display_width` 先剔除。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_ANSI_SEQ = re.compile(r"\x1b\[[0-9;]*m")

# 东亚宽度 W(ide)/F(ullwidth) 的字符占 2 列；A(mbiguous)（含盒线字符）与其余按 1 列计
_WIDE = ("W", "F")

# 内容行可用列数的下限——面板至少这么宽，窄面板不至于缩成一条
MIN_FIELD_WIDTH = 41

# 标题与边框之间的固定装饰：`┌── ` + 标题 + ` `，即标题占 4 列外框
_TITLE_DECOR = 4


def display_width(text: str) -> int:
    """返回文本在等宽终端占用的列数。

    先剥离 ANSI 颜色序列；组合字符（重音符号等）不占列；东亚宽字符计 2 列。
    """
    width = 0
    for char in _ANSI_SEQ.sub("", text):
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in _WIDE else 1
    return width


def pad_right(text: str, columns: int) -> str:
    """右补空格至指定显示列数，用于对齐表格列；已超宽则原样返回（不截断）。"""
    return text + " " * max(0, columns - display_width(text))


def render_panel(title: str, rows: Iterable[str | None] = (), *, min_field: int = MIN_FIELD_WIDTH) -> list[str]:
    """渲染一个盒线面板，返回待逐行打印的文本。

    Args:
        title: 面板标题（渲染为上边框 `┌── 标题 ──…─┐`）
        rows: 内容行；`None` 渲染为一条内区分隔线，`""` 渲染为空白行
        min_field: 内容可用列数的下限

    内区宽度取「标题所需」与「最长内容行」的较大者，四边因此对齐到同一列。
    """
    body = list(rows)
    field = max(
        [min_field, display_width(title) + _TITLE_DECOR - 1] + [display_width(row) for row in body if row is not None]
    )
    lines = [f"  ┌── {title} {'─' * (field - display_width(title) - _TITLE_DECOR + 1)}┐"]
    for row in body:
        if row is None:
            lines.append(f"  │{'─' * (field + 1)}│")
        else:
            lines.append(f"  │ {row}{' ' * (field - display_width(row))}│")
    lines.append(f"  └{'─' * (field + 1)}┘")
    return lines

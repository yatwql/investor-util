"""财报正文关键词定位 — 纯文本处理（全文兜底与备源章节切片共用）。

关键词命中常先落在**目录行**（「董事会报告 ……」），直接切片会把目录当正文摘要；
本模块提供「跳过目录行」的关键词定位判定，供全文兜底
（``fetcher/financial_report.py``）与巨潮备源的正文切片
（``fetcher/report_adapters.py`` 的 cninfo 适配器）共用同一规则——
两处不得各自实现目录行判定而漂移。
"""

from __future__ import annotations

#: 判定「目录行」的探测窗口（字符）：只看关键词到行尾这一行
_TOC_PROBE_CHARS = 90


def is_toc_line(content: str, pos: int) -> bool:
    """该位置是否是目录行（**同一行内**出现点线引导/省略号）。

    只看关键词到行尾这一行：正文段落里出现省略号（「利润及股息分配……」）不应被误判为目录。
    """
    line_end = content.find("\n", pos)
    line = content[pos : line_end if line_end >= 0 else pos + _TOC_PROBE_CHARS][:_TOC_PROBE_CHARS]
    return ("...." in line) or ("…" in line) or (".." in line)


def locate_keyword_excerpt(content: str, preferences: list[str], max_chars: int) -> tuple[str, str]:
    """按偏好关键词定位片段：跳过目录行，取首个正文命中的位置起 ``max_chars`` 字。

    Args:
        content: 正文全文（已去空白变体由调用方保证）。
        preferences: 偏好关键词列表（按顺序尝试，逐项 strip，空项跳过）。
        max_chars: 片段上限（调用方截断，防超长正文撑爆记录）。

    Returns:
        ``(片段, 命中的偏好关键词)``；无命中返回 ``("", "")``。
    """
    for pref in preferences:
        key = str(pref).strip()
        if not key:
            continue
        pos = content.find(key)
        while pos >= 0 and is_toc_line(content, pos):
            pos = content.find(key, pos + 1)  # 跳过目录行，找正文里那一次
        if pos >= 0:
            return content[pos : pos + max_chars], key
    return "", ""

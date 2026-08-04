"""JSON 文本编辑 — 带注释 JSON 的字段级替换与顶层键扫描/patch 引擎。

用于支持 ``//`` 注释的 JSON 文件（config.json / llm_settings.json / llm_key.json /
llm_providers.json）：写入时保留原文件注释与空白，仅替换发生变化的字段。
字段级替换自 tui/handlers_config.py 提取，顶层键扫描引擎自 config/_core.py 迁入。

对外提供：
  _update_json_raw_text(raw, current, new) — 字段级文本替换（llm_settings 用）
  _replace_dict_block(text, key, new_val)  — dict 值区块 brace 平衡替换
  _skip_ws_and_comments / _find_top_level_value_span / _find_value_end
  _find_top_level_close_brace              — 注释感知的顶层键扫描基元
  _patch_config_key(raw, key, new_value)   — 顶层键替换或追加（config.json 用）
  _remove_top_level_key(raw, key, vs, ve)  — 顶层键条目删除（config.json 用）
"""

from __future__ import annotations

import json
import re


def _update_json_raw_text(raw: str, current: dict, new: dict) -> str:
    """在原始 JSON 文本中做精确的字段级替换，保留注释和空白。

    对 dict 类型值使用 brace 平衡算法 + 自适应缩进替换，
    对简单值（str/int/bool/None）使用正则替换。

    Args:
        raw: 原始 JSON 文本（含注释）
        current: 当前解析后的值
        new: 要写入的新值

    Returns:
        经字段级替换后的新文本
    """
    result = raw
    for key, new_val in new.items():
        old_val = current.get(key)
        if old_val == new_val:
            continue

        if isinstance(old_val, dict):
            result = _replace_dict_block(result, key, new_val)
        else:
            old_json = json.dumps(old_val, ensure_ascii=False, indent=2) if old_val is not None else "null"
            new_json = json.dumps(new_val, ensure_ascii=False, indent=2) if new_val is not None else "null"
            result = re.sub(
                re.escape(f'"{key}":') + r"\s*" + re.escape(old_json),
                f'"{key}": {new_json}',
                result,
                count=1,
            )
    return result


def _replace_dict_block(text: str, key: str, new_val: dict) -> str:
    """在 JSON 文本中找到指定 key 的 dict 值区块，自适应缩进替换。

    使用 brace 平衡算法确保正确匹配嵌套大括号，自动检测周围缩进层级，
    使替换后的 JSON 与文件缩进风格一致。
    """
    match = re.search(re.escape(f'"{key}":') + r"\s*\{", text)
    if not match:
        return text

    # 检测 key 所在的当前行缩进
    line_start = text.rfind("\n", 0, match.start()) + 1
    base_indent = match.start() - line_start  # ""{key}"" 前的空格数

    # 序列化新值，使用 4 空格内缩
    INNER_INDENT = 4
    lines = json.dumps(new_val, ensure_ascii=False, indent=INNER_INDENT).split("\n")

    # 第一行是 "{"，续行加 base_indent 前缀，末行 "}" 也加 base_indent
    block_lines = [lines[0]]
    for line in lines[1:]:
        stripped = line.lstrip()
        leading = len(line) - len(stripped)
        if leading == 0:
            block_lines.append(" " * base_indent + stripped)
        else:
            block_lines.append(" " * base_indent + line)
    block_text = "\n".join(block_lines)

    # 从 opening brace 开始逐字符查找 matching closing brace
    brace_start = match.end() - 1  # '{' 的位置
    depth = 0
    pos = brace_start
    while pos < len(text):
        ch = text[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[: match.start()] + f'"{key}": {block_text}' + text[pos + 1 :]
        pos += 1
    return text  # brace 不平衡，放弃替换


# ═══════════════════════════════════════════════════════════════
# 顶层键扫描/patch 引擎（自 config/_core.py 迁入，与字段级替换同属本模块）
# ═══════════════════════════════════════════════════════════════


def _skip_ws_and_comments(text: str, i: int) -> int:
    """跳过空白、``//`` 行注释、``/* */`` 块注释，返回下一个实质字符索引。"""
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i)
            i = n if j == -1 else j + 2
            continue
        break
    return i


def _find_top_level_value_span(raw: str, key: str) -> tuple[int, int] | None:
    """定位含注释 JSON 文本中顶层键的 value 区间 (start, end)。

    返回 (value_start, value_end)：value 文本切片为 raw[value_start:value_end]。
    仅匹配顶层对象（深度 1）成员；字符串内 / 注释内出现的同名片段不误匹配。
    键不存在时返回 None。
    """
    n = len(raw)
    depth = 0
    i = 0
    while i < n:
        ch = raw[i]
        if ch == '"':
            j = i + 1
            while j < n:
                if raw[j] == "\\":
                    j += 2
                    continue
                if raw[j] == '"':
                    j += 1
                    break
                j += 1
            if depth == 1 and json.loads(raw[i:j]) == key:
                k = _skip_ws_and_comments(raw, j)
                if k < n and raw[k] == ":":
                    vs = _skip_ws_and_comments(raw, k + 1)
                    ve = _find_value_end(raw, vs)
                    return vs, ve
            i = j
            continue
        if ch in "{[":
            depth += 1
            i += 1
            continue
        if ch in "}]":
            depth -= 1
            i += 1
            continue
        if ch == "/" and i + 1 < n and raw[i + 1] == "/":
            j = raw.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if ch == "/" and i + 1 < n and raw[i + 1] == "*":
            j = raw.find("*/", i)
            i = n if j == -1 else j + 2
            continue
        i += 1
    return None


def _find_value_end(raw: str, start: int) -> int:
    """返回 value 的结束索引（不含），value 起始于 start。

    结构值（``{`` / ``[``）：括号匹配到对应闭合。标量值：扫描到逗号或
    对象/数组闭合符（无尾随逗号场景）。字符串与注释内容不会被误判结束。
    """
    n = len(raw)
    if start >= n:
        return start
    if raw[start] in "{[":
        depth = 0
        i = start
        while i < n:
            ch = raw[i]
            if ch == '"':
                j = i + 1
                while j < n:
                    if raw[j] == "\\":
                        j += 2
                        continue
                    if raw[j] == '"':
                        j += 1
                        break
                    j += 1
                i = j
                continue
            if ch in "{[":
                depth += 1
                i += 1
                continue
            if ch in "}]":
                depth -= 1
                i += 1
                if depth == 0:
                    return i
                continue
            if ch == "/" and i + 1 < n and raw[i + 1] == "/":
                j = raw.find("\n", i)
                i = n if j == -1 else j + 1
                continue
            if ch == "/" and i + 1 < n and raw[i + 1] == "*":
                j = raw.find("*/", i)
                i = n if j == -1 else j + 2
                continue
            i += 1
        return n
    i = start
    while i < n:
        ch = raw[i]
        if ch == '"':
            j = i + 1
            while j < n:
                if raw[j] == "\\":
                    j += 2
                    continue
                if raw[j] == '"':
                    j += 1
                    break
                j += 1
            i = j
            continue
        if ch in ",}]":
            return i
        if ch == "/" and i + 1 < n and raw[i + 1] == "/":
            j = raw.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if ch == "/" and i + 1 < n and raw[i + 1] == "*":
            j = raw.find("*/", i)
            i = n if j == -1 else j + 2
            continue
        i += 1
    return n


def _find_top_level_close_brace(raw: str) -> int | None:
    """返回顶层对象的闭合右花括号索引（键不存在时用于追加新键）。"""
    n = len(raw)
    depth = 0
    i = 0
    while i < n:
        ch = raw[i]
        if ch == '"':
            j = i + 1
            while j < n:
                if raw[j] == "\\":
                    j += 2
                    continue
                if raw[j] == '"':
                    j += 1
                    break
                j += 1
            i = j
            continue
        if ch in "{[":
            depth += 1
            i += 1
            continue
        if ch in "}]":
            depth -= 1
            if ch == "}" and depth == 0:
                return i
            i += 1
            continue
        if ch == "/" and i + 1 < n and raw[i + 1] == "/":
            j = raw.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if ch == "/" and i + 1 < n and raw[i + 1] == "*":
            j = raw.find("*/", i)
            i = n if j == -1 else j + 2
            continue
        i += 1
    return None


def _patch_config_key(raw: str, key: str, new_value_text: str) -> str:
    """在含注释 JSON 文本中替换或追加顶层键的值，保留注释与其他键。

    键已存在 → 仅替换该键的 value 区间；不存在 → 追加到对象末尾（保持合法）。

    Args:
        raw: 磁盘原始文本（可含 ``//`` 分组注释与行尾注释）
        key: 顶层配置键名
        new_value_text: 新值的 JSON 序列化文本（如 ``"abc"``、``42``、``{...}``）

    Returns:
        patch 后的完整文本。
    """
    span = _find_top_level_value_span(raw, key)
    if span is not None:
        start, end = span
        return raw[:start] + new_value_text + raw[end:]
    top_close = _find_top_level_close_brace(raw)
    if top_close is None:
        raise ValueError(f"config.json 无法定位顶层对象闭合位置，无法插入键 {key!r}")
    key_text = json.dumps(key, ensure_ascii=False)
    before = raw[:top_close]
    if before.rstrip().endswith("{"):
        # 空对象 { } → 直接写入成员
        new_raw = before + f"\n  {key_text}: {new_value_text}\n" + raw[top_close:]
    else:
        # 顶层最后一个成员后补逗号 + 换行 + 新键（逗号紧跟最后成员闭合符）
        stripped = before.rstrip()
        tail = before[len(stripped) :]
        new_raw = stripped + f",\n  {key_text}: {new_value_text}" + tail + raw[top_close:]
    return new_raw


def _remove_top_level_key(raw: str, key: str, vs: int, ve: int) -> str:
    """从含注释 JSON 文本中删除一个顶层键条目（含行尾注释与分隔逗号）。

    Args:
        raw: 磁盘原始文本
        key: 键名（用于定位行首）
        vs: value 起始索引（`_find_top_level_value_span` 返回值）
        ve: value 结束索引

    Returns:
        删除后的完整文本。被删键为中间键（值后紧跟逗号）→ 删除整行；
        为最后一个键（无尾随逗号）→ 删除整行并清理前一成员行尾逗号。
    """
    key_text = json.dumps(key, ensure_ascii=False)
    ks = raw.rfind(key_text, 0, vs)
    line_start = raw.rfind("\n", 0, ks)
    entry_start = line_start + 1 if line_start != -1 else 0
    if raw[ve : ve + 1] == ",":
        # 中间键：逗号跟在值后，删除整个条目行（含逗号、行尾注释、换行）
        next_nl = raw.find("\n", ve)
        entry_end = (next_nl + 1) if next_nl != -1 else len(raw)
        return raw[:entry_start] + raw[entry_end:]
    # 最后一个键：无自身尾随逗号，删除条目行后清理顶层对象末位成员尾随逗号。
    # 注意 _find_value_end 对末位标量会一路扫到顶层闭合 }（ve 可能越过键行），
    # 故先回退到 value 内容真实结束，再定位键行尾（保留顶层 }）。
    value_end = ve
    while value_end > vs and raw[value_end - 1] in " \t\r\n":
        value_end -= 1
    next_nl = raw.find("\n", value_end)
    entry_end = (next_nl + 1) if next_nl != -1 else value_end
    new_raw = raw[:entry_start] + raw[entry_end:]
    # 清理被删键前一成员（删除后成为顶层末位成员）的行尾尾随逗号。
    # 不依赖删除前后的索引映射，直接定位顶层闭合 } 检查末位成员是否残留逗号。
    close_brace = _find_top_level_close_brace(new_raw)
    if close_brace is None:
        return new_raw
    before = new_raw[:close_brace]
    stripped = before.rstrip()
    if stripped.endswith(","):
        tail = before[len(stripped) :]
        new_raw = stripped[:-1] + tail + new_raw[close_brace:]
    return new_raw

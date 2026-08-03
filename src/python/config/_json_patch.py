"""JSON 文本编辑 — 带注释 JSON 的字段级替换与 dict 区块自适应缩进替换。

用于 llm_settings.json 等支持 ``//`` 注释的 JSON 文件：写入时保留原文件
注释与空白，仅替换发生变化的字段（自 tui/handlers_config.py 提取）。

对外提供：
  _update_json_raw_text(raw, current, new) — 字段级文本替换
  _replace_dict_block(text, key, new_val)  — dict 值区块 brace 平衡替换
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

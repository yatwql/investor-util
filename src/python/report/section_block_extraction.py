"""章节区块提取 — 按注册表归一化口径从双端载体提取实际区块名。

提取面（与 `core/section_block_registry.py` 的契约配套，三向对账的「实现」侧）：

- **HTML 端** `extract_html_block_titles`：
    1. ``class="block-title"`` 元素（全部计为区块，可带序号头）；
    2. 内联加粗 div 中**带序号头**者（`①` / `一、` 式，区块级）——不带序号的
       加粗行是块内小标签（配对明细/回撤明细/持仓视角等），不计；
    3. 序号结构注释（`<!-- ── 一、…` / `<!-- ① …`）**兜底**：标题取序号后正文、
       按全角冒号截断、去 `─` 装饰；其序号已被可见区块占用或标题与可见区块
       归一后同名时丢弃（可见优先）。由此历史章「注释即区块」形态与演进章
       「注释旧文案 vs 可见新文案」并存都能收敛到注册表清单。
- **Excel 端** `extract_excel_block_titles`：AST 收集 ``write_block_title``
    调用点的第 3 参（字面量或模块常量），归一后比对——非区块小节标题
    （说明/配对明细/基准对照等）仍走 ``write_title_row``，不进入契约。

归一化 `normalize_block_title`（两端同口径，注册表清单即归一化结果）：
去 span 副标题与 HTML 标签 → 折叠空白 → 去序号头 → 去【】外框 → 去全角括号段。
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from pathlib import Path

_ORD_CN = "一二三四五六七八九十"
_ORD_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

# 序号头：中文数字须带顿号（避免把「一半」类词首误判），圈号直接后随
_MARKER_RE = re.compile(rf"^\s*(?:[{_ORD_CN}]+、|[{_ORD_CIRCLED}])\s*")
_RE_BLOCK_TITLE = re.compile(r'class="block-title">(.*?)</div>', re.S)
_RE_BOLD_DIV = re.compile(r'<div style="font-weight: bold[^"]*">(.*?)</div>', re.S)
# 注释兜底仅采「── 框式结构注释」（历史章形态）；裸 `<!-- ① … -->` 备注不计
_RE_COMMENT = re.compile(rf"<!--\s*─+\s*([{_ORD_CN}]+、|[{_ORD_CIRCLED}])\s*([^>]*?)\s*-->")


def normalize_block_title(raw: str) -> str:
    """区块标题归一化（注册表清单与双端提取共用的同一口径）。"""
    s = re.sub(r"<span[^>]*>.*?</span>", "", raw, flags=re.S)  # 去 span 副标题
    s = re.sub(r"<[^>]+>", "", s)  # 去其余 HTML 标签
    s = re.sub(r"\s+", " ", s).strip()
    s = _MARKER_RE.sub("", s)  # 去序号头
    s = re.sub(r"【([^】]*)】", r"\1", s)  # 【持仓概况】→ 持仓概况
    while "（" in s:  # 去全角括号段（含嵌套）
        s2 = re.sub(r"（[^（）]*）", "", s)
        if s2 == s:
            break
        s = s2
    return s.strip()


def extract_html_block_titles(partial_paths: Iterable[Path]) -> set[str]:
    """从 HTML partial 提取归一化区块名集合（三源规则见模块 docstring）。"""
    visible: set[str] = set()
    visible_markers: set[str] = set()
    commented: list[tuple[str, str]] = []
    for path in partial_paths:
        text = path.read_text(encoding="utf-8")
        for match in _RE_BLOCK_TITLE.finditer(text):
            norm = normalize_block_title(match.group(1))
            if norm:
                visible.add(norm)
                marker = _MARKER_RE.match(re.sub(r"<[^>]+>", "", match.group(1)))
                if marker:
                    visible_markers.add(marker.group(0).strip())
        for match in _RE_BOLD_DIV.finditer(text):
            raw = match.group(1)
            if not _MARKER_RE.match(raw):  # 无序号加粗行 = 块内小标签，不计
                continue
            norm = normalize_block_title(raw)
            if norm:
                visible.add(norm)
                marker = _MARKER_RE.match(raw)
                visible_markers.add(marker.group(0).strip())
        for match in _RE_COMMENT.finditer(text):
            body = match.group(2).strip("─ ")
            norm = normalize_block_title(body)
            if "：" in norm:  # 注释题名常带冒号后缀（“走势表：净值趋势图 …”），归一后截断
                norm = norm.split("：", 1)[0].strip()
            if norm:
                commented.append((match.group(1), norm))
    out = set(visible)
    for marker, norm in commented:
        if marker not in visible_markers and norm not in visible:
            out.add(norm)
    return out


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _resolve_title(node: ast.Call, consts: dict[str, str]) -> str | None:
    """取 write_block_title 第 3 参静态文本（字面量 / 模块常量 / title= 关键字）。"""
    if len(node.args) > 2:
        arg = node.args[2]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        if isinstance(arg, ast.Name):
            return consts.get(arg.id)
    for kw in node.keywords:
        if kw.arg == "title" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _collect_title_forwarders(tree: ast.Module) -> dict[str, int]:
    """找出「把参数直通给 write_block_title」的包装函数 → {函数名: 参数位次}。

    如行动章 ``_write_sub_block(ws, row, title, …)``：字面量在调用点，区块标题
    经参数直通写入——提取时对这类调用点解析对应位参，无需包装内联。
    """
    forwarders: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        params = [a.arg for a in node.args.args]
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and _call_name(sub.func) == "write_block_title"
                and len(sub.args) > 2
                and isinstance(sub.args[2], ast.Name)
                and sub.args[2].id in params
            ):
                forwarders.setdefault(node.name, params.index(sub.args[2].id))
    return forwarders


def _owner_function(tree: ast.Module) -> dict[int, str]:
    """建立「调用节点 id → 所在顶层函数名」映射（区分直通包装内外）。"""
    owners: dict[int, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    owners[id(sub)] = node.name
    return owners


def _resolve_at(call: ast.Call, index: int, consts: dict[str, str]) -> str | None:
    """取调用第 index 位参的静态文本（字面量 / 模块常量 / 同名关键字）。"""
    if len(call.args) > index:
        arg = call.args[index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        if isinstance(arg, ast.Name):
            return consts.get(arg.id)
    for kw in call.keywords:
        if kw.arg in {"title", "text", "label", "name"} and isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, str):
                return kw.value.value
    return None


def extract_excel_block_titles(module_paths: Iterable[Path]) -> set[str]:
    """从 Excel 写入器提取 write_block_title 调用点的归一化区块名集合。

    覆盖两种形态：直接字面量/常量调用，以及参数直通包装（见
    ``_collect_title_forwarders``）的调用点位参；包装体内的直通占位调用
    由其调用点提供字面量，此处跳过。标题非静态时抛 ValueError——区块契约
    要求静态可提取。
    """
    titles: set[str] = set()
    for path in module_paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        consts: dict[str, str] = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        consts[target.id] = node.value.value
        forwarders = _collect_title_forwarders(tree)
        owners = _owner_function(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            if name == "write_block_title":
                raw = _resolve_title(node, consts)
                if raw is None:
                    if owners.get(id(node)) in forwarders:
                        continue  # 直通包装体内的占位调用，字面量在调用点
                    raise ValueError(
                        f"{path.name}:{node.lineno}: write_block_title 标题须为字面量或模块常量（区块契约要求静态可提取）"
                    )
                titles.add(normalize_block_title(raw))
            elif name in forwarders:
                raw = _resolve_at(node, forwarders[name], consts)
                if raw is None:
                    raise ValueError(
                        f"{path.name}:{node.lineno}: 区块包装调用第 {forwarders[name]} 位标题须为字面量或模块常量"
                    )
                titles.add(normalize_block_title(raw))
    return titles

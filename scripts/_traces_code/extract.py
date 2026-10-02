"""注释行抽取（per-language）与标识符提取（check-code-traces 扫描输入层）。"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path

from _traces_code.patterns import _COMPILED_IDENTIFIER_PATTERNS


def _scan_identifiers(fpath: Path) -> list[tuple[int, str, str, str]]:
    """扫描单个文件的代码标识符，返回 [(行号, 分类, 模式说明, 标识符), ...]"""
    hits: list[tuple[int, str, str, str]] = []
    for lineno, ident in _iter_identifiers(fpath):
        for pat, cat, desc in _COMPILED_IDENTIFIER_PATTERNS:
            if pat.search(ident):
                hits.append((lineno, cat, desc, ident))
                break  # first match only per identifier
    return hits


def _iter_identifiers(fpath: Path) -> Iterator[tuple[int, str]]:
    """按文件类型提取代码标识符，产出 (行号, 标识符)。

    .py 用 ast 精确提取（函数/类/参数/赋值目标/导入别名）；
    .js/.mjs 用正则提取声明（var/let/const/function/class 名）。
    其余类型（.html/.sh/.ps1/.bat/.cmd）不参与标识符扫描。
    """
    suffix = fpath.suffix.lower()
    try:
        text = fpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if suffix == ".py":
        try:
            tree = ast.parse(text, filename=str(fpath))
        except SyntaxError:
            return
        yield from _py_identifier_names(tree)
    elif suffix in (".js", ".mjs"):
        yield from _js_identifier_names(text)


def _py_identifier_names(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """从 Python AST 提取全部标识符名（函数/类/参数/赋值目标/导入别名）。"""
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _a = node.args
            names.extend(x.arg for x in (*_a.posonlyargs, *_a.args, *_a.kwonlyargs))
            if _a.vararg:
                names.append(_a.vararg.arg)
            if _a.kwarg:
                names.append(_a.kwarg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Param)):
            names.append(node.id)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.alias):
            names.append(node.asname or node.name.split(".")[0])
        for name in names:
            if name:
                yield node.lineno, name


_JS_DECL_RE = re.compile(r"\b(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)\b")


def _js_identifier_names(text: str) -> Iterator[tuple[int, str]]:
    """从 JS 文本提取声明名（const/let/var/function/class 后的标识符）。"""
    for lineno, line in enumerate(text.split("\n"), 1):
        for m in _JS_DECL_RE.finditer(line):
            yield lineno, m.group(1)


def _iter_comment_lines(fpath: Path) -> Iterator[tuple[int, str]]:
    """按文件类型提取注释/文档字符串行，产出 (行号, 注释内容)。

    支持的扩展名：.py / .js / .mjs / .html / .sh / .ps1 / .bat / .cmd。
    其余类型不参与扫描。
    """
    suffix = fpath.suffix.lower()
    if suffix not in (".py", ".js", ".mjs", ".html", ".sh", ".ps1", ".bat", ".cmd"):
        return
    try:
        text = fpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if suffix == ".py":
        yield from _py_comment_lines(text)
    elif suffix in (".js", ".mjs"):
        yield from _js_comment_lines(text)
    elif suffix == ".html":
        yield from _html_comment_lines(text)
    else:
        yield from _shell_comment_lines(suffix, text)


def _shell_comment_lines(suffix: str, text: str) -> Iterator[tuple[int, str]]:
    """脚本文件注释：`.sh`（#）、`.ps1`（# 与 `<# #>`）、`.bat`/`.cmd`（REM/::）。"""
    if suffix in (".bat", ".cmd"):
        for lineno, raw in enumerate(text.split("\n"), 1):
            stripped = raw.strip().lstrip("﻿")
            if not stripped:
                continue
            if stripped[:4].upper() == "REM ":
                yield lineno, stripped[4:].lstrip()
            elif stripped.startswith("::"):
                yield lineno, stripped[2:].lstrip()
        return
    in_ps_block = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip().lstrip("﻿")
        if not stripped:
            continue
        if suffix == ".ps1" and in_ps_block:
            yield lineno, stripped
            if "#>" in stripped:
                in_ps_block = False
            continue
        if suffix == ".ps1" and stripped.startswith("<#"):
            yield lineno, stripped
            if "#>" not in stripped[2:]:
                in_ps_block = True
            continue
        if stripped.startswith("#!"):
            continue  # shebang，非注释
        if stripped.startswith("#"):
            yield lineno, stripped
            continue
        # 行内注释：提取由空白引导的 # 之后的注释文本（跳过字符串/URL 内 #）
        m = re.search(r"[ \t]#", stripped)
        if m:
            yield lineno, stripped[m.start() + 1 :]


def _py_comment_lines(text: str) -> Iterator[tuple[int, str]]:
    """Python：`#` 行注释（含行内）+ 真正的 docstring。

    用 tokenize 提取注释 token、用 AST 判定模块/类/函数 docstring 的行范围，
    避免行级三引号启发式把代码字符串（如 ``text = \"\"\"…\"\"\"``）的收尾行
    或裸 ``\"\"\"`` 关闭行误判为 docstring 开关，导致状态泄漏到后续代码行。
    """
    src_lines = text.split("\n")

    # AST 定位真正的 docstring 行范围：模块/类/函数体的首个字符串表达式语句
    doc_lines: set[int] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr):
                    val = body[0].value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        start = body[0].lineno
                        end = body[0].end_lineno or start
                        doc_lines.update(range(start, end + 1))

    # tokenize 提取注释 token（# 行注释/行内注释）与 docstring 字符串 token
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    except (tokenize.TokenError, IndentationError):
        return

    yielded: set[int] = set()
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            if tok.start[0] not in yielded:
                yielded.add(tok.start[0])
                yield tok.start[0], tok.string.strip()
        elif tok.type == tokenize.STRING and tok.start[0] in doc_lines:
            start, end = tok.start[0], tok.end[0]
            for ln in range(start, end + 1):
                if ln not in yielded and ln - 1 < len(src_lines):
                    yielded.add(ln)
                    yield ln, src_lines[ln - 1].strip()


def _js_comment_lines(text: str) -> Iterator[tuple[int, str]]:
    """JS：`//` 行注释 + `/* */` 块注释（含行内注释，排除 URL `://`）。"""
    in_block = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip()
        if in_block:
            yield lineno, stripped
            if "*/" in stripped:
                in_block = False
            continue
        if stripped.startswith("/*"):
            yield lineno, stripped
            if "*/" not in stripped[2:]:
                in_block = True
            continue
        if stripped.startswith("//"):
            yield lineno, stripped
            continue
        # 行内注释：// 或 /*（跳过 URL 的 ://）
        for m in re.finditer(r"//|/\*", stripped):
            marker = m.group(0)
            if marker == "//" and stripped[: m.start()].rstrip().endswith(":"):
                continue
            tail = stripped[m.start() :]
            if marker == "/*":
                end = tail.find("*/")
                tail = tail if end < 0 else tail[: end + 2]
                if end < 0:
                    in_block = True
            yield lineno, tail
            break


def _html_comment_lines(text: str) -> Iterator[tuple[int, str]]:
    """HTML：`<!-- -->`、Jinja `{# #}`、CSS/JS `/* */` 三种注释。"""
    in_jinja = in_html = in_css = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip()
        if in_jinja or in_html or in_css:
            yield lineno, stripped
            if in_jinja and "#}" in stripped:
                in_jinja = False
            if in_html and "-->" in stripped:
                in_html = False
            if in_css and "*/" in stripped:
                in_css = False
            continue
        starts = [("jinja", stripped.find("{#")), ("html", stripped.find("<!--")), ("css", stripped.find("/*"))]
        starts = [(k, p) for k, p in starts if p >= 0]
        if not starts:
            continue
        kind, pos = min(starts, key=lambda x: x[1])
        tail = stripped[pos:]
        end_marker = {"jinja": "#}", "html": "-->", "css": "*/"}[kind]
        end = tail.find(end_marker)
        if end >= 0:
            yield lineno, tail[: end + len(end_marker)]
        else:
            yield lineno, tail
            if kind == "jinja":
                in_jinja = True
            elif kind == "html":
                in_html = True
            else:
                in_css = True

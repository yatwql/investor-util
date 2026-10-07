#!/usr/bin/env python3
"""文档链接与结构一致性检查（死链 / 死锚点 / 重复标题 / 层级 / 编号序列 / § 引用）。

扫描范围（当前文档；`docs/archive/**` 为版本快照按设计豁免）：
  - `README.md`、`CLAUDE.md`
  - `docs/managements/*.md`（管理文档）
  - `docs/manuals/*.md`（用户手册）
  - `docs/plan/*.md`（中间计划）

六类检查：
  1. 死文件链接：相对链接目标文件不存在
  2. 死锚点：`#锚点` / `file.md#锚点` 无法命中目标文档标题——按 GitHub slug 规则
     （转小写、去标点、逐空格转连字符不折叠）生成；兼容显式 `<a id=...>` / `<a name=...>` 锚点
  3. 重复标题：同一文档内标题 slug 重复（GitHub 锚点只命中首处，`-1` 后缀链接脆弱）
  4. 标题层级跳变：相邻标题层级递增超过 1 级（如 h2 → h4）
  5. 编号标题序列：同层级（数字编号再按父前缀分组）序号必须连续——跳号即漏章或改名残留；
     中文数字序号（一、二、三…）按层级分组同样校验
  6. `xxx.md §N` 跨文档章节引用：归属取同一行中 § 之前最近出现的 `.md` 文件名
     （无文件名则归属当前文档），断言目标文档存在以该编号起始的标题（`#N.` / `**N.` 形式）

代码围栏（```）内的行不参与任何检查；行内代码（`...`）在链接提取时按等长空格遮罩，
不改变字符偏移，保证行号精确。

用法：
  python scripts/check-doc-links.py        # 检查全部
  python scripts/check-doc-links.py -v     # 详细输出（打印扫描文档清单）
  python scripts/check-doc-links.py --ci   # CI 模式（只输出 文件:行:描述，退出码 2）

退出码：
  0 — 全部通过
  2 — 发现 finding
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享设施（_checklib）
from _checklib import (  # noqa: E402
    REPO_ROOT,
    add_common_args,
    conclusion_cache_load,
    conclusion_cache_save,
    rel,
    report,
)

_SCOPE_GLOBS = (
    "README.md",
    "CLAUDE.md",
    "docs/managements/*.md",
    "docs/manuals/*.md",
    "docs/plan/*.md",
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_HTML_ANCHOR_RE = re.compile(r"""(?:id|name)\s*=\s*["']([^"']+)["']""")
_SECTION_REF_RE = re.compile(r"§\s*(\d+(?:\.\d+)*)")
_MD_TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+\.md")
_NUMERIC_HEAD_RE = re.compile(r"^(\d+(?:\.\d+)*)[.、\s]\s*(.*)$")
_CN_HEAD_RE = re.compile(r"^第?([一二三四五六七八九十]+)[、．.]\s*(.*)$")

_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def gh_slug(text: str) -> str:
    """GitHub 标题锚点 slug：转小写 → 去标点（保留字母数字/空白/_/-）→ 逐空白转连字符。

    与 github-slugger 一致：空格逐个替换不折叠，故 ``a — b`` 去掉长破折号后
    的两个空格会生成 ``a--b``；折叠空格会让 TOC 锚点全数失配。
    """
    cleaned = re.sub(r"[^\w\s-]", "", text.strip().lower(), flags=re.UNICODE)
    return re.sub(r"\s", "-", cleaned)


def _parse_cn(num: str) -> int | None:
    """中文数字（一 ~ 九十九）转整数；无法解析返回 None（调用方跳过该校验）。"""
    if num in _CN_DIGITS:
        return _CN_DIGITS[num]
    if num == "十":
        return 10
    if "十" in num:
        head, _, tail = num.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        return tens * 10 + (_CN_DIGITS.get(tail, 0) if tail else 0)
    return None


def default_targets() -> list[Path]:
    """默认扫描清单（当前文档，归档豁免）。"""
    targets: list[Path] = []
    for pattern in _SCOPE_GLOBS:
        targets.extend(sorted(REPO_ROOT.glob(pattern)))
    # 去重（glob 互不重叠，保序去重仅作防御）
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in targets:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _mask_fences(lines: list[str]) -> list[str]:
    """代码围栏行替换为等长空格（保字符偏移与行号），围栏状态由调用方逐行推进。"""
    out: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(" " * len(line))
            continue
        out.append(" " * len(line) if in_fence else line)
    return out


def _fence_states(lines: list[str]) -> list[bool]:
    """逐行标记是否处于代码围栏内（围栏起始行本身视为围栏内）。"""
    states: list[bool] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            states.append(True)
            continue
        states.append(in_fence)
    return states


def _parse_headings(lines: list[str], fenced: list[bool]) -> list[tuple[int, int, str]]:
    """提取非围栏 ATX 标题：[(行号 1-based, 层级, 原始标题文本), ...]。"""
    heads: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        if fenced[i]:
            continue
        m = _HEADING_RE.match(line)
        if m:
            heads.append((i + 1, len(m.group(1)), m.group(2)))
    return heads


class _Doc:
    """单份文档的解析缓存（标题 / 锚点 / 逐行掩码）。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        text = path.read_text(encoding="utf-8")
        raw_lines = text.split("\n")
        self.fenced = _fence_states(raw_lines)
        self.lines = _mask_fences(raw_lines)
        self.headings = _parse_headings(raw_lines, self.fenced)
        # slug → [行号...]（首处 + 后续重复）
        self.slug_lines: dict[str, list[int]] = {}
        for lineno, _level, raw in self.headings:
            self.slug_lines.setdefault(gh_slug(raw), []).append(lineno)
        # 文档是否使用数字编号章节（决定无文件名的 § 引用能否自归属）
        self.has_numeric_headings = any(_NUMERIC_HEAD_RE.match(raw) for _l, _lv, raw in self.headings)
        # 显式 HTML 锚点（<a id=...> / <a name=...>）
        self.html_anchors = {
            m.group(1)
            for i, line in enumerate(self.lines)
            if not self.fenced[i]
            for m in _HTML_ANCHOR_RE.finditer(line)
        }

    def has_anchor(self, anchor: str) -> bool:
        return anchor in self.slug_lines or anchor in self.html_anchors


def _check_dead_links_and_anchors(doc: _Doc, docs: dict[Path, _Doc]) -> list[str]:
    """死文件链接 + 死锚点（文内与跨文件）。"""
    findings: list[str] = []
    rel_path = rel(doc.path)
    for i, line in enumerate(doc.lines):
        if doc.fenced[i]:
            continue
        masked = _INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)
        for m in _LINK_RE.finditer(masked):
            text, target = m.group(1), m.group(2)
            if target.startswith(("http://", "https://", "mailto:", "<")):
                continue
            lineno = i + 1
            if target.startswith("#"):
                anchor = _safe_unquote(target[1:])
                if not doc.has_anchor(anchor):
                    findings.append(f"{rel_path}:{lineno}: 文内死锚点 [{text}](#{anchor})")
                continue
            file_part, _, anchor = target.partition("#")
            resolved = (
                (REPO_ROOT / file_part.lstrip("/")) if file_part.startswith("/") else (doc.path.parent / file_part)
            )
            if not resolved.exists():
                findings.append(f"{rel_path}:{lineno}: 死文件链接 [{text}]({target})")
                continue
            if anchor and resolved.suffix == ".md":
                target_doc = _load(resolved, docs)
                if target_doc is None:
                    findings.append(f"{rel_path}:{lineno}: 死文件链接 [{text}]({target})")
                elif not target_doc.has_anchor(_safe_unquote(anchor)):
                    findings.append(f"{rel_path}:{lineno}: 跨文件死锚点 [{text}]({target})")
    return findings


def _check_duplicate_headings(doc: _Doc) -> list[str]:
    """重复标题（锚点歧义）。"""
    rel_path = rel(doc.path)
    findings: list[str] = []
    for slug, lines in doc.slug_lines.items():
        for lineno in lines[1:]:
            findings.append(f"{rel_path}:{lineno}: 重复标题「{slug}」与前文同名（锚点只命中首处）")
    return findings


def _check_level_skips(doc: _Doc) -> list[str]:
    """相邻标题层级递增 > 1 级。"""
    rel_path = rel(doc.path)
    findings: list[str] = []
    for (prev_line, prev_level, prev_raw), (line, level, raw) in zip(doc.headings, doc.headings[1:]):
        if level > prev_level + 1:
            findings.append(
                f"{rel_path}:{line}: 标题层级跳变 h{prev_level} → h{level}"
                f"（「{raw}」紧接「{prev_raw}」后递升超过 1 级）"
            )
    return findings


def _check_numbering(doc: _Doc) -> list[str]:
    """数字与中文数字编号序列连续性。"""
    rel_path = rel(doc.path)
    findings: list[str] = []

    # 数字编号：按 (层级, 父前缀) 分组
    numeric: dict[tuple[int, str], list[tuple[int, str, str]]] = {}
    for lineno, level, raw in doc.headings:
        m = _NUMERIC_HEAD_RE.match(raw)
        if m:
            num, title = m.group(1), m.group(2)
            parent = num.rsplit(".", 1)[0] if "." in num else ""
            numeric.setdefault((level, parent), []).append((lineno, num, title))
    for group in numeric.values():
        for (line, num, title), (pline, pnum, ptitle) in zip(group[1:], group):
            if int(num.rsplit(".", 1)[-1]) != int(pnum.rsplit(".", 1)[-1]) + 1:
                findings.append(f"{rel_path}:{line}: 序号跳变「{num} {title}」接「{pnum} {ptitle}」")

    # 中文数字编号：按层级分组
    chinese: dict[int, list[tuple[int, int, str]]] = {}
    for lineno, level, raw in doc.headings:
        m = _CN_HEAD_RE.match(raw)
        if m:
            value = _parse_cn(m.group(1))
            if value is not None:
                chinese.setdefault(level, []).append((lineno, value, raw))
    for group in chinese.values():
        for (line, value, raw), (pline, pvalue, praw) in zip(group[1:], group):
            if value != pvalue + 1:
                findings.append(f"{rel_path}:{line}: 中文序号跳变「{raw}」接「{praw}」")
    return findings


def _check_section_refs(doc: _Doc, docs: dict[Path, _Doc], by_basename: dict[str, Path]) -> list[str]:
    """`xxx.md §N` 跨文档章节引用：目标文档须存在以该编号起始的标题。"""
    findings: list[str] = []
    rel_path = rel(doc.path)
    for i, line in enumerate(doc.lines):
        if doc.fenced[i]:
            continue
        # § 引用与文件名归属（最近前序 .md 记号；无则归属当前文档）
        for sec_match in _SECTION_REF_RE.finditer(line):
            section = sec_match.group(1)
            prior = [m for m in _MD_TOKEN_RE.finditer(line[: sec_match.start()]) if sec_match.start() - m.end() <= 60]
            if prior:
                name = Path(prior[-1].group(0)).name
                target_path = by_basename.get(name)
                if target_path is None:
                    continue  # 目标不在扫描范围（死文件链接由链接检查覆盖）
            else:
                # 无文件名归属时仅对编号章节文档自归属；非编号文档（如 FAQ）的
                # §N 多指报告章而非本文档章，跳过避免误报
                if not doc.has_numeric_headings:
                    continue
                target_path = doc.path
            target_doc = _load(target_path, docs)
            if target_doc is None:
                continue
            if not _target_has_section(target_doc, section):
                findings.append(f"{rel_path}:{i + 1}: § 引用无对应章节 {target_path.name} → §{section}")
    return findings


def _target_has_section(doc: _Doc, section: str) -> bool:
    """目标文档中是否存在以 `section` 起始的标题（`## N.` / `### §N`）或粗体段首（`**N.`）。"""
    esc = re.escape(section)
    heading_re = re.compile(rf"^#{{1,6}}\s*(?:§\s*)?{esc}(?:[.\s)）:：]|$)")
    bold_re = re.compile(rf"\*\*(?:§\s*)?{esc}(?:[.\s)）:：]|$)")
    for i, line in enumerate(doc.lines):
        if doc.fenced[i]:
            continue
        if heading_re.search(line) or bold_re.search(line):
            return True
    return False


def _load(path: Path, docs: dict[Path, _Doc]) -> _Doc | None:
    """按需加载并缓存文档解析；读取失败返回 None。"""
    key = path.resolve()
    if key not in docs:
        try:
            docs[key] = _Doc(path)
        except (OSError, UnicodeDecodeError):
            return None
    return docs[key]


def _safe_unquote(anchor: str) -> str:
    return unquote(anchor)


def run_checks(targets: Sequence[Path] | None = None) -> list[str]:
    """对目标文档集执行六类检查，返回 finding 列表（空 = 通过）。

    Args:
        targets: 待查文档路径；缺省用 `default_targets()`。跨文件解析只在该集合内发生。
    """
    paths = list(targets) if targets is not None else default_targets()
    docs: dict[Path, _Doc] = {}
    parsed: list[_Doc] = []
    findings: list[str] = []
    for p in paths:
        try:
            doc = _Doc(p)
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{rel(p)}: 无法读取文档（{exc}）")
            continue
        docs[p.resolve()] = doc
        parsed.append(doc)

    by_basename: dict[str, Path] = {}
    for p in paths:
        by_basename.setdefault(p.name, p)

    for doc in parsed:
        findings += _check_dead_links_and_anchors(doc, docs)
        findings += _check_duplicate_headings(doc)
        findings += _check_level_skips(doc)
        findings += _check_numbering(doc)
        findings += _check_section_refs(doc, docs, by_basename)
    return findings


#: 结论文案（全量与缓存回放两路共用，保证输出逐字一致）
_OK_MESSAGE = "[OK] 文档链接与结构一致（无死链/死锚点/重复标题/层级跳变/序号跳变/§引用失配）"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档链接与结构一致性检查（死链/死锚点/重复标题/层级/编号序列/§引用）")
    add_common_args(parser)
    args = parser.parse_args(argv)
    targets = default_targets()
    # 结论缓存（仅 --ci 加载）：输入面 = 受检文档集本身（跨文件解析只在集内发生）
    if args.ci:
        cached = conclusion_cache_load("doc_links", [Path(__file__)], targets)
        if cached is not None:
            return report(cached["findings"], _OK_MESSAGE, ci=True)
    if args.verbose:
        print(f"[..] 扫描 {len(targets)} 份当前文档（归档豁免）：")
        for p in targets:
            print(f"     {rel(p)}")
    findings = run_checks(targets)
    conclusion_cache_save("doc_links", [Path(__file__)], targets, {"findings": findings})
    return report(
        findings,
        _OK_MESSAGE,
        ci=args.ci,
    )


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""注释/文档字符串历史变更痕迹检查脚本。

扫描 src/ 与 scripts/ 下的 .py / .js / .mjs / .html / .sh / .ps1 /
.bat / .cmd 文件，检查注释和文档字符串中是否含有关代码历史迭代、
重构拆分、版本号标记、文件迁入迁出等变更痕迹。各语言注释形式：
Python（# 与三引号 docstring）、JS（// 与 /* */）、HTML（<!-- --> 与
Jinja {# #} 及 CSS /* */）、Shell（#）、PowerShell（# 与 <# #>）、
Windows 批处理（REM / ::）。

在代码和测试的注释/文档串中，只应描述"当前代码是什么/做什么"，
不应记录"从哪里来、怎么变的"。此类信息应放在管理文档
（changelog.md / review-findings.md）中。

用法：
  python scripts/check-history-traces.py           # 检查全部
  python scripts/check-history-traces.py -v        # 详细输出
  python scripts/check-history-traces.py --ci      # CI 模式（仅输出文件名:行号，非零退出码）

退出码：
  0 — 全部通过（无可疑痕迹）
  1 — 发现高置信度痕迹（HIGH/ORIGIN/VERSION）
  2 — 发现任务编号引用（CODE），应从注释中移除
  3 — 仅 LOW 级别痕迹，建议人工复核
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [
    REPO_ROOT / "src" / "python",
    REPO_ROOT / "src" / "test",
    REPO_ROOT / "src" / "static",
    REPO_ROOT / "scripts",
]
# 跳过文件名（压缩产物、本工具自身——后者的注释为检测类别文档，含 TODO/XXX 等字面量）
SKIP_FILES = {"chart.min.js", "check-history-traces.py"}


# ═══════════════════════════════════════════════════════════════
#  匹配模式定义
# ═══════════════════════════════════════════════════════════════
#  每项：(pattern, category, description)
#    pattern      — 正则表达式（在注释/文档串行中匹配）
#    category     — 置信度/分类（见下文说明）
#    description  — 简短说明
#
# 置信度等级说明：
#   HIGH       — 命中即违规，必须修复
#   ORIGIN     — 来源归属叙述，绝大多数是痕迹
#   VERSION    — 版本号/发布标记，注释中不应出现
#   DEPR       — 废弃/过时标记（需判断）
#   CHANGE     — 变更描述（需人工判断）
#   TODO       — 待办标记（建议用 issue 跟踪）

PATTERNS: list[tuple[str, str, str]] = [
    #
    # ═══ HIGH：明确的历史变更痕迹 ═══
    #   命中即违规——注释中不应出现这类内容。
    #
    (
        r"从[\w._\-]+\.py\s*(?:拆分|提取|迁移|合并|分离|移[入出至到])",
        "HIGH",
        "显式来源叙述（从XX.py拆分/提取/迁移/合并）",
    ),
    (r"合并[自到][\w._\-]+\.py", "HIGH", "合并自XX.py（暗示从其他文件合并而来）"),
    (r"(?:拆分|提取|分离)[自到成为][\w._\-]+\.py", "HIGH", "来源叙述（拆分自/分离为XX.py）"),
    (r"已迁[至到]\s*[\w._\-]+\.py", "HIGH", "已迁至XX.py（旧代码所在注释）"),
    (r"从原[\w._\-]+\.py\s*(?:合并|迁[入移])", "HIGH", "从原文件合并/迁入"),
    (r"(?<!原)\.py\s*(?:拆分|迁移)(?:至此|到此)", "HIGH", "拆分/迁移到此文件"),
    (r"(?:共同|原有).*?(?:职责|功能|逻辑).*?(?:拆分|提取|迁移|分离)(?:至此|到此)", "HIGH", "职责/功能迁移到此"),
    (r"自[\w._\-]+\.py\s*(?:拆分|提取|迁移)", "HIGH", "自XX.py拆分/提取"),
    #   以下模式覆盖 docstring 中 backtick 包裹（``module.py``）或裸写的模块路径，
    #   以及测试文件之间的覆盖/复用来源叙述（均属代码历史痕迹）。
    (r"提取自\s*[`\w./_-]+\.py", "HIGH", "提取自XX.py（来源归属叙述）"),
    (
        r"(?:从|由)\s*[`\w./_-]+\.py\s*(?:提取|复用|拆分|迁移|合并|分离)",
        "HIGH",
        "从XX.py提取/复用/拆分/迁移（来源归属叙述）",
    ),
    (r"已由\s*[`\w./_-]+\.py\s*(?:完整)?覆盖", "HIGH", "已由XX.py覆盖（测试覆盖来源叙述）"),
    (r"\b(?:Iter|Iteration)\s*\d+\b", "HIGH", "Iter/Iteration N 迭代标记（历史迭代信息）"),
    (r"已迁移", "HIGH", "已迁移（迁移痕迹）"),
    (r"历史上|历次迭代", "HIGH", "历史迭代信息（历史上/历次迭代）"),
    (r"曾(?:经)?(?:用[于]?|作为|属于|采用|以)", "HIGH", "曾用/曾用于/曾作为（历史实现叙述）"),
    (r"(?:后来|之后|随后)\s*(?:改[为成]|换[为成]|引入|移除)", "HIGH", "后来改为/之后引入（变更痕迹）"),
    #   以下模式将来源叙述扩展到非 .py 文件（.js/.html 等）。
    (r"提取自\s*[`\w./_-]+\.(?:js|mjs|html|ts|vue)", "HIGH", "提取自XX.js/html（来源归属叙述）"),
    (
        r"(?:从|由)\s*[`\w./_-]+\.(?:js|mjs|html|ts|vue)\s*(?:提取|复用|拆分|迁移|合并|分离)",
        "HIGH",
        "从XX.js/html提取/复用（来源归属叙述）",
    ),
    (r"已由\s*[`\w./_-]+\.(?:js|mjs|html|ts|vue)", "HIGH", "已由XX.js/html覆盖（来源叙述）"),
    #
    # ═══ CODE：任务/编号引用 ═══
    #   代码注释中不应出现管理任务的编号（形如 编号前缀-数字）。
    #
    (r"(?:rf|plan|R)-\d+", "CODE", "任务编号引用（如 rf-117、R-086）"),
    #
    # ═══ VERSION：版本号 / 发布 / 迭代标记 ═══
    #   代码注释中不应出现版本号、迭代信息、项目编号等变更记录。
    #
    (r"v\d+\.\d+\.\d+(?:-dev)?", "VERSION", "版本号标记（如 v0.8.9）"),
    (r"版本\s*[:：]\s*\d+\.\d+", "VERSION", "版本号声明"),
    (r"(?:发版|发布|release)\s*(?:于|版本|v?\d)", "VERSION", "发布/发版标记"),
    (r"迭代\s*(?:\d+|任务|计划)", "VERSION", "迭代/任务标记"),
    (r"切[换至到]\s*(?:dev|master|main|分支)", "VERSION", "分支切换记录"),
    (r"未升级版|旧版|老版", "VERSION", "旧版/未升级版（版本对比痕迹）"),
    (r"(?:原先|最初|早期)(?:是|为|使用|采用|属于)", "VERSION", "原先/最初/早期（历史状态叙述）"),
    #
    # ═══ ORIGIN：来源归属（通常也是痕迹） ═══
    #
    (r"本文件(?:保留|维护)(?:测试|内容|的)", "ORIGIN", "本文件保留/维护内容（暗示拆分）"),
    (r"由[\w._\-]+\.py\s*(?:移[入至]|迁[入至])", "ORIGIN", "由XX.py迁入/移入"),
    (r"原\s*[`\w./_-]+\.(?:py|js|mjs|html|ts|vue)", "ORIGIN", "原XX.py/js（暗示代码来源）"),
    (r"原为[\w._\-]+\.py", "ORIGIN", "原为XX.py（暗示历史来源）"),
    (r"来源于[\w._\-]+\.py", "ORIGIN", "来源于XX.py（暗示代码来源）"),
    (r"出自[\w._\-]+\.py", "ORIGIN", "出自XX.py（暗示代码来源）"),
    (r"原属[\w._\-]+\.py", "ORIGIN", "原属XX.py（暗示归属变迁）"),
    (r"是[\w._\-]+\.py\s*(?:的一部分|的组成部分)", "ORIGIN", "是XX.py的一部分（暗示文件拆分关系）"),
    #
    # ═══ DEPR：废弃/过时标记 ═══
    #
    (r"已废弃|已弃用|已重命名|已更名", "DEPR", "废弃/重命名标注（需判断是否为运行时行为）"),
    (r"过渡方案|过渡期|过渡性", "DEPR", "过渡性方案说明"),
    (r"暂时保留|暂保留|暂不[处理修复实现支持]", "DEPR", "暂时保留/暂不处理"),
    (r"(?:不再[推荐使用支持保留需要]|不再建议)", "DEPR", "不再推荐/使用/支持"),
    (r"兼容过渡", "DEPR", "兼容过渡（过渡性方案说明）"),
    #
    # ═══ CHANGE：变更描述（需人工判断） ═══
    #
    (r"重构[为成到]", "CHANGE", "重构为/重构到"),
    (r"新.{0,4}(?:版本|方案).{0,8}(?:替代|替换)", "CHANGE", "新版本/方案替代旧的"),
    (r"替代原有的|替换旧|替代旧", "CHANGE", "替代原有/旧的"),
    (r"(?<!最)新版", "CHANGE", "新版（版本变更描述，需判断）"),
    #
    # ═══ TODO：待办标记 ═══
    #
    (r"\b(?:TODO|FIXME|HACK|XXX|WORKAROUND)\b", "TODO", "待办/临时处理标记"),
    (r"尚未[实现处理支持完成覆盖]", "TODO", "尚未完成/实现（需加 issue 跟踪）"),
    (r"待[办做处补充修复]", "TODO", "待办/待处理"),
    (r"后续\s*(?:版本|迭代|优化|需要|再处理)", "TODO", "后续版本/迭代（需加 issue 跟踪）"),
]

# 行内排除模式：即使行命中 PATTERNS，若匹配以下任意模式则跳过
EXCLUDE_LINE: list[str] = [
    # ── 运行时行为描述（合法） ─────────
    r"模拟断电",
    r"模拟\s+\w+\s+崩溃",
    r"无临时文件残留",
    r"临时文件被清理",
    r"原文件不受影响",
    r"原文件应[保留完整存在]",
    r"原文件.*旧值",
    r"原文件完整",
    r"文件可能残留在磁盘",
    r"残留临时文件",
    r"清理.*过期.*归档目录",
    r"清理.*缓存",
    r"清除.*残留.*状态",
    r"前一阶段尚未关闭",  # perf.py
    # ── 运行时功能描述（合法） ─────────
    r"兼容性检查",
    r"兼容性名单",
    r"Thinking 兼容性",
    r"是否支持.*兼容",
    r"跨.*兼容",
    r"仍然可用",
    # ── 运行时回退/降级（合法） ──────
    r"回退[到为].*默认",
    r"回退[到为].*兜底",
    r"降级[到为].*过期缓存",
    r"降级[到为].*普通",
    r"改为降级",
    r"回退到\s*(?:\"|').*?(\"|')",  # 回退到"off"等 valid value
    # ── 运行时归档/版本行为（合法） ──────
    r"旧配置仍可",
    r"旧状态不会残留",
    r"跨日残留缓存清仓",
    r"缓存.*前序测试.*残留",
    r"尚未缓存到 registry session_cache",
    r"尚未重新熔断",
    r"尚未达到新鲜缓存",
    # ── VERSION 模式误报排除（运行时版本） ──
    r"APP_VERSION",
    r"__version__",
    r"version\s*=?\s*[\"']\d+\.\d+",  # 代码中赋值版本号变量
    r"原版本.*备份",  # 运行时备份逻辑
    r"备份旧版本",
    r"版本不兼容",
    r"版本.*不匹配",
    r"版本.*太低",
    r"版本.*落后",
    r"python.*版本",
    r"min_version",
    r"max_version",
    r"python_version",
    r"version_info",
    r"protobuf.*版本",  # compiler.proto version
    # ── TODO 模式误报排除（XXX 作为掩码占位符） ──
    r"000XXX",
    r"XXX\[",
    r"jQueryXXX",
]
_COMPILED_EXCLUDE = [re.compile(p) for p in EXCLUDE_LINE]


def _is_triple_quote_line(stripped: str) -> tuple[bool, bool]:
    """判断该行是否为三引号行。

    Returns:
        (is_open_close, is_open_only)
        is_open_close — 同一行内打开又关闭（如 \\"\\"\\"brief doc\\"\\"\\"）
        is_open_only  — 仅打开（或仅关闭）没有在同一行闭合
    """
    if stripped.startswith('"""') or stripped.startswith("'''"):
        # 检查该行是否在开头三引号之后又出现了结尾三引号
        rest = stripped[3:]
        close_quote = '"""' if stripped.startswith('"""') else "'''"
        if close_quote in rest:
            return (True, False)  # 同一行内开+关
        return (False, True)  # 仅打开或仅关闭
    return (False, False)


def _is_excluded(line: str) -> bool:
    """检查该行是否匹配排除模式（合法运行时描述）。"""
    for pat in _COMPILED_EXCLUDE:
        if pat.search(line):
            return True
    return False


def scan_file(fpath: Path, verbose: bool) -> list[tuple[int, str, str, str]]:
    """扫描单个文件，返回 [(行号, 分类, 模式说明, 行内容), ...]"""
    hits: list[tuple[int, str, str, str]] = []
    if fpath.name in SKIP_FILES:
        return hits

    for lineno, ctext in _iter_comment_lines(fpath):
        if not ctext.strip():
            continue
        if _is_excluded(ctext):
            if verbose:
                print(f"    (excluded) L{lineno}: {ctext[:80]}")
            continue

        for pat, cat, desc in PATTERNS:
            if re.search(pat, ctext):
                hits.append((lineno, cat, desc, ctext[:120]))
                break  # first match only per line

    return hits


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
    """Python：`#` 行注释（含行内）+ 三引号 docstring（含单行/多行状态跟踪）。"""
    in_docstring = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip()
        if not stripped:
            continue

        # 检测三引号开关，切换 docstring 状态
        is_oc, is_open = _is_triple_quote_line(stripped)
        if is_open:
            in_docstring = not in_docstring
            yield lineno, stripped  # 开关行本身参与匹配
        elif is_oc:
            yield lineno, stripped  # 单行 docstring（同行开闭）
        elif in_docstring:
            yield lineno, stripped
        elif stripped.startswith("#"):
            yield lineno, stripped
        else:
            # 行内注释：提取由空白引导的 # 之后的注释文本（跳过字符串内 #）
            m = re.search(r"[ \t]#", stripped)
            if m:
                yield lineno, stripped[m.start() + 1 :]


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="扫描代码注释中的历史变更痕迹",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="详细输出（含排除行信息）",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI 模式：仅输出 文件名:行号，非零退出码",
    )
    args = parser.parse_args()

    total_hits = 0
    high_count = 0
    code_count = 0
    low_count = 0
    summary: dict[str, int] = {}

    supported = {".py", ".js", ".mjs", ".html", ".sh", ".ps1", ".bat", ".cmd"}
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for fpath in sorted(scan_dir.rglob("*")):
            if not fpath.is_file() or fpath.suffix.lower() not in supported:
                continue
            rel = fpath.relative_to(REPO_ROOT)
            hits = scan_file(fpath, args.verbose)
            if not hits:
                continue

            if not args.ci:
                print(f"\n  {rel}")

            for lineno, cat, desc, text in hits:
                total_hits += 1
                summary[cat] = summary.get(cat, 0) + 1
                is_high = cat in ("HIGH", "ORIGIN", "VERSION")
                if is_high:
                    high_count += 1
                elif cat == "CODE":
                    code_count += 1
                else:
                    low_count += 1

                if args.ci:
                    print(f"{rel}:{lineno} [{cat}] {desc} — {text}")
                else:
                    marker = "[ERR]" if is_high else "[!]"
                    print(f"    {marker} L{lineno:>4} [{cat}] {desc}")
                    if args.verbose:
                        print(f"           {text}")

    # ── 汇总输出 ──────────────────────────────────────────────
    print()
    if total_hits == 0:
        print("[OK] 未发现历史变更痕迹，注释干净")
        sys.exit(0)

    cat_stats = ", ".join(f"{k}={v}" for k, v in sorted(summary.items()))
    print(f"[!] 发现 {total_hits} 处可疑痕迹（{cat_stats}）")
    if high_count > 0:
        print(f"    {high_count} 处高置信度（HIGH/ORIGIN/VERSION），建议优先审查")
        sys.exit(1)

    if code_count > 0:
        print(f"    {code_count} 处任务编号引用（CODE），应从注释中移除")
        sys.exit(2)

    if low_count > 0:
        print(f"[!] 仅 {low_count} 处 LOW 级别痕迹（TODO/CHANGE/DEPR），建议人工复核")
        sys.exit(3)


if __name__ == "__main__":
    main()

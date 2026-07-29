#!/usr/bin/env python3
"""注释/文档字符串历史变更痕迹检查脚本。

扫描 src/ 下所有 .py 文件，检查注释和文档字符串中是否含有关
于代码历史迭代、重构拆分、版本号标记、文件迁入迁出等变更痕迹。

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
  2 — 仅 LOW 级别痕迹，建议人工复核
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [REPO_ROOT / "src" / "python", REPO_ROOT / "src" / "test"]


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
    (r"从[\w._\-]+\.py\s*(?:拆分|提取|迁移|合并|分离|移[入出至到])", "HIGH",
     "显式来源叙述（从XX.py拆分/提取/迁移/合并）"),
    (r"合并[自到][\w._\-]+\.py", "HIGH",
     "合并自XX.py（暗示从其他文件合并而来）"),
    (r"(?:拆分|提取|分离)[自到成为][\w._\-]+\.py", "HIGH",
     "来源叙述（拆分自/分离为XX.py）"),
    (r"已迁[至到]\s*[\w._\-]+\.py", "HIGH",
     "已迁至XX.py（旧代码所在注释）"),
    (r"从原[\w._\-]+\.py\s*(?:合并|迁[入移])", "HIGH",
     "从原文件合并/迁入"),
    (r"(?<!原)\.py\s*(?:拆分|迁移)(?:至此|到此)", "HIGH",
     "拆分/迁移到此文件"),
    (r"(?:共同|原有).*?(?:职责|功能|逻辑).*?(?:拆分|提取|迁移|分离)(?:至此|到此)", "HIGH",
     "职责/功能迁移到此"),
    (r"自[\w._\-]+\.py\s*(?:拆分|提取|迁移)", "HIGH",
     "自XX.py拆分/提取"),

    #
    # ═══ CODE：任务/编号引用 ═══
    #   代码注释中不应出现管理任务的编号（如 rf-117、plan-42）。
    #
    (r"(?:rf|plan|R)-\d+", "CODE",
     "任务编号引用（如 rf-117、R-086）"),

    #
    # ═══ VERSION：版本号 / 发布 / 迭代标记 ═══
    #   代码注释中不应出现版本号、迭代信息、项目编号等变更记录。
    #
    (r"v\d+\.\d+\.\d+(?:-dev)?", "VERSION",
     "版本号标记（如 v0.8.9）"),
    (r"版本\s*[:：]\s*\d+\.\d+", "VERSION",
     "版本号声明"),
    (r"(?:发版|发布|release)\s*(?:于|版本|v?\d)", "VERSION",
     "发布/发版标记"),
    (r"迭代\s*(?:\d+|任务|计划)", "VERSION",
     "迭代/任务标记"),
    (r"切[换至到]\s*(?:dev|master|main|分支)", "VERSION",
     "分支切换记录"),

    #
    # ═══ ORIGIN：来源归属（通常也是痕迹） ═══
    #
    (r"本文件(?:保留|维护)(?:测试|内容|的)", "ORIGIN",
     "本文件保留/维护内容（暗示拆分）"),
    (r"由[\w._\-]+\.py\s*(?:移[入至]|迁[入至])", "ORIGIN",
     "由XX.py迁入/移入"),
    (r"原[\w._\-]+\.py", "ORIGIN",
     "原XX.py（暗示代码来源）"),
    (r"原为[\w._\-]+\.py", "ORIGIN",
     "原为XX.py（暗示历史来源）"),
    (r"来源于[\w._\-]+\.py", "ORIGIN",
     "来源于XX.py（暗示代码来源）"),
    (r"出自[\w._\-]+\.py", "ORIGIN",
     "出自XX.py（暗示代码来源）"),
    (r"原属[\w._\-]+\.py", "ORIGIN",
     "原属XX.py（暗示归属变迁）"),
    (r"是[\w._\-]+\.py\s*(?:的一部分|的组成部分)", "ORIGIN",
     "是XX.py的一部分（暗示文件拆分关系）"),

    #
    # ═══ DEPR：废弃/过时标记 ═══
    #
    (r"已废弃|已弃用|已重命名|已更名", "DEPR",
     "废弃/重命名标注（需判断是否为运行时行为）"),
    (r"过渡方案|过渡期|过渡性", "DEPR",
     "过渡性方案说明"),
    (r"暂时保留|暂保留|暂不[处理修复实现支持]", "DEPR",
     "暂时保留/暂不处理"),
    (r"(?:不再[推荐使用支持保留需要]|不再建议)", "DEPR",
     "不再推荐/使用/支持"),

    #
    # ═══ CHANGE：变更描述（需人工判断） ═══
    #
    (r"重构[为成到]", "CHANGE",
     "重构为/重构到"),
    (r"新.{0,4}(?:版本|方案).{0,8}(?:替代|替换)", "CHANGE",
     "新版本/方案替代旧的"),
    (r"替代原有的|替换旧|替代旧", "CHANGE",
     "替代原有/旧的"),

    #
    # ═══ TODO：待办标记 ═══
    #
    (r"\b(?:TODO|FIXME|HACK|XXX|WORKAROUND)\b", "TODO",
     "待办/临时处理标记"),
    (r"尚未[实现处理支持完成覆盖]", "TODO",
     "尚未完成/实现（需加 issue 跟踪）"),
    (r"待[办做处补充修复]", "TODO",
     "待办/待处理"),
    (r"后续\s*(?:版本|迭代|优化|需要|再处理)", "TODO",
     "后续版本/迭代（需加 issue 跟踪）"),
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
    try:
        text = fpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return hits

    in_docstring = False
    for lineno, raw in enumerate(text.split("\n"), 1):
        stripped = raw.strip()
        if not stripped:
            continue

        # 检测三引号开关，切换 docstring 状态
        is_oc, is_open = _is_triple_quote_line(stripped)
        if is_open:
            in_docstring = not in_docstring
            # 开关行本身继续往下参与模式匹配
        elif not in_docstring and not stripped.startswith("#"):
            # 不在 docstring 内也不是注释 → 跳过
            continue

        if _is_excluded(stripped):
            if verbose:
                print(f"    (excluded) L{lineno}: {stripped[:80]}")
            continue

        for pat, cat, desc in PATTERNS:
            if re.search(pat, stripped):
                hits.append((lineno, cat, desc, stripped[:120]))
                break  # first match only per line

    return hits


def main() -> None:
    parser = argparse.ArgumentParser(
        description="扫描代码注释中的历史变更痕迹",
    )
    parser.add_argument(
        "-v", "--verbose",
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
    low_count = 0
    summary: dict[str, int] = {}

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for pyfile in sorted(scan_dir.rglob("*.py")):
            rel = pyfile.relative_to(REPO_ROOT)
            hits = scan_file(pyfile, args.verbose)
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
        print()
        print("    高置信度模式通常对应：")
        print("    - docstring 标注「从XX.py拆分」 → 应改为「XX模块」")
        print("    - 注释标注「已迁至XX.py」 → 删除迁移动态")
        print("    - 注释标注版本号 → 删除版本信息")
        sys.exit(1)

    print(f"[!] 仅 {low_count} 处 LOW 级别痕迹（TODO/CHANGE/DEPR），建议人工复核")
    sys.exit(2)


if __name__ == "__main__":
    main()

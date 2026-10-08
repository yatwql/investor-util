#!/usr/bin/env python3
"""代码注释历史变更痕迹 + 任务编号标识符检查脚本（与 check-doc-traces.py 相对）。

扫描 src/ 与 scripts/ 下的 .py / .js / .mjs / .html / .sh / .ps1 /
.bat / .cmd 文件，检查注释和文档字符串中是否含有关代码历史迭代、
重构拆分、版本号标记、文件迁入迁出等变更痕迹，以及代码标识符
（变量/函数/类名）与注释中是否夹带任务编号/系列代号（语义命名纪律）。
各语言注释形式：Python（# 与三引号 docstring）、JS（// 与 /* */）、
HTML（<!-- --> 与 Jinja {# #} 及 CSS /* */）、Shell（#）、
PowerShell（# 与 <# #>）、Windows 批处理（REM / ::）。

在代码和测试的注释/文档串中，只应描述"当前代码是什么/做什么"，
不应记录"从哪里来、怎么变的"。此类信息应放在管理文档
（changelog.md / review-findings.md）中。标识符/注释中也不得出现
任务编号（plan-N / rf-N）或系列代号（B 系列/F 系列、b_series、F4 等）。

除历史痕迹外，注释/标识符中也不得出现三类暗号组合（无语义魔法编号 /
疑似任务编号 / 疑似无意义代码，统称"语义命名暗号"）：
  - 字母+数字（MAGIC）   ：C19 / D8 / HH6 / R11 / P1 —— 须用语义名替代
  - 字母-数字（DASHTASK）：F-1 / G-1 / TASK-22 / D-8 —— 疑似任务编号
  - 字母_数字（UNDERSCORE）：F_1 / H_1 / MINE_22 —— 疑似无意义代码
合法领域值（TOP10 前 N 名、T2/T3/T4 数据层级、T-1 交易日、A1:B1 Excel
单元格、F401 等 lint 码、VaR95/MD5、UTF-8、Sonnet-4 模型名等）由
_magic_excludes() / _dash_excludes() / _under_excludes() 行豁免。

两类扫描：
  - 注释痕迹扫描：PATTERNS 匹配注释/文档串行
  - 标识符扫描：IDENTIFIER_PATTERNS 匹配代码中的完整标识符 token
    （.py 用 ast 提取，.js/.mjs 用正则提取声明）

本文件为**薄 CLI**：模式表/扫描/守卫实现均在 `scripts/_traces_code/` 包
（config / patterns / exemptions / extract / scan / layers 六模块），
下方 re-export 保持「按原脚本名访问符号」的原面不破（测试与守护引用）。

用法：
  python scripts/check-code-traces.py           # 检查全部
  python scripts/check-code-traces.py -v        # 详细输出
  python scripts/check-code-traces.py --ci      # CI 模式（仅输出 文件名:行号，非零退出码）

退出码：
  0 — 全部通过（无可报痕迹）
  1 — 发现高置信度痕迹（HIGH/ORIGIN/VERSION）
  2 — 发现任务编号/章节编号/架构约束代号/语义命名暗号引用
      （CODE/IDENT/CHAPTER/ROUND/MAGIC/DASHTASK/UNDERSCORE），应从注释/标识符中移除
      （CHAPTER：注释中用数字章节号"N 章"/"第 N 章"指代报告具体章节，
      章节合并/重排后数字即失效，须改用语义章节名「X」章；
      ROUND：注释中用"第 N 轮"/"经 N 轮"/"N 轮"/"轮 N"指代开发迭代
      轮次，属迭代痕迹，须改用语义描述；
      MAGIC/DASHTASK/UNDERSCORE：注释中"字母+数字/字母-数字/字母_数字"
      组合（如 R11/F-1/F_1）属无语义魔法编号/疑似任务编号/疑似无意义
      代码，须改用语义名）
  3 — 仅 LOW 级别痕迹，建议人工复核
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享包（_traces_code / _checklib）
from _checklib import add_common_args  # noqa: E402
from _checklib import rel as rel_path  # noqa: E402,F401  # 统一相对路径展示（原面 re-export）
from _traces_code import (  # noqa: E402
    EXCLUDE_LINE,  # noqa: F401
    IDENTIFIER_PATTERNS,  # noqa: F401
    PATTERNS,  # noqa: F401
    REPO_ROOT,  # noqa: F401
    SCAN_DIRS,  # noqa: F401
    TEST_META_EXCLUDE,  # noqa: F401
    _COMPILED_CHAPTER_EXCLUDE,  # noqa: F401
    _COMPILED_ROUND_EXCLUDE,  # noqa: F401
    _chapter_excludes,  # noqa: F401
    _html_comment_lines,  # noqa: F401
    _is_chapter_excluded,  # noqa: F401
    _is_dash_excluded,  # noqa: F401
    _is_excluded,  # noqa: F401
    _is_magic_match_excluded,  # noqa: F401
    _is_round_excluded,  # noqa: F401
    _is_tool_self,  # noqa: F401
    _is_under_excluded,  # noqa: F401
    _iter_comment_lines,  # noqa: F401
    _js_comment_lines,  # noqa: F401
    _js_identifier_names,  # noqa: F401
    _magic_excludes,  # noqa: F401
    _py_comment_lines,  # noqa: F401
    _py_identifier_names,  # noqa: F401
    _round_excludes,  # noqa: F401
    _scan_core_layering,  # noqa: F401
    _scan_identifiers,  # noqa: F401
    _shell_comment_lines,  # noqa: F401
    scan_file,  # noqa: F401
)

#: 共享排除模式原面 re-export：测试与调用方仍按原脚本名访问（实现见 _traces_code）
__all__ = [
    "_COMPILED_CHAPTER_EXCLUDE",
    "_COMPILED_ROUND_EXCLUDE",
    "_chapter_excludes",
    "_is_chapter_excluded",
    "_is_round_excluded",
    "_round_excludes",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="扫描代码注释中的历史变更痕迹",
    )
    # 统一 CLI 契约（-v/--verbose + --ci）由 _checklib 提供，本脚本不自定义面；
    # 退出码仍走自身分级语义（0/1/2/3），见模块 docstring「退出码」。
    add_common_args(parser)
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
            if fpath.name in ("chart.min.js",):
                continue
            file_ref = rel_path(fpath)
            hits = scan_file(fpath, args.verbose)
            if not hits:
                continue

            if not args.ci:
                print(f"\n  {file_ref}")

            for lineno, cat, desc, text in hits:
                total_hits += 1
                summary[cat] = summary.get(cat, 0) + 1
                is_high = cat in ("HIGH", "ORIGIN", "VERSION")
                if is_high:
                    high_count += 1
                elif cat in ("CODE", "IDENT", "CHAPTER", "ROUND", "MAGIC", "DASHTASK", "UNDERSCORE"):
                    code_count += 1
                else:
                    low_count += 1

                if args.ci:
                    print(f"{file_ref}:{lineno} [{cat}] {desc} — {text}")
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
        print(f"    {code_count} 处任务编号/章节编号引用（CODE/IDENT/CHAPTER/ROUND），应从注释/标识符中移除")
        sys.exit(2)

    if low_count > 0:
        print(f"[!] 仅 {low_count} 处 LOW 级别痕迹（TODO/CHANGE/DEPR），建议人工复核")
        sys.exit(3)


if __name__ == "__main__":
    main()

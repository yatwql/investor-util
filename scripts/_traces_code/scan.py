"""check-code-traces 单文件扫描调度（痕迹/标识符/分层三条支路汇聚）。"""

from __future__ import annotations

import re
from pathlib import Path

from _traces_code.config import RULE_CARRIER_DIRS, SKIP_FILES, _is_tool_self
from _traces_code.exemptions import _is_chapter_excluded, _is_round_excluded
from _traces_code.extract import _iter_comment_lines, _scan_identifiers
from _traces_code.layers import _scan_core_layering
from _traces_code.patterns import (
    _COMPILED_PATTERNS,
    _PATTERNS_PREFILTER,
    _TASK_ID_RE,
    _is_dash_excluded,
    _is_excluded,
    _is_magic_match_excluded,
    _is_under_excluded,
)


def scan_file(fpath: Path, verbose: bool) -> list[tuple[int, str, str, str]]:
    """扫描单个文件，返回 [(行号, 分类, 模式说明, 行内容/标识符), ...]"""
    hits: list[tuple[int, str, str, str]] = []
    # 载体目录（规则定义字面量）与工具自身文件均为“尺子本身”，整文件跳过
    if fpath.name in SKIP_FILES or _is_tool_self(fpath.name) or RULE_CARRIER_DIRS.intersection(fpath.parts):
        return hits

    is_test_file = "src/test/" in fpath.as_posix()
    for lineno, ctext in _iter_comment_lines(fpath):
        if not ctext.strip():
            continue
        # 任务编号硬禁止：注释/docstring 出现 rf-/plan-/R- 编号一律检出，
        # 不被测试元描述/工具说明的整行豁免放行（任务代号只属内部计划表）
        if _TASK_ID_RE.search(ctext):
            hits.append((lineno, "CODE", "任务编号引用（如 rf-117、R-086）", ctext[:120]))
            continue
        if _is_excluded(ctext, test_file=is_test_file):
            if verbose:
                print(f"    (excluded) L{lineno}: {ctext[:80]}")
            continue

        if not _PATTERNS_PREFILTER.search(ctext):
            continue  # 并集预筛未命中：必然无 finding，跳过 89 次逐一匹配

        for pat, cat, desc in _COMPILED_PATTERNS:
            if cat == "CHAPTER" and _is_chapter_excluded(ctext):
                continue  # 章节计数/序数表述豁免，不影响其他模式
            if cat == "ROUND" and _is_round_excluded(ctext):
                continue  # 轮次计数/运行时表述豁免，不影响其他模式
            if cat == "DASHTASK" and _is_dash_excluded(ctext):
                continue  # 字母-数字合法领域值豁免（T-1 交易日等），不影响其他模式
            if cat == "UNDERSCORE" and _is_under_excluded(ctext):
                continue  # 字母_数字合法领域值豁免（小写语义短名），不影响其他模式
            if cat == "MAGIC":
                # 逐 token 豁免：同一行内合法场景标记（S1）与暗号代号（R11）并存时，
                # 仅豁免合法的 token，暗号仍会被检出（避免整行豁免掩盖暗号）。
                for m in re.finditer(pat, ctext):
                    if not _is_magic_match_excluded(ctext, m.start(), m.end()):
                        hits.append((lineno, cat, desc, ctext[:120]))
                        break  # 该行存在未豁免的 MAGIC 命中
                else:
                    continue  # 该行全部 MAGIC 命中均被合法领域值豁免，不影响其他模式
                break  # 已命中该行，不再检查后续模式
            if re.search(pat, ctext):
                hits.append((lineno, cat, desc, ctext[:120]))
                break  # first match only per line

    # 标识符扫描（变量/函数/类名任务代号，语义命名纪律）
    hits.extend(_scan_identifiers(fpath))

    # core → 上层分层守卫（core 是被依赖底座，反向 import 上层即层次倒置）
    hits.extend(_scan_core_layering(fpath))

    return hits

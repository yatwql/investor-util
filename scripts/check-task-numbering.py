#!/usr/bin/env python3
"""任务编号全局一致性检查脚本。

校验 plan- / rf- 两类任务编号是否与「编号源」标记一致，防止新增任务编号
与历史归档冲突（归档不回收、编号只增不回收）。

编号规则（见 CLAUDE.md「任务编号规范」）：
  - plan-{全局递增序号}（plan.md 计划项）
  - rf-{全局递增序号}（review-findings.md 自审问题）
  - 序号从 1 单调递增，已归档/已完成的序号不回收，跨文档引用必须带前缀

每类编号在对应管理文档头部维护一个「编号源」标记，记录**下一个可用编号**：
  - plan.md            → `plan-next = N`
  - review-findings.md → `rf-next = N`

校验逻辑：扫描当前管理文档 + 全部历史归档（docs-stm/archive/*/），取该
前缀实际出现过的最大编号，断言 `next` 严格大于它（即 next 是真正未用的）。
若 `next <= 已用最大` 或标记缺失，说明有人手工新增任务后忘了递增标记，
或标记初值写小——报错提示把 next 修正为「已用最大 + 1」。

用法：
  python scripts/check-task-numbering.py          # 检查全部（plan + rf）
  python scripts/check-task-numbering.py --kind plan
  python scripts/check-task-numbering.py --kind rf
  python scripts/check-task-numbering.py --ci     # CI 模式（只输出错误，退出码非零即失败）

退出码：
  0 — 全部通过
  1 — 存在违规
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANAGEMENTS_DIR = REPO_ROOT / "docs-stm" / "managements"
ARCHIVE_DIR = REPO_ROOT / "docs-stm" / "archive"

# 每类编号的配置：当前管理文档 + 编号源标记名
KINDS: dict[str, dict[str, str]] = {
    "plan": {
        "doc": "plan.md",
        "marker": "plan-next",
        "pattern": r"plan-\d+",
    },
    "rf": {
        "doc": "review-findings.md",
        "marker": "rf-next",
        "pattern": r"rf-\d+",
    },
}


def _all_numbering_files() -> list[Path]:
    """返回全部归档 review-findings/plan 文件（含当前管理文档）。"""
    files: list[Path] = []
    for archive in sorted(ARCHIVE_DIR.rglob("archived_*.md")):
        if "review-findings" in archive.name or "plan" in archive.name:
            files.append(archive)
    return files


def _read_next_marker(doc_path: Path, marker: str) -> int | None:
    """从文档头部解析「编号源」标记的 next 值；缺失/未命中返回 None。"""
    for line in doc_path.read_text(encoding="utf-8").splitlines()[:30]:
        m = re.search(rf"`{re.escape(marker)}\s*=\s*(\d+)`", line)
        if m:
            return int(m.group(1))
    return None


def _max_number_in(paths: list[Path], pattern: str) -> int | None:
    """在给定文件中收集某前缀全部编号，返回最大值；无匹配返回 None。"""
    nums: list[int] = []
    pat = re.compile(pattern)
    for fp in paths:
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        nums.extend(int(m.group(0).split("-")[1]) for m in pat.finditer(text))
    return max(nums) if nums else None


def check_kind(kind: str, ci_mode: bool) -> list[str]:
    """校验单个编号序列。返回违规列表（空=通过）。"""
    cfg = KINDS[kind]
    doc_path = MANAGEMENTS_DIR / cfg["doc"]
    next_val = _read_next_marker(doc_path, cfg["marker"])
    used_max = _max_number_in([doc_path, *_all_numbering_files()], cfg["pattern"])

    violations: list[str] = []
    if next_val is None:
        violations.append(f"{cfg['doc']}: 缺少编号源标记 `{cfg['marker']}`（应记录下一个可用编号）")
    elif used_max is None:
        violations.append(f"{cfg['doc']}: 未发现任何 {cfg['marker']} 编号，无法校验 next 初值")
    elif next_val <= used_max:
        violations.append(
            f"{cfg['doc']}: `{cfg['marker']} = {next_val}` 不晚于已用最大 {kind}-{used_max}，"
            f"新增编号会与历史冲突——请修正为 {kind}-{used_max + 1}"
        )
    elif not ci_mode:
        print(f"  [OK] {cfg['doc']} — {cfg['marker']} = {next_val} > 已用最大 {kind}-{used_max}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="任务编号（plan-/rf-）全局一致性检查",
    )
    parser.add_argument(
        "--kind",
        choices=sorted(KINDS),
        help="仅检查指定编号序列（默认全部）",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI 模式（只输出错误，退出码非零即失败）",
    )
    args = parser.parse_args()

    kinds = [args.kind] if args.kind else sorted(KINDS)

    if not args.ci:
        print(f"[..] 校验任务编号全局一致性（{', '.join(kinds)}）")

    all_violations: list[str] = []
    for kind in kinds:
        all_violations.extend(check_kind(kind, ci_mode=args.ci))

    if all_violations:
        if not args.ci:
            print("\n违规详情:")
        for v in all_violations:
            print(f"  [ERR] {v}")
        return 1

    if not args.ci:
        print("[OK] 全部编号序列通过，无历史冲突风险")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""`check-doc-drift` 目录树与统计表检查 —— `folders.md` 目录树双向比对 + 项目统计表数字核对。"""

from __future__ import annotations

import re
from pathlib import Path
from _checklib import REPO_ROOT, rel

from _doc_drift._shared import (
    _FOLDERS_MD,
    _MANAGEMENTS,
    _MANUALS,
    _README,
    _TREE_ROOTS,
    _collect_test_count,
    _count,
    _first_number,
    _is_generated,
    _split_table_row,
)


_TREE_ENTRY = re.compile(r"──\s+([^#]+?)\s*(?:#.*)?$")


def parse_tree_paths(doc_text: str) -> set[str]:
    """按缩进层级把 folders.md 的目录树还原为仓库相对路径集合。"""
    paths: set[str] = set()
    stack: list[tuple[int, str]] = []
    in_tree = False
    for line in doc_text.splitlines():
        if line.startswith("```"):
            in_tree = not in_tree
            continue
        if not in_tree or "── " not in line:
            continue
        prefix = line.split("── ", 1)[0]
        depth = len(re.findall(r"│|    ", prefix))
        name = line.split("── ", 1)[1].split("#")[0].strip()
        if not name:
            continue
        if name.endswith("/"):
            dirname = name.rstrip("/")
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, dirname))
        else:
            paths.add("/".join([p for d, p in stack if d < depth] + [name]))
    return paths


def _actual_files() -> set[str]:
    files: set[str] = set()
    for root in _TREE_ROOTS:
        for p in (REPO_ROOT / root).rglob("*"):
            if not p.is_file():
                continue
            rel_path = rel(p)
            if _is_generated(rel_path):
                continue
            files.add(rel_path)
    return files


def check_dir_tree(doc_text: str) -> list[str]:
    findings: list[str] = []
    tree = parse_tree_paths(doc_text)
    actual = _actual_files()
    for path_text in sorted(actual - tree):
        findings.append(f"{rel(_FOLDERS_MD)}: 目录树缺少 `{path_text}`（实际存在，须补条目）")
    for path_text in sorted(tree - actual):
        if any(path_text == root or path_text.startswith(root + "/") for root in _TREE_ROOTS):
            findings.append(f"{rel(_FOLDERS_MD)}: 目录树条目 `{path_text}` 在磁盘上不存在")
    return findings


_STATS_ROW = re.compile(r"^\|")


def _stats_actual() -> dict[str, tuple[int, int]]:
    """各统计行的实测 ``(文件数, 行数)``（键与 folders.md 行标签一致）。"""
    main = [p for p in (REPO_ROOT / "src").rglob("*.py") if "src/test/" not in rel(p)]
    tests = list((REPO_ROOT / "src" / "test").rglob("*.py"))
    # scripts/ 含 _test_runner 内部实现包：统计递归计入（与 folders.md「辅助脚本」口径一致）
    scripts = sorted((REPO_ROOT / "scripts").rglob("*.py"))
    tmpl = list((REPO_ROOT / "src" / "static" / "tmpl").rglob("*.html"))
    svg = sorted((REPO_ROOT / "src" / "static").glob("*.svg"))
    manuals = sorted(_MANUALS.glob("*.md"))
    mgmt = sorted(_MANAGEMENTS.glob("*.md"))
    archive = sorted((REPO_ROOT / "docs" / "archive").rglob("*.md"))
    plan = sorted((REPO_ROOT / "docs" / "plan").glob("*.md"))
    readme = [_README]
    claude = [REPO_ROOT / "CLAUDE.md"]
    actual = {
        "主程序代码": _count(main),
        "HTML 报告模板": _count(tmpl),
        "架构图示": _count(svg),
        "辅助脚本": _count(scripts),
        "测试代码": _count(tests),
        "用户文档": _count(readme + manuals),
        "manuals/": _count(manuals),
        "项目文档": _count(claude + mgmt + archive + plan),
        "managements/": _count(mgmt),
        "archive/": _count(archive),
        "plan/": _count(plan),
    }
    src_total = tuple(
        sum(v[i] for k, v in actual.items() if k in ("主程序代码", "HTML 报告模板", "架构图示", "辅助脚本"))
        for i in (0, 1)
    )
    actual["源代码合计"] = src_total
    return actual


def check_project_stats(
    doc_text: str, with_test_count: bool = False, snapshot: dict[str, int] | None = None
) -> list[str]:
    findings: list[str] = []
    actual = _stats_actual()
    test_count = snapshot.get("_总收集") if snapshot else (_collect_test_count() if with_test_count else None)
    for line_no, line in enumerate(doc_text.splitlines(), 1):
        cells = _split_table_row(line)
        if cells is None:
            continue
        label = cells[0].lstrip("├└─ ").strip()
        got_files = _first_number(cells[2])
        got_lines = _first_number(cells[3])
        if label == "测试用例":
            if test_count is None or got_lines is None:
                continue
            if got_lines != str(test_count):
                findings.append(
                    f"{rel(_FOLDERS_MD)}:{line_no}: 测试用例数 {got_lines} 与 collect-test-coverage 快照 {test_count} 不一致"
                )
            continue
        if label not in actual:
            continue
        exp_files, exp_lines = actual[label]
        if got_files is not None and got_files != str(exp_files):
            findings.append(f"{rel(_FOLDERS_MD)}:{line_no}: 「{label}」文件数 {got_files} 与实测 {exp_files} 不一致")
        if got_lines is not None and got_lines != str(exp_lines):
            findings.append(f"{rel(_FOLDERS_MD)}:{line_no}: 「{label}」行数 {got_lines} 与实测 {exp_lines} 不一致")
    return findings


def _reformat_number(value: int, style: str) -> str:
    """按原单元格的数字风格回写：原带千分位 → 千分位，否则纯正整数。"""
    return f"{value:,}" if "," in style else str(value)


def sync_project_stats(
    doc_path: Path | None = None,
    *,
    actual: dict[str, tuple[int, int]] | None = None,
    test_count: int | None = None,
) -> list[str]:
    """把实测的统计表数字回写 `folders.md`（`check-doc-drift --sync` 自动同步）。

    针对的是「统计表登记数字 vs 实测」类漂移 —— 该类漂移是全仓 CI 最高频的红源
    （changelog/自审记录每补一行、测试用例每增删，实测行数即变，人工同步必漏）。
    回写只替换数字单元格（保留千分位风格与其余文字），不改说明文字、不触碰版本
    演进对照表（其标签口径不同，不会精确匹配）与任何需要人工判断的条目。

    Args:
        doc_path: `folders.md` 路径（默认仓库登记路径，测试注入临时路径）
        actual: 实测 `(文件数, 行数)` 表(默认 `_stats_actual()`，测试注入 fixture)
        test_count: pytest 收集的用例数（默认 `_collect_test_count()`，测试注入）

    Returns:
        逐条应用的变更描述（无漂移时为空列表）。
    """
    path = doc_path or _FOLDERS_MD
    if not path.exists():
        return []
    live_actual = actual if actual is not None else _stats_actual()
    live_test = test_count if test_count is not None else _collect_test_count()
    lines_out: list[str] = []
    applied: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        rows = _split_table_row(line)
        if rows is None:
            lines_out.append(line)
            continue
        label = rows[0].lstrip("├└─ ").strip()
        if label in live_actual and len(rows) > 3:
            exp_files, exp_lines = live_actual[label]
            new_line = line
            changed = False
            for idx, exp_value in ((2, exp_files), (3, exp_lines)):
                rows = _split_table_row(new_line)
                if rows is None:
                    break
                got = _first_number(rows[idx])
                if got is not None and got != str(exp_value):
                    new_line = _sync_cell_number(new_line, idx, exp_value)
                    changed = True
                    applied.append(f"「{label}」{'文件数' if idx == 2 else '行数'} {got} → {exp_value}")
            line = new_line
            del changed
        elif label == "测试用例" and live_test is not None and len(rows) > 3:
            got = _first_number(rows[3])
            if got is not None and got != str(live_test):
                line = _sync_cell_number(line, 3, live_test)
                applied.append(f"「{label}」用例数 {got} → {live_test}")
        lines_out.append(line)
    if applied:
        path.write_text("".join(lines_out), encoding="utf-8")
    return applied


def _sync_cell_number(line: str, cell_idx: int, new_value: int) -> str:
    """把表格行第 `cell_idx` 个单元格的首个数字替换为 `new_value`（保留原格式）。

    直接对**原始行**做定位替换（不经过 `_split_table_row` 的粗体剥离），
    保证 `**11**` / `11` / 带 `#` 注释等逐字风格原样保留。
    """
    suffix = "\n" if line.endswith("\n") else ""
    body = line.rstrip("\n")
    # 原始管道拆分（首尾去 `|`），位置与 _split_table_row 的单元格一致
    raw_parts = body.strip().strip("|").split("|")
    raw_parts = [p.strip() for p in raw_parts]
    if len(raw_parts) <= cell_idx:
        return line
    old_cell = raw_parts[cell_idx]
    num = re.search(r"[\d][\d,]*", old_cell)
    if not num:
        return line
    replacement = _reformat_number(new_value, num.group(0))
    raw_parts[cell_idx] = old_cell.replace(num.group(0), replacement, 1)
    return "| " + " | ".join(raw_parts) + " |" + suffix

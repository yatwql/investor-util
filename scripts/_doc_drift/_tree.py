"""`check-doc-drift` 目录树与统计表检查 —— `folders.md` 目录树双向比对 + 项目统计表数字核对。"""

from __future__ import annotations

import re
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
    archive = sorted((REPO_ROOT / "docs-stm" / "archive").rglob("*.md"))
    plan = sorted((REPO_ROOT / "docs-stm" / "plan").glob("*.md"))
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

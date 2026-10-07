"""`check-doc-drift` 目录树与统计表检查 —— `folders.md` 目录树双向比对 + 项目统计表数字核对。"""

from __future__ import annotations

import re
from pathlib import Path
from _checklib import REPO_ROOT, rel
from src.python.core.registry import _REPORT_SECTION_DEFAULT

from _doc_drift._shared import (
    _FOLDERS_MD,
    _MANAGEMENTS,
    _MANUALS,
    _README,
    _TECHNICAL_MD,
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


# ──章节-区块矩阵（technical.md §4.22，双端章内区块对账） ──────────────

_BLOCK_MATRIX_TITLE = "章节-区块矩阵"
#: 矩阵表头列关键字（列按表头文本定位，不依赖列序）
_BLOCK_KEY_HEADER = "章节"
_BLOCK_COUNT_HEADER = "HTML 区块数"
_BLOCK_PARTIAL_HEADER = "HTML 载体"
_BLOCK_MARKER_HEADER = "Excel 区块清单"
_BLOCK_MODULE_HEADER = "Excel 载体"
#: 计数占位（流式章/单表章不计数）
_NO_COUNT = "—"
#: 同一单元格内多项的分隔符（载体多文件用 ` + `，区块清单用 ` / `）
_MULTI_SEP = " + "
_MARKER_SEP = " / "
#: 序号标记字符集（HTML 区块计数口径，与 technical.md §4.22 口径说明同步）
_ORD_CN = "一二三四五六七八九十"
_ORD_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
_BLOCK_PARTIAL_DIR = REPO_ROOT / "src" / "static" / "tmpl" / "partials"
_BLOCK_SHEET_DIR = REPO_ROOT / "src" / "python" / "report"


def recount_html_blocks(partial_names: list[str]) -> int | None:
    """按矩阵口径重算章节 HTML 区块数。

    序号标记三源去重（并集）：block-title 标题首字符序号、`>` 后的加粗序号 div、
    结构注释 `<!-- ── 一、…`；有序号 → 计集合大小；无序号但有 block-title → 计去重
    标题数；两者皆无 → None（流式章，矩阵记「—」）。
    """
    ords: set[str] = set()
    titles: set[str] = set()
    for name in partial_names:
        text = (_BLOCK_PARTIAL_DIR / name).read_text(encoding="utf-8")
        for token in re.findall(r'class="block-title">\s*([^\s<{】）(（]{1,3})', text):
            if token[0] in _ORD_CN or token[0] in _ORD_CIRCLED:
                ords.add(token[0])
        ords.update(re.findall(rf">\s*([{_ORD_CIRCLED}])", text))
        ords.update(re.findall(rf"<!--\s*─+\s*([{_ORD_CN}{_ORD_CIRCLED}])、", text))
        titles.update(
            re.sub(r"\s+", " ", t).strip() for t in re.findall(r'class="block-title">(.*?)</div>', text, re.S)
        )
    if ords:
        return len(ords)
    if titles:
        return len(titles)
    return None


def _strip_cell(text: str) -> str:
    """去掉单元格内的 markdown 装饰（反引号/加粗），保留 CJK 与括号。"""
    return text.replace("`", "").replace("**", "").strip()


def parse_block_matrix(doc_text: str) -> tuple[list[dict[str, str]], list[str]]:
    """解析 §4.22 章节-区块矩阵表 → ``(行列表, 解析 findings)``。"""
    findings: list[str] = []
    lines = doc_text.splitlines()
    title_idx = next((i for i, ln in enumerate(lines) if ln.startswith("#") and _BLOCK_MATRIX_TITLE in ln), None)
    if title_idx is None:
        return [], [f"未找到「{_BLOCK_MATRIX_TITLE}」章节标题"]
    header_idx: int | None = None
    header_cells: list[str] | None = None
    for i in range(title_idx + 1, min(title_idx + 12, len(lines))):
        cells = _split_table_row(lines[i])
        if cells and any(_BLOCK_COUNT_HEADER in c for c in cells):
            header_idx, header_cells = i, cells
            break
    if header_idx is None or header_cells is None:
        return [], [f"「{_BLOCK_MATRIX_TITLE}」章节下未找到含「{_BLOCK_COUNT_HEADER}」列的表头"]

    def _col(keyword: str) -> int | None:
        return next((i for i, c in enumerate(header_cells or []) if keyword in c), None)

    cols = {
        "key": _col(_BLOCK_KEY_HEADER),
        "count": _col(_BLOCK_COUNT_HEADER),
        "partials": _col(_BLOCK_PARTIAL_HEADER),
        "markers": _col(_BLOCK_MARKER_HEADER),
        "module": _col(_BLOCK_MODULE_HEADER),
    }
    absent = [name for name, idx in cols.items() if idx is None]
    if absent:
        return [], [f"矩阵表头缺少列：{'、'.join(absent)}"]

    rows: list[dict[str, str]] = []
    for i in range(header_idx + 1, len(lines)):
        if not lines[i].startswith("|"):
            break
        cells = _split_table_row(lines[i]) or []
        if cells and all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells):
            continue  # 分隔行
        if any(cols[name] is not None and cols[name] >= len(cells) for name in cols):
            findings.append(f"{rel(_TECHNICAL_MD)}:{i + 1}: 矩阵行单元格数不足（须与表头列数一致）")
            continue
        rows.append(
            {
                "line": str(i + 1),
                "key": _strip_cell(cells[cols["key"]]),  # type: ignore[index]
                "count": _strip_cell(cells[cols["count"]]),  # type: ignore[index]
                "partials": _strip_cell(cells[cols["partials"]]),  # type: ignore[index]
                "markers": _strip_cell(cells[cols["markers"]]),  # type: ignore[index]
                "module": _strip_cell(cells[cols["module"]]),  # type: ignore[index]
            }
        )
    if not rows:
        findings.append(f"{rel(_TECHNICAL_MD)}:「{_BLOCK_MATRIX_TITLE}」表无数据行")
    return rows, findings


def check_block_matrix(doc_text: str) -> list[str]:
    """章节-区块矩阵 ↔ 实现：key 双向对注册表 / HTML 区块数重算 / Excel 清单逐串存在。"""
    findings: list[str] = []
    rows, findings = parse_block_matrix(doc_text)
    if findings and not rows:
        return findings

    reg_keys = [sec["key"] for sec in _REPORT_SECTION_DEFAULT]
    mat_keys = [r["key"] for r in rows]
    if len(mat_keys) != len(set(mat_keys)):
        dup = sorted({k for k in mat_keys if mat_keys.count(k) > 1})
        findings.append(f"{rel(_TECHNICAL_MD)}: 矩阵表章节 key 重复：{'、'.join(dup)}")
    for key in sorted(set(reg_keys) - set(mat_keys)):
        findings.append(f"{rel(_TECHNICAL_MD)}: 矩阵表缺少注册表章节 `{key}`（须补行）")
    for key in sorted(set(mat_keys) - set(reg_keys)):
        findings.append(f"{rel(_TECHNICAL_MD)}: 矩阵表章节 `{key}` 不在注册表（删行或改 key）")

    for row in rows:
        loc = f"{rel(_TECHNICAL_MD)}:{row['line']}"
        # HTML 区块数 ↔ partials 实测重算
        partials = [p for p in row["partials"].split(_MULTI_SEP) if p]
        missing = [p for p in partials if not (_BLOCK_PARTIAL_DIR / p).is_file()]
        if missing:
            findings.append(f"{loc}: 矩阵 HTML 载体不存在：{'、'.join(missing)}")
        else:
            got = recount_html_blocks(partials)
            count_cell = row["count"]
            want: int | None
            if count_cell == _NO_COUNT:
                want = None
            elif count_cell.isdigit():
                want = int(count_cell)
            else:
                findings.append(f"{loc}: HTML 区块数列应为数字或「{_NO_COUNT}」，实际「{count_cell}」")
                want = None
            if want != got:
                shown = _NO_COUNT if got is None else str(got)
                findings.append(f"{loc}: `{row['key']}` HTML 区块数 {count_cell} 与 partial 实测 {shown} 不一致")
        # Excel 区块清单 ↔ 载体模块逐串存在
        if row["markers"] == _NO_COUNT:
            continue
        modules = [m for m in row["module"].split(_MULTI_SEP) if m]
        missing_mods = [m for m in modules if not (_BLOCK_SHEET_DIR / m).is_file()]
        if missing_mods:
            findings.append(f"{loc}: 矩阵 Excel 载体不存在：{'、'.join(missing_mods)}")
            continue
        module_text = "\n".join((_BLOCK_SHEET_DIR / m).read_text(encoding="utf-8") for m in modules)
        for marker in [mk for mk in row["markers"].split(_MARKER_SEP) if mk]:
            if marker not in module_text:
                findings.append(
                    f"{loc}: `{row['key']}` Excel 区块「{marker}」在 {'、'.join(modules)} 中未找到（区块删除/改名须同步矩阵）"
                )
    return findings

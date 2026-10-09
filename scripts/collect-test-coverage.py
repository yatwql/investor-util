#!/usr/bin/env python3
"""测试覆盖计数收集脚本 — 供 test-coverage.md 快照更新。

只做 pytest --collect-only（收集测试项，**不执行测试**），
按 `_test_runner/modes.py` 的 marker 表达式现场编译谓词归类计数（与 `-m`
实跑同源，表达式仅在 MODES 定义一处），
输出各模式/子标记的项数，供 docs/managements/test-coverage.md 更新使用。

用法：
  python scripts/collect-test-coverage.py                    # 收集并输出全部分组统计
  python scripts/collect-test-coverage.py --update-docs      # 追加：按本次快照回写 test-coverage.md / folders.md 的计数行

说明：
  - 本脚本只收集不执行，测试体不会运行，耗时 ~2s（取决于套件规模）
  - 项数随版本迭代变化，属撰写时快照，精确计数以本脚本实时输出为准
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:  # noqa: E402
    sys.path.insert(0, str(_SCRIPTS_DIR))  # 同目录共享模块（_test_runner）

from _test_runner.modes import (  # noqa: E402
    MODES,
    UNIT_DOMAIN_LABELS,
    compile_marker_expr,
    mode_marker_expr,
)
from _checklib import rel  # noqa: E402
from _doc_drift._format import (  # noqa: E402
    _COUNT_CELL,
    _COUNT_NAME_ALIAS,
    _DOMAIN_LABEL_TO_MARKER,
    _TEST_COVERAGE_DOMAIN_ROW,
    _TEST_COVERAGE_ROW,
)
from _doc_drift._shared import (  # noqa: E402
    _FOLDERS_MD,
    _TEST_COVERAGE_MD,
    _split_table_row,
)

# 不列入输出的模式及理由（其余模式随 MODES 增删自动跟随，不手维护清单）：
#   all   — 全量已由「总收集: N」行表达，文档按别名 all → _总收集 对表
#   live  — pytest.ini addopts = `-m "not live"`，默认收集宇宙不含 live，计数恒为 0
_OMITTED_MODES: dict[str, str] = {
    "all": "全量已由『总收集: N』行表达",
    "live": '默认收集宇宙排除 live（pytest.ini addopts = -m "not live"），计数恒为 0',
}

# 模式 → 谓词：由 MODES 的 marker 表达式现场编译（表达式无第二份定义）
_MODE_PREDICATES: dict[str, object] = {
    name: compile_marker_expr(mode_marker_expr(name)) for name in MODES if name not in _OMITTED_MODES
}

# 分组标记清单（输出分节与 `--update-docs` 快照的分组单源；顺序即输出顺序）：
#   unit 子标记 12 项 / scenario 分组 16 项 / 跨类 4 项（llm 仅跨类节有，
#   edge·data·smoke 同时是模式名——两处计数谓词与裸标记判定已实测同值）
UNIT_SUBS: tuple[str, ...] = (
    "unit_providers",
    "unit_fetcher",
    "unit_llm",
    "unit_news",
    "unit_report",
    "unit_config",
    "unit_core",
    "unit_analysis",
    "unit_cli",
    "unit_ui",
    "unit_scripts",
    "unit_web",
)
SCEN_SUBS: tuple[str, ...] = (
    "scenario_basic",
    "scenario_resilience",
    "scenario_llm",
    "scenario_datetime",
    "scenario_perf",
    "scenario_security",
    "scenario_extreme",
    "scenario_stock",
    "scenario_fund",
    "scenario_mixed_accounts",
    "scenario_new_holdings",
    "scenario_cache_hit",
    "scenario_bond",
    "scenario_network_down",
    "scenario_single_holding",
    "scenario_zero_cost",
)
CROSS_SUBS: tuple[str, ...] = ("llm", "smoke", "edge", "data")

# pytest 在 collection 阶段填充：nodeid + markers 集合
collected: list[tuple[str, set[str]]] = []


class CollectPlugin:
    def pytest_collection_finish(self, session):
        collected.clear()
        for item in session.items:
            markers = {m.name for m in item.iter_markers()}
            collected.append((item.nodeid, markers))


def _collect(targets: list[str]) -> int:
    """运行 pytest --collect-only，填充 collected（抑制 collect输出），返回 pytest 退出码。

    ``targets`` 为空目录/文件列表：默认 ``["src/test/"]`` 整树；增量快照路径
    传变更文件列表（`_doc_drift/_shared.py::_run_collect`），收集语义同源。
    **退出码必须传递**：收集期校验报错（exit=4，如 conftest 标记纪律校验中断钩子链
    导致 ``-m not live`` 过滤未执行）时输出是未过滤的错数，消费方按非零拒收、
    不得当真值缓存或回写文档。
    """
    with redirect_stdout(io.StringIO()):
        code = pytest.main(
            [*targets, "--collect-only", "-q", "--disable-warnings"],
            plugins=[CollectPlugin()],
        )
    return int(code)


def _target_files(targets: list[str]) -> list[str]:
    """targets（文件或目录）展开为测试文件路径（补零计数用；live 除外）。

    形式与传入目标同形（目录参数 rglob 结果自带前缀、文件参数原样），保证与
    nodeid 前缀一致可归并；live 套件被 `pytest.ini` `-m "not live"` 恒不收集。
    """
    live = (REPO_ROOT / "src" / "test" / "live").resolve()
    out: set[str] = set()
    for t in targets:
        p = Path(t)
        if p.is_file():
            out.add(t)
            continue
        if not p.is_dir():
            continue
        for pat in ("test_*.py", "*_test.py"):
            for f in p.rglob(pat):
                if "__pycache__" in f.parts:
                    continue
                try:
                    if live in f.resolve().parents:
                        continue
                except OSError:
                    continue
                out.add(f.as_posix())
    return sorted(out)


def _build_snapshot() -> dict[str, int]:
    """本次收集 → 计数快照 ``{名: 数}``（键与 stdout 分节行一致，含 ``_总收集``）。

    键集合覆盖输出各分节的 `name: N` 行（模式 / unit 子标记 / scenario 子标记 /
    跨类 / 功能域标签），供 `update_docs` 回写与外部核对复用；同名键（edge /
    data / smoke / scenario_extreme 在模式行与后置分节各出现一次）按 stdout
    分节次序以后者为准，与 `_doc_drift/_shared._parse_collect_stdout` 的逐行
    后写语义一致（重叠四处谓词与裸标记判定实测同值）。
    """

    def count(sel) -> int:
        return sum(1 for _, m in collected if sel(m))

    snap: dict[str, int] = {"_总收集": len(collected)}
    for name, sel in _MODE_PREDICATES.items():
        snap[name] = count(sel)
    for s in UNIT_SUBS:
        snap[s] = count(lambda m, s=s: s in m)
    for s in SCEN_SUBS:
        snap[s] = count(lambda m, s=s: s in m)
    for s in CROSS_SUBS:
        snap[s] = count(lambda m, s=s: s in m)
    for marker, label in UNIT_DOMAIN_LABELS.items():
        snap[label] = snap[marker]
    return snap


def _replace_first_number(raw_cell: str, value: int) -> tuple[str, str] | None:
    """替换单元格内首个数字串为 value（保留粗体/千分位/前后缀），无数字返回 None。"""
    m = re.search(r"\d[\d,]*", raw_cell)
    if not m:
        return None
    new_num = f"{value:,}" if "," in m.group(0) else str(value)
    return raw_cell[: m.start()] + new_num + raw_cell[m.end() :], m.group(0)


def _rewrite_count_line(line: str, value: int) -> tuple[str, str] | None:
    """计数行首个计数单元格替换 → ``(新行, 旧计数字)``；无计数单元格返回 None。

    单元格判定与位次复用 `check-doc-drift` 的 `_COUNT_CELL`（标签格后首个整格
    匹配计数形的格），保证「写入的格 = 核对读的格」；行首必须为 `|`（两类行
    正则均锚定列首）以保证原始格位对齐。
    """
    if not line.startswith("|"):
        return None
    raw_cells = line.split("|")
    for i, cell in enumerate(line.strip().strip("|").split("|")):
        if i == 0 or not _COUNT_CELL.match(cell.strip()):
            continue
        pair = _replace_first_number(raw_cells[i + 1], value)
        if pair is None:
            return None
        raw_cells[i + 1] = pair[0]
        return "|".join(raw_cells), pair[1]
    return None


def update_docs(snapshot: dict[str, int]) -> list[str]:
    """按快照回写 `test-coverage.md` 计数行与 `folders.md` 测试用例数 → 变更描述列表。

    行匹配/标签映射复用 `check-doc-drift` 原语（`_TEST_COVERAGE_ROW` /
    `_TEST_COVERAGE_DOMAIN_ROW` / `_COUNT_NAME_ALIAS` / `_DOMAIN_LABEL_TO_MARKER` /
    `_split_table_row`），只改计数数字、粗体与千分位原样保留——比对域与核对函数
    同构（反引号标记行 + 能映射到标记的加粗标签行，不限章内外；未映射标签不动），
    写后必然通过 `check_test_coverage_counts`。全程显式 encoding。
    """
    changes: list[str] = []
    # ── test-coverage.md：反引号标记行 + 已映射标签加粗行（与核对函数同构）──
    text = _TEST_COVERAGE_MD.read_text(encoding="utf-8")
    out: list[str] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        name: str | None = None
        m = _TEST_COVERAGE_ROW.match(line)
        if m:
            name = _COUNT_NAME_ALIAS.get(m.group(1), m.group(1))
        else:
            dm = _TEST_COVERAGE_DOMAIN_ROW.match(line)
            if dm:
                name = _DOMAIN_LABEL_TO_MARKER.get(dm.group(1).strip())
        if name and name in snapshot:
            rewritten = _rewrite_count_line(line, snapshot[name])
            if rewritten is not None and rewritten[0] != line:
                changes.append(f"{rel(_TEST_COVERAGE_MD)}:{line_no}: {name} {rewritten[1]} → {snapshot[name]}")
                line = rewritten[0]
        out.append(line)
    new_text = "\n".join(out) + ("\n" if text.endswith("\n") else "")
    if new_text != text:
        _TEST_COVERAGE_MD.write_text(new_text, encoding="utf-8")

    # ── folders.md：项目统计表「测试用例」行（计数列形如 `9,750 个`）──
    ftext = _FOLDERS_MD.read_text(encoding="utf-8")
    fout: list[str] = []
    for line_no, line in enumerate(ftext.splitlines(), 1):
        cells = _split_table_row(line)
        if cells and cells[0] == "测试用例" and line.startswith("|"):
            raw_cells = line.split("|")
            pair = _replace_first_number(raw_cells[4], snapshot["_总收集"])
            if pair is not None and pair[0] != raw_cells[4]:
                raw_cells[4] = pair[0]
                changes.append(f"{rel(_FOLDERS_MD)}:{line_no}: 测试用例 {pair[1]} → {snapshot['_总收集']}")
                line = "|".join(raw_cells)
        fout.append(line)
    new_ftext = "\n".join(fout) + ("\n" if ftext.endswith("\n") else "")
    if new_ftext != ftext:
        _FOLDERS_MD.write_text(new_ftext, encoding="utf-8")
    return changes


def main() -> None:
    # 输出强制 UTF-8：中文分组名在 cp936 Windows 上会按 GBK 编码写出，
    # 而消费方（`_doc_drift/_shared.py::_collect_test_snapshot`）按 UTF-8 解码
    # → UnicodeDecodeError（与仓库「文本 I/O 显式 encoding」纪律一致）。
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="测试覆盖计数收集（pytest --collect-only 快照，供 test-coverage.md 更新）"
    )
    parser.add_argument("targets", nargs="*", help="测试文件或目录（缺省整树 src/test/）")
    parser.add_argument(
        "--update-docs", action="store_true", help="按本次快照回写 test-coverage.md / folders.md 计数行"
    )
    args = parser.parse_args()
    targets = args.targets or ["src/test/"]
    exit_code = _collect(targets)
    snapshot = _build_snapshot()

    print(f"\n总收集: {snapshot['_总收集']} 项\n")

    # ── 模式对应测试量（谓词由 test-runner MODES 的 marker 表达式现场编译，
    #    与 -m 实跑同一求值器；表达式只在 _test_runner/modes.py 定义一处）──
    print("### 模式对应测试量")
    for name in _MODE_PREDICATES:
        print(f"{name}: {snapshot[name]}")

    # ── unit 子标记 ──
    print("\n### unit 子标记")
    for s in UNIT_SUBS:
        print(f"{s}: {snapshot[s]}")

    # ── scenario 分组标记 ──
    print("\n### scenario 子标记")
    for s in SCEN_SUBS:
        print(f"{s}: {snapshot[s]}")

    # ── 跨类标记 ──
    print("\n### 跨类标记")
    for s in CROSS_SUBS:
        print(f"{s}: {snapshot[s]}")

    # ── 功能域（unit 子标记聚合，标签映射单一来源见 _test_runner.modes）──
    print("\n### 功能域（unit 子标记聚合）")
    for marker, label in UNIT_DOMAIN_LABELS.items():
        print(f"{label}: {snapshot[marker]}")

    # ── unit 文件分布（供功能域表文件级参考）──
    print("\n### unit 文件分布（按文件，含所属 unit 子标记）")
    by_unit_file: Counter[str] = Counter()
    unit_file_markers: dict[str, set[str]] = {}
    for nodeid, m in collected:
        if "unit" in m:
            file_part = nodeid.split("::")[0].replace("src/test/", "")
            by_unit_file[file_part] += 1
            unit_file_markers.setdefault(file_part, set()).update(x for x in m if x.startswith("unit_"))
    for f, c in sorted(by_unit_file.items()):
        tags = ",".join(sorted(unit_file_markers[f]))
        print(f"{c:>4}  [{tags}]  {f}")

    # ── scenario 文件分布（供场景分组表文件级参考）──
    print("\n### scenario 文件分布")
    by_file: Counter[str] = Counter()
    for nodeid, m in collected:
        if "scenario" in m or "scenario_extreme" in m:
            file_part = nodeid.split("::")[0]
            by_file[file_part.replace("src/test/", "")] += 1
    for f, c in sorted(by_file.items()):
        print(f"{c:>4}  {f}")

    # ── 逐文件收集计数（tab 分隔；含 0 计数文件，供 --sync 增量快照按文件复用/比对）──
    print("\n### 逐文件收集计数")
    per_file: Counter[str] = Counter()
    for nodeid, _m in collected:
        per_file[nodeid.split("::")[0]] += 1
    for f in _target_files(targets):
        per_file.setdefault(f, 0)
    for f in sorted(per_file):
        print(f"{f}\t{per_file[f]}")

    # ── --update-docs：仅正常收集（0/5）才回写，错数不落盘 ──
    if args.update_docs:
        if exit_code in (0, 5):
            changes = update_docs(snapshot)
            for c in changes:
                print(f"[更新] {c}")
            if changes:
                print(f"[OK] 已回写 {len(changes)} 处")
            else:
                print("[OK] 计数与文档一致，无需回写")
        else:
            print("[!] 收集非正常退出，跳过文档回写", file=sys.stderr)

    # 收集出错（如标记纪律校验中断钩子链 → live 过滤未执行）→ 非零退出，
    # 消费方（_doc_drift/_shared.py::_run_collect）按退出码拒收，不回写错数
    if exit_code not in (0, 5):  # 5 = NO_TESTS_COLLECTED（合法空收集）
        sys.exit(exit_code)


if __name__ == "__main__":
    main()

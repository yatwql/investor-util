#!/usr/bin/env python3
"""测试覆盖计数收集脚本 — 供 test-coverage.md 快照更新。

只做 pytest --collect-only（收集测试项，**不执行测试**），
按 `_test_runner/modes.py` 的 marker 表达式现场编译谓词归类计数（与 `-m`
实跑同源，表达式仅在 MODES 定义一处），
输出各模式/子标记的项数，供 docs/managements/test-coverage.md 更新使用。

用法：
  python scripts/collect-test-coverage.py        # 收集并输出全部分组统计

说明：
  - 本脚本只收集不执行，测试体不会运行，耗时 ~2s（取决于套件规模）
  - 项数随版本迭代变化，属撰写时快照，精确计数以本脚本实时输出为准
"""

from __future__ import annotations

import io
import sys
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:  # noqa: E402
    sys.path.insert(0, str(_SCRIPTS_DIR))  # 同目录共享模块（_test_runner）

from _test_runner.modes import MODES, compile_marker_expr, mode_marker_expr  # noqa: E402

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


def main() -> None:
    # 输出强制 UTF-8：中文分组名在 cp936 Windows 上会按 GBK 编码写出，
    # 而消费方（`_doc_drift/_shared.py::_collect_test_snapshot`）按 UTF-8 解码
    # → UnicodeDecodeError（与仓库「文本 I/O 显式 encoding」纪律一致）。
    sys.stdout.reconfigure(encoding="utf-8")
    targets = sys.argv[1:] or ["src/test/"]
    exit_code = _collect(targets)

    total = len(collected)
    print(f"\n总收集: {total} 项\n")

    def count(sel) -> int:
        return sum(1 for _, m in collected if sel(m))

    # ── 模式对应测试量（谓词由 test-runner MODES 的 marker 表达式现场编译，
    #    与 -m 实跑同一求值器；表达式只在 _test_runner/modes.py 定义一处）──
    modes = _MODE_PREDICATES
    print("### 模式对应测试量")
    for name, sel in modes.items():
        print(f"{name}: {count(sel)}")

    # ── unit 子标记 ──
    unit_subs = [
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
    ]
    print("\n### unit 子标记")
    for s in unit_subs:
        print(f"{s}: {count(lambda m, s=s: s in m)}")

    # ── scenario 分组标记 ──
    scen_subs = [
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
    ]
    print("\n### scenario 子标记")
    for s in scen_subs:
        print(f"{s}: {count(lambda m, s=s: s in m)}")

    # ── 跨类标记 ──
    print("\n### 跨类标记")
    for s in ["llm", "smoke", "edge", "data"]:
        print(f"{s}: {count(lambda m, s=s: s in m)}")

    # ── 功能域（unit 子标记聚合）──
    domain_map = {
        "unit_providers": "数据源 Provider",
        "unit_fetcher": "数据获取调度",
        "unit_news": "新闻处理",
        "unit_report": "报告生成",
        "unit_llm": "LLM 智能分析",
        "unit_config": "配置管理",
        "unit_core": "核心基础设施",
        "unit_analysis": "分析计算",
        "unit_cli": "CLI 命令行",
        "unit_ui": "TUI 交互",
        "unit_web": "Web 服务",
    }
    print("\n### 功能域（unit 子标记聚合）")
    for s, label in domain_map.items():
        print(f"{label}: {count(lambda m, s=s: s in m)}")

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

    # 收集出错（如标记纪律校验中断钩子链 → live 过滤未执行）→ 非零退出，
    # 消费方（_doc_drift/_shared.py::_run_collect）按退出码拒收，不回写错数
    if exit_code not in (0, 5):  # 5 = NO_TESTS_COLLECTED（合法空收集）
        sys.exit(exit_code)


if __name__ == "__main__":
    main()

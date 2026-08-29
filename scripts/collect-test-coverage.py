#!/usr/bin/env python3
"""测试覆盖计数收集脚本 — 供 test-coverage.md 快照更新。

只做 pytest --collect-only（收集测试项，**不执行测试**），
按 test-runner.py MODES 的 marker 表达式本地归类计数，
输出各模式/子标记的项数，供 docs-stm/managements/test-coverage.md 更新使用。

用法：
  python scripts/collect-test-coverage.py        # 收集并输出全部分组统计

说明：
  - 本脚本只收集不执行，测试体不会运行，耗时 ~2s（取决于套件规模）
  - 项数随版本迭代变化，属撰写时快照，精确计数以本脚本实时输出为准
"""

from __future__ import annotations

import io
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

# pytest 在 collection 阶段填充：nodeid + markers 集合
collected: list[tuple[str, set[str]]] = []


class CollectPlugin:
    def pytest_collection_finish(self, session):
        collected.clear()
        for item in session.items:
            markers = {m.name for m in item.iter_markers()}
            collected.append((item.nodeid, markers))


def _sel(markers: set[str], *names: str) -> bool:
    return any(n in markers for n in names)


def _collect() -> None:
    """运行 pytest --collect-only，填充 collected（抑制 collect 输出）。"""
    with redirect_stdout(io.StringIO()):
        pytest.main(
            ["src/test/", "--collect-only", "-q", "--disable-warnings"],
            plugins=[CollectPlugin()],
        )


def main() -> None:
    _collect()

    total = len(collected)
    print(f"\n总收集: {total} 项\n")

    def count(sel) -> int:
        return sum(1 for _, m in collected if sel(m))

    # ── 模式对应测试量（对齐 test-runner.py MODES marker 表达式）──
    modes = {
        "unit": lambda m: "unit" in m,
        "standard": lambda m: "unit" in m and "edge" not in m and "data" not in m,
        "scenario": lambda m: "scenario" in m,
        "regression": lambda m: "scenario" in m,
        "verify": lambda m: _sel(
            m,
            "unit_core",
            "unit_providers",
            "unit_fetcher",
            "unit_config",
            "unit_news",
            "unit_llm",
            "unit_analysis",
            "unit_scripts",
            "unit_web",
        ),
        "dev-verify": lambda m: (
            (
                _sel(
                    m,
                    "unit_core",
                    "unit_providers",
                    "unit_fetcher",
                    "unit_analysis",
                    "unit_scripts",
                    "unit_web",
                )
                and "edge" not in m
                and "data" not in m
            )
            or "scenario_basic" in m
        ),
        "integration": lambda m: "scenario" in m or "integration" in m,
        "edge": lambda m: "edge" in m,
        "data": lambda m: "data" in m,
        "all_no_unit": lambda m: "unit" not in m,
        "smoke": lambda m: "smoke" in m,
        "report": lambda m: "unit_report" in m,
        "scenario_extreme": lambda m: "scenario_extreme" in m,
        "perf": lambda m: "scenario_perf" in m,
        "security": lambda m: "scenario_security" in m,
    }
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


if __name__ == "__main__":
    main()

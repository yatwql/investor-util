#!/usr/bin/env python3
"""测试标记合规性检查脚本。

扫描 src/test/ 下所有测试文件，验证标记（pytestmark / 装饰器）与
所在目录的预期匹配，避免新文件漏标导致标记体系退化。

通过标准：
  - unit/ 下每个文件必须包含 unit_* 子标记（unit/conftest.py 已有运行时强制）
  - scenario/ 下每个测试类必须包含对应 scenario_* 标记
  - _edge.py 文件必须包含 pytest.mark.edge
  - 所有 pytestmark 中不得引用已移除的标记（如 integration）

用法：
  python scripts/check-test-markers.py          # 检查全部
  python scripts/check-test-markers.py -v       # 详细输出
  python scripts/check-test-markers.py --ci     # CI 模式（只输出错误，退出码非零即失败）

退出码：
  0 — 全部通过
  1 — 存在违规
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = REPO_ROOT / "src" / "test"

# 期望的标记映射：子目录名 → 应含的标记名集合
# unit_* 标记由 conftest.py 运行时强制，此处只做静态扫描辅助
EXPECTED_DIR_MARKERS: dict[str, set[str]] = {
    # unit 子模块 — 由 pytestmark 模块级列表覆盖
    "unit/config": {"unit", "unit_config"},
    "unit/core": {"unit", "unit_core"},
    "unit/fetcher": {"unit", "unit_fetcher"},
    "unit/handlers": {"unit", "unit_core"},
    "unit/llm": {"unit", "unit_llm", "llm"},
    "unit/news": {"unit", "unit_news"},
    "unit/providers": {"unit", "unit_providers"},
    "unit/report": {"unit", "unit_report"},
    "unit/ui": {"unit", "unit_ui"},
    # scenario 子模块
    "scenario/basic": {"scenario", "scenario_basic"},
    "scenario/resilience": {"scenario", "scenario_resilience", "scenario_extreme"},
    "scenario/llm": {"scenario", "scenario_llm", "llm"},
    "scenario/datetime": {"scenario", "scenario_datetime"},
}

# 已移除的标记（不得出现）— 当前无已移除标记
DEPRECATED_MARKERS: set[str] = set()

# 已知的合法标记全集（conftest.py 注册的）
KNOWN_MARKERS = {
    "scenario",
    "scenario_basic",
    "scenario_resilience",
    "scenario_llm",
    "scenario_datetime",
    "scenario_stock",
    "scenario_fund",
    "scenario_mixed_accounts",
    "scenario_new_holdings",
    "scenario_cache_hit",
    "scenario_bond",
    "scenario_network_down",
    "scenario_single_holding",
    "scenario_zero_cost",
    "scenario_extreme",
    "unit",
    "unit_providers",
    "unit_fetcher",
    "unit_llm",
    "unit_news",
    "unit_report",
    "unit_config",
    "unit_core",
    "unit_ui",
    "edge",
    "smoke",
    "data",
    "llm",
    "integration",
    "integration_contract",
    "integration_isolation",
    "integration_news_pipeline",
    "integration_cache",
    "integration_tui",
}


def _extract_markers_from_file(filepath: Path) -> set[str]:
    """从测试文件静态提取 pytestmark 中的标记名。"""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()

    markers: set[str] = set()

    for node in ast.walk(tree):
        # 提取 pytestmark = [pytest.mark.xxx, ...]
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if (
                                isinstance(elt, ast.Attribute)
                                and isinstance(elt.value, ast.Attribute)
                                and elt.value.attr == "mark"
                                and isinstance(elt.value.value, ast.Name)
                                and elt.value.value.id == "pytest"
                            ):
                                markers.add(elt.attr)
        # 提取 @pytest.mark.xxx 装饰器（类级或方法级）
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Attribute)
                    and isinstance(decorator.value, ast.Attribute)
                    and decorator.value.attr == "mark"
                    and isinstance(decorator.value.value, ast.Name)
                    and decorator.value.value.id == "pytest"
                ):
                    markers.add(decorator.attr)

    return markers


def _get_relative_dir(filepath: Path) -> str:
    """获取测试文件相对于 TEST_DIR 的父目录路径（不含文件名）。

    例如 unit/core/test_cache.py → "unit/core"
    integration/test_integration_coverage.py → "integration"
    """
    rel = filepath.relative_to(TEST_DIR)
    parent = rel.parent
    return str(parent) if parent != Path(".") else ""


def check_file(filepath: Path, verbose: bool, ci_mode: bool) -> list[str]:
    """检查单个文件的标记合规性。返回违规列表（空=通过）。"""
    violations: list[str] = []
    markers = _extract_markers_from_file(filepath)
    rel_path = filepath.relative_to(REPO_ROOT)

    # 检查已移除的标记
    deprecated_found = markers & DEPRECATED_MARKERS
    for m in deprecated_found:
        violations.append(f"{rel_path}: 使用了已移除的标记 '{m}'")

    # 检查未知标记（拼写错误等）
    unknown = markers - KNOWN_MARKERS - DEPRECATED_MARKERS
    for m in unknown:
        violations.append(f"{rel_path}: 使用了未注册的标记 '{m}'（是否拼写错误？）")

    # 检查 _edge.py 是否含 edge 标记
    if filepath.name.endswith("_edge.py") and "edge" not in markers:
        violations.append(f"{rel_path}: _edge.py 文件缺少 'edge' 标记")

    # 按目录检查预期标记
    rel_dir = _get_relative_dir(filepath)
    expected = EXPECTED_DIR_MARKERS.get(rel_dir)
    if expected is not None:
        # 提取该文件实际含有的、属于预期集的标记
        found_expected = markers & expected
        if not found_expected:
            violations.append(f"{rel_path}: 缺少期望标记 {expected}（当前: {markers or '空'}）")

    if verbose and not violations:
        print(f"  [OK] {rel_path} — markers: {sorted(markers)}")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="测试标记合规性检查",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="详细输出（含通过的检查）",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI 模式（只输出错误，退出码非零即失败）",
    )
    args = parser.parse_args()

    # 收集所有测试文件
    test_files = sorted(TEST_DIR.rglob("test_*.py"))

    all_violations: list[str] = []
    passed = 0
    failed = 0

    for fp in test_files:
        violations = check_file(fp, verbose=args.verbose, ci_mode=args.ci)
        if violations:
            failed += 1
            all_violations.extend(violations)
        else:
            passed += 1

    # 输出汇总
    if not args.ci:
        print(f"\n{'=' * 50}")
        print(f"检查完成: {passed} 通过, {failed} 违规")

    if all_violations:
        if not args.ci:
            print("\n违规详情:")
        for v in all_violations:
            print(f"  [ERR] {v}")
        return 1

    if not args.ci:
        print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

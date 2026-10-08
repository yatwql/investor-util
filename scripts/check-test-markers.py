#!/usr/bin/env python3
"""测试标记合规性检查脚本。

扫描 src/test/ 下所有测试文件，验证标记（pytestmark / 装饰器）与
所在目录的预期匹配，避免新文件漏标导致标记体系退化。

通过标准：
  - unit/ 下每个文件按目录期望须含对应 unit_* 子标记（unit/conftest.py 已有运行时强制）
  - scenario/ 下每个文件按目录期望须含对应 scenario_* 标记
  - _edge.py 文件必须包含 pytest.mark.edge
  - 标记须在 src/test/conftest.py 注册集内（`KNOWN_MARKERS` 由该文件 AST 派生，conftest 新增标记自动跟随）
  - `DEPRECATED_MARKERS` 登记的已移除标记不得出现（当前登记集为空）

用法：
  python scripts/check-test-markers.py          # 检查全部
  python scripts/check-test-markers.py -v       # 详细输出
  python scripts/check-test-markers.py --ci     # CI 模式（只输出错误，退出码非零即失败）

退出码：
  0 — 全部通过
  2 — 存在违规（与 _checklib.report 返回值域一致）
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享设施（_checklib）
from _checklib import REPO_ROOT, add_common_args, rel, report  # noqa: E402,F401

TEST_DIR = REPO_ROOT / "src" / "test"
#: 标记注册的单一事实来源（`pytest_configure` 里的 `addinivalue_line("markers", …)`）
CONFTEST_PATH = REPO_ROOT / "src" / "test" / "conftest.py"

# 期望的标记映射：子目录名 → 应含的标记名集合
# 目录结构绑定：键必须是 `src/test/` 下真实存在的子目录（unit/* 与 scenario/* 全覆盖，
# 由单测双向校验）；子集语义是「至少命中其一」，故 `unit/handlers` 取 `unit_core`（该目录无专属标记）。
EXPECTED_DIR_MARKERS: dict[str, set[str]] = {
    # unit 子模块 — 由 pytestmark 模块级列表覆盖
    "unit/analysis": {"unit", "unit_analysis"},
    "unit/cache": {"unit", "unit_core"},
    "unit/cli": {"unit", "unit_cli"},
    "unit/config": {"unit", "unit_config"},
    "unit/core": {"unit", "unit_core"},
    "unit/fetcher": {"unit", "unit_fetcher"},
    "unit/handlers": {"unit", "unit_core"},
    "unit/llm": {"unit", "unit_llm", "llm"},
    "unit/news": {"unit", "unit_news"},
    "unit/providers": {"unit", "unit_providers"},
    "unit/report": {"unit", "unit_report"},
    "unit/scripts": {"unit", "unit_scripts"},
    "unit/startup": {"unit", "unit_ui"},
    "unit/ui": {"unit", "unit_ui"},
    "unit/web": {"unit", "unit_web"},
    # scenario 子模块
    "scenario/basic": {"scenario", "scenario_basic"},
    "scenario/datetime": {"scenario", "scenario_datetime"},
    "scenario/llm": {"scenario", "scenario_llm", "llm"},
    "scenario/perf": {"scenario", "scenario_perf"},
    "scenario/resilience": {"scenario", "scenario_resilience", "scenario_extreme"},
    "scenario/security": {"scenario", "scenario_security"},
}

# 已移除的标记（不得出现）— 当前无已移除标记
DEPRECATED_MARKERS: set[str] = set()


def registered_markers(conftest_path: Path = CONFTEST_PATH) -> set[str]:
    """从 `conftest.py` 的 `pytest_configure` 提取 `addinivalue_line("markers", …)` 注册的标记名。

    AST 解析（不执行 conftest），值取 `"名称: 说明"` 的冒号前部分；多行调用与相邻字符串
    字面量拼接由 `ast` 天然处理。标记清单只此一处事实源，conftest 新增/删除标记后本脚本
    自动跟随，不再靠人肉对表。
    """
    tree = ast.parse(conftest_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "addinivalue_line" or len(node.args) < 2:
            continue
        group, value = node.args[0], node.args[1]
        if not isinstance(group, ast.Constant) or group.value != "markers":
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.strip():
            names.add(value.value.split(":", 1)[0].strip())
    return names


#: 已知的合法标记全集（与 src/test/conftest.py 注册集同源派生，见 `registered_markers`）
KNOWN_MARKERS: set[str] = registered_markers()


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
    rel_path = rel(filepath)

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
    add_common_args(parser)
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

    return report(all_violations, "全部通过。", ci=args.ci, fail_message=f"检查完成: {passed} 通过, {{n}} 违规")


if __name__ == "__main__":
    sys.exit(main())

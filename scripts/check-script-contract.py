#!/usr/bin/env python3
"""scripts/ 顶层脚本契约机检（观察期：不入 pre-commit 钩子与 CI，模式同 check-style-guardrails）。

四条规则覆盖 2026-10-08 scripts 核查中靠人肉逐案发现的契约偏离：

  ① [exit-code]  退出码声明：`check-*` 与 `_checklib.report` 消费方的 docstring「退出码」
                  节声明码集须 ⊆ {0, 2}（`_checklib.report` 返回值域）；
                  分级/环境缺失/事实源不可读等特例见 `_EXIT_CODE_WHITELIST`
  ② [cli-surface] 检查类 CLI 面：`check-*` 顶层脚本须调用 `_checklib.add_common_args`
                  （统一 `-v/--verbose` + `--ci`）；钩子入口见 `_CLI_SURFACE_EXEMPT`
  ③ [encoding]   文本 I/O 显式 encoding：`open()`（非二进制模式）、`Path.read_text/write_text`、
                  `subprocess` 文本模式均须显式 `encoding=`（cp936 Windows 静默编码头风险）
  ④ [test-coverage] 测试覆盖：顶层脚本须被 `src/test/` 下任一测试文件按文件名引用；
                  一次性工具见 `_UNTESTED_EXEMPT`

用法：
  python scripts/check-script-contract.py
  python scripts/check-script-contract.py -v       # 逐脚本打印通过项
  python scripts/check-script-contract.py --ci     # CI 模式：仅输出 文件:描述

退出码：
  0 — 全部通过
  2 — 发现契约偏离（与 _checklib.report 返回值域一致）
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, add_common_args, rel, report  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parent
TEST_DIR = REPO_ROOT / "src" / "test"

#: `_checklib.report` 返回值域：0 = 通过，2 = 发现 finding
_REPORT_EXIT_CODES = frozenset({0, 2})

#: 规则① 特例：声明码集超出返回值域但属设计内的脚本（键 = 脚本文件名，值 = 允许码集）
_EXIT_CODE_WHITELIST: dict[str, frozenset[int]] = {
    "check-code-traces.py": frozenset({0, 1, 2, 3}),  # 分级退出码：1 = HIGH，3 = 仅 LOW
    "check-doc-traces.py": frozenset({0, 1, 2}),  # 分级退出码：1 = HIGH，2 = 仅 LOW
    "check-svg.py": frozenset({0, 1, 2}),  # 1 = 环境缺失（像素子命令需 Pillow）
    "check-version-consistency.py": frozenset({0, 1, 2}),  # 1 = 事实源不可读
}

#: 规则② 特例：钩子入口读环境变量/stdin，无 `-v`/`--ci` CLI 面（内部自行调用 `--ci`）
_CLI_SURFACE_EXEMPT = frozenset({"check-task-numbering-hook.py"})

#: 规则④ 特例：一次性/人工运行的探测与采样工具，无对应测试
_UNTESTED_EXEMPT = frozenset(
    {
        "llm-hallucination-sampler.py",  # 一次性 LLM 幻觉率采样（薄 CLI，实现在 `_halluc_sampler/` 包）
        "probe-csi-factor-indices.py",  # 旧入口兼容垫片（委托 `probes/csi.py`）
        "probe-push2.py",  # 旧入口兼容垫片（委托 `probes/push2.py`）
    }
)

_EXIT_SECTION_MARKER = "退出码"


def top_level_scripts() -> list[Path]:
    """`scripts/` 下顶层脚本（`_` 前缀的共享设施不检）。"""
    return sorted(path for path in SCRIPTS_DIR.glob("*.py") if not path.name.startswith("_"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def declared_exit_codes(path: Path) -> set[int] | None:
    """docstring「退出码」节声明的码集；未声明返回 None（规则① 不作用于未声明者）。"""
    try:
        doc = ast.get_docstring(_parse(path))
    except SyntaxError:
        return None
    if not doc:
        return None
    # 认「退出码：」/"退出码:" 章节头（正文中如「退出码声明：」不带冒号紧邻，不会误匹配）
    marker = re.search(rf"{_EXIT_SECTION_MARKER}[:：]", doc)
    if marker is None:
        return None
    tail = doc[marker.end() :]
    # 只看本节：到下一个空行为止，避免把后续正文里的数字算进码集
    tail = tail.split("\n\n", 1)[0]
    return {int(digit) for digit in re.findall(r"(?<!\d)(\d)(?!\.\d)", tail)}


def uses_report_contract(path: Path) -> bool:
    """是否从 `_checklib` 导入 `report`（退出码由 report() 返回值驱动的脚本）。"""
    try:
        tree = _parse(path)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "_checklib":
            if any(alias.name == "report" for alias in node.names):
                return True
    return False


def calls_function(path: Path, func_name: str) -> bool:
    """是否调用了指定名字的函数（如 `add_common_args`）。"""
    try:
        tree = _parse(path)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name) and target.id == func_name:
            return True
        if isinstance(target, ast.Attribute) and target.attr == func_name:
            return True
    return False


def encoding_violations(path: Path) -> list[str]:
    """规则③：文本 I/O 缺显式 encoding 的位置清单。"""
    violations: list[str] = []
    try:
        tree = _parse(path)
    except SyntaxError:
        return violations
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        keywords = {kw.arg: kw.value for kw in node.keywords}
        builtin_open = isinstance(func, ast.Name) and func.id == "open"
        attr_name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
        if builtin_open:
            if "encoding" in keywords:
                continue
            mode: str | None = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                mode = node.args[1].value
            if isinstance(keywords.get("mode"), ast.Constant) and isinstance(keywords["mode"].value, str):
                mode = keywords["mode"].value
            if mode is not None and "b" in mode:
                continue
            violations.append(f"L{node.lineno} open() 未声明 encoding=")
        elif attr_name in ("read_text", "write_text") and "encoding" not in keywords:
            violations.append(f"L{node.lineno} Path.{attr_name}() 未声明 encoding=")
        elif attr_name in ("run", "Popen", "check_output", "check_call"):
            if "encoding" not in keywords and ("text" in keywords or "universal_newlines" in keywords):
                violations.append(f"L{node.lineno} subprocess.{attr_name}(text=True) 未声明 encoding=")
    return violations


_TEST_TEXT_CACHE: dict[str, str] = {}


def has_test_reference(script_name: str) -> bool:
    """规则④：`src/test/` 下是否存在按文件名引用该脚本的测试文件。"""
    if not _TEST_TEXT_CACHE:
        for test_file in sorted(TEST_DIR.rglob("*.py")):
            if "__pycache__" in test_file.parts:
                continue
            _TEST_TEXT_CACHE[test_file.as_posix()] = test_file.read_text(encoding="utf-8")
    return any(script_name in text for text in _TEST_TEXT_CACHE.values())


def script_findings(path: Path) -> list[str]:
    """四条规则对该脚本的 finding（带规则标签，便于分规则聚合）。"""
    name = path.name
    findings: list[str] = []
    is_check = name.startswith("check-")

    if is_check or uses_report_contract(path):
        codes = declared_exit_codes(path)
        if codes is not None:
            allowed = _EXIT_CODE_WHITELIST.get(name, _REPORT_EXIT_CODES)
            if not codes <= allowed:
                findings.append(f"[exit-code] 声明码集 {sorted(codes)} 超出允许集 {sorted(allowed)}")

    if is_check and name not in _CLI_SURFACE_EXEMPT and not calls_function(path, "add_common_args"):
        findings.append("[cli-surface] 未调用 _checklib.add_common_args（缺统一 -v/--ci 面）")

    for detail in encoding_violations(path):
        findings.append(f"[encoding] {detail}")

    if name not in _UNTESTED_EXEMPT and not has_test_reference(name):
        findings.append("[test-coverage] src/test/ 下无按文件名引用本脚本的测试")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="scripts 顶层脚本契约机检（观察期，不入钩子与 CI）")
    add_common_args(parser)
    args = parser.parse_args()

    findings: list[str] = []
    for path in top_level_scripts():
        violations = script_findings(path)
        if args.verbose and not violations:
            print(f"  [OK] {path.name}")
        findings.extend(f"{rel(path)}: {item}" for item in violations)

    return report(
        findings,
        "[OK] scripts 顶层脚本契约全部通过（退出码 / CLI 面 / 文本编码 / 测试覆盖）",
        ci=args.ci,
        fail_message="[!] 发现 {n} 处 scripts 契约偏离，按提示修正后重试",
    )


if __name__ == "__main__":
    sys.exit(main())

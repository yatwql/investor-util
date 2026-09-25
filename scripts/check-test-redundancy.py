#!/usr/bin/env python3
"""测试用例冗余与无效检查（test redundancy / dead test check）—— 静态扫测试源，找「跑不到」「测不出」「同义反复」「重复」的用例。

四类检查（全部基于 AST 静态分析，不执行测试、不依赖网络）：

  A. **死用例（不可收集 / 被覆盖）** — pytest 永远不会执行的用例：
     - 同文件同类内同名重复定义（后者覆盖前者）
     - 类名不以 `Test` 开头的方法形式的 `test_*`（pytest 不收集）
     - `Test*` 类定义了 `__init__`（pytest 整类跳过）
  B. **无断言用例** — 既无 `assert`、也无 `pytest.raises/warns/fail`、也无 mock 断言（`assert_called*`）
  C. **完全重复用例** — 去掉 docstring 后「函数体 + 参数 + 装饰器」AST 归一化完全相同（同一被测对象同一断言）。
     为避免把「同名方法绑定不同被测对象」的并行覆盖误判为重复，凡函数体内出现无法解析的
     `self.<attr>` 间接调用（求值目标来自 setUp / 基类 / 外部模块）一律跳过比对。
  D. **自证用例（mock 替代被测对象）** — 同一用例内既 patch 了某个符号（`@patch("<mod>.<fn>")`），
     又直接调用同名函数，且把该 mock 的 `.return_value` 设成某个字面量、再用断言与该字面量比较——
     此时断言恒真，等于没测（常见于「顺手把被测函数也 patch 了」）。
  E. **硬编码「会演进的总数」** — 把需求/章节/开关等可增长集合的条数写死在断言里（如
     `assert len(req_ids) == 276`）。这类总数是文档真值来源的派生量，新增一条需求就会把测试打红，
     且与门禁脚本的全域覆盖断言职责重复。正确做法：结构关系断言（集合双向相等 / 域覆盖 / 序号连续）。结构关系断言（集合双向相等 / 域覆盖 / 序号连续）。

按设计排除：`src/test/live/`（`pytest.ini` 刻意排除的 opt-in 真网套件，默认不扫，`--include-live` 可纳入）、
`*_edge.py` 不特殊对待（同为测试，同样受检）。

用法：
  python scripts/check-test-redundancy.py                 # 四类全查
  python scripts/check-test-redundancy.py -v              # 详细输出（打印被跳过的间接调用用例数等）
  python scripts/check-test-redundancy.py --ci            # CI 模式：仅输出 文件:描述，退出码 2
  python scripts/check-test-redundancy.py --include-live  # 连带扫描 src/test/live/

退出码：
  0 — 全部通过
  2 — 发现死用例 / 无断言 / 完全重复 / 自证用例 / 硬编码演进总数
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, add_common_args, rel, report  # noqa: E402

_TEST_ROOT = REPO_ROOT / "src" / "test"
_LIVE_DIR = REPO_ROOT / "src" / "test" / "live"

#: mock 断言方法（`mock.assert_called_once*` 等）
_MOCK_ASSERT = re.compile(r"^assert_(called|any_call|has_calls|not_called)")
#: pytest 断言式调用（raises/warns 等，视为等价于 assert）
_PYTEST_ASSERT = frozenset({"raises", "warns", "fail", "deprecated_call"})
#: 常见的「被测对象句柄」类间接调用名（函数体内出现且无法解析时跳过重复比对）
_SUT_ATTRS = frozenset({"_call", "_run", "fn", "r", "sut", "proc", "target", "_target"})


class TestCase(NamedTuple):
    """一个测试用例（AST 视角）。"""

    path: Path
    class_name: str
    name: str
    lineno: int
    node: ast.FunctionDef | ast.AsyncFunctionDef
    cls: ast.ClassDef | None = None
    module: ast.Module | None = None


def _iter_test_files(include_live: bool) -> list[Path]:
    files = sorted(_TEST_ROOT.rglob("test_*.py"))
    if not include_live:
        files = [p for p in files if _LIVE_DIR not in p.parents]
    return files


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _dump(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=False, include_attributes=False)


def _class_attr_binding(cls: ast.ClassDef | None, attr: str) -> str | None:
    """解析类内 ``self.<attr>`` 的绑定目标（赋值式 / 方法返回式 / staticmethod）。"""
    if cls is None:
        return None
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            if stmt.targets[0].id == attr:
                return _dump(stmt.value)
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == attr:
            for inner in stmt.body:
                if isinstance(inner, ast.Return) and inner.value is not None:
                    return _dump(inner.value)
            return None
    return None


def _self_attrs(node: ast.AST) -> set[str]:
    return {
        n.attr
        for n in ast.walk(node)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"
    }


def _call_name(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")


def _assertion_in(node: ast.AST) -> tuple[bool, bool]:
    """本节点（含嵌套语句）内是否含断言式证据 / mock 断言。"""
    has_assert = False
    has_mock = False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assert):
            has_assert = True
        elif isinstance(sub, ast.Call):
            name = _call_name(sub)
            if _MOCK_ASSERT.match(name):
                has_assert = True
                has_mock = True
            elif name.startswith("assert") or name in _PYTEST_ASSERT:
                # unittest/numpy/mock 风格：assertEqual/assertTrue/assertIsNone/assert_called_* 与 fail/raises 等
                has_assert = True
    return has_assert, has_mock


def _same_scope_helpers(case: TestCase) -> dict[str, ast.AST]:
    """本文件/本类（含模块内基类）可解析的同名辅助函数：``name -> 函数节点``。"""
    helpers: dict[str, ast.AST] = {}
    if case.module is not None:
        for stmt in case.module.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                helpers[stmt.name] = stmt
        for cls in [n for n in ast.walk(case.module) if isinstance(n, ast.ClassDef)]:
            if (
                case.cls is None
                or cls is case.cls
                or any((isinstance(b, ast.Name) and b.id == cls.name) for b in case.cls.bases)
            ):
                for stmt in cls.body:
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        helpers.setdefault(stmt.name, stmt)
    return helpers


def _assertions(case: TestCase) -> tuple[bool, bool]:
    """返回 (是否有断言式证据, 是否有 mock 断言)。

    断言可以落在被测用例本体，也可以落在同文件/同类（含模块内基类）的辅助方法里
    （如 ``self._assert_pairs_contain(...)`` / ``self.fail(...)``）——两种情况都算有断言。
    """
    has_assert, has_mock = _assertion_in(case.node)
    if not has_assert:
        helpers = _same_scope_helpers(case)
        for name in {_call_name(c) for c in ast.walk(case.node) if isinstance(c, ast.Call)}:
            helper = helpers.get(name)
            if helper is not None and helper is not case.node:
                helper_assert, helper_mock = _assertion_in(helper)
                if helper_assert:
                    has_assert = True
                    has_mock = has_mock or helper_mock
                    break
    return has_assert, has_mock


def _patch_targets(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, str]]:
    """装饰器里的 ``@patch("a.b.c")`` → [(mock 参数名, 目标点分路径)]（按装饰器顺序对应参数尾）。"""
    targets: list[tuple[str, str]] = []
    params = [a.arg for a in node.args.args if a.arg != "self"]
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call) or not dec.args:
            continue
        func = dec.func
        fname = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        if fname != "patch":
            continue
        arg = dec.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            targets.append(("", arg.value))
    # patch 装饰器自下而上注入 → 参数表末尾起倒序对应
    for idx, (_, target) in enumerate(targets):
        param_index = len(params) - 1 - idx
        targets[idx] = (params[param_index] if 0 <= param_index < len(params) else "", target)
    return targets


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _mock_return_literals(node: ast.AST, mock_name: str) -> set[str]:
    """``<mock>.return_value = <字面量>`` 收集（只认单层，``mock.now.return_value`` 不算）。"""
    values: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assign) or len(sub.targets) != 1:
            continue
        tgt = sub.targets[0]
        if (
            isinstance(tgt, ast.Attribute)
            and tgt.attr == "return_value"
            and isinstance(tgt.value, ast.Name)
            and tgt.value.id == mock_name
            and isinstance(sub.value, ast.Constant)
        ):
            values.add(repr(sub.value.value))
    return values


def _asserted_literals(node: ast.AST) -> set[str]:
    """断言里出现的字面量（assert x == lit / assertEqual(x, lit)）。"""
    literals: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assert) and isinstance(sub.test, ast.Compare):
            for comp in sub.test.comparators:
                if isinstance(comp, ast.Constant):
                    literals.add(repr(comp.value))
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr
            in (
                "assertEqual",
                "assertEquals",
            )
        ):
            for arg in sub.args[1:]:
                if isinstance(arg, ast.Constant):
                    literals.add(repr(arg.value))
    return literals


def cases_in_module(path: Path, tree: ast.Module) -> list[TestCase]:
    """从单个已解析模块中提取全部测试用例（含所在类）。"""
    cls_of: dict[ast.AST, ast.ClassDef] = {}
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for stmt in cls.body:
            cls_of[stmt] = cls
    cases: list[TestCase] = []
    for node in ast.walk(tree):
        if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")):
            continue
        cls = cls_of.get(node)
        cases.append(
            TestCase(
                path=path,
                class_name=cls.name if cls else "",
                name=node.name,
                lineno=node.lineno,
                node=node,
                cls=cls,
                module=tree,
            )
        )
    return cases


def collect_cases(include_live: bool) -> tuple[list[TestCase], dict[Path, ast.Module], list[str]]:
    """收集全部测试用例，并顺带返回（解析失败的文件）提示。"""
    cases: list[TestCase] = []
    modules: dict[Path, ast.Module] = {}
    parse_errors: list[str] = []
    for path in _iter_test_files(include_live):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # 语法错误由 pytest 自己报，这里不重复报
            parse_errors.append(f"{rel(path)}: 无法解析（{exc.msg}）")
            continue
        modules[path] = tree
        cases.extend(cases_in_module(path, tree))
    return cases, modules, parse_errors


# ═══════════════════════════════════════════════════════════════
#  A. 死用例
# ═══════════════════════════════════════════════════════════════


def check_dead_tests(cases: list[TestCase], modules: dict[Path, ast.Module]) -> list[str]:
    findings: list[str] = []
    per_file: dict[Path, Counter[tuple[str, str]]] = defaultdict(Counter)
    for case in cases:
        per_file[case.path][(case.class_name, case.name)] += 1
    for case in cases:
        key = (case.class_name, case.name)
        if per_file[case.path][key] > 1 or case.class_name.startswith("非Test"):
            continue
        if case.class_name and not case.class_name.startswith("Test"):
            findings.append(
                f"{rel(case.path)}:{case.lineno}: 用例 {case.class_name}::{case.name} 所在类名不以 Test 开头，pytest 不会收集（死用例）"
            )
    # 同名重复（后者覆盖前者）
    for path, counter in per_file.items():
        for (cls, name), n in counter.items():
            if n > 1:
                findings.append(
                    f"{rel(path)}: {cls + '::' if cls else ''}{name} 在同一文件重复定义 {n} 次，仅最后一次会执行（其余为死用例）"
                )
    # Test* 类带 __init__
    for path, tree in modules.items():
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name.startswith("Test")]:
            has_init = any(
                isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name == "__init__" for b in cls.body
            )
            n_tests = sum(
                1
                for b in cls.body
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name.startswith("test")
            )
            if has_init and n_tests:
                findings.append(
                    f"{rel(path)}: Test 类 {cls.name} 定义了 __init__，pytest 整类跳过（{n_tests} 个用例为死用例）"
                )
    return findings


# ═══════════════════════════════════════════════════════════════
#  B. 无断言
# ═══════════════════════════════════════════════════════════════


def check_assertion_free(cases: list[TestCase]) -> list[str]:
    findings: list[str] = []
    for case in cases:
        has_assert, _ = _assertions(case)
        if not has_assert:
            findings.append(
                f"{rel(case.path)}:{case.lineno}: 用例 {case.name} 无任何断言（assert / pytest.raises / mock 断言均无）"
            )
    return findings


# ═══════════════════════════════════════════════════════════════
#  C. 完全重复
# ═══════════════════════════════════════════════════════════════


def body_signature(case: TestCase) -> str | None:
    """归一化指纹；含无法解析的 self 间接调用时返回 None（跳过比对，避免并行覆盖误报）。"""
    attrs = _self_attrs(case.node) & _SUT_ATTRS
    bindings: list[str] = []
    for attr in sorted(attrs):
        resolved = _class_attr_binding(case.cls, attr)
        if resolved is None:
            return None
        bindings.append(f"{attr}={resolved}")
    core = _strip_docstring(case.node.body)
    params = [a.arg for a in case.node.args.args]
    decorators = [_dump(d) for d in case.node.decorator_list]
    payload = f"{_dump(ast.Module(body=core, type_ignores=[]))}||{params}||{decorators}||{bindings}"
    return hashlib.sha1(payload.encode()).hexdigest()


def check_duplicate_bodies(cases: list[TestCase]) -> tuple[list[str], int]:
    """返回（findings, 被跳过的用例数）。"""
    findings: list[str] = []
    groups: dict[str, list[TestCase]] = defaultdict(list)
    skipped = 0
    for case in cases:
        sig = body_signature(case)
        if sig is None:
            skipped += 1
            continue
        groups[sig].append(case)
    for members in groups.values():
        if len(members) < 2:
            continue
        head = members[0]
        others = "、".join(f"{rel(m.path)}:{m.lineno} {m.name}" for m in members[1:])
        findings.append(
            f"{rel(head.path)}:{head.lineno}: 用例 {head.name} 与 {len(members) - 1} 个用例完全重复（函数体/参数/装饰器归一化后一致）：{others}"
        )
    return findings, skipped


# ═══════════════════════════════════════════════════════════════
#  D. 自证用例（mock 替代被测对象）
# ═══════════════════════════════════════════════════════════════


def check_self_fulfilling(cases: list[TestCase]) -> list[str]:
    findings: list[str] = []
    for case in cases:
        called = _called_names(case.node)
        asserted = _asserted_literals(case.node)
        if not called or not asserted:
            continue
        for mock_name, target in _patch_targets(case.node):
            short = target.split(".")[-1]
            if short not in called:
                continue
            mock_returns = _mock_return_literals(case.node, mock_name) if mock_name else set()
            if mock_returns & asserted:
                findings.append(
                    f"{rel(case.path)}:{case.lineno}: 用例 {case.name} patch 了被测函数 {target} 又把其 return_value 断言回原值（{sorted(mock_returns & asserted)}），断言恒真"
                )
    return findings


def check_hardcoded_evolving_totals(cases: list[TestCase]) -> list[str]:
    """E. **硬编码「会演进的总数」** —— 把需求/章节/开关等**可增长集合的条数**写死在断言里。

    为何是缺陷：这类总数是**文档真值来源的派生量**，随正常开发（新增一条需求/章节/开关）
    必然变化。写死后，良性变更会把测试打红（而它捕捉不到任何真实缺陷），反而阻碍演进；
    且它与门禁脚本（如 `check-requirement-trace` 的全域覆盖断言）**职责重复**。
    正确写法是断言**结构关系**（集合双向相等 / 域覆盖 / 序号连续），而非绝对条数。

    判定（保守，宁少报不误报）：
      - 仅看 `assert` 语句中形如 ``len(<x>) == <数字>`` 或 ``len(<x>) > <大数>`` 的比较；
      - 仅当**同一文件**内该 `len()` 实参名与需求 ID / 总数类语义相关时报告：
        实参名含 ``req_ids`` / ``requirement`` / ``section`` / ``switch`` / ``chapter`` 等，
        或断言所在文件路径含 ``requirement`` / ``registry`` / ``section``；
      - 忽略小数字（<= 3）：小集合的精确条数常为有意断言（如「两个 provider」）。
    """
    _SEMANTIC = (
        "requirement",
        "req_ids",
        "reqs",
        "section",
        "sections",
        "switch",
        "switches",
        "chapter",
        "chapters",
        "module",
        "modules",
        "domain",
        "domains",
        "panel",
        "panels",
    )
    findings: list[str] = []
    for case in cases:
        path_hint = "requirement" in str(case.path).lower() or "registry" in str(case.path).lower()
        for node in ast.walk(case.node):
            if not isinstance(node, ast.Assert):
                continue
            for cmp_node in ast.walk(node.test):
                if not isinstance(cmp_node, ast.Compare):
                    continue
                left = cmp_node.left
                if not (
                    isinstance(left, ast.Call)
                    and isinstance(left.func, ast.Name)
                    and left.func.id == "len"
                    and left.args
                ):
                    continue
                arg = left.args[0]
                arg_name = arg.id if isinstance(arg, ast.Name) else ast.unparse(arg)
                lowered = arg_name.lower()
                if not (path_hint or any(tok in lowered for tok in _SEMANTIC)):
                    continue
                for op, right in zip(cmp_node.ops, cmp_node.comparators):
                    if not isinstance(op, (ast.Eq, ast.Gt, ast.GtE)):
                        continue
                    if not isinstance(right, ast.Constant) or not isinstance(right.value, int):
                        continue
                    if right.value <= 3:
                        continue
                    findings.append(
                        f"{rel(case.path)}:{node.lineno}: 用例 {case.name} 断言硬编码会演进的总数 "
                        f"`len({arg_name}) {type(op).__name__.replace('GtE', '>=').replace('Gt', '>').replace('Eq', '==')} {right.value}`"
                        "——应改为结构关系断言（集合双向相等 / 域覆盖 / 序号连续），否则新增条目必红且职责与门禁重复"
                    )
    return findings


def run_checks(include_live: bool = False) -> tuple[list[str], dict[str, int]]:
    """跑全部检查，返回（findings, 统计）。"""
    cases, modules, parse_errors = collect_cases(include_live)
    dup_findings, skipped = check_duplicate_bodies(cases)
    findings: list[str] = []
    findings += parse_errors
    findings += check_dead_tests(cases, modules)
    findings += check_assertion_free(cases)
    findings += dup_findings
    findings += check_self_fulfilling(cases)
    findings += check_hardcoded_evolving_totals(cases)
    stats = {
        "files": len(modules),
        "cases": len(cases),
        "duplicate_skipped": skipped,
        "dead": len(check_dead_tests(cases, modules)),
        "assertion_free": len(check_assertion_free(cases)),
        "duplicate": len(dup_findings),
        "self_fulfilling": len(check_self_fulfilling(cases)),
        "hardcoded_totals": len(check_hardcoded_evolving_totals(cases)),
    }
    return findings, stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="测试用例冗余与无效检查（死用例 / 无断言 / 完全重复 / 自证用例 / 硬编码演进总数）",
    )
    add_common_args(parser)
    parser.add_argument("--include-live", action="store_true", help="连带扫描 src/test/live/（默认按 pytest.ini 排除）")
    args = parser.parse_args()

    findings, stats = run_checks(include_live=args.include_live)

    if args.verbose:
        print(
            f"  扫描测试文件 {stats['files']} 个 / 用例 {stats['cases']} 个"
            f"（live 目录{'纳入' if args.include_live else '跳过'}）"
        )
        print(
            f"  死用例 {stats['dead']} / 无断言 {stats['assertion_free']} /"
            f" 完全重复 {stats['duplicate']} / 自证用例 {stats['self_fulfilling']} /"
            f" 硬编码演进总数 {stats['hardcoded_totals']}"
        )
        print(f"  因不可解析的 self 间接调用而跳过重复比对的用例：{stats['duplicate_skipped']}")

    sys.exit(
        report(
            findings,
            "[OK] 测试用例冗余与无效检查通过（无死用例 / 无断言 / 完全重复 / 自证用例 / 硬编码演进总数）",
            ci=args.ci,
            fail_message="[!] 发现 {n} 处测试用例问题，须修正后提交",
        )
    )


if __name__ == "__main__":
    main()

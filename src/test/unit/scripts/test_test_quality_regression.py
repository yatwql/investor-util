"""测试质量回归守护 — 禁止空测试体（死用例）。

静态扫描 ``src/test/**/test_*.py``：任何 ``test_*`` 函数去除 docstring 后
必须含至少一条非 ``pass`` 语句。空体（仅 docstring / ``pass``）的「测试」
不会被任何断言覆盖，却会在收集计数与门禁全绿中制造虚假信心——本用例锁定
该形态不得再进入测试树。

注：本守护只判「是否完全空」，不判「是否有断言」——后者存在大量合法的
「不抛异常/no-op」弱断言（如 SilentProgressReporter、空范围的 no-crash），
纳入会让守护充满误报；「名字承诺断言却无断言」属语义问题，由人的评审负责。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts, pytest.mark.usefixtures("offline_external_sources")]

_TEST_ROOT = Path(__file__).resolve().parents[2]  # src/test


def _iter_test_functions(path: Path):
    """产出文件内全部 test_* 函数（含嵌套与异步）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            yield node


def test_no_empty_test_bodies():
    """任何 test_* 函数体（去 docstring）不得为空或仅 pass。"""
    offenders: list[str] = []
    for path in sorted(_TEST_ROOT.rglob("test_*.py")):
        if "__pycache__" in path.as_posix():
            continue
        for fn in _iter_test_functions(path):
            body = list(fn.body)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            if not body or all(isinstance(stmt, ast.Pass) for stmt in body):
                offenders.append(f"{path.relative_to(_TEST_ROOT).as_posix()}::{fn.name}")
    assert offenders == [], f"存在空测试体（死用例，须实现断言或删除）: {offenders}"

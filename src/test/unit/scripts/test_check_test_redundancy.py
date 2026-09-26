"""测试：check-test-redundancy.py — 测试用例冗余与无效检查

覆盖：
  - 用例收集（模块级函数 / Test 类方法 / 所在类归属）
  - 死用例：同文件同类同名重复定义、非 Test 类中的 test_ 方法、Test 类带 __init__
  - 无断言：assert / assertEqual 等 assert* / pytest.raises / mock 断言 / 经同类辅助方法断言
  - 完全重复：同体同参数同装饰器成组；字面量不同不成组；无法解析的 self 间接调用跳过比对
  - 自证用例：patch 被测函数 + 设 return_value + 断言回该字面量；断言别的字面量不算
  - 真实仓库冒烟：当前测试集无死用例 / 无断言 / 完全重复 / 自证用例

测试通过脚本 import 方式直接复用分析函数，不运行真实 CLI。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # 仓库根目录（src/test/unit/scripts 向上 4 级）
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_script(name: str):
    """按文件名加载 scripts/ 下的检查脚本（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[mod_name] = mod  # ast/类型注解解析需要模块已注册
    spec.loader.exec_module(mod)
    return mod


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
    pytest.mark.usefixtures("offline_external_sources"),
]


@pytest.fixture(scope="module")
def redundancy():
    return _load_script("check-test-redundancy.py")


def _cases(redundancy, src: str):
    """把源码字符串编译为用例列表（测试用，避免落盘）。"""
    tree = ast.parse(src)
    return redundancy.cases_in_module(Path("t.py"), tree)


def _no_findings(redundancy, src: str) -> None:
    assert redundancy.check_assertion_free(_cases(redundancy, src)) == []


# ═══ 用例收集 ═══


class TestCollection:
    def test_collects_module_level_and_class_methods(self, redundancy):
        src = (
            "def test_top():\n    assert 1\n"
            "class TestX:\n"
            "    def test_in_class(self):\n        assert 1\n"
            "    def helper(self):\n        pass\n"
        )
        cases = _cases(redundancy, src)
        assert [(c.class_name, c.name) for c in cases] == [("", "test_top"), ("TestX", "test_in_class")]

    def test_ignores_non_test_functions(self, redundancy):
        assert _cases(redundancy, "def helper():\n    assert 1\n") == []


# ═══ 死用例 ═══


class TestDeadTests:
    def test_duplicate_name_in_same_class(self, redundancy):
        src = "class TestX:\n    def test_a(self):\n        assert 1\n    def test_a(self):\n        assert 2\n"
        cases = _cases(redundancy, src)
        modules = {Path("t.py"): ast.parse(src)}
        findings = redundancy.check_dead_tests(cases, modules)
        assert len(findings) == 1 and "重复定义 2 次" in findings[0]

    def test_test_method_in_non_test_class(self, redundancy):
        src = "class Helper:\n    def test_a(self):\n        assert 1\n"
        findings = redundancy.check_dead_tests(_cases(redundancy, src), {Path("t.py"): ast.parse(src)})
        assert len(findings) == 1 and "不以 Test 开头" in findings[0]

    def test_test_class_with_init(self, redundancy):
        src = "class TestX:\n    def __init__(self):\n        pass\n    def test_a(self):\n        assert 1\n"
        findings = redundancy.check_dead_tests(_cases(redundancy, src), {Path("t.py"): ast.parse(src)})
        assert len(findings) == 1 and "__init__" in findings[0]

    def test_healthy_module_passes(self, redundancy):
        src = "class TestX:\n    def test_a(self):\n        assert 1\n    def test_b(self):\n        assert 2\n"
        assert redundancy.check_dead_tests(_cases(redundancy, src), {Path("t.py"): ast.parse(src)}) == []


# ═══ 无断言 ═══


class TestAssertionFree:
    @pytest.mark.parametrize(
        "body",
        [
            "        assert x == 1",
            "        self.assertEqual(x, 1)",
            "        self.assertTrue(x)",
            "        self.fail('boom')",
            "        with pytest.raises(ValueError):\n            f()",
            "        mock_fn.assert_called_once()",
            "        mock_fn.assert_not_called()",
        ],
    )
    def test_assertion_forms_accepted(self, redundancy, body):
        _no_findings(redundancy, f"def test_a(x=None):\n{body}\n")

    def test_call_only_is_flagged(self, redundancy):
        findings = redundancy.check_assertion_free(_cases(redundancy, "def test_a():\n    do_something()\n"))
        assert len(findings) == 1 and "无任何断言" in findings[0]

    def test_helper_method_with_assertion_counts(self, redundancy):
        src = (
            "class TestX(unittest.TestCase):\n"
            "    def _assert_pairs(self, pairs):\n"
            "        self.assertEqual(pairs, [])\n"
            "    def test_a(self):\n"
            "        self._assert_pairs([])\n"
        )
        _no_findings(redundancy, src)

    def test_helper_without_assertion_does_not_count(self, redundancy):
        src = "class TestX:\n    def _build(self):\n        return 1\n    def test_a(self):\n        self._build()\n"
        findings = redundancy.check_assertion_free(_cases(redundancy, src))
        assert len(findings) == 1


# ═══ 完全重复 ═══


class TestDuplicates:
    def test_identical_bodies_grouped(self, redundancy):
        src = "def test_a():\n    assert f(1) == 2\ndef test_b():\n    assert f(1) == 2\n"
        findings, skipped = redundancy.check_duplicate_bodies(_cases(redundancy, src))
        assert len(findings) == 1 and "完全重复" in findings[0] and skipped == 0

    def test_different_literal_not_grouped(self, redundancy):
        src = "def test_a():\n    assert f(1) == 2\ndef test_b():\n    assert f(1) == 3\n"
        findings, _ = redundancy.check_duplicate_bodies(_cases(redundancy, src))
        assert findings == []

    def test_shared_helper_differs_by_binding_not_grouped(self, redundancy):
        """同名方法调用 self._call，但两个类的绑定不同 → 并行覆盖，不算重复。"""
        src = (
            "class TestA:\n"
            "    def _call(self, v):\n        return fn_a(v)\n"
            "    def test_x(self):\n        assert self._call('a') == 0.0\n"
            "class TestB:\n"
            "    def _call(self, v):\n        return fn_b(v)\n"
            "    def test_x(self):\n        assert self._call('a') == 0.0\n"
        )
        findings, skipped = redundancy.check_duplicate_bodies(_cases(redundancy, src))
        assert findings == [] and skipped == 0

    def test_unresolvable_self_indirection_skipped(self, redundancy):
        """self 间接调用来自 setUp（类体内无绑定）→ 跳过比对，不误报。"""
        src = (
            "class TestX:\n"
            "    def test_a(self):\n        assert self.r.run() == 1\n"
            "    def test_b(self):\n        assert self.r.run() == 1\n"
        )
        cases = _cases(redundancy, src)
        assert all(redundancy.body_signature(c) is None for c in cases)
        findings, skipped = redundancy.check_duplicate_bodies(cases)
        assert findings == [] and skipped == 2


# ═══ 自证用例 ═══


class TestSelfFulfilling:
    def test_patch_sut_then_assert_own_return(self, redundancy):
        src = (
            "from unittest.mock import patch\n"
            "@patch('mod.get_ttl')\n"
            "def test_a(mock_ttl):\n"
            "    mock_ttl.return_value = 120\n"
            "    assert get_ttl('k') == 120\n"
        )
        findings = redundancy.check_self_fulfilling(_cases(redundancy, src))
        assert len(findings) == 1 and "断言恒真" in findings[0]

    def test_patch_sut_but_assert_other_value_not_flagged(self, redundancy):
        src = (
            "from unittest.mock import patch\n"
            "@patch('mod.get_ttl')\n"
            "def test_a(mock_ttl):\n"
            "    mock_ttl.return_value = 120\n"
            "    assert get_ttl('k') == 999\n"
        )
        assert redundancy.check_self_fulfilling(_cases(redundancy, src)) == []

    def test_patch_dependency_not_flagged(self, redundancy):
        """patch 的是依赖、断言的是真实返回值 → 正常。"""
        src = (
            "from unittest.mock import patch\n"
            "@patch('mod._is_market_open', return_value=True)\n"
            "def test_a(mock_open):\n"
            "    assert get_ttl('price') == 120\n"
        )
        assert redundancy.check_self_fulfilling(_cases(redundancy, src)) == []


# ═══ 硬编码「会演进的总数」（E）═══


class TestHardcodedEvolvingTotals:
    """E 类：把可增长集合的条数写死进断言 → 良性变更（新增条目）也会把测试打红。"""

    def _findings(self, redundancy, src: str, path: str = "src/test/unit/scripts/test_x.py"):
        tree = ast.parse(src)
        cases = redundancy.cases_in_module(Path(path), tree)
        return redundancy.check_hardcoded_evolving_totals(cases)

    def test_flags_hardcoded_requirement_total(self, redundancy):
        src = "def test_a(req_ids):\n    req_ids = load()\n    assert len(req_ids) == 276\n"
        findings = self._findings(redundancy, src)
        assert len(findings) == 1 and "硬编码会演进的总数" in findings[0]

    def test_flags_hardcoded_section_total(self, redundancy):
        """实参名含语义关键词（sections）时报告——与真实缺陷写法一致。"""
        src = "def test_a(sections):\n    assert len(sections) == 17\n"
        assert self._findings(redundancy, src)

    def test_ignores_small_totals(self, redundancy):
        """小数字（<= 3）常为有意断言，不报。"""
        src = "def test_a(xs):\n    assert len(xs) == 2\n"
        assert self._findings(redundancy, src) == []

    def test_ignores_unrelated_len(self, redundancy):
        """与可演进集合无关的 len 断言（如实参名无关键词且路径无提示）不报。"""
        src = "def test_a(values):\n    assert len(values) == 99\n"
        assert self._findings(redundancy, src, path="src/test/unit/misc/test_y.py") == []

    def test_path_hint_alone_is_enough(self, redundancy):
        """路径含 requirement/registry 提示时，即使实参名无关键词也报（真实缺陷常如此）。"""
        src = "def test_a(reg):\n    assert len(reg) == 17\n"
        assert self._findings(redundancy, src, path="src/test/unit/core/test_registry.py")

    def test_ignores_structural_assertions(self, redundancy):
        """结构关系断言（集合相等 / 子集 / 逐项遍历）不应被误报。"""
        src = (
            "def test_a(req_ids, mapped):\n"
            "    assert set(req_ids) == set(mapped)\n"
            "    assert expected <= set(req_ids)\n"
            "    for x in req_ids:\n        assert x\n"
        )
        assert self._findings(redundancy, src) == []

    def test_ignores_non_assert_usage(self, redundancy):
        """非断言位置的长度比较（如日志/计算）不报。"""
        src = "def test_a(req_ids):\n    n = len(req_ids) == 276\n    assert n is not None\n"
        assert self._findings(redundancy, src) == []


# ═══ 真实仓库冒烟 ═══


class TestRealRepoSmoke:
    def test_current_repo_clean(self, redundancy):
        findings, stats = redundancy.run_checks()
        assert findings == []
        assert stats["cases"] > 6000 and stats["files"] > 300

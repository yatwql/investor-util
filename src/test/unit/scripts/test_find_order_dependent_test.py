"""测试：顺序依赖二分工具 — find-order-dependent-test.py

覆盖：
  - `smallest_failing_prefix` 二分正确性（对多组单调失败阈值与线性 oracle 对齐）
  - `parse_collect_order` 从 `--collect-only -q` 输出解析文件顺序（首次出现、去重、跳过杂行）
  - `classify_output` 按返回码与 FAILED 摘要行判定目标/无关失败/执行错误
  - `minimize_subset` 预算内把集合精简到「每个元素都必要」（合成失败谓词）
  - 端到端：临时目录内「导入期泄漏 os.environ 的前置文件 + 断言无该环境变量的目标」
    —— 定位污染源退出 0；目标单跑即失败退出 1；无泄漏复现退出 2
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from src.test._script_loader import load_script

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def order_script():
    return load_script("find-order-dependent-test.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


class TestSmallestFailingPrefix:
    """二分最小失败前缀——对单调谓词必须与线性扫描 oracle 一致。"""

    @pytest.mark.parametrize(
        ("threshold", "total"),
        [
            (1, 1),
            (1, 8),
            (5, 16),
            (7, 7),
            (16, 16),
            (3, 100),
        ],
    )
    def test_matches_linear_oracle(self, order_script, threshold, total):
        """fails(k) = (k >= threshold) 时二分结果 == 线性最小满足点。"""
        calls: list[int] = []

        def fails(k: int) -> bool:
            calls.append(k)
            return k >= threshold

        got = order_script.smallest_failing_prefix(total, fails)
        assert got == threshold
        # 二分复杂度：比较次数 O(log n)，不得退化为线性
        assert len(calls) <= 2 * total.bit_length()

    def test_no_failing_prefix_returns_none(self, order_script):
        assert order_script.smallest_failing_prefix(10, lambda _k: False) is None

    def test_zero_total_returns_none(self, order_script):
        assert order_script.smallest_failing_prefix(0, lambda _k: True) is None


class TestParseCollectOrder:
    """收集输出解析：仅取 .py 节点、首现顺序、逐文件去重、跳过空行与杂行。"""

    def test_extracts_deduped_order(self, order_script):
        out = (
            "src/test/a/test_one.py::TestClass::test_x\n"
            "src/test/a/test_one.py::TestClass::test_y\n"
            "src/test/b/test_two.py::test_z\n"
            "\n"
            "src/test/a/test_one.py::test_again\n"  # 同文件再次出现 → 去重
            "3 files collected\n"  # 非节点行 → 跳过
        )
        files = order_script.parse_collect_order(out)
        assert files == [
            "src/test/a/test_one.py",
            "src/test/b/test_two.py",
        ]

    def test_ignores_non_py_and_blank(self, order_script):
        assert order_script.parse_collect_order("\n\n<Module session>\n") == []


class TestClassifyOutput:
    """返回码 + FAILED 摘要行 → 目标/无关失败/通过/错误 的分类。"""

    def test_target_failed_by_summary_line(self, order_script):
        out = "some/other.py::test_ok PASSED\nFAILED src/test/x.py::TestA::test_t\n"
        got = order_script.classify_output(1, out, "src/test/x.py::TestA::test_t")
        assert got is order_script.Outcome.TARGET_FAILED

    def test_target_failed_by_prefix_match(self, order_script):
        out = "FAILED src/test/x.py::TestA::test_t[param0]\n"
        got = order_script.classify_output(1, out, "src/test/x.py::TestA::test_t")
        assert got is order_script.Outcome.TARGET_FAILED

    def test_other_failure_is_not_target(self, order_script):
        out = "FAILED src/test/y.py::test_other\n"
        got = order_script.classify_output(1, out, "src/test/x.py::test_t")
        assert got is order_script.Outcome.OTHER_FAILURE

    def test_zero_return_is_pass(self, order_script):
        assert order_script.classify_output(0, "", "x.py::test_t") is order_script.Outcome.TARGET_PASSED

    def test_usage_error_is_error(self, order_script):
        assert order_script.classify_output(4, "ERROR: no such test", "x.py::test_t") is order_script.Outcome.ERROR


class TestMinimizeSubset:
    """预算内精简：只留必要元素（合成谓词可预期）。"""

    def test_reduces_to_single_culprit(self, order_script):
        files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
        got = order_script.minimize_subset(files, lambda s: "c.py" in s, budget=40)
        assert got == ["c.py"]

    def test_keeps_all_when_all_necessary(self, order_script):
        # 谓词要求两个元素同时存在 → 两个都必要
        files = ["a.py", "b.py", "c.py"]
        got = order_script.minimize_subset(files, lambda s: "a.py" in s and "b.py" in s, budget=40)
        assert set(got) == {"a.py", "b.py"}

    def test_budget_bounds_runs(self, order_script):
        files = [f"f{i}.py" for i in range(16)]
        calls = {"n": 0}

        def fails(s: list[str]) -> bool:
            calls["n"] += 1
            return "f7.py" in s

        order_script.minimize_subset(files, fails, budget=5)
        assert calls["n"] <= 5  # 预算硬上界（最后一次尝试也计入）


class TestEndToEndCli:
    """端到端：真实 pytest 子进程复现「导入期泄漏」并定位污染源。"""

    def _write_case(self, dirpath: Path, *, leak: bool, fail_alone: bool = False) -> tuple[str, str]:
        leak_file = dirpath / "test_leaky.py"
        target_file = dirpath / "test_target.py"
        leak_file.write_text(
            'import os\n\nos.environ["ORDER_LEAK_PROBE"] = "1"  # 模块导入期泄漏\n\n\n'
            "def test_touched_import():\n    assert True\n",
            encoding="utf-8",
        )
        if fail_alone:
            target_file.write_text("def test_always_fail():\n    assert False\n", encoding="utf-8")
        elif leak:
            target_file.write_text(
                'def test_sees_clean_env():\n    assert os.environ.get("ORDER_LEAK_PROBE") is None, "泄漏的环境变量"\n',
                encoding="utf-8",
            )
        else:
            target_file.write_text("def test_green():\n    assert True\n", encoding="utf-8")
        if leak:
            # 目标文件需要 import os 才能断言
            src = target_file.read_text(encoding="utf-8")
            if "import os" not in src:
                target_file.write_text("import os\n\n" + src, encoding="utf-8")
        target_node = (
            f"{target_file.name}::test_sees_clean_env"
            if leak and not fail_alone
            else (f"{target_file.name}::test_always_fail" if fail_alone else f"{target_file.name}::test_green")
        )
        leak_node = f"{leak_file.name}"
        return target_node, leak_node

    def _run_main(self, dirpath: Path, argv: list[str]) -> tuple[int, str]:
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "find-order-dependent-test.py"), *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(dirpath),
            timeout=300,
        )
        return proc.returncode, proc.stdout + proc.stderr

    def test_locates_leaking_file(self, tmp_path):
        target_node, leak_file = self._write_case(tmp_path, leak=True)
        rc, out = self._run_main(tmp_path, [target_node, "--collect-root", ".", "--candidates", leak_file])
        assert rc == 0, out
        assert leak_file in out, "污染源文件必须出现在输出中"
        assert "最小复现" in out

    def test_fails_alone_returns_not_order_dependent(self, tmp_path):
        target_node, _ = self._write_case(tmp_path, leak=False, fail_alone=True)
        rc, out = self._run_main(tmp_path, [target_node, "--collect-root", "."])
        assert rc == 1, out
        assert "不是顺序依赖" in out

    def test_no_leak_returns_not_reproducible(self, tmp_path):
        target_node, _ = self._write_case(tmp_path, leak=False)
        rc, out = self._run_main(tmp_path, [target_node, "--collect-root", "."])
        assert rc == 2, out
        assert "顺序依赖不成立" in out or "无法复现" in out

    def test_dry_run_skips_bisection(self, tmp_path):
        target_node, _ = self._write_case(tmp_path, leak=True)
        rc, out = self._run_main(tmp_path, [target_node, "--collect-root", ".", "--dry-run"])
        assert rc == 0, out
        assert "dry-run" in out

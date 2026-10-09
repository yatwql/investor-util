"""共享脚本 loader 测试（加载契约 / sys.modules 注册 / 样板唯一性）。

覆盖 `src/test/_script_loader.py`：按文件名与子路径加载、模块名派生与显式覆盖、
每次调用返回新实例、`@dataclass` 依赖的 sys.modules 注册；以及「样板唯一性」机检——
除 loader 自身外，任何测试文件不得再自带 importlib 动态加载样板。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from src.test._script_loader import SCRIPTS_DIR, load_script

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts, pytest.mark.usefixtures("offline_external_sources")]

_TEST_ROOT = Path(__file__).resolve().parents[2]


class TestLoadContract:
    """加载行为契约。"""

    def test_scripts_dir_points_at_repo_scripts(self):
        assert SCRIPTS_DIR.is_dir()
        assert (SCRIPTS_DIR / "check-svg.py").is_file()

    def test_load_by_filename(self):
        mod = load_script("check-svg.py")
        assert hasattr(mod, "geom_findings")

    def test_module_name_derived_from_filename(self):
        assert load_script("perf-report.py").__name__ == "perf_report"

    def test_explicit_module_name_override(self):
        mod = load_script("_checklib.py", module_name="_checklib_under_test")
        assert mod.__name__ == "_checklib_under_test"

    def test_subpath_script_loadable(self):
        mod = load_script("_test_runner/modes.py", module_name="_test_runner_modes_under_test")
        assert hasattr(mod, "MODES")

    def test_registered_in_sys_modules(self):
        """`@dataclass` 按 `cls.__module__` 回查命名空间，未注册会解析失败。"""
        mod = load_script("perf-report.py")
        assert sys.modules[mod.__name__] is mod
        assert hasattr(mod, "PerfSample")  # 模块内 @dataclass 定义成功即为注册生效

    def test_fresh_instance_each_call(self):
        """每次调用重新执行脚本，用例之间模块状态互不串扰。"""
        first = load_script("perf-report.py")
        second = load_script("perf-report.py")
        assert first is not second


class TestBoilerplateUniqueness:
    """样板唯一性：动态加载样板只允许存在于共享 loader 自身。"""

    def test_spec_boilerplate_has_single_home(self):
        # 名称动态拼接，避免本测试文件自身成为「样板出处」的证据
        needle = "spec_" + "from_file_location"
        offenders = sorted(
            p.as_posix()
            for p in _TEST_ROOT.rglob("*.py")
            if "__pycache__" not in p.parts and needle in p.read_text(encoding="utf-8")
        )
        assert offenders == [(_TEST_ROOT / "_script_loader.py").as_posix()]

    def test_no_local_load_script_definitions(self):
        """各测试文件不得再自定义同名本地加载器（避免与共享实现分叉）。"""
        offenders: list[str] = []
        for path in _TEST_ROOT.rglob("*.py"):
            if "__pycache__" in path.parts or path.name == "_script_loader.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name in {"_load_script", "load_script"}:
                    offenders.append(f"{path.as_posix()}::{node.name}")
        assert offenders == []

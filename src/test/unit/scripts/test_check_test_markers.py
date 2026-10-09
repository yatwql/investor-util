"""check-test-markers.py 测试标记合规检查（AST 静态提取 / 目录期望标记 / 违规判定）。

覆盖 `_extract_markers_from_file` 的三种标记来源（模块级 pytestmark、类/方法装饰器、
语法错误降级）、`_get_relative_dir` 的目录键、`check_file` 的四类违规分支
（未注册标记 / 已移除标记 / edge 文件缺 edge / 目录期望标记缺失）与干净路径；
以及标记清单的单一事实来源（由 `conftest.py` 注册语句 AST 派生）与目录期望表
同 `src/test/` 目录结构的双向绑定。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts, pytest.mark.usefixtures("offline_external_sources")]


@pytest.fixture(name="mod")
def fixture_mod():
    """加载 `scripts/check-test-markers.py` 为可测模块。"""
    from src.test._script_loader import load_script

    return load_script("check-test-markers.py")


@pytest.fixture(name="isolated_dir")
def fixture_isolated_dir(mod, tmp_path, monkeypatch):
    """把被检脚本的 TEST_DIR 指向临时目录，避免用例向真实 `src/test/` 写文件。"""
    monkeypatch.setattr(mod, "TEST_DIR", tmp_path)
    return tmp_path


def _write(root, rel_path: str, content: str):
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ── AST 静态提取 ──


class TestExtractMarkers:
    """从测试文件静态提取标记名。"""

    def test_module_level_pytestmark_list(self, mod, tmp_path):
        path = _write(
            tmp_path,
            "test_sample.py",
            "import pytest\n"
            "pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts]\n"
            "def test_x():\n    assert True\n",
        )
        assert mod._extract_markers_from_file(path) == {"unit", "unit_scripts"}

    def test_class_and_method_decorators(self, mod, tmp_path):
        path = _write(
            tmp_path,
            "test_sample.py",
            "import pytest\n"
            "@pytest.mark.edge\n"
            "class TestA:\n"
            "    @pytest.mark.smoke\n"
            "    def test_x(self):\n        assert True\n",
        )
        assert mod._extract_markers_from_file(path) == {"edge", "smoke"}

    def test_file_without_markers_returns_empty(self, mod, tmp_path):
        path = _write(tmp_path, "test_sample.py", "def test_x():\n    assert True\n")
        assert mod._extract_markers_from_file(path) == set()

    def test_syntax_error_returns_empty(self, mod, tmp_path):
        path = _write(tmp_path, "test_sample.py", "def test_x(:\n")
        assert mod._extract_markers_from_file(path) == set()

    def test_unrelated_attribute_not_parsed_as_marker(self, mod, tmp_path):
        path = _write(
            tmp_path,
            "test_sample.py",
            "import pytest\nmarkers = [pytest.markers.unit]\nclass TestA:\n    decorators = [pytest.markup.later]\n",
        )
        assert mod._extract_markers_from_file(path) == set()


# ── 目录键 ──


class TestRelativeDir:
    """`_get_relative_dir`：嵌套目录与测试根。"""

    def test_nested_dir(self, mod, isolated_dir):
        path = _write(isolated_dir, "unit/core/test_cache.py", "def test_x():\n    assert True\n")
        assert mod._get_relative_dir(path) == "unit/core"

    def test_root_level_file_returns_empty_string(self, mod, isolated_dir):
        path = _write(isolated_dir, "test_top.py", "def test_x():\n    assert True\n")
        assert mod._get_relative_dir(path) == ""


# ── 单文件检查 ──


class TestCheckFile:
    """`check_file` 的违规分支与干净路径。"""

    def test_unknown_marker_reported(self, mod, isolated_dir):
        path = _write(
            isolated_dir,
            "test_sample.py",
            "import pytest\npytestmark = [pytest.mark.unit, pytest.mark.unit_zzz]\n",
        )
        violations = mod.check_file(path, verbose=False, ci_mode=True)
        assert len(violations) == 1
        assert "unit_zzz" in violations[0]
        assert "未注册" in violations[0]

    def test_deprecated_marker_reported(self, mod, isolated_dir, monkeypatch):
        monkeypatch.setattr(mod, "DEPRECATED_MARKERS", {"legacy_marker"})
        path = _write(
            isolated_dir,
            "test_sample.py",
            "import pytest\npytestmark = [pytest.mark.unit, pytest.mark.legacy_marker]\n",
        )
        violations = mod.check_file(path, verbose=False, ci_mode=True)
        assert len(violations) == 1
        assert "已移除" in violations[0]

    def test_edge_file_missing_edge_marker_reported(self, mod, isolated_dir):
        path = _write(
            isolated_dir,
            "test_sample_edge.py",
            "import pytest\npytestmark = [pytest.mark.unit, pytest.mark.unit_core]\n",
        )
        violations = mod.check_file(path, verbose=False, ci_mode=True)
        assert len(violations) == 1
        assert "_edge.py" in violations[0]

    def test_edge_file_with_edge_marker_passes(self, mod, isolated_dir):
        path = _write(
            isolated_dir,
            "test_sample_edge.py",
            "import pytest\npytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]\n",
        )
        assert mod.check_file(path, verbose=False, ci_mode=True) == []

    def test_dir_expectation_unmet_reported(self, mod, isolated_dir):
        """unit/core 目录期望 {unit, unit_core}，两者都不标即报缺期望标记。"""
        path = _write(
            isolated_dir,
            "unit/core/test_cache.py",
            "import pytest\npytestmark = [pytest.mark.edge]\n",
        )
        violations = mod.check_file(path, verbose=False, ci_mode=True)
        assert len(violations) == 1
        assert "期望标记" in violations[0]
        assert "unit_core" in violations[0]

    def test_dir_expectation_met_passes(self, mod, isolated_dir):
        path = _write(
            isolated_dir,
            "unit/core/test_cache.py",
            "import pytest\npytestmark = [pytest.mark.unit, pytest.mark.unit_core]\n",
        )
        assert mod.check_file(path, verbose=False, ci_mode=True) == []

    def test_dir_without_expectation_skips_that_check(self, mod, isolated_dir):
        """未登记目录期望时不产生缺标记误报（期望表只约束已登记目录）。"""
        path = _write(
            isolated_dir,
            "unit/misc/test_odd.py",
            "import pytest\npytestmark = [pytest.mark.unit, pytest.mark.unit_core]\n",
        )
        assert mod.check_file(path, verbose=False, ci_mode=True) == []

    def test_clean_file_reports_ok_when_verbose(self, mod, isolated_dir, capsys):
        path = _write(
            isolated_dir,
            "unit/core/test_cache.py",
            "import pytest\npytestmark = [pytest.mark.unit, pytest.mark.unit_core]\n",
        )
        violations = mod.check_file(path, verbose=True, ci_mode=False)
        assert violations == []
        assert "[OK]" in capsys.readouterr().out


# ── 标记清单单一事实来源 ──


class TestRegisteredMarkers:
    """`registered_markers` 从 conftest 注册语句派生，不再靠人肉对表。"""

    def test_extracts_single_line_registrations(self, mod, tmp_path):
        conftest = _write(
            tmp_path,
            "conftest.py",
            "def pytest_configure(config):\n"
            '    config.addinivalue_line("markers", "unit: 单元测试总标记")\n'
            '    config.addinivalue_line("markers", "edge: 边缘场景")\n',
        )
        assert mod.registered_markers(conftest) == {"unit", "edge"}

    def test_extracts_multiline_call_with_concatenated_literals(self, mod, tmp_path):
        conftest = _write(
            tmp_path,
            "conftest.py",
            "def pytest_configure(config):\n"
            "    config.addinivalue_line(\n"
            '        "markers",\n'
            '        "cassette: 已录制数据源响应"\n'
            '        "回放",\n'
            "    )\n",
        )
        assert mod.registered_markers(conftest) == {"cassette"}

    def test_ignores_other_groups_and_star_args(self, mod, tmp_path):
        conftest = _write(
            tmp_path,
            "conftest.py",
            "ARGS = ['markers', 'x']\n"
            "def pytest_configure(config):\n"
            '    config.addinivalue_line("filterwarnings", "ignore")\n'
            "    config.addinivalue_line(*ARGS)\n",
        )
        assert mod.registered_markers(conftest) == set()

    def test_real_conftest_is_source_and_includes_cassette(self, mod):
        """手抄清单时代 `cassette` 已在 conftest 注册却不在清单内 — 派生后自动跟随。"""
        assert mod.KNOWN_MARKERS == mod.registered_markers(mod.CONFTEST_PATH)
        assert {"cassette", "unit_scripts", "integration_cli", "live"} <= mod.KNOWN_MARKERS

    def test_new_conftest_marker_is_auto_accepted(self, mod, isolated_dir, monkeypatch, tmp_path):
        conf_dir = tmp_path / "conf"
        conftest = _write(
            conf_dir,
            "conftest.py",
            "def pytest_configure(config):\n"
            '    config.addinivalue_line("markers", "unit: 单元测试总标记")\n'
            '    config.addinivalue_line("markers", "unit_brandnew: 新标记")\n',
        )
        monkeypatch.setattr(mod, "KNOWN_MARKERS", mod.registered_markers(conftest))
        path = _write(
            isolated_dir,
            "test_sample.py",
            "import pytest\npytestmark = [pytest.mark.unit, pytest.mark.unit_brandnew]\n",
        )
        assert mod.check_file(path, verbose=False, ci_mode=True) == []


# ── 目录期望表与目录结构绑定 ──


def _unit_dir_to_marker(repo_root: Path) -> dict[str, str]:
    """AST 取 `src/test/unit/conftest.py` 运行时提示表（避免导入 conftest 的副作用）。"""
    conftest_path = repo_root / "src" / "test" / "unit" / "conftest.py"
    tree = ast.parse(conftest_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_DIR_TO_MARKER":
            return ast.literal_eval(node.value)
    raise AssertionError("src/test/unit/conftest.py 未找到 _DIR_TO_MARKER")


class TestExpectationTableBoundToTree:
    """目录期望表既不幽灵（键须真实存在）也不漏（有测试的目录须有期望）。"""

    @pytest.mark.parametrize("top", ["unit", "scenario"])
    def test_every_test_dir_has_expectation(self, mod, top):
        root = mod.TEST_DIR / top
        actual = {f"{top}/{p.name}" for p in root.iterdir() if p.is_dir() and any(p.rglob("test_*.py"))}
        declared = {key for key in mod.EXPECTED_DIR_MARKERS if key.startswith(f"{top}/")}
        assert declared == actual

    @pytest.mark.parametrize("top", ["unit", "scenario"])
    def test_expectation_keys_are_real_dirs(self, mod, top):
        for key in (k for k in mod.EXPECTED_DIR_MARKERS if k.startswith(f"{top}/")):
            assert (mod.TEST_DIR / key).is_dir(), key

    def test_runtime_hint_map_matches_expectation_table(self, mod):
        """运行时提示表与静态期望表的 unit/* 键集必须一致（否则报错文案指向未知模块）。"""
        unit_keys = {key.split("/", 1)[1] for key in mod.EXPECTED_DIR_MARKERS if key.startswith("unit/")}
        hints = _unit_dir_to_marker(mod.REPO_ROOT)
        assert set(hints) == unit_keys
        assert set(hints.values()) <= mod.KNOWN_MARKERS


# ── 文档与现状一致 ──


class TestDocstringConsistency:
    """通过标准文案不得把现行注册标记写成已移除。"""

    def test_removed_example_is_not_a_registered_marker(self, mod):
        match = re.search(r"已移除的标记（如 ([A-Za-z_0-9]+)）", mod.__doc__ or "")
        if match:
            assert match.group(1) not in mod.KNOWN_MARKERS

    def test_integration_family_is_registered(self, mod):
        assert "integration" in mod.KNOWN_MARKERS
        assert "integration" not in mod.DEPRECATED_MARKERS

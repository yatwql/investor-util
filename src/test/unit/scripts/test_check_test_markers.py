"""check-test-markers.py 测试标记合规检查（AST 静态提取 / 目录期望标记 / 违规判定）。

覆盖 `_extract_markers_from_file` 的三种标记来源（模块级 pytestmark、类/方法装饰器、
语法错误降级）、`_get_relative_dir` 的目录键，以及 `check_file` 的四类违规分支
（未注册标记 / 已移除标记 / edge 文件缺 edge / 目录期望标记缺失）与干净路径。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts, pytest.mark.usefixtures("offline_external_sources")]


@pytest.fixture(name="mod")
def fixture_mod():
    """加载 `scripts/check-test-markers.py` 为可测模块。"""
    from src.test.unit.scripts.test_perf_report import _load_script

    return _load_script("check-test-markers.py")


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

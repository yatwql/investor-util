"""collect-test-coverage.py 收集与分组计数测试（退出码传递 / 目标展开 / 模式计数口径）。

覆盖 `_collect` 对 pytest 退出码的原样传递（含收集期失败 4 与空收集 5）、
`CollectPlugin` 的 nodeid+标记记录、`_target_files` 的目录展开与 live 套件排除、
`_sel` 匹配，以及 `main()` 的退出码出口与模式/子标记计数输出。
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts, pytest.mark.usefixtures("offline_external_sources")]


@pytest.fixture(name="mod")
def fixture_mod():
    """加载 `scripts/collect-test-coverage.py` 为可测模块。"""
    from src.test.unit.scripts.test_perf_report import _load_script

    return _load_script("collect-test-coverage.py")


class _StdoutStub(io.StringIO):
    """可被 `sys.stdout.reconfigure()` 调用的输出桩（真 StringIO 无该方法）。"""

    def reconfigure(self, *args, **kwargs):  # noqa: D102
        return None


def _run_main(mod, monkeypatch, records, targets) -> str:
    """以注入的收集结果跑一次 `main()`，返回其完整标准输出。"""
    monkeypatch.setattr(sys, "argv", ["collect-test-coverage.py", *targets])
    monkeypatch.setattr(mod, "_collect", lambda _targets: 0)
    mod.collected.clear()
    mod.collected.extend(records)
    buf = _StdoutStub()
    monkeypatch.setattr(sys, "stdout", buf)
    mod.main()
    return buf.getvalue()


def _section(text: str, header: str) -> dict[str, int]:
    """解析 `### <header>` 下的 `key: int` 行（遇空行/下一个标题即停）。"""
    lines = text.splitlines()
    assert header in lines, f"缺少输出段 {header!r}"
    start = lines.index(header)
    out: dict[str, int] = {}
    for line in lines[start + 1 :]:
        if not line.strip() or line.startswith("#"):
            break
        key, sep, value = line.partition(":")
        assert sep, f"非 key: value 行 {line!r}"
        out[key.strip()] = int(value.strip())
    return out


_FIXTURE_RECORDS = [
    ("src/test/unit/scripts/test_a.py::test_one", {"unit", "unit_scripts"}),
    ("src/test/unit/scripts/test_b.py::test_two", {"unit", "unit_scripts", "edge"}),
    ("src/test/scenario/basic/test_c.py::test_three", {"scenario", "scenario_basic"}),
    ("src/test/unit/llm/test_d.py::test_four", {"unit", "unit_llm", "llm"}),
]


class TestCollectExitCode:
    """`_collect` 必须原样返回 pytest 退出码（消费方按非零拒收）。"""

    @pytest.mark.parametrize("code", [0, 4, 5])
    def test_returns_pytest_exit_code(self, mod, monkeypatch, code):
        captured: dict = {}

        def fake_main(args, plugins=None, **kwargs):
            captured["args"] = args
            captured["plugins"] = plugins
            return code

        monkeypatch.setattr(mod.pytest, "main", fake_main)
        assert mod._collect(["src/test/"]) == code
        assert captured["args"][0] == "src/test/"
        assert "--collect-only" in captured["args"]
        assert isinstance(captured["plugins"][0], mod.CollectPlugin)

    def test_collect_silences_pytest_output(self, mod, monkeypatch, capsys):
        monkeypatch.setattr(mod.pytest, "main", lambda *a, **k: 0)
        mod._collect(["src/test/"])
        assert capsys.readouterr().out == ""


class TestCollectPlugin:
    """收集插件把 nodeid 与标记集合写入 `collected`，且每次先清空。"""

    def test_records_nodeid_and_markers(self, mod):
        plugin = mod.CollectPlugin()
        plugin.pytest_collection_finish(_fake_session([("a.py::t1", {"unit"})]))
        assert mod.collected == [("a.py::t1", {"unit"})]

    def test_clears_previous_items_on_recollect(self, mod):
        plugin = mod.CollectPlugin()
        plugin.pytest_collection_finish(_fake_session([("a.py::t1", {"unit"})]))
        plugin.pytest_collection_finish(_fake_session([("b.py::t2", {"scenario"})]))
        assert mod.collected == [("b.py::t2", {"scenario"})]


class _FakeMarker:
    def __init__(self, name: str):
        self.name = name


class _FakeItem:
    def __init__(self, nodeid: str, markers: set[str]):
        self._nodeid = nodeid
        self._markers = markers

    @property
    def nodeid(self) -> str:
        return self._nodeid

    def iter_markers(self):
        return [_FakeMarker(name) for name in self._markers]


def _fake_session(items):
    class _Session:
        pass

    session = _Session()
    session.items = [_FakeItem(nodeid, markers) for nodeid, markers in items]
    return session


class TestTargetFiles:
    """`_target_files`：目录展开 / 文件透传 / live 排除 / 排序。"""

    def test_dir_expands_to_test_files_sorted(self, mod):
        root = mod.REPO_ROOT / "src" / "test" / "unit" / "scripts"
        out = mod._target_files([str(root)])
        assert out
        assert out == sorted(out)
        assert all(f.startswith(str(root)) for f in out)
        assert all("__pycache__" not in f.split("/") for f in out)
        assert all(f.rsplit("/", 1)[-1].startswith("test_") for f in out)

    def test_live_suite_excluded(self, mod):
        live = (mod.REPO_ROOT / "src" / "test" / "live").resolve()
        out = mod._target_files([str(mod.REPO_ROOT / "src" / "test")])
        assert out
        assert not any(live in Path(f).resolve().parents for f in out)

    def test_file_target_passed_through_unchanged(self, mod):
        target = str(mod.REPO_ROOT / "src" / "test" / "conftest.py")
        assert mod._target_files([target]) == [target]

    def test_nonexistent_target_returns_empty(self, mod):
        assert mod._target_files([str(mod.REPO_ROOT / "no_such_target_dir")]) == []


class TestSel:
    """`_sel`：任一名命中即为真。"""

    def test_any_name_matches(self, mod):
        assert mod._sel({"unit", "unit_core"}, "unit_core", "unit_web") is True

    def test_no_name_matches(self, mod):
        assert mod._sel({"unit"}, "unit_core", "unit_web") is False

    def test_empty_markers(self, mod):
        assert mod._sel(set(), "unit") is False


class TestMainExitCode:
    """`main()` 出口：非 (0, 5) 原样 `sys.exit`，5（空收集）与 0 正常返回。"""

    @pytest.mark.parametrize("code", [0, 5])
    def test_zero_and_no_tests_collected_return_normally(self, mod, monkeypatch, code):
        monkeypatch.setattr(sys, "argv", ["collect-test-coverage.py", str(mod.REPO_ROOT / "src" / "test")])
        monkeypatch.setattr(mod, "_collect", lambda _targets: code)
        mod.collected.clear()
        monkeypatch.setattr(sys, "stdout", _StdoutStub())
        assert mod.main() is None

    @pytest.mark.parametrize("code", [1, 4])
    def test_collection_failure_exits_with_same_code(self, mod, monkeypatch, code):
        monkeypatch.setattr(sys, "argv", ["collect-test-coverage.py", str(mod.REPO_ROOT / "src" / "test")])
        monkeypatch.setattr(mod, "_collect", lambda _targets: code)
        mod.collected.clear()
        monkeypatch.setattr(sys, "stdout", _StdoutStub())
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == code


class TestMainGroupingCounts:
    """模式 / 子标记 / 跨类标记计数与注入的收集结果同源。"""

    @pytest.fixture(name="output")
    def fixture_output(self, mod, monkeypatch):
        small = str(mod.REPO_ROOT / "src" / "test" / "unit" / "scripts")
        return _run_main(mod, monkeypatch, _FIXTURE_RECORDS, [small])

    def test_total_matches_injected_records(self, mod, output):
        assert re.search(rf"总收集:\s*{len(_FIXTURE_RECORDS)}\s*项", output)

    def test_sections_present(self, output):
        for header in ("### 模式对应测试量", "### unit 子标记", "### scenario 子标记", "### 跨类标记"):
            assert header in output, header

    def test_mode_counts(self, output):
        modes = _section(output, "### 模式对应测试量")
        assert modes["unit"] == 3  # 4 条注入记录中带 unit 标记者
        assert modes["scenario"] == 1
        assert modes["edge"] == 1
        assert modes["smoke"] == 0
        assert modes["security"] == 0  # 无 scenario_security 记录

    def test_unit_sub_marker_counts(self, output):
        subs = _section(output, "### unit 子标记")
        assert subs["unit_scripts"] == 2
        assert subs["unit_llm"] == 1

    def test_cross_marker_counts(self, output):
        cross = _section(output, "### 跨类标记")
        assert cross["llm"] == 1
        assert cross["edge"] == 1
        assert cross["data"] == 0
        assert cross["smoke"] == 0

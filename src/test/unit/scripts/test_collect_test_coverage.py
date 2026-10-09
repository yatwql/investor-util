"""collect-test-coverage.py 收集与分组计数测试（退出码传递 / 目标展开 / 模式计数口径 / --update-docs 回写）。

覆盖 `_collect` 对 pytest 退出码的原样传递（含收集期失败 4 与空收集 5）、
`CollectPlugin` 的 nodeid+标记记录、`_target_files` 的目录展开与 live 套件排除、
模式谓词与 `_test_runner/modes.py::MODES` 的绑定、`main()` 的退出码出口与
模式/子标记计数输出，以及 `update_docs`/`--update-docs` 回写（保形改写 / 非计数
行跳过 / 写后过核对函数 / 幂等 / 收集失败与空收集的出口守卫）。
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
    from src.test._script_loader import load_script

    return load_script("collect-test-coverage.py")


class _StdoutStub(io.StringIO):
    """可被 `sys.stdout.reconfigure()` 调用的输出桩（真 StringIO 无该方法）。"""

    def reconfigure(self, *args, **kwargs):  # noqa: D102
        return None


def _run_main(mod, monkeypatch, records, targets, extra_args=()) -> str:
    """以注入的收集结果跑一次 `main()`，返回其完整标准输出。"""
    monkeypatch.setattr(sys, "argv", ["collect-test-coverage.py", *extra_args, *targets])
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


class TestModePredicateBinding:
    """模式计数谓词绑定到 `_test_runner/modes.py::MODES`（无手写表达式字典）。"""

    def test_reported_modes_are_registry_minus_omitted(self, mod):
        assert set(mod._MODE_PREDICATES) == set(mod.MODES) - set(mod._OMITTED_MODES)

    def test_omitted_modes_still_registered(self, mod):
        """豁免表若残留已删模式，本断言报出，避免静默陈旧。"""
        assert set(mod._OMITTED_MODES) <= set(mod.MODES)

    def test_omitted_modes_carry_reason(self, mod):
        assert all(str(reason).strip() for reason in mod._OMITTED_MODES.values())

    def test_every_reported_mode_resolves_expression(self, mod):
        """每个上报模式都能从 MODES 解析出表达式并编译（dev-verify 走阶段 marker）。"""
        for name in mod._MODE_PREDICATES:
            assert callable(mod.compile_marker_expr(mod.mode_marker_expr(name)))


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


# ═══ --update-docs 回写 ═══


class TestUpdateDocs:
    """`update_docs`/`--update-docs`：保形回写、非计数行跳过、写后过核对、幂等、出口守卫。"""

    @pytest.fixture()
    def docs(self, tmp_path, monkeypatch, mod):
        """陈旧计数的 test-coverage.md 与 folders.md（含各类应跳过行）。"""
        domain_rows = "\n".join(f"| **{label}** | 说明 | 555 |" for label in mod.UNIT_DOMAIN_LABELS.values())
        cov = tmp_path / "test-coverage.md"
        cov.write_text(
            "# 测试覆盖\n\n"
            "## 模式\n\n"
            "| 标记 | 计数 | 耗时 |\n"
            "|---|---|---|\n"
            "| `unit` | **9393** | ~31s |\n"
            "| `all` | **9746** | ~32s |\n"
            "| `unknown_key` | 111 | — |\n"
            "| `unit` | ~31s | ~3min |\n"
            "| **名称** | 表头加粗 | 222 |\n\n"
            f"## 功能域对应测试源\n\n{domain_rows}\n"
            "| **端到端业务场景** | 父标记行 | 555 |\n\n"
            "## 其它\n\n"
            "| **数据源 Provider** | 章外同标签 | 555 |\n",
            encoding="utf-8",
        )
        folds = tmp_path / "folders.md"
        folds.write_text(
            "# 目录\n\n"
            "| 项 | 一 | 二 | 计数 |\n"
            "|---|---|---|---|\n"
            "| 测试用例 | — | — | 9,750 个 |\n"
            "| 主程序 | — | — | 12,345 行 |\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(mod, "_TEST_COVERAGE_MD", cov)
        monkeypatch.setattr(mod, "_FOLDERS_MD", folds)
        return cov, folds

    @staticmethod
    def _snap(mod, total=42, val=7) -> dict[str, int]:
        """与 `_build_snapshot` 同形的快照（键集覆盖全部分节）。"""
        snap: dict[str, int] = {"_总收集": total}
        for name in mod._MODE_PREDICATES:
            snap[name] = val
        for s in (*mod.UNIT_SUBS, *mod.SCEN_SUBS, *mod.CROSS_SUBS):
            snap[s] = val
        for marker, label in mod.UNIT_DOMAIN_LABELS.items():
            snap[label] = snap[marker]
        return snap

    def test_stale_rows_rewritten_preserving_format(self, mod, docs):
        cov, folds = docs
        snap = self._snap(mod)
        changes = mod.update_docs(snap)
        text = cov.read_text(encoding="utf-8")
        assert "| `unit` | **7** | ~31s |" in text  # 粗体保留
        assert "| `all` | **42** | ~32s |" in text  # 别名 all → _总收集
        assert "| **端到端业务场景** | 父标记行 | 7 |" in text  # 聚合行走父标记 scenario
        assert "| **数据源 Provider** | 章外同标签 | 7 |" in text  # 章外同标签行同构改写
        ftext = folds.read_text(encoding="utf-8")
        assert "| 测试用例 | — | — | 42 个 |" in ftext  # 计数列改写、` 个` 后缀保留
        assert "| 主程序 | — | — | 12,345 行 |" in ftext  # 非测试用例行不动
        assert any(c.endswith("unit 9393 → 7") for c in changes)
        assert any(c.endswith("_总收集 9746 → 42") for c in changes)
        assert any("测试用例 9,750 → 42" in c for c in changes)

    def test_skipped_rows_untouched(self, mod, docs):
        cov, _ = docs
        mod.update_docs(self._snap(mod))
        text = cov.read_text(encoding="utf-8")
        assert "| `unknown_key` | 111 | — |" in text  # 键未入快照
        assert "| `unit` | ~31s | ~3min |" in text  # 无计数单元格
        assert "| **名称** | 表头加粗 | 222 |" in text  # 标签未映射

    def test_post_write_passes_count_check(self, mod, docs):
        from src.test._script_loader import load_script

        cov, _ = docs
        snap = self._snap(mod)
        mod.update_docs(snap)
        drift = load_script("check-doc-drift.py")
        assert drift.check_test_coverage_counts(cov.read_text(encoding="utf-8"), snap) == []

    def test_second_run_reports_no_changes(self, mod, docs):
        snap = self._snap(mod)
        assert mod.update_docs(snap)  # 首轮确有回写
        assert mod.update_docs(snap) == []  # 幂等：二轮零变更

    def test_main_update_docs_prints_summary(self, mod, monkeypatch, docs):
        cov, _ = docs
        out = _run_main(mod, monkeypatch, _FIXTURE_RECORDS, [], extra_args=["--update-docs"])
        assert "[更新] " in out
        assert "[OK] 已回写 " in out
        assert "**" in cov.read_text(encoding="utf-8")  # 真回写保留粗体
        again = _run_main(mod, monkeypatch, _FIXTURE_RECORDS, [], extra_args=["--update-docs"])
        assert "[OK] 计数与文档一致，无需回写" in again  # 二轮无回写

    def test_update_docs_skipped_when_collection_fails(self, mod, monkeypatch, docs, capsys):
        cov, _ = docs
        before = cov.read_text(encoding="utf-8")
        calls: list[dict] = []
        monkeypatch.setattr(mod, "update_docs", lambda snap: calls.append(snap) or [])
        monkeypatch.setattr(sys, "argv", ["collect-test-coverage.py", "--update-docs"])
        monkeypatch.setattr(mod, "_collect", lambda _targets: 2)
        mod.collected.clear()
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == 2
        assert calls == []  # 错数不回写
        assert cov.read_text(encoding="utf-8") == before
        assert "跳过文档回写" in capsys.readouterr().err

    def test_update_docs_allowed_on_empty_collection(self, mod, monkeypatch, docs):
        calls: list[dict] = []
        monkeypatch.setattr(mod, "update_docs", lambda snap: calls.append(snap) or [])
        monkeypatch.setattr(sys, "argv", ["collect-test-coverage.py", "--update-docs"])
        monkeypatch.setattr(mod, "_collect", lambda _targets: 5)  # NO_TESTS_COLLECTED 合法
        mod.collected.clear()
        mod.main()  # 不应 sys.exit
        assert len(calls) == 1

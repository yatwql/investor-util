"""测试：发布流程分步编排脚本 — release.py

覆盖：
  - 版本纯函数：开发版→发布版推导、补丁位递增、constants/README 行渲染、异常输入
  - changelog 发布段迁移：指针改写、归档索引区间延展、开发段清空与下一开发段生成、
    正文迁出（尾注不随迁）、版本不一致拒绝、索引缺失拒绝、归档文件追加
  - 预检：分支/工作树/版本形态/tag 条件与发布形态（publish 允许待提交改动）的行为
  - 版本演进：工作区口径统计（分类/行数/用例计数）、表两列写入与增长比、
    比值注释与用例口径注释、缺行拒绝、发布列仅在 --release 写入
  - 门禁：守护清单与 scripts/ 实体同源且互异、regression 先行、失败即停、
    最坏退出码传递
  - refresh：三步顺序执行、首步失败即停
  - publish：提交→verify→合并→tag 顺序与合并信息含 verify 项数、verify 失败中止、
    已提交时跳过、--push 才执行推送
  - prepare / devbump：文件手术落盘与预检失败中止（不落盘）
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


def _load_release_module():
    fpath = _SCRIPTS_DIR / "release.py"
    spec = importlib.util.spec_from_file_location("release_tool", fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rel():
    return _load_release_module()


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class FakeRunner:
    """脚本化子进程替身：按「命令片段全部出现」匹配应答，记录全部调用。"""

    def __init__(self, responses=None, default=(0, "", "")):
        self.responses = list(responses or [])
        self.default = default
        self.calls: list[list[str]] = []

    def run(self, cmd, root, capture=True):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        for matcher, resp in self.responses:
            if all(m in cmd for m in matcher):
                return resp
        return self.default


# ─────────────────────────── 版本纯函数 ───────────────────────────


class TestVersionMath:
    def test_release_version_of_accepts_dev(self, rel):
        assert rel.release_version_of("0.12.6-dev") == "0.12.6"

    def test_release_version_of_rejects_release_form(self, rel):
        with pytest.raises(rel.ReleaseError):
            rel.release_version_of("0.12.6")

    def test_next_dev_version_increments_patch(self, rel):
        assert rel.next_dev_version_of("0.12.6") == "0.12.7-dev"
        assert rel.next_dev_version_of("0.12.9") == "0.12.10-dev"

    def test_next_dev_version_rejects_dev_input(self, rel):
        with pytest.raises(rel.ReleaseError):
            rel.next_dev_version_of("0.12.6-dev")

    def test_render_app_version_roundtrip(self, rel):
        text = 'APP_VERSION = "0.12.6-dev"  # 当前版本\nOTHER = "x"\n'
        out = rel.render_app_version(text, "0.12.6")
        assert rel.read_app_version(out) == "0.12.6"
        assert "OTHER" in out

    def test_read_app_version_missing_raises(self, rel):
        with pytest.raises(rel.ReleaseError):
            rel.read_app_version("no version here\n")

    def test_render_readme_version_preserves_suffix(self, rel):
        text = "> 当前版本：0.12.6-dev（[版本历史](docs/managements/changelog.md)）\n"
        out = rel.render_readme_version(text, "0.12.6")
        assert out.startswith("> 当前版本：0.12.6（")
        assert "changelog.md" in out


# ─────────────────────────── changelog 发布段迁移 ───────────────────────────


def _sample_changelog(archive_name: str = "archived_changelog.0.12.x.md") -> str:
    return (
        "# 变更日志\n\n"
        "> **最近发布 [0.12.5]**（2026-10-07）——已发布版本段随发布移入 "
        f"[`{archive_name}`](../archive/v0.12.x/{archive_name})；本文件只保留当前开发版本段与归档索引。\n\n"
        "---\n\n\n"
        "## [0.12.6-dev] - 开发中（未发布）\n\n"
        "- **条目一**：内容甲 | rf-1\n"
        "- **条目二**：内容乙\n\n"
        "（本次发布内容见下方归档索引）\n\n"
        "## 归档\n\n"
        f"- [`{archive_name}`](../archive/v0.12.x/{archive_name}) — v0.12.1 ~ v0.12.5"
        "（2026-10-03 ~ 2026-10-07）\n"
        "- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)"
        " — v0.11.0 ~ v0.11.12（2026-09-15 ~ 2026-10-03）\n"
    )


class TestChangelogRelease:
    def test_pointer_and_next_dev_section_written(self, rel):
        out, _ = rel.apply_changelog_release(_sample_changelog(), "0.12.6", "2026-10-08")
        assert "> **最近发布 [0.12.6]**（2026-10-08）" in out
        assert "## [0.12.7-dev] - 开发中（未发布）" in out
        assert "内容甲" not in out  # 发布段正文迁出主文件

    def test_section_note_kept_in_main(self, rel):
        out, _ = rel.apply_changelog_release(_sample_changelog(), "0.12.6", "2026-10-08")
        assert rel._SECTION_NOTE in out
        assert out.index(rel._SECTION_NOTE) < out.index("## 归档")

    def test_migrated_body_excludes_section_note(self, rel):
        _, body = rel.apply_changelog_release(_sample_changelog(), "0.12.6", "2026-10-08")
        assert "内容甲" in body and "内容乙" in body
        assert rel._SECTION_NOTE not in body

    def test_archive_index_range_extended(self, rel):
        out, _ = rel.apply_changelog_release(_sample_changelog(), "0.12.6", "2026-10-08")
        assert "v0.12.1 ~ v0.12.6（2026-10-03 ~ 2026-10-08）" in out
        assert "v0.11.0 ~ v0.11.12（2026-09-15 ~ 2026-10-03）" in out  # 其余索引不动

    def test_version_mismatch_rejected(self, rel):
        with pytest.raises(rel.ReleaseError, match="不一致"):
            rel.apply_changelog_release(_sample_changelog(), "0.12.7", "2026-10-08")

    def test_missing_index_line_rejected(self, rel):
        with pytest.raises(rel.ReleaseError, match="归档索引"):
            rel.apply_changelog_release(_sample_changelog("archived_changelog.0.99.x.md"), "0.12.6", "2026-10-08")

    def test_write_archive_release_appends_and_accumulates(self, rel, tmp_path):
        archive = tmp_path / "archived_changelog.0.12.x.md"
        archive.write_text("# 归档\n\n头部说明\n", encoding="utf-8")
        rel.write_archive_release(archive, "0.12.6", "2026-10-08", "- 新条目")
        rel.write_archive_release(archive, "0.12.7", "2026-10-15", "- 次条目")
        text = archive.read_text(encoding="utf-8")
        assert text.count("## [") == 2
        assert text.index("## [0.12.6]") < text.index("## [0.12.7]")
        assert "头部说明" in text
        assert text.endswith("\n") and not text.endswith("\n\n")

    def test_write_archive_release_missing_file_raises(self, rel, tmp_path):
        with pytest.raises(rel.ReleaseError, match="归档文件不存在"):
            rel.write_archive_release(tmp_path / "nope.md", "0.12.6", "2026-10-08", "- x")


# ─────────────────────────── 预检 ───────────────────────────


def _preflight_runner(*, branch="dev", dirty=False, tag_exists=False, version_rc=0, form="-dev"):
    status = " M docs/x.md\n" if dirty else ""
    tag_rc = 0 if tag_exists else 1
    constants_text = f'APP_VERSION = "0.12.6{form}"\n'
    runner = FakeRunner(
        responses=[
            (["git", "branch", "--show-current"], (0, branch + "\n", "")),
            (["git", "status", "--porcelain"], (0, status, "")),
            (["git", "rev-parse"], (tag_rc, "" if tag_exists else "", "")),
            (["scripts/check-version-consistency.py"], (version_rc, "", "")),
        ]
    )
    return runner, constants_text


class TestPreflight:
    def _root(self, tmp_path: Path, constants_text: str) -> Path:
        cdir = tmp_path / "src" / "python" / "core"
        cdir.mkdir(parents=True)
        (cdir / "constants.py").write_text(constants_text, encoding="utf-8")
        return tmp_path

    def test_all_pass_on_clean_dev(self, rel, tmp_path):
        runner, text = _preflight_runner()
        results = rel.run_preflight(self._root(tmp_path, text), expect_release=False, runner=runner)
        assert all(ok for _, ok, _ in results), results
        names = [name for name, _, _ in results]
        assert "工作分支为 dev" in names and "工作树干净" in names

    def test_wrong_branch_fails(self, rel, tmp_path):
        runner, text = _preflight_runner(branch="master")
        results = rel.run_preflight(self._root(tmp_path, text), runner=runner)
        assert [ok for name, ok, _ in results if name == "工作分支为 dev"] == [False]

    def test_dirty_worktree_fails_when_required(self, rel, tmp_path):
        runner, text = _preflight_runner(dirty=True)
        results = rel.run_preflight(self._root(tmp_path, text), runner=runner)
        assert [ok for name, ok, _ in results if name == "工作树干净"] == [False]

    def test_publish_mode_skips_clean_check(self, rel, tmp_path):
        runner, text = _preflight_runner(dirty=True, form="")
        results = rel.run_preflight(self._root(tmp_path, text), expect_release=True, runner=runner, require_clean=False)
        names = [name for name, _, _ in results]
        assert "工作树干净" not in names
        assert all(ok for _, ok, _ in results), results

    def test_release_form_required_for_publish(self, rel, tmp_path):
        runner, text = _preflight_runner(dirty=True)  # 版本仍为 -dev
        results = rel.run_preflight(self._root(tmp_path, text), expect_release=True, runner=runner, require_clean=False)
        assert [ok for name, ok, _ in results if name == "版本为发布形态"] == [False]

    def test_existing_tag_blocks_release(self, rel, tmp_path):
        runner, text = _preflight_runner(form="", tag_exists=True)
        results = rel.run_preflight(self._root(tmp_path, text), expect_release=True, runner=runner, require_clean=False)
        assert [ok for name, ok, _ in results if "tag" in name] == [False]


# ─────────────────────────── 版本演进 ───────────────────────────


class TestEvolutionStats:
    @pytest.fixture
    def repo(self, tmp_path):
        files = {
            "src/python/app.py": "a = 1\nb = 2\n",  # 2 行
            "src/__init__.py": "",  # 空文件：按 1 行计（与 cat-file 口径一致）
            "src/test/test_app.py": "def test_one():\n    assert 1\n\ndef test_two():\n    pass\n",  # 2 用例
            "src/test/helpers.py": "# def test_ 提及应计入 grep 口径\ndef helper():\n    pass\n",
            "scripts/tool.py": "print('x')\n",
            "docs/notes.md": "# 标题\n内容\n",
            "src/static/tmpl/report_template.html": "<html>\n</html>\n",
            "docs/assets/diagram.svg": "<svg/>\n",
            "requirements.txt": "pandas\n",  # 非 md/py/html/svg：只进仓库合计
        }
        for rel_path, content in files.items():
            path = tmp_path / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
        return tmp_path

    def test_category_counts(self, rel, repo):
        stats = rel.build_evolution_stats(repo)
        assert stats["main_files"] == 2  # app.py + src/__init__.py
        assert stats["test_files"] == 2
        assert stats["scripts_files"] == 1
        assert stats["tmpl_files"] == 1
        assert stats["svg_files"] == 1
        assert stats["md_files"] == 1

    def test_line_counts_and_repo_totals(self, rel, repo):
        stats = rel.build_evolution_stats(repo)
        assert stats["main_lines"] == 3  # 空 __init__ 1 行 + app 2 行
        assert stats["five_files"] == 2 + 2 + 1 + 1 + 1
        assert stats["repo_files"] == 9
        assert stats["missing"] == 0
        assert stats["repo_lines"] == stats["five_lines"] + stats["md_lines"] + 1  # +requirements.txt

    def test_def_test_line_and_strict_counts(self, rel, repo):
        stats = rel.build_evolution_stats(repo)
        # grep 口径：test_app 2 行 + helpers 注释提及 1 行
        assert stats["def_test_lines"] == 3
        # 严格口径：注释行不算
        assert stats["def_test_strict"] == 2

    def test_line_count_without_trailing_newline(self, rel):
        assert rel._line_count(b"a\nb") == 2
        assert rel._line_count(b"a\nb\n") == 2
        assert rel._line_count(b"") == 1


_EVOLUTION_SAMPLE = (
    "| 指标 | 最初版本（首个提交 · 2026-06-27） | 最新发布（最近发布 tag v0.12.5 · 2026-10-07）"
    " | 当前开发版（0.12.6-dev · 本次重跑时的工作区 · 2026-10-07） | 增长（最初 → 当前） |\n"
    "| 主程序（`src/**/*.py`，不含测试） | 30 文件 / 7,258 行 | 335 文件 / 88,669 行"
    " | 335 文件 / 88,669 行 | 12.2×\n"
    "| 测试（`src/test/**/*.py`） | 13 文件 / 6,108 行 | 484 文件 / 140,058 行"
    " | 484 文件 / 140,058 行 | 22.9×\n"
    "| 辅助脚本（`scripts/*.py`） | 0（当时仅 `launch.sh` / `launch.ps1`） | 57 文件 / 13,990 行"
    " | 57 文件 / 13,990 行 | 新增\n"
    "| HTML 报告模板（`src/static/tmpl/*.html`） | 0（当时为 `src/tmpl/`：1 个 / 469 行）"
    " | 22 文件 / 4,874 行 | 22 文件 / 4,874 行 | 1 → 22\n"
    "| 架构图示（SVG） | 0 | 3 文件 / 337 行 | 3 文件 / 337 行 | 新增\n"
    "| 文档（`.md`） | 7 文件 / 1,355 行 | 176 文件 / 66,469 行 | 176 文件 / 66,469 行 | 49.1×\n"
    "| **代码文件合计**（前 5 项） | **43** | **901** | **901** | 21.0×\n"
    "| **代码行合计**（前 5 项） | **13,366** | **247,928** | **247,928** | 18.5×\n"
    "| **测试用例数**（`def test_` 行数口径） | **491** | **8,833** | **8,833** | 18.0×\n"
    "| 仓库文件总数 | 56 | 1,126 | 1,126 | 20.1×\n"
    "| 仓库总行数（全部跟踪文件） | 15,600 | 322,464 | 322,464 | 20.7×\n"
    '> - **测试用例数**采 `git grep -c "def test_"` 的**行数口径**（含注释/文档串中的 `def test_` 提及）：'
    "最初 491 → 当前 8,833；按更严格的「以 `def test_` 开头的定义行（含类方法缩进）」口径为 8,792；"
    "按 pytest 实际收集（含参数化展开）为 **9,259** 项（另 20 项 opt-in live 反选，全量 9,279）。\n"
    "> - **测试 / 主程序行数比**由 0.84:1（6,108 / 7,258）升至 **1.58:1**（140,058 / 88,669，最新发布点），"
    "当前工作区为 **1.58:1**（140,058 / 88,669）。\n"
)


def _stats(**overrides) -> dict:
    base = {
        "main_files": 400,
        "main_lines": 90_000,
        "test_files": 500,
        "test_lines": 140_000,
        "scripts_files": 58,
        "scripts_lines": 14_100,
        "tmpl_files": 23,
        "tmpl_lines": 4_900,
        "svg_files": 3,
        "svg_lines": 340,
        "md_files": 180,
        "md_lines": 67_000,
        "five_files": 984,
        "five_lines": 249_340,
        "def_test_lines": 8_900,
        "def_test_strict": 8_850,
        "repo_files": 1_200,
        "repo_lines": 330_000,
        "missing": 0,
    }
    base.update(overrides)
    return base


class TestEvolutionTable:
    def test_dev_column_only_when_release_flag_off(self, rel):
        out = rel.update_evolution_table(_EVOLUTION_SAMPLE, _stats(), with_release=False, date="2026-10-09")
        assert "| 335 文件 / 88,669 行 | 400 文件 / 90,000 行 |" in out  # 发布列冻结
        assert "| **901** | **984** |" in out

    def test_release_column_written_with_flag(self, rel):
        out = rel.update_evolution_table(_EVOLUTION_SAMPLE, _stats(), with_release=True, date="2026-10-09")
        assert "| 400 文件 / 90,000 行 | 400 文件 / 90,000 行 |" in out

    def test_growth_ratio_and_specials(self, rel):
        out = rel.update_evolution_table(_EVOLUTION_SAMPLE, _stats(), with_release=False, date="2026-10-09")
        assert "| 12.4×" in out  # 90,000 / 7,258（主程序行）
        assert "| 新增" in out  # 基线 0
        assert "| 1 → 23" in out  # 模板覆盖格式
        assert "2026-10-09）" in out  # 当前开发版列头日期

    def test_bold_cells_preserved(self, rel):
        out = rel.update_evolution_table(_EVOLUTION_SAMPLE, _stats(), with_release=False, date="2026-10-09")
        assert "| **984** |" in out and "| **249,340** |" in out and "| **8,900** |" in out

    def test_missing_row_rejected(self, rel):
        with pytest.raises(rel.ReleaseError, match="缺行"):
            rel.update_evolution_table("| 指标 | x | y | z | w |\n", _stats(), False, "2026-10-09")

    def test_ratio_note_dev_only_updates_workspace_pair(self, rel):
        text = "由 0.84:1 升至 **1.58:1**（140,058 / 88,669，最新发布点），当前工作区为 **1.58:1**（140,058 / 88,669）"
        out = rel.update_ratio_note(text, _stats(), with_release=False)
        assert "升至 **1.58:1**（140,058 / 88,669，最新发布点）" in out  # 发布点不动
        assert "当前工作区为 **1.56:1**（140,000 / 90,000）" in out

    def test_ratio_note_release_updates_both_pairs(self, rel):
        text = "升至 **1.58:1**（140,058 / 88,669，最新发布点），当前工作区为 **1.58:1**（140,058 / 88,669）"
        out = rel.update_ratio_note(text, _stats(), with_release=True)
        assert out.count("1.56:1") == 2
        assert "140,000 / 90,000" in out

    def test_case_note_updates_grep_and_strict(self, rel):
        # 真实排版：短语位于行中（「…提及）：最初 491 → 当前 …」），不得依赖行首锚定
        text = "行数口径（含 `def test_` 提及）：最初 491 → 当前 8,833；按严格口径为 8,792；收集 9,259"
        out = rel.update_case_note(text, _stats())
        assert "提及）：最初 491 → 当前 8,900" in out
        assert "严格口径为 8,850" in out
        assert "9,259" in out  # pytest 收集口径不代写

    def test_case_note_missing_pattern_raises(self, rel):
        with pytest.raises(rel.ReleaseError, match="最初"):
            rel.update_case_note("没有任何口径短语的文本", _stats())
        with pytest.raises(rel.ReleaseError, match="口径为"):
            rel.update_case_note("最初 1 → 当前 2，但缺第二个模式", _stats())

    def test_ratio_note_missing_pattern_raises(self, rel):
        with pytest.raises(rel.ReleaseError, match="当前工作区"):
            rel.update_ratio_note("没有比值短语", _stats(), with_release=False)
        with pytest.raises(rel.ReleaseError, match="最新发布点"):
            rel.update_ratio_note("当前工作区为 **1.58:1**（140,058 / 88,669）", _stats(), with_release=True)

    def test_evolution_table_missing_date_header_raises(self, rel):
        mangled = _EVOLUTION_SAMPLE.replace("· 本次重跑时的工作区 · 2026-10-07", "· 滚动读数")
        with pytest.raises(rel.ReleaseError, match="列头日期"):
            rel.update_evolution_table(mangled, _stats(), False, "2026-10-09")


# ─────────────────────────── 门禁 ───────────────────────────


class TestGate:
    def test_guard_scripts_exist_and_unique(self, rel):
        assert len(rel.GUARD_SCRIPTS) == len(set(rel.GUARD_SCRIPTS))
        for script in rel.GUARD_SCRIPTS:
            path = _REPO_ROOT / script
            assert path.is_file(), script
            assert script.startswith("scripts/check-"), script

    def test_gate_runs_regression_then_guards(self, rel):
        runner = FakeRunner()
        rc = rel.cmd_gate(ns(), runner=runner)
        assert rc == 0
        first = runner.calls[0]
        assert "test-runner" in first[1]
        assert "--mode" in first and "regression" in first
        guard_calls = [c for c in runner.calls if any("check-" in part for part in c)]
        assert len(guard_calls) == len(rel.GUARD_SCRIPTS)
        assert all("--ci" in c for c in guard_calls)

    def test_gate_stops_on_regression_failure(self, rel):
        runner = FakeRunner(responses=[(["scripts/test-runner.py"], (1, "", "boom"))])
        rc = rel.cmd_gate(ns(), runner=runner)
        assert rc == 1
        assert len(runner.calls) == 1  # 回归失败 → 十守护一个不跑

    def test_gate_returns_worst_guard_code(self, rel):
        responses = [
            (["scripts/test-runner.py"], (0, "", "")),
            ([rel.GUARD_SCRIPTS[3]], (2, "finding: x", "")),
        ]
        rc = rel.cmd_gate(ns(), runner=FakeRunner(responses=responses))
        assert rc == 2


# ─────────────────────────── refresh / evolution 命令 ───────────────────────────


class TestRefresh:
    def test_three_steps_in_order(self, rel):
        runner = FakeRunner()
        rc = rel.cmd_refresh(ns(), runner=runner)
        assert rc == 0
        assert len(runner.calls) == 3
        assert any("bench" in p for p in runner.calls[0])
        assert any("collect-test-coverage" in p for p in runner.calls[1])
        assert any("check-doc-drift" in p for p in runner.calls[2])

    def test_first_step_failure_stops_chain(self, rel):
        runner = FakeRunner(responses=[(["scripts/test-runner.py"], (5, "", "x"))])
        rc = rel.cmd_refresh(ns(), runner=runner)
        assert rc == 5
        assert len(runner.calls) == 1


class _ToolRepoFixture:
    """把 release 模块的输出路径重定向到临时目录，并构造最小文件集。"""

    def __init__(self, rel_mod, tmp_path: Path):
        self.mod = rel_mod
        self.root = tmp_path
        core = tmp_path / "src" / "python" / "core"
        core.mkdir(parents=True)
        docs = tmp_path / "docs" / "managements"
        docs.mkdir(parents=True)
        archive = tmp_path / "docs" / "archive" / "v0.12.x"
        archive.mkdir(parents=True)
        (core / "constants.py").write_text('APP_VERSION = "0.12.6-dev"\n', encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "> 当前版本：0.12.6-dev（[版本历史](docs/managements/changelog.md)）\n", encoding="utf-8"
        )
        (docs / "changelog.md").write_text(_sample_changelog(), encoding="utf-8")
        (archive / "archived_changelog.0.12.x.md").write_text("# 归档\n", encoding="utf-8")
        (docs / "folders.md").write_text(_EVOLUTION_SAMPLE, encoding="utf-8")
        paths = {
            "REPO_ROOT": tmp_path,
            "CONSTANTS_FILE": core / "constants.py",
            "README_FILE": tmp_path / "README.md",
            "CHANGELOG_FILE": docs / "changelog.md",
            "FOLDERS_FILE": docs / "folders.md",
        }
        for name, value in paths.items():
            setattr(rel_mod, name, value)
            setattr(self, name, value)


def _ok_runner(overrides: list | None = None) -> FakeRunner:
    """预检/一致性/git 默认全过（工作树干净）；各测试按需覆写单条。"""
    pairs: list[tuple] = [
        (["git", "branch", "--show-current"], (0, "dev\n", "")),
        (["git", "status", "--porcelain"], (0, "", "")),
        (["git", "rev-parse"], (1, "", "")),
        (["scripts/check-version-consistency.py"], (0, "[OK] 15/15\n", "")),
        (["git", "status", "--short"], (0, " M docs/x.md\n", "")),
    ]
    for matcher, resp in overrides or []:
        pairs = [p for p in pairs if p[0] != matcher] + [(matcher, resp)]
    return FakeRunner(responses=pairs)


class TestEvolutionCommand:
    def test_command_updates_folders_snapshot(self, rel, tmp_path, capsys):
        fx = _ToolRepoFixture(rel, tmp_path)
        runner = FakeRunner(responses=[(["git", "ls-files"], (0, "docs/managements/folders.md\n", ""))])
        rc = rel.cmd_evolution(ns(release=False), runner=runner)
        assert rc == 0
        text = fx.FOLDERS_FILE.read_text(encoding="utf-8")
        import datetime as dt

        today = dt.date.today().isoformat()
        assert f"本次重跑时的工作区 · {today}" in text
        assert "已更新" in capsys.readouterr().out


# ─────────────────────────── prepare / publish / devbump ───────────────────────────


class TestPrepare:
    def test_full_surgery_lands_on_disk(self, rel, tmp_path):
        fx = _ToolRepoFixture(rel, tmp_path)
        runner = _ok_runner()
        rc = rel.cmd_prepare(ns(version=None, date="2026-10-08"), runner=runner)
        assert rc == 0
        assert rel.read_app_version(fx.CONSTANTS_FILE.read_text(encoding="utf-8")) == "0.12.6"
        readme = fx.README_FILE.read_text(encoding="utf-8")
        assert readme.startswith("> 当前版本：0.12.6（")
        changelog = fx.CHANGELOG_FILE.read_text(encoding="utf-8")
        assert "## [0.12.7-dev] - 开发中（未发布）" in changelog
        assert "v0.12.1 ~ v0.12.6（2026-10-03 ~ 2026-10-08）" in changelog
        archived = (fx.root / "docs" / "archive" / "v0.12.x" / "archived_changelog.0.12.x.md").read_text(
            encoding="utf-8"
        )
        assert "## [0.12.6] - 2026-10-08" in archived and "内容甲" in archived
        assert any(any("check-version-consistency.py" in p for p in c) and "--fix" in c for c in runner.calls)

    def test_preflight_failure_leaves_files_untouched(self, rel, tmp_path):
        fx = _ToolRepoFixture(rel, tmp_path)
        runner = _ok_runner([(["git", "branch", "--show-current"], (0, "master\n", ""))])
        rc = rel.cmd_prepare(ns(version=None, date=None), runner=runner)
        assert rc == 2
        assert "0.12.6-dev" in fx.CONSTANTS_FILE.read_text(encoding="utf-8")
        assert "内容甲" in fx.CHANGELOG_FILE.read_text(encoding="utf-8")


class TestPublish:
    def _fixture(self, rel_mod, tmp_path, version: str):
        fx = _ToolRepoFixture(rel_mod, tmp_path)
        fx.CONSTANTS_FILE.write_text(f'APP_VERSION = "{version}"\n', encoding="utf-8")
        return fx

    @staticmethod
    def _dirty_runner(verify_out="— 8,621 通过, 0 失败\n", verify_rc=0) -> FakeRunner:
        return _ok_runner(
            [
                (["git", "status", "--porcelain"], (0, " M docs/x.md\n", "")),
                (["scripts/test-runner.py"], (verify_rc, verify_out, "")),
            ]
        )

    def test_commit_verify_merge_tag_order(self, rel, tmp_path):
        self._fixture(rel, tmp_path, "0.12.6")
        runner = self._dirty_runner()
        rc = rel.cmd_publish(ns(title="主题", push=False), runner=runner)
        assert rc == 0
        commit_idx = next(i for i, c in enumerate(runner.calls) if len(c) > 2 and c[1] == "commit")
        verify_idx = next(i for i, c in enumerate(runner.calls) if any("test-runner.py" in p for p in c))
        merge_idx = next(i for i, c in enumerate(runner.calls) if len(c) > 2 and c[1] == "merge")
        tag_idx = next(i for i, c in enumerate(runner.calls) if len(c) > 2 and c[1] == "tag")
        assert "release: v0.12.6 —— 主题" in runner.calls[commit_idx][-1]
        assert commit_idx < verify_idx < merge_idx < tag_idx
        merge_msg = runner.calls[merge_idx][runner.calls[merge_idx].index("-m") + 1]
        assert "8621 项已全绿" in merge_msg
        assert not any("push" in c for c in runner.calls)  # 默认不推送

    def test_verify_failure_aborts_before_merge(self, rel, tmp_path):
        self._fixture(rel, tmp_path, "0.12.6")
        runner = self._dirty_runner(verify_out="", verify_rc=1)
        rc = rel.cmd_publish(ns(title="t", push=False), runner=runner)
        assert rc == 1
        heads = [c[1] for c in runner.calls if c[0] == "git"]
        assert "merge" not in heads and "tag" not in heads and "checkout" not in heads

    def test_skips_commit_when_tree_clean(self, rel, tmp_path):
        self._fixture(rel, tmp_path, "0.12.6")
        runner = _ok_runner([(["scripts/test-runner.py"], (0, "— 10 通过, 0 失败\n", ""))])
        rc = rel.cmd_publish(ns(title="t", push=False), runner=runner)
        assert rc == 0
        assert not any(len(c) > 2 and c[1] in {"add", "commit"} for c in runner.calls)

    def test_push_flag_gates_push_calls(self, rel, tmp_path):
        self._fixture(rel, tmp_path, "0.12.6")
        runner = _ok_runner([(["scripts/test-runner.py"], (0, "— 10 通过, 0 失败\n", ""))])
        rc = rel.cmd_publish(ns(title="t", push=True), runner=runner)
        assert rc == 0
        pushed = [c for c in runner.calls if "push" in c]
        assert len(pushed) == 3  # dev / master / --tags


class TestDevBump:
    def test_writes_next_dev_and_commits(self, rel, tmp_path):
        fx = _ToolRepoFixture(rel, tmp_path)
        fx.CONSTANTS_FILE.write_text('APP_VERSION = "0.12.6"\n', encoding="utf-8")
        runner = _ok_runner([(["git", "status", "--porcelain"], (0, " M docs/x.md\n", ""))])
        rc = rel.cmd_devbump(ns(push=False), runner=runner)
        assert rc == 0
        assert rel.read_app_version(fx.CONSTANTS_FILE.read_text(encoding="utf-8")) == "0.12.7-dev"
        commit = next(c for c in runner.calls if len(c) > 2 and c[1] == "commit")
        assert commit[-1] == "chore: 切 0.12.7-dev 开发版本（v0.12.6 发布后）"
        assert not any("push" in c for c in runner.calls)

    def test_rejects_non_dev_branch(self, rel, tmp_path):
        fx = _ToolRepoFixture(rel, tmp_path)
        fx.CONSTANTS_FILE.write_text('APP_VERSION = "0.12.6"\n', encoding="utf-8")
        runner = _ok_runner([(["git", "branch", "--show-current"], (0, "master\n", ""))])
        rc = rel.cmd_devbump(ns(push=False), runner=runner)
        assert rc == 2
        assert rel.read_app_version(fx.CONSTANTS_FILE.read_text(encoding="utf-8")) == "0.12.6"


class TestCliSurface:
    def test_parser_and_handler_tables_agree(self, rel):
        parser = rel.build_parser()
        sub_actions = [a for a in parser._subparsers._group_actions if hasattr(a, "choices")]
        parser_cmds = set(sub_actions[0].choices) if sub_actions else set()
        handlers = {"check", "prepare", "refresh", "evolution", "gate", "publish", "devbump"}
        assert parser_cmds == handlers  # 两张内部表双向一致（结构断言，不写死条数）
        assert all(hasattr(rel, f"cmd_{name}") for name in handlers)

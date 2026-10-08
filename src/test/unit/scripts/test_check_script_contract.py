"""check-script-contract.py 契约机检测试（四条规则命中 / 白名单 / 退出码声明解析）。

覆盖：退出码章节的码集解析（章节头匹配、正文数字不串入、未声明返回 None）、
规则①②③④ 在合成脚本上的命中与豁免路径、白名单与实际声明一致，
以及真实仓库上规则①③④ 零偏离。
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts, pytest.mark.usefixtures("offline_external_sources")]


@pytest.fixture(name="mod")
def fixture_mod():
    """加载 `scripts/check-script-contract.py` 为可测模块。"""
    from src.test.unit.scripts.test_perf_report import _load_script

    return _load_script("check-script-contract.py")


def _script(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _rule(findings: list[str], tag: str) -> list[str]:
    """只取某条规则的 finding（合成脚本会在其它规则上产生预期外命中）。"""
    return [item for item in findings if item.startswith(tag)]


def _run_main(mod, monkeypatch, *argv: str) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["check-script-contract.py", *argv])
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = mod.main()
    return int(code), buf.getvalue()


# ── 退出码章节解析 ──


class TestDeclaredExitCodes:
    """规则① 的输入解析：认章节头，不认正文里的数字。"""

    def test_multiline_section(self, mod, tmp_path):
        path = _script(tmp_path, "a.py", '"""说明。\n\n退出码：\n  0 — 全部通过\n  2 — 发现问题\n"""\n')
        assert mod.declared_exit_codes(path) == {0, 2}

    def test_inline_section(self, mod, tmp_path):
        path = _script(tmp_path, "b.py", '"""说明。\n\n退出码：0 = 通过；1 = 失败；2 = 错误。\n"""\n')
        assert mod.declared_exit_codes(path) == {0, 1, 2}

    def test_no_section_returns_none(self, mod, tmp_path):
        path = _script(tmp_path, "c.py", '"""只有说明。\n"""\n')
        assert mod.declared_exit_codes(path) is None

    def test_prose_without_colon_not_treated_as_section(self, mod, tmp_path):
        path = _script(tmp_path, "d.py", '"""说明。\n\n退出码声明：这里只是正文提及，没有独立章节。\n"""\n')
        assert mod.declared_exit_codes(path) is None

    def test_digits_after_blank_line_excluded(self, mod, tmp_path):
        body = '"""说明。\n\n退出码：\n  0 — 通过\n  2 — 发现\n\n环境要求 Python 3.11。\n"""\n'
        assert mod.declared_exit_codes(_script(tmp_path, "e.py", body)) == {0, 2}

    def test_no_docstring_returns_none(self, mod, tmp_path):
        assert mod.declared_exit_codes(_script(tmp_path, "f.py", "x = 1\n")) is None


# ── 规则① 退出码声明 ──


class TestExitCodeRule:
    """码集须落在 `_checklib.report` 返回值域 {0, 2}，除非在白名单。"""

    def test_within_contract_passes(self, mod, tmp_path):
        path = _script(tmp_path, "check-ok.py", '"""说明。\n\n退出码：\n  0 — 通过\n  2 — 发现\n"""\n')
        assert _rule(mod.script_findings(path), "[exit-code]") == []

    def test_beyond_contract_flagged(self, mod, tmp_path):
        path = _script(tmp_path, "check-bad.py", '"""说明。\n\n退出码：\n  0 — 通过\n  1 — 出错\n"""\n')
        assert len(_rule(mod.script_findings(path), "[exit-code]")) == 1

    def test_whitelisted_script_allowed(self, mod, tmp_path):
        body = '"""说明。\n\n退出码：\n  0 — 通过\n  1 — 分级\n  3 — 低置信\n"""\n'
        path = _script(tmp_path, "check-code-traces.py", body)
        assert _rule(mod.script_findings(path), "[exit-code]") == []

    def test_non_check_script_without_report_import_exempt(self, mod, tmp_path):
        path = _script(tmp_path, "tool.py", '"""说明。\n\n退出码：0 = 好；1 = 坏。\n"""\n')
        assert _rule(mod.script_findings(path), "[exit-code]") == []

    def test_report_consumer_scope(self, mod, tmp_path):
        body = '"""说明。\n\n退出码：\n  0 — 通过\n  1 — 出错\n"""\nfrom _checklib import report\n'
        hits = _rule(mod.script_findings(_script(tmp_path, "tool_two.py", body)), "[exit-code]")
        assert len(hits) == 1

    def test_whitelist_entries_match_real_declarations(self, mod):
        """白名单不许挂账：键须是真实脚本，声明码集须与白名单完全一致。"""
        assert set(mod._EXIT_CODE_WHITELIST) <= {p.name for p in mod.top_level_scripts()}
        for name, allowed in mod._EXIT_CODE_WHITELIST.items():
            assert mod.declared_exit_codes(mod.SCRIPTS_DIR / name) == set(allowed)

    def test_exemption_names_exist(self, mod):
        names = {p.name for p in mod.top_level_scripts()}
        assert set(mod._CLI_SURFACE_EXEMPT) <= names
        assert set(mod._UNTESTED_EXEMPT) <= names


# ── 规则② 检查类 CLI 面 ──


class TestCliSurfaceRule:
    """`check-*` 须调用 `_checklib.add_common_args`。"""

    def test_missing_common_args_flagged(self, mod, tmp_path):
        path = _script(tmp_path, "check-x.py", '"""说明。\n"""\nimport argparse\n')
        assert len(_rule(mod.script_findings(path), "[cli-surface]")) == 1

    def test_with_common_args_passes(self, mod, tmp_path):
        body = '"""说明。\n"""\nimport argparse\nfrom _checklib import add_common_args\nparser = add_common_args()\n'
        assert _rule(mod.script_findings(_script(tmp_path, "check-y.py", body)), "[cli-surface]") == []

    def test_hook_entry_exempt(self, mod, tmp_path):
        path = _script(tmp_path, "check-task-numbering-hook.py", '"""说明。\n"""\nimport sys\n')
        assert _rule(mod.script_findings(path), "[cli-surface]") == []

    def test_non_check_script_not_applicable(self, mod, tmp_path):
        path = _script(tmp_path, "helper.py", '"""说明。\n"""\nimport sys\n')
        assert _rule(mod.script_findings(path), "[cli-surface]") == []


# ── 规则③ 文本 I/O 编码 ──


class TestEncodingRule:
    """文本 I/O 一律显式 encoding=，二进制与非内建 open 不受限。"""

    @pytest.mark.parametrize(
        ("line", "flagged"),
        [
            ("f = open(p)", True),
            ('f = open(p, encoding="utf-8")', False),
            ('f = open(p, "rb")', False),
            ('f = open(p, mode="wb")', False),
            ("f = Path(p).read_text()", True),
            ('f = Path(p).read_text(encoding="utf-8")', False),
            ("f = Path(p).write_text('x')", True),
            ('f = Path(p).write_text("x", encoding="utf-8")', False),
            ("f = image.open(p)", False),
            ("subprocess.run(cmd, text=True)", True),
            ('subprocess.run(cmd, text=True, encoding="utf-8")', False),
            ("subprocess.run(cmd, capture_output=True)", False),
        ],
    )
    def test_line_level(self, mod, tmp_path, line, flagged):
        body = '"""说明。\n"""\nfrom pathlib import Path\nimport subprocess\n' + line + "\n"
        hits = _rule(mod.script_findings(_script(tmp_path, "probe_tool.py", body)), "[encoding]")
        assert bool(hits) is flagged


# ── 规则④ 测试覆盖 ──


class TestCoverageRule:
    """顶层脚本须被 `src/test/` 下测试按文件名引用，一次性工具豁免。"""

    def test_referenced_script_passes(self, mod, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "has_test_reference", lambda _name: True)
        path = _script(tmp_path, "tool.py", '"""说明。\n"""\n')
        assert _rule(mod.script_findings(path), "[test-coverage]") == []

    def test_unreferenced_script_flagged(self, mod, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "has_test_reference", lambda _name: False)
        path = _script(tmp_path, "tool.py", '"""说明。\n"""\n')
        assert len(_rule(mod.script_findings(path), "[test-coverage]")) == 1

    def test_exempt_script_not_flagged(self, mod, tmp_path, monkeypatch):
        """豁免优先于引用：一次性工具即使无测试也不报（用 mock 避开本文件自引用）。"""
        monkeypatch.setattr(mod, "has_test_reference", lambda _name: False)
        path = _script(tmp_path, "probe-push2.py", '"""说明。\n"""\n')
        assert _rule(mod.script_findings(path), "[test-coverage]") == []

    def test_reference_lookup(self, mod):
        assert mod.has_test_reference("check-script-contract.py") is True
        # 名称动态拼接：本测试文件自身不得成为「被引用」的证据
        missing = "-".join(["no", "such", "script"]) + ".py"
        assert mod.has_test_reference(missing) is False


# ── 真实仓库 ──


class TestRealRepoContract:
    """真实仓库上退出码 / 编码 / 测试覆盖三条规则零偏离（CLI 面由后续接线计划收口）。"""

    @pytest.fixture(name="repo_findings")
    def fixture_repo_findings(self, mod):
        out: list[str] = []
        for path in mod.top_level_scripts():
            out.extend(f"{path.name}: {item}" for item in mod.script_findings(path))
        return out

    @pytest.mark.parametrize("rule", ["[exit-code]", "[encoding]", "[test-coverage]"])
    def test_rule_clean_on_repo(self, repo_findings, rule):
        assert [f for f in repo_findings if rule in f] == []

    def test_cli_surface_findings_only_pending_scripts(self, repo_findings):
        offenders = {f.split(":")[0] for f in repo_findings if "[cli-surface]" in f}
        assert offenders <= {"check-code-traces.py"}

    def test_main_returns_contract_code(self, mod, monkeypatch):
        code, output = _run_main(mod, monkeypatch, "--ci")
        assert code in (0, 2)
        assert ("[OK]" in output) == (code == 0)

    def test_verbose_lists_ok_scripts(self, mod, monkeypatch):
        code, output = _run_main(mod, monkeypatch, "-v")
        assert "[OK] check-script-contract.py" in output
        assert code in (0, 2)

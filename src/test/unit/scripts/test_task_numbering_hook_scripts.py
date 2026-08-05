"""测试：任务编号自动保障机制脚本

覆盖：
  - check-task-numbering-hook.py
      - 编辑编号文档（plan.md / review-findings.md）→ 触发校验
      - 编辑非编号文档 → 放行
      - 无 hook 上下文 / 非法 JSON → 放行
      - 校验脚本失败 → 非零退出码（拦截编辑）
      - 校验脚本不可运行（OSError）→ 放行
      - 同时兼容环境变量与命令行参数两种注入方式
  - install-claude-hook.py
      - 幂等安装（重复安装不重复写）
      - 合并式安装（保留已有配置，仅追加 hook）
      - 卸载（移除本 hook，保留其他配置）

测试隔离：**不触碰真实 plan.md / review-findings.md / .claude/settings.json**。
所有文件路径（注入的 tool_input.file_path、校验脚本、settings 路径）均
用 tmp_path 构造的假文件；子进程调用全部 mock，即使 mock 失效也只执行
tmp_path 下的假脚本。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # 仓库根目录（src/test/unit/scripts 向上 4 级）
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_script(name: str):
    """按文件名加载 scripts/ 下的脚本（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hook():
    return _load_script("check-task-numbering-hook.py")


@pytest.fixture(scope="module")
def installer():
    return _load_script("install-claude-hook.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


def _inject_payload(tool_name: str, file_path: str) -> dict:
    """构造 Claude Code 注入的 tool_input JSON。"""
    return {
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
    }


def _fake_doc(tmp_path: Path, name: str) -> Path:
    """在 tmp_path 下构造假文档（名为 plan.md / review-findings.md / 其他）。"""
    p = tmp_path / name
    p.write_text("dummy content", encoding="utf-8")
    return p


# ── check-task-numbering-hook.py: 目标文档判定 ───────────────────────


def test_hook_is_target_doc_plan(hook, tmp_path: Path):
    """编辑名为 plan.md 的文件（tmp_path 假文档）→ 目标文档。"""
    fake = _fake_doc(tmp_path, "plan.md")
    ti = _inject_payload("Edit", str(fake))
    assert hook._is_target_doc(ti["tool_input"]) is True


def test_hook_is_target_doc_review_findings(hook, tmp_path: Path):
    """编辑名为 review-findings.md 的文件（tmp_path 假文档）→ 目标文档。"""
    fake = _fake_doc(tmp_path, "review-findings.md")
    ti = _inject_payload("Edit", str(fake))
    assert hook._is_target_doc(ti["tool_input"]) is True


def test_hook_is_target_doc_other(hook, tmp_path: Path):
    """编辑其他文件（tmp_path 假文档）→ 非目标文档。"""
    fake = _fake_doc(tmp_path, "constants.py")
    ti = _inject_payload("Edit", str(fake))
    assert hook._is_target_doc(ti["tool_input"]) is False


# ── check-task-numbering-hook.py: main 放行分支 ─────────────────────


def test_hook_main_no_context_passes(hook):
    """无 __INJECTED_OBJECT__ 上下文 → 放行（exit 0）。"""
    with mock.patch.dict("os.environ", {}, clear=True):
        assert hook.main() == 0


def test_hook_main_bad_json_passes(hook):
    """非法 JSON → 放行（不阻断编辑）。"""
    with mock.patch.dict("os.environ", {"__INJECTED_OBJECT__": "{not-json"}, clear=True):
        assert hook.main() == 0


def test_hook_main_non_target_doc_passes(hook, tmp_path: Path):
    """编辑非编号文档 → 放行（不触发子进程）。"""
    fake = _fake_doc(tmp_path, "constants.py")
    payload = json.dumps(_inject_payload("Edit", str(fake)))
    with mock.patch.dict("os.environ", {"__INJECTED_OBJECT__": payload}, clear=True):
        with mock.patch("subprocess.run") as run:
            assert hook.main() == 0
            run.assert_not_called()


# ── check-task-numbering-hook.py: main 校验分支 ─────────────────────


def test_hook_main_check_pass(hook, tmp_path: Path, monkeypatch):
    """目标文档 + 校验通过 → 放行（exit 0）。

    校验脚本 monkeypatch 为 tmp_path 假脚本，确保即使 subprocess 执行
    也只会碰假文件，不触碰真实 check-task-numbering.py。
    """
    fake = _fake_doc(tmp_path, "plan.md")
    payload = json.dumps(_inject_payload("Edit", str(fake)))
    fake_check = tmp_path / "check-task-numbering.py"
    fake_check.write_text("", encoding="utf-8")
    monkeypatch.setattr(hook, "_CHECK_SCRIPT", fake_check)

    proc = mock.Mock()
    proc.returncode = 0
    proc.stdout = ""
    proc.stderr = ""
    with mock.patch.dict("os.environ", {"__INJECTED_OBJECT__": payload}, clear=True):
        with mock.patch("subprocess.run", return_value=proc) as run:
            assert hook.main() == 0
            run.assert_called_once()
            assert str(fake_check) in run.call_args.args[0]  # 执行的是假脚本


def test_hook_main_check_fail_blocks(hook, tmp_path: Path, monkeypatch):
    """目标文档 + 校验失败 → 非零退出码（拦截编辑）。"""
    fake = _fake_doc(tmp_path, "review-findings.md")
    payload = json.dumps(_inject_payload("Edit", str(fake)))
    fake_check = tmp_path / "check-task-numbering.py"
    fake_check.write_text("", encoding="utf-8")
    monkeypatch.setattr(hook, "_CHECK_SCRIPT", fake_check)

    proc = mock.Mock()
    proc.returncode = 1
    proc.stdout = "[ERR] conflict"
    proc.stderr = ""
    with mock.patch.dict("os.environ", {"__INJECTED_OBJECT__": payload}, clear=True):
        with mock.patch("subprocess.run", return_value=proc):
            assert hook.main() == 1


def test_hook_main_script_oserror_passes(hook, tmp_path: Path, monkeypatch):
    """校验脚本不可运行（OSError）→ 放行（不阻断编辑）。"""
    fake = _fake_doc(tmp_path, "plan.md")
    payload = json.dumps(_inject_payload("Edit", str(fake)))
    fake_check = tmp_path / "check-task-numbering.py"
    monkeypatch.setattr(hook, "_CHECK_SCRIPT", fake_check)

    with mock.patch.dict("os.environ", {"__INJECTED_OBJECT__": payload}, clear=True):
        with mock.patch("subprocess.run", side_effect=OSError):
            assert hook.main() == 0


def test_hook_main_argv_injection(hook, tmp_path: Path, monkeypatch):
    """命令行参数注入方式（settings.json 实际传法）同样生效。"""
    fake = _fake_doc(tmp_path, "review-findings.md")
    payload = json.dumps(_inject_payload("Edit", str(fake)))
    fake_check = tmp_path / "check-task-numbering.py"
    fake_check.write_text("", encoding="utf-8")
    monkeypatch.setattr(hook, "_CHECK_SCRIPT", fake_check)

    proc = mock.Mock()
    proc.returncode = 1
    proc.stdout = ""
    proc.stderr = ""
    with mock.patch.dict("os.environ", {}, clear=True):
        with mock.patch("subprocess.run", return_value=proc):
            with mock.patch.object(hook.sys, "argv", ["hook", payload]):
                assert hook.main() == 1


# ── install-claude-hook.py: 幂等/合并/卸载 ──────────────────────────


def test_install_idempotent(installer, tmp_path: Path, monkeypatch):
    """重复安装幂等：settings.json 已含 hook 时不重复写。"""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    existing = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Edit|Write",
                    "hooks": [{"type": "command", "command": installer._HOOK_CMD}],
                }
            ]
        }
    }
    settings.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(installer, "_SETTINGS_PATH", settings)

    assert installer.install() == 0
    assert len(json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PostToolUse"]) == 1


def test_install_merges_existing(installer, tmp_path: Path, monkeypatch):
    """合并式安装：保留已有配置（如 permissions），仅追加 hook。"""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text('{"permissions": {"allow": ["Bash(python *)"]}}', encoding="utf-8")
    monkeypatch.setattr(installer, "_SETTINGS_PATH", settings)

    assert installer.install() == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["permissions"]["allow"] == ["Bash(python *)"]  # 保留
    assert len(data["hooks"]["PostToolUse"]) == 1  # 追加 hook


def test_uninstall_removes_hook(installer, tmp_path: Path, monkeypatch):
    """卸载：移除本 hook，保留其他 hooks。"""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    existing = {
        "hooks": {
            "PostToolUse": [
                {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": installer._HOOK_CMD}]},
                {"matcher": "Write", "hooks": [{"type": "command", "command": "python other-hook.py"}]},
            ]
        }
    }
    settings.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(installer, "_SETTINGS_PATH", settings)

    assert installer.uninstall() == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    remaining = data["hooks"]["PostToolUse"]
    assert len(remaining) == 1
    assert "other-hook.py" in json.dumps(remaining)


def test_uninstall_no_hook_passes(installer, tmp_path: Path, monkeypatch):
    """无本 hook 时卸载 → 直接通过，且不写回多余内容。"""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text('{"hooks": {"PostToolUse": []}}', encoding="utf-8")
    monkeypatch.setattr(installer, "_SETTINGS_PATH", settings)

    assert installer.uninstall() == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"]["PostToolUse"] == []

"""测试：脚本编码/行尾与可执行位约定 — `scripts/*.ps1` 与 `scripts/*.sh`

覆盖：
  - 回归场景：Windows PowerShell 脚本必须 **UTF-8 with BOM + CRLF**——无 BOM 时
    Windows PowerShell 5.1 按 ANSI/GBK 误读 UTF-8 中文注释，报「字符串缺少
    终止符」解析崩溃；`.editorconfig` 的 `[*.ps1]` 段声明同一约定。曾出现
    `cli.ps1` / `launch.ps1` 有 BOM 但通体 LF 的偏离。
  - 回归场景：shell 包装脚本的可执行位必须**记入 git 索引**——仓库
    `core.fileMode=false` 时工作区权限不被跟踪，新克隆的仓库里
    `./scripts/llm.sh` 会报 permission denied，而文档示例正按可执行方式调用。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_BOM = b"\xef\xbb\xbf"


@pytest.mark.unit
@pytest.mark.unit_scripts
class TestWindowsScriptEncoding:
    """`scripts/*.ps1` 的编码与行尾约定（BOM + CRLF）。"""

    def test_ps1_all_have_utf8_bom(self):
        files = sorted(_SCRIPTS_DIR.glob("*.ps1"))
        assert files, "scripts/ 下应有 PowerShell 脚本"
        missing = [p.name for p in files if not p.read_bytes().startswith(_BOM)]
        assert missing == [], f"以下 .ps1 缺 UTF-8 BOM：{missing}"

    def test_ps1_all_use_crlf(self):
        offenders = {}
        for path in sorted(_SCRIPTS_DIR.glob("*.ps1")):
            data = path.read_bytes()
            bare_lf = data.count(b"\n") - data.count(b"\r\n")
            if bare_lf:
                offenders[path.name] = bare_lf
        assert offenders == {}, f"以下 .ps1 含裸 LF（应统一 CRLF）：{offenders}"


@pytest.mark.unit
@pytest.mark.unit_scripts
class TestShellScriptExecutableBit:
    """`scripts/*.sh` 的可执行位（git 索引 + 工作区）。"""

    def test_executable_bit_tracked_in_git_index(self):
        sh_files = sorted(p.name for p in _SCRIPTS_DIR.glob("*.sh"))
        assert sh_files, "scripts/ 下应有 shell 包装脚本"
        if shutil.which("git") is None or not (_REPO_ROOT / ".git").exists():
            pytest.skip("非 git 工作区，跳过索引可执行位校验")
        out = subprocess.run(
            ["git", "ls-files", "-s", "scripts"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        modes = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[3].endswith(".sh"):
                modes[Path(parts[3]).name] = parts[0]
        missing = [name for name in sh_files if modes.get(name) != "100755"]
        assert missing == [], f"以下 .sh 的可执行位未记入 git 索引（应为 100755）：{missing}"

    @pytest.mark.skipif(os.name == "nt", reason="Windows 无 POSIX 可执行位语义")
    def test_executable_in_worktree(self):
        not_exec = [p.name for p in sorted(_SCRIPTS_DIR.glob("*.sh")) if not os.access(p, os.X_OK)]
        assert not_exec == [], f"以下 .sh 在工作区不可执行：{not_exec}"

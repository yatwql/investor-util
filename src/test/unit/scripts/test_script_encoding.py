"""测试：脚本编码/行尾与可执行位约定 — `scripts/*.ps1`、`scripts/*.sh` 与 `requirements.txt`

覆盖：
  - 回归场景：Windows PowerShell 脚本必须 **UTF-8 with BOM + CRLF**——无 BOM 时
    Windows PowerShell 5.1 按 ANSI/GBK 误读 UTF-8 中文注释，报「字符串缺少
    终止符」解析崩溃；`.editorconfig` 的 `[*.ps1]` 段声明同一约定。曾出现
    `cli.ps1` / `launch.ps1` 有 BOM 但通体 LF 的偏离。
  - 回归场景：`requirements.txt` 必须 **UTF-8 with BOM**（或退化为纯 ASCII）——
    它含中文注释但无 BOM 时，中文 Windows（cp936 locale）上 pip ≤24.x 的
    `auto_decode` 按「BOM → PEP263 cookie → locale 编码」次序解码，最后一档
    回退 cp936 并报 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xac`，
    `launch.ps1` / `launch.sh` 装依赖阶段中断（pip ≥25 起默认 UTF-8，故该缺陷
    只在旧 pip + 非 UTF-8 locale 上暴露，本机 UTF-8 locale 与 CI 均不报）。
  - 回归场景：shell 包装脚本的可执行位必须**记入 git 索引**——仓库
    `core.fileMode=false` 时工作区权限不被跟踪，新克隆的仓库里
    `./scripts/llm.sh` 会报 permission denied，而文档示例正按可执行方式调用。
"""

from __future__ import annotations

import codecs
import locale
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_REQ_FILE = _REPO_ROOT / "requirements.txt"
_BOM = b"\xef\xbb\xbf"

# pip <= 24.x 的 `_internal/utils/encoding.py::auto_decode` 解码次序（BOM 表顺序
# 影响判定：窄位宽的 UTF BOM 是宽位宽 UTF BOM 的前缀，故宽编码须排在前面）。
_LEGACY_PIP_BOMS = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF32, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF16, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
)
_LEGACY_PIP_CODING_RE = re.compile(rb"coding[:=]\s*([-\w.]+)")


def _legacy_pip_auto_decode(data: bytes) -> str:
    """复刻 pip <= 24.x 的需求文件解码次序（BOM → PEP263 cookie → locale）。

    用于在测试内以受控 locale 重现真实读取方行为：无 BOM 且无 coding cookie
    时最后一档会回退 `locale.getpreferredencoding()`，即中文 Windows 上的崩溃点。
    """
    for bom, encoding in _LEGACY_PIP_BOMS:
        if data.startswith(bom):
            return data[len(bom) :].decode(encoding)
    for line in data.split(b"\n")[:2]:
        if line[0:1] == b"#":
            match = _LEGACY_PIP_CODING_RE.search(line)
            if match:
                return data.decode(match.group(1).decode("ascii"))
    return data.decode(locale.getpreferredencoding(False) or sys.getdefaultencoding())


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
class TestRequirementsFileEncoding:
    """`requirements.txt` 的编码必须与运行环境的 locale 无关。"""

    def test_non_ascii_content_requires_utf8_bom(self):
        """含非 ASCII 字节的文件必须带 BOM，否则旧 pip 会回退 locale 解码。"""
        data = _REQ_FILE.read_bytes()
        assert data.startswith(_BOM) or data.isascii(), (
            "requirements.txt 含非 ASCII 字符却无 UTF-8 BOM：中文 Windows（cp936）上 "
            "pip <= 24.x 会回退 locale 解码并抛 UnicodeDecodeError，装依赖中断"
        )

    def test_legacy_pip_autodecode_survives_gbk_locale(self, monkeypatch):
        """在强制 cp936 locale 下按旧 pip 次序解码，内容与 UTF-8 直读一致。"""
        monkeypatch.setattr(locale, "getpreferredencoding", lambda *args, **kwargs: "cp936")
        data = _REQ_FILE.read_bytes()
        decoded = _legacy_pip_auto_decode(data)
        expected = data[len(_BOM) :].decode("utf-8") if data.startswith(_BOM) else data.decode("utf-8")
        assert decoded == expected

    def test_bom_appears_only_as_file_prefix(self):
        """BOM 只允许出现在文件头（防编辑器重复写入导致首个依赖行被污染）。"""
        data = _REQ_FILE.read_bytes()
        if not data.startswith(_BOM):
            pytest.skip("requirements.txt 为纯 ASCII 无 BOM，无需校验 BOM 位置")
        assert _BOM not in data[len(_BOM) :]


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
            encoding="utf-8",
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

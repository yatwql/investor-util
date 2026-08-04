"""测试：版本号一致性检查脚本 — check-version-consistency.py

覆盖：
  - 回归场景：对「文档版本：」头部版本行做精确匹配，正文偶然出现目标版本号
    不得误判通过（rf-204 修复——全文 contains 方案会漏检，头部锚定方案修正）
  - 头部版本行正确时通过、错误版本/缺失头部时判定不一致
  - --fix 自动修正头部版本行
  - 管理文档 CHECKS 注册为 header 校验，防止退回 contains

测试通过脚本 import 方式直接复用 _check_header / _check_contains / _auto_fix_header，
不运行真实 CLI。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_script(name: str):
    """按文件名加载 scripts/ 下的检查脚本（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def version_script():
    return _load_script("check-version-consistency.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


class TestHeaderCheck:
    """「文档版本：」头部版本行精确校验（rf-204 回归场景）。"""

    def test_matching_header_passes(self, version_script):
        text = "> 文档版本：0.10.0\n\n正文……\n"
        assert version_script._check_header(text, "0.10.0") is True

    def test_old_header_rejected_even_if_body_mentions_target(self, version_script):
        """回归断言：头部为旧版本号、正文出现目标版本号时，header 校验必须判定不一致。"""
        text = (
            "> 文档版本：0.9.13-dev\n\n"
            "| rf-114 | 待 v0.10.0 稳定 2 个版本后删除旧渲染器 |\n"
        )
        # 全文 contains 方案：因正文出现目标版本号而误判通过。
        assert version_script._check_contains(text, ("{v}",), "0.10.0") is True
        # 新方案按头部行精确匹配：头部未同步则判定不一致。
        assert version_script._check_header(text, "0.10.0") is False

    def test_wrong_version_header_rejected(self, version_script):
        text = "> 文档版本：0.9.13-dev\n"
        assert version_script._check_header(text, "0.10.0") is False

    def test_no_header_rejected(self, version_script):
        text = "无版本头\n目标版本 0.10.0 出现在正文\n"
        assert version_script._check_header(text, "0.10.0") is False

    def test_header_with_leading_whitespace_passes(self, version_script):
        text = "  > 文档版本：0.10.0\n"
        assert version_script._check_header(text, "0.10.0") is True


class TestAutoFixHeader:
    """--fix 自动修正头部版本行。"""

    def test_fixes_old_header(self, version_script, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("> 文档版本：0.9.13-dev\n\n正文 v0.10.0\n", encoding="utf-8")
        assert version_script._auto_fix_header(p, "0.10.0") is True
        assert p.read_text(encoding="utf-8").startswith("> 文档版本：0.10.0\n")

    def test_no_change_when_already_matching(self, version_script, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("> 文档版本：0.10.0\n", encoding="utf-8")
        assert version_script._auto_fix_header(p, "0.10.0") is False
        assert p.read_text(encoding="utf-8") == "> 文档版本：0.10.0\n"

    def test_fixes_wrong_version_header(self, version_script, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("> 文档版本：0.9.13-dev\n", encoding="utf-8")
        assert version_script._auto_fix_header(p, "0.10.1-dev") is True
        assert p.read_text(encoding="utf-8") == "> 文档版本：0.10.1-dev\n"


class TestDocHeaderRegistration:
    """管理文档 CHECKS 注册为 header 校验，防止退回全文 contains（rf-204 回归场景）。"""

    HEADER_DOCS = [
        "docs-stm/managements/plan.md",
        "docs-stm/managements/technical.md",
        "docs-stm/managements/requirements.md",
        "docs-stm/managements/testplan.md",
        "docs-stm/managements/review-findings.md",
        "docs-stm/managements/llm-technical.md",
        "docs-stm/managements/folders.md",
        "docs-stm/managements/test-coverage.md",
        "docs-stm/manuals/how-to-test-my-code.md",
    ]

    def test_doc_header_docs_registered_as_header(self, version_script):
        # relative_to 在 Windows 返回反斜杠分隔，规范化 / 与 HEADER_DOCS 对齐
        # （Linux/macOS 无副作用）。
        types = {
            str(path.relative_to(version_script.REPO_ROOT)).replace("\\", "/"): assert_type
            for path, assert_type, _args in version_script.CHECKS
        }
        for rel in self.HEADER_DOCS:
            assert types.get(rel) == "header", f"{rel} 应注册为 header 校验而非 contains"

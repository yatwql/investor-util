"""测试：check-doc-links.py — 文档链接与结构一致性机检

覆盖：
  - 死文件链接 / 文内死锚点 / 跨文件死锚点（GitHub slug 规则与 `<a id>` 显式锚点）
  - 重复标题（锚点歧义）；代码围栏内的标题与链接不参与检查
  - 标题层级跳变
  - 数字与中文数字编号序列连续性（连续放行 / 跳变检出）
  - `xxx.md §N` 跨文档章节引用：归属、失配检出、非编号文档不自归属
  - 真实仓库冒烟：当前文档集零 finding（run_checks() 为空）
  - 扫描范围：归档（docs/archive）豁免、README/CLAUDE.md 在列

测试通过脚本 import 方式直接复用检查函数，不运行真实 CLI。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # 仓库根目录（src/test/unit/scripts 向上 4 级）
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
def links():
    return _load_script("check-doc-links.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
    pytest.mark.usefixtures("offline_external_sources"),
]


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestLinksAndAnchors:
    """死文件链接与死锚点的检出 / 放行。"""

    def test_dead_file_link_reported(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 甲\n\n见 [缺失](nowhere.md)。\n")
        findings = links.run_checks([doc])
        assert any("死文件链接" in f and "nowhere.md" in f for f in findings)

    def test_dead_anchor_reported(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 甲\n\n跳到 [无此锚点](#不存在)。\n")
        findings = links.run_checks([doc])
        assert any("文内死锚点" in f for f in findings)

    def test_valid_links_and_anchor_pass(self, links, tmp_path):
        _write(tmp_path, "other.md", "# 另一份\n")
        doc = _write(tmp_path, "a.md", "# 甲\n\n见 [乙章](#乙章) 与 [另一份](other.md#另一份)。\n\n## 乙章\n")
        assert links.run_checks([doc]) == []

    def test_html_anchor_cross_file_pass(self, links, tmp_path):
        target = _write(tmp_path, "b.md", "**Q: 问答体无标题**\n\n<a id='问答锚点'></a>\n")
        doc = _write(tmp_path, "a.md", "# 甲\n\n[问答](b.md#问答锚点)\n")
        assert links.run_checks([doc, target]) == []

    def test_external_links_skipped(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 甲\n\n[站](https://example.com/x) [邮](mailto:a@b.c)\n")
        assert links.run_checks([doc]) == []

    def test_fence_content_ignored(self, links, tmp_path):
        doc = _write(
            tmp_path,
            "a.md",
            "# 甲\n\n```bash\n# 围栏注释标题\n[围栏链接](nowhere.md)\n# 围栏注释标题\n```\n",
        )
        assert links.run_checks([doc]) == []


class TestStructure:
    """重复标题 / 层级跳变 / 编号序列。"""

    def test_duplicate_heading_reported(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 甲\n\n## 同名\n\n正文\n\n## 同名\n")
        findings = links.run_checks([doc])
        assert any("重复标题" in f for f in findings)

    def test_level_skip_reported(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 甲\n\n### 跳级\n")
        findings = links.run_checks([doc])
        assert any("层级跳变" in f for f in findings)

    def test_numeric_sequence_continuous_passes(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 头\n\n## 1. 甲\n\n## 2. 乙\n\n### 2.1 子\n\n### 2.2 子\n")
        assert links.run_checks([doc]) == []

    def test_numeric_sequence_jump_reported(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 头\n\n## 1. 甲\n\n## 3. 乙\n")
        findings = links.run_checks([doc])
        assert any("序号跳变" in f for f in findings)

    def test_chinese_sequence_jump_reported(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 头\n\n## 一、甲\n\n## 三、乙\n")
        findings = links.run_checks([doc])
        assert any("中文序号跳变" in f for f in findings)

    def test_chinese_sequence_continuous_passes(self, links, tmp_path):
        doc = _write(tmp_path, "a.md", "# 头\n\n## 一、甲\n\n## 二、乙\n\n## 三、丙\n")
        assert links.run_checks([doc]) == []


class TestSectionRefs:
    """`xxx.md §N` 跨文档章节引用的归属与失配。"""

    def test_section_ref_resolved_passes(self, links, tmp_path):
        target = _write(tmp_path, "b.md", "# 乙\n\n## 2.1 映射表\n")
        doc = _write(tmp_path, "a.md", "# 甲\n\n详见 `b.md` §2.1 的说明。\n")
        assert links.run_checks([doc, target]) == []

    def test_section_ref_missing_reported(self, links, tmp_path):
        target = _write(tmp_path, "b.md", "# 乙\n\n## 9.9 别的章节\n")
        doc = _write(tmp_path, "a.md", "# 甲\n\n详见 `b.md` §2.1 的说明。\n")
        findings = links.run_checks([doc, target])
        assert any("§ 引用无对应章节" in f and "§2.1" in f for f in findings)

    def test_unnumbered_doc_self_ref_skipped(self, links, tmp_path):
        # 非编号章节文档（如 FAQ 形态）里的 §13 多指报告章而非本文档章——不自归属、不误报
        doc = _write(tmp_path, "faq.md", "# 问答复\n\n## 启动与安装\n\n会。§13 某报告章含该段落。\n")
        assert links.run_checks([doc]) == []

    def test_self_ref_on_numbered_doc_checked(self, links, tmp_path):
        doc = _write(tmp_path, "c.md", "# 丙\n\n## 1. 概述\n\n见 §3 的后续章节。\n")
        findings = links.run_checks([doc])
        assert any("§ 引用无对应章节" in f and "§3" in f for f in findings)


class TestRealRepo:
    """真实仓库冒烟与扫描范围。"""

    def test_real_repo_clean(self, links):
        assert links.run_checks() == []

    def test_scope_excludes_archive_and_covers_entry_docs(self, links):
        targets = [p.as_posix() for p in links.default_targets()]
        assert all("docs/archive" not in t for t in targets)
        names = {Path(t).name for t in targets}
        assert {"README.md", "CLAUDE.md"} <= names

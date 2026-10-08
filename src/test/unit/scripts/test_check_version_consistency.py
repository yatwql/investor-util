"""测试：版本号一致性检查脚本 — check-version-consistency.py

覆盖：
  - 回归场景：对「文档版本：」头部版本行做精确匹配，正文偶然出现目标版本号
    不得误判通过（回归修复——全文 contains 方案会漏检，头部锚定方案修正）
  - 头部版本行正确时通过、错误版本/缺失头部时判定不一致
  - --fix 自动修正头部版本行
  - 管理文档 CHECKS 注册为 header 校验，防止退回 contains
  - folders.md 版本演进对照「当前开发版」列头版本号 evolution_head 锚定校验
    （匹配/旧号/无列头拒绝 + --fix 自动同步 + 与 header 并存注册）
  - 回归场景：--fix 头部改写保留版本头前空行（行首空白类只吃同行字符，
    不得跨行吞换行）；头部校验不跨行误判（`>\n文档版本：…` 不算合法头）

测试通过脚本 import 方式直接复用 _check_header / _check_contains /
_auto_fix_header / _check_evolution_head / _auto_fix_evolution_head，
不运行真实 CLI。
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from src.test._script_loader import load_script

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def version_script():
    return load_script("check-version-consistency.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


class TestHeaderCheck:
    """「文档版本：」头部版本行精确校验（回归场景）。"""

    def test_matching_header_passes(self, version_script):
        text = "> 文档版本：0.10.0\n\n正文……\n"
        assert version_script._check_header(text, "0.10.0") is True

    def test_old_header_rejected_even_if_body_mentions_target(self, version_script):
        """回归断言：头部为旧版本号、正文出现目标版本号时，header 校验必须判定不一致。"""
        text = "> 文档版本：0.9.13-dev\n\n| rf-114 | 待 v0.10.0 稳定 2 个版本后删除旧渲染器 |\n"
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

    def test_check_header_not_crossing_newline(self, version_script):
        # 行首空白类不得跨行：`>` 独占一行 + 下一行裸文本不构成版本头
        text = "# 标题\n>\n文档版本：0.10.0\n"
        assert version_script._check_header(text, "0.10.0") is False


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

    def test_fix_preserves_blank_line_before_header(self, version_script, tmp_path):
        # 行首空白类不得吞换行：H1 与版本头之间的空行改写后必须保留
        p = tmp_path / "doc.md"
        p.write_text("# 标题\n\n> 文档版本：0.9.13-dev\n\n## 章节\n", encoding="utf-8")
        assert version_script._auto_fix_header(p, "0.10.0") is True
        assert p.read_text(encoding="utf-8") == "# 标题\n\n> 文档版本：0.10.0\n\n## 章节\n"


class TestScriptSyntaxWarnings:
    r"""脚本源码无警告编译（回归：docstring 裸 `\s` 转义触发 SyntaxWarning）。"""

    def test_compiles_without_syntaxwarning(self):
        path = _SCRIPTS_DIR / "check-version-consistency.py"
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
        assert code is not None


class TestDocHeaderRegistration:
    """管理文档 CHECKS 注册为 header 校验，防止退回全文 contains（回归场景）。"""

    HEADER_DOCS = [
        "docs/managements/plan.md",
        "docs/managements/technical.md",
        "docs/managements/requirements.md",
        "docs/managements/testplan.md",
        "docs/managements/review-findings.md",
        "docs/managements/llm-technical.md",
        "docs/managements/folders.md",
        "docs/managements/test-coverage.md",
        "docs/managements/developer-guide.md",
    ]

    def test_doc_header_docs_registered_as_header(self, version_script):
        # relative_to 在 Windows 返回反斜杠分隔，规范化 / 与 HEADER_DOCS 对齐
        # （Linux/macOS 无副作用）。同文件可并存多条断言（如 folders.md 的
        # header + evolution_head），按集合断言主校验 header 在列。
        types: dict[str, set[str]] = {}
        for path, assert_type, _args in version_script.CHECKS:
            rel = str(path.relative_to(version_script.REPO_ROOT)).replace("\\", "/")
            types.setdefault(rel, set()).add(assert_type)
        for rel in self.HEADER_DOCS:
            assert "header" in types.get(rel, set()), f"{rel} 应注册为 header 校验而非 contains"

    def test_folders_evolution_head_registered(self, version_script):
        """folders.md 须另注册 evolution_head 断言（版本演进表头列版本号同步）。"""
        types: dict[str, set[str]] = {}
        for path, assert_type, _args in version_script.CHECKS:
            rel = str(path.relative_to(version_script.REPO_ROOT)).replace("\\", "/")
            types.setdefault(rel, set()).add(assert_type)
        assert "evolution_head" in types.get("docs/managements/folders.md", set())

    def test_folders_release_tag_registered(self, version_script):
        """folders.md 须注册 release_tag 断言（发布列 == changelog 发布指针）。"""
        types: dict[str, set[str]] = {}
        for path, assert_type, _args in version_script.CHECKS:
            rel = str(path.relative_to(version_script.REPO_ROOT)).replace("\\", "/")
            types.setdefault(rel, set()).add(assert_type)
        assert "release_tag" in types.get("docs/managements/folders.md", set())


# ── release_tag：版本演进「最近发布」列 ↔ changelog 发布指针单源 ─────────

_CHANGELOG_PTR = (
    "> **最近发布 [0.12.0]**（2026-10-03）——已发布版本段随发布移入归档；"
    "本文件只保留当前开发版本段与归档索引。\n## [0.12.1-dev] - 开发中（未发布）"
)


def _folders_release_text(ver: str = "0.12.0", date: str = "2026-10-03") -> str:
    """构造 folders 版本演进发布列两处出现（说明行 + 表头）。"""
    return (
        f"> **三个读数**：最初版本 = 仓库首个提交（`项目初始基线`，2026-06-27）；"
        f"最新发布 = 最近一次发布 tag（v{ver} · {date}）；**当前开发版 = 本次重跑时的 HEAD**。\n"
        f"| 指标 | 最初版本 | 最新发布（最近发布 tag v{ver} · {date}） | 当前开发版（0.12.1-dev） |"
    )


class TestReleaseTagCheck:
    """发布列（表头 + 说明行）== changelog 发布指针；任一处过期或指针缺失即拒绝。"""

    def test_both_columns_match_changelog_pointer(self, version_script):
        assert version_script._check_release_tag(_folders_release_text(), _CHANGELOG_PTR) is True

    def test_stale_version_rejected(self, version_script):
        text = _folders_release_text(ver="0.11.12", date="2026-10-01")
        assert version_script._check_release_tag(text, _CHANGELOG_PTR) is False

    def test_stale_date_rejected(self, version_script):
        assert version_script._check_release_tag(_folders_release_text(date="2026-10-02"), _CHANGELOG_PTR) is False

    def test_single_stale_occurrence_rejected(self, version_script):
        """两处出现处之一过期即判未同步（表头与说明行都需刷）。"""
        text = _folders_release_text().replace(
            "最近一次发布 tag（v0.12.0 · 2026-10-03）",
            "最近一次发布 tag（v0.11.12 · 2026-10-01）",
        )
        assert version_script._check_release_tag(text, _CHANGELOG_PTR) is False

    def test_changelog_without_pointer_rejected(self, version_script):
        assert version_script._check_release_tag(_folders_release_text(), "## [0.12.0] - 2026-10-03") is False

    def test_missing_column_rejected(self, version_script):
        assert version_script._check_release_tag("纯文本无发布列", _CHANGELOG_PTR) is False


class TestAutoFixReleaseTag:
    """--fix：两处出现处同步为 changelog 指针；已一致不动。"""

    def test_syncs_both_occurrences(self, version_script, tmp_path):
        p = tmp_path / "folders.md"
        p.write_text(_folders_release_text(ver="0.11.12", date="2026-10-01"), encoding="utf-8")
        c = tmp_path / "changelog.md"
        c.write_text(_CHANGELOG_PTR, encoding="utf-8")
        assert version_script._auto_fix_release_tag(p, c) is True
        out = p.read_text(encoding="utf-8")
        assert "v0.12.0 · 2026-10-03" in out, "说明行应同步为发布指针"
        assert "最近发布 tag v0.12.0 · 2026-10-03" in out, "表头应同步为发布指针"
        assert "0.11.12" not in out, "旧版本号不应残留"

    def test_no_change_when_already_matching(self, version_script, tmp_path):
        p = tmp_path / "folders.md"
        p.write_text(_folders_release_text(), encoding="utf-8")
        c = tmp_path / "changelog.md"
        c.write_text(_CHANGELOG_PTR, encoding="utf-8")
        assert version_script._auto_fix_release_tag(p, c) is False


# ── evolution_head：版本演进对照「当前开发版」列头版本号 ───────────


class TestEvolutionHeadCheck:
    """「当前开发版（」列头版本号锚定校验：匹配/旧号/无列头拒绝/单点定位。"""

    def test_matching_version_passes(self, version_script):
        text = "| 当前开发版（0.11.12-dev · 本次重跑时的 HEAD · 2026-10-02） | 增长 |"
        assert version_script._check_evolution_head(text, "0.11.12-dev") is True

    def test_stale_version_rejected(self, version_script):
        text = "| 当前开发版（0.11.11-dev · 本次重跑时的 HEAD · 2026-10-02） |"
        assert version_script._check_evolution_head(text, "0.11.12-dev") is False

    def test_missing_column_version_rejected(self, version_script):
        text = "| 当前开发版（本次重跑时的 HEAD · 2026-10-03） |"
        assert version_script._check_evolution_head(text, "0.11.12-dev") is False

    def test_release_tag_column_not_mistaken_for_dev_column(self, version_script):
        """「最近发布 tag」列的版本号不得被误当作「当前开发版」列头（单点锚定）。"""
        text = "| 最新发布（最近发布 tag v0.11.10 · 2026-10-01） | 当前开发版（0.11.12-dev · HEAD） |"
        assert version_script._check_evolution_head(text, "0.11.12-dev") is True


class TestAutoFixEvolutionHead:
    """--fix：列头旧号替换、无号插入、已一致不动。"""

    def test_replaces_stale_version(self, version_script, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("| 当前开发版（0.11.11-dev · HEAD · 2026-10-02） |", encoding="utf-8")
        assert version_script._auto_fix_evolution_head(p, "0.11.12-dev") is True
        assert "0.11.12-dev" in p.read_text(encoding="utf-8")

    def test_inserts_when_missing(self, version_script, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("| 当前开发版（本次重跑时的 HEAD · 2026-10-03） |", encoding="utf-8")
        assert version_script._auto_fix_evolution_head(p, "0.11.12-dev") is True
        assert "0.11.12-dev · 本次重跑" in p.read_text(encoding="utf-8")

    def test_no_change_when_already_matching(self, version_script, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("| 当前开发版（0.11.12-dev · HEAD） |", encoding="utf-8")
        assert version_script._auto_fix_evolution_head(p, "0.11.12-dev") is False

"""测试：任务编号一致性检查脚本 — check-task-numbering.py

覆盖：
  - 编号源标记（plan-next / rf-next）与历史归档最大编号的一致性校验
  - 标记缺失 → 报错
  - 标记不晚于已用最大（编号冲突）→ 报错
  - 跨全部归档文件取全局最大编号（不只看当前文档）
  - 双编号序列（plan / rf）独立校验

测试通过脚本 import 方式直接复用 _read_next_marker / _max_number_in /
check_kind 函数，不运行真实 CLI。临时文件用 monkeypatch 指向 tmp_path，
避免依赖真实仓库的归档内容。
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
def numbering():
    return _load_script("check-task-numbering.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


# ── _read_next_marker ───────────────────────────────────────────


def test_read_next_marker_hit(numbering, tmp_path: Path):
    """标记行命中：解析出 next 数值。"""
    doc = tmp_path / "review-findings.md"
    doc.write_text("> 文档版本：0.9.13-dev\n> **编号源**：`rf-next = 174`（说明）\n", encoding="utf-8")
    assert numbering._read_next_marker(doc, "rf-next") == 174


def test_read_next_marker_missing(numbering, tmp_path: Path):
    """标记缺失：返回 None。"""
    doc = tmp_path / "plan.md"
    doc.write_text("> 文档版本：0.9.13-dev\n", encoding="utf-8")
    assert numbering._read_next_marker(doc, "plan-next") is None


def test_read_next_marker_other_prefix_ignored(numbering, tmp_path: Path):
    """其他前缀的标记不影响本前缀解析。"""
    doc = tmp_path / "review-findings.md"
    doc.write_text("> **编号源**：`plan-next = 15`（其他）\n`rf-next = 174`\n", encoding="utf-8")
    assert numbering._read_next_marker(doc, "rf-next") == 174


# ── _max_number_in ──────────────────────────────────────────────


def test_max_number_in_across_files(numbering, tmp_path: Path):
    """跨多个文件取全局最大编号。"""
    f1 = tmp_path / "a.md"
    f2 = tmp_path / "b.md"
    f1.write_text("rf-10 rf-173 正文引用 rf-5\n", encoding="utf-8")
    f2.write_text("rf-42\n", encoding="utf-8")
    assert numbering._max_number_in([f1, f2], r"rf-\d+") == 173


def test_max_number_in_no_match(numbering, tmp_path: Path):
    """无任何匹配编号：返回 None。"""
    f = tmp_path / "a.md"
    f.write_text("无编号\n", encoding="utf-8")
    assert numbering._max_number_in([f], r"rf-\d+") is None


# ── check_kind ──────────────────────────────────────────────────


def test_check_kind_ok(numbering, tmp_path: Path, monkeypatch):
    """next > 已用最大：通过，无违规。"""
    doc = tmp_path / "review-findings.md"
    doc.write_text("> **编号源**：`rf-next = 174`\n", encoding="utf-8")
    archived = tmp_path / "archived.md"
    archived.write_text("rf-173\n", encoding="utf-8")

    monkeypatch.setattr(numbering, "MANAGEMENTS_DIR", tmp_path)
    monkeypatch.setattr(numbering, "_all_numbering_files", lambda: [archived])

    assert numbering.check_kind("rf", ci_mode=True) == []


def test_check_kind_marker_missing(numbering, tmp_path: Path, monkeypatch):
    """标记缺失：报错。"""
    doc = tmp_path / "plan.md"
    doc.write_text("> 文档版本：0.9.13-dev\n", encoding="utf-8")

    monkeypatch.setattr(numbering, "MANAGEMENTS_DIR", tmp_path)
    monkeypatch.setattr(numbering, "_all_numbering_files", lambda: [])

    violations = numbering.check_kind("plan", ci_mode=True)
    assert len(violations) == 1
    assert "缺少编号源标记" in violations[0]
    assert "plan-next" in violations[0]


def test_check_kind_conflict(numbering, tmp_path: Path, monkeypatch):
    """next 不晚于已用最大（编号冲突）：报错并提示修正值。"""
    doc = tmp_path / "review-findings.md"
    doc.write_text("> **编号源**：`rf-next = 160`\n", encoding="utf-8")
    archived = tmp_path / "archived.md"
    archived.write_text("rf-173\n", encoding="utf-8")

    monkeypatch.setattr(numbering, "MANAGEMENTS_DIR", tmp_path)
    monkeypatch.setattr(numbering, "_all_numbering_files", lambda: [archived])

    violations = numbering.check_kind("rf", ci_mode=True)
    assert len(violations) == 1
    assert "rf-next = 160" in violations[0]
    assert "rf-173" in violations[0]
    assert "rf-174" in violations[0]  # 提示修正为已用最大 + 1


def test_check_kind_no_numbers_at_all(numbering, tmp_path: Path, monkeypatch):
    """文档中从未出现任何编号：无法校验，报错提示。"""
    doc = tmp_path / "plan.md"
    doc.write_text("> **编号源**：`plan-next = 15`\n", encoding="utf-8")

    monkeypatch.setattr(numbering, "MANAGEMENTS_DIR", tmp_path)
    monkeypatch.setattr(numbering, "_all_numbering_files", lambda: [])

    violations = numbering.check_kind("plan", ci_mode=True)
    assert len(violations) == 1
    assert "未发现任何 plan" in violations[0]


def test_check_kind_plan_and_rf_independent(numbering, tmp_path: Path, monkeypatch):
    """plan / rf 两条序列独立校验，互不影响。"""
    rf_doc = tmp_path / "review-findings.md"
    rf_doc.write_text("> **编号源**：`rf-next = 174`\n", encoding="utf-8")
    plan_doc = tmp_path / "plan.md"
    plan_doc.write_text("> **编号源**：`plan-next = 15`\n", encoding="utf-8")

    archived = tmp_path / "archived.md"
    archived.write_text("rf-173 plan-14\n", encoding="utf-8")

    monkeypatch.setattr(numbering, "MANAGEMENTS_DIR", tmp_path)
    monkeypatch.setattr(numbering, "_all_numbering_files", lambda: [archived])

    assert numbering.check_kind("rf", ci_mode=True) == []
    assert numbering.check_kind("plan", ci_mode=True) == []

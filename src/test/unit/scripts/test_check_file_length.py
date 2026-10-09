"""测试：单文件行数红线守护脚本 — check-file-length.py

覆盖：
  - 阈值边界：主程序/脚本恰上限行数通过 / 超 1 行违规；测试恰 1200 行通过 / 1201 行违规
  - 三域记录收集：主程序/脚本/测试三类均入记录（scripts/ 纳入红线，防脚本破线漏检）
  - 豁免登记：豁免路径超限不判 finding（挂账），非豁免路径超限判 finding
  - 豁免文件回落阈值内 → 标记「可移除豁免」，不判 finding
  - `--ci` 退出码契约：通过 0 / 发现 finding 2（统一检查脚本契约）
  - 豁免登记完整性：登记路径必须存在且落在检查域内（防过期/错路径）
  - `-v` 清单派生：主程序 >500 / 脚本 >400 / 测试 >800 的可选优化区间输出与降序排序
    （review-findings「文件过长」登记表的派生源）

测试通过脚本 import 方式直接复用 collect_line_counts / split_findings /
over_limit_inventory / main，不运行真实 CLI 进程。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from src.test._script_loader import load_script

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
    pytest.mark.usefixtures("offline_external_sources"),
]


@pytest.fixture(scope="module")
def length_script():
    return load_script("check-file-length.py")


def _make_file(root: Path, rel_path: str, lines: int) -> Path:
    """构造恰好 `lines` 行的 py 文件。"""
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(["x"] * lines) + "\n", encoding="utf-8")
    return path


class TestThresholdBoundary:
    """阈值边界：恰好等于上限不算违规，超出一行即违规。"""

    def test_main_source_at_limit_passes(self, length_script, tmp_path):
        _make_file(tmp_path, "src/python/ok_main.py", length_script.MAIN_SOURCE_LIMIT)
        records = length_script.collect_line_counts(tmp_path)
        violations, _, _ = length_script.split_findings(records, exemptions={})
        assert violations == []

    def test_main_source_one_over_limit_flagged(self, length_script, tmp_path):
        _make_file(tmp_path, "src/python/too_big.py", length_script.MAIN_SOURCE_LIMIT + 1)
        records = length_script.collect_line_counts(tmp_path)
        violations, _, _ = length_script.split_findings(records, exemptions={})
        assert len(violations) == 1
        assert "too_big.py" in violations[0]
        assert str(length_script.MAIN_SOURCE_LIMIT) in violations[0]

    def test_scripts_source_at_limit_passes(self, length_script, tmp_path):
        _make_file(tmp_path, "scripts/ok_script.py", length_script.SCRIPTS_SOURCE_LIMIT)
        records = length_script.collect_line_counts(tmp_path)
        violations, _, _ = length_script.split_findings(records, exemptions={})
        assert violations == []

    def test_scripts_source_one_over_limit_flagged(self, length_script, tmp_path):
        _make_file(tmp_path, "scripts/too_big_script.py", length_script.SCRIPTS_SOURCE_LIMIT + 1)
        records = length_script.collect_line_counts(tmp_path)
        violations, _, _ = length_script.split_findings(records, exemptions={})
        assert len(violations) == 1
        assert "too_big_script.py" in violations[0]
        assert "脚本" in violations[0]

    def test_collect_covers_three_domains(self, length_script, tmp_path):
        """三检查域均入记录：scripts/ 必须纳入，否则脚本破线漏检。"""
        _make_file(tmp_path, "src/python/m.py", 5)
        _make_file(tmp_path, "scripts/s.py", 5)
        _make_file(tmp_path, "src/test/t.py", 5)
        kinds = {kind for kind, _path, _lines in length_script.collect_line_counts(tmp_path)}
        assert kinds == {"主程序", "脚本", "测试"}

    def test_test_source_at_limit_passes(self, length_script, tmp_path):
        _make_file(tmp_path, "src/test/test_ok.py", 1200)
        records = length_script.collect_line_counts(tmp_path)
        violations, _, _ = length_script.split_findings(records, exemptions={})
        assert violations == []

    def test_test_source_one_over_limit_flagged(self, length_script, tmp_path):
        _make_file(tmp_path, "src/test/test_too_big.py", length_script.TEST_SOURCE_LIMIT + 1)
        records = length_script.collect_line_counts(tmp_path)
        violations, _, _ = length_script.split_findings(records, exemptions={})
        assert len(violations) == 1
        assert str(length_script.TEST_SOURCE_LIMIT) in violations[0]


class TestExemptionRegistry:
    """豁免登记语义：挂账不判 finding、回落提示移除、登记表本身完整。"""

    def test_exempted_over_limit_not_flagged(self, length_script, tmp_path):
        path = _make_file(tmp_path, "src/python/exempt_main.py", length_script.MAIN_SOURCE_LIMIT + 100)
        records = length_script.collect_line_counts(tmp_path)
        exemptions = {length_script.rel(path): "挂账说明"}
        violations, exempted, removable = length_script.split_findings(records, exemptions)
        assert violations == []
        assert any("exempt_main.py" in line for line in exempted)
        assert removable == []

    def test_non_exempt_over_limit_still_flagged(self, length_script, tmp_path):
        _make_file(tmp_path, "src/python/big_main.py", length_script.MAIN_SOURCE_LIMIT + 50)
        records = length_script.collect_line_counts(tmp_path)
        violations, exempted, _ = length_script.split_findings(records, exemptions={})
        assert len(violations) == 1
        assert exempted == []

    def test_exemption_fallthrough_marked_removable(self, length_script, tmp_path):
        path = _make_file(tmp_path, "src/python/shrunk_main.py", 400)
        records = length_script.collect_line_counts(tmp_path)
        exemptions = {length_script.rel(path): "挂账说明"}
        violations, exempted, removable = length_script.split_findings(records, exemptions)
        assert violations == []
        assert exempted == []
        assert any("shrunk_main.py" in line for line in removable)

    def test_registry_paths_exist_and_in_scope(self, length_script):
        """登记路径必须真实存在且落在检查域内（防过期/错路径豁免）。"""
        scope_prefixes = (
            length_script.MAIN_SOURCE_ROOT + "/",
            length_script.SCRIPTS_SOURCE_ROOT + "/",
            length_script.TEST_SOURCE_ROOT + "/",
        )
        for path in length_script.EXEMPTIONS:
            assert path.startswith(scope_prefixes), f"豁免路径超出检查域: {path}"
            assert (_REPO_ROOT / path).is_file(), f"豁免路径不存在: {path}"

    def test_registry_exemptions_not_stale(self, length_script):
        """登记的豁免当前必须仍超限——回落即为过期豁免，须与 review-findings 挂账同步移除。"""
        records = {path: lines for _kind, path, lines in length_script.collect_line_counts(length_script.REPO_ROOT)}
        for path in length_script.EXEMPTIONS:
            lines = records[path]
            kind = (
                "测试"
                if path.startswith(length_script.TEST_SOURCE_ROOT + "/")
                else "脚本"
                if path.startswith(length_script.SCRIPTS_SOURCE_ROOT + "/")
                else "主程序"
            )
            limit = length_script._LIMIT_BY_KIND[kind]
            assert lines > limit, f"豁免 {path} 已回落至 {limit} 行内（实测 {lines} 行），应移除豁免登记"


class TestCliContract:
    """`--ci` 退出码契约：通过 0 / 发现 finding 2。"""

    def test_clean_tree_exits_zero(self, length_script, tmp_path, monkeypatch, capsys):
        _make_file(tmp_path, "src/python/small.py", 10)
        monkeypatch.setattr(length_script, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["check-file-length.py", "--ci"])
        assert length_script.main() == 0
        assert "[OK]" in capsys.readouterr().out

    def test_violation_exits_two(self, length_script, tmp_path, monkeypatch, capsys):
        _make_file(tmp_path, "src/python/huge.py", length_script.MAIN_SOURCE_LIMIT + 1)
        monkeypatch.setattr(length_script, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["check-file-length.py", "--ci"])
        assert length_script.main() == 2
        assert "huge.py" in capsys.readouterr().out

    def test_exempted_only_tree_exits_zero(self, length_script, tmp_path, monkeypatch, capsys):
        path = _make_file(tmp_path, "src/python/huge.py", length_script.MAIN_SOURCE_LIMIT + 1)
        monkeypatch.setattr(length_script, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(length_script, "EXEMPTIONS", {length_script.rel(path): "挂账说明"})
        monkeypatch.setattr(sys, "argv", ["check-file-length.py", "--ci"])
        assert length_script.main() == 0


class TestVerboseInventory:
    """`-v` 清单：可选优化区间（主程序 >500 / 脚本 >400 / 测试 >800）派生输出。"""

    def test_scripts_source_warn_zone_boundary(self, length_script, tmp_path):
        _make_file(tmp_path, "scripts/at_warn.py", 400)
        _make_file(tmp_path, "scripts/over_warn.py", 401)
        records = length_script.collect_line_counts(tmp_path)
        inventory = length_script.over_limit_inventory(records)
        assert any("over_warn.py" in line for line in inventory)
        assert not any("at_warn.py" in line for line in inventory)

    def test_main_source_warn_zone_boundary(self, length_script, tmp_path):
        _make_file(tmp_path, "src/python/at_warn.py", 500)
        _make_file(tmp_path, "src/python/over_warn.py", 501)
        records = length_script.collect_line_counts(tmp_path)
        inventory = length_script.over_limit_inventory(records)
        assert any("over_warn.py" in line for line in inventory)
        assert not any("at_warn.py" in line for line in inventory)

    def test_test_source_warn_zone_boundary(self, length_script, tmp_path):
        _make_file(tmp_path, "src/test/test_at_warn.py", 800)
        _make_file(tmp_path, "src/test/test_over_warn.py", 801)
        records = length_script.collect_line_counts(tmp_path)
        inventory = length_script.over_limit_inventory(records)
        assert any("test_over_warn.py" in line for line in inventory)
        assert not any("test_at_warn.py" in line for line in inventory)

    def test_inventory_sorted_descending(self, length_script, tmp_path):
        _make_file(tmp_path, "src/python/lower.py", 600)
        _make_file(tmp_path, "src/python/higher.py", 700)
        records = length_script.collect_line_counts(tmp_path)
        inventory = length_script.over_limit_inventory(records)
        assert len(inventory) == 2
        first_num = int(inventory[0].split("]")[1].split("行")[0].strip())
        second_num = int(inventory[1].split("]")[1].split("行")[0].strip())
        assert first_num >= second_num

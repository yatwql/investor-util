"""测试：check-requirement-trace.py — 需求 ID ↔ 验证载体追溯（requirements.md ↔ testplan.md §2.1）

覆盖：
  - 需求 ID 提取（requirements.md 表行）
  - 映射表解析（`<!-- requirement-trace:start/end -->` 标记区间、ID 与载体列）
  - 载体路径提取（`测试文件::用例` 中的 src/test 路径，多路径保序去重）
  - 五项断言：映射表缺失 / ID 不存在于需求侧 / ID 重复登记 / 已补全域漏映射 / 载体文件不存在 / 载体列空
  - 真实仓库冒烟：R-CCH 域 38 条全部映射且载体文件存在

测试通过脚本 import 方式直接复用解析/校验函数，不运行真实 CLI（只读文件）。
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
def trace():
    return _load_script("check-requirement-trace.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]

_REQ = "| R-CCH-01 | 所有外部数据获取结果应缓存到本地磁盘文件 |\n| R-CCH-02 | 缓存文件用 JSON 格式 |\n"
_GOOD_CARRIER = "`src/test/unit/core/test_cache_core.py`"


def _plan(rows: str) -> str:
    return f"## 2. 数据正确性验证\n\n<!-- requirement-trace:start -->\n{rows}<!-- requirement-trace:end -->\n"


class TestParsing:
    def test_extracts_requirement_ids(self, trace):
        ids = trace.requirement_ids(_REQ)
        assert list(ids) == ["R-CCH-01", "R-CCH-02"]

    def test_parses_trace_rows(self, trace):
        rows = trace.trace_rows(_plan(f"| R-CCH-01 | {_GOOD_CARRIER} | 批 1 |\n"))
        assert rows == [("R-CCH-01", _GOOD_CARRIER, 4)]

    def test_missing_marker_yields_no_rows(self, trace):
        assert trace.trace_rows("## 2. 无标记\n") == []

    def test_carrier_paths_deduped_and_ordered(self, trace):
        cell = "`src/test/a.py` + `src/test/b.py::test_x` + `src/test/a.py`"
        assert trace.carrier_paths(cell) == ["src/test/a.py", "src/test/b.py"]


class TestFindings:
    def test_clean_input_passes(self, trace):
        rows = f"| R-CCH-01 | {_GOOD_CARRIER} | 批 1 |\n| R-CCH-02 | {_GOOD_CARRIER} | 批 1 |\n"
        assert trace.check_requirement_trace(_REQ, _plan(rows), covered_domains=("R-CCH",)) == []

    def test_missing_table_reports(self, trace):
        findings = trace.check_requirement_trace(_REQ, "## 无表\n", covered_domains=("R-CCH",))
        assert any("未找到需求追溯映射表" in f for f in findings)

    def test_unknown_requirement_id_reports(self, trace):
        rows = f"| R-CCH-99 | {_GOOD_CARRIER} | 批 1 |\n| R-CCH-01 | {_GOOD_CARRIER} | 批 1 |\n| R-CCH-02 | {_GOOD_CARRIER} | 批 1 |\n"
        findings = trace.check_requirement_trace(_REQ, _plan(rows), covered_domains=("R-CCH",))
        assert any("不存在于 requirements.md" in f for f in findings)

    def test_duplicate_id_reports(self, trace):
        rows = f"| R-CCH-01 | {_GOOD_CARRIER} | 批 1 |\n| R-CCH-01 | {_GOOD_CARRIER} | 批 1 |\n| R-CCH-02 | {_GOOD_CARRIER} | 批 1 |\n"
        findings = trace.check_requirement_trace(_REQ, _plan(rows), covered_domains=("R-CCH",))
        assert any("重复登记" in f for f in findings)

    def test_missing_domain_coverage_reports(self, trace):
        """已补全域漏映射某条需求 → 报 finding（防「补了 N 条漏 1 条」）。"""
        rows = f"| R-CCH-01 | {_GOOD_CARRIER} | 批 1 |\n"
        findings = trace.check_requirement_trace(_REQ, _plan(rows), covered_domains=("R-CCH",))
        assert any("未映射验证载体" in f and "R-CCH-02" in f for f in findings)

    def test_nonexistent_carrier_path_reports(self, trace):
        rows = "| R-CCH-01 | `src/test/unit/core/test_does_not_exist.py` | 批 1 |\n| R-CCH-02 | `src/test/unit/core/test_does_not_exist.py` | 批 1 |\n"
        findings = trace.check_requirement_trace(_REQ, _plan(rows), covered_domains=("R-CCH",))
        assert any("不存在于磁盘" in f for f in findings)

    def test_empty_carrier_reports(self, trace):
        rows = "| R-CCH-01 | | 批 1 |\n| R-CCH-02 | | 批 1 |\n"
        findings = trace.check_requirement_trace(_REQ, _plan(rows), covered_domains=("R-CCH",))
        assert any("验证载体列缺失" in f for f in findings)

    def test_unknown_covered_domain_reports(self, trace):
        """声明补全的域在需求侧不存在 → 报 finding（域名拼写错误守卫）。"""
        rows = f"| R-CCH-01 | {_GOOD_CARRIER} | 批 1 |\n| R-CCH-02 | {_GOOD_CARRIER} | 批 1 |\n"
        findings = trace.check_requirement_trace(_REQ, _plan(rows), covered_domains=("R-NOPE",))
        assert any("无任何 ID" in f for f in findings)

    def test_empty_inputs_are_noop(self, trace):
        assert trace.check_requirement_trace("", "", covered_domains=("R-CCH",)) == []


class TestRealRepo:
    def test_covered_domains_are_known(self, trace):
        """已补全域必须都在 _ALL_DOMAINS 之内（防域前缀写错）。"""
        assert set(trace._COVERED_DOMAINS) <= set(trace._ALL_DOMAINS)

    def test_all_domains_covered(self, trace):
        """六批已完成：已补全域 == 全部域（分批机制已收敛为全量断言）。"""
        assert set(trace._COVERED_DOMAINS) == set(trace._ALL_DOMAINS)

    def test_every_requirement_id_mapped(self, trace):
        """全量对照：requirements.md 的每个 ID 均在映射表内（双向相等）。"""
        req_ids = set(trace.requirement_ids(trace._REQUIREMENTS_MD.read_text(encoding="utf-8")))
        mapped = {row[0] for row in trace.trace_rows(trace._TESTPLAN_MD.read_text(encoding="utf-8"))}
        assert req_ids == mapped
        assert len(req_ids) == 277

    def test_real_repo_passes(self, trace):
        """真实仓库：R-CCH 域 38 条需求全部映射且载体文件存在。"""
        assert trace.check_requirement_trace() == []

    def test_r_cch_mapping_covers_all_ids(self, trace):
        req_ids = [
            r
            for r in trace.requirement_ids(trace._REQUIREMENTS_MD.read_text(encoding="utf-8"))
            if r.startswith("R-CCH-")
        ]
        mapped = {
            row[0]
            for row in trace.trace_rows(trace._TESTPLAN_MD.read_text(encoding="utf-8"))
            if row[0].startswith("R-CCH-")
        }
        assert len(req_ids) == 38
        assert set(req_ids) == mapped

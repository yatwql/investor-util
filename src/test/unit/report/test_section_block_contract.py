"""章节区块契约测试 — SECTION_BLOCK_SPECS 与双端实现提取三向一致。

契约真值：`core/section_block_registry.py`（每章 html/excel 归一化区块名 + 载体）；
提取实现：`report/section_block_extraction.py`（HTML partial 三源规则 / Excel
`write_block_title` 调用点含参数直通包装）。本套锁「实现 ↔ 注册表」半边，
「文档矩阵 ↔ 注册表」半边由 `test_check_doc_drift.py::TestBlockMatrix` 锁定。

运行：
  pytest src/test/unit/report/test_section_block_contract.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.python.core.registry import _REPORT_SECTION_DEFAULT
from src.python.core.section_block_registry import SECTION_BLOCK_SPECS, SectionBlockSpec
from src.python.report.section_block_extraction import (
    extract_excel_block_titles,
    extract_html_block_titles,
    normalize_block_title,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.usefixtures("offline_external_sources")]

_REPO = Path(__file__).resolve().parents[4]
_PARTIAL_DIR = _REPO / "src" / "static" / "tmpl" / "partials"
_MODULE_DIR = _REPO / "src" / "python" / "report"


class TestSectionBlockContract:
    """注册表 ↔ 双端实现的区块级契约。"""

    def test_spec_keys_match_section_registry(self):
        """契约键集与章节注册表双向相等（结构关系断言，不写死条数）。"""
        section_keys = {sec["key"] for sec in _REPORT_SECTION_DEFAULT}
        assert set(SECTION_BLOCK_SPECS) == section_keys

    def test_carrier_files_exist(self):
        """每章登记的 partial 与写入器模块文件都存在。"""
        for key, spec in SECTION_BLOCK_SPECS.items():
            for name in spec.partials:
                assert (_PARTIAL_DIR / name).is_file(), f"{key}: 缺 partial {name}"
            for name in spec.modules:
                assert (_MODULE_DIR / name).is_file(), f"{key}: 缺写入器模块 {name}"

    def test_html_extraction_matches_spec(self):
        """HTML 实测提取（三源规则 + 归一化）与注册表 html 清单集合相等。"""
        for key, spec in SECTION_BLOCK_SPECS.items():
            got = extract_html_block_titles([_PARTIAL_DIR / p for p in spec.partials])
            assert got == set(spec.html or ()), f"{key}: html 实测 {sorted(got)} vs 注册表 {sorted(spec.html or ())}"

    def test_excel_extraction_matches_spec(self):
        """Excel 实测提取（write_block_title 调用点）与注册表 excel 清单集合相等。"""
        for key, spec in SECTION_BLOCK_SPECS.items():
            got = extract_excel_block_titles([_MODULE_DIR / m for m in spec.modules])
            assert got == set(spec.excel or ()), f"{key}: excel 实测 {sorted(got)} vs 注册表 {sorted(spec.excel or ())}"

    def test_dual_end_alignment(self):
        """双端都有区块的章节：html 与 excel 清单集合相等（双端对等断言）。"""
        for key, spec in SECTION_BLOCK_SPECS.items():
            if spec.html is not None and spec.excel is not None:
                assert set(spec.html) == set(spec.excel), f"{key}: 双端区块清单不等"

    def test_none_spec_still_carries_vectors(self):
        """双端皆无区块的条目仍登记载体（单表章/流式章契约完整、可定位提取面）。"""
        for key, spec in SECTION_BLOCK_SPECS.items():
            if spec.html is None and spec.excel is None:
                assert spec.partials and spec.modules, f"{key}: 双 None 条目缺载体登记"


class TestExtractionPrimitives:
    """提取原语：归一化口径 / HTML 三源规则 / Excel 直通包装与静态约束。"""

    def test_normalize_strips_markers_parens_and_labels(self):
        """归一化剥序号头、括号段、【】外框与 span 副标题（两端同口径）。"""
        assert normalize_block_title("① 总市值与总盈亏趋势") == "总市值与总盈亏趋势"
        assert normalize_block_title("一、市值核算明细") == "市值核算明细"
        assert normalize_block_title("【持仓概况】") == "持仓概况"
        assert normalize_block_title("行业 Beta（组合对各行业指数敏感性）") == "行业 Beta"
        assert (
            normalize_block_title('事件窗量化对照 <span style="font-size:12px;">新闻事件 × 持仓行情窗口比对</span>')
            == "事件窗量化对照"
        )

    def test_html_extract_three_source_rules(self, tmp_path):
        """block-title 全计 + 带序号加粗 div + 框式注释兜底（可见优先、裸注释不计）。"""
        partial = tmp_path / "fake_section.html"
        partial.write_text(
            """
        <div class="block-title">一、甲区块</div>
        <div style="font-weight: bold; font-size: 14px;">块内小标签（不带序号，不计）</div>
        <div style="font-weight: bold; font-size: 14px;">① 乙区块</div>
        <!-- ── 一、甲区块：旧注释（序号已被可见区块占用，丢弃） ── -->
        <!-- ── 三、丙区块（注释兜底计） ── -->
        <!-- ② 裸注释不计 -->
        """,
            encoding="utf-8",
        )
        assert extract_html_block_titles([partial]) == {"甲区块", "乙区块", "丙区块"}

    def test_excel_extract_resolves_forwarder_call_sites(self, tmp_path):
        """参数直通包装（_write_sub_block 形态）从调用点位参取区块名。"""
        mod = tmp_path / "fake_forwarder.py"
        mod.write_text(
            """
def write_block_title(ws, row, title):
    return row + 1

def _write_sub_block(ws, row, title):
    return write_block_title(ws, row, title)

def render(ws, row):
    row = _write_sub_block(ws, row, "区块甲")
    row = write_block_title(ws, row, "区块乙")
    return row
""",
            encoding="utf-8",
        )
        assert extract_excel_block_titles([mod]) == {"区块甲", "区块乙"}

    def test_excel_extract_rejects_dynamic_title(self, tmp_path):
        """动态拼接标题抛 ValueError（契约要求静态可提取，不静默漏计）。"""
        mod = tmp_path / "fake_dynamic.py"
        mod.write_text(
            """
def write_block_title(ws, row, title):
    return row + 1

def render(ws, row, name):
    return write_block_title(ws, row, f"动态{name}")
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="静态可提取"):
            extract_excel_block_titles([mod])


class TestSpecSideHelpers:
    """注册表构造器语义（both/excel_only/none 三形态）。"""

    def test_both_sets_identical_lists(self):
        spec = SectionBlockSpec.both(("甲", "乙"), partials=("a.html",), modules=("m.py",))
        assert spec.html == spec.excel == ("甲", "乙")

    def test_excel_only_leaves_html_none(self):
        spec = SectionBlockSpec.excel_only(("甲",), partials=("a.html",), modules=("m.py",))
        assert spec.html is None and spec.excel == ("甲",)

    def test_none_leaves_both_ends_empty(self):
        spec = SectionBlockSpec.none(partials=("a.html",), modules=("m.py",))
        assert spec.html is None and spec.excel is None

    def test_specs_are_frozen(self):
        spec = next(iter(SECTION_BLOCK_SPECS.values()))
        with pytest.raises(Exception):  # noqa: B017 — dataclass frozen 写入即抛，类型不限
            spec.html = ()

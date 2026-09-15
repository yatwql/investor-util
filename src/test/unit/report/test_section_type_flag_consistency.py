"""章节类型 ↔ board 层可见性旗标 ↔ 模块装配键 一致性守卫。

测试目标（每个章节合并批次都必须保持绿）：
  - 注册表 type ↔ 两侧 board_flags 映射键：每个 type 都在 Excel 侧
    （excel_sheet_factory.create_sheets）与 HTML 侧
    （html_writer_nav._compute_section_visibility）的 board_flags 字典中显式登记
  - 两侧 board_flags 键集合一致（除各自特有项外）
  - 页签写入器模块键 ↔ 装配键：分派层 `modules.get("write_*")` 引用的每个键
    都由 excel_module_loader 装配（模块键与装配键必须同步，避免生成期才暴露缺失）

设计意图：章节改名/合并时，注册表 type 是「可见性旗标的语义身份」，
它必须与两侧 board_flags 键、以及写入器模块装配键严格一致——
任一处保留旧名即视为命名未统一（见实施层施工单「命名统一的下游影响清单」）。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from src.python.core.registry import _REPORT_SECTION_DEFAULT
from src.python.report import excel_module_loader, excel_sheet_factory, html_writer_nav

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_LOADER_PATH = Path(inspect.getfile(excel_module_loader))
_REPORT_DIR = _LOADER_PATH.parent


def _extract_board_flag_keys(func) -> set[str]:
    """从函数源码的 `board_flags = { ... }` 字面量提取键名。"""
    src = inspect.getsource(func)
    m = re.search(r"board_flags(?:\s*:\s*[^=]+)?\s*=\s*\{(.*?)\n    \}", src, re.S)
    assert m, f"{func.__name__} 中未找到 board_flags 字典字面量"
    return set(re.findall(r'"([a-z_]+)":', m.group(1)))


class TestRegistryTypeBoardFlagConsistency:
    """注册表 type 必须与两侧 board_flags 键一致（三处严格一致纪律）。"""

    def test_every_registry_type_registered_in_both_side_board_flags(self):
        """注册表所有 type 都在 Excel 与 HTML 两侧 board_flags 中显式登记。"""
        registry_types = {sec["type"] for sec in _REPORT_SECTION_DEFAULT}
        excel_keys = _extract_board_flag_keys(excel_sheet_factory.create_sheets)
        html_keys = _extract_board_flag_keys(html_writer_nav._compute_section_visibility)
        missing_excel = registry_types - excel_keys
        missing_html = registry_types - html_keys
        assert not missing_excel, f"Excel 侧 board_flags 缺少 type: {sorted(missing_excel)}"
        assert not missing_html, f"HTML 侧 board_flags 缺少 type: {sorted(missing_html)}"

    def test_board_flags_keys_consistent_between_sides(self):
        """两侧 board_flags 键集合一致（可见性模型单一事实来源，防单侧漏改）。"""
        excel_keys = _extract_board_flag_keys(excel_sheet_factory.create_sheets)
        html_keys = _extract_board_flag_keys(html_writer_nav._compute_section_visibility)
        assert excel_keys == html_keys, (
            f"两侧 board_flags 键不一致：Excel 多 {sorted(excel_keys - html_keys)}，"
            f"HTML 多 {sorted(html_keys - excel_keys)}"
        )

    def test_no_stale_type_in_board_flags(self):
        """board_flags 不得残留注册表已不存在的 type（防旧章节类型遗留）。"""
        registry_types = {sec["type"] for sec in _REPORT_SECTION_DEFAULT}
        excel_keys = _extract_board_flag_keys(excel_sheet_factory.create_sheets)
        stale = excel_keys - registry_types
        assert not stale, f"board_flags 残留已废弃 type: {sorted(stale)}"


class TestSheetWriterModuleKeyConsistency:
    """分派层引用的写入器模块键，必须都由 excel_module_loader 装配。"""

    def _dispatch_writer_keys(self) -> set[str]:
        """扫描编排层各模块源码，收集 `modules.get(\"write_*\")` 引用的键。"""
        keys: set[str] = set()
        for path in sorted(_REPORT_DIR.glob("excel_*.py")):
            if path.name == "excel_module_loader.py":
                continue
            src = path.read_text(encoding="utf-8")
            keys |= set(re.findall(r'modules\.get\(\s*"(write_[a-z_]+)"', src))
        return keys

    def _assembled_keys(self) -> set[str]:
        """扫描装配层源码，收集 `modules[\"write_*\"] = ...` 装配的键。"""
        src = _LOADER_PATH.read_text(encoding="utf-8")
        return set(re.findall(r'modules\[\s*"(write_[a-z_]+)"\s*\]', src))

    def test_all_dispatch_writer_keys_are_assembled(self):
        """分派层引用的每个写入器键都在装配层登记（防改名漏同步）。"""
        dispatch = self._dispatch_writer_keys()
        assembled = self._assembled_keys()
        missing = dispatch - assembled
        assert not missing, f"分派层引用了未装配的写入器模块键: {sorted(missing)}"

    def test_holdings_detail_writer_key_wired(self):
        """合并章节写入器键已装配且被分派层引用（批次② 章节合并回归守卫）。"""
        assert "write_holdings_detail_sheet" in self._assembled_keys()
        assert "write_holdings_detail_sheet" in self._dispatch_writer_keys()
        # 旧章节写入器键不得再出现
        assert "write_market_value_sheet" not in self._assembled_keys()
        assert "write_category_sheet" not in self._assembled_keys()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

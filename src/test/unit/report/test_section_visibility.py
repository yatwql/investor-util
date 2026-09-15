"""章节可见性模型单元测试（两层可见性 + 多契约 OR 语义）。

覆盖：单契约 `data_flag` 的乐观判定（未登记视为就绪）与多契约 `data_flag_any`
的悲观 OR 判定（任一登记就绪即可见；未登记视为未就绪）；Excel 页签创建与
HTML 章节可见性两侧同口径。

运行：
  pytest src/test/unit/report/test_section_visibility.py -v
"""

from __future__ import annotations

import pytest

from src.python.report.excel_sheet_factory import should_create_sheet

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _section(**extra) -> dict:
    base = {"key": "demo", "name": "演示", "number": 1, "type": "always", "data_flag": None}
    base.update(extra)
    return base


class TestSingleContractFlag:
    """单契约 `data_flag`：既有乐观口径（未登记视为就绪）。"""

    def test_no_flag_always_visible(self):
        assert should_create_sheet(_section(), {}) is True

    def test_registered_true(self):
        assert should_create_sheet(_section(data_flag="demo_data"), {"demo_data": True}) is True

    def test_registered_false(self):
        assert should_create_sheet(_section(data_flag="demo_data"), {"demo_data": False}) is False

    def test_unregistered_treated_ready(self):
        """未登记视为就绪（页签先建、数据由下游兜底）——既有行为不得改变。"""
        assert should_create_sheet(_section(data_flag="demo_data"), {}) is True


class TestMultiContractFlagAny:
    """多契约 `data_flag_any`：任一就绪即可见（悲观判定）。"""

    def test_any_one_ready(self):
        sec = _section(data_flag_any=("block_a_data", "block_b_data"))
        assert should_create_sheet(sec, {"block_a_data": True, "block_b_data": False}) is True
        assert should_create_sheet(sec, {"block_a_data": False, "block_b_data": True}) is True

    def test_all_absent_hidden(self):
        sec = _section(data_flag_any=("block_a_data", "block_b_data"))
        assert should_create_sheet(sec, {"block_a_data": False, "block_b_data": False}) is False

    def test_unregistered_treated_not_ready(self):
        """悲观判定：未登记的契约不构成「就绪」信号（否则合并条目会显示空页签）。"""
        sec = _section(data_flag_any=("block_a_data", "block_b_data"))
        assert should_create_sheet(sec, {}) is False

    def test_single_element_behaves_like_flag(self):
        sec = _section(data_flag_any=("only_data",))
        assert should_create_sheet(sec, {"only_data": True}) is True
        assert should_create_sheet(sec, {"only_data": False}) is False


def _visibility(order, *, concentration_analysis=None, position_relationship_data=None, enable_fund_deep_analysis=True):
    """调用真实可见性函数（data 层旗标由其入参推导，测试用真实契约形参驱动）。"""
    from src.python.report.html_writer_nav import _compute_section_visibility

    _, visible, _ = _compute_section_visibility(
        order,
        None,
        None,
        concentration_analysis,
        None,
        False,
        False,
        enable_fund_deep_analysis=enable_fund_deep_analysis,
        position_relationship_data=position_relationship_data,
    )
    return visible


class TestHtmlSideMatchesExcel:
    """HTML 侧与 Excel 侧同口径（含多契约 OR）。

    注：两侧对**单契约未登记**的既有口径本就不同——Excel 乐观（未出现视为就绪，
    页签先建、数据由下游兜底），HTML 悲观（未出现视为隐藏）；本用例锁定现状，
    多契约 OR 则两侧一致为悲观。
    """

    def test_single_flag_unregistered_hidden_on_html_side(self):
        """既有口径：HTML 侧未登记的 data_flag 视为隐藏（与 Excel 侧乐观口径不同）。"""
        order = [_section(key="demo", data_flag="demo_data", type="always")]
        assert _visibility(order)["demo"] is False

    def test_or_flag_any_ready_visible(self):
        order = [
            _section(
                key="merged",
                type="fund_deep_analysis",
                data_flag_any=("position_relationship_data", "concentration_data"),
            )
        ]
        assert _visibility(order, position_relationship_data={})["merged"] is True

    def test_or_flag_none_ready_hidden(self):
        order = [
            _section(
                key="merged",
                type="fund_deep_analysis",
                data_flag_any=("position_relationship_data", "concentration_data"),
            )
        ]
        assert _visibility(order)["merged"] is False

    def test_or_respects_board_layer(self):
        """board 层关闭时，即使契约就绪也隐藏（两层 AND 语义不变）。"""
        order = [
            _section(
                key="merged",
                type="fund_deep_analysis",
                data_flag_any=("position_relationship_data", "concentration_data"),
            )
        ]
        assert _visibility(order, position_relationship_data={}, enable_fund_deep_analysis=False)["merged"] is False


class TestPositionStructureMergedChapter:
    """合并章「持仓结构与集中度」的 OR 可见性（真实注册表条目，一侧就绪即可见）。"""

    @staticmethod
    def _section():
        from src.python.core.registry import _REPORT_SECTION_DEFAULT

        return next(s for s in _REPORT_SECTION_DEFAULT if s["key"] == "position_structure")

    def test_registered_with_two_contracts(self):
        sec = self._section()
        assert sec["type"] == "fund_deep_analysis"
        assert sec["data_flag"] is None
        assert sec["data_flag_any"] == ("position_relationship_data", "concentration_data")

    def test_visible_when_only_relationship_contract_ready(self):
        sec = self._section()
        assert should_create_sheet(sec, {"position_relationship_data": True, "concentration_data": False}) is True

    def test_visible_when_only_concentration_contract_ready(self):
        sec = self._section()
        assert should_create_sheet(sec, {"position_relationship_data": False, "concentration_data": True}) is True

    def test_hidden_when_both_contracts_absent(self):
        sec = self._section()
        assert should_create_sheet(sec, {"position_relationship_data": False, "concentration_data": False}) is False

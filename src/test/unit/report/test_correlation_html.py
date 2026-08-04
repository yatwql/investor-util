"""持仓关系矩阵章节·相关性区块 HTML 呈现测试。

覆盖：
  - available=True → 汇总卡 + 相关度最高提示 + 热力矩阵 + 配对明细 + 说明
  - 强正/强负/不显著/N/A 单元格样式分支
  - 重叠样本不足品种提示行
  - available=False（数据不足 / 数据源故障）→ 降级占位
  - 相关性数据 None → 相关性区块渲染占位（章节由重合度区块驱动可见）

注意：模板在持仓关系矩阵章节内部直接调用 position_relationship_data.get()，
生产路径由 html_writer 保证重合度或相关性任一区块有数据时该章节才可见，
因此 None 场景通过「相关性区块占位」验证（重合度区块驱动章节可见）。
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

from src.test.unit.report.test_html_report_structure import (
    _REPORT_SECTION_DEFAULT,
    _build_minimal_render_data,
    _render_template,
)

_PR_SECTION = {"key": "position_relationship", "name": "持仓关系矩阵", "number": 7}


def _order_with_relationship() -> list[dict]:
    """默认清单中将 position_relationship 置为可见（其余隐藏）。"""
    return [dict(sec) for sec in _REPORT_SECTION_DEFAULT]


def _render_correlation(correlation_data) -> "BeautifulSoup":
    """渲染 position_relationship 可见、其余隐藏的模板。"""
    order = _order_with_relationship()
    numbers = {sec["key"]: sec["number"] for sec in order}
    sv_dict = {sec["key"]: (sec["key"] == "position_relationship") for sec in order}
    data = _build_minimal_render_data(order, numbers, sv_dict)
    data["position_relationship_data"] = correlation_data
    # 章节可见需重合度或相关性任一区块有数据：此处以相关性区块驱动（overlap 置空）
    data["overlap_matrix"] = {"fund_names": {}, "funds": [], "matrix": [], "pairs": []}
    return _render_template(data)


def _correlation_data(**extra) -> dict:
    """构造持仓关系矩阵·相关性区块数据契约 mock（2 品种，强负相关）。"""
    d = {
        "available": True,
        "status": "ok",
        "window": 60,
        "sample_count": 60,
        "codes": ["a", "b"],
        "names": {"a": "资产A", "b": "资产B"},
        "matrix": [[1.0, None], [-0.87, 1.0]],
        "p_values": [[None, None], [0.0001, None]],
        "pairs": [
            {
                "code_a": "b",
                "name_a": "资产B",
                "code_b": "a",
                "name_b": "资产A",
                "pearson": -0.87,
                "p_value": 0.0001,
                "significant": True,
                "samples": 60,
            }
        ],
        "insufficient_codes": [],
        "note": "",
    }
    d.update(extra)
    return d


class TestHtmlCorrelationSection(unittest.TestCase):
    """持仓关系矩阵章节·相关性区块 HTML 呈现测试。"""

    def _section(self, correlation_data):
        return _render_correlation(correlation_data).find(id="sec-position_relationship")

    def test_full_rendering_when_available(self):
        """available=True → 汇总卡 + 相关度最高 + 热力矩阵 + 配对明细 + 说明。"""
        section = self._section(_correlation_data())
        text = section.get_text()
        self.assertIn("持仓相关性矩阵", text)
        self.assertIn("个品种", text)  # 汇总卡
        self.assertIn("相关度最高", text)  # 提示横幅
        self.assertIn("配对明细", text)  # 配对表
        self.assertIn("资产A", text)
        self.assertIn("资产B", text)
        self.assertIn("-0.87", text)  # r 值
        self.assertIn("显著", text)
        # 说明区
        self.assertIn("Pearson 相关系数", text)

    def test_matrix_cell_branches(self):
        """单元格样式分支：强负/不显著/N/A/对角线。"""
        data = _correlation_data()
        data["codes"] = ["a", "b", "c"]
        data["names"] = {"a": "资产A", "b": "资产B", "c": "资产C"}
        data["matrix"] = [
            [1.0, None, None],
            [-0.6, 1.0, None],  # b×a 强负
            [None, 0.02, 1.0],  # c×a 样本不足 N/A；c×b 不显著 0.02
        ]
        data["p_values"] = [
            [None, None, None],
            [0.001, None, None],
            [None, 0.20, None],
        ]
        data["pairs"] = [
            {
                "code_a": "b",
                "name_a": "资产B",
                "code_b": "a",
                "name_b": "资产A",
                "pearson": -0.6,
                "p_value": 0.001,
                "significant": True,
                "samples": 60,
            },
            {
                "code_a": "c",
                "name_a": "资产C",
                "code_b": "b",
                "name_b": "资产B",
                "pearson": 0.02,
                "p_value": 0.20,
                "significant": False,
                "samples": 60,
            },
        ]
        section = self._section(data)
        text = section.get_text()
        self.assertIn("强负", text)  # r=-0.6 ≤ -0.5 → 强负格
        self.assertIn("N/A", text)  # c×a 样本不足
        self.assertIn("0.02", text)  # 不显著白格显示数值
        self.assertIn("1.00", text)  # 对角线自相关

    def test_insufficient_codes_note(self):
        """重叠样本不足品种 → 灰 N/A 提示行。"""
        data = _correlation_data()
        data["insufficient_codes"] = ["a", "b"]
        data["matrix"] = [[1.0, None], [None, 1.0]]
        section = self._section(data)
        text = section.get_text()
        self.assertIn("相关性格标为 N/A", text)
        self.assertIn("a", text)

    def test_insufficient_placeholder(self):
        """available=False + status=insufficient → 数据不足占位。"""
        data = _correlation_data(available=False, status="insufficient", sample_count=20, window=60, codes=[], pairs=[])
        section = self._section(data)
        self.assertIn("持仓相关性数据不足", section.get_text())
        self.assertNotIn("配对明细", section.get_text())

    def test_source_failed_placeholder(self):
        """available=False + status=source_failed → 数据源暂不可用占位。"""
        data = _correlation_data(available=False, status="source_failed", codes=[], pairs=[])
        section = self._section(data)
        self.assertIn("数据源暂不可用", section.get_text())

    def test_correlation_none_placeholder(self):
        """相关性数据 None → 相关性区块渲染占位（重合度区块驱动章节可见）。"""
        section = self._section(None)
        text = section.get_text()
        self.assertIn("持仓相关性数据不足", text)
        self.assertNotIn("配对明细", text)


def _overlap_result(**extra) -> dict:
    """构造持仓关系矩阵·重合度区块结构（2 只基金，部分重合 50%）。"""
    d = {
        "fund_names": {"a": "基金A", "b": "基金B"},
        "funds": ["a", "b"],
        "matrix": [
            [1.0, 0.5],
            [0.5, 1.0],
        ],
        "pairs": [
            {
                "fund_a": "a",
                "fund_b": "b",
                "name_a": "基金A",
                "name_b": "基金B",
                "code_a": "a",
                "code_b": "b",
                "common_count": 2,
                "jaccard": 0.5,
                "common_stocks": [
                    {"name": "贵州茅台", "code": "600519"},
                    {"name": "五粮液", "code": "000858"},
                ],
            }
        ],
    }
    d.update(extra)
    return d


class TestHtmlMergedRelationshipSection(unittest.TestCase):
    """持仓关系矩阵章节·一章两区块（重合度 + 相关性）HTML 呈现测试。"""

    def _render_merged(self, overlap_matrix, correlation_data) -> "BeautifulSoup":
        order = _order_with_relationship()
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: (sec["key"] == "position_relationship") for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["overlap_matrix"] = overlap_matrix
        data["position_relationship_data"] = correlation_data
        return _render_template(data).find(id="sec-position_relationship")

    def test_both_blocks_render_in_merged_section(self):
        """重合度 + 相关性同时提供 → 同一章节内两个子区块依次呈现。"""
        section = self._render_merged(_overlap_result(), _correlation_data())
        text = section.get_text()
        self.assertIn("一、持仓重合度矩阵", text)
        self.assertIn("二、持仓相关性矩阵", text)
        # 重合度区块内容
        self.assertIn("基金A", text)
        self.assertIn("基金B", text)
        self.assertIn("50.00%", text)  # Jaccard 0.5
        # 相关性区块内容
        self.assertIn("资产A", text)
        self.assertIn("-0.87", text)
        self.assertIn("配对明细", text)

    def test_overlap_only_section_visible_correlation_placeholder(self):
        """仅重合度数据 → 章节可见，相关性区块写占位（相关性配对表不出现）。"""
        section = self._render_merged(_overlap_result(), None)
        text = section.get_text()
        self.assertIn("一、持仓重合度矩阵", text)
        self.assertIn("基金A", text)
        self.assertIn("持仓相关性数据不足", text)
        # 相关性配对表表头（品种A/相关系数 r）不应出现；重合度区块自身的配对明细合法保留
        self.assertNotIn("相关系数 r", text)

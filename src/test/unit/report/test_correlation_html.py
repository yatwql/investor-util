"""持仓相关性矩阵章节 HTML 呈现测试。

覆盖：
  - available=True → 汇总卡 + 相关度最高提示 + 热力矩阵 + 配对明细 + 说明
  - 强正/强负/不显著/N/A 单元格样式分支
  - 重叠样本不足品种提示行
  - available=False（数据不足 / 数据源故障）→ 降级占位
  - correlation_data=None → 章节整体隐藏（html_writer 数据门控）

注意：模板在 correlation 章节内部直接调用 correlation_data.get()，
生产路径由 html_writer 保证 correlation_data 非 None 时才渲染该章节，
因此 None 场景测试通过「章节不可见」验证（而非渲染占位）。
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

_CORR_SECTION = {"key": "correlation_analysis", "name": "持仓相关性矩阵", "number": 11}


def _order_with_correlation() -> list[dict]:
    """默认清单追加 correlation_analysis 章节。"""
    return [dict(sec) for sec in _REPORT_SECTION_DEFAULT] + [dict(_CORR_SECTION)]


def _render_correlation(correlation_data) -> "BeautifulSoup":
    """渲染 correlation_analysis 可见、其余隐藏的模板。"""
    order = _order_with_correlation()
    numbers = {sec["key"]: sec["number"] for sec in order}
    sv_dict = {sec["key"]: (sec["key"] == "correlation_analysis") for sec in order}
    data = _build_minimal_render_data(order, numbers, sv_dict)
    data["correlation_data"] = correlation_data
    return _render_template(data)


def _correlation_data(**extra) -> dict:
    """构造 C19 契约 correlation_data mock（2 品种，强负相关）。"""
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
    """持仓相关性章节 HTML 呈现测试。"""

    def _section(self, correlation_data):
        return _render_correlation(correlation_data).find(id="sec-correlation_analysis")

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

    def test_correlation_none_section_hidden(self):
        """correlation_data=None → 章节整体不渲染（html_writer 数据门控）。"""
        order = _order_with_correlation()
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: False for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["correlation_data"] = None
        soup = _render_template(data)
        self.assertIsNone(soup.find(id="sec-correlation_analysis"))

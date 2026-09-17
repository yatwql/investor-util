"""财务指标提取（DataSinking 全文解析层）边缘场景测试。

覆盖：取值窗口边界、异常幅度与越界比率拒绝、孤立数值/零基数同比、
非数值行文、被截断的正文、无关数字干扰下的定位。

运行：
  pytest src/test/unit/analysis/test_financial_indicator_extract_edge.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.financial_indicator_extract import extract_indicators

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


def _synthetic(rows: str, unit: str = "单位：元币种：人民币") -> str:
    return f"(一) 主要会计数据{unit}主要会计数据2025年2024年本期比上年同期增减2023年调整后调整前{rows}"


class TestValueWindow:
    def test_gap_at_limit_is_accepted(self):
        """锚点与数值间隔恰好等于上限时仍取值。"""
        row = extract_indicators(_synthetic("营业收入" + "x" * 8 + "86,241,940,222.2084,491,870,566.52"))
        assert row is not None
        assert row["revenue"] == pytest.approx(86_241_940_222.20)

    def test_gap_beyond_limit_is_rejected(self):
        """间隔超过上限（疑为跨行）时弃用，不取远端的数字。"""
        assert extract_indicators(_synthetic("营业收入" + "x" * 9 + "86,241,940,222.2084,491,870,566.52")) is None


class TestRejection:
    def test_absurd_amount_magnitude_rejected(self):
        """无小数的整数连写被并成一个天文数字 → 拒绝（宁缺勿错）。"""
        assert extract_indicators(_synthetic("营业收入86241940222208449187056")) is None

    def test_percent_out_of_range_rejected(self):
        """比率超出 [-100, 100] 百分数区间 → 拒绝。"""
        assert extract_indicators(_synthetic("加权平均净资产收益率（%）250.00230.00")) is None

    def test_truncated_tail_without_numbers(self):
        """正文在锚点处被截断（其后无任何数值）→ 不产出。"""
        assert extract_indicators(_synthetic("营业收入")) is None

    def test_non_numeric_wording_ignored(self):
        """「不适用」等非数值行文不产生字段。"""
        assert extract_indicators(_synthetic("营业收入不适用不适用")) is None

    def test_whitespace_only_content(self):
        assert extract_indicators("   \n\t  ") is None


class TestDerivedYoy:
    def test_single_value_keeps_amount_without_yoy(self):
        """只有本期一个数值时保留金额，同比取 None。"""
        row = extract_indicators(_synthetic("营业收入86,241,940,222.20"))
        assert row["revenue"] == pytest.approx(86_241_940_222.20)
        assert row["revenue_yoy"] is None

    def test_zero_prior_yields_none_yoy(self):
        """上年为 0 时同比不可计算 → None（不做除法）。"""
        row = extract_indicators(_synthetic("营业收入86,241,940,222.200.00"))
        assert row["revenue"] == pytest.approx(86_241_940_222.20)
        assert row["revenue_yoy"] is None


class TestPositioning:
    def test_anchor_located_amid_unrelated_numbers(self):
        """正文前部充满无关数字时仍正确定位指标行。"""
        noise = "2025年年度报告第3页共120页证券代码600900单位：元币种：人民币"
        text = _synthetic("") + noise + "营业收入86,241,940,222.2084,491,870,566.52"
        row = extract_indicators(text)
        assert row["revenue"] == pytest.approx(86_241_940_222.20)

    def test_latest_unit_declaration_before_anchor_wins(self):
        """锚点前有多处单位声明时取最近一处（附表单位可能不同）。"""
        text = _synthetic("", unit="单位：万元币种：人民币") + "其他说明单位：元币种：人民币营业收入86,241,940.22"
        row = extract_indicators(text)
        assert row["revenue"] == pytest.approx(86_241_940.22)

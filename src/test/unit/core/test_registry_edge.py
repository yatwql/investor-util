"""Registry 报告序号可配置 edge 场景专项测试。

从 test_registry.py 提取的 edge 场景：
  - get_report_section_order 异常值处理（None/缺失/浮点数/布尔值/大数值）
  - 配置中存在未知 key
  - 所有模块使用同序号时的稳定排序行为
  - 返回值总数始终为 17 项的不变性

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/core/test_registry_edge.py -v
"""

from __future__ import annotations

import pytest

from src.python.registry import (
    get_report_section_order,
    _REPORT_SECTION_DEFAULT,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


class TestGetReportSectionOrderEdge:
    """get_report_section_order() edge 场景测试。"""

    def test_extra_keys_ignored(self):
        """配置中多出的未知 key → 忽略（不影响结果）。"""
        order = get_report_section_order({
            "report_section_order": {"summary": 5, "unknown_module": 1}
        })
        assert len(order) == 17
        summary = [s for s in order if s["key"] == "summary"][0]
        assert summary["number"] == 5

    def test_all_odd_numbers_in_config(self):
        """所有可配模块使用相同序号 → 按 Python 稳定排序保留原始相对顺序。"""
        order = get_report_section_order({
            "report_section_order": {"summary": 1, "market_value": 1,
                                      "category": 1, "penetration": 1,
                                      "fund_performance": 1}
        })
        # 已配置 5 项都在前面（key 顺序 = 排序前插入顺序）
        first_5 = [s["key"] for s in order[:5]]
        assert "summary" in first_5
        assert "market_value" in first_5
        assert order[-1]["key"] == "llm_usage"

    def test_none_config_value_fallsback(self):
        """report_section_order 为 None → 返回默认顺序。"""
        order = get_report_section_order({"report_section_order": None})
        assert len(order) == 17
        assert order[0]["key"] == "summary"
        assert order[-1]["key"] == "llm_usage"

    def test_missing_key_returns_defaults(self):
        """配置字典不含 report_section_order → 返回默认顺序。"""
        order = get_report_section_order({"holdings_dir": "data"})
        assert len(order) == 17
        assert order[0]["number"] == 1

    def test_float_number_truncated(self):
        """浮点数序号 → int() 截断取整。"""
        order = get_report_section_order({
            "report_section_order": {"summary": 1.9}
        })
        summary = [s for s in order if s["key"] == "summary"][0]
        assert summary["number"] == 1  # int(1.9) = 1

    def test_large_number_accepted(self):
        """大数值序号（如 999）→ registry 不校验，保留用户值。"""
        order = get_report_section_order({
            "report_section_order": {"summary": 999}
        })
        summary = [s for s in order if s["key"] == "summary"][0]
        assert summary["number"] == 999

    def test_boolean_true_as_number(self):
        """True（isinstance int） → 转为 1。"""
        order = get_report_section_order({
            "report_section_order": {"summary": True}
        })
        summary = [s for s in order if s["key"] == "summary"][0]
        assert summary["number"] == 1  # int(True) = 1

    def test_total_always_17_items(self):
        """无论配置如何，返回值始终 17 项。"""
        order1 = get_report_section_order({"report_section_order": {"summary": 1}})
        assert len(order1) == 17
        order2 = get_report_section_order({"report_section_order": dict.fromkeys(
            [s["key"] for s in _REPORT_SECTION_DEFAULT if s["key"] != "llm_usage"], 1
        )})
        assert len(order2) == 17

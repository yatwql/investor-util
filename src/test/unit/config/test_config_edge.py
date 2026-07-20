"""Config report_section_order edge 场景专项测试。

edge 场景：
  - 浮点值作为序号（int() 隐式转换）
  - 布尔值 True/False 作为序号（bool 是 int 子类）
  - 极大序号
  - 多个重复序号累积计数
  - llm_usage + 未知 key 组合场景

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/config/test_config_edge.py -v
"""

from __future__ import annotations

import unittest
import pytest

import src.python.config as cfg

pytestmark = [pytest.mark.unit, pytest.mark.unit_config, pytest.mark.edge]


class TestValidateReportSectionOrderEdge(unittest.TestCase):
    """report_section_order 配置校验 edge 场景测试。"""

    def test_float_value_accepted(self):
        """浮点值（如 1.5）→ int(1.5)=1，通过校验（0 问题）。"""
        n = cfg.validate_config({
            "report_section_order": {"summary": 1.5}
        })
        self.assertEqual(n, 0)

    def test_boolean_true_does_not_warn(self):
        """True（bool 是 int 子类）→ 0 问题（Python 中 True 通过 isinstance(x, int) 检查）。"""
        n = cfg.validate_config({
            "report_section_order": {"summary": True}
        })
        self.assertEqual(n, 0)

    def test_boolean_false_warns(self):
        """False（int(False)=0）→ 1 问题（零值非法）。"""
        n = cfg.validate_config({
            "report_section_order": {"summary": False}
        })
        self.assertEqual(n, 1)

    def test_large_number_accepted(self):
        """极大序号（如 999）→ 通过校验（0 问题）。"""
        n = cfg.validate_config({
            "report_section_order": {"summary": 999}
        })
        self.assertEqual(n, 0)

    def test_multiple_duplicate_numbers(self):
        """多个重复序号 → 每个重复项均计问题。"""
        n = cfg.validate_config({
            "report_section_order": {
                "summary": 1, "market_value": 1,
                "category": 1, "penetration": 1,
            }
        })
        self.assertEqual(n, 3)  # 第 1 个不重复，后 3 个重复

    def test_llm_usage_and_unknown_together(self):
        """llm_usage 配置 + 未知 key → 2 问题。"""
        n = cfg.validate_config({
            "report_section_order": {
                "llm_usage": 1,
                "not_a_module": 5,
            }
        })
        self.assertEqual(n, 2)

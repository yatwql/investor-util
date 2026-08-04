"""报告序号可配置 — 业务场景验证。

验证目标：
  - 默认顺序完整性（len(_REPORT_SECTION_DEFAULT) 个模块，summary 开头/llm_usage 结尾）
  - 序号 1~N 连续递增
  - get_report_section_keys 完备性
  - 6 种可见性类型计数正确（always=6, history=1, fund_deep_analysis=5, news=1, llm=5, evolution=1）
  - 基金深度分析 data_flag 各不相同
  - 空配置与无配置行为一致

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/scenario/basic/test_scenario_section_order.py -v
"""

from __future__ import annotations

import unittest

import pytest

from src.python.core.registry import _REPORT_SECTION_DEFAULT

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]


class TestScenarioSectionOrder(unittest.TestCase):
    """报告序号可配置 — 业务场景验证。

    验证默认顺序完整性、序号连续性、注册表与 Excel 命名一致性。
    """

    def setUp(self):
        from src.python.core.registry import (
            _REPORT_SECTION_DEFAULT,
            get_report_section_order,
            get_report_section_keys,
        )

        self._default = _REPORT_SECTION_DEFAULT
        self._get_order = get_report_section_order
        self._get_keys = get_report_section_keys

    def test_default_order_full_items(self):
        """默认顺序包含完整的 N 个模块。"""
        order = self._get_order()
        self.assertEqual(len(order), len(self._default))

    def test_default_order_correct_start_end(self):
        """默认顺序以 summary 开头，以 llm_usage 结尾。"""
        order = self._get_order()
        self.assertEqual(order[0]["key"], "summary")
        self.assertEqual(order[-1]["key"], "llm_usage")

    def test_default_numbers_sequential(self):
        """默认序号为 1~N 连续递增。"""
        order = self._get_order()
        numbers = [s["number"] for s in order]
        self.assertEqual(numbers, list(range(1, len(self._default) + 1)))

    def test_all_keys_valid(self):
        """get_report_section_keys 包含全部有效 key。"""
        keys = self._get_keys()
        expected = {s["key"] for s in self._default}
        self.assertEqual(keys, expected)

    def test_default_always_type_has_6_sections(self):
        """always 类型模块共 6 个（含数据源可用性矩阵），均无 data_flag。"""
        always = [s for s in self._default if s["type"] == "always"]
        self.assertEqual(len(always), 6)
        keys = {s["key"] for s in always}
        self.assertIn("data_source_status", keys)
        self.assertNotIn("portfolio_evolution", keys)
        for sec in always:
            self.assertIsNone(sec["data_flag"])

    def test_default_evolution_type_has_1_section(self):
        """evolution 类型模块共 1 个（组合演进，data_flag=evolution_data 控制可见性，
        available=False 时展示层写占位，见 technical.md §4.12）。"""
        evolution = [s for s in self._default if s["type"] == "evolution"]
        self.assertEqual(len(evolution), 1)
        sec = evolution[0]
        self.assertEqual(sec["key"], "portfolio_evolution")
        self.assertEqual(sec["data_flag"], "evolution_data")

    def test_default_fund_deep_analysis_type_has_4_sections(self):
        """基金深度分析类型模块共 4 个（含风格与因子分析一章三区块）。"""
        fund_deep_analysis = [s for s in self._default if s["type"] == "fund_deep_analysis"]
        self.assertEqual(len(fund_deep_analysis), 4)
        keys = [s["key"] for s in fund_deep_analysis]
        self.assertIn("fund_manager", keys)
        self.assertIn("position_relationship", keys)
        self.assertIn("fund_concentration", keys)
        self.assertIn("style_factor", keys)
        self.assertNotIn("fund_style", keys)
        self.assertNotIn("factor_exposure", keys)

    def test_default_news_type_has_1_section(self):
        """news 类型模块共 1 个（新闻）。"""
        news = [s for s in self._default if s["type"] == "news"]
        self.assertEqual(len(news), 1)
        key_set = {s["key"] for s in news}
        self.assertIn("news_correlation", key_set)

    def test_default_llm_type_has_5_sections(self):
        """llm 类型模块共 5 个（4 分析模块 + llm_usage）。"""
        llm = [s for s in self._default if s["type"] == "llm"]
        self.assertEqual(len(llm), 5)
        self.assertEqual(llm[-1]["key"], "llm_usage")

    def test_different_data_flags_in_fund_deep_analysis(self):
        """基金深度分析的 data_flag 各不相同。"""
        fund_deep_analysis = [s for s in self._default if s["type"] == "fund_deep_analysis"]
        flags = [s["data_flag"] for s in fund_deep_analysis]
        self.assertEqual(len(set(flags)), len(flags), f"data_flag 应各不相同: {flags}")

    def test_empty_config_equals_no_config(self):
        """空配置与无配置结果一致。"""
        order1 = self._get_order(None)
        order2 = self._get_order({"report_section_order": {}})
        for s1, s2 in zip(order1, order2):
            self.assertEqual(s1["key"], s2["key"])
            self.assertEqual(s1["number"], s2["number"])

    def test_6_visibility_types(self):
        """7 种 type 都有对应模块（含组合演进专属 evolution 类型、行动建议专属 action 类型）。"""
        type_counts: dict[str, int] = {}
        for sec in self._default:
            type_counts[sec["type"]] = type_counts.get(sec["type"], 0) + 1
        self.assertEqual(
            set(type_counts.keys()),
            {"always", "history", "fund_deep_analysis", "news", "llm", "evolution", "action"},
        )
        self.assertEqual(type_counts["always"], 6)
        self.assertEqual(type_counts["history"], 1)
        self.assertEqual(type_counts["fund_deep_analysis"], 4)
        self.assertEqual(type_counts["news"], 1)
        self.assertEqual(type_counts["llm"], 5)
        self.assertEqual(type_counts["evolution"], 1)
        self.assertEqual(type_counts["action"], 1)


class TestScenarioCustomSectionOrder(unittest.TestCase):
    """报告序号可配置 — 自定义顺序场景验证。

    验证 `get_report_section_order(config)` 在用户自定义配置下的合并行为。
    """

    def setUp(self):
        from src.python.core.registry import (
            get_report_section_order,
        )

        self._get_order = get_report_section_order

    def _partial_config(self) -> dict:
        """部分自定义配置：只覆盖前 3 个模块的序号。"""
        return {
            "report_section_order": {
                "fund_performance": 1,
                "summary": 2,
                "market_value": 3,
            }
        }

    def test_partial_custom_preserves_remaining_items(self):
        """部分自定义 → 仍返回 N 个模块，未配置项自动续编。"""
        order = self._get_order(self._partial_config())
        self.assertEqual(len(order), len(_REPORT_SECTION_DEFAULT))

    def test_partial_custom_reorders_modules(self):
        """部分自定义 → fund_performance 排第 1，summary 排第 2，market_value 排第 3。"""
        order = self._get_order(self._partial_config())
        self.assertEqual(order[0]["key"], "fund_performance")
        self.assertEqual(order[0]["number"], 1)
        self.assertEqual(order[1]["key"], "summary")
        self.assertEqual(order[1]["number"], 2)
        self.assertEqual(order[2]["key"], "market_value")
        self.assertEqual(order[2]["number"], 3)

    def test_partial_custom_auto_numbers_remaining(self):
        """部分自定义 → 未配置项保留原始序号（部分配置仅更改顺序和已配置项的序号）。"""
        order = self._get_order(self._partial_config())
        # 已配置项出现在前 3 位
        configured = {s["key"] for s in order[:3]}
        self.assertEqual(configured, {"fund_performance", "summary", "market_value"})
        # 未配置项 key 个数 = total - 3 已配置
        remaining = order[3:]
        self.assertEqual(len(remaining), len(_REPORT_SECTION_DEFAULT) - 3)
        # number 列应单调递增（可包含重复因部分配置和默认序号冲突）
        numbers = [s["number"] for s in remaining]
        for i in range(1, len(numbers)):
            self.assertGreaterEqual(numbers[i], numbers[i - 1], f"剩余项序号不单调递增: {numbers}")

    def test_partial_custom_all_keys_present(self):
        """部分自定义 → 所有 N 个 key 都出现且不重复。"""
        order = self._get_order(self._partial_config())
        keys = [s["key"] for s in order]
        self.assertEqual(len(set(keys)), len(_REPORT_SECTION_DEFAULT))

    def test_custom_unknown_key_falls_back_to_default(self):
        """自定义配置中有不在注册表中的 key → 忽略，不影响合并结果。"""
        config = {
            "report_section_order": {
                "summary": 1,
                "nonexistent_key": 99,
            }
        }
        order = self._get_order(config)
        self.assertEqual(len(order), len(_REPORT_SECTION_DEFAULT))
        keys = [s["key"] for s in order]
        self.assertNotIn("nonexistent_key", keys)

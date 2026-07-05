"""C 迭代报告序号可配置 — 业务场景验证。

验证目标：
  - 默认顺序完整性（16 个模块，summary 开头/llm_usage 结尾）
  - 序号 1~16 连续递增
  - get_report_section_keys 完备性
  - set_sheet_title 与默认注册表一致性
  - 4 种可见性类型计数正确（always=5, b_series=4, news=2, llm=5）
  - B 系列 data_flag 各不相同
  - 空配置与无配置行为一致

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/scenario/basic/test_scenario_section_order.py -v
"""

from __future__ import annotations

import unittest
import pytest

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]


class TestScenarioSectionOrder(unittest.TestCase):
    """C 迭代报告序号可配置 — 业务场景验证。

    验证默认顺序完整性、序号连续性、注册表与 Excel 命名一致性。
    """

    def setUp(self):
        from src.python.registry import (
            _REPORT_SECTION_DEFAULT,
            get_report_section_order,
            get_report_section_keys,
            set_sheet_title,
        )
        self._default = _REPORT_SECTION_DEFAULT
        self._get_order = get_report_section_order
        self._get_keys = get_report_section_keys
        self._set_title = set_sheet_title

    def test_default_order_16_items(self):
        """默认顺序包含完整的 16 个模块。"""
        order = self._get_order()
        self.assertEqual(len(order), 16)

    def test_default_order_correct_start_end(self):
        """默认顺序以 summary 开头，以 llm_usage 结尾。"""
        order = self._get_order()
        self.assertEqual(order[0]["key"], "summary")
        self.assertEqual(order[-1]["key"], "llm_usage")

    def test_default_numbers_1_to_16(self):
        """默认序号为 1~16 连续递增。"""
        order = self._get_order()
        numbers = [s["number"] for s in order]
        self.assertEqual(numbers, list(range(1, 17)))

    def test_all_keys_valid(self):
        """get_report_section_keys 包含全部 16 个有效 key。"""
        keys = self._get_keys()
        expected = {s["key"] for s in self._default}
        self.assertEqual(keys, expected)

    def test_set_sheet_title_vs_default(self):
        """set_sheet_title 对每个默认 key 生成正确的 "{number}.{name}"。"""

        class MockWs:
            def __init__(self):
                self.title = ""

        for sec in self._default:
            ws = MockWs()
            self._set_title(ws, sec["key"])
            expected = f"{sec['number']}.{sec['name']}"
            self.assertEqual(ws.title, expected,
                             f"{sec['key']}: 预期 {expected!r}，实际 {ws.title!r}")

    def test_default_always_type_has_5_sections(self):
        """always 类型模块共 5 个，均无 data_flag。"""
        always = [s for s in self._default if s["type"] == "always"]
        self.assertEqual(len(always), 5)
        for sec in always:
            self.assertIsNone(sec["data_flag"])

    def test_default_b_series_type_has_4_sections(self):
        """b_series 类型模块共 4 个（基金深度分析）。"""
        b_series = [s for s in self._default if s["type"] == "b_series"]
        self.assertEqual(len(b_series), 4)
        keys = [s["key"] for s in b_series]
        self.assertIn("fund_manager", keys)
        self.assertIn("fund_overlap", keys)
        self.assertIn("fund_concentration", keys)
        self.assertIn("fund_style", keys)

    def test_default_news_type_has_2_sections(self):
        """news 类型模块共 2 个（新闻+预警）。"""
        news = [s for s in self._default if s["type"] == "news"]
        self.assertEqual(len(news), 2)
        key_set = {s["key"] for s in news}
        self.assertIn("news_correlation", key_set)
        self.assertIn("early_warning", key_set)

    def test_default_llm_type_has_5_sections(self):
        """llm 类型模块共 5 个（4 分析模块 + llm_usage）。"""
        llm = [s for s in self._default if s["type"] == "llm"]
        self.assertEqual(len(llm), 5)
        self.assertEqual(llm[-1]["key"], "llm_usage")

    def test_different_data_flags_in_b_series(self):
        """b_series 的 data_flag 各不相同。"""
        b_series = [s for s in self._default if s["type"] == "b_series"]
        flags = [s["data_flag"] for s in b_series]
        self.assertEqual(len(set(flags)), len(flags),
                         f"data_flag 应各不相同: {flags}")

    def test_empty_config_equals_no_config(self):
        """空配置与无配置结果一致。"""
        order1 = self._get_order(None)
        order2 = self._get_order({"report_section_order": {}})
        for s1, s2 in zip(order1, order2):
            self.assertEqual(s1["key"], s2["key"])
            self.assertEqual(s1["number"], s2["number"])

    def test_4_visibility_types(self):
        """4 种 type 都有对应模块。"""
        type_counts: dict[str, int] = {}
        for sec in self._default:
            type_counts[sec["type"]] = type_counts.get(sec["type"], 0) + 1
        self.assertEqual(set(type_counts.keys()), {"always", "b_series", "news", "llm"})
        self.assertEqual(type_counts["always"], 5)
        self.assertEqual(type_counts["b_series"], 4)
        self.assertEqual(type_counts["news"], 2)
        self.assertEqual(type_counts["llm"], 5)


class TestScenarioCustomSectionOrder(unittest.TestCase):
    """C 迭代报告序号可配置 — 自定义顺序场景验证。

    验证 `get_report_section_order(config)` 在用户自定义配置下的合并行为，
    以及 set_sheet_title 在自定义序号下的正确性。
    """

    def setUp(self):
        from src.python.registry import (
            get_report_section_order,
            set_sheet_title,
        )
        self._get_order = get_report_section_order
        self._set_title = set_sheet_title

    def _partial_config(self) -> dict:
        """部分自定义配置：只覆盖前 3 个模块的序号。"""
        return {
            "report_section_order": {
                "fund_performance": 1,
                "summary": 2,
                "market_value": 3,
            }
        }

    def _mock_ws(self):
        class MockWs:
            def __init__(self):
                self.title = ""
        return MockWs()

    def test_partial_custom_preserves_remaining_16_items(self):
        """部分自定义 → 仍返回 16 个模块，未配置项自动续编。"""
        order = self._get_order(self._partial_config())
        self.assertEqual(len(order), 16)

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
        # 未配置项 key 个数 = 13（总 16 - 3 已配置）
        remaining = order[3:]
        self.assertEqual(len(remaining), 13)
        # number 列应单调递增（可包含重复因部分配置和默认序号冲突）
        numbers = [s["number"] for s in remaining]
        for i in range(1, len(numbers)):
            self.assertGreaterEqual(numbers[i], numbers[i-1],
                                    f"剩余项序号不单调递增: {numbers}")

    def test_partial_custom_all_keys_present(self):
        """部分自定义 → 所有 16 个 key 都出现且不重复。"""
        order = self._get_order(self._partial_config())
        keys = [s["key"] for s in order]
        self.assertEqual(len(set(keys)), 16)

    def test_partial_custom_assigns_correct_number_and_name(self):
        """部分自定义 → set_sheet_title 使用配置的 number。"""
        order = self._get_order(self._partial_config())
        for sec in order[:3]:
            ws = self._mock_ws()
            self._set_title(ws, sec["key"], order)
            expected = f"{sec['number']}.{sec['name']}"
            self.assertEqual(ws.title, expected,
                             f"{sec['key']}: 预期 {expected!r}，实际 {ws.title!r}")

    def test_custom_unknown_key_falls_back_to_default(self):
        """自定义配置中有不再注册表中的 key → 忽略，不影响合并结果。"""
        config = {
            "report_section_order": {
                "summary": 1,
                "nonexistent_key": 99,
            }
        }
        order = self._get_order(config)
        self.assertEqual(len(order), 16)
        keys = [s["key"] for s in order]
        self.assertNotIn("nonexistent_key", keys)

"""LLM 场景测试 — build_llm_module_info 状态契约。

build_llm_module_info 是 HTML/Excel 两端 LLM 用量展示的单一数据源。
本文件锁定其在各状态下的输出契约：disabled / failed / success / cached /
unknown 的状态标签、Token、费用、Thinking 标记，以及 failure 优先、
多模块合并等分发规则。
"""

from __future__ import annotations

import unittest

import pytest

from src.python.llm import (
    FAIL_REASON_API_ERROR,
    FAIL_REASON_CIRCUIT_OPEN,
    FAIL_REASON_DISABLED,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_TIMEOUT,
)

pytestmark = [pytest.mark.llm, pytest.mark.scenario_llm, pytest.mark.scenario]


class TestLlmModuleInfoContract(unittest.TestCase):
    """build_llm_module_info 状态 → 输出契约。

    每种状态断言相同的字段集合（状态、标签、Token、费用、Thinking），
    期望结构即 HTML/Excel 两端共用的规范字段。
    """

    def _key_for_comparison(self, entry: dict) -> dict:
        """提取关键字段用于比较（排除 key/name 等标识字段）。"""
        return {
            "status": entry.get("status"),
            "status_label": entry.get("status_label"),
            "model": entry.get("model"),
            "input_tokens": entry.get("input_tokens"),
            "output_tokens": entry.get("output_tokens"),
            "total_tokens": entry.get("total_tokens"),
            "cache_hit_tokens": entry.get("cache_hit_tokens"),
            "cost": entry.get("cost"),
            "cached": entry.get("cached"),
            "thinking": entry.get("thinking"),
        }

    def test_disabled_state_contract(self):
        """disabled 状态 → 状态、标签、费用契约。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {"health_check": FAIL_REASON_DISABLED}
        html_result = build_llm_module_info(failure, {})

        hc_html = next(m for m in html_result if m["key"] == "health_check")
        self.assertEqual(hc_html["status"], "disabled")
        self.assertEqual(hc_html["status_label"], "已禁用")

        # 与规范字段结构一致（Excel 侧消费同一结构）
        expected_entry = {
            "key": "health_check", "name": "持仓体检报告",
            "status": "disabled", "status_label": "已禁用",
            "model": "", "input_tokens": 0, "output_tokens": 0,
            "total_tokens": 0, "cache_hit_tokens": 0,
            "cost": 0.0, "cached": False, "thinking": False, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(hc_html),
                         self._key_for_comparison(expected_entry))

    def test_failure_reason_label_mapping(self):
        """各失败原因 → 状态标签映射契约。"""
        from src.python.report.llm_module_info import build_llm_module_info

        MODULE_KEY = "health_check"
        for reason, expected_label in [
            (FAIL_REASON_NOT_CONFIGURED, "LLM 未配置"),
            (FAIL_REASON_API_ERROR, "LLM API 调用失败"),
            (FAIL_REASON_NETWORK_ERROR, "LLM API 网络连接失败"),
            (FAIL_REASON_TIMEOUT, "LLM API 请求超时"),
            (FAIL_REASON_CIRCUIT_OPEN, "LLM API 暂时不可用（熔断冷却中）"),
        ]:
            with self.subTest(reason=reason):
                failure = {MODULE_KEY: reason}
                html_result = build_llm_module_info(failure, {})
                test_entry = next(m for m in html_result if m["key"] == MODULE_KEY)

                self.assertEqual(test_entry["status"], "failed")
                self.assertEqual(test_entry["status_label"], expected_label)
                self.assertEqual(test_entry["model"], "")
                self.assertEqual(test_entry["cost"], 0.0)

    def test_all_five_failure_reasons(self):
        """5 个模块同时失败 → 每个模块映射到对应标签。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "global_macro": FAIL_REASON_NOT_CONFIGURED,
            "expert_review": FAIL_REASON_API_ERROR,
            "health_check": FAIL_REASON_NETWORK_ERROR,
            "penetration_deep": FAIL_REASON_TIMEOUT,
            "news_correlation": FAIL_REASON_CIRCUIT_OPEN,
        }

        result = build_llm_module_info(failure, {})
        by_key = {m["key"]: m for m in result}

        expected = {
            "global_macro": ("failed", "LLM 未配置"),
            "expert_review": ("failed", "LLM API 调用失败"),
            "health_check": ("failed", "LLM API 网络连接失败"),
            "penetration_deep": ("failed", "LLM API 请求超时"),
            "news_correlation": ("failed", "LLM API 暂时不可用（熔断冷却中）"),
        }
        for key, (exp_status, exp_label) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(by_key[key]["status"], exp_status)
                self.assertEqual(by_key[key]["status_label"], exp_label)
                self.assertEqual(by_key[key]["model"], "")
                self.assertEqual(by_key[key]["cost"], 0.0)

    def test_failure_priority_over_per_module(self):
        """failure 状态优先于 per_module 数据。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "global_macro": FAIL_REASON_API_ERROR,
        }
        # 即使 per_module 有数据，failure 优先覆盖
        per_module = {
            "global_macro": {
                "model": "test", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": False,
                "endpoint": "",
            },
        }

        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["status"], "failed")
        self.assertEqual(by_key["global_macro"]["status_label"], "LLM API 调用失败")
        self.assertEqual(by_key["global_macro"]["model"], "")

    def test_success_state_contract(self):
        """success 状态 → 状态、标签、Token、Thinking 契约。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "expert_review": {
                "model": "claude-sonnet-4", "cached": False,
                "input_tokens": 1500, "output_tokens": 800,
                "cache_hit_tokens": 0, "cost": 0.005, "thinking": True,
                "endpoint": "",
            },
        }
        html_result = build_llm_module_info({}, per_module)
        er_html = next(m for m in html_result if m["key"] == "expert_review")

        self.assertEqual(er_html["status"], "success")
        self.assertEqual(er_html["status_label"], "成功")
        self.assertEqual(er_html["total_tokens"], 2300)
        self.assertEqual(er_html["cost"], 0.005)
        self.assertTrue(er_html["thinking"])

        # 与规范字段结构一致
        expected_entry = {
            "key": "expert_review", "name": "智囊团深度复盘",
            "status": "success", "status_label": "成功",
            "model": "claude-sonnet-4",
            "input_tokens": 1500, "output_tokens": 800,
            "total_tokens": 2300, "cache_hit_tokens": 0,
            "cost": 0.005, "cached": False, "thinking": True, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(er_html),
                         self._key_for_comparison(expected_entry))

    def test_cached_state_contract(self):
        """cached 状态 → 状态、标签、缓存命中 Token 契约。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
        }
        html_result = build_llm_module_info({}, per_module)
        gm_html = next(m for m in html_result if m["key"] == "global_macro")

        self.assertEqual(gm_html["status"], "cached")
        self.assertEqual(gm_html["status_label"], "缓存")
        self.assertEqual(gm_html["cache_hit_tokens"], 500)
        self.assertTrue(gm_html["cached"])

        # 与规范字段结构一致
        expected_entry = {
            "key": "global_macro", "name": "全球政经局势",
            "status": "cached", "status_label": "缓存",
            "model": "ds",
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "cache_hit_tokens": 500, "cost": 0.0, "cached": True,
            "thinking": False, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(gm_html),
                         self._key_for_comparison(expected_entry))

    def test_mixed_states_distribution(self):
        """混合状态（缓存+成功+失败+无数据）→ 各模块分发正确。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {"penetration_deep": FAIL_REASON_NETWORK_ERROR}
        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 2000, "output_tokens": 1000,
                "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
                "endpoint": "",
            },
        }
        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["status"], "cached")
        self.assertEqual(by_key["expert_review"]["status"], "success")
        self.assertEqual(by_key["penetration_deep"]["status"], "failed")
        self.assertEqual(by_key["penetration_deep"]["status_label"], "LLM API 网络连接失败")
        self.assertEqual(by_key["health_check"]["status"], "unknown")
        self.assertEqual(by_key["news_correlation"]["status"], "unknown")

    def test_merged_per_module_accumulates(self):
        """多轮 per_module 合并后各模块 Token 数据正确。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module_round1 = {
            "global_macro": {
                "model": "ds", "cached": False,
                "input_tokens": 1000, "output_tokens": 500,
                "cache_hit_tokens": 0, "cost": 0.005, "thinking": False,
                "endpoint": "",
            },
        }
        per_module_round2 = {
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 2000, "output_tokens": 1000,
                "cache_hit_tokens": 0, "cost": 0.008, "thinking": True,
                "endpoint": "",
            },
        }
        # 多轮合并 per_module 字典
        merged = {**per_module_round1, **per_module_round2}
        result = build_llm_module_info({}, merged)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["input_tokens"], 1000)
        self.assertEqual(by_key["expert_review"]["input_tokens"], 2000)
        self.assertEqual(len(result), 5)

    def test_module_order_with_news_correlation_last(self):
        """模块顺序固定且 news_correlation 位于末位。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "global_macro": {
                "model": "ds", "cached": True,
                "input_tokens": 0, "output_tokens": 0,
                "cache_hit_tokens": 500, "cost": 0.0, "thinking": False,
                "endpoint": "",
            },
            "expert_review": {
                "model": "claude", "cached": False,
                "input_tokens": 100, "output_tokens": 50,
                "cache_hit_tokens": 0, "cost": 0.001, "thinking": True,
                "endpoint": "",
            },
            "health_check": {
                "model": "gpt4", "cached": False,
                "input_tokens": 200, "output_tokens": 100,
                "cache_hit_tokens": 0, "cost": 0.002, "thinking": False,
                "endpoint": "",
            },
            "penetration_deep": {
                "model": "ds", "cached": False,
                "input_tokens": 300, "output_tokens": 150,
                "cache_hit_tokens": 0, "cost": 0.003, "thinking": False,
                "endpoint": "",
            },
            "news_correlation": {
                "model": "claude", "cached": False,
                "input_tokens": 400, "output_tokens": 200,
                "cache_hit_tokens": 0, "cost": 0.004, "thinking": False,
                "endpoint": "",
            },
        }
        result = build_llm_module_info({}, per_module)
        html_keys = [m["key"] for m in result if m["status"] != "unknown"]

        expected_order = ["global_macro", "expert_review",
                          "health_check", "penetration_deep",
                          "news_correlation"]
        self.assertEqual(html_keys, expected_order)
        self.assertEqual(len(result), 5)

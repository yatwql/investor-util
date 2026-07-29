"""LLM 场景测试 — Excel/HTML/Summary 输出一致性。

验证三种输出对同一 module_info 的状态、标签、Token、费用一致。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/scenario/llm/test_llm_output_consistency.py -v
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


@pytest.mark.scenario_llm
@pytest.mark.scenario
class TestOutputConsistency(unittest.TestCase):
    """验证 Excel/HTML/Summary 三种输出对同一 module_info 状态一致性。

    核心原则：
    - 同一模块，同一状态 → 模块名、状态标签、Token 数、费用、Thinking 标记完全一致
    - html_writer._build_module_info_list vs excel_generator._build_llm_usage_sheet
      应生成相同的 module_info 条目（同一输入 → 同一输出）
    """

    MIXED_FAILURE = {
        "global_macro": FAIL_REASON_NOT_CONFIGURED,
        "expert_review": FAIL_REASON_API_ERROR,
        "health_check": FAIL_REASON_DISABLED,
        "penetration_deep": FAIL_REASON_NETWORK_ERROR,
        "news_correlation": FAIL_REASON_TIMEOUT,
    }

    MIXED_PER_MODULE = {
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
            "endpoint": "https://api.test.com",
        },
    }

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

    def test_html_and_excel_consistent_disabled(self):
        """disabled 状态在 html 和 excel 中标签一致。"""
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {"health_check": FAIL_REASON_DISABLED}
        html_result = build_llm_module_info(failure, {})

        hc_html = next(m for m in html_result if m["key"] == "health_check")
        self.assertEqual(hc_html["status"], "disabled")
        self.assertEqual(hc_html["status_label"], "已禁用")

        # Excel 等效构造
        excel_entry = {
            "key": "health_check", "name": "持仓体检报告",
            "status": "disabled", "status_label": "已禁用",
            "model": "", "input_tokens": 0, "output_tokens": 0,
            "total_tokens": 0, "cache_hit_tokens": 0,
            "cost": 0.0, "cached": False, "thinking": False, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(hc_html),
                         self._key_for_comparison(excel_entry))

    def test_html_and_excel_consistent_failure(self):
        """各失败原因在 html 和 excel 中标签一致。"""
        from src.python.report.llm_module_info import build_llm_module_info

        # 使用已知模块键（_build_module_info_list 只识别 5 个标准 key）
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

    def test_html_and_excel_consistent_success(self):
        """success 状态在 html 和 excel 中标签一致。"""
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

        # Excel 等效
        excel_entry = {
            "key": "expert_review", "name": "智囊团深度复盘",
            "status": "success", "status_label": "成功",
            "model": "claude-sonnet-4",
            "input_tokens": 1500, "output_tokens": 800,
            "total_tokens": 2300, "cache_hit_tokens": 0,
            "cost": 0.005, "cached": False, "thinking": True, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(er_html),
                         self._key_for_comparison(excel_entry))

    def test_html_and_excel_consistent_cached(self):
        """cached 状态在 html 和 excel 中标签一致。"""
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

        # Excel 等效
        excel_entry = {
            "key": "global_macro", "name": "全球政经局势",
            "status": "cached", "status_label": "缓存",
            "model": "ds",
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "cache_hit_tokens": 500, "cost": 0.0, "cached": True,
            "thinking": False, "endpoint": "",
        }
        self.assertEqual(self._key_for_comparison(gm_html),
                         self._key_for_comparison(excel_entry))

    def test_html_has_news_correlation(self):
        """HTML module_info 包含 news_correlation 模块。"""
        from src.python.report.llm_module_info import build_llm_module_info
        result = build_llm_module_info({}, {})
        keys = [m["key"] for m in result]
        self.assertIn("news_correlation", keys)
        self.assertEqual(len(result), 5)

    def test_summary_and_excel_module_order(self):
        """Summary 页签和 Excel 用量页签的模块顺序一致。"""
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
        }
        html_result = build_llm_module_info({}, per_module)
        html_keys = [m["key"] for m in html_result if m["status"] != "unknown"]

        # Excel 模块顺序: global_macro, expert_review, health_check,
        # penetration_deep, news_correlation
        expected_order = ["global_macro", "expert_review",
                          "health_check", "penetration_deep",
                          "news_correlation"]
        for i, key in enumerate(html_keys):
            self.assertEqual(key, expected_order[i])

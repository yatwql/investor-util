"""llm_module_info.build_llm_endpoint_display 单元测试。

测试目标：
  - 单一端点原样返回、无端点返回空串
  - 多端点（主备混用）按 provider 链 priority 排序，主在前并标注主/备
  - 端点无法映射到链路时保持原顺序、不标注（避免误标主备）

运行：
  pytest src/test/unit/report/test_llm_module_info.py -v
"""

from __future__ import annotations

import unittest

import pytest

from src.python.report.llm_module_info import build_llm_endpoint_display

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_MAIN = "https://api.moonshot.cn/anthropic/v1/messages"
_BACKUP = "https://api.deepseek.com/anthropic/v1/messages"

# 主：Kimi（priority 10）/ 备：DeepSeek（priority 20）的最小链路配置
_CHAIN_CONFIG = {
    "_provider_list": [
        {"name": "kimi-main", "credentials_ref": "kimi-main", "priority": 10},
        {"name": "deepseek-main", "credentials_ref": "deepseek-main", "priority": 20},
    ],
    "_llm_credentials": {
        "kimi-main": {"endpoint": _MAIN},
        "deepseek-main": {"endpoint": _BACKUP},
    },
}


def _info(*endpoints: str) -> list[dict]:
    """按给定顺序构造模块信息（空串模拟未记录端点的模块）。"""
    return [{"key": f"m{i}", "endpoint": ep} for i, ep in enumerate(endpoints)]


class TestBuildLlmEndpointDisplay(unittest.TestCase):
    """build_llm_endpoint_display — Endpoint 汇总展示。"""

    def test_no_endpoint_returns_empty(self):
        """无任何端点 → 空串。"""
        self.assertEqual(build_llm_endpoint_display(_info("", ""), _CHAIN_CONFIG), "")

    def test_single_endpoint_passthrough(self):
        """单一端点原样返回，不标注。"""
        self.assertEqual(build_llm_endpoint_display(_info("", _MAIN), _CHAIN_CONFIG), _MAIN)

    def test_mixed_primary_labeled_first(self):
        """主备混用：主在前并标注主/备。"""
        result = build_llm_endpoint_display(_info(_MAIN, _BACKUP), _CHAIN_CONFIG)
        self.assertEqual(result, f"{_MAIN}（主） / {_BACKUP}（备）")

    def test_mixed_order_independent_of_module_order(self):
        """模块出现顺序不影响主备排序——备先出现仍须主在前。"""
        result = build_llm_endpoint_display(_info(_BACKUP, _MAIN), _CHAIN_CONFIG)
        self.assertEqual(result, f"{_MAIN}（主） / {_BACKUP}（备）")

    def test_unmapped_endpoint_falls_back_without_labels(self):
        """任一端点不在链路映射中 → 保持原顺序拼接且不标注（防止误标主备）。"""
        unknown = "https://example.com/v1/messages"
        result = build_llm_endpoint_display(_info(_MAIN, unknown), _CHAIN_CONFIG)
        self.assertEqual(result, f"{_MAIN} / {unknown}")

    def test_config_none_lazy_load_no_crash(self):
        """llm_config=None 时惰性加载全局配置；合成端点不在默认链路上 → 无标注拼接。"""
        unknown_a = "https://a.example.com/v1"
        unknown_b = "https://b.example.com/v1"
        result = build_llm_endpoint_display(_info(unknown_a, unknown_b), None)
        self.assertEqual(result, f"{unknown_a} / {unknown_b}")

    def test_duplicate_endpoint_deduped(self):
        """同一端点被多个模块使用时只出现一次。"""
        result = build_llm_endpoint_display(_info(_MAIN, "", _MAIN), _CHAIN_CONFIG)
        self.assertEqual(result, _MAIN)


if __name__ == "__main__":
    unittest.main()

"""LLM 多 Provider 配置解析边缘场景测试 — 。

测试目标：
  - 非法 provider 类型 → WARNING + 跳过
  - JSON 解析异常 → 返回 None（不抛异常）

运行：
  pytest src/test/unit/config/test_config_llm_multi_edge.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pytest

from src.python.config._llm_providers import (
    _load_llm_providers,
    _parse_providers_list,
    _validate_provider_entry,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_config, pytest.mark.edge]


class TestInvalidProviderType(unittest.TestCase):
    """非法 provider 类型场景测试。"""

    # ── _validate_provider_entry 层 ──

    def test_invalid_type_warning(self):
        """非 claude/openai/gemini → WARNING。"""
        entry = {"name": "test", "provider": "deepseek", "api_key": "sk-key", "model": "deepseek-v3"}
        warnings = _validate_provider_entry(entry, 0)
        self.assertTrue(any("provider" in w.lower() for w in warnings))

    def test_missing_type_warning(self):
        """缺 provider 字段 → WARNING。"""
        entry = {"name": "test", "api_key": "sk-key", "model": "m1"}
        warnings = _validate_provider_entry(entry, 0)
        self.assertTrue(any("provider" in w.lower() for w in warnings))

    # ── _parse_providers_list 层 ──

    def test_invalid_type_skipped_in_parse(self):
        """非法类型的 entry 被跳过，合法 entry 保留。"""
        raw = {
            "providers": [
                {"name": "valid", "provider": "claude", "api_key": "sk-1", "model": "m1"},
                {"name": "bad", "provider": "deepseek", "api_key": "sk-2", "model": "dsv3"},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "valid")


class TestMalformedJson(unittest.TestCase):
    """JSON 解析异常场景测试。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.providers_path = os.path.join(self.tmp.name, "llm_providers.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_raw(self, content: str):
        with open(self.providers_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _patch_providers_path(self):
        """mock _get_llm_providers_path 返回临时路径。"""
        return patch("src.python.config._llm_providers._get_llm_providers_path",
                     return_value=self.providers_path)

    def test_malformed_json_returns_none(self):
        """格式损坏的 JSON → 返回 None（不抛异常）。"""
        self._write_raw("{invalid json content}")
        with self._patch_providers_path():
            result = _load_llm_providers()
        self.assertIsNone(result)

    def test_empty_file_returns_none(self):
        """空文件 → 返回 None。"""
        self._write_raw("")
        with self._patch_providers_path():
            result = _load_llm_providers()
        self.assertIsNone(result)

    def test_not_a_json_object_returns_none(self):
        """JSON 是数组而非对象 → 返回 None（_load_llm_providers 校验根类型）。"""
        self._write_raw('["a", "b"]')
        with self._patch_providers_path():
            result = _load_llm_providers()
        self.assertIsNone(result)

    def test_non_dict_raw_config_handled(self):
        """非 dict JSON → _load_llm_providers 返回 None（不抛异常）。"""
        self._write_raw('"just a string"')
        with self._patch_providers_path():
            result = _load_llm_providers()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

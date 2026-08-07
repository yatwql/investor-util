"""LLM 多 Provider 配置解析单元测试 — 。

测试目标：
  - _load_llm_providers()：读取 llm_providers.json，返回 dict 或 None
  - _parse_providers_list()：校验并补齐 provider 数组
  - _validate_provider_entry()：单条 provider 字段校验

运行：
  pytest src/test/unit/config/test_config_llm_multi.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pytest

from src.python.config._llm_providers import (
    _inject_provider_chain_data,
    _load_llm_providers,
    _parse_providers_list,
    _validate_provider_entry,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]


class TestLoadLlmProviders(unittest.TestCase):
    """_load_llm_providers() — 文件读取层测试。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.providers_path = os.path.join(self.tmp.name, "llm_providers.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_json(self, data: dict):
        with open(self.providers_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 标准格式 ──

    def test_standard_format(self):
        """标准格式解析成功。"""
        self._write_json({
            "strategy": "priority",
            "preferred_providers": {"news": "claude-opus"},
            "providers": [
                {
                    "name": "claude-opus",
                    "provider": "claude",
                    "api_key": "sk-test",
                    "model": "claude-sonnet-4-20250514",
                }
            ],
        })
        with patch("src.python.config._llm_providers._get_llm_providers_path", return_value=self.providers_path):
            result = _load_llm_providers()
        self.assertIsNotNone(result)
        self.assertEqual(result["strategy"], "priority")
        self.assertEqual(len(result["providers"]), 1)
        self.assertEqual(result["providers"][0]["name"], "claude-opus")

    # ── 文件不存在 ──

    def test_file_not_found(self):
        """文件不存在返回 None（不抛异常）。"""
        missing = os.path.join(self.tmp.name, "nonexistent.json")
        with patch("src.python.config._llm_providers._get_llm_providers_path", return_value=missing):
            result = _load_llm_providers()
        self.assertIsNone(result)


class TestParseProvidersList(unittest.TestCase):
    """_parse_providers_list() 批量解析测试。"""

    # ── 单条 / 多条 ──

    def test_single_provider(self):
        """单条 provider 正确解析。"""
        raw = {
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "p1")

    def test_multiple_providers(self):
        """多条 provider 正确解析并保持顺序。"""
        raw = {
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-2", "model": "m2"},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "p1")
        self.assertEqual(result[1]["name"], "p2")

    # ── 空/缺 providers ──

    def test_empty_providers_array(self):
        """空 providers 数组返回 None。"""
        raw = {"providers": []}
        result = _parse_providers_list(raw)
        self.assertIsNone(result)

    def test_missing_providers_field(self):
        """缺 providers 字段返回 None。"""
        raw = {"strategy": "priority"}
        result = _parse_providers_list(raw)
        self.assertIsNone(result)

    # ── 缺失必填字段 ──

    def test_missing_required_field_skipped(self):
        """缺必填字段的 entry 被跳过，其余正常保留。"""
        raw = {
            "providers": [
                {"name": "valid", "provider": "claude", "api_key": "sk-1", "model": "m1"},
                {"name": "bad", "provider": "claude"},  # 缺 api_key 和 model
                {"name": "also-valid", "provider": "openai", "api_key": "sk-2", "model": "m2"},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "valid")
        self.assertEqual(result[1]["name"], "also-valid")

    def test_all_invalid_returns_none(self):
        """全部 entry 校验不通过返回 None。"""
        raw = {
            "providers": [
                {"name": "", "provider": "unknown", "api_key": "", "model": ""},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNone(result)

    # ── 同名 ──

    def test_duplicate_name(self):
        """同名 provider → 后者覆盖前者（二者均保留但后者在前者之后）。"""
        raw = {
            "providers": [
                {"name": "dup", "provider": "claude", "api_key": "sk-1", "model": "m1"},
                {"name": "dup", "provider": "openai", "api_key": "sk-2", "model": "m2"},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        names = [p["name"] for p in result]
        self.assertEqual(names, ["dup", "dup"])

    # ── 默认值补齐 ──

    def test_defaults_applied(self):
        """缺省字段用默认值补齐（priority=99, weight=1, timeout=60.0, endpoint=None, proxy_preferred=False）。"""
        raw = {
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        entry = result[0]
        self.assertEqual(entry["priority"], 99)
        self.assertEqual(entry["weight"], 1)
        self.assertEqual(entry["timeout"], 60.0)
        self.assertIsNone(entry["endpoint"])
        self.assertFalse(entry["proxy_preferred"])

    def test_custom_defaults_respected(self):
        """明确指定的值不被默认值覆盖。"""
        raw = {
            "providers": [
                {
                    "name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1",
                    "priority": 5, "weight": 3, "timeout": 120.0,
                    "endpoint": "https://custom.endpoint", "proxy_preferred": True,
                },
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        entry = result[0]
        self.assertEqual(entry["priority"], 5)
        self.assertEqual(entry["weight"], 3)
        self.assertEqual(entry["timeout"], 120.0)
        self.assertEqual(entry["endpoint"], "https://custom.endpoint")
        self.assertTrue(entry["proxy_preferred"])

    # ── api_key 清理 ──

    def test_api_key_stripped(self):
        """api_key 两端空格被去除，内联字段保留在 entry 中（运行时直接读取）。"""
        raw = {
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "  sk-test-key  ", "model": "m1"},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result[0]["api_key"], "sk-test-key")
        self.assertEqual(result[0]["model"], "m1")
        self.assertNotIn("credentials_ref", result[0])

    # ── 非 dict entry ──

    def test_non_dict_entry_skipped(self):
        """非 dict 的 providers 元素被跳过。"""
        raw = {
            "providers": [
                {"name": "valid", "provider": "claude", "api_key": "sk-1", "model": "m1"},
                "not_a_dict",
                {"name": "also-valid", "provider": "openai", "api_key": "sk-2", "model": "m2"},
            ]
        }
        result = _parse_providers_list(raw)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)


class TestValidateProviderEntry(unittest.TestCase):
    """_validate_provider_entry() 单条字段校验测试。"""

    def test_valid_entry_empty_warnings(self):
        """合法 entry 返回空列表。"""
        entry = {
            "name": "test-provider",
            "provider": "claude",
            "api_key": "sk-test-key",
            "model": "claude-sonnet-4-20250514",
        }
        warnings = _validate_provider_entry(entry)
        self.assertEqual(warnings, [])

    def test_valid_with_optional_fields(self):
        """含 endpoint 的合法 entry 返回空列表。"""
        entry = {
            "name": "test-provider",
            "provider": "openai",
            "api_key": "sk-test-key",
            "model": "gpt-4",
            "endpoint": "https://api.openai.com/v1",
        }
        warnings = _validate_provider_entry(entry)
        self.assertEqual(warnings, [])

    def test_missing_name_errors(self):
        """缺 name → WARNING。"""
        entry = {"provider": "claude", "api_key": "sk-key", "model": "m1"}
        warnings = _validate_provider_entry(entry)
        self.assertTrue(any("name" in w for w in warnings))

    def test_empty_name_errors(self):
        """空 name → WARNING。"""
        entry = {"name": "", "provider": "claude", "api_key": "sk-key", "model": "m1"}
        warnings = _validate_provider_entry(entry)
        self.assertTrue(any("name" in w for w in warnings))

    def test_missing_api_key_errors(self):
        """缺 api_key → WARNING。"""
        entry = {"name": "test", "provider": "claude", "model": "m1"}
        warnings = _validate_provider_entry(entry)
        self.assertTrue(any("api_key" in w for w in warnings))

    def test_missing_model_errors(self):
        """缺 model → WARNING。"""
        entry = {"name": "test", "provider": "claude", "api_key": "sk-key"}
        warnings = _validate_provider_entry(entry)
        self.assertTrue(any("model" in w for w in warnings))

    def test_null_endpoint_allowed(self):
        """endpoint 为 None 不警告。"""
        entry = {
            "name": "test", "provider": "claude", "api_key": "sk-key",
            "model": "m1", "endpoint": None,
        }
        warnings = _validate_provider_entry(entry)
        self.assertEqual(warnings, [])


# ── _inject_provider_chain_data 测试 ─────────────────────


class TestInjectProviderChainData(unittest.TestCase):
    """_inject_provider_chain_data() — get_llm_config() 注入逻辑测试。"""

    def setUp(self):
        self.base_config = {
            "provider": "claude",
            "api_key": "sk-test",
            "model": "claude-sonnet-4-20250514",
        }

    # ── _provider_list ──

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_has_provider_list(self, mock_load):
        """_inject_provider_chain_data → merged dict 含 _provider_list。"""
        mock_load.return_value = {
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        result = _inject_provider_chain_data(dict(self.base_config))
        self.assertIn("_provider_list", result)
        self.assertIsNotNone(result["_provider_list"])
        self.assertEqual(len(result["_provider_list"]), 1)
        self.assertEqual(result["_provider_list"][0]["name"], "p1")

    # ── strategy ──

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_strategy_default_priority(self, mock_load):
        """未指定 strategy → 默认 "priority"。"""
        mock_load.return_value = {
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        result = _inject_provider_chain_data(dict(self.base_config))
        self.assertEqual(result["_strategy"], "priority")

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_strategy_explicit_priority(self, mock_load):
        """指定 strategy="weighted" → 保留用户设置。"""
        mock_load.return_value = {
            "strategy": "weighted",
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        result = _inject_provider_chain_data(dict(self.base_config))
        self.assertEqual(result["_strategy"], "weighted")

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_strategy_invalid_fallback(self, mock_load):
        """非法策略值回退 priority + WARNING。"""
        mock_load.return_value = {
            "strategy": "random",
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        with self.assertLogs("invest", level="WARNING") as logs:
            result = _inject_provider_chain_data(dict(self.base_config))
        self.assertEqual(result["_strategy"], "priority")
        self.assertTrue(any("random" in msg for msg in logs.output))

    # ── preferred_providers ──

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_preferred_default_empty(self, mock_load):
        """未指定 preferred_providers → 默认 {}。"""
        mock_load.return_value = {
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        result = _inject_provider_chain_data(dict(self.base_config))
        self.assertEqual(result["_preferred_providers"], {})

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_preferred_valid_name(self, mock_load):
        """preferred_providers 中 name 存在 → 保留。"""
        mock_load.return_value = {
            "preferred_providers": {"news": "p1"},
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        result = _inject_provider_chain_data(dict(self.base_config))
        self.assertEqual(result["_preferred_providers"], {"news": "p1"})

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_preferred_invalid_name(self, mock_load):
        """不存在的偏好 name → WARNING + 忽略。"""
        mock_load.return_value = {
            "preferred_providers": {"news": "nonexistent"},
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        with self.assertLogs("invest", level="WARNING") as logs:
            result = _inject_provider_chain_data(dict(self.base_config))
        self.assertEqual(result["_preferred_providers"], {})
        self.assertTrue(any("nonexistent" in msg for msg in logs.output))

    # ── 原有字段保留 ──

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_first_provider_reference(self, mock_load):
        """原有 provider/api_key/model/endpoint 字段在注入后保留。"""
        mock_load.return_value = {
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        original = {
            "provider": "original_provider",
            "api_key": "original_key",
            "model": "original_model",
            "endpoint": "https://original.endpoint",
        }
        result = _inject_provider_chain_data(original)
        self.assertEqual(result["provider"], "original_provider")
        self.assertEqual(result["api_key"], "original_key")
        self.assertEqual(result["model"], "original_model")
        self.assertEqual(result["endpoint"], "https://original.endpoint")

    # ── 无 llm_providers.json ──

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_no_providers_file(self, mock_load):
        """llm_providers.json 不存在 → _provider_list=None, _strategy=priority, _preferred={}。"""
        mock_load.return_value = None
        result = _inject_provider_chain_data(dict(self.base_config))
        self.assertIsNone(result["_provider_list"])
        self.assertEqual(result["_strategy"], "priority")
        self.assertEqual(result["_preferred_providers"], {})

    # ── preferred_providers 非 dict ──

    @patch("src.python.config._llm_providers._load_llm_providers")
    def test_preferred_not_dict(self, mock_load):
        """preferred_providers 不是 dict → WARNING + 空 dict。"""
        mock_load.return_value = {
            "preferred_providers": "not_a_dict",
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1", "model": "m1"},
            ]
        }
        with self.assertLogs("invest", level="WARNING") as logs:
            result = _inject_provider_chain_data(dict(self.base_config))
        self.assertEqual(result["_preferred_providers"], {})
        self.assertTrue(any("not a dict" in msg.lower() or "dict" in msg.lower() for msg in logs.output))


if __name__ == "__main__":
    unittest.main()

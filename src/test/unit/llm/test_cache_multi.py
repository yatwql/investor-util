"""LLM Multi-Provider — 缓存适配（R11）。

测试 provider-aware cache key 构建、乐观预检、按实际 provider 落盘。

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/llm/test_cache_multi.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


class TestBuildProviderCacheKey(unittest.TestCase):
    """_build_provider_cache_key 单元测试。"""

    def test_legacy_mode_unchanged(self) -> None:
        """无 _provider_list → 返回原 key。"""
        from src.python.llm.skeleton import _build_provider_cache_key

        key = _build_provider_cache_key(
            "llm_global_macro_fp123", {"provider": "claude"}, "global_macro",
        )
        self.assertEqual(key, "llm_global_macro_fp123")

    def test_chain_mode_appends_provider(self) -> None:
        """有 _provider_list + resolved_first_name → key 含 provider name。"""
        from src.python.llm.skeleton import _build_provider_cache_key

        key = _build_provider_cache_key(
            "llm_global_macro_fp123",
            {"_provider_list": [{"name": "p1"}, {"name": "p2"}]},
            "global_macro",
            resolved_first_name="p1",
        )
        self.assertEqual(key, "llm_global_macro_fp123_p1")

    def test_diff_providers_diff_keys(self) -> None:
        """不同 provider → 不同 cache key。"""
        from src.python.llm.skeleton import _build_provider_cache_key

        base_config = {"_provider_list": [{"name": "p1"}, {"name": "p2"}]}
        key1 = _build_provider_cache_key("llm_m_fp", base_config, "m", resolved_first_name="p1")
        key2 = _build_provider_cache_key("llm_m_fp", base_config, "m", resolved_first_name="p2")
        self.assertNotEqual(key1, key2)

    def test_same_provider_same_key(self) -> None:
        """相同 provider + 相同 fingerprint → 相同 key。"""
        from src.python.llm.skeleton import _build_provider_cache_key

        base_config = {"_provider_list": [{"name": "p1"}]}
        key1 = _build_provider_cache_key("llm_m_fp", base_config, "m", resolved_first_name="p1")
        key2 = _build_provider_cache_key("llm_m_fp", base_config, "m", resolved_first_name="p1")
        self.assertEqual(key1, key2)


class TestCachePrecheckAndWrite(unittest.TestCase):
    """乐观预检 + 按实际 provider 落盘。"""

    @patch("src.python.llm.skeleton.cache_get")
    @patch("src.python.llm.skeleton.call_llm")
    @patch("src.python.llm.skeleton.clear_last_llm_failure")
    def test_optimistic_precheck_hit(
        self, mock_clear: MagicMock, mock_call: MagicMock, mock_cache_get: MagicMock,
    ) -> None:
        """乐观预检命中 → 不调用 call_llm。"""
        from src.python.llm.skeleton import generate_llm_content

        mock_cache_get.return_value = "cached content"

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1"},
            ],
        }
        result, from_cache = generate_llm_content(
            llm_config=config,
            cache_key="llm_test_fp",
            cache_ttl=3600,
            system_prompt="sys",
            user_prompt="user",
            cache_enabled=True,
            force=False,
            max_tokens=100,
            timeout=30,
            temperature=None,
            model=None,
            config_field="max_tokens_test",
            http_client=None,
            module_key="test",
        )
        self.assertTrue(from_cache)
        mock_call.assert_not_called()
        # 验证预检 key 含 provider name
        precheck_key = mock_cache_get.call_args[0][0]
        self.assertIn("p1", precheck_key)

    @patch("src.python.llm.skeleton.cache_get")
    @patch("src.python.llm.skeleton.cache_set")
    @patch("src.python.llm.skeleton.call_llm")
    @patch("src.python.llm.skeleton.clear_last_llm_failure")
    def test_cache_write_with_provider(
        self, mock_clear: MagicMock, mock_call: MagicMock,
        mock_cache_set: MagicMock, mock_cache_get: MagicMock,
    ) -> None:
        """call_llm 成功后按实际 provider_name 落盘。"""
        from src.python.llm.skeleton import generate_llm_content

        mock_cache_get.return_value = None  # 未命中
        mock_call.return_value = ("生成的内容", {"input_tokens": 10}, "p2")

        config = {
            "_provider_list": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1"},
                {"name": "p2", "provider": "openai", "api_key": "sk-2"},
            ],
        }
        result, from_cache = generate_llm_content(
            llm_config=config,
            cache_key="llm_test_fp",
            cache_ttl=3600,
            system_prompt="sys",
            user_prompt="user",
            cache_enabled=True,
            force=False,
            max_tokens=100,
            timeout=30,
            temperature=None,
            model=None,
            config_field="max_tokens_test",
            http_client=None,
            module_key="test",
        )
        self.assertFalse(from_cache)
        mock_call.assert_called_once()
        # 验证落盘 key 含实际 provider
        write_key = mock_cache_set.call_args[0][0]
        self.assertIn("p2", write_key)
        self.assertNotIn("p1", write_key)  # 不是乐观预检的 p1

    @patch("src.python.llm.skeleton.cache_get")
    @patch("src.python.llm.skeleton.cache_set")
    @patch("src.python.llm.skeleton.call_llm")
    @patch("src.python.llm.skeleton.clear_last_llm_failure")
    def test_legacy_cache_key_unchanged(
        self, mock_clear: MagicMock, mock_call: MagicMock,
        mock_cache_set: MagicMock, mock_cache_get: MagicMock,
    ) -> None:
        """无 _provider_list → cache key 不变。"""
        from src.python.llm.skeleton import generate_llm_content

        mock_cache_get.return_value = None
        mock_call.return_value = ("内容", {"prompt_tokens": 5}, None)

        config = {"provider": "claude", "api_key": "sk-1"}
        result, from_cache = generate_llm_content(
            llm_config=config,
            cache_key="llm_test_fp",
            cache_ttl=3600,
            system_prompt="sys",
            user_prompt="user",
            cache_enabled=True,
            force=False,
            max_tokens=100,
            timeout=30,
            temperature=None,
            model=None,
            config_field="max_tokens_test",
            http_client=None,
            module_key="test",
        )
        # 读 key = 原 cache_key
        get_key = mock_cache_get.call_args[0][0]
        self.assertEqual(get_key, "llm_test_fp")
        # 写 key = 原 cache_key
        write_key = mock_cache_set.call_args[0][0]
        self.assertEqual(write_key, "llm_test_fp")


if __name__ == "__main__":
    unittest.main()

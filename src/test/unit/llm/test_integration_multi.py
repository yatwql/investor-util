"""LLM Multi-Provider — 集成验证 + 清理验证。

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/llm/test_integration_multi.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


class TestIntegrationChainAllStrategies(unittest.TestCase):
    """所有 4 种策略走一遍端到端 chain（全 mock）。"""

    STRATEGIES = ["priority", "weighted", "cost_first", "fallback_only"]

    @patch("src.python.llm.api.call_single_provider")
    def test_all_strategies_end_to_end(self, mock_call: MagicMock) -> None:
        """每种策略都走完 resolve → call → 返回 provider_name。"""
        from src.python.llm.api import call_llm

        for strategy in self.STRATEGIES:
            with self.subTest(strategy=strategy):
                mock_call.reset_mock()
                mock_call.return_value = ("result", {"input_tokens": 10})

                config = {
                    "_provider_list": [
                        {"name": "p1", "provider": "claude", "api_key": "sk-1", "priority": 1},
                        {"name": "p2", "provider": "openai", "api_key": "sk-2", "priority": 2},
                    ],
                    "_strategy": strategy,
                }
                result, usage, provider_name = call_llm(
                    "sys", "user", config, config_field="max_tokens_test",
                )
                self.assertEqual(result, "result")
                self.assertIsNotNone(provider_name)
                mock_call.assert_called_once()


class TestConfigNoLlmKeyFile(unittest.TestCase):
    """验证 get_llm_config() 无 llm_key.json 但 llm_providers.json 有 provider 时正常。"""

    @patch("src.python.config._llm_providers._get_llm_key_path")
    @patch("src.python.config._llm_providers._load_llm_providers")
    @patch("src.python.config._core.os.path.exists")
    @patch("src.python.config._llm_settings.get_llm_settings_path")
    def test_llm_providers_as_key_source(
        self, mock_settings_path: MagicMock,
        mock_exists: MagicMock, mock_load: MagicMock,
        mock_get_key_path: MagicMock,
    ) -> None:
        """llm_key.json 不存在 + llm_settings.json 无 api_key + llm_providers.json 有 provider → 成功。"""
        import src.python.config._llm_providers as llm_providers
        import src.python.config._llm_settings as core

        # settings 无 api_key
        mock_settings_path.return_value = "/tmp/nonexistent/settings.json"
        # llm_key.json 不存在 — 让 _get_llm_key_path 和 os.path.exists 都认同一个 fake path
        fake_key_path = "/tmp/nonexistent/llm_key.json"
        mock_get_key_path.return_value = fake_key_path

        def _exists_side_effect(p: str) -> bool:
            if p == fake_key_path:
                return False
            return True  # 其他路径都存
        mock_exists.side_effect = _exists_side_effect

        # llm_providers.json 有 provider
        mock_load.return_value = {
            "strategy": "priority",
            "providers": [
                {"name": "p1", "provider": "claude", "api_key": "sk-1"},
            ],
        }

        core._llm_config_cache = None
        result = core.get_llm_config()
        self.assertIsNotNone(result)
        self.assertIn("_provider_list", result)
        core._llm_config_cache = None

    @patch("src.python.config._core.os.path.exists")
    def test_llm_key_path_not_exported(self, mock_exists: MagicMock) -> None:
        """验证 get_llm_key_path 未从 config 模块导出。"""
        import src.python.config as cfg
        self.assertFalse(hasattr(cfg, "get_llm_key_path"),
                         "get_llm_key_path 应从 config 模块移除")


class TestConfigSanityAfterCleanup(unittest.TestCase):
    """清理后 get_config() 不含 llm_key_file 键。"""

    def test_config_has_path_keys(self) -> None:
        """get_config() 含 llm_key_file 和 llm_providers_file 路径键。"""
        from src.python.config import get_config
        config = get_config()
        self.assertIn("llm_key_file", config,
                      "配置中应含 llm_key_file 路径键")
        self.assertIn("llm_providers_file", config,
                      "配置中应含 llm_providers_file 路径键")

    def test_template_has_path_keys(self) -> None:
        """配置模板含 llm_key_file 和 llm_providers_file 路径键。"""
        from src.python.config import _get_default_config_template
        template = _get_default_config_template()
        self.assertIn("llm_key_file", template,
                      "配置模板中应含 llm_key_file")
        self.assertIn("llm_providers_file", template,
                      "配置模板中应含 llm_providers_file")


if __name__ == "__main__":
    unittest.main()

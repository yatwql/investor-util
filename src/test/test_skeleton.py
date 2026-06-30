"""测试 skeleton.py 辅助函数（纯逻辑函数，无 API 调用）。"""

import unittest

from src.python.llm.skeleton import _is_llm_module_enabled


class TestIsLlmModuleEnabled(unittest.TestCase):
    """_is_llm_module_enabled — 检查 LLM 模块启用状态。"""

    def test_none_config_disabled(self):
        self.assertFalse(_is_llm_module_enabled(None, "global_macro"))

    def test_empty_enabled_map_default_true(self):
        config = {"enabled_llm": {}}
        self.assertTrue(_is_llm_module_enabled(config, "global_macro"))

    def test_missing_enabled_llm_default_true(self):
        config = {"api_key": "sk-xxx"}
        self.assertTrue(_is_llm_module_enabled(config, "global_macro"))

    def test_explicitly_enabled(self):
        config = {"enabled_llm": {"global_macro": True}}
        self.assertTrue(_is_llm_module_enabled(config, "global_macro"))

    def test_explicitly_disabled(self):
        config = {"enabled_llm": {"global_macro": False}}
        self.assertFalse(_is_llm_module_enabled(config, "global_macro"))

    def test_different_module_not_affected(self):
        config = {"enabled_llm": {"health_check": False}}
        self.assertTrue(_is_llm_module_enabled(config, "global_macro"))
        self.assertFalse(_is_llm_module_enabled(config, "health_check"))

    def test_unknown_module_defaults_true(self):
        config = {"enabled_llm": {"global_macro": True}}
        self.assertTrue(_is_llm_module_enabled(config, "unknown_module"))

    def test_enabled_map_none(self):
        config = {"enabled_llm": None}
        self.assertTrue(_is_llm_module_enabled(config, "global_macro"))


class TestHandleCacheHit(unittest.TestCase):
    """_handle_cache_hit — 缓存命中处理（通过 _generate_llm_content 间接测试）。

    注：此为集成验证的基础——_handle_cache_hit 内部依赖 _record_per_module /
    _strip_token_line / _extract_model_from_cached，这些在 test_llm.py 中有覆盖。
    """

    def test_module_imports_successfully(self):
        """验证 skeleton.py 模块导入正常，无语法/导入错误。"""
        from src.python.llm import skeleton
        self.assertTrue(hasattr(skeleton, "_handle_cache_hit"))
        self.assertTrue(hasattr(skeleton, "_finalize_and_cache"))
        self.assertTrue(hasattr(skeleton, "_handle_truncation"))


if __name__ == "__main__":
    unittest.main()

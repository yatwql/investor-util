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


class TestHandleTruncation(unittest.TestCase):
    """_handle_truncation — 截断检测与 usage 传递。

    核心契约：非截断场景必须透传调用链的 usage dict，
    否则 _finalize_and_cache 无法记录 per_module 用量和页脚 Token 信息。
    """

    def test_not_truncated_preserves_usage(self):
        """结果不含截断标记 → 原样返回 (result, usage)。"""
        from src.python.llm.skeleton import _handle_truncation
        result = "正常内容"
        usage = {"input_tokens": 100, "output_tokens": 200}
        r, u = _handle_truncation(result, usage, 4096, "", "", {}, 60, None, "", None, "")
        self.assertEqual(r, result)
        self.assertIs(u, usage)  # 同一对象，非 None

    def test_none_result_preserves_usage(self):
        """result 为 None 时同样保留 usage（不走截断路径）。"""
        from src.python.llm.skeleton import _handle_truncation
        usage = {"input_tokens": 50, "output_tokens": 80}
        r, u = _handle_truncation(None, usage, 4096, "", "", {}, 60, None, "", None, "")
        self.assertIsNone(r)
        self.assertIs(u, usage)

    def test_empty_result_preserves_usage(self):
        """空白字符串不走截断路径，保留 usage。"""
        from src.python.llm.skeleton import _handle_truncation
        usage = {"input_tokens": 10, "output_tokens": 20}
        r, u = _handle_truncation("", usage, 4096, "", "", {}, 60, None, "", None, "")
        self.assertEqual(r, "")
        self.assertIs(u, usage)


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

"""LLM 生成编排模块单元测试。

测试 _apply_llm_news_correlation 纯函数、各生成器入口的缓存预检逻辑。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/llm/test_generators.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


@pytest.mark.unit_llm
class TestApplyLlmNewsCorrelation(unittest.TestCase):
    """_apply_llm_news_correlation LLM JSON 响应解析。"""

    def _call(self, news_batch: list | None = None, llm_response: str = ""):
        from src.python.llm.generators_news import _apply_llm_news_correlation
        batch = news_batch if news_batch is not None else [
            {"title": "新闻A"}, {"title": "新闻B"},
        ]
        return _apply_llm_news_correlation(batch, llm_response)

    def test_empty_batch(self):
        """空 batch → 空列表。"""
        result = self._call(news_batch=[])
        self.assertEqual(result, [])

    def test_valid_json(self):
        """标准 JSON 数组返回正确结果。"""
        response = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "利好1"},'
            ' {"idx": 1, "relevance": "低", "sentiment": "中性", "analysis": "中性1"}]'
        )
        result = self._call(llm_response=response)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("高", "利好", "利好1"))
        self.assertEqual(result[1], ("低", "中性", "中性1"))

    def test_json_in_markdown_block(self):
        """JSON 在 Markdown 代码块内仍能解析。"""
        response = (
            '```json\n'
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "test"}]\n'
            '```'
        )
        result = self._call(news_batch=[{"title": "单条新闻"}], llm_response=response)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "高")

    def test_malformed_json_returns_defaults(self):
        """乱码 JSON → 所有条目返回默认值。"""
        response = "这不是 JSON {{{{"
        result = self._call(llm_response=response)
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r, ("低", "中性", ""))

    def test_non_array_response(self):
        """非数组 JSON → 所有条目返回默认值。"""
        response = '{"not": "array"}'
        result = self._call(llm_response=response)
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r, ("低", "中性", ""))

    def test_missing_fields_use_defaults(self):
        """缺失可选字段使用默认值。"""
        response = '[{"idx": 0}]'
        result = self._call(news_batch=[{"title": "A"}], llm_response=response)
        self.assertEqual(result[0], ("低", "中性", ""))

    def test_fewer_results_than_batch(self):
        """LLM 返回少于 batch 数量 → 缺失项用默认值填充。"""
        response = '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "a"}]'
        result = self._call(llm_response=response)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("高", "利好", "a"))
        self.assertEqual(result[1], ("低", "中性", ""))

    def test_idx_out_of_range(self):
        """idx 超出范围 → 跳过并用默认值填充。"""
        response = '[{"idx": 99, "relevance": "高", "sentiment": "利好", "analysis": "a"}]'
        result = self._call(llm_response=response)
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r, ("低", "中性", ""))

    def test_idx_not_int(self):
        """idx 非整数 → 跳过。"""
        response = '[{"idx": "0", "relevance": "高", "sentiment": "利好", "analysis": "a"}]'
        result = self._call(news_batch=[{"title": "A"}], llm_response=response)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ("低", "中性", ""))

    def test_json_with_extra_whitespace(self):
        """额外空白不影响解析。"""
        response = '  [  {  "idx": 0,  "relevance": "高"  }  ]  '
        result = self._call(news_batch=[{"title": "A"}], llm_response=response)
        self.assertEqual(len(result), 1)

    def test_all_news_high_correlation(self):
        """所有新闻高关联。"""
        response = '[' + ','.join(
            f'{{"idx": {i}, "relevance": "高", "sentiment": "利好", "analysis": "a{i}"}}'
            for i in range(5)
        ) + ']'
        batch = [{"title": f"N{i}"} for i in range(5)]
        result = self._call(news_batch=batch, llm_response=response)
        self.assertEqual(len(result), 5)
        for r in result:
            self.assertEqual(r[0], "高")

    def test_mixed_relevance(self):
        """混合关联度。"""
        response = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "a"},'
            ' {"idx": 1, "relevance": "无关", "sentiment": "中性", "analysis": "b"}]'
        )
        result = self._call(llm_response=response)
        self.assertEqual(result[0][0], "高")
        self.assertEqual(result[1][0], "无关")


@pytest.mark.unit_llm
class TestPrecheckOneCache(unittest.TestCase):
    """_precheck_one_cache 缓存预检。"""

    def test_cache_disabled(self):
        """can_cache=False → 返回 (None, False)。"""
        from src.python.llm.generators_orchestrator import _precheck_one_cache
        result, cached = _precheck_one_cache(
            {"can_cache": False, "key": "test", "ttl": 3600,
             "thinking_key": "thinking_enabled_test"},
            {}, "test_module",
        )
        self.assertIsNone(result)
        self.assertFalse(cached)

    @patch("src.python.llm.generators_orchestrator.cache_get", return_value=None)
    def test_cache_miss(self, mock_get):
        """缓存未命中 → 返回 (None, False)。"""
        from src.python.llm.generators_orchestrator import _precheck_one_cache
        result, cached = _precheck_one_cache(
            {"can_cache": True, "key": "test", "ttl": 3600,
             "thinking_key": "thinking_enabled_test"},
            {}, "test_module",
        )
        self.assertIsNone(result)
        self.assertFalse(cached)


@pytest.mark.unit_llm
class TestPrecheckAllModules(unittest.TestCase):
    """_precheck_all_modules 批量缓存预检。"""

    def setUp(self):
        from src.python.llm.prompts import LLM_MODULE_FAILURE
        self._orig = dict(LLM_MODULE_FAILURE)
        LLM_MODULE_FAILURE.clear()

    def tearDown(self):
        from src.python.llm.prompts import LLM_MODULE_FAILURE
        LLM_MODULE_FAILURE.clear()
        LLM_MODULE_FAILURE.update(self._orig)

    @patch("src.python.llm.generators_orchestrator.is_llm_module_enabled", return_value=False)
    def test_disabled_module_sets_failure(self, mock_enabled):
        """模块已禁用 → LLM_MODULE_FAILURE 记录 FAIL_REASON_DISABLED。"""
        from src.python.llm.generators_orchestrator import _precheck_all_modules
        from src.python.llm.prompts import FAIL_REASON_DISABLED, LLM_MODULE_FAILURE

        cache_info = {
            "global_macro": {"can_cache": True, "key": "llm_global_macro", "ttl": 86400,
                             "thinking_key": "thinking_enabled_global_macro"},
        }
        _precheck_all_modules({}, cache_info, _force=False)
        self.assertEqual(
            LLM_MODULE_FAILURE.get("global_macro"),
            FAIL_REASON_DISABLED,
        )


@pytest.mark.unit_llm
class TestGeneratorFunctions(unittest.TestCase):
    """各生成器入口函数的基本检证。"""

    def test_generate_global_macro_has_prompt_builder(self):
        """generate_global_macro 有正确签名的 prompt builder。"""
        from src.python.llm.generators import generate_global_macro
        import inspect
        sig = inspect.signature(generate_global_macro)
        params = list(sig.parameters.keys())
        self.assertIn("a_indices", params)
        self.assertIn("us_indices", params)
        self.assertIn("categories", params)

    def test_generate_expert_review_signature(self):
        """generate_expert_review 包含持仓明细和穿透参数。"""
        from src.python.llm.generators import generate_expert_review
        import inspect
        sig = inspect.signature(generate_expert_review)
        params = list(sig.parameters.keys())
        self.assertIn("holdings_details", params)
        self.assertIn("penetrated_assets", params)

    def test_generate_health_check_signature(self):
        """generate_health_check 包含四个维度参数。"""
        from src.python.llm.generators import generate_health_check
        import inspect
        sig = inspect.signature(generate_health_check)
        params = list(sig.parameters.keys())
        self.assertIn("holdings_details", params)
        self.assertIn("penetrated_assets", params)

    def test_generate_penetration_deep_signature(self):
        """generate_penetration_deep_analysis 包含穿透参数。"""
        from src.python.llm.generators import generate_penetration_deep_analysis
        import inspect
        sig = inspect.signature(generate_penetration_deep_analysis)
        params = list(sig.parameters.keys())
        self.assertIn("penetrated_assets", params)

    def test_llm_client_settings_have_http2(self):
        """默认 LLM 客户端配置包含 HTTP/2。"""
        from src.python.llm.generators_orchestrator import _LLM_CLIENT_SETTINGS
        self.assertTrue(_LLM_CLIENT_SETTINGS.get("http2"))
        self.assertIn("limits", _LLM_CLIENT_SETTINGS)


@pytest.mark.unit_llm
class TestComputeModuleCacheInfo(unittest.TestCase):
    """_compute_module_cache_info 返回结构化缓存信息。"""

    def test_contains_all_module_keys(self):
        """包含所有 4 个 LLM 主模块的缓存信息。"""
        from src.python.llm.generators_orchestrator import _compute_module_cache_info
        info = _compute_module_cache_info(
            {}, {}, {}, 0, 0, 0, 0, 0, {}, None, None, force=False,
        )
        for key in ["global_macro", "expert_review", "health_check", "penetration_deep"]:
            with self.subTest(key=key):
                self.assertIn(key, info)
                self.assertIn("can_cache", info[key])
                self.assertIn("key", info[key])
                self.assertIn("ttl", info[key])

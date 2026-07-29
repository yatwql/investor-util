"""财经新闻热点与持仓关联分析 LLM 增强测试。

测试目标：
  - _apply_llm_news_correlation — LLM JSON 响应解析
  - 批次 财经新闻热点与持仓关联分析（TestBatchNewsAnalysis）
  - enhance_news_correlation — 财经新闻热点与持仓关联分析 LLM 增强
  - enhance_news_correlation 接受 llm_config 参数
  - enhance_news_correlation 逐条缓存

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test.unit.llm.test_llm_analysis -v
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.llm import enhance_news_correlation
from src.python.llm.generators_news import _apply_llm_news_correlation
from src.test.helpers import SynchronousExecutor

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


# ═══════════════════════════════════════════════════════════
#  _apply_llm_news_correlation — LLM 响应解析
# ═══════════════════════════════════════════════════════════


class TestApplyLLMAnalysis(unittest.TestCase):
    """测试 LLM JSON 响应的解析 — 返回 (relevance, sentiment, analysis) 元组列表。"""

    def setUp(self) -> None:
        self.news = [
            {"title": "新闻A", "matched_keywords": ["茅台"]},
            {"title": "新闻B", "matched_keywords": ["五粮液"]},
            {"title": "新闻C", "matched_keywords": []},
        ]

    def test_standard_response(self) -> None:
        llm_resp = '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "白酒利好"}, {"idx": 1, "relevance": "中", "sentiment": "中性", "analysis": "间接影响"}]'
        result = _apply_llm_news_correlation(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("高", "利好", "白酒利好"))
        self.assertEqual(result[1], ("中", "中性", "间接影响"))
        self.assertEqual(result[2], ("低", "中性", ""))  # 缺失项默认值

    def test_with_sentiment(self) -> None:
        """解析 sentiment 字段。"""
        llm_resp = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "白酒利好"},'
            ' {"idx": 1, "relevance": "高", "sentiment": "利空", "analysis": "利空影响"},'
            ' {"idx": 2, "relevance": "低", "sentiment": "中性", "analysis": "中性影响"}]'
        )
        batch = self.news + [{"title": "新闻D", "matched_keywords": []}]
        result = _apply_llm_news_correlation(batch, llm_resp)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], ("高", "利好", "白酒利好"))
        self.assertEqual(result[1], ("高", "利空", "利空影响"))
        self.assertEqual(result[2], ("低", "中性", "中性影响"))
        self.assertEqual(result[3], ("低", "中性", ""))  # 缺失项默认值

    def test_irrelevant_not_filtered(self) -> None:
        """"无关"不被过滤——元组中直接返回原始数据，由调用方决定是否跳过。"""
        llm_resp = '[{"idx": 0, "relevance": "高", "sentiment": "中性", "analysis": "利好"}, {"idx": 1, "relevance": "无关", "sentiment": "中性", "analysis": "无关内容"}]'
        result = _apply_llm_news_correlation(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("高", "中性", "利好"))
        self.assertEqual(result[1], ("无关", "中性", "无关内容"))
        self.assertEqual(result[2], ("低", "中性", ""))

    def test_malformed_json(self) -> None:
        """JSON 解析失败 → 全部返回默认值。"""
        result = _apply_llm_news_correlation(self.news, "不是json")
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_not_a_list(self) -> None:
        """LLM 返回非数组 → 全部返回默认值。"""
        result = _apply_llm_news_correlation(self.news, '{"error": "wrong"}')
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_with_code_block(self) -> None:
        """响应包含 Markdown 代码块 → 正确提取 JSON。"""
        llm_resp = '```json\n[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "直接利好"}]\n```'
        result = _apply_llm_news_correlation(self.news[:1], llm_resp)
        self.assertEqual(result[0], ("高", "利好", "直接利好"))

    def test_idx_out_of_range(self) -> None:
        """idx 越界时忽略该条目，使用默认值填充。"""
        llm_resp = '[{"idx": 99, "relevance": "高", "sentiment": "利好", "analysis": "越界"}]'
        result = _apply_llm_news_correlation(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_empty_batch(self) -> None:
        """空列表 → 返回空列表。"""
        result = _apply_llm_news_correlation([], "[]")
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════
#  批次 财经新闻热点与持仓关联分析（TestBatchNewsAnalysis）
# ═══════════════════════════════════════════════════════════


class TestBatchNewsAnalysis(unittest.TestCase):
    """测试批次 财经新闻热点与持仓关联分析功能。"""

    def setUp(self) -> None:
        self.news_5 = [
            {"title": f"新闻{i}", "matched_keywords": ["茅台"]}
            for i in range(5)
        ]

    def test_handle_5_items_in_one_batch(self) -> None:
        """处理 5 条新闻的批次，全部成功返回。"""
        llm_resp = json.dumps([
            {"idx": i, "relevance": "高", "sentiment": "利好", "analysis": f"原因{i}"}
            for i in range(5)
        ])
        result = _apply_llm_news_correlation(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        for i in range(5):
            self.assertEqual(result[i], ("高", "利好", f"原因{i}"))

    def test_partial_json_response(self) -> None:
        """LLM 返回 3 条结果给 5 条新闻 → 缺失 2 条填充默认值。"""
        llm_resp = json.dumps([
            {"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "原因0"},
            {"idx": 2, "relevance": "中", "sentiment": "中性", "analysis": "原因2"},
            {"idx": 4, "relevance": "高", "sentiment": "利空", "analysis": "原因4"},
        ])
        result = _apply_llm_news_correlation(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0], ("高", "利好", "原因0"))
        self.assertEqual(result[1], ("低", "中性", ""))  # 缺失
        self.assertEqual(result[2], ("中", "中性", "原因2"))
        self.assertEqual(result[3], ("低", "中性", ""))  # 缺失
        self.assertEqual(result[4], ("高", "利空", "原因4"))

    def test_empty_batch(self) -> None:
        """空批次 → 返回空列表。"""
        result = _apply_llm_news_correlation([], "[]")
        self.assertEqual(result, [])

    def test_fewer_results_than_requested(self) -> None:
        """LLM 返回 1 条结果给 5 条新闻 → 缺失 4 条填充默认值。"""
        llm_resp = json.dumps([
            {"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "原因0"},
        ])
        result = _apply_llm_news_correlation(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0], ("高", "利好", "原因0"))
        for i in range(1, 5):
            self.assertEqual(result[i], ("低", "中性", ""))

    def test_malformed_json_in_batch(self) -> None:
        """JSON 格式错误 → 全部返回默认值。"""
        result = _apply_llm_news_correlation(self.news_5, "这不是JSON")
        self.assertEqual(len(result), 5)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))


# ═══════════════════════════════════════════════════════════
#  enhance_news_correlation — 财经新闻热点与持仓关联分析 LLM 增强
# ═══════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.get_llm_config")
class TestEnhanceNewsCorrelation(unittest.TestCase):
    """测试 enhance_news_correlation 的主流程。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._exec_patcher = patch("src.python.llm._batch_mode.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._exec_patcher.stop()

    def setUp(self) -> None:
        self.news = [
            {"title": "新闻A", "intro": "简介", "matched_keywords": ["茅台"]},
            {"title": "新闻B", "intro": "简介", "matched_keywords": ["五粮液"]},
        ]
        self.holdings = [
            MagicMock(name="长江电力", code="600900"),
            MagicMock(name="贵州茅台", code="600519"),
        ]

    def test_llm_not_configured(self, mock_cfg: MagicMock) -> None:
        """LLM 未配置 → 返回原始数据 + 空 token 用量。"""
        mock_cfg.return_value = None
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertEqual(result, self.news)
        self.assertFalse(cached)
        self.assertEqual(usage, {})

    def test_empty_news(self, mock_cfg: MagicMock) -> None:
        """空新闻列表 → 直接返回。"""
        result, cached, usage = enhance_news_correlation([], self.holdings)
        self.assertEqual(result, [])
        self.assertFalse(cached)
        self.assertEqual(usage, {})

    @patch("src.python.llm._batch_mode.call_llm")
    @patch("src.python.llm._batch_mode.cache_get")
    def test_cache_hit(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """每篇文章独立缓存命中 → 直接返回，不调用 LLM。"""
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        # 每篇文章的独立缓存存储 dict {relevance, sentiment, analysis}
        mock_cache_get.return_value = {"relevance": "高", "sentiment": "利好", "analysis": "已缓存"}
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertTrue(cached)
        mock_call.assert_not_called()

    @patch("src.python.llm._batch_mode.call_llm")
    @patch("src.python.llm._batch_mode.cache_get")
    def test_llm_success(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """LLM 调用成功 → 返回富化数据。"""
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_cache_get.return_value = None  # 缓存未命中
        mock_call.return_value = (
            '[{"idx": 0, "relevance": "高", "analysis": "直接相关"}, '
            '{"idx": 1, "relevance": "中", "analysis": "间接影响"}]',
            {"input_tokens": 100, "output_tokens": 50},
            None,
        )
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)
        self.assertIn("llm_analysis", result[0])
        self.assertEqual(usage.get("total_tokens"), 150)

    @patch("src.python.llm._batch_mode.call_llm")
    @patch("src.python.llm._batch_mode.cache_get")
    def test_llm_failure(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """LLM 调用失败 → 返回原始数据 + 空 token 用量。"""
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_cache_get.return_value = None  # 缓存未命中
        mock_call.return_value = (None, None, None)  # 调用失败
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)
        self.assertEqual(usage, {})
        # 不应有 llm_analysis
        for item in result:
            self.assertNotIn("llm_analysis", item)


# ═══════════════════════════════════════════════════════════
#  enhance_news_correlation 接受 llm_config 参数
# ═══════════════════════════════════════════════════════════


class TestEnhanceNewsCorrelationUsesLlmConfig(unittest.TestCase):
    """测试 enhance_news_correlation 接受 llm_config 参数。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._exec_patcher = patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators_orchestrator.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()

    @patch("src.python.llm._batch_mode.cache_get", return_value=None)
    @patch("src.python.llm._batch_mode.call_llm")
    def test_passed_config_used(
        self, mock_call: MagicMock, mock_cache_get: MagicMock,
    ) -> None:
        """传入 llm_config → 不需要内部 get_llm_config()。"""
        news = [{"title": "A", "matched_keywords": ["茅台"]}]
        holdings = [MagicMock(name="茅台", code="600519")]
        mock_call.return_value = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "好"}]',
            {"input_tokens": 10, "output_tokens": 5},
            None,
        )
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_news_correlation": False}
        result, cached, usage = enhance_news_correlation(
            news, holdings, llm_config=llm_config,
        )
        self.assertIn("llm_analysis", result[0])
        # 验证 call_llm 接受到 config（首个参数应为 llm_config）
        self.assertIs(mock_call.call_args[0][2], llm_config)


# ═══════════════════════════════════════════════════════════
#  enhance_news_correlation 逐条缓存
# ═══════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.get_llm_config")
class TestEnhanceNewsCorrelationGranularCache(unittest.TestCase):
    """测试财经新闻热点与持仓关联分析的逐条缓存行为。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._exec_patcher = patch("src.python.llm._batch_mode.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._exec_patcher.stop()

    def setUp(self):
        self.news = [
            {"title": "新闻A", "intro": "简介", "matched_keywords": ["茅台"]},
            {"title": "新闻B", "intro": "简介", "matched_keywords": ["五粮液"]},
            {"title": "新闻C", "intro": "简介", "matched_keywords": ["茅台", "五粮液"]},
        ]
        self.holdings = [
            MagicMock(name="长江电力", code="600900"),
            MagicMock(name="贵州茅台", code="600519"),
        ]

    @patch("src.python.llm._batch_mode.cache_get")
    @patch("src.python.llm._batch_mode.call_llm")
    def test_all_articles_cached(
        self, mock_call: MagicMock, mock_cache_get: MagicMock,
        mock_cfg: MagicMock,
    ) -> None:
        """全部文章独立缓存命中 → cached=True + 不调用 LLM。"""
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_cache_get.return_value = {"relevance": "高", "sentiment": "利好", "analysis": "缓存"}
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertTrue(cached)
        mock_call.assert_not_called()
        # 文章应有 llm_analysis 字段
        for item in result:
            self.assertIn("llm_analysis", item)

    @patch("src.python.llm._batch_mode.cache_get", return_value=None)
    @patch("src.python.llm._batch_mode.call_llm")
    def test_no_cache_all_fresh(
        self, mock_call: MagicMock, mock_cache_get: MagicMock,
        mock_cfg: MagicMock,
    ) -> None:
        """全部未缓存 → cached=False + 调用 LLM。"""
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_call.return_value = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "A"},'
            '{"idx": 1, "relevance": "中", "sentiment": "中性", "analysis": "B"},'
            '{"idx": 2, "relevance": "低", "sentiment": "利空", "analysis": "C"}]',
            {"input_tokens": 200, "output_tokens": 100},
            None,
        )
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)
        self.assertGreater(usage.get("total_tokens", 0), 0)
        mock_call.assert_called_once()

    @patch("src.python.llm._batch_mode.cache_get")
    @patch("src.python.llm._batch_mode.call_llm")
    def test_mixed_cache(
        self, mock_call: MagicMock, mock_cache_get: MagicMock,
        mock_cfg: MagicMock,
    ) -> None:
        """部分文章缓存 → 仅未缓存文章走 LLM。"""
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        # 文章 0 和 2 缓存命中，文章 1 未命中
        self._call_count = 0

        def _side_effect(*args, **kwargs):
            self._call_count += 1
            # 前 2 次调用对应文章 0 和 2（已排序后 top_news 顺序）
            if self._call_count in (1, 3):
                return {"relevance": "高", "sentiment": "利好", "analysis": "缓存"}
            return None

        mock_cache_get.side_effect = _side_effect
        mock_call.return_value = (
            '[{"idx": 0, "relevance": "中", "sentiment": "中性", "analysis": "新鲜"}]',
            {"input_tokens": 50, "output_tokens": 25},
            None,
        )
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)  # 部分未缓存 → 整体 cached=False
        mock_call.assert_called_once()

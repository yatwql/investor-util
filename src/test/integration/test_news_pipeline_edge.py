"""新闻全链路集成测试 — fetch → aggregate → deduplicate → correlate → write。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/integration/test_news_pipeline_edge.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.edge]


@pytest.mark.edge
class TestNewsPipelineIntegration(unittest.TestCase):
    """新闻流水线：聚合→去重→关联→写入全链路。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.news_cache_dir = os.path.join(self.tmp.name, "cache")
        os.makedirs(self.news_cache_dir, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _mock_news_item(self, title: str, source: str, ctime: str = "2026-07-08 10:00"):
        return {
            "title": title, "intro": f"{title}摘要",
            "url": f"https://{source}.com/{title}",
            "media_name": source, "ctime": ctime,
            "matched_keywords": [],
            "enriched_keywords": [],
        }

    @patch("src.python.providers.news_aggregator.fetch_news_from_all_sources")
    def test_aggregate_deduplicate_correlate_chain(self, mock_fetch):
        """聚合→去重→关联：3 条新闻中含重复 → 输出 2 条。"""
        from src.python.providers.news_aggregator import aggregate_news
        from src.python.providers.news_keywords import build_holding_keywords
        from src.python.models import Holding

        mock_fetch.return_value = [
            self._mock_news_item("新闻A", "新浪"),
            self._mock_news_item("新闻B", "东方财富"),
            self._mock_news_item("新闻A", "新浪"),  # 重复
        ]
        holdings = [Holding("账户", "贵州茅台", "600519", 100, 150.0)]
        keywords = build_holding_keywords(holdings, [], {})
        news = aggregate_news(["sina", "eastmoney"], top_n=10)
        self.assertIsNotNone(news)
        self.assertGreaterEqual(len(news), 2)
        # 去重后不应有重复标题
        titles = [n["title"] for n in news]
        self.assertEqual(len(titles), len(set(titles)), "重复新闻应被去重")

    @patch("src.python.providers.news_correlator._build_keyword_lookup")
    @patch("src.python.providers.news_correlator._compute_relevance")
    def test_correlator_sorts_by_relevance(self, mock_relevance, mock_lookup):
        """关联引擎按关联度排序输出。"""
        from src.python.providers.news_correlator import correlate_news
        from src.python.models import Holding

        mock_lookup.return_value = {"贵州茅台", "600519"}
        mock_relevance.side_effect = lambda news, kw: 0.9 if "茅台" in news["title"] else 0.1

        news = [
            {"title": "无关新闻", "intro": "...", "url": "https://a.com", "ctime": "2026-07-08", "matched_keywords": []},
            {"title": "茅台股价创新高", "intro": "...", "url": "https://b.com", "ctime": "2026-07-08", "matched_keywords": ["茅台"]},
        ]
        holdings = [Holding("账户", "贵州茅台", "600519", 100, 150.0)]
        result = correlate_news(news, holdings, [], {})
        self.assertTrue(result)
        # 关联度高的应在前
        top = result[0] if result else {}
        self.assertIn("茅台", top.get("title", ""))

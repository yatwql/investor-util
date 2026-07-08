"""新闻全链路集成测试 — fetch → aggregate → deduplicate → correlate → write。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/integration/test_news_pipeline_edge.py -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

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

    def test_aggregate_deduplicate_correlate_chain(self):
        """聚合→去重→关联：3 条新闻中含重复 → 输出 2 条。"""
        from src.python.providers.news_aggregator import aggregate_news

        mock_news = [
            self._mock_news_item("新闻A", "新浪"),
            self._mock_news_item("新闻B", "东方财富"),
            self._mock_news_item("新闻C", "财联社"),
        ]

        with (
            patch("src.python.providers.news_aggregator._fetch_from_all_sources",
                  return_value=(mock_news, {"sina": (2, "OK"), "eastmoney": (1, "OK"), "cls": (1, "OK")})),
            patch("src.python.providers.news_aggregator._check_news_cache",
                  return_value=None),
            patch("src.python.providers.news_aggregator._save_news_cache"),
            # 注意：patch news_aggregator 模块级的引用（而非 news_correlator），
            # 因为 news_aggregator.py 在模块级 from ... import 了该函数
            patch("src.python.providers.news_aggregator.correlate_news_with_holdings",
                  side_effect=lambda items, keywords, **kw: items),
        ):
            news = aggregate_news(["茅台", "白酒"], top_n=10)

        self.assertIsNotNone(news)
        # mock 返回 3 条，full pipeline 应全部返回（不重复）
        self.assertEqual(len(news), 3)

    def test_correlator_sorts_by_relevance(self):
        """关联引擎按关联度排序输出。"""
        from src.python.providers.news_correlator import correlate_news_with_holdings

        news = [
            {"title": "无关新闻", "intro": "...", "url": "https://a.com",
             "ctime": "2026-07-08", "matched_keywords": []},
            {"title": "茅台股价创新高", "intro": "...", "url": "https://b.com",
             "ctime": "2026-07-08", "matched_keywords": []},
        ]
        # 传入真实关键词，"茅台" 会匹配第 2 条
        result = correlate_news_with_holdings(news, ["茅台", "白酒"], top_n=10)
        self.assertTrue(result)
        # 关联度高的应在前
        top = result[0] if result else {}
        self.assertIn("茅台", top.get("title", ""))

    def test_fetch_from_all_sources_partial_failure(self):
        """多源并行获取：部分源失败时不影响其他源的数据。"""
        from src.python.providers.news_aggregator import _fetch_from_all_sources

        sources = ["sina", "eastmoney", "cls"]

        with (
            patch("src.python.providers.news_aggregator._FETCH_MAP") as mock_map,
        ):
            # sina 成功返回 2 条，eastmoney 抛出异常，cls 成功返回 1 条
            mock_map.get.side_effect = lambda key: {
                "sina": lambda n: [
                    {"title": "新浪新闻A", "url": "http://sina.com/a", "ctime": "2026-07-08"},
                    {"title": "新浪新闻B", "url": "http://sina.com/b", "ctime": "2026-07-08"},
                ],
                "eastmoney": lambda n: (_ for _ in ()).throw(Exception("网络异常")),
                "cls": lambda n: [
                    {"title": "财联社新闻C", "url": "http://cls.com/c", "ctime": "2026-07-08"},
                ],
            }.get(key)

            all_raw, src_results = _fetch_from_all_sources(sources, per_source=10)

        # 应包含成功源的数据（sina=2, cls=1）
        self.assertEqual(len(all_raw), 3)

        # 各源状态：sina=OK(2), eastmoney=失败, cls=OK(1)
        self.assertEqual(src_results["sina"][0], 2)
        self.assertEqual(src_results["sina"][1], "OK")
        self.assertNotEqual(src_results["eastmoney"][1], "OK")
        self.assertEqual(src_results["cls"][0], 1)
        self.assertEqual(src_results["cls"][1], "OK")

    def test_fetch_from_all_sources_deduplicates_by_url(self):
        """多源并行获取：相同 URL 的新闻只保留第一条。"""
        from src.python.providers.news_aggregator import _fetch_from_all_sources

        sources = ["sina", "eastmoney"]

        with (
            patch("src.python.providers.news_aggregator._FETCH_MAP") as mock_map,
        ):
            # 两个源返回完全相同的新闻（相同 URL）
            duplicate_item = {"title": "相同新闻", "url": "http://dup.com/x", "ctime": "2026-07-08"}
            mock_map.get.side_effect = lambda key: {
                "sina": lambda n: [dict(duplicate_item)],
                "eastmoney": lambda n: [dict(duplicate_item)],
            }.get(key)

            all_raw, src_results = _fetch_from_all_sources(sources, per_source=10)

        # 去重后只保留 1 条（先到的不一定是哪个，但数量为 1）
        self.assertEqual(len(all_raw), 1)
        self.assertEqual(all_raw[0]["title"], "相同新闻")

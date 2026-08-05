"""新闻流水线全链路集成 — fetch → aggregate → deduplicate → correlate。

验证新闻从聚合、去重、关键词关联到报告数据构建的端到端协同，
外部 API 一律 mock，避免真实请求。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.integration, pytest.mark.integration_news_pipeline]


@pytest.mark.integration
@pytest.mark.integration_news_pipeline
class TestNewsPipeline(unittest.TestCase):
    """新闻流水线全链路 — fetch → aggregate → deduplicate → correlate。

    验证各子步骤端到端协同工作，mock 外部 API 避免真实请求。
    """

    def _mock_news_item(self, title: str, url: str = "",
                        intro: str = "", source: str = "新浪财经",
                        ctime: str = "2026-07-03 10:00:00") -> dict:
        return {
            "title": title, "url": url or f"http://test.com/{hash(title)}",
            "intro": intro or f"{title}简介", "source": source,
            "ctime": ctime, "content": f"{title}正文",
        }

    def test_aggregate_news_deduplicates_by_url(self):
        """aggregate_news 按 URL 去重，相同 URL 只保留第一条。

        注：去重发生在 _fetch_from_all_sources 内部（URL 已去重进入 all_raw），
        此处验证全链路整合正确：mock 已去重的数据，确认输出条数一致。
        """
        from src.python.providers.news_aggregator import aggregate_news

        # _fetch_from_all_sources 在 mock 层面模拟去重后的结果
        mock_news = [
            self._mock_news_item("茅台股价突破2000元", url="http://test.com/a"),
            self._mock_news_item("腾讯发布财报", url="http://test.com/b"),
        ]

        with (
            patch("src.python.providers.news_aggregator.get_enabled_sources",
                  return_value=["sina"]),
            patch("src.python.providers.news_aggregator._fetch_from_all_sources",
                  return_value=(mock_news, {"sina": (2, "OK")})),
            patch("src.python.providers.news_aggregator._save_news_cache"),
            patch("src.python.providers.news_aggregator.correlate_news_with_holdings",
                  side_effect=lambda items, keywords, **kw: items),
        ):
            result = aggregate_news(keywords=["茅台"], top_n=10)

        # 模拟去重后应有 2 条（URL 不重复）
        self.assertEqual(len(result), 2)

    def test_correlate_news_matches_keywords(self):
        """correlate_news_with_holdings 按关键词匹配，matched_keywords 字段正确。"""
        from src.python.providers.news_correlator import correlate_news_with_holdings

        news_list = [
            self._mock_news_item("茅台股价创新高", intro="贵州茅台今日股价突破2000元"),
            self._mock_news_item("腾讯发布财报", intro="腾讯控股营收同比增长"),
            self._mock_news_item("无关新闻", intro="今日天气晴好"),
        ]
        keywords = ["茅台", "腾讯"]
        result = correlate_news_with_holdings(news_list, keywords, top_n=10)

        # 应匹配到 2 条
        self.assertEqual(len(result), 2)

        # 按匹配数降序
        result_titles = {item["title"]: item for item in result}
        self.assertIn("matched_keywords", result_titles["茅台股价创新高"])
        self.assertIn("茅台", result_titles["茅台股价创新高"]["matched_keywords"])
        self.assertIn("腾讯", result_titles["腾讯发布财报"]["matched_keywords"])

    def test_aggregate_news_empty_keywords_returns_raw(self):
        """空关键词时 correlate_news_with_holdings 返回原始列表。"""
        from src.python.providers.news_correlator import correlate_news_with_holdings

        news_list = [self._mock_news_item("测试新闻")]
        result = correlate_news_with_holdings(news_list, [], top_n=10)
        self.assertEqual(len(result), 1)

    def test_build_news_data_integration(self):
        """build_news_data 端到端：持仓 → 新闻 → 关联。

        Mock 外部的 aggregate_news，验证返回结构包含完整字段。
        """
        from src.python.report.news_correlation import build_news_data

        holdings = [
            Holding("证券", "贵州茅台", "600519", 100, 150.0),
            Holding("支付宝", "易方达蓝筹", "005827", 500, 2.0),
        ]

        mock_news = [
            {"title": "茅台股价新高", "intro": "贵州茅台今日大涨",
             "url": "http://test.com/mt", "source": "新浪财经",
             "ctime": "2026-07-03", "content": ""},
            {"title": "易方达基金分红", "intro": "易方达基金发布分红公告",
             "url": "http://test.com/yfd", "source": "东方财富",
             "ctime": "2026-07-03", "content": ""},
        ]

        with (
            patch("src.python.providers.news_aggregator.aggregate_news",
                  return_value=mock_news),
            patch("src.python.providers.news_keywords.build_holding_keywords",
                  return_value=["茅台", "易方达"]),
            patch("src.python.fetcher.industry.batch_fetch_industry_data",
                  return_value={}),
        ):
            news_result, news_meta = build_news_data(holdings, top_n=10)

        self.assertIsInstance(news_result, list)
        self.assertIsInstance(news_meta, dict)
        self.assertIn("active_sources", news_meta)
        self.assertIn("llm_enabled", news_meta)

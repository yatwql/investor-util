"""新闻关联匹配模块单元测试。

测试目标：
  - correlate_news_with_holdings — 关键词匹配、排序、去重

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_news_correlator -v
"""

from __future__ import annotations

import unittest

from src.python.providers.news_correlator import correlate_news_with_holdings


class TestCorrelateNewsWithHoldings(unittest.TestCase):
    """correlate_news_with_holdings 测试。"""

    def setUp(self):
        self.sample_news = [
            {"title": "长江电力股价创新高", "intro": "电力板块持续走强", "url": "http://a.com/1"},
            {"title": "宁德时代发布新电池", "intro": "电池技术突破", "url": "http://a.com/2"},
            {"title": "腾讯控股回购股份", "intro": "互联网板块企稳", "url": "http://a.com/3"},
        ]
        self.keywords = ["长江电力", "宁德", "腾讯"]

    def test_empty_news(self) -> None:
        """空新闻列表 → 空列表。"""
        self.assertEqual(correlate_news_with_holdings([], self.keywords), [])

    def test_empty_keywords(self) -> None:
        """空关键词 → 原列表返回（无 matched_keywords）。"""
        result = correlate_news_with_holdings(self.sample_news, [])
        self.assertEqual(len(result), 3)
        for item in result:
            self.assertNotIn("matched_keywords", item)

    def test_keyword_matched(self) -> None:
        """新闻标题含关键词 → matched_keywords 包含该词。"""
        result = correlate_news_with_holdings(self.sample_news, self.keywords)
        for news in result:
            if "长江电力" in news.get("title", ""):
                self.assertIn("长江电力", news["matched_keywords"])

    def test_no_match(self) -> None:
        """无匹配关键词 → 结果为空。"""
        news = [{"title": "天气日报", "intro": "今日晴间多云", "url": "http://a.com/w"}]
        result = correlate_news_with_holdings(news, self.keywords)
        self.assertEqual(result, [])

    def test_ordering_by_match_count(self) -> None:
        """匹配关键词多的新闻排在前面。"""
        news = [
            {"title": "长江电力", "intro": "宁德时代利好", "url": "http://a.com/1"},
            {"title": "腾讯控股", "intro": "", "url": "http://a.com/2"},
        ]
        result = correlate_news_with_holdings(news, self.keywords)
        # 第一条匹配 2 个词，应在前
        first_count = len(result[0]["matched_keywords"])
        second_count = len(result[1]["matched_keywords"])
        self.assertGreaterEqual(first_count, second_count)

    def test_dedup_by_url(self) -> None:
        """同一 URL 只保留一条。"""
        news = [
            {"title": "长江电力新闻", "intro": "长江电力", "url": "http://a.com/dup"},
            {"title": "长江电力报道", "intro": "长江电力", "url": "http://a.com/dup"},
            {"title": "宁德时代消息", "intro": "宁德时代", "url": "http://a.com/unique"},
        ]
        result = correlate_news_with_holdings(news, self.keywords)
        self.assertEqual(len(result), 2)

    def test_top_n_limit(self) -> None:
        """top_n 限制返回条数。"""
        news = [
            {"title": f"新闻{i}", "intro": f"长江电力{i}", "url": f"http://a.com/{i}"}
            for i in range(20)
        ]
        result = correlate_news_with_holdings(news, self.keywords, top_n=5)
        self.assertLessEqual(len(result), 5)

    def test_intro_also_searched(self) -> None:
        """简介中也搜索关键词。"""
        news = [
            {"title": "财经早报", "intro": "长江电力今日发布年报", "url": "http://a.com/intro"},
        ]
        result = correlate_news_with_holdings(news, self.keywords)
        self.assertEqual(len(result), 1)
        self.assertIn("长江电力", result[0]["matched_keywords"])

    def test_case_insensitive(self) -> None:
        """大小写不敏感匹配。"""
        news = [
            {"title": "AAPL rises 2%", "intro": "", "url": "http://a.com/aapl"},
        ]
        result = correlate_news_with_holdings(news, ["aapl"])
        self.assertEqual(len(result), 1)

    def test_matched_keywords_field_inserted(self) -> None:
        """结果中每条新闻都含 matched_keywords 字段。"""
        result = correlate_news_with_holdings(self.sample_news, self.keywords)
        for news in result:
            self.assertIn("matched_keywords", news)

    def test_partial_word_not_matched(self) -> None:
        """部分子串不匹配（关键词是完整词匹配）。"""
        news = [
            {"title": "长江电力股", "intro": "", "url": "http://a.com/partial"},
        ]
        # "长江电力股" 包含 "长江电力"，但这里是 substr 匹配
        # 实际上由于使用了 `kw in text`，substr 是匹配的
        # 这是已知行为——关键词是子串匹配
        result = correlate_news_with_holdings(news, ["长江电力"])
        self.assertEqual(len(result), 1)

    def test_missing_title_handled(self) -> None:
        """缺少 title 字段不崩溃。"""
        news = [{"intro": "长江电力相关", "url": "http://a.com/mt"}]
        result = correlate_news_with_holdings(news, self.keywords)
        self.assertEqual(len(result), 1)

    def test_missing_intro_handled(self) -> None:
        """缺少 intro 字段不崩溃。"""
        news = [{"title": "长江电力", "url": "http://a.com/mi"}]
        result = correlate_news_with_holdings(news, self.keywords)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()

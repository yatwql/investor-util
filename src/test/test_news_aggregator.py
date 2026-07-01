"""新闻聚合编排逻辑单元测试。

测试目标：
  - get_enabled_sources — 从配置读取启用的源
  - _compute_cache_key — 缓存键生成
  - _finalize_news_results — 排序、关联、截断
  - aggregate_news — 完整编排（mock 各源）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_news_aggregator.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestGetEnabledSources(unittest.TestCase):
    """get_enabled_sources 测试。"""

    @patch("src.python.providers.news_aggregator._SOURCE_LABELS",
           {"akshare": "akshare", "eastmoney": "东方财富", "cls": "财联社"})
    @patch("src.python.config.get_config")
    def test_all_enabled(self, mock_config):
        """全部启用 → 返回所有源。"""
        mock_config.return_value = {
            "news_sources": {"akshare": True, "eastmoney": True, "cls": True},
        }
        from src.python.providers.news_aggregator import get_enabled_sources
        result = get_enabled_sources()
        self.assertEqual(len(result), 3)
        self.assertIn("akshare", result)

    @patch("src.python.providers.news_aggregator._SOURCE_LABELS",
           {"akshare": "akshare", "eastmoney": "东方财富"})
    @patch("src.python.config.get_config")
    def test_partial_enabled(self, mock_config):
        """部分启用 → 仅返回启用的。"""
        mock_config.return_value = {
            "news_sources": {"akshare": True, "eastmoney": False},
        }
        from src.python.providers.news_aggregator import get_enabled_sources
        result = get_enabled_sources()
        self.assertEqual(result, ["akshare"])

    @patch("src.python.providers.news_aggregator._SOURCE_LABELS",
           {"akshare": "akshare", "eastmoney": "东方财富"})
    @patch("src.python.config.get_config")
    def test_empty_config(self, mock_config):
        """空配置 → 空列表。"""
        mock_config.return_value = {}
        from src.python.providers.news_aggregator import get_enabled_sources
        self.assertEqual(get_enabled_sources(), [])


class TestComputeCacheKey(unittest.TestCase):
    """_compute_cache_key 纯函数测试。"""

    def _call(self, keywords, top_n, sources, per_source):
        from src.python.providers.news_aggregator import _compute_cache_key
        return _compute_cache_key(keywords, top_n, sources, per_source)

    def test_returns_string(self):
        """返回以 news_ 为前缀的 12 位 hex 字符串。"""
        key = self._call(["kw1"], 10, ["akshare"], 50)
        self.assertIsInstance(key, str)
        self.assertTrue(key.startswith("news_"))
        self.assertEqual(len(key), 5 + 12)  # "news_" + 12 hex

    def test_deterministic(self):
        """相同输入 → 相同键。"""
        k1 = self._call(["kw1", "kw2"], 10, ["a", "b"], 50)
        k2 = self._call(["kw1", "kw2"], 10, ["a", "b"], 50)
        self.assertEqual(k1, k2)

    def test_different_input(self):
        """不同输入 → 不同键。"""
        k1 = self._call(["kw1"], 10, ["a"], 50)
        k2 = self._call(["kw2"], 10, ["a"], 50)
        self.assertNotEqual(k1, k2)


class TestFinalizeNewsResults(unittest.TestCase):
    """_finalize_news_results 测试。"""

    def _call(self, all_raw, keywords, top_n):
        from src.python.providers.news_aggregator import _finalize_news_results
        return _finalize_news_results(all_raw, keywords, top_n)

    @patch("src.python.providers.news_aggregator.correlate_news_with_holdings",
           side_effect=lambda items, *a, **kw: items)
    def test_empty_input(self, mock_corr):
        """空输入 → 空列表。"""
        self.assertEqual(self._call([], [], 10), [])

    @patch("src.python.providers.news_aggregator.correlate_news_with_holdings",
           side_effect=lambda items, *a, **kw: items)
    def test_sort_by_ctime(self, mock_corr):
        """按 ctime 降序排列。"""
        items = [
            {"ctime": "2026-07-01 10:00", "title": "早"},
            {"ctime": "2026-07-02 10:00", "title": "晚"},
        ]
        result = self._call(items, [], 10)
        self.assertEqual(result[0]["title"], "晚")

    @patch("src.python.providers.news_aggregator.correlate_news_with_holdings",
           side_effect=lambda items, *a, **kw: items)
    def test_ensure_matched_keywords(self, mock_corr):
        """每个条目确保有 matched_keywords 字段。"""
        items = [{"ctime": "2026-07-01", "title": "test"}]
        result = self._call(items, [], 10)
        self.assertIn("matched_keywords", result[0])

    @patch("src.python.providers.news_aggregator.correlate_news_with_holdings",
           side_effect=lambda items, *a, **kw: items)
    def test_truncate_top_n(self, mock_corr):
        """超过 top_n 条 → 截断。"""
        items = [{"ctime": f"2026-07-01 {i:02d}:00", "title": f"n{i}"}
                 for i in range(20)]
        result = self._call(items, [], 5)
        self.assertEqual(len(result), 5)

    @patch("src.python.providers.news_aggregator.correlate_news_with_holdings",
           side_effect=lambda items, *a, **kw: items)
    def test_existing_matched_keywords_preserved(self, mock_corr):
        """已有的 matched_keywords 不被覆盖。"""
        items = [{"ctime": "2026-07-01", "title": "test",
                  "matched_keywords": ["preserved"]}]
        result = self._call(items, ["keyword"], 10)
        self.assertEqual(result[0]["matched_keywords"], ["preserved"])


class TestAggregateNews(unittest.TestCase):
    """aggregate_news 编排测试。"""

    def setUp(self):
        self._source_patch = patch(
            "src.python.providers.news_aggregator._SOURCE_LABELS",
            {"eastmoney": "东方财富"},
        )
        self._source_patch.start()

    def tearDown(self):
        self._source_patch.stop()

    @patch("src.python.providers.news_aggregator._save_news_cache")
    @patch("src.python.providers.news_aggregator._check_news_cache")
    @patch("src.python.providers.news_aggregator._fetch_from_all_sources")
    @patch("src.python.providers.news_aggregator._finalize_news_results")
    def test_cache_hit(self, mock_finalize, mock_fetch, mock_cache_check,
                       mock_save):
        """缓存命中 → 不调取源。"""
        mock_cache_check.return_value = [{"title": "cached"}]
        from src.python.providers.news_aggregator import aggregate_news
        result = aggregate_news(["kw"], top_n=10, sources=["eastmoney"])
        self.assertEqual(len(result), 1)
        mock_fetch.assert_not_called()

    @patch("src.python.providers.news_aggregator._log_source_status")
    @patch("src.python.providers.news_aggregator._save_news_cache")
    @patch("src.python.providers.news_aggregator._check_news_cache")
    @patch("src.python.providers.news_aggregator._fetch_from_all_sources")
    def test_cache_miss(self, mock_fetch, mock_cache_check, mock_save,
                        mock_log):
        """缓存未命中 → 调取源并保存缓存。"""
        mock_cache_check.return_value = None
        mock_fetch.return_value = ([{"ctime": "2026-07-01", "title": "news"}],
                                    {"eastmoney": (1, "OK")})

        from src.python.providers.news_aggregator import (
            _finalize_news_results,
        )

        with patch.object(
            __import__("src.python.providers.news_aggregator",
                       fromlist=["correlate_news_with_holdings"]),
            "correlate_news_with_holdings",
            side_effect=lambda items, *a, **kw: items,
        ):
            from src.python.providers.news_aggregator import aggregate_news
            result = aggregate_news(["kw"], top_n=10, sources=["eastmoney"])

        mock_save.assert_called_once()

    @patch("src.python.providers.news_aggregator._check_news_cache")
    @patch("src.python.providers.news_aggregator._fetch_from_all_sources")
    def test_all_sources_fail(self, mock_fetch, mock_cache_check):
        """所有源失败 → 空列表。"""
        mock_cache_check.return_value = None
        mock_fetch.return_value = ([], {})
        from src.python.providers.news_aggregator import aggregate_news
        result = aggregate_news(["kw"], top_n=10, sources=["eastmoney"])
        self.assertEqual(result, [])

    @patch("src.python.providers.news_aggregator._check_news_cache")
    @patch("src.python.providers.news_aggregator.get_enabled_sources")
    def test_default_sources(self, mock_enabled, mock_cache_check):
        """未指定源 → 使用启用的源。"""
        mock_cache_check.return_value = None
        mock_enabled.return_value = ["eastmoney"]

        from src.python.providers.news_aggregator import (
            _fetch_from_all_sources,
        )

        with patch(
            "src.python.providers.news_aggregator._fetch_from_all_sources",
            return_value=([], {}),
        ):
            from src.python.providers.news_aggregator import aggregate_news
            aggregate_news(["kw"], top_n=10)

        mock_enabled.assert_called_once()

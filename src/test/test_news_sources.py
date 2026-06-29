"""新闻源获取模块单元测试。

测试目标：
  - _SOURCE_LABELS / _FALLBACK_ENABLED 完整性
  - get_source_label 查找
  - _FETCH_MAP 元数据完整性

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_news_sources -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.providers.news_sources import (
    _FETCH_MAP,
    _FALLBACK_ENABLED,
    _SOURCE_LABELS,
    get_source_label,
)


class TestSourceMetadata(unittest.TestCase):
    """新闻源元数据测试。"""

    def test_source_labels_complete(self) -> None:
        """所有源都有中文标签。"""
        expected_sources = {"sina", "eastmoney", "cls", "wallstreetcn", "akshare"}
        self.assertEqual(set(_SOURCE_LABELS.keys()), expected_sources)

    def test_fallback_enabled_complete(self) -> None:
        """所有源都有默认开关值。"""
        self.assertEqual(set(_FALLBACK_ENABLED.keys()), set(_SOURCE_LABELS.keys()))

    def test_sina_default_enabled(self) -> None:
        """新浪默认开启。"""
        self.assertTrue(_FALLBACK_ENABLED["sina"])

    def test_eastmoney_default_enabled(self) -> None:
        """东方财富默认开启（API 已修复）。"""
        self.assertTrue(_FALLBACK_ENABLED["eastmoney"])

    def test_cls_default_disabled(self) -> None:
        """财联社默认关闭。"""
        self.assertFalse(_FALLBACK_ENABLED["cls"])

    def test_wallstreetcn_default_enabled(self) -> None:
        """华尔街见闻默认开启。"""
        self.assertTrue(_FALLBACK_ENABLED["wallstreetcn"])

    def test_akshare_default_enabled(self) -> None:
        """akshare 默认开启。"""
        self.assertTrue(_FALLBACK_ENABLED["akshare"])

    def test_get_source_label_known(self) -> None:
        """已知源 → 返回中文标签。"""
        self.assertEqual(get_source_label("sina"), "新浪财经")
        self.assertEqual(get_source_label("cls"), "财联社")

    def test_get_source_label_unknown(self) -> None:
        """未知源 → 返回原名称。"""
        self.assertEqual(get_source_label("unknown_source"), "unknown_source")

    def test_fetch_map_complete(self) -> None:
        """每个源都有对应的获取函数。"""
        self.assertEqual(set(_FETCH_MAP.keys()), set(_SOURCE_LABELS.keys()))

    def test_fetch_map_callable(self) -> None:
        """_FETCH_MAP 中所有值都是 callable。"""
        for name, fn in _FETCH_MAP.items():
            self.assertTrue(callable(fn), f"{name} 的 fetch 函数不可调用")

    def test_get_source_label_empty_string(self) -> None:
        """空字符串 → 返回空字符串。"""
        self.assertEqual(get_source_label(""), "")

    def test_get_source_label_whitespace(self) -> None:
        """空白字符 → 返回原值。"""
        self.assertEqual(get_source_label("  "), "  ")

    def test_get_source_label_numeric(self) -> None:
        """纯数字字符串 → 返回原值。"""
        self.assertEqual(get_source_label("123"), "123")

    def test_source_label_values_non_empty(self) -> None:
        """所有中文标签非空。"""
        for key, label in _SOURCE_LABELS.items():
            self.assertTrue(label, f"{key} 的标签为空")

    def test_fallback_enabled_values_are_bool(self) -> None:
        """_FALLBACK_ENABLED 值均为布尔类型。"""
        for key, val in _FALLBACK_ENABLED.items():
            self.assertIsInstance(val, bool, f"{key} 的值不是布尔类型")


class TestFetchFunctionBehavior(unittest.TestCase):
    """各源获取函数的行为测试。"""

    @patch("src.python.providers.sina_news.fetch_news")
    def test_fetch_from_sina_returns_list(self, mock_fetch: MagicMock) -> None:
        """新浪财经获取函数返回列表。"""
        mock_fetch.return_value = [{"title": "t1", "url": "http://u1"}]
        fn = _FETCH_MAP["sina"]
        result = fn(num=3)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    @patch("src.python.providers.sina_news.fetch_news")
    def test_fetch_from_sina_dedup_by_url(self, mock_fetch: MagicMock) -> None:
        """新浪财经获取函数按 URL 去重。"""
        mock_fetch.return_value = [
            {"title": "a", "url": "http://u"},
            {"title": "b", "url": "http://u"},
        ]
        fn = _FETCH_MAP["sina"]
        result = fn(num=5)
        self.assertEqual(len(result), 1)

    @patch("src.python.providers.eastmoney_news.fetch_news")
    def test_fetch_from_eastmoney_returns_list(self, mock_fetch: MagicMock) -> None:
        """东方财富获取函数返回列表。"""
        mock_fetch.return_value = []
        fn = _FETCH_MAP["eastmoney"]
        result = fn(num=5)
        self.assertIsInstance(result, list)
        mock_fetch.assert_called_once_with(num=5)

    @patch("src.python.providers.cls_news.fetch_news")
    def test_fetch_from_cls_returns_list(self, mock_fetch: MagicMock) -> None:
        """财联社获取函数返回列表。"""
        mock_fetch.return_value = []
        fn = _FETCH_MAP["cls"]
        result = fn(num=5)
        self.assertIsInstance(result, list)
        mock_fetch.assert_called_once_with(num=5)

    @patch("src.python.providers.wallstreetcn_news.fetch_news")
    def test_fetch_from_wallstreetcn_returns_list(self, mock_fetch: MagicMock) -> None:
        """华尔街见闻获取函数返回列表。"""
        mock_fetch.return_value = []
        fn = _FETCH_MAP["wallstreetcn"]
        result = fn(num=5)
        self.assertIsInstance(result, list)
        mock_fetch.assert_called_once_with(num=5)

    @patch("src.python.providers.akshare_news.fetch_news")
    def test_fetch_from_akshare_returns_list(self, mock_fetch: MagicMock) -> None:
        """akshare 获取函数返回列表。"""
        mock_fetch.return_value = []
        fn = _FETCH_MAP["akshare"]
        result = fn(num=5)
        self.assertIsInstance(result, list)
        mock_fetch.assert_called_once_with(num=5)


if __name__ == "__main__":
    unittest.main()

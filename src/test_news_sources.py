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
from src.providers.news_sources import (
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


if __name__ == "__main__":
    unittest.main()

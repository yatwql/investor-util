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
    _SOURCE_LABELS,
    get_source_label,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_news]



class TestSourceMetadata(unittest.TestCase):
    """新闻源元数据测试。"""

    def test_source_labels_complete(self) -> None:
        """所有源都有中文标签。"""
        expected_sources = {"sina", "eastmoney", "cls", "wallstreetcn", "akshare"}
        self.assertEqual(set(_SOURCE_LABELS.keys()), expected_sources)

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


class TestDedupByTitle(unittest.TestCase):
    """_dedup_by_title 标题模糊去重测试。"""

    def _make_item(self, title: str, source: str = "东方财富") -> dict:
        return {"title": title, "_source": source, "url": "http://x.com/" + title[:10]}

    def test_cross_source_english_entity_matched(self) -> None:
        """跨源：含英数实体的同一新闻应合并（如微软+AMD+Helios）。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("微软Azure采用大规模集群AMD Helios以推动AI创新", "东方财富"),
            self._make_item("AMD与微软AI合作推出Azure上Helios系统", "财联社"),
        ]
        result = _dedup_by_title(items)
        # 改进算法下 bigram=5（微软 + azure + amd + helios + ai）≥3 → 合并为1条
        self.assertEqual(len(result), 1)

    def test_cross_source_different_news_kept(self) -> None:
        """跨源：不同新闻即使高 SequenceMatcher ratio 但实体不重叠，不应合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("2026年7月票房破25亿", "东方财富"),
            self._make_item("量化观察：预测2026年7月经营质量、动量等因子表现更优", "财联社"),
        ]
        result = _dedup_by_title(items)
        # 共享 bigram 主要为日期数字/量化术语，无实质实体重叠 → 保留2条
        self.assertEqual(len(result), 2)

    def test_cross_source_date_pattern_ratio_not_inflated(self) -> None:
        """跨源：仅共享日期格式的不同新闻，剥离日期后 ratio 应 <0.30，不进候选区。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("2026年7月票房破25亿", "东方财富"),
            self._make_item("2026年7月全国居民消费价格指数发布同比微涨", "财联社"),
        ]
        result = _dedup_by_title(items)
        # 去日期后实体 bigram 无重叠 → 保留2条
        self.assertEqual(len(result), 2)

    def test_cross_source_ratio_over_50_merged(self) -> None:
        """跨源：ratio ≥ 0.50 安全区直接合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("茅台股价突破2000元大关", "东方财富"),
            self._make_item("茅台股价突破2000元关口", "新浪财经"),
        ]
        result = _dedup_by_title(items)
        self.assertEqual(len(result), 1)

    def test_same_source_high_overlap_merged(self) -> None:
        """同源：共享实体 bigram ≥ 4 合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("英伟达发布新一代AI芯片Blackwell性能提升30%", "东方财富"),
            self._make_item("英伟达Blackwell AI芯片正式发布性能跃升30%", "东方财富"),
        ]
        result = _dedup_by_title(items)
        # 共享：英伟达、Blackwell、AI、芯片、发布、性能 → bigram≥4
        self.assertEqual(len(result), 1)

    def test_same_source_low_overlap_kept(self) -> None:
        """同源：bigram < 4 的不同新闻应保留（阈值防范误杀）。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("广发证券上调融资融券业务总规模上限至净资本2.5倍", "东方财富"),
            self._make_item("康希诺生物新冠疫苗获得世卫组织紧急使用授权", "东方财富"),
        ]
        result = _dedup_by_title(items)
        self.assertEqual(len(result), 2)

    def test_substring_dedup(self) -> None:
        """子串包含去重：短标题(≥6字)完全出现在长标题中则合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("锂电池板块集体走强宁德时代涨超5%", "东方财富"),
            self._make_item("锂电池板块集体走强", "东方财富"),
        ]
        result = _dedup_by_title(items)
        self.assertEqual(len(result), 1)

    def test_empty_input(self) -> None:
        """空输入应返回空列表。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        self.assertEqual(_dedup_by_title([]), [])

    def test_no_title_item_kept(self) -> None:
        """无标题项应直接保留。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [{"url": "http://no-title", "_source": "test"}]
        result = _dedup_by_title(items)
        self.assertEqual(len(result), 1)

    def test_cross_source_english_token_only_overlap(self) -> None:
        """跨源：仅英数 token 重叠但无实质实体重叠，不合并。

        数值 token（2.5%、0.8%）被 _normalize_title 过滤后，仅剩
        {cpi, ppi} 2 个 token，达不到跨源 ≥3 实体 bigram 的合并门槛。
        """
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("CPI同比增长2.5%PPI同比下降0.8%", "东方财富"),
            self._make_item("统计局公布CPI和PPI数据：CPI涨2.5%PPI降0.8%", "新浪财经"),
        ]
        result = _dedup_by_title(items)
        # _normalize_title 过滤百分比后 entity overlap={cpi, ppi}=2 < 3
        # ratio≈0.33 在候选区但 bigram 不足 → 保留2条
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()

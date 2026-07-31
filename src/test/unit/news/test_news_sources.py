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
        """跨源：仅英数 token 重叠但 ratio≥0.40 时走 bg=2 梯度规则合并。

        数值 token（2.5%、0.8%）被 _normalize_title 过滤后，仅剩
        {cpi, ppi} 2 个 token。ratio≈0.43 ≥ 0.40 阈值，触发
        bg=2 梯度规则（overlap≥2 + ratio≥0.40）合并。
        """
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("CPI同比增长2.5%PPI同比下降0.8%", "东方财富"),
            self._make_item("统计局公布CPI和PPI数据：CPI涨2.5%PPI降0.8%", "新浪财经"),
        ]
        result = _dedup_by_title(items)
        # bg=2 梯度规则：ratio≈0.43 ≥ 0.40 → 合并为1条
        self.assertEqual(len(result), 1)

    def test_cross_source_bg2_high_ratio_merged(self) -> None:
        """跨源：英数 token 重叠≥3（amd+helios+azure+ai），走正常 bg≥3 规则合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        # 同一事件不同表述，entity bigram 含 amd/helios/azure/ai 4 个英数 token
        # （注：原标注为 bg=2 梯度规则测试，实际走的是 bg≥3 主干规则）
        items = [
            self._make_item("微软Azure采用大规模集群AMD Helios以推动AI创新", "东方财富"),
            self._make_item("AMD与微软AI合作推出Azure上Helios系统", "新浪财经"),
        ]
        result = _dedup_by_title(items)
        # entity overlap = {amd, helios, azure, ai, _tk:helios, _tk:azure} ≥ 3 → 合并为1条
        self.assertEqual(len(result), 1)

    def test_cross_source_bg2_low_ratio_kept(self) -> None:
        """跨源：bg=2 但 ratio<0.40 时不合并，梯度规则不误杀。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        # 共享"持续""续走"2 个中文 bigram 但 ratio≈0.375，低于 0.40 门槛
        items = [
            self._make_item("科技板块持续走强", "东方财富"),
            self._make_item("国际油价持续走弱", "新浪财经"),
        ]
        result = _dedup_by_title(items)
        # overlap=2 但 ratio≈0.375 < 0.40 → 保留2条
        self.assertEqual(len(result), 2)

    def test_cross_source_year_digit_not_inflated(self) -> None:
        """跨源：仅共享独立年份数字的完全无关新闻，归一化后不进候选区。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("2026年炒股赚200万", "东方财富"),
            self._make_item("丝路视觉2026年全年业绩预期", "新浪财经"),
        ]
        result = _dedup_by_title(items)
        # normalize 剥离"2026"后仅剩炒股赚/丝路视觉全年业绩预期，ratio 极低 → 保留2条
        self.assertEqual(len(result), 2)

    def test_cross_source_long_english_token_weighted(self) -> None:
        """跨源：长英文专名（Anthropic/Meta/Helios≥4字符）在实体 bigram 中获得
        _tk: 前缀加权，使 bg 计数提升跨过 3 阈值，弥补 ratio 不足。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        # Anthropic(6)+Meta(4) → 两个长专名给双方各贡献 2 个 _tk: 虚拟 bigram
        # 中文 bigram 重叠 2 个（洽谈+算力）+ 2 个 _tk: 虚拟 = bg=4 ≥ 3 → 合并
        items = [
            self._make_item("Anthropic正与Meta开展初期洽谈，计划租赁后者算力", "新浪财经"),
            self._make_item("Meta据悉洽谈向Anthropic出租AI算力 拟进军云计算", "东方财富"),
        ]
        result = _dedup_by_title(items)
        # ratio≈0.381 < 0.40 走不了梯度规则，但 _tk: 加权后 bg≥3 通过候选区
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()

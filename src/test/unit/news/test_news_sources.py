"""新闻源获取模块单元测试。

测试目标：
  - _SOURCE_LABELS / _FALLBACK_ENABLED 完整性
  - get_source_label 查找
  - _FETCH_MAP 元数据完整性

运行：
  pytest src/test/unit/news/test_news_sources.py -v
"""

from __future__ import annotations

import os
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


class TestDedupFalseMergeGuard(unittest.TestCase):
    """跨源误合并防护回归测试（rf-290 校准结论，2026-08-17）。

    旧规则（候选区 0.30 + 安全区 0.50 直接合并 + bg=2 梯度 0.40）实测
    误合并率 ~70-80%：不同事件共享财报/回购/指数/预警/地震等模板词天然
    产生 3-6 个实体 bigram，英文统一占位符虚高 ratio。以下用例全部来自
    42560 锚点采样中的人工判定样本，必须保持两条（不合并）。
    """

    def _make_item(self, title: str, source: str = "东方财富") -> dict:
        return {"title": title, "_source": source, "url": "http://x.com/" + title[:10]}

    def test_same_company_different_events_kept(self) -> None:
        """同名不同事件（龙虎榜 vs 控制权变更）不合并——单实体重叠不足。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("兆日科技7月29日龙虎榜数据", "新浪财经"),
            self._make_item("兆日科技：筹划控制权变更事项 股票停牌", "东方财富"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_different_company_buyback_template_kept(self) -> None:
        """不同公司回购公告（共享"累计回购A股股份"模板）不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("美的集团：累计回购A股股份金额达69.73亿元", "东方财富"),
            self._make_item("中远海控：累计回购A股股份29116504股", "新浪财经"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_different_earthquake_kept(self) -> None:
        """不同地震（共享"发生N级地震"模板）不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("福建三明市尤溪县发生3.5级地震，震源深度8千米", "新浪财经"),
            self._make_item("日本熊本县发生4.4级地震", "东方财富"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_different_company_earnings_template_kept(self) -> None:
        """同源不同公司业绩快报（共享"半年度净利润同比增长"模板）不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("宏发股份：2026年半年度净利润同比增长19.89%", "东方财富"),
            self._make_item("西部矿业：2026年半年度净利润同比增长123%", "东方财富"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_different_target_price_rating_kept(self) -> None:
        """不同公司目标价/评级（共享"花旗+目标价"骨架）不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("花旗上调Visa目标价", "东方财富"),
            self._make_item("花旗：ASMPT重申“买入”评级 目标价250港元", "新浪财经"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_different_compute_contract_kept(self) -> None:
        """不同公司算力服务合同（共享"全资子公司签订算力服务合同"骨架）不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("行云科技：全资子公司签订算力服务补充协议 合同金额增至30.53", "东方财富"),
            self._make_item("亿田智能旗下全资子公司签订11.06亿元算力资源服务合同", "新浪财经"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_different_index_market_kept(self) -> None:
        """不同市场指数（共享"指数上涨/下跌 N%"骨架）不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("MSCI亚太指数下跌1%", "东方财富"),
            self._make_item("越南股指VN指数上涨1%。", "华尔街见闻"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_opposite_direction_kept(self) -> None:
        """跨源方向对立报道（暂缓加息 vs 将加息）不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("美联储主席沃什或在本次会议暂缓加息", "新浪财经"),
            self._make_item("城堡证券预计美联储将加息", "华尔街见闻"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_same_source_different_company_kept(self) -> None:
        """同源不同公司回购公告（ratio 0.7+ 模板骨架）不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("美的集团：累计回购A股股份金额达69.73亿元", "东方财富"),
            self._make_item("中远海控：累计回购A股股份29116504股", "东方财富"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)


class TestDedupTokenGradientMerge(unittest.TestCase):
    """跨源 bg=2 梯度规则（共享英数 token 专名）捕获的真重复。

    旧 bg=2 梯度（ratio≥0.40 即合并）误合并率高（英伟达 Vera Rubin vs
    英伟达投资同为 bg=2）；新规则要求共享 bigram 含英数/数字 token
    （CPI/PPI、荣耀IPO、SpaceX 类专名），纯中文公司名共享不触发。
    """

    def _make_item(self, title: str, source: str = "东方财富") -> dict:
        return {"title": title, "_source": source, "url": "http://x.com/" + title[:10]}

    def test_english_token_shared_merged(self) -> None:
        """共享英数 token（CPI/PPI）的同一数据报道合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("CPI同比增长2.5%PPI同比下降0.8%", "东方财富"),
            self._make_item("统计局公布CPI和PPI数据：CPI涨2.5%PPI降0.8%", "新浪财经"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 1)

    def test_pure_chinese_company_shared_kept(self) -> None:
        """纯中文公司名共享（英伟达 2 bigram）且事件不同不合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("英伟达Vera Rubin正全面加速量产", "东方财富"),
            self._make_item("英伟达据悉将向Lancium投资至冬30亿美元", "新浪财经"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 2)

    def test_same_event_english_entity_merged(self) -> None:
        """共享英文专名实体（SpaceX）的同一事件合并。"""
        from src.python.providers.news_aggregator import _dedup_by_title

        items = [
            self._make_item("美股三大股指小幅高开 SpaceX盘初大跌市值蒸发2050亿美元", "华尔街见闻"),
            self._make_item("SpaceX股价盘初重挫12%", "东方财富"),
        ]
        self.assertEqual(len(_dedup_by_title(items)), 1)


class TestFlushAnchorsDedup(unittest.TestCase):
    """_flush_anchors 锚点写入去重 — 同一对 (source,title) 跨轮运行不重复追加。

    背景：锚点文件 append-only，同一对新闻在每次真实抓取（_dedup_by_title
    进入候选区）时都会重新记录，多轮运行后同一对重复数十次（实测 calibration
    文件 61.6% 为重复记录），导致校准报告绝对数字失真（如 cross_skip bg=0
    从 279 虚增至 13800）。本测试验证写入层按 key 去重后跨轮不重复。
    """

    pytestmark = [
        pytest.mark.unit,
        pytest.mark.unit_news,
    ]

    def setUp(self) -> None:
        """隔离锚点路径 + 清空进程级已写 key 集合，避免污染真实 calibration 文件。"""
        import tempfile
        from unittest.mock import patch

        self._tmpdir = tempfile.mkdtemp()
        self._anchor_path = os.path.join(self._tmpdir, "anchors.jsonl")
        from src.python.providers import news_dedup

        # 隔离写入路径：patch 模块常量，确保测试不触碰真实 data/calibration/
        self._path_patch = patch("src.python.providers.news_dedup._ANCHOR_PATH", self._anchor_path)
        self._path_patch.start()
        # 重置进程级已写集合与内存记录列表
        news_dedup._WRITTEN_ANCHOR_KEYS = set()
        news_dedup._ANCHOR_RECORDS = []

    def tearDown(self) -> None:
        """恢复 patch。"""
        self._path_patch.stop()

    def _record_cross_skip(self, title_a: str, title_b: str) -> None:
        """记录一条 cross_skip 锚点（进入候选区但未合并的典型记录）。"""
        from src.python.providers.news_dedup import _record_anchor

        _record_anchor(
            {
                "source_a": "东方财富",
                "source_b": "新浪财经",
                "title_a": title_a,
                "title_b": title_b,
                "ratio": 0.312,
                "bigram_overlap": 2,
                "decision": False,
                "rule": "cross_skip",
                "ts": "",
            }
        )

    def test_same_pair_flushed_once_across_runs(self) -> None:
        """同一对新闻跨两次 flush 只写入一次。"""
        from src.python.providers.news_dedup import _flush_anchors

        # 第一轮：两条不同记录 + 一条与下一轮相同的记录
        self._record_cross_skip("特朗普下令暂停空袭伊朗", "美国连续第二晚暂停袭击伊朗")
        self._record_cross_skip("华尔街见闻", "东方财富完全不同新闻")
        _flush_anchors()
        lines1 = open(self._anchor_path, encoding="utf-8").readlines()
        self.assertEqual(len(lines1), 2, f"第一轮应写 2 条: {lines1}")

        # 第二轮：再次出现第一轮同对记录 → 不应重复追加
        self._record_cross_skip("特朗普下令暂停空袭伊朗", "美国连续第二晚暂停袭击伊朗")
        _flush_anchors()
        lines2 = open(self._anchor_path, encoding="utf-8").readlines()
        self.assertEqual(len(lines2), 2, f"第二轮不应重复追加，仍应 2 条: {lines2}")

    def test_different_pairs_still_appended(self) -> None:
        """不同 (source,title) 对正常追加，不被误去重。"""
        from src.python.providers.news_dedup import _flush_anchors

        self._record_cross_skip("新闻A", "新闻B")
        _flush_anchors()
        self._record_cross_skip("新闻C", "新闻D")
        _flush_anchors()
        lines = open(self._anchor_path, encoding="utf-8").readlines()
        self.assertEqual(len(lines), 2, f"不同对应各写一条: {lines}")

    def test_anchor_keys_cached_across_flush(self) -> None:
        """进程级已写 key 集合在 flush 后更新，后续同对直接拦截（不重复读文件）。"""
        from src.python.providers import news_dedup

        # 首次 flush 后 _WRITTEN_ANCHOR_KEYS 应包含已写 key
        self._record_cross_skip("新闻A", "新闻B")
        news_dedup._flush_anchors()
        self.assertGreaterEqual(
            len(news_dedup._WRITTEN_ANCHOR_KEYS), 1,
            "flush 后进程级 key 集合应包含已写记录",
        )


if __name__ == "__main__":
    unittest.main()

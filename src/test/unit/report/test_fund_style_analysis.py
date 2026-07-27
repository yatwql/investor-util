"""report/fund_style_base / fund_style_classify / fund_style_report 单元测试。

测试目标：
  - _market_cap_to_size：市值→规模
  - _pe_to_style：PE→估值倾向
  - _estimate_style_by_code：代码段降级
  - _classify_stock：综合判定
  - classify_fund_style：基金风格
  - _grid_distance：网格距离
  - _drift_level：漂移等级
  - analyze_style_for_all_funds：全流程
  - _push2_extended / _tencent_extended 文件缓存共享

场景覆盖：
  1. 市值阈值（大盘/中盘/小盘）
  2. PE vs 行业平均 PE 判定
  3. 代码段降级
  4. 基金风格加权
  5. 有/无 push2 数据
  6. 网格距离
  7. 漂移检测
  8. 首检/基线/严重漂移
  9. push2→tencent 文件缓存共享

运行：
  pytest src/test/ -m "unit_report" -k "fund_style" -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.report.fund_style_base import (
    _estimate_style_by_code,
    _get_size_from_code,
    _market_cap_to_size,
    _pe_to_style,
)
from src.python.report.fund_style_classify import (
    _get_industry_avg_pe,
    classify_fund_style,
)
from src.python.report.fund_style_report import (
    _drift_level,
    _grid_distance,
    analyze_style_for_all_funds,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ── _market_cap_to_size 测试 ────────────────────────────────


class TestMarketCapToSize(unittest.TestCase):
    """_market_cap_to_size：市值→规模"""

    def test_large_cap(self):
        """> 500 亿 → 大盘"""
        self.assertEqual(_market_cap_to_size(1000e8), "大盘")
        self.assertEqual(_market_cap_to_size(500e8), "大盘")

    def test_mid_cap(self):
        """100 ~ 500 亿 → 中盘"""
        self.assertEqual(_market_cap_to_size(300e8), "中盘")
        self.assertEqual(_market_cap_to_size(100e8), "中盘")

    def test_small_cap(self):
        """< 100 亿 → 小盘"""
        self.assertEqual(_market_cap_to_size(50e8), "小盘")
        self.assertEqual(_market_cap_to_size(1e8), "小盘")

    def test_zero(self):
        """0 → 未知"""
        self.assertEqual(_market_cap_to_size(0), "未知")


# ── _pe_to_style 测试 ────────────────────────────────────


class TestPeToStyle(unittest.TestCase):
    """_pe_to_style：PE→估值倾向"""

    def test_value_with_industry_avg(self):
        """PE < 行业均值的 70% → 价值"""
        self.assertEqual(_pe_to_style(10, 20), "价值")   # 10/20=0.5 < 0.7
        self.assertEqual(_pe_to_style(13, 20), "价值")   # 13/20=0.65 < 0.7

    def test_growth_with_industry_avg(self):
        """PE > 行业均值的 130% → 成长"""
        self.assertEqual(_pe_to_style(30, 20), "成长")   # 30/20=1.5 > 1.3
        self.assertEqual(_pe_to_style(26, 20), "成长")   # 26/20=1.3

    def test_blend_with_industry_avg(self):
        """PE 在中间范围 → 混合"""
        self.assertEqual(_pe_to_style(20, 20), "混合")   # 20/20=1.0

    def test_no_industry_avg_absolute(self):
        """无行业平均 PE → 绝对值判定"""
        self.assertEqual(_pe_to_style(10, None), "价值")  # < 15
        self.assertEqual(_pe_to_style(40, None), "成长")  # > 30
        self.assertEqual(_pe_to_style(20, None), "混合")

    def test_negative_pe(self):
        """负 PE → 混合"""
        self.assertEqual(_pe_to_style(-5, 20), "混合")


# ── _estimate_style_by_code 测试 ──────────────────────────


class TestEstimateByCode(unittest.TestCase):
    """_estimate_style_by_code：代码段降级"""

    def test_60_start(self):
        """60xxxx → 大盘"""
        self.assertEqual(_get_size_from_code("600519"), "大盘")
        self.assertEqual(_get_size_from_code("601318"), "大盘")

    def test_000_start(self):
        """000xxx → 中盘"""
        self.assertEqual(_get_size_from_code("000858"), "中盘")

    def test_002_start(self):
        """002xxx → 中盘"""
        self.assertEqual(_get_size_from_code("002415"), "中盘")

    def test_300_start(self):
        """300xxx → 小盘"""
        self.assertEqual(_get_size_from_code("300750"), "小盘")

    def test_688_start(self):
        """688xxx → 小盘"""
        self.assertEqual(_get_size_from_code("688001"), "小盘")

    def test_unknown_code(self):
        """未知代码 → 其他"""
        self.assertEqual(_get_size_from_code(""), "其他")


# ── _grid_distance 测试 ──────────────────────────────────


class TestGridDistance(unittest.TestCase):
    """_grid_distance：网格距离"""

    def test_same_style(self):
        """相同风格 → 0"""
        self.assertEqual(_grid_distance("大盘成长", "大盘成长"), 0)

    def test_one_size_diff(self):
        """跨 1 格 → 1"""
        self.assertEqual(_grid_distance("大盘成长", "中盘成长"), 1)

    def test_one_style_diff(self):
        """跨 1 个风格 → 1"""
        self.assertEqual(_grid_distance("大盘成长", "大盘混合"), 1)

    def test_two_diff(self):
        """跨 3 格（size=1, style=2）→ 3"""
        self.assertEqual(_grid_distance("大盘成长", "中盘价值"), 3)

    def test_extreme_diff(self):
        """完全相反 → 4"""
        self.assertEqual(_grid_distance("大盘成长", "小盘价值"), 4)

    def test_dash_style(self):
        """"--" → 0"""
        self.assertEqual(_grid_distance("大盘成长", "--"), 0)


# ── _drift_level 测试 ──────────────────────────────────────


class TestDriftLevel(unittest.TestCase):
    """_drift_level：漂移等级"""

    def test_none(self):
        self.assertEqual(_drift_level(0), "无")

    def test_mild(self):
        self.assertEqual(_drift_level(1), "轻度")

    def test_moderate(self):
        self.assertEqual(_drift_level(2), "中度")

    def test_severe(self):
        self.assertEqual(_drift_level(3), "严重")
        self.assertEqual(_drift_level(4), "严重")


# ── _get_industry_avg_pe 测试 ──────────────────────────────


class TestGetIndustryAvgPe(unittest.TestCase):
    """_get_industry_avg_pe：行业平均 PE 计算"""

    def setUp(self):
        from src.python.provider_registry import get_registry
        get_registry().session_cache_clear("extended")

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_same_industry_median(self, mock_push2, mock_fetch_ind):
        """同行业多只 → 中位数作为行业平均 PE"""
        mock_fetch_ind.side_effect = lambda c: {"600519": {"industry": "白酒"}, "000858": {"industry": "白酒"}, "000568": {"industry": "白酒"}}.get(c)
        mock_push2.side_effect = lambda c: {
            "600519": {"market_cap": 2e12, "pe": 25.0},
            "000858": {"market_cap": 5e11, "pe": 15.0},
            "000568": {"market_cap": 3e11, "pe": 35.0},
        }.get(c)

        result = _get_industry_avg_pe(["600519", "000858", "000568"])
        # 排序 PE: [15, 25, 35] → 中位数 = 25.0
        self.assertAlmostEqual(result.get("600519", 0), 25.0, places=4)
        self.assertAlmostEqual(result.get("000858", 0), 25.0, places=4)
        self.assertAlmostEqual(result.get("000568", 0), 25.0, places=4)

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_different_industries(self, mock_push2, mock_fetch_ind):
        """不同行业 → 各自独立计算"""
        mock_fetch_ind.side_effect = lambda c: {"600519": {"industry": "白酒"}, "300750": {"industry": "电池"}, "002594": {"industry": "电池"}}.get(c)
        mock_push2.side_effect = lambda c: {
            "600519": {"market_cap": 2e12, "pe": 25.0},
            "300750": {"market_cap": 8e11, "pe": 40.0},
            "002594": {"market_cap": 7e11, "pe": 20.0},
        }.get(c)

        result = _get_industry_avg_pe(["600519", "300750", "002594"])
        self.assertAlmostEqual(result.get("600519", 0), 25.0, places=4)  # 白酒=25
        self.assertAlmostEqual(result.get("300750", 0), 30.0, places=4)  # 电池 median(20,40)=30
        self.assertAlmostEqual(result.get("002594", 0), 30.0, places=4)

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_all_fail(self, mock_push2, mock_fetch_ind):
        """全部失败 → 空字典"""
        mock_fetch_ind.return_value = None
        mock_push2.return_value = None

        result = _get_industry_avg_pe(["600519", "000858"])
        self.assertEqual(result, {})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_partial_failure(self, mock_push2, mock_fetch_ind):
        """部分失败 → 有数据的正常计算"""
        def _industry_side(code):
            return {"industry": "白酒"} if code == "600519" else {"industry": "电池"} if code == "300750" else None
        mock_fetch_ind.side_effect = _industry_side
        mock_push2.side_effect = lambda c: {
            "600519": {"market_cap": 2e12, "pe": 25.0},
            "300750": {"market_cap": 8e11, "pe": 30.0},
        }.get(c)

        result = _get_industry_avg_pe(["600519", "000858", "300750"])
        # 600519 → 白酒 PE=25; 000858 无行业→跳过; 300750 → 电池 PE=30
        self.assertIn("600519", result)
        self.assertNotIn("000858", result)
        self.assertIn("300750", result)
        self.assertAlmostEqual(result["600519"], 25.0, places=4)
        self.assertAlmostEqual(result["300750"], 30.0, places=4)

    def test_empty_codes(self):
        """空列表 → 空字典"""
        self.assertEqual(_get_industry_avg_pe([]), {})

    def test_non_a_share_codes(self):
        """非 A 股代码 → 跳过"""
        # 港股/美股/基金代码不发起 push2 请求
        result = _get_industry_avg_pe(["00700", "AAPL", "110011"])
        self.assertEqual(result, {})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_even_count_median(self, mock_push2, mock_fetch_ind):
        """偶数只股票 → 中位数取中间两数平均值"""
        mock_fetch_ind.return_value = {"industry": "白酒"}
        mock_push2.side_effect = lambda c: {
            "600519": {"market_cap": 2e12, "pe": 20.0},
            "000858": {"market_cap": 5e11, "pe": 30.0},
            "000568": {"market_cap": 3e11, "pe": 10.0},
            "600809": {"market_cap": 4e11, "pe": 40.0},
        }.get(c)

        result = _get_industry_avg_pe(["600519", "000858", "000568", "600809"])
        # 排序 PE: [10, 20, 30, 40] → 中位数 = (20+30)/2 = 25.0
        self.assertAlmostEqual(result.get("600519", 0), 25.0, places=4)

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_session_cache_filled(self, mock_push2, mock_fetch_ind):
        """验证 registry session_cache 被填充，主循环复用"""
        mock_fetch_ind.side_effect = lambda c: {"600519": {"industry": "白酒"}, "000858": {"industry": "白酒"}}.get(c)
        push2_data = {
            "600519": {"market_cap": 2e12, "pe": 25.0},
            "000858": {"market_cap": 5e11, "pe": 15.0},
        }

        from src.python.provider_registry import get_registry

        def _push2_with_memo(code):
            val = push2_data.get(code)
            if val is not None:
                get_registry().session_cache_set("extended", code, val)
            return val

        mock_push2.side_effect = _push2_with_memo

        _ = _get_industry_avg_pe(["600519", "000858"])
        # _push2_extended 已填充 registry session_cache（通过 side_effect 模拟）
        self.assertTrue(get_registry().session_cache_contains("extended", "600519"))
        self.assertTrue(get_registry().session_cache_contains("extended", "000858"))

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_negative_pe_skipped(self, mock_push2, mock_fetch_ind):
        """负 PE / 零 PE 不参与行业平均计算"""
        mock_fetch_ind.side_effect = lambda c: {"600519": {"industry": "白酒"}, "000858": {"industry": "白酒"}}.get(c)
        mock_push2.side_effect = lambda c: {
            "600519": {"market_cap": 2e12, "pe": 25.0},
            "000858": {"market_cap": 5e11, "pe": -5.0},  # 负 PE，应跳过
        }.get(c)

        result = _get_industry_avg_pe(["600519", "000858"])
        # 000858 负PE被跳过，仅 600519 → 行业平均=25
        self.assertIn("600519", result)
        self.assertNotIn("000858", result)  # 负PE不参与计算，也不返回
        self.assertAlmostEqual(result["600519"], 25.0, places=4)


# ── classify_fund_style 测试 ──────────────────────────────


class TestClassifyFundStyle(unittest.TestCase):
    """classify_fund_style：基金风格判定"""

    def setUp(self):
        """每个测试前清除 registry session_cache（extended 域），避免跨测试污染。"""
        from src.python.provider_registry import get_registry
        get_registry().session_cache_clear("extended")

    def test_empty_holdings(self):
        """空持仓 → '--'"""
        result = classify_fund_style("110011", [])
        self.assertEqual(result["style"], "--")

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._tencent_extended")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_no_push2_fallback_code(self, mock_push2, mock_tencent, mock_fetch_ind):
        """push2 不可用 → 代码段降级"""
        mock_push2.return_value = None
        mock_tencent.return_value = None
        mock_fetch_ind.return_value = None  # 行业数据不可用，纯代码段判定
        # 60开头 → 大盘
        holdings = [{"name": "茅台", "code": "600519", "ratio": 100}]
        result = classify_fund_style("110011", holdings)
        self.assertEqual(result["style"], "大盘混合")
        self.assertTrue(result["is_estimated"])

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._tencent_extended")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_push2_fallback_to_tencent(self, mock_push2, mock_tencent, mock_fetch_ind):
        """push2 不可用，Tencent 可用 → 使用 Tencent 数据"""
        mock_push2.return_value = None
        mock_tencent.return_value = {"market_cap": 1000e8, "pe": 25.0}
        mock_fetch_ind.return_value = None
        holdings = [{"name": "茅台", "code": "600519", "ratio": 100}]
        result = classify_fund_style("110011", holdings)
        self.assertIn("大盘", result["style"])
        # Tencent 数据视为精确（非降级）
        self.assertFalse(result["is_estimated"])

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_with_push2_data(self, mock_push2, mock_fetch_ind):
        """push2 可用 → 精确风格"""
        mock_push2.return_value = {"market_cap": 1000e8, "pe": 25.0}
        mock_fetch_ind.return_value = None
        holdings = [{"name": "茅台", "code": "600519", "ratio": 100}]
        result = classify_fund_style("110011", holdings)
        self.assertIn("大盘", result["style"])
        self.assertFalse(result["is_estimated"])

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._tencent_extended")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_industry_avg_affects_style(self, mock_push2, mock_tencent, mock_fetch_ind):
        """行业平均 PE 影响风格判定 — 同一行业不同PE→价值/成长区分"""
        mock_tencent.return_value = None
        mock_fetch_ind.return_value = {"industry": "白酒"}  # 全部同一行业

        def push2_side(code):
            data = {
                "600519": {"market_cap": 2e12, "pe": 16.0},  # 低PE
                "000858": {"market_cap": 5e11, "pe": 44.0},  # 高PE
            }
            return data.get(code)
        mock_push2.side_effect = push2_side

        holdings = [
            {"name": "茅台", "code": "600519", "ratio": 50},
            {"name": "五粮液", "code": "000858", "ratio": 50},
        ]
        result = classify_fund_style("110011", holdings)
        # 行业平均 PE = median(16, 44) = 30
        # 茅台: 16/30 = 0.53 → 价值
        # 五粮液: 44/30 = 1.47 → 成长
        details = {d["code"]: d for d in result["details"]}
        self.assertEqual(details["600519"]["style"], "价值")
        self.assertEqual(details["000858"]["style"], "成长")
        self.assertFalse(details["600519"]["is_estimated"])
        self.assertFalse(details["000858"]["is_estimated"])

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    def test_weighted_style(self, mock_push2, mock_fetch_ind):
        """多只持仓加权 → 按权重最大的 size 和 style 输出"""
        mock_fetch_ind.return_value = None
        def side_effect(code):
            if code == "600519":
                return {"market_cap": 1000e8, "pe": 25.0}   # 大盘混合
            elif code == "300750":
                return {"market_cap": 50e8, "pe": 50.0}     # 小盘成长
            return None
        mock_push2.side_effect = side_effect

        holdings = [
            {"name": "茅台", "code": "600519", "ratio": 60},
            {"name": "宁德", "code": "300750", "ratio": 40},
        ]
        result = classify_fund_style("110011", holdings)
        # 大盘(60) + 小盘(40) → 大盘（dominant）
        # 混合(60) + 成长(40) → 混合（dominant）
        self.assertEqual(result["style"], "大盘混合")
        self.assertFalse(result["is_estimated"])


# ── analyze_style_for_all_funds 测试 ─────────────────────


class TestAnalyzeStyleForAllFunds(unittest.TestCase):
    """analyze_style_for_all_funds：全流程集成"""

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._tencent_extended")
    @patch("src.python.report.fund_style_classify._push2_extended")
    @patch("src.python.report.fund_style_report._load_snapshot")
    def test_first_run_all_baseline(self, mock_load, mock_push2, mock_tencent, mock_fetch_ind):
        """首次运行 → 全部基准确立中"""
        mock_load.return_value = None
        mock_push2.return_value = None  # 降级模式
        mock_tencent.return_value = None
        mock_fetch_ind.return_value = None
        fund_holdings = {
            "110011": {
                "name": "易方达中小盘",
                "holdings": [{"name": "茅台", "code": "600519", "ratio": 100}],
            },
        }
        result = analyze_style_for_all_funds(fund_holdings)
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["results"][0]["is_first_check"])
        self.assertEqual(result["results"][0]["drift_level"], "基准确立中")

    @patch("src.python.fetcher.industry.fetch_industry_data")
    @patch("src.python.report.fund_style_classify._push2_extended")
    @patch("src.python.report.fund_style_report._load_snapshot")
    def test_drift_detected(self, mock_load, mock_push2, mock_fetch_ind):
        """有快照且风格变化 → 漂移检测"""
        mock_load.return_value = {
            "110011": {"style": "大盘成长", "check_date": "2026-06-01"},
        }
        mock_push2.return_value = {"market_cap": 50e8, "pe": 50.0}  # 小盘成长
        mock_fetch_ind.return_value = None
        fund_holdings = {
            "110011": {
                "name": "易方达中小盘",
                "holdings": [{"name": "某小盘股", "code": "300001", "ratio": 100}],
            },
        }
        result = analyze_style_for_all_funds(fund_holdings)
        self.assertEqual(len(result["results"]), 1)
        r = result["results"][0]
        self.assertFalse(r["is_first_check"])
        # 大盘成长→小盘成长: size差2格, style差0格 → 距离=2 → 中度
        self.assertEqual(r["drift_level"], "中度")
        self.assertEqual(r["drift_score"], 2)

    def test_no_holdings_returns_empty(self):
        """无持仓 → 空结果"""
        result = analyze_style_for_all_funds({})
        self.assertEqual(result["results"], [])


# ═══════════════════════════════════════════════════════════════
#  _push2_extended / _tencent_extended 文件缓存共享
# ═══════════════════════════════════════════════════════════════


class TestExtendedCacheSharing(unittest.TestCase):
    """_push2_extended / _tencent_extended 共享文件缓存（key=extended_{code}）。

    验证：
      - 一个函数写入缓存后，另一个函数读取缓存而非重复调用 API
      - 缓存键兼容性
    """

    def setUp(self):
        """清除文件缓存中 extended_ 前缀的条目。"""
        from src.python.cache import clear_by_prefix
        clear_by_prefix("extended_")

    @patch("src.python.fetcher.price.fetch_market_data")
    @patch("src.python.fetcher.industry.make_push2_request")
    def test_push2_writes_tencent_reads(
        self, mock_push2_api, mock_tencent_api,
    ):
        """push2 写入缓存 → tencent 读取缓存（不调用 tencent API）"""
        # push2 成功返回数据（f20=总市值, f9=PE），写入缓存
        mock_push2_api.return_value = {"f20": 1e11, "f9": 25.0}
        mock_tencent_api.return_value = None  # 不应被调用

        from src.python.report.fund_style_classify import _push2_extended, _tencent_extended

        # 第一次调用：push2 API 被调用，写入缓存
        result1 = _push2_extended("600519")
        self.assertIsNotNone(result1)
        self.assertAlmostEqual(result1["market_cap"], 1e11)
        self.assertAlmostEqual(result1["pe"], 25.0)

        # 第二次调用：tencent 应命中同一缓存，不调用 tencent API
        result2 = _tencent_extended("600519")
        self.assertIsNotNone(result2)
        self.assertAlmostEqual(result2["market_cap"], 1e11)
        self.assertAlmostEqual(result2["pe"], 25.0)
        # tencent 数据源不应被调用（缓存命中）
        mock_tencent_api.assert_not_called()

    @patch("src.python.fetcher.price.fetch_market_data")
    @patch("src.python.fetcher.industry.make_push2_request")
    def test_tencent_writes_push2_reads(
        self, mock_push2_api, mock_tencent_api,
    ):
        """tencent 写入缓存 → push2 读取缓存（不调用 push2 API）"""
        mock_push2_api.return_value = None  # 不应被调用
        # Tencent 返回 market_cap 单位为亿，函数内部乘以 1e8 转为元
        mock_tencent_api.return_value = {"market_cap": 2000.0, "pe": 30.0}

        from src.python.report.fund_style_classify import _push2_extended, _tencent_extended

        # 第一次调用：tencent API 被调用，写入缓存（2000亿 → 2e11 元）
        result1 = _tencent_extended("600519")
        self.assertIsNotNone(result1)
        self.assertAlmostEqual(result1["market_cap"], 2e11)

        # 第二次调用：push2 应命中同一缓存，不调用 push2 API
        result2 = _push2_extended("600519")
        self.assertIsNotNone(result2)
        self.assertAlmostEqual(result2["market_cap"], 2e11)
        mock_push2_api.assert_not_called()

    @patch("src.python.fetcher.price.fetch_market_data")
    @patch("src.python.fetcher.industry.make_push2_request")
    def test_different_code_no_cache_interference(
        self, mock_push2_api, mock_tencent_api,
    ):
        """不同代码的缓存互不干扰。"""
        mock_push2_api.side_effect = lambda c: {
            "600519": {"f20": 1e11, "f9": 25.0},
            "000858": {"f20": 5e10, "f9": 15.0},
        }.get(c)

        from src.python.report.fund_style_classify import _push2_extended

        _push2_extended("600519")
        _push2_extended("000858")

        from src.python.report.fund_style_classify import _tencent_extended

        r1 = _tencent_extended("600519")
        self.assertIsNotNone(r1)
        self.assertAlmostEqual(r1["market_cap"], 1e11)

        r2 = _tencent_extended("000858")
        self.assertIsNotNone(r2)
        self.assertAlmostEqual(r2["market_cap"], 5e10)

        # tencent 数据源全程未实际调用（缓存命中）
        mock_tencent_api.assert_not_called()

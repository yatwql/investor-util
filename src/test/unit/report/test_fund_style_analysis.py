"""report/fund_style_analysis.py 单元测试。

测试目标：
  - _market_cap_to_size：市值→规模
  - _pe_to_style：PE→估值倾向
  - _estimate_style_by_code：代码段降级
  - _classify_stock：综合判定
  - classify_fund_style：基金风格
  - _grid_distance：网格距离
  - _drift_level：漂移等级
  - analyze_style_for_all_funds：全流程

场景覆盖：
  1. 市值阈值（大盘/中盘/小盘）
  2. PE vs 行业平均 PE 判定
  3. 代码段降级
  4. 基金风格加权
  5. 有/无 push2 数据
  6. 网格距离
  7. 漂移检测
  8. 首检/基线/严重漂移

运行：
  pytest src/test/ -m "unit_report" -k "fund_style" -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.report.fund_style_analysis import (
    _drift_level,
    _estimate_style_by_code,
    _get_size_from_code,
    _grid_distance,
    _market_cap_to_size,
    _pe_to_style,
    analyze_style_for_all_funds,
    classify_fund_style,
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


# ── classify_fund_style 测试 ──────────────────────────────


class TestClassifyFundStyle(unittest.TestCase):
    """classify_fund_style：基金风格判定"""

    def test_empty_holdings(self):
        """空持仓 → '--'"""
        result = classify_fund_style("110011", [])
        self.assertEqual(result["style"], "--")

    @patch("src.python.report.fund_style_analysis._push2_extended")
    def test_no_push2_fallback_code(self, mock_push2):
        """push2 不可用 → 代码段降级"""
        mock_push2.return_value = None
        # 60开头 → 大盘
        holdings = [{"name": "茅台", "code": "600519", "ratio": 100}]
        result = classify_fund_style("110011", holdings)
        self.assertEqual(result["style"], "大盘混合")
        self.assertTrue(result["is_estimated"])

    @patch("src.python.report.fund_style_analysis._push2_extended")
    def test_with_push2_data(self, mock_push2):
        """push2 可用 → 精确风格"""
        mock_push2.return_value = {"market_cap": 1000e8, "pe": 25.0}
        holdings = [{"name": "茅台", "code": "600519", "ratio": 100}]
        result = classify_fund_style("110011", holdings)
        self.assertIn("大盘", result["style"])
        self.assertFalse(result["is_estimated"])

    @patch("src.python.report.fund_style_analysis._push2_extended")
    def test_weighted_style(self, mock_push2):
        """多只持仓加权 → 按权重最大的 size 和 style 输出"""
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

    @patch("src.python.report.fund_style_analysis._push2_extended")
    @patch("src.python.report.fund_style_analysis._load_snapshot")
    def test_first_run_all_baseline(self, mock_load, mock_push2):
        """首次运行 → 全部基准确立中"""
        mock_load.return_value = None
        mock_push2.return_value = None  # 降级模式
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

    @patch("src.python.report.fund_style_analysis._push2_extended")
    @patch("src.python.report.fund_style_analysis._load_snapshot")
    def test_drift_detected(self, mock_load, mock_push2):
        """有快照且风格变化 → 漂移检测"""
        mock_load.return_value = {
            "110011": {"style": "大盘成长", "check_date": "2026-06-01"},
        }
        mock_push2.return_value = {"market_cap": 50e8, "pe": 50.0}  # 小盘成长
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

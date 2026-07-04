"""report/fund_concentration.py 单元测试。

测试目标：
  - compute_concentration：集中度计算、环比变化、预警、首检
  - _calc_alert_level：预警级别判定
  - 快照读写

场景覆盖：
  1. top3/5/10 占比正确计算
  2. 环比变化 + 预警
  3. 集中度 > 80% 预警
  4. 首次运行标记
  5. 快照读写
  6. 空输入

运行：
  pytest src/test/ -m "unit_report" -k "fund_concentration" -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.report.fund_concentration import (
    _calc_alert_level,
    _load_history_snapshot,
    _save_history_snapshot,
    compute_concentration,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ── _calc_alert_level 测试 ─────────────────────────────────


class TestCalcAlertLevel(unittest.TestCase):
    """_calc_alert_level：预警级别判定"""

    def test_emergency_change_gt_20(self):
        """环比变化 > 20% → 紧急"""
        self.assertEqual(_calc_alert_level(50.0, 25.0), "紧急")
        self.assertEqual(_calc_alert_level(30.0, 21.0), "紧急")

    def test_warning_change_gt_10(self):
        """环比变化 > 10% → 关注"""
        self.assertEqual(_calc_alert_level(50.0, 15.0), "关注")
        self.assertEqual(_calc_alert_level(30.0, 11.0), "关注")

    def test_warning_high_concentration(self):
        """当前集中度 > 80% → 关注"""
        self.assertEqual(_calc_alert_level(85.0, None), "关注")
        self.assertEqual(_calc_alert_level(81.0, 5.0), "关注")

    def test_normal_no_issue(self):
        """无问题 → 正常"""
        self.assertEqual(_calc_alert_level(50.0, 5.0), "正常")
        self.assertEqual(_calc_alert_level(70.0, 8.0), "正常")


# ── compute_concentration 测试 ──────────────────────────


class TestComputeConcentration(unittest.TestCase):
    """compute_concentration：集中度计算"""

    def setUp(self):
        self.three_funds = {
            "110011": {
                "name": "易方达中小盘混合",
                "holdings": [
                    {"name": "茅台", "code": "600519", "ratio": 9.5},
                    {"name": "五粮液", "code": "000858", "ratio": 8.0},
                    {"name": "泸州老窖", "code": "000568", "ratio": 7.0},
                    {"name": "美的", "code": "000333", "ratio": 6.0},
                    {"name": "格力", "code": "000651", "ratio": 5.0},
                ],
            },
        }
        # top3 = 9.5+8+7 = 24.5
        # top5 = 9.5+8+7+6+5 = 35.5
        # top10 = 35.5 (仅5只持仓)

    @patch("src.python.report.fund_concentration._load_history_snapshot")
    def test_top3_top5_top10_values(self, mock_load):
        """top3/5/10 占比计算正确"""
        mock_load.return_value = None
        result = compute_concentration(self.three_funds)
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertAlmostEqual(item["top3_pct"], 24.5)
        self.assertAlmostEqual(item["top5_pct"], 35.5)
        self.assertAlmostEqual(item["top10_pct"], 35.5)
        self.assertEqual(item["holding_count"], 5)

    @patch("src.python.report.fund_concentration._load_history_snapshot")
    def test_first_run_flag(self, mock_load):
        """首次运行 → is_first_check=True"""
        mock_load.return_value = None
        result = compute_concentration(self.three_funds)
        self.assertTrue(result[0]["is_first_check"])

    @patch("src.python.report.fund_concentration._load_history_snapshot")
    def test_first_run_prev_none(self, mock_load):
        """首次运行 → prev_top10_pct=None, change_pct=None"""
        mock_load.return_value = None
        result = compute_concentration(self.three_funds)
        self.assertIsNone(result[0]["prev_top10_pct"])
        self.assertIsNone(result[0]["change_pct"])

    @patch("src.python.report.fund_concentration._load_history_snapshot")
    def test_second_run_with_snapshot(self, mock_load):
        """第二次运行有快照 → 环比变化正确"""
        mock_load.return_value = {
            "110011": {"top10_pct": 30.0, "check_date": "2026-06-01"},
        }
        result = compute_concentration(self.three_funds)
        self.assertFalse(result[0]["is_first_check"])
        self.assertAlmostEqual(result[0]["prev_top10_pct"], 30.0)
        self.assertAlmostEqual(result[0]["change_pct"], 5.5)  # 35.5 - 30.0

    @patch("src.python.report.fund_concentration._load_history_snapshot")
    def test_concentration_gt_80_alert(self, mock_load):
        """集中度 > 80% 且环比变化不超阈值 → 关注"""
        # prev_top10 = 80, change = 85-80 = 5 (<10), 但当前85>80 → 关注
        mock_load.return_value = {
            "110011": {"top10_pct": 80.0, "check_date": "2026-06-01"},
        }
        high_conc = {
            "110011": {
                "name": "集中基金",
                "holdings": [
                    {"name": "A", "code": "000001", "ratio": 30.0},
                    {"name": "B", "code": "000002", "ratio": 25.0},
                    {"name": "C", "code": "000003", "ratio": 20.0},
                    {"name": "D", "code": "000004", "ratio": 10.0},
                ],
            },
        }
        # top10 = 85 > 80 → 关注
        result = compute_concentration(high_conc)
        self.assertEqual(result[0]["alert_level"], "关注")

    @patch("src.python.report.fund_concentration._load_history_snapshot")
    def test_change_gt_20_emergency(self, mock_load):
        """环比 > 20% → 紧急"""
        mock_load.return_value = {
            "110011": {"top10_pct": 10.0, "check_date": "2026-06-01"},
        }
        result = compute_concentration(self.three_funds)
        # change_pct = 35.5 - 10.0 = 25.5 > 20
        self.assertEqual(result[0]["alert_level"], "紧急")

    @patch("src.python.report.fund_concentration._load_history_snapshot")
    def test_empty_input(self, mock_load):
        """空输入 → 空列表"""
        mock_load.return_value = None
        result = compute_concentration({})
        self.assertEqual(result, [])

    @patch("src.python.report.fund_concentration._load_history_snapshot")
    def test_empty_holdings(self, mock_load):
        """持仓为空 → 跳过"""
        mock_load.return_value = None
        result = compute_concentration({
            "110011": {"name": "基金", "holdings": []},
        })
        self.assertEqual(result, [])


# ── 快照读写测试 ──────────────────────────────────────


class TestSnapshot(unittest.TestCase):
    """_load_history_snapshot / _save_history_snapshot：快照读写"""

    @patch("src.python.report.fund_concentration.cache_get")
    def test_load_first_run(self, mock_get):
        """首次运行无快照 → None"""
        mock_get.return_value = None
        result = _load_history_snapshot()
        self.assertIsNone(result)

    @patch("src.python.report.fund_concentration.cache_get")
    def test_load_has_data(self, mock_get):
        """有历史快照 → 返回数据"""
        expected = {"110011": {"top10_pct": 35.0, "check_date": "2026-06-01"}}
        mock_get.return_value = expected
        result = _load_history_snapshot()
        self.assertEqual(result, expected)

    @patch("src.python.report.fund_concentration.cache_set")
    def test_save_snapshot(self, mock_set):
        """保存快照"""
        data = [{"code": "110011", "top3_pct": 24.5, "top5_pct": 35.5, "top10_pct": 35.5}]
        _save_history_snapshot(data)
        mock_set.assert_called_once()
        args, _ = mock_set.call_args
        self.assertEqual(args[0], "fund_concentration_snapshot")
        self.assertIn("110011", args[1])
        self.assertAlmostEqual(args[1]["110011"]["top10_pct"], 35.5)

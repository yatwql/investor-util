"""report/fund_manager_analysis.py 单元测试。

测试目标：
  - detect_manager_changes：变更检测、预警级别、首检、无基金持仓
  - _load_snapshot / _update_snapshot：快照读写
  - build_first_check_summary：引导文案生成
  - 基金筛选使用 _is_fund（考虑账户上下文）

场景覆盖：
  1. 首次运行（无快照）→ 全部首检
  2. 经理未变更 → 全部正常
  3. 经理已变更（1月内）→ 🔴 紧急
  4. 经理已变更（3月内）→ ⚠️ 关注
  5. 无基金持仓 → 空列表
  6. 经理信息获取失败 → 显示"--"
  7. build_first_check_summary 文案正确

运行：
  pytest src/test/ -m "unit_report" -k "fund_manager_analysis" -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.fetcher.fund_manager import fetch_fund_manager
from src.python.report.fund_manager_analysis import (
    _calc_alert_level,
    _load_snapshot,
    _update_snapshot,
    build_first_check_summary,
    detect_manager_changes,
)
from src.python.models import Holding

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _make_holding(code: str, name: str, account: str = "测试账户") -> Holding:
    """构造测试用 Holding 对象。"""
    return Holding(
        account=account, name=name, code=code,
        shares=1000, cost_price=1.0,
    )


# ── _calc_alert_level 测试 ─────────────────────────────────


class TestCalcAlertLevel(unittest.TestCase):
    """_calc_alert_level：预警级别计算"""

    def test_emergency_1m(self):
        """1 月内变更 → 紧急"""
        self.assertEqual(_calc_alert_level(True, False, False), "紧急")
        self.assertEqual(_calc_alert_level(True, True, True), "紧急")

    def test_warning_3m(self):
        """3 月内变更 → 关注"""
        self.assertEqual(_calc_alert_level(False, True, False), "关注")
        self.assertEqual(_calc_alert_level(False, True, True), "关注")

    def test_warning_6m(self):
        """6 月内变更 → 关注"""
        self.assertEqual(_calc_alert_level(False, False, True), "关注")

    def test_normal_no_change(self):
        """无变更 → 正常"""
        self.assertEqual(_calc_alert_level(False, False, False), "正常")


# ── detect_manager_changes 测试 ──────────────────────────────


class TestDetectManagerChanges(unittest.TestCase):
    """detect_manager_changes：变更检测核心逻辑"""

    def setUp(self):
        self.fund_holdings = [
            _make_holding("110011", "易方达中小盘混合"),
            _make_holding("162605", "某主动基金"),
        ]
        self.stock_holding = _make_holding("600519", "贵州茅台")

    @patch("src.python.report.fund_manager_analysis.fetch_fund_manager")
    @patch("src.python.report.fund_manager_analysis._load_snapshot")
    def test_first_run_all_first_check(
        self, mock_snapshot: MagicMock, mock_manager: MagicMock,
    ):
        """首次运行（无快照）→ 全部标注首检。"""
        mock_snapshot.return_value = None  # 首次运行
        mock_manager.side_effect = lambda code: {
            "110011": {"manager_name": "张坤", "start_date": "2012-09-28", "tenure_days": 5000, "history": []},
            "162605": {"manager_name": "刘彦春", "start_date": "2019-04-15", "tenure_days": 2000, "history": []},
        }.get(code)

        results = detect_manager_changes(self.fund_holdings)

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertTrue(r["is_first_check"])
            self.assertEqual(r["alert_level"], "首检")

    @patch("src.python.report.fund_manager_analysis.fetch_fund_manager")
    @patch("src.python.report.fund_manager_analysis._load_snapshot")
    @patch("src.python.report.fund_manager_analysis._update_snapshot")
    def test_manager_unchanged_all_normal(
        self, mock_update: MagicMock, mock_snapshot: MagicMock, mock_manager: MagicMock,
    ):
        """经理未变更 → 全部正常。"""
        mock_snapshot.return_value = {
            "110011": {"manager_name": "张坤", "check_date": "2026-06-01"},
            "162605": {"manager_name": "刘彦春", "check_date": "2026-06-01"},
        }
        mock_manager.side_effect = lambda code: {
            "110011": {"manager_name": "张坤", "start_date": "2012-09-28", "tenure_days": 5000, "history": []},
            "162605": {"manager_name": "刘彦春", "start_date": "2019-04-15", "tenure_days": 2000, "history": []},
        }.get(code)

        results = detect_manager_changes(self.fund_holdings)

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertFalse(r["is_first_check"])
            self.assertEqual(r["alert_level"], "正常")

    @patch("src.python.report.fund_manager_analysis.fetch_fund_manager")
    @patch("src.python.report.fund_manager_analysis._load_snapshot")
    @patch("src.python.report.fund_manager_analysis._update_snapshot")
    def test_manager_changed_1m_emergency(
        self, mock_update: MagicMock, mock_snapshot: MagicMock, mock_manager: MagicMock,
    ):
        """经理变更（1 月内）→ 🔴 紧急。"""
        mock_snapshot.return_value = {
            "110011": {"manager_name": "张三", "check_date": "2026-05-01"},
        }
        # 当前经理为"李四"且 start_date 为最近（30 天内）
        import datetime
        recent_date = (datetime.datetime.now() - datetime.timedelta(days=15)).strftime("%Y-%m-%d")
        mock_manager.side_effect = lambda code: {
            "110011": {"manager_name": "李四", "start_date": recent_date, "tenure_days": 15, "history": []},
        }.get(code)

        results = detect_manager_changes(
            [_make_holding("110011", "易方达中小盘混合")]
        )

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertTrue(r["changed_1m"])
        self.assertEqual(r["alert_level"], "紧急")

    @patch("src.python.report.fund_manager_analysis.fetch_fund_manager")
    @patch("src.python.report.fund_manager_analysis._load_snapshot")
    @patch("src.python.report.fund_manager_analysis._update_snapshot")
    def test_manager_changed_3m_warning(
        self, mock_update: MagicMock, mock_snapshot: MagicMock, mock_manager: MagicMock,
    ):
        """经理变更（3 月内）→ ⚠️ 关注。"""
        mock_snapshot.return_value = {
            "110011": {"manager_name": "张三", "check_date": "2026-03-01"},
        }
        import datetime
        date_60d = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        mock_manager.side_effect = lambda code: {
            "110011": {"manager_name": "李四", "start_date": date_60d, "tenure_days": 60, "history": []},
        }.get(code)

        results = detect_manager_changes(
            [_make_holding("110011", "易方达中小盘混合")]
        )

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertFalse(r["changed_1m"])
        self.assertTrue(r["changed_3m"])
        self.assertEqual(r["alert_level"], "关注")

    @patch("src.python.report.fund_manager_analysis.fetch_fund_manager")
    def test_no_fund_holdings(self, mock_manager: MagicMock):
        """无基金持仓 → 空列表。"""
        results = detect_manager_changes([self.stock_holding])
        self.assertEqual(results, [])
        mock_manager.assert_not_called()

    @patch("src.python.report.fund_manager_analysis.fetch_fund_manager")
    @patch("src.python.report.fund_manager_analysis._load_snapshot")
    def test_manager_fetch_failed(
        self, mock_snapshot: MagicMock, mock_manager: MagicMock,
    ):
        """经理信息获取失败 → 显示"--"。"""
        mock_snapshot.return_value = {
            "110011": {"manager_name": "张坤", "check_date": "2026-06-01"},
        }
        mock_manager.return_value = None  # 获取失败

        results = detect_manager_changes(
            [_make_holding("110011", "易方达中小盘混合")]
        )

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["current_manager"], "--")
        self.assertEqual(r["start_date"], "--")


# ── build_first_check_summary 测试 ─────────────────────────


class TestBuildFirstCheckSummary(unittest.TestCase):
    """build_first_check_summary：首次运行引导文案"""

    def test_summary_text(self):
        """文案包含基金数和经理数。"""
        results = [
            {"current_manager": "张坤", "is_first_check": True},
            {"current_manager": "--", "is_first_check": True},
        ]
        text = build_first_check_summary(results)
        self.assertIn("2", text)  # 监控 2 只基金
        self.assertIn("1", text)  # 1 只有经理


# ── 快照读写测试 ──────────────────────────────────────────


class TestSnapshot(unittest.TestCase):
    """_load_snapshot / _update_snapshot：快照读写"""

    @patch("src.python.report.fund_manager_analysis.cache_get")
    def test_load_snapshot_first_run(self, mock_get: MagicMock):
        """首次运行无快照 → None。"""
        mock_get.return_value = None
        result = _load_snapshot()
        self.assertIsNone(result)

    @patch("src.python.report.fund_manager_analysis.cache_get")
    def test_load_snapshot_has_data(self, mock_get: MagicMock):
        """有历史快照时返回数据。"""
        expected = {"110011": {"manager_name": "张坤", "check_date": "2026-06-01"}}
        mock_get.return_value = expected
        result = _load_snapshot()
        self.assertEqual(result, expected)

    @patch("src.python.report.fund_manager_analysis.cache_set")
    def test_update_snapshot(self, mock_set: MagicMock):
        """更新快照。"""
        data = {"110011": {"manager_name": "张坤", "check_date": "2026-07-04"}}
        _update_snapshot(data)
        mock_set.assert_called_once_with("fund_manager_snapshot", data)

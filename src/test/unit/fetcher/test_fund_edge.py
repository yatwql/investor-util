"""fetcher/fund.py 联接基金穿透的边缘场景测试。

必须放在 *_edge.py 文件中（边缘测试文件隔离）。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.fetcher.fund import fetch_fund_holdings_batch, with_feeder_penetration

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher, pytest.mark.edge]


class TestWithFeederPenetrationEdge(unittest.TestCase):
    """with_feeder_penetration 异常/边界场景。"""

    def test_ok_false_lookalike_key(self):
        """``feeder_target_code`` 为空串（非法值）时不穿透。"""
        result = {"code": "016055", "name": "某基金", "holdings": [], "feeder_target_code": ""}
        self.assertIs(with_feeder_penetration("016055", result), result)

    @patch("src.python.fetcher.fund.fetch_fund_holdings_cached")
    def test_target_result_without_holdings_key(self, mock_cached):
        """目标结果缺 holdings 键（契约漂移）时不穿透，也不抛异常。"""
        mock_cached.return_value = {"code": "513390", "name": "纳指100ETF博时"}
        result = {"code": "016055", "name": "某联接", "holdings": [], "feeder_target_code": "513390"}
        self.assertNotIn("feeder_penetration", with_feeder_penetration("016055", result))

    @patch("src.python.fetcher.fund.fetch_fund_holdings_cached")
    def test_name_falls_back_to_target_name(self, mock_cached):
        """本基金名称缺失时用目标 ETF 名称兜底（避免报告层出现空名）。"""
        mock_cached.return_value = {
            "code": "513390",
            "name": "纳指100ETF博时",
            "date": "2026-06-30",
            "holdings": [{"name": "苹果"}],
        }
        result = {"code": "016055", "name": "", "holdings": [], "feeder_target_code": "513390"}

        merged = with_feeder_penetration("016055", result)

        self.assertEqual(merged["name"], "纳指100ETF博时")
        self.assertEqual(merged["code"], "016055")

    @patch("src.python.fetcher.fund.fetch_fund_holdings_cached")
    def test_target_raising_propagates_not_swallowed(self, mock_cached):
        """目标 ETF 取数抛异常时不吞异常（由既有降级/重试机制处理）。"""
        mock_cached.side_effect = RuntimeError("boom")
        result = {"code": "016055", "name": "某联接", "holdings": [], "feeder_target_code": "513390"}
        with self.assertRaises(RuntimeError):
            with_feeder_penetration("016055", result)

    @patch("src.python.fetcher.fund.fetch_fund_holdings_cached")
    def test_does_not_mutate_input(self, mock_cached):
        """不就地修改入参（幂等后处理须可安全重复调用）。"""
        mock_cached.return_value = {
            "code": "513390",
            "name": "纳指100ETF博时",
            "date": "2026-06-30",
            "holdings": [{"name": "苹果"}],
        }
        original = {"code": "016055", "name": "某联接", "holdings": [], "feeder_target_code": "513390"}

        with_feeder_penetration("016055", original)

        self.assertNotIn("feeder_penetration", original)
        self.assertEqual(original["holdings"], [])


class TestFetchFundHoldingsBatchEdge(unittest.TestCase):
    """fetch_fund_holdings_batch 穿透补做的边界场景。"""

    @patch("src.python.fetcher.fund.fetch_fund_holdings_cached")
    @patch("src.python.fetcher.batch.BatchDispatcher")
    def test_failed_task_penetration_is_noop(self, mock_dispatcher_cls, mock_cached):
        """失败项（result=None）不触发穿透取数。"""
        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = [
            type("R", (), {"success": False, "result": None, "error": "err"})(),
        ]
        mock_dispatcher_cls.return_value = mock_disp

        result = fetch_fund_holdings_batch(["016055"])

        self.assertIsNone(result["016055"])
        mock_cached.assert_not_called()

    @patch("src.python.fetcher.fund.fetch_fund_holdings_cached")
    @patch("src.python.fetcher.batch.BatchDispatcher")
    def test_non_feeder_entries_untouched(self, mock_dispatcher_cls, mock_cached):
        """混合批次：仅联接基金项被穿透，普通基金项原样返回。"""
        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = [
            type(
                "R",
                (),
                {
                    "success": True,
                    "result": {
                        "code": "110022",
                        "name": "易方达消费",
                        "date": "2026-06-30",
                        "holdings": [{"name": "贵州茅台"}],
                    },
                },
            )(),
            type(
                "R",
                (),
                {
                    "success": True,
                    "result": {"code": "016055", "name": "某联接", "holdings": [], "feeder_target_code": "513390"},
                },
            )(),
        ]
        mock_dispatcher_cls.return_value = mock_disp
        mock_cached.return_value = {
            "code": "513390",
            "name": "纳指100ETF博时",
            "date": "2026-06-30",
            "holdings": [{"name": "苹果"}],
        }

        result = fetch_fund_holdings_batch(["110022", "016055"])

        self.assertNotIn("feeder_penetration", result["110022"])
        self.assertEqual(result["016055"]["feeder_penetration"]["target_code"], "513390")
        self.assertEqual(mock_cached.call_count, 1)

    @patch("src.python.fetcher.fund.fetch_fund_holdings_cached")
    @patch("src.python.fetcher.batch.BatchDispatcher")
    def test_penetration_idempotent_when_result_already_merged(self, mock_dispatcher_cls, mock_cached):
        """任务已跑且已穿透的结果，在批量补做处不重复取数。"""
        mock_disp = MagicMock()
        mock_disp.execute_with_cache_check.return_value = [
            type(
                "R",
                (),
                {
                    "success": True,
                    "result": {
                        "code": "016055",
                        "name": "某联接",
                        "date": "2026-06-30",
                        "holdings": [{"name": "苹果"}],
                        "feeder_penetration": {"target_code": "513390", "target_name": "纳指100ETF博时"},
                    },
                },
            )(),
        ]
        mock_dispatcher_cls.return_value = mock_disp

        result = fetch_fund_holdings_batch(["016055"])

        self.assertEqual(result["016055"]["holdings"], [{"name": "苹果"}])
        mock_cached.assert_not_called()


if __name__ == "__main__":
    unittest.main()

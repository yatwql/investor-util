"""fund_roe_estimate 单元测试（基金重仓股 ROE 加权估算，阶段一：前十大重仓口径）。

覆盖：
  - weighted_roe 纯计算（空列表 / 加权平均 / 零占比剔除）
  - estimate_fund_roe_batch：正常估算、报告期陈旧闸门、持仓缺失、非 A 股过滤、
    无效占比过滤、ROE 缺失剔除、known_roe 命中免取数

运行：pytest src/test/unit/report/test_fund_roe_estimate.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.report.fund_roe_estimate import ESTIMATE_BASIS_TOP10, estimate_fund_roe_batch, weighted_roe

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_MOD = "src.python.report.fund_roe_estimate"


def _payload(holdings: list[dict], date: str = "2026-06-30") -> dict:
    return {"holdings": holdings, "date": date}


def _stock(code: str, ratio: float, name: str = "") -> dict:
    return {"code": code, "name": name or code, "ratio": ratio}


class TestWeightedRoe(unittest.TestCase):
    """weighted_roe — 重仓股 ROE 加权平均（纯计算）。"""

    def test_empty_returns_none(self):
        self.assertIsNone(weighted_roe([]))

    def test_weighted_average(self):
        # (50%×0.10 + 50%×0.20) / 100% = 0.15
        self.assertAlmostEqual(weighted_roe([(50.0, 0.10), (50.0, 0.20)]), 0.15)

    def test_zero_ratio_items_ignored(self):
        self.assertAlmostEqual(weighted_roe([(0.0, 0.99), (50.0, 0.10)]), 0.10)


class TestEstimateFundRoeBatch(unittest.TestCase):
    """estimate_fund_roe_batch — 基金层 ROE 估算编排（取数全部 mock）。"""

    def _run(self, fund_items, holdings_map, roe_map, known_roe=None, stale=False):
        with (
            patch("src.python.fetcher.fund.fetch_fund_holdings_batch", return_value=holdings_map),
            patch(f"{_MOD}._fetch_stock_roe_batch", return_value=roe_map) as mock_fetch,
            patch("src.python.report.holdings_freshness.is_stale_report", return_value=stale),
        ):
            result = estimate_fund_roe_batch(fund_items, known_roe=known_roe)
        return result, mock_fetch

    def test_basic_estimate(self):
        """正常估算：加权 ROE / 覆盖比例 / 口径与报告期字段齐全。"""
        holdings = [_stock("600519", 30.0), _stock("601398", 30.0)]
        result, _ = self._run(
            [{"code": "110022", "name": "易方达消费"}],
            {"110022": _payload(holdings)},
            {"600519": 0.10, "601398": 0.20},
        )
        est = result["110022"]
        self.assertAlmostEqual(est["roe"], 0.15)  # (30×0.10+30×0.20)/60
        self.assertEqual(est["covered_pct"], 60.0)
        self.assertEqual(est["top_n"], 2)
        self.assertEqual(est["basis"], ESTIMATE_BASIS_TOP10)
        self.assertEqual(est["report_period"], "2026-06-30")

    def test_known_roe_skips_fetch(self):
        """known_roe 全命中时不发起股票 ROE 取数。"""
        holdings = [_stock("600519", 30.0)]
        result, mock_fetch = self._run(
            [{"code": "110022", "name": "易方达消费"}],
            {"110022": _payload(holdings)},
            {},
            known_roe={"600519": 0.31},
        )
        self.assertAlmostEqual(result["110022"]["roe"], 0.31)
        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args[0][0], [])  # 需补取清单为空

    def test_stale_report_period_skipped(self):
        """持仓报告期陈旧的基金不参与估算（与穿透层同一时效闸门）。"""
        result, _ = self._run(
            [{"code": "110022", "name": "易方达消费"}],
            {"110022": _payload([_stock("600519", 30.0)])},
            {"600519": 0.31},
            stale=True,
        )
        self.assertEqual(result, {})

    def test_missing_holdings_absent(self):
        """持仓获取失败的基金不出现在结果中。"""
        result, _ = self._run([{"code": "110022", "name": "易方达消费"}], {"110022": None}, {})
        self.assertEqual(result, {})

    def test_non_a_share_codes_filtered(self):
        """非 A 股底层（港股/美股）不参与加权也不触发取数。"""
        holdings = [_stock("600519", 30.0), _stock("hk00700", 20.0), _stock("AAPL", 10.0)]
        result, mock_fetch = self._run(
            [{"code": "110022", "name": "易方达消费"}],
            {"110022": _payload(holdings)},
            {"600519": 0.30},
        )
        self.assertAlmostEqual(result["110022"]["roe"], 0.30)
        self.assertEqual(result["110022"]["covered_pct"], 30.0)
        self.assertEqual(mock_fetch.call_args[0][0], ["600519"])

    def test_invalid_ratio_filtered(self):
        """无效占比（≤0 或 >100）的持仓条目被剔除。"""
        holdings = [_stock("600519", 30.0), _stock("601398", 0.0), _stock("688981", 401.0)]
        result, _ = self._run(
            [{"code": "110022", "name": "易方达消费"}],
            {"110022": _payload(holdings)},
            {"600519": 0.25},
        )
        self.assertEqual(result["110022"]["top_n"], 1)
        self.assertAlmostEqual(result["110022"]["roe"], 0.25)

    def test_all_roe_missing_fund_absent(self):
        """全部重仓股都取不到 ROE 时该基金无估算值（不臆造）。"""
        result, _ = self._run(
            [{"code": "110022", "name": "易方达消费"}],
            {"110022": _payload([_stock("600519", 30.0)])},
            {},
        )
        self.assertEqual(result, {})

    def test_empty_fund_items(self):
        self.assertEqual(estimate_fund_roe_batch([]), {})


if __name__ == "__main__":
    unittest.main()

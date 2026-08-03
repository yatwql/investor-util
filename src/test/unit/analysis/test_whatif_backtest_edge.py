"""调仓 What-if 时序回测边缘场景测试 — 极端值/异常场景。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。

覆盖：
  - 未来生效日（返回 None，不抛出）
  - 单 bar（0 个交易日 → 数据不足降级）
  - 首值 0（锚点后移）
  - total_value=None 注入（锚点前 → 优雅跳过，不崩溃）
  - 极端涨跌（万倍跳涨 / 接近归零 → 不崩溃、序列可算）
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


def _bars(dates: list[str], values: list[float]) -> list[dict]:
    return [{"date": d, "total_value": v} for d, v in zip(dates, values)]


def _daily_dates(start: str, n: int) -> list[str]:
    d = datetime.strptime(start, "%Y-%m-%d").date()
    return [(d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


class TestWhatifBacktestEdge:
    """时序回测边缘场景。"""

    def test_future_date_none(self):
        """未来生效日 → compute_backtest_days 返回 None。"""
        from src.python.analysis.whatif_backtest import compute_backtest_days

        assert compute_backtest_days("2099-01-01") is None
        assert compute_backtest_days("2026-08-03", today=date(2026, 8, 3)) is None

    def test_single_bar_insufficient(self):
        """单 bar → 0 个交易日 → available=False 降级。"""
        from src.python.analysis.whatif_backtest import compute_backtest_metrics

        eff = "2026-07-01"
        res = compute_backtest_metrics(
            [{"date": eff, "total_value": 100.0}],
            [{"date": eff, "total_value": 100.0}],
            eff,
        )
        assert res["available"] is False
        assert res["status"] == "unavailable"
        assert "不足" in res["reason"]

    def test_first_value_zero_anchor_shifts(self):
        """首值 0 → 锚点后移到首个双方正值。"""
        from src.python.analysis.whatif_backtest import compute_backtest_metrics

        eff = "2026-07-01"
        dates = _daily_dates(eff, 25)
        base = _bars(dates, [0.0] + [100.0 + i for i in range(24)])
        cand = _bars(dates, [0.0] + [100.0 + 2 * i for i in range(24)])
        res = compute_backtest_metrics(base, cand, eff)
        assert res["available"] is True
        assert res["series"]["labels"][0] == dates[1]
        assert res["series"]["base"][0] == 100.0

    def test_none_injection_before_anchor(self):
        """首个日期 total_value=None → 锚点后移，不崩溃。"""
        from src.python.analysis.whatif_backtest import compute_backtest_metrics

        eff = "2026-07-01"
        dates = _daily_dates(eff, 25)
        base = [{"date": dates[0], "total_value": None}] + _bars(dates[1:], [101.0 + i for i in range(24)])
        cand = _bars(dates, [100.0 + 2 * i for i in range(25)])
        res = compute_backtest_metrics(base, cand, eff)
        assert res["available"] is True
        assert res["series"]["labels"][0] == dates[1]
        assert res["series"]["base"][0] == 100.0

    def test_extreme_moves_no_crash(self):
        """极端涨跌（万倍跳涨 / 接近归零）→ 不崩溃、序列可算。"""
        from src.python.analysis.whatif_backtest import compute_backtest_metrics

        eff = "2026-07-01"
        dates = _daily_dates(eff, 25)
        values = [100.0 + i for i in range(25)]
        values[10] = 100000.0  # 极端跳涨
        values[11] = 0.0001  # 接近归零
        base = _bars(dates, values)
        cand = _bars(dates, [100.0 + 2 * i for i in range(25)])
        res = compute_backtest_metrics(base, cand, eff)
        assert res["available"] is True
        assert len(res["series"]["base"]) == 25

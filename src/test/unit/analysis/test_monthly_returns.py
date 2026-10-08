"""月度收益日历聚合单元测试（analysis/monthly_returns.py）。

测试目标：
  - 月度收益算式（月末/上月末 − 1，百分数口径）
  - 窗口截取与首窗月真实基线、首月 inception 基线
  - 年分组 12 格结构（窗外月为空格）
  - 统计（胜/亏/平、最佳/最差、最长连亏）
  - 样本不足与脏数据降级（单日/空/非正值）
  - 双口径结构字段（as-if 现行 + realized 预留标签）

运行：
  pytest src/test/unit/analysis/test_monthly_returns.py -v
"""

from __future__ import annotations

import unittest

from src.python.analysis.monthly_returns import (
    CALIBER_AS_IF,
    CALIBER_LABELS,
    CALIBER_REALIZED,
    DEFAULT_WINDOW_MONTHS,
    aggregate_monthly_returns,
)
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


def _bar(date: str, value: float) -> dict:
    return {"date": date, "total_value": value}


def _bars_by_month(monthly: dict[str, float], day: str = "15") -> list[dict]:
    """{YYYY-MM: total_value} → 月末近似日频 bars（每月一根）。"""
    return [_bar(f"{ym}-{day}", value) for ym, value in sorted(monthly.items())]


class TestAggregateMonthlyReturns(unittest.TestCase):
    """月度收益聚合核心算式与结构。"""

    def test_month_over_month_return(self) -> None:
        """月度收益 = 月末/上月末 − 1（百分数）。"""
        bars = _bars_by_month({"2026-07": 100.0, "2026-08": 110.0, "2026-09": 99.0})
        result = aggregate_monthly_returns(bars)
        assert result["available"] is True
        cells = {c["key"]: c for y in result["years"] for c in y["cells"] if c["return_pct"] is not None}
        self.assertEqual(cells["2026-08"]["return_pct"], 10.0)
        self.assertAlmostEqual(cells["2026-09"]["return_pct"], -10.0, places=6)
        self.assertEqual(cells["2026-08"]["baseline"], "prev_month")

    def test_first_month_inception_baseline(self) -> None:
        """最早月无上月 → baseline=inception（以其首根 bar 为基线）。"""
        bars = [_bar("2026-08-01", 100.0), _bar("2026-08-31", 105.0), _bar("2026-09-30", 105.0)]
        result = aggregate_monthly_returns(bars)
        first = next(c for y in result["years"] for c in y["cells"] if c["key"] == "2026-08")
        self.assertEqual(first["baseline"], "inception")
        self.assertEqual(first["return_pct"], 5.0)

    def test_window_keeps_prev_month_baseline(self) -> None:
        """截窗只裁展示月，首窗月仍以上窗真实月末为基线。"""
        months = {f"2024-{m:02d}": 100.0 for m in range(1, 13)}
        months.update({f"2025-{m:02d}": 110.0 for m in range(1, 13)})
        bars = _bars_by_month(months)
        result = aggregate_monthly_returns(bars, window_months=2)
        keys = sorted(c["key"] for y in result["years"] for c in y["cells"] if c["return_pct"] is not None)
        self.assertEqual(keys, ["2025-11", "2025-12"])
        # 2025-11 基线 = 2025-10 月末 110（上窗真实值，非截窗伪基线）
        nov = next(c for y in result["years"] for c in y["cells"] if c["key"] == "2025-11")
        self.assertEqual(nov["return_pct"], 0.0)
        self.assertEqual(nov["baseline"], "prev_month")

    def test_years_grouping_full_twelve_cells(self) -> None:
        """每年恒 12 格；窗外/无样本月 return_pct=None。"""
        bars = _bars_by_month({"2025-11": 100.0, "2025-12": 101.0, "2026-01": 102.0})
        result = aggregate_monthly_returns(bars)
        self.assertEqual([y["year"] for y in result["years"]], [2025, 2026])
        for year in result["years"]:
            self.assertEqual([c["month"] for c in year["cells"]], list(range(1, 13)))
        y2025 = result["years"][0]
        self.assertIsNone(y2025["cells"][0]["return_pct"])  # 2025-01 窗外
        self.assertIsNotNone(y2025["cells"][10]["return_pct"])  # 2025-11

    def test_stats_up_down_flat_and_streak(self) -> None:
        """统计：胜/亏/平计数、最佳/最差月、最长连亏（平月打断）。"""
        bars = _bars_by_month(
            {
                "2026-01": 100.0,  # 01: 0%（首月 inception）flat
                "2026-02": 110.0,  # 02: +10.0 up
                "2026-03": 104.0,  # 03: −5.4545 down（最差）
                "2026-04": 99.0,  # 04: −4.8077 down → 2 连亏
                "2026-05": 99.0,  # 05: 0 flat（打断连亏）
                "2026-06": 94.0,  # 06: −5.0505 down
            }
        )
        stats = aggregate_monthly_returns(bars)["stats"]
        self.assertEqual((stats["up"], stats["down"], stats["flat"]), (1, 3, 2))
        self.assertEqual(stats["best"]["key"], "2026-02")
        self.assertEqual(stats["best"]["return_pct"], 10.0)
        self.assertEqual(stats["worst"]["key"], "2026-03")
        self.assertEqual(stats["worst"]["return_pct"], -5.4545)
        self.assertEqual(stats["max_down_streak"], {"end_key": "2026-04", "length": 2})

    def test_single_day_and_empty_unavailable(self) -> None:
        """单日样本 / 空输入 → available=False 且键集完整。"""
        for bars in ([], [_bar("2026-09-30", 100.0)]):
            result = aggregate_monthly_returns(bars)
            self.assertFalse(result["available"])
            self.assertEqual(result["years"], [])
            self.assertIsNone(result["stats"])
            self.assertEqual(result["months_total"], 0)
            self.assertIn("caliber_label", result)

    def test_dirty_values_skipped(self) -> None:
        """非正值/缺字段 bar 跳过，不产生 0 基线除零。"""
        bars = [
            _bar("2026-08-01", 100.0),
            {"date": "2026-08-15", "total_value": 0},
            {"date": "2026-08-20", "total_value": "bad"},
            _bar("2026-08-31", 102.0),
            _bar("2026-09-30", 102.0),
        ]
        result = aggregate_monthly_returns(bars)
        self.assertTrue(result["available"])
        aug = next(c for y in result["years"] for c in y["cells"] if c["key"] == "2026-08")
        self.assertEqual(aug["return_pct"], 2.0)

    def test_caliber_fields_and_reserved_label(self) -> None:
        """双口径结构：默认 as-if，realized 标签预留存在。"""
        bars = _bars_by_month({"2026-08": 100.0, "2026-09": 101.0})
        result = aggregate_monthly_returns(bars)
        self.assertEqual(result["caliber"], CALIBER_AS_IF)
        self.assertEqual(result["caliber_label"], CALIBER_LABELS[CALIBER_AS_IF])
        self.assertIn(CALIBER_REALIZED, CALIBER_LABELS)
        realized = aggregate_monthly_returns(bars, caliber=CALIBER_REALIZED)
        self.assertEqual(realized["caliber"], CALIBER_REALIZED)
        self.assertEqual(realized["caliber_label"], CALIBER_LABELS[CALIBER_REALIZED])

    def test_default_window_constant(self) -> None:
        """默认窗口为 24 个月（近 2 年日历）。"""
        self.assertEqual(DEFAULT_WINDOW_MONTHS, 24)


if __name__ == "__main__":
    unittest.main()

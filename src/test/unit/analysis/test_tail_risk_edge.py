"""尾部风险统计模块边缘场景测试 — 异常/极端值。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。

覆盖：
  - 零/负 total_value 跳过
  - 缺失 total_value / date 字段容错
  - 极大/极小量级数值
  - 样本数恰在下限边界（>=20 available / <20 unavailable）
  - 持平序列 / 单点序列
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]

from src.python.analysis.tail_risk import compute_tail_risk


def _bars(values: list[float], start: str = "2026-01-01") -> list[dict]:
    """从每日净值序列生成 bars（每日 +1 天）。"""
    from datetime import date, timedelta

    out: list[dict] = []
    d = date.fromisoformat(start)
    for v in values:
        out.append({"date": d.isoformat(), "total_value": float(v)})
        d += timedelta(days=1)
    return out


class TestInvalidValues:
    """非法 / 缺失字段容错。"""

    def test_zero_negative_values_skipped(self):
        """中间出现 0/负值 → 跳过（prev<=0 不产生收益），不崩溃。"""
        bars = [
            {"date": "2026-01-01", "total_value": 100.0},
            {"date": "2026-01-02", "total_value": 0.0},
            {"date": "2026-01-03", "total_value": -5.0},
            {"date": "2026-01-04", "total_value": 101.0},
        ] + [{"date": f"2026-01-{i:02d}", "total_value": 101.0 + i} for i in range(5, 30)]
        result = compute_tail_risk(bars)
        # 等效 [100, 101, 102, ...] 单调上涨 → 有充足样本、无损失日
        assert result["available"] is True
        assert result["var95"] == 0.0
        assert result["max_single_day_drop"] == 0.0

    def test_missing_total_value_skipped(self):
        """缺失 total_value 字段 → 相邻收益不成对、样本不足，不崩溃。"""
        bars = [
            {"date": "2026-01-01", "total_value": 100.0},
            {"date": "2026-01-02"},
            {"date": "2026-01-03", "total_value": 90.0},
            {"date": "2026-01-04", "total_value": 95.0},
        ]
        result = compute_tail_risk(bars)
        # 缺失日 curr=0 → 前后收益均被跳过，有效收益仅 90→95 一个
        assert result["available"] is False
        assert result["sample_size"] == 1

    def test_missing_date_no_crash(self):
        """缺失/非法 date 字段 → 日期字段为 None/空，不崩溃。"""
        bars = [{"date": "bad-date", "total_value": 100.0}, {"date": "2026-01-02", "total_value": 95.0}] + [
            {"date": f"2026-01-{i:02d}", "total_value": 96.0 + i} for i in range(3, 30)
        ]
        result = compute_tail_risk(bars)
        assert result["available"] is True
        assert result["consecutive_down_days"] == 1  # 首日跌幅

    def test_nan_total_value_skipped(self):
        """total_value 为 NaN → float() 后 prev 比较不产生收益，不崩溃。"""
        bars = [
            {"date": "2026-01-01", "total_value": float("nan")},
            {"date": "2026-01-02", "total_value": 100.0},
            {"date": "2026-01-03", "total_value": 101.0},
        ] + [{"date": f"2026-01-{i:02d}", "total_value": 101.0 + i} for i in range(4, 30)]
        result = compute_tail_risk(bars)
        assert result["available"] is True


class TestMagnitude:
    """极大幅值 / 极小量级数值。"""

    def test_large_magnitude_no_overflow(self):
        """1e12 量级净值 → 计算不溢出、指标正确。"""
        values = [1e12]
        values.append(values[-1] * 1.02)  # +2%
        values.append(values[-1] * 0.98)  # -2%（相对 +2% 后的水平）
        values += [values[-1] * 1.01 for _ in range(20)]  # 20 个 +1%
        result = compute_tail_risk(_bars(values))
        assert result["available"] is True
        assert result["max_single_day_drop"] == pytest.approx(2.0, abs=0.01)

    def test_tiny_returns_precision(self):
        """极小量级波动（1e-4 级）→ 指标计算不丢精度。"""
        returns = [0.0001, -0.0002, 0.0003, -0.0001] * 6  # 24 个
        from datetime import date, timedelta

        d = date.fromisoformat("2026-02-01")
        bars = [{"date": d.isoformat(), "total_value": 100.0}]
        d += timedelta(days=1)
        value = 100.0
        for r in returns:
            value *= 1.0 + r
            bars.append({"date": d.isoformat(), "total_value": value})
            d += timedelta(days=1)
        result = compute_tail_risk(bars)
        assert result["available"] is True
        assert result["var95"] >= 0.0
        assert result["var99"] >= result["var95"]


class TestBoundary:
    """样本数边界 / 序列形态边界。"""

    def test_exactly_min_sample_available(self):
        """日收益恰为下限 20 → available=True。"""
        values = [100.0]
        values += [values[-1] * (1.0 + 0.01) for _ in range(20)]
        result = compute_tail_risk(_bars(values))  # 21 个值 → 20 个收益
        assert result["available"] is True
        assert result["sample_size"] == 20

    def test_one_below_min_sample_unavailable(self):
        """日收益 19（恰差 1）→ available=False。"""
        values = [100.0]
        values += [values[-1] * (1.0 + 0.01) for _ in range(19)]
        result = compute_tail_risk(_bars(values))  # 20 个值 → 19 个收益
        assert result["available"] is False
        assert result["sample_size"] == 19

    def test_single_bar_unavailable(self):
        """单点序列 → 无收益、available=False。"""
        result = compute_tail_risk(_bars([100.0]))
        assert result["available"] is False
        assert result["sample_size"] == 0

    def test_flat_series_zero_metrics(self):
        """净值全持平 → 收益全 0、指标为 0、状态 none。"""
        result = compute_tail_risk(_bars([100.0] * 25))
        assert result["available"] is True
        assert result["var95"] == 0.0
        assert result["var99"] == 0.0
        assert result["max_single_day_drop"] == 0.0
        assert result["consecutive_down_days"] == 0
        assert result["recovery_state"] == "none"

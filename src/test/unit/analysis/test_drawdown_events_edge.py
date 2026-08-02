"""回撤事件提取模块边缘场景测试 — 异常/极端值。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。

覆盖：
  - 零/负 total_value 跳过
  - 缺失 total_value / date 字段容错
  - 非法日期不崩溃（时长回退 0）
  - 全部无效值 / 全 0
  - max_events=0 / min_depth_pct=0
  - 极大幅值数值
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]

from src.python.analysis.drawdown_events import (
    compute_recovery_times,
    extract_drawdown_events,
)


def _bars(values: list[float], start: str = "2026-01-01") -> list[dict]:
    """从每日净值序列生成 bars（每日 +1 天）。"""
    from datetime import date, timedelta

    out: list[dict] = []
    d = date.fromisoformat(start)
    for v in values:
        out.append({"date": d.isoformat(), "total_value": float(v)})
        d += timedelta(days=1)
    return out


class TestExtractDrawdownEventsEdge:
    """extract_drawdown_events 边缘场景。"""

    def test_zero_negative_values_skipped(self):
        """中间出现 0/负值 → 跳过，不影响其余净值处理。"""
        bars = [{"date": "2026-01-01", "total_value": 10.0},
                {"date": "2026-01-02", "total_value": 0.0},
                {"date": "2026-01-03", "total_value": -5.0},
                {"date": "2026-01-04", "total_value": 12.0}]
        # 等效 [10, 12] → 单调上涨，无事件
        assert extract_drawdown_events(bars) == []

    def test_all_invalid_values_no_events(self):
        """全部 total_value ≤ 0 → 无事件、不崩溃。"""
        bars = [{"date": "2026-01-01", "total_value": 0.0},
                {"date": "2026-01-02", "total_value": -1.0}]
        assert extract_drawdown_events(bars) == []

    def test_missing_total_value_skipped(self):
        """缺失 total_value 字段 → 按 0 跳过，不崩溃。"""
        bars = [{"date": "2026-01-01", "total_value": 100.0},
                {"date": "2026-01-02"},
                {"date": "2026-01-03", "total_value": 90.0}]
        events = extract_drawdown_events(bars)
        # 等效 [100, 90] → 单调下跌 → 1 个未恢复事件
        assert len(events) == 1
        assert events[0]["recovered"] is False

    def test_missing_date_no_crash(self):
        """缺失/非法 date 字段 → 时长回退 0，不崩溃。"""
        bars = [{"date": "bad-date", "total_value": 100.0},
                {"date": "2026-01-02", "total_value": 90.0}]
        events = extract_drawdown_events(bars)
        assert len(events) == 1
        assert events[0]["duration_days"] == 0
        assert events[0]["recovered"] is False

    def test_max_events_zero(self):
        """max_events=0 → 空列表。"""
        assert extract_drawdown_events(_bars([10, 12, 9]), max_events=0) == []

    def test_min_depth_pct_zero_includes_all(self):
        """min_depth_pct=0 → 深度 0 的持平区间也计入事件。"""
        events = extract_drawdown_events(_bars([10, 10, 10]), min_depth_pct=0.0)
        assert len(events) == 1
        assert events[0]["drawdown_pct"] == 0.0

    def test_large_magnitude_no_overflow(self):
        """极大幅值（1e9 量级）→ 计算不溢出、深度正确。"""
        events = extract_drawdown_events(_bars([1e9, 5e8, 2e9]))
        assert len(events) == 1
        assert events[0]["drawdown_pct"] == 50.0  # (1e9-5e8)/1e9*100

    def test_negative_total_value_before_peak(self):
        """首日即为负值 → 该日跳过，后续正常建峰。"""
        bars = [{"date": "2026-01-01", "total_value": -100.0},
                {"date": "2026-01-02", "total_value": 100.0},
                {"date": "2026-01-03", "total_value": 50.0}]
        events = extract_drawdown_events(bars)
        assert len(events) == 1
        assert events[0]["peak_date"] == "2026-01-02"
        assert events[0]["drawdown_pct"] == 50.0

    def test_single_underwater_then_flat(self):
        """单次下探后持平 → 未恢复事件（未创新高）。"""
        events = extract_drawdown_events(_bars([10, 12, 11, 11]))
        assert len(events) == 1
        assert events[0]["recovered"] is False
        assert events[0]["drawdown_pct"] == round((12 - 11) / 12 * 100, 2)  # 8.33


class TestComputeRecoveryTimesEdge:
    """compute_recovery_times 边缘场景。"""

    def test_recovery_days_none_when_unrecovered(self):
        """未恢复事件的 recovery_days 为 None。"""
        events = extract_drawdown_events(_bars([10, 12, 11, 9]))
        times = compute_recovery_times(events)
        assert times == []
        # 事件本身 recovery_days 为 None
        assert events[0]["recovery_days"] is None

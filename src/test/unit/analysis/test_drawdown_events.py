"""回撤事件提取模块测试 — 独立水下事件扫描 + 恢复耗时。

测试策略：
  - extract_drawdown_events() 覆盖空/单调/完整恢复/未恢复/多事件/深度过滤/截断
  - compute_recovery_times() 覆盖仅已恢复事件/排序/空输入
  - 事件字段完整性（peak/trough/recovery + 派生时长字段）

边缘/异常场景见 test_drawdown_events_edge.py。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

from src.python.analysis.drawdown_events import (
    compute_recovery_times,
    extract_drawdown_events,
)


def _bars(values: list[float], start: str = "2026-01-01") -> list[dict]:
    """从每日净值序列生成 bars（升序日期，每日 +1 天）。"""
    out: list[dict] = []
    d = date.fromisoformat(start)
    for v in values:
        out.append({"date": d.isoformat(), "total_value": float(v)})
        d += timedelta(days=1)
    return out


class TestExtractDrawdownEvents:
    """extract_drawdown_events 回撤事件扫描测试。"""

    def test_empty_bars_returns_empty(self):
        """空序列 → 空列表。"""
        assert extract_drawdown_events([]) == []

    def test_single_bar_no_events(self):
        """单点序列 → 无事件（单点是峰值，无水下区间）。"""
        assert extract_drawdown_events([{"date": "2026-01-01", "total_value": 100.0}]) == []

    def test_monotonic_rise_no_events(self):
        """单调上涨 → 无回撤事件。"""
        assert extract_drawdown_events(_bars([1, 2, 3, 4, 5])) == []

    def test_identical_values_no_events(self):
        """净值持平 → 无显著回撤（0% 深度低于阈值被过滤）。"""
        assert extract_drawdown_events(_bars([10, 10, 10])) == []

    def test_monotonic_decline_one_unrecovered(self):
        """单调下跌 → 1 个未恢复事件（前峰在首日，最深在末日）。"""
        events = extract_drawdown_events(_bars([5, 4, 3, 2, 1]))
        assert len(events) == 1
        e = events[0]
        assert e["peak_date"] == "2026-01-01"
        assert e["trough_date"] == "2026-01-05"
        assert e["recovery_date"] == ""
        assert e["recovered"] is False
        assert e["recovery_days"] is None
        assert e["duration_days"] == 4
        assert e["drawdown_pct"] == 80.0  # (5-1)/5*100

    def test_full_recovery_event(self):
        """V 型完整恢复 → 单事件含恢复日与恢复耗时。"""
        events = extract_drawdown_events(_bars([10, 11, 12, 10, 8, 12, 13]))
        assert len(events) == 1
        e = events[0]
        assert e["peak_date"] == "2026-01-03"
        assert e["trough_date"] == "2026-01-05"
        assert e["recovery_date"] == "2026-01-07"
        assert e["recovered"] is True
        assert e["drawdown_pct"] == 33.33  # (12-8)/12*100
        assert e["duration_days"] == 2  # 最深日 - 起峰日
        assert e["recovery_days"] == 2  # 恢复日 - 最深日

    def test_two_independent_events(self):
        """两个独立水下区间 → 各自恢复事件。"""
        events = extract_drawdown_events(_bars([10, 12, 9, 13, 15, 14, 16]))
        assert len(events) == 2
        e1, e2 = events
        assert e1["recovered"] is True and e2["recovered"] is True
        assert e1["drawdown_pct"] == 25.0  # (12-9)/12*100
        assert e2["drawdown_pct"] == 6.67  # (15-14)/15*100
        # 按起峰日升序
        assert e1["peak_date"] < e2["peak_date"]

    def test_depth_filter_removes_shallow(self):
        """深度低于 min_depth_pct 的事件被剔除。"""
        bars = _bars([10, 11, 10.5, 12])  # 从 11 跌到 10.5 = 4.55%
        assert extract_drawdown_events(bars, min_depth_pct=5.0) == []
        events = extract_drawdown_events(bars, min_depth_pct=4.0)
        assert len(events) == 1
        assert events[0]["drawdown_pct"] == 4.55

    def test_max_events_keeps_deepest(self):
        """超出 max_events → 保留深度最大的，且按起峰日升序。"""
        bars = _bars([100, 105, 99, 106, 110, 77, 111, 115, 103, 116])
        # 三次回撤：A=5.71%（105→99）、B=30.0%（110→77）、C=10.43%（115→103）
        events = extract_drawdown_events(bars, max_events=2)
        assert len(events) == 2
        assert [e["drawdown_pct"] for e in events] == [30.0, 10.43]
        assert events[0]["peak_date"] < events[1]["peak_date"]

    def test_unrecovered_event_at_data_end(self):
        """数据末尾仍处于水下 → 未恢复事件。"""
        events = extract_drawdown_events(_bars([10, 12, 11, 9, 8]))
        assert len(events) == 1
        e = events[0]
        assert e["recovered"] is False
        assert e["recovery_date"] == ""
        assert e["recovery_days"] is None
        assert e["drawdown_pct"] == 33.33  # (12-8)/12*100
        assert e["duration_days"] == 3

    def test_event_field_completeness(self):
        """事件 dict 字段完整：peak/trough/recovery + 派生时长字段。"""
        events = extract_drawdown_events(_bars([10, 12, 9, 13]))
        assert len(events) == 1
        e = events[0]
        for key in (
            "peak_date",
            "trough_date",
            "recovery_date",
            "drawdown_pct",
            "duration_days",
            "recovery_days",
            "recovered",
        ):
            assert key in e, f"事件应包含字段 {key}"

    def test_drawdown_pct_rounded_two_decimals(self):
        """drawdown_pct 四舍五入到两位小数。"""
        events = extract_drawdown_events(_bars([100, 120, 100]))
        # (120-100)/120*100 = 16.666... → 16.67
        assert events[0]["drawdown_pct"] == 16.67

    def test_recovery_resets_peak_for_next_event(self):
        """恢复后 running peak 更新，后续回撤以前峰为基准。"""
        events = extract_drawdown_events(_bars([10, 20, 15, 21, 19]))
        assert len(events) == 2
        # 事件 1：20→15 = 25%；事件 2：21→19 = 9.52%
        assert events[0]["drawdown_pct"] == 25.0
        assert events[1]["drawdown_pct"] == round((21 - 19) / 21 * 100, 2)


class TestComputeRecoveryTimes:
    """compute_recovery_times 恢复耗时明细测试。"""

    def test_only_recovered_events(self):
        """仅含 recovered=True 的事件，按起峰日升序。"""
        events = extract_drawdown_events(_bars([10, 12, 9, 13, 15, 14, 16]))
        times = compute_recovery_times(events)
        assert len(times) == 2
        for t in times:
            assert set(t) == {"start_date", "end_date", "days"}
            assert t["days"] is not None
        # 按 start_date 升序
        assert times[0]["start_date"] < times[1]["start_date"]

    def test_unrecovered_excluded(self):
        """未恢复事件不计入恢复耗时。"""
        events = extract_drawdown_events(_bars([10, 12, 11, 9, 8]))
        assert compute_recovery_times(events) == []

    def test_empty_input(self):
        """空事件列表 → 空列表。"""
        assert compute_recovery_times([]) == []

    def test_recovery_time_trough_to_recovery(self):
        """days = 最深日 → 恢复日 日历天数。"""
        events = extract_drawdown_events(_bars([10, 12, 9, 13]))
        times = compute_recovery_times(events)
        assert times[0] == {"start_date": "2026-01-03", "end_date": "2026-01-04", "days": 1}

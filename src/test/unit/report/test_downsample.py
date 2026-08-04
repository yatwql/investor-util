"""服务端下采样模块单元测试 — downsample.py。

覆盖 §4.9 验收标准（与 test_chart_data_builder.py::TestDownsampling 互补：
本文件测模块级函数，另一文件测经 build_chart_datasets 的集成行为）：
  - len(bars) ≤ 500 → 保留日频原样
  - len(bars) > 500 → 周聚合（点数 ≤ ceil(500/5)）
  - 周聚合后点数仍 > 200 → 月聚合兜底（点数 ≤ 200）
  - 取每周/每月最后一条（末点保留）
  - 下采样不改变原 bars 列表内容

运行：
  cd /lzcapp/document/working/codebase/investor-util
  .venv/bin/python -m pytest src/test/unit/report/test_downsample.py -v
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.python.report.downsample import (
    DOWNSAMPLE_MONTH_THRESHOLD,
    DOWNSAMPLE_WEEK_THRESHOLD,
    aggregate_bars_last,
    downsample_bars,
    month_key,
    week_key,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _gen_bars(n: int, start: str = "2024-01-01") -> list[dict]:
    """生成 n 个连续交易日 bars（2024-01-01 为周一，跳过周末）。"""
    bars: list[dict] = []
    d = date.fromisoformat(start)
    i = 0
    while len(bars) < n:
        if d.weekday() < 5:
            bars.append({"date": d.isoformat(), "total_value": 100.0 + i})
            i += 1
        d += timedelta(days=1)
    return bars


class TestDownsampleModule:
    def test_threshold_constants(self) -> None:
        """阈值常量与 §4.9 一致。"""
        assert DOWNSAMPLE_WEEK_THRESHOLD == 500
        assert DOWNSAMPLE_MONTH_THRESHOLD == 200

    def test_week_key_groups_by_iso_week(self) -> None:
        """week_key 按 ISO 年-周分组（跨年也正确）。"""
        assert week_key("2024-01-01") == (2024, 1)
        assert week_key("2024-01-05") == (2024, 1)  # 同周
        assert week_key("2026-01-01") != (2024, 1)

    def test_month_key_groups_by_year_month(self) -> None:
        """month_key 按 年-月 分组。"""
        assert month_key("2024-01-05") == "2024-01"
        assert month_key("2024-02-01") == "2024-02"

    def test_le_500_keeps_daily_identity(self) -> None:
        """≤500 点返回原列表（日频原样，引用不变）。"""
        bars = _gen_bars(500)
        assert downsample_bars(bars) is bars

    def test_over_500_weekly_aggregate(self) -> None:
        """>500 点 → 周聚合，点数 ≤ ceil(500/5)。"""
        bars = _gen_bars(501)
        result = downsample_bars(bars)
        assert len(result) < 500
        assert len(result) <= 500 // 5 + 1

    def test_weekly_takes_last_of_week(self) -> None:
        """周聚合取每周最后一条（首点 = 首周周五），末点保留。"""
        bars = _gen_bars(501)
        result = downsample_bars(bars)
        assert result[0]["date"] == "2024-01-05"  # 第 1 周周五
        assert result[-1]["date"] == bars[-1]["date"]  # 真实末点

    def test_weekly_too_many_falls_to_monthly(self) -> None:
        """周聚合后仍 > 200 → 月聚合兜底（点数 ≤ 200）。"""
        bars = _gen_bars(2000)
        result = downsample_bars(bars)
        assert len(result) <= 200
        assert result[0]["date"] == "2024-01-31"  # 每月末条

    def test_aggregate_keeps_last_of_group(self) -> None:
        """aggregate_bars_last 同组取最后一条。"""
        bars = [
            {"date": "2024-01-01", "total_value": 1.0},
            {"date": "2024-01-02", "total_value": 2.0},  # 同周，应覆盖
            {"date": "2024-01-08", "total_value": 3.0},
        ]
        result = aggregate_bars_last(bars, week_key)
        assert len(result) == 2
        assert result[0]["date"] == "2024-01-02"
        assert result[1]["date"] == "2024-01-08"

    def test_does_not_mutate_source(self) -> None:
        """下采样返回新列表，不改动原 bars 内容。"""
        bars = _gen_bars(501)
        original = [dict(b) for b in bars]
        downsample_bars(bars)
        assert bars == original

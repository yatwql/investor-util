"""危机区间标注模块测试 — 静态日期表 + 区间重叠 + 区间回撤/恢复耗时。

覆盖场景：
  - build_crisis_annotation 数据不可用占位（None / status=unavailable / bars 空）
  - 窗口与 2018/2020 区间重叠 → in_range + 区间最大回撤 + 最深日 + 恢复耗时
  - 窗口同时跨越 2018 + 2020 → 两个区间均正确标注并统计
  - 窗口不重叠 → 全部 in_range=False（显式"无历史区间"依据）
  - 最深日临近窗口末尾未恢复 → recovered=False / recovery_days=None
  - data_end 覆盖与缺失回退到 bars 末日期；恢复扫描不受窗口截断限制
  - 重叠窗口内无 bar / 非法日期 / 非正值净值 的防御分支

设计约束：纯标准库、无网络请求（危机日期为静态历史事实表）。
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

from src.python.analysis.crisis_annotation import (
    CRISIS_INTERVALS,
    _overlap_interval,
    _parse_window,
    build_crisis_annotation,
)


def _bars(pairs: list[tuple[str, float]]) -> list[dict]:
    """从 (date, total_value) 列表生成 bars（升序）。"""
    return [{"date": d, "total_value": float(v)} for d, v in pairs]


def _history(bars: list[dict], data_start: str, data_end: str | None = None) -> dict:
    """构造带窗口的 history_data mock。"""
    h: dict = {"status": "ok", "bars": bars, "data_start": data_start}
    if data_end is not None:
        h["data_end"] = data_end
    return h


# 2018 贸易摩擦重叠窗口：区间内 100 → 80 → 70（最深日）→ 100（恢复）→ 110
_2018_BARS = _bars(
    [
        ("2018-06-15", 100.0),  # 区间起点（2018-06-19）之前，不参与区间统计
        ("2018-06-20", 100.0),
        ("2018-07-05", 80.0),
        ("2018-08-01", 70.0),  # 最深日，回撤 30%
        ("2018-09-01", 100.0),  # 恢复至峰值
        ("2018-12-31", 110.0),
    ]
)

# 2020 疫情重叠窗口：区间内 100 → 80 → 60（最深日）→ 100（恢复）→ 120
_2020_BARS = _bars(
    [
        ("2020-02-10", 100.0),
        ("2020-02-25", 80.0),
        ("2020-03-05", 60.0),  # 最深日，回撤 40%
        ("2020-03-20", 100.0),  # 恢复至峰值
        ("2020-06-01", 120.0),
    ]
)


def _interval(contract: dict, name: str) -> dict:
    """按名称取出危机区间条目。"""
    return next(it for it in contract["intervals"] if it["name"] == name)


class TestBuildCrisisAnnotation:
    """build_crisis_annotation 数据可用性与区间标注。"""

    def test_none_returns_unavailable(self):
        """history_data=None → available=False 占位，4 个区间全 in_range=False。"""
        c = build_crisis_annotation(None)
        assert c["available"] is False
        assert len(c["intervals"]) == len(CRISIS_INTERVALS)
        assert all(it["in_range"] is False for it in c["intervals"])
        assert all(it["interval_drawdown_pct"] is None for it in c["intervals"])

    def test_status_unavailable_returns_unavailable(self):
        """status=unavailable → available=False 占位。"""
        c = build_crisis_annotation({"status": "unavailable", "bars": []})
        assert c["available"] is False

    def test_empty_bars_returns_unavailable(self):
        """bars 为空 → available=False 占位。"""
        c = build_crisis_annotation({"status": "ok", "bars": []})
        assert c["available"] is False

    def test_available_with_no_overlap_window(self):
        """窗口（2026）与全部危机区间不重叠 → available=True，全部 in_range=False。"""
        bars = _bars([("2026-01-05", 100.0), ("2026-06-01", 120.0)])
        c = build_crisis_annotation(_history(bars, "2026-01-01", "2026-12-31"))
        assert c["available"] is True
        assert all(it["in_range"] is False for it in c["intervals"])
        assert all(it["interval_drawdown_pct"] is None for it in c["intervals"])

    def test_2018_interval_annotated_with_stats(self):
        """窗口与 2018 贸易摩擦重叠 → 区间回撤 30.0%、最深日、恢复 31 天、已恢复。"""
        c = build_crisis_annotation(_history(_2018_BARS, "2018-06-15", "2018-12-31"))
        it = _interval(c, "2018 贸易摩擦")
        assert it["in_range"] is True
        assert it["interval_drawdown_pct"] == 30.0
        assert it["trough_date"] == "2018-08-01"
        assert it["recovery_days"] == 31
        assert it["recovered"] is True
        # 其余区间不重叠
        assert _interval(c, "2020 疫情冲击")["in_range"] is False
        assert _interval(c, "2015 股灾")["in_range"] is False

    def test_2020_interval_annotated_with_stats(self):
        """窗口与 2020 疫情重叠 → 区间回撤 40.0%、最深日、恢复 15 天、已恢复。"""
        c = build_crisis_annotation(_history(_2020_BARS, "2020-02-01", "2020-12-31"))
        it = _interval(c, "2020 疫情冲击")
        assert it["in_range"] is True
        assert it["interval_drawdown_pct"] == 40.0
        assert it["trough_date"] == "2020-03-05"
        assert it["recovery_days"] == 15
        assert it["recovered"] is True

    def test_window_spans_2018_and_2020_both_annotated(self):
        """窗口同时跨越 2018 + 2020 → 两个区间均 in_range 且统计正确（行为断言）。"""
        bars = _2018_BARS + _bars([("2019-06-03", 100.0)]) + _2020_BARS
        c = build_crisis_annotation(_history(bars, "2018-06-15", "2020-12-31"))
        it18 = _interval(c, "2018 贸易摩擦")
        it20 = _interval(c, "2020 疫情冲击")
        assert it18["in_range"] is True
        assert it18["interval_drawdown_pct"] == 30.0
        assert it20["in_range"] is True
        assert it20["interval_drawdown_pct"] == 40.0
        assert _interval(c, "2015 股灾")["in_range"] is False
        assert _interval(c, "2022 市场调整")["in_range"] is False

    def test_still_in_drawdown_at_window_end(self):
        """最深日后净值未回到峰值 → recovered=False / recovery_days=None。"""
        bars = _bars(
            [
                ("2018-06-20", 100.0),
                ("2018-07-05", 80.0),
                ("2018-08-01", 70.0),  # 最深日
                ("2018-12-31", 70.0),  # 窗口末尾仍在低谷
            ]
        )
        c = build_crisis_annotation(_history(bars, "2018-06-15", "2018-12-31"))
        it = _interval(c, "2018 贸易摩擦")
        assert it["in_range"] is True
        assert it["interval_drawdown_pct"] == 30.0
        assert it["trough_date"] == "2018-08-01"
        assert it["recovery_days"] is None
        assert it["recovered"] is False

    def test_data_end_override_and_recovery_scan_beyond_window(self):
        """data_end 提前截断报告窗口 → 区间统计以窗口内 bar 为准，恢复扫描仍全量。"""
        # 窗口只到 2018-08-05，但恢复（2018-09-01）在窗口外仍被扫描到
        c = build_crisis_annotation(_history(_2018_BARS, "2018-06-15", "2018-08-05"))
        it = _interval(c, "2018 贸易摩擦")
        assert it["in_range"] is True
        assert it["trough_date"] == "2018-08-01"
        assert it["recovery_days"] == 31
        assert it["recovered"] is True

    def test_data_end_missing_falls_back_to_last_bar(self):
        """history_data 无 data_end → 窗口末端回退到 bars[-1].date。"""
        c = build_crisis_annotation(_history(_2018_BARS, "2018-06-15"))
        it = _interval(c, "2018 贸易摩擦")
        assert it["in_range"] is True
        assert it["interval_drawdown_pct"] == 30.0

    def test_overlap_window_without_bars_keeps_stats_none(self):
        """重叠窗口内无 bar → in_range=True 但区间统计置空。"""
        bars = _bars(
            [
                ("2015-06-10", 100.0),
                ("2015-06-20", 90.0),  # 跳过 [2015-06-12, 2015-06-15] 窗口
            ]
        )
        c = build_crisis_annotation(_history(bars, "2015-06-12", "2015-06-15"))
        it = _interval(c, "2015 股灾")
        assert it["in_range"] is True
        assert it["interval_drawdown_pct"] is None
        assert it["recovered"] is None

    def test_nonpositive_value_skipped_in_interval_stats(self):
        """区间内出现非正值净值（0）→ 跳过，不破坏最大回撤计算。"""
        bars = _bars(
            [
                ("2018-06-20", 100.0),
                ("2018-07-05", 0.0),  # 非正值，跳过
                ("2018-08-01", 70.0),  # 最深日，回撤仍 30%
                ("2018-09-01", 100.0),
            ]
        )
        c = build_crisis_annotation(_history(bars, "2018-06-15", "2018-12-31"))
        it = _interval(c, "2018 贸易摩擦")
        assert it["interval_drawdown_pct"] == 30.0
        assert it["trough_date"] == "2018-08-01"

    def test_bad_window_dates_produce_no_overlap(self):
        """data_start/data_end 非法 → 全部区间不重叠（防御分支）。"""
        bars = _bars([("2020-02-10", 100.0)])
        c = build_crisis_annotation({"status": "ok", "bars": bars, "data_start": "bad-date", "data_end": "2020-12-31"})
        assert c["available"] is True
        assert all(it["in_range"] is False for it in c["intervals"])


class TestCrisisIntervalHelpers:
    """CRISIS_INTERVALS 静态表 + 内部解析/重叠辅助。"""

    def test_static_table_contains_four_known_intervals(self):
        """静态表含 2015/2018/2020/2022 四个已知危机区间。"""
        names = {it["name"] for it in CRISIS_INTERVALS}
        assert names == {"2015 股灾", "2018 贸易摩擦", "2020 疫情冲击", "2022 市场调整"}
        # 每项具备完整字段
        for it in CRISIS_INTERVALS:
            assert {"name", "start", "end", "desc"} <= set(it)
            date.fromisoformat(it["start"])
            date.fromisoformat(it["end"])

    def test_parse_window_valid(self):
        """合法日期 → (start, end) date 对。"""
        assert _parse_window("2018-01-01", "2018-12-31") == (
            date(2018, 1, 1),
            date(2018, 12, 31),
        )

    def test_parse_window_bad_format_returns_none(self):
        """非法日期 → None。"""
        assert _parse_window("bad", "2018-12-31") is None
        assert _parse_window(None, None) is None

    def test_overlap_clips_to_window(self):
        """区间与窗口部分重叠 → 返回裁剪后的重叠日期。"""
        raw = {"name": "2018 贸易摩擦", "start": "2018-06-19", "end": "2019-01-04"}
        window = (date(2018, 1, 1), date(2018, 12, 31))
        assert _overlap_interval(raw, window) == (date(2018, 6, 19), date(2018, 12, 31))

    def test_overlap_no_intersection_returns_none(self):
        """区间完全在窗口外 → None。"""
        raw = {"name": "2015 股灾", "start": "2015-06-12", "end": "2015-09-30"}
        window = (date(2018, 1, 1), date(2018, 12, 31))
        assert _overlap_interval(raw, window) is None

    def test_overlap_none_window_returns_none(self):
        """window=None → None。"""
        raw = {"name": "2018 贸易摩擦", "start": "2018-06-19", "end": "2019-01-04"}
        assert _overlap_interval(raw, None) is None

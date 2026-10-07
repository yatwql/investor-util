"""事件窗量化对照（event_window_impact）边缘场景：降级只降级不硬算，全部离线。"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.python.analysis.event_window_impact import (
    compute_event_impact,
    map_event_to_trading_day,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]

_HOLIDAYS = {"2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"}


def _weekdays(start: str, end: str) -> set[str]:
    out: set[str] = set()
    cur = datetime.strptime(start, "%Y-%m-%d")
    last = datetime.strptime(end, "%Y-%m-%d")
    while cur <= last:
        day = cur.strftime("%Y-%m-%d")
        if cur.weekday() < 5 and day not in _HOLIDAYS:
            out.add(day)
        cur += timedelta(days=1)
    return out


_CAL = _weekdays("2026-08-24", "2026-11-30")


@pytest.fixture(autouse=True)
def _calendar():
    with patch("src.python.core.trading_calendar._get_trading_calendar", return_value=set(_CAL)):
        yield


def _dates(start: str, end: str) -> list[str]:
    return sorted(d for d in _CAL if start <= d <= end)


def _bars(
    dates: list[str], default: float = 100.0, overrides: dict | None = None, drop: set[str] | None = None
) -> list[dict]:
    overrides = overrides or {}
    return [{"date": d, "close": overrides.get(d, default)} for d in dates if not (drop and d in drop)]


_ALL = _dates("2026-08-24", "2026-10-30")
_INDEX = _bars(_ALL, 3000.0, {"2026-09-22": 3150.0})


@pytest.mark.parametrize(
    "asset_bars",
    [
        None,
        [],
        [
            {"date": "2026-09-15", "close": None},
            {"date": "2026-09-16", "close": 0},
            {"date": "2026-09-17", "close": "abc"},
        ],
    ],
)
def test_missing_asset_bars_degrades(asset_bars):
    """品种行情缺失/全坏行 → 品种行情不可得，不抛异常。"""
    res = compute_event_impact("2026-09-15", asset_bars, _INDEX)
    assert res["available"] is False
    assert "品种行情不可得" in res["reason"]


@pytest.mark.parametrize("index_bars", [None, []])
def test_missing_index_bars_degrades(index_bars):
    """基准缺失 → 基准行情不可得（红线：缺基准不出行）。"""
    res = compute_event_impact("2026-09-15", _ALL and _bars(_ALL), index_bars)
    assert res["available"] is False
    assert "基准行情不可得" in res["reason"]


def test_missing_over_threshold_degrades():
    """窗口缺失 4/11 = 36% > 30% → 该事件不出行且 reason 标注缺失。"""
    asset = _bars(_ALL, 100.0, drop={"2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21"})
    res = compute_event_impact("2026-09-15", asset, _INDEX)
    assert res["available"] is False
    assert "缺失" in res["reason"]


def test_window_out_of_range_degrades():
    """行情轴过短（窗口越界）→ 不出行。"""
    short = _dates("2026-09-10", "2026-09-16")
    res = compute_event_impact("2026-09-15", _bars(short), _bars(short, 3000.0))
    assert res["available"] is False
    assert "窗口超出行情范围" in res["reason"]


@pytest.mark.parametrize("bad_date", ["", "2026-13-40", None, "not-a-date"])
def test_unmappable_event_date_degrades(bad_date):
    """非法事件日期 → 映射失败，不出行不抛异常。"""
    res = compute_event_impact(bad_date, _bars(_ALL), _INDEX)
    assert res["available"] is False
    assert "事件日无法映射" in res["reason"]


def test_anchor_not_in_axis_degrades():
    """映射交易日两侧行情都没有（轴内无该日）→ 不出行。"""
    asset = _bars(_dates("2026-09-16", "2026-10-09"))
    index = _bars(_dates("2026-09-16", "2026-10-09"), 3000.0)
    res = compute_event_impact("2026-09-15", asset, index)
    assert res["available"] is False
    assert "映射交易日不在行情轴" in res["reason"]


def test_no_pre_event_base_point_degrades():
    """window_before=0 且 T0 就是轴首日 → 无事件日前基点 → 不出行。"""
    asset = _bars(_dates("2026-09-15", "2026-10-09"))
    index = _bars(_dates("2026-09-15", "2026-10-09"), 3000.0)
    res = compute_event_impact("2026-09-15", asset, index, window_before=0)
    assert res["available"] is False
    assert "无事件日前基点" in res["reason"]


def test_unresolvable_prev_base_degrades():
    """品种从 T0 当日才开始有价 → T0−1 关键位 LOCF 无前值 → 不出行。"""
    asset = _bars(_dates("2026-09-15", "2026-10-09"))
    res = compute_event_impact("2026-09-15", asset, _INDEX)
    assert res["available"] is False
    assert "品种关键位无法解析" in res["reason"]


def test_map_exceeding_lookahead_returns_none():
    """前向探测耗尽（全部为非交易日）→ None 由调用方降级。"""
    empty_cal = set()  # 空日历 + 周末回退：周六起连探 0 天上限
    with patch("src.python.core.trading_calendar._get_trading_calendar", return_value=empty_cal):
        assert map_event_to_trading_day("2026-09-19", max_lookahead=0) is None

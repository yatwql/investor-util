"""事件窗量化对照（event_window_impact）纯计算单元测试。

手算对照口径：窗口 = 映射交易日 ±5 交易日（11 天）；收益基点 = T0−1 → T0+5。
日历以补丁注入（隔离 akshare 网络）；行情全部 fixture 构造，零真实取数。
极端/降级场景见 test_event_window_impact_edge.py。
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.python.analysis.event_window_impact import (
    assess_direction_match,
    compute_event_impact,
    map_event_to_trading_day,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

#: 模拟日历：2026-08-24 ~ 2026-11-30 全工作日，剔除模拟长假
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
    """注入交易日历（patch 持有者模块，隔离 akshare 网络调用）。"""
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
_ASSET = _bars(_ALL, 100.0, {"2026-09-22": 110.0})
_INDEX = _bars(_ALL, 3000.0, {"2026-09-22": 3150.0})


# ── 事件日 → 交易日映射 ────────────────────────────────────────


def test_map_trading_day_passthrough():
    """T 本身是交易日 → 原样返回。"""
    assert map_event_to_trading_day("2026-09-15") == "2026-09-15"


def test_map_weekend_forward():
    """T 落周末 → 其后第一个交易日（周一）。"""
    assert map_event_to_trading_day("2026-09-19") == "2026-09-21"


def test_map_holiday_forward_multiple_days():
    """T 落工作日假期（连休跨周末）→ 顺延多个自然日到首个交易日。"""
    assert map_event_to_trading_day("2026-10-01") == "2026-10-07"


# ── 主路径手算对照 ────────────────────────────────────────────


def test_full_impact_hand_computed():
    """正常窗口：收益/超额/方向/一致标记逐项与手算一致，窗口恰为 11 天。"""
    res = compute_event_impact("2026-09-15", _ASSET, _INDEX, text_polarity="利好", asset_code="600900")
    assert res["available"] is True
    assert res["trading_day"] == "2026-09-15"
    assert res["window_dates"] == [
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
        "2026-09-11",
        "2026-09-14",
        "2026-09-15",
        "2026-09-16",
        "2026-09-17",
        "2026-09-18",
        "2026-09-21",
        "2026-09-22",
    ]
    assert res["prev_date"] == "2026-09-14"
    assert res["end_date"] == "2026-09-22"
    # 手算：110/100−1 = 0.10；3150/3000−1 = 0.05；超额 0.05
    assert res["asset_return"] == pytest.approx(0.1)
    assert res["index_return"] == pytest.approx(0.05)
    assert res["excess_return"] == pytest.approx(0.05)
    assert res["direction"] == "上"
    assert res["match"] == "一致"
    assert res["missing_ratio"] == 0.0
    assert res["locf_filled"] == 0
    assert res["reason"] == ""


def test_locf_fills_suspension_gap():
    """停牌 2 日 → LOCF 前值填充并计数，收益关键位不受影响（手算一致）。"""
    asset = _bars(_ALL, 100.0, {"2026-09-22": 110.0}, drop={"2026-09-16", "2026-09-17"})
    res = compute_event_impact("2026-09-15", asset, _INDEX, text_polarity="利好")
    assert res["available"] is True
    assert res["locf_filled"] == 2
    assert res["missing_ratio"] == pytest.approx(0.1818)
    assert res["asset_return"] == pytest.approx(0.1)
    assert res["excess_return"] == pytest.approx(0.05)


def test_conflict_polarity_flagged():
    """利好 × 下跌（本例：利空极性 × 上涨）→ 分歧。"""
    res = compute_event_impact("2026-09-15", _ASSET, _INDEX, text_polarity="利空")
    assert res["direction"] == "上"
    assert res["match"] == "分歧"


def test_neutral_polarity_not_judged():
    """中性极性 → 中性不判（无方向主张，不计一致/分歧）。"""
    res = compute_event_impact("2026-09-15", _ASSET, _INDEX, text_polarity="中性")
    assert res["match"] == "中性不判"


def test_flat_return_marked():
    """首末价持平 → direction 持平 → 利好也不判（持平不判）。"""
    asset = _bars(_ALL, 100.0, {"2026-09-22": 100.0})
    res = compute_event_impact("2026-09-15", asset, _INDEX, text_polarity="利好")
    assert res["asset_return"] == 0.0
    assert res["direction"] == "持平"
    assert res["match"] == "持平不判"


def test_missing_ratio_exact_threshold_passes():
    """窗口 10 天缺 3 天 = 30.0% 恰等 → 不超限，照常出行（恰等算过）。"""
    asset = _bars(_ALL, 100.0, {"2026-09-22": 110.0}, drop={"2026-09-16", "2026-09-17", "2026-09-18"})
    res = compute_event_impact("2026-09-15", asset, _INDEX, text_polarity="利好", window_before=4)
    assert res["available"] is True
    assert res["missing_ratio"] == 0.30
    assert res["asset_return"] == pytest.approx(0.1)


def test_weekend_event_end_to_end():
    """周末事件全链路：映射到周一、窗口完整、收益手算一致。"""
    res = compute_event_impact("2026-09-19", _ASSET, _INDEX, text_polarity=None)
    assert res["available"] is True
    assert res["trading_day"] == "2026-09-21"
    # prev=2026-09-18(100)、end=2026-09-28(100) → 收益 0
    assert res["asset_return"] == 0.0
    assert res["match"] == "不可判"  # 无文本极性


# ── 方向比对表 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("direction", "polarity", "expected"),
    [
        ("上", "利好", "一致"),
        ("下", "利空", "一致"),
        ("上", "利空", "分歧"),
        ("下", "利好", "分歧"),
        ("上", "中性", "中性不判"),
        ("持平", "利好", "持平不判"),
        ("上", None, "不可判"),
        ("上", "看多", "不可判"),
    ],
)
def test_assess_direction_match_table(direction, polarity, expected):
    """方向 × 极性 → 比对结论全表遍历。"""
    assert assess_direction_match(direction, polarity) == expected

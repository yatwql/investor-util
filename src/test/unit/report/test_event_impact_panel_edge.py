"""事件窗对照表数据编排边缘场景（空输入/坏数据/取数异常），全部注入替身离线。"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.python.report.event_impact_panel import build_event_rows

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]

_HOLDINGS = [SimpleNamespace(name="工商银行", code="601398")]


@pytest.fixture(autouse=True)
def _calendar():
    """注入交易日历（patch 持有者模块，隔离 akshare 网络调用）。"""
    with patch("src.python.core.trading_calendar._get_trading_calendar", return_value=set(_CAL)):
        yield


_CAL = {f"2026-09-{d:02d}" for d in range(1, 31) if datetime.strptime(f"2026-09-{d:02d}", "%Y-%m-%d").weekday() < 5}


def _ok_providers():
    bars = [
        {"date": f"2026-09-{d:02d}", "close": 100.0}
        for d in range(10, 30)
        if d <= 30 and f"2026-09-{d:02d}" <= "2026-09-29"
    ]
    return (Mock(return_value=bars), Mock(return_value=bars), Mock(return_value="sh000300"))


def test_empty_news_hides_section():
    """无新闻 → 事件表空，available=False（章隐藏传导）。"""
    fetch_bars, fetch_index, resolve = _ok_providers()
    res = build_event_rows(
        _HOLDINGS, [], None, fetch_bars=fetch_bars, fetch_index=fetch_index, benchmark_code_for=resolve
    )
    assert res == {
        "available": False,
        "events": [],
        "degraded": [],
        "skipped": {"bad_date": 0, "unmatched": 0, "capped": 0},
        "degraded_count": 0,
    }


def test_bad_ctime_counted_not_crashing():
    """ctime 不可解析 → 计入 bad_date，不产出事件不抛异常。"""
    fetch_bars, fetch_index, resolve = _ok_providers()
    res = build_event_rows(
        _HOLDINGS,
        [{"ctime": "昨天", "matched_keywords": ["工商银行"], "title": "t"}],
        None,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert res["skipped"]["bad_date"] == 1
    assert res["available"] is False


def test_penetrated_malformed_codes_filtered():
    """穿透 codes 混入非 A 股代码 → 过滤后无命中计 unmatched。"""
    fetch_bars, fetch_index, resolve = _ok_providers()
    res = build_event_rows(
        _HOLDINGS,
        [{"ctime": "2026-09-15", "matched_keywords": ["腾讯"], "title": "t"}],
        [{"name": "腾讯", "codes": ["HK00700", "usAAPL"]}],
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert res["skipped"]["unmatched"] == 1
    fetch_bars.assert_not_called()


def test_fetch_exception_degrades_row():
    """取数抛异常 → 单行降级为取数异常，整体不崩（其余行继续）。"""
    bars = [{"date": f"2026-09-{d:02d}", "close": 100.0} for d in range(10, 30)]
    calls = {"n": 0}

    def flaky(code: str):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("chain down")
        return bars

    res = build_event_rows(
        _HOLDINGS,
        [
            {"ctime": "2026-09-15", "matched_keywords": ["工商银行"], "title": "a"},
            {"ctime": "2026-09-16", "matched_keywords": ["工商银行"], "title": "b"},
        ],
        None,
        fetch_bars=flaky,
        fetch_index=Mock(return_value=bars),
        benchmark_code_for=Mock(return_value="sh000300"),
    )
    assert res["degraded_count"] == 1
    assert "取数异常" in res["degraded"][0]["reason"]
    assert len(res["events"]) == 1


def test_news_none_treated_as_empty():
    """news_data=None → 空表降级不抛。"""
    fetch_bars, fetch_index, resolve = _ok_providers()
    res = build_event_rows(
        _HOLDINGS, None, None, fetch_bars=fetch_bars, fetch_index=fetch_index, benchmark_code_for=resolve
    )
    assert res["available"] is False


def test_holdings_none_no_crash():
    """holdings=None → 无品种索引，全部 unmatched 不抛。"""
    fetch_bars, fetch_index, resolve = _ok_providers()
    res = build_event_rows(
        None,
        [{"ctime": "2026-09-15", "matched_keywords": ["x"]}],
        None,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert res["skipped"]["unmatched"] == 1

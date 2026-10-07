"""事件窗对照表数据编排（event_impact_panel 数据侧）单元测试。

全部经注入替身取数（零网络）；行情 fixture 构造；品种索引/极性解析/事件行组装
主路径覆盖。降级与空输入场景见 test_event_impact_panel_edge.py。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.python.report.event_impact_panel import (
    build_event_rows,
    extract_text_polarity,
    parse_event_date,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _dates(start: str, end: str) -> list[str]:
    out, cur = [], datetime.strptime(start, "%Y-%m-%d")
    last = datetime.strptime(end, "%Y-%m-%d")
    while cur <= last:
        if cur.weekday() < 5:
            out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


_ALL = _dates("2026-08-24", "2026-10-30")
_CAL = set(_ALL)


@pytest.fixture(autouse=True)
def _calendar():
    """注入交易日历（patch 持有者模块，隔离 akshare 网络调用）。"""
    with patch("src.python.core.trading_calendar._get_trading_calendar", return_value=set(_CAL)):
        yield


def _bars(default: float = 100.0, overrides: dict | None = None) -> list[dict]:
    overrides = overrides or {}
    return [{"date": d, "close": overrides.get(d, default)} for d in _ALL]


_HOLDINGS = [SimpleNamespace(name="工商银行", code="601398"), SimpleNamespace(name="稳健增长混合", code="002943")]
_PENETRATED = [{"name": "长江电力", "codes": ["600900"]}]


def _news(**kw) -> dict:
    base = {
        "title": "工行发布三季度业绩",
        "intro": "……",
        "url": "https://example.com/n1",
        "ctime": "2026-09-15 10:30:00",
        "media_name": "测试源",
        "matched_keywords": ["工商银行"],
        "llm_analysis": "[高][利好] 业绩超预期",
    }
    base.update(kw)
    return base


# ── 极性与日期解析 ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[高][利好] 业绩超预期", "利好"),
        ("[中][利空] 增速回落", "利空"),
        ("[中] 维持观察", "中性"),
        ("", None),
        (None, None),
        ({"unexpected": "dict"}, None),
    ],
)
def test_extract_text_polarity_table(text, expected):
    """llm_analysis 标记 → 极性全表（与新闻表着色同口径，无标记=中性/缺失=None）。"""
    assert extract_text_polarity({"llm_analysis": text}) == expected


@pytest.mark.parametrize(
    ("ctime", "expected"),
    [
        ("2026-10-04 16:44", "2026-10-04"),
        ("2026-10-02 21:47:37", "2026-10-02"),
        ("2026-09-15", "2026-09-15"),
        ("bad-timestamp", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_event_date_table(ctime, expected):
    """三种上游时间格式 → 事件日期；坏值返回 None（计入 bad_date）。"""
    assert parse_event_date(ctime) == expected


# ── 事件表组装主路径 ──────────────────────────────────────────


def _providers(asset_bars=None, index_bars=None):
    fetch_bars = Mock(return_value=asset_bars if asset_bars is not None else _bars())
    fetch_index = Mock(return_value=index_bars if index_bars is not None else _bars(3000.0))
    resolve = Mock(return_value="sh000300")
    return fetch_bars, fetch_index, resolve


def test_happy_path_single_event():
    """持仓名命中 → 单事件出行：行字段、取数调用、极性与影响度齐全。"""
    asset = _bars(100.0, {"2026-09-14": 100.0, "2026-09-22": 110.0})
    index = _bars(3000.0, {"2026-09-14": 3000.0, "2026-09-22": 3150.0})
    fetch_bars, fetch_index, resolve = _providers(asset, index)
    res = build_event_rows(
        _HOLDINGS,
        [_news()],
        _PENETRATED,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert res["available"] is True
    assert len(res["events"]) == 1
    row = res["events"][0]
    assert row["code"] == "601398"
    assert row["title"] == "工行发布三季度业绩"
    assert row["polarity"] == "利好"
    assert row["matched_keyword"] == "工商银行"
    assert row["available"] is True
    assert row["asset_return"] == pytest.approx(0.1)
    assert row["match"] == "一致"
    fetch_bars.assert_called_once_with("601398")
    resolve.assert_called_once_with({"code": "601398"})
    fetch_index.assert_called_once_with("sh000300")


def test_penetrated_stock_matched_by_name():
    """穿透资产名命中 → 底层 A 股代码出行。"""
    fetch_bars, fetch_index, resolve = _providers()
    res = build_event_rows(
        _HOLDINGS,
        [_news(matched_keywords=["长江电力"], title="来水偏丰")],
        _PENETRATED,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert res["available"] is True
    assert res["events"][0]["code"] == "600900"


def test_one_news_multiple_codes_multiple_rows():
    """一条新闻同时命中多品种 → 事件 × 品种逐行展开。"""
    fetch_bars, fetch_index, resolve = _providers()
    res = build_event_rows(
        _HOLDINGS,
        [_news(matched_keywords=["工商银行", "长江电力"])],
        _PENETRATED,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert [r["code"] for r in res["events"]] == ["601398", "600900"]


def test_fund_holding_not_in_index():
    """基金持仓不入品种索引（无日频股票行情）→ 命中计 unmatched 不硬算。"""
    fetch_bars, fetch_index, resolve = _providers()
    res = build_event_rows(
        _HOLDINGS,
        [_news(matched_keywords=["稳健增长混合"], llm_analysis="[低] 观察")],
        None,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert res["available"] is False
    assert res["skipped"]["unmatched"] == 1
    fetch_bars.assert_not_called()


def test_row_cap_counts_overflow():
    """行数上限：超额新闻计入 capped，不无限膨胀。"""
    items = [_news(title=f"新闻{i}", url=f"https://example.com/{i}") for i in range(4)]
    fetch_bars, fetch_index, resolve = _providers()
    res = build_event_rows(
        _HOLDINGS,
        items,
        None,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
        max_rows=2,
    )
    assert len(res["events"]) == 2
    assert res["skipped"]["capped"] == 2


def test_degraded_event_excluded_but_counted():
    """窗口行情不可得 → 该事件降级不出行、计数呈现、available=False 供章隐藏。"""
    fetch_bars, fetch_index, resolve = _providers(asset_bars=[])
    res = build_event_rows(
        _HOLDINGS,
        [_news()],
        None,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert res["available"] is False
    assert res["events"] == []
    assert res["degraded_count"] == 1
    assert "品种行情不可得" in res["degraded"][0]["reason"]


def test_no_index_code_skips_fetch():
    """基准码解析为 None → 不调指数取数，事件按基准不可得降级。"""
    fetch_bars, fetch_index, resolve = _providers()
    resolve.return_value = None
    res = build_event_rows(
        _HOLDINGS,
        [_news()],
        None,
        fetch_bars=fetch_bars,
        fetch_index=fetch_index,
        benchmark_code_for=resolve,
    )
    assert res["available"] is False
    fetch_index.assert_not_called()
    assert "基准行情不可得" in res["degraded"][0]["reason"]

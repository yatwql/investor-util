"""真实 akshare 交易日历连通性验证（opt-in live 套件，不入门禁）。

运行：`python scripts/test-runner.py --mode live` 或 `pytest -m live`。

断言原则：只校验返回「结构」与非空，不校验具体日期集合。
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live]


@pytest.mark.live
def test_trading_calendar_akshare():
    """akshare 交易日历：返回非空交易日集合。"""
    from src.python.report.market_value import _get_trading_calendar

    calendar = _get_trading_calendar()
    assert isinstance(calendar, set)
    assert len(calendar) > 0, "akshare 交易日历不可达或返回空"
    # 抽查一个近期日期格式（YYYY-MM-DD）
    sample = next(iter(calendar))
    assert isinstance(sample, str)
    assert len(sample) == 10


@pytest.mark.live
def test_last_trading_day():
    """最近交易日：返回合法日期字符串。"""
    from src.python.report.market_value import get_last_trading_day

    day = get_last_trading_day()
    assert isinstance(day, str)
    assert len(day) == 10
    # YYYY-MM-DD 基本校验
    parts = day.split("-")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)

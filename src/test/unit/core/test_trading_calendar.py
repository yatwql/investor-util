"""交易日历原语单元测试。

测试目标：
  - count_trading_days_elapsed — 按交易日（而非自然日）统计区间内经过的交易日数
  - 回退口径 — 交易日历不可用时按「排除周六日」近似计数

运行：
  pytest src/test/unit/core/test_trading_calendar.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.core.trading_calendar import count_trading_days_elapsed

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

# 测试日历（2026 年 9-10 月片段）：09-16 ~ 09-25 与 10-01 ~ 10-07 为假期
_TEST_CALENDAR = {
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
    "2026-09-11",
    "2026-09-14",
    "2026-09-15",
    "2026-09-28",
    "2026-09-29",
    "2026-09-30",
    "2026-10-08",
    "2026-10-09",
    "2026-10-12",
}


def _with_calendar(calendar: set[str]):
    """打桩交易日历（隔离 akshare 网络调用）。"""
    return patch("src.python.core.trading_calendar._get_trading_calendar", return_value=calendar)


class TestCountTradingDaysElapsed:
    """交易日计数（不含起点、含终点）。"""

    def test_adjacent_trading_days_elapse_one(self):
        """相邻两个交易日 → 1。"""
        with _with_calendar(_TEST_CALENDAR):
            assert count_trading_days_elapsed("2026-09-10", "2026-09-11") == 1

    def test_weekend_is_not_counted(self):
        """周五 → 下周一：跨越周末但仅经过 1 个交易日。"""
        with _with_calendar(_TEST_CALENDAR):
            assert count_trading_days_elapsed("2026-09-11", "2026-09-14") == 1

    def test_long_holiday_counts_as_one_trading_day(self):
        """长假前后相邻的两个交易日相差 8 个自然日，但仅经过 1 个交易日。

        缺陷场景：按自然日差判定会把长假前后的正常间隔误判为「延迟/停更」。
        """
        with _with_calendar(_TEST_CALENDAR):
            assert count_trading_days_elapsed("2026-09-30", "2026-10-08") == 1

    def test_counts_every_session_in_range(self):
        """区间内每个交易日各计一次（不含起点、含终点）。"""
        with _with_calendar(_TEST_CALENDAR):
            # 2026-09-09 / 09-10 / 09-11 / 09-14 / 09-15 共 5 个交易日
            assert count_trading_days_elapsed("2026-09-08", "2026-09-15") == 5

    def test_same_date_returns_zero(self):
        """起点 == 终点 → 0。"""
        with _with_calendar(_TEST_CALENDAR):
            assert count_trading_days_elapsed("2026-09-11", "2026-09-11") == 0

    def test_reverse_order_returns_zero(self):
        """起点晚于终点（数据异常）→ 0。"""
        with _with_calendar(_TEST_CALENDAR):
            assert count_trading_days_elapsed("2026-09-11", "2026-09-10") == 0

    def test_invalid_date_returns_none(self):
        """日期格式非法 → None（消费方按「未知」处理）。"""
        with _with_calendar(_TEST_CALENDAR):
            assert count_trading_days_elapsed("not-a-date", "2026-09-11") is None
            assert count_trading_days_elapsed("2026-09-11", "") is None


class TestCalendarUnavailableFallback:
    """交易日历不可用时的近似口径（排除周六日）。"""

    def test_weekend_still_excluded(self):
        """日历不可用 → 周五到下周一只计 1（周六日不算交易日）。"""
        with _with_calendar(set()):
            assert count_trading_days_elapsed("2026-09-11", "2026-09-14") == 1

    def test_saturday_not_counted(self):
        """日历不可用 → 周六不计入。"""
        with _with_calendar(set()):
            assert count_trading_days_elapsed("2026-09-11", "2026-09-12") == 0

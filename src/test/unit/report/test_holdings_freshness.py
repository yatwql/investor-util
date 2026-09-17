"""基金持仓报告期时效判定单元测试。

缺陷场景：接口回退到「不指定年份」的默认请求时可能返回数年前的报告期
（如实测到的 2022-12-08），该报告期无人校验，陈旧持仓被按当期市值计入穿透。
本文件锁定判定口径与阈值边界。
"""

from __future__ import annotations

from datetime import date

import pytest

from src.python.report.holdings_freshness import (
    STALE_QUARTERS,
    complete_quarters_since,
    format_report_period,
    is_stale_report,
    parse_report_date,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestParseReportDate:
    """parse_report_date: 容忍接口的多种报告期写法。"""

    def test_iso_format(self):
        """标准 YYYY-MM-DD（实测路径）。"""
        assert parse_report_date("2022-12-08") == date(2022, 12, 8)

    def test_slash_format(self):
        """斜杠分隔。"""
        assert parse_report_date("2022/12/08") == date(2022, 12, 8)

    def test_compact_format(self):
        """无分隔符。"""
        assert parse_report_date("20221208") == date(2022, 12, 8)

    def test_chinese_format(self):
        """中文年月日。"""
        assert parse_report_date("2022年12月08日") == date(2022, 12, 8)

    def test_surrounding_whitespace_tolerated(self):
        """前后空白不影响解析。"""
        assert parse_report_date("  2022-12-08 ") == date(2022, 12, 8)

    def test_empty_returns_none(self):
        """空字符串/None 视为无报告期。"""
        assert parse_report_date("") is None
        assert parse_report_date(None) is None

    def test_unparseable_returns_none(self):
        """无法解析时返回 None，而不是抛异常或猜一个日期。"""
        assert parse_report_date("未知") is None
        assert parse_report_date("2022-13-45") is None


class TestCompleteQuartersSince:
    """complete_quarters_since: 报告期之后走完的完整季度数。"""

    def test_stale_report_counts_all_elapsed_quarters(self):
        """2022-12-08 的报告到 2026-09-11 已走完 14 个完整季度。"""
        assert complete_quarters_since(date(2022, 12, 8), date(2026, 9, 11)) == 14

    def test_report_from_current_quarter_is_zero(self):
        """报告期落在当季（当季未走完）时为 0。"""
        assert complete_quarters_since(date(2026, 6, 30), date(2026, 9, 11)) == 0

    def test_one_full_quarter_elapsed(self):
        """报告期为上一季末，其后只走完当季之前的一个季度。"""
        assert complete_quarters_since(date(2026, 3, 31), date(2026, 9, 11)) == 1

    def test_two_full_quarters_elapsed(self):
        """报告期为上上季末，其后走完两个完整季度。"""
        assert complete_quarters_since(date(2025, 12, 31), date(2026, 9, 11)) == 2

    def test_quarter_end_today_counts_current_quarter(self):
        """当天恰为季末时，当季即算走完。"""
        assert complete_quarters_since(date(2026, 6, 30), date(2026, 9, 30)) == 1

    def test_future_report_is_not_negative(self):
        """报告期晚于今天（接口异常）时返回 0，不为负数。"""
        assert complete_quarters_since(date(2027, 1, 15), date(2026, 9, 11)) == 0


class TestIsStaleReport:
    """is_stale_report: 达到阈值即判定不可采信。"""

    def test_stale_report_detected(self):
        """四年前的报告期判定为陈旧。"""
        assert is_stale_report(date(2022, 12, 8), date(2026, 9, 11)) is True

    def test_just_at_threshold_is_stale(self):
        """恰好走满阈值个完整季度即判陈旧（>= 而非 >）。"""
        report = date(2025, 12, 31)
        assert complete_quarters_since(report, date(2026, 9, 11)) == STALE_QUARTERS
        assert is_stale_report(report, date(2026, 9, 11)) is True

    def test_one_quarter_old_is_fresh(self):
        """差一个季度未达阈值，仍按可用处理——为披露滞后留出余量。"""
        assert is_stale_report(date(2026, 3, 31), date(2026, 9, 11)) is False

    def test_unparseable_report_is_not_stale(self):
        """报告期缺失/无法解析时不判陈旧——那属于数据缺失，走另一条降级路径。"""
        assert is_stale_report(None, date(2026, 9, 11)) is False


class TestFormatReportPeriod:
    """format_report_period: 展示用报告期文本。"""

    def test_normalizes_to_iso(self):
        """统一格式化为 YYYY-MM-DD 便于报告展示。"""
        assert format_report_period("2022/12/08") == "2022-12-08"

    def test_empty_shows_unknown(self):
        """无报告期时显示「未知」，不显示空串。"""
        assert format_report_period("") == "未知"
        assert format_report_period(None) == "未知"

    def test_unparseable_passes_through(self):
        """无法解析时原样展示，不吞掉接口返回的原始文本。"""
        assert format_report_period("2022年三季度") == "2022年三季度"

"""交易时段判断单元测试。

测试目标：
  - _parse_time_to_minutes — HH:MM→分钟数转换
  - _fetch_trading_status_from_official — API 调用与异常
  - _is_market_open_config — config.json 手动覆盖
  - _is_market_open_official — 官方 API 实时状态
  - _is_market_open_fallback — 内置默认值
  - is_market_open — 三层 orchestration

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_market_hours.py -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.python.market_hours import (

    _parse_time_to_minutes,
    is_market_open,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


# ═══════════════════════════════════════════════════════════
#  _parse_time_to_minutes
# ═══════════════════════════════════════════════════════════


class TestParseTimeToMinutes(unittest.TestCase):
    """HH:MM → 分钟数 转换测试。"""

    def test_normal_time(self):
        """正常时间 "09:30" → 570。"""
        self.assertEqual(_parse_time_to_minutes("09:30"), 570)

    def test_midday(self):
        """"13:00" → 780。"""
        self.assertEqual(_parse_time_to_minutes("13:00"), 780)

    def test_end_of_day(self):
        """"15:00" → 900。"""
        self.assertEqual(_parse_time_to_minutes("15:00"), 900)

    def test_midnight(self):
        """"00:00" → 0。"""
        self.assertEqual(_parse_time_to_minutes("00:00"), 0)

    def test_with_leading_space(self):
        """前导空格自动去除。"""
        self.assertEqual(_parse_time_to_minutes(" 09:30"), 570)

    def test_with_trailing_space(self):
        """后导空格自动去除。"""
        self.assertEqual(_parse_time_to_minutes("09:30 "), 570)

    def test_invalid_format_no_colon(self):
        """缺少冒号 → None。"""
        self.assertIsNone(_parse_time_to_minutes("0930"))

    def test_invalid_format_garbage(self):
        """无效字符 → None。"""
        self.assertIsNone(_parse_time_to_minutes("abc:def"))

    def test_invalid_format_empty(self):
        """空字符串 → None。"""
        self.assertIsNone(_parse_time_to_minutes(""))

    def test_invalid_minutes_out_of_range(self):
        """分钟超出范围（仍可解析为 int，不做边界校验）。"""
        self.assertEqual(_parse_time_to_minutes("09:99"), 9 * 60 + 99)


# ═══════════════════════════════════════════════════════════
#  _fetch_trading_status_from_official
# ═══════════════════════════════════════════════════════════


class TestFetchTradingStatusOfficial(unittest.TestCase):
    """东方财富 push2 API 实时状态获取测试。"""

    @patch("src.python.http_client.make_http_client")
    def test_trading(self, mock_make_client):
        """API 返回 f100=1 → 返回 1（交易中）。"""
        mock_client = MagicMock()
        mock_client.get.return_value.json.return_value = {"data": {"f100": 1}}
        mock_make_client.return_value.__enter__.return_value = mock_client
        from src.python.market_hours import _fetch_trading_status_from_official

        result = _fetch_trading_status_from_official()
        self.assertEqual(result, 1)

    @patch("src.python.http_client.make_http_client")
    def test_closed(self, mock_make_client):
        """API 返回 f100=2 → 返回 2（已收盘）。"""
        mock_client = MagicMock()
        mock_client.get.return_value.json.return_value = {"data": {"f100": 2}}
        mock_make_client.return_value.__enter__.return_value = mock_client
        from src.python.market_hours import _fetch_trading_status_from_official

        result = _fetch_trading_status_from_official()
        self.assertEqual(result, 2)

    @patch("src.python.http_client.make_http_client")
    def test_pre_open(self, mock_make_client):
        """API 返回 f100=0 → 返回 0（未开盘）。"""
        mock_client = MagicMock()
        mock_client.get.return_value.json.return_value = {"data": {"f100": 0}}
        mock_make_client.return_value.__enter__.return_value = mock_client
        from src.python.market_hours import _fetch_trading_status_from_official

        result = _fetch_trading_status_from_official()
        self.assertEqual(result, 0)

    @patch("src.python.http_client.make_http_client")
    def test_lunch_break(self, mock_make_client):
        """API 返回 f100=3 → 返回 3（午间休市）。"""
        mock_client = MagicMock()
        mock_client.get.return_value.json.return_value = {"data": {"f100": 3}}
        mock_make_client.return_value.__enter__.return_value = mock_client
        from src.python.market_hours import _fetch_trading_status_from_official

        result = _fetch_trading_status_from_official()
        self.assertEqual(result, 3)

    @patch("src.python.http_client.make_http_client")
    def test_api_timeout_returns_none(self, mock_make_client):
        """API 超时异常 → 返回 None。"""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("timeout")
        mock_make_client.return_value.__enter__.return_value = mock_client
        from src.python.market_hours import _fetch_trading_status_from_official

        result = _fetch_trading_status_from_official()
        self.assertIsNone(result)

    @patch("src.python.http_client.make_http_client")
    def test_empty_data_returns_none(self, mock_make_client):
        """API 返回 data 为空 → None。"""
        mock_client = MagicMock()
        mock_client.get.return_value.json.return_value = {"data": None}
        mock_make_client.return_value.__enter__.return_value = mock_client
        from src.python.market_hours import _fetch_trading_status_from_official

        result = _fetch_trading_status_from_official()
        self.assertIsNone(result)

    @patch("src.python.http_client.make_http_client")
    def test_status_missing_returns_none(self, mock_make_client):
        """API 返回 data 缺少 f100 → None。"""
        mock_client = MagicMock()
        mock_client.get.return_value.json.return_value = {"data": {"f169": 12345}}
        mock_make_client.return_value.__enter__.return_value = mock_client
        from src.python.market_hours import _fetch_trading_status_from_official

        result = _fetch_trading_status_from_official()
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════
#  _is_market_open_fallback（内置默认值）
# ═══════════════════════════════════════════════════════════


class TestIsMarketOpenFallback(unittest.TestCase):
    """内置默认值策略测试。"""

    def _run(self, mock_dt: datetime) -> bool:
        with patch("src.python.market_hours.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.timezone = timezone
            mock_datetime.timedelta = timedelta
            from src.python.market_hours import _is_market_open_fallback

            current_min = mock_dt.hour * 60 + mock_dt.minute
            return _is_market_open_fallback(current_min)

    def test_morning_session(self):
        """早盘 09:30 → True。"""
        dt = datetime(2026, 7, 1, 9, 30, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._run(dt))

    def test_afternoon_session(self):
        """午盘 14:00 → True。"""
        dt = datetime(2026, 7, 1, 14, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._run(dt))

    def test_lunch_break(self):
        """午间休市 12:00 → False。"""
        dt = datetime(2026, 7, 1, 12, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._run(dt))

    def test_pre_market(self):
        """盘前 08:00 → False。"""
        dt = datetime(2026, 7, 1, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._run(dt))

    def test_after_close(self):
        """收盘后 15:30 → False。"""
        dt = datetime(2026, 7, 1, 15, 30, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._run(dt))

    def test_weekend_saturday(self):
        """周六 → False。"""
        dt = datetime(2026, 7, 4, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._run(dt))

    def test_weekend_sunday(self):
        """周日 → False。"""
        dt = datetime(2026, 7, 5, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._run(dt))

    def test_boundary_morning_start(self):
        """09:30 开盘边界 → True。"""
        dt = datetime(2026, 7, 1, 9, 30, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._run(dt))

    def test_boundary_morning_end(self):
        """11:30 收盘边界 → True。"""
        dt = datetime(2026, 7, 1, 11, 30, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._run(dt))

    def test_boundary_lunch_start(self):
        """11:31 → False（午餐开始）。"""
        dt = datetime(2026, 7, 1, 11, 31, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._run(dt))

    def test_boundary_afternoon_start(self):
        """13:00 开盘边界 → True。"""
        dt = datetime(2026, 7, 1, 13, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._run(dt))

    def test_boundary_afternoon_end(self):
        """15:00 收盘边界 → True。"""
        dt = datetime(2026, 7, 1, 15, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertTrue(self._run(dt))

    def test_boundary_after_close(self):
        """15:01 → False。"""
        dt = datetime(2026, 7, 1, 15, 1, tzinfo=timezone(timedelta(hours=8)))
        self.assertFalse(self._run(dt))


# ═══════════════════════════════════════════════════════════
#  _is_market_open_config（配置文件覆盖）
# ═══════════════════════════════════════════════════════════


class TestIsMarketOpenConfig(unittest.TestCase):
    """config.json 手动覆盖策略测试。"""

    @patch("src.python.config.get_config")
    def test_no_config_returns_none(self, mock_get_config):
        """未配置 market_hours → None。"""
        mock_get_config.return_value = {}
        from src.python.market_hours import _is_market_open_config
        result = _is_market_open_config(600)
        self.assertIsNone(result)

    @patch("src.python.config.get_config")
    def test_partial_config_returns_none(self, mock_get_config):
        """配置不完整（缺 end）→ None。"""
        mock_get_config.return_value = {"market_hours": {"start": "09:30"}}
        from src.python.market_hours import _is_market_open_config
        result = _is_market_open_config(600)
        self.assertIsNone(result)

    @patch("src.python.config.get_config")
    @patch("src.python.market_hours.datetime")
    def test_config_in_range_no_lunch(self, mock_dt_datetime, mock_get_config):
        """配置 09:00-17:00，09:30 → True（午餐仍排除）。"""
        mock_get_config.return_value = {"market_hours": {"start": "09:00", "end": "17:00"}}
        fake_now = datetime(2026, 7, 1, 9, 30, tzinfo=timezone(timedelta(hours=8)))
        mock_dt_datetime.now.return_value = fake_now
        mock_dt_datetime.timezone = timezone
        mock_dt_datetime.timedelta = timedelta
        from src.python.market_hours import _is_market_open_config
        result = _is_market_open_config(570)
        self.assertTrue(result)

    @patch("src.python.config.get_config")
    @patch("src.python.market_hours.datetime")
    def test_config_lunch_still_excluded(self, mock_dt_datetime, mock_get_config):
        """配置 09:00-17:00，12:00 → False（午餐排除）。"""
        mock_get_config.return_value = {"market_hours": {"start": "09:00", "end": "17:00"}}
        fake_now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone(timedelta(hours=8)))
        mock_dt_datetime.now.return_value = fake_now
        mock_dt_datetime.timezone = timezone
        mock_dt_datetime.timedelta = timedelta
        from src.python.market_hours import _is_market_open_config
        result = _is_market_open_config(720)
        self.assertFalse(result)

    @patch("src.python.config.get_config")
    @patch("src.python.market_hours.datetime")
    def test_config_weekend_returns_false(self, mock_dt_datetime, mock_get_config):
        """配置 09:00-17:00，周六 → False。"""
        mock_get_config.return_value = {"market_hours": {"start": "09:00", "end": "17:00"}}
        fake_now = datetime(2026, 7, 4, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        mock_dt_datetime.now.return_value = fake_now
        mock_dt_datetime.timezone = timezone
        mock_dt_datetime.timedelta = timedelta
        from src.python.market_hours import _is_market_open_config
        result = _is_market_open_config(600)
        self.assertFalse(result)

    @patch("src.python.config.get_config")
    def test_invalid_time_format_returns_none(self, mock_get_config):
        """配置中时间格式无效 → None。"""
        mock_get_config.return_value = {"market_hours": {"start": "abc", "end": "15:00"}}
        from src.python.market_hours import _is_market_open_config
        result = _is_market_open_config(600)
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════
#  is_market_open（三层编排）
# ═══════════════════════════════════════════════════════════


class TestIsMarketOpen(unittest.TestCase):
    """三层策略编排集成测试。"""

    @patch("src.python.market_hours._is_market_open_config", return_value=True)
    @patch("src.python.market_hours._is_market_open_official")
    @patch("src.python.market_hours._is_market_open_fallback")
    @patch("src.python.market_hours.datetime")
    def test_config_takes_precedence_true(
        self, mock_dt, mock_fallback, mock_official, mock_config
    ):
        """config 层返回 True → 直接返回 True。"""
        mock_dt.now.return_value = datetime(2026, 7, 1, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        mock_dt.timezone = timezone
        mock_dt.timedelta = timedelta
        self.assertTrue(is_market_open())
        mock_official.assert_not_called()
        mock_fallback.assert_not_called()

    @patch("src.python.market_hours._is_market_open_config", return_value=None)
    @patch("src.python.market_hours._is_market_open_official", return_value=True)
    @patch("src.python.market_hours._is_market_open_fallback")
    @patch("src.python.market_hours.datetime")
    def test_official_takes_precedence(
        self, mock_dt, mock_fallback, mock_official, mock_config
    ):
        """config 层 None → 官方层 True → 返回 True。"""
        mock_dt.now.return_value = datetime(2026, 7, 1, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        mock_dt.timezone = timezone
        mock_dt.timedelta = timedelta
        self.assertTrue(is_market_open())
        mock_fallback.assert_not_called()

    @patch("src.python.market_hours._is_market_open_config", return_value=None)
    @patch("src.python.market_hours._is_market_open_official", return_value=None)
    @patch("src.python.market_hours._is_market_open_fallback", return_value=True)
    @patch("src.python.market_hours.datetime")
    def test_fallback_used_when_all_others_none(
        self, mock_dt, mock_fallback, mock_official, mock_config
    ):
        """config+官方均 None → fallback 层决定结果。"""
        mock_dt.now.return_value = datetime(2026, 7, 1, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        mock_dt.timezone = timezone
        mock_dt.timedelta = timedelta
        self.assertTrue(is_market_open())
        mock_fallback.assert_called_once()

    @patch("src.python.market_hours._is_market_open_config", return_value=False)
    @patch("src.python.market_hours._is_market_open_official")
    @patch("src.python.market_hours._is_market_open_fallback")
    @patch("src.python.market_hours.datetime")
    def test_config_false_short_circuits(
        self, mock_dt, mock_fallback, mock_official, mock_config
    ):
        """config 层返回 False → 直接返回 False。"""
        mock_dt.now.return_value = datetime(2026, 7, 1, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        mock_dt.timezone = timezone
        mock_dt.timedelta = timedelta
        self.assertFalse(is_market_open())
        mock_official.assert_not_called()
        mock_fallback.assert_not_called()

    @patch("src.python.market_hours._is_market_open_config", side_effect=Exception("boom"))
    @patch("src.python.market_hours._is_market_open_official")
    @patch("src.python.market_hours._is_market_open_fallback")
    @patch("src.python.market_hours.datetime")
    def test_exception_returns_false(
        self, mock_dt, mock_fallback, mock_official, mock_config
    ):
        """异常时保守返回 False。"""
        mock_dt.now.return_value = datetime(2026, 7, 1, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        mock_dt.timezone = timezone
        mock_dt.timedelta = timedelta
        self.assertFalse(is_market_open())


# ═══════════════════════════════════════════════════════════
#  R-084: UTC 时区一致性回归测试
# ═══════════════════════════════════════════════════════════


class TestUtcTimezoneConsistency(unittest.TestCase):
    """验证 market_hours 在非 UTC+8 系统时区下的行为一致性。

    Bug 背景：模块内部应始终使用北京时间（UTC+8）判断交易时段，
    而不是依赖系统时区。本测试模拟系统时区为 UTC / EST / UTC+8
    三种场景，验证结果一致。
    """

    def _test_at_time(self, beijing_hour: int, beijing_min: int,
                      weekday: int, system_tz_offset: int) -> bool:
        """在指定系统时区偏移下，模拟北京时间某时刻运行 is_market_open。

        Args:
            beijing_hour: 北京时间的小时（0-23）
            beijing_min: 北京时间的分钟（0-59）
            weekday: 星期几（0=周一, 6=周日）
            system_tz_offset: 系统时区相对 UTC 的偏移小时数

        Returns:
            is_market_open() 的返回结果
        """
        # 计算系统时区的本地时间
        utc_now = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)  # 任一基准日
        beijing_dt = utc_now + timedelta(hours=8)  # 北京时间基准
        # 调整到目标北京时间
        target_beijing = beijing_dt.replace(
            hour=beijing_hour, minute=beijing_min
        )
        # 对应的 UTC 时间
        target_utc = target_beijing - timedelta(hours=8)
        # 在系统时区下看到的本地时间
        system_local = target_utc + timedelta(hours=system_tz_offset)

        # 计算目标日期的 weekday
        # 从 2026-07-01（周三=2）推算
        base_weekday = 2  # 2026-07-01 是周三
        days_diff = (beijing_hour // 24) if beijing_hour >= 24 else 0
        actual_weekday = (base_weekday + days_diff) % 7
        # 用传参 weekday 覆盖以便测试周末
        target_system_dt = system_local.replace(
            year=2026, month=7,
            day=1 + days_diff
        )
        # 直接调整 weekday（更精确）
        from datetime import timezone as dt_tz, timedelta as dt_td
        with patch("src.python.market_hours.datetime") as mock_dt:
            # 模拟系统 datetime.now() 返回带系统时区偏移的时间
            mock_dt.now.return_value = target_system_dt
            mock_dt.timezone = dt_tz
            mock_dt.timedelta = dt_td
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            from src.python.market_hours import is_market_open as _imo
            return _imo()

    def _call_is_market_open_at_beijing_time(
        self, hour: int, minute: int, weekday: int = 0,
        system_offset: int = 8
    ) -> bool:
        """简化的北京时间测试辅助方法。"""
        from src.python.market_hours import _is_market_open_fallback, _is_market_open_config
        with patch("src.python.market_hours.datetime") as mock_dt:
            # 构造北京时间的时间对象
            beijing_dt = datetime(
                2026, 7, 6 + weekday, hour, minute,
                tzinfo=timezone(timedelta(hours=8))
            )
            # 对应 UTC 时间
            utc_dt = beijing_dt.astimezone(timezone.utc)
            # 在系统时区下看到的时间
            sys_dt = utc_dt.astimezone(timezone(timedelta(hours=system_offset)))

            # 使用 side_effect 确保 timezone 参数被正确处理：
            # is_market_open() 调用 datetime.now(tz=UTC+8) 应返回北京时间
            def _now_side_effect(tz=None):
                return sys_dt if tz is None else sys_dt.astimezone(tz)

            mock_dt.now.side_effect = _now_side_effect
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            from src.python.market_hours import is_market_open

            return is_market_open()

    def setUp(self):
        # 确保 config 层不干预
        self._cfg_patcher = patch("src.python.market_hours._is_market_open_config",
                                   return_value=None)
        self._cfg_patcher.start()
        self._official_patcher = patch("src.python.market_hours._is_market_open_official",
                                        return_value=None)
        self._official_patcher.start()

    def tearDown(self):
        self._official_patcher.stop()
        self._cfg_patcher.stop()

    # ── 系统时区为 UTC（+0）─ 北京时间 10:00 交易日 ──

    def test_utc_system_at_beijing_morning(self):
        """系统 UTC，北京时间 10:00 周二 → True。"""
        self.assertTrue(
            self._call_is_market_open_at_beijing_time(10, 0, weekday=1, system_offset=0)
        )

    def test_utc_system_at_beijing_lunch(self):
        """系统 UTC，北京时间 12:00 周二 → False（午休）。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(12, 0, weekday=1, system_offset=0)
        )

    def test_utc_system_at_beijing_afternoon(self):
        """系统 UTC，北京时间 14:00 周二 → True。"""
        self.assertTrue(
            self._call_is_market_open_at_beijing_time(14, 0, weekday=1, system_offset=0)
        )

    def test_utc_system_at_beijing_closed(self):
        """系统 UTC，北京时间 15:30 周二 → False。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(15, 30, weekday=1, system_offset=0)
        )

    # ── 系统时区为 EST（UTC-5）─ 北京时间 10:00 交易日 ──

    def test_est_system_at_beijing_morning(self):
        """系统 EST(UTC-5)，北京时间 10:00 周二 → True。"""
        self.assertTrue(
            self._call_is_market_open_at_beijing_time(10, 0, weekday=1, system_offset=-5)
        )

    def test_est_system_at_beijing_lunch(self):
        """系统 EST(UTC-5)，北京时间 12:00 周二 → False（午休）。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(12, 0, weekday=1, system_offset=-5)
        )

    def test_est_system_at_beijing_weekend(self):
        """系统 EST(UTC-5)，北京时间周六 10:00 → False。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(10, 0, weekday=5, system_offset=-5)
        )

    # ── 系统时区为 UTC+8（北京时间）─ 基线验证 ──

    def test_cst_system_at_beijing_morning(self):
        """系统 UTC+8，北京时间 10:00 周二 → True（基线）。"""
        self.assertTrue(
            self._call_is_market_open_at_beijing_time(10, 0, weekday=1, system_offset=8)
        )

    def test_cst_system_at_beijing_lunch(self):
        """系统 UTC+8，北京时间 12:00 周二 → False（基线）。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(12, 0, weekday=1, system_offset=8)
        )

    def test_cst_system_weekend(self):
        """系统 UTC+8，北京时间周六 10:00 → False（基线）。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(10, 0, weekday=5, system_offset=8)
        )

    # ── 边界日期：跨 UTC 日期线 ──

    def test_utc_system_cross_date_line_morning(self):
        """系统 UTC，北京时间周一 09:30（UTC 周日 01:30）→ True（交易日）。"""
        self.assertTrue(
            self._call_is_market_open_at_beijing_time(9, 30, weekday=0, system_offset=0)
        )

    def test_utc_system_cross_date_line_weekend_beijing_saturday(self):
        """系统 UTC，北京时间周六 09:30（UTC 周五 01:30）→ False（周末）。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(9, 30, weekday=5, system_offset=0)
        )

    # ── 系统时区为 JST（UTC+9）─ 与北京同时区方向 ──

    def test_jst_system_at_beijing_morning(self):
        """系统 JST(UTC+9)，北京时间 10:00 周二 → True。"""
        self.assertTrue(
            self._call_is_market_open_at_beijing_time(10, 0, weekday=1, system_offset=9)
        )

    def test_jst_system_at_beijing_lunch(self):
        """系统 JST(UTC+9)，北京时间 12:00 周二 → False。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(12, 0, weekday=1, system_offset=9)
        )

    # ── 系统时区为 Pacific（UTC-8）─ 深度负偏移 ──

    def test_pacific_system_at_beijing_morning(self):
        """系统 Pacific(UTC-8)，北京时间 10:00 周二 → True。"""
        self.assertTrue(
            self._call_is_market_open_at_beijing_time(10, 0, weekday=1, system_offset=-8)
        )

    def test_pacific_system_at_beijing_afternoon(self):
        """系统 Pacific(UTC-8)，北京时间 14:00 周二 → True。"""
        self.assertTrue(
            self._call_is_market_open_at_beijing_time(14, 0, weekday=1, system_offset=-8)
        )

    def test_pacific_system_weekend(self):
        """系统 Pacific(UTC-8)，北京时间周六 10:00 → False。"""
        self.assertFalse(
            self._call_is_market_open_at_beijing_time(10, 0, weekday=5, system_offset=-8)
        )

    # ── 午休判断时区一致性 ──

    def _call_midday_break_at_beijing_time(self, hour, minute, weekday=1, system_offset=8):
        """在指定系统时区下调用 is_midday_break() 辅助方法。"""
        with patch("src.python.market_hours.datetime") as mock_dt:
            beijing_dt = datetime(
                2026, 7, 6 + weekday, hour, minute,
                tzinfo=timezone(timedelta(hours=8))
            )
            utc_dt = beijing_dt.astimezone(timezone.utc)
            sys_dt = utc_dt.astimezone(timezone(timedelta(hours=system_offset)))

            def _now_side_effect(tz=None):
                return sys_dt if tz is None else sys_dt.astimezone(tz)

            mock_dt.now.side_effect = _now_side_effect
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            from src.python.market_hours import is_midday_break
            return is_midday_break()

    def test_midday_break_utc_system(self):
        """UTC 系统下北京时间 12:00 → 午休。"""
        self.assertTrue(
            self._call_midday_break_at_beijing_time(12, 0, system_offset=0)
        )

    def test_midday_break_est_system(self):
        """EST 系统下北京时间 12:00 → 午休。"""
        self.assertTrue(
            self._call_midday_break_at_beijing_time(12, 0, system_offset=-5)
        )

    def test_midday_break_non_break_time(self):
        """任意系统时区下北京时间 14:00 → 非午休。"""
        self.assertFalse(
            self._call_midday_break_at_beijing_time(14, 0, system_offset=8)
        )

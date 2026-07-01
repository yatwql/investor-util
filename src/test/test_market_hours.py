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

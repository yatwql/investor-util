"""交易时段判断时区一致性 edge 专项测试。

从 test_market_hours.py 提取的 edge 场景：
  - 系统时区为 JST（UTC+9）— 与北京同时区方向
  - 系统时区为 Pacific（UTC-8）— 深度负偏移
  - 午休判断时区一致性（UTC/EST/任意）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/core/test_market_hours_edge.py -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


@pytest.mark.edge
class TestUtcTimezoneConsistencyEdge(unittest.TestCase):
    """market_hours 在非标准系统时区下的 edge 行为。"""

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

    def _call_is_market_open_at_beijing_time(
        self, hour: int, minute: int, weekday: int = 0,
        system_offset: int = 8
    ) -> bool:
        """简化的北京时间测试辅助方法。"""
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

            # 使用 side_effect 确保 timezone 参数被正确处理
            def _now_side_effect(tz=None):
                return sys_dt if tz is None else sys_dt.astimezone(tz)

            mock_dt.now.side_effect = _now_side_effect
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            from src.python.market_hours import is_market_open
            return is_market_open()

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


if __name__ == "__main__":
    unittest.main()

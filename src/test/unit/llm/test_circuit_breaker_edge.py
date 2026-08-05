"""熔断器冷却计时边界 + 多端点状态 edge 专项测试。

edge 场景：
  - 冷却期满 60s 整 → 半开
  - 冷却期 59s（未满 60s）→ 仍然熔断
  - 多个 endpoint 处于不同熔断状态

运行：
  pytest src/test/unit/llm/test_circuit_breaker_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm, pytest.mark.edge]


@pytest.mark.edge
class TestCircuitBreakerBoundary(unittest.TestCase):
    """熔断器冷却计时边界 + 多端点状态独立性。"""

    def setUp(self):
        from src.python.llm.circuit_breaker import (
            _circuit_failures, _circuit_open_until,
        )
        self._orig_failures = _circuit_failures.copy()
        self._orig_open_until = _circuit_open_until.copy()
        _circuit_failures.clear()
        _circuit_open_until.clear()

    def tearDown(self):
        from src.python.llm.circuit_breaker import (
            _circuit_failures, _circuit_open_until,
        )
        _circuit_failures.clear()
        _circuit_failures.update(self._orig_failures)
        _circuit_open_until.clear()
        _circuit_open_until.update(self._orig_open_until)

    @patch("src.python.llm.circuit_breaker.time")
    def test_exact_60s_boundary_half_open(self, mock_time):
        """冷却期满 60s 整 → 半开（允许试探请求）。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _cb_is_open,
            _CIRCUIT_BREAKER_RECOVERY,
        )
        url = "https://api.test.com/v1"
        mock_time.time.return_value = 1000.0

        for _ in range(3):
            _cb_record_failure(url)
        self.assertTrue(_cb_is_open(url))

        # 刚好 60s → 半开
        mock_time.time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY
        self.assertFalse(_cb_is_open(url))

    @patch("src.python.llm.circuit_breaker.time")
    def test_recovery_time_not_reached(self, mock_time):
        """冷却期 59s（未满 60s）→ 仍然熔断。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _cb_is_open,
            _CIRCUIT_BREAKER_RECOVERY,
        )
        url = "https://api.test.com/v1"
        mock_time.time.return_value = 1000.0

        for _ in range(3):
            _cb_record_failure(url)
        self.assertTrue(_cb_is_open(url))

        # 59.999s → 仍熔断
        mock_time.time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY - 0.001
        self.assertTrue(_cb_is_open(url))

    @patch("src.python.llm.circuit_breaker.time")
    def test_multiple_endpoints_different_states(self, mock_time):
        """多个 endpoint 处于不同熔断状态（开/闭/计数中）。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _cb_is_open,
        )
        url_a = "https://api.anthropic.com/v1"
        url_b = "https://api.openai.com/v1"
        url_c = "https://api.deepseek.com/v1"
        mock_time.time.return_value = 1000.0

        # endpoint A: 3 次失败 → 熔断
        for _ in range(3):
            _cb_record_failure(url_a)
        self.assertTrue(_cb_is_open(url_a))

        # endpoint B: 2 次失败 → 计数中（未熔断）
        _cb_record_failure(url_b)
        _cb_record_failure(url_b)
        self.assertFalse(_cb_is_open(url_b))

        # endpoint C: 1 次失败 → 计数中（未熔断）
        _cb_record_failure(url_c)
        self.assertFalse(_cb_is_open(url_c))

        # 三者状态互不影响
        self.assertTrue(_cb_is_open(url_a))
        self.assertFalse(_cb_is_open(url_b))
        self.assertFalse(_cb_is_open(url_c))


if __name__ == "__main__":
    unittest.main()

"""熔断器冷却恢复测试。

测试目标：
  - 连续 3 次失败 → 熔断开启（_cb_is_open 返回 True）
  - 冷却 60 秒 → 半开（_cb_is_open 返回 False，允许一次试探）
  - 半开状态下成功 → 熔断关闭（失败计数清零）
  - 半开状态下再次失败 → 重新熔断
  - 成功重置失败计数
  - 不同 endpoint 独立熔断

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_circuit_breaker_recovery -v
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]



class TestCircuitBreakerOpenClose(unittest.TestCase):
    """验证熔断器开启/关闭/恢复完整生命周期。"""

    def setUp(self):
        # 每次测试前清理全局熔断状态
        from src.python.llm.circuit_breaker import (
            _circuit_failures, _circuit_open_until,
        )
        # 保存原始状态并在 tearDown 恢复
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

    def test_closed_by_default(self):
        """初始状态 → 熔断关闭。"""
        from src.python.llm.circuit_breaker import _cb_is_open
        self.assertFalse(_cb_is_open("https://api.test.com/v1"))

    def test_one_failure_does_not_open(self):
        """1 次失败 → 不开启熔断。"""
        from src.python.llm.circuit_breaker import _cb_record_failure, _cb_is_open

        _cb_record_failure("https://api.test.com/v1")
        self.assertFalse(_cb_is_open("https://api.test.com/v1"))

    def test_two_failures_does_not_open(self):
        """2 次失败 → 不开启熔断。"""
        from src.python.llm.circuit_breaker import _cb_record_failure, _cb_is_open

        _cb_record_failure("https://api.test.com/v1")
        _cb_record_failure("https://api.test.com/v1")
        self.assertFalse(_cb_is_open("https://api.test.com/v1"))

    def test_three_failures_opens_circuit(self):
        """3 次失败 → 熔断开启。"""
        from src.python.llm.circuit_breaker import _cb_record_failure, _cb_is_open

        for _ in range(3):
            _cb_record_failure("https://api.test.com/v1")
        self.assertTrue(_cb_is_open("https://api.test.com/v1"))

    def test_four_failures_keeps_open(self):
        """超过 3 次失败 → 熔断保持开启。"""
        from src.python.llm.circuit_breaker import _cb_record_failure, _cb_is_open

        for _ in range(4):
            _cb_record_failure("https://api.test.com/v1")
        self.assertTrue(_cb_is_open("https://api.test.com/v1"))


class TestCircuitBreakerRecovery(unittest.TestCase):
    """验证熔断冷却恢复 + 半开试探机制。"""

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
    def test_recovery_after_cooldown(self, mock_time):
        """冷却期过后 → 熔断半开（_cb_is_open 返回 False）。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _cb_is_open,
            _CIRCUIT_BREAKER_RECOVERY,
        )

        url = "https://api.test.com/v1"
        mock_time.time.return_value = 1000.0

        # 3 次失败 → 熔断开启
        for _ in range(3):
            _cb_record_failure(url)
        self.assertTrue(_cb_is_open(url))

        # 快进到冷却期后
        mock_time.time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY + 1

        # 冷却结束 → 半开（允许请求）
        self.assertFalse(_cb_is_open(url))

    @patch("src.python.llm.circuit_breaker.time")
    def test_success_resets_after_recovery(self, mock_time):
        """冷却后成功 → 熔断完全关闭，失败计数清零。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _cb_record_success, _cb_is_open,
            _circuit_failures, _CIRCUIT_BREAKER_RECOVERY,
        )

        url = "https://api.test.com/v1"
        mock_time.time.return_value = 1000.0

        # 3 次失败 → 熔断开启
        for _ in range(3):
            _cb_record_failure(url)
        self.assertTrue(_cb_is_open(url))

        # 快进到冷却期后 → 半开
        mock_time.time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY + 1
        self.assertFalse(_cb_is_open(url))  # 半开

        # 成功 → 熔断关闭
        _cb_record_success(url)
        self.assertFalse(_cb_is_open(url))
        self.assertNotIn(url, _circuit_failures)

    @patch("src.python.llm.circuit_breaker.time")
    def test_failure_after_semi_open_reopens(self, mock_time):
        """半开状态下再次失败 → 重新熔断（重置冷却计时器）。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _cb_is_open,
            _CIRCUIT_BREAKER_RECOVERY,
        )

        url = "https://api.test.com/v1"
        mock_time.time.return_value = 1000.0

        # 3 次失败 → 熔断开启
        for _ in range(3):
            _cb_record_failure(url)
        self.assertTrue(_cb_is_open(url))

        # 快进到冷却期后 → 半开
        mock_time.time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY + 1
        self.assertFalse(_cb_is_open(url))  # 半开

        # 半开状态下再次失败（第 4 次）→ 重新熔断
        _cb_record_failure(url)
        self.assertTrue(_cb_is_open(url))

        # 新冷却期内仍然熔断
        mock_time.time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY + 30
        self.assertTrue(_cb_is_open(url))

        # 新冷却期结束 → 半开
        mock_time.time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY * 2 + 1
        self.assertFalse(_cb_is_open(url))


class TestCircuitBreakerIndependentEndpoints(unittest.TestCase):
    """不同 endpoint 独立熔断。"""

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

    def test_independent_endpoints(self):
        """不同 endpoint 的失败计数互不影响。"""
        from src.python.llm.circuit_breaker import _cb_record_failure, _cb_is_open

        url_a = "https://api.anthropic.com/v1/messages"
        url_b = "https://api.openai.com/v1/chat/completions"

        # api.anthropic.com 3 次失败 → 熔断
        for _ in range(3):
            _cb_record_failure(url_a)
        self.assertTrue(_cb_is_open(url_a))
        # api.openai.com 不受影响
        self.assertFalse(_cb_is_open(url_b))

        # api.openai.com 2 次失败 → 不熔断
        _cb_record_failure(url_b)
        _cb_record_failure(url_b)
        self.assertFalse(_cb_is_open(url_b))

    def test_success_only_resets_its_endpoint(self):
        """成功重置仅影响对应 endpoint。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _cb_record_success, _cb_is_open,
        )

        url_a = "https://api.anthropic.com/v1/messages"
        url_b = "https://api.openai.com/v1/chat/completions"

        for _ in range(3):
            _cb_record_failure(url_a)
        for _ in range(3):
            _cb_record_failure(url_b)

        self.assertTrue(_cb_is_open(url_a))
        self.assertTrue(_cb_is_open(url_b))

        # 只重置 url_a
        _cb_record_success(url_a)
        self.assertFalse(_cb_is_open(url_a))
        self.assertTrue(_cb_is_open(url_b))


class TestCircuitBreakerEdgeCases(unittest.TestCase):
    """熔断器边界场景测试。"""

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

    def test_empty_url_not_open(self):
        """空 URL → 熔断器不开启。"""
        from src.python.llm.circuit_breaker import _cb_is_open
        self.assertFalse(_cb_is_open(""))

    def test_none_url_not_open(self):
        """None URL → 熔断器不开启。"""
        from src.python.llm.circuit_breaker import _cb_is_open
        self.assertFalse(_cb_is_open(None))

    def test_success_on_clean_state(self):
        """未熔断时调用 success → 无副作用。"""
        from src.python.llm.circuit_breaker import _cb_record_success, _cb_is_open
        _cb_record_success("https://api.test.com/v1")
        self.assertFalse(_cb_is_open("https://api.test.com/v1"))

    def test_failure_count_reset_on_success(self):
        """成功后失败计数清零，重新从 1 开始计数。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _cb_record_success, _cb_is_open,
        )


        url = "https://api.test.com/v1"
        _cb_record_failure(url)  # 1
        _cb_record_failure(url)  # 2
        _cb_record_success(url)  # 重置
        _cb_record_failure(url)  # 1（从 0 重新开始）
        _cb_record_failure(url)  # 2
        self.assertFalse(_cb_is_open(url))  # 还需一次才到 3


class TestCircuitBreakerEndpoint(unittest.TestCase):
    """_cb_endpoint URL 解析与基础计数测试。"""

    def test_endpoint_normal(self):
        """标准 URL → 提取域名。"""
        from src.python.llm.circuit_breaker import _cb_endpoint
        self.assertEqual(_cb_endpoint("https://api.anthropic.com/v1/messages"), "api.anthropic.com")

    def test_endpoint_empty(self):
        """空 URL → unknown。"""
        from src.python.llm.circuit_breaker import _cb_endpoint
        self.assertEqual(_cb_endpoint(""), "unknown")

    def test_endpoint_invalid(self):
        """无效 URL → unknown。"""
        from src.python.llm.circuit_breaker import _cb_endpoint
        self.assertEqual(_cb_endpoint("not-a-url"), "unknown")

    def test_failure_count_increments(self):
        """连续记录失败 → 计数递增。"""
        from src.python.llm.circuit_breaker import (
            _cb_record_failure, _circuit_failures,
        )
        _circuit_failures.clear()
        _cb_record_failure("https://api.anthropic.com/v1/messages")
        _cb_record_failure("https://api.anthropic.com/v1/messages")
        self.assertEqual(_circuit_failures.get("api.anthropic.com"), 2)
        _circuit_failures.clear()

    def test_unknown_endpoint_not_open(self):
        """未记录的 endpoint → 熔断关闭。"""
        from src.python.llm.circuit_breaker import _cb_is_open
        self.assertFalse(_cb_is_open("https://api.unknown.com/v1"))


if __name__ == "__main__":
    unittest.main()

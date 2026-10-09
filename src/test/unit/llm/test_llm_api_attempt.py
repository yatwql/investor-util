"""测试：LLM API 基础模块 — 单次调用尝试与重试策略表（api_base.py 分片）。

覆盖：
  - attempt_api_call：200 成功 / 429 / 503 / 超时 / HTTP 错误 / JSON 解码异常分支
  - 429 诊断建议回显（并发/间隔配置现值、绑定项判定、两级到底推配额）
  - retry_policy_factory：尝试次数跟随 max_retries 与手工退避表 / 上限钳位

运行：
  pytest src/test/unit/llm/test_llm_api_attempt.py -v
"""

import unittest
from unittest.mock import MagicMock, patch
import httpx
import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
]


class TestAttemptApiCall(unittest.TestCase):
    """_attempt_api_call — 单次 HTTP 调用。"""

    def setUp(self) -> None:
        from src.python.llm.api_base import _attempt_api_call

        self._attempt_api_call = _attempt_api_call

    def test_returns_success_status_and_payload_on_200(self) -> None:
        """200 OK → ('success', data)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": "hello"}
        mock_client.post.return_value = mock_response

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "success")
        self.assertEqual(info, {"content": "hello"})

    def test_rate_limit_429(self) -> None:
        """429 属限速终态 → ('quota', 429)（不进退避重试，交下游长冷却熔断）。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "quota")
        self.assertEqual(info, 429)

    def test_rate_limit_429_log_hints_both_concurrency_knobs(self) -> None:
        """429 日志同时给出全局（llm_max_concurrency）与端点级（pacing.max_concurrency）两个旋钮。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with self.assertLogs(level="WARNING") as cm:
            self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        log_text = "\n".join(cm.output)
        self.assertIn("llm_max_concurrency", log_text)
        self.assertIn("pacing.max_concurrency", log_text)

    def test_rate_limit_429_log_echoes_configured_values(self) -> None:
        """429 日志回显实际配置值：全局 llm_max_concurrency 与该 provider 的 pacing.max_concurrency。"""
        from src.python.llm.pacing import PacingPolicy

        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 5}),
            patch(
                "src.python.llm.pacing.get_policy",
                return_value=PacingPolicy(min_interval=1.0, max_concurrency=2),
            ),
        ):
            with self.assertLogs(level="WARNING") as cm:
                self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0, "kimi-main")
        log_text = "\n".join(cm.output)
        self.assertIn("llm_max_concurrency=5", log_text)
        self.assertIn("pacing.max_concurrency=2", log_text)
        self.assertIn("provider[kimi-main]", log_text)

    def test_rate_limit_429_log_echoes_min_interval_value_when_advised(self) -> None:
        """建议「加大 pacing.min_interval」时回显现值（配置行 + 建议句双处可见）。"""
        from src.python.llm.pacing import PacingPolicy

        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 3}),
            patch(
                "src.python.llm.pacing.get_policy",
                return_value=PacingPolicy(min_interval=1.5, max_concurrency=1),
            ),
        ):
            with self.assertLogs(level="WARNING") as cm:
                self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0, "kimi-main")
        log_text = "\n".join(cm.output)
        self.assertIn("pacing.min_interval=1.5s", log_text, "配置回显行应带 min_interval 现值")
        self.assertIn("min_interval（当前 1.5s）", log_text, "建议句应带 min_interval 现值")

    def test_rate_limit_429_log_marks_min_interval_unconfigured(self) -> None:
        """该端点未声明 pacing 时 min_interval 显式标「未配置」，不留空误导。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 3}),
            patch("src.python.llm.pacing.get_policy", return_value=None),
        ):
            with self.assertLogs(level="WARNING") as cm:
                self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0, "deepseek-main")
        log_text = "\n".join(cm.output)
        self.assertIn("pacing.min_interval=未配置", log_text)

    def test_rate_limit_429_endpoint_already_at_floor_skips_lowering_endpoint_advice(self) -> None:
        """端点=1（生效并发=min(全局,端点)=1）时：不叫调低端点，也不叫调低全局——只推 min_interval。

        回归场景：全局 3 / 端点 1 时，调低全局（3→2→1）对 min(3,1)=1 毫无影响，
        旧文案「建议调低全局 llm_max_concurrency（当前 3）」是恒无效的空话建议。
        """
        from src.python.llm.pacing import PacingPolicy

        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 3}),
            patch(
                "src.python.llm.pacing.get_policy",
                return_value=PacingPolicy(min_interval=0.0, max_concurrency=1),
            ),
        ):
            with self.assertLogs(level="WARNING") as cm:
                self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0, "kimi-main")
        log_text = "\n".join(cm.output)
        self.assertIn("pacing.max_concurrency=1", log_text)
        self.assertIn("无可再降", log_text)
        self.assertNotIn("按端点限流", log_text)
        self.assertNotIn("建议调低全局", log_text, "端点=1 时调低全局不减少该端点在途并发，不得作为建议给出")
        self.assertIn("不减少该端点在途并发", log_text, "应解释为何调低全局无效")
        self.assertIn("min_interval（当前 0s）", log_text, "应改推带当前值的间隔旋钮")

    def test_rate_limit_429_endpoint_binding_suggests_only_endpoint_knob(self) -> None:
        """端点 < 全局（端点绑定生效并发）时：只建议调低端点，不笼统叫调低全局。"""
        from src.python.llm.pacing import PacingPolicy

        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 5}),
            patch(
                "src.python.llm.pacing.get_policy",
                return_value=PacingPolicy(min_interval=1.0, max_concurrency=2),
            ),
        ):
            with self.assertLogs(level="WARNING") as cm:
                self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0, "kimi-main")
        log_text = "\n".join(cm.output)
        self.assertIn("由端点绑定", log_text)
        self.assertNotIn("或调低全局 llm_max_concurrency", log_text, "全局非绑定项，不得并列作建议")
        self.assertIn("调低全局（当前 5）须低于端点值才生效", log_text, "如提及全局须说明生效条件")

    def test_rate_limit_429_global_binding_suggests_only_global_knob(self) -> None:
        """全局 < 端点（全局绑定生效并发）时：只建议调低全局，不叫人调无效的端点值。"""
        from src.python.llm.pacing import PacingPolicy

        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 2}),
            patch(
                "src.python.llm.pacing.get_policy",
                return_value=PacingPolicy(min_interval=1.0, max_concurrency=5),
            ),
        ):
            with self.assertLogs(level="WARNING") as cm:
                self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0, "kimi-main")
        log_text = "\n".join(cm.output)
        self.assertIn("建议调低全局 llm_max_concurrency（当前 2）", log_text)
        self.assertNotIn("建议调低 provider", log_text, "端点 5 高于全局，逐步调低它不改变生效并发")
        self.assertIn("由全局绑定", log_text)

    def test_rate_limit_429_equal_knobs_suggests_both(self) -> None:
        """两级相等（均为绑定项）时：两个旋钮都列出，调低任一生效并发即降。"""
        from src.python.llm.pacing import PacingPolicy

        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 3}),
            patch(
                "src.python.llm.pacing.get_policy",
                return_value=PacingPolicy(min_interval=1.0, max_concurrency=3),
            ),
        ):
            with self.assertLogs(level="WARNING") as cm:
                self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0, "kimi-main")
        log_text = "\n".join(cm.output)
        self.assertIn("两级相等均为绑定项", log_text)
        self.assertIn("pacing.max_concurrency（当前 3，最低 1）", log_text)
        self.assertIn("llm_max_concurrency（当前 3）", log_text)

    def test_rate_limit_429_both_knobs_at_floor_points_to_quota(self) -> None:
        """全局与端点并发均为 1（均无下降空间）时，提示并发已到底、429 更可能来自配额/风控。"""
        from src.python.llm.pacing import PacingPolicy

        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.post.return_value = mock_response

        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 1}),
            patch(
                "src.python.llm.pacing.get_policy",
                return_value=PacingPolicy(min_interval=1.0, max_concurrency=1),
            ),
        ):
            with self.assertLogs(level="WARNING") as cm:
                self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0, "kimi-main")
        log_text = "\n".join(cm.output)
        self.assertIn("再调低并发已无益", log_text)
        self.assertIn("配额", log_text)
        self.assertNotIn("按端点限流", log_text)
        self.assertNotIn("建议调低", log_text, "生效并发=1 时不得给出任何调低并发类建议")

    def test_service_unavailable_503(self) -> None:
        """503 → ('retryable', 503)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_client.post.return_value = mock_response

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "retryable")
        self.assertEqual(info, 503)

    def test_timeout_exception(self) -> None:
        """httpx.TimeoutException → ('retryable', None)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.TimeoutException("timeout")

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "retryable")
        self.assertIsNone(info)

    def test_http_error(self) -> None:
        """httpx.HTTPError → ('retryable', host)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.HTTPError("connection error")

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com/path", {}, {}, 30.0)
        self.assertEqual(kind, "retryable")
        self.assertEqual(info, "api.test.com")

    def test_json_decode_error(self) -> None:
        """JSON 解析失败 → ('fatal', errmsg)。"""
        mock_client = MagicMock(spec=httpx.Client)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.post.return_value = mock_response

        kind, info = self._attempt_api_call(mock_client, "https://api.test.com", {}, {}, 30.0)
        self.assertEqual(kind, "fatal")
        self.assertIsInstance(info, str)


class TestRetryPolicyFactory(unittest.TestCase):
    """_retry_policy — LLM 重试策略（显式退避序列）契约。"""

    def test_attempts_follow_max_retries(self) -> None:
        """总尝试次数 = max_retries + 1。"""
        from src.python.llm.api_base import _retry_policy

        self.assertEqual(_retry_policy(2).attempts, 3)
        self.assertEqual(_retry_policy(0).attempts, 1)

    def test_delays_match_hand_tuned_table(self) -> None:
        """退避序列与手工调优表逐项一致。"""
        from src.python.llm.api_base import _RETRY_DELAYS, _retry_policy

        policy = _retry_policy(len(_RETRY_DELAYS))
        self.assertEqual([policy.delay_for(i) for i in range(1, len(_RETRY_DELAYS) + 1)], list(_RETRY_DELAYS))

    def test_delay_clamped_beyond_table(self) -> None:
        """max_retries 超出表长时锁定末位值（不越界）。"""
        from src.python.llm.api_base import _RETRY_DELAYS, _retry_policy

        policy = _retry_policy(len(_RETRY_DELAYS) + 3)
        self.assertEqual(policy.delay_for(len(_RETRY_DELAYS) + 3), _RETRY_DELAYS[-1])

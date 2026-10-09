"""测试：LLM API 基础模块 — call_llm_with_retry 错误分支（api_base.py 分片）。

覆盖：
  - HTTP 错误分支：429 首试即熔断（零重试）、503 重试、退避取自策略表、表外锁最后延迟、超时与成功穿插
  - 响应解析错误 / 内容过滤 / 截断分支的重试与耗尽行为
  - 截断警告文案标记（`_make_mock_response` 等响应桩助手随本分片）

运行：
  pytest src/test/unit/llm/test_llm_api_retry_errors.py -v
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


class TestTruncationWarning(unittest.TestCase):
    """_truncation_warning — 截断警告。"""

    def test_warning_contains_marker(self) -> None:
        """警告含截断标记。"""
        from src.python.llm.api_base import TRUNCATION_MARKER, _truncation_warning

        warning = _truncation_warning("max_tokens")
        self.assertIn(TRUNCATION_MARKER, warning)
        self.assertIn("max_tokens", warning)


# ═══════════════════════════════════════════════════════════════
#  call_llm_with_retry — HTTP 错误码/内容过滤/截断
#  使用 mock Response 对象构造，覆盖具体 HTTP 错误码场景
# ═══════════════════════════════════════════════════════════════


def _make_mock_response(status_code: int = 200, json_data: dict | None = None, usage: dict | None = None) -> MagicMock:
    """创建模拟 httpx.Response。"""
    if json_data is None:
        json_data = {"content": [{"type": "text", "text": "回复"}]}
    if usage is not None:
        json_data["usage"] = usage

    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data

    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None

    return resp


def _default_extract(data: dict) -> str:
    return data.get("content", [{}])[0].get("text", "")


def _no_truncation(data: dict, mt: int) -> bool:
    return False


class TestCallLlmWithRetryHttpErrors(unittest.TestCase):
    """call_llm_with_retry — HTTP 错误码重试 + 最终失败。"""

    def setUp(self) -> None:
        self.client = MagicMock(spec=httpx.Client)
        self.base_kw = dict(
            label="Test",
            client=self.client,
            url="https://api.test.com/v1",
            headers={},
            payload={"model": "test"},
            timeout=60,
            max_retries=2,
            max_tokens=1000,
            config_field="max_tokens",
            extract_fn=_default_extract,
            check_truncation_fn=_no_truncation,
            provider="claude",
            model_name="test-model",
        )
        self.cb_patcher = patch("src.python.llm.api_base._cb_is_open", return_value=False)
        self.cb_patcher.start()

    def tearDown(self) -> None:
        self.cb_patcher.stop()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("src.python.llm.api_base._log_token_usage")
    @patch("src.python.llm.api_base.track_session_usage")
    def test_success_first_try(self, mock_track, mock_log, mock_success):
        """首次调用成功。"""
        usage = {"input_tokens": 10, "output_tokens": 5}
        self.client.post.return_value = _make_mock_response(
            200,
            {"content": [{"type": "text", "text": "OK"}]},
            usage=usage,
        )
        from src.python.llm.api_base import call_llm_with_retry

        result, u = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(u["input_tokens"], 10)
        mock_success.assert_called_once()
        mock_log.assert_called_once()
        mock_track.assert_called_once()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_429_fails_first_attempt_without_retry(self, mock_sleep, mock_success):
        """429 属配额终态：首试即失败，不发第二次请求（零退避重试）。"""
        from src.python.llm.api_base import call_llm_with_retry

        self.client.post.return_value = _make_mock_response(429)
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 1)
        mock_sleep.assert_not_called()
        mock_success.assert_not_called()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_retry_delays_come_from_policy_table(self, mock_sleep, mock_success):
        """两次重试分别等待 1s、3s（退避数值来自统一策略，而非本模块自算；用 503——429 已不重试）。"""
        from src.python.llm.api_base import call_llm_with_retry

        succeed = _make_mock_response(200, {"content": [{"type": "text", "text": "OK"}]})
        self.client.post.side_effect = [_make_mock_response(503), _make_mock_response(503), succeed]
        result, _usage = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual([c.args[0] for c in mock_sleep.call_args_list], [1.0, 3.0])

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_retry_beyond_table_locks_last_delay(self, mock_sleep, mock_failure):
        """max_retries 超过退避表长度时不越界，末位值重复使用（用 503——429 已不重试）。"""
        from src.python.llm.api_base import _RETRY_DELAYS, call_llm_with_retry

        self.client.post.return_value = _make_mock_response(503)
        kw = dict(self.base_kw, max_retries=len(_RETRY_DELAYS) + 2)
        result, usage = call_llm_with_retry(**kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, len(_RETRY_DELAYS) + 3)
        self.assertEqual(mock_sleep.call_args_list[-1].args[0], _RETRY_DELAYS[-1])

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_429_log_carries_endpoint_key_to_attempt(self, mock_sleep, mock_failure):
        """endpoint_key 必须透传到 _attempt_api_call，否则 429 日志丢 provider 条目名。"""
        from src.python.llm.api_base import call_llm_with_retry
        from src.python.llm.pacing import PacingPolicy

        self.client.post.return_value = _make_mock_response(429)
        kw = dict(self.base_kw, endpoint_key="kimi-main")
        with (
            patch("src.python.config.get_llm_config", return_value={"llm_max_concurrency": 3}),
            patch("src.python.llm.pacing.get_policy", return_value=PacingPolicy(max_concurrency=1)),
        ):
            with self.assertLogs(level="WARNING") as cm:
                result, usage = call_llm_with_retry(**kw)

        self.assertIsNone(result)
        self.assertIsNone(usage)
        log_text = "\n".join(cm.output)
        self.assertIn("provider[kimi-main]", log_text)
        self.assertIn("pacing.max_concurrency=1", log_text)

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_429_fails_single_attempt_all(self, mock_sleep, mock_failure):
        """429 只发一次请求即失败 → (None, None)，零退避重试。"""
        from src.python.llm.api_base import call_llm_with_retry

        self.client.post.return_value = _make_mock_response(429)
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_429_first_try_forces_long_cooldown(self, mock_sleep, mock_failure):
        """429 首试即以 cooldown=600 + force=True 熔断（零重试），失败原因归配额类。"""
        from src.python.llm.api_base import (
            _RATE_LIMIT_RECOVERY,
            FAIL_REASON_QUOTA_EXCEEDED,
            call_llm_with_retry,
            _get_last_llm_failure,
        )

        self.client.post.return_value = _make_mock_response(429)
        result, usage = call_llm_with_retry(**self.base_kw)

        self.assertIsNone(result)
        self.assertEqual(self.client.post.call_count, 1, "429 不得退避重试")
        mock_failure.assert_called_once()
        _args, kwargs = mock_failure.call_args
        self.assertEqual(kwargs.get("cooldown"), _RATE_LIMIT_RECOVERY)
        self.assertEqual(kwargs.get("cooldown"), 600)
        self.assertIs(kwargs.get("force"), True)
        self.assertEqual(_get_last_llm_failure(), FAIL_REASON_QUOTA_EXCEEDED)

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_non_429_retryable_keeps_default_cooldown(self, mock_sleep, mock_failure):
        """非 429 的可重试失败（如超时）保持默认记录：无 force/cooldown 参数。"""
        from src.python.llm.api_base import call_llm_with_retry

        self.client.post.side_effect = [
            __import__("httpx").TimeoutException("t"),
            __import__("httpx").TimeoutException("t"),
            __import__("httpx").TimeoutException("t"),
        ]
        result, usage = call_llm_with_retry(**self.base_kw)

        self.assertIsNone(result)
        mock_failure.assert_called_once_with(self.base_kw["url"])
        mock_failure.assert_called_once()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_retry_on_503_then_success(self, mock_sleep, mock_success):
        """503 → 重试 → 成功。"""
        from src.python.llm.api_base import call_llm_with_retry

        succeed = _make_mock_response(200, {"content": [{"type": "text", "text": "OK"}]})
        self.client.post.side_effect = [_make_mock_response(503), succeed]
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(self.client.post.call_count, 2)

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_timeout_then_success(self, mock_sleep, mock_success):
        """超时 → 重试 → 成功。"""
        from src.python.llm.api_base import call_llm_with_retry

        succeed = _make_mock_response(200, {"content": [{"type": "text", "text": "OK"}]})
        self.client.post.side_effect = [httpx.TimeoutException("timeout"), succeed]
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(self.client.post.call_count, 2)

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_timeout_all_fail(self, mock_sleep, mock_failure):
        """超时全部重试失败 → (None, None)。"""
        from src.python.llm.api_base import call_llm_with_retry

        self.client.post.side_effect = httpx.TimeoutException("timeout")
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 3)
        mock_failure.assert_called_once()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("time.sleep")
    def test_request_error_then_success(self, mock_sleep, mock_success):
        """网络错误 → 重试 → 成功。"""
        from src.python.llm.api_base import call_llm_with_retry

        succeed = _make_mock_response(200, {"content": [{"type": "text", "text": "OK"}]})
        self.client.post.side_effect = [httpx.RequestError("reset"), succeed]
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertEqual(result, "OK")
        self.assertEqual(self.client.post.call_count, 2)

    @patch("src.python.llm.api_base._cb_record_failure")
    @patch("time.sleep")
    def test_request_error_all_fail(self, mock_sleep, mock_failure):
        """网络错误全部重试失败 → (None, None)。"""
        from src.python.llm.api_base import call_llm_with_retry

        self.client.post.side_effect = httpx.RequestError("reset")
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 3)
        mock_failure.assert_called_once()


class TestCallLlmWithRetryResponseErrors(unittest.TestCase):
    """call_llm_with_retry — 响应解析错误（不重试，立即失败）。"""

    def setUp(self) -> None:
        self.client = MagicMock(spec=httpx.Client)
        self.base_kw = dict(
            label="Test",
            client=self.client,
            url="https://api.test.com/v1",
            headers={},
            payload={},
            timeout=60,
            max_retries=2,
            max_tokens=1000,
            config_field="max_tokens",
            extract_fn=_default_extract,
            check_truncation_fn=_no_truncation,
            provider="claude",
            model_name="",
        )
        self.cb_patcher = patch("src.python.llm.api_base._cb_is_open", return_value=False)
        self.cb_patcher.start()

    def tearDown(self) -> None:
        self.cb_patcher.stop()

    @patch("src.python.llm.api_base._cb_record_failure")
    def test_json_decode_error(self, mock_failure):
        """JSON 解析失败 → 立即失败，不重试。"""
        from src.python.llm.api_base import call_llm_with_retry

        resp = _make_mock_response(200, json_data={"content": [{"type": "text", "text": ""}]})
        resp.json.side_effect = ValueError("Invalid JSON")
        self.client.post.return_value = resp
        result, usage = call_llm_with_retry(**self.base_kw)
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 1)

    @patch("src.python.llm.api_base._cb_record_failure")
    def test_extract_returns_none(self, mock_failure):
        """extract_fn 返回 None → 立即失败。"""
        from src.python.llm.api_base import call_llm_with_retry

        def _none_extract(data):
            return None

        resp = _make_mock_response(200, json_data={"wrong": "format"})
        self.client.post.return_value = resp
        result, usage = call_llm_with_retry(**{**self.base_kw, "extract_fn": _none_extract})
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(self.client.post.call_count, 1)


class TestCallLlmWithRetryContentFilter(unittest.TestCase):
    """call_llm_with_retry — 空内容（内容过滤）处理。"""

    def setUp(self) -> None:
        self.client = MagicMock(spec=httpx.Client)
        self.cb_patcher = patch("src.python.llm.api_base._cb_is_open", return_value=False)
        self.cb_patcher.start()

    def tearDown(self) -> None:
        self.cb_patcher.stop()

    def test_empty_content_returns_with_usage(self) -> None:
        """空内容 → 返回 ("", usage) 供安抚重试。"""
        from src.python.llm.api_base import call_llm_with_retry

        usage = {"input_tokens": 10, "output_tokens": 5}
        data = {"content": [{"type": "text", "text": ""}], "usage": usage}
        resp = _make_mock_response(200, json_data=data)
        self.client.post.return_value = resp

        result, u = call_llm_with_retry(
            "Test",
            self.client,
            "https://api.test.com/v1",
            {},
            {},
            60,
            2,
            1000,
            "max_tokens",
            _default_extract,
            _no_truncation,
            "claude",
            "",
        )
        self.assertEqual(result, "")
        self.assertEqual(u["input_tokens"], 10)


class TestCallLlmWithRetryTruncation(unittest.TestCase):
    """call_llm_with_retry — 截断检测 + 警告追加。"""

    def setUp(self) -> None:
        self.client = MagicMock(spec=httpx.Client)
        self.cb_patcher = patch("src.python.llm.api_base._cb_is_open", return_value=False)
        self.cb_patcher.start()

    def tearDown(self) -> None:
        self.cb_patcher.stop()

    @patch("src.python.llm.api_base._cb_record_success")
    @patch("src.python.llm.api_base._log_token_usage")
    @patch("src.python.llm.api_base.track_session_usage")
    def test_truncation_appends_warning(self, mock_track, mock_log, mock_success):
        """截断 → 内容追加截断警告。"""
        from src.python.llm.api_base import TRUNCATION_MARKER, call_llm_with_retry

        def _truncated(data, mt):
            return True

        data = {"content": [{"type": "text", "text": "部分内容"}], "usage": {"input_tokens": 10, "output_tokens": 800}}
        resp = _make_mock_response(200, json_data=data)
        self.client.post.return_value = resp

        result, usage = call_llm_with_retry(
            "Test",
            self.client,
            "https://api.test.com/v1",
            {},
            {},
            60,
            2,
            800,
            "max_tokens_expert_review",
            _default_extract,
            _truncated,
            "claude",
            "",
        )
        self.assertIn("max_tokens_expert_review", result)
        self.assertIn(TRUNCATION_MARKER, result)
        self.assertIn("部分内容", result)
